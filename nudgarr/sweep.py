"""
nudgarr/sweep.py

Core sweep engine — picks eligible items, applies cooldown, searches,
records results, prunes state, and returns a summary dict.

  run_sweep        -- orchestration: loops all instances, returns summary
  _sweep_instance  -- private: one Radarr or Sonarr instance, returns instance summary

All persistence goes through db.py directly.  The st_bucket dict
pattern from v3.0 is gone — cooldown checks and search marking operate
on the database per item.

Imports from within the package: globals, arr_clients, db, stats, utils.
"""

import logging
import time
from datetime import timedelta
from typing import Any, Dict, List, Set

import requests

from nudgarr import db
from nudgarr.arr_clients import (
    arr_get_tag_map,
    arr_get_profile_map,
    radarr_get_cutoff_unmet_movies,
    radarr_get_missing_movies,
    radarr_get_queued_movie_ids,
    radarr_get_movie_quality,
    radarr_search_movies,
    sonarr_get_cutoff_unmet_episodes,
    sonarr_get_missing_episodes,
    sonarr_get_queued_episode_ids,
    sonarr_get_episode_quality,
    sonarr_search_episodes,
    _sonarr_get_series_meta,
)
from nudgarr.constants import VALID_SAMPLE_MODES, VALID_BACKLOG_SAMPLE_MODES
from nudgarr.globals import STATUS
from nudgarr.state import load_exclusions, prune_state_by_retention, state_key
from nudgarr.stats import (
    batch_record_stat_entries,
    mark_items_searched,
    pick_items_with_cooldown,
)
from nudgarr.utils import iso_z, jitter_sleep, mask_url, parse_iso, utcnow

logger = logging.getLogger(__name__)


# ── Private per-instance helper ───────────────────────────────────────

def _sweep_instance(
    session: requests.Session,
    inst: Dict[str, Any],
    cfg: Dict[str, Any],
    excluded_titles: Set[str],
    cooldown_hours: int,
    max_per_run: int,
    sample_mode: str,
    batch_size: int,
    sleep_seconds: float,
    jitter_seconds: float,
    missing_max: int,
    backlog_enabled: bool,
    notifications_enabled: bool,
    app: str,
    missing_added_days: int = 0,
    backlog_sample_mode: str = "random",
) -> Dict[str, Any]:
    """Run one Radarr or Sonarr instance through a full sweep cycle.

    app must be "radarr" or "sonarr". The pipeline is identical for both apps;
    differences are isolated to four points:

      - Radarr only: minimumAvailability filter after queue skip
      - Radarr only: missing_added_days age filter before cooldown pick
      - Sonarr only: _series_meta pre-fetch passed to both cutoff and missing calls
      - App-specific callables (get_cutoff, get_missing, get_queue_ids,
        get_quality, search) resolved from app parameter

    All resolved values (cooldown, caps, modes) arrive pre-resolved from
    run_sweep via _resolve() — this function never reads cfg directly for those.

    sample_mode controls the cutoff unmet pipeline pick order.
    backlog_sample_mode controls the backlog (missing) pipeline pick order
    independently. Both are validated against their respective constants before
    being passed in — invalid values fall back to "random" in run_sweep.

    Returns a summary dict consumed by run_sweep and ultimately /api/status.
    """
    assert app in ("radarr", "sonarr"), f"Unknown app: {app}"
    APP = app.capitalize()
    name, url, key = inst["name"], inst["url"], inst["key"]
    inst_url = url.rstrip("/")

    # App-specific callables
    if app == "radarr":
        fn_get_cutoff = radarr_get_cutoff_unmet_movies
        fn_get_missing = radarr_get_missing_movies
        fn_get_queue_ids = radarr_get_queued_movie_ids
        fn_get_quality = radarr_get_movie_quality
        fn_search = radarr_search_movies
        item_type = "movie"
        missing_type = "missing_movie"
        series_meta = None  # Radarr has no series meta pre-fetch
    else:
        fn_get_cutoff = sonarr_get_cutoff_unmet_episodes
        fn_get_missing = sonarr_get_missing_episodes
        fn_get_queue_ids = sonarr_get_queued_episode_ids
        fn_get_quality = sonarr_get_episode_quality
        fn_search = sonarr_search_episodes
        item_type = "episode"
        missing_type = "missing_episode"
        # Fetch series meta once — passed to both cutoff and missing fetches
        # to avoid a redundant /api/v3/series call when backlog is enabled.
        series_meta = _sonarr_get_series_meta(session, url, key)

    # Read per-instance sweep filters — empty sets mean no filtering applied
    sweep_filters = inst.get("sweep_filters", {})
    excluded_tags = set(int(t) for t in sweep_filters.get("excluded_tags", []))
    excluded_profiles = set(int(p) for p in sweep_filters.get("excluded_profiles", []))

    # Fetch tag/profile maps once if filtering is active — used for debug logs only
    tag_map = arr_get_tag_map(session, url, key) if excluded_tags else {}
    profile_map = arr_get_profile_map(session, url, key) if excluded_profiles else {}

    # ── Cutoff-unmet pipeline ──────────────────────────────────────────

    if app == "radarr":
        all_items = fn_get_cutoff(session, url, key)
    else:
        all_items = fn_get_cutoff(session, url, key, series_meta=series_meta)
    all_items = [m for m in all_items if (m.get("title") or "").lower() not in excluded_titles]

    # Tag filter
    skipped_tag = 0
    if excluded_tags:
        filtered = []
        for m in all_items:
            hits = excluded_tags & set(m.get("tagIds") or [])
            if hits:
                for tid in hits:
                    logger.debug("[%s:%s] skipped_tag: %s (tag=%s)",
                                 APP, name, m.get("title", "?"), tag_map.get(tid, tid))
                skipped_tag += len(hits)
            else:
                filtered.append(m)
        all_items = filtered

    # Profile filter
    skipped_profile = 0
    if excluded_profiles:
        filtered = []
        for m in all_items:
            pid = m.get("qualityProfileId")
            if pid in excluded_profiles:
                logger.debug("[%s:%s] skipped_profile: %s (profile=%s)",
                             APP, name, m.get("title", "?"), profile_map.get(pid, pid))
                skipped_profile += 1
            else:
                filtered.append(m)
        all_items = filtered

    # Queue skip
    queue_ids = fn_get_queue_ids(session, url, key)
    queued_skipped = [m for m in all_items if m["id"] in queue_ids]
    all_items = [m for m in all_items if m["id"] not in queue_ids]
    for m in queued_skipped:
        logger.debug("[%s:%s] skipped_queued: %s (id=%s)", APP, name, m.get("title", "?"), m["id"])

    # Availability filter — Radarr only
    skipped_unavailable: List[Dict[str, Any]] = []
    if app == "radarr":
        skipped_unavailable = [m for m in all_items if not m.get("isAvailable", True)]
        all_items = [m for m in all_items if m.get("isAvailable", True)]
        if skipped_unavailable:
            for m in skipped_unavailable:
                threshold = m.get("minimumAvailability") or "unknown"
                release = m.get("releaseDate") or "no date"
                logger.debug("[Radarr:%s] skipped_not_available: %s (minimumAvailability=%s, releaseDate=%s)",
                             name, m.get("title", "?"), threshold, release)

    STATUS["instance_health"][f"{app}|{name}"] = "ok"
    all_ids = [m["id"] for m in all_items]

    chosen_items, eligible, skipped = pick_items_with_cooldown(
        all_items, app, name, inst_url, item_type,
        cooldown_hours, max_per_run, sample_mode
    )

    if app == "radarr":
        logger.info(
            "[Radarr:%s] cutoff_unmet_total=%d eligible=%d skipped_tag=%d "
            "skipped_profile=%d skipped_queued=%d skipped_not_available=%d "
            "skipped_cooldown=%d will_search=%d limit=%d",
            name, len(all_ids), eligible, skipped_tag, skipped_profile,
            len(queued_skipped), len(skipped_unavailable), skipped,
            len(chosen_items), max_per_run,
        )
    else:
        logger.info(
            "[Sonarr:%s] cutoff_unmet_total=%d eligible=%d skipped_tag=%d "
            "skipped_profile=%d skipped_queued=%d skipped_cooldown=%d "
            "will_search=%d limit=%d",
            name, len(all_ids), eligible, skipped_tag, skipped_profile,
            len(queued_skipped), skipped, len(chosen_items), max_per_run,
        )

    # Search loop — cutoff items
    searched = 0
    for i in range(0, len(chosen_items), batch_size):
        batch_items = chosen_items[i:i + batch_size]
        batch_ids = [m["id"] for m in batch_items]
        for m in batch_items:
            logger.debug("[%s:%s] cutoff item: %s (id=%s quality_from=%s)",
                         APP, name, m.get("title", "?"), m["id"], m.get("quality_from", ""))
            if not m.get("quality_from"):
                m["quality_from"] = fn_get_quality(session, url, key, m["id"])
                logger.debug("[%s:%s] quality_from fallback fetch: %s → %s",
                             APP, name, m.get("title", "?"), m.get("quality_from") or "(empty)")
        fn_search(session, url, key, batch_ids, instance_name=name)
        mark_items_searched(app, name, inst_url, item_type, batch_items, "Cutoff")
        batch_record_stat_entries(app, name, inst_url, batch_items, "Upgraded", iso_z(utcnow()))
        searched += len(batch_items)
        if i + batch_size < len(chosen_items):
            jitter_sleep(sleep_seconds, jitter_seconds)

    # ── Backlog pipeline ───────────────────────────────────────────────

    missing_total = 0
    eligible_missing = 0
    skipped_missing = 0
    searched_missing = 0
    chosen_missing: List[Dict[str, Any]] = []

    if backlog_enabled and missing_max > 0:
        if app == "radarr":
            missing_records = fn_get_missing(session, url, key)
        else:
            missing_records = fn_get_missing(session, url, key, series_meta=series_meta)
        missing_records = [m for m in missing_records
                           if (m.get("title") or "").lower() not in excluded_titles]

        queued_skipped_missing = [m for m in missing_records if m["id"] in queue_ids]
        missing_records = [m for m in missing_records if m["id"] not in queue_ids]
        for m in queued_skipped_missing:
            logger.debug("[%s:%s] skipped_queued (backlog): %s (id=%s)",
                         APP, name, m.get("title", "?"), m["id"])

        # Radarr only — availability filter on backlog
        if app == "radarr":
            missing_records = [m for m in missing_records if m.get("isAvailable", True)]

        # Tag filter — backlog pipeline
        if excluded_tags:
            filtered = []
            for m in missing_records:
                hits = excluded_tags & set(m.get("tagIds") or [])
                if hits:
                    for tid in hits:
                        logger.debug("[%s:%s] skipped_tag (backlog): %s (tag=%s)",
                                     APP, name, m.get("title", "?"), tag_map.get(tid, tid))
                    skipped_tag += len(hits)
                else:
                    filtered.append(m)
            missing_records = filtered

        # Profile filter — backlog pipeline
        if excluded_profiles:
            filtered = []
            for m in missing_records:
                pid = m.get("qualityProfileId")
                if pid in excluded_profiles:
                    logger.debug("[%s:%s] skipped_profile (backlog): %s (profile=%s)",
                                 APP, name, m.get("title", "?"), profile_map.get(pid, pid))
                    skipped_profile += 1
                else:
                    filtered.append(m)
            missing_records = filtered

        missing_total = len(missing_records)

        # Age filter — Radarr only
        if app == "radarr" and missing_added_days > 0:
            missing_filtered: List[Dict[str, Any]] = []
            for rec in missing_records:
                added_s = rec.get("added")
                ok_old = True
                if isinstance(added_s, str):
                    dt = parse_iso(added_s)
                    if dt is not None:
                        ok_old = dt <= (utcnow() - timedelta(days=missing_added_days))
                if ok_old:
                    missing_filtered.append(rec)
            missing_records = missing_filtered

        chosen_missing, eligible_missing, skipped_missing = pick_items_with_cooldown(
            missing_records, app, name, inst_url, missing_type,
            # backlog_sample_mode is independent of sample_mode (cutoff pipeline).
            # Both arrive pre-resolved from run_sweep — invalid values fall back
            # to "random" before reaching this point.
            cooldown_hours, missing_max, backlog_sample_mode
        )

        if app == "radarr":
            logger.info(
                "[Radarr:%s] missing_total=%d eligible_missing=%d "
                "skipped_missing_cooldown=%d will_search_missing=%d "
                "limit_missing=%d older_than_days=%d",
                name, missing_total, eligible_missing, skipped_missing,
                len(chosen_missing), missing_max, missing_added_days,
            )
        else:
            logger.info(
                "[Sonarr:%s] missing_total=%d eligible_missing=%d "
                "skipped_missing_cooldown=%d will_search_missing=%d limit_missing=%d",
                name, missing_total, eligible_missing, skipped_missing,
                len(chosen_missing), missing_max,
            )

        # Search loop — backlog items
        for i in range(0, len(chosen_missing), batch_size):
            batch_items = chosen_missing[i:i + batch_size]
            batch_ids = [m["id"] for m in batch_items]
            for m in batch_items:
                logger.debug("[%s:%s] backlog item: %s (id=%s quality_from=%s)",
                             APP, name, m.get("title", "?"), m["id"], m.get("quality_from", ""))
                if not m.get("quality_from"):
                    m["quality_from"] = fn_get_quality(session, url, key, m["id"])
                    logger.debug("[%s:%s] quality_from fallback fetch: %s → %s",
                                 APP, name, m.get("title", "?"), m.get("quality_from") or "(empty)")
            fn_search(session, url, key, batch_ids, instance_name=name)
            mark_items_searched(app, name, inst_url, missing_type, batch_items, "Backlog")
            batch_record_stat_entries(app, name, inst_url, batch_items, "Acquired", iso_z(utcnow()))
            searched_missing += len(batch_items)
            if i + batch_size < len(chosen_missing):
                jitter_sleep(sleep_seconds, jitter_seconds)

    result: Dict[str, Any] = {
        "name": name,
        "url": mask_url(url),
        "cutoff_unmet_total": len(all_ids),
        "eligible": eligible,
        "skipped_cooldown": skipped,
        "will_search": len(chosen_items),
        "searched": searched,
        "limit": max_per_run,
        "missing_total": missing_total,
        "eligible_missing": eligible_missing,
        "skipped_missing_cooldown": skipped_missing,
        "will_search_missing": len(chosen_missing),
        "searched_missing": searched_missing,
        "limit_missing": missing_max,
        "notifications_enabled": notifications_enabled,
    }
    if app == "radarr":
        result["missing_added_days"] = missing_added_days
    return result


# ── Override resolver ─────────────────────────────────────────────────

def _resolve(inst: Dict[str, Any], cfg: Dict[str, Any], overrides_enabled: bool,
             key: str, global_val: Any) -> Any:
    """Return per-instance override for key if overrides are enabled and set, else global_val."""
    if not overrides_enabled:
        return global_val
    return inst.get("overrides", {}).get(key, global_val)


# ── Auto-unexclude ────────────────────────────────────────────────────

def _run_auto_unexclude(cfg: Dict[str, Any]) -> None:
    """Remove auto-exclusions that have exceeded their configured age threshold.

    Runs at the start of each sweep before excluded_titles is built, so any
    titles removed here are immediately eligible for the current sweep.

    Two independent thresholds — one for movies (Radarr), one for shows (Sonarr).
    A threshold of 0 means never auto-unexclude for that app.

    Only rows with source='auto' are removed. Manual exclusions are never touched.

    After removing the exclusion row, the search_count is reset to 0 for all
    search_history rows matching that title. Without this reset the import check
    loop would see the count still at or above the threshold and immediately
    re-exclude the title before it ever gets searched again, making the
    auto-unexclude window functionally useless.
    """
    movies_days = int(cfg.get("auto_unexclude_movies_days", 0))
    shows_days = int(cfg.get("auto_unexclude_shows_days", 0))

    # Build a combined set of thresholds to check. We fetch all aged-out rows
    # and determine which threshold applies based on the app — but since the
    # exclusions table has no app column (exclusions are global), we use the
    # most conservative non-zero threshold available when both are set.
    # In practice the two thresholds apply to the same pool, so we run both
    # passes independently using the respective day value.
    for days, label in ((movies_days, "movies"), (shows_days, "shows")):
        if days <= 0:
            continue
        aged = db.get_auto_exclusions_older_than(days)
        for row in aged:
            db.remove_exclusion(row["title"], source="auto")
            # Reset search_count by title so the title gets a genuine fresh
            # start and is not immediately re-excluded on the next import check
            db.reset_search_count_by_title(row["title"])
            logger.info("[Auto-Unexclude] %s removed after %d days (%s threshold)",
                        row["title"], days, label)


# ── Orchestrator ──────────────────────────────────────────────────────

def run_sweep(cfg: Dict[str, Any], session: requests.Session) -> Dict[str, Any]:
    """
    Run one full sweep cycle across all configured Radarr and Sonarr instances.
    Returns a summary dict consumed by the scheduler and /api/status.
    """
    cooldown_hours = int(cfg.get("cooldown_hours", 48))
    radarr_sample_mode = str(cfg.get("radarr_sample_mode", "random")).lower()
    if radarr_sample_mode not in VALID_SAMPLE_MODES:
        radarr_sample_mode = "random"
    sonarr_sample_mode = str(cfg.get("sonarr_sample_mode", "random")).lower()
    if sonarr_sample_mode not in VALID_SAMPLE_MODES:
        sonarr_sample_mode = "random"

    # Backlog sample mode — independent of cutoff sample mode (v4.2.0)
    radarr_backlog_sample_mode = str(cfg.get("radarr_backlog_sample_mode", "random")).lower()
    if radarr_backlog_sample_mode not in VALID_BACKLOG_SAMPLE_MODES:
        radarr_backlog_sample_mode = "random"
    sonarr_backlog_sample_mode = str(cfg.get("sonarr_backlog_sample_mode", "random")).lower()
    if sonarr_backlog_sample_mode not in VALID_BACKLOG_SAMPLE_MODES:
        sonarr_backlog_sample_mode = "random"

    radarr_max = int(cfg.get("radarr_max_movies_per_run", 25))
    sonarr_max = int(cfg.get("sonarr_max_episodes_per_run", 25))
    batch_size = max(1, int(cfg.get("batch_size", 20)))
    sleep_seconds = float(cfg.get("sleep_seconds", 3))
    jitter_seconds = float(cfg.get("jitter_seconds", 2))
    retention_days = int(cfg.get("state_retention_days", 180))

    # ── Auto-unexclude pass ───────────────────────────────────────────
    # Runs before exclusions are loaded so any titles that aged out are
    # already removed by the time the pipeline builds excluded_titles.
    # Only auto-exclusions are touched — manual exclusions are never removed.
    _run_auto_unexclude(cfg)

    exclusions = load_exclusions()
    excluded_titles = {e["title"].lower() for e in exclusions if e.get("title")}

    pruned = prune_state_by_retention(retention_days)

    summary: Dict[str, Any] = {
        "pruned_entries": pruned,
        "radarr": [],
        "sonarr": [],
    }

    overrides_enabled = bool(cfg.get("per_instance_overrides_enabled", False))
    # When overrides_enabled is False, _resolve() is a passthrough — all instances
    # use the global values extracted above. When True, per-instance overrides stored
    # in inst["overrides"] take precedence over globals for any field they define.

    for app, instances, global_max, global_mode, global_missing_max, global_backlog_mode in [
        ("radarr",
         cfg.get("instances", {}).get("radarr", []),
         radarr_max, radarr_sample_mode,
         int(cfg.get("radarr_missing_max", 1)),
         radarr_backlog_sample_mode),
        ("sonarr",
         cfg.get("instances", {}).get("sonarr", []),
         sonarr_max, sonarr_sample_mode,
         int(cfg.get("sonarr_missing_max", 1)),
         sonarr_backlog_sample_mode),
    ]:
        APP = app.capitalize()
        for inst in instances:
            if not inst.get("enabled", True):
                logger.info("[%s:%s] disabled — skipping", APP, inst["name"])
                STATUS["instance_health"][f"{app}|{inst['name']}"] = "disabled"
                continue
            name, url = inst["name"], inst["url"]
            # Resolve per-instance overrides (fall back to global if not set)
            inst_cooldown = _resolve(inst, cfg, overrides_enabled, "cooldown_hours", cooldown_hours)
            inst_max = _resolve(inst, cfg, overrides_enabled, "max_cutoff_unmet", global_max)
            inst_sample_mode = _resolve(inst, cfg, overrides_enabled, "sample_mode", global_mode)
            if inst_sample_mode not in VALID_SAMPLE_MODES:
                inst_sample_mode = global_mode
            inst_missing_max = _resolve(inst, cfg, overrides_enabled, "max_backlog", global_missing_max)
            inst_backlog_enabled = _resolve(
                inst, cfg, overrides_enabled, "backlog_enabled",
                bool(cfg.get(f"{app}_backlog_enabled", False)))
            inst_notifications_enabled = _resolve(
                inst, cfg, overrides_enabled, "notifications_enabled",
                bool(cfg.get("notify_enabled", False)))
            # Radarr-only: missing_added_days age filter
            inst_missing_days = 0
            if app == "radarr":
                inst_missing_days = _resolve(inst, cfg, overrides_enabled, "max_missing_days",
                                             int(cfg.get("radarr_missing_added_days", 14)))
            # Backlog sample mode override — falls back to global backlog mode if not set
            inst_backlog_mode = _resolve(inst, cfg, overrides_enabled, "backlog_sample_mode", global_backlog_mode)
            if inst_backlog_mode not in VALID_BACKLOG_SAMPLE_MODES:
                inst_backlog_mode = global_backlog_mode
            logger.debug("[%s:%s] backlog_sample_mode resolved: %s%s",
                         APP, name, inst_backlog_mode,
                         " (override)" if inst_backlog_mode != global_backlog_mode else " (global)")
            try:
                inst_summary = _sweep_instance(
                    session, inst, cfg, excluded_titles,
                    inst_cooldown, inst_max, inst_sample_mode,
                    batch_size, sleep_seconds, jitter_seconds,
                    inst_missing_max, inst_backlog_enabled,
                    inst_notifications_enabled,
                    app=app,
                    missing_added_days=inst_missing_days,
                    backlog_sample_mode=inst_backlog_mode,
                )
                summary[app].append(inst_summary)
                lk = f"{app}|{state_key(name, url)}"
                db.upsert_sweep_lifetime(
                    lk,
                    runs_delta=1,
                    eligible_delta=inst_summary.get("eligible", 0) + inst_summary.get("eligible_missing", 0),
                    skipped_delta=inst_summary.get("skipped_cooldown", 0) + inst_summary.get("skipped_missing_cooldown", 0),
                    searched_delta=inst_summary.get("searched", 0) + inst_summary.get("searched_missing", 0),
                    last_run_utc=iso_z(utcnow()),
                )
            except Exception:
                # L-F2: full traceback on instance failure so the cause is never lost
                logger.exception("[%s:%s] sweep failed — retrying in 15s", APP, name)
                time.sleep(15)
                try:
                    if app == "radarr":
                        radarr_get_cutoff_unmet_movies(session, url, inst["key"])
                    else:
                        sonarr_get_cutoff_unmet_episodes(session, url, inst["key"])
                    STATUS["instance_health"][f"{app}|{name}"] = "ok"
                    logger.info("[%s:%s] Retry succeeded", APP, name)
                except Exception:
                    logger.exception("[%s:%s] Retry failed", APP, name)
                    STATUS["instance_health"][f"{app}|{name}"] = "bad"
                    summary[app].append({"name": name, "url": mask_url(url), "error": "sweep failed — see logs"})

    logger.info("Sweep complete. pruned=%d", pruned)
    return summary

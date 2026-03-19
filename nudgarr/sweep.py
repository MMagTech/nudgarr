"""
nudgarr/sweep.py

Core sweep engine — picks eligible items, applies cooldown, searches,
records results, prunes state, and returns a summary dict.

  run_sweep               -- orchestration: loops all instances, returns summary
  _sweep_radarr_instance  -- private: one Radarr instance, returns instance summary
  _sweep_sonarr_instance  -- private: one Sonarr instance, returns instance summary

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
from nudgarr.constants import VALID_SAMPLE_MODES
from nudgarr.globals import STATUS
from nudgarr.state import load_exclusions, prune_state_by_retention, state_key
from nudgarr.stats import (
    batch_record_stat_entries,
    mark_items_searched,
    pick_items_with_cooldown,
)
from nudgarr.utils import iso_z, jitter_sleep, mask_url, parse_iso, utcnow

logger = logging.getLogger(__name__)


# ── Private per-instance helpers ──────────────────────────────────────

def _sweep_radarr_instance(
    session: requests.Session,
    inst: Dict[str, Any],
    cfg: Dict[str, Any],
    excluded_titles: Set[str],
    cooldown_hours: int,
    radarr_max: int,
    radarr_sample_mode: str,
    batch_size: int,
    sleep_seconds: float,
    jitter_seconds: float,
    missing_max: int,
    missing_added_days: int,
    backlog_enabled: bool,
    notifications_enabled: bool,
) -> Dict[str, Any]:
    """Run one Radarr instance through a full sweep cycle.

    Filtering pipeline (order matters):
      1. Exclusions — skip titles on the global exclusion list
      2. Skip Queued — skip movies already in the download queue
      3. Availability — skip movies whose minimumAvailability hasn't been reached
      4. Cooldown — skip movies searched too recently (via pick_items_with_cooldown)
      5. Sample mode + cap — sort eligible items and take up to radarr_max

    Backlog nudges (missing movies) follow the same pipeline minus availability,
    with an additional age filter (missing_added_days) before cooldown.

    All resolved values (cooldown, caps, modes) come pre-resolved from run_sweep
    via _resolve() — this function never reads cfg directly for those fields.

    Returns a summary dict consumed by run_sweep and ultimately /api/status.
    """
    name, url, key = inst["name"], inst["url"], inst["key"]
    inst_url = url.rstrip("/")

    # Read per-instance sweep filters — empty sets mean no filtering applied
    sweep_filters = inst.get("sweep_filters", {})
    excluded_tags = set(int(t) for t in sweep_filters.get("excluded_tags", []))
    excluded_profiles = set(int(p) for p in sweep_filters.get("excluded_profiles", []))

    # Fetch tag map once if tag filtering is active — used for debug log labels only
    tag_map = arr_get_tag_map(session, url, key) if excluded_tags else {}

    all_movies = radarr_get_cutoff_unmet_movies(session, url, key)
    all_movies = [m for m in all_movies if (m.get("title") or "").lower() not in excluded_titles]

    # Tag filter — skip movies whose tagIds intersect the excluded set
    skipped_tag = 0
    if excluded_tags:
        filtered = []
        for m in all_movies:
            hits = excluded_tags & set(m.get("tagIds") or [])
            if hits:
                for tid in hits:
                    logger.debug("[Radarr:%s] skipped_tag: %s (tag=%s)",
                                 name, m.get("title", "?"), tag_map.get(tid, tid))
                skipped_tag += len(hits)
            else:
                filtered.append(m)
        all_movies = filtered

    # Profile filter — skip movies whose qualityProfileId is in the excluded set
    skipped_profile = 0
    if excluded_profiles:
        filtered = []
        for m in all_movies:
            pid = m.get("qualityProfileId")
            if pid in excluded_profiles:
                logger.debug("[Radarr:%s] skipped_profile: %s (profile_id=%s)",
                             name, m.get("title", "?"), pid)
                skipped_profile += 1
            else:
                filtered.append(m)
        all_movies = filtered

    queued_movie_ids = radarr_get_queued_movie_ids(session, url, key)
    all_movies = [m for m in all_movies if m["id"] not in queued_movie_ids]
    skipped_unavailable = [m for m in all_movies if not m.get("isAvailable", True)]
    all_movies = [m for m in all_movies if m.get("isAvailable", True)]
    if skipped_unavailable:
        for m in skipped_unavailable:
            threshold = m.get("minimumAvailability") or "unknown"
            release = m.get("releaseDate") or "no date"
            logger.debug("[Radarr:%s] skipped_not_available: %s (minimumAvailability=%s, releaseDate=%s)",
                         name, m.get("title", "?"), threshold, release)
    STATUS["instance_health"][f"radarr|{name}"] = "ok"
    all_ids = [m["id"] for m in all_movies]

    chosen_items, eligible, skipped = pick_items_with_cooldown(
        all_movies, "radarr", name, inst_url, "movie",
        cooldown_hours, radarr_max, radarr_sample_mode
    )
    logger.info("[Radarr:%s] cutoff_unmet_total=%d eligible=%d skipped_tag=%d skipped_profile=%d skipped_cooldown=%d will_search=%d limit=%d",
                name, len(all_ids), eligible, skipped_tag, skipped_profile, skipped, len(chosen_items), radarr_max)

    searched = 0
    for i in range(0, len(chosen_items), batch_size):
        batch_items = chosen_items[i:i + batch_size]
        batch_ids = [m["id"] for m in batch_items]
        for m in batch_items:
            logger.debug("[Radarr:%s] cutoff item: %s (id=%s quality_from=%s)",
                         name, m.get("title", "?"), m["id"], m.get("quality_from", ""))
            if not m.get("quality_from"):
                m["quality_from"] = radarr_get_movie_quality(session, url, key, m["id"])
                logger.debug("[Radarr:%s] quality_from fallback fetch: %s → %s",
                             name, m.get("title", "?"), m.get("quality_from") or "(empty)")
        radarr_search_movies(session, url, key, batch_ids, instance_name=name)
        mark_items_searched("radarr", name, inst_url, "movie", batch_items, "Cutoff")
        batch_record_stat_entries("radarr", name, inst_url, batch_items, "Upgraded", iso_z(utcnow()))
        searched += len(batch_items)
        if i + batch_size < len(chosen_items):
            jitter_sleep(sleep_seconds, jitter_seconds)

    # Optional: Missing backlog nudges
    missing_total = 0
    eligible_missing = 0
    skipped_missing = 0
    searched_missing = 0
    chosen_missing: List[Dict[str, Any]] = []

    if backlog_enabled and missing_max > 0:
        missing_records = radarr_get_missing_movies(session, url, key)
        missing_records = [m for m in missing_records if (m.get("title") or "").lower() not in excluded_titles]
        missing_records = [m for m in missing_records if m["id"] not in queued_movie_ids]
        missing_records = [m for m in missing_records if m.get("isAvailable", True)]

        # Tag filter — backlog pipeline
        if excluded_tags:
            filtered = []
            for m in missing_records:
                hits = excluded_tags & set(m.get("tagIds") or [])
                if hits:
                    for tid in hits:
                        logger.debug("[Radarr:%s] skipped_tag (backlog): %s (tag=%s)",
                                     name, m.get("title", "?"), tag_map.get(tid, tid))
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
                    logger.debug("[Radarr:%s] skipped_profile (backlog): %s (profile_id=%s)",
                                 name, m.get("title", "?"), pid)
                    skipped_profile += 1
                else:
                    filtered.append(m)
            missing_records = filtered

        missing_total = len(missing_records)

        missing_filtered: List[Dict[str, Any]] = []
        for rec in missing_records:
            added_s = rec.get("added")
            ok_old = True
            if missing_added_days > 0 and isinstance(added_s, str):
                dt = parse_iso(added_s)
                if dt is not None:
                    ok_old = dt <= (utcnow() - timedelta(days=missing_added_days))
            if ok_old:
                missing_filtered.append(rec)

        chosen_missing, eligible_missing, skipped_missing = pick_items_with_cooldown(
            missing_filtered, "radarr", name, inst_url, "missing_movie",
            cooldown_hours, missing_max, radarr_sample_mode
        )
        logger.info("[Radarr:%s] missing_total=%d eligible_missing=%d skipped_missing_cooldown=%d will_search_missing=%d limit_missing=%d older_than_days=%d",
                    name, missing_total, eligible_missing, skipped_missing, len(chosen_missing), missing_max, missing_added_days)

        for i in range(0, len(chosen_missing), batch_size):
            batch_items = chosen_missing[i:i + batch_size]
            batch_ids = [m["id"] for m in batch_items]
            for m in batch_items:
                logger.debug("[Radarr:%s] backlog item: %s (id=%s quality_from=%s)",
                             name, m.get("title", "?"), m["id"], m.get("quality_from", ""))
                if not m.get("quality_from"):
                    m["quality_from"] = radarr_get_movie_quality(session, url, key, m["id"])
                    logger.debug("[Radarr:%s] quality_from fallback fetch: %s → %s",
                                 name, m.get("title", "?"), m.get("quality_from") or "(empty)")
            radarr_search_movies(session, url, key, batch_ids, instance_name=name)
            mark_items_searched("radarr", name, inst_url, "missing_movie", batch_items, "Backlog")
            batch_record_stat_entries("radarr", name, inst_url, batch_items, "Acquired", iso_z(utcnow()))
            searched_missing += len(batch_items)
            if i + batch_size < len(chosen_missing):
                jitter_sleep(sleep_seconds, jitter_seconds)

    return {
        "name": name,
        "url": mask_url(url),
        "cutoff_unmet_total": len(all_ids),
        "eligible": eligible,
        "skipped_cooldown": skipped,
        "will_search": len(chosen_items),    # reserved — not currently read by UI
        "searched": searched,
        "limit": radarr_max,                  # reserved — not currently read by UI
        "missing_total": missing_total,
        "eligible_missing": eligible_missing,
        "skipped_missing_cooldown": skipped_missing,
        "will_search_missing": len(chosen_missing),  # reserved — not currently read by UI
        "searched_missing": searched_missing,
        "limit_missing": missing_max,              # reserved — not currently read by UI
        "missing_added_days": missing_added_days,  # reserved — not currently read by UI
        "notifications_enabled": notifications_enabled,
    }


def _sweep_sonarr_instance(
    session: requests.Session,
    inst: Dict[str, Any],
    cfg: Dict[str, Any],
    excluded_titles: Set[str],
    cooldown_hours: int,
    sonarr_max: int,
    sonarr_sample_mode: str,
    batch_size: int,
    sleep_seconds: float,
    jitter_seconds: float,
    missing_max: int,
    backlog_enabled: bool,
    notifications_enabled: bool,
) -> Dict[str, Any]:
    """Run one Sonarr instance through a full sweep cycle.

    Same pipeline as _sweep_radarr_instance but for episodes.
    Sonarr has no minimumAvailability concept — availability filter is omitted.
    Backlog nudges also have no age filter (missing_added_days is Radarr-only).

    All resolved values come pre-resolved from run_sweep via _resolve().
    """
    name, url, key = inst["name"], inst["url"], inst["key"]
    inst_url = url.rstrip("/")

    # Read per-instance sweep filters — empty sets mean no filtering applied
    sweep_filters = inst.get("sweep_filters", {})
    excluded_tags = set(int(t) for t in sweep_filters.get("excluded_tags", []))
    excluded_profiles = set(int(p) for p in sweep_filters.get("excluded_profiles", []))

    # Fetch tag map once if tag filtering is active — used for debug log labels only
    tag_map = arr_get_tag_map(session, url, key) if excluded_tags else {}

    # Fetch series meta once per instance — passed to both cutoff and missing
    # to avoid a redundant /api/v3/series call when backlog is enabled.
    _series_meta = _sonarr_get_series_meta(session, url, key)

    all_episodes = sonarr_get_cutoff_unmet_episodes(session, url, key, series_meta=_series_meta)
    all_episodes = [e for e in all_episodes if (e.get("title") or "").lower() not in excluded_titles]

    # Tag filter — skip episodes whose series tagIds intersect the excluded set
    skipped_tag = 0
    if excluded_tags:
        filtered = []
        for e in all_episodes:
            hits = excluded_tags & set(e.get("tagIds") or [])
            if hits:
                for tid in hits:
                    logger.debug("[Sonarr:%s] skipped_tag: %s (tag=%s)",
                                 name, e.get("title", "?"), tag_map.get(tid, tid))
                skipped_tag += len(hits)
            else:
                filtered.append(e)
        all_episodes = filtered

    # Profile filter — skip episodes whose series qualityProfileId is in the excluded set
    skipped_profile = 0
    if excluded_profiles:
        filtered = []
        for e in all_episodes:
            pid = e.get("qualityProfileId")
            if pid in excluded_profiles:
                logger.debug("[Sonarr:%s] skipped_profile: %s (profile_id=%s)",
                             name, e.get("title", "?"), pid)
                skipped_profile += 1
            else:
                filtered.append(e)
        all_episodes = filtered

    queued_episode_ids = sonarr_get_queued_episode_ids(session, url, key)
    all_episodes = [e for e in all_episodes if e["id"] not in queued_episode_ids]
    STATUS["instance_health"][f"sonarr|{name}"] = "ok"
    all_ids = [e["id"] for e in all_episodes]

    chosen_items, eligible, skipped = pick_items_with_cooldown(
        all_episodes, "sonarr", name, inst_url, "episode",
        cooldown_hours, sonarr_max, sonarr_sample_mode
    )
    logger.info("[Sonarr:%s] cutoff_unmet_total=%d eligible=%d skipped_tag=%d skipped_profile=%d skipped_cooldown=%d will_search=%d limit=%d",
                name, len(all_ids), eligible, skipped_tag, skipped_profile, skipped, len(chosen_items), sonarr_max)

    searched = 0
    for i in range(0, len(chosen_items), batch_size):
        batch_items = chosen_items[i:i + batch_size]
        batch_ids = [e["id"] for e in batch_items]
        for e in batch_items:
            logger.debug("[Sonarr:%s] cutoff item: %s (id=%s quality_from=%s)",
                         name, e.get("title", "?"), e["id"], e.get("quality_from", ""))
            if not e.get("quality_from"):
                e["quality_from"] = sonarr_get_episode_quality(session, url, key, e["id"])
                logger.debug("[Sonarr:%s] quality_from fallback fetch: %s → %s",
                             name, e.get("title", "?"), e.get("quality_from") or "(empty)")
        sonarr_search_episodes(session, url, key, batch_ids, instance_name=name)
        mark_items_searched("sonarr", name, inst_url, "episode", batch_items, "Cutoff")
        batch_record_stat_entries("sonarr", name, inst_url, batch_items, "Upgraded", iso_z(utcnow()))
        searched += len(batch_items)
        if i + batch_size < len(chosen_items):
            jitter_sleep(sleep_seconds, jitter_seconds)

    missing_total = 0
    eligible_missing = 0
    skipped_missing = 0
    searched_missing = 0
    chosen_missing: List[Dict[str, Any]] = []

    if backlog_enabled and missing_max > 0:
        missing_records = sonarr_get_missing_episodes(session, url, key, series_meta=_series_meta)
        missing_records = [m for m in missing_records if (m.get("title") or "").lower() not in excluded_titles]
        missing_records = [m for m in missing_records if m["id"] not in queued_episode_ids]

        # Tag filter — backlog pipeline
        if excluded_tags:
            filtered = []
            for e in missing_records:
                hits = excluded_tags & set(e.get("tagIds") or [])
                if hits:
                    for tid in hits:
                        logger.debug("[Sonarr:%s] skipped_tag (backlog): %s (tag=%s)",
                                     name, e.get("title", "?"), tag_map.get(tid, tid))
                    skipped_tag += len(hits)
                else:
                    filtered.append(e)
            missing_records = filtered

        # Profile filter — backlog pipeline
        if excluded_profiles:
            filtered = []
            for e in missing_records:
                pid = e.get("qualityProfileId")
                if pid in excluded_profiles:
                    logger.debug("[Sonarr:%s] skipped_profile (backlog): %s (profile_id=%s)",
                                 name, e.get("title", "?"), pid)
                    skipped_profile += 1
                else:
                    filtered.append(e)
            missing_records = filtered

        missing_total = len(missing_records)
        chosen_missing, eligible_missing, skipped_missing = pick_items_with_cooldown(
            missing_records, "sonarr", name, inst_url, "missing_episode",
            cooldown_hours, missing_max, sonarr_sample_mode
        )
        logger.info("[Sonarr:%s] missing_total=%d eligible_missing=%d skipped_missing_cooldown=%d will_search_missing=%d limit_missing=%d",
                    name, missing_total, eligible_missing, skipped_missing, len(chosen_missing), missing_max)

        for i in range(0, len(chosen_missing), batch_size):
            batch_items = chosen_missing[i:i + batch_size]
            batch_ids = [e["id"] for e in batch_items]
            for e in batch_items:
                logger.debug("[Sonarr:%s] backlog item: %s (id=%s quality_from=%s)",
                             name, e.get("title", "?"), e["id"], e.get("quality_from", ""))
                if not e.get("quality_from"):
                    e["quality_from"] = sonarr_get_episode_quality(session, url, key, e["id"])
                    logger.debug("[Sonarr:%s] quality_from fallback fetch: %s → %s",
                                 name, e.get("title", "?"), e.get("quality_from") or "(empty)")
            sonarr_search_episodes(session, url, key, batch_ids, instance_name=name)
            mark_items_searched("sonarr", name, inst_url, "missing_episode", batch_items, "Backlog")
            batch_record_stat_entries("sonarr", name, inst_url, batch_items, "Acquired", iso_z(utcnow()))
            searched_missing += len(batch_items)
            if i + batch_size < len(chosen_missing):
                jitter_sleep(sleep_seconds, jitter_seconds)

    return {
        "name": name,
        "url": mask_url(url),
        "cutoff_unmet_total": len(all_ids),
        "eligible": eligible,
        "skipped_cooldown": skipped,
        "will_search": len(chosen_items),    # reserved — not currently read by UI
        "searched": searched,
        "limit": sonarr_max,                  # reserved — not currently read by UI
        "missing_total": missing_total,
        "eligible_missing": eligible_missing,
        "skipped_missing_cooldown": skipped_missing,
        "will_search_missing": len(chosen_missing),  # reserved — not currently read by UI
        "searched_missing": searched_missing,
        "limit_missing": missing_max,              # reserved — not currently read by UI
        "notifications_enabled": notifications_enabled,
    }


# ── Override resolver ─────────────────────────────────────────────────

def _resolve(inst: Dict[str, Any], cfg: Dict[str, Any], overrides_enabled: bool,
             key: str, global_val: Any) -> Any:
    """Return per-instance override for key if overrides are enabled and set, else global_val."""
    if not overrides_enabled:
        return global_val
    return inst.get("overrides", {}).get(key, global_val)


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

    radarr_max = int(cfg.get("radarr_max_movies_per_run", 25))
    sonarr_max = int(cfg.get("sonarr_max_episodes_per_run", 25))
    batch_size = max(1, int(cfg.get("batch_size", 20)))
    sleep_seconds = float(cfg.get("sleep_seconds", 3))
    jitter_seconds = float(cfg.get("jitter_seconds", 2))
    retention_days = int(cfg.get("state_retention_days", 180))

    exclusions = load_exclusions()
    excluded_titles = {e["title"].lower() for e in exclusions if e.get("title")}

    pruned = prune_state_by_retention({}, retention_days)

    summary: Dict[str, Any] = {
        "pruned_entries": pruned,
        "radarr": [],
        "sonarr": [],
    }

    overrides_enabled = bool(cfg.get("per_instance_overrides_enabled", False))
    # When overrides_enabled is False, _resolve() is a passthrough — all instances
    # use the global values extracted above. When True, per-instance overrides stored
    # in inst["overrides"] take precedence over globals for any field they define.

    for inst in cfg.get("instances", {}).get("radarr", []):
        if not inst.get("enabled", True):
            logger.info("[Radarr:%s] disabled — skipping", inst["name"])
            STATUS["instance_health"][f"radarr|{inst['name']}"] = "disabled"
            continue
        name, url = inst["name"], inst["url"]
        # Resolve per-instance overrides (fall back to global if not set)
        inst_cooldown = _resolve(inst, cfg, overrides_enabled, "cooldown_hours", cooldown_hours)
        inst_radarr_max = _resolve(inst, cfg, overrides_enabled, "max_cutoff_unmet", radarr_max)
        inst_sample_mode = _resolve(inst, cfg, overrides_enabled, "sample_mode", radarr_sample_mode)
        if inst_sample_mode not in VALID_SAMPLE_MODES:
            inst_sample_mode = radarr_sample_mode
        inst_missing_max = _resolve(inst, cfg, overrides_enabled, "max_backlog", int(cfg.get("radarr_missing_max", 1)))
        inst_missing_days = _resolve(inst, cfg, overrides_enabled, "max_missing_days", int(cfg.get("radarr_missing_added_days", 14)))
        inst_backlog_enabled = _resolve(inst, cfg, overrides_enabled, "backlog_enabled", bool(cfg.get("radarr_backlog_enabled", False)))
        inst_notifications_enabled = _resolve(inst, cfg, overrides_enabled, "notifications_enabled", bool(cfg.get("notify_enabled", False)))
        try:
            inst_summary = _sweep_radarr_instance(
                session, inst, cfg, excluded_titles,
                inst_cooldown, inst_radarr_max, inst_sample_mode,
                batch_size, sleep_seconds, jitter_seconds,
                inst_missing_max, inst_missing_days, inst_backlog_enabled,
                inst_notifications_enabled,
            )
            summary["radarr"].append(inst_summary)
            lk = f"radarr|{state_key(name, url)}"
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
            logger.exception("[Radarr:%s] sweep failed — retrying in 15s", name)
            time.sleep(15)
            try:
                radarr_get_cutoff_unmet_movies(session, url, inst["key"])
                STATUS["instance_health"][f"radarr|{name}"] = "ok"
                logger.info("[Radarr:%s] Retry succeeded", name)
            except Exception:
                logger.exception("[Radarr:%s] Retry failed", name)
                STATUS["instance_health"][f"radarr|{name}"] = "bad"
                summary["radarr"].append({"name": name, "url": mask_url(url), "error": "sweep failed — see logs"})

    for inst in cfg.get("instances", {}).get("sonarr", []):
        if not inst.get("enabled", True):
            logger.info("[Sonarr:%s] disabled — skipping", inst["name"])
            STATUS["instance_health"][f"sonarr|{inst['name']}"] = "disabled"
            continue
        name, url = inst["name"], inst["url"]
        # Resolve per-instance overrides (fall back to global if not set)
        inst_cooldown = _resolve(inst, cfg, overrides_enabled, "cooldown_hours", cooldown_hours)
        inst_sonarr_max = _resolve(inst, cfg, overrides_enabled, "max_cutoff_unmet", sonarr_max)
        inst_sample_mode = _resolve(inst, cfg, overrides_enabled, "sample_mode", sonarr_sample_mode)
        if inst_sample_mode not in VALID_SAMPLE_MODES:
            inst_sample_mode = sonarr_sample_mode
        inst_missing_max = _resolve(inst, cfg, overrides_enabled, "max_backlog", int(cfg.get("sonarr_missing_max", 1)))
        inst_backlog_enabled = _resolve(inst, cfg, overrides_enabled, "backlog_enabled", bool(cfg.get("sonarr_backlog_enabled", False)))
        inst_notifications_enabled = _resolve(inst, cfg, overrides_enabled, "notifications_enabled", bool(cfg.get("notify_enabled", False)))
        try:
            inst_summary = _sweep_sonarr_instance(
                session, inst, cfg, excluded_titles,
                inst_cooldown, inst_sonarr_max, inst_sample_mode,
                batch_size, sleep_seconds, jitter_seconds,
                inst_missing_max, inst_backlog_enabled,
                inst_notifications_enabled,
            )
            summary["sonarr"].append(inst_summary)
            lk = f"sonarr|{state_key(name, url)}"
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
            logger.exception("[Sonarr:%s] sweep failed — retrying in 15s", name)
            time.sleep(15)
            try:
                sonarr_get_cutoff_unmet_episodes(session, url, inst["key"])
                STATUS["instance_health"][f"sonarr|{name}"] = "ok"
                logger.info("[Sonarr:%s] Retry succeeded", name)
            except Exception:
                logger.exception("[Sonarr:%s] Retry failed", name)
                STATUS["instance_health"][f"sonarr|{name}"] = "bad"
                summary["sonarr"].append({"name": name, "url": mask_url(url), "error": "sweep failed — see logs"})

    logger.info("Sweep complete. pruned=%d", pruned)
    return summary

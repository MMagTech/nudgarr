"""
nudgarr/sweep.py

Core sweep engine — picks eligible items, applies cooldown, searches,
records results, prunes state, and returns a summary dict.

  run_sweep               -- orchestration: loops all instances, returns summary
  _sweep_radarr_instance  -- private: one Radarr instance, returns instance summary
  _sweep_sonarr_instance  -- private: one Sonarr instance, returns instance summary

The STATUS dict (instance health dots) is updated here via globals.py.
All other persistence goes through state.py and stats.py.

Imports from within the package: globals, arr_clients, state, stats, utils.
"""

import time
from datetime import timedelta
from typing import Any, Dict, List, Set

import requests

from nudgarr.arr_clients import (
    radarr_get_cutoff_unmet_movies,
    radarr_get_missing_movies,
    radarr_search_movies,
    sonarr_get_cutoff_unmet_episodes,
    sonarr_get_missing_episodes,
    sonarr_search_episodes,
)
from nudgarr.constants import STATE_FILE
from nudgarr.globals import STATUS
from nudgarr.state import (
    ensure_state_structure,
    load_exclusions,
    load_stats,
    prune_state_by_retention,
    save_state,
    save_stats,
    state_key,
)
from nudgarr.stats import (
    mark_items_searched,
    pick_items_with_cooldown,
    record_stat_entry,
)
from nudgarr.utils import iso_z, jitter_sleep, mask_url, parse_iso, utcnow


# ── Private per-instance helpers ──────────────────────────────────────

def _sweep_radarr_instance(
    session: requests.Session,
    inst: Dict[str, Any],
    st_bucket: Dict[str, Any],
    cfg: Dict[str, Any],
    excluded_titles: Set[str],
    cooldown_hours: int,
    radarr_max: int,
    radarr_sample_mode: str,
    batch_size: int,
    sleep_seconds: float,
    jitter_seconds: float,
) -> Dict[str, Any]:
    """
    Run a full sweep for one Radarr instance. Returns an instance summary dict.
    Updates STATUS['instance_health'] directly.
    Raises on unrecoverable error (caller handles retry).
    """
    name, url, key = inst["name"], inst["url"], inst["key"]

    all_movies = radarr_get_cutoff_unmet_movies(session, url, key)
    all_movies = [m for m in all_movies if (m.get("title") or "").lower() not in excluded_titles]
    STATUS["instance_health"][f"radarr|{name}"] = "ok"
    all_ids = [m["id"] for m in all_movies]

    chosen_items, eligible, skipped = pick_items_with_cooldown(
        all_movies, st_bucket, "movie", cooldown_hours, radarr_max, radarr_sample_mode
    )
    chosen = [m["id"] for m in chosen_items]
    print(f"[Radarr:{name}] cutoff_unmet_total={len(all_ids)} eligible={eligible} "
          f"skipped_cooldown={skipped} will_search={len(chosen)} limit={radarr_max}")

    searched = 0
    for i in range(0, len(chosen_items), batch_size):
        batch_items = chosen_items[i:i + batch_size]
        batch_ids = [m["id"] for m in batch_items]
        radarr_search_movies(session, url, key, batch_ids)
        mark_items_searched(st_bucket, "movie", batch_items, "Cutoff Unmet")
        for m in batch_items:
            record_stat_entry("radarr", name, str(m["id"]), m.get("title", ""), "Upgraded", iso_z(utcnow()))
        searched += len(batch_items)
        if i + batch_size < len(chosen_items):
            jitter_sleep(sleep_seconds, jitter_seconds)

    # Optional: Missing backlog nudges
    missing_max = int(cfg.get("radarr_missing_max", 1))
    missing_added_days = int(cfg.get("radarr_missing_added_days", 14))
    radarr_backlog_enabled = bool(cfg.get("radarr_backlog_enabled", False))
    missing_total = 0
    eligible_missing = 0
    skipped_missing = 0
    searched_missing = 0
    chosen_missing: List[Dict[str, Any]] = []

    if radarr_backlog_enabled and missing_max > 0:
        missing_records = radarr_get_missing_movies(session, url, key)
        missing_records = [m for m in missing_records if (m.get("title") or "").lower() not in excluded_titles]
        missing_total = len(missing_records)

        missing_filtered: List[Dict[str, Any]] = []
        for rec in missing_records:
            added_s = rec.get("added")
            ok_old = True
            if missing_added_days > 0 and isinstance(added_s, str):
                dt = parse_iso(added_s)
                if dt is not None:
                    min_added_dt = utcnow() - timedelta(days=missing_added_days)
                    ok_old = dt <= min_added_dt
            if ok_old:
                missing_filtered.append(rec)

        chosen_missing, eligible_missing, skipped_missing = pick_items_with_cooldown(
            missing_filtered, st_bucket, "missing_movie", cooldown_hours, missing_max, radarr_sample_mode
        )
        print(f"[Radarr:{name}] missing_total={missing_total} eligible_missing={eligible_missing} "
              f"skipped_missing_cooldown={skipped_missing} will_search_missing={len(chosen_missing)} "
              f"limit_missing={missing_max} older_than_days={missing_added_days}")

        for i in range(0, len(chosen_missing), batch_size):
            batch_items = chosen_missing[i:i + batch_size]
            batch_ids = [m["id"] for m in batch_items]
            radarr_search_movies(session, url, key, batch_ids)
            mark_items_searched(st_bucket, "missing_movie", batch_items, "Backlog Nudge")
            for m in batch_items:
                record_stat_entry("radarr", name, str(m["id"]), m.get("title", ""), "Acquired", iso_z(utcnow()))
            searched_missing += len(batch_items)
            if i + batch_size < len(chosen_missing):
                jitter_sleep(sleep_seconds, jitter_seconds)

    return {
        "name": name,
        "url": mask_url(url),
        "cutoff_unmet_total": len(all_ids),
        "eligible": eligible,
        "skipped_cooldown": skipped,
        "will_search": len(chosen),
        "searched": searched,
        "limit": radarr_max,
        "missing_total": missing_total,
        "eligible_missing": eligible_missing,
        "skipped_missing_cooldown": skipped_missing,
        "will_search_missing": len(chosen_missing),
        "searched_missing": searched_missing,
        "limit_missing": missing_max,
        "missing_added_days": missing_added_days,
    }


def _sweep_sonarr_instance(
    session: requests.Session,
    inst: Dict[str, Any],
    st_bucket: Dict[str, Any],
    cfg: Dict[str, Any],
    excluded_titles: Set[str],
    cooldown_hours: int,
    sonarr_max: int,
    sonarr_sample_mode: str,
    batch_size: int,
    sleep_seconds: float,
    jitter_seconds: float,
) -> Dict[str, Any]:
    """
    Run a full sweep for one Sonarr instance. Returns an instance summary dict.
    Updates STATUS['instance_health'] directly.
    Raises on unrecoverable error (caller handles retry).
    """
    name, url, key = inst["name"], inst["url"], inst["key"]

    all_episodes = sonarr_get_cutoff_unmet_episodes(session, url, key)
    all_episodes = [e for e in all_episodes if (e.get("title") or "").lower() not in excluded_titles]
    STATUS["instance_health"][f"sonarr|{name}"] = "ok"
    all_ids = [e["id"] for e in all_episodes]

    chosen_items, eligible, skipped = pick_items_with_cooldown(
        all_episodes, st_bucket, "episode", cooldown_hours, sonarr_max, sonarr_sample_mode
    )
    chosen = [e["id"] for e in chosen_items]
    print(f"[Sonarr:{name}] cutoff_unmet_total={len(all_ids)} eligible={eligible} "
          f"skipped_cooldown={skipped} will_search={len(chosen)} limit={sonarr_max}")

    searched = 0
    for i in range(0, len(chosen_items), batch_size):
        batch_items = chosen_items[i:i + batch_size]
        batch_ids = [e["id"] for e in batch_items]
        sonarr_search_episodes(session, url, key, batch_ids)
        mark_items_searched(st_bucket, "episode", batch_items, "Cutoff Unmet")
        for e in batch_items:
            record_stat_entry("sonarr", name, str(e.get("series_id") or e["id"]), e.get("title", ""), "Upgraded", iso_z(utcnow()))
        searched += len(batch_items)
        if i + batch_size < len(chosen_items):
            jitter_sleep(sleep_seconds, jitter_seconds)

    # Optional: Missing backlog nudges
    sonarr_missing_max = int(cfg.get("sonarr_missing_max", 1))
    sonarr_backlog_enabled = bool(cfg.get("sonarr_backlog_enabled", False))
    missing_total = 0
    eligible_missing = 0
    skipped_missing = 0
    searched_missing = 0
    chosen_missing: List[Dict[str, Any]] = []

    if sonarr_backlog_enabled and sonarr_missing_max > 0:
        missing_records = sonarr_get_missing_episodes(session, url, key)
        missing_records = [m for m in missing_records if (m.get("title") or "").lower() not in excluded_titles]
        missing_total = len(missing_records)
        # No added days filter for Sonarr — if it's in Wanted, search it
        chosen_missing, eligible_missing, skipped_missing = pick_items_with_cooldown(
            missing_records, st_bucket, "missing_episode", cooldown_hours, sonarr_missing_max, sonarr_sample_mode
        )
        print(f"[Sonarr:{name}] missing_total={missing_total} eligible_missing={eligible_missing} "
              f"skipped_missing_cooldown={skipped_missing} will_search_missing={len(chosen_missing)} "
              f"limit_missing={sonarr_missing_max}")

        for i in range(0, len(chosen_missing), batch_size):
            batch_items = chosen_missing[i:i + batch_size]
            batch_ids = [e["id"] for e in batch_items]
            sonarr_search_episodes(session, url, key, batch_ids)
            mark_items_searched(st_bucket, "missing_episode", batch_items, "Backlog Nudge")
            for e in batch_items:
                record_stat_entry("sonarr", name, str(e.get("series_id") or e["id"]), e.get("title", ""), "Acquired", iso_z(utcnow()))
            searched_missing += len(batch_items)
            if i + batch_size < len(chosen_missing):
                jitter_sleep(sleep_seconds, jitter_seconds)

    return {
        "name": name,
        "url": mask_url(url),
        "cutoff_unmet_total": len(all_ids),
        "eligible": eligible,
        "skipped_cooldown": skipped,
        "will_search": len(chosen),
        "searched": searched,
        "limit": sonarr_max,
        "missing_total": missing_total,
        "eligible_missing": eligible_missing,
        "skipped_missing_cooldown": skipped_missing,
        "will_search_missing": len(chosen_missing),
        "searched_missing": searched_missing,
        "limit_missing": sonarr_missing_max,
    }


# ── Orchestrator ──────────────────────────────────────────────────────

def run_sweep(cfg: Dict[str, Any], state: Dict[str, Any], session: requests.Session) -> Dict[str, Any]:
    """
    Run one full sweep cycle across all configured Radarr and Sonarr instances.
    Returns a summary dict consumed by the scheduler and /api/status.
    """
    # ── Resolve sweep parameters ──
    cooldown_hours = int(cfg.get("cooldown_hours", 48))
    VALID_MODES = ("random", "alphabetical", "oldest_added", "newest_added")
    legacy_mode = str(cfg.get("sample_mode", "random")).lower()
    radarr_sample_mode = str(cfg.get("radarr_sample_mode", legacy_mode)).lower()
    if radarr_sample_mode not in VALID_MODES:
        radarr_sample_mode = "random"
    sonarr_sample_mode = str(cfg.get("sonarr_sample_mode", legacy_mode)).lower()
    if sonarr_sample_mode not in VALID_MODES:
        sonarr_sample_mode = "random"

    radarr_max = int(cfg.get("radarr_max_movies_per_run", 25))
    sonarr_max = int(cfg.get("sonarr_max_episodes_per_run", 25))
    batch_size = max(1, int(cfg.get("batch_size", 20)))
    sleep_seconds = float(cfg.get("sleep_seconds", 3))
    jitter_seconds = float(cfg.get("jitter_seconds", 2))
    retention_days = int(cfg.get("state_retention_days", 180))

    # ── Load exclusions ──
    exclusions = load_exclusions()
    excluded_titles = {e["title"].lower() for e in exclusions if e.get("title")}

    # ── Prune state and stats ──
    state = ensure_state_structure(state, cfg)
    pruned = prune_state_by_retention(state, retention_days)

    if retention_days > 0:
        stats = load_stats()
        cutoff = utcnow() - timedelta(days=retention_days)
        entries = stats.get("entries", [])
        before = len(entries)
        stats["entries"] = [
            e for e in entries
            if parse_iso(e.get("searched_ts", "")) and parse_iso(e.get("searched_ts", "")) > cutoff
        ]
        if len(stats["entries"]) < before:
            save_stats(stats)
            print(f"[Stats] Pruned {before - len(stats['entries'])} entries older than {retention_days} days")

    summary: Dict[str, Any] = {
        "pruned_entries": pruned,
        "radarr": [],
        "sonarr": [],
    }

    # ── Radarr instances ──
    for inst in cfg.get("instances", {}).get("radarr", []):
        if not inst.get("enabled", True):
            print(f"[Radarr:{inst['name']}] disabled — skipping")
            STATUS["instance_health"][f"radarr|{inst['name']}"] = "disabled"
            continue
        name, url = inst["name"], inst["url"]
        ik = state_key(name, url)
        st_bucket = state.setdefault("radarr", {}).setdefault(ik, {})
        try:
            inst_summary = _sweep_radarr_instance(
                session, inst, st_bucket, cfg, excluded_titles,
                cooldown_hours, radarr_max, radarr_sample_mode,
                batch_size, sleep_seconds, jitter_seconds,
            )
            summary["radarr"].append(inst_summary)
            # Lifetime sweep counters — survive Clear History
            lk = f"radarr|{state_key(name, url)}"
            lf = state.setdefault("sweep_lifetime", {}).setdefault(lk, {"runs": 0, "eligible": 0, "skipped": 0, "searched": 0})
            lf["runs"] += 1
            lf["eligible"] += inst_summary.get("eligible", 0) + inst_summary.get("eligible_missing", 0)
            lf["skipped"] += inst_summary.get("skipped_cooldown", 0) + inst_summary.get("skipped_missing_cooldown", 0)
            lf["searched"] += inst_summary.get("searched", 0) + inst_summary.get("searched_missing", 0)
            lf["last_run_utc"] = iso_z(utcnow())
        except Exception as e:
            print(f"[Radarr:{name}] ERROR: {e} — retrying in 15s")
            time.sleep(15)
            try:
                radarr_get_cutoff_unmet_movies(session, url, inst["key"])
                STATUS["instance_health"][f"radarr|{name}"] = "ok"
                print(f"[Radarr:{name}] Retry succeeded")
            except Exception as e2:
                print(f"[Radarr:{name}] Retry failed: {e2}")
                STATUS["instance_health"][f"radarr|{name}"] = "bad"
                summary["radarr"].append({"name": name, "url": mask_url(url), "error": str(e2)})

    # ── Sonarr instances ──
    for inst in cfg.get("instances", {}).get("sonarr", []):
        if not inst.get("enabled", True):
            print(f"[Sonarr:{inst['name']}] disabled — skipping")
            STATUS["instance_health"][f"sonarr|{inst['name']}"] = "disabled"
            continue
        name, url = inst["name"], inst["url"]
        ik = state_key(name, url)
        st_bucket = state.setdefault("sonarr", {}).setdefault(ik, {})
        try:
            inst_summary = _sweep_sonarr_instance(
                session, inst, st_bucket, cfg, excluded_titles,
                cooldown_hours, sonarr_max, sonarr_sample_mode,
                batch_size, sleep_seconds, jitter_seconds,
            )
            summary["sonarr"].append(inst_summary)
            # Lifetime sweep counters — survive Clear History
            lk = f"sonarr|{state_key(name, url)}"
            lf = state.setdefault("sweep_lifetime", {}).setdefault(lk, {"runs": 0, "eligible": 0, "skipped": 0, "searched": 0})
            lf["runs"] += 1
            lf["eligible"] += inst_summary.get("eligible", 0) + inst_summary.get("eligible_missing", 0)
            lf["skipped"] += inst_summary.get("skipped_cooldown", 0) + inst_summary.get("skipped_missing_cooldown", 0)
            lf["searched"] += inst_summary.get("searched", 0) + inst_summary.get("searched_missing", 0)
            lf["last_run_utc"] = iso_z(utcnow())
        except Exception as e:
            print(f"[Sonarr:{name}] ERROR: {e} — retrying in 15s")
            time.sleep(15)
            try:
                sonarr_get_cutoff_unmet_episodes(session, url, inst["key"])
                STATUS["instance_health"][f"sonarr|{name}"] = "ok"
                print(f"[Sonarr:{name}] Retry succeeded")
            except Exception as e2:
                print(f"[Sonarr:{name}] Retry failed: {e2}")
                STATUS["instance_health"][f"sonarr|{name}"] = "bad"
                summary["sonarr"].append({"name": name, "url": mask_url(url), "error": str(e2)})

    # ── Persist state ──
    save_state(state, cfg)
    print(f"State saved: {STATE_FILE} pruned={pruned}")

    return summary

#!/usr/bin/env python3
"""
Nudgarr v1.3.2 — Because RSS sometimes needs a nudge.

Core:
- Caps per run for Radarr (movies) and Sonarr (episodes)
- Persistent JSON state DB under /config with cooldown
- Loop / once modes

v1.3.2 fixes:
- Fixed Radarr cutoff/missing sweeps collecting zero IDs (wrong field: movieId → id)
- Fixed Sonarr cutoff sweep collecting zero IDs (wrong field: episodeId → id)
- Fixed _human_bytes never returning correct units (broken ternary chain)
- Fixed scheduler busy-waiting for a year in manual mode (now polls every 60s)
- Fixed saveSettings() silently dropping radarr_missing_max / radarr_missing_added_days
- Removed dead toggleRaw() JS function referencing undefined RAW variable
- Removed duplicate <hr> in Settings UI
- Fixed README version mismatch (was 1.2.2, now 1.3.2)

v1.2 UI:
- Clean minimal control panel (Instances / Settings / State / Advanced)
- Per-setting descriptions + safe defaults
- Add/edit/delete multiple Radarr/Sonarr instances
- State viewer (friendly list + raw JSON) + clear/prune
- Run Now button + status (last/next run)

State size control:
- state_retention_days (default 180): prune old entries
- state_pretty (default false): compact JSON by default
"""

import json
import os
import random
import signal
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests
from flask import Flask, jsonify, request, Response

VERSION = "1.4.2"

CONFIG_FILE = os.getenv("CONFIG_FILE", "/config/nudgarr-config.json")
STATE_FILE = os.getenv("STATE_FILE", "/config/nudgarr-state.json")
PORT = int(os.getenv("PORT", "8085"))

DEFAULT_CONFIG: Dict[str, Any] = {
    "scheduler_enabled": True,        # automatic sweeps on/off (container stays running)
    "run_interval_minutes": 360,
    "dry_run": True,

    "cooldown_hours": 48,
    "sample_mode": "random",           # random | first

    "radarr_max_movies_per_run": 25,
    "sonarr_max_episodes_per_run": 25,

    # Optional Radarr backlog missing nudges (OFF by default)
    "radarr_missing_max": 0,
    "radarr_missing_added_days": 14,

    # Optional Sonarr backlog missing nudges (OFF by default)
    "sonarr_missing_max": 0,
    "sonarr_missing_added_days": 14,

    "batch_size": 20,
    "sleep_seconds": 3,
    "jitter_seconds": 2,

    # State size controls
    "state_retention_days": 180,       # prune entries older than this (0 disables)
    "state_pretty": False,             # compact JSON by default

    "instances": {"radarr": [], "sonarr": []},
}

# -------------------------
# Utilities
# -------------------------

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

def parse_iso(s: str) -> Optional[datetime]:
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s).astimezone(timezone.utc)
    except Exception:
        return None

def ensure_dir(path: str) -> None:
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)

def load_json(path: str, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except Exception:
        return default

def save_json_atomic(path: str, data: Any, *, pretty: bool) -> None:
    ensure_dir(path)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        if pretty:
            json.dump(data, f, indent=2, sort_keys=True)
        else:
            json.dump(data, f, separators=(",", ":"), sort_keys=True)
    os.replace(tmp, path)

def mask_url(url: str) -> str:
    try:
        parts = url.split("://", 1)
        if len(parts) == 2:
            scheme, rest = parts
            host = rest.split("/", 1)[0]
            return f"{scheme}://{host}"
        return url.split("/", 1)[0]
    except Exception:
        return url

def req(session: requests.Session, method: str, url: str, key: str, json_body: Optional[dict] = None, timeout: int = 30):
    headers = {"X-Api-Key": key}
    r = session.request(method, url, headers=headers, json=json_body, timeout=timeout)
    r.raise_for_status()
    if r.text:
        try:
            return r.json()
        except Exception:
            return r.text
    return None

def validate_config(cfg: Dict[str, Any]) -> Tuple[bool, List[str]]:
    errs: List[str] = []

    if not isinstance(cfg.get("scheduler_enabled"), bool):
        errs.append("scheduler_enabled must be boolean")

    if not isinstance(cfg.get("run_interval_minutes"), int) or cfg["run_interval_minutes"] < 1:
        errs.append("run_interval_minutes must be an int >= 1")

    if cfg.get("sample_mode") not in ("random", "first"):
        errs.append("sample_mode must be 'random' or 'first'")

    for k in (
        "radarr_max_movies_per_run",
        "sonarr_max_episodes_per_run",
        "cooldown_hours",
        "sleep_seconds",
        "jitter_seconds",
        "state_retention_days",
        "radarr_missing_max",
        "radarr_missing_added_days",
    ):
        v = cfg.get(k)
        if not isinstance(v, int) or v < 0:
            errs.append(f"{k} must be an int >= 0")

    v = cfg.get("batch_size")
    if not isinstance(v, int) or v < 1:
        errs.append("batch_size must be an int >= 1")

    inst = cfg.get("instances")
    if not isinstance(inst, dict):
        errs.append("instances must be an object with keys: radarr, sonarr")
    else:
        for app in ("radarr", "sonarr"):
            items = inst.get(app)
            if not isinstance(items, list):
                errs.append(f"instances.{app} must be a list")
            else:
                for i, item in enumerate(items):
                    if not isinstance(item, dict):
                        errs.append(f"instances.{app}[{i}] must be an object")
                        continue
                    for f in ("name", "url", "key"):
                        if not item.get(f):
                            errs.append(f"instances.{app}[{i}].{f} is required")

    return (len(errs) == 0), errs

def deep_copy(obj: Any) -> Any:
    return json.loads(json.dumps(obj))

def load_or_init_config() -> Dict[str, Any]:
    cfg = load_json(CONFIG_FILE, None)
    if not isinstance(cfg, dict):
        cfg = deep_copy(DEFAULT_CONFIG)
        save_json_atomic(CONFIG_FILE, cfg, pretty=True)
        return cfg

    merged = deep_copy(DEFAULT_CONFIG)
    # merge non-instance keys
    for k, v in cfg.items():
        if k != "instances":
            merged[k] = v
    # merge instances
    merged["instances"]["radarr"] = cfg.get("instances", {}).get("radarr", merged["instances"]["radarr"])
    merged["instances"]["sonarr"] = cfg.get("instances", {}).get("sonarr", merged["instances"]["sonarr"])

    ok, errs = validate_config(merged)
    if not ok:
        print("⚠️ Config validation failed; using defaults for this run:")
        for e in errs:
            print(f"  - {e}")
        return deep_copy(DEFAULT_CONFIG)

    # Normalize & persist
    save_json_atomic(CONFIG_FILE, merged, pretty=True)
    return merged

def state_key(name: str, url: str) -> str:
    return f"{name}|{url.rstrip('/')}"

def load_state() -> Dict[str, Any]:
    st = load_json(STATE_FILE, {})
    return st if isinstance(st, dict) else {}

def ensure_state_structure(state: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    state.setdefault("radarr", {})
    state.setdefault("sonarr", {})
    for inst in cfg.get("instances", {}).get("radarr", []):
        ik = state_key(inst["name"], inst["url"])
        state["radarr"].setdefault(ik, {})
    for inst in cfg.get("instances", {}).get("sonarr", []):
        ik = state_key(inst["name"], inst["url"])
        state["sonarr"].setdefault(ik, {})
    return state

def save_state(state: Dict[str, Any], cfg: Dict[str, Any]) -> None:
    pretty = bool(cfg.get("state_pretty", False))
    save_json_atomic(STATE_FILE, state, pretty=pretty)

def is_allowed_by_cooldown(last_entry: Any, cooldown_hours: int) -> bool:
    if cooldown_hours <= 0:
        return True
    if not last_entry:
        return True
    # Support both old string format and new dict format {"ts": "...", "title": "..."}
    last_iso = last_entry.get("ts") if isinstance(last_entry, dict) else last_entry
    if not last_iso:
        return True
    dt = parse_iso(last_iso)
    if dt is None:
        return True
    return dt < (utcnow() - timedelta(hours=cooldown_hours))

def pick_items_with_cooldown(items: List[Dict[str, Any]], st_bucket: Dict[str, Any], prefix: str, cooldown_hours: int, max_per_run: int, sample_mode: str) -> Tuple[List[Dict[str, Any]], int, int]:
    eligible: List[Dict[str, Any]] = []
    skipped = 0
    for item in items:
        _id = item["id"]
        key = f"{prefix}:{_id}"
        entry = st_bucket.get(key)
        last_ts = entry.get("ts") if isinstance(entry, dict) else entry
        if is_allowed_by_cooldown(last_ts, cooldown_hours):
            eligible.append(item)
        else:
            skipped += 1
    if sample_mode == "random":
        random.shuffle(eligible)
    chosen = eligible[:max_per_run] if max_per_run > 0 else []
    return chosen, len(eligible), skipped

def pick_ids_with_cooldown(ids: List[int], st_bucket: Dict[str, Any], prefix: str, cooldown_hours: int, max_per_run: int, sample_mode: str) -> Tuple[List[int], int, int]:
    """Legacy helper for plain ID lists (kept for compatibility)."""
    items = [{"id": i, "title": ""} for i in ids]
    chosen_items, eligible, skipped = pick_items_with_cooldown(items, st_bucket, prefix, cooldown_hours, max_per_run, sample_mode)
    return [it["id"] for it in chosen_items], eligible, skipped

def mark_items_searched(st_bucket: Dict[str, Any], prefix: str, items: List[Dict[str, Any]]) -> None:
    now_s = iso_z(utcnow())
    for item in items:
        st_bucket[f"{prefix}:{item['id']}"] = {"ts": now_s, "title": item.get("title") or ""}

def mark_ids_searched(st_bucket: Dict[str, Any], prefix: str, ids: List[int]) -> None:
    """Legacy helper for plain ID lists (kept for compatibility)."""
    now_s = iso_z(utcnow())
    for _id in ids:
        key = f"{prefix}:{_id}"
        existing = st_bucket.get(key)
        title = existing.get("title", "") if isinstance(existing, dict) else ""
        st_bucket[key] = {"ts": now_s, "title": title}

def jitter_sleep(base_s: float, jitter_s: float) -> None:
    delay = base_s + (random.random() * jitter_s if jitter_s > 0 else 0)
    if delay > 0:
        time.sleep(delay)

def prune_state_by_retention(state: Dict[str, Any], retention_days: int) -> int:
    """Remove entries older than retention_days. Returns number removed."""
    if retention_days <= 0:
        return 0
    cutoff = utcnow() - timedelta(days=retention_days)
    removed = 0
    for app in ("radarr", "sonarr"):
        app_obj = state.get(app, {})
        if not isinstance(app_obj, dict):
            continue
        for inst_key, bucket in list(app_obj.items()):
            if not isinstance(bucket, dict):
                continue
            for item_key, entry in list(bucket.items()):
                # Support both old string format and new dict format
                ts = entry.get("ts") if isinstance(entry, dict) else entry
                dt = parse_iso(ts) if isinstance(ts, str) else None
                if dt is not None and dt < cutoff:
                    bucket.pop(item_key, None)
                    removed += 1
    return removed

# -------------------------
# Arr API helpers
# -------------------------

def radarr_get_cutoff_unmet_movies(session: requests.Session, url: str, key: str, page_size: int = 100, max_pages: int = 5) -> List[Dict[str, Any]]:
    """Returns list of dicts: {id:int, title:str} from Wanted->Cutoff Unmet."""
    movies: List[Dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        endpoint = f"{url.rstrip('/')}/api/v3/wanted/cutoff?page={page}&pageSize={page_size}"
        data = req(session, "GET", endpoint, key)
        if not isinstance(data, dict):
            break
        records = data.get("records") or []
        if not records:
            break
        for rec in records:
            # Radarr /wanted/cutoff returns movie objects directly; primary key is "id"
            mid = rec.get("id") or rec.get("movieId")
            if isinstance(mid, int):
                movies.append({"id": mid, "title": rec.get("title") or f"Movie {mid}"})
    return movies

def radarr_get_missing_movies(session: requests.Session, url: str, key: str, page_size: int = 100, max_pages: int = 5) -> List[Dict[str, Any]]:
    """Returns list of dicts: {id:int, title:str, added:str|None} from Wanted->Missing."""
    out: List[Dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        endpoint = f"{url.rstrip('/')}/api/v3/wanted/missing?page={page}&pageSize={page_size}"
        data = req(session, "GET", endpoint, key)
        if not isinstance(data, dict):
            break
        records = data.get("records") or []
        if not records:
            break
        for rec in records:
            # Radarr /wanted/missing returns movie objects directly; primary key is "id"
            mid = rec.get("id") or rec.get("movieId")
            added = rec.get("added") or rec.get("addedDate") or rec.get("addedUtc")
            if isinstance(mid, int):
                out.append({"id": mid, "title": rec.get("title") or f"Movie {mid}", "added": added})
    return out


def radarr_search_movies(session: requests.Session, url: str, key: str, movie_ids: List[int], dry_run: bool) -> None:
    if not movie_ids:
        return
    cmd = f"{url.rstrip('/')}/api/v3/command"
    payload = {"name": "MoviesSearch", "movieIds": movie_ids}
    if dry_run:
        print(f"[Radarr] DRY_RUN would search {len(movie_ids)} movie(s)")
    else:
        req(session, "POST", cmd, key, payload)
        print(f"[Radarr] Started MoviesSearch for {len(movie_ids)} movie(s)")

def sonarr_get_cutoff_unmet_episodes(session: requests.Session, url: str, key: str, page_size: int = 100, max_pages: int = 5) -> List[Dict[str, Any]]:
    """Returns list of dicts: {id:int, title:str} from Wanted->Cutoff Unmet."""
    episodes: List[Dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        endpoint = f"{url.rstrip('/')}/api/v3/wanted/cutoff?page={page}&pageSize={page_size}"
        data = req(session, "GET", endpoint, key)
        if not isinstance(data, dict):
            break
        records = data.get("records") or []
        if not records:
            break
        for rec in records:
            # Sonarr /wanted/cutoff returns episode objects directly; primary key is "id"
            eid = rec.get("id") or rec.get("episodeId")
            if isinstance(eid, int):
                # Build a friendly title: "Series S01E02 - Episode Title"
                series = rec.get("series", {})
                series_title = series.get("title") if isinstance(series, dict) else None
                season = rec.get("seasonNumber")
                ep_num = rec.get("episodeNumber")
                ep_title = rec.get("title")
                if series_title and season is not None and ep_num is not None:
                    title = f"{series_title} S{season:02d}E{ep_num:02d}"
                    if ep_title:
                        title += f" - {ep_title}"
                else:
                    title = ep_title or f"Episode {eid}"
                episodes.append({"id": eid, "title": title})
    return episodes

def sonarr_get_missing_episodes(session: requests.Session, url: str, key: str, page_size: int = 100, max_pages: int = 5) -> List[Dict[str, Any]]:
    """Returns list of dicts: {id:int, title:str, added:str|None} from Wanted->Missing."""
    episodes: List[Dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        endpoint = f"{url.rstrip('/')}/api/v3/wanted/missing?page={page}&pageSize={page_size}"
        data = req(session, "GET", endpoint, key)
        if not isinstance(data, dict):
            break
        records = data.get("records") or []
        if not records:
            break
        for rec in records:
            eid = rec.get("id") or rec.get("episodeId")
            if isinstance(eid, int):
                series = rec.get("series", {})
                series_title = series.get("title") if isinstance(series, dict) else None
                season = rec.get("seasonNumber")
                ep_num = rec.get("episodeNumber")
                ep_title = rec.get("title")
                added = rec.get("airDateUtc") or rec.get("added")
                if series_title and season is not None and ep_num is not None:
                    title = f"{series_title} S{season:02d}E{ep_num:02d}"
                    if ep_title:
                        title += f" - {ep_title}"
                else:
                    title = ep_title or f"Episode {eid}"
                episodes.append({"id": eid, "title": title, "added": added})
    return episodes
    if not episode_ids:
        return
    cmd = f"{url.rstrip('/')}/api/v3/command"
    payload = {"name": "EpisodeSearch", "episodeIds": episode_ids}
    if dry_run:
        print(f"[Sonarr] DRY_RUN would search {len(episode_ids)} episode(s)")
    else:
        req(session, "POST", cmd, key, payload)
        print(f"[Sonarr] Started EpisodeSearch for {len(episode_ids)} episode(s)")

# -------------------------
# Sweep
# -------------------------

def run_sweep(cfg: Dict[str, Any], state: Dict[str, Any], session: requests.Session) -> Dict[str, Any]:
    dry_run = bool(cfg.get("dry_run", True))
    cooldown_hours = int(cfg.get("cooldown_hours", 48))
    sample_mode = str(cfg.get("sample_mode", "random")).lower()

    radarr_max = int(cfg.get("radarr_max_movies_per_run", 25))
    sonarr_max = int(cfg.get("sonarr_max_episodes_per_run", 25))

    batch_size = max(1, int(cfg.get("batch_size", 20)))
    sleep_seconds = float(cfg.get("sleep_seconds", 3))
    jitter_seconds = float(cfg.get("jitter_seconds", 2))

    retention_days = int(cfg.get("state_retention_days", 180))

    state = ensure_state_structure(state, cfg)
    pruned = prune_state_by_retention(state, retention_days)

    summary = {
        "dry_run": dry_run,
        "pruned_entries": pruned,
        "radarr": [],
        "sonarr": [],
    }

    print(f"Started: {utcnow().isoformat()}  dry_run={dry_run}")

    # RADARR
    for inst in cfg.get("instances", {}).get("radarr", []):
        name, url, key = inst["name"], inst["url"], inst["key"]
        ik = state_key(name, url)
        st_bucket = state.setdefault("radarr", {}).setdefault(ik, {})
        try:
            all_movies = radarr_get_cutoff_unmet_movies(session, url, key)
            all_ids = [m["id"] for m in all_movies]
            chosen_items, eligible, skipped = pick_items_with_cooldown(all_movies, st_bucket, "movie", cooldown_hours, radarr_max, sample_mode)
            chosen = [m["id"] for m in chosen_items]
            print(f"[Radarr:{name}] cutoff_unmet_total={len(all_ids)} eligible={eligible} skipped_cooldown={skipped} will_search={len(chosen)} limit={radarr_max}")

            searched = 0
            for i in range(0, len(chosen_items), batch_size):
                batch_items = chosen_items[i:i+batch_size]
                batch_ids = [m["id"] for m in batch_items]
                radarr_search_movies(session, url, key, batch_ids, dry_run)
                if not dry_run:
                    mark_items_searched(st_bucket, "movie", batch_items)
                searched += len(batch_items)
                if i + batch_size < len(chosen_items):
                    jitter_sleep(sleep_seconds, jitter_seconds)

            # Optional: Missing backlog nudges (Radarr only)
            missing_max = int(cfg.get("radarr_missing_max", 0))
            missing_added_days = int(cfg.get("radarr_missing_added_days", 14))
            missing_total = 0
            eligible_missing = 0
            skipped_missing = 0
            searched_missing = 0
            chosen_missing: List[Dict[str, Any]] = []

            if missing_max > 0:
                missing_records = radarr_get_missing_movies(session, url, key)
                missing_total = len(missing_records)
                min_added_dt = utcnow() - timedelta(days=missing_added_days)

                missing_filtered: List[Dict[str, Any]] = []
                for rec in missing_records:
                    added_s = rec.get("added")
                    ok_old = True
                    if isinstance(added_s, str):
                        dt = parse_iso(added_s)
                        if dt is not None:
                            ok_old = dt < min_added_dt
                    if ok_old:
                        missing_filtered.append(rec)

                chosen_missing, eligible_missing, skipped_missing = pick_items_with_cooldown(
                    missing_filtered, st_bucket, "missing_movie", cooldown_hours, missing_max, sample_mode
                )
                print(f"[Radarr:{name}] missing_total={missing_total} eligible_missing={eligible_missing} skipped_missing_cooldown={skipped_missing} will_search_missing={len(chosen_missing)} limit_missing={missing_max} older_than_days={missing_added_days}")

                for i in range(0, len(chosen_missing), batch_size):
                    batch_items = chosen_missing[i:i+batch_size]
                    batch_ids = [m["id"] for m in batch_items]
                    radarr_search_movies(session, url, key, batch_ids, dry_run)
                    if not dry_run:
                        mark_items_searched(st_bucket, "missing_movie", batch_items)
                    searched_missing += len(batch_items)
                    if i + batch_size < len(chosen_missing):
                        jitter_sleep(sleep_seconds, jitter_seconds)

            summary["radarr"].append({
                "name": name, "url": mask_url(url),
                "cutoff_unmet_total": len(all_ids),
                "eligible": eligible, "skipped_cooldown": skipped,
                "will_search": len(chosen), "searched": searched,
                "limit": radarr_max,
            "missing_total": missing_total,
            "eligible_missing": eligible_missing,
            "skipped_missing_cooldown": skipped_missing,
            "will_search_missing": len(chosen_missing),
            "searched_missing": searched_missing,
            "limit_missing": missing_max,
            "missing_added_days": missing_added_days
            })
        except Exception as e:
            print(f"[Radarr:{name}] ERROR: {e}")
            summary["radarr"].append({"name": name, "url": mask_url(url), "error": str(e)})

    # SONARR
    for inst in cfg.get("instances", {}).get("sonarr", []):
        name, url, key = inst["name"], inst["url"], inst["key"]
        ik = state_key(name, url)
        st_bucket = state.setdefault("sonarr", {}).setdefault(ik, {})
        try:
            all_episodes = sonarr_get_cutoff_unmet_episodes(session, url, key)
            all_ids = [e["id"] for e in all_episodes]
            chosen_items, eligible, skipped = pick_items_with_cooldown(all_episodes, st_bucket, "episode", cooldown_hours, sonarr_max, sample_mode)
            chosen = [e["id"] for e in chosen_items]
            print(f"[Sonarr:{name}] cutoff_unmet_total={len(all_ids)} eligible={eligible} skipped_cooldown={skipped} will_search={len(chosen)} limit={sonarr_max}")

            searched = 0
            for i in range(0, len(chosen_items), batch_size):
                batch_items = chosen_items[i:i+batch_size]
                batch_ids = [e["id"] for e in batch_items]
                sonarr_search_episodes(session, url, key, batch_ids, dry_run)
                if not dry_run:
                    mark_items_searched(st_bucket, "episode", batch_items)
                searched += len(batch_items)
                if i + batch_size < len(chosen_items):
                    jitter_sleep(sleep_seconds, jitter_seconds)

            # Optional: Missing backlog nudges (Sonarr)
            sonarr_missing_max = int(cfg.get("sonarr_missing_max", 0))
            missing_total = 0
            eligible_missing = 0
            skipped_missing = 0
            searched_missing = 0
            chosen_missing: List[Dict[str, Any]] = []

            if sonarr_missing_max > 0:
                missing_records = sonarr_get_missing_episodes(session, url, key)
                missing_total = len(missing_records)
                # No added days filter for Sonarr — if it's in Wanted, search it
                chosen_missing, eligible_missing, skipped_missing = pick_items_with_cooldown(
                    missing_records, st_bucket, "missing_episode", cooldown_hours, sonarr_missing_max, sample_mode
                )
                print(f"[Sonarr:{name}] missing_total={missing_total} eligible_missing={eligible_missing} skipped_missing_cooldown={skipped_missing} will_search_missing={len(chosen_missing)} limit_missing={sonarr_missing_max}")

                for i in range(0, len(chosen_missing), batch_size):
                    batch_items = chosen_missing[i:i+batch_size]
                    batch_ids = [e["id"] for e in batch_items]
                    sonarr_search_episodes(session, url, key, batch_ids, dry_run)
                    if not dry_run:
                        mark_items_searched(st_bucket, "missing_episode", batch_items)
                    searched_missing += len(batch_items)
                    if i + batch_size < len(chosen_missing):
                        jitter_sleep(sleep_seconds, jitter_seconds)

            summary["sonarr"].append({
                "name": name, "url": mask_url(url),
                "cutoff_unmet_total": len(all_ids),
                "eligible": eligible, "skipped_cooldown": skipped,
                "will_search": len(chosen), "searched": searched,
                "limit": sonarr_max,
                "missing_total": missing_total,
                "eligible_missing": eligible_missing,
                "skipped_missing_cooldown": skipped_missing,
                "will_search_missing": len(chosen_missing),
                "searched_missing": searched_missing,
                "limit_missing": sonarr_missing_max,
            })
        except Exception as e:
            print(f"[Sonarr:{name}] ERROR: {e}")
            summary["sonarr"].append({"name": name, "url": mask_url(url), "error": str(e)})

    # Persist state (even on dry run, so pruning/structure changes persist)
    save_state(state, cfg)
    print(f"State saved: {STATE_FILE} (pretty={bool(cfg.get('state_pretty', False))}) pruned={pruned}")

    return summary

# -------------------------
# Web UI
# -------------------------

app = Flask(__name__)

# Silence default Flask request logging (werkzeug)
import logging
logging.getLogger('werkzeug').setLevel(logging.ERROR)


STATUS: Dict[str, Any] = {
    "version": VERSION,
    "last_run_utc": None,
    "next_run_utc": None,
    "last_summary": None,
    "scheduler_running": False,
    "run_in_progress": False,
    "run_requested": False,
    "last_error": None,
}

UI_HTML = r"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Nudgarr</title>
  <style>
    :root {
      --bg: #11131f;
      --surface: #181a28;
      --card: #1e2030;
      --card-hover: #22253a;
      --border: rgba(255,255,255,.10);
      --border-focus: rgba(99,120,255,.6);
      --muted: #7c8494;
      --text: #e8eaf0;
      --text-dim: #a0a8b8;
      --accent: #6378ff;
      --accent-dim: rgba(99,120,255,.15);
      --accent-border: rgba(99,120,255,.35);
      --ok: #22c55e;
      --ok-dim: rgba(34,197,94,.15);
      --warn: #f59e0b;
      --warn-dim: rgba(245,158,11,.15);
      --bad: #ef4444;
      --bad-dim: rgba(239,68,68,.15);
      --bad-border: rgba(239,68,68,.35);
    }
    *, *::before, *::after { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      font-size: 14px;
      line-height: 1.5;
    }
    .wrap { max-width: 1100px; margin: 0 auto; padding: 20px 18px; }

    /* ── Header ── */
    .header { display: flex; gap: 12px; align-items: center; justify-content: space-between; flex-wrap: wrap; margin-bottom: 20px; }
    .brand h1 { font-size: 18px; font-weight: 700; margin: 0; letter-spacing: -.3px; }
    .brand p { margin: 3px 0 0; color: var(--muted); font-size: 12px; }
    .header-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }

    /* ── Pills ── */
    .pill {
      display: inline-flex; align-items: center; gap: 7px;
      padding: 6px 12px; border: 1px solid var(--border);
      border-radius: 999px; background: var(--surface);
      font-size: 12px; color: var(--text-dim);
    }
    .dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
    .pill.clickable { cursor: pointer; transition: border-color .15s, background .15s; }
    .pill.clickable:hover { border-color: var(--border-focus); background: var(--card); }

    /* ── Buttons ── */
    .btn {
      border: 1px solid var(--border); background: var(--surface);
      color: var(--text); padding: 8px 14px; border-radius: 10px;
      cursor: pointer; font-size: 13px; font-weight: 500;
      transition: background .15s, border-color .15s;
      white-space: nowrap;
    }
    .btn:hover { background: var(--card-hover); border-color: rgba(255,255,255,.15); }
    .btn.primary {
      background: rgba(99,120,255,.2); border-color: var(--accent-border);
      color: #a8b4ff;
    }
    .btn.primary:hover { background: rgba(99,120,255,.32); border-color: var(--accent); color: #c0caff; }
    .btn.danger { background: var(--bad-dim); border-color: var(--bad-border); color: #fca5a5; }
    .btn.danger:hover { background: rgba(239,68,68,.25); }
    .btn.sm { padding: 6px 11px; font-size: 12px; border-radius: 8px; }
    .btn.run-now {
      background: rgba(99,120,255,.25); border-color: var(--accent);
      color: #c0caff; font-weight: 600; padding: 8px 18px;
    }
    .btn.run-now:hover { background: rgba(99,120,255,.4); color: #fff; }

    /* ── Modal ── */
    .modal-backdrop {
      position: fixed; inset: 0; background: rgba(0,0,0,.6);
      display: flex; align-items: center; justify-content: center;
      z-index: 1000; backdrop-filter: blur(4px);
    }
    .modal {
      background: var(--card); border: 1px solid var(--border);
      border-radius: 18px; padding: 24px; width: 100%; max-width: 440px;
      box-shadow: 0 24px 64px rgba(0,0,0,.5);
    }
    .modal h2 { font-size: 16px; font-weight: 700; margin: 0 0 18px; }
    .modal .field { margin-bottom: 14px; }
    .modal .row { margin-top: 20px; justify-content: flex-end; }
    .key-wrap { position: relative; }
    .key-wrap input { padding-right: 70px; }
    .key-toggle {
      position: absolute; right: 10px; top: 50%; transform: translateY(-50%);
      font-size: 11px; color: var(--muted); cursor: pointer;
      background: none; border: none; padding: 2px 6px;
    }
    .key-toggle:hover { color: var(--text); }

    /* ── Tabs ── */
    .tabs { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 16px; }
    .tab {
      padding: 7px 14px; border: 1px solid var(--border);
      border-radius: 999px; cursor: pointer; font-size: 13px;
      color: var(--muted); background: var(--surface);
      transition: all .15s;
    }
    .tab:hover { color: var(--text); border-color: rgba(255,255,255,.15); }
    .tab.active { color: var(--text); background: var(--card); border-color: rgba(255,255,255,.18); }
    .section { display: none; }
    .section.active { display: block; }

    /* ── Cards & Grid ── */
    .grid { display: grid; gap: 12px; }
    .cols2 { grid-template-columns: 1fr 1fr; }
    @media(max-width: 720px) { .cols2 { grid-template-columns: 1fr; } }
    .card {
      border: 1px solid var(--border); background: var(--card);
      border-radius: 16px; padding: 18px;
    }
    .card-title { font-size: 14px; font-weight: 600; margin: 0 0 12px; color: var(--text); }
    .full { grid-column: 1 / -1; }

    /* ── Form elements ── */
    .field { display: flex; flex-direction: column; gap: 5px; }
    label { font-size: 12px; color: var(--muted); font-weight: 500; }
    input, select {
      padding: 9px 11px; border-radius: 9px;
      border: 1px solid var(--border);
      background: var(--surface); color: var(--text);
      outline: none; font-size: 13px; width: 100%;
      transition: border-color .15s;
    }
    input:focus, select:focus { border-color: var(--border-focus); }
    input:disabled { opacity: .5; cursor: not-allowed; }
    .help { font-size: 12px; color: var(--muted); line-height: 1.4; }
    .hr { height: 1px; background: var(--border); margin: 16px 0; }
    .row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
    .msg { font-size: 12px; color: var(--muted); }
    .msg.ok { color: var(--ok); }
    .msg.err { color: var(--bad); }

    /* ── Toggle switch ── */
    .toggle-wrap { display: flex; align-items: center; gap: 10px; }
    .toggle {
      position: relative; width: 44px; height: 24px;
      flex-shrink: 0; cursor: pointer;
    }
    .toggle input { opacity: 0; width: 0; height: 0; position: absolute; }
    .toggle-track {
      position: absolute; inset: 0; border-radius: 999px;
      background: var(--surface); border: 1px solid var(--border);
      transition: background .2s, border-color .2s;
    }
    .toggle input:checked ~ .toggle-track { background: var(--accent); border-color: var(--accent); }
    .toggle input.warn:checked ~ .toggle-track { background: var(--warn); border-color: var(--warn); }
    .toggle-thumb {
      position: absolute; top: 3px; left: 3px;
      width: 16px; height: 16px; border-radius: 50%;
      background: var(--muted); transition: transform .2s, background .2s;
    }
    .toggle input:checked ~ .toggle-thumb { transform: translateX(20px); background: #fff; }

    /* ── Instance cards ── */
    .inst-card {
      border: 1px solid var(--border); border-radius: 12px;
      padding: 13px 14px; margin-top: 8px; background: var(--surface);
      display: flex; align-items: center; gap: 10px;
    }
    .inst-card .inst-info { flex: 1; min-width: 0; }
    .inst-card .inst-name { font-weight: 600; font-size: 13px; }
    .inst-card .inst-meta { font-size: 12px; color: var(--muted); margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .inst-card .inst-actions { display: flex; gap: 6px; flex-shrink: 0; }
    .status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--border); flex-shrink: 0; transition: background .3s; }
    .status-dot.ok { background: var(--ok); }
    .status-dot.bad { background: var(--bad); }
    .status-dot.checking { background: var(--warn); animation: pulse 1s infinite; }
    @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }

    /* ── Test result cards ── */
    .test-results { display: flex; flex-direction: column; gap: 8px; margin-top: 12px; }
    .test-card {
      display: flex; align-items: center; gap: 12px;
      padding: 11px 14px; border-radius: 12px; border: 1px solid var(--border);
      background: var(--surface);
    }
    .test-card.ok { border-color: rgba(34,197,94,.25); background: var(--ok-dim); }
    .test-card.bad { border-color: var(--bad-border); background: var(--bad-dim); }
    .test-card .tc-name { font-weight: 600; font-size: 13px; }
    .test-card .tc-detail { font-size: 12px; color: var(--muted); margin-top: 1px; }
    .test-card.ok .tc-detail { color: rgba(34,197,94,.8); }
    .test-card.bad .tc-detail { color: #fca5a5; }
    .test-icon { font-size: 16px; flex-shrink: 0; }

    /* ── Settings section headers ── */
    .section-label {
      font-size: 11px; font-weight: 600; letter-spacing: .06em;
      text-transform: uppercase; color: var(--muted);
      margin: 0 0 10px;
    }

    /* ── History table ── */
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { border-bottom: 1px solid var(--border); padding: 10px 8px; text-align: left; }
    th { color: var(--muted); font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: .04em; }
    td { color: var(--text); }
    tr:last-child td { border-bottom: none; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }

    /* ── KPI pills row ── */
    .kpis { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 14px; }

    /* ── Danger zone ── */
    .danger-section { border: 1px solid var(--bad-border); border-radius: 12px; padding: 14px; background: var(--bad-dim); }

    /* ── Diag box ── */
    .diag-box {
      background: var(--surface); border: 1px solid var(--border);
      border-radius: 10px; padding: 13px; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 12px; color: var(--text-dim); white-space: pre-wrap;
      line-height: 1.6; margin-top: 10px;
    }
  </style>
</head>
<body>
<div class="wrap">

  <!-- Header -->
  <div class="header">
    <div class="brand">
      <h1>Nudgarr <span style="font-weight:400; font-size:13px; color:var(--muted)">v<span id="ver"></span></span></h1>
      <p>Sweeping your library, one nudge at a time.</p>
    </div>
    <div class="header-right">
      <div class="pill clickable" id="pill-dryrun" onclick="toggleDryRun()" title="Click to toggle DRY RUN"><span class="dot" id="dot-dryrun"></span><span id="txt-dryrun">Loading…</span></div>
      <div class="pill"><span>Last: <span id="lastRun">—</span></span></div>
      <div class="pill"><span>Next: <span id="nextRun">—</span></span></div>
      <button class="btn run-now" onclick="runNow()">Run Now</button>
    </div>
  </div>

  <!-- Tabs -->
  <div class="tabs">
    <div class="tab active" data-tab="instances" onclick="showTab('instances')">Instances</div>
    <div class="tab" data-tab="settings" onclick="showTab('settings')">Settings</div>
    <div class="tab" data-tab="history" onclick="showTab('history')">History</div>
    <div class="tab" data-tab="advanced" onclick="showTab('advanced')">Advanced</div>
  </div>

  <!-- ══════════════════════════════ INSTANCES ══════════════════════════════ -->
  <div class="section active" id="tab-instances">
    <div class="grid cols2">
      <div class="card">
        <div class="row" style="margin-bottom:12px">
          <span class="card-title" style="margin:0">Radarr Instances</span>
          <button class="btn sm" style="margin-left:auto" onclick="addInstance('radarr')">+ Add</button>
        </div>
        <p class="help" style="margin:0 0 8px">Add one or more Radarr instances.</p>
        <div id="radarrList"></div>
      </div>

      <div class="card">
        <div class="row" style="margin-bottom:12px">
          <span class="card-title" style="margin:0">Sonarr Instances</span>
          <button class="btn sm" style="margin-left:auto" onclick="addInstance('sonarr')">+ Add</button>
        </div>
        <p class="help" style="margin:0 0 8px">Add one or more Sonarr instances.</p>
        <div id="sonarrList"></div>
      </div>

      <div class="card full">
        <div class="row">
          <button class="btn primary" onclick="saveAll()">Save Changes</button>
          <button class="btn" onclick="testConnections()">Test Connections</button>
          <span class="msg" id="saveMsg"></span>
        </div>
        <div id="testResults" style="display:none">
          <div class="hr"></div>
          <div class="test-results" id="testResultsInner"></div>
        </div>
      </div>
    </div>
  </div>

  <!-- ══════════════════════════════ SETTINGS ══════════════════════════════ -->
  <div class="section" id="tab-settings">
    <div class="grid" style="max-width:600px">

      <div class="card">
        <p class="section-label">Scheduler</p>
        <div class="row" style="gap:16px; flex-wrap:nowrap; align-items:flex-start">
          <div class="field" style="flex:1">
            <label>Automatic Sweeps</label>
            <div class="toggle-wrap">
              <label class="toggle">
                <input type="checkbox" id="scheduler_enabled" onchange="syncSchedulerUi()"/>
                <span class="toggle-track"></span>
                <span class="toggle-thumb"></span>
              </label>
              <span class="help" id="scheduler_label">Enabled</span>
            </div>
            <div class="help">When disabled, only sweeps when you click <b>Run Now</b>.</div>
          </div>
          <div class="field" style="max-width:160px">
            <label>Run Interval (minutes)</label>
            <input id="run_interval_minutes" type="number" min="1"/>
            <div class="help">How often Nudgarr runs a sweep.</div>
          </div>
        </div>
      </div>

      <div class="card">
        <p class="section-label">Search Behaviour</p>
        <div class="grid cols2" style="gap:12px">
          <div class="field">
            <label>Cooldown Hours</label>
            <input id="cooldown_hours" type="number" min="0"/>
            <div class="help">Minimum hours before the same movie or episode can be searched again. 0 disables.</div>
          </div>
          <div class="field">
            <label>Sample Mode</label>
            <select id="sample_mode">
              <option value="random">Random</option>
              <option value="first">First</option>
            </select>
            <div class="help">Random picks different items each run for even library coverage. First always prioritises the same items until they're upgraded.</div>
          </div>
        </div>
        <div style="margin-top:16px" class="grid cols2" style="gap:12px">
          <div class="field">
            <label>Max Movies Per Run</label>
            <input id="radarr_max_movies_per_run" type="number" min="0"/>
            <div class="help">Maximum Cutoff Unmet movie searches per instance run. 0 disables.</div>
          </div>
          <div class="field">
            <label>Max Episodes Per Run</label>
            <input id="sonarr_max_episodes_per_run" type="number" min="0"/>
            <div class="help">Maximum Cutoff Unmet episode searches per instance run. 0 disables.</div>
          </div>
        </div>
      </div>

      <div class="card">
        <p class="section-label">Throttling</p>
        <div class="grid cols2" style="gap:12px">
          <div class="field">
            <label>Batch Size</label>
            <input id="batch_size" type="number" min="1"/>
            <div class="help">Number of items sent per search command. Smaller values are easier on your indexers.</div>
          </div>
          <div class="field">
            <label>Sleep Seconds</label>
            <input id="sleep_seconds" type="number" min="0" step="0.1"/>
            <div class="help">Pause between batches in seconds. Gives your indexers time to breathe.</div>
          </div>
          <div class="field">
            <label>Jitter Seconds</label>
            <input id="jitter_seconds" type="number" min="0" step="0.1"/>
            <div class="help">Random extra pause on top of Sleep Seconds to help avoid indexer rate limiting.</div>
          </div>
        </div>
      </div>

      <div class="card" style="border-color: rgba(245,158,11,.25); background: rgba(245,158,11,.06);">
        <p class="help" style="margin:0; line-height:1.6; color: rgba(245,158,11,.9)">Nudgarr instructs your Radarr and Sonarr instances to search using your configured indexers. Be respectful of your indexers' limits and know their caps — searching too aggressively can get you banned from your indexer.</p>
      </div>

      <div class="row">
        <button class="btn primary" onclick="saveSettings()">Save Settings</button>
        <span class="msg" id="setMsg"></span>
      </div>
    </div>
  </div>

  <!-- ══════════════════════════════ HISTORY ══════════════════════════════ -->
  <div class="section" id="tab-history">
    <div class="card">
      <div class="kpis" id="kpis"></div>
      <div class="row" style="margin-bottom:14px">
        <button class="btn sm" onclick="refreshHistory()">Refresh</button>
        <button class="btn sm" onclick="pruneState()">Prune Expired</button>
        <button class="btn sm danger" onclick="clearState()">Clear History</button>
        <div style="margin-left:auto; display:flex; gap:8px; align-items:center;">
          <div class="field" style="min-width:200px">
            <select id="historyInstance" onchange="PAGE=0; refreshHistory()"></select>
          </div>
          <div class="field" style="min-width:100px">
            <select id="historyLimit" onchange="PAGE=0; refreshHistory()">
              <option>100</option><option selected>250</option><option>500</option><option>1000</option>
            </select>
          </div>
        </div>
      </div>
      <div id="historyTableWrap"></div>
      <div class="row" style="margin-top:12px" id="historyPagination">
        <button class="btn sm" onclick="prevPage()">Prev</button>
        <button class="btn sm" onclick="nextPage()">Next</button>
        <span class="msg" id="pageInfo"></span>
      </div>
    </div>
  </div>

  <!-- ══════════════════════════════ ADVANCED ══════════════════════════════ -->
  <div class="section" id="tab-advanced">
    <div class="grid">
      <div class="grid cols2">
        <div class="card">
          <p class="section-label">Backlog Nudges</p>
          <div class="help" style="margin-bottom:12px">Nudges movies and episodes identified as missing. These searches are on top of your Max Per Run caps. Off by default.</div>
          <p class="help" style="margin:0 0 8px; font-weight:600; color:var(--text-dim)">Radarr</p>
          <div class="grid cols2" style="gap:12px">
            <div class="field">
              <label>Radarr Missing Max</label>
              <input id="radarr_missing_max" type="number" min="0"/>
              <div class="help">Maximum missing movie searches per instance run. 0 disables.</div>
            </div>
            <div class="field">
              <label>Radarr Missing Added Days</label>
              <input id="radarr_missing_added_days" type="number" min="0"/>
              <div class="help">Only nudge movies that have been missing for more than this many days.</div>
            </div>
          </div>
          <div style="margin-top:14px">
          <p class="help" style="margin:0 0 8px; font-weight:600; color:var(--text-dim)">Sonarr</p>
          <div class="grid cols2" style="gap:12px">
            <div class="field">
              <label>Sonarr Missing Max</label>
              <input id="sonarr_missing_max" type="number" min="0"/>
              <div class="help">Nudges monitored episodes in your Wanted list. 0 disables.</div>
            </div>
          </div>
          </div>
        </div>

        <div class="card">
          <p class="section-label">History Size</p>
          <div class="field">
            <label>Retention Days</label>
            <input id="state_retention_days" type="number" min="0"/>
            <div class="help">Delete history entries older than this. 0 disables.</div>
          </div>
          <div class="hr"></div>
          <p class="section-label">Files</p>
          <div class="row">
            <button class="btn sm" onclick="downloadFile('config')">Download Config</button>
            <button class="btn sm" onclick="downloadFile('state')">Download History</button>
          </div>
        </div>
      </div>

      <div class="row" style="margin-top:4px">
        <button class="btn primary sm" onclick="saveAdvanced()">Save</button>
        <span class="msg" id="advMsg"></span>
      </div>

      <div class="grid cols2">
        <div class="card danger-section">
          <p class="section-label" style="color:#fca5a5">Danger Zone</p>
          <p class="help" style="margin:0 0 12px; color:#fca5a5">These actions are irreversible.</p>
          <div class="row">
            <button class="btn sm danger" onclick="resetConfig()">Reset Config to Defaults</button>
            <button class="btn sm danger" onclick="clearState()">Clear History</button>
          </div>
        </div>

        <div class="card">
          <p class="section-label">Diagnostics</p>
          <p class="help" style="margin:0 0 12px">Copy diagnostic info to share when opening a GitHub issue.</p>
          <button class="btn sm" onclick="copyDiagnostic()">Copy Diagnostic Info</button>
          <span class="msg" id="diagMsg" style="margin-left:8px"></span>
          <div id="diagBox" class="diag-box" style="display:none"></div>
        </div>
      </div>
    </div>
  </div>

</div>

  <!-- ══ Instance Modal ══ -->
  <div class="modal-backdrop" id="instModal" style="display:none" onclick="closeModal(event)">
    <div class="modal" onclick="event.stopPropagation()">
      <h2 id="modalTitle">Add Instance</h2>
      <div class="field">
        <label>Name</label>
        <input id="modalName" type="text" placeholder="e.g. radarr-4k"/>
      </div>
      <div class="field">
        <label>URL</label>
        <input id="modalUrl" type="text" placeholder="http://192.168.1.10:7878"/>
      </div>
      <div class="field">
        <label>API Key</label>
        <div class="key-wrap">
          <input id="modalKey" type="password" placeholder="Your API key"/>
          <button class="key-toggle" onclick="toggleKeyVis()" id="keyToggleBtn">Show</button>
        </div>
      </div>
      <div class="row">
        <button class="btn sm" onclick="closeModalDirect()">Cancel</button>
        <button class="btn sm primary" onclick="saveModal()">Save</button>
      </div>
    </div>
  </div>

<script>
let CFG = null;
let PAGE = 0;
// Track all configured instances: [{key, name, app}]
let ALL_INSTANCES = [];

function showTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  if (name === 'history') refreshHistory();
  if (name === 'advanced') fillAdvanced();
}

function el(id) { return document.getElementById(id); }

function escapeHtml(s) {
  return (s || '').toString()
    .replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;')
    .replaceAll('"','&quot;').replaceAll("'",'&#39;');
}

function fmtTime(s) {
  if (!s) return '—';
  try { return new Date(s).toLocaleString(); } catch(e) { return s; }
}

async function api(path, opts) {
  const r = await fetch(path, opts || {});
  const ct = r.headers.get('content-type') || '';
  const data = ct.includes('application/json') ? await r.json() : await r.text();
  if (!r.ok) throw new Error(typeof data === 'string' ? data : JSON.stringify(data));
  return data;
}

function updateDryRunPill(dry) {
  el('dot-dryrun').style.background = dry ? 'var(--warn)' : 'var(--ok)';
  el('txt-dryrun').textContent = dry ? 'DRY RUN' : 'LIVE';
}

async function loadAll() {
  CFG = await api('/api/config');
  const st = await api('/api/status');
  el('ver').textContent = st.version;
  el('lastRun').textContent = fmtTime(st.last_run_utc);
  el('nextRun').textContent = (CFG && CFG.scheduler_enabled) ? fmtTime(st.next_run_utc) : 'Manual';
  updateDryRunPill(CFG.dry_run);

  // Build instance list
  ALL_INSTANCES = [];
  (CFG.instances?.radarr || []).forEach(i => ALL_INSTANCES.push({key: i.name+'|'+i.url.replace(/\/$/,''), name: i.name, app:'radarr'}));
  (CFG.instances?.sonarr || []).forEach(i => ALL_INSTANCES.push({key: i.name+'|'+i.url.replace(/\/$/,''), name: i.name, app:'sonarr'}));

  renderInstances('radarr');
  renderInstances('sonarr');
  fillSettings();
}

// ── Instances tab ──
function renderInstances(kind) {
  const box = el(kind + 'List');
  const list = CFG?.instances?.[kind] || [];
  if (!list.length) {
    box.innerHTML = '<p class="help" style="margin:8px 0 0">No instances yet. Click <b>+ Add</b>.</p>';
    return;
  }
  box.innerHTML = list.map((it, idx) => `
    <div class="inst-card" id="instcard-${kind}-${idx}">
      <span class="status-dot" id="sdot-${kind}-${idx}"></span>
      <div class="inst-info">
        <div class="inst-name">${escapeHtml(it.name || '(unnamed)')}</div>
        <div class="inst-meta">${escapeHtml(it.url || '')} &nbsp;·&nbsp; Key: ••••••••</div>
      </div>
      <div class="inst-actions">
        <button class="btn sm" onclick="editInstance('${kind}', ${idx})">Edit</button>
        <button class="btn sm danger" onclick="deleteInstance('${kind}', ${idx})">Delete</button>
      </div>
    </div>
  `).join('');
}

let MODAL_KIND = '';
let MODAL_IDX = -1;

function openModal(kind, idx) {
  MODAL_KIND = kind;
  MODAL_IDX = idx;
  const isEdit = idx >= 0;
  el('modalTitle').textContent = (isEdit ? 'Edit ' : 'Add ') + (kind === 'radarr' ? 'Radarr' : 'Sonarr') + ' Instance';
  const it = isEdit ? CFG.instances[kind][idx] : {name:'', url:'http://', key:''};
  el('modalName').value = it.name || '';
  el('modalUrl').value = it.url || '';
  el('modalKey').value = it.key || '';
  el('modalKey').type = 'password';
  el('keyToggleBtn').textContent = 'Show';
  el('instModal').style.display = 'flex';
  setTimeout(() => el('modalName').focus(), 50);
}

function closeModal(e) {
  if (e.target === el('instModal')) closeModalDirect();
}

function closeModalDirect() {
  el('instModal').style.display = 'none';
}

function toggleKeyVis() {
  const inp = el('modalKey');
  const btn = el('keyToggleBtn');
  if (inp.type === 'password') { inp.type = 'text'; btn.textContent = 'Hide'; }
  else { inp.type = 'password'; btn.textContent = 'Show'; }
}

function saveModal() {
  const name = el('modalName').value.trim();
  const url = el('modalUrl').value.trim();
  const key = el('modalKey').value.trim();
  if (!name || !url || !key) { alert('All fields are required.'); return; }
  CFG.instances = CFG.instances || {radarr:[], sonarr:[]};
  if (MODAL_IDX >= 0) {
    CFG.instances[MODAL_KIND][MODAL_IDX] = {name, url, key};
  } else {
    CFG.instances[MODAL_KIND].push({name, url, key});
  }
  closeModalDirect();
  renderInstances(MODAL_KIND);
  el('saveMsg').textContent = MODAL_IDX >= 0 ? 'Edited — click Save Changes.' : 'Added — click Save Changes.';
  el('saveMsg').className = 'msg';
}

function addInstance(kind) {
  openModal(kind, -1);
}

function editInstance(kind, idx) {
  openModal(kind, idx);
}

function deleteInstance(kind, idx) {
  if (!confirm('Delete this instance?')) return;
  CFG.instances[kind].splice(idx, 1);
  renderInstances(kind);
  el('saveMsg').textContent = 'Deleted — click Save Changes.';
  el('saveMsg').className = 'msg';
}

async function saveAll() {
  try {
    await api('/api/config', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(CFG)});
    el('saveMsg').textContent = 'Saved.'; el('saveMsg').className = 'msg ok';
    await loadAll();
  } catch(e) {
    el('saveMsg').textContent = 'Save failed: ' + e.message; el('saveMsg').className = 'msg err';
  }
}

async function testConnections() {
  el('testResults').style.display = 'block';
  el('testResults').style.opacity = '1';
  el('testResultsInner').innerHTML = '<p class="help">Testing…</p>';

  document.querySelectorAll('.status-dot').forEach(d => { d.className = 'status-dot checking'; });

  try {
    const out = await api('/api/test', {method:'POST'});
    const allResults = [...(out.results.radarr||[]), ...(out.results.sonarr||[])];

    ['radarr','sonarr'].forEach(kind => {
      (out.results[kind]||[]).forEach((r, idx) => {
        const dot = el(`sdot-${kind}-${idx}`);
        if (dot) dot.className = 'status-dot ' + (r.ok ? 'ok' : 'bad');
      });
    });

    el('testResultsInner').innerHTML = allResults.map(r => `
      <div class="test-card ${r.ok ? 'ok' : 'bad'}">
        <span class="test-icon">${r.ok ? '✓' : '✗'}</span>
        <div>
          <div class="tc-name">${escapeHtml(r.name)}</div>
          <div class="tc-detail">${r.ok ? 'Connected · v' + escapeHtml(r.version||'?') + ' · ' + escapeHtml(r.url) : escapeHtml(r.error||'Connection failed')}</div>
        </div>
      </div>
    `).join('');

    // Fade out result cards after 3 seconds, dots persist
    setTimeout(() => {
      el('testResults').style.transition = 'opacity 0.8s ease';
      el('testResults').style.opacity = '0';
      setTimeout(() => {
        el('testResults').style.display = 'none';
        el('testResults').style.transition = '';
        el('testResults').style.opacity = '1';
      }, 800);
    }, 3000);

  } catch(e) {
    el('testResultsInner').innerHTML = `<p class="help" style="color:var(--bad)">Test failed: ${escapeHtml(e.message)}</p>`;
    document.querySelectorAll('.status-dot').forEach(d => { d.className = 'status-dot'; });
  }
}

// ── Settings tab ──
function syncSchedulerUi() {
  const enabled = el('scheduler_enabled').checked;
  el('scheduler_label').textContent = enabled ? 'Enabled' : 'Manual only';
  el('run_interval_minutes').disabled = !enabled;
}

function fillSettings() {
  el('scheduler_enabled').checked = !!CFG.scheduler_enabled;
  el('run_interval_minutes').value = CFG.run_interval_minutes;
  el('cooldown_hours').value = CFG.cooldown_hours;
  el('sample_mode').value = CFG.sample_mode;
  el('radarr_max_movies_per_run').value = CFG.radarr_max_movies_per_run;
  el('sonarr_max_episodes_per_run').value = CFG.sonarr_max_episodes_per_run;
  el('batch_size').value = CFG.batch_size;
  el('sleep_seconds').value = CFG.sleep_seconds;
  el('jitter_seconds').value = CFG.jitter_seconds;
  syncSchedulerUi();
}

async function toggleDryRun() {
  const currentlyDry = CFG?.dry_run;
  if (currentlyDry) {
    // Switching to LIVE — confirm first
    if (!confirm('Switch to Live mode? Nudgarr will start triggering real searches.')) return;
  }
  try {
    const out = await api('/api/toggle-dry-run', {method:'POST'});
    CFG.dry_run = out.dry_run;
    updateDryRunPill(out.dry_run);
  } catch(e) {
    alert('Failed to toggle DRY RUN: ' + e.message);
  }
}

async function saveSettings() {
  try {
    CFG.scheduler_enabled = el('scheduler_enabled').checked;
    CFG.run_interval_minutes = parseInt(el('run_interval_minutes').value || '360', 10);
    CFG.cooldown_hours = parseInt(el('cooldown_hours').value || '48', 10);
    CFG.sample_mode = el('sample_mode').value;
    CFG.radarr_max_movies_per_run = parseInt(el('radarr_max_movies_per_run').value || '25', 10);
    CFG.sonarr_max_episodes_per_run = parseInt(el('sonarr_max_episodes_per_run').value || '25', 10);
    CFG.batch_size = parseInt(el('batch_size').value || '20', 10);
    CFG.sleep_seconds = parseFloat(el('sleep_seconds').value || '3');
    CFG.jitter_seconds = parseFloat(el('jitter_seconds').value || '2');
    await api('/api/config', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(CFG)});
    el('setMsg').textContent = 'Saved.'; el('setMsg').className = 'msg ok';
    await loadAll();
  } catch(e) {
    el('setMsg').textContent = 'Save failed: ' + e.message; el('setMsg').className = 'msg err';
  }
}

// ── History tab ──
async function refreshHistory() {
  try {
    const sum = await api('/api/state/summary');

    // KPI pills — per instance counts
    const instPills = ALL_INSTANCES.map(inst => {
      const appSt = sum.per_instance || {};
      const count = (appSt[inst.app] && appSt[inst.app][inst.key]) || 0;
      return `<div class="pill"><span>${escapeHtml(inst.name)}: ${count}</span></div>`;
    }).join('');
    el('kpis').innerHTML = instPills +
      `<div class="pill"><span>History File: ${sum.file_size_human}</span></div>` +
      `<div class="pill"><span>Retention: ${sum.retention_days} days</span></div>`;

    // Build instance dropdown from ALL_INSTANCES (has correct app info)
    // Store index into ALL_INSTANCES as the option value to avoid any key parsing issues
    const sel = el('historyInstance');
    const prevIdx = sel.value;
    sel.innerHTML = ALL_INSTANCES.map((inst, idx) =>
      `<option value="${idx}">${escapeHtml(inst.name)}</option>`
    ).join('');
    if (prevIdx && parseInt(prevIdx) < ALL_INSTANCES.length) sel.value = prevIdx;

    const selIdx = parseInt(sel.value || '0');
    const selected = ALL_INSTANCES[selIdx];
    const instKey = selected ? selected.key : '';
    const appName = selected ? selected.app : 'radarr';

    const limit = parseInt(el('historyLimit').value || '250', 10);
    const items = await api(`/api/state/items?app=${encodeURIComponent(appName)}&instance=${encodeURIComponent(instKey)}&offset=${PAGE*limit}&limit=${limit}`);

    el('pageInfo').textContent = `Page ${PAGE+1} · ${items.items.length} of ${items.total}`;
    el('historyPagination').style.display = items.total > 0 ? 'flex' : 'none';

    const rows = items.items.map(it => `
      <tr>
        <td>${escapeHtml(it.title || it.key)}</td>
        <td>${escapeHtml(fmtTime(it.last_searched))}</td>
        <td>${escapeHtml(fmtTime(it.eligible_again))}</td>
      </tr>
    `).join('');

    el('historyTableWrap').innerHTML = `
      <table>
        <thead><tr><th>Title</th><th>Last Searched</th><th>Eligible Again</th></tr></thead>
        <tbody>${rows || '<tr><td colspan="3" class="help" style="text-align:center;padding:20px">No history yet.</td></tr>'}</tbody>
      </table>
    `;
  } catch(e) {
    el('historyTableWrap').innerHTML = `<p class="help" style="color:var(--bad)">Failed to load history: ${escapeHtml(e.message)}</p>`;
  }
}

function prevPage() { if (PAGE > 0) { PAGE--; refreshHistory(); } }
function nextPage() { PAGE++; refreshHistory(); }

async function pruneState() {
  if (!confirm('Prune expired history entries now?')) return;
  const out = await api('/api/state/prune', {method:'POST'});
  alert(`Pruned ${out.removed} entries.`);
  PAGE = 0; refreshHistory();
}

async function clearState() {
  if (!confirm('Clear all history? This removes all cooldown records.')) return;
  await api('/api/state/clear', {method:'POST'});
  alert('History cleared.');
  PAGE = 0; refreshHistory();
}

// ── Advanced tab ──
function fillAdvanced() {
  if (!CFG) return;
  el('radarr_missing_max').value = CFG.radarr_missing_max || 0;
  el('radarr_missing_added_days').value = CFG.radarr_missing_added_days || 14;
  el('sonarr_missing_max').value = CFG.sonarr_missing_max || 0;
  el('state_retention_days').value = CFG.state_retention_days || 180;
}

async function saveAdvanced() {
  try {
    CFG.radarr_missing_max = parseInt(el('radarr_missing_max').value || '0', 10);
    CFG.radarr_missing_added_days = parseInt(el('radarr_missing_added_days').value || '14', 10);
    CFG.sonarr_missing_max = parseInt(el('sonarr_missing_max').value || '0', 10);
    CFG.state_retention_days = parseInt(el('state_retention_days').value || '180', 10);
    CFG.state_pretty = false;
    await api('/api/config', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(CFG)});
    el('advMsg').textContent = 'Saved.'; el('advMsg').className = 'msg ok';
    await loadAll();
  } catch(e) {
    el('advMsg').textContent = 'Save failed: ' + e.message; el('advMsg').className = 'msg err';
  }
}

async function resetConfig() {
  if (!confirm('Reset config to defaults? All instances and settings will be lost.')) return;
  await api('/api/config/reset', {method:'POST'});
  alert('Config reset to defaults.');
  await loadAll();
}

function downloadFile(which) {
  const a = document.createElement('a');
  a.href = which === 'config' ? '/api/file/config' : '/api/file/state';
  a.download = which === 'config' ? 'nudgarr-config.json' : 'nudgarr-state.json';
  document.body.appendChild(a); a.click(); a.remove();
}

async function copyDiagnostic() {
  try {
    const data = await api('/api/diagnostic');
    el('diagBox').textContent = data.text;
    el('diagBox').style.display = 'block';
    // Use execCommand for local HTTP compatibility
    const ta = document.createElement('textarea');
    ta.value = data.text;
    ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    el('diagMsg').textContent = 'Copied to clipboard.'; el('diagMsg').className = 'msg ok';
  } catch(e) {
    el('diagMsg').textContent = 'Failed: ' + e.message; el('diagMsg').className = 'msg err';
  }
}

// ── Run Now ──
async function runNow() {
  try {
    await api('/api/run-now', {method:'POST'});
    el('lastRun').textContent = 'Running…';
  } catch(e) {
    alert('Run request failed: ' + e.message);
  }
}

// ── Status polling ──
async function refreshStatus() {
  try {
    const st = await api('/api/status');
    el('ver').textContent = st.version;
    el('lastRun').textContent = fmtTime(st.last_run_utc);
    el('nextRun').textContent = (CFG && CFG.scheduler_enabled) ? fmtTime(st.next_run_utc) : 'Manual';
    updateDryRunPill(CFG?.dry_run);
  } catch(e) {}
}

loadAll();
setInterval(refreshStatus, 5000);
</script>
</body>
</html>
"""

@app.get("/")
def index():
    return Response(UI_HTML, mimetype="text/html")

@app.get("/api/status")
def api_status():
    return jsonify(STATUS)

@app.get("/api/config")
def api_get_config():
    return jsonify(load_or_init_config())

@app.post("/api/config")
def api_set_config():
    cfg = request.get_json(force=True, silent=True)
    if not isinstance(cfg, dict):
        return jsonify({"ok": False, "error": "Body must be JSON object"}), 400
    ok, errs = validate_config(cfg)
    if not ok:
        return jsonify({"ok": False, "errors": errs}), 400
    save_json_atomic(CONFIG_FILE, cfg, pretty=True)
    return jsonify({"ok": True, "message": "Config saved", "config_file": CONFIG_FILE})

@app.post("/api/config/reset")
def api_reset_config():
    cfg = deep_copy(DEFAULT_CONFIG)
    save_json_atomic(CONFIG_FILE, cfg, pretty=True)
    return jsonify({"ok": True})

@app.post("/api/toggle-dry-run")
def api_toggle_dryrun():
    cfg = load_or_init_config()
    cfg["dry_run"] = not bool(cfg.get("dry_run", True))
    save_json_atomic(CONFIG_FILE, cfg, pretty=True)
    return jsonify({"ok": True, "dry_run": cfg["dry_run"]})

@app.post("/api/test")
def api_test():
    cfg = load_or_init_config()
    session = requests.Session()
    results = {"radarr": [], "sonarr": []}

    for inst in cfg.get("instances", {}).get("radarr", []):
        try:
            url = f"{inst['url'].rstrip('/')}/api/v3/system/status"
            data = req(session, "GET", url, inst["key"])
            results["radarr"].append({"name": inst["name"], "url": mask_url(inst["url"]), "ok": True, "version": data.get("version") if isinstance(data, dict) else None})
        except Exception as e:
            results["radarr"].append({"name": inst.get("name"), "url": mask_url(inst.get("url","")), "ok": False, "error": str(e)})

    for inst in cfg.get("instances", {}).get("sonarr", []):
        try:
            url = f"{inst['url'].rstrip('/')}/api/v3/system/status"
            data = req(session, "GET", url, inst["key"])
            results["sonarr"].append({"name": inst["name"], "url": mask_url(inst["url"]), "ok": True, "version": data.get("version") if isinstance(data, dict) else None})
        except Exception as e:
            results["sonarr"].append({"name": inst.get("name"), "url": mask_url(inst.get("url","")), "ok": False, "error": str(e)})

    return jsonify({"ok": True, "results": results})

# State endpoints
def _file_size(path: str) -> int:
    try:
        return os.path.getsize(path)
    except Exception:
        return 0

def _human_bytes(n: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return f"{n} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"

@app.get("/api/state/summary")
def api_state_summary():
    cfg = load_or_init_config()
    st = ensure_state_structure(load_state(), cfg)
    radarr_entries = 0
    sonarr_entries = 0
    per_instance: Dict[str, Dict[str, int]] = {"radarr": {}, "sonarr": {}}

    # Build mapping: state_key → friendly name
    name_map: Dict[str, str] = {}
    for inst in cfg.get("instances", {}).get("radarr", []):
        sk = state_key(inst["name"], inst["url"])
        name_map[sk] = inst["name"]
    for inst in cfg.get("instances", {}).get("sonarr", []):
        sk = state_key(inst["name"], inst["url"])
        name_map[sk] = inst["name"]

    instances: Dict[str, List[Dict[str, str]]] = {"radarr": [], "sonarr": []}
    for app in ("radarr", "sonarr"):
        app_obj = st.get(app, {})
        if isinstance(app_obj, dict):
            for sk, bucket in app_obj.items():
                friendly = name_map.get(sk, sk)
                instances[app].append({"key": sk, "name": friendly})
                if isinstance(bucket, dict):
                    count = len(bucket)
                    per_instance[app][sk] = count
                    if app == "radarr":
                        radarr_entries += count
                    else:
                        sonarr_entries += count

    size = _file_size(STATE_FILE)
    return jsonify({
        "file_size_bytes": size,
        "file_size_human": _human_bytes(size),
        "radarr_entries": radarr_entries,
        "sonarr_entries": sonarr_entries,
        "per_instance": per_instance,
        "instances": instances,
        "retention_days": int(cfg.get("state_retention_days", 180)),
    })

@app.get("/api/state/raw")
def api_state_raw():
    cfg = load_or_init_config()
    st = ensure_state_structure(load_state(), cfg)
    return jsonify(st)

@app.get("/api/state/items")
def api_state_items():
    cfg = load_or_init_config()
    st = ensure_state_structure(load_state(), cfg)
    app_name = request.args.get("app", "radarr")
    inst = request.args.get("instance", "")
    offset = int(request.args.get("offset", "0"))
    limit = int(request.args.get("limit", "250"))
    cooldown_hours = int(cfg.get("cooldown_hours", 48))

    app_obj = st.get(app_name, {})
    bucket = app_obj.get(inst, {}) if isinstance(app_obj, dict) else {}
    if not isinstance(bucket, dict):
        bucket = {}

    items = []
    for k, entry in bucket.items():
        if not isinstance(k, str):
            continue
        # Support both old string format and new dict format
        if isinstance(entry, dict):
            ts = entry.get("ts", "")
            title = entry.get("title", "")
        else:
            ts = entry if isinstance(entry, str) else ""
            title = ""
        # eligible again time
        dt = parse_iso(ts)
        eligible = ""
        if dt is not None:
            eligible_dt = dt + timedelta(hours=cooldown_hours)
            eligible = iso_z(eligible_dt)
        items.append({"key": k, "title": title, "last_searched": ts, "eligible_again": eligible})

    # newest first
    items.sort(key=lambda x: x.get("last_searched", ""), reverse=True)
    total = len(items)
    items = items[offset: offset+limit]
    return jsonify({"total": total, "items": items})

@app.post("/api/state/prune")
def api_state_prune():
    cfg = load_or_init_config()
    st = ensure_state_structure(load_state(), cfg)
    removed = prune_state_by_retention(st, int(cfg.get("state_retention_days", 180)))
    save_state(st, cfg)
    return jsonify({"ok": True, "removed": removed})

@app.post("/api/state/clear")
def api_state_clear():
    cfg = load_or_init_config()
    st = {"radarr": {}, "sonarr": {}}
    st = ensure_state_structure(st, cfg)
    save_state(st, cfg)
    return jsonify({"ok": True})

# File download endpoints
@app.get("/api/file/config")
def api_file_config():
    cfg = load_or_init_config()
    return Response(json.dumps(cfg, indent=2), mimetype="application/json")

@app.get("/api/file/state")
def api_file_state():
    cfg = load_or_init_config()
    st = ensure_state_structure(load_state(), cfg)
    pretty = True
    return Response(json.dumps(st, indent=2 if pretty else None), mimetype="application/json")

# Run-now endpoint
RUN_LOCK = threading.Lock()

@app.post("/api/run-now")
def api_run_now():
    with RUN_LOCK:
        STATUS["run_requested"] = True
    return jsonify({"ok": True})

@app.get("/api/diagnostic")
def api_diagnostic():
    cfg = load_or_init_config()
    radarr_instances = cfg.get("instances", {}).get("radarr", [])
    sonarr_instances = cfg.get("instances", {}).get("sonarr", [])
    radarr_names = [i.get("name") for i in radarr_instances]
    sonarr_names = [i.get("name") for i in sonarr_instances]

    # Per-instance state counts
    st = load_state()
    instance_counts = []
    for app in ("radarr", "sonarr"):
        app_obj = st.get(app, {})
        if isinstance(app_obj, dict):
            for sk, bucket in app_obj.items():
                count = len(bucket) if isinstance(bucket, dict) else 0
                instance_counts.append(f"  {app}/{sk}: {count} entries")

    last_summary = STATUS.get("last_summary") or {}
    summary_lines = []
    for app in ("radarr", "sonarr"):
        for s in last_summary.get(app, []):
            if "error" in s:
                summary_lines.append(f"  {s.get('name','?')}: ERROR — {s.get('error')}")
            else:
                summary_lines.append(f"  {s.get('name','?')}: searched={s.get('searched',0)} skipped_cooldown={s.get('skipped_cooldown',0)} missing_searched={s.get('searched_missing',0)}")

    lines = [
        f"Nudgarr v{VERSION}",
        f"Port: {PORT}",
        f"Last run: {STATUS.get('last_run_utc') or 'Never'}",
        f"Next run: {STATUS.get('next_run_utc') or 'N/A'}",
        f"Last error: {STATUS.get('last_error') or 'None'}",
        f"Scheduler: {'enabled' if cfg.get('scheduler_enabled') else 'manual'}, interval: {cfg.get('run_interval_minutes')}min",
        f"Dry run: {cfg.get('dry_run')}",
        f"Cooldown: {cfg.get('cooldown_hours')}h",
        f"Radarr instances ({len(radarr_names)}): {', '.join(radarr_names) or 'none'}",
        f"Sonarr instances ({len(sonarr_names)}): {', '.join(sonarr_names) or 'none'}",
        f"Radarr cap: {cfg.get('radarr_max_movies_per_run')}/run | Missing cap: {cfg.get('radarr_missing_max', 0)}/run",
        f"Sonarr cap: {cfg.get('sonarr_max_episodes_per_run')}/run | Missing cap: {cfg.get('sonarr_missing_max', 0)}/run",
        f"History file: {STATE_FILE}",
        f"Config file: {CONFIG_FILE}",
        "",
        "Last run summary:",
    ] + (summary_lines or ["  No runs yet."]) + [
        "",
        "History entry counts:",
    ] + (instance_counts or ["  No entries."])

    return jsonify({"text": "\n".join(lines)})

# -------------------------
# Scheduler / Service runner
# -------------------------

def print_banner(cfg: Dict[str, Any]) -> None:
    print("")
    print("====================================")
    print(f" Nudgarr v{VERSION}")
    print(" Because RSS sometimes needs a nudge.")
    print("====================================")
    print(f"Config: {CONFIG_FILE}")
    print(f"State:  {STATE_FILE}")
    print(f"UI:     http://<host>:{PORT}/")
    print("")
    print(f"Mode: {'loop' if cfg.get('scheduler_enabled', True) else 'manual'}  Interval: {cfg.get('run_interval_minutes')} minute(s)  DRY_RUN: {cfg.get('dry_run')}")
    print("")

def start_ui_server() -> None:
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)

def scheduler_loop(stop_flag: Dict[str, bool]) -> None:
    STATUS["scheduler_running"] = True
    session = requests.Session()
    cycle = 0
    run_event = threading.Event()

    # Patch RUN_LOCK to also signal the event so manual triggers wake immediately
    _orig_run_now_setter = None  # we'll use the event directly in the loop

    while not stop_flag["stop"]:
        cfg = load_or_init_config()
        # Ensure state file exists/structured even before first run
        st = ensure_state_structure(load_state(), cfg)
        save_state(st, cfg)

        now = utcnow()
        scheduler_enabled = bool(cfg.get("scheduler_enabled", True))

        interval_min = int(cfg.get("run_interval_minutes", 360))
        next_run = now + timedelta(minutes=interval_min)
        STATUS["next_run_utc"] = iso_z(next_run) if scheduler_enabled else None

        # Run on startup OR on schedule OR if manually requested
        should_run = (scheduler_enabled and cycle == 0)

        with RUN_LOCK:
            if STATUS.get("run_requested"):
                should_run = True
                STATUS["run_requested"] = False

        if should_run:
            cycle += 1
            STATUS["run_in_progress"] = True
            try:
                print(f"--- Sweep Cycle #{cycle} ---")
                summary = run_sweep(cfg, st, session)
                STATUS["last_summary"] = summary
                STATUS["last_run_utc"] = iso_z(utcnow())
                STATUS["last_error"] = None
            except Exception as e:
                STATUS["last_error"] = str(e)
                print(f"ERROR (sweep): {e}")
            finally:
                STATUS["run_in_progress"] = False

        if stop_flag["stop"]:
            break

        # Sleep until next run. In manual mode, wait up to 60s per tick so we
        # stay responsive to Run Now requests without busy-waiting for a year.
        sleep_seconds = interval_min * 60 if scheduler_enabled else 60
        deadline = time.monotonic() + sleep_seconds
        while not stop_flag["stop"] and time.monotonic() < deadline:
            with RUN_LOCK:
                if STATUS.get("run_requested"):
                    break
            time.sleep(1)

        # After sleeping the full interval, trigger the next scheduled run
        if scheduler_enabled and not stop_flag["stop"]:
            with RUN_LOCK:
                if not STATUS.get("run_requested"):
                    STATUS["run_requested"] = True

    STATUS["scheduler_running"] = False

def main() -> None:
    stop_flag = {"stop": False}

    def handle_signal(signum, frame):
        print("\nShutdown signal received. Stopping…")
        stop_flag["stop"] = True

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    cfg = load_or_init_config()
    print_banner(cfg)

    # Start UI
    threading.Thread(target=start_ui_server, daemon=True).start()

    # Run scheduler loop in main thread
    scheduler_loop(stop_flag)

    print("Nudgarr exiting.")

if __name__ == "__main__":
    main()

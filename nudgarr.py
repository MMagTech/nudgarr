#!/usr/bin/env python3
"""
Nudgarr v2.5.0 — Because RSS sometimes needs a nudge.

v2.5.0:
- Sample Modes expanded — Random, Alphabetical, Oldest Added, Newest Added
- Added field extracted from Radarr/Sonarr cutoff unmet endpoints for sort support
- Newest Added warning — amber notice on Settings and Advanced tabs when selected
- What's New modal — shows once per version upgrade, never on fresh install
- Support link pill — 🍺 Buy Me a Coffee in header, toggleable in Advanced → UI Preferences
- Confirm dialog copy updated — Prune Expired, Clear History, Clear Stats clarified
- Stats tab — Lifetime Confirmed pill above Movies and Shows cards
- Onboarding step 3 updated — all four sample modes described
- Onboarding final step updated — support link note added

v2.4.0:
- Title search on History and Stats tabs — inline with filters, ✕ to clear, no results message, resets on tab switch
- Pagination memory — shared across History and Stats, syncs for the session
- Data Retention — renamed from History Size, stats entries pruned alongside history, lifetime totals unaffected
- Retry logic — one retry per instance per sweep with 15 second wait, marks bad and moves on
- Instance error notifications — fires per failed instance with friendly unreachable message
- Error notification fix — now correctly fires on individual instance failures, not just catastrophic sweep failure
- Max Per Run labels updated to Per Instance across Settings and Advanced tabs
- Onboarding walkthrough updated — new Notifications step, per instance wording corrected throughout

v2.3.0:
- Apprise notifications tab — sweep complete, import confirmed, error triggers
- Universal docker-compose with .env support
- PUID/PGID startup fix — graceful chown fallback, cap_add CHOWN/SETUID/SETGID
- Sweep complete notification correctly aggregates across all instances
- Import Check help text corrected from Hours to Minutes
- Notifications save button colour fixed
- Open Issue button added to Diagnostics
- USE WITH CAUTION box moved to bottom of Advanced backlog card
- apk upgrade at build time for latest Alpine security patches

v2.2.0:
- First-run onboarding walkthrough — 8-step guided setup for new users
- Safe defaults — scheduler off, max per run 1, batch size 1 on fresh installs
- Password hashing upgraded to PBKDF2-HMAC-SHA256 with unique random salt
- Progressive brute force lockout: 3→30s, 6→5min, 10→30min, 15+→1hr
- Login countdown timer — button disables and counts down during lockout
- PUID/PGID support — container runs as specified UID/GID
- Lifetime Movies/Shows import totals persist through Clear Stats
- Clear Stats backend endpoint fixed
- Advanced tab reordered — History → Stats → Security
- README reverse proxy guidance for public internet exposure

v2.1.2:
- PUID/PGID support — container runs as specified UID/GID, defaults to 1000:1000
- Lifetime Movies/Shows import totals persist through Clear Stats
- Clear Stats backend endpoint fixed — was missing entirely
- Existing confirmed entries auto-seeded into lifetime totals on first run
- Save transition fixed — Unsaved Changes → Saved is visible and unhurried
- Sort indicators on all columns immediately on tab open
- Tab fade transition on switch
- Page size 10 added to History and Stats
- Docker resource limits right-sized for actual usage
- CI workflow — flake8 lint and syntax check on every push and PR

v2.1.0:
- Stats tab with confirmed import tracking
- Per-app Backlog Nudge toggles with age and cap controls
- Instance health dots — updated on every sweep and on add/edit
- Unsaved Changes notices across all tabs
- Import check delay in minutes, Check Now bypasses delay
- Non-root container user, read-only filesystem
- Multi-arch Docker images (amd64/arm64)

v2.0.0:
- Authentication — first run setup screen, hashed password, session timeout
- Require Login toggle in Advanced (default on)
- Login page styled to match UI
- Lockout recovery: delete config and restart
"""

import hashlib
import hmac
import json
import logging
import os
import random
import secrets
import signal
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests
from flask import Flask, jsonify, request, Response, session, redirect
try:
    import apprise
    APPRISE_AVAILABLE = True
except ImportError:
    APPRISE_AVAILABLE = False

VERSION = "2.5.0"

CONFIG_FILE = os.getenv("CONFIG_FILE", "/config/nudgarr-config.json")
STATE_FILE = os.getenv("STATE_FILE", "/config/nudgarr-state.json")
STATS_FILE = os.getenv("STATS_FILE", "/config/nudgarr-stats.json")
PORT = int(os.getenv("PORT", "8085"))

DEFAULT_CONFIG: Dict[str, Any] = {
    "scheduler_enabled": False,        # off by default — user enables deliberately
    "run_interval_minutes": 360,

    "cooldown_hours": 48,
    "sample_mode": "random",           # random | alphabetical | oldest_added | newest_added

    "radarr_max_movies_per_run": 1,
    "sonarr_max_episodes_per_run": 1,

    # Optional Radarr backlog missing nudges (OFF by default)
    "radarr_backlog_enabled": False,
    "radarr_missing_max": 1,
    "radarr_missing_added_days": 14,

    # Optional Sonarr backlog missing nudges (OFF by default)
    "sonarr_backlog_enabled": False,
    "sonarr_missing_max": 1,
    "sonarr_missing_added_days": 14,

    "batch_size": 1,
    "sleep_seconds": 5,
    "jitter_seconds": 2,

    # State size controls
    "state_retention_days": 180,       # prune entries older than this (0 disables)

    "instances": {"radarr": [], "sonarr": []},

    # Authentication (v2.0)
    "auth_enabled": True,
    "auth_username": "",
    "auth_password_hash": "",
    "auth_session_minutes": 30,

    # Stats (v2.0)
    "import_check_minutes": 120,

    # Notifications (v2.3.0)
    "notify_enabled": False,
    "notify_url": "",
    "notify_on_sweep_complete": True,
    "notify_on_import": True,
    "notify_on_error": True,

    # Onboarding
    "onboarding_complete": False,

    # UI Preferences (v2.5.0)
    "last_seen_version": "",
    "show_support_link": True,
}

# ─────────────────────────────────────────────────────────────────────
# Utilities
# Shared helpers: time, file I/O, URL masking, config validation, HTTP
# ─────────────────────────────────────────────────────────────────────

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

    if cfg.get("sample_mode") not in ("random", "alphabetical", "oldest_added", "newest_added"):
        errs.append("sample_mode must be 'random', 'alphabetical', 'oldest_added', or 'newest_added'")

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
    save_json_atomic(STATE_FILE, state, pretty=True)

# ─────────────────────────────────────────────────────────────────────
# Stats & Notifications
# Confirmed import tracking, lifetime totals, Apprise notification hooks
# ─────────────────────────────────────────────────────────────────────

def load_stats() -> Dict[str, Any]:
    st = load_json(STATS_FILE, {"entries": [], "lifetime_movies": 0, "lifetime_shows": 0})
    if not isinstance(st, dict):
        return {"entries": [], "lifetime_movies": 0, "lifetime_shows": 0}
    # Seed lifetime totals from existing confirmed entries if not yet set or uninitialized
    confirmed = [e for e in st.get("entries", []) if e.get("imported")]
    if st.get("lifetime_movies", 0) == 0 and st.get("lifetime_shows", 0) == 0 and confirmed:
        st["lifetime_movies"] = sum(1 for e in confirmed if e.get("app") == "radarr")
        st["lifetime_shows"] = sum(1 for e in confirmed if e.get("app") == "sonarr")
        save_json_atomic(STATS_FILE, st, pretty=True)
    st.setdefault("lifetime_movies", 0)
    st.setdefault("lifetime_shows", 0)
    return st

def save_stats(stats: Dict[str, Any]) -> None:
    save_json_atomic(STATS_FILE, stats, pretty=True)

# ── Notifications ──
# Apprise-based push notifications. send_notification() is the core
# dispatcher; notify_* helpers are called from the sweep engine.
def send_notification(title: str, body: str, cfg: Optional[Dict[str, Any]] = None) -> bool:
    """Send a notification via Apprise. Returns True on success."""
    if not APPRISE_AVAILABLE:
        print("[Notify] Apprise not available")
        return False
    if cfg is None:
        cfg = load_or_init_config()
    if not cfg.get("notify_enabled") or not cfg.get("notify_url", "").strip():
        return False
    try:
        ap = apprise.Apprise()
        ap.add(cfg["notify_url"].strip())
        result = ap.notify(title=title, body=body)
        if result:
            print(f"[Notify] Sent: {title}")
        else:
            print(f"[Notify] Failed to send: {title}")
        return result
    except Exception as e:
        print(f"[Notify] Error: {e}")
        return False

def notify_sweep_complete(summary: Dict[str, Any], cfg: Dict[str, Any]) -> None:
    if not cfg.get("notify_on_sweep_complete", True):
        return
    searched = 0
    skipped = 0
    for app in ("radarr", "sonarr"):
        for inst in summary.get(app, []):
            searched += inst.get("searched", 0) + inst.get("searched_missing", 0)
            skipped += inst.get("skipped_cooldown", 0) + inst.get("skipped_missing_cooldown", 0)
    send_notification(
        title="Nudgarr — Sweep Complete",
        body=f"{searched} item{'s' if searched != 1 else ''} searched, {skipped} skipped due to cooldown.",
        cfg=cfg
    )

def notify_import(title: str, entry_type: str, instance: str, cfg: Dict[str, Any]) -> None:
    if not cfg.get("notify_on_import", True):
        return
    send_notification(
        title=f"Nudgarr — {entry_type} Imported",
        body=f"{title} was successfully imported via {instance}.",
        cfg=cfg
    )

def notify_error(message: str, cfg: Optional[Dict[str, Any]] = None) -> None:
    if cfg is None:
        cfg = load_or_init_config()
    if not cfg.get("notify_on_error", True):
        return
    send_notification(
        title="Nudgarr — Error",
        body=message,
        cfg=cfg
    )

def record_stat_entry(app: str, instance_name: str, item_id: str, title: str, entry_type: str, searched_ts: str) -> None:
    """Record a searched item for later import checking. entry_type: 'Upgraded' or 'Acquired'"""
    stats = load_stats()
    entries = stats.get("entries", [])
    entries.append({
        "app": app,
        "instance": instance_name,
        "item_id": str(item_id),
        "title": title,
        "type": entry_type,
        "searched_ts": searched_ts,
        "imported": False,
        "imported_ts": None,
    })
    stats["entries"] = entries
    save_stats(stats)

def check_imports(session_obj: requests.Session, cfg: Dict[str, Any]) -> None:
    """Poll Radarr/Sonarr history for import events on recently searched items."""
    stats = load_stats()
    entries = stats.get("entries", [])
    check_minutes = int(cfg.get("import_check_minutes", 120))
    now = utcnow()
    updated = False

    # Build instance lookup
    instance_map: Dict[str, Dict[str, str]] = {}
    for inst in cfg.get("instances", {}).get("radarr", []):
        instance_map[("radarr", inst["name"])] = inst
    for inst in cfg.get("instances", {}).get("sonarr", []):
        instance_map[("sonarr", inst["name"])] = inst

    for entry in entries:
        if entry.get("imported"):
            continue
        searched_ts = entry.get("searched_ts")
        if not searched_ts:
            continue
        dt = parse_iso(searched_ts)
        if dt is None:
            continue
        # Only check after the delay has elapsed
        if (now - dt).total_seconds() / 60 < check_minutes:
            continue

        app = entry.get("app", "radarr")
        instance_name = entry.get("instance", "")
        inst = instance_map.get((app, instance_name))
        if not inst:
            continue

        url = inst["url"].rstrip("/")
        key = inst["key"]
        item_id = entry.get("item_id", "")

        try:
            if app == "radarr":
                r = session_obj.get(f"{url}/api/v3/history/movie", params={"movieId": item_id}, headers={"X-Api-Key": key}, timeout=15)
                if r.ok:
                    events = r.json() if isinstance(r.json(), list) else []
                    for ev in events:
                        if ev.get("eventType") == "downloadFolderImported":
                            ev_dt = parse_iso(ev.get("date", ""))
                            if ev_dt and ev_dt > dt:
                                entry["imported"] = True
                                entry["imported_ts"] = iso_z(ev_dt)
                                stats["lifetime_movies"] = stats.get("lifetime_movies", 0) + 1
                                notify_import(entry.get("title", "Unknown"), entry.get("type", "Upgraded"), instance_name, cfg)
                                updated = True
                                break
            else:
                r = session_obj.get(f"{url}/api/v3/history/series", params={"seriesId": item_id}, headers={"X-Api-Key": key}, timeout=15)
                if r.ok:
                    data = r.json()
                    events = data if isinstance(data, list) else data.get("records", [])
                    for ev in events:
                        if ev.get("eventType") == "downloadFolderImported":
                            ev_dt = parse_iso(ev.get("date", ""))
                            if ev_dt and ev_dt > dt:
                                entry["imported"] = True
                                entry["imported_ts"] = iso_z(ev_dt)
                                stats["lifetime_shows"] = stats.get("lifetime_shows", 0) + 1
                                notify_import(entry.get("title", "Unknown"), entry.get("type", "Upgraded"), instance_name, cfg)
                                updated = True
                                break
        except Exception as e:
            print(f"[Stats] Import check failed for {instance_name}/{item_id}: {e}")

    if updated:
        stats["entries"] = entries
        save_stats(stats)
        print("[Stats] Import check complete — updated confirmed imports")

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
    elif sample_mode == "alphabetical":
        eligible.sort(key=lambda x: (x.get("title") or "").lower())
    elif sample_mode == "oldest_added":
        # Items without added date sort to end
        eligible.sort(key=lambda x: (x.get("added") or "9999"))
    elif sample_mode == "newest_added":
        # Items without added date sort to end
        eligible.sort(key=lambda x: (x.get("added") or ""), reverse=True)
    # "first" and unknown modes: preserve original API order
    chosen = eligible[:max_per_run] if max_per_run > 0 else []
    return chosen, len(eligible), skipped

def pick_ids_with_cooldown(ids: List[int], st_bucket: Dict[str, Any], prefix: str, cooldown_hours: int, max_per_run: int, sample_mode: str) -> Tuple[List[int], int, int]:
    """Legacy helper for plain ID lists (kept for compatibility)."""
    items = [{"id": i, "title": ""} for i in ids]
    chosen_items, eligible, skipped = pick_items_with_cooldown(items, st_bucket, prefix, cooldown_hours, max_per_run, sample_mode)
    return [it["id"] for it in chosen_items], eligible, skipped

def mark_items_searched(st_bucket: Dict[str, Any], prefix: str, items: List[Dict[str, Any]], sweep_type: str = "") -> None:
    now_s = iso_z(utcnow())
    for item in items:
        st_bucket[f"{prefix}:{item['id']}"] = {"ts": now_s, "title": item.get("title") or "", "sweep_type": sweep_type}

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

# ─────────────────────────────────────────────────────────────────────
# Arr API Helpers
# Radarr/Sonarr API calls: cutoff unmet, missing, search commands
# ─────────────────────────────────────────────────────────────────────

def radarr_get_cutoff_unmet_movies(session: requests.Session, url: str, key: str, page_size: int = 100, max_pages: int = 5) -> List[Dict[str, Any]]:
    """Returns list of dicts: {id:int, title:str, added:str|None} from Wanted->Cutoff Unmet."""
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
            added = rec.get("added") or rec.get("addedDate") or rec.get("addedUtc")
            if isinstance(mid, int):
                movies.append({"id": mid, "title": rec.get("title") or f"Movie {mid}", "added": added})
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


def radarr_search_movies(session: requests.Session, url: str, key: str, movie_ids: List[int]) -> None:
    if not movie_ids:
        return
    cmd = f"{url.rstrip('/')}/api/v3/command"
    payload = {"name": "MoviesSearch", "movieIds": movie_ids}
    req(session, "POST", cmd, key, payload)
    print(f"[Radarr] Started MoviesSearch for {len(movie_ids)} movie(s)")

def sonarr_search_episodes(session: requests.Session, url: str, key: str, episode_ids: List[int]) -> None:
    if not episode_ids:
        return
    cmd = f"{url.rstrip('/')}/api/v3/command"
    payload = {"name": "EpisodeSearch", "episodeIds": episode_ids}
    req(session, "POST", cmd, key, payload)
    print(f"[Sonarr] Started EpisodeSearch for {len(episode_ids)} episode(s)")

def sonarr_get_cutoff_unmet_episodes(session: requests.Session, url: str, key: str, page_size: int = 100, max_pages: int = 5) -> List[Dict[str, Any]]:
    """Returns list of dicts: {id:int, series_id:int, title:str, added:str|None} from Wanted->Cutoff Unmet."""
    # First fetch all series to build id→title map
    series_map: Dict[int, str] = {}
    try:
        series_data = req(session, "GET", f"{url.rstrip('/')}/api/v3/series", key)
        if isinstance(series_data, list):
            for s in series_data:
                if isinstance(s.get("id"), int) and isinstance(s.get("title"), str):
                    series_map[s["id"]] = s["title"]
    except Exception:
        pass

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
            eid = rec.get("id") or rec.get("episodeId")
            if isinstance(eid, int):
                series_id = rec.get("seriesId")
                series_title = series_map.get(series_id) if series_id else None
                season = rec.get("seasonNumber")
                ep_num = rec.get("episodeNumber")
                ep_title = rec.get("title")
                added = rec.get("airDateUtc") or rec.get("added")
                if series_title and season is not None and ep_num is not None:
                    title = f"{series_title} S{season:02d}E{ep_num:02d}"
                    if ep_title:
                        title += f" · {ep_title}"
                else:
                    title = ep_title or f"Episode {eid}"
                episodes.append({"id": eid, "series_id": series_id, "title": title, "added": added})
    return episodes

def sonarr_get_missing_episodes(session: requests.Session, url: str, key: str, page_size: int = 100, max_pages: int = 5) -> List[Dict[str, Any]]:
    """Returns list of dicts: {id:int, series_id:int, title:str, added:str|None} from Wanted->Missing."""
    # Reuse series map
    series_map: Dict[int, str] = {}
    try:
        series_data = req(session, "GET", f"{url.rstrip('/')}/api/v3/series", key)
        if isinstance(series_data, list):
            for s in series_data:
                if isinstance(s.get("id"), int) and isinstance(s.get("title"), str):
                    series_map[s["id"]] = s["title"]
    except Exception:
        pass

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
                series_id = rec.get("seriesId")
                series_title = series_map.get(series_id) if series_id else None
                season = rec.get("seasonNumber")
                ep_num = rec.get("episodeNumber")
                ep_title = rec.get("title")
                added = rec.get("airDateUtc") or rec.get("added")
                if series_title and season is not None and ep_num is not None:
                    title = f"{series_title} S{season:02d}E{ep_num:02d}"
                    if ep_title:
                        title += f" · {ep_title}"
                else:
                    title = ep_title or f"Episode {eid}"
                episodes.append({"id": eid, "series_id": series_id, "title": title, "added": added})
    return episodes

# ─────────────────────────────────────────────────────────────────────
# Sweep Engine
# Core sweep logic: picks eligible items, applies cooldown, searches,
# records results, prunes state, fires notifications
# ─────────────────────────────────────────────────────────────────────

def run_sweep(cfg: Dict[str, Any], state: Dict[str, Any], session: requests.Session) -> Dict[str, Any]:
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

    # Prune stats entries using same retention setting — lifetime totals unaffected
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

    summary = {
        "pruned_entries": pruned,
        "radarr": [],
        "sonarr": [],
    }


    # RADARR
    for inst in cfg.get("instances", {}).get("radarr", []):
        name, url, key = inst["name"], inst["url"], inst["key"]
        ik = state_key(name, url)
        st_bucket = state.setdefault("radarr", {}).setdefault(ik, {})
        try:
            all_movies = radarr_get_cutoff_unmet_movies(session, url, key)
            STATUS["instance_health"][f"radarr|{name}"] = "ok"
            all_ids = [m["id"] for m in all_movies]
            chosen_items, eligible, skipped = pick_items_with_cooldown(all_movies, st_bucket, "movie", cooldown_hours, radarr_max, sample_mode)
            chosen = [m["id"] for m in chosen_items]
            print(f"[Radarr:{name}] cutoff_unmet_total={len(all_ids)} eligible={eligible} skipped_cooldown={skipped} will_search={len(chosen)} limit={radarr_max}")

            searched = 0
            for i in range(0, len(chosen_items), batch_size):
                batch_items = chosen_items[i:i+batch_size]
                batch_ids = [m["id"] for m in batch_items]
                radarr_search_movies(session, url, key, batch_ids)
                mark_items_searched(st_bucket, "movie", batch_items, "Cutoff Unmet")
                for m in batch_items:
                    record_stat_entry("radarr", name, str(m["id"]), m.get("title",""), "Upgraded", iso_z(utcnow()))
                searched += len(batch_items)
                if i + batch_size < len(chosen_items):
                    jitter_sleep(sleep_seconds, jitter_seconds)

            # Optional: Missing backlog nudges (Radarr only)
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
                    missing_filtered, st_bucket, "missing_movie", cooldown_hours, missing_max, sample_mode
                )
                print(f"[Radarr:{name}] missing_total={missing_total} eligible_missing={eligible_missing} skipped_missing_cooldown={skipped_missing} will_search_missing={len(chosen_missing)} limit_missing={missing_max} older_than_days={missing_added_days}")

                for i in range(0, len(chosen_missing), batch_size):
                    batch_items = chosen_missing[i:i+batch_size]
                    batch_ids = [m["id"] for m in batch_items]
                    radarr_search_movies(session, url, key, batch_ids)
                    mark_items_searched(st_bucket, "missing_movie", batch_items, "Backlog Nudge")
                    for m in batch_items:
                        record_stat_entry("radarr", name, str(m["id"]), m.get("title",""), "Acquired", iso_z(utcnow()))
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
            print(f"[Radarr:{name}] ERROR: {e} — retrying in 15s")
            time.sleep(15)
            try:
                all_movies = radarr_get_cutoff_unmet_movies(session, url, key)
                STATUS["instance_health"][f"radarr|{name}"] = "ok"
                print(f"[Radarr:{name}] Retry succeeded")
            except Exception as e2:
                print(f"[Radarr:{name}] Retry failed: {e2}")
                STATUS["instance_health"][f"radarr|{name}"] = "bad"
                summary["radarr"].append({"name": name, "url": mask_url(url), "error": str(e2)})

    # SONARR
    for inst in cfg.get("instances", {}).get("sonarr", []):
        name, url, key = inst["name"], inst["url"], inst["key"]
        ik = state_key(name, url)
        st_bucket = state.setdefault("sonarr", {}).setdefault(ik, {})
        try:
            all_episodes = sonarr_get_cutoff_unmet_episodes(session, url, key)
            STATUS["instance_health"][f"sonarr|{name}"] = "ok"
            all_ids = [e["id"] for e in all_episodes]
            chosen_items, eligible, skipped = pick_items_with_cooldown(all_episodes, st_bucket, "episode", cooldown_hours, sonarr_max, sample_mode)
            chosen = [e["id"] for e in chosen_items]
            print(f"[Sonarr:{name}] cutoff_unmet_total={len(all_ids)} eligible={eligible} skipped_cooldown={skipped} will_search={len(chosen)} limit={sonarr_max}")

            searched = 0
            for i in range(0, len(chosen_items), batch_size):
                batch_items = chosen_items[i:i+batch_size]
                batch_ids = [e["id"] for e in batch_items]
                sonarr_search_episodes(session, url, key, batch_ids)
                mark_items_searched(st_bucket, "episode", batch_items, "Cutoff Unmet")
                for e in batch_items:
                    record_stat_entry("sonarr", name, str(e.get("series_id") or e["id"]), e.get("title",""), "Upgraded", iso_z(utcnow()))
                searched += len(batch_items)
                if i + batch_size < len(chosen_items):
                    jitter_sleep(sleep_seconds, jitter_seconds)

            # Optional: Missing backlog nudges (Sonarr)
            sonarr_missing_max = int(cfg.get("sonarr_missing_max", 1))
            sonarr_backlog_enabled = bool(cfg.get("sonarr_backlog_enabled", False))
            missing_total = 0
            eligible_missing = 0
            skipped_missing = 0
            searched_missing = 0
            chosen_missing: List[Dict[str, Any]] = []

            if sonarr_backlog_enabled and sonarr_missing_max > 0:
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
                    sonarr_search_episodes(session, url, key, batch_ids)
                    mark_items_searched(st_bucket, "missing_episode", batch_items, "Backlog Nudge")
                    for e in batch_items:
                        record_stat_entry("sonarr", name, str(e.get("series_id") or e["id"]), e.get("title",""), "Acquired", iso_z(utcnow()))
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
            print(f"[Sonarr:{name}] ERROR: {e} — retrying in 15s")
            time.sleep(15)
            try:
                all_episodes = sonarr_get_cutoff_unmet_episodes(session, url, key)
                STATUS["instance_health"][f"sonarr|{name}"] = "ok"
                print(f"[Sonarr:{name}] Retry succeeded")
            except Exception as e2:
                print(f"[Sonarr:{name}] Retry failed: {e2}")
                STATUS["instance_health"][f"sonarr|{name}"] = "bad"
                summary["sonarr"].append({"name": name, "url": mask_url(url), "error": str(e2)})

    # Persist state (even on dry run, so pruning/structure changes persist)
    save_state(state, cfg)
    print(f"State saved: {STATE_FILE} pruned={pruned}")

    return summary

# ─────────────────────────────────────────────────────────────────────
# Web UI — Embedded HTML Templates
# Nudgarr is intentionally a single-file application. All HTML, CSS and
# JS is embedded here as raw strings to eliminate build steps and keep
# deployment as simple as possible (one file, one container).
# LOGIN_HTML  — login page
# SETUP_HTML  — first-run account creation
# UI_HTML     — main application interface
# ─────────────────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)
# Note: secret_key is regenerated on restart if not set via env var.
# Sessions will be invalidated on container restart — expected behaviour for local tool.
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# ─────────────────────────────────────────────────────────────────────
# Auth Helpers
# Password hashing (PBKDF2-HMAC-SHA256), session management,
# progressive brute force lockout, login required decorator
# ─────────────────────────────────────────────────────────────────────

SESSION_TIMEOUT_MINUTES = 30  # default, overridden by config

def hash_password(password: str) -> str:
    """Hash password using PBKDF2-HMAC-SHA256 with a random salt. Returns 'salt:hash'."""
    salt = secrets.token_hex(32)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260000).hex()
    return f"{salt}:{h}"

def verify_password(password: str, stored: str) -> bool:
    """Verify password against stored 'salt:hash' or legacy plain sha256 hash."""
    if ":" in stored:
        salt, h = stored.split(":", 1)
        expected = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260000).hex()
        return hmac.compare_digest(expected, h)
    # Legacy sha256 — auto-migrate on next successful login
    return hmac.compare_digest(hashlib.sha256(password.encode()).hexdigest(), stored)

# ── Progressive brute force lockout ──
_AUTH_FAILURES: Dict[str, Any] = {}  # ip -> {"count": int, "locked_until": float}
_AUTH_LOCK = threading.Lock()

LOCKOUT_SCHEDULE = [
    (3, 30),        # 3 failures  → 30 seconds
    (6, 300),       # 6 failures  → 5 minutes
    (10, 1800),     # 10 failures → 30 minutes
    (15, 3600),     # 15+ failures → 1 hour
]

def get_lockout_seconds(count: int) -> int:
    duration = 0
    for threshold, seconds in LOCKOUT_SCHEDULE:
        if count >= threshold:
            duration = seconds
    return duration

def check_auth_lockout(ip: str) -> tuple:
    """Returns (is_locked, seconds_remaining)."""
    with _AUTH_LOCK:
        record = _AUTH_FAILURES.get(ip)
        if not record:
            return False, 0
        if record["locked_until"] and time.time() < record["locked_until"]:
            return True, int(record["locked_until"] - time.time())
        return False, 0

def record_auth_failure(ip: str) -> int:
    """Record a failed attempt. Returns lockout duration in seconds (0 if none)."""
    with _AUTH_LOCK:
        record = _AUTH_FAILURES.get(ip, {"count": 0, "locked_until": 0.0})
        # Reset if previous lockout has expired
        if record["locked_until"] and time.time() >= record["locked_until"]:
            record = {"count": 0, "locked_until": 0.0}
        record["count"] += 1
        duration = get_lockout_seconds(record["count"])
        record["locked_until"] = time.time() + duration if duration else 0.0
        _AUTH_FAILURES[ip] = record
        return duration

def clear_auth_failures(ip: str) -> None:
    with _AUTH_LOCK:
        _AUTH_FAILURES.pop(ip, None)

def auth_required() -> bool:
    """Returns True if auth is enabled and credentials are configured."""
    cfg = load_or_init_config()
    return bool(cfg.get("auth_enabled", True)) and bool(cfg.get("auth_password_hash", ""))

def is_setup_needed() -> bool:
    """Returns True if auth is enabled but no credentials have been set up yet."""
    cfg = load_or_init_config()
    return bool(cfg.get("auth_enabled", True)) and not bool(cfg.get("auth_password_hash", ""))

def is_authenticated() -> bool:
    """Check if current session is valid and not timed out."""
    if not auth_required():
        return True
    last_active = session.get("last_active")
    if not last_active:
        return False
    cfg = load_or_init_config()
    timeout = int(cfg.get("auth_session_minutes", SESSION_TIMEOUT_MINUTES))
    elapsed = (datetime.now().timestamp() - last_active) / 60
    if elapsed > timeout:
        session.clear()
        return False
    session["last_active"] = datetime.now().timestamp()
    return True

def requires_auth(f):
    """Decorator for routes that need authentication."""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if is_setup_needed():
            if request.path != "/setup" and not request.path.startswith("/api/setup"):
                return redirect("/setup")
        elif auth_required() and not is_authenticated():
            if request.path != "/login" and not request.path.startswith("/api/auth"):
                if request.path.startswith("/api/"):
                    return jsonify({"ok": False, "error": "Unauthorized"}), 401
                return redirect("/login")
        return f(*args, **kwargs)
    return decorated


LOGIN_HTML = r"""<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Nudgarr — Login</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; }
    body { margin: 0; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
      background: #11131f; color: #e8eaf0; font-size: 14px; display: flex; align-items: center; justify-content: center; min-height: 100vh; }
    .card { background: #1e2030; border: 1px solid rgba(255,255,255,.10); border-radius: 18px; padding: 32px; width: 100%; max-width: 360px; }
    h1 { font-size: 20px; font-weight: 700; margin: 0 0 4px; }
    .sub { color: #7c8494; font-size: 13px; margin: 0 0 24px; }
    label { font-size: 12px; color: #7c8494; font-weight: 500; display: block; margin-bottom: 5px; }
    input { width: 100%; padding: 10px 12px; border-radius: 9px; border: 1px solid rgba(255,255,255,.10);
      background: #181a28; color: #e8eaf0; font-size: 13px; outline: none; margin-bottom: 14px; }
    input:focus { border-color: rgba(99,120,255,.6); }
    button { width: 100%; padding: 10px; border-radius: 10px; border: 1px solid rgba(99,120,255,.35);
      background: rgba(99,120,255,.2); color: #a8b4ff; font-size: 14px; font-weight: 600; cursor: pointer; }
    button:hover:not(:disabled) { background: rgba(99,120,255,.32); color: #c0caff; }
    button:disabled { opacity: 0.45; cursor: not-allowed; }
    .err { color: #fca5a5; font-size: 12px; margin-bottom: 14px; display: none; }
    .err.show { display: block; }
  </style>
</head>
<body>
<div class="card">
  <h1>Nudgarr</h1>
  <p class="sub">Sign in to continue</p>
  <div class="err" id="err"></div>
  <label>Username</label>
  <input type="text" id="usr" autocomplete="username" autofocus/>
  <label>Password</label>
  <input type="password" id="pwd" autocomplete="current-password" onkeydown="if(event.key==='Enter')login()"/>
  <button id="btn" onclick="login()">Sign In</button>
</div>
<script>
let _countdown = null;

function startCountdown(seconds) {
  const btn = document.getElementById('btn');
  const err = document.getElementById('err');
  btn.disabled = true;
  if (_countdown) clearInterval(_countdown);
  let remaining = seconds;
  function tick() {
    if (remaining <= 0) {
      clearInterval(_countdown);
      btn.disabled = false;
      btn.textContent = 'Sign In';
      err.textContent = 'You may try again.';
      return;
    }
    btn.textContent = `Try again in ${remaining}s`;
    remaining--;
  }
  tick();
  _countdown = setInterval(tick, 1000);
}

async function login() {
  const r = await fetch('/api/auth/login', {method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({username: document.getElementById('usr').value, password: document.getElementById('pwd').value})
  });
  if (r.ok) { window.location.href = '/'; }
  else {
    const d = await r.json();
    const err = document.getElementById('err');
    err.textContent = d.error || 'Invalid username or password.';
    err.classList.add('show');
    // Parse seconds from lockout message and start countdown
    const match = d.error && d.error.match(/Try again in (\d+)s/);
    if (match) {
      err.textContent = 'Too many failed attempts.';
      startCountdown(parseInt(match[1]));
    }
  }
}
</script>
</body>
</html>"""

SETUP_HTML = r"""<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Nudgarr — Setup</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; }
    body { margin: 0; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
      background: #11131f; color: #e8eaf0; font-size: 14px; display: flex; align-items: center; justify-content: center; min-height: 100vh; }
    .card { background: #1e2030; border: 1px solid rgba(255,255,255,.10); border-radius: 18px; padding: 32px; width: 100%; max-width: 400px; }
    h1 { font-size: 20px; font-weight: 700; margin: 0 0 4px; }
    .sub { color: #7c8494; font-size: 13px; margin: 0 0 24px; line-height: 1.5; }
    label { font-size: 12px; color: #7c8494; font-weight: 500; display: block; margin-bottom: 5px; }
    input { width: 100%; padding: 10px 12px; border-radius: 9px; border: 1px solid rgba(255,255,255,.10);
      background: #181a28; color: #e8eaf0; font-size: 13px; outline: none; margin-bottom: 14px; }
    input:focus { border-color: rgba(99,120,255,.6); }
    button { width: 100%; padding: 10px; border-radius: 10px; border: 1px solid rgba(99,120,255,.35);
      background: rgba(99,120,255,.2); color: #a8b4ff; font-size: 14px; font-weight: 600; cursor: pointer; }
    button:hover { background: rgba(99,120,255,.32); color: #c0caff; }
    .err { color: #fca5a5; font-size: 12px; margin-bottom: 14px; display: none; }
    .err.show { display: block; }
  </style>
</head>
<body>
<div class="card">
  <h1>Welcome to Nudgarr</h1>
  <p class="sub">Create your login credentials to get started. These will be required to access the UI.<br><br>To disable login later, go to Advanced → Require Login.</p>
  <div class="err" id="err"></div>
  <label>Username</label>
  <input type="text" id="usr" autocomplete="username" autofocus/>
  <label>Password</label>
  <input type="password" id="pwd" autocomplete="new-password"/>
  <label>Confirm Password</label>
  <input type="password" id="pwd2" autocomplete="new-password" onkeydown="if(event.key==='Enter')setup()"/>
  <button onclick="setup()">Create Account</button>
</div>
<script>
async function setup() {
  const usr = document.getElementById('usr').value.trim();
  const pwd = document.getElementById('pwd').value;
  const pwd2 = document.getElementById('pwd2').value;
  const err = document.getElementById('err');
  if (!usr) { err.textContent = 'Username is required.'; err.classList.add('show'); return; }
  if (pwd.length < 6) { err.textContent = 'Password must be at least 6 characters.'; err.classList.add('show'); return; }
  if (pwd !== pwd2) { err.textContent = 'Passwords do not match.'; err.classList.add('show'); return; }
  const r = await fetch('/api/setup', {method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({username: usr, password: pwd})
  });
  if (r.ok) { window.location.href = '/'; }
  else { const d = await r.json(); err.textContent = d.error || 'Setup failed.'; err.classList.add('show'); }
}
</script>
</body>
</html>"""

# Runtime status dict — shared between scheduler thread and Flask routes
# Read by /api/status endpoint and updated throughout sweep lifecycle
STATUS: Dict[str, Any] = {
    "version": VERSION,
    "last_run_utc": None,
    "next_run_utc": None,
    "last_summary": None,
    "scheduler_running": False,
    "run_in_progress": False,
    "run_requested": False,
    "last_error": None,
    "instance_health": {},  # {"radarr|name": "ok"|"bad", ...}
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
      color: #c0caff; font-weight: 600;
      padding: 6px 12px; font-size: 12px; border-radius: 999px;
    }
    .btn.run-now:hover { background: rgba(99,120,255,.4); color: #fff; }
    .btn.sign-out {
      padding: 6px 12px; font-size: 12px; border-radius: 999px;
    }

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
    .section { display: none; opacity: 0; }
    .section.active { display: block; animation: tabFadeIn 0.18s ease forwards; }
    .section.leaving { animation: tabFadeOut 0.1s ease forwards; }
    @keyframes tabFadeIn { from { opacity: 0; } to { opacity: 1; } }
    @keyframes tabFadeOut { from { opacity: 1; } to { opacity: 0; } }

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
    label { font-size: 12px; color: var(--text-dim); font-weight: 500; }
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
    .msg { font-size: 12px; color: var(--muted); transition: opacity 0.5s ease; }
    .msg.ok { color: var(--ok); }
    .msg.err { color: var(--bad); }
    .msg.unsaved { color: #fbbf24; }
    .msg.fade { opacity: 0; }
    th.sortable { cursor: pointer; user-select: none; }
    th.sortable:hover { color: var(--text); }
    th.sortable::after { content: ' ↕'; opacity: 0.25; font-size: 10px; }
    th.sort-asc::after { content: ' ↑'; opacity: 1; }
    th.sort-desc::after { content: ' ↓'; opacity: 1; }

    /* ── Toggle switch ── */
    .toggle-wrap { display: flex; align-items: center; gap: 10px; }
    .toggle {
      position: relative; width: 36px; height: 20px;
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
      position: absolute; top: 50%; left: 3px;
      transform: translateY(-50%);
      width: 14px; height: 14px; border-radius: 50%;
      background: var(--muted); transition: left .2s, background .2s;
    }
    .toggle input:checked ~ .toggle-thumb { left: 19px; background: #fff; transform: translateY(-50%); }

    /* ── Instance cards ── */
    .inst-card {
      border: 1px solid var(--border); border-radius: 12px;
      padding: 13px 14px; margin-top: 8px; background: var(--surface);
      display: flex; align-items: center; gap: 10px;
    }
    .inst-card .inst-info { flex: 1; min-width: 0; }
    .inst-card .inst-name { font-size: 11px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-dim); }
    .inst-card .inst-meta { font-size: 12px; color: var(--muted); margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .inst-card .inst-actions { display: flex; gap: 6px; flex-shrink: 0; }
    .status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--border); flex-shrink: 0; transition: background .3s; }
    .status-dot.ok { background: var(--ok); }
    .status-dot.bad { background: var(--bad); }
    .status-dot.checking { background: var(--warn); animation: pulse 1s infinite; }
    .dot.running { background: var(--warn) !important; animation: pulse 1s infinite; }
    @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
    #pill-lastrun { min-width: 185px; }

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
      font-size: 13px; font-weight: 600; letter-spacing: .04em;
      color: var(--text);
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
    .import-stats { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 14px; }
    .import-stat-card { flex: 1; display: flex; align-items: center; justify-content: center; gap: 8px; padding: 10px 16px; border-radius: 20px; border: 1px solid; font-size: 13px; }
    .import-stat-card.movies { background: rgba(99,102,241,0.07); border-color: rgba(99,102,241,0.3); }
    .import-stat-card.shows { background: rgba(99,102,241,0.07); border-color: rgba(99,102,241,0.3); }
    .import-stat-label { font-weight: 500; color: rgba(99,102,241,0.7); }
    .import-stat-value { font-weight: 700; font-size: 15px; color: #6366f1; text-shadow: 0 0 16px rgba(99,102,241,0.4); }


    /* ── Tooltips ── */
    .tooltip-wrap { position: relative; display: inline-flex; align-items: center; gap: 5px; }
    .tooltip-icon {
      display: inline-flex; align-items: center; justify-content: center;
      width: 14px; height: 14px; border-radius: 50%;
      border: 1px solid var(--accent-border); color: var(--accent);
      font-size: 9px; font-style: italic; font-weight: 700;
      cursor: default; flex-shrink: 0; line-height: 1;
      user-select: none; transition: background .15s, border-color .15s;
      position: relative;
    }
    .tooltip-wrap:hover .tooltip-icon { background: var(--accent-dim); border-color: var(--accent); }
    .tooltip-wrap:hover .tooltip-icon .tooltip-box { opacity: 1; pointer-events: auto; }
    .tooltip-box {
      position: absolute; left: calc(100% + 3px); bottom: 0; top: auto;
      background: #242640; border: 1px solid var(--accent-border);
      border-radius: 10px; padding: 10px 12px;
      font-size: 12px; font-weight: 400; font-style: normal;
      color: var(--text-dim); line-height: 1.5;
      width: 360px; z-index: 100;
      opacity: 0; pointer-events: none;
      transition: opacity .2s;
      box-shadow: 0 12px 32px rgba(0,0,0,.6), 0 0 0 1px rgba(99,120,255,.08);
    }

    /* ── Cooldown warning flash ── */
    @keyframes warnFlash {
      0%,100% { opacity: 1; }
      50% { opacity: 0; }
    }
    .warn-flash { animation: warnFlash 1s ease 3; color: var(--warn); font-size: 12px; }
    .warn-steady { color: var(--warn); font-size: 12px; }
    /* ── Amber warning boxes ── */
    .amber-warn {
      padding: 12px; border-radius: 12px;
      background: rgba(251,191,36,0.06); border: 1px solid rgba(251,191,36,0.2);
    }
    .amber-warn-title { font-size: 12px; color: #fbbf24; font-weight: 600; margin: 0 0 4px; }
    .amber-warn-body { margin: 0; }
    .amber-warn-collapsible {
      overflow: hidden;
      max-height: 0;
      opacity: 0;
      transition: max-height 0.35s ease, opacity 0.3s ease, margin-top 0.35s ease;
      margin-top: 0;
    }
    .amber-warn-collapsible.visible {
      max-height: 120px;
      opacity: 1;
      margin-top: 6px;
    }

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
      <h1><span style="font-style:italic; letter-spacing:0.03em">Nudgarr</span> <span style="font-weight:400; font-size:13px; color:var(--muted)">v<span id="ver"></span></span></h1>
      <p>Sweeping your library, one nudge at a time.</p>
    </div>
    <div class="header-right">
      <div class="pill" id="pill-dryrun"><span class="dot" id="dot-dryrun"></span><span id="txt-dryrun">Loading…</span></div>
      <div class="pill" id="pill-lastrun"><span>Last: <span id="lastRun">—</span></span></div>
      <div class="pill"><span>Next: <span id="nextRun">—</span></span></div>
      <button class="btn run-now" onclick="runNow()">Run Now</button>
      <button class="btn sign-out" onclick="logout()" id="logoutBtn" style="display:none">Sign Out</button>
    </div>
  </div>

  <!-- Tabs -->
  <div class="tabs">
    <div class="tab active" data-tab="instances" onclick="showTab('instances')">Instances</div>
    <div class="tab" data-tab="settings" onclick="showTab('settings')">Settings</div>
    <div class="tab" data-tab="history" onclick="showTab('history')">History</div>
    <div class="tab" data-tab="stats" onclick="showTab('stats')">Stats</div>
    <div class="tab" data-tab="notifications" onclick="showTab('notifications')">Notifications</div>
    <div class="tab" data-tab="advanced" onclick="showTab('advanced')">Advanced</div>
    <a id="supportLink" href="https://buymeacoffee.com/mmagtech" target="_blank" class="pill clickable" style="text-decoration:none;display:none;margin-left:auto;align-self:center;white-space:nowrap;padding:7px 14px;font-size:13px" title="Buy Me a Coffee">🍺 Donate</a>
  </div>

  <!-- ══════════════════════════════ INSTANCES ══════════════════════════════ -->
  <div class="section active" id="tab-instances">
    <div class="grid cols2">
      <div class="card">
        <div class="row" style="margin-bottom:12px">
          <span class="section-label" style="margin:0">Radarr Instances</span>
          <button class="btn sm" style="margin-left:auto" onclick="addInstance('radarr')">+ Add</button>
        </div>
        <p class="help" style="margin:0 0 8px">Add one or more Radarr instances.</p>
        <div id="radarrList"></div>
      </div>

      <div class="card">
        <div class="row" style="margin-bottom:12px">
          <span class="section-label" style="margin:0">Sonarr Instances</span>
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
        <div class="help" style="margin-top:8px">Connection status updates automatically on each sweep.</div>
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
                <input type="checkbox" id="scheduler_enabled" onchange="syncSchedulerUi(); markUnsaved('setMsg')"/>
                <span class="toggle-track"></span>
                <span class="toggle-thumb"></span>
              </label>
              <span class="help" id="scheduler_label">Enabled</span>
            </div>
            <div class="help">When disabled, only sweeps when you click <b>Run Now</b>.</div>
          </div>
          <div class="field" style="max-width:160px">
            <div class="tooltip-wrap">
              <label>Run Interval (Hours)</label>
              <span class="tooltip-icon">i<div class="tooltip-box">How often Nudgarr automatically fires a sweep. If set to 6 hours, a sweep runs every 6 hours when the scheduler is enabled. Setting this too low combined with a short cooldown and high max per run can generate enough search traffic to trigger indexer rate limits or bans.</div></span>
            </div>
            <input id="run_interval_minutes" type="number" min="1" oninput="markUnsaved('setMsg'); checkCooldownWarning()"/>
            <div class="help">How often sweeps run.</div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="row" style="margin-bottom:10px"><p class="section-label" style="margin:0">Search Behaviour</p><span id="cooldownWarnMsg"></span></div>
        <div class="grid cols2" style="gap:12px">
          <div class="field">
            <div class="tooltip-wrap">
              <label>Cooldown (Hours)</label>
              <span class="tooltip-icon">i<div class="tooltip-box">How long Nudgarr waits before searching the same item again. If your run interval is 6 hours and cooldown is 4 hours, the same item will be searched every single sweep because it's always past cooldown by the time the next run fires. Most indexers recommend waiting at least 24-48 hours between searches for the same item to avoid triggering rate limits or bans.</div></span>
            </div>
            <input id="cooldown_hours" type="number" min="0" oninput="markUnsaved('setMsg'); checkCooldownWarning()"/>
            <div class="help">Minimum hours before the same movie or episode can be searched again. 0 disables.</div>
          </div>
          <div class="field">
            <div class="tooltip-wrap">
              <label>Sample Mode</label>
              <span class="tooltip-icon">i<div class="tooltip-box">Controls which eligible items are selected each run.<br><br><strong>Random</strong> — different items each run for even coverage.<br><br><strong>Alphabetical</strong> — works through your library from A to Z.<br><br><strong>Oldest Added</strong> — picks from the oldest end of your eligible pool.<br><br><strong>Newest Added</strong> — picks from the newest end of your eligible pool.<br><br><em>Radarr's Missing Added Days sets the eligible pool. For example, with days set to 30 only items added 30+ days ago qualify — Newest Added then picks the ones closest to that cutoff first. Set days to 0 to search all missing items newest-first with no age filter.</em></div></span>
            </div>
            <select id="sample_mode" onchange="markUnsaved('setMsg'); checkNewestAddedWarning()">
              <option value="random">Random</option>
              <option value="alphabetical">Alphabetical</option>
              <option value="oldest_added">Oldest Added</option>
              <option value="newest_added">Newest Added</option>
            </select>
            <div class="help" id="sampleModeHelp">How Nudgarr picks which eligible items to search each run.</div>
            <div id="newestAddedWarnSettings" class="amber-warn amber-warn-collapsible">
              <p class="help amber-warn-body">⚠️ <strong>Newest Added</strong> is active and Radarr backlog nudges are enabled. Items closest to your Missing Added Days cutoff will be searched first.</p>
            </div>
          </div>
        </div>
        <div class="grid cols2" style="gap:12px">
          <div class="field">
            <div class="tooltip-wrap">
              <label>Max Movies (Per Instance)</label>
              <span class="tooltip-icon">i<div class="tooltip-box">How many Cutoff Unmet movies are searched per Radarr instance each sweep. If you have two Radarr instances both set to 20, a single sweep could trigger up to 40 movie searches. Start low and increase gradually — combine with a sensible cooldown and run interval to keep total search volume manageable.</div></span>
            </div>
            <input id="radarr_max_movies_per_run" type="number" min="0" oninput="markUnsaved('setMsg')"/>
            <div class="help">Maximum Cutoff Unmet movies searched per instance per run. 0 disables.</div>
          </div>
          <div class="field">
            <div class="tooltip-wrap">
              <label>Max Episodes (Per Instance)</label>
              <span class="tooltip-icon">i<div class="tooltip-box">How many Cutoff Unmet episodes are searched per Sonarr instance each sweep. If you have two Sonarr instances both set to 20, a single sweep could trigger up to 40 episode searches. Start low and increase gradually — combine with a sensible cooldown and run interval to keep total search volume manageable.</div></span>
            </div>
            <input id="sonarr_max_episodes_per_run" type="number" min="0" oninput="markUnsaved('setMsg')"/>
            <div class="help">Maximum Cutoff Unmet episodes searched per instance per run. 0 disables.</div>
          </div>
        </div>
      </div>

      <div class="card">
        <p class="section-label">Throttling</p>
        <div class="grid cols2" style="gap:12px">
          <div class="field">
            <div class="tooltip-wrap">
              <label>Batch Size</label>
              <span class="tooltip-icon">i<div class="tooltip-box">How many search commands are sent to your indexer at once per batch. A batch size of 1 means each item is searched individually with a pause in between. Higher values send multiple searches simultaneously which can overwhelm indexers and trigger rate limiting. Keep this at 1 unless you have a specific reason to increase it.</div></span>
            </div>
            <input id="batch_size" type="number" min="1" oninput="markUnsaved('setMsg')"/>
            <div class="help">Number of items sent per search command. Smaller values are easier on your indexers.</div>
          </div>
          <div class="field">
            <div class="tooltip-wrap">
              <label>Sleep Seconds</label>
              <span class="tooltip-icon">i<div class="tooltip-box">How long Nudgarr pauses between each batch of searches. Combined with batch size this controls the overall pace of a sweep. A sleep of 5 seconds with a batch size of 1 means one search every 5 seconds. Lowering this too much reduces the breathing room between searches and increases the risk of hitting indexer rate limits.</div></span>
            </div>
            <input id="sleep_seconds" type="number" min="0" step="0.1" oninput="markUnsaved('setMsg')"/>
            <div class="help">Pause between batches in seconds. Gives your indexers time to breathe.</div>
          </div>
          <div class="field">
            <div class="tooltip-wrap">
              <label>Jitter Seconds</label>
              <span class="tooltip-icon">i<div class="tooltip-box">Adds a random delay on top of the sleep time between batches. If sleep is 5 seconds and jitter is 2 seconds, actual pauses will vary between 5 and 7 seconds. This randomness makes Nudgarr's search pattern less predictable and helps avoid triggering automated rate limit detection that looks for suspiciously regular request intervals.</div></span>
            </div>
            <input id="jitter_seconds" type="number" min="0" step="0.1" oninput="markUnsaved('setMsg')"/>
            <div class="help">Random extra pause on top of Sleep Seconds to help avoid indexer rate limiting.</div>
          </div>
        </div>
      </div>

      <div class="card amber-warn">
        <p class="amber-warn-title">INDEXER LIMITS</p>
        <p class="help amber-warn-body">Nudgarr instructs your Radarr and Sonarr instances to search using your configured indexers. Be mindful of their rate limits — aggressive search behaviour can result in temporary or permanent bans.</p>
      </div>

      <div class="row" style="margin-top:16px">
        <button class="btn primary" onclick="saveSettings()">Save Changes</button>
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
        <div style="margin-left:auto; display:flex; gap:8px; align-items:center;">
          <div class="field" style="min-width:200px">
            <select id="historyInstance" onchange="PAGE=0; refreshHistory()"></select>
          </div>
          <div class="field" style="min-width:100px">
            <select id="historyLimit" onchange="syncPageSize('history'); PAGE=0; refreshHistory()">
              <option>10</option><option selected>25</option><option>50</option><option>100</option>
            </select>
          </div>
          <div class="field" style="min-width:180px;position:relative">
            <input type="text" id="historySearch" placeholder="Search title…" oninput="filterHistorySearch()" style="padding-right:28px"/>
            <button id="historySearchClear" onclick="clearHistorySearch()" style="display:none;position:absolute;right:6px;top:50%;transform:translateY(-50%);background:none;border:none;cursor:pointer;color:var(--text-dim);font-size:14px;padding:0;line-height:1">✕</button>
          </div>
        </div>
      </div>
      <div id="historyTableWrap"></div>
      <div id="historyNoResults" style="display:none;text-align:center;padding:24px;color:var(--text-dim)">No results match your search.</div>
      <div class="row" style="margin-top:12px" id="historyPagination">
        <button class="btn sm" onclick="prevPage()">Prev</button>
        <button class="btn sm" onclick="nextPage()">Next</button>
        <span class="msg" id="pageInfo"></span>
      </div>
    </div>
  </div>

  <!-- ══════════════════════════════ STATS ══════════════════════════════ -->
  <div class="section" id="tab-stats">
    <div class="card">
      <div style="display:flex;justify-content:center;margin-bottom:14px">
        <div class="pill" style="font-size:13px;font-weight:700;letter-spacing:0.04em;padding:8px 24px;background:rgba(16,185,129,0.08);border-color:rgba(16,185,129,0.3);color:#10b981;text-transform:uppercase">
          Lifetime Confirmed
        </div>
      </div>
      <div class="import-stats">
        <div class="import-stat-card movies">
          <span class="import-stat-label">Movies:</span>
          <span class="import-stat-value" id="statMoviesTotal">—</span>
        </div>
        <div class="import-stat-card shows">
          <span class="import-stat-label">Shows:</span>
          <span class="import-stat-value" id="statShowsTotal">—</span>
        </div>
      </div>
      <div class="row" style="margin-bottom:14px">
        <button class="btn sm" onclick="checkImportsNow()">Check Now</button>
        <div style="margin-left:auto; display:flex; gap:8px; align-items:center;">
          <div class="field" style="min-width:200px">
            <select id="statsInstance" onchange="STATS_PAGE=0; refreshStats()">
              <option value="">All Instances</option>
            </select>
          </div>
          <div class="field" style="min-width:150px">
            <select id="statsType" onchange="STATS_PAGE=0; refreshStats()">
              <option value="">All Types</option>
            </select>
          </div>
          <div class="field" style="min-width:100px">
            <select id="statsLimit" onchange="syncPageSize('stats'); STATS_PAGE=0; refreshStats()">
              <option>10</option><option selected>25</option><option>50</option><option>100</option>
            </select>
          </div>
          <div class="field" style="min-width:180px;position:relative">
            <input type="text" id="statsSearch" placeholder="Search title…" oninput="filterStatsSearch()" style="padding-right:28px"/>
            <button id="statsSearchClear" onclick="clearStatsSearch()" style="display:none;position:absolute;right:6px;top:50%;transform:translateY(-50%);background:none;border:none;cursor:pointer;color:var(--text-dim);font-size:14px;padding:0;line-height:1">✕</button>
          </div>
        </div>
      </div>
      <div id="statsTableWrap"></div>
      <div id="statsNoResults" style="display:none;text-align:center;padding:24px;color:var(--text-dim)">No results match your search.</div>
      <div class="row" style="margin-top:12px" id="statsPagination">
        <button class="btn sm" onclick="prevStatsPage()">Prev</button>
        <button class="btn sm" onclick="nextStatsPage()">Next</button>
        <span class="msg" id="statsPageInfo"></span>
      </div>
    </div>
  </div>

  <!-- ══════════════════════════════ NOTIFICATIONS ══════════════════════════════ -->
  <div class="section" id="tab-notifications">
    <div class="grid cols2">
      <div class="card">
        <p class="section-label">Notifications</p>
        <div class="field">
          <label>Enable Notifications</label>
          <div class="toggle-wrap">
            <label class="toggle">
              <input type="checkbox" id="notify_enabled" onchange="syncNotifyUi(); markUnsaved('notifyMsg')"/>
              <span class="toggle-track"></span>
              <span class="toggle-thumb"></span>
            </label>
            <span class="help" id="notify_label">Disabled</span>
          </div>
          <div class="help">Send notifications via any Apprise-compatible service — Discord, Gotify, Ntfy, Pushover, Slack, and many more.</div>
        </div>
        <div class="field" id="notify_url_field" style="margin-top:12px">
          <label>Notification URL</label>
          <div class="key-wrap">
            <input type="password" id="notify_url" placeholder="e.g. discord://webhookid/token" oninput="markUnsaved('notifyMsg')"/>
            <button class="key-toggle" onclick="toggleNotifyUrl()" id="notifyUrlToggleBtn">Show</button>
          </div>
          <div class="help">Enter your Apprise-compatible notification URL. See <a href="https://github.com/caronc/apprise/wiki" target="_blank" style="color:var(--accent)">Apprise docs</a> for supported services and URL formats.</div>
        </div>
        <div id="notify_test_row" style="margin-top:12px;display:none">
          <button class="btn sm" onclick="testNotification()">Send Test</button>
          <span class="msg" id="notifyTestMsg" style="margin-left:8px"></span>
        </div>
      </div>

      <div class="card" id="notify_events_card">
        <p class="section-label">Notify On</p>
        <div class="field">
          <label>Sweep Complete</label>
          <div class="toggle-wrap">
            <label class="toggle">
              <input type="checkbox" id="notify_on_sweep_complete" onchange="markUnsaved('notifyMsg')"/>
              <span class="toggle-track"></span>
              <span class="toggle-thumb"></span>
            </label>
          </div>
          <div class="help">Fires when a sweep finishes — includes items searched and skipped.</div>
        </div>
        <div class="field" style="margin-top:12px">
          <label>Import Confirmed</label>
          <div class="toggle-wrap">
            <label class="toggle">
              <input type="checkbox" id="notify_on_import" onchange="markUnsaved('notifyMsg')"/>
              <span class="toggle-track"></span>
              <span class="toggle-thumb"></span>
            </label>
          </div>
          <div class="help">Fires when a searched item is confirmed imported into your library.</div>
        </div>
        <div class="field" style="margin-top:12px">
          <label>Error</label>
          <div class="toggle-wrap">
            <label class="toggle">
              <input type="checkbox" id="notify_on_error" onchange="markUnsaved('notifyMsg')"/>
              <span class="toggle-track"></span>
              <span class="toggle-thumb"></span>
            </label>
          </div>
          <div class="help">Fires when a sweep fails or an instance becomes unreachable.</div>
        </div>
      </div>
    </div>

    <div class="row" style="margin-top:16px">
      <button class="btn primary" onclick="saveNotifications()">Save Changes</button>
      <span class="msg" id="notifyMsg"></span>
    </div>
  </div>

  <!-- ══════════════════════════════ ADVANCED ══════════════════════════════ -->
  <div class="section" id="tab-advanced">
    <div class="grid">
      <div class="grid cols2">
        <div class="card">
          <p class="section-label">Backlog Nudges</p>
          <div class="help" style="margin-bottom:12px">Searches movies and episodes identified as missing. These searches are on top of your Max Per Run caps.</div>
          <p class="section-label" style="margin:0 0 8px">Radarr</p>
          <div class="field" style="margin-bottom:10px">
            <div class="toggle-wrap">
              <label class="toggle">
                <input type="checkbox" id="radarr_backlog_enabled" onchange="syncBacklogUi(); checkNewestAddedWarning(); markUnsaved('advMsg')"/>
                <span class="toggle-track"></span>
                <span class="toggle-thumb"></span>
              </label>
              <span class="help" id="radarr_backlog_label">Disabled</span>
            </div>
          </div>
          <div id="radarr_backlog_fields" style="opacity:0.35;pointer-events:none">
          <div class="grid cols2" style="gap:12px">
            <div class="field">
              <div class="tooltip-wrap">
                <label>Radarr Missing Max (Per Instance)</label>
                <span class="tooltip-icon">i<div class="tooltip-box">How many missing movies are searched per Radarr instance each sweep when backlog nudges are enabled. Unlike Cutoff Unmet searches which target items you already have at a lower quality, missing searches target items you have never downloaded. These can add up fast — if you have hundreds of missing movies and set this high combined with a short run interval you can generate a very large number of searches in a short time. Start at 1 and increase slowly.</div></span>
              </div>
              <input id="radarr_missing_max" type="number" min="1" oninput="markUnsaved('advMsg'); checkNewestAddedWarning()"/>
              <div class="help">Maximum missing movies searched per instance per run.</div>
            </div>
            <div class="field">
              <div class="tooltip-wrap">
                <label>Radarr Missing Added Days</label>
                <span class="tooltip-icon">i<div class="tooltip-box">Only search for missing items that were added to your library at least this many days ago. This prevents Nudgarr from immediately searching for something you just added and are still expecting to arrive naturally through your RSS feed. Setting this to 0 disables the filter entirely and makes all missing items immediately eligible regardless of when they were added.</div></span>
              </div>
              <input id="radarr_missing_added_days" type="number" min="0" oninput="markUnsaved('advMsg'); checkNewestAddedWarning()"/>
              <div class="help">Only search missing items added more than this many days ago.</div>
            </div>
          </div>
          </div>
          <div style="margin-top:14px">
          <p class="section-label" style="margin:0 0 8px">Sonarr</p>
          <div class="field" style="margin-bottom:10px">
            <div class="toggle-wrap">
              <label class="toggle">
                <input type="checkbox" id="sonarr_backlog_enabled" onchange="syncBacklogUi(); markUnsaved('advMsg')"/>
                <span class="toggle-track"></span>
                <span class="toggle-thumb"></span>
              </label>
              <span class="help" id="sonarr_backlog_label">Disabled</span>
            </div>
          </div>
          <div id="sonarr_backlog_fields" style="opacity:0.35;pointer-events:none">
          <div class="grid cols2" style="gap:12px">
            <div class="field">
              <div class="tooltip-wrap">
                <label>Sonarr Missing Max (Per Instance)</label>
                <span class="tooltip-icon">i<div class="tooltip-box">How many missing episodes are searched per Sonarr instance each sweep when backlog nudges are enabled. Unlike Cutoff Unmet searches which target episodes you already have at a lower quality, missing searches target episodes you have never downloaded. TV libraries tend to have far more missing episodes than movies — a single incomplete series can have hundreds of missing entries. Start at 1 and increase very slowly while watching your indexer's rate limits carefully.</div></span>
              </div>
              <input id="sonarr_missing_max" type="number" min="1" oninput="markUnsaved('advMsg')"/>
              <div class="help">Maximum missing episodes searched per instance per run.</div>
            </div>
          </div>
          </div>
          </div>
          <div class="amber-warn" style="margin-top:16px">
            <p class="amber-warn-title">USE WITH CAUTION</p>
            <p class="help amber-warn-body">Setting Missing Added Days to 0 disables the age filter — all missing items become eligible immediately. Combined with a high Missing Max and short run interval this can generate a very large number of searches in a short time, risking indexer rate limiting or bans. Nudgarr is not responsible for bans resulting from user-configured search behaviour.</p>
          </div>
          <div id="newestAddedWarnAdvanced" class="amber-warn amber-warn-collapsible">
            <p class="help amber-warn-body">⚠️ <strong>Newest Added</strong> is active and Radarr backlog nudges are enabled. Items closest to your Missing Added Days cutoff will be searched first.</p>
          </div>
        </div>

        <div class="card">
          <p class="section-label">Data Retention</p>
          <div class="field">
            <div class="tooltip-wrap">
              <label>Days to Keep</label>
              <span class="tooltip-icon">i<div class="tooltip-box">How many days Nudgarr keeps history and stats entries before pruning them on the next sweep. This applies to both the History tab and the Stats tab. Lifetime Movies and Shows totals are never affected by pruning — only the individual entry records are removed. Setting to 0 disables pruning entirely and entries are kept forever.</div></span>
            </div>
            <input id="state_retention_days" type="number" min="0" oninput="markUnsaved('advMsg')"/>
            <div class="help">Prunes history and stats entries older than this. Lifetime totals are not affected. 0 disables.</div>
          </div>
          <div class="hr"></div>
          <p class="section-label">Stats</p>
          <div class="field">
            <label>Import Check Delay (Minutes)</label>
            <input id="import_check_minutes" type="number" min="1" oninput="markUnsaved('advMsg')"/>
            <div class="help">Minutes to wait before checking if a searched item was successfully imported. Confirmed imports appear in the Stats tab.</div>
          </div>
          <div class="hr"></div>
          <p class="section-label">Security</p>
          <div class="field">
            <label>Require Login</label>
            <div class="toggle-wrap">
              <label class="toggle">
                <input type="checkbox" id="auth_enabled" onchange="syncAuthUi(); markUnsaved('advMsg')"/>
                <span class="toggle-track"></span>
                <span class="toggle-thumb"></span>
              </label>
              <span class="help" id="auth_label">Enabled</span>
            </div>
            <div class="help">When disabled, anyone on your network can access the UI.</div>
          </div>
          <div class="field" style="margin-top:16px">
            <label>Session Timeout (Minutes)</label>
            <input id="auth_session_minutes" type="number" min="1" oninput="markUnsaved('advMsg')"/>
            <div class="help">Minutes of inactivity before requiring re-login.</div>
          </div>
          <div class="hr"></div>
          <p class="section-label">UI Preferences</p>
          <div class="field">
            <label>Show Support Link</label>
            <div class="toggle-wrap">
              <label class="toggle">
                <input type="checkbox" id="show_support_link" onchange="syncSupportLinkUi(); markUnsaved('advMsg')"/>
                <span class="toggle-track"></span>
                <span class="toggle-thumb"></span>
              </label>
              <span class="help" id="support_link_label">Shown</span>
            </div>
            <div class="help">Toggle off to hide.</div>
          </div>
        </div>
      </div>

      <div class="row" style="margin-top:16px">
        <button class="btn primary" onclick="saveAdvanced()">Save Changes</button>
        <span class="msg" id="advMsg"></span>
      </div>

      <div class="card danger-section" style="margin-bottom:12px">
        <p class="section-label" style="color:#fca5a5">Danger Zone</p>
        <p class="help" style="margin:0 0 12px;color:#fca5a5">These actions are irreversible and cannot be undone.</p>
        <div class="row" style="flex-wrap:wrap;gap:8px">
          <button class="btn sm danger" onclick="resetConfig()">Reset Config</button>
        </div>
        <div class="row" style="flex-wrap:wrap;gap:8px;margin-top:8px">
          <button class="btn sm danger" onclick="clearState()">Clear History</button>
          <button class="btn sm danger" onclick="clearStats()">Clear Stats</button>
        </div>
      </div>

      <div class="card">
        <p class="section-label">Support &amp; Diagnostics</p>
        <p class="help" style="margin:0 0 12px">Backup your data or grab a diagnostic to share on GitHub.</p>
        <div class="row" style="flex-wrap:wrap;gap:8px;margin-bottom:10px">
          <button class="btn sm" onclick="downloadFile('config')">Download Config</button>
          <button class="btn sm" onclick="downloadFile('state')">Download History</button>
          <button class="btn sm" onclick="downloadDiagnostic()">Download Diagnostic</button>
          <a href="https://github.com/MMagTech/nudgarr/issues/new" target="_blank" class="btn sm" style="text-decoration:none">Open Issue ↗</a>
        </div>
        <span class="msg" id="diagMsg" style="margin-top:8px;display:block"></span>
        <div id="diagBox" class="diag-box" style="display:none"></div>
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

  <!-- ══ Confirm Modal ══ -->
  <div class="modal-backdrop" id="confirmModal" style="display:none">
    <div class="modal" onclick="event.stopPropagation()" style="max-width:380px">
      <h2 id="confirmTitle">Confirm</h2>
      <p class="help" id="confirmMsg" style="margin:0 0 20px"></p>
      <div class="row" style="justify-content:flex-end">
        <button class="btn sm" onclick="confirmResolve(false)">Cancel</button>
        <button class="btn sm primary" id="confirmOkBtn" onclick="confirmResolve(true)">Confirm</button>
      </div>
    </div>
  </div>

  <!-- ══ Alert Modal ══ -->
  <div class="modal-backdrop" id="alertModal" style="display:none">
    <div class="modal" onclick="event.stopPropagation()" style="max-width:380px">
      <p class="help" id="alertMsg" style="margin:0 0 20px"></p>
      <div class="row" style="justify-content:flex-end">
        <button class="btn sm primary" onclick="el('alertModal').style.display='none'">OK</button>
      </div>
    </div>
  </div>

  <!-- ══ What's New Modal ══ -->
  <div class="modal-backdrop" id="whatsNewModal" style="display:none">
    <div class="modal" onclick="event.stopPropagation()" style="max-width:520px">
      <h2 style="margin:0 0 4px">What's New in v2.5.0</h2>
      <p class="help" style="margin:0 0 18px;color:var(--muted)">Here's what changed since your last visit.</p>
      <div style="display:flex;flex-direction:column;gap:10px;max-height:380px;overflow-y:auto;padding-right:4px">
        <div style="padding:12px;background:var(--surface);border:1px solid var(--border);border-radius:10px">
          <div style="font-weight:600;font-size:13px;margin-bottom:4px">🎯 Sample Modes</div>
          <div class="help">Four modes now available: <strong>Random</strong>, <strong>Alphabetical</strong>, <strong>Oldest Added</strong>, and <strong>Newest Added</strong>. Find them in Settings → Search Behaviour.</div>
        </div>
        <div style="padding:12px;background:var(--surface);border:1px solid var(--border);border-radius:10px">
          <div style="font-weight:600;font-size:13px;margin-bottom:4px">📊 Stats — Lifetime Confirmed pill</div>
          <div class="help">A combined lifetime total now appears above the Movies and Shows cards on the Stats tab.</div>
        </div>
        <div style="padding:12px;background:var(--surface);border:1px solid var(--border);border-radius:10px">
          <div style="font-weight:600;font-size:13px;margin-bottom:4px">⚠️ Newest Added warning</div>
          <div class="help">Selecting Newest Added mode now shows an amber warning when backlog nudges are enabled, as it may conflict with Missing Added Days.</div>
        </div>
        <div style="padding:12px;background:var(--surface);border:1px solid var(--border);border-radius:10px">
          <div style="font-weight:600;font-size:13px;margin-bottom:4px">🍺 Support link</div>
          <div class="help">A Buy Me a Coffee link now appears in the header. Toggle it off anytime in Advanced → UI Preferences.</div>
        </div>
      </div>
      <div class="row" style="justify-content:flex-end;margin-top:20px">
        <button class="btn sm primary" onclick="dismissWhatsNew()">Got it</button>
      </div>
    </div>
  </div>

  <!-- ══ Onboarding Modal ══ -->
  <div class="modal-backdrop" id="onboardingModal" style="display:none">
    <div class="modal" onclick="event.stopPropagation()" style="max-width:480px">
      <div id="onboardingContent"></div>
      <div style="display:flex; align-items:center; justify-content:space-between; margin-top:24px">
        <div style="display:flex; gap:6px" id="onboardingDots"></div>
        <div style="display:flex; gap:8px">
          <button class="btn sm" id="onboardingPrev" onclick="onboardingStep(-1)">Back</button>
          <button class="btn sm primary" id="onboardingNext" onclick="onboardingStep(1)">Next</button>
        </div>
      </div>
    </div>
  </div>

<script>
let CFG = null;
let PAGE = 0;
let STATS_PAGE = 0;
let ALL_INSTANCES = [];
let confirmResolve = null;
let ACTIVE_TAB = 'instances';
let HISTORY_SORT = { col: 'last_searched', dir: 'desc' };
let STATS_SORT = { col: 'imported_ts', dir: 'desc' };

async function showConfirm(title, msg, okLabel = 'Confirm', danger = false) {
  el('confirmTitle').textContent = title;
  el('confirmMsg').textContent = msg;
  el('confirmOkBtn').textContent = okLabel;
  el('confirmOkBtn').className = danger ? 'btn sm danger' : 'btn sm primary';
  el('confirmModal').style.display = 'flex';
  return new Promise(resolve => { confirmResolve = (v) => { el('confirmModal').style.display = 'none'; resolve(v); }; });
}

function showAlert(msg) {
  el('alertMsg').textContent = msg;
  el('alertModal').style.display = 'flex';
}

// ── Onboarding Walkthrough ──
const ONBOARDING_STEPS = [
  {
    title: "Welcome to Nudgarr",
    body: `Nudgarr searches your Radarr and Sonarr Wanted lists automatically — finding items that need a quality upgrade or haven't been grabbed yet — so you don't have to.
<br><br>
This quick walkthrough covers the key things to know before your first run. It is key to understand these settings to prevent an indexer ban.`
  },
  {
    title: "Step 1 — Add Your Instances",
    body: `Start on the <strong>Instances tab</strong>. Add each of your Radarr and Sonarr servers with their URL and API key.
<br><br>
You can add multiple instances — Nudgarr will search across all of them each run. Note that settings like Max Per Run apply <strong>per instance</strong> — if you have two Radarr instances set to 5, that's up to 10 movie searches per sweep. Use the <strong>Test Connections</strong> button to confirm everything is connected before moving on.`
  },
  {
    title: "Step 2 — Scheduler",
    body: `The Scheduler controls when Nudgarr automatically runs sweeps.
<br><br>
<strong>Automatic Sweeps</strong><br>
Off by default — Nudgarr will not run until you enable it. You can still trigger a sweep at any time by clicking <strong>Run Now</strong>. This is the recommended approach until you are confident in your settings.
<br><br>
<strong>Run Interval</strong><br>
How often the scheduler fires when enabled. Default is every 6 hours. Start conservative and adjust based on the size of your library and how active your indexers are.`
  },
  {
    title: "Step 3 — Search Behavior",
    body: `These settings control what gets searched and how often.
<br><br>
<strong>Max Per Run</strong><br>
How many items are searched <strong>per instance</strong> each run. If you have two Radarr instances set to 5, that's up to 10 movie searches per sweep. Starts at 1 — increase slowly as you get comfortable with how Nudgarr behaves.
<br><br>
<strong>Cooldown</strong><br>
How long Nudgarr waits before searching the same item again. Default is 48 hours. Do not lower this aggressively — repeated searches for the same item in a short window is one of the fastest ways to get banned from an indexer.
<br><br>
<strong>Sample Mode</strong><br>
Controls which eligible items are picked each run. <strong>Random</strong> gives even library coverage. <strong>Alphabetical</strong> works through your library from A to Z. <strong>Oldest Added</strong> prioritises items you've had longest. <strong>Newest Added</strong> targets recently added items — use with caution if backlog nudges are enabled.`
  },
  {
    title: "Step 4 — Throttling",
    body: `These settings control how fast Nudgarr communicates with your Radarr and Sonarr instances during a run.
<br><br>
<strong>Batch Size</strong><br>
How many search commands are sent at once. Default is 1. Keeping this low reduces the chance of overwhelming your indexer.
<br><br>
<strong>Sleep</strong><br>
How long Nudgarr pauses between batches. Default is 5 seconds. A longer pause is more respectful of your indexer's rate limits.
<br><br>
<strong>Jitter</strong><br>
Adds a small random delay on top of the sleep time to make search patterns less predictable. Helps avoid triggering automated rate limit detection.`
  },
  {
    title: "Step 5 — History & Stats",
    body: `Nudgarr keeps track of everything it does so you can see exactly what's happening.
<br><br>
<strong>History</strong><br>
A log of every item that has been searched, when it was last searched, and how many times. Use this to verify Nudgarr is behaving as expected after your first few runs.
<br><br>
<strong>Stats</strong><br>
Tracks confirmed imports — items that were searched by Nudgarr and later successfully imported. Movies and Shows totals are lifetime counters that persist even if you clear the stats table.
<br><br>
Both tabs support <strong>title search</strong> — type a show or movie name to filter the table instantly. Use the instance dropdown alongside it to narrow results further.`
  },
  {
    title: "Step 6 — Notifications",
    body: `Nudgarr can notify you when sweeps complete, imports are confirmed, or an instance becomes unreachable.
<br><br>
Add your Apprise-compatible URL, choose which events to be notified on, and use <strong>Send Test</strong> to confirm it's working before enabling. Supports Discord, Gotify, Ntfy, Pushover, Slack, and more.`
  },
  {
    title: "Step 7 — Advanced & Backlog Nudges",
    body: `The <strong>Advanced tab</strong> contains settings for backlog nudges, data retention, and security.
<br><br>
<strong>Backlog Nudges</strong> — Off by default. When enabled, searches for missing movies and episodes that have never been grabbed, going beyond just cutoff upgrades.<br><br>
<strong>Missing Max (Per Instance)</strong> — How many missing items to search per instance per run. Keep this low.<br><br>
<strong>Missing Added Days</strong> — Only search for items added to your library at least this many days ago. Prevents searching for things you just added and are still expecting to arrive naturally.<br><br>
<strong>Data Retention</strong> — How many days Nudgarr keeps history and stats entries before pruning. Lifetime totals are never affected. Default is 180 days.<br><br>
<strong>Import Check</strong> — Nudgarr periodically checks whether items it previously searched were successfully imported into your library. This is what feeds the Stats screen. Default is every 120 minutes.<br><br>
<strong>Security</strong> — Session timeout controls how long before an inactive login is automatically signed out. Default is 30 minutes.
<br><br>
⚠️ <span style="color:#fbbf24;font-weight:600">Backlog nudges can generate a lot of searches very quickly.</span> Start with a low cap and watch your indexer's rate limits carefully.`
  },
  {
    title: "You're Ready",
    body: `You're all set. Here's the recommended way to start:
<br><br>
1. Add your instances and test connections<br>
2. Review your settings — keep them conservative to start<br>
3. Hit <strong>Run Now</strong> to trigger your first sweep manually<br>
4. Check the <strong>History tab</strong> to see what was searched<br>
5. If everything looks right, enable the scheduler<br>
6. Gradually increase Max Per Run as you get comfortable
<br><br>
Nudgarr is designed to work quietly in the background — not to hammer your indexers. Start slow and let it earn your trust.
<br><br>
<span style="color:var(--muted);font-size:12px">If Nudgarr is useful to you, the 🍺 support link in the header is a nice way to say thanks. You can hide it anytime in Advanced → UI Preferences.</span>`
  }
];

let _obStep = 0;

function renderOnboardingStep() {
  const step = ONBOARDING_STEPS[_obStep];
  const total = ONBOARDING_STEPS.length;
  el('onboardingContent').innerHTML = `
    <h2 style="font-size:16px;font-weight:700;margin:0 0 12px">${step.title}</h2>
    <p class="help" style="line-height:1.7;margin:0">${step.body}</p>
  `;
  // Dots
  el('onboardingDots').innerHTML = ONBOARDING_STEPS.map((_, i) =>
    `<div style="width:7px;height:7px;border-radius:50%;background:${i===_obStep ? 'var(--accent)' : 'var(--border)'}"></div>`
  ).join('');
  el('onboardingPrev').style.display = _obStep === 0 ? 'none' : '';
  el('onboardingNext').textContent = _obStep === total - 1 ? 'Got it' : 'Next';
}

async function onboardingStep(dir) {
  const total = ONBOARDING_STEPS.length;
  if (dir === 1 && _obStep === total - 1) {
    // Finished
    el('onboardingModal').style.display = 'none';
    await api('/api/onboarding/complete', {method: 'POST'});
    if (CFG) { CFG.onboarding_complete = true; CFG.last_seen_version = el('ver').textContent; }
    return;
  }
  _obStep = Math.max(0, Math.min(total - 1, _obStep + dir));
  renderOnboardingStep();
}

function maybeShowOnboarding() {
  if (!CFG || CFG.onboarding_complete) return;
  _obStep = 0;
  renderOnboardingStep();
  el('onboardingModal').style.display = 'flex';
}

function showTab(name) {
  ACTIVE_TAB = name;
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
  const current = document.querySelector('.section.active');
  const next = document.getElementById('tab-' + name);
  if (current && current !== next) {
    current.classList.add('leaving');
    setTimeout(() => {
      current.classList.remove('active', 'leaving');
      next.classList.add('active');
      _onTabShown(name);
    }, 100);
  } else {
    document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
    next.classList.add('active');
    _onTabShown(name);
  }
}

function _onTabShown(name) {
  if (name === 'history') {
    clearHistorySearch();
    if (!el('historyTableWrap').querySelector('table')) {
      el('historyTableWrap').innerHTML = `
        <table><thead><tr>
          <th class="sortable ${HISTORY_SORT.col==='title' ? 'sort-'+HISTORY_SORT.dir : ''}" data-col="title" onclick="sortHistory('title')">Title</th>
          <th class="sortable ${HISTORY_SORT.col==='sweep_type' ? 'sort-'+HISTORY_SORT.dir : ''}" data-col="sweep_type" onclick="sortHistory('sweep_type')">Type</th>
          <th class="sortable ${HISTORY_SORT.col==='last_searched' ? 'sort-'+HISTORY_SORT.dir : ''}" data-col="last_searched" onclick="sortHistory('last_searched')">Last Searched</th>
          <th class="sortable ${HISTORY_SORT.col==='eligible_again' ? 'sort-'+HISTORY_SORT.dir : ''}" data-col="eligible_again" onclick="sortHistory('eligible_again')">Eligible Again</th>
        </tr></thead><tbody></tbody></table>`;
    }
    refreshHistory();
  }
  if (name === 'stats') {
    clearStatsSearch();
    if (!el('statsTableWrap').querySelector('table')) {
      el('statsTableWrap').innerHTML = `
        <table><thead><tr>
          <th class="sortable ${STATS_SORT.col==='title' ? 'sort-'+STATS_SORT.dir : ''}" data-col="title" onclick="sortStats('title')">Title</th>
          <th class="sortable ${STATS_SORT.col==='instance' ? 'sort-'+STATS_SORT.dir : ''}" data-col="instance" onclick="sortStats('instance')">Instance</th>
          <th class="sortable ${STATS_SORT.col==='type' ? 'sort-'+STATS_SORT.dir : ''}" data-col="type" onclick="sortStats('type')">Type</th>
          <th class="sortable ${STATS_SORT.col==='searched_ts' ? 'sort-'+STATS_SORT.dir : ''}" data-col="searched_ts" onclick="sortStats('searched_ts')">Searched</th>
          <th class="sortable ${STATS_SORT.col==='imported_ts' ? 'sort-'+STATS_SORT.dir : ''}" data-col="imported_ts" onclick="sortStats('imported_ts')">Imported</th>
        </tr></thead><tbody></tbody></table>`;
    }
    refreshStats();
  }
  if (name === 'advanced') fillAdvanced();
  if (name === 'notifications') fillNotifications();
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

function updateStatusPill(schedulerEnabled) {
  if (schedulerEnabled) {
    el('dot-dryrun').style.background = 'var(--ok)';
    el('txt-dryrun').textContent = 'AUTO';
  } else {
    el('dot-dryrun').style.background = '#a78bfa';
    el('txt-dryrun').textContent = 'MANUAL';
  }
}

async function loadAll() {
  CFG = await api('/api/config');
  const st = await api('/api/status');
  el('ver').textContent = st.version;
  el('lastRun').textContent = fmtTime(st.last_run_utc);
  el('nextRun').textContent = (CFG && CFG.scheduler_enabled) ? fmtTime(st.next_run_utc) : 'Manual';
  updateStatusPill(CFG.scheduler_enabled);

  // Show logout button when auth is enabled
  const lb = el('logoutBtn');
  if (lb) lb.style.display = CFG.auth_enabled !== false ? 'inline-flex' : 'none';

  // Support link
  const sl = el('supportLink');
  if (sl) sl.style.display = CFG.show_support_link !== false ? 'inline-flex' : 'none';

  // Build instance list
  ALL_INSTANCES = [];
  (CFG.instances?.radarr || []).forEach(i => ALL_INSTANCES.push({key: i.name+'|'+i.url.replace(/\/$/,''), name: i.name, app:'radarr'}));
  (CFG.instances?.sonarr || []).forEach(i => ALL_INSTANCES.push({key: i.name+'|'+i.url.replace(/\/$/,''), name: i.name, app:'sonarr'}));

  renderInstances('radarr');
  renderInstances('sonarr');
  fillSettings();
  fillAdvanced();
  fillNotifications();
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

async function saveModal() {
  const name = el('modalName').value.trim();
  const url = el('modalUrl').value.trim();
  const key = el('modalKey').value.trim();
  if (!name || !url || !key) { showAlert('All fields are required.'); return; }
  CFG.instances = CFG.instances || {radarr:[], sonarr:[]};
  if (MODAL_IDX >= 0) {
    CFG.instances[MODAL_KIND][MODAL_IDX] = {name, url, key};
  } else {
    CFG.instances[MODAL_KIND].push({name, url, key});
  }
  closeModalDirect();
  renderInstances(MODAL_KIND);
  el('saveMsg').textContent = MODAL_IDX >= 0 ? 'Unsaved Changes' : 'Unsaved Changes';
  el('saveMsg').className = 'msg unsaved';

  // Silently test the new/edited instance and update its dot
  const idx = MODAL_IDX >= 0 ? MODAL_IDX : CFG.instances[MODAL_KIND].length - 1;
  const dot = el(`sdot-${MODAL_KIND}-${idx}`);
  if (dot) dot.className = 'status-dot checking';
  try {
    const out = await api('/api/test', {method:'POST'});
    const results = out.results[MODAL_KIND] || [];
    const match = results.find(r => r.name === name);
    if (dot && match) dot.className = 'status-dot ' + (match.ok ? 'ok' : 'bad');
  } catch(e) {
    if (dot) dot.className = 'status-dot bad';
  }
}

function addInstance(kind) {
  openModal(kind, -1);
}

function editInstance(kind, idx) {
  openModal(kind, idx);
}

async function deleteInstance(kind, idx) {
  if (!await showConfirm('Delete Instance', 'Are you sure you want to delete this instance?', 'Delete', true)) return;
  CFG.instances[kind].splice(idx, 1);
  renderInstances(kind);
  el('saveMsg').textContent = 'Unsaved Changes';
  el('saveMsg').className = 'msg unsaved';
}

function fadeMsg(id) {
  const el_ = el(id);
  clearTimeout(el_._fadeTimer);
  el_.classList.remove('fade');
  el_._fadeTimer = setTimeout(() => el_.classList.add('fade'), 4000);
}

async function saveAll() {
  try {
    await api('/api/config', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(CFG)});
    await loadAll();
    await new Promise(r => setTimeout(r, 400));
    el('saveMsg').textContent = 'Saved'; el('saveMsg').className = 'msg ok'; fadeMsg('saveMsg');
  } catch(e) {
    el('saveMsg').textContent = 'Save failed: ' + e.message; el('saveMsg').className = 'msg err';
  }
}

async function testConnections() {
  el('testResults').style.display = 'none';
  el('testResultsInner').innerHTML = '';

  document.querySelectorAll('.status-dot').forEach(d => { d.className = 'status-dot checking'; });

  try {
    const [out] = await Promise.all([
      api('/api/test', {method:'POST'}),
      new Promise(r => setTimeout(r, 2000))
    ]);
    const allResults = [...(out.results.radarr||[]), ...(out.results.sonarr||[])];

    ['radarr','sonarr'].forEach(kind => {
      (out.results[kind]||[]).forEach((r, idx) => {
        const dot = el(`sdot-${kind}-${idx}`);
        if (dot) dot.className = 'status-dot ' + (r.ok ? 'ok' : 'bad');
      });
    });

    const failures = allResults.filter(r => !r.ok);
    if (failures.length > 0) {
      el('testResultsInner').innerHTML = failures.map(r => `
        <div class="test-card bad">
          <span class="test-icon">✗</span>
          <div>
            <div class="tc-name">${escapeHtml(r.name)}</div>
            <div class="tc-detail">${r.error && r.error.length < 80 ? escapeHtml(r.error) : 'Could not connect — check the URL and API key'}</div>
          </div>
        </div>
      `).join('');
      el('testResults').style.display = 'block';
      el('testResults').style.opacity = '1';
      setTimeout(() => {
        el('testResults').style.transition = 'opacity 0.8s ease';
        el('testResults').style.opacity = '0';
        setTimeout(() => {
          el('testResults').style.display = 'none';
          el('testResults').style.transition = '';
          el('testResults').style.opacity = '1';
        }, 800);
      }, 4000);
    }

  } catch(e) {
    el('testResultsInner').innerHTML = `<p class="help" style="color:var(--bad)">Test failed: ${escapeHtml(e.message)}</p>`;
    el('testResults').style.display = 'block';
    document.querySelectorAll('.status-dot').forEach(d => { d.className = 'status-dot bad'; });
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
  el('run_interval_minutes').value = Math.round((CFG.run_interval_minutes || 360) / 60);
  el('cooldown_hours').value = CFG.cooldown_hours;
  el('sample_mode').value = CFG.sample_mode || 'random';
  el('radarr_max_movies_per_run').value = CFG.radarr_max_movies_per_run;
  el('sonarr_max_episodes_per_run').value = CFG.sonarr_max_episodes_per_run;
  el('batch_size').value = CFG.batch_size;
  el('sleep_seconds').value = CFG.sleep_seconds;
  el('jitter_seconds').value = CFG.jitter_seconds;
  syncSchedulerUi();
  el('setMsg').textContent = ''; el('setMsg').className = 'msg';
  checkCooldownWarning();
  checkNewestAddedWarning();
}

async function saveSettings() {
  try {
    CFG.scheduler_enabled = el('scheduler_enabled').checked;
    CFG.run_interval_minutes = parseInt(el('run_interval_minutes').value || '6', 10) * 60;
    CFG.cooldown_hours = parseInt(el('cooldown_hours').value || '48', 10);
    CFG.sample_mode = el('sample_mode').value;
    CFG.radarr_max_movies_per_run = parseInt(el('radarr_max_movies_per_run').value || '25', 10);
    CFG.sonarr_max_episodes_per_run = parseInt(el('sonarr_max_episodes_per_run').value || '25', 10);
    CFG.batch_size = parseInt(el('batch_size').value || '20', 10);
    CFG.sleep_seconds = parseFloat(el('sleep_seconds').value || '3');
    CFG.jitter_seconds = parseFloat(el('jitter_seconds').value || '2');
    await api('/api/config', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(CFG)});
    await loadAll();
    await new Promise(r => setTimeout(r, 400));
    el('setMsg').textContent = 'Saved'; el('setMsg').className = 'msg ok'; fadeMsg('setMsg');
    fadeNewestAddedWarnings();
  } catch(e) {
    el('setMsg').textContent = 'Save failed: ' + e.message; el('setMsg').className = 'msg err';
  }
}

// ── Cooldown warning ──
let _warnFlashTimer = null;
function checkCooldownWarning() {
  const intervalHours = parseFloat(el('run_interval_minutes').value || '6');
  const cooldown = parseFloat(el('cooldown_hours').value || '48');
  const warn = el('cooldownWarnMsg');
  if (!warn) return;
  const shouldWarn = cooldown > 0 && cooldown < intervalHours;
  if (shouldWarn) {
    if (warn.textContent === '') {
      warn.textContent = '⚠️ Cooldown < run interval — repeated searches likely';
      warn.className = 'warn-flash';
      if (_warnFlashTimer) clearTimeout(_warnFlashTimer);
      _warnFlashTimer = setTimeout(() => { warn.className = 'warn-steady'; }, 3000);
    }
  } else {
    warn.textContent = '';
    warn.className = '';
    if (_warnFlashTimer) { clearTimeout(_warnFlashTimer); _warnFlashTimer = null; }
  }
}

// ── Newest Added warning ──
function checkNewestAddedWarning() {
  const mode = el('sample_mode') ? el('sample_mode').value : (CFG ? CFG.sample_mode : '');
  const radarrBacklog = el('radarr_backlog_enabled') ? el('radarr_backlog_enabled').checked : (CFG ? !!CFG.radarr_backlog_enabled : false);
  const missingDaysEl = el('radarr_missing_added_days');
  const missingDays = missingDaysEl ? parseInt(missingDaysEl.value || '0', 10) : (CFG ? (CFG.radarr_missing_added_days ?? 0) : 0);
  const isNewest = mode === 'newest_added';
  const showWarn = isNewest && radarrBacklog && missingDays > 0;
  const warnSettings = el('newestAddedWarnSettings');
  const warnAdv = el('newestAddedWarnAdvanced');
  const helpText = el('sampleModeHelp');
  [warnSettings, warnAdv].forEach(w => {
    if (!w) return;
    clearTimeout(w._warnFade);
    if (showWarn) {
      w.style.opacity = '';
      w.style.transition = '';
      w.classList.add('visible');
    } else {
      w.style.opacity = '';
      w.style.transition = '';
      w.classList.remove('visible');
    }
  });
  if (helpText) helpText.style.display = '';
}

function fadeNewestAddedWarnings() {
  [el('newestAddedWarnSettings'), el('newestAddedWarnAdvanced')].forEach(w => {
    if (!w || !w.classList.contains('visible')) return;
    clearTimeout(w._warnFade);
    w.style.transition = 'opacity 0.5s ease';
    w.style.opacity = '0';
    w._warnFade = setTimeout(() => {
      w.style.opacity = '';
      w.style.transition = '';
      w.classList.remove('visible');
    }, 500);
  });
}

// ── What's New modal ──
async function dismissWhatsNew() {
  el('whatsNewModal').style.display = 'none';
  await api('/api/whats-new/dismiss', {method: 'POST'});
  if (CFG) CFG.last_seen_version = el('ver').textContent;
}

function maybeShowWhatsNew() {
  if (!CFG) return;
  if (!CFG.onboarding_complete) return;
  const lastSeen = CFG.last_seen_version || '';
  const current = el('ver').textContent || '';
  if (current && lastSeen !== current) {
    el('whatsNewModal').style.display = 'flex';
  }
}

// ── Support link UI ──
function syncSupportLinkUi() {
  const show = el('show_support_link') ? el('show_support_link').checked : true;
  const sl = el('supportLink');
  if (sl) sl.style.display = show ? 'inline-flex' : 'none';
  const lbl = el('support_link_label');
  if (lbl) lbl.textContent = show ? 'Shown' : 'Hidden';
}

// ── History tab ──
async function refreshHistory() {
  try {
    const sum = await api('/api/state/summary');

    // KPI pills — per instance counts
    const instPills = ALL_INSTANCES.map(inst => {
      const appSt = sum.per_instance || {};
      const count = (appSt[inst.app] && appSt[inst.app][inst.key]) || 0;
      return `<div class="pill"><span style="color:var(--text-dim);font-size:11px">${escapeHtml(inst.name)}:</span><span style="color:var(--text);font-weight:400;font-size:13px">${count}</span></div>`;
    }).join('');
    el('kpis').innerHTML = instPills +
      `<div class="pill"><span style="color:var(--text-dim);font-size:11px">History File:</span><span style="color:var(--text);font-weight:400;font-size:13px">${sum.file_size_human}</span></div>` +
      `<div class="pill"><span style="color:var(--text-dim);font-size:11px">Retention:</span><span style="color:var(--text);font-weight:400;font-size:13px">${sum.retention_days} days</span></div>`;

    // Build instance dropdown from ALL_INSTANCES (has correct app info)
    // Store index into ALL_INSTANCES as the option value to avoid any key parsing issues
    const sel = el('historyInstance');
    const prevIdx = sel.value;
    sel.innerHTML = '<option value="">All Instances</option>' + ALL_INSTANCES.map((inst, idx) =>
      `<option value="${idx}">${escapeHtml(inst.name)}</option>`
    ).join('');
    if (prevIdx && (prevIdx === '' || parseInt(prevIdx) < ALL_INSTANCES.length)) sel.value = prevIdx;

    const selVal = sel.value;
    const selected = selVal !== '' ? ALL_INSTANCES[parseInt(selVal)] : null;
    const instKey = selected ? selected.key : '';
    const appName = selected ? selected.app : '';

    const limit = parseInt(el('historyLimit').value || '25', 10);
    const items = await api(`/api/state/items?app=${encodeURIComponent(appName)}&instance=${encodeURIComponent(instKey)}&offset=${PAGE*limit}&limit=${limit}`);

    el('pageInfo').textContent = `Page ${PAGE+1} · ${items.items.length} of ${items.total}`;
    el('historyPagination').style.display = items.total > 0 ? 'flex' : 'none';

    const sorted = sortItems(items.items, HISTORY_SORT.col, HISTORY_SORT.dir);
    const rows = sorted.map(it => `
      <tr>
        <td>${escapeHtml(it.title || it.key)}</td>
        <td>${it.sweep_type ? `<span class="pill" style="font-size:11px;padding:2px 8px">${escapeHtml(it.sweep_type)}</span>` : ''}</td>
        <td>${escapeHtml(fmtTime(it.last_searched))}</td>
        <td>${escapeHtml(fmtTime(it.eligible_again))}</td>
      </tr>
    `).join('');

    el('historyTableWrap').innerHTML = `
      <table>
        <thead><tr>
          <th class="sortable ${HISTORY_SORT.col==='title' ? 'sort-'+HISTORY_SORT.dir : ''}" data-col="title" onclick="sortHistory('title')">Title</th>
          <th class="sortable ${HISTORY_SORT.col==='sweep_type' ? 'sort-'+HISTORY_SORT.dir : ''}" data-col="sweep_type" onclick="sortHistory('sweep_type')">Type</th>
          <th class="sortable ${HISTORY_SORT.col==='last_searched' ? 'sort-'+HISTORY_SORT.dir : ''}" data-col="last_searched" onclick="sortHistory('last_searched')">Last Searched</th>
          <th class="sortable ${HISTORY_SORT.col==='eligible_again' ? 'sort-'+HISTORY_SORT.dir : ''}" data-col="eligible_again" onclick="sortHistory('eligible_again')">Eligible Again</th>
        </tr></thead>
        <tbody>${rows || '<tr><td colspan="4" class="help" style="text-align:center;padding:20px">No history yet.</td></tr>'}</tbody>
      </table>
    `;
    applySortIndicators('#historyTableWrap table', HISTORY_SORT);
  } catch(e) {
    el('historyTableWrap').innerHTML = `<p class="help" style="color:var(--bad)">Failed to load history: ${escapeHtml(e.message)}</p>`;
  }
}

function sortHistory(col) {
  if (HISTORY_SORT.col === col) {
    HISTORY_SORT.dir = HISTORY_SORT.dir === 'asc' ? 'desc' : 'asc';
  } else {
    HISTORY_SORT.col = col;
    HISTORY_SORT.dir = 'asc';
  }
  PAGE = 0;
  refreshHistory();
}

function sortStats(col) {
  if (STATS_SORT.col === col) {
    STATS_SORT.dir = STATS_SORT.dir === 'asc' ? 'desc' : 'asc';
  } else {
    STATS_SORT.col = col;
    STATS_SORT.dir = 'asc';
  }
  STATS_PAGE = 0;
  refreshStats();
}

function applySortIndicators(tableSelector, sortState) {
  document.querySelectorAll(`${tableSelector} th.sortable`).forEach(th => {
    th.classList.remove('sort-asc', 'sort-desc');
    if (th.dataset.col === sortState.col) {
      th.classList.add(sortState.dir === 'asc' ? 'sort-asc' : 'sort-desc');
    }
  });
}

function sortItems(items, col, dir) {
  return [...items].sort((a, b) => {
    const av = (a[col] || '').toString().toLowerCase();
    const bv = (b[col] || '').toString().toLowerCase();
    return dir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
  });
}

function prevPage() { if (PAGE > 0) { PAGE--; refreshHistory(); } }
function nextPage() { PAGE++; refreshHistory(); }

// ── Page size memory (shared across History and Stats) ──
function syncPageSize(source) {
  const val = el(source === 'history' ? 'historyLimit' : 'statsLimit').value;
  const other = el(source === 'history' ? 'statsLimit' : 'historyLimit');
  if (other && other.value !== val) other.value = val;
}

// ── History search ──
function filterHistorySearch() {
  const q = el('historySearch').value.trim().toLowerCase();
  el('historySearchClear').style.display = q ? '' : 'none';
  const rows = el('historyTableWrap').querySelectorAll('tbody tr');
  let visible = 0;
  rows.forEach(row => {
    const title = row.cells[0]?.textContent.toLowerCase() || '';
    const show = !q || title.includes(q);
    row.style.display = show ? '' : 'none';
    if (show) visible++;
  });
  const noRes = el('historyNoResults');
  if (noRes) noRes.style.display = (!visible && q) ? '' : 'none';
}

function clearHistorySearch() {
  el('historySearch').value = '';
  el('historySearchClear').style.display = 'none';
  filterHistorySearch();
}

// ── Stats search ──
function filterStatsSearch() {
  const q = el('statsSearch').value.trim().toLowerCase();
  el('statsSearchClear').style.display = q ? '' : 'none';
  const rows = el('statsTableWrap').querySelectorAll('tbody tr');
  let visible = 0;
  rows.forEach(row => {
    const title = row.cells[0]?.textContent.toLowerCase() || '';
    const show = !q || title.includes(q);
    row.style.display = show ? '' : 'none';
    if (show) visible++;
  });
  const noRes = el('statsNoResults');
  if (noRes) noRes.style.display = (!visible && q) ? '' : 'none';
}

function clearStatsSearch() {
  el('statsSearch').value = '';
  el('statsSearchClear').style.display = 'none';
  filterStatsSearch();
}

async function pruneState() {
  if (!await showConfirm('Prune Expired', 'Remove history entries that have passed your retention window? This does not affect cooldowns on items still within the retention period.', 'Prune')) return;
  const out = await api('/api/state/prune', {method:'POST'});
  showAlert(`Pruned ${out.removed} entries.`);
  PAGE = 0; refreshHistory();
}

async function clearState() {
  if (!await showConfirm('Clear History', 'Clear all search history? Cooldown records will be reset — every item becomes eligible for search immediately. This cannot be undone.', 'Clear', true)) return;
  await api('/api/state/clear', {method:'POST'});
  showAlert('History cleared.');
  PAGE = 0; refreshHistory();
}

// ── Stats tab ──
async function refreshStats() {
  try {
    const inst = el('statsInstance') ? el('statsInstance').value : '';
    const type = el('statsType') ? el('statsType').value : '';
    const limit = parseInt(el('statsLimit')?.value || '25', 10);
    let url = `/api/stats?offset=${STATS_PAGE * limit}&limit=${limit}`;
    if (inst) url += `&instance=${encodeURIComponent(inst)}`;
    if (type) url += `&type=${encodeURIComponent(type)}`;
    const data = await api(url);

    // Populate instance dropdown
    const sel = el('statsInstance');
    if (sel) {
      const prev = sel.value;
      sel.innerHTML = '<option value="">All Instances</option>' +
        data.instances.map(i => `<option value="${escapeHtml(i.name)}">${escapeHtml(i.name)}</option>`).join('');
      if (prev) sel.value = prev;
    }

    // Populate type dropdown dynamically from available types
    const typeSel = el('statsType');
    if (typeSel) {
      const prevType = typeSel.value;
      typeSel.innerHTML = '<option value="">All Types</option>' +
        (data.types || []).map(t => `<option value="${escapeHtml(t)}">${escapeHtml(t)}</option>`).join('');
      if (prevType && (data.types || []).includes(prevType)) typeSel.value = prevType;
    }

    el('statsPageInfo').textContent = `Page ${STATS_PAGE+1} · ${data.entries.length} of ${data.total}`;
    el('statsPagination').style.display = data.total > 0 ? 'flex' : 'none';

    // Update grand total cards
    el('statMoviesTotal').textContent = data.movies_total ?? 0;
    el('statShowsTotal').textContent = data.shows_total ?? 0;

    if (!data.entries.length && STATS_PAGE === 0) {
      el('statsTableWrap').innerHTML = '<p class="help" style="text-align:center;padding:20px">No confirmed imports yet. Nudgarr will check for imports ' + (CFG?.import_check_minutes || 120) + ' minutes after each search.</p>';
      return;
    }

    const sorted = sortItems(data.entries, STATS_SORT.col, STATS_SORT.dir);
    const rows = sorted.map(e => `
      <tr>
        <td>${escapeHtml(e.title || e.item_id)}</td>
        <td>${escapeHtml(e.instance)}</td>
        <td><span class="pill" style="font-size:11px;padding:2px 8px">${escapeHtml(e.type)}</span></td>
        <td>${escapeHtml(fmtTime(e.searched_ts))}</td>
        <td>${escapeHtml(fmtTime(e.imported_ts))}</td>
      </tr>
    `).join('');

    el('statsTableWrap').innerHTML = `
      <table>
        <thead><tr>
          <th class="sortable ${STATS_SORT.col==='title' ? 'sort-'+STATS_SORT.dir : ''}" data-col="title" onclick="sortStats('title')">Title</th>
          <th class="sortable ${STATS_SORT.col==='instance' ? 'sort-'+STATS_SORT.dir : ''}" data-col="instance" onclick="sortStats('instance')">Instance</th>
          <th class="sortable ${STATS_SORT.col==='type' ? 'sort-'+STATS_SORT.dir : ''}" data-col="type" onclick="sortStats('type')">Type</th>
          <th class="sortable ${STATS_SORT.col==='searched_ts' ? 'sort-'+STATS_SORT.dir : ''}" data-col="searched_ts" onclick="sortStats('searched_ts')">Searched</th>
          <th class="sortable ${STATS_SORT.col==='imported_ts' ? 'sort-'+STATS_SORT.dir : ''}" data-col="imported_ts" onclick="sortStats('imported_ts')">Imported</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
    `;
    applySortIndicators('#statsTableWrap table', STATS_SORT);
  } catch(e) {
    el('statsTableWrap').innerHTML = `<p class="help" style="color:var(--bad)">Failed to load stats: ${escapeHtml(e.message)}</p>`;
  }
}

function prevStatsPage() { if (STATS_PAGE > 0) { STATS_PAGE--; refreshStats(); } }
function nextStatsPage() { STATS_PAGE++; refreshStats(); }

async function checkImportsNow() {
  try {
    await api('/api/stats/check-imports', {method:'POST'});
    await refreshStats();
  } catch(e) {
    console.error('Import check failed:', e);
  }
}

async function clearStats() {
  if (!await showConfirm('Clear Stats', 'Clear all confirmed import entries? Lifetime Movies and Shows totals are preserved. This cannot be undone.', 'Clear', true)) return;
  await api('/api/stats/clear', {method:'POST'});
  refreshStats();
}

// ── Advanced tab ──
// ── Notifications tab ──
function fillNotifications() {
  if (!CFG) return;
  el('notify_enabled').checked = !!CFG.notify_enabled;
  el('notify_url').value = CFG.notify_url || '';
  el('notify_on_sweep_complete').checked = CFG.notify_on_sweep_complete !== false;
  el('notify_on_import').checked = CFG.notify_on_import !== false;
  el('notify_on_error').checked = CFG.notify_on_error !== false;
  syncNotifyUi();
}

function syncNotifyUi() {
  const enabled = el('notify_enabled').checked;
  el('notify_label').textContent = enabled ? 'Enabled' : 'Disabled';
  el('notify_url_field').style.opacity = enabled ? '1' : '0.5';
  el('notify_url_field').style.pointerEvents = enabled ? '' : 'none';
  el('notify_events_card').style.opacity = enabled ? '1' : '0.5';
  el('notify_events_card').style.pointerEvents = enabled ? '' : 'none';
  el('notify_test_row').style.display = enabled ? '' : 'none';
}

function toggleNotifyUrl() {
  const inp = el('notify_url');
  const btn = el('notifyUrlToggleBtn');
  if (inp.type === 'password') { inp.type = 'text'; btn.textContent = 'Hide'; }
  else { inp.type = 'password'; btn.textContent = 'Show'; }
}

async function testNotification() {
  const url = el('notify_url').value.trim();
  const msg = el('notifyTestMsg');
  if (!url) { msg.textContent = 'Enter a URL first.'; msg.className = 'msg err'; return; }
  msg.textContent = 'Sending…'; msg.className = 'msg';
  const r = await api('/api/notifications/test', {method: 'POST', body: JSON.stringify({url})});
  if (r && r.ok) {
    msg.textContent = '✓ Notification sent successfully';
    msg.className = 'msg ok';
  } else {
    msg.textContent = '✗ ' + (r?.error || 'Failed — check your URL');
    msg.className = 'msg err';
  }
  setTimeout(() => { msg.textContent = ''; msg.className = 'msg'; }, 5000);
}

async function saveNotifications() {
  CFG.notify_enabled = el('notify_enabled').checked;
  CFG.notify_url = el('notify_url').value.trim();
  CFG.notify_on_sweep_complete = el('notify_on_sweep_complete').checked;
  CFG.notify_on_import = el('notify_on_import').checked;
  CFG.notify_on_error = el('notify_on_error').checked;
  const r = await api('/api/config', {method: 'POST', body: JSON.stringify(CFG)});
  if (r && r.ok) {
    await loadAll();
    await new Promise(res => setTimeout(res, 400));
    el('notifyMsg').textContent = 'Saved'; el('notifyMsg').className = 'msg ok'; fadeMsg('notifyMsg');
  }
}

function fillAdvanced() {
  if (!CFG) return;
  el('radarr_backlog_enabled').checked = !!CFG.radarr_backlog_enabled;
  el('radarr_missing_max').value = CFG.radarr_missing_max ?? 1;
  el('radarr_missing_added_days').value = CFG.radarr_missing_added_days ?? 14;
  el('sonarr_backlog_enabled').checked = !!CFG.sonarr_backlog_enabled;
  el('sonarr_missing_max').value = CFG.sonarr_missing_max ?? 1;
  el('state_retention_days').value = CFG.state_retention_days ?? 180;
  el('auth_enabled').checked = CFG.auth_enabled !== false;
  el('auth_session_minutes').value = CFG.auth_session_minutes ?? 30;
  el('import_check_minutes').value = CFG.import_check_minutes ?? 120;
  if (el('show_support_link')) el('show_support_link').checked = CFG.show_support_link !== false;
  syncAuthUi();
  syncBacklogUi();
  syncSupportLinkUi();
  el('advMsg').textContent = ''; el('advMsg').className = 'msg';
}

function syncAuthUi() {
  const enabled = el('auth_enabled').checked;
  el('auth_label').textContent = enabled ? 'Enabled' : 'Disabled — anyone on your network can access the UI';
}

function markUnsaved(msgId) {
  const m = el(msgId);
  if (!m) return;
  clearTimeout(m._fadeTimer);
  m.classList.remove('fade');
  m.style.opacity = '';
  m.textContent = 'Unsaved Changes';
  m.className = 'msg unsaved';
}

function syncBacklogUi() {
  const radarrOn = el('radarr_backlog_enabled').checked;
  const sonarrOn = el('sonarr_backlog_enabled').checked;
  el('radarr_backlog_label').textContent = radarrOn ? 'Enabled' : 'Disabled';
  el('sonarr_backlog_label').textContent = sonarrOn ? 'Enabled' : 'Disabled';
  el('radarr_backlog_fields').style.opacity = radarrOn ? '1' : '0.35';
  el('radarr_backlog_fields').style.pointerEvents = radarrOn ? '' : 'none';
  el('sonarr_backlog_fields').style.opacity = sonarrOn ? '1' : '0.35';
  el('sonarr_backlog_fields').style.pointerEvents = sonarrOn ? '' : 'none';
}

async function saveAdvanced() {
  try {
    CFG.radarr_backlog_enabled = el('radarr_backlog_enabled').checked;
    CFG.radarr_missing_max = parseInt(el('radarr_missing_max').value !== '' ? el('radarr_missing_max').value : '1', 10);
    CFG.radarr_missing_added_days = parseInt(el('radarr_missing_added_days').value !== '' ? el('radarr_missing_added_days').value : '14', 10);
    CFG.sonarr_backlog_enabled = el('sonarr_backlog_enabled').checked;
    CFG.sonarr_missing_max = parseInt(el('sonarr_missing_max').value !== '' ? el('sonarr_missing_max').value : '1', 10);
    CFG.state_retention_days = parseInt(el('state_retention_days').value !== '' ? el('state_retention_days').value : '180', 10);
    CFG.auth_enabled = el('auth_enabled').checked;
    CFG.auth_session_minutes = parseInt(el('auth_session_minutes').value !== '' ? el('auth_session_minutes').value : '30', 10);
    CFG.import_check_minutes = parseInt(el('import_check_minutes').value !== '' ? el('import_check_minutes').value : '120', 10);
    if (el('show_support_link')) CFG.show_support_link = el('show_support_link').checked;
    await api('/api/config', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(CFG)});
    await loadAll();
    await new Promise(r => setTimeout(r, 400));
    el('advMsg').textContent = 'Saved'; el('advMsg').className = 'msg ok'; fadeMsg('advMsg');
    fadeNewestAddedWarnings();
  } catch(e) {
    el('advMsg').textContent = 'Save failed: ' + e.message; el('advMsg').className = 'msg err';
  }
}

async function logout() {
  await fetch('/api/auth/logout', {method:'POST'});
  window.location.href = '/login';
}

async function resetConfig() {
  if (!await showConfirm('Reset Config', 'Reset config to defaults? All instances and settings will be lost.', 'Reset', true)) return;
  await api('/api/config/reset', {method:'POST'});
  showAlert('Config reset to defaults.');
  await loadAll();
}

function downloadFile(which) {
  const a = document.createElement('a');
  a.href = which === 'config' ? '/api/file/config' : '/api/file/state';
  a.download = which === 'config' ? 'nudgarr-config.json' : 'nudgarr-state.json';
  document.body.appendChild(a); a.click(); a.remove();
}

function downloadDiagnostic() {
  const a = document.createElement('a');
  a.href = '/api/diagnostic';
  a.download = 'nudgarr-diagnostic.txt';
  document.body.appendChild(a); a.click(); a.remove();
}

// ── Run Now ──
async function runNow() {
  try {
    await api('/api/run-now', {method:'POST'});
    el('lastRun').textContent = 'Running…';
    el('dot-dryrun').classList.add('running');
  } catch(e) {
    showAlert('Run request failed: ' + e.message);
  }
}

// ── Status polling ──
async function refreshStatus() {
  try {
    const st = await api('/api/status');
    el('ver').textContent = st.version;
    el('lastRun').textContent = fmtTime(st.last_run_utc);
    el('dot-dryrun').classList.remove('running');
    el('nextRun').textContent = (CFG && CFG.scheduler_enabled) ? fmtTime(st.next_run_utc) : 'Manual';
    updateStatusPill(CFG?.scheduler_enabled);

    // Update instance health dots from last known state
    const health = st.instance_health || {};
    Object.entries(health).forEach(([key, state]) => {
      const [app, ...nameParts] = key.split('|');
      const name = nameParts.join('|');
      const inst = ALL_INSTANCES.find(i => i.app === app && i.name === name);
      if (inst) {
        const idx = ALL_INSTANCES.indexOf(inst);
        const cfgIdx = (CFG?.instances?.[app] || []).findIndex(i => i.name === name);
        if (cfgIdx >= 0) {
          const dot = el(`sdot-${app}-${cfgIdx}`);
          if (dot) {
            dot.className = 'status-dot ' + (state === 'ok' ? 'ok' : 'bad');
          }
        }
      }
    });
  } catch(e) {}
}

let AUTO_REFRESH_LAST = 0;
async function pollCycle() {
  await refreshStatus();
  const now = Date.now();
  if (now - AUTO_REFRESH_LAST >= 30000) {
    AUTO_REFRESH_LAST = now;
    if (ACTIVE_TAB === 'history') refreshHistory();
    if (ACTIVE_TAB === 'stats') refreshStats();
  }
}

loadAll().then(() => {
  document.querySelectorAll('.status-dot').forEach(d => { d.className = 'status-dot checking'; });
  maybeShowOnboarding();
  if (!CFG || CFG.onboarding_complete) maybeShowWhatsNew();
});
setInterval(pollCycle, 5000);
</script>
</body>
</html>
"""

# ─────────────────────────────────────────────────────────────────────
# Flask Routes
# REST API endpoints consumed by the UI and the scheduler
# All state-mutating endpoints are POST, read-only endpoints are GET
# ─────────────────────────────────────────────────────────────────────

@app.get("/")
@requires_auth
def index():
    return Response(UI_HTML, mimetype="text/html")

@app.get("/login")
def login_page():
    if is_authenticated():
        return redirect("/")
    return Response(LOGIN_HTML, mimetype="text/html")

@app.get("/setup")
def setup_page():
    if not is_setup_needed():
        return redirect("/")
    return Response(SETUP_HTML, mimetype="text/html")

@app.post("/api/setup")
def api_setup():
    if not is_setup_needed():
        return jsonify({"ok": False, "error": "Setup already complete"}), 400
    data = request.get_json(force=True, silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    if not username:
        return jsonify({"ok": False, "error": "Username is required"}), 400
    if len(password) < 6:
        return jsonify({"ok": False, "error": "Password must be at least 6 characters"}), 400
    cfg = load_or_init_config()
    cfg["auth_username"] = username
    cfg["auth_password_hash"] = hash_password(password)  # salted PBKDF2
    cfg["auth_enabled"] = True
    save_json_atomic(CONFIG_FILE, cfg, pretty=True)
    session["authenticated"] = True
    session["last_active"] = datetime.now().timestamp()
    return jsonify({"ok": True})

@app.post("/api/auth/login")
def api_login():
    ip = request.remote_addr or "unknown"
    locked, remaining = check_auth_lockout(ip)
    if locked:
        return jsonify({"ok": False, "error": f"Too many failed attempts. Try again in {remaining}s."}), 429
    data = request.get_json(force=True, silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    cfg = load_or_init_config()
    stored_hash = cfg.get("auth_password_hash", "")
    valid = verify_password(password, stored_hash) and username == cfg.get("auth_username", "")
    if not valid:
        duration = record_auth_failure(ip)
        msg = "Invalid credentials"
        if duration:
            msg = f"Too many failed attempts. Try again in {duration}s."
        return jsonify({"ok": False, "error": msg}), 401
    # Auto-migrate legacy sha256 hash to salted PBKDF2 on successful login
    if ":" not in stored_hash:
        cfg["auth_password_hash"] = hash_password(password)
        save_json_atomic(CONFIG_FILE, cfg, pretty=True)
    clear_auth_failures(ip)
    session["authenticated"] = True
    session["last_active"] = datetime.now().timestamp()
    return jsonify({"ok": True})

@app.post("/api/auth/logout")
def api_logout():
    session.clear()
    return jsonify({"ok": True})

@app.get("/api/status")
@requires_auth
def api_status():
    return jsonify(STATUS)

@app.get("/api/stats")
@requires_auth
def api_get_stats():
    cfg = load_or_init_config()
    stats = load_stats()
    entries = stats.get("entries", [])
    instance_filter = request.args.get("instance", "")
    type_filter = request.args.get("type", "")
    if instance_filter:
        entries = [e for e in entries if e.get("instance") == instance_filter]
    confirmed = [e for e in entries if e.get("imported")]
    confirmed.sort(key=lambda x: x.get("imported_ts", ""), reverse=True)
    # Build available types from current instance-filtered confirmed entries
    available_types = sorted(set(e.get("type", "") for e in confirmed if e.get("type")))
    if type_filter:
        confirmed = [e for e in confirmed if e.get("type") == type_filter]
    total = len(confirmed)
    try:
        offset = int(request.args.get("offset", 0))
        limit = int(request.args.get("limit", 25))
    except ValueError:
        offset, limit = 0, 25
    page_entries = confirmed[offset:offset + limit]
    # Build instance list for dropdown
    all_instances = []
    for inst in cfg.get("instances", {}).get("radarr", []):
        all_instances.append({"name": inst["name"], "app": "radarr"})
    for inst in cfg.get("instances", {}).get("sonarr", []):
        all_instances.append({"name": inst["name"], "app": "sonarr"})
    return jsonify({"entries": page_entries, "instances": all_instances, "types": available_types, "total": total, "movies_total": stats.get("lifetime_movies", 0), "shows_total": stats.get("lifetime_shows", 0)})

@app.post("/api/stats/clear")
@requires_auth
def api_clear_stats():
    stats = load_stats()
    stats["entries"] = []
    save_stats(stats)
    return jsonify({"ok": True})

@app.post("/api/stats/check-imports")
@requires_auth
def api_check_imports_now():
    cfg = load_or_init_config()
    session = requests.Session()
    # Temporarily override check delay to 0 for manual check
    cfg_override = dict(cfg)
    cfg_override["import_check_minutes"] = 0
    try:
        check_imports(session, cfg_override)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})
    return jsonify({"ok": True})

@app.get("/api/config")
@requires_auth
def api_get_config():
    return jsonify(load_or_init_config())

@app.post("/api/config")
@requires_auth
def api_set_config():
    cfg = request.get_json(force=True, silent=True)
    if not isinstance(cfg, dict):
        return jsonify({"ok": False, "error": "Body must be JSON object"}), 400
    ok, errs = validate_config(cfg)
    if not ok:
        return jsonify({"ok": False, "errors": errs}), 400
    save_json_atomic(CONFIG_FILE, cfg, pretty=True)
    return jsonify({"ok": True, "message": "Config saved", "config_file": CONFIG_FILE})

@app.post("/api/onboarding/complete")
@requires_auth
def api_onboarding_complete():
    cfg = load_or_init_config()
    cfg["onboarding_complete"] = True
    cfg["last_seen_version"] = VERSION
    save_json_atomic(CONFIG_FILE, cfg, pretty=True)
    return jsonify({"ok": True})

@app.post("/api/whats-new/dismiss")
@requires_auth
def api_whats_new_dismiss():
    cfg = load_or_init_config()
    cfg["last_seen_version"] = VERSION
    save_json_atomic(CONFIG_FILE, cfg, pretty=True)
    return jsonify({"ok": True})

@app.post("/api/notifications/test")
@requires_auth
def api_test_notification():
    data = request.get_json(force=True, silent=True) or {}
    url = str(data.get("url", "")).strip()
    if not url:
        return jsonify({"ok": False, "error": "No URL provided"}), 400
    if not APPRISE_AVAILABLE:
        return jsonify({"ok": False, "error": "Apprise is not installed in this container"}), 500
    try:
        ap = apprise.Apprise()
        if not ap.add(url):
            return jsonify({"ok": False, "error": "Invalid notification URL — check the format"}), 400
        result = ap.notify(title="Nudgarr — Test Notification", body="Your notification setup is working correctly.")
        if result:
            return jsonify({"ok": True})
        return jsonify({"ok": False, "error": "Notification sent but delivery failed — check your service settings"}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.post("/api/config/reset")
@requires_auth
def api_reset_config():
    cfg = deep_copy(DEFAULT_CONFIG)
    save_json_atomic(CONFIG_FILE, cfg, pretty=True)
    return jsonify({"ok": True})

@app.post("/api/test")
@requires_auth
def api_test():
    cfg = load_or_init_config()
    session = requests.Session()
    results = {"radarr": [], "sonarr": []}

    for inst in cfg.get("instances", {}).get("radarr", []):
        try:
            url = f"{inst['url'].rstrip('/')}/api/v3/system/status"
            data = req(session, "GET", url, inst["key"])
            results["radarr"].append({"name": inst["name"], "url": mask_url(inst["url"]), "ok": True, "version": data.get("version") if isinstance(data, dict) else None})
            STATUS["instance_health"][f"radarr|{inst['name']}"] = "ok"
        except Exception as e:
            results["radarr"].append({"name": inst.get("name"), "url": mask_url(inst.get("url","")), "ok": False, "error": str(e)})
            STATUS["instance_health"][f"radarr|{inst.get('name','')}"] = "bad"

    for inst in cfg.get("instances", {}).get("sonarr", []):
        try:
            url = f"{inst['url'].rstrip('/')}/api/v3/system/status"
            data = req(session, "GET", url, inst["key"])
            results["sonarr"].append({"name": inst["name"], "url": mask_url(inst["url"]), "ok": True, "version": data.get("version") if isinstance(data, dict) else None})
            STATUS["instance_health"][f"sonarr|{inst['name']}"] = "ok"
        except Exception as e:
            results["sonarr"].append({"name": inst.get("name"), "url": mask_url(inst.get("url","")), "ok": False, "error": str(e)})
            STATUS["instance_health"][f"sonarr|{inst.get('name','')}"] = "bad"

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
@requires_auth
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
@requires_auth
def api_state_raw():
    cfg = load_or_init_config()
    st = ensure_state_structure(load_state(), cfg)
    return jsonify(st)

@app.get("/api/state/items")
@requires_auth
def api_state_items():
    cfg = load_or_init_config()
    st = ensure_state_structure(load_state(), cfg)
    app_name = request.args.get("app", "")
    inst = request.args.get("instance", "")
    offset = int(request.args.get("offset", "0"))
    limit = int(request.args.get("limit", "250"))
    cooldown_hours = int(cfg.get("cooldown_hours", 48))

    # Determine which apps to include
    apps_to_scan = [app_name] if app_name else ["radarr", "sonarr"]

    items = []
    for cur_app in apps_to_scan:
        valid_keys = set()
        for i in cfg.get("instances", {}).get(cur_app, []):
            valid_keys.add(state_key(i["name"], i["url"]))

        app_obj = st.get(cur_app, {})
        if inst:
            buckets = {inst: app_obj.get(inst, {})} if inst in valid_keys else {}
        else:
            buckets = {k: v for k, v in (app_obj.items() if isinstance(app_obj, dict) else []) if k in valid_keys}

        for bucket_key, bucket in buckets.items():
            if not isinstance(bucket, dict):
                continue
            for k, entry in bucket.items():
                if not isinstance(k, str):
                    continue
                if isinstance(entry, dict):
                    ts = entry.get("ts", "")
                    title = entry.get("title", "")
                    sweep_type = entry.get("sweep_type", "")
                else:
                    ts = entry if isinstance(entry, str) else ""
                    title = ""
                    sweep_type = ""
                dt = parse_iso(ts)
                eligible = ""
                if dt is not None:
                    eligible_dt = dt + timedelta(hours=cooldown_hours)
                    eligible = iso_z(eligible_dt)
                items.append({"key": k, "title": title, "last_searched": ts, "eligible_again": eligible, "sweep_type": sweep_type})

    items.sort(key=lambda x: x.get("last_searched", ""), reverse=True)
    total = len(items)
    items = items[offset: offset+limit]
    return jsonify({"total": total, "items": items})

@app.post("/api/state/prune")
@requires_auth
def api_state_prune():
    cfg = load_or_init_config()
    st = ensure_state_structure(load_state(), cfg)
    removed = prune_state_by_retention(st, int(cfg.get("state_retention_days", 180)))
    # Also silently remove orphaned instance keys
    for app_name in ("radarr", "sonarr"):
        valid_keys = {state_key(i["name"], i["url"]) for i in cfg.get("instances", {}).get(app_name, [])}
        app_obj = st.get(app_name, {})
        if isinstance(app_obj, dict):
            for sk in list(app_obj.keys()):
                if sk not in valid_keys:
                    del app_obj[sk]
    save_state(st, cfg)
    return jsonify({"ok": True, "removed": removed})

@app.post("/api/state/clear")
@requires_auth
def api_state_clear():
    cfg = load_or_init_config()
    st = {"radarr": {}, "sonarr": {}}
    st = ensure_state_structure(st, cfg)
    save_state(st, cfg)
    return jsonify({"ok": True})

# File download endpoints
@app.get("/api/file/config")
@requires_auth
def api_file_config():
    cfg = load_or_init_config()
    return Response(json.dumps(cfg, indent=2), mimetype="application/json")

@app.get("/api/file/state")
@requires_auth
def api_file_state():
    cfg = load_or_init_config()
    st = ensure_state_structure(load_state(), cfg)
    pretty = True
    return Response(json.dumps(st, indent=2 if pretty else None), mimetype="application/json")

# Run-now endpoint
RUN_LOCK = threading.Lock()

@app.post("/api/run-now")
@requires_auth
def api_run_now():
    with RUN_LOCK:
        STATUS["run_requested"] = True
    return jsonify({"ok": True})

@app.get("/api/diagnostic")
@requires_auth
def api_diagnostic():
    cfg = load_or_init_config()
    radarr_instances = cfg.get("instances", {}).get("radarr", [])
    sonarr_instances = cfg.get("instances", {}).get("sonarr", [])
    radarr_names = [i.get("name") for i in radarr_instances]
    sonarr_names = [i.get("name") for i in sonarr_instances]

    # Build valid key → friendly name map
    name_map: Dict[str, str] = {}
    valid_keys: set = set()
    for inst in radarr_instances:
        sk = state_key(inst["name"], inst["url"])
        name_map[("radarr", sk)] = inst["name"]
        valid_keys.add(("radarr", sk))
    for inst in sonarr_instances:
        sk = state_key(inst["name"], inst["url"])
        name_map[("sonarr", sk)] = inst["name"]
        valid_keys.add(("sonarr", sk))

    # Per-instance state counts with orphan detection
    st = load_state()
    instance_counts = []
    for app_name in ("radarr", "sonarr"):
        app_obj = st.get(app_name, {})
        if isinstance(app_obj, dict):
            for sk, bucket in app_obj.items():
                count = len(bucket) if isinstance(bucket, dict) else 0
                key_tuple = (app_name, sk)
                if key_tuple in valid_keys:
                    friendly = name_map[key_tuple]
                    instance_counts.append(f"  {app_name}/{friendly}: {count} entries")
                else:
                    instance_counts.append(f"  {app_name}/{sk}: {count} entries (orphaned — no matching instance)")

    # Last run summary with cutoff/backlog breakdown
    last_summary = STATUS.get("last_summary") or {}
    summary_lines = []
    for app_name in ("radarr", "sonarr"):
        for s in last_summary.get(app_name, []):
            if "error" in s:
                summary_lines.append(f"  {s.get('name','?')}: ERROR — {s.get('error')}")
            else:
                cutoff = s.get('searched', 0)
                backlog = s.get('searched_missing', 0)
                skipped = s.get('skipped_cooldown', 0)
                summary_lines.append(
                    f"  {s.get('name','?')}: searched={cutoff + backlog} "
                    f"(cutoff={cutoff} backlog={backlog}) skipped_cooldown={skipped}"
                )

    lines = [
        f"Nudgarr v{VERSION}",
        f"Port: {PORT}",
        f"Last run: {STATUS.get('last_run_utc') or 'Never'}",
        f"Next run: {STATUS.get('next_run_utc') or 'N/A'}",
        f"Last error: {STATUS.get('last_error') or 'None'}",
        f"Scheduler: {'enabled' if cfg.get('scheduler_enabled') else 'manual'}, interval: {cfg.get('run_interval_minutes')}min",
        f"Cooldown: {cfg.get('cooldown_hours')}h",
        f"Radarr instances ({len(radarr_names)}): {', '.join(radarr_names) or 'none'}",
        f"Sonarr instances ({len(sonarr_names)}): {', '.join(sonarr_names) or 'none'}",
        f"Radarr cap: {cfg.get('radarr_max_movies_per_run')}/run | Backlog cap: {cfg.get('radarr_missing_max', 0)}/run",
        f"Sonarr cap: {cfg.get('sonarr_max_episodes_per_run')}/run | Backlog cap: {cfg.get('sonarr_missing_max', 0)}/run",
        f"History file: {STATE_FILE}",
        f"Config file: {CONFIG_FILE}",
        f"Stats file: {STATS_FILE}",
        "",
        "Last run summary:",
    ] + (summary_lines or ["  No runs yet."]) + [
        "",
        "History entry counts:",
    ] + (instance_counts or ["  No entries."])

    text = "\n".join(lines)
    return Response(
        text,
        mimetype="text/plain",
        headers={"Content-Disposition": "attachment; filename=nudgarr-diagnostic.txt"}
    )

# ─────────────────────────────────────────────────────────────────────
# Scheduler & Service Runner
# Background thread runs sweeps on interval, handles run-now requests,
# manages stop signal, prints banner on startup
# ─────────────────────────────────────────────────────────────────────

def print_banner(cfg: Dict[str, Any]) -> None:
    print("")
    print("====================================")
    print(f" Nudgarr v{VERSION}")
    print(" Because RSS sometimes needs a nudge.")
    print("====================================")
    print(f"Config: {CONFIG_FILE}")
    print(f"State:  {STATE_FILE}")
    print(f"Stats:  {STATS_FILE}")
    print(f"UI:     http://<host>:{PORT}/")
    print("")
    print("")

def start_ui_server() -> None:
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)

def scheduler_loop(stop_flag: Dict[str, bool]) -> None:
    STATUS["scheduler_running"] = True
    session = requests.Session()
    cycle = 0

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
                # Persist last_run so it survives restart
                st["last_run_utc"] = STATUS["last_run_utc"]
                save_state(st, cfg)
                notify_sweep_complete(summary, cfg)
                # Notify on any instance-level errors within the sweep
                for app in ("radarr", "sonarr"):
                    for inst in summary.get(app, []):
                        if "error" in inst:
                            notify_error(f"'{inst['name']}' is unreachable.", cfg)
                # Check for confirmed imports from previous searches
                try:
                    check_imports(session, cfg)
                except Exception as ce:
                    print(f"[Stats] Import check error: {ce}")
            except Exception as e:
                STATUS["last_error"] = str(e)
                print(f"ERROR (sweep): {e}")
                notify_error(f"Sweep failed: {e}", cfg)
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

    # Pre-populate STATUS from persisted state so UI has values immediately
    _st = load_state()
    if _st.get("last_run_utc"):
        STATUS["last_run_utc"] = _st["last_run_utc"]
    if cfg.get("scheduler_enabled"):
        _interval = int(cfg.get("run_interval_minutes", 360))
        STATUS["next_run_utc"] = iso_z(utcnow() + timedelta(minutes=_interval))

    # Background health ping — parallel, non-blocking, populates dots within ~1s
    def _startup_health_ping():
        _session = requests.Session()
        instances = []
        for _inst in cfg.get("instances", {}).get("radarr", []):
            instances.append(("radarr", _inst))
        for _inst in cfg.get("instances", {}).get("sonarr", []):
            instances.append(("sonarr", _inst))
        def _ping(app, inst):
            try:
                _url = f"{inst['url'].rstrip('/')}/api/v3/system/status"
                req(_session, "GET", _url, inst["key"], timeout=5)
                STATUS["instance_health"][f"{app}|{inst['name']}"] = "ok"
            except Exception:
                STATUS["instance_health"][f"{app}|{inst['name']}"] = "bad"
        threads = [threading.Thread(target=_ping, args=(a, i), daemon=True) for a, i in instances]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    threading.Thread(target=_startup_health_ping, daemon=True).start()

    # Start UI
    threading.Thread(target=start_ui_server, daemon=True).start()

    # Run scheduler loop in main thread
    scheduler_loop(stop_flag)

    print("Nudgarr exiting.")

if __name__ == "__main__":
    main()

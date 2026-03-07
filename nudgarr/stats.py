"""
nudgarr/stats.py

Stats recording, import confirmation checking, and cooldown selection.

  Stats recording : record_stat_entry
  Import checking : check_imports
  Cooldown logic  : is_allowed_by_cooldown,
                    pick_items_with_cooldown, pick_ids_with_cooldown
  State marking   : mark_items_searched, mark_ids_searched

pick_ids_with_cooldown and mark_ids_searched are legacy helpers kept for
compatibility with any code still passing plain ID lists rather than item
dicts.

Imports from within the package: state, notifications, utils.
"""

import random
from datetime import timedelta
from typing import Any, Dict, List, Tuple

import requests

from nudgarr.notifications import notify_import
from nudgarr.state import load_stats, save_stats
from nudgarr.utils import iso_z, parse_iso, utcnow


# ── Stats recording ───────────────────────────────────────────────────

def record_stat_entry(
    app: str,
    instance_name: str,
    item_id: str,
    title: str,
    entry_type: str,
    searched_ts: str,
) -> None:
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


# ── Import checking ───────────────────────────────────────────────────

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
                r = session_obj.get(
                    f"{url}/api/v3/history/movie",
                    params={"movieId": item_id},
                    headers={"X-Api-Key": key},
                    timeout=15,
                )
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
                r = session_obj.get(
                    f"{url}/api/v3/history/series",
                    params={"seriesId": item_id},
                    headers={"X-Api-Key": key},
                    timeout=15,
                )
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


# ── Cooldown selection ────────────────────────────────────────────────

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


def pick_items_with_cooldown(
    items: List[Dict[str, Any]],
    st_bucket: Dict[str, Any],
    prefix: str,
    cooldown_hours: int,
    max_per_run: int,
    sample_mode: str,
) -> Tuple[List[Dict[str, Any]], int, int]:
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


def pick_ids_with_cooldown(
    ids: List[int],
    st_bucket: Dict[str, Any],
    prefix: str,
    cooldown_hours: int,
    max_per_run: int,
    sample_mode: str,
) -> Tuple[List[int], int, int]:
    """Legacy helper for plain ID lists (kept for compatibility)."""
    items = [{"id": i, "title": ""} for i in ids]
    chosen_items, eligible, skipped = pick_items_with_cooldown(items, st_bucket, prefix, cooldown_hours, max_per_run, sample_mode)
    return [it["id"] for it in chosen_items], eligible, skipped


# ── State marking ─────────────────────────────────────────────────────

def mark_items_searched(
    st_bucket: Dict[str, Any],
    prefix: str,
    items: List[Dict[str, Any]],
    sweep_type: str = "",
) -> None:
    now_s = iso_z(utcnow())
    for item in items:
        key = f"{prefix}:{item['id']}"
        existing = st_bucket.get(key) or {}
        prev_count = existing.get("search_count", 0) if isinstance(existing, dict) else 0
        st_bucket[key] = {
            "ts": now_s,
            "title": item.get("title") or "",
            "sweep_type": sweep_type,
            "library_added": item.get("added") or existing.get("library_added") or "",
            "search_count": prev_count + 1,
        }


def mark_ids_searched(
    st_bucket: Dict[str, Any],
    prefix: str,
    ids: List[int],
) -> None:
    """Legacy helper for plain ID lists (kept for compatibility)."""
    now_s = iso_z(utcnow())
    for _id in ids:
        key = f"{prefix}:{_id}"
        existing = st_bucket.get(key)
        title = existing.get("title", "") if isinstance(existing, dict) else ""
        st_bucket[key] = {"ts": now_s, "title": title}

"""
nudgarr/stats.py

Stats recording, import confirmation checking, and cooldown selection.

  Stats recording : record_stat_entry
  Import checking : check_imports
  Cooldown logic  : is_allowed_by_cooldown, pick_items_with_cooldown
  State marking   : mark_items_searched

Cooldown checking and state marking query the SQLite database
directly via db.py rather than the st_bucket dict pattern.

Imports from within the package: db, notifications, utils.
"""

import random
from datetime import timedelta
from typing import Any, Dict, List, Tuple

import requests

from nudgarr import db
from nudgarr.notifications import notify_import
from nudgarr.utils import iso_z, parse_iso, utcnow


# ── Stats recording ───────────────────────────────────────────────────

def record_stat_entry(
    app: str,
    instance_name: str,
    instance_url: str,
    item_id: str,
    title: str,
    entry_type: str,
    searched_ts: str,
) -> None:
    """Record a searched item for later import checking."""
    db.upsert_stat_entry(app, instance_name, instance_url, str(item_id), title, entry_type, searched_ts)


# ── Import checking ───────────────────────────────────────────────────

def check_imports(session_obj: requests.Session, cfg: Dict[str, Any]) -> None:
    """Poll Radarr/Sonarr history for import events on recently searched items."""
    check_minutes = int(cfg.get("import_check_minutes", 120))
    now_ts = iso_z(utcnow())

    instance_map: Dict[Tuple[str, str], Dict] = {}
    instance_map_by_url: Dict[Tuple[str, str], Dict] = {}
    for inst in cfg.get("instances", {}).get("radarr", []):
        instance_map[("radarr", inst["name"])] = inst
        instance_map_by_url[("radarr", inst["url"].rstrip("/"))] = inst
    for inst in cfg.get("instances", {}).get("sonarr", []):
        instance_map[("sonarr", inst["name"])] = inst
        instance_map_by_url[("sonarr", inst["url"].rstrip("/"))] = inst

    entries = db.get_unconfirmed_entries(check_minutes, now_ts)
    updated = False

    for entry in entries:
        app = entry.get("app", "radarr")
        instance_name = entry.get("instance", "")
        instance_url = (entry.get("instance_url") or "").rstrip("/")
        inst = instance_map.get((app, instance_name)) or (instance_map_by_url.get((app, instance_url)) if instance_url else None)
        if not inst:
            continue

        url = inst["url"].rstrip("/")
        key = inst["key"]
        item_id = entry.get("item_id", "")
        entry_type = entry.get("type", "")
        last_searched_ts = entry.get("last_searched_ts", "")
        dt = parse_iso(last_searched_ts)

        try:
            if app == "radarr":
                r = session_obj.get(
                    f"{url}/api/v3/history/movie",
                    params={"movieId": item_id},
                    headers={"X-Api-Key": key},
                    timeout=15,
                )
                if r.ok:
                    events = r.json()
                    if not isinstance(events, list):
                        events = []
                    for ev in events:
                        if ev.get("eventType") == "downloadFolderImported":
                            ev_dt = parse_iso(ev.get("date", ""))
                            if ev_dt and (dt is None or ev_dt > dt):
                                imported_ts = iso_z(ev_dt)
                                if db.confirm_stat_entry(app, instance_name, instance_url, item_id, entry_type, imported_ts):
                                    db.increment_lifetime_total("movies")
                                    overrides_on = cfg.get("per_instance_overrides_enabled", False)
                                    ov = inst.get("overrides", {}) if overrides_on else {}
                                    notify_on = ov.get("notifications_enabled", cfg.get("notify_enabled", False))
                                    if notify_on:
                                        notify_import(entry.get("title", "Unknown"), entry_type, instance_name, cfg)
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
                            if ev_dt and (dt is None or ev_dt > dt):
                                imported_ts = iso_z(ev_dt)
                                if db.confirm_stat_entry(app, instance_name, instance_url, item_id, entry_type, imported_ts):
                                    db.increment_lifetime_total("shows")
                                    overrides_on = cfg.get("per_instance_overrides_enabled", False)
                                    ov = inst.get("overrides", {}) if overrides_on else {}
                                    notify_on = ov.get("notifications_enabled", cfg.get("notify_enabled", False))
                                    if notify_on:
                                        notify_import(entry.get("title", "Unknown"), entry_type, instance_name, cfg)
                                    updated = True
                                break
        except Exception as e:
            print(f"[Stats] Import check failed for {instance_name}/{item_id}: {e}")

    if updated:
        print("[Stats] Import check complete — updated confirmed imports")


# ── Cooldown selection ────────────────────────────────────────────────

def is_allowed_by_cooldown(last_ts: Any, cooldown_hours: int) -> bool:
    """Return True if the item is eligible to be searched again.
    Always returns True when cooldown_hours <= 0 (cooldown disabled) or when
    last_ts is None (item has never been searched). Otherwise checks whether
    enough time has elapsed since last_ts."""
    if cooldown_hours <= 0:
        return True
    if not last_ts:
        return True
    dt = parse_iso(last_ts) if isinstance(last_ts, str) else None
    if dt is None:
        return True
    return dt < (utcnow() - timedelta(hours=cooldown_hours))


def pick_items_with_cooldown(
    items: List[Dict[str, Any]],
    instance_app: str,
    instance_name: str,
    instance_url: str,
    item_type: str,
    cooldown_hours: int,
    max_per_run: int,
    sample_mode: str,
) -> Tuple[List[Dict[str, Any]], int, int]:
    """
    Filter items by cooldown, sort by sample_mode, and return up to max_per_run.
    Cooldown timestamps are fetched from the DB per item.
    Returns (chosen_items, eligible_count, skipped_count).
    """
    eligible: List[Dict[str, Any]] = []
    skipped = 0

    # Fetch all cooldown timestamps in one query instead of one per item
    item_ids = [str(item["id"]) for item in items]
    ts_map = db.get_last_searched_ts_bulk(
        instance_app, instance_name, instance_url, item_type, item_ids
    )

    for item in items:
        last_ts = ts_map.get(str(item["id"]))
        if is_allowed_by_cooldown(last_ts, cooldown_hours):
            eligible.append(item)
        else:
            skipped += 1

    if sample_mode == "random":
        random.shuffle(eligible)
    elif sample_mode == "alphabetical":
        eligible.sort(key=lambda x: (x.get("title") or "").lower())
    elif sample_mode == "oldest_added":
        eligible.sort(key=lambda x: (x.get("added") or "9999"))
    elif sample_mode == "newest_added":
        eligible.sort(key=lambda x: (x.get("added") or ""), reverse=True)

    chosen = eligible[:max_per_run] if max_per_run > 0 else []
    return chosen, len(eligible), skipped


# ── State marking ─────────────────────────────────────────────────────

def mark_items_searched(
    instance_app: str,
    instance_name: str,
    instance_url: str,
    item_type: str,
    items: List[Dict[str, Any]],
    sweep_type: str = "",
) -> None:
    """Write a search_history record for every item in items. No return value.
    Upserts each row — increments search_count and updates last_searched_ts
    if the item already exists in history."""
    now_s = iso_z(utcnow())
    for item in items:
        db.upsert_search_history(
            app=instance_app,
            instance_name=instance_name,
            instance_url=instance_url,
            item_type=item_type,
            item_id=str(item["id"]),
            title=item.get("title") or "",
            sweep_type=sweep_type,
            library_added=item.get("added") or "",
            now_ts=now_s,
            series_id=str(item.get("series_id") or ""),
        )

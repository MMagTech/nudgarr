"""
nudgarr/routes/state.py

State inspection, file downloads, and exclusion list management.

  GET  /api/state/summary     -- entry counts and file size per instance
  GET  /api/state/raw         -- full state dict
  GET  /api/state/items       -- paginated history items with cooldown info
  POST /api/state/prune       -- prune entries older than retention_days
  POST /api/state/clear       -- wipe state (preserves lifetime counters)
  GET  /api/file/config       -- download config JSON
  GET  /api/file/state        -- download state JSON
  GET  /api/file/backup       -- download zip of all data files
  GET  /api/exclusions        -- list exclusions
  POST /api/exclusions/add    -- add a title to exclusions
  POST /api/exclusions/remove -- remove a title from exclusions
"""

import io
import json
import os
import zipfile
from datetime import timedelta

from flask import Blueprint, Response, jsonify, request

from nudgarr.auth import requires_auth
from nudgarr.config import load_or_init_config
from nudgarr.constants import STATE_FILE
from nudgarr.state import (
    ensure_state_structure,
    load_exclusions,
    load_state,
    load_stats,
    prune_state_by_retention,
    save_exclusions,
    save_state,
    state_key,
)
from nudgarr.utils import iso_z, parse_iso, utcnow

bp = Blueprint("state", __name__)


# ── Helpers ───────────────────────────────────────────────────────────

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


# ── State ─────────────────────────────────────────────────────────────

@bp.get("/api/state/summary")
@requires_auth
def api_state_summary():
    cfg = load_or_init_config()
    st = ensure_state_structure(load_state(), cfg)
    radarr_entries = 0
    sonarr_entries = 0
    per_instance = {"radarr": {}, "sonarr": {}}

    # Build mapping: state_key → friendly name
    name_map = {}
    for inst in cfg.get("instances", {}).get("radarr", []):
        sk = state_key(inst["name"], inst["url"])
        name_map[sk] = inst["name"]
    for inst in cfg.get("instances", {}).get("sonarr", []):
        sk = state_key(inst["name"], inst["url"])
        name_map[sk] = inst["name"]

    instances = {"radarr": [], "sonarr": []}
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


@bp.get("/api/state/raw")
@requires_auth
def api_state_raw():
    cfg = load_or_init_config()
    st = ensure_state_structure(load_state(), cfg)
    return jsonify(st)


@bp.get("/api/state/items")
@requires_auth
def api_state_items():
    cfg = load_or_init_config()
    st = ensure_state_structure(load_state(), cfg)
    app_name = request.args.get("app", "")
    inst = request.args.get("instance", "")
    offset = int(request.args.get("offset", "0"))
    limit = int(request.args.get("limit", "250"))
    cooldown_hours = int(cfg.get("cooldown_hours", 48))

    apps_to_scan = [app_name] if app_name else ["radarr", "sonarr"]

    # Build reverse map: bucket_key → instance name
    bucket_name_map = {}
    for cur_app in ["radarr", "sonarr"]:
        for i in cfg.get("instances", {}).get(cur_app, []):
            bucket_name_map[state_key(i["name"], i["url"])] = i["name"]

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
            instance_name = bucket_name_map.get(bucket_key, bucket_key.split("|")[0])
            for k, entry in bucket.items():
                if not isinstance(k, str):
                    continue
                if isinstance(entry, dict):
                    ts = entry.get("ts", "")
                    title = entry.get("title", "")
                    sweep_type = entry.get("sweep_type", "")
                    library_added = entry.get("library_added", "")
                    search_count = entry.get("search_count", 1)
                else:
                    ts = entry if isinstance(entry, str) else ""
                    title = ""
                    sweep_type = ""
                    library_added = ""
                    search_count = 1
                dt = parse_iso(ts)
                eligible = ""
                if dt is not None:
                    eligible_dt = dt + timedelta(hours=cooldown_hours)
                    eligible = iso_z(eligible_dt)
                items.append({
                    "key": k, "title": title, "instance": instance_name,
                    "last_searched": ts, "eligible_again": eligible,
                    "sweep_type": sweep_type, "library_added": library_added,
                    "search_count": search_count,
                })

    items.sort(key=lambda x: x.get("last_searched", ""), reverse=True)
    total = len(items)
    items = items[offset:offset + limit]
    return jsonify({"total": total, "items": items})


@bp.post("/api/state/prune")
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


@bp.post("/api/state/clear")
@requires_auth
def api_state_clear():
    cfg = load_or_init_config()
    old_st = load_state()
    st = {"radarr": {}, "sonarr": {}}
    # Preserve lifetime sweep counters — these survive Clear History
    if "sweep_lifetime" in old_st:
        st["sweep_lifetime"] = old_st["sweep_lifetime"]
    st = ensure_state_structure(st, cfg)
    save_state(st, cfg)
    return jsonify({"ok": True})


# ── File downloads ────────────────────────────────────────────────────

@bp.get("/api/file/config")
@requires_auth
def api_file_config():
    cfg = load_or_init_config()
    return Response(json.dumps(cfg, indent=2), mimetype="application/json")


@bp.get("/api/file/state")
@requires_auth
def api_file_state():
    cfg = load_or_init_config()
    st = ensure_state_structure(load_state(), cfg)
    return Response(json.dumps(st, indent=2), mimetype="application/json")


@bp.get("/api/file/backup")
@requires_auth
def api_file_backup():
    cfg = load_or_init_config()
    st = ensure_state_structure(load_state(), cfg)
    stats = load_stats()
    exclusions = load_exclusions()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("nudgarr-config.json", json.dumps(cfg, indent=2))
        zf.writestr("nudgarr-state.json", json.dumps(st, indent=2))
        zf.writestr("nudgarr-stats.json", json.dumps(stats, indent=2))
        zf.writestr("nudgarr-exclusions.json", json.dumps(exclusions, indent=2))
    buf.seek(0)
    return Response(
        buf.read(),
        mimetype="application/zip",
        headers={"Content-Disposition": "attachment; filename=nudgarr-backup.zip"},
    )


# ── Exclusions ────────────────────────────────────────────────────────

@bp.get("/api/exclusions")
@requires_auth
def api_get_exclusions():
    return jsonify(load_exclusions())


@bp.post("/api/exclusions/add")
@requires_auth
def api_add_exclusion():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title required"}), 400
    exclusions = load_exclusions()
    if not any(e.get("title", "").lower() == title.lower() for e in exclusions):
        exclusions.append({"title": title, "excluded_at": iso_z(utcnow())})
        save_exclusions(exclusions)
    return jsonify({"ok": True, "count": len(exclusions)})


@bp.post("/api/exclusions/remove")
@requires_auth
def api_remove_exclusion():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title required"}), 400
    exclusions = load_exclusions()
    exclusions = [e for e in exclusions if e.get("title", "").lower() != title.lower()]
    save_exclusions(exclusions)
    return jsonify({"ok": True, "count": len(exclusions)})

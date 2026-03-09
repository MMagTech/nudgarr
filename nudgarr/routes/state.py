"""
nudgarr/routes/state.py

State inspection, file downloads, and exclusion list management.

  GET  /api/state/summary     -- entry counts and file size per instance
  GET  /api/state/raw         -- full state dict (compat shim)
  GET  /api/state/items       -- paginated history items with cooldown info
  POST /api/state/prune       -- prune entries older than retention_days
  POST /api/state/clear       -- wipe search history (preserves sweep_lifetime)
  GET  /api/file/config       -- download config JSON
  GET  /api/file/state        -- download state JSON (from DB)
  GET  /api/file/backup       -- download zip of all data
  GET  /api/exclusions        -- list exclusions
  POST /api/exclusions/add    -- add a title to exclusions
  POST /api/exclusions/remove -- remove a title from exclusions
"""

import io
import json

from flask import Blueprint, Response, jsonify, request

from nudgarr import db
from nudgarr.auth import requires_auth
from nudgarr.config import load_or_init_config
from nudgarr.state import prune_state_by_retention, state_key


bp = Blueprint("state", __name__)


# ── State ─────────────────────────────────────────────────────────────

@bp.get("/api/state/summary")
@requires_auth
def api_state_summary():
    cfg = load_or_init_config()
    return jsonify(db.get_search_history_summary(cfg))


@bp.get("/api/state/raw")
@requires_auth
def api_state_raw():
    """Compatibility shim: return DB contents shaped like the old state JSON."""
    export = db.export_as_json_dict()
    return jsonify(export["state"])


@bp.get("/api/state/items")
@requires_auth
def api_state_items():
    cfg = load_or_init_config()
    app_name = request.args.get("app", "")
    inst_key = request.args.get("instance", "")
    offset = int(request.args.get("offset", "0"))
    limit = int(request.args.get("limit", "250"))
    cooldown_hours = int(cfg.get("cooldown_hours", 48))

    # Build friendly name map: state_key → name
    name_map = {}
    for cur_app in ("radarr", "sonarr"):
        for inst in cfg.get("instances", {}).get(cur_app, []):
            sk = state_key(inst["name"], inst["url"])
            name_map[sk] = inst["name"]

    total, items = db.get_search_history(
        app_filter=app_name,
        instance_key=inst_key,
        offset=offset,
        limit=limit,
        cooldown_hours=cooldown_hours,
        instance_name_map=name_map,
    )
    return jsonify({"total": total, "items": items})


@bp.post("/api/state/prune")
@requires_auth
def api_state_prune():
    cfg = load_or_init_config()
    removed = prune_state_by_retention({}, int(cfg.get("state_retention_days", 180)))
    return jsonify({"ok": True, "removed": removed})


@bp.post("/api/state/clear")
@requires_auth
def api_state_clear():
    # Clear search history but leave sweep_lifetime intact
    db.clear_search_history()
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
    export = db.export_as_json_dict()
    return Response(json.dumps(export["state"], indent=2), mimetype="application/json")


@bp.get("/api/file/backup")
@requires_auth
def api_file_backup():
    cfg = load_or_init_config()
    export = db.export_as_json_dict()
    buf = io.BytesIO()
    import zipfile
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("nudgarr-config.json", json.dumps(cfg, indent=2))
        zf.writestr("nudgarr-state.json", json.dumps(export["state"], indent=2))
        zf.writestr("nudgarr-stats.json", json.dumps(export["stats"], indent=2))
        zf.writestr("nudgarr-exclusions.json", json.dumps(export["exclusions"], indent=2))
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
    return jsonify(db.get_exclusions())


@bp.post("/api/exclusions/add")
@requires_auth
def api_add_exclusion():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title required"}), 400
    count = db.add_exclusion(title)
    return jsonify({"ok": True, "count": count})


@bp.post("/api/exclusions/remove")
@requires_auth
def api_remove_exclusion():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title required"}), 400
    count = db.remove_exclusion(title)
    return jsonify({"ok": True, "count": count})

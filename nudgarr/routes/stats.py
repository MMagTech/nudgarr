"""
nudgarr/routes/stats.py

Confirmed import stats endpoints.

  GET  /api/stats                -- paginated confirmed imports with filters
  POST /api/stats/clear          -- clear all stat entries (preserves lifetime totals)
  POST /api/stats/check-imports  -- manually trigger import check now
"""

import requests as req_lib

from flask import Blueprint, jsonify, request

from nudgarr import db
from nudgarr.auth import requires_auth
from nudgarr.config import load_or_init_config
from nudgarr.stats import check_imports

bp = Blueprint("stats", __name__)


@bp.get("/api/stats")
@requires_auth
def api_get_stats():
    cfg = load_or_init_config()
    instance_filter = request.args.get("instance", "")
    type_filter = request.args.get("type", "")
    try:
        offset = int(request.args.get("offset", 0))
        limit = int(request.args.get("limit", 25))
    except ValueError:
        offset, limit = 0, 25

    total, entries, available_types = db.get_confirmed_entries(
        instance_filter=instance_filter,
        type_filter=type_filter,
        offset=offset,
        limit=limit,
    )
    totals = db.get_lifetime_totals()

    all_instances = []
    for inst in cfg.get("instances", {}).get("radarr", []):
        all_instances.append({"name": inst["name"], "app": "radarr"})
    for inst in cfg.get("instances", {}).get("sonarr", []):
        all_instances.append({"name": inst["name"], "app": "sonarr"})

    return jsonify({
        "entries": entries,
        "instances": all_instances,
        "types": available_types,
        "total": total,
        "movies_total": totals.get("movies", 0),
        "shows_total": totals.get("shows", 0),
    })


@bp.post("/api/stats/clear")
@requires_auth
def api_clear_stats():
    db.clear_stat_entries()
    return jsonify({"ok": True})


@bp.post("/api/stats/check-imports")
@requires_auth
def api_check_imports_now():
    cfg = load_or_init_config()
    session = req_lib.Session()
    cfg_override = dict(cfg)
    cfg_override["import_check_minutes"] = 0
    try:
        check_imports(session, cfg_override)
    except Exception:
        return jsonify({"ok": False, "error": "Import check failed — check logs for details"})
    return jsonify({"ok": True})

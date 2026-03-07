"""
nudgarr/routes/stats.py

Confirmed import stats endpoints.

  GET  /api/stats                -- paginated confirmed imports with filters
  POST /api/stats/clear          -- clear all stat entries (preserves lifetime totals)
  POST /api/stats/check-imports  -- manually trigger import check now
"""

import requests as req_lib

from flask import Blueprint, jsonify, request

from nudgarr.auth import requires_auth
from nudgarr.config import load_or_init_config
from nudgarr.state import load_stats, save_stats
from nudgarr.stats import check_imports

bp = Blueprint("stats", __name__)


@bp.get("/api/stats")
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
    return jsonify({
        "entries": page_entries,
        "instances": all_instances,
        "types": available_types,
        "total": total,
        "movies_total": stats.get("lifetime_movies", 0),
        "shows_total": stats.get("lifetime_shows", 0),
    })


@bp.post("/api/stats/clear")
@requires_auth
def api_clear_stats():
    stats = load_stats()
    stats["entries"] = []
    save_stats(stats)
    return jsonify({"ok": True})


@bp.post("/api/stats/check-imports")
@requires_auth
def api_check_imports_now():
    cfg = load_or_init_config()
    session = req_lib.Session()
    # Temporarily override check delay to 0 for manual check
    cfg_override = dict(cfg)
    cfg_override["import_check_minutes"] = 0
    try:
        check_imports(session, cfg_override)
    except Exception:
        return jsonify({"ok": False, "error": "Import check failed — check logs for details"})
    return jsonify({"ok": True})

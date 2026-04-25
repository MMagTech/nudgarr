"""
nudgarr/routes/stats.py

Confirmed import stats endpoints.

  GET  /api/stats                -- paginated confirmed imports with filters
  POST /api/stats/clear          -- clear all stat entries (preserves lifetime totals)
  POST /api/stats/check-imports  -- manually trigger import check now

The GET endpoint accepts optional query params: `period` (lifetime, 30, 7),
`instance`, `type`, `search` (case-insensitive title substring on confirmed imports),
plus `offset` and `limit` for pagination.
Lifetime returns the persistent lifetime totals; 30 and 7 return rolling window
counts calculated from imported_ts in stat_entries.
"""

import json
import requests as req_lib

from flask import Blueprint, jsonify, request

from nudgarr import db
from nudgarr.auth import requires_auth
from nudgarr.config import load_or_init_config
from nudgarr.stats import check_imports
from nudgarr.scheduler import _run_auto_exclusion_check

import logging

logger = logging.getLogger(__name__)


bp = Blueprint("stats", __name__)


@bp.get("/api/stats")
@requires_auth
def api_get_stats():
    cfg = load_or_init_config()
    instance_filter = request.args.get("instance", "").rstrip("/")
    type_filter = request.args.get("type", "")
    period = request.args.get("period", "lifetime")
    try:
        offset = int(request.args.get("offset", 0))
        limit = int(request.args.get("limit", 25))
    except ValueError:
        offset, limit = 0, 25

    # Same window as KPI totals: list + count must match Movies/Episodes for 7/30/lifetime.
    period_days = None
    if period == "7":
        period_days = 7
    elif period == "30":
        period_days = 30

    title_search = request.args.get("search", "").strip()

    total, entries, available_types = db.get_confirmed_entries(
        instance_url_filter=instance_filter,
        type_filter=type_filter,
        offset=offset,
        limit=limit,
        period_days=period_days,
        title_search=title_search,
    )

    # Resolve totals for the requested period.
    # Lifetime uses the protected lifetime_totals table which persists through
    # Clear Stats. Rolling windows query stat_entries directly so they reflect
    # any clears.
    if period == "7":
        totals = db.get_period_totals(7)
    elif period == "30":
        totals = db.get_period_totals(30)
    else:
        totals = db.get_lifetime_totals()

    all_instances = []
    for inst in cfg.get("instances", {}).get("radarr", []):
        all_instances.append({"name": inst["name"], "url": inst["url"].rstrip("/"), "app": "radarr"})
    for inst in cfg.get("instances", {}).get("sonarr", []):
        all_instances.append({"name": inst["name"], "url": inst["url"].rstrip("/"), "app": "sonarr"})

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
    from nudgarr.globals import STATUS
    db.clear_stat_entries()
    STATUS["imports_confirmed_sweep"] = {"movies": 0, "shows": 0}
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
        # Update imports_confirmed_sweep so the Sweep tab reflects the
        # confirmed imports immediately without waiting for the background loop.
        from nudgarr.globals import STATUS
        sweep_start = STATUS.get("last_sweep_start_utc")
        if sweep_start:
            STATUS["imports_confirmed_sweep"] = db.get_imports_since(sweep_start)
            db.set_state("imports_confirmed_sweep", json.dumps(STATUS["imports_confirmed_sweep"]))
    except Exception:
        logger.exception("Manual import check failed")
        return jsonify({"ok": False, "error": "Import check failed — check logs for details"}), 500
    try:
        _run_auto_exclusion_check(session, cfg)
    except Exception:
        logger.exception("Auto-exclusion check failed during manual import check")
    return jsonify({"ok": True})

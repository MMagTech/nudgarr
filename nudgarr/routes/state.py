"""
nudgarr/routes/state.py

State inspection, file downloads, and exclusion list management.

  GET  /api/state/summary                  -- entry counts and file size per instance
  GET  /api/state/raw                      -- full state dict (compat shim)
  GET  /api/state/items                    -- paginated history items with cooldown info
  POST /api/state/prune                    -- prune entries older than retention_days
  POST /api/state/clear                    -- wipe search history (preserves sweep_lifetime)
  GET  /api/file/config                    -- download config JSON
  GET  /api/file/state                     -- download state JSON (from DB)
  GET  /api/file/backup                    -- download zip of all data
  GET  /api/exclusions                     -- list exclusions with source/count/acknowledged
  GET  /api/exclusions/unacknowledged-count -- count of unseen auto-exclusions (badge)
  POST /api/exclusions/add                 -- add a manual exclusion
  POST /api/exclusions/remove              -- remove a title from exclusions
  POST /api/exclusions/acknowledge         -- mark all auto-exclusions as seen
  POST /api/exclusions/clear-auto          -- delete all auto-exclusion rows
"""

import io
import json
import logging
import os
import zipfile

import requests as _requests
from flask import Blueprint, Response, jsonify, request

from nudgarr import db
from nudgarr.auth import requires_auth
from nudgarr.config import load_or_init_config
from nudgarr.state import prune_state_by_retention, state_key

logger = logging.getLogger(__name__)

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
    overrides_enabled = bool(cfg.get("per_instance_overrides_enabled", False))

    # Build friendly name map: state_key → name
    # Build per-instance cooldown map: instance_url → effective cooldown_hours.
    # When overrides are enabled and an instance has its own cooldown_hours set,
    # that value is used instead of the global so eligible_again reflects the
    # same cooldown the sweep actually enforces.
    name_map = {}
    cooldown_map = {}
    for cur_app in ("radarr", "sonarr"):
        for inst in cfg.get("instances", {}).get(cur_app, []):
            sk = state_key(inst["name"], inst["url"])
            name_map[sk] = inst["name"]
            url = inst["url"].rstrip("/")
            if overrides_enabled:
                ov_cooldown = inst.get("overrides", {}).get("cooldown_hours")
                cooldown_map[url] = int(ov_cooldown) if ov_cooldown is not None else cooldown_hours
            else:
                cooldown_map[url] = cooldown_hours

    total, items = db.get_search_history(
        app_filter=app_name,
        instance_key=inst_key,
        offset=offset,
        limit=limit,
        cooldown_hours=cooldown_hours,
        instance_name_map=name_map,
        cooldown_map=cooldown_map,
    )
    return jsonify({"total": total, "items": items})


@bp.post("/api/state/prune")
@requires_auth
def api_state_prune():
    cfg = load_or_init_config()
    removed = prune_state_by_retention(int(cfg.get("state_retention_days", 180)))
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
    from nudgarr.constants import CONFIG_FILE, DB_FILE
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if os.path.exists(CONFIG_FILE):
            zf.write(CONFIG_FILE, "nudgarr-config.json")
        if os.path.exists(DB_FILE):
            zf.write(DB_FILE, "nudgarr.db")
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
    """Return all exclusion rows including source, search_count, and acknowledged fields."""
    return jsonify(db.get_exclusions())


@bp.get("/api/exclusions/unacknowledged-count")
@requires_auth
def api_exclusions_unacknowledged_count():
    """Return the count of auto-exclusions not yet acknowledged by the user.
    Drives the status bar badge — returns 0 when the badge should be hidden.
    """
    return jsonify({"count": db.get_unacknowledged_count()})


@bp.post("/api/exclusions/add")
@requires_auth
def api_add_exclusion():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title required"}), 400
    db.add_exclusion(title)
    return jsonify({"ok": True})


@bp.post("/api/exclusions/remove")
@requires_auth
def api_remove_exclusion():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title required"}), 400
    # Check source before removing — if auto-excluded, reset search_count so
    # the title gets a genuine fresh start and is not immediately re-excluded
    # by the import check loop on the next cycle.
    exclusions = db.get_exclusions()
    row = next((e for e in exclusions if (e.get("title") or "").lower() == title.lower()), None)
    db.remove_exclusion(title)
    if row and row.get("source") == "auto":
        db.reset_search_count_by_title(title)
    return jsonify({"ok": True})


@bp.post("/api/exclusions/acknowledge")
@requires_auth
def api_acknowledge_exclusions():
    """Mark all auto-exclusion rows as acknowledged, clearing the status bar badge."""
    db.acknowledge_all()
    return jsonify({"ok": True})


@bp.post("/api/exclusions/clear-auto")
@requires_auth
def api_clear_auto_exclusions():
    """Delete all auto-excluded entries. Manual exclusions are not affected.
    Used by the Danger Zone reset button and the auto-exclusion disabled popup.
    Returns the number of rows removed.
    """
    removed = db.clear_auto_exclusions()
    return jsonify({"ok": True, "removed": removed})


@bp.post("/api/exclusions/clear-manual")
@requires_auth
def api_clear_manual_exclusions():
    """Delete all manually excluded entries. Auto-exclusions are not affected.
    Used by the Clear Exclusions action in the History tab (Manual only option).
    Returns the number of rows removed.
    """
    removed = db.clear_manual_exclusions()
    return jsonify({"ok": True, "removed": removed})


@bp.post("/api/exclusions/clear-all")
@requires_auth
def api_clear_all_exclusions():
    """Delete all exclusion entries — both auto and manual.
    Logs unexcluded events for auto-exclusions so Intel calibration data
    is preserved. Used by the Clear Exclusions action in the History tab
    (All option). Returns the number of rows removed.
    """
    removed = db.clear_all_exclusions()
    return jsonify({"ok": True, "removed": removed})

# ── Arr link ──────────────────────────────────────────────────────────


@bp.get("/api/arr-link")
@requires_auth
def api_arr_link():
    """
    Resolve a Radarr/Sonarr item ID to a direct UI URL in the configured instance.
    For Sonarr, series_id must be supplied — item_id is the episode ID and cannot
    be used to look up the series slug.
    Returns {ok: true, url: "http://..."} or {ok: false, error: "..."}.
    """
    app_name = request.args.get("app", "").lower()
    instance_name = request.args.get("instance", "").strip()
    item_id = request.args.get("item_id", "").strip()
    series_id = request.args.get("series_id", "").strip()

    if app_name not in ("radarr", "sonarr") or not instance_name or not item_id:
        return jsonify({"ok": False, "error": "app, instance, and item_id are required"}), 400

    cfg = load_or_init_config()
    instances = cfg.get("instances", {}).get(app_name, [])
    inst = next((i for i in instances if i.get("name") == instance_name), None)
    if not inst:
        return jsonify({"ok": False, "error": "Instance not found"}), 404

    base_url = inst["url"].rstrip("/")
    key = inst["key"]

    try:
        if app_name == "radarr":
            r = _requests.get(
                f"{base_url}/api/v3/movie/{item_id}",
                headers={"X-Api-Key": key},
                timeout=10,
            )
            r.raise_for_status()
            slug = r.json().get("titleSlug", "")
            if not slug:
                return jsonify({"ok": False, "error": "No titleSlug in response"}), 502
            return jsonify({"ok": True, "url": f"{base_url}/movie/{slug}"})
        else:
            lookup_id = series_id if series_id else item_id
            r = _requests.get(
                f"{base_url}/api/v3/series/{lookup_id}",
                headers={"X-Api-Key": key},
                timeout=10,
            )
            r.raise_for_status()
            slug = r.json().get("titleSlug", "")
            if not slug:
                return jsonify({"ok": False, "error": "No titleSlug in response"}), 502
            return jsonify({"ok": True, "url": f"{base_url}/series/{slug}"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 502

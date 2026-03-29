"""
nudgarr/routes/cf_scores.py

CF Score tab API routes.

  GET  /api/cf-scores/status   -- aggregate stats and per-instance coverage
  GET  /api/cf-scores/entries  -- items below cutoff for the UI table
  POST /api/cf-scores/scan     -- trigger an immediate out-of-schedule sync
  POST /api/cf-scores/reset    -- clear the CF score index (Reset CF Index)

All routes require authentication.  The scan route fires the syncer in a
background thread so it does not block the HTTP response.
"""

import json
import logging
import threading

import requests
from flask import Blueprint, jsonify, request

from nudgarr import db
from nudgarr.auth import requires_auth
from nudgarr.cf_score_syncer import CF_SYNC_PROGRESS_PREFIX, CustomFormatScoreSyncer
from nudgarr.config import load_or_init_config
from nudgarr.globals import STATUS

logger = logging.getLogger(__name__)

bp = Blueprint("cf_scores", __name__)

# Shared syncer instance reused across scan calls
_syncer = CustomFormatScoreSyncer()
# Lock prevents overlapping manual scan requests
_scan_lock = threading.Lock()


# ── GET /api/cf-scores/status ─────────────────────────────────────────

@bp.get("/api/cf-scores/status")
@requires_auth
def api_cf_scores_status():
    """Return CF Score tab status payload.

    Includes:
      enabled:         Whether cf_score_enabled is True in config
      stats:           Aggregate counts (total_indexed, below_cutoff, passing)
      instances:       Per-instance sync coverage for the ring charts
      scan_in_progress: Whether a manual Scan Library is currently running
    """
    try:
        cfg = load_or_init_config()
        enabled = bool(cfg.get("cf_score_enabled", False))
        stats = db.get_cf_score_stats()
        instances = db.get_cf_score_instance_stats()

        # Enrich per-instance data with human-readable name and app from config
        instance_map = {}
        for app_name in ("radarr", "sonarr"):
            for inst in cfg.get("instances", {}).get(app_name, []):
                key = f"{app_name}|{inst['url'].rstrip('/')}"
                instance_map[key] = {
                    "app": app_name,
                    "name": inst.get("name", key),
                }

        enriched_instances = []
        for row in instances:
            meta = instance_map.get(row["arr_instance_id"], {})
            # Read live sync progress from nudgarr_state for the ring chart
            progress_raw = db.get_state(CF_SYNC_PROGRESS_PREFIX + row["arr_instance_id"])
            try:
                sync_progress = json.loads(progress_raw) if progress_raw else None
            except (ValueError, TypeError):
                sync_progress = None
            enriched_instances.append({
                **row,
                "app": meta.get("app", "unknown"),
                "instance_name": meta.get("name", row["arr_instance_id"]),
                "sync_progress": sync_progress,
            })

        return jsonify({
            "enabled": enabled,
            "stats": stats,
            "instances": enriched_instances,
            "scan_in_progress": _scan_lock.locked(),
        })
    except Exception:
        logger.exception("[CF Scores] GET /api/cf-scores/status failed")
        return jsonify({"error": "Status unavailable -- check logs for details."}), 500


# ── GET /api/cf-scores/entries ────────────────────────────────────────

@bp.get("/api/cf-scores/entries")
@requires_auth
def api_cf_scores_entries():
    """Return items below CF cutoff for the UI table.

    Query params:
      app     -- filter by 'radarr' or 'sonarr' (optional; omit for all)
      limit   -- max rows to return (default 200, max 200)
      offset  -- row offset for scrollable overflow (default 0)

    Results are ordered worst gap first (largest gap = furthest below cutoff).
    """
    try:
        cfg = load_or_init_config()
        app_filter = request.args.get("app", "").lower().strip()
        instance_id_filter = request.args.get("instance_id", "").strip()
        try:
            limit = min(int(request.args.get("limit", 200)), 200)
            offset = max(int(request.args.get("offset", 0)), 0)
        except (ValueError, TypeError):
            limit, offset = 200, 0

        # instance_id filter takes priority over app filter
        if instance_id_filter:
            arr_instance_id = instance_id_filter
            item_type = None
        else:
            arr_instance_id = None
            item_type = None
            if app_filter == "radarr":
                item_type = "movie"
            elif app_filter == "sonarr":
                item_type = "episode"
        entries = db.get_cf_score_entries(
            arr_instance_id=arr_instance_id,
            item_type=item_type,
            limit=limit,
            offset=offset,
        )

        # Enrich entries with human-readable instance name
        instance_map = {}
        for an in ("radarr", "sonarr"):
            for inst in cfg.get("instances", {}).get(an, []):
                key = f"{an}|{inst['url'].rstrip('/')}"
                instance_map[key] = inst.get("name", key)

        for entry in entries:
            entry["instance_name"] = instance_map.get(
                entry.get("arr_instance_id", ""), entry.get("arr_instance_id", "")
            )

        return jsonify({"entries": entries, "total": len(entries)})
    except Exception:
        logger.exception("[CF Scores] GET /api/cf-scores/entries failed")
        return jsonify({"error": "Entries unavailable -- check logs for details."}), 500


# ── POST /api/cf-scores/scan ──────────────────────────────────────────

@bp.post("/api/cf-scores/scan")
@requires_auth
def api_cf_scores_scan():
    """Trigger an immediate out-of-schedule library sync.

    Runs the syncer in a background thread so the HTTP response returns
    immediately.  Returns 409 if a scan is already in progress.
    Returns 400 if CF Score Scan is not enabled in config.
    """
    cfg = load_or_init_config()
    if not cfg.get("cf_score_enabled", False):
        return jsonify({"error": "CF Score Scan is not enabled."}), 400

    if STATUS.get("run_in_progress", False):
        return jsonify({"error": "A sweep is in progress -- try again after it completes."}), 409

    if _scan_lock.locked():
        return jsonify({"error": "A scan is already in progress."}), 409

    def _run_scan():
        """Background thread: acquire lock, run syncer, release lock."""
        if not _scan_lock.acquire(blocking=False):
            return
        try:
            session = requests.Session()
            current_cfg = load_or_init_config()
            logger.info("[CF Scores] Manual Scan Library triggered")
            _syncer.run(current_cfg, session)
            logger.info("[CF Scores] Manual Scan Library complete")
        except Exception:
            logger.exception("[CF Scores] Manual Scan Library failed")
        finally:
            _scan_lock.release()

    t = threading.Thread(target=_run_scan, daemon=True, name="cf-score-manual-scan")
    t.start()
    return jsonify({"ok": True, "message": "Scan started."})


# ── POST /api/cf-scores/reset ─────────────────────────────────────────

@bp.post("/api/cf-scores/reset")
@requires_auth
def api_cf_scores_reset():
    """Clear the CF score index (Reset CF Index).

    Truncates cf_score_entries entirely.  The next scheduled or manual
    Scan Library run will rebuild the index from scratch.
    Returns 409 if a scan is currently in progress to avoid clearing
    an index that is mid-build.
    """
    if _scan_lock.locked():
        return jsonify({"error": "A scan is in progress -- wait for it to finish before resetting."}), 409

    try:
        removed = db.clear_cf_score_index()
        logger.info("[CF Scores] Index reset -- %d entries cleared", removed)
        return jsonify({"ok": True, "removed": removed})
    except Exception:
        logger.exception("[CF Scores] POST /api/cf-scores/reset failed")
        return jsonify({"error": "Reset failed -- check logs for details."}), 500

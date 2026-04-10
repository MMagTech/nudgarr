"""
nudgarr/routes/arr.py

Arr instance proxy endpoints — fetch tags and quality profiles from
configured Radarr and Sonarr instances server-side. API keys never
leave the server.

  GET /api/arr/tags     -- fetch all tags for one instance
  GET /api/arr/profiles -- fetch all quality profiles for one instance
  POST /api/arr/filters -- persist sweep tag/profile filters for one instance
"""

import logging

import requests as req_lib

from flask import Blueprint, jsonify, request

from nudgarr.auth import requires_auth
from nudgarr.arr_clients import arr_get_tag_map
from nudgarr.config import load_or_init_config, validate_config
from nudgarr.constants import CONFIG_FILE
from nudgarr.globals import STATUS
from nudgarr.utils import req, save_json_atomic

logger = logging.getLogger(__name__)

bp = Blueprint("arr", __name__)


def _get_instance(kind: str, idx: int) -> dict | None:
    """Return the instance dict at cfg.instances[kind][idx], or None if not found."""
    cfg = load_or_init_config()
    instances = cfg.get("instances", {}).get(kind, [])
    if idx < 0 or idx >= len(instances):
        return None
    return instances[idx]


@bp.get("/api/arr/tags")
@requires_auth
def api_arr_tags():
    kind = request.args.get("kind", "")
    try:
        idx = int(request.args.get("idx", -1))
    except (TypeError, ValueError):
        idx = -1
    if kind not in ("radarr", "sonarr") or idx < 0:
        return jsonify({"ok": False, "error": "Invalid kind or idx"}), 400
    inst = _get_instance(kind, idx)
    if inst is None:
        return jsonify({"ok": False, "error": "Instance not found"}), 404
    try:
        session = req_lib.Session()
        tag_map = arr_get_tag_map(session, inst["url"], inst["key"])
        tags = [{"id": tid, "label": label} for tid, label in sorted(tag_map.items())]
        return jsonify({"ok": True, "tags": tags})
    except Exception:
        logger.warning("api_arr_tags failed for %s idx=%d", kind, idx, exc_info=True)
        return jsonify({"ok": False, "error": "Failed to fetch tags — check instance connectivity"}), 502


@bp.get("/api/arr/profiles")
@requires_auth
def api_arr_profiles():
    kind = request.args.get("kind", "")
    try:
        idx = int(request.args.get("idx", -1))
    except (TypeError, ValueError):
        idx = -1
    if kind not in ("radarr", "sonarr") or idx < 0:
        return jsonify({"ok": False, "error": "Invalid kind or idx"}), 400
    inst = _get_instance(kind, idx)
    if inst is None:
        return jsonify({"ok": False, "error": "Instance not found"}), 404
    try:
        session = req_lib.Session()
        endpoint = f"{inst['url'].rstrip('/')}/api/v3/qualityProfile"
        data = req(session, "GET", endpoint, inst["key"])
        profiles = []
        if isinstance(data, list):
            for p in data:
                if isinstance(p.get("id"), int) and isinstance(p.get("name"), str):
                    profiles.append({"id": p["id"], "name": p["name"]})
        return jsonify({"ok": True, "profiles": profiles})
    except Exception:
        logger.warning("api_arr_profiles failed for %s idx=%d", kind, idx, exc_info=True)
        return jsonify({"ok": False, "error": "Failed to fetch profiles — check instance connectivity"}), 502


@bp.post("/api/arr/filters")
@requires_auth
def api_arr_filters():
    """Persist sweep_filters (excluded tags / quality profiles) for one instance.

    Body: { kind, idx, sweep_filters }
    sweep_filters may use excluded_tags / excluded_profiles (canonical) or
    excluded_tag_ids / excluded_profile_ids (UI alias) — all stored as
    excluded_tags and excluded_profiles in config (matches sweep / syncer).
    """
    data = request.get_json(force=True, silent=True) or {}
    kind = data.get("kind", "")
    idx = data.get("idx", -1)
    sf = data.get("sweep_filters")
    if kind not in ("radarr", "sonarr") or not isinstance(idx, int) or idx < 0:
        return jsonify({"ok": False, "error": "Invalid kind or idx"}), 400
    if not isinstance(sf, dict):
        return jsonify({"ok": False, "error": "sweep_filters must be an object"}), 400
    tags = sf.get("excluded_tags") or sf.get("excluded_tag_ids") or []
    profiles = sf.get("excluded_profiles") or sf.get("excluded_profile_ids") or []
    try:
        tags_norm = [int(t) for t in tags]
        profiles_norm = [int(p) for p in profiles]
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Tag and profile IDs must be integers"}), 400

    cfg = load_or_init_config()
    instances = cfg.get("instances", {}).get(kind, [])
    if idx >= len(instances):
        return jsonify({"ok": False, "error": "Instance not found"}), 404
    instances[idx]["sweep_filters"] = {
        "excluded_tags": tags_norm,
        "excluded_profiles": profiles_norm,
    }
    ok, errs = validate_config(cfg)
    if not ok:
        return jsonify({"ok": False, "errors": errs}), 400
    try:
        save_json_atomic(CONFIG_FILE, cfg, pretty=True)
    except Exception:
        logger.exception("Failed to write config in api_arr_filters")
        return jsonify({"ok": False, "error": "Failed to write config — check disk space and permissions"}), 500
    STATUS["cf_filters_changed"] = True
    return jsonify({"ok": True})

"""
nudgarr/routes/arr.py

Arr instance proxy endpoints — fetch tags and quality profiles from
configured Radarr and Sonarr instances server-side. API keys never
leave the server.

  GET /api/arr/tags     -- fetch all tags for one instance
  GET /api/arr/profiles -- fetch all quality profiles for one instance
"""

import logging

import requests as req_lib

from flask import Blueprint, jsonify, request

from nudgarr.auth import requires_auth
from nudgarr.arr_clients import arr_get_tag_map
from nudgarr.config import load_or_init_config
from nudgarr.utils import req

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

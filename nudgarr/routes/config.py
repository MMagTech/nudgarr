"""
nudgarr/routes/config.py

Configuration management endpoints.

  GET  /api/config               -- return full config
  POST /api/config               -- save full config
  POST /api/config/reset         -- reset to DEFAULT_CONFIG
  POST /api/onboarding/complete  -- mark onboarding done
  POST /api/whats-new/dismiss    -- dismiss what's new modal
  POST /api/instance/toggle      -- enable/disable one instance
"""

import threading

import requests as req_lib

from flask import Blueprint, jsonify, request

from nudgarr.auth import requires_auth
from nudgarr.config import deep_copy, load_or_init_config, validate_config
from nudgarr.constants import CONFIG_FILE, VERSION
from nudgarr.globals import STATUS
from nudgarr.utils import req, save_json_atomic

bp = Blueprint("config", __name__)


@bp.get("/api/config")
@requires_auth
def api_get_config():
    return jsonify(load_or_init_config())


@bp.post("/api/config")
@requires_auth
def api_set_config():
    cfg = request.get_json(force=True, silent=True)
    if not isinstance(cfg, dict):
        return jsonify({"ok": False, "error": "Body must be JSON object"}), 400
    ok, errs = validate_config(cfg)
    if not ok:
        return jsonify({"ok": False, "errors": errs}), 400
    save_json_atomic(CONFIG_FILE, cfg, pretty=True)
    return jsonify({"ok": True, "message": "Config saved", "config_file": CONFIG_FILE})


@bp.post("/api/config/reset")
@requires_auth
def api_reset_config():
    from nudgarr.constants import DEFAULT_CONFIG
    cfg = deep_copy(DEFAULT_CONFIG)
    save_json_atomic(CONFIG_FILE, cfg, pretty=True)
    return jsonify({"ok": True})


@bp.post("/api/onboarding/complete")
@requires_auth
def api_onboarding_complete():
    cfg = load_or_init_config()
    cfg["onboarding_complete"] = True
    cfg["last_seen_version"] = VERSION
    save_json_atomic(CONFIG_FILE, cfg, pretty=True)
    return jsonify({"ok": True})


@bp.post("/api/whats-new/dismiss")
@requires_auth
def api_whats_new_dismiss():
    cfg = load_or_init_config()
    cfg["last_seen_version"] = VERSION
    save_json_atomic(CONFIG_FILE, cfg, pretty=True)
    return jsonify({"ok": True})


@bp.post("/api/instance/toggle")
@requires_auth
def api_instance_toggle():
    data = request.get_json(force=True, silent=True) or {}
    kind = data.get("kind", "")
    idx = data.get("idx", -1)
    if kind not in ("radarr", "sonarr") or not isinstance(idx, int) or idx < 0:
        return jsonify({"ok": False, "error": "Invalid kind or idx"}), 400
    cfg = load_or_init_config()
    instances = cfg.get("instances", {}).get(kind, [])
    if idx >= len(instances):
        return jsonify({"ok": False, "error": "Instance not found"}), 404
    inst = instances[idx]
    was_enabled = inst.get("enabled", True)
    inst["enabled"] = not was_enabled
    now_enabled = inst["enabled"]
    save_json_atomic(CONFIG_FILE, cfg, pretty=True)
    name = inst.get("name", "")
    key = f"{kind}|{name}"
    if now_enabled:
        # Trigger a fresh health ping for this instance
        def _ping():
            s = req_lib.Session()
            try:
                req(s, "GET", f"{inst['url'].rstrip('/')}/api/v3/system/status", inst["key"], timeout=5)
                STATUS["instance_health"][key] = "ok"
            except Exception:
                STATUS["instance_health"][key] = "bad"
        threading.Thread(target=_ping, daemon=True).start()
    else:
        STATUS["instance_health"][key] = "disabled"
    return jsonify({"ok": True, "enabled": now_enabled})

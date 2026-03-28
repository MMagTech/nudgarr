"""
nudgarr/routes/config.py

Configuration management endpoints.

  GET  /api/config               -- return config with API keys masked
  POST /api/config               -- save full config (masked keys preserved)
  POST /api/config/reset         -- reset to DEFAULT_CONFIG
  POST /api/onboarding/complete  -- mark onboarding done
  POST /api/whats-new/dismiss    -- dismiss what's new modal
  POST /api/instance/toggle      -- enable/disable one instance
  POST /api/instance/overrides   -- save or clear overrides for one instance
  POST /api/overrides/toggle     -- enable/disable per-instance overrides globally
"""

import threading

import requests as req_lib

from flask import Blueprint, jsonify, request

from nudgarr.auth import requires_auth
from nudgarr import db
from nudgarr.config import deep_copy, load_or_init_config, validate_config
from nudgarr.constants import CONFIG_FILE, VERSION
from nudgarr.globals import STATUS
from nudgarr.utils import req, save_json_atomic

import logging

logger = logging.getLogger(__name__)


bp = Blueprint("config", __name__)

# Sentinel prefix used to represent a masked but unchanged API key.
# The last 4 characters of the real key are appended for user reference.
_KEY_MASK_PREFIX = "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022"  # ••••••••


def _mask_config(cfg: dict) -> dict:
    """Return a copy of cfg with all instance API keys masked."""
    import copy
    out = copy.deepcopy(cfg)
    for app_name in ("radarr", "sonarr"):
        for inst in out.get("instances", {}).get(app_name, []):
            raw = inst.get("key", "")
            if raw:
                inst["key"] = _KEY_MASK_PREFIX + raw[-4:]
    return out


def _is_masked(key: str) -> bool:
    return key.startswith(_KEY_MASK_PREFIX)


def _restore_keys(incoming: dict, stored: dict) -> None:
    """Replace masked keys in incoming with real keys from stored config."""
    for app_name in ("radarr", "sonarr"):
        incoming_insts = incoming.get("instances", {}).get(app_name, [])
        stored_insts = stored.get("instances", {}).get(app_name, [])
        stored_by_name = {i.get("name", ""): i for i in stored_insts}
        stored_by_url = {i.get("url", "").rstrip("/"): i for i in stored_insts}
        for inst in incoming_insts:
            if _is_masked(inst.get("key", "")):
                # Try name first, fall back to URL for rename scenarios
                match = stored_by_name.get(inst.get("name", "")) or stored_by_url.get(inst.get("url", "").rstrip("/"))
                real = (match or {}).get("key", "")
                if real:
                    inst["key"] = real


@bp.get("/api/config")
@requires_auth
def api_get_config():
    cfg = load_or_init_config()
    out = _mask_config(cfg)
    # Collect reset keys from both the loaded config (persisted across restarts)
    # and STATUS (set in the same session before any restart).
    reset_keys = list(cfg.get("_config_reset_keys") or [])
    for k in (STATUS.get("config_reset_keys") or []):
        if k not in reset_keys:
            reset_keys.append(k)
    STATUS["config_reset_keys"] = []
    if reset_keys:
        out["_config_reset_keys"] = reset_keys
        logger.info("[api/config] Attached config_reset_keys to response: %s", reset_keys)
        # Strip _config_reset_keys from disk now that the browser has received it
        from nudgarr.utils import save_json_atomic as _save
        from nudgarr.constants import CONFIG_FILE as _cf
        clean = {k: v for k, v in cfg.items() if k != "_config_reset_keys"}
        _save(_cf, clean, pretty=True)
    else:
        logger.debug("[api/config] config_reset_keys in STATUS: []")
    return jsonify(out)


@bp.post("/api/config")
@requires_auth
def api_set_config():
    cfg = request.get_json(force=True, silent=True)
    if not isinstance(cfg, dict):
        return jsonify({"ok": False, "error": "Body must be JSON object"}), 400
    stored = load_or_init_config()
    # Restore any masked keys before validation and save
    _restore_keys(cfg, stored)
    # Detect instance renames (by URL) before saving
    renames = []
    for app_name in ("radarr", "sonarr"):
        stored_by_url = {
            i.get("url", "").rstrip("/"): i.get("name", "")
            for i in stored.get("instances", {}).get(app_name, [])
        }
        for inst in cfg.get("instances", {}).get(app_name, []):
            url = inst.get("url", "").rstrip("/")
            old_name = stored_by_url.get(url)
            new_name = inst.get("name", "")
            if old_name and old_name != new_name:
                renames.append((app_name, url, new_name))
    ok, errs = validate_config(cfg)
    if not ok:
        return jsonify({"ok": False, "errors": errs}), 400
    cfg.pop("_config_reset_keys", None)
    try:
        save_json_atomic(CONFIG_FILE, cfg, pretty=True)
    except Exception:
        logger.exception("Failed to write config in api_set_config")
        return jsonify({"ok": False, "error": "Failed to write config — check disk space and permissions"}), 500
    # Apply renames to history and imports
    for app_name, url, new_name in renames:
        db.rename_instance_in_history(app_name, url, new_name)

    # Update next_run_utc in STATUS immediately so UI reflects new schedule without
    # waiting for the scheduler loop to wake and detect the config change.
    cron_expression = cfg.get("cron_expression", "0 */6 * * *")
    scheduler_enabled = bool(cfg.get("scheduler_enabled", False))
    if scheduler_enabled and cron_expression:
        try:
            from nudgarr.scheduler import _next_cron_utc
            STATUS["next_run_utc"] = _next_cron_utc(cron_expression)
        except Exception:
            pass
    else:
        STATUS["next_run_utc"] = None

    # Apply log level immediately so it takes effect without restart
    try:
        from nudgarr.log_setup import apply_log_level
        apply_log_level(cfg.get("log_level", "INFO"))
    except Exception:
        pass

    return jsonify({"ok": True, "message": "Config saved", "config_file": CONFIG_FILE})


@bp.post("/api/config/reset")
@requires_auth
def api_reset_config():
    from nudgarr.constants import DEFAULT_CONFIG
    cfg = deep_copy(DEFAULT_CONFIG)
    try:
        save_json_atomic(CONFIG_FILE, cfg, pretty=True)
    except Exception:
        logger.exception("Failed to write config in api_reset_config")
        return jsonify({"ok": False, "error": "Failed to write config — check disk space and permissions"}), 500
    return jsonify({"ok": True})


@bp.post("/api/onboarding/complete")
@requires_auth
def api_onboarding_complete():
    cfg = load_or_init_config()
    cfg["onboarding_complete"] = True
    cfg["last_seen_version"] = VERSION
    try:
        save_json_atomic(CONFIG_FILE, cfg, pretty=True)
    except Exception:
        logger.exception("Failed to write config in api_onboarding_complete")
        return jsonify({"ok": False, "error": "Failed to write config — check disk space and permissions"}), 500
    return jsonify({"ok": True})


@bp.post("/api/whats-new/dismiss")
@requires_auth
def api_whats_new_dismiss():
    cfg = load_or_init_config()
    cfg["last_seen_version"] = VERSION
    try:
        save_json_atomic(CONFIG_FILE, cfg, pretty=True)
    except Exception:
        logger.exception("Failed to write config in api_whats_new_dismiss")
        return jsonify({"ok": False, "error": "Failed to write config — check disk space and permissions"}), 500
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
    try:
        save_json_atomic(CONFIG_FILE, cfg, pretty=True)
    except Exception:
        logger.exception("Failed to write config in api_instance_toggle")
        return jsonify({"ok": False, "error": "Failed to write config — check disk space and permissions"}), 500
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


@bp.post("/api/instance/overrides")
@requires_auth
def api_instance_overrides():
    """Save or clear the overrides block for one instance.

    Body: { kind, idx, overrides }
    overrides is a sparse dict — only fields to override are present.
    Pass an empty dict {} to clear all overrides for that instance.
    """
    data = request.get_json(force=True, silent=True) or {}
    kind = data.get("kind", "")
    idx = data.get("idx", -1)
    overrides = data.get("overrides", {})
    if kind not in ("radarr", "sonarr") or not isinstance(idx, int) or idx < 0:
        return jsonify({"ok": False, "error": "Invalid kind or idx"}), 400
    if not isinstance(overrides, dict):
        return jsonify({"ok": False, "error": "overrides must be an object"}), 400
    cfg = load_or_init_config()
    instances = cfg.get("instances", {}).get(kind, [])
    if idx >= len(instances):
        return jsonify({"ok": False, "error": "Instance not found"}), 404
    if overrides:
        instances[idx]["overrides"] = overrides
    else:
        instances[idx].pop("overrides", None)
    try:
        save_json_atomic(CONFIG_FILE, cfg, pretty=True)
    except Exception:
        logger.exception("Failed to write config in api_instance_overrides")
        return jsonify({"ok": False, "error": "Failed to write config — check disk space and permissions"}), 500
    return jsonify({"ok": True})


@bp.post("/api/overrides/toggle")
@requires_auth
def api_overrides_toggle():
    """Enable or disable per-instance overrides globally.

    Body: { enabled: bool }
    Also marks per_instance_overrides_seen on first enable.
    """
    data = request.get_json(force=True, silent=True) or {}
    enabled = data.get("enabled")
    if not isinstance(enabled, bool):
        return jsonify({"ok": False, "error": "enabled must be boolean"}), 400
    cfg = load_or_init_config()
    cfg["per_instance_overrides_enabled"] = enabled
    if enabled and not cfg.get("per_instance_overrides_seen", False):
        cfg["per_instance_overrides_seen"] = True
    try:
        save_json_atomic(CONFIG_FILE, cfg, pretty=True)
    except Exception:
        logger.exception("Failed to write config in api_overrides_toggle")
        return jsonify({"ok": False, "error": "Failed to write config — check disk space and permissions"}), 500
    return jsonify({"ok": True, "enabled": enabled})

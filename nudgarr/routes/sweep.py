"""
nudgarr/routes/sweep.py

Sweep control and instance connection testing.

  GET  /api/status        -- current scheduler status and last summary
  POST /api/run-now       -- request an immediate sweep
  POST /api/test          -- test connections to all configured instances (from disk)
  POST /api/test-instance -- test a single instance against in-memory values
"""

import os
import datetime

import requests as req_lib

from flask import Blueprint, jsonify, request

from nudgarr import db
from nudgarr.auth import requires_auth
from nudgarr.config import load_or_init_config
from nudgarr.globals import RUN_LOCK, STATUS
from nudgarr.utils import mask_url, req, is_safe_url

bp = Blueprint("sweep", __name__)


def _container_time_str() -> str:
    """Return current container time as 'HH:MM TZ' using TZ env var."""
    tz_name = os.environ.get("TZ", "UTC")
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo(tz_name)
        now = datetime.datetime.now(tz)
        abbr = now.strftime("%Z") or tz_name
        return now.strftime("%H:%M") + " " + abbr
    except Exception:
        now = datetime.datetime.utcnow()
        return now.strftime("%H:%M") + " UTC"


@bp.get("/api/status")
@requires_auth
def api_status():
    payload = dict(STATUS)
    payload["sweep_lifetime"] = db.get_sweep_lifetime()
    payload["container_time"] = _container_time_str()
    return jsonify(payload)


@bp.post("/api/run-now")
@requires_auth
def api_run_now():
    with RUN_LOCK:
        STATUS["run_requested"] = True
    return jsonify({"ok": True})


@bp.post("/api/test")
@requires_auth
def api_test():
    cfg = load_or_init_config()
    session = req_lib.Session()
    results = {"radarr": [], "sonarr": []}

    for inst in cfg.get("instances", {}).get("radarr", []):
        if not inst.get("enabled", True):
            STATUS["instance_health"][f"radarr|{inst['name']}"] = "disabled"
            results["radarr"].append({
                "name": inst["name"], "url": mask_url(inst["url"]), "ok": True, "disabled": True
            })
            continue
        try:
            if not is_safe_url(inst["url"]):
                results["radarr"].append({
                    "name": inst["name"], "url": mask_url(inst["url"]),
                    "ok": False, "error": "Invalid or disallowed URL",
                })
                STATUS["instance_health"][f"radarr|{inst['name']}"] = "bad"
                continue
            url = f"{inst['url'].rstrip('/')}/api/v3/system/status"
            data = req(session, "GET", url, inst["key"])
            results["radarr"].append({
                "name": inst["name"], "url": mask_url(inst["url"]), "ok": True,
                "version": data.get("version") if isinstance(data, dict) else None,
            })
            STATUS["instance_health"][f"radarr|{inst['name']}"] = "ok"
        except Exception:
            results["radarr"].append({
                "name": inst.get("name"), "url": mask_url(inst.get("url", "")),
                "ok": False, "error": "Connection failed — check URL and API key",
            })
            STATUS["instance_health"][f"radarr|{inst.get('name', '')}"] = "bad"

    for inst in cfg.get("instances", {}).get("sonarr", []):
        if not inst.get("enabled", True):
            STATUS["instance_health"][f"sonarr|{inst['name']}"] = "disabled"
            results["sonarr"].append({
                "name": inst["name"], "url": mask_url(inst["url"]), "ok": True, "disabled": True
            })
            continue
        try:
            if not is_safe_url(inst["url"]):
                results["sonarr"].append({
                    "name": inst["name"], "url": mask_url(inst["url"]),
                    "ok": False, "error": "Invalid or disallowed URL",
                })
                STATUS["instance_health"][f"sonarr|{inst['name']}"] = "bad"
                continue
            url = f"{inst['url'].rstrip('/')}/api/v3/system/status"
            data = req(session, "GET", url, inst["key"])
            results["sonarr"].append({
                "name": inst["name"], "url": mask_url(inst["url"]), "ok": True,
                "version": data.get("version") if isinstance(data, dict) else None,
            })
            STATUS["instance_health"][f"sonarr|{inst['name']}"] = "ok"
        except Exception:
            results["sonarr"].append({
                "name": inst.get("name"), "url": mask_url(inst.get("url", "")),
                "ok": False, "error": "Connection failed — check URL and API key",
            })
            STATUS["instance_health"][f"sonarr|{inst.get('name', '')}"] = "bad"

    return jsonify({"ok": True, "results": results})


def _test_single_instance(session, app_name: str, inst: dict, results: dict) -> None:
    name = inst.get("name", "")
    if not inst.get("enabled", True):
        STATUS["instance_health"][f"{app_name}|{name}"] = "disabled"
        results[app_name].append({
            "name": name, "url": mask_url(inst.get("url", "")), "ok": True, "disabled": True
        })
        return
    try:
        if not is_safe_url(inst.get("url", "")):
            results[app_name].append({
                "name": name, "url": mask_url(inst.get("url", "")),
                "ok": False, "error": "Invalid or disallowed URL",
            })
            STATUS["instance_health"][f"{app_name}|{name}"] = "bad"
            return
        url = f"{inst['url'].rstrip('/')}/api/v3/system/status"
        data = req(session, "GET", url, inst.get("key", ""))
        results[app_name].append({
            "name": name, "url": mask_url(inst["url"]), "ok": True,
            "version": data.get("version") if isinstance(data, dict) else None,
        })
        STATUS["instance_health"][f"{app_name}|{name}"] = "ok"
    except Exception:
        results[app_name].append({
            "name": name, "url": mask_url(inst.get("url", "")),
            "ok": False, "error": "Connection failed — check URL and API key",
        })
        STATUS["instance_health"][f"{app_name}|{name}"] = "bad"


@bp.post("/api/test-instance")
@requires_auth
def api_test_instance():
    data = request.get_json(force=True, silent=True) or {}
    kind = data.get("kind", "")
    instances = data.get("instances", {})
    if kind not in ("radarr", "sonarr"):
        return jsonify({"ok": False, "error": "Invalid kind"}), 400
    stored = load_or_init_config()
    stored_insts = {i.get("name", ""): i for i in stored.get("instances", {}).get(kind, [])}
    session = req_lib.Session()
    results = {kind: []}
    for inst in instances.get(kind, []):
        key = inst.get("key", "")
        if key.startswith("••••••••"):
            real = stored_insts.get(inst.get("name", ""), {}).get("key", "")
            if real:
                inst = dict(inst)
                inst["key"] = real
        _test_single_instance(session, kind, inst, results)
    return jsonify({"ok": True, "results": results})

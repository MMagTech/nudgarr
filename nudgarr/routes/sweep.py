"""
nudgarr/routes/sweep.py

Sweep control and instance connection testing.

  GET  /api/status  -- current scheduler status and last summary
  POST /api/run-now -- request an immediate sweep
  POST /api/test    -- test connections to all configured instances
"""

import requests as req_lib

from flask import Blueprint, jsonify

from nudgarr.auth import requires_auth
from nudgarr.config import load_or_init_config
from nudgarr.globals import RUN_LOCK, STATUS
from nudgarr.state import load_state
from nudgarr.utils import mask_url, req

bp = Blueprint("sweep", __name__)


@bp.get("/api/status")
@requires_auth
def api_status():
    st = load_state()
    payload = dict(STATUS)
    payload["sweep_lifetime"] = st.get("sweep_lifetime", {})
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
            url = f"{inst['url'].rstrip('/')}/api/v3/system/status"
            data = req(session, "GET", url, inst["key"])
            results["radarr"].append({
                "name": inst["name"], "url": mask_url(inst["url"]), "ok": True,
                "version": data.get("version") if isinstance(data, dict) else None,
            })
            STATUS["instance_health"][f"radarr|{inst['name']}"] = "ok"
        except Exception as e:
            results["radarr"].append({
                "name": inst.get("name"), "url": mask_url(inst.get("url", "")),
                "ok": False, "error": str(e),
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
            url = f"{inst['url'].rstrip('/')}/api/v3/system/status"
            data = req(session, "GET", url, inst["key"])
            results["sonarr"].append({
                "name": inst["name"], "url": mask_url(inst["url"]), "ok": True,
                "version": data.get("version") if isinstance(data, dict) else None,
            })
            STATUS["instance_health"][f"sonarr|{inst['name']}"] = "ok"
        except Exception as e:
            results["sonarr"].append({
                "name": inst.get("name"), "url": mask_url(inst.get("url", "")),
                "ok": False, "error": str(e),
            })
            STATUS["instance_health"][f"sonarr|{inst.get('name', '')}"] = "bad"

    return jsonify({"ok": True, "results": results})

"""
main.py — Nudgarr entry point.

Wires everything together:
  1. Registers Flask route blueprints
  2. Handles SIGTERM / SIGINT for clean shutdown
  3. Pre-populates STATUS from persisted state (so UI dots show immediately)
  4. Fires a parallel startup health-ping to all configured instances
  5. Starts the Flask UI server in a daemon thread
  6. Runs the scheduler loop in the main thread
"""

import signal
import threading
from datetime import timedelta

import requests

from nudgarr.config import load_or_init_config
from nudgarr.globals import STATUS
from nudgarr.routes import register_blueprints
from nudgarr.scheduler import print_banner, scheduler_loop, start_ui_server
from nudgarr.state import load_state
from nudgarr.utils import iso_z, req, utcnow


def main() -> None:
    register_blueprints()

    stop_flag = {"stop": False}

    def handle_signal(signum, frame):
        print("\nShutdown signal received. Stopping…")
        stop_flag["stop"] = True

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    cfg = load_or_init_config()
    print_banner(cfg)

    # Pre-populate STATUS from persisted state so UI has values immediately
    _st = load_state()
    if _st.get("last_run_utc"):
        STATUS["last_run_utc"] = _st["last_run_utc"]
    if cfg.get("scheduler_enabled"):
        _interval = int(cfg.get("run_interval_minutes", 360))
        STATUS["next_run_utc"] = iso_z(utcnow() + timedelta(minutes=_interval))

    # Background health ping — parallel, non-blocking, populates dots within ~1s
    def _startup_health_ping():
        _session = requests.Session()
        instances = []
        for _inst in cfg.get("instances", {}).get("radarr", []):
            if not _inst.get("enabled", True):
                STATUS["instance_health"][f"radarr|{_inst['name']}"] = "disabled"
            else:
                instances.append(("radarr", _inst))
        for _inst in cfg.get("instances", {}).get("sonarr", []):
            if not _inst.get("enabled", True):
                STATUS["instance_health"][f"sonarr|{_inst['name']}"] = "disabled"
            else:
                instances.append(("sonarr", _inst))

        def _ping(app_name, inst):
            try:
                _url = f"{inst['url'].rstrip('/')}/api/v3/system/status"
                req(_session, "GET", _url, inst["key"], timeout=5)
                STATUS["instance_health"][f"{app_name}|{inst['name']}"] = "ok"
            except Exception:
                STATUS["instance_health"][f"{app_name}|{inst['name']}"] = "bad"

        threads = [threading.Thread(target=_ping, args=(a, i), daemon=True) for a, i in instances]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    threading.Thread(target=_startup_health_ping, daemon=True).start()

    # Start UI in a daemon thread
    threading.Thread(target=start_ui_server, daemon=True).start()

    # Run scheduler loop in main thread
    scheduler_loop(stop_flag)

    print("Nudgarr exiting.")


if __name__ == "__main__":
    main()

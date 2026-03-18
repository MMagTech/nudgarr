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

import logging
import signal
import threading

import requests

from nudgarr import db
from nudgarr.config import load_or_init_config
from nudgarr.globals import STATUS
from nudgarr.log_setup import setup_logging
from nudgarr.routes import register_blueprints
from nudgarr.scheduler import import_check_loop, print_banner, scheduler_loop, start_ui_server
from nudgarr.utils import req

logger = logging.getLogger(__name__)


def main() -> None:
    register_blueprints()

    # Initialise database (schema creation + one-time JSON migration if needed)
    db.init_db()

    # Load config early so log_level is available before the banner prints.
    # setup_logging must be called before any nudgarr module emits a log line.
    cfg = load_or_init_config()
    setup_logging(cfg.get("log_level", "INFO"))

    stop_flag = {"stop": False}

    def handle_signal(signum, frame):
        logger.info("Shutdown signal received. Stopping...")
        stop_flag["stop"] = True

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    print_banner(cfg)

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
                logger.debug("[%s:%s] startup health ping OK", app_name, inst["name"])
            except Exception:
                STATUS["instance_health"][f"{app_name}|{inst['name']}"] = "bad"
                logger.warning("[%s:%s] startup health ping FAILED", app_name, inst["name"])

        threads = [threading.Thread(target=_ping, args=(a, i), daemon=True) for a, i in instances]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    threading.Thread(target=_startup_health_ping, daemon=True).start()

    # Start UI in a daemon thread
    threading.Thread(target=start_ui_server, daemon=True).start()

    # Start import check loop in a daemon thread — independent of sweep schedule
    threading.Thread(target=import_check_loop, args=(stop_flag,), daemon=True).start()

    # Run scheduler loop in main thread
    scheduler_loop(stop_flag)

    logger.info("Nudgarr exiting.")


if __name__ == "__main__":
    main()

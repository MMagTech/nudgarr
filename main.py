"""
main.py — Nudgarr entry point.

Wires everything together:
  1. Registers Flask route blueprints
  2. Registers SIGTERM / SIGINT handlers and a threading.Event for clean shutdown
     — allows an in-progress sweep to finish before the process exits
  3. Pre-populates STATUS from persisted state (so UI dots show immediately)
  4. Fires a parallel startup health-ping to all configured instances
  5. Starts the Flask UI server in a daemon thread
  6. Runs the scheduler loop in the main thread

When NUDGARR_DEV is set (non-empty), step 5–6 change: scheduler, import check,
and CF sync run in daemon threads; Flask's development server runs in the main
thread with debug and reloader enabled. WERKZEUG_RUN_MAIN guards background
startup so the Werkzeug reloader does not duplicate threads. Background loops
use interruptible waits on the shutdown event so Ctrl+C exits within ~1s after
Flask stops instead of hanging on a full 60s sleep.
"""

import logging
import os
import signal
import threading

import requests

from nudgarr import db
from nudgarr.config import load_or_init_config
from nudgarr.constants import PORT
from nudgarr.globals import STATUS, app
from nudgarr.log_setup import setup_logging
from nudgarr.routes import register_blueprints
from nudgarr.scheduler import cf_score_sync_loop, import_check_loop, print_banner, scheduler_loop, start_ui_server
from nudgarr.utils import req

logger = logging.getLogger(__name__)


def main() -> None:
    # Load config and initialise logging first — before any nudgarr module emits a log line.
    # setup_logging must run before register_blueprints and db.init_db or the level
    # set in Advanced → Log Level will be ignored on restart.
    cfg = load_or_init_config()
    setup_logging(cfg.get("log_level", "INFO"))

    register_blueprints()

    # Initialise database (schema creation + one-time JSON migration if needed)
    db.init_db()

    # _shutdown is set by SIGTERM/SIGINT handlers. The scheduler and import
    # check loops check is_set() at each cycle boundary — an in-progress
    # sweep is always allowed to finish before the process exits.
    _shutdown = threading.Event()

    def handle_signal(signum, frame):
        sig_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
        logger.info("Received %s — waiting for active sweep to finish before exiting...", sig_name)
        _shutdown.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    print_banner(cfg)

    # Log config load summary
    radarr_count = len(cfg.get("instances", {}).get("radarr", []))
    sonarr_count = len(cfg.get("instances", {}).get("sonarr", []))
    logger.info("Config loaded — %d instance(s): %d Radarr, %d Sonarr",
                radarr_count + sonarr_count,
                radarr_count,
                sonarr_count)

    # Background health ping — parallel, non-blocking, populates dots within ~1s
    def _startup_health_ping():
        _session = requests.Session()
        instances = []
        for _inst in cfg.get("instances", {}).get("radarr", []):
            if not _inst.get("enabled", True):
                STATUS["instance_health"][f"radarr|{_inst['name']}"] = "disabled"
                logger.debug("[radarr:%s] startup ping — skipped (disabled)", _inst["name"])
            else:
                instances.append(("radarr", _inst))
        for _inst in cfg.get("instances", {}).get("sonarr", []):
            if not _inst.get("enabled", True):
                STATUS["instance_health"][f"sonarr|{_inst['name']}"] = "disabled"
                logger.debug("[sonarr:%s] startup ping — skipped (disabled)", _inst["name"])
            else:
                instances.append(("sonarr", _inst))

        def _ping(app_name, inst):
            try:
                _url = f"{inst['url'].rstrip('/')}/api/v3/system/status"
                data = req(_session, "GET", _url, inst["key"], timeout=5)
                STATUS["instance_health"][f"{app_name}|{inst['name']}"] = "ok"
                version = data.get("version", "unknown") if isinstance(data, dict) else "unknown"
                logger.debug("[%s:%s] startup ping — ok (v%s)", app_name, inst["name"], version)
            except Exception:
                STATUS["instance_health"][f"{app_name}|{inst['name']}"] = "bad"
                logger.warning("[%s:%s] startup ping — failed", app_name, inst["name"])

        threads = [threading.Thread(target=_ping, args=(a, i), daemon=True) for a, i in instances]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    threading.Thread(target=_startup_health_ping, daemon=True).start()

    if os.getenv("NUDGARR_DEV", "").strip():
        import_check_thread = None
        cf_sync_thread = None
        sched_thread = None
        if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
            sched_thread = threading.Thread(
                target=scheduler_loop, args=(_shutdown,), daemon=True, name="scheduler"
            )
            sched_thread.start()
            import_check_thread = threading.Thread(
                target=import_check_loop, args=(_shutdown,), daemon=True, name="import-check"
            )
            import_check_thread.start()
            cf_sync_thread = threading.Thread(
                target=cf_score_sync_loop, args=(_shutdown,), daemon=True, name="cf-score-sync"
            )
            cf_sync_thread.start()
        logger.info("NUDGARR_DEV is set: Flask dev server running in main thread")
        app.run(host="0.0.0.0", port=PORT, debug=True, use_reloader=True)

        if import_check_thread is not None:
            import_check_thread.join(timeout=10)
            if import_check_thread.is_alive():
                logger.warning("Import check thread did not exit within 10s — proceeding with shutdown")

        if cf_sync_thread is not None:
            cf_sync_thread.join(timeout=10)
            if cf_sync_thread.is_alive():
                logger.warning("CF score sync thread did not exit within 10s — proceeding with shutdown")

        if sched_thread is not None:
            sched_thread.join(timeout=10)
            if sched_thread.is_alive():
                logger.warning("Scheduler thread did not exit within 10s — proceeding with shutdown")

        logger.info("Nudgarr exiting.")
        return

    # Start UI in a daemon thread
    threading.Thread(target=start_ui_server, daemon=True).start()

    # Start import check loop in a daemon thread — independent of sweep schedule
    import_check_thread = threading.Thread(
        target=import_check_loop, args=(_shutdown,), daemon=True, name="import-check"
    )
    import_check_thread.start()

    # Start CF score sync loop in a daemon thread — independent of sweep schedule.
    # Wakes every 60s, runs a full library sync when cf_score_sync_hours have
    # elapsed and cf_score_enabled is True.  Dormant when feature is disabled.
    cf_sync_thread = threading.Thread(
        target=cf_score_sync_loop, args=(_shutdown,), daemon=True, name="cf-score-sync"
    )
    cf_sync_thread.start()

    # Run scheduler loop in main thread — blocks until _shutdown is set
    scheduler_loop(_shutdown)

    # Wait for background threads to exit cleanly before process teardown.
    # 10 seconds is generous — loops use interruptible 1s waits so they observe
    # _shutdown within ~1s of Ctrl+C/SIGTERM.
    import_check_thread.join(timeout=10)
    if import_check_thread.is_alive():
        logger.warning("Import check thread did not exit within 10s — proceeding with shutdown")

    cf_sync_thread.join(timeout=10)
    if cf_sync_thread.is_alive():
        logger.warning("CF score sync thread did not exit within 10s — proceeding with shutdown")

    logger.info("Nudgarr exiting.")


if __name__ == "__main__":
    main()

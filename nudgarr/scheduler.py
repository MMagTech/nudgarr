"""
nudgarr/scheduler.py

Background sweep engine.

  print_banner     -- startup banner to stdout
  start_ui_server  -- blocking Flask server call (run in a thread)
  scheduler_loop   -- main sweep loop, runs on interval + handles run-now requests
"""

import time
from datetime import timedelta
from typing import Any, Dict

import requests

from nudgarr.config import load_or_init_config
from nudgarr.constants import CONFIG_FILE, DB_FILE, PORT, VERSION
from nudgarr.globals import RUN_LOCK, STATUS, app
from nudgarr.notifications import notify_error, notify_sweep_complete
from nudgarr.stats import check_imports
from nudgarr.sweep import run_sweep
from nudgarr.utils import iso_z, utcnow


def print_banner(cfg: Dict[str, Any]) -> None:
    print("")
    print("====================================")
    print(f" Nudgarr v{VERSION}")
    print(" Because RSS sometimes needs a nudge.")
    print("====================================")
    print(f"Config: {CONFIG_FILE}")
    print(f"DB:     {DB_FILE}")
    print(f"UI:     http://<host>:{PORT}/")
    print("")
    print("")


def start_ui_server() -> None:
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)


def import_check_loop(stop_flag: Dict[str, bool]) -> None:
    """
    Independent import-check timer. Fires check_imports on its own schedule,
    completely separate from the sweep interval. Wakes every 60 seconds and
    checks whether import_check_minutes has elapsed since the last check.
    """
    session = requests.Session()
    last_check_ts = utcnow()

    while not stop_flag["stop"]:
        time.sleep(60)
        if stop_flag["stop"]:
            break

        cfg = load_or_init_config()
        check_minutes = int(cfg.get("import_check_minutes", 120))
        if check_minutes <= 0:
            continue

        now = utcnow()
        elapsed = (now - last_check_ts).total_seconds() / 60
        if elapsed >= check_minutes:
            try:
                check_imports(session, cfg)
            except Exception as e:
                print(f"[Stats] Import check error: {e}")
            last_check_ts = now



    STATUS["scheduler_running"] = True
    session = requests.Session()
    cycle = 0

    # Set next_run_utc at startup without running a sweep.
    # The first sweep fires when the interval elapses or Run Now is pressed.
    # Missed intervals during downtime are skipped — no catch-up on restart.
    cfg = load_or_init_config()
    scheduler_enabled = bool(cfg.get("scheduler_enabled", True))
    interval_min = int(cfg.get("run_interval_minutes", 360))
    if scheduler_enabled:
        STATUS["next_run_utc"] = iso_z(utcnow() + timedelta(minutes=interval_min))
    else:
        STATUS["next_run_utc"] = None

    while not stop_flag["stop"]:
        cfg = load_or_init_config()

        scheduler_enabled = bool(cfg.get("scheduler_enabled", True))
        interval_min = int(cfg.get("run_interval_minutes", 360))

        should_run = False

        with RUN_LOCK:
            if STATUS.get("run_requested"):
                should_run = True
                STATUS["run_requested"] = False

        if should_run:
            cycle += 1
            STATUS["run_in_progress"] = True
            try:
                print(f"--- Sweep Cycle #{cycle} ---")
                summary = run_sweep(cfg, session)
                STATUS["last_summary"] = summary
                STATUS["last_run_utc"] = iso_z(utcnow())
                STATUS["last_error"] = None
                notify_sweep_complete(summary, cfg)
                for app_name in ("radarr", "sonarr"):
                    for inst in summary.get(app_name, []):
                        if "error" in inst:
                            notify_error(f"'{inst['name']}' is unreachable.", cfg)
                try:
                    check_imports(session, cfg)
                except Exception as ce:
                    print(f"[Stats] Import check error: {ce}")
            except Exception as e:
                STATUS["last_error"] = str(e)
                print(f"ERROR (sweep): {e}")
                notify_error(f"Sweep failed: {e}", cfg)
            finally:
                STATUS["run_in_progress"] = False
                # Recalculate next run after each sweep completes
                if scheduler_enabled:
                    STATUS["next_run_utc"] = iso_z(utcnow() + timedelta(minutes=interval_min))
                else:
                    STATUS["next_run_utc"] = None

        if stop_flag["stop"]:
            break

        sleep_seconds = interval_min * 60 if scheduler_enabled else 60
        deadline = time.monotonic() + sleep_seconds
        while not stop_flag["stop"] and time.monotonic() < deadline:
            with RUN_LOCK:
                if STATUS.get("run_requested"):
                    break
            time.sleep(1)

        if scheduler_enabled and not stop_flag["stop"]:
            with RUN_LOCK:
                if not STATUS.get("run_requested"):
                    STATUS["run_requested"] = True

    STATUS["scheduler_running"] = False

def scheduler_loop(stop_flag: Dict[str, bool]) -> None:
    STATUS["scheduler_running"] = True
    session = requests.Session()
    cycle = 0

    # Set next_run_utc at startup without running a sweep.
    # The first sweep fires when the interval elapses or Run Now is pressed.
    # Missed intervals during downtime are skipped — no catch-up on restart.
    cfg = load_or_init_config()
    scheduler_enabled = bool(cfg.get("scheduler_enabled", True))
    interval_min = int(cfg.get("run_interval_minutes", 360))
    if scheduler_enabled:
        STATUS["next_run_utc"] = iso_z(utcnow() + timedelta(minutes=interval_min))
    else:
        STATUS["next_run_utc"] = None

    while not stop_flag["stop"]:
        cfg = load_or_init_config()

        scheduler_enabled = bool(cfg.get("scheduler_enabled", True))
        interval_min = int(cfg.get("run_interval_minutes", 360))

        should_run = False

        with RUN_LOCK:
            if STATUS.get("run_requested"):
                should_run = True
                STATUS["run_requested"] = False

        if should_run:
            cycle += 1
            STATUS["run_in_progress"] = True
            try:
                print(f"--- Sweep Cycle #{cycle} ---")
                summary = run_sweep(cfg, session)
                STATUS["last_summary"] = summary
                STATUS["last_run_utc"] = iso_z(utcnow())
                STATUS["last_error"] = None
                notify_sweep_complete(summary, cfg)
                for app_name in ("radarr", "sonarr"):
                    for inst in summary.get(app_name, []):
                        if "error" in inst:
                            notify_error(f"'{inst['name']}' is unreachable.", cfg)
                try:
                    check_imports(session, cfg)
                except Exception as ce:
                    print(f"[Stats] Import check error: {ce}")
            except Exception as e:
                STATUS["last_error"] = str(e)
                print(f"ERROR (sweep): {e}")
                notify_error(f"Sweep failed: {e}", cfg)
            finally:
                STATUS["run_in_progress"] = False
                # Recalculate next run after each sweep completes
                if scheduler_enabled:
                    STATUS["next_run_utc"] = iso_z(utcnow() + timedelta(minutes=interval_min))
                else:
                    STATUS["next_run_utc"] = None

        if stop_flag["stop"]:
            break

        sleep_seconds = interval_min * 60 if scheduler_enabled else 60
        deadline = time.monotonic() + sleep_seconds
        while not stop_flag["stop"] and time.monotonic() < deadline:
            with RUN_LOCK:
                if STATUS.get("run_requested"):
                    break
            time.sleep(1)

        if scheduler_enabled and not stop_flag["stop"]:
            with RUN_LOCK:
                if not STATUS.get("run_requested"):
                    STATUS["run_requested"] = True

    STATUS["scheduler_running"] = False

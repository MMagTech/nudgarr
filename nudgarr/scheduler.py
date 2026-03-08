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
from nudgarr.constants import CONFIG_FILE, PORT, STATE_FILE, STATS_FILE, VERSION
from nudgarr.globals import RUN_LOCK, STATUS, app
from nudgarr.notifications import notify_error, notify_queue_threshold, notify_sweep_complete
from nudgarr.state import ensure_state_structure, load_state, save_state
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
    print(f"State:  {STATE_FILE}")
    print(f"Stats:  {STATS_FILE}")
    print(f"UI:     http://<host>:{PORT}/")
    print("")
    print("")


def start_ui_server() -> None:
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)


def scheduler_loop(stop_flag: Dict[str, bool]) -> None:
    STATUS["scheduler_running"] = True
    session = requests.Session()
    cycle = 0

    while not stop_flag["stop"]:
        cfg = load_or_init_config()
        # Ensure state file exists/structured even before first run
        st = ensure_state_structure(load_state(), cfg)
        save_state(st, cfg)

        now = utcnow()
        scheduler_enabled = bool(cfg.get("scheduler_enabled", True))

        interval_min = int(cfg.get("run_interval_minutes", 360))
        next_run = now + timedelta(minutes=interval_min)
        STATUS["next_run_utc"] = iso_z(next_run) if scheduler_enabled else None

        # Run on startup OR on schedule OR if manually requested
        should_run = scheduler_enabled and cycle == 0

        with RUN_LOCK:
            if STATUS.get("run_requested"):
                should_run = True
                STATUS["run_requested"] = False

        if should_run:
            cycle += 1
            STATUS["run_in_progress"] = True
            try:
                print(f"--- Sweep Cycle #{cycle} ---")
                summary = run_sweep(cfg, st, session)
                STATUS["last_summary"] = summary
                STATUS["last_run_utc"] = iso_z(utcnow())
                STATUS["last_error"] = None
                # Persist last_run so it survives restart
                st["last_run_utc"] = STATUS["last_run_utc"]
                save_state(st, cfg)
                notify_sweep_complete(summary, cfg)
                # Notify on any instance-level errors or queue threshold skips
                for app_name in ("radarr", "sonarr"):
                    for inst in summary.get(app_name, []):
                        if "error" in inst:
                            notify_error(f"'{inst['name']}' is unreachable.", cfg)
                        if inst.get("skipped_queue_threshold"):
                            notify_queue_threshold(
                                inst["name"],
                                inst.get("queue_count", 0),
                                inst.get("queue_threshold", 0),
                                cfg,
                            )
                # Check for confirmed imports from previous searches
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

        if stop_flag["stop"]:
            break

        # Sleep until next run. In manual mode, wait up to 60s per tick so we
        # stay responsive to Run Now requests without busy-waiting for a year.
        sleep_seconds = interval_min * 60 if scheduler_enabled else 60
        deadline = time.monotonic() + sleep_seconds
        while not stop_flag["stop"] and time.monotonic() < deadline:
            with RUN_LOCK:
                if STATUS.get("run_requested"):
                    break
            time.sleep(1)

        # After sleeping the full interval, trigger the next scheduled run
        if scheduler_enabled and not stop_flag["stop"]:
            with RUN_LOCK:
                if not STATUS.get("run_requested"):
                    STATUS["run_requested"] = True

    STATUS["scheduler_running"] = False

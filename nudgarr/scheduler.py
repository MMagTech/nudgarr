"""
nudgarr/scheduler.py

Background sweep engine.

  print_banner        -- startup banner to stdout
  start_ui_server     -- blocking Flask server call (run in a thread)
  import_check_loop   -- independent import-check timer (runs in a daemon thread)
  scheduler_loop      -- main sweep loop, runs on interval + handles run-now requests
"""

import datetime as _dt
import os
import time
from typing import Any, Dict

import requests
from croniter import croniter

from nudgarr import db
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
    """Independent import-check timer running in its own daemon thread.

    Wakes every 60 seconds and checks whether import_check_minutes has elapsed
    since the last check. Completely decoupled from the sweep schedule — imports
    are polled on their own interval regardless of when sweeps run.

    Intentionally runs even when the scheduler is disabled (manual-only mode).
    """
    session = requests.Session()
    last_check_ts = utcnow()

    try:
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
    finally:
        db.close_connection()


def _next_cron_utc(expression: str) -> str:
    """Return the next fire time for a cron expression as a UTC ISO-Z string."""
    tz_name = os.environ.get("TZ", "UTC")
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo(tz_name)
    except Exception:
        tz = None

    now = utcnow()
    try:
        if tz:
            now_local = now.astimezone(tz)
            cron = croniter(expression, now_local)
            next_local = cron.get_next(_dt.datetime)
            next_utc = next_local.astimezone(_dt.timezone.utc)
        else:
            cron = croniter(expression, now)
            next_utc = cron.get_next(type(now))
    except Exception:
        next_utc = now + _dt.timedelta(hours=1)

    return iso_z(next_utc)


def _cron_due(expression: str) -> bool:
    """Return True if the cron expression should have fired since last checked (within 60s window)."""
    tz_name = os.environ.get("TZ", "UTC")
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo(tz_name)
    except Exception:
        tz = None

    now = utcnow()
    try:
        if tz:
            now_local = now.astimezone(tz)
            cron = croniter(expression, now_local)
            prev_local = cron.get_prev(_dt.datetime)
            prev_utc = prev_local.astimezone(_dt.timezone.utc)
        else:
            cron = croniter(expression, now)
            prev_utc = cron.get_prev(type(now))
        return (now - prev_utc).total_seconds() < 90
    except Exception:
        return False


def scheduler_loop(stop_flag: Dict[str, bool]) -> None:
    """Main sweep loop — runs in the main thread for the lifetime of the process.

    Wakes every 60 seconds to check for:
      - A run-now request from the UI (STATUS["run_requested"])
      - A cron fire — uses a 90-second window (not 60) to avoid missing a cron
        tick that falls just outside a 60-second sleep boundary

    Config is reloaded on every iteration so schedule changes take effect
    without a restart. next_run_utc is recalculated immediately on config change.

    To add a new per-sweep action (e.g. a post-sweep hook), add it in the
    try block after notify_sweep_complete.
    """
    STATUS["scheduler_running"] = True
    session = requests.Session()

    # Restore last_run_utc from persisted state so UI shows correctly after restart.
    cfg = load_or_init_config()
    scheduler_enabled = bool(cfg.get("scheduler_enabled", False))
    cron_expression = cfg.get("cron_expression", "0 */6 * * *")

    persisted_last_run = db.get_state("last_run_utc")
    if persisted_last_run:
        STATUS["last_run_utc"] = persisted_last_run

    # Set initial next_run_utc
    if scheduler_enabled and cron_expression:
        STATUS["next_run_utc"] = _next_cron_utc(cron_expression)
    else:
        STATUS["next_run_utc"] = None

    _prev_scheduler_enabled = scheduler_enabled
    _prev_cron_expression = cron_expression

    try:
        while not stop_flag["stop"]:
            cfg = load_or_init_config()
            scheduler_enabled = bool(cfg.get("scheduler_enabled", False))
            cron_expression = cfg.get("cron_expression", "0 */6 * * *")

            # Recalculate next_run_utc immediately if config changed
            config_changed = (
                scheduler_enabled != _prev_scheduler_enabled
                or cron_expression != _prev_cron_expression
            )
            if config_changed:
                STATUS["next_run_utc"] = _next_cron_utc(cron_expression) if scheduler_enabled and cron_expression else None
                _prev_scheduler_enabled = scheduler_enabled
                _prev_cron_expression = cron_expression

            should_run = False

            with RUN_LOCK:
                if STATUS.get("run_requested"):
                    should_run = True
                    STATUS["run_requested"] = False

            # Cron trigger: check if a scheduled fire time just passed (within 90s window)
            if not should_run and scheduler_enabled and cron_expression:
                if _cron_due(cron_expression):
                    should_run = True

            if should_run:
                STATUS["run_in_progress"] = True
                try:
                    print(f"--- Sweep {iso_z(utcnow())[:16].replace('T', ' ')} UTC ---")
                    summary = run_sweep(cfg, session)
                    STATUS["last_summary"] = summary
                    STATUS["last_run_utc"] = iso_z(utcnow())
                    db.set_state("last_run_utc", STATUS["last_run_utc"])
                    STATUS["last_error"] = None
                    notify_sweep_complete(summary, cfg)
                    for app_name in ("radarr", "sonarr"):
                        for inst in summary.get(app_name, []):
                            if "error" in inst and inst.get("notifications_enabled", True):
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
                    STATUS["next_run_utc"] = _next_cron_utc(cron_expression) if scheduler_enabled and cron_expression else None

            if stop_flag["stop"]:
                break

            # Always wake every 60s to check for due cron fires and config changes
            deadline = time.monotonic() + 60
            while not stop_flag["stop"] and time.monotonic() < deadline:
                with RUN_LOCK:
                    if STATUS.get("run_requested"):
                        break
                time.sleep(1)

    finally:
        STATUS["scheduler_running"] = False
        db.close_connection()

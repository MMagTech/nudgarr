"""
nudgarr/scheduler.py

Background sweep engine.

  print_banner        -- startup banner to stdout (uses logger.info)
  start_ui_server     -- blocking Flask server call (run in a thread)
  import_check_loop   -- independent import-check timer (runs in a daemon thread)
  scheduler_loop      -- main sweep loop, runs on interval + handles run-now requests
"""

import datetime as _dt
import json
import logging
import os
import threading
import time
from typing import Any, Dict

import requests
from croniter import croniter

from nudgarr import db
from nudgarr.cf_score_syncer import CustomFormatScoreSyncer
from nudgarr.config import load_or_init_config
from nudgarr.constants import CONFIG_FILE, DB_FILE, PORT, VERSION
from nudgarr.globals import RUN_LOCK, STATUS, app
from nudgarr.notifications import notify_error, notify_auto_exclusion, notify_sweep_complete
from nudgarr.stats import check_imports
from nudgarr.sweep import run_sweep
from nudgarr.utils import iso_z, utcnow

logger = logging.getLogger(__name__)


def print_banner(cfg: Dict[str, Any]) -> None:
    """Log the startup banner and key runtime paths."""
    logger.info("====================================")
    logger.info(" Nudgarr v%s", VERSION)
    logger.info(" Because RSS sometimes needs a nudge.")
    logger.info("====================================")
    logger.info("Config: %s", CONFIG_FILE)
    logger.info("DB:     %s", DB_FILE)
    logger.info("UI:     http://<host>:%s/", PORT)
    logger.info("Log level: %s  (Nudgarr verbosity — set in Advanced tab)", cfg.get("log_level", "INFO"))


def start_ui_server() -> None:
    """Start the WSGI server. Blocking — must be run in a dedicated thread.

    Uses Waitress in production (present in requirements.txt and the Docker
    image). Falls back to Flask's development server with a warning if
    Waitress is not installed — this should only happen when running from
    source without installing requirements.txt.

    threads=4 is sufficient for Nudgarr's single-user workload. The status
    poll (every 5s per tab) is the most frequent caller — 4 threads handles
    multiple open tabs with headroom to spare.
    """
    try:
        from waitress import serve
        logger.debug("Starting Waitress WSGI server on port %s (threads=4)", PORT)
        serve(app, host="0.0.0.0", port=PORT, threads=4)
    except ImportError:
        logger.warning(
            "Waitress not found — falling back to Flask development server. "
            "Install waitress via requirements.txt for production use."
        )
        app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)


def import_check_loop(shutdown: threading.Event) -> None:
    """Independent import-check timer running in its own daemon thread.

    Wakes every 60 seconds and checks whether import_check_minutes has elapsed
    since the last check. Completely decoupled from the sweep schedule — imports
    are polled on their own interval regardless of when sweeps run.

    After each import check cycle, runs the auto-exclusion evaluation for all
    unconfirmed entries that have met their threshold. The four conditions that
    must all be true before a title is auto-excluded are:
      1. Search count >= configured threshold for that app
      2. No confirmed import on record
      3. Title not currently in the Radarr or Sonarr download queue
      4. Title not already in the exclusions list

    Intentionally runs even when the scheduler is disabled (manual-only mode).
    """
    session = requests.Session()
    last_check_ts = utcnow()

    try:
        while not shutdown.is_set():
            time.sleep(60)
            if shutdown.is_set():
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
                except Exception:
                    logger.exception("[Stats] Import check failed in background loop")
                # Auto-exclusion check runs after every import check cycle,
                # regardless of whether check_imports succeeded. Uses the same
                # session for queue API calls to avoid extra connection overhead.
                try:
                    _run_auto_exclusion_check(session, cfg)
                except Exception:
                    logger.exception("[Auto-Exclude] Check failed in background loop")
                last_check_ts = now
    finally:
        db.close_connection()


def _run_auto_exclusion_check(session: requests.Session, cfg: Dict[str, Any]) -> None:
    """Evaluate search history entries for auto-exclusion.

    Called after every import check cycle. Drives from search_history rather
    than stat_entries so only titles Nudgarr has actually searched are evaluated.
    The database query (get_high_search_count_unconfirmed) returns rows that:
      - Have search_count >= the configured threshold for their app
      - Have no confirmed import in stat_entries (LEFT JOIN + IS NULL filter)

    For each candidate, two additional conditions are checked at runtime:
      3. Title not currently in the Radarr/Sonarr download queue -- protects
         against excluding an item that was just grabbed and is still
         downloading, regardless of how aggressive the import check interval is
      4. Title not already in the exclusions table -- prevents duplicate rows

    When all conditions are met the exclusion row is written with source=auto
    and the search count at the time of exclusion. A notification fires if the
    Auto-Exclusion trigger is enabled in Notifications.

    A threshold of 0 disables auto-exclusion for that app entirely.
    """
    movies_threshold = int(cfg.get("auto_exclude_movies_threshold", 0))
    shows_threshold = int(cfg.get("auto_exclude_shows_threshold", 0))

    logger.info("[Auto-Exclude] check invoked — movies_threshold=%d shows_threshold=%d",
                movies_threshold, shows_threshold)

    # Skip entirely if both thresholds are disabled
    if movies_threshold <= 0 and shows_threshold <= 0:
        return

    # Build instance lookup map for queue API calls
    instance_map: Dict[tuple, Dict] = {}
    for inst in cfg.get("instances", {}).get("radarr", []):
        instance_map[("radarr", inst["name"])] = inst
    for inst in cfg.get("instances", {}).get("sonarr", []):
        instance_map[("sonarr", inst["name"])] = inst

    # Load current exclusion titles once for condition 4
    existing_exclusions = {
        e["title"].lower() for e in db.get_exclusions() if e.get("title")
    }

    # Fetch candidates from search_history -- titles Nudgarr has searched
    # that are above the threshold and have no confirmed import
    candidates = db.get_high_search_count_unconfirmed(movies_threshold, shows_threshold)
    logger.info("[Auto-Exclude] found %d candidate(s) (movies_threshold=%d shows_threshold=%d)",
                len(candidates), movies_threshold, shows_threshold)

    for entry in candidates:
        app = entry.get("app", "radarr")
        title = entry.get("title", "")
        search_count = entry.get("search_count", 0)
        instance_name = entry.get("instance_name", "?")

        logger.debug(
            "[Auto-Exclude] checking: %s (%s:%s) searches=%d threshold=%d",
            title, app, instance_name, search_count,
            movies_threshold if app == "radarr" else shows_threshold
        )

        # Condition 4: not already excluded
        if title.lower() in existing_exclusions:
            logger.debug("[Auto-Exclude] %s -- already excluded", title)
            continue

        # Condition 3: not currently in the download queue.
        # For Sonarr use series_id for the queue check since the queue API
        # filters by seriesId not episodeId. item_id in search_history stores
        # the episode ID for Sonarr entries.
        inst = instance_map.get((app, instance_name))
        if inst:
            queue_id = entry.get("series_id") if app == "sonarr" else entry.get("item_id", "")
            if not queue_id:
                queue_id = entry.get("item_id", "")
            in_queue = _is_title_in_queue(session, app, inst, queue_id)
            if in_queue:
                logger.debug("[Auto-Exclude] %s -- skipped (in queue)", title)
                continue

        # All conditions met -- write the exclusion row
        db.add_auto_exclusion(title, search_count)
        logger.info("[Auto-Exclude] %s excluded after %d searches with no import (%s:%s)",
                    title, search_count, app, instance_name)
        notify_auto_exclusion(title, search_count, instance_name, app, cfg)
        existing_exclusions.add(title.lower())


def _is_title_in_queue(session: requests.Session, app: str,
                       inst: Dict[str, Any], item_id: str) -> bool:
    """Check whether an item is currently present in the Radarr or Sonarr queue.

    Returns True if the item is found in the queue, False otherwise or on any
    API error. Errors are logged at debug level — a failed queue check should
    not block the auto-exclusion evaluation; the conservative outcome is to
    return False and allow the other conditions to decide.

    app     -- 'radarr' or 'sonarr'
    inst    -- instance config dict with url and key
    item_id -- the movie ID (Radarr) or series ID (Sonarr) to check
    """
    url = inst["url"].rstrip("/")
    key = inst["key"]
    try:
        if app == "radarr":
            r = session.get(
                f"{url}/api/v3/queue",
                params={"movieId": item_id},
                headers={"X-Api-Key": key},
                timeout=10,
            )
        else:
            r = session.get(
                f"{url}/api/v3/queue",
                params={"seriesId": item_id},
                headers={"X-Api-Key": key},
                timeout=10,
            )
        if not r.ok:
            return False
        data = r.json()
        records = data.get("records", []) if isinstance(data, dict) else data
        return len(records) > 0
    except Exception as e:
        logger.debug("[Auto-Exclude] queue check failed for %s/%s: %s", app, item_id, e)
        return False


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


def _in_maintenance_window(cfg: Dict[str, Any]) -> bool:
    """Return True if the current local time falls inside the configured maintenance window.

    The maintenance window suppresses scheduled (cron-triggered) sweeps. Manual
    runs via Run Now are never passed through this check — callers are responsible
    for only calling this on cron-triggered fires.

    Behaviour summary:
      - Returns False immediately if maintenance_window_enabled is False.
      - Returns False immediately if maintenance_window_days is empty — an empty
        day list means the window never fires, equivalent to disabled.
      - Supports overnight ranges (e.g. 23:00 to 07:00 spanning midnight). The
        window is considered active if the current time falls between start and end
        taking the overnight crossing into account. The day check is against the
        day the window opened, not the current calendar day.
      - Uses container local time via the TZ environment variable, consistent with
        how cron expressions are evaluated elsewhere in this module.

    cfg keys consumed:
      maintenance_window_enabled -- bool
      maintenance_window_start   -- "HH:MM" 24-hour string
      maintenance_window_end     -- "HH:MM" 24-hour string
      maintenance_window_days    -- list of ints 0-6 (Monday=0, Sunday=6)
    """
    if not cfg.get("maintenance_window_enabled", False):
        return False

    selected_days = set(cfg.get("maintenance_window_days") or [])
    if not selected_days:
        # Empty day list — window never fires regardless of toggle state
        return False

    start_str = cfg.get("maintenance_window_start", "00:00")
    end_str = cfg.get("maintenance_window_end", "00:00")
    if start_str == end_str:
        return False

    # Resolve local time using TZ, consistent with _cron_due
    tz_name = os.environ.get("TZ", "UTC")
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo(tz_name)
        now = _dt.datetime.now(tz)
    except Exception:
        now = _dt.datetime.utcnow()

    try:
        sh, sm = int(start_str[:2]), int(start_str[3:])
        eh, em = int(end_str[:2]), int(end_str[3:])
    except (ValueError, IndexError):
        return False

    start_mins = sh * 60 + sm
    end_mins = eh * 60 + em
    overnight = start_mins > end_mins

    today = now.date()
    start_today = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
    end_today = now.replace(hour=eh, minute=em, second=0, microsecond=0)

    if overnight:
        # Two candidate windows — the window that opened yesterday (tail end)
        # and the window that opens today (opening side).
        window_a_open = start_today - _dt.timedelta(days=1)
        window_a_close = end_today
        window_b_open = start_today
        window_b_close = end_today + _dt.timedelta(days=1)

        if window_a_open <= now < window_a_close:
            # Active window opened yesterday — check yesterday's weekday
            yesterday = (today - _dt.timedelta(days=1)).weekday()
            return yesterday in selected_days
        if window_b_open <= now < window_b_close:
            # Active window opened today
            return today.weekday() in selected_days
        return False
    else:
        # Same-day window
        if start_today <= now < end_today:
            return today.weekday() in selected_days
        return False


def cf_score_sync_loop(shutdown: threading.Event) -> None:
    """Background CF score sync loop running in its own daemon thread.

    Wakes every 60 seconds to check whether cf_score_sync_hours hours have
    elapsed since the last sync.  Skips the run entirely if:
      - cf_score_enabled is False
      - A sweep is currently in progress (defers to avoid simultaneous load)

    The syncer is the sole writer of cf_score_entries.  This loop owns the
    scheduled runs; the manual Scan Library button triggers runs via the
    /api/cf-scores/scan route independently.

    Intentionally runs even when the main scheduler is disabled so users in
    manual-only mode still get CF score index updates on schedule.
    """
    session = requests.Session()
    syncer = CustomFormatScoreSyncer()
    last_sync_ts = None  # None means never synced -- run immediately on first wake

    try:
        while not shutdown.is_set():
            time.sleep(60)
            if shutdown.is_set():
                break

            cfg = load_or_init_config()

            if not cfg.get("cf_score_enabled", False):
                # Feature is off -- reset last_sync_ts so a sync runs
                # immediately if the feature is later re-enabled
                last_sync_ts = None
                continue

            sync_hours = int(cfg.get("cf_score_sync_hours", 24))
            if sync_hours < 1:
                sync_hours = 1

            now = utcnow()
            should_sync = False

            if last_sync_ts is None:
                # First run since startup (or after re-enable) -- sync now
                should_sync = True
            else:
                elapsed_hours = (now - last_sync_ts).total_seconds() / 3600
                if elapsed_hours >= sync_hours:
                    should_sync = True

            if not should_sync:
                continue

            try:
                logger.info("[CF Sync] Scheduled sync starting")
                syncer.run(cfg, session)
                last_sync_ts = utcnow()
                logger.info("[CF Sync] Scheduled sync complete")
            except Exception:
                logger.exception("[CF Sync] Scheduled sync failed")
    finally:
        db.close_connection()


def scheduler_loop(shutdown: threading.Event) -> None:
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

    # Restore last_run_utc and last_summary from persisted state so UI shows correctly after restart.
    cfg = load_or_init_config()
    scheduler_enabled = bool(cfg.get("scheduler_enabled", False))
    cron_expression = cfg.get("cron_expression", "0 */6 * * *")

    persisted_last_run = db.get_state("last_run_utc")
    if persisted_last_run:
        STATUS["last_run_utc"] = persisted_last_run

    persisted_summary = db.get_state("last_summary")
    if persisted_summary:
        try:
            STATUS["last_summary"] = json.loads(persisted_summary)
        except (ValueError, TypeError):
            logger.warning("Could not restore last_summary from state — will repopulate after next sweep")

    # Set initial next_run_utc
    if scheduler_enabled and cron_expression:
        STATUS["next_run_utc"] = _next_cron_utc(cron_expression)
    else:
        STATUS["next_run_utc"] = None

    _prev_scheduler_enabled = scheduler_enabled
    _prev_cron_expression = cron_expression

    try:
        while not shutdown.is_set():
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

            # Cron trigger: check if a scheduled fire time just passed (within 90s window).
            # Manual run-now requests (above) bypass this check entirely — suppression
            # only applies to scheduled fires. See _in_maintenance_window for full logic.
            if not should_run and scheduler_enabled and cron_expression:
                if _cron_due(cron_expression):
                    if _in_maintenance_window(cfg):
                        logger.info(
                            "[Scheduler] Sweep suppressed by maintenance window "
                            "(window: %s to %s, now: %s)",
                            cfg.get("maintenance_window_start", "?"),
                            cfg.get("maintenance_window_end", "?"),
                            _dt.datetime.now().strftime("%H:%M"),
                        )
                    else:
                        should_run = True

            if should_run:
                if RUN_LOCK.locked():
                    logger.debug("Sweep skipped — RUN_LOCK already held (sweep in progress)")
                    should_run = False
                STATUS["run_in_progress"] = True
                try:
                    logger.info("--- Sweep %s UTC --- [log level: %s]", iso_z(utcnow())[:16].replace("T", " "), cfg.get("log_level", "INFO"))
                    STATUS["last_sweep_start_utc"] = iso_z(utcnow())
                    summary = run_sweep(cfg, session)
                    STATUS["last_summary"] = summary
                    STATUS["last_run_utc"] = iso_z(utcnow())
                    db.set_state("last_run_utc", STATUS["last_run_utc"])
                    db.set_state("last_summary", json.dumps(summary))
                    STATUS["last_error"] = None
                    if STATUS["last_sweep_start_utc"]:
                        STATUS["imports_confirmed_sweep"] = db.get_imports_since(
                            STATUS["last_sweep_start_utc"]
                        )
                    notify_sweep_complete(summary, cfg)
                    for app_name in ("radarr", "sonarr"):
                        for inst in summary.get(app_name, []):
                            if "error" in inst and inst.get("notifications_enabled", True):
                                notify_error(f"'{inst['name']}' is unreachable.", cfg)
                except Exception:
                    STATUS["last_error"] = "Sweep failed — see logs for details"
                    logger.exception("Sweep failed")
                    notify_error("Sweep failed — check logs.", cfg)
                finally:
                    STATUS["run_in_progress"] = False
                    STATUS["next_run_utc"] = _next_cron_utc(cron_expression) if scheduler_enabled and cron_expression else None

            if shutdown.is_set():
                break

            # Always wake every 60s to check for due cron fires and config changes
            deadline = time.monotonic() + 60
            while not shutdown.is_set() and time.monotonic() < deadline:
                with RUN_LOCK:
                    if STATUS.get("run_requested"):
                        break
                time.sleep(1)

    finally:
        STATUS["scheduler_running"] = False
        db.close_connection()

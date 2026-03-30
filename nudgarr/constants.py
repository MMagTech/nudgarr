"""
nudgarr/constants.py

Static configuration: version string, runtime file paths (from env),
and the DEFAULT_CONFIG dict that new installs are seeded from.

No imports from within the nudgarr package — stdlib only.
"""

import os
from typing import Any, Dict

VERSION = "4.2.0"

CONFIG_FILE = os.getenv("CONFIG_FILE", "/config/nudgarr-config.json")
DB_FILE = os.getenv("DB_FILE", "/config/nudgarr.db")
PORT = int(os.getenv("PORT", "8085"))

DEFAULT_CONFIG: Dict[str, Any] = {
    "scheduler_enabled": False,        # off by default — user enables deliberately
    "cron_expression": "0 */6 * * *",  # default: every 6 hours on the clock

    "cooldown_hours": 48,
    "radarr_sample_mode": "random",    # random | alphabetical | oldest_added | newest_added
    "sonarr_sample_mode": "random",    # random | alphabetical | oldest_added | newest_added

    # Backlog Sample Mode (v4.2.0)
    # Independent sample mode for the backlog (missing) pipeline. Separate from
    # radarr_sample_mode / sonarr_sample_mode which control the cutoff unmet pipeline.
    # Backlog mode intentionally excludes any cutoff-only modes since missing items
    # have no existing file to score against.
    "radarr_backlog_sample_mode": "random",  # random | alphabetical | oldest_added | newest_added
    "sonarr_backlog_sample_mode": "random",  # random | alphabetical | oldest_added | newest_added

    "radarr_max_movies_per_run": 1,
    "sonarr_max_episodes_per_run": 1,
    "radarr_cutoff_enabled": True,     # master toggle for Radarr Cutoff Unmet pipeline (v4.2.0)
    "sonarr_cutoff_enabled": True,     # master toggle for Sonarr Cutoff Unmet pipeline (v4.2.0)

    # Optional Radarr backlog missing nudges (OFF by default)
    "radarr_backlog_enabled": False,
    "radarr_missing_max": 1,
    "radarr_missing_added_days": 14,
    "radarr_missing_grace_hours": 0,

    # Optional Sonarr backlog missing nudges (OFF by default)
    "sonarr_backlog_enabled": False,
    "sonarr_missing_max": 1,
    "sonarr_missing_added_days": 14,
    "sonarr_missing_grace_hours": 0,

    "batch_size": 1,
    "sleep_seconds": 5,
    "jitter_seconds": 2,

    # State size controls
    "state_retention_days": 180,       # prune entries older than this (0 disables)

    "instances": {"radarr": [], "sonarr": []},

    # Authentication (v2.0)
    "auth_enabled": True,
    "auth_username": "",
    "auth_password_hash": "",
    "auth_session_minutes": 30,

    # Stats (v2.0)
    "import_check_minutes": 120,

    # Notifications (v2.3.0)
    "notify_enabled": False,
    "notify_url": "",
    "notify_on_sweep_complete": True,
    "notify_on_import": True,
    "notify_on_auto_exclusion": True,
    "notify_on_error": True,

    # Onboarding
    "onboarding_complete": False,

    # UI Preferences (v2.5.0)
    "last_seen_version": "",
    "show_support_link": True,

    # Per-Instance Overrides (v3.2.0)
    "per_instance_overrides_enabled": False,
    "per_instance_overrides_seen": False,
    "per_instance_overrides_seen_mobile": False,

    # Logging (v4.0.0)
    "log_level": "INFO",   # DEBUG | INFO | WARNING | ERROR

    # Auto-Exclusion (v4.1.0)
    # Titles searched this many times with no confirmed import are automatically
    # excluded. 0 disables auto-exclusion for that app. Each app is independent
    # so Radarr and Sonarr can have different thresholds.
    "auto_exclude_movies_threshold": 0,   # searches before auto-excluding a movie
    "auto_exclude_shows_threshold": 0,    # searches before auto-excluding a show
    # Auto-excluded titles older than this many days are removed at sweep start,
    # making them eligible again. 0 means they stay excluded until manually removed.
    "auto_unexclude_movies_days": 0,      # days before a movie auto-exclusion expires
    "auto_unexclude_shows_days": 0,       # days before a show auto-exclusion expires

    # CF Score Scan (v4.2.0)
    # Library-wide audit that finds movies/episodes where customFormatScore is
    # below the quality profile's cutoffFormatScore even when Radarr/Sonarr does
    # not flag them via wanted/cutoff. The syncer builds a persistent index on its
    # own schedule; the sweep OR-conditions against it. Feature is fully dormant
    # until cf_score_enabled is set to True — no background work runs otherwise.
    "cf_score_enabled": False,        # master toggle — disables all CF score activity when False
    "cf_score_sync_hours": 24,        # hours between automatic index re-syncs
    "radarr_cf_max_per_run": 1,       # max CF-score-only Radarr items searched per sweep
    "sonarr_cf_max_per_run": 1,       # max CF-score-only Sonarr items searched per sweep

    # Maintenance Window (v4.2.0)
    # Suppresses scheduled (cron-triggered) sweeps during a defined time window.
    # Manual runs via Run Now are never affected — suppression applies only to the
    # automatic schedule. If maintenance_window_days is empty the feature behaves
    # as if disabled regardless of the toggle. Overnight ranges are supported
    # (e.g. 23:00 to 07:00 spanning midnight). Days stored as integers 0-6
    # where 0 = Monday and 6 = Sunday, matching Python's datetime.weekday().
    "maintenance_window_enabled": False,
    "maintenance_window_start": "00:00",  # HH:MM 24-hour start of suppression window
    "maintenance_window_end": "00:00",    # HH:MM 24-hour end of suppression window
    "maintenance_window_days": [],        # list of ints 0-6; empty = window never fires
}

# Valid sample modes for radarr_sample_mode, sonarr_sample_mode, and per-instance overrides.
# Single definition — sweep.py and config.py import this instead of defining their own.
VALID_SAMPLE_MODES = ("random", "alphabetical", "oldest_added", "newest_added")

# Valid sample modes for the backlog (missing) pipeline.
# Kept separate from VALID_SAMPLE_MODES so the backlog dropdown never exposes
# any future cutoff-only modes (e.g. quality gap scoring) that require an
# existing file. Missing items have no file, so those modes cannot apply.
VALID_BACKLOG_SAMPLE_MODES = ("random", "alphabetical", "oldest_added", "newest_added")

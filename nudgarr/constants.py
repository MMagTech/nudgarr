"""
nudgarr/constants.py

Static configuration: version string, runtime file paths (from env),
and the DEFAULT_CONFIG dict that new installs are seeded from.

No imports from within the nudgarr package — stdlib only.
"""

import os
from typing import Any, Dict

VERSION = "3.2.0"

CONFIG_FILE = os.getenv("CONFIG_FILE", "/config/nudgarr-config.json")
STATE_FILE = os.getenv("STATE_FILE", "/config/nudgarr-state.json")
STATS_FILE = os.getenv("STATS_FILE", "/config/nudgarr-stats.json")
EXCLUSIONS_FILE = os.getenv("EXCLUSIONS_FILE", "/config/nudgarr-exclusions.json")
DB_FILE = os.getenv("DB_FILE", "/config/nudgarr.db")
PORT = int(os.getenv("PORT", "8085"))

DEFAULT_CONFIG: Dict[str, Any] = {
    "scheduler_enabled": False,        # off by default — user enables deliberately
    "cron_expression": "0 */6 * * *",  # default: every 6 hours on the clock

    "cooldown_hours": 48,
    "sample_mode": "random",           # legacy — still accepted as fallback
    "radarr_sample_mode": "random",    # random | alphabetical | oldest_added | newest_added
    "sonarr_sample_mode": "random",    # random | alphabetical | oldest_added | newest_added

    "radarr_max_movies_per_run": 1,
    "sonarr_max_episodes_per_run": 1,

    # Optional Radarr backlog missing nudges (OFF by default)
    "radarr_backlog_enabled": False,
    "radarr_missing_max": 1,
    "radarr_missing_added_days": 14,

    # Optional Sonarr backlog missing nudges (OFF by default)
    "sonarr_backlog_enabled": False,
    "sonarr_missing_max": 1,
    "sonarr_missing_added_days": 14,

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
    "notify_on_error": True,

    # Onboarding
    "onboarding_complete": False,

    # UI Preferences (v2.5.0)
    "last_seen_version": "",
    "show_support_link": True,

    # Per-Instance Overrides (v3.2.0)
    "per_instance_overrides_enabled": False,
    "per_instance_overrides_seen": False,
}

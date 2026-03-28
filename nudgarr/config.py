"""
nudgarr/config.py

Config loading, validation, and merging.

  deep_copy           -- JSON-based deep clone
  validate_config     -- validates a config dict, returns (ok, [errors])
  load_or_init_config -- loads from disk, merges with DEFAULT_CONFIG,
                         writes back if new keys were added, falls back
                         to defaults on validation failure

Imports from within the package: constants, utils only.
"""

import json
import logging
from typing import Any, Dict, List, Tuple

from nudgarr.constants import CONFIG_FILE, DEFAULT_CONFIG, VALID_SAMPLE_MODES, VALID_BACKLOG_SAMPLE_MODES
from nudgarr.utils import load_json, save_json_atomic

logger = logging.getLogger(__name__)


def deep_copy(obj: Any) -> Any:
    """JSON round-trip deep clone. Safer than copy.deepcopy for config dicts
    since it strips any non-serialisable objects and guarantees a plain dict."""
    return json.loads(json.dumps(obj))


def validate_config(cfg: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate a config dict against all required field types and constraints.
    Checks scheduler fields, cron expression, sample modes, numeric bounds,
    instance structure, and the per-instance overrides block (v3.2.0+).
    Returns (ok, errors) where ok is False if any errors were found."""
    errs: List[str] = []

    if not isinstance(cfg.get("scheduler_enabled"), bool):
        errs.append("scheduler_enabled must be boolean")

    if not isinstance(cfg.get("cron_expression"), str):
        errs.append("cron_expression must be a string")
    elif cfg.get("scheduler_enabled"):
        parts = cfg["cron_expression"].strip().split()
        if len(parts) != 5:
            errs.append("cron_expression must be a valid 5-field cron string")

    for mode_key in ("radarr_sample_mode", "sonarr_sample_mode"):
        if cfg.get(mode_key) not in VALID_SAMPLE_MODES:
            errs.append(f"{mode_key} must be one of {VALID_SAMPLE_MODES}")

    # Backlog sample mode — independent pipeline, validated against VALID_BACKLOG_SAMPLE_MODES
    for mode_key in ("radarr_backlog_sample_mode", "sonarr_backlog_sample_mode"):
        if cfg.get(mode_key) not in VALID_BACKLOG_SAMPLE_MODES:
            errs.append(f"{mode_key} must be one of {VALID_BACKLOG_SAMPLE_MODES}")

    for k in (
        "radarr_max_movies_per_run",
        "sonarr_max_episodes_per_run",
        "cooldown_hours",
        "sleep_seconds",
        "jitter_seconds",
        "state_retention_days",
        "radarr_missing_max",
        "radarr_missing_added_days",
        "sonarr_missing_max",
        "sonarr_missing_added_days",
        "auto_exclude_movies_threshold",
        "auto_exclude_shows_threshold",
        "auto_unexclude_movies_days",
        "auto_unexclude_shows_days",
    ):
        v = cfg.get(k)
        if not isinstance(v, int) or v < 0:
            errs.append(f"{k} must be an int >= 0")

    v = cfg.get("batch_size")
    if not isinstance(v, int) or v < 1:
        errs.append("batch_size must be an int >= 1")

    inst = cfg.get("instances")
    if not isinstance(inst, dict):
        errs.append("instances must be an object with keys: radarr, sonarr")
    else:
        for app in ("radarr", "sonarr"):
            items = inst.get(app)
            if not isinstance(items, list):
                errs.append(f"instances.{app} must be a list")
            else:
                for i, item in enumerate(items):
                    if not isinstance(item, dict):
                        errs.append(f"instances.{app}[{i}] must be an object")
                        continue
                    for f in ("name", "url", "key"):
                        if not item.get(f):
                            errs.append(f"instances.{app}[{i}].{f} is required")
                    # Validate overrides block if present — only check fields that exist
                    overrides = item.get("overrides", {})
                    if not isinstance(overrides, dict):
                        errs.append(f"instances.{app}[{i}].overrides must be an object")
                    else:
                        for ov_key in ("cooldown_hours", "max_cutoff_unmet", "max_backlog", "max_missing_days"):
                            v = overrides.get(ov_key)
                            if v is not None and (not isinstance(v, int) or v < 0):
                                errs.append(f"instances.{app}[{i}].overrides.{ov_key} must be an int >= 0")
                        sm = overrides.get("sample_mode")
                        if sm is not None and sm not in VALID_SAMPLE_MODES:
                            errs.append(f"instances.{app}[{i}].overrides.sample_mode must be one of {VALID_SAMPLE_MODES}")
                        # Backlog sample mode override — validated against VALID_BACKLOG_SAMPLE_MODES
                        bsm = overrides.get("backlog_sample_mode")
                        if bsm is not None and bsm not in VALID_BACKLOG_SAMPLE_MODES:
                            errs.append(f"instances.{app}[{i}].overrides.backlog_sample_mode must be one of {VALID_BACKLOG_SAMPLE_MODES}")
                        be = overrides.get("backlog_enabled")
                        if be is not None and not isinstance(be, bool):
                            errs.append(f"instances.{app}[{i}].overrides.backlog_enabled must be boolean")
                        ne = overrides.get("notifications_enabled")
                        if ne is not None and not isinstance(ne, bool):
                            errs.append(f"instances.{app}[{i}].overrides.notifications_enabled must be boolean")

    for bool_key in ("per_instance_overrides_enabled", "per_instance_overrides_seen", "per_instance_overrides_seen_mobile"):
        v = cfg.get(bool_key)
        if v is not None and not isinstance(v, bool):
            errs.append(f"{bool_key} must be boolean")

    log_level = cfg.get("log_level")
    if log_level is not None and log_level not in ("DEBUG", "INFO", "WARNING", "ERROR"):
        errs.append("log_level must be one of: DEBUG, INFO, WARNING, ERROR")

    # Maintenance Window (v4.2.0)
    mw_enabled = cfg.get("maintenance_window_enabled")
    if mw_enabled is not None and not isinstance(mw_enabled, bool):
        errs.append("maintenance_window_enabled must be boolean")
    for time_key in ("maintenance_window_start", "maintenance_window_end"):
        t = cfg.get(time_key)
        if t is not None:
            import re as _re
            if not isinstance(t, str) or not _re.match(r"^\d{2}:\d{2}$", t):
                errs.append(f"{time_key} must be a string in HH:MM format")
    mw_days = cfg.get("maintenance_window_days")
    if mw_days is not None:
        if not isinstance(mw_days, list):
            errs.append("maintenance_window_days must be a list")
        elif not all(isinstance(d, int) and 0 <= d <= 6 for d in mw_days):
            errs.append("maintenance_window_days must be a list of integers 0-6")

    return (len(errs) == 0), errs


def load_or_init_config() -> Dict[str, Any]:
    """Load config from disk, merge with DEFAULT_CONFIG, and return the result.
    If the file is missing or unreadable, seeds it from defaults and returns that.
    Applies the v3.1.0 run_interval_minutes -> cron_expression migration if needed,
    drops legacy keys (run_interval_minutes, cron_enabled), and writes back to disk
    only when the merged result differs from what was on disk (e.g. new default keys
    were added). Falls back to defaults if validation fails after merging."""
    cfg = load_json(CONFIG_FILE, None)
    if not isinstance(cfg, dict):
        cfg = deep_copy(DEFAULT_CONFIG)
        save_json_atomic(CONFIG_FILE, cfg, pretty=True)
        return cfg

    merged = deep_copy(DEFAULT_CONFIG)
    # Capture any _config_reset_keys persisted from a previous validation failure
    # before the merge loop (which skips the key). This ensures api_get_config
    # can find it even when validation passes on this load.
    _persisted_reset_keys = cfg.get("_config_reset_keys") or []
    # merge non-instance keys — skip _config_reset_keys so it never leaks into merged
    # from a previous write; it is only ever set explicitly in the validation block below.
    for k, v in cfg.items():
        if k != "instances" and k != "_config_reset_keys":
            merged[k] = v
    # merge instances
    merged["instances"]["radarr"] = cfg.get("instances", {}).get("radarr", merged["instances"]["radarr"])
    merged["instances"]["sonarr"] = cfg.get("instances", {}).get("sonarr", merged["instances"]["sonarr"])

    # ── Migration: interval → cron (v3.1.0) ──
    # Old installs may have run_interval_minutes and/or cron_enabled.
    # Convert to cron_expression if missing or empty, then drop legacy keys.
    if not merged.get("cron_expression"):
        interval_min = cfg.get("run_interval_minutes")
        converted = False
        if isinstance(interval_min, int) and interval_min > 0:
            if interval_min < 60 and 60 % interval_min == 0:
                # Sub-hour clean divisor e.g. 30 → */30 * * * *
                merged["cron_expression"] = f"*/{interval_min} * * * *"
                converted = True
            elif interval_min % 60 == 0:
                hours = interval_min // 60
                if hours == 1:
                    merged["cron_expression"] = "0 * * * *"
                else:
                    merged["cron_expression"] = f"0 */{hours} * * *"
                converted = True
        if not converted:
            merged["cron_expression"] = DEFAULT_CONFIG["cron_expression"]

    # Drop legacy keys that no longer exist in DEFAULT_CONFIG
    for legacy_key in ("run_interval_minutes", "cron_enabled"):
        merged.pop(legacy_key, None)

    ok, errs = validate_config(merged)
    if not ok:
        logger.warning("Config validation failed on some keys — resetting only affected keys to defaults: %s", errs)
        # Non-destructive recovery: reset only the specific keys that failed
        # rather than discarding the entire config. This preserves instances,
        # credentials, and all other settings when a single key is bad.
        _FIELD_DEFAULTS = {
            "scheduler_enabled": DEFAULT_CONFIG["scheduler_enabled"],
            "cron_expression": DEFAULT_CONFIG["cron_expression"],
            "radarr_sample_mode": DEFAULT_CONFIG["radarr_sample_mode"],
            "sonarr_sample_mode": DEFAULT_CONFIG["sonarr_sample_mode"],
            "radarr_backlog_sample_mode": DEFAULT_CONFIG["radarr_backlog_sample_mode"],
            "sonarr_backlog_sample_mode": DEFAULT_CONFIG["sonarr_backlog_sample_mode"],
            "radarr_max_movies_per_run": DEFAULT_CONFIG["radarr_max_movies_per_run"],
            "sonarr_max_episodes_per_run": DEFAULT_CONFIG["sonarr_max_episodes_per_run"],
            "cooldown_hours": DEFAULT_CONFIG["cooldown_hours"],
            "sleep_seconds": DEFAULT_CONFIG["sleep_seconds"],
            "jitter_seconds": DEFAULT_CONFIG["jitter_seconds"],
            "batch_size": DEFAULT_CONFIG["batch_size"],
            "state_retention_days": DEFAULT_CONFIG["state_retention_days"],
            "radarr_missing_max": DEFAULT_CONFIG["radarr_missing_max"],
            "radarr_missing_added_days": DEFAULT_CONFIG["radarr_missing_added_days"],
            "sonarr_missing_max": DEFAULT_CONFIG["sonarr_missing_max"],
            "sonarr_missing_added_days": DEFAULT_CONFIG["sonarr_missing_added_days"],
            "auto_exclude_movies_threshold": DEFAULT_CONFIG["auto_exclude_movies_threshold"],
            "auto_exclude_shows_threshold": DEFAULT_CONFIG["auto_exclude_shows_threshold"],
            "auto_unexclude_movies_days": DEFAULT_CONFIG["auto_unexclude_movies_days"],
            "auto_unexclude_shows_days": DEFAULT_CONFIG["auto_unexclude_shows_days"],
            "log_level": DEFAULT_CONFIG["log_level"],
            "maintenance_window_enabled": DEFAULT_CONFIG["maintenance_window_enabled"],
            "maintenance_window_start": DEFAULT_CONFIG["maintenance_window_start"],
            "maintenance_window_end": DEFAULT_CONFIG["maintenance_window_end"],
            "maintenance_window_days": DEFAULT_CONFIG["maintenance_window_days"],
        }
        reset_keys = []
        for err in errs:
            for field in _FIELD_DEFAULTS:
                if err.startswith(field):
                    merged[field] = deep_copy(_FIELD_DEFAULTS[field])
                    if field not in reset_keys:
                        reset_keys.append(field)
                    break
        if reset_keys:
            merged["_config_reset_keys"] = reset_keys
            logger.warning("Reset keys to defaults: %s", reset_keys)
    elif _persisted_reset_keys:
        # Validation passed but a previous run wrote reset keys to disk — carry them
        # through so api_get_config can surface them to the browser.
        merged["_config_reset_keys"] = _persisted_reset_keys

    # Only persist new default keys added since last run. If validation failed,
    # leave the bad values on disk — the user must Acknowledge the popup before
    # they are corrected. Only write _config_reset_keys alongside the bad values
    # so it survives restarts until the user acknowledges.
    clean = {k: v for k, v in merged.items() if k != "_config_reset_keys"}
    if merged.get("_config_reset_keys") and not _persisted_reset_keys:
        # First detection — write bad config + reset key list to disk.
        to_write = dict(cfg)
        to_write["_config_reset_keys"] = merged["_config_reset_keys"]
        save_json_atomic(CONFIG_FILE, to_write, pretty=True)
    elif not merged.get("_config_reset_keys") and clean != cfg:
        # No validation issues — persist any new default keys added.
        save_json_atomic(CONFIG_FILE, clean, pretty=True)
    return merged

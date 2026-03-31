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
import re
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
        "radarr_missing_grace_hours",
        "sonarr_missing_max",
        "sonarr_missing_grace_hours",
        "auto_exclude_movies_threshold",
        "auto_exclude_shows_threshold",
        "auto_unexclude_movies_days",
        "auto_unexclude_shows_days",
        "cf_score_sync_hours",
        "radarr_cf_max_per_run",
        "sonarr_cf_max_per_run",
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
                        for ov_key in ("cooldown_hours", "max_cutoff_unmet", "max_backlog",
                                       "max_missing_days", "missing_grace_hours", "cf_max"):
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

    for bool_key in (
        "per_instance_overrides_enabled", "per_instance_overrides_seen",
        "radarr_backlog_enabled",
        "sonarr_backlog_enabled", "notify_enabled", "notify_on_sweep_complete",
        "notify_on_import", "notify_on_error", "notify_on_auto_exclusion",
        "cf_score_enabled",
        "radarr_cutoff_enabled", "sonarr_cutoff_enabled",
        "radarr_auto_exclude_enabled", "sonarr_auto_exclude_enabled",
    ):
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
            if not isinstance(t, str) or not re.match(r"^\d{2}:\d{2}$", t):
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
    were added). Invalid values are reset to defaults with a warning logged."""
    cfg = load_json(CONFIG_FILE, None)
    if not isinstance(cfg, dict):
        cfg = deep_copy(DEFAULT_CONFIG)
        save_json_atomic(CONFIG_FILE, cfg, pretty=True)
        return cfg

    merged = deep_copy(DEFAULT_CONFIG)
    for k, v in cfg.items():
        if k != "instances":
            merged[k] = v
    merged["instances"]["radarr"] = cfg.get("instances", {}).get("radarr", merged["instances"]["radarr"])
    merged["instances"]["sonarr"] = cfg.get("instances", {}).get("sonarr", merged["instances"]["sonarr"])

    # ── Migration: interval → cron (v3.1.0) ──
    if not merged.get("cron_expression"):
        interval_min = cfg.get("run_interval_minutes")
        converted = False
        if isinstance(interval_min, int) and interval_min > 0:
            if interval_min < 60 and 60 % interval_min == 0:
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

    for legacy_key in ("run_interval_minutes", "cron_enabled"):
        merged.pop(legacy_key, None)

    # Migration (v4.2.0): radarr_cutoff_enabled / sonarr_cutoff_enabled introduced.
    # If the key is absent and the corresponding max is 0, the user was using 0 as
    # a disable mechanism — preserve that intent by setting enabled=False and
    # resetting max to 1 so 0 now correctly means "all eligible".
    for app, max_key, toggle_key in (
        ("radarr", "radarr_max_movies_per_run", "radarr_cutoff_enabled"),
        ("sonarr", "sonarr_max_episodes_per_run", "sonarr_cutoff_enabled"),
    ):
        if toggle_key not in cfg and int(merged.get(max_key, 1)) == 0:
            merged[toggle_key] = False
            merged[max_key] = 1
            logger.info(
                "Migration: %s was 0 (used as disable). Set %s=False, %s=1.",
                max_key, toggle_key, max_key,
            )

    # Migration (v4.2.0): radarr_auto_exclude_enabled / sonarr_auto_exclude_enabled introduced.
    # If the key is absent and the threshold is > 0, the user had auto-exclusion active —
    # set enabled=True to preserve that behaviour. If threshold is 0, enabled stays False.
    for threshold_key, toggle_key in (
        ("auto_exclude_movies_threshold", "radarr_auto_exclude_enabled"),
        ("auto_exclude_shows_threshold", "sonarr_auto_exclude_enabled"),
    ):
        if toggle_key not in cfg:
            threshold = int(merged.get(threshold_key, 0))
            if threshold > 0:
                merged[toggle_key] = True
                logger.info(
                    "Migration: %s=%d found, setting %s=True.",
                    threshold_key, threshold, toggle_key,
                )

    # Migration (v4.2.0): remove keys that no longer exist in DEFAULT_CONFIG.
    # sonarr_missing_added_days — Sonarr never had a missing-added-days filter (Radarr-only).
    # per_instance_overrides_seen_mobile — mobile UI removed in v4.2.0.
    # notify_on_queue_threshold / dry_run — features never shipped; were leftover in validation only.
    for dead_key in (
        "sonarr_missing_added_days",
        "per_instance_overrides_seen_mobile",
        "notify_on_queue_threshold",
        "dry_run",
    ):
        if dead_key in merged:
            merged.pop(dead_key)
            logger.info("Migration: removed dead config key '%s'.", dead_key)

    ok, errs = validate_config(merged)
    if not ok:
        logger.warning("Config validation failed — resetting affected keys to defaults: %s", errs)
        for err in errs:
            for field, default in DEFAULT_CONFIG.items():
                if err.startswith(field) and not isinstance(default, dict):
                    merged[field] = deep_copy(default)
                    logger.warning("Reset %s to default: %r", field, default)
                    break

    if merged != cfg:
        save_json_atomic(CONFIG_FILE, merged, pretty=True)
    return merged

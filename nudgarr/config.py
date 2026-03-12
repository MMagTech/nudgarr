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
from typing import Any, Dict, List, Tuple

from nudgarr.constants import CONFIG_FILE, DEFAULT_CONFIG
from nudgarr.utils import load_json, save_json_atomic


def deep_copy(obj: Any) -> Any:
    return json.loads(json.dumps(obj))


def validate_config(cfg: Dict[str, Any]) -> Tuple[bool, List[str]]:
    errs: List[str] = []

    if not isinstance(cfg.get("scheduler_enabled"), bool):
        errs.append("scheduler_enabled must be boolean")

    if not isinstance(cfg.get("cron_expression"), str):
        errs.append("cron_expression must be a string")
    else:
        parts = cfg["cron_expression"].strip().split()
        if len(parts) != 5:
            errs.append("cron_expression must be a valid 5-field cron string")

    VALID_MODES = ("random", "alphabetical", "oldest_added", "newest_added")
    for mode_key in ("radarr_sample_mode", "sonarr_sample_mode"):
        if cfg.get(mode_key) not in VALID_MODES:
            errs.append(f"{mode_key} must be one of {VALID_MODES}")

    for k in (
        "radarr_max_movies_per_run",
        "sonarr_max_episodes_per_run",
        "cooldown_hours",
        "sleep_seconds",
        "jitter_seconds",
        "state_retention_days",
        "radarr_missing_max",
        "radarr_missing_added_days",
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

    return (len(errs) == 0), errs


def load_or_init_config() -> Dict[str, Any]:
    cfg = load_json(CONFIG_FILE, None)
    if not isinstance(cfg, dict):
        cfg = deep_copy(DEFAULT_CONFIG)
        save_json_atomic(CONFIG_FILE, cfg, pretty=True)
        return cfg

    merged = deep_copy(DEFAULT_CONFIG)
    # merge non-instance keys
    for k, v in cfg.items():
        if k != "instances":
            merged[k] = v
    # merge instances
    merged["instances"]["radarr"] = cfg.get("instances", {}).get("radarr", merged["instances"]["radarr"])
    merged["instances"]["sonarr"] = cfg.get("instances", {}).get("sonarr", merged["instances"]["sonarr"])

    # ── Migration: interval → cron (v3.2.0) ──
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
        print("⚠️ Config validation failed; using defaults for this run:")
        for e in errs:
            print(f"  - {e}")
        return deep_copy(DEFAULT_CONFIG)

    # Only persist if merged differs from what was on disk (e.g. new default keys added)
    if merged != cfg:
        save_json_atomic(CONFIG_FILE, merged, pretty=True)
    return merged

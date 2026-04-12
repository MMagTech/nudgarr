"""
Effective CF Score enablement (master + per-app + per-instance overrides).

Used by the CF syncer, sweep pipeline, status/health APIs, and config-save pruning.
"""

import logging
from typing import Any, Dict, Set

logger = logging.getLogger(__name__)


def _make_instance_id(app: str, url: str) -> str:
    """Same composite key as cf_score_syncer._make_instance_id (no import cycle)."""
    return f"{app}|{url.rstrip('/')}"


# Must match cf_score_syncer.CF_SYNC_PROGRESS_PREFIX (avoid importing syncer here).
_CF_SYNC_PROGRESS_PREFIX = "cf_sync_progress|"
# Written when an instance finishes a CF sync run; survives row prune when CF is disabled.
CF_LAST_INSTANCE_SYNC_PREFIX = "cf_last_instance_sync|"
# Per-instance last scan size for Intel (movie files or series stepped); JSON {"scanned": N}.
CF_SCAN_SNAPSHOT_PREFIX = "cf_intel_scan_snapshot|"


def effective_cf_score_enabled(cfg: Dict[str, Any], app: str, inst: Dict[str, Any]) -> bool:
    """Return True if this instance should participate in CF Score sync and sweep.

    False when any of: master off, per-app toggle off, instance disabled in Instances,
    or per-instance override explicitly disables CF Score for this app.
    """
    if not cfg.get("cf_score_enabled", False):
        return False
    if app == "radarr":
        if not cfg.get("radarr_cf_score_enabled", True):
            return False
    elif app == "sonarr":
        if not cfg.get("sonarr_cf_score_enabled", True):
            return False
    else:
        return False
    if not inst.get("enabled", True):
        return False
    ov_en = bool(cfg.get("per_instance_overrides_enabled", False))
    if not ov_en:
        return True
    ov = inst.get("overrides") or {}
    key = "radarr_cf_score_enabled" if app == "radarr" else "sonarr_cf_score_enabled"
    if key in ov and ov[key] is not None:
        return bool(ov[key])
    return True


def allowed_cf_score_instance_ids(cfg: Dict[str, Any]) -> Set[str]:
    """Set of arr_instance_id values that should retain rows in cf_score_entries."""
    out: Set[str] = set()
    for app in ("radarr", "sonarr"):
        for inst in cfg.get("instances", {}).get(app, []):
            if not effective_cf_score_enabled(cfg, app, inst):
                continue
            url = inst.get("url") or ""
            if not url.strip():
                continue
            out.add(_make_instance_id(app, url))
    return out


def prune_cf_entries_on_effective_disable_transition(previous_cfg: Dict[str, Any], new_cfg: Dict[str, Any]) -> None:
    """DELETE cf_score_entries for instances that transitioned from effectively enabled to disabled.

    Also removes rows for instance IDs that disappeared from config (rename/delete).
    Silent — intended for config save paths.
    """
    from nudgarr import db

    def _effective_map(cfg: Dict[str, Any]) -> Dict[str, bool]:
        m: Dict[str, bool] = {}
        for app in ("radarr", "sonarr"):
            for inst in cfg.get("instances", {}).get(app, []):
                url = (inst.get("url") or "").strip()
                if not url:
                    continue
                aid = _make_instance_id(app, url)
                m[aid] = effective_cf_score_enabled(cfg, app, inst)
        return m

    old_m = _effective_map(previous_cfg)
    new_m = _effective_map(new_cfg)
    for aid, was_on in old_m.items():
        if was_on and not new_m.get(aid, False):
            try:
                ts = db.get_cf_max_last_synced_at_for_instance(aid)
                if ts:
                    db.set_state(CF_LAST_INSTANCE_SYNC_PREFIX + aid, ts)
            except Exception:
                logger.exception(
                    "CF Score: failed to persist last sync time for %s (non-fatal)", aid
                )
            db.delete_cf_scores_for_instance(aid)
            try:
                db.delete_state(_CF_SYNC_PROGRESS_PREFIX + aid)
            except Exception:
                logger.exception("CF Score: failed to clear sync progress for %s (non-fatal)", aid)

"""
nudgarr/filter_scope.py

Per-pipeline resolution of tag / quality profile sweep filters.

A sweep filter has always applied to every pipeline. With Filter Pipeline
Scope enabled, each filtered tag or profile may instead name the subset of
pipelines it applies to via two optional maps on the instance config:

    "sweep_filters": {
        "excluded_tags": [1, 3],
        "excluded_profiles": [6],
        "tag_pipelines":     { "3": ["cfscore"] },
        "profile_pipelines": { "6": ["cutoff", "backlog"] }
    }

An id absent from its map applies to ALL pipelines — so a config written
before this feature existed, or one that never narrows anything, behaves
byte-identically to the legacy all-pipelines behaviour. The same is true
whenever the master toggle (filter_pipeline_scope_enabled) is off: scope
maps are ignored entirely but preserved in config, mirroring how
Per-Instance Overrides survive their toggle.

Consumers: sweep.py resolves "cutoff" and "backlog" per instance;
cf_score_syncer.py resolves "cfscore" at index-build time.

Imports from within the package: none (mirrors cf_effective.py).
"""

import logging
from typing import Any, Dict, Set, Tuple

logger = logging.getLogger(__name__)

# Canonical pipeline names, matching the three sweep pipelines.
PIPELINES = ("cutoff", "backlog", "cfscore")


def _applies(pipeline: str, scope_map: Dict[str, Any], item_id: int) -> bool:
    """True if the filter for item_id applies to pipeline.

    Absent id -> applies everywhere. A malformed entry (not a list) is
    treated as absent so a hand-edited config degrades to legacy behaviour
    rather than silently disabling a filter.
    """
    entry = scope_map.get(str(item_id))
    if not isinstance(entry, (list, tuple)):
        return True
    return pipeline in entry


def scoped_filter_sets(
    cfg: Dict[str, Any],
    inst: Dict[str, Any],
    pipeline: str,
) -> Tuple[Set[int], Set[int]]:
    """Return (excluded_tags, excluded_profiles) applicable to one pipeline.

    With filter_pipeline_scope_enabled off (or absent — the upgrade default)
    this returns the full legacy sets regardless of any scope maps present.
    """
    assert pipeline in PIPELINES, f"Unknown pipeline: {pipeline}"
    sf = inst.get("sweep_filters") or {}
    try:
        tags = set(int(t) for t in sf.get("excluded_tags") or [])
        profiles = set(int(p) for p in sf.get("excluded_profiles") or [])
    except (TypeError, ValueError):
        logger.warning("sweep_filters contains non-integer ids — ignoring filters for this instance")
        return set(), set()

    if not cfg.get("filter_pipeline_scope_enabled", False):
        return tags, profiles

    tag_map = sf.get("tag_pipelines") or {}
    profile_map = sf.get("profile_pipelines") or {}
    if not isinstance(tag_map, dict):
        tag_map = {}
    if not isinstance(profile_map, dict):
        profile_map = {}

    return (
        {t for t in tags if _applies(pipeline, tag_map, t)},
        {p for p in profiles if _applies(pipeline, profile_map, p)},
    )

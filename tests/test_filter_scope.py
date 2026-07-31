"""
tests/test_filter_scope.py

Unit tests for Filter Pipeline Scope (per-pipeline tag/profile filters).

Covers three layers:
  1. scoped_filter_sets — the resolver, including the backward-compat
     guarantee: legacy configs and a disabled toggle behave byte-identically
     to the all-pipelines behaviour.
  2. routes.arr._merge_sweep_filters / _normalize_pipeline_map — the
     merge-preserving save that stops older clients clobbering scope maps.
  3. sweep._sweep_instance — integration: which items each pipeline
     actually searches under scoped configs, plus the new
     skipped_excluded_backlog counter. All arr HTTP and db calls mocked.

Zero live HTTP; zero real database writes.
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from nudgarr.config import validate_config
from nudgarr.constants import DEFAULT_CONFIG
from nudgarr.filter_scope import PIPELINES, scoped_filter_sets
from nudgarr.routes.arr import _merge_sweep_filters, _normalize_pipeline_map


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _inst(sweep_filters=None):
    inst = {"name": "R", "url": "http://radarr:7878", "key": "k", "enabled": True}
    if sweep_filters is not None:
        inst["sweep_filters"] = sweep_filters
    return inst


def _cfg(scope_enabled=None):
    cfg = {"instances": {"radarr": [], "sonarr": []}}
    if scope_enabled is not None:
        cfg["filter_pipeline_scope_enabled"] = scope_enabled
    return cfg


LEGACY_SF = {"excluded_tags": [1, 3], "excluded_profiles": [6]}

SCOPED_SF = {
    "excluded_tags": [1, 3],
    "excluded_profiles": [6],
    "tag_pipelines": {"3": ["cfscore"]},
    "profile_pipelines": {"6": ["cutoff", "backlog"]},
}


# ---------------------------------------------------------------------------
# 1. Resolver — backward compatibility
# ---------------------------------------------------------------------------

def test_legacy_config_all_pipelines():
    """A pre-feature config resolves identically for every pipeline."""
    for pipeline in PIPELINES:
        tags, profiles = scoped_filter_sets(_cfg(), _inst(LEGACY_SF), pipeline)
        assert tags == {1, 3}
        assert profiles == {6}


def test_toggle_absent_ignores_scope_maps():
    """Scope maps present but toggle key missing (upgrade default) — legacy sets."""
    for pipeline in PIPELINES:
        tags, profiles = scoped_filter_sets(_cfg(), _inst(SCOPED_SF), pipeline)
        assert tags == {1, 3}
        assert profiles == {6}


def test_toggle_off_ignores_scope_maps():
    """Explicitly disabled toggle — scope maps preserved but inert."""
    for pipeline in PIPELINES:
        tags, profiles = scoped_filter_sets(_cfg(False), _inst(SCOPED_SF), pipeline)
        assert tags == {1, 3}
        assert profiles == {6}


def test_no_filters_at_all():
    """Instance without sweep_filters resolves to empty sets."""
    tags, profiles = scoped_filter_sets(_cfg(True), _inst(), "cutoff")
    assert tags == set() and profiles == set()


# ---------------------------------------------------------------------------
# 1b. Resolver — scoping enabled
# ---------------------------------------------------------------------------

def test_scoped_tag_narrows_per_pipeline():
    """Tag 3 scoped to cfscore only; tag 1 unscoped applies everywhere."""
    cfg, inst = _cfg(True), _inst(SCOPED_SF)
    assert scoped_filter_sets(cfg, inst, "cutoff")[0] == {1}
    assert scoped_filter_sets(cfg, inst, "backlog")[0] == {1}
    assert scoped_filter_sets(cfg, inst, "cfscore")[0] == {1, 3}


def test_scoped_profile_narrows_per_pipeline():
    """Profile 6 scoped to cutoff+backlog — absent from cfscore."""
    cfg, inst = _cfg(True), _inst(SCOPED_SF)
    assert scoped_filter_sets(cfg, inst, "cutoff")[1] == {6}
    assert scoped_filter_sets(cfg, inst, "backlog")[1] == {6}
    assert scoped_filter_sets(cfg, inst, "cfscore")[1] == set()


def test_malformed_scope_entry_degrades_to_all_pipelines():
    """A hand-edited non-list entry must not silently disable the filter."""
    sf = dict(SCOPED_SF, tag_pipelines={"3": "cfscore"})  # string, not list
    tags, _ = scoped_filter_sets(_cfg(True), _inst(sf), "cutoff")
    assert tags == {1, 3}


def test_malformed_scope_map_degrades_to_all_pipelines():
    """tag_pipelines that isn't a dict is ignored entirely."""
    sf = dict(SCOPED_SF, tag_pipelines=["cfscore"])
    tags, _ = scoped_filter_sets(_cfg(True), _inst(sf), "cutoff")
    assert tags == {1, 3}


def test_unknown_pipeline_asserts():
    with pytest.raises(AssertionError):
        scoped_filter_sets(_cfg(), _inst(), "bogus")


# ---------------------------------------------------------------------------
# 2. Merge-preserving save
# ---------------------------------------------------------------------------

def test_merge_preserves_scope_when_payload_omits_maps():
    """A pre-feature client saving tags must not clobber stored scope maps."""
    stored = dict(SCOPED_SF)
    merged, err = _merge_sweep_filters(stored, [1, 3], [6], {"excluded_tags": [1, 3]})
    assert err is None
    assert merged["tag_pipelines"] == {"3": ["cfscore"]}
    assert merged["profile_pipelines"] == {"6": ["backlog", "cutoff"]}


def test_merge_preserves_unknown_keys():
    """Future fields on sweep_filters survive every save."""
    stored = dict(LEGACY_SF, future_field={"x": 1})
    merged, err = _merge_sweep_filters(stored, [1], [], {})
    assert err is None
    assert merged["future_field"] == {"x": 1}


def test_merge_prunes_scope_for_removed_ids():
    """Deleting a filter drops its now-meaningless scope entry."""
    merged, err = _merge_sweep_filters(dict(SCOPED_SF), [1], [], {"excluded_tags": [1]})
    assert err is None
    assert "tag_pipelines" not in merged
    assert "profile_pipelines" not in merged
    assert merged["excluded_tags"] == [1]


def test_merge_accepts_payload_maps():
    merged, err = _merge_sweep_filters(
        dict(LEGACY_SF), [1, 3], [6],
        {"tag_pipelines": {"1": ["backlog"]}},
    )
    assert err is None
    assert merged["tag_pipelines"] == {"1": ["backlog"]}


def test_merge_drops_full_scope_entries():
    """Naming all three pipelines equals absence — stored config stays minimal."""
    merged, err = _merge_sweep_filters(
        dict(LEGACY_SF), [1], [],
        {"tag_pipelines": {"1": ["cutoff", "backlog", "cfscore"]}},
    )
    assert err is None
    assert "tag_pipelines" not in merged


def test_merge_rejects_bad_pipeline_name():
    merged, err = _merge_sweep_filters(
        dict(LEGACY_SF), [1], [], {"tag_pipelines": {"1": ["nonsense"]}}
    )
    assert merged is None and "tag_pipelines" in err


def test_normalize_rejects_non_integer_keys():
    out, err = _normalize_pipeline_map({"abc": ["cutoff"]}, {1})
    assert out is None and "integer" in err


def test_normalize_none_is_empty():
    out, err = _normalize_pipeline_map(None, {1})
    assert out == {} and err is None


# ---------------------------------------------------------------------------
# 3. validate_config — no new failure modes
# ---------------------------------------------------------------------------

def test_default_config_still_valid():
    ok, errs = validate_config(dict(DEFAULT_CONFIG))
    assert ok is True and errs == []


def test_scoped_config_passes_validation():
    """Scope maps in instance config produce no validation errors."""
    cfg = dict(DEFAULT_CONFIG)
    cfg["filter_pipeline_scope_enabled"] = True
    cfg["instances"] = {"radarr": [
        {"name": "R", "url": "http://radarr:7878", "key": "k", "sweep_filters": dict(SCOPED_SF)},
    ], "sonarr": []}
    ok, errs = validate_config(cfg)
    assert ok is True and errs == []


def test_toggle_type_is_validated():
    cfg = dict(DEFAULT_CONFIG)
    cfg["filter_pipeline_scope_enabled"] = "yes"
    ok, errs = validate_config(cfg)
    assert ok is False
    assert any("filter_pipeline_scope_enabled" in e for e in errs)


# ---------------------------------------------------------------------------
# 4. Sweep integration — which pipeline searches what
# ---------------------------------------------------------------------------

CUTOFF_ITEMS = [
    {"id": 1, "title": "Plain Movie", "added": "", "isAvailable": True,
     "minimumAvailability": "", "releaseDate": "", "quality_from": "HD",
     "qualityProfileId": 10, "tagIds": []},
    {"id": 2, "title": "Tagged Movie", "added": "", "isAvailable": True,
     "minimumAvailability": "", "releaseDate": "", "quality_from": "HD",
     "qualityProfileId": 10, "tagIds": [5]},
]

MISSING_ITEMS = [
    {"id": 3, "title": "Plain Missing", "added": "", "isAvailable": True,
     "quality_from": "HD", "qualityProfileId": 10, "tagIds": []},
    {"id": 4, "title": "Tagged Missing", "added": "", "isAvailable": True,
     "quality_from": "HD", "qualityProfileId": 10, "tagIds": [5]},
]


def _run_radarr_sweep(sweep_filters, scope_enabled, excluded_titles=None):
    """Run _sweep_instance for one Radarr instance with all IO mocked.

    Returns (searched_ids, summary).
    """
    from nudgarr import sweep as sweep_mod

    searched = []

    def fake_search(session, url, key, ids, instance_name=""):
        searched.extend(ids)

    cfg = {
        "filter_pipeline_scope_enabled": scope_enabled,
        "cf_score_enabled": False,
        "instances": {"radarr": [], "sonarr": []},
    }
    inst = _inst(sweep_filters)

    with patch.object(sweep_mod, "radarr_get_cutoff_unmet_movies",
                      return_value=[dict(m) for m in CUTOFF_ITEMS]), \
         patch.object(sweep_mod, "radarr_get_missing_movies",
                      return_value=[dict(m) for m in MISSING_ITEMS]), \
         patch.object(sweep_mod, "radarr_get_queued_movie_ids", return_value=set()), \
         patch.object(sweep_mod, "radarr_get_movie_quality", return_value="HD"), \
         patch.object(sweep_mod, "radarr_search_movies", side_effect=fake_search), \
         patch.object(sweep_mod, "arr_get_tag_map", return_value={5: "anime"}), \
         patch.object(sweep_mod, "arr_get_profile_map", return_value={10: "HD-1080p"}), \
         patch.object(sweep_mod, "pick_items_with_cooldown",
                      side_effect=lambda items, *a, **k: (list(items), len(items), 0)), \
         patch.object(sweep_mod, "mark_items_searched"), \
         patch.object(sweep_mod, "batch_record_stat_entries"), \
         patch.object(sweep_mod, "jitter_sleep"):
        summary = sweep_mod._sweep_instance(
            MagicMock(spec=requests.Session), inst, cfg,
            excluded_titles or set(),
            cooldown_hours=0, max_per_run=25, sample_mode="alphabetical",
            batch_size=20, sleep_seconds=0, jitter_seconds=0,
            missing_max=25, backlog_enabled=True,
            notifications_enabled=False, app="radarr",
        )
    return searched, summary


def test_sweep_legacy_filter_blocks_everywhere():
    """Toggle off: tag 5 filtered from both cutoff and backlog."""
    searched, summary = _run_radarr_sweep({"excluded_tags": [5], "excluded_profiles": []}, False)
    assert set(searched) == {1, 3}
    assert summary["skipped_tag_cutoff"] == 1
    assert summary["skipped_tag_backlog"] == 1


def test_sweep_cfscore_scoped_tag_releases_cutoff_and_backlog():
    """mogno-jelly's case: tag scoped to cfscore — cutoff and backlog search it."""
    sf = {"excluded_tags": [5], "excluded_profiles": [],
          "tag_pipelines": {"5": ["cfscore"]}}
    searched, summary = _run_radarr_sweep(sf, True)
    assert set(searched) == {1, 2, 3, 4}
    assert summary["skipped_tag_cutoff"] == 0
    assert summary["skipped_tag_backlog"] == 0


def test_sweep_cutoff_scoped_tag_blocks_only_cutoff():
    sf = {"excluded_tags": [5], "excluded_profiles": [],
          "tag_pipelines": {"5": ["cutoff"]}}
    searched, summary = _run_radarr_sweep(sf, True)
    assert set(searched) == {1, 3, 4}
    assert summary["skipped_tag_cutoff"] == 1
    assert summary["skipped_tag_backlog"] == 0


def test_sweep_scope_maps_inert_without_toggle():
    """Maps present, toggle off — behaves exactly like the legacy filter."""
    sf = {"excluded_tags": [5], "excluded_profiles": [],
          "tag_pipelines": {"5": ["cfscore"]}}
    searched_off, _ = _run_radarr_sweep(sf, False)
    searched_legacy, _ = _run_radarr_sweep({"excluded_tags": [5], "excluded_profiles": []}, False)
    assert set(searched_off) == set(searched_legacy) == {1, 3}


def test_sweep_backlog_excluded_counter():
    """New skipped_excluded_backlog counts exclusion-list hits, not filters."""
    searched, summary = _run_radarr_sweep(
        {"excluded_tags": [], "excluded_profiles": []}, False,
        excluded_titles={"tagged missing"},
    )
    assert 4 not in searched
    assert summary["skipped_excluded_backlog"] == 1
    assert summary["skipped_tag_backlog"] == 0

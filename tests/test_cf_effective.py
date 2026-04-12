"""
Unit tests for CF Score effective enablement and config-save pruning.
"""

from unittest.mock import patch

from nudgarr.cf_effective import (
    allowed_cf_score_instance_ids,
    effective_cf_score_enabled,
    prune_cf_entries_on_effective_disable_transition,
)
from nudgarr.constants import DEFAULT_CONFIG


def _inst(name="A", url="http://r:7878", enabled=True, overrides=None):
    return {
        "name": name,
        "url": url,
        "key": "k",
        "enabled": enabled,
        "overrides": overrides if overrides is not None else {},
    }


def _minimal_cfg(**kwargs):
    base = {
        "cf_score_enabled": True,
        "radarr_cf_score_enabled": True,
        "sonarr_cf_score_enabled": True,
        "per_instance_overrides_enabled": False,
        "instances": {"radarr": [_inst()], "sonarr": [_inst(url="http://s:8989", name="S")]},
    }
    base.update(kwargs)
    return base


def test_per_app_keys_missing_default_to_enabled_like_merge():
    """Missing radarr_cf_score_enabled / sonarr_cf_score_enabled behave as True (non-breaking)."""
    cfg = _minimal_cfg()
    del cfg["radarr_cf_score_enabled"]
    del cfg["sonarr_cf_score_enabled"]
    assert effective_cf_score_enabled(cfg, "radarr", cfg["instances"]["radarr"][0]) is True
    assert effective_cf_score_enabled(cfg, "sonarr", cfg["instances"]["sonarr"][0]) is True


def test_default_config_includes_per_app_cf_toggles_true():
    assert DEFAULT_CONFIG.get("radarr_cf_score_enabled") is True
    assert DEFAULT_CONFIG.get("sonarr_cf_score_enabled") is True


def test_per_app_radarr_disabled_skips_instance():
    cfg = _minimal_cfg(radarr_cf_score_enabled=False)
    assert effective_cf_score_enabled(cfg, "radarr", cfg["instances"]["radarr"][0]) is False
    assert effective_cf_score_enabled(cfg, "sonarr", cfg["instances"]["sonarr"][0]) is True


def test_per_instance_override_disables_cf():
    cfg = _minimal_cfg(per_instance_overrides_enabled=True)
    r = _inst(overrides={"radarr_cf_score_enabled": False})
    assert effective_cf_score_enabled(cfg, "radarr", r) is False


def test_master_off_disables_everything():
    cfg = _minimal_cfg(cf_score_enabled=False)
    assert effective_cf_score_enabled(cfg, "radarr", cfg["instances"]["radarr"][0]) is False


def test_allowed_instance_ids_excludes_disabled_app():
    cfg = _minimal_cfg(radarr_cf_score_enabled=False)
    allowed = allowed_cf_score_instance_ids(cfg)
    assert "radarr|http://r:7878" not in allowed
    assert "sonarr|http://s:8989" in allowed


def test_prune_on_transition_calls_delete_once():
    before = _minimal_cfg()
    after = _minimal_cfg(radarr_cf_score_enabled=False)
    with patch("nudgarr.db.delete_cf_scores_for_instance") as m_del, patch(
        "nudgarr.db.delete_state"
    ) as m_st:
        prune_cf_entries_on_effective_disable_transition(before, after)
    m_del.assert_called_once_with("radarr|http://r:7878")
    m_st.assert_called_once_with("cf_sync_progress|radarr|http://r:7878")


def test_prune_not_called_when_no_transition():
    cfg = _minimal_cfg()
    with patch("nudgarr.db.delete_cf_scores_for_instance") as m_del, patch(
        "nudgarr.db.delete_state"
    ) as m_st:
        prune_cf_entries_on_effective_disable_transition(cfg, cfg)
    m_del.assert_not_called()
    m_st.assert_not_called()


def test_prune_orphan_instance_removed_from_config():
    before = _minimal_cfg()
    after = _minimal_cfg()
    after["instances"]["radarr"] = []
    with patch("nudgarr.db.delete_cf_scores_for_instance") as m_del, patch(
        "nudgarr.db.delete_state"
    ) as m_st:
        prune_cf_entries_on_effective_disable_transition(before, after)
    m_del.assert_called_once_with("radarr|http://r:7878")
    m_st.assert_called_once_with("cf_sync_progress|radarr|http://r:7878")

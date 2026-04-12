"""
tests/test_config_validation.py

Unit tests for nudgarr.config.validate_config().
Zero mocking — calls validate_config directly with crafted dicts.
All tests confirm (ok, errs) return values against expected outcomes.
"""

import pytest
from nudgarr.config import validate_config
from nudgarr.constants import DEFAULT_CONFIG


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_cfg(**overrides):
    """Return a copy of DEFAULT_CONFIG with optional overrides applied."""
    cfg = dict(DEFAULT_CONFIG)
    cfg.update(overrides)
    return cfg


def _errs(cfg):
    """Return just the error list from validate_config."""
    ok, errs = validate_config(cfg)
    return errs


def _ok(cfg):
    """Return just the ok bool from validate_config."""
    ok, _ = validate_config(cfg)
    return ok


# ---------------------------------------------------------------------------
# Valid baseline
# ---------------------------------------------------------------------------

def test_default_config_passes():
    """DEFAULT_CONFIG should pass validation with no errors."""
    ok, errs = validate_config(dict(DEFAULT_CONFIG))
    assert ok is True
    assert errs == []


# ---------------------------------------------------------------------------
# scheduler_enabled
# ---------------------------------------------------------------------------

def test_scheduler_enabled_true_passes():
    assert _ok(_valid_cfg(scheduler_enabled=True))


def test_scheduler_enabled_false_passes():
    assert _ok(_valid_cfg(scheduler_enabled=False))


def test_scheduler_enabled_string_fails():
    errs = _errs(_valid_cfg(scheduler_enabled="yes"))
    assert any("scheduler_enabled" in e for e in errs)


def test_scheduler_enabled_none_fails():
    errs = _errs(_valid_cfg(scheduler_enabled=None))
    assert any("scheduler_enabled" in e for e in errs)


# ---------------------------------------------------------------------------
# cron_expression
# ---------------------------------------------------------------------------

def test_valid_cron_passes():
    assert _ok(_valid_cfg(scheduler_enabled=True, cron_expression="0 */6 * * *"))


def test_invalid_cron_field_count_fails():
    errs = _errs(_valid_cfg(scheduler_enabled=True, cron_expression="0 * *"))
    assert any("cron_expression" in e for e in errs)


def test_cron_not_validated_when_scheduler_disabled():
    """Bad cron is not validated when scheduler_enabled=False."""
    errs = _errs(_valid_cfg(scheduler_enabled=False, cron_expression="not_a_cron"))
    assert not any("cron_expression must be a valid" in e for e in errs)


def test_cron_must_be_string():
    errs = _errs(_valid_cfg(cron_expression=12345))
    assert any("cron_expression" in e for e in errs)


# ---------------------------------------------------------------------------
# Sample modes
# ---------------------------------------------------------------------------

def test_valid_sample_mode_passes():
    assert _ok(_valid_cfg(radarr_sample_mode="random", sonarr_sample_mode="alphabetical"))


def test_invalid_radarr_sample_mode_fails():
    errs = _errs(_valid_cfg(radarr_sample_mode="zigzag"))
    assert any("radarr_sample_mode" in e for e in errs)


def test_invalid_sonarr_backlog_sample_mode_fails():
    errs = _errs(_valid_cfg(sonarr_backlog_sample_mode="zigzag"))
    assert any("sonarr_backlog_sample_mode" in e for e in errs)


def test_invalid_cf_sample_mode_fails():
    errs = _errs(_valid_cfg(radarr_cf_sample_mode="zigzag"))
    assert any("radarr_cf_sample_mode" in e for e in errs)


def test_round_robin_valid_for_backlog():
    assert _ok(_valid_cfg(radarr_backlog_sample_mode="round_robin"))


# ---------------------------------------------------------------------------
# Queue depth
# ---------------------------------------------------------------------------

def test_queue_depth_disabled_no_validation():
    """When queue_depth_enabled=False, threshold is not validated."""
    assert _ok(_valid_cfg(queue_depth_enabled=False, queue_depth_threshold=0))


def test_queue_depth_enabled_threshold_one_passes():
    assert _ok(_valid_cfg(queue_depth_enabled=True, queue_depth_threshold=1))


def test_queue_depth_enabled_threshold_zero_fails():
    errs = _errs(_valid_cfg(queue_depth_enabled=True, queue_depth_threshold=0))
    assert any("queue_depth_threshold" in e for e in errs)


def test_queue_depth_enabled_threshold_negative_fails():
    errs = _errs(_valid_cfg(queue_depth_enabled=True, queue_depth_threshold=-1))
    assert any("queue_depth_threshold" in e for e in errs)


def test_queue_depth_enabled_threshold_string_fails():
    errs = _errs(_valid_cfg(queue_depth_enabled=True, queue_depth_threshold="10"))
    assert any("queue_depth_threshold" in e for e in errs)


# ---------------------------------------------------------------------------
# Numeric fields
# ---------------------------------------------------------------------------

def test_cooldown_hours_zero_passes():
    assert _ok(_valid_cfg(cooldown_hours=0))


def test_cooldown_hours_negative_fails():
    errs = _errs(_valid_cfg(cooldown_hours=-1))
    assert any("cooldown_hours" in e for e in errs)


def test_batch_size_one_passes():
    assert _ok(_valid_cfg(batch_size=1))


def test_batch_size_zero_fails():
    errs = _errs(_valid_cfg(batch_size=0))
    assert any("batch_size" in e for e in errs)


def test_batch_size_negative_fails():
    errs = _errs(_valid_cfg(batch_size=-5))
    assert any("batch_size" in e for e in errs)


# ---------------------------------------------------------------------------
# default_tab
# ---------------------------------------------------------------------------

def test_valid_default_tab_passes():
    assert _ok(_valid_cfg(default_tab="sweep"))


def test_invalid_default_tab_fails():
    errs = _errs(_valid_cfg(default_tab="nonexistent"))
    assert any("default_tab" in e for e in errs)


# ---------------------------------------------------------------------------
# Instance structure
# ---------------------------------------------------------------------------

def test_instances_not_dict_fails():
    errs = _errs(_valid_cfg(instances="bad"))
    assert any("instances" in e for e in errs)


def test_instance_missing_url_fails():
    cfg = _valid_cfg()
    cfg["instances"] = {"radarr": [{"name": "R", "key": "abc"}], "sonarr": []}
    errs = _errs(cfg)
    assert any("url" in e for e in errs)


def test_instance_missing_key_fails():
    cfg = _valid_cfg()
    cfg["instances"] = {"radarr": [{"name": "R", "url": "http://radarr"}], "sonarr": []}
    errs = _errs(cfg)
    assert any(".key" in e for e in errs)


def test_valid_instance_passes():
    cfg = _valid_cfg()
    cfg["instances"] = {
        "radarr": [{"name": "R", "url": "http://radarr", "key": "abc"}],
        "sonarr": [],
    }
    assert _ok(cfg)


def test_override_invalid_sample_mode_fails():
    cfg = _valid_cfg()
    cfg["instances"] = {
        "radarr": [{
            "name": "R", "url": "http://radarr", "key": "abc",
            "overrides": {"sample_mode": "bogus"},
        }],
        "sonarr": [],
    }
    errs = _errs(cfg)
    assert any("sample_mode" in e for e in errs)


def test_override_negative_cooldown_fails():
    cfg = _valid_cfg()
    cfg["instances"] = {
        "radarr": [{
            "name": "R", "url": "http://radarr", "key": "abc",
            "overrides": {"cooldown_hours": -5},
        }],
        "sonarr": [],
    }
    errs = _errs(cfg)
    assert any("cooldown_hours" in e for e in errs)


def test_override_backlog_enabled_non_bool_fails():
    cfg = _valid_cfg()
    cfg["instances"] = {
        "radarr": [{
            "name": "R", "url": "http://radarr", "key": "abc",
            "overrides": {"backlog_enabled": "yes"},
        }],
        "sonarr": [],
    }
    errs = _errs(cfg)
    assert any("backlog_enabled" in e for e in errs)


def test_override_cutoff_enabled_non_bool_fails():
    cfg = _valid_cfg()
    cfg["instances"] = {
        "radarr": [{
            "name": "R", "url": "http://radarr", "key": "abc",
            "overrides": {"cutoff_enabled": "yes"},
        }],
        "sonarr": [],
    }
    errs = _errs(cfg)
    assert any("cutoff_enabled" in e for e in errs)


# ---------------------------------------------------------------------------
# validate_config return type contract
# ---------------------------------------------------------------------------

def test_returns_tuple():
    result = validate_config(dict(DEFAULT_CONFIG))
    assert isinstance(result, tuple)
    assert len(result) == 2


def test_ok_false_when_errors():
    ok, errs = validate_config(_valid_cfg(batch_size=0))
    assert ok is False
    assert len(errs) >= 1

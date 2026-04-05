"""
tests/test_queue_depth.py

Unit tests for nudgarr.sweep._check_queue_depth().
HTTP calls are mocked via unittest.mock.patch on the req() function
used by radarr_get_queue_total and sonarr_get_queue_total.
Zero changes to nudgarr code required.
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from nudgarr.sweep import _check_queue_depth


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cfg(enabled=True, threshold=10, radarr_instances=None, sonarr_instances=None):
    return {
        "queue_depth_enabled": enabled,
        "queue_depth_threshold": threshold,
        "instances": {
            "radarr": radarr_instances if radarr_instances is not None else [
                {"name": "Radarr", "url": "http://radarr:7878", "key": "abc", "enabled": True},
            ],
            "sonarr": sonarr_instances if sonarr_instances is not None else [],
        },
    }


def _session():
    return MagicMock(spec=requests.Session)


def _mock_queue_status(total_count):
    """Return a mock for nudgarr.arr_clients.req that returns a queue/status response."""
    return MagicMock(return_value={"totalCount": total_count})


# ---------------------------------------------------------------------------
# Feature disabled
# ---------------------------------------------------------------------------

def test_disabled_returns_false():
    """When queue_depth_enabled=False, check skips entirely and returns False."""
    with patch("nudgarr.arr_clients.req") as mock_req:
        result = _check_queue_depth(_cfg(enabled=False), _session())
    assert result is False
    mock_req.assert_not_called()


def test_threshold_zero_returns_false():
    """threshold < 1 disables the check even if enabled=True."""
    with patch("nudgarr.arr_clients.req") as mock_req:
        result = _check_queue_depth(_cfg(enabled=True, threshold=0), _session())
    assert result is False
    mock_req.assert_not_called()


# ---------------------------------------------------------------------------
# Threshold boundary conditions
# ---------------------------------------------------------------------------

def test_total_below_threshold_proceeds():
    """total < threshold returns False (sweep proceeds)."""
    with patch("nudgarr.arr_clients.req", _mock_queue_status(4)):
        result = _check_queue_depth(_cfg(threshold=5), _session())
    assert result is False


def test_total_at_exactly_threshold_skips():
    """total == threshold returns True (sweep skipped)."""
    with patch("nudgarr.arr_clients.req", _mock_queue_status(5)):
        result = _check_queue_depth(_cfg(threshold=5), _session())
    assert result is True


def test_total_above_threshold_skips():
    """total > threshold returns True (sweep skipped)."""
    with patch("nudgarr.arr_clients.req", _mock_queue_status(99)):
        result = _check_queue_depth(_cfg(threshold=5), _session())
    assert result is True


def test_threshold_one_with_empty_queue_proceeds():
    """threshold=1, total=0 — sweep proceeds."""
    with patch("nudgarr.arr_clients.req", _mock_queue_status(0)):
        result = _check_queue_depth(_cfg(threshold=1), _session())
    assert result is False


def test_threshold_one_with_one_item_skips():
    """threshold=1, total=1 — sweep skipped."""
    with patch("nudgarr.arr_clients.req", _mock_queue_status(1)):
        result = _check_queue_depth(_cfg(threshold=1), _session())
    assert result is True


# ---------------------------------------------------------------------------
# Fail-open behaviour
# ---------------------------------------------------------------------------

def test_exception_fails_open():
    """Exception from queue endpoint contributes 0 — sweep proceeds."""
    with patch("nudgarr.arr_clients.req", side_effect=Exception("connection refused")):
        result = _check_queue_depth(_cfg(threshold=1), _session())
    assert result is False


def test_missing_total_count_field_fails_open():
    """Response without totalCount — contributes 0, sweep proceeds."""
    with patch("nudgarr.arr_clients.req", MagicMock(return_value={})):
        result = _check_queue_depth(_cfg(threshold=1), _session())
    assert result is False


def test_non_dict_response_fails_open():
    """Non-dict response (e.g. None) — contributes 0, sweep proceeds."""
    with patch("nudgarr.arr_clients.req", MagicMock(return_value=None)):
        result = _check_queue_depth(_cfg(threshold=1), _session())
    assert result is False


# ---------------------------------------------------------------------------
# Multi-instance summing
# ---------------------------------------------------------------------------

def test_sums_across_radarr_and_sonarr():
    """Totals from Radarr and Sonarr are summed — 4 + 4 = 8 >= threshold 5."""
    cfg = _cfg(
        threshold=5,
        radarr_instances=[
            {"name": "Radarr", "url": "http://radarr:7878", "key": "abc", "enabled": True},
        ],
        sonarr_instances=[
            {"name": "Sonarr", "url": "http://sonarr:8989", "key": "xyz", "enabled": True},
        ],
    )
    with patch("nudgarr.arr_clients.req", _mock_queue_status(4)):
        result = _check_queue_depth(cfg, _session())
    assert result is True


def test_disabled_instance_not_checked():
    """Disabled instances are skipped — their queue count is not fetched."""
    cfg = _cfg(
        threshold=1,
        radarr_instances=[
            {"name": "Radarr", "url": "http://radarr:7878", "key": "abc", "enabled": False},
        ],
        sonarr_instances=[],
    )
    with patch("nudgarr.arr_clients.req") as mock_req:
        result = _check_queue_depth(cfg, _session())
    assert result is False
    mock_req.assert_not_called()


def test_no_instances_returns_false():
    """No instances configured — total is 0, sweep proceeds."""
    cfg = _cfg(threshold=1, radarr_instances=[], sonarr_instances=[])
    result = _check_queue_depth(cfg, _session())
    assert result is False

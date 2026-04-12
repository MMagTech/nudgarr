"""Tests for maintenance window helpers and next sweep UTC calculation."""

from nudgarr.constants import DEFAULT_CONFIG
from nudgarr.config import deep_copy
from nudgarr.scheduler import (
    _local_datetime_in_maintenance_window,
    _next_cron_utc,
    _next_sweep_run_utc,
    next_run_in_maintenance_window,
)


def _cfg(**kwargs):
    c = deep_copy(DEFAULT_CONFIG)
    c.update(kwargs)
    return c


def test_next_sweep_run_utc_none_when_scheduler_disabled():
    cfg = _cfg(scheduler_enabled=False, cron_expression="0 * * * *")
    assert _next_sweep_run_utc(cfg) is None


def test_next_sweep_run_utc_matches_next_cron_when_maintenance_inactive():
    """With maintenance off (or empty days), next run equals raw next cron fire."""
    cfg = _cfg(
        scheduler_enabled=True,
        cron_expression="15 * * * *",
        maintenance_window_enabled=False,
    )
    a = _next_sweep_run_utc(cfg)
    b = _next_cron_utc("15 * * * *")
    assert a == b


def test_local_datetime_in_maintenance_respects_disabled_toggle():
    import datetime as dt
    from zoneinfo import ZoneInfo

    cfg = _cfg(maintenance_window_enabled=False)
    t = dt.datetime(2026, 6, 15, 14, 30, tzinfo=ZoneInfo("UTC"))
    assert _local_datetime_in_maintenance_window(cfg, t) is False


def test_local_datetime_in_maintenance_same_day_window():
    import datetime as dt
    from zoneinfo import ZoneInfo

    cfg = _cfg(
        maintenance_window_enabled=True,
        maintenance_window_days=[0, 1, 2, 3, 4, 5, 6],
        maintenance_window_start="10:00",
        maintenance_window_end="12:00",
    )
    # Monday 2026-06-15 11:00 UTC — inside 10-12 if TZ=UTC
    t = dt.datetime(2026, 6, 15, 11, 0, tzinfo=ZoneInfo("UTC"))
    assert _local_datetime_in_maintenance_window(cfg, t) is True
    t2 = dt.datetime(2026, 6, 15, 9, 30, tzinfo=ZoneInfo("UTC"))
    assert _local_datetime_in_maintenance_window(cfg, t2) is False


def test_next_run_in_maintenance_window_false_when_next_is_outside_window(monkeypatch):
    """Displayed next run skips maintenance; it must not flag as inside the window."""
    monkeypatch.setenv("TZ", "UTC")
    cfg = _cfg(
        scheduler_enabled=True,
        cron_expression="15 * * * *",
        maintenance_window_enabled=True,
        maintenance_window_days=[0, 1, 2, 3, 4, 5, 6],
        maintenance_window_start="10:00",
        maintenance_window_end="12:00",
    )
    n = _next_sweep_run_utc(cfg)
    assert n is not None
    assert next_run_in_maintenance_window(cfg, n) is False


def test_next_run_in_maintenance_window_true_when_iso_falls_in_window(monkeypatch):
    monkeypatch.setenv("TZ", "UTC")
    cfg = _cfg(
        maintenance_window_enabled=True,
        maintenance_window_days=[0, 1, 2, 3, 4, 5, 6],
        maintenance_window_start="10:00",
        maintenance_window_end="12:00",
    )
    assert next_run_in_maintenance_window(cfg, "2026-06-15T11:00:00Z") is True

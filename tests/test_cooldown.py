"""
tests/test_cooldown.py

Unit tests for cooldown logic in nudgarr.db.history.
Uses a real temp SQLite database — no mocking required.
DB_FILE env var is patched to an in-memory path before any imports touch
the connection so tests are fully isolated from any live database.
"""

import os
import tempfile
import pytest

# ---------------------------------------------------------------------------
# DB isolation — must happen before nudgarr.db imports
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Point DB_FILE at a fresh temp file for each test."""
    db_path = str(tmp_path / "test_nudgarr.db")
    monkeypatch.setenv("DB_FILE", db_path)
    # Force reconnection to the new path
    import nudgarr.db.connection as conn_mod
    conn_mod._local.__dict__.clear()
    conn_mod.DB_FILE = db_path
    conn_mod.init_db()
    yield
    # Clean up thread-local connection
    conn_mod.close_connection()


from nudgarr.db.history import get_last_searched_ts_bulk, batch_upsert_search_history
from nudgarr.utils import iso_z, utcnow
from datetime import timedelta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_ts():
    return iso_z(utcnow())


def _ts_hours_ago(hours):
    return iso_z(utcnow() - timedelta(hours=hours))


def _upsert(app, instance_url, item_type, item_id, now_ts=None, instance_name="TestInst"):
    """Write a single search history row."""
    batch_upsert_search_history([{
        "app": app,
        "instance_name": instance_name,
        "instance_url": instance_url,
        "item_type": item_type,
        "item_id": item_id,
        "series_id": "",
        "title": f"Title {item_id}",
        "sweep_type": "cutoff",
        "library_added": "",
        "now_ts": now_ts or _now_ts(),
    }])


def _is_on_cooldown(app, instance_url, item_type, item_id, cooldown_hours):
    """Check cooldown by fetching the last searched ts and comparing."""
    ts_map = get_last_searched_ts_bulk(app, instance_url, item_type, [item_id])
    if item_id not in ts_map:
        return False
    if cooldown_hours <= 0:
        return False
    from nudgarr.utils import parse_iso
    last = parse_iso(ts_map[item_id])
    if last is None:
        return False
    cutoff = utcnow() - timedelta(hours=cooldown_hours)
    return last > cutoff


# ---------------------------------------------------------------------------
# Basic cooldown checks
# ---------------------------------------------------------------------------

def test_unsearched_item_not_on_cooldown():
    """An item with no search history is not on cooldown."""
    result = _is_on_cooldown("radarr", "http://r:7878", "movie", "101", cooldown_hours=48)
    assert result is False


def test_recently_searched_item_on_cooldown():
    """An item searched just now is on cooldown."""
    _upsert("radarr", "http://r:7878", "movie", "101")
    result = _is_on_cooldown("radarr", "http://r:7878", "movie", "101", cooldown_hours=48)
    assert result is True


def test_item_searched_past_cooldown_not_on_cooldown():
    """An item searched 50 hours ago is not on cooldown with a 48h window."""
    _upsert("radarr", "http://r:7878", "movie", "101", now_ts=_ts_hours_ago(50))
    result = _is_on_cooldown("radarr", "http://r:7878", "movie", "101", cooldown_hours=48)
    assert result is False


def test_item_searched_inside_cooldown_on_cooldown():
    """An item searched 24 hours ago is still on cooldown with a 48h window."""
    _upsert("radarr", "http://r:7878", "movie", "101", now_ts=_ts_hours_ago(24))
    result = _is_on_cooldown("radarr", "http://r:7878", "movie", "101", cooldown_hours=48)
    assert result is True


def test_zero_cooldown_disables():
    """cooldown_hours=0 always returns False regardless of search history."""
    _upsert("radarr", "http://r:7878", "movie", "101")
    result = _is_on_cooldown("radarr", "http://r:7878", "movie", "101", cooldown_hours=0)
    assert result is False


# ---------------------------------------------------------------------------
# Per-instance isolation
# ---------------------------------------------------------------------------

def test_cooldown_per_instance_isolated():
    """A cooldown on instance A does not affect instance B."""
    _upsert("radarr", "http://r1:7878", "movie", "101")
    result = _is_on_cooldown("radarr", "http://r2:7878", "movie", "101", cooldown_hours=48)
    assert result is False


def test_different_apps_isolated():
    """A Radarr history entry does not affect Sonarr lookup."""
    _upsert("radarr", "http://r:7878", "movie", "101")
    result = _is_on_cooldown("sonarr", "http://r:7878", "movie", "101", cooldown_hours=48)
    assert result is False


# ---------------------------------------------------------------------------
# Upsert behaviour
# ---------------------------------------------------------------------------

def test_upsert_updates_existing_row():
    """Searching an item twice produces one row with updated timestamp."""
    from nudgarr.db.connection import get_connection
    _upsert("radarr", "http://r:7878", "movie", "101", now_ts=_ts_hours_ago(50))
    _upsert("radarr", "http://r:7878", "movie", "101", now_ts=_now_ts())
    conn = get_connection()
    rows = conn.execute(
        "SELECT COUNT(*) FROM search_history WHERE app='radarr' AND item_id='101'"
    ).fetchone()
    assert rows[0] == 1


def test_upsert_increments_search_count():
    """search_count increments on each upsert."""
    from nudgarr.db.connection import get_connection
    _upsert("radarr", "http://r:7878", "movie", "101")
    _upsert("radarr", "http://r:7878", "movie", "101")
    conn = get_connection()
    row = conn.execute(
        "SELECT search_count FROM search_history WHERE app='radarr' AND item_id='101'"
    ).fetchone()
    assert row["search_count"] == 2


# ---------------------------------------------------------------------------
# Bulk fetch
# ---------------------------------------------------------------------------

def test_bulk_fetch_returns_only_requested_ids():
    """get_last_searched_ts_bulk returns only the requested item IDs."""
    _upsert("radarr", "http://r:7878", "movie", "101")
    _upsert("radarr", "http://r:7878", "movie", "102")
    result = get_last_searched_ts_bulk("radarr", "http://r:7878", "movie", ["101"])
    assert "101" in result
    assert "102" not in result


def test_bulk_fetch_empty_ids_returns_empty():
    """Passing empty list returns empty dict without querying."""
    result = get_last_searched_ts_bulk("radarr", "http://r:7878", "movie", [])
    assert result == {}


def test_bulk_fetch_missing_item_not_in_result():
    """An item not in the DB is simply absent from the result dict."""
    result = get_last_searched_ts_bulk("radarr", "http://r:7878", "movie", ["999"])
    assert "999" not in result

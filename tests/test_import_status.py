"""
tests/test_import_status.py

Tests for the "Imported" status in the Library History feed (issue #13).

Confirmed-imported items must be shown with a distinct "Imported" status in
get_search_history() rather than the cooldown-derived "Next Sweep", which made
resolved items indistinguishable from genuinely pending ones.

Covers:
  - Radarr Backlog import (clean movie-id join)
  - Sonarr Backlog episode import (episode row -> series-level stat_entry join)
  - Cutoff upgrade import
  - Unconfirmed item past cooldown still shows "Next Sweep" (regression guard)
  - Sonarr sibling episode still pending is NOT marked imported (series-level
    guard using imported_ts vs last_searched_ts)

Uses a real temp SQLite database — no mocking. DB_FILE is patched before any
nudgarr.db import touches the connection so tests are isolated.
"""

import pytest
from datetime import timedelta


# ---------------------------------------------------------------------------
# DB isolation — must happen before nudgarr.db imports
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Point DB_FILE at a fresh temp file for each test."""
    db_path = str(tmp_path / "test_nudgarr.db")
    monkeypatch.setenv("DB_FILE", db_path)
    import nudgarr.db.connection as conn_mod
    conn_mod._local.__dict__.clear()
    conn_mod.DB_FILE = db_path
    conn_mod.init_db()
    yield
    conn_mod.close_connection()


from nudgarr.db.history import get_search_history, batch_upsert_search_history
from nudgarr.utils import iso_z, utcnow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts_hours_ago(hours):
    return iso_z(utcnow() - timedelta(hours=hours))


def _now_ts():
    return iso_z(utcnow())


def _add_history(app, instance_url, item_type, item_id, series_id="",
                 sweep_type="Backlog", last_ts=None, instance_name="TestInst"):
    batch_upsert_search_history([{
        "app": app,
        "instance_name": instance_name,
        "instance_url": instance_url,
        "item_type": item_type,
        "item_id": item_id,
        "series_id": series_id,
        "title": f"Title {item_id}",
        "sweep_type": sweep_type,
        "library_added": "",
        "now_ts": last_ts or _now_ts(),
    }])


def _add_imported_stat(app, instance_url, item_id, imported_ts,
                       entry_type="Acquired", iteration=1, instance="TestInst"):
    """Insert a confirmed (imported=1) stat_entries row directly."""
    from nudgarr.db.connection import get_connection
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO stat_entries
            (app, instance, instance_url, item_id, title, type, iteration,
             first_searched_ts, last_searched_ts, imported, imported_ts, quality_from)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        """,
        (app, instance, instance_url, item_id, f"Title {item_id}", entry_type,
         iteration, imported_ts, imported_ts, imported_ts, ""),
    )
    conn.commit()


def _fetch_row(item_id, app_filter=""):
    """Return the single history item for item_id, or None."""
    _total, items = get_search_history(
        app_filter=app_filter, limit=250, cooldown_hours=48,
    )
    for it in items:
        if it["item_id"] == str(item_id):
            return it
    return None


# ---------------------------------------------------------------------------
# Case 1 — Radarr Backlog import (movie-id join)
# ---------------------------------------------------------------------------

def test_radarr_backlog_imported_shows_imported():
    url = "http://radarr:7878"
    _add_history("radarr", url, "missing_movie", "101",
                 sweep_type="Backlog", last_ts=_ts_hours_ago(10))
    _add_imported_stat("radarr", url, "101", imported_ts=_ts_hours_ago(5))

    row = _fetch_row("101", app_filter="radarr")
    assert row is not None
    assert row["imported"] is True
    assert row["eligible_again"] == "Imported"


# ---------------------------------------------------------------------------
# Case 2 — Sonarr Backlog episode import (episode row -> series stat_entry)
# ---------------------------------------------------------------------------

def test_sonarr_backlog_episode_imported_shows_imported():
    url = "http://sonarr:8989"
    # search_history keyed by episode id (5001) with its series id (900).
    _add_history("sonarr", url, "missing_episode", "5001", series_id="900",
                 sweep_type="Backlog", last_ts=_ts_hours_ago(10))
    # stat_entries keyed by SERIES id (900), as batch_record_stat_entries does.
    _add_imported_stat("sonarr", url, "900", imported_ts=_ts_hours_ago(5))

    row = _fetch_row("5001", app_filter="sonarr")
    assert row is not None
    assert row["imported"] is True, "Sonarr episode must join to series-level import"
    assert row["eligible_again"] == "Imported"


# ---------------------------------------------------------------------------
# Case 3 — Unconfirmed item past cooldown still shows "Next Sweep"
# ---------------------------------------------------------------------------

def test_unconfirmed_past_cooldown_shows_next_sweep():
    # last searched 50h ago with a 48h cooldown -> eligible_again is ~2h in the
    # past. The backend returns that ISO timestamp; the frontend renders any
    # past timestamp as "Next Sweep". The key regression guard here is that an
    # unconfirmed item is never flagged imported.
    from nudgarr.utils import parse_iso
    url = "http://radarr:7878"
    _add_history("radarr", url, "missing_movie", "202",
                 sweep_type="Backlog", last_ts=_ts_hours_ago(50))
    # No stat_entries row at all.

    _total, items = get_search_history(app_filter="radarr", limit=250, cooldown_hours=48)
    row = next(it for it in items if it["item_id"] == "202")
    assert row["imported"] is False
    assert row["eligible_again"] != "Imported"
    # Eligible-again timestamp is in the past -> the UI would show "Next Sweep".
    eligible_dt = parse_iso(row["eligible_again"])
    assert eligible_dt is not None
    assert eligible_dt <= utcnow()


# ---------------------------------------------------------------------------
# Case 4 — Cutoff upgrade import shows "Imported"
# ---------------------------------------------------------------------------

def test_cutoff_upgrade_imported_shows_imported():
    url = "http://radarr:7878"
    _add_history("radarr", url, "movie", "303",
                 sweep_type="Cutoff", last_ts=_ts_hours_ago(10))
    _add_imported_stat("radarr", url, "303", imported_ts=_ts_hours_ago(5),
                       entry_type="Upgraded", iteration=2)

    row = _fetch_row("303", app_filter="radarr")
    assert row is not None
    assert row["imported"] is True
    assert row["eligible_again"] == "Imported"


# ---------------------------------------------------------------------------
# Case 5 — Sonarr sibling episode still pending is NOT marked imported
# ---------------------------------------------------------------------------

def test_sonarr_sibling_episode_still_pending_not_imported():
    """Series 900 had episode 5001 imported, but episode 5002 is still missing
    and was searched after the import. It must NOT show as imported."""
    url = "http://sonarr:8989"
    # Episode 5001 imported.
    _add_history("sonarr", url, "missing_episode", "5001", series_id="900",
                 sweep_type="Backlog", last_ts=_ts_hours_ago(10))
    # Episode 5002 searched just now (after the import) — still pending.
    _add_history("sonarr", url, "missing_episode", "5002", series_id="900",
                 sweep_type="Backlog", last_ts=_now_ts())
    # Series-level import recorded 5 hours ago.
    _add_imported_stat("sonarr", url, "900", imported_ts=_ts_hours_ago(5))

    imported_row = _fetch_row("5001", app_filter="sonarr")
    pending_row = _fetch_row("5002", app_filter="sonarr")

    assert imported_row["imported"] is True
    assert pending_row["imported"] is False, (
        "sibling episode searched after the series import must stay pending"
    )
    assert pending_row["eligible_again"] != "Imported"

"""
nudgarr/db/exclusions.py

exclusions table — all read/write operations.

  get_exclusions()              -- return all exclusion rows with source/count/acknowledged
  add_exclusion()               -- insert a manual exclusion (case-insensitive dedup)
  add_auto_exclusion()          -- insert an auto-exclusion with search count
  remove_exclusion()            -- delete by title
  clear_auto_exclusions()       -- delete all rows where source='auto'
  get_unacknowledged_count()    -- count of auto-exclusions not yet seen by the user
  acknowledge_all()             -- mark all auto-exclusion rows as acknowledged
  get_auto_exclusions_older_than() -- auto-exclusion rows older than N days (for unexclude)
"""

from typing import Dict, List

from nudgarr.db.connection import get_connection
import logging

from nudgarr.utils import iso_z, utcnow

logger = logging.getLogger(__name__)


def get_exclusions() -> List[Dict]:
    """Return all exclusion rows ordered by most recently added.

    Each row includes: title, excluded_at, source ('manual' or 'auto'),
    search_count (0 for manual entries), and acknowledged flag.
    """
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT title, excluded_at, source, search_count, acknowledged
        FROM exclusions
        ORDER BY excluded_at DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]


def add_exclusion(title: str) -> None:
    """Add a manual exclusion (case-insensitive dedup via INSERT OR IGNORE).

    Manual exclusions are acknowledged by default since the user added them
    deliberately and does not need a status bar notification.
    Appends an exclusion_events row so Intel can track the full lifecycle.
    """
    conn = get_connection()
    now = iso_z(utcnow())
    conn.execute(
        """
        INSERT OR IGNORE INTO exclusions
            (title, excluded_at, source, search_count, acknowledged)
        VALUES (?, ?, 'manual', 0, 1)
        """,
        (title.strip(), now)
    )
    conn.execute(
        """
        INSERT INTO exclusion_events
            (title, event_type, source, search_count_at_event, event_ts)
        VALUES (?, 'excluded', 'manual', 0, ?)
        """,
        (title.strip(), now)
    )
    conn.commit()


def add_auto_exclusion(title: str, search_count: int) -> None:
    """Insert an auto-exclusion row written by the import check loop.

    Auto-exclusions are unacknowledged (acknowledged=0) so the status bar
    badge fires. If the title is already excluded (e.g. manually added),
    the INSERT OR IGNORE is a no-op — the existing row is preserved.
    Appends an exclusion_events row so Intel can track the full lifecycle.

    title        -- exact title string from the search history record
    search_count -- number of searches that triggered the auto-exclusion
    """
    conn = get_connection()
    now = iso_z(utcnow())
    conn.execute(
        """
        INSERT OR IGNORE INTO exclusions
            (title, excluded_at, source, search_count, acknowledged)
        VALUES (?, ?, 'auto', ?, 0)
        """,
        (title.strip(), now, search_count)
    )
    conn.execute(
        """
        INSERT INTO exclusion_events
            (title, event_type, source, search_count_at_event, event_ts)
        VALUES (?, 'excluded', 'auto', ?, ?)
        """,
        (title.strip(), search_count, now)
    )
    conn.commit()


def remove_exclusion(title: str, source: str = "manual") -> None:
    """Remove a title from the exclusions list (case-insensitive match).

    Reads the current search_count from the exclusions row before deletion
    so it can be snapshotted in exclusion_events. This preserves the
    pre-deletion count for Intel calibration even after the row is gone.

    source -- 'manual' when the user deletes via the UI (default),
              'auto' when the sweep timer triggers auto-unexclude.
    """
    conn = get_connection()
    title_clean = title.strip()
    now = iso_z(utcnow())
    existing = conn.execute(
        "SELECT search_count FROM exclusions WHERE title = ? COLLATE NOCASE",
        (title_clean,)
    ).fetchone()
    search_count_at_event = existing["search_count"] if existing else 0
    conn.execute(
        "DELETE FROM exclusions WHERE title = ? COLLATE NOCASE",
        (title_clean,)
    )
    conn.execute(
        """
        INSERT INTO exclusion_events
            (title, event_type, source, search_count_at_event, event_ts)
        VALUES (?, 'unexcluded', ?, ?, ?)
        """,
        (title_clean, source, search_count_at_event, now)
    )
    conn.commit()


def clear_auto_exclusions() -> int:
    """Delete all rows where source='auto'. Returns the number of rows removed.

    Manual exclusions are never touched by this operation. Used by the
    Danger Zone reset button and the auto-exclusion disabled popup (Clear).
    Appends an unexcluded event row for each auto-exclusion removed so Intel
    calibration data is preserved across bulk clears.
    """
    conn = get_connection()
    now = iso_z(utcnow())
    rows = conn.execute(
        "SELECT title, search_count FROM exclusions WHERE source = 'auto'"
    ).fetchall()
    for r in rows:
        conn.execute(
            """
            INSERT INTO exclusion_events
                (title, event_type, source, search_count_at_event, event_ts)
            VALUES (?, 'unexcluded', 'auto', ?, ?)
            """,
            (r["title"], r["search_count"], now)
        )
    cursor = conn.execute("DELETE FROM exclusions WHERE source = 'auto'")
    conn.commit()
    return cursor.rowcount


def clear_manual_exclusions() -> int:
    """Delete all rows where source='manual'. Returns the number of rows removed.

    Auto-exclusions are never touched by this operation. Used by the Clear
    Exclusions action in the History tab when the user selects Manual only.
    """
    conn = get_connection()
    cursor = conn.execute("DELETE FROM exclusions WHERE source = 'manual'")
    conn.commit()
    return cursor.rowcount


def clear_all_exclusions() -> int:
    """Delete all rows from the exclusions table. Returns the number of rows removed.

    Logs unexcluded events for all auto-exclusions removed so Intel calibration
    data is preserved. Used by the Clear Exclusions action in the History tab
    when the user selects All.
    """
    conn = get_connection()
    now = iso_z(utcnow())
    rows = conn.execute(
        "SELECT title, search_count FROM exclusions WHERE source = 'auto'"
    ).fetchall()
    for r in rows:
        conn.execute(
            """
            INSERT INTO exclusion_events
                (title, event_type, source, search_count_at_event, event_ts)
            VALUES (?, 'unexcluded', 'auto', ?, ?)
            """,
            (r["title"], r["search_count"], now)
        )
    cursor = conn.execute("DELETE FROM exclusions")
    conn.commit()
    return cursor.rowcount


def get_unacknowledged_count() -> int:
    """Return the count of auto-exclusions not yet seen by the user.

    Drives the status bar badge. Returns 0 when no unacknowledged rows exist,
    which hides the badge entirely.
    """
    return get_connection().execute(
        "SELECT COUNT(*) FROM exclusions WHERE source = 'auto' AND acknowledged = 0"
    ).fetchone()[0]


def acknowledge_all() -> None:
    """Mark all auto-exclusion rows as acknowledged.

    Called when the user clicks the status bar badge, clearing it. Only
    affects auto-exclusion rows — manual exclusions have no acknowledged state.
    """
    conn = get_connection()
    conn.execute(
        "UPDATE exclusions SET acknowledged = 1 WHERE source = 'auto'"
    )
    conn.commit()


def get_auto_exclusions_older_than(days: int) -> List[Dict]:
    """Return auto-exclusion rows whose excluded_at is older than N days.

    Used by the auto-unexclude pass at the start of each sweep. Only rows
    with source='auto' are returned — manual exclusions are never auto-unexcluded.

    days -- threshold in days; rows older than this are returned
    """
    from datetime import timedelta
    cutoff = iso_z(utcnow() - timedelta(days=days))
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT title, excluded_at, search_count
        FROM exclusions
        WHERE source = 'auto' AND excluded_at < ?
        """,
        (cutoff,)
    ).fetchall()
    return [dict(r) for r in rows]

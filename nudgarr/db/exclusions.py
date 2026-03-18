"""
nudgarr/db/exclusions.py

exclusions table — all read/write operations.

  get_exclusions()  -- return all exclusion rows
  add_exclusion()   -- insert a title (case-insensitive dedup)
  remove_exclusion() -- delete by title
"""

from typing import Dict, List

from nudgarr.db.connection import get_connection
import logging

from nudgarr.utils import iso_z, utcnow

logger = logging.getLogger(__name__)


def get_exclusions() -> List[Dict]:
    """Return all exclusion rows ordered by most recently added."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT title, excluded_at FROM exclusions ORDER BY excluded_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def add_exclusion(title: str) -> None:
    """Add a title to the exclusions list (case-insensitive dedup via INSERT OR IGNORE)."""
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO exclusions (title, excluded_at) VALUES (?, ?)",
        (title.strip(), iso_z(utcnow()))
    )
    conn.commit()


def remove_exclusion(title: str) -> None:
    """Remove a title from the exclusions list (case-insensitive match)."""
    conn = get_connection()
    conn.execute(
        "DELETE FROM exclusions WHERE title = ? COLLATE NOCASE",
        (title.strip(),)
    )
    conn.commit()

"""
nudgarr/db/lifetime.py

sweep_lifetime and lifetime_totals tables.

  upsert_sweep_lifetime()  -- insert or update counters for one instance
  get_sweep_lifetime()     -- return all rows as a dict keyed by instance_key
  get_sweep_lifetime_row() -- return one row by instance_key
  increment_lifetime_total() -- add delta to movies or shows counter
  get_lifetime_totals()    -- return {movies: N, shows: N}
"""

from typing import Any, Dict, Optional

import logging

from nudgarr.db.connection import get_connection

logger = logging.getLogger(__name__)


def upsert_sweep_lifetime(
    instance_key: str,
    runs_delta: int = 0,
    eligible_delta: int = 0,
    skipped_delta: int = 0,
    searched_delta: int = 0,
    last_run_utc: Optional[str] = None,
) -> None:
    """Insert or update lifetime sweep counters for one instance.
    All delta parameters are additive — they are added to the existing values,
    not used as absolute replacements. last_run_utc overwrites the stored value."""
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO sweep_lifetime (instance_key, runs, eligible, skipped, searched, last_run_utc)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (instance_key) DO UPDATE SET
            runs         = sweep_lifetime.runs + excluded.runs,
            eligible     = sweep_lifetime.eligible + excluded.eligible,
            skipped      = sweep_lifetime.skipped + excluded.skipped,
            searched     = sweep_lifetime.searched + excluded.searched,
            last_run_utc = excluded.last_run_utc
        """,
        (instance_key, runs_delta, eligible_delta, skipped_delta, searched_delta, last_run_utc)
    )
    conn.commit()


def get_sweep_lifetime() -> Dict[str, Any]:
    """Return all sweep_lifetime rows as {instance_key: row_dict}."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM sweep_lifetime").fetchall()
    return {r["instance_key"]: dict(r) for r in rows}


def get_sweep_lifetime_row(instance_key: str) -> Optional[Dict]:
    """Return the sweep_lifetime row for one instance, or None if not found."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM sweep_lifetime WHERE instance_key = ?", (instance_key,)
    ).fetchone()
    return dict(row) if row else None


def increment_lifetime_total(key: str, delta: int = 1) -> None:
    """Add delta to the lifetime_totals counter for key ('movies' or 'shows')."""
    conn = get_connection()
    conn.execute(
        "UPDATE lifetime_totals SET value = value + ? WHERE key = ?",
        (delta, key)
    )
    conn.commit()


def get_lifetime_totals() -> Dict[str, int]:
    """Return {movies: N, shows: N} lifetime import counters. Never returns None."""
    conn = get_connection()
    rows = conn.execute("SELECT key, value FROM lifetime_totals").fetchall()
    result = {"movies": 0, "shows": 0}
    for r in rows:
        result[r["key"]] = r["value"]
    return result

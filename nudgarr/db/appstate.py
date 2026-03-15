"""
nudgarr/db/appstate.py

nudgarr_state table — key/value persistence for application state.

  get_state() -- retrieve a value by key
  set_state() -- persist a value by key

Named appstate to avoid confusion with nudgarr/state.py.
"""

from typing import Optional

from nudgarr.db.connection import get_connection


def get_state(key: str) -> Optional[str]:
    """Retrieve a persisted state value by key."""
    conn = get_connection()
    row = conn.execute(
        "SELECT value FROM nudgarr_state WHERE key = ?", (key,)
    ).fetchone()
    return row["value"] if row else None


def set_state(key: str, value: str) -> None:
    """Persist a state value by key."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO nudgarr_state (key, value) VALUES (?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value)
    )
    conn.commit()

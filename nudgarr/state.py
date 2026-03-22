"""
nudgarr/state.py

Thin compatibility facade over db.py.

All persistence that previously lived in the three JSON runtime files
now lives in the SQLite database via nudgarr/db.py.  This module keeps
the public function signatures that the rest of the package uses.

  State      : state_key
  Exclusions : load_exclusions
  Pruning    : prune_state_by_retention

Imports from within the package: db only.
"""

from typing import Any, Dict, List

import logging

from nudgarr import db

logger = logging.getLogger(__name__)

# ── Key helper (used by routes and sweep) ─────────────────────────────


def state_key(name: str, url: str) -> str:
    """Return the composite lookup key used throughout the package: 'name|url'.
    Trailing slashes are stripped from url for consistent matching."""
    return f"{name}|{url.rstrip('/')}"

# ── Exclusions ────────────────────────────────────────────────────────


def load_exclusions() -> List[Dict[str, Any]]:
    """Return all exclusion rows from the database as a list of dicts."""
    return db.get_exclusions()

# ── Pruning ───────────────────────────────────────────────────────────


def prune_state_by_retention(retention_days: int) -> int:
    """Prune search_history and unimported stat_entries. Returns rows removed."""
    removed = db.prune_search_history(retention_days)
    removed += db.prune_stat_entries(retention_days)
    return removed

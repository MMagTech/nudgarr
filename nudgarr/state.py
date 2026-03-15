"""
nudgarr/state.py

Thin compatibility facade over db.py.

All persistence that previously lived in the three JSON runtime files
now lives in the SQLite database via nudgarr/db.py.  This module keeps
the same public function signatures that the rest of the package uses
so that call sites need minimal changes.

  State      : state_key, load_state*, ensure_state_structure*, save_state*
  Stats      : load_stats*, save_stats*
  Exclusions : load_exclusions, save_exclusions*
  Pruning    : prune_state_by_retention

Functions marked * are stubs or no-ops retained for call-site
compatibility.  The real work happens inside db.py.

Imports from within the package: db, constants, utils only.
"""

from typing import Any, Dict, List

from nudgarr import db



# ── Key helper (still used by routes and sweep) ───────────────────────

def state_key(name: str, url: str) -> str:
    return f"{name}|{url.rstrip('/')}"


# ── State stubs ───────────────────────────────────────────────────────
# Routes and scheduler still call load_state / save_state / ensure_state_structure.
# They now return/accept a minimal dict with only the keys that still matter
# (last_run_utc).  sweep_lifetime is served directly from the DB.

def load_state() -> Dict[str, Any]:
    """Return a minimal state dict for call-site compatibility."""
    return {}


def ensure_state_structure(state: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    """No-op: structure is maintained by the DB schema."""
    return state


def save_state(state: Dict[str, Any], cfg: Dict[str, Any]) -> None:
    """No-op: state is persisted immediately in db.py."""
    pass


# ── Stats stubs ───────────────────────────────────────────────────────
# sweep.py imports load_stats / save_stats from state for the pruning
# block.  Those calls are being removed in the sweep.py rewrite, but
# keeping stubs here prevents import errors during the transition.

def load_stats() -> Dict[str, Any]:
    totals = db.get_lifetime_totals()
    return {
        "entries": [],
        "lifetime_movies": totals.get("movies", 0),
        "lifetime_shows": totals.get("shows", 0),
    }


def save_stats(stats: Dict[str, Any]) -> None:
    """No-op: stats are persisted immediately in db.py."""
    pass


# ── Exclusions ────────────────────────────────────────────────────────

def load_exclusions() -> List[Dict[str, Any]]:
    return db.get_exclusions()


def save_exclusions(exclusions: List[Dict[str, Any]]) -> None:
    """
    Legacy bulk-save.  Used only by routes that have not yet been
    migrated to call db.add_exclusion / db.remove_exclusion directly.
    Syncs the DB to match the supplied list.
    """
    existing = {e["title"].lower() for e in db.get_exclusions()}
    new_titles = {(e.get("title") or "").strip().lower() for e in exclusions if e.get("title")}
    for e in exclusions:
        title = (e.get("title") or "").strip()
        if title and title.lower() not in existing:
            db.add_exclusion(title)
    for title_lower in existing - new_titles:
        db.remove_exclusion(title_lower)


# ── Pruning ───────────────────────────────────────────────────────────

def prune_state_by_retention(state: Dict[str, Any], retention_days: int) -> int:
    """Prune search_history and unimported stat_entries. Returns rows removed."""
    removed = db.prune_search_history(retention_days)
    removed += db.prune_stat_entries(retention_days)
    return removed

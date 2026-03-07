"""
nudgarr/state.py

All persistence for the three runtime data files.

  State      : state_key, load_state, ensure_state_structure, save_state
  Stats      : load_stats, save_stats
  Exclusions : load_exclusions, save_exclusions
  Pruning    : prune_state_by_retention

State tracks what has been searched and when (nudgarr-state.json).
Stats tracks confirmed imports (nudgarr-stats.json).
Exclusions tracks titles excluded from future searches (nudgarr-exclusions.json).

Imports from within the package: constants, utils only.
"""

from datetime import timedelta
from typing import Any, Dict, List

from nudgarr.constants import EXCLUSIONS_FILE, STATE_FILE, STATS_FILE
from nudgarr.utils import load_json, parse_iso, save_json_atomic, utcnow


# ── State ─────────────────────────────────────────────────────────────

def state_key(name: str, url: str) -> str:
    return f"{name}|{url.rstrip('/')}"


def load_state() -> Dict[str, Any]:
    st = load_json(STATE_FILE, {})
    return st if isinstance(st, dict) else {}


def ensure_state_structure(state: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    state.setdefault("radarr", {})
    state.setdefault("sonarr", {})
    for inst in cfg.get("instances", {}).get("radarr", []):
        ik = state_key(inst["name"], inst["url"])
        state["radarr"].setdefault(ik, {})
    for inst in cfg.get("instances", {}).get("sonarr", []):
        ik = state_key(inst["name"], inst["url"])
        state["sonarr"].setdefault(ik, {})
    return state


def save_state(state: Dict[str, Any], cfg: Dict[str, Any]) -> None:
    save_json_atomic(STATE_FILE, state, pretty=True)


# ── Stats ─────────────────────────────────────────────────────────────

def load_stats() -> Dict[str, Any]:
    st = load_json(STATS_FILE, {"entries": [], "lifetime_movies": 0, "lifetime_shows": 0})
    if not isinstance(st, dict):
        return {"entries": [], "lifetime_movies": 0, "lifetime_shows": 0}
    # Seed lifetime totals from existing confirmed entries if not yet set or uninitialized
    confirmed = [e for e in st.get("entries", []) if e.get("imported")]
    if st.get("lifetime_movies", 0) == 0 and st.get("lifetime_shows", 0) == 0 and confirmed:
        st["lifetime_movies"] = sum(1 for e in confirmed if e.get("app") == "radarr")
        st["lifetime_shows"] = sum(1 for e in confirmed if e.get("app") == "sonarr")
        save_json_atomic(STATS_FILE, st, pretty=True)
    st.setdefault("lifetime_movies", 0)
    st.setdefault("lifetime_shows", 0)
    return st


def save_stats(stats: Dict[str, Any]) -> None:
    save_json_atomic(STATS_FILE, stats, pretty=True)


# ── Exclusions ────────────────────────────────────────────────────────

def load_exclusions() -> List[Dict[str, Any]]:
    data = load_json(EXCLUSIONS_FILE, [])
    if not isinstance(data, list):
        return []
    return data


def save_exclusions(exclusions: List[Dict[str, Any]]) -> None:
    save_json_atomic(EXCLUSIONS_FILE, exclusions, pretty=True)


# ── Pruning ───────────────────────────────────────────────────────────

def prune_state_by_retention(state: Dict[str, Any], retention_days: int) -> int:
    """Remove entries older than retention_days. Returns number removed."""
    if retention_days <= 0:
        return 0
    cutoff = utcnow() - timedelta(days=retention_days)
    removed = 0
    for app in ("radarr", "sonarr"):
        app_obj = state.get(app, {})
        if not isinstance(app_obj, dict):
            continue
        for inst_key, bucket in list(app_obj.items()):
            if not isinstance(bucket, dict):
                continue
            for item_key, entry in list(bucket.items()):
                # Support both old string format and new dict format
                ts = entry.get("ts") if isinstance(entry, dict) else entry
                dt = parse_iso(ts) if isinstance(ts, str) else None
                if dt is not None and dt < cutoff:
                    bucket.pop(item_key, None)
                    removed += 1
    return removed

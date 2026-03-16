"""
nudgarr/db/backup.py

Serialises all tables to a JSON-serialisable dict for backup/export.

  export_as_json_dict() -- return all tables as a nested dict
"""

from typing import Any, Dict

from nudgarr.db.connection import get_connection
from nudgarr.db.lifetime import get_lifetime_totals, get_sweep_lifetime


def export_as_json_dict() -> Dict[str, Any]:
    """Serialise all database tables to a JSON-serialisable dict.
    Returns {state, stats, exclusions} where state contains search_history
    and sweep_lifetime, stats contains stat_entries and lifetime totals,
    and exclusions contains the full exclusions list."""
    conn = get_connection()

    sh_rows = conn.execute("SELECT * FROM search_history").fetchall()
    state_export: Dict[str, Any] = {"radarr": {}, "sonarr": {}}
    for r in sh_rows:
        app = r["app"]
        sk = f"{r['instance_name']}|{r['instance_url']}"
        state_export.setdefault(app, {}).setdefault(sk, {})
        item_key = f"{r['item_type']}:{r['item_id']}"
        state_export[app][sk][item_key] = {
            "ts": r["last_searched_ts"],
            "title": r["title"],
            "sweep_type": r["sweep_type"],
            "library_added": r["library_added"],
            "search_count": r["search_count"],
            "first_searched_ts": r["first_searched_ts"],
        }
    lifetime = get_sweep_lifetime()
    if lifetime:
        state_export["sweep_lifetime"] = lifetime

    se_rows = conn.execute("SELECT * FROM stat_entries").fetchall()
    totals = get_lifetime_totals()
    entries = []
    for r in se_rows:
        entries.append({
            "app": r["app"],
            "instance": r["instance"],
            "item_id": r["item_id"],
            "title": r["title"],
            "type": r["type"],
            "first_searched_ts": r["first_searched_ts"],
            "searched_ts": r["last_searched_ts"],
            "imported": bool(r["imported"]),
            "imported_ts": r["imported_ts"],
        })
    stats_export = {
        "entries": entries,
        "lifetime_movies": totals.get("movies", 0),
        "lifetime_shows": totals.get("shows", 0),
    }

    excl_rows = conn.execute(
        "SELECT title, excluded_at FROM exclusions ORDER BY excluded_at DESC"
    ).fetchall()
    exclusions_export = [dict(r) for r in excl_rows]

    return {
        "state": state_export,
        "stats": stats_export,
        "exclusions": exclusions_export,
    }

"""
nudgarr/db/entries.py

stat_entries table — all read/write operations.

  upsert_stat_entry()       -- insert or update the active (unimported) row
  confirm_stat_entry()      -- mark a row as imported
  get_unconfirmed_entries() -- entries eligible for import checking
  get_confirmed_entries()   -- paginated confirmed imports with filters
  rename_instance_in_history() -- update instance name after a rename
  clear_stat_entries()      -- delete all rows
  prune_stat_entries()      -- delete old unimported rows
"""

from datetime import timedelta
from typing import Dict, List, Optional, Tuple

from nudgarr.db.connection import get_connection
from nudgarr.utils import iso_z, parse_iso, utcnow


def upsert_stat_entry(
    app: str,
    instance: str,
    instance_url: str,
    item_id: str,
    title: str,
    entry_type: str,
    searched_ts: str,
) -> None:
    """Insert or update an unimported stat entry for import-checking.
    The ON CONFLICT targets the partial unique index on
    (app, instance, item_id, type) WHERE imported = 0, so each
    active (unimported) item gets one row per type. Confirmed (imported = 1)
    rows are managed separately by confirm_stat_entry()."""
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO stat_entries
            (app, instance, instance_url, item_id, title, type,
             first_searched_ts, last_searched_ts, imported)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
        ON CONFLICT (app, instance, item_id, type) WHERE imported = 0 DO UPDATE SET
            last_searched_ts = excluded.last_searched_ts,
            instance_url = excluded.instance_url,
            title = CASE WHEN excluded.title != '' THEN excluded.title
                         ELSE stat_entries.title END
        """,
        (app, instance, instance_url, item_id, title, entry_type, searched_ts, searched_ts)
    )
    conn.commit()


def confirm_stat_entry(
    app: str,
    instance: str,
    instance_url: str,
    item_id: str,
    entry_type: str,
    imported_ts: str,
) -> bool:
    """Mark a stat entry as imported and increment its iteration counter.
    Uses a two-phase lookup: by instance name first, then by URL as a fallback
    to handle instance renames gracefully. If a confirmed row already exists for
    this item, updates it in place (one row per item). Returns True if a row
    was successfully confirmed, False if no matching unimported row was found."""
    conn = get_connection()

    # Check for an existing imported row for this item (any type).
    # If one exists we update it in place — one row per item, badge reflects
    # the most recent event, iteration increments when the same type repeats.
    # Fall back to URL match if name lookup fails (handles renames).
    existing = conn.execute(
        """
        SELECT id, type, iteration FROM stat_entries
        WHERE app = ? AND instance = ? AND item_id = ? AND imported = 1
        ORDER BY id ASC LIMIT 1
        """,
        (app, instance, item_id)
    ).fetchone()

    if not existing and instance_url:
        existing = conn.execute(
            """
            SELECT id, type, iteration FROM stat_entries
            WHERE app = ? AND instance_url = ? AND item_id = ? AND imported = 1
            ORDER BY id ASC LIMIT 1
            """,
            (app, instance_url, item_id)
        ).fetchone()

    if existing:
        new_iteration = (existing["iteration"] + 1) if existing["type"] == entry_type else 1
        conn.execute(
            """
            UPDATE stat_entries
            SET type = ?, imported_ts = ?, iteration = ?, instance = ?
            WHERE id = ?
            """,
            (entry_type, imported_ts, new_iteration, instance, existing["id"])
        )
        conn.execute(
            """
            DELETE FROM stat_entries
            WHERE app = ? AND item_id = ? AND type = ? AND imported = 0
              AND (instance = ? OR instance_url = ?)
            """,
            (app, item_id, entry_type, instance, instance_url)
        )
        conn.commit()
        return True

    cur = conn.execute(
        """
        UPDATE stat_entries
        SET imported = 1, imported_ts = ?, iteration = 1, instance = ?
        WHERE app = ? AND item_id = ? AND type = ? AND imported = 0
          AND (instance = ? OR instance_url = ?)
        """,
        (imported_ts, instance, app, item_id, entry_type, instance, instance_url)
    )
    conn.commit()
    return cur.rowcount > 0


def get_unconfirmed_entries(check_minutes: int, now_ts: str) -> List[Dict]:
    """Return unimported stat entries that are ready for import checking.
    When check_minutes <= 0, returns all unimported entries with no time filter.
    Otherwise returns only entries whose last_searched_ts is at least
    check_minutes ago, so recently-searched items are not checked prematurely."""
    conn = get_connection()
    if check_minutes <= 0:
        rows = conn.execute(
            "SELECT * FROM stat_entries WHERE imported = 0"
        ).fetchall()
        return [dict(r) for r in rows]

    now_dt = parse_iso(now_ts)
    if now_dt is None:
        return []
    cutoff = iso_z(now_dt - timedelta(minutes=check_minutes))
    rows = conn.execute(
        """
        SELECT * FROM stat_entries
        WHERE imported = 0 AND last_searched_ts <= ?
        """,
        (cutoff,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_confirmed_entries(
    instance_url_filter: str = "",
    type_filter: str = "",
    offset: int = 0,
    limit: int = 25,
) -> Tuple[int, List[Dict], List[str]]:
    """Return paginated confirmed (imported) stat entries with optional filters.
    Returns a three-tuple: (total, entries, available_types) where total is the
    unfiltered count, entries is the current page of dicts with a computed
    turnaround field, and available_types is the distinct list of entry types
    present for the current instance filter (used to populate the type dropdown)."""
    conn = get_connection()
    where = ["imported = 1"]
    params: list = []
    if instance_url_filter:
        where.append("instance_url = ?")
        params.append(instance_url_filter)
    where_sql = "WHERE " + " AND ".join(where)

    type_rows = conn.execute(
        f"SELECT DISTINCT type FROM stat_entries {where_sql} ORDER BY type", params
    ).fetchall()
    available_types = [r["type"] for r in type_rows if r["type"]]

    if type_filter:
        where.append("type = ?")
        params.append(type_filter)
        where_sql = "WHERE " + " AND ".join(where)

    total = conn.execute(
        f"SELECT COUNT(*) FROM stat_entries {where_sql}", params
    ).fetchone()[0]

    rows = conn.execute(
        f"""
        SELECT app, instance, item_id, title, type, iteration,
               first_searched_ts, last_searched_ts, imported_ts
        FROM stat_entries {where_sql}
        ORDER BY imported_ts DESC
        LIMIT ? OFFSET ?
        """,
        params + [limit, offset]
    ).fetchall()

    entries = []
    for r in rows:
        entry = dict(r)
        entry["turnaround"] = _calc_turnaround(r["first_searched_ts"], r["imported_ts"])
        entries.append(entry)

    return total, entries, available_types


def _calc_turnaround(first_ts: Optional[str], imported_ts: Optional[str]) -> str:
    if not first_ts or not imported_ts:
        return "-"
    dt_first = parse_iso(first_ts)
    dt_imported = parse_iso(imported_ts)
    if dt_first is None or dt_imported is None:
        return "-"
    delta_s = (dt_imported - dt_first).total_seconds()
    if delta_s < 0:
        return "-"
    if delta_s < 30:
        return "<1m"
    minutes = int((delta_s + 30) // 60)
    hours = minutes // 60
    days = hours // 24
    if days >= 56:
        months = days // 30
        return f"{months}mo"
    if days >= 7:
        weeks = days // 7
        rem_days = days % 7
        return f"{weeks}w {rem_days}d" if rem_days else f"{weeks}w"
    if days > 0:
        rem_hours = hours % 24
        return f"{days}d {rem_hours}h" if rem_hours else f"{days}d"
    if hours > 0:
        rem_minutes = minutes % 60
        return f"{hours}h {rem_minutes}m" if rem_minutes else f"{hours}h"
    return f"{minutes}m"


def rename_instance_in_history(app: str, instance_url: str, new_name: str) -> None:
    """Update instance_name in search_history and stat_entries for a renamed instance."""
    url = instance_url.rstrip("/")
    conn = get_connection()
    conn.execute(
        "UPDATE search_history SET instance_name = ? WHERE app = ? AND instance_url = ?",
        (new_name, app, url)
    )
    conn.execute(
        "UPDATE stat_entries SET instance = ? WHERE app = ? AND instance_url = ?",
        (new_name, app, url)
    )
    conn.commit()


def clear_stat_entries() -> None:
    """Delete all rows from stat_entries. Lifetime totals are not affected."""
    conn = get_connection()
    conn.execute("DELETE FROM stat_entries")
    conn.commit()


def prune_stat_entries(retention_days: int) -> int:
    """Delete confirmed (imported = 1) stat entries older than retention_days.
    Unimported (pending) entries are intentionally preserved regardless of age
    so in-flight import checks are never interrupted. Returns the number of
    rows deleted. No-op if retention_days <= 0."""
    if retention_days <= 0:
        return 0
    cutoff = iso_z(utcnow() - timedelta(days=retention_days))
    conn = get_connection()
    cur = conn.execute(
        "DELETE FROM stat_entries WHERE imported = 1 AND imported_ts < ?",
        (cutoff,)
    )
    conn.commit()
    return cur.rowcount

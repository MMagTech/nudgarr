"""
nudgarr/db/entries.py

stat_entries table — all read/write operations.

  upsert_stat_entry()       -- insert or update the active (unimported) row
  confirm_stat_entry()      -- mark a row as imported; insert quality_history row
  get_unconfirmed_entries() -- entries eligible for import checking
  get_confirmed_entries()   -- paginated confirmed imports with quality history
  get_period_totals()       -- confirmed import counts for a rolling day window
  rename_instance_in_history() -- update instance name after a rename
  clear_stat_entries()      -- delete all rows
  prune_stat_entries()      -- delete old unimported rows
"""

from datetime import timedelta
from typing import Dict, List, Optional, Tuple

import logging

from nudgarr.db.connection import get_connection
from nudgarr.db.intel import get_intel_aggregate, update_intel_aggregate
from nudgarr.utils import iso_z, parse_iso, utcnow

logger = logging.getLogger(__name__)


def upsert_stat_entry(
    app: str,
    instance: str,
    instance_url: str,
    item_id: str,
    title: str,
    entry_type: str,
    searched_ts: str,
    quality_from: str = "",
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
             first_searched_ts, last_searched_ts, imported, quality_from)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
        ON CONFLICT (app, instance, item_id, type) WHERE imported = 0 DO UPDATE SET
            last_searched_ts = excluded.last_searched_ts,
            instance_url = excluded.instance_url,
            title = CASE WHEN excluded.title != '' THEN excluded.title
                         ELSE stat_entries.title END,
            quality_from = CASE WHEN excluded.quality_from != '' THEN excluded.quality_from
                                ELSE stat_entries.quality_from END
        """,
        (app, instance, instance_url, item_id, title, entry_type, searched_ts, searched_ts, quality_from or "")
    )
    conn.commit()


def confirm_stat_entry(
    app: str,
    instance: str,
    instance_url: str,
    item_id: str,
    entry_type: str,
    imported_ts: str,
    quality_to: str = "",
) -> bool:
    """Mark a stat entry as imported and increment its iteration counter.
    Inserts a quality_history row when quality_to is present so the full
    upgrade path is preserved across multiple import cycles.
    Uses a two-phase lookup: by instance name first, then by URL as a fallback
    to handle instance renames gracefully. If a confirmed row already exists for
    this item, updates it in place (one row per item). Returns True if a row
    was successfully confirmed, False if no matching unimported row was found."""
    conn = get_connection()

    # Read the unconfirmed row first — we need quality_from before it is deleted.
    pending = conn.execute(
        """
        SELECT id, quality_from, first_searched_ts FROM stat_entries
        WHERE app = ? AND item_id = ? AND type = ? AND imported = 0
          AND (instance = ? OR instance_url = ?)
        LIMIT 1
        """,
        (app, item_id, entry_type, instance, instance_url)
    ).fetchone()

    if not pending:
        return False

    quality_from = pending["quality_from"] or None

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
        final_iteration = new_iteration
        entry_id = existing["id"]
        conn.execute(
            """
            UPDATE stat_entries
            SET type = ?, imported_ts = ?, iteration = ?, instance = ?
            WHERE id = ?
            """,
            (entry_type, imported_ts, new_iteration, instance, entry_id)
        )
        conn.execute(
            """
            DELETE FROM stat_entries
            WHERE app = ? AND item_id = ? AND type = ? AND imported = 0
              AND (instance = ? OR instance_url = ?)
            """,
            (app, item_id, entry_type, instance, instance_url)
        )
    else:
        final_iteration = 1
        conn.execute(
            """
            UPDATE stat_entries
            SET imported = 1, imported_ts = ?, iteration = 1, instance = ?
            WHERE id = ?
            """,
            (imported_ts, instance, pending["id"])
        )
        entry_id = pending["id"]

    # Insert a quality_history row if quality_to was captured.
    # quality_from may be None for first-time acquisitions — stored as NULL,
    # displayed as "Acquired →" in the UI.
    if quality_to:
        conn.execute(
            """
            INSERT INTO quality_history (entry_id, quality_from, quality_to, imported_ts)
            VALUES (?, ?, ?, ?)
            """,
            (entry_id, quality_from, quality_to, imported_ts)
        )

    # ── Intel aggregate update ────────────────────────────────────────────
    # All writes happen inside the same transaction before commit so a failure
    # rolls back both the confirm and the aggregate update cleanly.
    _update_intel_on_confirm(
        conn=conn,
        app=app,
        instance_url=instance_url,
        item_id=item_id,
        entry_type=entry_type,
        imported_ts=imported_ts,
        first_searched_ts=pending["first_searched_ts"],
        quality_from=quality_from,
        quality_to=quality_to,
        final_iteration=final_iteration,
    )

    conn.commit()
    return True


def _get_library_age_bucket(library_added: str, first_searched_ts: str) -> str:
    """Return the library age bucket label for an item at the time of first search.

    Age is the gap between library_added and first_searched_ts in days.
    Returns an empty string if either timestamp is missing or unparseable,
    which causes the item to fall into the 'Unknown' bucket at display time.
    """
    if not library_added or not first_searched_ts:
        return ""
    dt_added = parse_iso(library_added)
    dt_searched = parse_iso(first_searched_ts)
    if dt_added is None or dt_searched is None:
        return ""
    age_days = (dt_searched - dt_added).total_seconds() / 86400
    if age_days < 0:
        return ""
    if age_days < 30:
        return "Under 1 month"
    if age_days < 90:
        return "1 to 3 months"
    if age_days < 180:
        return "3 to 6 months"
    if age_days < 365:
        return "6 to 12 months"
    return "12+ months"


def _update_intel_on_confirm(
    conn,
    app: str,
    instance_url: str,
    item_id: str,
    entry_type: str,
    imported_ts: str,
    first_searched_ts: str,
    quality_from: Optional[str],
    quality_to: str,
    final_iteration: int,
) -> None:
    """Update intel_aggregate counters at the moment a confirm fires.

    Called inside confirm_stat_entry() before conn.commit() so aggregate
    writes are always atomic with the confirm itself. A rollback undoes both.

    Reads search_count and library_added from search_history for the confirmed
    item (point-in-time snapshot before any future reset). Uses update_intel_aggregate
    which issues a single UPDATE against the existing aggregate row.
    """
    # Read search_count and library_added from search_history at confirm time.
    # This snapshots the count before any future auto-unexclude reset can alter it.
    url = instance_url.rstrip("/")
    sh_row = conn.execute(
        """
        SELECT search_count, library_added FROM search_history
        WHERE app = ? AND instance_url = ? AND item_id = ?
        LIMIT 1
        """,
        (app, url, item_id)
    ).fetchone()
    search_count = sh_row["search_count"] if sh_row else 0
    library_added = sh_row["library_added"] if sh_row else ""

    # Turnaround in days.
    turnaround_days = 0.0
    dt_first = parse_iso(first_searched_ts)
    dt_imported = parse_iso(imported_ts)
    if dt_first and dt_imported:
        turnaround_days = max(0.0, (dt_imported - dt_first).total_seconds() / 86400)

    # Read current aggregate for JSON blob updates.
    agg = get_intel_aggregate()

    updates = {}

    # Turnaround — always recorded regardless of iteration.
    updates["turnaround_sum_days"] = agg["turnaround_sum_days"] + turnaround_days
    updates["turnaround_count"] = agg["turnaround_count"] + 1

    # Searches per import — always recorded.
    updates["searches_per_import_sum"] = agg["searches_per_import_sum"] + search_count
    updates["searches_per_import_count"] = agg["searches_per_import_count"] + 1

    # Pipeline import split — only on first import (iteration = 1).
    # entry_type reflects the stat_entries.type value set by batch_record_stat_entries:
    #   "Upgraded"  — Cutoff Unmet pipeline
    #   "Acquired"  — Backlog pipeline
    #   "CF Score"  — CF Score Scan pipeline
    if final_iteration == 1:
        if entry_type == "Upgraded":
            updates["cutoff_import_count"] = agg["cutoff_import_count"] + 1
        elif entry_type == "CF Score":
            updates["cf_score_import_count"] = agg["cf_score_import_count"] + 1
        else:
            # "Acquired" (Backlog) and any legacy or unknown types
            updates["backlog_import_count"] = agg["backlog_import_count"] + 1
        updates["success_total_imported"] = agg["success_total_imported"] + 1

    # Quality upgrades — only genuine upgrades (quality_from populated).
    if quality_to and quality_from:
        updates["quality_upgrades_count"] = agg["quality_upgrades_count"] + 1

    # Imported once vs upgraded tracking.
    # iteration=1: new first-time import, add to imported_once.
    # iteration=2: first upgrade, move title from imported_once to upgraded.
    # iteration>2: already in upgraded, no change needed.
    if final_iteration == 1:
        updates["imported_once_count"] = agg["imported_once_count"] + 1
    elif final_iteration == 2:
        updates["imported_once_count"] = max(0, agg["imported_once_count"] - 1)
        updates["upgraded_count"] = agg["upgraded_count"] + 1

    # Per-instance imports (JSON blob) — only on first import.
    if final_iteration == 1:
        per_inst = agg["per_instance_imports"]
        per_inst[url] = per_inst.get(url, 0) + 1
        updates["per_instance_imports"] = per_inst

    # Per-instance turnaround (JSON blob) — always recorded.
    per_ta = agg["per_instance_turnaround"]
    inst_ta = per_ta.get(url, {"sum": 0.0, "count": 0})
    inst_ta["sum"] = inst_ta["sum"] + turnaround_days
    inst_ta["count"] = inst_ta["count"] + 1
    per_ta[url] = inst_ta
    updates["per_instance_turnaround"] = per_ta

    # Library age bucket imported count (JSON blob) — only on first import.
    if final_iteration == 1:
        bucket = _get_library_age_bucket(library_added, first_searched_ts)
        age_buckets = agg["library_age_buckets"]
        bucket_key = bucket if bucket else "Unknown"
        bucket_data = age_buckets.get(bucket_key, {"total": 0, "imported": 0})
        bucket_data["imported"] = bucket_data["imported"] + 1
        age_buckets[bucket_key] = bucket_data
        updates["library_age_buckets"] = age_buckets

    update_intel_aggregate(updates)


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
    turnaround field and quality_history list, and available_types is the
    distinct list of entry types present for the current instance filter."""
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
        SELECT id, app, instance, item_id, title, type, iteration,
               first_searched_ts, last_searched_ts, imported_ts
        FROM stat_entries {where_sql}
        ORDER BY imported_ts DESC
        LIMIT ? OFFSET ?
        """,
        params + [limit, offset]
    ).fetchall()

    # Fetch quality history for all entries in one query, then group by entry_id.
    # Ordered oldest-first so the UI can render the chronological upgrade path
    # without needing to sort client-side.
    entry_ids = [r["id"] for r in rows]
    history_map: Dict[int, List[Dict]] = {eid: [] for eid in entry_ids}
    if entry_ids:
        placeholders = ",".join("?" * len(entry_ids))
        history_rows = conn.execute(
            f"""
            SELECT entry_id, quality_from, quality_to, imported_ts
            FROM quality_history
            WHERE entry_id IN ({placeholders})
            ORDER BY entry_id, imported_ts ASC
            """,
            entry_ids
        ).fetchall()
        for hr in history_rows:
            history_map[hr["entry_id"]].append({
                "quality_from": hr["quality_from"],
                "quality_to": hr["quality_to"],
                "imported_ts": hr["imported_ts"],
            })

    entries = []
    for r in rows:
        entry = dict(r)
        entry["turnaround"] = _calc_turnaround(r["first_searched_ts"], r["imported_ts"])
        entry["quality_history"] = history_map.get(r["id"], [])
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
    """Delete all rows from stat_entries. Lifetime totals are not affected.
    quality_history rows are removed automatically via ON DELETE CASCADE."""
    conn = get_connection()
    conn.execute("DELETE FROM stat_entries")
    conn.commit()


def prune_stat_entries(retention_days: int) -> int:
    """Delete confirmed (imported = 1) stat entries older than retention_days.
    Unimported (pending) entries are intentionally preserved regardless of age
    so in-flight import checks are never interrupted. quality_history rows are
    removed automatically via ON DELETE CASCADE. Returns the number of rows
    deleted. No-op if retention_days <= 0."""
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


def count_confirmed_entries() -> int:
    """Return count of confirmed (imported=1) stat entries."""
    return get_connection().execute(
        "SELECT COUNT(*) FROM stat_entries WHERE imported = 1"
    ).fetchone()[0]


def get_period_totals(days: int) -> Dict[str, int]:
    """Return confirmed import counts for a rolling window of the last N days.

    Counts confirmed stat_entries (imported=1) whose imported_ts falls within
    the last `days` days from now. Movies are identified by type values
    containing 'movie' or 'Upgraded'; shows by 'episode', 'missing_episode',
    or 'Acquired' with a sonarr app value.

    Uses the app column to distinguish movies (radarr) from shows (sonarr)
    so the split matches the lifetime totals pattern.

    Returns {movies: N, shows: N}. Never returns None.
    """
    conn = get_connection()
    cutoff = iso_z(utcnow() - timedelta(days=days))
    rows = conn.execute(
        """
        SELECT app, COUNT(*) as cnt
        FROM stat_entries
        WHERE imported = 1 AND imported_ts >= ?
        GROUP BY app
        """,
        (cutoff,)
    ).fetchall()
    result = {"movies": 0, "shows": 0}
    for r in rows:
        if r["app"] == "radarr":
            result["movies"] = r["cnt"]
        elif r["app"] == "sonarr":
            result["shows"] = r["cnt"]
    return result


def batch_upsert_stat_entries(entries: list) -> None:
    """Write multiple stat_entry rows in a single transaction.

    Each entry must be a dict with keys: app, instance, instance_url, item_id,
    title, entry_type, searched_ts, quality_from.
    A single commit covers the entire batch so a mid-batch failure rolls back
    cleanly rather than leaving partially-written rows.
    """
    if not entries:
        return
    conn = get_connection()
    for entry in entries:
        conn.execute(
            """
            INSERT INTO stat_entries
                (app, instance, instance_url, item_id, title, type,
                 first_searched_ts, last_searched_ts, imported, quality_from)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
            ON CONFLICT (app, instance, item_id, type) WHERE imported = 0 DO UPDATE SET
                last_searched_ts = excluded.last_searched_ts,
                instance_url = excluded.instance_url,
                title = CASE WHEN excluded.title != '' THEN excluded.title
                             ELSE stat_entries.title END,
                quality_from = CASE WHEN excluded.quality_from != '' THEN excluded.quality_from
                                    ELSE stat_entries.quality_from END
            """,
            (
                entry["app"], entry["instance"], entry["instance_url"],
                entry["item_id"], entry.get("title", ""), entry["entry_type"],
                entry["searched_ts"], entry["searched_ts"],
                entry.get("quality_from", "") or "",
            )
        )
    conn.commit()

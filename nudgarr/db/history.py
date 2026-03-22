"""
nudgarr/db/history.py

search_history table — all read/write operations.

  upsert_search_history()      -- insert or update a row
  get_last_searched_ts()       -- single-item cooldown lookup
  get_last_searched_ts_bulk()  -- batch cooldown lookup
  get_search_history()         -- paginated history with cooldown metadata
  get_search_history_summary() -- entry counts per instance
  reset_search_count_by_title() -- reset search_count to 0 on auto-unexclude
  prune_search_history()       -- delete rows older than retention_days
  clear_search_history()       -- delete all rows
"""

import os
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from nudgarr.constants import DB_FILE
from nudgarr.db.connection import get_connection
from nudgarr.utils import iso_z, parse_iso, utcnow

import logging

logger = logging.getLogger(__name__)


def upsert_search_history(
    app: str,
    instance_name: str,
    instance_url: str,
    item_type: str,
    item_id: str,
    title: str,
    sweep_type: str,
    library_added: str,
    now_ts: str,
    series_id: str = "",
) -> None:
    """Insert or update a search_history row for one searched item.
    On conflict (same app, instance_url, item_type, item_id), increments
    search_count and updates last_searched_ts. sweep_type, library_added,
    series_id, and title are updated only when the incoming value is non-empty,
    preserving the original value if the caller passes an empty string."""
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO search_history
            (app, instance_name, instance_url, item_type, item_id, series_id,
             title, sweep_type, library_added,
             first_searched_ts, last_searched_ts, search_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        ON CONFLICT (app, instance_url, item_type, item_id) DO UPDATE SET
            last_searched_ts = excluded.last_searched_ts,
            search_count     = search_history.search_count + 1,
            instance_name    = excluded.instance_name,
            series_id        = CASE WHEN excluded.series_id != '' THEN excluded.series_id
                                    ELSE search_history.series_id END,
            title            = CASE WHEN excluded.title != '' THEN excluded.title
                                    ELSE search_history.title END,
            sweep_type       = CASE WHEN excluded.sweep_type != '' THEN excluded.sweep_type
                                    ELSE search_history.sweep_type END,
            library_added    = CASE WHEN excluded.library_added != '' THEN excluded.library_added
                                    ELSE search_history.library_added END
        """,
        (app, instance_name, instance_url, item_type, item_id, series_id,
         title, sweep_type, library_added, now_ts, now_ts)
    )
    conn.commit()


def get_last_searched_ts(
    app: str,
    instance_name: str,
    instance_url: str,
    item_type: str,
    item_id: str,
) -> Optional[str]:
    """Return the last_searched_ts ISO string for one item, or None if not in history."""
    conn = get_connection()
    row = conn.execute(
        """
        SELECT last_searched_ts FROM search_history
        WHERE app = ? AND instance_url = ?
          AND item_type = ? AND item_id = ?
        """,
        (app, instance_url, item_type, item_id)
    ).fetchone()
    return row["last_searched_ts"] if row else None


def get_last_searched_ts_bulk(
    app: str,
    instance_url: str,
    item_type: str,
    item_ids: List[str],
) -> Dict[str, str]:
    """Return {item_id: last_searched_ts} for a list of items in one query.
    Filters by app, instance_url, and item_type — instance_name is not used
    because instance_url is the reliable unique identifier in the DB."""
    if not item_ids:
        return {}
    conn = get_connection()
    placeholders = ",".join("?" * len(item_ids))
    rows = conn.execute(
        f"""
        SELECT item_id, last_searched_ts FROM search_history
        WHERE app = ? AND instance_url = ?
          AND item_type = ? AND item_id IN ({placeholders})
        """,
        [app, instance_url, item_type] + item_ids
    ).fetchall()
    return {r["item_id"]: r["last_searched_ts"] for r in rows}


def get_search_history(
    app_filter: str = "",
    instance_key: str = "",
    offset: int = 0,
    limit: int = 250,
    cooldown_hours: int = 48,
    instance_name_map: Optional[Dict[str, str]] = None,
    cooldown_map: Optional[Dict[str, int]] = None,
) -> Tuple[int, List[Dict]]:
    """Return paginated search history rows with computed cooldown metadata.
    instance_key accepts the composite 'name|url' format and extracts the URL
    portion internally for the database query. eligible_again is computed per row
    using cooldown_map[instance_url] when present, falling back to cooldown_hours.
    This ensures per-instance cooldown overrides are reflected in the display.
    Returns (total, items)."""
    conn = get_connection()
    params: list = []
    where = []
    if app_filter:
        where.append("sh.app = ?")
        params.append(app_filter)
    if instance_key:
        parts = instance_key.split("|", 1)
        if len(parts) > 1:
            where.append("sh.instance_url = ?")
            params.append(parts[1])
        else:
            where.append("sh.instance_url = ?")
            params.append(parts[0])
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    total = conn.execute(
        f"SELECT COUNT(*) FROM search_history sh {where_sql}", params
    ).fetchone()[0]

    rows = conn.execute(
        f"""
        SELECT sh.app, sh.instance_name, sh.instance_url, sh.item_type, sh.item_id, sh.series_id,
               sh.title, sh.sweep_type, sh.library_added,
               sh.last_searched_ts, sh.search_count,
               se.iteration AS import_iteration
        FROM search_history sh
        LEFT JOIN stat_entries se
          ON se.app = sh.app
         AND se.instance_url = sh.instance_url
         AND se.item_id = sh.item_id
         AND se.imported = 1
        {where_sql}
        ORDER BY sh.last_searched_ts DESC
        LIMIT ? OFFSET ?
        """,
        params + [limit, offset]
    ).fetchall()

    items = []
    for r in rows:
        ts = r["last_searched_ts"]
        eligible = ""
        dt = parse_iso(ts) if ts else None
        if dt is not None:
            url = r["instance_url"].rstrip("/")
            row_cooldown = (cooldown_map or {}).get(url, cooldown_hours)
            eligible = "Next Sweep" if row_cooldown <= 0 else iso_z(dt + timedelta(hours=row_cooldown))
        sk = f"{r['instance_name']}|{r['instance_url']}"
        friendly = (instance_name_map or {}).get(sk, r["instance_name"])
        items.append({
            "key": f"{r['item_type']}:{r['item_id']}",
            "app": r["app"],
            "instance_name": r["instance_name"],
            "item_id": r["item_id"],
            "series_id": r["series_id"],
            "title": r["title"],
            "instance": friendly,
            "last_searched": ts,
            "eligible_again": eligible,
            "sweep_type": r["sweep_type"],
            "library_added": r["library_added"],
            "search_count": r["search_count"],
            "import_iteration": r["import_iteration"] or 0,
        })
    return total, items


def get_search_history_summary(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Return entry counts, file size, and instance metadata for the History tab header.
    state_key is imported locally here to avoid a circular import
    (nudgarr.state imports nudgarr.db, so importing at module level would cycle)."""
    from nudgarr.state import state_key as make_state_key

    conn = get_connection()
    rows = conn.execute(
        """
        SELECT app, instance_url, COUNT(*) as cnt
        FROM search_history
        GROUP BY app, instance_url
        """
    ).fetchall()

    url_to_name: Dict[str, str] = {}
    for app_name in ("radarr", "sonarr"):
        for inst in cfg.get("instances", {}).get(app_name, []):
            url_to_name[inst["url"].rstrip("/")] = inst["name"]

    per_instance: Dict[str, Dict] = {"radarr": {}, "sonarr": {}}
    radarr_total = 0
    sonarr_total = 0
    for r in rows:
        name = url_to_name.get(r["instance_url"], r["instance_url"])
        sk = f"{name}|{r['instance_url'].rstrip('/')}"
        per_instance[r["app"]][sk] = r["cnt"]
        if r["app"] == "radarr":
            radarr_total += r["cnt"]
        else:
            sonarr_total += r["cnt"]

    instances: Dict[str, List] = {"radarr": [], "sonarr": []}
    for app in ("radarr", "sonarr"):
        for inst in cfg.get("instances", {}).get(app, []):
            sk = make_state_key(inst["name"], inst["url"])
            instances[app].append({"key": sk, "name": inst["name"]})

    try:
        size = os.path.getsize(DB_FILE)
    except Exception:
        size = 0

    def _human(n: int) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if n < 1024:
                return f"{n} {unit}" if unit == "B" else f"{n:.1f} {unit}"
            n //= 1024
        return f"{n:.1f} TB"

    return {
        "file_size_bytes": size,
        "file_size_human": _human(size),
        "radarr_entries": radarr_total,
        "sonarr_entries": sonarr_total,
        "per_instance": per_instance,
        "instances": instances,
        "retention_days": int(cfg.get("state_retention_days", 180)),
    }


def prune_search_history(retention_days: int) -> int:
    """Delete search_history rows whose last_searched_ts is older than retention_days.
    Returns the number of rows deleted. No-op if retention_days <= 0."""
    if retention_days <= 0:
        return 0
    cutoff = iso_z(utcnow() - timedelta(days=retention_days))
    conn = get_connection()
    cur = conn.execute(
        "DELETE FROM search_history WHERE last_searched_ts < ?", (cutoff,)
    )
    conn.commit()
    return cur.rowcount


def clear_search_history() -> None:
    """Delete all rows from search_history. sweep_lifetime is not affected."""
    conn = get_connection()
    conn.execute("DELETE FROM search_history")
    conn.commit()


def count_search_history() -> int:
    """Return total row count of search_history."""
    return get_connection().execute("SELECT COUNT(*) FROM search_history").fetchone()[0]


def get_search_history_counts() -> list:
    """Return raw (app, instance_url, cnt) rows for diagnostic use.
    Returns a list of sqlite3.Row objects with app, instance_url, cnt fields."""
    return get_connection().execute(
        """
        SELECT app, instance_url, COUNT(*) as cnt
        FROM search_history
        GROUP BY app, instance_url
        """
    ).fetchall()


def batch_upsert_search_history(items: List[Dict]) -> None:
    """Write multiple search_history rows in a single transaction.

    Each item must be a dict with the same keys accepted by upsert_search_history.
    A single commit covers the entire batch so a mid-batch failure rolls back cleanly
    rather than leaving partially-written rows.
    """
    if not items:
        return
    conn = get_connection()
    now_s = items[0].get("now_ts", "")  # all items in a batch share the same timestamp
    for item in items:
        conn.execute(
            """
            INSERT INTO search_history
                (app, instance_name, instance_url, item_type, item_id, series_id,
                 title, sweep_type, library_added,
                 first_searched_ts, last_searched_ts, search_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT (app, instance_url, item_type, item_id) DO UPDATE SET
                last_searched_ts = excluded.last_searched_ts,
                search_count     = search_history.search_count + 1,
                instance_name    = excluded.instance_name,
                series_id        = CASE WHEN excluded.series_id != '' THEN excluded.series_id
                                        ELSE search_history.series_id END,
                title            = CASE WHEN excluded.title != '' THEN excluded.title
                                        ELSE search_history.title END,
                sweep_type       = CASE WHEN excluded.sweep_type != '' THEN excluded.sweep_type
                                        ELSE search_history.sweep_type END,
                library_added    = CASE WHEN excluded.library_added != '' THEN excluded.library_added
                                        ELSE search_history.library_added END
            """,
            (
                item["app"], item["instance_name"], item["instance_url"],
                item["item_type"], item["item_id"], item.get("series_id", ""),
                item.get("title", ""), item.get("sweep_type", ""),
                item.get("library_added", ""),
                item.get("now_ts", now_s), item.get("now_ts", now_s),
            )
        )
    conn.commit()


def reset_search_count_by_title(title: str) -> None:
    """Reset search_count to 0 for all search_history rows matching a title.

    Called when a title is auto-unexcluded at sweep start. Without this reset
    the import check loop would see the count still at or above the threshold
    and immediately re-exclude the title before it ever gets searched again,
    making the auto-unexclude window functionally useless.

    Matches case-insensitively on title across all apps and instances — the
    exclusions table is global and carries no app or item_id, so title is the
    only available key. Does nothing if no matching rows exist.
    """
    conn = get_connection()
    conn.execute(
        "UPDATE search_history SET search_count = 0 WHERE title = ? COLLATE NOCASE",
        (title.strip(),)
    )
    conn.commit()

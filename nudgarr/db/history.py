"""
nudgarr/db/history.py

search_history table — all read/write operations.

  upsert_search_history()      -- insert or update a row
  get_last_searched_ts()       -- single-item cooldown lookup
  get_last_searched_ts_bulk()  -- batch cooldown lookup
  get_search_history()         -- paginated history with cooldown metadata
  get_search_history_summary() -- entry counts per instance
  prune_search_history()       -- delete rows older than retention_days
  clear_search_history()       -- delete all rows
"""

import os
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from nudgarr.constants import DB_FILE
from nudgarr.db.connection import get_connection
from nudgarr.utils import iso_z, parse_iso, utcnow


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
    instance_name: str,
    instance_url: str,
    item_type: str,
    item_ids: List[str],
) -> Dict[str, str]:
    """Return {item_id: last_searched_ts} for a list of items in one query."""
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
) -> Tuple[int, List[Dict]]:
    conn = get_connection()
    params: list = []
    where = []
    if app_filter:
        where.append("app = ?")
        params.append(app_filter)
    if instance_key:
        parts = instance_key.split("|", 1)
        if len(parts) > 1:
            where.append("instance_url = ?")
            params.append(parts[1])
        else:
            where.append("instance_url = ?")
            params.append(parts[0])
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    total = conn.execute(
        f"SELECT COUNT(*) FROM search_history {where_sql}", params
    ).fetchone()[0]

    rows = conn.execute(
        f"""
        SELECT app, instance_name, instance_url, item_type, item_id, series_id,
               title, sweep_type, library_added,
               last_searched_ts, search_count
        FROM search_history {where_sql}
        ORDER BY last_searched_ts DESC
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
            eligible = iso_z(dt + timedelta(hours=cooldown_hours))
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
        })
    return total, items


def get_search_history_summary(cfg: Dict[str, Any]) -> Dict[str, Any]:
    # Local import avoids circular dependency (state imports db)
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
    conn = get_connection()
    conn.execute("DELETE FROM search_history")
    conn.commit()

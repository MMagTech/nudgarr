"""
nudgarr/db.py

SQLite persistence layer.  Replaces the three JSON runtime files
(nudgarr-state.json, nudgarr-stats.json, nudgarr-exclusions.json).

Public API
──────────
Connection management
  get_connection()         -- return a thread-local connection, opening it if needed
  close_connection()       -- close the thread-local connection (call on thread exit)
  init_db()                -- create schema and run migration if needed; call once at startup

search_history
  upsert_search_history()  -- insert or update a search_history row
  get_search_history()     -- paginated history items with cooldown metadata
  get_search_history_summary() -- entry counts per instance
  get_last_searched_ts()   -- return last_searched_ts for a single item (cooldown check)
  prune_search_history()   -- delete rows older than retention_days
  clear_search_history()   -- delete all rows (Clear History)

stat_entries
  upsert_stat_entry()      -- insert-or-update the active (unimported) row
  confirm_stat_entry()     -- mark a row as imported
  get_unconfirmed_entries()-- return entries eligible for import checking
  get_confirmed_entries()  -- paginated confirmed imports with filters
  clear_stat_entries()     -- delete all rows (preserves lifetime_totals)
  prune_stat_entries()     -- delete old unimported rows

exclusions
  get_exclusions()         -- return all exclusion rows
  add_exclusion()          -- insert a title (case-insensitive dedup)
  remove_exclusion()       -- delete by title

sweep_lifetime
  upsert_sweep_lifetime()  -- insert or update counters for one instance
  get_sweep_lifetime()     -- return all rows as a dict keyed by instance_key
  get_sweep_lifetime_row() -- return one row by instance_key

lifetime_totals
  increment_lifetime_total() -- add delta to movies or shows counter
  get_lifetime_totals()    -- return {movies: N, shows: N}

backup
  export_as_json_dict()    -- serialise all tables to a JSON-serialisable dict

Imports from within the package: constants, utils only.
"""

import os
import sqlite3
import threading
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from nudgarr.constants import (
    DB_FILE,
    EXCLUSIONS_FILE,
    STATE_FILE,
    STATS_FILE,
)
from nudgarr.utils import iso_z, load_json, parse_iso, utcnow

# ── Thread-local connection ───────────────────────────────────────────

_local = threading.local()


def get_connection() -> sqlite3.Connection:
    """Return a thread-local SQLite connection, opening it if needed."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        os.makedirs(os.path.dirname(DB_FILE) or ".", exist_ok=True)
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        _apply_pragmas(conn)
        _local.conn = conn
    return conn


def close_connection() -> None:
    """Close the thread-local connection. Call on thread exit."""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None


def _apply_pragmas(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")


# ── Schema ────────────────────────────────────────────────────────────

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS search_history (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    app               TEXT NOT NULL,
    instance_name     TEXT NOT NULL,
    instance_url      TEXT NOT NULL,
    item_type         TEXT NOT NULL,
    item_id           TEXT NOT NULL,
    title             TEXT NOT NULL DEFAULT '',
    sweep_type        TEXT NOT NULL DEFAULT '',
    library_added     TEXT NOT NULL DEFAULT '',
    first_searched_ts TEXT NOT NULL,
    last_searched_ts  TEXT NOT NULL,
    search_count      INTEGER NOT NULL DEFAULT 1,
    UNIQUE (app, instance_name, instance_url, item_type, item_id)
);
CREATE INDEX IF NOT EXISTS idx_sh_lookup
    ON search_history (app, instance_name, instance_url, item_type, item_id);
CREATE INDEX IF NOT EXISTS idx_sh_last_searched
    ON search_history (last_searched_ts);

CREATE TABLE IF NOT EXISTS stat_entries (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    app               TEXT NOT NULL,
    instance          TEXT NOT NULL,
    item_id           TEXT NOT NULL,
    title             TEXT NOT NULL DEFAULT '',
    type              TEXT NOT NULL DEFAULT '',
    iteration         INTEGER NOT NULL DEFAULT 1,
    first_searched_ts TEXT NOT NULL,
    last_searched_ts  TEXT NOT NULL,
    imported          INTEGER NOT NULL DEFAULT 0,
    imported_ts       TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_stat_entries_active
    ON stat_entries (app, instance, item_id, type) WHERE imported = 0;
CREATE INDEX IF NOT EXISTS idx_stat_unimported
    ON stat_entries (imported, last_searched_ts) WHERE imported = 0;
CREATE INDEX IF NOT EXISTS idx_stat_imported
    ON stat_entries (imported_ts) WHERE imported = 1;

CREATE TABLE IF NOT EXISTS exclusions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL UNIQUE COLLATE NOCASE,
    excluded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sweep_lifetime (
    instance_key  TEXT NOT NULL PRIMARY KEY,
    runs          INTEGER NOT NULL DEFAULT 0,
    eligible      INTEGER NOT NULL DEFAULT 0,
    skipped       INTEGER NOT NULL DEFAULT 0,
    searched      INTEGER NOT NULL DEFAULT 0,
    last_run_utc  TEXT
);

CREATE TABLE IF NOT EXISTS lifetime_totals (
    key   TEXT NOT NULL PRIMARY KEY,
    value INTEGER NOT NULL DEFAULT 0
);
INSERT OR IGNORE INTO lifetime_totals (key, value) VALUES ('movies', 0);
INSERT OR IGNORE INTO lifetime_totals (key, value) VALUES ('shows', 0);

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER NOT NULL PRIMARY KEY,
    applied_at  TEXT NOT NULL
);
"""


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA_SQL)
    conn.commit()


# ── Init and migration ────────────────────────────────────────────────

def init_db() -> None:
    """
    Create schema if needed, then run the JSON migration if this is a
    fresh database and legacy JSON files are present.
    Called once at application startup.
    """
    conn = get_connection()
    _create_schema(conn)

    row = conn.execute(
        "SELECT version FROM schema_migrations WHERE version = 1"
    ).fetchone()
    if row is not None:
        _run_migration_v2(conn)
        return

    state_exists = os.path.exists(STATE_FILE)
    stats_exists = os.path.exists(STATS_FILE)
    excl_exists = os.path.exists(EXCLUSIONS_FILE)

    if not (state_exists or stats_exists or excl_exists):
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (1, ?)",
            (iso_z(utcnow()),)
        )
        conn.commit()
        print("[Migration] Fresh install — no legacy JSON files found, skipping migration")
        return

    _run_migration(conn)


def _run_migration(conn: sqlite3.Connection) -> None:
    print("[Migration] Legacy JSON files detected — starting migration")
    try:
        with conn:
            _migrate_exclusions(conn)
            _migrate_state(conn)
            _migrate_stats(conn)
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (1, ?)",
                (iso_z(utcnow()),)
            )
    except Exception as exc:
        print(f"[Migration] FAILED: {exc} — starting with empty database, JSON files untouched")
        try:
            conn.execute("DELETE FROM search_history")
            conn.execute("DELETE FROM stat_entries")
            conn.execute("DELETE FROM exclusions")
            conn.execute("DELETE FROM sweep_lifetime")
            conn.execute("DELETE FROM lifetime_totals WHERE key IN ('movies','shows')")
            conn.execute("INSERT OR IGNORE INTO lifetime_totals (key, value) VALUES ('movies', 0)")
            conn.execute("INSERT OR IGNORE INTO lifetime_totals (key, value) VALUES ('shows', 0)")
            conn.commit()
        except Exception:
            pass
        return

    for path in (STATE_FILE, STATS_FILE, EXCLUSIONS_FILE):
        if os.path.exists(path):
            try:
                os.rename(path, path + ".migrated")
                print(f"[Migration] Renamed {path} → {path}.migrated")
            except Exception as rename_err:
                print(f"[Migration] Warning: could not rename {path}: {rename_err}")

    print("[Migration] Complete")


def _run_migration_v2(conn: sqlite3.Connection) -> None:
    """
    Schema v2 — adds iteration column and deduplicates imported stat rows
    left over from the JSON migration.
    Safe to run on every startup when v2 is not yet recorded.
    """
    row = conn.execute(
        "SELECT version FROM schema_migrations WHERE version = 2"
    ).fetchone()
    if row is not None:
        return

    print("[Migration v2] Running — adding iteration column and deduplicating imports")
    try:
        with conn:
            # Add iteration column if not present (existing installs)
            cols = [r[1] for r in conn.execute("PRAGMA table_info(stat_entries)").fetchall()]
            if "iteration" not in cols:
                conn.execute(
                    "ALTER TABLE stat_entries ADD COLUMN iteration INTEGER NOT NULL DEFAULT 1"
                )

            # Deduplicate: find (app, instance, item_id, type) groups
            # with multiple imported=1 rows — artefacts of the JSON migration
            # which appended rather than upserted. Keep earliest first_searched_ts
            # (tiebreak: lowest id), delete the rest.
            dup_groups = conn.execute(
                """
                SELECT app, instance, item_id, type
                FROM stat_entries
                WHERE imported = 1
                GROUP BY app, instance, item_id, type
                HAVING COUNT(*) > 1
                """
            ).fetchall()

            deleted = 0
            for grp in dup_groups:
                group_rows = conn.execute(
                    """
                    SELECT id FROM stat_entries
                    WHERE imported = 1
                      AND app = ? AND instance = ? AND item_id = ? AND type = ?
                    ORDER BY first_searched_ts ASC, id ASC
                    """,
                    (grp[0], grp[1], grp[2], grp[3])
                ).fetchall()
                for r in group_rows[1:]:
                    conn.execute("DELETE FROM stat_entries WHERE id = ?", (r[0],))
                    deleted += 1

            # Rename sweep_type labels to shorter single-word versions
            conn.execute("UPDATE search_history SET sweep_type = 'Backlog' WHERE sweep_type = 'Backlog Nudge'")
            conn.execute("UPDATE search_history SET sweep_type = 'Cutoff' WHERE sweep_type = 'Cutoff Unmet'")

            conn.execute(
                (iso_z(utcnow()),)
            )

        print(f"[Migration v2] Complete — {deleted} duplicate imported rows removed")
    except Exception as exc:
        print(f"[Migration v2] FAILED: {exc}")


def _migrate_exclusions(conn: sqlite3.Connection) -> None:
    data = load_json(EXCLUSIONS_FILE, [])
    if not isinstance(data, list):
        return
    for entry in data:
        title = (entry.get("title") or "").strip()
        excluded_at = entry.get("excluded_at") or iso_z(utcnow())
        if title:
            conn.execute(
                "INSERT OR IGNORE INTO exclusions (title, excluded_at) VALUES (?, ?)",
                (title, excluded_at)
            )
    print(f"[Migration] exclusions: {len(data)} rows")


def _migrate_state(conn: sqlite3.Connection) -> None:
    state = load_json(STATE_FILE, {})
    if not isinstance(state, dict):
        return

    rows_inserted = 0
    for app in ("radarr", "sonarr"):
        app_obj = state.get(app, {})
        if not isinstance(app_obj, dict):
            continue
        for inst_key, bucket in app_obj.items():
            if not isinstance(bucket, dict):
                continue
            parts = inst_key.split("|", 1)
            inst_name = parts[0]
            inst_url = parts[1] if len(parts) > 1 else ""
            for item_key, entry in bucket.items():
                key_parts = item_key.split(":", 1)
                item_type = key_parts[0]
                item_id = key_parts[1] if len(key_parts) > 1 else item_key
                if isinstance(entry, dict):
                    ts = entry.get("ts") or iso_z(utcnow())
                    title = entry.get("title") or ""
                    sweep_type = entry.get("sweep_type") or ""
                    library_added = entry.get("library_added") or ""
                    search_count = entry.get("search_count") or 1
                else:
                    ts = entry if isinstance(entry, str) else iso_z(utcnow())
                    title = ""
                    sweep_type = ""
                    library_added = ""
                    search_count = 1
                conn.execute(
                    """
                    INSERT OR IGNORE INTO search_history
                        (app, instance_name, instance_url, item_type, item_id,
                         title, sweep_type, library_added,
                         first_searched_ts, last_searched_ts, search_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (app, inst_name, inst_url, item_type, item_id,
                     title, sweep_type, library_added, ts, ts, search_count)
                )
                rows_inserted += 1

    lifetime = state.get("sweep_lifetime", {})
    if isinstance(lifetime, dict):
        for lk, lf in lifetime.items():
            if not isinstance(lf, dict):
                continue
            conn.execute(
                """
                INSERT OR REPLACE INTO sweep_lifetime
                    (instance_key, runs, eligible, skipped, searched, last_run_utc)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    lk,
                    lf.get("runs", 0),
                    lf.get("eligible", 0),
                    lf.get("skipped", 0),
                    lf.get("searched", 0),
                    lf.get("last_run_utc"),
                )
            )

    print(f"[Migration] search_history: {rows_inserted} rows")


def _migrate_stats(conn: sqlite3.Connection) -> None:
    stats = load_json(STATS_FILE, {})
    if not isinstance(stats, dict):
        return

    entries = stats.get("entries", [])
    imported_rows = 0
    unimported_rows = 0

    groups: Dict[Tuple, Dict] = {}
    imported_entries = []

    for entry in entries:
        if entry.get("imported"):
            imported_entries.append(entry)
            continue
        key = (
            entry.get("app", ""),
            entry.get("instance", ""),
            str(entry.get("item_id", "")),
            entry.get("type", ""),
        )
        searched_ts = entry.get("searched_ts") or iso_z(utcnow())
        if key not in groups:
            groups[key] = {
                "title": entry.get("title") or "",
                "first_searched_ts": searched_ts,
                "last_searched_ts": searched_ts,
            }
        else:
            existing = groups[key]
            if searched_ts < existing["first_searched_ts"]:
                existing["first_searched_ts"] = searched_ts
            if searched_ts > existing["last_searched_ts"]:
                existing["last_searched_ts"] = searched_ts

    for (app, instance, item_id, entry_type), data in groups.items():
        conn.execute(
            """
            INSERT OR IGNORE INTO stat_entries
                (app, instance, item_id, title, type,
                 first_searched_ts, last_searched_ts, imported)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (app, instance, item_id, data["title"], entry_type,
             data["first_searched_ts"], data["last_searched_ts"])
        )
        unimported_rows += 1

    for entry in imported_entries:
        searched_ts = entry.get("searched_ts") or iso_z(utcnow())
        conn.execute(
            """
            INSERT INTO stat_entries
                (app, instance, item_id, title, type,
                 first_searched_ts, last_searched_ts, imported, imported_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                entry.get("app", ""),
                entry.get("instance", ""),
                str(entry.get("item_id", "")),
                entry.get("title") or "",
                entry.get("type") or "",
                searched_ts,
                searched_ts,
                entry.get("imported_ts"),
            )
        )
        imported_rows += 1

    lifetime_movies = int(stats.get("lifetime_movies", 0))
    lifetime_shows = int(stats.get("lifetime_shows", 0))
    if lifetime_movies == 0 and lifetime_shows == 0 and imported_entries:
        lifetime_movies = sum(1 for e in imported_entries if e.get("app") == "radarr")
        lifetime_shows = sum(1 for e in imported_entries if e.get("app") == "sonarr")
    conn.execute("UPDATE lifetime_totals SET value = ? WHERE key = 'movies'", (lifetime_movies,))
    conn.execute("UPDATE lifetime_totals SET value = ? WHERE key = 'shows'", (lifetime_shows,))

    print(f"[Migration] stat_entries: {unimported_rows} unimported + {imported_rows} imported rows")


# ── search_history ────────────────────────────────────────────────────

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
) -> None:
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO search_history
            (app, instance_name, instance_url, item_type, item_id,
             title, sweep_type, library_added,
             first_searched_ts, last_searched_ts, search_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        ON CONFLICT (app, instance_name, instance_url, item_type, item_id) DO UPDATE SET
            last_searched_ts = excluded.last_searched_ts,
            search_count     = search_history.search_count + 1,
            title            = CASE WHEN excluded.title != '' THEN excluded.title
                                    ELSE search_history.title END,
            sweep_type       = CASE WHEN excluded.sweep_type != '' THEN excluded.sweep_type
                                    ELSE search_history.sweep_type END,
            library_added    = CASE WHEN excluded.library_added != '' THEN excluded.library_added
                                    ELSE search_history.library_added END
        """,
        (app, instance_name, instance_url, item_type, item_id,
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
        WHERE app = ? AND instance_name = ? AND instance_url = ?
          AND item_type = ? AND item_id = ?
        """,
        (app, instance_name, instance_url, item_type, item_id)
    ).fetchone()
    return row["last_searched_ts"] if row else None


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
        where.append("instance_name = ?")
        params.append(parts[0])
        if len(parts) > 1:
            where.append("instance_url = ?")
            params.append(parts[1])
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    total = conn.execute(
        f"SELECT COUNT(*) FROM search_history {where_sql}", params
    ).fetchone()[0]

    rows = conn.execute(
        f"""
        SELECT app, instance_name, instance_url, item_type, item_id,
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
    from nudgarr.constants import DB_FILE as _DB_FILE
    from nudgarr.state import state_key as make_state_key

    conn = get_connection()
    rows = conn.execute(
        """
        SELECT app, instance_name, instance_url, COUNT(*) as cnt
        FROM search_history
        GROUP BY app, instance_name, instance_url
        """
    ).fetchall()

    per_instance: Dict[str, Dict] = {"radarr": {}, "sonarr": {}}
    radarr_total = 0
    sonarr_total = 0
    for r in rows:
        sk = f"{r['instance_name']}|{r['instance_url']}"
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
        size = os.path.getsize(_DB_FILE)
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


# ── stat_entries ──────────────────────────────────────────────────────

def upsert_stat_entry(
    app: str,
    instance: str,
    item_id: str,
    title: str,
    entry_type: str,
    searched_ts: str,
) -> None:
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO stat_entries
            (app, instance, item_id, title, type,
             first_searched_ts, last_searched_ts, imported)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0)
        ON CONFLICT (app, instance, item_id, type) WHERE imported = 0 DO UPDATE SET
            last_searched_ts = excluded.last_searched_ts,
            title = CASE WHEN excluded.title != '' THEN excluded.title
                         ELSE stat_entries.title END
        """,
        (app, instance, item_id, title, entry_type, searched_ts, searched_ts)
    )
    conn.commit()


def confirm_stat_entry(
    app: str,
    instance: str,
    item_id: str,
    entry_type: str,
    imported_ts: str,
) -> bool:
    conn = get_connection()

    # Check for an existing imported row for this item (any type).
    # If one exists we update it in place — one row per item, badge reflects
    # the most recent event, iteration increments when the same type repeats.
    existing = conn.execute(
        """
        SELECT id, type, iteration FROM stat_entries
        WHERE app = ? AND instance = ? AND item_id = ? AND imported = 1
        """,
        (app, instance, item_id)
    ).fetchone()

    if existing:
        new_iteration = (existing["iteration"] + 1) if existing["type"] == entry_type else 1
        conn.execute(
            """
            UPDATE stat_entries
            SET type = ?, imported_ts = ?, iteration = ?
            WHERE id = ?
            """,
            (entry_type, imported_ts, new_iteration, existing["id"])
        )
        # Remove the now-confirmed pending row
        conn.execute(
            """
            DELETE FROM stat_entries
            WHERE app = ? AND instance = ? AND item_id = ? AND type = ? AND imported = 0
            """,
            (app, instance, item_id, entry_type)
        )
        conn.commit()
        return True

    # No prior imported row — mark the pending row as imported
    cur = conn.execute(
        """
        UPDATE stat_entries
        SET imported = 1, imported_ts = ?, iteration = 1
        WHERE app = ? AND instance = ? AND item_id = ? AND type = ? AND imported = 0
        """,
        (imported_ts, app, instance, item_id, entry_type)
    )
    conn.commit()
    return cur.rowcount > 0


def get_unconfirmed_entries(check_minutes: int, now_ts: str) -> List[Dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM stat_entries WHERE imported = 0"
    ).fetchall()
    if check_minutes == 0:
        return [dict(r) for r in rows]
    now_dt = parse_iso(now_ts)
    result = []
    for r in rows:
        dt = parse_iso(r["last_searched_ts"])
        if dt is None:
            continue
        if now_dt and (now_dt - dt).total_seconds() / 60 >= check_minutes:
            result.append(dict(r))
    return result


def get_confirmed_entries(
    instance_filter: str = "",
    type_filter: str = "",
    offset: int = 0,
    limit: int = 25,
) -> Tuple[int, List[Dict], List[str]]:
    conn = get_connection()
    where = ["imported = 1"]
    params: list = []
    if instance_filter:
        where.append("instance = ?")
        params.append(instance_filter)
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
    # Round to nearest minute (30s threshold)
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


def clear_stat_entries() -> None:
    conn = get_connection()
    conn.execute("DELETE FROM stat_entries")
    conn.commit()


def prune_stat_entries(retention_days: int) -> int:
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


# ── exclusions ────────────────────────────────────────────────────────

def get_exclusions() -> List[Dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT title, excluded_at FROM exclusions ORDER BY excluded_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def add_exclusion(title: str) -> int:
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO exclusions (title, excluded_at) VALUES (?, ?)",
        (title.strip(), iso_z(utcnow()))
    )
    conn.commit()
    return conn.execute("SELECT COUNT(*) FROM exclusions").fetchone()[0]


def remove_exclusion(title: str) -> int:
    conn = get_connection()
    conn.execute(
        "DELETE FROM exclusions WHERE title = ? COLLATE NOCASE",
        (title.strip(),)
    )
    conn.commit()
    return conn.execute("SELECT COUNT(*) FROM exclusions").fetchone()[0]


# ── sweep_lifetime ────────────────────────────────────────────────────

def upsert_sweep_lifetime(
    instance_key: str,
    runs_delta: int = 0,
    eligible_delta: int = 0,
    skipped_delta: int = 0,
    searched_delta: int = 0,
    last_run_utc: Optional[str] = None,
) -> None:
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
    conn = get_connection()
    rows = conn.execute("SELECT * FROM sweep_lifetime").fetchall()
    return {r["instance_key"]: dict(r) for r in rows}


def get_sweep_lifetime_row(instance_key: str) -> Optional[Dict]:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM sweep_lifetime WHERE instance_key = ?", (instance_key,)
    ).fetchone()
    return dict(row) if row else None


# ── lifetime_totals ───────────────────────────────────────────────────

def increment_lifetime_total(key: str, delta: int = 1) -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE lifetime_totals SET value = value + ? WHERE key = ?",
        (delta, key)
    )
    conn.commit()


def get_lifetime_totals() -> Dict[str, int]:
    conn = get_connection()
    rows = conn.execute("SELECT key, value FROM lifetime_totals").fetchall()
    result = {"movies": 0, "shows": 0}
    for r in rows:
        result[r["key"]] = r["value"]
    return result


# ── backup export ─────────────────────────────────────────────────────

def export_as_json_dict() -> Dict[str, Any]:
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

"""
nudgarr/db/connection.py

Thread-local SQLite connection management, schema definition, and
database initialisation.

  get_connection()   -- return a thread-local connection, opening it if needed
  close_connection() -- close the thread-local connection (call on thread exit)
  init_db()          -- create schema; call once at startup

Imports from within the package: constants, utils only.
"""

import logging
import os
import sqlite3
import threading

from nudgarr.constants import DB_FILE
from nudgarr.utils import iso_z, utcnow  # noqa: F401 — re-used by sibling modules

logger = logging.getLogger(__name__)

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
    series_id         TEXT NOT NULL DEFAULT '',
    title             TEXT NOT NULL DEFAULT '',
    sweep_type        TEXT NOT NULL DEFAULT '',
    library_added     TEXT NOT NULL DEFAULT '',
    first_searched_ts TEXT NOT NULL,
    last_searched_ts  TEXT NOT NULL,
    search_count      INTEGER NOT NULL DEFAULT 1,
    UNIQUE (app, instance_url, item_type, item_id)
);
CREATE INDEX IF NOT EXISTS idx_sh_lookup
    ON search_history (app, instance_url, item_type, item_id);
CREATE INDEX IF NOT EXISTS idx_sh_last_searched
    ON search_history (last_searched_ts);

CREATE TABLE IF NOT EXISTS stat_entries (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    app               TEXT NOT NULL,
    instance          TEXT NOT NULL,
    instance_url      TEXT NOT NULL DEFAULT '',
    item_id           TEXT NOT NULL,
    title             TEXT NOT NULL DEFAULT '',
    type              TEXT NOT NULL DEFAULT '',
    iteration         INTEGER NOT NULL DEFAULT 1,
    first_searched_ts TEXT NOT NULL,
    last_searched_ts  TEXT NOT NULL,
    imported          INTEGER NOT NULL DEFAULT 0,
    imported_ts       TEXT,
    quality_from      TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_stat_entries_active
    ON stat_entries (app, instance, item_id, type) WHERE imported = 0;
CREATE UNIQUE INDEX IF NOT EXISTS uq_stat_entries_confirmed
    ON stat_entries (app, instance, item_id) WHERE imported = 1;
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

CREATE TABLE IF NOT EXISTS nudgarr_state (
    key    TEXT NOT NULL PRIMARY KEY,
    value  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quality_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id     INTEGER NOT NULL REFERENCES stat_entries(id) ON DELETE CASCADE,
    quality_from TEXT,
    quality_to   TEXT NOT NULL,
    imported_ts  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_qh_entry_id ON quality_history (entry_id);
"""


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA_SQL)
    conn.commit()


# ── Init ──────────────────────────────────────────────────────────────

def init_db() -> None:
    """
    Create schema if not present.  Safe to call on every startup —
    all CREATE statements use IF NOT EXISTS.
    Called once at application startup.
    """
    conn = get_connection()
    _create_schema(conn)
    _run_migration_v7(conn)
    _run_migration_v8(conn)


def _run_migration_v7(conn: sqlite3.Connection) -> None:
    """Add series_id column to search_history for Sonarr title link resolution.

    NOTE: This migration was added during the v4.0.0 nightly cycle after the
    schema reset, so it cannot be folded into _SCHEMA_SQL. It handles all
    existing installs including v3.2.0 upgrades. Future columns added before
    a major version boundary should follow the same pattern.
    """
    existing = conn.execute(
        "SELECT version FROM schema_migrations WHERE version = 7"
    ).fetchone()
    if existing:
        return
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(search_history)").fetchall()]
        if "series_id" not in cols:
            conn.execute(
                "ALTER TABLE search_history ADD COLUMN series_id TEXT NOT NULL DEFAULT ''"
            )
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (7, ?)",
            (iso_z(utcnow()),)
        )
        conn.commit()
        logger.info("[Migration v7] Added series_id to search_history")
    except Exception as exc:
        logger.exception("[Migration v7] FAILED")


def _run_migration_v8(conn: sqlite3.Connection) -> None:
    """Create quality_history table for per-import upgrade tracking.

    Each confirmed import event gets a row recording quality_from and quality_to,
    enabling the full upgrade path to be displayed in the Imports tab tooltip.
    ON DELETE CASCADE means rows are automatically removed when the parent
    stat_entries row is deleted — clear and prune require no changes.
    Covers upgrades from v3.2.x. Fresh installs get the table via _SCHEMA_SQL.

    NOTE: quality_history is also defined in _SCHEMA_SQL for fresh installs.
    It must also appear here because upgrades from v3.2.x do not have the table.
    Both paths are required — this is not accidental duplication.
    Future columns added to quality_history before a major version boundary
    must be added to _SCHEMA_SQL AND a new migration function.
    """
    existing = conn.execute(
        "SELECT version FROM schema_migrations WHERE version = 8"
    ).fetchone()
    if existing:
        return
    try:
        # Add quality_from to stat_entries for temporary storage between sweep
        # and import confirmation. The value moves to quality_history on confirm
        # and is never retained on the confirmed row.
        cols = [r[1] for r in conn.execute("PRAGMA table_info(stat_entries)").fetchall()]
        if "quality_from" not in cols:
            conn.execute("ALTER TABLE stat_entries ADD COLUMN quality_from TEXT")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS quality_history (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_id     INTEGER NOT NULL REFERENCES stat_entries(id) ON DELETE CASCADE,
                quality_from TEXT,
                quality_to   TEXT NOT NULL,
                imported_ts  TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_qh_entry_id ON quality_history (entry_id)"
        )
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (8, ?)",
            (iso_z(utcnow()),)
        )
        conn.commit()
        logger.info("[Migration v8] Created quality_history table")
    except Exception as exc:
        logger.exception("[Migration v8] FAILED")

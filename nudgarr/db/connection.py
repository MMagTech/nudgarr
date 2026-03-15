"""
nudgarr/db/connection.py

Thread-local SQLite connection management, schema definition, and
database initialisation.

  get_connection()   -- return a thread-local connection, opening it if needed
  close_connection() -- close the thread-local connection (call on thread exit)
  init_db()          -- create schema; call once at startup

Imports from within the package: constants, utils only.
"""

import os
import sqlite3
import threading

from nudgarr.constants import DB_FILE
from nudgarr.utils import iso_z, utcnow  # noqa: F401 — re-used by sibling modules

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
    imported_ts       TEXT
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

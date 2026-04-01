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
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    excluded_at  TEXT NOT NULL,
    source       TEXT NOT NULL DEFAULT 'manual',
    search_count INTEGER NOT NULL DEFAULT 0,
    acknowledged INTEGER NOT NULL DEFAULT 1
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

CREATE TABLE IF NOT EXISTS exclusion_events (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    title                 TEXT NOT NULL COLLATE NOCASE,
    event_type            TEXT NOT NULL,
    source                TEXT NOT NULL,
    search_count_at_event INTEGER NOT NULL DEFAULT 0,
    event_ts              TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ee_title
    ON exclusion_events (title);
CREATE INDEX IF NOT EXISTS idx_ee_event_ts
    ON exclusion_events (event_ts);
CREATE INDEX IF NOT EXISTS idx_ee_type_source
    ON exclusion_events (event_type, source);

CREATE TABLE IF NOT EXISTS intel_aggregate (
    id                          INTEGER PRIMARY KEY CHECK (id = 1),
    success_total_imported      INTEGER NOT NULL DEFAULT 0,
    success_total_worked        INTEGER NOT NULL DEFAULT 0,
    turnaround_sum_days         REAL    NOT NULL DEFAULT 0.0,
    turnaround_count            INTEGER NOT NULL DEFAULT 0,
    searches_per_import_sum     INTEGER NOT NULL DEFAULT 0,
    searches_per_import_count   INTEGER NOT NULL DEFAULT 0,
    cutoff_import_count         INTEGER NOT NULL DEFAULT 0,
    backlog_import_count        INTEGER NOT NULL DEFAULT 0,
    cf_score_import_count       INTEGER NOT NULL DEFAULT 0,
    quality_upgrades_count      INTEGER NOT NULL DEFAULT 0,
    imported_once_count         INTEGER NOT NULL DEFAULT 0,
    upgraded_count              INTEGER NOT NULL DEFAULT 0,
    per_instance_imports        TEXT    NOT NULL DEFAULT '{}',
    per_instance_turnaround     TEXT    NOT NULL DEFAULT '{}',
    library_age_buckets         TEXT    NOT NULL DEFAULT '{}',
    calibration_later_imported  INTEGER NOT NULL DEFAULT 0
);
INSERT OR IGNORE INTO intel_aggregate (id) VALUES (1);

CREATE TABLE IF NOT EXISTS cf_score_entries (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    arr_instance_id     TEXT    NOT NULL,
    item_type           TEXT    NOT NULL,
    external_item_id    INTEGER NOT NULL,
    series_id           INTEGER NOT NULL DEFAULT 0,
    file_id             INTEGER NOT NULL DEFAULT 0,
    title               TEXT    NOT NULL DEFAULT '',
    current_score       INTEGER NOT NULL DEFAULT 0,
    cutoff_score        INTEGER NOT NULL DEFAULT 0,
    quality_profile_id  INTEGER NOT NULL DEFAULT 0,
    quality_profile_name TEXT   NOT NULL DEFAULT '',
    added_date          TEXT    NOT NULL DEFAULT '',
    tag_ids             TEXT    NOT NULL DEFAULT '[]',
    is_monitored        INTEGER NOT NULL DEFAULT 1,
    last_synced_at      TEXT    NOT NULL DEFAULT '',
    UNIQUE (arr_instance_id, item_type, external_item_id)
);
CREATE INDEX IF NOT EXISTS idx_cf_instance_type
    ON cf_score_entries (arr_instance_id, item_type);
CREATE INDEX IF NOT EXISTS idx_cf_below_cutoff
    ON cf_score_entries (arr_instance_id, current_score, cutoff_score)
    WHERE current_score < cutoff_score;
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
    _run_migration_v9(conn)
    _run_migration_v10(conn)
    _run_migration_v11(conn)
    _run_migration_v12(conn)


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
    except Exception:
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
    except Exception:
        logger.exception("[Migration v8] FAILED")


def _run_migration_v9(conn: sqlite3.Connection) -> None:
    """Add source, search_count, and acknowledged columns to the exclusions table.

    source       -- 'manual' for user-added exclusions, 'auto' for auto-excluded titles.
                    Existing rows default to 'manual' since all prior exclusions were
                    added by the user.
    search_count -- Number of searches that triggered the auto-exclusion. 0 for manual
                    entries. Stored for display in the Exclusions tab.
    acknowledged -- Whether the user has seen this auto-exclusion via the status bar
                    badge. Defaults to 1 (acknowledged) for existing rows so the badge
                    only fires for newly auto-excluded titles going forward.

    Fresh installs get these columns via _SCHEMA_SQL. This migration handles all
    existing installs including v4.0.x upgrades.
    """
    existing = conn.execute(
        "SELECT version FROM schema_migrations WHERE version = 9"
    ).fetchone()
    if existing:
        return
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(exclusions)").fetchall()]
        if "source" not in cols:
            conn.execute(
                "ALTER TABLE exclusions ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'"
            )
        if "search_count" not in cols:
            conn.execute(
                "ALTER TABLE exclusions ADD COLUMN search_count INTEGER NOT NULL DEFAULT 0"
            )
        if "acknowledged" not in cols:
            conn.execute(
                "ALTER TABLE exclusions ADD COLUMN acknowledged INTEGER NOT NULL DEFAULT 1"
            )
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (9, ?)",
            (iso_z(utcnow()),)
        )
        conn.commit()
        logger.info("[Migration v9] Added source, search_count, acknowledged to exclusions")
    except Exception:
        logger.exception("[Migration v9] FAILED")


def _run_migration_v10(conn: sqlite3.Connection) -> None:
    """Create exclusion_events and intel_aggregate tables for the Intel tab.

    exclusion_events -- append-only audit log of every exclude and unexclude
    action. Captures title, event type (excluded/unexcluded), source
    (manual/auto), search_count at the moment of the event, and a timestamp.
    Never cleared by Clear History or Clear Stats. Only Reset Intel removes rows.

    intel_aggregate -- single-row accumulator protected from all clear and prune
    operations. Stores lifetime Intel metrics as dedicated typed columns.
    The CHECK (id = 1) constraint enforces exactly one row at all times.
    Seeded with a single zero row on creation via INSERT OR IGNORE.

    Both tables are also defined in _SCHEMA_SQL for fresh installs. This
    migration handles all existing installs on v4.1.x and above upgrading
    to v4.2.0. This is not accidental duplication -- both paths are required.
    """
    existing = conn.execute(
        "SELECT version FROM schema_migrations WHERE version = 10"
    ).fetchone()
    if existing:
        return
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS exclusion_events (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                title                 TEXT NOT NULL COLLATE NOCASE,
                event_type            TEXT NOT NULL,
                source                TEXT NOT NULL,
                search_count_at_event INTEGER NOT NULL DEFAULT 0,
                event_ts              TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_ee_title
                ON exclusion_events (title);
            CREATE INDEX IF NOT EXISTS idx_ee_event_ts
                ON exclusion_events (event_ts);
            CREATE INDEX IF NOT EXISTS idx_ee_type_source
                ON exclusion_events (event_type, source);

            CREATE TABLE IF NOT EXISTS intel_aggregate (
                id                          INTEGER PRIMARY KEY CHECK (id = 1),
                success_total_imported      INTEGER NOT NULL DEFAULT 0,
                success_total_worked        INTEGER NOT NULL DEFAULT 0,
                turnaround_sum_days         REAL    NOT NULL DEFAULT 0.0,
                turnaround_count            INTEGER NOT NULL DEFAULT 0,
                searches_per_import_sum     INTEGER NOT NULL DEFAULT 0,
                searches_per_import_count   INTEGER NOT NULL DEFAULT 0,
                cutoff_import_count         INTEGER NOT NULL DEFAULT 0,
                backlog_import_count        INTEGER NOT NULL DEFAULT 0,
                cf_score_import_count       INTEGER NOT NULL DEFAULT 0,
                quality_upgrades_count      INTEGER NOT NULL DEFAULT 0,
                imported_once_count         INTEGER NOT NULL DEFAULT 0,
                upgraded_count              INTEGER NOT NULL DEFAULT 0,
                per_instance_imports        TEXT    NOT NULL DEFAULT '{}',
                per_instance_turnaround     TEXT    NOT NULL DEFAULT '{}',
                library_age_buckets         TEXT    NOT NULL DEFAULT '{}',
                calibration_later_imported  INTEGER NOT NULL DEFAULT 0
            );
            INSERT OR IGNORE INTO intel_aggregate (id) VALUES (1);
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (10, ?)",
            (iso_z(utcnow()),)
        )
        conn.commit()
        logger.info("[Migration v10] Created exclusion_events and intel_aggregate tables")
    except Exception:
        logger.exception("[Migration v10] FAILED")


def _run_migration_v11(conn: sqlite3.Connection) -> None:
    """Create the cf_score_entries table for existing installs upgrading to v4.2.0.

    cf_score_entries is the persistent index written by CustomFormatScoreSyncer
    and read by the sweep's CF Score pass.  One row per monitored item where
    customFormatScore is below the quality profile's cutoffFormatScore and the
    gap meets the profile's minUpgradeFormatScore threshold.

    The table is also defined in _SCHEMA_SQL for fresh installs — both paths
    are required and the duplication is intentional.  Installs on v4.1.x and
    earlier will not have the table until this migration runs.

    Indexes:
      idx_cf_instance_type  -- fast lookup by instance and item type (sweep)
      idx_cf_below_cutoff   -- partial index on below-cutoff rows (UI query)
    """
    existing = conn.execute(
        "SELECT version FROM schema_migrations WHERE version = 11"
    ).fetchone()
    if existing:
        return
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS cf_score_entries (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                arr_instance_id      TEXT    NOT NULL,
                item_type            TEXT    NOT NULL,
                external_item_id     INTEGER NOT NULL,
                series_id            INTEGER NOT NULL DEFAULT 0,
                file_id              INTEGER NOT NULL DEFAULT 0,
                title                TEXT    NOT NULL DEFAULT '',
                current_score        INTEGER NOT NULL DEFAULT 0,
                cutoff_score         INTEGER NOT NULL DEFAULT 0,
                quality_profile_id   INTEGER NOT NULL DEFAULT 0,
                quality_profile_name TEXT    NOT NULL DEFAULT '',
                added_date           TEXT    NOT NULL DEFAULT '',
                tag_ids              TEXT    NOT NULL DEFAULT '[]',
                is_monitored         INTEGER NOT NULL DEFAULT 1,
                last_synced_at       TEXT    NOT NULL DEFAULT '',
                UNIQUE (arr_instance_id, item_type, external_item_id)
            );
            CREATE INDEX IF NOT EXISTS idx_cf_instance_type
                ON cf_score_entries (arr_instance_id, item_type);
            CREATE INDEX IF NOT EXISTS idx_cf_below_cutoff
                ON cf_score_entries (arr_instance_id, current_score, cutoff_score)
                WHERE current_score < cutoff_score;
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (11, ?)",
            (iso_z(utcnow()),)
        )
        conn.commit()
        logger.info("[Migration v11] Created cf_score_entries table and indexes")
    except Exception:
        logger.exception("[Migration v11] FAILED")


def _run_migration_v12(conn: sqlite3.Connection) -> None:
    """Add cf_score_import_count to intel_aggregate for existing v4.2.0 installs.

    This column was added to track confirmed imports that originated from the
    CF Score Scan pipeline, completing the three-way import split in the Intel
    tab (Cutoff Unmet, Backlog, CF Score).

    Fresh installs get the column via _SCHEMA_SQL.  Installs that already ran
    migration v10 or v11 will not have it until this migration runs.
    """
    existing = conn.execute(
        "SELECT version FROM schema_migrations WHERE version = 12"
    ).fetchone()
    if existing:
        return
    # Fresh installs already have this column via _SCHEMA_SQL.  Only ALTER if
    # the column is genuinely absent so we never hit a duplicate column error.
    cols = [
        row[1]
        for row in conn.execute(
            "PRAGMA table_info(intel_aggregate)"
        ).fetchall()
    ]
    if "cf_score_import_count" not in cols:
        conn.execute(
            "ALTER TABLE intel_aggregate ADD COLUMN"
            " cf_score_import_count INTEGER NOT NULL DEFAULT 0"
        )
        logger.info("[Migration v12] Added cf_score_import_count to intel_aggregate")
    else:
        logger.info(
            "[Migration v12] cf_score_import_count already present, skipping ALTER"
        )
    # Always write the migration record so this never re-runs.
    conn.execute(
        "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (12, ?)",
        (iso_z(utcnow()),)
    )
    conn.commit()

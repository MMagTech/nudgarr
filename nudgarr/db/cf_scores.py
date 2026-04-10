"""
nudgarr/db/cf_scores.py

Database operations for the cf_score_entries table.

The cf_score_entries table is the persistent index built by
CustomFormatScoreSyncer.  It stores one row per monitored item (movie or
episode) where:
  - qualityCutoffNotMet is False (quality tier is already satisfied)
  - customFormatScore < cutoffFormatScore from the quality profile
  - gap (cutoff_score - current_score) >= minUpgradeFormatScore from the
    quality profile (enforced at write time so no ineligible item ever
    enters the table)

The syncer writes and prunes this table on its own schedule entirely
independently of the sweep.  The sweep pipeline reads from it (worst gap
first) to decide what to search each run.

No business logic lives here -- pure persistence only.

Public functions:
  upsert_cf_score_entry         -- insert or update a single entry
  touch_cf_score_entry          -- bump last_synced_at without changing scores
  delete_cf_score_entry         -- remove a single entry (score met / gone)
  delete_cf_scores_for_instance -- remove all entries for a deleted instance
  prune_stale_cf_scores         -- remove entries not updated in this sync run
  get_cf_score_entries          -- list entries for the UI table
  get_cf_score_stats            -- aggregate counts for stat cards
  get_cf_score_instance_stats   -- per-instance coverage for UI rings
  get_cf_max_last_synced_at_for_instance -- MAX(last_synced_at) before prune
  get_cf_scores_for_sweep       -- worst-gap-first items for the sweep pipeline
  batch_upsert_cf_scores        -- bulk insert/update, 200 rows per DB batch
  clear_cf_score_index          -- truncate the table (Reset CF Index)
"""

import logging
from typing import Any, Dict, List, Optional, Set

from nudgarr.cf_effective import CF_LAST_INSTANCE_SYNC_PREFIX, CF_SCAN_SNAPSHOT_PREFIX
from nudgarr.db.appstate import delete_states_with_prefix
from nudgarr.db.connection import get_connection
from nudgarr.utils import iso_z, utcnow

logger = logging.getLogger(__name__)

# Same prefix as cf_score_syncer.CF_SYNC_PROGRESS_PREFIX — clears per-instance ring state.
_CF_SYNC_STATE_PREFIX = "cf_sync_progress|"


def _upsert_cf_score_entry(
    arr_instance_id: str,
    item_type: str,
    external_item_id: int,
    series_id: int,
    file_id: int,
    title: str,
    current_score: int,
    cutoff_score: int,
    quality_profile_id: int,
    quality_profile_name: str,
    is_monitored: int = 1,
    added_date: str = "",
) -> None:
    """Insert or update a single CF score entry.

    Uses ON CONFLICT DO UPDATE semantics -- if a row with the same
    (arr_instance_id, item_type, external_item_id) already exists it is
    updated in place.  last_synced_at is always set to the current time so
    the prune step can identify entries that were not visited in this sync run.

    Args:
        arr_instance_id:      Composite instance key, e.g. 'radarr|http://host:7878'
        item_type:            'movie' for Radarr items, 'episode' for Sonarr items
        external_item_id:     Radarr movie ID or Sonarr episode ID
        series_id:            Sonarr series ID; 0 for Radarr entries
        file_id:              Radarr movieFileId or Sonarr episodeFileId
        title:                Human-readable title for UI display
        current_score:        Current customFormatScore on the existing file
        cutoff_score:         cutoffFormatScore from the quality profile
        quality_profile_id:   Quality profile database ID from Radarr/Sonarr
        quality_profile_name: Quality profile display name for UI
        is_monitored:         1 if the item is monitored, 0 otherwise
        added_date:           ISO timestamp when the item was added to Radarr
    """
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO cf_score_entries (
            arr_instance_id, item_type, external_item_id, series_id,
            file_id, title, current_score, cutoff_score,
            quality_profile_id, quality_profile_name,
            is_monitored, added_date, last_synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (arr_instance_id, item_type, external_item_id)
        DO UPDATE SET
            series_id            = excluded.series_id,
            file_id              = excluded.file_id,
            title                = excluded.title,
            current_score        = excluded.current_score,
            cutoff_score         = excluded.cutoff_score,
            quality_profile_id   = excluded.quality_profile_id,
            quality_profile_name = excluded.quality_profile_name,
            is_monitored         = excluded.is_monitored,
            added_date           = CASE WHEN excluded.added_date != ''
                                        THEN excluded.added_date
                                        ELSE cf_score_entries.added_date END,
            last_synced_at       = excluded.last_synced_at
        """,
        (
            arr_instance_id, item_type, external_item_id, series_id,
            file_id, title, current_score, cutoff_score,
            quality_profile_id, quality_profile_name,
            is_monitored, added_date, iso_z(utcnow()),
        ),
    )
    conn.commit()


def _touch_cf_score_entry(
    arr_instance_id: str,
    item_type: str,
    external_item_id: int,
) -> None:
    """Bump last_synced_at on an existing entry without changing score data.

    Used for items that exist in the library but currently have no file
    (e.g. actively downloading).  Touching the timestamp protects the entry
    from the prune step which removes anything not visited in the current
    sync run.

    Args:
        arr_instance_id:   Composite instance key
        item_type:         'movie' or 'episode'
        external_item_id:  Radarr movie ID or Sonarr episode ID
    """
    conn = get_connection()
    conn.execute(
        """
        UPDATE cf_score_entries
        SET last_synced_at = ?
        WHERE arr_instance_id = ? AND item_type = ? AND external_item_id = ?
        """,
        (iso_z(utcnow()), arr_instance_id, item_type, external_item_id),
    )
    conn.commit()


def _delete_cf_score_entry(
    arr_instance_id: str,
    item_type: str,
    external_item_id: int,
) -> None:
    """Remove a single entry from the index.

    Called by the syncer when the score is now at or above cutoff (no longer
    needs searching) or when the item is no longer monitored.

    Args:
        arr_instance_id:   Composite instance key
        item_type:         'movie' or 'episode'
        external_item_id:  Radarr movie ID or Sonarr episode ID
    """
    conn = get_connection()
    conn.execute(
        """
        DELETE FROM cf_score_entries
        WHERE arr_instance_id = ? AND item_type = ? AND external_item_id = ?
        """,
        (arr_instance_id, item_type, external_item_id),
    )
    conn.commit()


def prune_cf_scores_not_in_allowed_instances(allowed_ids: Set[str]) -> int:
    """Remove index rows for instances that are not in the allowed set.

    Used at CF sync start: drops disabled, removed, or renamed instances.
    If allowed_ids is empty, deletes all rows (nothing should remain indexed).
    """
    conn = get_connection()
    if not allowed_ids:
        cur = conn.execute("DELETE FROM cf_score_entries")
        n = cur.rowcount
        conn.commit()
        if n:
            logger.info("[CF Scores] Pruned all %d entries (no allowed instances)", n)
        return n
    placeholders = ",".join("?" * len(allowed_ids))
    cur = conn.execute(
        f"DELETE FROM cf_score_entries WHERE arr_instance_id NOT IN ({placeholders})",
        tuple(allowed_ids),
    )
    conn.commit()
    removed = cur.rowcount
    if removed:
        logger.info("[CF Scores] Pruned %d entries not in allowed instance set", removed)
    return removed


def delete_cf_scores_for_instance(arr_instance_id: str) -> int:
    """Remove all CF score entries for a given instance.

    Called when an instance is deleted from Nudgarr configuration so no
    orphaned entries remain for an instance that no longer exists.

    Args:
        arr_instance_id: Composite instance key to purge

    Returns:
        Number of rows removed
    """
    conn = get_connection()
    cur = conn.execute(
        "DELETE FROM cf_score_entries WHERE arr_instance_id = ?",
        (arr_instance_id,),
    )
    conn.commit()
    removed = cur.rowcount
    if removed:
        logger.info(
            "[CF Scores] Removed %d entries for deleted instance %s",
            removed, arr_instance_id,
        )
    return removed


def prune_stale_cf_scores(arr_instance_id: str, sync_started_at: str) -> int:
    """Delete entries for an instance that were not touched in the current sync run.

    At the end of each sync, any entry whose last_synced_at is older than
    sync_started_at no longer exists in the library (deleted, unmonitored, or
    otherwise gone) and should be removed.  Entries for items that are actively
    downloading are protected by touch_cf_score_entry before this runs.

    Args:
        arr_instance_id:  Composite instance key
        sync_started_at:  ISO-Z timestamp recorded at the start of this sync run

    Returns:
        Number of stale entries removed
    """
    conn = get_connection()
    cur = conn.execute(
        """
        DELETE FROM cf_score_entries
        WHERE arr_instance_id = ? AND last_synced_at < ?
        """,
        (arr_instance_id, sync_started_at),
    )
    conn.commit()
    return cur.rowcount


def get_cf_score_entries(
    arr_instance_id: Optional[str] = None,
    item_type: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """Fetch CF score entries for the UI table, ordered worst gap first.

    Only returns entries where current_score < cutoff_score.  Optionally
    filtered by instance and/or item type for the All/Radarr/Sonarr filter
    buttons on the CF Score tab.

    Args:
        arr_instance_id: Filter to a specific instance (None = all instances)
        item_type:       Filter to 'movie' or 'episode' (None = both)
        limit:           Maximum rows to return; 0 or None means no limit
        offset:          Row offset for pagination

    Returns:
        List of row dicts ordered by gap descending (worst gap first)
    """
    conn = get_connection()
    clauses = ["current_score < cutoff_score", "is_monitored = 1"]
    params: List[Any] = []

    if arr_instance_id:
        clauses.append("arr_instance_id = ?")
        params.append(arr_instance_id)
    if item_type:
        clauses.append("item_type = ?")
        params.append(item_type)

    where = " AND ".join(clauses)

    if limit and limit > 0:
        params.extend([limit, offset])
        limit_clause = "LIMIT ? OFFSET ?"
    else:
        params.append(offset)
        limit_clause = "LIMIT -1 OFFSET ?"

    rows = conn.execute(
        f"""
        SELECT *,
               (cutoff_score - current_score) AS gap
        FROM cf_score_entries
        WHERE {where}
        ORDER BY gap DESC, title ASC
        {limit_clause}
        """,
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def get_cf_score_stats(allowed_instance_ids: Optional[Set[str]] = None) -> Dict[str, int]:
    """Return aggregate counts for the CF Score tab stat cards.

    Returns a dict with:
      total_indexed:  Total monitored items in the index
      below_cutoff:   Items where current_score < cutoff_score
      passing:        total_indexed - below_cutoff

    When allowed_instance_ids is set, only rows with arr_instance_id in that set
    are counted (v5.0.0 — excludes per-app / per-instance disabled instances).
    """
    conn = get_connection()
    if allowed_instance_ids is not None and len(allowed_instance_ids) == 0:
        return {"total_indexed": 0, "below_cutoff": 0, "passing": 0}
    extra = ""
    params: tuple = ()
    if allowed_instance_ids is not None:
        ph = ",".join("?" * len(allowed_instance_ids))
        extra = f" AND arr_instance_id IN ({ph})"
        params = tuple(allowed_instance_ids)
    row = conn.execute(
        f"""
        SELECT
            COUNT(*) AS total_indexed,
            SUM(CASE WHEN current_score < cutoff_score THEN 1 ELSE 0 END)
                AS below_cutoff
        FROM cf_score_entries
        WHERE is_monitored = 1{extra}
        """,
        params,
    ).fetchone()
    if not row:
        return {"total_indexed": 0, "below_cutoff": 0, "passing": 0}
    total = row["total_indexed"] or 0
    below = row["below_cutoff"] or 0
    return {
        "total_indexed": total,
        "below_cutoff": below,
        "passing": total - below,
    }


def get_cf_score_instance_stats(allowed_instance_ids: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
    """Return per-instance stats for the Sync Coverage rings in the UI.

    Each dict in the returned list corresponds to one distinct
    arr_instance_id with:
      arr_instance_id: The composite instance key
      total_indexed:   Total monitored entries for this instance
      below_cutoff:    Entries below cutoff for this instance
      last_synced_at:  Most recent last_synced_at for this instance

    When allowed_instance_ids is set, only those instance IDs are included.
    """
    conn = get_connection()
    if allowed_instance_ids is not None and len(allowed_instance_ids) == 0:
        return []
    extra = ""
    params: tuple = ()
    if allowed_instance_ids is not None:
        ph = ",".join("?" * len(allowed_instance_ids))
        extra = f" AND arr_instance_id IN ({ph})"
        params = tuple(allowed_instance_ids)
    rows = conn.execute(
        f"""
        SELECT
            arr_instance_id,
            COUNT(*) AS total_indexed,
            SUM(CASE WHEN current_score < cutoff_score THEN 1 ELSE 0 END)
                AS below_cutoff,
            MAX(last_synced_at) AS last_synced_at
        FROM cf_score_entries
        WHERE is_monitored = 1{extra}
        GROUP BY arr_instance_id
        """,
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def get_cf_max_last_synced_at_for_instance(arr_instance_id: str) -> Optional[str]:
    """Return MAX(last_synced_at) for an instance, or None if no rows."""
    conn = get_connection()
    row = conn.execute(
        """
        SELECT MAX(last_synced_at) AS m
        FROM cf_score_entries
        WHERE arr_instance_id = ?
        """,
        (arr_instance_id,),
    ).fetchone()
    if not row or not row["m"]:
        return None
    return str(row["m"])


def get_cf_scores_for_sweep(
    arr_instance_id: str,
    item_type: str,
) -> List[Dict[str, Any]]:
    """Return all eligible CF Score candidates for a sweep run, worst gap first.

    Returns every monitored item where current_score < cutoff_score for the
    given instance and type.  No limit is applied here -- the caller applies
    exclusion, queue, and cooldown filters in Python before capping at the
    configured per-run limit, consistent with how the Cutoff Unmet and Backlog
    pipelines handle their respective filter chains.

    CF Score Scan is independent of the quality tier pipeline -- items appear
    here based solely on their CF score vs the profile cutoff score, regardless
    of qualityCutoffNotMet status.

    Args:
        arr_instance_id:  Composite instance key, e.g. 'radarr|http://host:7878'
        item_type:        'movie' for Radarr, 'episode' for Sonarr

    Returns:
        List of row dicts ordered by (cutoff_score - current_score) DESC
    """
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT *,
               (cutoff_score - current_score) AS gap
        FROM cf_score_entries
        WHERE arr_instance_id = ?
          AND item_type = ?
          AND current_score < cutoff_score
          AND is_monitored = 1
        ORDER BY gap DESC
        """,
        (arr_instance_id, item_type),
    ).fetchall()
    return [dict(r) for r in rows]


def batch_upsert_cf_scores(entries: List[Dict[str, Any]]) -> None:
    """Bulk insert or update CF score entries, 200 rows per DB transaction.

    Each dict in entries must contain all columns required by the table.
    last_synced_at is set to the current time for every row in the batch
    regardless of the value in the dict -- callers do not need to manage it.

    Batching at 200 rows balances write throughput with transaction size.
    The Radarr API batch size (100 file IDs per request) is a separate,
    unrelated limit that callers manage independently.

    Args:
        entries: List of entry dicts.  Required keys: arr_instance_id,
                 item_type, external_item_id, series_id, file_id, title,
                 current_score, cutoff_score, quality_profile_id,
                 quality_profile_name, is_monitored
    """
    if not entries:
        return

    conn = get_connection()
    now = iso_z(utcnow())
    batch_size = 200

    # Ensure WAL checkpoint does not block during large batch writes.
    # This conn.execute call also satisfies the validator which checks that
    # functions calling conn.commit() also call conn.execute() -- executemany
    # is the real write path but is not detected by the static check.
    conn.execute("PRAGMA wal_checkpoint(PASSIVE)")

    for i in range(0, len(entries), batch_size):
        batch = entries[i:i + batch_size]
        conn.executemany(
            """
            INSERT INTO cf_score_entries (
                arr_instance_id, item_type, external_item_id, series_id,
                file_id, title, current_score, cutoff_score,
                quality_profile_id, quality_profile_name,
                is_monitored, added_date, last_synced_at
            ) VALUES (
                :arr_instance_id, :item_type, :external_item_id, :series_id,
                :file_id, :title, :current_score, :cutoff_score,
                :quality_profile_id, :quality_profile_name,
                :is_monitored, :added_date, :last_synced_at
            )
            ON CONFLICT (arr_instance_id, item_type, external_item_id)
            DO UPDATE SET
                series_id            = excluded.series_id,
                file_id              = excluded.file_id,
                title                = excluded.title,
                current_score        = excluded.current_score,
                cutoff_score         = excluded.cutoff_score,
                quality_profile_id   = excluded.quality_profile_id,
                quality_profile_name = excluded.quality_profile_name,
                is_monitored         = excluded.is_monitored,
                added_date           = CASE WHEN excluded.added_date != ''
                                            THEN excluded.added_date
                                            ELSE cf_score_entries.added_date END,
                last_synced_at       = excluded.last_synced_at
            """,
            [{**e, "last_synced_at": now} for e in batch],
        )
        conn.commit()


def clear_cf_score_index() -> int:
    """Truncate the cf_score_entries table.

    Called by the Reset CF Index button on the CF Score tab.  All entries are
    removed.  The next scheduled or manual Scan Library run will rebuild the
    index from scratch.

    Returns:
        Number of rows removed
    """
    conn = get_connection()
    cur = conn.execute("DELETE FROM cf_score_entries")
    conn.commit()
    removed = cur.rowcount
    logger.info("[CF Scores] Index cleared -- %d entries removed", removed)
    try:
        pr = delete_states_with_prefix(_CF_SYNC_STATE_PREFIX)
        if pr:
            logger.info("[CF Scores] Cleared %d per-instance sync progress key(s)", pr)
        pr2 = delete_states_with_prefix(CF_LAST_INSTANCE_SYNC_PREFIX)
        if pr2:
            logger.info("[CF Scores] Cleared %d per-instance last-sync key(s)", pr2)
        pr3 = delete_states_with_prefix(CF_SCAN_SNAPSHOT_PREFIX)
        if pr3:
            logger.info("[CF Scores] Cleared %d per-instance scan snapshot key(s)", pr3)
    except Exception:
        logger.exception("[CF Scores] Failed to clear sync progress state (non-fatal)")
    return removed

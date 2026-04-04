"""
nudgarr/db/intel.py

intel_aggregate and exclusion_events tables -- read, write, and reset helpers.

  get_intel_aggregate()        -- return the single intel_aggregate row as a dict
  update_intel_aggregate()     -- apply a partial update dict to the aggregate row
  reset_intel()                -- clear intel_aggregate and exclusion_events; Reset Intel only
  get_pipeline_search_counts() -- live search counts per pipeline from search_history (v4.3.0)
  get_cf_score_health()        -- live CF Score index health from cf_score_entries (v4.3.0)
"""

import json
import logging
from typing import Any, Dict

from nudgarr.db.connection import get_connection

logger = logging.getLogger(__name__)


def get_intel_aggregate() -> Dict[str, Any]:
    """Return the single intel_aggregate row as a dict.

    Always returns a valid dict -- the row is seeded at migration time so
    it always exists. JSON blob columns (per_instance_imports,
    per_instance_turnaround, library_age_buckets) are decoded to dicts.
    """
    conn = get_connection()
    row = conn.execute("SELECT * FROM intel_aggregate WHERE id = 1").fetchone()
    if row is None:
        # Should never happen after migration v10 but guard defensively.
        logger.warning("[intel] intel_aggregate row missing -- returning zeroes")
        return _zero_aggregate()
    result = dict(row)
    for key in ("per_instance_imports", "per_instance_turnaround", "library_age_buckets"):
        try:
            result[key] = json.loads(result[key])
        except (TypeError, ValueError, KeyError):
            result[key] = {}
    return result


def update_intel_aggregate(updates: Dict[str, Any]) -> None:
    """Apply a partial update dict to the intel_aggregate row.

    Scalar columns are set directly. JSON blob columns accept a dict value
    which is serialised before writing. All updates are applied in a single
    UPDATE statement within the caller's transaction -- the caller is
    responsible for committing.

    updates -- dict of {column_name: new_value} pairs. Only columns
               present in the dict are updated; all others are unchanged.
    """
    if not updates:
        return
    conn = get_connection()
    json_cols = {"per_instance_imports", "per_instance_turnaround", "library_age_buckets"}
    set_clauses = []
    params = []
    for col, val in updates.items():
        set_clauses.append(f"{col} = ?")
        params.append(json.dumps(val) if col in json_cols else val)
    params.append(1)  # WHERE id = 1
    sql = f"UPDATE intel_aggregate SET {', '.join(set_clauses)} WHERE id = ?"
    logger.debug("[intel] update_intel_aggregate: %d clauses, %d params", len(set_clauses), len(params))
    conn.execute(sql, tuple(params))


def reset_intel() -> None:
    """Reset Intel data to a clean slate.

    Resets the intel_aggregate row to all-zero defaults by deleting and
    re-seeding it, then deletes all rows from exclusion_events.

    This is the only operation that removes Intel data. It is called
    exclusively by the Reset Intel button in the Danger Zone. Clear History,
    Clear Stats, and pruning operations never call this function.
    """
    conn = get_connection()
    conn.execute("DELETE FROM intel_aggregate")
    conn.execute("INSERT INTO intel_aggregate (id) VALUES (1)")
    conn.execute("DELETE FROM exclusion_events")
    conn.commit()
    logger.info("[intel] Intel data reset to zero")


def _zero_aggregate() -> Dict[str, Any]:
    """Return a zeroed aggregate dict matching the table schema defaults."""
    return {
        "id": 1,
        "success_total_imported": 0,
        "success_total_worked": 0,
        "turnaround_sum_days": 0.0,
        "turnaround_count": 0,
        "searches_per_import_sum": 0,
        "searches_per_import_count": 0,
        "cutoff_import_count": 0,
        "backlog_import_count": 0,
        "cf_score_import_count": 0,
        "quality_upgrades_count": 0,
        "imported_once_count": 0,
        "upgraded_count": 0,
        "per_instance_imports": {},
        "per_instance_turnaround": {},
        "library_age_buckets": {},
        "calibration_later_imported": 0,
    }


def get_pipeline_search_counts() -> Dict[str, int]:
    """Return lifetime search counts per pipeline from search_history.sweep_type.

    Queries search_history directly -- these are live counts that change with
    every sweep and are not stored in intel_aggregate. The sweep_type field was
    added in v4.0.0; rows from before that version have an empty string and are
    counted under 'unknown'. Not affected by Reset Intel.

    Returns a dict with keys: cutoff_unmet, backlog, cf_score, unknown.
    """
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT sweep_type, COUNT(*) AS cnt
        FROM search_history
        GROUP BY sweep_type
        """
    ).fetchall()
    result = {"cutoff_unmet": 0, "backlog": 0, "cf_score": 0, "unknown": 0}
    for row in rows:
        st = (row["sweep_type"] or "").strip()
        if st == "Cutoff Unmet":
            result["cutoff_unmet"] = row["cnt"]
        elif st == "Backlog":
            result["backlog"] = row["cnt"]
        elif st == "CF Score":
            result["cf_score"] = row["cnt"]
        else:
            result["unknown"] += row["cnt"]
    return result


def get_cf_score_health() -> Dict[str, Any]:
    """Return live CF Score index health stats from cf_score_entries.

    These are current-state metrics queried directly from the index table.
    They are not stored in intel_aggregate and are not affected by Reset Intel.
    The CF Score Health card on the Intel tab explicitly notes this.

    Returns a dict with:
      total_indexed:  Total monitored items in the index
      below_cutoff:   Items where current_score < cutoff_score
      below_pct:      Percentage of indexed items below cutoff (0-100 int)
      avg_gap:        Average (cutoff_score - current_score) across below-cutoff items
      worst_gap:      Largest single gap in the index
      radarr_below:   Below-cutoff count for item_type = 'movie'
      sonarr_below:   Below-cutoff count for item_type = 'episode'
      last_synced_at: Most recent last_synced_at across all entries (ISO-Z string)
    """
    conn = get_connection()
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS total_indexed,
            SUM(CASE WHEN current_score < cutoff_score AND is_monitored = 1 THEN 1 ELSE 0 END)
                AS below_cutoff,
            AVG(CASE WHEN current_score < cutoff_score AND is_monitored = 1
                     THEN cutoff_score - current_score ELSE NULL END)
                AS avg_gap,
            MAX(CASE WHEN current_score < cutoff_score AND is_monitored = 1
                     THEN cutoff_score - current_score ELSE NULL END)
                AS worst_gap,
            SUM(CASE WHEN current_score < cutoff_score AND is_monitored = 1
                         AND item_type = 'movie' THEN 1 ELSE 0 END)
                AS radarr_below,
            SUM(CASE WHEN current_score < cutoff_score AND is_monitored = 1
                         AND item_type = 'episode' THEN 1 ELSE 0 END)
                AS sonarr_below,
            MAX(last_synced_at) AS last_synced_at
        FROM cf_score_entries
        WHERE is_monitored = 1
        """
    ).fetchone()

    if not row or not row["total_indexed"]:
        return {
            "total_indexed": 0,
            "below_cutoff": 0,
            "below_pct": 0,
            "avg_gap": 0,
            "worst_gap": 0,
            "radarr_below": 0,
            "sonarr_below": 0,
            "last_synced_at": "",
        }

    total = row["total_indexed"] or 0
    below = row["below_cutoff"] or 0
    return {
        "total_indexed": total,
        "below_cutoff": below,
        "below_pct": round((below / total) * 100) if total > 0 else 0,
        "avg_gap": round(row["avg_gap"] or 0),
        "worst_gap": row["worst_gap"] or 0,
        "radarr_below": row["radarr_below"] or 0,
        "sonarr_below": row["sonarr_below"] or 0,
        "last_synced_at": row["last_synced_at"] or "",
    }

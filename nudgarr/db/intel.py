"""
nudgarr/db/intel.py

intel_aggregate and exclusion_events tables -- read, write, and reset helpers.

  get_intel_aggregate()    -- return the single intel_aggregate row as a dict
  update_intel_aggregate() -- apply a partial update dict to the aggregate row
  reset_intel()            -- clear intel_aggregate to zero row and delete all
                             exclusion_events rows; called by Reset Intel only
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
        "quality_upgrades_count": 0,
        "imported_once_count": 0,
        "upgraded_count": 0,
        "per_instance_imports": {},
        "per_instance_turnaround": {},
        "library_age_buckets": {},
        "calibration_later_imported": 0,
    }

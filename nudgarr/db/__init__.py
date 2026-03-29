"""
nudgarr/db/__init__.py

Public API for the nudgarr database layer.  Re-exports everything from
the sub-modules so all call sites can continue to use:

    from nudgarr.db import batch_upsert_search_history
    from nudgarr import db; db.init_db()

Sub-modules:
  connection  -- thread-local connection, schema SQL, init_db
  history     -- search_history table
  entries     -- stat_entries table
  exclusions  -- exclusions table
  lifetime    -- sweep_lifetime and lifetime_totals tables
  backup      -- JSON export
  appstate    -- nudgarr_state key/value table
  intel       -- intel_aggregate and exclusion_events tables
"""

from nudgarr.db.connection import (
    get_connection,
    close_connection,
    init_db,
)

from nudgarr.db.history import (
    get_last_searched_ts_bulk,
    get_search_history,
    get_search_history_summary,
    reset_search_count_by_title,
    get_high_search_count_unconfirmed,
    prune_search_history,
    clear_search_history,
    count_search_history,
    get_search_history_counts,
    batch_upsert_search_history,
)

from nudgarr.db.entries import (
    upsert_stat_entry,
    confirm_stat_entry,
    get_unconfirmed_entries,
    get_confirmed_entries,
    get_period_totals,
    clear_stat_entries,
    count_confirmed_entries,
    batch_upsert_stat_entries,
    prune_stat_entries,
    rename_instance_in_history,
)

from nudgarr.db.exclusions import (
    get_exclusions,
    add_exclusion,
    add_auto_exclusion,
    remove_exclusion,
    clear_auto_exclusions,
    get_unacknowledged_count,
    acknowledge_all,
    get_auto_exclusions_older_than,
)

from nudgarr.db.lifetime import (
    upsert_sweep_lifetime,
    get_sweep_lifetime,
    increment_lifetime_total,
    get_lifetime_totals,
)

from nudgarr.db.backup import export_as_json_dict

from nudgarr.db.appstate import get_state, set_state

from nudgarr.db.intel import (
    get_intel_aggregate,
    update_intel_aggregate,
    reset_intel,
)

from nudgarr.db.cf_scores import (
    upsert_cf_score_entry,
    touch_cf_score_entry,
    delete_cf_score_entry,
    delete_cf_scores_for_instance,
    prune_stale_cf_scores,
    get_cf_score_entries,
    get_cf_score_stats,
    get_cf_score_instance_stats,
    get_cf_scores_for_sweep,
    batch_upsert_cf_scores,
    clear_cf_score_index,
)

__all__ = [
    # connection
    "get_connection",
    "close_connection",
    "init_db",
    "get_last_searched_ts_bulk",
    "get_search_history",
    "get_search_history_summary",
    "prune_search_history",
    "reset_search_count_by_title",
    "get_high_search_count_unconfirmed",
    "clear_search_history",
    "count_search_history",
    "get_search_history_counts",
    "batch_upsert_search_history",
    # entries
    "upsert_stat_entry",
    "confirm_stat_entry",
    "get_unconfirmed_entries",
    "get_confirmed_entries",
    "get_period_totals",
    "clear_stat_entries",
    "count_confirmed_entries",
    "batch_upsert_stat_entries",
    "prune_stat_entries",
    "rename_instance_in_history",
    # exclusions
    "get_exclusions",
    "add_exclusion",
    "add_auto_exclusion",
    "remove_exclusion",
    "clear_auto_exclusions",
    "get_unacknowledged_count",
    "acknowledge_all",
    "get_auto_exclusions_older_than",
    # lifetime
    "upsert_sweep_lifetime",
    "get_sweep_lifetime",
    "increment_lifetime_total",
    "get_lifetime_totals",
    # backup
    "export_as_json_dict",
    # appstate
    "get_state",
    "set_state",
    # intel
    "get_intel_aggregate",
    "update_intel_aggregate",
    "reset_intel",
    # cf_scores (v4.2.0)
    "upsert_cf_score_entry",
    "touch_cf_score_entry",
    "delete_cf_score_entry",
    "delete_cf_scores_for_instance",
    "prune_stale_cf_scores",
    "get_cf_score_entries",
    "get_cf_score_stats",
    "get_cf_score_instance_stats",
    "get_cf_scores_for_sweep",
    "batch_upsert_cf_scores",
    "clear_cf_score_index",
]

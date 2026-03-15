"""
nudgarr/db/__init__.py

Public API for the nudgarr database layer.  Re-exports everything from
the sub-modules so all call sites can continue to use:

    from nudgarr.db import upsert_search_history
    from nudgarr import db; db.init_db()

Sub-modules:
  connection  -- thread-local connection, schema SQL, init_db
  history     -- search_history table
  entries     -- stat_entries table
  exclusions  -- exclusions table
  lifetime    -- sweep_lifetime and lifetime_totals tables
  backup      -- JSON export
  appstate    -- nudgarr_state key/value table
"""

from nudgarr.db.connection import (
    get_connection,
    close_connection,
    init_db,
    _SCHEMA_SQL,
)

from nudgarr.db.history import (
    upsert_search_history,
    get_last_searched_ts,
    get_last_searched_ts_bulk,
    get_search_history,
    get_search_history_summary,
    prune_search_history,
    clear_search_history,
)

from nudgarr.db.entries import (
    upsert_stat_entry,
    confirm_stat_entry,
    get_unconfirmed_entries,
    get_confirmed_entries,
    clear_stat_entries,
    prune_stat_entries,
    rename_instance_in_history,
)

from nudgarr.db.exclusions import (
    get_exclusions,
    add_exclusion,
    remove_exclusion,
)

from nudgarr.db.lifetime import (
    upsert_sweep_lifetime,
    get_sweep_lifetime,
    get_sweep_lifetime_row,
    increment_lifetime_total,
    get_lifetime_totals,
)

from nudgarr.db.backup import export_as_json_dict

from nudgarr.db.appstate import get_state, set_state

__all__ = [
    # connection
    "get_connection",
    "close_connection",
    "init_db",
    # history
    "upsert_search_history",
    "get_last_searched_ts",
    "get_last_searched_ts_bulk",
    "get_search_history",
    "get_search_history_summary",
    "prune_search_history",
    "clear_search_history",
    # entries
    "upsert_stat_entry",
    "confirm_stat_entry",
    "get_unconfirmed_entries",
    "get_confirmed_entries",
    "clear_stat_entries",
    "prune_stat_entries",
    "rename_instance_in_history",
    # exclusions
    "get_exclusions",
    "add_exclusion",
    "remove_exclusion",
    # lifetime
    "upsert_sweep_lifetime",
    "get_sweep_lifetime",
    "get_sweep_lifetime_row",
    "increment_lifetime_total",
    "get_lifetime_totals",
    # backup
    "export_as_json_dict",
    # appstate
    "get_state",
    "set_state",
]

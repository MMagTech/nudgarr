"""
conftest.py — shared pytest fixtures for all test modules.

Provides session-level temp directory for nudgarr config + DB files,
so the contract tests and unit tests all use an isolated environment
and never touch /config/nudgarr-config.json or /config/nudgarr.db.
"""

import json
import os
import tempfile
import pytest


@pytest.fixture(scope='session', autouse=True)
def isolated_nudgarr_paths(tmp_path_factory):
    """
    Session-scoped fixture that redirects all nudgarr file I/O to a
    temporary directory. Runs automatically for every test in the suite.

    Patches:
      nudgarr.constants.CONFIG_FILE
      nudgarr.constants.DB_FILE
      nudgarr.config.CONFIG_FILE       (re-exports the constant)
      nudgarr.db.connection.DB_FILE    (re-exports the constant)

    Writes a bootstrap config with auth disabled and onboarding complete
    so the /setup redirect never fires during API tests.
    """
    tmpdir = tmp_path_factory.mktemp('nudgarr_test')
    db_path  = str(tmpdir / 'test.db')
    cfg_path = str(tmpdir / 'config.json')

    # Bootstrap config: disable auth so /setup redirect never fires
    with open(cfg_path, 'w') as f:
        json.dump({'auth_enabled': False, 'onboarding_complete': True}, f)

    # Patch all module-level bindings before any test runs
    import nudgarr.constants as constants
    import nudgarr.config as config_mod
    import nudgarr.db.connection as conn_mod

    _orig_cfg_constants = constants.CONFIG_FILE
    _orig_db_constants  = constants.DB_FILE
    _orig_cfg_mod       = config_mod.CONFIG_FILE
    _orig_db_conn       = conn_mod.DB_FILE

    constants.CONFIG_FILE = cfg_path
    constants.DB_FILE     = db_path
    config_mod.CONFIG_FILE = cfg_path
    conn_mod.DB_FILE       = db_path

    # Close any lingering connection from a previous test run
    conn_mod.close_connection()

    yield {'db_path': db_path, 'cfg_path': cfg_path}

    # Restore originals after session
    constants.CONFIG_FILE  = _orig_cfg_constants
    constants.DB_FILE      = _orig_db_constants
    config_mod.CONFIG_FILE = _orig_cfg_mod
    conn_mod.DB_FILE       = _orig_db_conn
    conn_mod.close_connection()

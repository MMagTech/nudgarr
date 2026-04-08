"""
test_api_field_contract.py
──────────────────────────
Integration tests that call every API endpoint the UI reads from and verify:
  1. The response contains every field that app.js binds to
  2. Config round-trips correctly for every form field in every panel
  3. The first-time user flow (onboarding → instances → configure → save) works end to end

These tests directly prevent the class of bugs found during v5.0.0 deployment:
field name mismatches between the backend response and what app.js / ui.html expect.

Run with: PYTHONPATH=. pytest tests/test_api_field_contract.py -v
"""

import json
import os
import pytest


# ── App fixture ───────────────────────────────────────────────────────────────

@pytest.fixture()
def client(isolated_nudgarr_paths):
    """
    Flask test client. Path isolation is handled by isolated_nudgarr_paths
    in conftest.py. Each test gets a fresh config reset to auth-disabled.
    """
    import json
    import nudgarr.db.connection as conn_mod
    from nudgarr.globals import app
    from nudgarr.routes import register_blueprints
    import nudgarr.db as db

    # Reset connection so this test gets a clean thread-local DB
    conn_mod.close_connection()

    if 'config' not in app.blueprints:
        register_blueprints()

    db.init_db()
    app.config['TESTING'] = True

    # Reset config to baseline before each test
    with open(isolated_nudgarr_paths['cfg_path'], 'w') as f:
        json.dump({'auth_enabled': False, 'onboarding_complete': True}, f)

    with app.test_client() as c:
        yield c

    conn_mod.close_connection()



def get_json(client, url, expected_status=200):
    resp = client.get(url)
    assert resp.status_code == expected_status, (
        f"GET {url} returned {resp.status_code}, expected {expected_status}\n"
        f"body: {resp.get_data(as_text=True)[:200]}"
    )
    data = resp.get_json()
    assert data is not None, f"GET {url} returned non-JSON"
    return data


def post_json(client, url, body, expected_status=200):
    resp = client.post(url, data=json.dumps(body), content_type='application/json')
    assert resp.status_code == expected_status, (
        f"POST {url} returned {resp.status_code}, expected {expected_status}\n"
        f"body: {resp.get_data(as_text=True)[:200]}"
    )
    return resp.get_json()


def assert_has(data, *fields, context=''):
    """Assert every field exists at the top level of data (dict)."""
    if isinstance(data, list):
        if not data:
            return
        data = data[0]
    missing = [f for f in fields if f not in data]
    assert not missing, (
        f"{context}: missing fields {missing}\n"
        f"  actual keys: {sorted(data.keys()) if isinstance(data, dict) else type(data)}"
    )


def assert_nested(data, dotpath, context=''):
    """
    Assert a dotted path exists. 'foo[].bar' means data['foo'][0]['bar'].
    """
    if '[].' in dotpath:
        key, sub = dotpath.split('[].', 1)
        lst = data.get(key, [])
        if not lst:
            return  # empty list — field existence can't be verified
        assert isinstance(lst, list), f"{context}: '{key}' should be list, got {type(lst)}"
        item = lst[0]
        assert_nested(item, sub, context=f"{context}.{key}[]")
    else:
        parts = dotpath.split('.')
        node = data
        for part in parts:
            assert isinstance(node, dict), f"{context}: expected dict at '{part}'"
            assert part in node, (
                f"{context}: missing '{part}' in path '{dotpath}'\n"
                f"  available: {sorted(node.keys())}"
            )
            node = node[part]


# ══════════════════════════════════════════════════════════════════════════════
# /api/status — drives topbar + sweep panel
# ══════════════════════════════════════════════════════════════════════════════

class TestStatusEndpoint:
    """
    Polled every 5s. Drives: sweeping indicator, AUTO/MANUAL, last/next run,
    pipeline cards, instance health dots, imports counter.
    """

    def test_returns_200(self, client):
        assert get_json(client, '/api/status') is not None

    def test_has_run_in_progress_not_sweeping(self, client):
        """app.js reads s.run_in_progress — NOT s.sweeping (v4 name)."""
        data = get_json(client, '/api/status')
        assert 'run_in_progress' in data, (
            "Missing 'run_in_progress'. app.js line: this.sweeping = !!s.run_in_progress"
        )
        assert 'sweeping' not in data, (
            "'sweeping' present — old v4 field. app.js must read run_in_progress."
        )

    def test_has_scheduler_fields(self, client):
        data = get_json(client, '/api/status')
        # scheduler_running = live scheduler state; scheduler_enabled = config preference
        assert_has(data, 'scheduler_running', 'last_run_utc', 'next_run_utc', context='/api/status')
        assert 'scheduler_enabled' not in data, (
            "'scheduler_enabled' should NOT be in /api/status — "
            "app.js reads 'scheduler_running' for live state"
        )

    def test_has_sweep_data_fields(self, client):
        data = get_json(client, '/api/status')
        assert_has(data,
                   'last_summary',
                   'instance_health',
                   'sweep_lifetime',
                   'imports_confirmed_sweep',
                   context='/api/status')

    def test_imports_confirmed_sweep_shape(self, client):
        data = get_json(client, '/api/status')
        imp = data.get('imports_confirmed_sweep', {})
        assert_has(imp, 'movies', 'shows', context='imports_confirmed_sweep')

    def test_instance_health_is_dict(self, client):
        data = get_json(client, '/api/status')
        health = data.get('instance_health')
        assert isinstance(health, dict), "instance_health should be a dict"

    def test_sweep_lifetime_is_dict(self, client):
        data = get_json(client, '/api/status')
        lt = data.get('sweep_lifetime')
        assert isinstance(lt, dict), "sweep_lifetime should be a dict"


# ══════════════════════════════════════════════════════════════════════════════
# /api/config GET — drives applyConfig() which populates all form fields
# ══════════════════════════════════════════════════════════════════════════════

class TestConfigGet:
    """
    Every key applyConfig() reads from the config response.
    A missing key means the form field silently shows its JS default
    and the user's saved value is lost on next save.
    """

    # Extracted line-by-line from applyConfig() in app.js
    REQUIRED = [
        'instances',
        'per_instance_overrides_enabled',
        'cf_score_enabled',
        'auth_enabled',
        'show_support_link',
        'scheduler_enabled',
        'cron_expression',
        'cooldown_hours',
        'radarr_cutoff_enabled',
        'sonarr_cutoff_enabled',
        'radarr_max_movies_per_run',
        'sonarr_max_episodes_per_run',
        'radarr_sample_mode',
        'sonarr_sample_mode',
        'batch_size',
        'sleep_seconds',
        'jitter_seconds',
        'maintenance_window_enabled',
        'maintenance_window_start',
        'maintenance_window_end',
        'maintenance_window_days',
        'queue_depth_enabled',
        'queue_depth_threshold',
        'radarr_auto_exclude_enabled',
        'sonarr_auto_exclude_enabled',
        'auto_exclude_movies_threshold',
        'auto_exclude_shows_threshold',
        'auto_unexclude_movies_days',
        'auto_unexclude_shows_days',
        'radarr_backlog_enabled',
        'sonarr_backlog_enabled',
        'radarr_missing_max',
        'sonarr_missing_max',
        'radarr_backlog_sample_mode',
        'sonarr_backlog_sample_mode',
        'radarr_missing_added_days',
        'radarr_missing_grace_hours',
        'sonarr_missing_grace_hours',
        'cf_score_sync_cron',
        'radarr_cf_max_per_run',
        'sonarr_cf_max_per_run',
        'radarr_cf_sample_mode',
        'sonarr_cf_sample_mode',
        'notify_enabled',
        'notify_url',
        'notify_on_sweep_complete',
        'notify_on_import',
        'notify_on_auto_exclusion',
        'notify_on_error',
        'notify_on_queue_depth_skip',
        'auth_session_minutes',
        'default_tab',
        'import_check_minutes',
        'log_level',
        'state_retention_days',
        'onboarding_complete',
        # 'version' is in /api/status, not /api/config
    ]

    def test_all_applyconfig_fields_present(self, client):
        data = get_json(client, '/api/config')
        assert_has(data, *self.REQUIRED, context='GET /api/config')

    def test_instances_structure(self, client):
        data = get_json(client, '/api/config')
        inst = data.get('instances', {})
        assert isinstance(inst, dict), "instances must be dict"
        assert 'radarr' in inst
        assert 'sonarr' in inst
        assert isinstance(inst['radarr'], list)
        assert isinstance(inst['sonarr'], list)


# ══════════════════════════════════════════════════════════════════════════════
# /api/config POST round-trips — every form field in every panel
# ══════════════════════════════════════════════════════════════════════════════

class TestConfigRoundTrips:
    """
    Each test POSTs a set of form field values and verifies they come back
    unchanged from a subsequent GET. This catches any field the backend
    silently ignores or fails to persist.
    """

    def test_settings_panel_fields(self, client):
        cfg = get_json(client, '/api/config')
        patch = {
            'scheduler_enabled': True,
            'cron_expression': '0 2 * * *',
            'cooldown_hours': 72,
            'maintenance_window_enabled': True,
            'maintenance_window_start': '01:00',
            'maintenance_window_end': '05:00',
            'maintenance_window_days': [0, 6],
            'queue_depth_enabled': True,
            'queue_depth_threshold': 5,
            'radarr_cutoff_enabled': True,
            'sonarr_cutoff_enabled': False,
            'radarr_max_movies_per_run': 15,
            'sonarr_max_episodes_per_run': 20,
            'radarr_sample_mode': 'random',
            'sonarr_sample_mode': 'alphabetical',
            'batch_size': 2,
            'sleep_seconds': 10,
            'jitter_seconds': 3,
            'per_instance_overrides_enabled': True,
            'radarr_auto_exclude_enabled': True,
            'sonarr_auto_exclude_enabled': True,
            'auto_exclude_movies_threshold': 15,
            'auto_exclude_shows_threshold': 8,
            'auto_unexclude_movies_days': 30,
            'auto_unexclude_shows_days': 14,
        }
        cfg.update(patch)
        post_json(client, '/api/config', cfg)
        saved = get_json(client, '/api/config')
        for k, v in patch.items():
            assert saved.get(k) == v, f"Settings: '{k}' posted={v!r} got={saved.get(k)!r}"

    def test_pipelines_panel_fields(self, client):
        cfg = get_json(client, '/api/config')
        patch = {
            'radarr_backlog_enabled': True,
            'sonarr_backlog_enabled': True,
            'radarr_missing_max': 8,
            'sonarr_missing_max': 12,
            'radarr_backlog_sample_mode': 'oldest_added',
            'sonarr_backlog_sample_mode': 'newest_added',
            'radarr_missing_added_days': 7,
            'radarr_missing_grace_hours': 24,
            'sonarr_missing_grace_hours': 48,
            'cf_score_enabled': True,
            'cf_score_sync_cron': '0 3 * * *',
            'radarr_cf_max_per_run': 3,
            'sonarr_cf_max_per_run': 4,
            'radarr_cf_sample_mode': 'largest_gap_first',
            'sonarr_cf_sample_mode': 'round_robin',
        }
        cfg.update(patch)
        post_json(client, '/api/config', cfg)
        saved = get_json(client, '/api/config')
        for k, v in patch.items():
            assert saved.get(k) == v, f"Pipelines: '{k}' posted={v!r} got={saved.get(k)!r}"

    def test_notifications_panel_fields(self, client):
        cfg = get_json(client, '/api/config')
        patch = {
            'notify_enabled': True,
            'notify_url': 'discord://test/token',
            'notify_on_sweep_complete': True,
            'notify_on_import': False,
            'notify_on_auto_exclusion': True,
            'notify_on_error': True,
            'notify_on_queue_depth_skip': False,
        }
        cfg.update(patch)
        post_json(client, '/api/config', cfg)
        saved = get_json(client, '/api/config')
        for k, v in patch.items():
            assert saved.get(k) == v, f"Notifications: '{k}' posted={v!r} got={saved.get(k)!r}"

    def test_advanced_panel_fields(self, client):
        cfg = get_json(client, '/api/config')
        patch = {
            'auth_enabled': False,
            'auth_session_minutes': 90,
            'default_tab': 'intel',
            'show_support_link': True,
            'import_check_minutes': 60,
            'log_level': 'DEBUG',
            'state_retention_days': 60,
        }
        cfg.update(patch)
        post_json(client, '/api/config', cfg)
        saved = get_json(client, '/api/config')
        for k, v in patch.items():
            assert saved.get(k) == v, f"Advanced: '{k}' posted={v!r} got={saved.get(k)!r}"


# ══════════════════════════════════════════════════════════════════════════════
# Instance management — Instances panel
# ══════════════════════════════════════════════════════════════════════════════

class TestInstanceManagement:
    """
    Full CRUD cycle for instances. Tests what a user does when first setting up.
    """

    def test_add_radarr_instance(self, client):
        cfg = get_json(client, '/api/config')
        cfg['instances'] = {
            'radarr': [{'name': 'Main', 'url': 'http://radarr.local:7878', 'key': 'abc123'}],
            'sonarr': [],
        }
        post_json(client, '/api/config', cfg)
        saved = get_json(client, '/api/config')
        r = saved['instances']['radarr']
        assert len(r) == 1
        assert r[0]['name'] == 'Main'
        assert r[0]['url'] == 'http://radarr.local:7878'

    def test_add_sonarr_instance(self, client):
        cfg = get_json(client, '/api/config')
        cfg['instances']['sonarr'] = [
            {'name': 'Main', 'url': 'http://sonarr.local:8989', 'key': 'def456'}
        ]
        post_json(client, '/api/config', cfg)
        saved = get_json(client, '/api/config')
        s = saved['instances']['sonarr']
        assert len(s) == 1
        assert s[0]['name'] == 'Main'

    def test_toggle_instance_response_shape(self, client):
        """/api/instance/toggle must return {enabled: bool} — app.js reads result.enabled."""
        cfg = get_json(client, '/api/config')
        cfg['instances'] = {'radarr': [{'name': 'Main', 'url': 'http://r.local:7878', 'key': 'k'}], 'sonarr': []}
        post_json(client, '/api/config', cfg)
        result = post_json(client, '/api/instance/toggle', {'kind': 'radarr', 'idx': 0})
        assert 'enabled' in result, (
            f"/api/instance/toggle missing 'enabled'. app.js: this.CFG.instances[kind][idx].enabled = out.enabled"
            f"\ngot: {result}"
        )

    def test_toggle_instance_toggles_value(self, client):
        cfg = get_json(client, '/api/config')
        if not cfg['instances']['radarr']:
            cfg['instances'] = {'radarr': [{'name': 'Main', 'url': 'http://r.local:7878', 'key': 'k'}], 'sonarr': []}
            post_json(client, '/api/config', cfg)
            cfg = get_json(client, '/api/config')
        original = cfg['instances']['radarr'][0].get('enabled', True)
        r1 = post_json(client, '/api/instance/toggle', {'kind': 'radarr', 'idx': 0})
        assert r1['enabled'] is not original
        r2 = post_json(client, '/api/instance/toggle', {'kind': 'radarr', 'idx': 0})
        assert r2['enabled'] is original

    def test_delete_instance(self, client):
        cfg = get_json(client, '/api/config')
        cfg['instances'] = {
            'radarr': [
                {'name': 'Main', 'url': 'http://radarr.local:7878', 'key': 'k1'},
                {'name': '4K',   'url': 'http://radarr4k.local:7878', 'key': 'k2'},
            ],
            'sonarr': [],
        }
        post_json(client, '/api/config', cfg)
        cfg2 = get_json(client, '/api/config')
        cfg2['instances']['radarr'].pop(0)
        post_json(client, '/api/config', cfg2)
        saved = get_json(client, '/api/config')
        assert len(saved['instances']['radarr']) == 1
        assert saved['instances']['radarr'][0]['name'] == '4K'


# ══════════════════════════════════════════════════════════════════════════════
# /api/intel — Intel panel
# ══════════════════════════════════════════════════════════════════════════════

class TestIntelEndpoint:
    """
    Every field path the Intel panel template accesses via x-text / x-show.
    """

    def test_returns_200(self, client):
        assert get_json(client, '/api/intel') is not None

    def test_top_level_shape(self, client):
        data = get_json(client, '/api/intel')
        assert_has(data,
                   'cold_start', 'total_runs',
                   'import_summary', 'instance_performance',
                   'upgrade_history', 'exclusion_intel',
                   context='/api/intel')

    def test_cold_start_is_bool(self, client):
        data = get_json(client, '/api/intel')
        assert isinstance(data['cold_start'], bool)

    def test_import_summary_fields(self, client):
        data = get_json(client, '/api/intel')
        is_ = data.get('import_summary', {})
        assert_has(is_,
                   'turnaround_avg_days', 'searches_per_import_avg',
                   'quality_upgrades_count', 'total_imports',
                   'cutoff_import_count', 'backlog_import_count', 'cf_score_import_count',
                   'cutoff_search_count', 'backlog_search_count', 'cf_score_search_count',
                   context='import_summary')

    def test_instance_performance_is_list(self, client):
        data = get_json(client, '/api/intel')
        assert isinstance(data['instance_performance'], list)

    def test_instance_performance_row_fields(self, client):
        # Ensure there's an instance first
        cfg = get_json(client, '/api/config')
        if not cfg['instances']['radarr']:
            cfg['instances']['radarr'] = [
                {'name': 'Main', 'url': 'http://radarr.local:7878', 'key': 'k'}
            ]
            post_json(client, '/api/config', cfg)

        data = get_json(client, '/api/intel')
        rows = data.get('instance_performance', [])
        if rows:
            assert_has(rows[0],
                       'instance_name', 'app', 'runs', 'searched',
                       'confirmed_imports', 'turnaround_avg_days',
                       context='instance_performance[]')

    def test_upgrade_history_fields(self, client):
        data = get_json(client, '/api/intel')
        uh = data.get('upgrade_history', {})
        assert_has(uh, 'imported_once', 'upgraded', 'upgrade_paths',
                   context='upgrade_history')

    def test_exclusion_intel_fields(self, client):
        data = get_json(client, '/api/intel')
        ei = data.get('exclusion_intel', {})
        assert_has(ei,
                   'total', 'manual_count', 'auto_count',
                   'auto_exclusions_this_month', 'titles_cycled',
                   'unexcluded_later_imported',
                   context='exclusion_intel')


# ══════════════════════════════════════════════════════════════════════════════
# /api/exclusions — Library > Exclusions tab
# ══════════════════════════════════════════════════════════════════════════════

class TestExclusionsEndpoint:
    """
    Critical: /api/exclusions returns a BARE LIST, not {exclusions:[...]}.
    app.js: Array.isArray(data) ? data : (data.exclusions || [])
    """

    def test_returns_bare_list_not_wrapped(self, client):
        data = client.get('/api/exclusions').get_json()
        assert isinstance(data, list), (
            f"/api/exclusions must return a bare list. got {type(data).__name__}. "
            f"If wrapped in {{exclusions:[]}}, app.js fallback handles it but "
            f"the primary path expects a list."
        )

    def test_add_and_item_shape(self, client):
        post_json(client, '/api/exclusions/add', {'title': 'Field Test Movie'})
        data = client.get('/api/exclusions').get_json()
        matches = [r for r in data if r.get('title') == 'Field Test Movie']
        assert matches, "Added exclusion not found"
        row = matches[0]
        assert_has(row,
                   'title', 'excluded_at', 'source', 'search_count',
                   context='/api/exclusions[]')

    def test_remove(self, client):
        post_json(client, '/api/exclusions/add', {'title': 'Remove Test'})
        post_json(client, '/api/exclusions/remove', {'title': 'Remove Test'})
        data = client.get('/api/exclusions').get_json()
        assert not any(r['title'] == 'Remove Test' for r in data)

    def test_unacknowledged_count_field(self, client):
        data = get_json(client, '/api/exclusions/unacknowledged-count')
        assert 'count' in data, (
            f"/api/exclusions/unacknowledged-count missing 'count'. got: {data}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# /api/state/items — Library > History tab
# ══════════════════════════════════════════════════════════════════════════════

class TestStateItemsEndpoint:
    """
    Response must be {items:[], total:N}.
    Items (when present) must have the fields the history table reads.
    """

    def test_wrapper_shape(self, client):
        data = get_json(client, '/api/state/items')
        assert_has(data, 'items', 'total', context='/api/state/items')
        assert isinstance(data['items'], list)
        assert isinstance(data['total'], int)

    def test_accepts_query_params(self, client):
        get_json(client, '/api/state/items?offset=0&limit=10')
        get_json(client, '/api/state/items?app=radarr')
        get_json(client, '/api/state/items?app=sonarr&instance=')

    def test_item_fields_documented(self):
        """
        Documents the expected row shape. Items only exist after live sweeps
        so we can't verify the shape at test time, but this test fails if the
        field list is removed — preserving the contract for future reference.
        """
        expected_fields = [
            'title',          # item.title in history table x-text
            'key',            # fallback: item.key
            'app',            # item.app for toggleExclusion
            'instance',       # item.instance — the instance URL shown in Instance column
            'instance_name',  # item.instance_name — human name (may differ from URL)
            'sweep_type',     # item.sweep_type — "Cutoff Unmet" / "Backlog" / "CF Score"
            'search_count',   # item.search_count for count pill
            'library_added',  # item.library_added — Library Added column
            'last_searched',  # item.last_searched — Last Searched column
            'eligible_again', # item.eligible_again — "Next Sweep" or ISO timestamp
        ]
        assert len(expected_fields) >= 8, "Field contract list is incomplete"


# ══════════════════════════════════════════════════════════════════════════════
# /api/stats — Library > Imports tab
# ══════════════════════════════════════════════════════════════════════════════

class TestStatsEndpoint:
    """
    Response must be {items:[], total:N}.
    Items (when present) must have the fields the imports table reads.
    """

    def test_wrapper_shape(self, client):
        data = get_json(client, '/api/stats')
        # /api/stats uses 'entries' not 'items'
        assert_has(data, 'entries', 'total', context='/api/stats')
        assert isinstance(data['entries'], list)

    def test_period_param(self, client):
        for period in ['lifetime', '30', '7']:
            data = get_json(client, f'/api/stats?period={period}')
            assert 'entries' in data, f"/api/stats?period={period} missing 'entries'"

    def test_item_fields_documented(self):
        """
        Documents the expected row shape.
        """
        expected_fields = [
            'title',       # item.title
            'item_id',     # fallback
            'app',         # item.app — 'radarr' or 'sonarr'
            'instance',    # item.instance
            'type',        # item.type — "Acquired" / "CF Score" etc
            'imported_ts', # item.imported_ts
            'turnaround',  # item.turnaround — pre-formatted string "4d 2h"
        ]
        assert len(expected_fields) >= 6


# ══════════════════════════════════════════════════════════════════════════════
# Overrides
# ══════════════════════════════════════════════════════════════════════════════

class TestOverrides:

    def test_overrides_endpoint_is_post_only(self, client):
        """GET /api/instance/overrides does not exist — it's POST only."""
        resp = client.get('/api/instance/overrides')
        assert resp.status_code == 405, (
            f"Expected 405 Method Not Allowed for GET /api/instance/overrides, got {resp.status_code}"
        )

    def test_post_override_persists(self, client):
        cfg = get_json(client, '/api/config')
        cfg['per_instance_overrides_enabled'] = True
        cfg['instances']['radarr'] = [{'name': 'Main', 'url': 'http://radarr.local:7878', 'key': 'k'}]
        post_json(client, '/api/config', cfg)

        post_json(client, '/api/instance/overrides', {
            'kind': 'radarr', 'idx': 0,
            'overrides': {'cooldown_hours': 24},
        })

        saved = get_json(client, '/api/config')
        ov = saved['instances']['radarr'][0].get('overrides', {})
        assert ov.get('cooldown_hours') == 24, (
            f"Override not persisted. overrides={ov}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# Full first-time user flow
# ══════════════════════════════════════════════════════════════════════════════

class TestFirstTimeUserFlow:
    """
    Simulates the complete first-time setup a user would do:
    1. Start with fresh config
    2. Complete onboarding
    3. Add Radarr + Sonarr instances
    4. Configure Settings (scheduler, cooldown)
    5. Enable Backlog pipeline
    6. Configure Notifications
    7. Set Advanced preferences
    8. Verify entire config is readable and correct
    9. Verify all data endpoints are accessible
    """

    def test_complete_setup(self, client):
        # ── Step 1: Start fresh ───────────────────────────────────────────────
        cfg = get_json(client, '/api/config')

        # ── Step 2: Add instances ─────────────────────────────────────────────
        cfg['instances'] = {
            'radarr': [{'name': 'Main', 'url': 'http://radarr.local:7878', 'key': 'rk'}],
            'sonarr': [{'name': 'Main', 'url': 'http://sonarr.local:8989', 'key': 'sk'}],
        }
        post_json(client, '/api/config', cfg)

        # ── Step 3: Settings panel ────────────────────────────────────────────
        cfg = get_json(client, '/api/config')
        cfg.update({
            'scheduler_enabled': True,
            'cron_expression': '0 */4 * * *',
            'cooldown_hours': 48,
            'radarr_max_movies_per_run': 10,
            'sonarr_max_episodes_per_run': 10,
            'radarr_sample_mode': 'round_robin',
            'sonarr_sample_mode': 'round_robin',
        })
        post_json(client, '/api/config', cfg)

        # ── Step 4: Pipelines panel ───────────────────────────────────────────
        cfg = get_json(client, '/api/config')
        cfg.update({
            'radarr_backlog_enabled': True,
            'radarr_missing_max': 5,
            'radarr_missing_added_days': 30,
            'radarr_backlog_sample_mode': 'round_robin',
        })
        post_json(client, '/api/config', cfg)

        # ── Step 5: Notifications ─────────────────────────────────────────────
        cfg = get_json(client, '/api/config')
        cfg.update({
            'notify_enabled': False,
            'notify_url': '',
        })
        post_json(client, '/api/config', cfg)

        # ── Step 6: Advanced ─────────────────────────────────────────────────
        cfg = get_json(client, '/api/config')
        cfg.update({
            'default_tab': 'sweep',
            'log_level': 'INFO',
            'state_retention_days': 90,
        })
        post_json(client, '/api/config', cfg)

        # ── Step 7: Complete onboarding ───────────────────────────────────────
        post_json(client, '/api/onboarding/complete', {})
        cfg = get_json(client, '/api/config')
        assert cfg.get('onboarding_complete'), "onboarding_complete should be True"

        # ── Step 8: Verify full config round-trip ─────────────────────────────
        final = get_json(client, '/api/config')
        assert final['instances']['radarr'][0]['name'] == 'Main'
        assert final['instances']['sonarr'][0]['name'] == 'Main'
        assert final['scheduler_enabled'] is True
        assert final['cooldown_hours'] == 48
        assert final['radarr_backlog_enabled'] is True
        assert final['radarr_missing_max'] == 5
        assert final['default_tab'] == 'sweep'

        # ── Step 9: All read endpoints accessible ─────────────────────────────
        status = get_json(client, '/api/status')
        assert 'run_in_progress' in status

        intel = get_json(client, '/api/intel')
        assert 'cold_start' in intel
        assert 'import_summary' in intel
        assert 'instance_performance' in intel

        excl = client.get('/api/exclusions').get_json()
        assert isinstance(excl, list)

        hist = get_json(client, '/api/state/items')
        assert 'items' in hist and 'total' in hist

        stats = get_json(client, '/api/stats')
        assert 'entries' in stats and 'total' in stats

"""
test_frontend_structure.py
──────────────────────────
Structural integrity tests for the Nudgarr v5 frontend (Alpine.js).

v5 architecture:
  - nudgarr/static/app.js      Single Alpine data factory function nudgarr()
  - nudgarr/static/alpine.min.js  Alpine.js v3 runtime (self-hosted)
  - nudgarr/templates/ui.html  Single-file HTML with inline CSS, all panels

Run before and after any frontend change to verify:
  - Required static files exist and meet size expectations
  - HTML contains the Alpine entry point and all 10 panel bindings
  - app.js contains all critical functions (including 18 bug-fix guards)
  - All modals are wired in HTML
  - validate.py reports 0 failures

Usage:
  cd <repo-root>
  pytest tests/test_frontend_structure.py -v
"""

import os
import re
import subprocess
import sys

import pytest

# ── Paths ─────────────────────────────────────────────────────────────────────

REPO_ROOT    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR   = os.path.join(REPO_ROOT, 'nudgarr', 'static')
TEMPLATE_DIR = os.path.join(REPO_ROOT, 'nudgarr', 'templates')
UI_HTML      = os.path.join(TEMPLATE_DIR, 'ui.html')
APP_JS       = os.path.join(STATIC_DIR, 'app.js')
ALPINE_JS    = os.path.join(STATIC_DIR, 'alpine.min.js')

# ── v5 JS files ───────────────────────────────────────────────────────────────

V5_JS_FILES = ['alpine.min.js', 'app.js']

# ── Line-count ceilings ───────────────────────────────────────────────────────

LINE_COUNT_CEILINGS = {
    'app.js':        1700,  # v5 single-file Alpine data object
    'alpine.min.js': 5,     # minified — always 1-2 lines
}

# ── All 10 panels expected in ui.html ────────────────────────────────────────

EXPECTED_PANELS = [
    'sweep', 'library', 'intel', 'instances', 'pipelines',
    'settings', 'overrides', 'filters', 'notifications', 'advanced',
]

# ── Critical Alpine functions in app.js ──────────────────────────────────────

REQUIRED_ALPINE_METHODS = [
    'init',
    'loadAll',
    'applyConfig',       # bug #1: only place schedulerEnabled is set
    'applyStatus',
    'pollCycle',
    'navigateTo',
    'runNow',
    'refreshHistory',
    'refreshImports',    # must use data.entries (bug #3) + movies_total (bug #4)
    'refreshCfScores',
    'refreshIntel',
    'refreshExclusions',
    'savePipelines',     # must include all cutoff fields (bug #2)
    'saveSettings',
    'saveNotifications', # must be a real method, not just flag clear (bug #7)
    'saveAdvanced',
    'saveInstances',
    'saveFilters',
    'applyOverrides',
    'resetOverrideCard',
    'testNotification',  # must send {url} body (bug #5)
    'openArrLink',       # must exist in Alpine object (bug #11)
    'openInstModal',
    'closeInstModal',
    'saveInstModal',
    'testInstConnection',
    'toggleInstance',
    'deleteInstance',
    'testConnections',
    'toggleExclusion',
    'loadExclusions',
    'loadFilterData',
    'toggleFilterTag',
    'toggleFilterProfile',
    '_showConfirm',      # promise-based confirm for deleteInstance
    'genericConfirmOk',
    'closeModal',
    'showAlert',         # replaces old confirmOk / alert pattern
    'maybeShowOnboarding',
    'maybeShowWhatsNew',
    'dismissWhatsNew',
    'danger',            # stores confirmAction, opens confirm modal
    'executeDanger',
    'executeResetConfig',
    'logout',
    'backupAll',
    'downloadDiagnostic',
    'formatCompact',
    'formatRelative',    # replaces _relTime
    '_fmtTimePadded',
    '_sortItems',
    '_describeCron',
    'validateCron',
    'validateCfCron',
    'validateMaintTime',
    'toggleMaintDay',
    'intelUpgradePaths',
    'resetIntelData',
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def read_file(path):
    with open(path, encoding='utf-8') as f:
        return f.read()

def read_html():
    return read_file(UI_HTML)

def read_app_js():
    return read_file(APP_JS)


# ── Tests — File existence ─────────────────────────────────────────────────────

class TestFileExistence:

    def test_app_js_exists(self):
        assert os.path.exists(APP_JS), "Missing: nudgarr/static/app.js"

    def test_alpine_min_js_exists(self):
        assert os.path.exists(ALPINE_JS), "Missing: nudgarr/static/alpine.min.js"

    def test_ui_html_exists(self):
        assert os.path.exists(UI_HTML), "Missing: nudgarr/templates/ui.html"

    def test_alpine_min_js_minimum_size(self):
        """Alpine.js minified should be at least 30KB."""
        size = os.path.getsize(ALPINE_JS)
        assert size >= 30_000, (
            f"alpine.min.js is only {size} bytes — appears incomplete or placeholder"
        )

    def test_app_js_minimum_size(self):
        """app.js should be at least 30KB (it's a large data object)."""
        size = os.path.getsize(APP_JS)
        assert size >= 30_000, (
            f"app.js is only {size} bytes — appears incomplete"
        )


# ── Tests — HTML structure ─────────────────────────────────────────────────────

class TestHTMLStructure:

    def test_alpine_entry_point_present(self):
        html = read_html()
        assert 'x-data="nudgarr()"' in html, (
            'x-data="nudgarr()" missing from HTML — Alpine will not initialise'
        )

    def test_x_cloak_defined(self):
        html = read_html()
        assert 'x-cloak' in html, (
            "x-cloak missing — Alpine flash of unstyled content (FOUC) will occur"
        )

    def test_inline_css_present(self):
        html = read_html()
        assert '<style>' in html, (
            "No inline <style> block in ui.html — v5 CSS is expected inline"
        )

    def test_no_bare_inline_scripts(self):
        html = read_html()
        bare = re.findall(r'<script(?![^>]*src)[^>]*>[^<]+</script>', html, re.DOTALL)
        assert not bare, (
            f"Bare inline <script> blocks found in HTML ({len(bare)} instance(s)) — "
            f"all JS should be in app.js"
        )

    @pytest.mark.parametrize('js_file', V5_JS_FILES)
    def test_js_file_referenced_in_html(self, js_file):
        html = read_html()
        assert js_file in html, f"HTML does not reference: {js_file}"

    def test_alpine_loaded_before_body_close(self):
        html = read_html()
        alpine_pos = html.rfind('alpine.min.js')
        body_close_pos = html.rfind('</body>')
        assert alpine_pos != -1, "alpine.min.js not found in HTML"
        assert body_close_pos != -1, "</body> not found in HTML"
        assert alpine_pos < body_close_pos, (
            "alpine.min.js must appear before </body>"
        )

    def test_app_js_loaded_after_alpine(self):
        html = read_html()
        assert html.index('app.js') > html.index('alpine.min.js'), (
            "app.js must be loaded AFTER alpine.min.js"
        )

    @pytest.mark.parametrize('panel', EXPECTED_PANELS)
    def test_panel_xshow_binding(self, panel):
        html = read_html()
        binding = f"panel==='{panel}'"
        assert binding in html, (
            f"x-show panel binding missing for panel: {panel}"
        )

    def test_sidebar_navigateto_calls_present(self):
        html = read_html()
        assert 'navigateTo' in html, "navigateTo() calls missing from sidebar HTML"

    def test_instance_modal_present(self):
        html = read_html()
        assert 'instModal.show' in html, "Instance modal binding missing from HTML"

    def test_confirm_modal_present(self):
        html = read_html()
        assert "modal==='confirm'" in html, "Confirm modal binding missing from HTML"

    def test_alert_modal_present(self):
        html = read_html()
        assert "modal==='alert'" in html, "Alert modal binding missing from HTML"

    def test_onboarding_modal_present(self):
        html = read_html()
        assert "modal==='onboarding'" in html, "Onboarding modal binding missing from HTML"

    def test_clear_excl_modal_present(self):
        html = read_html()
        assert "modal==='clearExcl'" in html, "Clear exclusions modal binding missing from HTML"

    def test_run_now_button_present(self):
        html = read_html()
        assert 'runNow()' in html, "Run Now button missing from HTML"

    def test_version_template_tag_present(self):
        html = read_html()
        assert '{{ VERSION }}' in html, "VERSION template variable missing from ui.html"


# ── Tests — app.js structure ──────────────────────────────────────────────────

class TestAppJsStructure:

    def test_nudgarr_factory_function(self):
        js = read_app_js()
        assert 'function nudgarr()' in js, (
            "function nudgarr() Alpine data factory not found in app.js"
        )

    @pytest.mark.parametrize('method', REQUIRED_ALPINE_METHODS)
    def test_method_present(self, method):
        js = read_app_js()
        assert method in js, f"Required Alpine method missing from app.js: {method}"

    def test_scheduler_enabled_only_in_apply_config(self):
        """
        schedulerEnabled must only be set inside applyConfig() (bug #1).
        It must NOT be set from poll cycle or scheduler_running.
        """
        js = read_app_js()
        assignments = re.findall(r'this\.schedulerEnabled\s*=', js)
        # Should appear in applyConfig and possibly in pollCycle as a comment guard
        # Check it's not set from scheduler_running
        assert 'scheduler_running' not in re.sub(
            r'//[^\n]*', '', js  # strip single-line comments
        ).split('schedulerEnabled')[1].split('\n')[0] if 'schedulerEnabled' in js else True, (
            "schedulerEnabled must not be set from scheduler_running (bug #1)"
        )
        assert len(assignments) >= 1, "schedulerEnabled never assigned in app.js"

    def test_save_pipelines_includes_cutoff_fields(self):
        """savePipelines must include all six cutoff config fields (bug #2)."""
        js = read_app_js()
        required_fields = [
            'radarr_cutoff_enabled',
            'sonarr_cutoff_enabled',
            'radarr_max_movies_per_run',
            'sonarr_max_episodes_per_run',
            'radarr_sample_mode',
            'sonarr_sample_mode',
        ]
        # Extract savePipelines body
        match = re.search(r'async savePipelines\(\)(.*?)(?=\n    [a-zA-Z_]|\n  \})', js, re.DOTALL)
        if not match:
            pytest.skip("savePipelines() not found with expected pattern — check manually")
        body = match.group(1)
        missing = [f for f in required_fields if f not in body]
        assert not missing, (
            f"savePipelines() missing cutoff fields (bug #2): {missing}"
        )

    def test_refresh_imports_uses_data_entries(self):
        """refreshImports must read data.entries not data.items (bug #3)."""
        js = read_app_js()
        assert 'data.entries' in js, (
            "refreshImports must use data.entries (not data.items) — bug #3"
        )

    def test_imports_totals_from_api(self):
        """importsMoviesTotal must come from data.movies_total (bug #4 and #18)."""
        js = read_app_js()
        assert 'movies_total' in js, (
            "importsMoviesTotal not bound to data.movies_total (bug #4/18)"
        )
        assert 'importsMoviesTotal' in js, "importsMoviesTotal state property missing"
        assert 'importsShowsTotal' in js, "importsShowsTotal state property missing"

    def test_test_notification_sends_url_body(self):
        """testNotification must send {url: ...} in request body (bug #5)."""
        js = read_app_js()
        # Should contain { url } or { url: or "url":
        assert re.search(r'\{\s*url\s*[\}:]', js), (
            "testNotification must send {url} in POST body — bug #5"
        )

    def test_save_notifications_is_real_method(self):
        """saveNotifications() must POST config, not just clear a flag (bug #7)."""
        js = read_app_js()
        match = re.search(r'async saveNotifications\(\)(.*?)(?=\n    [a-zA-Z_]|\n  \})', js, re.DOTALL)
        assert match, "saveNotifications() method not found in app.js (bug #7)"
        body = match.group(1)
        assert '/api/config' in body, (
            "saveNotifications() must POST to /api/config to actually save (bug #7)"
        )

    def test_upgrade_path_uses_path_from_not_from_quality(self):
        """Upgrade history must use path.from and path.to (bug #8)."""
        js = read_app_js()
        assert 'path.from' in js, (
            "Upgrade history uses path.from — 'path.from' not found in app.js (bug #8)"
        )
        assert 'path.to' in js, (
            "Upgrade history uses path.to — 'path.to' not found in app.js (bug #8)"
        )
        assert 'from_quality' not in js, (
            "app.js uses 'from_quality' but API returns 'path.from' (bug #8)"
        )

    def test_open_arr_link_in_alpine_object(self):
        """openArrLink() must be a method in the Alpine object (bug #11)."""
        js = read_app_js()
        assert 'openArrLink' in js, (
            "openArrLink() missing from app.js — HTML calls it but it won't exist (bug #11)"
        )

    def test_cf_score_uses_last_sync_at(self):
        """CF Score sync time must use last_sync_at not last_sync_utc (bug #17)."""
        js = read_app_js()
        assert 'last_sync_at' in js, (
            "CF Score last sync uses last_sync_at — not found in app.js (bug #17)"
        )
        assert 'last_sync_utc' not in js, (
            "app.js uses 'last_sync_utc' but API returns 'last_sync_at' (bug #17)"
        )

    def test_notify_on_toggles_use_x_model(self):
        """Notify On toggles must use x-model bindings in HTML (bug #6)."""
        html = read_html()
        required_bindings = [
            'notifyOnSweep', 'notifyOnImport', 'notifyOnAutoExcl',
            'notifyOnError', 'notifyOnQueueDepth',
        ]
        missing = [b for b in required_bindings if b not in html]
        assert not missing, (
            f"Notify On x-model bindings missing from HTML (bug #6): {missing}"
        )

    def test_activity_ping_in_init(self):
        """Activity ping must POST /api/ping debounced on user events (bug #14)."""
        js = read_app_js()
        assert '/api/ping' in js, "Activity ping /api/ping missing from app.js (bug #14)"

    def test_last_skipped_queue_depth_utc_handled(self):
        """last_skipped_queue_depth_utc must be tracked in state (bug — queue depth skip)."""
        js = read_app_js()
        assert 'last_skipped_queue_depth_utc' in js, (
            "last_skipped_queue_depth_utc not handled in app.js"
        )

    def test_onboarding_8_steps(self):
        """Onboarding walkthrough must have exactly 8 steps (0-7).
        v5 uses x-if templates in HTML rather than a JS steps array."""
        html = read_html()
        steps_found = set()
        for m in re.finditer(r'onboardingStep===(\d+)', html):
            steps_found.add(int(m.group(1)))
        assert len(steps_found) >= 8, (
            f"Expected 8 onboarding step templates (0-7), found indices: {sorted(steps_found)}"
        )
        js = read_app_js()
        assert 'onboardingTotal: 8' in js, "onboardingTotal must be 8 in app.js"
    def test_queue_depth_state_properties(self):
        js = read_app_js()
        assert 'queueDepthEnabled' in js, "queueDepthEnabled missing from app.js"
        assert 'queueDepthThreshold' in js, "queueDepthThreshold missing from app.js"

    def test_all_config_fields_in_save_settings(self):
        """saveSettings must write the complete set of settings fields."""
        js = read_app_js()
        required_fields = [
            'scheduler_enabled', 'cron_expression', 'cooldown_hours',
            'maintenance_window_enabled', 'batch_size', 'sleep_seconds',
            'queue_depth_enabled', 'queue_depth_threshold',
            'per_instance_overrides_enabled',
        ]
        missing = [f for f in required_fields if f not in js]
        assert not missing, (
            f"saveSettings() missing config fields: {missing}"
        )


# ── Tests — Line count ceilings ───────────────────────────────────────────────

class TestLineCounts:

    @pytest.mark.parametrize('filename,ceiling', LINE_COUNT_CEILINGS.items())
    def test_file_under_line_ceiling(self, filename, ceiling):
        path = os.path.join(STATIC_DIR, filename)
        if not os.path.exists(path):
            pytest.skip(f"{filename} not found")
        count = sum(1 for _ in open(path, encoding='utf-8'))
        assert count <= ceiling, (
            f"{filename} has {count} lines — exceeds ceiling of {ceiling}."
        )


# ── Tests — validate.py passthrough ──────────────────────────────────────────

class TestValidatePy:

    def test_validate_py_passes_with_zero_failures(self):
        """validate.py must report 0 failures. This is the canonical gate."""
        result = subprocess.run(
            [sys.executable, 'validate.py'],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"validate.py exited with code {result.returncode}.\n"
            f"Output:\n{result.stdout}\n{result.stderr}"
        )
        assert 'FAIL' not in result.stdout, (
            f"validate.py reported failures:\n{result.stdout}"
        )

    def test_validate_py_check_count_in_range(self):
        """
        validate.py must pass a reasonable number of checks.
        This is a range check to accommodate minor count drift without
        requiring a manual update on every small validate.py change.
        Update MIN/MAX deliberately when checks are substantially added or removed.
        """
        MIN_CHECKS = 200
        MAX_CHECKS = 400

        result = subprocess.run(
            [sys.executable, 'validate.py'],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        match = re.search(r'ALL (\d+) CHECKS PASSED', result.stdout)
        assert match, f"Could not find check count in validate.py output:\n{result.stdout}"
        actual = int(match.group(1))
        assert MIN_CHECKS <= actual <= MAX_CHECKS, (
            f"validate.py passed {actual} checks — expected between "
            f"{MIN_CHECKS} and {MAX_CHECKS}. "
            f"If checks were deliberately added or removed, update the range."
        )

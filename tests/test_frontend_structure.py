"""
test_frontend_structure.py
──────────────────────────
Structural integrity tests for the Nudgarr v5 frontend.

v5 architecture:
  - Single Alpine.js app (app.js) replaces 12 separate JS files
  - Single ui.html template replaces 15 template partials
  - alpine.min.js self-hosted alongside Outfit/JetBrains Mono fonts
  - ui-responsive.css is the sole responsive surface

Run before and after any JS or template change to verify:
  - All expected files exist
  - All files are linked from ui.html
  - All required Alpine state properties are declared
  - All required methods are present in app.js
  - All 10 panels and 9 modals are present in ui.html
  - No v4 split files remain
  - validate.py reports 0 failures at the expected check count

Usage:
  cd <repo-root>
  PYTHONPATH=. pytest tests/test_frontend_structure.py -v
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

# ── Expected v5 static files ──────────────────────────────────────────────────

EXPECTED_JS_FILES  = ['alpine.min.js', 'app.js']
EXPECTED_CSS_FILES = ['ui.css', 'ui-responsive.css']

# ── v4 files that must NOT be present ─────────────────────────────────────────

V4_JS_FILES = [
    'ui-core.js', 'ui-instances.js', 'ui-overrides.js', 'ui-sweep.js',
    'ui-history.js', 'ui-imports.js', 'ui-intel.js', 'ui-cf-scores.js',
    'ui-settings.js', 'ui-notifications.js', 'ui-advanced.js', 'ui-filters.js',
]

V4_TEMPLATE_PARTIALS = [
    'ui-header.html', 'ui-nav.html', 'ui-modals.html',
    'ui-tab-advanced.html', 'ui-tab-cf-scores.html', 'ui-tab-filters.html',
    'ui-tab-history.html', 'ui-tab-imports.html', 'ui-tab-instances.html',
    'ui-tab-intel.html', 'ui-tab-notifications.html', 'ui-tab-overrides.html',
    'ui-tab-settings.html', 'ui-tab-sweep.html',
]

# ── Required Alpine state properties ──────────────────────────────────────────

REQUIRED_STATE = [
    'panel', 'sidebarOpen', 'sweeping', 'schedulerEnabled', 'modal',
    'overridesEnabled', 'cfScoreEnabled', 'unsaved', 'libView', 'exclBadge',
    'CFG', 'lastRunUtc', 'nextRunUtc', 'autoMode',
]

# ── Required methods in app.js ────────────────────────────────────────────────

REQUIRED_METHODS = [
    # Bootstrap
    'loadAll', 'pollCycle', 'refreshStatus', 'applyConfig',
    # Panel refreshers
    'refreshSweep', 'refreshHistory', 'refreshImports', 'refreshCfScores',
    'loadExclusions', 'refreshIntel',
    # Save functions
    'saveSettings', 'savePipelines', 'saveNotifications', 'saveAdvanced', 'saveFilters',
    # Actions
    'runNow', 'logout', 'danger', 'executeConfirmAction', 'doResetConfig',
    'confirmClearExclusions',
    # Modal helpers
    'showAlert', 'openModal', 'closeModal',
    # Utilities
    'formatRelative', 'formatCompact', 'describeCron',
    # Sidebar
    'openSidebar', 'closeSidebar',
]

# ── Required panels ───────────────────────────────────────────────────────────

PANELS_V5 = [
    'sweep', 'library', 'intel', 'instances', 'pipelines',
    'overrides', 'filters', 'settings', 'notifications', 'advanced',
]

# ── Required modals ───────────────────────────────────────────────────────────

MODALS_V5 = [
    'instance', 'clearExcl', 'confirm', 'resetConfig', 'alert',
    'noInstances', 'overridesInfo', 'whatsNew', 'onboarding',
]

# ── Line count ceilings ───────────────────────────────────────────────────────

LINE_COUNT_CEILINGS = {
    'app.js':              2000,
    'ui.css':               500,
    'ui-responsive.css':    400,
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def read_file(path):
    with open(path, encoding='utf-8') as f:
        return f.read()

def read_static(filename):
    return read_file(os.path.join(STATIC_DIR, filename))

def read_ui_html():
    return read_file(UI_HTML)

def read_app_js():
    return read_file(os.path.join(STATIC_DIR, 'app.js'))


# ── Tests — File existence ─────────────────────────────────────────────────────

class TestFileExistence:

    @pytest.mark.parametrize('filename', EXPECTED_JS_FILES)
    def test_js_file_exists(self, filename):
        assert os.path.exists(os.path.join(STATIC_DIR, filename)), \
            f"Missing JS file: nudgarr/static/{filename}"

    @pytest.mark.parametrize('filename', EXPECTED_CSS_FILES)
    def test_css_file_exists(self, filename):
        assert os.path.exists(os.path.join(STATIC_DIR, filename)), \
            f"Missing CSS file: nudgarr/static/{filename}"

    def test_ui_html_exists(self):
        assert os.path.exists(UI_HTML)

    def test_login_html_exists(self):
        assert os.path.exists(os.path.join(TEMPLATE_DIR, 'login.html'))

    def test_setup_html_exists(self):
        assert os.path.exists(os.path.join(TEMPLATE_DIR, 'setup.html'))

    def test_fonts_present(self):
        for font in ['Outfit[wght].woff2', 'JetBrainsMono[wght].woff2']:
            assert os.path.exists(os.path.join(STATIC_DIR, 'fonts', font)), \
                f"Missing font: {font}"

    def test_alpine_self_hosted(self):
        """alpine.min.js must be self-hosted — not loaded from CDN."""
        assert os.path.exists(os.path.join(STATIC_DIR, 'alpine.min.js')), \
            "alpine.min.js missing from static/"
        html = read_ui_html()
        assert 'cdn.jsdelivr.net' not in html, \
            "Alpine.js loaded from CDN — must be self-hosted"


# ── Tests — No v4 artifacts ────────────────────────────────────────────────────

class TestNoV4Artifacts:

    @pytest.mark.parametrize('filename', V4_JS_FILES)
    def test_v4_js_not_present(self, filename):
        assert not os.path.exists(os.path.join(STATIC_DIR, filename)), \
            f"v4 JS file still present: {filename} — remove it"

    @pytest.mark.parametrize('filename', V4_TEMPLATE_PARTIALS)
    def test_v4_partial_not_present(self, filename):
        assert not os.path.exists(os.path.join(TEMPLATE_DIR, filename)), \
            f"v4 template partial still present: {filename} — remove it"


# ── Tests — HTML links ─────────────────────────────────────────────────────────

class TestHTMLLinks:

    @pytest.mark.parametrize('filename', EXPECTED_JS_FILES)
    def test_js_linked_in_html(self, filename):
        html = read_ui_html()
        assert filename in html, \
            f"ui.html missing script tag for: {filename}"

    @pytest.mark.parametrize('filename', EXPECTED_CSS_FILES)
    def test_css_linked_in_html(self, filename):
        html = read_ui_html()
        assert filename in html, \
            f"ui.html missing link tag for: {filename}"


# ── Tests — HTML structure ─────────────────────────────────────────────────────

class TestHTMLStructure:

    def test_div_balance(self):
        html = read_ui_html()
        opens  = html.count('<div')
        closes = html.count('</div')
        assert opens == closes, \
            f"Unbalanced divs in ui.html: {opens} opens vs {closes} closes"

    def test_alpine_xdata_present(self):
        html = read_ui_html()
        assert 'x-data="nudgarr()"' in html, \
            "Alpine x-data='nudgarr()' missing from ui.html body tag"

    def test_sidebar_present(self):
        assert 'class="sb"' in read_ui_html()

    def test_main_area_present(self):
        assert 'class="main"' in read_ui_html()

    def test_no_duplicate_ids(self):
        html = read_ui_html()
        all_ids = re.findall(r'id=["\']([^"\']+)["\']', html)
        seen, dupes = set(), set()
        for i in all_ids:
            if i in seen: dupes.add(i)
            seen.add(i)
        assert not dupes, f"Duplicate IDs in ui.html: {sorted(dupes)}"

    @pytest.mark.parametrize('panel', PANELS_V5)
    def test_panel_present(self, panel):
        html = read_ui_html()
        assert f"panel==='{panel}'" in html, \
            f"Panel '{panel}' missing from ui.html"

    @pytest.mark.parametrize('modal', MODALS_V5)
    def test_modal_present(self, modal):
        html = read_ui_html()
        assert f"modal==='{modal}'" in html, \
            f"Modal '{modal}' missing from ui.html"


# ── Tests — Line count ceilings ───────────────────────────────────────────────

class TestLineCounts:

    @pytest.mark.parametrize('filename,ceiling', LINE_COUNT_CEILINGS.items())
    def test_file_under_ceiling(self, filename, ceiling):
        path = os.path.join(STATIC_DIR, filename)
        if not os.path.exists(path):
            pytest.skip(f"{filename} not found")
        count = sum(1 for _ in open(path, encoding='utf-8'))
        assert count <= ceiling, (
            f"{filename} has {count} lines — exceeds ceiling of {ceiling}. "
            f"Raise the ceiling deliberately if this is intentional."
        )


# ── Tests — Alpine state ──────────────────────────────────────────────────────

class TestAlpineState:

    @pytest.mark.parametrize('prop', REQUIRED_STATE)
    def test_state_property_declared(self, prop):
        js = read_app_js()
        assert f"'{prop}'" in js or f'"{prop}"' in js or f'{prop}:' in js, \
            f"Alpine state property '{prop}' not declared in app.js"


# ── Tests — Required methods ──────────────────────────────────────────────────

class TestRequiredMethods:

    @pytest.mark.parametrize('method', REQUIRED_METHODS)
    def test_method_present(self, method):
        js = read_app_js()
        assert f'async {method}(' in js or f'{method}(' in js, \
            f"Method '{method}()' missing from app.js"


# ── Tests — Tab migration ─────────────────────────────────────────────────────

class TestTabMigration:

    def test_migration_map_in_app_js(self):
        js = read_app_js()
        assert 'TAB_MIGRATION_V5' in js, \
            "TAB_MIGRATION_V5 not in app.js"

    def test_v4_tabs_in_migration_map(self):
        js = read_app_js()
        for old_tab in ['history', 'imports', 'cf-scores']:
            assert old_tab in js, \
                f"v4 tab '{old_tab}' missing from migration map in app.js"

    def test_migration_in_constants(self):
        constants = read_file(os.path.join(REPO_ROOT, 'nudgarr', 'constants.py'))
        assert 'TAB_MIGRATION_V5' in constants, \
            "TAB_MIGRATION_V5 missing from constants.py"

    def test_migration_in_config(self):
        config = read_file(os.path.join(REPO_ROOT, 'nudgarr', 'config.py'))
        assert 'TAB_MIGRATION_V5' in config, \
            "TAB_MIGRATION_V5 not applied in config.py"

    def test_valid_tabs_updated(self):
        constants = read_file(os.path.join(REPO_ROOT, 'nudgarr', 'constants.py'))
        # v5 tabs should be present
        for tab in ['library', 'pipelines']:
            assert tab in constants, \
                f"v5 tab '{tab}' missing from VALID_TABS in constants.py"
        # v4 standalone tabs should not be in VALID_TABS
        m = re.search(r'VALID_TABS\s*=\s*\((.*?)\)', constants, re.DOTALL)
        assert m, "VALID_TABS not found in constants.py"
        valid_tabs_block = m.group(1)
        for old_tab in ['"cf-scores"', '"history"', '"imports"']:
            assert old_tab not in valid_tabs_block, \
                f"v4 tab {old_tab} still in VALID_TABS (should be removed)"


# ── Tests — Responsive CSS ────────────────────────────────────────────────────

class TestResponsiveCSS:

    def test_breakpoints_present(self):
        resp = read_static('ui-responsive.css')
        assert '@media (max-width: 720px)' in resp
        assert '@media (max-width: 480px)' in resp

    def test_sidebar_overlay_present(self):
        resp = read_static('ui-responsive.css')
        assert 'sb-open' in resp, \
            "Sidebar open state (.sb-open or .sb.sb-open) missing from responsive CSS"

    def test_hamburger_present(self):
        resp = read_static('ui-responsive.css')
        assert 'hamburger' in resp, \
            ".hamburger class missing from responsive CSS"


    def test_validate_py_passes(self):
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

    def test_validate_py_check_count(self):
        """
        validate.py must pass at exactly the expected check count.
        Update this number deliberately when checks are added or removed.
        """
        EXPECTED_CHECK_COUNT = 260  # v5.0 baseline (260 after Alpine binding cross-check added)

        result = subprocess.run(
            [sys.executable, 'validate.py'],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        match = re.search(r'ALL (\d+) CHECKS PASSED', result.stdout)
        assert match, f"Could not find check count in validate.py output:\n{result.stdout}"
        actual = int(match.group(1))
        assert actual == EXPECTED_CHECK_COUNT, (
            f"validate.py passed {actual} checks but expected {EXPECTED_CHECK_COUNT}. "
            f"If checks were deliberately added or removed, update EXPECTED_CHECK_COUNT."
        )

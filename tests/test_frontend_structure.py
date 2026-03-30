"""
test_frontend_structure.py
──────────────────────────
Structural integrity tests for the Nudgarr frontend.

Run before and after any JS or template refactor to verify:
  - All expected files exist
  - All files are linked from ui.html in the correct order
  - No function is defined more than once across the JS codebase
      (known intentional overloads are explicitly whitelisted)
  - Every onclick handler in ui.html resolves to a defined JS function
  - Every el('id') call in JS resolves to an id defined in ui.html
  - Cross-file function calls respect script load order
      (a file must not call a function defined in a later-loading file
       at parse time — deferred calls inside function bodies are OK
       only when the calling function itself is never invoked at parse time)
  - All shared state variables are declared in ui-core.js
  - No JS file exceeds the agreed line-count ceiling
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

# ── Expected JS files and their load order (index = position in ui.html) ──────

JS_LOAD_ORDER = [
    'ui-core.js',
    'ui-instances.js',
    'ui-overrides.js',
    'ui-sweep.js',
    'ui-history.js',
    'ui-imports.js',
    'ui-intel.js',
    'ui-cf-scores.js',
    'ui-settings.js',
    'ui-notifications.js',
    'ui-advanced.js',
    'ui-filters.js',
    'ui-mobile-core.js',
    'ui-mobile-landscape.js',
    'ui-mobile-landscape-filters.js',
    'ui-mobile-landscape-exec.js',
    'ui-mobile-portrait-home.js',
    'ui-mobile-portrait-history.js',
    'ui-mobile-portrait-settings.js',
    'ui-mobile-portrait.js',
]

# ── Line-count ceilings per file (0 = no ceiling set) ─────────────────────────
# Any file that exceeds this will fail. Update when a deliberate large file
# is accepted (e.g. after a future refactor raises the ceiling).

LINE_COUNT_CEILINGS = {
    'ui-core.js':                      400,
    'ui-instances.js':                 450,
    'ui-overrides.js':                 470,  # raised v4.2.0: +cf_max override field and CF Score group
    'ui-sweep.js':                     500,  # raised v4.2.0: Sweep tab redesign
    'ui-history.js':                   380,
    'ui-imports.js':                   250,
    'ui-intel.js':                     550,
    'ui-cf-scores.js':                 450,  # CF Score tab (v4.2.0)
    'ui-settings.js':                  660,  # raised v4.2.0: +syncMaintUi/validateMaintTime/toggleMaintDay + load/save
    'ui-notifications.js':             120,
    'ui-advanced.js':                  300,  # raised v4.2.0: +CF Score toggle functions
    'ui-filters.js':                   470,  # raised v4.2.0: CF filter sync modal handlers
    'ui-mobile-core.js':               300,
    'ui-mobile-landscape.js':          460,
    'ui-mobile-landscape-filters.js':  340,
    'ui-mobile-landscape-exec.js':     370,
    'ui-mobile-portrait-home.js':      320,
    'ui-mobile-portrait-history.js':   310,
    'ui-mobile-portrait-settings.js':  300,
    'ui-mobile-portrait.js':           200,
}

# ── Known intentional duplicate function names (defined in two files by design)
# Format: frozenset of the two filenames that each define the function.

KNOWN_DUPLICATE_FUNCTIONS = {
    'updateBacklogLabel': frozenset({'ui-mobile-landscape.js', 'ui-overrides.js'}),
    'updateNotifyLabel':  frozenset({'ui-mobile-landscape.js', 'ui-overrides.js'}),
}

# ── Shared state that must be declared in ui-core.js ─────────────────────────

SHARED_STATE_VARS = [
    'CFG',
    'PAGE',
    'HISTORY_TOTAL',
    'IMPORTS_PAGE',
    'IMPORTS_TOTAL',
    'IMPORTS_PERIOD',
    'SWEEP_FEED_PAGE',
    'SWEEP_FEED_TOTAL',
    'ALL_INSTANCES',
    'ACTIVE_TAB',
    'HISTORY_SORT',
    'IMPORTS_SORT',
    'EXCLUSIONS_SET',
    'EXCL_FILTER_ACTIVE',
    'MOBILE',
]

# ── Cross-file load-order dependencies ────────────────────────────────────────
# These are calls inside function bodies (not at parse time) where the called
# function lives in a later-loading file. They are legitimate because the caller
# only executes after all scripts have loaded (user interaction / poll cycle).
# Listed here so the load-order test can explicitly whitelist them rather than
# silently ignore the issue.

DEFERRED_CROSS_FILE_CALLS = {
    # ui-settings.js calls these inside _onTabShown / showTab — only invoked
    # at runtime after all scripts have loaded.
    'ui-settings.js': {
        'fillNotifications',    # defined in ui-notifications.js
        'fillAdvanced',         # defined in ui-advanced.js
        'fillFilters',          # defined in ui-filters.js
        '_filterHasPending',    # defined in ui-filters.js
        'renderOverridesCards', # defined in ui-overrides.js (loads before — OK, listed for completeness)
    },
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def read_file(path):
    with open(path, encoding='utf-8') as f:
        return f.read()

def read_js(filename):
    return read_file(os.path.join(STATIC_DIR, filename))

def read_html():
    # Read ui.html plus all template partials as a single combined string
    # so ID and onclick checks cover elements that moved to partial files.
    combined = read_file(UI_HTML)
    for partial in sorted(os.listdir(TEMPLATE_DIR)):
        if partial != 'ui.html' and partial.startswith('ui') and partial.endswith('.html'):
            p = os.path.join(TEMPLATE_DIR, partial)
            if os.path.exists(p):
                combined += '\n' + read_file(p)
    return combined

def all_js_content():
    """Combined content of all JS files in load order."""
    parts = []
    for fn in JS_LOAD_ORDER:
        path = os.path.join(STATIC_DIR, fn)
        if os.path.exists(path):
            parts.append(read_js(fn))
    return '\n'.join(parts)

def get_defined_functions(content):
    """Return set of function names defined at top level in JS content."""
    return set(re.findall(r'^(?:async\s+)?function\s+([a-zA-Z_][a-zA-Z0-9_]*)', content, re.MULTILINE))

def get_defined_functions_per_file():
    """Return dict mapping filename -> set of defined function names."""
    result = {}
    for fn in JS_LOAD_ORDER:
        path = os.path.join(STATIC_DIR, fn)
        if os.path.exists(path):
            result[fn] = get_defined_functions(read_js(fn))
    return result

def get_onclick_functions(html):
    """Extract bare function names from onclick attributes in HTML."""
    raw = re.findall(r'onclick="([^"]+)"', html)
    functions = set()
    for handler in raw:
        # Extract leading function name (before '(' or '.')
        match = re.match(r'([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', handler)
        if match:
            functions.add(match.group(1))
    return functions

def get_el_calls(content):
    """Return set of element IDs referenced via el('id') in JS."""
    return set(re.findall(r"el\('([^']+)'\)", content))

def get_html_ids(html):
    """Return set of element IDs declared in HTML."""
    return set(re.findall(r'id="([^"]+)"', html))

def get_script_load_order(html):
    """Return list of JS filenames in the order they appear as script tags."""
    return re.findall(r"filename='([^']+\.js)'", html)


# ── Tests — File existence ─────────────────────────────────────────────────────

class TestFileExistence:

    @pytest.mark.parametrize('filename', JS_LOAD_ORDER)
    def test_js_file_exists(self, filename):
        path = os.path.join(STATIC_DIR, filename)
        assert os.path.exists(path), f"Missing JS file: nudgarr/static/{filename}"

    def test_ui_html_exists(self):
        assert os.path.exists(UI_HTML), "Missing template: nudgarr/templates/ui.html"


# ── Tests — HTML links ────────────────────────────────────────────────────────

class TestHTMLLinks:

    @pytest.mark.parametrize('filename', JS_LOAD_ORDER)
    def test_js_file_linked_in_html(self, filename):
        html = read_html()
        assert filename in html, \
            f"ui.html is missing a <script> tag for: {filename}"

    def test_script_load_order_matches_expected(self):
        html = read_html()
        actual_order = get_script_load_order(html)
        # Filter to only files in our known list
        actual_known = [f for f in actual_order if f in JS_LOAD_ORDER]
        assert actual_known == JS_LOAD_ORDER, (
            f"Script load order in ui.html does not match expected.\n"
            f"Expected: {JS_LOAD_ORDER}\n"
            f"Got:      {actual_known}"
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
            f"{filename} has {count} lines — exceeds ceiling of {ceiling}. "
            f"Consider splitting or raise the ceiling deliberately."
        )


# ── Tests — Duplicate functions ───────────────────────────────────────────────

class TestNoDuplicateFunctions:

    def test_no_unexpected_duplicate_function_definitions(self):
        per_file = get_defined_functions_per_file()
        # Build inverse map: function name -> list of files that define it
        fn_to_files = {}
        for filename, fns in per_file.items():
            for fn in fns:
                fn_to_files.setdefault(fn, []).append(filename)

        unexpected_dupes = {}
        for fn, files in fn_to_files.items():
            if len(files) < 2:
                continue
            known = KNOWN_DUPLICATE_FUNCTIONS.get(fn)
            if known and frozenset(files) == known:
                continue  # whitelisted intentional duplicate
            unexpected_dupes[fn] = files

        assert not unexpected_dupes, (
            "Unexpected duplicate function definitions found:\n" +
            '\n'.join(f"  {fn}: {files}" for fn, files in sorted(unexpected_dupes.items()))
        )


# ── Tests — onclick resolution ────────────────────────────────────────────────

class TestOnclickResolution:

    # Functions that exist at runtime but are not in our static JS files
    # (e.g. browser builtins, or intentionally inlined)
    IGNORED_ONCLICK_FUNCTIONS = {
        'el',              # inline helper used in some onclick attributes
        'event',           # browser event object access
        'confirmResolve',  # assigned dynamically in showConfirm() — not a function declaration
    }

    def test_all_onclick_functions_defined_in_js(self):
        html = read_html()
        js  = all_js_content()
        defined = get_defined_functions(js)
        onclick_fns = get_onclick_functions(html) - self.IGNORED_ONCLICK_FUNCTIONS
        missing = {fn for fn in onclick_fns if fn not in defined}
        assert not missing, (
            "onclick handlers in ui.html call functions not defined in any JS file:\n" +
            '\n'.join(f"  {fn}()" for fn in sorted(missing))
        )


# ── Tests — el() ID resolution ────────────────────────────────────────────────

class TestElementIdResolution:

    # IDs that are injected dynamically at runtime (not present in static HTML)
    DYNAMIC_IDS = {
        # Instance cards rendered by renderInstances()
        'radarrList', 'sonarrList',
        # Sweep cards rendered by refreshSweep()
        'sweepRadarrList', 'sweepSonarrList',
        # Status dots injected per instance
    }

    def test_el_calls_reference_existing_ids(self):
        js   = all_js_content()
        html = read_html()
        el_calls = get_el_calls(js) - self.DYNAMIC_IDS
        html_ids = get_html_ids(html)
        missing  = el_calls - html_ids
        # Filter out IDs that look like dynamic patterns (contain variables)
        static_missing = {i for i in missing if re.match(r'^[a-zA-Z][a-zA-Z0-9_\-]*$', i)}
        assert not static_missing, (
            "el() calls in JS reference IDs not found in ui.html:\n" +
            '\n'.join(f"  el('{i}')" for i in sorted(static_missing))
        )


# ── Tests — Shared state location ─────────────────────────────────────────────

class TestSharedState:

    @pytest.mark.parametrize('var_name', SHARED_STATE_VARS)
    def test_shared_state_declared_in_core(self, var_name):
        core = read_js('ui-core.js')
        # Match let/const declaration at line start
        pattern = rf'^(?:let|const)\s+{re.escape(var_name)}\b'
        assert re.search(pattern, core, re.MULTILINE), (
            f"Shared state variable '{var_name}' is not declared in ui-core.js"
        )

    @pytest.mark.parametrize('var_name', SHARED_STATE_VARS)
    def test_shared_state_not_redeclared_in_other_files(self, var_name):
        """Shared state should be declared once in ui-core.js, not in other files."""
        offenders = []
        for fn in JS_LOAD_ORDER:
            if fn == 'ui-core.js':
                continue
            path = os.path.join(STATIC_DIR, fn)
            if not os.path.exists(path):
                continue
            content = read_js(fn)
            pattern = rf'^(?:let|const)\s+{re.escape(var_name)}\b'
            if re.search(pattern, content, re.MULTILINE):
                offenders.append(fn)
        assert not offenders, (
            f"Shared state '{var_name}' is re-declared in: {offenders}. "
            f"It must only be declared in ui-core.js."
        )


# ── Tests — Load order safety ──────────────────────────────────────────────────

class TestLoadOrder:

    def test_ui_imports_only_calls_sort_helpers_from_ui_history(self):
        """
        ui-imports.js calls applySortIndicators() and sortItems() which are
        defined in ui-history.js. ui-history.js loads before ui-imports.js.
        This test verifies that relationship is intact.
        """
        imports_content = read_js('ui-imports.js')
        history_content = read_js('ui-history.js')
        history_order   = JS_LOAD_ORDER.index('ui-history.js')
        imports_order   = JS_LOAD_ORDER.index('ui-imports.js')
        assert history_order < imports_order, \
            "ui-history.js must load before ui-imports.js"

        for fn in ('applySortIndicators', 'sortItems'):
            assert fn in imports_content, \
                f"ui-imports.js no longer calls {fn} — test may be stale"
            assert re.search(rf'^function {fn}\b', history_content, re.MULTILINE), \
                f"{fn} is no longer defined in ui-history.js"

    def test_deferred_cross_file_calls_are_inside_functions(self):
        """
        Functions called across file boundaries in ui-settings.js must be
        inside function bodies (deferred), not at parse/module level.
        This ensures they are only invoked after all scripts have loaded.
        """
        content = read_js('ui-settings.js')
        deferred = DEFERRED_CROSS_FILE_CALLS.get('ui-settings.js', set())
        for fn in deferred:
            if fn not in content:
                continue  # function not called here at all — test stays green
            # Verify the call appears inside a function body:
            # check that it's not at column 0 (i.e. not a top-level statement)
            for line in content.splitlines():
                stripped = line.strip()
                if re.match(rf'{re.escape(fn)}\s*\(', stripped):
                    assert not line.startswith(fn), (
                        f"{fn}() appears to be called at the top level in "
                        f"ui-settings.js — it must only be called inside a "
                        f"function body to be safe across script load order."
                    )

    def test_notifications_loads_after_settings(self):
        settings_order      = JS_LOAD_ORDER.index('ui-settings.js')
        notifications_order = JS_LOAD_ORDER.index('ui-notifications.js')
        assert settings_order < notifications_order, \
            "ui-settings.js must load before ui-notifications.js"

    def test_advanced_loads_after_settings(self):
        settings_order = JS_LOAD_ORDER.index('ui-settings.js')
        advanced_order = JS_LOAD_ORDER.index('ui-advanced.js')
        assert settings_order < advanced_order, \
            "ui-settings.js must load before ui-advanced.js"

    def test_filters_loads_after_settings(self):
        settings_order = JS_LOAD_ORDER.index('ui-settings.js')
        filters_order  = JS_LOAD_ORDER.index('ui-filters.js')
        assert settings_order < filters_order, \
            "ui-settings.js must load before ui-filters.js"

    def test_landscape_filters_loads_after_landscape(self):
        landscape_order         = JS_LOAD_ORDER.index('ui-mobile-landscape.js')
        landscape_filters_order = JS_LOAD_ORDER.index('ui-mobile-landscape-filters.js')
        assert landscape_order < landscape_filters_order, \
            "ui-mobile-landscape.js must load before ui-mobile-landscape-filters.js"

    def test_landscape_exec_loads_last_among_landscape_files(self):
        landscape_order         = JS_LOAD_ORDER.index('ui-mobile-landscape.js')
        landscape_filters_order = JS_LOAD_ORDER.index('ui-mobile-landscape-filters.js')
        landscape_exec_order    = JS_LOAD_ORDER.index('ui-mobile-landscape-exec.js')
        assert landscape_exec_order > landscape_order, \
            "ui-mobile-landscape-exec.js must load after ui-mobile-landscape.js"
        assert landscape_exec_order > landscape_filters_order, \
            "ui-mobile-landscape-exec.js must load after ui-mobile-landscape-filters.js"


# ── Tests — Split integrity ───────────────────────────────────────────────────

class TestSplitIntegrity:
    """
    Verify that the split files contain the functions they are expected to own.
    These tests act as a guard against functions accidentally landing in the
    wrong file during a refactor.
    """

    EXPECTED_OWNERS = {
        # file -> functions that must be defined there
        'ui-notifications.js': {
            'fillNotifications', 'syncNotifyUi', 'toggleNotifyUrl',
            'testNotification', 'saveNotifications',
        },
        'ui-advanced.js': {
            'fillAdvanced', 'syncAutoExclUi', 'syncAuthUi',
            'markUnsaved', 'syncBacklogUi', 'saveAdvanced',
            'onAutoExclDisabledKeep', 'onAutoExclDisabledClear',
            'logout', 'resetConfig', 'clearLog',
            'backupAll', 'downloadDiagnostic',
        },
        'ui-settings.js': {
            'showTab', '_doShowTab', '_onTabShown',
            'fillSettings', 'saveSettings', 'validateCronExpr', 'describeCron',
            'checkCooldownWarning', 'maybeShowWhatsNew', 'dismissWhatsNew',
            'renderOnboardingStep', 'onboardingStep', 'maybeShowOnboarding',
            'replayOnboarding', 'syncCutoffUi',
        },
        'ui-history.js': {
            'loadExclusions', 'toggleExclusion', 'refreshAutoExclBadge',
            'onAutoExclBadgeClick', 'toggleExclusionsFilter',
            'refreshHistory', 'sortHistory', 'applySortIndicators', 'sortItems',
            'prevPage', 'nextPage', 'filterHistorySearch', 'clearHistorySearch',
            'pruneState', 'clearState',
            'openClearExclusionsModal', 'closeClearExclusionsModal',
            'selectClearExclOption', 'confirmClearExclusions',
        },
        'ui-imports.js': {
            'refreshImports', 'sortImports', 'prevStatsPage', 'nextStatsPage',
            'filterImportsSearch', 'clearImportsSearch', 'onImportsPeriodChange',
            'checkImportsNow', 'clearImports', 'buildUpgradeCell', 'fmtDate',
        },
        'ui-sweep.js': {
            'refreshSweep', 'showSweepNoInstancesModal', 'runNow',
            'loadSweepFeed', 'prevSweepFeed', 'nextSweepFeed', 'goToSweepFeedPage',
        },
        'ui-filters.js': {
            'saveFilters', 'fillFilters', 'closeCfFilterSyncModal', 'syncCfIndexFromModal',
        },
        'ui-mobile-landscape-filters.js': {
            'lsFiltersRenderRail', 'lsFiltersSelectInst', 'lsFiltersRenderPanel',
            'lsFiltersSearch', 'lsFiltersToggle', 'lsFiltersLoad', 'lsFiltersApply',
        },
        'ui-mobile-landscape.js': {
            'lsOvRenderRail', 'lsOvSelectInstance', 'lsOvRenderPanel',
            'lsOvStep', 'lsOvHoldStart', 'lsOvHoldEnd', 'lsOvMarkDirty',
            'lsOvUpdateFooter', 'lsOvApply', 'lsOvReset',
        },
    }

    @pytest.mark.parametrize('filename,expected_fns', EXPECTED_OWNERS.items())
    def test_file_owns_expected_functions(self, filename, expected_fns):
        path = os.path.join(STATIC_DIR, filename)
        if not os.path.exists(path):
            pytest.skip(f"{filename} not found")
        defined = get_defined_functions(read_js(filename))
        missing = expected_fns - defined
        assert not missing, (
            f"{filename} is missing expected functions:\n" +
            '\n'.join(f"  {fn}" for fn in sorted(missing))
        )

    @pytest.mark.parametrize('filename,expected_fns', EXPECTED_OWNERS.items())
    def test_functions_not_duplicated_in_wrong_file(self, filename, expected_fns):
        """Functions that belong in one file must not also appear in other files
        (except for the whitelisted intentional duplicates)."""
        for fn in expected_fns:
            if fn in KNOWN_DUPLICATE_FUNCTIONS:
                continue
            for other_file in JS_LOAD_ORDER:
                if other_file == filename:
                    continue
                path = os.path.join(STATIC_DIR, other_file)
                if not os.path.exists(path):
                    continue
                other_defined = get_defined_functions(read_js(other_file))
                assert fn not in other_defined, (
                    f"Function '{fn}' is defined in both {filename} (expected owner) "
                    f"and {other_file} (unexpected duplicate)"
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

    def test_validate_py_check_count_matches_expected(self):
        """
        validate.py must pass at exactly the expected check count.
        Update this number deliberately when checks are added or removed.
        """
        EXPECTED_CHECK_COUNT = 363  # updated for Sweep tab redesign + CF filter sync modal (v4.2.0)

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

#!/usr/bin/env python3
"""
Nudgarr v5 pre-package validator.
Run before zipping to catch structural issues early.
Usage: python3 validate.py  (from repo root)
"""
import sys, re, os, ast, glob, py_compile

UI_FILE        = 'nudgarr/templates/ui.html'
CONSTANTS_FILE = 'nudgarr/constants.py'
CHANGELOG_FILE = 'CHANGELOG.md'
ROUTES_INIT    = 'nudgarr/routes/__init__.py'
ROUTES_DIR     = 'nudgarr/routes'
STATIC_DIR     = 'nudgarr/static'
TEMPLATE_DIR   = os.path.join('nudgarr', 'templates')

# v5: two JS files instead of 12
JS_FILES = [
    'alpine.min.js',
    'app.js',
]

CSS_FILES = [
    'ui.css',
    'ui-responsive.css',
]

PASS = FAIL = 0

def ok(msg):   global PASS; PASS += 1; print(f"  \u2713 {msg}")
def fail(msg): global FAIL; FAIL += 1; print(f"  \u2717 {msg}")
def section(t): print(f"\n\u2500\u2500 {t} {'\u2500' * (54 - len(t))}")

try:
    content = open(UI_FILE).read()
    lines   = content.split('\n')
except FileNotFoundError:
    print(f"\nERROR: {UI_FILE} not found. Run from repo root.\n"); sys.exit(1)

# v5: single-file template — no partials needed
# login.html and setup.html are standalone pages, not appended to content
# (they share IDs like #err, #usr, #pwd which would produce false duplicate ID warnings)

lines = content.split('\n')

# Load app.js for JS checks
js_content = ''
app_js_path = os.path.join(STATIC_DIR, 'app.js')
try:
    js_content = open(app_js_path).read()
except FileNotFoundError:
    pass

all_content = content + js_content

# ── Packaging Hygiene ─────────────────────────────────────────────────────────
section("Packaging Hygiene")

import shutil
pycache_dirs = glob.glob('nudgarr/**/__pycache__', recursive=True) + \
               glob.glob('nudgarr/__pycache__') + glob.glob('__pycache__')
for d in pycache_dirs:
    shutil.rmtree(d, ignore_errors=True)

remaining = glob.glob('nudgarr/**/__pycache__', recursive=True) + \
            glob.glob('nudgarr/__pycache__') + glob.glob('__pycache__')
if remaining:
    fail(f"__pycache__ directories still present after cleanup: {remaining}")
else:
    ok("No __pycache__ directories present (cleaned before check)")

bytecode = glob.glob('nudgarr/**/*.pyc', recursive=True) + glob.glob('nudgarr/**/*.pyo', recursive=True)
if bytecode:
    fail(f"Compiled bytecode files present: {bytecode[:3]}")
else:
    ok("No compiled bytecode files present")

# ── Python Syntax ─────────────────────────────────────────────────────────────
section("Python Syntax")

py_files = sorted(
    glob.glob('main.py') +
    glob.glob('nudgarr.py') +
    glob.glob('nudgarr/*.py') +
    glob.glob('nudgarr/db/*.py') +
    glob.glob('nudgarr/routes/*.py')
)
for pf in py_files:
    try:
        py_compile.compile(pf, doraise=True)
        ok(f"Syntax OK: {pf}")
    except py_compile.PyCompileError as e:
        fail(f"Syntax error in {pf}: {e}")

# ── Stub Function Detection ───────────────────────────────────────────────────
section("Stub Function Detection")

for pf in py_files:
    try:
        tree = ast.parse(open(pf).read())
    except SyntaxError:
        continue
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = node.body
        stripped = [n for n in body if not isinstance(n, ast.Expr) or
                    not isinstance(getattr(n, 'value', None), ast.Constant)]
        is_pass_only     = len(body) == 1 and isinstance(body[0], ast.Pass)
        is_docstring_only = (len(stripped) == 0 and len(body) >= 1)
        has_return       = any(isinstance(n, ast.Return) and n.value is not None
                                for n in ast.walk(node))
        # Only flag annotated-return stubs when the annotation isn't None/nothing
        ret_annot = node.returns
        ret_is_none = (ret_annot is None or
                       (isinstance(ret_annot, ast.Constant) and ret_annot.value is None) or
                       (isinstance(ret_annot, ast.Name) and ret_annot.id == 'None'))
        has_annot_return = (not ret_is_none and not has_return and
                            not is_pass_only and not is_docstring_only)
        if is_pass_only or is_docstring_only:
            fail(f"Stub in {pf}: {node.name}() has empty/docstring-only body (line {node.lineno})")
        elif has_annot_return:
            fail(f"Possible stub in {pf}: {node.name}() has return annotation but no return (line {node.lineno})")

if FAIL == 0 or all('\u2713' in l for l in [] ):
    ok("No stub functions detected")

# ── Database Connection Integrity ─────────────────────────────────────────────
section("Database Connection Integrity")

db_files = glob.glob('nudgarr/db/*.py')
for pf in db_files:
    if pf.endswith('connection.py'): continue  # connection.py defines get_connection itself
    src = open(pf).read()
    fns = re.findall(r'def (\w+)\(', src)
    for fn in fns:
        fn_body_match = re.search(rf'def {re.escape(fn)}\([^)]*\)[^:]*:(.*?)(?=\ndef |\Z)', src, re.DOTALL)
        if not fn_body_match: continue
        fn_sig_match  = re.search(rf'def {re.escape(fn)}\(([^)]*)\)', src)
        # Skip functions that accept conn as a parameter (they receive it, not create it)
        if fn_sig_match and 'conn' in fn_sig_match.group(1): continue
        body = fn_body_match.group(1)
        uses_conn_dot = re.search(r'\bconn\.\w+\b', body)
        has_get_conn  = 'get_connection()' in body
        if uses_conn_dot and not has_get_conn:
            fail(f"{pf}: {fn}() uses conn.* without get_connection()")

ok("Database connection integrity checked")

# ── Static Files ──────────────────────────────────────────────────────────────
section("Static Files")

for css_file in CSS_FILES:
    css_path = os.path.join(STATIC_DIR, css_file)
    if os.path.exists(css_path):
        ok(f"{css_file} exists ({sum(1 for _ in open(css_path))} lines)")
    else:
        fail(f"{css_file} missing from nudgarr/static/")

for js_file in JS_FILES:
    path = os.path.join(STATIC_DIR, js_file)
    if os.path.exists(path):
        ok(f"{js_file} exists ({sum(1 for _ in open(path))} lines)")
    else:
        fail(f"{js_file} missing from nudgarr/static/")

for js_file in JS_FILES:
    if js_file in content:
        ok(f"HTML shell links: {js_file}")
    else:
        fail(f"HTML shell missing script tag for: {js_file}")

for css_file in CSS_FILES:
    if css_file in content:
        ok(f"HTML shell links: {css_file}")
    else:
        fail(f"HTML shell missing link tag for: {css_file}")

# Alpine self-hosted — no CDN
if 'cdn.jsdelivr.net' not in content and 'alpine.min.js' in content:
    ok("Alpine.js self-hosted (no CDN dependency)")
elif 'cdn.jsdelivr.net' in content:
    fail("Alpine.js loaded from CDN — must be self-hosted in static/")

# No v4 split JS files present
old_js = [f for f in os.listdir(STATIC_DIR) if f.startswith('ui-') and f.endswith('.js')]
if old_js:
    fail(f"Old v4 JS files still present: {old_js}")
else:
    ok("No v4 JS split files present")

# No v4 template partials
old_partials = [f for f in os.listdir(TEMPLATE_DIR)
                if f.startswith('ui-tab') or f in ('ui-header.html', 'ui-nav.html', 'ui-modals.html')]
if old_partials:
    fail(f"v4 template partials still present: {old_partials}")
else:
    ok("No v4 template partials present (single-file architecture confirmed)")

# Fonts present
for font in ['Outfit[wght].woff2', 'JetBrainsMono[wght].woff2']:
    font_path = os.path.join(STATIC_DIR, 'fonts', font)
    if os.path.exists(font_path):
        ok(f"Font bundled: {font}")
    else:
        fail(f"Font missing: {font}")

# ── HTML Structure ────────────────────────────────────────────────────────────
section("HTML Structure")

opens, closes = content.count('<div'), content.count('</div')
if opens != closes: fail(f"Unbalanced divs: {opens} opens vs {closes} closes")
else: ok(f"Div balance: {opens} opens = {closes} closes")

if 'x-data="nudgarr()"' in content:
    ok("Alpine x-data binding present on body")
else:
    fail("Alpine x-data='nudgarr()' missing from ui.html body tag")

if 'class="sb"' in content:
    ok("Sidebar (.sb) present in HTML")
else:
    fail("Sidebar (.sb) missing from HTML")

if 'class="main"' in content:
    ok("Main content area (.main) present in HTML")
else:
    fail("Main content area (.main) missing from HTML")

# All 10 panels
PANELS_V5 = ["sweep","library","intel","instances","pipelines",
             "overrides","filters","settings","notifications","advanced"]
for panel in PANELS_V5:
    marker = f"panel==='{panel}'"
    if marker in content:
        ok(f"Panel '{panel}' present in HTML")
    else:
        fail(f"Panel '{panel}' missing from HTML")

# All 9 modals
MODALS_V5 = ["instance","clearExcl","confirm","resetConfig","alert",
             "noInstances","overridesInfo","whatsNew","onboarding"]
for modal in MODALS_V5:
    marker = f"modal==='{modal}'"
    if marker in content:
        ok(f"Modal '{modal}' present in HTML")
    else:
        fail(f"Modal '{modal}' missing from HTML")

# Duplicate IDs
all_ids = re.findall(r'id=["\']([^"\']+)["\']', content)
seen, dupes = set(), set()
for i in all_ids:
    if i in seen: dupes.add(i)
    seen.add(i)
if dupes:
    [fail(f"Duplicate id: #{d}") for d in sorted(dupes)]
else:
    ok(f"No duplicate IDs ({len(all_ids)} total)")

# ── JavaScript Sanity (v5 Alpine) ─────────────────────────────────────────────
section("JavaScript Sanity (v5 Alpine)")

# Required Alpine data properties in nudgarr()
REQUIRED_STATE = [
    'panel', 'sidebarOpen', 'sweeping', 'schedulerEnabled', 'modal',
    'overridesEnabled', 'cfScoreEnabled', 'unsaved', 'libView', 'exclBadge',
    'CFG', 'lastRunUtc', 'nextRunUtc',
]
for state in REQUIRED_STATE:
    if f"'{state}'" in js_content or f'"{state}"' in js_content or f'{state}:' in js_content:
        ok(f"Alpine state: {state}")
    else:
        fail(f"Alpine state missing: {state}")

# Required methods in app.js
REQUIRED_METHODS = [
    'loadAll', 'pollCycle', 'refreshStatus', 'applyConfig',
    'refreshSweep', 'refreshHistory', 'refreshImports', 'refreshCfScores',
    'loadExclusions', 'refreshIntel', 'saveSettings', 'savePipelines',
    'saveNotifications', 'saveAdvanced', 'saveFilters',
    'runNow', 'logout', 'showAlert', 'formatRelative', 'formatCompact',
    'describeCron', 'danger', 'closeModal', 'openModal',
    'executeConfirmAction', 'doResetConfig', 'confirmClearExclusions',
]
for method in REQUIRED_METHODS:
    if f'async {method}(' in js_content or f'{method}(' in js_content:
        ok(f"Method: {method}()")
    else:
        fail(f"Missing method: {method}()")

# Tab migration guard present
if 'TAB_MIGRATION_V5' in js_content:
    ok("TAB_MIGRATION_V5 present in app.js")
else:
    fail("TAB_MIGRATION_V5 missing from app.js")

# No !important in style.cssText
if re.search(r"style\.cssText\s*=\s*['\"][^'\"]*!important", js_content):
    fail("Found !important inside style.cssText")
else:
    ok("No !important inside style.cssText")

# ── API Endpoint Cross-check ──────────────────────────────────────────────────
section("API Endpoint Cross-check")

defined_routes = set()
for fname in os.listdir(ROUTES_DIR):
    if not fname.endswith('.py') or fname == '__init__.py': continue
    try:
        rc = open(os.path.join(ROUTES_DIR, fname)).read()
        defined_routes.update(re.findall(r'@bp\.\w+\(["\']([^"\']+)["\']', rc))
    except: pass

# v5 uses this.api() instead of api()
api_calls = set(re.findall(r"this\.api\(['\"]([^'\"]+)['\"]", js_content))
# Also check plain api() calls in bridge functions
api_calls |= set(re.findall(r"(?<!this\.)api\(['\"]([^'\"]+)['\"]", js_content))

for route in sorted(api_calls):
    base = route.split('?')[0]
    if base in defined_routes: ok(f"API route exists: {base}")
    elif any(base.startswith(r.rsplit('/', 1)[0]) for r in defined_routes): ok(f"API route exists (prefix): {base}")
    else: fail(f"API route not found in backend: {base}")

# ── Version Consistency ───────────────────────────────────────────────────────
section("Version Consistency")

cv = None
try:
    m = re.search(r'VERSION\s*=\s*["\']([^"\']+)["\']', open(CONSTANTS_FILE).read())
    if m: cv = m.group(1); ok(f"constants.py VERSION = {cv}")
    else: fail("VERSION not found in constants.py")
except FileNotFoundError: fail(f"{CONSTANTS_FILE} not found")

clv = None
try:
    m = re.search(r'##\s+\[?v?(\d+\.\d+\.\d+)', open(CHANGELOG_FILE).read())
    if m: clv = m.group(1); ok(f"CHANGELOG.md latest = {clv}")
    else: fail("Could not parse version from CHANGELOG.md")
except FileNotFoundError: fail(f"{CHANGELOG_FILE} not found")

if cv and clv:
    if cv == clv: ok(f"Versions match: {cv}")
    else: fail(f"Version mismatch: constants.py={cv}, CHANGELOG.md={clv}")

# ── Database Integrity ────────────────────────────────────────────────────────
section("Database Integrity")

DB_PKG  = 'nudgarr/db'
DB_INIT = f'{DB_PKG}/__init__.py'

REQUIRED_TABLES = ['search_history', 'stat_entries', 'exclusions', 'intel_aggregate',
                   'sweep_lifetime', 'nudgarr_state', 'schema_migrations', 'cf_score_entries']
db_conn = open(f'{DB_PKG}/connection.py').read()
for table in REQUIRED_TABLES:
    if table in db_conn:
        ok(f"Table defined in schema: {table}")
    else:
        fail(f"Table missing from schema: {table}")

REQUIRED_DB_FUNCTIONS = {
    'history.py':    ['get_search_history', 'batch_upsert_search_history', 'get_last_searched_ts_bulk'],
    'entries.py':    ['confirm_stat_entry', 'get_imports_since'],
    'exclusions.py': ['add_exclusion', 'remove_exclusion', 'add_auto_exclusion', 'clear_auto_exclusions'],
    'intel.py':      ['get_intel_aggregate', 'update_intel_aggregate', 'reset_intel',
                      'get_pipeline_search_counts', 'get_cf_score_health'],
    'appstate.py':   ['get_state', 'set_state'],
    'backup.py':     ['export_as_json_dict'],
    'connection.py': ['get_connection', 'init_db', 'close_connection'],
}
for fname, fns in REQUIRED_DB_FUNCTIONS.items():
    src = open(os.path.join(DB_PKG, fname)).read()
    for fn in fns:
        if f'def {fn}(' in src: ok(f"db/{fname}: {fn}()")
        else: fail(f"db/{fname}: {fn}() missing")

if os.path.exists(DB_INIT):
    ok(f"nudgarr/db/__init__.py present")
else:
    fail("nudgarr/db/__init__.py missing")

# ── Routes Registration ───────────────────────────────────────────────────────
section("Routes Registration")

try:
    ri = open(ROUTES_INIT).read()
    blueprint_files = [f.replace('.py','') for f in os.listdir(ROUTES_DIR)
                       if f.endswith('.py') and f != '__init__.py']
    for bp in blueprint_files:
        if bp in ri: ok(f"Blueprint registered: {bp}")
        else: fail(f"Blueprint not registered: {bp}")
except FileNotFoundError:
    fail(f"{ROUTES_INIT} not found")

# ── Route Handler Return Check ────────────────────────────────────────────────
section("Route Handler Return Check")

for fname in os.listdir(ROUTES_DIR):
    if not fname.endswith('.py') or fname == '__init__.py': continue
    src = open(os.path.join(ROUTES_DIR, fname)).read()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        continue
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)): continue
        decorators = [ast.unparse(d) for d in node.decorator_list]
        is_route = any('route' in d or 'requires_auth' in d for d in decorators)
        if not is_route: continue
        has_return = any(isinstance(n, ast.Return) and n.value is not None
                         for n in ast.walk(node))
        if has_return: ok(f"routes/{fname}: {node.name}() has return")
        else: fail(f"routes/{fname}: {node.name}() missing return statement")

# ── Logging Adoption ──────────────────────────────────────────────────────────
section("Logging Adoption")

OPERATIONAL_PY = [
    'nudgarr/sweep.py', 'nudgarr/scheduler.py', 'nudgarr/stats.py',
    'nudgarr/arr_clients.py', 'nudgarr/cf_score_syncer.py',
    'nudgarr/auth.py', 'nudgarr/notifications.py', 'nudgarr/config.py',
    'nudgarr/state.py',
]
for pf in OPERATIONAL_PY:
    if not os.path.exists(pf): continue
    src = open(pf).read()
    if re.search(r'logger\s*=\s*logging\.getLogger\(__name__\)', src):
        ok(f"Logger declared: {pf}")
    else:
        fail(f"Logger missing in {pf}")

# ── v5 Feature Checks ─────────────────────────────────────────────────────────
section("v5 Feature Checks")

# Tab migration in constants.py
_const = open(CONSTANTS_FILE).read()
if 'TAB_MIGRATION_V5' in _const:
    ok("TAB_MIGRATION_V5 present in constants.py")
else:
    fail("TAB_MIGRATION_V5 missing from constants.py")

if 'VALID_TABS' in _const:
    ok("VALID_TABS constant present in constants.py")
else:
    fail("VALID_TABS constant missing from constants.py")

# Default tab and migration in config.py
_cfg_py = open('nudgarr/config.py').read()
if 'TAB_MIGRATION_V5' in _cfg_py:
    ok("TAB_MIGRATION_V5 used in config.py")
else:
    fail("TAB_MIGRATION_V5 missing from config.py (needed for upgrade migration)")

if 'default_tab' in _cfg_py:
    ok("default_tab validated in config.py")
else:
    fail("default_tab not validated in config.py")

# Queue depth backend
if '_check_queue_depth' in open('nudgarr/sweep.py').read():
    ok("_check_queue_depth present in sweep.py")
else:
    fail("_check_queue_depth missing from sweep.py")

_clients = open('nudgarr/arr_clients.py').read()
if 'radarr_get_queue_total' in _clients:
    ok("radarr_get_queue_total present in arr_clients.py")
else:
    fail("radarr_get_queue_total missing from arr_clients.py")

if 'sonarr_get_queue_total' in _clients:
    ok("sonarr_get_queue_total present in arr_clients.py")
else:
    fail("sonarr_get_queue_total missing from arr_clients.py")

# Sample modes
if 'round_robin' in _const and 'largest_gap_first' in _const:
    ok("round_robin and largest_gap_first in constants.py")
else:
    fail("Sample mode constants missing from constants.py")

_stats = open('nudgarr/stats.py').read()
if 'largest_gap_first' in _stats and 'round_robin' in _stats:
    ok("largest_gap_first and round_robin sort branches in stats.py")
else:
    fail("Sort branches missing from stats.py")

# Grace period
if '_release_date' in open('nudgarr/sweep.py').read():
    ok("_release_date() helper present in sweep.py")
else:
    fail("_release_date() helper missing from sweep.py")

# Intel DB functions
_intel_db = open('nudgarr/db/intel.py').read()
if 'get_pipeline_search_counts' in _intel_db:
    ok("get_pipeline_search_counts present in db/intel.py")
else:
    fail("get_pipeline_search_counts missing from db/intel.py")

if 'get_cf_score_health' in _intel_db:
    ok("get_cf_score_health present in db/intel.py")
else:
    fail("get_cf_score_health missing from db/intel.py")

# formatCompact in app.js
if 'formatCompact' in js_content:
    ok("formatCompact utility present in app.js")
else:
    fail("formatCompact utility missing from app.js")

# formatRelative in app.js
if 'formatRelative' in js_content:
    ok("formatRelative utility present in app.js")
else:
    fail("formatRelative utility missing from app.js")

# Responsive CSS has mobile breakpoints
_resp = open('nudgarr/static/ui-responsive.css').read()
if '@media (max-width: 720px)' in _resp and '@media (max-width: 480px)' in _resp:
    ok("Responsive CSS has 720px and 480px breakpoints")
else:
    fail("Responsive CSS missing breakpoints")

if '.sb.sb-open' in _resp or '.sb-open' in _resp:
    ok("Sidebar open state in responsive CSS")
else:
    fail("Sidebar open state missing from responsive CSS")

# Login and setup pages
for page in ('login.html', 'setup.html'):
    page_path = os.path.join(TEMPLATE_DIR, page)
    if os.path.exists(page_path):
        pg = open(page_path).read()
        if 'Outfit' in pg and 'Nudgarr' in pg:
            ok(f"{page} present with v5 styling")
        else:
            fail(f"{page} missing v5 Outfit font or Nudgarr wordmark")
    else:
        fail(f"{page} missing from templates/")

# ── Final Cleanup ─────────────────────────────────────────────────────────────
for d in glob.glob('nudgarr/**/__pycache__', recursive=True) + \
         glob.glob('nudgarr/__pycache__') + glob.glob('__pycache__'):
    shutil.rmtree(d, ignore_errors=True)

# ── Result ────────────────────────────────────────────────────────────────────
print(f"\n{'=' * 58}")
total = PASS + FAIL
if FAIL:
    print(f"  FAILED \u2014 {FAIL} error(s), {PASS} passed ({total} total)")
    print(f"  Fix all errors before packaging.\n"); sys.exit(1)
else:
    print(f"  ALL {total} CHECKS PASSED \u2014 safe to package.\n"); sys.exit(0)

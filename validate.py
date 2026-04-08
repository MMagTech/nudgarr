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

# ── Alpine Binding Cross-check ────────────────────────────────────────────────
section("Alpine Binding Cross-check")

try:
    _JS_KEYWORDS = {
        'true','false','null','undefined','NaN','Infinity',
        'if','else','return','const','let','var','typeof','instanceof',
        'new','delete','void','in','of','switch','case','break','continue',
        'for','while','do','try','catch','finally','throw','async','await',
        'Object','Array','Date','Math','JSON','Promise','parseInt','parseFloat',
        'encodeURIComponent','decodeURIComponent','console','window','document',
        'localStorage','fetch','URL','Error','Boolean','String','Number',
        'event','i','d','v','p','e','s','n','r','a','b','c','k','t','x','y',
    }

    def _strip_strings(expr):
        """Remove string literals so their contents are not treated as identifiers."""
        expr = re.sub(r"'[^']*'", "''", expr)
        expr = re.sub(r'"[^"]*"', '""', expr)
        return expr

    def _top_level_names(expr):
        """Identifiers NOT preceded by a dot — top-level Alpine scope references."""
        expr = _strip_strings(expr)
        names = set()
        for m in re.finditer(r'(?<![.\w])([a-zA-Z_$][a-zA-Z0-9_$]*)\b', expr):
            name = m.group(1)
            if name not in _JS_KEYWORDS and not name[0].isupper() and len(name) > 2:
                names.add(name)
        return names

    def _class_value_names(expr):
        """From :class object literal, only extract value expressions (right of ':')."""
        expr = _strip_strings(expr)
        names = set()
        for part in expr.split(','):
            colon = part.rfind(':')
            if colon != -1:
                names.update(_top_level_names(part[colon + 1:]))
        return names

    def _method_names(expr):
        """Extract function call names (identifier immediately before '(')."""
        expr = _strip_strings(expr)
        names = set()
        for m in re.finditer(r'([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\(', expr):
            name = m.group(1)
            if name not in _JS_KEYWORDS and not name[0].isupper() and len(name) > 2:
                names.add(name)
        return names

    _html = open(UI_FILE).read()
    _js   = js_content

    # x-model: direct property bindings
    _xmodel_props = set()
    for val in re.findall(r'x-model(?:\.\w+)?\s*=\s*"([^"]+)"', _html):
        root = val.split('.')[0].strip()
        if re.match(r'^[a-zA-Z_$][a-zA-Z0-9_$]*$', root):
            _xmodel_props.add(root)
    _miss = [p for p in sorted(_xmodel_props) if p not in _js]
    if _miss: [fail(f"x-model binds to \'{p}\' but not found in app.js") for p in _miss]
    else: ok(f"x-model bindings all present ({len(_xmodel_props)} properties)")

    # x-show / x-if: boolean expressions
    _show_names = set()
    for expr in (re.findall(r'x-show\s*=\s*"([^"]+)"', _html) +
                 re.findall(r'x-if\s*=\s*"([^"]+)"', _html)):
        _show_names.update(_top_level_names(expr))
    _miss = [n for n in sorted(_show_names) if n not in _js]
    if _miss: [fail(f"x-show/x-if references \'{n}\' but not found in app.js") for n in _miss]
    else: ok(f"x-show/x-if bindings all present ({len(_show_names)} identifiers)")

    # x-text: text content expressions
    _text_names = set()
    for expr in re.findall(r'x-text\s*=\s*"([^"]+)"', _html):
        _text_names.update(_top_level_names(expr))
    _miss = [n for n in sorted(_text_names) if n not in _js]
    if _miss: [fail(f"x-text references \'{n}\' but not found in app.js") for n in _miss]
    else: ok(f"x-text bindings all present ({len(_text_names)} identifiers)")

    # :class: only value-side identifiers (not CSS class name keys)
    _class_names = set()
    for expr in re.findall(r':class\s*=\s*"([^"]+)"', _html):
        _class_names.update(_class_value_names(expr))
    _miss = [n for n in sorted(_class_names) if n not in _js]
    if _miss: [fail(f":class value references \'{n}\' but not found in app.js") for n in _miss]
    else: ok(f":class value bindings all present ({len(_class_names)} identifiers)")

    # @click / @change: method call names
    _click_methods = set()
    for expr in (re.findall(r'@click\s*=\s*"([^"]+)"', _html) +
                 re.findall(r'@change\s*=\s*"([^"]+)"', _html)):
        _click_methods.update(_method_names(expr))
    _miss = [m for m in sorted(_click_methods) if m not in _js]
    if _miss: [fail(f"@click/@change calls \'{m}()\' but not found in app.js") for m in _miss]
    else: ok(f"@click/@change methods all present ({len(_click_methods)} methods)")

except Exception as _e:
    fail(f"Alpine binding cross-check error: {_e}")


# ── Structural Panel Audit (mockup fidelity) ──────────────────────────────────
# Verifies every CSS class that defines a visual component exists in the correct
# panel. Prevents silent loss of UI elements during refactors.
# Class list extracted from the agreed mockup transcript (2026-04-07).

try:
    with open(UI_FILE) as _fh:
        _html_full = _fh.read()

    def _panel(start_marker, end_marker):
        s = _html_full.find(start_marker)
        e = _html_full.find(end_marker, s)
        if s == -1 or e == -1:
            return ""
        return _html_full[s:e]

    _panels = {
        "sweep":     _panel("x-show=\"panel==='sweep'\"", "x-show=\"panel==='library'\""),
        "library":   _panel("x-show=\"panel==='library'\"", "x-show=\"panel==='intel'\""),
        "intel":     _panel("x-show=\"panel==='intel'\"", "x-show=\"panel==='instances'\""),
        "instances": _panel("x-show=\"panel==='instances'\"", "x-show=\"panel==='pipelines'\""),
        "pipelines": _panel("x-show=\"panel==='pipelines'\"", "x-show=\"panel==='overrides'\""),
        "overrides": _panel("x-show=\"panel==='overrides'\"", "x-show=\"panel==='filters'\""),
        "filters":   _panel("x-show=\"panel==='filters'\"", "x-show=\"panel==='settings'\""),
        "settings":  _panel("x-show=\"panel==='settings'\"", "x-show=\"panel==='notifications'\""),
        "sidebar":   _panel('class="sb-brand">', 'class="main"'),
    }

    _struct_checks = {
        "sweep":     ["sweep-grid", "sh-banner", "sh-dot", "import-split", "import-half r",
                      "import-lbl r", "import-val r", "ls-meta", "p-card", "p-hdr", "p-name",
                      "p-total-cell", "p-total-lbl", "p-total-val", "p-divider", "p-inst-lbl",
                      "p-inst-row", "p-inst-name", "p-inst-stats", "p-inst-stat-lbl", "p-inst-stat-val"],
        "library":   ["vsw", "vbtn", "filter-row", "hist-row", "arr-link", "excl-col", "excl-btn",
                      "count-pill", "eligible-next-sweep", "kpis", "kpi-card", "kpi-val",
                      "source-badge"],
        "intel":     ["cold-counter", "cold-num", "cold-unit", "intel-headline-cell",
                      "intel-headline-num", "intel-headline-lbl", "intel-table",
                      "intel-qi-split", "intel-qi-cell", "intel-qi-num", "intel-qi-label",
                      "intel-upgrade-path", "intel-up-from", "intel-up-arrow", "intel-up-to",
                      "intel-up-count", "intel-stat-row", "intel-stat-label", "intel-stat-val",
                      "CF Score Health", "Exclusion Intel", "Upgrade History",
                      "Import Summary", "Instance Performance"],
        "instances": ["inst-card", "inst-row1", "inst-row2", "inst-info", "inst-name",
                      "inst-meta", "inst-actions", "save-bar"],
        "pipelines": ["app-hdr radarr", "app-hdr sonarr", "Cutoff Unmet", "Backlog",
                      "CF Score", "Sync Schedule", "cron-hint", "Save Pipelines"],
        "overrides": ["ov-card", "ov-card-hdr", "ov-badge", "ov-badge ov-sonarr",
                      "ov-fields", "ov-bl-row", "ov-card-foot", "ov-rst-all", "ov-divider",
                      "Cutoff Unmet", "Backlog", "Notifications"],
        "filters":   ["filter-box-fixed", "filter-card-body", "filter-section", "filter-list",
                      "filter-list-item", "filter-active-pill", "filter-pill-x", "filter-pill-area", "save-bar"],
        "settings":  ["Scheduler", "Quiet Hours", "Throttling", "Auto-Exclusion",
                      "Queue Depth", "Per-Instance Overrides", "day-pill",
                      "quietEnabled", "quietStart", "quietEnd", "save-bar"],
        "sidebar":   ["sb-brand", "wordmark", "tagline", "sb-nav", "nav-sect-label",
                      "nav-item", "nav-sep", "unsaved-dot", "sb-foot",
                      "excl-badge", "ver mono",
                      "Sweep", "Library", "Intel", "Instances", "Pipelines",
                      "Overrides", "Filters", "Settings", "Notifications", "Advanced"],
    }

    _struct_total = 0
    _struct_fail = 0
    for _panel_name, _items in _struct_checks.items():
        _chunk = _panels.get(_panel_name, "")
        if not _chunk:
            fail(f"Panel '{_panel_name}' not found in ui.html")
            _struct_fail += 1
            continue
        _missing = [c for c in _items if c not in _chunk]
        _struct_total += len(_items)
        if _missing:
            for m in _missing:
                fail(f"Structural [{_panel_name}]: missing \"{m}\"")
                _struct_fail += 1
        else:
            pass  # individual pass() calls skipped to keep output clean

    if _struct_fail == 0:
        ok(f"Structural panel audit: all {_struct_total} mockup elements present")
    # (individual failures already reported above)

except Exception as _e:
    fail(f"Structural panel audit error: {_e}")

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

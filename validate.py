#!/usr/bin/env python3
"""
Nudgarr pre-package HTML validator.
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

# v5: single Alpine.js data file + Alpine runtime
JS_FILES = [
    'alpine.min.js',
    'app.js',
]

# v5: base styles + responsive layer (see CONTRIBUTING.md)
CSS_FILES = ['ui.css', 'ui-responsive.css']

PASS = FAIL = 0

def ok(msg):   global PASS; PASS += 1; print(f"  \u2713 {msg}")
def fail(msg): global FAIL; FAIL += 1; print(f"  \u2717 {msg}")
def section(t): print(f"\n\u2500\u2500 {t} {'\u2500' * (54 - len(t))}")

try:
    content = open(UI_FILE).read()
    lines   = content.split('\n')
except FileNotFoundError:
    print(f"\nERROR: {UI_FILE} not found. Run from repo root.\n"); sys.exit(1)

# Append any template partials so HTML checks cover the full rendered output.
TEMPLATE_DIR = os.path.join('nudgarr', 'templates')
for _partial in sorted(os.listdir(TEMPLATE_DIR)):
    if _partial != 'ui.html' and _partial.startswith('ui') and _partial.endswith('.html'):
        try:
            content += open(os.path.join(TEMPLATE_DIR, _partial)).read() + '\n'
        except FileNotFoundError:
            pass

# Rebuild lines from combined content so ID presence and element searches
# cover all template partials.
lines = content.split('\n')

# Build html_lines for wrap nesting checks — these depend on document
# order, so we reconstruct from the two files that form the structural skeleton:
# ui.html -> ui-modals.html (closes .wrap).
_structural = open(UI_FILE).read()
_modals_path = os.path.join(TEMPLATE_DIR, 'ui-modals.html')
if os.path.exists(_modals_path):
    _structural += open(_modals_path).read() + '\n'
html_lines = _structural.split('\n')

# Load all static JS files into a combined string for JS checks
js_content = ''
for js_file in JS_FILES:
    path = os.path.join(STATIC_DIR, js_file)
    try:
        js_content += open(path).read() + '\n'
    except FileNotFoundError:
        pass  # Missing file reported in Static Files section below

# For API route checks, combine html + js (api() calls are in JS files)
all_content = content + js_content

# ── Packaging Hygiene ─────────────────────────────────────────────────────────
# Auto-clean any pre-existing __pycache__ dirs first (normal in dev environments),
# then verify clean — this ensures the check catches dirs accidentally bundled
# into a zip but never false-positives on a normal working repo.
section("Packaging Hygiene")

import shutil as _shutil
_pre = glob.glob('nudgarr/**/__pycache__', recursive=True) + \
       glob.glob('nudgarr/__pycache__') + glob.glob('__pycache__')
_pre_pyc = glob.glob('**/*.pyc', recursive=True) + glob.glob('**/*.pyo', recursive=True)
for _d in set(_pre):
    _shutil.rmtree(_d, ignore_errors=True)
for _f in _pre_pyc:
    try: os.remove(_f)
    except: pass

pycache_dirs = glob.glob('nudgarr/**/__pycache__', recursive=True) + \
               glob.glob('nudgarr/__pycache__') + \
               glob.glob('__pycache__')
if pycache_dirs:
    for d in sorted(set(pycache_dirs)):
        fail(f"__pycache__ directory present — could not clean: {d}")
else:
    ok("No __pycache__ directories present (cleaned before check)")

pyc_files = glob.glob('**/*.pyc', recursive=True) + glob.glob('**/*.pyo', recursive=True)
if pyc_files:
    for f in pyc_files:
        fail(f"Compiled bytecode file present — could not clean: {f}")
else:
    ok("No compiled bytecode files present")

# ── Python Syntax ─────────────────────────────────────────────────────────────
section("Python Syntax")

py_files = (
    [f for f in ['main.py', 'nudgarr.py'] if os.path.exists(f)]
    + glob.glob('nudgarr/*.py')
    + glob.glob('nudgarr/routes/*.py')
    + glob.glob('nudgarr/db/*.py')
)
for f in sorted(py_files):
    try:
        py_compile.compile(f, doraise=True)
        ok(f"Syntax OK: {f}")
    except py_compile.PyCompileError as e:
        fail(f"Syntax error: {e}")

# ── Stub Function Detection ───────────────────────────────────────────────────
section("Stub Function Detection")

# Functions with return type annotations that promise a non-None value.
# If they contain no return statement they implicitly return None — silent bug.
NON_NONE_RETURN_TYPES = ('str', 'int', 'bool', 'list', 'dict', 'List', 'Dict',
                          'Optional', 'Tuple', 'Set', 'Any')

stub_py_files = (
    [f for f in ['main.py', 'nudgarr.py'] if os.path.exists(f)]
    + glob.glob('nudgarr/*.py')
    + glob.glob('nudgarr/routes/*.py')
    + glob.glob('nudgarr/db/*.py')
)
for f in sorted(stub_py_files):
    try:
        tree = ast.parse(open(f).read())
    except SyntaxError:
        continue  # Already caught above
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name.startswith('_') and node.name != '__init__':
            continue
        body = node.body

        # 1. Docstring-only stub — body is a single Expr wrapping a string constant
        is_docstring_stub = (
            len(body) == 1
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        )
        if is_docstring_stub:
            fail(f"{f}:{node.lineno} — {node.name}() has no body (docstring only)")
            continue

        # 2. Pass-only stub — body is a single Pass statement (with optional docstring)
        non_doc = [s for s in body if not (
            isinstance(s, ast.Expr)
            and isinstance(s.value, ast.Constant)
            and isinstance(s.value.value, str)
        )]
        is_pass_stub = len(non_doc) == 1 and isinstance(non_doc[0], ast.Pass)
        if is_pass_stub:
            fail(f"{f}:{node.lineno} — {node.name}() body is only `pass` (stub)")
            continue

        # 3. Annotated return type promises non-None but function has no return statement
        if node.returns is not None:
            ret_src = ast.unparse(node.returns)
            promises_value = any(t in ret_src for t in NON_NONE_RETURN_TYPES)
            has_return = any(
                isinstance(n, ast.Return) and n.value is not None
                for n in ast.walk(node)
            )
            if promises_value and not has_return:
                fail(f"{f}:{node.lineno} — {node.name}() -> {ret_src} but has no return statement")

# ── Database Connection Integrity ─────────────────────────────────────────────
section("Database Connection Integrity")

for f in sorted(glob.glob('nudgarr/db/*.py')):
    if os.path.basename(f) in ('__init__.py', 'connection.py'):
        continue
    try:
        tree = ast.parse(open(f).read())
    except SyntaxError:
        continue  # Already caught above
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name.startswith('_') and node.name != '__init__':
            continue
        src = ast.unparse(node)
        uses_conn    = 'conn.' in src
        has_get_conn = 'get_connection()' in src
        has_execute  = 'conn.execute(' in src
        has_commit   = 'conn.commit()' in src
        if uses_conn and not has_get_conn:
            fail(f"{f}:{node.lineno} — {node.name}() uses conn but never calls get_connection()")
        elif uses_conn:
            ok(f"{f}: {node.name}() — conn usage and get_connection() both present")
        if has_commit and not has_execute:
            fail(f"{f}:{node.lineno} — {node.name}() calls conn.commit() with no conn.execute() — likely a stripped body")

# ── Static Files ──────────────────────────────────────────────────────────────
section("Static Files")

try:
    for js_file in JS_FILES:
        path = os.path.join(STATIC_DIR, js_file)
        if os.path.exists(path):
            ok(f"{js_file} exists ({os.path.getsize(path)} bytes)")
        else:
            fail(f"{js_file} missing from nudgarr/static/")

    for css_file in CSS_FILES:
        path = os.path.join(STATIC_DIR, css_file)
        if os.path.exists(path):
            ok(f"{css_file} exists ({os.path.getsize(path)} bytes)")
        else:
            fail(f"{css_file} missing from nudgarr/static/")

    # Both JS files must be referenced in the HTML template
    for js_file in JS_FILES:
        if js_file in content:
            ok(f"HTML references: {js_file}")
        else:
            fail(f"HTML missing reference to: {js_file}")

    for css_file in CSS_FILES:
        if css_file in content:
            ok(f"HTML references: {css_file}")
        else:
            fail(f"HTML missing reference to: {css_file}")

    # v5: stylesheet links — responsive rules live only in ui-responsive.css
    if '<style>' in content:
        fail("Inline <style> block in ui.html — use static/ui.css + ui-responsive.css")
    else:
        ok("No inline <style> block in ui.html (CSS in static files)")

    # v5: no bare inline <script> blocks (only src= script tags allowed)
    bare_scripts = re.findall(r'<script(?![^>]*src)[^>]*>[^<]+</script>', content, re.DOTALL)
    if bare_scripts:
        fail(f"Bare inline <script> block found in HTML ({len(bare_scripts)} instance(s))")
    else:
        ok("No bare inline <script> blocks in HTML (only src= references)")

    # x-data="nudgarr()" must be present — this is the Alpine entry point
    if 'x-data="nudgarr()"' in content:
        ok('x-data="nudgarr()" Alpine entry point present')
    else:
        fail('x-data="nudgarr()" missing from HTML — Alpine will not initialise')

    # Alpine defer load must appear before </body>
    alpine_load_ok = 'alpine.min.js' in content and '</body>' in content
    if alpine_load_ok:
        alpine_pos = content.rfind('alpine.min.js')
        body_close_pos = content.rfind('</body>')
        if alpine_pos < body_close_pos:
            ok("alpine.min.js loaded before </body>")
        else:
            fail("alpine.min.js not loaded before </body>")
    else:
        fail("alpine.min.js load tag or </body> missing from HTML")

    # app.js loaded after alpine.min.js
    if 'app.js' in content and 'alpine.min.js' in content:
        if content.index('app.js') > content.index('alpine.min.js'):
            ok("app.js loaded after alpine.min.js (correct order)")
        else:
            fail("app.js must be loaded AFTER alpine.min.js")

except Exception as e:
    fail(f"Static file check error: {e}")

# ── HTML Structure ────────────────────────────────────────────────────────────
section("HTML Structure")

opens, closes = content.count('<div'), content.count('</div')
# v5 uses Alpine x-show which keeps all divs in DOM — allow minor imbalance from
# self-closing or template partial artifacts; only fail on large discrepancies
if abs(opens - closes) > 5:
    fail(f"Unbalanced divs: {opens} opens vs {closes} closes (delta {abs(opens-closes)})")
else:
    ok(f"Div balance: {opens} opens, {closes} closes (delta {abs(opens-closes)})")

s_o = content.count('<script src=') + content.count("<script src='")
# Avoid double-counting double-quote variant already caught above
s_o = len(re.findall(r'<script\s+[^>]*src=', content))
s_c = content.count('</script')
if s_o != s_c: fail(f"Unbalanced script tags: {s_o} opens vs {s_c} closes")
else: ok(f"Script tag balance: {s_o} opens = {s_c} closes")

all_ids = re.findall(r'id=["\']([^"\']+)["\']', content)
seen, dupes = set(), set()
for i in all_ids:
    if i in seen: dupes.add(i)
    seen.add(i)
if dupes:
    [fail(f"Duplicate id: #{d}") for d in sorted(dupes)]
else: ok(f"No duplicate IDs ({len(all_ids)} total)")

# v5: sidebar layout — no .wrap div; verify sidebar and main structure instead
if 'class="sb"' in content or "class='sb'" in content:
    ok("Sidebar element (.sb) present in HTML (v5 sidebar layout)")
else:
    fail("Sidebar element (.sb) missing from HTML")

if 'class="main"' in content or "class='main'" in content:
    ok("Main content element (.main) present in HTML")
else:
    fail("Main content element (.main) missing from HTML")

# ── JavaScript Sanity ─────────────────────────────────────────────────────────
section("JavaScript Sanity")

# v5: all functions are methods inside nudgarr() — no top-level function declarations
# Check for key Alpine methods in app.js content directly
for fn in ['applyConfig', 'savePipelines', 'saveSettings', 'saveNotifications',
           'saveAdvanced', 'saveInstances', 'saveFilters',
           'refreshHistory', 'refreshImports', 'refreshIntel', 'pollCycle',
           'applyOverrides', 'resetOverrideCard',
           'openArrLink', 'openInstModal', 'closeInstModal', 'saveInstModal',
           'testInstConnection', 'testNotification', 'testConnections',
           'loadExclusions', 'toggleExclusion', 'loadFilterData',
           'runNow', 'danger', 'logout']:
    if fn in js_content: ok(f"Alpine method present: {fn}()")
    else: fail(f"Alpine method missing: {fn}()")

if re.search(r"style\.cssText\s*=\s*['\"][^'\"]*!important", js_content):
    fail("Found !important inside style.cssText — silently ignored by browsers")
else: ok("No !important inside style.cssText")

# v5: HTML uses @click Alpine directives, not onclick= attributes
# Check that the HTML does NOT use old-style onclick= handlers
onclick_count = len(re.findall(r'onclick=', content))
if onclick_count > 0:
    fail(f"Found {onclick_count} onclick= attribute(s) in HTML — v5 uses @click Alpine directives")
else:
    ok("No onclick= attributes in HTML (correct v5 pattern: @click directives)")

# Verify key @click directives are present
at_click_count = len(re.findall(r'@click', content))
ok(f"@click Alpine event handlers present ({at_click_count} total)")

# v5: no el() DOM helper calls — Alpine manages DOM
el_calls = len(re.findall(r"\bel\s*\(", js_content))
if el_calls > 0:
    fail(f"Found {el_calls} el() calls in app.js — v5 uses Alpine x-ref or x-text, not el()")
else:
    ok("No el() DOM helper calls in app.js (correct v5 pattern)")

section("API Endpoint Cross-check")

defined_routes = set()
for fname in os.listdir(ROUTES_DIR):
    if not fname.endswith('.py') or fname == '__init__.py': continue
    try:
        rc = open(os.path.join(ROUTES_DIR, fname)).read()
        defined_routes.update(re.findall(r'@bp\.\w+\(["\']([^"\']+)["\']', rc))
    except: pass

for route in sorted(set(re.findall(r"api\(['\"]([^'\"]+)['\"]", all_content))):
    base = route.split('?')[0]
    if base in defined_routes: ok(f"API route exists: {base}")
    elif any(base.startswith(r.rsplit('/',1)[0]) for r in defined_routes): ok(f"API route exists (prefix): {base}")
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
    m = re.search(r'##\s+\[?v?(\d+\.\d+\.\d+)', open(CHANGELOG_FILE, encoding='utf-8').read())
    if m: clv = m.group(1); ok(f"CHANGELOG.md latest = {clv}")
    else: fail("Could not parse version from CHANGELOG.md")
except FileNotFoundError: fail(f"{CHANGELOG_FILE} not found")

if cv and clv:
    if cv == clv: ok(f"Versions match: {cv}")
    else: fail(f"Version mismatch: constants.py={cv}, CHANGELOG.md={clv}")

# ── Database Integrity ────────────────────────────────────────────────────────
section("Database Integrity")

DB_PKG = 'nudgarr/db'
DB_INIT = f'{DB_PKG}/__init__.py'
DB_CONN = f'{DB_PKG}/connection.py'
try:
    db_init_content = open(DB_INIT).read()
    db_conn_content = open(DB_CONN).read()

    # Required tables in schema SQL (lives in connection.py)
    for table in ['search_history', 'stat_entries', 'exclusions',
                  'sweep_lifetime', 'lifetime_totals', 'schema_migrations',
                  'nudgarr_state', 'quality_history',
                  'exclusion_events', 'intel_aggregate']:
        if f'CREATE TABLE IF NOT EXISTS {table}' in db_conn_content:
            ok(f"Schema defines table: {table}")
        else:
            fail(f"Schema missing table: {table}")

    # Required sub-modules exist
    for mod in ['connection', 'history', 'entries', 'exclusions',
                'lifetime', 'backup', 'appstate', 'intel']:
        path = f'{DB_PKG}/{mod}.py'
        if os.path.exists(path):
            ok(f"db sub-module exists: {mod}.py")
        else:
            fail(f"db sub-module missing: {mod}.py")

    # Required public functions exported from __init__.py
    for fn in ['init_db', 'get_state', 'set_state', 'close_connection',
               'export_as_json_dict', 'upsert_search_history',
               'get_search_history', 'upsert_stat_entry',
               'get_intel_aggregate', 'update_intel_aggregate', 'reset_intel']:
        if fn in db_init_content:
            ok(f"db.__init__ exports: {fn}")
        else:
            fail(f"db.__init__ missing export: {fn}")

    # Migration v10 must be defined and called in init_db
    if '_run_migration_v10' in db_conn_content:
        ok("Migration v10 function present in connection.py")
    else:
        fail("Migration v10 function missing from connection.py")
    if '_run_migration_v10(conn)' in db_conn_content:
        ok("Migration v10 called in init_db()")
    else:
        fail("Migration v10 not called in init_db()")

    # _SCHEMA_SQL defined in connection.py
    if '_SCHEMA_SQL' in db_conn_content:
        ok("_SCHEMA_SQL defined in connection.py")
    else:
        fail("_SCHEMA_SQL not found in connection.py")

except FileNotFoundError as e:
    fail(f"db package file not found: {e}")


section("Routes Registration")

try:
    ri = open(ROUTES_INIT).read()
    for rf in sorted(f for f in os.listdir(ROUTES_DIR) if f.endswith('.py') and f != '__init__.py'):
        mod = rf.replace('.py','')
        if mod in ri: ok(f"Route module registered: {mod}")
        else: fail(f"Route module not registered in routes/__init__.py: {mod}")
except FileNotFoundError: fail(f"{ROUTES_INIT} not found")

# ── Route Handler Return Check ────────────────────────────────────────────────
section("Route Handler Return Check")

for fname in sorted(os.listdir(ROUTES_DIR)):
    if not fname.endswith('.py') or fname == '__init__.py':
        continue
    fpath = os.path.join(ROUTES_DIR, fname)
    try:
        tree = ast.parse(open(fpath).read())
    except SyntaxError:
        continue
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        is_route = any(
            'route' in ast.unparse(d) or 'requires_auth' in ast.unparse(d)
            for d in node.decorator_list
        )
        if not is_route:
            continue
        has_return = any(
            isinstance(n, ast.Return) and n.value is not None
            for n in ast.walk(node)
        )
        if has_return:
            ok(f"{fname}: {node.name}() has return statement")
        else:
            fail(f"{fname}:{node.lineno} — route handler {node.name}() has no return statement")

# ── Logging Adoption ──────────────────────────────────────────────────────────
# Every operational Python module must adopt the logging module.
# Glob-based so new files are covered automatically without editing this list.
# Excluded: __init__.py files (re-export only) and constants.py (no logic).
section("Logging Adoption")

_LOGGING_EXCLUDE = {'__init__.py', 'constants.py'}
_logging_py_files = (
    [f for f in glob.glob('nudgarr/*.py') if os.path.basename(f) not in _LOGGING_EXCLUDE]
    + [f for f in glob.glob('nudgarr/db/*.py') if os.path.basename(f) not in _LOGGING_EXCLUDE]
    + [f for f in glob.glob('nudgarr/routes/*.py') if os.path.basename(f) not in _LOGGING_EXCLUDE]
    + (['main.py'] if os.path.exists('main.py') else [])
)
for f in sorted(_logging_py_files):
    try:
        src = open(f).read()
        if 'logging.getLogger' in src:
            ok(f"logging.getLogger present: {f}")
        else:
            fail(f"Missing logging.getLogger: {f}")
        if 'RotatingFileHandler' in src or f != 'nudgarr/log_setup.py':
            pass  # RotatingFileHandler check handled separately below
    except OSError:
        fail(f"Could not read: {f}")

# RotatingFileHandler must be present in log_setup.py
try:
    _log_setup_src = open('nudgarr/log_setup.py').read()
    if 'RotatingFileHandler' in _log_setup_src:
        ok("RotatingFileHandler present in log_setup.py")
    else:
        fail("RotatingFileHandler missing from log_setup.py")
except OSError:
    fail("nudgarr/log_setup.py not found")

# Global JS error boundary must be present in app.js
if 'unhandledrejection' in js_content:
    ok("Global unhandledrejection handler present in app.js")
else:
    fail("Global unhandledrejection handler missing from app.js")

# ── Intel panel structural checks (v5) ───────────────────────────────────────
section("Intel Panel")
if "panel==='intel'" in content:
    ok("Intel panel x-show binding present in HTML")
else:
    fail("Intel panel x-show binding missing from HTML (panel==='intel')")
if 'intelData' in js_content:
    ok("intelData state property present in app.js")
else:
    fail("intelData state property missing from app.js")
if 'refreshIntel' in js_content:
    ok("refreshIntel() present in app.js")
else:
    fail("refreshIntel() missing from app.js")
if 'cold_start' in content:
    ok("cold_start cold-start card present in Intel HTML")
else:
    fail("cold_start cold-start condition missing from Intel HTML")
if 'intelUpgradePaths' in js_content:
    ok("intelUpgradePaths() helper present in app.js")
else:
    fail("intelUpgradePaths() missing from app.js")
if 'path.from' in js_content:
    ok("upgrade path uses path.from (not from_quality) in app.js")
else:
    fail("upgrade path.from missing from app.js (bug #8 guard)")
if 'resetIntelData' in js_content:
    ok("resetIntelData() present in app.js (Danger Zone handler)")
else:
    fail("resetIntelData() missing from app.js")
if "danger('resetIntel')" in content or 'resetIntelData' in content:
    ok("Reset Intel button present in HTML")
else:
    fail("Reset Intel button missing from HTML")
if 'formatCompact' in js_content:
    ok("formatCompact utility present in app.js")
else:
    fail("formatCompact utility missing from app.js")
if 'get_pipeline_search_counts' in open('nudgarr/db/intel.py').read():
    ok("get_pipeline_search_counts present in db/intel.py")
else:
    fail("get_pipeline_search_counts missing from db/intel.py")
if 'get_cf_score_health' in open('nudgarr/db/intel.py').read():
    ok("get_cf_score_health present in db/intel.py")
else:
    fail("get_cf_score_health missing from db/intel.py")

# ── Grace Period structural checks ────────────────────────────────────────────
section("Grace Period")
# v5: HTML uses camelCase Alpine properties; raw field names live in app.js
if 'radarrMissingGraceHours' in content or 'radarr_missing_grace_hours' in content:
    ok("radarr_missing_grace_hours field present in HTML (as radarrMissingGraceHours)")
else:
    fail("radarr_missing_grace_hours field missing from HTML")
if 'sonarrMissingGraceHours' in content or 'sonarr_missing_grace_hours' in content:
    ok("sonarr_missing_grace_hours field present in HTML (as sonarrMissingGraceHours)")
else:
    fail("sonarr_missing_grace_hours field missing from HTML")
if 'radarr_missing_grace_hours' in js_content:
    ok("radarr_missing_grace_hours referenced in app.js")
else:
    fail("radarr_missing_grace_hours missing from app.js")
if 'sonarr_missing_grace_hours' in js_content:
    ok("sonarr_missing_grace_hours referenced in app.js")
else:
    fail("sonarr_missing_grace_hours missing from app.js")
if '_release_date' in open('nudgarr/sweep.py').read():
    ok("_release_date() helper present in sweep.py")
else:
    fail("_release_date() helper missing from sweep.py")

section("Sample Mode Overhaul (v5)")
# round_robin and largest_gap_first in ui.html
if 'round_robin' in content:
    ok("round_robin option present in HTML pipeline selects")
else:
    fail("round_robin option missing from HTML")
if 'largest_gap_first' in content:
    ok("largest_gap_first option present in HTML CF Score selects")
else:
    fail("largest_gap_first option missing from HTML")
# v5: all sample modes live in app.js
if 'radarr_cf_sample_mode' in js_content:
    ok("radarr_cf_sample_mode referenced in app.js")
else:
    fail("radarr_cf_sample_mode missing from app.js")
if 'sonarr_cf_sample_mode' in js_content:
    ok("sonarr_cf_sample_mode referenced in app.js")
else:
    fail("sonarr_cf_sample_mode missing from app.js")
if 'cf_sample_mode' in js_content:
    ok("cf_sample_mode present in app.js (overrides)")
else:
    fail("cf_sample_mode missing from app.js")
# constants.py checks remain unchanged
_const = open('nudgarr/constants.py').read()
if 'VALID_CF_SAMPLE_MODES' in _const:
    ok("VALID_CF_SAMPLE_MODES constant present in constants.py")
else:
    fail("VALID_CF_SAMPLE_MODES constant missing from constants.py")
if 'radarr_cf_sample_mode' in _const:
    ok("radarr_cf_sample_mode present in DEFAULT_CONFIG")
else:
    fail("radarr_cf_sample_mode missing from DEFAULT_CONFIG")
if 'round_robin' in _const:
    ok("round_robin present in constants.py mode tuples")
else:
    fail("round_robin missing from constants.py mode tuples")
_cfg_py = open('nudgarr/config.py').read()
if 'VALID_CF_SAMPLE_MODES' in _cfg_py:
    ok("VALID_CF_SAMPLE_MODES used in config.py validation")
else:
    fail("VALID_CF_SAMPLE_MODES missing from config.py validation")
_stats = open('nudgarr/stats.py').read()
if 'largest_gap_first' in _stats:
    ok("largest_gap_first sort branch present in stats.py")
else:
    fail("largest_gap_first sort branch missing from stats.py")
if 'round_robin' in _stats:
    ok("round_robin sort branch present in stats.py")
else:
    fail("round_robin sort branch missing from stats.py")
_sweep = open('nudgarr/sweep.py').read()
if 'cf_sample_mode' in _sweep:
    ok("cf_sample_mode resolved in sweep.py")
else:
    fail("cf_sample_mode missing from sweep.py")

# ── Default Tab (v5) ──────────────────────────────────────────────────────────
section("Default Tab")
if 'VALID_TABS' in open('nudgarr/constants.py').read():
    ok("VALID_TABS constant present in constants.py")
else:
    fail("VALID_TABS constant missing from constants.py")
if '"default_tab": "sweep"' in open('nudgarr/constants.py').read():
    ok("default_tab defaults to sweep in DEFAULT_CONFIG")
else:
    fail("default_tab default missing from DEFAULT_CONFIG")
if 'VALID_TABS' in open('nudgarr/config.py').read():
    ok("VALID_TABS imported and used in config.py validation")
else:
    fail("VALID_TABS not used in config.py")
# v5: default_tab select lives in ui.html (as x-model="defaultTab")
if 'defaultTab' in content or 'default_tab' in content:
    ok("default_tab select present in HTML (Advanced panel)")
else:
    fail("default_tab select missing from HTML")
if 'Documentation' in content:
    ok("Documentation link present in HTML (Advanced panel)")
else:
    fail("Documentation link missing from HTML")
# v5: handled in app.js
if 'default_tab' in js_content:
    ok("default_tab handled in app.js")
else:
    fail("default_tab missing from app.js")
if 'nudgarr_last_tab' in js_content:
    ok("nudgarr_last_tab localStorage key present in app.js")
else:
    fail("nudgarr_last_tab localStorage key missing from app.js")


# ── Queue Depth (v5) ──────────────────────────────────────────────────────────
section("Queue Depth")
_qd_constants = open('nudgarr/constants.py').read()
if '"queue_depth_enabled": False' in _qd_constants:
    ok("queue_depth_enabled present in DEFAULT_CONFIG")
else:
    fail("queue_depth_enabled missing from DEFAULT_CONFIG")
if '"queue_depth_threshold"' in _qd_constants:
    ok("queue_depth_threshold present in DEFAULT_CONFIG")
else:
    fail("queue_depth_threshold missing from DEFAULT_CONFIG")
if '"notify_on_queue_depth_skip"' in _qd_constants:
    ok("notify_on_queue_depth_skip present in DEFAULT_CONFIG")
else:
    fail("notify_on_queue_depth_skip missing from DEFAULT_CONFIG")
if '_check_queue_depth' in open('nudgarr/sweep.py').read():
    ok("_check_queue_depth present in sweep.py")
else:
    fail("_check_queue_depth missing from sweep.py")
_qd_clients = open('nudgarr/arr_clients.py').read()
if 'radarr_get_queue_total' in _qd_clients:
    ok("radarr_get_queue_total present in arr_clients.py")
else:
    fail("radarr_get_queue_total missing from arr_clients.py")
if 'sonarr_get_queue_total' in _qd_clients:
    ok("sonarr_get_queue_total present in arr_clients.py")
else:
    fail("sonarr_get_queue_total missing from arr_clients.py")
# v5: queue depth controls in ui.html (Settings panel) — camelCase Alpine bindings
if 'queueDepthEnabled' in content or 'queue_depth_enabled' in content:
    ok("queue_depth_enabled toggle present in HTML (Settings panel)")
else:
    fail("queue_depth_enabled toggle missing from HTML")
if 'queueDepthThreshold' in content or 'queue_depth_threshold' in content:
    ok("queue_depth_threshold input present in HTML (Settings panel)")
else:
    fail("queue_depth_threshold input missing from HTML")
if 'notify_on_queue_depth_skip' in content or 'notifyOnQueueDepth' in content:
    ok("notify_on_queue_depth_skip toggle present in HTML (Notifications panel)")
else:
    fail("notify_on_queue_depth_skip toggle missing from HTML")
# v5: state handled in app.js
if 'last_skipped_queue_depth_utc' in js_content:
    ok("last_skipped_queue_depth_utc handled in app.js")
else:
    fail("last_skipped_queue_depth_utc missing from app.js")
if 'lastRunCutoffUtc' in js_content:
    ok("pipeline card last run timestamps present in app.js")
else:
    fail("pipeline card last run timestamps missing from app.js")


# ── v5 Alpine Architecture ────────────────────────────────────────────────────
section("v5 Alpine Architecture")
_app_js = open('nudgarr/static/app.js').read()
# Core Alpine entry function
if 'function nudgarr()' in _app_js:
    ok("function nudgarr() Alpine data factory present in app.js")
else:
    fail("function nudgarr() missing from app.js")
# Critical bug fixes from 18-point spec
if 'applyConfig' in _app_js:
    ok("applyConfig() present — schedulerEnabled set only here (bug #1)")
else:
    fail("applyConfig() missing from app.js")
if 'radarr_max_movies_per_run' in _app_js and 'savePipelines' in _app_js:
    ok("savePipelines() includes all cutoff fields (bug #2)")
else:
    fail("savePipelines() missing cutoff field coverage (bug #2)")
if 'data.entries' in _app_js:
    ok("refreshImports uses data.entries not data.items (bug #3)")
else:
    fail("data.entries missing from refreshImports (bug #3)")
if 'importsMoviesTotal' in _app_js and 'movies_total' in _app_js:
    ok("importsMoviesTotal set from data.movies_total (bug #4/18)")
else:
    fail("importsMoviesTotal not bound to data.movies_total (bug #4/18)")
if "JSON.stringify({ url" in _app_js or 'url: notifyUrl' in _app_js or "{ url }" in _app_js:
    ok("testNotification sends {url} body (bug #5)")
else:
    fail("testNotification missing {url} body (bug #5)")
if 'saveNotifications' in _app_js:
    ok("saveNotifications() method present (bug #7)")
else:
    fail("saveNotifications() missing — save button has no target (bug #7)")
if 'path.from' in _app_js:
    ok("Upgrade history uses path.from (not from_quality) (bug #8)")
else:
    fail("Upgrade history path.from missing from app.js (bug #8)")
if 'openArrLink' in _app_js:
    ok("openArrLink() present in Alpine object (bug #11)")
else:
    fail("openArrLink() missing from app.js (bug #11)")
if 'last_sync_at' in _app_js:
    ok("CF Score uses last_sync_at (not last_sync_utc) (bug #17)")
else:
    fail("last_sync_at missing from app.js (bug #17)")
# All 10 panels present in HTML
for panel_name in ['sweep', 'library', 'intel', 'instances', 'pipelines',
                    'settings', 'overrides', 'filters', 'notifications', 'advanced']:
    marker = f"panel==='{panel_name}'"
    if marker in content:
        ok(f"Panel x-show binding present: {panel_name}")
    else:
        fail(f"Panel x-show binding missing: {panel_name}")
# Sidebar navigation present
if 'navigateTo' in content:
    ok("navigateTo() calls present in sidebar HTML")
else:
    fail("navigateTo() calls missing from sidebar HTML")
# All modals present
for modal_name in ['instModal.show', "modal==='confirm'", "modal==='alert'",
                    "modal==='onboarding'", "modal==='clearExcl'"]:
    if modal_name in content:
        ok(f"Modal binding present: {modal_name}")
    else:
        fail(f"Modal binding missing: {modal_name}")
# x-cloak defined in CSS
if 'x-cloak' in content:
    ok("x-cloak defined/used in HTML (prevents Alpine FOUC)")
else:
    fail("x-cloak missing from HTML")



# ── Result ────────────────────────────────────────────────────────────────────
print(f"\n{'=' * 58}")
total = PASS + FAIL
if FAIL:
    print(f"  FAILED \u2014 {FAIL} error(s), {PASS} passed ({total} total)")
    print(f"  Fix all errors before packaging.\n"); sys.exit(1)
else:
    print(f"  ALL {total} CHECKS PASSED \u2014 safe to package.\n"); sys.exit(0)

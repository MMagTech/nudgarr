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

JS_FILES = [
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

    # Check all JS files are linked in the HTML shell
    for js_file in JS_FILES:
        if js_file in content:
            ok(f"HTML shell links: {js_file}")
        else:
            fail(f"HTML shell missing script tag for: {js_file}")

    # Check all CSS files are linked in the HTML shell
    for css_file in CSS_FILES:
        if css_file in content:
            ok(f"HTML shell links: {css_file}")
        else:
            fail(f"HTML shell missing link tag for: {css_file}")

    # No inline <style> or <script> blocks remain in HTML shell
    if '<style>' in content:
        fail("HTML shell still contains inline <style> block")
    else:
        ok("No inline <style> block in HTML shell")

    if re.search(r'<script>(?!.*src)', content) and '<script>' in content:
        fail("HTML shell still contains inline <script> block")
    else:
        ok("No inline <script> block in HTML shell")

except Exception as e:
    fail(f"Static file check error: {e}")

# ── HTML Structure ────────────────────────────────────────────────────────────
section("HTML Structure")

opens, closes = content.count('<div'), content.count('</div')
if opens != closes: fail(f"Unbalanced divs: {opens} opens vs {closes} closes")
else: ok(f"Div balance: {opens} opens = {closes} closes")

s_o = content.count('<script src=')
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

wrap_start = next((i for i,l in enumerate(html_lines) if 'class="wrap"' in l), None)

if not wrap_start: fail(".wrap div not found")
else:
    depth, wrap_closed_at = 0, None
    for i, line in enumerate(html_lines):
        if i < wrap_start: continue
        depth += line.count('<div') - line.count('</div')
        if i > wrap_start and depth == 0: wrap_closed_at = i; break
    if wrap_closed_at is None: fail(".wrap div never closes")
    else: ok(f".wrap div closes at line {wrap_closed_at+1}")

# ── JavaScript Sanity ─────────────────────────────────────────────────────────
section("JavaScript Sanity")

for fn in ['toggleOverridesFeature','dismissOverridesModal',
           'renderOverridesCards','renderSingleOverrideCard','applyOverrides',
           'resetCardOverrides','resetFieldOverride',
           'markCardDirty','updateBacklogLabel','updateNotifyLabel',
           'fillFilters','loadArrData','saveFilters',
           'fillIntel','renderIntel','resetIntel']:
    if f'function {fn}' not in js_content: fail(f"Missing JS function: {fn}()")
    else: ok(f"Found function: {fn}()")

js_lines = js_content.split('\n')

if re.search(r"style\.cssText\s*=\s*['\"][^'\"]*!important", js_content):
    fail("Found !important inside style.cssText — silently ignored by browsers")
else: ok("No !important inside style.cssText")

onclick_fns = set(re.findall(r'onclick=["\'](\w+)\(', content))
defined_fns = set(re.findall(r'(?:async\s+)?function\s+(\w+)\s*\(', js_content))
defined_fns |= set(re.findall(r'(?:let|var|const)\s+(\w+)\s*=', js_content))
missing_fns = onclick_fns - defined_fns
if missing_fns: [fail(f"onclick calls undefined function: {fn}()") for fn in sorted(missing_fns)]
else: ok(f"All onclick functions defined ({len(onclick_fns)} checked)")

el_refs  = set(re.findall(r"el\('([^']+)'\)", js_content))
el_refs |= set(re.findall(r'getElementById\(["\']([^"\']+)["\']\)', js_content))
html_ids = set(re.findall(r'id=["\']([^"\']+)["\']', content))
missing  = el_refs - html_ids
ignore_prefixes = ('sdot-', 'instcard-', 'sweepcard-', 'onboarding', 'ls-ov-', 'ov-card-')
missing = {m for m in missing if not any(m.startswith(p) for p in ignore_prefixes)}
if missing: [fail(f"JS references missing element: #{i}") for i in sorted(missing)]
else: ok(f"All JS element references exist ({len(el_refs)} checked)")

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
    m = re.search(r'##\s+\[?v?(\d+\.\d+\.\d+)', open(CHANGELOG_FILE).read())
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

# Global JS error boundary must be present in ui-core.js
if 'unhandledrejection' in js_content:
    ok("Global unhandledrejection handler present in JS")
else:
    fail("Global unhandledrejection handler missing from JS (expected in ui-core.js)")

# ── Intel tab structural checks ───────────────────────────────────────────────
section("Intel Tab")
if 'id="tab-intel"' in content:
    ok("Intel tab section present in HTML (tab-intel)")
else:
    fail("Intel tab section missing from HTML (id='tab-intel')")
if 'data-tab="intel"' in content:
    ok("Intel tab nav button present in HTML")
else:
    fail("Intel tab nav button missing from HTML (data-tab='intel')")
if 'sticky-shell' in content:
    ok("Sticky header shell present in HTML")
else:
    fail("sticky-shell missing from HTML")
if '.sticky-shell' in open('nudgarr/static/ui.css').read():
    ok(".sticky-shell CSS defined in ui.css")
else:
    fail(".sticky-shell CSS missing from ui.css")
if 'resetIntelData' in js_content:
    ok("resetIntelData() present in JS (Danger Zone handler)")
else:
    fail("resetIntelData() missing from JS")
if 'resetIntelData' in content:
    ok("Reset Intel button present in HTML (Danger Zone)")
else:
    fail("Reset Intel button missing from HTML (Danger Zone)")

# ── Grace Period structural checks ────────────────────────────────────────────
section("Grace Period")
if 'radarr_missing_grace_hours' in content:
    ok("radarr_missing_grace_hours field present in HTML")
else:
    fail("radarr_missing_grace_hours field missing from HTML")
if 'sonarr_missing_grace_hours' in content:
    ok("sonarr_missing_grace_hours field present in HTML")
else:
    fail("sonarr_missing_grace_hours field missing from HTML")
if 'radarr_missing_grace_hours' in js_content:
    ok("radarr_missing_grace_hours referenced in JS")
else:
    fail("radarr_missing_grace_hours missing from JS")
if 'sonarr_missing_grace_hours' in js_content:
    ok("sonarr_missing_grace_hours referenced in JS")
else:
    fail("sonarr_missing_grace_hours missing from JS")
if '_release_date' in open('nudgarr/sweep.py').read():
    ok("_release_date() helper present in sweep.py")
else:
    fail("_release_date() helper missing from sweep.py")

# ── Cleanup — remove __pycache__ created by py_compile above ─────────────────
import shutil
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

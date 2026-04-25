# Contributing to Nudgarr

Thanks for your interest in contributing. This document covers the project structure, how the pieces connect, how to run locally, and where to make common types of changes.

Nudgarr is a lightweight project -- the goal is to keep it that way. If you're considering a larger change, opening an issue to discuss it first is always appreciated.

---

## Project structure

As of v5.0.0, Nudgarr uses a SQLite database for all persistence via the `nudgarr/db/` package and an Alpine.js single-file frontend. Patch releases (v5.0.1, etc.) are listed at the top of `CHANGELOG.md`; `constants.py` `VERSION` must match the latest changelog heading (enforced by `validate.py`).

```
nudgarr/                    <- Python package
  __init__.py               <- package metadata, exposes __version__
  constants.py              <- VERSION, file paths, DEFAULT_CONFIG
  utils.py                  <- shared helpers: time, file I/O, HTTP, URL validation, jitter
  config.py                 <- load, validate, and deep-copy config
  cf_effective.py           <- CF Score effective enablement: effective_cf_score_enabled(),
                               allowed_cf_score_instance_ids(),
                               prune_cf_entries_on_effective_disable_transition().
                               Also defines CF_LAST_INSTANCE_SYNC_PREFIX and
                               CF_SCAN_SNAPSHOT_PREFIX -- import from here, not the syncer.
  db/                       <- SQLite persistence layer (package)
    __init__.py             <- public API -- re-exports everything below
    connection.py           <- thread-local connection, _SCHEMA_SQL, init_db, close_connection
    history.py              <- search_history table; get_search_history() accepts optional
                               since (ISO UTC, last_searched_ts), type_filter (Cutoff Unmet /
                               Backlog / CF Score), and title_search (substring on title).
                               Used by Library History and any caller of /api/state/items
    entries.py              <- stat_entries table; get_imports_since(since_utc) counts confirmed
                               imports by app since a UTC timestamp
    exclusions.py           <- exclusions table
    lifetime.py             <- sweep_lifetime and lifetime_totals tables
    appstate.py             <- nudgarr_state key/value table; get_state, set_state,
                               delete_state, delete_states_with_prefix
    backup.py               <- JSON export helper
    intel.py                <- intel_aggregate and exclusion_events tables; get_intel_aggregate,
                               update_intel_aggregate, reset_intel, get_pipeline_search_counts,
                               get_cf_score_health. Also reads CF_SCAN_SNAPSHOT_PREFIX from
                               cf_effective for per-instance scan count display in Intel.
    cf_scores.py            <- cf_score_entries table; upsert, query, reset;
                               count_cf_score_entries() / get_cf_score_entries() support
                               search (title LIKE), sort_col/sort_dir, and arr_instance_id
                               filter (composite key must match cf_score_syncer:
                               radarr|url or sonarr|url, trailing slash stripped);
                               delete_cf_scores_for_instance(arr_instance_id);
                               get_cf_max_last_synced_at_for_instance(arr_instance_id) -- MAX
                               last_synced_at before prune, used to preserve last sync time
  state.py                  <- exclusions and history helpers built on top of nudgarr.db;
                               also exposes state_key(name, url) -- the canonical composite
                               key used across search_history, stat_entries, and cooldown
                               lookups
  auth.py                   <- password hashing, lockout, session checks
  notifications.py          <- Apprise wrappers (sweep complete, import, error)
  log_setup.py              <- logging initialisation and runtime level control
  arr_clients.py            <- Radarr and Sonarr API calls; pagination handled internally;
                               CF Score API functions (cf_get_quality_profiles, cf_radarr_*,
                               cf_sonarr_*) in the CF Score Scan section at the bottom
  cf_score_syncer.py        <- CustomFormatScoreSyncer; full library sync logic for Radarr
                               and Sonarr; applies tag/profile sweep filters at write time;
                               writes live sync progress and CF_SCAN_SNAPSHOT_PREFIX state
                               to nudgarr_state per instance
  stats.py                  <- import tracking, cooldown logic, stat recording
  globals.py                <- Flask app instance, STATUS dict, RUN_LOCK, security headers,
                               persistent secret key
  sweep.py                  <- run_sweep orchestrator + per-instance helpers; CF Score third
                               pipeline pass after Cutoff Unmet and Backlog
  scheduler.py              <- cron scheduler, import check loop, cf_score_sync_loop;
                               writes STATUS["last_sweep_start_utc"] before run_sweep() and
                               STATUS["imports_confirmed_sweep"] after; persists per-pipeline
                               last run timestamps to nudgarr_state
  routes/                   <- Flask blueprints (one file per domain)
    __init__.py             <- register_blueprints() -- called once from main.py
    auth.py                 <- /, /login, /setup, /api/auth/*, /api/setup; the GET / handler
                               (index()) is the only place that calls
                               render_template('ui.html', VERSION=VERSION)
    config.py               <- /api/config, /api/instance/toggle, onboarding,
                               /api/whats-new/dismiss
    arr.py                  <- /api/arr/tags, /api/arr/profiles
    sweep.py                <- /api/status, /api/run-now, /api/test, /api/test-instance
    state.py                <- /api/state/*, /api/state/clear, /api/file/*, /api/exclusions*,
                               /api/arr-link; GET /api/state/items passes type & search query
                               params through to get_search_history()
    stats.py                <- /api/stats (instance, type, search, period, pagination),
                               /api/stats/clear, check-imports
    intel.py                <- /api/intel, /api/intel/reset
    cf_scores.py            <- /api/cf-scores/status, /api/cf-scores/entries (instance_id,
                               search, sort, dir), /api/cf-scores/scan, /api/cf-scores/reset
    notifications.py        <- /api/notifications/test
    diagnostics.py          <- /api/diagnostic, /api/log/clear
  static/                   <- JS and CSS served as static assets
    app.js                  <- entire Alpine.js frontend; single nudgarr() function with all
                               state, computed props, and methods
    alpine.min.js           <- Alpine.js v3.15.11, self-hosted (no CDN dependency)
    fonts/                  <- Outfit and JetBrains Mono, served locally
  templates/                <- HTML served by Flask render_template()
    login.html              <- login page
    setup.html              <- first-run setup page
    ui.html                 <- full Alpine.js UI; <body x-data="nudgarr()">
main.py                     <- entry point: signals, startup ping, thread launch and join
nudgarr.py                  <- compatibility shim for source runners (deprecated)
validate.py                 <- pre-package static analysis tool
```

---

## Database

All persistence goes through the `nudgarr/db/` package. Import from it as `from nudgarr.db import ...` or `from nudgarr import db`.

The database lives at `/config/nudgarr.db` by default (controlled by the `DB_FILE` env var). Schema is defined in `_SCHEMA_SQL` in `nudgarr/db/connection.py` and applied by `init_db()`. Migrations are versioned in the `schema_migrations` table. If adding a new migration, write a new `_run_migration_vN` function in `nudgarr/db/connection.py` and call it from `init_db()`. Do not modify or remove existing migration functions -- they may have already run on installed databases.

**Intel aggregate write points**

`intel_aggregate` is a protected accumulator -- it must never be cleared by any normal operation (Clear History, Clear Imports, pruning). It is only reset by the explicit Reset Intel action at the bottom of the Intel panel. The aggregate is updated at two write points:

- `confirm_stat_entry()` in `db/entries.py` -- snapshots turnaround, searches per import, pipeline import split (Cutoff Unmet via `entry_type="Upgraded"`, CF Score via `entry_type="CF Score"`, Backlog via all other types), quality upgrades, iteration counts, and per-instance imports and turnaround at the moment each import is confirmed.
- `reset_intel()` in `db/intel.py` -- the only operation that clears both `intel_aggregate` and `exclusion_events`.

Note: `success_total_worked` and `library_age_buckets` remain as columns in `intel_aggregate` but are no longer written to as of v4.3.0. They are unused orphan columns retained to avoid a migration.

All aggregate writes happen inside the same transaction as the operation that triggers them. A rollback undoes both the primary write and the aggregate update atomically.

Live Intel queries (pipeline search counts, CF Score health) read directly from `search_history` and `cf_score_entries` at request time via `get_pipeline_search_counts()` and `get_cf_score_health()` in `db/intel.py`. These are not stored in the aggregate and are not affected by Reset Intel.

**Exclusion event write points**

`exclusion_events` is append-only. A row is written at every exclude and unexclude action in `db/exclusions.py`: `add_exclusion()`, `add_auto_exclusion()`, `remove_exclusion()`, and `clear_auto_exclusions()`. The table is never modified outside of `reset_intel()`.

| Table | Purpose |
|---|---|
| `search_history` | Every item Nudgarr has searched, with cooldown timestamps |
| `stat_entries` | Items pending import confirmation and confirmed imports |
| `quality_history` | Per-import quality upgrade records for the Imports tooltip |
| `exclusions` | Titles excluded from sweeps -- source, search count, acknowledged flag |
| `exclusion_events` | Append-only audit log of every exclude/unexclude action |
| `intel_aggregate` | Single protected row accumulating lifetime Intel metrics |
| `cf_score_entries` | CF Score index -- monitored files below their cutoff score |
| `sweep_lifetime` | Per-instance lifetime sweep stats |
| `lifetime_totals` | Lifetime confirmed import counts (movies/shows) |
| `nudgarr_state` | General key/value persistent state (e.g. last run time) |
| `schema_migrations` | Records which migrations have been applied |

---

## Import graph

Understanding what imports what avoids circular dependency issues. The rule is simple: modules lower in the list may import from modules higher up, never the reverse.

```
constants
  |-- log_setup             (imports constants only -- sits alongside utils)
  |-- cf_effective          (imports constants + stdlib only; db imported lazily
  |                          inside prune_cf_entries_on_effective_disable_transition
  |                          to avoid a circular import)
  `-- utils
        `-- db
              `-- config
                    `-- state
                          |-- auth
                          |-- notifications
                          `-- stats
                                `-- arr_clients
                                      `-- sweep
                                            `-- scheduler
globals  <-- imports only constants + stdlib (Flask, threading, os)
routes/* <-- import from globals + any module above them
main.py  <-- imports from routes, scheduler, globals, log_setup
```

`globals.py` is the one module with a special rule: it must only import from `constants` and the Python standard library. Everything else imports `globals` to get the `app`, `STATUS`, and `RUN_LOCK` objects. Breaking this rule will create a circular import.

`cf_effective.py` follows a similar rule: it imports only from `constants` and the standard library at module level. The `db` import inside `prune_cf_entries_on_effective_disable_transition` is deferred (local import) to avoid a circular dependency since `db/cf_scores.py` imports from `cf_effective`.

**Known exception -- `routes/stats.py` imports from `scheduler`:** The manual import-check endpoint calls `_run_auto_exclusion_check` directly from `scheduler.py`. This is the only place a route file reaches up into `scheduler`. Do not add further route-to-scheduler imports without a clear reason.

---

## How a sweep works

1. `scheduler_loop` in `scheduler.py` runs on a timer (or responds to `run_requested`)
2. It writes `STATUS["last_sweep_start_utc"]` immediately before calling `run_sweep(cfg, session)`
3. `run_sweep` in `sweep.py` runs `_check_queue_depth` -- if queue depth is enabled, one `GET /api/v3/queue/status` call is made per enabled instance, totals are summed, and the sweep is skipped entirely if the sum meets or exceeds the threshold (fail-open on instance errors). If skipped, `STATUS["last_skipped_queue_depth_utc"]` is set and persisted.
4. `run_sweep` then runs `_run_auto_unexclude` and iterates over configured Radarr and Sonarr instances in a unified loop, calling `_sweep_instance(app=...)` for each
5. Each instance helper calls `arr_clients.py` to fetch eligible items -- pagination is handled internally with no item cap. The helper then applies exclusions, tag/profile filters, and queue filtering, applies cooldown logic from `stats.py`, calls the search API, then records results in a single batched transaction via `nudgarr/db/`
6. `run_sweep` returns a summary dict
7. `scheduler_loop` stores the summary in `STATUS["last_summary"]`, persists `last_run_utc` and per-pipeline timestamps (`last_run_cutoff_utc`, `last_run_backlog_utc`, `last_run_cfscore_utc`) to `nudgarr_state`, populates `STATUS["imports_confirmed_sweep"]` via `get_imports_since()`, triggers notifications, and runs import checks
8. A separate `import_check_loop` thread runs independently, polling for confirmed imports without waiting for a sweep. After each cycle it also runs the auto-exclusion evaluation

---

## How a request works

1. `main.py` calls `register_blueprints()` which registers all route blueprints with the Flask app
2. A request arrives at one of the endpoints
3. The `@requires_auth` decorator in `auth.py` checks session validity and runs a CSRF origin check on POST requests before the handler runs
4. The handler reads/writes state via `nudgarr/db/` and `state.py`, config via `config.py`, and updates `STATUS` in `globals.py`
5. Flask serialises the response as JSON (most endpoints) or renders a template

---

## Running locally (without Docker)

**Requirements:** Python 3.12+, pip

**Shutdown:** Nudgarr handles SIGTERM and SIGINT cleanly via a `threading.Event`. On `docker stop`, any in-progress sweep is allowed to finish before the process exits.

```bash
# Install dependencies (includes Waitress)
pip install -r requirements.txt

# Run
python main.py
```

The app will start on port 8085 by default. The database and config are written to `/config/` -- you can override with environment variables:

```bash
export CONFIG_FILE=./config/nudgarr-config.json
export DB_FILE=./config/nudgarr.db
export PORT=8085
python main.py
```

---

## Running with Docker

```bash
docker build -t nudgarr .
docker run -p 8085:8085 -v ./config:/config nudgarr
```

Or use the provided `docker-compose.yml`.

---

## Making changes

### Adding a new config key

1. Add the key with its default value to `DEFAULT_CONFIG` in `constants.py`
2. Add a validation rule in `validate_config()` in `config.py` if needed
3. Read the value via `cfg.get("your_key", default)` wherever it is used

If the key accepts a fixed set of string values, define the allowed values as a tuple constant in `constants.py` (see `VALID_SAMPLE_MODES` for the pattern) and import it in both `config.py` and wherever the value is consumed.

**Frontend wiring (if the key is exposed in Settings, Pipelines, or Advanced):**

The config arrives in the browser via `/api/config` and is applied to the Alpine.js state object by `applyConfig()` in `app.js`. To wire up a new key:

4. **HTML control** -- add the input or toggle element to the relevant panel section in `ui.html`. Use `x-model` to bind to the matching state property (e.g. `x-model="myCooldownHours"`), or `@change="unsaved.settings = true"` for fields that require a Save button.
5. **State declaration** -- add the property to the matching state section in `nudgarr()` in `app.js` with a sensible default (e.g. `myCooldownHours: 0`).
6. **applyConfig()** -- in the `applyConfig()` method, read from `this.cfg` into your state property: `this.myCooldownHours = this.cfg.my_cooldown_hours ?? 0;`
7. **_syncFullCfgFromUi()** -- in the `_syncFullCfgFromUi()` method, write back to `this.cfg`: `this.cfg.my_cooldown_hours = Number(this.myCooldownHours);` This method is called by every panel's `savePanel()` before the POST to `/api/config`.

### Adding a new API endpoint

1. Decide which blueprint it belongs to (or create a new one under `routes/`)
2. Add the route handler to that blueprint file
3. Apply the `@requires_auth` decorator from `nudgarr.auth` to every handler that requires an authenticated session -- which is every endpoint except `/login`, `/setup`, and the `POST /api/auth/*` and `POST /api/setup` endpoints. The decorator also runs a CSRF origin check on every POST.
4. If it is a new blueprint, register it in `routes/__init__.py`

If your endpoint returns any part of the config, use `_mask_config()` from `routes/config.py` to strip API keys before serialising the response.

### Changing sweep behaviour

The sweep logic lives entirely in `sweep.py`. `_sweep_instance` is the shared per-instance worker -- most sweep changes happen there. It accepts an `app` parameter (`"radarr"` or `"sonarr"`) and handles all per-app differences internally via conditional blocks.

**Backlog (missing) pipeline filters**

The missing search pipeline applies filters in this order before handing items to `pick_items_with_cooldown`:

1. Excluded titles filter
2. Queue filter -- items already actively downloading are skipped
3. `minimumAvailability` filter -- Radarr items not yet past their availability status are dropped
4. Age filter -- Radarr only; items added within `missing_added_days` days are dropped
5. Grace period filter -- items whose release date falls within `missing_grace_hours` are skipped

`_release_date(rec)` checks `releaseDate`, `physicalRelease`, `digitalRelease`, `inCinemas`, `airDateUtc`, `airDate` in that order. If you add a new date field to the API response, add it to this helper's field list.

**`pick_items_with_cooldown` and max_per_run**

`pick_items_with_cooldown` in `stats.py` applies the cooldown filter, sorts by sample mode, and caps the result. `max_per_run=0` means all eligible items are returned. The guard in `_sweep_instance` is `if backlog_enabled:` (not `if backlog_enabled and missing_max > 0:`).

Supported sort branches: `random`, `alphabetical`, `oldest_added`, `newest_added`, `round_robin`, `largest_gap_first`. Unrecognised mode strings fall through without sorting, preserving input order.

### Changing database schema

1. Add new columns or tables to `_SCHEMA_SQL` in `nudgarr/db/connection.py` for fresh installs
2. Write a new `_run_migration_vN` function in `nudgarr/db/connection.py` that applies the change to existing databases
3. Call it from `init_db()` in the migration chain
4. Never modify existing migration functions -- they may have already run on user databases

### Changing the UI

The frontend is a two-file Alpine.js app -- no build step required. `nudgarr/templates/ui.html` contains the full HTML with Alpine directives. `nudgarr/static/app.js` contains the single `nudgarr()` function that defines all reactive state, computed properties, and methods. `alpine.min.js` is self-hosted -- no CDN dependency.

**Alpine.js basics for this codebase**

- The root element is `<body x-data="nudgarr()" x-init="...">`. Every Alpine directive in `ui.html` resolves against the object returned by `nudgarr()`.
- Use `x-show="someCondition"` to show/hide elements. Use `x-model="someProperty"` for two-way input binding. Use `x-for`, `x-bind`, and `@click` / `@input` for loops, attribute binding, and event handlers.
- All state lives on the `nudgarr()` object. Do not use global JS variables for reactive state -- Alpine will not track them.
- `this.cfg` holds the raw config object returned by `/api/config` (with API keys masked). `applyConfig()` reads from `this.cfg` into flattened state properties for the UI. `_syncFullCfgFromUi()` writes those properties back to `this.cfg` before a save.
- The `el()` helper from v4 is gone. Reference elements via Alpine directives, or use `document.getElementById()` only for non-reactive imperatives (e.g. focusing an input after a modal opens).

**Panels and navigation**

`this.panel` holds the name of the currently visible panel (e.g. `'sweep'`, `'library'`, `'instances'`). Call `navigateTo(name)` to switch panels -- this sets `this.panel` and triggers any data fetch needed for that panel.

Each panel section in `ui.html` is wrapped in `<div x-show="panel==='panelName'" class="panel">`. The sidebar nav items use `:class="{ active: panel==='panelName' }"` and `@click="navigateTo('panelName')"`.

The Library panel has a sub-view switcher (`this.libView`). Valid values are `'history'`, `'imports'`, `'cfscores'`, `'exclusions'`. Use `setLibView(v)` to switch between them.

**Instance dropdown keys (`allInstances` computed in `app.js`)**

Each row includes `key` (`InstanceName|normalisedUrl`) for endpoints that resolve the instance by URL (e.g. `GET /api/state/items?instance=...`). It also includes `cfKey` (`radarr|url` or `sonarr|url`, same shape as `cf_score_syncer._make_instance_id`) for `GET /api/cf-scores/entries?instance_id=...`, which must match `cf_score_entries.arr_instance_id`. Use `inst.key` in History filters and `inst.cfKey` in the CF Score instance dropdown — they are not interchangeable.

**Unsaved changes tracking**

Each panel that has a Save button tracks its own dirty state via `this.unsaved.panelName`. The amber dot in the sidebar is driven by `unsaved[panel]`. Set it to `true` when a field changes (e.g. `@change="unsaved.settings = true"` on the panel wrapper div). It is cleared by the panel's save method after a successful POST.

Toggle controls use `@click` handlers that call the relevant `toggle*()` method and auto-save immediately -- they do not set `unsaved`. Field inputs that require a deliberate Save use `@change` or `@input` to set `unsaved`.

**Save messages**

Each panel has a corresponding `this.saveMsg.panelName` string that shows an inline status message (e.g. `'Saved'`, `'Error saving'`). Call `_fadeSaveMsg('panelName')` after setting it to clear it after 3 seconds. Do not use a modal for save success -- the inline message pattern is standard across all panels.

**Poll cycle**

`_pollCycle()` in `app.js` runs every 5 seconds. It fetches `/api/status`, calls `applyStatus(st)` to update sweep state, and auto-refreshes the active library view if a sweep just finished. If you add a feature that needs periodic UI updates, add it here rather than creating a separate interval.

**Static file cache-busting**

All static file URLs in `ui.html` include `?v={{ VERSION }}` via Flask's `url_for` (e.g. `url_for('static', filename='app.js', v=VERSION)`). If you add a new static file, follow this pattern -- do not use bare string URLs.

### Adding a new panel

Five places must all be touched in concert.

1. **Panel section in `ui.html`** -- add `<div x-show="panel==='myPanel'" class="panel">...</div>` alongside the existing panel divs.
2. **Sidebar nav item** -- add a `<div class="nav-item" :class="{ active: panel==='myPanel' }" @click="navigateTo('myPanel')">My Panel</div>` in the appropriate sidebar group (Monitor / Configure / System).
3. **State in `nudgarr()`** -- add a state section comment and declare any properties your panel needs.
4. **navigateTo hook (if needed)** -- if your panel needs a data fetch when first opened, add `if (name === 'myPanel') this.refreshMyPanel();` inside `navigateTo()` in `app.js`.
5. **validate.py and tests** -- add the panel name to the `VALID_PANELS` list in `validate.py` and update `EXPECTED_CHECK_COUNT` in `tests/test_frontend_structure.py` to match the new check count.

If your panel has unsaved changes, add a `myPanel: false` entry to the `unsaved` object at the top of `nudgarr()` and add `@change="unsaved.myPanel = true"` on the panel wrapper div in `ui.html`.

### Adding a new config key to CF Score effective enablement

If you add a config toggle that controls whether CF Score is active for an instance, it must be reflected in `effective_cf_score_enabled()` in `cf_effective.py`. That function is the single source of truth for the master -> per-app -> per-instance hierarchy. The syncer, sweep, Intel, and config-save pruning all call through it. Do not add inline enablement checks elsewhere.

### Changing authentication

Auth logic -- hashing, lockout, session checks, the `@requires_auth` decorator -- is in `nudgarr/auth.py`. The decorator also runs `_csrf_origin_ok()` on every POST request. Session cookie settings are in `nudgarr/globals.py`.

The session secret key is managed by `_load_or_create_secret_key()` in `nudgarr/globals.py`. It checks for a `SECRET_KEY` env var first, then reads or creates `/config/nudgarr-secret.key`. Avoid moving this logic outside `globals.py` -- it must run before any route is registered.

### Adding logging to a new module

Every operational module declares a module-level logger at the top of the file:

```python
import logging
logger = logging.getLogger(__name__)
```

The `nudgarr` root logger is configured by `log_setup.py` at startup -- child loggers inherit its level and handlers automatically. Use `logger.debug` for per-item detail, `logger.info` for lifecycle events, `logger.warning` for recoverable issues, and `logger.exception` inside except blocks to capture the full traceback. `validate.py` enforces that every operational file has a logger -- new files without one will fail the Logging Adoption check.

---

## Validation

Run `validate.py` before packaging to catch structural issues early:

```bash
python3 validate.py
```

Run the structural test suite to verify file ownership, Alpine bindings, and split integrity:

```bash
pytest tests/test_frontend_structure.py -v
```

The test suite must pass at exactly the expected check count. If you add or remove files, Alpine panel `x-show` bindings, or validate.py checks, update `EXPECTED_CHECK_COUNT` in `tests/test_frontend_structure.py` to match the new count.

The current expected check count is **359** (defined at the top of `tests/test_frontend_structure.py`). If validate.py gains or loses checks -- which happens when you add new route files, new Alpine panel bindings, or new required modal bindings -- update this constant or the test will fail with a count mismatch even though validate.py itself passes.

This checks:

| Check | What it does |
|---|---|
| Packaging Hygiene | Cleans and verifies no `__pycache__` dirs or bytecode files are present |
| Python Syntax | `py_compile` on every `.py` file |
| Stub Function Detection | AST check -- flags docstring-only, pass-only, and annotated-return stubs |
| Database Connection Integrity | Flags db functions using `conn.` without `get_connection()`, or `conn.commit()` without `conn.execute()` |
| Static Files | Expected JS and CSS files present and linked in `ui.html` |
| HTML Structure | Div balance, duplicate IDs |
| Alpine Bindings | Panel `x-show` bindings, `navigateTo()` calls, required modal bindings, `x-cloak` |
| API Endpoint Cross-check | Every `_api('/api/...')` call in `app.js` has a matching backend route |
| Version Consistency | `constants.py` VERSION matches the latest entry in `CHANGELOG.md` |
| Database Integrity | Required tables, functions, and schema SQL present in `nudgarr/db/` |
| Routes Registration | All blueprint modules registered in `routes/__init__.py` |
| Route Handler Return Check | Every `@bp.route` and `@requires_auth` handler has a return statement |
| Logging Adoption | Every operational `.py` file declares a module-level logger via `logging.getLogger` |

---

## CI checks

The CI workflow (`.github/workflows/ci.yml`) runs four checks on every push:

| Check | What it does |
|---|---|
| Python syntax | `py_compile` on every `.py` file |
| Flake8 lint | Style and import checks, max line length 120 |
| JS syntax | Runs `node --check` on `app.js` |
| Element ID consistency | Verifies Alpine `:id` and `x-ref` references in `app.js` have matching elements in `ui.html` |

Run them locally before pushing:

```bash
# Syntax
for f in main.py nudgarr/*.py nudgarr/routes/*.py nudgarr/db/*.py; do python -m py_compile "$f"; done

# Lint
pip install flake8
flake8 main.py nudgarr/ --max-line-length=120 --ignore=E501,W503

# JS (requires Node.js)
node --check nudgarr/static/app.js && echo "OK"

# Full structural check
python3 validate.py
```

---

## Forking for additional arr support

Nudgarr intentionally supports only Radarr and Sonarr. If you want to add Readarr, Lidarr, or another arr, the changes are contained:

- **API calls:** add a new section to `arr_clients.py` following the existing Radarr/Sonarr pattern
- **CF Score enablement:** add a per-app toggle key to `DEFAULT_CONFIG` and extend `effective_cf_score_enabled()` in `cf_effective.py` to handle the new app type
- **Sweep:** extend `_sweep_instance` in `sweep.py` -- add callables to the `if app == ...` block at the top of the function and any app-specific pipeline differences as conditional blocks. Add the new app to the `run_sweep` loop.
- **Database:** the schema is keyed by app name -- adding a new app type flows through automatically
- **UI:** the instance cards, sweep cards, and history filters in `ui.html` / `app.js` are data-driven -- adding a new app type flows through automatically once the backend returns data for it
- **Overrides:** `_buildOverrideData()` in `app.js` builds override columns per app. The first divider uses `:first-child` CSS to remove its top margin, which assumes Radarr always renders first. If a third app type is added, apply an explicit `.ov-divider-first` class to the first divider in the render loop instead.

---

## Questions

Check the [wiki](https://github.com/MMagTech/nudgarr/wiki) first -- setup, settings, and common questions are covered there. For anything not answered, open an issue on GitHub. If you are working on something larger, it is worth discussing the approach before building it.

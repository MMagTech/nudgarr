# Contributing to Nudgarr

Thanks for your interest in contributing. This document covers the project structure, how the pieces connect, how to run locally, and where to make common types of changes.

Nudgarr is a lightweight project — the goal is to keep it that way. If you're considering a larger change, opening an issue to discuss it first is always appreciated.

---

## Project structure

As of v4.0.0, Nudgarr uses a SQLite database for all persistence via the `nudgarr/db/` package.

```
nudgarr/                    ← Python package
  __init__.py               ← package metadata, exposes __version__
  constants.py              ← VERSION, file paths, DEFAULT_CONFIG
  utils.py                  ← shared helpers: time, file I/O, HTTP, URL validation, jitter
  config.py                 ← load, validate, and deep-copy config
  db/                       ← SQLite persistence layer (package)
    __init__.py             ← public API — re-exports everything below
    connection.py           ← thread-local connection, _SCHEMA_SQL, init_db, close_connection
    history.py              ← search_history table
    entries.py              ← stat_entries table
    exclusions.py           ← exclusions table
    lifetime.py             ← sweep_lifetime and lifetime_totals tables
    appstate.py             ← nudgarr_state key/value table
    backup.py               ← JSON export helper
    intel.py                ← intel_aggregate and exclusion_events tables; get_intel_aggregate, update_intel_aggregate, reset_intel
  state.py                  ← exclusions and history helpers built on top of nudgarr.db;
                              also exposes state_key(name, url) — the canonical composite
                              key used across search_history, stat_entries, and cooldown
                              lookups. Use this function whenever you need to build or
                              compare an instance key; do not compute the format inline.
  auth.py                   ← password hashing, lockout, session checks
  notifications.py          ← Apprise wrappers (sweep complete, import, error)
  log_setup.py              ← logging initialisation and runtime level control
  arr_clients.py            ← Radarr and Sonarr API calls; pagination handled internally, callers receive a flat list
                              CF Score API functions (cf_get_quality_profiles, cf_radarr_*, cf_sonarr_*) appended
                              at the bottom under the CF Score Scan section heading.
                              cf_radarr_get_all_movies fetches all monitored movies with hasFile=true and
                              isAvailable=true. Does NOT filter on qualityCutoffNotMet — CF Score scans all
                              monitored files regardless of quality tier. Returns tag_ids and added_date per movie.
                              cf_sonarr_get_all_series returns tag_ids. Both tag_ids fields used by the syncer
                              to apply sweep filters at write time.
  cf_score_syncer.py        ← CustomFormatScoreSyncer class; full library sync logic for Radarr and Sonarr;
                              applies tag/profile sweep filters at write time (syncer-as-gatekeeper);
                              writes live sync progress to nudgarr_state per instance for ring chart animation;
                              _make_instance_id() helper used by both syncer and sweep to ensure consistent keys
  stats.py                  ← import tracking, cooldown logic, stat recording
  globals.py                ← Flask app instance, STATUS dict, RUN_LOCK, security headers, persistent secret key
  sweep.py                  ← run_sweep orchestrator + per-instance helpers; CF Score third pipeline pass at
                              the end of _sweep_instance, after Cutoff Unmet and Backlog passes; CF Score pass
                              applies the full filter chain (exclusions, queue skip, cooldown) via
                              pick_items_with_cooldown before capping at cf_max
  scheduler.py              ← scheduler loop, import check loop, cf_score_sync_loop, banner, WSGI server starter
  routes/                   ← Flask blueprints (one file per domain)
    __init__.py             ← register_blueprints() — called once from main.py
    auth.py                 ← /, /login, /setup, /api/auth/*, /api/setup;
                              the GET / handler (index()) is the only place that calls
                              render_template('ui.html', VERSION=VERSION) — if you need
                              to pass a new template variable to the UI shell, this is
                              the function to change
    config.py               ← /api/config, /api/instance/toggle, onboarding
    arr.py                  ← /api/arr/tags, /api/arr/profiles (arr proxy endpoints)
    sweep.py                ← /api/status, /api/run-now, /api/test, /api/test-instance
    state.py                ← /api/state/*, /api/state/clear, /api/file/*, /api/exclusions*, /api/arr-link
    stats.py                ← /api/stats, /api/stats/clear, check-imports
    intel.py                ← /api/intel (full Intel payload), /api/intel/reset (Danger Zone)
    cf_scores.py            ← /api/cf-scores/status, /api/cf-scores/entries (supports ?instance_id= and
                              ?app= filters; no row cap — returns all matching entries),
                              /api/cf-scores/scan (manual sync), /api/cf-scores/reset (Reset CF Index)
    notifications.py        ← /api/notifications/test
    diagnostics.py          ← /api/diagnostic, /api/log/clear
  static/                   ← JS and CSS served as static assets
    ui-core.js              ← bootstrap, shared state, cron helper, status polling, tab switching, shared sort helpers, desktop run
    ui-instances.js         ← instances tab, instance modal, connection tests
    ui-sweep.js             ← sweep tab rendering, Run Now; refreshSweep() builds per-instance sweep cards
                              showing Library State (Cutoff Unmet, Backlog, CF Score when enabled) and
                              This Run stats (Eligible, Searched, Cooldown, Capped) rolled up across all
                              three pipelines; SWEEP_DATA_CACHE retains last known stats for disabled instances
    ui-history.js           ← history tab, exclusions, shared sort/pagination helpers; jumpHistoryPage() for direct page navigation
    ui-imports.js           ← imports/stats tab; jumpImportsPage() for direct page navigation
    ui-intel.js             ← Intel tab — fillIntel, renderIntel, resetIntel and all render helpers
    ui-cf-scores.js         ← CF Score tab — fillCfScores, cfRenderStats, cfRenderCoverage (flat list with
                              percentage pills), cfRenderTable, cfPopulateInstanceDropdown, cfFilterEntries,
                              cfFilterSearch, cfClearSearch, cfSortTable, cfPrevPage, cfNextPage, jumpCfPage,
                              cfScanLibrary (_cfWaitForScan polls and updates coverage live), cfResetIndex.
                              Titles use .arr-link with openArrLink(). No row cap — all entries returned.
    ui-settings.js          ← settings tab, tab switching, onboarding, What's New modal
    ui-notifications.js     ← notifications tab
    ui-advanced.js          ← advanced tab, danger zone, diagnostics; toggleCfScoreFeature and
                              syncCfScoreToggleLabel added for CF Score Scan feature gate
    ui-overrides.js         ← per-instance overrides tab and modal
    ui-filters.js           ← filters tab — fill, load, save, pill/list render functions
    ui-mobile-core.js              ← shared mobile helpers, mSaveCfgKeys, poll cycle, bridge functions
    ui-mobile-landscape.js         ← landscape Overrides rail/panel — lsOv* functions; panel layout matches desktop (Cooldown, Cutoff Unmet, Backlog with Backlog Sample Mode + Grace Period, Notifications); backlog fields grey when backlog is off
    ui-mobile-landscape-filters.js ← landscape Filters rail/panel — lsFilters* functions
    ui-mobile-landscape-exec.js    ← landscape Backlog and Execution tabs — ls* functions, LS_* state; backlog sample mode selects (lsSaveBacklogSampleMode), Grace Period steppers (r-grace, s-grace), Maintenance Window band (lsToggleMaint, lsSaveMaintTime, lsToggleMaintDay, lsSyncMaintUi, lsBuildMaintHint), switchToMobileView()
    ui-mobile-portrait-home.js     ← portrait Home, Instances, and Sweep tabs; mToggleAuto and mToggleMaintWindow live here
    ui-mobile-portrait-history.js  ← portrait History tab and Imports sheet
    ui-mobile-portrait-settings.js ← portrait Settings tab
    ui-mobile-portrait.js          ← portrait tab switcher, swipe gesture, mobile init block
    ui.css                         ← desktop styles
    ui-mobile.css                  ← portrait mobile styles
    ui-landscape.css               ← landscape styles
  templates/                ← HTML served by Flask render_template()
    login.html              ← login page
    setup.html              ← first-run setup page
    ui.html                 ← 61-line shell — loads CSS, includes partials, loads JS
    ui-header.html          ← header bar and status bar
    ui-nav.html             ← desktop tab navigation
    ui-tab-instances.html   ← Instances tab section
    ui-tab-sweep.html       ← Sweep tab section
    ui-tab-settings.html    ← Settings tab section
    ui-tab-filters.html     ← Filters tab section
    ui-tab-history.html     ← History tab section
    ui-tab-imports.html     ← Imports tab section
    ui-tab-intel.html       ← Intel tab section
    ui-tab-notifications.html ← Notifications tab section
    ui-tab-advanced.html    ← Advanced tab section
    ui-tab-overrides.html   ← Overrides tab section
    ui-modals.html          ← all desktop modals
    ui-mobile.html          ← entire landscape/mobile UI block
main.py                     ← entry point: signals (SIGTERM/SIGINT via threading.Event), startup ping, thread launch and join
nudgarr.py                  ← compatibility shim for source runners (deprecated)
validate.py                 ← pre-package static analysis tool
```

---

## Database

All persistence goes through the `nudgarr/db/` package. Import from it as `from nudgarr.db import ...` or `from nudgarr import db`.

The database lives at `/config/nudgarr.db` by default (controlled by the `DB_FILE` env var). Schema is defined in `_SCHEMA_SQL` in `nudgarr/db/connection.py` and applied by `init_db()`. Migrations are versioned in the `schema_migrations` table. If adding a new migration, write a new `_run_migration_vN` function in `nudgarr/db/connection.py` and call it from `init_db()`. Do not modify or remove existing migration functions — they may have already run on installed databases.

**Intel aggregate write points**

`intel_aggregate` is a protected accumulator — it must never be cleared by any normal operation (Clear History, Clear Stats, pruning). It is only reset by the explicit Reset Intel action in the Danger Zone. The aggregate is updated at three write points:

- `confirm_stat_entry()` in `db/entries.py` — snapshots turnaround, searches per import, pipeline import split (Cutoff Unmet via `entry_type="Upgraded"`, CF Score via `entry_type="CF Score"`, Backlog via all other types), quality upgrades, iteration counts, per-instance imports and turnaround, and library age bucket imported counts at the moment each import is confirmed.
- `batch_upsert_search_history()` in `db/history.py` — increments `success_total_worked` and library age bucket totals on first insert of each new item (when `search_count == 1` after the upsert).
- `reset_intel()` in `db/intel.py` — the only operation that clears both `intel_aggregate` and `exclusion_events`.

All aggregate writes happen inside the same transaction as the operation that triggers them. A rollback undoes both the primary write and the aggregate update atomically.

**Exclusion event write points**

`exclusion_events` is append-only. A row is written at every exclude and unexclude action in `db/exclusions.py`: `add_exclusion()` (manual exclude), `add_auto_exclusion()` (auto exclude), `remove_exclusion()` (manual or auto unexclude — source passed as a parameter), and `clear_auto_exclusions()` (bulk auto unexclude). The table is never modified or deleted from outside of `reset_intel()`.

| Table | Purpose |
|---|---|
| `search_history` | Every item Nudgarr has searched, with cooldown timestamps |
| `stat_entries` | Items pending import confirmation and confirmed imports |
| `quality_history` | Per-import quality upgrade records for the Imports tab tooltip |
| `exclusions` | Titles excluded from sweeps — includes source (manual/auto), search count, and acknowledged flag |
| `exclusion_events` | Append-only audit log of every exclude and unexclude action — powers Intel calibration signal |
| `intel_aggregate` | Single protected row accumulating lifetime Intel metrics — never cleared by Clear History, Clear Stats, or pruning |
| `sweep_lifetime` | Per-instance lifetime sweep stats |
| `lifetime_totals` | Lifetime confirmed import counts (movies/shows) |
| `nudgarr_state` | General key/value persistent state (e.g. last run time) |
| `schema_migrations` | Records which migrations have been applied |

---

## Import graph

Understanding what imports what avoids circular dependency issues. The rule is simple: modules lower in the list may import from modules higher up, never the reverse.

```
constants
  ├── log_setup             (imports constants only — sits alongside utils)
  └── utils
        └── db
              └── config
                    └── state
                          ├── auth
                          ├── notifications
                          └── stats
                                └── arr_clients
                                      └── sweep
                                            └── scheduler
globals  ←─ imports only constants + stdlib (Flask, threading, os)
routes/* ←─ import from globals + any module above them
main.py  ←─ imports from routes, scheduler, globals, log_setup
```

`globals.py` is the one module with a special rule: it must only import from `constants` and the Python standard library. Everything else imports `globals` to get the `app`, `STATUS`, and `RUN_LOCK` objects. Breaking this rule will create a circular import.

**Known exception — `routes/stats.py` imports from `scheduler`:** The manual import-check endpoint (`POST /api/stats/check-imports`) calls `_run_auto_exclusion_check` directly from `scheduler.py` rather than going through an intermediary. This is the only place a route file reaches up into `scheduler`. Do not add further route-to-scheduler imports without a clear reason.

---

## How a sweep works

1. `scheduler_loop` in `scheduler.py` runs on a timer (or responds to `run_requested`)
2. It calls `run_sweep(cfg, session)` in `sweep.py`
3. `run_sweep` runs the auto-unexclude pass first — any auto-excluded titles older than the configured threshold are removed from the exclusions table and their search_count reset to 0 in search_history, making them eligible immediately in this sweep
4. `run_sweep` iterates over configured Radarr and Sonarr instances in a unified loop, calling `_sweep_instance(app=...)` for each
5. Each instance helper calls `arr_clients.py` to fetch eligible items — pagination is handled internally with no item cap, callers receive a flat list of all eligible items regardless of library size. The helper then applies exclusions, tag/profile filters, and queue filtering, applies cooldown logic from `stats.py`, calls the search API, then records results in a single batched transaction via `nudgarr/db/` — `batch_upsert_search_history` and `batch_upsert_stat_entries` commit the entire batch at once rather than per-item
6. `run_sweep` returns a summary dict
7. `scheduler_loop` stores the summary in `STATUS["last_summary"]`, persists `last_run_utc` to `nudgarr_state`, triggers notifications, and runs import checks
8. A separate `import_check_loop` thread runs independently on its own timer, polling for confirmed imports without waiting for a sweep. After each import check cycle it also runs the auto-exclusion evaluation — titles that meet the configured threshold, have no confirmed import, are not in the download queue, and are not already excluded are written to the exclusions table and a notification fires

---

## How a request works

1. `main.py` calls `register_blueprints()` which registers all 7 route blueprints with the Flask app
2. A request arrives at one of the 31 endpoints
3. The `@requires_auth` decorator in `auth.py` checks session validity and runs a CSRF origin check on POST requests before the handler runs
4. The handler reads/writes state via `nudgarr/db/` and `state.py`, config via `config.py`, and updates `STATUS` in `globals.py`
5. Flask serialises the response as JSON (most endpoints) or renders a template

---

## Running locally (without Docker)

**Requirements:** Python 3.12+, pip

**Shutdown:** Nudgarr handles SIGTERM and SIGINT cleanly via a `threading.Event`. On `docker stop`, any in-progress sweep is allowed to finish before the process exits. A new sweep cycle will not start after the signal is received.

```bash
# Install dependencies (includes Waitress)
pip install -r requirements.txt

# Run
python main.py
```

The app will start on port 8085 by default. The database and config are written to `/config/` — you can override with environment variables:

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
3. Read the value via `cfg.get("your_key", default)` wherever it's used

If the key accepts a fixed set of string values, define the allowed values as a tuple constant in `constants.py` (see `VALID_SAMPLE_MODES` for the pattern) and import it in both `config.py` and wherever the value is consumed. This ensures validation and consumption stay in sync.

**Frontend wiring (if the key is exposed in the Settings or Advanced tab):**

The config arrives in the browser via `/api/config` and is stored in the global `CFG` object (populated by `loadAll()` in `ui-core.js`). Your new key will be present in `CFG` automatically — no changes to `ui-core.js` are needed. What you do need to wire up:

4. **HTML control** — add the input element to the relevant tab partial under `nudgarr/templates/`. Give it an `id` that matches what the JS will reference.
5. **Fill function** — in the corresponding `ui-*.js` file, find the `fill*()` function for that tab and add: `el('my_new_key').value = CFG.my_new_key;`
6. **Save function** — in the same JS file, find the `save*()` function and add: `CFG.my_new_key = el('my_new_key').value;` before the `POST /api/config` call.

### Adding a new API endpoint

1. Decide which blueprint it belongs to (or create a new one under `routes/`)
2. Add the route handler to that blueprint file
3. Apply the `@requires_auth` decorator from `nudgarr.auth` to every handler that requires an authenticated session — which is every endpoint except `/login`, `/setup`, and the `POST /api/auth/*` and `POST /api/setup` endpoints. Omitting it leaves the endpoint completely unauthenticated. `validate.py` does not catch this omission. The decorator also runs a CSRF origin check on every POST, so you do not need to add that separately.
4. If it's a new blueprint, register it in `routes/__init__.py`

If your endpoint returns any part of the config (including individual instance fields), use `_mask_config()` from `routes/config.py` to strip API keys before serialising the response. Sending a raw config dict to the browser exposes real API keys in transit.

### Changing sweep behaviour

The sweep logic lives entirely in `sweep.py`. `_sweep_instance` is the shared per-instance worker — most sweep changes happen there. It accepts an `app` parameter (`"radarr"` or `"sonarr"`) and handles all per-app differences internally via conditional blocks. `run_sweep` is the orchestrator and handles pruning, exclusions, and summary building.

**Backlog (missing) pipeline filters**

The missing search pipeline applies filters in this order before handing items to `pick_items_with_cooldown`:

1. Excluded titles filter — items matching `excluded_titles` are dropped
2. Queue filter — items already actively downloading are skipped
3. `minimumAvailability` filter — Radarr items not yet past their availability status are dropped
4. Age filter — Radarr only; items added within `missing_added_days` days are dropped
5. Grace period filter — items whose release date (see `_release_date()`) falls within the configured `missing_grace_hours` window are skipped with a debug log

`_release_date(rec)` is a helper that returns the earliest known release date for a record, checking `releaseDate`, `physicalRelease`, `digitalRelease`, `inCinemas`, `airDateUtc`, `airDate` in that order. If no date is found it returns `None` (treated as past the grace window). If you add a new date field to the API response, add it to this helper's field list.

**`pick_items_with_cooldown` and max_per_run**

`pick_items_with_cooldown` in `stats.py` applies the cooldown filter, sorts by sample mode, and caps the result. `max_per_run=0` means all eligible items are returned — it does not disable the pipeline. The guard in `_sweep_instance` is `if backlog_enabled:` (not `if backlog_enabled and missing_max > 0:`) — backlog runs when max is 0 and relies on `pick_items_with_cooldown` to return the full eligible pool.

### Changing database schema

1. Add new columns or tables to `_SCHEMA_SQL` in `nudgarr/db/connection.py` for fresh installs
2. Write a new `_run_migration_vN` function in `nudgarr/db/connection.py` that applies the change to existing databases
3. Call it from `init_db()` in `nudgarr/db/connection.py` in the migration chain
4. Never modify existing migration functions — they may have already run on user databases

### Changing the UI

The frontend is a multi-file static app — no build step required. `nudgarr/templates/ui.html` is a thin shell that loads CSS, includes template partials via Jinja2 `{% include %}`, and loads JS. Each tab section, the header, nav, modals, and the mobile/landscape block live in their own partial file under `nudgarr/templates/`. The JS files are split by domain (see project structure above). All files are plain vanilla JavaScript and CSS.

All static file URLs in `ui.html` include `?v={{ VERSION }}` via Flask's `url_for` keyword argument (e.g. `url_for('static', filename='ui-core.js', v=VERSION)`). This means browsers automatically fetch fresh files on version bump without a hard reload. If you add a new static file, follow this pattern — do not use bare string URLs.

The desktop UI renders on screens 500px and wider. The mobile UI renders on screens under 500px and is a separate layout split across `ui-mobile-core.js`, `ui-mobile-portrait.js`, and `ui-mobile-landscape.js`. Mobile functions are prefixed with `m` (e.g. `mHaptic`, `mSheetOpen`) to avoid collisions with desktop functions.

**Portrait Settings tab steppers**

Settings steppers are driven by four parallel state objects in `ui-mobile-portrait-settings.js`: `M_S_VALS` (current values), `M_S_MINS` (floor per key), `M_S_CFG_KEYS` (maps UI key to CFG field name), and `M_S_HOLD_INCS` (hold-to-accelerate increment). To add a new stepper: add the key to all four objects, add the corresponding HTML in `ui.html` with `id="m-sv-{key}"` on the value element, and add `mSHoldStart`/`mSHoldEnd` handlers on the buttons. `mSSave` automatically includes all keys in `M_S_CFG_KEYS` on the next debounced save — no further wiring needed.

**Threshold/dependent stepper pairs**

Some steppers have a dependency relationship — when a threshold is 0 (feature disabled), a paired unexclude or secondary stepper should grey out. This is handled by `M_S_THRESHOLD_KEYS` (maps threshold key to the ID of its dependent row) and `mSyncAutoExclUi(key)`. `mSStep` calls `mSyncAutoExclUi` automatically whenever a threshold key changes, so the grey state stays live. `mPopulateSettings` also calls it on load. If you add a new threshold/dependent pair, add the mapping to `M_S_THRESHOLD_KEYS` and give the dependent row a stable `id` in `ui.html` — no other changes needed.

**Mobile poll cycle**

`mPollCycle` in `ui-mobile-core.js` runs every 5s. It fetches `/api/status`, updates the home screen, checks the version banner, and refreshes the sweep tab if active. It also calls `mRefreshMobileAutoExclBadge()` on every cycle so the History nav badge stays in sync with the backend without requiring a page reload. If you add a feature that needs periodic refresh on mobile, add it here rather than creating a separate interval.

**Mobile modals**

Mobile confirmation dialogs use the `m-sheet-backdrop` + `m-sheet m-sheet-auto` pattern with `border-radius:20px;margin:16px` inline. Content goes in a `padding:20px 18px 0` div. Buttons go in a `padding:0 18px 20px;margin-top:16px` div. For single-action modals (informational) use the base `m-modal-btn` class (blue). For two-button choice modals use `m-modal-btn-neutral` (Cancel/secondary) and `m-modal-btn-danger` (destructive action) side by side with `display:flex;gap:8px`. Show by setting `display:flex` and adding `m-visible`; hide by removing `m-visible` and setting `display:none` after the 300ms CSS transition.

When adding new HTML elements that are referenced by `el('some-id')` in JS, make sure the `id` attribute exists in the relevant template partial. The `validate.py` tool and CI element ID check will catch mismatches.

### Adding a new desktop tab

Six places must all be touched in concert. Missing any one will produce either a tab that never appears, a JS syntax error, or a validate.py/test failure.

1. **Template partial** — create `nudgarr/templates/ui-tab-{name}.html`
2. **Include in shell** — add `{% include "ui-tab-{name}.html" %}` to `ui.html`
3. **Nav entry** — add the tab `<div>` to `ui-nav.html` with `data-tab="{name}"` and `onclick="showTab('{name}')"`. The `showTab()` wiring in `ui-settings.js` handles everything else automatically.
4. **JS file** — create `nudgarr/static/ui-{name}.js` and add a `<script>` tag to `ui.html` in load order. Declare a `fill{Name}()` function — it will be called by `_onTabShown` in `ui-settings.js` when the tab is opened.
5. **Update validate.py and tests** — add the filename to `EXPECTED_STATIC_FILES` in `validate.py`, and to `JS_LOAD_ORDER` and `LINE_COUNT_CEILINGS` in `tests/test_frontend_structure.py`. The check count in `EXPECTED_CHECK_COUNT` will also need updating.
6. **Backend route (if needed)** — follow the Adding a new API endpoint guide above.

### Changing authentication

Auth logic — hashing, lockout, session checks, the `@requires_auth` decorator — is in `nudgarr/auth.py`. The decorator also runs `_csrf_origin_ok()` on every POST request, which validates the Origin or Referer header to reject cross-origin requests. Session cookie settings (HttpOnly, SameSite) are in `nudgarr/globals.py`.

The session secret key is managed by `_load_or_create_secret_key()` in `nudgarr/globals.py`. It checks for a `SECRET_KEY` env var first, then reads or creates `/config/nudgarr-secret.key` for persistence across restarts. Avoid moving this logic outside `globals.py` — it must run before any route is registered.

### Adding logging to a new module

Every operational module declares a module-level logger at the top of the file:

```python
import logging
logger = logging.getLogger(__name__)
```

The `nudgarr` root logger is configured by `log_setup.py` at startup — child loggers inherit its level and handlers automatically. Use `logger.debug` for per-item detail (cooldown skips, queue skips, quality fetches), `logger.info` for lifecycle events (sweep start/complete, import confirmed), `logger.warning` for recoverable issues, and `logger.exception` inside except blocks to capture the full traceback. `validate.py` enforces that every operational file has a logger — new files without one will fail the Logging Adoption check.

---

## Validation

Run `validate.py` before packaging to catch structural issues early:

```bash
python3 validate.py
```

Run the structural test suite to verify file ownership, load order, shared state, and split integrity:

```bash
pytest tests/test_frontend_structure.py -v
```

The test suite must pass at exactly the expected check count. If you add or remove files, functions, or validate.py checks, update `EXPECTED_CHECK_COUNT` and `LINE_COUNT_CEILINGS` in `tests/test_frontend_structure.py` accordingly.

The current expected check count is **327** (defined at the top of `tests/test_frontend_structure.py`). If validate.py gains or loses checks — which happens when you add new static files, new route files, or new required element IDs — update this constant or the test will fail with a count mismatch even though validate.py itself passes.

`LINE_COUNT_CEILINGS` in `tests/test_frontend_structure.py` sets a per-file line ceiling for every JS file. If you add code to an existing file and push it over its ceiling, the structural test will fail. Raise the ceiling deliberately in the same commit rather than working around it.

This checks:

| Check | What it does |
|---|---|
| Packaging Hygiene | Cleans and verifies no `__pycache__` dirs or bytecode files are present |
| Python Syntax | `py_compile` on every `.py` file |
| Stub Function Detection | AST check — flags docstring-only, pass-only, and annotated-return stubs |
| Database Connection Integrity | Flags db functions using `conn.` without `get_connection()`, or `conn.commit()` without `conn.execute()` |
| Static Files | All expected JS and CSS files present and linked in `ui.html` |
| HTML Structure | Div balance, duplicate IDs, wrap/mobile-ui nesting |
| Key Mobile Elements | Confirms required mobile elements and nav items exist |
| JavaScript Sanity | Required functions present, onclick references defined, element IDs matched |
| API Endpoint Cross-check | Every `api('/api/...')` call in the UI has a matching backend route |
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
| JS syntax | Runs `node --check` on every `.js` file in `nudgarr/static/` |
| Element ID consistency | Verifies every `el('id')` call across all JS files has a matching `id` attribute in any template partial |

Run them locally before pushing:

```bash
# Syntax
for f in main.py nudgarr/*.py nudgarr/routes/*.py nudgarr/db/*.py; do python -m py_compile "$f"; done

# Lint
pip install flake8
flake8 main.py nudgarr/ --max-line-length=120 --ignore=E501,W503

# JS (requires Node.js)
for f in nudgarr/static/*.js; do node --check "$f" && echo "OK: $f"; done

# Element ID consistency
python3 validate.py
```

---

## Forking for additional arr support

Nudgarr intentionally supports only Radarr and Sonarr. If you want to add Readarr, Lidarr, or another arr, the changes are contained:

- **API calls:** add a new section to `arr_clients.py` following the existing Radarr/Sonarr pattern
- **Sweep:** extend `_sweep_instance` in `sweep.py` to handle the new app — add its callables to the `if app == ...` block at the top of the function and add any app-specific pipeline differences as conditional blocks. Add the new app to the `run_sweep` loop.
- **Database:** the schema is keyed by app name — adding a new app type flows through automatically
- **UI:** the instance cards, sweep cards, and history filters are all data-driven — adding a new app type flows through automatically once the backend returns data for it
- **Overrides tab:** `renderOverridesCards()` in `ui-overrides.js` uses `.ov-divider:first-child { margin-top: 0 }` to remove top margin from the first divider. This assumes the loop order `['radarr', 'sonarr']` always places Radarr first. If a third app is added, replace the `:first-child` rule with an explicit `.ov-divider-first` class applied in `renderOverridesCards()` when building the first divider.

---

## Questions

Check the [wiki](https://github.com/MMagTech/nudgarr/wiki) first — setup, settings, and common questions are covered there. For anything not answered, open an issue on GitHub. If you're working on something larger, it's worth discussing the approach before building it.


# Contributing to Nudgarr

Thanks for your interest in contributing. This document covers the project structure, how the pieces connect, how to run locally, and where to make common types of changes.

Nudgarr is a lightweight project — the goal is to keep it that way. If you're considering a larger change, opening an issue to discuss it first is always appreciated.

---

## Project structure

As of v3.1.0, Nudgarr uses a SQLite database for all persistence via `db.py`.

```
nudgarr/                    ← Python package
  __init__.py               ← package metadata, exposes __version__
  constants.py              ← VERSION, file paths, DEFAULT_CONFIG
  utils.py                  ← shared helpers: time, file I/O, HTTP, URL validation, jitter
  config.py                 ← load, validate, and deep-copy config
  db.py                     ← SQLite persistence layer: schema, migrations, all read/write ops
  state.py                  ← exclusions and history helpers built on top of db.py
  auth.py                   ← password hashing, lockout, session checks
  notifications.py          ← Apprise wrappers (sweep complete, import, error)
  arr_clients.py            ← Radarr and Sonarr API calls
  stats.py                  ← import tracking, cooldown logic, stat recording
  globals.py                ← Flask app instance, STATUS dict, RUN_LOCK, security headers, persistent secret key
  sweep.py                  ← run_sweep orchestrator + per-instance helpers
  scheduler.py              ← scheduler loop, import check loop, banner, Flask server starter
  routes/                   ← Flask blueprints (one file per domain)
    __init__.py             ← register_blueprints() — called once from main.py
    auth.py                 ← /, /login, /setup, /api/auth/*, /api/setup
    config.py               ← /api/config, /api/instance/toggle, onboarding
    sweep.py                ← /api/status, /api/run-now, /api/test, /api/test-instance
    state.py                ← /api/state/*, /api/file/*, /api/exclusions*
    stats.py                ← /api/stats, /api/stats/clear, check-imports
    notifications.py        ← /api/notifications/test
    diagnostics.py          ← /api/diagnostic
  templates/                ← HTML served by Flask render_template()
    login.html              ← login page
    setup.html              ← first-run setup page
    ui.html                 ← main single-page application (~3500 lines)
main.py                     ← entry point: signals, startup ping, thread launch
nudgarr.py                  ← compatibility shim for source runners (deprecated)
validate.py                 ← pre-package static analysis tool
```

---

## Database

All persistence goes through `db.py`. There are no JSON state files in v3.1.0 — on first start after upgrading from an older version, existing JSON files are migrated automatically.

The database lives at `/config/nudgarr.db` by default (controlled by the `DB_FILE` env var). Schema is defined in `_SCHEMA_SQL` and created by `_create_schema()`. Migrations are versioned in the `schema_migrations` table — do not modify existing migration functions, only add new ones.

Key tables:

| Table | Purpose |
|---|---|
| `search_history` | Every item Nudgarr has searched, with cooldown timestamps |
| `stat_entries` | Items pending import confirmation and confirmed imports |
| `exclusions` | Titles excluded from sweeps |
| `sweep_lifetime` | Per-instance lifetime sweep stats |
| `lifetime_totals` | Lifetime confirmed import counts (movies/shows) |
| `nudgarr_state` | General key/value persistent state (e.g. last run time) |
| `schema_migrations` | Records which migrations have been applied |

---

## Import graph

Understanding what imports what avoids circular dependency issues. The rule is simple: modules lower in the list may import from modules higher up, never the reverse.

```
constants
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
main.py  ←─ imports from routes, scheduler, globals
```

`globals.py` is the one module with a special rule: it must only import from `constants` and the Python standard library. Everything else imports `globals` to get the `app`, `STATUS`, and `RUN_LOCK` objects. Breaking this rule will create a circular import.

---

## How a sweep works

1. `scheduler_loop` in `scheduler.py` runs on a timer (or responds to `run_requested`)
2. It calls `run_sweep(cfg, session)` in `sweep.py`
3. `run_sweep` iterates over configured instances, calling `_sweep_radarr_instance` or `_sweep_sonarr_instance` for each
4. Each instance helper calls `arr_clients.py` to fetch eligible items, applies cooldown logic from `stats.py`, calls the search API, then records results via `db.py`
5. `run_sweep` returns a summary dict
6. `scheduler_loop` stores the summary in `STATUS["last_summary"]`, persists `last_run_utc` to `nudgarr_state`, triggers notifications, and runs import checks
7. A separate `import_check_loop` thread runs independently on its own timer, polling for confirmed imports without waiting for a sweep

---

## How a request works

1. `main.py` calls `register_blueprints()` which registers all 7 route blueprints with the Flask app
2. A request arrives at one of the 31 endpoints
3. The `@requires_auth` decorator in `auth.py` checks session validity and runs a CSRF origin check on POST requests before the handler runs
4. The handler reads/writes state via `db.py` and `state.py`, config via `config.py`, and updates `STATUS` in `globals.py`
5. Flask serialises the response as JSON (most endpoints) or renders a template

---

## Running locally (without Docker)

**Requirements:** Python 3.12+, pip

```bash
# Install dependencies
pip install flask requests apprise

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

### Adding a new API endpoint

1. Decide which blueprint it belongs to (or create a new one under `routes/`)
2. Add the route handler to that blueprint file
3. If it's a new blueprint, register it in `routes/__init__.py`

### Changing sweep behaviour

The sweep logic lives entirely in `sweep.py`. `_sweep_radarr_instance` and `_sweep_sonarr_instance` are the per-instance workers — most sweep changes happen there. `run_sweep` is the orchestrator and handles pruning, exclusions, and summary building.

### Changing database schema

1. Add new columns or tables to `_SCHEMA_SQL` in `db.py` for fresh installs
2. Write a new `_run_migration_vN` function that applies the change to existing databases
3. Call it from `init_db()` in the migration chain
4. Never modify existing migration functions — they may have already run on user databases

### Changing the UI

The frontend is a single-page app in `nudgarr/templates/ui.html`. It's plain HTML, CSS, and vanilla JavaScript — no build step required. The JS communicates with the backend exclusively via the REST API endpoints.

The file has two distinct UI sections. The desktop UI renders on screens 500px and wider. The mobile UI — marked with `<!-- MOBILE UI -->` — renders on screens under 500px and is a separate layout with its own HTML, CSS, and JS functions. Mobile functions are prefixed with `m` (e.g. `mHaptic`, `mSheetOpen`) to avoid collisions with desktop functions.

When adding new HTML elements that are referenced by `el('some-id')` in JS, make sure the `id` attribute exists in the HTML. The `validate.py` tool will catch mismatches.

### Changing authentication

Auth logic — hashing, lockout, session checks, the `@requires_auth` decorator — is in `nudgarr/auth.py`. The decorator also runs `_csrf_origin_ok()` on every POST request, which validates the Origin or Referer header to reject cross-origin requests. Session cookie settings (HttpOnly, SameSite) are in `nudgarr/globals.py`.

The session secret key is managed by `_load_or_create_secret_key()` in `nudgarr/globals.py`. It checks for a `SECRET_KEY` env var first, then reads or creates `/config/nudgarr-secret.key` for persistence across restarts. Avoid moving this logic outside `globals.py` — it must run before any route is registered.

---

## Validation

Run `validate.py` before packaging to catch structural issues early:

```bash
python3 validate.py
```

This checks:

| Check | What it does |
|---|---|
| HTML structure | Div balance, duplicate IDs, wrap/mobile-ui nesting |
| Key mobile elements | Confirms required mobile elements and nav items exist |
| JavaScript sanity | Required functions present, onclick references defined, element IDs matched |
| API endpoint cross-check | Every `api('/api/...')` call in the UI has a matching backend route |
| Version consistency | `constants.py` VERSION matches the latest entry in `CHANGELOG.md` |
| Database integrity | Required tables, functions, and migration versions present in `db.py` |
| Routes registration | All blueprint modules registered in `routes/__init__.py` |

---

## CI checks

The CI workflow (`.github/workflows/ci.yml`) runs four checks on every push:

| Check | What it does |
|---|---|
| Python syntax | `py_compile` on every `.py` file |
| Flake8 lint | Style and import checks, max line length 120 |
| JS syntax | Extracts the `<script>` block from `ui.html` and runs `node --check` |
| Element ID consistency | Verifies every `el('id')` call in `ui.html` has a matching `id` attribute |

Run them locally before pushing:

```bash
# Syntax
for f in main.py nudgarr/*.py nudgarr/routes/*.py; do python -m py_compile "$f"; done

# Lint
pip install flake8
flake8 main.py nudgarr/ --max-line-length=120 --ignore=E122,E226,E231,E302,E303,E305,E306,E402,E501,W503

# JS (requires Node.js)
python3 -c "
import re
html = open('nudgarr/templates/ui.html').read()
m = re.search(r'<script>(.*?)</script>', html, re.DOTALL)
open('/tmp/check.js', 'w').write(m.group(1))
"
node --check /tmp/check.js
```

---

## Forking for additional arr support

Nudgarr intentionally supports only Radarr and Sonarr. If you want to add Readarr, Lidarr, or another arr, the changes are contained:

- **API calls:** add a new section to `arr_clients.py` following the existing Radarr/Sonarr pattern
- **Sweep:** add a `_sweep_<app>_instance` function in `sweep.py` and call it from `run_sweep`
- **Database:** the schema is keyed by app name — adding a new app type flows through automatically
- **UI:** the instance cards, sweep cards, and history filters are all data-driven — adding a new app type flows through automatically once the backend returns data for it

---

## Questions

Check the [wiki](https://github.com/MMagTech/nudgarr/wiki) first — setup, settings, and common questions are covered there. For anything not answered, open an issue on GitHub. If you're working on something larger, it's worth discussing the approach before building it.


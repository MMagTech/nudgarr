# Contributing to Nudgarr

Thanks for your interest in contributing. This document covers the project structure, how the pieces connect, how to run locally, and where to make common types of changes.

Nudgarr is a lightweight project — the goal is to keep it that way. If you're considering a larger change, opening an issue to discuss it first is always appreciated.

---

## Project structure

As of v2.8.0, Nudgarr is organised as a Python package rather than a single file.

```
nudgarr/                    ← Python package
  __init__.py               ← package metadata, exposes __version__
  constants.py              ← VERSION, file paths, DEFAULT_CONFIG
  utils.py                  ← shared helpers: time, file I/O, HTTP, URL validation, jitter
  config.py                 ← load, validate, and deep-copy config
  state.py                  ← state/stats/exclusions persistence
  auth.py                   ← password hashing, lockout, session checks
  notifications.py          ← Apprise wrappers (sweep complete, import, error)
  arr_clients.py            ← Radarr and Sonarr API calls
  stats.py                  ← import tracking, cooldown logic, stat recording
  globals.py                ← Flask app instance, STATUS dict, RUN_LOCK, security headers, persistent secret key
  sweep.py                  ← run_sweep orchestrator + per-instance helpers
  scheduler.py              ← scheduler loop, banner, Flask server starter
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
    ui.html                 ← main single-page application (~3200 lines)
main.py                     ← entry point: signals, startup ping, thread launch
nudgarr.py                  ← compatibility shim for source runners (deprecated)
```

---

## Import graph

Understanding what imports what avoids circular dependency issues. The rule is simple: modules lower in the list may import from modules higher up, never the reverse.

```
constants
  └── utils
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
2. It calls `run_sweep(cfg, state, session)` in `sweep.py`
3. `run_sweep` iterates over configured instances, calling `_sweep_radarr_instance` or `_sweep_sonarr_instance` for each
4. Each instance helper calls `arr_clients.py` to fetch eligible items, applies cooldown logic from `stats.py`, calls the search API, then records results
5. `run_sweep` saves state and returns a summary dict
6. `scheduler_loop` stores the summary in `STATUS["last_summary"]`, triggers notifications, and runs import checks

---

## How a request works

1. `main.py` calls `register_blueprints()` which registers all 7 route blueprints with the Flask app
2. A request arrives at one of the 31 endpoints
3. The `@requires_auth` decorator in `auth.py` checks session validity and runs a CSRF origin check on POST requests before the handler runs
4. The handler reads/writes state via `state.py`, config via `config.py`, and updates `STATUS` in `globals.py`
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

The app will start on port 8085 by default. Config and state files are written to `/config/` — you can override the paths with environment variables:

```bash
export CONFIG_FILE=./config/nudgarr-config.json
export STATE_FILE=./config/nudgarr-state.json
export STATS_FILE=./config/nudgarr-stats.json
export EXCLUSIONS_FILE=./config/nudgarr-exclusions.json
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

The sweep logic lives entirely in `sweep.py`. `_sweep_radarr_instance` and `_sweep_sonarr_instance` are the per-instance workers — most sweep changes happen there. `run_sweep` is the orchestrator and handles pruning, exclusions, and state persistence.

### Changing the UI

The frontend is a single-page app in `nudgarr/templates/ui.html`. It's plain HTML, CSS, and vanilla JavaScript — no build step required. The JS communicates with the backend exclusively via the REST API endpoints.

The file has two distinct UI sections. The desktop UI renders on screens 500px and wider. The mobile UI — marked with `<!-- MOBILE UI -->` — renders on screens under 500px and is a separate layout with its own HTML, CSS, and JS functions. Mobile functions are prefixed with `m` (e.g. `mHaptic`, `mSheetOpen`) to avoid collisions with desktop functions.

When adding new HTML elements that are referenced by `el('some-id')` in JS, make sure the `id` attribute exists in the HTML. The CI check will catch mismatches.

### Changing authentication

Auth logic — hashing, lockout, session checks, the `@requires_auth` decorator — is in `nudgarr/auth.py`. The decorator also runs `_csrf_origin_ok()` on every POST request, which validates the Origin or Referer header to reject cross-origin requests. Session cookie settings (HttpOnly) are in `nudgarr/globals.py`.

The session secret key is managed by `_load_or_create_secret_key()` in `nudgarr/globals.py`. It checks for a `SECRET_KEY` env var first, then reads or creates `/config/nudgarr-secret.key` for persistence across restarts. Avoid moving this logic outside `globals.py` — it must run before any route is registered.

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
- **State:** the state structure is keyed by app name — adding a new key (e.g. `"readarr"`) works without schema changes
- **UI:** the instance cards, sweep cards, and history filters are all data-driven — adding a new app type flows through automatically once the backend returns data for it

---

## Questions

Open an issue on GitHub. If you're working on something larger, it's worth discussing the approach before building it.

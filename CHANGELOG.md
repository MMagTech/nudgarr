# Changelog

All notable changes to Nudgarr are documented here.

---

## v2.9.0

**Security hardening**
- H1: API keys masked in `GET /api/config` response — last 4 characters shown as `••••••••XXXX`. Full key only travels client → server on save. Frontend handles masked keys gracefully — editing an existing instance without changing the key preserves the original.
- H2: URL validation added to Test Connections (`/api/test`) and notification test (`/api/notifications/test`) endpoints — blocks link-local addresses (169.254.x.x) to prevent metadata endpoint probing.
- H3: Origin/Referer header validation on all authenticated POST routes — cross-origin POSTs from third-party pages are rejected with 403. Same-host and headerless (curl/CLI) requests are unaffected.
- L1: Security response headers added via `after_request` hook — `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy: strict-origin-when-cross-origin`.
- M1: Secret key now persisted to `/config/nudgarr-secret.key` on first start — sessions survive container restarts without requiring `SECRET_KEY` env var. Falls back to ephemeral key if config directory is not writable.
- L2: Raw exception strings removed from API error responses — generic messages returned to client, full detail logged server-side.

**Instance modal improvements**
- API Key label updated dynamically — shows `API Key (Masked After Save)` when adding a new instance, `API Key (Masked)` when editing an existing one
- Connection test on modal save now fires against in-memory values rather than disk — a bad key goes red immediately without needing to hit Save Changes first
- New `POST /api/test-instance` endpoint accepts caller-supplied instance data directly; resolves masked keys against stored config before testing

---

## v2.8.0

**Internal restructure — package layout (no behaviour changes)**
- `nudgarr.py` split into a proper Python package under `nudgarr/`
- Modules: `constants`, `utils`, `config`, `state`, `auth`, `notifications`, `arr_clients`, `stats`, `globals`, `sweep`, `scheduler`
- Flask routes split into 7 blueprints under `nudgarr/routes/`
- HTML templates extracted to real files under `nudgarr/templates/` — served via `render_template()` instead of inline Python strings
- Entry point is now `main.py` — `nudgarr.py` retained as a deprecation shim for source runners
- CI updated — syntax check, flake8, JS check, and element ID check all target the new structure
- Docker users: no changes required — image behaviour is identical
- Source runners: update start command from `python nudgarr.py` to `python main.py`

---

## v2.7.0

**Sweep tab**
- Dedicated Sweep tab between Instances and Settings
- Per-instance cards showing Sweep Mode and Last Run time independently
- Library State section — Cutoff Unmet and Backfill counts reflecting current library state
- This Run section — Eligible, On Cooldown, Capped, and Searched counts from the last sweep
- Disabled instances retain last known stats and show a Disabled pill — dimmed but not blank
- Tooltip on Radarr and Sonarr headings explains each stat with tuning guidance
- Cache persists last known stats across sweeps for disabled instances

**Exclusion list**
- ⊘ icon appears on History rows on hover — clicking adds the title to `nudgarr-exclusions.json`
- Exclusions filter pill appears in History only when exclusions exist
- Selecting the filter shows excluded items only — icon becomes Unexclude action for that row
- Excluded items remain visible in History as a log of past searches

**Onboarding**
- Expanded from 8 to 10 steps
- Step 8 — Reading Your Sweep Stats — covers Library State and This Run with tuning guidance
- Informational note added: gradual tuning recommended, Nudgarr has no visibility into indexer limits
- Replay Walkthrough button added to Advanced → UI Preferences

**Security**
- `SESSION_COOKIE_HTTPONLY=True` explicitly set — confirms Flask default, prevents JS cookie access
- `SESSION_COOKIE_SAMESITE` not set — Nudgarr is LAN-only, HTTPS is not planned; `SameSite=Lax` breaks POST requests through reverse proxies (Unraid, Synology)

---

## v2.6.0

**Per-instance enable/disable**
- Disable/Enable toggle on each instance card — live update, no save required
- Disabled instances skipped entirely in sweep, Test Connections, and startup health ping
- Health dot goes grey when disabled; re-enabling triggers an immediate background ping
- Card content dims when disabled — Enable button stays full opacity as the primary action
- Toggle surgically updates only the affected card — sibling instance dots unaffected

**Per-arr sample mode**
- `radarr_sample_mode` and `sonarr_sample_mode` replace the single `sample_mode` key
- Legacy `sample_mode` still accepted — used as fallback for both if per-arr keys not set
- Newest Added warning checks `radarr_sample_mode` independently of Sonarr
- Settings → Search Behaviour restructured — Cooldown solo at top, Max Movies + Radarr Sample Mode paired, Max Episodes + Sonarr Sample Mode paired

**Library Added column in History**
- `library_added` field stored in state on each search — populated from Radarr/Sonarr `added` field
- New sortable column in History between Type and Last Searched
- Persists across searches — preserves value if `added` not returned on subsequent searches

**Search Count in History**
- `search_count` incremented in state on each search — survives cooldown resets
- Displayed as a pill in History (×2, ×3…), hidden when count is 1
- Sortable column — useful for finding items searched many times with no import

**Instance column in History**
- Instance name returned from `api/state/items` and shown as a dedicated sortable column

**Backup All**
- Replaces individual Download Config and Download History buttons in Support & Diagnostics
- Single button downloads a zip containing config, state, and stats JSON files
- Danger Zone confirm dialogs now reference Backup All and suggest using it beforehand

**UI polish**
- Donate pill moved from tab bar into header alongside Sign Out — visible from all tabs
- Instance card restructured into two rows — name/URL on top, buttons on bottom
- Indexer limits card retitled to ⚠️ INDEXER RATE LIMITS with updated body copy

---

## v2.5.0

**Sample modes**
- Four sample modes — Random, Alphabetical, Oldest Added, Newest Added
- `added` date extracted from Radarr and Sonarr Cutoff Unmet and Missing endpoints to support sort modes
- Newest Added warning — amber notice on Settings and Advanced tabs when Newest Added is selected with backlog enabled and Missing Added Days > 0
- Warning fades on save only, not on appear

**UI**
- What's New modal — shown once per version upgrade, never on fresh install
- Stats tab — Lifetime Confirmed pill above Movies and Shows cards
- Support link pill (🍺 Donate) in header — toggleable in Advanced → UI Preferences
- Onboarding updated — all four sample modes described in step 3

**Startup**
- Last Run persisted to state file — populates immediately on restart
- Next Run calculated from config on startup — no waiting for first scheduler cycle
- Instance health dots pulse amber immediately on page load via parallel background ping — resolves within ~1 second

**Bug fixes**
- Visual hierarchy corrected — section headers (13px/600) now outrank field labels (12px/500) and help text (12px/400)
- Tooltip text weight fixed — was inheriting bold from parent
- Sample mode tooltip widened to 360px — was riding off screen
- Newest Added warning gap fixed — `visible` class now removed after fade so no empty space remains
- Newest Added warning condition fixed — was checking `missing_max` instead of `missing_added_days`
- Test connection amber pulse fixed — was resolving too fast
- Test connection error fixed — was showing raw Python exception instead of friendly message
- Danger zone buttons consolidated to one row
- Clear History no longer shows second OK popup after confirm — clears quietly like Clear Stats
- Stats tab Movies card colour fixed — was green, now matches Shows (purple)
- Stats tab number sizing fixed — was 20px, now 15px
- Support pill sizing fixed — now matches tab padding
- Save button spacing fixed across Notifications and Settings tabs
- History KPI pill numbers — weight reduced to 400, size relationship between label and number corrected
- Import Check help text shortened to one line
- Settings second field row excess margin removed

---

## v2.4.0

- Title search on History and Stats tabs — inline with filters, ✕ to clear, resets on tab switch
- Pagination memory — page size shared across History and Stats for the session
- Data Retention — renamed from History Size; stats entries pruned alongside history on each sweep, lifetime totals unaffected
- Retry logic — one retry per instance per sweep with 15 second wait, marks bad and moves on
- Instance error notifications — fires per failed instance with friendly unreachable message
- Error notification fix — now correctly fires on individual instance failures
- Max Per Run labels updated to Per Instance throughout Settings and Advanced

---

## v2.3.0

- Apprise notifications — sweep complete, import confirmed, and error triggers
- Universal docker-compose with `.env` support
- PUID/PGID startup fix — graceful chown fallback, cap_add CHOWN/SETUID/SETGID
- Open Issue button added to Diagnostics
- apk upgrade at build time for latest Alpine security patches

---

## v2.2.0

- First-run onboarding walkthrough — 8-step guided setup for new users
- Safe defaults — scheduler off, max per run 1, batch size 1 on fresh installs
- Password hashing upgraded to PBKDF2-HMAC-SHA256 with unique random salt, replacing unsalted SHA256
- Existing passwords migrate automatically on next successful login — no action required
- Progressive brute force lockout — 3 failures → 30s, 6 → 5min, 10 → 30min, 15+ → 1hr
- Login countdown timer — button disables and counts down during lockout
- PUID/PGID support — container runs as specified UID/GID
- Lifetime Movies/Shows import totals persist through Clear Stats
- Clear Stats backend endpoint fixed
- Advanced tab reordered — History → Stats → Security

---

## v2.1.2

- Lifetime Movies/Shows import totals — persist through Clear Stats, seeded from existing confirmed entries on first run after upgrade
- Clear Stats backend endpoint fixed — was missing entirely
- Save transition fixed — Unsaved Changes → Saved visible and unhurried
- Sort indicators on all columns immediately on tab open
- Tab fade transition on switch
- Page size 10 added to History and Stats
- Docker resource limits right-sized for actual usage
- CI workflow — flake8 lint and syntax check on every push and PR

---

## v2.1.0

- Stats tab with confirmed import tracking
- Per-app Backlog Nudge toggles with age and cap controls
- Instance health dots — updated on every sweep and on add/edit
- Unsaved Changes notices across all tabs
- Import check delay in minutes, Check Now bypasses delay
- Non-root container user, read-only filesystem
- Multi-arch Docker images (amd64/arm64)
- Import check delay unit change — config key `import_check_hours` renamed to `import_check_minutes`, defaults to 120 minutes

---

## v2.0.0

- Authentication — first run setup screen, hashed password, session timeout
- Require Login toggle in Advanced (default on)
- Login page styled to match UI
- Lockout recovery — delete config and restart

# Changelog

All notable changes to Nudgarr are documented here.

---

## v3.2.0

**Per-Instance Overrides**

- Seven fields per instance: cooldown hours, max cutoff unmet, max backlog, max missing days, sample mode, backlog enabled, notifications enabled
- Sparse storage — only fields that differ from global are saved; unset fields inherit global automatically
- Model B override logic — any field set on an instance fully supersedes the global for that instance
- Sonarr instances omit max missing days (Radarr-only field)
- Sample mode uses a `__global__` sentinel for the Use Global option
- Batch size, sleep, jitter, and auth remain global only

**Desktop overrides UI**

- New Overrides tab between Instances and Sweep with animated slide transition
- Per-instance panel with all seven fields, Global hint below each field
- Per-card Apply button with debounce, dirty state tracking, Pending indicator in footer
- Reset All to Global with confirm dialog
- One-time modal on first enable explaining overrides behaviour
- Backlog and Notifications toggle rows show Global: On/Off inline

**Mobile overrides**

- Enable toggle in Quick Settings sheet with animated callout that flips to accent style when active
- First-time modal on first mobile enable (separate flag from desktop) explaining global vs override relationship and Apply requirement
- Landscape third nav tab (⊙) hidden until overrides enabled
- Left rail showing all instances with override count chip and pending dot
- Left rail and right panel layout in landscape with safe area inset on rail
- Steppers replace number inputs — hold cooldown to accelerate by 24, all others by 1
- Stepper buttons use programmatic addEventListener for reliable hold detection
- Per-instance Apply and Reset All to Global in landscape footer
- Backlog and Notifications sub-labels simplified to show Global value only

**Notifications**

- Sweep complete notification is now per-instance aware — each line shows the instance name and searched counts; instances with notifications disabled are silently skipped; instances that searched nothing are omitted
- Import Confirmed notification body updated to `"{title} imported via {instance}."`
- Error notifications respect per-instance notifications_enabled

**Radarr minimumAvailability filter**

- Movies whose minimumAvailability threshold has not been reached are skipped during cutoff unmet and backlog sweeps
- Release date resolved from physicalRelease → digitalRelease → inCinemas in that order
- Per-movie log line printed when a movie is skipped due to availability

**Backend**

- `arr_clients.py`: extracted `_radarr_movies_from_wanted` shared helper used by both cutoff unmet and backlog Radarr fetches, matching the existing Sonarr pattern
- Sweep log separator now shows timestamp (`--- Sweep 2026-03-14 18:42 UTC ---`) instead of cycle number
- `PYTHONUNBUFFERED=1` added to Dockerfile — log output appears immediately without buffering
- Contributor docstrings added to `sweep.py`, `scheduler.py`, `notifications.py`, and `config.py`

**Desktop UI**

- Titles in History and Imports are now clickable — clicking opens the item directly in the configured Radarr or Sonarr instance
- Instance modal shows a soft amber URL path warning when the entered URL contains a path component
- Confirm and alert modals moved to body level so they render correctly in all UI modes
- Tab gap between Instances and Sweep fixed

---

## v3.1.2

**Bug Fixes**

- Instance rename now correctly updates the connection dot — `api/test-instance` was missing the URL fallback for masked key lookup, causing the dot to go red after a rename even when the key was intact
- Renaming an instance now retroactively updates the instance name in History and Imports
- iOS PWA nav bar no longer overlaps the home indicator — portrait and landscape nav bars now expand to accommodate the safe area inset with icons correctly anchored above it
- What's New modal now compares major.minor only — patch version upgrades no longer trigger the modal

**UI**

- Instance modal Save button renamed to Apply to better reflect that changes are staged until Save Changes is clicked

---

## v3.1.1

**Bug Fixes**

- Instance rename no longer breaks API key restoration — `_restore_keys` now falls back to URL matching when the stored name doesn't match, so renaming and saving in one step preserves the connection
- Import confirmation is now rename-safe throughout — `stat_entries` stores `instance_url`, `check_imports` falls back to URL when name lookup fails, and `confirm_stat_entry` handles URL-based matching for both pending and confirmed rows
- Imports tab instance filter now keys on URL rather than name — existing entries remain visible after a rename

---

## v3.1.0

**SQLite Database**

Nudgarr now stores all state, history, stats, and exclusions in a local SQLite database. On first start after upgrading, existing JSON files are migrated automatically — no action required.

- `db.py` introduced as the single persistence layer replacing direct JSON file reads/writes
- Schema migrations versioned — v1 covers JSON migration, v2 adds iteration tracking and deduplication, v3 renames sweep type labels
- `nudgarr_state` key/value table for persistent app state across restarts
- Last run time and next run schedule now survive container restarts

**Scheduler**

- Cron expression replaces the run interval setting — default `0 */6 * * *` (every 6 hours)
- TZ environment variable respected for cron evaluation — schedules fire in container local time
- Startup no longer triggers an immediate sweep — first sweep fires when the cron expression next fires or Run Now is pressed
- Missed intervals during downtime are skipped; no catch-up on restart

**Skip Queued**

- Items already present in the Radarr or Sonarr download queue are silently skipped during sweeps
- Applies to both cutoff unmet and backlog searches across all instances
- Queued items do not consume a slot — max per run is always filled from actionable items only
- Always-on, no toggle or configuration required

**Imports Tab**

- Iteration tracking — each confirmed import of the same item increments a counter; re-imports at the same quality show a ×2, ×3 badge
- `first_searched_ts` records the original search timestamp and never resets; turnaround measures the full journey from first search to confirmed import
- Turnaround format extended — `<1m`, `2m`, `4h 23m`, `3d 14h`, `3w 2d`, `2mo`
- Turnaround column header tooltip explaining the calculation
- Duplicate imported rows from JSON migration deduplicated automatically
- Column header renamed to Last Searched

**Import Checking**

- Import check loop now runs on its own independent timer, separate from the sweep schedule
- Previously import checks only fired after a sweep completed — now they fire on the configured interval regardless of sweep activity

**History**

- Sweep type labels shortened — `Backlog Nudge` → `Backlog`, `Cutoff Unmet` → `Cutoff`
- Existing database rows updated automatically via migration v3
- History tab always resets to Last Searched descending on tab switch
- Next page button now correctly disabled when all items fit on one page
- Type column uses `.tag` CSS classes matching the Imports tab

**Settings**

- Settings tab now renders full width — consistent with other tabs
- Cron input validates on change — invalid expressions are highlighted with an amber glow
- Container local time displayed inline beneath the cron field for at-a-glance schedule confirmation

**UI Polish**

- Exclusion pill transitions rewritten — pure CSS opacity/transform, no keyframe animations
- Tooltips now trigger on hover without requiring a `.tooltip-wrap` parent element
- Tooltip text no longer inherits uppercase styling from table header context
- Instance modal name and URL placeholders are app-aware with correct default ports for Radarr and Sonarr; URL field no longer pre-fills with `http://`
- Lifetime Confirmed card includes a tooltip explaining what the counter tracks
- Auth toggle inline label simplified to `Enabled` / `Disabled`
- Support link pill correctly resets to saved state on tab switch
- Help text cleaned up across Settings, Advanced, and Notifications — consistent punctuation and inline `(0 Disables)` format
- Indexer rate limits warning updated
- CONTRIBUTING rewritten

---

## v3.0.0

**Mobile UI**

A purpose-built mobile layout — same backend, same logic, just a UI built for smaller screens. On any device under 500px wide (portrait), the desktop UI is swapped out for a native-feeling mobile experience.

- Four-tab bottom nav — Home · Instances · Sweep · Exclusions
- Home tab — full-width Run Now button, Last Run and Next Run cards, Movies and Episodes import pills (tap to browse), and four independent toggles: Automatic Sweeps, Notifications, Radarr Backlog, Sonarr Backlog
- Import pills — tap Movies or Episodes to open a scrollable bottom sheet of all confirmed imports across every Radarr or Sonarr instance combined, most recent first
- Exclusions — fourth nav item opens a bottom sheet with two inner tabs: Excluded (scrollable list with Remove buttons) and Add from History (recent searched items with + Exclude)
- Sweep tab — per-instance accordion cards with Library State and This Run stats, same data as desktop
- Instances tab — per-instance cards with Enable/Disable toggle
- Sweep in progress indicator — full-width banner on Home tab during active runs
- iOS safe area support — `viewport-fit=cover` with `env(safe-area-inset-bottom)` on nav
- Landscape orientation overlay — prompts to rotate to portrait
- Independent toggles for Radarr Backlog and Sonarr Backlog — previously a shared toggle

**Mobile UI polish**

- Hold to Configure hint pill spans full width with even 10px spacing above and below — spacing preserved when hint collapses so Run Now and time row never touch
- Quick Settings sheet — long press Run Now to configure Run Interval, Cooldown, Max Movies, Max Episodes without leaving the home tab; Run Interval dims when scheduler is off
- Exclusion remove and Add from History rows fade out and collapse before the API call fires — no abrupt disappearance
- History list reloads silently after adding an exclusion — no Loading… flash mid-animation
- Nav icons balanced — Home, Instances, Exclusions at 24px to visually match the Sweep ↻ glyph at 20px
- `theme-color` meta tag set to `#181a28` — Safari and Chrome toolbar matches the nav bar across all tab layout orientations on iOS and Android
- Safe area inset below nav filled with surface colour — no page background bleed below the home indicator
- Haptic feedback on all interactive elements — toggles 40ms, steppers 20ms, remove/exclude 60ms
- Button press animations on steppers, Remove, and + Exclude via JS-driven `.m-pressed` class
- Drag-to-dismiss on all bottom sheets with full-width touch target
- Disable button styled neutral/muted, Enable styled accent blue — red reserved for health errors only
- Import sheet titles corrected to "Imported"
- Instance name display bug fixed

---



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

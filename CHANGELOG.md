# Changelog

All notable changes to Nudgarr are documented here.

---

## v4.0.0

**Quality upgrade tracking, tag and profile filtering, structured logging, mobile redesign, and a full backend and frontend restructure.**

**Bug fixes (post-release)**

- Filters tab — instance pill now renders instance name with dot inside; dot colour reflects enabled state correctly; disabled instances no longer appear in the instance selector; card border turns amber on pending changes; Apply button correctly right-aligned with centred status text; pending changes trigger a proceed/cancel dialog when navigating away from the tab; loading tags and profiles for the second instance of a kind now works correctly (dropdown option values previously used position within the enabled list rather than the real config index); Load/Refresh button no longer stays permanently disabled after a successful load — clicking Refresh now correctly re-fetches from the arr instance
- Filters tab — cards are now fixed height (520px) so Radarr and Sonarr boxes always align; tags and profiles each occupy equal flex space within the card with independent scrolling; instances with no tags show a "No tags configured" message without affecting card height
- Overrides desktop — card pill now renders instance name with dot inside, removing the redundant separate name text
- Overrides landscape — stray `—` removed from panel header area; panel body now scrolls when content exceeds viewport height so Max Backlog and Max Missing Days are always reachable; rail updated to new accent pill style matching Filters rail
- Filters landscape — panel now correctly fills the right column alongside the rail; tags and profiles rendered in a two-column grid (tags left, profiles right) with each column as a flex container so lists stretch to fill available height and scroll independently; filter count chip updated to accent pill style
- Sweep logging — quality profile filter debug log now shows the profile name instead of the numeric ID (e.g. `profile=HD-1080p` instead of `profile_id=1`), matching the existing tag label resolution; `arr_get_profile_map` added to `arr_clients.py` as a shared helper
- Instances — instance health dot now correctly updates after toggle-then-save; `TOGGLE_IN_PROGRESS` guard cleaned up after health check completes so subsequent saves no longer leave the dot stale

**Tag and Quality Profile Filtering**

- New Filters tab (between Settings and Sweep) lets you exclude items from sweep by tag or quality profile, configured independently per instance
- Items matching an excluded tag or profile are filtered out of the sweep pipeline after title exclusions and before cooldown — they never consume a search slot
- Both cutoff unmet and backlog pipelines apply the same filters, so excluded items are skipped in all sweep modes
- Tags and profiles are fetched live from each arr instance via two new proxy endpoints (`GET /api/arr/tags`, `GET /api/arr/profiles`) — API keys never leave the server
- Selections saved as `sweep_filters` on the instance config object — persists across page refresh and container restart
- Per-instance: each instance has its own independent filter configuration
- Debug logging per filtered item (`skipped_tag: Title (tag=4K-Only)`, `skipped_profile: Title (profile=Ultra-HD)`) and aggregate info counts (`skipped_tag=2 skipped_profile=1`) in the sweep log
- Disabled instances show their last saved filters read-only with an "All Instances Disabled" label — filters are preserved and reactivate when the instance is re-enabled
- Desktop Filters tab: two-column grid, Radarr (blue) and Sonarr (green) boxes, per-box instance selector (dropdown for multiple instances), Load Tags & Profiles button, scrollable tag and profile lists with pill display and search, per-box Apply
- Landscape mobile fourth nav tab (⊘ Filters): rail listing all instances with filter count chip, panel with Filtered Tags and Filtered Quality Profiles sections, Load/Refresh and Apply in footer, amber save dot on Apply
- Tab order updated: Instances — Overrides — Settings — Filters — Sweep — History — Imports — Notifications — Advanced

**Landscape mobile Overrides refresh**

- Rail updated to match Filters style — larger coloured dot (7px), override count shown as an accent pill on its own line ("2 Overrides") instead of a grey inline badge
- Panel header (instance name + app badge) removed — fields start immediately with no wasted vertical space
- Footer status text updated to title case — "No Overrides Set" replaces "Global Inherited"
- Apply now fires the amber save indicator in the landscape header, consistent with Backlog/Execution saves

**Quality upgrade tracking**

- Imports tab gains an Upgrade column showing the full quality upgrade path per item as a hover tooltip — e.g. Acquired → WEBDL-720p on first download, then WEBDL-720p → Bluray-1080p on each subsequent upgrade
- Each confirmed import event is recorded in a new `quality_history` table with `quality_from`, `quality_to`, and timestamp; history is displayed chronologically oldest-first so the upgrade journey reads naturally top to bottom
- Acquired label used for first-download rows where no prior file existed
- Cutoff unmet and backlog sweeps both fire an additional `GET /api/v3/movie/{id}` or `GET /api/v3/episode/{id}` per chosen item before searching to read the current file quality as `quality_from` — the wanted/cutoff endpoint does not reliably include the full file object in its response so a direct lookup is required
- `quality_to` captured from the `downloadFolderImported` history event at import confirmation time
- `quality_history` rows cascade-delete automatically when the parent `stat_entries` row is removed — Clear Imports and prune require no changes
- Iteration count moved out of the type badge into a dedicated Count column (×N pill, empty when iteration is 1) — consistent with the History tab pattern; type badge now shows type only
- Migration v8 adds `quality_from` to `stat_entries` and creates the `quality_history` table for v3.2 upgrades; fresh installs get both via `_SCHEMA_SQL`

**UI**

- Refreshed visual design — deeper background palette, accent colour updated to `#5b72f5`, new CSS token set including `--accent-lt`, `--radius`, `--border-md`
- Typography updated to Outfit (UI text) and JetBrains Mono (code/mono elements), served via system font stack with graceful fallback — no external CDN dependency
- Sweep cards redesigned — Library State band (Cutoff Unmet + Backfill) and This Run band (Eligible, Searched, Cooldown, Capped) with section labels; lifetime totals below; Disabled badge replaces full-card dim; last run moved to card header
- Header and status bar restructured — three separate pills consolidated into a single segmented status bar; scheduler state uses CSS class toggle instead of inline style
- Overrides tab label updated to include ⊙ glyph
- Instance modal now has an explicit Test connection button. Shows a live result (checking → connected with version, or error message) before you apply. Result is cached — pressing Apply immediately after a successful test reuses it without a second request.
- Save bar styling unified across Instances, Settings, Notifications, and Advanced tabs using a shared `.save-bar` class. Overrides section divider spacing and line weight adjusted.

**Mobile**

- Portrait nav restructured — four tabs now Home · Sweep · History · Settings; Instances hidden, Exclusions promoted into History as an inner tab alongside History and Add from History
- Home tab redesigned — stat grid (Last Run, Next Run, Movies, Episodes tap cards); instance health rows inline; Auto Schedule and Notifications toggles on home; Run Now button redesigned with animated icon and running state
- Quick Settings sheet removed — Cooldown, Cutoff Max, Sample Mode, Notifications, and Per-Instance Overrides toggle now live in a dedicated Settings tab with stepper and segmented controls
- Landscape nav tabs renamed from Settings + Advanced to Backlog + Execution; Backlog tab covers per-app missing search controls; Execution tab covers Batch, Sleep, Jitter, and a cron field with live validation
- Landscape Overrides panel gains an instance name header with Radarr/Sonarr app badges; Desktop View button moved from Advanced tab to the header

**Bug fixes**

- Sonarr clickable titles now correctly open the series page in Sonarr. Previously the arr-link route used the episode ID to look up the series, which would fail. `series_id` is now stored in `search_history`, returned by the history API, and passed through to `/api/arr-link`. Migration v7 adds the column to existing installs.
- Editing an existing instance no longer clears its Per-Instance Override values. The previous save path rebuilt the instance object with only four fields, dropping any stored overrides.
- History summary now normalises trailing slashes on both the `url_to_name` lookup and the grouping key, preventing duplicate or missing history pills when a URL was stored inconsistently across sweeps.
- Sweep tab stats now persist across container restarts. `last_summary` is written to `nudgarr_state` after each sweep and restored on startup alongside `last_run_utc`. Previously the Sweep tab showed empty cards until the next sweep completed after a restart.

**Backend cleanup**

- `db.py` — collapsed all migration functions into the base `_SCHEMA_SQL`. Removed `_run_migration`, `_run_migration_v2` through `_run_migration_v6`, `_migrate_exclusions`, `_migrate_state`, `_migrate_stats`. All installs are on the final schema by now; the migration chain served its purpose. `init_db` applies the base schema and runs any pending post-reset migrations.
- `constants.py` — removed legacy `sample_mode` key from `DEFAULT_CONFIG`. Old installs that still had this key will have had it migrated away before v4.0.
- `sweep.py` — removed `legacy_mode` fallback variable in `run_sweep`. Both per-app sample mode lookups now fall back to `"random"` directly.
- `stats.py` — removed `pick_ids_with_cooldown` and `mark_ids_searched`. Both had zero call sites in the codebase and were explicitly documented as legacy helpers.
- `state.py` — removed dead stubs: `load_state`, `ensure_state_structure`, `save_state`, `load_stats`, `save_stats`, `save_exclusions`. All had zero external callers. Active functions (`state_key`, `load_exclusions`, `prune_state_by_retention`) kept.
- `ui.html` — renamed element IDs `pill-dryrun`, `dot-dryrun`, `txt-dryrun` to `pill-scheduler`, `dot-scheduler`, `txt-scheduler`. These IDs show AUTO/MANUAL scheduler state and never had anything to do with dry run mode, which was scratched.
- Flake8 — fixed E302/E303/E305 blank line violations in `globals.py`, `state.py`, `stats.py`, `db.py`. CI ignore list trimmed to `E501,W503` only.
- Frontend structure — `ui-mobile-portrait.js` split into `ui-mobile-portrait.js` (tab switcher and init, 118 lines), `ui-mobile-portrait-home.js`, `ui-mobile-portrait-history.js`, and `ui-mobile-portrait-settings.js`; `ui.css` split into `ui.css` (desktop, 585 lines), `ui-mobile.css` (portrait, 415 lines), and `ui-landscape.css` (landscape, 294 lines). `validate.py` updated to check all 15 static files and 3 CSS link tags (261 checks total).

**Logging and error handling**

- Structured logging throughout — all operational modules now use Python's `logging` module with `logging.getLogger(__name__)`. Log output goes to both stdout (Docker log driver) and a rotating file at `/config/logs/nudgarr.log` (5 MB per file, 3 backups, 20 MB total cap).
- Log level configurable live from the Advanced tab — choose DEBUG, INFO, WARNING, or ERROR. Takes effect immediately without a container restart. Default is INFO.
- Log level now correctly applies on container restart. Previously `register_blueprints()` and `db.init_db()` ran before `setup_logging()`, allowing Python's logging machinery to partially initialise before the configured level was applied. Startup order corrected so `setup_logging` always runs first.
- Werkzeug startup banner suppressed — `Serving Flask app` and `Debug mode: off` lines no longer appear in container logs. These were unrelated to Nudgarr's Log Level setting and caused confusion when DEBUG was enabled. Actual Werkzeug errors still surface.
- Startup banner now labels the log level clearly as `(Nudgarr verbosity — set in Advanced tab)` to distinguish it from Flask's separate debug mode.
- Each sweep header now includes the active log level — `--- Sweep 2026-03-18 23:49 UTC --- [log level: DEBUG]` — so diagnostics clearly show what verbosity was in effect for each run without hunting through startup banners.
- Log Level dropdown moved inline with the Backup All, Download Diagnostic, and Open Issue buttons in the Support & Diagnostics card. Options prefixed with `Log:` so the selected value is always self-describing. Helper text removed.
- Support & Diagnostics card description updated to "Data backup and diagnostic tools."
- Diagnostic download now includes the current log level and the last 250 lines of `nudgarr.log` with URLs masked — useful for sharing when troubleshooting.
- Flask error handlers registered for 400, 404, and 500 — all return JSON instead of Flask's default HTML error pages, which previously broke the frontend API wrapper and exposed framework internals.
- Config write failures now return a 500 with a readable error message (`Failed to write config — check disk space and permissions`) instead of an unhandled exception. Covers all seven config-writing routes.
- Import check route now correctly returns 500 on failure. Previously returned 200 with `{ok: false}`, which the frontend treated as success and swallowed the error silently.
- `loadAll()` on the desktop now shows an alert if the backend is unavailable on cold start instead of rendering a blank page with no message.
- `checkImportsNow()` now surfaces a user-visible alert on failure instead of logging to the console only.
- Global `unhandledrejection` and `error` handlers added to catch uncaught exceptions and unhandled promise rejections — logged to console rather than disappearing silently.
- Mobile version mismatch banner — if the page version does not match the running server version after a container update, a tap-to-reload banner appears at the top of the mobile UI.

**Performance and reliability**

- Search history and stat entry writes are now batched — a single SQLite transaction covers the entire sweep batch instead of one commit per item. At higher Max per Run values this meaningfully reduces WAL flushes on spinning storage.
- Sonarr series map fetched once per instance per sweep instead of twice when both cutoff and backlog are enabled — previously two full `GET /api/v3/series` calls fired per Sonarr instance.
- Per-instance cooldown now correctly reflected in History tab `eligible_again` timestamps — previously always used the global cooldown value regardless of instance overrides.
- `VALID_SAMPLE_MODES` consolidated into `constants.py` — was defined identically in `config.py` (twice) and `sweep.py`.
- `get_last_searched_ts_bulk` unused `instance_name` parameter removed — the SQL query filtered by `instance_url` only; the parameter implied a fallback that did not exist.
- Shared `_process_import_events` helper extracted in `stats.py` — the Radarr and Sonarr import check branches were structurally identical with ~30 lines duplicated verbatim.
- Diagnostics route raw `get_connection()` calls replaced with proper db-layer helpers (`count_search_history`, `count_confirmed_entries`, `get_search_history_counts`).

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

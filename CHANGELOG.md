# Changelog

All notable changes to Nudgarr are documented here.

---

## v4.3.0

**Intel Tab Redesign, Sample Mode Overhaul, Auto-Exclusion Queue Fix, KPI Number Formatting.**

This release folds v4.2.1 (never publicly shipped) into v4.3.0. All changes from v4.2.1 are included below.

**Intel Tab Redesign (v4.3.0)**

- Library Score ring, Stuck Items card, Sweep Efficiency card, and Library Age vs Success card removed. The scoring system and assumption-based metrics have been replaced with hard facts drawn directly from the database.
- Five new cards: Import Summary, Instance Performance, Upgrade History, CF Score Health, and Exclusion Intel.
- Import Summary shows average turnaround, searches per import, quality upgrades confirmed, and a pipeline breakdown table with import counts, search counts, and conversion rate per pipeline. Disabled pipelines show their historic data dimmed with a Disabled pill.
- Instance Performance shows sweep runs, total searched, confirmed imports, and average turnaround per instance. Disabled instances show historic data dimmed.
- Upgrade History replaces Quality Iteration. Shows Imported Once and Upgraded counts alongside the top 3 upgrade paths across all apps.
- CF Score Health is a new card showing total indexed, below cutoff count, percentage, average gap, worst gap, Radarr/Sonarr split, and last synced time. Reads live from `cf_score_entries` and is not stored in `intel_aggregate`. Not affected by Reset Intel. Card is hidden when CF Score is disabled.
- Exclusion Intel simplified to total exclusions, auto this month, manual/auto split, titles cycled through exclusions, and unexcluded titles later imported. Calibration Signal and avg searches at exclusion removed. Auto-exclusions disabled notice added when auto-exclusion is off.
- `get_pipeline_search_counts()` and `get_cf_score_health()` added to `db/intel.py` as named functions following the existing DB module pattern.
- Dead code removed: `_compute_library_score()`, `_compute_calibration()`, `_sh_field()`, `_CALIBRATION_HIGH`, `_CALIBRATION_LOW` from `routes/intel.py`. `_get_library_age_bucket()` from `db/entries.py`. `_get_library_age_bucket_for_history()` from `db/history.py`.
- Dead writes removed: `library_age_buckets` and `success_total_worked` no longer written to `intel_aggregate` on every search/import. The columns remain in the table as unused but removing them would require a migration.
- `ui-responsive.css` dead `.intel-grid-score` stacking rule removed.
- Cold start screen unchanged: 25 confirmed imports or 50 sweep runs threshold preserved.
- Reset Intel, Clear History, Clear Imports, and Clear Log are fully independent operations with no overlap.
- Average turnaround displays in smart units matching the Imports tab format (30m, 3h, 1d 12h, 8d etc) rather than a raw decimal days value. Instances with no confirmed imports show a dash.
- Import Summary headline grid reflows to a 2+1 layout at phone width so the three headline numbers no longer overflow.
- Pipeline breakdown section label renamed from Pipeline Breakdown to Breakdown to avoid repeating the word alongside the Pipeline column header.
- Quality Upgrades Confirmed tooltip opens leftward to stay within the card on narrow viewports.
- Instance Performance tooltip reworded to plain language with an explanation of what Avg Turnaround measures.
- `formatCompact` applied to pipeline breakdown Imports and Searches columns and Instance Performance Sweep Runs, Total Searched, and Confirmed Imports columns.

**KPI Number Formatting (v4.3.0)**

- `formatCompact(n)` utility function added to `ui-core.js`. Numbers below 10,000 display as-is; 10,000 and above display as compact format (10k, 1.2M etc).
- Applied at five locations where large counts would overflow constrained mobile layouts: History page info line, History KPI pills, Imports page info line, Imports Movies/Episodes stat cards, CF Score page info line and coverage inline text.
- Also applied to Intel tab pipeline breakdown and Instance Performance table columns.

**Auto-Exclusion Queue Check Fix (from v4.2.1)**

- `_is_title_in_queue` in `scheduler.py` removed. It used `/api/v3/queue?movieId=X` to check if a candidate was actively downloading before writing an auto-exclusion. The per-item filtered endpoint does not work reliably across Radarr/Sonarr versions. On affected versions the filter is silently ignored and the full queue is returned for every request, causing every auto-exclusion candidate to be reported as in-queue and skipped indefinitely.
- Auto-exclusion queue check now fetches the full queue once per instance upfront using `radarr_get_queued_movie_ids` and `sonarr_get_queued_episode_ids`. Reduces API calls from one per candidate to one per instance per cycle.
- Users with auto-exclusion enabled who had stuck items that never got excluded despite reaching the threshold will see correct exclusions on the next import check cycle after upgrading.

**Sample Mode Overhaul (from v4.2.1)**

- `round_robin` added to `VALID_SAMPLE_MODES` and `VALID_BACKLOG_SAMPLE_MODES`.
- `VALID_CF_SAMPLE_MODES` constant added: `random`, `alphabetical`, `oldest_added`, `newest_added`, `round_robin`, `largest_gap_first`. Independent of the other two constants.
- `radarr_cf_sample_mode` and `sonarr_cf_sample_mode` added to `DEFAULT_CONFIG`, both defaulting to `largest_gap_first`. Existing installs receive these keys on first boot via `fill_missing_keys`.
- Round Robin sorts NULL items (never searched) first in random order, then searched items ascending by `last_searched_ts`.
- `largest_gap_first` uses a unified sort key `(-gap, null_flag, tiebreaker)` so gap group boundaries are never violated. Previous split-list implementation incorrectly placed low-gap NULL items above high-gap searched items.
- CF Score sample mode added to Overrides tab per-instance override field.
- Round Robin option added to Settings tab (Cutoff Unmet) and Advanced tab (Backlog). All four tooltips updated.
- CF Score tab Sample Mode selects added below each max input (Radarr then Sonarr).
- 14 unit tests added covering both new sort modes including NULL handling, tiebreakers, and cross-group ordering.

---

## v4.2.1

Folded into v4.3.0. Never publicly shipped.

---

## v4.2.0

**Sample Mode Overhaul — Round Robin across all pipelines, CF Score gets full mode control, starvation fix. Auto-exclusion queue check fix.**

**Auto-Exclusion Queue Check Fix**

- `_is_title_in_queue` in `scheduler.py` has been removed. It used `/api/v3/queue?movieId=X` and `/api/v3/queue?seriesId=X` to check if a candidate title was actively downloading before writing an auto-exclusion. The per-item filtered endpoint does not work reliably across Radarr/Sonarr versions — on affected versions the filter is silently ignored and the full queue is returned for every request, causing every auto-exclusion candidate to be reported as in-queue and skipped indefinitely regardless of actual queue state.
- Auto-exclusion queue check now fetches the full queue once per instance upfront using `radarr_get_queued_movie_ids` and `sonarr_get_queued_episode_ids` — the same functions the sweep pipeline already uses. Candidate item IDs are checked against the resulting set in memory. This reduces API calls from one per candidate to one per instance per cycle and produces correct results regardless of Radarr/Sonarr version.
- Users with auto-exclusion enabled who had stuck items that never got excluded despite reaching the threshold will see those titles correctly excluded on the next import check cycle after upgrading.

**Round Robin — Cutoff Unmet and Backlog**

- `round_robin` added to `VALID_SAMPLE_MODES` and `VALID_BACKLOG_SAMPLE_MODES`. Both constants remain independent — adding a mode to one does not automatically add it to the other.
- Round Robin primary sort: oldest `last_searched_ts` ascending so the longest-waiting eligible item goes first.
- NULL handling: items with no record in `search_history` (never searched) are treated as highest priority. Among NULL items the tiebreaker is random so new additions do not always queue in the same insertion order.
- Tiebreaker for equal timestamps on Cutoff Unmet and Backlog: random (consistent with the shuffle step that precedes the sort).
- Round Robin option added to the Radarr and Sonarr Sample Mode selects in the Settings tab (Cutoff Unmet) and Advanced tab (Backlog). All four tooltips updated to document the new mode.

**CF Score Sample Modes (new)**

- CF Score pipeline previously had no user-selectable sample mode — pick order was hardcoded worst-gap-first with no tiebreaker.
- `VALID_CF_SAMPLE_MODES` constant added: `random`, `alphabetical`, `oldest_added`, `newest_added`, `round_robin`, `largest_gap_first`. Kept as a third independent constant — do not merge with `VALID_SAMPLE_MODES` or `VALID_BACKLOG_SAMPLE_MODES`.
- `radarr_cf_sample_mode` and `sonarr_cf_sample_mode` added to `DEFAULT_CONFIG`, both defaulting to `largest_gap_first`. Existing installs receive these keys silently on first boot via `fill_missing_keys()` — no manual migration required.
- `largest_gap_first` formalizes the previous hardcoded behavior: primary sort gap descending, with a Round Robin tiebreaker added to fix the starvation bug (see below).
- CF Score Sample Mode selects added to the CF Score tab config card, stacked below each respective max input (Radarr then Sonarr). Tooltips cover all six modes with CF-specific descriptions for Largest Gap First and Round Robin.
- Existing max input tooltips updated to remove the stale "picks worst gap items first" wording now that sample mode is user-controlled.
- `cf_sample_mode` override field added to the CF Score section of each instance card in the Overrides tab. Uses the `__global__` sentinel pattern matching `backlog_sample_mode` — shows "Use Global (Largest Gap First)" when no override is set, highlights with `ov-active` blue ring when overridden. Hidden when CF Score is disabled globally, consistent with existing CF Score section behavior.
- Per-instance `cf_sample_mode` resolved via `_resolve()` in `sweep.py`, falling back to the global `radarr_cf_sample_mode` or `sonarr_cf_sample_mode` when no override is set. Invalid resolved values fall back to `largest_gap_first`.
- `config.py` validates `radarr_cf_sample_mode` and `sonarr_cf_sample_mode` at the top level and `cf_sample_mode` in the per-instance overrides block against `VALID_CF_SAMPLE_MODES`.

**Starvation Fix — Largest Gap First**

- Previous hardcoded worst-gap-first had no tiebreaker: items with equal gap values were returned in arbitrary DB order, causing the same small group of titles to be searched every cooldown cycle while other equal-gap items were never reached.
- `largest_gap_first` now uses a Round Robin tiebreaker within tied gap groups: among items sharing the same gap value, whoever has been waiting longest goes first. NULL items within a tied group are shuffled randomly.
- Effect: every eligible item in a tied gap group is eventually searched before any item in that group gets a second turn.

---

## v4.2.0

**CF Score Scan, Intel Tab, Sweep Tab Redesign, Responsive UI, Backlog Sample Mode Split, Maintenance Window, Grace Period, Auto-Exclusion Toggles, Cutoff Unmet Toggles, Advanced Tab Restructure, and Sticky Header.**

**Auto-Exclusion Toggles**

- `radarr_auto_exclude_enabled` and `sonarr_auto_exclude_enabled` added as independent per-app master toggles for auto-exclusion. Both default to `False` so fresh installs have auto-exclusion off by default and explicit enabling is required.
- Toggle is now the on/off switch — the threshold field is the search count, not the off mechanism. Setting the threshold to 0 while the toggle is on is not valid; `syncAutoExclUi()` auto-sets it to 1 when the toggle is turned on with a 0 value.
- Fields (Exclude After X Searches, Unexclude After X Days) grey out when the toggle is off, matching the Backlog and Cutoff Unmet pattern.
- Disabled popup fires when the toggle is turned off while auto-exclusions exist, not only when the threshold drops to zero — covers the new toggle-off disabling path.
- Migration: if the toggle key is absent and the threshold is above 0 (existing user who had auto-exclusion active), `validate_config` sets `enabled=True` preserving their behaviour. Threshold at 0 with no toggle key leaves `enabled=False`.
- `scheduler.py` `_run_auto_exclusion_check` reads both enabled toggles before reading thresholds — a disabled app treats its threshold as 0 without requiring the user to change the threshold field.
- UI labels updated throughout: "0 = Off" replaced by "0 = Disabled" where threshold semantics were previously implied. Section description updated to remove stale reference to Per-Instance Overrides tooltip.
- Sonarr-facing wording updated from "show" to "episode" throughout (tooltip, help text, and unexclude field) to match the actual level Nudgarr operates at — auto-exclusion fires per episode title, not per series.

**Advanced Tab Restructure (final)**

- Three full-width horizontal cards replacing the previous two-card side-by-side layout:
  - Row 1 — Backlog Nudges: full width, Radarr and Sonarr side by side with their own toggle, fields, and sample mode. Each app column has its own `app-head` divider.
  - Row 2 — Auto-Exclusion: full width, Radarr and Sonarr side by side. Each app has its own toggle and fields (Exclude After X Searches, Unexclude After X Days).
  - Row 3 — Configuration: full width, `cols3` inner grid in two rows of three. Top row: For the Arr-tists, Pipelines, Data Retention. Bottom row: Stats, Security, UI Preferences. Vertical dividers via `border-right` with padding on each cell.
- `adv-cfg-cell--left/mid/right` classes added to all six configuration cells. At 720px breakpoint in `ui-responsive.css`, `border-right` is removed and cells gain `border-top` separators — correct stacking on mobile portrait.
- Advanced tab pager removed entirely (`advSetPage()` and all pager elements gone). All settings visible simultaneously without scrolling between pages.

**Settings Tab Layout**

- Scheduler and Cutoff Unmet cards wrapped in `cols2` with `align-items:stretch` — side by side at equal height, matching the confirmed mockup.
- Radarr and Sonarr sub-labels in Cutoff Unmet use the same bordered uppercase inline style as the Auto-Exclusion section in Advanced.

**Bug Fixes**

- Sweep feed empty after container restart: `last_sweep_start_utc` was only stored in memory. On restart it reset to `None`, causing the feed to show "No sweep has run yet." while stats (restored from DB via `last_summary`) showed correctly. Fixed by writing `last_sweep_start_utc` to `db.set_state()` after each sweep and restoring it from `db.get_state()` on scheduler startup alongside `last_run_utc` and `last_summary`.
- CF Score progress stuck mid-percentage: `_cfWaitForScan` was only called from `cfScanLibrary`. Syncs triggered from the filter change popup or background scheduler left progress rings frozen at whatever percentage was rendered when the tab was first opened. Fixed by adding `_cfScanPolling` flag and auto-start logic in `fillCfScores` — if `scan_in_progress` is true on tab open and no polling loop is running, `_cfWaitForScan` starts automatically.
- CF Score sync popup navigating to tab: `syncCfIndexFromModal` was calling `showTab('cf-scores')` after firing the scan. Removed — modal closes, scan fires, user stays on their current tab.
- CF Score `quality_from` empty: CF Score items had `quality_from: ""` so the Imports tab showed "Acquired" instead of "Upgraded". Added `fn_get_quality` fallback fetch per item in `sweep.py` CF Score search loop.

**Polish**

- `sw-pill` (pipeline badge in Imports and Sweep feed) gained `white-space:nowrap` — "CF Score" no longer wraps to two lines in narrow table cells.
- Per-page default changed from 25 to 10 across History, Imports, CF Score, and Sweep feed — both HTML `selected` attribute and JS fallback defaults.
- Log level select gained `text-align:center` so the selected value is centred in the dropdown.
- Sample Mode help text shortened to single line across Settings and Advanced — "Pick order for Cutoff Unmet Radarr/Sonarr items" and "Pick order for missing Radarr/Sonarr items".
- All "0 Disables" and "0 = Disabled" wording replaced with "0 = Off", "0 = Keep Forever", "0 = No Grace Period", "0 = No Cooldown", or "0 = No Age Filter" as appropriate throughout Advanced and Settings tabs.

**CF Score Sync — Cron Schedule and Persistence**

- `cf_score_sync_hours` replaced by `cf_score_sync_cron` (default `0 0 * * *` — midnight daily). Full cron expression gives users precise control to avoid conflicts with other scheduled tasks. Same cron infrastructure and UI pattern as the sweep scheduler.
- Last sync time persisted to `nudgarr_state` DB (`cf_last_sync_utc`). Container restarts now correctly respect the cron schedule rather than triggering an immediate re-sync. Next scheduled fire is calculated on startup and logged.
- Enabling CF Score for the first time triggers an immediate sync so the CF Score tab populates without waiting for the next cron fire.
- Next Sync displayed in the CF Score tab right card alongside Last Synced, calculated from the cron expression and last sync time.
- Coverage pills now color-coded: blue = sync in progress (with live percentage), green = 100% complete, muted dash = never synced.
- Migration: existing `cf_score_sync_hours` values are automatically converted to an equivalent cron expression on first start after upgrade.
- Scheduled CF Score syncs are now suppressed during the configured Maintenance Window, consistent with sweep suppression. Manual Scan Library always bypasses the window. Settings tab Maintenance Window help text updated to reflect this.
- `cf_score_sync_cron` tooltip updated to mention Maintenance Window suppression and that manual Scan Library always runs regardless.

- CF Score sync concurrency fix: a second scheduled cron fire while a sync was already running would start a concurrent sync, corrupting progress state and leaving coverage pills frozen mid-percentage. Fixed with `STATUS["cf_sync_in_progress"]` flag — the scheduler loop skips a scheduled fire if a sync is already running. Manual Scan Library also respects this flag. Progress rings now correctly clear on exception via `try/finally` in both Radarr and Sonarr instance sync methods.

- CF Score tab stat cards (Items Indexed, Below CF Cutoff) removed — both always showed identical numbers since `cf_score_entries` only contains items below cutoff by design. The per-instance coverage list already surfaces this data accurately.
- CF Score Save Changes failing with `cf_score_sync_hours must be an int >= 0` — old key was still present in the integer validation list and not stripped from incoming POST payloads. Fixed by removing from validation and adding to dead keys list so it is stripped before validation on both load and save.
- CF Score settings card: spacing added between Sync Schedule and Per-Run Limits sections.

**Bug Fixes (post-release)**

- Migration v12 (`cf_score_import_count`) crashed on fresh install container restart with `sqlite3.OperationalError: duplicate column name`. Fresh installs already have the column via `_SCHEMA_SQL` so the `ALTER TABLE` failed before the migration record was written, causing it to re-fail on every restart. Fixed with a `PRAGMA table_info` check before the `ALTER` — the migration record is now always written whether or not the column was added.
- Turnaround column tooltip in the Imports table was rendering as a single line extending off the right edge of the screen on desktop. Root cause: the `th` element has `white-space: nowrap` which cascaded into the tooltip box. Tooltip removed entirely — the column label is self-explanatory.
- Confirmed tooltip on the Imports stat card was opening rightward and overlapping the tab bar. Changed to `tip-down`.
- Tooltip `z-index` raised from 200 to 201 — previously equal to the sticky header's `z-index: 200`, causing tooltips in the top card of any tab to render behind the sticky header on desktop.
- Tooltip direction classes audited across all tabs. Right-column and right-card tooltips in Settings and Advanced were opening rightward and overflowing the viewport on desktop. Changed to `tip-left` where appropriate, `tip-down` for the Backlog Nudges card (first card, closest to sticky header).

**UI Text Polish**

- Settings — Maintenance Window help: `Scheduled sweep suppression. Manual runs are not affected.` shortened to `Manual runs are not affected.`
- Settings — Cooldown help: `Minimum hours before the same movie or episode can be searched again (0 = No Cooldown)` shortened to `Minimum hours before an item can be searched again (0 = No Cooldown)`. JS constant `_COOLDOWN_HELP_DEFAULT` updated to match.
- Settings — Cutoff Unmet card: added `Finds and searches cutoff unmet titles from your library.` helper text beneath the heading, matching the Backlog Nudges reference style in Advanced.
- Settings — Max (Per Instance) help under Cutoff Unmet: `Maximum Cutoff Unmet movies/episodes nudged per instance per run (0 = All Eligible)` collapsed to `0 = All Eligible`.
- Notifications — Auto-exclusion event help: shortened to `Fires on auto-exclusion when the search threshold is reached with no import`.
- Advanced — Auto-exclusion section description: shortened to `Auto-exclude titles repeatedly searched with no confirmed import. Exclusion thresholds are global and apply across all instances by title.`
- Advanced — Session Timeout and Show Support Link fields: `margin-top: 12px` added for breathing room.
- Advanced — Require Login: tooltip added summarising local-network scope, password hashing, and remote access guidance.
- Advanced — Danger Zone header: `margin-bottom` corrected from 4px to 10px so the button rows align with Support & Diagnostics.

**Mobile Responsive**

- `html { overflow-x: hidden }` added globally to prevent Safari from auto-zooming the page when any element briefly exceeds the viewport width.
- Settings tab: `sched-row` class added to both `flex-wrap: nowrap` rows in the Scheduler card. At 720px they wrap so the Cron Expression and Maintenance Window fields don't overflow on narrow viewports.
- History and Imports tabs: `.tab-filter-controls` class added to the filter wrapper div. At 720px the controls go full-width, `margin-left: auto` is removed, dropdowns wrap two-per-row, and search input takes the full width of the third row.
- Sweep grid: `1fr` column changed to `minmax(0, 1fr)` at 720px to prevent grid cells expanding beyond the viewport when inner content is wide.
- Sweep cards: `min-width: 0; overflow-x: auto` at 480px (portrait) and in the landscape orientation query so per-instance stat rows scroll within each card rather than overflowing.
- Sweep tab in landscape: grid stacks to single column so each card gets the full viewport width with content scrollable horizontally within the card.
- Import stat cards: reordered in portrait (480px) using CSS `order` — Confirmed card goes full-width on top, Movies and Episodes sit side by side below. HTML and JS references unchanged.
- Imports table: `width: auto` override added at 720px to counter `ui.css` global `table { width: 100% }` which was causing the 8-column table to squish into the wrapper width and produce phantom horizontal scroll space. `min-width: 760px` floors the table at a size that fits all columns. `position: sticky` removed from the imports table first column — applying sticky inside `overflow-x: auto` causes Safari to add phantom scroll space equal to the viewport width after the last column.
- Imports table first column: `white-space: normal; word-break: break-word; min-width: 130px; max-width: 160px` allows long titles to wrap to two lines on mobile.
- Tooltip boxes: all tooltips override to open downward (`top: calc(100% + 3px)`) on portrait (480px) and landscape phone viewports — downward is the only direction guaranteed to have space when cards stack full-width. Width reduced to 220px and `white-space: normal` enforced so text wraps correctly inside the box.
- Tab bar in landscape: `flex-wrap: nowrap; overflow-x: auto` at `orientation: landscape` and `max-height: 500px` keeps all tabs on a single scrollable line. Targets phones only — tablets and desktops in landscape are taller than 500px.
- CF Score filter controls: `min-width` constraints shed at 720px so filter dropdowns don't overflow on narrow viewports.



- New third search pipeline that finds monitored files where `customFormatScore` is below the quality profile's `cutoffFormatScore`. Completely independent of the quality tier — scans all monitored files with `hasFile=true` and `isAvailable=true` (Radarr) regardless of `qualityCutoffNotMet` status. A movie at 720p with a low CF score is just as eligible as a movie at Bluray-1080p with a low CF score.
- Enable in Advanced > Pipelines to unlock the CF Score tab. Feature is fully dormant when disabled — no background work runs.
- `CustomFormatScoreSyncer` runs as a dedicated background thread on a configurable schedule (default 24 hours). Performs a full library pass. Eligibility filters applied at sync time: `current_score >= minFormatScore` (excludes files penalised below the profile minimum — Radarr will never grab anything below this floor) and `current_score < cutoffFormatScore`. `minUpgradeFormatScore` is intentionally not applied at sync time — whether a found release clears the minimum increment is Radarr/Sonarr's decision at grab time, consistent with the Cutoff Unmet and Backlog pipelines. Cooldown handles the case where no qualifying release is found.
- Syncer applies per-instance tag and profile sweep filters at write time (syncer-as-gatekeeper). Items with excluded tags or profiles never enter `cf_score_entries` and are therefore never searched.
- Syncer writes live sync progress to `nudgarr_state` per instance (`cf_sync_progress|{app}|{url}`) as it processes batches. Coverage cards in the CF Score tab show live percentage during a Scan Library run.
- `cf_score_entries` table stores the index. Stale entries (deleted, unmonitored, or score now met) are pruned at the end of each sync run per instance. `added_date` field populated from Radarr's `added` field so Library Added date shows correctly in History.
- Sweep pipeline adds a third CF Score pass after Cutoff Unmet and Backlog. Applies the same filter chain as the other pipelines: exclusions, queue skip, and cooldown. Can overlap with Cutoff Unmet on the same item — cooldown naturally prevents double-searching within the same window.
- CF Score pass uses `pick_items_with_cooldown` with a `"worst_gap"` sample mode (unrecognised, so ordering is preserved) to apply cooldown and cap at `cf_max` while maintaining worst-gap-first ordering. The DB query returns all eligible items without a limit — the limit is applied in Python after the full filter chain.
- Searches recorded in `search_history` with `sweep_type='CF Score'` and in `stat_entries` with `entry_type='CF Score'` (own type, separate from Cutoff Unmet's `'Upgraded'`). History tab shows CF Score badge in amber. History Library Added date populated from syncer-stored `added_date`. Imports tab, import confirmation loop, Intel, and auto-exclusion all see CF Score activity correctly attributed.
- Syncer defers if a sweep is in progress to avoid simultaneous API load on underpowered hardware. Random 100-500ms delay between Radarr file batches and Sonarr series iterations.
- CF Score tab: stat cards in a single horizontal row (indexed, below cutoff, passing). Right card shows Last Synced, Scan Library, Sync Coverage as a flat scrollable list (instance name, percentage pill, counts), and Reset CF Index at the bottom. Left card has config fields and Save Changes. Items table supports search by title, filter by instance via dropdown, sortable columns, clickable titles (open in Radarr/Sonarr), pagination with Go to page, and no row cap — all indexed items available.
- Radarr and Sonarr app badges use `--accent` and `--ok` CSS variables consistently with the rest of the app.
- New config keys: `cf_score_enabled` (bool, default False), `cf_score_sync_hours` (int, default 24), `radarr_cf_max_per_run` (int, default 1), `sonarr_cf_max_per_run` (int, default 1).
- New DB table: `cf_score_entries`. Migration v11 creates it for existing installs. Fresh installs get it via `_SCHEMA_SQL`.
- New files: `nudgarr/db/cf_scores.py`, `nudgarr/cf_score_syncer.py`, `nudgarr/routes/cf_scores.py`, `nudgarr/templates/ui-tab-cf-scores.html`, `nudgarr/static/ui-cf-scores.js`.

**CF Score Per-Instance Override**

- `cf_max` (max CF Score searches per run) added as a per-instance override field. Appears in the CF Score group on each override card when CF Score is enabled globally. Hides entirely when CF Score is disabled globally since the syncer is global infrastructure and per-instance enable/disable is not supported.
- Override cards now show three distinct pipeline groups: Cutoff Unmet, Backlog, CF Score — each visually separated with a divider and group header.
- Backend: `_resolve()` used for `cf_max` in `sweep.py` so per-instance override values are respected at sweep time. Falls back to global `radarr_cf_max_per_run` or `sonarr_cf_max_per_run` when no override is set.

**Sweep Notifications — CF Score**

- Sweep notification message now includes CF Score in the per-instance breakdown when CF Score searches occurred. Format: `Radarr — 17 Searched (10 Cutoff, 5 Backlog, 2 CF Score)`. Each pipeline only appears in the detail string if it actually searched something that run. Total searched count includes all three pipelines.

**CF Score Sweep Logging**

- CF Score INFO log line now matches Cutoff Unmet granularity. Added `cf_score_total`, `skipped_cf_excluded`, and `skipped_cf_queued` counters alongside the existing `skipped_cf_cooldown`. Zero-eligible DEBUG log also includes all skip counters for easier diagnosis of why specific titles are not being searched.

**Cutoff Unmet Toggle (v4.2.0)**

- `radarr_cutoff_enabled` and `sonarr_cutoff_enabled` added as independent per-app toggles for the Cutoff Unmet pipeline. Both default to `True` so existing installs are unaffected.
- Settings tab updated with Radarr and Sonarr Cutoff Unmet sections, each with a toggle and greyed Max/Sample Mode fields when disabled. Matches Backlog layout in the Advanced tab.
- Max Per Run help text updated from "0 Disables" to "0 = All Eligible" for both Cutoff Unmet and Backlog fields. The toggle is now the on/off switch; 0 means all eligible items are nudged each run.
- `sweep.py` Cutoff Unmet filter chain wrapped in `if cutoff_enabled` guard. When disabled all counters remain 0, no items are fetched, and queue_ids are still fetched so Backlog and CF Score can skip items already downloading.
- `ui-sweep.js` Library State Cutoff Unmet cell greys with a dash when disabled, matching Backlog behaviour.
- `ui-overrides.js` Cutoff Unmet group fields grey when disabled globally, consistent with Backlog fields greying when Backlog is off.
- Migration: if `radarr_cutoff_enabled` or `sonarr_cutoff_enabled` is absent from config and the corresponding max is 0 (previously used as a disable mechanism), `validate_config` sets the toggle to `False` and resets max to 1 preserving the user's intent.
- Onboarding Step 2 updated — Cutoff Unmet described as "on by default" rather than "always active".

**Onboarding Walkthrough Rewrite**

- Reduced from 10 steps to 8. New structure: Welcome, How Nudgarr Works (new), Add Instances, Scheduler and Run Now, Search Behaviour and Throttling, Exclusions and Auto-Exclusion (new), Notifications and Intel, You're Ready.
- New "How Nudgarr Works" step introduces all three pipelines (Cutoff Unmet, Backlog, CF Score) as a natural progression before any configuration steps. Frames Nudgarr as nudging the Arrs rather than searching directly.
- Exclusions and Auto-Exclusion step added covering manual exclusions, auto-exclusion threshold, and Clear Exclusions.
- Intel tab introduced in Notifications step.
- All references to "Nudgarr searches" corrected to reflect that Nudgarr sends search commands to Radarr and Sonarr.
- Backfill renamed to Backlog throughout. Stats tab renamed to Imports throughout.
- Onboarding modal given fixed height (520px) with scrollable content area and pinned footer. Navigation buttons now stay at the same position regardless of step content length.

**Advanced Tab Layout Reorganisation**

- Left card now contains Backlog Nudges at the top and Auto-Exclusion at the bottom.
- Right card now contains For the Arr-tists and Pipelines at the top, followed by Data Retention, Stats, Security, and UI Preferences.
- Support & Diagnostics buttons (Backup All, Log Level, Download Diagnostic, Open Issue) now use a uniform 2×2 grid matching the Danger Zone layout so both bottom cards are visually consistent.
- Danger Zone buttons use `width:100%` so they fill their grid cells evenly.
- Reset Intel wrapped in a full `card` element for proper background treatment, matching the Support & Diagnostics / Danger Zone row pattern.

**Polish Fixes**

- Exclusions clear refresh bug: `confirmClearExclusions` now calls `PAGE = 0; refreshHistory()` after clearing so the history table updates immediately without requiring a tab switch.
- Exclusions filter pagination: when Exclusions filter is active, page size is now respected and pagination controls are shown. Previously all exclusions were shown regardless of the per-page setting.
- Reset Intel: description text removed — bare right-aligned button only, matching Reset CF Index pattern.
- Danger Zone: 2x2 grid layout matching the left card structure. Tooltip icon added next to the "Danger Zone" label explaining Clear Imports scope. Helper text below buttons removed.
- CF Score tab: right card now uses `flex-direction:column` so Reset CF Index stays pinned to the card footer and aligns vertically with Save Changes on the left card.
- Override cards: Notifications toggle row now has a `divider + grpHead('Notifications')` label above it, consistent with Cutoff Unmet, Backlog, and CF Score groups.

**Danger Zone Cleanup and Reset Button Relocation**

- Reset Intel moved from Advanced Danger Zone to the bottom of the Intel tab as a right-aligned button. Matches the Reset CF Index pattern on the CF Score tab — destructive action lives next to the data it affects.
- Reset Auto-Exclusions removed from Advanced Danger Zone entirely. Replaced by Clear Exclusions on the History tab (see below).
- Clear Stats renamed to Clear Imports throughout — button label, JS function (`clearStats` → `clearImports`), and confirmation popup title and body. The popup body now correctly references the Imports tab instead of the Stats tab.
- Danger Zone now contains four focused global actions: Clear History, Clear Imports, Clear Log, Reset Config. A help note below the buttons clarifies that Clear Imports removes import records only and Intel lifetime data is unaffected.

**Clear Exclusions — History Tab**

- New "Clear Exclusions" button added to the right of the History tab pagination row. Opens a modal with three radio options: Clear Auto-Exclusions (removes auto-excluded titles only), Clear Manual Exclusions (removes manually excluded titles only), Clear All Exclusions (removes all). Confirm button is disabled until an option is selected.
- Three new API endpoints added: `POST /api/exclusions/clear-manual`, `POST /api/exclusions/clear-all`. Existing `POST /api/exclusions/clear-auto` unchanged.
- Two new DB functions added: `clear_manual_exclusions()` and `clear_all_exclusions()`. Both follow the same pattern as `clear_auto_exclusions()`. `clear_all_exclusions()` logs unexcluded events for auto-exclusions so Intel calibration data is preserved.
- `openClearExclusionsModal`, `closeClearExclusionsModal`, `selectClearExclOption`, `confirmClearExclusions` added to `ui-history.js`. Dead `resetAutoExclusions` function removed from `ui-advanced.js`.

**Sweep Tab — CF Score Integration**

- Library State section renamed Backfill to Backlog and now shows three cells: Cutoff Unmet, Backlog, CF Score. CF Score cell shows the indexed item count from `cf_score_entries`. Backlog shows a dash when disabled globally. CF Score shows a dash when disabled globally. Both cells always render so the grid stays stable at 3 columns.
- This Run stats (Eligible, Searched, Cooldown, Capped) now roll up all three pipelines. Previously only Cutoff Unmet and Backlog were counted.
- Lifetime Searched accumulator now includes CF Score searches. `upsert_sweep_lifetime` updated to include `eligible_cf`, `skipped_cf_cooldown`, and `searched_cf` in the respective deltas.
- Sub-text capitalised consistently: In Library, Missing, In Index, In Scope, Triggered, Skipped, Over Limit.
- Sweep tab tooltips updated to describe all three pipelines.
- `stats-grid-3` CSS class added alongside `stats-grid-2` and `stats-grid-4`.

**Copy Fixes**

- What's New modal CF Score Scan card updated to correctly describe the feature as an independent pipeline that scans all monitored files regardless of quality tier. Removed stale reference to Radarr/Sonarr not surfacing these items via wanted/cutoff.
- Advanced tab CF Score Scan tooltip updated to match the corrected description.

**History and Imports — Go to Page**

- Prev/Next pagination row in History and Imports now includes a Go to page input and Go button for direct page navigation. Enter a page number and press Enter or click Go to jump directly.

**CF Score Table — Search, Instance Filter, Clickable Titles**

- Items table redesigned to match History tab conventions. Instance filter is now a dropdown matching History's All Instances pattern. Title search input added alongside it. Titles are clickable and open the item in Radarr or Sonarr (same `.arr-link` pattern as History — white at rest, accent blue on hover). Go to page added to pagination row. 200 row hard cap removed — all indexed items available across all pages.

**Advanced Tab — Pipelines Section**

- CF Score Scan toggle moved from For the Arr-tists to a new Pipelines section with its own divider and label. Per-Instance Overrides remains in For the Arr-tists. The separation reflects that CF Score is an independent search pipeline rather than a configuration modifier.

**Intel Import Split Fix**

- Pre-existing bug fixed: `cutoff_import_count` in `intel_aggregate` was always 0 because `_update_intel_on_confirm` checked `entry_type == "cutoff_unmet"` but the actual stored value is `"Upgraded"`. All confirmed imports were incorrectly counted as backlog imports regardless of which pipeline triggered them.
- Fixed by correcting the check to `entry_type == "Upgraded"` (Cutoff Unmet), `entry_type == "CF Score"` (CF Score Scan), and `else` for `"Acquired"` (Backlog) and any legacy types.
- `cf_score_import_count` added to `intel_aggregate` to track CF Score confirmed imports independently. Migration v12 adds the column for existing installs via `ALTER TABLE`. Import Breakdown in the Intel Search Health card updated from a two-way to a three-way split: Cutoff Unmet, Backlog, CF Score.

**Advanced Tab Restructure**

- Advanced tab pager removed. Page 1 (Backlog Nudges + For the Arr-tists) and Page 2 (Auto-Exclusion) are now visible simultaneously in the two-card layout without pagination.
- Auto-Exclusion moved from the left card Page 2 to the top of the right card. Right card now contains Auto-Exclusion, Data Retention, Stats, Security, and UI Preferences.
- Left card contains only Backlog Nudges and For the Arr-tists — a cleaner, shorter card that no longer requires scrolling past Backlog config to reach the feature toggles.
- For the Arr-tists section retains Per-Instance Overrides toggle. A new Pipelines section below it holds the CF Score Scan toggle — visually separated to reflect that CF Score is an independent search pipeline rather than a configuration modifier.
- `advSetPage()` function and all associated pager elements (`advPage1`, `advPage2`, `advPageNum`, `advPagerPrev`, `advPagerNext`) removed.

**Grace Period (Hours)**

- New per-app Grace Period (Hours) setting delays Nudgarr's first missing search for an item until at least the configured number of hours have elapsed since its release or availability date. Useful when indexers need time to populate after a release. 0 disables the filter — existing behaviour is preserved by default.
- Applies to both Radarr and Sonarr missing (backlog) pipelines independently. Does not affect Cutoff Unmet searches.
- New config keys: `radarr_missing_grace_hours` and `sonarr_missing_grace_hours`. Both default to 0.
- Advanced tab page 1 — Radarr backlog section gains a Grace Period (Hours) field in the second column of the Backlog Sample Mode row. Sonarr backlog section gains a Grace Period (Hours) field in a new row below Backlog Sample Mode.
- Overrides tab — Grace Period (Hours) added to both Radarr and Sonarr backlog field groups. Radarr: fills the previously empty cell next to Max Missing Days. Sonarr: new row with Grace Period on the left.
- Per-instance overrides supported — uses the same `_resolve()` path as all other override fields.
- Landscape Backlog tab — Grace Period (Hours) stepper added at the bottom of both Radarr and Sonarr backlog fields columns.
- Landscape Overrides panel — Grace Period (Hours) stepper added to the backlog fields grid for both apps.
- Backend: `_release_date()` helper in `sweep.py` checks `releaseDate`, `physicalRelease`, `digitalRelease`, `inCinemas`, `airDateUtc`, `airDate` in preference order. Items within the grace window are skipped with a per-item debug log entry. `skipped_missing_grace` counter added to the Radarr and Sonarr info log lines.

**Missing Max — 0 = All Eligible**

- Setting Missing Max (Per Instance) to 0 now means all eligible items are searched each run — previously 0 was treated as disabled and returned an empty pool. Help text updated to append `(0 = All Eligible)` for both Radarr and Sonarr on the Advanced tab and landscape Backlog tab.
- The backlog pipeline guard in `sweep.py` changed from `if backlog_enabled and missing_max > 0` to `if backlog_enabled` — backlog now runs when max is 0 and passes all eligible items.

**Newest Added Warning Removed**

- The conditional amber warning block on Advanced page 1 ("Newest Added is active and Radarr backlog nudges are enabled") has been removed along with its corresponding block in the Settings tab. The information it conveyed is covered by the Backlog Sample Mode tooltip.
- `checkNewestAddedWarning()`, `_newestAddedWarningActive()`, and `fadeNewestAddedWarnings()` removed from `ui-settings.js` along with all call sites across `ui-advanced.js`, `ui-tab-advanced.html`, and `ui-tab-settings.html`.

**Use With Caution Block Removed**

- The amber "USE WITH CAUTION" block on Advanced page 1 has been removed. Its content has been folded into the Missing Added Days tooltip where it belongs.

**Intel Tab**

- New Intel tab added between Imports and Notifications — a read-only lifetime performance dashboard that gets richer the longer Nudgarr has been running. Answers the question "how is Nudgarr performing for my library overall?" — distinct from the Sweep tab which covers the last run.
- Library Score: a single 0-100 composite score based on success rate (40%), turnaround (25%), stuck items (20%), and sweep efficiency (15%). Shows "Building…" on fresh installs until 10 confirmed imports or 30 sweep runs have accumulated.
- Search Health card: lifetime success rate, average turnaround, average searches per import, stuck item count, cutoff unmet vs backlog import split, quality upgrades confirmed.
- Instance Performance table: per-instance sweep runs, total searched, confirmed imports, success rate, average turnaround, eligible used bar, and stuck items.
- Stuck Items: titles searched at or above the auto-exclusion threshold with no confirmed import and not yet excluded — the only actionable card in Intel.
- Exclusion Intel: total exclusions, manual vs auto breakdown, average searches at auto-exclusion, auto-exclusions this month, and a calibration signal showing how many auto-excluded titles later imported after being given a second chance.
- Library Age vs Success: import success rate bucketed by how long items had been in the library at first search. Reveals long-tail content that indexers may not carry.
- Quality Iteration: titles imported once vs upgraded, most common upgrade path per app (Radarr and Sonarr shown separately).
- Sweep Efficiency: per-instance lifetime average of items searched vs eligible with a callout when an instance is consistently hitting its search cap.
- Reset Intel button added to the Danger Zone — clears `intel_aggregate` and `exclusion_events`. Clear History and Clear Stats do not affect Intel data.

**Sticky Header**

- Header (wordmark, status bar, Run Now) and tab bar now pin to the top of the viewport while tab content scrolls beneath. Applies to all tabs. Hidden on mobile where the fixed mobile nav takes over.

**Exclusion Event Tracking**

- New `exclusion_events` table — append-only audit log written at every exclude and unexclude action (manual or auto). Captures title, event type, source, search count at the moment of the event, and a timestamp. Never affected by Clear History, Clear Stats, or pruning.
- Powers the Intel calibration signal: tracks whether auto-excluded titles that later received a second chance (via auto-unexclude timer or manual deletion) eventually imported.

**Protected Aggregate**

- New `intel_aggregate` table — single-row accumulator that is written to at confirm time and never cleared by any normal operation. Protects Intel metrics from Clear History, Clear Stats, and retention pruning.
- Snapshot of `search_count` is taken at confirm time before any future auto-unexclude reset can affect it, ensuring searches-per-import is accurate even on installs with heavy auto-exclusion cycling.
- Migration v10 adds both new tables. Handles all existing installs upgrading to v4.2.0. Fresh installs receive both tables via `_SCHEMA_SQL`.

**Backlog Sample Mode Split**

- Cutoff Unmet and Backlog (missing) sweeps now have independent sample mode settings. Previously one sample mode applied to both pipelines.
- Two new global config keys: `radarr_backlog_sample_mode` and `sonarr_backlog_sample_mode`. Both default to Random.
- Advanced tab page 1 — Radarr backlog section gains a Backlog Sample Mode dropdown alongside Missing Max. Sonarr backlog section gains a Backlog Sample Mode dropdown alongside Missing Max. Options are Random, Alphabetical, Oldest Added, Newest Added. Quality gap modes are not available for backlog since missing items have no existing file to score against.
- Overrides tab — per-instance override cards restructured into two clear groups: Cutoff Unmet (Max + Sample Mode) and Backlog (toggle + Max + Backlog Sample Mode + Max Missing Days for Radarr). Cooldown sits above both groups as it applies to the full pipeline. Backlog Sample Mode follows the existing Use Global sentinel pattern.
- Backend — the backlog pipeline in `sweep.py` reads `backlog_sample_mode` independently from the cutoff `sample_mode`. Per-instance overrides support `backlog_sample_mode` with the same resolution logic as all other override fields.

**Maintenance Window**

- Scheduled sweeps can now be suppressed during a defined time window. Manual Run Now is never affected — suppression applies only to cron-triggered fires.
- Configure in Settings tab → Scheduler card, below the cron expression row. Toggle enables the feature and greys out all dependent fields when off.
- Time inputs use 24-hour HH:MM format. Overnight ranges are supported (e.g. 23:00 to 07:00 spanning midnight) — the window stays active until the configured end time regardless of the calendar day boundary.
- Day-of-week selectors are individual pill toggles (Mon through Sun). Default is no days selected — days must be deliberately chosen. If no days are selected the feature behaves as disabled regardless of the toggle state.
- The hint line below the time inputs describes the active window once both times and at least one day are valid, and flags overnight ranges explicitly.
- Backend — `_in_maintenance_window()` in `scheduler.py` handles both same-day and overnight range detection. Uses container local time via the `TZ` environment variable, consistent with cron evaluation.
- Suppressed sweeps log at INFO: `[Scheduler] Sweep suppressed by maintenance window (window: HH:MM to HH:MM, now: HH:MM)`.

**Backlog fields greying in Overrides**

- Desktop and mobile landscape override cards now grey out Max Backlog, Backlog Sample Mode, and Max Missing Days when the backlog toggle is off (resolved value, accounting for overrides). Fields ungrey immediately when backlog is enabled via override even if disabled globally. `updateBacklogLabel()` syncs the grey state live on toggle change.

**Non-destructive config validation**

- Config validation failure no longer wipes the entire config. Only the specific failing keys are identified and reset to their defaults individually. All other keys — instances, credentials, and all other settings — are preserved.

**Mobile**

- Portrait Settings tab — "Sample Mode" renamed to "Cutoff Sample Mode" on the Radarr and Sonarr cards. The segment control already wrote to `radarr_sample_mode` / `sonarr_sample_mode` (cutoff only) — the rename makes this explicit and distinguishes it from the new backlog mode.
- Portrait Home Automation card — Maintenance Window toggle added directly below Auto Schedule. Greys out when Auto Schedule is off. Sub-label reads "Select at least one day" in red when enabled with no days configured, matching desktop hint behaviour.
- Landscape Backlog tab — Radarr and Sonarr backlog fields each gain a Backlog Sample Mode dropdown at the bottom of their fields div. Inherits the existing backlog fields greying when backlog is disabled.
- Landscape Execution tab — Maintenance Window added as a full-width band below the two-column grid. Three sub-columns: Suppress Sweeps toggle; Hours (24h) with start and end text inputs; Active Days with Mon through Sun pill toggles. Live hint line matches desktop format exactly.
- Landscape Overrides panel — rebuilt to match desktop layout and feature parity. Order: Cooldown (full width) → Cutoff Unmet group (Max + Sample Mode) → Backlog group (toggle + Max Backlog + Backlog Sample Mode + Max Missing Days) → Notifications. Group headers added. Backlog Sample Mode was previously missing entirely.
- Desktop View bug fix — tapping Desktop View in landscape mode now correctly shows the full desktop header and tab nav.
- Mobile View button — a subtle ghost button ("◱ Mobile") appears in the desktop header when the desktop override is active, allowing return to the mobile UI without rotating the device. Hidden on all non-override loads via CSS.
- Maintenance window hint format — landscape hint now matches desktop exactly: `HH:MM to HH:MM (overnight) on Mon, Wed, Fri`.

**Minor improvements**

- Advanced tab — "Radarr Missing Added Days" label corrected to "Missing Added Days".
- Advanced tab — help text standardised: "Only search missing items older than this many days (0 = No Age Filter)".
- Backup JSON export (`/api/file/state`) now includes `exclusion_events` and `intel_aggregate` sections. The primary backup (`/api/file/backup`) already included full database coverage as it packages the raw SQLite file directly.
- `db/backup.py` docstring updated to reflect the complete export structure.
- Intel tab unit labels capitalised — Days, Searches, Items, Upgrades throughout all cards and the instance table.

**Sweep Tab Redesign**

- Complete rewrite of the Sweep tab from per-instance cards to a three-row grid layout.
- Row 1 — Pipeline cards: three side-by-side cards (Cutoff Unmet, Backlog, CF Score), each showing aggregate totals and per-instance breakdowns. Cutoff Unmet shows six aggregate cells: Searched, Cooldown, Capped, Excluded, Tag, Profile. Backlog shows six aggregate cells: Searched, Cooldown, Capped, Grace, Tag, Profile. CF Score shows four aggregate cells: Searched, Cooldown, Excluded, Queued. Tag and Profile are not shown for CF Score — they are enforced at sync time, not sweep time. Each card has per-instance rows showing Searched, Cooldown, and Excl per enabled instance and a Disabled badge for disabled instances.
- Row 2 — Summary cards: Sweep Health (all-healthy banner vs. failed-instance error banner with Lifetime Runs, Avg Per Run, Last Error, and Instances counts), Last Sweep (Completed, Next Run, Lifetime Runs, Lifetime Searched as a 2x2 grid), Imports Confirmed (total with Movies/Episodes breakdown, or zero-state). Imports Confirmed reads `imports_confirmed_sweep` from STATUS — no extra API call at render time.
- Row 3 — Sweep Feed: full-width paginated table showing all items searched in the current sweep (Title, Instance, Time, Pipeline badge). Powered by `/api/state/items?since=<last_sweep_start_utc>`. Pipeline badges use `.sw-pill` (scoped class) to avoid colliding with the existing `.pill` tag/filter pills in the Filters tab. Pagination is 10/25/50/100 per page, wired into the existing `syncPageSize` mechanism so all three paginated tables (History, Imports, Sweep feed) stay in sync. Go to page included.
- Pipeline row uses a nested sub-grid (`grid-column: 1/-1` + `display: grid`) so the loading placeholder always occupies the full top band and summary cards are always anchored to row 2.
- `globals.py` — STATUS gains `last_sweep_start_utc` (ISO UTC written just before `run_sweep()` fires), `imports_confirmed_sweep` (`{movies: N, shows: N}` written after each sweep), and `cf_filters_changed` (bool, set by `ui-filters.js` when tag or profile filters are saved with CF Score enabled).
- `db/entries.py` — `get_imports_since(since_utc)` counts confirmed imports since a given UTC timestamp grouped by app. Returns `{movies: N, shows: N}`.
- `db/history.py` — `get_search_history()` gains an optional `since` parameter. When set, adds `sh.last_searched_ts >= ?` to the WHERE clause so the sweep feed only fetches rows from the current sweep window.
- `routes/state.py` — `/api/state/items` passes the `since` query param through to `get_search_history()`.
- `scheduler.py` — writes `STATUS["last_sweep_start_utc"]` immediately before `run_sweep()`; populates `STATUS["imports_confirmed_sweep"]` via `get_imports_since()` after a successful sweep.
- `sweep.py` — `skipped_tag` and `skipped_profile` were previously shared accumulator variables across both the Cutoff Unmet and Backlog pipelines. Split into four independent fields: `skipped_tag_cutoff`, `skipped_profile_cutoff`, `skipped_tag_backlog`, `skipped_profile_backlog`. Added `skipped_excluded_cutoff` (items dropped by the exclusion list in the Cutoff Unmet pipeline) and `skipped_grace` to the per-instance result dict. All six new fields present in the result dict stored in `STATUS["last_summary"]`.
- `ui-core.js` — `SWEEP_FEED_PAGE` and `SWEEP_FEED_TOTAL` added as shared state vars. `syncPageSize()` extended from a two-participant function (History / Imports) to a three-participant function (History / Imports / Sweep feed) keyed on `sweepFeedLimit`.

**CF Filter Sync Warning Modal**

- When a Filters tab save changes `excluded_tags` or `excluded_profiles` for any instance and CF Score is enabled globally, a warning modal appears: "CF Score Index Out of Sync". Two actions: Later (dismiss) and Sync Now (closes modal and triggers `triggerCfSync()`). Amber-bordered modal.
- `closeCfFilterSyncModal()` and `syncCfIndexFromModal()` handlers added to `ui-filters.js`. Modal HTML added to `ui-modals.html`.

**Settings Tab — Cooldown Relocation**

- Cooldown field moved from the Search Behaviour card into the Scheduler card, placed after the Maintenance Window section with a divider. Cooldown belongs alongside scheduler configuration as it directly controls how the scheduler spaces repeated searches.
- The Search Behaviour card is removed entirely. Cutoff Unmet now has the full right card to itself.
- Cooldown help text updated from "0 Disables" to "0 = No Cooldown" in both the static HTML and the `_COOLDOWN_HELP_DEFAULT` JS constant.
- Onboarding step 3 title updated from "Search Behaviour and Throttling" to "Cutoff Unmet and Throttling".

**Responsive Desktop UI — Mobile UI Removal**

- The dedicated mobile UI (portrait and landscape) has been replaced with a fully responsive desktop UI that works on any screen size. All features are now accessible on mobile — the CF Score tab, Intel tab, Overrides, and every configuration field are no longer desktop-only.
- `ui-responsive.css` added as a new static file containing only `@media` blocks. `ui.css` is never modified — the responsive layer is the sole responsive surface.
- At 720px: sweep pipeline grid stacks to single column, `intel-grid-score` stacks, History, Imports, and CF Score table wrappers get `overflow-x: auto` with a sticky first column, sweep feed table wrapped in a scrollable div, CF Score filter controls realign from right-anchored to full-width.
- At 480px: tab bar switches from wrapping to horizontal scroll with a right-fade hint, wrap padding tightened, Last and Next run segments hidden from the status bar, pipeline aggregate cells reflow (6-col to 3-col, 4-col to 2-col), Advanced auto-exclusion grid stacks from 2-col to 1-col.
- 11 files removed: `ui-mobile.html`, `ui-mobile.css`, `ui-landscape.css`, `ui-mobile-core.js`, `ui-mobile-portrait.js`, `ui-mobile-portrait-home.js`, `ui-mobile-portrait-history.js`, `ui-mobile-portrait-settings.js`, `ui-mobile-landscape.js`, `ui-mobile-landscape-exec.js`, `ui-mobile-landscape-filters.js`. Net reduction of approximately 3,700 lines.
- `ui-core.js` — `MOBILE` constant and `if (!MOBILE)` desktop init guard removed. Desktop init and poll cycle now run unconditionally on all clients.
- `ui-header.html` — Mobile view button removed.
- `validate.py` and `tests/test_frontend_structure.py` updated to reflect the removed files, removed mobile function and element checks, and removed `MOBILE` const and guard checks.

---

## v4.1.0


**Auto-exclusion and import stats period toggle.**

**Auto-Exclusion**

- Titles searched N times with no confirmed import are automatically excluded from future sweeps. Configure independently for Radarr (movies) and Sonarr (shows) in Advanced → page 2.
- Four new Advanced fields: Exclude After X Searches (Radarr), Exclude After X Searches (Sonarr), Unexclude After X Days (Radarr), Unexclude After X Days (Sonarr). All default to 0 (disabled).
- Setting a threshold to 0 greys out the corresponding unexclude field for that app.
- Auto-unexclude pass runs at sweep start — titles older than the configured threshold are removed from exclusions before the pipeline runs, making them eligible again immediately.
- Auto-exclusion check runs inside the import check loop after each cycle. Four conditions must all be true: search count meets the threshold, no confirmed import on record, title not currently in the download queue, title not already excluded. The queue check protects against excluding items that were just grabbed and are still downloading.
- Exclusions tab gains Source (Manual / Auto) and Excluded On columns when the exclusions filter is active. Auto entries show an amber Auto badge; manual entries show a muted Manual badge.
- Status bar gains a new leftmost segment showing the count of unacknowledged auto-exclusions. Clicking navigates to the History tab with the exclusions filter active and clears the badge.
- Saving Advanced with a threshold changing from non-zero to 0 fires a dynamic popup showing current auto-exclusion counts. Keep leaves them in place; Clear removes all auto-exclusion rows. Both choices auto-save without a second click.
- Reset Auto-Exclusions button added to the Danger Zone — removes all auto-exclusion rows in one action. Manual exclusions are never affected.
- Separate Apprise notification trigger: Auto-Exclusion. Toggle visible in the Notifications tab between Import Confirmed and Error.
- Migration v9 adds `source`, `search_count`, and `acknowledged` columns to the exclusions table. Existing rows default to `source=manual`, `search_count=0`, `acknowledged=1`.

**Import Stats Period Toggle**

- The Lifetime Confirmed label on the Imports tab stats card is now a period selector: Lifetime / Last 30 Days / Last 7 Days.
- Changing the period updates the Movies and Episodes counts immediately with a fade animation.
- Selection persists across page refreshes via localStorage.
- Lifetime uses the protected `lifetime_totals` table and survives Clear Stats. Last 30 Days and Last 7 Days are rolling windows calculated from `stat_entries` and reflect any clears.
- Tooltip updated to explain the rolling window behaviour and the persistence distinction.

---

**Logging improvements, notification visibility, dependency pinning, and mobile zoom support.**

- Log timestamps now reflect container local time (controlled by the `TZ` environment variable) instead of UTC, matching the time displayed in the scheduler. Both stdout and the rotating log file use local time.
- Notification logging — `send_notification` now uses `logger.debug` on successful send, `logger.warning` on failure, and `logger.debug` on no-op skips (disabled, no URL, nothing searched). Bare `print()` calls removed throughout `notifications.py`. Full notification visibility in DEBUG log.
- `notify_sweep_complete` logs a DEBUG line for each skipped instance (notifications disabled or nothing searched) so the reason is always visible in the log.
- Startup logging — config load summary logged at INFO on startup (`Config loaded — N Radarr, N Sonarr instances`); startup health ping results now include the arr app version on success and clearly label disabled instances; log lines use consistent `[app:name] startup ping — ok (vX.Y.Z)` format.
- Import check loop now logs a DEBUG line per instance showing how many pending entries were checked and how many were confirmed (`[Stats] [radarr:Radarr] import check — checked 12 events, 2 confirmed`).
- Scheduler now logs a DEBUG line when a sweep is skipped because `RUN_LOCK` is already held (`Sweep skipped — RUN_LOCK already held`), making it clear why Run Now appeared to do nothing.
- `requirements.txt` added with pinned versions of all dependencies — `flask`, `requests`, `apprise`, `croniter`. Dockerfile updated to install from `requirements.txt` instead of inline package names, ensuring reproducible builds.
- Mobile pinch zoom enabled — viewport meta tag updated to `user-scalable=yes` and `maximum-scale=5`. Both iOS and Android can now zoom in and out. Page loads at correct scale on all devices.

**Mobile Auto-Exclusion**

- Portrait Settings tab — Radarr and Sonarr cards each gain two new steppers: Auto-Exclude (searches before auto-exclude, 0 = off) and Unexclude Days (days before re-eligible, 0 = never). Unexclude Days row greys immediately when the paired threshold is 0, matching desktop `syncAutoExclUi()` behaviour.
- Stepping a threshold to 0 with existing auto-exclusions present fires the Auto-Exclusion Disabled popup — Keep leaves all entries in place; Clear removes them. Uses the existing `m-sheet-auto` modal pattern. Body text uses combined total with neutral "title(s)" label since clearing is a global action across all apps.
- Notifications card gains a fourth toggle — Auto-Exclusion — between Import Confirmed and Error, matching desktop order and `notify_on_auto_exclusion` in config.
- Home tab gains a notification row below Run Now that shows "N New Auto-Exclusion(s)" when unacknowledged auto-exclusions exist, replacing the hint text. Tapping navigates directly to the History Excluded inner tab and acknowledges all entries, clearing the row. Desktop status bar badge clears on its next poll since the acknowledged flag is shared in the database.
- Excluded tab: auto-excluded titles render in amber (`#fbbf24`) via `.m-hist-title-auto`, matching the desktop `.source-badge.auto` colour. Manual exclusions remain `--text-dim`.
- Notification row also refreshes after any exclusion is manually removed via `mExclRemove`.
- New CSS rules added to `ui-mobile.css`: `.m-autoexcl-row`, `.m-modal-btn-neutral`, `.m-modal-btn-danger`, `.m-hist-title-auto`.

**Bug fixes**

- History tab Eligible Again column now shows a calculated date for auto-excluded titles when Unexclude Days is above 0 (`excluded_at + unexclude_days`). Previously showed `—` for all excluded titles regardless of source or unexclude config. Manual exclusions and auto-exclusions with Unexclude Days = 0 continue to show `—`. Date recalculates from live config on every history refresh so changing the Unexclude Days field updates the column immediately after saving.

**Under the Hood**

- Frontend split into focused single-responsibility files — `ui-settings.js` split into `ui-settings.js`, `ui-notifications.js`, and `ui-advanced.js`; `ui-mobile-landscape.js` split into `ui-mobile-landscape.js` (Overrides) and `ui-mobile-landscape-filters.js` (Filters); `ui-sweep.js` split into `ui-sweep.js` (Sweep + Run Now), `ui-history.js` (History + Exclusions), and `ui-imports.js` (Imports)
- `ui.html` reduced from 1,481 lines to a 61-line shell — all tab sections, modals, and the mobile/landscape UI block extracted into dedicated template partials (`ui-header.html`, `ui-nav.html`, `ui-tab-*.html`, `ui-modals.html`, `ui-mobile.html`) loaded via Jinja2 `{% include %}`
- `sweep.py` consolidated — `_sweep_radarr_instance` and `_sweep_sonarr_instance` merged into a single `_sweep_instance` helper parameterised on app type; `run_sweep` loop unified across both apps
- Shared `cronIntervalMinutes()` moved to `ui-core.js` — previously duplicated independently in `ui-settings.js` and `ui-mobile-landscape-exec.js`
- `mSaveCfgKeys()` moved to `ui-mobile-core.js` alongside other shared mobile helpers; `typeof` guard removed since function now loads before all call sites
- Inline styles replaced with named CSS classes throughout JS render functions — `ui.css` gains `.sweep-disabled-badge`, `.count-pill`, `.iter-pill`, `.eligible-next-sweep`, `.td-*` table cell helpers, and full upgrade tooltip anatomy; `ui-mobile.css` gains `.m-inst-pill`, `.m-count-pill`, `.m-type-badge`, `.m-excl-inline`, and related import row helpers
- Dead code removed — `record_stat_entry()` wrapper in `stats.py`, `upsert_search_history()` and `get_last_searched_ts()` in `db/history.py` (both superseded by batch variants), `get_sweep_lifetime_row()` in `db/lifetime.py`, unused `state` parameter on `prune_state_by_retention()` in `state.py`, `mCloseExclusions()` empty stub, and orphaned `m-excl-sheet` HTML block
- `validate.py` updated to load template partials into combined content for all HTML checks; `html_lines` rebuilt from the rendered skeleton for wrap/mobile-ui nesting checks
- `tests/test_frontend_structure.py` added — 110-test pytest suite covering file existence, HTML links, script load order, line count ceilings, duplicate function detection, onclick resolution, element ID resolution, shared state location, load order safety, split integrity, and validate.py passthrough
- Pagination cap removed from `arr_clients.py` — `_radarr_movies_from_wanted` and `_sonarr_episodes_from_wanted` previously capped at 500 items regardless of library size. All four public fetch functions now paginate until the API returns an empty page. Default `page_size` raised from 100 to 500 to reduce API round-trips for large libraries. All sample modes now operate on the full library unconditionally.
- Graceful SIGTERM shutdown — `stop_flag` dict replaced with `threading.Event` across `main.py` and `scheduler.py`. Signal handler logs the received signal name and sets the event. The import check thread is joined with a 10-second timeout before process exit, allowing an in-progress sweep to finish naturally on `docker stop`.
- Cache-busting added to all static file URLs — all 21 CSS and JS references in `ui.html` now include `?v={{ VERSION }}` via Flask's `url_for` keyword argument pattern. Browsers treat each version as a distinct resource and serve fresh files automatically after a container upgrade without requiring a hard reload.
- Contributor commenting pass — all new and split files gained function-level docstrings, ownership headers, and cross-file navigation comments. Stale function references removed from module docstrings in `stats.py`, `db/history.py`, and `db/lifetime.py`.
- Waitress production WSGI server added — replaces Flask's development server. `waitress==3.0.2` added to `requirements.txt`. Configured at 4 threads, sufficient for Nudgarr's single-user workload. Falls back to Flask development server with a warning if Waitress is not installed.
- CI element ID check fixed — the check previously read only `ui.html` to find element IDs. After the template split, all IDs live in partial files. Updated to glob all `nudgarr/templates/*.html` files, matching how `validate.py` handles the same check. 197 el() calls now verified correctly.

---

## v4.0.0

**Quality upgrade tracking, tag and profile filtering, structured logging, mobile redesign, and a full backend and frontend restructure.**

**Bug fixes (post-release)**

- Clear Log — new button in Advanced → Danger Zone truncates the active `nudgarr.log` to zero bytes; rotation backups are unaffected; the log resumes writing immediately on the next sweep; confirm dialog matches Clear History and Clear Stats style

- Filters tab — instance pill now renders instance name with dot inside; dot colour reflects enabled state correctly; disabled instances no longer appear in the instance selector; card border turns amber on pending changes; Apply button correctly right-aligned with centred status text; pending changes trigger a proceed/cancel dialog when navigating away from the tab; loading tags and profiles for the second instance of a kind now works correctly (dropdown option values previously used position within the enabled list rather than the real config index); Load/Refresh button no longer stays permanently disabled after a successful load — clicking Refresh now correctly re-fetches from the arr instance
- Filters tab — cards are now fixed height (520px) so Radarr and Sonarr boxes always align; tags and profiles each occupy equal flex space within the card with independent scrolling; instances with no tags show a "No tags configured" message without affecting card height
- Overrides desktop — card pill now renders instance name with dot inside, removing the redundant separate name text
- Overrides landscape — stray `—` removed from panel header area; panel body now scrolls when content exceeds viewport height so Max Backlog and Max Missing Days are always reachable; rail updated to new accent pill style matching Filters rail
- Filters landscape — panel now correctly fills the right column alongside the rail; tags and profiles rendered in a two-column grid (tags left, profiles right) with each column as a flex container so lists stretch to fill available height and scroll independently; filter count chip updated to accent pill style
- Sweep logging — queue-filtered items now logged at DEBUG level for all four pipeline locations (Radarr cutoff, Radarr backlog, Sonarr cutoff, Sonarr backlog) with `skipped_queued` and `skipped_queued (backlog)` labels matching the existing tag and profile convention; `skipped_queued` and `skipped_not_available` counts added to the Radarr cutoff INFO summary line; `skipped_queued` added to the Sonarr cutoff INFO summary line
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

// ── Settings tab and modal logic ───────────────────────────────────────────
// Owns: Onboarding walkthrough, tab switching (_doShowTab, _onTabShown), Settings
// form (scheduler, cron, cooldown, sample mode, batch/sleep/jitter), cron
// validation (validateCronExpr, describeCron), cooldown and newest-added warnings,
// What's New modal, and support-link sync.
// Notifications tab logic lives in ui-notifications.js.
// Advanced tab logic lives in ui-advanced.js.
const ONBOARDING_STEPS = [
  {
    title: "Welcome to Nudgarr",
    body: `Nudgarr searches your Radarr and Sonarr Wanted lists automatically — finding items that need a quality upgrade or haven't been grabbed yet — so you don't have to.
<br><br>
This quick walkthrough covers the key things to know before your first run. It is key to understand these settings to prevent an indexer ban.`
  },
  {
    title: "Step 1 — Add Your Instances",
    body: `Start on the <strong>Instances tab</strong>. Add each of your Radarr and Sonarr servers with their URL and API key.
<br><br>
You can add multiple instances — Nudgarr will search across all of them each run. Note that settings like Max Per Run apply <strong>per instance</strong> — if you have two Radarr instances set to 5, that's up to 10 movie searches per sweep. Use the <strong>Test Connections</strong> button to confirm everything is connected before moving on.
<br><br>
<span style="display:block;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1);border-radius:8px;padding:9px 12px;font-size:12px;color:var(--muted);line-height:1.6">On mobile, instance management requires a desktop browser. Once your instances are configured you can monitor and enable/disable them from the Home screen.</span>`
  },
  {
    title: "Step 2 — Scheduler",
    body: `The Scheduler controls when Nudgarr automatically runs sweeps.
<br><br>
<strong>Automatic Sweeps</strong><br>
Off by default — Nudgarr will not run until you enable it. You can still trigger a sweep at any time by clicking <strong>Run Now</strong>. This is the recommended approach until you are confident in your settings.
<br><br>
<strong>Cron Schedule</strong><br>
Controls when the scheduler fires. Default is <code>0 */6 * * *</code> — every 6 hours on the clock. Cron fires in container time. Set the <code>TZ</code> environment variable if you want schedules to follow a specific timezone — if unset or unresolvable, Nudgarr falls back to UTC. Start conservative and adjust based on your library size and how active your indexers are.`
  },
  {
    title: "Step 3 — Search Behavior",
    body: `These settings control what gets searched and how often.
<br><br>
<strong>Max Per Run</strong><br>
How many items are searched <strong>per instance</strong> each run. If you have two Radarr instances set to 5, that's up to 10 movie searches per sweep. Starts at 1 — increase slowly as you get comfortable with how Nudgarr behaves.
<br><br>
<strong>Cooldown</strong><br>
How long Nudgarr waits before searching the same item again. Default is 48 hours. Do not lower this aggressively — repeated searches for the same item in a short window is one of the fastest ways to get banned from an indexer.
<br><br>
<strong>Sample Mode</strong><br>
Controls which eligible items are picked each run. <strong>Random</strong> gives even library coverage. <strong>Alphabetical</strong> works through your library from A to Z. <strong>Oldest Added</strong> prioritises items you've had longest. <strong>Newest Added</strong> targets recently added items — use with caution if backlog nudges are enabled.`
  },
  {
    title: "Step 4 — Throttling",
    body: `These settings control how fast Nudgarr communicates with your Radarr and Sonarr instances during a run.
<br><br>
<strong>Batch Size</strong><br>
How many search commands are sent at once. Default is 1. Keeping this low reduces the chance of overwhelming your indexer.
<br><br>
<strong>Sleep</strong><br>
How long Nudgarr pauses between batches. Default is 5 seconds. A longer pause is more respectful of your indexer's rate limits.
<br><br>
<strong>Jitter</strong><br>
Adds a small random delay on top of the sleep time to make search patterns less predictable. Helps avoid triggering automated rate limit detection.`
  },
  {
    title: "Step 5 — History & Imports",
    body: `Nudgarr keeps track of everything it does so you can see exactly what's happening.
<br><br>
<strong>History</strong><br>
A log of every item that has been searched, when it was last searched, and how many times. Use this to verify Nudgarr is behaving as expected after your first few runs.
<br><br>
<strong>Imports</strong><br>
Tracks confirmed imports — items that were searched by Nudgarr and later successfully downloaded. Movies and Episodes totals are lifetime counters that persist even if you clear the imports table. Items that have been through multiple upgrade cycles show a ×2, ×3 badge, and turnaround tracks how long from first search to confirmed import.
<br><br>
Both tabs support <strong>title search</strong> — type a show or movie name to filter the table instantly. Use the instance dropdown alongside it to narrow results further.`
  },
  {
    title: "Step 6 — Notifications",
    body: `Nudgarr can notify you when sweeps complete, imports are confirmed, or an instance becomes unreachable.
<br><br>
Add your Apprise-compatible URL, choose which events to be notified on, and use <strong>Send Test</strong> to confirm it's working before enabling. Supports Discord, Gotify, Ntfy, Pushover, Slack, and more.`
  },
  {
    title: "Step 7 — Advanced & Backlog Nudges",
    body: `The <strong>Advanced tab</strong> contains settings for backlog nudges, data retention, and security.
<br><br>
<strong>Backlog Nudges</strong> — Off by default. When enabled, searches for missing movies and episodes that have never been grabbed, going beyond just cutoff upgrades.<br><br>
<strong>Missing Max (Per Instance)</strong> — How many missing items to search per instance per run. Keep this low.<br><br>
<strong>Missing Added Days</strong> — Only search for items added to your library at least this many days ago. Prevents searching for things you just added and are still expecting to arrive naturally.<br><br>
<strong>Data Retention</strong> — How many days Nudgarr keeps history and stats entries before pruning. Lifetime totals are never affected. Default is 180 days.<br><br>
<strong>Import Check</strong> — Nudgarr periodically checks whether items it previously searched were successfully imported into your library. This is what feeds the Stats screen. Default is every 120 minutes.<br><br>
<strong>Security</strong> — Session timeout controls how long before an inactive login is automatically signed out. Default is 30 minutes.
<br><br>
⚠️ <span style="color:#fbbf24;font-weight:600">Backlog nudges can generate a lot of searches very quickly.</span> Start with a low cap and watch your indexer's rate limits carefully.`
  },
  {
    title: "Step 8 — Reading Your Sweep Stats",
    body: `The Sweep tab is your feedback loop — it shows you exactly what happened each run so you can tune Nudgarr to work best for your setup.
<br><br>
<strong style="font-size:9px;letter-spacing:.08em;text-transform:uppercase;color:#5b72f5">Library State</strong><br>
Cutoff Unmet and Backfill reflect the current state of your library as reported by your Radarr and Sonarr instances. They update as your library changes — not as a direct result of sweeps.
<br><br>
<strong style="font-size:9px;letter-spacing:.08em;text-transform:uppercase;color:#5b72f5">This Run</strong><br>
<strong>Eligible</strong> — how many items were ready to search this run. If this is consistently low your cooldown may be too long.<br><br>
<strong>On Cooldown</strong> — items that were found but aren't ready yet. This is normal and healthy — it means the system is pacing itself.<br><br>
<strong>Capped</strong> — items that were eligible but didn't get searched because the per-run cap was reached. If this is consistently high consider raising your Max Per Run gradually.<br><br>
<strong>Searched</strong> — what actually happened this run. This is your output.
<br><br>
<span style="color:var(--muted);font-size:12px">The defaults are intentionally conservative. Use these numbers over time to tune gradually — small increases to Max Per Run or small decreases to cooldown can make a meaningful difference.</span>
<br><br>
<span class="callout-text">These numbers are informational. If you increase Max Per Run or reduce cooldown, do so gradually and monitor your indexer activity closely. Nudgarr has no visibility into your indexer's limits.</span>`
  },
  {
    title: "You're Ready",
    body: `You're all set. Here's the recommended way to start:
<br><br>
1. Add your instances and test connections<br>
2. Review your settings — keep them conservative to start<br>
3. Hit <strong>Run Now</strong> to trigger your first sweep manually<br>
4. Check the <strong>History tab</strong> to see what was searched<br>
5. If everything looks right, enable the scheduler<br>
6. Gradually increase Max Per Run as you get comfortable
<br><br>
Nudgarr is designed to work quietly in the background — not to hammer your indexers. Start slow and let it earn your trust.
<br><br>
<span style="color:var(--muted);font-size:12px">If Nudgarr is useful to you, the 🍺 support link in the header is a nice way to say thanks. You can hide it anytime in Advanced → UI Preferences.</span>`
  }
];

let _obStep = 0;

function renderOnboardingStep() {
  const step = ONBOARDING_STEPS[_obStep];
  const total = ONBOARDING_STEPS.length;
  el('onboardingContent').innerHTML = `
    <h2 style="font-size:16px;font-weight:700;margin:0 0 12px">${step.title}</h2>
    <p class="help" style="line-height:1.7;margin:0">${step.body}</p>
  `;
  // Dots
  el('onboardingDots').innerHTML = ONBOARDING_STEPS.map((_, i) =>
    `<div style="width:7px;height:7px;border-radius:50%;background:${i===_obStep ? 'var(--accent)' : 'var(--border)'}"></div>`
  ).join('');
  el('onboardingPrev').style.display = _obStep === 0 ? 'none' : '';
  el('onboardingNext').textContent = _obStep === total - 1 ? 'Continue' : 'Next';
}

async function onboardingStep(dir) {
  const total = ONBOARDING_STEPS.length;
  if (dir === 1 && _obStep === total - 1) {
    // Finished
    el('onboardingModal').style.display = 'none';
    await api('/api/onboarding/complete', {method: 'POST'});
    if (CFG) { CFG.onboarding_complete = true; CFG.last_seen_version = el('ver').textContent; }
    return;
  }
  _obStep = Math.max(0, Math.min(total - 1, _obStep + dir));
  renderOnboardingStep();
}

function maybeShowOnboarding() {
  if (!CFG || CFG.onboarding_complete) return;
  _obStep = 0;
  renderOnboardingStep();
  el('onboardingModal').style.display = 'flex';
}

function replayOnboarding() {
  _obStep = 0;
  renderOnboardingStep();
  el('onboardingModal').style.display = 'flex';
}

function showTab(name) {
  // Overrides tab — check for pending (dirty) cards before navigating away
  if (ACTIVE_TAB === 'overrides' && name !== 'overrides') {
    const dirty = document.querySelectorAll('#overrides-grid .ov-card.ov-dirty');
    if (dirty.length) {
      const names = Array.from(dirty).map(c => c.dataset.name).filter(Boolean).join(', ');
      showConfirm(
        'Pending Changes',
        `You have unapplied changes on: ${names}. Proceed without applying?`,
        'Proceed'
      ).then(ok => { if (ok) _doShowTab(name); });
      return;
    }
  }
  // Filters tab — check for pending changes before navigating away
  if (ACTIVE_TAB === 'filters' && name !== 'filters') {
    if (typeof _filterHasPending === 'function' && _filterHasPending()) {
      showConfirm(
        'Pending Changes',
        'You have unapplied filter changes. Proceed without applying?',
        'Proceed'
      ).then(ok => { if (ok) _doShowTab(name); });
      return;
    }
  }
  _doShowTab(name);
}

function _doShowTab(name) {
  // Sweep tab — if no instances configured, show modal instead
  if (name === 'sweep') {
    const radarr = CFG?.instances?.radarr || [];
    const sonarr = CFG?.instances?.sonarr || [];
    if (!radarr.length && !sonarr.length) {
      showSweepNoInstancesModal();
      return;
    }
  }
  ACTIVE_TAB = name;
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
  const current = document.querySelector('.section.active');
  const next = document.getElementById('tab-' + name);
  if (current && current !== next) {
    current.classList.add('leaving');
    setTimeout(() => {
      current.classList.remove('active', 'leaving');
      next.classList.add('active');
      _onTabShown(name);
    }, 100);
  } else {
    document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
    next.classList.add('active');
    _onTabShown(name);
  }
}

// _onTabShown — called after every tab transition. Handles tab-specific side effects:
// resets history sort state and exclusion filter on re-entry, lazily initialises
// empty table skeletons before the first data fetch, routes data refreshes to the
// correct function (refreshHistory, refreshImports, refreshSweep), and re-syncs
// form fields for Advanced and Notifications if they have no pending unsaved changes.
function _onTabShown(name) {
  // Reset header support pill to saved state on every tab switch
  const sl = el('supportLink');
  if (sl && CFG) sl.style.display = CFG.show_support_link !== false ? 'inline-flex' : 'none';

  if (name === 'history') {
    HISTORY_SORT = { col: 'last_searched', dir: 'desc' };
    if (!EXCL_FILTER_ACTIVE) {
      const pill = el('exclusionsPill'); if (pill) pill.classList.remove('active');
    }
    clearHistorySearch();
    if (!el('historyTableWrap').querySelector('table')) {
      el('historyTableWrap').innerHTML = `
        <table><thead><tr>
          <th class="sortable ${HISTORY_SORT.col==='title' ? 'sort-'+HISTORY_SORT.dir : ''}" data-col="title" onclick="sortHistory('title')">Title</th>
          <th class="excl-col"></th>
          <th class="sortable ${HISTORY_SORT.col==='sweep_type' ? 'sort-'+HISTORY_SORT.dir : ''}" data-col="sweep_type" onclick="sortHistory('sweep_type')">Type</th>
          <th class="sortable ${HISTORY_SORT.col==='last_searched' ? 'sort-'+HISTORY_SORT.dir : ''}" data-col="last_searched" onclick="sortHistory('last_searched')">Last Searched</th>
          <th class="sortable ${HISTORY_SORT.col==='eligible_again' ? 'sort-'+HISTORY_SORT.dir : ''}" data-col="eligible_again" onclick="sortHistory('eligible_again')">Eligible Again</th>
        </tr></thead><tbody></tbody></table>`;
    }
    refreshHistory();
  }
  if (name === 'imports') {
    clearImportsSearch();
    if (!el('importsTableWrap').querySelector('table')) {
      el('importsTableWrap').innerHTML = `
        <table><thead><tr>
          <th class="sortable ${IMPORTS_SORT.col==='title' ? 'sort-'+IMPORTS_SORT.dir : ''}" data-col="title" onclick="sortImports('title')">Title</th>
          <th class="sortable ${IMPORTS_SORT.col==='instance' ? 'sort-'+IMPORTS_SORT.dir : ''}" data-col="instance" onclick="sortImports('instance')">Instance</th>
          <th class="sortable ${IMPORTS_SORT.col==='type' ? 'sort-'+IMPORTS_SORT.dir : ''}" data-col="type" onclick="sortImports('type')">Type</th>
          <th class="sortable ${IMPORTS_SORT.col==='first_searched_ts' ? 'sort-'+IMPORTS_SORT.dir : ''}" data-col="first_searched_ts" onclick="sortImports('first_searched_ts')">Last Searched</th>
          <th class="sortable ${IMPORTS_SORT.col==='imported_ts' ? 'sort-'+IMPORTS_SORT.dir : ''}" data-col="imported_ts" onclick="sortImports('imported_ts')">Imported</th>
          <th>Turnaround <span class="tooltip-icon tip-down">i<div class="tooltip-box">Time from when Nudgarr first searched this item to when it was confirmed imported. Resets if the item is imported again at a higher quality.</div></span></th>
        </tr></thead><tbody></tbody></table>`;
    }
    refreshImports();
  }
  if (name === 'sweep') refreshSweep();
  if (name === 'history') { loadExclusions(); }
  if (name === 'advanced') {
    const msg = el('advMsg');
    if (!msg || !msg.textContent.includes('Unsaved')) fillAdvanced();
  }
  if (name === 'notifications') {
    const msg = el('notifyMsg');
    if (!msg || !msg.textContent.includes('Unsaved')) fillNotifications();
  }
  if (name === 'overrides') renderOverridesCards();
  if (name === 'filters') fillFilters();
}
// ── Settings tab ──
function updateContainerTime(timeStr) {
  const el = document.getElementById('cronContainerTime');
  if (el) el.textContent = timeStr ? '(' + timeStr + ')' : '';
}

function syncSchedulerUi() {
  const enabled = el('scheduler_enabled').checked;
  el('scheduler_label').textContent = enabled ? 'Enabled' : 'Manual';
  const cronInput = el('cron_expression');
  if (cronInput) {
    cronInput.disabled = !enabled;
    cronInput.style.opacity = enabled ? '' : '0.4';
    cronInput.style.cursor = enabled ? '' : 'not-allowed';
    if (enabled) {
      validateCronExpr();
    } else {
      cronInput.classList.remove('cron-valid', 'cron-invalid', 'cron-glow');
      const icon = el('cronValidIcon');
      if (icon) icon.style.display = 'none';
      const hint = el('cronHintLine');
      if (hint) { hint.className = 'cron-hint-line'; hint.innerHTML = ''; }
    }
  }
}


function validateCronExpr() {
  const input = el('cron_expression');
  const hint  = el('cronHintLine');
  const icon  = el('cronValidIcon');
  if (!input) return;
  input.classList.remove('cron-glow');
  const val = input.value.trim();
  if (!val) {
    input.classList.remove('cron-valid', 'cron-invalid');
    icon.style.display = 'none';
    hint.className = 'cron-hint-line';
    hint.innerHTML = '';
    return;
  }
  const parts = val.split(/\s+/);
  const valid = parts.length === 5 && parts.every(p => /^[\d\*\/,\-]+$/.test(p));
  input.classList.toggle('cron-valid',   valid);
  input.classList.toggle('cron-invalid', !valid);
  icon.style.display = valid ? 'inline' : 'none';
  if (valid) {
    const interval = cronIntervalMinutes(val);
    const tooFrequent = interval !== null && interval < 60;
    if (tooFrequent) {
      icon.style.color = '#fbbf24';
      hint.className = 'cron-hint-line cron-warn';
      hint.innerHTML = '⚠ May stress indexers';
    } else {
      icon.style.color = '#22c55e';
      hint.className = 'cron-hint-line cron-ok';
      hint.innerHTML = describeCron(val);
    }
  } else {
    icon.style.color = '#ef4444';
    hint.className = 'cron-hint-line cron-bad';
    hint.innerHTML = 'Invalid cron expression';
  }
}

function describeCron(expr) {
  const parts = expr.trim().split(/\s+/);
  if (parts.length !== 5) return 'Custom Schedule';
  const [min, hr, dom, mon, dow] = parts;
  const days = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
  const exactMin = /^\d+$/.test(min);
  const exactHr  = /^\d+$/.test(hr);
  const mm = exactMin ? String(parseInt(min)).padStart(2,'0') : '00';
  // Daily at specific time
  if (dom === '*' && mon === '*' && dow === '*' && exactHr && exactMin) {
    const h = parseInt(hr), m = parseInt(min);
    const suffix = h >= 12 ? 'PM' : 'AM';
    const h12 = h % 12 || 12;
    return `Daily at ${h12}:${String(m).padStart(2,'0')} ${suffix}`;
  }
  // Weekly on specific day
  if (dom === '*' && mon === '*' && /^\d+$/.test(dow) && exactHr && exactMin) {
    const d = parseInt(dow) % 7;
    const h = parseInt(hr), m = parseInt(min);
    const suffix = h >= 12 ? 'PM' : 'AM';
    const h12 = h % 12 || 12;
    return `Weekly on ${days[d]} at ${h12}:${String(m).padStart(2,'0')} ${suffix}`;
  }
  // Monthly on specific day
  if (/^\d+$/.test(dom) && mon === '*' && dow === '*' && exactHr && exactMin) {
    const d = parseInt(dom);
    const h = parseInt(hr), m = parseInt(min);
    const suffix = h >= 12 ? 'PM' : 'AM';
    const h12 = h % 12 || 12;
    const ord = d === 1 ? '1st' : d === 2 ? '2nd' : d === 3 ? '3rd' : `${d}th`;
    return `Monthly on the ${ord} at ${h12}:${String(m).padStart(2,'0')} ${suffix}`;
  }
  // Every N hours at fixed minute
  if (/^\*\/\d+$/.test(hr) && dom === '*' && mon === '*' && dow === '*' && exactMin) {
    const n = parseInt(hr.split('/')[1]);
    return `Every ${n} hour${n !== 1 ? 's' : ''} at xx:${mm}`;
  }
  // Every N hours (on the hour)
  if (min === '0' && /^\*\/\d+$/.test(hr) && dom === '*' && mon === '*' && dow === '*') {
    const n = parseInt(hr.split('/')[1]);
    return `Every ${n} hour${n !== 1 ? 's' : ''} at xx:00`;
  }
  // Every hour at fixed minute
  if (/^\d+$/.test(min) && hr === '*' && dom === '*' && mon === '*' && dow === '*') {
    return `Every hour at xx:${mm}`;
  }
  // Every hour on the hour
  if (min === '0' && hr === '*' && dom === '*' && mon === '*' && dow === '*') {
    return 'Every hour at xx:00';
  }
  // Every N minutes
  if (/^\*\/\d+$/.test(min) && hr === '*' && dom === '*' && mon === '*' && dow === '*') {
    const n = parseInt(min.split('/')[1]);
    return `Every ${n} minute${n !== 1 ? 's' : ''}`;
  }
  return 'Custom Schedule';
}

function fillSettings() {
  el('scheduler_enabled').checked = !!CFG.scheduler_enabled;
  el('cron_expression').value = CFG.cron_expression || '0 */6 * * *';

  el('cooldown_hours').value = CFG.cooldown_hours;
  const legacyMode = CFG.sample_mode || 'random';
  el('radarr_sample_mode').value = CFG.radarr_sample_mode || legacyMode;
  el('sonarr_sample_mode').value = CFG.sonarr_sample_mode || legacyMode;
  el('radarr_max_movies_per_run').value = CFG.radarr_max_movies_per_run;
  el('sonarr_max_episodes_per_run').value = CFG.sonarr_max_episodes_per_run;
  el('batch_size').value = CFG.batch_size;
  el('sleep_seconds').value = CFG.sleep_seconds;
  el('jitter_seconds').value = CFG.jitter_seconds;
  syncSchedulerUi();
  el('setMsg').textContent = ''; el('setMsg').className = 'msg';
  checkCooldownWarning();
}

// saveSettings — validates the cron expression client-side before submitting.
// If the scheduler is enabled with an invalid expression it adds cron-glow to
// the input and returns early. The void offsetWidth call forces a reflow so the
// CSS animation restarts even if the class was already present from a prior attempt.
async function saveSettings() {
  try {
    const enabled = el('scheduler_enabled').checked;
    const expr = el('cron_expression').value.trim();
    const parts = expr.split(/\s+/);
    const exprValid = parts.length === 5 && parts.every(p => /^[\d\*\/,\-]+$/.test(p));

    // Client-side guard: block save if auto enabled with no valid expression
    if (enabled && !exprValid) {
      const input = el('cron_expression');
      input.classList.remove('cron-glow');
      void input.offsetWidth; // force reflow so the glow animation restarts even if already present
      input.classList.add('cron-invalid', 'cron-glow');
      el('setMsg').textContent = 'Enter a valid cron expression first';
      el('setMsg').className = 'msg err';
      return;
    }

    CFG.scheduler_enabled = enabled;
    CFG.cron_expression = expr;
    CFG.cooldown_hours = parseInt(el('cooldown_hours').value || '48', 10);
    CFG.radarr_sample_mode = el('radarr_sample_mode').value;
    CFG.sonarr_sample_mode = el('sonarr_sample_mode').value;
    CFG.radarr_max_movies_per_run = parseInt(el('radarr_max_movies_per_run').value || '25', 10);
    CFG.sonarr_max_episodes_per_run = parseInt(el('sonarr_max_episodes_per_run').value || '25', 10);
    CFG.batch_size = parseInt(el('batch_size').value || '20', 10);
    CFG.sleep_seconds = parseFloat(el('sleep_seconds').value || '3');
    CFG.jitter_seconds = parseFloat(el('jitter_seconds').value || '2');
    const res = await fetch('/api/config', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(CFG)});
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      const msg = (body && body.errors && body.errors[0]) ? body.errors[0] : 'Save failed';
      el('setMsg').textContent = msg; el('setMsg').className = 'msg err';
      return;
    }
    await loadAll();
    await new Promise(r => setTimeout(r, 400));
    el('setMsg').textContent = 'Saved'; el('setMsg').className = 'msg ok'; fadeMsg('setMsg');
    fadeNewestAddedWarnings();
    flashCooldownDisabledNote();
  } catch(e) {
    el('setMsg').textContent = 'Save failed: ' + e.message; el('setMsg').className = 'msg err';
  }
}

// ── Cooldown note ──
const _COOLDOWN_HELP_DEFAULT = 'Minimum hours before the same movie or episode can be searched again (0 Disables)';
const _COOLDOWN_HELP_ZERO    = 'Cooldown is disabled. Items may repeat each sweep.';

function checkCooldownWarning() {
  const helpEl   = el('cooldownHelpText');
  if (!helpEl) return;
  const cooldown = parseFloat(el('cooldown_hours').value || '48');
  helpEl.textContent = cooldown <= 0 ? _COOLDOWN_HELP_ZERO : _COOLDOWN_HELP_DEFAULT;
}

function flashCooldownDisabledNote() {
  checkCooldownWarning();
}

// ── Newest Added warning ──
function _newestAddedWarningActive() {
  const mode = el('radarr_sample_mode') ? el('radarr_sample_mode').value : (CFG ? CFG.radarr_sample_mode || CFG.sample_mode : 'random');
  const backlog = el('radarr_backlog_enabled') ? el('radarr_backlog_enabled').checked : (CFG ? !!CFG.radarr_backlog_enabled : false);
  const days = el('radarr_missing_added_days') ? parseInt(el('radarr_missing_added_days').value || '0', 10) : (CFG ? (CFG.radarr_missing_added_days ?? 0) : 0);
  return mode === 'newest_added' && backlog && days > 0;
}

function checkNewestAddedWarning() {
  const showWarn = _newestAddedWarningActive();
  const warnSettings = el('newestAddedWarnSettings');
  const warnAdv = el('newestAddedWarnAdvanced');
  [warnSettings, warnAdv].forEach(w => {
    if (!w) return;
    clearTimeout(w._warnFade);
    w.style.opacity = '';
    w.style.transition = '';
    if (showWarn) { w.classList.add('visible'); }
    else          { w.classList.remove('visible'); }
  });
}

function fadeNewestAddedWarnings() {
  [el('newestAddedWarnSettings'), el('newestAddedWarnAdvanced')].forEach(w => {
    if (!w || !w.classList.contains('visible')) return;
    clearTimeout(w._warnFade);
    w.style.transition = 'opacity 0.5s ease';
    w.style.opacity = '0';
    w._warnFade = setTimeout(() => {
      w.style.opacity = '';
      w.style.transition = '';
      w.classList.remove('visible');
    }, 500);
  });
}

// ── What's New modal ──
async function dismissWhatsNew() {
  el('whatsNewModal').style.display = 'none';
  await api('/api/whats-new/dismiss', {method: 'POST'});
  if (CFG) CFG.last_seen_version = el('ver').textContent;
}

function maybeShowWhatsNew() {
  if (!CFG) return;
  if (!CFG.onboarding_complete) return;
  const lastSeen = CFG.last_seen_version || '';
  const current = el('ver').textContent || '';
  const toMinor = v => v.split('.').slice(0, 2).join('.');
  if (current && toMinor(lastSeen) !== toMinor(current)) {
    el('whatsNewModal').style.display = 'flex';
  }
}

// ── Support link UI ──
function syncSupportLinkUi() {
  const show = el('show_support_link') ? el('show_support_link').checked : true;
  const sl = el('supportLink');
  if (sl) sl.style.display = show ? 'inline-flex' : 'none';
  const lbl = el('support_link_label');
  if (lbl) lbl.textContent = show ? 'Shown' : 'Hidden';
}

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
    body: `Nudgarr tells your Radarr and Sonarr instances what to search for, so you don't have to. It works quietly in the background, nudging your Arrs toward better quality releases, filling in missing content, and refining what you already have.
<br><br>
It runs on a schedule. You set the rules once and let it work through your library over time. This walkthrough covers the key concepts and settings to get you started safely.`
  },
  {
    title: "How Nudgarr Works",
    body: `Nudgarr runs three independent pipelines each sweep. Each one targets a different kind of gap in your library.
<br><br>
<strong>Cutoff Unmet</strong><br>
You have the file but it does not meet your quality profile cutoff. Nudgarr tells Radarr or Sonarr to search for a better version. On by default — this is the primary pipeline.
<br><br>
<strong>Backlog</strong><br>
You do not have the file at all. Nudgarr tells your Arrs to search for missing movies and episodes that were never grabbed. Off by default — enable in Advanced when you're ready.
<br><br>
<strong>CF Score</strong><br>
You have the file and the quality tier is met, but the custom format score is below the cutoff for that profile. Nudgarr tells your Arrs to look for a better-scored release. Off by default — enable in Advanced when you're ready.
<br><br>
As sweeps run over time these three pipelines work together. Backlog fills in what is missing. Cutoff Unmet upgrades what you have. CF Score refines what is already good.`
  },
  {
    title: "Step 1 — Add Your Instances",
    body: `Start on the <strong>Instances tab</strong>. Add each of your Radarr and Sonarr servers with their URL and API key. Use <strong>Test Connections</strong> to confirm everything is reachable before moving on.
<br><br>
You can add multiple instances of the same app. Nudgarr will nudge all of them each run. Keep in mind that settings like Max Per Run apply <strong>per instance</strong> — two Radarr instances set to 5 means up to 10 movie search commands per sweep.`
  },
  {
    title: "Step 2 — Scheduler and Run Now",
    body: `The scheduler is <strong>off by default</strong>. Nudgarr will not run automatically until you enable it.
<br><br>
You can trigger a sweep at any time using <strong>Run Now</strong>. This is the recommended approach for your first few runs so you can see exactly what happens before committing to a schedule.
<br><br>
When you are ready to automate, set a cron schedule. The default is <code>0 */6 * * *</code> — every 6 hours. Start conservative and adjust based on your library size and how active your indexers are.
<br><br>
Nudgarr has no visibility into your indexer's rate limits. Pacing is your responsibility.`
  },
  {
    title: "Step 3 — Cutoff Unmet and Throttling",
    body: `<strong>Max Per Run</strong><br>
How many items Nudgarr nudges per instance per run. Start at 1 and increase slowly. There is no rush — Nudgarr will work through your library gradually over time.
<br><br>
<strong>Cooldown</strong><br>
How long before the same item is nudged again. Default is 48 hours. Do not lower this aggressively — triggering repeated searches for the same item in a short window is one of the fastest ways to get flagged by an indexer.
<br><br>
<strong>Sample Mode</strong><br>
Controls which eligible items are picked each run. Random gives even coverage. Alphabetical works A to Z. Oldest Added prioritises items you have had longest. Newest Added targets recently added items. Round Robin searches whoever has been waiting longest, with never-searched items going first.
<br><br>
<strong>Batch, Sleep, and Jitter</strong><br>
These control how fast Nudgarr sends commands to your instances. The defaults are safe. Only adjust these if you know what you are doing.`
  },
  {
    title: "Step 4 — Exclusions and Auto-Exclusion",
    body: `Some items will never be available on your indexers regardless of how many times they are searched. Excluding them keeps your eligible pool clean and avoids wasting search commands.
<br><br>
<strong>Manual Exclusions</strong><br>
From the History tab, click the exclusion icon on any row to permanently remove that title from future searches. Click the same icon to remove the exclusion. Excluded titles appear under the Exclusions filter and can be cleared individually or in bulk using Clear Exclusions.
<br><br>
<strong>Auto-Exclusion</strong><br>
In Advanced, enable the auto-exclusion toggle for Radarr, Sonarr, or both, then set a search threshold. If an item is nudged that many times with no confirmed import, Nudgarr excludes it automatically. You can also set an Unexclude Days value — after that many days the title is removed from exclusions and gets another chance. Start with a conservative threshold like 10 and adjust based on your library.`
  },
  {
    title: "Step 5 — Notifications and Intel",
    body: `<strong>Notifications</strong><br>
Nudgarr can notify you when sweeps complete, imports are confirmed, items are auto-excluded, or an instance becomes unreachable. Add your Apprise-compatible URL in the Notifications tab, choose which events to be notified on, and use Send Test to confirm it is working. Supports Discord, Gotify, Ntfy, Pushover, Slack, and more.
<br><br>
<strong>Intel</strong><br>
The Intel tab is a lifetime performance dashboard. It shows hard facts about what Nudgarr has actually done — import turnaround, searches per import, pipeline breakdown, upgrade history, and exclusion activity. It needs a minimum of 25 confirmed imports or 50 sweep runs before data appears. Give it time.`
  },
  {
    title: "You're Ready",
    body: `Here is the recommended way to start:
<br><br>
1. Add your instances and test connections<br>
2. Review your settings and keep them conservative<br>
3. Hit <strong>Run Now</strong> to trigger your first sweep manually<br>
4. Check the <strong>History tab</strong> to see what was nudged<br>
5. Check the <strong>Imports tab</strong> after a day or two to see what was confirmed<br>
6. If everything looks right, enable the scheduler<br>
7. Gradually increase Max Per Run as you get comfortable<br>
8. Set your <strong>Default Tab</strong> in Advanced under UI Preferences to choose where Nudgarr opens on a new browser or device
<br><br>
Nudgarr remembers the last tab you visited within the same browser, so refreshing always brings you back to where you were.
<br><br>
Nudgarr is designed to work quietly in the background. Start slow, let it earn your trust, and tune from there.
<br><br>
<span style="color:var(--muted);font-size:12px">If Nudgarr is useful to you, the 🍺 support link in the header is a nice way to say thanks. You can hide it anytime in Advanced under UI Preferences.</span>`
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
  // Guard: refuse to navigate to a conditional tab if its feature is currently disabled.
  // Fall back to sweep so the user always lands somewhere visible.
  const conditionalTabEnabled = {
    'overrides': () => !!CFG?.per_instance_overrides_enabled,
    'cf-scores': () => !!CFG?.cf_score_enabled,
    'filters':   () => !!((CFG?.instances?.radarr?.length || 0) + (CFG?.instances?.sonarr?.length || 0)),
  };
  const tabCheck = conditionalTabEnabled[name];
  if (tabCheck && !tabCheck()) { _doShowTab('sweep'); return; }

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
  // Persist last visited tab so browser refresh returns to the same tab.
  // Only written after onboarding is complete — new installs always start on Instances.
  if (CFG && CFG.onboarding_complete) {
    try { localStorage.setItem('nudgarr_last_tab', name); } catch (_) {}
  }
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
  if (name === 'intel') fillIntel();
  if (name === 'cf-scores') fillCfScores();
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
  el('radarr_cutoff_enabled').checked = CFG.radarr_cutoff_enabled !== false;
  el('sonarr_cutoff_enabled').checked = CFG.sonarr_cutoff_enabled !== false;
  syncCutoffUi();
  el('batch_size').value = CFG.batch_size;
  el('sleep_seconds').value = CFG.sleep_seconds;
  el('jitter_seconds').value = CFG.jitter_seconds;
  // Maintenance window (v4.2.0)
  if (el('maintenance_window_enabled')) {
    el('maintenance_window_enabled').checked = !!CFG.maintenance_window_enabled;
    el('maintenance_window_start').value = CFG.maintenance_window_start || '';
    el('maintenance_window_end').value = CFG.maintenance_window_end || '';
    const days = CFG.maintenance_window_days || [];
    document.querySelectorAll('#maint_day_pills .day-pill').forEach(btn => {
      btn.classList.toggle('on', days.includes(parseInt(btn.dataset.day, 10)));
    });
    syncMaintUi();
  }
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
    CFG.radarr_cutoff_enabled = el('radarr_cutoff_enabled').checked;
    CFG.sonarr_cutoff_enabled = el('sonarr_cutoff_enabled').checked;
    CFG.batch_size = parseInt(el('batch_size').value || '20', 10);
    CFG.sleep_seconds = parseFloat(el('sleep_seconds').value || '3');
    CFG.jitter_seconds = parseFloat(el('jitter_seconds').value || '2');
    // Maintenance window (v4.2.0)
    if (el('maintenance_window_enabled')) {
      CFG.maintenance_window_enabled = el('maintenance_window_enabled').checked;
      CFG.maintenance_window_start = el('maintenance_window_start').value.trim() || '00:00';
      CFG.maintenance_window_end = el('maintenance_window_end').value.trim() || '00:00';
      CFG.maintenance_window_days = [...document.querySelectorAll('#maint_day_pills .day-pill.on')]
        .map(btn => parseInt(btn.dataset.day, 10));
    }
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
    flashCooldownDisabledNote();
  } catch(e) {
    el('setMsg').textContent = 'Save failed: ' + e.message; el('setMsg').className = 'msg err';
  }
}

// ── Cooldown note ──
const _COOLDOWN_HELP_DEFAULT = 'Minimum hours before an item can be searched again (0 = No Cooldown)';
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

// ── Maintenance Window (v4.2.0) ──

// syncCutoffUi — greys the Max and Sample Mode fields for each app when that
// app's Cutoff Unmet pipeline is disabled. Mirrors the Backlog enabled pattern
// in ui-advanced.js. Called on toggle change and on fillSettings.
function syncCutoffUi() {
  for (const app of ['radarr', 'sonarr']) {
    const on = el(app + '_cutoff_enabled')?.checked !== false;
    const lbl = el(app + '_cutoff_label');
    const fields = el(app + '_cutoff_fields');
    if (lbl) lbl.textContent = on ? 'Enabled' : 'Disabled';
    if (fields) {
      fields.style.opacity = on ? '' : '0.35';
      fields.style.pointerEvents = on ? '' : 'none';
    }
  }
}

// syncMaintUi — enables or disables the time/day fields based on the toggle.
// Called on toggle change and on fillSettings() load.
function syncMaintUi() {
  const on = el('maintenance_window_enabled') && el('maintenance_window_enabled').checked;
  const lbl = el('maint_label');
  if (lbl) lbl.textContent = on ? 'Enabled' : 'Disabled';
  const ctrl = el('maint_controls');
  if (ctrl) {
    ctrl.style.opacity = on ? '1' : '0.35';
    ctrl.style.pointerEvents = on ? '' : 'none';
  }
  if (on) validateMaintTime();
  else {
    const hint = el('maint_hint');
    if (hint) { hint.className = 'cron-hint-line'; hint.textContent = ''; }
  }
}

// validateMaintTime — validates both HH:MM inputs and updates the hint line.
// Describes the window once both times are valid and at least one day is selected.
// Detects and labels overnight ranges (start > end).
function validateMaintTime() {
  const sInput = el('maintenance_window_start');
  const eInput = el('maintenance_window_end');
  const hint   = el('maint_hint');
  if (!sInput || !eInput || !hint) return;

  const timeRe = /^(\d{2}):(\d{2})$/;
  const sMatch = sInput.value.trim().match(timeRe);
  const eMatch = eInput.value.trim().match(timeRe);

  sInput.classList.remove('cron-valid', 'cron-invalid');
  eInput.classList.remove('cron-valid', 'cron-invalid');
  sInput.style.borderColor = '';
  eInput.style.borderColor = '';

  if (!sInput.value && !eInput.value) {
    hint.className = 'cron-hint-line'; hint.textContent = ''; return;
  }

  const sOk = !!(sMatch && parseInt(sMatch[1],10) <= 23 && parseInt(sMatch[2],10) <= 59);
  const eOk = !!(eMatch && parseInt(eMatch[1],10) <= 23 && parseInt(eMatch[2],10) <= 59);
  sInput.style.borderColor = sOk ? 'rgba(34,197,94,.45)' : 'rgba(239,68,68,.45)';
  eInput.style.borderColor = eOk ? 'rgba(34,197,94,.45)' : 'rgba(239,68,68,.45)';

  if (!sOk || !eOk) {
    hint.className = 'cron-hint-line cron-bad';
    hint.textContent = 'Enter times in HH:MM format (e.g. 23:00)';
    return;
  }

  const startMins = parseInt(sMatch[1],10) * 60 + parseInt(sMatch[2],10);
  const endMins   = parseInt(eMatch[1],10) * 60 + parseInt(eMatch[2],10);

  if (startMins === endMins) {
    hint.className = 'cron-hint-line cron-bad';
    hint.textContent = 'Start and end time cannot be the same';
    return;
  }

  const selectedDays = [...document.querySelectorAll('#maint_day_pills .day-pill.on')]
    .map(btn => btn.textContent);

  if (selectedDays.length === 0) {
    hint.className = 'cron-hint-line cron-bad';
    hint.textContent = 'Select at least one day';
    return;
  }

  const dayStr = selectedDays.length === 7 ? 'every day' : selectedDays.join(', ');
  const overnight = startMins > endMins;
  hint.className = 'cron-hint-line cron-ok';
  hint.textContent = `${sInput.value.trim()} to ${eInput.value.trim()}${overnight ? ' (overnight)' : ''} on ${dayStr}`;
}

// toggleMaintDay — toggles the on state of a day pill and re-validates the hint.
function toggleMaintDay(btn) {
  btn.classList.toggle('on');
  validateMaintTime();
}

// ── Landscape Backlog and Execution tabs ────────────────────────────────────
// LS_* state (LS_VALS, LS_MINS, LS_CFG_KEYS, LS_SAVE_TIMER, LS_HIDE_TIMER,
// LS_TAB), lsPopulate, lsToggleBacklog, lsSyncBacklogFields, lsSaveBacklogSampleMode,
// lsToggleAuto, lsValidateCron, lsHoldStart/End/Step, lsTriggerSave, lsSwitchTab,
// _lsDoSwitchTab, lsSwitchToDesktop, lsToggleMaint, lsSaveMaintTime,
// lsToggleMaintDay, lsBuildMaintHint, lsSyncMaintUi, landscape swipe gesture.
// cronIntervalMinutes (shared cron helper) lives in ui-core.js.

// ── Landscape section (inside if(MOBILE)) ─────────────────────────────────

const LS_VALS = {
  batch: 1, sleep: 5, jitter: 2,
  'r-missing': 1, 'r-days': 14, 's-missing': 1,
};
const LS_MINS = {
  batch: 1, sleep: 0, jitter: 0,
  'r-missing': 1, 'r-days': 0, 's-missing': 1,
};
const LS_CFG_KEYS = {
  batch:       'batch_size',
  sleep:       'sleep_seconds',
  jitter:      'jitter_seconds',
  'r-missing': 'radarr_missing_max',
  'r-days':    'radarr_missing_added_days',
  's-missing': 'sonarr_missing_max',
};
let LS_SAVE_TIMER = null;
let LS_HIDE_TIMER = null;
let LS_TAB = 0;

function lsPopulate() {
  if (!CFG) return;
  LS_VALS.batch       = CFG.batch_size                  ?? 1;
  LS_VALS.sleep       = CFG.sleep_seconds               ?? 5;
  LS_VALS.jitter      = CFG.jitter_seconds              ?? 2;
  LS_VALS['r-missing'] = CFG.radarr_missing_max          ?? 1;
  LS_VALS['r-days']   = CFG.radarr_missing_added_days   ?? 14;
  LS_VALS['s-missing'] = CFG.sonarr_missing_max          ?? 1;

  Object.keys(LS_VALS).forEach(k => {
    const el = document.getElementById('ls-v-' + k);
    if (el) { el.textContent = LS_VALS[k]; el.classList.toggle('ls-zero', LS_VALS[k] === 0); }
  });

  // Backlog toggles and sample mode selects
  const rBl = document.getElementById('ls-tog-radarr-backlog');
  const sBl = document.getElementById('ls-tog-sonarr-backlog');
  if (rBl) rBl.classList.toggle('ls-on', !!CFG.radarr_backlog_enabled);
  if (sBl) sBl.classList.toggle('ls-on', !!CFG.sonarr_backlog_enabled);
  const rSel = document.getElementById('ls-sel-radarr-backlog-mode');
  if (rSel) rSel.value = CFG.radarr_backlog_sample_mode || 'random';
  const sSel = document.getElementById('ls-sel-sonarr-backlog-mode');
  if (sSel) sSel.value = CFG.sonarr_backlog_sample_mode || 'random';
  lsSyncBacklogFields('radarr');
  lsSyncBacklogFields('sonarr');

  // Execution tab
  const autoTog = document.getElementById('ls-tog-auto');
  if (autoTog) autoTog.classList.toggle('ls-on', !!CFG.scheduler_enabled);
  const autoSub = document.getElementById('ls-auto-sub');
  if (autoSub) autoSub.textContent = CFG.scheduler_enabled ? describeCron(CFG.cron_expression || '') : 'Manual';
  const cronInput = document.getElementById('ls-cron-input');
  if (cronInput) { cronInput.value = CFG.cron_expression || ''; lsValidateCron(); }
  const cronRow = document.getElementById('ls-cron-row');
  if (cronRow) cronRow.style.opacity = CFG.scheduler_enabled ? '' : '.38';

  // Maintenance Window
  const maintTog = document.getElementById('ls-tog-maint');
  if (maintTog) maintTog.classList.toggle('ls-on', !!CFG.maintenance_window_enabled);
  const maintStart = document.getElementById('ls-maint-start');
  if (maintStart) maintStart.value = CFG.maintenance_window_start || '';
  const maintEnd = document.getElementById('ls-maint-end');
  if (maintEnd) maintEnd.value = CFG.maintenance_window_end || '';
  const days = CFG.maintenance_window_days || [];
  ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].forEach((d, i) => {
    const pill = document.getElementById('ls-maint-day-' + d);
    if (pill) pill.classList.toggle('ls-on', days.includes(i));
  });
  lsSyncMaintUi();

  if (typeof mOvUpdateSubLabels === 'function') mOvUpdateSubLabels();
}

function lsUpdateContainerTime(timeStr) {
  const el = document.getElementById('ls-container-time');
  if (el) el.textContent = timeStr ? 'Container: ' + timeStr : '';
}

function lsToggleBacklog(app) {
  mHaptic(40);
  const key = app + '_backlog_enabled';
  mSaveCfgKeys({[key]: !CFG[key]}).then(() => {
    const tog = document.getElementById('ls-tog-' + app + '-backlog');
    if (tog) tog.classList.toggle('ls-on', !!CFG[key]);
    lsSyncBacklogFields(app);
  });
}

function lsSyncBacklogFields(app) {
  const fieldsDiv = document.getElementById('ls-' + app + '-backlog-fields');
  if (!fieldsDiv) return;
  const enabled = app === 'radarr' ? !!CFG?.radarr_backlog_enabled : !!CFG?.sonarr_backlog_enabled;
  fieldsDiv.style.opacity = enabled ? '' : '.38';
  fieldsDiv.style.pointerEvents = enabled ? '' : 'none';
}

// lsSaveBacklogSampleMode — saves the backlog sample mode select value for the given app.
function lsSaveBacklogSampleMode(app) {
  const sel = document.getElementById('ls-sel-' + app + '-backlog-mode');
  if (!sel) return;
  mSaveCfgKeys({[app + '_backlog_sample_mode']: sel.value});
}

function lsToggleAuto() {
  mHaptic(40);
  mSaveCfgKeys({scheduler_enabled: !CFG.scheduler_enabled}).then(() => {
    const tog = document.getElementById('ls-tog-auto');
    if (tog) tog.classList.toggle('ls-on', !!CFG.scheduler_enabled);
    const sub = document.getElementById('ls-auto-sub');
    if (sub) sub.textContent = CFG.scheduler_enabled ? describeCron(CFG.cron_expression || '') : 'Manual';
    const cronRow = document.getElementById('ls-cron-row');
    if (cronRow) cronRow.style.opacity = CFG.scheduler_enabled ? '' : '.38';
    lsSyncMaintUi();
  });
}

// lsToggleMaint — toggles maintenance_window_enabled and syncs UI.
function lsToggleMaint() {
  mHaptic(40);
  mSaveCfgKeys({maintenance_window_enabled: !CFG.maintenance_window_enabled}).then(() => {
    lsSyncMaintUi();
  });
}

// lsSaveMaintTime — debounced save for start/end time inputs.
let _lsMaintTimeTimer = null;
function lsSaveMaintTime() {
  clearTimeout(_lsMaintTimeTimer);
  _lsMaintTimeTimer = setTimeout(() => {
    const start = (document.getElementById('ls-maint-start') || {}).value || '';
    const end   = (document.getElementById('ls-maint-end')   || {}).value || '';
    mSaveCfgKeys({maintenance_window_start: start, maintenance_window_end: end}).then(() => {
      lsSyncMaintUi();
    });
  }, 800);
}

// lsToggleMaintDay — toggles a day in maintenance_window_days (integer 0-6) and saves.
function lsToggleMaintDay(day) {
  mHaptic(20);
  const dayIndex = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].indexOf(day);
  const days = Array.isArray(CFG.maintenance_window_days) ? [...CFG.maintenance_window_days] : [];
  const idx = days.indexOf(dayIndex);
  if (idx === -1) days.push(dayIndex); else days.splice(idx, 1);
  mSaveCfgKeys({maintenance_window_days: days}).then(() => {
    const pill = document.getElementById('ls-maint-day-' + day);
    if (pill) pill.classList.toggle('ls-on', days.includes(dayIndex));
    lsSyncMaintUi();
  });
}

// lsBuildMaintHint — builds the hint line from current config values.
// Returns empty string if window is disabled, times invalid, or no days selected.
function lsBuildMaintHint() {
  if (!CFG.maintenance_window_enabled) return '';
  const start = (document.getElementById('ls-maint-start') || {}).value || CFG.maintenance_window_start || '';
  const end   = (document.getElementById('ls-maint-end')   || {}).value || CFG.maintenance_window_end   || '';
  const days  = Array.isArray(CFG.maintenance_window_days) ? CFG.maintenance_window_days : [];
  const validTime = /^([01]\d|2[0-3]):[0-5]\d$/;
  if (!validTime.test(start) || !validTime.test(end) || days.length === 0) return '';
  const _DAY_NAMES = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
  const dayNames = days.map(d => _DAY_NAMES[d] || d).join(', ');
  const overnight = end <= start;
  return 'Active ' + dayNames + ' from ' + start + ' to ' + end + '.' + (overnight ? ' Overnight range.' : '');
}

// lsSyncMaintUi — updates enabled/disabled state of MW controls and hint line.
function lsSyncMaintUi() {
  const schedulerOn = !!CFG.scheduler_enabled;
  const maintOn     = !!CFG.maintenance_window_enabled;
  const band = document.getElementById('ls-maint-band');
  if (band) {
    band.style.opacity       = schedulerOn ? '' : '.38';
    band.style.pointerEvents = schedulerOn ? '' : 'none';
  }
  const tog = document.getElementById('ls-tog-maint');
  if (tog) tog.classList.toggle('ls-on', maintOn);
  const timeCol = document.getElementById('ls-maint-time-col');
  const daysCol = document.getElementById('ls-maint-days-col');
  const inactive = !schedulerOn || !maintOn;
  [timeCol, daysCol].forEach(el => {
    if (!el) return;
    el.style.opacity       = inactive ? '.38' : '';
    el.style.pointerEvents = inactive ? 'none' : '';
  });
  const hint = document.getElementById('ls-maint-hint');
  if (hint) {
    const text = lsBuildMaintHint();
    hint.textContent = text;
    hint.className = 'ls-cron-hint' + (text ? ' ls-cron-ok' : '');
  }
}

function lsValidateCron() {
  const input = document.getElementById('ls-cron-input');
  const hint = document.getElementById('ls-cron-hint');
  if (!input || !hint) return;
  const val = input.value.trim();
  if (!val) { hint.textContent = ''; hint.className = 'ls-cron-hint'; return; }
  const parts = val.split(/\s+/);
  const valid = parts.length === 5 && parts.every(p => /^[\d\*\/,\-]+$/.test(p));
  input.classList.toggle('ls-cron-valid', valid);
  input.classList.toggle('ls-cron-invalid', !valid);
  if (valid) {
    const interval = cronIntervalMinutes(val);
    if (interval !== null && interval < 60) {
      hint.textContent = '\u26a0 May stress indexers \u00b7 ' + describeCron(val);
      hint.className = 'ls-cron-hint ls-cron-warn';
    } else {
      hint.textContent = describeCron(val);
      hint.className = 'ls-cron-hint ls-cron-ok';
    }
    clearTimeout(LS_SAVE_TIMER);
    LS_SAVE_TIMER = setTimeout(() => {
      mSaveCfgKeys({cron_expression: val}).then(() => {
        const sub = document.getElementById('ls-auto-sub');
        if (sub) sub.textContent = CFG.scheduler_enabled ? describeCron(val) : 'Manual';
      });
    }, 1000);
  } else {
    hint.textContent = 'Invalid cron expression';
    hint.className = 'ls-cron-hint ls-cron-bad';
  }
}


const LS_HOLD_INCREMENTS = {
  batch: 1, sleep: 1, jitter: 1,
  'r-missing': 1, 'r-days': 7, 's-missing': 1,
};
let _lsHoldTimer = null;
let _lsHoldInterval = null;
let _lsHoldFired = false;

function lsHoldStart(key, dir) {
  _lsHoldFired = false;
  _lsHoldTimer = setTimeout(() => {
    _lsHoldFired = true;
    const inc = LS_HOLD_INCREMENTS[key] || 1;
    mHaptic(20);
    lsStep(key, dir, inc);
    _lsHoldInterval = setInterval(() => { mHaptic(10); lsStep(key, dir, inc); }, 400);
  }, 500);
}

function lsHoldEnd(key, dir) {
  clearTimeout(_lsHoldTimer);
  clearInterval(_lsHoldInterval);
  _lsHoldTimer = null; _lsHoldInterval = null;
  if (!_lsHoldFired && key !== undefined) { mHaptic(20); lsStep(key, dir, 1); }
  _lsHoldFired = false;
}

function lsStep(key, dir, amt) {
  mHaptic(20);
  LS_VALS[key] = Math.max(LS_MINS[key], LS_VALS[key] + dir * (amt || 1));
  const el = document.getElementById('ls-v-' + key);
  if (el) { el.textContent = LS_VALS[k = key]; el.classList.toggle('ls-zero', LS_VALS[key] === 0); }
  lsTriggerSave();
}

function lsTriggerSave() {
  clearTimeout(LS_SAVE_TIMER);
  clearTimeout(LS_HIDE_TIMER);
  const ind = document.getElementById('ls-save-ind');
  if (ind) ind.classList.remove('ls-visible');
  LS_SAVE_TIMER = setTimeout(async () => {
    try {
      const updates = {};
      Object.entries(LS_CFG_KEYS).forEach(([k, cfgKey]) => { updates[cfgKey] = LS_VALS[k]; });
      const cfg = await api('/api/config');
      Object.assign(cfg, updates);
      await api('/api/config', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(cfg)});
      Object.assign(CFG, updates);
      if (ind) {
        ind.classList.add('ls-visible');
        LS_HIDE_TIMER = setTimeout(() => ind.classList.remove('ls-visible'), 1200);
      }
    } catch(e) {}
  }, 800);
}

const LS_NAV_ITEMS = ['ls-nav-backlog','ls-nav-execution','ls-nav-overrides','ls-nav-filters'];
const LS_TAB_IDS   = ['ls-tab-backlog','ls-tab-execution','ls-tab-overrides','ls-tab-filters'];

function lsSwitchTab(idx) {
  if (LS_TAB === 2 && idx !== 2 && lsOvHasPending()) {
    showConfirm('Unsaved Overrides', 'You have pending changes. Apply or discard before leaving.', 'Discard', true)
      .then(confirmed => { if (confirmed) { lsOvDiscardAll(); _lsDoSwitchTab(idx); } });
    return;
  }
  _lsDoSwitchTab(idx);
}

function _lsDoSwitchTab(idx) {
  LS_TAB = idx;
  LS_TAB_IDS.forEach((id, i) => {
    const t = document.getElementById(id);
    if (!t) return;
    t.classList.remove('ls-tab-active','ls-tab-prev');
    if (i === idx) t.classList.add('ls-tab-active');
    else if (i < idx) t.classList.add('ls-tab-prev');
  });
  LS_NAV_ITEMS.forEach((id, i) => {
    const n = document.getElementById(id);
    if (n) n.classList.toggle('ls-active', i === idx);
  });
  if (idx === 2) lsOvRenderRail();
  if (idx === 3) lsFiltersRenderRail();
}

function lsSwitchToDesktop() {
  LS_DESKTOP_OVERRIDE = true;
  sessionStorage.setItem('nudgarr_desktop_override','1');
  checkOrientation();
}

// ── Landscape swipe ────────────────────────────────────────────────────────

(function() {
  const vp = document.getElementById('ls-viewport');
  if (!vp) return;
  let sx = null, sy = null;
  vp.addEventListener('touchstart', e => { sx = e.touches[0].clientX; sy = e.touches[0].clientY; }, {passive: true});
  vp.addEventListener('touchend', e => {
    if (sx === null) return;
    const dx = e.changedTouches[0].clientX - sx;
    const dy = e.changedTouches[0].clientY - sy;
    if (Math.abs(dx) >= 30 && Math.abs(dx) >= Math.abs(dy) * 1.5) {
      if (dx < 0 && LS_TAB < LS_TAB_IDS.length - 1) lsSwitchTab(LS_TAB + 1);
      if (dx > 0 && LS_TAB > 0) lsSwitchTab(LS_TAB - 1);
    }
    sx = null;
  }, {passive: true});
})();


// ── Portrait Settings tab ───────────────────────────────────────────────────
// M_S_VALS, M_S_MINS, M_S_CFG_KEYS, M_S_HOLD_INCS state;
// mSHoldStart, mSHoldEnd, mSStep, mSSave, mSetSeg, mPopulateSettings,
// mSyncAutoExclUi, mMaybeShowAutoExclDisabledPopup,
// mOnAutoExclDisabledCancel, mOnAutoExclDisabledClear,
// mToggleNotifySettings, mToggleNotifyEvent, mSyncNotifyEvents

// ── Settings tab ───────────────────────────────────────────────────────────

// M_S_VALS / M_S_MINS / M_S_CFG_KEYS / M_S_HOLD_INCS — stepper state for the
// portrait Settings tab. Steppers map short UI keys to CFG field names and
// enforce per-field minimums. Auto-exclusion steppers added in v4.1.0:
//   r-autoexcl / r-unexclude — Radarr auto-exclude threshold and unexclude days
//   s-autoexcl / s-unexclude — Sonarr equivalents
const M_S_VALS = {
  cooldown: 48, 'r-cutoff': 3, 's-cutoff': 5,
  'r-autoexcl': 0, 'r-unexclude': 0,
  's-autoexcl': 0, 's-unexclude': 0,
};
const M_S_MINS = {
  cooldown: 0, 'r-cutoff': 0, 's-cutoff': 0,
  'r-autoexcl': 0, 'r-unexclude': 0,
  's-autoexcl': 0, 's-unexclude': 0,
};
const M_S_CFG_KEYS = {
  cooldown:      'cooldown_hours',
  'r-cutoff':    'radarr_max_movies_per_run',
  's-cutoff':    'sonarr_max_episodes_per_run',
  'r-autoexcl':  'auto_exclude_movies_threshold',
  'r-unexclude': 'auto_unexclude_movies_days',
  's-autoexcl':  'auto_exclude_shows_threshold',
  's-unexclude': 'auto_unexclude_shows_days',
};
// M_S_HOLD_INCS — the accelerated increment applied when the user holds a stepper
// button past the 500ms threshold (hold-to-accelerate pattern).
const M_S_HOLD_INCS = {
  cooldown: 24, 'r-cutoff': 1, 's-cutoff': 1,
  'r-autoexcl': 1, 'r-unexclude': 1,
  's-autoexcl': 1, 's-unexclude': 1,
};

// M_S_THRESHOLD_KEYS — maps each threshold key to its paired unexclude row ID.
// Used by mSyncAutoExclUi to grey the unexclude stepper when threshold is 0.
const M_S_THRESHOLD_KEYS = {
  'r-autoexcl': 'm-row-r-unexclude',
  's-autoexcl': 'm-row-s-unexclude',
};

// _mSHoldTimer / _mSHoldInterval / _mSHoldFired — together implement hold-to-accelerate.
// _mSHoldTimer fires after 500ms to enter hold mode; _mSHoldInterval repeats at 400ms;
// _mSHoldFired prevents the tap handler from also firing on release after a hold.
let _mSHoldTimer = null;
let _mSHoldInterval = null;
let _mSHoldFired = false;

// M_S_SAVE_TIMER — debounces config saves so rapid stepper taps produce one request.
let M_S_SAVE_TIMER = null;

function mSHoldStart(key, dir) {
  _mSHoldFired = false;
  _mSHoldTimer = setTimeout(() => {
    _mSHoldFired = true;
    const inc = M_S_HOLD_INCS[key] || 1;
    mHaptic(20);
    mSStep(key, dir, inc);
    _mSHoldInterval = setInterval(() => { mHaptic(10); mSStep(key, dir, inc); }, 400);
  }, 500);
}

function mSHoldEnd(key, dir) {
  clearTimeout(_mSHoldTimer);
  clearInterval(_mSHoldInterval);
  _mSHoldTimer = null; _mSHoldInterval = null;
  if (!_mSHoldFired && key !== undefined) { mHaptic(20); mSStep(key, dir, 1); }
  _mSHoldFired = false;
}

// mSStep — steps a stepper value by dir * amt, enforces minimum, updates the
// display, and schedules a debounced save. For threshold keys (r-autoexcl,
// s-autoexcl) it also:
//   1. Greys or ungreys the paired unexclude row via mSyncAutoExclUi.
//   2. Checks whether the value transitioned from >0 to 0 with existing
//      auto-exclusions present, and fires the disabled popup if so.
function mSStep(key, dir, amt) {
  const prev = M_S_VALS[key];
  M_S_VALS[key] = Math.max(M_S_MINS[key], M_S_VALS[key] + dir * (amt || 1));
  const el = document.getElementById('m-sv-' + key);
  if (el) { el.textContent = M_S_VALS[key]; el.classList.toggle('m-zero', M_S_VALS[key] === 0); }

  // Sync unexclude row grey state whenever a threshold key changes.
  if (key in M_S_THRESHOLD_KEYS) {
    mSyncAutoExclUi(key);
    // Fire disabled popup when threshold transitions from >0 to exactly 0.
    // prev > 0 guard prevents firing on hold-repeat once already at 0.
    if (prev > 0 && M_S_VALS[key] === 0) {
      mMaybeShowAutoExclDisabledPopup();
    }
  }

  clearTimeout(M_S_SAVE_TIMER);
  M_S_SAVE_TIMER = setTimeout(mSSave, 800);
}

// mSyncAutoExclUi — greys out the Unexclude Days stepper row when the paired
// threshold is 0 (auto-exclusion disabled for that app), matching the desktop
// syncAutoExclUi() behaviour. Called from mSStep and mPopulateSettings.
// key must be a threshold key present in M_S_THRESHOLD_KEYS.
function mSyncAutoExclUi(key) {
  const rowId = M_S_THRESHOLD_KEYS[key];
  const row = document.getElementById(rowId);
  if (!row) return;
  const on = M_S_VALS[key] > 0;
  row.style.opacity = on ? '' : '.38';
  row.style.pointerEvents = on ? '' : 'none';
}

// mMaybeShowAutoExclDisabledPopup — queries current auto-exclusions and shows
// the disabled popup only if rows exist to act on. Mirrors the desktop
// _maybeShowAutoExclDisabledPopup logic (combined total, neutral "title(s)"
// label since clearing is a global action across all apps).
async function mMaybeShowAutoExclDisabledPopup() {
  try {
    const data = await api('/api/exclusions');
    const autoRows = (data || []).filter(e => e.source === 'auto');
    if (autoRows.length === 0) return;
    const count = autoRows.length;
    const bodyEl = document.getElementById('m-autoexcl-disabled-body');
    if (bodyEl) {
      bodyEl.textContent = `You have ${count} auto-excluded title${count !== 1 ? 's' : ''}. Clear them now or keep them?`;
    }
    const modal = document.getElementById('m-autoexcl-disabled-modal');
    if (modal) { modal.style.display = 'flex'; modal.classList.add('m-visible'); }
  } catch(e) { /* silent — popup is non-critical */ }
}

// mOnAutoExclDisabledCancel — closes the popup, leaving all auto-exclusions intact.
function mOnAutoExclDisabledCancel() {
  const modal = document.getElementById('m-autoexcl-disabled-modal');
  if (modal) { modal.classList.remove('m-visible'); setTimeout(() => { modal.style.display = 'none'; }, 300); }
}

// mOnAutoExclDisabledClear — deletes all auto-exclusion rows then closes the
// popup. Refreshes the exclusion count badge after clearing.
async function mOnAutoExclDisabledClear() {
  try {
    await api('/api/exclusions/clear-auto', {method: 'POST'});
    mRefreshMobileAutoExclBadge();
  } catch(e) { /* silent */ }
  mOnAutoExclDisabledCancel();
}

async function mSSave() {
  const updates = {};
  Object.entries(M_S_CFG_KEYS).forEach(([k, cfgKey]) => { updates[cfgKey] = M_S_VALS[k]; });
  try {
    const cfg = await api('/api/config');
    Object.assign(cfg, updates);
    await api('/api/config', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(cfg)});
    Object.assign(CFG, updates);
  } catch(e) {}
}

function mSetSeg(app, val, el) {
  const seg = document.getElementById('m-seg-' + app);
  if (seg) seg.querySelectorAll('.m-seg-opt').forEach(o => o.classList.remove('m-seg-active'));
  el.classList.add('m-seg-active');
  const cfgKey = app === 'radarr' ? 'radarr_sample_mode' : 'sonarr_sample_mode';
  mSaveCfgKeys({[cfgKey]: val});
}

// mPopulateSettings — reads CFG and sets all stepper display values, segment
// control states, and notification toggles. Called on init and when returning
// to the Settings tab. Auto-exclusion fields added in v4.1.0.
function mPopulateSettings() {
  if (!CFG) return;
  M_S_VALS.cooldown          = CFG.cooldown_hours ?? 48;
  M_S_VALS['r-cutoff']       = CFG.radarr_max_movies_per_run ?? 3;
  M_S_VALS['s-cutoff']       = CFG.sonarr_max_episodes_per_run ?? 5;
  M_S_VALS['r-autoexcl']     = CFG.auto_exclude_movies_threshold ?? 0;
  M_S_VALS['r-unexclude']    = CFG.auto_unexclude_movies_days ?? 0;
  M_S_VALS['s-autoexcl']     = CFG.auto_exclude_shows_threshold ?? 0;
  M_S_VALS['s-unexclude']    = CFG.auto_unexclude_shows_days ?? 0;

  Object.keys(M_S_VALS).forEach(k => {
    const el = document.getElementById('m-sv-' + k);
    if (el) { el.textContent = M_S_VALS[k]; el.classList.toggle('m-zero', M_S_VALS[k] === 0); }
  });

  // Apply greyed state for unexclude rows based on loaded threshold values.
  Object.keys(M_S_THRESHOLD_KEYS).forEach(k => mSyncAutoExclUi(k));

  // Sample mode segs
  const modeMap = {random: 0, alphabetical: 1, oldest_added: 2, newest_added: 3};
  ['radarr','sonarr'].forEach(app => {
    const seg = document.getElementById('m-seg-' + app);
    if (!seg) return;
    const cfgKey = app + '_sample_mode';
    const val = CFG[cfgKey] || 'random';
    seg.querySelectorAll('.m-seg-opt').forEach((opt, i) => opt.classList.toggle('m-seg-active', i === (modeMap[val] ?? 0)));
  });

  // Notifications
  const tog = document.getElementById('m-toggle-notify-settings');
  if (tog) tog.classList.toggle('m-on', !!CFG.notify_enabled);
  mSyncNotifyEvents();
}

function mToggleNotifySettings() {
  mHaptic(40);
  mSaveCfgKeys({notify_enabled: !CFG.notify_enabled}).then(() => mSyncNotifyEvents());
}

// mToggleNotifyEvent — toggles a single notification event flag and syncs UI.
// auto_exclusion key added in v4.1.0 to match notify_on_auto_exclusion in CFG.
function mToggleNotifyEvent(type) {
  mHaptic(40);
  let key;
  if (type === 'sweep_complete')  key = 'notify_on_sweep_complete';
  else if (type === 'import')     key = 'notify_on_import';
  else if (type === 'auto_exclusion') key = 'notify_on_auto_exclusion';
  else if (type === 'error')      key = 'notify_on_error';
  if (key) mSaveCfgKeys({[key]: !CFG[key]}).then(() => mSyncNotifyEvents());
}

// mSyncNotifyEvents — reflects CFG notification flags onto all toggle elements.
// Dims the events block when master notify_enabled is off. Auto-exclusion
// toggle added in v4.1.0.
function mSyncNotifyEvents() {
  if (!CFG) return;
  const enabled = !!CFG.notify_enabled;
  const tog = document.getElementById('m-toggle-notify-settings');
  if (tog) tog.classList.toggle('m-on', enabled);
  const events = document.getElementById('m-notify-events');
  if (events) events.style.opacity = enabled ? '' : '.38';
  if (events) events.style.pointerEvents = enabled ? '' : 'none';
  const togSweep      = document.getElementById('m-toggle-notify-sweep');
  const togImport     = document.getElementById('m-toggle-notify-import');
  const togAutoExcl   = document.getElementById('m-toggle-notify-auto-exclusion');
  const togError      = document.getElementById('m-toggle-notify-error');
  if (togSweep)    togSweep.classList.toggle('m-on',    !!CFG.notify_on_sweep_complete);
  if (togImport)   togImport.classList.toggle('m-on',   !!CFG.notify_on_import);
  if (togAutoExcl) togAutoExcl.classList.toggle('m-on', CFG.notify_on_auto_exclusion !== false);
  if (togError)    togError.classList.toggle('m-on',    !!CFG.notify_on_error);
}


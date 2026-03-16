// ── Portrait Settings tab ───────────────────────────────────────────────────
// M_S_VALS, M_S_MINS, M_S_CFG_KEYS, M_S_HOLD_INCS state;
// mSHoldStart, mSHoldEnd, mSStep, mSSave, mSetSeg, mPopulateSettings,
// mToggleNotifySettings, mToggleNotifyEvent, mSyncNotifyEvents

// ── Settings tab ───────────────────────────────────────────────────────────

// M_S_VALS / M_S_MINS / M_S_CFG_KEYS / M_S_HOLD_INCS — stepper state for the
// portrait Settings tab. Steppers map short UI keys (cooldown, r-cutoff, s-cutoff)
// to CFG field names and enforce per-field minimums.
const M_S_VALS = {cooldown: 48, 'r-cutoff': 3, 's-cutoff': 5};
const M_S_MINS = {cooldown: 0, 'r-cutoff': 0, 's-cutoff': 0};
const M_S_CFG_KEYS = {
  cooldown: 'cooldown_hours',
  'r-cutoff': 'radarr_max_movies_per_run',
  's-cutoff': 'sonarr_max_episodes_per_run',
};
// M_S_HOLD_INCS — the accelerated increment applied when the user holds a stepper
// button past the 500ms threshold (hold-to-accelerate pattern).
const M_S_HOLD_INCS = {cooldown: 24, 'r-cutoff': 1, 's-cutoff': 1};
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

function mSStep(key, dir, amt) {
  M_S_VALS[key] = Math.max(M_S_MINS[key], M_S_VALS[key] + dir * (amt || 1));
  const el = document.getElementById('m-sv-' + key);
  if (el) { el.textContent = M_S_VALS[key]; el.classList.toggle('m-zero', M_S_VALS[key] === 0); }
  clearTimeout(M_S_SAVE_TIMER);
  M_S_SAVE_TIMER = setTimeout(mSSave, 800);
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

function mPopulateSettings() {
  if (!CFG) return;
  M_S_VALS.cooldown = CFG.cooldown_hours ?? 48;
  M_S_VALS['r-cutoff'] = CFG.radarr_max_movies_per_run ?? 3;
  M_S_VALS['s-cutoff'] = CFG.sonarr_max_episodes_per_run ?? 5;
  Object.keys(M_S_VALS).forEach(k => {
    const el = document.getElementById('m-sv-' + k);
    if (el) { el.textContent = M_S_VALS[k]; el.classList.toggle('m-zero', M_S_VALS[k] === 0); }
  });
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

function mToggleNotifyEvent(type) {
  mHaptic(40);
  let key;
  if (type === 'sweep_complete') key = 'notify_on_sweep_complete';
  else if (type === 'import') key = 'notify_on_import';
  else if (type === 'error') key = 'notify_on_error';
  if (key) mSaveCfgKeys({[key]: !CFG[key]}).then(() => mSyncNotifyEvents());
}

function mSyncNotifyEvents() {
  if (!CFG) return;
  const enabled = !!CFG.notify_enabled;
  const tog = document.getElementById('m-toggle-notify-settings');
  if (tog) tog.classList.toggle('m-on', enabled);
  // Sync Home toggle too
  const homeTog = document.getElementById('m-toggle-notify');
  if (homeTog) homeTog.classList.toggle('m-on', enabled);
  const events = document.getElementById('m-notify-events');
  if (events) events.style.opacity = enabled ? '' : '.38';
  if (events) events.style.pointerEvents = enabled ? '' : 'none';
  const togSweep = document.getElementById('m-toggle-notify-sweep');
  const togImport = document.getElementById('m-toggle-notify-import');
  const togError = document.getElementById('m-toggle-notify-error');
  if (togSweep) togSweep.classList.toggle('m-on', !!CFG.notify_on_sweep_complete);
  if (togImport) togImport.classList.toggle('m-on', !!CFG.notify_on_import);
  if (togError) togError.classList.toggle('m-on', !!CFG.notify_on_error);
}


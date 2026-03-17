// ── Core globals, polling loop, API wrapper, tab switching, and activity ping ──
// Loaded first. Provides shared state and utilities consumed by all other UI modules.

const MOBILE = Math.min(window.screen.width, window.screen.height) <= 500;
let CFG = null;            // Live config object; refreshed by loadAll() and after each save
let PAGE = 0;              // Current page index for the History tab
let HISTORY_TOTAL = 0;     // Total history item count from the last fetch (used for pagination)
let IMPORTS_PAGE = 0;      // Current page index for the Imports/Stats tab
let IMPORTS_TOTAL = 0;     // Total import count from the last fetch (used for pagination)
let ALL_INSTANCES = [];    // Flat ordered list of {key, name, app} built from CFG; used by dropdowns
// confirmResolve — stores the Promise resolver for the shared confirm-modal pattern.
// Set by showConfirm(), called by the OK/Cancel buttons, cleared after each use.
let confirmResolve = null;
let ACTIVE_TAB = 'instances';
let HISTORY_SORT = { col: 'last_searched', dir: 'desc' };
let IMPORTS_SORT = { col: 'imported_ts', dir: 'desc' };
let EXCLUSIONS_SET = new Set();
let EXCL_FILTER_ACTIVE = false;

async function showConfirm(title, msg, okLabel = 'Confirm', danger = false) {
  el('confirmTitle').textContent = title;
  el('confirmMsg').textContent = msg;
  el('confirmOkBtn').textContent = okLabel;
  el('confirmOkBtn').className = danger ? 'btn sm danger' : 'btn sm primary';
  el('confirmModal').style.display = 'flex';
  return new Promise(resolve => { confirmResolve = (v) => { el('confirmModal').style.display = 'none'; resolve(v); }; });
}

function showAlert(msg) {
  el('alertMsg').textContent = msg;
  el('alertModal').style.display = 'flex';
}
function el(id) { return document.getElementById(id); }
function escapeHtml(s) {
  return (s || '').toString()
    .replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;')
    .replaceAll('"','&quot;').replaceAll("'",'&#39;');
}

function fmtTime(s) {
  if (!s) return '—';
  try { return new Date(s).toLocaleString(); } catch(e) { return s; }
}

async function api(path, opts) {
  const r = await fetch(path, opts || {});
  if (r.status === 401) { window.location.href = '/login'; return; }
  const ct = r.headers.get('content-type') || '';
  const data = ct.includes('application/json') ? await r.json() : await r.text();
  if (!r.ok) throw new Error(typeof data === 'string' ? data : JSON.stringify(data));
  return data;
}

function updateStatusPill(schedulerEnabled) {
  const dot = el('dot-scheduler');
  if (schedulerEnabled) {
    dot.classList.add('ok');
    el('txt-scheduler').textContent = 'AUTO';
  } else {
    dot.classList.remove('ok');
    el('txt-scheduler').textContent = 'MANUAL';
  }
}

async function loadAll() {
  CFG = await api('/api/config');
  const st = await api('/api/status');
  el('ver').textContent = st.version;
  el('lastRun').textContent = fmtTime(st.last_run_utc);
  el('nextRun').textContent = (CFG && (CFG.scheduler_enabled)) ? fmtTime(st.next_run_utc) : 'Manual';
  updateStatusPill(CFG.scheduler_enabled);
  updateContainerTime(st.container_time);
  await loadExclusions();

  // Show logout button when auth is enabled
  const lb = el('logoutBtn');
  if (lb) lb.style.display = CFG.auth_enabled !== false ? 'inline-flex' : 'none';

  // Support link
  const sl = el('supportLink');
  if (sl) sl.style.display = CFG.show_support_link !== false ? 'inline-flex' : 'none';

  // Build instance list
  ALL_INSTANCES = [];
  (CFG.instances?.radarr || []).forEach(i => ALL_INSTANCES.push({key: i.name+'|'+i.url.replace(/\/$/,''), name: i.name, app:'radarr'}));
  (CFG.instances?.sonarr || []).forEach(i => ALL_INSTANCES.push({key: i.name+'|'+i.url.replace(/\/$/,''), name: i.name, app:'sonarr'}));

  renderInstances('radarr');
  renderInstances('sonarr');
  fillSettings();
  fillAdvanced();
  fillNotifications();
  // Restore overrides tab visibility
  const ovTab = el('tab-btn-overrides');
  if (ovTab && CFG.per_instance_overrides_enabled) ovTab.classList.add('ov-tab-visible');
  else if (ovTab) ovTab.classList.remove('ov-tab-visible');
  // Sync mobile overrides state (portrait sub-labels + landscape nav)
  if (typeof mOvUpdateSubLabels === 'function') mOvUpdateSubLabels();
  if (typeof mInitRunBtn === 'function') mInitRunBtn();
}
// ── Page size memory (shared across History and Stats) ──
function syncPageSize(source) {
  const val = el(source === 'history' ? 'historyLimit' : 'importsLimit').value;
  const other = el(source === 'history' ? 'importsLimit' : 'historyLimit');
  if (other && other.value !== val) other.value = val;
}
async function openArrLink(app, instance, itemId, seriesId) {
  try {
    let url = `/api/arr-link?app=${encodeURIComponent(app)}&instance=${encodeURIComponent(instance)}&item_id=${encodeURIComponent(itemId)}`;
    if (seriesId) url += `&series_id=${encodeURIComponent(seriesId)}`;
    const data = await api(url);
    if (data.ok && data.url) {
      window.open(data.url, '_blank');
    } else {
      showAlert('Could not open in ' + (app === 'radarr' ? 'Radarr' : 'Sonarr') + ': ' + (data.error || 'Unknown error'));
    }
  } catch(e) {
    showAlert('Link failed: ' + e.message);
  }
}


// _wasRunning — tracks whether a sweep was in progress on the previous poll tick.
// When it flips from true to false the just-completed run triggers a one-time
// history/sweep refresh without waiting for the 30-second auto-refresh window.
let _wasRunning = false;
async function refreshStatus() {
  try {
    const st = await api('/api/status');
    el('ver').textContent = st.version;
    const isRunning = !!st.run_in_progress;
    if (!isRunning) el('lastRun').textContent = fmtTime(st.last_run_utc);
    if (isRunning) {
      el('dot-scheduler').classList.add('running');
      el('wordmark').classList.add('sweeping');
      el('wordmark')._pendingStop = false;
    } else {
      el('dot-scheduler').classList.remove('running');
      const wm = el('wordmark');
      if (wm.classList.contains('sweeping')) {
        wm._pendingStop = true;
        wm.addEventListener('animationiteration', function done() {
          if (wm._pendingStop) {
            wm.classList.remove('sweeping');
            wm._pendingStop = false;
          }
          wm.removeEventListener('animationiteration', done);
        });
      }
      if (_wasRunning) {
        AUTO_REFRESH_LAST = 0;
        HISTORY_SORT = { col: 'last_searched', dir: 'desc' };
        if (ACTIVE_TAB === 'history') refreshHistory();
        if (ACTIVE_TAB === 'sweep') refreshSweep();
      }
    }
    _wasRunning = isRunning;
    el('nextRun').textContent = (CFG && (CFG.scheduler_enabled)) ? fmtTime(st.next_run_utc) : 'Manual';
    updateStatusPill(CFG?.scheduler_enabled);
    updateContainerTime(st.container_time);
    refreshDotsFromStatus(st.instance_health || {});
  } catch(e) {}
}

// Tracks instances mid-toggle so poll doesn't race their dot
const TOGGLE_IN_PROGRESS = new Set();

function refreshDotsFromStatus(health) {
  if (!health) return;
  Object.entries(health).forEach(([key, state]) => {
    const [app, ...nameParts] = key.split('|');
    const name = nameParts.join('|');
    const cfgIdx = (CFG?.instances?.[app] || []).findIndex(i => i.name === name);
    if (cfgIdx >= 0) {
      const dotKey = `${app}-${cfgIdx}`;
      // Skip dots that are mid-toggle — toggleInstance manages those directly
      if (TOGGLE_IN_PROGRESS.has(dotKey)) return;
      const dot = el(`sdot-${dotKey}`);
      if (!dot) return;
      if (state === 'ok') dot.className = 'status-dot ok';
      else if (state === 'bad') dot.className = 'status-dot bad';
      else if (state === 'disabled') dot.className = 'status-dot disabled';
      else dot.className = 'status-dot';
    }
    // Mirror dot state to Sweep tab card if present
    const sweepDot = el(`sdot-sweep-${key}`);
    if (sweepDot) {
      if (state === 'ok') sweepDot.className = 'status-dot ok';
      else if (state === 'bad') sweepDot.className = 'status-dot bad';
      else if (state === 'disabled') sweepDot.className = 'status-dot disabled';
      else sweepDot.className = 'status-dot';
    }
  });
}

// AUTO_REFRESH_LAST — Date.now() timestamp of the last data-tab auto-refresh.
// pollCycle() checks this to throttle background refreshes to once every 30 seconds,
// independent of the 5-second status-pill poll.
let AUTO_REFRESH_LAST = 0;
async function pollCycle() {
  await refreshStatus();
  const now = Date.now();
  if (now - AUTO_REFRESH_LAST >= 30000) {
    AUTO_REFRESH_LAST = now;
    if (ACTIVE_TAB === 'history') refreshHistory();
    if (ACTIVE_TAB === 'imports') refreshImports();
    if (ACTIVE_TAB === 'sweep') refreshSweep();
  }
}

if (!MOBILE) {
  loadAll().then(() => {
    // Only pulse checking on enabled instances — disabled stay grey
    (CFG?.instances?.radarr || []).forEach((inst, idx) => {
      if (inst.enabled !== false) {
        const d = el(`sdot-radarr-${idx}`);
        if (d) d.className = 'status-dot checking';
      }
    });
    (CFG?.instances?.sonarr || []).forEach((inst, idx) => {
      if (inst.enabled !== false) {
        const d = el(`sdot-sonarr-${idx}`);
        if (d) d.className = 'status-dot checking';
      }
    });
    maybeShowOnboarding();
    if (!CFG || CFG.onboarding_complete) maybeShowWhatsNew();
  });
  setInterval(pollCycle, 5000);
}

// ══════════════════════════════════════════════════════════════════════════
// MOBILE UI
// ══════════════════════════════════════════════════════════════════════════
// ── Activity ping — updates session last_active on real user interaction only ──
// Background polling does NOT reset the session timer. Only clicks, keypresses,
// and scrolls count as activity. Debounced to fire at most once every 15 seconds.
(function() {
  let _pingTimer = null;
  function _ping() {
    fetch('/api/ping', { method: 'POST', credentials: 'same-origin' }).catch(() => {});
  }
  function _onActivity() {
    if (_pingTimer) return;
    _ping();
    _pingTimer = setTimeout(() => { _pingTimer = null; }, 15000);
  }
  ['click', 'keydown', 'scroll', 'touchstart'].forEach(ev =>
    document.addEventListener(ev, _onActivity, { passive: true })
  );
})();

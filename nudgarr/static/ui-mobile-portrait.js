  let M_TAB = 'home';
  let M_OPEN_SWEEP = null;

  // ── Haptics ──
  function mSwitchTab(name) {
    // Sweep tab — if no instances configured, redirect to Instances
    if (name === 'sweep') {
      const radarr = CFG?.instances?.radarr || [];
      const sonarr = CFG?.instances?.sonarr || [];
      if (!radarr.length && !sonarr.length) {
        mSwitchTab('instances');
        return;
      }
    }
    document.querySelectorAll('.m-tab').forEach(t => t.classList.remove('m-active'));
    document.querySelectorAll('.m-nav-item').forEach(n => n.classList.remove('m-active'));
    const tab = document.getElementById('m-' + name);
    const nav = document.getElementById('m-nav-' + name);
    if (tab) tab.classList.add('m-active');
    if (nav) nav.classList.add('m-active');
    M_TAB = name;
    if (name === 'sweep') mRenderSweep();
    if (name === 'instances') mRenderInstances();
  }

  // ── Portrait swipe between tabs ──
  (function() {
    const ui = document.getElementById('mobile-ui');
    if (!ui) return;
    const TAB_ORDER = ['home', 'instances', 'sweep'];
    let sx = null, sy = null;
    ui.addEventListener('touchstart', e => {
      sx = e.touches[0].clientX;
      sy = e.touches[0].clientY;
    }, { passive: true });
    ui.addEventListener('touchend', e => {
      if (sx === null) return;
      const dx = e.changedTouches[0].clientX - sx;
      const dy = e.changedTouches[0].clientY - sy;
      if (Math.abs(dx) >= 30 && Math.abs(dx) >= Math.abs(dy) * 1.5) {
        const idx = TAB_ORDER.indexOf(M_TAB);
        if (dx < 0 && idx < TAB_ORDER.length - 1) mSwitchTab(TAB_ORDER[idx + 1]);
        if (dx > 0 && idx > 0) mSwitchTab(TAB_ORDER[idx - 1]);
      }
      sx = null;
    }, { passive: true });
  })();

  // ── Home ──

  function mUpdateHome(cfg, st) {
    const lastEl = document.getElementById('m-last-run');
    if (lastEl) lastEl.textContent = fmtTime(st.last_run_utc);
    const nextEl = document.getElementById('m-next-run');
    if (nextEl) nextEl.textContent = (cfg.scheduler_enabled) ? fmtTime(st.next_run_utc) : 'Manual';
    const pill = document.getElementById('m-running-pill');
    if (pill) pill.classList.toggle('hidden', !st.run_in_progress);
    const autoActive = cfg.scheduler_enabled;
    const autoSub = document.getElementById('m-auto-sub');
    if (autoSub) {
      if (cfg.scheduler_enabled) {
        autoSub.textContent = describeCron(cfg.cron_expression || '');
      } else {
        autoSub.textContent = 'Manual';
      }
    }
    const tAuto = document.getElementById('m-toggle-auto');
    if (tAuto) tAuto.classList.toggle('m-on', !!autoActive);
    const tNotify = document.getElementById('m-toggle-notify');
    if (tNotify) tNotify.classList.toggle('m-on', !!cfg.notify_enabled);
    const tRadarrBacklog = document.getElementById('m-toggle-radarr-backlog');
    if (tRadarrBacklog) tRadarrBacklog.classList.toggle('m-on', !!cfg.radarr_backlog_enabled);
    const tSonarrBacklog = document.getElementById('m-toggle-sonarr-backlog');
    if (tSonarrBacklog) tSonarrBacklog.classList.toggle('m-on', !!cfg.sonarr_backlog_enabled);
  }

  // ── Run Now long press ──

  let M_LONGPRESS_TIMER = null;

  function mInitRunBtn() {
    const btn = document.getElementById('m-run-btn');
    if (!btn) return;
    if (localStorage.getItem('nudgarr_hint_dismissed')) {
      const wrap = document.getElementById('m-run-hint-wrap');
      if (wrap) wrap.classList.add('m-hint-gone');
    }
    btn.addEventListener('mousedown', () => mStartLongPress());
    btn.addEventListener('touchstart', e => { e.preventDefault(); mStartLongPress(); }, {passive: false});
    btn.addEventListener('mouseup', () => mCancelLongPress(true));
    btn.addEventListener('mouseleave', () => mCancelLongPress(false));
    btn.addEventListener('touchend', () => mCancelLongPress(true));
    btn.addEventListener('touchcancel', () => mCancelLongPress(false));
  }

  function mStartLongPress() {
    const btn = document.getElementById('m-run-btn');
    if (btn) { btn.style.transition = 'opacity .15s ease'; btn.style.opacity = '0.6'; }
    M_LONGPRESS_TIMER = setTimeout(() => {
      M_LONGPRESS_TIMER = null;
      mHaptic(40);
      const btn2 = document.getElementById('m-run-btn');
      if (btn2) { btn2.style.opacity = ''; btn2.style.transition = ''; }
      mDismissHint();
      mOpenQS();
    }, 500);
  }

  function mCancelLongPress(doRun) {
    if (M_LONGPRESS_TIMER) {
      clearTimeout(M_LONGPRESS_TIMER);
      M_LONGPRESS_TIMER = null;
      const btn = document.getElementById('m-run-btn');
      if (btn) { btn.style.opacity = ''; btn.style.transition = ''; }
      if (doRun) { mDismissHint(); mRunNow(); }
    }
  }

  function mDismissHint() {
    if (localStorage.getItem('nudgarr_hint_dismissed')) return;
    localStorage.setItem('nudgarr_hint_dismissed', '1');
    const wrap = document.getElementById('m-run-hint-wrap');
    if (wrap) wrap.classList.add('m-hint-gone');
  }

  async function mRunNow() {
    mHaptic(40);
    try {
      await api('/api/run-now', {method:'POST'});
      const lastEl = document.getElementById('m-last-run');
      if (lastEl) lastEl.textContent = 'Running…';
      const pill = document.getElementById('m-running-pill');
      if (pill) pill.classList.remove('hidden');
    } catch(e) {}
  }

  // ── Quick Settings sheet ──

  function mOpenQS() {
    M_QS_VALS.cooldown = CFG.cooldown_hours || 48;
    M_QS_VALS.movies = CFG.radarr_max_movies_per_run || 1;
    M_QS_VALS.episodes = CFG.sonarr_max_episodes_per_run || 1;
    ['cooldown','movies','episodes'].forEach(k => {
      const el = document.getElementById('m-qs-' + k);
      if (el) { el.textContent = M_QS_VALS[k]; el.classList.toggle('m-zero', M_QS_VALS[k] === 0); }
    });
    mSheetOpen('m-qs-sheet');
    mSheetDrag('m-qs-handle', 'm-qs-sheet', mCloseQS);
  }

  function mCloseQS() { mSheetClose('m-qs-sheet'); }
  const M_QS_HOLD_INCREMENTS = {cooldown: 24, movies: 1, episodes: 1};
  let _mQsHoldTimer = null;
  let _mQsHoldInterval = null;
  let _mQsHoldFired = false;

  function mQSHoldStart(key, dir) {
    _mQsHoldFired = false;
    _mQsHoldTimer = setTimeout(() => {
      _mQsHoldFired = true;
      const inc = M_QS_HOLD_INCREMENTS[key] || 1;
      mQSStep(key, dir, inc);
      _mQsHoldInterval = setInterval(() => {
        mHaptic(10);
        mQSStep(key, dir, inc);
      }, 400);
    }, 500);
  }

  function mQSHoldEnd(key, dir) {
    clearTimeout(_mQsHoldTimer);
    clearInterval(_mQsHoldInterval);
    _mQsHoldTimer = null;
    _mQsHoldInterval = null;
    if (!_mQsHoldFired && key !== undefined) {
      mHaptic(20);
      mQSStep(key, dir, 1);
    }
    _mQsHoldFired = false;
  }

  function mQSStep(key, dir, amt) {
    mHaptic(20);
    M_QS_VALS[key] = Math.max(M_QS_MINS[key], M_QS_VALS[key] + dir * (amt || 1));
    const el = document.getElementById('m-qs-' + key);
    if (el) { el.textContent = M_QS_VALS[key]; el.classList.toggle('m-zero', M_QS_VALS[key] === 0); }
    clearTimeout(M_QS_SAVE_TIMER);
    M_QS_SAVE_TIMER = setTimeout(mQSSave, 800);
  }

  async function mQSSave() {
    const updates = {
      cooldown_hours: M_QS_VALS.cooldown,
      radarr_max_movies_per_run: M_QS_VALS.movies,
      sonarr_max_episodes_per_run: M_QS_VALS.episodes,
    };
    try {
      const cfg = await api('/api/config');
      Object.assign(cfg, updates);
      await api('/api/config', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(cfg)});
      Object.assign(CFG, updates);
    } catch(e) {}
  }

  async function mQSRunNow() {
    mHaptic(40);
    clearTimeout(M_QS_SAVE_TIMER);
    await mQSSave();
    mCloseQS();
    await mRunNow();
  }


async function mSaveCfgKey(updates) {
  try {
    const cfg = await api('/api/config');
    Object.assign(cfg, updates);
    await api('/api/config', {method:'POST', body: JSON.stringify(cfg)});
    Object.assign(CFG, updates);
    mUpdateHome(CFG, {
      version: CFG.version,
      last_run_utc: null,
      next_run_utc: null,
      run_in_progress: false,
    });
    // Re-read status for accurate times
    const st = await api('/api/status');
    mUpdateHome(CFG, st);
  } catch(e) {}
}

function mToggleAuto() {
  mHaptic(40);
  mSaveCfgKey({scheduler_enabled: !CFG.scheduler_enabled});
}

function mToggleNotify() {
  mHaptic(40);
  const newVal = !CFG.notify_enabled;
  mSaveCfgKey({notify_enabled: newVal});
}

function mToggleRadarrBacklog() {
  mHaptic(40);
  mSaveCfgKey({radarr_backlog_enabled: !CFG.radarr_backlog_enabled});
}

function mToggleSonarrBacklog() {
  mHaptic(40);
  mSaveCfgKey({sonarr_backlog_enabled: !CFG.sonarr_backlog_enabled});
}
// ── Instances ──

function mRenderInstances() {
  const list = document.getElementById('m-inst-list');
  if (!list || !CFG) return;
  const cards = [];
  for (const kind of ['radarr', 'sonarr']) {
    (CFG.instances?.[kind] || []).forEach((inst, idx) => {
      const enabled = inst.enabled !== false;
      const healthKey = `${kind}|${inst.name}`;
      const health = (STATUS_CACHE && STATUS_CACHE[healthKey]) || 'checking';
      const dotClass = health === 'ok' ? 'ok' : health === 'bad' ? 'bad' : health === 'disabled' ? 'disabled' : '';
      cards.push(`
        <div class="m-inst-card">
          <div class="m-inst-name-row">
            <span class="status-dot ${dotClass}" id="m-dot-${kind}-${idx}"></span>
            <span class="m-inst-name">${escapeHtml(inst.name)}</span>
          </div>
          <div class="m-inst-url">${escapeHtml((inst.url || '').replace(/\/$/, ''))}</div>
          <button class="m-inst-btn ${enabled ? 'm-inst-disable' : 'm-inst-enable'}"
            onclick="mToggleInstance('${kind}', ${idx})">
            ${enabled ? 'Disable' : 'Enable'}
          </button>
        </div>`);
    });
  }
  list.innerHTML = cards.join('') || '<p class="help" style="text-align:center;padding:24px 0">No instances configured.</p>';
}

let STATUS_CACHE = {};

async function mToggleInstance(kind, idx) {
  try {
  mHaptic(40);
    await api('/api/instance/toggle', {method:'POST', body: JSON.stringify({kind, idx})});
    await loadAll();
    mRenderInstances();
  } catch(e) {}
}

// ── Sweep ──

function mRenderSweep() {
  const list = document.getElementById('m-sweep-list');
  if (!list || !CFG) return;
  const cards = [];
  const legacyMode = CFG.sample_mode || 'random';
  function fmtMode(m) {
    return (m || 'random').split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
  }
  for (const kind of ['radarr', 'sonarr']) {
    (CFG.instances?.[kind] || []).forEach((inst) => {
      const key = `${kind}|${inst.name}`;
      const disabled = inst.enabled === false;
      const cached = SWEEP_DATA_CACHE[key] || null;
      const hasData = cached != null;
      const modeKey = kind === 'radarr' ? 'radarr_sample_mode' : 'sonarr_sample_mode';
      const mode = CFG[modeKey] || legacyMode;
      const isOpen = (M_OPEN_SWEEP === null && cards.length === 0) || M_OPEN_SWEEP === key;
      cards.push(`
        <div class="m-sweep-card ${isOpen ? 'm-open' : ''}" data-key="${key}" onclick="mAccordion(this)">
          <div class="m-sweep-hdr">
            <div class="m-sweep-hdr-left">
              <span class="status-dot ${disabled ? 'disabled' : 'ok'}" id="m-sdot-${key}"></span>
              <span class="m-sweep-name">${escapeHtml(inst.name)}</span>
            </div>
            <span class="m-sweep-chevron">▼</span>
          </div>
          <div class="m-sweep-body">
            ${disabled ? '<p class="m-sweep-meta">Disabled</p>' : `
            <div class="m-sweep-meta">${fmtMode(mode)}</div>
            <div class="m-stat-section">LIBRARY STATE</div>
            <div class="m-stat-grid">
              <div><div class="m-stat-label">Cutoff Unmet</div><div class="m-stat-value ${hasData ? '' : 'm-dim'}">${hasData ? (cached.cutoffUnmet ?? '—') : '—'}</div></div>
              <div><div class="m-stat-label">Backfill</div><div class="m-stat-value ${hasData ? '' : 'm-dim'}">${hasData ? (cached.backfill ?? '—') : '—'}</div></div>
            </div>
            <div class="m-stat-section">THIS RUN</div>
            <div class="m-stat-grid">
              <div><div class="m-stat-label">Eligible</div><div class="m-stat-value ${hasData ? '' : 'm-dim'}">${hasData ? cached.eligible : '—'}</div></div>
              <div><div class="m-stat-label">On Cooldown</div><div class="m-stat-value ${hasData ? '' : 'm-dim'}">${hasData ? cached.onCooldown : '—'}</div></div>
              <div><div class="m-stat-label">Capped</div><div class="m-stat-value ${hasData ? '' : 'm-dim'}">${hasData ? cached.capped : '—'}</div></div>
              <div><div class="m-stat-label">Searched</div><div class="m-stat-value ${hasData ? '' : 'm-dim'}">${hasData ? cached.searched : '—'}</div></div>
            </div>`}
          </div>
        </div>`);
    });
  }
  list.innerHTML = cards.join('') || '<p class="help" style="text-align:center;padding:24px 0">No instances configured.</p>';
}

function mAccordion(card) {
  const key = card.dataset.key;
  const wasOpen = card.classList.contains('m-open');
  // Close all
  document.querySelectorAll('#m-sweep-list .m-sweep-card').forEach(c => c.classList.remove('m-open'));
  // Open tapped unless it was already open — but always keep one open
  if (!wasOpen) {
    card.classList.add('m-open');
    M_OPEN_SWEEP = key;
  } else {
    // Re-open first card since we can't have none open
    const first = document.querySelector('#m-sweep-list .m-sweep-card');
    if (first) { first.classList.add('m-open'); M_OPEN_SWEEP = first.dataset.key; }
  }
}

// ── Exclusions sheet ──

let M_EXCL_DATA = [];
let M_EXCL_HIST_DATA = [];

async function mOpenExclusions() {
  mSwitchExclTab('excl');
  await mLoadExclusions();
  mSheetOpen('m-excl-sheet');
  mSheetDrag('m-excl-handle', 'm-excl-sheet', mCloseExclusions);
  mExclBindEvents();
}

function mExclBindEvents() {
  const listEl = document.getElementById('m-excl-list');
  const histEl = document.getElementById('m-excl-hist');
  if (listEl && !listEl._bound) {
    listEl._bound = true;
    listEl.addEventListener('click', e => {
      const btn = e.target.closest('[data-title]');
      if (btn && btn.classList.contains('m-excl-remove')) { mBtnPress(btn); mExclRemove(btn.dataset.title); }
    });
  }
  if (histEl && !histEl._bound) {
    histEl._bound = true;
    histEl.addEventListener('click', e => {
      const btn = e.target.closest('[data-title]');
      if (btn && btn.classList.contains('m-hist-add')) { mBtnPress(btn); mExclAdd(btn.dataset.title); }
    });
  }
}


function mCloseExclusions() {
  mSheetClose('m-excl-sheet', () => {
    const navItem = document.getElementById('m-nav-exclusions');
    if (navItem) navItem.classList.remove('m-active');
  });
}

function mSwitchExclTab(tab) {
  const listPane = document.getElementById('m-excl-list');
  const histPane = document.getElementById('m-excl-hist');
  const tabExcl = document.getElementById('m-excl-tab-excl');
  const tabAdd = document.getElementById('m-excl-tab-add');
  if (tab === 'excl') {
    if (listPane) listPane.style.display = '';
    if (histPane) histPane.style.display = 'none';
    if (tabExcl) tabExcl.classList.add('m-active');
    if (tabAdd) tabAdd.classList.remove('m-active');
  } else {
    if (listPane) listPane.style.display = 'none';
    if (histPane) histPane.style.display = '';
    if (tabExcl) tabExcl.classList.remove('m-active');
    if (tabAdd) tabAdd.classList.add('m-active');
    mLoadExclHistory();
  }
}

async function mLoadExclusions() {
  const listEl = document.getElementById('m-excl-list');
  const countEl = document.getElementById('m-excl-count');
  if (!listEl) return;
  try {
    const data = await api('/api/exclusions');
    M_EXCL_DATA = data || [];
    if (countEl) countEl.textContent = M_EXCL_DATA.length;
    if (!M_EXCL_DATA.length) {
      listEl.innerHTML = '<p class="help" style="text-align:center;padding:32px 18px">No exclusions yet.</p>';
      return;
    }
    listEl.innerHTML = M_EXCL_DATA.map(e => {
      const title = escapeHtml(e.title || '');
      return `<div class="m-excl-row">
        <span class="m-excl-title">${title}</span>
        <button class="m-excl-remove" data-title="${escapeHtml(e.title || '')}">Remove</button>
      </div>`;
    }).join('');
  } catch(err) {
    listEl.innerHTML = '<p class="help" style="color:var(--bad);text-align:center;padding:24px 18px">Failed to load exclusions.</p>';
  }
}

async function mExclRemove(title) {
  mHaptic(60);
  // Fade out the row first
  const listEl = document.getElementById('m-excl-list');
  if (listEl) {
    const rows = listEl.querySelectorAll('.m-excl-row');
    for (const row of rows) {
      const t = row.querySelector('.m-excl-title');
      if (t && t.textContent.trim() === title) { row.classList.add('m-fading'); break; }
    }
  }
  await new Promise(r => setTimeout(r, 300));
  try {
    await api('/api/exclusions/remove', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({title})});
    await mLoadExclusions();
  } catch(e) {
    if (listEl) listEl.insertAdjacentHTML('afterbegin', `<p class="help" style="color:var(--bad);padding:8px 18px">Remove failed: ${e.message}</p>`);
  }
}

async function mLoadExclHistory(silent = false) {
  const histEl = document.getElementById('m-excl-hist');
  if (!histEl) return;
  if (!silent) histEl.innerHTML = '<p class="help" style="text-align:center;padding:24px 18px;color:var(--muted)">Loading…</p>';
  try {
    const items = await api('/api/state/items?app=&instance=&offset=0&limit=500');
    M_EXCL_HIST_DATA = (items.items || []);
    const exclSet = new Set(M_EXCL_DATA.map(e => (e.title || '').toLowerCase()));
    const filtered = M_EXCL_HIST_DATA.filter(it => {
      const t = (it.title || it.key || '').toLowerCase();
      return t && !exclSet.has(t);
    });
    if (!filtered.length) {
      histEl.innerHTML = '<p class="help" style="text-align:center;padding:32px 18px">No search history yet.</p>';
      return;
    }
    histEl.innerHTML = filtered.map(it => {
      const title = it.title || it.key || '';
      const count = it.search_count > 1 ? ` · ×${it.search_count}` : '';
      const inst = it.instance ? ` · ${escapeHtml(it.instance)}` : '';
      const last = it.last_searched ? ` · ${fmtTime(it.last_searched)}` : '';
      return `<div class="m-hist-row">
        <div class="m-hist-info">
          <div class="m-hist-title">${escapeHtml(title)}</div>
          <div class="m-hist-meta">${escapeHtml(it.instance || '')}${count}${last}</div>
        </div>
        <span class="m-hist-add" data-title="${escapeHtml(title)}">+ Exclude</span>
      </div>`;
    }).join('');
  } catch(err) {
    histEl.innerHTML = '<p class="help" style="color:var(--bad);text-align:center;padding:24px 18px">Failed to load history.</p>';
  }
}

async function mExclAdd(title) {
  mHaptic(60);
  // Fade out the history row first
  const histEl = document.getElementById('m-excl-hist');
  if (histEl) {
    const rows = histEl.querySelectorAll('.m-hist-row');
    for (const row of rows) {
      const t = row.querySelector('.m-hist-title');
      if (t && t.textContent.trim() === title) { row.classList.add('m-fading'); break; }
    }
  }
  await new Promise(r => setTimeout(r, 300));
  try {
    await api('/api/exclusions/add', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({title})});
    await mLoadExclusions();
    await mLoadExclHistory(true);
  } catch(e) {
    if (histEl) histEl.insertAdjacentHTML('afterbegin', `<p class="help" style="color:var(--bad);padding:8px 18px">Add failed: ${e.message}</p>`);
  }
}

// ── Imports sheet ──

async function mOpenImports(type) {
  const titleEl = document.getElementById('m-imports-sheet-title');
  const bodyEl = document.getElementById('m-imports-sheet-body');
  if (titleEl) titleEl.textContent = type === 'movies' ? 'Movies (Imported)' : 'Episodes (Imported)';
  if (bodyEl) bodyEl.innerHTML = '<p class="help" style="text-align:center;padding:24px 18px;color:var(--muted)">Loading…</p>';
  mSheetOpen('m-imports-sheet');
  mSheetDrag('m-imports-handle', 'm-imports-sheet', mCloseImports);
  await mLoadImports(type);
}


function mCloseImports() {
  mSheetClose('m-imports-sheet');
}


async function mLoadImports(type) {
  const bodyEl = document.getElementById('m-imports-sheet-body');
  if (!bodyEl) return;
  try {
    // Fetch a generous page so scrolling works without pagination
    const data = await api('/api/stats?offset=0&limit=200');
    const app = type === 'movies' ? 'radarr' : 'sonarr';
    const entries = (data.entries || []).filter(e => e.app === app);
    if (!entries.length) {
      bodyEl.innerHTML = '<p class="help" style="text-align:center;padding:32px 18px">No confirmed imports yet.</p>';
      return;
    }
    bodyEl.innerHTML = entries.map(e => {
      const title = escapeHtml(e.title || e.item_id || '—');
      const date = e.imported_ts ? fmtTime(e.imported_ts) : '';
      const tagClass = e.type === 'Acquired' ? 'tag acquired' : 'tag';
      const iterSuffix = (e.iteration && e.iteration > 1) ? ` ×${e.iteration}` : '';
      const tagHtml = e.type ? `<span class="${tagClass}">${escapeHtml(e.type)}${escapeHtml(iterSuffix)}</span>` : '';
      return `<div class="m-import-row">
        <div class="m-import-row-left">
          <div class="m-import-row-title">${title}</div>
          ${tagHtml}
        </div>
        <span class="m-import-row-date">${escapeHtml(date)}</span>
      </div>`;
    }).join('');
  } catch(err) {
    bodyEl.innerHTML = '<p class="help" style="color:var(--bad);text-align:center;padding:24px 18px">Failed to load imports.</p>';
  }
}


// ── Module-level bridge ───────────────────────────────────────────────────────
// Allows ui-mobile-core.js to trigger a landscape tab switch without accessing
// block-scoped LS_TAB or lsSwitchTab directly (both live inside if(MOBILE)).
function lsSwitchTabSafe(idx) {
  if (typeof lsSwitchTab === 'function') lsSwitchTab(idx);
}

function lsIsOnOverridesTab() {
  return typeof LS_TAB !== 'undefined' && LS_TAB === 2;
}

// ── Mobile init ──

if (MOBILE) {
  // Force layout via JS — show mobile in portrait, desktop in landscape
  const wrap = document.querySelector('.wrap');
  const mobileUi = document.getElementById('mobile-ui');

  const MOBILE_UI_STYLE = 'display:flex; flex-direction:column; width:100%; height:100vh; height:100dvh; position:fixed; top:0; left:0; overflow:hidden;';

  const landscapeUi = document.getElementById('landscape-ui');
  const LS_UI_STYLE = 'display:flex; flex-direction:column; width:100%; height:100vh; height:100dvh; position:fixed; top:0; left:0; overflow:hidden;';
  let LS_DESKTOP_OVERRIDE = sessionStorage.getItem('nudgarr_desktop_override') === '1';

  function checkOrientation() {
    const isLandscape = window.innerWidth > window.innerHeight;
    if (!isLandscape) {
      // Portrait — always show portrait mobile, clear desktop override
      LS_DESKTOP_OVERRIDE = false;
      sessionStorage.removeItem('nudgarr_desktop_override');
      if (wrap) wrap.style.removeProperty('display'); // remove forced !important override
      if (landscapeUi) landscapeUi.style.display = 'none';
      if (mobileUi) mobileUi.style.cssText = MOBILE_UI_STYLE;
    } else if (LS_DESKTOP_OVERRIDE) {
      // Landscape + user chose desktop — force override of media query !important
      if (mobileUi) mobileUi.style.display = 'none';
      if (landscapeUi) landscapeUi.style.display = 'none';
      if (wrap) wrap.style.setProperty('display', 'block', 'important');
    } else {
      // Landscape — show landscape config UI
      if (mobileUi) mobileUi.style.display = 'none';
      if (wrap) wrap.style.display = 'none';
      if (landscapeUi) landscapeUi.style.cssText = LS_UI_STYLE;
      lsPopulate();
    }
  }
  checkOrientation();
  window.addEventListener('orientationchange', () => {
    if (wrap) wrap.style.setProperty('display', 'none', 'important');
    if (mobileUi) mobileUi.style.display = 'none';
    if (landscapeUi) landscapeUi.style.display = 'none';
    setTimeout(checkOrientation, 100);
  });
  window.addEventListener('resize', checkOrientation);
  loadAll().then(async () => {
    const st = await api('/api/status');
    STATUS_CACHE = st.instance_health || {};
    mUpdateHome(CFG, st);
    mRenderInstances();
    await refreshSweep();
    mRenderSweep();
    // Populate import pill totals on Home tab
    try {
      const stats = await api('/api/stats?offset=0&limit=1');
      const movEl = document.getElementById('m-movies-total');
      const showEl = document.getElementById('m-shows-total');
      if (movEl) movEl.textContent = stats.movies_total ?? '—';
      if (showEl) showEl.textContent = stats.shows_total ?? '—';
    } catch(e) {}
    maybeShowOnboarding();
    if (!CFG || CFG.onboarding_complete) maybeShowWhatsNew();
    // Re-populate landscape UI now that CFG is loaded — fixes landscape nav
    // icon not appearing when page loads directly in landscape orientation
    if (typeof lsPopulate === 'function') lsPopulate();
  });


  // ── Landscape UI ────────────────────────────────────────────────────────────

  const LS_VALS = {
    movies: 1, episodes: 1,
    cooldown: 48, batch: 1, sleep: 5, jitter: 2,
    'r-missing': 1, 'r-days': 14, 's-missing': 1,
  };
  const LS_MINS = {
    movies: 0, episodes: 0,
    cooldown: 0, batch: 1, sleep: 0, jitter: 0,
    'r-missing': 1, 'r-days': 1, 's-missing': 1,
  };
  const LS_CFG_KEYS = {
    movies:      'radarr_max_movies_per_run',
    episodes:    'sonarr_max_episodes_per_run',
    cooldown:    'cooldown_hours',
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
    LS_VALS.movies    = CFG.radarr_max_movies_per_run   ?? 1;
    LS_VALS.episodes  = CFG.sonarr_max_episodes_per_run ?? 1;
    LS_VALS.cooldown  = CFG.cooldown_hours              ?? 48;
    LS_VALS.batch     = CFG.batch_size                  ?? 1;
    LS_VALS.sleep     = CFG.sleep_seconds               ?? 5;
    LS_VALS.jitter    = CFG.jitter_seconds              ?? 2;
    LS_VALS['r-missing'] = CFG.radarr_missing_max          ?? 1;
    LS_VALS['r-days']    = CFG.radarr_missing_added_days   ?? 14;
    LS_VALS['s-missing'] = CFG.sonarr_missing_max          ?? 1;

    Object.keys(LS_VALS).forEach(k => {
      const el = document.getElementById('ls-v-' + k);
      if (el) { el.textContent = LS_VALS[k]; el.classList.toggle('ls-zero', LS_VALS[k] === 0); }
    });
    lsSetSegActive('radarr', CFG.radarr_sample_mode || 'random');
    lsSetSegActive('sonarr', CFG.sonarr_sample_mode || 'random');
    // Sync mobile overrides sub-labels and landscape nav visibility
    if (typeof mOvUpdateSubLabels === 'function') mOvUpdateSubLabels();
  }

  function lsSetSegActive(which, val) {
    const map = { random: 0, alphabetical: 1, oldest_added: 2, newest_added: 3 };
    const seg = document.getElementById('ls-seg-' + which);
    if (!seg) return;
    seg.querySelectorAll('.ls-seg-opt').forEach((o, i) =>
      o.classList.toggle('ls-active', i === (map[val] ?? 0))
    );
  }

  const LS_HOLD_INCREMENTS = {
    movies: 1, episodes: 1, cooldown: 24,
    batch: 1, sleep: 1, jitter: 1,
    'r-missing': 1, 'r-days': 1, 's-missing': 1,
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
      _lsHoldInterval = setInterval(() => {
        mHaptic(10);
        lsStep(key, dir, inc);
      }, 400);
    }, 500);
  }

  function lsHoldEnd(key, dir) {
    clearTimeout(_lsHoldTimer);
    clearInterval(_lsHoldInterval);
    _lsHoldTimer = null;
    _lsHoldInterval = null;
    if (!_lsHoldFired && key !== undefined) {
      mHaptic(20);
      lsStep(key, dir, 1);
    }
    _lsHoldFired = false;
  }

  function lsStep(key, dir, amt) {
    mHaptic(20);
    LS_VALS[key] = Math.max(LS_MINS[key], LS_VALS[key] + dir * (amt || 1));
    const el = document.getElementById('ls-v-' + key);
    if (el) { el.textContent = LS_VALS[key]; el.classList.toggle('ls-zero', LS_VALS[key] === 0); }
    lsTriggerSave();
  }

  function lsSeg(which, val, el) {
    const seg = document.getElementById('ls-seg-' + which);
    if (seg) seg.querySelectorAll('.ls-seg-opt').forEach(o => o.classList.remove('ls-active'));
    el.classList.add('ls-active');
    if (which === 'radarr') CFG.radarr_sample_mode = val;
    if (which === 'sonarr') CFG.sonarr_sample_mode = val;
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
        updates.radarr_sample_mode = CFG.radarr_sample_mode;
        updates.sonarr_sample_mode = CFG.sonarr_sample_mode;
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

  const LS_NAV_ITEMS = ['ls-nav-settings', 'ls-nav-advanced', 'ls-nav-overrides'];
  const LS_TAB_IDS   = ['ls-tab-settings', 'ls-tab-advanced', 'ls-tab-overrides'];

  function lsSwitchTab(idx) {
    // Guard: if leaving overrides tab with pending changes, confirm first
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
      t.classList.remove('ls-tab-active', 'ls-tab-prev');
      if (i === idx) t.classList.add('ls-tab-active');
      else if (i < idx) t.classList.add('ls-tab-prev');
    });
    LS_NAV_ITEMS.forEach((id, i) => {
      const n = document.getElementById(id);
      if (n) n.classList.toggle('ls-active', i === idx);
    });
    if (idx === 2) lsOvRenderRail();
  }

  function lsSwitchToDesktop() {
    LS_DESKTOP_OVERRIDE = true;
    sessionStorage.setItem('nudgarr_desktop_override', '1');
    checkOrientation();
  }

  (function() {
    const vp = document.getElementById('ls-viewport');
    if (!vp) return;
    let sx = null, sy = null;
    vp.addEventListener('touchstart', e => {
      sx = e.touches[0].clientX;
      sy = e.touches[0].clientY;
    }, { passive: true });
    vp.addEventListener('touchend', e => {
      if (sx === null) return;
      const dx = e.changedTouches[0].clientX - sx;
      const dy = e.changedTouches[0].clientY - sy;
      if (Math.abs(dx) >= 30 && Math.abs(dx) >= Math.abs(dy) * 1.5) {
        if (dx < 0 && LS_TAB < LS_TAB_IDS.length - 1) lsSwitchTab(LS_TAB + 1);
        if (dx > 0 && LS_TAB > 0) lsSwitchTab(LS_TAB - 1);
      }
      sx = null;
    }, { passive: true });
  })();

  // ── End Landscape UI ──────────────────────────────────────────────────────

  setInterval(mPollCycle, 5000);
}

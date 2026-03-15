  function mHaptic(ms) {
    if (navigator.vibrate) navigator.vibrate(ms || 40);
  }

  // ── Sheet helpers ──

  function mSheetOpen(id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.classList.add('m-visible');
  }

  function mSheetClose(id, cb) {
    const el = document.getElementById(id);
    if (!el) return;
    const sheet = el.querySelector('.m-sheet');
    if (sheet) { sheet.style.transition = 'transform .3s ease-in'; sheet.style.transform = 'translateY(100%)'; }
    el.style.transition = 'opacity .3s ease'; el.style.opacity = '0';
    setTimeout(() => {
      el.classList.remove('m-visible');
      if (sheet) { sheet.style.transition = ''; sheet.style.transform = ''; }
      el.style.transition = ''; el.style.opacity = '';
      if (cb) cb();
    }, 300);
  }

  function mSheetDrag(handleId, backdropId, closeFn) {
    const handle = document.getElementById(handleId);
    if (!handle) return;
    let startY = 0, curY = 0, dragging = false;
    const backdrop = document.getElementById(backdropId);
    const sheet = backdrop ? backdrop.querySelector('.m-sheet') : null;
    handle.addEventListener('touchstart', e => {
      startY = e.touches[0].clientY; curY = 0; dragging = true;
      if (sheet) sheet.style.transition = 'none';
    }, {passive: true});
    handle.addEventListener('touchmove', e => {
      if (!dragging) return;
      curY = Math.max(0, e.touches[0].clientY - startY);
      if (sheet) sheet.style.transform = 'translateY(' + curY + 'px)';
    }, {passive: true});
    handle.addEventListener('touchend', () => {
      if (!dragging) return; dragging = false;
      if (curY > 80) { closeFn(); }
      else { if (sheet) { sheet.style.transition = 'transform .2s ease-out'; sheet.style.transform = 'translateY(0)'; } }
    });
  }
  const M_QS_VALS = {cooldown: 48, movies: 1, episodes: 1};
  const M_QS_MINS = {cooldown: 0, movies: 0, episodes: 0};
  let M_QS_SAVE_TIMER = null;
  function mBtnPress(el) {
    el.classList.add('m-pressed');
    setTimeout(() => el.classList.remove('m-pressed'), 150);
  }
// ── Mobile Overrides — portrait sub-label helpers ──────────────────────────

function _mOvSwapSub(aId, bId, showB, bText) {
  const a = document.getElementById(aId);
  const b = document.getElementById(bId);
  if (!a || !b) return;
  if (showB) {
    if (bText !== undefined) b.textContent = bText;
    a.classList.add('m-sub-exiting');
    setTimeout(() => {
      a.classList.remove('m-sub-exiting');
      a.style.display = 'none';
      b.classList.add('m-sub-entering');
    }, 200);
  } else {
    b.classList.remove('m-sub-entering');
    b.style.display = '';
    a.style.display = '';
    a.classList.remove('m-sub-exiting');
    // Force reflow then animate in
    requestAnimationFrame(() => { a.style.opacity = ''; a.style.transform = ''; });
  }
}

function _mOvCountFieldOverrides(field) {
  if (!CFG) return 0;
  let n = 0;
  ['radarr', 'sonarr'].forEach(k => {
    (CFG.instances?.[k] || []).forEach(inst => {
      if (inst.overrides && field in inst.overrides) n++;
    });
  });
  return n;
}

function _mOvCountBacklogOverrides(kind) {
  if (!CFG) return 0;
  return (CFG.instances?.[kind] || []).filter(inst => inst.overrides && 'backlog_enabled' in inst.overrides).length;
}

function _mOvPlural(n, word) {
  return n === 1 ? `1 Override` : `${n} Overrides`;
}

function mOvUpdateSubLabels() {
  const enabled = CFG && CFG.per_instance_overrides_enabled;

  // Backlog toggles on portrait home
  const rCount = _mOvCountBacklogOverrides('radarr');
  const sCount = _mOvCountBacklogOverrides('sonarr');
  _mOvSwapSub('m-radarr-backlog-sub-a', 'm-radarr-backlog-sub-b', enabled && rCount > 0,
    `Global — ${_mOvPlural(rCount)}`);
  _mOvSwapSub('m-sonarr-backlog-sub-a', 'm-sonarr-backlog-sub-b', enabled && sCount > 0,
    `Global — ${_mOvPlural(sCount)}`);

  // QS stepper sub-labels
  const coolCount = _mOvCountFieldOverrides('cooldown_hours');
  const movCount  = _mOvCountFieldOverrides('max_cutoff_unmet');
  const epCount   = _mOvCountFieldOverrides('max_backlog');
  _mOvSwapSub('m-qs-cooldown-sub-a', 'm-qs-cooldown-sub-b', enabled && coolCount > 0,
    `Global — ${_mOvPlural(coolCount)}`);
  _mOvSwapSub('m-qs-movies-sub-a', 'm-qs-movies-sub-b', enabled && movCount > 0,
    `Global — ${_mOvPlural(movCount)}`);
  _mOvSwapSub('m-qs-episodes-sub-a', 'm-qs-episodes-sub-b', enabled && epCount > 0,
    `Global — ${_mOvPlural(epCount)}`);

  // QS callout
  const callA = document.getElementById('m-callout-default');
  const callB = document.getElementById('m-callout-active');
  if (callA && callB) {
    if (enabled) {
      callA.classList.add('m-sub-exiting');
      setTimeout(() => {
        callA.classList.remove('m-sub-exiting');
        callA.style.display = 'none';
        callB.classList.add('m-sub-entering');
      }, 200);
    } else {
      callB.classList.remove('m-sub-entering');
      callA.style.display = '';
      callB.style.display = '';
    }
  }

  // QS toggle state
  const togEl = document.getElementById('m-ov-toggle');
  const subEl = document.getElementById('m-ov-toggle-sub');
  if (togEl) togEl.classList.toggle('m-on', !!enabled);
  if (subEl) {
    subEl.textContent = enabled ? 'Enabled' : 'Disabled';
    subEl.style.color = enabled ? 'var(--ok)' : 'var(--muted)';
  }

  // Landscape nav visibility
  const lsNav = document.getElementById('ls-nav-overrides');
  if (lsNav) lsNav.style.display = enabled ? 'flex' : 'none';
}

async function mToggleMobileOverrides() {
  mHaptic(40);
  const newVal = !CFG.per_instance_overrides_enabled;
  try {
    await api('/api/overrides/toggle', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({enabled: newVal})
    });
    CFG.per_instance_overrides_enabled = newVal;
    mOvUpdateSubLabels();
    // Show first-time modal when enabling
    if (newVal && !CFG.per_instance_overrides_seen_mobile) {
      const modal = document.getElementById('m-ov-modal');
      if (modal) { modal.style.display = 'flex'; modal.classList.add('m-visible'); }
    }
    // If disabling and currently on overrides tab in landscape, go back to settings
    if (!newVal && lsIsOnOverridesTab()) lsSwitchTabSafe(0);
  } catch(e) {
    // Revert toggle on failure
    const togEl = document.getElementById('m-ov-toggle');
    if (togEl) togEl.classList.toggle('m-on', !newVal);
    showAlert('Failed to save overrides setting: ' + e.message);
  }
}

function mDismissOvModal() {
  const modal = document.getElementById('m-ov-modal');
  if (modal) { modal.classList.remove('m-visible'); setTimeout(() => { modal.style.display = 'none'; }, 300); }
  if (CFG && !CFG.per_instance_overrides_seen_mobile) {
    CFG.per_instance_overrides_seen_mobile = true;
    mSaveCfgKey({per_instance_overrides_seen_mobile: true});
  }
}
async function mPollCycle() {
  if (!MOBILE) return;
  try {
    const st = await api('/api/status');
    STATUS_CACHE = st.instance_health || {};
    if (CFG) mUpdateHome(CFG, st);
    if (M_TAB === 'sweep') {
      await refreshSweep(); // reuse desktop sweep data loader to populate SWEEP_DATA_CACHE
      mRenderSweep();
    }
    if (M_TAB === 'instances') mRenderInstances();
  } catch(e) {}
}

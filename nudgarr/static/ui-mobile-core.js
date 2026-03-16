// ── Mobile Core — shared helpers ────────────────────────────────────────────
// Loaded after ui-overrides.js, before ui-mobile-landscape.js and ui-mobile-portrait.js.

function mHaptic(ms) {
  if (navigator.vibrate) navigator.vibrate(ms || 40);
}

// ── Sheet helpers ──────────────────────────────────────────────────────────

function mSheetOpen(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.add('m-visible');
}

function mSheetClose(id, cb) {
  const el = document.getElementById(id);
  if (!el) return;
  const sheet = el.querySelector('.m-sheet');
  if (sheet) {
    sheet.style.transition = 'transform .3s ease-in';
    sheet.style.transform = 'translateY(100%)';
  }
  el.style.transition = 'opacity .3s ease';
  el.style.opacity = '0';
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

function mBtnPress(el) {
  el.classList.add('m-pressed');
  setTimeout(() => el.classList.remove('m-pressed'), 150);
}

// ── Overrides sub-label helpers ────────────────────────────────────────────

function _mOvCountFieldOverrides(field, kind) {
  if (!CFG) return 0;
  const apps = kind ? [kind] : ['radarr', 'sonarr'];
  let n = 0;
  apps.forEach(k => {
    (CFG.instances?.[k] || []).forEach(inst => {
      if (inst.overrides && field in inst.overrides) n++;
    });
  });
  return n;
}

function _mOvPlural(n) {
  return n === 1 ? '1 Override' : n + ' Overrides';
}

function _mOvSetStepperSub(key, showOverride, normalText, overrideText) {
  const valEl = document.getElementById('m-sv-' + key);
  if (!valEl) return;
  const row = valEl.closest('.m-stepper-row');
  if (!row) return;
  const sub = row.querySelector('.m-stepper-sub');
  if (!sub) return;
  if (showOverride) {
    sub.textContent = overrideText;
    sub.style.color = 'var(--warn)';
    sub.style.fontWeight = '500';
  } else {
    sub.textContent = normalText;
    sub.style.color = '';
    sub.style.fontWeight = '';
  }
}

function mOvUpdateSubLabels() {
  const enabled = CFG && CFG.per_instance_overrides_enabled;

  const coolCount = _mOvCountFieldOverrides('cooldown_hours');
  const rCutCount = _mOvCountFieldOverrides('max_cutoff_unmet', 'radarr');
  const sCutCount = _mOvCountFieldOverrides('max_cutoff_unmet', 'sonarr');

  _mOvSetStepperSub('cooldown', enabled && coolCount > 0,
    'Hours between searches \u00b7 hold +24', 'Global \u2014 ' + _mOvPlural(coolCount));
  _mOvSetStepperSub('r-cutoff', enabled && rCutCount > 0,
    'Cutoff searches per run \u00b7 0 disables', 'Global \u2014 ' + _mOvPlural(rCutCount));
  _mOvSetStepperSub('s-cutoff', enabled && sCutCount > 0,
    'Cutoff searches per run \u00b7 0 disables', 'Global \u2014 ' + _mOvPlural(sCutCount));

  const togEl = document.getElementById('m-ov-toggle');
  const subEl = document.getElementById('m-ov-toggle-sub');
  if (togEl) togEl.classList.toggle('m-on', !!enabled);
  if (subEl) {
    subEl.textContent = enabled ? 'Enabled' : 'Disabled';
    subEl.style.color = enabled ? 'var(--ok)' : 'var(--muted)';
  }

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
    if (newVal && !CFG.per_instance_overrides_seen_mobile) {
      const modal = document.getElementById('m-ov-modal');
      if (modal) { modal.style.display = 'flex'; modal.classList.add('m-visible'); }
    }
    if (!newVal && lsIsOnOverridesTab()) lsSwitchTabSafe(0);
  } catch(e) {
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
    if (typeof mSaveCfgKeys === 'function') mSaveCfgKeys({per_instance_overrides_seen_mobile: true});
  }
}

// ── Poll cycle ─────────────────────────────────────────────────────────────

async function mPollCycle() {
  if (!MOBILE) return;
  try {
    const st = await api('/api/status');
    STATUS_CACHE = st.instance_health || {};
    if (CFG) mUpdateHome(CFG, st);
    if (M_TAB === 'sweep') {
      await refreshSweep();
      mRenderSweep();
    }
  } catch(e) {}
}

// ── Landscape bridge functions ─────────────────────────────────────────────

function lsSwitchTabSafe(idx) {
  if (typeof lsSwitchTab === 'function') lsSwitchTab(idx);
}

function lsIsOnOverridesTab() {
  return typeof LS_TAB !== 'undefined' && LS_TAB === 2;
}

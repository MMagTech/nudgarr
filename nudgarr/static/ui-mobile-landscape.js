// ── Landscape Overrides ────────────────────────────────────────────────────
// Handles the Overrides rail/panel in landscape mode.
// All other landscape logic lives inside if(MOBILE) in ui-mobile-portrait.js.

const LS_OV_PENDING = {};
let LS_OV_SEL = null;
let _lsOvApplyTimer = null;

function _lsOvKey(kind, idx) { return kind + '|' + idx; }

function lsOvHasPending() {
  return Object.keys(LS_OV_PENDING).length > 0;
}

function lsOvDiscardAll() {
  Object.keys(LS_OV_PENDING).forEach(k => delete LS_OV_PENDING[k]);
}

// lsOvRenderRail — rebuilds the rail (left column) listing all instances.
// Highlights the selected instance, shows a pending dot when changes are
// unsaved, and displays the override count pill. Auto-selects the first
// instance if nothing is selected. Calls lsOvRenderPanel() at the end.
function lsOvRenderRail() {
  const rail = document.getElementById('ls-ov-rail');
  if (!rail || !CFG) return;
  let html = '';
  ['radarr', 'sonarr'].forEach(kind => {
    (CFG.instances?.[kind] || []).forEach((inst, idx) => {
      const key = _lsOvKey(kind, idx);
      const ovCount = Object.keys(inst.overrides || {}).length;
      const isPending = !!LS_OV_PENDING[key];
      const isActive = LS_OV_SEL && LS_OV_SEL.kind === kind && LS_OV_SEL.idx === idx;
      const isDisabled = inst.enabled === false;
      const dotColor = isDisabled ? 'var(--muted)' : (kind === 'sonarr' ? 'var(--ok)' : 'var(--accent)');
      const dotGlow = (!isDisabled && isActive) ? (kind === 'sonarr' ? ';box-shadow:0 0 5px rgba(34,197,94,.5)' : ';box-shadow:0 0 5px rgba(91,114,245,.6)') : '';
      const accentColor  = kind === 'sonarr' ? 'var(--ok)'           : 'var(--accent-lt)';
      const accentBg     = kind === 'sonarr' ? 'rgba(34,197,94,.1)'  : 'var(--accent-dim)';
      const accentBorder = kind === 'sonarr' ? 'rgba(34,197,94,.28)' : 'var(--accent-border)';
      html += '<div class="ls-ov-rail-item' + (isActive ? ' ls-ov-active' : '') + (isDisabled ? ' ls-ov-disabled' : '') + '"'
        + ' onclick="' + (isDisabled ? '' : 'lsOvSelectInstance(\'' + kind + '\',' + idx + ')') + '">'
        + '<div class="ls-ov-rail-row1">'
        + '<div style="display:flex;align-items:center;gap:6px;min-width:0;flex:1">'
        + '<div style="width:7px;height:7px;border-radius:50%;background:' + dotColor + dotGlow + ';flex-shrink:0"></div>'
        + '<span class="ls-ov-rail-name">' + escapeHtml(inst.name) + '</span>'
        + '</div>'
        + (isPending ? '<span class="ls-ov-pending-dot"></span>' : '')
        + '</div>'
        + (ovCount > 0 ? '<div style="margin-top:4px;margin-left:13px"><span style="display:inline-flex;align-items:center;padding:1px 8px;border-radius:999px;font-size:10px;background:' + accentBg + ';border:1px solid ' + accentBorder + ';color:' + accentColor + '">' + ovCount + ' Override' + (ovCount !== 1 ? 's' : '') + '</span></div>' : '')
        + '</div>';
    });
  });
  rail.innerHTML = html || '<p style="font-size:11px;color:var(--muted);padding:12px 10px">No instances configured.</p>';
  if (!LS_OV_SEL) {
    const first = (CFG.instances?.radarr?.[0]) ? {kind:'radarr', idx:0}
      : (CFG.instances?.sonarr?.[0]) ? {kind:'sonarr', idx:0} : null;
    if (first) { LS_OV_SEL = first; lsOvRenderRail(); return; }
  }
  lsOvRenderPanel();
}

// lsOvSelectInstance — saves any pending DOM state for the current selection
// then switches selection to the new instance and re-renders rail + panel.
function lsOvSelectInstance(kind, idx) {
  if (LS_OV_SEL) _lsOvSavePendingFromDOM();
  LS_OV_SEL = {kind, idx};
  lsOvRenderRail();
}

function _lsOvSavePendingFromDOM() {
  if (!LS_OV_SEL) return;
  const {kind, idx} = LS_OV_SEL;
  const key = _lsOvKey(kind, idx);
  const pending = {};
  const numFields = ['cooldown_hours','max_cutoff_unmet','max_backlog'];
  if (kind === 'radarr') numFields.push('max_missing_days');
  numFields.forEach(f => {
    const el = document.getElementById('ls-ov-f-' + f);
    if (el) pending[f] = el.value;
  });
  const modeEl = document.getElementById('ls-ov-f-sample_mode');
  if (modeEl) pending.sample_mode = modeEl.value;
  const blEl = document.getElementById('ls-ov-f-backlog_enabled');
  if (blEl) pending.backlog_enabled = blEl.checked;
  const notEl = document.getElementById('ls-ov-f-notifications_enabled');
  if (notEl) pending.notifications_enabled = notEl.checked;
  if (document.getElementById('ls-ov-body')?.dataset.dirty === '1') {
    LS_OV_PENDING[key] = pending;
  }
}

// lsOvRenderPanel — builds the right-column panel for the selected instance.
// Renders all override fields (cooldown, mode, cutoff, backlog, missing days,
// notifications) showing current override value or global fallback. Wires
// hold-to-accelerate touch/mouse events on stepper buttons.
function lsOvRenderPanel() {
  if (!LS_OV_SEL || !CFG) return;
  const {kind, idx} = LS_OV_SEL;
  const inst = (CFG.instances?.[kind] || [])[idx];
  if (!inst) return;
  const ov = inst.overrides || {};
  const key = _lsOvKey(kind, idx);
  const pending = LS_OV_PENDING[key];
  const VALID_MODES = ['random','alphabetical','oldest_added','newest_added'];
  const MODE_LABELS = {random:'Random',alphabetical:'Alphabetical',oldest_added:'Oldest Added',newest_added:'Newest Added'};

  function gv(field) { return _getGlobal(kind, field); }
  function fVal(field) {
    if (pending && field in pending) return pending[field];
    return field in ov ? ov[field] : '';
  }
  function fActive(field) { return field in ov || (pending && field in pending); }

  const numField = (field, label) => {
    const val = fVal(field);
    const gVal = gv(field);
    const active = fActive(field);
    const dispVal = val !== '' && val !== null ? val : gVal;
    return '<div class="ls-ov-field">'
      + '<label>' + label + '</label>'
      + '<div class="ls-ov-stepper' + (active ? ' ls-ov-active' : '') + '" id="ls-ov-s-' + field + '">'
      + '<button class="ls-ov-stepper-btn" data-ov-field="' + field + '" data-ov-dir="-1">\u2212</button>'
      + '<div class="ls-ov-stepper-val' + (dispVal === 0 ? ' ls-ov-zero' : '') + '" id="ls-ov-sv-' + field + '">' + dispVal + '</div>'
      + '<button class="ls-ov-stepper-btn" data-ov-field="' + field + '" data-ov-dir="1">+</button>'
      + '</div>'
      + '<input type="hidden" id="ls-ov-f-' + field + '" value="' + (val !== '' && val !== null ? val : '') + '"/>'
      + '<span class="ls-ov-global">Global: ' + gVal + '</span>'
      + '</div>';
  };

  const gMode = gv('sample_mode');
  const modeVal = pending && 'sample_mode' in pending ? pending.sample_mode
    : ('sample_mode' in ov ? ov.sample_mode : '__global__');
  const modeActive = modeVal !== '__global__' ? ' ls-ov-active' : '';
  const modeField = '<div class="ls-ov-field">'
    + '<label>Sample Mode</label>'
    + '<select id="ls-ov-f-sample_mode" class="' + modeActive + '" onchange="lsOvMarkDirty()">'
    + '<option value="__global__"' + (modeVal === '__global__' ? ' selected' : '') + '>Use Global</option>'
    + VALID_MODES.map(m => '<option value="' + m + '"' + (modeVal === m ? ' selected' : '') + '>' + MODE_LABELS[m] + '</option>').join('')
    + '</select>'
    + '<span class="ls-ov-global">Global: ' + (MODE_LABELS[gMode] || gMode) + '</span>'
    + '</div>';

  const gBl = gv('backlog_enabled');
  const blVal = pending && 'backlog_enabled' in pending ? pending.backlog_enabled
    : ('backlog_enabled' in ov ? ov.backlog_enabled : gBl);
  const blActive = 'backlog_enabled' in ov || (pending && 'backlog_enabled' in pending) ? ' ls-ov-active' : '';
  const blField = '<div class="ls-ov-field">'
    + '<label style="visibility:hidden">Backlog</label>'
    + '<div class="ls-ov-bl-row' + blActive + '" id="ls-ov-bl-row">'
    + '<div><div class="ls-ov-bl-label">Backlog</div>'
    + '<div class="ls-ov-bl-sub" id="ls-ov-bl-sub">Global: ' + (gBl ? 'On' : 'Off') + '</div></div>'
    + '<label class="ls-ov-toggle">'
    + '<input type="checkbox" id="ls-ov-f-backlog_enabled"' + (blVal ? ' checked' : '') + ' onchange="lsOvMarkDirty(); updateBacklogLabel()"/>'
    + '<span class="ls-ov-toggle-track"></span><span class="ls-ov-toggle-thumb"></span>'
    + '</label></div></div>';

  const row3 = kind === 'radarr'
    ? numField('max_backlog','Max Backlog') + numField('max_missing_days','Max Missing Days')
    : numField('max_backlog','Max Backlog') + '<div></div>';

  const gNot = gv('notifications_enabled');
  const notVal = pending && 'notifications_enabled' in pending ? pending.notifications_enabled
    : ('notifications_enabled' in ov ? ov.notifications_enabled : gNot);
  const notActive = 'notifications_enabled' in ov || (pending && 'notifications_enabled' in pending) ? ' ls-ov-active' : '';

  const isInstDisabled = inst.enabled === false;

  const body = document.getElementById('ls-ov-body');
  if (body) {
    body.dataset.dirty = pending ? '1' : '0';
    body.classList.toggle('ls-ov-panel-disabled', isInstDisabled);
    body.innerHTML = numField('cooldown_hours','Cooldown Hours')
      + modeField
      + numField('max_cutoff_unmet','Max Cutoff Unmet')
      + blField
      + row3
      + '<div class="ls-ov-notify-row' + notActive + '" id="ls-ov-notify-row" style="grid-column:1/-1">'
      + '<div style="display:flex;align-items:baseline;gap:6px">'
      + '<span class="ls-ov-notify-label">Notifications</span>'
      + '<span class="ls-ov-notify-sub" id="ls-ov-notify-sub">Global: ' + (gNot ? 'On' : 'Off') + '</span>'
      + '</div>'
      + '<label class="ls-ov-toggle">'
      + '<input type="checkbox" id="ls-ov-f-notifications_enabled"' + (notVal ? ' checked' : '') + ' onchange="lsOvMarkDirty(); updateNotifyLabel()"/>'
      + '<span class="ls-ov-toggle-track"></span><span class="ls-ov-toggle-thumb"></span>'
      + '</label></div>'
      + (isInstDisabled ? '<div class="ls-ov-disabled-notice">Instance is disabled. Enable it to configure overrides.</div>' : '');

    body.querySelectorAll('.ls-ov-stepper-btn[data-ov-field]').forEach(btn => {
      const field = btn.dataset.ovField;
      const dir = parseInt(btn.dataset.ovDir, 10);
      btn.addEventListener('mousedown', () => lsOvHoldStart(field, dir));
      btn.addEventListener('mouseup', () => lsOvHoldEnd(field, dir));
      btn.addEventListener('mouseleave', () => lsOvHoldEnd(field, dir));
      btn.addEventListener('touchstart', e => { e.preventDefault(); lsOvHoldStart(field, dir); }, {passive: false});
      btn.addEventListener('touchend', () => lsOvHoldEnd(field, dir));
      btn.addEventListener('touchcancel', () => lsOvHoldEnd(field, dir));
    });

    const foot = document.getElementById('ls-ov-foot');
    if (foot) {
      foot.style.opacity = isInstDisabled ? '.38' : '';
      foot.style.pointerEvents = isInstDisabled ? 'none' : '';
    }
  }
  lsOvUpdateFooter();
}

const LS_OV_HOLD_INCREMENTS = {
  cooldown_hours: 24, max_cutoff_unmet: 5,
  max_backlog: 5, max_missing_days: 7,
};
let _lsOvHoldTimer = null;
let _lsOvHoldInterval = null;
let _lsOvHoldFired = false;

function lsOvStep(field, dir, amt) {
  const hidden = document.getElementById('ls-ov-f-' + field);
  const valEl = document.getElementById('ls-ov-sv-' + field);
  const stepper = document.getElementById('ls-ov-s-' + field);
  if (!hidden || !valEl) return;
  const {kind} = LS_OV_SEL || {};
  const gVal = kind ? (_getGlobal(kind, field) ?? 0) : 0;
  const current = hidden.value !== '' ? parseInt(hidden.value, 10) : gVal;
  const next = Math.max(0, current + dir * (amt || 1));
  hidden.value = next;
  valEl.textContent = next;
  valEl.classList.toggle('ls-ov-zero', next === 0);
  if (stepper) stepper.classList.toggle('ls-ov-active', next !== gVal);
  lsOvMarkDirty();
}

function lsOvHoldStart(field, dir) {
  _lsOvHoldFired = false;
  _lsOvHoldTimer = setTimeout(() => {
    _lsOvHoldFired = true;
    const inc = LS_OV_HOLD_INCREMENTS[field] || 1;
    lsOvStep(field, dir, inc);
    _lsOvHoldInterval = setInterval(() => { lsOvStep(field, dir, inc); }, 400);
  }, 500);
}

function lsOvHoldEnd(field, dir) {
  clearTimeout(_lsOvHoldTimer);
  clearInterval(_lsOvHoldInterval);
  _lsOvHoldTimer = null; _lsOvHoldInterval = null;
  if (!_lsOvHoldFired && field !== undefined) lsOvStep(field, dir, 1);
  _lsOvHoldFired = false;
}

// lsOvMarkDirty — marks the current panel as having unsaved changes.
// Updates the footer status and adds a pending dot to the rail item.
function lsOvMarkDirty() {
  const body = document.getElementById('ls-ov-body');
  if (body) body.dataset.dirty = '1';
  lsOvUpdateFooter();
  if (LS_OV_SEL) {
    _lsOvSavePendingFromDOM();
    const {kind, idx} = LS_OV_SEL;
    const key = _lsOvKey(kind, idx);
    const railItem = document.querySelector('[onclick="lsOvSelectInstance(\'' + kind + '\',' + idx + ')"]');
    if (railItem && !railItem.querySelector('.ls-ov-pending-dot')) {
      const row1 = railItem.querySelector('.ls-ov-rail-row1');
      if (row1) { const dot = document.createElement('span'); dot.className = 'ls-ov-pending-dot'; row1.appendChild(dot); }
    }
  }
}

function lsOvUpdateFooter() {
  if (!LS_OV_SEL || !CFG) return;
  const {kind, idx} = LS_OV_SEL;
  const inst = (CFG.instances?.[kind] || [])[idx];
  const body = document.getElementById('ls-ov-body');
  const isDirty = body && body.dataset.dirty === '1';
  const ovCount = inst ? Object.keys(inst.overrides || {}).length : 0;
  const statusEl = document.getElementById('ls-ov-status');
  if (!statusEl) return;
  statusEl.className = 'ls-ov-foot-mid';
  if (isDirty) {
    statusEl.classList.add('ls-ov-foot-pending');
    statusEl.innerHTML = '<span class="ls-ov-pending-dot-sm"></span>Pending';
  } else if (ovCount > 0) {
    statusEl.classList.add('ls-ov-foot-count');
    statusEl.textContent = ovCount + ' Override' + (ovCount !== 1 ? 's' : '');
  } else {
    statusEl.classList.add('ls-ov-foot-inherited');
    statusEl.textContent = 'No Overrides Set';
  }
}

function updateBacklogLabel() {
  if (!LS_OV_SEL) return;
  const {kind} = LS_OV_SEL;
  const lblEl = document.getElementById('ls-ov-bl-sub');
  const rowEl = document.getElementById('ls-ov-bl-row');
  if (!lblEl) return;
  lblEl.textContent = 'Global: ' + (_getGlobal(kind, 'backlog_enabled') ? 'On' : 'Off');
  if (rowEl) rowEl.classList.add('ls-ov-active');
}

function updateNotifyLabel() {
  if (!LS_OV_SEL) return;
  const {kind} = LS_OV_SEL;
  const lblEl = document.getElementById('ls-ov-notify-sub');
  const rowEl = document.getElementById('ls-ov-notify-row');
  if (!lblEl) return;
  lblEl.textContent = 'Global: ' + (_getGlobal(kind, 'notifications_enabled') ? 'On' : 'Off');
  if (rowEl) rowEl.classList.add('ls-ov-active');
}

// lsOvApply — reads all field values from the DOM, posts to
// /api/instance/overrides, and updates CFG in place. Clears pending state
// and re-renders the rail on success. Debounced 500ms to avoid double-tap.
async function lsOvApply() {
  if (!LS_OV_SEL || !CFG) return;
  clearTimeout(_lsOvApplyTimer);
  const applyBtn = document.getElementById('ls-ov-apply');
  if (applyBtn) { applyBtn.disabled = true; applyBtn.style.opacity = '.5'; }
  const {kind, idx} = LS_OV_SEL;
  const inst = (CFG.instances?.[kind] || [])[idx];
  if (!inst) { if (applyBtn) { applyBtn.disabled = false; applyBtn.style.opacity = ''; } return; }
  const existing = inst.overrides || {};
  const newOv = Object.assign({}, existing);
  const numFields = ['cooldown_hours','max_cutoff_unmet','max_backlog'];
  _lsOvApplyTimer = setTimeout(async () => {
    if (kind === 'radarr') numFields.push('max_missing_days');
    numFields.forEach(field => {
      const input = document.getElementById('ls-ov-f-' + field);
      if (!input) return;
      const raw = input.value.trim();
      if (raw !== '') { newOv[field] = parseInt(raw, 10); }
      else if (field in newOv) { delete newOv[field]; }
    });
    const modeEl = document.getElementById('ls-ov-f-sample_mode');
    if (modeEl) {
      if (modeEl.value === '__global__' || modeEl.value === '') { delete newOv.sample_mode; }
      else { newOv.sample_mode = modeEl.value; }
    }
    const blEl = document.getElementById('ls-ov-f-backlog_enabled');
    if (blEl) {
      const gBl = _getGlobal(kind, 'backlog_enabled');
      if (blEl.checked !== gBl || 'backlog_enabled' in existing) newOv.backlog_enabled = blEl.checked;
    }
    const notEl = document.getElementById('ls-ov-f-notifications_enabled');
    if (notEl) {
      const gNot = _getGlobal(kind, 'notifications_enabled');
      if (notEl.checked !== gNot || 'notifications_enabled' in existing) newOv.notifications_enabled = notEl.checked;
    }
    try {
      await api('/api/instance/overrides', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({kind, idx, overrides: newOv})
      });
      inst.overrides = newOv;
      delete LS_OV_PENDING[_lsOvKey(kind, idx)];
      const body = document.getElementById('ls-ov-body');
      if (body) body.dataset.dirty = '0';
      lsOvRenderRail();
      mOvUpdateSubLabels();
      lsTriggerSave();
    } catch(e) {
      showAlert('Failed to save overrides: ' + e.message);
    } finally {
      if (applyBtn) { applyBtn.disabled = false; applyBtn.style.opacity = ''; }
    }
  }, 500);
}

// lsOvReset — shows a confirm dialog then posts an empty overrides object
// for the selected instance, returning it to global settings.
async function lsOvReset() {
  if (!LS_OV_SEL || !CFG) return;
  const {kind, idx} = LS_OV_SEL;
  const confirmed = await showConfirm('Reset All to Global',
    'Remove all overrides for this instance? It will inherit global settings.', 'Reset', true);
  if (!confirmed) return;
  try {
    await api('/api/instance/overrides', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({kind, idx, overrides: {}})
    });
    const inst = (CFG.instances?.[kind] || [])[idx];
    if (inst) inst.overrides = {};
    delete LS_OV_PENDING[_lsOvKey(kind, idx)];
    const body = document.getElementById('ls-ov-body');
    if (body) body.dataset.dirty = '0';
    lsOvRenderRail();
    mOvUpdateSubLabels();
  } catch(e) {
    showAlert('Failed to reset overrides: ' + e.message);
  }
}

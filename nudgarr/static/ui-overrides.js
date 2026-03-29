// ── Per-Instance Overrides ─────────────────────────────────────────────────────
// Owns: Overrides tab rendering (renderOverridesCards, renderSingleOverrideCard),
// override feature toggle (toggleOverridesFeature, syncOverridesToggleLabel),
// per-card apply/reset (applyOverrides, resetCardOverrides, resetFieldOverride),
// dirty tracking (markCardDirty), label sync (updateBacklogLabel,
// updateNotifyLabel), the one-time info modal (dismissOverridesModal), and
// the shared _getGlobal() helper used by override card rendering.
//
// Each override card is built by _buildOverrideCard() and rendered into
// #overrides-grid by renderOverridesCards(). Cards track dirty state via
// .ov-dirty class — showTab() guards navigation away from the tab when
// any card has unsaved changes.


function syncOverridesToggleLabel() {
  const enabled = el('per_instance_overrides_enabled') && el('per_instance_overrides_enabled').checked;
  const lbl = el('overrides_enabled_label');
  if (lbl) lbl.textContent = enabled ? 'Enabled' : 'Disabled';
}

async function toggleOverridesFeature(enabled) {
  syncOverridesToggleLabel();
  try {
    await api('/api/overrides/toggle', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({enabled})
    });
    CFG.per_instance_overrides_enabled = enabled;
    const tab = el('tab-btn-overrides');
    if (enabled) {
      tab.classList.add('ov-tab-visible');
      // Show one-time modal on first enable
      if (!CFG.per_instance_overrides_seen) {
        CFG.per_instance_overrides_seen = true;
        el('overridesInfoModal').style.display = 'flex';
      }
    } else {
      tab.classList.remove('ov-tab-visible');
      // If currently on overrides tab, navigate away
      if (ACTIVE_TAB === 'overrides') _doShowTab('advanced');
    }
  } catch(e) {
    showAlert('Failed to save overrides setting: ' + e.message);
    // Revert toggle visually
    if (el('per_instance_overrides_enabled')) {
      el('per_instance_overrides_enabled').checked = !enabled;
      syncOverridesToggleLabel();
    }
  }
}

function dismissOverridesModal() {
  el('overridesInfoModal').style.display = 'none';
}

function _getGlobal(kind, field) {
  if (!CFG) return '';
  const map = {
    cooldown_hours:        CFG.cooldown_hours ?? 48,
    max_cutoff_unmet:      kind === 'radarr' ? (CFG.radarr_max_movies_per_run ?? 1) : (CFG.sonarr_max_episodes_per_run ?? 1),
    sample_mode:           kind === 'radarr' ? (CFG.radarr_sample_mode || 'random') : (CFG.sonarr_sample_mode || 'random'),
    max_backlog:           kind === 'radarr' ? (CFG.radarr_missing_max ?? 1) : (CFG.sonarr_missing_max ?? 1),
    max_missing_days:      CFG.radarr_missing_added_days ?? 14,
    backlog_enabled:       kind === 'radarr' ? !!CFG.radarr_backlog_enabled : !!CFG.sonarr_backlog_enabled,
    notifications_enabled: !!CFG.notify_enabled,
    // Backlog sample mode — independent of cutoff sample mode (v4.2.0)
    backlog_sample_mode:   kind === 'radarr' ? (CFG.radarr_backlog_sample_mode || 'random') : (CFG.sonarr_backlog_sample_mode || 'random'),
    // Grace period — applied after availability date before first missing search (v4.2.0)
    missing_grace_hours:   kind === 'radarr' ? (CFG.radarr_missing_grace_hours ?? 0) : (CFG.sonarr_missing_grace_hours ?? 0),
  };
  return field in map ? map[field] : '';
}

function _ovCardId(kind, idx) { return `ov-card-${kind}-${idx}`; }

// _buildOverrideCard — renders the HTML for a single per-instance override card.
// Layout (v4.2.0):
//   Cooldown — spans full width, applies to both pipelines
//   [Cutoff Unmet group] Max Cutoff Unmet / Sample Mode
//   [Backlog group] toggle row, Max Backlog / Backlog Sample Mode,
//                  Max Missing Days / empty (Radarr only)
//   Notifications footer row
// Fields with an active override get the ov-active class to highlight them visually.
// Disabled instances are fully dimmed and pointer-events are removed.
// Returns a raw HTML string for innerHTML injection by renderOverridesCards().
function _buildOverrideCard(kind, idx, inst, solo = false) {
  const ov = inst.overrides || {};
  const cardId = _ovCardId(kind, idx);
  const ovCount = Object.keys(ov).length;
  const isDisabled = inst.enabled === false;
  const badgeClass = kind === 'sonarr' ? 'ov-badge ov-sonarr' : 'ov-badge';
  const dotClass = kind === 'sonarr' ? 'ov-dot ov-sonarr' : 'ov-dot';
  const badgeStyle = isDisabled ? 'opacity:0.4;filter:saturate(0)' : '';
  const dotStyle = isDisabled ? 'opacity:0.4' : '';
  const VALID_MODES = ['random', 'alphabetical', 'oldest_added', 'newest_added'];
  const MODE_LABELS = {random: 'Random', alphabetical: 'Alphabetical', oldest_added: 'Oldest Added', newest_added: 'Newest Added'};

  const statusHtml = ovCount
    ? `<span class="help" style="font-size:11px">${ovCount} Override${ovCount !== 1 ? 's' : ''}</span>`
    : `<span class="help" style="font-size:11px;color:var(--muted)">Global Inherited</span>`;

  const disabledStyle = isDisabled ? 'opacity:0.45;pointer-events:none' : '';
  const disabledBorder = isDisabled ? 'border-color:rgba(255,255,255,.06)' : '';

  const numField = (field, label, globalVal) => {
    const hasOv = field in ov;
    const val = hasOv ? ov[field] : '';
    const activeClass = hasOv ? 'ov-active' : '';
    return `<div class="field">
      <label>${label}</label>
      <div class="ov-iw">
        <input type="number" min="0" id="${cardId}-${field}" value="${val}"
          placeholder="${globalVal}" class="${activeClass}"
          oninput="markCardDirty('${kind}',${idx})"/>
        <button class="ov-rx" title="Reset to global (${globalVal})"
          onclick="resetFieldOverride('${kind}',${idx},'${field}')">×</button>
      </div>
      <span class="help">Global: ${globalVal}</span>
    </div>`;
  };

  // Cutoff sample mode — uses __global__ sentinel; follows existing pattern
  const globalMode = _getGlobal(kind, 'sample_mode');
  const hasOvMode = 'sample_mode' in ov;
  const modeVal = hasOvMode ? ov.sample_mode : '__global__';
  const modeField = `<div class="field">
    <label>Sample Mode</label>
    <select id="${cardId}-sample_mode" class="${hasOvMode ? 'ov-active' : ''}"
      onchange="markCardDirty('${kind}',${idx})">
      <option value="__global__"${!hasOvMode ? ' selected' : ''}>Use Global (${MODE_LABELS[globalMode] || globalMode})</option>
      ${VALID_MODES.map(m => `<option value="${m}"${modeVal === m ? ' selected' : ''}>${MODE_LABELS[m]}</option>`).join('')}
    </select>
  </div>`;

  // Backlog sample mode — independent of cutoff sample mode; same __global__ sentinel pattern (v4.2.0)
  const globalBacklogMode = _getGlobal(kind, 'backlog_sample_mode');
  const hasOvBacklogMode = 'backlog_sample_mode' in ov;
  const backlogModeVal = hasOvBacklogMode ? ov.backlog_sample_mode : '__global__';
  const backlogModeField = `<div class="field">
    <label>Backlog Sample Mode</label>
    <select id="${cardId}-backlog_sample_mode" class="${hasOvBacklogMode ? 'ov-active' : ''}"
      onchange="markCardDirty('${kind}',${idx})">
      <option value="__global__"${!hasOvBacklogMode ? ' selected' : ''}>Use Global (${MODE_LABELS[globalBacklogMode] || globalBacklogMode})</option>
      ${VALID_MODES.map(m => `<option value="${m}"${backlogModeVal === m ? ' selected' : ''}>${MODE_LABELS[m]}</option>`).join('')}
    </select>
  </div>`;

  // Backlog enabled toggle
  const globalBacklog = _getGlobal(kind, 'backlog_enabled');
  const hasOvBacklog = 'backlog_enabled' in ov;
  const backlogVal = hasOvBacklog ? ov.backlog_enabled : globalBacklog;
  const blRowClass = hasOvBacklog ? 'ov-bl-row ov-active' : 'ov-bl-row';
  const blLabel = hasOvBacklog
    ? `${backlogVal ? 'On (Override)' : 'Off (Override)'} Global: ${globalBacklog ? 'On' : 'Off'}`
    : `${backlogVal ? 'On' : 'Off'} (Global: ${globalBacklog ? 'On' : 'Off'})`;

  const gCooldown = _getGlobal(kind, 'cooldown_hours');
  const gCutoff   = _getGlobal(kind, 'max_cutoff_unmet');
  const gBacklog  = _getGlobal(kind, 'max_backlog');
  const gMissing  = _getGlobal(kind, 'max_missing_days');
  const gGrace    = _getGlobal(kind, 'missing_grace_hours');

  // Backlog fields: Max Backlog / Backlog Sample Mode (both apps)
  // Radarr row 2: Max Missing Days / Grace Period (Hours)
  // Sonarr row 2: Grace Period (Hours) / empty
  // Grey the entire fields block when backlog is effectively off (resolved value)
  const backlogFieldsStyle = backlogVal ? '' : 'opacity:0.38;pointer-events:none';
  const backlogFieldsHtml = kind === 'radarr'
    ? `<div class="ov-fields" id="${cardId}-backlog-fields" style="${backlogFieldsStyle}">
        ${numField('max_backlog', 'Max Backlog', gBacklog)}
        ${backlogModeField}
        ${numField('max_missing_days', 'Max Missing Days', gMissing)}
        ${numField('missing_grace_hours', 'Grace Period (Hours)', gGrace)}
      </div>`
    : `<div class="ov-fields" id="${cardId}-backlog-fields" style="${backlogFieldsStyle}">
        ${numField('max_backlog', 'Max Backlog', gBacklog)}
        ${backlogModeField}
        ${numField('missing_grace_hours', 'Grace Period (Hours)', gGrace)}
        <div></div>
      </div>`;

  const disabledTag = isDisabled
    ? `<span class="help" style="font-size:11px;color:var(--muted)">Disabled</span>`
    : `<div style="display:flex;align-items:center;gap:6px" id="${cardId}-status">${statusHtml}</div>`;

  const globalNotify = _getGlobal(kind, 'notifications_enabled');
  const hasOvNotify = 'notifications_enabled' in ov;
  const notifyVal = hasOvNotify ? ov.notifications_enabled : globalNotify;
  const notifyRowClass = hasOvNotify ? 'notify-footer-row ov-active' : 'notify-footer-row';
  const notifyLabel = hasOvNotify
    ? `${notifyVal ? 'On (Override)' : 'Off (Override)'} Global: ${globalNotify ? 'On' : 'Off'}`
    : `${notifyVal ? 'On' : 'Off'} (Global: ${globalNotify ? 'On' : 'Off'})`;

  // Inner divider + group label helpers (inline styles — no new CSS classes required)
  const innerDivider = `<div style="height:1px;background:var(--border);margin:10px 0"></div>`;
  const grpHead = (text) => `<div style="font-size:10px;font-weight:700;letter-spacing:.07em;text-transform:uppercase;color:var(--muted);margin-bottom:8px">${text}</div>`;

  return `<div class="${'ov-card' + (solo ? ' ov-solo' : '')}" id="${cardId}" data-kind="${kind}" data-idx="${idx}" data-name="${escapeHtml(inst.name)}" style="${disabledBorder}">
    <div class="ov-card-hdr">
      <div style="display:flex;align-items:center;gap:7px">
        <div class="${badgeClass}" style="${badgeStyle}"><div class="${dotClass}" style="${dotStyle}"></div>${escapeHtml(inst.name)}</div>
      </div>
      ${disabledTag}
    </div>
    <div style="${disabledStyle}">
      <!-- Cooldown — applies to both pipelines, sits above the cutoff/backlog split -->
      <div class="ov-fields" style="margin-bottom:10px">
        <div style="grid-column:1/-1;max-width:50%">
          ${numField('cooldown_hours', 'Cooldown Hours', gCooldown)}
        </div>
      </div>
      ${innerDivider}
      <!-- Cutoff Unmet group -->
      ${grpHead('Cutoff Unmet')}
      <div class="ov-fields" style="margin-bottom:10px">
        ${numField('max_cutoff_unmet', 'Max', gCutoff)}
        ${modeField}
      </div>
      ${innerDivider}
      <!-- Backlog group — toggle gates the fields below it visually -->
      ${grpHead('Backlog')}
      <div class="${blRowClass}" id="${cardId}-bl-row" style="margin-bottom:8px">
        <span class="help" style="font-size:11px" id="${cardId}-bl-label">${blLabel}</span>
        <label class="toggle">
          <input type="checkbox" id="${cardId}-backlog_enabled"${backlogVal ? ' checked' : ''}
            onchange="markCardDirty('${kind}',${idx}); updateBacklogLabel('${kind}',${idx})"/>
          <span class="toggle-track"></span>
          <span class="toggle-thumb"></span>
        </label>
      </div>
      ${backlogFieldsHtml}
      <!-- Notifications footer -->
      <div class="${notifyRowClass}" id="${cardId}-notify-row">
        <span class="help" style="font-size:11.5px" id="${cardId}-notify-label">${notifyLabel}</span>
        <label class="toggle">
          <input type="checkbox" id="${cardId}-notifications_enabled"${notifyVal ? ' checked' : ''}
            onchange="markCardDirty('${kind}',${idx}); updateNotifyLabel('${kind}',${idx})"/>
          <span class="toggle-track"></span>
          <span class="toggle-thumb"></span>
        </label>
      </div>
      <div class="ov-card-foot">
        <button class="ov-rst-all" onclick="resetCardOverrides('${kind}',${idx})">Reset All to Global</button>
        <button class="btn sm primary" onclick="applyOverrides('${kind}',${idx})">Apply</button>
      </div>
    </div>
  </div>`;
}

function renderOverridesCards() {
  if (!CFG) return;
  const grid = el('overrides-grid');
  if (!grid) return;
  let html = '';
  let hasAny = false;
  ['radarr', 'sonarr'].forEach(kind => {
    const insts = CFG.instances[kind] || [];
    if (!insts.length) return;
    hasAny = true;
    const label = kind.charAt(0).toUpperCase() + kind.slice(1);
    html += `<div class="ov-divider"><span class="ov-divider-label">${label}</span><span class="ov-divider-line"></span></div>`;
    insts.forEach((inst, idx) => {
      html += _buildOverrideCard(kind, idx, inst, insts.length === 1);
    });
  });
  grid.innerHTML = hasAny ? html : '<p class="help" style="color:var(--muted)">No instances configured.</p>';
}

function renderSingleOverrideCard(kind, idx) {
  const insts = CFG.instances[kind] || [];
  const inst = insts[idx];
  if (!inst) return;
  const cardId = _ovCardId(kind, idx);
  const existing = el(cardId);
  if (!existing) return;
  const newHtml = _buildOverrideCard(kind, idx, inst, insts.length === 1);
  existing.outerHTML = newHtml;
}

function markCardDirty(kind, idx) {
  const card = el(_ovCardId(kind, idx));
  if (!card) return;
  card.classList.add('ov-dirty');
  const status = el(_ovCardId(kind, idx) + '-status');
  if (status && !status.querySelector('.ov-pending-dot')) {
    status.innerHTML = `<span class="help" style="font-size:11px;color:var(--warn)">Pending</span><span class="ov-pending-dot"></span>`;
  }
}

function updateBacklogLabel(kind, idx) {
  const cardId = _ovCardId(kind, idx);
  const checked = el(cardId + '-backlog_enabled').checked;
  const globalBacklog = _getGlobal(kind, 'backlog_enabled');
  const row = el(cardId + '-bl-row');
  const lbl = el(cardId + '-bl-label');
  const label = `${checked ? 'On (Override)' : 'Off (Override)'} Global: ${globalBacklog ? 'On' : 'Off'}`;
  if (lbl) lbl.textContent = label;
  if (row) { row.classList.add('ov-active'); }
  const fields = el(cardId + '-backlog-fields');
  if (fields) {
    fields.style.opacity = checked ? '' : '0.38';
    fields.style.pointerEvents = checked ? '' : 'none';
  }
}

function updateNotifyLabel(kind, idx) {
  const cardId = _ovCardId(kind, idx);
  const checked = el(cardId + '-notifications_enabled').checked;
  const globalNotify = _getGlobal(kind, 'notifications_enabled');
  const row = el(cardId + '-notify-row');
  const lbl = el(cardId + '-notify-label');
  const label = `${checked ? 'On (Override)' : 'Off (Override)'} Global: ${globalNotify ? 'On' : 'Off'}`;
  if (lbl) lbl.textContent = label;
  if (row) row.classList.add('ov-active');
}

// applyOverrides — reads the current DOM state of one card and writes a new
// overrides object to the server via /api/instance/overrides.
// Write/delete rules: an empty string input removes that field from the override
// dict (falls back to global); sample_mode set to '__global__' removes the override;
// backlog_enabled and notifications_enabled are written whenever their current value
// differs from the global, or if an override already existed (to allow explicit
// matching-global saves that still show ov-active until Reset is clicked).
async function applyOverrides(kind, idx) {
  const cardId = _ovCardId(kind, idx);
  const inst = (CFG.instances[kind] || [])[idx];
  if (!inst) return;
  const existing = inst.overrides || {};

  // Build new overrides — only include fields that differ from global or were already overridden
  const newOv = Object.assign({}, existing);

  const numFields = ['cooldown_hours', 'max_cutoff_unmet', 'max_backlog'];
  if (kind === 'radarr') numFields.push('max_missing_days');
  numFields.push('missing_grace_hours');

  numFields.forEach(field => {
    const input = el(cardId + '-' + field);
    if (!input) return;
    const raw = input.value.trim();
    if (raw !== '') {
      newOv[field] = parseInt(raw, 10);
      input.classList.add('ov-active');
    } else if (field in newOv) {
      delete newOv[field];
      input.classList.remove('ov-active');
    }
  });

  // Sample mode — __global__ means Use Global (remove override), any valid mode saves it
  const modeEl = el(cardId + '-sample_mode');
  if (modeEl) {
    if (modeEl.value === '__global__' || modeEl.value === '') {
      delete newOv.sample_mode;
      modeEl.classList.remove('ov-active');
    } else {
      newOv.sample_mode = modeEl.value;
      modeEl.classList.add('ov-active');
    }
  }

  // Backlog sample mode — same __global__ sentinel pattern as sample_mode (v4.2.0)
  const backlogModeEl = el(cardId + '-backlog_sample_mode');
  if (backlogModeEl) {
    if (backlogModeEl.value === '__global__' || backlogModeEl.value === '') {
      delete newOv.backlog_sample_mode;
      backlogModeEl.classList.remove('ov-active');
    } else {
      newOv.backlog_sample_mode = backlogModeEl.value;
      backlogModeEl.classList.add('ov-active');
    }
  }

  // Backlog enabled — always store current value if input has been interacted with
  const blInput = el(cardId + '-backlog_enabled');
  if (blInput) {
    const globalBacklog = _getGlobal(kind, 'backlog_enabled');
    if (blInput.checked !== globalBacklog || 'backlog_enabled' in existing) {
      newOv.backlog_enabled = blInput.checked;
    }
  }

  // Notifications enabled — always store current value if input has been interacted with
  const notifyInput = el(cardId + '-notifications_enabled');
  if (notifyInput) {
    const globalNotify = _getGlobal(kind, 'notifications_enabled');
    if (notifyInput.checked !== globalNotify || 'notifications_enabled' in existing) {
      newOv.notifications_enabled = notifyInput.checked;
    }
  }

  try {
    await api('/api/instance/overrides', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({kind, idx, overrides: newOv})
    });
    // Update local CFG
    inst.overrides = newOv;
    // Re-render just this card so all styles reflect the saved state correctly
    renderSingleOverrideCard(kind, idx);
  } catch(e) {
    showAlert('Failed to save overrides: ' + e.message);
  }
}

async function resetCardOverrides(kind, idx) {
  const confirmed = await showConfirm('Reset All to Global', 'Remove all overrides for this instance? It will inherit global settings.', 'Reset', true);
  if (!confirmed) return;
  const inst = (CFG.instances[kind] || [])[idx];
  if (!inst) return;
  try {
    await api('/api/instance/overrides', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({kind, idx, overrides: {}})
    });
    inst.overrides = {};
    renderOverridesCards();
  } catch(e) {
    showAlert('Failed to reset overrides: ' + e.message);
  }
}

function resetFieldOverride(kind, idx, field) {
  const cardId = _ovCardId(kind, idx);
  if (field === 'sample_mode' || field === 'backlog_sample_mode') {
    // Both mode selects use the __global__ sentinel to indicate no override
    const sel = el(cardId + '-' + field);
    if (sel) { sel.value = '__global__'; sel.classList.remove('ov-active'); }
  } else {
    const input = el(cardId + '-' + field);
    if (!input) return;
    input.value = '';
    input.classList.remove('ov-active');
  }
  markCardDirty(kind, idx);
}

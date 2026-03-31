// ── Filters tab ─────────────────────────────────────────────────────────────
// Owns: fillFilters (tab entry point), loadArrData (fetch tags + profiles from
// arr instance), saveFilters (persist sweep_filters to config), pill rendering,
// onFilterInstanceChange (instance selector handler).
//
// State is held per kind|idx in FILTER_STATE so switching instances and back
// does not lose unsaved selections within the same page session.

const FILTER_STATE = {};

// ── Entry point — called by _onTabShown when Filters tab opens ────────────────
function fillFilters() {
  const cfg = CFG;
  const radarrInsts = cfg?.instances?.radarr || [];
  const sonarrInsts = cfg?.instances?.sonarr || [];
  const hasAny = radarrInsts.length > 0 || sonarrInsts.length > 0;

  el('filters-no-instances').style.display = hasAny ? 'none' : '';
  el('filters-content').style.display      = hasAny ? ''     : 'none';

  if (!hasAny) return;

  _fillInstanceSelector('radarr', radarrInsts);
  _fillInstanceSelector('sonarr', sonarrInsts);
  _renderFilterBox('radarr');
  _renderFilterBox('sonarr');
}

// ── Pending check — used by showTab guard ─────────────────────────────────────
function _filterHasPending() {
  return Object.values(FILTER_STATE).some(s => s.dirty === true);
}

// ── Instance selector ─────────────────────────────────────────────────────────
function _fillInstanceSelector(kind, instances) {
  // Bug 4 fix: only show enabled instances in the selector
  const enabledInstances = instances.filter(i => i.enabled !== false);
  const sel      = el('filter-' + kind + '-idx');
  const hdrLeft  = el('filter-' + kind + '-hdr-left');
  if (!hdrLeft) return;

  // Clear previous pill if any
  const existing = hdrLeft.querySelector('.filter-inst-pill');
  if (existing) existing.remove();

  if (enabledInstances.length === 0) {
    if (sel) sel.style.display = 'none';
    return;
  }

  // Build pill — instance name with dot inside, always enabled (disabled filtered out)
  const currentVal = parseInt(el('filter-' + kind + '-idx')?.value || '0', 10);
  const inst = instances[currentVal] || enabledInstances[0];
  const dotColor   = kind === 'radarr' ? 'var(--accent)'        : 'var(--ok)';
  const pillBg     = kind === 'radarr' ? 'var(--accent-dim)'    : 'rgba(34,197,94,.08)';
  const pillBorder = kind === 'radarr' ? 'var(--accent-border)' : 'rgba(34,197,94,.22)';
  const pillColor  = kind === 'radarr' ? 'var(--accent-lt)'     : '#86efac';

  const pill = document.createElement('span');
  pill.className = 'filter-inst-pill';
  pill.style.cssText = `display:inline-flex;align-items:center;gap:5px;font-size:11px;font-weight:700;padding:2px 9px;border-radius:999px;letter-spacing:.04em;background:${pillBg};border:1px solid ${pillBorder};color:${pillColor}`;
  pill.innerHTML = `<span style="width:6px;height:6px;border-radius:50%;background:${dotColor};flex-shrink:0"></span>${escapeHtml(inst.name || (kind === 'radarr' ? 'Radarr' : 'Sonarr'))}`;
  hdrLeft.insertBefore(pill, hdrLeft.firstChild);

  // Dropdown — only shown for multiple enabled instances
  if (!sel) return;
  if (enabledInstances.length === 1) {
    sel.style.display = 'none';
  } else {
    sel.style.display = '';
    const current = parseInt(sel.value || '0', 10);
    sel.innerHTML = enabledInstances.map(inst => {
      const realIdx = instances.indexOf(inst);
      return `<option value="${realIdx}"${realIdx === current ? ' selected' : ''}>${inst.name || 'Instance ' + realIdx}</option>`;
    }).join('');
  }
}

// ── Instance selector change handler ─────────────────────────────────────────
function onFilterInstanceChange(kind) {
  _renderFilterBox(kind);
}

// ── Render one filter box body ────────────────────────────────────────────────
function _renderFilterBox(kind) {
  const cfg = CFG;
  const instances = cfg?.instances?.[kind] || [];
  const body = el('filter-' + kind + '-body');
  const loadBtn = el('filter-' + kind + '-load-btn');
  const box = el('filters-' + kind + '-box');
  if (!body) return;

  const enabledInstances = instances.filter(i => i.enabled !== false);

  if (instances.length === 0) {
    // No instances of this kind configured at all
    body.innerHTML = `<div class="help" style="text-align:center;padding:20px 0;opacity:.5">No ${kind === 'radarr' ? 'Radarr' : 'Sonarr'} instances configured.</div>`;
    if (loadBtn) loadBtn.style.display = 'none';
    return;
  }

  if (enabledInstances.length === 0) {
    // Instances exist but all disabled — show greyed read-only state
    if (loadBtn) loadBtn.style.display = 'none';
    if (box) {
      box.style.opacity = '0.45';
      box.style.pointerEvents = 'none';
      // Show "All Instances Disabled" in header
      const hdr = box.querySelector('.card-hdr');
      if (hdr && !hdr.querySelector('.filter-disabled-label')) {
        const lbl = document.createElement('span');
        lbl.className = 'filter-disabled-label help';
        lbl.textContent = 'All Instances Disabled';
        hdr.insertBefore(lbl, hdr.querySelector('button'));
      }
    }
    // Show last saved filters read-only from config
    const idx = 0;
    const savedFilters = (cfg?.instances?.[kind]?.[idx]?.sweep_filters) || {};
    const savedTagIds     = savedFilters.excluded_tags     || [];
    const savedProfileIds = savedFilters.excluded_profiles || [];
    const stateKey = kind + '|' + idx;
    const state = FILTER_STATE[stateKey];
    // If we have loaded state use it, otherwise render pills from saved IDs with numeric fallback
    const tags     = state?.tags     || savedTagIds.map(id => ({ id, label: String(id) }));
    const profiles = state?.profiles || savedProfileIds.map(id => ({ id, name: String(id) }));
    body.innerHTML = _buildLoadedBodyHTML(kind, tags, savedTagIds, profiles, savedProfileIds, true);
    return;
  }

  // Restore box to active state in case it was previously disabled
  if (box) { box.style.opacity = ''; box.style.pointerEvents = ''; }
  if (loadBtn) loadBtn.style.display = '';
  const hdrLbl = box && box.querySelector('.filter-disabled-label');
  if (hdrLbl) hdrLbl.remove();

  const idx = _getSelectedIdx(kind);
  const stateKey = kind + '|' + idx;
  const state = FILTER_STATE[stateKey];

  if (!state || !state.loaded) {
    body.innerHTML = `<div class="help" style="text-align:center;padding:20px 0">Click <strong>Load Tags &amp; Profiles</strong> to fetch from this instance.</div>`;
    if (loadBtn) loadBtn.textContent = 'Load Tags & Profiles';
    return;
  }

  if (loadBtn) loadBtn.textContent = 'Refresh';
  body.innerHTML = _buildLoadedBodyHTML(kind, state.tags, state.excludedTags, state.profiles, state.excludedProfiles, false);
  _renderPills(kind, 'tags');
  _renderPills(kind, 'profiles');
  _renderList(kind, 'tags', '');
  _renderList(kind, 'profiles', '');
}

// ── Build loaded body HTML ────────────────────────────────────────────────────
function _buildLoadedBodyHTML(kind, tags, excludedTagIds, profiles, excludedProfileIds, readOnly) {
  const noTags     = tags.length === 0;
  const noProfiles = profiles.length === 0;
  const searchAttr        = readOnly || noTags     ? 'disabled' : `oninput="_filterSearch('${kind}','tags')" autocomplete="off"`;
  const profileSearchAttr = readOnly || noProfiles ? 'disabled' : `oninput="_filterSearch('${kind}','profiles')" autocomplete="off"`;
  const noTagsMsg     = noTags     ? `<div class="help" style="font-style:italic;padding:5px 0">No tags configured in this instance</div>` : '';
  const noProfilesMsg = noProfiles ? `<div class="help" style="font-style:italic;padding:5px 0">No quality profiles found</div>` : '';
  return `
    <div class="filter-section">
      <div class="card-label" style="margin-bottom:8px;flex-shrink:0">Filtered Tags</div>
      <div id="filter-${kind}-tag-pills" class="filter-pill-area"></div>
      <input id="filter-${kind}-tag-search" class="filter-search" placeholder="Search tags…" ${searchAttr}>
      <div id="filter-${kind}-tag-list" class="filter-list">${noTagsMsg}</div>
    </div>
    <hr style="border:none;border-top:1px solid var(--border);margin:8px 0;flex-shrink:0">
    <div class="filter-section">
      <div class="card-label" style="margin-bottom:8px;flex-shrink:0">Filtered Quality Profiles</div>
      <div id="filter-${kind}-profile-pills" class="filter-pill-area"></div>
      <input id="filter-${kind}-profile-search" class="filter-search" placeholder="Search profiles…" ${profileSearchAttr}>
      <div id="filter-${kind}-profile-list" class="filter-list">${noProfilesMsg}</div>
    </div>
    <div class="save-bar" style="margin-top:8px;flex-shrink:0">
      <span class="msg" id="filter-${kind}-msg" style="flex:1;text-align:center"></span>
      <button class="btn sm primary" ${readOnly ? 'disabled' : `onclick="saveFilters('${kind}')"`}>Apply</button>
    </div>`;
}

// ── Pill area renderer ────────────────────────────────────────────────────────
function _renderPills(kind, section) {
  const idx      = _getSelectedIdx(kind);
  const stateKey = kind + '|' + idx;
  const state    = FILTER_STATE[stateKey];
  if (!state) return;

  const items    = section === 'tags' ? state.tags    : state.profiles;
  const excluded = section === 'tags' ? state.excludedTags : state.excludedProfiles;
  const labelKey = section === 'tags' ? 'label' : 'name';
  const wrap     = el('filter-' + kind + '-' + (section === 'tags' ? 'tag' : 'profile') + '-pills');
  if (!wrap) return;

  const selected = items.filter(i => excluded.includes(i.id));
  if (selected.length === 0) {
    wrap.innerHTML = `<span class="help" style="font-style:italic">None filtered</span>`;
    return;
  }
  wrap.innerHTML = selected.map(item =>
    `<span class="filter-active-pill${kind === 'sonarr' ? ' pill-sonarr' : ''}" onclick="_removePill('${kind}','${section}',${item.id})">${item[labelKey]} <span class="filter-pill-x">×</span></span>`
  ).join('');
}

// ── List renderer ─────────────────────────────────────────────────────────────
function _renderList(kind, section, search) {
  const idx      = _getSelectedIdx(kind);
  const stateKey = kind + '|' + idx;
  const state    = FILTER_STATE[stateKey];
  if (!state) return;

  const items    = section === 'tags' ? state.tags    : state.profiles;
  const excluded = section === 'tags' ? state.excludedTags : state.excludedProfiles;
  const labelKey = section === 'tags' ? 'label' : 'name';
  const wrap     = el('filter-' + kind + '-' + (section === 'tags' ? 'tag' : 'profile') + '-list');
  if (!wrap) return;

  const accentLt  = kind === 'radarr' ? 'var(--accent-lt)'  : 'var(--ok)';
  const accentDim = kind === 'radarr' ? 'var(--accent-dim)' : 'rgba(34,197,94,.1)';

  if (items.length === 0) {
    wrap.innerHTML = `<div class="help" style="padding:5px 8px;font-style:italic">No ${section === 'tags' ? 'tags' : 'quality profiles'} configured in this instance.</div>`;
    return;
  }

  const q = search.toLowerCase();
  const filtered = q ? items.filter(i => i[labelKey].toLowerCase().includes(q)) : items;

  if (filtered.length === 0) {
    wrap.innerHTML = `<div class="help" style="padding:5px 8px">No results</div>`;
    return;
  }

  wrap.innerHTML = filtered.map(item => {
    const sel = excluded.includes(item.id);
    const activeClass = sel ? (' active-' + kind) : '';
    return `<div class="filter-list-item${activeClass}"
      onclick="_toggleFilterItem('${kind}','${section}',${item.id})">
      <span>${item[labelKey]}</span>
      ${sel ? '<span style="font-size:11px;opacity:.8">✓</span>' : ''}
    </div>`;
  }).join('');
}

// ── Search handler ────────────────────────────────────────────────────────────
function _filterSearch(kind, section) {
  const inputId = 'filter-' + kind + '-' + (section === 'tags' ? 'tag' : 'profile') + '-search';
  const val = (el(inputId) || {}).value || '';
  _renderList(kind, section, val);
}

// ── Status helper — sets msg element with colour and toggles pending border ───
function _setFilterStatus(kind, type, text) {
  const msg  = el('filter-' + kind + '-msg');
  const box  = el('filters-' + kind + '-box');
  if (box) box.classList.toggle('filter-box-pending', type === 'pending');
  if (!msg) return;
  if (type === 'pending') {
    msg.innerHTML = `<span style="display:inline-flex;align-items:center;gap:5px;color:var(--warn)"><span style="width:6px;height:6px;border-radius:50%;background:var(--warn);flex-shrink:0;display:inline-block"></span>${text}</span>`;
  } else if (type === 'ok') {
    msg.style.color = 'var(--ok)';
    msg.textContent = text;
  } else if (type === 'error') {
    msg.style.color = 'var(--bad)';
    msg.textContent = text;
  } else {
    msg.style.color = '';
    msg.textContent = text;
  }
}

// ── Toggle item in/out of excluded set ───────────────────────────────────────
function _toggleFilterItem(kind, section, id) {
  const idx      = _getSelectedIdx(kind);
  const stateKey = kind + '|' + idx;
  const state    = FILTER_STATE[stateKey];
  if (!state) return;

  const arr = section === 'tags' ? state.excludedTags : state.excludedProfiles;
  const pos = arr.indexOf(id);
  if (pos === -1) arr.push(id); else arr.splice(pos, 1);
  state.dirty = true;

  _renderPills(kind, section);
  const searchId = 'filter-' + kind + '-' + (section === 'tags' ? 'tag' : 'profile') + '-search';
  _renderList(kind, section, (el(searchId) || {}).value || '');

  const msg = el('filter-' + kind + '-msg');
  if (msg) msg.textContent = '';
  _setFilterStatus(kind, 'pending', 'Pending');
}

// ── Remove via pill × ─────────────────────────────────────────────────────────
function _removePill(kind, section, id) {
  _toggleFilterItem(kind, section, id);
}

// ── Load tags and profiles from arr instance ──────────────────────────────────
async function loadArrData(kind) {
  const idx = _getSelectedIdx(kind);
  const loadBtn = el('filter-' + kind + '-load-btn');
  const body    = el('filter-' + kind + '-body');
  if (loadBtn) { loadBtn.disabled = true; loadBtn.textContent = 'Loading…'; }

  try {
    const [tagRes, profileRes] = await Promise.all([
      api('/api/arr/tags?kind=' + kind + '&idx=' + idx),
      api('/api/arr/profiles?kind=' + kind + '&idx=' + idx),
    ]);

    if (!tagRes?.ok || !profileRes?.ok) {
      const err = tagRes?.error || profileRes?.error || 'Failed to load — check instance connectivity';
      if (body) body.innerHTML = `<div class="help" style="color:var(--bad);text-align:center;padding:16px 0">${err}</div>`;
      if (loadBtn) { loadBtn.disabled = false; loadBtn.textContent = 'Retry'; }
      return;
    }

    const stateKey = kind + '|' + idx;
    // Preserve existing selections if already in state, else load from saved config
    const existing = FILTER_STATE[stateKey] || {};
    const savedFilters = (CFG?.instances?.[kind]?.[idx]?.sweep_filters) || {};

    FILTER_STATE[stateKey] = {
      loaded:          true,
      tags:            tagRes.tags     || [],
      profiles:        profileRes.profiles || [],
      excludedTags:    existing.excludedTags    ?? (savedFilters.excluded_tags    || []),
      excludedProfiles:existing.excludedProfiles ?? (savedFilters.excluded_profiles || []),
    };

    if (loadBtn) { loadBtn.disabled = false; }
    _renderFilterBox(kind);
  } catch (e) {
    if (body) body.innerHTML = `<div class="help" style="color:var(--bad);text-align:center;padding:16px 0">Unexpected error — see console</div>`;
    if (loadBtn) { loadBtn.disabled = false; loadBtn.textContent = 'Retry'; }
  }
}

// ── Save filters to config ────────────────────────────────────────────────────
async function saveFilters(kind) {
  const idx = _getSelectedIdx(kind);
  const stateKey = kind + '|' + idx;
  const state = FILTER_STATE[stateKey];
  const msg = el('filter-' + kind + '-msg');

  if (!state) return;

  try {
    const cfg = await api('/api/config');
    if (!cfg) { if (msg) _setFilterStatus(kind, 'error', 'Failed to load config'); return; }

    const instances = cfg.instances?.[kind] || [];
    if (idx >= instances.length) { if (msg) _setFilterStatus(kind, 'error', 'Instance not found'); return; }

    // Capture old values before overwriting so we can detect changes
    const oldFilters  = instances[idx].sweep_filters || {};
    const oldTags     = JSON.stringify((oldFilters.excluded_tags || []).slice().sort());
    const oldProfiles = JSON.stringify((oldFilters.excluded_profiles || []).slice().sort());
    const newTags     = JSON.stringify((state.excludedTags || []).slice().sort());
    const newProfiles = JSON.stringify((state.excludedProfiles || []).slice().sort());
    const filtersChanged = (oldTags !== newTags) || (oldProfiles !== newProfiles);

    instances[idx].sweep_filters = {
      excluded_tags:     state.excludedTags,
      excluded_profiles: state.excludedProfiles,
    };

    const res = await api('/api/config', { method: 'POST', body: JSON.stringify(cfg) });
    if (res?.ok) {
      CFG = cfg;
      state.dirty = false;
      _setFilterStatus(kind, 'ok', 'Saved');
      setTimeout(() => { _setFilterStatus(kind, '', ''); }, 2000);

      // If CF Score is enabled and filter-relevant fields changed, show the sync modal
      if (filtersChanged && cfg.cf_score_enabled) {
        el('cfFilterSyncModal').style.display = 'flex';
      }
    } else {
      _setFilterStatus(kind, 'error', res?.error || 'Save failed');
    }
  } catch (e) {
    _setFilterStatus(kind, 'error', 'Unexpected error — see console');
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function _getSelectedIdx(kind) {
  const sel = el('filter-' + kind + '-idx');
  return sel && sel.style.display !== 'none' ? parseInt(sel.value || '0', 10) : 0;
}

// ── CF Filter Sync Modal ──────────────────────────────────────────────────────

function closeCfFilterSyncModal() {
  el('cfFilterSyncModal').style.display = 'none';
}

// syncCfIndexFromModal -- triggered by "Sync Now" in the CF filter sync modal.
// Calls the scan API directly then switches to the CF Score tab so the user
// can see progress. Does not depend on ui-cf-scores.js being loaded.
async function syncCfIndexFromModal() {
  closeCfFilterSyncModal();
  try {
    await api('/api/cf-scores/scan', {method: 'POST'});
  } catch(e) {
    // Non-fatal -- user can manually trigger from CF Score tab
    console.debug('[CF Filter] syncCfIndexFromModal scan request failed:', e);
  }
  // Switch to CF Score tab so the user sees progress
  if (typeof showTab === 'function') showTab('cf-scores');
}

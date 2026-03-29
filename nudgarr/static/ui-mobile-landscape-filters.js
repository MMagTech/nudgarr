// ── Landscape Filters rail/panel ───────────────────────────────────
// Handles the Filters rail/panel in landscape mode (⊘ Filters nav tab).
// Overrides landscape logic lives in ui-mobile-landscape.js.
//
// State: LS_FILTERS_SEL holds the currently selected "kind|idx" key.
// FILTER_STATE (declared in ui-filters.js, shared) holds loaded tags,
// profiles, and pending excluded selections per instance key.
//
// Flow: lsFiltersRenderRail() builds the instance list. Tapping an
// instance calls lsFiltersSelectInst() which calls lsFiltersRenderPanel().
// The panel shows Excluded Tags and Excluded Profiles with pill display
// and searchable lists. lsFiltersApply() persists to /api/config.

let LS_FILTERS_SEL = null; // currently selected instance key "kind|idx"

// lsFiltersRenderRail — rebuilds the rail listing all instances with a
// filter count chip showing how many tags + profiles are excluded.
function lsFiltersRenderRail() {
  const rail = document.getElementById('ls-filters-rail');
  if (!rail) return;

  const cfg = CFG;
  const allInsts = [];
  for (const kind of ['radarr', 'sonarr']) {
    (cfg?.instances?.[kind] || []).forEach((inst, idx) => {
      allInsts.push({ kind, idx, name: inst.name || (kind + ' ' + idx), enabled: inst.enabled !== false });
    });
  }

  if (!allInsts.length) {
    rail.innerHTML = '<div class="ls-ov-disabled-notice">No instances configured.</div>';
    lsFiltersRenderPanel(null);
    return;
  }

  // Default selection to first enabled instance if none set
  if (!LS_FILTERS_SEL || !allInsts.find(i => _lsOvKey(i.kind, i.idx) === LS_FILTERS_SEL)) {
    const first = allInsts.find(i => i.enabled) || allInsts[0];
    LS_FILTERS_SEL = _lsOvKey(first.kind, first.idx);
  }

  rail.innerHTML = allInsts.map(inst => {
    const key = _lsOvKey(inst.kind, inst.idx);
    const isActive = key === LS_FILTERS_SEL;
    const isDisabled = !inst.enabled;
    const dotColor     = isDisabled ? 'var(--muted)' : (inst.kind === 'radarr' ? 'var(--accent)' : 'var(--ok)');
    const dotGlow      = (!isDisabled && isActive) ? (inst.kind === 'sonarr' ? ';box-shadow:0 0 5px rgba(34,197,94,.5)' : ';box-shadow:0 0 5px rgba(91,114,245,.6)') : '';
    const state = FILTER_STATE[key];
    const filterCount = state ? (state.excludedTags.length + state.excludedProfiles.length) : 0;
    const savedFilters = cfg?.instances?.[inst.kind]?.[inst.idx]?.sweep_filters || {};
    const savedCount = (savedFilters.excluded_tags || []).length + (savedFilters.excluded_profiles || []).length;
    const displayCount = filterCount || savedCount;
    const accentColor  = inst.kind === 'radarr' ? 'var(--accent-lt)'     : 'var(--ok)';
    const accentBg     = inst.kind === 'radarr' ? 'var(--accent-dim)'    : 'rgba(34,197,94,.1)';
    const accentBorder = inst.kind === 'radarr' ? 'var(--accent-border)' : 'rgba(34,197,94,.28)';

    return `<div class="ls-ov-rail-item${isActive ? ' ls-ov-active' : ''}${isDisabled ? ' ls-ov-disabled' : ''}"
      onclick="${isDisabled ? '' : `lsFiltersSelectInst('${inst.kind}',${inst.idx})`}">
      <div class="ls-ov-rail-row1">
        <div style="display:flex;align-items:center;gap:6px;min-width:0;flex:1">
          <div style="width:7px;height:7px;border-radius:50%;background:${dotColor}${dotGlow};flex-shrink:0"></div>
          <span class="ls-ov-rail-name">${inst.name}</span>
        </div>
      </div>
      ${displayCount > 0 ? `<div style="margin-top:4px;margin-left:13px"><span style="display:inline-flex;align-items:center;padding:1px 8px;border-radius:999px;font-size:10px;background:${accentBg};border:1px solid ${accentBorder};color:${accentColor}">${displayCount} Filter${displayCount !== 1 ? 's' : ''}</span></div>` : ''}
    </div>`;
  }).join('');

  lsFiltersRenderPanel(LS_FILTERS_SEL);
}

function lsFiltersSelectInst(kind, idx) {
  LS_FILTERS_SEL = _lsOvKey(kind, idx);
  lsFiltersRenderRail();
}

// lsFiltersRenderPanel — builds the right-column panel for the selected
// instance. If the instance has never been loaded (not in FILTER_STATE)
// shows a load prompt. Otherwise renders tag and profile sections with
// active pills and a searchable scrollable list for each.
function lsFiltersRenderPanel(key) {
  const body   = document.getElementById('ls-filters-body');
  const status = document.getElementById('ls-filters-status');
  const loadBtn = document.getElementById('ls-filters-load-btn');
  const applyBtn = document.getElementById('ls-filters-apply');
  if (!body) return;

  if (!key) {
    body.innerHTML = '<div class="ls-ov-disabled-notice">No instance selected.</div>';
    if (status) status.textContent = '';
    return;
  }

  const [kind, idxStr] = key.split('|');
  const idx = parseInt(idxStr, 10);
  const cfg = CFG;
  const inst = cfg?.instances?.[kind]?.[idx];
  if (!inst) return;

  const disabled = inst.enabled === false;
  const foot = document.getElementById('ls-filters-foot');
  if (foot) foot.classList.toggle('ls-ov-panel-disabled', disabled);

  if (disabled) {
    if (status) status.textContent = 'All Instances Disabled';
    if (loadBtn) loadBtn.disabled = true;
    if (applyBtn) applyBtn.disabled = true;
  } else {
    if (loadBtn) { loadBtn.disabled = false; }
    if (applyBtn) { applyBtn.disabled = false; }
  }

  const state = FILTER_STATE[key];
  const savedFilters = inst.sweep_filters || {};
  const accentColor  = kind === 'radarr' ? 'var(--accent-lt)' : 'var(--ok)';
  const accentBg     = kind === 'radarr' ? 'var(--accent-dim)' : 'rgba(34,197,94,.1)';

  if (!state || !state.loaded) {
    body.innerHTML = `<div class="ls-ov-disabled-notice" style="padding:20px 0">Tap <strong>Load</strong> to fetch tags and profiles.</div>`;
    if (loadBtn) loadBtn.textContent = 'Load';
    if (status) status.textContent = '';
    return;
  }

  if (loadBtn) loadBtn.textContent = 'Refresh';

  const totalFilters = state.excludedTags.length + state.excludedProfiles.length;
  if (status) status.textContent = totalFilters > 0 ? `${totalFilters} Filter${totalFilters !== 1 ? 's' : ''} Active` : 'No Filters Set';

  body.innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:0 12px;flex:1;min-height:0">
      <div style="display:flex;flex-direction:column;min-height:0">
        <div class="ls-col-label" style="margin-bottom:6px;flex-shrink:0">Filtered Tags</div>
        <div id="ls-filters-tag-pills" style="min-height:24px;max-height:50px;overflow-y:auto;display:flex;flex-wrap:wrap;align-content:flex-start;gap:4px;margin-bottom:6px;flex-shrink:0"></div>
        <input id="ls-filters-tag-search" class="filter-search" placeholder="Search tags…" oninput="lsFiltersSearch('tags')" autocomplete="off" style="flex-shrink:0">
        <div id="ls-filters-tag-list" class="filter-list" style="flex:1;overflow-y:auto;max-height:none"></div>
      </div>
      <div style="display:flex;flex-direction:column;min-height:0">
        <div class="ls-col-label" style="margin-bottom:6px;flex-shrink:0">Filtered Quality Profiles</div>
        <div id="ls-filters-profile-pills" style="min-height:24px;max-height:50px;overflow-y:auto;display:flex;flex-wrap:wrap;align-content:flex-start;gap:4px;margin-bottom:6px;flex-shrink:0"></div>
        <input id="ls-filters-profile-search" class="filter-search" placeholder="Search profiles…" oninput="lsFiltersSearch('profiles')" autocomplete="off" style="flex-shrink:0">
        <div id="ls-filters-profile-list" class="filter-list" style="flex:1;overflow-y:auto;max-height:none"></div>
      </div>
    </div>`;

  _lsFiltersRenderPills('tags');
  _lsFiltersRenderPills('profiles');
  _lsFiltersRenderList('tags', '');
  _lsFiltersRenderList('profiles', '');
}

function _lsFiltersRenderPills(section) {
  const key   = LS_FILTERS_SEL;
  const state = FILTER_STATE[key];
  if (!state) return;
  const [kind] = key.split('|');
  const items    = section === 'tags' ? state.tags    : state.profiles;
  const excluded = section === 'tags' ? state.excludedTags : state.excludedProfiles;
  const labelKey = section === 'tags' ? 'label' : 'name';
  const wrap = document.getElementById('ls-filters-' + (section === 'tags' ? 'tag' : 'profile') + '-pills');
  if (!wrap) return;
  const accentColor  = kind === 'radarr' ? 'var(--accent-lt)' : 'var(--ok)';
  const accentBg     = kind === 'radarr' ? 'var(--accent-dim)' : 'rgba(34,197,94,.1)';
  const selected = items.filter(i => excluded.includes(i.id));
  if (!selected.length) {
    wrap.innerHTML = `<span class="help" style="font-style:italic;font-size:11px">None filtered</span>`;
    return;
  }
  wrap.innerHTML = selected.map(item =>
    `<span class="filter-active-pill${kind === 'sonarr' ? ' pill-sonarr' : ''}" style="font-size:11px;height:20px;padding:2px 8px"
      onclick="lsFiltersToggle('${section}',${item.id})">${item[labelKey]} <span class="filter-pill-x">×</span></span>`
  ).join('');
}

function _lsFiltersRenderList(section, search) {
  const key   = LS_FILTERS_SEL;
  const state = FILTER_STATE[key];
  if (!state) return;
  const [kind] = key.split('|');
  const items    = section === 'tags' ? state.tags    : state.profiles;
  const excluded = section === 'tags' ? state.excludedTags : state.excludedProfiles;
  const labelKey = section === 'tags' ? 'label' : 'name';
  const wrap = document.getElementById('ls-filters-' + (section === 'tags' ? 'tag' : 'profile') + '-list');
  if (!wrap) return;
  const accentColor = kind === 'radarr' ? 'var(--accent-lt)' : 'var(--ok)';
  const accentBg    = kind === 'radarr' ? 'var(--accent-dim)' : 'rgba(34,197,94,.1)';
  if (!items.length) {
    wrap.innerHTML = `<div class="help" style="padding:4px 6px;font-style:italic;font-size:11px">None configured in this instance.</div>`;
    return;
  }
  const q = search.toLowerCase();
  const filtered = q ? items.filter(i => i[labelKey].toLowerCase().includes(q)) : items;
  if (!filtered.length) { wrap.innerHTML = `<div class="help" style="padding:4px 6px;font-size:11px">No results</div>`; return; }
  const activeClass = kind === 'radarr' ? 'active-radarr' : 'active-sonarr';
  wrap.innerHTML = filtered.map(item => {
    const sel = excluded.includes(item.id);
    return `<div class="filter-list-item${sel ? ' ' + activeClass : ''}" onclick="lsFiltersToggle('${section}',${item.id})">
      <span>${item[labelKey]}</span>${sel ? '<span style="font-size:10px;opacity:.8">✓</span>' : ''}
    </div>`;
  }).join('');
}

function lsFiltersSearch(section) {
  const inputId = 'ls-filters-' + (section === 'tags' ? 'tag' : 'profile') + '-search';
  const val = (document.getElementById(inputId) || {}).value || '';
  _lsFiltersRenderList(section, val);
}

function lsFiltersToggle(section, id) {
  const key   = LS_FILTERS_SEL;
  const state = FILTER_STATE[key];
  if (!state) return;
  const arr = section === 'tags' ? state.excludedTags : state.excludedProfiles;
  const pos = arr.indexOf(id);
  if (pos === -1) arr.push(id); else arr.splice(pos, 1);
  _lsFiltersRenderPills(section);
  const searchId = 'ls-filters-' + (section === 'tags' ? 'tag' : 'profile') + '-search';
  _lsFiltersRenderList(section, (document.getElementById(searchId) || {}).value || '');
  const status = document.getElementById('ls-filters-status');
  const total = state.excludedTags.length + state.excludedProfiles.length;
  if (status) status.textContent = total > 0 ? `${total} filter${total !== 1 ? 's' : ''} active` : 'No filters set';
  lsFiltersRenderRail();
}

// lsFiltersLoad — fetches tags and profiles from the arr instance via
// /api/arr/tags and /api/arr/profiles, merges with any existing selections
// in FILTER_STATE, and re-renders the panel. Handles load/retry button state.
async function lsFiltersLoad() {
  const key = LS_FILTERS_SEL;
  if (!key) return;
  const [kind, idxStr] = key.split('|');
  const idx = parseInt(idxStr, 10);
  const loadBtn = document.getElementById('ls-filters-load-btn');
  const status  = document.getElementById('ls-filters-status');
  if (loadBtn) { loadBtn.disabled = true; loadBtn.textContent = 'Loading…'; }
  try {
    const [tagRes, profileRes] = await Promise.all([
      api('/api/arr/tags?kind=' + kind + '&idx=' + idx),
      api('/api/arr/profiles?kind=' + kind + '&idx=' + idx),
    ]);
    if (!tagRes?.ok || !profileRes?.ok) {
      if (status) status.textContent = 'Load failed — check connectivity';
      if (loadBtn) { loadBtn.disabled = false; loadBtn.textContent = 'Retry'; }
      return;
    }
    const existing = FILTER_STATE[key] || {};
    const savedFilters = CFG?.instances?.[kind]?.[idx]?.sweep_filters || {};
    FILTER_STATE[key] = {
      loaded:           true,
      tags:             tagRes.tags     || [],
      profiles:         profileRes.profiles || [],
      excludedTags:     existing.excludedTags     ?? (savedFilters.excluded_tags    || []),
      excludedProfiles: existing.excludedProfiles ?? (savedFilters.excluded_profiles || []),
    };
    lsFiltersRenderRail();
  } catch(e) {
    if (status) status.textContent = 'Unexpected error';
    if (loadBtn) { loadBtn.disabled = false; loadBtn.textContent = 'Retry'; }
  }
}

// lsFiltersApply — posts the current excludedTags and excludedProfiles
// for the selected instance to /api/config as sweep_filters. Updates CFG
// in place and re-renders the rail to reflect the new filter count.
async function lsFiltersApply() {
  const key = LS_FILTERS_SEL;
  if (!key) return;
  const [kind, idxStr] = key.split('|');
  const idx = parseInt(idxStr, 10);
  const state   = FILTER_STATE[key];
  const status  = document.getElementById('ls-filters-status');
  const applyBtn = document.getElementById('ls-filters-apply');
  if (!state) return;
  if (applyBtn) applyBtn.disabled = true;
  try {
    const cfg = await api('/api/config');
    if (!cfg) { if (status) status.textContent = 'Failed to load config'; if (applyBtn) applyBtn.disabled = false; return; }
    const instances = cfg.instances?.[kind] || [];
    if (idx >= instances.length) { if (status) status.textContent = 'Instance not found'; if (applyBtn) applyBtn.disabled = false; return; }
    instances[idx].sweep_filters = {
      excluded_tags:     state.excludedTags,
      excluded_profiles: state.excludedProfiles,
    };
    const res = await api('/api/config', { method: 'POST', body: JSON.stringify(cfg) });
    if (res?.ok) {
      CFG = cfg;
      if (status) { status.textContent = 'Saved ✓'; setTimeout(() => {
        const total = state.excludedTags.length + state.excludedProfiles.length;
        if (status) status.textContent = total > 0 ? `${total} Filter${total !== 1 ? 's' : ''} Active` : 'No Filters Set';
      }, 2000); }
      lsFiltersRenderRail();
      lsTriggerSave();
    } else {
      if (status) status.textContent = res?.error || 'Save failed';
    }
  } catch(e) {
    if (status) status.textContent = 'Unexpected error';
  } finally {
    if (applyBtn) applyBtn.disabled = false;
  }
}

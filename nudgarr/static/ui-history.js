// ── History tab and Exclusions ───────────────────────────────────────
// Owns: Exclusions state (EXCLUSIONS_DATA, loadExclusions, toggleExclusion,
// refreshAutoExclBadge, onAutoExclBadgeClick, toggleExclusionsFilter),
// History tab (refreshHistory, sortHistory, prevPage, nextPage,
// filterHistorySearch, clearHistorySearch, pruneState, clearState),
// and shared sort helpers (applySortIndicators, sortItems) used by both
// History and Imports tabs.
// Imports tab logic lives in ui-imports.js.
// ── Exclusions ─────────────────────────────────────────────────────────────

// EXCLUSIONS_DATA — full exclusion rows including source, search_count, acknowledged.
// Populated by loadExclusions() so the history table can render source badges.
let EXCLUSIONS_DATA = [];

async function loadExclusions() {
  try {
    const data = await api('/api/exclusions');
    EXCLUSIONS_DATA = data || [];
    EXCLUSIONS_SET = new Set(EXCLUSIONS_DATA.map(e => (e.title || '').toLowerCase()));
    const pill = el('exclusionsPill');
    if (pill) {
      pill.classList.toggle('visible', EXCLUSIONS_SET.size > 0);
      pill.classList.toggle('active', EXCL_FILTER_ACTIVE && EXCLUSIONS_SET.size > 0);
    }
    const hint = el('exclusionsHint');
    if (hint) hint.style.display = EXCLUSIONS_SET.size > 0 ? 'none' : 'block';
    if (EXCLUSIONS_SET.size === 0 && EXCL_FILTER_ACTIVE) {
      EXCL_FILTER_ACTIVE = false;
      PAGE = 0;
    }
    // Update status bar badge with current unacknowledged count
    refreshAutoExclBadge();
  } catch(e) { /* silent */ }
}

// refreshAutoExclBadge — fetches unacknowledged auto-exclusion count and
// updates the status bar badge visibility and number. Badge hidden at 0.
async function refreshAutoExclBadge() {
  try {
    const data = await api('/api/exclusions/unacknowledged-count');
    const count = data?.count ?? 0;
    const seg = el('autoExclBadgeSeg');
    const badge = el('autoExclBadge');
    if (seg) seg.style.display = count > 0 ? '' : 'none';
    if (badge) badge.textContent = count;
  } catch(e) { /* silent */ }
}

// onAutoExclBadgeClick — navigates to the History tab with exclusions filter
// active and acknowledges all auto-exclusions, clearing the badge.
async function onAutoExclBadgeClick() {
  try {
    await api('/api/exclusions/acknowledge', { method: 'POST' });
  } catch(e) { /* silent */ }
  showTab('history');
  EXCL_FILTER_ACTIVE = true;
  PAGE = 0;
  await loadExclusions();
  refreshHistory();
}

async function toggleExclusion(title) {
  const isExcl = EXCLUSIONS_SET.has(title.toLowerCase());
  const endpoint = isExcl ? '/api/exclusions/remove' : '/api/exclusions/add';
  await api(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title }) });
  await loadExclusions();
  refreshHistory();
}

function toggleExclusionsFilter() {
  EXCL_FILTER_ACTIVE = !EXCL_FILTER_ACTIVE;
  const pill = el('exclusionsPill');
  if (pill) pill.classList.toggle('active', EXCL_FILTER_ACTIVE);
  PAGE = 0;
  refreshHistory();
}
// refreshHistory — fetches and renders the History tab in full.
// Responsibilities: rebuilds the instance dropdown (preserving the selected value),
// updates the KPI pill row with per-instance search counts, applies the exclusion
// filter client-side when active (fetches all items and filters locally so excluded
// titles are not constrained to the current page), renders the sortable table,
// and manages pagination visibility and the page-info label.
async function refreshHistory() {
  try {
    const sum = await api('/api/state/summary');

    // KPI pills — per instance counts
    const instPills = ALL_INSTANCES.map(inst => {
      const appSt = sum.per_instance || {};
      const count = (appSt[inst.app] && appSt[inst.app][inst.key]) || 0;
      if (count === 0) return '';
      return `<div class="kpi-card"><span class="kpi-lbl">${escapeHtml(inst.name)}</span><span class="kpi-val">${formatCompact(count)}</span></div>`;
    }).join('');
    el('kpis').innerHTML = instPills;

    // Build instance dropdown from ALL_INSTANCES (has correct app info)
    // Store index into ALL_INSTANCES as the option value to avoid any key parsing issues
    const sel = el('historyInstance');
    const prevIdx = sel.value;
    sel.innerHTML = '<option value="">All Instances</option>' + ALL_INSTANCES.map((inst, idx) =>
      `<option value="${idx}">${escapeHtml(inst.name)}</option>`
    ).join('');
    if (prevIdx && (prevIdx === '' || parseInt(prevIdx) < ALL_INSTANCES.length)) sel.value = prevIdx;

    const selVal = sel.value;
    const selected = selVal !== '' ? ALL_INSTANCES[parseInt(selVal)] : null;
    const instKey = selected ? selected.key : '';
    const appName = selected ? selected.app : '';

    const limit = parseInt(el('historyLimit').value || '10', 10);
    // When exclusion filter is active fetch all items so client-side filter
    // isn't limited to the current page — excluded items may span all pages.
    const fetchLimit = EXCL_FILTER_ACTIVE ? 9999 : limit;
    const fetchOffset = EXCL_FILTER_ACTIVE ? 0 : PAGE * limit;
    const items = await api(`/api/state/items?app=${encodeURIComponent(appName)}&instance=${encodeURIComponent(instKey)}&offset=${fetchOffset}&limit=${fetchLimit}`);

    // Apply exclusion filter client-side when active, then paginate
    if (EXCL_FILTER_ACTIVE) {
      const allExcl = items.items.filter(it => EXCLUSIONS_SET.has((it.title || it.key || '').toLowerCase()));
      const exclTotal = allExcl.length;
      items.items = allExcl.slice(PAGE * limit, (PAGE + 1) * limit);
      items.total = exclTotal;
    }

    el('pageInfo').textContent = EXCL_FILTER_ACTIVE
      ? `Page ${PAGE+1} of ${Math.max(1, Math.ceil(items.total / limit))} · ${formatCompact(items.total)} excluded item${items.total !== 1 ? 's' : ''}`
      : `Page ${PAGE+1} of ${Math.max(1, Math.ceil(items.total / limit))} · ${formatCompact(items.total)} item${items.total !== 1 ? 's' : ''}`;
    HISTORY_TOTAL = items.total;
    el('historyPagination').style.display = items.total > 0 ? 'flex' : 'none';

    const sorted = sortItems(items.items, HISTORY_SORT.col, HISTORY_SORT.dir);
    const showExclFilter = EXCL_FILTER_ACTIVE;
    const rows = sorted.map(it => {
      const title = it.title || it.key;
      const isExcl = EXCLUSIONS_SET.has(title.toLowerCase());
      const rowClass = isExcl && !showExclFilter ? 'row-excluded' : '';
      const exclClass = isExcl ? 'excl-btn excluded' : 'excl-btn';
      const exclTitle = isExcl ? 'Remove from exclusion list' : 'Exclude from future searches';

      // Look up exclusion row for all excluded items — needed for both the
      // source/excluded-on cells (filter mode only) and the eligible again cell.
      const exclRow = isExcl
        ? EXCLUSIONS_DATA.find(e => (e.title || '').toLowerCase() === title.toLowerCase())
        : null;

      // When the exclusion filter is active, build source and excluded-on cells
      let sourceCell = '';
      let excludedOnCell = '';
      if (showExclFilter) {
        if (exclRow) {
          const src = exclRow.source === 'auto' ? 'auto' : 'manual';
          const srcLabel = src === 'auto' ? 'Auto' : 'Manual';
          const countHint = src === 'auto' && exclRow.search_count > 0
            ? ` title="Auto-excluded after ${exclRow.search_count} searches with no confirmed import"` : '';
          sourceCell = `<td><span class="source-badge ${src}"${countHint}>${srcLabel}</span></td>`;
          excludedOnCell = `<td class="td-muted">${escapeHtml(fmtTime(exclRow.excluded_at))}</td>`;
        } else {
          sourceCell = '<td></td>';
          excludedOnCell = '<td></td>';
        }
      }

      // Eligible Again cell:
      // - Not excluded: show cooldown-based date from backend (or Next Sweep)
      // - Manual exclusion: — (stays excluded until manually removed)
      // - Auto-exclusion with unexclude_days = 0: — (stays excluded until manually removed)
      // - Auto-exclusion with unexclude_days > 0: excluded_at + unexclude_days
      let eligibleCell;
      if (!isExcl) {
        eligibleCell = it.eligible_again === 'Next Sweep'
          ? '<span class="eligible-next-sweep">Next Sweep</span>'
          : escapeHtml(fmtTime(it.eligible_again));
      } else if (exclRow && exclRow.source === 'auto' && exclRow.excluded_at) {
        const unexcludeDays = it.app === 'radarr'
          ? (CFG?.auto_unexclude_movies_days ?? 0)
          : (CFG?.auto_unexclude_shows_days ?? 0);
        if (unexcludeDays > 0) {
          const excludedDt = new Date(exclRow.excluded_at);
          excludedDt.setDate(excludedDt.getDate() + unexcludeDays);
          eligibleCell = `<span class="td-blue-dim">${escapeHtml(fmtTime(excludedDt.toISOString()))}</span>`;
        } else {
          eligibleCell = '<span class="td-muted">—</span>';
        }
      } else {
        eligibleCell = '<span class="td-muted">—</span>';
      }
      return `
      <tr class="${rowClass}">
        <td class="arr-link" title="Open in ${it.app === 'radarr' ? 'Radarr' : 'Sonarr'}" onclick="openArrLink('${escapeHtml(it.app)}','${escapeHtml(it.instance_name)}','${escapeHtml(it.item_id)}','${escapeHtml(it.series_id || '')}')">${escapeHtml(title)}</td>
        <td class="excl-col"><button class="${exclClass}" title="${exclTitle}" data-title="${escapeHtml(title)}" onclick="toggleExclusion(this.dataset.title)">\u2298</button></td>
        <td class="td-dim">${escapeHtml(it.instance || '')}</td>
        <td class="td-nowrap">${it.sweep_type ? `<span class="tag${it.sweep_type === 'Backlog' ? ' acquired' : it.sweep_type === 'CF Score' ? ' cf-score' : ''}">${escapeHtml(it.sweep_type)}</span>` : ''}</td>
        <td>${it.search_count > 1 ? `<span class="count-pill">×${it.search_count}</span>` : ''}</td>
        ${sourceCell}
        ${excludedOnCell}
        <td class="td-muted">${escapeHtml(fmtTime(it.library_added))}</td>
        <td class="td-blue">${escapeHtml(fmtTime(it.last_searched))}</td>
        <td>${eligibleCell}</td>
      </tr>
    `}).join('');

    // Source and Excluded On columns only appear when the exclusions filter is active
    const sourceHeader = showExclFilter ? `<th>Source</th><th>Excluded On</th>` : '';
    const colspan = showExclFilter ? '10' : '8';

    el('historyTableWrap').innerHTML = `
      <table>
        <thead><tr>
          <th class="sortable ${HISTORY_SORT.col==='title' ? 'sort-'+HISTORY_SORT.dir : ''}" data-col="title" onclick="sortHistory('title')">Title</th>
          <th class="excl-col"></th>
          <th class="sortable ${HISTORY_SORT.col==='instance' ? 'sort-'+HISTORY_SORT.dir : ''}" data-col="instance" onclick="sortHistory('instance')">Instance</th>
          <th class="sortable ${HISTORY_SORT.col==='sweep_type' ? 'sort-'+HISTORY_SORT.dir : ''}" data-col="sweep_type" onclick="sortHistory('sweep_type')">Type</th>
          <th class="sortable ${HISTORY_SORT.col==='search_count' ? 'sort-'+HISTORY_SORT.dir : ''}" data-col="search_count" onclick="sortHistory('search_count')">Count</th>
          ${sourceHeader}
          <th class="sortable ${HISTORY_SORT.col==='library_added' ? 'sort-'+HISTORY_SORT.dir : ''}" data-col="library_added" onclick="sortHistory('library_added')">Library Added</th>
          <th class="sortable ${HISTORY_SORT.col==='last_searched' ? 'sort-'+HISTORY_SORT.dir : ''}" data-col="last_searched" onclick="sortHistory('last_searched')">Last Searched</th>
          <th class="sortable ${HISTORY_SORT.col==='eligible_again' ? 'sort-'+HISTORY_SORT.dir : ''}" data-col="eligible_again" onclick="sortHistory('eligible_again')">Eligible Again</th>
        </tr></thead>
        <tbody>${rows || `<tr><td colspan="${colspan}" class="help" style="text-align:center;padding:20px">No history yet.</td></tr>`}</tbody>
      </table>
    `;
    applySortIndicators('#historyTableWrap table', HISTORY_SORT);
  } catch(e) {
    el('historyTableWrap').innerHTML = `<p class="help" style="color:var(--bad)">Failed to load history: ${escapeHtml(e.message)}</p>`;
  }
}

function sortHistory(col) {
  if (HISTORY_SORT.col === col) {
    HISTORY_SORT.dir = HISTORY_SORT.dir === 'asc' ? 'desc' : 'asc';
  } else {
    HISTORY_SORT.col = col;
    HISTORY_SORT.dir = 'asc';
  }
  PAGE = 0;
  refreshHistory();
}

function applySortIndicators(tableSelector, sortState) {
  document.querySelectorAll(`${tableSelector} th.sortable`).forEach(th => {
    th.classList.remove('sort-asc', 'sort-desc');
    if (th.dataset.col === sortState.col) {
      th.classList.add(sortState.dir === 'asc' ? 'sort-asc' : 'sort-desc');
    }
  });
}

function sortItems(items, col, dir) {
  return [...items].sort((a, b) => {
    const av = a[col] ?? '';
    const bv = b[col] ?? '';
    if (col === 'search_count') {
      return dir === 'asc' ? (av - bv) : (bv - av);
    }
    const as = av.toString().toLowerCase();
    const bs = bv.toString().toLowerCase();
    return dir === 'asc' ? as.localeCompare(bs) : bs.localeCompare(as);
  });
}

function prevPage() { if (PAGE > 0) { PAGE--; refreshHistory(); } }
function nextPage() {
  const limit = parseInt(el('historyLimit').value || '10', 10);
  if ((PAGE + 1) * limit < HISTORY_TOTAL) { PAGE++; refreshHistory(); }
}
function jumpHistoryPage() {
  const limit = parseInt(el('historyLimit').value || '10', 10);
  const val = parseInt(el('historyPageJump')?.value || '1', 10);
  const maxPage = Math.max(0, Math.ceil(HISTORY_TOTAL / limit) - 1);
  if (!isNaN(val) && val >= 1) { PAGE = Math.min(val - 1, maxPage); refreshHistory(); }
}
// ── History search ──
function filterHistorySearch() {
  const q = el('historySearch').value.trim().toLowerCase();
  el('historySearchClear').style.display = q ? '' : 'none';
  const rows = el('historyTableWrap').querySelectorAll('tbody tr');
  let visible = 0;
  rows.forEach(row => {
    const title = row.cells[0]?.textContent.toLowerCase() || '';
    const show = !q || title.includes(q);
    row.style.display = show ? '' : 'none';
    if (show) visible++;
  });
  const noRes = el('historyNoResults');
  if (noRes) noRes.style.display = (!visible && q) ? '' : 'none';
}

function clearHistorySearch() {
  el('historySearch').value = '';
  el('historySearchClear').style.display = 'none';
  filterHistorySearch();
}

async function pruneState() {
  const days = parseInt(el('state_retention_days')?.value || '0', 10);
  if (days <= 0) {
    showAlert('Pruning is disabled. Set Days to Keep to a value greater than 0 in the Advanced tab to enable it.');
    return;
  }
  if (!await showConfirm('Prune Expired', 'Remove history entries and confirmed imports that have passed your retention window? Unconfirmed items — things still waiting to arrive — are not affected.', 'Prune')) return;
  const out = await api('/api/state/prune', {method:'POST'});
  showAlert(`Pruned ${out.removed} entries.`);
  PAGE = 0; refreshHistory();
}

async function clearState() {
  if (!await showConfirm('Clear History', 'This will permanently delete all search history. Cooldown records will be reset — every item becomes eligible immediately. Consider using Backup All in Support & Diagnostics first.', 'Clear', true)) return;
  await api('/api/state/clear', {method:'POST'});
  PAGE = 0; refreshHistory();
}

// ── Clear Exclusions modal ──────────────────────────────────────────────────
// openClearExclusionsModal  -- shows the modal and resets selection state
// closeClearExclusionsModal -- hides the modal
// selectClearExclOption     -- highlights chosen option and enables Confirm
// confirmClearExclusions    -- calls the appropriate API endpoint and refreshes

let _clearExclSelected = null;

function openClearExclusionsModal() {
  _clearExclSelected = null;
  ['auto', 'manual', 'all'].forEach(k => {
    const opt = el('clearExclOpt' + k.charAt(0).toUpperCase() + k.slice(1));
    const radio = el('clearExclRadio' + k.charAt(0).toUpperCase() + k.slice(1));
    if (opt) {
      opt.style.borderColor = '';
      opt.style.background = 'rgba(255,255,255,.02)';
    }
    if (radio) {
      radio.style.borderColor = '';
      radio.style.background = '';
    }
  });
  const confirmBtn = el('clearExclConfirmBtn');
  if (confirmBtn) confirmBtn.disabled = true;
  const modal = el('clearExclusionsModal');
  if (modal) modal.style.display = 'flex';
}

function closeClearExclusionsModal() {
  const modal = el('clearExclusionsModal');
  if (modal) modal.style.display = 'none';
}

function selectClearExclOption(key) {
  _clearExclSelected = key;
  ['auto', 'manual', 'all'].forEach(k => {
    const cap = k.charAt(0).toUpperCase() + k.slice(1);
    const opt = el('clearExclOpt' + cap);
    const radio = el('clearExclRadio' + cap);
    const active = k === key;
    if (opt) {
      opt.style.borderColor = active ? 'rgba(239,68,68,.38)' : '';
      opt.style.background  = active ? 'rgba(239,68,68,.08)' : 'rgba(255,255,255,.02)';
    }
    if (radio) {
      radio.style.borderColor = active ? 'var(--bad)' : '';
      radio.style.background  = active ? 'var(--bad)' : '';
    }
  });
  const confirmBtn = el('clearExclConfirmBtn');
  if (confirmBtn) confirmBtn.disabled = false;
}

async function confirmClearExclusions() {
  if (!_clearExclSelected) return;
  const endpoints = {
    auto:   '/api/exclusions/clear-auto',
    manual: '/api/exclusions/clear-manual',
    all:    '/api/exclusions/clear-all',
  };
  closeClearExclusionsModal();
  await api(endpoints[_clearExclSelected], {method: 'POST'});
  await loadExclusions();
  refreshAutoExclBadge();
  PAGE = 0;
  refreshHistory();
}

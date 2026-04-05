// ── Imports tab ─────────────────────────────────────────────────────────────
// Owns: Imports tab rendering (refreshImports, sortImports, prevStatsPage,
// nextStatsPage, filterImportsSearch, clearImportsSearch, onImportsPeriodChange,
// checkImportsNow, clearImports) and helpers (buildUpgradeCell, fmtDate).
// Shared sort helpers (applySortIndicators, sortItems) live in ui-history.js
// which loads before this file.
function sortImports(col) {
  if (IMPORTS_SORT.col === col) {
    IMPORTS_SORT.dir = IMPORTS_SORT.dir === 'asc' ? 'desc' : 'asc';
  } else {
    IMPORTS_SORT.col = col;
    IMPORTS_SORT.dir = 'asc';
  }
  IMPORTS_PAGE = 0;
  refreshImports();
}

// ── Stats search ──
function filterImportsSearch() {
  const q = el('importsSearch').value.trim().toLowerCase();
  el('importsSearchClear').style.display = q ? '' : 'none';
  const rows = el('importsTableWrap').querySelectorAll('tbody tr');
  let visible = 0;
  rows.forEach(row => {
    const title = row.cells[0]?.textContent.toLowerCase() || '';
    const show = !q || title.includes(q);
    row.style.display = show ? '' : 'none';
    if (show) visible++;
  });
  const noRes = el('importsNoResults');
  if (noRes) noRes.style.display = (!visible && q) ? '' : 'none';
}

function clearImportsSearch() {
  el('importsSearch').value = '';
  el('importsSearchClear').style.display = 'none';
  filterImportsSearch();
}

// refreshImports — fetches and renders the Stats/Imports tab.
// Rebuilds both the instance dropdown and the type dropdown dynamically from
// available data (preserving prior selections across refreshes), updates the
// lifetime total cards (movies/shows), and renders the sortable paginated table.
function buildUpgradeCell(e) {
  const history = e.quality_history || [];
  if (!history.length) return '';

  const rows = history.map(h => {
    const from = h.quality_from
      ? `<span class="upgrade-from">${escapeHtml(h.quality_from)}</span>`
      : `<span class="upgrade-acquired">Acquired</span>`;
    const to   = `<span class="upgrade-to">${escapeHtml(h.quality_to)}</span>`;
    const date = h.imported_ts ? `<span class="upgrade-date">${escapeHtml(fmtDate(h.imported_ts))}</span>` : '';
    return `<div class="upgrade-row">`
      + `<span class="upgrade-mono">${from}<span class="upgrade-arrow">→</span>${to}</span>`
      + date
      + `</div>`;
  }).join('');

  const header = `<div class="upgrade-header">Upgrade history</div>`;
  const inner  = `<div class="upgrade-inner">${header}${rows}</div>`;

  return `<div class="upgrade-wrap">`
    + `<span class="tooltip-icon upgrade-icon">i`
    + `<div class="tooltip-box tooltip-box-right">${inner}</div>`
    + `</span></div>`;
}

function fmtDate(ts) {
  if (!ts) return '';
  const d = new Date(ts);
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

async function refreshImports() {
  try {
    const inst = el('importsInstance') ? el('importsInstance').value : '';
    const type = el('importsType') ? el('importsType').value : '';
    const limit = parseInt(el('importsLimit')?.value || '10', 10);

    // Restore period select to match the persisted IMPORTS_PERIOD value
    const periodSel = el('importsPeriod');
    if (periodSel && periodSel.value !== IMPORTS_PERIOD) periodSel.value = IMPORTS_PERIOD;

    let url = `/api/stats?offset=${IMPORTS_PAGE * limit}&limit=${limit}&period=${encodeURIComponent(IMPORTS_PERIOD)}`;
    if (inst) url += `&instance=${encodeURIComponent(inst)}`;
    if (type) url += `&type=${encodeURIComponent(type)}`;
    const data = await api(url);

    // Populate instance dropdown
    const sel = el('importsInstance');
    if (sel) {
      const prev = sel.value;
      sel.innerHTML = '<option value="">All Instances</option>' +
        data.instances.map(i => `<option value="${escapeHtml(i.url)}">${escapeHtml(i.name)}</option>`).join('');
      if (prev) sel.value = prev;
    }

    // Populate type dropdown dynamically from available types
    const typeSel = el('importsType');
    if (typeSel) {
      const prevType = typeSel.value;
      typeSel.innerHTML = '<option value="">All Types</option>' +
        (data.types || []).map(t => `<option value="${escapeHtml(t)}">${escapeHtml(t)}</option>`).join('');
      if (prevType && (data.types || []).includes(prevType)) typeSel.value = prevType;
    }

    el('importsPageInfo').textContent = `Page ${IMPORTS_PAGE+1} of ${Math.max(1, Math.ceil(data.total / limit))} · ${formatCompact(data.total)} import${data.total !== 1 ? 's' : ''}`;
    IMPORTS_TOTAL = data.total;
    el('statsPagination').style.display = data.total > 0 ? 'flex' : 'none';

    // Update grand total cards
    el('statMoviesTotal').textContent = formatCompact(data.movies_total ?? 0);
    el('statShowsTotal').textContent = formatCompact(data.shows_total ?? 0);

    if (!data.entries.length && IMPORTS_PAGE === 0) {
      el('importsTableWrap').innerHTML = '<p class="help" style="text-align:center;padding:20px">No confirmed imports yet. Nudgarr will check for imports ' + (CFG?.import_check_minutes || 120) + ' minutes after each search.</p>';
      return;
    }

    const sorted = sortItems(data.entries, IMPORTS_SORT.col, IMPORTS_SORT.dir);
    const rows = sorted.map(e => {
      const countCell = (e.iteration && e.iteration > 1) ? `<span class="imports-iter-pill">×${e.iteration}</span>` : '';
      const tagClass = e.type === 'Acquired' ? 'tag acquired'
        : e.type === 'CF Score' ? 'tag cf-score'
        : 'tag';
      return `
      <tr>
        <td class="arr-link" title="Open in ${e.app === 'radarr' ? 'Radarr' : 'Sonarr'}" onclick="openArrLink('${escapeHtml(e.app)}','${escapeHtml(e.instance)}','${escapeHtml(e.item_id)}','${escapeHtml(e.series_id || '')}')">${escapeHtml(e.title || e.item_id)}</td>
        <!-- NOTE: e.series_id is undefined here — stat_entries has no series_id column.
             The fallback to e.item_id in openArrLink is intentional: sweep.py stores
             the series_id directly as item_id in stat_entries for Sonarr entries.
             Tracked in GitHub: add series_id to stat_entries or document the relationship
             explicitly in get_confirmed_entries. -->
        <td class="td-dim">${escapeHtml(e.instance)}</td>
        <td><span class="${tagClass}">${escapeHtml(e.type)}</span></td>
        <td style="text-align:center">${countCell}</td>
        <td style="text-align:center">${buildUpgradeCell(e)}</td>
        <td class="td-blue">${escapeHtml(fmtTime(e.first_searched_ts))}</td>
        <td class="td-blue-dim">${escapeHtml(fmtTime(e.imported_ts))}</td>
        <td class="td-dim" style="font-size:12px">${escapeHtml(e.turnaround || '—')}</td>
      </tr>
    `}).join('');

    el('importsTableWrap').innerHTML = `
      <table>
        <thead><tr>
          <th class="sortable ${IMPORTS_SORT.col==='title' ? 'sort-'+IMPORTS_SORT.dir : ''}" data-col="title" onclick="sortImports('title')">Title</th>
          <th class="sortable ${IMPORTS_SORT.col==='instance' ? 'sort-'+IMPORTS_SORT.dir : ''}" data-col="instance" onclick="sortImports('instance')">Instance</th>
          <th class="sortable ${IMPORTS_SORT.col==='type' ? 'sort-'+IMPORTS_SORT.dir : ''}" data-col="type" onclick="sortImports('type')">Type</th>
          <th style="text-align:center">Count</th>
          <th style="text-align:center">Upgrade</th>
          <th class="sortable ${IMPORTS_SORT.col==='first_searched_ts' ? 'sort-'+IMPORTS_SORT.dir : ''}" data-col="first_searched_ts" onclick="sortImports('first_searched_ts')">Last Searched</th>
          <th class="sortable ${IMPORTS_SORT.col==='imported_ts' ? 'sort-'+IMPORTS_SORT.dir : ''}" data-col="imported_ts" onclick="sortImports('imported_ts')">Imported</th>
          <th>Turnaround</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
    `;
    applySortIndicators('#importsTableWrap table', IMPORTS_SORT);
  } catch(e) {
    el('importsTableWrap').innerHTML = `<p class="help" style="color:var(--bad)">Failed to load stats: ${escapeHtml(e.message)}</p>`;
  }
}

function prevStatsPage() { if (IMPORTS_PAGE > 0) { IMPORTS_PAGE--; refreshImports(); } }
function nextStatsPage() {
  const limit = parseInt(el('importsLimit')?.value || '10', 10);
  if ((IMPORTS_PAGE + 1) * limit < IMPORTS_TOTAL) { IMPORTS_PAGE++; refreshImports(); }
}
function jumpImportsPage() {
  const limit = parseInt(el('importsLimit')?.value || '10', 10);
  const val = parseInt(el('importsPageJump')?.value || '1', 10);
  const maxPage = Math.max(0, Math.ceil(IMPORTS_TOTAL / limit) - 1);
  if (!isNaN(val) && val >= 1) { IMPORTS_PAGE = Math.min(val - 1, maxPage); refreshImports(); }
}

// onImportsPeriodChange — fired when the user changes the period select on the
// Imports tab stats card. Persists the selection to localStorage so it survives
// page refreshes, resets to page 0, and re-fetches with the new period.
function onImportsPeriodChange() {
  const sel = el('importsPeriod');
  if (!sel) return;
  IMPORTS_PERIOD = sel.value;
  localStorage.setItem('nudgarr_imports_period', IMPORTS_PERIOD);
  IMPORTS_PAGE = 0;
  refreshImports();
}

async function checkImportsNow() {
  try {
    await api('/api/stats/check-imports', {method:'POST'});
    await refreshImports();
  } catch(e) {
    showAlert('Import check failed: ' + e.message);
  }
}

async function clearImports() {
  if (!await showConfirm('Clear Imports', 'This will permanently clear all import records from the Imports tab. Lifetime totals are preserved. Consider using Backup All in Support & Diagnostics first.', 'Clear', true)) return;
  await api('/api/stats/clear', {method:'POST'});
  refreshImports();
}


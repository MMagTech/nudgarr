// ── Sweep tab ──────────────────────────────────────────────────────────────

// Cache last known sweep stats per instance so disabled instances retain their values
const SWEEP_DATA_CACHE = {};
const SWEEP_LIFETIME_CACHE = {};

async function refreshSweep() {
  const status = await api('/api/status');
  const cfg = await api('/api/config');
  const summary = status.last_summary || {};
  const health = status.instance_health || {};
  const lifetime = status.sweep_lifetime || {};
  const instances = cfg.instances || {};
  const legacyMode = cfg.sample_mode || 'random';

  function fmtMode(m) {
    return (m || 'random').split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
  }

  for (const kind of ['radarr', 'sonarr']) {
    const listEl = el('sweep' + kind.charAt(0).toUpperCase() + kind.slice(1) + 'List');
    const insts = instances[kind] || [];
    if (!insts.length) {
      listEl.innerHTML = `<p class="help" style="margin:4px 0">No ${kind} instances configured.</p>`;
      continue;
    }
    const summaryInsts = summary[kind] || [];
    listEl.innerHTML = insts.map(inst => {
      const instKey = `${kind}|${inst.name}`;
      const sk = `${kind}|${inst.name}|${(inst.url || '').replace(/\/+$/, '')}`;
      const dotState = health[instKey] || 'checking';
      const disabled = inst.enabled === false;
      const sw = summaryInsts.find(s => s.name === inst.name);
      const modeKey = kind === 'radarr' ? 'radarr_sample_mode' : 'sonarr_sample_mode';
      const mode = cfg[modeKey] || legacyMode || 'random';

      // Lifetime stats no longer shown on card but last_run_utc still used
      const lk = Object.keys(lifetime).find(k => k.startsWith(`${kind}|${inst.name}|`));
      const lf = lk ? lifetime[lk] : null;
      if (lf?.last_run_utc) SWEEP_LIFETIME_CACHE[`${kind}|${inst.name}`] = lf.last_run_utc;

      // Per-instance last run — disabled instances show their last actual run time
      const lastRun = disabled
        ? (lf?.last_run_utc ? fmtTime(lf.last_run_utc) : '—')
        : (status.last_run_utc ? fmtTime(status.last_run_utc) : '—');

      // Last run stats — use cache if instance absent from this sweep (disabled)
      const cacheKey = `${kind}|${inst.name}`;
      if (sw) {
        // Instance ran this sweep — update cache
        const el_ = (sw.eligible || 0) + (sw.eligible_missing || 0);
        const sr = (sw.searched || 0) + (sw.searched_missing || 0);
        SWEEP_DATA_CACHE[cacheKey] = {
          eligible: el_,
          onCooldown: (sw.skipped_cooldown || 0) + (sw.skipped_missing_cooldown || 0),
          capped: Math.max(0, el_ - sr),
          searched: sr,
          cutoffUnmet: sw.cutoff_unmet_total ?? '—',
          backfill: sw.missing_total ?? '—',
        };
      }
      const cached = SWEEP_DATA_CACHE[cacheKey] || null;
      const eligible = cached ? cached.eligible : null;
      const onCooldown = cached ? cached.onCooldown : null;
      const capped = cached ? cached.capped : null;
      const searched = cached ? cached.searched : null;
      const cutoffUnmet = cached ? cached.cutoffUnmet : null;
      const backfill = cached ? cached.backfill : null;
      const hasData = cached != null;

      const dimStyle = disabled ? 'opacity:0.45;' : '';

      return `
        <div class="inst-card" id="sweepcard-${kind}-${inst.name.replace(/\s+/g,'_')}">
          <div style="${dimStyle}">
            <div class="inst-row1">
              <span class="status-dot ${dotState}" id="sdot-sweep-${instKey}"></span>
              <div class="inst-info">
                <div class="inst-name">${escapeHtml(inst.name)}</div>
                <div style="display:flex;justify-content:space-between;align-items:center;margin-top:2px">
                  <span class="inst-meta">Sweep Mode: ${fmtMode(mode)}</span>
                  <span class="inst-meta" style="font-size:11px;white-space:nowrap;flex-shrink:0">Last Run: ${lastRun}</span>
                </div>
              </div>
            </div>
            <div class="sweep-stats-grid" style="position:relative">
              <div style="grid-column:1/-1;display:flex;align-items:center;justify-content:space-between;padding-bottom:4px">
                <span style="font-size:9px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#6378ff">Library State</span>
                ${disabled ? '<span style="font-size:10px;padding:2px 7px;background:rgba(99,120,255,.15);color:#6378ff;border:1px solid rgba(99,120,255,.3);border-radius:4px;font-weight:600;letter-spacing:.04em;opacity:1">Disabled</span>' : ''}
              </div>
              <div class="sweep-stat">
                <span class="sweep-stat-label">Cutoff Unmet</span>
                <span class="sweep-stat-value ${hasData ? '' : 'dim'}">${hasData ? cutoffUnmet : '—'}</span>
              </div>
              <div class="sweep-stat">
                <span class="sweep-stat-label">Backfill</span>
                <span class="sweep-stat-value ${hasData ? '' : 'dim'}">${hasData ? backfill : '—'}</span>
              </div>
              <hr class="sweep-row-divider">
              <span style="grid-column:1/-1;font-size:9px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#6378ff;padding-bottom:4px;padding-top:2px">This Run</span>
              <div class="sweep-stat">
                <span class="sweep-stat-label">Eligible</span>
                <span class="sweep-stat-value ${hasData ? '' : 'dim'}">${hasData ? eligible : '—'}</span>
              </div>
              <div class="sweep-stat">
                <span class="sweep-stat-label">On Cooldown</span>
                <span class="sweep-stat-value ${hasData ? '' : 'dim'}">${hasData ? onCooldown : '—'}</span>
              </div>
              <hr class="sweep-row-divider">
              <div class="sweep-stat">
                <span class="sweep-stat-label">Capped</span>
                <span class="sweep-stat-value ${hasData ? '' : 'dim'}">${hasData ? capped : '—'}</span>
              </div>
              <div class="sweep-stat">
                <span class="sweep-stat-label">Searched</span>
                <span class="sweep-stat-value ${hasData ? '' : 'dim'}">${hasData ? searched : '—'}</span>
              </div>
            </div>
          </div>
        </div>`;
    }).join('');
  }
}
function showSweepNoInstancesModal() {
  el('sweepNoInstancesModal').style.display = 'flex';
}

// ── Exclusions ─────────────────────────────────────────────────────────────

async function loadExclusions() {
  try {
    const data = await api('/api/exclusions');
    EXCLUSIONS_SET = new Set((data || []).map(e => (e.title || '').toLowerCase()));
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
  } catch(e) { /* silent */ }
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
async function refreshHistory() {
  try {
    const sum = await api('/api/state/summary');

    // KPI pills — per instance counts
    const instPills = ALL_INSTANCES.map(inst => {
      const appSt = sum.per_instance || {};
      const count = (appSt[inst.app] && appSt[inst.app][inst.key]) || 0;
      if (count === 0) return '';
      return `<div class="pill"><span style="color:var(--text-dim);font-size:11px">${escapeHtml(inst.name)}:</span><span style="color:var(--text);font-weight:400;font-size:13px">${count}</span></div>`;
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

    const limit = parseInt(el('historyLimit').value || '25', 10);
    // When exclusion filter is active fetch all items so client-side filter
    // isn't limited to the current page — excluded items may span all pages.
    const fetchLimit = EXCL_FILTER_ACTIVE ? 9999 : limit;
    const fetchOffset = EXCL_FILTER_ACTIVE ? 0 : PAGE * limit;
    const items = await api(`/api/state/items?app=${encodeURIComponent(appName)}&instance=${encodeURIComponent(instKey)}&offset=${fetchOffset}&limit=${fetchLimit}`);

    // Apply exclusion filter client-side when active
    if (EXCL_FILTER_ACTIVE) {
      items.items = items.items.filter(it => EXCLUSIONS_SET.has((it.title || it.key || '').toLowerCase()));
      items.total = items.items.length;
    }

    el('pageInfo').textContent = EXCL_FILTER_ACTIVE
      ? `${items.items.length} excluded item${items.items.length !== 1 ? 's' : ''}`
      : `Page ${PAGE+1} of ${Math.max(1, Math.ceil(items.total / limit))} · ${items.total} item${items.total !== 1 ? 's' : ''}`;
    HISTORY_TOTAL = items.total;
    el('historyPagination').style.display = (!EXCL_FILTER_ACTIVE && items.total > 0) ? 'flex' : 'none';

    const sorted = sortItems(items.items, HISTORY_SORT.col, HISTORY_SORT.dir);
    const showExclFilter = EXCL_FILTER_ACTIVE;
    const rows = sorted.map(it => {
      const title = it.title || it.key;
      const isExcl = EXCLUSIONS_SET.has(title.toLowerCase());
      const rowClass = isExcl && !showExclFilter ? 'row-excluded' : '';
      const exclClass = isExcl ? 'excl-btn excluded' : 'excl-btn';
      const exclTitle = isExcl ? 'Remove from exclusion list' : 'Exclude from future searches';
      return `
      <tr class="${rowClass}">
        <td style="color:var(--text);font-weight:500" class="arr-link" title="Open in ${it.app === 'radarr' ? 'Radarr' : 'Sonarr'}" onclick="openArrLink('${escapeHtml(it.app)}','${escapeHtml(it.instance_name)}','${escapeHtml(it.item_id)}','${escapeHtml(it.series_id || '')}')">${escapeHtml(title)}</td>
        <td class="excl-col"><button class="${exclClass}" title="${exclTitle}" data-title="${escapeHtml(title)}" onclick="toggleExclusion(this.dataset.title)">\u2298</button></td>
        <td style="color:var(--text-dim)">${escapeHtml(it.instance || '')}</td>
        <td style="white-space:nowrap">${it.sweep_type ? `<span class="tag${it.sweep_type === 'Backlog' ? ' acquired' : ''}">${escapeHtml(it.sweep_type)}</span>` : ''}</td>
        <td>${it.search_count > 1 ? `<span class="pill" style="font-size:11px;padding:2px 8px;background:rgba(99,120,255,.15);color:#8899ff">×${it.search_count}</span>` : ''}</td>
        <td style="color:var(--muted)">${escapeHtml(fmtTime(it.library_added))}</td>
        <td style="color:#b0bcf0">${escapeHtml(fmtTime(it.last_searched))}</td>
        <td style="color:rgba(176,188,240,.6)">${escapeHtml(fmtTime(it.eligible_again))}</td>
      </tr>
    `}).join('');

    el('historyTableWrap').innerHTML = `
      <table>
        <thead><tr>
          <th class="sortable ${HISTORY_SORT.col==='title' ? 'sort-'+HISTORY_SORT.dir : ''}" data-col="title" onclick="sortHistory('title')">Title</th>
          <th class="excl-col"></th>
          <th class="sortable ${HISTORY_SORT.col==='instance' ? 'sort-'+HISTORY_SORT.dir : ''}" data-col="instance" onclick="sortHistory('instance')">Instance</th>
          <th class="sortable ${HISTORY_SORT.col==='sweep_type' ? 'sort-'+HISTORY_SORT.dir : ''}" data-col="sweep_type" onclick="sortHistory('sweep_type')">Type</th>
          <th class="sortable ${HISTORY_SORT.col==='search_count' ? 'sort-'+HISTORY_SORT.dir : ''}" data-col="search_count" onclick="sortHistory('search_count')">Count</th>
          <th class="sortable ${HISTORY_SORT.col==='library_added' ? 'sort-'+HISTORY_SORT.dir : ''}" data-col="library_added" onclick="sortHistory('library_added')">Library Added</th>
          <th class="sortable ${HISTORY_SORT.col==='last_searched' ? 'sort-'+HISTORY_SORT.dir : ''}" data-col="last_searched" onclick="sortHistory('last_searched')">Last Searched</th>
          <th class="sortable ${HISTORY_SORT.col==='eligible_again' ? 'sort-'+HISTORY_SORT.dir : ''}" data-col="eligible_again" onclick="sortHistory('eligible_again')">Eligible Again</th>
        </tr></thead>
        <tbody>${rows || '<tr><td colspan="8" class="help" style="text-align:center;padding:20px">No history yet.</td></tr>'}</tbody>
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
  const limit = parseInt(el('historyLimit').value || '25', 10);
  if ((PAGE + 1) * limit < HISTORY_TOTAL) { PAGE++; refreshHistory(); }
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

// ── Stats tab ──
async function refreshImports() {
  try {
    const inst = el('importsInstance') ? el('importsInstance').value : '';
    const type = el('importsType') ? el('importsType').value : '';
    const limit = parseInt(el('importsLimit')?.value || '25', 10);
    let url = `/api/stats?offset=${IMPORTS_PAGE * limit}&limit=${limit}`;
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

    el('importsPageInfo').textContent = `Page ${IMPORTS_PAGE+1} of ${Math.max(1, Math.ceil(data.total / limit))} · ${data.total} import${data.total !== 1 ? 's' : ''}`;
    IMPORTS_TOTAL = data.total;
    el('statsPagination').style.display = data.total > 0 ? 'flex' : 'none';

    // Update grand total cards
    el('statMoviesTotal').textContent = data.movies_total ?? 0;
    el('statShowsTotal').textContent = data.shows_total ?? 0;

    if (!data.entries.length && IMPORTS_PAGE === 0) {
      el('importsTableWrap').innerHTML = '<p class="help" style="text-align:center;padding:20px">No confirmed imports yet. Nudgarr will check for imports ' + (CFG?.import_check_minutes || 120) + ' minutes after each search.</p>';
      return;
    }

    const sorted = sortItems(data.entries, IMPORTS_SORT.col, IMPORTS_SORT.dir);
    const rows = sorted.map(e => {
      const iterSuffix = (e.iteration && e.iteration > 1) ? ` ×${e.iteration}` : '';
      const tagClass = e.type === 'Acquired' ? 'tag acquired' : 'tag';
      return `
      <tr>
        <td style="color:var(--text);font-weight:500" class="arr-link" title="Open in ${e.app === 'radarr' ? 'Radarr' : 'Sonarr'}" onclick="openArrLink('${escapeHtml(e.app)}','${escapeHtml(e.instance)}','${escapeHtml(e.item_id)}','${escapeHtml(e.series_id || '')}')">${escapeHtml(e.title || e.item_id)}</td>
        <td style="color:var(--text-dim)">${escapeHtml(e.instance)}</td>
        <td><span class="${tagClass}">${escapeHtml(e.type)}${escapeHtml(iterSuffix)}</span></td>
        <td style="color:#b0bcf0">${escapeHtml(fmtTime(e.first_searched_ts))}</td>
        <td style="color:rgba(176,188,240,.6)">${escapeHtml(fmtTime(e.imported_ts))}</td>
        <td style="color:var(--text-dim);font-size:12px">${escapeHtml(e.turnaround || '—')}</td>
      </tr>
    `}).join('');

    el('importsTableWrap').innerHTML = `
      <table>
        <thead><tr>
          <th class="sortable ${IMPORTS_SORT.col==='title' ? 'sort-'+IMPORTS_SORT.dir : ''}" data-col="title" onclick="sortImports('title')">Title</th>
          <th class="sortable ${IMPORTS_SORT.col==='instance' ? 'sort-'+IMPORTS_SORT.dir : ''}" data-col="instance" onclick="sortImports('instance')">Instance</th>
          <th class="sortable ${IMPORTS_SORT.col==='type' ? 'sort-'+IMPORTS_SORT.dir : ''}" data-col="type" onclick="sortImports('type')">Type</th>
          <th class="sortable ${IMPORTS_SORT.col==='first_searched_ts' ? 'sort-'+IMPORTS_SORT.dir : ''}" data-col="first_searched_ts" onclick="sortImports('first_searched_ts')">Last Searched</th>
          <th class="sortable ${IMPORTS_SORT.col==='imported_ts' ? 'sort-'+IMPORTS_SORT.dir : ''}" data-col="imported_ts" onclick="sortImports('imported_ts')">Imported</th>
          <th>Turnaround <span class="tooltip-icon tip-down">i<div class="tooltip-box">Time from when Nudgarr first searched this item to when it was confirmed imported. Resets if the item is imported again at a higher quality.</div></span></th>
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
  const limit = parseInt(el('importsLimit')?.value || '25', 10);
  if ((IMPORTS_PAGE + 1) * limit < IMPORTS_TOTAL) { IMPORTS_PAGE++; refreshImports(); }
}

async function checkImportsNow() {
  try {
    await api('/api/stats/check-imports', {method:'POST'});
    await refreshImports();
  } catch(e) {
    console.error('Import check failed:', e);
  }
}

async function clearStats() {
  if (!await showConfirm('Clear Stats', 'This will permanently clear all import records from the Stats tab. Lifetime totals are preserved. Consider using Backup All in Support & Diagnostics first.', 'Clear', true)) return;
  await api('/api/stats/clear', {method:'POST'});
  refreshImports();
}

// ── Advanced tab ──
// ── Notifications tab ──
// ── Run Now ──
async function runNow() {
  try {
    await api('/api/run-now', {method:'POST'});
    el('lastRun').textContent = 'Running…';
    el('dot-scheduler').classList.add('running');
    const wm = el('wordmark');
    wm.classList.add('sweeping');
    wm._pendingStop = false;
  } catch(e) {
    showAlert('Run request failed: ' + e.message);
  }
}

// ── Arr link ──

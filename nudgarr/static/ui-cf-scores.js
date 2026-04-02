// ── CF Score tab ───────────────────────────────────────────────────────────────
// Owns: CF Score tab rendering (fillCfScores, cfRenderCoverage, cfRenderTable),
// config fields (saveCfScores), manual scan (cfScanLibrary), index reset
// (cfResetIndex), app filter buttons (cfFilterEntries), and pagination
// (cfPrevPage, cfNextPage).
//
// fillCfScores() is the main entry point called by _onTabShown('cf-scores').

let CF_FILTER = 'all';
let CF_FILTER_INSTANCE_ID = '';
let CF_PAGE = 0;
let CF_PAGE_SIZE = 10;
let CF_TOTAL = 0;
let _cfScanPolling = false; // prevents duplicate _cfWaitForScan loops


// ── fillCfScores ───────────────────────────────────────────────────────────────
async function fillCfScores() {
  try {
    const entriesUrl = CF_FILTER_INSTANCE_ID
      ? '/api/cf-scores/entries?instance_id=' + encodeURIComponent(CF_FILTER_INSTANCE_ID)
      : '/api/cf-scores/entries';
    const [status, entries] = await Promise.all([
      api('/api/cf-scores/status'),
      api(entriesUrl),
    ]);
    cfRenderCoverage(status);
    cfPopulateInstanceDropdown(status);
    cfRenderTable(entries);
    cfSyncConfigFields();

    // If a scan is already running (e.g. triggered from the filter sync popup or
    // the background scheduler) and we are not already polling, start the wait
    // loop so progress rings update automatically without needing to leave the tab.
    if (status?.scan_in_progress && !_cfScanPolling) {
      _cfScanPolling = true;
      _cfWaitForScan().finally(() => {
        _cfScanPolling = false;
        fillCfScores();
      });
    }
  } catch(e) {
    console.error('[CF Score] fillCfScores failed:', e.message);
  }
}


// ── cfPopulateInstanceDropdown ─────────────────────────────────────────────────
// Populate the instance filter dropdown from status data.
function cfPopulateInstanceDropdown(status) {
  const sel = el('cfInstanceFilter');
  if (!sel) return;
  const instances = status?.instances || [];
  const current = sel.value;
  sel.innerHTML = '<option value="">All Instances</option>' +
    instances.map(i =>
      `<option value="${escapeHtml(i.arr_instance_id)}"${i.arr_instance_id === current ? ' selected' : ''}>${escapeHtml(i.instance_name || i.arr_instance_id)}</option>`
    ).join('');
}


// ── cfFilterSearch ─────────────────────────────────────────────────────────────
let CF_SEARCH_TERM = '';

function cfFilterSearch() {
  const inp = el('cfSearch');
  const clearBtn = el('cfSearchClear');
  CF_SEARCH_TERM = (inp?.value || '').toLowerCase();
  if (clearBtn) clearBtn.style.display = CF_SEARCH_TERM ? '' : 'none';
  CF_PAGE = 0;
  _cfRenderPage();
}

function cfClearSearch() {
  const inp = el('cfSearch');
  if (inp) inp.value = '';
  const clearBtn = el('cfSearchClear');
  if (clearBtn) clearBtn.style.display = 'none';
  CF_SEARCH_TERM = '';
  CF_PAGE = 0;
  _cfRenderPage();
}


// ── jumpCfPage ─────────────────────────────────────────────────────────────────
function jumpCfPage() {
  CF_PAGE_SIZE = parseInt(el('cfPageSize')?.value || '10', 10);
  const val = parseInt(el('cfPageJump')?.value || '1', 10);
  const totalPages = Math.max(1, Math.ceil(CF_TOTAL / CF_PAGE_SIZE));
  if (!isNaN(val) && val >= 1) { CF_PAGE = Math.min(val - 1, totalPages - 1); _cfRenderPage(); }
}

function cfChangePageSize() {
  CF_PAGE_SIZE = parseInt(el('cfPageSize')?.value || '10', 10);
  CF_PAGE = 0;
  _cfRenderPage();
}


// ── cfFilterEntries ────────────────────────────────────────────────────────────
async function cfFilterEntries(instanceId) {
  CF_FILTER_INSTANCE_ID = instanceId || '';
  CF_FILTER = instanceId ? 'instance' : 'all';
  CF_PAGE = 0;
  try {
    const url = CF_FILTER_INSTANCE_ID
      ? '/api/cf-scores/entries?instance_id=' + encodeURIComponent(CF_FILTER_INSTANCE_ID)
      : '/api/cf-scores/entries';
    const data = await api(url);
    cfRenderTable(data);
  } catch(e) {
    console.error('[CF Score] cfFilterEntries failed:', e.message);
  }
}


// ── cfRenderCoverage ───────────────────────────────────────────────────────────
// Flat list: instance name, app badge, inline percentage pill, file counts.
// Scrollable via CSS on the container. Sync progress from sync_progress field.
function cfRenderCoverage(status) {
  const wrap = el('cfCoverageList');
  if (!wrap) return;

  const instances = status?.instances || [];
  const lastSyncedDot  = el('cfLastSyncedDot');
  const lastSyncedText = el('cfLastSyncedText');
  const nextSyncText   = el('cfNextSyncText');

  // Populate Last Synced from global status field (persisted to DB)
  const globalLastSync = status?.last_sync_at;
  if (lastSyncedDot) lastSyncedDot.style.background = globalLastSync ? 'var(--ok)' : 'var(--muted)';
  if (lastSyncedText) {
    lastSyncedText.textContent = globalLastSync
      ? 'Last Synced ' + fmtTime(globalLastSync)
      : 'Never synced';
  }

  // Populate Next Sync
  if (nextSyncText) {
    const nextSync = status?.next_sync_at;
    nextSyncText.textContent = nextSync
      ? 'Next Sync ' + fmtTime(nextSync)
      : 'Next sync: —';
  }

  if (!instances.length) {
    wrap.innerHTML = '<p class="help">No instances synced yet. Run Scan Library to build the index.</p>';
    return;
  }

  wrap.innerHTML = instances.map((inst, idx) => {
    const app = (inst.app || 'radarr').toLowerCase();
    const isRadarr = app === 'radarr';
    const total = inst.total_indexed || 0;
    const below = inst.below_cutoff || 0;

    const prog = inst.sync_progress;
    let pctLabel = '—';
    // Pill color: blue = in progress, green = 100% complete, muted = never synced
    let pillColor = 'color:var(--muted);background:transparent;border-color:var(--border);';

    if (prog && prog.in_progress) {
      const pct = prog.total > 0 ? Math.min(99, Math.round((prog.processed / prog.total) * 100)) : 0;
      pctLabel = pct + '%';
      pillColor = 'color:var(--accent-lt);background:var(--accent-dim);border-color:var(--accent-border);';
    } else if (prog && prog.total > 0) {
      pctLabel = '100%';
      pillColor = 'color:var(--ok);background:rgba(34,197,94,.08);border-color:rgba(34,197,94,.25);';
    } else if (total > 0) {
      pctLabel = '100%';
      pillColor = 'color:var(--ok);background:rgba(34,197,94,.08);border-color:rgba(34,197,94,.25);';
    }

    const isLast = idx === instances.length - 1;
    return `<div style="display:flex;align-items:center;justify-content:space-between;padding:9px 0;${isLast ? '' : 'border-bottom:1px solid var(--border);'}">
      <div>
        <div style="font-size:12.5px;font-weight:600;color:var(--text);display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
          ${escapeHtml(inst.instance_name || inst.arr_instance_id)}
          <span style="font-size:12px;font-weight:700;border-radius:6px;padding:1px 7px;border:1px solid;${pillColor}">${pctLabel}</span>
        </div>
        <div style="font-size:11px;color:var(--muted);margin-top:2px;">${total.toLocaleString()} indexed · ${below.toLocaleString()} below cutoff</div>
      </div>
    </div>`;
  }).join('');
}


// ── cfRenderTable ──────────────────────────────────────────────────────────────
// Sortable columns matching History tab pattern. App column removed.
// Pagination via cfPrevPage/cfNextPage.
let CF_SORT = { col: 'gap', dir: 'desc' };
let CF_ALL_ENTRIES = [];

function cfRenderTable(data) {
  const wrap = el('cfEntriesWrap');
  const pagination = el('cfPagination');
  if (!wrap) return;

  // Sync filter button states
  document.querySelectorAll('#cfFilterBtns button').forEach(b => {
    const label = b.textContent.trim().toLowerCase();
    const isActive = (CF_FILTER === 'all' && label === 'all') ||
                     (CF_FILTER === 'radarr' && label === 'radarr') ||
                     (CF_FILTER === 'sonarr' && label === 'sonarr');
    b.className = 'btn sm' + (isActive ? ' primary' : '');
  });

  CF_ALL_ENTRIES = data?.entries || [];
  CF_TOTAL = CF_ALL_ENTRIES.length;

  if (!CF_ALL_ENTRIES.length) {
    wrap.innerHTML = '<p class="help" style="padding:12px 0;">No items below CF cutoff' +
      (CF_FILTER !== 'all' ? ' for the selected filter' : '') + '.</p>';
    if (pagination) pagination.style.display = 'none';
    return;
  }

  if (pagination) pagination.style.display = '';
  _cfRenderPage();
}

function _cfRenderPage() {
  const wrap = el('cfEntriesWrap');
  const pageInfo = el('cfPageInfo');
  if (!wrap) return;

  CF_PAGE_SIZE = parseInt(el('cfPageSize')?.value || '10', 10);

  // Apply client-side search filter
  const searchFiltered = CF_SEARCH_TERM
    ? CF_ALL_ENTRIES.filter(e => (e.title || '').toLowerCase().includes(CF_SEARCH_TERM))
    : CF_ALL_ENTRIES;

  const sorted = [...searchFiltered].sort((a, b) => {
    const col = CF_SORT.col;
    const av = col === 'gap' ? (a.gap ?? a.cutoff_score - a.current_score)
             : col === 'current_score' ? a.current_score
             : col === 'cutoff_score' ? a.cutoff_score
             : (a[col] || '');
    const bv = col === 'gap' ? (b.gap ?? b.cutoff_score - b.current_score)
             : col === 'current_score' ? b.current_score
             : col === 'cutoff_score' ? b.cutoff_score
             : (b[col] || '');
    if (typeof av === 'string') return CF_SORT.dir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
    return CF_SORT.dir === 'asc' ? av - bv : bv - av;
  });

  const total = sorted.length;
  const start = CF_PAGE * CF_PAGE_SIZE;
  const slice = sorted.slice(start, start + CF_PAGE_SIZE);
  const maxGap = Math.max(...searchFiltered.map(e => e.gap ?? e.cutoff_score - e.current_score), 1);

  const sortTh = (col, label) => {
    const active = CF_SORT.col === col;
    const cls = active ? (CF_SORT.dir === 'asc' ? 'sort-asc' : 'sort-desc') : '';
    return `<th class="sortable ${cls}" onclick="cfSortTable('${col}')">${label}</th>`;
  };

  if (!slice.length) {
    wrap.innerHTML = '<p class="help" style="padding:12px 0;">No items match your search.</p>';
    if (pageInfo) pageInfo.textContent = '';
    const btnPrev = el('cfPagination')?.querySelector('button:first-child');
    const btnNext = el('cfPagination')?.querySelector('button:nth-child(2)');
    if (btnPrev) btnPrev.disabled = true;
    if (btnNext) btnNext.disabled = true;
    return;
  }

  const rows = slice.map(e => {
    const gap = e.gap ?? (e.cutoff_score - e.current_score);
    const barPct = Math.min(100, Math.round((Math.abs(gap) / maxGap) * 100));
    const app = e.arr_instance_id ? e.arr_instance_id.split('|')[0] : 'radarr';
    const itemId = e.external_item_id || '';
    const seriesId = e.series_id || '';
    return `<tr>
      <td class="arr-link" style="font-size:12.5px;" title="Open in ${app === 'radarr' ? 'Radarr' : 'Sonarr'}" onclick="openArrLink('${escapeHtml(app)}','${escapeHtml(e.instance_name || '')}','${itemId}','${seriesId}')">${escapeHtml(e.title || '—')}</td>
      <td style="font-size:12px;color:var(--text-dim);">${escapeHtml(e.instance_name || '—')}</td>
      <td style="font-size:12px;color:var(--text-dim);">${escapeHtml(e.quality_profile_name || '—')}</td>
      <td style="font-family:'JetBrains Mono',ui-monospace,monospace;color:var(--bad);font-weight:600;">${e.current_score}</td>
      <td style="font-family:'JetBrains Mono',ui-monospace,monospace;color:var(--text-dim);">${e.cutoff_score}</td>
      <td style="font-family:'JetBrains Mono',ui-monospace,monospace;color:var(--warn);font-weight:600;">
        ${gap}
        <span style="display:inline-block;width:50px;height:3px;background:rgba(255,255,255,.06);border-radius:2px;overflow:hidden;vertical-align:middle;margin-left:5px;">
          <span style="display:block;height:100%;border-radius:2px;background:var(--warn);width:${barPct}%;"></span>
        </span>
      </td>
    </tr>`;
  }).join('');

  wrap.innerHTML = `<div style="overflow-x:auto;">
    <table class="cf-table">
      <thead><tr>
        ${sortTh('title','Title')}
        ${sortTh('instance_name','Instance')}
        ${sortTh('quality_profile_name','Profile')}
        ${sortTh('current_score','Current Score')}
        ${sortTh('cutoff_score','Cutoff Score')}
        ${sortTh('gap','Gap')}
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>
  </div>`;

  const end = Math.min(start + CF_PAGE_SIZE, total);
  const totalPages = Math.max(1, Math.ceil(total / CF_PAGE_SIZE));
  if (pageInfo) pageInfo.textContent = `Page ${CF_PAGE + 1} of ${totalPages} · ${total} item${total !== 1 ? 's' : ''}`;

  const btnPrev = el('cfPagination')?.querySelector('button:first-child');
  const btnNext = el('cfPagination')?.querySelector('button:nth-child(2)');
  if (btnPrev) btnPrev.disabled = CF_PAGE === 0;
  if (btnNext) btnNext.disabled = end >= total;

  const jumpInput = el('cfPageJump');
  if (jumpInput) jumpInput.max = totalPages;
}

function cfSortTable(col) {
  if (CF_SORT.col === col) {
    CF_SORT.dir = CF_SORT.dir === 'asc' ? 'desc' : 'asc';
  } else {
    CF_SORT.col = col;
    CF_SORT.dir = col === 'gap' || col === 'current_score' || col === 'cutoff_score' ? 'desc' : 'asc';
  }
  CF_PAGE = 0;
  _cfRenderPage();
}

function cfPrevPage() { if (CF_PAGE > 0) { CF_PAGE--; _cfRenderPage(); } }
function cfNextPage() { if ((CF_PAGE + 1) * CF_PAGE_SIZE < CF_TOTAL) { CF_PAGE++; _cfRenderPage(); } }


// ── cfSyncConfigFields ─────────────────────────────────────────────────────────
function cfSyncConfigFields() {
  if (!CFG) return;
  const cronInput = el('cfSyncCron');
  const rMax = el('cfRadarrMax');
  const sMax = el('cfSonarrMax');
  if (cronInput) {
    cronInput.value = CFG.cf_score_sync_cron ?? '0 0 * * *';
    validateCfCronExpr();
  }
  if (rMax) rMax.value = CFG.radarr_cf_max_per_run ?? 1;
  if (sMax) sMax.value = CFG.sonarr_cf_max_per_run ?? 1;
  const msg = el('cfMsg');
  if (msg) { msg.textContent = ''; msg.className = 'msg'; }
}


// ── saveCfScores ───────────────────────────────────────────────────────────────
async function saveCfScores() {
  if (!CFG) return;
  try {
    const cronVal = (el('cfSyncCron')?.value || '0 0 * * *').trim();
    const rMaxVal  = parseInt(el('cfRadarrMax')?.value || '1', 10);
    const sMaxVal  = parseInt(el('cfSonarrMax')?.value || '1', 10);
    const cronParts = cronVal.split(/\s+/);
    CFG.cf_score_sync_cron     = cronParts.length === 5 ? cronVal : '0 0 * * *';
    CFG.radarr_cf_max_per_run  = isNaN(rMaxVal)  || rMaxVal  < 1 ? 1  : rMaxVal;
    CFG.sonarr_cf_max_per_run  = isNaN(sMaxVal)  || sMaxVal  < 1 ? 1  : sMaxVal;
    await api('/api/config', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(CFG),
    });
    el('cfMsg').textContent = 'Saved';
    el('cfMsg').className = 'msg ok';
    fadeMsg('cfMsg');
  } catch(e) {
    el('cfMsg').textContent = 'Save failed: ' + e.message;
    el('cfMsg').className = 'msg err';
  }
}


// ── cfScanLibrary ──────────────────────────────────────────────────────────────
async function cfScanLibrary() {
  const btn = el('cfScanBtn');
  if (btn) { btn.disabled = true; btn.textContent = 'Scanning…'; }
  try {
    const result = await api('/api/cf-scores/scan', {method: 'POST'});
    if (result?.ok) {
      _cfScanPolling = true;
      await _cfWaitForScan();
      _cfScanPolling = false;
      await fillCfScores();
    } else {
      showAlert(result?.error || 'Scan could not be started.');
    }
  } catch(e) {
    showAlert('Scan failed: ' + e.message);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Scan Library'; }
  }
}


// ── _cfWaitForScan ─────────────────────────────────────────────────────────────
async function _cfWaitForScan() {
  const maxAttempts = 150;
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise(r => setTimeout(r, 2000));
    try {
      const status = await api('/api/cf-scores/status');
      cfRenderCoverage(status);
      if (!status?.scan_in_progress) return;
    } catch(e) {
      return;
    }
  }
}


// ── validateCfCronExpr ─────────────────────────────────────────────────────────
// Validates the CF cron expression input and updates the hint line.
// Mirrors the sweep scheduler's validateCronExpr pattern.
function validateCfCronExpr() {
  const input = el('cfSyncCron');
  const hint  = el('cfCronHintLine');
  if (!input || !hint) return;
  const val = input.value.trim();
  const parts = val.split(/\s+/);
  if (parts.length !== 5) {
    hint.textContent = 'Must be a valid 5-field cron expression';
    hint.style.color = 'var(--bad)';
    return;
  }
  // Produce a human-readable description for common patterns
  const [min, hr, dom, mon, dow] = parts;
  let desc = '';
  if (min === '0' && hr === '0' && dom === '*' && mon === '*' && dow === '*') {
    desc = 'Every day at midnight';
  } else if (min === '0' && dom === '*' && mon === '*' && dow === '*') {
    if (hr === '*') desc = 'Every hour';
    else if (hr.startsWith('*/')) desc = `Every ${hr.slice(2)} hours`;
    else desc = `Every day at ${hr.padStart(2,'0')}:00`;
  } else if (min.startsWith('*/') && hr === '*') {
    desc = `Every ${min.slice(2)} minutes`;
  } else {
    desc = 'Custom schedule';
  }
  hint.textContent = desc;
  hint.style.color = 'var(--ok)';
}
async function cfResetIndex() {
  if (!await showConfirm(
    'Reset CF Score Index',
    'This will clear the entire CF score index. The next Scan Library run will rebuild it from scratch.',
    'Reset',
    true
  )) return;
  try {
    await api('/api/cf-scores/reset', {method: 'POST'});
    await fillCfScores();
  } catch(e) {
    showAlert('Reset failed: ' + e.message);
  }
}


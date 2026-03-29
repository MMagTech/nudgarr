// ── CF Score tab ───────────────────────────────────────────────────────────────
// Owns: CF Score tab rendering (fillCfScores, cfRenderCoverage, cfRenderTable),
// config fields (saveCfScores), manual scan (cfScanLibrary), index reset
// (cfResetIndex), app filter buttons (cfFilterEntries), and pagination
// (cfPrevPage, cfNextPage).
//
// fillCfScores() is the main entry point called by _onTabShown('cf-scores').

let CF_FILTER = 'all';
let CF_PAGE = 0;
const CF_PAGE_SIZE = 25;
let CF_TOTAL = 0;


// ── fillCfScores ───────────────────────────────────────────────────────────────
async function fillCfScores() {
  try {
    const [status, entries] = await Promise.all([
      api('/api/cf-scores/status'),
      api('/api/cf-scores/entries' + (CF_FILTER !== 'all' ? '?app=' + CF_FILTER : '')),
    ]);
    cfRenderStats(status);
    cfRenderCoverage(status);
    cfRenderTable(entries);
    cfSyncConfigFields();
  } catch(e) {
    console.error('[CF Score] fillCfScores failed:', e.message);
  }
}


// ── cfRenderStats ──────────────────────────────────────────────────────────────
function cfRenderStats(status) {
  const stats = status?.stats || {};
  const indexed = stats.total_indexed ?? 0;
  const below = stats.below_cutoff ?? 0;
  const passing = stats.passing ?? 0;
  const instances = status?.instances || [];

  const indexedEl = el('cfStatIndexed');
  const belowEl = el('cfStatBelow');
  const passingEl = el('cfStatPassing');
  const indexedSub = el('cfStatIndexedSub');
  const passingPct = el('cfStatPassingPct');

  if (indexedEl) indexedEl.textContent = indexed.toLocaleString();
  if (belowEl) belowEl.textContent = below.toLocaleString();
  if (passingEl) passingEl.textContent = passing.toLocaleString();
  if (indexedSub) {
    const n = instances.length;
    indexedSub.textContent = n > 0 ? `across ${n} instance${n !== 1 ? 's' : ''}` : '';
  }
  if (passingPct) {
    passingPct.textContent = indexed > 0
      ? `${Math.round((passing / indexed) * 100)}% of indexed library`
      : '';
  }
  if (belowEl) belowEl.style.color = below > 0 ? 'var(--bad)' : 'var(--muted)';
}


// ── cfRenderCoverage ───────────────────────────────────────────────────────────
// Flat list: instance name, app badge, inline percentage pill, file counts.
// Scrollable via CSS on the container. Sync progress from sync_progress field.
function cfRenderCoverage(status) {
  const wrap = el('cfCoverageList');
  if (!wrap) return;

  const instances = status?.instances || [];
  const lastSyncedDot = el('cfLastSyncedDot');
  const lastSyncedText = el('cfLastSyncedText');

  if (!instances.length) {
    wrap.innerHTML = '<p class="help">No instances synced yet. Run Scan Library to build the index.</p>';
    if (lastSyncedDot) lastSyncedDot.style.background = 'var(--muted)';
    if (lastSyncedText) lastSyncedText.textContent = 'Never synced';
    return;
  }

  const timestamps = instances.map(i => i.last_synced_at).filter(Boolean).sort();
  const latestSync = timestamps.length ? timestamps[timestamps.length - 1] : null;
  if (lastSyncedDot) lastSyncedDot.style.background = latestSync ? 'var(--ok)' : 'var(--muted)';
  if (lastSyncedText) {
    lastSyncedText.textContent = latestSync
      ? 'Last Synced ' + fmtTime(latestSync)
      : 'Never synced';
  }

  wrap.innerHTML = instances.map((inst, idx) => {
    const app = (inst.app || 'radarr').toLowerCase();
    const isRadarr = app === 'radarr';
    const appLabel = isRadarr ? 'Radarr' : 'Sonarr';
    const total = inst.total_indexed || 0;
    const below = inst.below_cutoff || 0;

    const prog = inst.sync_progress;
    let pctLabel = '—';
    let pctStyle = 'color:var(--muted);background:transparent;border-color:var(--border);';
    if (prog) {
      const pct = prog.in_progress
        ? Math.min(99, prog.total > 0 ? Math.round((prog.processed / prog.total) * 100) : 0)
        : (prog.total > 0 ? 100 : 0);
      pctLabel = prog.in_progress ? pct + '%' : (prog.total > 0 ? '100%' : '—');
      if (prog.total > 0) pctStyle = '';
    }

    const isLast = idx === instances.length - 1;
    return `<div style="display:flex;align-items:center;justify-content:space-between;padding:9px 0;${isLast ? '' : 'border-bottom:1px solid var(--border);'}">
      <div>
        <div style="font-size:12.5px;font-weight:600;color:var(--text);display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
          ${_escHtml(inst.instance_name || inst.arr_instance_id)}
          <span class="cf-badge ${app}">${appLabel}</span>
          <span style="font-size:12px;font-weight:700;background:var(--accent-dim);border:1px solid var(--accent-border);color:var(--accent-lt);border-radius:6px;padding:1px 7px;${pctStyle}">${pctLabel}</span>
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

  const sorted = [...CF_ALL_ENTRIES].sort((a, b) => {
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

  const start = CF_PAGE * CF_PAGE_SIZE;
  const slice = sorted.slice(start, start + CF_PAGE_SIZE);
  const maxGap = Math.max(...CF_ALL_ENTRIES.map(e => e.gap ?? e.cutoff_score - e.current_score), 1);

  const sortTh = (col, label) => {
    const active = CF_SORT.col === col;
    const cls = active ? (CF_SORT.dir === 'asc' ? 'sort-asc' : 'sort-desc') : '';
    return `<th class="sortable ${cls}" onclick="cfSortTable('${col}')">${label}</th>`;
  };

  const rows = slice.map(e => {
    const gap = e.gap ?? (e.cutoff_score - e.current_score);
    const barPct = Math.min(100, Math.round((Math.abs(gap) / maxGap) * 100));
    return `<tr>
      <td style="color:var(--text);font-weight:500;font-size:12.5px;">${_escHtml(e.title || '—')}</td>
      <td style="font-size:12px;color:var(--text-dim);">${_escHtml(e.instance_name || '—')}</td>
      <td style="font-size:12px;color:var(--text-dim);">${_escHtml(e.quality_profile_name || '—')}</td>
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

  const total = CF_TOTAL;
  const end = Math.min(start + CF_PAGE_SIZE, total);
  const totalPages = Math.max(1, Math.ceil(total / CF_PAGE_SIZE));
  if (pageInfo) pageInfo.textContent = `Page ${CF_PAGE + 1} of ${totalPages} · ${total} item${total !== 1 ? 's' : ''}`;

  const btnPrev = el('cfPagination')?.querySelector('button:first-child');
  const btnNext = el('cfPagination')?.querySelector('button:last-of-type');
  if (btnPrev) btnPrev.disabled = CF_PAGE === 0;
  if (btnNext) btnNext.disabled = end >= total;
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
  const hours = el('cfSyncHours');
  const rMax = el('cfRadarrMax');
  const sMax = el('cfSonarrMax');
  if (hours) hours.value = CFG.cf_score_sync_hours ?? 24;
  if (rMax) rMax.value = CFG.radarr_cf_max_per_run ?? 1;
  if (sMax) sMax.value = CFG.sonarr_cf_max_per_run ?? 1;
  const msg = el('cfMsg');
  if (msg) { msg.textContent = ''; msg.className = 'msg'; }
}


// ── saveCfScores ───────────────────────────────────────────────────────────────
async function saveCfScores() {
  if (!CFG) return;
  try {
    const hoursVal = parseInt(el('cfSyncHours')?.value || '24', 10);
    const rMaxVal  = parseInt(el('cfRadarrMax')?.value || '1', 10);
    const sMaxVal  = parseInt(el('cfSonarrMax')?.value || '1', 10);
    CFG.cf_score_sync_hours    = isNaN(hoursVal) || hoursVal < 1 ? 24 : hoursVal;
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


// ── cfFilterEntries ────────────────────────────────────────────────────────────
async function cfFilterEntries(app) {
  CF_FILTER = app;
  CF_PAGE = 0;
  try {
    const url = '/api/cf-scores/entries' + (app !== 'all' ? '?app=' + app : '');
    const data = await api(url);
    cfRenderTable(data);
  } catch(e) {
    console.error('[CF Score] cfFilterEntries failed:', e.message);
  }
}


// ── cfScanLibrary ──────────────────────────────────────────────────────────────
async function cfScanLibrary() {
  const btn = el('cfScanBtn');
  if (btn) { btn.disabled = true; btn.textContent = 'Scanning…'; }
  try {
    const result = await api('/api/cf-scores/scan', {method: 'POST'});
    if (result?.ok) {
      await _cfWaitForScan();
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


// ── cfResetIndex ───────────────────────────────────────────────────────────────
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


// ── _escHtml ───────────────────────────────────────────────────────────────────
function _escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

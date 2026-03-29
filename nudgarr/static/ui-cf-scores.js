// ── CF Score tab ───────────────────────────────────────────────────────────────
// Owns: CF Score tab rendering (fillCfScores, cfRenderCoverage, cfRenderTable),
// config fields (saveCfScores), manual scan (cfScanLibrary), index reset
// (cfResetIndex), and app filter buttons (cfFilterEntries).
//
// fillCfScores() is the main entry point called by _onTabShown('cf-scores').
// It fetches /api/cf-scores/status for stat cards and coverage rings, then
// fetches /api/cf-scores/entries for the items table.
//
// The tab is only reachable when cf_score_enabled is True -- the tab button is
// hidden otherwise (controlled by ui-core.js loadAll() and toggleCfScoreFeature
// in ui-advanced.js). All functions guard against missing elements gracefully.

// Active filter state -- 'all', 'radarr', or 'sonarr'
let CF_FILTER = 'all';


// ── fillCfScores -- main entry point ──────────────────────────────────────────
// Called by _onTabShown('cf-scores') every time the tab becomes active.
// Fetches status (stat cards + coverage) and entries (items table) in parallel.
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


// ── cfRenderStats ─────────────────────────────────────────────────────────────
// Renders the three stat cards from the status API response.
function cfRenderStats(status) {
  const stats = status?.stats || {};
  const indexed = stats.total_indexed ?? 0;
  const below = stats.below_cutoff ?? 0;
  const passing = stats.passing ?? 0;

  const indexedEl = el('cfStatIndexed');
  const belowEl = el('cfStatBelow');
  const passingEl = el('cfStatPassing');
  const indexedSub = el('cfStatIndexedSub');
  const passingPct = el('cfStatPassingPct');

  if (indexedEl) indexedEl.textContent = indexed.toLocaleString();
  if (belowEl) belowEl.textContent = below.toLocaleString();
  if (passingEl) passingEl.textContent = passing.toLocaleString();

  // Sub-labels: instance count and passing percentage
  const instances = status?.instances || [];
  if (indexedSub) {
    const n = instances.length;
    indexedSub.textContent = n > 0 ? `across ${n} instance${n !== 1 ? 's' : ''}` : '';
  }
  if (passingPct) {
    passingPct.textContent = indexed > 0
      ? `${Math.round((passing / indexed) * 100)}% of indexed library`
      : '';
  }

  // Colour the below-cutoff stat card: red when non-zero, muted when zero
  if (belowEl) {
    belowEl.style.color = below > 0 ? 'var(--bad)' : 'var(--muted)';
  }
}


// ── cfRenderCoverage ──────────────────────────────────────────────────────────
// Renders the per-instance sync coverage rings in the right card.
// Ring percentage reflects actual sync progress: 0->100% during a live scan,
// 100% once a sync has completed, 0% before first sync.
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

  // Find most recent last_synced_at across all instances for the status line
  const timestamps = instances.map(i => i.last_synced_at).filter(Boolean).sort();
  const latestSync = timestamps.length ? timestamps[timestamps.length - 1] : null;
  if (lastSyncedDot) lastSyncedDot.style.background = latestSync ? 'var(--ok)' : 'var(--muted)';
  if (lastSyncedText) {
    lastSyncedText.textContent = latestSync
      ? 'Last Synced ' + fmtTime(latestSync)
      : 'Never synced';
  }

  wrap.innerHTML = instances.map(inst => {
    const total = inst.total_indexed || 0;
    const below = inst.below_cutoff || 0;
    const app = (inst.app || 'radarr').toLowerCase();
    const isRadarr = app === 'radarr';
    const ringColor = isRadarr ? '#5b72f5' : '#34d399';
    const appLabel = isRadarr ? 'Radarr' : 'Sonarr';
    const appClass = isRadarr ? 'radarr' : 'sonarr';

    // Calculate ring percentage from sync_progress if available.
    // During an active scan: processed/total * 100 (animates in real time).
    // After scan completes: 100% if total > 0, else 0%.
    // Before first scan: 0%.
    const prog = inst.sync_progress;
    let pct = 0;
    let pctLabel = '0%';
    if (prog) {
      if (prog.in_progress) {
        pct = prog.total > 0 ? Math.min(99, Math.round((prog.processed / prog.total) * 100)) : 0;
        pctLabel = pct + '%';
      } else {
        pct = prog.total > 0 ? 100 : 0;
        pctLabel = pct + '%';
      }
    }

    // SVG ring: circumference of r=22 circle = 2*pi*22 = 138.2
    const circ = 138.2;
    const offset = circ * (1 - pct / 100);

    const subLabel = prog?.in_progress
      ? `Syncing… ${prog.processed || 0} / ${prog.total || 0}`
      : `${total.toLocaleString()} files indexed`;

    return `<div style="display:flex;align-items:center;gap:14px;padding:12px;background:rgba(255,255,255,.02);border:1px solid var(--border);border-radius:10px;margin-bottom:8px;">
      <div style="position:relative;width:56px;height:56px;flex-shrink:0;">
        <svg width="56" height="56" viewBox="0 0 56 56" style="transform:rotate(-90deg);">
          <circle fill="none" stroke="rgba(255,255,255,.06)" stroke-width="6" cx="28" cy="28" r="22"/>
          <circle fill="none" stroke="${ringColor}" stroke-width="6" stroke-linecap="round"
            cx="28" cy="28" r="22"
            stroke-dasharray="${circ}"
            stroke-dashoffset="${offset}"/>
        </svg>
        <div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;">
          <span style="font-size:12px;font-weight:800;color:var(--text);">${pctLabel}</span>
        </div>
      </div>
      <div style="flex:1;min-width:0;">
        <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;flex-wrap:wrap;">
          <span style="font-size:13px;font-weight:600;color:var(--text);">${inst.instance_name || inst.arr_instance_id}</span>
          <span class="cf-badge ${appClass}">${appLabel}</span>
        </div>
        <div style="font-size:11px;color:var(--text-dim);">${subLabel}</div>
        <div style="font-size:11px;color:var(--muted);margin-top:2px;">${below.toLocaleString()} below cutoff</div>
      </div>
    </div>`;
  }).join('');
}


// ── cfRenderTable ─────────────────────────────────────────────────────────────
// Renders the items-below-cutoff table and updates filter button active state.
function cfRenderTable(data) {
  const wrap = el('cfEntriesWrap');
  if (!wrap) return;

  // Sync filter button active states
  ['all', 'radarr', 'sonarr'].forEach(f => {
    const btns = document.querySelectorAll('#cfFilterBtns button');
    btns.forEach(b => {
      const matches = b.textContent.trim().toLowerCase() === f ||
        (f === 'all' && b.textContent.trim() === 'All');
      b.className = 'btn sm' + (f === CF_FILTER && matches ? ' primary' : '');
    });
  });

  const entries = data?.entries || [];
  if (!entries.length) {
    wrap.innerHTML = '<p class="help" style="padding:12px 0;">No items below CF cutoff' +
      (CF_FILTER !== 'all' ? ' for the selected filter' : '') + '.</p>';
    return;
  }

  const rows = entries.map(e => {
    const isRadarr = e.item_type === 'movie';
    const appLabel = isRadarr ? 'Radarr' : 'Sonarr';
    const appClass = isRadarr ? 'radarr' : 'sonarr';
    const gap = e.gap ?? (e.cutoff_score - e.current_score);
    // Gap bar width: percentage of max gap (cap at 100% for display)
    const maxGap = Math.max(e.cutoff_score, 1);
    const barPct = Math.min(100, Math.round((Math.abs(gap) / maxGap) * 100));

    return `<tr>
      <td style="color:var(--text);font-weight:500;font-size:12.5px;">${_escHtml(e.title || '—')}</td>
      <td><span class="cf-badge ${appClass}">${appLabel}</span></td>
      <td style="font-size:12px;color:var(--text-dim);">${_escHtml(e.instance_name || '—')}</td>
      <td style="font-size:12px;color:var(--text-dim);">${_escHtml(e.quality_profile_name || '—')}</td>
      <td style="font-family:'JetBrains Mono',ui-monospace,monospace;color:var(--bad);font-weight:600;">${e.current_score}</td>
      <td style="font-family:'JetBrains Mono',ui-monospace,monospace;color:var(--text-dim);">${e.cutoff_score}</td>
      <td style="font-family:'JetBrains Mono',ui-monospace,monospace;color:var(--warn);font-weight:600;">
        ${gap}
        <span style="display:inline-block;width:60px;height:4px;background:rgba(255,255,255,.06);border-radius:2px;overflow:hidden;vertical-align:middle;margin-left:6px;">
          <span style="display:block;height:100%;border-radius:2px;background:var(--warn);width:${barPct}%;"></span>
        </span>
      </td>
    </tr>`;
  }).join('');

  wrap.innerHTML = `
    <div style="overflow-x:auto;">
      <table class="cf-table">
        <thead>
          <tr>
            <th>Title</th>
            <th>App</th>
            <th>Instance</th>
            <th>Profile</th>
            <th>Current Score</th>
            <th>Cutoff Score</th>
            <th>Gap</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    ${entries.length >= 200 ? '<p class="help" style="margin-top:8px;padding-top:8px;border-top:1px solid var(--border);">Showing first 200 items.</p>' : ''}`;
}


// ── cfSyncConfigFields ────────────────────────────────────────────────────────
// Populates the config input fields from the current CFG object.
// Called after fillCfScores() and after saveAdvanced() reloads config.
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


// ── saveCfScores ──────────────────────────────────────────────────────────────
// Saves the CF Score config fields (sync interval, max per run) to the server.
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


// ── cfFilterEntries ───────────────────────────────────────────────────────────
// Switches the active app filter and refreshes the items table.
async function cfFilterEntries(app) {
  CF_FILTER = app;
  try {
    const url = '/api/cf-scores/entries' + (app !== 'all' ? '?app=' + app : '');
    const data = await api(url);
    cfRenderTable(data);
  } catch(e) {
    console.error('[CF Score] cfFilterEntries failed:', e.message);
  }
}


// ── cfScanLibrary ─────────────────────────────────────────────────────────────
// Triggers an immediate out-of-schedule library sync via the scan route.
// Disables the button while the scan is in progress and re-enables it when done.
async function cfScanLibrary() {
  const btn = el('cfScanBtn');
  if (btn) { btn.disabled = true; btn.textContent = 'Scanning…'; }
  try {
    const result = await api('/api/cf-scores/scan', {method: 'POST'});
    if (result?.ok) {
      // Poll for scan completion before refreshing
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


// ── _cfWaitForScan ────────────────────────────────────────────────────────────
// Polls /api/cf-scores/status until scan_in_progress is false.
// Refreshes the coverage rings on each tick so the ring percentage animates
// live as the syncer processes batches.
// Times out after 5 minutes to avoid an infinite wait on error.
async function _cfWaitForScan() {
  const maxAttempts = 150; // 5 minutes at 2s intervals
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise(r => setTimeout(r, 2000));
    try {
      const status = await api('/api/cf-scores/status');
      // Refresh rings live so percentage animates during the scan
      cfRenderCoverage(status);
      if (!status?.scan_in_progress) return;
    } catch(e) {
      return; // If status fails, stop waiting and refresh anyway
    }
  }
}


// ── cfResetIndex ──────────────────────────────────────────────────────────────
// Clears the entire CF score index after user confirmation.
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


// ── _escHtml ──────────────────────────────────────────────────────────────────
// Minimal HTML escaping for user-supplied strings rendered into innerHTML.
function _escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── Sweep tab ──────────────────────────────────────────────────────────────
// Owns: pipeline cards, summary cards, sweep feed (paginated history since
// last sweep start), and Run Now.
//
// Pipeline cards (Cutoff Unmet, Backlog, CF Score) show aggregate totals
// across all instances plus per-instance breakdowns. Data comes from
// status.last_summary which is structured as {radarr:[...], sonarr:[...]}.
//
// Summary cards (Sweep Health, Last Sweep, Imports Confirmed) come from
// STATUS fields: instance_health, last_run_utc, next_run_utc, sweep_lifetime,
// and imports_confirmed_sweep.
//
// Sweep feed calls /api/state/items?since=<last_sweep_start_utc> to show
// only items searched in the most recent sweep, paginated via SWEEP_FEED_PAGE.

// ── Pipeline card builder ─────────────────────────────────────────────────

function _pipelineCardHtml(type, insts, summary, health) {
  // type: 'cutoff' | 'backlog' | 'cfscore'
  // Aggregate totals across all instances for this pipeline.
  let agg = {};
  if (type === 'cutoff') {
    agg = {
      searched: 0, cooldown: 0, capped: 0,
      excluded: 0, tag: 0, profile: 0,
    };
    for (const s of summary) {
      agg.searched  += s.searched || 0;
      agg.cooldown  += s.skipped_cooldown || 0;
      const el_ = s.eligible || 0;
      const sr  = s.searched || 0;
      agg.capped    += Math.max(0, el_ - sr);
      agg.excluded  += s.skipped_excluded_cutoff || 0;
      agg.tag       += s.skipped_tag_cutoff || 0;
      agg.profile   += s.skipped_profile_cutoff || 0;
    }
  } else if (type === 'backlog') {
    agg = {
      searched: 0, cooldown: 0, capped: 0,
      grace: 0, tag: 0, profile: 0,
    };
    for (const s of summary) {
      agg.searched  += s.searched_missing || 0;
      agg.cooldown  += s.skipped_missing_cooldown || 0;
      const el_ = s.eligible_missing || 0;
      const sr  = s.searched_missing || 0;
      agg.capped    += Math.max(0, el_ - sr);
      agg.grace     += s.skipped_grace || 0;
      agg.tag       += s.skipped_tag_backlog || 0;
      agg.profile   += s.skipped_profile_backlog || 0;
    }
  } else {
    agg = { searched: 0, cooldown: 0, excluded: 0, queued: 0 };
    for (const s of summary) {
      agg.searched  += s.searched_cf || 0;
      agg.cooldown  += s.skipped_cf_cooldown || 0;
      agg.excluded  += s.skipped_cf_excluded || 0;
      agg.queued    += s.skipped_cf_queued || 0;
    }
  }

  function cell(lbl, val) {
    const dim = val === 0 ? ' dim' : '';
    return `<div class="p-total-cell"><div class="p-total-lbl">${lbl}</div>`
         + `<div class="p-total-val${dim}">${val}</div></div>`;
  }

  let totalsHtml = '';
  if (type === 'cutoff') {
    totalsHtml = `<div class="p-totals">`
      + cell('Searched', agg.searched) + cell('Cooldown', agg.cooldown)
      + cell('Capped', agg.capped) + cell('Excluded', agg.excluded)
      + cell('Tag', agg.tag) + cell('Profile', agg.profile)
      + `</div>`;
  } else if (type === 'backlog') {
    totalsHtml = `<div class="p-totals">`
      + cell('Searched', agg.searched) + cell('Cooldown', agg.cooldown)
      + cell('Capped', agg.capped) + cell('Grace', agg.grace)
      + cell('Tag', agg.tag) + cell('Profile', agg.profile)
      + `</div>`;
  } else {
    totalsHtml = `<div class="p-totals-4">`
      + cell('Searched', agg.searched) + cell('Cooldown', agg.cooldown)
      + cell('Excluded', agg.excluded) + cell('Queued', agg.queued)
      + `</div>`;
  }

  // Per-instance rows
  let instHtml = '';
  for (const inst of insts) {
    const hk = inst._kind + '|' + inst.name;
    const dotState = health[hk] || 'checking';
    const disabled = inst.enabled === false;
    const s = summary.find(x => x.name === inst.name);

    if (disabled) {
      instHtml += `<div class="p-inst-row">`
        + `<div class="p-inst-name"><span class="status-dot disabled"></span>${escapeHtml(inst.name)}</div>`
        + `<span class="p-inst-disabled">Disabled</span>`
        + `</div>`;
      continue;
    }

    let v1, v2, v3, l1, l2, l3;
    if (type === 'cutoff') {
      l1 = 'Searched'; v1 = s ? (s.searched || 0) : '&mdash;';
      l2 = 'Cooldown'; v2 = s ? (s.skipped_cooldown || 0) : '&mdash;';
      l3 = 'Excl';     v3 = s ? (s.skipped_excluded_cutoff || 0) : '&mdash;';
    } else if (type === 'backlog') {
      l1 = 'Searched'; v1 = s ? (s.searched_missing || 0) : '&mdash;';
      l2 = 'Cooldown'; v2 = s ? (s.skipped_missing_cooldown || 0) : '&mdash;';
      l3 = 'Excl';     v3 = s ? ((s.skipped_tag_backlog || 0) + (s.skipped_profile_backlog || 0)) : '&mdash;';
    } else {
      l1 = 'Searched'; v1 = s ? (s.searched_cf || 0) : '&mdash;';
      l2 = 'Cooldown'; v2 = s ? (s.skipped_cf_cooldown || 0) : '&mdash;';
      l3 = 'Excl';     v3 = s ? (s.skipped_cf_excluded || 0) : '&mdash;';
    }

    const d1 = v1 === 0 ? ' dim' : '';
    const d2 = ' dim', d3 = ' dim';
    instHtml += `<div class="p-inst-row">`
      + `<div class="p-inst-name"><span class="status-dot ${dotState}"></span>${escapeHtml(inst.name)}</div>`
      + `<div class="p-inst-stats">`
      + `<div class="p-inst-stat"><div class="p-inst-stat-lbl">${l1}</div><div class="p-inst-stat-val${d1}">${v1}</div></div>`
      + `<div class="p-inst-stat"><div class="p-inst-stat-lbl">${l2}</div><div class="p-inst-stat-val${d2}">${v2}</div></div>`
      + `<div class="p-inst-stat"><div class="p-inst-stat-lbl">${l3}</div><div class="p-inst-stat-val${d3}">${v3}</div></div>`
      + `</div></div>`;
  }

  const name = type === 'cutoff' ? 'Cutoff Unmet' : type === 'backlog' ? 'Backlog' : 'CF Score';
  const slotId = type === 'cutoff' ? 'sweepPipelineCutoff'
    : type === 'backlog' ? 'sweepPipelineBacklog'
    : 'sweepPipelineCfScore';

  const tooltipText = type === 'cutoff'
    ? 'Finds items that have a file but have not reached the quality profile cutoff and tells the Arr to search for a better version.'
    : type === 'backlog'
    ? 'Finds missing movies and episodes that have never been grabbed and tells the Arr to search for them.'
    : 'Finds monitored files where the custom format score is below the quality profile cutoff and tells the Arr to search for a better-scored release.';

  return `<div id="${slotId}" class="p-card ${type}">
    <div class="p-hdr">
      <div class="p-hdr-left">
        <span class="p-name">${name}</span>
        <div class="tooltip-wrap" style="display:inline-block;margin-left:5px;vertical-align:middle">
          <span class="tooltip-icon" style="font-size:9px">i<div class="tooltip-box">${tooltipText}</div></span>
        </div>
      </div>
    </div>
    ${totalsHtml}
    <div class="p-divider"></div>
    <div class="p-inst-lbl">Per Instance</div>
    ${instHtml}
  </div>`;
}

// ── refreshSweep ──────────────────────────────────────────────────────────

async function refreshSweep() {
  const status = await api('/api/status');
  const cfg    = await api('/api/config');
  const summary   = status.last_summary || {};
  const health    = status.instance_health || {};
  const lifetime  = status.sweep_lifetime || {};
  const cfEnabled = !!cfg.cf_score_enabled;

  // Build flat instance lists tagged with their kind ('radarr'/'sonarr')
  const allInsts = [];
  for (const kind of ['radarr', 'sonarr']) {
    for (const inst of (cfg.instances || {})[kind] || []) {
      allInsts.push({ ...inst, _kind: kind });
    }
  }

  const radarrSummary = summary.radarr || [];
  const sonarrSummary = summary.sonarr || [];
  const allSummary    = [...radarrSummary, ...sonarrSummary];

  // ── Pipeline cards ────────────────────────────────────────────────────
  const cutoffSlot  = el('sweepPipelineCutoff');
  const backlogSlot = el('sweepPipelineBacklog');
  const cfSlot      = el('sweepPipelineCfScore');

  if (!allInsts.length) {
    const msg = '<p class="help" style="margin:8px 0 0">No instances configured.</p>';
    if (cutoffSlot)  cutoffSlot.innerHTML  = msg;
    if (backlogSlot) backlogSlot.innerHTML = msg;
    if (cfSlot)      cfSlot.innerHTML      = msg;
  } else {
    if (cutoffSlot)  cutoffSlot.outerHTML  = _pipelineCardHtml('cutoff',  allInsts, allSummary, health);
    if (backlogSlot) backlogSlot.outerHTML = _pipelineCardHtml('backlog', allInsts, allSummary, health);
    if (cfSlot)      cfSlot.outerHTML      = cfEnabled
      ? _pipelineCardHtml('cfscore', allInsts, allSummary, health)
      : _pipelineCardHtml('cfscore', allInsts, [],         health);
  }

  // ── Health card ───────────────────────────────────────────────────────
  const badInstances = Object.entries(health).filter(([, v]) => v === 'bad');
  const enabledCount = Object.values(health).filter(v => v !== 'disabled').length;
  const okCount      = Object.values(health).filter(v => v === 'ok').length;

  // Lifetime totals across all instances
  let ltRuns = 0, ltSearched = 0;
  for (const row of Object.values(lifetime)) {
    ltRuns     += row.runs || 0;
    ltSearched += row.searched || 0;
  }
  const avgPerRun = ltRuns > 0 ? (ltSearched / ltRuns).toFixed(1) : '0';
  const lastErr   = status.last_error ? 'See Logs' : 'Never';
  const lastErrCls = status.last_error ? 'bad' : 'none';

  const healthCell = (lbl, val, cls) =>
    `<div class="health-stat-cell"><div class="health-stat-lbl">${lbl}</div>`
    + `<div class="health-stat-val ${cls}">${val}</div></div>`;

  const statsGrid = `<div class="health-stats">`
    + healthCell('Lifetime Runs',     ltRuns.toLocaleString(), '')
    + healthCell('Avg / Run',         avgPerRun, '')
    + healthCell('Last Error',        lastErr, lastErrCls)
    + healthCell('Instances',         `${okCount} / ${enabledCount}`, '')
    + `</div>`;

  const healthEl = el('sweepHealthCard');
  if (badInstances.length) {
    const n = badInstances.length;
    healthEl.className = 'card health-err-card';
    healthEl.innerHTML = `<span class="sum-title">Sweep Health</span>`
      + `<div class="health-err-banner"><div class="health-err-dot"></div>`
      + `<span class="health-err-text">${n} Instance${n > 1 ? 's' : ''} Failed Last Sweep</span></div>`
      + `<p class="health-err-hint">Check logs for details.</p>`
      + statsGrid;
  } else {
    healthEl.className = 'card';
    healthEl.innerHTML = `<span class="sum-title">Sweep Health</span>`
      + `<div class="health-ok-banner"><div class="health-ok-dot"></div>`
      + `<span class="health-ok-text">All Instances Healthy</span></div>`
      + statsGrid;
  }

  // ── Last Sweep card ───────────────────────────────────────────────────
  const lastRun  = status.last_run_utc;
  const nextRun  = status.next_run_utc;
  el('sweepLastCompletedVal').textContent = lastRun ? _relTime(lastRun) : 'Never';
  el('sweepLastCompletedSub').textContent = lastRun ? fmtTimePadded(lastRun) : '';
  el('sweepNextRunVal').textContent = nextRun ? _relTime(nextRun) : 'Off';
  el('sweepNextRunSub').textContent = nextRun ? fmtTimePadded(nextRun) : '';
  el('sweepLifetimeRuns').textContent     = ltRuns.toLocaleString();
  el('sweepLifetimeSearched').textContent = ltSearched.toLocaleString();

  // ── Imports Confirmed card ────────────────────────────────────────────
  const imp   = status.imports_confirmed_sweep || {};
  const movies = imp.movies || 0;
  const shows  = imp.shows  || 0;
  const total  = movies + shows;

  let ltImports = 0;
  for (const row of Object.values(lifetime)) ltImports += row.searched || 0;

  const impEl = el('sweepImportsCard');
  if (total > 0) {
    impEl.innerHTML = `<span class="sum-title">Imports Confirmed</span>`
      + `<div class="import-total-row">`
      + `<div class="import-total-val">${total}</div>`
      + `<div class="import-total-sub">Imports Confirmed</div></div>`
      + `<div class="import-breakdown">`
      + `<div class="import-cell"><div class="import-cell-lbl">Movies</div>`
      + `<div class="import-cell-val">${movies}</div>`
      + `<div class="import-cell-sub">Radarr</div></div>`
      + `<div class="import-cell"><div class="import-cell-lbl">Episodes</div>`
      + `<div class="import-cell-val">${shows}</div>`
      + `<div class="import-cell-sub">Sonarr</div></div></div>`
      + `<div class="import-lifetime"><span class="import-lifetime-lbl">Lifetime Imports</span>`
      + `<span class="import-lifetime-val">${ltImports.toLocaleString()}</span></div>`;
  } else {
    impEl.innerHTML = `<span class="sum-title">Imports Confirmed</span>`
      + `<div class="import-empty">`
      + `<div class="import-empty-val">0</div>`
      + `<div class="import-empty-sub">Nothing Imported This Sweep</div></div>`
      + `<div class="import-lifetime"><span class="import-lifetime-lbl">Lifetime Imports</span>`
      + `<span class="import-lifetime-val">${ltImports.toLocaleString()}</span></div>`;
  }

  // ── Feed ──────────────────────────────────────────────────────────────
  if (SWEEP_FEED_PAGE === 0) {
    loadSweepFeed(0);
  }
}

function _relTime(iso) {
  if (!iso) return '—';
  try {
    const diff = Math.round((new Date(iso) - Date.now()) / 1000);
    const abs  = Math.abs(diff);
    if (abs < 60)   return diff >= 0 ? 'In a moment' : 'Just now';
    if (abs < 3600) return diff >= 0 ? `${Math.round(abs / 60)} min` : `${Math.round(abs / 60)} min ago`;
    if (abs < 86400) return diff >= 0 ? `${Math.round(abs / 3600)} hr` : `${Math.round(abs / 3600)} hr ago`;
    return fmtTimePadded(iso);
  } catch (e) { return '—'; }
}

// ── Sweep feed ────────────────────────────────────────────────────────────

async function loadSweepFeed(page) {
  const status = await api('/api/status');
  const since  = status.last_sweep_start_utc || '';
  if (!since) {
    el('sweepFeedBody').innerHTML =
      '<tr><td colspan="4" style="text-align:center;color:var(--muted);padding:16px 0;font-size:12px">No sweep has run yet.</td></tr>';
    el('sweepFeedPageInfo').textContent = '';
    el('sweepFeedPrevBtn').disabled = true;
    el('sweepFeedNextBtn').disabled = true;
    return;
  }
  const limit  = parseInt(el('sweepFeedLimit').value || '10', 10);
  const offset = page * limit;
  const data   = await api(`/api/state/items?since=${encodeURIComponent(since)}&limit=${limit}&offset=${offset}`);
  SWEEP_FEED_TOTAL = data.total || 0;
  SWEEP_FEED_PAGE  = page;

  const tbody = el('sweepFeedBody');
  if (!data.items || !data.items.length) {
    tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--muted);padding:16px 0;font-size:12px">No items searched this sweep.</td></tr>';
    el('sweepFeedPageInfo').textContent = '';
    el('sweepFeedPrevBtn').disabled = true;
    el('sweepFeedNextBtn').disabled = true;
    return;
  }

  function pipePill(sweepType) {
    if (!sweepType) return '';
    const t = sweepType.toLowerCase();
    if (t === 'cf score') return '<span class="sw-pill cfscore">CF Score</span>';
    if (t === 'backlog')  return '<span class="sw-pill backlog">Backlog</span>';
    return '<span class="sw-pill cutoff">Cutoff</span>';
  }

  tbody.innerHTML = data.items.map(item => {
    const ts   = item.last_searched || '';
    const time = ts ? new Date(ts).toLocaleTimeString([], {hour:'numeric', minute:'2-digit'}) : '—';
    const pip  = pipePill(item.sweep_type);
    const app  = item.app || '';
    const clickAttr = `onclick="openArrLink('${escapeHtml(app)}','${escapeHtml(item.instance_name || '')}','${escapeHtml(item.item_id || '')}','${escapeHtml(item.series_id || '')}')" title="Open in ${app === 'radarr' ? 'Radarr' : 'Sonarr'}"`;
    return `<tr>`
      + `<td class="arr-link" ${clickAttr}>${escapeHtml(item.title || '')}</td>`
      + `<td><span class="feed-instance">${escapeHtml(item.instance || '')}</span></td>`
      + `<td><span class="feed-time">${escapeHtml(time)}</span></td>`
      + `<td class="feed-badge-cell">${pip}</td>`
      + `</tr>`;
  }).join('');

  const from = offset + 1;
  const to   = Math.min(offset + data.items.length, SWEEP_FEED_TOTAL);
  el('sweepFeedPageInfo').textContent = `Showing ${from} \u2013 ${to} of ${SWEEP_FEED_TOTAL}`;
  el('sweepFeedPrevBtn').disabled = page <= 0;
  el('sweepFeedNextBtn').disabled = to >= SWEEP_FEED_TOTAL;
  el('sweepFeedGoInput').value    = page + 1;
}

function prevSweepFeed() {
  if (SWEEP_FEED_PAGE > 0) loadSweepFeed(SWEEP_FEED_PAGE - 1);
}

function nextSweepFeed() {
  const limit    = parseInt(el('sweepFeedLimit').value || '10', 10);
  const maxPage  = Math.ceil(SWEEP_FEED_TOTAL / limit) - 1;
  if (SWEEP_FEED_PAGE < maxPage) loadSweepFeed(SWEEP_FEED_PAGE + 1);
}

function goToSweepFeedPage() {
  const limit   = parseInt(el('sweepFeedLimit').value || '10', 10);
  const maxPage = Math.max(0, Math.ceil(SWEEP_FEED_TOTAL / limit) - 1);
  const p       = Math.min(maxPage, Math.max(0, parseInt(el('sweepFeedGoInput').value || '1', 10) - 1));
  loadSweepFeed(p);
}

// ── Sweep no-instances modal ──────────────────────────────────────────────

function showSweepNoInstancesModal() {
  el('sweepNoInstancesModal').style.display = 'flex';
}

// ── Run Now ───────────────────────────────────────────────────────────────

async function runNow() {
  try {
    await api('/api/run-now', {method:'POST'});
    el('lastRun').textContent = 'Running\u2026';
    el('dot-scheduler').classList.add('running');
    const wm = el('wordmark');
    wm.classList.add('sweeping');
    wm._pendingStop = false;
  } catch(e) {
    showAlert('Run request failed: ' + e.message);
  }
}

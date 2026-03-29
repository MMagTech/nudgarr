/**
 * ui-intel.js
 *
 * Intel tab — fetch /api/intel and render the full dashboard.
 *
 * Public functions (checked by validate.py):
 *   fillIntel()    -- called by showTab('intel') to load/refresh data
 *   renderIntel()  -- render a payload object into the DOM
 *   resetIntel()   -- called by Danger Zone Reset Intel button
 */

'use strict';

// ── Public: fillIntel ─────────────────────────────────────────────────────

function fillIntel() {
  api('/api/intel')
    .then(data => renderIntel(data))
    .catch(() => _intelError('Failed to load Intel data.'));
}

// ── Public: renderIntel ───────────────────────────────────────────────────

function renderIntel(d) {
  if (!d) return _intelError('Failed to load Intel data.');

  const coldEl    = document.getElementById('intelColdStart');
  const contentEl = document.getElementById('intelContent');

  if (d.cold_start) {
    if (coldEl)    coldEl.style.display    = '';
    if (contentEl) contentEl.style.display = 'none';
    _renderColdStart(d);
    return;
  }

  if (coldEl)    coldEl.style.display    = 'none';
  if (contentEl) contentEl.style.display = '';

  // ── Library Score ──────────────────────────────────────────────────
  _renderScore(d);

  // ── Search Health ──────────────────────────────────────────────────
  _renderSearchHealth(d.search_health || {});

  // ── Instance Performance ───────────────────────────────────────────
  _renderInstanceTable(d.instance_performance || []);

  // ── Stuck Items ────────────────────────────────────────────────────
  _renderStuckItems(d.stuck_items || [], d.search_health || {});

  // ── Exclusion Intel ────────────────────────────────────────────────
  _renderExclusionIntel(d.exclusion_intel || {});

  // ── Library Age ────────────────────────────────────────────────────
  _renderLibraryAge(d.library_age || {});

  // ── Quality Iteration ──────────────────────────────────────────────
  _renderQualityIteration(d.quality_iteration || {});

  // ── Sweep Efficiency ───────────────────────────────────────────────
  _renderSweepEfficiency(d.sweep_efficiency || []);
}

// ── Cold Start ────────────────────────────────────────────────────────────

function _renderColdStart(d) {
  const sh      = d.search_health || {};
  const imports = sh.success_total_imported || 0;
  const runs    = d.total_runs || 0;

  const importsEl = document.getElementById('intelColdImports');
  const runsEl    = document.getElementById('intelColdRuns');
  const progressWrap = document.getElementById('intelColdProgressWrap');
  const progressFill = document.getElementById('intelColdProgressFill');
  const progressPct  = document.getElementById('intelColdProgressPct');

  if (importsEl) {
    importsEl.textContent = imports;
    importsEl.style.color = imports > 0 ? 'var(--ok)' : 'var(--muted)';
  }
  if (runsEl) {
    runsEl.textContent = runs;
    runsEl.style.color = runs > 0 ? 'var(--accent-lt)' : 'var(--muted)';
  }

  // Progress bar — show only when at least one counter is above zero.
  // Uses the higher of the two completion percentages since either hitting
  // 100% unlocks the score.
  const importsPct = Math.round((imports / 25) * 100);
  const runsPct    = Math.round((runs / 50) * 100);
  const best       = Math.min(100, Math.max(importsPct, runsPct));

  if (progressWrap && progressFill && progressPct) {
    if (imports > 0 || runs > 0) {
      progressWrap.style.display = '';
      progressFill.style.width   = best + '%';
      progressPct.textContent    = best + '%';
    } else {
      progressWrap.style.display = 'none';
    }
  }
}

// ── Public: resetIntel ───────────────────────────────────────────────────

function resetIntel() {
  api('/api/intel/reset', { method: 'POST' })
    .then(() => {
      fillIntel();
    })
    .catch(() => alert('Reset Intel failed. Please try again.'));
}

// ── Score ─────────────────────────────────────────────────────────────────

function _renderScore(d) {
  const numEl    = document.getElementById('intelScoreNum');
  const sublbl   = document.getElementById('intelScoreSublbl');
  const fillEl   = document.getElementById('intelScoreFill');
  const gradeEl  = document.getElementById('intelScoreGrade');
  const compsEl  = document.getElementById('intelScoreComps');
  const sh       = d.search_health || {};
  const eff      = d.sweep_efficiency || [];

  if (d.cold_start || d.library_score === null || d.library_score === undefined) {
    numEl.textContent   = 'Building…';
    numEl.style.fontSize = '16px';
    sublbl.style.display = 'none';
    gradeEl.style.display = 'none';
    // Grey out sub-components.
    ['intelCompSuccessVal','intelCompTurnaroundVal','intelCompStuckVal','intelCompEffVal']
      .forEach(id => { const el = document.getElementById(id); if (el) el.textContent = '—'; });
    return;
  }

  const score = d.library_score;
  numEl.textContent    = score;
  numEl.style.fontSize = '';
  sublbl.style.display = '';

  // Ring fill: circumference = 339.3
  const offset = 339.3 * (1 - score / 100);
  fillEl.style.strokeDashoffset = offset;
  fillEl.setAttribute('class', 'intel-score-fill ' + (score >= 70 ? 'high' : score >= 40 ? 'mid' : 'low'));

  // Grade pill.
  gradeEl.style.display = '';
  if (score >= 70) {
    gradeEl.textContent = 'Good Health';
    gradeEl.className   = 'intel-grade high';
  } else if (score >= 40) {
    gradeEl.textContent = 'Needs Attention';
    gradeEl.className   = 'intel-grade mid';
  } else {
    gradeEl.textContent = 'Poor Health';
    gradeEl.className   = 'intel-grade low';
  }

  // Sub-components.
  const successPct = Math.round((sh.success_rate || 0) * 100);
  _setComp('Success', successPct + '%', successPct, 'var(--ok)');

  const avgDays = sh.turnaround_avg_days || 0;
  const tScore  = Math.max(0, Math.round(100 - (avgDays / 30) * 100));
  _setComp('Turnaround', avgDays.toFixed(1) + ' Days', tScore, 'var(--accent)');

  const stuck = sh.stuck_items_disabled ? null : (sh.stuck_items_total || 0);
  const stuckScore = stuck === null ? 50 : Math.max(0, 100 - stuck * 5);
  _setComp('Stuck', stuck === null ? 'N/A' : stuck + ' items', stuckScore, 'var(--ok)');

  const totalElig = eff.reduce((s, r) => s + (r.eligible || 0), 0);
  const totalSrch = eff.reduce((s, r) => s + (r.searched || 0), 0);
  const effPct    = totalElig > 0 ? Math.round((totalSrch / totalElig) * 100) : 0;
  _setComp('Efficiency', effPct + '% used', effPct, 'var(--accent)');
}

function _setComp(label, valText, pct, color) {
  const key = label.replace(/\s/g,'');
  const fillEl = document.getElementById('intelComp' + key + 'Fill');
  const valEl  = document.getElementById('intelComp' + key + 'Val');
  if (fillEl) { fillEl.style.width = Math.min(100, pct) + '%'; fillEl.style.background = color; }
  if (valEl)  { valEl.textContent = valText; }
}

// ── Search Health ─────────────────────────────────────────────────────────

function _renderSearchHealth(sh) {
  const successPct = Math.round((sh.success_rate || 0) * 100);
  const totalWorked   = sh.success_total_worked || 0;
  const totalImported = sh.success_total_imported || 0;
  _setText('intelSuccessRate',
    successPct + '% \u200b(' + totalImported + ' of ' + totalWorked + ' items)');

  const avgDays = sh.turnaround_avg_days || 0;
  _setText('intelTurnaround', avgDays.toFixed(1) + ' Days');
  _setText('intelSearchesPerImport', (sh.searches_per_import_avg || 0).toFixed(1) + ' Searches');

  if (sh.stuck_items_disabled) {
    _setText('intelStuckTotal', 'N/A');
    document.getElementById('intelStuckTotal').className = 'intel-stat-val muted';
  } else {
    const stuck = sh.stuck_items_total || 0;
    _setText('intelStuckTotal', stuck + ' Item' + (stuck !== 1 ? 's' : ''));
    document.getElementById('intelStuckTotal').className =
      'intel-stat-val ' + (stuck > 0 ? 'warn' : 'ok');
  }

  const cutoff   = sh.cutoff_import_count   || 0;
  const backlog  = sh.backlog_import_count  || 0;
  const cfScore  = sh.cf_score_import_count || 0;
  const total    = cutoff + backlog + cfScore;
  _setText('intelCutoffCount',  cutoff);
  _setText('intelBacklogCount', backlog);
  _setText('intelCfScoreCount', cfScore);
  _setText('intelCutoffPct',   total > 0 ? Math.round(cutoff  / total * 100) + '% of imports' : '');
  _setText('intelBacklogPct',  total > 0 ? Math.round(backlog / total * 100) + '% of imports' : '');
  _setText('intelCfScorePct',  total > 0 ? Math.round(cfScore / total * 100) + '% of imports' : '');

  const upg = sh.quality_upgrades_count || 0;
  _setText('intelUpgradesCount', upg + ' Upgrade' + (upg !== 1 ? 's' : ''));
}

// ── Instance Performance Table ────────────────────────────────────────────

function _renderInstanceTable(rows) {
  const el = document.getElementById('intelInstanceTable');
  if (!el) return;
  if (!rows.length) {
    el.innerHTML = '<p class="help">No instance data yet.</p>';
    return;
  }

  const thead = `<thead><tr>
    <th>Instance</th>
    <th>Sweep Runs</th>
    <th>Total Searched</th>
    <th>Confirmed Imports</th>
    <th>Success Rate</th>
    <th>Avg Turnaround</th>
    <th>Eligible Used</th>
    <th>Stuck Items</th>
  </tr></thead>`;

  const tbody = rows.map(r => {
    const app       = r.app || 'radarr';
    const dotStyle  = app === 'sonarr'
      ? 'background:var(--ok);box-shadow:0 0 5px rgba(34,197,94,.5)'
      : 'background:var(--accent);box-shadow:0 0 5px rgba(91,114,245,.5)';
    const dot       = `<div class="run-dot" style="${dotStyle}"></div>`;
    const tag       = `<span class="intel-app-tag ${app}">${app.charAt(0).toUpperCase() + app.slice(1)}</span>`;
    const nameCell  = `<div class="intel-inst-cell">${dot}<div><div style="color:var(--text);font-weight:500;font-size:13px;">${escapeHtml(r.instance_name)}</div>${tag}</div></div>`;
    const sucPct    = Math.round((r.success_rate || 0) * 100);
    const sucColor  = sucPct >= 60 ? 'var(--ok)' : 'var(--warn)';
    const ratio     = r.eligible_used_ratio || 0;
    const barPct    = Math.round(ratio * 100);
    const barColor  = barPct >= 80 ? 'var(--ok)' : barPct >= 50 ? 'var(--warn)' : 'var(--bad)';
    const bar       = `<div class="intel-bar-wrap"><div class="intel-bar-track"><div class="intel-bar-fill" style="width:${barPct}%;background:${barColor};"></div></div><span style="font-size:11px;color:${barColor};min-width:34px;text-align:right;">${barPct}%</span></div>`;
    const stuckVal  = r.stuck_items || 0;
    const stuckClr  = stuckVal > 0 ? 'var(--warn)' : 'var(--muted)';
    return `<tr>
      <td>${nameCell}</td>
      <td><strong>${_num(r.runs)}</strong></td>
      <td><strong>${_num(r.searched)}</strong></td>
      <td><strong>${_num(r.confirmed_imports)}</strong></td>
      <td><strong style="color:${sucColor};">${sucPct}%</strong></td>
      <td><strong>${(r.turnaround_avg_days || 0).toFixed(1)} Days</strong></td>
      <td>${bar}</td>
      <td><strong style="color:${stuckClr};">${stuckVal}</strong></td>
    </tr>`;
  }).join('');

  el.innerHTML = `<table class="intel-table">${thead}<tbody>${tbody}</tbody></table>`;
}

// ── Stuck Items ───────────────────────────────────────────────────────────

function _renderStuckItems(items, sh) {
  const listEl = document.getElementById('intelStuckList');
  const subEl  = document.getElementById('intelStuckSub');
  if (!listEl) return;

  if (sh.stuck_items_disabled) {
    listEl.innerHTML = '<p class="help">Enable auto-exclusion thresholds to surface stuck items.</p>';
    if (subEl) subEl.textContent = 'Items searched repeatedly with no confirmed import';
    return;
  }

  if (!items.length) {
    listEl.innerHTML = '<p class="help">No stuck items detected.</p>';
    if (subEl) subEl.textContent = 'No items currently stuck';
    return;
  }

  if (subEl) {
    const total = sh.stuck_items_total || items.length;
    subEl.textContent = 'Searched ' + _threshold(sh) + '+ times with no confirmed import';
    if (total > items.length) {
      subEl.textContent += ' — showing ' + items.length + ' of ' + total;
    }
  }

  listEl.innerHTML = items.map(item => {
    const firstDate    = item.first_searched ? _fmtDate(item.first_searched) : 'Unknown';
    const addedDate    = item.library_added  ? _fmtDate(item.library_added)  : 'Unknown';
    const addedText    = item.library_added  ? ' \u00b7 Added ' + addedDate  : '';
    return `<div class="intel-stuck-item">
      <div class="intel-stuck-top">
        <span class="intel-stuck-title">${escapeHtml(item.title)}</span>
        <span class="intel-stuck-count">${item.search_count}&times;</span>
      </div>
      <div class="intel-stuck-meta">${escapeHtml(item.instance_name)} \u00b7 First searched ${firstDate}${addedText}</div>
    </div>`;
  }).join('');
}

function _threshold(sh) {
  return sh.stuck_threshold || '?';
}

// ── Exclusion Intel ───────────────────────────────────────────────────────

function _renderExclusionIntel(ei) {
  _setText('intelExclTotal',    ei.total || 0);
  _setText('intelExclThisMonth', ei.auto_exclusions_this_month || 0);

  const manual = ei.manual_count || 0;
  const auto   = ei.auto_count   || 0;
  const total  = manual + auto;
  _setText('intelExclManual', manual);
  _setText('intelExclAuto',   auto);
  _setText('intelExclManualPct', total > 0 ? Math.round(manual / total * 100) + '% of exclusions' : '');
  _setText('intelExclAutoPct',   total > 0 ? Math.round(auto   / total * 100) + '% of exclusions' : '');
  _setText('intelAvgSearches', (ei.avg_searches_at_exclusion || 0).toFixed(1) + ' Searches');

  const cal      = ei.calibration || {};
  const ratioEl  = document.getElementById('intelCalibrationRatio');
  const callout  = document.getElementById('intelCalibrationCallout');
  const textEl   = document.getElementById('intelCalibrationText');

  if (ratioEl) ratioEl.textContent = cal.later_imported + ' of ' + cal.total_unexcluded;

  if (callout && textEl) {
    if (cal.cold_start) {
      callout.style.display = 'none';
    } else {
      callout.style.display = '';
      const ratio = cal.total_unexcluded > 0
        ? cal.later_imported / cal.total_unexcluded : 0;
      callout.className = 'intel-callout ' + (ratio > 0.20 ? 'warn' : 'ok');
      textEl.textContent = cal.recommendation || '';
    }
  }
}

// ── Library Age ───────────────────────────────────────────────────────────

function _renderLibraryAge(la) {
  const chartEl   = document.getElementById('intelAgeChart');
  const unknownEl = document.getElementById('intelUnknownNote');
  if (!chartEl) return;

  const buckets = (la.buckets || []).filter(b => b.label !== 'Unknown' && b.total > 0);
  if (!buckets.length) {
    chartEl.innerHTML = '<p class="help">Not enough data yet to show library age breakdown.</p>';
    return;
  }

  chartEl.innerHTML = buckets.map(b => {
    const pct   = b.total > 0 ? Math.round((b.imported / b.total) * 100) : 0;
    const color = pct >= 70 ? 'var(--ok)' : pct >= 50 ? 'var(--accent)' : 'var(--warn)';
    return `<div class="intel-age-row">
      <span class="intel-age-label">${escapeHtml(b.label)}</span>
      <div class="intel-age-track"><div class="intel-age-fill" style="width:${pct}%;background:${color};"></div></div>
      <span class="intel-age-pct" style="color:${color};">${pct}%</span>
    </div>`;
  }).join('');

  if (unknownEl) {
    const note = la.unknown_note || '';
    if (note) {
      unknownEl.textContent    = note;
      unknownEl.style.display  = '';
    } else {
      unknownEl.style.display  = 'none';
    }
  }
}

// ── Quality Iteration ─────────────────────────────────────────────────────

function _renderQualityIteration(qi) {
  _setText('intelImportedOnce', _num(qi.imported_once || 0));
  _setText('intelUpgraded',     _num(qi.upgraded      || 0));

  const pathsEl = document.getElementById('intelUpgradePaths');
  if (!pathsEl) return;

  const radarr = qi.upgrade_path_radarr;
  const sonarr = qi.upgrade_path_sonarr;

  const hasRadarr = radarr && radarr.from && radarr.count > 0;
  const hasSonarr = sonarr && sonarr.from && sonarr.count > 0;

  if (!hasRadarr && !hasSonarr) {
    pathsEl.innerHTML = '<p class="help">No upgrade paths recorded yet.</p>';
    return;
  }

  const rows = [];
  if (hasRadarr) rows.push(_upgradePathRow('radarr', radarr));
  if (hasSonarr) rows.push(_upgradePathRow('sonarr', sonarr));
  pathsEl.innerHTML = rows.join('');
}

function _upgradePathRow(app, path) {
  return `<div class="intel-upgrade-path">
    <span class="intel-app-tag ${app}">${app.charAt(0).toUpperCase() + app.slice(1)}</span>
    <span class="intel-up-from">${escapeHtml(path.from)}</span>
    <span class="intel-up-arrow">&#8594;</span>
    <span class="intel-up-to">${escapeHtml(path.to)}</span>
    <span class="intel-up-count">${path.count} time${path.count !== 1 ? 's' : ''}</span>
  </div>`;
}

// ── Sweep Efficiency ──────────────────────────────────────────────────────

function _renderSweepEfficiency(rows) {
  const el = document.getElementById('intelEfficiency');
  if (!el) return;
  if (!rows.length) {
    el.innerHTML = '<p class="help">No sweep data yet.</p>';
    return;
  }

  el.innerHTML = rows.map(r => {
    const ratio    = r.ratio || 0;
    const pct      = Math.round(ratio * 100);
    const barColor = pct >= 80 ? 'var(--ok)' : pct >= 50 ? 'var(--warn)' : 'var(--bad)';
    const pctColor = pct >= 80 ? 'var(--ok)' : pct >= 50 ? 'var(--warn)' : 'var(--bad)';
    const app      = r.app || 'radarr';
    const dotStyle = app === 'sonarr'
      ? 'background:var(--ok);box-shadow:0 0 5px rgba(34,197,94,.5)'
      : 'background:var(--accent);box-shadow:0 0 5px rgba(91,114,245,.5)';
    const dotClass = 'run-dot';
    return `<div class="intel-eff-row">
      <div class="intel-eff-name">
        <div class="${dotClass}" style="${dotStyle}"></div>
        ${escapeHtml(r.instance_name)}
      </div>
      <div class="intel-eff-bar-wrap">
        <div class="intel-eff-track"><div class="intel-eff-fill" style="width:${pct}%;background:${barColor};"></div></div>
        <div class="intel-eff-numbers">${_num(r.searched)} searched of ${_num(r.eligible)} eligible &middot; lifetime average</div>
      </div>
      <div class="intel-eff-pct" style="color:${pctColor};">${pct}%</div>
    </div>`;
  }).join('');
}

// ── Error state ───────────────────────────────────────────────────────────

function _intelError(msg) {
  const ids = [
    'intelInstanceTable','intelStuckList','intelAgeChart',
    'intelUpgradePaths','intelEfficiency'
  ];
  ids.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = `<p class="help">${escapeHtml(msg)}</p>`;
  });
}

// ── Utilities ─────────────────────────────────────────────────────────────

function _setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

function _num(n) {
  return (n || 0).toLocaleString();
}

function _fmtDate(iso) {
  if (!iso) return 'Unknown';
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch (_) { return iso; }
}

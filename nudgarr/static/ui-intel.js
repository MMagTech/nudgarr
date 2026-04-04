/**
 * ui-intel.js
 *
 * Intel tab -- fetch /api/intel and render the redesigned dashboard (v4.3.0).
 *
 * Public functions (checked by validate.py):
 *   fillIntel()    -- called by showTab('intel') to load/refresh data
 *   renderIntel()  -- render a payload object into the DOM
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

  // ── Import Summary ─────────────────────────────────────────────────
  _renderImportSummary(d.import_summary || {});

  // ── Instance Performance ───────────────────────────────────────────
  _renderInstanceTable(d.instance_performance || []);

  // ── Upgrade History ────────────────────────────────────────────────
  _renderUpgradeHistory(d.upgrade_history || {});

  // ── CF Score Health ────────────────────────────────────────────────
  _renderCfScoreHealth(d.cf_score_health);

  // ── Exclusion Intel ────────────────────────────────────────────────
  _renderExclusionIntel(d.exclusion_intel || {});
}

// ── Cold Start ────────────────────────────────────────────────────────────

function _renderColdStart(d) {
  const is_   = d.import_summary || {};
  const imports = is_.total_imports || 0;
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

// ── Import Summary ────────────────────────────────────────────────────────

function _renderImportSummary(is_) {
  // Headline numbers
  const avgDays = is_.turnaround_avg_days || 0;
  _setText('intelTurnaround', _fmtAvgTurnaround(avgDays));
  _setText('intelSearchesPerImport', (is_.searches_per_import_avg || 0).toFixed(1) + ' Searches');
  const upg = is_.quality_upgrades_count || 0;
  _setText('intelUpgradesCount', _num(upg) + ' Upgrade' + (upg !== 1 ? 's' : ''));

  // Pipeline breakdown table
  const tableEl = document.getElementById('intelPipelineTable');
  if (!tableEl) return;

  const cutoffImports = is_.cutoff_import_count || 0;
  const backlogImports = is_.backlog_import_count || 0;
  const cfImports = is_.cf_score_import_count || 0;
  const total = cutoffImports + backlogImports + cfImports;

  const cutoffSearches = is_.cutoff_search_count || 0;
  const backlogSearches = is_.backlog_search_count || 0;
  const cfSearches = is_.cf_score_search_count || 0;

  const cutoffEnabled = is_.cutoff_enabled !== false;
  const backlogEnabled = !!is_.backlog_enabled;
  const cfEnabled = !!is_.cf_enabled;

  const pct = (n) => total > 0 ? '(' + Math.round(n / total * 100) + '%)' : '(0%)';
  const conv = (imp, srch) => srch > 0 ? Math.round(imp / srch * 100) + '%' : '0%';
  const disabledPill = '<span style="font-size:10px;margin-left:4px;background:rgba(255,255,255,.05);border:1px solid var(--border);border-radius:4px;padding:1px 5px;color:var(--muted);">Disabled</span>';

  const rows = [
    {
      label: 'Cutoff Unmet',
      color: 'var(--accent-lt)',
      tagClass: 'cutoff',
      imports: cutoffImports,
      searches: cutoffSearches,
      enabled: cutoffEnabled,
      pctOfTotal: pct(cutoffImports),
    },
    {
      label: 'Backlog',
      color: 'var(--ok)',
      tagClass: 'backlog',
      imports: backlogImports,
      searches: backlogSearches,
      enabled: backlogEnabled,
      pctOfTotal: pct(backlogImports),
    },
    {
      label: 'CF Score',
      color: 'var(--warn)',
      tagClass: 'cf',
      imports: cfImports,
      searches: cfSearches,
      enabled: cfEnabled,
      pctOfTotal: pct(cfImports),
    },
  ];

  const thead = `<thead><tr>
    <th>Pipeline</th>
    <th style="text-align:right">Imports</th>
    <th style="text-align:right">Searches</th>
    <th style="text-align:right">Conversion</th>
  </tr></thead>`;

  const tbody = rows.map(r => {
    const dimStyle = (!r.enabled && (r.imports > 0 || r.searches > 0))
      ? 'color:var(--text-dim);' : (!r.enabled ? 'color:var(--muted);' : '');
    const tagOpacity = r.enabled ? '' : 'opacity:0.4;';
    const dotColor = r.enabled ? r.color : 'var(--muted)';
    const convCell = r.enabled
      ? `<span style="${dimStyle}">${conv(r.imports, r.searches)}</span>`
      : (r.imports > 0
        ? `<span style="${dimStyle}">${conv(r.imports, r.searches)} ${disabledPill}</span>`
        : disabledPill);

    return `<tr>
      <td><div class="pipeline-label">
        <div class="pip-dot" style="background:${dotColor}"></div>
        <span class="tag ${r.tagClass}" style="${tagOpacity}">${r.label}</span>
      </div></td>
      <td style="text-align:right;${dimStyle}font-weight:600;">${_num(r.imports)} <span class="conv-rate">${r.pctOfTotal}</span></td>
      <td style="text-align:right;${dimStyle}font-weight:600;">${_num(r.searches)}</td>
      <td style="text-align:right;">${convCell}</td>
    </tr>`;
  }).join('');

  tableEl.innerHTML = `<table class="intel-pipeline-table">${thead}<tbody>${tbody}</tbody></table>`;
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
    <th>Avg Turnaround</th>
  </tr></thead>`;

  const tbody = rows.map(r => {
    const app      = r.app || 'radarr';
    const enabled  = r.enabled !== false;
    const dotStyle = enabled
      ? (app === 'sonarr'
          ? 'background:var(--ok);'
          : 'background:var(--accent);')
      : 'background:var(--muted);';
    const badgeOpacity = enabled ? '' : 'opacity:0.5;';
    const cellStyle = enabled ? '' : 'color:var(--text-dim);';
    const disabledPill = !enabled
      ? '<span style="font-size:10px;margin-left:6px;background:rgba(255,255,255,.05);border:1px solid var(--border);border-radius:4px;padding:1px 5px;color:var(--muted);">Disabled</span>'
      : '';
    const badge = `<div class="inst-badge ${app}" style="${badgeOpacity}"><div class="inst-dot" style="${dotStyle}"></div>${escapeHtml(r.instance_name)}</div>`;
    const nameCell = `<div style="display:flex;align-items:center;gap:6px;">${badge}${disabledPill}</div>`;

    return `<tr>
      <td>${nameCell}</td>
      <td style="${cellStyle}"><strong>${_num(r.runs)}</strong></td>
      <td style="${cellStyle}"><strong>${_num(r.searched)}</strong></td>
      <td style="${cellStyle}color:${enabled ? 'var(--ok)' : 'var(--text-dim)'}"><strong>${_num(r.confirmed_imports)}</strong></td>
      <td style="${cellStyle}"><strong>${_fmtAvgTurnaround(r.turnaround_avg_days)}</strong></td>
    </tr>`;
  }).join('');

  el.innerHTML = `<table class="intel-table">${thead}<tbody>${tbody}</tbody></table>`;
}

// ── Upgrade History ───────────────────────────────────────────────────────

function _renderUpgradeHistory(uh) {
  _setText('intelImportedOnce', _num(uh.imported_once || 0));
  _setText('intelUpgraded',     _num(uh.upgraded      || 0));

  const pathsEl = document.getElementById('intelUpgradePaths');
  if (!pathsEl) return;

  const paths = uh.upgrade_paths || [];
  if (!paths.length) {
    pathsEl.innerHTML = '<p class="help">No upgrade paths recorded yet.</p>';
    return;
  }

  pathsEl.innerHTML = paths.map(p => `
    <div class="intel-upgrade-path">
      <div>
        <span class="intel-up-from">${escapeHtml(p.from)}</span>
        <span class="intel-up-arrow">&#8594;</span>
        <span class="intel-up-to">${escapeHtml(p.to)}</span>
      </div>
      <span class="upgrade-count">${p.count}&times;</span>
    </div>`).join('');
}

// ── CF Score Health ───────────────────────────────────────────────────────

function _renderCfScoreHealth(cf) {
  const card = document.getElementById('intelCfScoreCard');
  const content = document.getElementById('intelCfScoreContent');
  if (!card || !content) return;

  if (!cf) {
    card.style.display = 'none';
    return;
  }

  card.style.display = '';

  const total  = cf.total_indexed  || 0;
  const below  = cf.below_cutoff   || 0;
  const pct    = cf.below_pct      || 0;
  const avg    = cf.avg_gap        || 0;
  const worst  = cf.worst_gap      || 0;
  const radarr = cf.radarr_below   || 0;
  const sonarr = cf.sonarr_below   || 0;
  const synced = cf.last_synced_at || '';

  const fmtSync = synced ? _fmtDateUS(synced) : 'Never';

  content.innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:1px;background:var(--border);border-radius:var(--radius-sm);overflow:hidden;margin-bottom:12px;">
      <div style="background:var(--surface);padding:12px 14px;">
        <div style="font-size:22px;font-weight:800;line-height:1;color:var(--text);margin-bottom:3px;">${_num(total)}</div>
        <div style="font-size:11px;color:var(--muted);">Total Indexed</div>
      </div>
      <div style="background:var(--surface);padding:12px 14px;">
        <div style="font-size:22px;font-weight:800;line-height:1;color:var(--warn);margin-bottom:3px;">${_num(below)}</div>
        <div style="font-size:11px;color:var(--muted);">Below Cutoff</div>
      </div>
      <div style="background:var(--surface);padding:12px 14px;">
        <div style="font-size:22px;font-weight:800;line-height:1;color:var(--muted);margin-bottom:3px;">${pct}%</div>
        <div style="font-size:11px;color:var(--muted);">of Index</div>
      </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:1px;background:var(--border);border-radius:var(--radius-sm);overflow:hidden;margin-bottom:12px;">
      <div style="background:var(--surface);padding:12px 14px;">
        <div style="font-size:18px;font-weight:800;line-height:1;color:var(--text);margin-bottom:3px;">${avg}</div>
        <div style="font-size:11px;color:var(--muted);">Avg Gap</div>
      </div>
      <div style="background:var(--surface);padding:12px 14px;">
        <div style="font-size:18px;font-weight:800;line-height:1;color:var(--bad);margin-bottom:3px;">${_num(worst)}</div>
        <div style="font-size:11px;color:var(--muted);">Worst Gap</div>
      </div>
      <div style="background:var(--surface);padding:12px 14px;display:flex;flex-direction:column;justify-content:center;">
        <div style="font-size:10px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin-bottom:6px;">App Split</div>
        <div style="display:flex;flex-direction:column;gap:3px;">
          <div style="display:flex;justify-content:space-between;font-size:11px;">
            <span style="color:var(--accent-lt);">Radarr</span>
            <span style="font-weight:600;color:var(--text);">${_num(radarr)}</span>
          </div>
          <div style="display:flex;justify-content:space-between;font-size:11px;">
            <span style="color:var(--ok);">Sonarr</span>
            <span style="font-weight:600;color:var(--text);">${_num(sonarr)}</span>
          </div>
        </div>
      </div>
    </div>
    <div style="display:flex;align-items:center;justify-content:space-between;padding-top:10px;border-top:1px solid var(--border);">
      <span style="font-size:11.5px;color:var(--muted);">Last synced</span>
      <span style="font-size:11.5px;color:var(--text-dim);">${escapeHtml(fmtSync)}</span>
    </div>`;
}

// ── Exclusion Intel ───────────────────────────────────────────────────────

function _renderExclusionIntel(ei) {
  const content = document.getElementById('intelExclusionContent');
  if (!content) return;

  const total   = ei.total        || 0;
  const manual  = ei.manual_count || 0;
  const auto    = ei.auto_count   || 0;
  const thisMonth = ei.auto_exclusions_this_month || 0;
  const cycled  = ei.titles_cycled || 0;
  const later   = ei.unexcluded_later_imported || 0;
  const autoOn  = !!ei.auto_enabled;

  const manualPct = total > 0 ? Math.round(manual / total * 100) : 0;
  const autoPct   = total > 0 ? Math.round(auto   / total * 100) : 0;

  const disabledNotice = !autoOn
    ? `<div style="display:flex;align-items:center;gap:8px;padding:8px 10px;background:rgba(255,255,255,.03);border:1px solid var(--border);border-radius:var(--radius-sm);margin-bottom:12px;">
        <div style="width:6px;height:6px;border-radius:50%;background:var(--muted);flex-shrink:0;"></div>
        <span style="font-size:11.5px;color:var(--muted);">Auto-exclusions disabled. Enable in the Advanced tab to automate exclusions.</span>
      </div>`
    : '';

  const thisMonthColor = autoOn && thisMonth > 0 ? 'var(--warn)' : 'var(--muted)';
  const autoColor = auto > 0 ? 'var(--accent-lt)' : 'var(--muted)';

  content.innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--border);border-radius:var(--radius-sm);overflow:hidden;margin-bottom:12px;">
      <div style="background:var(--surface);padding:12px 14px;">
        <div style="font-size:22px;font-weight:800;line-height:1;color:var(--text);margin-bottom:3px;">${_num(total)}</div>
        <div style="font-size:11px;color:var(--muted);">Total Exclusions</div>
      </div>
      <div style="background:var(--surface);padding:12px 14px;">
        <div style="font-size:22px;font-weight:800;line-height:1;color:${thisMonthColor};margin-bottom:3px;">${thisMonth}</div>
        <div style="font-size:11px;color:var(--muted);">Auto this month</div>
      </div>
      <div style="background:var(--surface);padding:12px 14px;border-top:1px solid var(--border);">
        <div style="font-size:10px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin-bottom:6px;">Manual</div>
        <div style="font-size:20px;font-weight:800;line-height:1;color:var(--text);margin-bottom:3px;">${_num(manual)}</div>
        <div style="font-size:11px;color:var(--muted);">${manualPct}%</div>
      </div>
      <div style="background:var(--surface);padding:12px 14px;border-top:1px solid var(--border);">
        <div style="font-size:10px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin-bottom:6px;">Auto</div>
        <div style="font-size:20px;font-weight:800;line-height:1;color:${autoColor};margin-bottom:3px;">${_num(auto)}</div>
        <div style="font-size:11px;color:var(--muted);">${autoPct}%</div>
      </div>
    </div>
    ${disabledNotice}
    <div style="height:1px;background:var(--border);margin-bottom:12px;"></div>
    <div class="intel-stat-row">
      <span class="intel-stat-label">Titles cycled through exclusions
        <span class="tooltip-wrap"><span class="tooltip-icon tip-down">i<div class="tooltip-box">Titles that were excluded and later unexcluded at least once. Counts both manual and auto exclusion cycling. Reset by Reset Intel.</div></span></span>
      </span>
      <span class="intel-stat-val">${_num(cycled)}</span>
    </div>
    <div class="intel-stat-row">
      <span class="intel-stat-label">Unexcluded titles later imported
        <span class="tooltip-wrap"><span class="tooltip-icon tip-down">i<div class="tooltip-box">Titles that were excluded, given a second chance via unexclude, and later confirmed imported. Counts both manual and auto exclusion cycles. Reset by Reset Intel.</div></span></span>
      </span>
      <span class="intel-stat-val ok">${_num(later)}</span>
    </div>`;
}

// ── Error state ───────────────────────────────────────────────────────────

function _intelError(msg) {
  const ids = ['intelPipelineTable', 'intelInstanceTable', 'intelUpgradePaths', 'intelCfScoreContent', 'intelExclusionContent'];
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

function _fmtDateUS(iso) {
  if (!iso) return 'Never';
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch (_) { return iso; }
}

// _fmtAvgTurnaround -- format a float days value as a human-readable duration,
// matching the per-item turnaround format used on the Imports tab.
// 0 or no imports returns '--'.
function _fmtAvgTurnaround(days) {
  if (!days || days <= 0) return '--';
  const totalSeconds = days * 86400;
  if (totalSeconds < 30) return '<1m';
  const minutes = Math.round(totalSeconds / 60);
  const hours = Math.floor(minutes / 60);
  const days_ = Math.floor(hours / 24);
  if (days_ >= 56) return Math.floor(days_ / 30) + 'mo';
  if (days_ >= 7) {
    const weeks = Math.floor(days_ / 7);
    const remDays = days_ % 7;
    return remDays ? weeks + 'w ' + remDays + 'd' : weeks + 'w';
  }
  if (days_ > 0) {
    const remHours = hours % 24;
    return remHours ? days_ + 'd ' + remHours + 'h' : days_ + 'd';
  }
  if (hours > 0) {
    const remMins = minutes % 60;
    return remMins ? hours + 'h ' + remMins + 'm' : hours + 'h';
  }
  return minutes + 'm';
}

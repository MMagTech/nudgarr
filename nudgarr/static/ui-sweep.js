// ── Sweep tab ──────────────────────────────────────────────────────────────
// Owns: Sweep tab rendering (refreshSweep, showSweepNoInstancesModal) and
// Run Now (runNow).
// History and Exclusions logic lives in ui-history.js.
// Imports logic lives in ui-imports.js.
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
      const dotState = health[instKey] || 'checking';
      const disabled = inst.enabled === false;
      const sw = summaryInsts.find(s => s.name === inst.name);
      const modeKey = kind === 'radarr' ? 'radarr_sample_mode' : 'sonarr_sample_mode';
      const mode = cfg[modeKey] || legacyMode || 'random';

      // Lifetime row for this instance
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
        const sr  = (sw.searched || 0) + (sw.searched_missing || 0);
        const el_ = (sw.eligible || 0) + (sw.eligible_missing || 0);
        SWEEP_DATA_CACHE[cacheKey] = {
          cutoffUnmet: sw.cutoff_unmet_total ?? '—',
          backfill:    sw.missing_total ?? 0,
          eligible:    el_,
          searched:    sr,
          onCooldown:  (sw.skipped_cooldown || 0) + (sw.skipped_missing_cooldown || 0),
          capped:      Math.max(0, el_ - sr),
        };
      }
      const cached  = SWEEP_DATA_CACHE[cacheKey] || null;
      const hasData = cached != null;
      const dim     = 'dim';

      // Library State — retained on disabled cards (reflects library, not run activity)
      const cuVal  = hasData ? cached.cutoffUnmet : '—';
      const bfVal  = hasData ? cached.backfill    : '—';
      const cuDim  = hasData ? (cached.cutoffUnmet === '—' ? dim : '') : dim;
      const bfDim  = hasData ? '' : dim;

      // This Run — dashed on disabled cards (no run occurred)
      const elVal  = (!disabled && hasData) ? cached.eligible   : '—';
      const srVal  = (!disabled && hasData) ? cached.searched   : '—';
      const cdVal  = (!disabled && hasData) ? cached.onCooldown : '—';
      const capVal = (!disabled && hasData) ? cached.capped     : '—';
      const elDim  = (!disabled && hasData) ? ''       : dim;
      const srDim  = (!disabled && hasData) ? 'accent' : dim;
      const cdDim  = dim;
      const capDim = dim;

      // Backfill sub-label is app-specific
      const bfSub  = kind === 'radarr' ? 'Movies missing' : 'Episodes missing';

      // Lifetime grid — show when any lifetime data exists
      const ltSearched = lf ? (lf.searched ?? 0) : null;
      const ltRuns     = lf ? (lf.runs     ?? 0) : null;
      const lifetimeGrid = ltSearched !== null ? `
        <div class="lifetime-grid">
          <div class="lifetime-cell"><div class="lifetime-lbl">Lifetime Searched</div><div class="lifetime-val">${ltSearched.toLocaleString()}</div></div>
          <div class="lifetime-cell"><div class="lifetime-lbl">Sweep Runs</div><div class="lifetime-val">${ltRuns.toLocaleString()}</div></div>
        </div>` : '';

      const disabledBadge = disabled
        ? `<span class="sweep-disabled-badge">Disabled</span>`
        : '';

      return `
        <div class="sweep-card${disabled ? ' disabled-card' : ''}" id="sweepcard-${kind}-${inst.name.replace(/\s+/g,'_')}">
          <div class="sweep-top">
            <div class="sweep-name-row">
              <span class="status-dot ${dotState}" id="sdot-sweep-${instKey}"></span>
              <div>
                <div class="sweep-inst-name">${escapeHtml(inst.name)}</div>
                <div class="sweep-url">${escapeHtml(fmtMode(mode))}</div>
              </div>
            </div>
            <div class="sweep-right">
              ${disabledBadge}
              <span class="sweep-lastrun">${escapeHtml(lastRun)}</span>
            </div>
          </div>
          <div class="section-band">
            <div class="section-lbl">Library State</div>
            <div class="stats-grid-2">
              <div class="stat-cell"><div class="stat-lbl">Cutoff Unmet</div><div class="stat-val ${cuDim}">${cuVal}</div><div class="stat-sub">In library</div></div>
              <div class="stat-cell"><div class="stat-lbl">Backfill</div><div class="stat-val ${bfDim}">${bfVal}</div><div class="stat-sub">${bfSub}</div></div>
            </div>
          </div>
          <div class="section-band">
            <div class="section-lbl">This Run</div>
            <div class="stats-grid-4">
              <div class="stat-cell"><div class="stat-lbl">Eligible</div><div class="stat-val ${elDim}">${elVal}</div><div class="stat-sub">In scope</div></div>
              <div class="stat-cell"><div class="stat-lbl">Searched</div><div class="stat-val ${srDim}">${srVal}</div><div class="stat-sub">Triggered</div></div>
              <div class="stat-cell"><div class="stat-lbl">Cooldown</div><div class="stat-val ${cdDim}">${cdVal}</div><div class="stat-sub">Skipped</div></div>
              <div class="stat-cell"><div class="stat-lbl">Capped</div><div class="stat-val ${capDim}">${capVal}</div><div class="stat-sub">Over limit</div></div>
            </div>
          </div>
          ${lifetimeGrid}
        </div>`;
    }).join('');
  }
}
function showSweepNoInstancesModal() {
  el('sweepNoInstancesModal').style.display = 'flex';
}

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


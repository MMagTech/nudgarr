// ── Portrait Home, Instances, Sweep tabs ──────────────────────────────────
// mUpdateHome, mRenderInstanceRows, mRunNow, mInitRunBtn,
// mToggleAuto, mToggleMaintWindow, mToggleRadarrBacklog, mToggleSonarrBacklog,
// mToggleInstance, mRenderSweep, mAccordion,
// mAddArrLinkHandler

// ── Home ───────────────────────────────────────────────────────────────────

// mUpdateHome — refreshes all dynamic content on the portrait Home tab.
// Updates last/next run timestamps, run-button state (idle vs. sweeping),
// scheduler and notifications toggle highlights, the cron description sub-label,
// and triggers mRenderInstanceRows() to rebuild the instance health list.
function mUpdateHome(cfg, st) {
  const lastEl = document.getElementById('m-last-run');
  const lastSub = document.getElementById('m-last-run-sub');
  if (lastEl) {
    if (st.run_in_progress) {
      lastEl.textContent = 'Running\u2026';
      lastEl.style.color = 'var(--ok)';
    } else {
      lastEl.textContent = fmtTime(st.last_run_utc);
      lastEl.style.color = '';
    }
  }
  if (lastSub) lastSub.textContent = st.run_in_progress ? 'In progress' : 'Completed';

  const nextEl = document.getElementById('m-next-run');
  const nextSub = document.getElementById('m-next-run-sub');
  if (nextEl) nextEl.textContent = cfg.scheduler_enabled ? fmtTime(st.next_run_utc) : 'Manual';
  if (nextSub) nextSub.textContent = cfg.scheduler_enabled ? (describeCron(cfg.cron_expression || '')) : 'Auto schedule off';

  // Run button state
  const btnIcon = document.getElementById('m-run-btn-icon');
  const btnLabel = document.getElementById('m-run-btn-label');
  const btn = document.getElementById('m-run-btn');
  if (st.run_in_progress) {
    if (btn) btn.classList.add('m-run-btn-running');
    if (btnIcon) btnIcon.textContent = '\u25cf';
    if (btnLabel) btnLabel.textContent = 'Sweeping\u2026';
  } else {
    if (btn) btn.classList.remove('m-run-btn-running');
    if (btnIcon) btnIcon.textContent = '\u25b6';
    if (btnLabel) btnLabel.textContent = 'Run Now';
  }

  const autoActive = cfg.scheduler_enabled;
  const autoSub = document.getElementById('m-auto-sub');
  if (autoSub) autoSub.textContent = cfg.scheduler_enabled ? describeCron(cfg.cron_expression || '') : 'Manual';
  const tAuto = document.getElementById('m-toggle-auto');
  if (tAuto) tAuto.classList.toggle('m-on', !!autoActive);

  const maintRow = document.getElementById('m-maint-row');
  const tMaint = document.getElementById('m-toggle-maint');
  if (maintRow) {
    maintRow.style.opacity = autoActive ? '' : '.38';
    maintRow.style.pointerEvents = autoActive ? '' : 'none';
  }
  if (tMaint) tMaint.classList.toggle('m-on', !!cfg.maintenance_window_enabled);
  const maintSub = document.querySelector('#m-maint-row .m-toggle-sub');
  if (maintSub) {
    const noDays = cfg.maintenance_window_enabled && !(cfg.maintenance_window_days || []).length;
    maintSub.textContent = noDays ? 'Select at least one day' : 'Suppresses scheduled sweeps';
    maintSub.style.color = noDays ? 'var(--bad)' : '';
  }

  mRenderInstanceRows();
}

function mRenderInstanceRows() {
  const container = document.getElementById('m-instance-rows');
  if (!container || !CFG) return;
  const rows = [];
  ['radarr', 'sonarr'].forEach(kind => {
    (CFG.instances?.[kind] || []).forEach((inst, idx) => {
      const enabled = inst.enabled !== false;
      const healthKey = kind + '|' + inst.name;
      const health = (STATUS_CACHE && STATUS_CACHE[healthKey]) || 'checking';
      const dotColor = !enabled ? 'var(--muted)' : health === 'ok' ? 'var(--ok)' : health === 'bad' ? 'var(--bad)' : 'var(--muted)';
      const dotGlow = !enabled ? '' : health === 'ok' ? 'box-shadow:0 0 6px rgba(34,197,94,.5)' : health === 'bad' ? 'box-shadow:0 0 6px rgba(239,68,68,.5)' : '';
      const statusLabel = !enabled ? 'Disabled' : health === 'ok' ? 'Online' : health === 'bad' ? 'Offline' : 'Checking';
      const badgeColor = kind === 'sonarr' ? 'background:rgba(34,197,94,.1);color:#4ade80;border:1px solid rgba(34,197,94,.2)' : 'background:rgba(91,114,245,.15);color:var(--accent-lt);border:1px solid rgba(91,114,245,.25)';
      const ovCount = CFG.per_instance_overrides_enabled ? Object.keys(inst.overrides || {}).length : 0;
      const ovChip = ovCount > 0 ? '<span class="m-ov-chip">' + ovCount + ' Override' + (ovCount !== 1 ? 's' : '') + '</span>' : '';
      rows.push(
        '<div class="m-inst-row' + (!enabled ? ' m-inst-row-disabled' : '') + '">'
        + '<div style="display:flex;align-items:center;gap:10px;flex:1;min-width:0">'
        + '<div style="width:8px;height:8px;border-radius:50%;background:' + dotColor + ';' + dotGlow + ';flex-shrink:0"></div>'
        + '<div style="min-width:0">'
        + '<div style="display:flex;align-items:center;gap:6px">'
        + '<span class="m-inst-name">' + escapeHtml(inst.name) + '</span>'
        + '<span class="m-app-badge" style="' + badgeColor + '">' + (kind === 'radarr' ? 'Radarr' : 'Sonarr') + '</span>'
        + ovChip
        + '</div>'
        + '<div class="m-inst-status">' + statusLabel + '</div>'
        + '</div></div>'
        + '<div class="m-toggle' + (enabled ? ' m-on' : '') + '" onclick="mToggleInstance(\'' + kind + '\',' + idx + ')"></div>'
        + '</div>'
      );
    });
  });
  container.innerHTML = rows.join('') || '<p class="m-empty">No instances configured.</p>';
}

// ── Run Now ────────────────────────────────────────────────────────────────

async function mRunNow() {
  mHaptic(40);
  const btn = document.getElementById('m-run-btn');
  const btnIcon = document.getElementById('m-run-btn-icon');
  const btnLabel = document.getElementById('m-run-btn-label');
  if (btn) btn.classList.add('m-run-btn-running');
  if (btnIcon) btnIcon.textContent = '\u25cf';
  if (btnLabel) btnLabel.textContent = 'Sweeping\u2026';
  const lastEl = document.getElementById('m-last-run');
  if (lastEl) { lastEl.textContent = 'Running\u2026'; lastEl.style.color = 'var(--ok)'; }
  const lastSub = document.getElementById('m-last-run-sub');
  if (lastSub) lastSub.textContent = 'In progress';
  try {
    await api('/api/run-now', {method:'POST'});
  } catch(e) {}
}

function mInitRunBtn() {
  const btn = document.getElementById('m-run-btn');
  if (!btn) return;
  const hint = document.getElementById('m-run-hint-wrap');
  if (hint && localStorage.getItem('nudgarr_run_hint_dismissed')) hint.style.display = 'none';
  btn.addEventListener('click', () => {
    if (hint) { hint.style.display = 'none'; localStorage.setItem('nudgarr_run_hint_dismissed','1'); }
    mRunNow();
  });
}

// ── Toggles ────────────────────────────────────────────────────────────────


function mToggleAuto() {
  mHaptic(40);
  mSaveCfgKeys({scheduler_enabled: !CFG.scheduler_enabled});
}

function mToggleMaintWindow() {
  mHaptic(40);
  mSaveCfgKeys({maintenance_window_enabled: !CFG.maintenance_window_enabled});
}

function mToggleRadarrBacklog() {
  mHaptic(40);
  mSaveCfgKeys({radarr_backlog_enabled: !CFG.radarr_backlog_enabled});
}

function mToggleSonarrBacklog() {
  mHaptic(40);
  mSaveCfgKeys({sonarr_backlog_enabled: !CFG.sonarr_backlog_enabled});
}

// ── Instances ─────────────────────────────────────────────────────────────

async function mToggleInstance(kind, idx) {
  mHaptic(40);
  try {
    await api('/api/instance/toggle', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({kind, idx})});
    await loadAll();
    mRenderInstanceRows();
  } catch(e) {}
}

// ── Sweep ──────────────────────────────────────────────────────────────────

function mRenderSweep() {
  const list = document.getElementById('m-sweep-list');
  if (!list || !CFG) return;
  const cards = [];
  const legacyMode = CFG.sample_mode || 'random';
  function fmtMode(m) {
    return (m || 'random').split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
  }
  for (const kind of ['radarr', 'sonarr']) {
    (CFG.instances?.[kind] || []).forEach(inst => {
      const key = kind + '|' + inst.name;
      const disabled = inst.enabled === false;
      const cached = SWEEP_DATA_CACHE[key] || null;
      const hasData = cached != null;
      const modeKey = kind === 'radarr' ? 'radarr_sample_mode' : 'sonarr_sample_mode';
      const mode = CFG[modeKey] || legacyMode;
      const isOpen = (M_OPEN_SWEEP === null && cards.length === 0) || M_OPEN_SWEEP === key;
      const dotColor = disabled ? 'var(--muted)' : 'var(--ok)';
      const dotGlow = disabled ? '' : 'box-shadow:0 0 6px rgba(34,197,94,.5)';
      const badgeColor = kind === 'sonarr' ? 'background:rgba(34,197,94,.1);color:#4ade80;border:1px solid rgba(34,197,94,.2)' : 'background:rgba(91,114,245,.15);color:var(--accent-lt);border:1px solid rgba(91,114,245,.25)';
      const lastRun = hasData && cached.lastRun ? '\u00b7 ' + fmtTime(cached.lastRun) : '';
      cards.push(
        '<div class="m-sweep-card' + (isOpen ? ' m-open' : '') + '" data-key="' + key + '" onclick="mAccordion(this)">'
        + '<div class="m-sweep-hdr">'
        + '<div class="m-sweep-hdr-left">'
        + '<span style="width:8px;height:8px;border-radius:50%;background:' + dotColor + ';' + dotGlow + ';flex-shrink:0;display:inline-block"></span>'
        + '<div>'
        + '<div style="display:flex;align-items:center;gap:8px">'
        + '<span class="m-sweep-name">' + escapeHtml(inst.name) + '</span>'
        + '<span class="m-app-badge" style="' + badgeColor + '">' + (kind === 'radarr' ? 'Radarr' : 'Sonarr') + '</span>'
        + '</div>'
        + '<div style="font-size:10px;color:var(--muted);margin-top:2px">' + fmtMode(mode) + (disabled ? ' \u00b7 Disabled' : lastRun) + '</div>'
        + '</div></div>'
        + '<span class="m-sweep-chevron">\u25bc</span>'
        + '</div>'
        + '<div class="m-sweep-body">'
        + (disabled ? '<p class="m-sweep-meta">Disabled</p>' :
          '<div class="m-sweep-section">Library State</div>'
          + '<div class="m-stat-grid2">'
          + '<div class="m-stat2"><div class="m-stat2-label">Cutoff Unmet</div><div class="m-stat2-value' + (hasData ? '' : ' m-dim') + '">' + (hasData ? (cached.cutoffUnmet ?? '\u2014') : '\u2014') + '</div></div>'
          + '<div class="m-stat2"><div class="m-stat2-label">Backfill</div><div class="m-stat2-value' + (hasData ? '' : ' m-dim') + '">' + (hasData ? (cached.backfill ?? '\u2014') : '\u2014') + '</div></div>'
          + '</div>'
          + '<div class="m-sweep-section">This Run</div>'
          + '<div class="m-stat-grid2">'
          + '<div class="m-stat2"><div class="m-stat2-label">Eligible</div><div class="m-stat2-value' + (hasData ? '' : ' m-dim') + '">' + (hasData ? cached.eligible : '\u2014') + '</div></div>'
          + '<div class="m-stat2"><div class="m-stat2-value-ok' + (hasData ? '' : ' m-dim') + '">' + (hasData ? cached.searched : '\u2014') + '</div><div class="m-stat2-label">Searched</div></div>'
          + '</div>'
          + '<div class="m-sweep-secondary">'
          + '<div class="m-sweep-sec"><div class="m-stat2-label">Cooldown</div><div class="m-sweep-sec-val">' + (hasData ? cached.onCooldown : '\u2014') + '</div></div>'
          + '<div class="m-sweep-sec"><div class="m-stat2-label">Capped</div><div class="m-sweep-sec-val">' + (hasData ? cached.capped : '\u2014') + '</div></div>'
          + '</div>'
          + '<div class="m-sweep-section m-sweep-section-lt">Lifetime</div>'
          + '<div class="m-sweep-secondary m-sweep-secondary-lt">'
          + '<div class="m-sweep-sec m-sweep-sec-lt"><div class="m-stat2-label">Lifetime Searched</div><div class="m-sweep-sec-val-lt">' + (hasData ? (cached.lifetimeSearched ?? '\u2014') : '\u2014') + '</div></div>'
          + '<div class="m-sweep-sec m-sweep-sec-lt"><div class="m-stat2-label">Sweep Runs</div><div class="m-sweep-sec-val-lt">' + (hasData ? (cached.sweepRuns ?? '\u2014') : '\u2014') + '</div></div>'
          + '</div>'
        )
        + '</div></div>'
      );
    });
  }
  list.innerHTML = cards.join('') || '<p class="m-empty">No instances configured.</p>';
}

function mAccordion(card) {
  const key = card.dataset.key;
  const wasOpen = card.classList.contains('m-open');
  document.querySelectorAll('#m-sweep-list .m-sweep-card').forEach(c => c.classList.remove('m-open'));
  if (!wasOpen) {
    card.classList.add('m-open');
    M_OPEN_SWEEP = key;
  } else {
    const first = document.querySelector('#m-sweep-list .m-sweep-card');
    if (first) { first.classList.add('m-open'); M_OPEN_SWEEP = first.dataset.key; }
  }
}

// ── Arr link helper — scroll-safe tap handler ──────────────────────────────
// Attaches a touchstart/touchend delta guard so scrolling doesn't
// accidentally trigger an open-in-arr action. Falls back to click for
// desktop/mouse users.

function mAddArrLinkHandler(el, app, instance, itemId, seriesId) {
  if (!app || !instance || !itemId) return;
  el.classList.add('m-arr-link');
  let _ty = 0;
  el.addEventListener('touchstart', e => { _ty = e.touches[0].clientY; }, {passive: true});
  el.addEventListener('touchend', e => {
    if (Math.abs(e.changedTouches[0].clientY - _ty) < 10) {
      mHaptic(20);
      openArrLink(app, instance, itemId, seriesId || '');
    }
  }, {passive: true});
  el.addEventListener('click', () => openArrLink(app, instance, itemId, seriesId || ''));
}


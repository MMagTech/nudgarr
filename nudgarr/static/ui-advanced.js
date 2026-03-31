// ── Advanced tab ─────────────────────────────────────────────────────────────
// Owns: Advanced form (backlog, retention, auth, imports, UI prefs, overrides
// toggle, auto-exclusion fields), danger zone actions, diagnostics, and the
// auto-exclusion disabled popup.

function fillAdvanced() {
  if (!CFG) return;
  el('radarr_backlog_enabled').checked = !!CFG.radarr_backlog_enabled;
  el('radarr_missing_max').value = CFG.radarr_missing_max ?? 1;
  el('radarr_missing_added_days').value = CFG.radarr_missing_added_days ?? 14;
  // Backlog sample mode — independent of cutoff sample mode (v4.2.0)
  if (el('radarr_backlog_sample_mode')) el('radarr_backlog_sample_mode').value = CFG.radarr_backlog_sample_mode || 'random';
  if (el('radarr_missing_grace_hours')) el('radarr_missing_grace_hours').value = CFG.radarr_missing_grace_hours ?? 0;
  el('sonarr_backlog_enabled').checked = !!CFG.sonarr_backlog_enabled;
  el('sonarr_missing_max').value = CFG.sonarr_missing_max ?? 1;
  if (el('sonarr_backlog_sample_mode')) el('sonarr_backlog_sample_mode').value = CFG.sonarr_backlog_sample_mode || 'random';
  if (el('sonarr_missing_grace_hours')) el('sonarr_missing_grace_hours').value = CFG.sonarr_missing_grace_hours ?? 0;
  el('state_retention_days').value = CFG.state_retention_days ?? 180;
  el('auth_enabled').checked = CFG.auth_enabled !== false;
  el('auth_session_minutes').value = CFG.auth_session_minutes ?? 30;
  el('import_check_minutes').value = CFG.import_check_minutes ?? 120;
  if (el('show_support_link')) el('show_support_link').checked = CFG.show_support_link !== false;
  if (el('log_level')) el('log_level').value = CFG.log_level || 'INFO';
  if (el('per_instance_overrides_enabled')) {
    el('per_instance_overrides_enabled').checked = !!CFG.per_instance_overrides_enabled;
    syncOverridesToggleLabel();
  }
  // CF Score Scan toggle (v4.2.0)
  if (el('cf_score_enabled')) {
    el('cf_score_enabled').checked = !!CFG.cf_score_enabled;
    syncCfScoreToggleLabel();
  }
  // Auto-exclusion fields (page 2)
  if (el('auto_exclude_movies_threshold')) el('auto_exclude_movies_threshold').value = CFG.auto_exclude_movies_threshold ?? 0;
  if (el('auto_exclude_shows_threshold')) el('auto_exclude_shows_threshold').value = CFG.auto_exclude_shows_threshold ?? 0;
  if (el('auto_unexclude_movies_days')) el('auto_unexclude_movies_days').value = CFG.auto_unexclude_movies_days ?? 0;
  if (el('auto_unexclude_shows_days')) el('auto_unexclude_shows_days').value = CFG.auto_unexclude_shows_days ?? 0;
  if (el('radarr_auto_exclude_enabled')) el('radarr_auto_exclude_enabled').checked = !!CFG.radarr_auto_exclude_enabled;
  if (el('sonarr_auto_exclude_enabled')) el('sonarr_auto_exclude_enabled').checked = !!CFG.sonarr_auto_exclude_enabled;
  syncAuthUi();
  syncBacklogUi();
  syncSupportLinkUi();
  syncAutoExclUi();
  el('advMsg').textContent = ''; el('advMsg').className = 'msg';
}

// syncAutoExclUi — greys the threshold and unexclude fields when the toggle is
// off. When the toggle is on, also greys the unexclude field if the threshold
// is 0 (no searches configured yet). Mirrors the Backlog and Cutoff Unmet
// greying pattern.
function syncAutoExclUi() {
  for (const app of ['radarr', 'sonarr']) {
    const toggleId = app + '_auto_exclude_enabled';
    const labelId  = app + '_auto_excl_label';
    const fieldsId = app + '_auto_excl_fields';
    const unexclId = app === 'radarr' ? 'auto_unexclude_movies_wrap' : 'auto_unexclude_shows_wrap';
    const threshId = app === 'radarr' ? 'auto_exclude_movies_threshold' : 'auto_exclude_shows_threshold';

    const on = el(toggleId)?.checked ?? false;
    if (el(labelId)) el(labelId).textContent = on ? 'Enabled' : 'Disabled';

    const fields = el(fieldsId);
    if (fields) {
      fields.style.opacity = on ? '' : '0.35';
      fields.style.pointerEvents = on ? '' : 'none';
    }

    // When toggle is on, also grey unexclude if threshold is still 0
    if (on) {
      const thresh = parseInt(el(threshId)?.value || '0', 10);
      const unexcl = el(unexclId);
      if (unexcl) {
        unexcl.style.opacity = thresh > 0 ? '' : '0.35';
        unexcl.style.pointerEvents = thresh > 0 ? '' : 'none';
      }
    }
  }
}

function syncAuthUi() {
  const enabled = el('auth_enabled').checked;
  el('auth_label').textContent = enabled ? 'Enabled' : 'Disabled';
}

function markUnsaved(msgId) {
  const m = el(msgId);
  if (!m) return;
  clearTimeout(m._fadeTimer);
  m.classList.remove('fade');
  m.style.opacity = '';
  m.textContent = 'Unsaved Changes';
  m.className = 'msg unsaved';
}

function syncBacklogUi() {
  const radarrOn = el('radarr_backlog_enabled').checked;
  const sonarrOn = el('sonarr_backlog_enabled').checked;
  el('radarr_backlog_label').textContent = radarrOn ? 'Enabled' : 'Disabled';
  el('sonarr_backlog_label').textContent = sonarrOn ? 'Enabled' : 'Disabled';
  el('radarr_backlog_fields').style.opacity = radarrOn ? '1' : '0.35';
  el('radarr_backlog_fields').style.pointerEvents = radarrOn ? '' : 'none';
  el('sonarr_backlog_fields').style.opacity = sonarrOn ? '1' : '0.35';
  el('sonarr_backlog_fields').style.pointerEvents = sonarrOn ? '' : 'none';
}

async function saveAdvanced() {
  try {
    CFG.radarr_backlog_enabled = el('radarr_backlog_enabled').checked;
    CFG.radarr_missing_max = parseInt(el('radarr_missing_max').value !== '' ? el('radarr_missing_max').value : '0', 10);
    CFG.radarr_missing_added_days = parseInt(el('radarr_missing_added_days').value !== '' ? el('radarr_missing_added_days').value : '14', 10);
    // Backlog sample mode — independent of cutoff sample mode (v4.2.0)
    if (el('radarr_backlog_sample_mode')) CFG.radarr_backlog_sample_mode = el('radarr_backlog_sample_mode').value || 'random';
    if (el('radarr_missing_grace_hours')) CFG.radarr_missing_grace_hours = parseInt(el('radarr_missing_grace_hours').value !== '' ? el('radarr_missing_grace_hours').value : '0', 10);
    CFG.sonarr_backlog_enabled = el('sonarr_backlog_enabled').checked;
    CFG.sonarr_missing_max = parseInt(el('sonarr_missing_max').value !== '' ? el('sonarr_missing_max').value : '0', 10);
    if (el('sonarr_backlog_sample_mode')) CFG.sonarr_backlog_sample_mode = el('sonarr_backlog_sample_mode').value || 'random';
    if (el('sonarr_missing_grace_hours')) CFG.sonarr_missing_grace_hours = parseInt(el('sonarr_missing_grace_hours').value !== '' ? el('sonarr_missing_grace_hours').value : '0', 10);
    CFG.state_retention_days = parseInt(el('state_retention_days').value !== '' ? el('state_retention_days').value : '180', 10);
    CFG.auth_enabled = el('auth_enabled').checked;
    CFG.auth_session_minutes = parseInt(el('auth_session_minutes').value !== '' ? el('auth_session_minutes').value : '30', 10);
    CFG.import_check_minutes = parseInt(el('import_check_minutes').value !== '' ? el('import_check_minutes').value : '120', 10);
    if (el('show_support_link')) CFG.show_support_link = el('show_support_link').checked;
    if (el('log_level')) CFG.log_level = el('log_level').value || 'INFO';

    // Auto-exclusion fields — capture previous state before updating so we can
    // detect a disabling transition and show the popup if auto-exclusions exist.
    // Disabling occurs when: threshold goes from non-zero to zero, OR toggle turns off.
    const prevMovies = CFG.auto_exclude_movies_threshold ?? 0;
    const prevShows = CFG.auto_exclude_shows_threshold ?? 0;
    const prevMoviesEnabled = !!CFG.radarr_auto_exclude_enabled;
    const prevShowsEnabled = !!CFG.sonarr_auto_exclude_enabled;
    const newMovies = parseInt(el('auto_exclude_movies_threshold')?.value || '0', 10);
    const newShows = parseInt(el('auto_exclude_shows_threshold')?.value || '0', 10);
    const newMoviesEnabled = el('radarr_auto_exclude_enabled')?.checked ?? false;
    const newShowsEnabled = el('sonarr_auto_exclude_enabled')?.checked ?? false;
    CFG.auto_exclude_movies_threshold = newMovies;
    CFG.auto_exclude_shows_threshold = newShows;
    CFG.auto_unexclude_movies_days = parseInt(el('auto_unexclude_movies_days')?.value || '0', 10);
    CFG.auto_unexclude_shows_days = parseInt(el('auto_unexclude_shows_days')?.value || '0', 10);
    CFG.radarr_auto_exclude_enabled = el('radarr_auto_exclude_enabled')?.checked ?? false;
    CFG.sonarr_auto_exclude_enabled = el('sonarr_auto_exclude_enabled')?.checked ?? false;

    await api('/api/config', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(CFG)});
    await loadAll();
    await new Promise(r => setTimeout(r, 400));
    el('advMsg').textContent = 'Saved'; el('advMsg').className = 'msg ok'; fadeMsg('advMsg');
    syncAutoExclUi();

    // Show the auto-exclusion disabled popup if either app went from active to
    // inactive — either threshold dropped to zero or toggle was turned off
    const moviesDisabled = (prevMoviesEnabled && prevMovies > 0) && (!newMoviesEnabled || newMovies === 0);
    const showsDisabled  = (prevShowsEnabled  && prevShows  > 0) && (!newShowsEnabled  || newShows  === 0);
    if (moviesDisabled || showsDisabled) {
      _maybeShowAutoExclDisabledPopup(moviesDisabled, showsDisabled);
    }
  } catch(e) {
    el('advMsg').textContent = 'Save failed: ' + e.message; el('advMsg').className = 'msg err';
  }
}

// _maybeShowAutoExclDisabledPopup — queries the current auto-exclusion counts
// and shows the disabled popup only if rows actually exist to act on.
async function _maybeShowAutoExclDisabledPopup(moviesDisabled, showsDisabled) {
  try {
    const data = await api('/api/exclusions');
    const autoRows = (data || []).filter(e => e.source === 'auto');
    if (autoRows.length === 0) return;

    // Show combined total — clearing is a global action that affects all
    // auto-exclusions regardless of which app's threshold was set to 0
    const count = autoRows.length;
    el('autoExclDisabledBody').textContent =
      `You have ${count} auto-excluded title${count !== 1 ? 's' : ''}. You can clear them all now or keep them.`;
    el('autoExclDisabledModal').style.display = 'flex';
  } catch(e) { /* silent — popup is non-critical */ }
}

// onAutoExclDisabledKeep — closes the popup, keeping all auto-exclusions intact.
function onAutoExclDisabledKeep() {
  el('autoExclDisabledModal').style.display = 'none';
}

// onAutoExclDisabledClear — deletes all auto-exclusion rows then closes popup.
async function onAutoExclDisabledClear() {
  try {
    await api('/api/exclusions/clear-auto', {method:'POST'});
    await loadExclusions();
  } catch(e) { /* silent */ }
  el('autoExclDisabledModal').style.display = 'none';
}

async function logout() {
  try {
    await fetch('/api/auth/logout', {method:'POST'});
  } catch(e) {
    console.warn('[logout] request failed:', e.message);
  }
  window.location.href = '/login';
}

async function resetConfig() {
  if (!await showConfirm('Reset Config', 'This will reset all settings to defaults — all instances and configuration will be lost. Consider using Backup All in Support & Diagnostics first.', 'Reset', true)) return;
  await api('/api/config/reset', {method:'POST'});
  showAlert('Config reset to defaults.');
  await loadAll();
}

async function clearLog() {
  if (!await showConfirm('Clear Log', 'This will clear the active nudgarr.log file. Rotation backups are not affected. The log will resume writing immediately on the next sweep.', 'Clear', true)) return;
  await api('/api/log/clear', {method:'POST'});
}


// resetIntelData -- permanently resets the Intel dashboard to a clean slate.
// Clears intel_aggregate back to zero defaults and deletes all exclusion_events
// rows. Clear History and Clear Stats do not touch Intel data -- this is the
// only operation that resets it. Intel data will begin accumulating again
// immediately on the next sweep.
async function resetIntelData() {
  if (!await showConfirm(
    'Reset Intel',
    'This will permanently reset your Intel dashboard, including all lifetime performance data and exclusion event history. Intel data will begin accumulating again on the next sweep. This cannot be undone.',
    'Reset Intel',
    true
  )) return;
  await api('/api/intel/reset', {method:'POST'});
}

async function backupAll() {
  try {
    const res = await fetch('/api/file/backup', { credentials: 'same-origin' });
    if (!res.ok) { showAlert('Backup failed — please try again.'); return; }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'nudgarr-backup.zip';
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  } catch(e) { showAlert('Backup failed: ' + e.message); }
}

function downloadDiagnostic() {
  fetch('/api/diagnostic', { credentials: 'same-origin' })
    .then(res => { if (!res.ok) throw new Error('Request failed'); return res.blob(); })
    .then(blob => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = 'nudgarr-diagnostic.txt';
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
    })
    .catch(e => showAlert('Diagnostic failed: ' + e.message));
}

// ── CF Score Scan feature toggle (v4.2.0) ─────────────────────────────────────
// Mirrors the pattern used by toggleOverridesFeature in ui-overrides.js.
// The toggle HTML element lives in ui-tab-advanced.html (added in Phase 3).
// These functions are defined here in Phase 2 so _onTabShown and loadAll()
// can reference them safely before the Phase 3 HTML is in place.

function syncCfScoreToggleLabel() {
  const enabled = el('cf_score_enabled') && el('cf_score_enabled').checked;
  const lbl = el('cf_score_label');
  if (lbl) lbl.textContent = enabled ? 'Enabled' : 'Disabled';
}

async function toggleCfScoreFeature(enabled) {
  syncCfScoreToggleLabel();
  try {
    CFG.cf_score_enabled = enabled;
    await api('/api/config', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(CFG),
    });
    const tab = el('tab-btn-cf-scores');
    if (enabled) {
      if (tab) tab.classList.add('cf-tab-visible');
    } else {
      if (tab) tab.classList.remove('cf-tab-visible');
      // Navigate away if currently on the CF Score tab
      if (ACTIVE_TAB === 'cf-scores') _doShowTab('advanced');
    }
  } catch(e) {
    showAlert('Failed to save CF Score Scan setting: ' + e.message);
    // Revert toggle visually
    if (el('cf_score_enabled')) {
      el('cf_score_enabled').checked = !enabled;
      syncCfScoreToggleLabel();
    }
  }
}

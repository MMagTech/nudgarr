// ── Notifications tab ────────────────────────────────────────────────────────
// Owns: Notifications form (Apprise URL, event toggles, test, save).

// fillNotifications — populates the Notifications tab from CFG. Called by
// _onTabShown when the tab opens, provided no unsaved changes are pending.
function fillNotifications() {
  if (!CFG) return;
  el('notify_enabled').checked = !!CFG.notify_enabled;
  el('notify_url').value = CFG.notify_url || '';
  el('notify_on_sweep_complete').checked = CFG.notify_on_sweep_complete !== false;
  el('notify_on_import').checked = CFG.notify_on_import !== false;
  if (el('notify_on_auto_exclusion')) el('notify_on_auto_exclusion').checked = CFG.notify_on_auto_exclusion !== false;
  el('notify_on_error').checked = CFG.notify_on_error !== false;
  syncNotifyUi();
}

// syncNotifyUi — greys out the URL field and events card when notifications
// are disabled, and hides the Send Test row. Called on toggle and on fill.
function syncNotifyUi() {
  const enabled = el('notify_enabled').checked;
  el('notify_label').textContent = enabled ? 'Enabled' : 'Disabled';
  el('notify_url_field').style.opacity = enabled ? '1' : '0.5';
  el('notify_url_field').style.pointerEvents = enabled ? '' : 'none';
  el('notify_events_card').style.opacity = enabled ? '1' : '0.5';
  el('notify_events_card').style.pointerEvents = enabled ? '' : 'none';
  el('notify_test_row').style.display = enabled ? '' : 'none';
}

// toggleNotifyUrl — toggles the Apprise URL field between password and text
// visibility. Bound to the Show/Hide button next to the URL input.
function toggleNotifyUrl() {
  const inp = el('notify_url');
  const btn = el('notifyUrlToggleBtn');
  if (inp.type === 'password') { inp.type = 'text'; btn.textContent = 'Hide'; }
  else { inp.type = 'password'; btn.textContent = 'Show'; }
}

// testNotification — sends a test notification to the URL currently in the
// input field (not the saved value) via POST /api/notifications/test.
// Shows success or failure inline for 5 seconds then clears.
async function testNotification() {
  const url = el('notify_url').value.trim();
  const msg = el('notifyTestMsg');
  if (!url) { msg.textContent = 'Enter a URL first.'; msg.className = 'msg err'; return; }
  msg.textContent = 'Sending…'; msg.className = 'msg';
  const r = await api('/api/notifications/test', {method: 'POST', body: JSON.stringify({url})});
  if (r && r.ok) {
    msg.textContent = '✓ Notification sent successfully';
    msg.className = 'msg ok';
  } else {
    msg.textContent = '✗ ' + (r?.error || 'Failed — check your URL');
    msg.className = 'msg err';
  }
  setTimeout(() => { msg.textContent = ''; msg.className = 'msg'; }, 5000);
}

// saveNotifications — writes all notification fields to CFG and posts to
// /api/config. Calls loadAll() to resync global state after save.
async function saveNotifications() {
  CFG.notify_enabled = el('notify_enabled').checked;
  CFG.notify_url = el('notify_url').value.trim();
  CFG.notify_on_sweep_complete = el('notify_on_sweep_complete').checked;
  CFG.notify_on_import = el('notify_on_import').checked;
  if (el('notify_on_auto_exclusion')) CFG.notify_on_auto_exclusion = el('notify_on_auto_exclusion').checked;
  CFG.notify_on_error = el('notify_on_error').checked;
  const r = await api('/api/config', {method: 'POST', body: JSON.stringify(CFG)});
  if (r && r.ok) {
    await loadAll();
    await new Promise(res => setTimeout(res, 400));
    el('notifyMsg').textContent = 'Saved'; el('notifyMsg').className = 'msg ok'; fadeMsg('notifyMsg');
  }
}

// ── Notifications tab ────────────────────────────────────────────────────────
// Owns: Notifications form (Apprise URL, event toggles, test, save).

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

function syncNotifyUi() {
  const enabled = el('notify_enabled').checked;
  el('notify_label').textContent = enabled ? 'Enabled' : 'Disabled';
  el('notify_url_field').style.opacity = enabled ? '1' : '0.5';
  el('notify_url_field').style.pointerEvents = enabled ? '' : 'none';
  el('notify_events_card').style.opacity = enabled ? '1' : '0.5';
  el('notify_events_card').style.pointerEvents = enabled ? '' : 'none';
  el('notify_test_row').style.display = enabled ? '' : 'none';
}

function toggleNotifyUrl() {
  const inp = el('notify_url');
  const btn = el('notifyUrlToggleBtn');
  if (inp.type === 'password') { inp.type = 'text'; btn.textContent = 'Hide'; }
  else { inp.type = 'password'; btn.textContent = 'Show'; }
}

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

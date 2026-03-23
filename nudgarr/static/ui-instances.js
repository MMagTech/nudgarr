// ── Instances tab ──────────────────────────────────────────────────────────
// Owns: Instances tab rendering (renderInstances), instance modal
// (openModal, closeModal, saveModal, testModalConnection), connection
// tests (testConnections), save (saveAll), and shared helpers
// (fadeMsg, toggleKeyVis, checkModalUrlPath).
//
// Each instance card is rendered by renderInstances(kind) — called from
// loadAll() whenever config changes. The modal is reused for both add
// and edit flows; openModal(kind, idx) populates it for edit, addInstance
// opens it blank for add.
function renderInstances(kind) {
  const box = el(kind + 'List');
  const list = CFG?.instances?.[kind] || [];
  if (!list.length) {
    box.innerHTML = '<p class="help" style="margin:8px 0 0">No instances yet. Click <b>+ Add</b>.</p>';
    return;
  }
  box.innerHTML = list.map((it, idx) => {
    const enabled = it.enabled !== false;
    const contentDim = enabled ? '' : 'opacity:0.45;';
    const toggleLabel = enabled ? 'Disable' : 'Enable';
    const toggleClass = enabled ? 'btn sm' : 'btn sm primary';
    return `
    <div class="inst-card" id="instcard-${kind}-${idx}">
      <div class="inst-row1" style="${contentDim}">
        <span class="status-dot" id="sdot-${kind}-${idx}"></span>
        <div class="inst-info">
          <div class="inst-name">${escapeHtml(it.name || '(unnamed)')}</div>
          <div class="inst-meta">${escapeHtml(it.url || '')} &nbsp;·&nbsp; Key: ••••••••</div>
        </div>
      </div>
      <div class="inst-row2">
        <button class="${toggleClass}" onclick="toggleInstance('${kind}', ${idx})">${toggleLabel}</button>
        <div class="inst-actions" style="${contentDim}">
          <button class="btn sm" onclick="editInstance('${kind}', ${idx})">Edit</button>
          <button class="btn sm danger" onclick="deleteInstance('${kind}', ${idx})">Delete</button>
        </div>
      </div>
    </div>
  `}).join('');
}

let MODAL_KIND = '';
let MODAL_IDX = -1;
// _modalTestDone/_modalTestOk/_modalTestVersion — cache the result of a manual
// connection test fired from inside the Add/Edit modal. When the user clicks Save
// immediately after a successful test, saveModal() reuses the cached result instead
// of firing a redundant second request. Cleared by clearModalTest() on every modal open.
let _modalTestDone = false;
let _modalTestOk = null;
let _modalTestVersion = null;

function clearModalTest() {
  _modalTestDone = false;
  _modalTestOk = null;
  _modalTestVersion = null;
  const wrap = el('modalTestResult');
  if (wrap) wrap.classList.remove('visible');
}

// testModalConnection — builds a temporary config copy with the modal's current
// field values, POSTs it to /api/test-instance, then resolves the result by index
// first (existing instance) and by name as a fallback (new instance being added).
// Caches the outcome in _modalTestDone/_modalTestOk so saveModal() can skip a
// second request if the user saves immediately after a successful test.
async function testModalConnection() {
  const name = el('modalName').value.trim() || (MODAL_KIND === 'radarr' ? 'Radarr' : 'Sonarr');
  const url = el('modalUrl').value.trim();
  const key = el('modalKey').value.trim();
  const keyIsMasked = key.startsWith('••••••••');
  if (!url || (!key && !keyIsMasked)) { showAlert('Enter a URL and API key before testing.'); return; }

  const btn = el('modalTestBtn');
  const wrap = el('modalTestResult');
  const inner = el('modalTestResultInner');
  const dot = el('modalTestDot');
  const msg = el('modalTestMsg');

  btn.disabled = true;
  inner.className = 'modal-test-result-inner checking';
  dot.className = 'status-dot checking';
  msg.textContent = 'Testing connection\u2026';
  wrap.classList.add('visible');

  try {
    const tempInst = { name, url, key: keyIsMasked ? (MODAL_IDX >= 0 ? CFG.instances[MODAL_KIND][MODAL_IDX].key : '') : key };
    const tempCfg = JSON.parse(JSON.stringify(CFG));
    if (MODAL_IDX >= 0) {
      tempCfg.instances[MODAL_KIND][MODAL_IDX] = Object.assign({}, tempCfg.instances[MODAL_KIND][MODAL_IDX], tempInst);
    } else {
      tempCfg.instances[MODAL_KIND] = tempCfg.instances[MODAL_KIND] || [];
      tempCfg.instances[MODAL_KIND] = [...tempCfg.instances[MODAL_KIND], tempInst];
    }
    const out = await api('/api/test-instance', { method: 'POST', body: JSON.stringify({ kind: MODAL_KIND, instances: tempCfg.instances, update_status: false }) });
    const idx = MODAL_IDX >= 0 ? MODAL_IDX : (tempCfg.instances[MODAL_KIND].length - 1);
    const results = out.results[MODAL_KIND] || [];
    const match = results[idx] || results.find(r => r.name === name);
    if (match && match.ok) {
      _modalTestDone = true; _modalTestOk = true; _modalTestVersion = match.version || null;
      inner.className = 'modal-test-result-inner ok';
      dot.className = 'status-dot ok';
      msg.textContent = 'Connected' + (_modalTestVersion ? ' \u2014 ' + (MODAL_KIND === 'radarr' ? 'Radarr' : 'Sonarr') + ' v' + _modalTestVersion : '');
    } else {
      _modalTestDone = true; _modalTestOk = false;
      inner.className = 'modal-test-result-inner bad';
      dot.className = 'status-dot bad';
      msg.textContent = (match && match.error) ? match.error : 'Could not connect \u2014 check URL and API key';
    }
  } catch(e) {
    _modalTestDone = true; _modalTestOk = false;
    inner.className = 'modal-test-result-inner bad';
    dot.className = 'status-dot bad';
    msg.textContent = 'Could not connect \u2014 check URL and API key';
  }
  btn.disabled = false;
}

function checkModalUrlPath(val) {
  const warn = el('modalUrlWarn');
  const msg = el('modalUrlWarnMsg');
  if (!warn || !msg) return;
  if (!val) { warn.classList.remove('visible'); return; }
  try {
    const parsed = new URL(val);
    const path = parsed.pathname;
    const PAGE_PATTERNS = [/\/series\//i, /\/movie\//i, /\/movies\//i, /\/calendar/i, /\/activity/i, /\/wanted/i, /\/settings/i, /\/system/i, /\/history/i, /\.[a-z]{2,4}$/i];
    const isPagePath = PAGE_PATTERNS.some(p => p.test(path));
    const hasDeepPath = path.split('/').filter(Boolean).length > 1;
    if (isPagePath) {
      msg.innerHTML = `⚠️ URL appears to include a page path. The instance URL should end at the port — e.g. <code style="background:rgba(91,114,245,.12);border:1px solid rgba(91,114,245,.2);border-radius:4px;padding:1px 5px;font-size:11px;color:var(--accent-lt)">${parsed.origin}</code>`;
      warn.classList.add('visible');
    } else if (hasDeepPath) {
      msg.innerHTML = `⚠️ URL includes a subpath. If this is a reverse proxy base URL that's fine — otherwise it should end at the port.`;
      warn.classList.add('visible');
    } else {
      warn.classList.remove('visible');
    }
  } catch(e) {
    warn.classList.remove('visible');
  }
}

function openModal(kind, idx) {
  MODAL_KIND = kind;
  MODAL_IDX = idx;
  const isEdit = idx >= 0;
  el('modalTitle').textContent = (isEdit ? 'Edit ' : 'Add ') + (kind === 'radarr' ? 'Radarr' : 'Sonarr') + ' Instance';
  const it = isEdit ? CFG.instances[kind][idx] : {name:'', url:'', key:''};
  el('modalName').value = it.name || '';
  el('modalUrl').value = it.url || '';
  const isMasked = (it.key || '').startsWith('••••••••');
  el('modalKey').value = it.key || '';
  el('modalKey').placeholder = isMasked ? 'Leave unchanged or enter a new key' : 'Instance API Key';
  el('modalName').placeholder = kind === 'radarr' ? 'Example: Radarr' : 'Example: Sonarr';
  el('modalUrl').placeholder = kind === 'radarr' ? 'Example: http://192.168.1.10:7878' : 'Example: http://192.168.1.10:8989';
  el('modalKey').type = 'password';
  el('keyToggleBtn').textContent = 'Show';
  el('modalKeyLabel').textContent = isEdit ? 'API Key (Masked)' : 'API Key (Masked After Save)';
  el('instModal').style.display = 'flex';
  clearModalTest();
  // Clear URL warning on fresh open and check if editing an existing URL
  const urlWarn = el('modalUrlWarn');
  if (urlWarn) urlWarn.classList.remove('visible');
  if (it.url) checkModalUrlPath(it.url);
  setTimeout(() => el('modalName').focus(), 50);
}

function closeModal(e) {
  if (e.target === el('instModal')) closeModalDirect();
}

function closeModalDirect() {
  el('instModal').style.display = 'none';
  clearModalTest();
}

function toggleKeyVis() {
  const inp = el('modalKey');
  const btn = el('keyToggleBtn');
  if (inp.type === 'password') { inp.type = 'text'; btn.textContent = 'Hide'; }
  else { inp.type = 'password'; btn.textContent = 'Show'; }
}

async function saveModal() {
  const name = el('modalName').value.trim();
  const url = el('modalUrl').value.trim();
  const key = el('modalKey').value.trim();
  const keyIsMasked = key.startsWith('••••••••');
  if (!name || !url || (!key && MODAL_IDX < 0)) { showAlert('All fields are required.'); return; }
  if (!key && MODAL_IDX >= 0) { showAlert('API key is required.'); return; }
  CFG.instances = CFG.instances || {radarr:[], sonarr:[]};
  if (MODAL_IDX >= 0) {
    const existing = CFG.instances[MODAL_KIND][MODAL_IDX];
    CFG.instances[MODAL_KIND][MODAL_IDX] = {...existing, name, url, key, enabled: existing.enabled};
  } else {
    CFG.instances[MODAL_KIND].push({name, url, key});
  }
  closeModalDirect();
  renderInstances(MODAL_KIND);
  el('saveMsg').textContent = MODAL_IDX >= 0 ? 'Unsaved Changes' : 'Unsaved Changes';
  el('saveMsg').className = 'msg unsaved';

  // If a manual test was already run on these credentials use the cached
  // result directly — no second request needed.
  const idx = MODAL_IDX >= 0 ? MODAL_IDX : CFG.instances[MODAL_KIND].length - 1;
  const dot = el(`sdot-${MODAL_KIND}-${idx}`);
  if (_modalTestDone) {
    if (dot) dot.className = 'status-dot ' + (_modalTestOk ? 'ok' : 'bad');
  } else {
    // Silent post-apply test — same as existing behaviour
    if (dot) dot.className = 'status-dot checking';
    try {
      const testPayload = { kind: MODAL_KIND, instances: CFG.instances };
      const out = await api('/api/test-instance', {method:'POST', body: JSON.stringify({...testPayload, update_status: true})});
      const results = out.results[MODAL_KIND] || [];
      const match = results.find(r => r.name === name);
      if (dot && match) dot.className = 'status-dot ' + (match.ok ? 'ok' : 'bad');
    } catch(e) {
      if (dot) dot.className = 'status-dot bad';
    }
  }
}

function addInstance(kind) {
  openModal(kind, -1);
}

function editInstance(kind, idx) {
  openModal(kind, idx);
}

// toggleInstance — enables or disables one instance via /api/instance/toggle.
// Does a surgical DOM update (touching only the toggled card, never rebuilding the list)
// then fires a delayed health check for newly-enabled instances. Adds the dot key to
// TOGGLE_IN_PROGRESS while waiting so the 5-second poll doesn't race the update.
async function toggleInstance(kind, idx) {
  const dotKey = `${kind}-${idx}`;
  try {
    const out = await api('/api/instance/toggle', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({kind, idx})});
    const enabled = out.enabled;
    CFG.instances[kind][idx].enabled = enabled;

    // Surgical update — only touch the card that was toggled, never rebuild the list
    const card = el(`instcard-${kind}-${idx}`);
    if (card) {
      const row1 = card.querySelector('.inst-row1');
      const actions = card.querySelector('.inst-actions');
      const toggleBtn = card.querySelector('.inst-row2 button');
      const dim = enabled ? '' : 'opacity:0.45;';
      if (row1) row1.style.opacity = enabled ? '' : '0.45';
      if (actions) actions.style.opacity = enabled ? '' : '0.45';
      if (toggleBtn) {
        toggleBtn.textContent = enabled ? 'Disable' : 'Enable';
        toggleBtn.className = enabled ? 'btn sm' : 'btn sm primary';
      }
    }

    const dot = el(`sdot-${dotKey}`);
    if (dot) {
      if (!enabled) {
        dot.className = 'status-dot disabled';
      } else {
        TOGGLE_IN_PROGRESS.add(dotKey);
        dot.className = 'status-dot checking';
        setTimeout(async () => {
          try {
            const st = await api('/api/status');
            const health = st.instance_health || {};
            const name = CFG.instances[kind][idx]?.name;
            const state = health[`${kind}|${name}`];
            const d = el(`sdot-${dotKey}`);
            if (d) {
              if (state === 'ok') d.className = 'status-dot ok';
              else if (state === 'bad') d.className = 'status-dot bad';
              else d.className = 'status-dot';
            }
          } catch(e) {
            console.warn('[toggleInstance] dot update failed:', e.message);
          } finally {
            TOGGLE_IN_PROGRESS.delete(dotKey);
          }
        }, 1400);
      }
    }
  } catch(e) {
    TOGGLE_IN_PROGRESS.delete(dotKey);
    showAlert('Toggle failed: ' + e.message);
  }
}

async function deleteInstance(kind, idx) {
  if (!await showConfirm('Delete Instance', 'Are you sure you want to delete this instance?', 'Delete', true)) return;
  CFG.instances[kind].splice(idx, 1);
  renderInstances(kind);
  el('saveMsg').textContent = 'Unsaved Changes';
  el('saveMsg').className = 'msg unsaved';
}

function fadeMsg(id) {
  const el_ = el(id);
  clearTimeout(el_._fadeTimer);
  el_.classList.remove('fade');
  el_._fadeTimer = setTimeout(() => el_.classList.add('fade'), 4000);
}

async function saveAll() {
  try {
    await api('/api/config', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(CFG)});
    await loadAll();
    await new Promise(r => setTimeout(r, 400));
    el('saveMsg').textContent = 'Saved'; el('saveMsg').className = 'msg ok'; fadeMsg('saveMsg');
  } catch(e) {
    el('saveMsg').textContent = 'Save failed: ' + e.message; el('saveMsg').className = 'msg err';
  }
}

// testConnections — tests all configured instances via /api/test. Runs a minimum
// 2-second display delay (Promise.all race) so the checking dots are visible before
// results arrive. Handles disabled instances separately (dot stays grey). On failure,
// auto-fades the results panel after 4 seconds so it doesn't linger.
async function testConnections() {
  el('testResults').style.display = 'none';
  el('testResultsInner').innerHTML = '';

  // Only pulse checking on enabled instances
  ['radarr','sonarr'].forEach(kind => {
    (CFG?.instances?.[kind] || []).forEach((inst, idx) => {
      const dot = el(`sdot-${kind}-${idx}`);
      if (!dot) return;
      dot.className = inst.enabled !== false ? 'status-dot checking' : 'status-dot disabled';
    });
  });

  try {
    const [out] = await Promise.all([
      api('/api/test', {method:'POST'}),
      new Promise(r => setTimeout(r, 2000))
    ]);
    const allResults = [...(out.results.radarr||[]), ...(out.results.sonarr||[])];

    ['radarr','sonarr'].forEach(kind => {
      (out.results[kind]||[]).forEach((r, idx) => {
        const dot = el(`sdot-${kind}-${idx}`);
        if (!dot) return;
        if (r.disabled) { dot.className = 'status-dot disabled'; return; }
        dot.className = 'status-dot ' + (r.ok ? 'ok' : 'bad');
      });
    });

    const failures = allResults.filter(r => !r.ok);
    if (failures.length > 0) {
      el('testResultsInner').innerHTML = failures.map(r => `
        <div class="test-card bad">
          <span class="test-icon">✗</span>
          <div>
            <div class="tc-name">${escapeHtml(r.name)}</div>
            <div class="tc-detail">${r.error && r.error.length < 80 ? escapeHtml(r.error) : 'Could not connect — check the URL and API key'}</div>
          </div>
        </div>
      `).join('');
      el('testResults').style.display = 'block';
      el('testResults').style.opacity = '1';
      setTimeout(() => {
        el('testResults').style.transition = 'opacity 0.8s ease';
        el('testResults').style.opacity = '0';
        setTimeout(() => {
          el('testResults').style.display = 'none';
          el('testResults').style.transition = '';
          el('testResults').style.opacity = '1';
        }, 800);
      }, 4000);
    }

  } catch(e) {
    el('testResultsInner').innerHTML = `<p class="help" style="color:var(--bad)">Test failed: ${escapeHtml(e.message)}</p>`;
    el('testResults').style.display = 'block';
    document.querySelectorAll('.status-dot').forEach(d => { d.className = 'status-dot bad'; });
  }
}

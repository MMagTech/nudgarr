// ── Portrait History tab and Imports sheet ─────────────────────────────────
// mSwitchExclTab, mOpenExclusions, mCloseExclusions, mLoadExclusions,
// mExclRemove, mLoadExclHistory, mExclAdd, mOpenImports, mCloseImports,
// mLoadImports

// ── History tab ────────────────────────────────────────────────────────────

let M_EXCL_DATA = [];
let M_HIST_DATA = [];
let M_HIST_CURRENT_PANE = 'history';

function mSwitchExclTab(pane) {
  M_HIST_CURRENT_PANE = pane;
  ['history','add','excluded'].forEach(p => {
    const paneEl = document.getElementById('m-hist-pane-' + p);
    const tabEl = document.getElementById('m-htab-' + p);
    if (paneEl) paneEl.style.display = p === pane ? '' : 'none';
    if (tabEl) tabEl.classList.toggle('m-inner-tab-active', p === pane);
  });
  if (pane === 'history') mLoadExclHistory();
  if (pane === 'add') mLoadExclHistory();
  if (pane === 'excluded') mLoadExclusions();
}

// mOpenExclusions / mCloseExclusions kept for API compatibility
function mOpenExclusions() {
  mSwitchTab('history');
  mSwitchExclTab('excluded');
}

function mCloseExclusions() {}

async function mLoadExclusions() {
  const listEl = document.getElementById('m-excl-list');
  const countEl = document.getElementById('m-excl-count');
  if (!listEl) return;
  try {
    const data = await api('/api/exclusions');
    M_EXCL_DATA = data || [];
    if (countEl) countEl.textContent = M_EXCL_DATA.length;
    if (!M_EXCL_DATA.length) {
      listEl.innerHTML = '<p class="m-empty">No exclusions yet.</p>';
      return;
    }
    listEl.innerHTML = M_EXCL_DATA.map(e => {
      const title = escapeHtml(e.title || '');
      return '<div class="m-hist-row">'
        + '<span class="m-hist-title">' + title + '</span>'
        + '<button class="m-excl-remove" data-title="' + escapeHtml(e.title || '') + '">Remove</button>'
        + '</div>';
    }).join('');
    listEl.querySelectorAll('.m-excl-remove').forEach(btn => {
      btn.addEventListener('click', () => { mBtnPress(btn); mExclRemove(btn.dataset.title); });
    });
  } catch(err) {
    listEl.innerHTML = '<p class="m-empty m-empty-err">Failed to load exclusions.</p>';
  }
}

async function mExclRemove(title) {
  mHaptic(60);
  const listEl = document.getElementById('m-excl-list');
  if (listEl) {
    listEl.querySelectorAll('.m-hist-row').forEach(row => {
      const t = row.querySelector('.m-hist-title');
      if (t && t.textContent.trim() === title) row.classList.add('m-fading');
    });
  }
  await new Promise(r => setTimeout(r, 300));
  try {
    await api('/api/exclusions/remove', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({title})});
    await mLoadExclusions();
  } catch(e) {}
}

async function mLoadExclHistory(silent) {
  const histEl = document.getElementById('m-excl-hist');
  const histListEl = document.getElementById('m-hist-list');
  if (!histEl && !histListEl) return;
  try {
    const items = await api('/api/state/items?app=&instance=&offset=0&limit=500');
    M_HIST_DATA = (items.items || []);
    const exclSet = new Set(M_EXCL_DATA.map(e => (e.title || '').toLowerCase()));

    // History pane — all searched items
    if (histListEl) {
      if (!M_HIST_DATA.length) {
        histListEl.innerHTML = '<p class="m-empty">No search history yet.</p>';
      } else {
        histListEl.innerHTML = '<div class="m-hist-card">'
          + M_HIST_DATA.slice(0, 200).map(it => {
            const title = it.title || it.key || '';
            const count = it.search_count > 1 ? '\u00d7' + it.search_count : '';
            const appLabel = it.app ? (it.app === 'radarr' ? '<span class="m-app-badge" style="background:rgba(91,114,245,.15);color:var(--accent-lt);border:1px solid rgba(91,114,245,.25)">Radarr</span>' : '<span class="m-app-badge" style="background:rgba(34,197,94,.1);color:#4ade80;border:1px solid rgba(34,197,94,.2)">Sonarr</span>') : '';
            const last = it.last_searched ? fmtTime(it.last_searched) : '';
            return '<div class="m-hist-item">'
              + '<div class="m-hist-item-left">'
              + '<div class="m-hist-item-title"'
              + ' data-app="' + escapeHtml(it.app || '') + '"'
              + ' data-instance="' + escapeHtml(it.instance_name || it.instance || '') + '"'
              + ' data-item-id="' + escapeHtml(it.item_id || '') + '"'
              + ' data-series-id="' + escapeHtml(it.series_id || '') + '">'
              + escapeHtml(title) + '</div>'
              + '<div class="m-hist-item-meta">' + appLabel + (it.instance ? ' <span>' + escapeHtml(it.instance) + '</span>' : '') + (count ? ' <span>' + count + '</span>' : '') + (last ? ' <span>' + escapeHtml(last) + '</span>' : '') + '</div>'
              + '</div></div>';
          }).join('')
          + '</div>';
        histListEl.querySelectorAll('.m-hist-item-title[data-app]').forEach(el => {
          mAddArrLinkHandler(el, el.dataset.app, el.dataset.instance, el.dataset.itemId, el.dataset.seriesId);
        });
      }
    }

    // Add pane — items not yet excluded
    if (histEl) {
      const filtered = M_HIST_DATA.filter(it => {
        const t = (it.title || it.key || '').toLowerCase();
        return t && !exclSet.has(t);
      });
      if (!filtered.length) {
        histEl.innerHTML = '<p class="m-empty">No history to exclude.</p>';
        return;
      }
      histEl.innerHTML = '<div class="m-hist-card">'
        + filtered.map(it => {
          const title = it.title || it.key || '';
          const count = it.search_count > 1 ? '\u00d7' + it.search_count : '';
          const inst = it.instance ? escapeHtml(it.instance) : '';
          const last = it.last_searched ? fmtTime(it.last_searched) : '';
          return '<div class="m-hist-item">'
            + '<div class="m-hist-item-left">'
            + '<div class="m-hist-item-title">' + escapeHtml(title) + '</div>'
            + '<div class="m-hist-item-meta">' + (inst ? '<span>' + inst + '</span>' : '') + (count ? '<span>' + count + '</span>' : '') + (last ? '<span>' + last + '</span>' : '') + '</div>'
            + '</div>'
            + '<button class="m-hist-add" data-title="' + escapeHtml(title) + '">+ Exclude</button>'
            + '</div>';
        }).join('')
        + '</div>';
      histEl.querySelectorAll('.m-hist-add').forEach(btn => {
        btn.addEventListener('click', () => { mBtnPress(btn); mExclAdd(btn.dataset.title); });
      });
    }
  } catch(err) {
    if (histListEl) histListEl.innerHTML = '<p class="m-empty m-empty-err">Failed to load history.</p>';
    if (histEl) histEl.innerHTML = '<p class="m-empty m-empty-err">Failed to load history.</p>';
  }
}

async function mExclAdd(title) {
  mHaptic(60);
  const histEl = document.getElementById('m-excl-hist');
  if (histEl) {
    histEl.querySelectorAll('.m-hist-item').forEach(row => {
      const t = row.querySelector('.m-hist-item-title');
      if (t && t.textContent.trim() === title) row.classList.add('m-fading');
    });
  }
  await new Promise(r => setTimeout(r, 300));
  try {
    await api('/api/exclusions/add', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({title})});
    await mLoadExclusions();
    await mLoadExclHistory(true);
  } catch(e) {}
}

// ── Imports sheet ──────────────────────────────────────────────────────────

async function mOpenImports(type) {
  const titleEl = document.getElementById('m-imports-sheet-title');
  const bodyEl = document.getElementById('m-imports-sheet-body');
  if (titleEl) titleEl.textContent = type === 'movies' ? 'Movies (Imported)' : 'Episodes (Imported)';
  if (bodyEl) bodyEl.innerHTML = '<p class="m-empty">Loading\u2026</p>';
  mSheetOpen('m-imports-sheet');
  mSheetDrag('m-imports-handle', 'm-imports-sheet', mCloseImports);
  await mLoadImports(type);
}

function mCloseImports() {
  mSheetClose('m-imports-sheet');
}

async function mLoadImports(type) {
  const bodyEl = document.getElementById('m-imports-sheet-body');
  if (!bodyEl) return;
  try {
    const data = await api('/api/stats?offset=0&limit=200');
    const app = type === 'movies' ? 'radarr' : 'sonarr';
    const entries = (data.entries || []).filter(e => e.app === app);
    if (!entries.length) {
      bodyEl.innerHTML = '<p class="m-empty">No confirmed imports yet.</p>';
      return;
    }
    bodyEl.innerHTML = entries.map(e => {
      const title = escapeHtml(e.title || e.item_id || '\u2014');
      const date = e.imported_ts ? fmtTime(e.imported_ts) : '';
      const tagClass = e.type === 'Acquired' ? 'tag acquired' : 'tag';
      const iterSuffix = (e.iteration && e.iteration > 1) ? ' \u00d7' + e.iteration : '';
      const tagHtml = e.type ? '<span class="' + tagClass + '">' + escapeHtml(e.type) + escapeHtml(iterSuffix) + '</span>' : '';
      const history = e.quality_history || [];
      const latest = history.length ? history[history.length - 1] : null;
      const qualityHtml = latest
        ? '<div class="m-import-quality">'
          + (latest.quality_from ? escapeHtml(latest.quality_from) + ' <span class="m-import-quality-arrow">\u2192</span> ' : '<span class="m-import-quality-arrow">\u2192</span> ')
          + escapeHtml(latest.quality_to || '')
          + '</div>'
        : '';
      return '<div class="m-import-row">'        + '<div class="m-import-row-top">'        + '<div class="m-import-row-title">' + title + '</div>'        + '<span class="m-import-row-date">' + escapeHtml(date) + '</span>'        + '</div>'        + '<div class="m-import-row-bottom">' + tagHtml + qualityHtml + '</div>'        + '</div>';
    }).join('');
  } catch(err) {
    bodyEl.innerHTML = '<p class="m-empty m-empty-err">Failed to load imports.</p>';
  }
}


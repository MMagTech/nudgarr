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
  ['history','excluded'].forEach(p => {
    const paneEl = document.getElementById('m-hist-pane-' + p);
    const tabEl = document.getElementById('m-htab-' + p);
    if (paneEl) paneEl.style.display = p === pane ? '' : 'none';
    if (tabEl) tabEl.classList.toggle('m-inner-tab-active', p === pane);
  });
  if (pane === 'history') mLoadExclHistory();
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

    // History pane — color-coded instance pill, ×N count pill, inline ⊘ exclude
    if (histListEl) {
      if (!M_HIST_DATA.length) {
        histListEl.innerHTML = '<p class="m-empty">No search history yet.</p>';
      } else {
        histListEl.innerHTML = '<div class="m-hist-card">'
          + M_HIST_DATA.slice(0, 200).map(it => {
            const title = it.title || it.key || '';
            const isRadarr = it.app === 'radarr';
            const instStyle = isRadarr
              ? 'background:rgba(91,114,245,.15);color:var(--accent-lt);border:1px solid rgba(91,114,245,.25)'
              : 'background:rgba(34,197,94,.1);color:#4ade80;border:1px solid rgba(34,197,94,.2)';
            const instPill = it.instance
              ? '<span style="font-size:10px;font-weight:600;padding:2px 7px;border-radius:5px;' + instStyle + '">' + escapeHtml(it.instance) + '</span>'
              : '';
            const countPill = it.search_count > 1
              ? '<span style="font-size:10px;font-weight:600;color:var(--text-dim);background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);border-radius:5px;padding:1px 6px">\u00d7' + it.search_count + '</span>'
              : '';
            const last = it.last_searched ? fmtTimePadded(it.last_searched) : '';
            const excluded = exclSet.has((title).toLowerCase());
            return '<div class="m-hist-item" style="display:flex;align-items:center;justify-content:space-between;gap:8px;padding:10px 16px;border-bottom:1px solid rgba(255,255,255,.05)">'
              + '<div style="flex:1;min-width:0">'
              + '<div class="m-hist-item-title"'
              + ' data-app="' + escapeHtml(it.app || '') + '"'
              + ' data-instance="' + escapeHtml(it.instance_name || it.instance || '') + '"'
              + ' data-item-id="' + escapeHtml(it.item_id || '') + '"'
              + ' data-series-id="' + escapeHtml(it.series_id || '') + '"'
              + ' style="font-size:13px;color:var(--accent-lt);font-weight:500;margin-bottom:3px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'
              + escapeHtml(title) + '</div>'
              + '<div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">'
              + instPill + countPill
              + (last ? '<span style="font-size:11px;color:var(--muted)">' + escapeHtml(last) + '</span>' : '')
              + '</div></div>'
              + (excluded ? '' : '<button class="m-excl-inline" data-title="' + escapeHtml(title) + '" style="font-size:12px;color:var(--muted);border:1px solid rgba(255,255,255,.1);background:transparent;border-radius:5px;padding:3px 8px;cursor:pointer;flex-shrink:0">\u2298</button>')
              + '</div>';
          }).join('')
          + '</div>';
        histListEl.querySelectorAll('.m-hist-item-title[data-app]').forEach(el => {
          mAddArrLinkHandler(el, el.dataset.app, el.dataset.instance, el.dataset.itemId, el.dataset.seriesId);
        });
        histListEl.querySelectorAll('.m-excl-inline').forEach(btn => {
          btn.addEventListener('click', () => { mBtnPress(btn); mExclAdd(btn.dataset.title); });
        });
      }
    }
  } catch(err) {
    if (histListEl) histListEl.innerHTML = '<p class="m-empty m-empty-err">Failed to load history.</p>';
  }
}

async function mExclAdd(title) {
  mHaptic(60);
  const histListEl = document.getElementById('m-hist-list');
  if (histListEl) {
    histListEl.querySelectorAll('.m-hist-item').forEach(row => {
      const btn = row.querySelector('.m-excl-inline');
      if (btn && btn.dataset.title === title) row.classList.add('m-fading');
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

const DATE_COL_W = 88;
const SCROLL_PX_PER_SEC = 18;
const SCROLL_PAUSE = 2;

function _applyQualityTicker(wrap) {
  const inner = wrap.querySelector('.m-q-inner');
  if (!inner) return;
  requestAnimationFrame(() => {
    const overflow = inner.scrollWidth - DATE_COL_W;
    if (overflow <= 2) return;
    const scrollDur = (overflow / SCROLL_PX_PER_SEC).toFixed(2);
    const total = (SCROLL_PAUSE + parseFloat(scrollDur) + SCROLL_PAUSE).toFixed(2);
    const pct1 = ((SCROLL_PAUSE / total) * 100).toFixed(1);
    const pct2 = (((SCROLL_PAUSE + parseFloat(scrollDur)) / total) * 100).toFixed(1);
    const name = 'mq' + Math.random().toString(36).slice(2);
    const style = document.createElement('style');
    style.textContent = '@keyframes ' + name + '{'
      + '0%{transform:translateX(0)}'
      + pct1 + '%{transform:translateX(0)}'
      + pct2 + '%{transform:translateX(-' + overflow + 'px)}'
      + '100%{transform:translateX(-' + overflow + 'px)}'
      + '}';
    document.head.appendChild(style);
    inner.style.animation = name + ' ' + total + 's ease-in-out infinite alternate';
  });
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
      const date = e.imported_ts ? fmtTimePadded(e.imported_ts) : '';
      const isAcq = e.type === 'Acquired';
      const tagStyle = isAcq
        ? 'background:rgba(34,197,94,.1);color:#4ade80;border:1px solid rgba(34,197,94,.2)'
        : 'background:rgba(91,114,245,.12);color:#a0b0ff;border:1px solid rgba(91,114,245,.22)';
      const tagHtml = e.type
        ? '<span style="font-size:10px;font-weight:700;padding:2px 8px;border-radius:5px;white-space:nowrap;' + tagStyle + '">' + escapeHtml(e.type) + '</span>'
        : '';
      const countPill = (e.iteration && e.iteration > 1)
        ? '<span style="font-size:10px;font-weight:600;color:var(--text-dim);background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);border-radius:5px;padding:1px 6px;white-space:nowrap">\u00d7' + e.iteration + '</span>'
        : '';
      const history = e.quality_history || [];
      const latest = history.length ? history[history.length - 1] : null;
      const qualityStr = latest
        ? (latest.quality_from ? escapeHtml(latest.quality_from) + ' \u2192 ' : '\u2192 ') + escapeHtml(latest.quality_to || '')
        : '';
      return '<div class="m-import-row" style="padding:10px 16px;border-bottom:1px solid rgba(255,255,255,.05)">'
        + '<div style="display:flex;align-items:baseline;gap:6px;margin-bottom:2px">'
        + '<div style="font-size:13px;color:var(--text-dim);font-weight:500;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + title + '</div>'
        + '<div style="font-size:11px;color:var(--muted);white-space:nowrap;width:' + DATE_COL_W + 'px;text-align:right;flex-shrink:0">' + escapeHtml(date) + '</div>'
        + '</div>'
        + '<div style="font-size:11px;color:var(--muted);margin-bottom:3px">' + escapeHtml(e.instance || '') + '</div>'
        + '<div style="display:flex;align-items:center;gap:6px">'
        + '<div style="display:flex;align-items:center;gap:6px;flex:1;min-width:0">' + tagHtml + countPill + '</div>'
        + (qualityStr ? '<div class="m-q-wrap" style="width:' + DATE_COL_W + 'px;flex-shrink:0;overflow:hidden"><span class="m-q-inner" style="font-size:10px;color:var(--muted);font-family:monospace;white-space:nowrap;display:inline-block">' + qualityStr + '</span></div>' : '')
        + '</div>'
        + '</div>';
    }).join('');
    bodyEl.querySelectorAll('.m-q-wrap').forEach(_applyQualityTicker);
  } catch(err) {
    bodyEl.innerHTML = '<p class="m-empty m-empty-err">Failed to load imports.</p>';
  }
}


// ── Portrait state ─────────────────────────────────────────────────────────

let M_TAB = 'home';
let M_OPEN_SWEEP = null;
let STATUS_CACHE = {};

// ── Tab switching ──────────────────────────────────────────────────────────

function mSwitchTab(name) {
  if (name === 'sweep') {
    const radarr = CFG?.instances?.radarr || [];
    const sonarr = CFG?.instances?.sonarr || [];
    if (!radarr.length && !sonarr.length) { mSwitchTab('instances'); return; }
  }
  document.querySelectorAll('.m-tab').forEach(t => t.classList.remove('m-active'));
  document.querySelectorAll('.m-nav-item').forEach(n => n.classList.remove('m-active'));
  const tab = document.getElementById('m-' + name);
  const nav = document.getElementById('m-nav-' + name);
  if (tab) tab.classList.add('m-active');
  if (nav) nav.classList.add('m-active');
  M_TAB = name;
  if (name === 'sweep') mRenderSweep();
  if (name === 'instances') mRenderInstances();
  if (name === 'history') {
    mLoadExclHistory();
    // Acknowledge all unacknowledged auto-exclusions when the user navigates
    // to History, clearing the nav badge. Mirrors onAutoExclBadgeClick() on
    // desktop which acknowledges on badge click before showing the history tab.
    const badge = document.getElementById('m-autoexcl-badge');
    if (badge && badge.style.display !== 'none') {
      api('/api/exclusions/acknowledge', {method: 'POST'}).catch(() => {});
      badge.style.display = 'none';
    }
  }
}

// ── Swipe between portrait tabs ────────────────────────────────────────────

(function() {
  const ui = document.getElementById('mobile-ui');
  if (!ui) return;
  const TAB_ORDER = ['home', 'sweep', 'history', 'settings'];
  let sx = null, sy = null;
  ui.addEventListener('touchstart', e => {
    sx = e.touches[0].clientX;
    sy = e.touches[0].clientY;
  }, {passive: true});
  ui.addEventListener('touchend', e => {
    if (sx === null) return;
    const dx = e.changedTouches[0].clientX - sx;
    const dy = e.changedTouches[0].clientY - sy;
    if (Math.abs(dx) >= 30 && Math.abs(dx) >= Math.abs(dy) * 1.5) {
      const idx = TAB_ORDER.indexOf(M_TAB);
      if (dx < 0 && idx < TAB_ORDER.length - 1) mSwitchTab(TAB_ORDER[idx + 1]);
      if (dx > 0 && idx > 0) mSwitchTab(TAB_ORDER[idx - 1]);
    }
    sx = null;
  }, {passive: true});
})();

// ── Orientation and desktop-override state ─────────────────────────────────
// Declared at module scope so lsSwitchToDesktop() in ui-mobile-landscape-exec.js
// can read and write LS_DESKTOP_OVERRIDE, and so checkOrientation() is globally
// callable from the resize/orientationchange listeners in the init block below.

const wrap        = document.querySelector('.wrap');
const mobileUi    = document.getElementById('mobile-ui');
const landscapeUi = document.getElementById('landscape-ui');
// MOBILE_UI_STYLE / LS_UI_STYLE are intentionally separate constants even though
// they appear identical. MOBILE_UI_STYLE is applied to #mobile-ui (portrait shell)
// and LS_UI_STYLE is applied to #landscape-ui in checkOrientation(). Keeping them
// separate makes each usage site explicit and allows them to diverge independently.
const MOBILE_UI_STYLE = 'display:flex; flex-direction:column; width:100%; height:100vh; height:100dvh; position:fixed; top:0; left:0; overflow:hidden;';
const LS_UI_STYLE     = 'display:flex; flex-direction:column; width:100%; height:100vh; height:100dvh; position:fixed; top:0; left:0; overflow:hidden;';
let LS_DESKTOP_OVERRIDE = sessionStorage.getItem('nudgarr_desktop_override') === '1';

function checkOrientation() {
  const isLandscape = window.innerWidth > window.innerHeight;
  if (!isLandscape) {
    LS_DESKTOP_OVERRIDE = false;
    sessionStorage.removeItem('nudgarr_desktop_override');
    if (wrap) wrap.style.removeProperty('display');
    if (landscapeUi) landscapeUi.style.display = 'none';
    if (mobileUi) mobileUi.style.cssText = MOBILE_UI_STYLE;
  } else if (LS_DESKTOP_OVERRIDE) {
    if (mobileUi) mobileUi.style.display = 'none';
    if (landscapeUi) landscapeUi.style.display = 'none';
    if (wrap) wrap.style.setProperty('display','block','important');
  } else {
    if (mobileUi) mobileUi.style.display = 'none';
    if (wrap) wrap.style.display = 'none';
    if (landscapeUi) landscapeUi.style.cssText = LS_UI_STYLE;
    lsPopulate();
  }
}

// ── Mobile init ────────────────────────────────────────────────────────────

if (MOBILE) {
  checkOrientation();
  window.addEventListener('orientationchange', () => {
    if (wrap) wrap.style.setProperty('display','none','important');
    if (mobileUi) mobileUi.style.display = 'none';
    if (landscapeUi) landscapeUi.style.display = 'none';
    setTimeout(checkOrientation, 100);
  });
  window.addEventListener('resize', checkOrientation);

  loadAll().then(async () => {
    const st = await api('/api/status');
    STATUS_CACHE = st.instance_health || {};
    mUpdateHome(CFG, st);
    if (typeof lsUpdateContainerTime === 'function') lsUpdateContainerTime(st.container_time);
    mRenderInstances();
    mPopulateSettings();
    mOvUpdateSubLabels();
    await refreshSweep();
    mRenderSweep();
    try {
      const stats = await api('/api/stats?offset=0&limit=1');
      const movEl = document.getElementById('m-movies-total');
      const showEl = document.getElementById('m-shows-total');
      if (movEl) movEl.textContent = stats.movies_total ?? '\u2014';
      if (showEl) showEl.textContent = stats.shows_total ?? '\u2014';
    } catch(e) {
      console.warn('[mobile] stats fetch failed:', e.message);
    }
    mInitRunBtn();
    mInitUpdateBanner();
    // Fetch initial auto-exclusion badge count on load so the nav badge is
    // accurate before the first poll cycle fires at 5s.
    mRefreshMobileAutoExclBadge();
    maybeShowOnboarding();
    if (!CFG || CFG.onboarding_complete) maybeShowWhatsNew();
    if (typeof lsPopulate === 'function') lsPopulate();
  });

  setInterval(mPollCycle, 5000);
}

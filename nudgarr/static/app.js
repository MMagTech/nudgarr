// Nudgarr v5 — app.js
// Alpine.js data object + shared utilities.
// All panel rendering, API calls, and state management live here.

// ── Tab migration — maps removed v4 tab names to v5 equivalents ───────────────
const TAB_MIGRATION_V5 = {
  'history':   'library',
  'imports':   'library',
  'cf-scores': 'library',
};

const VALID_TABS_V5 = [
  'sweep', 'library', 'intel', 'instances', 'pipelines',
  'overrides', 'filters', 'settings', 'notifications', 'advanced',
];

// ── Main Alpine data function ─────────────────────────────────────────────────
function nudgarr() {
  return {

    // ── Core state ───────────────────────────────────────────────────────────
    CFG: null,
    panel: 'sweep',
    sidebarOpen: false,
    sweeping: false,
    schedulerEnabled: true,
    autoMode: 'AUTO',
    lastRunUtc: null,
    nextRunUtc: null,
    lastSkippedQueueDepthUtc: null,

    // ── Instance counts ──────────────────────────────────────────────────────
    radarrInstances: [],
    sonarrInstances: [],
    get radarrInstanceCount() { return this.radarrInstances.length; },
    get sonarrInstanceCount() { return this.sonarrInstances.length; },

    // ── Feature flags ────────────────────────────────────────────────────────
    overridesEnabled: false,
    cfScoreEnabled: false,
    authEnabled: false,
    showSupportLink: false,

    // ── Unsaved change tracking ──────────────────────────────────────────────
    unsaved: {
      settings: false, pipelines: false, overrides: false,
      notifications: false, advanced: false, filters: false,
    },

    // ── Modal state ──────────────────────────────────────────────────────────
    modal: null,
    clearExclOpt: null,
    confirmAction: null,
    confirmTitle: '',
    confirmMsg: '',
    confirmLabel: '',
    alertMsg: '',
    alertType: 'error',
    modalMode: 'add',
    modalIdx: -1,

    // ── Overrides info seen flag ─────────────────────────────────────────────
    overridesInfoSeen: false,

    // ── Onboarding state ─────────────────────────────────────────────────────
    onboardingStep: 0,
    get onboardingTotal()   { return 8; },
    get onboardingIsFirst() { return this.onboardingStep === 0; },
    get onboardingIsLast()  { return this.onboardingStep === 7; },
    onboardingNext() { if (this.onboardingStep < 7) this.onboardingStep++; else this.completeOnboarding(); },
    onboardingPrev() { if (this.onboardingStep > 0) this.onboardingStep--; },
    onboardingGoto(step) { if (step >= 0 && step <= 7) this.onboardingStep = step; },

    async completeOnboarding() {
      this.closeModal();
      try { await this.api('/api/onboarding/complete', { method: 'POST' }); } catch (_) {}
      if (this.CFG) this.CFG.onboarding_complete = true;
      this.panel = 'instances';
    },

    // ── Day pills (Quiet Hours day-of-week selector) ──────────────────────────
    isDayActive(i) { return (this.quietDays || []).includes(i); },
    toggleDay(i) {
      const days = [...(this.quietDays || [])];
      const idx = days.indexOf(i);
      if (idx >= 0) days.splice(idx, 1); else days.push(i);
      this.quietDays = days.sort((a, b) => a - b);
      this.unsaved.settings = true;
    },



    // ── Library view state ───────────────────────────────────────────────────
    libView: 'history',
    exclBadge: 0,

    // ── History state ────────────────────────────────────────────────────────
    historyItems: [],
    historyPage: 1,
    historyTotal: 0,
    historySort: 'desc',
    historySortField: 'last_searched_ts',
    historySearch: '',
    historyInstanceFilter: '',
    historyTypeFilter: '',
    showExclusions: false,
    exclusions: [],

    // ── Imports state ────────────────────────────────────────────────────────
    importsItems: [],
    importsPage: 1,
    importsTotal: 0,
    importsSort: 'desc',
    importsSortField: 'confirmed_ts',
    importsSearch: '',
    importsPeriod: localStorage.getItem('nudgarr_imports_period') || 'lifetime',

    // ── CF Score state ───────────────────────────────────────────────────────
    cfItems: [],
    cfPage: 1,
    cfTotal: 0,
    cfSearch: '',
    cfInstanceFilter: '',
    cfPageSize: 25,
    cfScanInProgress: false,

    // ── Sweep state ──────────────────────────────────────────────────────────
    sweepStatus: null,
    lifetimeRuns: 0,
    avgPerRun: 0,
    importsSweep: { movies: 0, shows: 0 },
    importsTotal_: 0,
    instanceStatus: [],
    pipelineData: { cutoff: null, backlog: null, cfScore: null },

    // ── Intel state ──────────────────────────────────────────────────────────
    intelData: null,
    intelColdStart: true,

    // ── Settings form state ──────────────────────────────────────────────────
    cronExpr: '0 */6 * * *',
    quietEnabled: false,
    quietStart: '02:00',
    quietEnd: '06:00',
    quietDays: [],
    cooldown: 48,
    queueEnabled: false,
    queueThreshold: 10,
    radarrCutoffEnabled: true,
    sonarrCutoffEnabled: true,
    radarrMax: 10,
    sonarrMax: 10,
    radarrSampleMode: 'round_robin',
    sonarrSampleMode: 'round_robin',
    batchSize: 1,
    sleepSecs: 5,
    jitterSecs: 2,
    radarrExclEnabled: false,
    sonarrExclEnabled: false,
    radarrExclThreshold: 10,
    radarrUnexcl: 0,
    sonarrExclThreshold: 10,
    sonarrUnexcl: 0,

    // ── Pipelines form state ─────────────────────────────────────────────────
    radarrBacklogEnabled: false,
    sonarrBacklogEnabled: false,
    radarrBacklogMax: 5,
    sonarrBacklogMax: 5,
    radarrBacklogSampleMode: 'round_robin',
    sonarrBacklogSampleMode: 'round_robin',
    radarrMissingAddedDays: 30,
    sonarrMissingAddedDays: 0,
    radarrGracePeriod: 0,
    sonarrGracePeriod: 0,
    cfSyncCron: '0 0 * * *',
    radarrCfMax: 5,
    sonarrCfMax: 5,
    radarrCfSampleMode: 'largest_gap_first',
    sonarrCfSampleMode: 'largest_gap_first',
    cfLastSync: null,

    // ── Notifications form state ─────────────────────────────────────────────
    notifyEnabled: false,
    notifyUrl: '',
    notifyUrlVisible: false,
    notifyOnSweep: true,
    notifyOnImport: true,
    notifyOnAutoExcl: true,
    notifyOnError: true,
    notifyOnQueueDepth: true,

    // ── Advanced form state ──────────────────────────────────────────────────
    requireLogin: false,
    sessionTimeout: 60,
    defaultTab: 'sweep',
    showSupportLinkForm: false,
    importCheck: 120,
    logLevel: 'INFO',
    retentionDays: 90,

    // ── Filters state ────────────────────────────────────────────────────────
    radarrFiltersInstance: '',
    sonarrFiltersInstance: '',
    radarrFiltersLoaded: false,
    sonarrFiltersLoaded: false,

    // ── Overrides state ──────────────────────────────────────────────────────
    overrideCards: [],

    // ── Page size (shared across paginated views) ─────────────────────────────
    pageSize: 25,

    // ─────────────────────────────────────────────────────────────────────────
    // COMPUTED PROPERTIES
    // ─────────────────────────────────────────────────────────────────────────

    get topbarTitle() {
      const m = {
        sweep: 'Sweep', library: 'Library', intel: 'Intel',
        instances: 'Instances', pipelines: 'Pipelines', overrides: 'Overrides',
        filters: 'Filters', settings: 'Settings', notifications: 'Notifications',
        advanced: 'Advanced',
      };
      return m[this.panel] || '';
    },

    get topbarSub() {
      const total = this.radarrInstanceCount + this.sonarrInstanceCount;
      const activePipelines = [
        this.radarrCutoffEnabled || this.sonarrCutoffEnabled,
        this.radarrBacklogEnabled || this.sonarrBacklogEnabled,
        this.cfScoreEnabled,
      ].filter(Boolean).length;
      const disabled = [
        !(this.radarrBacklogEnabled || this.sonarrBacklogEnabled) ? 'Backlog' : null,
        !this.cfScoreEnabled ? 'CF Score' : null,
      ].filter(Boolean);
      const pipelineSub = disabled.length
        ? `${activePipelines} pipeline${activePipelines !== 1 ? 's' : ''} \u00b7 ${disabled.join(', ')} disabled`
        : `${activePipelines} pipeline${activePipelines !== 1 ? 's' : ''}`;
      const m = {
        sweep:         `${total} instance${total !== 1 ? 's' : ''} \u00b7 ${pipelineSub}`,
        library:       'History \u00b7 Imports \u00b7 CF Score \u00b7 Exclusions',
        intel:         'Lifetime performance data',
        instances:     `${this.radarrInstanceCount} Radarr \u00b7 ${this.sonarrInstanceCount} Sonarr`,
        pipelines:     pipelineSub,
        overrides:     `${total} instance${total !== 1 ? 's' : ''}`,
        filters:       'Tag and quality profile exclusions per instance',
        settings:      'Scheduler, throttling, auto-exclusion',
        notifications: '1 agent configured',
        advanced:      'Auth, retention, diagnostics',
      };
      return m[this.panel] || '';
    },

    get lastRunTs() {
      if (!this.lastRunUtc) return Date.now() - 2 * 3600000;
      return new Date(this.lastRunUtc).getTime();
    },

    get nextRunTs() {
      if (!this.nextRunUtc) return Date.now() + 25 * 60000;
      return new Date(this.nextRunUtc).getTime();
    },

    get nextRunColor() {
      if (!this.schedulerEnabled) return 'color:var(--muted)';
      if (this.nextRunTs < Date.now()) return 'color:var(--warn)';
      return 'color:var(--ok)';
    },

    get nextRunLabel() {
      if (!this.schedulerEnabled) return 'Manual';
      if (this.nextRunTs < Date.now()) return 'Overdue';
      return this.formatRelative(this.nextRunTs, true);
    },

    // ─────────────────────────────────────────────────────────────────────────
    // INIT
    // ─────────────────────────────────────────────────────────────────────────

    init() {
      // Tab migration guard
      try {
        const saved = localStorage.getItem('nudgarr_last_tab');
        if (saved) {
          const migrated = TAB_MIGRATION_V5[saved] || saved;
          const valid = VALID_TABS_V5.includes(migrated) ? migrated : 'sweep';
          if (valid !== saved) localStorage.setItem('nudgarr_last_tab', valid);
          this.panel = valid;
        }
      } catch (_) {}
      if (TAB_MIGRATION_V5[this.defaultTab]) this.defaultTab = TAB_MIGRATION_V5[this.defaultTab];
      if (!VALID_TABS_V5.includes(this.defaultTab)) this.defaultTab = 'sweep';

      // Load config and start polling
      this.loadAll();
      setInterval(() => this.pollCycle(), 5000);
    },

    // ─────────────────────────────────────────────────────────────────────────
    // API
    // ─────────────────────────────────────────────────────────────────────────

    async api(path, opts = {}) {
      const res = await fetch(path, {
        headers: { 'Content-Type': 'application/json', ...opts.headers },
        ...opts,
        body: opts.body ? JSON.stringify(opts.body) : undefined,
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.error || `HTTP ${res.status}`);
      }
      return res.json();
    },

    // ─────────────────────────────────────────────────────────────────────────
    // BOOTSTRAP
    // ─────────────────────────────────────────────────────────────────────────

    async loadAll() {
      try {
        this.CFG = await this.api('/api/config');
        this.applyConfig();
        await this.refreshStatus();
        this.maybeShowWhatsNew();
        this.maybeShowOnboarding();

        // Navigate to saved or default tab
        if (this.CFG && this.CFG.onboarding_complete) {
          let start = null;
          try { start = localStorage.getItem('nudgarr_last_tab'); } catch (_) {}
          if (!start) start = this.CFG.default_tab || 'sweep';
          start = TAB_MIGRATION_V5[start] || start;
          if (!VALID_TABS_V5.includes(start)) start = 'sweep';
          if (start === 'overrides' && !this.overridesEnabled) start = 'sweep';
          this.panel = start;
        } else {
          this.panel = 'instances';
        }

        localStorage.setItem('nudgarr_last_tab', this.panel);
        this.loadPanel(this.panel);
        this.$watch('panel', val => {
          localStorage.setItem('nudgarr_last_tab', val);
          this.loadPanel(val);
        });
      } catch (e) {
        this.showAlert('Failed to load — please refresh the page. (' + e.message + ')');
      }
    },

    applyConfig() {
      const c = this.CFG;
      if (!c) return;
      // Instances
      this.radarrInstances = (c.instances && c.instances.radarr) ? c.instances.radarr : [];
      this.sonarrInstances = (c.instances && c.instances.sonarr) ? c.instances.sonarr : [];
      // Feature flags
      this.overridesEnabled = !!c.per_instance_overrides_enabled;
      this.cfScoreEnabled   = !!c.cf_score_enabled;
      this.authEnabled      = !!c.auth_enabled;
      this.showSupportLink  = !!c.show_support_link;
      // Scheduler
      this.schedulerEnabled = !!c.scheduler_enabled;
      this.cronExpr         = c.cron_expression || '0 */6 * * *';
      this.autoMode             = c.scheduler_enabled ? 'AUTO' : 'MANUAL';
      // Maintenance
      this.quietEnabled = !!c.maintenance_window_enabled;
      this.quietStart   = c.maintenance_window_start || '02:00';
      this.quietEnd     = c.maintenance_window_end   || '06:00';
      this.quietDays    = c.maintenance_window_days  || [];
      // Cutoff
      this.cooldown            = c.cooldown_hours            !== undefined ? c.cooldown_hours : 48;
      this.radarrCutoffEnabled = c.radarr_cutoff_enabled     !== false;
      this.sonarrCutoffEnabled = c.sonarr_cutoff_enabled     !== false;
      this.radarrMax           = c.radarr_max_movies_per_run !== undefined ? c.radarr_max_movies_per_run : 10;
      this.sonarrMax           = c.sonarr_max_episodes_per_run !== undefined ? c.sonarr_max_episodes_per_run : 10;
      this.radarrSampleMode    = c.radarr_sample_mode        || 'round_robin';
      this.sonarrSampleMode    = c.sonarr_sample_mode        || 'round_robin';
      // Throttle
      this.batchSize    = c.batch_size    || 1;
      this.sleepSecs = c.sleep_seconds || 5;
      this.jitterSecs = c.jitter_seconds || 2;
      // Queue depth
      this.queueEnabled   = !!c.queue_depth_enabled;
      this.queueThreshold = c.queue_depth_threshold || 10;
      // Auto-exclusion
      this.radarrExclEnabled  = !!c.radarr_auto_exclude_enabled;
      this.sonarrExclEnabled  = !!c.sonarr_auto_exclude_enabled;
      this.radarrExclThreshold    = c.auto_exclude_movies_threshold || 10;
      this.radarrUnexcl           = c.auto_unexclude_movies_days    || 0;
      this.sonarrExclThreshold    = c.auto_exclude_shows_threshold  || 10;
      this.sonarrUnexcl           = c.auto_unexclude_shows_days     || 0;
      // Backlog
      this.radarrBacklogEnabled    = !!c.radarr_backlog_enabled;
      this.sonarrBacklogEnabled    = !!c.sonarr_backlog_enabled;
      this.radarrBacklogMax        = c.radarr_missing_max            !== undefined ? c.radarr_missing_max : 5;
      this.sonarrBacklogMax        = c.sonarr_missing_max            !== undefined ? c.sonarr_missing_max : 5;
      this.radarrBacklogSampleMode = c.radarr_backlog_sample_mode    || 'round_robin';
      this.sonarrBacklogSampleMode = c.sonarr_backlog_sample_mode    || 'round_robin';
      this.radarrMissingAddedDays  = c.radarr_missing_added_days     !== undefined ? c.radarr_missing_added_days : 30;
      this.radarrGracePeriod       = c.radarr_missing_grace_hours    || 0;
      this.sonarrGracePeriod       = c.sonarr_missing_grace_hours    || 0;
      // CF Score
      this.cfSyncCron          = c.cf_score_sync_cron          || '0 0 * * *';
      this.radarrCfMax         = c.radarr_cf_score_max         !== undefined ? c.radarr_cf_score_max : 5;
      this.sonarrCfMax         = c.sonarr_cf_score_max         !== undefined ? c.sonarr_cf_score_max : 5;
      this.radarrCfSampleMode  = c.radarr_cf_sample_mode       || 'largest_gap_first';
      this.sonarrCfSampleMode  = c.sonarr_cf_sample_mode       || 'largest_gap_first';
      // Notifications
      this.notifyEnabled     = !!c.notify_enabled;
      this.notifyUrl         = c.notify_url || '';
      this.notifyOnSweep     = c.notify_on_sweep_complete  !== false;
      this.notifyOnImport    = c.notify_on_import          !== false;
      this.notifyOnAutoExcl  = c.notify_on_auto_exclusion  !== false;
      this.notifyOnError     = c.notify_on_error           !== false;
      this.notifyOnQueueDepth = !!c.notify_on_queue_depth_skip;
      // Advanced
      this.requireLogin      = !!c.auth_enabled;
      this.sessionTimeout    = c.auth_session_minutes || 60;
      this.defaultTab        = c.default_tab          || 'sweep';
      this.showSupportLinkForm = !!c.show_support_link;
      this.importCheck  = c.import_check_minutes || 120;
      this.logLevel            = c.log_level            || 'INFO';
      this.retentionDays       = c.state_retention_days !== undefined ? c.state_retention_days : 90;
    },

    // ─────────────────────────────────────────────────────────────────────────
    // STATUS POLLING
    // ─────────────────────────────────────────────────────────────────────────

    async pollCycle() {
      try { await this.refreshStatus(); } catch (_) {}
    },

    async refreshStatus() {
      const s = await this.api('/api/status');
      this.sweeping         = !!s.sweeping;
      this.schedulerEnabled = !!s.scheduler_enabled;
      this.autoMode         = s.scheduler_enabled ? 'AUTO' : 'MANUAL';
      this.lastRunUtc       = s.last_run_utc       || null;
      this.nextRunUtc       = s.next_run_utc        || null;
      this.lastSkippedQueueDepthUtc = s.last_skipped_queue_depth_utc || null;
      // Update sweep panel data if on sweep tab
      if (this.panel === 'sweep') this.refreshSweep(s);
    },

    // ─────────────────────────────────────────────────────────────────────────
    // PANEL LOADER
    // ─────────────────────────────────────────────────────────────────────────

    loadPanel(p) {
      // Guard: if CF Score disabled and on cfscores view, redirect to history
      if (p === 'library' && this.libView === 'cfscores' && !this.cfScoreEnabled) {
        this.libView = 'history';
      }
      switch (p) {
        case 'sweep':         this.refreshSweep();    break;
        case 'library':       this.refreshLibrary();  break;
        case 'intel':         this.refreshIntel();    break;
        case 'instances':     this.renderInstances(); break;
        case 'pipelines':     break; // reactive, no load needed
        case 'overrides':     this.renderOverrides(); break;
        case 'filters':       this.loadFilters();     break;
        case 'settings':      break; // reactive
        case 'notifications': break; // reactive
        case 'advanced':      break; // reactive
      }
    },

    // ─────────────────────────────────────────────────────────────────────────
    // SIDEBAR / MODAL HELPERS
    // ─────────────────────────────────────────────────────────────────────────

    openSidebar()  { this.sidebarOpen = true; },
    closeSidebar() { this.sidebarOpen = false; },

    openModal(name) { this.modal = name; },
    closeModal()    { this.modal = null; this.clearExclOpt = null; this.confirmAction = null; },

    showAlert(msg, type = 'error') { this.alertMsg = msg; this.alertType = type; this.modal = 'alert'; },

    danger(action) {
      const actions = {
        clearHistory:  { title: 'Clear History',          msg: 'Removes all search history records. Exclusions, imports, and Intel lifetime data are not affected.',          label: 'Clear History' },
        clearImports:  { title: 'Clear Imports',          msg: 'Removes all import records. Intel lifetime totals and sweep run counts are not affected.',                    label: 'Clear Imports' },
        clearLog:      { title: 'Clear Log',              msg: 'Clears the application log. This only affects the in-memory log shown in diagnostics.',                      label: 'Clear Log' },
        resetIntel:    { title: 'Reset Intel',            msg: 'Resets all lifetime Intel data including turnaround, upgrade history, and exclusion events. Cannot be undone.', label: 'Reset Intel' },
        resetExclusions: { title: 'Clear All Exclusions', msg: 'Removes every exclusion. All titles will become eligible for searching again immediately.',                   label: 'Clear Exclusions' },
      };
      const a = actions[action];
      if (!a) return;
      this.confirmAction = action;
      this.confirmTitle  = a.title;
      this.confirmMsg    = a.msg;
      this.confirmLabel  = a.label;
      this.modal = 'confirm';
    },

    enableOverrides() {
      this.overridesEnabled = true;
      if (!this.overridesInfoSeen) { this.overridesInfoSeen = true; this.modal = 'overridesInfo'; }
    },

    // ─────────────────────────────────────────────────────────────────────────
    // WHAT'S NEW / ONBOARDING
    // ─────────────────────────────────────────────────────────────────────────

    maybeShowWhatsNew() {
      if (!this.CFG || !this.CFG.onboarding_complete) return;
      const lastSeen = this.CFG.last_seen_version || '';
      const current  = this.CFG.version           || '';
      const toMinor  = v => v.split('.').slice(0, 2).join('.');
      if (current && toMinor(lastSeen) !== toMinor(current)) this.modal = 'whatsNew';
    },

    async dismissWhatsNew() {
      this.closeModal();
      try { await this.api('/api/whats-new/dismiss', { method: 'POST' }); } catch (_) {}
      if (this.CFG) this.CFG.last_seen_version = this.CFG.version;
    },

    maybeShowOnboarding() {
      if (this.CFG && !this.CFG.onboarding_complete) this.modal = 'onboarding';
    },

    // ─────────────────────────────────────────────────────────────────────────
    // TIME / CRON UTILITIES
    // ─────────────────────────────────────────────────────────────────────────

    formatRelative(ts, future = false) {
      const diff = future ? ts - Date.now() : Date.now() - ts;
      const mins = Math.floor(diff / 60000);
      const hrs  = Math.floor(diff / 3600000);
      const days = Math.floor(diff / 86400000);
      if (!future && mins < 1) return 'Just now';
      if (future  && mins < 1) return 'Now';
      if (mins < 60)           return `${mins}m${future ? '' : ' ago'}`;
      if (hrs  < 24)           return `${hrs}h${future ? '' : ' ago'}`;
      if (days < 7)            return `${days}d${future ? '' : ' ago'}`;
      const d = new Date(ts);
      const sameYear = d.getFullYear() === new Date().getFullYear();
      return d.toLocaleDateString('en-US', {
        month: 'short', day: 'numeric',
        ...(sameYear ? {} : { year: 'numeric' }),
      });
    },

    formatCompact(n) {
      if (n === null || n === undefined) return '—';
      if (n < 10000) return n.toLocaleString();
      if (n < 1000000) return (n / 1000).toFixed(n >= 100000 ? 0 : 1).replace(/\.0$/, '') + 'k';
      return (n / 1000000).toFixed(1).replace(/\.0$/, '') + 'M';
    },

    describeCron(expr) {
      if (!expr) return '';
      const parts = expr.trim().split(/\s+/);
      if (parts.length !== 5) return expr;
      const [min, hr, dom, mon, dow] = parts;
      if (expr === '0 */6 * * *') return 'Every 6 hours';
      if (expr === '0 */4 * * *') return 'Every 4 hours';
      if (expr === '0 */12 * * *') return 'Every 12 hours';
      if (expr === '0 0 * * *') return 'Daily at midnight';
      if (expr === '0 2 * * *') return 'Daily at 2 AM';
      if (hr.startsWith('*/') && min === '0' && dom === '*' && mon === '*' && dow === '*') {
        return `Every ${hr.slice(2)} hours`;
      }
      if (dom === '*' && mon === '*' && dow === '*' && min === '0') {
        return `Daily at ${hr.padStart(2,'0')}:00`;
      }
      return expr;
    },

    updateContainerTime() {
      return new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
    },

    // ─────────────────────────────────────────────────────────────────────────
    // PANEL STUBS — implemented in Phase 3
    // ─────────────────────────────────────────────────────────────────────────

    async runNow() {
      try {
        await this.api('/api/run-now', { method: 'POST' });
        this.sweeping = true;
      } catch (e) {
        this.showAlert('Run request failed: ' + e.message);
      }
    },

    async logout() {
      try {
        await this.api('/api/auth/logout', { method: 'POST' });
        window.location.href = '/login';
      } catch (_) {
        window.location.href = '/login';
      }
    },

    // ── Filter data (loaded on demand) ─────────────────────────────────────────
    radarrFilterTags:       [],
    radarrFilterProfiles:   [],
    sonarrFilterTags:       [],
    sonarrFilterProfiles:   [],
    radarrExcludedTags:     [],
    radarrExcludedProfiles: [],
    sonarrExcludedTags:     [],
    sonarrExcludedProfiles: [],
    filtersRadarrUnsaved:   false,
    filtersSonarrUnsaved:   false,



      // ── Sweep ─────────────────────────────────────────────────────────────────
      async refreshSweep(statusData) {
        try {
          const status = statusData || await this.api('/api/status');
          const summary  = status.last_summary || {};
          const health   = status.instance_health || {};
          const lifetime = status.sweep_lifetime || {};
          const lastCutoff  = status.last_run_cutoff_utc  || null;
          const lastBacklog = status.last_run_backlog_utc  || null;
          const lastCf      = status.last_run_cfscore_utc  || null;

          const allInsts = [];
          for (const kind of ['radarr','sonarr']) {
            for (const inst of (this.CFG?.instances?.[kind] || [])) {
              allInsts.push({ ...inst, _kind: kind });
            }
          }

          // Lifetime stats
          let ltRuns = 0, ltSearched = 0;
          for (const row of Object.values(lifetime)) {
            ltRuns     += row.runs     || 0;
            ltSearched += row.searched || 0;
          }
          this.lifetimeRuns = ltRuns;
          this.avgPerRun    = ltRuns > 0 ? (ltSearched / ltRuns).toFixed(1) : '0';

          // Instance health
          const badInsts   = Object.entries(health).filter(([,v]) => v === 'bad');
          this.instanceStatus = Object.entries(health).map(([key, state]) => {
            const [app, ...np] = key.split('|');
            return { app, name: np.join('|'), state };
          });

          // Imports confirmed this sweep
          const imp = status.imports_confirmed_sweep || { movies: 0, shows: 0 };
          this.importsSweep = imp;
          this.importsTotal_ = (imp.movies || 0) + (imp.shows || 0);

          // Pipeline data
          this.pipelineData = {
            cutoff:  this._buildPipelineAgg('cutoff',  summary, allInsts),
            backlog: this._buildPipelineAgg('backlog', summary, allInsts),
            cfScore: this._buildPipelineAgg('cfscore', summary, allInsts),
            health,
            lastCutoff, lastBacklog, lastCf,
            allInsts,
          };
        } catch(e) {
          console.warn('[sweep] refreshSweep failed:', e.message);
        }
      },

      _buildPipelineAgg(type, summary, allInsts) {
        const radarr = summary.radarr || [];
        const sonarr = summary.sonarr || [];
        const all    = [...radarr, ...sonarr];
        const agg = { searched: 0, cooldown: 0, excluded: 0, tag: 0, profile: 0, grace: 0 };
        for (const s of all) {
          if (type === 'cutoff') {
            agg.searched  += s.searched                || 0;
            agg.cooldown  += s.skipped_cooldown         || 0;
            agg.excluded  += s.skipped_excluded_cutoff  || 0;
            agg.tag       += s.skipped_tag_cutoff       || 0;
            agg.profile   += s.skipped_profile_cutoff   || 0;
          } else if (type === 'backlog') {
            agg.searched  += s.searched_missing         || 0;
            agg.cooldown  += s.skipped_missing_cooldown || 0;
            agg.grace     += s.skipped_grace            || 0;
            agg.tag       += s.skipped_tag_backlog      || 0;
            agg.profile   += s.skipped_profile_backlog  || 0;
          } else {
            agg.searched  += s.searched_cf              || 0;
            agg.cooldown  += s.skipped_cf_cooldown      || 0;
            agg.excluded  += s.skipped_cf_excluded      || 0;
          }
        }
        return agg;
      },

      // ── Library ───────────────────────────────────────────────────────────────
      async refreshLibrary() {
        if (this.libView === 'history')    await this.refreshHistory();
        else if (this.libView === 'imports')   await this.refreshImports();
        else if (this.libView === 'cf-score')  await this.refreshCfScores();
        else if (this.libView === 'exclusions') await this.loadExclusions();
      },

      async refreshHistory() {
        try {
          const sum = await this.api('/api/state/summary');
          // Badge
          const count = await this.api('/api/exclusions/unacknowledged-count');
          this.exclBadge = count.count || 0;

          const allInsts = [];
          for (const kind of ['radarr','sonarr']) {
            for (const inst of (this.CFG?.instances?.[kind] || [])) {
              allInsts.push({ ...inst, _kind: kind, key: inst.url + '|' + inst.name });
            }
          }

          const selInst  = this.historyInstanceFilter;
          const selType  = this.historyTypeFilter;
          const limit    = this.pageSize;
          const offset   = (this.historyPage - 1) * limit;

          const url = `/api/state/items?offset=${offset}&limit=${limit}`
            + (selInst ? `&instance=${encodeURIComponent(selInst)}` : '')
            + (selType ? `&type=${encodeURIComponent(selType)}` : '')
            + (this.historySearch ? `&search=${encodeURIComponent(this.historySearch)}` : '');

          const data = await this.api(url);
          this.historyItems = data.items  || [];
          this.historyTotal = data.total  || 0;
        } catch(e) {
          console.warn('[library] refreshHistory failed:', e.message);
        }
      },

      async refreshImports() {
        try {
          const limit  = this.pageSize;
          const offset = (this.importsPage - 1) * limit;
          let url = `/api/stats?offset=${offset}&limit=${limit}&period=${encodeURIComponent(this.importsPeriod)}`;
          if (this.historyInstanceFilter) url += `&instance=${encodeURIComponent(this.historyInstanceFilter)}`;
          const data = await this.api(url);
          this.importsItems = data.items      || [];
          this.importsTotal = data.total      || 0;
          localStorage.setItem('nudgarr_imports_period', this.importsPeriod);
        } catch(e) {
          console.warn('[library] refreshImports failed:', e.message);
        }
      },

      async refreshCfScores() {
        try {
          let url = '/api/cf-scores/entries';
          if (this.cfInstanceFilter) url += '?instance_id=' + encodeURIComponent(this.cfInstanceFilter);
          const [status, entries] = await Promise.all([
            this.api('/api/cf-scores/status'),
            this.api(url),
          ]);
          this.cfItems = entries.entries || entries.items || [];
          this.cfTotal = entries.total   || this.cfItems.length;
          this.cfLastSync = status?.last_sync_utc || null;

          if (status?.scan_in_progress && !this.cfScanInProgress) {
            this.cfScanInProgress = true;
            this._cfWaitForScan();
          }
        } catch(e) {
          console.warn('[library] refreshCfScores failed:', e.message);
        }
      },

      async _cfWaitForScan() {
        for (let i = 0; i < 120; i++) {
          await new Promise(r => setTimeout(r, 3000));
          try {
            const s = await this.api('/api/cf-scores/status');
            if (!s.scan_in_progress) { this.cfScanInProgress = false; await this.refreshCfScores(); return; }
          } catch(_) {}
        }
        this.cfScanInProgress = false;
      },

      async cfScanLibrary() {
        try {
          await this.api('/api/cf-scores/scan');
          this.cfScanInProgress = true;
          this._cfWaitForScan();
        } catch(e) {
          this.showAlert('Scan could not be started: ' + e.message);
        }
      },

      async cfResetIndex() {
        try {
          await this.api('/api/cf-scores/reset');
          this.showAlert('CF Score index reset.', 'success');
          await this.refreshCfScores();
        } catch(e) {
          this.showAlert('Reset failed: ' + e.message);
        }
      },

      async loadExclusions() {
        try {
          const data = await this.api('/api/exclusions');
          this.exclusions = data.exclusions || [];
          this.exclBadge  = 0;
          await this.api('/api/exclusions/acknowledge');
        } catch(e) {
          console.warn('[library] loadExclusions failed:', e.message);
        }
      },

      async toggleExclusion(title, app) {
        try {
          const isExcluded = this.exclusions.some(e => e.title === title);
          if (isExcluded) {
            await this.api(`/api/exclusions/${encodeURIComponent(title)}`, { method: 'DELETE' });
          } else {
            await this.api('/api/exclusions', { method: 'POST', body: { title, app } });
          }
          await this.loadExclusions();
        } catch(e) {
          this.showAlert('Exclusion update failed: ' + e.message);
        }
      },

      async confirmClearExclusions() {
        if (!this.clearExclOpt) return;
        try {
          await this.api('/api/exclusions/clear-auto', { method: 'POST', body: { scope: this.clearExclOpt } });
          this.closeModal();
          this.showAlert('Exclusions cleared.', 'success');
          await this.loadExclusions();
        } catch(e) {
          this.showAlert('Clear failed: ' + e.message);
        }
      },

      async pruneHistory() {
        try {
          const out = await this.api('/api/state/prune', { method: 'POST' });
          this.showAlert(`Pruned ${out.removed || 0} entries.`, 'success');
          await this.refreshHistory();
        } catch(e) {
          this.showAlert('Prune failed: ' + e.message);
        }
      },

      // ── Intel ─────────────────────────────────────────────────────────────────
      async refreshIntel() {
        try {
          this.intelData = await this.api('/api/intel');
          this.intelColdStart = !!(this.intelData && this.intelData.cold_start);
        } catch(e) {
          console.warn('[intel] refreshIntel failed:', e.message);
        }
      },

      // ── Instances ─────────────────────────────────────────────────────────────
      async renderInstances() {
        // Instances are rendered reactively from this.radarrInstances / sonarrInstances
        // No API call needed — config is already loaded in applyConfig()
      },

      openInstanceModal(kind, idx) {
        this.modalMode = idx >= 0 ? 'edit' : 'add';
        this.modalIdx  = idx;
        window._modalKind = kind;
        window._modalIdx  = idx;

        const inst = idx >= 0 ? (this.CFG?.instances?.[kind]?.[idx] || {}) : {};
        const nameEl = document.getElementById('modalName');
        const urlEl  = document.getElementById('modalUrl');
        const keyEl  = document.getElementById('modalKey');
        if (nameEl) nameEl.value = inst.name || '';
        if (urlEl)  urlEl.value  = inst.url  || '';
        if (keyEl)  { keyEl.value = inst.key || ''; keyEl.type = 'password'; }
        const lbl = document.getElementById('modalKeyLabel');
        if (lbl) lbl.textContent = 'Show';

        // Clear test result
        const wr = document.getElementById('modalTestResult');
        if (wr) wr.style.display = 'none';

        this.modal = 'instance';
        setTimeout(() => { if (nameEl) nameEl.focus(); }, 60);
      },

      async deleteInstance(kind, idx) {
        if (!this.CFG) return;
        this.CFG.instances[kind].splice(idx, 1);
        this.radarrInstances = this.CFG.instances.radarr || [];
        this.sonarrInstances = this.CFG.instances.sonarr || [];
        this.unsaved.settings = true;
      },

      async toggleInstance(kind, idx) {
        try {
          const out = await this.api('/api/instance/toggle', { method: 'POST', body: { kind, idx } });
          if (this.CFG) this.CFG.instances[kind][idx].enabled = out.enabled;
          this.radarrInstances = [...(this.CFG?.instances?.radarr || [])];
          this.sonarrInstances = [...(this.CFG?.instances?.sonarr || [])];
        } catch(e) {
          this.showAlert('Toggle failed: ' + e.message);
        }
      },

      async saveInstances() {
        try {
          await this.api('/api/config', { method: 'POST', body: this.CFG });
          await this.loadAll();
          this.unsaved.settings = false;
          this.showAlert('Saved.', 'success');
        } catch(e) {
          this.showAlert('Save failed: ' + e.message);
        }
      },

      // ── Overrides ─────────────────────────────────────────────────────────────
      async renderOverrides() {
        try {
          const data = await this.api('/api/instance/overrides');
          this.overrideCards = data.overrides || [];
        } catch(e) {
          console.warn('[overrides] renderOverrides failed:', e.message);
        }
      },

      async applyOverrides(kind, idx) {
        try {
          const inst = this.CFG?.instances?.[kind]?.[idx];
          if (!inst) return;
          const card = document.querySelector(`[data-ov-card="${kind}-${idx}"]`);
          if (!card) return;

          const newOv = Object.assign({}, inst.overrides || {});
          const numFields = ['cooldown_hours', 'max_cutoff_unmet', 'max_backlog', 'missing_grace_hours'];
          if (kind === 'radarr') numFields.push('max_missing_days');
          if (this.cfScoreEnabled) numFields.push('cf_max');

          numFields.forEach(field => {
            const input = card.querySelector(`[data-ov-field="${field}"]`);
            if (!input) return;
            const raw = input.value.trim();
            if (raw !== '') newOv[field] = parseInt(raw, 10);
            else delete newOv[field];
          });

          ['sample_mode', 'backlog_sample_mode', 'cf_sample_mode'].forEach(field => {
            const sel = card.querySelector(`[data-ov-field="${field}"]`);
            if (!sel) return;
            if (!sel.value || sel.value === '__global__') delete newOv[field];
            else newOv[field] = sel.value;
          });

          const boolFields = ['backlog_enabled', 'notifications_enabled'];
          boolFields.forEach(field => {
            const chk = card.querySelector(`[data-ov-field="${field}"]`);
            if (!chk) return;
            newOv[field] = chk.checked;
          });

          await this.api('/api/instance/overrides', {
            method: 'POST',
            body: { kind, idx, overrides: newOv },
          });
          this.CFG.instances[kind][idx].overrides = newOv;
          this.showAlert('Overrides applied.', 'success');
        } catch(e) {
          this.showAlert('Failed to save overrides: ' + e.message);
        }
      },

      async resetCardOverrides(kind, idx) {
        try {
          await this.api('/api/instance/overrides', {
            method: 'POST',
            body: { kind, idx, overrides: {} },
          });
          if (this.CFG?.instances?.[kind]?.[idx]) this.CFG.instances[kind][idx].overrides = {};
          this.showAlert('Overrides reset.', 'success');
        } catch(e) {
          this.showAlert('Failed to reset overrides: ' + e.message);
        }
      },

      // ── Filters ───────────────────────────────────────────────────────────────
      async loadFilters() {
        // Filters are loaded on demand when "Load Tags & Profiles" is clicked
        // Pre-populate instance selectors from config
        const radarrInsts = this.CFG?.instances?.radarr || [];
        const sonarrInsts = this.CFG?.instances?.sonarr || [];
        if (radarrInsts.length) this.radarrFiltersInstance = '0';
        if (sonarrInsts.length) this.sonarrFiltersInstance = '0';
      },

      async loadArrData(kind) {
        const idx = parseInt(kind === 'radarr' ? this.radarrFiltersInstance : this.sonarrFiltersInstance) || 0;
        try {
          const [tagRes, profileRes] = await Promise.all([
            this.api(`/api/arr/tags?kind=${kind}&idx=${idx}`),
            this.api(`/api/arr/profiles?kind=${kind}&idx=${idx}`),
          ]);
          if (!tagRes?.ok || !profileRes?.ok) {
            this.showAlert(tagRes?.error || profileRes?.error || 'Failed to load — check instance connectivity.');
            return;
          }
          if (kind === 'radarr') {
            this.radarrFilterTags     = tagRes.tags      || [];
            this.radarrFilterProfiles = profileRes.profiles || [];
            this.radarrFiltersLoaded  = true;
          } else {
            this.sonarrFilterTags     = tagRes.tags      || [];
            this.sonarrFilterProfiles = profileRes.profiles || [];
            this.sonarrFiltersLoaded  = true;
          }
        } catch(e) {
          this.showAlert('Failed to load arr data: ' + e.message);
        }
      },

      async saveFilters(kind) {
        const idx = parseInt(kind === 'radarr' ? this.radarrFiltersInstance : this.sonarrFiltersInstance) || 0;
        try {
          const cfg = await this.api('/api/config');
          const insts = cfg.instances?.[kind] || [];
          if (idx >= insts.length) return;
          insts[idx].sweep_filters = {
            excluded_tags:     kind === 'radarr' ? (this.radarrExcludedTags     || []) : (this.sonarrExcludedTags     || []),
            excluded_profiles: kind === 'radarr' ? (this.radarrExcludedProfiles || []) : (this.sonarrExcludedProfiles || []),
          };
          await this.api('/api/config', { method: 'POST', body: cfg });
          this.CFG = cfg;
          this.unsaved.filters = false;
          this.showAlert('Filters saved.', 'success');
        } catch(e) {
          this.showAlert('Save failed: ' + e.message);
        }
      },

      // ── Settings ──────────────────────────────────────────────────────────────
      async saveSettings() {
        try {
          if (!this.CFG) return;
          if (this.schedulerEnabled) {
            const parts = (this.cronExpr || '').trim().split(/\s+/);
            const valid = parts.length === 5 && parts.every(p => /^[\d*/,\-]+$/.test(p));
            if (!valid) { this.showAlert('Enter a valid cron expression before saving.'); return; }
          }
          Object.assign(this.CFG, {
            scheduler_enabled:         this.schedulerEnabled,
            cron_expression:           this.cronExpr,
            cooldown_hours:            parseInt(this.cooldown) || 48,
            radarr_cutoff_enabled:     this.radarrCutoffEnabled,
            sonarr_cutoff_enabled:     this.sonarrCutoffEnabled,
            radarr_max_movies_per_run: parseInt(this.radarrMax)  || 10,
            sonarr_max_episodes_per_run: parseInt(this.sonarrMax) || 10,
            radarr_sample_mode:        this.radarrSampleMode,
            sonarr_sample_mode:        this.sonarrSampleMode,
            batch_size:                parseInt(this.batchSize)    || 1,
            sleep_seconds:             parseFloat(this.sleepSecs) || 5,
            jitter_seconds:            parseFloat(this.jitterSecs) || 2,
            maintenance_window_enabled: this.quietEnabled,
            maintenance_window_start:  this.quietStart,
            maintenance_window_end:    this.quietEnd,
            maintenance_window_days:   this.quietDays,
            queue_depth_enabled:       this.queueEnabled,
            queue_depth_threshold:     Math.max(1, parseInt(this.queueThreshold) || 10),
            per_instance_overrides_enabled: this.overridesEnabled,
            radarr_auto_exclude_enabled:    this.radarrExclEnabled,
            sonarr_auto_exclude_enabled:    this.sonarrExclEnabled,
            auto_exclude_movies_threshold:  parseInt(this.radarrExclThreshold) || 0,
            auto_exclude_shows_threshold:   parseInt(this.sonarrExclThreshold) || 0,
            auto_unexclude_movies_days:     parseInt(this.radarrUnexcl)        || 0,
            auto_unexclude_shows_days:      parseInt(this.sonarrUnexcl)        || 0,
          });
          await this.api('/api/config', { method: 'POST', body: this.CFG });
          await this.loadAll();
          this.unsaved.settings = false;
          this.showAlert('Settings saved.', 'success');
        } catch(e) {
          this.showAlert('Save failed: ' + e.message);
        }
      },

      // ── Pipelines ─────────────────────────────────────────────────────────────
      async savePipelines() {
        try {
          if (!this.CFG) return;
          Object.assign(this.CFG, {
            radarr_backlog_enabled:    this.radarrBacklogEnabled,
            sonarr_backlog_enabled:    this.sonarrBacklogEnabled,
            radarr_missing_max:        parseInt(this.radarrBacklogMax) || 0,
            sonarr_missing_max:        parseInt(this.sonarrBacklogMax) || 0,
            radarr_backlog_sample_mode: this.radarrBacklogSampleMode,
            sonarr_backlog_sample_mode: this.sonarrBacklogSampleMode,
            radarr_missing_added_days:  parseInt(this.radarrMissingAddedDays) || 0,
            radarr_missing_grace_hours: parseInt(this.radarrGracePeriod)       || 0,
            sonarr_missing_grace_hours: parseInt(this.sonarrGracePeriod)       || 0,
            cf_score_enabled:           this.cfScoreEnabled,
            cf_score_sync_cron:         this.cfSyncCron,
            radarr_cf_score_max:        parseInt(this.radarrCfMax) || 0,
            sonarr_cf_score_max:        parseInt(this.sonarrCfMax) || 0,
            radarr_cf_sample_mode:      this.radarrCfSampleMode,
            sonarr_cf_sample_mode:      this.sonarrCfSampleMode,
          });
          await this.api('/api/config', { method: 'POST', body: this.CFG });
          await this.loadAll();
          this.unsaved.pipelines = false;
          this.showAlert('Pipelines saved.', 'success');
        } catch(e) {
          this.showAlert('Save failed: ' + e.message);
        }
      },

      // ── Notifications ─────────────────────────────────────────────────────────
      async saveNotifications() {
        try {
          if (!this.CFG) return;
          Object.assign(this.CFG, {
            notify_enabled:            this.notifyEnabled,
            notify_url:                this.notifyUrl,
            notify_on_sweep_complete:  this.notifyOnSweep,
            notify_on_import:          this.notifyOnImport,
            notify_on_auto_exclusion:  this.notifyOnAutoExcl,
            notify_on_error:           this.notifyOnError,
            notify_on_queue_depth_skip: this.notifyOnQueueDepth,
          });
          await this.api('/api/config', { method: 'POST', body: this.CFG });
          this.unsaved.notifications = false;
          this.showAlert('Saved.', 'success');
        } catch(e) {
          this.showAlert('Save failed: ' + e.message);
        }
      },

      async testNotification() {
        try {
          await this.api('/api/notifications/test');
          this.showAlert('Test notification sent.', 'success');
        } catch(e) {
          this.showAlert('Test failed: ' + e.message);
        }
      },

      // ── Advanced ──────────────────────────────────────────────────────────────
      async saveAdvanced() {
        try {
          if (!this.CFG) return;
          Object.assign(this.CFG, {
            auth_enabled:          this.requireLogin,
            auth_session_minutes:  parseInt(this.sessionTimeout)    || 60,
            default_tab:           this.defaultTab,
            show_support_link:     this.showSupportLinkForm,
            import_check_minutes:  parseInt(this.importCheck) || 120,
            log_level:             this.logLevel,
            state_retention_days:  parseInt(this.retentionDays)      || 0,
          });
          await this.api('/api/config', { method: 'POST', body: this.CFG });
          await this.loadAll();
          this.unsaved.advanced = false;
          this.showAlert('Saved.', 'success');
        } catch(e) {
          this.showAlert('Save failed: ' + e.message);
        }
      },

      // ── Danger zone ───────────────────────────────────────────────────────────
      async executeConfirmAction() {
        this.closeModal();
        try {
          switch (this.confirmAction) {
            case 'clearHistory':
              await this.api('/api/state/clear', { method: 'POST' });
              this.showAlert('History cleared.', 'success');
              if (this.panel === 'library') await this.refreshHistory();
              break;
            case 'clearImports':
              await this.api('/api/stats/clear', { method: 'POST' });
              this.showAlert('Imports cleared.', 'success');
              if (this.panel === 'library') await this.refreshImports();
              break;
            case 'clearLog':
              await this.api('/api/log/clear', { method: 'POST' });
              this.showAlert('Log cleared.', 'success');
              break;
            case 'resetIntel':
              await this.api('/api/intel/reset', { method: 'POST' });
              this.showAlert('Intel reset.', 'success');
              if (this.panel === 'intel') await this.refreshIntel();
              break;
          }
        } catch(e) {
          this.showAlert(e.message);
        }
      },

      async doResetConfig() {
        this.closeModal();
        try {
          await this.api('/api/config/reset', { method: 'POST' });
          window.location.href = '/';
        } catch(e) {
          this.showAlert('Reset failed: ' + e.message);
        }
      },

      async backupAll() {
        try {
          const res = await fetch('/api/diagnostic');
          const blob = await res.blob();
          const a = document.createElement('a');
          a.href = URL.createObjectURL(blob);
          a.download = 'nudgarr-backup.json';
          a.click();
        } catch(e) {
          this.showAlert('Backup failed: ' + e.message);
        }
      },

      async downloadDiagnostic() {
        try {
          const res = await fetch('/api/diagnostic?mode=diag');
          const blob = await res.blob();
          const a = document.createElement('a');
          a.href = URL.createObjectURL(blob);
          a.download = 'nudgarr-diagnostic.txt';
          a.click();
        } catch(e) {
          this.showAlert('Diagnostic failed: ' + e.message);
        }
      },

  };
}

// ── Globals still needed for onclick handlers in modals ───────────────────────
// These bridge between onclick attributes in ui.html and the Alpine data object.
// In a future cleanup these could be replaced with x-on:click bindings.

function toggleKeyVis() {
  const inp = document.getElementById('modalKey');
  const btn = document.getElementById('modalKeyLabel');
  if (!inp) return;
  if (inp.type === 'password') { inp.type = 'text'; btn.textContent = 'Hide'; }
  else                         { inp.type = 'password'; btn.textContent = 'Show'; }
}

// ── Alpine bridge helpers ─────────────────────────────────────────────────────
// Called from onclick attrs in ui.html where @click is not possible.
function _alpine() {
  try { return Alpine.$data(document.querySelector('[x-data]')); } catch(_) { return null; }
}

async function testModalConnection() {
  const d = _alpine(); if (!d) return;
  const kind = window._modalKind || 'radarr';
  const idx  = window._modalIdx  !== undefined ? window._modalIdx : -1;
  const name = document.getElementById('modalName')?.value.trim();
  const url  = document.getElementById('modalUrl')?.value.trim();
  const key  = document.getElementById('modalKey')?.value.trim();
  if (!url || !key) { d.showAlert('Enter a URL and API key before testing.'); return; }
  const btn  = document.getElementById('modalTestBtn');
  const wrap = document.getElementById('modalTestResult');
  const inner = wrap?.querySelector('.modal-test-inner');
  if (btn)   btn.disabled = true;
  if (wrap)  wrap.style.display = 'block';
  try {
    const tempCfg = JSON.parse(JSON.stringify(d.CFG));
    tempCfg.instances = tempCfg.instances || { radarr: [], sonarr: [] };
    const tempInst = { name: name || kind, url, key };
    if (idx >= 0) tempCfg.instances[kind][idx] = Object.assign({}, tempCfg.instances[kind][idx], tempInst);
    else { tempCfg.instances[kind] = tempCfg.instances[kind] || []; tempCfg.instances[kind].push(tempInst); }
    const out = await d.api('/api/test-instance', { method: 'POST', body: { kind, instances: tempCfg.instances, update_status: false } });
    const results = out.results?.[kind] || [];
    const testIdx = idx >= 0 ? idx : results.length - 1;
    const match   = results[testIdx] || results.find(r => r.name === name);
    if (wrap) wrap.style.display = 'block';
    if (match?.ok) {
      if (wrap) wrap.innerHTML = `<div class="modal-test-inner ok">Connected${match.version ? ' — ' + kind.charAt(0).toUpperCase()+kind.slice(1)+' v'+match.version : ''}</div>`;
    } else {
      if (wrap) wrap.innerHTML = `<div class="modal-test-inner bad">${escapeHtml((match && match.error) ? match.error : 'Could not connect — check URL and API key')}</div>`;
    }
  } catch(e) {
    if (wrap) wrap.innerHTML = `<div class="modal-test-inner bad">Could not connect — check URL and API key</div>`;
  }
  if (btn) btn.disabled = false;
}

async function saveModal() {
  const d = _alpine(); if (!d) return;
  const kind = window._modalKind || 'radarr';
  const idx  = window._modalIdx  !== undefined ? window._modalIdx : -1;
  const name = document.getElementById('modalName')?.value.trim();
  const url  = document.getElementById('modalUrl')?.value.trim();
  const key  = document.getElementById('modalKey')?.value.trim();
  if (!name || !url) { d.showAlert('All fields are required.'); return; }
  if (!key && idx < 0) { d.showAlert('API key is required.'); return; }
  if (!d.CFG.instances) d.CFG.instances = { radarr: [], sonarr: [] };
  if (!d.CFG.instances[kind]) d.CFG.instances[kind] = [];
  if (idx >= 0) {
    d.CFG.instances[kind][idx] = Object.assign({}, d.CFG.instances[kind][idx], { name, url, key });
  } else {
    d.CFG.instances[kind].push({ name, url, key });
  }
  d.radarrInstances = [...(d.CFG.instances.radarr || [])];
  d.sonarrInstances = [...(d.CFG.instances.sonarr || [])];
  d.unsaved.settings = true;
  d.closeModal();
}

function executeConfirmAction() { const d = _alpine(); if (d) d.executeConfirmAction(); }
function doResetConfig()        { const d = _alpine(); if (d) d.doResetConfig(); }
function confirmClearExclusions() { const d = _alpine(); if (d) d.confirmClearExclusions(); }


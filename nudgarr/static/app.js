// Nudgarr v5 — Alpine.js frontend
// Single data object; loaded as nudgarr/static/app.js.
// ui.html: <body x-data="nudgarr()" x-init="...">

function nudgarr() {
  return {

    // ── Navigation ──────────────────────────────────────────────────────
    panel: 'sweep',
    mobileDrawerOpen: false,

    // ── Feature flags ───────────────────────────────────────────────────
    cfScoreEnabled: false,
    overridesEnabled: false,

    // ── Unsaved-changes tracking per panel ──────────────────────────────
    unsaved: {
      settings: false, pipelines: false, overrides: false,
      notifications: false, advanced: false,
      filtersRadarr: false, filtersSonarr: false,
    },

    // ── Sweep / Status ───────────────────────────────────────────────────
    version: '',
    sweeping: false,
    schedulerEnabled: false,   // ONLY set from applyConfig() — never from scheduler_running
    lastRunUtc: null,
    nextRunUtc: null,
    nextRunInMaintenanceWindow: false,
    containerTime: '',
    instanceHealth: {},
    sweepLifetime: {},
    importsConfirmedSweep: { movies: 0, shows: 0 },
    lastSweepStartUtc: null,
    lastSkippedQueueDepthUtc: null,
    lastSummary: { radarr: [], sonarr: [] },
    lastRunCutoffUtc: null,
    lastRunBacklogUtc: null,
    lastRunCfscoreUtc: null,
    lastError: null,
    _wasRunning: false,
    _autoRefreshLast: 0,

    // ── Library ──────────────────────────────────────────────────────────
    libView: 'history',

    // History
    historyItems: [],
    historyTotal: 0,
    historyPage: 0,
    historyPageSize: 25,
    historySearch: '',
    historyInstance: '',
    historyType: '',
    historySort: { col: 'last_searched', dir: 'desc' },
    exclusionsData: [],
    exclusionsSet: new Set(),
    exclBadge: 0,
    summaryKpis: [],

    // Imports
    importsItems: [],
    importsTotal: 0,
    importsPage: 0,
    importsPageSize: 25,
    importsSearch: '',
    importsInstance: '',
    importsType: '',
    importsSort: { col: 'imported_ts', dir: 'desc' },
    importsPeriod: (function() { try { return localStorage.getItem('nudgarr_imports_period') || 'lifetime'; } catch(e) { return 'lifetime'; } })(),
    importsMoviesTotal: 0,
    importsShowsTotal: 0,
    importsAvailableInstances: [],
    importsAvailableTypes: [],

    // CF Score entries
    cfEntries: [],
    cfTotal: 0,
    cfPage: 0,
    cfPageSize: 25,
    cfSearch: '',
    cfInstanceFilter: '',
    cfStatusData: null,

    // Exclusions view
    exclusionItems: [],
    exclSearch: '',
    exclInstance: '',
    exclType: '',
    exclPageSize: 25,
    exclPage: 0,
    exclTotal: 0,

    // ── Save messages (inline, no modal on success) ───────────────────────
    saveMsg: { pipelines: '', settings: '', notifications: '', advanced: '', filters: '' },
    saveMsgOk: { pipelines: true, settings: true, notifications: true, advanced: true, filters: true },

    // ── Intel ────────────────────────────────────────────────────────────
    intelData: null,

    // ── Instances ────────────────────────────────────────────────────────
    instMsg: '',
    instMsgClass: '',
    instModal: {
      show: false, kind: 'radarr', idx: -1,
      name: '', url: '', key: '', keyVisible: false,
      testStatus: '', testMsg: '', testDone: false, testOk: false,
      urlWarn: false, isEdit: false,
      title: '', namePlaceholder: '', urlPlaceholder: '', keyLabel: '', keyPlaceholder: '',
    },
    cfg: null,

    // ── Pipelines ────────────────────────────────────────────────────────
    radarrCutoffEnabled: true,
    sonarrCutoffEnabled: true,
    radarrMaxCutoff: 25,
    sonarrMaxCutoff: 25,
    radarrSampleMode: 'round_robin',
    sonarrSampleMode: 'round_robin',

    radarrBacklogEnabled: false,
    sonarrBacklogEnabled: false,
    radarrMissingMax: 1,
    sonarrMissingMax: 1,
    radarrMissingAddedDays: 14,
    radarrMissingGraceHours: 0,
    sonarrMissingGraceHours: 0,
    radarrBacklogSampleMode: 'round_robin',
    sonarrBacklogSampleMode: 'round_robin',

    cfEnabled: false,
    cfSyncCron: '0 0 * * *',
    cfCronHint: '',
    cfCronValid: null,
    radarrCfMax: 25,
    sonarrCfMax: 25,
    radarrCfSampleMode: 'largest_gap_first',
    sonarrCfSampleMode: 'largest_gap_first',
    radarrCfScoreAppEnabled: true,
    sonarrCfScoreAppEnabled: true,

    // ── Overrides ────────────────────────────────────────────────────────
    ovData: {},
    ovDirty: {},
    overridesInfoSeen: false,

    // ── Filters ──────────────────────────────────────────────────────────
    radarrFilters: { loaded: false, instanceIdx: 0, tags: [], profiles: [], excludedTagIds: [], excludedProfileIds: [], tagSearch: '', profileSearch: '', loading: false },
    sonarrFilters: { loaded: false, instanceIdx: 0, tags: [], profiles: [], excludedTagIds: [], excludedProfileIds: [], tagSearch: '', profileSearch: '', loading: false },

    // ── Settings ─────────────────────────────────────────────────────────
    schedulerEnabledUi: false,
    cronExpr: '0 */6 * * *',
    cronHint: '',
    cronValid: null,
    cooldownHours: 48,
    maintenanceEnabled: false,
    maintenanceStart: '23:00',
    maintenanceEnd: '07:00',
    maintenanceDays: [0,1,2,3,4,5,6],
    maintHint: '',
    batchSize: 1,
    sleepSeconds: 5,
    jitterSeconds: 2,
    queueDepthEnabled: false,
    queueDepthThreshold: 10,
    perInstanceOverridesEnabled: false,
    radarrAutoExclEnabled: false,
    sonarrAutoExclEnabled: false,
    autoExclMoviesThreshold: 0,
    autoExclShowsThreshold: 0,
    autoUnexclMoviesDays: 0,
    autoUnexclShowsDays: 0,

    // ── Notifications ────────────────────────────────────────────────────
    notifyEnabled: false,
    notifyUrl: '',
    notifyUrlVisible: false,
    notifyOnSweep: true,
    notifyOnImport: true,
    notifyOnAutoExcl: true,
    notifyOnError: true,
    notifyOnQueueDepth: false,
    notifTestMsg: '',
    notifTestMsgClass: '',

    // ── Advanced ─────────────────────────────────────────────────────────
    authEnabled: false,
    sessionTimeout: 60,
    importCheckMinutes: 120,
    logLevel: 'INFO',
    defaultTab: 'sweep',
    showSupportLink: true,
    retentionDays: 180,

    // ── Modals ───────────────────────────────────────────────────────────
    modal: null,
    confirmAction: null,
    alertMsg: '',
    alertType: 'error',   // 'error' | 'success'
    clearExclOpt: null,
    _confirmResolve: null,

    // ── Onboarding ───────────────────────────────────────────────────────
    onboardingStep: 0,
    onboardingTotal: 8,

    // ── Computed ─────────────────────────────────────────────────────────

    get autoMode() { return this.schedulerEnabled ? 'AUTO' : 'MANUAL'; },

    get topbarTitle() {
      const m = { sweep:'Sweep', library:'Library', intel:'Intel', instances:'Instances', pipelines:'Pipelines', settings:'Settings', overrides:'Overrides', filters:'Filters', notifications:'Notifications', advanced:'Advanced' };
      return m[this.panel] || '';
    },

    get topbarSub() {
      if (!this.cfg) return '';
      const radarrCount = (this.cfg.instances?.radarr || []).length;
      const sonarrCount = (this.cfg.instances?.sonarr || []).length;
      const totalInst = radarrCount + sonarrCount;
      const instStr = totalInst ? totalInst + ' instance' + (totalInst !== 1 ? 's' : '') : 'No instances';
      const activePipelines = [
        this.radarrCutoffEnabled || this.sonarrCutoffEnabled,
        this.radarrBacklogEnabled || this.sonarrBacklogEnabled,
        this.cfEnabled,
      ].filter(Boolean).length;
      const disabledNames = [
        !this.radarrBacklogEnabled && !this.sonarrBacklogEnabled ? 'Backlog' : null,
        !this.cfEnabled ? 'CF Score' : null,
      ].filter(Boolean);
      const pipelineSub = disabledNames.length
        ? activePipelines + ' pipeline' + (activePipelines !== 1 ? 's' : '') + ' \u00b7 ' + disabledNames.join(', ') + ' disabled'
        : activePipelines + ' pipeline' + (activePipelines !== 1 ? 's' : '');
      const m = {
        sweep: instStr + ' \u00b7 ' + pipelineSub,
        library: 'History \u00b7 Imports \u00b7 CF Score \u00b7 Exclusions',
        intel: 'Lifetime performance data',
        instances: radarrCount ? radarrCount + ' Radarr \u00b7 ' + sonarrCount + ' Sonarr' : 'No instances configured',
        pipelines: pipelineSub,
        settings: 'Scheduler, throttling, auto-exclusion',
        overrides: totalInst + ' instance' + (totalInst !== 1 ? 's' : ''),
        filters: 'Tag and quality profile exclusions per instance',
        notifications: this.notifyEnabled ? '1 agent configured' : 'No agents configured',
        advanced: 'Auth, retention, diagnostics',
      };
      return m[this.panel] || '';
    },

    // Topbar status
    get lastRunDisplay() {
      if (this.lastSkippedQueueDepthUtc) return 'Queue Skip';
      if (!this.lastRunUtc) return 'Never';
      return this.formatRelative(new Date(this.lastRunUtc).getTime(), false);
    },

    get nextRunDisplay() {
      if (!this.schedulerEnabled) return 'Manual';
      if (!this.nextRunUtc) return 'Unavailable';
      return this.formatRelative(new Date(this.nextRunUtc).getTime(), true);
    },

    get nextRunColor() {
      if (!this.schedulerEnabled) return 'color:var(--muted)';
      if (!this.nextRunUtc) return 'color:var(--muted)';
      if (new Date(this.nextRunUtc).getTime() < Date.now()) return 'color:var(--warn)';
      return 'color:var(--ok)';
    },

    get topbarDotClass() {
      if (this.sweeping) return 'warn';
      if (!this.schedulerEnabled) return 'muted';
      if (this.nextRunUtc && new Date(this.nextRunUtc).getTime() < Date.now()) return 'warn';
      return '';
    },

    get sweepHealthState() {
      if (this.lastError) return 'error';
      const bad = Object.values(this.instanceHealth).filter(v => v === 'bad').length;
      return bad > 0 ? 'warn' : 'ok';
    },

    get sweepHealthMsg() {
      if (this.lastError) return 'Sweep Failed';
      const bad = Object.entries(this.instanceHealth).filter(([,v]) => v === 'bad');
      if (bad.length) return bad.length + ' Instance' + (bad.length > 1 ? 's' : '') + ' Unreachable';
      return 'All Instances Healthy';
    },

    get lifetimeRuns() {
      let r = 0;
      for (const row of Object.values(this.sweepLifetime)) r += row.runs || 0;
      return r;
    },

    get lifetimeAvgPerRun() {
      let r = 0, s = 0;
      for (const row of Object.values(this.sweepLifetime)) { r += row.runs || 0; s += row.searched || 0; }
      return r > 0 ? (s / r).toFixed(1) : '0';
    },

    get allInstances() {
      if (!this.cfg) return [];
      const out = [];
      (this.cfg.instances?.radarr || []).forEach(i => out.push({ key: i.name + '|' + (i.url || '').replace(/\/$/, ''), name: i.name, app: 'radarr' }));
      (this.cfg.instances?.sonarr || []).forEach(i => out.push({ key: i.name + '|' + (i.url || '').replace(/\/$/, ''), name: i.name, app: 'sonarr' }));
      return out;
    },

    get hasInstances() {
      if (!this.cfg) return false;
      return (this.cfg.instances?.radarr || []).length > 0 || (this.cfg.instances?.sonarr || []).length > 0;
    },

    get cutoffAgg() { return this._pipelineAgg('cutoff'); },
    get backlogAgg() { return this._pipelineAgg('backlog'); },
    get cfscoreAgg() { return this._pipelineAgg('cfscore'); },

    get cutoffInstRows() { return this._pipelineInstRows('cutoff'); },
    get backlogInstRows() { return this._pipelineInstRows('backlog'); },
    get cfscoreInstRows() { return this._pipelineInstRows('cfscore'); },

    get overrideInstances() {
      if (!this.cfg) return [];
      const out = [];
      (this.cfg.instances?.radarr || []).forEach((inst, idx) => out.push({ kind: 'radarr', idx, name: inst.name, enabled: inst.enabled }));
      (this.cfg.instances?.sonarr || []).forEach((inst, idx) => out.push({ kind: 'sonarr', idx, name: inst.name, enabled: inst.enabled }));
      return out;
    },

    get overrideColumns() {
      if (!this.cfg) {
        return [
          { title: 'Radarr Instances', insts: [] },
          { title: 'Sonarr Instances', insts: [] },
        ];
      }
      const rad = [];
      (this.cfg.instances?.radarr || []).forEach((inst, idx) => rad.push({ kind: 'radarr', idx, name: inst.name, enabled: inst.enabled }));
      const son = [];
      (this.cfg.instances?.sonarr || []).forEach((inst, idx) => son.push({ kind: 'sonarr', idx, name: inst.name, enabled: inst.enabled }));
      return [
        { title: 'Radarr Instances', insts: rad },
        { title: 'Sonarr Instances', insts: son },
      ];
    },

    get radarrInstances() { return (this.cfg?.instances?.radarr || []); },
    get sonarrInstances() { return (this.cfg?.instances?.sonarr || []); },

    get historyPageCount() { return Math.max(1, Math.ceil(this.historyTotal / this.historyPageSize)); },
    get importsPageCount() { return Math.max(1, Math.ceil(this.importsTotal / this.importsPageSize)); },
    get cfPageCount() { return Math.max(1, Math.ceil(this.cfTotal / this.cfPageSize)); },

    get exclPageCount() { return Math.max(1, Math.ceil(this.exclTotal / this.exclPageSize)); },
    get hasExclusions() { return this.exclusionsData.length > 0; },

    get onboardingIsFirst() { return this.onboardingStep === 0; },
    get onboardingIsLast() { return this.onboardingStep === this.onboardingTotal - 1; },

    get cfCronRowInteractive() {
      return this.cfEnabled && (this.radarrCfScoreAppEnabled || this.sonarrCfScoreAppEnabled);
    },

    get cfStatusSyncCoverage() {
      if (!this.cfStatusData) return [];
      return (this.cfStatusData.instances || []).map(row => {
        const sp = row.sync_progress;
        let coverage = 0;
        if (row.cf_enabled === false) {
          coverage = 0;
        } else if (sp && sp.total > 0) {
          coverage = Math.min(100, Math.round((sp.processed / sp.total) * 100));
        } else if (sp && sp.in_progress) {
          coverage = 0;
        } else if (sp && !sp.in_progress) {
          // Sync finished for this instance (includes total===0 libraries)
          coverage = 100;
        } else if (row.last_synced_at) {
          coverage = 100;
        }
        return { ...row, coverage };
      });
    },

    cfIndexLastSyncText(row) {
      const t = row.last_synced_at;
      if (!t) return 'Never';
      return this.formatRelative(new Date(t).getTime(), false);
    },

    cfIndexStatusSubtitle(row) {
      const sp = row.sync_progress;
      if (sp && sp.in_progress && sp.total > 0) {
        return (sp.processed ?? 0) + ' / ' + sp.total + ' scanned';
      }
      const b = row.below_cutoff ?? 0;
      return b + ' Below CF Score \u00b7 Last Sync ' + this.cfIndexLastSyncText(row);
    },

    // ── Init ─────────────────────────────────────────────────────────────

    async init() {
      let _pingTimer = null;
      const _doPing = () => fetch('/api/ping', { method: 'POST', credentials: 'same-origin' }).catch(() => {});
      const _onActivity = () => { if (_pingTimer) return; _doPing(); _pingTimer = setTimeout(() => { _pingTimer = null; }, 15000); };
      ['click', 'keydown', 'scroll', 'touchstart'].forEach(ev => document.addEventListener(ev, _onActivity, { passive: true }));

      window.addEventListener('unhandledrejection', ev => console.error('[unhandled]', ev.reason?.message || ev.reason));

      try {
        await this.loadAll();
        await this.maybeShowOnboarding();
        if (this.cfg && this.cfg.onboarding_complete) await this.maybeShowWhatsNew();
      } catch (e) {
        this.showAlert('Failed to load \u2014 please refresh the page. (' + e.message + ')', 'error');
      }

      setInterval(() => this.pollCycle(), 5000);
    },

    // ── API helper ───────────────────────────────────────────────────────

    async _api(path, opts) {
      const r = await fetch(path, opts || {});
      if (r.status === 401) { window.location.href = '/login'; return; }
      const ct = r.headers.get('content-type') || '';
      const data = ct.includes('application/json') ? await r.json() : await r.text();
      if (!r.ok) throw new Error(typeof data === 'string' ? data : (data.error || JSON.stringify(data)));
      return data;
    },

    _post(path, body) {
      return this._api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    },

    // ── Load all ─────────────────────────────────────────────────────────

    async loadAll() {
      this.cfg = await this._api('/api/config');
      const st = await this._api('/api/status');
      this.version = st.version || '';
      this.applyStatus(st);
      this.applyConfig();
      await this.loadExclusions();
    },

    applyConfig() {
      if (!this.cfg) return;
      // CRITICAL: schedulerEnabled only set here
      this.schedulerEnabled = !!this.cfg.scheduler_enabled;
      this.cfScoreEnabled = !!this.cfg.cf_score_enabled;
      this.overridesEnabled = !!this.cfg.per_instance_overrides_enabled;

      this.schedulerEnabledUi = !!this.cfg.scheduler_enabled;
      this.cronExpr = this.cfg.cron_expression || '0 */6 * * *';
      this.cooldownHours = this.cfg.cooldown_hours ?? 48;
      this.maintenanceEnabled = !!this.cfg.maintenance_window_enabled;
      this.maintenanceStart = this.cfg.maintenance_window_start || '23:00';
      this.maintenanceEnd = this.cfg.maintenance_window_end || '07:00';
      this.maintenanceDays = this.cfg.maintenance_window_days || [0,1,2,3,4,5,6];
      this.batchSize = this.cfg.batch_size ?? 1;
      this.sleepSeconds = this.cfg.sleep_seconds ?? 5;
      this.jitterSeconds = this.cfg.jitter_seconds ?? 2;
      this.queueDepthEnabled = !!this.cfg.queue_depth_enabled;
      this.queueDepthThreshold = this.cfg.queue_depth_threshold ?? 10;
      this.perInstanceOverridesEnabled = !!this.cfg.per_instance_overrides_enabled;
      this.overridesInfoSeen = !!this.cfg.per_instance_overrides_seen;
      this.radarrAutoExclEnabled = !!this.cfg.radarr_auto_exclude_enabled;
      this.sonarrAutoExclEnabled = !!this.cfg.sonarr_auto_exclude_enabled;
      this.autoExclMoviesThreshold = this.cfg.auto_exclude_movies_threshold ?? 0;
      this.autoExclShowsThreshold = this.cfg.auto_exclude_shows_threshold ?? 0;
      this.autoUnexclMoviesDays = this.cfg.auto_unexclude_movies_days ?? 0;
      this.autoUnexclShowsDays = this.cfg.auto_unexclude_shows_days ?? 0;

      this.radarrCutoffEnabled = this.cfg.radarr_cutoff_enabled !== false;
      this.sonarrCutoffEnabled = this.cfg.sonarr_cutoff_enabled !== false;
      this.radarrMaxCutoff = this.cfg.radarr_max_movies_per_run ?? 25;
      this.sonarrMaxCutoff = this.cfg.sonarr_max_episodes_per_run ?? 25;
      this.radarrSampleMode = this.cfg.radarr_sample_mode || 'round_robin';
      this.sonarrSampleMode = this.cfg.sonarr_sample_mode || 'round_robin';
      this.radarrBacklogEnabled = !!this.cfg.radarr_backlog_enabled;
      this.sonarrBacklogEnabled = !!this.cfg.sonarr_backlog_enabled;
      this.radarrMissingMax = this.cfg.radarr_missing_max ?? 1;
      this.sonarrMissingMax = this.cfg.sonarr_missing_max ?? 1;
      this.radarrMissingAddedDays = this.cfg.radarr_missing_added_days ?? 14;
      this.radarrMissingGraceHours = this.cfg.radarr_missing_grace_hours ?? 0;
      this.sonarrMissingGraceHours = this.cfg.sonarr_missing_grace_hours ?? 0;
      this.radarrBacklogSampleMode = this.cfg.radarr_backlog_sample_mode || 'round_robin';
      this.sonarrBacklogSampleMode = this.cfg.sonarr_backlog_sample_mode || 'round_robin';
      this.cfEnabled = !!this.cfg.cf_score_enabled;
      this.cfSyncCron = this.cfg.cf_score_sync_cron || '0 0 * * *';
      this.radarrCfMax = this.cfg.radarr_cf_max_per_run ?? 25;
      this.sonarrCfMax = this.cfg.sonarr_cf_max_per_run ?? 25;
      this.radarrCfSampleMode = this.cfg.radarr_cf_sample_mode || 'largest_gap_first';
      this.sonarrCfSampleMode = this.cfg.sonarr_cf_sample_mode || 'largest_gap_first';
      this.radarrCfScoreAppEnabled = this.cfg.radarr_cf_score_enabled !== false;
      this.sonarrCfScoreAppEnabled = this.cfg.sonarr_cf_score_enabled !== false;

      this.notifyEnabled = !!this.cfg.notify_enabled;
      this.notifyUrl = this.cfg.notify_url || '';
      this.notifyOnSweep = this.cfg.notify_on_sweep_complete !== false;
      this.notifyOnImport = this.cfg.notify_on_import !== false;
      this.notifyOnAutoExcl = this.cfg.notify_on_auto_exclusion !== false;
      this.notifyOnError = this.cfg.notify_on_error !== false;
      this.notifyOnQueueDepth = !!this.cfg.notify_on_queue_depth_skip;

      this.authEnabled = this.cfg.auth_enabled !== false;
      this.sessionTimeout = this.cfg.auth_session_minutes ?? 60;
      this.importCheckMinutes = this.cfg.import_check_minutes ?? 120;
      this.logLevel = this.cfg.log_level || 'INFO';
      this.defaultTab = this.cfg.default_tab || 'sweep';
      this.showSupportLink = this.cfg.show_support_link !== false;
      this.retentionDays = this.cfg.state_retention_days ?? 180;

      this.validateCron();
      this.validateCfCron();
      this.validateMaintTime();
    },

    applyStatus(st) {
      if (!st) return;
      this.sweeping = !!st.run_in_progress;
      this.lastRunUtc = st.last_run_utc || null;
      this.nextRunUtc = st.next_run_utc || null;
      this.nextRunInMaintenanceWindow = !!st.next_run_in_maintenance_window;
      this.containerTime = st.container_time || '';
      this.instanceHealth = st.instance_health || {};
      this.sweepLifetime = st.sweep_lifetime || {};
      this.importsConfirmedSweep = st.imports_confirmed_sweep || { movies: 0, shows: 0 };
      this.lastSweepStartUtc = st.last_sweep_start_utc || null;
      this.lastSkippedQueueDepthUtc = st.last_skipped_queue_depth_utc || null;
      this.lastSummary = st.last_summary || { radarr: [], sonarr: [] };
      this.lastRunCutoffUtc = st.last_run_cutoff_utc || null;
      this.lastRunBacklogUtc = st.last_run_backlog_utc || null;
      this.lastRunCfscoreUtc = st.last_run_cfscore_utc || null;
      this.lastError = st.last_error || null;
    },

    // ── Poll cycle ───────────────────────────────────────────────────────

    async pollCycle() {
      try {
        const st = await this._api('/api/status');
        this.version = st.version || this.version;
        const isRunning = !!st.run_in_progress;
        this.sweeping = isRunning;
        this.nextRunUtc = st.next_run_utc || null;
        this.nextRunInMaintenanceWindow = !!st.next_run_in_maintenance_window;
        this.instanceHealth = st.instance_health || {};
        this.sweepLifetime = st.sweep_lifetime || {};
        this.importsConfirmedSweep = st.imports_confirmed_sweep || { movies: 0, shows: 0 };
        this.lastSweepStartUtc = st.last_sweep_start_utc || null;
        this.lastSkippedQueueDepthUtc = st.last_skipped_queue_depth_utc || null;
        this.lastSummary = st.last_summary || { radarr: [], sonarr: [] };
        this.lastRunCutoffUtc = st.last_run_cutoff_utc || null;
        this.lastRunBacklogUtc = st.last_run_backlog_utc || null;
        this.lastRunCfscoreUtc = st.last_run_cfscore_utc || null;
        this.lastError = st.last_error || null;
        if (!isRunning) {
          this.lastRunUtc = st.last_run_utc || null;
          this.containerTime = st.container_time || '';
        }
        if (this._wasRunning && !isRunning) {
          this._autoRefreshLast = 0;
          if (this.panel === 'library') this.refreshHistory();
        }
        this._wasRunning = isRunning;
        const now = Date.now();
        if (now - this._autoRefreshLast >= 30000) {
          this._autoRefreshLast = now;
          if (this.panel === 'library' && this.libView === 'history') this.refreshHistory();
          if (this.panel === 'library' && this.libView === 'imports') this.refreshImports();
        }
        if (this.cfScoreEnabled && (
          this.panel === 'pipelines' ||
          (this.panel === 'library' && this.libView === 'cfscores') ||
          (this.cfStatusData && this.cfStatusData.scan_in_progress)
        )) {
          await this.refreshCfStatusOnly();
        }
      } catch (e) {
        console.warn('[poll] failed:', e.message);
      }
    },

    // ── Navigation ───────────────────────────────────────────────────────

    navigateTo(name) {
      this.panel = name;
      this.mobileDrawerOpen = false;
      if (this.cfg && this.cfg.onboarding_complete) {
        try { localStorage.setItem('nudgarr_last_tab', name); } catch (_) {}
      }
      if (name === 'library' && this.libView === 'history') this.refreshHistory();
      if (name === 'library' && this.libView === 'imports') this.refreshImports();
      if (name === 'library' && this.libView === 'cfscores') this.refreshCfScores();
      if (name === 'library' && this.libView === 'exclusions') void this.onExclusionsTabShown();
      if (name === 'pipelines' && this.cfScoreEnabled) this.refreshCfStatusOnly();
      if (name === 'intel') this.refreshIntel();
      if (name === 'overrides') this._buildOverrideData();
    },

    setLibView(v) {
      if (v === 'cfscores' && !this.cfScoreEnabled) { this.libView = 'history'; return; }
      this.libView = v;
      if (v === 'history') this.refreshHistory();
      if (v === 'imports') this.refreshImports();
      if (v === 'cfscores') this.refreshCfScores();
      if (v === 'exclusions') void this.onExclusionsTabShown();
    },

    // ── Sweep ────────────────────────────────────────────────────────────

    _pipelineAgg(type) {
      const all = [...(this.lastSummary.radarr || []), ...(this.lastSummary.sonarr || [])];
      if (type === 'cutoff') {
        const r = { searched: 0, cooldown: 0, capped: 0, excluded: 0, tag: 0, profile: 0 };
        for (const s of all) { r.searched += s.searched||0; r.cooldown += s.skipped_cooldown||0; r.capped += Math.max(0,(s.eligible||0)-(s.searched||0)); r.excluded += s.skipped_excluded_cutoff||0; r.tag += s.skipped_tag_cutoff||0; r.profile += s.skipped_profile_cutoff||0; }
        return r;
      }
      if (type === 'backlog') {
        const r = { searched: 0, cooldown: 0, capped: 0, grace: 0, tag: 0, profile: 0 };
        for (const s of all) { r.searched += s.searched_missing||0; r.cooldown += s.skipped_missing_cooldown||0; r.capped += Math.max(0,(s.eligible_missing||0)-(s.searched_missing||0)); r.grace += s.skipped_grace||0; r.tag += s.skipped_tag_backlog||0; r.profile += s.skipped_profile_backlog||0; }
        return r;
      }
      const r = { searched: 0, cooldown: 0, excluded: 0, queued: 0 };
      for (const s of all) { r.searched += s.searched_cf||0; r.cooldown += s.skipped_cf_cooldown||0; r.excluded += s.skipped_cf_excluded||0; r.queued += s.skipped_cf_queued||0; }
      return r;
    },

    _pipelineInstRows(type) {
      if (!this.cfg) return [];
      const rows = [];
      const all = [...(this.lastSummary.radarr || []), ...(this.lastSummary.sonarr || [])];
      for (const kind of ['radarr', 'sonarr']) {
        for (const inst of (this.cfg.instances?.[kind] || [])) {
          const hk = kind + '|' + inst.name;
          const dot = this.instanceHealth[hk] || 'unknown';
          const s = all.find(x => x.name === inst.name);
          const disabled = inst.enabled === false;
          let v1, v2, v3;
          if (type === 'cutoff') { v1 = s?(s.searched||0):null; v2 = s?(s.skipped_cooldown||0):null; v3 = s?(s.skipped_excluded_cutoff||0):null; }
          else if (type === 'backlog') { v1 = s?(s.searched_missing||0):null; v2 = s?(s.skipped_missing_cooldown||0):null; v3 = s?((s.skipped_tag_backlog||0)+(s.skipped_profile_backlog||0)):null; }
          else { v1 = s?(s.searched_cf||0):null; v2 = s?(s.skipped_cf_cooldown||0):null; v3 = s?(s.skipped_cf_excluded||0):null; }
          rows.push({ name: inst.name, dot, disabled, v1, v2, v3 });
        }
      }
      return rows;
    },

    async runNow() {
      if (!this.hasInstances) { this.openModal('noInstances'); return; }
      try {
        await this._api('/api/run-now', { method: 'POST' });
        this.sweeping = true;
      } catch (e) {
        this.showAlert('Run request failed: ' + e.message, 'error');
      }
    },

    // ── Library — Exclusions ──────────────────────────────────────────────

    /** Mark auto-exclusions as seen server-side so the badge stays cleared. */
    async onExclusionsTabShown() {
      try {
        await this._api('/api/exclusions/acknowledge', { method: 'POST' });
      } catch (e) { console.warn('[excl ack]', e.message); }
      this.exclBadge = 0;
      await this.refreshExclusions();
    },

    async loadExclusions() {
      try {
        const data = await this._api('/api/exclusions');
        this.exclusionsData = data || [];
        this.exclusionsSet = new Set(this.exclusionsData.map(e => (e.title || '').toLowerCase()));
        await this.refreshAutoExclBadge();
      } catch (e) { console.warn('[excl]', e.message); }
    },

    async refreshAutoExclBadge() {
      try {
        const data = await this._api('/api/exclusions/unacknowledged-count');
        this.exclBadge = data?.count ?? 0;
      } catch (e) { /* silent */ }
    },

    isExcluded(title) { return this.exclusionsSet.has((title || '').toLowerCase()); },

    async toggleExclusion(title, searchCount) {
      const isExcl = this.isExcluded(title);
      const body = { title };
      if (!isExcl && searchCount != null && searchCount !== '') body.search_count = searchCount;
      await this._api(isExcl ? '/api/exclusions/remove' : '/api/exclusions/add', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      await this.loadExclusions();
      if (this.libView === 'history') this.refreshHistory();
    },

    // ── Library — History ────────────────────────────────────────────────

    async refreshHistory(page) {
      if (page !== undefined) this.historyPage = page;
      try {
        const sum = await this._api('/api/state/summary');
        this.summaryKpis = this.allInstances.map(inst => {
          const count = (sum.per_instance?.[inst.app]?.[inst.key]) || 0;
          return { name: inst.name, count, app: inst.app, key: inst.key };
        });

        const limit = this.historyPageSize;
        const offset = this.historyPage * limit;
        let url = '/api/state/items?limit=' + limit + '&offset=' + offset;
        if (this.historyInstance) url += '&instance=' + encodeURIComponent(this.historyInstance);
        if (this.historyType) url += '&type=' + encodeURIComponent(this.historyType);
        if (this.historySearch) url += '&search=' + encodeURIComponent(this.historySearch);
        const data = await this._api(url);
        this.historyItems = this._sortItems(data.items || [], this.historySort.col, this.historySort.dir);
        this.historyTotal = data.total || 0;
      } catch (e) { console.warn('[history]', e.message); }
    },

    sortHistory(col) {
      if (this.historySort.col === col) this.historySort.dir = this.historySort.dir === 'asc' ? 'desc' : 'asc';
      else { this.historySort.col = col; this.historySort.dir = 'asc'; }
      this.historyPage = 0;
      this.refreshHistory();
    },

    prevHistoryPage() { if (this.historyPage > 0) this.refreshHistory(this.historyPage - 1); },
    nextHistoryPage() { if (this.historyPage < this.historyPageCount - 1) this.refreshHistory(this.historyPage + 1); },

    _goToLibraryPageInput(el, maxPages, refresh) {
      const n = parseInt(String(el && el.value != null ? el.value : '').trim(), 10);
      if (el) el.value = '';
      if (Number.isNaN(n)) return;
      const max = Math.max(1, Math.floor(maxPages));
      refresh(Math.min(Math.max(1, n), max) - 1);
    },
    goToHistoryPageInput(el) { this._goToLibraryPageInput(el, this.historyPageCount, (p) => this.refreshHistory(p)); },
    goToImportsPageInput(el) { this._goToLibraryPageInput(el, this.importsPageCount, (p) => this.refreshImports(p)); },
    goToCfPageInput(el) { this._goToLibraryPageInput(el, this.cfPageCount, (p) => this.refreshCfScores(p)); },
    goToExclPageInput(el) { this._goToLibraryPageInput(el, this.exclPageCount, (p) => this.refreshExclusions(p)); },

    async pruneState() {
      try { await this._api('/api/state/prune', { method: 'POST' }); this.historyPage = 0; this.refreshHistory(); }
      catch (e) { this.showAlert('Prune failed: ' + e.message, 'error'); }
    },

    openClearExclModal() { this.clearExclOpt = null; this.openModal('clearExcl'); },

    async confirmClearExcl() {
      if (!this.clearExclOpt) return;
      const ep = this.clearExclOpt === 'auto' ? '/api/exclusions/clear-auto' : this.clearExclOpt === 'manual' ? '/api/exclusions/clear-manual' : '/api/exclusions/clear-all';
      try { await this._api(ep, { method: 'POST' }); this.closeModal(); await this.loadExclusions(); this.refreshHistory(); }
      catch (e) { this.showAlert('Clear failed: ' + e.message, 'error'); }
    },

    eligibleDisplay(item) {
      const title = item.title || item.key || '';
      if (!this.isExcluded(title)) {
        if (item.eligible_again === 'Next Sweep') return { cls: 'eligible-next-sweep', text: 'Next Sweep' };
        if (item.eligible_again) {
          try {
            const ts = new Date(item.eligible_again).getTime();
            if (!isNaN(ts)) {
              if (ts <= Date.now()) return { cls: 'eligible-next-sweep', text: 'Next Sweep' };
              return { cls: 'td-blue-dim', text: 'In ' + this.formatRelative(ts, true) };
            }
          } catch (_) {}
        }
        return { cls: 'td-muted', text: '\u2014' };
      }
      return { cls: 'td-muted', text: '\u2014' };
    },

    // ── Library — Imports ────────────────────────────────────────────────

    async refreshImports(page) {
      if (page !== undefined) this.importsPage = page;
      try {
        try { localStorage.setItem('nudgarr_imports_period', this.importsPeriod); } catch (_) {}
        const limit = this.importsPageSize;
        const offset = this.importsPage * limit;
        let url = '/api/stats?offset=' + offset + '&limit=' + limit + '&period=' + encodeURIComponent(this.importsPeriod);
        if (this.importsInstance) url += '&instance=' + encodeURIComponent(this.importsInstance);
        if (this.importsType) url += '&type=' + encodeURIComponent(this.importsType);
        // Bug #3: /api/stats returns data.entries
        const data = await this._api(url);
        this.importsItems = data.entries || [];
        this.importsTotal = data.total || 0;
        // Bug #4 / #18: totals come from API
        this.importsMoviesTotal = data.movies_total ?? 0;
        this.importsShowsTotal = data.shows_total ?? 0;
        this.importsAvailableInstances = data.instances || [];
        this.importsAvailableTypes = data.types || [];
        this.importsItems = this._sortItems(this.importsItems, this.importsSort.col, this.importsSort.dir);
      } catch (e) { console.warn('[imports]', e.message); }
    },

    sortImports(col) {
      if (this.importsSort.col === col) this.importsSort.dir = this.importsSort.dir === 'asc' ? 'desc' : 'asc';
      else { this.importsSort.col = col; this.importsSort.dir = 'asc'; }
      this.importsPage = 0;
      this.refreshImports();
    },

    prevImportsPage() { if (this.importsPage > 0) this.refreshImports(this.importsPage - 1); },
    nextImportsPage() { if (this.importsPage < this.importsPageCount - 1) this.refreshImports(this.importsPage + 1); },

    async checkImportsNow() {
      try { await this._api('/api/stats/check-imports', { method: 'POST' }); this.refreshImports(); }
      catch (e) { this.showAlert('Check failed: ' + e.message, 'error'); }
    },

    // ── Library — CF Score ────────────────────────────────────────────────

    async refreshCfStatusOnly() {
      if (!this.cfg?.cf_score_enabled) return;
      try {
        this.cfStatusData = await this._api('/api/cf-scores/status');
      } catch (e) { console.warn('[cf-status]', e.message); }
    },

    async refreshCfScores(page) {
      if (page !== undefined) this.cfPage = page;
      try {
        let url = '/api/cf-scores/entries?offset=' + (this.cfPage * this.cfPageSize) + '&limit=' + this.cfPageSize;
        if (this.cfInstanceFilter) url += '&instance_id=' + encodeURIComponent(this.cfInstanceFilter);
        if (this.cfSearch) url += '&search=' + encodeURIComponent(this.cfSearch);
        const data = await this._api(url);
        this.cfEntries = data.entries || [];
        this.cfTotal = data.total || 0;
        this.cfStatusData = await this._api('/api/cf-scores/status');
      } catch (e) { console.warn('[cfscores]', e.message); }
    },

    prevCfPage() { if (this.cfPage > 0) this.refreshCfScores(this.cfPage - 1); },
    nextCfPage() { if (this.cfPage < this.cfPageCount - 1) this.refreshCfScores(this.cfPage + 1); },

    cfLastSync() {
      return this.cfStatusData?.last_sync_at ? this.formatRelative(new Date(this.cfStatusData.last_sync_at).getTime(), false) : 'Never';
    },

    cfIndexedCount() { return this.cfStatusData?.stats?.total_indexed ?? 0; },

    async scanCfLibrary() {
      try { await this._api('/api/cf-scores/scan', { method: 'POST' }); this.refreshCfScores(); }
      catch (e) { this.showAlert('Scan failed: ' + e.message, 'error'); }
    },

    async resetCfIndex() {
      try { await this._api('/api/cf-scores/reset', { method: 'POST' }); this.refreshCfScores(); }
      catch (e) { this.showAlert('Reset failed: ' + e.message, 'error'); }
    },

    // ── Library — Exclusions view ─────────────────────────────────────────

    async refreshExclusions(page) {
      if (page !== undefined) this.exclPage = page;
      await this.loadExclusions();
      let items = [...this.exclusionsData];
      if (this.exclInstance) items = items.filter(e => (e.instance_name || e.instance || '') === this.exclInstance);
      if (this.exclType) items = items.filter(e => this.exclType === 'auto' ? e.source === 'auto' : e.source !== 'auto');
      if (this.exclSearch) { const q = this.exclSearch.toLowerCase(); items = items.filter(e => (e.title || '').toLowerCase().includes(q)); }
      this.exclTotal = items.length;
      const start = this.exclPage * this.exclPageSize;
      this.exclusionItems = items.slice(start, start + this.exclPageSize);
    },

    prevExclPage() { if (this.exclPage > 0) this.refreshExclusions(this.exclPage - 1); },
    nextExclPage() { if (this.exclPage < this.exclPageCount - 1) this.refreshExclusions(this.exclPage + 1); },

    async unexcludeItem(title) {
      await this._api('/api/exclusions/remove', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title }) });
      await this.loadExclusions();
      this.exclusionItems = this.exclusionsData;
    },

    // ── Intel ─────────────────────────────────────────────────────────────

    async refreshIntel() {
      try { const data = await this._api('/api/intel'); this.intelData = data; }
      catch (e) { console.warn('[intel]', e.message); }
    },

    intelUpgradePaths() {
      // Bug #8: use path.from and path.to
      return (this.intelData?.upgrade_history?.upgrade_paths || []);
    },

    async resetIntelData() {
      await this._api('/api/intel/reset', { method: 'POST' });
      this.refreshIntel();
    },

    // ── Instances ─────────────────────────────────────────────────────────

    openInstModal(kind, idx) {
      const isEdit = idx >= 0;
      const inst = isEdit ? (this.cfg?.instances?.[kind]?.[idx] || {}) : {};
      this.instModal = {
        show: true, kind, idx, isEdit,
        name: inst.name || '',
        url: inst.url || '',
        key: '',
        keyVisible: false,
        testStatus: '', testMsg: '', testDone: false, testOk: false,
        urlWarn: false,
        title: (isEdit ? 'Edit ' : 'Add ') + (kind === 'radarr' ? 'Radarr' : 'Sonarr') + ' Instance',
        namePlaceholder: kind === 'radarr' ? 'Example: Radarr' : 'Example: Sonarr',
        urlPlaceholder: kind === 'radarr' ? 'http://192.168.1.10:7878' : 'http://192.168.1.10:8989',
        keyLabel: isEdit ? 'API Key (Leave blank to keep existing)' : 'API Key',
        keyPlaceholder: isEdit ? 'Leave blank to keep existing key' : 'Instance API Key',
      };
    },

    closeInstModal() { this.instModal.show = false; },

    checkInstUrlPath() {
      const url = this.instModal.url.trim();
      if (!url) { this.instModal.urlWarn = false; return; }
      try { const u = new URL(url); this.instModal.urlWarn = u.pathname && u.pathname !== '/'; }
      catch (e) { this.instModal.urlWarn = false; }
    },

    async testInstConnection() {
      const { name, url, key, kind } = this.instModal;
      if (!url.trim()) { this.instModal.testStatus = 'err'; this.instModal.testMsg = 'Enter a URL first.'; return; }
      this.instModal.testStatus = 'loading'; this.instModal.testMsg = 'Testing\u2026'; this.instModal.testDone = false;
      try {
        const payload = { kind, name: name || 'test', url: url.trim(), key: key.trim() };
        const r = await this._api('/api/test-single', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        this.instModal.testDone = true; this.instModal.testOk = !!r.ok;
        if (r.ok) { this.instModal.testStatus = 'ok'; this.instModal.testMsg = '\u2713 ' + (r.version ? 'Connected \u00b7 v' + r.version : 'Connected'); }
        else { this.instModal.testStatus = 'err'; this.instModal.testMsg = '\u2717 ' + (r.error || 'Connection failed'); }
      } catch (e) { this.instModal.testDone = true; this.instModal.testOk = false; this.instModal.testStatus = 'err'; this.instModal.testMsg = '\u2717 ' + e.message; }
    },

    async saveInstModal() {
      const { kind, idx, name, url, key } = this.instModal;
      if (!name.trim() || !url.trim()) { this.instModal.testStatus = 'err'; this.instModal.testMsg = 'Name and URL are required.'; return; }
      if (!key.trim() && idx < 0) { this.instModal.testStatus = 'err'; this.instModal.testMsg = 'API key is required.'; return; }
      // Test first
      await this.testInstConnection();
      if (!this.instModal.testOk) return;
      // Build entry
      if (!this.cfg.instances) this.cfg.instances = { radarr: [], sonarr: [] };
      const entry = { name: name.trim(), url: url.trim(), key: key.trim() };
      if (idx >= 0) {
        const existing = this.cfg.instances[kind][idx];
        if (!key.trim()) entry.key = existing.key;
        this.cfg.instances[kind][idx] = { ...existing, ...entry };
      } else {
        this.cfg.instances[kind].push(entry);
      }
      // Save immediately
      try {
        await this._api('/api/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(this.cfg) });
        await this.loadAll();
        await new Promise(r => setTimeout(r, 400));
        await this.testConnections();
        this.closeInstModal();
        this.instMsg = 'Saved'; this.instMsgClass = 'msg ok';
        this._fadeMsg('instMsg');
      } catch (e) {
        this.instModal.testStatus = 'err';
        this.instModal.testMsg = '\u2717 Save failed: ' + e.message;
      }
    },

    async toggleInstance(kind, idx) {
      try {
        const r = await this._api('/api/instance/toggle', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ kind, idx }) });
        if (this.cfg?.instances?.[kind]?.[idx]) this.cfg.instances[kind][idx].enabled = r.enabled;
      } catch (e) { this.showAlert('Toggle failed: ' + e.message, 'error'); }
    },

    async deleteInstance(kind, idx) {
      const name = this.cfg?.instances?.[kind]?.[idx]?.name || 'this instance';
      const ok = await this._showConfirm('Delete Instance', 'Remove ' + name + ' from Nudgarr? This cannot be undone.', 'Delete', true);
      if (!ok) return;
      this.cfg.instances[kind].splice(idx, 1);
      this.instMsg = 'Unsaved Changes'; this.instMsgClass = 'msg unsaved';
    },

    async saveInstances() {
      try {
        await this._api('/api/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(this.cfg) });
        await this.loadAll();
        await new Promise(r => setTimeout(r, 400));
        this.instMsg = 'Saved'; this.instMsgClass = 'msg ok';
        this._fadeMsg('instMsg');
      } catch (e) { this.instMsg = 'Save failed: ' + e.message; this.instMsgClass = 'msg err'; }
    },

    // ── Panel toggles (local state only; use Save on each panel to persist) ──

    toggleSchedulerEnabled(val) { this.schedulerEnabledUi = val; },
    toggleMaintEnabled(val) { this.maintenanceEnabled = val; },

    toggleQueueDepthEnabled(val) { this.queueDepthEnabled = val; },

    toggleCfEnabled(val) { this.cfEnabled = val; this.cfScoreEnabled = val; },

    toggleCfScoreAppEnabled(kind, val) {
      if (kind === 'radarr') this.radarrCfScoreAppEnabled = val;
      else this.sonarrCfScoreAppEnabled = val;
    },

    /** Per-app CF Score toggle in Pipelines (Radarr / Sonarr) — overrides are meaningless when this is off. */
    ovCfAppGlobalOn(kind) {
      return kind === 'radarr' ? this.radarrCfScoreAppEnabled : this.sonarrCfScoreAppEnabled;
    },

    ovCutoffAppGlobalOn(kind) {
      return kind === 'radarr' ? this.radarrCutoffEnabled : this.sonarrCutoffEnabled;
    },

    ovCutoffFieldsActive(kind, idx) {
      if (!this.ovCutoffAppGlobalOn(kind)) return false;
      const d = this.ovGet(kind, idx);
      const o = d.cutoff_enabled;
      if (o !== null && o !== undefined) return !!o;
      return true;
    },

    ovBacklogAppGlobalOn(kind) {
      return kind === 'radarr' ? this.radarrBacklogEnabled : this.sonarrBacklogEnabled;
    },

    ovBacklogFieldsActive(kind, idx) {
      if (!this.ovBacklogAppGlobalOn(kind)) return false;
      const d = this.ovGet(kind, idx);
      const o = d.backlog_enabled;
      if (o !== null && o !== undefined) return !!o;
      return true;
    },

    ovCfFieldsActive(kind, idx) {
      if (!this.cfScoreEnabled) return false;
      const appOn = this.ovCfAppGlobalOn(kind);
      if (!appOn) return false;
      const d = this.ovGet(kind, idx);
      const o = d.cf_score_enabled;
      if (o !== null && o !== undefined) return !!o;
      return true;
    },

    toggleCutoffEnabled(kind, val) {
      if (kind === 'radarr') this.radarrCutoffEnabled = val;
      else this.sonarrCutoffEnabled = val;
    },

    toggleBacklogEnabled(kind, val) {
      if (kind === 'radarr') this.radarrBacklogEnabled = val;
      else this.sonarrBacklogEnabled = val;
    },

    toggleAutoExcl(kind, val) {
      if (kind === 'radarr') this.radarrAutoExclEnabled = val;
      else this.sonarrAutoExclEnabled = val;
    },

    toggleShowSupportLink(val) { this.showSupportLink = val; },

    toggleNotifyEnabled(val) { this.notifyEnabled = val; },

    toggleNotifyOn(field, val) { this[field] = val; },

    _fadeSaveMsg(panel) {
      setTimeout(() => { this.saveMsg[panel] = ''; }, 3000);
    },

    async testConnections() {
      try {
        const out = await this._api('/api/test', { method: 'POST' });
        const health = {};
        for (const kind of ['radarr', 'sonarr']) {
          for (const r of (out.results?.[kind] || [])) {
            health[kind + '|' + r.name] = r.disabled ? 'disabled' : r.ok ? 'ok' : 'bad';
          }
        }
        this.instanceHealth = { ...this.instanceHealth, ...health };
      } catch (e) { this.showAlert('Test failed: ' + e.message, 'error'); }
    },

    // ── Pipelines ─────────────────────────────────────────────────────────

    // Copy every config-backed panel from Alpine state into cfg before POST.
    _syncFullCfgFromUi() {
      if (!this.cfg) return;
      this.cfg.radarr_cutoff_enabled = this.radarrCutoffEnabled;
      this.cfg.sonarr_cutoff_enabled = this.sonarrCutoffEnabled;
      this.cfg.radarr_max_movies_per_run = parseInt(this.radarrMaxCutoff) || 25;
      this.cfg.sonarr_max_episodes_per_run = parseInt(this.sonarrMaxCutoff) || 25;
      this.cfg.radarr_sample_mode = this.radarrSampleMode;
      this.cfg.sonarr_sample_mode = this.sonarrSampleMode;
      this.cfg.radarr_backlog_enabled = this.radarrBacklogEnabled;
      this.cfg.sonarr_backlog_enabled = this.sonarrBacklogEnabled;
      this.cfg.radarr_missing_max = parseInt(this.radarrMissingMax) || 1;
      this.cfg.sonarr_missing_max = parseInt(this.sonarrMissingMax) || 1;
      this.cfg.radarr_missing_added_days = parseInt(this.radarrMissingAddedDays) || 14;
      this.cfg.radarr_missing_grace_hours = parseInt(this.radarrMissingGraceHours) || 0;
      this.cfg.sonarr_missing_grace_hours = parseInt(this.sonarrMissingGraceHours) || 0;
      this.cfg.radarr_backlog_sample_mode = this.radarrBacklogSampleMode;
      this.cfg.sonarr_backlog_sample_mode = this.sonarrBacklogSampleMode;
      this.cfg.cf_score_enabled = this.cfEnabled;
      this.cfg.cf_score_sync_cron = this.cfSyncCron;
      this.cfg.radarr_cf_max_per_run = parseInt(this.radarrCfMax) || 25;
      this.cfg.sonarr_cf_max_per_run = parseInt(this.sonarrCfMax) || 25;
      this.cfg.radarr_cf_sample_mode = this.radarrCfSampleMode;
      this.cfg.sonarr_cf_sample_mode = this.sonarrCfSampleMode;
      this.cfg.radarr_cf_score_enabled = this.radarrCfScoreAppEnabled;
      this.cfg.sonarr_cf_score_enabled = this.sonarrCfScoreAppEnabled;

      this.cfg.scheduler_enabled = this.schedulerEnabledUi;
      this.cfg.cron_expression = (this.cronExpr || '').trim();
      this.cfg.cooldown_hours = parseInt(this.cooldownHours) || 48;
      this.cfg.maintenance_window_enabled = this.maintenanceEnabled;
      this.cfg.maintenance_window_start = this.maintenanceStart;
      this.cfg.maintenance_window_end = this.maintenanceEnd;
      this.cfg.maintenance_window_days = [...this.maintenanceDays];
      this.cfg.batch_size = parseInt(this.batchSize) || 1;
      this.cfg.sleep_seconds = parseFloat(this.sleepSeconds) || 5;
      this.cfg.jitter_seconds = parseFloat(this.jitterSeconds) || 2;
      this.cfg.queue_depth_enabled = this.queueDepthEnabled;
      this.cfg.queue_depth_threshold = Math.max(1, parseInt(this.queueDepthThreshold) || 10);
      this.cfg.per_instance_overrides_enabled = this.perInstanceOverridesEnabled;
      this.cfg.per_instance_overrides_seen = this.overridesInfoSeen;
      this.cfg.radarr_auto_exclude_enabled = this.radarrAutoExclEnabled;
      this.cfg.sonarr_auto_exclude_enabled = this.sonarrAutoExclEnabled;
      this.cfg.auto_exclude_movies_threshold = parseInt(this.autoExclMoviesThreshold) || 0;
      this.cfg.auto_exclude_shows_threshold = parseInt(this.autoExclShowsThreshold) || 0;
      this.cfg.auto_unexclude_movies_days = parseInt(this.autoUnexclMoviesDays) || 0;
      this.cfg.auto_unexclude_shows_days = parseInt(this.autoUnexclShowsDays) || 0;

      this.cfg.notify_enabled = this.notifyEnabled;
      this.cfg.notify_url = this.notifyUrl.trim();
      this.cfg.notify_on_sweep_complete = this.notifyOnSweep;
      this.cfg.notify_on_import = this.notifyOnImport;
      this.cfg.notify_on_auto_exclusion = this.notifyOnAutoExcl;
      this.cfg.notify_on_error = this.notifyOnError;
      this.cfg.notify_on_queue_depth_skip = this.notifyOnQueueDepth;

      this.cfg.state_retention_days = parseInt(this.retentionDays) || 180;
      this.cfg.auth_enabled = this.authEnabled;
      this.cfg.auth_session_minutes = parseInt(this.sessionTimeout) || 60;
      this.cfg.import_check_minutes = parseInt(this.importCheckMinutes) || 120;
      this.cfg.log_level = this.logLevel;
      this.cfg.default_tab = this.defaultTab;
      this.cfg.show_support_link = this.showSupportLink;
    },

    async savePipelines() {
      try {
        this._syncFullCfgFromUi();
        await this._api('/api/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(this.cfg) });
        await this.loadAll();
        await new Promise(r => setTimeout(r, 400));
        this.unsaved.pipelines = false;
        this.saveMsg.pipelines = 'Saved'; this.saveMsgOk.pipelines = true;
        this._fadeSaveMsg('pipelines');
      } catch (e) { this.saveMsg.pipelines = 'Save failed: ' + e.message; this.saveMsgOk.pipelines = false; }
    },

    validateCfCron() {
      const val = (this.cfSyncCron || '').trim();
      const parts = val.split(/\s+/);
      const valid = parts.length === 5 && parts.every(p => /^[\d\*\/,\-]+$/.test(p));
      this.cfCronValid = val ? valid : null;
      this.cfCronHint = valid ? this._describeCron(val) : (val ? 'Invalid cron expression' : '');
    },

    // ── Settings ──────────────────────────────────────────────────────────

    validateCron() {
      const val = (this.cronExpr || '').trim();
      const parts = val.split(/\s+/);
      const valid = parts.length === 5 && parts.every(p => /^[\d\*\/,\-]+$/.test(p));
      this.cronValid = val ? valid : null;
      if (valid) {
        const interval = this._cronIntervalMinutes(val);
        this.cronHint = (interval !== null && interval < 60) ? '\u26a0 May stress indexers' : this._describeCron(val);
      } else {
        this.cronHint = val ? 'Invalid cron expression' : '';
      }
    },

    validateMaintTime() {
      const re = /^(\d{2}):(\d{2})$/;
      const sm = this.maintenanceStart.match(re);
      const em = this.maintenanceEnd.match(re);
      if (!sm || !em) { this.maintHint = sm || em ? 'Enter times as HH:MM' : ''; return; }
      const sOk = parseInt(sm[1]) <= 23 && parseInt(sm[2]) <= 59;
      const eOk = parseInt(em[1]) <= 23 && parseInt(em[2]) <= 59;
      if (!sOk || !eOk) { this.maintHint = 'Enter times as HH:MM (e.g. 23:00)'; return; }
      const sMin = parseInt(sm[1]) * 60 + parseInt(sm[2]);
      const eMin = parseInt(em[1]) * 60 + parseInt(em[2]);
      if (sMin === eMin) { this.maintHint = 'Start and end time cannot be the same'; return; }
      if (!this.maintenanceDays.length) { this.maintHint = 'Select at least one day'; return; }
      const days = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
      const sel = this.maintenanceDays.map(d => days[d]);
      const dayStr = sel.length === 7 ? 'every day' : sel.join(', ');
      const overnight = sMin > eMin;
      this.maintHint = this.maintenanceStart + ' to ' + this.maintenanceEnd + (overnight ? ' (overnight)' : '') + ' on ' + dayStr;
    },

    toggleMaintDay(d) {
      if (this.maintenanceDays.includes(d)) this.maintenanceDays = this.maintenanceDays.filter(x => x !== d);
      else this.maintenanceDays = [...this.maintenanceDays, d];
      this.validateMaintTime();
      this.unsaved.settings = true;
    },

    isDayActive(d) { return this.maintenanceDays.includes(d); },

    async saveSettings() {
      try {
        this._syncFullCfgFromUi();
        await this._api('/api/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(this.cfg) });
        await this.loadAll();
        await new Promise(r => setTimeout(r, 400));
        this.unsaved.settings = false;
        this.saveMsg.settings = 'Saved'; this.saveMsgOk.settings = true;
        this._fadeSaveMsg('settings');
      } catch (e) { this.saveMsg.settings = 'Save failed: ' + e.message; this.saveMsgOk.settings = false; }
    },

    // ── Overrides ─────────────────────────────────────────────────────────

    disableOverrides() {
      this.overridesEnabled = false;
      this.perInstanceOverridesEnabled = false;
      this.unsaved.settings = true;
    },

    enableOverrides() {
      this.overridesEnabled = true;
      this.perInstanceOverridesEnabled = true;
      this.unsaved.settings = true;
      if (!this.cfg?.per_instance_overrides_seen) this.openModal('overridesInfo');
    },

    closeOverridesInfoModal() {
      this.closeModal();
      if (!this.cfg) return;
      this.cfg.per_instance_overrides_seen = true;
      this.overridesInfoSeen = true;
      this.unsaved.settings = true;
    },

    _buildOverrideData() {
      if (!this.cfg) return;
      const newData = {}, newDirty = {};
      for (const kind of ['radarr', 'sonarr']) {
        (this.cfg.instances?.[kind] || []).forEach((inst, idx) => {
          const k = kind + '-' + idx;
          const ov = inst.overrides || {};
          if (!this.ovData[k]) {
            newData[k] = {
              cooldown_hours: ov.cooldown_hours ?? null,
              cutoff_enabled: ov.cutoff_enabled ?? null,
              cutoff_max: kind === 'radarr' ? (ov.radarr_max_movies_per_run ?? null) : (ov.sonarr_max_episodes_per_run ?? null),
              cutoff_sample_mode: (kind === 'radarr' ? ov.radarr_sample_mode : ov.sonarr_sample_mode) ?? '__global__',
              backlog_enabled: (kind === 'radarr' ? ov.radarr_backlog_enabled : ov.sonarr_backlog_enabled) ?? null,
              backlog_max: (kind === 'radarr' ? ov.radarr_missing_max : ov.sonarr_missing_max) ?? null,
              backlog_sample_mode: (kind === 'radarr' ? ov.radarr_backlog_sample_mode : ov.sonarr_backlog_sample_mode) ?? '__global__',
              missing_added_days: kind === 'radarr' ? (ov.radarr_missing_added_days ?? null) : null,
              missing_grace_hours: ov.missing_grace_hours ?? null,
              cf_max: (kind === 'radarr' ? ov.radarr_cf_max_per_run : ov.sonarr_cf_max_per_run) ?? null,
              cf_score_enabled: (kind === 'radarr' ? ov.radarr_cf_score_enabled : ov.sonarr_cf_score_enabled) ?? null,
              cf_sample_mode: (kind === 'radarr' ? ov.radarr_cf_sample_mode : ov.sonarr_cf_sample_mode) ?? '__global__',
              notifications_enabled: ov.notifications_enabled ?? null,
            };
            newDirty[k] = false;
          } else {
            newData[k] = { ...this.ovData[k] };
            if (newData[k].cf_max === undefined) {
              newData[k].cf_max = (kind === 'radarr' ? ov.radarr_cf_max_per_run : ov.sonarr_cf_max_per_run) ?? null;
            }
            if (newData[k].cf_score_enabled === undefined) {
              newData[k].cf_score_enabled = (kind === 'radarr' ? ov.radarr_cf_score_enabled : ov.sonarr_cf_score_enabled) ?? null;
            }
            if (newData[k].cutoff_enabled === undefined) {
              newData[k].cutoff_enabled = ov.cutoff_enabled ?? null;
            }
            newDirty[k] = this.ovDirty[k];
          }
        });
      }
      this.ovData = newData; this.ovDirty = newDirty;
    },

    ovGet(kind, idx) { return this.ovData[kind + '-' + idx] || {}; },
    ovMarkDirty(kind, idx) { this.ovDirty[kind + '-' + idx] = true; this.unsaved.overrides = true; },

    ovOverrideCount(kind, idx) {
      const d = this.ovGet(kind, idx);
      return Object.values(d).filter(v => v !== null && v !== '__global__').length;
    },

    async applyOverrides(kind, idx) {
      const d = this.ovGet(kind, idx);
      const ov = {};
      if (d.cooldown_hours !== null) ov.cooldown_hours = parseInt(d.cooldown_hours) || 0;
      if (d.cutoff_enabled !== null) ov.cutoff_enabled = !!d.cutoff_enabled;
      if (d.cutoff_max !== null) { if (kind === 'radarr') ov.radarr_max_movies_per_run = parseInt(d.cutoff_max) || 1; else ov.sonarr_max_episodes_per_run = parseInt(d.cutoff_max) || 1; }
      if (d.cutoff_sample_mode !== '__global__') { if (kind === 'radarr') ov.radarr_sample_mode = d.cutoff_sample_mode; else ov.sonarr_sample_mode = d.cutoff_sample_mode; }
      if (d.backlog_enabled !== null) { if (kind === 'radarr') ov.radarr_backlog_enabled = !!d.backlog_enabled; else ov.sonarr_backlog_enabled = !!d.backlog_enabled; }
      if (d.backlog_max !== null) { if (kind === 'radarr') ov.radarr_missing_max = parseInt(d.backlog_max) || 1; else ov.sonarr_missing_max = parseInt(d.backlog_max) || 1; }
      if (d.backlog_sample_mode !== '__global__') { if (kind === 'radarr') ov.radarr_backlog_sample_mode = d.backlog_sample_mode; else ov.sonarr_backlog_sample_mode = d.backlog_sample_mode; }
      if (kind === 'radarr' && d.missing_added_days !== null) ov.radarr_missing_added_days = parseInt(d.missing_added_days) || 14;
      if (d.missing_grace_hours !== null) ov.missing_grace_hours = parseInt(d.missing_grace_hours) || 0;
      if (d.cf_max !== null) { if (kind === 'radarr') ov.radarr_cf_max_per_run = parseInt(d.cf_max) || 1; else ov.sonarr_cf_max_per_run = parseInt(d.cf_max) || 1; }
      if (d.cf_score_enabled !== null) {
        if (kind === 'radarr') ov.radarr_cf_score_enabled = !!d.cf_score_enabled;
        else ov.sonarr_cf_score_enabled = !!d.cf_score_enabled;
      }
      if (d.cf_sample_mode !== '__global__') { if (kind === 'radarr') ov.radarr_cf_sample_mode = d.cf_sample_mode; else ov.sonarr_cf_sample_mode = d.cf_sample_mode; }
      if (d.notifications_enabled !== null) ov.notifications_enabled = !!d.notifications_enabled;
      try {
        await this._api('/api/instance/overrides', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ kind, idx, overrides: ov }) });
        if (this.cfg.instances?.[kind]?.[idx]) this.cfg.instances[kind][idx].overrides = ov;
        this.ovDirty[kind + '-' + idx] = false;
        const anyDirty = Object.values(this.ovDirty).some(Boolean);
        if (!anyDirty) this.unsaved.overrides = false;
      } catch (e) { this.showAlert('Apply failed: ' + e.message, 'error'); }
    },

    async resetOverrideCard(kind, idx) {
      try {
        await this._api('/api/instance/overrides', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ kind, idx, overrides: {} }) });
        if (this.cfg.instances?.[kind]?.[idx]) this.cfg.instances[kind][idx].overrides = {};
        const k = kind + '-' + idx;
        const blank = {};
        for (const key of Object.keys(this.ovData[k] || {})) blank[key] = key.includes('sample_mode') ? '__global__' : null;
        this.ovData[k] = blank; this.ovDirty[k] = false;
        const anyDirty = Object.values(this.ovDirty).some(Boolean);
        if (!anyDirty) this.unsaved.overrides = false;
      } catch (e) { this.showAlert('Reset failed: ' + e.message, 'error'); }
    },

    // ── Filters ───────────────────────────────────────────────────────────

    async loadFilterData(kind) {
      const f = kind === 'radarr' ? this.radarrFilters : this.sonarrFilters;
      f.loading = true;
      try {
        const [tagsData, profilesData] = await Promise.all([
          this._api('/api/arr/tags?kind=' + kind + '&idx=' + f.instanceIdx),
          this._api('/api/arr/profiles?kind=' + kind + '&idx=' + f.instanceIdx),
        ]);
        f.tags = tagsData.tags || [];
        f.profiles = profilesData.profiles || [];
        const inst = (this.cfg?.instances?.[kind] || [])[f.instanceIdx];
        const sf = inst?.sweep_filters || {};
        const tagSrc = sf.excluded_tag_ids ?? sf.excluded_tags;
        const profSrc = sf.excluded_profile_ids ?? sf.excluded_profiles;
        f.excludedTagIds = tagSrc ? [...tagSrc] : [];
        f.excludedProfileIds = profSrc ? [...profSrc] : [];
        f.loaded = true;
      } catch (e) { this.showAlert('Failed to load filter data: ' + e.message, 'error'); }
      finally { f.loading = false; }
    },

    filterTagFiltered(kind) {
      const f = kind === 'radarr' ? this.radarrFilters : this.sonarrFilters;
      const q = (f.tagSearch || '').toLowerCase();
      return f.tags.filter(t => !q || (t.label || '').toLowerCase().includes(q));
    },

    filterProfileFiltered(kind) {
      const f = kind === 'radarr' ? this.radarrFilters : this.sonarrFilters;
      const q = (f.profileSearch || '').toLowerCase();
      return f.profiles.filter(p => !q || (p.name || '').toLowerCase().includes(q));
    },

    toggleFilterTag(kind, id) {
      const f = kind === 'radarr' ? this.radarrFilters : this.sonarrFilters;
      const i = f.excludedTagIds.indexOf(id);
      if (i >= 0) f.excludedTagIds.splice(i, 1); else f.excludedTagIds.push(id);
      if (kind === 'radarr') this.unsaved.filtersRadarr = true; else this.unsaved.filtersSonarr = true;
    },

    toggleFilterProfile(kind, id) {
      const f = kind === 'radarr' ? this.radarrFilters : this.sonarrFilters;
      const i = f.excludedProfileIds.indexOf(id);
      if (i >= 0) f.excludedProfileIds.splice(i, 1); else f.excludedProfileIds.push(id);
      if (kind === 'radarr') this.unsaved.filtersRadarr = true; else this.unsaved.filtersSonarr = true;
    },

    async saveFilters(kind) {
      const f = kind === 'radarr' ? this.radarrFilters : this.sonarrFilters;
      const instances = this.cfg?.instances?.[kind];
      if (!instances || !instances[f.instanceIdx]) return;
      const payload = {
        kind, idx: f.instanceIdx,
        sweep_filters: { excluded_tags: [...f.excludedTagIds], excluded_profiles: [...f.excludedProfileIds] },
      };
      try {
        await this._api('/api/arr/filters', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        if (this.cfg.instances?.[kind]?.[f.instanceIdx]) {
          this.cfg.instances[kind][f.instanceIdx].sweep_filters = {
            excluded_tags: [...f.excludedTagIds],
            excluded_profiles: [...f.excludedProfileIds],
          };
        }
        if (kind === 'radarr') this.unsaved.filtersRadarr = false; else this.unsaved.filtersSonarr = false;
        const appCfOn = kind === 'radarr' ? this.radarrCfScoreAppEnabled : this.sonarrCfScoreAppEnabled;
        if (this.cfScoreEnabled && appCfOn) this.openModal('cfFiltersSync');
      } catch (e) { this.showAlert('Save failed: ' + e.message, 'error'); }
    },

    async cfFiltersSyncNow() {
      this.closeModal();
      await this.scanCfLibrary();
    },

    // ── Notifications ─────────────────────────────────────────────────────

    async testNotification() {
      const url = this.notifyUrl.trim();
      if (!url) { this.notifTestMsg = 'Enter a URL first.'; this.notifTestMsgClass = 'msg err'; return; }
      this.notifTestMsg = 'Sending\u2026'; this.notifTestMsgClass = 'msg';
      // Bug #5: must send {url} in body
      try {
        const r = await this._api('/api/notifications/test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url }) });
        if (r && r.ok) { this.notifTestMsg = '\u2713 Notification sent'; this.notifTestMsgClass = 'msg ok'; }
        else { this.notifTestMsg = '\u2717 ' + (r?.error || 'Failed'); this.notifTestMsgClass = 'msg err'; }
      } catch (e) { this.notifTestMsg = '\u2717 ' + e.message; this.notifTestMsgClass = 'msg err'; }
      setTimeout(() => { this.notifTestMsg = ''; this.notifTestMsgClass = ''; }, 5000);
    },

    // Bug #7: saveNotifications must POST config
    async saveNotifications() {
      try {
        this._syncFullCfgFromUi();
        await this._api('/api/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(this.cfg) });
        await this.loadAll();
        await new Promise(r => setTimeout(r, 400));
        this.unsaved.notifications = false;
        this.saveMsg.notifications = 'Saved'; this.saveMsgOk.notifications = true;
        this._fadeSaveMsg('notifications');
      } catch (e) { this.saveMsg.notifications = 'Save failed: ' + e.message; this.saveMsgOk.notifications = false; }
    },

    // ── Advanced ──────────────────────────────────────────────────────────

    async saveAdvanced() {
      try {
        this._syncFullCfgFromUi();
        await this._api('/api/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(this.cfg) });
        await this.loadAll();
        await new Promise(r => setTimeout(r, 400));
        this.unsaved.advanced = false;
        this.saveMsg.advanced = 'Saved'; this.saveMsgOk.advanced = true;
        this._fadeSaveMsg('advanced');
      } catch (e) { this.saveMsg.advanced = 'Save failed: ' + e.message; this.saveMsgOk.advanced = false; }
    },

    async logout() {
      try { await fetch('/api/auth/logout', { method: 'POST' }); } catch (e) { /* silent */ }
      window.location.href = '/login';
    },

    backupAll() { window.location.href = '/api/file/backup'; },
    downloadDiagnostic() { window.location.href = '/api/diagnostic'; },

    // Danger zone — stores confirmAction, shows confirm modal
    danger(action) { this.confirmAction = action; this.openModal('confirm'); },

    async executeDanger() {
      const action = this.confirmAction;
      this.closeModal();
      try {
        if (action === 'clearHistory') await this._api('/api/state/clear', { method: 'POST' });
        else if (action === 'clearImports') await this._api('/api/stats/clear', { method: 'POST' });
        else if (action === 'clearLog') await this._api('/api/log/clear', { method: 'POST' });
        else if (action === 'resetIntel') { await this._api('/api/intel/reset', { method: 'POST' }); this.refreshIntel(); }
      } catch (e) { this.showAlert(action + ' failed: ' + e.message, 'error'); }
    },

    async executeResetConfig() {
      this.closeModal();
      try { await this._api('/api/config/reset', { method: 'POST' }); window.location.reload(); }
      catch (e) { this.showAlert('Reset failed: ' + e.message, 'error'); }
    },

    // ── Arr link ─────────────────────────────────────────────────────────

    // Bug #11: openArrLink must exist in the Alpine object
    async openArrLink(app, instanceName, itemId, seriesId) {
      if (!app || !instanceName || !itemId) {
        this.showAlert('No Radarr/Sonarr link is stored for this row yet.', 'info');
        return;
      }
      try {
        let url = '/api/arr-link?app=' + encodeURIComponent(app) + '&instance=' + encodeURIComponent(instanceName) + '&item_id=' + encodeURIComponent(itemId);
        if (seriesId) url += '&series_id=' + encodeURIComponent(seriesId);
        const data = await this._api(url);
        if (data.ok && data.url) window.open(data.url, '_blank');
        else { this.showAlert('Could not open in ' + (app === 'radarr' ? 'Radarr' : 'Sonarr') + ': ' + (data.error || 'Unknown error'), 'error'); }
      } catch (e) { this.showAlert('Link failed: ' + e.message, 'error'); }
    },

    // ── Modal helpers ─────────────────────────────────────────────────────

    openModal(name) { this.modal = name; },

    closeModal() {
      const wasConfirm = this.modal === 'confirm';
      this.modal = null;
      this.clearExclOpt = null;
      if (!wasConfirm) this.confirmAction = null;
      if (wasConfirm && this._confirmResolve) { this._confirmResolve(false); this._confirmResolve = null; }
    },

    showAlert(msg, type) {
      this.alertMsg = msg;
      this.alertType = type || 'error';
      this.openModal('alert');
    },

    // Promise-based confirm for deleteInstance etc.
    _showConfirm(title, msg, okLabel, isDanger) {
      this.confirmAction = null;  // not a danger zone action
      this._genericConfirmTitle = title;
      this._genericConfirmMsg = msg;
      this._genericConfirmOkLabel = okLabel || 'Confirm';
      this._genericConfirmIsDanger = !!isDanger;
      this.openModal('genericConfirm');
      return new Promise(resolve => { this._confirmResolve = resolve; });
    },

    _genericConfirmTitle: '',
    _genericConfirmMsg: '',
    _genericConfirmOkLabel: 'Confirm',
    _genericConfirmIsDanger: false,

    genericConfirmOk() {
      this.modal = null;
      if (this._confirmResolve) { this._confirmResolve(true); this._confirmResolve = null; }
    },

    // ── Onboarding ────────────────────────────────────────────────────────

    async maybeShowOnboarding() {
      if (!this.cfg || this.cfg.onboarding_complete) return;
      this.onboardingStep = 0;
      this.openModal('onboarding');
    },

    onboardingNext() {
      if (!this.onboardingIsLast) { this.onboardingStep++; }
      else { this.closeModal(); this._completeOnboarding(); this.onboardingStep = 0; }
    },

    onboardingPrev() { if (!this.onboardingIsFirst) this.onboardingStep--; },
    onboardingGoto(i) { this.onboardingStep = i; },

    async _completeOnboarding() {
      try { await this._api('/api/onboarding/complete', { method: 'POST' }); if (this.cfg) this.cfg.onboarding_complete = true; }
      catch (e) { /* silent */ }
    },

    async maybeShowWhatsNew() {
      if (!this.cfg) return;
      const lastSeen = this.cfg.last_seen_version || '';
      const current = this.version || '';
      const toMinor = v => v.split('.').slice(0, 2).join('.');
      if (current && toMinor(lastSeen) !== toMinor(current)) {
        this.openModal('whatsNew');
      }
    },

    async dismissWhatsNew() {
      this.closeModal();
      try { await this._api('/api/whats-new/dismiss', { method: 'POST' }); if (this.cfg) this.cfg.last_seen_version = this.version; }
      catch (e) { /* silent */ }
    },

    // ── Helpers ───────────────────────────────────────────────────────────

    formatRelative(ts, future) {
      const diff = future ? ts - Date.now() : Date.now() - ts;
      const mins = Math.floor(diff / 60000);
      const hrs  = Math.floor(diff / 3600000);
      const days = Math.floor(diff / 86400000);
      if (!future && mins < 1) return 'Just now';
      if (future  && mins < 1) return 'Now';
      if (mins < 60)  return mins + 'm' + (future ? '' : ' ago');
      if (hrs  < 24)  return hrs + 'h' + (future ? '' : ' ago');
      if (days < 7)   return days + 'd' + (future ? '' : ' ago');
      const d = new Date(ts);
      const sameYear = d.getFullYear() === new Date().getFullYear();
      return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', ...(sameYear ? {} : { year: 'numeric' }) });
    },

    _fmtTime(s) {
      if (!s) return '\u2014';
      try { return new Date(s).toLocaleString(); } catch (e) { return s; }
    },

    _fmtTimePadded(s) {
      if (!s) return '';
      try {
        const d = new Date(s);
        const mo = String(d.getMonth() + 1).padStart(2, '0');
        const dy = String(d.getDate()).padStart(2, '0');
        let h = d.getHours(), ampm = h >= 12 ? 'PM' : 'AM';
        h = h % 12 || 12;
        const mi = String(d.getMinutes()).padStart(2, '0');
        return mo + '/' + dy + ', ' + h + ':' + mi + ' ' + ampm;
      } catch (e) { return s; }
    },

    _sortItems(items, col, dir) {
      return [...items].sort((a, b) => {
        let av = a[col], bv = b[col];
        if (av == null) av = ''; if (bv == null) bv = '';
        if (typeof av === 'number' && typeof bv === 'number') return dir === 'asc' ? av - bv : bv - av;
        return dir === 'asc' ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
      });
    },

    formatCompact(n) {
      const v = Number(n) || 0;
      if (v < 10000) return v.toLocaleString();
      if (v < 1000000) return (v / 1000).toFixed(v < 100000 ? 1 : 0) + 'k';
      return (v / 1000000).toFixed(1) + 'M';
    },

    formatQualityHistoryLine(step) {
      if (!step) return '\u2014';
      const to = step.quality_to != null && String(step.quality_to).trim() !== '' ? String(step.quality_to).trim() : '';
      const from = step.quality_from != null && String(step.quality_from).trim() !== '' ? String(step.quality_from).trim() : '';
      const dash = '\u2014';
      if (!to && !from) return dash;
      if (!from) return 'Acquired \u2192 ' + (to || dash);
      return from + ' \u2192 ' + (to || dash);
    },

    _cronIntervalMinutes(expr) {
      const parts = expr.trim().split(/\s+/);
      if (parts.length !== 5) return null;
      const [min, hr] = parts;
      if (/^\*\/\d+$/.test(min)) return parseInt(min.split('/')[1]);
      if (min === '*') return 1;
      if (/^\*\/\d+$/.test(hr) && /^\d+$/.test(min)) return parseInt(hr.split('/')[1]) * 60;
      return 60;
    },

    _describeCron(expr) {
      const parts = expr.trim().split(/\s+/);
      if (parts.length !== 5) return 'Custom Schedule';
      const [min, hr, dom, mon, dow] = parts;
      const exactMin = /^\d+$/.test(min), exactHr = /^\d+$/.test(hr);
      const mm = exactMin ? String(parseInt(min)).padStart(2,'0') : '00';
      if (dom === '*' && mon === '*' && dow === '*' && exactHr && exactMin) {
        const h = parseInt(hr), m = parseInt(min), suffix = h >= 12 ? 'PM' : 'AM', h12 = h % 12 || 12;
        return 'Daily at ' + h12 + ':' + String(m).padStart(2,'0') + ' ' + suffix;
      }
      if (/^\*\/\d+$/.test(hr) && dom === '*' && mon === '*' && dow === '*') {
        const n = parseInt(hr.split('/')[1]);
        return 'Every ' + n + ' hour' + (n !== 1 ? 's' : '') + (exactMin ? ' at xx:' + mm : ' on the hour');
      }
      if (/^\*\/\d+$/.test(min) && hr === '*' && dom === '*' && mon === '*' && dow === '*') {
        const n = parseInt(min.split('/')[1]);
        return 'Every ' + n + ' minute' + (n !== 1 ? 's' : '');
      }
      return 'Custom Schedule';
    },

    _fadeMsg(prop) {
      setTimeout(() => { this[prop] = ''; this[prop + 'Class'] = ''; }, 3000);
    },

    sweepPipePill(sweepType) {
      const t = (sweepType || '').toLowerCase();
      if (t === 'cf score') return 'cfscore';
      if (t === 'backlog') return 'backlog';
      return 'cutoff';
    },

    fmtSweepTime(ts) {
      if (!ts) return '\u2014';
      try { return new Date(ts).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }); } catch (e) { return ts; }
    },
  };
}

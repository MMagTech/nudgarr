# Nudgarr
### Because RSS sometimes needs a nudge.

Nudgarr keeps your Radarr and Sonarr libraries improving automatically. Three independent pipelines handle Cutoff Unmet searches, missing content Backlog nudges, and CF Score upgrades for files that score below your quality profile cutoff. Set your limits, configure your schedule, and let it run.

---

## Quick Start

Images are available on **Docker Hub** and **GitHub Container Registry (GHCR)**.

| Registry | Image |
|----------|-------|
| Docker Hub | `mmagtech/nudgarr:latest` |
| GHCR | `ghcr.io/mmagtech/nudgarr:latest` |

**Tags:** `latest` · `v4.2.0` · `4.2.0` · `4.2` · `v4.1.0` · `4.1.0` · `4.1` · `v4.0.0` · `4.0.0` · `4.0`

1. Copy `.env.example` to `.env` and fill in your values
2. Run `docker compose up -d`
3. Open `http://<your-host>:8085`

```env
PUID=1000
PGID=1000
PORT=8085
CONFIG_PATH=/your/path/to/appdata/nudgarr
TZ=UTC
# SECRET_KEY=your-secret-key  # optional, auto-generated if not set
```

A ready-to-use `docker-compose.yml` is included in the repo root. Copy it alongside a `.env` file — see `.env.example` for all available options.

---

## UI

Nudgarr includes a full web UI accessible from any browser on your network. No separate app required — just navigate to `http://your-host:8085` after setup.

<img src="docs/ui-demo.gif" width="900" alt="Nudgarr UI"/>

The interface covers everything in one place: instance management, sweep status and history, confirmed imports with quality upgrade tracking, exclusions, notifications, and per-instance configuration. The UI is fully responsive and works on any screen size — every feature, including CF Score, Intel, and Overrides, is accessible on mobile.

---

## Features

**Core**
- Cron-based scheduler with configurable expression and timezone support, or manual-only mode
- Skip Queued — items already in the download queue are silently bypassed; max per run always filled from actionable items
- Per-instance enable/disable — disabled instances skipped in sweeps and health checks
- Per-app sample modes — Random, Alphabetical, Oldest Added, Newest Added independently for Radarr and Sonarr
- Configurable cooldown, batch size, sleep, and jitter controls for indexer rate limit compliance
- Per-app Backlog Nudge toggles with Missing Added Days age filter and per-instance caps
- Radarr minimumAvailability filter — movies that haven't reached their availability threshold are automatically skipped

**UI**
- Web UI with Instances, Sweep, Settings, Filters, History, Imports, Intel, Notifications, Advanced, and Overrides tabs
- Sticky header — wordmark, status bar, and tab bar pin to the top of the viewport on all tabs; tab content scrolls beneath
- Sweep tab — three pipeline cards (Cutoff Unmet, Backlog, CF Score) with aggregate totals and per-instance breakdowns; Sweep Health, Last Sweep, and Imports Confirmed summary cards; full-width paginated feed of every item searched in the current sweep with pipeline badges
- Intel tab — lifetime performance dashboard showing Library Score, Search Health, Instance Performance, Stuck Items, Exclusion Intel, Library Age vs Success, Quality Iteration, and Sweep Efficiency
- Search history with sweep type, instance, library added date, search count, sortable columns, and title search
- Clickable titles in History and Imports — opens the item directly in the configured Radarr or Sonarr instance
- Auto-exclusion badge and confirmed import tracking with lifetime totals, period toggle, type filtering, title search, and quality upgrade history per item
- Apprise notifications — sweep complete, import confirmed, auto-exclusion, and error triggers per instance
- Configurable log level (DEBUG / INFO / WARNING / ERROR) set live from the Advanced tab with no container restart
- Diagnostic download includes the last 250 lines of `nudgarr.log` with URLs masked
- First-run onboarding walkthrough and What's New modal on upgrade

**Mobile**
- Fully responsive desktop UI — all features available on any screen size, no separate layout or URL
- Tab bar scrolls horizontally on narrow screens; pipeline cards, grids, and tables reflow at phone width
- Tables (History, Imports, CF Score) scroll horizontally with the title column pinned
- iOS and Android browser toolbar matches the app via `theme-color`

**Power User**
- **CF Score Scan** — finds monitored items where the custom format score is below the quality profile cutoff even when Radarr and Sonarr don't flag them via their normal wanted system. Enable in Advanced to unlock the CF Score tab.
- **Auto-Exclusion** — titles searched N times with no confirmed import are automatically excluded. Configure separate thresholds for Radarr and Sonarr in Advanced. Auto-unexclude after X days returns titles to eligibility.
- **Tag & Quality Profile Filters** — exclude items from sweep by tag or quality profile, configured per instance. Items matching an excluded tag or profile are skipped before cooldown runs and never consume a search slot.
- **Per-Instance Overrides** — tune cooldown, max cutoff unmet, max backlog, max missing days, sample mode, backlog enabled, and notifications independently per instance. Unset fields inherit the global value. Enable in Advanced and configure in the Overrides tab. [Full details on the wiki.](https://github.com/MMagTech/nudgarr/wiki/Per-Instance-Overrides)
- **Maintenance Window** — suppress scheduled sweeps during a defined time window. Manual Run Now always bypasses it. Configure in Settings.
- **Backlog Grace Period** — delay the first search on a missing item until a configured number of hours after its availability date, giving indexers time to populate.
- **Exclusions** — click the ⊘ icon on any History row to permanently exclude a title from future searches. Exclusions are global across all instances. Manage the full list in the History tab.

---

## Documentation

Full documentation is available on the [Nudgarr Wiki](https://github.com/MMagTech/nudgarr/wiki), including:

- [Setup & Configuration](https://github.com/MMagTech/nudgarr/wiki/Setup-&-Configuration)
- [How Nudgarr Works](https://github.com/MMagTech/nudgarr/wiki/How-Nudgarr-Works)
- [Settings Reference](https://github.com/MMagTech/nudgarr/wiki/Settings-Reference)
- [Per-Instance Overrides](https://github.com/MMagTech/nudgarr/wiki/Per-Instance-Overrides)
- [Tag & Quality Profile Filters](https://github.com/MMagTech/nudgarr/wiki/Filters)
- [Radarr & Sonarr Backlog](https://github.com/MMagTech/nudgarr/wiki/Radarr-and-Sonarr-Backlog)
- [Exclusions](https://github.com/MMagTech/nudgarr/wiki/Exclusions)
- [Notifications (Apprise)](https://github.com/MMagTech/nudgarr/wiki/Notifications-(Apprise))
- [FAQ & Troubleshooting](https://github.com/MMagTech/nudgarr/wiki/FAQ-&-Troubleshooting)
- [Glossary](https://github.com/MMagTech/nudgarr/wiki/Glossary)

---

## PUID / PGID

Nudgarr runs as the user you specify — no permission issues with your `/config` volume.

| Platform | Typical values |
|----------|---------------|
| Unraid | `PUID=99` `PGID=100` (nobody:users) |
| Linux | `PUID=1000` `PGID=1000` |
| Synology | Match your DSM user — check with `id` over SSH |

Defaults to `1000:1000` if not set.

---

## Data files

| File | Purpose |
|------|---------|
| `/config/nudgarr-config.json` | All settings |
| `/config/nudgarr.db` | SQLite database — history, stats, exclusions, and app state |
| `/config/logs/nudgarr.log` | Rotating log file — 5 MB per file, 3 backups. Log level set in Advanced tab. |

---

## Security

Nudgarr is a local network tool. The login screen provides basic access control — it is not a hardened security layer. Passwords use PBKDF2-HMAC-SHA256 with a unique random salt, and failed attempts trigger a progressive lockout.

Run on your LAN only. For remote access use a VPN (Tailscale, WireGuard) or a reverse proxy with HTTPS. Do not expose port 8085 to the internet.

---

## Upgrade notes

**v4.2.0** adds CF Score Scan, Intel tab, Sweep tab redesign, responsive desktop UI (mobile UI removed), sticky header, exclusion event tracking, backlog sample mode split, maintenance window, grace period, and Settings tab cleanup. No config changes required. Pull the new image and restart. Migrations v10 and v11 run automatically on first start. Existing data is fully preserved.

**v4.1.0** adds auto-exclusion, import stats period toggle, and logging improvements. No config changes required. Pull the new image and restart. Migration v9 runs automatically on first start. From this version onwards, static assets include version query strings — browsers automatically receive fresh JS and CSS after a container upgrade without requiring a hard refresh.

**v4.0.0** is the foundations release. No config changes required, no data migration needed. Pull the new image and restart. If upgrading directly from v3.1.x or earlier, upgrade to v3.2.0 first.

**v3.2.0** — No config changes required. Per-Instance Overrides is off by default — enable in Advanced if you want to use it.

**v3.1.0** — All data (history, stats, exclusions) moves to a SQLite database. Existing JSON files migrate automatically on first start — no action needed.

**v3.0.0** — No config changes required.

For full version history see [CHANGELOG.md](CHANGELOG.md).

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for project structure and development guide. For usage questions, the [wiki](https://github.com/MMagTech/nudgarr/wiki) is the first stop.

## Community

Join the community on Reddit at [r/nudgarr](https://www.reddit.com/r/nudgarr) — share configs, ask questions, and follow development updates.

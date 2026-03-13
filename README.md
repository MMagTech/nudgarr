# Nudgarr
### Because RSS sometimes needs a nudge.

Nudgarr keeps your Radarr and Sonarr libraries improving automatically — scheduling searches for missing content and quality upgrades so you don't have to.

---

## Screenshots

Click any screenshot to view full size.

<table>
  <tr>
    <td align="center"><a href="docs/screenshots/instances.png"><img src="docs/screenshots/instances.png" width="400" alt="Instances"/></a><br/><sub>Instances</sub></td>
    <td align="center"><a href="docs/screenshots/sweep.png"><img src="docs/screenshots/sweep.png" width="400" alt="Sweep"/></a><br/><sub>Sweep</sub></td>
  </tr>
  <tr>
    <td align="center"><a href="docs/screenshots/history.png"><img src="docs/screenshots/history.png" width="400" alt="History"/></a><br/><sub>History</sub></td>
    <td align="center"><a href="docs/screenshots/imports.png"><img src="docs/screenshots/imports.png" width="400" alt="Imports"/></a><br/><sub>Imports</sub></td>
  </tr>
  <tr>
    <td align="center"><a href="docs/screenshots/settings.png"><img src="docs/screenshots/settings.png" width="400" alt="Settings"/></a><br/><sub>Settings</sub></td>
    <td align="center"><a href="docs/screenshots/notifications.png"><img src="docs/screenshots/notifications.png" width="400" alt="Notifications"/></a><br/><sub>Notifications</sub></td>
  </tr>
  <tr>
    <td align="center"><a href="docs/screenshots/advanced.png"><img src="docs/screenshots/advanced.png" width="400" alt="Advanced"/></a><br/><sub>Advanced</sub></td>
    <td align="center"><a href="docs/screenshots/onboard.png"><img src="docs/screenshots/onboard.png" width="400" alt="Onboarding"/></a><br/><sub>Onboarding</sub></td>
  </tr>
</table>

---

## Documentation

Full documentation is available on the [Nudgarr Wiki](https://github.com/MMagTech/nudgarr/wiki), including:

- [Setup & Configuration](https://github.com/MMagTech/nudgarr/wiki/Setup-&-Configuration)
- [How Nudgarr Works](https://github.com/MMagTech/nudgarr/wiki/How-Nudgarr-Works)
- [Settings Reference](https://github.com/MMagTech/nudgarr/wiki/Settings-Reference)
- [Exclusions](https://github.com/MMagTech/nudgarr/wiki/Exclusions)
- [Notifications (Apprise)](https://github.com/MMagTech/nudgarr/wiki/Notifications-(Apprise))
- [FAQ & Troubleshooting](https://github.com/MMagTech/nudgarr/wiki/FAQ-&-Troubleshooting)

---

## What it does

- **Cutoff Unmet sweeps** — finds items in Radarr and Sonarr's Wanted → Cutoff Unmet queue and triggers a search for a better quality version
- **Backlog Nudges** — searches missing movies and episodes that have never been grabbed, with age filtering and per-app caps
- **Skip Queued** — items already downloading are silently skipped; queued items never consume a search slot
- **Import tracking** — polls Radarr and Sonarr after each sweep to confirm which searches resulted in a successful download
- **Multiple instances** — supports multiple Radarr and Sonarr instances independently, each with their own health status

---

## Features

**Core**
- Cron-based scheduler with configurable expression and timezone support, or manual-only mode
- Skip Queued — items already in the download queue are silently bypassed; max per run always filled from actionable items
- Per-instance enable/disable — disabled instances skipped in sweeps and health checks
- Per-app sample modes — Random, Alphabetical, Oldest Added, Newest Added independently for Radarr and Sonarr
- Configurable cooldown, batch size, sleep, and jitter controls for indexer rate limit compliance
- Per-app Backlog Nudge toggles with Missing Added Days age filter and per-instance caps

**UI**
- Web UI with Instances, Sweep, Settings, History, Imports, Notifications, and Advanced tabs
- Search history with sweep type, instance, library added date, search count, sortable columns, and title search
- Exclusion list — exclude specific titles from future searches via the ⊘ icon in History
- Confirmed import tracking with lifetime Movies/Episodes totals, type filtering, and title search
- Apprise notifications — sweep complete, import confirmed, and error triggers per instance
- First-run onboarding walkthrough and What's New modal on upgrade

**Mobile**
- Purpose-built layout for devices under 500px wide — activates automatically, no separate app or URL
- Four-tab bottom nav: Home · Instances · Sweep · Exclusions
- Quick Settings — long press Run Now to adjust cooldown and max per run without leaving the home tab
- Landscape mode — rotating to landscape switches to a compact settings panel; tap Desktop View to access the full UI
- Bottom sheets for Exclusions and Imports with haptic feedback and swipe-to-dismiss
- iOS and Android browser toolbar matches the app via `theme-color`

---

## Quick start

Images are available on **Docker Hub** and **GitHub Container Registry (GHCR)**.

| Registry | Image |
|----------|-------|
| Docker Hub | `mmagtech/nudgarr:latest` |
| GHCR | `ghcr.io/mmagtech/nudgarr:latest` |

**Tags:** `latest` · `v3.1.0` · `3.1.0` · `3.1`

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

```yaml
version: "3.8"
services:
  nudgarr:
    image: mmagtech/nudgarr:latest
    container_name: nudgarr
    restart: unless-stopped
    ports:
      - "${PORT:-8085}:${PORT:-8085}"
    volumes:
      - ${CONFIG_PATH:-./config}:/config
    environment:
      - PUID=${PUID:-1000}
      - PGID=${PGID:-1000}
      - PORT=${PORT:-8085}
      - CONFIG_FILE=/config/nudgarr-config.json
      - DB_FILE=/config/nudgarr.db
      - TZ=${TZ:-UTC}
      # - SECRET_KEY=${SECRET_KEY}  # optional, auto-generated if not set
    read_only: true
    tmpfs:
      - /tmp:rw,noexec,nosuid,nodev,size=64m
    tty: false
    stdin_open: false
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    cap_add:
      - CHOWN
      - SETUID
      - SETGID
    pids_limit: 50
    mem_limit: 128m
    cpus: 0.5
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
```

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

If upgrading from v3.0.0 or earlier, existing JSON files are migrated automatically on first start. The original files are left in place and can be removed once you're satisfied with the upgrade.

---

## Security

Nudgarr is a local network tool. The login screen provides basic access control — it is not a hardened security layer. Passwords use PBKDF2-HMAC-SHA256 with a unique random salt, and failed attempts trigger a progressive lockout.

Run on your LAN only. For remote access use a VPN (Tailscale, WireGuard) or a reverse proxy with HTTPS. Do not expose port 8085 to the internet.

---

## Upgrade notes

**v3.1.0** — All data (history, stats, exclusions) moves to a SQLite database. Existing JSON files migrate automatically on first start — no action needed. See the Data files section above for details.

**v3.0.0** — No config changes required. The mobile layout activates automatically on devices under 500px wide.

For full version history see [CHANGELOG.md](CHANGELOG.md).

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for project structure and development guide. For usage questions, the [wiki](https://github.com/MMagTech/nudgarr/wiki) is the first stop.


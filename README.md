# Nudgarr
### Because RSS sometimes needs a nudge.

> **A note from the creator:** I'm not a developer — I'm a tech enthusiast and a fan of the *arr stack who wanted to build something useful. Nudgarr is vibe coded, built through curiosity, community tools, and a lot of learning along the way. If you're a developer and want to contribute, improve the code, or help with branding and design, I'd genuinely welcome it. This is as much a learning experience as it is a project.

Nudgarr is a lightweight upgrade sweeper and backlog nudger for Radarr and Sonarr. It runs on a schedule, finds items in your Wanted lists, and instructs your instances to search — so you don't have to.

---

## What it does

- **Cutoff Unmet sweeps** — searches items in Radarr and Sonarr's Wanted → Cutoff Unmet queue for better quality versions
- **Backlog Nudges** — searches missing movies and episodes that haven't been grabbed yet
- **Import tracking** — confirms which searches resulted in a successful download and shows them in the Stats tab
- **Multiple instances** — supports multiple Radarr and Sonarr instances independently

---

## Features

- Web UI with Instances, Settings, History, Stats, and Advanced tabs
- Scheduler with configurable run interval
- Configurable cooldown period to avoid hammering indexers
- Batch size and sleep controls for indexer rate limit compliance
- Per-app Backlog Nudge toggles with age and cap controls
- Search history with sweep type labels, sortable columns, pagination, and auto-refresh
- Confirmed import tracking with Movies/Shows totals, type filtering, and pagination
- Instance health dots — updated on every sweep and on add/edit
- Unsaved Changes notices across all tabs
- UI login with configurable session timeout
- Download Diagnostic for troubleshooting
- Multi-arch Docker images — `linux/amd64` and `linux/arm64`

---

## Docker Compose

Images are available on both **Docker Hub** and **GitHub Container Registry (GHCR)**. Either works — use whichever your platform prefers.

| Registry | Image |
|----------|-------|
| Docker Hub | `mmagtech/nudgarr:latest` |
| GHCR | `ghcr.io/mmagtech/nudgarr:latest` |

**Available tags:**
- `latest` — current stable release from main
- `dev` — development branch, may be unstable
- `v2.3.0`, `2.3.0`, `2.3` — pinned version tags

**Setup**

1. Copy `.env.example` to `.env` and fill in your values
2. Run `docker compose up -d`

```env
# .env
PUID=1000
PGID=1000
PORT=8085
CONFIG_PATH=/your/path/to/appdata/nudgarr
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
      - STATE_FILE=/config/nudgarr-state.json
      - STATS_FILE=/config/nudgarr-stats.json
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
      - CHOWN      # required to set /config ownership on startup
      - SETUID     # required for su-exec to drop privileges
      - SETGID     # required for su-exec to drop privileges
    pids_limit: 50
    mem_limit: 128m
    cpus: 0.5
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
```

Open the UI at `http://<your-host>:8085`

---

## User and Group ID (PUID / PGID)

Nudgarr supports `PUID` and `PGID` environment variables so the container runs as the correct user on your system — no permission issues with your `/config` volume.

| Platform | Typical values |
|----------|---------------|
| Unraid | `PUID=99` `PGID=100` (nobody:users) |
| Linux | `PUID=1000` `PGID=1000` |
| Synology | Match your DSM user — check with `id` in SSH |

If `PUID` and `PGID` are not set, the container defaults to `1000:1000`.

---

## Supported platforms

Any host running Docker — Unraid, Synology, TrueNAS SCALE, CasaOS, Portainer, or a plain Linux server.

Supports `linux/amd64` and `linux/arm64`.

---

## Config files

| File | Purpose |
|------|---------|
| `/config/nudgarr-config.json` | All settings |
| `/config/nudgarr-state.json` | Search history and cooldowns |
| `/config/nudgarr-stats.json` | Confirmed import records |

---

## Security

Nudgarr is a local network tool. Understanding what it does and doesn't protect is important before deploying it.

**What the built-in login does**
The login screen prevents someone on your network from accessing the UI and changing your configuration. It is not a hardened security layer — it is a basic access control for your local network.

Passwords are stored using PBKDF2-HMAC-SHA256 with a unique random salt. Failed login attempts trigger a progressive lockout to protect against brute force. Timing-safe comparison is used throughout.

**What it does not protect**
- Your Radarr and Sonarr API keys are stored in plaintext in the config file. Anyone with access to your server's filesystem can read them.
- The login does not encrypt traffic. Credentials are sent over plain HTTP unless you put Nudgarr behind a reverse proxy with HTTPS.
- If someone has SSH or physical access to your server, they have access to everything regardless of the login.

**Our approach**
Nudgarr intentionally avoids features that introduce unnecessary attack surface. It does not execute arbitrary code, does not accept external input beyond its own UI, and does not make outbound connections to anything other than your configured Radarr and Sonarr instances.

**Recommendations**
- Run Nudgarr on your LAN only — do not expose port 8085 to the internet
- If you need remote access, use a VPN or a reverse proxy with proper authentication and HTTPS
- Enable the built-in login as a basic layer of protection on your local network

**If you expose Nudgarr to the public internet**
The built-in login is designed for local network use and should not be considered sufficient protection for a publicly accessible instance. If you need to access Nudgarr remotely, the strongly recommended approach is to place it behind a reverse proxy such as NGINX Proxy Manager, Caddy, or Traefik with HTTPS and its own authentication layer — or use a VPN such as Tailscale or WireGuard to access your home network securely. This keeps Nudgarr off the public internet entirely and removes the need to rely solely on the built-in login for security.

**Container hardening (implemented in v2.0.0)**
The provided `docker-compose.yml` includes the following hardening settings out of the box:
- `no-new-privileges` — prevents the container from elevating privileges after start
- `cap_drop: ALL` — removes all Linux capabilities; three are added back explicitly: `CHOWN` (to set /config ownership on startup), `SETUID` and `SETGID` (required for su-exec to drop to your PUID/PGID)
- `pids_limit`, `mem_limit`, `cpus` — limits resource consumption to protect the host
- `tty: false`, `stdin_open: false` — disables unnecessary input channels
- Logging limits — prevents log files from consuming unbounded disk space

**Additional hardening (implemented in v2.1.0)**
- Non-root container user — the container runs as the UID/GID you specify via `PUID` and `PGID`. The entrypoint briefly runs as root to set ownership of `/config`, then immediately drops to your specified user before the app starts. Defaults to `1000:1000` if not set.
- Read-only filesystem — the container filesystem is mounted read-only with a restricted `/tmp` tmpfs (`noexec,nosuid,nodev`), so any payload written inside the container cannot be executed.

These are standard Docker settings and work on any platform.

Locked out? Delete the config file and restart — Nudgarr will regenerate it with defaults.

## Upgrade Notes

**v2.3.0 — Notifications and deployment improvements**
Apprise notifications are off by default — nothing changes for existing users until you configure a URL and enable them. If you are using `cap_drop: ALL` without `cap_add`, update your compose to include `CHOWN`, `SETUID`, and `SETGID` or pre-set your `/config` volume ownership on the host to match your PUID/PGID.

**v2.2.0 — Security hardening and onboarding**
First-run onboarding walkthrough guides new users through every setting before their first run. Safe defaults ensure fresh installs do nothing until the user deliberately enables them. Passwords are now stored using PBKDF2-HMAC-SHA256 with a unique random salt per password, replacing the previous unsalted SHA256 hash. Existing passwords automatically migrate to the new format on next successful login — no action required. A progressive lockout is applied to failed login attempts (3 failures → 30s, 6 → 5min, 10 → 30min, 15+ → 1hr) to protect against brute force attacks.

**v2.1.1 — Lifetime import totals**
The Stats tab now tracks lifetime Movies and Shows totals that persist through Clear Stats. On first run after upgrading, existing confirmed entries are automatically counted and the totals are seeded. This is a one-way migration — downgrading to an earlier version will show zeros on the pills. The stats file itself is not corrupted by downgrading, but the lifetime keys will be ignored by older versions.

**v2.1.0 — Import check delay unit change**
The config key `import_check_hours` was renamed to `import_check_minutes`. The value defaults to 120 minutes (2 hours) if not set. Your config will auto-migrate on next save.

---

## Contributing

Nudgarr is a community-welcome project. Whether you want to fix a bug, improve the code quality, add a feature, or just give feedback — all of it is appreciated.

If you have design skills and want to help with a proper icon or branding, that's something the project genuinely needs. Open an issue or a PR and let's talk.

---

## Inspiration

Nudgarr was inspired by the idea behind tools like Huntarr — automating the tedious parts of library management. We took a different approach: keep it small, keep it focused, and be transparent about what it does and doesn't do.

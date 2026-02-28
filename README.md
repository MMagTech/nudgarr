# Nudgarr
### Because RSS sometimes needs a nudge.

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

```yaml
version: "3.8"
services:
  nudgarr:
    image: ghcr.io/mmagtech/nudgarr:latest
    container_name: nudgarr
    restart: unless-stopped
    ports:
      - "8085:8085"
    volumes:
      - /your/path/to/appdata/nudgarr:/config
    environment:
      - PORT=8085
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
    pids_limit: 512
    mem_limit: 256m
    cpus: 1
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
```

Open the UI at `http://<your-host>:8085`

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

**Container hardening (implemented in v2.0.0)**
The provided `docker-compose.yml` includes the following hardening settings out of the box:
- `no-new-privileges` — prevents the container from elevating privileges after start
- `cap_drop: ALL` — removes all Linux capabilities; Nudgarr does not require any
- `pids_limit`, `mem_limit`, `cpus` — limits resource consumption to protect the host
- `tty: false`, `stdin_open: false` — disables unnecessary input channels
- Logging limits — prevents log files from consuming unbounded disk space

**Additional hardening (implemented in v2.1.0)**
- Non-root container user — the container runs as a dedicated `nudgarr` user. An entrypoint script briefly runs as root to fix `/config` ownership then immediately drops privileges before the app starts.
- Read-only filesystem — the container filesystem is mounted read-only with a restricted `/tmp` tmpfs (`noexec,nosuid,nodev`), so any payload written inside the container cannot be executed.

These are standard Docker settings and work on any platform.

Locked out? Delete the config file and restart — Nudgarr will regenerate it with defaults.

---

## Inspiration

Nudgarr was inspired by the idea behind tools like Huntarr — automating the tedious parts of library management. We took a different approach: keep it small, keep it focused, and be transparent about what it does and doesn't do.

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
- Search history with sweep type (Cutoff Unmet / Backlog Nudge)
- Confirmed import tracking via Stats tab
- UI login to prevent unauthorized config changes
- Download Diagnostic for troubleshooting

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

Locked out? Delete the config file and restart — Nudgarr will run the setup wizard again.

---

## Inspiration

Nudgarr was inspired by the idea behind tools like Huntarr — automating the tedious parts of library management. We took a different approach: keep it small, keep it focused, and be transparent about what it does and doesn't do.

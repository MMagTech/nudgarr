# Nudgarr
### Because RSS sometimes needs a nudge.

Nudgarr is a polite upgrade sweeper for Radarr & Sonarr.

## v1.1.0 adds
- Caps per run for **Radarr movies** and **Sonarr episodes**
- Persistent JSON state DB under `/config` to avoid re-searching too often (cooldown)
- Minimal web UI to edit config and test connections

## Web UI
Open: `http://<your-host>:8085`

- Config: `/config/nudgarr-config.json`
- State:  `/config/nudgarr-state.json`

## Unraid persistence
Map:
- Host: `/mnt/user/appdata/nudgarr`
- Container: `/config`

## Quick start (Unraid)
1. Install: `ghcr.io/mmagtech/nudgarr:latest`
2. Map `/config` and publish port `8085`
3. Start container
4. Use UI to add instances + set caps/cooldown
5. Toggle DRY_RUN off when ready

Security: keep UI behind LAN or your reverse proxy + Auth (API keys are stored in config).

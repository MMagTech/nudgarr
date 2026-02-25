# Nudgarr
### Because RSS sometimes needs a nudge.

Nudgarr is a polite upgrade sweeper for Radarr & Sonarr.

## v1.4.0 highlights
- Clean minimal control panel UI (Instances / Settings / State / Advanced)
- Multiple Radarr/Sonarr instances with add/edit/delete + connection test
- Per-setting descriptions + safe defaults
- State viewer (friendly), Run Now button, and pruning controls
- State size controls:
  - **Retention days** (default 180)
  - **Compact state** by default

## Web UI
Open: `http://<your-host>:8085`

- Config: `/config/nudgarr-config.json`
- State:  `/config/nudgarr-state.json`

## Unraid persistence
Map:
- Host: `/mnt/user/appdata/nudgarr`
- Container: `/config`

## Notes
- Keep the UI behind LAN or your reverse proxy + Auth (API keys are stored in the config file).
- Nudgarr targets **Wanted → Cutoff Unmet** for both apps.

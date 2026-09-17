# API Contract - System Health & Optimization Suite

**Base URL**: `http://localhost:5000` (or configured port)  
**Data Format**: JSON (`Content-Type: application/json`)  
**Design Philosophy**: Minimal payload overhead, lean single-roundtrip endpoints, explicit degradation states.

---

## 1. Live Resource Dashboard

### `GET /api/dashboard`
Fetches real-time system metrics: aggregate health score, CPU utilization, physical memory categorized into 3 plain-language tiers, storage usage, and primary battery/power state.

#### Request
- **Method**: `GET`
- **Headers**: `Accept: application/json`
- **Query Parameters**: None

#### Success Response (`200 OK`)
```json
{
  "timestamp": "2026-09-17T11:30:00Z",
  "health_score": {
    "score": 88,
    "status": "Good",
    "summary": "System running smoothly with low pressure.",
    "breakdown": {
      "cpu_penalty": 4,
      "memory_penalty": 8,
      "disk_penalty": 0,
      "battery_penalty": 0
    }
  },
  "cpu": {
    "total_percent": 14.2,
    "core_count_logical": 8,
    "core_count_physical": 4,
    "frequency_mhz": 2400.0,
    "load_average_1m": 1.15
  },
  "memory": {
    "total_bytes": 4294967296,
    "total_readable": "4.00 GB",
    "in_use_bytes": 1932735283,
    "in_use_readable": "1.80 GB",
    "in_use_percent": 45.0,
    "reclaimable_cache_bytes": 1288490188,
    "reclaimable_cache_readable": "1.20 GB",
    "reclaimable_cache_percent": 30.0,
    "truly_free_bytes": 1073741825,
    "truly_free_readable": "1.00 GB",
    "truly_free_percent": 25.0,
    "cache_explanation": "Reclaimable Cache: RAM temporarily holding recently read files and apps for instant launching; automatically freed the moment running programs request more memory."
  },
  "disk": [
    {
      "mount_point": "/",
      "device": "/dev/sda1",
      "fstype": "ext4",
      "total_bytes": 128849018880,
      "total_readable": "120.0 GB",
      "used_bytes": 64424509440,
      "used_readable": "60.0 GB",
      "free_bytes": 64424509440,
      "free_readable": "60.0 GB",
      "used_percent": 50.0
    }
  ],
  "battery": {
    "has_battery": true,
    "percent": 82,
    "power_plugged": false,
    "seconds_left": 14400,
    "status": "Discharging",
    "status_message": "82% - 4h 0m remaining"
  }
}
```

---

## 2. Battery Drain Analyzer

### `GET /api/battery`
Returns battery telemetry, per-process power drain ranking, and actionable plain-language optimization tips. Handles desktops (no battery detected) cleanly without failing.

#### Request
- **Method**: `GET`
- **Headers**: `Accept: application/json`

#### Success Response (`200 OK`) — Laptop with Battery Detected
```json
{
  "has_battery": true,
  "battery_info": {
    "percent": 45,
    "power_plugged": false,
    "seconds_left": 5400,
    "status": "Discharging",
    "readable_time": "1 hour, 30 minutes remaining"
  },
  "ranking": [
    {
      "pid": 1042,
      "name": "chrome",
      "cpu_percent": 18.4,
      "memory_mb": 420.5,
      "drain_score": 82,
      "impact": "High",
      "tip": "High CPU utilization detected while on battery. Close background tabs or pause video streams."
    },
    {
      "pid": 3211,
      "name": "code",
      "cpu_percent": 4.1,
      "memory_mb": 310.2,
      "drain_score": 35,
      "impact": "Medium",
      "tip": "Moderate background indexing. Consider disabling heavy linting plugins."
    },
    {
      "pid": 589,
      "name": "spotify",
      "cpu_percent": 1.2,
      "memory_mb": 115.0,
      "drain_score": 12,
      "impact": "Low",
      "tip": "Minimal impact."
    }
  ],
  "global_tips": [
    "Battery level is below 50%. Lower display brightness to save up to 20% power.",
    "Chrome is responsible for ~55% of active CPU battery drain."
  ]
}
```

#### Success Response (`200 OK`) — Desktop / No Battery Detected
```json
{
  "has_battery": false,
  "battery_info": {
    "percent": null,
    "power_plugged": true,
    "seconds_left": null,
    "status": "No battery detected",
    "readable_time": "Running on AC Power"
  },
  "ranking": [
    {
      "pid": 1042,
      "name": "chrome",
      "cpu_percent": 18.4,
      "memory_mb": 420.5,
      "drain_score": 82,
      "impact": "High",
      "tip": "Consuming noticeable CPU cycles."
    }
  ],
  "global_tips": [
    "No battery detected. System is running on constant wall AC power.",
    "Battery conservation mode is disabled automatically."
  ]
}
```

---

## 3. Startup Program Impact Analyzer

### `GET /api/startup`
Scans startup entries. Uses platform-native inspection:
- **Windows**: `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` and `HKLM\Software\Microsoft\Windows\CurrentVersion\Run`.
- **Linux**: `~/.config/autostart/*.desktop` and user systemd unit files (`~/.config/systemd/user/`).

If OS-specific inspection encounters permission errors or missing components, it returns a degraded status and clear error message without breaking the app.

#### Request
- **Method**: `GET`
- **Headers**: `Accept: application/json`

#### Success Response (`200 OK`) — Normal Operation (Linux or Windows)
```json
{
  "os": "linux",
  "status": "ok",
  "error_message": null,
  "summary": {
    "total_count": 4,
    "enabled_count": 3,
    "high_impact_count": 1
  },
  "items": [
    {
      "id": "autostart-discord",
      "name": "Discord",
      "command": "/usr/bin/discord --start-minimized",
      "source": "~/.config/autostart/discord.desktop",
      "enabled": true,
      "impact": "High",
      "impact_reason": "Spawns full Electron runtime with multiple worker helper processes during desktop login.",
      "can_toggle": true
    },
    {
      "id": "autostart-steam",
      "name": "Steam",
      "command": "/usr/bin/steam -silent",
      "source": "~/.config/autostart/steam.desktop",
      "enabled": true,
      "impact": "Medium",
      "impact_reason": "Background client checking for library and workshop updates.",
      "can_toggle": true
    },
    {
      "id": "systemd-syncthing",
      "name": "Syncthing Service",
      "command": "/usr/bin/syncthing serve --no-browser",
      "source": "systemd user service",
      "enabled": true,
      "impact": "Low",
      "impact_reason": "Lightweight native sync daemon.",
      "can_toggle": true
    },
    {
      "id": "autostart-dropbox",
      "name": "Dropbox",
      "command": "dropbox start -i",
      "source": "~/.config/autostart/dropbox.desktop",
      "enabled": false,
      "impact": "Medium",
      "impact_reason": "Previously disabled by user.",
      "can_toggle": true
    }
  ]
}
```

#### Success Response (`200 OK`) — Graceful OS Failure / Degraded State
When the OS inspection fails (e.g., permission denied reading registry key, inaccessible directory, or unexpected OS environment):
```json
{
  "os": "windows",
  "status": "degraded",
  "error_message": "Access denied while reading HKLM Run registry key. Showing HKCU entries only.",
  "summary": {
    "total_count": 1,
    "enabled_count": 1,
    "high_impact_count": 0
  },
  "items": [
    {
      "id": "win-onedrive",
      "name": "OneDrive",
      "command": "\"C:\\Users\\User\\AppData\\Local\\Microsoft\\OneDrive\\OneDrive.exe\" /background",
      "source": "HKCU Run Key",
      "enabled": true,
      "impact": "Medium",
      "impact_reason": "Cloud synchronization background agent.",
      "can_toggle": true
    }
  ]
}
```

If the entire OS discovery mechanism encounters an unrecoverable failure:
```json
{
  "os": "unknown",
  "status": "error",
  "error_message": "Failed to inspect startup entries for current platform: Unsupported platform or insufficient permissions.",
  "summary": {
    "total_count": 0,
    "enabled_count": 0,
    "high_impact_count": 0
  },
  "items": []
}
```

---

### `POST /api/startup/toggle`
Safely enables or disables a startup item.
- On Linux: Sets `Hidden=true` / `X-GNOME-Autostart-enabled=false` in the desktop entry, or masks/disables user systemd unit.
- On Windows: Moves entry to `Run-` or backup registry value, or toggles approval flag.

#### Request
- **Method**: `POST`
- **Headers**: `Content-Type: application/json`
- **Body**:
```json
{
  "id": "autostart-discord",
  "enable": false
}
```

#### Success Response (`200 OK`)
```json
{
  "success": true,
  "id": "autostart-discord",
  "enabled": false,
  "message": "Successfully disabled 'Discord' from startup.",
  "error": null
}
```

#### Error Response (`400 Bad Request` or `500 Internal Server Error`)
```json
{
  "success": false,
  "id": "autostart-discord",
  "enabled": true,
  "message": "Failed to modify startup entry.",
  "error": "Permission denied writing to ~/.config/autostart/discord.desktop"
}
```

---

## 4. Standard Error Response Shape
All endpoints return standard JSON on unhandled server or validation errors:

```json
{
  "error": true,
  "status_code": 500,
  "message": "Detailed plain-language explanation of what went wrong.",
  "endpoint": "/api/dashboard"
}
```

# ResourceSense - Project Memory & Status

## 1. Problem Statement
Modern system monitors and optimization suites are frequently bloated Electron applications that consume 300MB–1GB of RAM simply to monitor system health, defeating their own purpose on constrained hardware (such as 4GB RAM systems).

Users also regularly misinterpret OS memory metrics—mistaking beneficial "reclaimable cache" for wasted or leaked memory. Furthermore, many utility suites crash or misbehave on systems without batteries (desktops) or fail abruptly when reading OS-specific startup configurations.

**ResourceSense** is a lightweight, cross-platform (Windows & Linux) System Health & Optimization Suite inspired by the efficiency and dense information architecture of classic Windows Task Manager. It runs with a microscopic footprint, uses plain polling without heavy background daemons, provides plain-language resource explanations, and isolates platform-dependent code so errors degrade gracefully.

---

## 2. Tech Stack (Locked)
- **Backend Runtime**: Python 3.8+
- **Web Framework**: Flask (minimal microframework, serving JSON API and static files)
- **Telemetry & Process Engine**: `psutil` (lean cross-platform system queries)
- **Frontend Architecture**: Plain HTML5, Vanilla CSS, Vanilla JavaScript (ES6+)
  - **No** frontend framework (no React, Vue, Angular)
  - **No** build tools / compilers (no Webpack, Vite, Tailwind, Babel)
  - **No** Electron or Chromium wrappers
- **Deployment & Access**: Served locally at `http://localhost:5000` and opened directly in the user's default web browser.

---

## 3. Done
- [x] Defined complete API contract in [`API_CONTRACT.md`](file:///home/aivin/Desktop/GIt/projects/ResourceSense/API_CONTRACT.md):
  - `GET /api/dashboard` (Live resource metrics, 3-tier memory breakdown, 0-100 health score).
  - `GET /api/battery` (Per-app battery drain ranking, graceful desktop/no-battery response, plain-language tips).
  - `GET /api/startup` (Windows registry + Linux autostart/systemd detection, graceful degradation schema).
  - `POST /api/startup/toggle` (Safe enable/disable endpoint with status verification).
- [x] Initialized project documentation and system design specifications.
- [x] Configured comprehensive [`.gitignore`](file:///home/aivin/Desktop/GIt/projects/ResourceSense/.gitignore) covering Python bytecode, virtual environments (`venv/`), caches, and OS artifacts.
- [x] Initialized Git repository for ResourceSense and pushed clean codebase to GitHub (`aivinjmca2527/ResourceSense`).
- [x] **Backend fully implemented and tested** ([`backend/app.py`](file:///home/aivin/Desktop/GIt/projects/ResourceSense/backend/app.py)):
  - **`GET /api/dashboard`**: Health score (0-100), CPU stats, 3-tier memory breakdown (in-use / reclaimable cache / truly free), filtered disk partitions (squashfs/snap/tmpfs excluded), battery status. Uses a background poller thread (2-second interval) for CPU stats — no busy loops.
  - **`GET /api/battery`**: Battery info with graceful `None` handling (desktops/VMs), per-process drain ranking (top 20, sorted by drain score — 70% CPU + 30% memory weighted), plain-language rule-based tips (no AI), global advisory tips.
  - **`GET /api/startup`**: Linux branch scans `~/.config/autostart/*.desktop` files + `systemctl --user list-unit-files`. Windows branch reads `HKCU\...\Run` and `HKLM\...\Run` via `winreg`. Both branches wrapped in try/except for graceful degradation. Impact estimated via known-app rules + heuristics.
  - **`POST /api/startup/toggle`**: Linux autostart toggle (sets `Hidden=` + `X-GNOME-Autostart-enabled=`), Linux systemd toggle (`systemctl --user enable/disable`), Windows registry toggle (moves to `Run-` backup key). All wrapped in try/except.
  - Standard error JSON shape on all endpoints (`error`, `status_code`, `message`, `endpoint`).
- [x] Virtual environment set up at `backend/venv/` with Flask + psutil.
- [x] **System tray icon** ([`backend/tray.py`](file:///home/aivin/Desktop/GIt/projects/ResourceSense/backend/tray.py)) — implemented with pystray/Pillow. Menu: "Open Dashboard" (opens browser) + "Quit". Integrated into app.py entry point with try/except so it never blocks core functionality.

---

## 4. In Progress / Next
- [ ] Frontend implementation (`static/index.html`, `static/style.css`, `static/app.js`):
  - 3-tab compact layout (Dashboard, Battery Drain, Startup Impact).
  - In-place DOM updates on periodic poll (preventing UI flicker and memory leaks).
  - Memory breakdown visualization with the plain-language cache explanatory tooltip/callout.
  - Startup toggle controls and desktop power indicators.
- [ ] End-to-end testing on Linux and cross-platform verification.

---

## 5. Known Issues & Platform Edge Cases

> [!WARNING]
> **Windows Startup Analyzer Path is UNTESTED.**
> The Windows branch in `_scan_windows_startup()` and `_toggle_windows_startup()` reads/writes registry Run keys via `winreg`. This code was developed and tested exclusively on Ubuntu Linux. The `winreg` module is only available on Windows, so `import winreg` raises `ImportError` on Linux — this is caught and returned as a clear error. The Windows logic follows documented `winreg` API behavior but has **never been run on an actual Windows machine**. Manual verification on Windows is required before considering it production-ready.

1. **Windows Registry Import**: `import winreg` is only available on Windows. Linux environments will raise `ImportError`. All platform-specific imports are guarded conditionally inside try/except blocks.
2. **Missing Battery Hardware**: Desktops and VMs have no battery controller. `psutil.sensors_battery()` returns `None`. Handled gracefully across dashboard and battery analyzer — returns `has_battery: false` with a clean "Running on AC Power" status.
3. **RAM Cache Semantics**:
   - Linux: `cached + buffers` represents reclaimable memory. The backend uses `psutil.virtual_memory().cached + .buffers`.
   - Windows: Working set vs standby cache semantics differ; psutil `available` calculation (`free + cached`) must be normalized to ensure `In Use + Reclaimable + Free = Total`. The backend includes a normalization guard (`if truly_free < 0`).
4. **Startup Permissions**: Toggling startup entries in system paths could fail due to permissions. The API reports permission errors inline in the JSON error response rather than crashing with 500.
5. **Snap/Squashfs Disk Partitions**: On Ubuntu with snap, `psutil.disk_partitions()` returns many squashfs loopback mounts that are always 100% full. These are filtered out from the disk list to avoid noise and false disk penalties.
6. **System Tray (pystray)**: Works on X11 with a system tray manager (e.g., KDE, XFCE). On GNOME/Wayland, pystray's `_xorg.py` backend fails to dock (no `_systray_manager`). The tray failure is logged but does **not** crash the Flask server — the server continues running normally. To get tray icons working on GNOME, install `gnome-shell-extension-appindicator`. The tray is purely optional.

---

## 6. Design Direction
- **Philosophy**: Minimal, dense, and data-focused. No decorative UI weight, heavy animations, or extraneous spacing.
- **Visuals**: Modern dark-mode palette, crisp monospaced or system sans-serif typography (`system-ui`, monospace for metrics), high data density, and clear status badges (`Good` = green, `Degraded/Warning` = amber, `Critical` = red).
- **Footprint**: Zero external font files, zero icon SVG bundles, zero CSS frameworks. Sub-millisecond frontend render passes with plain vanilla DOM updates.

---

## 7. Run Commands & Quick Reference

### Start the backend
```bash
cd /home/aivin/Desktop/GIt/projects/ResourceSense
backend/venv/bin/python backend/app.py
```
Server starts at `http://localhost:5000`.

### curl examples
```bash
# Dashboard (health score, CPU, memory, disk, battery)
curl http://localhost:5000/api/dashboard | python3 -m json.tool

# Battery drain analyzer (process ranking, tips)
curl http://localhost:5000/api/battery | python3 -m json.tool

# Startup program list
curl http://localhost:5000/api/startup | python3 -m json.tool

# Toggle a startup item (disable)
curl -X POST http://localhost:5000/api/startup/toggle \
  -H "Content-Type: application/json" \
  -d '{"id": "autostart-kando", "enable": false}'

# Toggle a startup item (enable)
curl -X POST http://localhost:5000/api/startup/toggle \
  -H "Content-Type: application/json" \
  -d '{"id": "autostart-kando", "enable": true}'
```

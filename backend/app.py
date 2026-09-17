"""
ResourceSense Backend - System Health & Optimization Suite
Flask + psutil backend serving JSON APIs for live system metrics.
"""

import os
import platform
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil
from flask import Flask, jsonify, request

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Polling / caching layer  (2-second interval, no busy-loop)
# ---------------------------------------------------------------------------

_cache = {
    "cpu_percent": 0.0,
    "per_cpu": [],
    "load_avg": (0.0, 0.0, 0.0),
    "updated_at": 0.0,
}
_cache_lock = threading.Lock()
POLL_INTERVAL = 2  # seconds


def _poller():
    """Background thread that updates cached values every POLL_INTERVAL seconds."""
    while True:
        cpu = psutil.cpu_percent(interval=POLL_INTERVAL)  # blocks for interval
        per_cpu = psutil.cpu_percent(percpu=True)
        try:
            load = os.getloadavg()
        except (OSError, AttributeError):
            load = (0.0, 0.0, 0.0)
        with _cache_lock:
            _cache["cpu_percent"] = cpu
            _cache["per_cpu"] = per_cpu
            _cache["load_avg"] = load
            _cache["updated_at"] = time.monotonic()


_poller_thread = threading.Thread(target=_poller, daemon=True)
_poller_thread.start()


def _get_cached_cpu():
    with _cache_lock:
        return _cache["cpu_percent"], _cache["per_cpu"], _cache["load_avg"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bytes_readable(b):
    """Convert bytes to a human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(b) < 1024.0:
            return f"{b:.2f} {unit}"
        b /= 1024.0
    return f"{b:.2f} PB"


def _seconds_readable(secs):
    """Convert seconds to 'Xh Ym' or 'X hours, Y minutes' string."""
    if secs is None or secs < 0:
        return "Unknown"
    h = int(secs // 3600)
    m = int((secs % 3600) // 60)
    if h > 0 and m > 0:
        return f"{h} hour{'s' if h != 1 else ''}, {m} minute{'s' if m != 1 else ''} remaining"
    if h > 0:
        return f"{h} hour{'s' if h != 1 else ''} remaining"
    return f"{m} minute{'s' if m != 1 else ''} remaining"


def _battery_info():
    """Return battery dict, gracefully handling None (desktop/VM)."""
    bat = psutil.sensors_battery()
    if bat is None:
        return {
            "has_battery": False,
            "percent": None,
            "power_plugged": True,
            "seconds_left": None,
            "status": "No battery detected",
            "status_message": "Running on AC Power",
        }
    if bat.power_plugged:
        status = "Charging" if bat.percent < 100 else "Fully Charged"
    else:
        status = "Discharging"
    secs = bat.secsleft if bat.secsleft not in (
        psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN, -1, -2
    ) else None
    pct_rounded = round(bat.percent)
    if secs and secs > 0:
        h = int(secs // 3600)
        m = int((secs % 3600) // 60)
        msg = f"{pct_rounded}% - {h}h {m}m remaining"
    elif bat.power_plugged:
        msg = f"{pct_rounded}% - Plugged in"
    else:
        msg = f"{pct_rounded}%"
    return {
        "has_battery": True,
        "percent": pct_rounded,
        "power_plugged": bat.power_plugged,
        "seconds_left": int(secs) if secs and secs > 0 else None,
        "status": status,
        "status_message": msg,
    }


def _health_score(cpu_pct, mem_pct, disk_max_pct, battery):
    """Compute 0-100 health score with penalty breakdown."""
    # CPU penalty: escalating above 50%
    if cpu_pct > 90:
        cpu_pen = 30
    elif cpu_pct > 70:
        cpu_pen = 20
    elif cpu_pct > 50:
        cpu_pen = 10
    elif cpu_pct > 30:
        cpu_pen = int((cpu_pct - 30) / 20 * 10)
    else:
        cpu_pen = 0

    # Memory penalty: based on in-use percent (not counting cache)
    if mem_pct > 90:
        mem_pen = 30
    elif mem_pct > 70:
        mem_pen = 20
    elif mem_pct > 50:
        mem_pen = 10
    elif mem_pct > 30:
        mem_pen = int((mem_pct - 30) / 20 * 10)
    else:
        mem_pen = 0

    # Disk penalty
    if disk_max_pct > 95:
        disk_pen = 20
    elif disk_max_pct > 85:
        disk_pen = 10
    elif disk_max_pct > 75:
        disk_pen = 5
    else:
        disk_pen = 0

    # Battery penalty (only on battery, low charge)
    bat_pen = 0
    if battery["has_battery"] and not battery.get("power_plugged", True):
        pct = battery.get("percent") or 100
        if pct < 10:
            bat_pen = 15
        elif pct < 20:
            bat_pen = 10
        elif pct < 30:
            bat_pen = 5

    score = max(0, 100 - cpu_pen - mem_pen - disk_pen - bat_pen)

    if score >= 80:
        status = "Good"
        summary = "System running smoothly with low pressure."
    elif score >= 50:
        status = "Warning"
        summary = "System is under moderate load. Some resources are stressed."
    else:
        status = "Critical"
        summary = "System is heavily loaded. Consider closing applications."

    return {
        "score": score,
        "status": status,
        "summary": summary,
        "breakdown": {
            "cpu_penalty": cpu_pen,
            "memory_penalty": mem_pen,
            "disk_penalty": disk_pen,
            "battery_penalty": bat_pen,
        },
    }


# ---------------------------------------------------------------------------
# Endpoint 1: GET /api/dashboard
# ---------------------------------------------------------------------------

@app.route("/api/dashboard")
def dashboard():
    try:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        cpu_pct, per_cpu, load_avg = _get_cached_cpu()

        # CPU info
        freq = psutil.cpu_freq()
        cpu_data = {
            "total_percent": cpu_pct,
            "core_count_logical": psutil.cpu_count(logical=True),
            "core_count_physical": psutil.cpu_count(logical=False),
            "frequency_mhz": round(freq.current, 1) if freq else None,
            "load_average_1m": round(load_avg[0], 2),
        }

        # Memory — three-way breakdown
        vm = psutil.virtual_memory()
        total = vm.total
        # "in use" = used (what the OS reports as actively consumed)
        in_use = vm.used
        # "reclaimable cache" = cached + buffers (Linux); on other OSes use
        # what psutil exposes via the cached attribute
        cached = getattr(vm, "cached", 0) + getattr(vm, "buffers", 0)
        # "truly free" = whatever remains
        truly_free = total - in_use - cached
        if truly_free < 0:
            # Normalise: on some kernels used already includes cache
            truly_free = vm.free
            cached = total - in_use - truly_free

        in_use_pct = round(in_use / total * 100, 1) if total else 0
        cache_pct = round(cached / total * 100, 1) if total else 0
        free_pct = round(truly_free / total * 100, 1) if total else 0

        mem_data = {
            "total_bytes": total,
            "total_readable": _bytes_readable(total),
            "in_use_bytes": in_use,
            "in_use_readable": _bytes_readable(in_use),
            "in_use_percent": in_use_pct,
            "reclaimable_cache_bytes": cached,
            "reclaimable_cache_readable": _bytes_readable(cached),
            "reclaimable_cache_percent": cache_pct,
            "truly_free_bytes": truly_free,
            "truly_free_readable": _bytes_readable(truly_free),
            "truly_free_percent": free_pct,
            "cache_explanation": (
                "Reclaimable Cache: RAM temporarily holding recently read files "
                "and apps for instant launching; automatically freed the moment "
                "running programs request more memory."
            ),
        }

        # Disk — physical partitions only (skip squashfs/snap/tmpfs noise)
        _SKIP_FS = {"squashfs", "tmpfs", "devtmpfs", "overlay"}
        disk_list = []
        disk_max_pct = 0
        for part in psutil.disk_partitions(all=False):
            if part.fstype in _SKIP_FS:
                continue
            if "/snap/" in part.mountpoint or part.device.startswith("/dev/loop"):
                continue
            try:
                usage = psutil.disk_usage(part.mountpoint)
            except PermissionError:
                continue
            used_pct = round(usage.percent, 1)
            if used_pct > disk_max_pct:
                disk_max_pct = used_pct
            disk_list.append({
                "mount_point": part.mountpoint,
                "device": part.device,
                "fstype": part.fstype,
                "total_bytes": usage.total,
                "total_readable": _bytes_readable(usage.total),
                "used_bytes": usage.used,
                "used_readable": _bytes_readable(usage.used),
                "free_bytes": usage.free,
                "free_readable": _bytes_readable(usage.free),
                "used_percent": used_pct,
            })

        # Battery
        battery = _battery_info()

        # Health score
        health = _health_score(cpu_pct, in_use_pct, disk_max_pct, battery)

        return jsonify({
            "timestamp": now,
            "health_score": health,
            "cpu": cpu_data,
            "memory": mem_data,
            "disk": disk_list,
            "battery": battery,
        })
    except Exception as e:
        return jsonify({
            "error": True,
            "status_code": 500,
            "message": str(e),
            "endpoint": "/api/dashboard",
        }), 500


# ---------------------------------------------------------------------------
# Endpoint 2: GET /api/battery
# ---------------------------------------------------------------------------

def _drain_score(cpu_pct, mem_mb):
    """Compute a 0-100 drain score weighted 70% CPU, 30% memory."""
    # CPU component: scale so 100% cpu -> 70 points
    cpu_component = min(cpu_pct, 100) * 0.7
    # Memory component: 500MB+ -> 30 points
    mem_component = min(mem_mb / 500, 1.0) * 30
    return min(100, int(cpu_component + mem_component))


def _impact_label(score):
    if score >= 60:
        return "High"
    if score >= 25:
        return "Medium"
    return "Low"


def _process_tip(name, cpu_pct, mem_mb, impact, has_battery, plugged):
    """Generate a plain-language tip based on rule thresholds."""
    name_lower = name.lower()
    if impact == "High":
        if "chrome" in name_lower or "firefox" in name_lower or "brave" in name_lower:
            if not plugged and has_battery:
                return "High CPU utilization detected while on battery. Close background tabs or pause video streams."
            return "Consuming significant CPU cycles. Close unused tabs to free resources."
        if not plugged and has_battery:
            return f"High CPU utilization detected while on battery. Consider closing or pausing {name}."
        return f"Consuming noticeable CPU cycles. Consider closing {name} if not needed."
    if impact == "Medium":
        if "code" in name_lower or "vscode" in name_lower:
            return "Moderate background indexing. Consider disabling heavy linting plugins."
        return f"Moderate resource usage by {name}."
    return "Minimal impact."


def _get_process_ranking(has_battery, plugged):
    """Build per-process ranking sorted by drain_score descending."""
    procs = []
    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
        try:
            info = proc.info
            cpu_p = info.get("cpu_percent") or 0.0
            mem_bytes = 0
            mi = info.get("memory_info")
            if mi:
                mem_bytes = mi.rss
            mem_mb = round(mem_bytes / (1024 * 1024), 1)
            if cpu_p < 0.1 and mem_mb < 10:
                continue  # skip idle noise
            score = _drain_score(cpu_p, mem_mb)
            impact = _impact_label(score)
            tip = _process_tip(info["name"] or "unknown", cpu_p, mem_mb, impact, has_battery, plugged)
            procs.append({
                "pid": info["pid"],
                "name": info["name"] or "unknown",
                "cpu_percent": round(cpu_p, 1),
                "memory_mb": mem_mb,
                "drain_score": score,
                "impact": impact,
                "tip": tip,
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    procs.sort(key=lambda x: x["drain_score"], reverse=True)
    return procs[:20]  # top 20


def _global_tips(bat_info, ranking):
    """Generate global advisory tips."""
    tips = []
    if not bat_info["has_battery"]:
        tips.append("No battery detected. System is running on constant wall AC power.")
        tips.append("Battery conservation mode is disabled automatically.")
        return tips

    pct = bat_info.get("percent") or 100
    plugged = bat_info.get("power_plugged", True)

    if pct < 20:
        tips.append(f"Battery level is critically low ({pct}%). Connect charger immediately.")
    elif pct < 50:
        tips.append(f"Battery level is below 50%. Lower display brightness to save up to 20% power.")

    if not plugged and ranking:
        # Find top CPU drainer
        top = ranking[0]
        total_cpu = sum(p["cpu_percent"] for p in ranking) or 1
        share = round(top["cpu_percent"] / total_cpu * 100)
        if share > 20:
            tips.append(f"{top['name']} is responsible for ~{share}% of active CPU battery drain.")

    if plugged:
        tips.append("Charger is connected. Battery drain analysis is informational only.")

    return tips


@app.route("/api/battery")
def battery():
    try:
        bat = _battery_info()
        has_battery = bat["has_battery"]
        plugged = bat.get("power_plugged", True)

        ranking = _get_process_ranking(has_battery, plugged)
        tips = _global_tips(bat, ranking)

        # Build battery_info sub-object matching contract shape
        battery_info_resp = {
            "percent": bat["percent"],
            "power_plugged": bat["power_plugged"],
            "seconds_left": bat["seconds_left"],
            "status": bat["status"],
            "readable_time": (
                _seconds_readable(bat["seconds_left"])
                if bat["has_battery"] and bat["seconds_left"]
                else ("Running on AC Power" if not has_battery else bat["status_message"])
            ),
        }

        return jsonify({
            "has_battery": has_battery,
            "battery_info": battery_info_resp,
            "ranking": ranking,
            "global_tips": tips,
        })
    except Exception as e:
        return jsonify({
            "error": True,
            "status_code": 500,
            "message": str(e),
            "endpoint": "/api/battery",
        }), 500


# ---------------------------------------------------------------------------
# Endpoint 3: GET /api/startup  +  POST /api/startup/toggle
# ---------------------------------------------------------------------------

# --- Impact estimation (rule-based by known process names) ---

_KNOWN_IMPACT = {
    # name_lower -> (impact, reason)
    "discord": ("High", "Spawns full Electron runtime with multiple worker helper processes during desktop login."),
    "slack": ("High", "Spawns full Electron runtime with multiple worker helper processes during desktop login."),
    "teams": ("High", "Spawns full Electron runtime with multiple worker helper processes during desktop login."),
    "steam": ("Medium", "Background client checking for library and workshop updates."),
    "dropbox": ("Medium", "Cloud synchronization background agent."),
    "onedrive": ("Medium", "Cloud synchronization background agent."),
    "spotify": ("Medium", "Media streaming client with background activity."),
    "syncthing": ("Low", "Lightweight native sync daemon."),
    "nm-applet": ("Low", "Lightweight system tray network indicator."),
    "blueman": ("Low", "Lightweight Bluetooth manager applet."),
    "gnome-keyring": ("Low", "System credential manager, essential service."),
}


def _estimate_impact(name, command=""):
    """Estimate startup impact from known names or heuristics."""
    name_lower = (name or "").lower()
    for key, (impact, reason) in _KNOWN_IMPACT.items():
        if key in name_lower or key in (command or "").lower():
            return impact, reason
    # Heuristic: electron-based apps tend to be heavy
    cmd_lower = (command or "").lower()
    if "electron" in cmd_lower or "node" in cmd_lower:
        return "High", "Electron-based application; typically heavy at startup."
    if "/usr/lib" in cmd_lower or "/usr/bin" in cmd_lower:
        return "Low", "System utility."
    return "Medium", "Unknown startup application."


# --- Linux startup scanner ---

def _scan_linux_autostart():
    """Scan ~/.config/autostart/*.desktop files."""
    items = []
    errors = []
    autostart_dir = Path.home() / ".config" / "autostart"
    try:
        if not autostart_dir.exists():
            return items, errors
        for desktop_file in sorted(autostart_dir.glob("*.desktop")):
            try:
                content = desktop_file.read_text(errors="replace")
                name = _desktop_field(content, "Name") or desktop_file.stem
                command = _desktop_field(content, "Exec") or ""
                hidden = _desktop_field(content, "Hidden")
                gnome_enabled = _desktop_field(content, "X-GNOME-Autostart-enabled")
                # Enabled unless explicitly disabled
                enabled = True
                if hidden and hidden.lower() == "true":
                    enabled = False
                if gnome_enabled and gnome_enabled.lower() == "false":
                    enabled = False
                impact, reason = _estimate_impact(name, command)
                items.append({
                    "id": f"autostart-{desktop_file.stem}",
                    "name": name,
                    "command": command,
                    "source": f"~/.config/autostart/{desktop_file.name}",
                    "enabled": enabled,
                    "impact": impact,
                    "impact_reason": reason,
                    "can_toggle": True,
                })
            except Exception as e:
                errors.append(f"Error reading {desktop_file.name}: {e}")
    except PermissionError as e:
        errors.append(f"Permission denied accessing {autostart_dir}: {e}")
    except Exception as e:
        errors.append(f"Error scanning autostart directory: {e}")
    return items, errors


def _desktop_field(content, key):
    """Extract a field value from .desktop file content."""
    for line in content.splitlines():
        line = line.strip()
        if line.startswith(f"{key}="):
            return line[len(key) + 1:].strip()
    return None


def _scan_linux_systemd_user():
    """Scan systemd --user unit files for enabled services."""
    items = []
    errors = []
    try:
        result = subprocess.run(
            ["systemctl", "--user", "list-unit-files", "--type=service", "--no-pager", "--plain"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            errors.append(f"systemctl --user failed: {result.stderr.strip()}")
            return items, errors

        for line in result.stdout.strip().splitlines():
            parts = line.split()
            if len(parts) < 2 or parts[0].endswith(".service") is False:
                continue
            unit_name = parts[0]
            state = parts[1]
            if state not in ("enabled", "disabled", "static"):
                continue
            if state == "static":
                continue  # static units can't be toggled
            short_name = unit_name.replace(".service", "")
            # Try to get the ExecStart for the command
            command = ""
            try:
                show = subprocess.run(
                    ["systemctl", "--user", "show", unit_name, "--property=ExecStart"],
                    capture_output=True, text=True, timeout=5,
                )
                if show.returncode == 0:
                    # parse ExecStart=... format
                    raw = show.stdout.strip()
                    if "path=" in raw:
                        # systemd output: { path=/usr/bin/foo ; ... }
                        start = raw.find("path=")
                        end = raw.find(";", start)
                        if start >= 0 and end >= 0:
                            command = raw[start + 5:end].strip()
                    elif raw.startswith("ExecStart="):
                        command = raw[10:].strip()
            except Exception:
                pass

            impact, reason = _estimate_impact(short_name, command)
            items.append({
                "id": f"systemd-{short_name}",
                "name": f"{short_name.replace('-', ' ').title()} Service",
                "command": command or f"systemd user service: {unit_name}",
                "source": "systemd user service",
                "enabled": state == "enabled",
                "impact": impact,
                "impact_reason": reason,
                "can_toggle": True,
            })
    except FileNotFoundError:
        errors.append("systemctl not found. systemd may not be installed.")
    except subprocess.TimeoutExpired:
        errors.append("systemctl --user timed out.")
    except Exception as e:
        errors.append(f"Error scanning systemd user units: {e}")
    return items, errors


def _scan_windows_startup():
    """Scan Windows registry Run keys for startup entries.
    NOTE: This branch is UNTESTED — written for Windows compatibility but
    developed and tested only on Ubuntu. See MEMORY.md.
    """
    items = []
    errors = []
    try:
        import winreg  # only available on Windows

        run_keys = [
            (winreg.HKEY_CURRENT_USER,
             r"Software\Microsoft\Windows\CurrentVersion\Run",
             "HKCU Run Key"),
            (winreg.HKEY_LOCAL_MACHINE,
             r"Software\Microsoft\Windows\CurrentVersion\Run",
             "HKLM Run Key"),
        ]

        for hive, key_path, source_label in run_keys:
            try:
                with winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ) as key:
                    i = 0
                    while True:
                        try:
                            name, value, _ = winreg.EnumValue(key, i)
                            impact, reason = _estimate_impact(name, value)
                            items.append({
                                "id": f"win-{name.lower().replace(' ', '-')}",
                                "name": name,
                                "command": value,
                                "source": source_label,
                                "enabled": True,
                                "impact": impact,
                                "impact_reason": reason,
                                "can_toggle": True,
                            })
                            i += 1
                        except OSError:
                            break  # no more values
            except PermissionError:
                errors.append(f"Access denied while reading {source_label} registry key.")
            except FileNotFoundError:
                pass  # key doesn't exist
            except Exception as e:
                errors.append(f"Error reading {source_label}: {e}")

    except ImportError:
        errors.append("winreg module not available (not running on Windows).")
    except Exception as e:
        errors.append(f"Unexpected error scanning Windows startup: {e}")
    return items, errors


@app.route("/api/startup")
def startup():
    try:
        os_name = platform.system().lower()
        items = []
        errors = []

        if os_name == "linux":
            autostart_items, autostart_errs = _scan_linux_autostart()
            systemd_items, systemd_errs = _scan_linux_systemd_user()
            items = autostart_items + systemd_items
            errors = autostart_errs + systemd_errs
        elif os_name == "windows":
            win_items, win_errs = _scan_windows_startup()
            items = win_items
            errors = win_errs
        else:
            errors.append(f"Unsupported platform: {platform.system()}")

        if errors and not items:
            status = "error"
        elif errors:
            status = "degraded"
        else:
            status = "ok"

        enabled_count = sum(1 for i in items if i["enabled"])
        high_count = sum(1 for i in items if i["impact"] == "High")

        return jsonify({
            "os": os_name if os_name in ("linux", "windows") else "unknown",
            "status": status,
            "error_message": "; ".join(errors) if errors else None,
            "summary": {
                "total_count": len(items),
                "enabled_count": enabled_count,
                "high_impact_count": high_count,
            },
            "items": items,
        })
    except Exception as e:
        return jsonify({
            "error": True,
            "status_code": 500,
            "message": str(e),
            "endpoint": "/api/startup",
        }), 500


# --- POST /api/startup/toggle ---

def _toggle_linux_autostart(item_id, enable):
    """Toggle a .desktop autostart entry by setting Hidden / X-GNOME-Autostart-enabled."""
    stem = item_id.replace("autostart-", "", 1)
    desktop_path = Path.home() / ".config" / "autostart" / f"{stem}.desktop"
    if not desktop_path.exists():
        return False, f"Desktop file not found: {desktop_path}"
    try:
        content = desktop_path.read_text(errors="replace")
        lines = content.splitlines()
        new_lines = []
        found_hidden = False
        found_gnome = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("Hidden="):
                new_lines.append(f"Hidden={'false' if enable else 'true'}")
                found_hidden = True
            elif stripped.startswith("X-GNOME-Autostart-enabled="):
                new_lines.append(f"X-GNOME-Autostart-enabled={'true' if enable else 'false'}")
                found_gnome = True
            else:
                new_lines.append(line)
        if not found_hidden:
            new_lines.append(f"Hidden={'false' if enable else 'true'}")
        if not found_gnome:
            new_lines.append(f"X-GNOME-Autostart-enabled={'true' if enable else 'false'}")
        desktop_path.write_text("\n".join(new_lines) + "\n")
        return True, None
    except PermissionError:
        return False, f"Permission denied writing to {desktop_path}"
    except Exception as e:
        return False, str(e)


def _toggle_linux_systemd(item_id, enable):
    """Enable or disable a systemd --user service."""
    unit = item_id.replace("systemd-", "", 1) + ".service"
    action = "enable" if enable else "disable"
    try:
        result = subprocess.run(
            ["systemctl", "--user", action, unit],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return False, result.stderr.strip() or f"systemctl {action} failed"
        return True, None
    except FileNotFoundError:
        return False, "systemctl not found"
    except subprocess.TimeoutExpired:
        return False, "systemctl timed out"
    except Exception as e:
        return False, str(e)


def _toggle_windows_startup(item_id, enable):
    """Toggle a Windows registry Run key entry.
    NOTE: UNTESTED — see MEMORY.md.
    """
    try:
        import winreg
    except ImportError:
        return False, "winreg module not available (not running on Windows)."

    name = item_id.replace("win-", "", 1).replace("-", " ").title()
    try:
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0,
                            winreg.KEY_READ | winreg.KEY_WRITE) as key:
            if enable:
                # Restore from Run- backup key if exists
                backup_path = r"Software\Microsoft\Windows\CurrentVersion\Run-"
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, backup_path, 0,
                                        winreg.KEY_READ | winreg.KEY_WRITE) as bk:
                        value, vtype = winreg.QueryValueEx(bk, name)
                        winreg.SetValueEx(key, name, 0, vtype, value)
                        winreg.DeleteValue(bk, name)
                except FileNotFoundError:
                    return False, f"No backup found for '{name}' to restore."
            else:
                # Move to Run- backup key
                try:
                    value, vtype = winreg.QueryValueEx(key, name)
                except FileNotFoundError:
                    return False, f"Entry '{name}' not found in Run key."
                backup_path = r"Software\Microsoft\Windows\CurrentVersion\Run-"
                try:
                    bk = winreg.CreateKey(winreg.HKEY_CURRENT_USER, backup_path)
                    winreg.SetValueEx(bk, name, 0, vtype, value)
                    winreg.CloseKey(bk)
                except Exception as e:
                    return False, f"Failed to create backup: {e}"
                winreg.DeleteValue(key, name)
        return True, None
    except PermissionError:
        return False, "Permission denied modifying registry."
    except Exception as e:
        return False, str(e)


@app.route("/api/startup/toggle", methods=["POST"])
def startup_toggle():
    try:
        data = request.get_json(force=True)
        item_id = data.get("id", "")
        enable = data.get("enable", True)

        if not item_id:
            return jsonify({
                "success": False,
                "id": item_id,
                "enabled": not enable,
                "message": "Missing required field: id",
                "error": "No startup item ID provided.",
            }), 400

        os_name = platform.system().lower()

        if os_name == "linux":
            if item_id.startswith("autostart-"):
                ok, err = _toggle_linux_autostart(item_id, enable)
            elif item_id.startswith("systemd-"):
                ok, err = _toggle_linux_systemd(item_id, enable)
            else:
                ok, err = False, f"Unknown item ID format: {item_id}"
        elif os_name == "windows":
            ok, err = _toggle_windows_startup(item_id, enable)
        else:
            ok, err = False, f"Unsupported platform: {platform.system()}"

        if ok:
            # Figure out display name from ID
            display_name = item_id.split("-", 1)[1].replace("-", " ").title() if "-" in item_id else item_id
            action_word = "enabled" if enable else "disabled"
            return jsonify({
                "success": True,
                "id": item_id,
                "enabled": enable,
                "message": f"Successfully {action_word} '{display_name}' from startup.",
                "error": None,
            })
        else:
            return jsonify({
                "success": False,
                "id": item_id,
                "enabled": not enable,
                "message": "Failed to modify startup entry.",
                "error": err,
            }), 500

    except Exception as e:
        return jsonify({
            "error": True,
            "status_code": 500,
            "message": str(e),
            "endpoint": "/api/startup/toggle",
        }), 500


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("ResourceSense backend starting on http://localhost:5000")

    # Optional: start system tray icon
    try:
        from tray import start_tray
        start_tray()
    except Exception as e:
        print(f"[tray] Could not start system tray: {e}")

    app.run(host="0.0.0.0", port=5000, debug=False)


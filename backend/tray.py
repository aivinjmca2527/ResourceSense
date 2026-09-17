"""
ResourceSense System Tray Icon (Optional)
Provides a system tray icon with menu to open dashboard in browser and quit.
Run alongside app.py or import and call start_tray() from app.py.
"""

import threading
import webbrowser
import sys

try:
    from PIL import Image, ImageDraw
    import pystray
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False


DASHBOARD_URL = "http://localhost:5000"


def _create_icon_image(size=64):
    """Create a simple green/dark circle icon programmatically."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Green circle with dark border
    draw.ellipse([2, 2, size - 3, size - 3], fill=(46, 204, 113), outline=(30, 30, 30), width=2)
    # "R" letter in center
    try:
        draw.text((size // 2 - 6, size // 2 - 10), "R", fill=(255, 255, 255))
    except Exception:
        pass
    return img


def _open_dashboard(icon, item):
    webbrowser.open(DASHBOARD_URL)


def _quit_app(icon, item):
    icon.stop()
    # Forcefully exit the whole process (Flask + tray)
    import os
    os._exit(0)


def start_tray():
    """Start the system tray icon in its own thread. Non-blocking."""
    if not TRAY_AVAILABLE:
        print("[tray] pystray/Pillow not installed — skipping tray icon.")
        return None

    icon = pystray.Icon(
        name="ResourceSense",
        icon=_create_icon_image(),
        title="ResourceSense",
        menu=pystray.Menu(
            pystray.MenuItem("Open Dashboard", _open_dashboard, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit ResourceSense", _quit_app),
        ),
    )

    tray_thread = threading.Thread(target=icon.run, daemon=True)
    tray_thread.start()
    print("[tray] System tray icon started.")
    return icon


if __name__ == "__main__":
    # Standalone test
    print("Starting tray icon standalone (Ctrl+C to quit)...")
    icon = start_tray()
    if icon:
        import time
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            icon.stop()
    else:
        print("Tray not available.")

import ctypes
import sys
import threading
import subprocess
from pathlib import Path

import pystray
from pystray import MenuItem as Item, Menu
from PIL import Image, ImageDraw
from win10toast import ToastNotifier
import keyboard  # using `keyboard` lib instead of `pynput` for reliability

APP_NAME = "OneTouch"
toaster = ToastNotifier()
tray_icon = None
touch_enabled = None  # detected at startup


# --- admin elevation ---
def ensure_admin():
    try:
        if ctypes.windll.shell32.IsUserAnAdmin():
            return
    except Exception:
        pass
    # relaunch elevated
    params = " ".join(f'"{a}"' for a in sys.argv)
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
    sys.exit()


# --- powershell helper ---
def run_ps(ps_command: str) -> subprocess.CompletedProcess:
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", ps_command],
        startupinfo=si,
        creationflags=subprocess.CREATE_NO_WINDOW,
        capture_output=True,
        text=True,
        timeout=10
    )


# --- device helpers ---
def get_touch_status() -> bool | None:
    """Return True if enabled, False if disabled, None if not found."""
    cmd = r"(Get-PnpDevice | Where-Object { $_.FriendlyName -like 'HID-compliant touch screen' } | Select-Object -First 1).Status"
    cp = run_ps(cmd)
    out = (cp.stdout or "").strip()
    if not out:
        return None
    return "OK" in out  # OK == enabled


def toggle_touch(enable: bool) -> bool:
    """Enable/disable and return success boolean."""
    if enable:
        cmd = r"Get-PnpDevice | Where-Object { $_.FriendlyName -like 'HID-compliant touch screen' } | Enable-PnpDevice -Confirm:$false"
    else:
        cmd = r"Get-PnpDevice | Where-Object { $_.FriendlyName -like 'HID-compliant touch screen' } | Disable-PnpDevice -Confirm:$false"
    cp = run_ps(cmd)
    return cp.returncode == 0 and not (cp.stderr and "Exception" in cp.stderr)


# --- tray icon drawing ---
def make_icon(enabled: bool) -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    color = (135, 206, 250, 255) if enabled else (255, 255, 255, 255) 
    d.ellipse((8, 8, 56, 56), fill=color)
    return img


def set_tray_state(enabled: bool):
    global tray_icon
    tray_icon.icon = make_icon(enabled)
    tray_icon.title = f"{APP_NAME} – {'Touchscreen Enabled' if enabled else 'Touchscreen Disabled'}"


# --- actions ---
def do_toggle(_icon=None, _item=None):
    global touch_enabled
    if touch_enabled is None:
        touch_enabled = bool(get_touch_status())
    target = not touch_enabled
    ok = toggle_touch(enable=target)
    if not ok:
        current = get_touch_status()
        if current is not None:
            ok = (current == target)
    if ok:
        touch_enabled = target
        set_tray_state(touch_enabled)
        toaster.show_toast(APP_NAME, f"Touchscreen {'Enabled' if touch_enabled else 'Disabled'}",
                           duration=3, threaded=True)
    else:
        toaster.show_toast(APP_NAME, "Failed to toggle (need Admin or device not found)",
                           duration=4, threaded=True)


def on_quit(_icon=None, _item=None):
    tray_icon.stop()
    sys.exit(0)


# --- hotkey ---
def start_hotkey_listener():
    keyboard.add_hotkey("ctrl+alt+t", lambda: do_toggle())
    keyboard.wait()  # keep thread alive


# --- main ---
def main():
    ensure_admin()

    global touch_enabled, tray_icon
    touch_enabled = get_touch_status()
    if touch_enabled is None:
        touch_enabled = True

    menu = Menu(
        Item("Toggle Touchscreen", do_toggle, default=True),
        Item("Quit", on_quit)
    )
    tray_icon = pystray.Icon(APP_NAME, make_icon(touch_enabled), APP_NAME, menu)

    # hotkey listener in background
    threading.Thread(target=start_hotkey_listener, daemon=True).start()

    tray_icon.run()


if __name__ == "__main__":
    main()

"""Windows autostart helpers (HKCU Run key)."""

import sys
from pathlib import Path

try:
    import winreg
except ImportError:  # pragma: no cover - not available outside Windows
    winreg = None

AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_NAME = "NetworkSpeed"
AUTOSTART_ARG = "--tray"


def autostart_supported():
    return winreg is not None and sys.platform == "win32"


def startup_command():
    """Command used by the OS to launch the app hidden in the tray."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" {AUTOSTART_ARG}'

    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")
    executable = pythonw if pythonw.exists() else python
    # The entry point lives next to this module.
    script = Path(__file__).resolve().with_name("main.py")
    return f'"{executable}" "{script}" {AUTOSTART_ARG}'


def is_autostart_enabled():
    if not autostart_supported():
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY) as key:
            value, _ = winreg.QueryValueEx(key, AUTOSTART_NAME)
            return bool(value)
    except OSError:
        return False


def set_autostart(enabled):
    """Add or remove the HKCU Run entry. Returns True on success."""
    if not autostart_supported():
        return False
    try:
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            if enabled:
                winreg.SetValueEx(
                    key, AUTOSTART_NAME, 0, winreg.REG_SZ, startup_command()
                )
            else:
                try:
                    winreg.DeleteValue(key, AUTOSTART_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False

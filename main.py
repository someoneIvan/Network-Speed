"""Application entry point."""

import sys

from PyQt6.QtWidgets import QApplication

from gui import APP_NAME, NetworkSpeedWindow, create_app_icon
from network import collect_results

# Windows groups taskbar buttons by this identifier. Without it the taskbar can
# fall back to the icon of python.exe/pythonw.exe instead of the window icon.
APP_USER_MODEL_ID = "NetworkSpeed.App"


def _set_windows_app_id():
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            APP_USER_MODEL_ID
        )
    except (AttributeError, OSError):
        pass


def run_cli():
    results = collect_results()
    speed = results["speed"]
    if isinstance(speed, tuple):
        download_speed, upload_speed = speed
        print(f"Download: {download_speed:.2f} Mbit/s")
        print(f"Upload: {upload_speed:.2f} Mbit/s")
    else:
        print(f"Speed: {speed}")
    print(f"IP: {results['ip']}")
    print(f"Location: {results['location']}")


def main():
    if "--cli" in sys.argv:
        run_cli()
        return

    _set_windows_app_id()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)

    icon = create_app_icon()
    app.setWindowIcon(icon)

    window = NetworkSpeedWindow(icon)
    # Autostart passes --tray so the app boots silently into the tray.
    if "--tray" not in sys.argv or window.tray is None:
        window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

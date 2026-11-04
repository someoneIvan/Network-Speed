import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from PyQt6.QtCore import QPointF, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap, QPolygonF
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

try:
    import winreg
except ImportError:  # pragma: no cover - not available outside Windows
    winreg = None

# Timeouts in seconds.
CONNECT_TIMEOUT = 5
READ_TIMEOUT = 15
MEASURE_SECONDS = 10.0

DOWNLOAD_URL = "https://speed.cloudflare.com/__down"
UPLOAD_URL = "https://speed.cloudflare.com/__up"
DOWNLOAD_BYTES = 50_000_000  # Cloudflare does not accept 100 MB
UPLOAD_BYTES = 10_000_000

IP_URL = "https://api.ipify.org"
GEO_URL = "https://ipwho.is/"

CHUNK_SIZE = 64 * 1024

AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_NAME = "NetworkSpeed"
AUTOSTART_ARG = "--tray"


def _measure_download(session):
    """Measure download speed in Mbit/s, downloading for at most MEASURE_SECONDS."""
    with session.get(
        DOWNLOAD_URL,
        params={"bytes": DOWNLOAD_BYTES},
        stream=True,
        timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
    ) as response:
        response.raise_for_status()
        started = time.perf_counter()
        received = 0
        for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
            received += len(chunk)
            if time.perf_counter() - started >= MEASURE_SECONDS:
                break
        elapsed = time.perf_counter() - started

    if elapsed <= 0:
        raise RuntimeError("download finished too fast to measure")
    return received * 8 / elapsed / 1_000_000


def _measure_upload(session):
    """Measure upload speed in Mbit/s."""
    payload = b"\0" * UPLOAD_BYTES
    started = time.perf_counter()
    response = session.post(
        UPLOAD_URL,
        data=payload,
        timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
    )
    elapsed = time.perf_counter() - started
    response.raise_for_status()

    if elapsed <= 0:
        raise RuntimeError("upload finished too fast to measure")
    return UPLOAD_BYTES * 8 / elapsed / 1_000_000


def measure_speed():
    """Return (download, upload) in Mbit/s. Raises on failure."""
    # One session for both phases reuses the TLS connection to Cloudflare
    # instead of paying for a second handshake before the upload.
    with requests.Session() as session:
        download_speed = _measure_download(session)
        upload_speed = _measure_upload(session)
    return download_speed, upload_speed


def get_internet_speed():
    try:
        download_speed, upload_speed = measure_speed()
        return f"Download: {download_speed:.2f} Mbit/s, Upload: {upload_speed:.2f} Mbit/s"
    except (requests.RequestException, RuntimeError) as exc:
        return f"Unavailable ({exc.__class__.__name__})"


def get_ip():
    try:
        response = requests.get(IP_URL, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
        response.raise_for_status()
        return response.text.strip()
    except requests.RequestException as exc:
        return f"Unavailable ({exc.__class__.__name__})"


def get_location():
    try:
        response = requests.get(GEO_URL, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
        response.raise_for_status()
        data = response.json()
        if not data.get("success"):
            return "Unknown"
        return f"{data.get('city') or 'Unknown'}, {data.get('country') or 'Unknown'}"
    except (requests.RequestException, ValueError) as exc:
        return f"Unknown ({exc.__class__.__name__})"


def collect_results():
    """Run every check concurrently and return a result payload."""
    with ThreadPoolExecutor(max_workers=3) as executor:
        speed_future = executor.submit(measure_speed)
        ip_future = executor.submit(get_ip)
        location_future = executor.submit(get_location)

        try:
            speed = speed_future.result()
        except (requests.RequestException, RuntimeError) as exc:
            speed = f"Unavailable ({exc.__class__.__name__})"
        ip = ip_future.result()
        location = location_future.result()

    return {"speed": speed, "ip": ip, "location": location}


# --- Autostart (Windows registry) -----------------------------------------


def autostart_supported():
    return winreg is not None and sys.platform == "win32"


def startup_command():
    """Command used by the OS to launch the app hidden in the tray."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" {AUTOSTART_ARG}'

    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")
    executable = pythonw if pythonw.exists() else python
    script = Path(__file__).resolve()
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


# --- Icon ------------------------------------------------------------------


def _icon_pixmap(size):
    """Draw a minimal dark disc with a white bolt."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)

    painter.setBrush(QColor("#16181d"))
    painter.drawEllipse(0, 0, size, size)

    bolt = [(60, 6), (28, 55), (47, 55), (40, 94), (76, 41), (54, 41)]
    scale = size / 100
    painter.setBrush(QColor("#ffffff"))
    painter.drawPolygon(
        QPolygonF([QPointF(x * scale, y * scale) for x, y in bolt])
    )
    painter.end()
    return pixmap


def create_app_icon():
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128):
        icon.addPixmap(_icon_pixmap(size))
    return icon


# --- Worker ----------------------------------------------------------------


class MeasurementWorker(QThread):
    """Runs the network checks off the UI thread."""

    results_ready = pyqtSignal(object)

    def run(self):
        self.results_ready.emit(collect_results())


STYLESHEET = """
#root {
    background: #f4f5f7;
}
QLabel {
    font-family: "Segoe UI", "Inter", sans-serif;
}
#title {
    font-size: 22px;
    font-weight: 600;
    color: #16181d;
}
#subtitle {
    font-size: 12px;
    color: #8b909a;
}
#card {
    background: #ffffff;
    border-radius: 14px;
}
#metricName {
    font-size: 11px;
    font-weight: 600;
    color: #9aa0aa;
}
#metricValue {
    font-size: 30px;
    font-weight: 600;
    color: #16181d;
}
#metricUnit {
    font-size: 11px;
    color: #9aa0aa;
}
#divider {
    background: #edeff2;
}
#rowKey {
    font-size: 13px;
    color: #8b909a;
}
#rowValue {
    font-size: 13px;
    font-weight: 600;
    color: #16181d;
}
#autostart {
    font-size: 12px;
    color: #5c626b;
    spacing: 8px;
}
#status {
    font-size: 12px;
    color: #8b909a;
}
QPushButton {
    background: #16181d;
    color: #ffffff;
    border: none;
    border-radius: 10px;
    padding: 12px 16px;
    font-size: 14px;
    font-weight: 600;
}
QPushButton:hover {
    background: #2c313a;
}
QPushButton:pressed {
    background: #000000;
}
QPushButton:disabled {
    background: #c8ccd2;
}
"""


class NetworkSpeedWindow(QWidget):
    def __init__(self, icon=None):
        super().__init__()
        self._worker = None
        self._quitting = False
        self._tray_message_shown = False
        self.tray = None
        self.tray_menu = None
        self.autostart_checkbox = None
        self.autostart_action = None

        self.icon = icon or create_app_icon()
        self.setWindowIcon(self.icon)
        self.setObjectName("root")
        self.setWindowTitle("Network Speed")
        self.setFixedWidth(360)
        self.setStyleSheet(STYLESHEET)

        self._build_ui()
        self._setup_tray()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 24, 26, 24)
        root.setSpacing(14)

        title = QLabel("Network Speed")
        title.setObjectName("title")
        subtitle = QLabel("Проверка скорости интернет-соединения")
        subtitle.setObjectName("subtitle")
        root.addWidget(title)
        root.addWidget(subtitle)
        root.addSpacing(4)

        # Speed card: download | upload
        metrics = QFrame()
        metrics.setObjectName("card")
        metrics_row = QHBoxLayout(metrics)
        metrics_row.setContentsMargins(20, 18, 20, 18)
        metrics_row.setSpacing(18)
        self.download_value = self._add_metric(metrics_row, "Загрузка ↓")
        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFixedWidth(1)
        metrics_row.addWidget(divider)
        self.upload_value = self._add_metric(metrics_row, "Выгрузка ↑")
        root.addWidget(metrics)

        # Details card: IP + location
        details = QFrame()
        details.setObjectName("card")
        grid = QGridLayout(details)
        grid.setContentsMargins(20, 14, 20, 14)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        self.ip_value = self._add_row(grid, 0, "IP-адрес")
        self.location_value = self._add_row(grid, 1, "Расположение")
        grid.setColumnStretch(1, 1)
        root.addWidget(details)

        self.autostart_checkbox = QCheckBox("Запускать при входе в Windows")
        self.autostart_checkbox.setObjectName("autostart")
        self.autostart_checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        self.autostart_checkbox.setChecked(is_autostart_enabled())
        self.autostart_checkbox.setVisible(autostart_supported())
        self.autostart_checkbox.toggled.connect(self._set_autostart)
        root.addWidget(self.autostart_checkbox)

        self.status = QLabel("Готово к проверке")
        self.status.setObjectName("status")
        root.addWidget(self.status)

        self.button = QPushButton("Проверить скорость")
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button.setDefault(True)
        self.button.clicked.connect(self.start_measurement)
        root.addWidget(self.button)

    def _add_metric(self, parent_layout, name):
        column = QVBoxLayout()
        column.setSpacing(2)
        name_label = QLabel(name.upper())
        name_label.setObjectName("metricName")
        value = QLabel("—")
        value.setObjectName("metricValue")
        unit = QLabel("Mbit/s")
        unit.setObjectName("metricUnit")
        column.addWidget(name_label)
        column.addWidget(value)
        column.addWidget(unit)
        parent_layout.addLayout(column, 1)
        return value

    def _add_row(self, grid, row, key):
        key_label = QLabel(key)
        key_label.setObjectName("rowKey")
        value_label = QLabel("—")
        value_label.setObjectName("rowValue")
        value_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        value_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        grid.addWidget(key_label, row, 0)
        grid.addWidget(value_label, row, 1)
        return value_label

    # --- Tray -------------------------------------------------------------

    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        self.tray = QSystemTrayIcon(self.icon, self)
        self.tray.setToolTip("Network Speed")

        self.tray_menu = QMenu()
        show_action = self.tray_menu.addAction("Показать окно")
        show_action.triggered.connect(self.show_window)
        measure_action = self.tray_menu.addAction("Проверить скорость")
        measure_action.triggered.connect(self._measure_from_tray)
        self.tray_menu.addSeparator()
        self.autostart_action = self.tray_menu.addAction("Автозапуск")
        self.autostart_action.setCheckable(True)
        self.autostart_action.setChecked(is_autostart_enabled())
        self.autostart_action.setVisible(autostart_supported())
        self.autostart_action.toggled.connect(self._set_autostart)
        self.tray_menu.addSeparator()
        quit_action = self.tray_menu.addAction("Выход")
        quit_action.triggered.connect(self.quit_app)

        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

        # Closing the window should keep the app alive in the tray.
        QApplication.instance().setQuitOnLastWindowClosed(False)

    def _on_tray_activated(self, reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_window()

    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _measure_from_tray(self):
        self.show_window()
        self.start_measurement()

    def closeEvent(self, event):
        if self._quitting or self.tray is None:
            event.accept()
            return
        event.ignore()
        self.hide()
        if not self._tray_message_shown:
            self.tray.showMessage(
                "Network Speed",
                "Приложение свёрнуто в трей и продолжает работать.",
                QSystemTrayIcon.MessageIcon.Information,
                2500,
            )
            self._tray_message_shown = True

    # --- Autostart --------------------------------------------------------

    def _set_autostart(self, enabled):
        if not autostart_supported():
            return
        if set_autostart(enabled):
            self._sync_autostart_controls(enabled)
            if not (self._worker is not None and self._worker.isRunning()):
                self.status.setStyleSheet("")
                self.status.setText(
                    "Автозапуск включён" if enabled else "Автозапуск выключен"
                )
        else:
            self._sync_autostart_controls(is_autostart_enabled())
            self.status.setStyleSheet("color: #d9534f;")
            self.status.setText("Не удалось изменить автозапуск")

    def _sync_autostart_controls(self, enabled):
        for widget in (self.autostart_checkbox, self.autostart_action):
            if widget is None:
                continue
            widget.blockSignals(True)
            widget.setChecked(enabled)
            widget.blockSignals(False)

    # --- Measurement ------------------------------------------------------

    def start_measurement(self):
        if self._worker is not None and self._worker.isRunning():
            return

        self.button.setEnabled(False)
        self.button.setText("Измерение…")
        self.status.setStyleSheet("")
        self.status.setText("Измерение скорости и сбор данных…")
        if self.tray is not None:
            self.tray.setToolTip("Network Speed — измерение…")
        for label in (
            self.download_value,
            self.upload_value,
            self.ip_value,
            self.location_value,
        ):
            label.setText("—")

        self._worker = MeasurementWorker()
        self._worker.results_ready.connect(self.show_results)
        self._worker.start()

    def show_results(self, results):
        speed = results.get("speed")
        if isinstance(speed, tuple):
            download_speed, upload_speed = speed
            self.download_value.setText(f"{download_speed:.2f}")
            self.upload_value.setText(f"{upload_speed:.2f}")
            self.status.setText("Проверка завершена")
            if self.tray is not None:
                self.tray.setToolTip(
                    f"Network Speed — ↓ {download_speed:.2f} "
                    f"↑ {upload_speed:.2f} Mbit/s"
                )
        else:
            self.download_value.setText("—")
            self.upload_value.setText("—")
            self.status.setStyleSheet("color: #d9534f;")
            self.status.setText(f"Не удалось измерить скорость: {speed}")
            if self.tray is not None:
                self.tray.setToolTip("Network Speed — ошибка измерения")

        self.ip_value.setText(str(results.get("ip", "—")))
        self.location_value.setText(str(results.get("location", "—")))

        self.button.setEnabled(True)
        self.button.setText("Проверить скорость")

    def quit_app(self):
        self._quitting = True
        if self._worker is not None and self._worker.isRunning():
            if not self._worker.wait(1500):
                self._worker.terminate()
                self._worker.wait()
        if self.tray is not None:
            self.tray.hide()
        QApplication.instance().quit()


def run_cli():
    results = collect_results()
    print(f"Speed: {results['speed']}")
    print(f"IP: {results['ip']}")
    print(f"Location: {results['location']}")


def main():
    if "--cli" in sys.argv:
        run_cli()
        return

    app = QApplication(sys.argv)
    app.setApplicationName("Network Speed")

    icon = create_app_icon()
    app.setWindowIcon(icon)

    window = NetworkSpeedWindow(icon)
    # Autostart passes --tray so the app boots silently into the tray.
    if "--tray" not in sys.argv or window.tray is None:
        window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

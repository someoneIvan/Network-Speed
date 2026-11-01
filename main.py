import sys
import time
from concurrent.futures import ThreadPoolExecutor

import requests
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

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
    def __init__(self):
        super().__init__()
        self._worker = None

        self.setObjectName("root")
        self.setWindowTitle("Network Speed")
        self.setFixedWidth(360)
        self.setStyleSheet(STYLESHEET)

        self._build_ui()

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

    def start_measurement(self):
        if self._worker is not None and self._worker.isRunning():
            return

        self.button.setEnabled(False)
        self.button.setText("Измерение…")
        self.status.setStyleSheet("")
        self.status.setText("Измерение скорости и сбор данных…")
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
        else:
            self.download_value.setText("—")
            self.upload_value.setText("—")
            self.status.setStyleSheet("color: #d9534f;")
            self.status.setText(f"Не удалось измерить скорость: {speed}")

        self.ip_value.setText(str(results.get("ip", "—")))
        self.location_value.setText(str(results.get("location", "—")))

        self.button.setEnabled(True)
        self.button.setText("Проверить скорость")


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
    window = NetworkSpeedWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

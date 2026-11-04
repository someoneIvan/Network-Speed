"""Minimal PyQt6 interface for the network speed app."""

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

from autostart import autostart_supported, is_autostart_enabled, set_autostart
from network import collect_results
from styles import ERROR_TEXT_STYLE, STYLESHEET

APP_NAME = "Network Speed"
EMPTY_VALUE = "—"
MEASURE_TEXT = "Проверить скорость"
MEASURE_BUSY_TEXT = "Измерение…"
MEASURE_TOOLTIP = "измерение…"


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


class MeasurementWorker(QThread):
    """Runs the network checks off the UI thread."""

    results_ready = pyqtSignal(object)

    def run(self):
        self.results_ready.emit(collect_results())


class NetworkSpeedWindow(QWidget):
    def __init__(self, icon=None):
        super().__init__()
        self._worker = None
        self._quitting = False
        self._tray_message_shown = False
        self._autostart_on = is_autostart_enabled()
        self.tray = None
        self.tray_menu = None
        self.autostart_checkbox = None
        self.autostart_action = None

        self.icon = icon or create_app_icon()
        self.setWindowIcon(self.icon)
        self.setObjectName("root")
        self.setWindowTitle(APP_NAME)
        self.setFixedWidth(360)
        self.setStyleSheet(STYLESHEET)

        self._build_ui()
        self._setup_tray()

    # --- Layout -----------------------------------------------------------

    @staticmethod
    def _card():
        card = QFrame()
        card.setObjectName("card")
        return card

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 24, 26, 24)
        root.setSpacing(14)

        title = QLabel(APP_NAME)
        title.setObjectName("title")
        subtitle = QLabel("Проверка скорости интернет-соединения")
        subtitle.setObjectName("subtitle")
        root.addWidget(title)
        root.addWidget(subtitle)
        root.addSpacing(4)

        # Speed card: download | upload
        metrics = self._card()
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
        details = self._card()
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
        self.autostart_checkbox.setChecked(self._autostart_on)
        self.autostart_checkbox.setVisible(autostart_supported())
        self.autostart_checkbox.toggled.connect(self._set_autostart)
        root.addWidget(self.autostart_checkbox)

        self.status = QLabel("Готово к проверке")
        self.status.setObjectName("status")
        root.addWidget(self.status)

        self.button = QPushButton(MEASURE_TEXT)
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button.setDefault(True)
        self.button.clicked.connect(self.start_measurement)
        root.addWidget(self.button)

    def _add_metric(self, parent_layout, name):
        column = QVBoxLayout()
        column.setSpacing(2)
        name_label = QLabel(name.upper())
        name_label.setObjectName("metricName")
        value = QLabel(EMPTY_VALUE)
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
        value_label = QLabel(EMPTY_VALUE)
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
        self.tray.setToolTip(APP_NAME)

        self.tray_menu = QMenu()
        show_action = self.tray_menu.addAction("Показать окно")
        show_action.triggered.connect(self.show_window)
        measure_action = self.tray_menu.addAction(MEASURE_TEXT)
        measure_action.triggered.connect(self._measure_from_tray)
        self.tray_menu.addSeparator()
        self.autostart_action = self.tray_menu.addAction("Автозапуск")
        self.autostart_action.setCheckable(True)
        self.autostart_action.setChecked(self._autostart_on)
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

    def _set_tray_tooltip(self, text):
        if self.tray is not None:
            self.tray.setToolTip(f"{APP_NAME} — {text}")

    def closeEvent(self, event):
        if self._quitting or self.tray is None:
            event.accept()
            return
        event.ignore()
        self.hide()
        if not self._tray_message_shown:
            self.tray.showMessage(
                APP_NAME,
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
            self._autostart_on = enabled
            self._sync_autostart_controls(enabled)
            if not (self._worker is not None and self._worker.isRunning()):
                self._set_status(
                    "Автозапуск включён" if enabled else "Автозапуск выключен"
                )
        else:
            self._autostart_on = is_autostart_enabled()
            self._sync_autostart_controls(self._autostart_on)
            self._set_status("Не удалось изменить автозапуск", error=True)

    def _sync_autostart_controls(self, enabled):
        for widget in (self.autostart_checkbox, self.autostart_action):
            if widget is None:
                continue
            widget.blockSignals(True)
            widget.setChecked(enabled)
            widget.blockSignals(False)

    # --- Measurement ------------------------------------------------------

    def _set_status(self, text, error=False):
        self.status.setStyleSheet(ERROR_TEXT_STYLE if error else "")
        self.status.setText(text)

    def _clear_values(self):
        for label in (
            self.download_value,
            self.upload_value,
            self.ip_value,
            self.location_value,
        ):
            label.setText(EMPTY_VALUE)

    def start_measurement(self):
        if self._worker is not None and self._worker.isRunning():
            return

        self.button.setEnabled(False)
        self.button.setText(MEASURE_BUSY_TEXT)
        self._set_status("Измерение скорости и сбор данных…")
        self._set_tray_tooltip(MEASURE_TOOLTIP)
        self._clear_values()

        self._worker = MeasurementWorker()
        self._worker.results_ready.connect(self.show_results)
        self._worker.start()

    def show_results(self, results):
        speed = results.get("speed")
        if isinstance(speed, tuple):
            download_speed, upload_speed = speed
            self.download_value.setText(f"{download_speed:.2f}")
            self.upload_value.setText(f"{upload_speed:.2f}")
            self._set_status("Проверка завершена")
            self._set_tray_tooltip(
                f"↓ {download_speed:.2f} ↑ {upload_speed:.2f} Mbit/s"
            )
        else:
            self._clear_values()
            self._set_status(f"Не удалось измерить скорость: {speed}", error=True)
            self._set_tray_tooltip("ошибка измерения")

        self.ip_value.setText(str(results.get("ip", EMPTY_VALUE)))
        self.location_value.setText(str(results.get("location", EMPTY_VALUE)))

        self.button.setEnabled(True)
        self.button.setText(MEASURE_TEXT)

    def quit_app(self):
        self._quitting = True
        if self._worker is not None and self._worker.isRunning():
            if not self._worker.wait(1500):
                self._worker.terminate()
                self._worker.wait()
        if self.tray is not None:
            self.tray.hide()
        QApplication.instance().quit()

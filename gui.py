"""Minimal PyQt6 interface for the network speed app."""

import math
import sys

from PyQt6.QtCore import QPointF, QSize, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QIcon,
    QPainter,
    QPalette,
    QPen,
    QPixmap,
    QPolygonF,
)
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
from styles import (
    DARK_MENU_STYLESHEET,
    DARK_STYLESHEET,
    ERROR_TEXT_STYLE,
    ERROR_TEXT_STYLE_LIGHT,
    LIGHT_MENU_STYLESHEET,
    LIGHT_STYLESHEET,
)

APP_NAME = "Network Speed"
EMPTY_VALUE = "—"
MEASURE_TEXT = "Проверить скорость"
MEASURE_BUSY_TEXT = "Измерение…"
MEASURE_TOOLTIP = "измерение…"

# The icon is rendered once at a large size and smoothly downsampled to every
# size Qt asks for. Rendering each small size directly makes the bolt look
# pixelated and clips the disc at the right/bottom edges.
ICON_MASTER_SIZE = 1024
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def _render_icon_master():
    """Render a high-resolution disc with a white bolt."""
    size = ICON_MASTER_SIZE
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    painter.setPen(Qt.PenStyle.NoPen)

    scale = size / 100
    # Keep a small transparent margin so the disc is never clipped.
    painter.setBrush(QColor("#16181d"))
    painter.drawEllipse(
        QPointF(50 * scale, 50 * scale), 48 * scale, 48 * scale
    )

    bolt = [(60, 6), (28, 55), (47, 55), (40, 94), (76, 41), (54, 41)]
    painter.setBrush(QColor("#ffffff"))
    painter.drawPolygon(
        QPolygonF([QPointF(x * scale, y * scale) for x, y in bolt])
    )
    painter.end()
    return pixmap


def _icon_pixmap(size, master=None):
    """Return a crisp icon of the requested size."""
    if master is None:
        master = _render_icon_master()
    return master.scaled(
        size,
        size,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def create_app_icon():
    master = _render_icon_master()
    icon = QIcon()
    for size in ICON_SIZES:
        icon.addPixmap(_icon_pixmap(size, master))
    return icon


def _theme_icon_pixmap(dark):
    """Draw a sun (dark mode) or a crescent moon (light mode)."""
    size = 128
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    color = QColor("#f5f7fa") if dark else QColor("#16181d")

    center = QPointF(size / 2, size / 2)
    if dark:
        # Sun: click to switch to the light theme.
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(color, size * 0.055))
        radius = size * 0.16
        painter.drawEllipse(center, radius, radius)
        for index in range(8):
            angle = index * math.pi / 4
            inner = size * 0.28
            outer = size * 0.39
            painter.drawLine(
                QPointF(
                    center.x() + inner * math.cos(angle),
                    center.y() + inner * math.sin(angle),
                ),
                QPointF(
                    center.x() + outer * math.cos(angle),
                    center.y() + outer * math.sin(angle),
                ),
            )
    else:
        # Crescent moon: click to switch to the dark theme.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(
            QPointF(size * 0.46, size * 0.5), size * 0.32, size * 0.32
        )
        painter.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_Clear
        )
        painter.drawEllipse(
            QPointF(size * 0.62, size * 0.46), size * 0.30, size * 0.30
        )
        painter.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_SourceOver
        )

    painter.end()
    return pixmap


def _theme_icon(dark):
    master = _theme_icon_pixmap(dark)
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128):
        icon.addPixmap(
            master.scaled(
                size,
                size,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
    return icon


class MeasurementWorker(QThread):
    """Runs the network checks off the UI thread."""

    results_ready = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            results = collect_results(cancel=lambda: self._cancelled)
        except Exception as exc:
            if self._cancelled:
                return
            # Keep the UI responsive on unexpected errors.
            results = {
                "speed": f"Unavailable ({exc.__class__.__name__})",
                "ip": EMPTY_VALUE,
                "location": EMPTY_VALUE,
            }
        self.results_ready.emit(results)


class NetworkSpeedWindow(QWidget):
    def __init__(self, icon=None):
        super().__init__()
        self._worker = None
        self._quitting = False
        self._tray_message_shown = False
        self._autostart_on = is_autostart_enabled()
        self._dark = True
        self._status_is_error = False
        self.tray = None
        self.tray_menu = None
        self.autostart_checkbox = None
        self.autostart_action = None
        self.theme_action = None
        self.theme_button = None

        self.icon = icon or create_app_icon()
        self.setWindowIcon(self.icon)
        self.setObjectName("root")
        self.setWindowTitle(APP_NAME)
        self.setFixedWidth(360)
        self.setStyleSheet(DARK_STYLESHEET)
        self._apply_palette(dark=True)

        self._build_ui()
        self._setup_tray()
        self._update_theme_button()
        self._apply_dark_titlebar()

    # --- Theme ------------------------------------------------------------

    def _apply_dark_titlebar(self):
        """Make the Windows title bar match the selected theme."""
        if sys.platform != "win32":
            return
        try:
            import ctypes
            from ctypes import wintypes

            hwnd = int(self.winId())
            value = wintypes.BOOL(self._dark)
            dwmapi = ctypes.windll.dwmapi
            # 20 works on Windows 10 2004+ and Windows 11; 19 on older
            # Windows 10 builds. Ignore the result on unsupported systems.
            for attribute in (20, 19):
                result = dwmapi.DwmSetWindowAttribute(
                    hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)
                )
                if result == 0:
                    return
        except (AttributeError, OSError):
            pass

    def _apply_tray_menu_theme(self):
        """Style the tray menu explicitly (it does not inherit the window QSS)."""
        if self.tray_menu is None:
            return
        self.tray_menu.setStyleSheet(
            DARK_MENU_STYLESHEET if self._dark else LIGHT_MENU_STYLESHEET
        )
        self.tray_menu.setPalette(self._build_palette(self._dark))
        self.tray_menu.update()

    def _toggle_theme(self):
        self.set_theme(not self._dark)

    def _update_theme_button(self):
        if self.theme_button is None:
            return
        self.theme_button.setIcon(_theme_icon(self._dark))
        self.theme_button.setToolTip(
            "Включить светлую тему" if self._dark else "Включить тёмную тему"
        )
        self.theme_button.setAccessibleName(self.theme_button.toolTip())

    @staticmethod
    def _build_palette(dark):
        palette = QPalette()
        if dark:
            window = QColor("#0f1115")
            text = QColor("#f5f7fa")
            base = QColor("#1a1d24")
            button = QColor("#1a1d24")
            muted = QColor("#9aa3b2")
            tooltip = QColor("#1a1d24")
        else:
            window = QColor("#f4f5f7")
            text = QColor("#16181d")
            base = QColor("#ffffff")
            button = QColor("#f4f5f7")
            muted = QColor("#5c626b")
            tooltip = QColor("#ffffdc")

        highlight = QColor("#3b82f6")
        palette.setColor(QPalette.ColorRole.Window, window)
        palette.setColor(QPalette.ColorRole.WindowText, text)
        palette.setColor(QPalette.ColorRole.Base, base)
        palette.setColor(QPalette.ColorRole.AlternateBase, base)
        palette.setColor(QPalette.ColorRole.Text, text)
        palette.setColor(QPalette.ColorRole.Button, button)
        palette.setColor(QPalette.ColorRole.ButtonText, text)
        palette.setColor(QPalette.ColorRole.Highlight, highlight)
        palette.setColor(
            QPalette.ColorRole.HighlightedText, QColor("#ffffff")
        )
        palette.setColor(QPalette.ColorRole.ToolTipBase, tooltip)
        palette.setColor(QPalette.ColorRole.ToolTipText, text)
        palette.setColor(QPalette.ColorRole.PlaceholderText, muted)
        palette.setColor(
            QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, muted
        )
        palette.setColor(
            QPalette.ColorGroup.Disabled,
            QPalette.ColorRole.ButtonText,
            muted,
        )
        return palette

    def _apply_palette(self, dark):
        app = QApplication.instance()
        if app is not None:
            app.setPalette(self._build_palette(dark))

    def set_theme(self, dark):
        """Switch between the dark and light interface themes."""
        self._dark = bool(dark)
        self.setStyleSheet(
            DARK_STYLESHEET if self._dark else LIGHT_STYLESHEET
        )
        self._apply_palette(self._dark)
        self._apply_dark_titlebar()
        self._apply_tray_menu_theme()
        self._update_theme_button()
        if self._status_is_error:
            self._set_status(self.status.text(), error=True)
        if self.theme_action is not None:
            self.theme_action.blockSignals(True)
            self.theme_action.setChecked(self._dark)
            self.theme_action.blockSignals(False)

    def showEvent(self, event):
        super().showEvent(event)
        # The native title bar exists only after the window is shown.
        self._apply_dark_titlebar()

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

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)

        title = QLabel(APP_NAME)
        title.setObjectName("title")
        header.addWidget(title)
        header.addStretch(1)

        self.theme_button = QPushButton()
        self.theme_button.setObjectName("themeButton")
        self.theme_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_button.setFlat(True)
        self.theme_button.setFixedSize(32, 32)
        self.theme_button.setIconSize(QSize(20, 20))
        self.theme_button.clicked.connect(self._toggle_theme)
        header.addWidget(self.theme_button)
        root.addLayout(header)

        subtitle = QLabel("Проверка скорости интернет-соединения")
        subtitle.setObjectName("subtitle")
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
        self.status.setWordWrap(True)
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
        value_label.setWordWrap(True)
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
        measure_action = self.tray_menu.addAction(MEASURE_TEXT)
        measure_action.triggered.connect(self._measure_from_tray)
        self.tray_menu.addSeparator()
        self.theme_action = self.tray_menu.addAction("Тёмная тема")
        self.theme_action.setCheckable(True)
        self.theme_action.setChecked(self._dark)
        self.theme_action.toggled.connect(self.set_theme)
        self.autostart_action = self.tray_menu.addAction("Автозапуск")
        self.autostart_action.setCheckable(True)
        self.autostart_action.setChecked(self._autostart_on)
        self.autostart_action.setVisible(autostart_supported())
        self.autostart_action.toggled.connect(self._set_autostart)
        self.tray_menu.addSeparator()
        quit_action = self.tray_menu.addAction("Выход")
        quit_action.triggered.connect(self.quit_app)

        self.tray.setContextMenu(self.tray_menu)
        self._apply_tray_menu_theme()
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
        self._status_is_error = bool(error)
        error_style = ERROR_TEXT_STYLE if self._dark else ERROR_TEXT_STYLE_LIGHT
        self.status.setStyleSheet(error_style if error else "")
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
        if self._quitting:
            return
        self._quitting = True
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.cancel()
            self._set_status("Завершение…")
            QApplication.instance().processEvents()
            if not worker.wait(1000):
                # A blocking request cannot be interrupted instantly. Wait for
                # the worker instead of terminating a running Python thread.
                self._wait_for_worker(worker)
                return
        self._worker = None
        self._finalize_quit()

    def _wait_for_worker(self, worker):
        if worker.isRunning():
            QTimer.singleShot(100, lambda: self._wait_for_worker(worker))
            return
        self._worker = None
        self._finalize_quit()

    def _finalize_quit(self):
        if self.tray is not None:
            self.tray.hide()
        QApplication.instance().quit()

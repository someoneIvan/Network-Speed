"""Minimal PyQt6 interface for the network speed app."""

import math
import sys

from PyQt6.QtCore import (
    QPointF,
    QRect,
    QRectF,
    QSize,
    Qt,
    QThread,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
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
    QSizePolicy,
    QStyle,
    QStyleOptionButton,
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
DEFAULT_LANGUAGE = "en"

TRANSLATIONS = {
    "en": {
        "subtitle": "Internet connection speed test",
        "download": "Download ↓",
        "upload": "Upload ↑",
        "ip": "IP-address",
        "provider": "Provider",
        "location": "Location",
        "ping": "Ping",
        "autostart": "Launch at Windows startup",
        "ready": "Ready to test",
        "measure": "Test speed",
        "measuring": "Measuring…",
        "measuring_status": "Measuring speed and collecting data…",
        "complete": "Test complete",
        "speed_error": "Could not measure speed: {speed}",
        "dark_theme": "Dark theme",
        "autostart_action": "Autostart",
        "quit": "Quit",
        "tray_message": "The app is minimized to the tray and keeps running.",
        "tray_measuring": "measuring…",
        "tray_error": "measurement error",
        "autostart_on": "Autostart enabled",
        "autostart_off": "Autostart disabled",
        "autostart_error": "Could not change autostart",
        "theme_to_light": "Switch to light theme",
        "theme_to_dark": "Switch to dark theme",
        "language_to_russian": "Switch to Russian",
        "language_to_english": "Switch to English",
        "finishing": "Finishing…",
    },
    "ru": {
        "subtitle": "Проверка скорости интернет-соединения",
        "download": "Загрузка ↓",
        "upload": "Выгрузка ↑",
        "ip": "IP-адрес",
        "provider": "Провайдер",
        "location": "Расположение",
        "ping": "Пинг",
        "autostart": "Запускать при входе в Windows",
        "ready": "Готово к проверке",
        "measure": "Проверить скорость",
        "measuring": "Измерение…",
        "measuring_status": "Измерение скорости и сбор данных…",
        "complete": "Проверка завершена",
        "speed_error": "Не удалось измерить скорость: {speed}",
        "dark_theme": "Тёмная тема",
        "autostart_action": "Автозапуск",
        "quit": "Выход",
        "tray_message": "Приложение свёрнуто в трей и продолжает работать.",
        "tray_measuring": "измерение…",
        "tray_error": "ошибка измерения",
        "autostart_on": "Автозапуск включён",
        "autostart_off": "Автозапуск выключен",
        "autostart_error": "Не удалось изменить автозапуск",
        "theme_to_light": "Включить светлую тему",
        "theme_to_dark": "Включить тёмную тему",
        "language_to_russian": "Включить русский язык",
        "language_to_english": "Включить английский язык",
        "finishing": "Завершение…",
    },
}

MEASURE_TEXT = TRANSLATIONS[DEFAULT_LANGUAGE]["measure"]
MEASURE_BUSY_TEXT = TRANSLATIONS[DEFAULT_LANGUAGE]["measuring"]
MEASURE_TOOLTIP = TRANSLATIONS[DEFAULT_LANGUAGE]["tray_measuring"]

# Long locations shrink their font and wrap to at most four lines.
LOCATION_MAX_LINES = 4
LOCATION_MIN_FONT_SIZE = 10
LOCATION_FALLBACK_WIDTH = 128

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
        # Filled sun so it reads as light as the language button text.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        radius = size * 0.16
        painter.drawEllipse(center, radius, radius)

        pen = QPen(color, size * 0.075)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for index in range(8):
            angle = index * math.pi / 4
            inner = size * 0.26
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


def _wrap_text_lines(text, font_metrics, max_width, max_lines):
    """Wrap text into at most max_lines, returning (lines, truncated)."""
    words = text.split()
    if not words:
        return [""], False

    lines = []
    current = ""

    for index, word in enumerate(words):
        has_more = index < len(words) - 1
        candidate = word if not current else f"{current} {word}"
        if font_metrics.horizontalAdvance(candidate) <= max_width:
            current = candidate
            continue

        if current:
            lines.append(current)
            current = ""
            if len(lines) >= max_lines:
                return lines, True

        # Place the word, breaking it when a single word is wider than the line.
        while font_metrics.horizontalAdvance(word) > max_width:
            cut = len(word)
            while (
                cut > 1
                and font_metrics.horizontalAdvance(word[:cut]) > max_width
            ):
                cut -= 1
            lines.append(word[:cut])
            word = word[cut:]
            if len(lines) >= max_lines:
                return lines, bool(word) or has_more

        if word:
            current = word

    if current:
        if len(lines) >= max_lines:
            return lines, True
        lines.append(current)

    return lines, False


def _elide_last_line(lines, font_metrics, max_width):
    """Add an ellipsis to the last line, removing words/chars as needed."""
    if not lines:
        return ["…"]
    last = lines[-1]
    while last and font_metrics.horizontalAdvance(last + "…") > max_width:
        if " " in last:
            last = last.rsplit(" ", 1)[0]
        else:
            last = last[:-1]
    return lines[:-1] + [last + "…"]


def _line_x(index, line, first_x, first_advance, metrics, width):
    """Right-align the first line and centre the following lines below it."""
    if index == 0:
        return first_x
    advance = metrics.horizontalAdvance(line)
    x = first_x + first_advance / 2 - advance / 2
    return max(0, min(x, width - advance))


class FitLabel(QLabel):
    """Label that shrinks its font and wraps to at most four lines.

    The first line is right-aligned. Every following line is centred below the
    first line. If even the smallest font needs more than four lines, the last
    visible line is shortened with an ellipsis.
    """

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._full_text = ""
        self._lines = [""]
        self._font = self.font()
        self._line_height = 0
        self._text_height = 0
        self._last_width = -1
        self._last_text = None
        self._last_font_key = None
        self.setWordWrap(True)
        self.setText(text)

    def setText(self, text):
        self._full_text = text
        super().setText(text)
        self.setToolTip(text)
        self._refit()

    def refresh(self):
        self._last_width = -1
        self._refit()

    def _base_font_size(self):
        size = self.font().pixelSize()
        if size <= 0:
            size = self.font().pointSize()
        if size <= 0:
            size = 13
        return size

    def _font_key(self):
        font = self.font()
        return (font.family(), int(font.weight()), self._base_font_size())

    def _compute_layout(self, width):
        base_font = QFont(self.font())
        base_size = self._base_font_size()
        min_size = min(LOCATION_MIN_FONT_SIZE, base_size)
        max_size = max(LOCATION_MIN_FONT_SIZE, base_size)

        if not self._full_text:
            font = QFont(base_font)
            font.setPixelSize(base_size)
            return font, [""], False

        for size in range(max_size, min_size - 1, -1):
            font = QFont(base_font)
            font.setPixelSize(size)
            metrics = QFontMetrics(font)
            lines, truncated = _wrap_text_lines(
                self._full_text, metrics, width, LOCATION_MAX_LINES
            )
            if truncated:
                continue
            # The more lines the text needs, the smaller the font should be:
            # 1 line -> max size, 2 -> -1 px, 3 -> -2 px, 4 -> -3 px.
            desired = max(
                min_size,
                max_size - (min(len(lines), LOCATION_MAX_LINES) - 1),
            )
            if size <= desired:
                return font, lines, False

        # Even the smallest font does not fit: keep four lines and elide.
        font = QFont(base_font)
        font.setPixelSize(min_size)
        metrics = QFontMetrics(font)
        lines, truncated = _wrap_text_lines(
            self._full_text, metrics, width, LOCATION_MAX_LINES
        )
        if truncated:
            lines = _elide_last_line(lines, metrics, width)
        return font, lines, True

    def _refit(self):
        width = self.width()
        if width <= 1:
            width = LOCATION_FALLBACK_WIDTH
        font_key = self._font_key()
        if (
            width == self._last_width
            and self._full_text == self._last_text
            and font_key == self._last_font_key
        ):
            return

        font, lines, _ = self._compute_layout(width)
        self._font = font
        self._lines = lines
        self._line_height = QFontMetrics(font).height()
        self._text_height = self._line_height * max(1, len(lines))
        self._last_width = width
        self._last_text = self._full_text
        self._last_font_key = font_key

        if self.minimumHeight() != self._text_height:
            self.setMinimumHeight(self._text_height)
        self.updateGeometry()
        self.update()

    def sizeHint(self):
        return QSize(
            max(self.width(), LOCATION_FALLBACK_WIDTH),
            max(self._text_height, self._line_height),
        )

    def minimumSizeHint(self):
        return QSize(0, max(self._text_height, self._line_height))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        if width <= 1:
            width = LOCATION_FALLBACK_WIDTH
        font, lines, _ = self._compute_layout(width)
        return QFontMetrics(font).height() * max(1, len(lines))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refit()

    def paintEvent(self, event):
        if self._full_text and not self._lines:
            self._refit()
        if not self._lines:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setFont(self._font)
        metrics = QFontMetrics(self._font)

        group = (
            QPalette.ColorGroup.Normal
            if self.isEnabled()
            else QPalette.ColorGroup.Disabled
        )
        painter.setPen(self.palette().color(group, QPalette.ColorRole.WindowText))

        line_height = metrics.height()
        total_height = line_height * len(self._lines)
        y = (self.height() - total_height) / 2

        first = self._lines[0]
        first_advance = metrics.horizontalAdvance(first)
        first_x = self.width() - first_advance

        for index, line in enumerate(self._lines):
            x = _line_x(
                index, line, first_x, first_advance, metrics, self.width()
            )
            baseline = y + metrics.ascent() + index * line_height
            painter.drawText(QPointF(x, baseline), line)

        painter.end()


class ThemedCheckBox(QCheckBox):
    """Checkbox with a thick, high-contrast mark in both themes."""

    CHECKED_COLOR = "#d9534f"
    DARK_CHECK_COLOR = "#0f1115"
    LIGHT_CHECK_COLOR = "#f4f5f7"
    DARK_BORDER = "#4a5160"
    LIGHT_BORDER = "#8b909a"

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._dark = True
        self.set_dark(True)

    def set_dark(self, dark):
        self._dark = bool(dark)
        palette = self.palette()
        palette.setColor(
            QPalette.ColorRole.WindowText,
            QColor("#c3c9d4") if self._dark else QColor("#5c626b"),
        )
        self.setPalette(palette)
        self.update()

    def paintEvent(self, event):
        opt = QStyleOptionButton()
        self.initStyleOption(opt)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        indicator_w = (
            self.style().pixelMetric(
                QStyle.PixelMetric.PM_IndicatorWidth, opt, self
            )
            or 16
        )
        indicator_h = (
            self.style().pixelMetric(
                QStyle.PixelMetric.PM_IndicatorHeight, opt, self
            )
            or 16
        )
        spacing = (
            self.style().pixelMetric(
                QStyle.PixelMetric.PM_CheckBoxLabelSpacing, opt, self
            )
            or 8
        )
        indicator = QRect(
            self.rect().left() + 4,
            self.rect().center().y() - indicator_h // 2,
            indicator_w,
            indicator_h,
        )

        radius = max(3.0, indicator.width() * 0.24)
        if self.isChecked():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self.CHECKED_COLOR))
            painter.drawRoundedRect(QRectF(indicator), radius, radius)

            check_color = QColor(
                self.DARK_CHECK_COLOR
                if self._dark
                else self.LIGHT_CHECK_COLOR
            )
            pen = QPen(check_color, max(2.4, indicator.width() * 0.19))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            x, y = indicator.x(), indicator.y()
            w, h = indicator.width(), indicator.height()
            start = QPointF(x + w * 0.22, y + h * 0.52)
            corner = QPointF(x + w * 0.40, y + h * 0.70)
            end = QPointF(x + w * 0.78, y + h * 0.30)
            painter.drawLine(start, corner)
            painter.drawLine(corner, end)
        else:
            border = QColor(
                self.DARK_BORDER if self._dark else self.LIGHT_BORDER
            )
            painter.setPen(QPen(border, 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(
                QRectF(indicator.adjusted(1, 1, -1, -1)), radius, radius
            )

        text_rect = QRect(
            indicator.right() + spacing,
            self.rect().top(),
            max(0, self.rect().right() - indicator.right() - spacing),
            self.rect().height(),
        )
        painter.setFont(self.font())
        group = (
            QPalette.ColorGroup.Normal
            if self.isEnabled()
            else QPalette.ColorGroup.Disabled
        )
        painter.setPen(self.palette().color(group, QPalette.ColorRole.WindowText))
        painter.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            self.text(),
        )

        if self.hasFocus():
            painter.setPen(QPen(QColor("#3b82f6"), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

        painter.end()


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
        self._lang = DEFAULT_LANGUAGE
        self._status_is_error = False
        self._status_key = "ready"
        self._status_params = {}
        self._last_speed = None
        self._tray_error = False
        self.tray = None
        self.tray_menu = None
        self.autostart_checkbox = None
        self.autostart_action = None
        self.measure_action = None
        self.quit_action = None
        self.theme_action = None
        self.theme_button = None
        self.language_button = None
        self.metrics_card = None
        self.details_card = None
        self.ping_value = None
        self.provider_value = None
        self.subtitle_label = None
        self.metric_name_labels = []
        self.metric_name_keys = []
        self.row_key_labels = []
        self.row_key_keys = []

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
        self._update_language_button()
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
            self.tr("theme_to_light")
            if self._dark
            else self.tr("theme_to_dark")
        )
        self.theme_button.setAccessibleName(self.theme_button.toolTip())

    # --- Language ---------------------------------------------------------

    def tr(self, key, **params):
        text = TRANSLATIONS.get(self._lang, TRANSLATIONS[DEFAULT_LANGUAGE]).get(
            key, key
        )
        if params:
            return text.format(**params)
        return text

    def _toggle_language(self):
        self.set_language("ru" if self._lang == "en" else "en")

    def _update_language_button(self):
        if self.language_button is None:
            return
        self.language_button.setText(self._lang.upper())
        # The tooltip is written in the language the interface will switch to.
        self.language_button.setToolTip(
            TRANSLATIONS["ru"]["language_to_russian"]
            if self._lang == "en"
            else TRANSLATIONS["en"]["language_to_english"]
        )
        self.language_button.setAccessibleName(
            self.language_button.toolTip()
        )

    def _update_measure_button(self):
        if self.button is None:
            return
        running = self._worker is not None and self._worker.isRunning()
        self.button.setText(
            self.tr("measuring") if running else self.tr("measure")
        )

    def set_language(self, lang):
        if lang not in TRANSLATIONS or lang == self._lang:
            return
        self._lang = lang
        self._retranslate_ui()
        self._update_language_button()
        self._update_theme_button()
        self._update_tray_tooltip()
        self._ensure_height()

    def _retranslate_ui(self):
        if self.subtitle_label is not None:
            self.subtitle_label.setText(self.tr("subtitle"))

        for label, key in zip(
            self.metric_name_labels, self.metric_name_keys
        ):
            label.setText(self.tr(key).upper())

        for label, key in zip(self.row_key_labels, self.row_key_keys):
            label.setText(self.tr(key))

        if self.autostart_checkbox is not None:
            self.autostart_checkbox.setText(self.tr("autostart"))
            self.autostart_checkbox.updateGeometry()

        if self._status_key:
            self._set_status(
                self.tr(self._status_key, **self._status_params),
                error=self._status_is_error,
            )

        self._update_measure_button()

        if self.measure_action is not None:
            self.measure_action.setText(self.tr("measure"))
        if self.theme_action is not None:
            self.theme_action.setText(self.tr("dark_theme"))
        if self.autostart_action is not None:
            self.autostart_action.setText(self.tr("autostart"))
        if self.quit_action is not None:
            self.quit_action.setText(self.tr("quit"))

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
        if self.autostart_checkbox is not None:
            self.autostart_checkbox.set_dark(self._dark)
        if self.location_value is not None:
            self.location_value.refresh()
        self._ensure_height()
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
        # Re-measure after the first real layout so wrapped text gets enough height.
        QTimer.singleShot(0, self._ensure_height)

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

        self.language_button = QPushButton()
        self.language_button.setObjectName("languageButton")
        self.language_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.language_button.setFlat(True)
        self.language_button.setFixedSize(32, 32)
        self.language_button.clicked.connect(self._toggle_language)
        header.addWidget(self.language_button)

        self.theme_button = QPushButton()
        self.theme_button.setObjectName("themeButton")
        self.theme_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_button.setFlat(True)
        self.theme_button.setFixedSize(32, 32)
        self.theme_button.setIconSize(QSize(20, 20))
        self.theme_button.clicked.connect(self._toggle_theme)
        header.addWidget(self.theme_button)
        root.addLayout(header)

        self.subtitle_label = QLabel(self.tr("subtitle"))
        self.subtitle_label.setObjectName("subtitle")
        root.addWidget(self.subtitle_label)
        root.addSpacing(4)

        # Speed card: download | upload
        metrics = self._card()
        self.metrics_card = metrics
        metrics_row = QHBoxLayout(metrics)
        metrics_row.setContentsMargins(20, 18, 20, 18)
        metrics_row.setSpacing(18)
        self.download_value = self._add_metric(metrics_row, "download")
        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFixedWidth(1)
        metrics_row.addWidget(divider)
        self.upload_value = self._add_metric(metrics_row, "upload")
        root.addWidget(metrics)

        # Details card: IP + location
        details = self._card()
        self.details_card = details
        grid = QGridLayout(details)
        grid.setContentsMargins(20, 14, 20, 14)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        self.ip_value = self._add_row(grid, 0, "ip")
        self.provider_value = self._add_row(
            grid, 1, "provider", fit=True
        )
        self.location_value = self._add_row(
            grid, 2, "location", fit=True
        )
        self.ping_value = self._add_row(grid, 3, "ping")
        grid.setColumnStretch(1, 1)
        root.addWidget(details)

        self.autostart_checkbox = ThemedCheckBox(self.tr("autostart"))
        self.autostart_checkbox.setObjectName("autostart")
        self.autostart_checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        self.autostart_checkbox.setChecked(self._autostart_on)
        self.autostart_checkbox.setVisible(autostart_supported())
        # Keep the clickable area exactly around the indicator and text.
        self.autostart_checkbox.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed
        )
        self.autostart_checkbox.toggled.connect(self._set_autostart)
        root.addWidget(self.autostart_checkbox)

        self.status = QLabel(self.tr("ready"))
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        self.button = QPushButton(self.tr("measure"))
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button.setDefault(True)
        self.button.clicked.connect(self.start_measurement)
        root.addWidget(self.button)

    def _add_metric(self, parent_layout, name_key):
        column = QVBoxLayout()
        column.setSpacing(2)
        name_label = QLabel(self.tr(name_key).upper())
        name_label.setObjectName("metricName")
        value = QLabel(EMPTY_VALUE)
        value.setObjectName("metricValue")
        unit = QLabel("Mbit/s")
        unit.setObjectName("metricUnit")
        column.addWidget(name_label)
        column.addWidget(value)
        column.addWidget(unit)
        parent_layout.addLayout(column, 1)
        self.metric_name_labels.append(name_label)
        self.metric_name_keys.append(name_key)
        return value

    def _add_row(self, grid, row, key, fit=False):
        key_label = QLabel(self.tr(key))
        key_label.setObjectName("rowKey")
        # Keep the key column from squeezing the value column on wide fonts.
        key_label.setMaximumWidth(110)
        value_label = FitLabel(EMPTY_VALUE) if fit else QLabel(EMPTY_VALUE)
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
        self.row_key_labels.append(key_label)
        self.row_key_keys.append(key)
        return value_label

    def _ensure_height(self):
        """Grow the window when wrapped content needs more vertical space."""
        for card in (self.metrics_card, self.details_card):
            if card is None:
                continue
            needed = card.sizeHint().height()
            if card.minimumHeight() != needed:
                card.setMinimumHeight(needed)
        required = self.sizeHint().height()
        if self.height() < required:
            self.resize(self.width(), required)

    # --- Tray -------------------------------------------------------------

    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        self.tray = QSystemTrayIcon(self.icon, self)
        self.tray.setToolTip(APP_NAME)

        self.tray_menu = QMenu()
        self.measure_action = self.tray_menu.addAction(self.tr("measure"))
        self.measure_action.triggered.connect(self._measure_from_tray)
        self.tray_menu.addSeparator()
        self.theme_action = self.tray_menu.addAction(self.tr("dark_theme"))
        self.theme_action.setCheckable(True)
        self.theme_action.setChecked(self._dark)
        self.theme_action.toggled.connect(self.set_theme)
        self.autostart_action = self.tray_menu.addAction(
            self.tr("autostart")
        )
        self.autostart_action.setCheckable(True)
        self.autostart_action.setChecked(self._autostart_on)
        self.autostart_action.setVisible(autostart_supported())
        self.autostart_action.toggled.connect(self._set_autostart)
        self.tray_menu.addSeparator()
        self.quit_action = self.tray_menu.addAction(self.tr("quit"))
        self.quit_action.triggered.connect(self.quit_app)

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

    def _update_tray_tooltip(self):
        if self.tray is None:
            return
        running = self._worker is not None and self._worker.isRunning()
        if running:
            self._set_tray_tooltip(self.tr("tray_measuring"))
        elif self._tray_error:
            self._set_tray_tooltip(self.tr("tray_error"))
        elif self._last_speed is not None:
            download, upload, ping = self._last_speed
            text = f"↓ {download:.2f} ↑ {upload:.2f} Mbit/s"
            if isinstance(ping, (int, float)):
                text += f" · {ping:.0f} ms"
            self._set_tray_tooltip(text)
        else:
            self.tray.setToolTip(APP_NAME)

    def closeEvent(self, event):
        if self._quitting or self.tray is None:
            event.accept()
            return
        event.ignore()
        self.hide()
        if not self._tray_message_shown:
            self.tray.showMessage(
                APP_NAME,
                self.tr("tray_message"),
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
                self._set_status_key(
                    "autostart_on" if enabled else "autostart_off"
                )
        else:
            self._autostart_on = is_autostart_enabled()
            self._sync_autostart_controls(self._autostart_on)
            self._set_status_key("autostart_error", error=True)

    def _sync_autostart_controls(self, enabled):
        for widget in (self.autostart_checkbox, self.autostart_action):
            if widget is None:
                continue
            widget.blockSignals(True)
            widget.setChecked(enabled)
            widget.blockSignals(False)

    # --- Measurement ------------------------------------------------------

    def _set_status_key(self, key, error=False, **params):
        self._status_key = key
        self._status_params = params
        self._set_status(self.tr(key, **params), error=error)

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
            self.provider_value,
            self.location_value,
            self.ping_value,
        ):
            label.setText(EMPTY_VALUE)

    def start_measurement(self):
        if self._worker is not None and self._worker.isRunning():
            return

        self.button.setEnabled(False)
        self.button.setText(self.tr("measuring"))
        self._set_status_key("measuring_status")
        self._last_speed = None
        self._tray_error = False
        self._set_tray_tooltip(self.tr("tray_measuring"))
        self._clear_values()

        self._worker = MeasurementWorker()
        self._worker.results_ready.connect(self.show_results)
        self._worker.start()

    def show_results(self, results):
        speed = results.get("speed")
        ping = results.get("ping")
        if isinstance(speed, tuple) and len(speed) == 2:
            download_speed, upload_speed = speed
            self.download_value.setText(f"{download_speed:.2f}")
            self.upload_value.setText(f"{upload_speed:.2f}")
            self._set_status_key("complete")
            self._last_speed = (download_speed, upload_speed, ping)
            self._tray_error = False
            self._update_tray_tooltip()
        else:
            self._clear_values()
            self._set_status_key("speed_error", speed=speed, error=True)
            self._last_speed = None
            self._tray_error = True
            self._update_tray_tooltip()

        self.ip_value.setText(str(results.get("ip") or EMPTY_VALUE))
        self.provider_value.setText(
            str(results.get("provider") or EMPTY_VALUE)
        )
        self.location_value.setText(
            str(results.get("location") or EMPTY_VALUE)
        )

        if isinstance(ping, (int, float)):
            self.ping_value.setText(f"{ping:.0f} ms")
        else:
            self.ping_value.setText(str(ping) if ping else EMPTY_VALUE)

        self.button.setEnabled(True)
        self.button.setText(self.tr("measure"))
        self._ensure_height()

    def quit_app(self):
        if self._quitting:
            return
        self._quitting = True
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.cancel()
            self._set_status_key("finishing")
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

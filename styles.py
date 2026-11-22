"""Application style sheets and shared style tokens."""

# Error text needs a different shade in each theme to stay readable.
ERROR_COLOR = "#ff6b6b"
ERROR_TEXT_STYLE = f"color: {ERROR_COLOR};"
ERROR_COLOR_LIGHT = "#d9534f"
ERROR_TEXT_STYLE_LIGHT = f"color: {ERROR_COLOR_LIGHT};"

LIGHT_STYLESHEET = """
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
    color: #7a7f87;
}
QMenu {
    background: #ffffff;
    color: #16181d;
    border: 1px solid #e3e6ea;
}
QMenu::item:selected {
    background: #edeff2;
}
QMenu::separator {
    height: 1px;
    background: #edeff2;
    margin: 4px 8px;
}
#themeButton {
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 0;
}
#themeButton:hover {
    background: #edeff2;
}
#themeButton:pressed {
    background: #e3e6ea;
}
"""

DARK_STYLESHEET = """
#root {
    background: #0f1115;
}
QLabel {
    font-family: "Segoe UI", "Inter", sans-serif;
}
#title {
    font-size: 22px;
    font-weight: 600;
    color: #f5f7fa;
}
#subtitle {
    font-size: 12px;
    color: #9aa3b2;
}
#card {
    background: #1a1d24;
    border-radius: 14px;
}
#metricName {
    font-size: 11px;
    font-weight: 600;
    color: #9aa3b2;
}
#metricValue {
    font-size: 30px;
    font-weight: 600;
    color: #f5f7fa;
}
#metricUnit {
    font-size: 11px;
    color: #9aa3b2;
}
#divider {
    background: #2a2f3a;
}
#rowKey {
    font-size: 13px;
    color: #9aa3b2;
}
#rowValue {
    font-size: 13px;
    font-weight: 600;
    color: #f5f7fa;
}
#autostart {
    font-size: 12px;
    color: #c3c9d4;
    spacing: 8px;
}
#status {
    font-size: 12px;
    color: #9aa3b2;
}
QPushButton {
    background: #3b82f6;
    color: #ffffff;
    border: none;
    border-radius: 10px;
    padding: 12px 16px;
    font-size: 14px;
    font-weight: 600;
}
QPushButton:hover {
    background: #4c8dff;
}
QPushButton:pressed {
    background: #2f6fd0;
}
QPushButton:disabled {
    background: #2a2f3a;
    color: #6b7280;
}
QMenu {
    background: #1a1d24;
    color: #f5f7fa;
    border: 1px solid #2a2f3a;
}
QMenu::item:selected {
    background: #2a2f3a;
}
QMenu::separator {
    height: 1px;
    background: #2a2f3a;
    margin: 4px 8px;
}
#themeButton {
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 0;
}
#themeButton:hover {
    background: #2a2f3a;
}
#themeButton:pressed {
    background: #343a46;
}
"""

LIGHT_MENU_STYLESHEET = """
QMenu {
    background: #ffffff;
    color: #16181d;
    border: 1px solid #e3e6ea;
}
QMenu::item:selected {
    background: #edeff2;
    color: #16181d;
}
QMenu::separator {
    height: 1px;
    background: #edeff2;
    margin: 4px 8px;
}
"""

DARK_MENU_STYLESHEET = """
QMenu {
    background: #1a1d24;
    color: #f5f7fa;
    border: 1px solid #2a2f3a;
}
QMenu::item:selected {
    background: #2a2f3a;
    color: #f5f7fa;
}
QMenu::separator {
    height: 1px;
    background: #2a2f3a;
    margin: 4px 8px;
}
"""

# Kept for callers that imported the old name.
STYLESHEET = DARK_STYLESHEET
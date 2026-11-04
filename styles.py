"""Application style sheet and shared style tokens."""

ERROR_COLOR = "#d9534f"
ERROR_TEXT_STYLE = f"color: {ERROR_COLOR};"

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

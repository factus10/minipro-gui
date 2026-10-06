"""Application stylesheet, with light and dark variants."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

LIGHT = dict(
    window="#f4f5f7", card="#ffffff", inset="#f7f9fc", border="#dde1e7", text="#1d2330",
    muted="#5d6675", accent="#2563eb", accent_hover="#1d4ed8", accent_text="#ffffff",
    ok_bg="#dcfce7", ok_fg="#166534", warn_bg="#fef3c7", warn_fg="#92400e",
    err_bg="#fee2e2", err_fg="#991b1b", busy_bg="#dbeafe", busy_fg="#1e40af",
    idle_bg="#eceff3", idle_fg="#4b5563", code_bg="#f1f3f6",
)
DARK = dict(
    window="#1b1d22", card="#24272e", inset="#2b2f37", border="#3a3f4a", text="#e6e8ec",
    muted="#9aa3b2", accent="#3b82f6", accent_hover="#60a5fa", accent_text="#ffffff",
    ok_bg="#14532d", ok_fg="#bbf7d0", warn_bg="#78350f", warn_fg="#fde68a",
    err_bg="#7f1d1d", err_fg="#fecaca", busy_bg="#1e3a8a", busy_fg="#bfdbfe",
    idle_bg="#30343d", idle_fg="#c4c9d2", code_bg="#2b2f37",
)

TEMPLATE = """
QMainWindow, QDialog {{ background: {window}; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; }}
QFrame[role="card"] {{
    background: {card}; border: 1px solid {border}; border-radius: 10px;
}}
QFrame[role="inset"] {{
    background: {inset}; border: 1px solid {border}; border-radius: 8px;
}}
QLabel[role="help"] {{ color: {muted}; }}
QLabel[role="heading"] {{ font-size: 16px; font-weight: 600; color: {text}; }}
QLabel[role="subheading"] {{ font-weight: 600; color: {text}; margin-top: 6px; }}
QLabel[role="title"] {{ font-size: 18px; font-weight: 600; color: {text}; }}
QLabel[role="step"] {{
    background: {accent}; color: {accent_text}; border-radius: 13px; font-weight: 700;
}}
QLabel[role="code"] {{
    background: {code_bg}; border: 1px solid {border}; border-radius: 6px; padding: 6px 8px;
}}
QLabel[role="result"] {{
    background: {inset}; border: 1px solid {border}; border-radius: 6px; padding: 8px;
    color: {text};
}}
QLabel[state="ok"] {{ color: {ok_fg}; }}
QLabel[state="warn"] {{ color: {warn_fg}; }}
QLabel[state="error"] {{ color: {err_fg}; }}
QLabel[role="badge"] {{
    border-radius: 10px; padding: 3px 10px; font-weight: 600;
    background: {idle_bg}; color: {idle_fg};
}}
QLabel[role="badge"][state="ok"] {{ background: {ok_bg}; color: {ok_fg}; }}
QLabel[role="badge"][state="error"] {{ background: {err_bg}; color: {err_fg}; }}
QLabel[role="badge"][state="warn"] {{ background: {warn_bg}; color: {warn_fg}; }}
QLabel[role="badge"][state="busy"] {{ background: {busy_bg}; color: {busy_fg}; }}
QPushButton[role="primary"], QPushButton[role="big"] {{
    background: {accent}; color: {accent_text}; border: none; border-radius: 6px;
    padding: 6px 14px; font-weight: 600;
}}
QPushButton[role="big"] {{ font-size: 16px; padding: 12px 20px; }}
QPushButton[role="primary"]:hover, QPushButton[role="big"]:hover {{ background: {accent_hover}; }}
QPushButton[role="primary"]:disabled, QPushButton[role="big"]:disabled {{
    background: {idle_bg}; color: {muted};
}}
QToolButton[role="disclosure"] {{ border: none; font-weight: 600; color: {text}; }}
QListWidget::item {{ padding: 5px 4px; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ padding: 8px 18px; }}
"""


def stylesheet() -> str:
    dark = QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    return TEMPLATE.format(**(DARK if dark else LIGHT))

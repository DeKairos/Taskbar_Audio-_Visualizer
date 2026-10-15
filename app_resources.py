"""
Shared resource helpers for icon and bundled file resolution.
"""
import os
import sys
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt6.QtCore import Qt


def get_resource_path(relative_path: str) -> str:
    """Resolve a resource path for both source and PyInstaller runs."""
    base_dir = os.path.dirname(os.path.abspath(__file__))

    # PyInstaller onefile extracts files under _MEIPASS.
    meipass_dir = getattr(sys, "_MEIPASS", "")
    if meipass_dir:
        candidate = os.path.join(meipass_dir, relative_path)
        if os.path.exists(candidate):
            return candidate

    candidate = os.path.join(base_dir, relative_path)
    if os.path.exists(candidate):
        return candidate

    # PyInstaller onedir typically places assets next to the executable.
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        candidate = os.path.join(exe_dir, relative_path)
        if os.path.exists(candidate):
            return candidate

    return os.path.join(base_dir, relative_path)


def get_app_icon() -> QIcon:
    """Return app icon.

    Use an explicitly bundled ICO, with a generated fallback if it cannot render.
    """
    icon = QIcon(get_resource_path(os.path.join("assets", "app_icon.ico")))
    if not icon.pixmap(16, 16).isNull():
        return icon

    # QIcon(executable) is not a reliable Windows executable-icon extractor.
    # Keep a visible, high-contrast icon even if an asset is missing or corrupt.
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(10, 36, 52))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(0, 0, 32, 32)
    painter.setBrush(QColor(92, 228, 255))
    for x, height in ((6, 10), (12, 20), (18, 15), (24, 23)):
        painter.drawRoundedRect(x, 28 - height, 3, height, 1, 1)
    painter.end()
    return QIcon(pixmap)

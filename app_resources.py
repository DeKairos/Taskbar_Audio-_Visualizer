"""
Shared resource helpers for icon and bundled file resolution.
"""
import os
import sys
from PyQt6.QtGui import QIcon


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

    Frozen builds prefer the executable icon so installer upgrades cannot be
    masked by a stale copied assets/app_icon.ico file.
    """
    if getattr(sys, "frozen", False):
        exe_icon = QIcon(sys.executable)
        if not exe_icon.isNull():
            return exe_icon

    icon = QIcon(get_resource_path(os.path.join("assets", "app_icon.ico")))
    if not icon.isNull():
        return icon

    return QIcon()
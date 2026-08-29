"""
ui/theme_editor.py — Custom theme creator for the Audio Visualizer.

Allows users to create, save, and manage custom color themes.
Provides a visual color picker with live preview.
"""
import json
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QColorDialog, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QFrame, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QBrush, QPen, QPainterPath, QFont
from ui.fluent_theme import (
    RADIUS_CARD, RADIUS_MEDIUM, SPACE_SM, SPACE_MD, FONT_FAMILY,
    lerp_color, rgb_to_hex, hex_to_rgb,
)


THEMES_DIR = os.path.join(os.path.expanduser("~"), ".audio_visualizer_themes")


def _ensure_themes_dir():
    os.makedirs(THEMES_DIR, exist_ok=True)


def load_custom_themes():
    """Load all saved custom themes."""
    _ensure_themes_dir()
    themes = {}
    for fname in os.listdir(THEMES_DIR):
        if fname.endswith(".json"):
            try:
                with open(os.path.join(THEMES_DIR, fname), "r") as f:
                    data = json.load(f)
                name = data.get("name", fname[:-5])
                themes[name] = data
            except Exception:
                pass
    return themes


def save_custom_theme(name: str, theme_data: dict):
    """Save a custom theme to disk."""
    _ensure_themes_dir()
    safe_name = "".join(c for c in name if c.isalnum() or c in " _-").strip()
    if not safe_name:
        safe_name = "custom_theme"
    theme_data["name"] = name
    filepath = os.path.join(THEMES_DIR, f"{safe_name}.json")
    with open(filepath, "w") as f:
        json.dump(theme_data, f, indent=2)


def delete_custom_theme(name: str):
    """Delete a custom theme file."""
    _ensure_themes_dir()
    safe_name = "".join(c for c in name if c.isalnum() or c in " _-").strip()
    filepath = os.path.join(THEMES_DIR, f"{safe_name}.json")
    if os.path.exists(filepath):
        os.remove(filepath)


# ─── Color Swatch Button ───────────────────────────────────────────

class _ColorSwatch(QPushButton):
    clicked_color = pyqtSignal(str, tuple)

    def __init__(self, label: str, color: tuple, key: str, parent=None):
        super().__init__(parent)
        self._key = key
        self._color = color
        self.setFixedSize(80, 44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_style()
        self.clicked.connect(self._pick)

    def _update_style(self):
        r, g, b = self._color
        self.setStyleSheet(f"""
            QPushButton {{
                background: rgb({r},{g},{b});
                border: 1px solid rgba(255,255,255,40);
                border-radius: 8px;
                color: white;
                font-family: {FONT_FAMILY}, Segoe UI;
                font-size: 11px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                border: 1px solid rgba(255,255,255,80);
            }}
        """)
        self.setText(self._key.capitalize())

    def _pick(self):
        color = QColorDialog.getColor(
            QColor(*self._color), self, f"Pick {self._key} color"
        )
        if color.isValid():
            self._color = (color.red(), color.green(), color.blue())
            self._update_style()
            self.clicked_color.emit(self._key, self._color)

    @property
    def color(self):
        return self._color


# ─── Preview Widget ────────────────────────────────────────────────

class _ThemePreview(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(280, 60)
        self._base = (20, 180, 230)
        self._peak = (150, 250, 255)
        self._glow = (80, 200, 240)
        self._bg = (180, 220, 255)

    def set_colors(self, base, peak, glow, bg):
        self._base = base
        self._peak = peak
        self._glow = glow
        self._bg = bg
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()

        # Background
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(20, 20, 22)))
        p.drawRoundedRect(0, 0, w, h, RADIUS_CARD, RADIUS_CARD)

        # Draw simulated bars
        import math
        num_bars = 24
        gap = 2
        bar_w = max(2, (w - gap * (num_bars + 1)) / num_bars)
        for i in range(num_bars):
            t = i / max(1, num_bars - 1)
            norm = 0.3 + 0.7 * abs(math.sin(t * math.pi * 1.5))
            bar_h = norm * (h - 10)
            x = gap + i * (bar_w + gap)
            y = h - bar_h - 4

            # Glow
            r, g, b = self._glow
            p.setBrush(QBrush(QColor(r, g, b, int(40 * norm))))
            glow_r = bar_w * 2
            p.drawEllipse(int(x + bar_w / 2), int(y + bar_h / 2), int(glow_r), int(glow_r))

            # Bar with gradient
            r1, g1, b1 = self._base
            r2, g2, b2 = self._peak
            r = int(r1 + t * (r2 - r1))
            g = int(g1 + t * (g2 - g1))
            b = int(b1 + t * (b2 - b1))
            p.setBrush(QBrush(QColor(r, g, b, 200)))
            p.drawRoundedRect(int(x), int(y), int(bar_w), int(bar_h), 2, 2)

        p.end()


# ─── Theme Editor Widget ───────────────────────────────────────────

class ThemeEditor(QWidget):
    theme_saved = pyqtSignal(str, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._base = (20, 180, 230)
        self._peak = (150, 250, 255)
        self._glow = (80, 200, 240)
        self._bg = (180, 220, 255)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_MD)

        # Preview
        self._preview = _ThemePreview()
        layout.addWidget(self._preview)

        # Color pickers row
        colors_row = QHBoxLayout()
        colors_row.setSpacing(SPACE_SM)

        self._swatches = {}
        for key, color in [("base", self._base), ("peak", self._peak),
                           ("glow", self._glow), ("bg", self._bg)]:
            swatch = _ColorSwatch(key, color, key)
            swatch.clicked_color.connect(self._on_color_changed)
            self._swatches[key] = swatch
            colors_row.addWidget(swatch)

        colors_row.addStretch()
        layout.addLayout(colors_row)

        # Theme name + save
        save_row = QHBoxLayout()
        save_row.setSpacing(SPACE_SM)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Theme name...")
        self._name_edit.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(255,255,255,10);
                border: 1px solid rgba(255,255,255,16);
                border-radius: 6px;
                padding: 6px 10px;
                color: white;
                font-family: {FONT_FAMILY}, Segoe UI;
                font-size: 12px;
            }}
        """)
        save_row.addWidget(self._name_edit)

        save_btn = QPushButton("Save Theme")
        save_btn.setFixedHeight(32)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(100,180,255,60);
                border: 1px solid rgba(100,180,255,40);
                border-radius: 6px;
                color: white;
                font-family: {FONT_FAMILY}, Segoe UI;
                font-size: 12px;
                padding: 0 16px;
            }}
            QPushButton:hover {{
                background: rgba(100,180,255,90);
            }}
        """)
        save_btn.clicked.connect(self._save_theme)
        save_row.addWidget(save_btn)

        layout.addLayout(save_row)

        # Saved themes list
        self._theme_list = QListWidget()
        self._theme_list.setStyleSheet(f"""
            QListWidget {{
                background: rgba(255,255,255,5);
                border: 1px solid rgba(255,255,255,10);
                border-radius: 8px;
                color: white;
                font-family: {FONT_FAMILY}, Segoe UI;
                font-size: 12px;
            }}
            QListWidget::item {{
                padding: 6px 10px;
            }}
            QListWidget::item:selected {{
                background: rgba(100,180,255,30);
            }}
        """)
        self._load_saved_themes()
        layout.addWidget(self._theme_list)

        delete_btn = QPushButton("Delete Selected")
        delete_btn.setFixedHeight(28)
        delete_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(255,80,80,30);
                border: 1px solid rgba(255,80,80,30);
                border-radius: 6px;
                color: rgba(255,120,120,200);
                font-family: {FONT_FAMILY}, Segoe UI;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background: rgba(255,80,80,50);
            }}
        """)
        delete_btn.clicked.connect(self._delete_theme)
        layout.addWidget(delete_btn)

    def _on_color_changed(self, key: str, color: tuple):
        setattr(self, f"_{key}", color)
        self._preview.set_colors(self._base, self._peak, self._glow, self._bg)

    def _save_theme(self):
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Save Theme", "Please enter a theme name.")
            return

        theme_data = {
            "base": list(self._base),
            "peak": list(self._peak),
            "glow": list(self._glow),
            "bg": list(self._bg),
            "rainbow": False,
        }

        try:
            save_custom_theme(name, theme_data)
            self._load_saved_themes()
            self._name_edit.clear()
            self.theme_saved.emit(name, theme_data)
            QMessageBox.information(self, "Theme Saved", f"Theme '{name}' saved successfully.")
        except Exception as e:
            QMessageBox.warning(self, "Save Failed", str(e))

    def _load_saved_themes(self):
        self._theme_list.clear()
        try:
            themes = load_custom_themes()
            for name in sorted(themes.keys()):
                item = QListWidgetItem(f"\u2728 {name}")
                item.setData(Qt.ItemDataRole.UserRole, name)
                self._theme_list.addItem(item)
        except Exception:
            pass

    def _delete_theme(self):
        item = self._theme_list.currentItem()
        if not item:
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        reply = QMessageBox.question(
            self, "Delete Theme", f"Delete theme '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            delete_custom_theme(name)
            self._load_saved_themes()

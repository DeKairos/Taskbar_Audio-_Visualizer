"""
ui/volume_flyout.py — Fluent 2-style volume popup.

Appears when scrolling over the visualizer area.
Shows volume percentage with a compact card.
"""
from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QTimer, QRectF, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QPainterPath, QFont, QLinearGradient
from ui.fluent_theme import RADIUS_CARD, RADIUS_MEDIUM, FONT_FAMILY, accent_color


class VolumeFlyout(QWidget):
    """Compact Fluent 2 card showing volume percentage."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self._volume_pct = 50
        self._alpha = 0.0

        self.setFixedSize(60, 90)

        # Animation
        self._anim = QPropertyAnimation(self, b"vol_alpha")
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Auto-hide
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide_animated)

    # ── Alpha property ─────────────────────────────────────────────
    def get_alpha(self):
        return self._alpha

    def set_alpha(self, val):
        self._alpha = max(0.0, min(1.0, val))
        self.setWindowOpacity(self._alpha)
        self.update()

    vol_alpha = pyqtProperty(float, fget=get_alpha, fset=set_alpha)

    # ── Public API ─────────────────────────────────────────────────
    def show_volume(self, volume_pct: int, duration: float = 1.5):
        """Show the volume flyout with the given percentage."""
        self._volume_pct = max(0, min(100, volume_pct))

        # Position near bottom-right of primary screen
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.x() + geo.width() - self.width() - 40
            y = geo.y() + geo.height() - self.height() - 80
            self.move(x, y)

        self.show()
        self.raise_()
        self._animate_in()
        self._hide_timer.start(int(duration * 1000))

    def hide_animated(self):
        self._animate_out()

    # ── Animations ─────────────────────────────────────────────────
    def _animate_in(self):
        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def _animate_out(self):
        self._anim.stop()
        self._anim.setStartValue(self._alpha)
        self._anim.setEndValue(0.0)
        try:
            self._anim.finished.disconnect(self._on_fade_out)
        except Exception:
            pass
        self._anim.finished.connect(self._on_fade_out)
        self._anim.start()

    def _on_fade_out(self):
        try:
            self._anim.finished.disconnect(self._on_fade_out)
        except Exception:
            pass
        if self._alpha < 0.05:
            self.hide()

    # ── Painting ───────────────────────────────────────────────────
    def paintEvent(self, event):
        w = self.width()
        h = self.height()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        alpha = self._alpha

        # Card
        path = QPainterPath()
        path.addRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), RADIUS_CARD, RADIUS_CARD)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(28, 28, 30, int(230 * alpha))))
        p.drawPath(path)
        p.setPen(QPen(QColor(255, 255, 255, int(16 * alpha)), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

        # Volume bar background
        bar_x = w // 2 - 4
        bar_top = 14
        bar_bottom = h - 32
        bar_h = bar_bottom - bar_top
        bar_w = 8
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(255, 255, 255, int(25 * alpha))))
        p.drawRoundedRect(bar_x, bar_top, bar_w, bar_h, 4, 4)

        # Volume bar fill
        fill_h = int(bar_h * self._volume_pct / 100)
        fill_y = bar_bottom - fill_h
        acc = accent_color()
        grad = QLinearGradient(bar_x, fill_y, bar_x, bar_bottom)
        grad.setColorAt(0.0, QColor(acc.red(), acc.green(), acc.blue(), int(220 * alpha)))
        grad.setColorAt(1.0, QColor(acc.red() // 2, acc.green() // 2, acc.blue() // 2, int(200 * alpha)))
        p.setBrush(QBrush(grad))
        p.drawRoundedRect(bar_x, fill_y, bar_w, fill_h, 4, 4)

        # Percentage text
        pct_font = QFont(FONT_FAMILY, 13, QFont.Weight.Bold)
        p.setFont(pct_font)
        p.setPen(QPen(QColor(255, 255, 255, int(230 * alpha))))
        p.drawText(0, h - 26, w, 22, Qt.AlignmentFlag.AlignCenter, f"{self._volume_pct}%")

        # Speaker icon (simplified)
        icon_font = QFont("Segoe UI Symbol", 14)
        p.setFont(icon_font)
        p.setPen(QPen(QColor(255, 255, 255, int(180 * alpha))))
        p.drawText(0, 2, w, 14, Qt.AlignmentFlag.AlignCenter, "\U0001F50A" if self._volume_pct > 0 else "\U0001F507")

        p.end()

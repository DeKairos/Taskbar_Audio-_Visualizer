"""
ui/taskbar_widget.py — Compact media widget for the taskbar.

Shows album art thumbnail, truncated title, and elapsed time.
Can be positioned alongside or instead of the visualizer bars.
Click opens the full media flyout.
"""
import time
from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import (
    QPainter, QColor, QBrush, QPen, QPainterPath,
    QLinearGradient, QFont, QPixmap, QRadialGradient,
)
from ui.fluent_theme import RADIUS_CARD, RADIUS_MEDIUM, FONT_FAMILY, accent_color


class TaskbarMediaWidget(QWidget):
    """Always-visible compact widget showing current track info on the taskbar."""

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.cfg = config
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.BypassWindowManagerHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self._title = ""
        self._artist = ""
        self._playing = False
        self._cover_pixmap: QPixmap | None = None
        self._elapsed = 0.0
        self._total = 0.0
        self._last_update = 0.0

        self.setFixedSize(200, 40)

        # Update timer for elapsed time
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(500)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start()

    def update_media(self, title: str, artist: str = "",
                     cover_bytes: bytes = None, playing: bool = False,
                     elapsed: float = 0.0, total: float = 0.0):
        """Update the widget with current media info."""
        self._title = title
        self._artist = artist
        self._playing = playing
        self._elapsed = elapsed
        self._total = total
        self._last_update = time.time()

        if cover_bytes:
            pix = QPixmap()
            if pix.loadFromData(cover_bytes):
                self._cover_pixmap = pix
            else:
                self._cover_pixmap = None

        self.update()

    def position_widget(self, vis_x: int, vis_y: int, vis_w: int, vis_h: int,
                        position: str = "left"):
        """Position relative to the visualizer window area."""
        if position == "left":
            x = vis_x - self.width() - 4
            y = vis_y + (vis_h - self.height()) // 2
        elif position == "right":
            x = vis_x + vis_w + 4
            y = vis_y + (vis_h - self.height()) // 2
        else:  # center or above
            x = vis_x + (vis_w - self.width()) // 2
            y = vis_y - self.height() - 2
        self.move(max(0, x), max(0, y))

    def _tick(self):
        if self._playing and self._elapsed < self._total:
            self._elapsed += 0.5
            self.update()

    def _format_time(self, seconds: float) -> str:
        m = int(seconds) // 60
        s = int(seconds) % 60
        return f"{m}:{s:02d}"

    def paintEvent(self, event):
        if not self._title:
            return

        w = self.width()
        h = self.height()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Card background
        path = QPainterPath()
        path.addRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), RADIUS_CARD, RADIUS_CARD)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(28, 28, 30, 230)))
        p.drawPath(path)
        p.setPen(QPen(QColor(255, 255, 255, 14), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

        # Album art thumbnail
        thumb_size = h - 8
        thumb_x = 4
        thumb_y = 4

        if self._cover_pixmap and not self._cover_pixmap.isNull():
            clip = QPainterPath()
            clip.addRoundedRect(QRectF(thumb_x, thumb_y, thumb_size, thumb_size), 4, 4)
            p.save()
            p.setClipPath(clip)
            scaled = self._cover_pixmap.scaled(
                thumb_size, thumb_size,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            sx = max(0, (scaled.width() - thumb_size) // 2)
            sy = max(0, (scaled.height() - thumb_size) // 2)
            p.drawPixmap(thumb_x, thumb_y, scaled, sx, sy, thumb_size, thumb_size)
            p.restore()
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(50, 50, 50, 200)))
            p.drawRoundedRect(QRectF(thumb_x, thumb_y, thumb_size, thumb_size), 4, 4)
            icon_font = QFont("Segoe UI Symbol", 10)
            p.setFont(icon_font)
            p.setPen(QPen(QColor(255, 255, 255, 100)))
            p.drawText(thumb_x, thumb_y, thumb_size, thumb_size, Qt.AlignmentFlag.AlignCenter, "\u266B")

        # Text area
        text_x = thumb_x + thumb_size + 6
        text_w = w - text_x - 6

        # Title
        title_font = QFont(FONT_FAMILY, 10, QFont.Weight.DemiBold)
        p.setFont(title_font)
        p.setPen(QPen(QColor(255, 255, 255, 220)))
        fm = p.fontMetrics()
        elided = fm.elidedText(self._title, Qt.TextElideMode.ElideRight, text_w)
        p.drawText(text_x, 6, text_w, 16, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided)

        # Artist
        if self._artist:
            artist_font = QFont(FONT_FAMILY, 9)
            p.setFont(artist_font)
            p.setPen(QPen(QColor(255, 255, 255, 130)))
            fm = p.fontMetrics()
            elided_a = fm.elidedText(self._artist, Qt.TextElideMode.ElideRight, text_w)
            p.drawText(text_x, 20, text_w, 14, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided_a)

        # Time
        if self._total > 0:
            time_font = QFont(FONT_FAMILY, 8)
            p.setFont(time_font)
            p.setPen(QPen(QColor(255, 255, 255, 100)))
            time_str = f"{self._format_time(self._elapsed)} / {self._format_time(self._total)}"
            p.drawText(text_x, 32, text_w, 10, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, time_str)

        # Playing indicator
        if self._playing:
            acc = accent_color()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(acc.red(), acc.green(), acc.blue(), 200)))
            p.drawEllipse(int(w - 10), int(h - 10), 6, 6)

        p.end()

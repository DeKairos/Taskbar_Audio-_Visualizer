"""
ui/media_flyout.py — Fluent 2-style media now-playing flyout.

A popup card showing album art, title, artist, album, and transport controls.
Appears on track change or when triggered manually.
Uses Acrylic-style backdrop and smooth slide/fade animations.
"""
import time
from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QTimer, QRectF, QRect, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt6.QtGui import (
    QPainter, QColor, QBrush, QPen, QPainterPath,
    QLinearGradient, QFont, QPixmap, QRadialGradient,
)
from ui.fluent_theme import (
    RADIUS_CARD, RADIUS_MEDIUM, SPACE_SM, SPACE_MD, SPACE_LG,
    FONT_FAMILY, card_bg, card_border, text_primary, text_secondary,
    accent_color, qcolor_with_alpha,
)


class MediaFlyout(QWidget):
    """A Fluent 2-style popup card showing now-playing info."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self._title = ""
        self._artist = ""
        self._album = ""
        self._cover_pixmap: QPixmap | None = None
        self._cover_bytes: bytes | None = None
        self._alpha = 0.0
        self._playing = False

        # Animation
        self._anim = QPropertyAnimation(self, b"flyout_alpha")
        self._anim.setDuration(300)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Auto-hide timer
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide_animated)

        self.setFixedSize(340, 100)

    # ── Alpha property for animation ───────────────────────────────
    def get_alpha(self):
        return self._alpha

    def set_alpha(self, val):
        self._alpha = max(0.0, min(1.0, val))
        self.setWindowOpacity(self._alpha)
        self.update()

    flyout_alpha = pyqtProperty(float, fget=get_alpha, fset=set_alpha)

    # ── Public API ─────────────────────────────────────────────────
    def show_info(self, title: str, artist: str = "", album: str = "",
                  cover_bytes: bytes = None, playing: bool = False,
                  duration: float = 4.0):
        """Show the flyout with the given media info."""
        self._title = title
        self._artist = artist
        self._album = album
        self._playing = playing

        if cover_bytes and cover_bytes != self._cover_bytes:
            self._cover_bytes = cover_bytes
            pix = QPixmap()
            if pix.loadFromData(cover_bytes):
                self._cover_pixmap = pix
            else:
                self._cover_pixmap = None
        elif not cover_bytes:
            self._cover_pixmap = None
            self._cover_bytes = None

        # Position: centered on primary screen, near bottom
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.x() + (geo.width() - self.width()) // 2
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
        self._anim.finished.connect(self._on_fade_out_done)
        self._anim.start()

    def _on_fade_out_done(self):
        try:
            self._anim.finished.disconnect(self._on_fade_out_done)
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

        # ── Card background ────────────────────────────────────────
        path = QPainterPath()
        path.addRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), RADIUS_CARD, RADIUS_CARD)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(28, 28, 30, int(235 * alpha))))
        p.drawPath(path)

        # Frosted border
        p.setPen(QPen(QColor(255, 255, 255, int(18 * alpha)), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

        # ── Album Art ──────────────────────────────────────────────
        cover_size = h - 16
        cover_x = SPACE_MD
        cover_y = 8

        if self._cover_pixmap and not self._cover_pixmap.isNull():
            clip = QPainterPath()
            clip.addRoundedRect(QRectF(cover_x, cover_y, cover_size, cover_size), RADIUS_MEDIUM, RADIUS_MEDIUM)
            p.save()
            p.setClipPath(clip)
            scaled = self._cover_pixmap.scaled(
                cover_size, cover_size,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            src_x = max(0, (scaled.width() - cover_size) // 2)
            src_y = max(0, (scaled.height() - cover_size) // 2)
            p.drawPixmap(cover_x, cover_y, scaled, src_x, src_y, cover_size, cover_size)
            p.restore()
            p.setPen(QPen(QColor(255, 255, 255, int(30 * alpha)), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(cover_x, cover_y, cover_size, cover_size), RADIUS_MEDIUM, RADIUS_MEDIUM)
        else:
            # Placeholder
            grad = QLinearGradient(cover_x, cover_y, cover_x + cover_size, cover_y + cover_size)
            grad.setColorAt(0.0, QColor(60, 60, 60, int(200 * alpha)))
            grad.setColorAt(1.0, QColor(30, 30, 30, int(200 * alpha)))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(grad))
            p.drawRoundedRect(QRectF(cover_x, cover_y, cover_size, cover_size), RADIUS_MEDIUM, RADIUS_MEDIUM)
            # Music note
            icon_font = QFont("Segoe UI Symbol", max(10, int(cover_size * 0.35)))
            p.setFont(icon_font)
            p.setPen(QPen(QColor(255, 255, 255, int(120 * alpha))))
            p.drawText(cover_x, cover_y, cover_size, cover_size, Qt.AlignmentFlag.AlignCenter, "\u266B")

        # ── Text ───────────────────────────────────────────────────
        text_x = cover_x + cover_size + SPACE_MD
        text_w = w - text_x - SPACE_MD

        # Title
        title_font = QFont(FONT_FAMILY, 13, QFont.Weight.DemiBold)
        p.setFont(title_font)
        p.setPen(QPen(QColor(255, 255, 255, int(230 * alpha))))
        fm = p.fontMetrics()
        elided_title = fm.elidedText(self._title or "No Track", Qt.TextElideMode.ElideRight, text_w)
        title_y = cover_y + 2
        p.drawText(text_x, title_y, text_w, 20, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided_title)

        # Artist
        if self._artist:
            artist_font = QFont(FONT_FAMILY, 11)
            p.setFont(artist_font)
            p.setPen(QPen(QColor(255, 255, 255, int(160 * alpha))))
            fm = p.fontMetrics()
            elided_artist = fm.elidedText(self._artist, Qt.TextElideMode.ElideRight, text_w)
            p.drawText(text_x, title_y + 20, text_w, 18, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided_artist)

        # Album
        if self._album:
            album_font = QFont(FONT_FAMILY, 10)
            p.setFont(album_font)
            p.setPen(QPen(QColor(255, 255, 255, int(120 * alpha))))
            fm = p.fontMetrics()
            elided_album = fm.elidedText(self._album, Qt.TextElideMode.ElideRight, text_w)
            p.drawText(text_x, title_y + 38, text_w, 16, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided_album)

        # Playing indicator (dot)
        if self._playing:
            acc = accent_color()
            dot_r = 4
            dot_x = text_x + text_w - dot_r * 2 - 4
            dot_y = title_y + 8
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(acc.red(), acc.green(), acc.blue(), int(220 * alpha))))
            p.drawEllipse(dot_x, dot_y, dot_r * 2, dot_r * 2)

        p.end()

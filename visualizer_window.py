"""
Audio Visualizer — transparent overlay on the Windows taskbar.
Features: glow, click-through, left-side positioning, beat detection,
waveform mode, auto-hide, preset themes, album art colors, volume control.
"""
import ctypes
import ctypes.wintypes
import time
import numpy as np
from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QTimer, QPointF, QEvent
from PyQt6.QtGui import (
    QPainter, QColor, QBrush, QPen, QPainterPath,
    QRadialGradient, QLinearGradient, QFont,
)
from color_themes import get_theme, bar_color

# Win32 constants for click-through
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000

HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
SWP_NOOWNERZORDER = 0x0200
SW_SHOWNOACTIVATE = 4
SW_RESTORE = 9
user32 = ctypes.windll.user32


class VisualizerWindow(QWidget):
    def __init__(self, config: dict):
        super().__init__()
        self.cfg = config

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.BypassWindowManagerHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        num = self.cfg.get("bar_count", 64)
        self.fft_data = np.zeros(num)
        self.smoothed = np.zeros(num)

        # Beat detection state
        self._bass_history = []
        self._beat_flash = 0.0       # 0.0 = no flash, 1.0 = full flash
        self._beat_decay = 0.06      # how fast flash fades per frame

        # Auto-hide state
        self._last_sound_time = time.time()
        self._visible = True
        self._opacity = 1.0

        # Now-playing overlay: show briefly on track change, then fade out.
        self._media_overlay_started_at = 0.0
        self._media_overlay_duration = 3.5
        self._media_overlay_fade = 1.2
        self._media_overlay_alpha = 0.0

        # Runtime keep-alive counter for z-order/style refresh cadence.
        self._style_refresh_counter = 0

        # External modules (set by main.py)
        self.volume_scroller = None
        self.media_monitor = None

        # Repaint timer (~33 fps)
        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)
        self.timer.start(30)

        # Periodic reposition timer — adapts if Start button moves
        self._reposition_timer = QTimer()
        self._reposition_timer.timeout.connect(self._maybe_reposition)
        self._reposition_timer.start(5000)
        self._last_vis_w = 0

        # Periodic click-through refresh timer — keeps the window click-through
        # even if taskbar or other events try to change it
        self._clickthrough_refresh_timer = QTimer()
        self._clickthrough_refresh_timer.timeout.connect(self._refresh_window_styles)
        self._clickthrough_refresh_timer.start(500)

    # ====================== POSITIONING ==============================

    def position_on_taskbar(self):
        """Position to the LEFT of the Windows Start button (DPI-correct)."""
        screen = QApplication.primaryScreen()
        full = screen.geometry()
        avail = screen.availableGeometry()
        dpi_ratio = screen.devicePixelRatio()

        taskbar_y = avail.y() + avail.height()
        taskbar_h = full.height() - avail.height()
        screen_w = full.width()

        # Try to detect the Start button position
        vis_w = self._detect_start_button_x(dpi_ratio)
        source = "Start button"

        if vis_w is None or vis_w < 50:
            # Fallback to percentage-based width
            width_pct = self.cfg.get("width_percent", 40) / 100.0
            vis_w = int(screen_w * width_pct)
            source = f"{int(width_pct*100)}% fallback"

        # Small padding so bars don't touch the Start button
        vis_w = max(100, vis_w - 8)

        self.setGeometry(0, taskbar_y, vis_w, taskbar_h)
        self.show()
        self.raise_()

        # Enable click-through via Win32
        self._ensure_topmost(force_bounce=True)
        self._enable_click_through()

        self._last_vis_w = vis_w
        print(f"[Visualizer] Taskbar overlay: (0,{taskbar_y}) "
              f"{vis_w}x{taskbar_h}  ({source})")

    def _maybe_reposition(self):
        """Re-check Start button position and resize if it changed."""
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        dpi_ratio = screen.devicePixelRatio()
        new_w = self._detect_start_button_x(dpi_ratio)
        if new_w and new_w > 50:
            new_w = max(100, new_w - 8)
            if abs(new_w - self._last_vis_w) > 10:
                self.position_on_taskbar()

    def _detect_start_button_x(self, dpi_ratio: float):
        """Find the Start button's left edge (logical pixels).
        Returns None if detection fails."""
        try:
            taskbar_hwnd = user32.FindWindowW("Shell_TrayWnd", None)
            if not taskbar_hwnd:
                return None

            start_hwnd = user32.FindWindowExW(taskbar_hwnd, None, "Start", None)
            if not start_hwnd:
                return None

            rc = ctypes.wintypes.RECT()
            user32.GetWindowRect(start_hwnd, ctypes.byref(rc))

            # Convert physical pixels → logical pixels
            logical_x = int(rc.left / dpi_ratio)
            print(f"[Visualizer] Start button at physical x={rc.left}, "
                  f"logical x={logical_x}")
            return logical_x
        except Exception as e:
            print(f"[Visualizer] Start button detection failed: {e}")
            return None

    def _enable_click_through(self):
        """Set WS_EX_TRANSPARENT + WS_EX_LAYERED so clicks pass through."""
        hwnd = int(self.winId())
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(
            hwnd, GWL_EXSTYLE,
            style
            | WS_EX_TRANSPARENT
            | WS_EX_LAYERED
            | WS_EX_NOACTIVATE
        )

    def _ensure_topmost(self, force_bounce: bool = False):
        """Keep the overlay above taskbar even after taskbar receives clicks."""
        hwnd = int(self.winId())
        flags = (
            SWP_NOMOVE
            | SWP_NOSIZE
            | SWP_NOACTIVATE
            | SWP_SHOWWINDOW
            | SWP_NOOWNERZORDER
        )

        # Frequent NOTOPMOST->TOPMOST bouncing can cause visible flicker when
        # interacting with Start/taskbar, so only do it for explicit recovery.
        if force_bounce:
            user32.SetWindowPos(
                hwnd,
                HWND_NOTOPMOST,
                0,
                0,
                0,
                0,
                flags,
            )
        user32.SetWindowPos(
            hwnd,
            HWND_TOPMOST,
            0,
            0,
            0,
            0,
            flags,
        )

    def _refresh_window_styles(self):
        if self.cfg.get("enabled", True):
            self._restore_win32_visibility()
            self._restore_if_minimized_or_hidden()
        self._ensure_topmost(force_bounce=False)
        self._enable_click_through()

    def _restore_win32_visibility(self):
        """Recover window if shell toggled hidden/iconic at native Win32 level."""
        hwnd = int(self.winId())
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        if not user32.IsWindowVisible(hwnd):
            user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)

    def _restore_if_minimized_or_hidden(self):
        """Recover from shell/taskbar minimize or hide without stealing focus."""
        if self.isMinimized() or (self.windowState() & Qt.WindowState.WindowMinimized):
            self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
            self.showNormal()
        if self._opacity > 0 and not self.isVisible():
            self.show()
        self.raise_()

    def focusOutEvent(self, event):
        """Re-apply click-through when focus is lost (e.g., to taskbar)."""
        super().focusOutEvent(event)
        # Reapply styles to ensure overlay remains click-through and topmost.
        self._refresh_window_styles()

    def changeEvent(self, event):
        """Immediately recover if taskbar interaction minimized the overlay."""
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            if self.cfg.get("enabled", True) and (
                self.isMinimized()
                or (self.windowState() & Qt.WindowState.WindowMinimized)
            ):
                # Defer one tick so Qt finishes processing state change first.
                QTimer.singleShot(0, self._refresh_window_styles)

    def hideEvent(self, event):
        """Recover when shell temporarily hides the overlay (e.g., Start open)."""
        super().hideEvent(event)
        if self.cfg.get("enabled", True) and self._opacity > 0:
            QTimer.singleShot(0, self._refresh_window_styles)

    def mousePressEvent(self, event):
        """Block mouse events — window is click-through."""
        event.ignore()

    # ====================== DATA INPUT ===============================

    def update_fft(self, data: np.ndarray):
        n = min(len(self.smoothed), len(data))
        sens = self.cfg.get("sensitivity", 1.0)
        scaled = data[:n] * sens

        # Smooth: fast attack, slow decay
        for i in range(n):
            if scaled[i] > self.smoothed[i]:
                self.smoothed[i] = self.smoothed[i] * 0.3 + scaled[i] * 0.7
            else:
                self.smoothed[i] = self.smoothed[i] * 0.8 + scaled[i] * 0.2

        self.fft_data = self.smoothed.copy()

        # Detect meaningful audio from incoming signal (not only smoothed bars).
        # The previous threshold (smoothed max > 1.0) could miss normal playback,
        # causing auto-hide to fade out and never recover.
        if n > 0:
            peak = float(np.max(scaled))
            avg = float(np.mean(scaled))
            if np.isfinite(peak) and np.isfinite(avg):
                if peak > 0.08 or avg > 0.015:
                    self._last_sound_time = time.time()

        # Beat detection on low-frequency bins (bass)
        if self.cfg.get("beat_flash", True):
            bass = float(np.mean(self.fft_data[:6]))
            self._bass_history.append(bass)
            if len(self._bass_history) > 30:
                self._bass_history.pop(0)
            avg_bass = np.mean(self._bass_history) if self._bass_history else 0
            if bass > avg_bass * 1.8 and bass > 5.0:
                self._beat_flash = 1.0

    # ====================== TICK / AUTO-HIDE =========================

    def _tick(self):
        # Keep shell/taskbar z-order steals from making the overlay disappear.
        # Refresh every frame for fastest recovery from Start/taskbar transitions.
        self._refresh_window_styles()

        if not self.cfg.get("enabled", True):
            if self._opacity > 0:
                self._opacity = max(0, self._opacity - 0.1)
                self.setWindowOpacity(self._opacity)
            return

        # Auto-hide logic
        if self.cfg.get("auto_hide", True):
            silence_dur = time.time() - self._last_sound_time
            timeout = self.cfg.get("auto_hide_timeout", 5.0)

            if silence_dur > timeout:
                if self._opacity > 0:
                    self._opacity = max(0, self._opacity - 0.05)
                    self.setWindowOpacity(self._opacity)
            else:
                if self._opacity < 1.0:
                    self._opacity = min(1.0, self._opacity + 0.1)
                    self.setWindowOpacity(self._opacity)
        else:
            if self._opacity < 1.0:
                self._opacity = 1.0
                self.setWindowOpacity(self._opacity)

        # Decay beat flash
        if self._beat_flash > 0:
            self._beat_flash = max(0, self._beat_flash - self._beat_decay)

        # Update media overlay visibility/alpha.
        self._update_media_overlay_state()

        self.update()

    def _update_media_overlay_state(self):
        """Show now-playing briefly on change, then fade it out."""
        if not self.media_monitor:
            self._media_overlay_alpha = 0.0
            return

        media = self.media_monitor.info
        if not media.title:
            self._media_overlay_alpha = 0.0
            media.changed = False
            return

        now = time.time()
        if media.changed:
            self._media_overlay_started_at = now
            media.changed = False

        if self._media_overlay_started_at <= 0:
            self._media_overlay_alpha = 0.0
            return

        elapsed = now - self._media_overlay_started_at
        if elapsed <= self._media_overlay_duration:
            self._media_overlay_alpha = 1.0
        elif elapsed <= self._media_overlay_duration + self._media_overlay_fade:
            fade_elapsed = elapsed - self._media_overlay_duration
            self._media_overlay_alpha = max(
                0.0, 1.0 - (fade_elapsed / self._media_overlay_fade)
            )
        else:
            self._media_overlay_alpha = 0.0

    def _resolve_theme(self) -> dict:
        """Return the active color theme, applying album-art color only in dynamic mode."""
        theme_name = self.cfg.get("theme", "cyan")
        theme = dict(get_theme(theme_name))

        use_album_art = theme_name == "album_art"
        accent_rgb = (
            self.media_monitor.info.accent_rgb
            if self.media_monitor and self.media_monitor.info.accent_rgb
            else None
        )
        if use_album_art and accent_rgb:
            theme["base"] = accent_rgb
            theme["peak"] = tuple(min(c + 100, 255) for c in accent_rgb)
            theme["glow"] = tuple(min(c + 50, 255) for c in accent_rgb)

        return theme

    # ====================== PAINTING =================================

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        mode = self.cfg.get("mode", "bars")

        if mode == "wave":
            self._paint_waveform(p, w, h)
        elif mode == "mirror":
            self._paint_mirror(p, w, h)
        else:
            self._paint_bars(p, w, h)

        # Beat flash overlay
        if self._beat_flash > 0.01:
            alpha = int(self._beat_flash * 40)
            p.fillRect(0, 0, w, h, QColor(180, 220, 255, alpha))

        # Volume overlay (if hovering on visualizer)
        if self.volume_scroller and self.volume_scroller.show_volume:
            self._paint_volume_overlay(p, w, h)

        # Media info overlay (brief on track change + fade out)
        if (
            self.media_monitor
            and self.media_monitor.info.title
            and self._media_overlay_alpha > 0.01
        ):
            self._paint_media_overlay(p, w, h, self._media_overlay_alpha)

        p.end()

    def _paint_bars(self, p: QPainter, w: int, h: int):
        p.setPen(Qt.PenStyle.NoPen)

        num = len(self.fft_data)
        gap = 2
        bar_w = max(2, (w - gap * (num + 1)) / num)
        max_val = max(self.fft_data.max(), 0.001)

        theme = self._resolve_theme()

        for i in range(num):
            val = self.fft_data[i]
            norm = min(val / max_val, 1.0)
            bar_h = max(2, norm * (h - 6))

            x = gap + int(i * (bar_w + gap))
            y = int(h - bar_h - 3)

            # Get color from theme
            r, g, b = bar_color(theme, norm, i, num)

            # ---- Glow effect (drawn first, behind the bar) ----
            if self.cfg.get("glow", True) and norm > 0.1:
                glow_r = int(bar_w * 2.5)
                cx = x + bar_w / 2
                cy = y + bar_h / 2
                grad = QRadialGradient(QPointF(cx, cy), glow_r)
                glow_alpha = int(norm * 80)
                grad.setColorAt(0.0, QColor(r, g, b, glow_alpha))
                grad.setColorAt(1.0, QColor(r, g, b, 0))
                p.setBrush(QBrush(grad))
                p.drawEllipse(
                    QPointF(cx, cy),
                    glow_r, bar_h * 0.8
                )

            # ---- Actual bar ----
            alpha = int(160 + norm * 95)
            p.setBrush(QBrush(QColor(r, g, b, alpha)))
            p.drawRoundedRect(x, y, int(bar_w), int(bar_h), 2, 2)

    def _paint_waveform(self, p: QPainter, w: int, h: int):
        num = len(self.fft_data)
        max_val = max(self.fft_data.max(), 0.001)

        theme = self._resolve_theme()

        # Build smooth path
        path = QPainterPath()
        points = []
        for i in range(num):
            norm = min(self.fft_data[i] / max_val, 1.0)
            x = int(i * w / (num - 1)) if num > 1 else 0
            y = int(h - norm * (h - 8) - 4)
            points.append(QPointF(x, y))

        if not points:
            return

        # Smooth Catmull-Rom → cubic bezier
        path.moveTo(points[0])
        for i in range(1, len(points)):
            p0 = points[max(i - 1, 0)]
            p1 = points[i]
            ctrl_x = (p0.x() + p1.x()) / 2
            path.cubicTo(QPointF(ctrl_x, p0.y()), QPointF(ctrl_x, p1.y()), p1)

        # Get theme colors
        br, bg, bb = theme["base"]
        pr, pg, pb = theme["peak"]
        gr, gg, gb = theme["glow"]

        # Glow: thick blurred line behind
        if self.cfg.get("glow", True):
            glow_pen = QPen(QColor(gr, gg, gb, 50), 12)
            glow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(glow_pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)

        # Main line
        pen = QPen(QColor(pr, pg, pb, 200), 2.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

        # Fill under the curve (subtle)
        fill_path = QPainterPath(path)
        fill_path.lineTo(QPointF(w, h))
        fill_path.lineTo(QPointF(0, h))
        fill_path.closeSubpath()
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, QColor(gr, gg, gb, 40))
        grad.setColorAt(1.0, QColor(gr, gg, gb, 5))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawPath(fill_path)

    def _paint_mirror(self, p: QPainter, w: int, h: int):
        """Symmetric bars — grow outward from the center line."""
        p.setPen(Qt.PenStyle.NoPen)

        num = len(self.fft_data)
        gap = 2
        bar_w = max(2, (w - gap * (num + 1)) / num)
        max_val = max(self.fft_data.max(), 0.001)
        mid_y = h / 2

        theme = self._resolve_theme()

        for i in range(num):
            val = self.fft_data[i]
            norm = min(val / max_val, 1.0)
            half_h = max(1, norm * (mid_y - 3))

            x = gap + int(i * (bar_w + gap))
            top_y = int(mid_y - half_h)
            full_h = int(half_h * 2)

            # Get color from theme
            r, g, b = bar_color(theme, norm, i, num)

            # Glow
            if self.cfg.get("glow", True) and norm > 0.1:
                glow_r = int(bar_w * 2.5)
                cx = x + bar_w / 2
                grad = QRadialGradient(QPointF(cx, mid_y), glow_r)
                glow_alpha = int(norm * 80)
                grad.setColorAt(0.0, QColor(r, g, b, glow_alpha))
                grad.setColorAt(1.0, QColor(r, g, b, 0))
                p.setBrush(QBrush(grad))
                p.drawEllipse(QPointF(cx, mid_y), glow_r, half_h * 0.8)

            # Actual mirrored bar
            alpha = int(160 + norm * 95)
            p.setBrush(QBrush(QColor(r, g, b, alpha)))
            p.drawRoundedRect(x, top_y, int(bar_w), full_h, 2, 2)

    # ====================== CONFIG UPDATES ===========================

    def apply_config(self, cfg: dict):
        """Called when tray menu changes a setting."""
        self.cfg = cfg
        num = cfg.get("bar_count", 64)
        if len(self.fft_data) != num:
            self.fft_data = np.zeros(num)
            self.smoothed = np.zeros(num)
        # Re-position if width changed
        self.position_on_taskbar()

    # ====================== OVERLAYS ==================================

    def _paint_volume_overlay(self, p: QPainter, w: int, h: int):
        """Draw volume percentage on right side of visualizer."""
        vol_pct = self.volume_scroller.volume_pct
        
        # Semi-transparent background box
        box_w = 45
        box_h = 32
        box_x = w - box_w - 4
        box_y = h - box_h - 4
        
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(0, 0, 0, 140)))
        p.drawRoundedRect(box_x, box_y, box_w, box_h, 4, 4)
        
        # Volume percentage text
        font = QFont("Segoe UI", 14, QFont.Weight.Bold)
        p.setFont(font)
        p.setPen(QPen(QColor(100, 220, 255, 255)))
        text = f"{vol_pct}%"
        p.drawText(box_x, box_y, box_w, box_h, Qt.AlignmentFlag.AlignCenter, text)

    def _paint_media_overlay(self, p: QPainter, w: int, h: int, alpha: float = 1.0):
        """Draw now-playing intro card that briefly covers bars."""
        media = self.media_monitor.info
        if not media.title:
            return

        alpha = max(0.0, min(1.0, alpha))
        
        # Large centered card so metadata is readable before fading out.
        box_margin_x = 8
        box_w = max(120, w - (box_margin_x * 2))
        box_h = max(34, int(h * 0.78))
        box_x = int((w - box_w) / 2)
        box_y = int((h - box_h) / 2)
        
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(0, 0, 0, int(180 * alpha))))
        p.drawRoundedRect(box_x, box_y, box_w, box_h, 8, 8)
        
        # Line 1: title
        title_font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        p.setFont(title_font)
        p.setPen(QPen(QColor(230, 230, 230, int(240 * alpha))))
        title = media.title.strip() or "Now Playing"

        # Line 2: artist + album
        details_parts = []
        if media.artist:
            details_parts.append(media.artist.strip())
        if getattr(media, "album", ""):
            details_parts.append(media.album.strip())
        details = " • ".join([x for x in details_parts if x])

        pad_x = 10
        top_y = box_y + 6
        title_h = max(12, int(box_h * 0.48))
        details_h = max(10, box_h - title_h - 8)

        title_rect_x = box_x + pad_x
        title_rect_w = box_w - (pad_x * 2)
        title_rect_y = top_y

        # Elide title to fit.
        title_fm = p.fontMetrics()
        title = title_fm.elidedText(title, Qt.TextElideMode.ElideRight, title_rect_w)
        p.drawText(
            title_rect_x,
            title_rect_y,
            title_rect_w,
            title_h,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            title,
        )

        details_font = QFont("Segoe UI", 9)
        p.setFont(details_font)
        p.setPen(QPen(QColor(185, 185, 185, int(220 * alpha))))
        if details:
            details_fm = p.fontMetrics()
            details = details_fm.elidedText(
                details, Qt.TextElideMode.ElideRight, title_rect_w
            )
            p.drawText(
                title_rect_x,
                title_rect_y + title_h - 2,
                title_rect_w,
                details_h,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                details,
            )

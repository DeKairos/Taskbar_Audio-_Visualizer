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
from PyQt6.QtCore import Qt, QTimer, QPointF, QEvent, QRectF, pyqtSignal
from PyQt6.QtGui import (
    QPainter, QColor, QBrush, QPen, QPainterPath,
    QRadialGradient, QLinearGradient, QFont, QPixmap,
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
    media_overlay_requested = pyqtSignal()

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
        self._media_initial_auto_shown = False

        # Track-change morph: bars briefly collapse to center and re-expand.
        self._track_morph_started_at = 0.0
        self._track_morph_duration = 0.58

        # Startup intro animation state.
        self._startup_started_at = time.monotonic()
        self._startup_duration = 2.2

        # Runtime keep-alive counter for z-order/style refresh cadence.
        self._style_refresh_counter = 0

        # External modules (set by main.py)
        self.volume_scroller = None
        self.media_monitor = None
        self.media_click_watcher = None

        # Thread-safe trigger from global mouse hook.
        self.media_overlay_requested.connect(self._show_media_overlay_on_demand)

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
        """Auto-show now-playing once initially; later show only on click trigger."""
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
            if not self._media_initial_auto_shown:
                self._media_overlay_started_at = now
                self._track_morph_started_at = now
                self._media_initial_auto_shown = True
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

    def request_media_overlay(self):
        """Request media overlay display from non-Qt threads safely."""
        self.media_overlay_requested.emit()

    def _show_media_overlay_on_demand(self):
        """Show now-playing overlay when user clicks visualizer area."""
        if not self.media_monitor:
            return
        media = self.media_monitor.info
        if not media.title:
            return
        now = time.time()
        self._media_overlay_started_at = now
        self._track_morph_started_at = now

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

    def _startup_progress(self) -> float:
        """0.0->1.0 progress for initial reveal animation."""
        elapsed = time.monotonic() - self._startup_started_at
        if self._startup_duration <= 0:
            return 1.0
        return max(0.0, min(1.0, elapsed / self._startup_duration))

    def _track_morph_amount(self) -> float:
        """Return 0..1 intensity for the track-change morph animation."""
        if self._track_morph_started_at <= 0:
            return 0.0

        elapsed = time.time() - self._track_morph_started_at
        if elapsed <= 0 or elapsed >= self._track_morph_duration:
            return 0.0

        progress = elapsed / self._track_morph_duration
        triangle = 1.0 - abs((2.0 * progress) - 1.0)
        return max(0.0, min(1.0, triangle * triangle))

    def _stereo_split_gains(self):
        """Pseudo-stereo shaping: left favors low-mid, right favors high-mid."""
        n = len(self.fft_data)
        if n <= 0:
            return 1.0, 1.0

        low_end = max(4, int(n * 0.25))
        high_start = max(6, int(n * 0.35))
        high_end = max(high_start + 1, int(n * 0.78))

        low_band = self.fft_data[2:low_end] if low_end > 2 else self.fft_data[:low_end]
        high_band = self.fft_data[high_start:high_end]

        low_energy = float(np.mean(low_band)) if len(low_band) else 0.0
        high_energy = float(np.mean(high_band)) if len(high_band) else 0.0
        peak = max(float(np.max(self.fft_data)), 1e-6)

        low_norm = max(0.0, min(1.0, low_energy / peak))
        high_norm = max(0.0, min(1.0, high_energy / peak))

        left_gain = 0.88 + (0.52 * low_norm)
        right_gain = 0.88 + (0.52 * high_norm)
        return left_gain, right_gain

    # ====================== PAINTING =================================

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        mode = self.cfg.get("mode", "bars")
        intro_t = self._startup_progress()
        morph = self._track_morph_amount()

        if morph > 0.001:
            p.save()
            cx = w / 2.0
            squeeze = 1.0 - (0.62 * morph)
            p.translate(cx, 0)
            p.scale(squeeze, 1.0)
            p.translate(-cx, 0)

        # Initial reveal: bars slide in from left during startup intro.
        if intro_t < 1.0:
            eased = 1.0 - ((1.0 - intro_t) ** 3)
            reveal_w = max(1, int(w * max(0.08, eased)))
            p.save()
            p.setClipRect(0, 0, reveal_w, h)

            if mode == "wave":
                self._paint_waveform(p, w, h)
            elif mode == "mirror":
                self._paint_mirror(p, w, h)
            else:
                self._paint_bars(p, w, h)
            p.restore()
        else:
            if mode == "wave":
                self._paint_waveform(p, w, h)
            elif mode == "mirror":
                self._paint_mirror(p, w, h)
            else:
                self._paint_bars(p, w, h)

        if morph > 0.001:
            p.restore()
            # Tint briefly with current accent color during the morph.
            theme = self._resolve_theme()
            br, bg, bb = theme["base"]
            wash_alpha = int(55 * morph)
            if wash_alpha > 0:
                p.fillRect(0, 0, w, h, QColor(br, bg, bb, wash_alpha))

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

        if intro_t < 1.0:
            self._paint_startup_intro(p, w, h, intro_t)

        p.end()

    def _paint_startup_intro(self, p: QPainter, w: int, h: int, t: float):
        """Draw a short cinematic sweep on startup."""
        t = max(0.0, min(1.0, t))
        fade = 1.0 - t

        # Brief dark veil so reveal feels intentional.
        veil_alpha = int(90 * (fade ** 1.4))
        if veil_alpha > 0:
            p.fillRect(0, 0, w, h, QColor(0, 0, 0, veil_alpha))

        # Cyan sweep that glides across once.
        sweep_w = max(50, int(w * 0.34))
        sweep_center = int((t * 1.35 - 0.2) * w)
        grad = QLinearGradient(sweep_center - sweep_w, 0, sweep_center + sweep_w, 0)
        peak = int(130 * (fade ** 0.6))
        grad.setColorAt(0.0, QColor(90, 220, 255, 0))
        grad.setColorAt(0.5, QColor(120, 235, 255, peak))
        grad.setColorAt(1.0, QColor(90, 220, 255, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawRect(0, 0, w, h)

        # Subtle horizon line pulse near bottom edge.
        line_alpha = int(140 * (fade ** 1.1))
        if line_alpha > 0:
            line_grad = QLinearGradient(0, h - 2, w, h - 2)
            line_grad.setColorAt(0.0, QColor(80, 190, 240, 0))
            line_grad.setColorAt(0.5, QColor(130, 235, 255, line_alpha))
            line_grad.setColorAt(1.0, QColor(80, 190, 240, 0))
            p.setBrush(QBrush(line_grad))
            p.drawRect(0, h - 2, w, 2)

    def _paint_bars(self, p: QPainter, w: int, h: int):
        p.setPen(Qt.PenStyle.NoPen)

        num = len(self.fft_data)
        gap = 2
        bar_w = max(2, (w - gap * (num + 1)) / num)
        max_val = max(self.fft_data.max(), 0.001)
        left_gain, right_gain = self._stereo_split_gains()

        theme = self._resolve_theme()

        for i in range(num):
            pan = (i / (num - 1)) if num > 1 else 0.5
            side_gain = (left_gain * (1.0 - pan)) + (right_gain * pan)
            val = self.fft_data[i] * side_gain
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
        left_gain, right_gain = self._stereo_split_gains()

        theme = self._resolve_theme()

        # Build smooth path
        path = QPainterPath()
        points = []
        for i in range(num):
            pan = (i / (num - 1)) if num > 1 else 0.5
            side_gain = (left_gain * (1.0 - pan)) + (right_gain * pan)
            norm = min((self.fft_data[i] * side_gain) / max_val, 1.0)
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
        left_gain, right_gain = self._stereo_split_gains()

        theme = self._resolve_theme()

        for i in range(num):
            pan = (i / (num - 1)) if num > 1 else 0.5
            side_gain = (left_gain * (1.0 - pan)) + (right_gain * pan)
            val = self.fft_data[i] * side_gain
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

        pad_x = 10
        cover_gap = 8
        cover_size = max(20, min(box_h - 10, int(box_h * 0.75)))
        cover_x = box_x + pad_x
        cover_y = box_y + int((box_h - cover_size) / 2)

        cover_bytes = getattr(media, "cover_bytes", None)
        has_cover = bool(cover_bytes)
        if has_cover:
            pix = QPixmap()
            has_cover = pix.loadFromData(cover_bytes)

        show_cover_slot = True

        if has_cover:
            cover_rect_f = QRectF(float(cover_x), float(cover_y), float(cover_size), float(cover_size))
            clip_path = QPainterPath()
            clip_path.addRoundedRect(cover_rect_f, 5.0, 5.0)
            p.save()
            p.setClipPath(clip_path)
            scaled = pix.scaled(
                cover_size,
                cover_size,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            src_x = max(0, int((scaled.width() - cover_size) / 2))
            src_y = max(0, int((scaled.height() - cover_size) / 2))
            p.drawPixmap(
                cover_x,
                cover_y,
                scaled,
                src_x,
                src_y,
                cover_size,
                cover_size,
            )
            p.restore()
            p.setPen(QPen(QColor(255, 255, 255, int(70 * alpha)), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(cover_x, cover_y, cover_size, cover_size, 5, 5)
        else:
            # Keep a stable left slot even when art is unavailable.
            ph_grad = QLinearGradient(
                cover_x,
                cover_y,
                cover_x + cover_size,
                cover_y + cover_size,
            )
            ph_grad.setColorAt(0.0, QColor(70, 70, 70, int(180 * alpha)))
            ph_grad.setColorAt(1.0, QColor(35, 35, 35, int(180 * alpha)))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(ph_grad))
            p.drawRoundedRect(cover_x, cover_y, cover_size, cover_size, 5, 5)
            p.setPen(QPen(QColor(255, 255, 255, int(90 * alpha)), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(cover_x, cover_y, cover_size, cover_size, 5, 5)

            icon_font = QFont("Segoe UI", max(8, int(cover_size * 0.42)), QFont.Weight.Bold)
            p.setFont(icon_font)
            p.setPen(QPen(QColor(220, 220, 220, int(170 * alpha))))
            p.drawText(
                cover_x,
                cover_y,
                cover_size,
                cover_size,
                Qt.AlignmentFlag.AlignCenter,
                "♪",
            )
        
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

        top_y = box_y + 6
        title_h = max(12, int(box_h * 0.48))
        details_h = max(10, box_h - title_h - 8)

        left_offset = (cover_size + cover_gap) if show_cover_slot else 0
        title_rect_x = box_x + pad_x + left_offset
        title_rect_w = box_w - (pad_x * 2) - left_offset
        if title_rect_w < 30:
            return
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

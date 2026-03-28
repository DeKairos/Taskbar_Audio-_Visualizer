"""
Audio Visualizer — transparent overlay on the Windows taskbar.
Features: glow, click-through, left-side positioning, beat pulse background,
bars/wave/mirror/dot-matrix modes, auto-hide, themes, album art colors,
volume control.
"""
import ctypes
import ctypes.wintypes
import time
import random
import numpy as np
from PyQt6.QtWidgets import QWidget, QApplication, QToolButton, QGraphicsDropShadowEffect
from PyQt6.QtCore import Qt, QTimer, QPointF, QPoint, QEvent, QRectF, QRect, pyqtSignal
from PyQt6.QtGui import (
    QPainter, QColor, QBrush, QPen, QPainterPath,
    QRadialGradient, QLinearGradient, QFont, QPixmap,
    QCursor,
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
VK_LBUTTON = 0x01
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
        self.peak_caps = np.zeros(num)
        self._prev_weighted = np.zeros(num)
        self._stagnant_fft_frames = 0
        self._display_level_ref = 1.0

        # Dynamic quality state adapts visual cost to frame time.
        self._quality_level = "high"
        self._frame_ms_avg = 0.0
        self._glow_quality_scale = 1.0

        # Beat-driven visual motion state
        self._bass_history = []
        self._bg_pulse = 0.0         # 0.0 = calm, 1.0 = strong beat pulse
        self._bg_decay = 0.045       # pulse fade rate per frame
        self._bg_phase = 0.0         # animated background drift phase

        # Subtle particle dust for texture in compact taskbar mode.
        self._particles = []
        self._particle_cap = 24

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
        self._media_cover_pixmap = None
        self._media_cover_scaled_pixmap = None
        self._media_cover_scaled_size = 0

        # Track-change morph: bars briefly collapse to center and re-expand.
        self._track_morph_started_at = 0.0
        self._track_morph_duration = 0.58

        # Startup intro animation state.
        self._startup_started_at = time.monotonic()
        self._startup_duration = 2.2

        # Runtime keep-alive counter for z-order/style refresh cadence.
        self._style_refresh_counter = 0
        self._last_fft_update_time = time.time()

        # External modules (set by main.py)
        self.volume_scroller = None
        self.media_monitor = None
        self.media_click_watcher = None
        self._left_pressed_last = False
        self._media_button_rects = {}
        self._click_through_enabled = None
        self._last_media_buttons_layout_sig = None
        self._mode_getter = None

        # Painted control state & animations
        self.controls_rects = {}
        self.hovered_button = None
        # animated scale for subtle hover/press effects
        self.button_scale = {"prev": 1.0, "play": 1.0, "next": 1.0}
        # target scales used by the animation stepper
        self._button_target = {"prev": 1.0, "play": 1.0, "next": 1.0}
        # enable mouse tracking so hover updates work when overlay becomes interactive
        self.setMouseTracking(True)

        # Thread-safe trigger from global mouse hook.
        self.media_overlay_requested.connect(self._show_media_overlay_on_demand)

        try:
            from modes import get_mode as _get_mode
            self._mode_getter = _get_mode
        except Exception:
            self._mode_getter = None

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

        # Safe click polling in UI thread (avoids global low-level mouse hooks).
        self._click_poll_timer = QTimer()
        self._click_poll_timer.timeout.connect(self._poll_media_overlay_click)
        self._click_poll_timer.start(40)

        # Media control widgets (optional; created lazily based on config)
        self._media_buttons = {}
        mcfg = self.cfg.get("media_controls", {}) or {}
        self._use_widget_buttons = bool(mcfg.get("use_widgets", True))
        if self._use_widget_buttons:
            size = int(mcfg.get("size", 36) or 36)
            icon_font = QFont("Segoe UI Symbol", max(10, int(size * 0.5)))
            for name, glyph in [("prev", "⏮"), ("play", "⏯"), ("next", "⏭")]:
                try:
                    btn = QToolButton(self)
                    btn.setText(glyph)
                    btn.setFixedSize(size, size)
                    btn.setFont(icon_font)
                    btn.setCursor(Qt.CursorShape.PointingHandCursor)
                    btn.setAutoRaise(True)
                    btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
                    # Rounded translucent background for glass-like look and
                    # hover/pressed states using theme glow color.
                    try:
                        theme = self._resolve_theme()
                        gr, gg, gb = theme.get("glow", (90, 200, 255))
                        # subtle neutral base with glow on hover/press
                        css = (
                            f"QToolButton{{background: rgba(255,255,255,18); color: rgba(230,230,230,255); border-radius: {int(size//2)}px;}}"
                            f"QToolButton:hover{{background: rgba({gr},{gg},{gb},36);}}"
                            f"QToolButton:pressed{{background: rgba({gr},{gg},{gb},86);}}"
                        )
                        btn.setStyleSheet(css)
                        effect = QGraphicsDropShadowEffect(self)
                        effect.setBlurRadius(14)
                        effect.setOffset(0, 2)
                        effect.setColor(QColor(gr, gg, gb, 110))
                        btn.setGraphicsEffect(effect)
                    except Exception:
                        # Fallback minimal style
                        btn.setStyleSheet(
                            f"QToolButton{{background: rgba(255,255,255,18); color: rgba(230,230,230,255); border-radius: {int(size//2)}px;}}"
                        )
                    btn.clicked.connect(lambda checked, n=name: self._activate_media_control(n))
                    btn.hide()
                    self._media_buttons[name] = btn
                except Exception:
                    # If widget creation fails, fall back to painted controls
                    self._media_buttons = {}
                    self._use_widget_buttons = False
                    break

    def _poll_media_overlay_click(self):
        """Trigger media card when left-click starts over this visualizer."""
        try:
            left_pressed = bool(user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)
        except Exception:
            left_pressed = False
        # Rising edge only: one trigger per click press.
        if left_pressed and not self._left_pressed_last:
            global_pos = QCursor.pos()
            if self.geometry().contains(global_pos):
                widget_pos = self.mapFromGlobal(global_pos)
                # If overlay is visible, try the painted/widget media control hit-testing.
                if self._media_overlay_alpha > 0.01 and (
                    getattr(self, "_media_button_rects", None) or getattr(self, "controls_rects", None)
                ):
                    try:
                        # Prefer the unified handler which will call the monitor actions.
                        self.handle_media_click(widget_pos.x(), widget_pos.y())
                    except Exception:
                        # Fallback: best-effort per-rect check
                        merged = {}
                        merged.update(getattr(self, "_media_button_rects", {}) or {})
                        merged.update(getattr(self, "controls_rects", {}) or {})
                        for name, rect in merged.items():
                            if rect.contains(widget_pos):
                                self._activate_media_control(name)
                                break
                    # keep overlay visible
                    self._media_overlay_started_at = time.time()
                else:
                    self._show_media_overlay_on_demand()

        self._left_pressed_last = left_pressed

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
        if self._click_through_enabled is True:
            return
        hwnd = int(self.winId())
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(
            hwnd, GWL_EXSTYLE,
            style
            | WS_EX_TRANSPARENT
            | WS_EX_LAYERED
            | WS_EX_NOACTIVATE
        )
        self._click_through_enabled = True

    def _disable_click_through(self):
        """Clear WS_EX_TRANSPARENT so this window (and children) receive mouse events."""
        if self._click_through_enabled is False:
            return
        try:
            hwnd = int(self.winId())
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            new_style = style & ~WS_EX_TRANSPARENT
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_style)
            self._click_through_enabled = False
        except Exception:
            pass

    def _update_media_buttons_geometry(self):
        """Position media buttons according to config (right/center/left)."""
        if not getattr(self, "_media_buttons", None):
            return
        try:
            w = self.width()
            h = self.height()
            mcfg = self.cfg.get("media_controls", {}) or {}
            configured_size = int(mcfg.get("size", 36) or 36)
            padding = int(mcfg.get("padding", 8) or 8)
            configured_spacing = int(mcfg.get("spacing", 6) or 6)
            position = mcfg.get("position", "right")

            names = ["prev", "play", "next"]
            n = len(names)
            size = configured_size
            spacing = configured_spacing
            total_w = n * size + (n - 1) * spacing

            # If the media overlay card is visible, constrain widget buttons
            # to sit inside that card so they never overflow the black box.
            if getattr(self, "_media_overlay_alpha", 0.0) > 0.01 and getattr(self, "media_monitor", None) and getattr(self.media_monitor, "info", None) and getattr(self.media_monitor.info, "title", ""):
                rect = self._media_overlay_rect(w, h)
                # Right-align the controls inside the overlay box horizontally.
                overlay_pad = max(6, min(10, rect.height() // 4))
                # In compact taskbars, keep controls sized to fit card height.
                max_size_in_card = max(20, rect.height() - (overlay_pad * 2))
                size = max(20, min(configured_size, max_size_in_card))
                spacing = max(3, min(configured_spacing, max(4, size // 4)))
                total_w = n * size + (n - 1) * spacing
                start_x = max(rect.x() + overlay_pad, rect.x() + rect.width() - overlay_pad - total_w)
                # Keep controls inside the card; avoid negative y in short taskbars.
                btn_y = rect.y() + rect.height() - overlay_pad - size
                btn_y = max(rect.y() + 1, btn_y)
            else:
                if position == "right":
                    start_x = max(0, w - padding - total_w)
                elif position == "center":
                    start_x = max(0, int((w - total_w) / 2))
                else:
                    start_x = padding

                btn_y = max(0, h - padding - size - 6)

            for idx, name in enumerate(names):
                btn = self._media_buttons.get(name)
                if not btn:
                    continue
                x = start_x + idx * (size + spacing)
                btn.setFixedSize(size, size)
                font = btn.font()
                font.setPointSize(max(10, int(size * 0.58)))
                btn.setFont(font)
                btn.move(int(x), int(btn_y))
        except Exception:
            pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Recompute button geometry on resize
        try:
            self._update_media_buttons_geometry()
        except Exception:
            pass

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
        # If media controls are implemented as widgets and the overlay is visible,
        # keep window interactive so child buttons can receive mouse events.
        mcfg = self.cfg.get("media_controls", {}) or {}
        use_widgets = bool(mcfg.get("use_widgets", True)) and getattr(self, "_use_widget_buttons", False)
        if use_widgets and getattr(self, "_media_overlay_alpha", 0.0) > 0.01:
            self._disable_click_through()
        else:
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
        """Handle mouse presses when the media overlay is interactive.

        When the painted overlay is visible we accept left clicks and dispatch
        them to media controls; otherwise keep the window click-through by
        ignoring events.
        """
        try:
            if event.button() == Qt.MouseButton.LeftButton and getattr(self, "_media_overlay_alpha", 0.0) > 0.01:
                # If using widget-based controls, let child widgets handle clicks.
                mcfg = self.cfg.get("media_controls", {}) or {}
                use_widgets = bool(mcfg.get("use_widgets", True)) and self._use_widget_buttons
                if use_widgets:
                    # Let default handling propagate to child widgets; do not ignore.
                    event.ignore()
                    return

                pos = event.pos()
                handled = False
                try:
                    handled = self.handle_media_click(pos.x(), pos.y())
                except Exception:
                    handled = False

                if handled:
                    event.accept()
                    return
        except Exception:
            pass

        # Default: ignore so the window remains click-through
        event.ignore()

    def mouseMoveEvent(self, event):
        """Track hover for painted controls while overlay is visible."""
        try:
            if getattr(self, "_media_overlay_alpha", 0.0) > 0.01:
                self.update_hover_state(event.pos())
                event.accept()
                return
        except Exception:
            pass
        event.ignore()

    def leaveEvent(self, event):
        """Clear hover when the mouse leaves the widget area."""
        try:
            if self.hovered_button:
                self.hovered_button = None
                for n in ("prev", "play", "next"):
                    self._button_target[n] = 1.0
                try:
                    QApplication.restoreOverrideCursor()
                except Exception:
                    pass
                self.update()
        except Exception:
            pass
        super().leaveEvent(event)

    # ====================== DATA INPUT ===============================

    def update_fft(self, data: np.ndarray):
        self._last_fft_update_time = time.time()
        n = min(len(self.smoothed), len(data))
        sens = self.cfg.get("sensitivity", 1.0)
        scaled = data[:n] * sens

        if n > 0:
            low_end_boost = float(self.cfg.get("low_end_boost", 1.35) or 1.35)
            low_end_boost = max(1.0, min(2.2, low_end_boost))
            pos = np.linspace(0.0, 1.0, n)
            bass_curve = 1.0 + ((1.0 - pos) ** 1.35) * (low_end_boost - 1.0)
            weighted = scaled * bass_curve
        else:
            weighted = scaled

        has_meaningful_audio = False
        if n > 0:
            peak = float(np.max(weighted))
            avg = float(np.mean(weighted))
            if np.isfinite(peak) and np.isfinite(avg):
                has_meaningful_audio = bool(peak > 0.07 or avg > 0.014)

        # Some loopback drivers keep emitting nearly-identical FFT frames on pause.
        # Treat persistent stagnant frames as paused/silent so visuals decay naturally.
        stagnant_input = False
        if n > 0:
            if len(self._prev_weighted) != len(self.smoothed):
                self._prev_weighted = np.zeros(len(self.smoothed))
            prev_view = self._prev_weighted[:n]
            delta = float(np.mean(np.abs(weighted - prev_view)))
            denom = max(float(np.mean(np.abs(weighted))), 1e-6)
            rel_delta = delta / denom
            stagnant_threshold = float(self.cfg.get("stagnant_delta_threshold", 0.0012) or 0.0012)
            stagnant_threshold = max(0.0001, min(0.02, stagnant_threshold))
            if rel_delta < stagnant_threshold:
                self._stagnant_fft_frames += 1
            else:
                self._stagnant_fft_frames = 0
            stagnant_frames_required = int(self.cfg.get("stagnant_frames_required", 14) or 14)
            stagnant_frames_required = max(4, min(60, stagnant_frames_required))
            stagnant_input = self._stagnant_fft_frames >= stagnant_frames_required
            prev_view[:] = weighted
        else:
            self._stagnant_fft_frames = 0

        # Smooth: fast attack, slow decay
        if n > 0:
            smoothed_view = self.smoothed[:n]
            if has_meaningful_audio and not stagnant_input:
                attack_mask = weighted > smoothed_view
                smoothed_view[attack_mask] = (smoothed_view[attack_mask] * 0.25) + (weighted[attack_mask] * 0.75)
                decay_mask = ~attack_mask
                smoothed_view[decay_mask] = (smoothed_view[decay_mask] * 0.86) + (weighted[decay_mask] * 0.14)
            else:
                # During pause/silence, ease bars toward base level (zero), not noise floor.
                silent_decay = float(self.cfg.get("silent_decay_rate", 0.965) or 0.965)
                silent_decay = max(0.90, min(0.99, silent_decay))
                smoothed_view *= silent_decay
                # Prevent denormal-like tails from visually "sticking" above baseline.
                smoothed_view[smoothed_view < 0.012] = 0.0

        # Peak-hold caps decay gently for punchier visual transients.
        if self.cfg.get("peak_caps_enabled", True):
            peak_decay = float(self.cfg.get("peak_hold_decay", 0.045) or 0.045)
            peak_decay = max(0.01, min(0.12, peak_decay))
            if n > 0:
                self.peak_caps[:n] = np.maximum(
                    self.peak_caps[:n] * (1.0 - peak_decay),
                    self.smoothed[:n],
                )
        else:
            self.peak_caps[:n] = self.smoothed[:n]

        self.fft_data = self.smoothed.copy()

        if n > 0:
            current_peak = float(np.max(self.smoothed[:n]))
            ref_attack = float(self.cfg.get("level_ref_attack", 0.22) or 0.22)
            ref_attack = max(0.05, min(0.6, ref_attack))
            ref_decay_active = float(self.cfg.get("level_ref_decay_active", 0.995) or 0.995)
            ref_decay_active = max(0.96, min(0.9995, ref_decay_active))
            ref_decay_silent = float(self.cfg.get("level_ref_decay_silent", 0.94) or 0.94)
            ref_decay_silent = max(0.85, min(0.995, ref_decay_silent))

            if current_peak > self._display_level_ref:
                self._display_level_ref = (
                    (self._display_level_ref * (1.0 - ref_attack))
                    + (current_peak * ref_attack)
                )
            else:
                decay = ref_decay_silent if (not has_meaningful_audio or stagnant_input) else ref_decay_active
                self._display_level_ref *= decay

            self._display_level_ref = max(0.12, min(200.0, self._display_level_ref))

        # Detect meaningful audio from incoming signal (not only smoothed bars).
        # The previous threshold (smoothed max > 1.0) could miss normal playback,
        # causing auto-hide to fade out and never recover.
        if n > 0 and has_meaningful_audio and not stagnant_input:
            self._last_sound_time = time.time()

        # Beat detection on low-frequency bins (bass)
        if self.cfg.get("beat_flash", True):
            bass = float(np.mean(self.fft_data[:6]))
            self._bass_history.append(bass)
            if len(self._bass_history) > 30:
                self._bass_history.pop(0)
            avg_bass = np.mean(self._bass_history) if self._bass_history else 0
            if bass > avg_bass * 1.8 and bass > 5.0:
                self._bg_pulse = 1.0

    # ====================== TICK / AUTO-HIDE =========================

    def _tick(self):
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

        # Decay beat pulse and animate the moving background.
        if self._bg_pulse > 0:
            self._bg_pulse = max(0, self._bg_pulse - self._bg_decay)
        self._bg_phase = (self._bg_phase + 0.018) % 1.0

        # Adapt rendering quality only when dynamic quality is enabled.
        if self.cfg.get("dynamic_quality", True):
            ms = self._frame_ms_avg
            if ms > 16.5:
                self._quality_level = "low"
                self._glow_quality_scale = 0.5
            elif ms > 11.0:
                self._quality_level = "medium"
                self._glow_quality_scale = 0.75
            else:
                self._quality_level = "high"
                self._glow_quality_scale = 1.0
        else:
            self._quality_level = "high"
            self._glow_quality_scale = 1.0

        self._decay_when_stale_audio()

        self._update_particles()

        # Update media overlay visibility/alpha.
        self._update_media_overlay_state()

        # Animate button scales toward targets for smooth hover/press transitions.
        try:
            for k in list(self.button_scale.keys()):
                cur = float(self.button_scale.get(k, 1.0))
                tgt = float(self._button_target.get(k, 1.0))
                step = 0.16
                cur += (tgt - cur) * step
                if abs(cur - tgt) < 0.001:
                    cur = tgt
                self.button_scale[k] = cur
        except Exception:
            pass

        self.update()

    def _decay_when_stale_audio(self):
        """Decay bars/caps when no fresh FFT frames arrive (e.g., paused audio)."""
        now = time.time()
        if (now - self._last_fft_update_time) <= 0.12:
            return

        if len(self.smoothed) == 0:
            return

        # Natural falloff for bars while source is paused/stalled.
        stale_decay = float(self.cfg.get("stale_audio_decay_rate", 0.95) or 0.95)
        stale_decay = max(0.88, min(0.995, stale_decay))
        self.smoothed *= stale_decay
        self.smoothed[self.smoothed < 0.012] = 0.0
        self._display_level_ref *= 0.95
        self._display_level_ref = max(0.12, min(200.0, self._display_level_ref))

        if self.cfg.get("peak_caps_enabled", True):
            peak_decay = float(self.cfg.get("peak_hold_decay", 0.045) or 0.045)
            peak_decay = max(0.01, min(0.12, peak_decay))
            self.peak_caps *= (1.0 - peak_decay)
            # Ensure caps do not remain below current bar level.
            self.peak_caps = np.maximum(self.peak_caps, self.smoothed)
        else:
            self.peak_caps[:] = self.smoothed

        self.fft_data = self.smoothed.copy()

    def _update_media_overlay_state(self):
        """Auto-show now-playing on track changes; allow click-to-show on demand."""
        if not self.media_monitor:
            self._media_overlay_alpha = 0.0
            return

        media = self.media_monitor.info
        if not media.title:
            self._media_overlay_alpha = 0.0
            self._media_cover_pixmap = None
            self._media_cover_scaled_pixmap = None
            self._media_cover_scaled_size = 0
            self._media_button_rects = {}
            media.changed = False
            return

        now = time.time()
        if media.changed:
            # Track metadata changed: show card + run morph once per change.
            self._media_overlay_started_at = now
            self._track_morph_started_at = now
            self._media_initial_auto_shown = True
            self._media_cover_pixmap = None
            self._media_cover_scaled_pixmap = None
            self._media_cover_scaled_size = 0
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

        # If using widget-based media controls, show/hide buttons and toggle
        # click-through so child widgets receive events while visible.
        try:
            mcfg = self.cfg.get("media_controls", {}) or {}
            use_widgets = bool(mcfg.get("use_widgets", True)) and self._use_widget_buttons
            # Widget-based controls: show/hide child widgets and toggle click-through
            if use_widgets and getattr(self, "_media_buttons", None):
                if self._media_overlay_alpha > 0.01:
                    for b in self._media_buttons.values():
                        b.show()
                    # Allow the window to accept mouse events for buttons
                    self._disable_click_through()
                else:
                    for b in self._media_buttons.values():
                        b.hide()
                    # Restore click-through when overlay is hidden
                    self._enable_click_through()
                # Only recompute button geometry when input layout changes.
                vis = self._media_overlay_alpha > 0.01
                layout_sig = (
                    self.width(),
                    self.height(),
                    int(mcfg.get("size", 36) or 36),
                    int(mcfg.get("padding", 8) or 8),
                    int(mcfg.get("spacing", 6) or 6),
                    str(mcfg.get("position", "right")),
                    bool(vis),
                )
                if layout_sig != self._last_media_buttons_layout_sig:
                    self._last_media_buttons_layout_sig = layout_sig
                    self._update_media_buttons_geometry()
            else:
                # Painted controls fallback: enable/disable click-through while overlay visible
                if self._media_overlay_alpha > 0.01:
                    self._disable_click_through()
                else:
                    self._enable_click_through()
        except Exception:
            pass

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

    def _update_particles(self):
        """Update lightweight ambient particles used as subtle visual texture."""
        if not self.cfg.get("glow", True):
            self._particles.clear()
            return

        if self._quality_level == "low":
            self._particles.clear()
            return

        if len(self.fft_data) == 0:
            self._particles.clear()
            return

        max_val = max(float(np.max(self.fft_data)), 0.001)
        energy = float(np.mean(self.fft_data) / max_val)
        energy = max(0.0, min(1.0, energy))

        if self._quality_level == "medium":
            self._particle_cap = 12
        else:
            self._particle_cap = 24

        spawn_budget = 0
        if self.cfg.get("enabled", True) and self._opacity > 0.15:
            if energy > 0.18:
                spawn_budget += 1
            if self._bg_pulse > 0.25:
                spawn_budget += 1

        for _ in range(spawn_budget):
            if len(self._particles) >= self._particle_cap:
                break
            self._particles.append(
                {
                    "x": random.uniform(0.0, max(1.0, float(self.width()))),
                    "y": random.uniform(float(self.height()) * 0.35, float(self.height()) + 4.0),
                    "vx": random.uniform(-0.15, 0.15),
                    "vy": random.uniform(-0.45, -0.1),
                    "life": random.uniform(0.55, 1.0),
                    "size": random.uniform(1.3, 2.6),
                }
            )

        alive = []
        width = float(max(1, self.width()))
        for pt in self._particles:
            pt["x"] += pt["vx"]
            pt["y"] += pt["vy"]
            pt["life"] -= 0.016

            if pt["x"] < -6.0:
                pt["x"] = width + 2.0
            elif pt["x"] > width + 6.0:
                pt["x"] = -2.0

            if pt["life"] > 0.0 and pt["y"] > -6.0:
                alive.append(pt)
        self._particles = alive

    def _paint_dynamic_background(self, p: QPainter, w: int, h: int):
        """Beat-synced moving gradient: dynamic but calm enough for taskbar use."""
        if not self.cfg.get("glow", True) and not self.cfg.get("beat_flash", True):
            return

        theme = self._resolve_theme()
        br, bg, bb = theme["base"]
        gr, gg, gb = theme["glow"]

        phase = self._bg_phase
        shift = int(w * (0.5 + 0.5 * np.sin(phase * np.pi * 2.0)))
        pulse = self._bg_pulse if self.cfg.get("beat_flash", True) else 0.0

        # Keep idle state very dim; let beat pulses carry most of the look.
        ambient = 3 if self.cfg.get("glow", True) else 0
        a0 = int(ambient + (14 * pulse))
        a1 = int(max(0, ambient - 1) + (18 * pulse))
        a2 = int(max(0, ambient - 2) + (10 * pulse))

        # Avoid drawing an always-on tint when both ambient and pulse are tiny.
        if (a0 + a1 + a2) <= 2:
            return

        grad = QLinearGradient(-int(w * 0.2) + shift, 0, int(w * 1.2) - shift, h)
        grad.setColorAt(0.0, QColor(br, bg, bb, a0))
        grad.setColorAt(0.5, QColor(gr, gg, gb, a1))
        grad.setColorAt(1.0, QColor(br, bg, bb, a2))

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawRect(0, 0, w, h)

    def _paint_particles(self, p: QPainter):
        if not self.cfg.get("glow", True) or not self._particles:
            return

        theme = self._resolve_theme()
        r, g, b = theme["glow"]
        p.setPen(Qt.PenStyle.NoPen)

        for pt in self._particles:
            alpha = int(24 * pt["life"] + (16 * self._bg_pulse))
            if alpha <= 0:
                continue
            p.setBrush(QBrush(QColor(r, g, b, min(56, alpha))))
            p.drawEllipse(QPointF(pt["x"], pt["y"]), pt["size"], pt["size"])

    def _quality_stride(self) -> int:
        if self._quality_level == "low":
            return 3
        if self._quality_level == "medium":
            return 2
        return 1

    def _sampled_bins(self):
        stride = self._quality_stride()
        return self.fft_data[::stride], self.peak_caps[::stride]

    def _display_max_value(self, values: np.ndarray, peak_caps: np.ndarray | None = None) -> float:
        """Return a stable normalization reference so visuals can naturally settle to baseline."""
        ref = max(0.12, float(self._display_level_ref))
        if len(values) > 0:
            ref = max(ref, float(np.max(values)))
        if peak_caps is not None and len(peak_caps) > 0:
            ref = max(ref, float(np.max(peak_caps)))
        return ref

    def _energy_norm(self, value: float, max_value: float) -> float:
        raw = min(max(value / max(max_value, 0.001), 0.0), 1.0)
        return raw ** 0.82

    def _bar_fill_brush(self, theme: dict, norm: float, index: int, total: int, y: int, bar_h: int):
        r, g, b = bar_color(theme, norm, index, total)
        if theme.get("rainbow"):
            return QBrush(QColor(r, g, b, int(160 + norm * 95)))

        gradient_mode = self.cfg.get("gradient_mode", "three_color")
        if gradient_mode == "off":
            return QBrush(QColor(r, g, b, int(160 + norm * 95)))

        pr, pg, pb = theme["peak"]
        gr, gg, gb = theme["glow"]
        grad = QLinearGradient(0, y, 0, y + max(1, bar_h))

        if gradient_mode == "two_color":
            grad.setColorAt(0.0, QColor(pr, pg, pb, int(185 + norm * 60)))
            grad.setColorAt(1.0, QColor(r, g, b, int(150 + norm * 70)))
        else:
            grad.setColorAt(0.0, QColor(pr, pg, pb, int(185 + norm * 60)))
            grad.setColorAt(0.45, QColor(gr, gg, gb, int(165 + norm * 70)))
            grad.setColorAt(1.0, QColor(r, g, b, int(145 + norm * 75)))

        return QBrush(grad)

    # ====================== PAINTING =================================

    def paintEvent(self, event):
        frame_start = time.perf_counter()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        mode = self.cfg.get("mode", "bars")
        if mode == "oscilloscope":
            mode = "wave"
        elif mode == "mirror_tunnel":
            mode = "mirror"

        # Resolve mode painter using cached registry accessor (set in __init__).
        get_mode = self._mode_getter

        mode_params = self.cfg.get("mode_params", {}).get(mode, {})
        intro_t = self._startup_progress()
        morph = self._track_morph_amount()

        self._paint_dynamic_background(p, w, h)

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

            # Dispatch to registered painter if available, otherwise fallback to built-ins.
            painter_info = get_mode(mode) if get_mode else None
            painter = painter_info.get("painter") if painter_info else None
            if painter:
                try:
                    painter(self, p, w, h, mode_params)
                except Exception:
                    self._paint_bars(p, w, h)
            else:
                # Keep legacy fallbacks for unregistered/unknown modes.
                if mode == "wave":
                    self._paint_waveform(p, w, h)
                elif mode == "mirror":
                    self._paint_mirror(p, w, h)
                elif mode == "mirror_tunnel":
                    self._paint_mirror_tunnel(p, w, h)
                elif mode == "dot_matrix":
                    self._paint_dot_matrix(p, w, h)
                elif mode == "constellation":
                    self._paint_constellation(p, w, h)
                else:
                    self._paint_bars(p, w, h)
            p.restore()
        else:
            painter_info = get_mode(mode) if get_mode else None
            painter = painter_info.get("painter") if painter_info else None
            if painter:
                try:
                    painter(self, p, w, h, mode_params)
                except Exception:
                    self._paint_bars(p, w, h)
            else:
                if mode == "wave":
                    self._paint_waveform(p, w, h)
                elif mode == "mirror":
                    self._paint_mirror(p, w, h)
                elif mode == "mirror_tunnel":
                    self._paint_mirror_tunnel(p, w, h)
                elif mode == "dot_matrix":
                    self._paint_dot_matrix(p, w, h)
                elif mode == "constellation":
                    self._paint_constellation(p, w, h)
                else:
                    self._paint_bars(p, w, h)

        self._paint_particles(p)

        if morph > 0.001:
            p.restore()
            # Tint briefly with current accent color during the morph.
            theme = self._resolve_theme()
            br, bg, bb = theme["base"]
            wash_alpha = int(55 * morph)
            if wash_alpha > 0:
                p.fillRect(0, 0, w, h, QColor(br, bg, bb, wash_alpha))

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

        elapsed_ms = (time.perf_counter() - frame_start) * 1000.0
        if self._frame_ms_avg <= 0.0:
            self._frame_ms_avg = elapsed_ms
        else:
            self._frame_ms_avg = (self._frame_ms_avg * 0.9) + (elapsed_ms * 0.1)

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

        values, peak_caps = self._sampled_bins()
        num = len(values)
        if num <= 0:
            return
        gap = 2
        bar_w = max(2, (w - gap * (num + 1)) / num)
        peak_caps_enabled = bool(self.cfg.get("peak_caps_enabled", True))
        max_val = self._display_max_value(values, peak_caps if peak_caps_enabled else None)
        left_gain, right_gain = self._stereo_split_gains()

        theme = self._resolve_theme()

        for i in range(num):
            pan = (i / (num - 1)) if num > 1 else 0.5
            side_gain = (left_gain * (1.0 - pan)) + (right_gain * pan)
            val = values[i] * side_gain
            cap_val = peak_caps[i] * side_gain if peak_caps_enabled else val
            norm = self._energy_norm(val, max_val)
            cap_norm = self._energy_norm(cap_val, max_val)
            bar_h = norm * (h - 6)
            cap_h = cap_norm * (h - 6)
            if bar_h < 0.6:
                continue

            x = gap + int(i * (bar_w + gap))
            y = int(h - bar_h - 3)
            cap_y = int(h - cap_h - 5)

            # Get color from theme
            r, g, b = bar_color(theme, norm, i, num)

            # ---- Glow effect (drawn first, behind the bar) ----
            if self.cfg.get("glow", True) and norm > 0.1:
                glow_r = int(bar_w * 2.5)
                cx = x + bar_w / 2
                cy = y + bar_h / 2
                grad = QRadialGradient(QPointF(cx, cy), glow_r)
                glow_alpha = int((norm * 46 + self._bg_pulse * 16) * self._glow_quality_scale)
                grad.setColorAt(0.0, QColor(r, g, b, glow_alpha))
                grad.setColorAt(1.0, QColor(r, g, b, 0))
                p.setBrush(QBrush(grad))
                p.drawEllipse(
                    QPointF(cx, cy),
                    glow_r, bar_h * 0.8
                )

            # ---- Actual bar ----
            p.setBrush(self._bar_fill_brush(theme, norm, i, num, y, int(bar_h)))
            p.drawRoundedRect(x, y, int(bar_w), int(bar_h), 2, 2)

            if peak_caps_enabled and cap_h >= 0.6:
                # ---- Peak hold cap ----
                cap_alpha = int(140 + cap_norm * 90)
                p.setBrush(QBrush(QColor(theme["peak"][0], theme["peak"][1], theme["peak"][2], cap_alpha)))
                p.drawRoundedRect(x, cap_y, int(bar_w), 2, 1, 1)

    def _paint_waveform(self, p: QPainter, w: int, h: int):
        values, _peak_caps = self._sampled_bins()
        num = len(values)
        if num <= 0:
            return
        max_val = self._display_max_value(values)
        left_gain, right_gain = self._stereo_split_gains()

        theme = self._resolve_theme()

        # Build smooth path
        path = QPainterPath()
        points = []
        for i in range(num):
            pan = (i / (num - 1)) if num > 1 else 0.5
            side_gain = (left_gain * (1.0 - pan)) + (right_gain * pan)
            norm = self._energy_norm(values[i] * side_gain, max_val)
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
        gradient_mode = self.cfg.get("gradient_mode", "three_color")

        # Glow: thick blurred line behind
        if self.cfg.get("glow", True):
            glow_pen = QPen(QColor(gr, gg, gb, int((32 + self._bg_pulse * 20) * self._glow_quality_scale)), 10)
            glow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(glow_pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)

        # Main line
        if gradient_mode == "off":
            pen = QPen(QColor(pr, pg, pb, 200), 2.5)
        else:
            line_grad = QLinearGradient(0, 0, w, 0)
            if gradient_mode == "two_color":
                line_grad.setColorAt(0.0, QColor(br, bg, bb, 190))
                line_grad.setColorAt(1.0, QColor(pr, pg, pb, 220))
            else:
                line_grad.setColorAt(0.0, QColor(br, bg, bb, 185))
                line_grad.setColorAt(0.5, QColor(gr, gg, gb, 220))
                line_grad.setColorAt(1.0, QColor(pr, pg, pb, 225))
            pen = QPen(QBrush(line_grad), 2.5)
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
        if gradient_mode == "off":
            grad.setColorAt(0.0, QColor(gr, gg, gb, 30))
            grad.setColorAt(1.0, QColor(gr, gg, gb, 4))
        elif gradient_mode == "two_color":
            grad.setColorAt(0.0, QColor(pr, pg, pb, 42))
            grad.setColorAt(1.0, QColor(br, bg, bb, 6))
        else:
            grad.setColorAt(0.0, QColor(pr, pg, pb, 42))
            grad.setColorAt(0.45, QColor(gr, gg, gb, 34))
            grad.setColorAt(1.0, QColor(br, bg, bb, 7))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawPath(fill_path)

    def _paint_mirror(self, p: QPainter, w: int, h: int):
        """Symmetric bars — grow outward from the center line."""
        p.setPen(Qt.PenStyle.NoPen)

        values, peak_caps = self._sampled_bins()
        num = len(values)
        if num <= 0:
            return
        gap = 2
        bar_w = max(2, (w - gap * (num + 1)) / num)
        peak_caps_enabled = bool(self.cfg.get("peak_caps_enabled", True))
        max_val = self._display_max_value(values, peak_caps if peak_caps_enabled else None)
        mid_y = h / 2
        left_gain, right_gain = self._stereo_split_gains()
        center_mode = bool(self.cfg.get("mirror_center_mode", False))
        center_gap = int(max(0, self.cfg.get("mirror_center_gap", 2) or 2))

        theme = self._resolve_theme()

        for i in range(num):
            pan = (i / (num - 1)) if num > 1 else 0.5
            side_gain = (left_gain * (1.0 - pan)) + (right_gain * pan)
            val = values[i] * side_gain
            cap_val = peak_caps[i] * side_gain if peak_caps_enabled else val
            norm = self._energy_norm(val, max_val)
            cap_norm = self._energy_norm(cap_val, max_val)
            half_h = norm * (mid_y - 3 - (center_gap if center_mode else 0))
            cap_h = cap_norm * (mid_y - 3 - (center_gap if center_mode else 0))
            if half_h < 0.5:
                continue

            x = gap + int(i * (bar_w + gap))
            top_y = int(mid_y - half_h - (center_gap if center_mode else 0))
            full_h = int(half_h * 2)
            if center_mode:
                full_h = int(half_h)

            # Get color from theme
            r, g, b = bar_color(theme, norm, i, num)

            # Glow
            if self.cfg.get("glow", True) and norm > 0.1:
                glow_r = int(bar_w * 2.5)
                cx = x + bar_w / 2
                grad = QRadialGradient(QPointF(cx, mid_y), glow_r)
                glow_alpha = int((norm * 46 + self._bg_pulse * 16) * self._glow_quality_scale)
                grad.setColorAt(0.0, QColor(r, g, b, glow_alpha))
                grad.setColorAt(1.0, QColor(r, g, b, 0))
                p.setBrush(QBrush(grad))
                p.drawEllipse(QPointF(cx, mid_y), glow_r, half_h * 0.8)

            # Actual mirrored bar
            if center_mode:
                p.setBrush(self._bar_fill_brush(theme, norm, i, num, top_y, int(full_h)))
                p.drawRoundedRect(x, top_y, int(bar_w), full_h, 2, 2)
                bottom_y = int(mid_y + center_gap)
                p.setBrush(self._bar_fill_brush(theme, norm, i, num, bottom_y, int(full_h)))
                p.drawRoundedRect(x, bottom_y, int(bar_w), full_h, 2, 2)

                if peak_caps_enabled:
                    cap_alpha = int(140 + cap_norm * 90)
                    peak = theme["peak"]
                    p.setBrush(QBrush(QColor(peak[0], peak[1], peak[2], cap_alpha)))
                    p.drawRoundedRect(x, int(mid_y - cap_h - center_gap - 2), int(bar_w), 2, 1, 1)
                    p.drawRoundedRect(x, int(mid_y + cap_h + center_gap), int(bar_w), 2, 1, 1)
            else:
                p.setBrush(self._bar_fill_brush(theme, norm, i, num, top_y, int(full_h)))
                p.drawRoundedRect(x, top_y, int(bar_w), full_h, 2, 2)

                if peak_caps_enabled:
                    cap_alpha = int(140 + cap_norm * 90)
                    peak = theme["peak"]
                    p.setBrush(QBrush(QColor(peak[0], peak[1], peak[2], cap_alpha)))
                    p.drawRoundedRect(x, int(mid_y - cap_h - 2), int(bar_w), 2, 1, 1)
                    p.drawRoundedRect(x, int(mid_y + cap_h), int(bar_w), 2, 1, 1)

    def _paint_dot_matrix(self, p: QPainter, w: int, h: int):
        """LED-like dot columns with optional peak-dot accent."""
        p.setPen(Qt.PenStyle.NoPen)

        values, peak_caps = self._sampled_bins()
        num = len(values)
        if num <= 0:
            return

        peak_caps_enabled = bool(self.cfg.get("peak_caps_enabled", True))
        max_val = self._display_max_value(values, peak_caps if peak_caps_enabled else None)

        left_gain, right_gain = self._stereo_split_gains()
        theme = self._resolve_theme()

        cols_gap = 2
        col_w = max(2, int((w - cols_gap * (num + 1)) / max(1, num)))
        dot_h = 3
        dot_gap = 2
        max_dots = max(3, int((h - 6) / (dot_h + dot_gap)))

        for i in range(num):
            pan = (i / (num - 1)) if num > 1 else 0.5
            side_gain = (left_gain * (1.0 - pan)) + (right_gain * pan)
            val = values[i] * side_gain
            cap_val = peak_caps[i] * side_gain if peak_caps_enabled else val
            norm = self._energy_norm(val, max_val)
            cap_norm = self._energy_norm(cap_val, max_val)

            lit = int(round(norm * max_dots))
            cap_idx = int(round(cap_norm * max_dots))
            x = cols_gap + int(i * (col_w + cols_gap))

            for j in range(max_dots):
                y = h - 3 - ((j + 1) * (dot_h + dot_gap))
                active = j < lit
                dot_norm = (j + 1) / max(1, max_dots)
                r, g, b = bar_color(theme, dot_norm, i, num)

                if active:
                    alpha = int(120 + dot_norm * 120)
                    p.setBrush(QBrush(QColor(r, g, b, alpha)))
                else:
                    p.setBrush(QBrush(QColor(r, g, b, 16)))

                p.drawRoundedRect(x, y, col_w, dot_h, 1, 1)

            if peak_caps_enabled and cap_idx > 0:
                y = h - 3 - (min(max_dots, cap_idx) * (dot_h + dot_gap))
                peak = theme["peak"]
                p.setBrush(QBrush(QColor(peak[0], peak[1], peak[2], 230)))
                p.drawRoundedRect(x, y, col_w, dot_h, 1, 1)

    def _paint_oscilloscope(self, p: QPainter, w: int, h: int):
        """Neon oscilloscope around the vertical center line with glow trail."""
        values, _peak_caps = self._sampled_bins()
        num = len(values)
        if num <= 0:
            return

        max_val = self._display_max_value(values)
        left_gain, right_gain = self._stereo_split_gains()
        theme = self._resolve_theme()
        br, bg, bb = theme["base"]
        pr, pg, pb = theme["peak"]
        gr, gg, gb = theme["glow"]
        gradient_mode = self.cfg.get("gradient_mode", "three_color")

        mid = h * 0.5
        amp = max(5.0, h * 0.42)

        points = []
        for i in range(num):
            pan = (i / (num - 1)) if num > 1 else 0.5
            side_gain = (left_gain * (1.0 - pan)) + (right_gain * pan)
            norm = self._energy_norm(values[i] * side_gain, max_val)
            centered = (norm - 0.5) * 2.0
            x = int(i * w / (num - 1)) if num > 1 else 0
            y = int(mid - centered * amp * 0.65)
            points.append(QPointF(x, y))

        if not points:
            return

        path = QPainterPath()
        path.moveTo(points[0])
        for i in range(1, len(points)):
            p0 = points[max(i - 1, 0)]
            p1 = points[i]
            ctrl_x = (p0.x() + p1.x()) / 2
            path.cubicTo(QPointF(ctrl_x, p0.y()), QPointF(ctrl_x, p1.y()), p1)

        if self.cfg.get("glow", True):
            glow_alpha = int((44 + self._bg_pulse * 26) * self._glow_quality_scale)
            glow_pen = QPen(QColor(gr, gg, gb, glow_alpha), 11)
            glow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(glow_pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)

        if gradient_mode == "off":
            line_pen = QPen(QColor(pr, pg, pb, 220), 2.6)
        else:
            line_grad = QLinearGradient(0, 0, w, 0)
            if gradient_mode == "two_color":
                line_grad.setColorAt(0.0, QColor(br, bg, bb, 205))
                line_grad.setColorAt(1.0, QColor(pr, pg, pb, 235))
            else:
                line_grad.setColorAt(0.0, QColor(br, bg, bb, 190))
                line_grad.setColorAt(0.5, QColor(gr, gg, gb, 232))
                line_grad.setColorAt(1.0, QColor(pr, pg, pb, 236))
            line_pen = QPen(QBrush(line_grad), 2.6)

        line_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(line_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

    def _paint_mirror_tunnel(self, p: QPainter, w: int, h: int):
        """Mirrored bars with center-perspective depth for tunnel-like motion."""
        p.setPen(Qt.PenStyle.NoPen)

        values, peak_caps = self._sampled_bins()
        num = len(values)
        if num <= 0:
            return

        peak_caps_enabled = bool(self.cfg.get("peak_caps_enabled", True))
        max_val = self._display_max_value(values, peak_caps if peak_caps_enabled else None)

        left_gain, right_gain = self._stereo_split_gains()
        theme = self._resolve_theme()

        gap = 2
        bar_w = max(2, (w - gap * (num + 1)) / num)
        center_x = w * 0.5
        center_gap = int(max(0, self.cfg.get("mirror_center_gap", 2) or 2))
        mid_y = h * 0.5

        for i in range(num):
            pan = (i / (num - 1)) if num > 1 else 0.5
            side_gain = (left_gain * (1.0 - pan)) + (right_gain * pan)
            val = values[i] * side_gain
            cap_val = peak_caps[i] * side_gain if peak_caps_enabled else val
            norm = self._energy_norm(val, max_val)
            cap_norm = self._energy_norm(cap_val, max_val)

            x = gap + int(i * (bar_w + gap))
            dist = abs((x + bar_w * 0.5) - center_x) / max(center_x, 1.0)
            depth_scale = 0.68 + (0.52 * (1.0 - dist))
            half_h = norm * (mid_y - 4 - center_gap) * depth_scale
            cap_h = cap_norm * (mid_y - 4 - center_gap) * depth_scale
            if half_h < 0.5:
                continue

            top_y = int(mid_y - center_gap - half_h)
            bottom_y = int(mid_y + center_gap)
            draw_h = int(half_h)

            p.setBrush(self._bar_fill_brush(theme, norm, i, num, top_y, max(1, draw_h)))
            p.drawRoundedRect(x, top_y, int(bar_w), max(1, draw_h), 2, 2)
            p.setBrush(self._bar_fill_brush(theme, norm, i, num, bottom_y, max(1, draw_h)))
            p.drawRoundedRect(x, bottom_y, int(bar_w), max(1, draw_h), 2, 2)

            if self.cfg.get("glow", True) and norm > 0.12:
                glow_r = int(bar_w * (1.9 + 0.8 * depth_scale))
                cx = x + bar_w / 2
                grad = QRadialGradient(QPointF(cx, mid_y), glow_r)
                glow_alpha = int((norm * 42 + self._bg_pulse * 18) * self._glow_quality_scale)
                r, g, b = bar_color(theme, norm, i, num)
                grad.setColorAt(0.0, QColor(r, g, b, glow_alpha))
                grad.setColorAt(1.0, QColor(r, g, b, 0))
                p.setBrush(QBrush(grad))
                p.drawEllipse(QPointF(cx, mid_y), glow_r, half_h * 0.78)

            if peak_caps_enabled:
                peak = theme["peak"]
                cap_alpha = int(130 + cap_norm * 95)
                p.setBrush(QBrush(QColor(peak[0], peak[1], peak[2], cap_alpha)))
                p.drawRoundedRect(x, int(mid_y - center_gap - cap_h - 2), int(bar_w), 2, 1, 1)
                p.drawRoundedRect(x, int(mid_y + center_gap + cap_h), int(bar_w), 2, 1, 1)

    def _paint_constellation(self, p: QPainter, w: int, h: int):
        """Draws nodes at frequency peaks and connects them with lines."""
        p.setBrush(Qt.BrushStyle.NoBrush)

        values, _peak_caps = self._sampled_bins()
        num = len(values)
        if num <= 0:
            return
        max_val = self._display_max_value(values)
        left_gain, right_gain = self._stereo_split_gains()

        theme = self._resolve_theme()
        br, bg, bb = theme["base"]
        pr, pg, pb = theme["peak"]
        gr, gg, gb = theme["glow"]

        points = []
        for i in range(num):
            pan = (i / (num - 1)) if num > 1 else 0.5
            side_gain = (left_gain * (1.0 - pan)) + (right_gain * pan)
            norm = self._energy_norm(values[i] * side_gain, max_val)
            x = int(i * w / (num - 1)) if num > 1 else w / 2
            y = int(h - norm * (h - 8) - 4)
            points.append(QPointF(x, y))

        if not points:
            return

        # Draw connecting lines
        line_pen = QPen(QColor(gr, gg, gb, 80), 1.2)
        line_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(line_pen)
        path = QPainterPath()
        path.moveTo(points[0])
        for i in range(1, len(points)):
            path.lineTo(points[i])
        p.drawPath(path)

        # Draw nodes (circles)
        p.setPen(Qt.PenStyle.NoPen)
        for i, pt in enumerate(points):
            pan = (i / (num - 1)) if num > 1 else 0.5
            side_gain = (left_gain * (1.0 - pan)) + (right_gain * pan)
            norm = self._energy_norm(values[i] * side_gain, max_val)
            r, g, b = bar_color(theme, norm, i, num)
            size = 1.5 + (norm * 2.5)

            if self.cfg.get("glow", True) and norm > 0.3:
                glow_grad = QRadialGradient(pt, size * 2.5)
                glow_alpha = int((norm * 60 + self._bg_pulse * 20) * self._glow_quality_scale)
                glow_grad.setColorAt(0.0, QColor(r, g, b, glow_alpha))
                glow_grad.setColorAt(1.0, QColor(r, g, b, 0))
                p.setBrush(QBrush(glow_grad))
                p.drawEllipse(pt, size * 2.5, size * 2.5)

            p.setBrush(QBrush(QColor(r, g, b, int(200 + norm * 55))))
            p.drawEllipse(pt, size, size)

    # ====================== CONFIG UPDATES ===========================

    def apply_config(self, cfg: dict):
        """Called when tray menu changes a setting."""
        self.cfg = cfg
        num = cfg.get("bar_count", 64)
        if len(self.fft_data) != num:
            self.fft_data = np.zeros(num)
            self.smoothed = np.zeros(num)
            self.peak_caps = np.zeros(num)
        # Re-position if width changed
        self.position_on_taskbar()
        # Update media button usage / geometry when config changes
        try:
            mcfg = cfg.get("media_controls", {}) or {}
            self._use_widget_buttons = bool(mcfg.get("use_widgets", True))
            if getattr(self, "_media_buttons", None):
                # recompute sizes and positions
                self._update_media_buttons_geometry()
                # enforce visibility according to overlay alpha
                if self._use_widget_buttons and getattr(self, "_media_overlay_alpha", 0.0) > 0.01:
                    for b in self._media_buttons.values():
                        b.show()
                    self._disable_click_through()
                else:
                    for b in self._media_buttons.values():
                        b.hide()
                    self._enable_click_through()
        except Exception:
            pass

    # ====================== OVERLAYS ==================================

    def _media_overlay_rect(self, w: int = None, h: int = None) -> QRect:
        """Compute the media overlay card rectangle (matches painting math).

        Returns a QRect in widget-local coordinates for the centered media card.
        """
        if w is None:
            w = self.width()
        if h is None:
            h = self.height()
        box_margin_x = 8
        box_w = max(120, w - (box_margin_x * 2))
        box_h = max(34, int(h * 0.78))
        box_x = int((w - box_w) / 2)
        box_y = int((h - box_h) / 2)
        return QRect(box_x, box_y, box_w, box_h)


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
        if not cover_bytes:
            self._media_cover_pixmap = None
            self._media_cover_scaled_pixmap = None
            self._media_cover_scaled_size = 0

        if cover_bytes and self._media_cover_pixmap is None:
            pix = QPixmap()
            if pix.loadFromData(cover_bytes):
                self._media_cover_pixmap = pix

        has_cover = bool(self._media_cover_pixmap and not self._media_cover_pixmap.isNull())

        show_cover_slot = True

        if has_cover:
            cover_rect_f = QRectF(float(cover_x), float(cover_y), float(cover_size), float(cover_size))
            clip_path = QPainterPath()
            clip_path.addRoundedRect(cover_rect_f, 5.0, 5.0)
            p.save()
            p.setClipPath(clip_path)
            if (
                self._media_cover_scaled_pixmap is None
                or self._media_cover_scaled_size != cover_size
            ):
                self._media_cover_scaled_pixmap = self._media_cover_pixmap.scaled(
                    cover_size,
                    cover_size,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._media_cover_scaled_size = cover_size

            scaled = self._media_cover_scaled_pixmap
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
        # Draw simple transport controls under the metadata (prev / play-pause / next)
        mcfg = self.cfg.get("media_controls", {}) or {}
        # If widget-based controls are enabled and paint fallback is disabled,
        # skip painting the buttons (widgets will be used instead).
        if self._use_widget_buttons and mcfg.get("use_widgets", False) and not mcfg.get("use_paint_fallback", False):
            self._media_button_rects = {}
        else:
            try:
                # Use the new painted control renderer (glassmorphism + hover/scale)
                self.draw_media_controls(p)
            except Exception:
                # Drawing of controls is best-effort; don't break overlay rendering.
                self._media_button_rects = {}


    def _activate_media_control(self, name: str):
        """Invoke the named media control on the attached MediaMonitor."""
        if not self.media_monitor:
            return
        # Prefer explicit API names if present on media_monitor; fall back
        # to the existing toggle/play methods for backward compatibility.
        try:
            self._invoke_media_action(name)
            # Keep the overlay visible briefly to provide feedback
            self._media_overlay_started_at = time.time()
        except Exception as e:
            print(f"[Visualizer] media control {name} failed: {e}")

    def _invoke_media_action(self, name: str):
        """Robustly invoke a transport action on the attached MediaMonitor.

        Tries canonical method names (play_pause) then falls back to
        existing toggle/play methods on MediaMonitor.
        """
        if not self.media_monitor:
            return
        mm = self.media_monitor
        try:
            if name == "prev":
                func = getattr(mm, "previous_track", None) or getattr(mm, "prev", None)
                if func:
                    func()
                    return
            elif name == "next":
                func = getattr(mm, "next_track", None) or getattr(mm, "skip", None)
                if func:
                    func()
                    return
            elif name == "play":
                # Try preferred API name 'play_pause' first, then 'toggle_play_pause'.
                func = getattr(mm, "play_pause", None) or getattr(mm, "toggle_play_pause", None) or getattr(mm, "play", None) or getattr(mm, "pause", None)
                if func:
                    func()
                    return
        except Exception:
            # As a last resort, try sending the toggle key via existing helper.
            try:
                if name == "prev":
                    mm.previous_track()
                elif name == "next":
                    mm.next_track()
                elif name == "play":
                    mm.toggle_play_pause()
            except Exception:
                raise

    # ---------------------- Painted control helpers -----------------
    def draw_media_controls(self, p: QPainter):
        """Paint modern glassmorphic media transport controls.

        This method draws three circular buttons centered horizontally inside
        the now-playing card, applies hover glow and scale transforms, and
        updates self.controls_rects for hit-testing.
        """
        alpha = max(0.0, min(1.0, getattr(self, "_media_overlay_alpha", 1.0)))
        box = self._media_overlay_rect()
        box_x, box_y, box_w, box_h = box.x(), box.y(), box.width(), box.height()

        pad_x = 10
        cover_gap = 8
        cover_size = max(20, min(box_h - 10, int(box_h * 0.75)))

        # Reserve a left cover slot if media cover area exists in this overlay
        show_cover_slot = True
        media = getattr(self, "media_monitor", None)
        cover_bytes = None
        if media and getattr(media, "info", None):
            cover_bytes = getattr(media.info, "cover_bytes", None)
        has_cover = bool(self._media_cover_pixmap and not self._media_cover_pixmap.isNull()) or bool(cover_bytes)

        left_offset = (cover_size + cover_gap) if show_cover_slot else 0

        # Button sizing: play button slightly larger
        small_btn = int(max(22, min(44, box_h * 0.18)))
        play_btn = int(small_btn * 1.16)
        btn_spacing = int(max(8, small_btn * 0.35))

        total_w = small_btn + play_btn + small_btn + (2 * btn_spacing)
        start_x = int(box_x + (box_w - total_w) / 2)
        btn_y = int(box_y + box_h - pad_x - play_btn - 8)

        prev_rect = QRect(start_x, btn_y + (play_btn - small_btn) // 2, small_btn, small_btn)
        play_rect = QRect(start_x + small_btn + btn_spacing, btn_y, play_btn, play_btn)
        next_rect = QRect(start_x + small_btn + btn_spacing + play_btn + btn_spacing, btn_y + (play_btn - small_btn) // 2, small_btn, small_btn)

        # Expose hit-rects for polling / event handlers
        self.controls_rects = {"prev": prev_rect, "play": play_rect, "next": next_rect}
        # Keep backward-compatible name used elsewhere
        self._media_button_rects = self.controls_rects

        # Glassy background slab behind the controls (subtle)
        ctrl_bg_w = total_w + 22
        ctrl_bg_h = play_btn + 14
        ctrl_bg_x = int(box_x + (box_w - ctrl_bg_w) / 2)
        ctrl_bg_y = int(btn_y - 6)

        radius = 14
        path = QPainterPath()
        path.addRoundedRect(QRectF(ctrl_bg_x, ctrl_bg_y, ctrl_bg_w, ctrl_bg_h), radius, radius)

        base_bg = QColor(28, 30, 32, int(140 * alpha))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(base_bg))
        p.drawPath(path)

        # Frosted inner sheen
        sheen = QLinearGradient(ctrl_bg_x, ctrl_bg_y, ctrl_bg_x + ctrl_bg_w, ctrl_bg_y + ctrl_bg_h)
        sheen.setColorAt(0.0, QColor(255, 255, 255, int(10 * alpha)))
        sheen.setColorAt(1.0, QColor(255, 255, 255, int(4 * alpha)))
        p.setBrush(QBrush(sheen))
        p.drawPath(path)

        # Theme glow color for hover accents
        theme = self._resolve_theme()
        gr, gg, gb = theme.get("glow", (90, 200, 255))

        # Draw each control with scale transform and hover glow
        for name, rect in self.controls_rects.items():
            scale = float(self.button_scale.get(name, 1.0))
            cx = rect.x() + rect.width() / 2.0
            cy = rect.y() + rect.height() / 2.0

            p.save()
            p.translate(cx, cy)
            p.scale(scale, scale)
            p.translate(-cx, -cy)

            # Background circle
            bg_alpha = int((28 if self.hovered_button == name else 18) * alpha)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(255, 255, 255, bg_alpha)))
            p.drawEllipse(rect.x(), rect.y(), rect.width(), rect.height())

            # Hover glow (radial)
            if self.hovered_button == name:
                glow_alpha = int(88 * alpha)
                rg = QRadialGradient(QPointF(cx, cy), max(rect.width(), rect.height()) * 1.6)
                rg.setColorAt(0.0, QColor(gr, gg, gb, int(glow_alpha * 0.9)))
                rg.setColorAt(0.5, QColor(gr, gg, gb, int(glow_alpha * 0.35)))
                rg.setColorAt(1.0, QColor(gr, gg, gb, 0))
                p.setBrush(QBrush(rg))
                p.drawEllipse(cx - rect.width() * 0.9, cy - rect.height() * 0.9, rect.width() * 1.8, rect.height() * 1.8)

            # Icon
            icon_font = QFont("Segoe UI Symbol", max(10, int(rect.width() * 0.5)))
            p.setFont(icon_font)
            p.setPen(QPen(QColor(240, 240, 240, int(240 * alpha))))

            if name == "prev":
                ch = "⏮"
            elif name == "next":
                ch = "⏭"
            else:
                # Determine playback state (best-effort): prefer explicit state on media_monitor
                playing = False
                if getattr(self, "media_monitor", None):
                    mm = self.media_monitor
                    # common attribute checks
                    playing_attr = getattr(mm, "is_playing", None)
                    if playing_attr is not None:
                        playing = bool(playing_attr)
                    else:
                        # Fallback: infer from recent FFT updates (non-blocking)
                        try:
                            playing = (time.time() - self._last_fft_update_time) < 0.7 and float(np.max(self.smoothed)) > 0.02
                        except Exception:
                            playing = False
                ch = "⏸" if playing else "▶"

            p.drawText(rect.x(), rect.y(), rect.width(), rect.height(), Qt.AlignmentFlag.AlignCenter, ch)
            p.restore()

    def update_hover_state(self, mouse_pos):
        """Update hovered button given a widget-local QPoint or QPointF.

        Updates target scales and cursor state.
        """
        try:
            pt = mouse_pos
            new = None
            for name, rect in (getattr(self, "controls_rects", {}) or {}).items():
                if rect.contains(pt):
                    new = name
                    break

            if new != self.hovered_button:
                self.hovered_button = new
                for n in ("prev", "play", "next"):
                    self._button_target[n] = 1.1 if n == new else 1.0
                if new:
                    QApplication.setOverrideCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                else:
                    try:
                        QApplication.restoreOverrideCursor()
                    except Exception:
                        pass
                self.update()
        except Exception:
            pass

    def handle_media_click(self, x: int, y: int):
        """Handle a left-click at widget-local coordinates, dispatch to media action.

        Returns True when a control was activated.
        """
        try:
            pt = QPointF(float(x), float(y))
            merged = {}
            merged.update(getattr(self, "_media_button_rects", {}) or {})
            merged.update(getattr(self, "controls_rects", {}) or {})
            for name, rect in merged.items():
                if rect.contains(QPointF(pt.x(), pt.y()).toPoint()):
                    # press animation: briefly scale down then bounce back
                    try:
                        self._button_target[name] = 0.92
                        QTimer.singleShot(120, lambda nm=name: self._button_target.update({nm: 1.0}))
                    except Exception:
                        pass
                    # Invoke action (robust)
                    try:
                        self._invoke_media_action(name)
                    except Exception:
                        # fallback to old activator
                        try:
                            self._activate_media_control(name)
                        except Exception:
                            pass
                    # keep overlay visible so user gets feedback
                    self._media_overlay_started_at = time.time()
                    return True
        except Exception:
            pass
        return False

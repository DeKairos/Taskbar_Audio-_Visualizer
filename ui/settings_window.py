"""
ui/settings_window.py — Fluent 2-style settings window for the Audio Visualizer.

Replaces the tray-menu-only configuration with a proper windowed settings UI.
Sidebar navigation: General | Visualizer | Themes | Audio | Media | About
"""
import sys
import time
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QFrame, QPushButton, QComboBox, QSlider, QCheckBox, QSpinBox,
    QColorDialog, QGroupBox, QGridLayout, QSizePolicy, QStackedWidget,
    QApplication,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QBrush, QPen, QPainterPath
from ui.fluent_theme import (
    RADIUS_CARD, RADIUS_MEDIUM, SPACE_SM, SPACE_MD, SPACE_LG, SPACE_XL,
    FONT_FAMILY, FONT_SIZES, card_bg, card_border, text_primary, text_secondary,
    accent_color, qcolor_with_alpha_f, lerp_color,
)
from color_themes import THEMES, THEME_NAMES, THEME_DISPLAY


# ─── Sidebar Nav Button ────────────────────────────────────────────

class _NavButton(QPushButton):
    """Custom styled nav button for the sidebar."""
    def __init__(self, label: str, icon_text: str = "", parent=None):
        super().__init__(parent)
        self.setText(f"  {icon_text}  {label}" if icon_text else f"  {label}")
        self.setCheckable(True)
        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_style(False)

    def _update_style(self, active: bool):
        if active:
            bg = "rgba(255,255,255,10)"
            border = "rgba(255,255,255,16)"
        else:
            bg = "transparent"
            border = "transparent"
        self.setStyleSheet(f"""
            QPushButton {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 6px;
                color: rgba(255,255,255,230);
                font-family: {FONT_FAMILY}, Segoe UI;
                font-size: 13px;
                text-align: left;
                padding-left: 12px;
            }}
            QPushButton:hover {{
                background: rgba(255,255,255,6);
            }}
        """)


# ─── Section Header ────────────────────────────────────────────────

class _SectionHeader(QLabel):
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setStyleSheet(f"""
            QLabel {{
                color: rgba(255,255,255,210);
                font-family: {FONT_FAMILY}, Segoe UI;
                font-size: 16px;
                font-weight: 600;
                padding: 8px 0px;
            }}
        """)


# ─── Setting Row (label + control) ─────────────────────────────────

class _SettingRow(QFrame):
    def __init__(self, label: str, control: QWidget, description: str = "", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(2)

        row = QHBoxLayout()
        row.setSpacing(12)

        lbl = QLabel(label)
        lbl.setStyleSheet(f"""
            QLabel {{
                color: rgba(255,255,255,200);
                font-family: {FONT_FAMILY}, Segoe UI;
                font-size: 13px;
            }}
        """)
        lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row.addWidget(lbl)
        row.addWidget(control)
        layout.addLayout(row)

        if description:
            desc = QLabel(description)
            desc.setStyleSheet(f"""
                QLabel {{
                    color: rgba(255,255,255,120);
                    font-family: {FONT_FAMILY}, Segoe UI;
                    font-size: 11px;
                }}
            """)
            desc.setWordWrap(True)
            layout.addWidget(desc)


# ─── Styled Controls ───────────────────────────────────────────────

def _make_combo(items: list[str], current: str = None) -> QComboBox:
    cb = QComboBox()
    cb.addItems(items)
    if current and current in items:
        cb.setCurrentText(current)
    cb.setStyleSheet(f"""
        QComboBox {{
            background: rgba(255,255,255,10);
            border: 1px solid rgba(255,255,255,16);
            border-radius: 6px;
            padding: 4px 8px;
            color: white;
            font-family: {FONT_FAMILY}, Segoe UI;
            font-size: 12px;
            min-width: 100px;
        }}
        QComboBox::drop-down {{
            border: none;
        }}
        QComboBox QAbstractItemView {{
            background: #2d2d2d;
            color: white;
            selection-background-color: rgba(255,255,255,20);
        }}
    """)
    return cb


def _make_slider(min_v: int, max_v: int, current: int, suffix: str = "") -> QSlider:
    s = QSlider(Qt.Orientation.Horizontal)
    s.setRange(min_v, max_v)
    s.setValue(current)
    s.setFixedWidth(140)
    s.setStyleSheet("""
        QSlider::groove:horizontal {
            background: rgba(255,255,255,20);
            height: 4px;
            border-radius: 2px;
        }
        QSlider::handle:horizontal {
            background: white;
            width: 14px;
            height: 14px;
            margin: -5px 0;
            border-radius: 7px;
        }
        QSlider::sub-page:horizontal {
            background: rgba(120,200,255,180);
            border-radius: 2px;
        }
    """)
    return s


def _make_checkbox(checked: bool) -> QCheckBox:
    cb = QCheckBox()
    cb.setChecked(checked)
    cb.setStyleSheet("""
        QCheckBox::indicator {
            width: 18px;
            height: 18px;
            border-radius: 4px;
            border: 1px solid rgba(255,255,255,30);
            background: rgba(255,255,255,10);
        }
        QCheckBox::indicator:checked {
            background: rgba(100,180,255,200);
            border: 1px solid rgba(100,180,255,100);
        }
    """)
    return cb


def _make_spinbox(min_v: int, max_v: int, current: int) -> QSpinBox:
    sb = QSpinBox()
    sb.setRange(min_v, max_v)
    sb.setValue(current)
    sb.setStyleSheet(f"""
        QSpinBox {{
            background: rgba(255,255,255,10);
            border: 1px solid rgba(255,255,255,16);
            border-radius: 6px;
            padding: 4px 8px;
            color: white;
            font-family: {FONT_FAMILY}, Segoe UI;
            font-size: 12px;
            min-width: 60px;
        }}
    """)
    return sb


# ─── Settings Pages ────────────────────────────────────────────────

class _GeneralPage(QWidget):
    config_changed = pyqtSignal(dict)

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_MD)

        layout.addWidget(_SectionHeader("General"))

        # Auto-hide
        self.auto_hide_cb = _make_checkbox(cfg.get("auto_hide", True))
        layout.addWidget(_SettingRow(
            "Auto-Hide", self.auto_hide_cb,
            "Hide the visualizer when no audio is playing."
        ))
        self.auto_hide_cb.toggled.connect(self._on_change)

        # Auto-hide timeout
        self.timeout_slider = _make_slider(1, 30, int(cfg.get("auto_hide_timeout", 5)))
        layout.addWidget(_SettingRow(
            "Auto-Hide Timeout", self.timeout_slider,
            "Seconds of silence before hiding."
        ))
        self.timeout_slider.valueChanged.connect(self._on_change)

        # Start with Windows
        self.startup_cb = _make_checkbox(cfg.get("startup", False))
        layout.addWidget(_SettingRow(
            "Start with Windows", self.startup_cb,
            "Launch automatically when you log in."
        ))
        self.startup_cb.toggled.connect(self._on_change)

        # Dynamic Quality
        self.dynamic_q_cb = _make_checkbox(cfg.get("dynamic_quality", True))
        layout.addWidget(_SettingRow(
            "Dynamic Quality", self.dynamic_q_cb,
            "Automatically reduce effects when frame rate drops."
        ))
        self.dynamic_q_cb.toggled.connect(self._on_change)

        # Auto Update Check
        self.update_cb = _make_checkbox(cfg.get("auto_update_check", True))
        layout.addWidget(_SettingRow(
            "Auto Update Check", self.update_cb,
            "Check for new versions on startup."
        ))
        self.update_cb.toggled.connect(self._on_change)

        layout.addWidget(_SectionHeader("Taskbar"))

        # Visualizer height
        self.height_slider = _make_slider(20, 80, cfg.get("visualizer_height", 40))
        layout.addWidget(_SettingRow(
            "Visualizer Height (px)", self.height_slider,
            "Height of the visualizer strip in pixels."
        ))
        self.height_slider.valueChanged.connect(self._on_change)

        # Taskbar auto-hide behavior
        self.taskbar_behavior_combo = _make_combo(
            ["Follow taskbar", "Hide when hidden", "Always show"],
            {"follow": "Follow taskbar", "hide": "Hide when hidden", "always": "Always show"}.get(
                cfg.get("taskbar_auto_hide_behavior", "follow"), "Follow taskbar"
            )
        )
        layout.addWidget(_SettingRow(
            "When Taskbar Auto-Hides", self.taskbar_behavior_combo,
            "Choose how the visualizer behaves when the taskbar is auto-hidden."
        ))
        self.taskbar_behavior_combo.currentIndexChanged.connect(self._on_change)

        # Monitor selector
        monitor_items = ["Primary Monitor"]
        try:
            from ui.monitor_manager import MonitorManager
            mm = MonitorManager()
            monitors = mm.get_monitors()
            if len(monitors) > 1:
                monitor_items = [f"Monitor {i+1}" for i in range(len(monitors))]
        except Exception:
            pass

        current_monitor = cfg.get("visualizer_monitor", 0)
        current_monitor_text = monitor_items[0] if current_monitor == 0 else f"Monitor {current_monitor+1}" if current_monitor < len(monitor_items) else monitor_items[0]
        self.monitor_combo = _make_combo(monitor_items, current_monitor_text)
        layout.addWidget(_SettingRow(
            "Display Monitor", self.monitor_combo,
            "Which monitor to show the visualizer on."
        ))
        self.monitor_combo.currentIndexChanged.connect(self._on_change)

        layout.addStretch()

    def _on_change(self, *args):
        self.cfg["auto_hide"] = self.auto_hide_cb.isChecked()
        self.cfg["auto_hide_timeout"] = float(self.timeout_slider.value())
        self.cfg["startup"] = self.startup_cb.isChecked()
        self.cfg["dynamic_quality"] = self.dynamic_q_cb.isChecked()
        self.cfg["auto_update_check"] = self.update_cb.isChecked()
        self.cfg["visualizer_height"] = self.height_slider.value()
        behavior_map = {"Follow taskbar": "follow", "Hide when hidden": "hide", "Always show": "always"}
        self.cfg["taskbar_auto_hide_behavior"] = behavior_map.get(self.taskbar_behavior_combo.currentText(), "follow")
        monitor_idx = self.monitor_combo.currentIndex()
        self.cfg["visualizer_monitor"] = monitor_idx
        self.config_changed.emit(self.cfg)


class _VisualizerPage(QWidget):
    config_changed = pyqtSignal(dict)

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_MD)

        layout.addWidget(_SectionHeader("Visualizer"))

        # Mode selector
        from modes import list_modes
        mode_items = []
        self._mode_ids = []
        for m in list_modes():
            mode_items.append(m.get("label", m["id"]))
            self._mode_ids.append(m["id"])

        current_mode = cfg.get("mode", "bars")
        current_label = ""
        for m in list_modes():
            if m["id"] == current_mode:
                current_label = m.get("label", current_mode)
                break

        self.mode_combo = _make_combo(mode_items, current_label)
        layout.addWidget(_SettingRow(
            "Visualization Mode", self.mode_combo,
            "Choose how audio is displayed."
        ))
        self.mode_combo.currentIndexChanged.connect(self._on_mode_change)

        # Bar Count
        self.bar_count_slider = _make_slider(8, 128, cfg.get("bar_count", 64))
        layout.addWidget(_SettingRow(
            "Bar Count", self.bar_count_slider,
            "Number of frequency bars."
        ))
        self.bar_count_slider.valueChanged.connect(self._on_change)

        # Width %
        self.width_slider = _make_slider(10, 100, cfg.get("width_percent", 40))
        layout.addWidget(_SettingRow(
            "Width %", self.width_slider,
            "Percentage of taskbar width the visualizer occupies."
        ))
        self.width_slider.valueChanged.connect(self._on_change)

        # Width Mode
        width_mode = cfg.get("width_mode", "auto")
        width_mode_text = {"auto": "Auto (empty space)", "percentage": "Percentage", "fixed": "Fixed pixels"}.get(width_mode, "Auto (empty space)")
        self.width_mode_combo = _make_combo(["Auto (empty space)", "Percentage", "Fixed pixels"], width_mode_text)
        layout.addWidget(_SettingRow(
            "Width Mode", self.width_mode_combo,
            "Auto: detect empty space. Percentage: % of taskbar. Fixed: exact pixels."
        ))
        self.width_mode_combo.currentIndexChanged.connect(self._on_change)

        # Alignment Hint
        alignment_hint = cfg.get("alignment_hint", "left")
        alignment_text = {"left": "Left", "center": "Center"}.get(alignment_hint, "Left")
        self.alignment_combo = _make_combo(["Left", "Center"], alignment_text)
        layout.addWidget(_SettingRow(
            "Alignment", self.alignment_combo,
            "Position of the visualizer within the taskbar area."
        ))
        self.alignment_combo.currentIndexChanged.connect(self._on_change)

        # Sensitivity
        self.sens_combo = _make_combo(["Low", "Medium", "High"],
            {0.5: "Low", 1.0: "Medium", 2.0: "High"}.get(cfg.get("sensitivity", 1.0), "Medium"))
        layout.addWidget(_SettingRow("Sensitivity", self.sens_combo))
        self.sens_combo.currentIndexChanged.connect(self._on_change)

        # Toggles
        self.glow_cb = _make_checkbox(cfg.get("glow", True))
        layout.addWidget(_SettingRow("Glow Effect", self.glow_cb, "Adds soft halo around bars."))
        self.glow_cb.toggled.connect(self._on_change)

        self.beat_cb = _make_checkbox(cfg.get("beat_flash", True))
        layout.addWidget(_SettingRow("Beat Pulse", self.beat_cb, "Background pulses to the beat."))
        self.beat_cb.toggled.connect(self._on_change)

        self.peak_cb = _make_checkbox(cfg.get("peak_caps_enabled", True))
        layout.addWidget(_SettingRow("Peak Caps", self.peak_cb, "Shows a cap at the highest point."))
        self.peak_cb.toggled.connect(self._on_change)

        layout.addStretch()

    def _on_mode_change(self, idx):
        if 0 <= idx < len(self._mode_ids):
            self.cfg["mode"] = self._mode_ids[idx]
            self.config_changed.emit(self.cfg)

    def _on_change(self, *args):
        self.cfg["bar_count"] = self.bar_count_slider.value()
        self.cfg["width_percent"] = self.width_slider.value()
        width_mode_map = {"Auto (empty space)": "auto", "Percentage": "percentage", "Fixed pixels": "fixed"}
        self.cfg["width_mode"] = width_mode_map.get(self.width_mode_combo.currentText(), "auto")
        alignment_map = {"Left": "left", "Center": "center"}
        self.cfg["alignment_hint"] = alignment_map.get(self.alignment_combo.currentText(), "left")
        sens_map = {"Low": 0.5, "Medium": 1.0, "High": 2.0}
        self.cfg["sensitivity"] = sens_map.get(self.sens_combo.currentText(), 1.0)
        self.cfg["glow"] = self.glow_cb.isChecked()
        self.cfg["beat_flash"] = self.beat_cb.isChecked()
        self.cfg["peak_caps_enabled"] = self.peak_cb.isChecked()
        self.config_changed.emit(self.cfg)


class _ThemesPage(QWidget):
    config_changed = pyqtSignal(dict)

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_MD)

        layout.addWidget(_SectionHeader("Themes"))

        # Theme selector
        theme_items = [THEME_DISPLAY.get(t, t) for t in THEME_NAMES]
        current = THEME_DISPLAY.get(cfg.get("theme", "cyan"), "Cyan")
        self.theme_combo = _make_combo(theme_items, current)
        layout.addWidget(_SettingRow("Color Theme", self.theme_combo))
        self.theme_combo.currentIndexChanged.connect(self._on_theme_change)

        # Gradient mode
        self.grad_combo = _make_combo(["Off", "2-Color", "3-Color"],
            {"off": "Off", "two_color": "2-Color", "three_color": "3-Color"}.get(cfg.get("gradient_mode", "off"), "Off"))
        layout.addWidget(_SettingRow("Gradient Mode", self.grad_combo,
            "Adds color gradient transitions across bars."))
        self.grad_combo.currentIndexChanged.connect(self._on_gradient_change)

        # Low end boost
        self.boost_slider = _make_slider(80, 200, int(cfg.get("low_end_boost", 1.35) * 100))
        layout.addWidget(_SettingRow("Bass Boost", self.boost_slider,
            "Emphasize low frequencies (100 = default)."))
        self.boost_slider.valueChanged.connect(self._on_change)

        # Peak hold decay
        self.decay_slider = _make_slider(10, 100, int(cfg.get("peak_hold_decay", 0.045) * 1000))
        layout.addWidget(_SettingRow("Peak Decay Speed", self.decay_slider,
            "How quickly peak caps fall. Lower = slower."))
        self.decay_slider.valueChanged.connect(self._on_change)

        # Custom theme color picker section
        layout.addWidget(_SectionHeader("Custom Theme"))
        color_row = QHBoxLayout()
        color_row.setSpacing(SPACE_SM)

        for label, key in [("Base", "base"), ("Peak", "peak"), ("Glow", "glow")]:
            btn = QPushButton(label)
            btn.setFixedSize(70, 32)
            theme = THEMES.get(cfg.get("theme", "cyan"), THEMES["cyan"])
            c = theme.get(key, (100, 100, 100))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: rgb({c[0]},{c[1]},{c[2]});
                    border: 1px solid rgba(255,255,255,40);
                    border-radius: 6px;
                    color: white;
                    font-family: {FONT_FAMILY}, Segoe UI;
                    font-size: 11px;
                }}
            """)
            btn.clicked.connect(lambda checked, k=key, b=btn: self._pick_color(k, b))
            color_row.addWidget(btn)
        color_row.addStretch()
        layout.addLayout(color_row)

        layout.addStretch()

    def _on_theme_change(self, idx):
        if 0 <= idx < len(THEME_NAMES):
            self.cfg["theme"] = THEME_NAMES[idx]
            self.config_changed.emit(self.cfg)

    def _on_gradient_change(self, idx):
        modes = ["off", "two_color", "three_color"]
        if 0 <= idx < len(modes):
            self.cfg["gradient_mode"] = modes[idx]
            self.config_changed.emit(self.cfg)

    def _on_change(self, *args):
        self.cfg["low_end_boost"] = self.boost_slider.value() / 100.0
        self.cfg["peak_hold_decay"] = self.decay_slider.value() / 1000.0
        self.config_changed.emit(self.cfg)

    def _pick_color(self, key: str, btn: QPushButton):
        color = QColorDialog.getColor(parent=self)
        if color.isValid():
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: rgb({color.red()},{color.green()},{color.blue()});
                    border: 1px solid rgba(255,255,255,40);
                    border-radius: 6px;
                    color: white;
                    font-family: {FONT_FAMILY}, Segoe UI;
                    font-size: 11px;
                }}
            """)
            # Store custom theme override
            custom = self.cfg.get("custom_theme", {})
            custom[key] = (color.red(), color.green(), color.blue())
            self.cfg["custom_theme"] = custom
            self.cfg["theme"] = "custom"
            self.config_changed.emit(self.cfg)


class _AudioPage(QWidget):
    config_changed = pyqtSignal(dict)

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_MD)

        layout.addWidget(_SectionHeader("Audio"))

        # Input source
        self.input_combo = _make_combo(["System Audio (Loopback)", "Microphone"],
            "System Audio (Loopback)" if not cfg.get("use_microphone", False) else "Microphone")
        layout.addWidget(_SettingRow("Input Source", self.input_combo,
            "Choose between system audio capture or microphone input."))
        self.input_combo.currentIndexChanged.connect(self._on_change)

        # FFT Size
        self.fft_combo = _make_combo(["2048", "4096", "8192"],
                                     str(cfg.get("fft_size", 2048)))
        layout.addWidget(_SettingRow("FFT Size", self.fft_combo,
            "Larger = finer frequency resolution, more latency."))
        self.fft_combo.currentIndexChanged.connect(self._on_change)

        # Frequency range
        self.freq_min_slider = _make_slider(20, 200, cfg.get("freq_min", 40))
        layout.addWidget(_SettingRow("Min Frequency (Hz)", self.freq_min_slider))
        self.freq_min_slider.valueChanged.connect(self._on_change)

        self.freq_max_slider = _make_slider(4000, 20000, cfg.get("freq_max", 16000))
        layout.addWidget(_SettingRow("Max Frequency (Hz)", self.freq_max_slider))
        self.freq_max_slider.valueChanged.connect(self._on_change)

        # Band isolation
        layout.addWidget(_SectionHeader("Band Isolation"))
        self.bass_cb = _make_checkbox(cfg.get("isolate_bass", False))
        layout.addWidget(_SettingRow("Bass Only", self.bass_cb,
            "Show only low-frequency content (useful for DJ practice)."))
        self.bass_cb.toggled.connect(self._on_change)

        layout.addStretch()

    def _on_change(self, *args):
        self.cfg["use_microphone"] = self.input_combo.currentIndex() == 1
        self.cfg["fft_size"] = int(self.fft_combo.currentText())
        self.cfg["freq_min"] = self.freq_min_slider.value()
        self.cfg["freq_max"] = self.freq_max_slider.value()
        self.cfg["isolate_bass"] = self.bass_cb.isChecked()
        self.config_changed.emit(self.cfg)


class _MediaPage(QWidget):
    config_changed = pyqtSignal(dict)

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        mcfg = cfg.get("media_controls", {})
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_MD)

        layout.addWidget(_SectionHeader("Media Overlay"))

        # Show on track change
        self.show_overlay_cb = _make_checkbox(cfg.get("show_media_overlay", True))
        layout.addWidget(_SettingRow("Show on Track Change", self.show_overlay_cb,
            "Display now-playing info when a new track starts."))
        self.show_overlay_cb.toggled.connect(self._on_change)

        # Overlay duration
        self.duration_slider = _make_slider(1, 10, int(cfg.get("media_overlay_duration", 3.5)))
        layout.addWidget(_SettingRow("Overlay Duration (s)", self.duration_slider,
            "How long the now-playing card stays visible."))
        self.duration_slider.valueChanged.connect(self._on_change)

        # Widget controls
        self.widget_cb = _make_checkbox(mcfg.get("use_widgets", True))
        layout.addWidget(_SettingRow("Widget Controls", self.widget_cb,
            "Show media transport buttons as interactive widgets."))
        self.widget_cb.toggled.connect(self._on_change)

        # Position
        self.pos_combo = _make_combo(["Left", "Center", "Right"],
            mcfg.get("position", "center").capitalize())
        layout.addWidget(_SettingRow("Controls Position", self.pos_combo))
        self.pos_combo.currentIndexChanged.connect(self._on_change)

        # Button size
        self.size_slider = _make_slider(20, 60, mcfg.get("size", 36))
        layout.addWidget(_SettingRow("Button Size", self.size_slider))
        self.size_slider.valueChanged.connect(self._on_change)

        layout.addStretch()

    def _on_change(self, *args):
        self.cfg["show_media_overlay"] = self.show_overlay_cb.isChecked()
        self.cfg["media_overlay_duration"] = float(self.duration_slider.value())
        mcfg = self.cfg.get("media_controls", {})
        mcfg["use_widgets"] = self.widget_cb.isChecked()
        mcfg["position"] = self.pos_combo.currentText().lower()
        mcfg["size"] = self.size_slider.value()
        self.cfg["media_controls"] = mcfg
        self.config_changed.emit(self.cfg)


class _AboutPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_MD)

        layout.addWidget(_SectionHeader("About"))

        info = QLabel(
            "Audio Visualizer\n"
            "Version 2.0 (Fluent Edition)\n\n"
            "A taskbar audio visualizer with Fluent 2 design,\n"
            "media integration, and multiple visualization modes.\n\n"
            "Built with PyQt6, NumPy, and SoundCard.\n"
            "Inspired by FluentFlyout."
        )
        info.setStyleSheet(f"""
            QLabel {{
                color: rgba(255,255,255,180);
                font-family: {FONT_FAMILY}, Segoe UI;
                font-size: 13px;
                line-height: 1.6;
            }}
        """)
        info.setWordWrap(True)
        layout.addWidget(info)

        # Mode list
        layout.addWidget(_SectionHeader("Available Modes"))
        try:
            from modes import list_modes
            modes_text = "\n".join(
                f"  \u2022  {m.get('label', m['id'])} \u2014 {m.get('tooltip', '')}"
                for m in list_modes()
            )
        except Exception:
            modes_text = "  (unable to load mode list)"

        modes_lbl = QLabel(modes_text)
        modes_lbl.setStyleSheet(f"""
            QLabel {{
                color: rgba(255,255,255,150);
                font-family: {FONT_FAMILY}, Segoe UI;
                font-size: 12px;
            }}
        """)
        modes_lbl.setWordWrap(True)
        layout.addWidget(modes_lbl)
        layout.addStretch()


# ─── Main Settings Window ──────────────────────────────────────────

class SettingsWindow(QWidget):
    config_changed = pyqtSignal(dict)

    NAV_ITEMS = [
        ("General", "\u2699"),
        ("Visualizer", "\u25C6"),
        ("Themes", "\u2728"),
        ("Audio", "\u266B"),
        ("Media", "\u25B6"),
        ("About", "\u2139"),
    ]

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = dict(cfg)  # work on a copy
        self.setWindowTitle("Audio Visualizer \u2014 Settings")
        self.setMinimumSize(560, 420)
        self.resize(620, 480)

        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        self._build_ui()
        self._apply_window_style()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Card container
        card = QFrame()
        card.setObjectName("settingsCard")
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)
        root.addWidget(card)

        # ─── Sidebar ──────────────────────────────────────────────
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(160)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(SPACE_SM, SPACE_SM, SPACE_SM, SPACE_SM)
        sidebar_layout.setSpacing(2)

        # Title in sidebar
        title = QLabel("Settings")
        title.setStyleSheet(f"""
            QLabel {{
                color: rgba(255,255,255,220);
                font-family: {FONT_FAMILY}, Segoe UI;
                font-size: 15px;
                font-weight: 600;
                padding: 8px 8px 12px 8px;
            }}
        """)
        sidebar_layout.addWidget(title)

        self._nav_buttons = []
        for label, icon in self.NAV_ITEMS:
            btn = _NavButton(label, icon)
            btn.clicked.connect(lambda checked, l=label: self._navigate(l))
            sidebar_layout.addWidget(btn)
            self._nav_buttons.append(btn)

        sidebar_layout.addStretch()
        card_layout.addWidget(sidebar)

        # ─── Content Stack ────────────────────────────────────────
        self._stack = QStackedWidget()
        self._pages = {}

        general = _GeneralPage(self.cfg)
        general.config_changed.connect(self._on_config_changed)
        self._pages["General"] = general
        self._stack.addWidget(general)

        visualizer = _VisualizerPage(self.cfg)
        visualizer.config_changed.connect(self._on_config_changed)
        self._pages["Visualizer"] = visualizer
        self._stack.addWidget(visualizer)

        themes = _ThemesPage(self.cfg)
        themes.config_changed.connect(self._on_config_changed)
        self._pages["Themes"] = themes
        self._stack.addWidget(themes)

        audio = _AudioPage(self.cfg)
        audio.config_changed.connect(self._on_config_changed)
        self._pages["Audio"] = audio
        self._stack.addWidget(audio)

        media = _MediaPage(self.cfg)
        media.config_changed.connect(self._on_config_changed)
        self._pages["Media"] = media
        self._stack.addWidget(media)

        about = _AboutPage()
        self._pages["About"] = about
        self._stack.addWidget(about)

        card_layout.addWidget(self._stack)

        # Default to first nav item
        self._navigate("General")

    def _navigate(self, label: str):
        for i, btn in enumerate(self._nav_buttons):
            is_active = self.NAV_ITEMS[i][0] == label
            btn._update_style(is_active)
            btn.setChecked(is_active)
        if label in self._pages:
            self._stack.setCurrentWidget(self._pages[label])

    def _on_config_changed(self, cfg: dict):
        self.cfg = cfg
        self.config_changed.emit(cfg)

    def _apply_window_style(self):
        self.setStyleSheet(f"""
            QWidget#settingsCard {{
                background: #1e1e1e;
                border: 1px solid rgba(255,255,255,10);
                border-radius: {RADIUS_CARD}px;
            }}
            QWidget#sidebar {{
                background: rgba(255,255,255,4);
                border-right: 1px solid rgba(255,255,255,8);
                border-top-left-radius: {RADIUS_CARD}px;
                border-bottom-left-radius: {RADIUS_CARD}px;
            }}
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            SettingsWindow {{
                background: transparent;
            }}
        """)

    def showEvent(self, event):
        super().showEvent(event)
        # Center on screen
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + (geo.height() - self.height()) // 2
            self.move(x, y)

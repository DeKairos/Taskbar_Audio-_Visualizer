"""
tray_manager.py — System tray icon with controls for the visualizer.
"""
import sys
import os
import time
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QMessageBox
from PyQt6.QtGui import QIcon, QPixmap, QColor, QAction
from PyQt6.QtCore import QTimer
from config_manager import save_config, set_startup
from color_themes import THEME_NAMES, THEME_DISPLAY
from update_checker import check_for_updates
from app_resources import get_app_icon


class TrayManager(QSystemTrayIcon):
    def __init__(self, visualizer_window, audio_thread, config: dict):
        icon = get_app_icon()
        if icon.isNull():
            pixmap = QPixmap(32, 32)
            pixmap.fill(QColor(0, 180, 220))
            icon = QIcon(pixmap)

        super().__init__(icon)
        self.vis = visualizer_window
        self.audio_thread = audio_thread
        self.cfg = config

        self.setToolTip("Audio Visualizer")
        self._build_menu()
        self._schedule_auto_update_check()

    def _build_menu(self):
        menu = QMenu()

        # ─── Toggle Show/Hide ───
        self.toggle_action = QAction("Hide Visualizer", menu)
        self.toggle_action.triggered.connect(self._toggle_vis)
        menu.addAction(self.toggle_action)
        menu.addSeparator()

        # ─── Mode ───
        mode_menu = menu.addMenu("Mode")
        self.bars_action = QAction("○ Bars", mode_menu)
        self.wave_action = QAction("○ Waveform", mode_menu)
        self.mirror_action = QAction("○ Mirror", mode_menu)
        self.bars_action.triggered.connect(lambda: self._set_mode("bars"))
        self.wave_action.triggered.connect(lambda: self._set_mode("wave"))
        self.mirror_action.triggered.connect(lambda: self._set_mode("mirror"))
        mode_menu.addAction(self.bars_action)
        mode_menu.addAction(self.wave_action)
        mode_menu.addAction(self.mirror_action)
        self._update_mode_labels()

        # ─── Sensitivity ───
        sens_menu = menu.addMenu("Sensitivity")
        for label, val in [("Low", 0.5), ("Medium", 1.0), ("High", 2.0)]:
            prefix = "◉" if self.cfg.get("sensitivity", 1.0) == val else "○"
            action = QAction(f"{prefix} {label}", sens_menu)
            action.triggered.connect(lambda checked, v=val: self._set_sensitivity(v))
            sens_menu.addAction(action)

        # ─── Theme ───
        theme_menu = menu.addMenu("Theme")
        current_theme = self.cfg.get("theme", "cyan")
        for theme_id in THEME_NAMES:
            display_name = THEME_DISPLAY.get(theme_id, theme_id)
            prefix = "◉" if current_theme == theme_id else "○"
            action = QAction(f"{prefix} {display_name}", theme_menu)
            action.triggered.connect(lambda checked, t=theme_id: self._set_theme(t))
            theme_menu.addAction(action)

        menu.addSeparator()

        # ─── Toggles ───
        self.glow_action = QAction(
            "✓ Glow Effect" if self.cfg.get("glow", True) else "  Glow Effect", menu
        )
        self.glow_action.triggered.connect(self._toggle_glow)
        menu.addAction(self.glow_action)

        self.beat_action = QAction(
            "✓ Beat Flash" if self.cfg.get("beat_flash", True) else "  Beat Flash", menu
        )
        self.beat_action.triggered.connect(self._toggle_beat)
        menu.addAction(self.beat_action)

        self.autohide_action = QAction(
            "✓ Auto-Hide" if self.cfg.get("auto_hide", True) else "  Auto-Hide", menu
        )
        self.autohide_action.triggered.connect(self._toggle_autohide)
        menu.addAction(self.autohide_action)

        menu.addSeparator()

        # ─── Startup ───
        self.startup_action = QAction(
            "✓ Start with Windows" if self.cfg.get("startup", False)
            else "  Start with Windows", menu
        )
        self.startup_action.triggered.connect(self._toggle_startup)
        menu.addAction(self.startup_action)

        menu.addSeparator()

        # ─── Updates ───
        self.check_updates_action = QAction("Check for updates", menu)
        self.check_updates_action.triggered.connect(self._check_for_updates)
        menu.addAction(self.check_updates_action)

        menu.addSeparator()

        # ─── Quit ───
        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)

        self.setContextMenu(menu)

    # ─── Actions ────────────────────────────────────────────────────

    def _toggle_vis(self):
        self.cfg["enabled"] = not self.cfg.get("enabled", True)
        self.toggle_action.setText(
            "Show Visualizer" if not self.cfg["enabled"] else "Hide Visualizer"
        )
        if self.cfg["enabled"]:
            self.vis.setWindowOpacity(1.0)
            self.vis._opacity = 1.0
            self.vis.show()
        self._save()

    def _set_mode(self, mode: str):
        self.cfg["mode"] = mode
        self._update_mode_labels()
        self.vis.apply_config(self.cfg)
        self._save()

    def _update_mode_labels(self):
        cur = self.cfg.get("mode", "bars")
        self.bars_action.setText("◉ Bars" if cur == "bars" else "○ Bars")
        self.wave_action.setText("◉ Waveform" if cur == "wave" else "○ Waveform")
        self.mirror_action.setText("◉ Mirror" if cur == "mirror" else "○ Mirror")

    def _set_sensitivity(self, val: float):
        self.cfg["sensitivity"] = val
        self.vis.apply_config(self.cfg)
        self._build_menu()  # rebuild to update radio indicators
        self._save()

    def _set_theme(self, theme: str):
        self.cfg["theme"] = theme
        self.vis.apply_config(self.cfg)
        self._build_menu()  # rebuild to update radio indicators
        self._save()

    def _toggle_glow(self):
        self.cfg["glow"] = not self.cfg.get("glow", True)
        self.glow_action.setText(
            "✓ Glow Effect" if self.cfg["glow"] else "  Glow Effect"
        )
        self.vis.apply_config(self.cfg)
        self._save()

    def _toggle_beat(self):
        self.cfg["beat_flash"] = not self.cfg.get("beat_flash", True)
        self.beat_action.setText(
            "✓ Beat Flash" if self.cfg["beat_flash"] else "  Beat Flash"
        )
        self.vis.apply_config(self.cfg)
        self._save()

    def _toggle_autohide(self):
        self.cfg["auto_hide"] = not self.cfg.get("auto_hide", True)
        self.autohide_action.setText(
            "✓ Auto-Hide" if self.cfg["auto_hide"] else "  Auto-Hide"
        )
        self.vis.apply_config(self.cfg)
        self._save()

    def _toggle_startup(self):
        self.cfg["startup"] = not self.cfg.get("startup", False)
        set_startup(self.cfg["startup"])
        self.startup_action.setText(
            "✓ Start with Windows" if self.cfg["startup"]
            else "  Start with Windows"
        )
        self._save()

    def _save(self):
        save_config(self.cfg)

    def _schedule_auto_update_check(self):
        if not self.cfg.get("auto_update_check", True):
            return

        interval_hours = float(self.cfg.get("update_check_interval_hours", 24) or 24)
        interval_seconds = max(1.0, interval_hours * 3600.0)
        last_check = float(self.cfg.get("last_update_check_ts", 0.0) or 0.0)
        if time.time() - last_check < interval_seconds:
            return

        # Delay startup check so app launch remains responsive.
        QTimer.singleShot(5000, self._run_silent_startup_update_check)

    def _run_silent_startup_update_check(self):
        self._check_for_updates(silent_error=True, silent_no_update=True)

    def _check_for_updates(self, silent_error: bool = False, silent_no_update: bool = False):
        self.cfg["last_update_check_ts"] = time.time()
        self._save()

        result = check_for_updates()
        if not result.get("ok", False):
            if silent_error:
                return
            QMessageBox.warning(
                self.vis,
                "Update Check",
                "Could not check for updates.\n\n"
                f"Reason: {result.get('error', 'Unknown error')}",
            )
            return

        current_version = result.get("current_version", "unknown")
        latest_version = result.get("latest_version", "unknown")

        if result.get("update_available", False):
            release_name = result.get("release_name", "Latest release")
            release_url = result.get("release_url", "")
            msg = QMessageBox(self.vis)
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setWindowTitle("Update Available")
            msg.setText(
                f"A new version is available.\n\n"
                f"Current: {current_version}\n"
                f"Latest: {latest_version}\n"
                f"Release: {release_name}"
            )
            open_btn = msg.addButton("Open Release Page", QMessageBox.ButtonRole.AcceptRole)
            msg.addButton(QMessageBox.StandardButton.Close)
            msg.exec()
            if msg.clickedButton() == open_btn and release_url:
                import webbrowser

                webbrowser.open(release_url)
            return

        if silent_no_update:
            return

        QMessageBox.information(
            self.vis,
            "Update Check",
            f"You are up to date.\n\nCurrent version: {current_version}\nLatest available: {latest_version}",
        )

    def _quit(self):
        self.vis.timer.stop()
        self.audio_thread.stop()
        if self.vis.volume_scroller:
            self.vis.volume_scroller.stop()
        if self.vis.media_click_watcher:
            self.vis.media_click_watcher.stop()
        if self.vis.media_monitor:
            self.vis.media_monitor.stop()
        self.vis.close()
        sys.exit()

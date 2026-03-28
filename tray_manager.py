"""
tray_manager.py — System tray icon with controls for the visualizer.
"""
import sys
import os
import time
import subprocess
import tempfile
import urllib.request
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QMessageBox, QApplication, QProgressDialog
from PyQt6.QtGui import QIcon, QPixmap, QColor, QAction
from PyQt6.QtCore import QTimer, Qt
from config_manager import save_config, set_startup
from color_themes import THEME_NAMES, THEME_DISPLAY
from update_checker import check_for_updates
from app_resources import get_app_icon


class TrayManager(QSystemTrayIcon):
    def __init__(self, visualizer_window, audio_thread, config: dict, app_icon=None):
        icon = app_icon

        if icon is None or icon.isNull():
            app = QApplication.instance()
            if app is not None:
                app_window_icon = app.windowIcon()
                if app_window_icon is not None and not app_window_icon.isNull():
                    icon = app_window_icon

        if icon is None or icon.isNull():
            icon = get_app_icon()

        if icon is None or icon.isNull():
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
        # Try to build mode menu from the modes registry. If it's unavailable,
        # fall back to the legacy hard-coded entries.
        self._mode_actions = {}
        try:
            from modes import list_modes
            modes_list = list_modes()
        except Exception:
            modes_list = None

        if modes_list:
            for m in modes_list:
                mode_id = m.get("id")
                label = m.get("label", mode_id)
                action = QAction(f"○ {label}", mode_menu)
                action.setData((mode_id, label))
                action.triggered.connect(lambda checked, mid=mode_id: self._set_mode(mid))
                mode_menu.addAction(action)
                self._mode_actions[mode_id] = action
            self._update_mode_labels()
        else:
            # Legacy static menu (kept for compatibility if registry unavailable)
            self.bars_action = QAction("○ Bars", mode_menu)
            self.wave_action = QAction("○ Wave", mode_menu)
            self.mirror_action = QAction("○ Mirror", mode_menu)
            self.dot_matrix_action = QAction("○ Dot Matrix", mode_menu)
            self.skyline_action = QAction("○ Skyline", mode_menu)
            self.bars_action.triggered.connect(lambda: self._set_mode("bars"))
            self.wave_action.triggered.connect(lambda: self._set_mode("wave"))
            self.mirror_action.triggered.connect(lambda: self._set_mode("mirror"))
            self.dot_matrix_action.triggered.connect(lambda: self._set_mode("dot_matrix"))
            self.skyline_action.triggered.connect(lambda: self._set_mode("skyline"))
            mode_menu.addAction(self.bars_action)
            mode_menu.addAction(self.wave_action)
            mode_menu.addAction(self.mirror_action)
            mode_menu.addAction(self.dot_matrix_action)
            mode_menu.addAction(self.skyline_action)
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

        # ─── Gradient ───
        gradient_menu = menu.addMenu("Gradient")
        current_gradient = self.cfg.get("gradient_mode", "off")
        for label, mode in [
            ("Off", "off"),
            ("2-Color", "two_color"),
            ("3-Color", "three_color"),
        ]:
            prefix = "◉" if current_gradient == mode else "○"
            action = QAction(f"{prefix} {label}", gradient_menu)
            action.triggered.connect(lambda checked, m=mode: self._set_gradient_mode(m))
            gradient_menu.addAction(action)

        # ─── Mirror Center ───
        mirror_menu = menu.addMenu("Mirror Center")
        center_enabled = bool(self.cfg.get("mirror_center_mode", False))
        center_toggle = QAction(
            "✓ Enable Center Gap" if center_enabled else "  Enable Center Gap",
            mirror_menu,
        )
        center_toggle.triggered.connect(self._toggle_mirror_center_mode)
        mirror_menu.addAction(center_toggle)

        gap_menu = mirror_menu.addMenu("Center Gap")
        current_gap = int(self.cfg.get("mirror_center_gap", 2) or 2)
        for gap_val in [0, 2, 4, 6, 8, 10]:
            prefix = "◉" if current_gap == gap_val else "○"
            action = QAction(f"{prefix} {gap_val}px", gap_menu)
            action.triggered.connect(lambda checked, g=gap_val: self._set_mirror_center_gap(g))
            gap_menu.addAction(action)

        menu.addSeparator()

        # ─── Toggles ───
        self.glow_action = QAction(
            "✓ Glow Effect" if self.cfg.get("glow", True) else "  Glow Effect", menu
        )
        self.glow_action.triggered.connect(self._toggle_glow)
        menu.addAction(self.glow_action)

        self.beat_action = QAction(
            "✓ Beat Pulse" if self.cfg.get("beat_flash", True) else "  Beat Pulse", menu
        )
        self.beat_action.triggered.connect(self._toggle_beat)
        menu.addAction(self.beat_action)

        self.autohide_action = QAction(
            "✓ Auto-Hide" if self.cfg.get("auto_hide", True) else "  Auto-Hide", menu
        )
        self.autohide_action.triggered.connect(self._toggle_autohide)
        menu.addAction(self.autohide_action)

        self.dynamic_quality_action = QAction(
            "✓ Dynamic Quality" if self.cfg.get("dynamic_quality", True) else "  Dynamic Quality",
            menu,
        )
        self.dynamic_quality_action.triggered.connect(self._toggle_dynamic_quality)
        menu.addAction(self.dynamic_quality_action)

        self.peak_caps_action = QAction(
            "✓ Peak Caps" if self.cfg.get("peak_caps_enabled", True) else "  Peak Caps",
            menu,
        )
        self.peak_caps_action.triggered.connect(self._toggle_peak_caps)
        menu.addAction(self.peak_caps_action)

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
        # Keep compatibility with older configs where these names mapped to similar visuals.
        if cur == "oscilloscope":
            cur = "wave"
        elif cur == "mirror_tunnel":
            cur = "mirror"
        # If we built the menu from the registry, update those labels.
        if getattr(self, "_mode_actions", None):
            for mid, action in self._mode_actions.items():
                data = action.data() or (mid, action.text())
                label = data[1] if isinstance(data, (list, tuple)) else str(data)
                action.setText(("◉ " if cur == mid else "○ ") + label)
            return

        # Legacy static labels
        self.bars_action.setText("◉ Bars" if cur == "bars" else "○ Bars")
        self.wave_action.setText("◉ Wave" if cur == "wave" else "○ Wave")
        self.mirror_action.setText("◉ Mirror" if cur == "mirror" else "○ Mirror")
        self.dot_matrix_action.setText("◉ Dot Matrix" if cur == "dot_matrix" else "○ Dot Matrix")
        self.skyline_action.setText("◉ Skyline" if cur == "skyline" else "○ Skyline")
        # Radar/rotating modes removed; legacy configs mapping still handled elsewhere.

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

    def _set_gradient_mode(self, mode: str):
        self.cfg["gradient_mode"] = mode
        self.vis.apply_config(self.cfg)
        self._build_menu()
        self._save()

    def _toggle_mirror_center_mode(self):
        self.cfg["mirror_center_mode"] = not self.cfg.get("mirror_center_mode", False)
        self.vis.apply_config(self.cfg)
        self._build_menu()
        self._save()

    def _set_mirror_center_gap(self, gap_px: int):
        self.cfg["mirror_center_gap"] = max(0, int(gap_px))
        self.vis.apply_config(self.cfg)
        self._build_menu()
        self._save()

    def _toggle_dynamic_quality(self):
        self.cfg["dynamic_quality"] = not self.cfg.get("dynamic_quality", True)
        self.dynamic_quality_action.setText(
            "✓ Dynamic Quality" if self.cfg["dynamic_quality"] else "  Dynamic Quality"
        )
        self.vis.apply_config(self.cfg)
        self._save()

    def _toggle_peak_caps(self):
        self.cfg["peak_caps_enabled"] = not self.cfg.get("peak_caps_enabled", True)
        self.peak_caps_action.setText(
            "✓ Peak Caps" if self.cfg["peak_caps_enabled"] else "  Peak Caps"
        )
        self.vis.apply_config(self.cfg)
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
            "✓ Beat Pulse" if self.cfg["beat_flash"] else "  Beat Pulse"
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

    def _get_release_notes_preview(self, notes: str, max_lines: int = 10, max_chars: int = 700) -> str:
        if not notes:
            return ""

        lines = [line.rstrip() for line in str(notes).splitlines() if line.strip()]
        if not lines:
            return ""

        preview = "\n".join(lines[:max_lines]).strip()
        if len(preview) > max_chars:
            preview = preview[:max_chars].rstrip() + "..."
        if len(lines) > max_lines:
            preview += "\n..."
        return preview

    def _is_update_deferred(self) -> bool:
        defer_until = float(self.cfg.get("update_defer_until_ts", 0.0) or 0.0)
        return defer_until > time.time()

    def _is_update_skipped(self, latest_version: str) -> bool:
        skipped = str(self.cfg.get("update_skip_version", "") or "").strip()
        return bool(skipped and latest_version and skipped == latest_version)

    def _defer_update_prompt(self):
        remind_hours = float(self.cfg.get("update_remind_after_hours", 24) or 24)
        remind_hours = max(1.0, remind_hours)
        self.cfg["update_defer_until_ts"] = time.time() + (remind_hours * 3600.0)
        self._save()

    def _skip_update_version(self, latest_version: str):
        self.cfg["update_skip_version"] = str(latest_version or "")
        self.cfg["update_defer_until_ts"] = 0.0
        self._save()

    def _clear_update_hold_state(self):
        self.cfg["update_defer_until_ts"] = 0.0
        self.cfg["update_skip_version"] = ""
        self._save()

    def _download_and_launch_installer(self, download_url: str, asset_name: str) -> bool:
        if not download_url:
            return False

        def _fmt_mb(byte_count: int) -> str:
            return f"{byte_count / (1024 * 1024):.1f} MB"

        safe_name = os.path.basename(asset_name or "AudioVisualizer-Setup-latest.exe")
        target_dir = os.path.join(tempfile.gettempdir(), "AudioVisualizerUpdates")
        os.makedirs(target_dir, exist_ok=True)

        installer_path = os.path.join(target_dir, safe_name)
        partial_path = installer_path + ".part"
        progress = None

        self.check_updates_action.setEnabled(False)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        try:
            req = urllib.request.Request(
                download_url,
                headers={"User-Agent": "AudioVisualizer-Updater"},
            )
            with urllib.request.urlopen(req, timeout=90) as src, open(partial_path, "wb") as dst:
                total_bytes = 0
                content_length = src.headers.get("Content-Length", "").strip()
                if content_length.isdigit():
                    total_bytes = int(content_length)

                progress = QProgressDialog("Downloading installer...", "Cancel", 0, 100, self.vis)
                progress.setWindowTitle("Update")
                progress.setMinimumDuration(0)
                progress.setAutoClose(False)
                progress.setAutoReset(False)
                progress.setWindowModality(Qt.WindowModality.ApplicationModal)

                if total_bytes > 0:
                    progress.setRange(0, total_bytes)
                    progress.setValue(0)
                    progress.setLabelText(
                        f"Downloading installer... 0% (0.0 MB / {_fmt_mb(total_bytes)})"
                    )
                else:
                    # Unknown file size: keep an indeterminate progress bar.
                    progress.setRange(0, 0)
                    progress.setLabelText("Downloading installer... 0.0 MB")

                progress.show()
                QApplication.processEvents()

                downloaded = 0
                chunk_size = 256 * 1024
                while True:
                    if progress.wasCanceled():
                        raise RuntimeError("Download canceled by user")

                    chunk = src.read(chunk_size)
                    if not chunk:
                        break

                    dst.write(chunk)
                    downloaded += len(chunk)

                    if total_bytes > 0:
                        progress.setValue(min(downloaded, total_bytes))
                        pct = int((downloaded * 100) / max(1, total_bytes))
                        progress.setLabelText(
                            "Downloading installer... "
                            f"{min(pct, 100)}% ({_fmt_mb(downloaded)} / {_fmt_mb(total_bytes)})"
                        )
                    else:
                        progress.setLabelText(f"Downloading installer... {_fmt_mb(downloaded)}")
                    QApplication.processEvents()

                if total_bytes > 0:
                    progress.setValue(total_bytes)

            if os.path.exists(installer_path):
                os.remove(installer_path)
            os.replace(partial_path, installer_path)

            subprocess.Popen([installer_path], close_fds=True)
            QMessageBox.information(
                self.vis,
                "Update",
                "Installer downloaded. Audio Visualizer will now close so the updater can continue.",
            )
            self._quit()
            return True
        except Exception as e:
            if os.path.exists(partial_path):
                try:
                    os.remove(partial_path)
                except Exception:
                    pass
            QMessageBox.warning(
                self.vis,
                "Update",
                "Could not download or start the installer.\n\n"
                f"Reason: {e}",
            )
            return False
        finally:
            if progress:
                progress.close()
            self.check_updates_action.setEnabled(True)
            QApplication.restoreOverrideCursor()

    def _check_for_updates(self, silent_error: bool = False, silent_no_update: bool = False):
        is_manual_check = not silent_error and not silent_no_update
        self.cfg["last_update_check_ts"] = time.time()
        self._save()

        result = check_for_updates()
        if not result.get("ok", False):
            if silent_error:
                return

            status = str(result.get("status") or "").strip().lower()
            reason = str(result.get("error") or "Unknown error")
            if status == "error-rate-limited":
                body = (
                    "Could not check for updates right now because GitHub rate limits were hit.\n\n"
                    "Please try again in a few minutes, or open the release page manually from the tray menu.\n\n"
                    f"Details: {reason}"
                )
            else:
                body = f"Could not check for updates.\n\nReason: {reason}"

            QMessageBox.warning(
                self.vis,
                "Update Check",
                body,
            )
            return

        current_version = result.get("current_version", "unknown")
        latest_version = result.get("latest_version", "unknown")

        if result.get("update_available", False):
            if not is_manual_check:
                if self._is_update_deferred() or self._is_update_skipped(latest_version):
                    return

            release_name = result.get("release_name", "Latest release")
            release_url = result.get("release_url", "")
            release_notes = result.get("release_notes", "")
            installer_asset_url = result.get("installer_asset_url", "")
            installer_asset_name = result.get("installer_asset_name", "")
            notes_preview = self._get_release_notes_preview(release_notes)

            dialog_lines = [
                "A new version is available.",
                "",
                f"Current: {current_version}",
                f"Latest: {latest_version}",
                f"Release: {release_name}",
            ]
            if notes_preview:
                dialog_lines.extend(["", "Release notes preview:", notes_preview])

            msg = QMessageBox(self.vis)
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setWindowTitle("Update Available")
            msg.setText("\n".join(dialog_lines))
            install_btn = None
            if installer_asset_url:
                install_btn = msg.addButton("Download and Install", QMessageBox.ButtonRole.AcceptRole)
            open_btn = msg.addButton("Open Release Page", QMessageBox.ButtonRole.ActionRole)
            remind_btn = msg.addButton("Remind me later", QMessageBox.ButtonRole.ActionRole)
            skip_btn = msg.addButton("Skip this version", QMessageBox.ButtonRole.ActionRole)
            msg.addButton(QMessageBox.StandardButton.Close)
            msg.exec()

            if install_btn and msg.clickedButton() == install_btn:
                if self._download_and_launch_installer(installer_asset_url, installer_asset_name):
                    self._clear_update_hold_state()
                return

            if msg.clickedButton() == open_btn and release_url:
                import webbrowser

                webbrowser.open(release_url)
                return

            if msg.clickedButton() == remind_btn:
                self._defer_update_prompt()
                return

            if msg.clickedButton() == skip_btn:
                self._skip_update_version(latest_version)
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

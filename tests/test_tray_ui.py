"""Focused tray menu tests for tray_manager (offscreen Qt, no desktop launch)."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace

import pytest
from PyQt6.QtGui import QColor, QIcon, QPixmap
from PyQt6.QtWidgets import QApplication

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(scope="session")
def app():
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    return instance


@pytest.fixture
def make_tray(app, monkeypatch):
    import tray_manager

    # Tests must never touch the real ~/.audio_visualizer.json.
    monkeypatch.setattr(tray_manager, "save_config", lambda cfg: None)

    created = []
    def _make(cfg):
        pixmap = QPixmap(8, 8)
        pixmap.fill(QColor(0, 180, 220))
        visualizer = SimpleNamespace(
            apply_config=lambda *_: None,
            setWindowOpacity=lambda *_: None,
            show=lambda: None,
            _opacity=1.0,
        )
        base = {"auto_update_check": False}
        base.update(cfg)
        tray = tray_manager.TrayManager(visualizer, None, base, QIcon(pixmap))
        created.append(tray)
        return tray

    yield _make
    for tray in created:
        tray._shutting_down = True
        tray._tray_timer.stop()
        tray._auto_update_timer.stop()
        tray.hide()
        tray.deleteLater()
    QApplication.processEvents()


def test_toggle_label_matches_saved_visibility_on_first_build(make_tray):
    hidden = make_tray({"enabled": False})
    assert hidden.toggle_action.text() == "Show Visualizer"

    visible = make_tray({"enabled": True})
    assert visible.toggle_action.text() == "Hide Visualizer"


def test_toggle_label_stays_correct_across_rebuilds(make_tray):
    tray = make_tray({"enabled": True})
    assert tray.toggle_action.text() == "Hide Visualizer"

    # Rebuilds happen after every settings change (see _on_settings_changed).
    tray.cfg["enabled"] = False
    tray._build_menu()
    assert tray.toggle_action.text() == "Show Visualizer"

    tray.cfg["enabled"] = True
    tray._build_menu()
    assert tray.toggle_action.text() == "Hide Visualizer"


def test_toggle_action_flips_state_and_label(make_tray):
    tray = make_tray({"enabled": False})
    assert tray.toggle_action.text() == "Show Visualizer"

    tray.toggle_action.trigger()
    assert tray.cfg["enabled"] is True
    assert tray.toggle_action.text() == "Hide Visualizer"

    # A settings-driven rebuild must not disagree with the toggled state.
    tray._build_menu()
    assert tray.toggle_action.text() == "Hide Visualizer"

    tray.toggle_action.trigger()
    assert tray.cfg["enabled"] is False
    assert tray.toggle_action.text() == "Show Visualizer"


def test_menu_keeps_existing_action_set(make_tray):
    tray = make_tray({"enabled": False})
    actions = tray.contextMenu().actions()
    texts = [action.text() for action in actions if not action.isSeparator()]

    assert len(texts) == 4, texts
    assert any("Settings" in text for text in texts)
    assert texts[1] in {"Hide Visualizer", "Show Visualizer"}
    assert "Check for updates" in texts
    assert texts[-1] == "Quit"
    assert any(action.isSeparator() for action in actions)


def test_settings_quit_uses_existing_shutdown_action_once(make_tray, monkeypatch):
    tray = make_tray({})
    requests = []
    monkeypatch.setattr(tray, '_quit', lambda: requests.append(True))
    tray._open_settings()
    window = tray._settings_win
    try:
        tray._open_settings()  # Reopening must not duplicate the signal connection.
        window.quit_button.click()
        assert requests == [True]
    finally:
        window.close()
        window.deleteLater()


def test_settings_quit_stops_capture_before_exiting(make_tray, monkeypatch):
    tray = make_tray({})
    calls = []
    tray.audio_thread = SimpleNamespace(stop=lambda: calls.append('audio stopped'))
    tray.vis.timer = SimpleNamespace(stop=lambda: calls.append('animation stopped'))
    tray.vis.volume_scroller = None
    tray.vis.media_click_watcher = None
    tray.vis.media_monitor = SimpleNamespace(stop=lambda: calls.append('media stopped'))
    tray.vis.close = lambda: calls.append('overlay closed')
    monkeypatch.setattr(QApplication, 'quit', lambda: calls.append('app exited'))
    tray._open_settings()
    window = tray._settings_win
    try:
        window.quit_button.click()
        assert calls == ['animation stopped', 'audio stopped', 'media stopped',
                         'overlay closed', 'app exited']
        assert tray._shutting_down
        assert not tray._tray_timer.isActive()
        assert not tray._auto_update_timer.isActive()
    finally:
        window.close()
        window.deleteLater()


def test_settings_edit_preserves_tray_visibility_and_update_state(make_tray):
    from copy import deepcopy
    from config_manager import DEFAULTS

    tray = make_tray(deepcopy(DEFAULTS) | {"auto_update_check": False})
    tray._open_settings()
    window = tray._settings_win
    try:
        tray._toggle_vis()
        tray.cfg["update_skip_version"] = "2.0.0"
        tray.cfg["last_update_check_ts"] = 123.0
        window._pages["Visualizer"].glow_cb.setChecked(False)
        assert tray.cfg["enabled"] is False
        assert tray.cfg["glow"] is False
        assert tray.cfg["update_skip_version"] == "2.0.0"
        assert tray.cfg["last_update_check_ts"] == 123.0
        # Reusing the window and making another edit must preserve newer state too.
        tray._toggle_vis()
        window._pages["Visualizer"].glow_cb.setChecked(True)
        assert tray.cfg["enabled"] is True
    finally:
        window.close()
        window.deleteLater()


def test_update_check_runs_off_ui_thread_and_keeps_event_loop_alive(make_tray, monkeypatch):
    import threading
    import time
    from PyQt6.QtCore import QTimer
    import tray_manager

    started, release = threading.Event(), threading.Event()
    worker_threads, results, ticks = [], [], []

    def slow_check():
        worker_threads.append(threading.get_ident())
        started.set()
        release.wait(3)
        return {"ok": True, "update_available": False}

    monkeypatch.setattr(tray_manager, "check_for_updates", slow_check)
    tray = make_tray({})
    monkeypatch.setattr(tray, "_handle_update_result", lambda *args: results.append(threading.get_ident()))
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(True))
    timer.start(0)
    main_thread = threading.get_ident()
    try:
        tray._check_for_updates()
        assert started.wait(1)
        assert worker_threads[0] != main_thread
        tray._check_for_updates()  # Duplicate clicks cannot start another request.
        tray._build_menu()  # Settings changes rebuild the menu during requests.
        assert not tray.check_updates_action.isEnabled()
        QApplication.processEvents()
        assert ticks and not results
    finally:
        release.set()
        deadline = time.monotonic() + 4
        while tray._check_worker and time.monotonic() < deadline:
            QApplication.processEvents()
            time.sleep(0.001)
        timer.stop()
    assert worker_threads[0] != main_thread
    assert results == [main_thread]
    assert ticks
    assert tray.check_updates_action.isEnabled()


def test_cancel_download_keeps_ui_responsive_and_does_not_launch_installer(make_tray, monkeypatch):
    import threading
    import time
    from PyQt6.QtWidgets import QWidget
    import tray_manager

    started, release = threading.Event(), threading.Event()
    threads = []

    def slow_download(asset, kind, version, progress, cancel):
        threads.append(threading.get_ident())
        started.set()
        release.wait(3)
        return {"ok": True, "path": "must-not-launch.exe"}

    monkeypatch.setattr(tray_manager, "stage_update", slow_download)
    monkeypatch.setattr(tray_manager, "launch_update", lambda *a, **k: pytest.fail("Canceled download launched"))
    tray = make_tray({})
    window = QWidget()
    tray.vis = window
    try:
        tray._download_update({}, "portable-exe", "2.0.0")
        assert started.wait(1)
        assert threads[0] != threading.get_ident()
        QApplication.processEvents()
        assert not tray.check_updates_action.isEnabled()
        tray._download_progress.canceled.emit()
        assert tray._download_worker.cancel.is_set()
    finally:
        release.set()
        deadline = time.monotonic() + 4
        while tray._download_worker and time.monotonic() < deadline:
            QApplication.processEvents()
            time.sleep(0.001)
        window.close()
        window.deleteLater()
    assert tray._download_worker is None
    assert tray.check_updates_action.isEnabled()


def test_tray_recovers_when_shell_becomes_available(make_tray, monkeypatch):
    tray = make_tray({})
    monkeypatch.setattr(tray, "isSystemTrayAvailable", lambda: False)
    tray._ensure_tray_visible()
    assert not tray._tray_was_available
    shown = []
    monkeypatch.setattr(tray, "isSystemTrayAvailable", lambda: True)
    monkeypatch.setattr(tray, "show", lambda: shown.append(True))
    monkeypatch.setattr(tray, "isVisible", lambda: True)
    tray._ensure_tray_visible()
    tray._ensure_tray_visible()
    assert shown == [True]  # Avoid repeatedly re-registering overflow icons.
    tray._shutting_down = True
    tray._ensure_tray_visible()
    assert shown == [True]


def test_icon_renders_when_resource_is_missing(app, monkeypatch):
    import app_resources
    monkeypatch.setattr(app_resources, "get_resource_path", lambda p: "missing-icon.ico")
    icon = app_resources.get_app_icon()
    pixmap = icon.pixmap(16, 16)
    assert not pixmap.isNull()
    image = pixmap.toImage()
    assert any(image.pixelColor(x, y).alpha() > 0 for x in range(16) for y in range(16))


def test_auto_checks_repeat_and_honor_deferral(make_tray, monkeypatch):
    import tray_manager
    tray = make_tray({"auto_update_check": True, "last_update_check_ts": 0, "update_defer_until_ts": 0})
    clock = [100000.0]
    monkeypatch.setattr(tray_manager.time, "time", lambda: clock[0])
    checks = []
    monkeypatch.setattr(tray, "_check_for_updates", lambda **kwargs: checks.append(kwargs))
    tray._run_silent_startup_update_check()
    tray.cfg["last_update_check_ts"] = clock[0]
    clock[0] += 86401
    tray.cfg["update_defer_until_ts"] = clock[0] + 1000
    tray._run_silent_startup_update_check()
    assert len(checks) == 1
    clock[0] += 1001
    tray._run_silent_startup_update_check()
    assert len(checks) == 2


def test_automatic_update_downloads_without_a_modal_prompt(make_tray, monkeypatch):
    import tray_manager
    tray = make_tray({})
    selected = {"name": "update.exe"}
    monkeypatch.setattr(tray_manager, "installation_kind", lambda: "installed")
    monkeypatch.setattr(tray_manager, "select_update_asset", lambda *a: selected)
    downloads = []
    monkeypatch.setattr(tray, "_download_update", lambda *a, **k: downloads.append((a, k)))
    tray._handle_update_result({"ok": True, "update_available": True, "latest_version": "2.0.0"}, True, True)
    assert downloads == [((selected, "installed", "2.0.0"), {"automatic": True})]


def test_download_ready_waits_for_user_restart(make_tray, monkeypatch):
    import threading
    import tray_manager
    tray = make_tray({})
    tray._download_worker = SimpleNamespace(cancel=threading.Event(), deleteLater=lambda: None)
    tray._download_progress = SimpleNamespace(close=lambda: None, deleteLater=lambda: None)
    tray._download_automatic = True
    notices = []
    monkeypatch.setattr(tray, "showMessage", lambda *a: notices.append(a))
    monkeypatch.setattr(tray_manager, "launch_update", lambda *a: pytest.fail("Restart was not requested"))
    ready = {"ok": True, "stage": "staged-update", "version": "2.0.0"}
    tray._on_download_finished(ready)
    assert tray._ready_update == ready
    assert tray.cfg["pending_update"] == ready
    assert tray.check_updates_action.text() == "Restart to update"
    assert notices


def test_handoff_keeps_app_running_until_helper_is_ready(make_tray, tmp_path, monkeypatch):
    import time
    tray = make_tray({})
    tray._ready_update = {"stage": str(tmp_path)}
    tray.cfg['pending_update'] = tray._ready_update
    tray._update_process = SimpleNamespace(poll=lambda: None)
    tray._handoff_deadline = time.monotonic() + 10
    tray._handoff_timer = SimpleNamespace(stop=lambda: None)
    quits = []
    monkeypatch.setattr(tray, "_quit", lambda: quits.append(True))
    tray._poll_update_handoff()
    assert not quits
    (tmp_path / "ready").write_text("ready")
    tray._poll_update_handoff()
    assert quits == [True]
    assert 'pending_update' not in tray.cfg

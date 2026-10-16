"""Background overlay recovery must not dismiss the app's interactive UI."""
from types import SimpleNamespace

from PyQt6.QtWidgets import QApplication
from visualizer_window import VisualizerWindow


def test_recovery_leaves_open_popups_alone(monkeypatch):
    calls = []
    monkeypatch.setattr(QApplication, 'activePopupWidget', lambda: object())
    vis = SimpleNamespace(cfg={'enabled': True},
        _restore_win32_visibility=lambda: calls.append('restore'),
        _restore_if_minimized_or_hidden=lambda: calls.append('raise'),
        _ensure_topmost=lambda **kwargs: calls.append('topmost'),
        _enable_click_through=lambda: calls.append('click-through'))
    vis._application_ui_active = lambda: VisualizerWindow._application_ui_active(vis)
    VisualizerWindow._refresh_window_styles(vis)
    assert calls == []


def test_settings_window_defers_recovery_but_overlay_does_not(monkeypatch):
    monkeypatch.setattr(QApplication, 'activePopupWidget', lambda: None)
    monkeypatch.setattr(QApplication, 'activeModalWidget', lambda: None)
    vis = SimpleNamespace()
    monkeypatch.setattr(QApplication, 'activeWindow', lambda: object())
    assert VisualizerWindow._application_ui_active(vis)
    monkeypatch.setattr(QApplication, 'activeWindow', lambda: vis)
    assert not VisualizerWindow._application_ui_active(vis)
    monkeypatch.setattr(QApplication, 'activeWindow', lambda: None)
    assert not VisualizerWindow._application_ui_active(vis)


def test_normal_recovery_resumes_after_popup_closes(monkeypatch):
    calls = []
    vis = SimpleNamespace(cfg={'enabled': True}, _application_ui_active=lambda: False,
        _visibility_recovery_allowed=lambda: True,
        _restore_win32_visibility=lambda: calls.append('restore'),
        _restore_if_minimized_or_hidden=lambda: calls.append('raise'),
        _ensure_topmost=lambda **kwargs: calls.append('topmost'),
        _enable_click_through=lambda: calls.append('click-through'))
    VisualizerWindow._refresh_window_styles(vis)
    assert calls == ['restore', 'raise', 'topmost', 'click-through']

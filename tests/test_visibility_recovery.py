"""Recovery must distinguish intentional hiding from shell interference."""
from types import SimpleNamespace

import pytest

from visualizer_window import VisualizerWindow


def overlay(**state):
    calls = []
    vis = SimpleNamespace(
        cfg={'enabled': True, 'auto_hide': True},
        _taskbar_suppressed=False, _opacity=1.0, _decay_progress=0.0,
        _application_ui_active=lambda: False,
        _restore_win32_visibility=lambda: calls.append('native restore'),
        _restore_if_minimized_or_hidden=lambda: calls.append('qt restore'),
        _ensure_topmost=lambda **kwargs: calls.append('topmost'),
        _enable_click_through=lambda: None,
    )
    vis.__dict__.update(state)
    vis._visibility_recovery_allowed = lambda: VisualizerWindow._visibility_recovery_allowed(vis)
    return vis, calls


@pytest.mark.parametrize('state', [
    {'_taskbar_suppressed': True},
    {'_opacity': 0.1, '_decay_progress': 1.0},
    {'_opacity': 0.0},
    {'cfg': {'enabled': False}},
])
def test_recovery_never_shows_intentionally_hidden_overlay(state):
    vis, calls = overlay(**state)
    VisualizerWindow._refresh_window_styles(vis)
    assert calls == []


def test_recovery_resumes_when_audio_and_taskbar_return():
    vis, calls = overlay(_taskbar_suppressed=True, _decay_progress=1.0, _opacity=0.1)
    VisualizerWindow._refresh_window_styles(vis)
    assert calls == []
    vis._taskbar_suppressed = False
    vis._decay_progress = 0.0
    vis._opacity = 1.0
    VisualizerWindow._refresh_window_styles(vis)
    assert calls == ['native restore', 'qt restore', 'topmost']


def test_reposition_does_not_revive_completed_silence_decay():
    vis, calls = overlay(_decay_progress=1.0, _opacity=0.1)
    vis._monitor_mgr = SimpleNamespace(
        get_taskbar_info=lambda index: {},
        visualizer_position=lambda **kwargs: (0, 0, 800, 40),
    )
    vis.x, vis.y = lambda: 0, lambda: 0
    vis.width, vis.height = lambda: 800, lambda: 40
    vis.isVisible = lambda: False
    vis.show = lambda: calls.append('show')
    vis._place_on_taskbar = lambda *args: None
    VisualizerWindow._maybe_reposition(vis)
    assert calls == []


def test_turning_off_auto_hide_allows_recovery_after_silence():
    vis, calls = overlay(cfg={'enabled': True, 'auto_hide': False},
                         _decay_progress=1.0, _opacity=0.1)
    VisualizerWindow._refresh_window_styles(vis)
    assert calls == ['native restore', 'qt restore', 'topmost']

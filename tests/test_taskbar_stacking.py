"""Taskbar children follow shell display bands and retain global positioning."""
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QRect

import visualizer_window as module
from visualizer_window import VisualizerWindow


@pytest.mark.parametrize('hosted, explicit, expected', [
    (True, True, [module.HWND_TOP]),
    (True, False, [module.HWND_TOP]),
    (False, False, [module.HWND_TOPMOST]),
    (False, True, [module.HWND_NOTOPMOST, module.HWND_TOPMOST]),
])
def test_hosted_recovery_never_changes_taskbar_topmost_state(monkeypatch, hosted, explicit, expected):
    calls = []
    monkeypatch.setattr(module, 'user32', SimpleNamespace(
        SetWindowPos=lambda hwnd, after, *args: calls.append((after, args[-1]))))
    vis = SimpleNamespace(winId=lambda: 100, _application_ui_active=lambda: False,
                          _taskbar_host_hwnd=200 if hosted else 0)
    VisualizerWindow._ensure_topmost(vis, force_bounce=explicit)
    assert [after for after, flags in calls] == expected
    assert all(flags & module.SWP_NOACTIVATE for after, flags in calls)


def make_overlay(monkeypatch, *, same_dpi=True, can_attach=True):
    state = SimpleNamespace(parent=None, geometry=QRect(), hosts=[], placements=[])
    def wrap(hwnd):
        host = SimpleNamespace(hwnd=hwnd, deleteLater=lambda: None)
        state.hosts.append(host)
        return host
    def set_parent(host):
        state.parent = host.hwnd if host and can_attach else None
    def set_geometry(rect):
        state.geometry = rect
        state.placements.append(rect)
    monkeypatch.setattr(module.QApplication, 'platformName', lambda: 'windows')
    monkeypatch.setattr(module, 'QWindow', SimpleNamespace(fromWinId=wrap))
    monkeypatch.setattr(module, 'user32', SimpleNamespace(
        GetParent=lambda hwnd: state.parent,
        GetWindowDpiAwarenessContext=lambda hwnd: hwnd,
        AreDpiAwarenessContextsEqual=lambda *args: same_dpi))
    vis = SimpleNamespace(
        cfg={'visualizer_monitor': 1}, winId=lambda: 100,
        _taskbar_host_window=None, _taskbar_host_hwnd=0,
        windowHandle=lambda: SimpleNamespace(setParent=set_parent),
        geometry=lambda: state.geometry, setGeometry=set_geometry,
        _monitor_mgr=SimpleNamespace(_find_taskbar_hwnd=lambda index: 200))
    return vis, state


def test_hosted_geometry_uses_taskbar_coordinates_on_secondary_monitor(monkeypatch):
    vis, state = make_overlay(monkeypatch)
    info = {'rect': QRect(1920, -40, 1200, 40)}
    VisualizerWindow._place_on_taskbar(vis, (2000, -40, 400, 40), info)
    assert vis._taskbar_host_hwnd == state.parent == 200
    assert state.geometry == QRect(80, 0, 400, 40)
    VisualizerWindow._place_on_taskbar(vis, (2000, -40, 400, 40), info)
    assert len(state.hosts) == len(state.placements) == 1


@pytest.mark.parametrize('same_dpi, can_attach', [(False, True), (True, False)])
def test_unsupported_embedding_keeps_standalone_global_geometry(monkeypatch, same_dpi, can_attach):
    vis, state = make_overlay(monkeypatch, same_dpi=same_dpi, can_attach=can_attach)
    VisualizerWindow._place_on_taskbar(vis, (20, 800, 400, 40), {'rect': QRect(0, 800, 1200, 40)})
    assert vis._taskbar_host_hwnd == 0
    assert state.parent is None
    assert state.geometry == QRect(20, 800, 400, 40)


def test_auto_hidden_always_visible_layout_detaches_from_taskbar(monkeypatch):
    vis, state = make_overlay(monkeypatch)
    info = {'rect': QRect(0, 800, 1200, 40), 'autohide': True}
    VisualizerWindow._place_on_taskbar(vis, (20, 800, 400, 40), info)
    assert state.parent == 200
    vis.cfg['taskbar_auto_hide_behavior'] = 'always'
    VisualizerWindow._place_on_taskbar(vis, (20, 800, 400, 40), info)
    assert state.parent is None
    assert vis._taskbar_host_hwnd == 0
    assert state.geometry == QRect(20, 800, 400, 40)


def test_monitor_change_replaces_foreign_host(monkeypatch):
    vis, state = make_overlay(monkeypatch)
    info = {'rect': QRect(0, 800, 1200, 40)}
    VisualizerWindow._place_on_taskbar(vis, (20, 800, 400, 40), info)
    vis._monitor_mgr._find_taskbar_hwnd = lambda index: 300
    VisualizerWindow._place_on_taskbar(vis, (20, 800, 400, 40), info)
    assert vis._taskbar_host_hwnd == state.parent == 300

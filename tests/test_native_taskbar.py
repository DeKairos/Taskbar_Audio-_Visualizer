"""Native surface placement, DPI input, and recovery regressions."""
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QRect

import ui.native_taskbar as native
from ui.native_taskbar import NativeTaskbarSurface, TaskbarVisualizerWindow


def packed(x, y):
    return ((int(y) & 0xffff) << 16) | (int(x) & 0xffff)


def test_reposition_polling_does_not_reorder_an_unchanged_surface(monkeypatch):
    calls = []
    monkeypatch.setattr(native, 'u', SimpleNamespace(
        ScreenToClient=lambda *args: True, SetWindowPos=lambda *args: calls.append(args) or True))
    surface = object.__new__(NativeTaskbarSurface)
    surface.parent, surface.hwnd, surface._bounds, surface.position_changes = 1, 2, None, 0
    for _ in range(120):
        surface.position(0, 1040, 600, 40)
    assert len(calls) == 1
    surface.position(20, 1040, 700, 40)
    assert len(calls) == 2
    assert calls[-1][-1] & 0x0004  # Geometry changes preserve z-order.


@pytest.mark.parametrize('scale', [1.0, 1.25, 1.5, 2.0])
def test_native_clicks_map_physical_pixels_and_dispatch_once(monkeypatch, scale):
    origin = (-1920, 1000)
    def to_client(hwnd, ptr):
        ptr._obj.x -= origin[0]
        ptr._obj.y -= origin[1]
        return True
    monkeypatch.setattr(native, 'u', SimpleNamespace(
        ScreenToClient=to_client, SetCapture=lambda *args: None, ReleaseCapture=lambda: None))
    monkeypatch.setattr(native.QTimer, 'singleShot', lambda delay, callback: callback())
    actions = []
    view = SimpleNamespace(
        _surface_scale=scale, _media_overlay_alpha=1, _native_pressed=None,
        controls_rects={'play': QRect(470, 8, 22, 22)}, _button_target={}, native_clicks=0,
        handle_media_click=lambda x, y: actions.append((x, y)))
    for name in ('_native_mouse_point', '_native_control_at'):
        method = getattr(TaskbarVisualizerWindow, name)
        setattr(view, name, lambda *args, method=method, **kwargs: method(view, *args, **kwargs))
    x, y = round(480 * scale), round(18 * scale)
    handler = lambda msg, lp: TaskbarVisualizerWindow._native_message(view, 1, msg, 0, lp)
    assert handler(0x84, packed(origin[0] + x, origin[1] + y)) == 1
    handler(0x201, packed(x, y))
    handler(0x202, packed(x, y))
    assert len(actions) == view.native_clicks == 1
    assert view.controls_rects['play'].contains(*actions[0])
    handler(0x201, packed(x, y))
    handler(0x202, packed(0, 0))
    assert len(actions) == 1  # A drag out must cancel the action.
    handler(0x201, packed(x, y))
    handler(0x215, 0)  # Capture loss cancels the pressed button.
    handler(0x202, packed(x, y))
    assert len(actions) == 1


def test_native_button_polling_cannot_duplicate_mouse_messages(monkeypatch):
    monkeypatch.setattr(native, 'u', SimpleNamespace(GetAsyncKeyState=lambda key: 0x8000))
    view = SimpleNamespace(surface=SimpleNamespace(interactive=True), _left_pressed_last=False)
    TaskbarVisualizerWindow._poll_media_overlay_click(view)
    assert view._left_pressed_last


def test_surface_recovers_after_explorer_replaces_taskbar(monkeypatch):
    closed, created = [], []
    current = [10]
    monkeypatch.setattr(native, 'u', SimpleNamespace(IsWindow=lambda hwnd: hwnd == 30))
    def create(parent, handler):
        created.append(parent)
        return SimpleNamespace(parent=parent, hwnd=30, close=lambda: closed.append(parent))
    monkeypatch.setattr(native, 'NativeTaskbarSurface', create)
    view = SimpleNamespace(cfg={}, surface=SimpleNamespace(parent=5, hwnd=6, close=lambda: closed.append(5)),
        _native_message=lambda *args: None,
        _monitor_mgr=SimpleNamespace(_find_taskbar_hwnd=lambda index: current[0]))
    assert TaskbarVisualizerWindow._ensure_surface(view)
    assert closed == [5] and created == [10]
    assert TaskbarVisualizerWindow._ensure_surface(view)
    assert created == [10]
    current[0] = 0
    assert not TaskbarVisualizerWindow._ensure_surface(view)
    assert view.surface is None


def test_offscreen_update_does_not_queue_an_unused_widget_repaint():
    # The timer submits the frame itself; this must not call QWidget.update.
    assert TaskbarVisualizerWindow.update(SimpleNamespace()) is None

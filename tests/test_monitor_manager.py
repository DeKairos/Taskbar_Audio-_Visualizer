"""Tests for ui.monitor_manager module."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_monitor_manager_instantiation():
    # Can't test with real QApplication in unit test, but verify class exists
    from ui.monitor_manager import MonitorManager
    assert MonitorManager is not None


def test_monitor_manager_has_methods():
    from ui.monitor_manager import MonitorManager
    assert hasattr(MonitorManager, "get_monitors")
    assert hasattr(MonitorManager, "get_monitor")
    assert hasattr(MonitorManager, "get_primary_monitor")
    assert hasattr(MonitorManager, "taskbar_geometry")
    assert hasattr(MonitorManager, "visualizer_position")


def test_mixed_dpi_conversion_keeps_the_display_origin():
    from ctypes.wintypes import RECT
    from PyQt6.QtCore import QRect
    from ui.monitor_manager import MonitorManager
    monitor = {"geometry": QRect(1920, -200, 1280, 720)}
    physical_monitor = RECT(1920, -200, 3840, 880)
    taskbar = RECT(1920, 820, 3840, 880)
    result = MonitorManager._rect_to_logical(taskbar, 1.5, monitor, physical_monitor)
    assert result == QRect(1920, 480, 1280, 40)


def test_secondary_taskbar_is_matched_by_display_name():
    from types import SimpleNamespace
    from ui.monitor_manager import MonitorManager
    manager = MonitorManager.__new__(MonitorManager)
    windows = {'Shell_TrayWnd': [10], 'Shell_SecondaryTrayWnd': [20, 30]}
    def find(parent, previous, name, title):
        candidates = windows[name]
        index = candidates.index(previous) + 1 if previous else 0
        return candidates[index] if index < len(candidates) else 0
    manager._user32 = SimpleNamespace(FindWindowExW=find)
    manager.get_monitor = lambda index: {'name': 'DISPLAY3'}
    manager._window_monitor = lambda hwnd: SimpleNamespace(szDevice={10: 'DISPLAY1', 20: 'DISPLAY3', 30: 'DISPLAY2'}[hwnd])
    assert manager._find_taskbar_hwnd(2) == 20


def test_gap_after_icons_does_not_include_the_icons():
    from PyQt6.QtCore import QRect
    from ui.monitor_manager import MonitorManager, ABE_BOTTOM
    manager = MonitorManager.__new__(MonitorManager)
    manager._find_taskbar_hwnd = lambda index: 10
    children = {'Start': QRect(0, 0, 48, 40), 'MSTaskListWClass': QRect(48, 0, 400, 40),
                'TrayNotifyWnd': QRect(900, 0, 100, 40)}
    manager._logical_child_rect = lambda hwnd, name, index: children.get(name)
    gap = manager._get_horizontal_empty_space(QRect(0, 0, 1000, 40), 'center', 0, ABE_BOTTOM)
    assert gap['x'] >= children['MSTaskListWClass'].right() + 1
    assert gap['x'] + gap['width'] <= children['TrayNotifyWnd'].left()


def test_auto_position_uses_the_measured_gap_location():
    from PyQt6.QtCore import QRect
    from ui.monitor_manager import MonitorManager, ABE_BOTTOM
    manager = MonitorManager.__new__(MonitorManager)
    manager.get_taskbar_info = lambda index: {'rect': QRect(1920, 1000, 1280, 40), 'edge': ABE_BOTTOM}
    manager.get_taskbar_empty_space = lambda *args: {'available': True, 'x': 2500, 'width': 300}
    assert manager.visualizer_position(alignment_hint='center') == (2500, 1000, 300, 40)


def test_vertical_placement_stays_inside_a_narrow_taskbar():
    from PyQt6.QtCore import QRect
    from ui.monitor_manager import MonitorManager, ABE_LEFT
    manager = MonitorManager.__new__(MonitorManager)
    manager.get_taskbar_info = lambda index: {'rect': QRect(-1000, 0, 32, 800), 'edge': ABE_LEFT}
    manager.get_taskbar_empty_space = lambda *args: {'available': True, 'x': 100, 'width': 300}
    assert manager.visualizer_position() == (-1000, 100, 32, 300)


def test_auto_hide_state_is_separate_from_taskbar_geometry():
    from ctypes.wintypes import RECT
    from types import SimpleNamespace
    from PyQt6.QtCore import QRect
    from ui.monitor_manager import MonitorManager, ABM_GETSTATE
    manager = MonitorManager.__new__(MonitorManager)
    manager.get_monitor = lambda index: {'geometry': QRect(0, 0, 1920, 1080),
        'available_geometry': QRect(0, 0, 1920, 1080), 'ratio': 1.0}
    manager._find_taskbar_hwnd = lambda index: 10
    manager._get_window_rect = lambda hwnd: RECT(0, 1078, 1920, 1126)
    manager._window_monitor = lambda hwnd: SimpleNamespace(rcMonitor=RECT(0, 0, 1920, 1080))
    def state(message, data):
        assert message == ABM_GETSTATE
        return 1
    manager._shell32 = SimpleNamespace(SHAppBarMessage=state)
    info = manager.get_taskbar_info()
    assert info['autohide'] and info['hidden']
    assert info['rect'] == QRect(0, 1032, 1920, 48)

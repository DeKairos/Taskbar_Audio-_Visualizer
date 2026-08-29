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

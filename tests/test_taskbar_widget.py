"""Tests for ui.taskbar_widget module."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_taskbar_widget_class_exists():
    from ui.taskbar_widget import TaskbarMediaWidget
    assert TaskbarMediaWidget is not None
    assert hasattr(TaskbarMediaWidget, "update_media")
    assert hasattr(TaskbarMediaWidget, "position_widget")

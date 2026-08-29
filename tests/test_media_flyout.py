"""Tests for ui.media_flyout module."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_media_flyout_class_exists():
    from ui.media_flyout import MediaFlyout
    assert MediaFlyout is not None
    assert hasattr(MediaFlyout, "show_info")
    assert hasattr(MediaFlyout, "hide_animated")


def test_media_flyout_has_alpha_property():
    from ui.media_flyout import MediaFlyout
    assert hasattr(MediaFlyout, "flyout_alpha")

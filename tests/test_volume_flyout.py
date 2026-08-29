"""Tests for ui.volume_flyout module."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_volume_flyout_class_exists():
    from ui.volume_flyout import VolumeFlyout
    assert VolumeFlyout is not None
    assert hasattr(VolumeFlyout, "show_volume")
    assert hasattr(VolumeFlyout, "hide_animated")

"""Tests for ui.gl_renderer module."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_gl_renderer_class_exists():
    from ui.gl_renderer import GLRenderer
    r = GLRenderer()
    assert r is not None
    assert hasattr(r, "available")
    assert hasattr(r, "initialize")
    assert hasattr(r, "clear")
    assert hasattr(r, "draw_rect")
    assert hasattr(r, "draw_circle")
    assert hasattr(r, "cleanup")


def test_gl_renderer_availability_flag():
    from ui.gl_renderer import HAS_OPENGL
    # Just check the flag is a boolean
    assert isinstance(HAS_OPENGL, bool)

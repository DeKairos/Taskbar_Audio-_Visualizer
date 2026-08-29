"""Tests for color_themes module."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_get_theme():
    from color_themes import get_theme
    theme = get_theme("cyan")
    assert "base" in theme
    assert "peak" in theme
    assert "glow" in theme
    assert "bg" in theme
    assert "rainbow" in theme


def test_get_theme_fallback():
    from color_themes import get_theme
    theme = get_theme("nonexistent_theme_xyz")
    assert theme == get_theme("cyan")


def test_bar_color_normal():
    from color_themes import get_theme, bar_color
    theme = get_theme("cyan")
    r, g, b = bar_color(theme, 0.5, 10, 64)
    assert 0 <= r <= 255
    assert 0 <= g <= 255
    assert 0 <= b <= 255


def test_bar_color_rainbow():
    from color_themes import get_theme, bar_color
    theme = get_theme("rainbow")
    r1, g1, b1 = bar_color(theme, 0.5, 0, 64)
    r2, g2, b2 = bar_color(theme, 0.5, 32, 64)
    assert (r1, g1, b1) != (r2, g2, b2)


def test_bar_color_bounds():
    from color_themes import get_theme, bar_color
    theme = get_theme("sunset")
    for norm in [0.0, 0.25, 0.5, 0.75, 1.0]:
        r, g, b = bar_color(theme, norm, 0, 1)
        assert 0 <= r <= 255
        assert 0 <= g <= 255
        assert 0 <= b <= 255


def test_all_themes_valid():
    from color_themes import THEMES, THEME_NAMES
    assert len(THEME_NAMES) > 0
    for name in THEME_NAMES:
        theme = THEMES[name]
        assert isinstance(theme["base"], tuple)
        assert len(theme["base"]) == 3
        assert isinstance(theme["rainbow"], bool)

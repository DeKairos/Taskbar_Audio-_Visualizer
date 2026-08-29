"""Tests for ui.fluent_theme module."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_design_tokens_exist():
    from ui.fluent_theme import (
        RADIUS_SMALL, RADIUS_MEDIUM, RADIUS_LARGE, RADIUS_CARD,
        SPACE_SM, SPACE_MD, SPACE_LG, SPACE_XL,
        FONT_FAMILY, FONT_SIZES, FONT_WEIGHTS,
    )
    assert RADIUS_SMALL < RADIUS_MEDIUM < RADIUS_LARGE < RADIUS_CARD
    assert SPACE_SM < SPACE_MD < SPACE_LG < SPACE_XL
    assert isinstance(FONT_SIZES, dict)
    assert isinstance(FONT_WEIGHTS, dict)


def test_lerp_color():
    from ui.fluent_theme import lerp_color
    assert lerp_color((0, 0, 0), (255, 255, 255), 0.0) == (0, 0, 0)
    assert lerp_color((0, 0, 0), (255, 255, 255), 1.0) == (255, 255, 255)
    result = lerp_color((0, 0, 0), (255, 255, 255), 0.5)
    assert 120 <= result[0] <= 135  # approximately 127


def test_hex_conversion():
    from ui.fluent_theme import hex_to_rgb, rgb_to_hex
    assert hex_to_rgb("#ff8000") == (255, 128, 0)
    assert rgb_to_hex((255, 128, 0)) == "#ff8000"
    assert rgb_to_hex(hex_to_rgb("#aabbcc")) == "#aabbcc"


def test_card_colors():
    from ui.fluent_theme import card_bg, card_border, text_primary, text_secondary
    dark_bg = card_bg(dark_mode=True)
    light_bg = card_bg(dark_mode=False)
    assert dark_bg.red() < light_bg.red()  # dark is darker

    dark_border = card_border(dark_mode=True)
    light_border = card_border(dark_mode=False)
    assert dark_border.alpha() > 0


def test_acrylic_simulation():
    from ui.fluent_theme import acrylic_bg_color
    c = acrylic_bg_color((100, 150, 200), tint_alpha=50)
    assert c.alpha() == 50
    assert c.red() < 100  # darkened


def test_accent_color():
    from ui.fluent_theme import accent_color
    c = accent_color()
    assert c is not None
    assert 0 <= c.red() <= 255
    assert 0 <= c.green() <= 255
    assert 0 <= c.blue() <= 255

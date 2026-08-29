"""Tests for ui.theme_editor module."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_theme_editor_class_exists():
    from ui.theme_editor import ThemeEditor
    assert ThemeEditor is not None
    assert hasattr(ThemeEditor, "theme_saved")


def test_load_save_delete_custom_themes():
    from ui.theme_editor import save_custom_theme, load_custom_themes, delete_custom_theme

    test_theme = {
        "name": "test_theme_unit",
        "base": [255, 0, 0],
        "peak": [0, 255, 0],
        "glow": [0, 0, 255],
        "bg": [128, 128, 128],
        "rainbow": False,
    }

    # Save
    save_custom_theme("test_theme_unit", test_theme)

    # Load
    themes = load_custom_themes()
    assert "test_theme_unit" in themes

    # Verify data
    loaded = themes["test_theme_unit"]
    assert loaded["base"] == [255, 0, 0]
    assert loaded["peak"] == [0, 255, 0]

    # Delete
    delete_custom_theme("test_theme_unit")
    themes_after = load_custom_themes()
    assert "test_theme_unit" not in themes_after

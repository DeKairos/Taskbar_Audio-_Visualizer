"""Focused UI tests for ui.settings_window (offscreen Qt, no desktop launch)."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from copy import deepcopy

import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtWidgets import QApplication, QFrame, QLabel, QScrollArea, QSlider

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config_manager import DEFAULTS  # noqa: E402


@pytest.fixture(scope="session")
def app():
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    return instance


@pytest.fixture
def make_window(app, monkeypatch):
    """Build a shown SettingsWindow at the 560x420 minimum size."""
    import ui.settings_window as settings_window

    created = []

    def _make(cfg=None, version="9.9.9"):
        monkeypatch.setattr(settings_window, "get_current_version", lambda: version)
        window = settings_window.SettingsWindow(
            deepcopy(DEFAULTS) if cfg is None else cfg
        )
        window.resize(560, 420)
        window.show()
        QApplication.processEvents()
        created.append(window)
        return window

    yield _make

    for window in created:
        window.close()
        window.deleteLater()
    QApplication.processEvents()


def _label_texts(widget):
    return [lbl.text() for lbl in widget.findChildren(QLabel)]


def test_quit_button_is_reachable_on_every_settings_page(make_window):
    window = make_window()
    requests = []
    window.quit_requested.connect(lambda: requests.append(True))
    for name in window._pages:
        window._navigate(name)
        QApplication.processEvents()
        button = window.quit_button
        assert button.isVisible()
        assert window.rect().contains(button.mapTo(window, button.rect().topLeft()))
        assert window.rect().contains(button.mapTo(window, button.rect().bottomRight()))
    window.quit_button.click()
    assert requests == [True]


def test_tall_pages_scroll_at_minimum_size(make_window):
    window = make_window()
    scroll = window._scroll_area

    assert isinstance(scroll, QScrollArea)
    assert scroll.widgetResizable()
    assert scroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff

    for page_name in ("General", "Visualizer"):
        window._navigate(page_name)
        QApplication.processEvents()
        assert scroll.verticalScrollBar().maximum() > 0, (
            f"{page_name} should scroll at 560x420"
        )


def test_short_pages_do_not_scroll_over_blank_space(make_window):
    """The scroll body tracks the visible page, not the tallest page.

    Pinning the content height to the tallest page kept a scrollbar (and
    blank space) alive on short pages such as Themes or About. Only the
    height relationship is asserted: an exact "no scrollbar" check depends
    on font metrics, which vary in the fontless offscreen test platform.
    """
    window = make_window()
    scroll = window._scroll_area
    content = scroll.widget()

    window._navigate("Visualizer")
    QApplication.processEvents()
    tallest = content.height()
    assert scroll.verticalScrollBar().maximum() > 0

    for page_name in ("Themes", "Media", "About"):
        window._navigate(page_name)
        QApplication.processEvents()
        assert content.height() < tallest, (
            f"{page_name} is shorter than Visualizer, so the scroll body "
            f"should shrink with it instead of staying at {tallest}px"
        )


def test_last_row_reachable_after_scrolling(make_window):
    window = make_window()
    window._navigate("Visualizer")
    QApplication.processEvents()

    scroll = window._scroll_area
    bar = scroll.verticalScrollBar()
    assert bar.maximum() > 0
    bar.setValue(bar.maximum())
    QApplication.processEvents()

    row = window._pages["Visualizer"].peak_cb.parentWidget()
    top_left = row.mapTo(scroll.viewport(), QPoint(0, 0))
    assert top_left.y() >= 0
    assert top_left.y() + row.height() <= scroll.viewport().height(), (
        "Peak Caps row must be fully visible after scrolling to the bottom"
    )


def test_readouts_show_initial_values_with_units(make_window):
    window = make_window()
    pages = window._pages

    general = pages["General"]
    assert general.timeout_slider.readout_label.text() == "5 s"
    assert general.height_slider.readout_label.text() == "40 px"

    visualizer = pages["Visualizer"]
    assert visualizer.bar_count_slider.readout_label.text() == "64"
    assert visualizer.width_slider.readout_label.text() == "40 %"
    assert visualizer.boost_slider.readout_label.text() == "1.35"
    assert visualizer.decay_slider.readout_label.text() == "0.045"

    audio = pages["Audio"]
    assert audio.freq_min_slider.readout_label.text() == "40 Hz"
    assert audio.freq_max_slider.readout_label.text() == "16000 Hz"

    media = pages["Media"]
    assert media.duration_slider.readout_label.text() == "3 s"
    assert media.size_slider.readout_label.text() == "36 px"


def test_readouts_follow_changes_and_storage_scaling_is_unchanged(make_window):
    window = make_window()
    pages = window._pages

    general = pages["General"]
    general.timeout_slider.setValue(12)
    assert general.timeout_slider.readout_label.text() == "12 s"
    assert window.cfg["auto_hide_timeout"] == 12.0

    visualizer = pages["Visualizer"]
    visualizer.bar_count_slider.setValue(96)
    assert visualizer.bar_count_slider.readout_label.text() == "96"
    assert window.cfg["bar_count"] == 96

    visualizer.boost_slider.setValue(150)
    assert visualizer.boost_slider.readout_label.text() == "1.50"
    assert window.cfg["low_end_boost"] == 1.5

    visualizer.decay_slider.setValue(60)
    assert visualizer.decay_slider.readout_label.text() == "0.060"
    assert window.cfg["peak_hold_decay"] == 0.06

    audio = pages["Audio"]
    audio.freq_max_slider.setValue(20000)
    assert audio.freq_max_slider.readout_label.text() == "20000 Hz"
    assert window.cfg["freq_max"] == 20000

    media = pages["Media"]
    media.size_slider.setValue(48)
    assert media.size_slider.readout_label.text() == "48 px"
    assert window.cfg["media_controls"]["size"] == 48


def test_width_mode_copy_follows_selection_without_config_rewrite(make_window):
    window = make_window()
    visualizer = window._pages["Visualizer"]

    assert visualizer.width_mode_combo.currentText() == "Auto (empty space)"
    assert visualizer.width_row.label_widget.text() == "Width %"
    assert visualizer.width_slider.readout_label.text() == "40 %"
    assert "empty space" in visualizer.width_row.description_widget.text()

    before = deepcopy(window.cfg)
    visualizer.width_mode_combo.setCurrentText("Fixed pixels")
    QApplication.processEvents()

    assert visualizer.width_row.label_widget.text() == "Width (px)"
    assert visualizer.width_slider.readout_label.text() == "40 px"
    assert "pixels" in visualizer.width_row.description_widget.text()

    after = deepcopy(window.cfg)
    changed = {key for key in after if before.get(key) != after.get(key)}
    assert changed == {"width_mode"}, f"only width_mode may change, got {changed}"
    assert after["width_mode"] == "fixed"
    assert after["width_percent"] == 40
    assert not (set(after) - set(DEFAULTS)), "no new config keys may appear"

    visualizer.width_mode_combo.setCurrentText("Percentage")
    QApplication.processEvents()
    assert visualizer.width_row.label_widget.text() == "Width %"
    assert visualizer.width_slider.readout_label.text() == "40 %"
    assert "Percentage of taskbar width" in visualizer.width_row.description_widget.text()
    assert window.cfg["width_mode"] == "percentage"
    assert window.cfg["width_percent"] == 40


def test_bass_boost_and_peak_decay_live_on_visualizer_page(make_window):
    window = make_window()
    visualizer = window._pages["Visualizer"]
    themes = window._pages["Themes"]

    # Grouping: width/alignment together, rendering-response values moved here.
    visualizer_labels = _label_texts(visualizer)
    assert "Width & Position" in visualizer_labels
    assert "Response & Emphasis" in visualizer_labels
    assert "Bass Boost" in visualizer_labels
    assert "Peak Decay Speed" in visualizer_labels

    theme_labels = _label_texts(themes)
    assert "Bass Boost" not in theme_labels
    assert "Peak Decay Speed" not in theme_labels
    assert not hasattr(themes, "boost_slider")
    assert not hasattr(themes, "decay_slider")

    # Same keys, same defaults, same storage scaling as before the move.
    assert window.cfg["low_end_boost"] == DEFAULTS["low_end_boost"]
    assert window.cfg["peak_hold_decay"] == DEFAULTS["peak_hold_decay"]

    visualizer.boost_slider.setValue(150)
    assert window.cfg["low_end_boost"] == 1.5
    assert window.cfg["peak_hold_decay"] == DEFAULTS["peak_hold_decay"]

    visualizer.decay_slider.setValue(75)
    assert window.cfg["peak_hold_decay"] == 0.075
    assert not (set(window.cfg) - set(DEFAULTS)), "no new config keys may appear"


def test_non_triplet_sensitivity_survives_unrelated_edits(make_window):
    cfg = deepcopy(DEFAULTS)
    cfg["sensitivity"] = 1.5
    window = make_window(cfg)
    visualizer = window._pages["Visualizer"]

    assert visualizer.sens_combo.currentText() == "Medium"

    # Unrelated edit on the same page must not rewrite the stored value.
    visualizer.bar_count_slider.setValue(96)
    assert window.cfg["sensitivity"] == 1.5

    # Unrelated edit on another page must not rewrite it either.
    window._pages["General"].timeout_slider.setValue(9)
    assert window.cfg["sensitivity"] == 1.5

    # An explicit pick still applies the documented triplet value.
    visualizer.sens_combo.setCurrentText("High")
    assert window.cfg["sensitivity"] == 2.0


def test_about_version_line_uses_resolver(make_window):
    window = make_window(version="9.9.9")
    text = window._pages["About"].info_label.text()
    assert "9.9.9" in text
    assert "2.0" not in text


def test_about_version_falls_back_when_resolver_has_no_version(make_window):
    window = make_window(version="")
    text = window._pages["About"].info_label.text()
    assert "development build" in text
    assert "2.0" not in text


def test_slider_ranges_are_unchanged(make_window):
    window = make_window()
    pages = window._pages

    expected = {
        pages["General"].timeout_slider: (1, 30),
        pages["General"].height_slider: (20, 80),
        pages["Visualizer"].bar_count_slider: (8, 128),
        pages["Visualizer"].width_slider: (10, 100),
        pages["Visualizer"].boost_slider: (80, 200),
        pages["Visualizer"].decay_slider: (10, 100),
        pages["Audio"].freq_min_slider: (20, 200),
        pages["Audio"].freq_max_slider: (4000, 20000),
        pages["Media"].duration_slider: (1, 10),
        pages["Media"].size_slider: (20, 60),
    }
    for slider, (minimum, maximum) in expected.items():
        assert isinstance(slider, QSlider)
        assert (slider.minimum(), slider.maximum()) == (minimum, maximum)


def test_secondary_text_uses_caption_size_and_secondary_alpha(make_window):
    window = make_window()
    description_style = window._pages["Visualizer"].width_row.description_widget.styleSheet()

    # Readable secondary typography: caption size (12) and Fluent secondary
    # text opacity (160/255) instead of the previous 11 px / 120 alpha.
    assert "font-size: 12px" in description_style
    assert "rgba(255,255,255,160)" in description_style

    readout_style = window._pages["General"].timeout_slider.readout_label.styleSheet()
    assert "font-size: 12px" in readout_style

    # The card/sidebar frame styling must survive the scroll-area wrap.
    assert window.findChildren(QFrame)

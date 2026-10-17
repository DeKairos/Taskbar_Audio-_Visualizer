"""Adaptive visual effects must preserve the spectrum's geometry."""
from types import SimpleNamespace

import numpy as np
import pytest

from visualizer_window import VisualizerWindow


@pytest.mark.parametrize('count', [16, 47, 64, 127])
def test_quality_changes_preserve_all_spectrum_bins_and_peak_positions(count):
    values = np.linspace(0.2, 1.0, count)
    caps = values + 0.1
    view = SimpleNamespace(fft_data=values, peak_caps=caps)

    # Exercise repeated transitions like those around the frame-cost thresholds.
    for quality in ['high', 'medium', 'high', 'low', 'medium', 'high']:
        view._quality_level = quality
        drawn, peaks = VisualizerWindow._sampled_bins(view)
        np.testing.assert_array_equal(drawn, values)
        np.testing.assert_array_equal(peaks, caps)


def test_quality_transitions_keep_rendered_bar_columns_in_place():
    columns = []
    painter = SimpleNamespace(
        setPen=lambda *args: None, setBrush=lambda *args: None,
        drawRoundedRect=lambda x, y, width, height, *args: columns.append((x, width)),
    )
    view = SimpleNamespace(
        cfg={'glow': False, 'peak_caps_enabled': False},
        fft_data=np.linspace(0.2, 1, 47), peak_caps=np.ones(47),
        _decay_progress=0, _display_level_ref=1,
        _stereo_split_gains=lambda: (1, 1),
        _resolve_theme=lambda: {'base': (50, 100, 150), 'peak': (100, 200, 255),
                               'glow': (80, 180, 240), 'rainbow': False},
        _bar_fill_brush=lambda *args: None,
    )
    for name in ('_sampled_bins', '_display_max_value', '_energy_norm'):
        method = getattr(VisualizerWindow, name)
        setattr(view, name, lambda *args, method=method: method(view, *args))
    layouts = []
    for quality in ['high', 'medium', 'low', 'high']:
        view._quality_level = quality
        columns.clear()
        VisualizerWindow._paint_bars(view, painter, 600, 40)
        layouts.append(columns.copy())
    assert len(layouts[0]) == 47
    assert all(layout == layouts[0] for layout in layouts)

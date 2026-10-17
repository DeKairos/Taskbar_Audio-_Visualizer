"""Compact transport controls must fit the card and match their hit targets."""
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QRect

from visualizer_window import VisualizerWindow


@pytest.mark.parametrize('height', [34, 40, 60])
@pytest.mark.parametrize('width', [120, 545, 1000])
@pytest.mark.parametrize('size', [16, 36, 64])
def test_compact_controls_fit_card_and_align_to_right(width, height, size):
    view = SimpleNamespace(cfg={'media_controls': {'size': size}})
    box = QRect(8, 3, width, height)
    controls = VisualizerWindow._compact_media_control_rects(view, box)
    previous = None
    for rect in controls.values():
        assert box.contains(rect)
        assert abs(rect.center().y() - box.center().y()) <= 1
        if previous is not None:
            assert previous.right() < rect.left()
        previous = rect
    assert controls['play'].center().x() >= box.center().x()
    assert 4 <= box.right() - controls['next'].right() <= 10


def test_painted_controls_and_click_targets_use_the_same_compact_rectangles(monkeypatch):
    import visualizer_window
    drawn = []
    painter = SimpleNamespace(**{name: lambda *args: None for name in (
        'setPen', 'setBrush', 'drawPath', 'save', 'restore', 'translate', 'scale', 'setFont')})
    painter.drawEllipse = lambda *args: None
    painter.drawText = lambda x, y, w, h, *args: drawn.append(QRect(x, y, w, h))
    actions = []
    view = SimpleNamespace(
        cfg={'media_controls': {}}, _media_overlay_alpha=1,
        _media_overlay_rect=lambda: QRect(8, 3, 545, 34),
        _media_cover_pixmap=None, media_monitor=None,
        button_scale={}, hovered_button=None, _button_target={},
        _resolve_theme=lambda: {'glow': (90, 200, 255)},
        _invoke_media_action=actions.append,
    )
    view._compact_media_control_rects = lambda box: VisualizerWindow._compact_media_control_rects(view, box)
    VisualizerWindow.draw_media_controls(view, painter)
    assert drawn == list(view.controls_rects.values())
    assert all(view._media_overlay_rect().contains(rect) for rect in drawn)
    monkeypatch.setattr(visualizer_window.QTimer, 'singleShot', lambda *args: None)
    monkeypatch.setattr(visualizer_window.time, 'monotonic', lambda: 123.0)
    for name, rect in view.controls_rects.items():
        center = rect.center()
        assert VisualizerWindow.handle_media_click(view, center.x(), center.y())
        assert actions[-1] == name
        assert view._media_overlay_started_at == 123.0

"""Combo mode — waveform on top half, frequency bars on bottom half."""
import numpy as np
from PyQt6.QtGui import QPainterPath, QColor, QPen, QLinearGradient, QPainter
from PyQt6.QtCore import QPointF, Qt
from .registry import register_mode


def _painter(vis, qp, w, h, params=None):
    params = params or {}
    split_ratio = float(params.get("split_ratio", 0.45))
    wave_width = float(params.get("wave_width", 2.0))

    bins, peak_caps = vis._sampled_bins()
    num = max(1, len(bins))
    max_v = vis._display_max_value(bins, peak_caps)

    theme = vis._resolve_theme() if hasattr(vis, "_resolve_theme") else None
    if not theme:
        return

    br, bg, bb = theme.get("base", (20, 180, 230))
    pr, pg, pb = theme.get("peak", (150, 250, 255))
    gr, gg, gb = theme.get("glow", (80, 200, 240))

    split_y = int(h * split_ratio)
    bar_region_h = h - split_y

    # ─── Waveform (top half) ───────────────────────────────────────
    points = []
    for i in range(num):
        norm = vis._energy_norm(bins[i], max_v)
        centered = (norm - 0.5) * 2.0
        x = int(i * w / (num - 1)) if num > 1 else 0
        mid = split_y / 2
        amp = split_y * 0.38
        y = int(mid - centered * amp)
        points.append(QPointF(x, y))

    if points:
        # Build smooth path
        path = QPainterPath()
        path.moveTo(points[0])
        for i in range(1, len(points)):
            p0 = points[max(i - 1, 0)]
            p1 = points[i]
            ctrl_x = (p0.x() + p1.x()) / 2
            path.cubicTo(QPointF(ctrl_x, p0.y()), QPointF(ctrl_x, p1.y()), p1)

        # Glow
        glow_pen = QPen(QColor(gr, gg, gb, 40), 8)
        glow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        qp.setPen(glow_pen)
        qp.setBrush(Qt.BrushStyle.NoBrush)
        qp.drawPath(path)

        # Main wave line
        grad = QLinearGradient(0, 0, w, 0)
        grad.setColorAt(0.0, QColor(br, bg, bb, 200))
        grad.setColorAt(0.5, QColor(gr, gg, gb, 230))
        grad.setColorAt(1.0, QColor(pr, pg, pb, 240))
        pen = QPen(QBrush(grad), wave_width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        qp.setPen(pen)
        qp.setBrush(Qt.BrushStyle.NoBrush)
        qp.drawPath(path)

        # Fill under wave
        fill = QPainterPath(path)
        fill.lineTo(QPointF(w, split_y))
        fill.lineTo(QPointF(0, split_y))
        fill.closeSubpath()
        fill_grad = QLinearGradient(0, 0, 0, split_y)
        fill_grad.setColorAt(0.0, QColor(pr, pg, pb, 30))
        fill_grad.setColorAt(1.0, QColor(br, bg, bb, 5))
        qp.setPen(Qt.PenStyle.NoPen)
        qp.setBrush(QBrush(fill_grad))
        qp.drawPath(fill)

    # ─── Divider line ──────────────────────────────────────────────
    divider_pen = QPen(QColor(gr, gg, gb, 40), 1)
    qp.setPen(divider_pen)
    qp.drawLine(0, split_y, w, split_y)

    # ─── Frequency bars (bottom half) ──────────────────────────────
    gap = 2
    bar_w = max(2, (w - gap * (num + 1)) / num)
    peak_caps_enabled = bool(vis.cfg.get("peak_caps_enabled", True))

    qp.setPen(Qt.PenStyle.NoPen)
    for i in range(num):
        norm = vis._energy_norm(bins[i], max_v)
        bar_h = norm * (bar_region_h - 6)
        if bar_h < 0.5:
            continue

        x = gap + i * (bar_w + gap)
        y = split_y + bar_region_h - bar_h - 2

        t = i / max(1, num - 1)
        r = int(br + t * (pr - br))
        g = int(bg + t * (pg - bg))
        b = int(bb + t * (pb - bb))

        qp.setBrush(QColor(r, g, b, 180))
        qp.drawRoundedRect(int(x), int(y), int(bar_w), int(bar_h), 2, 2)

        # Peak cap
        if peak_caps_enabled:
            cap_norm = vis._energy_norm(peak_caps[i], max_v)
            cap_y = split_y + bar_region_h - cap_norm * (bar_region_h - 6) - 2
            if cap_y < y - 1:
                cap_alpha = int(140 + cap_norm * 90)
                qp.setBrush(QColor(pr, pg, pb, cap_alpha))
                qp.drawRoundedRect(int(x), int(cap_y), int(bar_w), 2, 1, 1)


register_mode(
    "combo", "Combo", _painter,
    default_params={"split_ratio": 0.45, "wave_width": 2.0},
    tooltip="Waveform on top half, frequency bars on bottom half."
)

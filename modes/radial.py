"""Radial Spectrum mode — circular bars arranged around the center."""
import math
from PyQt6.QtGui import QColor
from .registry import register_mode


def _painter(vis, qp, w, h, params=None):
    params = params or {}
    radius = float(params.get("radius", 0.35))  # fraction of min(w,h)
    bar_width = float(params.get("bar_width", 0.04))

    bins, caps = vis._sampled_bins()
    total = max(1, len(bins))
    max_v = vis._display_max_value(bins, caps)
    cx = w / 2.0
    cy = h / 2.0
    base_r = min(w, h) * radius

    qp.save()
    for i, v in enumerate(bins):
        theta = (i / total) * (2.0 * math.pi)
        norm = vis._energy_norm(v, max_v)
        bar_len = base_r * (0.12 + 0.8 * norm)

        x1 = cx + math.cos(theta) * base_r
        y1 = cy + math.sin(theta) * base_r
        x2 = cx + math.cos(theta) * (base_r + bar_len)
        y2 = cy + math.sin(theta) * (base_r + bar_len)

        color = QColor(160, 200, 255, 220 - int(norm * 120))
        qp.setPen(color)
        qp.drawLine(int(x1), int(y1), int(x2), int(y2))

    qp.restore()


register_mode("radial", "Radial Spectrum", _painter, default_params={"radius": 0.35, "bar_width": 0.04}, tooltip="Circular spectrum with radial bars.")

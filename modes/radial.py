"""Radial Spectrum mode — circular bars arranged around the center."""
import math
from PyQt6.QtGui import QColor
from .registry import register_mode


def _painter(vis, qp, w, h, params=None):
    params = params or {}
    radius = float(params.get("radius", 0.35))
    bar_width = float(params.get("bar_width", 0.04))

    bins, caps = vis._sampled_bins()
    total = max(1, len(bins))
    max_v = vis._display_max_value(bins, caps)
    cx = w / 2.0
    cy = h / 2.0
    base_r = min(w, h) * radius

    theme = vis._resolve_theme() if hasattr(vis, "_resolve_theme") else None
    if theme:
        br, bg, bb = theme.get("base", (40, 60, 100))
        pr, pg, pb = theme.get("peak", (160, 200, 255))
        gr, gg, gb = theme.get("glow", (80, 200, 240))
    else:
        br, bg, bb = 40, 60, 100
        pr, pg, pb = 160, 200, 255
        gr, gg, gb = 80, 200, 240

    qp.save()
    for i, v in enumerate(bins):
        theta = (i / total) * (2.0 * math.pi)
        norm = vis._energy_norm(v, max_v)
        bar_len = base_r * (0.12 + 0.8 * norm)

        x1 = cx + math.cos(theta) * base_r
        y1 = cy + math.sin(theta) * base_r
        x2 = cx + math.cos(theta) * (base_r + bar_len)
        y2 = cy + math.sin(theta) * (base_r + bar_len)

        t = i / max(1, total - 1)
        r = int(br + t * (pr - br))
        g = int(bg + t * (pg - bg))
        b = int(bb + t * (pb - bb))
        alpha = int(160 + norm * 80)

        color = QColor(r, g, b, alpha)
        qp.setPen(color)
        qp.drawLine(int(x1), int(y1), int(x2), int(y2))

        # Glow dot at tip when high energy
        if norm > 0.4 and vis.cfg.get("glow", True):
            dot_sz = 2 + norm * 3
            dot_alpha = int(norm * 120)
            qp.setPen(QColor(gr, gg, gb, dot_alpha))
            qp.setBrush(QColor(gr, gg, gb, dot_alpha))
            qp.drawEllipse(int(x2 - dot_sz / 2), int(y2 - dot_sz / 2), int(dot_sz), int(dot_sz))

    qp.restore()


register_mode(
    "radial", "Radial Spectrum", _painter,
    default_params={"radius": 0.35, "bar_width": 0.04},
    tooltip="Circular spectrum with radial bars."
)

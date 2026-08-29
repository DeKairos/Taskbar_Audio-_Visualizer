"""Radar Sweep mode — rotating wedge that highlights bands under the sweep."""
import math
import time
from PyQt6.QtGui import QColor, QPainterPath
from .registry import register_mode


def _painter(vis, qp, w, h, params=None):
    params = params or {}
    speed = float(params.get("speed", 0.9))
    sweep_width = float(params.get("sweep_width", 0.28))

    bins, caps = vis._sampled_bins()
    total = max(1, len(bins))
    max_v = vis._display_max_value(bins, caps)
    cx = w / 2.0
    cy = h / 2.0
    radius = min(w, h) * 0.42

    theme = vis._resolve_theme() if hasattr(vis, "_resolve_theme") else None
    if theme:
        br, bg, bb = theme.get("base", (40, 60, 100))
        pr, pg, pb = theme.get("peak", (160, 200, 255))
        gr, gg, gb = theme.get("glow", (80, 200, 240))
    else:
        br, bg, bb = 40, 60, 100
        pr, pg, pb = 160, 200, 255
        gr, gg, gb = 80, 200, 240

    t = time.time() * speed
    angle = (t % 1.0) * 2.0 * math.pi

    qp.save()
    # Draw faint circular background
    qp.setPen(QColor(br, bg, bb, 120))
    qp.setBrush(QColor(br // 2, bg // 2, bb // 2, 60))
    qp.drawEllipse(int(cx - radius), int(cy - radius), int(radius * 2), int(radius * 2))

    # Draw bars around circle
    for i, v in enumerate(bins):
        theta = (i / total) * (2.0 * math.pi)
        norm = vis._energy_norm(v, max_v)
        bar_len = radius * (0.12 + 0.7 * norm)
        x1 = cx + math.cos(theta) * (radius - bar_len)
        y1 = cy + math.sin(theta) * (radius - bar_len)
        x2 = cx + math.cos(theta) * radius
        y2 = cy + math.sin(theta) * radius

        # Highlight if within sweep wedge
        dtheta = min(abs((theta - angle) % (2 * math.pi)), abs((angle - theta) % (2 * math.pi)))
        is_high = dtheta < (sweep_width * math.pi)
        if is_high:
            color = QColor(pr, pg, pb, 220)
        else:
            t_bar = i / max(1, total - 1)
            r = int(br + t_bar * (pr - br))
            g = int(bg + t_bar * (pg - bg))
            b = int(bb + t_bar * (pb - bb))
            color = QColor(r, g, b, 160)
        qp.setPen(color)
        qp.drawLine(int(x1), int(y1), int(x2), int(y2))

    # Draw sweep line
    sweep_len = radius * 1.05
    sx = cx + math.cos(angle) * sweep_len
    sy = cy + math.sin(angle) * sweep_len
    sweep_pen = QColor(gr, gg, gb, 180)
    qp.setPen(sweep_pen)
    qp.drawLine(int(cx), int(cy), int(sx), int(sy))

    qp.restore()


register_mode(
    "radar", "Radar Sweep", _painter,
    default_params={"speed": 0.9, "sweep_width": 0.28},
    tooltip="Rotating radar sweep highlights active bands."
)

"""Radar Sweep mode — rotating wedge that highlights bands under the sweep."""
import math
import time
from PyQt6.QtGui import QColor, QPainterPath
from .registry import register_mode


def _painter(vis, qp, w, h, params=None):
    params = params or {}
    speed = float(params.get("speed", 0.9))
    sweep_width = float(params.get("sweep_width", 0.28))  # fraction of circle

    bins, caps = vis._sampled_bins()
    total = max(1, len(bins))
    max_v = vis._display_max_value(bins, caps)
    cx = w / 2.0
    cy = h / 2.0
    radius = min(w, h) * 0.42

    t = time.time() * speed
    angle = (t % 1.0) * 2.0 * math.pi

    qp.save()
    # Draw faint circular background
    qp.setPen(QColor(80, 80, 90, 120))
    qp.setBrush(QColor(20, 24, 30, 60))
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
        color = QColor(180, 200, 255, 220) if is_high else QColor(120, 140, 170, 160)
        qp.setPen(color)
        qp.drawLine(int(x1), int(y1), int(x2), int(y2))

    qp.restore()


register_mode("radar", "Radar Sweep", _painter, default_params={"speed": 0.9, "sweep_width": 0.28}, tooltip="Rotating radar sweep highlights active bands.")

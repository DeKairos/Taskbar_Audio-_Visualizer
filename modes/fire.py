"""Fire / Plasma mode — heat-map style bars with flickering flame tips."""
import math
import time
import random
import numpy as np
from PyQt6.QtGui import QColor, QPainterPath, QPainter
from PyQt6.QtCore import QRectF, QPointF
from .registry import register_mode

# Persistent state for flicker
_prev_bars = None


def _painter(vis, qp, w, h, params=None):
    global _prev_bars

    params = params or {}
    flicker_speed = float(params.get("flicker_speed", 2.0))
    flame_height = float(params.get("flame_height", 1.0))

    bins, _caps = vis._sampled_bins()
    num = max(1, len(bins))
    max_v = vis._display_max_value(bins)

    theme = vis._resolve_theme() if hasattr(vis, "_resolve_theme") else None
    if not theme:
        return

    # Use warm colors: base = deep red, peak = bright yellow-white
    base = theme.get("base", (180, 30, 0))
    mid = theme.get("glow", (255, 120, 0))
    peak = theme.get("peak", (255, 255, 60))

    gap = 2
    bar_w = max(2, (w - gap * (num + 1)) / num)
    now = time.time()

    # Smooth and add flicker
    values = np.array([vis._energy_norm(bins[i], max_v) for i in range(num)])

    if _prev_bars is None or len(_prev_bars) != num:
        _prev_bars = values.copy()
    else:
        _prev_bars = _prev_bars * 0.7 + values * 0.3

    smoothed = _prev_bars.copy()

    qp.save()
    qp.setPen(QColor(0, 0, 0, 0))

    for i in range(num):
        x = gap + i * (bar_w + gap)
        norm = smoothed[i]

        # Flicker: add per-bar noise
        flicker = math.sin(now * flicker_speed + i * 0.7) * 0.08
        flicker += random.uniform(-0.04, 0.04)
        norm = max(0.0, min(1.0, norm + flicker))

        bar_h = norm * (h - 8) * flame_height
        if bar_h < 1:
            continue

        y = h - bar_h - 2

        # Gradient from bottom (deep red) to top (yellow)
        segment_step = 8 if getattr(vis, "_quality_level", "high") == "low" else 4
        num_segments = max(1, int(bar_h / segment_step))
        seg_h = bar_h / num_segments

        for s in range(num_segments):
            t = s / max(1, num_segments - 1)
            # Color transition: base -> mid -> peak
            if t < 0.5:
                t2 = t * 2.0
                r = int(base[0] + t2 * (mid[0] - base[0]))
                g = int(base[1] + t2 * (mid[1] - base[1]))
                b = int(base[2] + t2 * (mid[2] - base[2]))
            else:
                t2 = (t - 0.5) * 2.0
                r = int(mid[0] + t2 * (peak[0] - mid[0]))
                g = int(mid[1] + t2 * (peak[1] - mid[1]))
                b = int(mid[2] + t2 * (peak[2] - mid[2]))

            alpha = int(200 - t * 60)
            seg_y = y + s * seg_h

            # Add wavy displacement at tips
            if t > 0.6:
                wave = math.sin(now * 3 + i * 1.2 + s * 0.5) * 3 * t
                x_off = wave
            else:
                x_off = 0

            qp.setBrush(QColor(r, g, b, alpha))
            seg_w = bar_w * (1.0 - t * 0.3)
            qp.drawRoundedRect(
                int(x + x_off + (bar_w - seg_w) / 2),
                int(seg_y),
                int(seg_w),
                int(seg_h + 1),
                1, 1
            )

        # Ember particles at top
        if norm > 0.4 and getattr(vis, "_quality_level", "high") != "low":
            for _ in range(int(norm * 3)):
                ex = x + random.uniform(0, bar_w)
                ey = y + random.uniform(-6, 0)
                esz = random.uniform(1, 2.5)
                ea = int(random.randint(80, 200) * norm)
                qp.setBrush(QColor(peak[0], peak[1], peak[2], ea))
                qp.drawEllipse(int(ex), int(ey), int(esz), int(esz))

    qp.restore()


register_mode(
    "fire", "Fire", _painter,
    default_params={"flicker_speed": 2.0, "flame_height": 1.0},
    tooltip="Heat-map fire bars with flickering flame tips and embers."
)

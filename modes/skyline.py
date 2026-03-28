"""Skyline mode — layered silhouette mountains driven by band envelopes."""
import math
import time
from PyQt6.QtGui import QPainterPath, QColor, QPainter
from .registry import register_mode


def _painter(vis, qp, w, h, params=None):
    params = params or {}
    layers = int(params.get("layers", 3))
    smoothing = float(params.get("smoothing", 0.6))

    bins, caps = vis._sampled_bins()
    total = max(1, len(bins))
    max_v = vis._display_max_value(bins, caps)

    theme = vis._resolve_theme() if hasattr(vis, "_resolve_theme") else None

    qp.save()
    try:
        qp.setRenderHint(QPainter.RenderHint.Antialiasing)
    except Exception:
        pass

    for layer in range(layers):
        path = QPainterPath()
        path.moveTo(0, h)
        for i, v in enumerate(bins):
            x = (i / max(1, total - 1)) * w
            norm = vis._energy_norm(v, max_v)
            # layer affects height and smooth attenuation
            layer_scale = 0.35 + (0.55 * (layer / max(1, layers - 1)))
            y = h - int(norm * (h * layer_scale))
            if i == 0:
                path.lineTo(x, y)
            else:
                path.lineTo(x, y)
        path.lineTo(w, h)
        # Colour the layer using the active theme (fall back to hardcoded hues).
        if theme:
            base = theme.get("base", (40, 60, 100))
            peak = theme.get("peak", (160, 200, 255))
        else:
            base = (40, 60, 100)
            peak = (160, 200, 255)

        layer_factor = (layer / max(1, layers - 1)) if layers > 1 else 0.0
        r = int(base[0] + layer_factor * (peak[0] - base[0]))
        g = int(base[1] + layer_factor * (peak[1] - base[1]))
        b = int(base[2] + layer_factor * (peak[2] - base[2]))
        alpha = int(140 / (1 + layer))
        qp.fillPath(path, QColor(r, g, b, alpha))

    qp.restore()


register_mode("skyline", "Skyline", _painter, default_params={"layers": 3, "smoothing": 0.6}, tooltip="Layered mountain silhouettes driven by the spectrum.")

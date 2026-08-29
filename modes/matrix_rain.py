"""Matrix Rain mode — falling character columns driven by frequency bands."""
import math
import time
import random
from PyQt6.QtGui import QColor, QFont, QPainter
from .registry import register_mode

# Persistent state: columns
_columns = None

# Characters to use
_CHARS = "ﾊﾐﾋｰｳｼﾅﾓﾆｻﾜﾂｵﾘｱﾎﾃﾏｹﾒｴｶｷﾑﾕﾗｾﾈｽﾀﾇﾍ0123456789ABCDEF"
_GLITCH = "!@#$%^&*()[]{}<>+=?/\\|~`"


class _Column:
    __slots__ = ("head_y", "speed", "chars", "trail_len")

    def __init__(self, speed, trail_len):
        self.head_y = random.uniform(-1.0, 0.0)
        self.speed = speed
        self.trail_len = trail_len
        self.chars = [random.choice(_CHARS) for _ in range(trail_len)]


def _painter(vis, qp, w, h, params=None):
    global _columns

    params = params or {}
    char_size = int(params.get("char_size", 12))
    max_trail = int(params.get("trail_length", 20))
    density = float(params.get("density", 0.8))

    bins, _caps = vis._sampled_bins()
    num = max(1, len(bins))
    max_v = vis._display_max_value(bins)

    theme = vis._resolve_theme() if hasattr(vis, "_resolve_theme") else {}
    base_r, base_g, base_b = theme.get("base", (20, 200, 50))
    peak_r, peak_g, peak_b = theme.get("peak", (120, 255, 140))

    num_cols = max(8, int(w / char_size))
    if _columns is None or len(_columns) != num_cols:
        _columns = []
        for _ in range(num_cols):
            _columns.append(_Column(
                speed=random.uniform(0.3, 1.2),
                trail_len=random.randint(8, max_trail)
            ))

    now = time.time()
    font = QFont("Consolas", char_size - 2)

    qp.save()
    qp.setFont(font)

    for ci, col in enumerate(_columns):
        x = ci * char_size
        if x > w:
            continue

        # Map column to a frequency band
        band_idx = int((ci / num_cols) * num)
        band_idx = min(band_idx, num - 1)
        norm = vis._energy_norm(bins[band_idx], max_v) if band_idx < len(bins) else 0

        # Speed driven by band energy
        speed = col.speed * (0.3 + norm * 2.5)
        col.head_y += speed * 0.016

        # Randomly mutate characters
        if random.random() < 0.05 + norm * 0.2:
            idx = random.randint(0, len(col.chars) - 1)
            if random.random() < 0.1:
                col.chars[idx] = random.choice(_GLITCH)
            else:
                col.chars[idx] = random.choice(_CHARS)

        # Reset when past bottom
        if col.head_y > 1.3:
            col.head_y = random.uniform(-0.5, -0.1)
            col.trail_len = random.randint(8, max_trail)
            col.chars = [random.choice(_CHARS) for _ in range(col.trail_len)]
            col.speed = random.uniform(0.3, 1.2)

        # Draw trail
        for ti in range(col.trail_len):
            char_y = col.head_y * h - ti * char_size
            if char_y < -char_size or char_y > h:
                continue

            t = ti / max(1, col.trail_len - 1)

            if ti == 0:
                # Head: bright white-ish
                r = min(255, int(peak_r + (255 - peak_r) * 0.5))
                g = min(255, int(peak_g + (255 - peak_g) * 0.5))
                b = min(255, int(peak_b + (255 - peak_b) * 0.5))
                alpha = 255
            else:
                # Trail: fade from peak to base
                r = int(peak_r * (1 - t) + base_r * t)
                g = int(peak_g * (1 - t) + base_g * t)
                b = int(peak_b * (1 - t) + base_b * t)
                alpha = int(200 * (1 - t * t))

            qp.setPen(QColor(r, g, b, alpha))
            qp.drawText(int(x), int(char_y), char_size, char_size,
                        0x0084, col.chars[ti % len(col.chars)])

    qp.restore()


register_mode(
    "matrix_rain", "Matrix Rain", _painter,
    default_params={"char_size": 12, "trail_length": 20, "density": 0.8},
    tooltip="Falling character columns driven by frequency bands, Matrix-style."
)

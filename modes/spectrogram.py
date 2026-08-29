"""Spectrogram / Waterfall mode — scrolling heatmap of frequency over time."""
import numpy as np
from PyQt6.QtGui import QImage, QColor, QPainter
from PyQt6.QtCore import QRect
from .registry import register_mode

# Module-level state: ring buffer of recent FFT frames
_history = None
_history_idx = 0
_history_filled = False


def _ensure_history(num_bars: int, frames: int = 120):
    """Allocate or reallocate the ring buffer."""
    global _history, _history_idx, _history_filled
    if _history is None or _history.shape != (frames, num_bars):
        _history = np.zeros((frames, num_bars), dtype=np.float32)
        _history_idx = 0
        _history_filled = False
    return _history


def _make_heatmap_color(t: float, theme: dict) -> tuple:
    """Map normalized value t (0-1) to an RGB color using the theme."""
    br, bg, bb = theme.get("base", (10, 10, 40))
    gr, gg, gb = theme.get("glow", (60, 100, 200))
    pr, pg, pb = theme.get("peak", (255, 255, 100))

    t = max(0.0, min(1.0, t))
    if t < 0.5:
        t2 = t * 2.0
        return (
            int(br + t2 * (gr - br)),
            int(bg + t2 * (gg - bg)),
            int(bb + t2 * (gb - bb)),
        )
    else:
        t2 = (t - 0.5) * 2.0
        return (
            int(gr + t2 * (pr - gr)),
            int(gg + t2 * (pg - gg)),
            int(gb + t2 * (pb - gb)),
        )


def _painter(vis, qp, w, h, params=None):
    global _history, _history_idx, _history_filled

    params = params or {}
    num_bars = int(params.get("bars", 64))
    _ensure_history(num_bars)

    bins, _caps = vis._sampled_bins()
    total = max(1, len(bins))
    max_v = vis._display_max_value(bins)

    # Downsample/interpolate bins to num_bars
    indices = np.linspace(0, total - 1, num_bars).astype(int)
    sampled = bins[indices] if len(bins) > 0 else np.zeros(num_bars)

    # Normalize
    norms = np.array([vis._energy_norm(v, max_v) for v in sampled], dtype=np.float32)

    # Store in ring buffer
    _history[_history_idx] = norms
    _history_idx = (_history_idx + 1) % _history.shape[0]
    if _history_idx == 0:
        _history_filled = True

    theme = vis._resolve_theme() if hasattr(vis, "_resolve_theme") else {}

    # Build colormap lookup (256 entries)
    colormap = np.zeros((256, 4), dtype=np.uint8)
    for i in range(256):
        t = i / 255.0
        r, g, b = _make_heatmap_color(t, theme)
        alpha = 20 + int(235 * t)
        colormap[i] = [b, g, r, alpha]  # QImage.Format_ARGB32 is BGRA

    # Determine how many rows we have filled
    num_rows = _history.shape[0] if _history_filled else _history_idx

    if num_rows == 0:
        return

    # Create a QImage from the history buffer
    # Each column in the image = one bar position, each row = one time frame (newest at bottom)
    img_w = min(num_bars, 256)
    img_h = min(num_rows, 200)

    # Sample the history to image dimensions
    row_indices = np.linspace(num_rows - img_h, num_rows - 1, img_h).astype(int)
    col_indices = np.linspace(0, num_bars - 1, img_w).astype(int)

    # Build pixel data with NumPy indexing instead of nested Python loops.
    history_indices = (_history_idx - num_rows + row_indices) % _history.shape[0]
    values = _history[history_indices[:, None], col_indices[None, :]]
    color_indices = np.clip((values * 255).astype(np.int16), 0, 255)
    pixel_data = colormap[color_indices]

    # Create QImage
    raw = pixel_data.tobytes()
    img = QImage(raw, img_w, img_h, img_w * 4, QImage.Format.Format_ARGB32)
    transformation = (
        Qt.TransformationMode.FastTransformation
        if getattr(vis, "_quality_level", "high") == "low"
        else Qt.TransformationMode.SmoothTransformation
    )
    scaled = img.scaled(
        w, h,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        transformation,
    )

    qp.drawImage(QRect(0, 0, w, h), scaled)


# Need Qt import for scaling
from PyQt6.QtCore import Qt


register_mode(
    "spectrogram", "Spectrogram", _painter,
    default_params={"bars": 64},
    tooltip="Scrolling heatmap of frequency content over time."
)

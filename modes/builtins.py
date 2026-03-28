"""Register adapters that wrap the existing VisualizerWindow painters and load new built-in modes."""
from .registry import register_mode

# Register adapters for existing painter methods on VisualizerWindow.
register_mode("bars", "Bars", lambda vis, qp, w, h, params=None: vis._paint_bars(qp, w, h), default_params={})
register_mode("wave", "Wave", lambda vis, qp, w, h, params=None: vis._paint_waveform(qp, w, h), default_params={})
register_mode("mirror", "Mirror", lambda vis, qp, w, h, params=None: vis._paint_mirror(qp, w, h), default_params={})
register_mode("dot_matrix", "Dot Matrix", lambda vis, qp, w, h, params=None: vis._paint_dot_matrix(qp, w, h), default_params={})
# Expose legacy painters as adapters where meaningful. Note: oscilloscope and
# mirror_tunnel are intentionally omitted - use `wave` and `mirror` instead.

# Register the new built-in modes by importing their modules (they call register_mode on import).
try:
    from . import skyline  # noqa: F401
except Exception:
    # Import errors should not break startup; modes will simply not be registered.
    pass

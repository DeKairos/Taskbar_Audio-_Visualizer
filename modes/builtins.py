"""Register the supported visualizer modes."""
import importlib

from .registry import register_mode

# Keep the mode surface intentionally small: these are the supported modes.
register_mode("bars", "Bars", lambda vis, qp, w, h, params=None: vis._paint_bars(qp, w, h), default_params={})
register_mode("wave", "Wave", lambda vis, qp, w, h, params=None: vis._paint_waveform(qp, w, h), default_params={})
register_mode("mirror", "Mirror", lambda vis, qp, w, h, params=None: vis._paint_mirror(qp, w, h), default_params={})
register_mode("dot_matrix", "Dot Matrix", lambda vis, qp, w, h, params=None: vis._paint_dot_matrix(qp, w, h), default_params={})

try:
    importlib.import_module(".skyline", __package__)
except Exception:
    # Keep the four core modes available if Skyline's optional module fails.
    pass

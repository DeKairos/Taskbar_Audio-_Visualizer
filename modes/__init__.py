"""Modes package — exposes registry helpers and loads builtins on demand."""
import logging

from .registry import register_mode, get_mode, list_modes, get_default_params

logger = logging.getLogger(__name__)

def load_builtin_modes():
    """Import and register the built-in modes.

    Importing `builtins` will execute its top-level registration code.
    """
    try:
        import importlib
        importlib.import_module('.builtins', __package__)
    except Exception:
        # If import fails, leave the registry usable and expose the cause.
        logger.exception("Failed to load built-in visualizer modes")

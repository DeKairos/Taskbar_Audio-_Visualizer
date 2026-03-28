"""Modes package — exposes registry helpers and loads builtins on demand."""
from .registry import register_mode, get_mode, list_modes, get_default_params

def load_builtin_modes():
    """Import and register the built-in modes.

    Importing `builtins` will execute its top-level registration code.
    """
    try:
        import importlib
        importlib.import_module('.builtins', __package__)
    except Exception:
        # If import fails, leave registry empty — callers should handle None.
        pass

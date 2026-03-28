"""Simple in-memory registry for visualizer modes.

Each registered mode is a dict with keys:
 - id: mode id string
 - label: display label
 - painter: callable(vis, qp, w, h, params)
 - default_params: dict
 - tooltip: optional string
"""
from typing import Callable, Dict, Any

_REGISTRY: Dict[str, Dict[str, Any]] = {}


def register_mode(mode_id: str, label: str, painter: Callable, default_params: Dict[str, Any] = None, tooltip: str = ""):
    _REGISTRY[mode_id] = {
        "id": mode_id,
        "label": label,
        "painter": painter,
        "default_params": default_params or {},
        "tooltip": tooltip or "",
    }


def get_mode(mode_id: str):
    return _REGISTRY.get(mode_id)


def list_modes():
    return list(_REGISTRY.values())


def get_default_params(mode_id: str):
    m = get_mode(mode_id)
    return m["default_params"] if m else {}

"""Tests for modes.registry module."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_registry_basic():
    from modes.registry import register_mode, get_mode, list_modes
    register_mode("test_mode", "Test Mode", lambda v, p, w, h: None)
    mode = get_mode("test_mode")
    assert mode is not None
    assert mode["id"] == "test_mode"
    assert mode["label"] == "Test Mode"
    assert callable(mode["painter"])


def test_registry_list():
    from modes.registry import list_modes
    modes = list_modes()
    assert isinstance(modes, list)


def test_registry_default_params():
    from modes.registry import register_mode, get_default_params
    register_mode("test_params", "Test Params", lambda v, p, w, h: None,
                   default_params={"speed": 1.0, "size": 10})
    params = get_default_params("test_params")
    assert params == {"speed": 1.0, "size": 10}


def test_registry_missing_mode():
    from modes.registry import get_mode
    assert get_mode("nonexistent_mode_xyz") is None


def test_builtin_modes_load():
    from modes import load_builtin_modes
    from modes.registry import get_mode
    load_builtin_modes()

    expected_modes = ["bars", "wave", "mirror", "dot_matrix", "skyline"]
    for mode_id in expected_modes:
        m = get_mode(mode_id)
        assert m is not None, f"Mode '{mode_id}' not registered!"
        assert "painter" in m
        assert callable(m["painter"])

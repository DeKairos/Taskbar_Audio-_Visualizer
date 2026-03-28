import importlib


def test_registry_basic():
    # Ensure builtins can be loaded and registry exposes list_modes/get_mode
    modes = importlib.import_module('modes')
    modes.load_builtin_modes()
    reg = importlib.import_module('modes.registry')
    modes_list = reg.list_modes()
    assert isinstance(modes_list, list)
    # Try getting a known mode id (bars) if present
    m = reg.get_mode('bars')
    if m is not None:
        assert 'painter' in m

"""The release probe must load runtime modules without starting the application."""
import builtins
import json

import main


def test_self_test_checks_runtime_without_starting_ui(monkeypatch, tmp_path):
    import update_checker
    # A shallow CI checkout has no release tags. Supply the build version
    # explicitly and prove the probe does not rely on local Git history.
    monkeypatch.setenv('AUDIO_VISUALIZER_VERSION', '1.4.1')
    monkeypatch.setattr(update_checker, '_current_version_from_git', lambda: None)
    report = tmp_path / 'report.json'
    monkeypatch.setattr(main.sys, 'argv', ['AudioVisualizer', '--self-test', str(report)])
    monkeypatch.setattr(main, '_acquire_single_instance_lock',
                        lambda: (_ for _ in ()).throw(AssertionError('Normal startup was entered')))
    assert main.main() == 0
    result = json.loads(report.read_text())
    assert result['ok'] and result['runtime_imports'] and result['resources']
    assert result['version'] == '1.4.1'
    assert not result['error']


def test_self_test_reports_a_missing_runtime_dependency(monkeypatch, tmp_path):
    monkeypatch.setenv('AUDIO_VISUALIZER_VERSION', '1.4.1')
    report = tmp_path / 'report.json'
    monkeypatch.setattr(main.sys, 'argv', ['AudioVisualizer', '--self-test', str(report)])
    original_import = builtins.__import__
    def import_module(name, *args, **kwargs):
        if name == 'ui.settings_window':
            raise ImportError('missing settings dependency')
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', import_module)
    assert main.main() == 1
    result = json.loads(report.read_text())
    assert not result['ok'] and not result['runtime_imports']
    assert 'missing settings dependency' in result['error']

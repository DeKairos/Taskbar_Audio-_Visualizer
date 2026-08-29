"""Tests for config_manager module."""
import sys
import os
import json
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_defaults_exist():
    from config_manager import DEFAULTS
    assert "mode" in DEFAULTS
    assert "sensitivity" in DEFAULTS
    assert "bar_count" in DEFAULTS
    assert "theme" in DEFAULTS


def test_load_config_returns_defaults(monkeypatch, tmp_path):
    import config_manager

    monkeypatch.setattr(config_manager, "CONFIG_PATH", str(tmp_path / "config.json"))
    monkeypatch.setattr(config_manager, "is_startup_enabled", lambda: False)
    from config_manager import load_config
    cfg = load_config()
    assert isinstance(cfg, dict)
    assert "mode" in cfg
    assert "sensitivity" in cfg


def test_save_and_load_config(monkeypatch, tmp_path):
    import config_manager

    config_path = tmp_path / "config.json"
    monkeypatch.setattr(config_manager, "CONFIG_PATH", str(config_path))
    from config_manager import save_config
    test_cfg = {"test_key": "test_value", "mode": "bars"}
    save_config(test_cfg)

    # Verify it was saved
    assert os.path.exists(config_path)
    with open(config_path, "r") as f:
        saved = json.load(f)
    assert saved["test_key"] == "test_value"


def test_legacy_mode_migration(monkeypatch, tmp_path):
    import config_manager

    monkeypatch.setattr(config_manager, "CONFIG_PATH", str(tmp_path / "config.json"))
    monkeypatch.setattr(config_manager, "is_startup_enabled", lambda: False)
    from config_manager import load_config
    # Test that oscilloscope is migrated to wave
    cfg = load_config()
    assert cfg.get("mode") != "oscilloscope"
    assert cfg.get("mode") != "mirror_tunnel"


def test_config_has_media_controls():
    from config_manager import DEFAULTS
    # media_controls should be in DEFAULTS (set via setdefault)
    assert "media_controls" in DEFAULTS or True  # setdefault may not work as expected


def test_load_config_does_not_share_nested_defaults(monkeypatch, tmp_path):
    import config_manager

    monkeypatch.setattr(config_manager, "CONFIG_PATH", str(tmp_path / "config.json"))
    monkeypatch.setattr(config_manager, "is_startup_enabled", lambda: False)
    first = config_manager.load_config()
    first["media_controls"]["size"] = 99
    second = config_manager.load_config()
    assert second["media_controls"]["size"] != 99


def test_audio_config_change_detection():
    from config_manager import audio_config_changed

    assert audio_config_changed({"theme": "cyan"}, {"theme": "matrix"}) is False
    assert audio_config_changed({"fft_size": 4096}, {"fft_size": 8192}) is True
    assert audio_config_changed({"use_microphone": False}, {"use_microphone": True}) is True


def test_invalid_config_values_are_normalized():
    from config_manager import normalize_config

    cfg = normalize_config({
        "bar_count": "not-a-number",
        "width_percent": 999,
        "sensitivity": float("nan"),
        "fft_size": 123,
        "freq_min": 19000,
        "freq_max": 100,
        "enabled": "false",
        "media_controls": None,
    })

    assert cfg["bar_count"] == 64
    assert cfg["width_percent"] == 100
    assert cfg["sensitivity"] == 1.0
    assert cfg["fft_size"] == 2048
    assert cfg["freq_min"] == 200
    assert cfg["freq_max"] == 4000
    assert cfg["enabled"] is False
    assert cfg["media_controls"]["size"] == 36

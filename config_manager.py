"""
config_manager.py — Persists settings to JSON, manages Windows startup registry.
"""
import json
import math
import os
import sys
import winreg
from copy import deepcopy

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".audio_visualizer.json")
APP_NAME = "AudioVisualizer"

DEFAULTS = {
    "mode": "bars",           # "bars", "wave", "mirror", or "dot_matrix"
    "sensitivity": 1.0,       # 0.5, 1.0, 2.0
    "enabled": True,
    "bar_count": 64,
    "width_percent": 40,      # % of taskbar width (left side)
    "visualizer_height": 40,  # visualizer height in pixels
    "visualizer_monitor": 0,  # monitor index for multi-monitor setups
    "taskbar_auto_hide_behavior": "follow",  # "follow", "hide", "always"
    "width_mode": "auto",    # "auto" (empty space), "percentage", "fixed"
    "alignment_hint": "left",  # "left", "center"
    "auto_hide": True,
    "auto_hide_timeout": 5.0, # seconds
    "glow": True,
    "beat_flash": True,      # legacy key: controls beat pulse background
    "theme": "album_art",     # color theme
    "startup": False,
    "auto_update_check": True,
    "update_check_interval_hours": 24,
    "last_update_check_ts": 0.0,
    "update_remind_after_hours": 24,
    "update_defer_until_ts": 0.0,
    "update_skip_version": "",
    "dynamic_quality": True,
    "gradient_mode": "off",  # "off", "two_color", "three_color"
    "mirror_center_mode": False,
    "mirror_center_gap": 2,
    "low_end_boost": 1.35,
    "peak_hold_decay": 0.045,
    "peak_caps_enabled": True,
    "mode_params": {},
}

# UI controls config for media overlay
DEFAULTS.setdefault("media_controls", {
    "use_widgets": True,          # Use real QToolButton widgets instead of painted hit-rects
    "position": "right",        # 'left' | 'center' | 'right'
    "size": 36,                   # button diameter in pixels
    "style": "glass",           # 'glass'|'flat'|'outline'
    "use_paint_fallback": False,  # keep painted controls as fallback
    "padding": 8,                 # padding from overlay edges
    "spacing": 6,                 # spacing between buttons
})

AUDIO_CONFIG_KEYS = frozenset({
    "bar_count",
    "fft_size",
    "freq_min",
    "freq_max",
    "use_microphone",
    "isolate_bass",
    "window_function",
})


def audio_config_changed(previous: dict, current: dict) -> bool:
    """Return whether capture must restart for a configuration update."""
    return any(
        previous.get(key) != current.get(key)
        for key in AUDIO_CONFIG_KEYS
    )


def _number(value, default, minimum, maximum, converter):
    try:
        value = converter(value)
        if not math.isfinite(value):
            raise ValueError
        return max(minimum, min(maximum, value))
    except (TypeError, ValueError, OverflowError):
        return default


def _boolean(value, default):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return default


def normalize_config(cfg: dict) -> dict:
    """Clamp persisted values before they reach Qt or the audio thread."""
    normalized = dict(cfg)
    if normalized.get("mode") not in {"bars", "wave", "mirror", "dot_matrix"}:
        normalized["mode"] = "bars"
    normalized["bar_count"] = int(_number(normalized.get("bar_count"), 64, 8, 128, int))
    normalized["width_percent"] = int(_number(normalized.get("width_percent"), 40, 10, 100, int))
    normalized["sensitivity"] = _number(normalized.get("sensitivity"), 1.0, 0.1, 5.0, float)
    normalized["auto_hide_timeout"] = _number(
        normalized.get("auto_hide_timeout"), 5.0, 1.0, 60.0, float
    )
    normalized["low_end_boost"] = _number(
        normalized.get("low_end_boost"), 1.35, 0.8, 2.0, float
    )
    normalized["peak_hold_decay"] = _number(
        normalized.get("peak_hold_decay"), 0.045, 0.01, 0.1, float
    )

    for key, default in (
        ("enabled", True),
        ("auto_hide", True),
        ("glow", True),
        ("beat_flash", True),
        ("peak_caps_enabled", True),
        ("dynamic_quality", True),
        ("auto_update_check", True),
        ("use_microphone", False),
        ("isolate_bass", False),
    ):
        normalized[key] = _boolean(normalized.get(key), default)

    fft_size = normalized.get("fft_size", 2048)
    try:
        fft_size = int(fft_size)
    except (TypeError, ValueError):
        fft_size = 2048
    normalized["fft_size"] = fft_size if fft_size in {2048, 4096, 8192} else 2048

    normalized["freq_min"] = int(_number(normalized.get("freq_min"), 40, 20, 200, int))
    normalized["freq_max"] = int(_number(normalized.get("freq_max"), 16000, 4000, 20000, int))
    if normalized["freq_max"] <= normalized["freq_min"]:
        normalized["freq_min"] = 40
        normalized["freq_max"] = 16000

    media_controls = normalized.get("media_controls")
    if not isinstance(media_controls, dict):
        media_controls = deepcopy(DEFAULTS["media_controls"])
    else:
        media_controls = dict(DEFAULTS["media_controls"]) | media_controls
    media_controls["use_widgets"] = _boolean(media_controls.get("use_widgets"), True)
    media_controls["use_paint_fallback"] = _boolean(
        media_controls.get("use_paint_fallback"), False
    )
    media_controls["size"] = int(_number(media_controls.get("size"), 36, 22, 64, int))
    normalized["media_controls"] = media_controls
    return normalized


def load_config() -> dict:
    # Deep-copy nested defaults so callers cannot mutate shared application state.
    cfg = deepcopy(DEFAULTS)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                saved = json.load(f)
            cfg.update(saved)
        except Exception:
            pass

    # Migrate legacy settings to current schema.
    cfg.pop("visual_preset", None)
    if cfg.get("mode") == "oscilloscope":
        cfg["mode"] = "wave"
    elif cfg.get("mode") == "mirror_tunnel":
        cfg["mode"] = "mirror"

    cfg = normalize_config(cfg)

    # Keep persisted config in sync with actual registry startup state.
    cfg["startup"] = is_startup_enabled()
    return cfg


def save_config(cfg: dict):
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"[Config] Failed to save: {e}")


def set_startup(enable: bool):
    """Add or remove from HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run."""
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        if enable:
            if getattr(sys, "frozen", False):
                command = f'"{sys.executable}"'
            else:
                exe = sys.executable
                script = os.path.abspath(os.path.join(os.path.dirname(__file__), "main.py"))
                command = f'"{exe}" "{script}"'
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, command)
            print("[Config] Added to Windows startup")
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
                print("[Config] Removed from Windows startup")
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception as e:
        print(f"[Config] Startup registry error: {e}")


def is_startup_enabled() -> bool:
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return True
    except (FileNotFoundError, OSError):
        return False

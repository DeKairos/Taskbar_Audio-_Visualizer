"""
config_manager.py — Persists settings to JSON, manages Windows startup registry.
"""
import json
import os
import sys
import winreg

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".audio_visualizer.json")
APP_NAME = "AudioVisualizer"

DEFAULTS = {
    "mode": "bars",           # "bars", "wave", "mirror", or "dot_matrix"
    "sensitivity": 1.0,       # 0.5, 1.0, 2.0
    "enabled": True,
    "bar_count": 64,
    "width_percent": 40,      # % of taskbar width (left side)
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


def load_config() -> dict:
    cfg = dict(DEFAULTS)
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

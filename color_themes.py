"""
color_themes.py — Preset colour palettes for the audio visualizer.

Each theme is a dict with:
    base  : (R, G, B)  — low-energy colour
    peak  : (R, G, B)  — high-energy colour
    glow  : (R, G, B)  — glow halo colour
    bg    : (R, G, B)  — subtle fill / beat-flash tint
    rainbow: bool       — if True, hue rotates per-bar (ignores base/peak)
"""


import colorsys
from collections import Counter
import io


def artwork_accent(image_bytes):
    """Choose a substantial colorful region, avoiding white borders and tiny accents."""
    try:
        from PIL import Image
        with Image.open(io.BytesIO(image_bytes)) as source:
            source.thumbnail((64, 64))
            rgba = source.convert("RGBA")
            data = rgba.get_flattened_data() if hasattr(rgba, "get_flattened_data") else rgba.getdata()
            pixels = [rgb[:3] for rgb in data if rgb[3] >= 128]
        if not pixels:
            return None
        buckets = Counter(tuple(channel // 32 for channel in rgb) for rgb in pixels)
        candidates = []
        for bucket, count in buckets.items():
            rgb = tuple(min(255, value * 32 + 16) for value in bucket)
            hue, saturation, value = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
            if count >= max(2, len(pixels) * 0.02) and saturation >= 0.2 and value >= 0.12:
                candidates.append((count * saturation * value ** 0.5, hue, saturation, value))
        if candidates:
            _, hue, saturation, value = max(candidates)
            return tuple(round(c * 255) for c in colorsys.hsv_to_rgb(hue, saturation, max(0.55, value)))
        # Monochrome artwork remains neutral instead of inventing a hue.
        rgb = tuple(sum(pixel[i] for pixel in pixels) / len(pixels) for i in range(3))
        brightness = max(rgb)
        scale = max(1.0, 140 / max(brightness, 1))
        return tuple(min(255, round(c * scale)) for c in rgb) if brightness else (140, 140, 140)
    except (OSError, ValueError, TypeError, ImportError):
        return None


def artwork_theme(accent):
    """Derive a coherent palette without clipping each channel toward white."""
    hue, saturation, value = colorsys.rgb_to_hsv(*(c / 255 for c in accent))
    def rgb(s, v):
        return tuple(round(c * 255) for c in colorsys.hsv_to_rgb(hue, s, v))
    return {
        "base": rgb(saturation, max(0.55, min(value, 0.9))),
        "peak": rgb(saturation * 0.45, 1.0),
        "glow": rgb(saturation * 0.8, max(0.8, value)),
        "bg": rgb(saturation * 0.65, max(0.7, value)),
        "rainbow": False,
    }


class ThemeTransition:
    """Retarget a short crossfade from the palette currently being displayed."""
    def __init__(self, duration=0.45):
        self.duration = duration
        self._target = None
        self._start = None
        self._started_at = 0.0

    def sample(self, now):
        if self._target is None:
            return None
        progress = min(1.0, max(0.0, (now - self._started_at) / self.duration)) if self.duration > 0 else 1.0
        progress = progress * progress * (3 - 2 * progress)
        result = dict(self._target)
        for key in ("base", "peak", "glow", "bg"):
            result[key] = tuple(round(a + (b - a) * progress)
                                for a, b in zip(self._start[key], self._target[key]))
        return result

    def resolve(self, target, now):
        if target != self._target:
            self._start = self.sample(now) if self._target is not None else dict(target)
            self._target = dict(target)
            self._started_at = now
        return self.sample(now)


THEMES = {
    "album_art": {
        # Placeholder colors used until media art is available.
        "base": (20, 180, 230),
        "peak": (150, 250, 255),
        "glow": (80, 200, 240),
        "bg":   (180, 220, 255),
        "rainbow": False,
    },
    "cyan": {
        "base": (20, 180, 230),
        "peak": (150, 250, 255),
        "glow": (80, 200, 240),
        "bg":   (180, 220, 255),
        "rainbow": False,
    },
    "neon_purple": {
        "base": (120, 20, 230),
        "peak": (220, 140, 255),
        "glow": (160, 80, 255),
        "bg":   (200, 160, 255),
        "rainbow": False,
    },
    "sunset": {
        "base": (230, 80, 20),
        "peak": (255, 220, 80),
        "glow": (255, 140, 40),
        "bg":   (255, 180, 100),
        "rainbow": False,
    },
    "matrix": {
        "base": (20, 200, 50),
        "peak": (120, 255, 140),
        "glow": (60, 230, 80),
        "bg":   (100, 255, 120),
        "rainbow": False,
    },
    "aurora": {
        "base": (45, 170, 140),
        "peak": (150, 250, 210),
        "glow": (90, 225, 185),
        "bg":   (120, 230, 205),
        "rainbow": False,
    },
    "retro_vu": {
        "base": (210, 150, 40),
        "peak": (255, 220, 110),
        "glow": (235, 175, 60),
        "bg":   (255, 210, 120),
        "rainbow": False,
    },
    "minimal_studio": {
        "base": (85, 180, 205),
        "peak": (205, 240, 250),
        "glow": (130, 210, 230),
        "bg":   (160, 225, 240),
        "rainbow": False,
    },
    "neon_grid": {
        "base": (45, 210, 250),
        "peak": (190, 245, 255),
        "glow": (90, 225, 255),
        "bg":   (140, 230, 255),
        "rainbow": False,
    },
    "rainbow": {
        "base": (255, 0, 0),     # unused — per-bar hue
        "peak": (255, 255, 255),
        "glow": (255, 255, 255),
        "bg":   (180, 220, 255),
        "rainbow": True,
    },
}

THEME_NAMES = list(THEMES.keys())          # ordered list
THEME_DISPLAY = {                           # tray menu labels
    "album_art":   "Album Art (Dynamic)",
    "cyan":        "Cyan",
    "neon_purple": "Neon Purple",
    "sunset":      "Sunset",
    "matrix":      "Matrix Green",
    "aurora":      "Aurora",
    "retro_vu":    "Retro VU",
    "minimal_studio": "Minimal Studio",
    "neon_grid":   "Neon Grid",
    "rainbow":     "Rainbow",
}


def get_theme(name: str) -> dict:
    return THEMES.get(name, THEMES["cyan"])


def bar_color(theme: dict, norm: float, index: int, total: int):
    """Return (R, G, B) for a single bar given its normalised amplitude.

    For rainbow mode *index*/*total* drives the hue.
    Otherwise the colour is linearly interpolated base→peak.
    """
    if theme["rainbow"]:
        import colorsys
        hue = index / max(total, 1)
        r, g, b = colorsys.hsv_to_rgb(hue, 0.85, 0.7 + 0.3 * norm)
        return int(r * 255), int(g * 255), int(b * 255)

    br, bg, bb = theme["base"]
    pr, pg, pb = theme["peak"]
    r = int(br + norm * (pr - br))
    g = int(bg + norm * (pg - bg))
    b = int(bb + norm * (pb - bb))
    return r, g, b

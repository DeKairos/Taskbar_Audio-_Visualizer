"""
color_themes.py — Preset colour palettes for the audio visualizer.

Each theme is a dict with:
    base  : (R, G, B)  — low-energy colour
    peak  : (R, G, B)  — high-energy colour
    glow  : (R, G, B)  — glow halo colour
    bg    : (R, G, B)  — subtle fill / beat-flash tint
    rainbow: bool       — if True, hue rotates per-bar (ignores base/peak)
"""


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

"""
ui/fluent_theme.py — Fluent 2 Design System tokens and helpers.

Provides centralized design constants used by all UI surfaces:
settings window, flyouts, overlays, and visualizer modes.
"""
from PyQt6.QtGui import QColor
from PyQt6.QtCore import Qt


# ── Corner Radii ───────────────────────────────────────────────────
RADIUS_SMALL = 4
RADIUS_MEDIUM = 8
RADIUS_LARGE = 12
RADIUS_CARD = 16
RADIUS_CIRCLE = 9999  # pill / circle

# ── Spacing Scale ──────────────────────────────────────────────────
SPACE_2XS = 2
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16
SPACE_XL = 24
SPACE_2XL = 32

# ── Typography (Segoe UI Variable family) ──────────────────────────
FONT_FAMILY = "Segoe UI Variable"
FONT_FAMILY_FALLBACK = "Segoe UI"

FONT_SIZES = {
    "caption": 12,
    "body": 14,
    "body_strong": 14,
    "subtitle": 18,
    "title": 20,
    "title_large": 28,
    "display": 34,
}

FONT_WEIGHTS = {
    "regular": 400,
    "medium": 500,
    "semibold": 600,
    "bold": 700,
}

# ── Opacity Layers (Fluent 2 token values) ─────────────────────────
OPACITY_DISABLED = 0.36
OPACITY_SECONDARY_TEXT = 0.70
OPACITY_TERTIARY_TEXT = 0.50
OPACITY_HOVER = 0.06
OPACITY_PRESSED = 0.12
OPACITY_SELECTED = 0.08

# ── Elevation Shadows ─────────────────────────────────────────────
ELEVATION_4 = {"blur": 4, "offset_y": 1, "alpha": 20}
ELEVATION_8 = {"blur": 8, "offset_y": 2, "alpha": 28}
ELEVATION_16 = {"blur": 16, "offset_y": 4, "alpha": 32}
ELEVATION_64 = {"blur": 64, "offset_y": 16, "alpha": 40}


# ── Color Helpers ──────────────────────────────────────────────────

def qcolor_with_alpha(c: QColor, alpha: int) -> QColor:
    """Return a copy of the color with the given alpha (0-255)."""
    return QColor(c.red(), c.green(), c.blue(), alpha)


def qcolor_with_alpha_f(c: QColor, alpha: float) -> QColor:
    """Return a copy with alpha from float (0.0-1.0)."""
    return QColor(c.red(), c.green(), c.blue(), int(alpha * 255))


def lerp_color(c1: tuple, c2: tuple, t: float) -> tuple:
    """Linearly interpolate between two RGB tuples."""
    t = max(0.0, min(1.0, t))
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def hex_to_rgb(hex_str: str) -> tuple:
    """Convert hex color string '#RRGGBB' to (R, G, B) tuple."""
    h = hex_str.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb: tuple) -> str:
    """Convert (R, G, B) tuple to '#RRGGBB' string."""
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


# ── Fluent 2 Acrylic/Mica Simulation ──────────────────────────────

def acrylic_bg_color(base_color: tuple, tint_alpha: int = 40) -> QColor:
    """Simulate an acrylic surface: darkened base with tint overlay."""
    r, g, b = base_color
    return QColor(
        max(0, r - 30),
        max(0, g - 30),
        max(0, b - 30),
        tint_alpha,
    )


def card_bg(dark_mode: bool = True) -> QColor:
    """Return a card background color matching Fluent 2 surface tokens."""
    if dark_mode:
        return QColor(32, 32, 32, 220)
    return QColor(252, 252, 252, 240)


def card_border(dark_mode: bool = True) -> QColor:
    """Card border color matching Fluent 2 stroke tokens."""
    if dark_mode:
        return QColor(255, 255, 255, 14)
    return QColor(0, 0, 0, 8)


def text_primary(dark_mode: bool = True) -> QColor:
    """Primary text color."""
    if dark_mode:
        return QColor(255, 255, 255, 240)
    return QColor(0, 0, 0, 230)


def text_secondary(dark_mode: bool = True) -> QColor:
    """Secondary text color."""
    if dark_mode:
        return QColor(255, 255, 255, 160)
    return QColor(0, 0, 0, 150)


def accent_color() -> QColor:
    """Try to get the Windows system accent color. Falls back to cyan."""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\DWM"
        )
        value, _ = winreg.QueryValueEx(key, "AccentColor")
        winreg.CloseKey(key)
        # Windows stores as AABBGGRR
        r = value & 0xFF
        g = (value >> 8) & 0xFF
        b = (value >> 16) & 0xFF
        return QColor(r, g, b)
    except Exception:
        return QColor(0, 120, 215)  # Windows default blue


# ── Flyout Card Painter ────────────────────────────────────────────

def paint_flyout_card(painter, x: int, y: int, w: int, h: int,
                      dark_mode: bool = True, radius: int = RADIUS_CARD):
    """Paint a Fluent 2 style card: filled rect + border + subtle shadow."""
    from PyQt6.QtGui import QPainterPath, QBrush, QPen, QColor
    from PyQt6.QtCore import QRectF

    path = QPainterPath()
    path.addRoundedRect(QRectF(x, y, w, h), radius, radius)

    # Fill
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(card_bg(dark_mode)))
    painter.drawPath(path)

    # Border
    painter.setPen(QPen(card_border(dark_mode), 1))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(path)

"""Particle system mode — particles emitted from bar peaks with gravity and theme colors."""
import math
import time
import random
import numpy as np
from PyQt6.QtGui import QColor, QPainter
from .registry import register_mode

# Module-level particle state (persists across frames)
_particles = []


class _Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "size", "r", "g", "b")

    def __init__(self, x, y, vx, vy, life, size, r, g, b):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.life = life
        self.max_life = life
        self.size = size
        self.r = r
        self.g = g
        self.b = b


def _painter(vis, qp, w, h, params=None):
    global _particles
    params = params or {}
    gravity = float(params.get("gravity", 80.0))
    emit_rate = int(params.get("emit_rate", 3))
    max_particles = int(params.get("max_particles", 600))
    wind = float(params.get("wind", 0.0))

    bins, _caps = vis._sampled_bins()
    total = max(1, len(bins))
    max_v = vis._display_max_value(bins)

    theme = vis._resolve_theme() if hasattr(vis, "_resolve_theme") else None
    if not theme:
        return

    br, bg, bb = theme.get("base", (20, 180, 230))
    pr, pg, pb = theme.get("peak", (150, 250, 255))
    glow_r, glow_g, glow_b = theme.get("glow", (80, 200, 240))

    now = time.time()

    # Emit new particles from bar peaks
    for i, v in enumerate(bins):
        norm = vis._energy_norm(v, max_v)
        if norm < 0.15:
            continue
        bar_x = (i + 0.5) / total * w
        bar_y = h - norm * (h - 8) - 4
        for _ in range(emit_rate):
            if len(_particles) >= max_particles:
                break
            angle = random.uniform(-math.pi, 0)
            speed = random.uniform(10, 40) * norm
            vx = math.cos(angle) * speed + wind
            vy = math.sin(angle) * speed
            life = random.uniform(0.6, 1.8)
            size = random.uniform(1.0, 3.0) * (0.5 + norm * 0.5)
            # Color from theme gradient
            t = random.random()
            r = int(br + t * (pr - br))
            g = int(bg + t * (pg - bg))
            b = int(bb + t * (pb - bb))
            _particles.append(_Particle(
                bar_x, bar_y, vx, vy, life, size, r, g, b
            ))

    # Update and draw particles
    qp.save()
    qp.setPen(QColor(0, 0, 0, 0))

    alive = []
    for p in _particles:
        p.life -= 0.016
        if p.life <= 0:
            continue
        p.x += p.vx * 0.016
        p.y += p.vy * 0.016
        p.vy += gravity * 0.016
        p.vx += wind * 0.016
        alive.append(p)

        life_ratio = p.life / p.max_life
        alpha = int(255 * life_ratio * life_ratio)
        sz = p.size * (0.5 + 0.5 * life_ratio)

        # Glow effect
        if sz > 1.5:
            glow_sz = sz * 3
            glow_alpha = int(alpha * 0.3)
            qp.setBrush(QColor(glow_r, glow_g, glow_b, glow_alpha))
            qp.drawEllipse(
                int(p.x - glow_sz / 2), int(p.y - glow_sz / 2),
                int(glow_sz), int(glow_sz)
            )

        # Core dot
        qp.setBrush(QColor(p.r, p.g, p.b, alpha))
        qp.drawEllipse(
            int(p.x - sz / 2), int(p.y - sz / 2),
            int(max(1, sz)), int(max(1, sz))
        )

    _particles = alive[-max_particles:]
    qp.restore()


register_mode(
    "particles", "Particles", _painter,
    default_params={"gravity": 80.0, "emit_rate": 3, "max_particles": 600, "wind": 0.0},
    tooltip="Particles emitted from bar peaks with gravity and glow."
)

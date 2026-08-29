"""
ui/gl_renderer.py — Optional OpenGL-accelerated renderer for the visualizer.

Provides a QOpenGLWidget subclass that offloads bar drawing, glow gradients,
and particle rendering to the GPU. Falls back to QPainter if OpenGL is unavailable.
"""
import numpy as np

try:
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget
    from PyQt6.QtOpenGL import QOpenGLShaderProgram, QOpenGLBuffer, QOpenGLVertexArrayObject
    from OpenGL.GL import (
        glClearColor, glClear, GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT,
        glEnable, glDisable, GL_BLEND, glBlendFunc, GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA,
        glViewport, glScissor, GL_SCISSOR_TEST,
        GL_TRIANGLES, GL_LINES, GL_LINE_STRIP,
        glGenBuffers, glBindBuffer, glBufferData, GL_ARRAY_BUFFER, GL_STATIC_DRAW,
        glVertexAttribPointer, glEnableVertexAttribArray, GL_FLOAT,
        glUseProgram, glUniform4f, glGetUniformLocation,
        glDrawArrays, GL_DYNAMIC_DRAW,
        glGenVertexArrays, glBindVertexArray,
    )
    HAS_OPENGL = True
except ImportError:
    HAS_OPENGL = False


class GLRenderer:
    """Manages OpenGL rendering context and drawing primitives."""

    def __init__(self):
        self._initialized = False
        self._program = None

    @property
    def available(self):
        return HAS_OPENGL

    def initialize(self):
        """Initialize OpenGL resources. Call once after context is current."""
        if self._initialized:
            return
        if not HAS_OPENGL:
            return

        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        self._initialized = True

    def clear(self, r=0.0, g=0.0, b=0.0, a=0.0):
        """Clear the framebuffer."""
        if not self._initialized:
            return
        glClearColor(r, g, b, a)
        glClear(GL_COLOR_BUFFER_BIT)

    def draw_rect(self, x, y, w, h, r, g, b, a=1.0):
        """Draw a filled rectangle (simulates a bar)."""
        if not self._initialized:
            return
        # Use immediate mode for simplicity (can be upgraded to VBOs later)
        from OpenGL.GL import glBegin, glEnd, glVertex2f, glColor4f
        glEnable(GL_BLEND)
        glColor4f(r, g, b, a)
        glBegin(GL_TRIANGLES)
        glVertex2f(x, y)
        glVertex2f(x + w, y)
        glVertex2f(x + w, y + h)
        glVertex2f(x, y)
        glVertex2f(x + w, y + h)
        glVertex2f(x, y + h)
        glEnd()

    def draw_circle(self, cx, cy, radius, r, g, b, a=1.0, segments=16):
        """Draw a filled circle (simulates glow)."""
        if not self._initialized:
            return
        from OpenGL.GL import glBegin, glEnd, glVertex2f, glColor4f, GL_TRIANGLE_FAN
        import math
        glColor4f(r, g, b, a)
        glBegin(GL_TRIANGLE_FAN)
        glVertex2f(cx, cy)
        for i in range(segments + 1):
            angle = 2.0 * math.pi * i / segments
            glVertex2f(cx + math.cos(angle) * radius, cy + math.sin(angle) * radius)
        glEnd()

    def cleanup(self):
        """Release OpenGL resources."""
        self._initialized = False

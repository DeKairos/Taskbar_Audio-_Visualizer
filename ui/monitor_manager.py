"""
ui/monitor_manager.py — Multi-monitor support for the Audio Visualizer.

Detects all available monitors and provides positioning helpers.
Allows the visualizer to be placed on any monitor.
Uses Win32 APPBARDATA for accurate taskbar geometry and edge detection.
"""
import ctypes
import ctypes.wintypes
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QRect, QPoint


ABM_GETSTATE = 0x00000004
ABM_GETTASKBARPOS = 0x00000005
ABE_LEFT = 0
ABE_TOP = 1
ABE_RIGHT = 2
ABE_BOTTOM = 3
ABE_AUTOHIDE = 0x00000001


class APPBARDATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.wintypes.DWORD),
        ("hWnd", ctypes.wintypes.HWND),
        ("uCallbackMessage", ctypes.wintypes.UINT),
        ("uEdge", ctypes.wintypes.UINT),
        ("rc", ctypes.wintypes.RECT),
        ("lParam", ctypes.wintypes.LPARAM),
    ]


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.wintypes.DWORD),
        ("rcMonitor", ctypes.wintypes.RECT),
        ("rcWork", ctypes.wintypes.RECT),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("szDevice", ctypes.wintypes.WCHAR * 32),
    ]


class MonitorManager:
    """Manages monitor detection and positioning."""

    def __init__(self):
        self._cached_screens = []
        self._refresh()
        self._shell32 = ctypes.windll.shell32
        self._user32 = ctypes.windll.user32
        # Explicit pointer-sized signatures avoid truncating handles on 64-bit Windows.
        for name in ("FindWindowW", "FindWindowExW"):
            getattr(self._user32, name).restype = ctypes.wintypes.HWND
        self._user32.FindWindowW.argtypes = [ctypes.wintypes.LPCWSTR, ctypes.wintypes.LPCWSTR]
        self._user32.FindWindowExW.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.HWND,
                                             ctypes.wintypes.LPCWSTR, ctypes.wintypes.LPCWSTR]
        self._user32.MonitorFromWindow.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.DWORD]
        self._user32.MonitorFromWindow.restype = ctypes.wintypes.HANDLE
        self._user32.GetMonitorInfoW.argtypes = [ctypes.wintypes.HANDLE, ctypes.POINTER(MONITORINFOEXW)]
        self._user32.GetWindowRect.argtypes = [ctypes.wintypes.HWND, ctypes.POINTER(ctypes.wintypes.RECT)]
        self._shell32.SHAppBarMessage.argtypes = [ctypes.wintypes.DWORD, ctypes.POINTER(APPBARDATA)]
        self._shell32.SHAppBarMessage.restype = ctypes.c_size_t

    def _refresh(self):
        """Refresh the list of available screens."""
        app = QApplication.instance()
        if app:
            self._cached_screens = app.screens()
        else:
            self._cached_screens = []

    def get_monitors(self):
        """Return list of monitor info dicts."""
        self._refresh()
        monitors = []
        for i, screen in enumerate(self._cached_screens):
            geo = screen.geometry()
            avail = screen.availableGeometry()
            monitors.append({
                "index": i,
                "name": screen.name(),
                "geometry": geo,
                "available_geometry": avail,
                "width": geo.width(),
                "height": geo.height(),
                "dpi": screen.logicalDotsPerInch(),
                "primary": screen == QApplication.instance().primaryScreen(),
                "ratio": screen.devicePixelRatio(),
            })
        return monitors

    def get_monitor(self, index: int):
        """Get a specific monitor by index."""
        monitors = self.get_monitors()
        if 0 <= index < len(monitors):
            return monitors[index]
        return monitors[0] if monitors else None

    def get_primary_monitor(self):
        """Get the primary monitor."""
        return next((mon for mon in self.get_monitors() if mon["primary"]), None)

    def get_taskbar_info(self, monitor_index: int = 0) -> dict:
        """
        Get accurate taskbar info using Win32 APPBARDATA.
        Returns dict with: rect (QRect), edge (int), autohide (bool),
        monitor_index (int), screen_geometry (QRect)
        """
        mon = self.get_monitor(monitor_index)
        if not mon:
            print("[MonitorManager] No monitor found, using fallback")
            return self._fallback_taskbar_info(monitor_index)

        screen_geo = mon["geometry"]
        screen_avail = mon["available_geometry"]
        hwnd = self._find_taskbar_hwnd(monitor_index)
        if not hwnd:
            return self._estimate_from_screen_geometry(screen_geo, screen_avail, monitor_index)
        physical = self._get_window_rect(hwnd)
        native = self._window_monitor(hwnd)
        if physical is None or native is None:
            return self._estimate_from_screen_geometry(screen_geo, screen_avail, monitor_index)
        rect = self._rect_to_logical(physical, mon["ratio"], mon, native.rcMonitor)
        vertical = rect.height() > rect.width()
        if vertical:
            edge = ABE_LEFT if abs(rect.left() - screen_geo.left()) < abs(rect.right() - screen_geo.right()) else ABE_RIGHT
        else:
            edge = ABE_TOP if abs(rect.top() - screen_geo.top()) < abs(rect.bottom() - screen_geo.bottom()) else ABE_BOTTOM
        abd = APPBARDATA()
        abd.cbSize = ctypes.sizeof(APPBARDATA)
        abd.hWnd = hwnd
        autohide = bool(self._shell32.SHAppBarMessage(ABM_GETSTATE, ctypes.byref(abd)) & ABE_AUTOHIDE)
        intersection = rect.intersected(screen_geo)
        hidden = autohide and (intersection.width() <= 2 if vertical else intersection.height() <= 2)
        # Auto-hidden bars slide outside the screen; keep overlay placement inside it.
        if hidden:
            if edge == ABE_BOTTOM:
                rect.moveBottom(screen_geo.bottom())
            elif edge == ABE_TOP:
                rect.moveTop(screen_geo.top())
            elif edge == ABE_LEFT:
                rect.moveLeft(screen_geo.left())
            else:
                rect.moveRight(screen_geo.right())
        return {
            "rect": rect, "edge": edge, "autohide": autohide, "hidden": hidden,
            "monitor_index": monitor_index, "screen_geometry": screen_geo,
            "screen_available_geometry": screen_avail,
        }

    def _window_monitor(self, hwnd):
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(info)
        handle = self._user32.MonitorFromWindow(hwnd, 2)
        return info if handle and self._user32.GetMonitorInfoW(handle, ctypes.byref(info)) else None

    def _find_taskbar_hwnd(self, monitor_index: int) -> int:
        """Match the taskbar's native display name to QScreen, not enumeration order."""
        mon = self.get_monitor(monitor_index)
        if not mon:
            return 0
        for window_class in ("Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
            hwnd = self._user32.FindWindowExW(0, 0, window_class, None)
            while hwnd:
                native = self._window_monitor(hwnd)
                if native and native.szDevice.casefold() == mon["name"].casefold():
                    return hwnd
                hwnd = self._user32.FindWindowExW(0, hwnd, window_class, None)
        return 0

    def _estimate_from_screen_geometry(self, screen_geo: QRect, screen_avail: QRect, monitor_index: int) -> dict:
        """Fallback: estimate taskbar from screen vs available geometry."""
        gaps = [
            (screen_avail.left() - screen_geo.left(), ABE_LEFT),
            (screen_avail.top() - screen_geo.top(), ABE_TOP),
            (screen_geo.right() - screen_avail.right(), ABE_RIGHT),
            (screen_geo.bottom() - screen_avail.bottom(), ABE_BOTTOM),
        ]
        thickness, edge = max(gaps)
        thickness = thickness if thickness > 0 else 40
        if edge == ABE_LEFT:
            rect = QRect(screen_geo.left(), screen_geo.top(), thickness, screen_geo.height())
        elif edge == ABE_TOP:
            rect = QRect(screen_geo.left(), screen_geo.top(), screen_geo.width(), thickness)
        elif edge == ABE_RIGHT:
            rect = QRect(screen_geo.right() - thickness + 1, screen_geo.top(), thickness, screen_geo.height())
        else:
            rect = QRect(screen_geo.left(), screen_geo.bottom() - thickness + 1, screen_geo.width(), thickness)

        return {
            "rect": rect,
            "edge": edge,
            "autohide": False,
            "monitor_index": monitor_index,
            "screen_geometry": screen_geo,
            "screen_available_geometry": screen_avail,
        }

    def _fallback_taskbar_info(self, monitor_index: int) -> dict:
        """Last resort fallback."""
        screen_geo = QRect(0, 0, 1920, 1080)
        screen_avail = QRect(0, 0, 1920, 1040)
        return self._estimate_from_screen_geometry(screen_geo, screen_avail, monitor_index)

    def get_taskbar_empty_space(self, monitor_index: int = 0, alignment_hint: str = "left") -> dict:
        """
        Detect empty space in taskbar (between Start button and icons).
        Uses alignment_hint to determine which space to use:
        - "left": use space BEFORE Start button (at taskbar left edge)
        - "center": use larger of space before Start or space after icons
        Returns dict with: width (int), x (int), edge (int), available (bool)
        """
        info = self.get_taskbar_info(monitor_index)
        if not info:
            print("[MonitorManager] No taskbar info for empty space detection")
            return {"width": 0, "x": 0, "edge": ABE_BOTTOM, "available": False}

        taskbar_rect = info["rect"]
        edge = info["edge"]

        if edge in (ABE_LEFT, ABE_RIGHT):
            return self._get_vertical_empty_space(taskbar_rect, edge, monitor_index)

        return self._get_horizontal_empty_space(taskbar_rect, alignment_hint, monitor_index, edge)

    def _logical_child_rect(self, parent, class_name, monitor_index):
        hwnd = self._user32.FindWindowExW(parent, 0, class_name, None)
        # Windows 10 nests the task list in a rebar/task-switcher container.
        if not hwnd and class_name == "MSTaskListWClass":
            rebar = self._user32.FindWindowExW(parent, 0, "ReBarWindow32", None)
            switcher = self._user32.FindWindowExW(rebar, 0, "MSTaskSwWClass", None) if rebar else 0
            hwnd = self._user32.FindWindowExW(switcher, 0, class_name, None) if switcher else 0
        rect = self._get_window_rect(hwnd)
        mon = self.get_monitor(monitor_index)
        native = self._window_monitor(parent)
        return self._rect_to_logical(rect, mon["ratio"], mon, native.rcMonitor) if rect and mon and native else None

    def _get_horizontal_empty_space(self, taskbar_rect, alignment_hint="left", monitor_index=0, edge=ABE_BOTTOM):
        hwnd = self._find_taskbar_hwnd(monitor_index)
        if not hwnd:
            return self._fallback_empty_space(taskbar_rect, edge)
        start = self._logical_child_rect(hwnd, "Start", monitor_index)
        tasklist = self._logical_child_rect(hwnd, "MSTaskListWClass", monitor_index)
        tray = self._logical_child_rect(hwnd, "TrayNotifyWnd", monitor_index)
        before_end = min(r.left() for r in (start, tasklist) if r is not None) if start or tasklist else taskbar_rect.left()
        before = max(0, before_end - taskbar_rect.left() - 8)
        # The after gap starts AFTER the task list, never inside its occupied area.
        after_start = max(r.right() + 1 for r in (start, tasklist) if r is not None) if start or tasklist else taskbar_rect.right() + 1
        after_end = tray.left() if tray else taskbar_rect.right() + 1
        after = max(0, after_end - after_start - 8) if tasklist else 0
        choices = [(before, taskbar_rect.left())]
        if alignment_hint == "center":
            choices.append((after, after_start + 4))
        width, x = max(choices)
        if width < 100:
            return self._fallback_empty_space(taskbar_rect, edge)
        return {"width": width, "x": x, "edge": edge, "available": True}

    @staticmethod
    def _rect_to_logical(rect, dpi_ratio, monitor=None, physical_monitor=None):
        """Scale offsets within a display; Qt keeps native desktop origins on Windows."""
        if rect is None:
            return None
        ratio = dpi_ratio or 1.0
        physical_x = physical_monitor.left if physical_monitor is not None else 0
        physical_y = physical_monitor.top if physical_monitor is not None else 0
        logical_x = monitor["geometry"].x() if monitor else 0
        logical_y = monitor["geometry"].y() if monitor else 0
        return QRect(
            logical_x + round((rect.left - physical_x) / ratio),
            logical_y + round((rect.top - physical_y) / ratio),
            round((rect.right - rect.left) / ratio),
            round((rect.bottom - rect.top) / ratio),
        )

    def _get_vertical_empty_space(self, taskbar_rect, edge, monitor_index=0):
        # Shell child rectangles don't reliably expose all vertical icons. Use the
        # existing fallback until a complete occupied-area measurement is available.
        return self._fallback_empty_space(taskbar_rect, edge)

    def _fallback_empty_space(self, taskbar_rect: QRect, edge: int) -> dict:
        """Fallback: use percentage of taskbar size."""
        if edge in (ABE_LEFT, ABE_RIGHT):
            return {"width": int(taskbar_rect.height() * 0.4), "x": taskbar_rect.top(), "edge": edge, "available": True}
        return {"width": int(taskbar_rect.width() * 0.4), "x": taskbar_rect.left(), "edge": edge, "available": True}

    def _get_window_rect(self, hwnd: int):
        """Get window rect in physical pixels."""
        if not hwnd:
            return None
        rc = ctypes.wintypes.RECT()
        if self._user32.GetWindowRect(hwnd, ctypes.byref(rc)):
            return rc
        return None

    def _get_dpi_ratio(self) -> float:
        """Get system DPI scaling ratio."""
        try:
            dpi = self._user32.GetDpiForSystem()
            return dpi / 96.0 if dpi else 1.0
        except Exception:
            return 1.0

    def taskbar_geometry(self, monitor_index: int = 0) -> QRect:
        """Get taskbar geometry (compatibility method)."""
        info = self.get_taskbar_info(monitor_index)
        return info["rect"] if info else QRect(0, 0, 800, 40)

    def visualizer_position(self, monitor_index: int = 0,
                            width_percent: int = 40,
                            vis_height: int = 40,
                            width_mode: str = "auto",
                            alignment_hint: str = "left") -> tuple:
        """
        Calculate visualizer position on the given monitor.
        Returns (x, y, width, height).

        width_mode:
            "auto" - use empty space detection (default)
            "percentage" - use width_percent of taskbar width
            "fixed" - use width_percent as fixed pixels

        alignment_hint:
            "left" - position at left edge of taskbar (default)
            "center" - position at center of taskbar
            "right" - position at right edge of taskbar
        """
        info = self.get_taskbar_info(monitor_index)
        if not info:
            print("[MonitorManager] No taskbar info, using safe default")
            return self._safe_position(0, 0, 800, vis_height, monitor_index)

        taskbar = info["rect"]
        edge = info["edge"]

        empty_space = self.get_taskbar_empty_space(monitor_index, alignment_hint)

        if edge == ABE_BOTTOM:
            if width_mode == "auto" and empty_space.get("available"):
                # Auto mode: use alignment to determine position, empty space for width
                vis_w = empty_space.get("width", int(taskbar.width() * width_percent / 100))
                vis_x, vis_y = empty_space["x"], taskbar.top()
            elif width_mode == "fixed":
                vis_w = width_percent
                vis_x, vis_y = self._get_position_for_alignment(taskbar, vis_w, vis_height, alignment_hint, edge)
            else:
                vis_w = int(taskbar.width() * width_percent / 100)
                vis_x, vis_y = self._get_position_for_alignment(taskbar, vis_w, vis_height, alignment_hint, edge)
            pos = (vis_x, vis_y, max(100, vis_w), vis_height)

        elif edge == ABE_TOP:
            if width_mode == "auto" and empty_space.get("available"):
                vis_w = empty_space.get("width", int(taskbar.width() * width_percent / 100))
                vis_x, vis_y = empty_space["x"], taskbar.top()
            elif width_mode == "fixed":
                vis_w = width_percent
                vis_x, vis_y = self._get_position_for_alignment(taskbar, vis_w, vis_height, alignment_hint, edge)
            else:
                vis_w = int(taskbar.width() * width_percent / 100)
                vis_x, vis_y = self._get_position_for_alignment(taskbar, vis_w, vis_height, alignment_hint, edge)
            pos = (vis_x, vis_y, max(100, vis_w), vis_height)

        elif edge == ABE_LEFT:
            if width_mode == "auto" and empty_space.get("available"):
                vis_h = empty_space.get("width", vis_height)
                vis_x, vis_y = taskbar.left(), empty_space["x"]
            elif width_mode == "fixed":
                vis_h = width_percent
                vis_x, vis_y = self._get_position_for_alignment_vertical(taskbar, vis_h, vis_height, alignment_hint, edge)
            else:
                vis_h = vis_height
                vis_x, vis_y = self._get_position_for_alignment_vertical(taskbar, vis_h, vis_height, alignment_hint, edge)
            pos = (vis_x, vis_y, vis_height, max(100, vis_h))

        elif edge == ABE_RIGHT:
            if width_mode == "auto" and empty_space.get("available"):
                vis_h = empty_space.get("width", vis_height)
                vis_x, vis_y = taskbar.left(), empty_space["x"]
            elif width_mode == "fixed":
                vis_h = width_percent
                vis_x, vis_y = self._get_position_for_alignment_vertical(taskbar, vis_h, vis_height, alignment_hint, edge)
            else:
                vis_h = vis_height
                vis_x, vis_y = self._get_position_for_alignment_vertical(taskbar, vis_h, vis_height, alignment_hint, edge)
            pos = (vis_x, vis_y, vis_height, max(100, vis_h))

        else:
            pos = (taskbar.x(), taskbar.y(), taskbar.width(), vis_height)

        # Verify bounds and clamp if needed
        if edge == ABE_BOTTOM or edge == ABE_TOP:
            pos = self._verify_bounds_horizontal(pos, taskbar, edge)
        else:
            pos = self._verify_bounds_vertical(pos, taskbar)

        print(f"[MonitorManager] Final position: {pos}")
        return pos

    def _get_position_for_alignment(self, taskbar: QRect, vis_w: int, vis_h: int, alignment: str, edge: int) -> tuple:
        """Get (x, y) position based on alignment for horizontal taskbar."""
        if edge == ABE_BOTTOM:
            if alignment == "left":
                x = taskbar.left()
            else:  # center
                x = taskbar.left() + (taskbar.width() - vis_w) // 2
            y = taskbar.top()
        else:  # ABE_TOP
            if alignment == "left":
                x = taskbar.left()
            else:  # center
                x = taskbar.left() + (taskbar.width() - vis_w) // 2
            y = taskbar.top() + taskbar.height() - vis_h
        return (x, y)

    def _get_position_for_alignment_vertical(self, taskbar: QRect, vis_h: int, vis_w: int, alignment: str, edge: int) -> tuple:
        """Get (x, y) position based on alignment for vertical taskbar."""
        if edge == ABE_LEFT:
            if alignment == "left":
                y = taskbar.top()
            else:  # center
                y = taskbar.top() + (taskbar.height() - vis_h) // 2
            x = taskbar.left() + (taskbar.width() - vis_w) // 2
        else:  # ABE_RIGHT
            if alignment == "left":
                y = taskbar.top()
            else:  # center
                y = taskbar.top() + (taskbar.height() - vis_h) // 2
            x = taskbar.left() + (taskbar.width() - vis_w) // 2
        return (x, y)

    @staticmethod
    def _clamp_to_taskbar(pos, taskbar):
        x, y, w, h = pos
        w = max(1, min(w, taskbar.width()))
        h = max(1, min(h, taskbar.height()))
        x = max(taskbar.left(), min(x, taskbar.right() + 1 - w))
        y = max(taskbar.top(), min(y, taskbar.bottom() + 1 - h))
        return x, y, w, h

    def _verify_bounds_horizontal(self, pos, taskbar, edge):
        return self._clamp_to_taskbar(pos, taskbar)

    def _verify_bounds_vertical(self, pos, taskbar):
        return self._clamp_to_taskbar(pos, taskbar)

    def _safe_position(self, x: int, y: int, w: int, h: int, monitor_index: int) -> tuple:
        """Return a safe fallback position."""
        mon = self.get_monitor(monitor_index)
        if mon:
            avail = mon["available_geometry"]
            return (avail.left(), avail.bottom() - h, min(w, avail.width() // 4), h)
        return (0, 0, 800, h)

    def _get_alignment_x(self, taskbar: QRect, vis_w: int, alignment: str) -> int:
        """Get x position based on alignment hint for horizontal taskbar."""
        if alignment == "left":
            return taskbar.x()
        else:  # center
            return taskbar.x() + (taskbar.width() - vis_w) // 2

    def _get_alignment_x_vertical(self, taskbar: QRect, vis_h: int, alignment: str) -> int:
        """Get y position based on alignment hint for vertical taskbar."""
        if alignment == "left":
            return taskbar.top()
        else:  # center
            return taskbar.top() + (taskbar.height() - vis_h) // 2
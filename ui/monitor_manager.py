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


class MonitorManager:
    """Manages monitor detection and positioning."""

    def __init__(self):
        self._cached_screens = []
        self._refresh()
        self._shell32 = ctypes.windll.shell32
        self._user32 = ctypes.windll.user32

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
                "primary": i == 0,
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
        return self.get_monitor(0)

    def get_taskbar_info(self, monitor_index: int = 0) -> dict:
        """
        Get accurate taskbar info using Win32 APPBARDATA.
        Returns dict with: rect (QRect), edge (int), autohide (bool),
        monitor_index (int), screen_geometry (QRect)
        """
        mon = self.get_monitor(monitor_index)
        if not mon:
            return self._fallback_taskbar_info(monitor_index)

        screen_geo = mon["geometry"]
        screen_avail = mon["available_geometry"]

        abd = APPBARDATA()
        abd.cbSize = ctypes.sizeof(APPBARDATA)
        abd.hWnd = self._find_taskbar_hwnd(monitor_index)

        if abd.hWnd == 0:
            return self._estimate_from_screen_geometry(screen_geo, screen_avail, monitor_index)

        result = self._shell32.SHAppBarMessage(ABM_GETTASKBARPOS, ctypes.byref(abd))
        if not result:
            return self._estimate_from_screen_geometry(screen_geo, screen_avail, monitor_index)

        taskbar_rect = QRect(
            abd.rc.left, abd.rc.top,
            abd.rc.right - abd.rc.left,
            abd.rc.bottom - abd.rc.top
        )

        edge = abd.uEdge
        autohide = bool(abd.lParam & ABE_AUTOHIDE)

        return {
            "rect": taskbar_rect,
            "edge": edge,
            "autohide": autohide,
            "monitor_index": monitor_index,
            "screen_geometry": screen_geo,
            "screen_available_geometry": screen_avail,
        }

    def _find_taskbar_hwnd(self, monitor_index: int) -> int:
        """Find the taskbar window handle for the given monitor."""
        taskbar_class = "Shell_TrayWnd"
        if monitor_index == 0:
            hwnd = self._user32.FindWindowW(taskbar_class, None)
            return hwnd if hwnd else 0

        hwnd = self._user32.FindWindowExW(0, 0, taskbar_class, None)
        for _ in range(monitor_index):
            if not hwnd:
                return 0
            hwnd = self._user32.FindWindowExW(0, hwnd, taskbar_class, None)
        return hwnd if hwnd else 0

    def _estimate_from_screen_geometry(self, screen_geo: QRect, screen_avail: QRect, monitor_index: int) -> dict:
        """Fallback: estimate taskbar from screen vs available geometry."""
        full_h = screen_geo.height()
        avail_h = screen_avail.height()
        taskbar_h = full_h - avail_h

        if taskbar_h > 0:
            edge = ABE_BOTTOM
            rect = QRect(screen_avail.x(), screen_avail.y() + avail_h, screen_avail.width(), taskbar_h)
        else:
            edge = ABE_BOTTOM
            rect = QRect(screen_avail.x(), screen_avail.y() + avail_h - 40, screen_avail.width(), 40)

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

    def get_taskbar_empty_space(self, monitor_index: int = 0) -> dict:
        """
        Detect empty space in taskbar (between Start button and icons).
        Returns dict with: width (int), x (int), edge (int), available (bool)
        """
        info = self.get_taskbar_info(monitor_index)
        if not info:
            return {"width": 0, "x": 0, "edge": ABE_BOTTOM, "available": False}

        taskbar_rect = info["rect"]
        edge = info["edge"]

        if edge in (ABE_LEFT, ABE_RIGHT):
            return self._get_vertical_empty_space(taskbar_rect, edge)

        return self._get_horizontal_empty_space(taskbar_rect)

    def _get_horizontal_empty_space(self, taskbar_rect: QRect) -> dict:
        """Find empty space on horizontal (bottom/top) taskbar."""
        try:
            taskbar_hwnd = self._user32.FindWindowW("Shell_TrayWnd", None)
            if not taskbar_hwnd:
                return self._fallback_empty_space(taskbar_rect, ABE_BOTTOM)

            start_hwnd = self._user32.FindWindowExW(taskbar_hwnd, 0, "Start", None)
            tray_hwnd = self._user32.FindWindowExW(taskbar_hwnd, 0, "TrayNotifyWnd", None)
            tasklist_hwnd = self._user32.FindWindowExW(taskbar_hwnd, 0, "MSTaskListWClass", None)

            start_rect = self._get_window_rect(start_hwnd)
            tray_rect = self._get_window_rect(tray_hwnd)
            tasklist_rect = self._get_window_rect(tasklist_hwnd)

            dpi_ratio = self._get_dpi_ratio()

            if start_rect and dpi_ratio:
                start_logical = QRect(
                    int(start_rect.left / dpi_ratio), int(start_rect.top / dpi_ratio),
                    int((start_rect.right - start_rect.left) / dpi_ratio),
                    int((start_rect.bottom - start_rect.top) / dpi_ratio)
                )
            else:
                start_logical = None

            first_icon_x = taskbar_rect.right()
            if tray_rect and dpi_ratio:
                first_icon_x = min(first_icon_x, int(tray_rect.left / dpi_ratio))
            if tasklist_rect and dpi_ratio:
                first_icon_x = min(first_icon_x, int(tasklist_rect.left / dpi_ratio))

            if start_logical:
                empty_width = max(0, first_icon_x - start_logical.right())
                return {
                    "width": empty_width,
                    "x": start_logical.right(),
                    "edge": ABE_BOTTOM,
                    "available": empty_width > 50
                }

            fallback_width = int(taskbar_rect.width() * 0.4)
            return {
                "width": fallback_width,
                "x": taskbar_rect.left(),
                "edge": ABE_BOTTOM,
                "available": True
            }
        except Exception:
            return self._fallback_empty_space(taskbar_rect, ABE_BOTTOM)

    def _get_vertical_empty_space(self, taskbar_rect: QRect, edge: int) -> dict:
        """Find empty space on vertical (left/right) taskbar - simplified."""
        try:
            taskbar_hwnd = self._user32.FindWindowW("Shell_TrayWnd", None)
            start_hwnd = self._user32.FindWindowExW(taskbar_hwnd, 0, "Start", None)
            start_rect = self._get_window_rect(start_hwnd)
            dpi_ratio = self._get_dpi_ratio()

            if start_rect and dpi_ratio:
                start_top = int(start_rect.top / dpi_ratio)
                start_bottom = int(start_rect.bottom / dpi_ratio)
                empty_height = start_top - taskbar_rect.top()
                if empty_height < 50:
                    empty_height = taskbar_rect.bottom() - start_bottom

                return {
                    "width": empty_height,
                    "x": start_top,
                    "edge": edge,
                    "available": empty_height > 50
                }
        except Exception:
            pass

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
            return (0, 0, 800, 40)

        taskbar = info["rect"]
        edge = info["edge"]

        empty_space = self.get_taskbar_empty_space(monitor_index)

        if edge == ABE_BOTTOM:
            if width_mode == "auto" and empty_space["available"]:
                vis_w = empty_space["width"]
                vis_x = empty_space["x"]
            elif width_mode == "fixed":
                vis_w = width_percent
                vis_x = self._get_alignment_x(taskbar, vis_w, alignment_hint)
            else:
                vis_w = int(taskbar.width() * width_percent / 100)
                vis_x = self._get_alignment_x(taskbar, vis_w, alignment_hint)
            vis_y = taskbar.y() + (taskbar.height() - vis_height) // 2
            return (vis_x, vis_y, max(100, vis_w), vis_height)

        elif edge == ABE_TOP:
            if width_mode == "auto" and empty_space["available"]:
                vis_w = empty_space["width"]
                vis_x = empty_space["x"]
            elif width_mode == "fixed":
                vis_w = width_percent
                vis_x = self._get_alignment_x(taskbar, vis_w, alignment_hint)
            else:
                vis_w = int(taskbar.width() * width_percent / 100)
                vis_x = self._get_alignment_x(taskbar, vis_w, alignment_hint)
            vis_y = taskbar.y() + (taskbar.height() - vis_height) // 2
            return (vis_x, vis_y, max(100, vis_w), vis_height)

        elif edge == ABE_LEFT:
            if width_mode == "auto" and empty_space["available"]:
                vis_h = empty_space["width"]
                vis_y = empty_space["x"]
            elif width_mode == "fixed":
                vis_h = width_percent
                vis_y = self._get_alignment_x_vertical(taskbar, vis_h, alignment_hint)
            else:
                vis_h = vis_height
                vis_y = self._get_alignment_x_vertical(taskbar, vis_h, alignment_hint)
            vis_x = taskbar.x() + (taskbar.width() - vis_height) // 2
            return (vis_x, vis_y, vis_height, max(100, vis_h))

        elif edge == ABE_RIGHT:
            if width_mode == "auto" and empty_space["available"]:
                vis_h = empty_space["width"]
                vis_y = empty_space["x"]
            elif width_mode == "fixed":
                vis_h = width_percent
                vis_y = self._get_alignment_x_vertical(taskbar, vis_h, alignment_hint)
            else:
                vis_h = vis_height
                vis_y = self._get_alignment_x_vertical(taskbar, vis_h, alignment_hint)
            vis_x = taskbar.x() + (taskbar.width() - vis_height) // 2
            return (vis_x, vis_y, vis_height, max(100, vis_h))

        return (taskbar.x(), taskbar.y(), taskbar.width(), vis_height)

    def _get_alignment_x(self, taskbar: QRect, vis_w: int, alignment: str) -> int:
        """Get x position based on alignment hint for horizontal taskbar."""
        if alignment == "left":
            return taskbar.x()
        elif alignment == "right":
            return taskbar.right() - vis_w
        else:  # center
            return taskbar.x() + (taskbar.width() - vis_w) // 2

    def _get_alignment_x_vertical(self, taskbar: QRect, vis_h: int, alignment: str) -> int:
        """Get y position based on alignment hint for vertical taskbar."""
        if alignment == "left":
            return taskbar.top()
        elif alignment == "right":
            return taskbar.bottom() - vis_h
        else:  # center
            return taskbar.top() + (taskbar.height() - vis_h) // 2
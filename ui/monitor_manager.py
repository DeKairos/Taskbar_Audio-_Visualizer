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
            print("[MonitorManager] No monitor found, using fallback")
            return self._fallback_taskbar_info(monitor_index)

        screen_geo = mon["geometry"]
        screen_avail = mon["available_geometry"]
        dpi_ratio = self._get_dpi_ratio()

        abd = APPBARDATA()
        abd.cbSize = ctypes.sizeof(APPBARDATA)
        abd.hWnd = self._find_taskbar_hwnd(monitor_index)

        if abd.hWnd == 0:
            print("[MonitorManager] Taskbar HWND not found, using screen geometry fallback")
            return self._estimate_from_screen_geometry(screen_geo, screen_avail, monitor_index)

        result = self._shell32.SHAppBarMessage(ABM_GETTASKBARPOS, ctypes.byref(abd))
        if not result:
            print("[MonitorManager] SHAppBarMessage failed, using screen geometry fallback")
            return self._estimate_from_screen_geometry(screen_geo, screen_avail, monitor_index)

        # APPBARDATA returns physical pixels - convert to logical pixels for Qt
        if dpi_ratio and dpi_ratio != 1.0:
            taskbar_rect = QRect(
                int(abd.rc.left / dpi_ratio),
                int(abd.rc.top / dpi_ratio),
                int((abd.rc.right - abd.rc.left) / dpi_ratio),
                int((abd.rc.bottom - abd.rc.top) / dpi_ratio)
            )
            print(f"[MonitorManager] DPI conversion: {dpi_ratio}x physical→logical for taskbar rect")
        else:
            taskbar_rect = QRect(
                abd.rc.left, abd.rc.top,
                abd.rc.right - abd.rc.left,
                abd.rc.bottom - abd.rc.top
            )

        edge = abd.uEdge
        autohide = bool(abd.lParam & ABE_AUTOHIDE)

        print(f"[MonitorManager] Taskbar: rect={taskbar_rect}, edge={edge}, autohide={autohide}, dpi_ratio={dpi_ratio}")

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
            return self._get_vertical_empty_space(taskbar_rect, edge)

        return self._get_horizontal_empty_space(taskbar_rect, alignment_hint)

    def _get_horizontal_empty_space(self, taskbar_rect: QRect, alignment_hint: str = "left") -> dict:
        """Find empty space on horizontal (bottom/top) taskbar.

        Uses alignment_hint to determine which space to use:
        - "left": space BEFORE Start button (at taskbar left edge)
        - "center": larger of space before Start or space after icons
        """
        dpi_ratio = self._get_dpi_ratio()
        print(f"[MonitorManager] Detecting horizontal empty space, DPI ratio: {dpi_ratio}")

        try:
            taskbar_hwnd = self._user32.FindWindowW("Shell_TrayWnd", None)
            if not taskbar_hwnd:
                print("[MonitorManager] Taskbar HWND not found")
                return self._fallback_empty_space(taskbar_rect, ABE_BOTTOM)

            # Get all relevant window rects
            start_rect = self._get_window_rect(self._user32.FindWindowExW(taskbar_hwnd, 0, "Start", None))
            tray_rect = self._get_window_rect(self._user32.FindWindowExW(taskbar_hwnd, 0, "TrayNotifyWnd", None))
            tasklist_rect = self._get_window_rect(self._user32.FindWindowExW(taskbar_hwnd, 0, "MSTaskListWClass", None))

            # Convert to logical pixels
            start_logical = self._rect_to_logical(start_rect, dpi_ratio) if start_rect else None
            tray_logical = self._rect_to_logical(tray_rect, dpi_ratio) if tray_rect else None
            tasklist_logical = self._rect_to_logical(tasklist_rect, dpi_ratio) if tasklist_rect else None

            print(f"[MonitorManager] Start: {start_logical}, Tray: {tray_logical}, TaskList: {tasklist_logical}")

            if not start_logical:
                print("[MonitorManager] Start button not found, using fallback")
                return self._fallback_empty_space(taskbar_rect, ABE_BOTTOM)

            # Find icon group boundaries
            icon_left = start_logical.right()  # Icons start after Start button
            icon_right = taskbar_rect.right()  # Default to taskbar edge

            if tray_logical:
                icon_right = min(icon_right, tray_logical.left())
            if tasklist_logical:
                # Tasklist might span the icon area - use its left as icon group start
                if tasklist_logical.left() > start_logical.right():
                    icon_left = tasklist_logical.left()
                # Find the rightmost icon by checking tasklist right edge
                if tasklist_logical.right() < icon_right:
                    icon_right = tasklist_logical.right()

            print(f"[MonitorManager] Icon group: left={icon_left}, right={icon_right}")

            # Calculate empty space based on alignment_hint (user's setting)
            # Space BEFORE icon group (left side of Start button)
            space_before_icons = max(0, start_logical.left() - taskbar_rect.left())
            # Space AFTER icon group (right side, before system tray)
            space_after_icons = max(0, icon_right - icon_left)

            print(f"[MonitorManager] Space before icons: {space_before_icons}, after icons: {space_after_icons}")

            if alignment_hint == "left":
                # Use space BEFORE Start button (at taskbar left edge)
                if space_before_icons > 100:
                    return {
                        "width": space_before_icons,
                        "x": taskbar_rect.left(),
                        "edge": ABE_BOTTOM,
                        "available": True
                    }
            else:  # "center"
                # Use larger of space before Start or space after icons
                space_to_use = max(space_before_icons, space_after_icons)
                if space_to_use > 100:
                    if space_before_icons >= space_after_icons:
                        return {
                            "width": space_before_icons,
                            "x": taskbar_rect.left(),
                            "edge": ABE_BOTTOM,
                            "available": True
                        }
                    else:
                        return {
                            "width": space_after_icons,
                            "x": icon_left,
                            "edge": ABE_BOTTOM,
                            "available": True
                        }

            # Fallback: not enough space detected
            print("[MonitorManager] Not enough empty space detected, using fallback")
            return self._fallback_empty_space(taskbar_rect, ABE_BOTTOM)

        except Exception as e:
            print(f"[MonitorManager] Empty space detection failed: {e}")
            return self._fallback_empty_space(taskbar_rect, ABE_BOTTOM)

    def _rect_to_logical(self, rect, dpi_ratio):
        """Convert physical pixel rect to logical pixels."""
        if not rect or dpi_ratio == 1.0:
            return rect
        return QRect(
            int(rect.left / dpi_ratio),
            int(rect.top / dpi_ratio),
            int((rect.right - rect.left) / dpi_ratio),
            int((rect.bottom - rect.top) / dpi_ratio)
        )

    def _get_vertical_empty_space(self, taskbar_rect: QRect, edge: int) -> dict:
        """Find empty space on vertical (left/right) taskbar - simplified."""
        dpi_ratio = self._get_dpi_ratio()
        print(f"[MonitorManager] Detecting vertical empty space, DPI ratio: {dpi_ratio}")

        try:
            taskbar_hwnd = self._user32.FindWindowW("Shell_TrayWnd", None)
            start_hwnd = self._user32.FindWindowExW(taskbar_hwnd, 0, "Start", None)
            start_rect = self._get_window_rect(start_hwnd)

            if start_rect and dpi_ratio and dpi_ratio != 1.0:
                start_top = int(start_rect.top / dpi_ratio)
                start_bottom = int(start_rect.bottom / dpi_ratio)
                empty_height = start_top - taskbar_rect.top()
                if empty_height < 50:
                    empty_height = taskbar_rect.bottom() - start_bottom

                print(f"[MonitorManager] Vertical empty space: height={empty_height}, y={start_top}")
                return {
                    "width": empty_height,
                    "x": start_top,
                    "edge": edge,
                    "available": empty_height > 50
                }
            elif start_rect:
                start_top = start_rect.top
                empty_height = start_top - taskbar_rect.top()
                if empty_height < 50:
                    empty_height = taskbar_rect.bottom() - start_rect.bottom
                return {
                    "width": empty_height,
                    "x": start_top,
                    "edge": edge,
                    "available": empty_height > 50
                }
        except Exception as e:
            print(f"[MonitorManager] Vertical empty space detection failed: {e}")

        print("[MonitorManager] Vertical fallback empty space")
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
                vis_x, vis_y = self._get_position_for_alignment(taskbar, vis_w, vis_height, alignment_hint, edge)
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
                vis_x, vis_y = self._get_position_for_alignment(taskbar, vis_w, vis_height, alignment_hint, edge)
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
                vis_x, vis_y = self._get_position_for_alignment_vertical(taskbar, vis_h, vis_height, alignment_hint, edge)
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
                vis_x, vis_y = self._get_position_for_alignment_vertical(taskbar, vis_h, vis_height, alignment_hint, edge)
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
            pos = self._verify_bounds_vertical(pos, taskbar, edge)

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

    def _verify_bounds_horizontal(self, pos: tuple, taskbar: QRect, edge: int) -> tuple:
        """Verify bounds for horizontal (bottom/top) taskbar."""
        x, y, w, h = pos

        # Clamp to taskbar bounds for horizontal edges
        if x < taskbar.left():
            x = taskbar.left()
        if x + w > taskbar.right():
            w = max(100, taskbar.right() - x)

        if edge == ABE_BOTTOM:
            # Visualizer should be within taskbar vertically
            if y < taskbar.top():
                y = taskbar.top()
            if y + h > taskbar.bottom():
                h = max(20, taskbar.bottom() - y)
        else:  # ABE_TOP
            if y < taskbar.top():
                y = taskbar.top()
            if y + h > taskbar.bottom():
                h = max(20, taskbar.bottom() - y)

        # If still out of bounds, use safe position within taskbar
        if w < 50 or h < 20:
            print("[MonitorManager] Position out of bounds, using safe position within taskbar")
            safe_w = max(100, taskbar.width() // 4)
            return (taskbar.left(), taskbar.top() + (taskbar.height() - 40) // 2, safe_w, 40)

        return (x, y, w, h)

    def _verify_bounds_vertical(self, pos: tuple, screen_avail: QRect) -> tuple:
        """Verify bounds for vertical (left/right) taskbar."""
        x, y, w, h = pos

        # Clamp to screen available area for vertical edges
        if x < screen_avail.left():
            x = screen_avail.left()
        if y < screen_avail.top():
            y = screen_avail.top()
        if x + w > screen_avail.right():
            w = max(20, screen_avail.right() - x)
        if y + h > screen_avail.bottom():
            h = max(100, screen_avail.bottom() - y)

        # If still out of bounds, use safe position
        if w < 20 or h < 50:
            print("[MonitorManager] Position out of bounds, using safe position")
            return (screen_avail.left(), screen_avail.top() + screen_avail.height() // 4, 40, screen_avail.height() // 2)

        return (x, y, w, h)

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
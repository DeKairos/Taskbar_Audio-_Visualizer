"""Native taskbar surface with off-screen Qt drawing and native button input."""
import ctypes as c
from ctypes import wintypes as w
import os
from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication
from visualizer_window import VisualizerWindow

u = c.WinDLL('user32', use_last_error=True)
g = c.WinDLL('gdi32', use_last_error=True)
k = c.WinDLL('kernel32', use_last_error=True)
PROC = c.WINFUNCTYPE(c.c_ssize_t, w.HWND, w.UINT, w.WPARAM, w.LPARAM)

class WC(c.Structure):
    _fields_ = [('style', w.UINT), ('proc', PROC), ('cls_extra', c.c_int),
                ('wnd_extra', c.c_int), ('instance', w.HINSTANCE), ('icon', w.HANDLE),
                ('cursor', w.HANDLE), ('background', w.HBRUSH), ('menu', w.LPCWSTR),
                ('name', w.LPCWSTR)]

class BI(c.Structure):
    _fields_ = [('size', w.DWORD), ('width', w.LONG), ('height', w.LONG),
                ('planes', w.WORD), ('bits', w.WORD), ('compression', w.DWORD),
                ('image_size', w.DWORD), ('x', w.LONG), ('y', w.LONG),
                ('used', w.DWORD), ('important', w.DWORD), ('colors', w.DWORD * 3)]

class BLEND(c.Structure):
    _fields_ = [('op', w.BYTE), ('flags', w.BYTE), ('alpha', w.BYTE), ('format', w.BYTE)]

def sig(lib, name, result, args):
    fn = getattr(lib, name)
    fn.restype, fn.argtypes = result, args
    return fn

sig(k, 'GetModuleHandleW', w.HMODULE, [w.LPCWSTR])
sig(u, 'DefWindowProcW', c.c_ssize_t, [w.HWND, w.UINT, w.WPARAM, w.LPARAM])
sig(u, 'RegisterClassW', w.WORD, [c.POINTER(WC)])
sig(u, 'UnregisterClassW', w.BOOL, [w.LPCWSTR, w.HINSTANCE])
sig(u, 'CreateWindowExW', w.HWND, [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD,
    c.c_int, c.c_int, c.c_int, c.c_int, w.HWND, w.HMENU, w.HINSTANCE, c.c_void_p])
sig(u, 'DestroyWindow', w.BOOL, [w.HWND])
sig(u, 'IsWindowVisible', w.BOOL, [w.HWND])
sig(u, 'GetParent', w.HWND, [w.HWND])
sig(u, 'ShowWindow', w.BOOL, [w.HWND, c.c_int])
sig(u, 'SetWindowPos', w.BOOL, [w.HWND, w.HWND, c.c_int, c.c_int, c.c_int, c.c_int, w.UINT])
sig(u, 'ScreenToClient', w.BOOL, [w.HWND, c.POINTER(w.POINT)])
sig(u, 'GetWindowRect', w.BOOL, [w.HWND, c.POINTER(w.RECT)])
sig(u, 'GetWindowLongPtrW', c.c_ssize_t, [w.HWND, c.c_int])
sig(u, 'SetWindowLongPtrW', c.c_ssize_t, [w.HWND, c.c_int, c.c_ssize_t])
sig(u, 'SetCapture', w.HWND, [w.HWND])
sig(u, 'ReleaseCapture', w.BOOL, [])
sig(u, 'UpdateLayeredWindow', w.BOOL, [w.HWND, w.HDC, c.POINTER(w.POINT),
    c.POINTER(w.SIZE), w.HDC, c.POINTER(w.POINT), w.DWORD, c.POINTER(BLEND), w.DWORD])
sig(g, 'CreateCompatibleDC', w.HDC, [w.HDC])
sig(g, 'DeleteDC', w.BOOL, [w.HDC])
sig(g, 'CreateDIBSection', w.HBITMAP, [w.HDC, c.POINTER(BI), w.UINT,
    c.POINTER(c.c_void_p), w.HANDLE, w.DWORD])
sig(g, 'SelectObject', w.HANDLE, [w.HDC, w.HANDLE])
sig(g, 'DeleteObject', w.BOOL, [w.HANDLE])
sig(k, 'GetCurrentProcess', w.HANDLE, [])
sig(u, 'GetGuiResources', w.DWORD, [w.HANDLE, w.DWORD])

sig(u, 'IsWindow', w.BOOL, [w.HWND])

class NativeTaskbarSurface:
    def __init__(self, parent, event_handler=None):
        self.frames = self.errors = self.shows = self.hides = 0
        self.position_changes = self.position_messages = self.erase_messages = 0
        self._bounds = None
        self.interactive = False
        self.event_handler = event_handler
        self.dc = self.bitmap = self.old = self.hwnd = None
        self.buffer = c.c_void_p()
        self.dim = None
        self.instance = k.GetModuleHandleW(None)
        self.name = f'AudioVisualizerNativeSurface{os.getpid()}'
        @PROC
        def callback(hwnd, msg, wp, lp):
            if self.event_handler is not None:
                result = self.event_handler(hwnd, msg, wp, lp)
                if result is not None:
                    return result
            if msg == 0x0014:  # No background erase between submitted frames.
                self.erase_messages += 1
                return 1
            if msg == 0x0047:
                self.position_messages += 1
            if msg == 0x0084:
                return -1  # HTTRANSPARENT: preserve taskbar clicks.
            if msg == 0x0021:
                return 3  # MA_NOACTIVATE
            if msg == 0x0018:
                if wp:
                    self.shows += 1
                else:
                    self.hides += 1
            return u.DefWindowProcW(hwnd, msg, wp, lp)
        self.callback = callback
        wc = WC(0, callback, 0, 0, self.instance, None, None, None, None, self.name)
        if not u.RegisterClassW(c.byref(wc)):
            raise c.WinError(c.get_last_error())
        self.hwnd = u.CreateWindowExW(0x080800A0, self.name, 'Audio Visualizer',
            0x40000000, 0, 0, 1, 1, parent, None, self.instance, None)
        if not self.hwnd:
            raise c.WinError(c.get_last_error())
        self.parent = parent

    def set_interactive(self, interactive):
        if interactive == self.interactive:
            return
        style = u.GetWindowLongPtrW(self.hwnd, -20)
        new_style = style & ~0x20 if interactive else style | 0x20
        c.set_last_error(0)
        if not u.SetWindowLongPtrW(self.hwnd, -20, new_style) and c.get_last_error():
            raise c.WinError(c.get_last_error())
        self.interactive = interactive

    def position(self, x, y, width, height):
        point = w.POINT(x, y)
        if not u.ScreenToClient(self.parent, c.byref(point)):
            raise c.WinError(c.get_last_error())
        bounds = (point.x, point.y, width, height)
        if bounds == self._bounds:
            return
        flags = 0x0010  # Initial placement puts the native child above siblings.
        if self._bounds is not None:
            flags |= 0x0004  # SWP_NOZORDER: subsequent geometry changes only.
        if not u.SetWindowPos(self.hwnd, 0, *bounds, flags):
            raise c.WinError(c.get_last_error())
        self._bounds = bounds
        self.position_changes += 1

    def allocate(self, width, height):
        if self.dim == (width, height):
            return
        self.free_bitmap()
        self.dc = g.CreateCompatibleDC(None)
        bi = BI()
        bi.size = 40
        bi.width, bi.height = width, -height
        bi.planes, bi.bits = 1, 32
        self.bitmap = g.CreateDIBSection(self.dc, c.byref(bi), 0, c.byref(self.buffer), None, 0)
        if not self.bitmap:
            raise c.WinError(c.get_last_error())
        self.old = g.SelectObject(self.dc, self.bitmap)
        self.dim = (width, height)

    def submit(self, image, opacity):
        self.allocate(image.width(), image.height())
        c.memmove(self.buffer, int(image.constBits()), image.sizeInBytes())
        size, source = w.SIZE(*self.dim), w.POINT(0, 0)
        blend = BLEND(0, 0, round(max(0, min(1, opacity)) * 255), 1)
        if not u.UpdateLayeredWindow(self.hwnd, None, None, c.byref(size), self.dc,
                c.byref(source), 0, c.byref(blend), 2):
            self.errors += 1
            raise c.WinError(c.get_last_error())
        self.frames += 1
        if not u.IsWindowVisible(self.hwnd):
            u.ShowWindow(self.hwnd, 4)

    def free_bitmap(self):
        if self.dc:
            g.SelectObject(self.dc, self.old)
            g.DeleteObject(self.bitmap)
            g.DeleteDC(self.dc)
        self.dc = self.bitmap = self.old = None

    def close(self):
        if self.hwnd:
            u.DestroyWindow(self.hwnd)
            self.hwnd = None
        self.free_bitmap()
        u.UnregisterClassW(self.name, self.instance)

class TaskbarVisualizerWindow(VisualizerWindow):
    """Display Qt frames in a native taskbar child without reparenting Qt."""
    _supports_widget_controls = False

    def __init__(self, cfg):
        self.surface = None
        self.image = None
        self.native_clicks = 0
        self._native_pressed = None
        self._surface_scale = 1.0
        super().__init__(cfg)
        self.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        QApplication.instance().aboutToQuit.connect(self.cleanup_surface)

    def _ensure_topmost(self, force_bounce=False):
        pass

    def _enable_click_through(self):
        self._click_through_enabled = True

    def _disable_click_through(self):
        pass

    def _refresh_window_styles(self):
        pass

    def update(self, *args):
        # _tick renders the complete frame into self.image. A queued QWidget
        # repaint would draw the same frame again into an unused backing store.
        pass

    def _poll_media_overlay_click(self):
        if self.surface and self.surface.interactive:
            # Native button messages own card clicks; polling only reveals it.
            self._left_pressed_last = bool(u.GetAsyncKeyState(1) & 0x8000)
            return
        super()._poll_media_overlay_click()

    def _native_control_at(self, point):
        if self._media_overlay_alpha <= 0.01:
            return None
        return next((name for name, rect in self.controls_rects.items() if rect.contains(point)), None)

    def _native_mouse_point(self, hwnd, lp, screen=False):
        point = w.POINT(c.c_short(lp & 0xffff).value, c.c_short((lp >> 16) & 0xffff).value)
        if screen and not u.ScreenToClient(hwnd, c.byref(point)):
            return None
        return QPoint(round(point.x / self._surface_scale), round(point.y / self._surface_scale))

    def _native_message(self, hwnd, msg, wp, lp):
        if msg not in (0x0084, 0x0201, 0x0202, 0x0215):
            return None
        if msg == 0x0215:  # WM_CAPTURECHANGED: cancel an interrupted press.
            self._native_pressed = None
            return 0
        point = self._native_mouse_point(hwnd, lp, screen=msg == 0x0084)
        name = self._native_control_at(point) if point is not None else None
        if msg == 0x0084:
            return 1 if name else -1  # HTCLIENT for buttons, HTTRANSPARENT elsewhere.
        if msg == 0x0201:
            self._native_pressed = name
            if name:
                self._button_target[name] = 0.92
                u.SetCapture(hwnd)
            return 0
        pressed = self._native_pressed
        self._native_pressed = None
        u.ReleaseCapture()
        if pressed:
            self._button_target[pressed] = 1.0
        if name and name == pressed:
            self.native_clicks += 1
            QTimer.singleShot(0, lambda x=point.x(), y=point.y(): self.handle_media_click(x, y))
        return 0

    def setWindowOpacity(self, opacity):
        # Native surface owns opacity; never change the hidden Qt native window.
        pass

    def position_on_taskbar(self):
        super().position_on_taskbar()
        if self._ensure_surface():
            self.place_surface()

    def _ensure_surface(self):
        """Recreate the native host if Explorer or the selected taskbar changes."""
        parent = self._monitor_mgr._find_taskbar_hwnd(self.cfg.get('visualizer_monitor', 0))
        if self.surface and self.surface.parent == parent and u.IsWindow(self.surface.hwnd):
            return True
        if self.surface:
            self.surface.close()
            self.surface = None
        if not parent:
            return False
        self.surface = NativeTaskbarSurface(parent, self._native_message)
        return True

    def place_surface(self):
        index = self.cfg.get('visualizer_monitor', 0)
        mon = self._monitor_mgr.get_monitor(index)
        native = self._monitor_mgr._window_monitor(self.surface.parent)
        geo, ratio = mon['geometry'], mon['ratio']
        self._surface_scale = ratio
        self.surface.position(round(native.rcMonitor.left + (self.x() - geo.x()) * ratio),
            round(native.rcMonitor.top + (self.y() - geo.y()) * ratio),
            round(self.width() * ratio), round(self.height() * ratio))

    def _maybe_reposition(self):
        super()._maybe_reposition()
        if self._ensure_surface():
            self.place_surface()

    def _tick(self):
        super()._tick()
        if not self.surface or not u.IsWindow(self.surface.hwnd):
            return
        if not self.isVisible() or self._opacity <= 0:
            self.surface.set_interactive(False)
            if u.IsWindowVisible(self.surface.hwnd):
                u.ShowWindow(self.surface.hwnd, 0)
            return
        ratio = self._monitor_mgr.get_monitor(self.cfg.get('visualizer_monitor', 0))['ratio']
        size = (round(self.width() * ratio), round(self.height() * ratio))
        if self.image is None or (self.image.width(), self.image.height()) != size:
            self.image = QImage(*size, QImage.Format.Format_ARGB32_Premultiplied)
            self.image.setDevicePixelRatio(ratio)
        self.image.fill(0)
        self.render(self.image)
        try:
            self.surface.submit(self.image, self._opacity)
            self.surface.set_interactive(self._media_overlay_alpha > 0.01)
        except OSError as exc:
            if not u.IsWindow(self.surface.hwnd):
                return  # The reposition timer recovers after Explorer restarts.
            print('SURFACE_ERROR', str(exc), flush=True)
            QApplication.exit(2)

    def cleanup_surface(self):
        self.timer.stop()
        if self.surface:
            self.surface.close()

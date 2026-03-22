"""
input_hooks.py — Global mouse hooks for visualizer interactions.

Contains click detection over the visualizer window region while preserving
click-through behavior on the overlay itself.
"""
import ctypes
import ctypes.wintypes
import threading
import time

# Win32 constants
WH_MOUSE_LL = 14
WM_LBUTTONDOWN = 0x0201
HC_ACTION = 0


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", ctypes.wintypes.POINT),
        ("mouseData", ctypes.wintypes.DWORD),
        ("flags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


HOOKPROC = ctypes.WINFUNCTYPE(
    ctypes.c_long,
    ctypes.c_int,
    ctypes.wintypes.WPARAM,
    ctypes.wintypes.LPARAM,
)


class VisualizerClickWatcher:
    """Captures left-clicks over the visualizer rect and triggers a callback."""

    def __init__(self, visualizer_hwnd: int, on_click):
        self._vis_hwnd = int(visualizer_hwnd) if visualizer_hwnd else None
        self.on_click = on_click
        self._hook = None
        self._running = False
        self._thread = None
        self._last_click_ts = 0.0

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._hook_thread, daemon=True)
        self._thread.start()
        print("[VisualizerClickWatcher] started.")

    def stop(self):
        self._running = False

    def _hook_thread(self):
        """Run low-level mouse hook in its own message loop thread."""
        user32 = ctypes.windll.user32

        rect = ctypes.wintypes.RECT()

        def _cursor_over_visualizer(x: int, y: int) -> bool:
            if not self._vis_hwnd:
                return False
            if not user32.IsWindowVisible(self._vis_hwnd):
                return False
            if not user32.GetWindowRect(self._vis_hwnd, ctypes.byref(rect)):
                return False
            return rect.left <= x <= rect.right and rect.top <= y <= rect.bottom

        @HOOKPROC
        def callback(nCode, wParam, lParam):
            if nCode == HC_ACTION and wParam == WM_LBUTTONDOWN:
                info = ctypes.cast(
                    lParam, ctypes.POINTER(MSLLHOOKSTRUCT)
                ).contents
                if _cursor_over_visualizer(info.pt.x, info.pt.y):
                    now = time.time()
                    # Debounce quick repeats from shell-level click propagation.
                    if now - self._last_click_ts > 0.18:
                        self._last_click_ts = now
                        try:
                            self.on_click()
                        except Exception:
                            pass
            return user32.CallNextHookEx(None, nCode, wParam, lParam)

        self._hook = user32.SetWindowsHookExW(WH_MOUSE_LL, callback, None, 0)

        msg = ctypes.wintypes.MSG()
        while self._running:
            if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            else:
                time.sleep(0.01)

        if self._hook:
            user32.UnhookWindowsHookEx(self._hook)

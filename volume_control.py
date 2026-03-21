"""
volume_control.py — System volume control + scroll-hook over the visualizer.

Uses pycaw for Windows Core Audio volume control.
Installs a low-level mouse hook (WH_MOUSE_LL) to capture scroll events
over the visualizer window region while keeping click-through intact.
"""
import ctypes
import ctypes.wintypes
import threading
import time

try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from comtypes import CLSCTX_ALL
    HAS_PYCAW = True
except ImportError:
    HAS_PYCAW = False

# Win32 constants
WH_MOUSE_LL = 14
WM_MOUSEWHEEL = 0x020A
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


class VolumeScroller:
    """Captures mouse scroll over the visualizer's rect and adjusts volume."""

    STEP = 0.02  # 2% per scroll notch

    def __init__(self, visualizer_window):
        self.vis = visualizer_window
        self._hook = None
        self._running = False
        self._thread = None
        self._volume = None
        self._vis_hwnd = None
        self._volume_display = 0.0   # current volume 0-1 (for overlay)
        self._volume_show_until = 0.0
        self._init_volume()

    def _init_volume(self):
        if not HAS_PYCAW:
            return
        try:
            devices = AudioUtilities.GetSpeakers()
            # pycaw API varies by version: older builds expose Activate,
            # newer builds expose EndpointVolume directly.
            if hasattr(devices, "Activate"):
                interface = devices.Activate(
                    IAudioEndpointVolume._iid_, CLSCTX_ALL, None
                )
                self._volume = interface.QueryInterface(IAudioEndpointVolume)
            elif hasattr(devices, "EndpointVolume"):
                self._volume = devices.EndpointVolume
            else:
                raise AttributeError("No compatible endpoint volume API found")
        except Exception as e:
            print(f"[VolumeScroller] init failed: {e}")

    def start(self):
        if not HAS_PYCAW or self._volume is None:
            print("[VolumeScroller] pycaw not available — skipping.")
            return
        self._running = True
        self._thread = threading.Thread(target=self._hook_thread, daemon=True)
        self._thread.start()
        print("[VolumeScroller] started.")

    def stop(self):
        self._running = False

    @property
    def show_volume(self) -> bool:
        return time.time() < self._volume_show_until

    @property
    def volume_pct(self) -> int:
        return int(self._volume_display * 100)

    # ── hook thread ─────────────────────────────────────────────────

    def _hook_thread(self):
        """Must run in its own thread with a message loop."""
        user32 = ctypes.windll.user32

        # Cache visualizer HWND once; avoid calling Qt methods inside hook callback.
        try:
            self._vis_hwnd = int(self.vis.winId())
        except Exception:
            self._vis_hwnd = None

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
            if nCode == HC_ACTION and wParam == WM_MOUSEWHEEL:
                info = ctypes.cast(
                    lParam, ctypes.POINTER(MSLLHOOKSTRUCT)
                ).contents
                # mouseData high word = wheel delta (positive = up)
                delta = ctypes.c_short(info.mouseData >> 16).value

                # Keep callback lightweight; use Win32 rect test only.
                x, y = info.pt.x, info.pt.y
                if _cursor_over_visualizer(x, y):
                    self._adjust(delta)
            return user32.CallNextHookEx(None, nCode, wParam, lParam)

        self._hook = user32.SetWindowsHookExW(
            WH_MOUSE_LL, callback, None, 0
        )
        msg = ctypes.wintypes.MSG()
        while self._running:
            # Pump messages so the hook gets called
            if user32.PeekMessageW(
                ctypes.byref(msg), None, 0, 0, 1  # PM_REMOVE
            ):
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            else:
                time.sleep(0.01)

        if self._hook:
            user32.UnhookWindowsHookEx(self._hook)

    def _adjust(self, delta: int):
        if self._volume is None:
            return
        try:
            cur = self._volume.GetMasterVolumeLevelScalar()
            step = self.STEP if delta > 0 else -self.STEP
            new_vol = max(0.0, min(1.0, cur + step))
            self._volume.SetMasterVolumeLevelScalar(new_vol, None)
            self._volume_display = new_vol
            self._volume_show_until = time.time() + 1.5
        except Exception:
            pass

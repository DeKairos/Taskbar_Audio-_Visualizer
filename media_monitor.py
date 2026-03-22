"""
media_monitor.py — Poll Windows media session for now-playing info.

Uses Windows.Media.Control (WinRT via winsdk) to fetch:
  • title, artist
  • album art thumbnail → dominant colour extraction

Runs a lightweight polling loop on a background thread.
"""
import asyncio
import threading
import time
import io
import traceback

try:
    from winsdk.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as SessionManager,
    )
    from winsdk.windows.storage.streams import (
        DataReader,
        Buffer,
        InputStreamOptions,
    )
    HAS_WINSDK = True
except ImportError:
    HAS_WINSDK = False


class MediaInfo:
    """Snapshot of current media state."""
    __slots__ = (
        "title",
        "artist",
        "album",
        "accent_rgb",
        "cover_bytes",
        "changed",
    )

    def __init__(self):
        self.title: str = ""
        self.artist: str = ""
        self.album: str = ""
        self.accent_rgb: tuple = (80, 200, 240)   # default cyan
        self.cover_bytes: bytes | None = None
        self.changed: bool = False


class MediaMonitor:
    """Polls Windows media session in a daemon thread."""

    def __init__(self, poll_interval: float = 2.0):
        self.interval = poll_interval
        self.info = MediaInfo()
        self._prev_key = ""
        self._running = False
        self._thread = None

    def start(self):
        if not HAS_WINSDK:
            print("[MediaMonitor] winsdk not available — skipping.")
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("[MediaMonitor] started.")

    def stop(self):
        self._running = False

    # ── internal ────────────────────────────────────────────────────

    def _loop(self):
        while self._running:
            try:
                asyncio.run(self._poll_once())
            except Exception:
                traceback.print_exc()
            time.sleep(self.interval)

    async def _poll_once(self):
        manager = await SessionManager.request_async()
        session = manager.get_current_session()
        if session is None:
            # Force next valid session to be treated as a fresh track snapshot,
            # even if title/artist/album are unchanged after device switches.
            self._prev_key = ""
            if self.info.title:
                self.info.title = ""
                self.info.artist = ""
                self.info.album = ""
                self.info.cover_bytes = None
                self.info.changed = True
            return

        props = await session.try_get_media_properties_async()
        title = props.title or ""
        artist = props.artist or ""
        album = getattr(props, "album_title", "") or ""
        key = f"{artist}|{title}|{album}"

        if key != self._prev_key:
            self._prev_key = key
            self.info.title = title
            self.info.artist = artist
            self.info.album = album
            self.info.changed = True

            # Try to extract album art dominant colour
            try:
                thumb = props.thumbnail
                if thumb:
                    stream = await thumb.open_read_async()
                    size = int(stream.size) if stream.size else 0
                    if size <= 0:
                        size = 262_144
                    # Read the full thumbnail so image decode is valid for cover preview.
                    buf = Buffer(size)
                    await stream.read_async(
                        buf, buf.capacity, InputStreamOptions.READ_AHEAD
                    )
                    reader = DataReader.from_buffer(buf)
                    data = bytearray(buf.length)
                    reader.read_bytes(data)
                    raw = bytes(data)
                    self.info.cover_bytes = raw or None
                    rgb = self._dominant_color(raw)
                    if rgb:
                        self.info.accent_rgb = rgb
                else:
                    self.info.cover_bytes = None
            except Exception:
                self.info.cover_bytes = None
                pass   # thumbnail extraction is best-effort

    @staticmethod
    def _dominant_color(img_bytes: bytes):
        """Extract dominant colour from raw image bytes (JPEG/PNG).
        Uses simple averaging of brightest 30% pixels.
        Returns (R, G, B) or None on failure.
        """
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            img = img.resize((50, 50))
            pixels = list(img.getdata())
            # sort by brightness, take top 30%
            pixels.sort(key=lambda p: sum(p), reverse=True)
            top = pixels[:max(1, len(pixels) // 3)]
            r = sum(p[0] for p in top) // len(top)
            g = sum(p[1] for p in top) // len(top)
            b = sum(p[2] for p in top) // len(top)
            # Ensure minimum saturation & brightness
            mx = max(r, g, b, 1)
            if mx < 80:
                scale = 80 / mx
                r, g, b = int(r * scale), int(g * scale), int(b * scale)
            return (min(r, 255), min(g, 255), min(b, 255))
        except Exception:
            return None

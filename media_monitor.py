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
import traceback
import ctypes
import queue
from color_themes import artwork_accent

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


# Virtual-Key codes for multimedia keys (used by fallback control)
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3


class MediaInfo:
    """Snapshot of current media state."""
    __slots__ = (
        "title",
        "artist",
        "album",
        "accent_rgb",
        "cover_bytes",
        "changed",
        "source_app_id",
    )

    def __init__(self):
        self.title: str = ""
        self.artist: str = ""
        self.album: str = ""
        self.accent_rgb: tuple = (80, 200, 240)   # default cyan
        self.cover_bytes: bytes | None = None
        self.changed: bool = False
        self.source_app_id: str = ""


class MediaMonitor:
    """Polls Windows media session in a daemon thread."""

    def __init__(self, poll_interval: float = 2.0):
        self.interval = poll_interval
        self.info = MediaInfo()
        self._prev_key = ""
        self._running = False
        self._thread = None
        self._stop_event = threading.Event()
        self._commands = queue.Queue()

    def start(self):
        if not HAS_WINSDK:
            print("[MediaMonitor] winsdk not available — skipping.")
            return
        if self._thread and self._thread.is_alive():
            return
        # Discard commands from a previous run, including its stop sentinel.
        while True:
            try:
                self._commands.get_nowait()
            except queue.Empty:
                break
        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("[MediaMonitor] started.")

    def stop(self):
        self._running = False
        self._stop_event.set()
        self._commands.put(None)
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=max(1.0, self.interval + 1.0))
        self._thread = None

    # ── internal ────────────────────────────────────────────────────

    def _loop(self):
        next_poll = 0.0
        while self._running and not self._stop_event.is_set():
            if time.monotonic() >= next_poll:
                try:
                    asyncio.run(self._poll_once())
                except Exception:
                    traceback.print_exc()
                next_poll = time.monotonic() + self.interval
            try:
                command = self._commands.get(timeout=max(0.0, next_poll - time.monotonic()))
            except queue.Empty:
                continue
            if not self._running or command is None:
                continue
            action, source_app_id = command
            try:
                accepted = asyncio.run(asyncio.wait_for(self._control_session(action, source_app_id), 3.0))
                print(f"[MediaMonitor] session control {action}: {'accepted' if accepted else 'unavailable'}")
            except Exception as exc:
                print(f"[MediaMonitor] session control {action} failed: {exc}")

    async def _poll_once(self):
        manager = await SessionManager.request_async()
        session = manager.get_current_session()
        if session is None:
            # Force next valid session to be treated as a fresh track snapshot,
            # even if title/artist/album are unchanged after device switches.
            self._prev_key = ""
            if self.info.title or self.info.cover_bytes:
                empty = MediaInfo()
                empty.changed = True
                self.info = empty
            return

        props = await session.try_get_media_properties_async()
        title = props.title or ""
        artist = props.artist or ""
        album = getattr(props, "album_title", "") or ""
        key = (getattr(session, "source_app_user_model_id", ""), artist, title, album)

        if key != self._prev_key:
            # Build the whole snapshot before publishing it to the UI thread.
            snapshot = MediaInfo()
            snapshot.title = title
            snapshot.artist = artist
            snapshot.album = album
            snapshot.source_app_id = getattr(session, "source_app_user_model_id", "") or ""
            snapshot.changed = True

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
                    snapshot.cover_bytes = raw or None
                    rgb = self._dominant_color(raw)
                    if rgb:
                        snapshot.accent_rgb = rgb
                    else:
                        snapshot.cover_bytes = None
                else:
                    snapshot.cover_bytes = None
            except Exception:
                snapshot.cover_bytes = None
                pass   # thumbnail extraction is best-effort

            self._prev_key = key
            self.info = snapshot

    # ── Transport control (target the session displayed on the card) ───────
    async def _control_session(self, action, source_app_id):
        manager = await SessionManager.request_async()
        if source_app_id:
            session = next((item for item in manager.get_sessions()
                            if item.source_app_user_model_id == source_app_id), None)
        else:
            session = manager.get_current_session()
        if session is None:
            return False
        method = {
            'play': 'try_play_async', 'pause': 'try_pause_async',
            'toggle_play_pause': 'try_toggle_play_pause_async',
            'next_track': 'try_skip_next_async', 'previous_track': 'try_skip_previous_async',
        }[action]
        return bool(await getattr(session, method)())

    def _request_transport(self, action, fallback_key):
        if not HAS_WINSDK:
            self._send_media_key(fallback_key)
            return
        self.start()
        self._commands.put((action, self.info.source_app_id))

    def _send_media_key(self, vk: int):
        """Send a multimedia key (via Win32) as a best-effort transport control.

        Used only when the WinRT module is unavailable.
        """
        try:
            # key down
            ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
            # short pause to ensure the OS registers the key
            time.sleep(0.02)
            # key up
            ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
        except Exception:
            print(f"[MediaMonitor] failed to send media key 0x{vk:02X}")

    def play(self):
        """Request playback on the displayed media session."""
        self._request_transport('play', VK_MEDIA_PLAY_PAUSE)

    def pause(self):
        """Request pause on the displayed media session."""
        self._request_transport('pause', VK_MEDIA_PLAY_PAUSE)

    def toggle_play_pause(self):
        """Toggle playback state."""
        self._request_transport('toggle_play_pause', VK_MEDIA_PLAY_PAUSE)

    def next_track(self):
        """Skip to next track."""
        self._request_transport('next_track', VK_MEDIA_NEXT_TRACK)

    def previous_track(self):
        """Skip to previous track."""
        self._request_transport('previous_track', VK_MEDIA_PREV_TRACK)

    @staticmethod
    def _dominant_color(img_bytes: bytes):
        return artwork_accent(img_bytes)

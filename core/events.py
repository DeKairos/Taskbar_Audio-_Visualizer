"""
core/events.py — Lightweight typed event bus for decoupling modules.

Usage:
    from core.events import bus, Event

    # Subscribe
    def on_track(info):
        print(info.title)
    bus.subscribe("track_changed", on_track)

    # Publish
    bus.publish("track_changed", title="Song", artist="Artist")

Events are dispatched synchronously on the publisher's thread.
For Qt thread safety, connect via QTimer or QMetaObject.invokeMethod.
"""
import logging
from typing import Any, Callable, Dict, List


logger = logging.getLogger(__name__)


class Event:
    """A single event dispatch."""
    __slots__ = ("name", "data")

    def __init__(self, name: str, **data: Any):
        self.name = name
        self.data = data

    def __repr__(self):
        return f"Event({self.name!r}, {', '.join(f'{k}={v!r}' for k,v in self.data.items())})"


class EventBus:
    """Simple pub/sub event bus with named event channels."""

    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}

    def subscribe(self, event_name: str, callback: Callable) -> None:
        """Register a callback for a named event."""
        self._subscribers.setdefault(event_name, []).append(callback)

    def unsubscribe(self, event_name: str, callback: Callable) -> None:
        """Remove a previously registered callback."""
        subs = self._subscribers.get(event_name)
        if subs and callback in subs:
            subs.remove(callback)

    def publish(self, event_name: str, **kwargs: Any) -> None:
        """Fire an event, calling all subscribers with the provided kwargs."""
        for cb in self._subscribers.get(event_name, []):
            try:
                cb(**kwargs)
            except Exception:
                # One faulty subscriber must not prevent other subscribers running.
                logger.exception("Event subscriber failed for '%s'", event_name)

    def clear(self, event_name = None) -> None:
        """Remove all subscribers for an event, or all events if name is None."""
        if event_name:
            self._subscribers.pop(event_name, None)
        else:
            self._subscribers.clear()


# Global singleton
bus = EventBus()

# ── Well-known event names (use these to avoid typos) ──────────────
TRACK_CHANGED = "track_changed"
AUDIO_DATA = "audio_data"
BEAT_DETECTED = "beat_detected"
THEME_CHANGED = "theme_changed"
CONFIG_UPDATED = "config_updated"
VOLUME_CHANGED = "volume_changed"
VISIBILITY_CHANGED = "visibility_changed"

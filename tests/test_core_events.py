"""Tests for core.events module."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_event_bus_subscribe_publish():
    from core.events import bus
    received = []
    def handler(x):
        received.append(x)
    bus.subscribe("test_event", handler)
    bus.publish("test_event", x=42)
    assert received == [42]
    bus.clear()


def test_event_bus_multiple_subscribers():
    from core.events import bus
    results = []
    bus.subscribe("multi", lambda a: results.append(f"A:{a}"))
    bus.subscribe("multi", lambda a: results.append(f"B:{a}"))
    bus.publish("multi", a="hello")
    assert "A:hello" in results
    assert "B:hello" in results
    bus.clear()


def test_event_bus_unsubscribe():
    from core.events import bus
    results = []
    def handler(v):
        results.append(v)
    bus.subscribe("unsub_test", handler)
    bus.publish("unsub_test", v=1)
    bus.unsubscribe("unsub_test", handler)
    bus.publish("unsub_test", v=2)
    assert results == [1]
    bus.clear()


def test_event_bus_clear():
    from core.events import bus
    results = []
    bus.subscribe("c1", lambda: results.append("c1"))
    bus.subscribe("c2", lambda: results.append("c2"))
    bus.clear("c1")
    bus.publish("c1")
    bus.publish("c2")
    assert results == ["c2"]
    bus.clear()


def test_event_names_exist():
    from core.events import (
        TRACK_CHANGED, AUDIO_DATA, BEAT_DETECTED,
        THEME_CHANGED, CONFIG_UPDATED, VOLUME_CHANGED,
        VISIBILITY_CHANGED,
    )
    assert TRACK_CHANGED == "track_changed"
    assert AUDIO_DATA == "audio_data"
    assert BEAT_DETECTED == "beat_detected"


def test_subscriber_failure_does_not_stop_other_subscribers(caplog):
    from core.events import bus

    def failing_subscriber():
        raise RuntimeError("subscriber failed")

    results = []
    bus.subscribe("failure_test", failing_subscriber)
    bus.subscribe("failure_test", lambda: results.append("ok"))

    with caplog.at_level("ERROR"):
        bus.publish("failure_test")

    assert results == ["ok"]
    assert "Event subscriber failed" in caplog.text
    bus.clear()

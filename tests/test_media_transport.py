"""Transport buttons target the displayed session without foreground media keys."""
from types import SimpleNamespace
import threading

import pytest

import media_monitor
from media_monitor import MediaMonitor


def complete(coroutine):
    try:
        with pytest.raises(StopIteration) as stopped:
            coroutine.send(None)
        return stopped.value.value
    finally:
        coroutine.close()


@pytest.mark.parametrize('action,method', [
    ('play', 'try_play_async'), ('pause', 'try_pause_async'),
    ('toggle_play_pause', 'try_toggle_play_pause_async'),
    ('next_track', 'try_skip_next_async'), ('previous_track', 'try_skip_previous_async'),
])
def test_controls_target_displayed_player_even_when_current_session_differs(monkeypatch, action, method):
    calls = []
    async def control():
        calls.append(action)
        return True
    displayed = SimpleNamespace(source_app_user_model_id='displayed-player', **{method: control})
    other = SimpleNamespace(source_app_user_model_id='foreground-player')
    async def manager():
        return SimpleNamespace(get_current_session=lambda: other, get_sessions=lambda: [other, displayed])
    monkeypatch.setattr(media_monitor, 'SessionManager', SimpleNamespace(request_async=manager))
    assert complete(MediaMonitor()._control_session(action, 'displayed-player'))
    assert calls == [action]


def test_closed_displayed_player_does_not_control_another_player(monkeypatch):
    async def manager():
        return SimpleNamespace(get_current_session=lambda: object(), get_sessions=lambda: [])
    monkeypatch.setattr(media_monitor, 'SessionManager', SimpleNamespace(request_async=manager))
    assert not complete(MediaMonitor()._control_session('next_track', 'closed-player'))


def test_clicks_queue_commands_without_sending_foreground_media_keys(monkeypatch):
    monitor = MediaMonitor()
    monitor.info.source_app_id = 'displayed-player'
    monkeypatch.setattr(media_monitor, 'HAS_WINSDK', True)
    monkeypatch.setattr(monitor, 'start', lambda: None)
    monkeypatch.setattr(monitor, '_send_media_key', lambda *args: pytest.fail('Simulated key used'))
    monitor.next_track()
    monitor.previous_track()
    monitor.toggle_play_pause()
    assert [monitor._commands.get_nowait() for _ in range(3)] == [
        ('next_track', 'displayed-player'), ('previous_track', 'displayed-player'),
        ('toggle_play_pause', 'displayed-player')]


def test_legacy_media_key_fallback_only_when_winrt_is_unavailable(monkeypatch):
    monitor = MediaMonitor()
    keys = []
    monkeypatch.setattr(media_monitor, 'HAS_WINSDK', False)
    monkeypatch.setattr(monitor, '_send_media_key', keys.append)
    monitor.toggle_play_pause()
    assert keys == [media_monitor.VK_MEDIA_PLAY_PAUSE]


def test_background_worker_preserves_command_order_and_stops(monkeypatch):
    monitor = MediaMonitor(poll_interval=60)
    calls = []
    done = threading.Event()
    async def poll():
        pass
    async def control(action, source):
        assert threading.current_thread() is not threading.main_thread()
        calls.append(action)
        if len(calls) == 3:
            done.set()
        return True
    monkeypatch.setattr(media_monitor, 'HAS_WINSDK', True)
    monkeypatch.setattr(monitor, '_poll_once', poll)
    monkeypatch.setattr(monitor, '_control_session', control)
    try:
        monitor.next_track()
        monitor.previous_track()
        monitor.toggle_play_pause()
        assert done.wait(3)
        assert calls == ['next_track', 'previous_track', 'toggle_play_pause']
    finally:
        monitor.stop()
    assert monitor._thread is None

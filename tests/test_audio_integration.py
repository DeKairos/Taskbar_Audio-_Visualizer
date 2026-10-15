from types import SimpleNamespace
import numpy as np
from tray_manager import TrayManager
from visualizer_window import VisualizerWindow


def test_repeated_settings_edits_restart_capture(monkeypatch):
    restarts = []
    tray = SimpleNamespace(cfg={'fft_size': 2048}, vis=SimpleNamespace(apply_config=lambda cfg: None),
                           _restart_audio_capture=lambda: restarts.append(True),
                           _save=lambda: None, _build_menu=lambda: None)
    working = {'fft_size': 4096}
    TrayManager._on_settings_changed(tray, working)
    working['fft_size'] = 8192
    TrayManager._on_settings_changed(tray, working)
    assert len(restarts) == 2


def test_sustained_audio_does_not_get_classified_as_silence(monkeypatch):
    import visualizer_window
    clock = [0.0]
    monkeypatch.setattr(visualizer_window.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(visualizer_window.time, 'time', lambda: clock[0])
    vis = SimpleNamespace(cfg={'beat_flash': False}, smoothed=np.zeros(64), peak_caps=np.zeros(64),
                          _last_spectrum_time=0.0, _last_sound_time=0.0, _display_level_ref=1.0)
    for _ in range(100):
        clock[0] += 1024 / 44100
        VisualizerWindow.update_fft(vis, np.ones(64) * 10)
    assert vis._last_sound_time == clock[0]
    assert vis.smoothed.min() > 9


def test_hidden_taskbar_cannot_be_reshown_by_animation():
    hidden = []
    vis = SimpleNamespace(_last_tick_time=0.0, _taskbar_suppressed=True,
                          hide=lambda: hidden.append(True))
    VisualizerWindow._tick(vis)
    assert hidden == [True]


def test_capture_reads_hops_and_emits_analyzed_audio(monkeypatch):
    import audio_capture
    from PyQt6.QtCore import Qt
    from audio_capture import AudioCaptureThread
    reads = []
    class Recorder:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def record(self, numframes):
            reads.append(numframes)
            # Bound the fake recorder even if a regression prevents signal delivery.
            thread._running = False
            return np.ones((numframes, 2)) * 0.2
    def open_recorder(**kwargs):
        assert kwargs['blocksize'] == 512
        return Recorder()
    monkeypatch.setattr(audio_capture.ctypes, 'windll', SimpleNamespace(
        ole32=SimpleNamespace(CoInitializeEx=lambda *args: None, CoUninitialize=lambda: None)))
    thread = AudioCaptureThread({'fft_size': 4096, 'capture_hop': 512})
    monkeypatch.setattr(thread, '_find_loopback_device', lambda: SimpleNamespace(name='test', recorder=open_recorder))
    monkeypatch.setattr(thread, '_current_default_speaker_name', lambda: 'test')
    received = []
    def receive(bars):
        received.append(bars)
        thread._running = False
    # run() is called synchronously here; don't depend on Qt event-loop ordering.
    thread.fft_data_ready.connect(receive, type=Qt.ConnectionType.DirectConnection)
    thread.run()
    assert reads == [512]
    assert received[0].shape == (64,)
    assert np.all(np.isfinite(received[0]))


def test_default_device_switch_reopens_capture(monkeypatch):
    import itertools
    import audio_capture
    from audio_capture import AudioCaptureThread
    from PyQt6.QtCore import Qt

    opened = []
    clock = itertools.count(step=5)
    defaults = iter(['old', 'new', 'new', 'new'])
    thread = AudioCaptureThread({'capture_hop': 1024})

    class Recorder:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def record(self, numframes):
            if len(opened) == 2:
                thread._running = False
            return np.zeros((numframes, 2))

    def device():
        name = 'old' if not opened else 'new'
        def recorder(**kwargs):
            opened.append(name)
            return Recorder()
        if len(opened) >= 2:
            thread._running = False
        return SimpleNamespace(name=name, recorder=recorder)

    monkeypatch.setattr(audio_capture.ctypes, 'windll', SimpleNamespace(
        ole32=SimpleNamespace(CoInitializeEx=lambda *args: None, CoUninitialize=lambda: None)))
    monkeypatch.setattr(audio_capture.time, 'monotonic', lambda: next(clock))
    monkeypatch.setattr(audio_capture.time, 'sleep', lambda duration: None)
    monkeypatch.setattr(thread, '_find_loopback_device', device)
    monkeypatch.setattr(thread, '_current_default_speaker_name', lambda: next(defaults))
    received = []
    thread.fft_data_ready.connect(received.append, type=Qt.ConnectionType.DirectConnection)
    thread.run()
    assert opened == ['old', 'new']
    assert len(received) == 2

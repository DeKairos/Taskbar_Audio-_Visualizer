import ctypes
import warnings
import time
import numpy as np
import soundcard as sc
from PyQt6.QtCore import QThread, pyqtSignal
from core.spectrum import SpectrumAnalyzer

# Suppress the SoundcardRuntimeWarning for data discontinuity (cosmetic warning only)
warnings.filterwarnings("ignore", category=RuntimeWarning)

COINIT_MULTITHREADED = 0x0

class AudioCaptureThread(QThread):
    fft_data_ready = pyqtSignal(np.ndarray)

    def __init__(self, config=None):
        super().__init__()
        self._running = True
        self._config = config or {}

    def _find_loopback_device(self):
        """
        Find the best loopback device.
        This works for speakers AND headphones / external audio devices.
        We match the current default speaker by name, and if that fails,
        we just pick the first available loopback device.
        """
        use_mic = bool(self._config.get("use_microphone", False))

        if use_mic:
            return self._find_microphone_device()

        try:
            default_speaker = sc.default_speaker()
            loopback_mics = sc.all_microphones(include_loopback=True)

            # First pass: match default speaker by name (case-insensitive partial match)
            for mic in loopback_mics:
                if mic.isloopback and default_speaker.name.lower() in mic.name.lower():
                    print(f"[AudioCapture] Using loopback for: {mic.name}")
                    return mic

            # Second pass: just pick any loopback device
            for mic in loopback_mics:
                if mic.isloopback:
                    print(f"[AudioCapture] Fallback loopback device: {mic.name}")
                    return mic

        except Exception as e:
            print(f"[AudioCapture] Error finding loopback device: {e}")

        return None

    def _find_microphone_device(self):
        """Find the default microphone for direct input capture."""
        try:
            default_mic = sc.default_microphone()
            if default_mic:
                print(f"[AudioCapture] Using microphone: {default_mic.name}")
                return default_mic

            # Fallback: find any non-loopback mic
            for mic in sc.all_microphones(include_loopback=True):
                if not mic.isloopback:
                    print(f"[AudioCapture] Fallback microphone: {mic.name}")
                    return mic
        except Exception as e:
            print(f"[AudioCapture] Error finding microphone: {e}")
        return None

    def _current_default_speaker_name(self):
        """Track the selected input/output default for device-change detection."""
        try:
            speaker = (sc.default_microphone() if self._config.get("use_microphone", False)
                       else sc.default_speaker())
            return (speaker.name or "").strip().lower()
        except Exception:
            return ""

    def run(self):
        # Initialize COM for this thread to avoid "Cannot change thread mode" errors
        # from Windows Media Foundation (used internally by soundcard on Windows)
        ctypes.windll.ole32.CoInitializeEx(None, COINIT_MULTITHREADED)

        cfg = self._config
        samplerate = 44100
        hop = int(cfg.get("capture_hop", 1024))

        try:
            while self._running:
                loopback_mic = self._find_loopback_device()
                if loopback_mic is None:
                    print("[AudioCapture] No loopback device found. Retrying...")
                    time.sleep(1.0)
                    continue

                device_name = (getattr(loopback_mic, "name", "") or "").strip()
                print(f"[AudioCapture] Recorder open on: {device_name}")
                default_name_at_open = self._current_default_speaker_name()
                next_device_check = time.monotonic() + 1.0

                try:
                    analyzer = SpectrumAnalyzer(cfg, samplerate)
                    with loopback_mic.recorder(samplerate=samplerate, blocksize=hop) as recorder:
                        while self._running:
                            data = recorder.record(numframes=hop)
                            if data is not None and len(data) > 0:
                                bars = analyzer.push(data)
                                if bars is not None:
                                    self.fft_data_ready.emit(bars)

                            # If the selected default device changed, reopen capture.
                            now = time.monotonic()
                            if now >= next_device_check:
                                next_device_check = now + 1.0
                                current_default = self._current_default_speaker_name()
                                if (
                                    current_default
                                    and default_name_at_open
                                    and current_default != default_name_at_open
                                ):
                                    raise RuntimeError("Default audio device changed")

                except Exception as e:
                    print(f"[AudioCapture] Error during recording: {e}")
                    # Device unplug/restart can throw transient HRESULT failures.
                    # Sleep briefly, then re-detect and reconnect to current default.
                    time.sleep(0.8)
        finally:
            ctypes.windll.ole32.CoUninitialize()

    def stop(self):
        self._running = False
        self.wait()

    def update_config(self, config):
        """Update audio capture config. Some changes require restart."""
        self._config = config or {}


import ctypes
import warnings
import time
import numpy as np
import soundcard as sc
from PyQt6.QtCore import QThread, pyqtSignal

# Suppress the SoundcardRuntimeWarning for data discontinuity (cosmetic warning only)
warnings.filterwarnings("ignore", category=RuntimeWarning)

COINIT_MULTITHREADED = 0x0

class AudioCaptureThread(QThread):
    fft_data_ready = pyqtSignal(np.ndarray)

    def __init__(self):
        super().__init__()
        self._running = True

    def _find_loopback_device(self):
        """
        Find the best loopback device.
        This works for speakers AND headphones / external audio devices.
        We match the current default speaker by name, and if that fails,
        we just pick the first available loopback device.
        """
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

    def _current_default_speaker_name(self):
        """Best-effort default speaker name lookup for device-change detection."""
        try:
            speaker = sc.default_speaker()
            return (speaker.name or "").strip().lower()
        except Exception:
            return ""

    def run(self):
        # Initialize COM for this thread to avoid "Cannot change thread mode" errors
        # from Windows Media Foundation (used internally by soundcard on Windows)
        ctypes.windll.ole32.CoInitializeEx(None, COINIT_MULTITHREADED)

        # Larger block size reduces buffer underruns ("data discontinuity" warnings)
        block_size = 4096
        samplerate = 44100
        num_bars = 64

        # Perceptual frequency mapping: log-spaced buckets spread activity more
        # evenly across the visualizer width than linear FFT bin slicing.
        fft_freqs = np.fft.rfftfreq(block_size, d=1.0 / samplerate)
        min_hz = 40.0
        max_hz = min(16000.0, samplerate * 0.48)
        hz_edges = np.logspace(np.log10(min_hz), np.log10(max_hz), num_bars + 1)
        edge_idx = np.searchsorted(fft_freqs, hz_edges, side="left")
        edge_idx = np.clip(edge_idx, 0, len(fft_freqs) - 1)

        # Ensure each band has at least one source bin.
        for i in range(1, len(edge_idx)):
            if edge_idx[i] <= edge_idx[i - 1]:
                edge_idx[i] = min(edge_idx[i - 1] + 1, len(fft_freqs) - 1)

        # Slight treble compensation so low-end does not dominate the left side.
        eq_curve = np.linspace(1.0, 1.85, num_bars)

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
                    with loopback_mic.recorder(samplerate=samplerate, blocksize=block_size) as recorder:
                        while self._running:
                            data = recorder.record(numframes=block_size)
                            if data is not None and len(data) > 0:
                                # Mix to mono
                                if data.ndim > 1:
                                    mono = data.mean(axis=1)
                                else:
                                    mono = data

                                # Apply a Hann window for clean FFT
                                window = np.hanning(len(mono))
                                mono = mono * window

                                # Compute real FFT
                                fft_data = np.abs(np.fft.rfft(mono))

                                # Convert to dB scale, normalized
                                fft_data = 20 * np.log10(fft_data + 1e-6)
                                fft_data = np.clip(fft_data, 0, None)

                                # Bucket into `num_bars` using log-spaced bands.
                                bars = np.zeros(num_bars, dtype=np.float32)
                                for i in range(num_bars):
                                    start = int(edge_idx[i])
                                    end = int(edge_idx[i + 1])
                                    if end <= start:
                                        end = min(start + 1, len(fft_data))
                                    band = fft_data[start:end]
                                    bars[i] = float(np.mean(band)) if len(band) else 0.0

                                # Rebalance for fuller right-side presence and smooth extremes.
                                bars *= eq_curve
                                bars = np.power(np.maximum(bars, 0.0), 0.96)

                                self.fft_data_ready.emit(bars)

                            # If Windows default output changed, re-open on the new loopback.
                            now = time.monotonic()
                            if now >= next_device_check:
                                next_device_check = now + 1.0
                                current_default = self._current_default_speaker_name()
                                if (
                                    current_default
                                    and default_name_at_open
                                    and current_default != default_name_at_open
                                ):
                                    raise RuntimeError("Default audio output changed")

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


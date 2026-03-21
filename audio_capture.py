import ctypes
import warnings
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

    def run(self):
        # Initialize COM for this thread to avoid "Cannot change thread mode" errors
        # from Windows Media Foundation (used internally by soundcard on Windows)
        ctypes.windll.ole32.CoInitializeEx(None, COINIT_MULTITHREADED)

        loopback_mic = self._find_loopback_device()

        if loopback_mic is None:
            print("[AudioCapture] No loopback device found. Cannot capture audio.")
            return

        # Larger block size reduces buffer underruns ("data discontinuity" warnings)
        block_size = 4096
        samplerate = 44100
        num_bars = 64

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

                        # Bucket into `num_bars` frequency bins
                        freq_bins = len(fft_data)
                        bars = np.array([
                            fft_data[int(i * freq_bins / num_bars):int((i + 1) * freq_bins / num_bars)].mean()
                            for i in range(num_bars)
                        ])

                        self.fft_data_ready.emit(bars)

        except Exception as e:
            print(f"[AudioCapture] Error during recording: {e}")
        finally:
            ctypes.windll.ole32.CoUninitialize()

    def stop(self):
        self._running = False
        self.wait()


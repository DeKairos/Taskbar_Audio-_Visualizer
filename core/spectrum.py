"""Overlapping spectrum analysis, independent of audio devices and Qt."""
import numpy as np


class SpectrumAnalyzer:
    def __init__(self, config, samplerate=44100):
        self.size = int(config.get("fft_size", 2048))
        self.samplerate = samplerate
        self.count = int(config.get("bar_count", 64))
        minimum = float(config.get("freq_min", 40))
        maximum = min(float(config.get("freq_max", 16000)), samplerate * 0.48)
        if config.get("isolate_bass", False):
            maximum = min(maximum, 300.0)
        self.edges = np.geomspace(minimum, maximum, self.count + 1)
        self.centers = np.sqrt(self.edges[:-1] * self.edges[1:])
        self.frequencies = np.fft.rfftfreq(self.size, 1.0 / samplerate)
        self.starts = np.searchsorted(self.frequencies, self.edges[:-1])
        self.ends = np.searchsorted(self.frequencies, self.edges[1:])
        windows = {"hann": np.hanning, "hamming": np.hamming, "blackman": np.blackman}
        self.window = windows.get(config.get("window_function"), np.hanning)(self.size)
        # Keep displayed levels comparable across FFT sizes and window functions.
        self.gain = np.hanning(2048).sum() / self.window.sum()
        self.eq = np.linspace(1.0, 1.85, self.count)
        self._buffer = None

    def push(self, samples):
        samples = np.asarray(samples, dtype=np.float64)
        if samples.ndim == 1:
            samples = samples[:, None]
        if samples.ndim != 2 or not samples.shape[0] or not samples.shape[1]:
            return None
        samples = np.nan_to_num(samples, nan=0.0, posinf=0.0, neginf=0.0)
        if self._buffer is None or self._buffer.shape[1] != samples.shape[1]:
            self._buffer = np.zeros((self.size, samples.shape[1]))
        length = min(len(samples), self.size)
        self._buffer[:-length] = self._buffer[length:]
        self._buffer[-length:] = samples[-length:]
        spectrum = np.fft.rfft(self._buffer * self.window[:, None], axis=0)
        # Combine channel energy after FFT: opposite-phase stereo must not cancel.
        magnitude = np.sqrt(np.mean(np.abs(spectrum) ** 2, axis=1)) * self.gain
        levels = np.maximum(20 * np.log10(magnitude + 1e-6), 0.0)
        lengths = self.ends - self.starts
        # Peak aggregation preserves transients and avoids diluting narrow tones
        # with more empty bins when users increase the FFT resolution.
        bands = np.array([levels[start:end].max() if end > start else 0.0
                          for start, end in zip(self.starts, self.ends)])
        # Several bass bands can fall between the same FFT bins. Interpolate there
        # rather than moving their boundaries into unrelated higher frequencies.
        missing = lengths == 0
        bands[missing] = np.interp(self.centers[missing], self.frequencies, levels)
        return np.power(bands * self.eq, 0.96).astype(np.float32)


def decay_factor(retention, elapsed, reference=2048 / 44100):
    """Express legacy per-update retention as a duration-based decay."""
    return float(retention) ** (max(0.0, elapsed) / reference)

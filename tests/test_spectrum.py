import numpy as np
import pytest
from core.spectrum import SpectrumAnalyzer, decay_factor


def tone(frequency, length, amplitude=0.5):
    return amplitude * np.sin(2 * np.pi * frequency * np.arange(length) / 44100)


def test_silence_is_finite_and_zero():
    analyzer = SpectrumAnalyzer({})
    bars = analyzer.push(np.zeros((1024, 2)))
    assert bars.shape == (64,)
    assert np.all(bars == 0)


def test_opposite_phase_stereo_does_not_cancel():
    samples = tone(1000, 2048)
    mono = SpectrumAnalyzer({}).push(samples)
    stereo = SpectrumAnalyzer({}).push(np.column_stack((samples, -samples)))
    np.testing.assert_allclose(stereo, mono, rtol=1e-6)
    assert stereo.max() > 20


@pytest.mark.parametrize('frequency', [80, 440, 1000, 8000])
def test_peak_tracks_the_requested_frequency(frequency):
    analyzer = SpectrumAnalyzer({'fft_size': 8192})
    bars = analyzer.push(tone(frequency, 8192))
    peak = analyzer.centers[np.argmax(bars)]
    assert abs(np.log2(peak / frequency)) < 0.2


def test_overlapping_chunks_match_a_full_window():
    samples = tone(440, 4096)
    analyzer = SpectrumAnalyzer({'fft_size': 4096})
    for chunk in np.split(samples, 4):
        bars = analyzer.push(chunk)
    expected = SpectrumAnalyzer({'fft_size': 4096}).push(samples)
    np.testing.assert_allclose(bars, expected)


def test_fft_size_does_not_change_display_gain():
    peaks = [SpectrumAnalyzer({'fft_size': size}).push(tone(1000, size)).max()
             for size in (2048, 4096, 8192)]
    assert max(peaks) / min(peaks) < 1.3


def test_bass_only_keeps_bass_across_the_full_display():
    analyzer = SpectrumAnalyzer({'fft_size': 8192, 'isolate_bass': True})
    bars = analyzer.push(tone(250, 8192))
    assert np.argmax(bars) > 40
    assert analyzer.edges[-1] == 300


def test_invalid_samples_and_channel_changes_recover():
    analyzer = SpectrumAnalyzer({})
    assert np.all(np.isfinite(analyzer.push(np.full((1024, 2), np.nan))))
    assert analyzer.push(tone(1000, 2048)).max() > 20
    assert analyzer.push(np.zeros((0, 2))) is None


def test_decay_has_same_result_at_different_update_rates():
    slow = decay_factor(0.86, 1 / 20) ** 20
    fast = decay_factor(0.86, 1 / 80) ** 80
    assert slow == pytest.approx(fast)

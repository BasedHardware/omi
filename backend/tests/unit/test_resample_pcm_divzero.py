"""Regression coverage for malformed sample-rate inputs in listen audio routing."""

from utils.listen_audio import resample_pcm


def test_resample_pcm_zero_source_rate_returns_input_unchanged():
    pcm = b'\x00\x00\x00\x00'
    assert resample_pcm(pcm, 0, 16000) == pcm


def test_resample_pcm_negative_target_rate_returns_input_unchanged():
    pcm = b'\x01\x00\x02\x00'
    assert resample_pcm(pcm, 16000, -1) == pcm


def test_resample_pcm_equal_rates_still_passthrough():
    pcm = b'\x05\x00\x06\x00'
    assert resample_pcm(pcm, 16000, 16000) == pcm

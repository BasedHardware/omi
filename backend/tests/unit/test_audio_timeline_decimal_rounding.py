"""Tests for rounding decimal provider timestamps in ProviderEpochTranslator.

Provider timestamps can sit on 10 ms decimal grids (e.g. 2.01 * 16000 == 32159.999...).
Truncating with int() places the sample one sample early, straddling the preceding send boundary.
Using round() matches the elapsed-send cursor and maps boundary samples accurately.
"""

from utils.audio_timeline import CaptureTimeline, ProviderEpochTranslator

RATE = 16000


def _pcm(count: int) -> bytes:
    return b'\x00\x00' * count


def test_decimal_provider_seconds_round_to_the_nearest_sample():
    """2.01 * 16000 evaluates to 32159.999... and must round to 32160, not truncate to 32159."""
    # Verify the float representation boundary
    assert int(2.01 * RATE) == 32159 and round(2.01 * RATE) == 32160
    assert int(8001 / RATE * RATE) == 8000 and round(8001 / RATE * RATE) == 8001

    timeline = CaptureTimeline(sample_rate=RATE)
    for index in range(200):
        timeline.accept(_pcm(320), arrival_wall=100.0 + (index + 1) * 0.02, arrival_monotonic=(index + 1) * 0.02)
    translator = ProviderEpochTranslator(timeline, RATE)
    translator.note_accepted(0, 64000)

    (segment,) = translator.translate([{'start': 2.01, 'end': 3.01, 'text': 'decimal_test'}])
    assert segment['_capture_start_sample'] == 32160
    assert segment['_capture_end_sample'] == 48160
    assert segment['start'] == timeline.wall(32160)

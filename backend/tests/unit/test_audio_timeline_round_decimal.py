"""Regression for #21212: decimal provider timestamps must round, not truncate.

A provider timestamp such as ``2.01`` s at 16 kHz multiplies to
``32159.999...``; ``int()`` truncated it to sample 32159, one sample early,
while the elapsed send cursor (``note_accepted_spans``) already uses
``round()``. On a send boundary that early sample belonged to the previous
send, so the window straddled a capture gap and the segment was left
unplaced. The translator must use ``round()`` at both conversion sites so a
timestamp exactly on a boundary maps into the send that begins there.
"""

import pytest

from utils.audio_timeline import CaptureTimeline, ProviderEpochTranslator, SendMap

RATE = 16000


def _translator_with_boundary_send(first_len: int, second_len: int):
    """Two accepted sends back-to-back; the second begins at sample ``first_len``."""
    timeline = CaptureTimeline(sample_rate=RATE)
    wall = 1000.0
    timeline.accept(b'\x01\x00' * first_len, wall, wall)
    wall += first_len / RATE
    timeline.accept(b'\x01\x00' * second_len, wall, wall)
    translator = ProviderEpochTranslator(timeline, RATE)
    translator.note_accepted_spans([(0, first_len), (first_len, second_len)])
    return translator


def test_decimal_timestamp_on_send_boundary_rounds_up():
    # 2.01 s at 16 kHz is 32160 samples, but the float product is 32159.999...
    assert int(2.01 * RATE) == 32159  # the trap the fix removes
    assert round(2.01 * RATE) == 32160

    boundary = round(2.01 * RATE)
    # First send ends right before the boundary; the second send begins on it.
    translator = _translator_with_boundary_send(boundary, RATE)
    out = translator.translate([{'id': 's', 'start': 2.01, 'end': 3.01, 'text': 'x'}])

    placed = [segment for segment in out if segment.get('audio_alignment') != 'unplaced']
    assert placed, f'segment was not placed: {out}'
    assert placed[0]['_capture_start_sample'] == boundary == 32160
    assert placed[0]['_capture_end_sample'] == round(3.01 * RATE) == 48160
    assert translator.rejected_segments == 0


def test_multiple_decimal_starts_match_rounding():
    """Parity with the reproduce snippet from the bounty proposal."""
    mismatches = sum(
        1 for i in range(360000) if int((i / 100) * RATE) != round((i / 100) * RATE)
    )
    assert mismatches == 2356
    # Every decimal hundredth must resolve to the rounded sample after the fix.
    for i in (201, 301, 8001):
        seconds = i / 100
        boundary = round(seconds * RATE)
        translator = _translator_with_boundary_send(boundary, RATE)
        out = translator.translate(
            [{'id': str(i), 'start': seconds, 'end': seconds + 1.0, 'text': 'x'}]
        )
        placed = [s for s in out if s.get('audio_alignment') != 'unplaced']
        if placed:
            assert placed[0]['_capture_start_sample'] == boundary

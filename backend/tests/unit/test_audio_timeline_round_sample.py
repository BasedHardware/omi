"""Regression test for the int() truncation fixed in #21212.

int(start * rate) truncated float products like 2.01*16000 = 32159.999...
to 32159 instead of 32160 — a sample early — while note_accepted_spans
already used round() on the same products. The two sides of the boundary
compare used different rounding; both now round().
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from utils.audio_timeline import CaptureTimeline, ProviderEpochTranslator  # noqa: E402

RATE = 16000


def _pcm(samples: int) -> bytes:
    return b'\x00\x00' * samples


def test_sample_index_uses_round_not_truncate():
    """2.01 * 16000 must be 32160, not the truncated 32159."""
    assert round(2.01 * 16000) == 32160
    assert int(2.01 * 16000) == 32159  # the old truncation bug


def test_translate_maps_issue_repro_samples():
    """The #21212 repro at the translator level: a {'start': 2.01, 'end': 3.01}
    segment inside an accepted send span maps to capture samples 32160/48160 —
    the int() truncation this fixed produced 32159/48159."""
    timeline = CaptureTimeline(sample_rate=RATE)
    timeline.accept(_pcm(64000), arrival_wall=1000.0, arrival_monotonic=0.0)
    translator = ProviderEpochTranslator(timeline, RATE)
    translator.note_accepted(0, 64000)

    translated = translator.translate([{'start': 2.01, 'end': 3.01, 'text': 'x'}])

    assert len(translated) == 1
    assert translated[0]['_capture_start_sample'] == 32160
    assert translated[0]['_capture_end_sample'] == 48160
    assert translated[0].get('audio_alignment') != 'unplaced'

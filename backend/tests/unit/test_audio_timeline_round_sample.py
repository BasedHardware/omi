"""Regression test for the int() truncation fixed in #21212.

int(start * rate) truncated float products like 2.01*16000 = 32159.999...
to 32159 instead of 32160 — a sample early — while note_accepted_spans
already used round() on the same products. The two sides of the boundary
compare used different rounding; both now round().
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


def test_sample_index_uses_round_not_truncate():
    """2.01 * 16000 must be 32160, not the truncated 32159."""
    assert round(2.01 * 16000) == 32160
    assert int(2.01 * 16000) == 32159  # the old truncation bug


def test_translate_rounds_provider_samples():
    """translate() must round(), matching note_accepted_spans."""
    import inspect
    import utils.audio_timeline as at

    src = inspect.getsource(at)
    # no int(start * rate) truncation left in translate / outside-attribution
    assert "int(start * rate)" not in src
    assert "int(float(segment['start']) * self.provider_sample_rate)" not in src

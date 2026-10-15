"""Refusal subreasons describe bounded send geometry without changing placement."""

import pytest

from utils.audio_timeline import CaptureTimeline, ProviderEpochTranslator, SendMap
from utils.metrics import AUDIO_TIMELINE_OUTSIDE_SUBREASONS


@pytest.mark.parametrize(
    'shape,first,end',
    [
        ('empty_map', 0, 10),
        ('before_first_send', -10, 5),
        ('after_last_send', 0, 100),
        ('interior_hole', 25, 30),
        ('evicted', 0, 10),
    ],
)
def test_outside_geometry(shape, first, end):
    ledger = SendMap(10, max_spans=1 if shape == 'evicted' else 10)
    if shape != 'empty_map':
        ledger.add_accepted(0, 0, 10)
        ledger.add_accepted(40, 40, 10)
    assert ledger.outside_reason(first, end) == shape
    assert shape in AUDIO_TIMELINE_OUTSIDE_SUBREASONS


def test_subreason_is_additive_and_callback_failure_does_not_change_refusal():
    reasons = []
    epoch = ProviderEpochTranslator(CaptureTimeline(10), 10, project_times=False, on_outside=reasons.append)
    item = {'text': 'Preserved.', 'start': 1, 'end': 2}
    result = epoch.translate([item])
    assert reasons == ['empty_map']
    assert result == [{**item, '_capture_window_reason': 'translator_outside_accepted_sends'}]

    def broken(_):
        raise RuntimeError('local metric failure')

    other = ProviderEpochTranslator(CaptureTimeline(10), 10, project_times=False, on_outside=broken)
    assert other.translate([item]) == result

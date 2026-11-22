"""Future-capture recovery outcomes are counted by label only (SCA-3501 readback)."""

import pytest

from tests.unit.test_sync_receipt_clock_anchor import FUTURE, RECEIVED, anchors, units  # noqa: F401
from utils.sync import receipt_clock


def _value(outcome):
    return receipt_clock.RECOVERY.labels(outcome)._value.get()


def test_anchored_offset_is_counted_once_per_decision(anchors, tmp_path):
    before = _value('anchored')
    assert units(tmp_path / 'one', [FUTURE])
    assert _value('anchored') == before + 1


@pytest.mark.parametrize(
    ('kwargs', 'outcome'),
    [
        ({'uid': ''}, 'identity_required'),
        ({'device_id': None}, 'identity_required'),
    ],
)
def test_retry_is_counted_by_its_code(kwargs, outcome):
    arguments = {
        'uid': 'synthetic',
        'device_id': 'ios_abcd1234',
        'received_at': RECEIVED,
    } | kwargs
    path = f'/tmp/audio_omi_pcm16_16000_u0_clkeone_{int(FUTURE)}.wav'
    before = _value(outcome)
    with pytest.raises(receipt_clock.FutureCaptureRetry):
        receipt_clock.receipt_clock_offsets([(path, FUTURE, 10.0)], **arguments)
    assert _value(outcome) == before + 1


def test_refusal_is_counted():
    before = _value('refused')
    with pytest.raises(receipt_clock.FutureCaptureRefused):
        receipt_clock.receipt_clock_offsets([], uid='synthetic', device_id='ios_abcd1234', received_at=RECEIVED)
    assert _value('refused') == before + 1


def test_counter_failure_never_changes_the_answer(monkeypatch):
    class Broken:
        def labels(self, *_):
            raise RuntimeError('registry unavailable')

    monkeypatch.setattr(receipt_clock, 'RECOVERY', Broken())
    with pytest.raises(receipt_clock.FutureCaptureRefused):
        receipt_clock.receipt_clock_offsets([], uid='synthetic', device_id='ios_abcd1234', received_at=RECEIVED)

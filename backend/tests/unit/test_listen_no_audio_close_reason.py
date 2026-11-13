"""omi_listen_no_audio_close_reason_total: how a no-audio accepted listen session closed, closed labels only."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from utils import metrics
from utils.observability import transcription
from utils.observability import listen_close
from utils.observability.listen_close import no_audio_close_reason
from utils.observability.reasons import ListenNoAudioCloseReason


def _state(initiator=None, code=None):
    return SimpleNamespace(ws_close_initiator=initiator, ws_close_code=code)


@pytest.mark.parametrize(
    ('state', 'expected'),
    [
        (_state('client', 1000), ListenNoAudioCloseReason.CLIENT_CLOSE_NORMAL),
        (_state('client', 1001), ListenNoAudioCloseReason.CLIENT_CLOSE_NORMAL),
        (_state('client', 1005), ListenNoAudioCloseReason.CLIENT_CLOSE_ABNORMAL),
        (_state('client', 1006), ListenNoAudioCloseReason.CLIENT_CLOSE_ABNORMAL),
        (_state('client', 1011), ListenNoAudioCloseReason.CLIENT_CLOSE_ABNORMAL),
        (_state('client', 4001), ListenNoAudioCloseReason.CLIENT_CLOSE_ABNORMAL),
        (_state('client', True), ListenNoAudioCloseReason.CLIENT_CLOSE_ABNORMAL),
        (_state('server', 1001), ListenNoAudioCloseReason.SERVER_CLOSE),
        (_state('server', 1008), ListenNoAudioCloseReason.SERVER_CLOSE),
        (_state(None, 1001), ListenNoAudioCloseReason.NO_CLOSE_FRAME),
        (_state('bogus', 1000), ListenNoAudioCloseReason.UNKNOWN),
        (object(), ListenNoAudioCloseReason.NO_CLOSE_FRAME),
    ],
)
def test_close_reason_buckets_the_observed_close(state, expected):
    assert no_audio_close_reason(state) is expected


def test_close_reason_never_raises_on_a_broken_state():
    class Explodes:
        @property
        def ws_close_initiator(self):
            raise RuntimeError('boom')

    assert no_audio_close_reason(Explodes()) is ListenNoAudioCloseReason.UNKNOWN


def test_recorder_bounds_platform_and_counts_once(monkeypatch):
    counter = MagicMock()
    monkeypatch.setattr(transcription, 'OMI_LISTEN_NO_AUDIO_CLOSE_REASON_TOTAL', counter)

    transcription.record_listen_no_audio_close_reason(
        platform='IOS', close_reason=ListenNoAudioCloseReason.SERVER_CLOSE
    )
    counter.labels.assert_called_once_with(client_platform='ios', close_reason='server_close')

    counter.reset_mock()
    transcription.record_listen_no_audio_close_reason(platform='iphone-x', close_reason='not-a-member')
    counter.labels.assert_called_once_with(client_platform='unknown', close_reason='unknown')


def _samples():
    out = {}
    for family in listen_close.OMI_LISTEN_NO_AUDIO_CLOSE_REASON_TOTAL.collect():
        for sample in family.samples:
            if sample.name.endswith('_total'):
                out.setdefault(sample.labels['client_platform'], set()).add(sample.labels['close_reason'])
    return out


def test_precreated_platforms_mirror_the_bounded_platform_set():
    assert set(_samples()) == set(transcription._PLATFORMS) | {'unknown'}


def test_precreated_close_reasons_cover_every_member():
    expected = {member.value for member in ListenNoAudioCloseReason}
    for platform, reasons in _samples().items():
        assert reasons == expected, platform


def test_existing_no_audio_teardown_labels_are_unchanged():
    assert metrics.OMI_LISTEN_NO_AUDIO_TEARDOWN_TOTAL._labelnames == ('transcription_source', 'client_platform')

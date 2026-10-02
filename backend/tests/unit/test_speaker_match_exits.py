"""Every silent early exit in live speaker-ID matching is now attributable.

The 2026-09-25 incident: after a mid-session STT failover the queued owner
detections returned before any match decision without a single log line, and
the account could only be attributed by replaying the saved conversation. Each
pre-decision return now bumps exactly one bounded ``omi_speaker_id_match_exits_total``
reason and emits one log line carrying the recording session id (never uid),
and the existing evidence/decision lines carry the same session id.
"""

import logging
from collections import deque

import numpy as np
from types import SimpleNamespace

import pytest

import routers.listen.speakers as speakers_module
from routers.listen.speakers import SPEAKER_ID_EXIT_REASONS, SpeakerMatcher
from utils.audio import AudioRingBuffer
from utils.metrics import OMI_SPEAKER_ID_MATCH_EXITS_TOTAL

RATE = 16000


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def _counter(reason: str) -> float:
    return OMI_SPEAKER_ID_MATCH_EXITS_TOTAL.labels(reason=reason)._value.get()


def _host(ring, *, recording_session_id='rec-exits-1'):
    return SimpleNamespace(
        request=SimpleNamespace(uid='uid-exits', sample_rate=RATE),
        state=SimpleNamespace(audio_ring_buffer=ring, speaker_id_enabled=True),
        limits=SimpleNamespace(speaker_id_min_audio=2.0),
        has_speech_profile=False,
        persistence=SimpleNamespace(call=_unexpected_call),
        spawn=_unexpected_spawn,
        emit_speaker_suggestion=lambda *args, **kwargs: None,
        recording_session_id=recording_session_id,
    )


async def _unexpected_call(*args, **kwargs):
    raise AssertionError('persistence must not be reached by a pre-decision exit')


def _unexpected_spawn(coro, *, name):
    coro.close()
    raise AssertionError('no task must be spawned by a pre-decision exit')


def _queued(start: float, end: float, *, speaker=0, conversation=None, duration=None):
    return {
        'id': 'seg-exit',
        'conversation_id': conversation,
        'speaker_id': speaker,
        'abs_start': start,
        'abs_end': end,
        'duration': duration if duration is not None else end - start,
    }


def _ring_with(seconds: float = 1.0, at: float = 100.0) -> AudioRingBuffer:
    ring = AudioRingBuffer(60.0, RATE)
    ring.write(b'\x01\x00' * int(seconds * RATE), at)
    return ring


@pytest.mark.anyio
async def test_exit_reasons_are_enumerated():
    assert SPEAKER_ID_EXIT_REASONS == frozenset(
        {
            'window_outside_buffer',
            'too_short',
            'no_pcm',
            'stale_generation',
            'already_mapped',
            'rejected',
            'manual_decision',
        }
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    'reason,ring,segment',
    [
        ('no_pcm', None, _queued(100.0, 103.0)),
        ('no_pcm', AudioRingBuffer(60.0, RATE), _queued(100.0, 103.0)),
        ('too_short', _ring_with(), _queued(100.0, 103.0, duration=1.0)),
        ('window_outside_buffer', _ring_with(at=100.0), _queued(10.0, 13.0)),
        ('window_outside_buffer', _ring_with(at=100.0), _queued(200.0, 203.0)),
    ],
)
async def test_early_exits_count_and_log_one_bounded_reason(reason, ring, segment, caplog):
    matcher = SpeakerMatcher(_host(ring))
    before = _counter(reason)
    with caplog.at_level(logging.INFO, logger='routers.listen.speakers'):
        await matcher.match(segment['speaker_id'], segment)
    assert _counter(reason) == before + 1
    assert any(
        f'speaker_id_exit reason={reason}' in record.message and 'session=rec-exits-1' in record.message
        for record in caplog.records
    ), [record.message for record in caplog.records]


@pytest.mark.anyio
async def test_queued_detection_from_older_conversation_is_stale(caplog):
    matcher = SpeakerMatcher(_host(_ring_with()))
    before = _counter('stale_generation')
    with caplog.at_level(logging.INFO, logger='routers.listen.speakers'):
        await matcher.match(0, _queued(100.0, 103.0, conversation='conv-old'))
    assert _counter('stale_generation') == before + 1


@pytest.mark.anyio
async def test_already_mapped_speaker_counts_as_its_own_reason(caplog):
    matcher = SpeakerMatcher(_host(_ring_with()))
    matcher.speaker_to_person[0] = ('user', 'The User')
    before = _counter('already_mapped')
    with caplog.at_level(logging.INFO, logger='routers.listen.speakers'):
        await matcher.match(0, _queued(100.0, 103.0))
    assert _counter('already_mapped') == before + 1


@pytest.mark.anyio
async def test_post_embedding_stale_generation_is_counted(monkeypatch, caplog):
    """The re-check after the embedding request returns also names its reason."""
    matcher = SpeakerMatcher(_host(_ring_with(seconds=4.0, at=101.0)))
    matcher.person_embeddings['user'] = {'embedding': None, 'name': 'The User'}

    # The embedding extraction is the last step before the stale re-check;
    # flip the generation inside it, as a concurrent conversation rollover would.
    def flip_generation(wav, name):
        matcher.clear()
        return None  # unused: the stale re-check fires first

    monkeypatch.setattr(speakers_module, 'extract_embedding_from_bytes', flip_generation)
    before = _counter('stale_generation')
    with caplog.at_level(logging.INFO, logger='routers.listen.speakers'):
        await matcher.match(0, _queued(97.5, 103.0))
    assert _counter('stale_generation') == before + 1


@pytest.mark.anyio
@pytest.mark.parametrize('reason', ['rejected', 'manual_decision'])
async def test_receipt_exits_count_and_log_one_bounded_reason(reason, monkeypatch, caplog):
    host = _host(_ring_with(seconds=10.0, at=110.0))
    host.limits.speaker_id_min_audio = 1.0
    matcher = SpeakerMatcher(host)
    matcher._profile_conversation_id = 'conv-receipt'
    embedding = np.array([[1.0, 0.0]])
    matcher.person_embeddings['p1'] = {'embedding': embedding, 'name': 'Person'}
    matcher.speaker_evidence[0] = deque([(embedding, 10.0)])
    decision = (
        {'rejection': {'kind': 'not_a_person', 'person_id': None}, 'generation': 1}
        if reason == 'rejected'
        else {'person_id': 'p1', 'is_user': False, 'generation': 1}
    )

    async def receipt_call(fn, *args, **kwargs):
        assert fn is speakers_module.conversations_db.get_manual_speaker_receipt
        return {'speakers': {'0': decision}}

    host.persistence.call = receipt_call
    monkeypatch.setattr(speakers_module, 'extract_embedding_from_bytes', lambda *args: embedding)
    monkeypatch.setattr(speakers_module, 'compare_embeddings', lambda *args: 0.0)
    before = _counter(reason)
    with caplog.at_level(logging.INFO, logger='routers.listen.speakers'):
        await matcher.match(0, _queued(100.0, 110.0, conversation='conv-receipt'))
    assert _counter(reason) == before + 1
    assert sum(f'speaker_id_exit reason={reason}' in record.message for record in caplog.records) == 1
    assert host.state.speaker_map_dirty
    if reason == 'rejected':
        assert 0 not in matcher.speaker_to_person
    else:
        assert matcher.speaker_to_person[0] == ('p1', 'Person')

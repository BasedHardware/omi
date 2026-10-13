"""Admission attribution observes real matching without weakening its gates."""

import asyncio
import logging
from collections import deque

import numpy as np
import pytest

from routers.listen import speakers, speaker_audio
from tests.unit.test_speaker_match import _live_matcher, _segment
from tests.unit.test_owner_recognition_embedding_budget import _clock
from utils.metrics import OMI_SPEAKER_ID_MATCH_EXITS_TOTAL
from utils.observability.speaker_embedding_budget import BUDGET_EXITS, BUDGET_VOICES, BUDGET_SOCKETS, EMBEDDING_ATTEMPTS


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def _value(counter, **labels):
    return counter.labels(**labels)._value.get()


def _caps(counter):
    return {cap: _value(counter, cap=cap) for cap in ('voice', 'socket', 'both')}


def _attempts():
    return {outcome: _value(EMBEDDING_ATTEMPTS, outcome=outcome) for outcome in ('reserved', 'succeeded', 'failed')}


def _blocked_matcher(monkeypatch, *, attempts=12, tokens=16):
    _clock(monkeypatch)
    matcher, host, _ = _live_matcher(monkeypatch, [])
    host.request.uid = 'test-owner'
    host.session_id = 'socket-test'
    host.recording_session_id = 'recording-test'
    matcher._profile_conversation_id = 'conversation-test'
    matcher._embedding_attempts[1] = attempts
    matcher._socket_embedding_tokens = tokens
    return matcher, host


@pytest.mark.anyio
@pytest.mark.parametrize('cap,attempts,tokens', [('voice', 12, 16), ('socket', 0, 0), ('both', 12, 0)])
async def test_exclusive_cap_equals_legacy_exit_and_first_block_log(monkeypatch, caplog, cap, attempts, tokens):
    matcher, _ = _blocked_matcher(monkeypatch, attempts=attempts, tokens=tokens)
    before = [_caps(counter) for counter in (BUDGET_EXITS, BUDGET_VOICES, BUDGET_SOCKETS)]
    legacy = _value(OMI_SPEAKER_ID_MATCH_EXITS_TOTAL, reason='embedding_budget')
    reservations = _attempts()
    vector = np.array([[1.0, 0.0]])
    matcher.speaker_evidence[1] = deque([(vector, 5.0)])
    with caplog.at_level(logging.INFO, logger=speakers.__name__):
        await matcher.match(1, {**_segment('segment-test', 0, 5), 'speaker_id_scope': 'provider-epoch'})
    for counter, previous in zip((BUDGET_EXITS, BUDGET_VOICES, BUDGET_SOCKETS), before):
        assert _caps(counter) == {key: value + (key == cap) for key, value in previous.items()}
    assert _value(OMI_SPEAKER_ID_MATCH_EXITS_TOTAL, reason='embedding_budget') == legacy + 1
    assert _attempts() == reservations
    messages = [r.message for r in caplog.records if 'speaker_id_budget_first_block' in r.message]
    assert len(messages) == 1
    for field in (
        'uid=test-owner',
        'socket=socket-test',
        'recording=recording-test',
        'conversation=conversation-test',
        'generation=0',
        'speaker=1',
        'scope=provider-epoch',
        f'attempts={attempts}',
        f'tokens={tokens:.3f}',
        'evidence_seconds=5.000',
        'pending_seconds=5.000',
        f'cap={cap}',
    ):
        assert field in messages[0]
    assert not any('speaker_id_exit reason=embedding_budget' in r.message for r in caplog.records)


@pytest.mark.anyio
async def test_repeated_blocks_and_cap_changes_do_not_recount_incidence(monkeypatch, caplog):
    matcher, _ = _blocked_matcher(monkeypatch)
    voices, sockets, exits = _caps(BUDGET_VOICES), _caps(BUDGET_SOCKETS), _caps(BUDGET_EXITS)
    legacy = _value(OMI_SPEAKER_ID_MATCH_EXITS_TOTAL, reason='embedding_budget')
    with caplog.at_level(logging.INFO, logger=speakers.__name__):
        await matcher.match(1, _segment('first', 0, 5))
        await matcher.refresh_for_conversation('conversation-test')
        matcher._socket_embedding_tokens = 0
        for _ in range(3):
            await matcher.match(1, _segment('repeat', 0, 5))
        await matcher.match(2, _segment('other', 0, 5))
    assert _caps(BUDGET_EXITS) == {
        'voice': exits['voice'] + 1,
        'socket': exits['socket'] + 1,
        'both': exits['both'] + 3,
    }
    assert _value(OMI_SPEAKER_ID_MATCH_EXITS_TOTAL, reason='embedding_budget') == legacy + 5
    assert _caps(BUDGET_VOICES) == {
        'voice': voices['voice'] + 1,
        'socket': voices['socket'] + 1,
        'both': voices['both'],
    }
    assert _caps(BUDGET_SOCKETS) == {key: value + (key == 'voice') for key, value in sockets.items()}
    assert len([r for r in caplog.records if 'speaker_id_budget_first_block' in r.message]) == 2


@pytest.mark.anyio
@pytest.mark.parametrize('carried', [False, True])
async def test_generation_incidence_resets_but_socket_and_carried_allowance_do_not(monkeypatch, caplog, carried):
    matcher, host = _blocked_matcher(monkeypatch, tokens=0)
    host.state.speaker_id_enabled = False
    if carried:
        matcher.speaker_to_person[1] = ('user', 'User')
        matcher._mapping_origin[1] = 'manual'
    voices, sockets = sum(_caps(BUDGET_VOICES).values()), sum(_caps(BUDGET_SOCKETS).values())
    with caplog.at_level(logging.INFO, logger=speakers.__name__):
        # Reservation observes the same budget even if an existing manual map
        # normally suppresses the live task before this point.
        assert not matcher._reserve_embedding(1)
        matcher.note_rollover_carry({1} if carried else set())
        await matcher.refresh_for_conversation('conversation-next')
        matcher._admit_voice(1)
        assert not matcher._reserve_embedding(1, segment={'speaker_id_scope': 'next-scope'})
    assert matcher._embedding_attempts[1] == (12 if carried else 0)
    assert matcher._socket_embedding_tokens == 0
    assert sum(_caps(BUDGET_VOICES).values()) == voices + 2
    assert sum(_caps(BUDGET_SOCKETS).values()) == sockets + 1
    logs = [r.message for r in caplog.records if 'speaker_id_budget_first_block' in r.message]
    assert len(logs) == 2 and 'generation=1' in logs[1] and 'scope=next-scope' in logs[1]


@pytest.mark.anyio
async def test_scope_change_does_not_reset_the_same_admitted_voice_budget(monkeypatch, caplog):
    matcher, _ = _blocked_matcher(monkeypatch)
    before = sum(_caps(BUDGET_VOICES).values())
    with caplog.at_level(logging.INFO, logger=speakers.__name__):
        for scope in ('provider-first', 'provider-next'):
            await matcher.match(1, {**_segment('segment', 0, 5), 'speaker_id_scope': scope})
        matcher._embedding_attempts[2] = 12
        await matcher.match(2, {**_segment('new-voice', 0, 5), 'speaker_id_scope': 'provider-next'})
    assert matcher._embedding_attempts[1] == 12
    assert sum(_caps(BUDGET_VOICES).values()) == before + 2
    logs = [r.message for r in caplog.records if 'speaker_id_budget_first_block' in r.message]
    assert len(logs) == 2 and 'scope=provider-first' in logs[0] and 'speaker=2 scope=provider-next' in logs[1]


@pytest.mark.anyio
@pytest.mark.parametrize('outcome', ['succeeded', 'failed', 'encoding_failed', 'cancelled', 'stale'])
async def test_reservations_settle_extraction_only_without_refunds(monkeypatch, outcome):
    _clock(monkeypatch)
    matcher, _, _ = _live_matcher(monkeypatch, [])
    before = _attempts()

    def extract(*args):
        if outcome == 'failed':
            raise RuntimeError('injected extraction failure')
        if outcome == 'stale':
            matcher.clear()
        return np.array([[1.0, 1.0]], dtype=np.float32)  # successful extraction, margin rejection

    monkeypatch.setattr(speakers, 'extract_embedding_from_bytes', extract)
    if outcome == 'encoding_failed':
        monkeypatch.setattr(
            speaker_audio.av, 'open', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('encoding failed'))
        )
    if outcome == 'cancelled':

        async def cancel(*args, **kwargs):
            raise asyncio.CancelledError

        monkeypatch.setattr(speakers, 'run_blocking', cancel)
        with pytest.raises(asyncio.CancelledError):
            await matcher.match(1, _segment('cancelled', 0, 5))
    else:
        await matcher.match(1, _segment('attempt', 0, 5))
    success = outcome in ('succeeded', 'stale')
    assert _attempts() == {
        'reserved': before['reserved'] + 1,
        'succeeded': before['succeeded'] + success,
        'failed': before['failed'] + (not success),
    }
    assert matcher._socket_embedding_tokens == 15
    assert not matcher.speaker_to_person
    if outcome != 'stale':
        assert matcher._embedding_attempts[1] == 1
    if not success:
        assert not matcher._covered_audio[1]


@pytest.mark.anyio
async def test_short_or_unavailable_audio_never_reserves(monkeypatch):
    matcher, host, _ = _live_matcher(monkeypatch, [])
    before = _attempts()
    await matcher.match(1, _segment('short', 0, 0.1))
    host.state.audio_ring_buffer = None
    await matcher.match(2, _segment('no-pcm', 0, 5))
    assert _attempts() == before


@pytest.mark.anyio
async def test_concurrent_failures_still_share_sixteen_tokens_and_exact_exit_sum(monkeypatch):
    _clock(monkeypatch)
    matcher, _, _ = _live_matcher(monkeypatch, [])
    before, caps = _attempts(), _caps(BUDGET_EXITS)
    legacy = _value(OMI_SPEAKER_ID_MATCH_EXITS_TOTAL, reason='embedding_budget')
    calls = []

    def fail(*args):
        calls.append(1)
        raise RuntimeError('injected failure')

    monkeypatch.setattr(speakers, 'extract_embedding_from_bytes', fail)
    await asyncio.gather(*(matcher.match(voice, _segment(f's{voice}', 0, 5)) for voice in range(32)))
    assert len(calls) == 16 and sum(matcher._embedding_attempts.values()) == 16
    assert _attempts() == {
        'reserved': before['reserved'] + 16,
        'succeeded': before['succeeded'],
        'failed': before['failed'] + 16,
    }
    assert sum(_caps(BUDGET_EXITS).values()) - sum(caps.values()) == 16
    assert _value(OMI_SPEAKER_ID_MATCH_EXITS_TOTAL, reason='embedding_budget') == legacy + 16


def test_metric_labels_and_zero_series_have_fixed_cardinality():
    for counter, label, values in (
        (BUDGET_EXITS, 'cap', {'voice', 'socket', 'both'}),
        (BUDGET_VOICES, 'cap', {'voice', 'socket', 'both'}),
        (BUDGET_SOCKETS, 'cap', {'voice', 'socket', 'both'}),
        (EMBEDDING_ATTEMPTS, 'outcome', {'reserved', 'succeeded', 'failed'}),
    ):
        samples = [s for m in counter.collect() for s in m.samples if s.name.endswith('_total')]
        assert len(samples) == 3
        assert {tuple(s.labels) for s in samples} == {(label,)}
        assert {s.labels[label] for s in samples} == values

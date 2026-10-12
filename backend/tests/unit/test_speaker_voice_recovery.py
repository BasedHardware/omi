"""Real PCM provenance, live matching, authority and bounded recovery cost."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import pytest

from routers.listen import speakers
from routers.listen.speaker_audio import select_query_audio
from tests.unit.test_speaker_match import _segment
from tests.unit.test_owner_recognition_diagnostics import live, snapshot
from tests.unit.test_owner_recognition_embedding_budget import _clock
from tests.unit.test_speaker_targeted_fairness import serve
from utils.audio import AudioRingBuffer
from utils.observability.speaker_embedding_budget import RECOVERY_GRANTS, RECOVERY_ACCEPTANCES, RECOVERY_DENIALS
from utils.stt.speaker_recovery import VoiceRecovery, RECOVERY_COOLDOWN_SECONDS


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def _pcm(seconds, value=0):
    return np.full(round(seconds * 16000), value, dtype=np.int16).tobytes()


def _metric(counter, **labels):
    return counter.labels(**labels)._value.get()


NEAR_OWNER = np.array([[0.32, -np.sqrt(1 - 0.32**2)]], dtype=np.float32)
FAR = np.array([[-1.0, 0.0]], dtype=np.float32)


def _setup(monkeypatch, *, failed=False):
    clock = _clock(monkeypatch)
    matcher, host, emitted = live(monkeypatch, [])
    host.state.audio_ring_buffer = AudioRingBuffer(120, 16000)
    calls = []

    def extract(*args):
        calls.append(1)
        if failed:
            raise RuntimeError('injected failure')
        return NEAR_OWNER.copy()

    monkeypatch.setattr(speakers, 'extract_embedding_from_bytes', extract)
    return matcher, host, clock, calls, emitted


async def _exhaust(matcher, host, clock):
    for i in range(12):
        clock.now = i * 2
        host.state.audio_ring_buffer.write_positioned(_pcm(2), i * 2)
        await matcher.match(1, _segment(f'noisy-{i}', i * 2, 2))
    assert matcher._embedding_attempts[1] == 12
    assert not matcher.speaker_to_person


@pytest.mark.anyio
async def test_twelve_near_owner_attempts_then_new_clean_owner_speech_recovers(monkeypatch):
    matcher, host, clock, calls, emitted = _setup(monkeypatch)
    first = _metric(RECOVERY_GRANTS, tranche='first')
    accepted = _metric(RECOVERY_ACCEPTANCES, target='owner')
    await _exhaust(matcher, host, clock)
    clock.now += RECOVERY_COOLDOWN_SECONDS
    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    monkeypatch.setattr(speakers, 'extract_embedding_from_bytes', lambda *a: calls.append(1) or owner)
    host.state.audio_ring_buffer.write_positioned(_pcm(10, 20), 24)
    await matcher.match(1, _segment('clean-long', 24, 10))
    assert matcher._embedding_attempts[1] == 13
    assert len(calls) == 13
    assert matcher.speaker_to_person[1][0] == 'user'
    assert emitted[-1] == (1, 'user', 'User', 'clean-long')
    assert _metric(RECOVERY_GRANTS, tranche='first') == first + 1
    assert _metric(RECOVERY_ACCEPTANCES, target='owner') == accepted + 1
    matcher._publish_decisions(matcher._voice_decisions)
    await matcher.match(1, _segment('mapped-repeat', 34, 2))
    assert _metric(RECOVERY_ACCEPTANCES, target='owner') == accepted + 1
    assert len(calls) == 13


@pytest.mark.anyio
async def test_gapped_new_phrases_win_recovery_over_long_failed_pending_audio(monkeypatch):
    matcher, host, clock, calls, _ = _setup(monkeypatch, failed=True)
    ring = host.state.audio_ring_buffer
    ring.write_positioned(_pcm(60, 1), 0)
    for _ in range(12):
        await matcher.match(1, _segment('old-failed', 0, 60))
    recovery = matcher._voice_recovery[1]
    clock.now = recovery.next_grant_at
    observed = []

    async def extract(pcm):
        observed.append(np.frombuffer(pcm, dtype=np.int16))
        return NEAR_OWNER.copy()

    monkeypatch.setattr(matcher, '_extract_query', extract)
    # Accrue proof across updates, preserving gaps and the selection checkpoint.
    for i in range(5):
        start = 70 + i * 3
        ring.write_positioned(_pcm(2, 20 + i), start)
        await matcher.match(1, _segment(f'phrase-{i}', start, 2))
    assert matcher._embedding_attempts[1] == 13
    assert recovery.tranches == 1
    assert len(observed) == 1
    assert len(observed[0]) == 10 * 16000
    assert set(observed[0]) == {20, 21, 22, 23, 24}
    assert all(np.count_nonzero(observed[0] == value) == 2 * 16000 for value in range(20, 25))
    assert recovery.checkpoint_audio_watermark == 84
    assert recovery.query_audio_watermark == 60
    assert 1 not in matcher._pending_audio  # main clears metadata after success; no self-requeue
    clock.now += 30
    await matcher.match(1, _segment('old-fallback', 0, 60))
    await matcher.match(1, _segment('old-fallback', 0, 60))
    await matcher.match(1, _segment('cannot-recredit-phrases', 70, 14))
    assert matcher._embedding_attempts[1] == 15
    assert recovery.tranches == 1
    assert recovery.fresh_bytes == 0
    assert len(calls) == 12


@pytest.mark.anyio
async def test_uncarried_release_at_fifteen_cannot_admit_sixteen_with_first_grant(monkeypatch):
    matcher, host, clock, calls, _ = _setup(monkeypatch, failed=True)
    await _exhaust(matcher, host, clock)
    matcher._embedding_attempts[1] = 27
    matcher._release_rollover_attempts({1: 12}, set())
    recovery = matcher._voice_recovery[1]
    host.state.audio_ring_buffer.write_positioned(_pcm(10), 24)
    clock.now = recovery.next_grant_at
    before = _metric(RECOVERY_GRANTS, tranche='first')
    await matcher.match(1, _segment('first-grant-cannot-cover-sixteen', 24, 10))
    assert matcher._embedding_attempts[1] == 15
    assert recovery.tranches == 0
    assert recovery.fresh_bytes == 10 * 16000 * 2
    assert _metric(RECOVERY_GRANTS, tranche='first') == before
    assert len(calls) == 12


@pytest.mark.anyio
async def test_evicted_fresh_proof_cannot_checkpoint_an_old_fallback_query(monkeypatch):
    matcher, host, clock, calls, _ = _setup(monkeypatch, failed=True)
    ring = host.state.audio_ring_buffer = AudioRingBuffer(10, 16000)
    ring.write_positioned(_pcm(10, 1), 0)
    matcher._admit_voice(1)
    matcher._embedding_attempts[1] = 12
    recovery = matcher._voice_recovery[1] = VoiceRecovery.checkpoint(ring, 0)
    ring.write_positioned(_pcm(10, 2), 10)
    recovery.observe(ring, [(10, 20)])
    ring.write_positioned(_pcm(10, 1), 0)  # regressed capture evicts the credited PCM
    clock.now = 30
    await matcher.match(1, _segment('old-fallback-cannot-grant', 0, 10))
    assert not calls
    assert recovery.tranches == 0
    assert recovery.checkpoint_audio_watermark == 10
    assert recovery.fresh_bytes == 10 * ring.bytes_per_second
    assert matcher._embedding_attempts[1] == 12


def test_new_audio_below_minimum_falls_back_without_claiming_a_fresh_query():
    ring = AudioRingBuffer(120, 16000)
    ring.write_positioned(_pcm(10, 1), 0)
    ring.write_positioned(_pcm(0.25, 2), 20)
    pcm, selected = select_query_audio(
        ring,
        [(0, 10), (20, 20.25)],
        prefer_recent=True,
        sample_rate=16000,
        capture_watermark=10,
        minimum_seconds=0.5,
    )
    assert selected == [(0, 10)]
    assert set(np.frombuffer(pcm, dtype=np.int16)) == {1}


@pytest.mark.anyio
async def test_failures_spend_both_tranches_and_never_exceed_eighteen(monkeypatch):
    matcher, host, clock, calls, _ = _setup(monkeypatch, failed=True)
    before = {x: _metric(RECOVERY_GRANTS, tranche=x) for x in ('first', 'second')}
    await _exhaust(matcher, host, clock)
    for tranche in range(2):
        clock.now += RECOVERY_COOLDOWN_SECONDS
        start = 24 + tranche * 10
        host.state.audio_ring_buffer.write_positioned(_pcm(10), start)
        for _ in range(5):
            await matcher.match(1, _segment('failed-replay', start, 10))
        assert matcher._embedding_attempts[1] == 15 + tranche * 3
    clock.now += 300
    host.state.audio_ring_buffer.write_positioned(_pcm(20), 44)
    for _ in range(10):
        await matcher.match(1, _segment('third-forbidden', 44, 20))
    assert len(calls) == 18
    assert matcher._embedding_attempts[1] == 18
    assert matcher._voice_recovery[1].tranches == 2
    assert not matcher._covered_audio[1]
    assert {x: _metric(RECOVERY_GRANTS, tranche=x) for x in before} == {x: v + 1 for x, v in before.items()}


@pytest.mark.anyio
@pytest.mark.parametrize('replay', ['duplicate', 'overlap', 'forged', 'rewritten_pcm'])
async def test_repeated_and_forged_audio_cannot_unlock_a_tranche(monkeypatch, replay):
    matcher, host, clock, calls, _ = _setup(monkeypatch, failed=True)
    await _exhaust(matcher, host, clock)
    clock.now += 300
    ring = host.state.audio_ring_buffer
    ring.write_positioned(_pcm(5), 24)
    for i in range(20):
        if replay == 'duplicate':
            segment = _segment('duplicate', 24, 5)
        elif replay == 'overlap':
            segment = _segment('overlap', 24 + i % 2, 5)
        elif replay == 'forged':
            segment = _segment('forged', -1e9, 2e9)
        else:
            ring.write_positioned(_pcm(5), 24)
            segment = _segment('same-capture', 24, 5)
        await matcher.match(1, segment)
    assert len(calls) == 12
    assert matcher._voice_recovery[1].tranches == 0
    assert matcher._voice_recovery[1].fresh_bytes <= 5 * ring.bytes_per_second


def test_checkpoint_excludes_prebuffered_audio_and_timestamp_gaps():
    ring = AudioRingBuffer(120, 16000)
    ring.write_positioned(_pcm(20), 0)
    recovery = VoiceRecovery.checkpoint(ring, 0)
    recovery.observe(ring, [(0, 20)])
    assert not recovery.grant(100)
    ring.write_positioned(_pcm(2), 1e9)
    recovery.observe(ring, [(0, 2e9)])
    assert recovery.fresh_bytes == 2 * ring.bytes_per_second
    assert not recovery.grant(100)


def test_one_observation_deduplicates_overlapping_physical_spans():
    ring = AudioRingBuffer(120, 16000)
    recovery = VoiceRecovery.checkpoint(ring, 0)
    ring.write_positioned(_pcm(5), 0)
    ring.write_positioned(_pcm(5), 0)
    recovery.observe(ring, [(0, 5), (0, 5), (1, 5)])
    assert recovery.fresh_bytes == 5 * ring.bytes_per_second
    assert not recovery.grant(100)


def test_distinct_fragments_reach_ten_seconds_without_counting_their_gap():
    ring = AudioRingBuffer(120, 16000)
    recovery = VoiceRecovery.checkpoint(ring, 0)
    ring.write_positioned(_pcm(6), 10)
    recovery.observe(ring, [(10, 16), (11, 16)])
    assert recovery.fresh_bytes == 6 * ring.bytes_per_second
    assert not recovery.grant(30)
    ring.write_positioned(_pcm(4), 100)
    recovery.observe(ring, [(10, 104)])
    assert recovery.fresh_bytes == 10 * ring.bytes_per_second
    assert recovery.grant(30)


def test_grant_checkpoints_all_current_pcm_not_just_the_observed_window():
    ring = AudioRingBuffer(120, 16000)
    recovery = VoiceRecovery.checkpoint(ring, 0)
    ring.write_positioned(_pcm(20), 0)
    recovery.observe(ring, [(0, 10)])
    assert recovery.grant(30)
    recovery.observe(ring, [(10, 20)])
    assert not recovery.grant(60)
    ring.write_positioned(_pcm(10), 20)
    recovery.observe(ring, [(20, 30)])
    assert recovery.grant(60)


def test_ring_wrap_and_replacement_cannot_reuse_old_proof():
    ring = AudioRingBuffer(10, 16000)
    ring.write_positioned(_pcm(10), 0)
    recovery = VoiceRecovery.checkpoint(ring, 0)
    ring.write_positioned(_pcm(10), 10)
    recovery.observe(ring, [(0, 20)])
    assert recovery.grant(30)
    recovery.observe(ring, [(0, 20)])
    assert not recovery.grant(60)
    replacement = AudioRingBuffer(10, 16000)
    replacement.write_positioned(_pcm(10), 0)
    recovery.observe(replacement, [(0, 10)])
    assert not recovery.grant(60)
    assert recovery.tranches == 1
    replacement.write_positioned(_pcm(10), 10)
    recovery.observe(replacement, [(10, 20)])
    assert not recovery.grant(60)  # old capture positions remain old across ring replacement
    replacement.write_positioned(_pcm(10), 20)
    recovery.observe(replacement, [(20, 30)])
    assert recovery.grant(60)
    assert recovery.tranches == 2


@pytest.mark.anyio
async def test_cooldown_is_monotonic_and_socket_denial_does_not_grant(monkeypatch):
    matcher, host, clock, calls, _ = _setup(monkeypatch, failed=True)
    await _exhaust(matcher, host, clock)
    host.state.audio_ring_buffer.write_positioned(_pcm(10), 24)
    next_grant = matcher._voice_recovery[1].next_grant_at
    for now in (next_grant - 1, -100, next_grant - 1):
        clock.now = now
        await matcher.match(1, _segment('waiting', 24, 10))
        assert len(calls) == 12
    clock.now = next_grant
    matcher._socket_embedding_tokens = 0
    matcher._socket_embedding_refilled_at = clock.now
    await matcher.match(1, _segment('socket-blocked', 24, 10))
    assert matcher._voice_recovery[1].tranches == 0
    assert len(calls) == 12
    clock.now += 15
    await matcher.match(1, _segment('one-token', 24, 10))
    assert len(calls) == 13
    assert matcher._socket_embedding_tokens == pytest.approx(0)


@pytest.mark.anyio
async def test_cancelled_recovery_spends_allowance_without_acceptance(monkeypatch):
    matcher, host, clock, calls, _ = _setup(monkeypatch)
    await _exhaust(matcher, host, clock)
    host.state.audio_ring_buffer.write_positioned(_pcm(10), 24)
    clock.now += 30

    async def cancel(*args, **kwargs):
        raise asyncio.CancelledError

    monkeypatch.setattr(speakers, 'run_blocking', cancel)
    for _ in range(3):
        with pytest.raises(asyncio.CancelledError):
            await matcher.match(1, _segment('cancelled-recovery', 24, 10))
    await matcher.match(1, _segment('spent-tranche', 24, 10))
    assert matcher._embedding_attempts[1] == 15
    assert matcher._voice_recovery[1].tranches == 1
    assert not matcher._voice_recovery[1].has_evidence
    assert len(calls) == 12


@pytest.mark.anyio
async def test_hard_max_is_independent_of_grant_history(monkeypatch):
    matcher, host, clock, calls, _ = _setup(monkeypatch)
    matcher._admit_voice(1)
    matcher._embedding_attempts[1] = 18
    matcher._voice_recovery[1] = VoiceRecovery.checkpoint(host.state.audio_ring_buffer, 0)
    host.state.audio_ring_buffer.write_positioned(_pcm(10), 0)
    clock.now = 30
    await matcher.match(1, _segment('hard-cap', 0, 10))
    assert not calls
    assert matcher._embedding_attempts[1] == 18
    assert matcher._voice_recovery[1].tranches == 0


@pytest.mark.anyio
async def test_named_person_recovery_is_counted_separately(monkeypatch):
    matcher, host, clock, calls, _ = _setup(monkeypatch)
    await _exhaust(matcher, host, clock)
    matcher.speaker_evidence[1].clear()
    clock.now += 30
    host.state.audio_ring_buffer.write_positioned(_pcm(10), 24)
    before = _metric(RECOVERY_ACCEPTANCES, target='person')
    monkeypatch.setattr(speakers, 'extract_embedding_from_bytes', lambda *a: np.array([[0.0, 1.0]], dtype=np.float32))
    await matcher.match(1, _segment('person-recovery', 24, 10))
    assert matcher.speaker_to_person[1][0] == 'p1'
    assert _metric(RECOVERY_ACCEPTANCES, target='person') == before + 1


def test_recovery_prefers_long_recent_clips_and_caps_physical_pcm():
    ring = AudioRingBuffer(120, 16000)
    ring.write_positioned(_pcm(4, 1), 0)
    ring.write_positioned(_pcm(10, 2), 10)
    ring.write_positioned(_pcm(10, 3), 30)
    pcm, selected = select_query_audio(ring, [(0, 4), (10, 20), (30, 40)], prefer_recent=True, sample_rate=16000)
    assert selected == [(30, 40)]
    assert np.frombuffer(pcm, dtype=np.int16).tolist() == [3] * 160000
    ring.write_positioned(_pcm(10, 4), 30)
    pcm, _ = select_query_audio(ring, [(30, 40)], prefer_recent=True, sample_rate=16000)
    assert len(pcm) == 10 * 16000 * 2


@pytest.mark.anyio
@pytest.mark.parametrize('veto', ['manual_rejected', 'manual_positive', 'owner_reserved', 'contended', 'stale'])
async def test_recovery_cannot_bypass_identity_authority_or_stale_generation(monkeypatch, veto):
    matcher, host, clock, calls, _ = _setup(monkeypatch)
    await _exhaust(matcher, host, clock)
    clock.now += 30
    host.state.audio_ring_buffer.write_positioned(_pcm(10), 24)
    matcher.speaker_evidence[1].clear()  # isolate the authority gate from old centroid noise
    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    matcher._profile_conversation_id = 'c'
    host.request.uid = 'u'
    receipt = {}
    if veto == 'manual_rejected':
        receipt = {'speakers': {'1': {'rejection': True}}}
    elif veto == 'manual_positive':
        receipt = {'speakers': {'1': {'is_user': True, 'generation': 1}}}
    elif veto == 'owner_reserved':
        receipt = {'speakers': {'2': {'is_user': True}}}
    host.persistence = SimpleNamespace(call=AsyncMock(return_value=receipt))
    if veto == 'contended':
        matcher._voice_centroids[2] = owner
        matcher.speaker_evidence[2] = type(matcher.speaker_evidence[1])([(owner, 10)], maxlen=3)
        matcher._voice_scopes[2] = ''
        matcher._voice_segments[2] = 'competitor'

    def extract(*args):
        calls.append(1)
        if veto == 'stale':
            matcher.clear()
        return owner

    monkeypatch.setattr(speakers, 'extract_embedding_from_bytes', extract)
    accepted = _metric(RECOVERY_ACCEPTANCES, target='owner')
    await matcher.match(1, _segment('proof-veto', 24, 10))
    assert len(calls) == 13
    if veto == 'manual_positive':
        assert matcher.speaker_to_person[1][0] == 'user'
        assert matcher._mapping_origin[1] == 'manual'
    else:
        assert 1 not in matcher.speaker_to_person
    assert _metric(RECOVERY_ACCEPTANCES, target='owner') == accepted


@pytest.mark.anyio
async def test_actual_scope_change_and_carried_rollover_do_not_renew_tranches(monkeypatch):
    matcher, host, clock, _, _ = _setup(monkeypatch, failed=True)
    await _exhaust(matcher, host, clock)
    clock.now += 30
    host.state.audio_ring_buffer.write_positioned(_pcm(10), 24)
    monkeypatch.setattr(speakers, 'extract_embedding_from_bytes', lambda *a: NEAR_OWNER.copy())
    await matcher.match(1, dict(_segment('scope-next', 24, 10), speaker_id_scope='next'))
    recovery = matcher._voice_recovery[1]
    assert recovery.tranches == 1
    checkpoint = (recovery.checkpoint_audio_watermark, recovery.query_audio_watermark, recovery.next_grant_at)
    assert matcher._voice_scopes[1] == 'next'
    host.state.audio_ring_buffer.write_positioned(_pcm(2), 34)
    await matcher.match(1, dict(_segment('scope-change', 34, 2), speaker_id_scope='another-provider'))
    assert matcher._voice_scopes[1] == 'another-provider'
    assert matcher._voice_recovery[1] is recovery
    assert recovery.tranches == 1
    assert (recovery.checkpoint_audio_watermark, recovery.query_audio_watermark, recovery.next_grant_at) == checkpoint
    assert recovery.fresh_bytes == 2 * 16000 * 2
    assert matcher._embedding_attempts[1] == 14
    matcher._profile_conversation_id = 'first'
    host.state.speaker_id_enabled = False
    await matcher.refresh_for_conversation('first')
    assert matcher._voice_recovery[1] is recovery
    matcher._mapping_origin[1] = 'manual'
    matcher.speaker_to_person[1] = ('user', 'User')
    matcher.note_rollover_carry({1})
    await matcher.refresh_for_conversation('second')
    assert matcher._embedding_attempts[1] == 14
    assert matcher._voice_recovery[1] is recovery
    matcher.note_rollover_carry(set())
    await matcher.refresh_for_conversation('third')
    assert not matcher._voice_recovery
    assert not matcher._embedding_attempts


@pytest.mark.anyio
async def test_concurrent_recovery_and_churn_cannot_escape_socket_bucket(monkeypatch):
    matcher, host, clock, calls, _ = _setup(monkeypatch, failed=True)
    ring = host.state.audio_ring_buffer
    for voice in range(32):
        matcher._admit_voice(voice)
        matcher._embedding_attempts[voice] = 12
        matcher._voice_recovery[voice] = VoiceRecovery.checkpoint(ring, 0)
    ring.write_positioned(_pcm(10), 0)
    clock.now = 30
    await asyncio.gather(*(matcher.match(v, _segment(f'voice-{v}', 0, 10)) for v in range(32)))
    assert len(calls) == 16
    assert sum(r.tranches for r in matcher._voice_recovery.values()) == 16
    tokens = matcher._socket_embedding_tokens
    for _ in range(5):
        matcher.clear()
        await matcher.match(1, _segment('churn', 0, 10))
    assert len(calls) == 16
    assert matcher._socket_embedding_tokens == tokens == 0


def test_recovery_metrics_have_closed_labels_only():
    for counter, label, values in (
        (RECOVERY_GRANTS, 'tranche', {'first', 'second'}),
        (RECOVERY_ACCEPTANCES, 'target', {'owner', 'person'}),
        (RECOVERY_DENIALS, 'reason', {'proven_rejector', 'clearly_far', 'completed_not_near_owner'}),
    ):
        samples = [s for family in counter.collect() for s in family.samples if s.name.endswith('_total')]
        assert len(samples) == len(values)
        assert all(set(s.labels) == {label} for s in samples)
        assert {s.labels[label] for s in samples} == values


@pytest.mark.anyio
@pytest.mark.parametrize('reason', ['proven_rejector', 'clearly_far', 'completed_not_near_owner'])
async def test_real_runner_denies_fresh_tranches_to_decided_non_near_voices(monkeypatch, reason):
    matcher, host, clock, calls, _ = _setup(monkeypatch)

    def extract(*args):
        calls.append(1)
        if reason == 'clearly_far' and len(calls) <= 11:
            raise RuntimeError('initial failure before one completed comparison')
        return np.array([[1.0, 1.0]], dtype=np.float32) if reason == 'completed_not_near_owner' else FAR

    monkeypatch.setattr(speakers, 'extract_embedding_from_bytes', extract)
    await _exhaust(matcher, host, clock)
    assert matcher._rejectors.proven(1) is (reason == 'proven_rejector')
    if reason == 'clearly_far':
        assert matcher._rejectors.comparisons[1] == 1
    recovery = matcher._voice_recovery[1]
    clock.now = recovery.next_grant_at
    host.state.audio_ring_buffer.write_positioned(_pcm(10), 24)
    checkpoint = (recovery.checkpoint_audio_watermark, recovery.query_audio_watermark, recovery.next_grant_at)
    grants = _metric(RECOVERY_GRANTS, tranche='first')
    denied = _metric(RECOVERY_DENIALS, reason=reason)
    tokens = matcher._socket_embedding_tokens
    matcher.queue.put_nowait(dict(_segment('fresh-but-ineligible', 24, 10), speaker_id=1))
    assert await serve(matcher, host, monkeypatch, 1) == [(1, 'fresh-but-ineligible')]
    assert len(calls) == matcher._embedding_attempts[1] == 12
    assert recovery.tranches == 0
    assert recovery.fresh_bytes == 10 * host.state.audio_ring_buffer.bytes_per_second
    assert checkpoint == (recovery.checkpoint_audio_watermark, recovery.query_audio_watermark, recovery.next_grant_at)
    assert _metric(RECOVERY_GRANTS, tranche='first') == grants
    assert _metric(RECOVERY_DENIALS, reason=reason) == denied + 1
    summary = snapshot(matcher)
    assert summary['attempted'] == 12 and summary['owner_comparisons'] > 0
    assert summary['budget_voice'] == summary['reasons']['embedding_budget'] == 1
    matcher.diagnostics.stop('drain', matcher.queue, matcher.tasks)
    frozen = snapshot(matcher)
    assert frozen['stop'] == 'drain' and frozen['pending_queue'] == 0 and frozen['pending_tasks'] == 0
    # Only the unchanged monotonic refill occurred; the denied request spent nothing.
    assert matcher._socket_embedding_tokens == pytest.approx(min(16, tokens + 30 * 240 / 3600))


@pytest.mark.anyio
async def test_new_completed_far_result_cannot_spend_remaining_recovery_attempts(monkeypatch):
    matcher, host, clock, calls, _ = _setup(monkeypatch, failed=True)
    await _exhaust(matcher, host, clock)
    clock.now = matcher._voice_recovery[1].next_grant_at
    host.state.audio_ring_buffer.write_positioned(_pcm(10), 24)
    monkeypatch.setattr(speakers, 'extract_embedding_from_bytes', lambda *args: calls.append(1) or FAR)
    matcher.queue.put_nowait(dict(_segment('undecided-grant', 24, 10), speaker_id=1))
    await serve(matcher, host, monkeypatch, 1)
    recovery = matcher._voice_recovery[1]
    assert recovery.tranches == 1 and matcher._embedding_attempts[1] == 13
    assert matcher._rejectors.comparisons[1] == 1
    denied = _metric(RECOVERY_DENIALS, reason='clearly_far')
    tokens = matcher._socket_embedding_tokens
    host.state.audio_ring_buffer.write_positioned(_pcm(2), 34)
    matcher.queue.put_nowait(dict(_segment('now-clearly-far', 34, 2), speaker_id=1))
    await serve(matcher, host, monkeypatch, 1)
    assert len(calls) == matcher._embedding_attempts[1] == 13
    assert recovery.tranches == 1 and not recovery.accepted
    assert matcher._socket_embedding_tokens == tokens
    assert _metric(RECOVERY_DENIALS, reason='clearly_far') == denied + 1


@pytest.mark.anyio
async def test_profile_recheck_can_make_a_former_rejector_eligible_without_renewing_proof(monkeypatch):
    matcher, host, clock, calls, _ = _setup(monkeypatch)
    monkeypatch.setattr(speakers, 'extract_embedding_from_bytes', lambda *args: calls.append(1) or FAR)
    await _exhaust(matcher, host, clock)
    recovery = matcher._voice_recovery[1]
    clock.now = recovery.next_grant_at
    host.state.audio_ring_buffer.write_positioned(_pcm(10), 24)
    await matcher.match(1, _segment('far-first', 24, 10))
    assert matcher._embedding_attempts[1] == 12 and recovery.tranches == 0
    matcher.person_embeddings['user']['embedding'] = np.array([[-0.32, np.sqrt(1 - 0.32**2)]], dtype=np.float32)
    await matcher._reevaluate_loaded_owner()
    assert not matcher._rejectors.proven(1)
    assert matcher._voice_distances[1]['user'] == pytest.approx(0.68)
    await matcher.match(1, _segment('same-fresh-proof-now-near', 24, 10))
    assert matcher._voice_recovery[1] is recovery
    assert matcher._embedding_attempts[1] == len(calls) == 13
    assert recovery.tranches == 1


@pytest.mark.anyio
async def test_retained_decided_row_is_not_undecided_when_round_history_is_absent(monkeypatch):
    matcher, host, clock, calls, _ = _setup(monkeypatch)
    monkeypatch.setattr(speakers, 'extract_embedding_from_bytes', lambda *args: calls.append(1) or FAR)
    await _exhaust(matcher, host, clock)
    # Carried/manual rows may already have a decision without a current round ledger.
    matcher._rejectors.comparisons.clear()
    assert matcher._voice_decisions[1] is not None and not matcher._rejectors.proven(1)
    recovery = matcher._voice_recovery[1]
    clock.now = recovery.next_grant_at
    host.state.audio_ring_buffer.write_positioned(_pcm(10), 24)
    before = _metric(RECOVERY_DENIALS, reason='clearly_far')
    await matcher.match(1, _segment('decided-row-without-rounds', 24, 10))
    assert len(calls) == matcher._embedding_attempts[1] == 12
    assert recovery.tranches == 0
    assert _metric(RECOVERY_DENIALS, reason='clearly_far') == before + 1

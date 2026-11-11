"""Automatic owner continuity must reach the transcript without manual authority."""

from collections import deque
from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import pytest

from models.transcript_segment import SpeakerIdentityStatus, TranscriptSegment
from database import conversations as conversations_db
from database import live_owner_continuity as continuity_cache
from routers.listen.speakers import SpeakerMatcher
from tests.unit.test_live_speaker_carry import _CarryHarness, _segment, _stamped_epoch, SCOPE
from tests.unit.test_listen_speaker_id_failover import FailoverStack, CONV, UID
from tests.unit.test_speaker_match import _live_matcher, _segment as audio_segment
from utils.observability.owner_recognition import LIVE_SPEAKER_ROLLOVER
from utils.speaker_assignment import process_speaker_assigned_segments
from utils.stt.speaker_match import select_speaker_match
from utils.live_owner_continuity import OwnerContinuity


@pytest.mark.anyio
@pytest.mark.parametrize(
    'restart,rejected,changed_profile,late_rejection,competing_print',
    [
        (False, False, False, False, False),
        (True, False, False, False, False),
        (False, True, False, False, False),
        (False, False, True, False, False),
        (False, False, False, True, False),
        (False, False, False, False, True),
    ],
)
async def test_automatic_owner_rollover_transcript(
    monkeypatch, restart, rejected, changed_profile, late_rejection, competing_print
):
    harness = _CarryHarness(monkeypatch)
    receipt = (
        {'generation': 1, 'speakers': {'0': {'generation': 1, 'rejection': {'kind': 'not_me'}}}} if rejected else {}
    )
    harness.add_previous(receipt, [_segment('old', is_user=True)])
    controller = harness.connect(_stamped_epoch())
    matcher = SpeakerMatcher(controller.host)
    old_call = controller.host.persistence.call

    async def call(fn, *args, **kwargs):
        if fn.__name__ == 'get_manual_speaker_receipt':
            return (harness.rows.get(args[1]) or {}).get('manual_speaker_assignments') or {}
        return await old_call(fn, *args, **kwargs)

    controller.host.persistence.call = call
    controller.host.speakers = matcher
    controller.host.state.speaker_id_enabled = True
    matcher._profile_conversation_id = 'prev-conv'
    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    matcher.person_embeddings = {'user': {'embedding': owner, 'name': 'Owner'}}
    matcher.speaker_to_person = {0: ('user', 'Owner')}
    matcher.voice_identity_status = {0: SpeakerIdentityStatus.user}
    matcher._voice_scopes = {0: SCOPE}
    matcher._voice_distances = {0: {'user': 0.1}}
    matcher._voice_decisions = {0: select_speaker_match({'user': 0.1})}
    matcher._voice_centroids = {0: owner}
    matcher.speaker_evidence = {0: deque([(owner, 5.0)])}
    matcher._covered_audio = {0: [(0.0, 5.0)]}
    matcher._embedding_attempts = {0: 12, 1: 12}
    matcher._socket_embedding_tokens = 0.0

    async def load():
        matcher.person_embeddings = {
            'user': {'embedding': np.array([[0.0, 1.0]]) if changed_profile else owner, 'name': 'Owner'}
        }
        if late_rejection:
            harness.rows['prev-conv']['manual_speaker_assignments'] = {
                'generation': 1,
                'speakers': {'0': {'generation': 1, 'rejection': {'kind': 'not_me'}}},
            }
        if competing_print:
            matcher.person_embeddings['other'] = {'embedding': owner, 'name': 'Other'}

    matcher._load_profiles = AsyncMock(side_effect=load)
    if restart:
        harness.on_scope_swap = lambda: setattr(
            controller.host.receiver, 'speaker_provider_epoch', _stamped_epoch('new')
        )
    automatic = LIVE_SPEAKER_ROLLOVER.labels(carried='automatic', target='owner')
    dropped = LIVE_SPEAKER_ROLLOVER.labels(carried='none', target='owner')
    automatic_before, dropped_before = automatic._value.get(), dropped._value.get()
    await controller.create_new_in_progress_conversation(rollover=True)
    row = harness.rows[harness.pointer]
    incoming = [TranscriptSegment(**_segment('new', start=0.0, end=0.5))]
    process_speaker_assigned_segments(incoming, matcher.segment_assignments, matcher.speaker_to_person)
    assert incoming[0].is_user is (not (restart or rejected or changed_profile or late_rejection or competing_print))
    if incoming[0].is_user:
        assert matcher._covered_audio[0] == [(0.0, 5.0)]
        assert matcher._embedding_attempts[0] == 12
    else:
        assert matcher._embedding_attempts.get(0, 0) == 0
    assert 1 not in matcher._embedding_attempts
    assert matcher._socket_embedding_tokens == 0.0
    assert not row.get('manual_speaker_assignments') or rejected
    assert matcher.segment_assignments == {}
    assert automatic._value.get() == automatic_before + int(incoming[0].is_user)
    assert dropped._value.get() == dropped_before + int(not incoming[0].is_user)


@pytest.mark.anyio
async def test_carry_arbitrates_voice_matched_during_donor_read(monkeypatch):
    from types import SimpleNamespace
    from tests.unit.test_speaker_match import _live_matcher, _segment as audio_segment
    from routers.listen import speakers as mod

    old = np.array([[0.47, np.sqrt(1 - 0.47**2)]], dtype=np.float32)
    new = np.array([[0.46, np.sqrt(1 - 0.46**2)]], dtype=np.float32)
    matcher, host, emitted = _live_matcher(monkeypatch, [new])
    host.emit_speaker_suggestion = lambda *args, **kw: emitted.append(args)
    matcher.person_embeddings.pop('p1')
    owner = matcher.person_embeddings['user']
    matcher._profile_conversation_id = 'old'
    matcher.speaker_to_person[0] = ('user', 'User')
    matcher._mapping_origin[0] = 'automatic'
    matcher._voice_distances[0] = {'user': 0.53}
    matcher._voice_decisions[0] = select_speaker_match({'user': 0.53})
    matcher._voice_centroids[0] = old
    matcher._voice_scopes[0] = SCOPE
    matcher.speaker_evidence[0] = deque([(old, 5.0)], maxlen=3)
    matcher._covered_audio[0] = [(0.0, 5.0)]
    host.state.speaker_id_enabled = True
    host.request.uid = 'u'
    host.receiver = SimpleNamespace(speaker_provider_epoch=SimpleNamespace(current_scope=SCOPE))

    async def load():
        matcher.person_embeddings['user'] = owner

    async def read(fn, *args, **kwargs):
        if fn is continuity_cache.authority_snapshot:
            return {conversation: {} for conversation in args[1]}
        if fn is mod.conversations_db.get_conversation:
            await matcher.match(1, dict(audio_segment('new', 6, 5), speaker_id_scope=SCOPE))
            assert matcher.speaker_to_person[1][0] == 'user'
            return {'id': 'old'}
        return {}

    matcher._load_profiles = AsyncMock(side_effect=load)
    host.persistence = SimpleNamespace(call=read)
    matcher.note_rollover_carry(set())
    await matcher.refresh_for_conversation('next', owner_carry_scope=SCOPE, owner_carry_donor={'id': 'old'})
    incoming = [TranscriptSegment(**_segment(str(v), speaker_id=v)) for v in (0, 1)]
    process_speaker_assigned_segments(incoming, {}, matcher.speaker_to_person)
    assert [s.is_user for s in incoming] == [False, False]
    assert matcher.voice_identity_status[0] == matcher.voice_identity_status[1] == SpeakerIdentityStatus.ambiguous
    assert any(args[0] == 1 and not args[1] for args in emitted), 'withdraw already published owner'


@pytest.mark.anyio
async def test_carry_revalidates_current_prints_and_corrects_emitted_owner(monkeypatch):
    from types import SimpleNamespace
    from tests.unit.test_speaker_match import _live_matcher, _segment as audio_segment
    from routers.listen.transcripts import TranscriptProcessor

    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    old = np.array([[0.47, -np.sqrt(1 - 0.47**2)]], dtype=np.float32)
    other = np.array([[0.6, 0.8]], dtype=np.float32)
    matcher, host, emitted = _live_matcher(monkeypatch, [other])
    matcher.person_embeddings = {'user': {'embedding': owner, 'name': 'Owner'}}
    matcher._profile_conversation_id = 'old'
    matcher.speaker_to_person[0] = ('user', 'Owner')
    matcher._mapping_origin[0] = 'automatic'
    matcher._voice_distances[0] = {'user': 0.53}
    matcher._voice_decisions[0] = select_speaker_match({'user': 0.53})
    matcher._voice_centroids[0] = old
    matcher._voice_scopes[0] = SCOPE
    matcher.speaker_evidence[0] = deque([(old, 5.0)], maxlen=3)
    host.state.speaker_id_enabled = True
    host.request.uid = 'u'
    host.receiver = SimpleNamespace(speaker_provider_epoch=SimpleNamespace(current_scope=SCOPE))
    host.emit_speaker_suggestion = lambda *args, **kw: emitted.append(args)
    processor = object.__new__(TranscriptProcessor)
    processor.host = SimpleNamespace(speakers=matcher)
    incoming = [TranscriptSegment(**_segment(f'new{v}', speaker_id=v)) for v in (0, 1)]

    async def read(fn, *args, **kwargs):
        if fn is continuity_cache.authority_snapshot:
            return {conversation: {} for conversation in args[1]}
        return {'id': 'old'} if fn.__name__ == 'get_conversation' else {}

    async def load():
        matcher.person_embeddings['user'] = {'embedding': owner, 'name': 'Owner'}
        await matcher.match(1, dict(audio_segment('new1', 6, 5), speaker_id_scope=SCOPE))
        process_speaker_assigned_segments(incoming, {}, matcher.speaker_to_person)
        processor._apply_speaker_identity_statuses(incoming)
        assert incoming[1].is_user is True
        # The paid person's print arrives after the early owner-only comparison.
        matcher.person_embeddings['peer'] = {'embedding': other, 'name': 'Other'}

    matcher._load_profiles = AsyncMock(side_effect=load)
    host.persistence = SimpleNamespace(call=read)
    await matcher.refresh_for_conversation('next', owner_carry_scope=SCOPE, owner_carry_donor={'id': 'old'})
    process_speaker_assigned_segments(incoming, {}, matcher.speaker_to_person)
    processor._apply_speaker_identity_statuses(incoming)
    assert [s.model_dump()['is_user'] for s in incoming] == [True, False]
    assert incoming[1].person_id == 'peer'


@pytest.mark.anyio
@pytest.mark.parametrize('remove_map_before_flush', [False, True])
async def test_completed_roster_margin_rejection_withdraws_delivered_and_persisted_owner(
    monkeypatch, remove_map_before_flush
):
    """An owner-only accept must disappear when the paid roster later abstains."""
    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    old = np.array([[0.47, -np.sqrt(1 - 0.47**2)]], dtype=np.float32)
    query = np.array([[0.8, 0.6]], dtype=np.float32)
    peer = np.array([[np.cos(np.deg2rad(70)), np.sin(np.deg2rad(70))]], dtype=np.float32)
    stack = FailoverStack(monkeypatch, v2=False)
    try:
        matcher, host, emitted = _live_matcher(monkeypatch, [query])
        stack.state.audio_ring_buffer = host.state.audio_ring_buffer
        matcher.host = stack.host
        matcher.continuity = OwnerContinuity(matcher)
        stack.host.speakers = matcher
        stack.host.emit_speaker_suggestion = lambda *args, **kw: emitted.append(args)
        stack.host.receiver = SimpleNamespace(speaker_provider_epoch=SimpleNamespace(current_scope=SCOPE))
        matcher.person_embeddings = {'user': {'embedding': owner, 'name': 'Owner'}}
        matcher._profile_conversation_id = 'old'
        matcher.speaker_to_person[0] = ('user', 'Owner')
        matcher._mapping_origin[0] = 'automatic'
        matcher._voice_distances[0] = {'user': 0.53}
        matcher._voice_decisions[0] = select_speaker_match({'user': 0.53})
        matcher._voice_centroids[0] = old
        matcher._voice_scopes[0] = SCOPE
        matcher.speaker_evidence[0] = deque([(old, 5.0)], maxlen=3)
        stack.store.rows[('users', UID, 'conversations', 'old')] = {'id': 'old'}
        segment = TranscriptSegment(**_segment('early-peer', speaker_id=1, start=6, end=11))
        conversations_db.update_conversation_segments(
            UID, CONV, [segment.model_dump()], invalidate_client_processing=False
        )

        async def load():
            matcher.person_embeddings['user'] = {'embedding': owner, 'name': 'Owner'}
            await matcher.match(1, dict(audio_segment(segment.id, 6, 5), speaker_id_scope=SCOPE))
            await stack.processor.flush_speaker_assignments(CONV)
            assert stack.decode_segments()[0]['is_user'] is True
            assert stack.websocket.sent_json[-1][0]['is_user'] is True
            matcher.person_embeddings['peer'] = {'embedding': peer, 'name': 'Peer'}

        matcher._load_profiles = AsyncMock(side_effect=load)
        await matcher.refresh_for_conversation(CONV, owner_carry_scope=SCOPE, owner_carry_donor={'id': 'old'})
        decision = matcher._voice_decisions[1]
        assert decision.person_id is None and not decision.owner_contended
        assert matcher._voice_distances[1]['user'] == pytest.approx(0.2)
        assert matcher._voice_distances[1]['peer'] == pytest.approx(0.162568, abs=1e-6)
        map_removed = 1 not in matcher.speaker_to_person and 1 not in matcher._mapping_origin
        if remove_map_before_flush:
            # Independently reproduce the reviewer's map-removal-alone probe.
            matcher.speaker_to_person.pop(1, None)
            matcher._mapping_origin.pop(1, None)
        await stack.processor.flush_speaker_assignments(CONV)
        saved = stack.decode_segments()[0]
        rendered = stack.websocket.sent_json[-1][0]
        assert (saved['is_user'], rendered['is_user']) == (False, False)
        assert saved.get('person_id') is None and rendered.get('person_id') is None
        assert saved['speaker_identity_status'] == 'no_match'
        assert map_removed, 'ordinary margin rejection must withdraw the automatic map'
        assert any(args[0] == 1 and not args[1] for args in emitted), 'withdraw early suggestion'
    finally:
        stack.restore()


@pytest.mark.anyio
async def test_rollover_keeps_competing_voice_when_paid_roster_becomes_owner_only(monkeypatch):
    """A previously named peer becomes an owner contender on free downgrade."""
    from routers.listen import speakers as mod

    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    winner = np.array([[0.47, -np.sqrt(1 - 0.47**2)]], dtype=np.float32)
    peer = np.array([[0.6, 0.8]], dtype=np.float32)
    matcher, host, _ = _live_matcher(monkeypatch, [np.array([[-1.0, 0.0]], dtype=np.float32)])
    matcher._profile_conversation_id = 'old'
    matcher.person_embeddings = {
        'user': {'embedding': owner, 'name': 'Owner'},
        'peer': {'embedding': peer, 'name': 'Peer'},
    }
    matcher.speaker_to_person = {0: ('user', 'Owner'), 1: ('peer', 'Peer')}
    matcher._mapping_origin = {0: 'automatic', 1: 'automatic'}
    matcher._voice_centroids = {0: winner, 1: peer}
    matcher._voice_distances = {0: {'user': 0.53, 'peer': 1.0}, 1: {'user': 0.4, 'peer': 0.0}}
    matcher._voice_decisions = {v: select_speaker_match(d) for v, d in matcher._voice_distances.items()}
    matcher._voice_scopes = {0: SCOPE, 1: SCOPE}
    matcher.speaker_evidence = {v: deque([(e, 5.0)], maxlen=3) for v, e in matcher._voice_centroids.items()}
    host.request.uid = 'u'
    host.state.speaker_id_enabled = True
    host.receiver = SimpleNamespace(speaker_provider_epoch=SimpleNamespace(current_scope=SCOPE))

    async def load():
        matcher.person_embeddings = {'user': {'embedding': owner, 'name': 'Owner'}}

    async def read(fn, *args, **kwargs):
        if fn is continuity_cache.authority_snapshot:
            return {conversation: {} for conversation in args[1]}
        return {'id': 'old'} if fn is mod.conversations_db.get_conversation else {}

    matcher._load_profiles = AsyncMock(side_effect=load)
    host.persistence = SimpleNamespace(call=read)
    matcher.note_rollover_carry(set())
    await matcher.refresh_for_conversation('next', owner_carry_scope=SCOPE, owner_carry_donor={'id': 'old'})
    assert matcher.speaker_to_person == {}
    assert matcher.voice_identity_status[0] == SpeakerIdentityStatus.ambiguous
    assert matcher._voice_distances[1]['user'] == pytest.approx(0.4)
    assert matcher._voice_decisions[1].person_id is None
    assert 1 in matcher._competition_only
    assert 'peer' not in matcher.person_embeddings
    await matcher.match(2, dict(audio_segment('unrelated', 20, 5), speaker_id_scope=SCOPE))
    assert not matcher.speaker_to_person, 'later arbitration must never promote retained peer evidence'
    assert matcher._voice_decisions[1].person_id is None


@pytest.mark.anyio
@pytest.mark.parametrize(
    'case,reason',
    [
        ('no_scope', 'no_scope'),
        ('no_donor', 'donor_unavailable'),
        ('deleted', 'donor_ineligible'),
        ('old_scope', 'scope_changed'),
        ('no_evidence', 'no_evidence'),
        ('manual', 'manual_override'),
        ('profile_unavailable', 'profile_unavailable'),
        ('profile_changed', 'profile_changed'),
        ('read_failed', 'donor_unavailable'),
        ('late_manual', 'manual_override'),
        ('restart', 'scope_changed'),
        ('voiceprint', 'voiceprint_rejected'),
        ('capacity', 'voice_capacity'),
        ('carry', 'automatic'),
    ],
)
async def test_rollover_logs_bounded_reason_for_each_prior_owner(monkeypatch, caplog, case, reason):
    import logging
    from routers.listen import speakers as mod

    matcher, host, _ = _live_matcher(monkeypatch, [])
    owner = matcher.person_embeddings['user']
    vector = owner['embedding']
    matcher._profile_conversation_id = 'old'
    matcher.speaker_to_person = {0: ('user', 'Owner')}
    matcher._mapping_origin = {0: 'automatic'}
    matcher._voice_decisions = {0: select_speaker_match({'user': 0.0})}
    matcher._voice_centroids = {0: vector}
    matcher.speaker_evidence = {0: deque([(vector, 5.0)], maxlen=3)}
    matcher._voice_scopes = {0: 'obsolete' if case == 'old_scope' else SCOPE}
    scope = None if case == 'no_scope' else SCOPE
    donor = {} if case == 'no_donor' else {'id': 'old'}
    if case == 'deleted':
        donor['deleted'] = True
    manual = {'speakers': {'0': {'rejection': {'kind': 'not_me'}}}}
    if case == 'manual':
        donor['manual_speaker_assignments'] = manual
    if case == 'no_evidence':
        matcher._voice_centroids.clear()
    host.request.uid = 'u'
    host.state.speaker_id_enabled = True
    host.receiver = SimpleNamespace(
        speaker_provider_epoch=SimpleNamespace(current_scope='new' if case == 'restart' else SCOPE)
    )

    async def load():
        if case != 'profile_unavailable':
            matcher.person_embeddings = {'user': owner}
        if case == 'profile_changed':
            matcher.person_embeddings['user'] = {'embedding': np.array([[0.0, 1.0]]), 'name': 'Owner'}
        if case == 'voiceprint':
            matcher.person_embeddings['peer'] = {'embedding': vector, 'name': 'Peer'}

    async def read(fn, *args, **kwargs):
        if case == 'read_failed':
            raise RuntimeError('offline')
        if fn is continuity_cache.authority_snapshot:
            return {
                conversation: (manual if case == 'late_manual' and conversation == 'old' else {})
                for conversation in args[1]
            }
        if fn is mod.conversations_db.get_conversation:
            return dict(donor, manual_speaker_assignments=manual) if case == 'late_manual' else donor
        return {}

    if case == 'capacity':
        monkeypatch.setattr(matcher, '_admit_voice', lambda v: None)
    matcher._load_profiles = AsyncMock(side_effect=load)
    host.persistence = SimpleNamespace(call=read)
    matcher.note_rollover_carry(set())
    with caplog.at_level(logging.INFO, logger='utils.observability.owner_recognition'):
        await matcher.refresh_for_conversation('next', owner_carry_scope=scope, owner_carry_donor=donor)
    observations = [r.message for r in caplog.records if r.message.startswith('live_speaker_rollover')]
    assert len(observations) == 1
    assert f'reason={reason}' in observations[0]
    assert 'target=owner' in observations[0]

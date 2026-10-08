"""Automatic owner continuity must reach the transcript without manual authority."""

from collections import deque
from unittest.mock import AsyncMock

import numpy as np
import pytest

from models.transcript_segment import SpeakerIdentityStatus, TranscriptSegment
from routers.listen.speakers import SpeakerMatcher
from tests.unit.test_live_speaker_carry import _CarryHarness, _segment, _stamped_epoch, SCOPE
from utils.observability.owner_recognition import LIVE_SPEAKER_ROLLOVER
from utils.speaker_assignment import process_speaker_assigned_segments
from utils.stt.speaker_match import select_speaker_match


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

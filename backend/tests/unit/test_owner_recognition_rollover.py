"""Automatic owner continuity must reach the transcript without manual authority."""

from collections import deque
from unittest.mock import AsyncMock

import numpy as np
import pytest

from models.transcript_segment import SpeakerIdentityStatus, TranscriptSegment
from routers.listen.speakers import SpeakerMatcher
from tests.unit.test_live_speaker_carry import _CarryHarness, _segment, _stamped_epoch, SCOPE
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
    await controller.create_new_in_progress_conversation(rollover=True)
    row = harness.rows[harness.pointer]
    incoming = [TranscriptSegment(**_segment('new', start=0.0, end=0.5))]
    process_speaker_assigned_segments(incoming, matcher.segment_assignments, matcher.speaker_to_person)
    assert incoming[0].is_user is (not (restart or rejected or changed_profile or late_rejection or competing_print))
    if incoming[0].is_user:
        assert matcher._covered_audio[0] == [(0.0, 5.0)]
    assert not row.get('manual_speaker_assignments') or rejected
    assert matcher.segment_assignments == {}

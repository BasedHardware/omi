"""Unmatched live voices have lifetime request budgets, including rollovers."""

import asyncio
import numpy as np

from tests.unit.test_speaker_match import _live_matcher, _segment
from routers.listen import speakers
from models.transcript_segment import TranscriptSegment
from tests.unit.test_owner_speaker_profiles import _Persistence
from utils.speaker_assignment import process_speaker_assigned_segments


def test_unmatched_voice_has_twelve_embedding_attempts_per_socket(monkeypatch):
    matcher, _, _ = _live_matcher(monkeypatch, [])
    matcher.person_embeddings.pop('p1')
    calls = []
    monkeypatch.setattr(
        speakers, 'extract_embedding_from_bytes', lambda *a: calls.append(1) or np.array([[0.0, 1.0]], dtype=np.float32)
    )

    async def speech():
        for i in range(120):
            await matcher.match(1, _segment(f's{i}', i * 0.5, 0.5))

    asyncio.run(speech())
    assert 3 < len(calls) <= 12
    assert not matcher.speaker_to_person


def test_rollovers_cannot_reset_socket_embedding_budget(monkeypatch):
    monkeypatch.setattr(speakers, 'MAX_SOCKET_EMBEDDING_ATTEMPTS', 16, raising=False)
    matcher, _, _ = _live_matcher(monkeypatch, [])
    owner = matcher.person_embeddings['user']
    calls = []
    monkeypatch.setattr(
        speakers, 'extract_embedding_from_bytes', lambda *a: calls.append(1) or np.array([[0.0, 1.0]], dtype=np.float32)
    )

    async def speech():
        for i in range(20):
            matcher.clear()
            matcher.person_embeddings['user'] = owner
            await matcher.match(i % 8, _segment(f's{i}', 0, 5))

    asyncio.run(speech())
    assert len(calls) == 16


def test_taught_owner_reuses_evidence_after_voice_budget_is_spent(monkeypatch):

    matcher, host, _ = _live_matcher(monkeypatch, [])
    matcher.person_embeddings.pop('user')
    host.request.uid = 'u'
    host.has_speech_profile = False
    host.persistence = _Persistence()
    calls = []
    monkeypatch.setattr(
        speakers, 'extract_embedding_from_bytes', lambda *a: calls.append(1) or np.array([[1.0, 0.0]], dtype=np.float32)
    )
    monkeypatch.setattr(speakers.user_db, 'get_user_speaker_embedding', lambda uid: [1.0, 0.0])
    monkeypatch.setattr(speakers, 'get_user_name', lambda *a: 'Owner')

    async def speech():
        for i in range(120):
            await matcher.match(1, _segment(f's{i}', i * 0.5, 0.5))
        assert len(calls) == 12
        assert not matcher.speaker_to_person
        await matcher._load_profiles(owner_only=True)

    asyncio.run(speech())
    segments = [
        TranscriptSegment(id='render', speaker_id=1, speaker='SPEAKER_1', text='hello', start=0, end=1, is_user=False)
    ]
    process_speaker_assigned_segments(segments, {}, matcher.speaker_to_person)
    assert segments[0].model_dump()['is_user'] is True
    assert len(calls) == 12

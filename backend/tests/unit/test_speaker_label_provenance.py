"""C1: public ``speaker_label_source`` provenance projection.

One helper decides the public label source: a winning receipt decision is
authoritative (manual, or carried for placeholders); without a receipt the
internal match markers project to ``auto``; unknown legacy identity stays
None. Negative decisions carry no identity and project to None.
"""

from copy import deepcopy
from datetime import datetime, timezone
import os

import pytest

from database import conversations as db
from models.conversation import Conversation
from models.speaker_label_provenance import project_source
from models.structured import Structured
from models.transcript_segment import TranscriptSegment
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.conversations.speaker_resolution import (
    MATCH_SOURCE,
    apply_speaker_resolution,
    resolve_speakers_for_processing,
)
from utils.stt.conversation_speakers import Identity

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

UID = 'uid-provenance'
CONV = 'conv-p'
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _raw(seg_id, speaker_id, **extra):
    segment = {'id': seg_id, 'speaker_id': speaker_id, 'start': 0.0, 'end': 1.0, 'text': 'hi', 'is_user': False}
    segment.update(extra)
    return segment


def test_identity_without_receipt_projects_auto_from_match_marker():
    segment = _raw('s0', 4, person_id='p1', speaker_match_source='live_embedding')
    assert project_source(segment) == 'auto'


def test_unknown_legacy_identity_projects_none():
    assert project_source(_raw('s0', 4, person_id='p1')) is None


def test_absent_identity_projects_none():
    assert project_source(_raw('s0', 4)) is None
    assert project_source(_raw('s0', 4, speaker_label_source='auto')) is None


def test_existing_public_source_survives():
    for source in ('manual', 'auto', 'carried'):
        assert project_source(_raw('s0', 4, person_id='p1', speaker_label_source=source)) == source


def test_winning_receipt_decision_projects_manual():
    segment = _raw('s0', 4)
    decision = {'person_id': 'p1', 'is_user': False}
    assert project_source(segment, decision) == 'manual'


def test_carried_placeholder_decision_projects_carried():
    segment = _raw('s0', 4, person_id='p1')
    decision = {'person_id': 'p1', 'is_user': False, 'source': 'carried'}
    assert project_source(segment, decision) == 'carried'


def test_negative_decision_projects_none():
    segment = _raw('s0', 4, speaker_match_source='live_embedding', speaker_label_source='auto')
    decision = {'rejection': {'kind': 'not_me', 'person_id': None}}
    assert project_source(segment, decision) is None


def test_serializer_projects_the_public_field():
    segment = TranscriptSegment(
        text='hi',
        is_user=False,
        start=0.0,
        end=1.0,
        speaker='SPEAKER_00',
        person_id='p1',
        speaker_match_source='live_embedding',
    )
    assert segment.speaker_label_source == 'auto'
    dumped = segment.model_dump()
    assert dumped['speaker_label_source'] == 'auto'
    cleared = TranscriptSegment(
        text='hi',
        is_user=False,
        start=0.0,
        end=1.0,
        speaker='SPEAKER_00',
        speaker_match_source=None,
        speaker_label_source='auto',
    )
    assert cleared.model_dump()['speaker_label_source'] is None


@pytest.fixture
def store(monkeypatch):
    store = StrictFirestore()
    path = ('users', UID, 'conversations', CONV)
    segments = [
        _raw('s0', 4, person_id='p1', speaker_match_source='live_embedding'),
        _raw('s1', 4, person_id='p1', speaker_match_source='live_embedding'),
    ]
    store.rows[path] = dict(id=CONV, status='completed', transcript_segments=segments)
    store.rows[('users', UID, 'people', 'p1')] = dict(id='p1', name='Sam')
    monkeypatch.setattr(db, 'get_firestore_client', lambda: store)
    return store


def test_read_boundary_overlays_manual_source_on_legacy_segments(store):
    db.assign_conversation_speaker(UID, CONV, person_id='p1', speaker_id=4)
    raw = db._decrypt_conversation_data(deepcopy(store.rows[('users', UID, 'conversations', CONV)]), UID)
    sources = {s['id']: s['speaker_label_source'] for s in raw['transcript_segments']}
    assert sources == {'s0': 'manual', 's1': 'manual'}


def test_resolution_overlay_applies_manual_source_to_in_memory_transcript(store):
    db.assign_conversation_speaker(UID, CONV, person_id='p1', speaker_id=4)
    conversation = Conversation(
        id=CONV,
        created_at=NOW,
        started_at=NOW,
        finished_at=NOW,
        structured=Structured(title='t', overview='o'),
        transcript_segments=[
            {
                'id': 's0',
                'text': 'hi',
                'is_user': False,
                'speaker': 'SPEAKER_00',
                'speaker_id': 4,
                'start': 0.0,
                'end': 1.0,
            },
            {
                'id': 's1',
                'text': 'hi',
                'is_user': False,
                'speaker': 'SPEAKER_00',
                'speaker_id': 4,
                'start': 1.0,
                'end': 2.0,
            },
        ],
    )
    assert resolve_speakers_for_processing(UID, conversation)
    assert all(s.speaker_label_source == 'manual' for s in conversation.transcript_segments)
    assert all(s.model_dump()['speaker_label_source'] == 'manual' for s in conversation.transcript_segments)


def test_resolution_apply_marks_matched_identity_auto():
    conversation = Conversation(
        id='fresh-conv',
        created_at=NOW,
        started_at=NOW,
        finished_at=NOW,
        structured=Structured(title='t', overview='o'),
        transcript_segments=[
            {
                'id': 's0',
                'text': 'hi',
                'is_user': False,
                'speaker': 'SPEAKER_00',
                'speaker_id': 0,
                'start': 0.0,
                'end': 1.0,
            }
        ],
    )
    apply_speaker_resolution(
        conversation,
        {'s0': 4},
        {4: Identity(is_user=False, person_id='p1')},
        {4: 'not_user'},
        owner_voiceprint_available=True,
    )
    segment = conversation.transcript_segments[0]
    assert segment.person_id == 'p1' and segment.speaker_match_source == MATCH_SOURCE
    assert segment.speaker_label_source == 'auto'


def test_merge_does_not_cross_provenance_sources():
    base = dict(text='hi', is_user=False, speaker='SPEAKER_00', start=0.0, end=1.0, speaker_id=4)
    existing = [TranscriptSegment(**{**base, 'person_id': 'p1', 'speaker_label_source': 'auto'})]
    incoming = [TranscriptSegment(**{**base, 'person_id': 'p1', 'speaker_label_source': 'manual'})]
    merged = TranscriptSegment.combine_segments(existing, incoming)
    assert len(merged.segments) == 2
    assert {s.speaker_label_source for s in merged.segments} == {'auto', 'manual'}

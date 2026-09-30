"""Call-tile names from conferencing OCR, pinned to the shared parity vectors.

The vectors in tests/fixtures/meeting_identity/call_tile_vectors.json are the
contract both extractors implement: this Python one and the macOS
OnDeviceMeetingIdentityService. A change to the rule changes the vectors, and
both sides then have to agree again.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from utils.conversations.meeting_context import call_tile_names, context_from_screen_activity

VECTORS_PATH = Path(__file__).resolve().parents[1] / 'fixtures' / 'meeting_identity' / 'call_tile_vectors.json'
VECTORS = json.loads(VECTORS_PATH.read_text(encoding='utf-8'))['vectors']
START = datetime(2026, 9, 30, 17, 0, tzinfo=timezone.utc)
END = datetime(2026, 9, 30, 17, 30, tzinfo=timezone.utc)


@pytest.mark.parametrize('vector', VECTORS, ids=[vector['id'] for vector in VECTORS])
def test_tile_names_match_the_shared_vector(vector):
    names = call_tile_names(vector['rows'], owner_names=vector['owner_names'], owner_emails=vector['owner_emails'])
    assert names == vector['expected_tile_names']


@pytest.mark.parametrize('vector', VECTORS, ids=[vector['id'] for vector in VECTORS])
def test_extractor_participants_match_the_shared_vector(vector):
    context = context_from_screen_activity(
        vector['rows'],
        started_at=START,
        finished_at=END,
        owner_names=vector['owner_names'],
        owner_emails=vector['owner_emails'],
    )
    names = [participant.name for participant in (context.participants if context else []) if participant.name]
    assert names == vector['expected_participant_names']
    assert not set(names) & set(vector['must_exclude'])
    if context is not None:
        assert context.calendar_source == 'screen_activity'


def test_the_incident_vector_is_present():
    # The rule exists for this incident; losing the vector would un-pin it.
    assert any(vector['id'] == 'meet_1on1_bare_tile_repeated' for vector in VECTORS)

"""Every conversation-row producer's output reads back through the write seam, Conversation and the list response.

Synthetic data only; no model calls. A new producer adopts the round trip with one
``assert_conversation_row_round_trips(output)`` line.
"""

import os

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from datetime import datetime, timedelta, timezone  # noqa: E402

import pytest  # noqa: E402

from models.conversation import Conversation, CreateConversation  # noqa: E402
from models.conversation_enums import ConversationSource  # noqa: E402
from models.transcript_segment import TranscriptSegment  # noqa: E402
from tests.unit.fixtures.conversation_round_trip import assert_conversation_row_round_trips  # noqa: E402
from utils.conversations import row_contract  # noqa: E402
from utils.conversations.deterministic_minimum import build_deterministic_minimum_structured  # noqa: E402
from utils.conversations.projection_payload import omit_null_processing_state  # noqa: E402
from utils.conversations.v3 import outline, planner  # noqa: E402
from utils.imports import transcript_files  # noqa: E402

NOW = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)


def _v3_planned_row(people):
    recording = {
        'id': 'r',
        'started_at': NOW,
        'source': 'omi',
        'recording': True,
        'transcript_segments': [{'text': 'hello world', 'start': 0, 'end': 10, 'is_user': True}],
    }
    groups = outline.stretches([recording], NOW + timedelta(hours=1))
    entry = {
        'first_line': 1,
        'title': 'A stable subject',
        'line': 'You made a plan.',
        'kind': 'conversation',
        'emoji': '🛠',
        'people': people,
        'sections': [{'title': 'Plan'}],
    }
    [window] = planner.windows(groups, [[entry]])
    return planner.build('synthetic', window, {'r': recording})


@pytest.mark.parametrize('people', [[], ['Alex', 'Sam']])
def test_v3_planner_rows_round_trip(people):
    conversation = assert_conversation_row_round_trips(_v3_planned_row(people))
    assert [p.name for p in conversation.structured.participants] == people


@pytest.fixture(autouse=True)
def enforced_write_seam(monkeypatch):
    monkeypatch.delenv(row_contract.WRITE_VALIDATION_ENV, raising=False)


def test_v3_planner_row_without_participant_source_is_repaired_and_accepted():
    # The exact 2026-11-17 row shape: the reader model since #25588 folds a missing source, so the seam accepts it.
    row = _v3_planned_row(['Alex'])
    del row['structured']['participants'][0]['source']
    conversation = assert_conversation_row_round_trips(row)
    assert conversation.structured.participants[0].source == 'transcript'


def test_v3_planner_row_with_an_out_of_vocabulary_participant_source_fails_at_the_write_seam():
    # The same class the readers cannot repair: a participant field outside the reader model's vocabulary.
    row = _v3_planned_row(['Alex'])
    row['structured']['participants'][0]['source'] = 'calendar'
    with pytest.raises(row_contract.InvalidConversationRow) as raised:
        assert_conversation_row_round_trips(row)
    assert raised.value.paths == ['structured.participants.0.source:literal_error']


def test_transcript_file_import_rows_round_trip():
    data = b'WEBVTT\n\n00:01.000 --> 00:05.000\n<v Alice Doe>Can we ship?</v> <v Bob Smith>No, wait.</v>\n'
    parsed = transcript_files.parse_transcript_file('standup.vtt', data)
    conversation = transcript_files.build_imported_conversation(
        'synthetic',
        parsed,
        data,
        source=ConversationSource.unknown,
        language_code='en',
        owner_name='Alice Doe',
        people={'bob smith': 'person-bob'},
        fallback_started_at=NOW,
    )
    # The payload the importer persists (utils/imports/transcript_files.py).
    assert_conversation_row_round_trips(omit_null_processing_state(conversation.model_dump()))


def test_sync_intake_deterministic_minimum_rows_round_trip():
    # The intake row legacy sync builds before notes (utils/sync/pipeline.py).
    create = CreateConversation(
        started_at=NOW,
        finished_at=NOW + timedelta(minutes=2),
        source=ConversationSource.omi,
        transcript_segments=[TranscriptSegment(text='We agreed to ship on Monday.', start=0, end=4, is_user=True)],
    )
    row = Conversation(
        id='sync-row',
        created_at=NOW,
        structured=build_deterministic_minimum_structured(create, uid='synthetic'),
        **create.model_dump(),
    ).model_dump()
    row['data_protection_level'] = 'enhanced'
    conversation = assert_conversation_row_round_trips(row)
    assert conversation.structured.title

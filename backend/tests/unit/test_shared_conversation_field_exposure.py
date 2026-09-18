"""The public /v1/conversations/{id}/shared endpoint is an explicit allowlist.

The endpoint returns a conversation to anyone with the link (no auth). Exposure
is a deliberate choice: the response model does not inherit Conversation, does
not extra='allow', and projects only the fields the share page (and documented
compat consumers) actually need. Owner-internal fields — geolocation, encryption
tier, merge provenance, device ids, calendar attendee emails, speech samples —
must not appear, including when a new arbitrary key lands on the stored document.
"""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi import HTTPException

import routers.conversations as conv_router
from models.conversation import (
    CalendarEventLink,
    Conversation,
    SharedConversationResponse,
    SharedPerson,
    project_shared_conversation,
)
from models.conversation_enums import ConversationSource, ConversationStatus, ConversationVisibility
from models.geolocation import Geolocation
from models.other import Person
from models.structured import ActionItem, Event, Section, Structured
from models.transcript_segment import TranscriptSegment

ALLOWLIST_TOP_LEVEL = frozenset(SharedConversationResponse.model_fields)
LEAKING_FIELDS = frozenset(
    {
        'geolocation',
        'data_protection_level',
        'external_data',
        'client_device_id',
        'client_platform',
        'folder_id',
        'call_id',
        'calendar_event',
        'processing_memory_id',
        'processing_conversation_id',
        'meeting_treatment_eligible',
        'meeting_treatment_reason',
        'meeting_duration_s',
        'meeting_dedup_speech_s',
        'transcript_segments_compressed',
        'suggested_summarization_apps',
        'screenshot_sharing_enabled',
        'private_cloud_sync_enabled',
        'audio_files',
        'conversation_audio',
        'photos',
        'starred',
        'discarded',
        'deferred',
        'is_locked',
        'uses_custom_stt',
        'updated_at',
        'app_id',
        'imported',
    }
)
CREATED_AT = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)


def _conversation(**overrides) -> Conversation:
    payload = dict(
        id='c1',
        created_at=CREATED_AT,
        started_at=CREATED_AT,
        finished_at=CREATED_AT,
        language='en',
        source=ConversationSource.omi,
        status=ConversationStatus.completed,
        visibility=ConversationVisibility.shared,
        structured=Structured(
            title='Shared notes',
            overview='A public summary.',
            emoji='📝',
            action_items=[
                ActionItem(
                    description='Send the deck',
                    completed=False,
                    conversation_id='c1',
                    owner_name='Ada',
                    due_at=CREATED_AT,
                )
            ],
            events=[
                Event(
                    title='Follow-up',
                    description='Team sync',
                    start=CREATED_AT,
                    duration=30,
                    created=False,
                )
            ],
            sections=[Section(heading='Secret section', body_markdown='internal', source_segment_ids=['s1'])],
        ),
        transcript_segments=[
            TranscriptSegment(
                id='seg-1',
                text='Hello from the owner.',
                speaker='SPEAKER_00',
                speaker_id=0,
                is_user=True,
                person_id=None,
                start=0.0,
                end=1.5,
                stt_provider='deepgram',
            ),
            TranscriptSegment(
                id='seg-2',
                text='Hi from Ada.',
                speaker='SPEAKER_01',
                speaker_id=1,
                is_user=False,
                person_id='person-ada',
                start=1.5,
                end=3.0,
                stt_provider='deepgram',
            ),
        ],
        geolocation=Geolocation(latitude=37.77, longitude=-122.42),
        data_protection_level='enhanced',
        external_data={'merge_metadata': {'source_ids': ['other-conv']}},
        client_device_id='device-secret',
        client_platform='macos',
        folder_id='folder-secret',
        call_id='call-secret',
        calendar_event=CalendarEventLink(
            event_id='evt-1',
            title='Private meeting',
            attendees=['Ada Lovelace'],
            attendee_emails=['ada@example.com'],
            start_time=CREATED_AT,
            end_time=CREATED_AT,
        ),
        processing_conversation_id='proc-secret',
        meeting_treatment_eligible=True,
        meeting_treatment_reason='calendar_overlap',
        meeting_duration_s=3600.0,
        meeting_dedup_speech_s=1200.0,
        transcript_segments_compressed=True,
        suggested_summarization_apps=['app-secret'],
        screenshot_sharing_enabled=True,
        private_cloud_sync_enabled=True,
        apps_results=[{'app_id': 'summarizer', 'content': 'A public app result.'}],
    )
    payload.update(overrides)
    return Conversation(**payload)


def _call_shared(conversation: Conversation, people_data=None):
    with patch.object(conv_router.redis_db, 'get_conversation_uid', return_value='owner-uid'), patch.object(
        conv_router, '_get_valid_conversation_by_id', return_value={'visibility': 'shared'}
    ), patch.object(conv_router, 'deserialize_conversation', return_value=conversation), patch.object(
        conv_router.users_db, 'get_people_by_ids', return_value=people_data or []
    ):
        return conv_router.get_shared_conversation_by_id('c1')


def _payload(response: SharedConversationResponse) -> dict:
    return response.model_dump(mode='json')


def test_shared_response_top_level_keys_equal_allowlist():
    payload = _payload(_call_shared(_conversation()))
    assert set(payload) == ALLOWLIST_TOP_LEVEL


def test_previously_leaking_fields_are_absent():
    payload = _payload(_call_shared(_conversation()))
    assert LEAKING_FIELDS.isdisjoint(payload)
    assert 'geolocation' not in payload
    assert 'data_protection_level' not in payload
    assert 'external_data' not in payload
    assert 'calendar_event' not in payload
    assert 'client_device_id' not in payload


def test_new_arbitrary_field_on_stored_document_does_not_appear():
    leaky = _conversation().model_dump()
    leaky['owner_secret'] = 'should-never-leave-the-owner-doc'
    leaky['brand_new_conversation_field'] = {'nested': True}
    leaky['people'] = [{'id': 'p1', 'name': 'Ada', 'speech_samples': ['gs://secret'], 'email': 'ada@example.com'}]
    projected = SharedConversationResponse.model_validate(leaky)
    payload = projected.model_dump(mode='json')
    assert 'owner_secret' not in payload
    assert 'brand_new_conversation_field' not in payload
    assert set(payload) == ALLOWLIST_TOP_LEVEL
    assert payload['people'] == [{'id': 'p1', 'name': 'Ada'}]


def test_people_projection_is_id_and_name_only():
    people = [
        {
            'id': 'person-ada',
            'name': 'Ada',
            'speech_samples': ['gs://bucket/sample.wav'],
            'speech_sample_transcripts': ['hello'],
            'created_at': CREATED_AT.isoformat(),
            'updated_at': CREATED_AT.isoformat(),
        }
    ]
    payload = _payload(_call_shared(_conversation(), people_data=people))
    assert payload['people'] == [{'id': 'person-ada', 'name': 'Ada'}]
    assert set(payload['people'][0]) == set(SharedPerson.model_fields)


def test_structured_and_transcript_drop_internal_nested_fields():
    payload = _payload(_call_shared(_conversation()))
    structured = payload['structured']
    assert set(structured) == {'title', 'overview', 'emoji', 'category', 'action_items', 'events'}
    assert 'sections' not in structured
    assert structured['action_items'] == [{'description': 'Send the deck', 'completed': False}]
    assert 'conversation_id' not in structured['action_items'][0]
    assert 'owner_name' not in structured['action_items'][0]
    segment = payload['transcript_segments'][1]
    assert set(segment) == {'id', 'text', 'speaker', 'speaker_id', 'is_user', 'person_id', 'start', 'end'}
    assert 'stt_provider' not in segment
    assert 'translations' not in segment
    assert 'speaker_identity_status' not in segment


def test_private_conversation_still_404s():
    with patch.object(conv_router.redis_db, 'get_conversation_uid', return_value='owner-uid'), patch.object(
        conv_router, '_get_valid_conversation_by_id', return_value={'visibility': 'private'}
    ):
        with pytest.raises(HTTPException) as exc:
            conv_router.get_shared_conversation_by_id('c1')
    assert exc.value.status_code == 404


def test_missing_share_link_still_404s():
    with patch.object(conv_router.redis_db, 'get_conversation_uid', return_value=None):
        with pytest.raises(HTTPException) as exc:
            conv_router.get_shared_conversation_by_id('c1')
    assert exc.value.status_code == 404


def test_from_conversation_keeps_share_page_fields():
    response = project_shared_conversation(
        _conversation(),
        [Person(id='person-ada', name='Ada', speech_samples=['gs://secret'])],
    )
    payload = response.model_dump(mode='json')
    assert payload['id'] == 'c1'
    assert payload['structured']['title'] == 'Shared notes'
    assert payload['structured']['overview'] == 'A public summary.'
    assert payload['apps_results'] == [{'app_id': 'summarizer', 'content': 'A public app result.'}]
    assert payload['people'][0] == {'id': 'person-ada', 'name': 'Ada'}
    assert payload['visibility'] == ConversationVisibility.shared
    assert payload['language'] == 'en'

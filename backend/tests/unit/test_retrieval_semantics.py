from datetime import datetime, timezone, timedelta

import pytest
from pydantic import ValidationError

from database import mem_db, redis_db
from models.calendar_mutation import CalendarMutationResult, format_deleted_calendar_events
from models.conversation_metadata import ConversationMetadata, ConversationMetadataKeys, metadata_list
from models.daily_summary_payload import DailySummaryPayload
from utils.conversations.datetime_utils import coerce_utc_datetime
from utils.log_sanitizer import sanitize_validation_error


def test_conversation_metadata_uses_single_vector_schema_and_entities_field():
    metadata = ConversationMetadata(
        people=['alice'],
        topics=['vector search'],
        entities=['pinecone'],
        dates=['2026-06-25'],
    ).to_vector_metadata()

    assert metadata == {
        ConversationMetadataKeys.PEOPLE: ['alice'],
        ConversationMetadataKeys.TOPICS: ['vector search'],
        ConversationMetadataKeys.ENTITIES: ['pinecone'],
        ConversationMetadataKeys.DATES: ['2026-06-25'],
    }
    assert 'people_mentioned' not in metadata
    assert metadata[ConversationMetadataKeys.ENTITIES] != metadata[ConversationMetadataKeys.TOPICS]


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        (['alice'], ['alice']),
        (('alice', 'bob'), ['alice', 'bob']),
        ('alice', []),
        (None, []),
    ],
)
def test_metadata_list_only_returns_list_like_values(raw, expected):
    assert metadata_list({'people': raw}, ConversationMetadataKeys.PEOPLE) == expected


def test_calendar_delete_result_reports_only_successful_events_as_deleted():
    result = CalendarMutationResult(
        succeeded=[
            {
                'summary': 'Design review',
                'start': {'dateTime': '2026-06-25T16:30:00Z'},
            }
        ],
        failed=[('Dentist', 'permission denied')],
    )

    message = format_deleted_calendar_events(result)

    assert 'Successfully deleted 1 calendar event(s)' in message
    assert 'Design review (2026-06-25 16:30)' in message
    assert 'Failed to delete 1 event(s)' in message
    assert 'Dentist: permission denied' in message
    assert 'Successfully deleted 2' not in message


def test_calendar_delete_result_with_only_failures_is_not_success_message():
    message = format_deleted_calendar_events(CalendarMutationResult(failed=[('Dentist', 'not found')]))

    assert message == 'Error: Failed to delete events: Dentist: not found'


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        ('2026-06-25T12:00:00Z', datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc)),
        (
            '2026-06-25T08:00:00-04:00',
            datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc),
        ),
        (
            datetime(2026, 6, 25, 8, 0, tzinfo=timezone(timedelta(hours=-4))),
            datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc),
        ),
        (datetime(2026, 6, 25, 12, 0), datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc)),
    ],
)
def test_coerce_utc_datetime_normalizes_supported_timestamps(value, expected):
    assert coerce_utc_datetime(value) == expected


@pytest.mark.parametrize('value', [None, 'not-a-date', object()])
def test_coerce_utc_datetime_returns_none_for_missing_or_malformed_values(value):
    assert coerce_utc_datetime(value) is None


def test_daily_summary_payload_rejects_malformed_section_shape():
    with pytest.raises(ValidationError):
        DailySummaryPayload.model_validate({'headline': 'Today', 'highlights': ['not an object']})
    with pytest.raises(ValidationError):
        DailySummaryPayload.model_validate(
            {'headline': 'Today', 'highlights': [{'topic_name': 'wrong key', 'summary': 'Summary'}]}
        )


def test_daily_summary_payload_allows_omitted_optional_sections():
    payload = DailySummaryPayload.model_validate({'headline': 'Today'})

    assert payload.headline == 'Today'
    assert payload.highlights == []
    assert payload.unresolved_questions == []


def test_daily_summary_validation_log_summary_omits_private_input_value():
    private_summary_text = "Private therapy conversation about Alice and Bob"
    try:
        DailySummaryPayload.model_validate(
            {
                "headline": "Today",
                "highlights": [
                    {
                        "topic": "Personal",
                        "summary": private_summary_text,
                        "conversation_numbers": "not-a-list",
                    }
                ],
            }
        )
    except ValidationError as exc:
        safe_summary = sanitize_validation_error(exc)
    else:
        raise AssertionError("expected malformed daily summary payload to fail validation")

    assert private_summary_text not in safe_summary
    assert "input_value" not in safe_summary
    assert "conversation_numbers" in safe_summary


def test_proactive_notification_cache_setters_require_keyword_app_id():
    bad_args = ('uid', object(), 123)
    with pytest.raises(TypeError):
        mem_db.set_proactive_noti_sent_at(*bad_args)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        redis_db.set_proactive_noti_sent_at(*bad_args)  # type: ignore[call-arg]

    mem_db.set_proactive_noti_sent_at('uid', app_id='app', ts=123, ttl=1)
    assert mem_db.get_proactive_noti_sent_at('uid', 'app') == 123

"""Storing a resolved meeting context must never fail the conversation.

Regression cover for Cloud Error Reporting group ``CMma2pfi_ePzeg``: an
external-integration conversation whose window overlapped a stored calendar
meeting reached ``store_meeting_context``, which unconditionally assigned
``conversation.external_data``. ``ExternalIntegrationCreateConversation`` has no
such field, so pydantic raised ``ValueError`` out of ``process_conversation`` and
the conversation never completed.

The contract these tests pin:

* every conversation model that reaches ``process_conversation`` can carry a
  resolved context, and storing one never raises;
* the ``Conversation`` path (``external_data['calendar_meeting_context']``) and
  the ``CreateConversation`` path (``calendar_meeting_context``) are unchanged;
* the external-integration create model carries it as a field, the same way
  ``CreateConversation`` does, and the persisted ``Conversation`` carries it in
  ``external_data`` — the shape every reader already understands.

Fixtures are synthetic stored shapes: no production data, no user content.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from models.calendar_context import CalendarMeetingContext, MeetingParticipant
from models.conversation import Conversation, CreateConversation, ExternalIntegrationCreateConversation
from models.conversation_enums import ConversationSource, ExternalIntegrationConversationSource
from models.structured import Structured
from utils.conversations.meeting_context import store_meeting_context, stored_meeting_context

START = datetime(2026, 11, 18, 9, 0, tzinfo=timezone.utc)
END = datetime(2026, 11, 18, 9, 30, tzinfo=timezone.utc)


def _context() -> CalendarMeetingContext:
    return CalendarMeetingContext(
        calendar_event_id='evt-synthetic',
        title='Synthetic planning sync',
        start_time=START,
        duration_minutes=30,
        calendar_source='system_calendar',
        participants=[MeetingParticipant(name='Synthetic Participant')],
    )


def _external_integration_conversation() -> ExternalIntegrationCreateConversation:
    return ExternalIntegrationCreateConversation(
        text='Synthetic integration transcript.',
        text_source=ExternalIntegrationConversationSource.audio,
        started_at=START,
        finished_at=END,
        source=ConversationSource.external_integration,
    )


def _persisted_conversation() -> Conversation:
    return Conversation(
        id='synthetic-conversation',
        created_at=START,
        started_at=START,
        finished_at=END,
        structured=Structured(),
        source=ConversationSource.desktop,
        external_data={'conversation_role': 'meeting'},
    )


class TestExternalIntegrationCreateConversation:
    def test_storing_a_context_does_not_raise_and_sets_the_field(self):
        conversation = _external_integration_conversation()
        context = _context()

        store_meeting_context(conversation, context)

        assert conversation.calendar_meeting_context == context
        assert stored_meeting_context(conversation) == context

    def test_client_supplied_context_is_discarded(self):
        """Only the server resolver may attach a context, so the set of
        conversations that get one cannot change through the request body."""
        conversation = ExternalIntegrationCreateConversation(
            text='Synthetic integration transcript.',
            calendar_meeting_context=_context(),
        )

        assert conversation.calendar_meeting_context is None

    def test_the_field_is_not_part_of_the_public_request_schema(self):
        schema = ExternalIntegrationCreateConversation.model_json_schema()

        assert 'calendar_meeting_context' not in schema['properties']


class TestUnchangedPaths:
    def test_create_conversation_still_carries_the_context_as_a_field(self):
        conversation = CreateConversation(
            started_at=START,
            finished_at=END,
            transcript_segments=[],
        )
        context = _context()

        store_meeting_context(conversation, context)

        assert conversation.calendar_meeting_context == context
        assert stored_meeting_context(conversation) == context

    def test_conversation_still_carries_the_context_in_external_data(self):
        conversation = _persisted_conversation()
        context = _context()

        store_meeting_context(conversation, context)

        raw = conversation.external_data['calendar_meeting_context']
        assert isinstance(raw, dict), 'the persisted shape must stay a JSON mapping'
        assert raw['calendar_event_id'] == 'evt-synthetic'
        assert conversation.external_data['conversation_role'] == 'meeting'
        assert stored_meeting_context(conversation) == context


class TestNeverRaises:
    def test_a_model_that_can_carry_neither_is_left_untouched(self):
        conversation = SimpleNamespace(text='Synthetic integration transcript.')

        store_meeting_context(conversation, _context())

        assert not hasattr(conversation, 'external_data')

    def test_a_plain_mapping_receiver_still_gets_the_context(self):
        conversation = SimpleNamespace(external_data={})

        store_meeting_context(conversation, _context())

        assert conversation.external_data['calendar_meeting_context']['calendar_event_id'] == 'evt-synthetic'

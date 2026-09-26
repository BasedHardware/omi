"""One unusable element from the extractor must not cost the user the whole conversation.

Live prod signature (backend image 920fc55, api.omi.me):

    ERROR:utils.llm.gateway_error_contract:Conversation processing failed: ValidationError
    -> HTTP 500 {"detail": "Error processing conversation, please try again later"}

30 of these on POST /v1/dev/user/conversations on 2026-08-20 alone (7-12s each, users retrying the
same text twice ~14s apart and getting the same 500). The one instance prod did print a traceback
for names the mechanism exactly:

    Value error, duration must be a positive number of minutes [type=value_error, input_value=0]

`ExtractedEvent.duration` had a validator that *raised* on `0`, so pydantic failed the entire
`StructuredExtraction` -- title, overview, every action item and every other event -- and
`_get_structured` mapped that to HTTP 500. The conversation was stored with no summary at all.

Each list on the extraction is optional detail that already models its own absence
(`default_factory=list`), so an unusable element is worth exactly as much as no element. Drop it,
keep the conversation, and log which field it was: the prod 500s carried no traceback, which is why
the other 30 could not be told apart from this one.
"""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

import json  # noqa: E402
from datetime import datetime  # noqa: E402
from typing import Any  # noqa: E402

import pytest  # noqa: E402
from langchain_core.output_parsers import PydanticOutputParser  # noqa: E402
from langchain_core.runnables import RunnableLambda  # noqa: E402
from pydantic import BaseModel, ValidationError, field_validator  # noqa: E402

import utils.llm.external_integrations as external_integrations  # noqa: E402
from models.structured_extraction import (  # noqa: E402
    ActionItemsExtraction,
    ExtractedEvent,
    StructuredExtraction,
)

# The payload shape prod answered with, trimmed to the offending event plus the content the user lost.
PROD_PAYLOAD: dict[str, Any] = {
    "title": "Kickoff With The Design Team",
    "overview": "Agreed on the launch scope and who owns the landing page.",
    "emoji": "🧠",
    "category": "business",
    "action_items": [{"description": "Send the landing page copy", "capture_owner": "user"}],
    "events": [
        {
            "title": "Launch review",
            "description": "Walk through the final scope",
            "start": "2026-08-20T15:00:00+00:00",
            "duration": 0,
        }
    ],
}


class _StructuredOutputLLM:
    """The provider seam `summarize_experience_text` uses: a payload validated into the schema."""

    def __init__(self, payload: dict[str, Any]):
        self._payload = payload

    def with_structured_output(self, schema):
        return RunnableLambda(lambda _prompt: schema.model_validate(self._payload))


@pytest.fixture
def provider_answers(monkeypatch):
    def _install(payload: dict[str, Any]):
        monkeypatch.setattr(external_integrations, 'get_llm', lambda *a, **k: _StructuredOutputLLM(payload))

    return _install


def test_prod_payload_still_produces_a_summary(provider_answers):
    """The real production function for POST /v1/dev/user/conversations, on the payload that 500'd."""
    provider_answers(PROD_PAYLOAD)

    structured = external_integrations.summarize_experience_text('Kickoff notes.', 'other_text', tz='UTC')

    assert structured.title == 'Kickoff With The Design Team'
    assert structured.overview.startswith('Agreed on the launch scope')
    assert [item.description for item in structured.action_items] == ['Send the landing page copy']
    # The event survives too -- a zero duration says "unspecified", which is what the default means.
    assert [(event.title, event.duration) for event in structured.events] == [('Launch review', 30)]


def test_zero_duration_is_what_lost_the_conversation():
    """Control: the pre-fix model, whose duration validator raised, on the same event."""

    class PreFixExtractedEvent(BaseModel):
        title: str
        description: str = ''
        start: datetime
        duration: int = 30

        @field_validator('duration')
        @classmethod
        def duration_must_be_positive(cls, v: int) -> int:
            if v <= 0:
                raise ValueError('duration must be a positive number of minutes')
            return v

    with pytest.raises(ValidationError, match='duration must be a positive number of minutes'):
        PreFixExtractedEvent.model_validate(PROD_PAYLOAD['events'][0])

    assert ExtractedEvent.model_validate(PROD_PAYLOAD['events'][0]).duration == 30


@pytest.mark.parametrize(
    'duration,expected',
    [('45', 45), (45.0, 45), (-15, 30), (None, 30), ('a while', 30), (0, 30)],
    ids=['numeric-string', 'float', 'negative', 'null', 'prose', 'zero'],
)
def test_duration_falls_back_to_the_documented_default(duration, expected):
    event = ExtractedEvent.model_validate({'title': 'Sync', 'start': '2026-08-20T15:00:00+00:00', 'duration': duration})

    assert event.duration == expected


@pytest.mark.parametrize(
    'field,unusable',
    [
        ('action_items', {'due_at': '2026-08-21T09:00:00+00:00'}),  # no description
        ('events', {'title': 'Standup'}),  # no start
        ('sections', {'heading': 'Decisions'}),  # no body_markdown
    ],
)
def test_an_unusable_element_is_dropped_and_the_conversation_survives(field, unusable):
    payload = dict(PROD_PAYLOAD)
    payload[field] = [unusable, *PROD_PAYLOAD.get(field, [])]

    extraction = PydanticOutputParser(pydantic_object=StructuredExtraction).parse(json.dumps(payload))

    assert extraction.title == 'Kickoff With The Design Team'
    assert len(getattr(extraction, field)) == len(PROD_PAYLOAD.get(field, []))
    assert extraction.to_structured().title == 'Kickoff With The Design Team'


def test_explicit_nulls_fall_back_to_defaults_instead_of_failing():
    extraction = StructuredExtraction.model_validate(
        {'title': 'Kickoff', 'overview': None, 'emoji': None, 'events': None, 'action_items': None}
    )

    assert extraction.title == 'Kickoff'
    assert extraction.overview == ''
    assert extraction.emoji == '🧠'
    assert extraction.events == []
    assert extraction.action_items == []


def test_action_items_extraction_shares_the_guard():
    """`extract_action_items` parses through the action-item-only model, on the main conversation path."""
    completion = json.dumps({'action_items': [{'due_at': None}, {'description': 'Send the deck'}]})

    extraction = PydanticOutputParser(pydantic_object=ActionItemsExtraction).parse(completion)

    assert [item.description for item in extraction.to_action_items()] == ['Send the deck']


def test_dropping_an_element_names_the_field_without_leaking_the_payload(caplog):
    with caplog.at_level('WARNING', logger='models.structured_extraction'):
        StructuredExtraction.model_validate(
            {'title': 'Kickoff', 'action_items': [{'description': 'Call Dana about the invoice'}, {}]}
        )

    assert 'Dropping unusable action_items element' in caplog.text
    assert 'Call Dana' not in caplog.text

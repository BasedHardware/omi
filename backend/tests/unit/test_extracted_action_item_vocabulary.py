"""The extractor's out-of-vocabulary literals must not abort a whole conversation extraction.

Prod, 2026-08-19: the structure model returned a speaker's name ("Archit") for `capture_owner` on
three action items of one conversation. Pydantic raised literal_error for each, PydanticOutputParser
turned that into OutputParserException, and `_get_structured` mapped it to HTTP 500 — the user's
conversation never got a summary because of an enum token. The completion below is that prod
payload, trimmed to the three offending items plus one good one.
"""

import json

import pytest
from langchain_core.output_parsers import PydanticOutputParser

from models.structured_extraction import ActionItemsExtraction, ExtractedActionItem, StructuredExtraction

PROD_COMPLETION = json.dumps(
    {
        "title": "Archit Defines Omi's Agent Context Strategy",
        "overview": "Archit and the team discuss Omi's hardware, Mac app, and strategic direction.",
        "emoji": "🧠",
        "category": "technology",
        "action_items": [
            {
                "description": "Collect a couple of weeks of performance data for the launch.",
                "due_at": None,
                "capture_kind": "clear_commitment",
                "capture_confidence": 0.9,
                "ownership_confidence": 0.9,
                "capture_owner": "Archit",
                "concrete_deliverable": True,
                "candidate_action": "complete",
                "target_task_id": None,
                "source_segment_ids": [],
            },
            {
                "description": "Download and personally test the Omi macOS app.",
                "capture_kind": "direct_request",
                "capture_owner": "user",
                "candidate_action": "complete",
                "source_segment_ids": [],
            },
            {
                "description": "Submit the collaboration form discussed during the evaluation.",
                "capture_kind": "clear_commitment",
                "capture_owner": "Archit",
                "candidate_action": "complete",
                "source_segment_ids": [],
            },
            {
                "description": "Give feedback on the Omi product after trying the device.",
                "capture_kind": "clear_commitment",
                "capture_owner": "Archit",
                "candidate_action": "complete",
                "source_segment_ids": [],
            },
        ],
        "events": [],
    }
)


def test_prod_completion_with_named_capture_owner_parses():
    """The exact prod payload, through the exact production parser seam."""
    extraction = PydanticOutputParser(pydantic_object=StructuredExtraction).parse(PROD_COMPLETION)

    assert extraction.title == "Archit Defines Omi's Agent Context Strategy"
    assert [item.capture_owner for item in extraction.action_items] == ['other', 'user', 'other', 'other']
    assert len(extraction.to_structured().action_items) == 4


def test_named_capture_owner_is_kept_as_owner_name():
    item = ExtractedActionItem.model_validate({'description': 'Send the address', 'capture_owner': 'Archit'})

    assert item.capture_owner == 'other'
    assert item.owner_name == 'Archit'
    assert item.to_action_item().owner_name == 'Archit'


def test_named_capture_owner_does_not_overwrite_an_explicit_owner_name():
    item = ExtractedActionItem.model_validate(
        {'description': 'Send the address', 'capture_owner': 'Archit', 'owner_name': 'Archit Sharma'}
    )

    assert item.capture_owner == 'other'
    assert item.owner_name == 'Archit Sharma'


@pytest.mark.parametrize('value', ['User', ' other ', 'UNKNOWN'])
def test_vocabulary_values_survive_casing_and_padding(value):
    item = ExtractedActionItem.model_validate({'description': 'Ship it', 'capture_owner': value})

    assert item.capture_owner == value.strip().lower()


@pytest.mark.parametrize('field', ['capture_kind', 'due_certainty', 'candidate_action'])
def test_unusable_optional_literal_is_dropped_rather_than_failing_the_item(field):
    item = ExtractedActionItem.model_validate({'description': 'Ship it', field: 'something_the_model_invented'})

    assert getattr(item, field) is None
    assert item.description == 'Ship it'


def test_action_items_extraction_survives_the_same_payload():
    """The action-item-only parser shares the model, so it shares the guard."""
    completion = json.dumps({'action_items': [{'description': 'Send the deck', 'capture_owner': 'Archit'}]})

    extraction = PydanticOutputParser(pydantic_object=ActionItemsExtraction).parse(completion)

    assert extraction.to_action_items()[0].capture_owner == 'other'

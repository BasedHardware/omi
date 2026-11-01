"""Salience (Episodes M3): the notes pass says whether a conversation is a highlight or background, so
Home can fold background into one line under the day. It is optional everywhere: legacy notes and the
one-shot schema never carry it, and an unknown answer is dropped without costing the note."""

import os

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import pytest  # noqa: E402

from models.structured import Structured  # noqa: E402
from models.structured_extraction import (  # noqa: E402
    AgentNotesSubmission,
    RichStructuredExtraction,
    StructuredExtraction,
)
from utils.llm.notes_agent_prompt import SUBMIT_SCHEMA  # noqa: E402


def _notes(**extra):
    return {'title': 'Lunch', 'overview': 'Lunch with Sam.', 'emoji': '🍜', 'category': 'personal', **extra}


@pytest.mark.parametrize('model', [RichStructuredExtraction, AgentNotesSubmission])
@pytest.mark.parametrize(
    'answer,expected',
    [('highlight', 'highlight'), (' Background ', 'background'), ('meh', None), (3, None), (None, None)],
)
def test_salience_reaches_the_note_or_is_dropped(model, answer, expected):
    structured = model.model_validate(_notes(salience=answer)).to_structured()
    assert structured.salience == expected
    assert structured.title == 'Lunch'


def test_the_one_shot_schema_is_unchanged():
    assert 'salience' not in StructuredExtraction.model_fields
    assert 'salience' in RichStructuredExtraction.model_fields


def test_legacy_notes_omit_it_on_the_wire():
    assert 'salience' not in Structured(title='t', overview='o').model_dump()
    assert Structured(title='t', overview='o', salience='background').model_dump()['salience'] == 'background'


def test_the_agent_tool_offers_both_values():
    parameters = SUBMIT_SCHEMA['function']['parameters']
    assert parameters['properties']['salience']['enum'] == ['highlight', 'background']
    assert 'salience' not in parameters['required']

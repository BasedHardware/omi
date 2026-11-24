"""The notes `gist`: one extra field in the existing call, clipped and persisted."""

from __future__ import annotations

import os

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)
os.environ.setdefault('OPENAI_API_KEY', 'test-openai-key-not-real')

from models.structured import Structured
from models.structured_extraction import GIST_MAX_WORDS, StructuredExtraction, clip_gist
from utils.llm.conversation_notes_prompts import conversation_notes_static_instructions
from utils.llm.notes_output import NotesOutput, submit_tool


def test_clip_gist_keeps_at_most_twelve_words():
    text = 'one two three four five six seven eight nine ten eleven twelve thirteen fourteen'
    assert clip_gist(text) == 'one two three four five six seven eight nine ten eleven twelve'
    assert len(clip_gist(text).split()) == GIST_MAX_WORDS
    assert clip_gist('  spaced\n\nout  ') == 'spaced out'
    assert clip_gist(None) == ''


def test_notes_output_clips_and_persists_the_gist():
    output = NotesOutput.model_validate(
        {
            'title': 'Launch plan',
            'overview': 'notes',
            'gist': 'one two three four five six seven eight nine ten eleven twelve thirteen',
        }
    )
    assert output.gist == 'one two three four five six seven eight nine ten eleven twelve'
    assert output.to_structured().gist == output.gist


def test_legacy_extraction_clips_and_persists_the_gist():
    extraction = StructuredExtraction.model_validate(
        {'title': 'Launch plan', 'overview': 'notes', 'gist': 'Launch plan settled; Arjan owns rollout'}
    )
    assert extraction.to_structured().gist == 'Launch plan settled; Arjan owns rollout'


def test_a_missing_gist_stays_absent_from_the_stored_document():
    structured = Structured(title='Launch plan', overview='notes')
    assert 'gist' not in structured.model_dump()
    assert Structured(title='Launch plan', overview='notes', gist='A gist').model_dump()['gist'] == 'A gist'


def test_the_notes_prompt_asks_for_a_gist():
    instructions = conversation_notes_static_instructions('FORMAT')
    assert 'GIST' in instructions and 'at most 12 words' in instructions


def test_the_agent_submit_tool_exposes_the_gist():
    parameters = submit_tool()['function']['parameters']
    assert 'gist' in parameters['properties']

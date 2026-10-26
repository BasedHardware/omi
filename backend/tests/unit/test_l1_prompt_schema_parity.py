"""Synthetic full-response parity for the L1 model-facing schema projection."""

import json
import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault('FIRESTORE_EMULATOR_HOST', 'localhost:8787')
os.environ.setdefault('GOOGLE_CLOUD_PROJECT', 'test')

import pytest

from models.memory_contracts import WorkingObservationArchiveItem
from utils.llm import working_observations as extraction

FIXTURE = json.loads((Path(__file__).parent / 'fixtures/l1_prompt_schema_parity.json').read_text())
DERIVED = {
    'archive_id',
    'allowed_use',
    'normal_search_allowed',
    'is_stable_profile_fact',
    'search_result_label',
}


class FixtureLLM:
    model_name = 'gpt-6-luna'

    def __init__(self, items):
        self.items = items
        self.messages = []

    def invoke(self, messages):
        self.messages = messages
        return SimpleNamespace(content=json.dumps({'items': self.items}))


def extract(items):
    model = FixtureLLM(items)
    result = extraction.extract_l1_memory_archive_items_from_text(
        uid='synthetic-owner',
        source_id='synthetic-conversation',
        source_type='voice_transcript',
        text='Morgan: I chose the Friday launch. Maya: This is a private family matter.',
        user_name='Morgan',
        persist_route_outcomes=False,
        llm=model,
        strict=True,
    )
    return [item.model_dump(mode='json') for item in result], model


def test_prompt_schema_removes_only_server_derived_properties():
    full = WorkingObservationArchiveItem.model_json_schema()
    projected = extraction._L1PromptItem.model_json_schema()
    full.pop('title')
    projected.pop('title')
    assert set(full['properties']) - set(projected['properties']) == DERIVED
    for key in DERIVED:
        full['properties'].pop(key)
    # All remaining types, aliases, defaults, enums, constraints and references survive.
    assert projected == full


@pytest.mark.parametrize('case', FIXTURE['cases'], ids=lambda case: case['name'])
def test_omitting_model_generated_derived_fields_preserves_complete_parsed_item(case):
    old_shape = {**case['item'], **case['supplied_derived']}
    full, _ = extract([old_shape])
    projected, model = extract([case['item']])
    assert full == projected
    assert all(key in projected[0] for key in DERIVED)
    assert projected[0]['archive_id'].startswith('l1_')
    assert projected[0]['archive_id'] != case['supplied_derived']['archive_id']
    system = model.messages[0]['content']
    assert extraction._l1_format_instructions() in system
    for key in DERIVED:
        assert f'"{key}"' not in extraction._l1_format_instructions()


def test_empty_extraction_and_full_parser_contract_stay_available():
    assert extract([])[0] == []
    # The prompt projection must never shrink the persisted/public model schema.
    assert DERIVED <= set(WorkingObservationArchiveItem.model_json_schema()['properties'])


def test_projected_response_still_rejects_missing_memory_text():
    with pytest.raises(extraction.WorkingObservationExtractionError):
        extract([{'about': 'the user', 'evidence_quotes': ['I chose the Friday launch.']}])

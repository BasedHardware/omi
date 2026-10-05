"""Stale provenance is omitted on reads without changing stored claims."""

import importlib
import json
from copy import deepcopy
from datetime import datetime, timezone

import pytest
from pydantic import TypeAdapter

from models.conversation import Conversation, ConversationMutationResponse, CreateConversationResponse
from models.note_claims import current_note_claims
from models.structured import NoteClaim, Section, Structured
from testing.import_isolation import AutoMockModule, stub_modules


def note():
    targets = {
        '/title': 'Pricing decision',
        '/overview': 'Ari approved the price.',
        '/sections/0/body_markdown': 'Launch on Monday.',
    }
    return Structured(
        title=targets['/title'],
        overview=targets['/overview'],
        sections=[Section(heading='Next step', body_markdown=targets['/sections/0/body_markdown'])],
        note_claims=[
            NoteClaim(target=target, text=text, evidence_ids=['speech:s1'], provenance='said')
            for target, text in targets.items()
        ],
    )


def conversation(structured):
    return Conversation(
        id='synthetic',
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        started_at=None,
        finished_at=None,
        structured=structured,
    )


@pytest.fixture
def render():
    with stub_modules({name: AutoMockModule(name) for name in ('database.auth', 'database.folders', 'database.users')}):
        yield importlib.import_module('utils.conversations.render')


@pytest.mark.parametrize(
    'field,replacement,target',
    [
        ('title', 'Owner edited the title', '/title'),
        ('overview', 'Owner wrote a new summary.', '/overview'),
        ('sections', [], '/sections/0/body_markdown'),
    ],
)
@pytest.mark.parametrize('mode', ['python', 'json'])
def test_edited_fields_drop_only_stale_claims_on_read(field, replacement, target, mode):
    structured = note()
    original = deepcopy(structured.note_claims)
    setattr(structured, field, replacement)
    expected = [claim for claim in original if claim.target != target]
    assert current_note_claims(structured) == expected
    dumped = conversation(structured).model_dump(mode=mode)['structured']['note_claims']
    assert dumped == [claim.model_dump(mode=mode) for claim in expected]
    assert structured.note_claims == original  # No in-memory or persisted mutation.


@pytest.mark.parametrize(
    'response',
    [
        lambda conv: ConversationMutationResponse(status='ok', conversation=conv),
        lambda conv: CreateConversationResponse(conversation=conv),
        lambda conv: TypeAdapter(list[Conversation]).dump_python([conv], mode='json'),
    ],
)
def test_nested_response_serialization_filters_stale_claims(response):
    structured = note()
    structured.title = 'Edited title'
    result = response(conversation(structured))
    data = result if isinstance(result, list) else result.model_dump(mode='json')
    projected = data[0] if isinstance(data, list) else data['conversation']
    assert [claim['target'] for claim in projected['structured']['note_claims']] == [
        '/overview',
        '/sections/0/body_markdown',
    ]


def test_json_and_integration_dumps_filter_current_claims(render):
    structured = note()
    structured.overview = 'Replaced overview.'
    conv = conversation(structured)
    for data in (json.loads(conv.model_dump_json()), conv.as_dict_cleaned_dates(), render.conversation_to_dict(conv)):
        assert [claim['target'] for claim in data['structured']['note_claims']] == [
            '/title',
            '/sections/0/body_markdown',
        ]


def test_locked_projection_filters_claims_after_redaction(render):
    structured = note().model_dump(mode='json')
    structured['action_items'] = [{'description': 'Send invoice'}]
    structured['note_claims'].append(
        {
            'target': '/action_items/0/description',
            'text': 'Send invoice',
            'evidence_ids': ['speech:s1'],
            'provenance': 'said',
        }
    )
    listed = render.redact_conversation_for_list({'is_locked': True, 'structured': structured})
    assert 'note_claims' not in listed['structured']
    assert structured['action_items'] == [{'description': 'Send invoice'}]
    assert structured['note_claims']  # Projection must not mutate the source note.
    integrated = render.redact_conversation_for_integration({'is_locked': True, 'structured': deepcopy(structured)})
    assert [claim['target'] for claim in integrated['structured']['note_claims']] == ['/sections/0/body_markdown']


def test_unedited_claims_and_attribution_preserved():
    structured = note()
    assert current_note_claims(structured) == structured.note_claims
    assert conversation(structured).model_dump()['structured'] == structured.model_dump()


def test_legacy_notes_remain_metadata_free(render):
    structured = Structured(title='Legacy', overview='No episode annotations')
    expected = structured.model_dump()
    assert current_note_claims(structured) == []
    assert conversation(structured).model_dump()['structured'] == expected
    assert 'note_claims' not in expected
    projected = render.redact_conversation_for_integration({'is_locked': True, 'structured': deepcopy(expected)})
    assert 'note_claims' not in projected['structured']


def test_filter_checks_serialized_field_exclusions():
    dumped = conversation(note()).model_dump(exclude={'structured': {'sections'}})
    assert [claim['target'] for claim in dumped['structured']['note_claims']] == ['/title', '/overview']


def test_json_pointer_resolution_rejects_missing_targets_and_nonexact_text():
    data = {'title': 'Keep Case', 'sections': [{'body_markdown': 'Known detail'}], 'a/b~c': 'Escaped'}
    data['note_claims'] = [
        {'target': target, 'text': text}
        for target, text in (
            ('/title', 'Keep Case'),
            ('/a~1b~0c', 'Escaped'),
            ('/title', 'keep case'),
            ('/title', ''),
            ('/missing', 'Detail'),
            ('/sections/-1/body_markdown', 'Known detail'),
            ('/sections/99999999999999999999', 'Known detail'),
            ('/sections/00/body_markdown', 'Known detail'),
            ('/sections', 'Known detail'),
            ('/note_claims/0/text', 'Keep Case'),
            ('title', 'Keep Case'),
        )
    ]
    before = deepcopy(data)
    assert current_note_claims(data) == data['note_claims'][:2]
    assert data == before

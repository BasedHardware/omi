"""Vertex JSON Schema wire contract for real structured-output consumers."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from llm_gateway.gateway.vertex_wire import _vertex_request
from models.dream_agent import Plan, Triage
from utils.translation_core.providers import LunaTranslationBatch

# Vertex v1 GenerationConfig.response_json_schema's documented keyword set.
# Keep this independent of the converter so additions require a contract review.
SUPPORTED = {
    '$id',
    '$defs',
    '$ref',
    '$anchor',
    'type',
    'format',
    'title',
    'description',
    'enum',
    'items',
    'prefixItems',
    'minItems',
    'maxItems',
    'minimum',
    'maximum',
    'anyOf',
    'oneOf',
    'properties',
    'additionalProperties',
    'required',
    'propertyOrdering',
}


def assert_vertex_subset(node):
    assert isinstance(node, dict)
    assert set(node) <= SUPPORTED
    if '$ref' in node:
        assert all(key.startswith('$') for key in node)
    for key in ('properties', '$defs'):
        for child in node.get(key, {}).values():
            assert_vertex_subset(child)
    for key in ('items', 'additionalProperties'):
        child = node.get(key)
        if isinstance(child, dict):
            assert_vertex_subset(child)
    for key in ('anyOf', 'oneOf', 'prefixItems'):
        for child in node.get(key, []):
            assert_vertex_subset(child)


@pytest.mark.parametrize('model', [Plan, Triage, LunaTranslationBatch])
def test_real_consumer_schema_uses_vertex_json_schema_subset(model):
    schema = model.model_json_schema()
    original = deepcopy(schema)
    payload = _vertex_request(
        {
            'messages': [{'role': 'user', 'content': 'synthetic'}],
            'response_format': {'type': 'json_schema', 'json_schema': {'name': model.__name__, 'schema': schema}},
        }
    )
    config = payload['generationConfig']
    assert config['responseMimeType'] == 'application/json'
    converted = config.get('responseJsonSchema', config.get('responseSchema'))
    assert_vertex_subset(converted)
    assert 'responseSchema' not in config
    assert '$defs' in converted
    assert schema == original


def test_caller_still_enforces_constraints_omitted_from_generation_schema():
    with pytest.raises(ValidationError):
        Plan.model_validate({'edits': [{'kind': 'spelling', 'target': 'synthetic', 'reason': '', 'evidence': []}]})
    with pytest.raises(ValidationError):
        Plan.model_validate({'unexpected': True})
    with pytest.raises(ValidationError):
        Plan.model_validate(
            {
                'questions': [
                    {
                        'item_id': 'synthetic',
                        'kind': 'task',
                        'title': 'synthetic',
                        'created_at': '2026-10-09T00:00:00Z',
                        'spelling': {'term_id': 'synthetic', 'options': ['a', 'b'], 'allow_custom': True},
                    }
                ]
            }
        )


def test_const_nullable_ref_siblings_and_keyword_named_properties():
    schema = {
        '$defs': {'Item': {'type': 'string', 'minLength': 1}},
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'const': {'const': 'synthetic', 'default': 'synthetic'},
            'default': {'anyOf': [{'$ref': '#/$defs/Item'}, {'type': 'null'}], 'default': None},
            '$ref': {'$ref': '#/$defs/Item', 'description': 'synthetic'},
            'tuple': {'type': 'array', 'prefixItems': [{'type': 'integer'}, {'type': 'string'}], 'maxItems': 2},
        },
    }
    converted = _vertex_request(
        {
            'messages': [],
            'response_format': {'type': 'json_schema', 'json_schema': {'schema': schema}},
        }
    )['generationConfig']['responseJsonSchema']
    assert_vertex_subset(converted)
    assert set(converted['properties']) == {'const', 'default', '$ref', 'tuple'}
    assert converted['properties']['const'] == {'enum': ['synthetic']}
    assert converted['properties']['default']['anyOf'] == [{'$ref': '#/$defs/Item'}, {'type': 'null'}]
    assert converted['properties']['$ref'] == {'type': 'string', 'description': 'synthetic'}
    assert converted['additionalProperties'] is False


@pytest.mark.parametrize('ref', ['https://invalid.example/schema', '#/$defs/Missing'])
def test_unresolvable_refs_fail_before_dispatch(ref):
    from llm_gateway.gateway.provider_types import ProviderFailure
    from llm_gateway.gateway.schemas import FailureClass

    with pytest.raises(ProviderFailure) as failure:
        _vertex_request(
            {
                'messages': [],
                'response_format': {'type': 'json_schema', 'json_schema': {'schema': {'$ref': ref}}},
            }
        )
    assert failure.value.failure_class == FailureClass.CAPABILITY_MISMATCH


def test_optional_recursive_ref_remains_compact():
    schema = {
        '$defs': {
            'Node': {
                'type': 'object',
                'properties': {
                    'child': {'anyOf': [{'$ref': '#/$defs/Node'}, {'type': 'null'}]},
                },
            }
        },
        '$ref': '#/$defs/Node',
    }
    converted = _vertex_request(
        {
            'messages': [],
            'response_format': {'type': 'json_schema', 'json_schema': {'schema': schema}},
        }
    )['generationConfig']['responseJsonSchema']
    assert_vertex_subset(converted)
    assert converted['$defs']['Node']['properties']['child']['anyOf'][0] == {'$ref': '#/$defs/Node'}


@pytest.mark.parametrize(
    'message,reason',
    [
        ('Unknown name "const" at generation_config.response_schema echoed private text', 'schema_keyword'),
        ('Invalid response schema: reference $ref cannot have siblings private text', 'schema_reference'),
        ('Response schema too complex; too many states private text', 'schema_complexity'),
        ('Invalid response schema private text', 'schema'),
        ('Missing a thought_signature private text', 'missing_thought_signature'),
        ('arbitrary private text', 'unknown'),
    ],
)
def test_vertex_4xx_log_only_emits_sanitized_reason_class(capsys, message, reason):
    import json
    from llm_gateway.gateway.vertex_pt_policy import VertexPTPolicyMixin
    from utils.llm import vertex_pt_routing as ptr

    provider = VertexPTPolicyMixin()
    provider._observe_attempt(
        ptr.PT_MODEL_CURRENT, 'dedicated', 400, json.dumps({'error': {'message': message}}).encode()
    )
    output = capsys.readouterr().out
    assert json.loads(output)['reason'] == reason
    assert 'private text' not in output
    assert 'const' not in output


def test_root_ref_with_title_retains_definitions_for_nested_refs():
    schema = {
        '$defs': {
            'Root': {'type': 'object', 'properties': {'child': {'$ref': '#/$defs/Child'}}},
            'Child': {'type': 'string'},
        },
        '$ref': '#/$defs/Root',
        'title': 'Root',
    }
    converted = _vertex_request(
        {
            'messages': [],
            'response_format': {'type': 'json_schema', 'json_schema': {'schema': schema}},
        }
    )['generationConfig']['responseJsonSchema']
    assert_vertex_subset(converted)
    assert converted['$defs']['Child'] == {'type': 'string'}
    assert converted['properties']['child'] == {'$ref': '#/$defs/Child'}


def test_legacy_definitions_and_escaped_pointer_names():
    schema = {
        'definitions': {'a/b~c': {'type': 'string'}},
        'properties': {
            'item': {'$ref': '#/definitions/a~1b~0c'},
        },
        'type': 'object',
    }
    converted = _vertex_request(
        {
            'messages': [],
            'response_format': {'type': 'json_schema', 'json_schema': {'schema': schema}},
        }
    )['generationConfig']['responseJsonSchema']
    assert_vertex_subset(converted)
    assert converted['$defs']['a/b~c'] == {'type': 'string'}
    assert converted['properties']['item'] == {'$ref': '#/$defs/a~1b~0c'}

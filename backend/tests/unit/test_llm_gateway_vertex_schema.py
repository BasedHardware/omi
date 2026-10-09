"""Vertex JSON Schema wire contract for real structured-output consumers."""

from copy import deepcopy
import json

import pytest
from pydantic import ValidationError

from llm_gateway.gateway.provider_types import ProviderFailure
from llm_gateway.gateway.schemas import FailureClass
from llm_gateway.gateway.vertex_pt_policy import VertexPTPolicyMixin
from llm_gateway.gateway.vertex_wire import _vertex_request
from llm_gateway.gateway.vertex_schema import vertex_response_json_schema
from models.dream_agent import Plan, Triage
from utils.llm import vertex_pt_routing as ptr
from utils.translation_core.providers import LunaTranslationBatch

from tests.support.vertex_contract import assert_vertex_subset


@pytest.mark.parametrize('model', [Plan, Triage])
def test_real_dream_schema_omits_all_array_bounds_without_other_changes(model):
    schema = model.model_json_schema()
    original = vertex_response_json_schema(schema)

    def remove_bounds(node):
        if isinstance(node, dict):
            return {key: remove_bounds(value) for key, value in node.items() if key not in {'minItems', 'maxItems'}}
        if isinstance(node, list):
            return [remove_bounds(value) for value in node]
        return node

    assert 'maxItems' in json.dumps(schema)  # Guard against testing an unbounded stand-in.
    assert 'minItems' in json.dumps(schema)
    assert original == remove_bounds(original)
    assert original == vertex_response_json_schema(remove_bounds(schema))


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


def test_array_bound_removal_preserves_other_supported_constraints_and_data_names():
    schema = {
        'type': 'array',
        'minItems': 1,
        'maxItems': 3,
        'title': 'synthetic',
        'description': 'synthetic',
        'items': {
            'type': 'object',
            'required': ['maxItems'],
            'additionalProperties': False,
            'propertyOrdering': ['maxItems', 'minItems'],
            'properties': {
                'maxItems': {'type': 'integer', 'minimum': 1, 'maximum': 5, 'enum': [1, 2]},
                'minItems': {'type': 'string', 'format': 'date-time', 'enum': ['maxItems']},
            },
        },
    }
    expected = deepcopy(schema)
    del expected['minItems'], expected['maxItems']
    assert vertex_response_json_schema(schema) == expected


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
        ('Response schema too complex; too many states private text', 'schema_too_many_states'),
        (
            'The specified schema produces a constraint that has too many states for serving. '
            'Typical causes are long array length limits (especially when nested). private text',
            'schema_too_many_states',
        ),
        ('Invalid response schema private text', 'schema'),
        ('Missing a thought_signature private text', 'missing_thought_signature'),
        ('arbitrary private text', 'unknown'),
    ],
)
def test_vertex_4xx_log_only_emits_sanitized_reason_class(capsys, message, reason):

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


@pytest.mark.parametrize('values', [[True, False], [None], ['synthetic', None], [{'type': 'string'}]])
def test_enums_outside_vertex_scalar_vocabulary_are_left_to_caller_validation(values):
    converted = _vertex_request(
        {
            'messages': [],
            'response_format': {'type': 'json_schema', 'json_schema': {'schema': {'enum': values}}},
        }
    )['generationConfig']['responseJsonSchema']
    assert 'enum' not in converted


def test_string_and_numeric_enums_remain_constrained():
    converted = _vertex_request(
        {
            'messages': [],
            'response_format': {'type': 'json_schema', 'json_schema': {'schema': {'enum': ['synthetic', 1, 1.5]}}},
        }
    )['generationConfig']['responseJsonSchema']
    assert converted['enum'] == ['synthetic', 1, 1.5]


def test_optional_reference_to_schema_root_remains_compact():
    schema = {'type': 'object', 'properties': {'child': {'anyOf': [{'$ref': '#'}, {'type': 'null'}]}}}
    converted = _vertex_request(
        {
            'messages': [],
            'response_format': {'type': 'json_schema', 'json_schema': {'schema': schema}},
        }
    )['generationConfig']['responseJsonSchema']
    assert_vertex_subset(converted)
    assert converted['properties']['child']['anyOf'][0] == {'$ref': '#'}

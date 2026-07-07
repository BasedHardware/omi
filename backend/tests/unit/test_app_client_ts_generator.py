from __future__ import annotations

import json
from pathlib import Path

from scripts import generate_ts_openapi_types

ROOT_DIR = Path(__file__).resolve().parents[3]
SPEC_PATH = ROOT_DIR / 'docs' / 'api-reference' / 'app-client-openapi.json'


def test_typescript_schema_types_are_generated_from_app_client_openapi():
    spec = json.loads(SPEC_PATH.read_text())
    generated = generate_ts_openapi_types.generate(spec, 'docs/api-reference/app-client-openapi.json')

    for output in generate_ts_openapi_types.DEFAULT_OUTPUTS:
        assert output.read_text() == generated
    assert '// GENERATED CODE - DO NOT EDIT.' in generated
    assert 'export interface Conversation {' in generated
    assert 'export interface GoalResponse {' in generated
    assert 'export interface App {' in generated
    assert 'export interface Memory {' in generated
    assert 'created_at: string;' in generated
    assert 'finished_at: string | null;' in generated
    assert 'transcript_segments?: Array<TranscriptSegment>;' in generated


def test_typescript_operation_response_map_is_generated():
    spec = json.loads(SPEC_PATH.read_text())
    generated = generate_ts_openapi_types.generate(spec, 'docs/api-reference/app-client-openapi.json')

    assert 'export interface OmiApiPaths {' in generated
    assert '"/v1/conversations": {' in generated
    assert 'operationId: "get_conversations_v1_conversations_get";' in generated
    assert '"200": Array<Conversation>;' in generated
    assert '"/v1/goals/suggest": {' in generated
    assert '"200": GoalSuggestionResponse;' in generated


def test_typescript_generator_handles_refs_nullability_and_additional_properties():
    spec = {
        'components': {
            'schemas': {
                'Nested': {'type': 'object', 'properties': {'value': {'type': 'string'}}, 'required': ['value']},
                'Example': {
                    'type': 'object',
                    'properties': {
                        'id': {'type': 'string'},
                        'maybe': {'anyOf': [{'type': 'string'}, {'type': 'null'}]},
                        'nested': {'$ref': '#/components/schemas/Nested'},
                        'tags': {'type': 'array', 'items': {'type': 'string'}},
                        'metadata': {'type': 'object', 'additionalProperties': {'type': 'number'}},
                    },
                    'required': ['id', 'nested'],
                },
            }
        },
        'paths': {},
    }

    generated = generate_ts_openapi_types.generate(spec, 'test-openapi.json')

    assert 'export interface Example {' in generated
    assert 'id: string;' in generated
    assert 'maybe?: string | null;' in generated
    assert 'nested: Nested;' in generated
    assert 'tags?: Array<string>;' in generated
    assert 'metadata?: Record<string, number>;' in generated

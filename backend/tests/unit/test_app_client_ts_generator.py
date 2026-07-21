from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path, PureWindowsPath

from scripts import generate_ts_openapi_types

ROOT_DIR = Path(__file__).resolve().parents[3]
SPEC_PATH = ROOT_DIR / 'docs' / 'api-reference' / 'app-client-openapi.json'


def test_typescript_schema_types_are_generated_from_app_client_openapi():
    spec = json.loads(SPEC_PATH.read_text(encoding='utf-8'))
    generated = generate_ts_openapi_types.generate(spec, 'docs/api-reference/app-client-openapi.json')

    for output in generate_ts_openapi_types.DEFAULT_OUTPUTS:
        assert output.read_text(encoding='utf-8') == generated
    assert '// GENERATED CODE - DO NOT EDIT.' in generated
    assert 'export interface Conversation {' in generated
    assert 'export interface GoalResponse {' in generated
    assert 'export interface App {' in generated
    assert 'export interface Memory {' in generated
    assert 'created_at: string;' in generated
    assert 'finished_at: string | null;' in generated
    assert 'transcript_segments?: Array<TranscriptSegment>;' in generated


def test_typescript_operation_response_map_is_generated():
    spec = json.loads(SPEC_PATH.read_text(encoding='utf-8'))
    generated = generate_ts_openapi_types.generate(spec, 'docs/api-reference/app-client-openapi.json')

    assert 'export interface OmiApiPaths {' in generated
    assert '"/v1/conversations": {' in generated
    assert 'operationId: "get_conversations_v1_conversations_get";' in generated
    assert '"200": Array<Conversation>;' in generated
    assert '"/v1/goals/suggest": {' in generated
    assert '"200": GoalSuggestionResponse;' in generated


def test_typescript_generator_emits_required_operation_headers():
    spec = {
        'components': {'schemas': {}},
        'paths': {
            '/v1/example': {
                'post': {
                    'operationId': 'create_example',
                    'parameters': [
                        {
                            'in': 'header',
                            'name': 'Idempotency-Key',
                            'required': True,
                            'schema': {'type': 'string'},
                        }
                    ],
                    'responses': {'204': {'description': 'Created'}},
                }
            }
        },
    }

    generated = generate_ts_openapi_types.generate(spec, 'test-openapi.json')

    assert 'header: { Idempotency_Key: string }' in generated
    assert '"Idempotency-Key": String(header.Idempotency_Key)' in generated


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


def test_typescript_generator_emits_type_for_object_unions():
    spec = {
        'components': {
            'schemas': {
                'CandidateRecord': {
                    'oneOf': [
                        {
                            'type': 'object',
                            'properties': {
                                'proposed_action': {'const': 'create'},
                                'task_id': {'type': 'null'},
                            },
                        },
                        {
                            'type': 'object',
                            'properties': {
                                'proposed_action': {'const': 'update'},
                                'task_id': {'type': 'string'},
                            },
                            'required': ['task_id'],
                        },
                    ]
                },
                'NullableObject': {
                    'anyOf': [
                        {'type': 'object', 'properties': {'ok': {'type': 'boolean'}}, 'required': ['ok']},
                        {'type': 'null'},
                    ]
                },
            }
        },
        'paths': {},
    }

    generated = generate_ts_openapi_types.generate(spec, 'test-openapi.json')

    assert 'export type CandidateRecord =' in generated
    assert 'export interface CandidateRecord' not in generated
    assert '} | {' in generated
    assert 'export type NullableObject =' in generated
    assert 'export interface NullableObject' not in generated
    assert re.search(r'export type CandidateRecord = \{[\s\S]*?\} \| \{', generated)


def test_typescript_source_label_is_stable_for_windows_paths():
    root = PureWindowsPath('C:/src/omi')
    spec_path = root / 'docs' / 'api-reference' / 'app-client-openapi.json'

    assert (
        generate_ts_openapi_types.source_label_for_path(spec_path, root) == 'docs/api-reference/app-client-openapi.json'
    )


def test_typescript_generator_cli_uses_utf8_when_the_process_locale_does_not(tmp_path: Path):
    spec_path = tmp_path / 'openapi.json'
    output_path = tmp_path / 'generated.ts'
    spec = {
        'components': {
            'schemas': {
                'Price\u20ac': {
                    'type': 'object',
                    'properties': {'currency': {'type': 'string'}},
                }
            }
        },
        'paths': {},
    }
    spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding='utf-8')
    env = os.environ.copy()
    env.update({'LANG': 'C', 'LC_ALL': 'C', 'PYTHONCOERCECLOCALE': '0', 'PYTHONUTF8': '0'})

    completed = subprocess.run(
        [
            sys.executable,
            str(generate_ts_openapi_types.__file__),
            '--spec',
            str(spec_path),
            '--output',
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode == 0, completed.stderr
    assert 'export interface Price_ {' in output_path.read_text(encoding='utf-8')

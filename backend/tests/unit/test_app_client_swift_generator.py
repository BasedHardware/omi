"""Tests for the Swift DTO generator (backend/scripts/generate_swift_openapi_types.py).

Validates that the generated OmiApi.generated.swift is fresh against the
app-client OpenAPI spec, that the generator handles refs/optionals/enums, and
that the namespaced OmiAPI types cover the desktop's highest-traffic read DTOs.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts import generate_swift_openapi_types

ROOT_DIR = Path(__file__).resolve().parents[3]
SPEC_PATH = ROOT_DIR / 'docs' / 'api-reference' / 'app-client-openapi.json'
SWIFT_PATH = ROOT_DIR / 'desktop' / 'macos' / 'Desktop' / 'Sources' / 'Generated' / 'OmiApi.generated.swift'


def test_swift_dto_file_is_generated_from_app_client_openapi():
    spec = json.loads(SPEC_PATH.read_text())
    generated = generate_swift_openapi_types.generate(spec, 'docs/api-reference/app-client-openapi.json')

    assert SWIFT_PATH.read_text() == generated
    assert '// GENERATED CODE - DO NOT EDIT.' in generated
    assert 'public enum OmiAPI {' in generated


def test_swift_dto_file_covers_desktop_high_traffic_read_schemas():
    generated = SWIFT_PATH.read_text()

    # The desktop's highest-traffic read endpoints (conversations, memories,
    # action items, goals) decode these generated DTOs through adapter inits
    # in APIClient.swift. Each must be present in the OmiAPI namespace.
    for name in (
        'struct Conversation:',
        'struct Structured:',
        'struct ActionItemResponse:',
        'struct ActionItemCreateRequest:',
        'struct ActionItemUpdateRequest:',
        'struct ActionItem:',
        'struct MemoryDB:',
        'struct GoalResponse:',
        'struct GoalDetailProjection:',
        'struct CandidateRecord:',
        'struct WorkstreamDetailProjection:',
        'struct ArtifactDescriptor:',
        'struct ContinuationCheckpoint:',
        'struct TranscriptSegment:',
        'struct Geolocation:',
        'struct AppResult:',
    ):
        assert f'public {name}' in generated, f'OmiAPI.{name} missing from generated Swift DTOs'

    # Enums the desktop consumes via the wire.
    assert 'public enum ConversationStatus:' in generated
    assert 'public enum MemoryCategory:' in generated
    assert 'public enum GoalType:' in generated
    assert 'public enum CandidateTaskChange: Codable {' in generated
    assert 'public enum CandidateCreate: Codable {' in generated
    assert 'public enum OmiPatchField<Value: Codable>: Codable {' in generated
    assert 'public let goalId: OmiPatchField<String>' in generated
    assert 'public struct GoalUpdate: Codable {' in generated
    assert 'public let desiredOutcome: OmiPatchField<String>' in generated
    assert 'public let nextReviewAt: OmiPatchField<String>' in generated
    assert 'taskChange = .create(try c.decode(TaskCreatePayload.self' in generated


def test_swift_generator_handles_refs_optionals_and_enums():
    # Test the unit-level renderers directly since generate() only emits
    # TARGET_SCHEMAS + transitive deps.
    color_schema = {'type': 'string', 'enum': ['red', 'green', 'blue']}
    nested_schema = {
        'type': 'object',
        'properties': {'value': {'type': 'string'}},
        'required': ['value'],
    }
    widget_schema = {
        'type': 'object',
        'properties': {
            'id': {'type': 'string'},
            'tags': {'type': 'array', 'items': {'type': 'string'}},
            'nested': {'$ref': '#/components/schemas/Nested'},
            'color': {'$ref': '#/components/schemas/Color'},
            'meta': {'type': 'object', 'additionalProperties': {'type': 'number'}},
        },
        'required': ['id', 'nested'],
    }

    color_block = generate_swift_openapi_types._render_enum('Color', color_schema)
    assert 'public enum Color: String, Codable, CaseIterable {' in color_block
    assert 'case red' in color_block
    assert 'case _unknown = "__unknown__"' in color_block  # tolerant fallback

    nested_block = generate_swift_openapi_types._render_struct('Nested', nested_schema)
    assert 'public struct Nested: Codable {' in nested_block

    widget_block = generate_swift_openapi_types._render_struct('Widget', widget_schema)
    assert 'public struct Widget: Codable {' in widget_block
    # Refs render as the referenced type name; required ref is non-optional.
    assert 'public let nested: Nested' in widget_block
    assert 'public let tags: [String]?' in widget_block
    # Newly optional fields must not break existing construction call sites.
    assert 'tags: [String]? = nil' in widget_block
    # AdditionalProperties renders as a typed dictionary.
    assert '[String: Double]?' in widget_block


def test_swift_generator_sanitizes_openapi_component_names():
    rendered = generate_swift_openapi_types._render_struct(
        'WorkstreamProposal-Output',
        {'type': 'object', 'properties': {'title': {'type': 'string'}}, 'required': ['title']},
    )

    assert 'public struct WorkstreamProposalOutput: Codable {' in rendered
    assert 'WorkstreamProposal-Output' not in rendered


def test_swift_generator_module_helper_is_emitted():
    spec = {'components': {'schemas': {}}}
    generated = generate_swift_openapi_types.generate(spec, 'test-openapi.json')
    # OmiAnyCodable helper present for opaque maps even with no target schemas.
    assert 'public struct OmiAnyCodable: Codable' in generated
    assert 'public enum OmiAPI {' in generated


def test_swift_generator_emits_required_headers_and_client_default_headers():
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
                    'responses': {'200': {'content': {'application/json': {'schema': {'type': 'string'}}}}},
                }
            }
        },
    }

    generated = generate_swift_openapi_types.generate(spec, 'test-openapi.json')

    assert 'headers: [String: String] = [:]' in generated
    assert 'idempotencyKey: String' in generated
    assert 'for (name, value) in client.headers' in generated
    assert 'req.setValue(String(idempotencyKey), forHTTPHeaderField: "Idempotency-Key")' in generated

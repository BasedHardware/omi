"""Cross-client wire-contract checks for the additive knowledge ledger fields.

The app-client OpenAPI document is the schema authority. This test deliberately
proves only the checked-in wire artifacts and JSON boundary: it does not claim
that a client has adopted ledger behavior or that a runtime adapter accepts a
malformed/future payload safely.
"""

from __future__ import annotations

import copy
import json
import warnings
from pathlib import Path

with warnings.catch_warnings():
    warnings.simplefilter('ignore', DeprecationWarning)
    from jsonschema import Draft202012Validator, RefResolver

from scripts import generate_dart_models, generate_swift_openapi_types, generate_ts_openapi_types

ROOT_DIR = Path(__file__).resolve().parents[3]
SPEC_PATH = ROOT_DIR / 'docs' / 'api-reference' / 'app-client-openapi.json'
FIXTURE_PATH = Path(__file__).with_name('fixtures') / 'knowledge_ledger_memories.json'
DART_PATH = ROOT_DIR / 'app' / 'lib' / 'backend' / 'schema' / 'gen' / 'memories_wire.g.dart'
SWIFT_PATH = ROOT_DIR / 'desktop' / 'macos' / 'Desktop' / 'Sources' / 'Generated' / 'OmiApi.generated.swift'

LEDGER_MEMORY_FIELDS = {
    'body',
    'curation_weight',
    'evidence',
    'intent_backed',
    'invalid_at',
    'kind',
    'ledger_schema_version',
    'slot',
    'subject_entity_id',
    'subject_scope',
    'superseded_by',
    'trigger_condition',
    'valid_at',
    'write_reason',
}

EVIDENCE_FIELDS = {
    'artifact_ref',
    'capture_confidence',
    'client_device_id',
    'created_at',
    'evidence_id',
    'extractor_id',
    'extractor_version',
    'independence_group',
    'redaction_status',
    'source_id',
    'source_signal',
    'source_type',
}


def _spec() -> dict:
    return json.loads(SPEC_PATH.read_text(encoding='utf-8'))


def _schema(spec: dict, name: str) -> dict:
    return spec['components']['schemas'][name]


def _non_null_variants(schema: dict) -> list[dict]:
    variants = schema.get('anyOf')
    if variants is None:
        return [schema]
    return [variant for variant in variants if variant.get('type') != 'null']


def _validate_memory_fixture(spec: dict, fixture: dict) -> None:
    # The OpenAPI document uses local component refs. RefResolver is deprecated
    # upstream but remains the supported jsonschema API for this pinned runtime.
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', DeprecationWarning)
        validator = Draft202012Validator(
            _schema(spec, 'MemoryDB'),
            resolver=RefResolver.from_schema(spec),
        )
    errors = sorted(validator.iter_errors(fixture), key=lambda error: list(error.path))
    assert not errors, '\n'.join(error.message for error in errors)


def test_knowledge_ledger_v1_schema_is_additive_and_evidence_is_optional():
    spec = _spec()
    memory = _schema(spec, 'MemoryDB')
    evidence = _schema(spec, 'Evidence')

    assert LEDGER_MEMORY_FIELDS <= memory['properties'].keys()
    assert EVIDENCE_FIELDS == evidence['properties'].keys()
    assert set(memory['required']) == {'content', 'created_at', 'id', 'layer', 'uid', 'updated_at'}
    assert set(evidence['required']) == {'evidence_id', 'independence_group'}
    assert 'evidence' not in memory['required']

    # Version is intentionally open-ended so a v1 decoder can identify and
    # quarantine a future version instead of treating it as a current row.
    assert _non_null_variants(memory['properties']['ledger_schema_version']) == [{'type': 'string'}]
    assert memory.get('additionalProperties', True) is True
    assert evidence.get('additionalProperties', True) is True

    evidence_item = memory['properties']['evidence']['items']
    assert evidence_item == {'$ref': '#/components/schemas/Evidence'}


def test_legacy_v1_and_future_wire_fixtures_validate_at_the_shared_boundary():
    spec = _spec()
    fixtures = json.loads(FIXTURE_PATH.read_text(encoding='utf-8'))

    for name, payload in fixtures.items():
        _validate_memory_fixture(spec, payload)
        assert payload['content'], name

    assert 'ledger_schema_version' not in fixtures['legacy']
    assert fixtures['v1']['ledger_schema_version'] == 'knowledge_ledger.v1'
    assert fixtures['v1']['evidence'][0]['evidence_id'] == 'evidence-1'
    assert fixtures['future']['ledger_schema_version'] == 'knowledge_ledger.v2'
    assert 'future_ledger_field' in fixtures['future']
    assert 'future_evidence_field' in fixtures['future']['evidence'][0]


def test_optional_evidence_type_is_rendered_for_each_generator():
    spec = _spec()
    schemas = spec['components']['schemas']
    memory = _schema(spec, 'MemoryDB')

    dart_fields = generate_dart_models.fields_for_schema('MemoryDB', memory, ('Evidence', 'MemoryDB'), schemas)
    dart_evidence = next(field for field in dart_fields if field.wire_name == 'evidence')
    assert dart_evidence.required is False
    assert dart_evidence.dart_type.annotation == 'List<GeneratedEvidence>?'

    swift_type, swift_optional = generate_swift_openapi_types._swift_type(
        memory['properties']['evidence'], required=False
    )
    assert (swift_type, swift_optional) == ('[Evidence]', True)

    typescript_memory = generate_ts_openapi_types.schema_to_ts(memory)
    assert 'evidence?: Array<Evidence>;' in typescript_memory


def test_checked_in_mobile_desktop_windows_and_web_artifacts_share_the_same_mapping():
    spec = _spec()

    assert DART_PATH.read_text(encoding='utf-8') == generate_dart_models.build_output(spec, 'memories')
    assert SWIFT_PATH.read_text(encoding='utf-8') == generate_swift_openapi_types.generate(
        spec, 'docs/api-reference/app-client-openapi.json'
    )

    generated_typescript = generate_ts_openapi_types.generate(spec, 'docs/api-reference/app-client-openapi.json')
    for output in generate_ts_openapi_types.DEFAULT_OUTPUTS:
        assert output.read_text(encoding='utf-8') == generated_typescript


def test_malformed_evidence_is_not_a_valid_v1_wire_row():
    spec = _spec()
    fixtures = json.loads(FIXTURE_PATH.read_text(encoding='utf-8'))
    malformed = copy.deepcopy(fixtures['v1'])
    malformed['evidence'] = [{'source_id': 'missing-required-identity'}]

    with warnings.catch_warnings():
        warnings.simplefilter('ignore', DeprecationWarning)
        validator = Draft202012Validator(_schema(spec, 'MemoryDB'), resolver=RefResolver.from_schema(spec))
    assert list(validator.iter_errors(malformed))

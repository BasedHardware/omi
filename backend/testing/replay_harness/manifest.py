"""Stable v1 case wire format shared with capture writers.

``stages`` selects the boundaries to execute, in pipeline order. Each boundary
contains either ``expect: pass`` or ``expect_stop_stage`` + ``expect_reason``.
Reason patterns are regex searches over sanitized class/site tokens, never
exception messages. Reserved, unimplemented stages cannot have expectations.
``seed_blob_sha256`` lists SHA256 digests of seed files. Optional ``notes``
describes a synthetic mechanism without inventing production evidence.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

SCHEMA_VERSION = 1
STAGES = ('capture_upload', 'admission', 'worker', 'projection', 'final_pass', 'titling', 'episodes', 'privacy_cache')
IMPLEMENTED_STAGES = ('capture_upload', 'admission', 'titling', 'privacy_cache')
_STAGE_SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'oneOf': [
        {'required': ['expect'], 'properties': {'expect': {'const': 'pass'}}},
        {
            'required': ['expect_stop_stage', 'expect_reason'],
            'properties': {
                'expect_stop_stage': {'enum': list(STAGES)},
                'expect_reason': {'type': 'string', 'minLength': 1},
            },
        },
    ],
    'properties': {
        'expect': {'const': 'pass'},
        'expect_stop_stage': {'enum': list(STAGES)},
        'expect_reason': {'type': 'string', 'minLength': 1},
    },
}
JSON_SCHEMA = {
    '$schema': 'https://json-schema.org/draft/2020-12/schema',
    'title': 'Omi replay case v1',
    'type': 'object',
    'additionalProperties': False,
    'required': ['schema_version', 'id', 'tier', 'scrub', 'seed_blob_sha256', 'created', 'prod_evidence', 'stages'],
    'allOf': [
        {'if': {'properties': {'tier': {'const': 'S'}}}, 'then': {'properties': {'stages': {'minProperties': 1}}}},
        {
            'if': {
                'required': ['gate'],
                'properties': {'gate': {'required': ['fixed_by_ref'], 'properties': {'fixed_by_ref': {'const': True}}}},
            },
            'then': {
                'properties': {
                    'stages': {
                        'anyOf': [
                            {'required': [stage], 'properties': {stage: {'required': ['expect_stop_stage']}}}
                            for stage in IMPLEMENTED_STAGES
                        ]
                    }
                }
            },
        },
    ],
    'properties': {
        'schema_version': {'const': SCHEMA_VERSION},
        'id': {'type': 'string', 'pattern': r'^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$'},
        'tier': {'enum': ['S', 'C']},
        'scrub': {'type': 'string', 'minLength': 1},
        'seed_blob_sha256': {
            'type': 'array',
            'uniqueItems': True,
            'items': {'type': 'string', 'pattern': '^[a-f0-9]{64}$'},
        },
        'created': {'type': 'string', 'format': 'date-time'},
        'prod_evidence': {'type': 'object'},
        'gate': {
            'type': 'object',
            'additionalProperties': False,
            'properties': {'fixed_by_ref': {'type': 'boolean'}},
        },
        'expect': {'const': 'pass'},
        'notes': {'type': 'string', 'minLength': 1},
        'stages': {
            'type': 'object',
            'minProperties': 0,
            'additionalProperties': False,
            'properties': {
                stage: {
                    **_STAGE_SCHEMA,
                    'properties': {
                        **_STAGE_SCHEMA['properties'],
                        'expect_stop_stage': {'const': stage},
                        **(
                            {
                                'bound_s': {'type': 'number', 'exclusiveMinimum': 0, 'maximum': 86400},
                                'min_verified_transitions': {'type': 'integer', 'enum': [0, 1000], 'default': 1000},
                            }
                            if stage == 'privacy_cache'
                            else {}
                        ),
                    },
                }
                for stage in IMPLEMENTED_STAGES
            },
        },
    },
}


@dataclass(frozen=True)
class Manifest:
    id: str
    tier: str
    scrub: str
    seed_blob_sha256: list[str]
    created: str
    prod_evidence: dict[str, Any]
    stages: dict[str, dict[str, Any]]
    schema_version: int = SCHEMA_VERSION
    expect: str | None = None
    notes: str | None = None
    gate: dict[str, bool] | None = None

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for optional in ('expect', 'notes', 'gate'):
            if value[optional] is None:
                del value[optional]
        return value


def validate_manifest(value: Any) -> Manifest:
    """Validate without importing any product code, clients or heavy providers."""
    if not isinstance(value, dict):
        raise ValueError('manifest must be an object')
    required = set(JSON_SCHEMA['required'])
    if required - value.keys() or value.keys() - JSON_SCHEMA['properties'].keys():
        raise ValueError('manifest fields do not match schema v1')
    if type(value['schema_version']) is not int or value['schema_version'] != SCHEMA_VERSION:
        raise ValueError('unsupported manifest schema_version')
    if not isinstance(value['id'], str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}', value['id']):
        raise ValueError('invalid case id')
    if value['tier'] not in ('S', 'C') or not isinstance(value['scrub'], str) or not value['scrub'].strip():
        raise ValueError('tier and scrub must be explicit')
    hashes = value['seed_blob_sha256']
    if not isinstance(hashes, list) or any(
        not isinstance(h, str) or not re.fullmatch('[a-f0-9]{64}', h) for h in hashes
    ):
        raise ValueError('invalid seed_blob_sha256')
    if len(set(hashes)) != len(hashes):
        raise ValueError('duplicate seed digest')
    try:
        created = datetime.fromisoformat(value['created'].replace('Z', '+00:00'))
        if created.tzinfo is None:
            raise ValueError('timezone required')
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError('created must be an ISO timestamp with timezone') from error
    if not isinstance(value['prod_evidence'], dict):
        raise ValueError('prod_evidence must be an object')
    if 'expect' in value and value['expect'] != 'pass':
        raise ValueError('invalid top-level expectation')
    if 'notes' in value and (not isinstance(value['notes'], str) or not value['notes'].strip()):
        raise ValueError('notes must be nonempty text')
    if 'gate' in value:
        gate = value['gate']
        if (
            not isinstance(gate, dict)
            or gate.keys() - {'fixed_by_ref'}
            or any(type(flag) is not bool for flag in gate.values())
        ):
            raise ValueError('invalid gate block')
    stages = value['stages']
    if not isinstance(stages, dict) or (not stages and value['tier'] != 'C') or stages.keys() - set(STAGES):
        raise ValueError('stages must select known boundaries')
    if stages.keys() - set(IMPLEMENTED_STAGES):
        raise ValueError('expectations on not_implemented stages are forbidden')
    for stage, expectation in stages.items():
        if not isinstance(expectation, dict):
            raise ValueError('stage expectation must be an object')
        if stage == 'privacy_cache' and 'min_verified_transitions' in expectation:
            minimum = expectation['min_verified_transitions']
            if type(minimum) is not int or minimum not in (0, 1000):
                raise ValueError('privacy min_verified_transitions must be 0 (smoke) or 1000 (qualification)')
            expectation = {key: value for key, value in expectation.items() if key != 'min_verified_transitions'}
        if stage == 'privacy_cache' and 'bound_s' in expectation:
            bound = expectation['bound_s']
            if type(bound) not in (int, float) or not math.isfinite(bound) or not 0 < bound <= 86400:
                raise ValueError('privacy bound_s must be finite and in (0, 86400]')
            expectation = {key: value for key, value in expectation.items() if key != 'bound_s'}
        if expectation == {'expect': 'pass'}:
            continue
        if set(expectation) != {'expect_stop_stage', 'expect_reason'} or expectation['expect_stop_stage'] != stage:
            raise ValueError('stop expectation must name its stage')
        pattern = expectation['expect_reason']
        if not isinstance(pattern, str) or not pattern:
            raise ValueError('expected reason must be a nonempty regex')
        try:
            re.compile(pattern)
        except re.error as error:
            raise ValueError('invalid expected reason regex') from error
        if value.get('expect') == 'pass':
            raise ValueError('pass case cannot expect a stop')
    if value.get('gate', {}).get('fixed_by_ref') and not any('expect_stop_stage' in e for e in stages.values()):
        raise ValueError('fixed_by_ref requires an expected failing stop')
    return Manifest(**value)


@dataclass(frozen=True)
class Case:
    directory: Path
    manifest: Manifest
    corpus: dict[str, Any] = field(repr=False)


def load_case(directory: Path | str) -> Case:
    directory = Path(directory).resolve(strict=True)
    for name in ('manifest.json', 'corpus.json'):
        if directory not in (directory / name).resolve().parents:
            raise ValueError('case document escapes case directory')
    manifest = validate_manifest(json.loads((directory / 'manifest.json').read_text()))
    corpus = json.loads((directory / 'corpus.json').read_text())
    if not isinstance(corpus, dict):
        raise ValueError('corpus must be an object')
    # A declared digest must exist locally; never follow a corpus symlink outside
    # its case directory, and never load a URI or a remote blob as a fallback.
    available = {hashlib.sha256((directory / 'corpus.json').read_bytes()).hexdigest()}
    for subdirectory in ('blobs', 'cassettes'):
        for path in (directory / subdirectory).rglob('*'):
            if directory not in path.resolve().parents:
                raise ValueError('seed blob escapes case directory')
            if path.is_file():
                available.add(hashlib.sha256(path.read_bytes()).hexdigest())
    if set(manifest.seed_blob_sha256) - available:
        raise ValueError('seed blob digest missing or mismatched')
    return Case(directory, manifest, corpus)

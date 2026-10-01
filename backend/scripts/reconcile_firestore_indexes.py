#!/usr/bin/env python3
"""Reconcile the generated Firestore index manifest and wait for READY indexes."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
import urllib.error
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / 'backend'
sys.path.insert(0, str(BACKEND_ROOT))

from database.firestore_index_registry import firebase_index_manifest  # noqa: E402
from database.firestore_query_types import FieldIndexRequirement  # noqa: E402
from scripts import firestore_field_indexes as field_indexes  # noqa: E402

DEFAULT_DATABASE = '(default)'
DEFAULT_TIMEOUT_SECONDS = 900.0
DEFAULT_POLL_INTERVAL_SECONDS = 10.0
DEFAULT_PROPOSAL_TTL_SECONDS = 3600
MAX_PROPOSAL_TTL_SECONDS = 3600
MAX_PROPOSAL_BYTES = 1_000_000

IndexSignature = tuple[str, str, tuple[tuple[str, str], ...]]
CommandRunner = Callable[..., Any]
Clock = Callable[[], datetime]

_GCLOUD_QUERY_SCOPES = {
    'COLLECTION': 'collection',
    'COLLECTION_GROUP': 'collection-group',
}
_GCLOUD_FIELD_CONFIGS = {
    'ASCENDING': 'order=ascending',
    'DESCENDING': 'order=descending',
    'CONTAINS': 'array-config=contains',
}
_FIRESTORE_API_SCOPES = {
    'ANY_API',
    'DATASTORE_MODE_API',
    'MONGODB_COMPATIBLE_API',
}


@dataclass(frozen=True)
class LiveIndex:
    """One Firestore Admin API resource, retained without response-shape aliases."""

    resource_name: str
    signature: IndexSignature
    state: str
    api_scope: str = 'ANY_API'


def _collection_group_from_resource_name(index: Mapping[str, Any]) -> str:
    collection_group = index.get('collectionGroup')
    if isinstance(collection_group, str):
        return collection_group
    name = index.get('name')
    marker = '/collectionGroups/'
    if isinstance(name, str) and marker in name:
        collection_group = name.split(marker, 1)[1].split('/', 1)[0]
        if collection_group:
            return collection_group
    raise ValueError('Firestore index entry must contain collectionGroup or a collectionGroups resource name')


def _index_signature(index: Mapping[str, Any]) -> IndexSignature:
    collection_group = _collection_group_from_resource_name(index)
    query_scope = index.get('queryScope')
    fields = index.get('fields')
    if not isinstance(query_scope, str) or not isinstance(fields, list):
        raise ValueError('Firestore index entry must contain collectionGroup, queryScope, and fields')
    normalized_fields: list[tuple[str, str]] = []
    for field in fields:
        if not isinstance(field, Mapping) or not isinstance(field.get('fieldPath'), str):
            raise ValueError('Firestore index field must contain fieldPath')
        direction = field.get('order') or field.get('arrayConfig')
        if not isinstance(direction, str):
            raise ValueError(f"Firestore index field {field['fieldPath']!r} has no order or arrayConfig")
        normalized_fields.append((field['fieldPath'], direction))
    return (collection_group, query_scope, tuple(normalized_fields))


def expected_index_signatures(manifest: Mapping[str, Any]) -> set[IndexSignature]:
    indexes = manifest.get('indexes')
    if not isinstance(indexes, list):
        raise ValueError('Firestore manifest must contain an indexes list')
    return {_index_signature(index) for index in indexes if isinstance(index, Mapping)}


_SOURCE_ROOT_REGISTRY_SNIPPET = (
    'import json, sys\n'
    'sys.path.insert(0, sys.argv[1])\n'
    'from database.firestore_index_registry import firebase_index_manifest\n'
    'json.dump(firebase_index_manifest(), sys.stdout)\n'
)
SOURCE_ROOT_REGISTRY_TIMEOUT_SECONDS = 60.0
REGISTRY_RELATIVE_PATH = Path('backend') / 'database' / 'firestore_index_registry.py'


def _generated_manifest_at_source_root(source_root: Path) -> dict[str, Any]:
    """Regenerate the manifest from the registry inside a separate checkout.

    The registry is imported in a bounded subprocess of this same interpreter so
    the deploying workflow's registry can validate a manifest checked out at the
    admitted target SHA without importing target code into this process.
    """

    registry_path = source_root / REGISTRY_RELATIVE_PATH
    if not registry_path.is_file():
        raise ValueError(f'{source_root} does not contain {REGISTRY_RELATIVE_PATH}')
    try:
        result = subprocess.run(
            [sys.executable, '-c', _SOURCE_ROOT_REGISTRY_SNIPPET, str(source_root / 'backend')],
            check=False,
            capture_output=True,
            text=True,
            timeout=SOURCE_ROOT_REGISTRY_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError('source-root index registry did not produce a manifest before the bound expired') from exc
    if result.returncode != 0:
        tail = '\n'.join((result.stderr or '').splitlines()[-20:])[-4000:]
        raise ValueError(f'source-root index registry failed to generate a manifest: {tail}')
    try:
        generated = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError('source-root index registry did not emit a JSON manifest') from exc
    if not isinstance(generated, dict):
        raise ValueError('source-root index registry manifest must be an object')
    return generated


_PREREGISTRY_FIELD_MODES = {'order': {'ASCENDING', 'DESCENDING'}, 'arrayConfig': {'CONTAINS'}}


def _validated_preregistry_manifest(manifest_path: Path) -> dict[str, Any]:
    """Structurally validate a manifest committed before the registry existed.

    There is no registry to regenerate from, so the checked-in manifest is the
    declaration of record; every entry is validated (never silently skipped)
    and the manifest is returned as-is so proposal hashes cover it verbatim.
    """

    try:
        loaded = json.loads(manifest_path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        raise ValueError(f'{manifest_path} is not valid JSON') from exc
    if not isinstance(loaded, dict):
        raise ValueError(f'{manifest_path} must contain an object')
    indexes = loaded.get('indexes')
    if not isinstance(indexes, list):
        raise ValueError(f'{manifest_path} must contain an indexes list')
    for position, index in enumerate(indexes):
        scope = f'indexes[{position}]'
        if not isinstance(index, Mapping):
            raise ValueError(f'Firestore manifest {scope} must be an object')
        collection_group = index.get('collectionGroup')
        if not isinstance(collection_group, str) or not collection_group:
            raise ValueError(f'Firestore manifest {scope} must contain a nonempty collectionGroup')
        if not isinstance(index.get('queryScope'), str) or index['queryScope'] not in _GCLOUD_QUERY_SCOPES:
            raise ValueError(f'Firestore manifest {scope} has an unsupported queryScope')
        fields = index.get('fields')
        if not isinstance(fields, list):
            raise ValueError(f'Firestore manifest {scope} must contain a fields list')
        for field in fields:
            if not isinstance(field, Mapping) or not isinstance(field.get('fieldPath'), str) or not field['fieldPath']:
                raise ValueError(f'Firestore manifest {scope} field must contain a nonempty fieldPath')
            present = [mode for mode in _PREREGISTRY_FIELD_MODES if mode in field]
            if (
                len(present) != 1
                or not isinstance(field[present[0]], str)
                or field[present[0]] not in _PREREGISTRY_FIELD_MODES[present[0]]
            ):
                raise ValueError(f'Firestore manifest {scope} field must set exactly one valid order or arrayConfig')
    candidate = dict(loaded)
    candidate.setdefault('fieldOverrides', [])
    field_indexes.expected_field_requirements(candidate)
    print(f'{manifest_path} predates the index registry; validated the declared manifest as-is')
    return loaded


def verify_manifest_source(manifest_path: Path, source_root: Path | None = None) -> dict[str, Any]:
    if source_root is None:
        try:
            loaded = json.loads(manifest_path.read_text(encoding='utf-8'))
        except json.JSONDecodeError as exc:
            raise ValueError(f'{manifest_path} is not valid JSON') from exc
        if not isinstance(loaded, dict):
            raise ValueError(f'{manifest_path} must contain an object')
        generated = firebase_index_manifest()
        if loaded != generated:
            raise ValueError('firestore.indexes.json is not generated from the repository index registry')
        return generated

    source_root = source_root.resolve()
    expected_manifest = (source_root / 'firestore.indexes.json').resolve()
    if manifest_path.resolve() != expected_manifest:
        raise ValueError(f'--source-root requires the manifest at {expected_manifest}')
    if not (source_root / REGISTRY_RELATIVE_PATH).is_file():
        if not manifest_path.is_file():
            print(f'{manifest_path} predates the index registry and declares no manifest; nothing to verify')
            return {'indexes': [], 'fieldOverrides': []}
        return _validated_preregistry_manifest(manifest_path)
    try:
        loaded = json.loads(manifest_path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        raise ValueError(f'{manifest_path} is not valid JSON') from exc
    if not isinstance(loaded, dict):
        raise ValueError(f'{manifest_path} must contain an object')
    generated = _generated_manifest_at_source_root(source_root)
    if loaded != generated:
        raise ValueError('firestore.indexes.json is not generated from the repository index registry')
    return generated


def expected_field_requirements(manifest: Mapping[str, Any]) -> tuple[FieldIndexRequirement, ...]:
    candidate = manifest
    if 'fieldOverrides' not in manifest:
        candidate = dict(manifest)
        candidate['fieldOverrides'] = []
    return field_indexes.expected_field_requirements(candidate)


def gcloud_create_index_command(*, project: str, database: str, signature: IndexSignature) -> list[str]:
    """Build the Firestore Admin API create command for one manifest signature."""

    collection_group, query_scope, fields = signature
    try:
        gcloud_query_scope = _GCLOUD_QUERY_SCOPES[query_scope]
    except KeyError as exc:
        raise ValueError(f'unsupported Firestore query scope for gcloud provisioning: {query_scope!r}') from exc
    command = [
        'gcloud',
        'firestore',
        'indexes',
        'composite',
        'create',
        f'--project={project}',
        f'--database={database}',
        f'--collection-group={collection_group}',
        f'--query-scope={gcloud_query_scope}',
    ]
    for field_path, direction in fields:
        try:
            field_config = _GCLOUD_FIELD_CONFIGS[direction]
        except KeyError as exc:
            raise ValueError(
                f'unsupported Firestore field configuration for gcloud provisioning: {direction!r}'
            ) from exc
        command.append(f'--field-config=field-path={field_path},{field_config}')
    return [*command, '--async', '--quiet']


READ_RETRY_DELAYS_SECONDS = (2.0, 5.0, 10.0)
_READ_LIST_TRANSIENT_MARKERS = (
    'unavailable',
    'deadline_exceeded',
    'resource_exhausted',
    '429',
    '500',
    '502',
    '503',
    '504',
    'connection reset',
    'timed out',
)
_READ_LIST_PERMANENT_MARKERS = ('401', '403', '404')
_READ_LIST_TIMEOUT_SECONDS = 120.0


def _listing_failure_is_transient(stderr: str) -> bool:
    lowered = stderr.casefold()
    if any(marker in lowered for marker in _READ_LIST_PERMANENT_MARKERS):
        return False
    return any(marker in lowered for marker in _READ_LIST_TRANSIENT_MARKERS)


def list_live_indexes(
    *,
    project: str,
    database: str,
    runner: CommandRunner = subprocess.run,
    retry_read: bool = False,
    sleep: Callable[[float], None] = time.sleep,
) -> list[LiveIndex]:
    """Read live Admin API resources without normalizing distinct index shapes."""
    command = [
        'gcloud',
        'firestore',
        'indexes',
        'composite',
        'list',
        f'--project={project}',
        f'--database={database}',
        '--format=json',
    ]
    result = None
    for attempt in range(len(READ_RETRY_DELAYS_SECONDS) + 1):
        kwargs: dict[str, Any] = dict(cwd=ROOT, check=False, capture_output=True, text=True)
        if retry_read:
            kwargs['timeout'] = _READ_LIST_TIMEOUT_SECONDS
        try:
            result = runner(command, **kwargs)
        except (subprocess.TimeoutExpired, TimeoutError, urllib.error.URLError) as exc:
            transient = isinstance(exc, (subprocess.TimeoutExpired, TimeoutError)) or _field_read_is_transient(exc)
            if retry_read and transient and attempt < len(READ_RETRY_DELAYS_SECONDS):
                sleep(READ_RETRY_DELAYS_SECONDS[attempt])
                continue
            raise RuntimeError('Firestore composite-index listing failed') from exc
        if result.returncode == 0:
            break
        if (
            retry_read
            and attempt < len(READ_RETRY_DELAYS_SECONDS)
            and _listing_failure_is_transient(getattr(result, 'stderr', '') or '')
        ):
            sleep(READ_RETRY_DELAYS_SECONDS[attempt])
            continue
        raise RuntimeError('Firestore composite-index listing failed')
    assert result is not None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError('Firestore composite-index listing did not return JSON') from exc
    if not isinstance(payload, list):
        raise RuntimeError('Firestore composite-index listing did not return a list')
    live_indexes: list[LiveIndex] = []
    for position, index in enumerate(payload):
        if not isinstance(index, Mapping):
            raise RuntimeError(f'Firestore composite-index inventory entry {position} is not an object')
        try:
            signature = _index_signature(index)
        except ValueError as exc:
            raise RuntimeError(
                f'Firestore composite-index inventory entry {position} cannot be represented safely'
            ) from exc
        resource_name = index.get('name')
        if not isinstance(resource_name, str) or not resource_name:
            raise RuntimeError(f'Firestore composite-index inventory entry {position} has no resource name')
        api_scope = index.get('apiScope', 'ANY_API')
        if not isinstance(api_scope, str) or api_scope not in _FIRESTORE_API_SCOPES:
            raise RuntimeError(f'Firestore composite-index inventory entry {position} has an invalid API scope')
        state = index.get('state')
        if not isinstance(state, str) or not state:
            raise RuntimeError(f'Firestore composite-index inventory entry {position} has no state')
        live_indexes.append(
            LiveIndex(resource_name=resource_name, signature=signature, api_scope=api_scope, state=state)
        )
    return live_indexes


def expected_index_resource_prefix(*, project: str, database: str, signature: IndexSignature) -> str:
    collection_group = signature[0]
    return f'projects/{project}/databases/{database}/collectionGroups/{collection_group}/indexes/'


def _matches_expected_resource_identity(
    live_index: LiveIndex, *, project: str, database: str, signature: IndexSignature
) -> bool:
    prefix = expected_index_resource_prefix(project=project, database=database, signature=signature)
    identifier = live_index.resource_name.removeprefix(prefix)
    return live_index.resource_name.startswith(prefix) and bool(identifier) and '/' not in identifier


def _implicit_terminal_document_id_alias(signature: IndexSignature) -> IndexSignature | None:
    """Return the historic Firebase-manifest shape for an Admin API implicit terminal order."""
    fields = signature[2]
    if (
        len(fields) > 1
        and fields[-1][0] == '__name__'
        and fields[-1][1] == fields[-2][1]
        and fields[-1][1] in {'ASCENDING', 'DESCENDING'}
    ):
        return (signature[0], signature[1], fields[:-1])
    return None


def expected_index_states(
    *,
    expected: Iterable[IndexSignature],
    live_indexes: Iterable[LiveIndex],
    project: str,
    database: str,
    allow_implicit_terminal_document_id_alias: bool = False,
) -> dict[IndexSignature, str]:
    """Return exact Admin API readiness states, failing closed on any ambiguity."""
    states: dict[IndexSignature, str] = {}
    inventory = list(live_indexes)
    for signature in set(expected):
        matches = [
            index
            for index in inventory
            if index.api_scope == 'ANY_API'
            and (
                index.signature == signature
                or (
                    allow_implicit_terminal_document_id_alias
                    and _implicit_terminal_document_id_alias(index.signature) == signature
                )
            )
            and _matches_expected_resource_identity(index, project=project, database=database, signature=signature)
        ]
        if not matches:
            states[signature] = 'MISSING'
        elif len(matches) != 1:
            states[signature] = 'AMBIGUOUS'
        else:
            states[signature] = matches[0].state
    return states


def unmanaged_live_indexes(
    *,
    expected: Iterable[IndexSignature],
    live_indexes: Iterable[LiveIndex],
) -> list[LiveIndex]:
    """Return live composite indexes the repository manifest does not declare.

    Reconciliation is create-only by design: an index dropped from the manifest,
    or created by hand in the console during an incident, survives forever with
    nothing pointing at it. Deleting it automatically would be an outage
    primitive -- a still-serving older Cloud Run revision can need an index the
    new manifest no longer declares -- so this reports drift instead of acting
    on it, and deletion stays a deliberate human operation.
    """

    expected_set = set(expected)
    unmanaged: list[LiveIndex] = []
    for index in live_indexes:
        if index.api_scope != 'ANY_API':
            continue
        if index.signature in expected_set:
            continue
        alias = _implicit_terminal_document_id_alias(index.signature)
        if alias is not None and alias in expected_set:
            continue
        unmanaged.append(index)
    return unmanaged


def report_unmanaged_live_indexes(
    *,
    expected: Iterable[IndexSignature],
    live_indexes: Iterable[LiveIndex],
) -> list[LiveIndex]:
    """Surface create-only drift as non-blocking annotations on an existing gate."""

    unmanaged = unmanaged_live_indexes(expected=expected, live_indexes=live_indexes)
    for index in sorted(unmanaged, key=lambda live: live.resource_name):
        print(
            '::warning title=Unmanaged Firestore index::'
            f'{format_signature(index.signature)} is serving but is not declared by '
            'firestore.indexes.json; reconciliation is create-only and will never remove it'
        )
    return unmanaged


def format_signature(signature: IndexSignature) -> str:
    collection_group, query_scope, fields = signature
    field_text = ', '.join(f'{field}:{direction}' for field, direction in fields)
    return f'{query_scope}/{collection_group} ({field_text})'


def signature_manifest_entry(signature: IndexSignature) -> dict[str, Any]:
    """Return the exact Firebase-manifest shape used for create-only proposals."""

    collection_group, query_scope, fields = signature
    manifest_fields: list[dict[str, str]] = []
    for field_path, direction in fields:
        field = {'fieldPath': field_path}
        if direction in {'ASCENDING', 'DESCENDING'}:
            field['order'] = direction
        else:
            field['arrayConfig'] = direction
        manifest_fields.append(field)
    return {
        'collectionGroup': collection_group,
        'queryScope': query_scope,
        'fields': manifest_fields,
    }


def _canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _utc_timestamp(value: datetime) -> str:
    if value.utcoffset() is None:
        raise ValueError('proposal clock must return a timezone-aware datetime')
    return value.astimezone(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def _normalize_source_commit(source_commit: str) -> str:
    normalized_commit = source_commit.strip().lower()
    if len(normalized_commit) not in {40, 64} or any(
        character not in '0123456789abcdef' for character in normalized_commit
    ):
        raise ValueError('source_commit must be a full hexadecimal Git object id')
    return normalized_commit


def _validate_proposal_ttl(ttl_seconds: int) -> None:
    if ttl_seconds <= 0 or ttl_seconds > MAX_PROPOSAL_TTL_SECONDS:
        raise ValueError(f'proposal TTL must be between 1 and {MAX_PROPOSAL_TTL_SECONDS} seconds')


def _field_override_key(override: Mapping[str, Any]) -> tuple[str, str]:
    return (override['collectionGroup'], override['fieldPath'])


def write_schema_proposal(
    *,
    output_path: Path,
    project: str,
    database: str,
    source_commit: str,
    manifest: Mapping[str, Any],
    states: Mapping[IndexSignature, str],
    ttl_seconds: int,
    field_states: Mapping[tuple[str, str], str] | None = None,
    clock: Clock = lambda: datetime.now(timezone.utc),
) -> dict[str, Any]:
    """Write a redacted, deterministic-input proposal for a human-approved follow-up."""

    normalized_commit = _normalize_source_commit(source_commit)
    _validate_proposal_ttl(ttl_seconds)

    blocking = [
        {
            'signature': signature_manifest_entry(signature),
            'state': state,
        }
        for signature, state in sorted(states.items())
        if state != 'READY'
    ]
    create_indexes = [
        signature_manifest_entry(signature) for signature, state in sorted(states.items()) if state == 'MISSING'
    ]
    field_states = field_states or {}
    overrides = {
        _field_override_key(override): override
        for override in manifest.get('fieldOverrides', [])
        if isinstance(override, Mapping) and override.get('indexes')
    }
    unknown_fields = sorted(key for key in field_states if key not in overrides)
    if unknown_fields:
        raise ValueError(f'field states reference undeclared manifest overrides: {unknown_fields}')
    blocking_field_indexes = [
        {'override': overrides[key], 'state': field_states[key]}
        for key in sorted(field_states)
        if field_states[key] != 'READY'
    ]
    create_field_indexes = [overrides[key] for key in sorted(field_states) if field_states[key] == 'MISSING']
    plan_input = {
        'schema_version': 2,
        'target': {'project': project, 'database': database},
        'source': {
            'commit': normalized_commit,
            'manifest_sha256': _canonical_sha256(manifest),
        },
        'create_indexes': create_indexes,
        'blocking_indexes': blocking,
        'create_field_indexes': create_field_indexes,
        'blocking_field_indexes': blocking_field_indexes,
        'ttl_seconds': ttl_seconds,
    }
    created_at = clock()
    expires_at = created_at + timedelta(seconds=ttl_seconds)
    input_sha256 = _canonical_sha256(plan_input)
    validity = {
        'created_at': _utc_timestamp(created_at),
        'expires_at': _utc_timestamp(expires_at),
        'ttl_seconds': ttl_seconds,
    }
    proposal_content = {
        **plan_input,
        'kind': 'firestore-index-create-proposal',
        'status': 'BLOCKED',
        'input_sha256': input_sha256,
        'validity': validity,
    }
    proposal = {**proposal_content, 'proposal_sha256': _canonical_sha256(proposal_content)}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(f'.{output_path.name}.tmp')
    temporary_path.write_text(json.dumps(proposal, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    temporary_path.replace(output_path)
    return proposal


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], *, scope: str) -> None:
    actual = set(value)
    if actual != expected:
        raise ValueError(f'{scope} keys do not match the proposal schema')


def _parse_utc_timestamp(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith('Z'):
        raise ValueError(f'{field} must be a UTC timestamp')
    try:
        parsed = datetime.fromisoformat(value[:-1] + '+00:00')
    except ValueError as exc:
        raise ValueError(f'{field} must be a valid UTC timestamp') from exc
    return parsed.astimezone(timezone.utc)


def _validated_proposal_signature(value: Any, *, scope: str) -> IndexSignature:
    if not isinstance(value, Mapping):
        raise ValueError(f'{scope} must be an index signature object')
    signature = _index_signature(value)
    if dict(value) != signature_manifest_entry(signature):
        raise ValueError(f'{scope} must use the exact Firebase manifest signature shape')
    return signature


def validate_schema_proposal(
    *,
    proposal_path: Path,
    manifest_path: Path,
    project: str,
    database: str,
    source_commit: str,
    ttl_seconds: int,
    source_root: Path | None = None,
    clock: Clock = lambda: datetime.now(timezone.utc),
) -> dict[str, Any]:
    """Validate a proposal artifact before it can cross the workflow boundary."""

    if proposal_path.is_symlink() or not proposal_path.is_file():
        raise ValueError('proposal path must be a regular file, not a symlink')
    if proposal_path.stat().st_size > MAX_PROPOSAL_BYTES:
        raise ValueError(f'proposal file exceeds the {MAX_PROPOSAL_BYTES}-byte limit')
    try:
        loaded = json.loads(proposal_path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        raise ValueError('proposal file is not valid JSON') from exc
    if not isinstance(loaded, dict):
        raise ValueError('proposal file must contain an object')

    _validate_proposal_ttl(ttl_seconds)
    expected_commit = _normalize_source_commit(source_commit)
    manifest = verify_manifest_source(manifest_path, source_root=source_root)
    expected_signatures = expected_index_signatures(manifest)
    _require_exact_keys(
        loaded,
        {
            'schema_version',
            'kind',
            'status',
            'target',
            'source',
            'create_indexes',
            'blocking_indexes',
            'create_field_indexes',
            'blocking_field_indexes',
            'ttl_seconds',
            'input_sha256',
            'validity',
            'proposal_sha256',
        },
        scope='proposal',
    )
    if loaded['schema_version'] != 2:
        raise ValueError('proposal schema_version must be 2')
    if loaded['kind'] != 'firestore-index-create-proposal' or loaded['status'] != 'BLOCKED':
        raise ValueError('proposal kind or status is invalid')
    if loaded['ttl_seconds'] != ttl_seconds:
        raise ValueError('proposal TTL does not match the workflow contract')

    target = loaded['target']
    if not isinstance(target, Mapping):
        raise ValueError('proposal target must be an object')
    _require_exact_keys(target, {'project', 'database'}, scope='proposal target')
    if target != {'project': project, 'database': database}:
        raise ValueError('proposal target does not match the workflow target')

    source = loaded['source']
    if not isinstance(source, Mapping):
        raise ValueError('proposal source must be an object')
    _require_exact_keys(source, {'commit', 'manifest_sha256'}, scope='proposal source')
    if source.get('commit') != expected_commit:
        raise ValueError('proposal source commit does not match the approved commit')
    if source.get('manifest_sha256') != _canonical_sha256(manifest):
        raise ValueError('proposal manifest hash does not match the approved manifest')

    create_entries = loaded['create_indexes']
    blocking_entries = loaded['blocking_indexes']
    if not isinstance(create_entries, list) or not isinstance(blocking_entries, list):
        raise ValueError('proposal must contain create_indexes and blocking_indexes lists')
    create_signatures = [
        _validated_proposal_signature(entry, scope=f'create_indexes[{index}]')
        for index, entry in enumerate(create_entries)
    ]
    if len(create_signatures) != len(set(create_signatures)):
        raise ValueError('proposal create_indexes contains duplicates')

    blocking_signatures: list[IndexSignature] = []
    missing_signatures: set[IndexSignature] = set()
    for index, entry in enumerate(blocking_entries):
        if not isinstance(entry, Mapping):
            raise ValueError(f'blocking_indexes[{index}] must be an object')
        _require_exact_keys(entry, {'signature', 'state'}, scope=f'blocking_indexes[{index}]')
        signature = _validated_proposal_signature(entry['signature'], scope=f'blocking_indexes[{index}].signature')
        state = entry['state']
        if (
            not isinstance(state, str)
            or not state
            or state == 'READY'
            or len(state) > 64
            or state != state.upper()
            or not state.replace('_', '').isalnum()
        ):
            raise ValueError(f'blocking_indexes[{index}].state must be a non-READY state')
        blocking_signatures.append(signature)
        if state == 'MISSING':
            missing_signatures.add(signature)
    if len(blocking_signatures) != len(set(blocking_signatures)):
        raise ValueError('proposal blocking_indexes contains duplicates')
    if not set(blocking_signatures).issubset(expected_signatures):
        raise ValueError('proposal blocking indexes are not all declared by the approved manifest')
    if set(create_signatures) != missing_signatures:
        raise ValueError('proposal create_indexes must exactly match the MISSING blocking signatures')

    additive_hashes: dict[str, dict[str, Any]] = {}
    for index, override in enumerate(manifest.get('fieldOverrides', [])):
        if not isinstance(override, Mapping):
            raise ValueError(f'manifest fieldOverrides[{index}] must be an object')
        if isinstance(override.get('indexes'), list) and override['indexes']:
            additive_hashes[_canonical_sha256(override)] = dict(override)

    def _validated_proposal_field_override(value: Any, *, scope: str) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise ValueError(f'{scope} must be a field override object')
        hashed = _canonical_sha256(value)
        if hashed not in additive_hashes:
            raise ValueError(f'{scope} is not an additive field override in the approved manifest')
        return additive_hashes[hashed]

    create_field_entries = loaded['create_field_indexes']
    blocking_field_entries = loaded['blocking_field_indexes']
    if not isinstance(create_field_entries, list) or not isinstance(blocking_field_entries, list):
        raise ValueError('proposal must contain create_field_indexes and blocking_field_indexes lists')
    create_field_keys = [
        _field_override_key(_validated_proposal_field_override(entry, scope=f'create_field_indexes[{index}]'))
        for index, entry in enumerate(create_field_entries)
    ]
    if len(create_field_keys) != len(set(create_field_keys)):
        raise ValueError('proposal create_field_indexes contains duplicates')

    blocking_field_keys: list[tuple[str, str]] = []
    missing_field_keys: set[tuple[str, str]] = set()
    for index, entry in enumerate(blocking_field_entries):
        if not isinstance(entry, Mapping):
            raise ValueError(f'blocking_field_indexes[{index}] must be an object')
        _require_exact_keys(entry, {'override', 'state'}, scope=f'blocking_field_indexes[{index}]')
        override = _validated_proposal_field_override(
            entry['override'], scope=f'blocking_field_indexes[{index}].override'
        )
        state = entry['state']
        if (
            not isinstance(state, str)
            or not state
            or state == 'READY'
            or len(state) > 64
            or state != state.upper()
            or not state.replace('_', '').isalnum()
        ):
            raise ValueError(f'blocking_field_indexes[{index}].state must be a non-READY state')
        key = _field_override_key(override)
        blocking_field_keys.append(key)
        if state == 'MISSING':
            missing_field_keys.add(key)
    if len(blocking_field_keys) != len(set(blocking_field_keys)):
        raise ValueError('proposal blocking_field_indexes contains duplicates')
    if set(create_field_keys) != missing_field_keys:
        raise ValueError('proposal create_field_indexes must exactly match the MISSING blocking field overrides')
    if not create_field_keys and not blocking_entries and not blocking_field_entries:
        raise ValueError('proposal must contain at least one blocking index')

    validity = loaded['validity']
    if not isinstance(validity, Mapping):
        raise ValueError('proposal validity must be an object')
    _require_exact_keys(validity, {'created_at', 'expires_at', 'ttl_seconds'}, scope='proposal validity')
    if validity.get('ttl_seconds') != ttl_seconds:
        raise ValueError('proposal validity TTL does not match the workflow contract')
    created_at = _parse_utc_timestamp(validity.get('created_at'), field='proposal created_at')
    expires_at = _parse_utc_timestamp(validity.get('expires_at'), field='proposal expires_at')
    if expires_at - created_at != timedelta(seconds=ttl_seconds):
        raise ValueError('proposal validity window does not match its TTL')
    now = clock()
    if now.utcoffset() is None:
        raise ValueError('proposal validation clock must return a timezone-aware datetime')
    now = now.astimezone(timezone.utc)
    if created_at > now + timedelta(minutes=5) or expires_at <= now:
        raise ValueError('proposal is expired or has an invalid creation time')

    plan_input = {
        key: loaded[key]
        for key in (
            'schema_version',
            'target',
            'source',
            'create_indexes',
            'blocking_indexes',
            'create_field_indexes',
            'blocking_field_indexes',
            'ttl_seconds',
        )
    }
    if loaded['input_sha256'] != _canonical_sha256(plan_input):
        raise ValueError('proposal input hash is invalid')
    proposal_content = {key: value for key, value in loaded.items() if key != 'proposal_sha256'}
    if loaded['proposal_sha256'] != _canonical_sha256(proposal_content):
        raise ValueError('proposal hash is invalid')
    return loaded


_FIELD_READ_TRANSIENT_STATUSES = {429, 500, 502, 503, 504}


def _field_read_is_transient(exc: BaseException | None) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in _FIELD_READ_TRANSIENT_STATUSES
    if isinstance(exc, (urllib.error.URLError, TimeoutError)):
        return True
    if isinstance(exc, field_indexes.FieldIndexError):
        return _field_read_is_transient(exc.__cause__)
    return False


def _retrying_field_read_request(field_request, sleep: Callable[[float], None]):
    """Retry transient field-config GETs; mutations and permanent errors fail at once."""

    def wrapped(method: str, url: str, payload: Mapping[str, Any] | None = None, **kwargs):
        attempt = 0
        while True:
            try:
                return field_request(method, url, payload, **kwargs)
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, field_indexes.FieldIndexError) as exc:
                if method != 'GET' or not _field_read_is_transient(exc) or attempt >= len(READ_RETRY_DELAYS_SECONDS):
                    raise
                sleep(READ_RETRY_DELAYS_SECONDS[attempt])
                attempt += 1

    return wrapped


def live_field_requirement_states(
    *,
    requirements: Iterable,
    project: str,
    database: str,
    field_request,
) -> dict[tuple[str, str], str]:
    """Read each additive field requirement's live state through the REST seam."""

    return field_indexes.expected_field_states(
        requirements=tuple(requirements),
        project=project,
        database=database,
        request=field_request,
    )


def check_indexes_and_write_proposal(
    *,
    expected: Iterable[IndexSignature],
    manifest: Mapping[str, Any],
    field_requirements: Iterable = (),
    project: str,
    database: str,
    proposal_output: Path,
    source_commit: str,
    proposal_ttl_seconds: int,
    runner: CommandRunner = subprocess.run,
    field_request=field_indexes.field_api_request,
    sleep: Callable[[float], None] = time.sleep,
    clock: Clock = lambda: datetime.now(timezone.utc),
) -> None:
    """Check one live snapshot and emit a bounded proposal when readiness fails."""

    expected_set = set(expected)
    live_indexes = list_live_indexes(project=project, database=database, runner=runner, retry_read=True, sleep=sleep)
    states = expected_index_states(
        expected=expected_set,
        live_indexes=live_indexes,
        project=project,
        database=database,
    )
    report_unmanaged_live_indexes(expected=expected_set, live_indexes=live_indexes)
    field_states = live_field_requirement_states(
        requirements=field_requirements,
        project=project,
        database=database,
        field_request=_retrying_field_read_request(field_request, sleep),
    )
    pending = {signature: state for signature, state in states.items() if state != 'READY'}
    pending_fields = {key: state for key, state in field_states.items() if state != 'READY'}
    if not pending and not pending_fields:
        print(
            f'Firestore index readiness passed: {len(expected_set)} composite indexes '
            f'and {len(field_states)} field overrides READY'
        )
        return

    write_schema_proposal(
        output_path=proposal_output,
        project=project,
        database=database,
        source_commit=source_commit,
        manifest=manifest,
        states=states,
        field_states=field_states,
        ttl_seconds=proposal_ttl_seconds,
        clock=clock,
    )
    details = '; '.join(f'{format_signature(signature)}={state}' for signature, state in sorted(pending.items()))
    field_details = '; '.join(f'{key[0]}.{key[1]}={state}' for key, state in sorted(pending_fields.items()))
    message = f'Firestore index readiness failed; proposal written to {proposal_output}: {details}'
    if field_details:
        message = f'{message}; fields: {field_details}'
    raise RuntimeError(message)


def missing_index_signatures(
    *,
    expected: Iterable[IndexSignature],
    live_indexes: Iterable[LiveIndex],
    project: str,
    database: str,
    allow_implicit_terminal_document_id_alias: bool = False,
) -> set[IndexSignature]:
    """Return manifest requirements absent from the Firestore Admin API inventory."""
    states = expected_index_states(
        expected=expected,
        live_indexes=live_indexes,
        project=project,
        database=database,
        allow_implicit_terminal_document_id_alias=allow_implicit_terminal_document_id_alias,
    )
    return {signature for signature, state in states.items() if state == 'MISSING'}


def provision_missing_indexes(
    *,
    expected: Iterable[IndexSignature],
    project: str,
    database: str,
    runner: CommandRunner = subprocess.run,
) -> set[IndexSignature]:
    """Create only manifest entries absent from the live Firestore inventory."""

    missing = missing_index_signatures(
        expected=expected,
        live_indexes=list_live_indexes(
            project=project,
            database=database,
            runner=runner,
        ),
        project=project,
        database=database,
    )
    for signature in sorted(missing):
        result = runner(
            gcloud_create_index_command(project=project, database=database, signature=signature),
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 and 'already_exists' not in (getattr(result, 'stderr', '') or '').casefold():
            raise RuntimeError(f'Firestore composite-index provisioning failed: {format_signature(signature)}')
    return missing


def wait_for_indexes(
    *,
    expected: Iterable[IndexSignature],
    project: str,
    database: str,
    timeout_seconds: float,
    poll_interval_seconds: float,
    allow_implicit_terminal_document_id_alias: bool = False,
    field_requirements: Iterable = (),
    runner: CommandRunner = subprocess.run,
    field_request=field_indexes.field_api_request,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> None:
    if timeout_seconds <= 0:
        raise ValueError('timeout_seconds must be positive')
    if poll_interval_seconds <= 0:
        raise ValueError('poll_interval_seconds must be positive')
    expected_set = set(expected)
    field_requirements = tuple(field_requirements)
    deadline = monotonic() + timeout_seconds
    while True:
        states = expected_index_states(
            expected=expected_set,
            live_indexes=list_live_indexes(
                project=project,
                database=database,
                runner=runner,
            ),
            project=project,
            database=database,
            allow_implicit_terminal_document_id_alias=allow_implicit_terminal_document_id_alias,
        )
        pending = {
            signature: states.get(signature, 'MISSING')
            for signature in expected_set
            if states.get(signature) != 'READY'
        }
        field_states = live_field_requirement_states(
            requirements=field_requirements,
            project=project,
            database=database,
            field_request=field_request,
        )
        pending_fields = {key: state for key, state in field_states.items() if state != 'READY'}
        if not pending and not pending_fields:
            print(
                f'Firestore index readiness passed: {len(expected_set)} composite indexes '
                f'and {len(field_states)} field overrides READY'
            )
            return
        if monotonic() >= deadline:
            details = '; '.join(
                f'{format_signature(signature)}={state}' for signature, state in sorted(pending.items())
            )
            field_details = '; '.join(f'{key[0]}.{key[1]}={state}' for key, state in sorted(pending_fields.items()))
            message = f'Firestore indexes did not become READY before timeout: {details}'
            if field_details:
                message = f'{message}; fields: {field_details}'
            raise RuntimeError(message)
        sleep(poll_interval_seconds)


def reconcile(
    *,
    project: str,
    database: str,
    manifest_path: Path,
    timeout_seconds: float,
    poll_interval_seconds: float,
    check_only: bool = False,
    dry_run: bool = False,
    provision_missing: bool = False,
    proposal_output: Path | None = None,
    source_commit: str | None = None,
    proposal_ttl_seconds: int = DEFAULT_PROPOSAL_TTL_SECONDS,
    source_root: Path | None = None,
    runner: CommandRunner = subprocess.run,
    field_request=field_indexes.field_api_request,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    clock: Clock = lambda: datetime.now(timezone.utc),
) -> None:
    if sum((check_only, dry_run, provision_missing)) > 1:
        raise ValueError('--check-only, --dry-run, and --provision-missing cannot be combined')
    if source_root is not None and not check_only:
        raise ValueError('--source-root is only valid with --check-only or --validate-proposal')
    if check_only:
        if proposal_output is None or not source_commit:
            raise ValueError('--check-only requires --proposal-output and --source-commit')
        _normalize_source_commit(source_commit)
        _validate_proposal_ttl(proposal_ttl_seconds)
    elif proposal_output is not None or source_commit is not None:
        raise ValueError('--proposal-output and --source-commit require --check-only')
    manifest = verify_manifest_source(manifest_path, source_root=source_root)
    expected = expected_index_signatures(manifest)
    field_requirements = expected_field_requirements(manifest)
    if dry_run:
        live_indexes = list_live_indexes(
            project=project,
            database=database,
            runner=runner,
        )
        missing = missing_index_signatures(
            expected=expected,
            live_indexes=live_indexes,
            project=project,
            database=database,
        )
        for signature in sorted(missing):
            print(f'Firestore index provisioning dry run: would create {format_signature(signature)}')
        field_states = live_field_requirement_states(
            requirements=field_requirements,
            project=project,
            database=database,
            field_request=field_request,
        )
        for key, state in sorted(field_states.items()):
            print(f'Firestore field override dry run: {key[0]}.{key[1]} is {state}')
        report_unmanaged_live_indexes(expected=expected, live_indexes=live_indexes)
        return
    if check_only:
        assert proposal_output is not None and source_commit is not None
        check_indexes_and_write_proposal(
            expected=expected,
            manifest=manifest,
            field_requirements=field_requirements,
            project=project,
            database=database,
            proposal_output=proposal_output,
            source_commit=source_commit,
            proposal_ttl_seconds=proposal_ttl_seconds,
            runner=runner,
            field_request=field_request,
            sleep=sleep,
            clock=clock,
        )
        return
    if provision_missing:
        provision_missing_indexes(expected=expected, project=project, database=database, runner=runner)
        field_indexes.provision_field_requirements(
            requirements=field_requirements,
            project=project,
            database=database,
            request=field_request,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            sleep=sleep,
            monotonic=monotonic,
        )
    wait_for_indexes(
        expected=expected,
        field_requirements=field_requirements,
        project=project,
        database=database,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
        runner=runner,
        field_request=field_request,
        sleep=sleep,
        monotonic=monotonic,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--database', default=DEFAULT_DATABASE)
    parser.add_argument('--manifest', type=Path, default=ROOT / 'firestore.indexes.json')
    parser.add_argument('--timeout-seconds', type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument('--poll-interval-seconds', type=float, default=DEFAULT_POLL_INTERVAL_SECONDS)
    mutation_mode = parser.add_mutually_exclusive_group()
    mutation_mode.add_argument(
        '--provision-missing',
        action='store_true',
        help='create manifest entries missing from the Firestore Admin API inventory with gcloud',
    )
    mutation_mode.add_argument(
        '--check-only',
        action='store_true',
        help='perform no writes and fail unless every manifest index is READY',
    )
    parser.add_argument('--proposal-output', type=Path)
    parser.add_argument('--validate-proposal', type=Path)
    parser.add_argument('--source-commit')
    parser.add_argument(
        '--source-root',
        type=Path,
        help='read the manifest and index registry from this checked-out source tree instead of the script\'s own',
    )
    parser.add_argument('--proposal-ttl-seconds', type=int, default=DEFAULT_PROPOSAL_TTL_SECONDS)
    parser.add_argument(
        '--dry-run', action='store_true', help='validate the manifest and print the no-write reconciliation plan'
    )
    args = parser.parse_args()
    try:
        if args.validate_proposal is not None:
            if args.check_only or args.provision_missing or args.dry_run or args.proposal_output is not None:
                raise ValueError('--validate-proposal cannot be combined with reconciliation modes')
            if not args.source_commit:
                raise ValueError('--validate-proposal requires --source-commit')
            validate_schema_proposal(
                proposal_path=args.validate_proposal,
                manifest_path=args.manifest.resolve(),
                project=args.project,
                database=args.database,
                source_commit=args.source_commit,
                ttl_seconds=args.proposal_ttl_seconds,
                source_root=args.source_root.resolve() if args.source_root else None,
            )
            print('Firestore schema proposal validation passed')
            return 0
        if not (args.check_only or args.dry_run or args.provision_missing):
            raise ValueError('choose one reconciliation mode: --check-only, --dry-run, or --provision-missing')
        reconcile(
            project=args.project,
            database=args.database,
            manifest_path=args.manifest.resolve(),
            timeout_seconds=args.timeout_seconds,
            poll_interval_seconds=args.poll_interval_seconds,
            check_only=args.check_only,
            dry_run=args.dry_run,
            provision_missing=args.provision_missing,
            proposal_output=args.proposal_output.resolve() if args.proposal_output else None,
            source_commit=args.source_commit,
            proposal_ttl_seconds=args.proposal_ttl_seconds,
            source_root=args.source_root.resolve() if args.source_root else None,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
"""Shared additive single-field index reconciliation over the Firestore Admin REST API.

``gcloud firestore indexes fields update`` cannot express the collection-group
query scope, so field requirements are reconciled through ``fields.patch``
with ``updateMask=indexConfig``. Every write is a union of the live effective
configuration and the declared override: the API replaces ``indexes``
wholesale, so any live mode omitted from the patch would be deleted.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / 'backend'
sys.path.insert(0, str(BACKEND_ROOT))

from database.firestore_query_types import FieldIndexRequirement  # noqa: E402

FIRESTORE_ADMIN_API = 'https://firestore.googleapis.com/v1'
_FIELD_RESOURCE = re.compile(
    r'^projects/(?P<project>[^/]+)/databases/(?P<database>[^/]+)/collectionGroups/'
    r'(?P<collection>[^/]+)/fields/(?P<field>[^/]+)$'
)
_FIELD_NAME = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$|^\*$')
_FIELD_STATES = {'CREATING', 'READY', 'NEEDS_REPAIR'}
_FIELD_SCOPES = {'COLLECTION', 'COLLECTION_GROUP'}
_FIELD_MODES = {'ASCENDING', 'DESCENDING', 'CONTAINS'}
_FIELD_ORDER_MODES = {'ASCENDING', 'DESCENDING'}
_FIELD_ARRAY_MODES = {'CONTAINS'}
_OVERRIDE_KEYS = {'collectionGroup', 'fieldPath', 'ttl', 'indexes'}
_INDEX_KEYS = {'queryScope', 'order', 'arrayConfig'}
_LIVE_INDEX_KEYS = {'queryScope', 'apiScope', 'fields', 'name', 'state'}
_LIVE_FIELD_KEYS = {'fieldPath', 'order', 'arrayConfig'}
_OPERATION_RESOURCE = re.compile(
    r'^projects/(?P<project>[^/]+)/databases/(?P<database>[^/]+)/operations/(?P<operation>[^/]+)$'
)


class FieldIndexError(ValueError):
    """Raised when a field index operation crosses its fail-closed contract."""


def gcloud_access_token() -> str:
    """Read the already-authorized gcloud token without exposing it in output."""

    result = subprocess.run(
        ['gcloud', 'auth', 'print-access-token'],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    token = result.stdout.strip()
    if result.returncode != 0 or not token:
        raise FieldIndexError('gcloud access-token lookup failed for Firestore field configuration')
    return token


def field_api_request(
    method: str,
    url: str,
    payload: Mapping[str, Any] | None = None,
    *,
    token_provider: Callable[[], str] = gcloud_access_token,
) -> Mapping[str, Any]:
    """Make one bounded Firestore Admin API request using the active gcloud identity."""

    body = None if payload is None else json.dumps(payload, separators=(',', ':')).encode('utf-8')
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            'Authorization': f'Bearer {token_provider()}',
            'Content-Type': 'application/json',
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise FieldIndexError(f'Firestore field API {method} failed with HTTP {exc.code}') from exc
    except urllib.error.URLError as exc:
        raise FieldIndexError(f'Firestore field API {method} was unavailable') from exc
    try:
        parsed = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FieldIndexError(f'Firestore field API {method} returned invalid JSON') from exc
    if not isinstance(parsed, Mapping):
        raise FieldIndexError(f'Firestore field API {method} returned a non-object')
    return parsed


def field_resource_name(*, project: str, database: str, collection_group: str, field_path: str) -> str:
    return f'projects/{project}/databases/{database}/collectionGroups/{collection_group}/fields/{field_path}'


def field_resource_url(*, project: str, database: str, collection_group: str, field_path: str) -> str:
    return (
        f'{FIRESTORE_ADMIN_API}/'
        f'{field_resource_name(project=project, database=database, collection_group=collection_group, field_path=field_path)}'
    )


def _field_resource_parts(name: Any, *, project: str, database: str) -> tuple[str, str]:
    if not isinstance(name, str):
        raise FieldIndexError('Firestore field resource name must be a string')
    match = _FIELD_RESOURCE.fullmatch(name)
    if not match or match['project'] != project or match['database'] != database:
        raise FieldIndexError('Firestore field resource has an unexpected database identity')
    if not _FIELD_NAME.fullmatch(match['field']):
        raise FieldIndexError('Firestore field resource has an invalid field path')
    return match['collection'], match['field']


def _operation_resource_parts(name: Any, *, project: str, database: str) -> str:
    """Restrict LRO polling to operations under the exact target database."""

    if not isinstance(name, str):
        raise FieldIndexError('Firestore field operation name must be a string')
    match = _OPERATION_RESOURCE.fullmatch(name)
    if not match or match['project'] != project or match['database'] != database:
        raise FieldIndexError('Firestore field operation has an unexpected database identity')
    return match['operation']


def expected_field_requirements(manifest: Mapping[str, Any]) -> tuple[FieldIndexRequirement, ...]:
    """Parse the manifest's nonempty (additive) field overrides into requirements.

    Entries with ``indexes == []`` are destructive exemptions owned by the
    manual exemption reconciler and are skipped; malformed overrides fail
    closed rather than being silently ignored.
    """

    overrides = manifest.get('fieldOverrides')
    if not isinstance(overrides, list):
        raise FieldIndexError('Firestore manifest must contain a fieldOverrides list')
    requirements: list[FieldIndexRequirement] = []
    seen: set[tuple[str, str]] = set()
    for position, override in enumerate(overrides):
        scope = f'fieldOverrides[{position}]'
        if not isinstance(override, Mapping):
            raise FieldIndexError(f'Firestore manifest {scope} must be an object')
        unknown_keys = set(override) - _OVERRIDE_KEYS
        if unknown_keys:
            raise FieldIndexError(f'Firestore manifest {scope} has unsupported keys {sorted(unknown_keys)}')
        collection_group = override.get('collectionGroup')
        field_path = override.get('fieldPath')
        indexes = override.get('indexes')
        ttl = override.get('ttl', False)
        if not isinstance(collection_group, str) or not collection_group or '/' in collection_group:
            raise FieldIndexError(f'Firestore manifest {scope} must contain a collectionGroup id')
        if not isinstance(field_path, str) or not field_path or not _FIELD_NAME.fullmatch(field_path):
            raise FieldIndexError(f'Firestore manifest {scope} must contain a valid fieldPath')
        if not isinstance(indexes, list) or ttl is not False:
            raise FieldIndexError(f'Firestore manifest {scope} must contain an indexes list and ttl=false')
        if (collection_group, field_path) in seen:
            raise FieldIndexError(f'Firestore manifest {scope} duplicates a field override')
        seen.add((collection_group, field_path))
        if not indexes:
            continue
        modes: list[str] = []
        declared: set[tuple[str, str]] = set()
        for index in indexes:
            if not isinstance(index, Mapping):
                raise FieldIndexError(f'Firestore manifest {scope} has a malformed index entry')
            if set(index) - _INDEX_KEYS:
                raise FieldIndexError(f'Firestore manifest {scope} has unsupported index keys')
            query_scope = index.get('queryScope')
            if query_scope not in _FIELD_SCOPES:
                raise FieldIndexError(f'Firestore manifest {scope} has an unsupported queryScope')
            has_order = 'order' in index
            has_array = 'arrayConfig' in index
            if has_order == has_array:
                raise FieldIndexError(f'Firestore manifest {scope} index must set exactly one mode')
            if has_order and index['order'] not in _FIELD_ORDER_MODES:
                raise FieldIndexError(f'Firestore manifest {scope} has an unsupported order')
            if has_array and index['arrayConfig'] not in _FIELD_ARRAY_MODES:
                raise FieldIndexError(f'Firestore manifest {scope} has an unsupported arrayConfig')
            mode = index.get('order') or index.get('arrayConfig')
            if (query_scope, mode) in declared:
                raise FieldIndexError(f'Firestore manifest {scope} duplicates an index mode')
            declared.add((query_scope, mode))
            if query_scope == 'COLLECTION_GROUP':
                modes.append(mode)
        if not modes:
            raise FieldIndexError(f'Firestore manifest {scope} has no collection-group modes')
        requirements.append(
            FieldIndexRequirement(
                identifier=f'{collection_group}.{field_path}',
                collection_group=collection_group,
                field_path=field_path,
                collection_group_modes=tuple(modes),
            )
        )
    return tuple(requirements)


def _validate_index_api_scope(index: Mapping[str, Any]) -> None:
    if 'apiScope' not in index:
        return
    if index['apiScope'] != 'ANY_API':
        raise FieldIndexError('Firestore field index apiScope must be ANY_API or omitted')


def _validate_live_field_entry(field: Mapping[str, Any], *, field_path: str, allow_wildcard: bool) -> None:
    """Fail closed on a live index field we cannot preserve faithfully."""

    unknown = set(field) - _LIVE_FIELD_KEYS
    if unknown:
        raise FieldIndexError(f'Firestore field index field has unrepresentable keys {sorted(unknown)}')
    path = field.get('fieldPath')
    if not isinstance(path, str):
        raise FieldIndexError('Firestore field index field omitted fieldPath')
    if path == '__name__':
        if set(field) - {'fieldPath', 'order'} or field.get('order') != 'ASCENDING':
            raise FieldIndexError('Firestore field index __name__ entry must be a plain ascending key')
        return
    has_order = 'order' in field
    has_array = 'arrayConfig' in field
    if has_order == has_array:
        raise FieldIndexError('Firestore field index field must set exactly one mode')
    if has_order and field['order'] not in _FIELD_ORDER_MODES:
        raise FieldIndexError('Firestore field index field has an unsupported order')
    if has_array and field['arrayConfig'] not in _FIELD_ARRAY_MODES:
        raise FieldIndexError('Firestore field index field has an unsupported arrayConfig')
    if path == '*':
        if not allow_wildcard:
            raise FieldIndexError('Firestore field index wildcard is only valid on inherited config')
        return
    if path != field_path:
        raise FieldIndexError(f'Firestore field index references a different field path ({path!r} != {field_path!r})')


def _validate_live_index(index: Mapping[str, Any], *, field_path: str, allow_wildcard: bool) -> None:
    """Fail closed on any live index shape we cannot preserve faithfully."""

    unknown = set(index) - _LIVE_INDEX_KEYS
    if unknown:
        raise FieldIndexError(f'Firestore field index has unrepresentable keys {sorted(unknown)}')
    _validate_index_api_scope(index)
    if index.get('queryScope') not in _FIELD_SCOPES:
        raise FieldIndexError('Firestore field index has an unsupported queryScope')
    fields = index.get('fields')
    if not isinstance(fields, list) or not fields or not all(isinstance(field, Mapping) for field in fields):
        raise FieldIndexError('Firestore field index has malformed fields')
    named = [field for field in fields if field.get('fieldPath') != '__name__']
    key_fields = [field for field in fields if field.get('fieldPath') == '__name__']
    if len(named) != 1 or len(key_fields) > 1 or (key_fields and fields[-1] is not key_fields[0]):
        raise FieldIndexError('Firestore field index must carry exactly one field plus an optional terminal __name__')
    for field in fields:
        _validate_live_field_entry(field, field_path=field_path, allow_wildcard=allow_wildcard)
    state = index.get('state')
    if not isinstance(state, str) or not state:
        raise FieldIndexError('Firestore field index state is missing')
    if state.upper() not in _FIELD_STATES:
        raise FieldIndexError('Firestore field index has an unsupported state')


def _effective_field_indexes(
    payload: Mapping[str, Any],
    *,
    requirement: FieldIndexRequirement,
    project: str,
    database: str,
    fetch: Callable[..., Mapping[str, Any]],
    visited: frozenset[str] = frozenset(),
    inherited: bool = False,
) -> list[dict[str, Any]]:
    """Resolve the effective index config, following inherited ancestors read-only.

    A patch against a field with ``usesAncestorConfig`` would otherwise wipe
    the inherited collection-scope defaults. The chain is restricted to field
    resources inside the exact project/database, and cycles fail closed.
    """

    config = payload.get('indexConfig')
    if not isinstance(config, Mapping):
        raise FieldIndexError('Firestore field config omitted indexConfig; refusing to overwrite defaults')
    if config.get('reverting') is True:
        raise FieldIndexError('Firestore field config is reverting; refusing to overwrite transitioning state')
    if config.get('usesAncestorConfig') is True:
        ancestor = config.get('ancestorField')
        if not isinstance(ancestor, str) or not ancestor:
            raise FieldIndexError('Firestore field config omitted ancestorField; refusing to overwrite defaults')
        _field_resource_parts(ancestor, project=project, database=database)
        if ancestor in visited:
            raise FieldIndexError('Firestore field config ancestor chain is cyclic')
        ancestor_payload = fetch('GET', f'{FIRESTORE_ADMIN_API}/{ancestor.lstrip("/")}', None)
        if not isinstance(ancestor_payload, Mapping):
            raise FieldIndexError('Firestore ancestor field config returned a non-object')
        if ancestor_payload.get('name') != ancestor:
            raise FieldIndexError('Firestore ancestor field config returned a mismatched resource name')
        return _effective_field_indexes(
            ancestor_payload,
            requirement=requirement,
            project=project,
            database=database,
            fetch=fetch,
            visited=visited | {ancestor},
            inherited=True,
        )
    raw_indexes = config.get('indexes', [])
    if not isinstance(raw_indexes, list):
        raise FieldIndexError('Firestore field config omitted explicit indexes; refusing to overwrite defaults')
    if not all(isinstance(index, Mapping) for index in raw_indexes):
        raise FieldIndexError('Firestore field config contains a malformed index')
    normalized = []
    seen_modes: set[tuple[str, str]] = set()
    for index in raw_indexes:
        _validate_live_index(index, field_path=requirement.field_path, allow_wildcard=inherited)
        normalized_fields = []
        for field in index['fields']:
            normalized_field = dict(field)
            if normalized_field.get('fieldPath') == '*':
                normalized_field['fieldPath'] = requirement.field_path
            normalized_fields.append(normalized_field)
        normalized_index = dict(index)
        normalized_index['fields'] = normalized_fields
        mode_key = _index_mode_key(normalized_index)
        if mode_key is not None:
            if mode_key in seen_modes:
                raise FieldIndexError('Firestore field config has ambiguous duplicate index modes')
            seen_modes.add(mode_key)
        normalized.append(normalized_index)
    return normalized


def _index_mode_key(index: Mapping[str, Any]) -> tuple[str, str] | None:
    fields = index.get('fields')
    if not isinstance(fields, list) or not fields:
        return None
    field = next(
        (entry for entry in fields if isinstance(entry, Mapping) and entry.get('fieldPath') != '__name__'),
        None,
    )
    if field is None:
        return None
    mode = field.get('order') or field.get('arrayConfig')
    if mode not in _FIELD_MODES:
        return None
    return (index.get('queryScope'), mode)


def _patchable_field_index(index: Mapping[str, Any]) -> dict[str, Any]:
    """Strip server output fields while retaining every semantic index option."""

    patch = {'queryScope': index['queryScope']}
    for key in ('apiScope',):
        if key in index:
            patch[key] = index[key]
    patch['fields'] = []
    for field in index['fields']:
        field_patch = {}
        for key in ('fieldPath', 'order', 'arrayConfig'):
            if key in field:
                field_patch[key] = field[key]
        patch['fields'].append(field_patch)
    return patch


def _declared_index_entry(requirement: FieldIndexRequirement, scope: str, mode: str) -> dict[str, Any]:
    field = {'fieldPath': requirement.field_path}
    if mode == 'CONTAINS':
        field['arrayConfig'] = 'CONTAINS'
    else:
        field['order'] = mode
    return {'queryScope': scope, 'fields': [field]}


def field_requirement_state(
    *,
    project: str,
    database: str,
    requirement: FieldIndexRequirement,
    request: Callable[..., Mapping[str, Any]],
) -> tuple[str, dict[str, Any] | None]:
    """Return (state, patch) for one requirement: READY, CREATING, or MISSING+patch."""

    url = field_resource_url(
        project=project,
        database=database,
        collection_group=requirement.collection_group,
        field_path=requirement.field_path,
    )
    payload = request('GET', url, None)
    if not isinstance(payload, Mapping):
        raise FieldIndexError('Firestore field lookup returned a non-object')
    expected_name = field_resource_name(
        project=project,
        database=database,
        collection_group=requirement.collection_group,
        field_path=requirement.field_path,
    )
    if payload.get('name') != expected_name:
        raise FieldIndexError(f'Firestore field resource identity mismatch: {requirement.identifier}')
    indexes = _effective_field_indexes(
        payload, requirement=requirement, project=project, database=database, fetch=request
    )
    for index in indexes:
        if str(index.get('state', '')).upper() == 'NEEDS_REPAIR':
            raise FieldIndexError(f'Firestore field index needs repair: {requirement.identifier}')
    ready_modes = {_index_mode_key(index) for index in indexes if str(index.get('state', '')).upper() == 'READY'}
    required = {('COLLECTION_GROUP', mode) for mode in requirement.collection_group_modes}
    if required <= ready_modes:
        return 'READY', None
    # Do not patch over a preserved index that is still building.
    if any(str(index.get('state', '')).upper() == 'CREATING' for index in indexes):
        return 'CREATING', None
    present = {key for key in (_index_mode_key(index) for index in indexes) if key is not None}
    declared = [
        ('COLLECTION', 'ASCENDING'),
        ('COLLECTION', 'DESCENDING'),
        ('COLLECTION', 'CONTAINS'),
        *(('COLLECTION_GROUP', mode) for mode in requirement.collection_group_modes),
    ]
    missing = [entry for entry in declared if entry not in present]
    if not missing:
        return 'READY', None
    updated_indexes = [
        *(_patchable_field_index(index) for index in indexes),
        *(_declared_index_entry(requirement, scope, mode) for scope, mode in missing),
    ]
    return 'MISSING', {
        'name': field_resource_name(
            project=project,
            database=database,
            collection_group=requirement.collection_group,
            field_path=requirement.field_path,
        ),
        'indexConfig': {'indexes': updated_indexes},
    }


def expected_field_states(
    *,
    requirements: tuple[FieldIndexRequirement, ...],
    project: str,
    database: str,
    request: Callable[..., Mapping[str, Any]],
) -> dict[tuple[str, str], str]:
    """Read every requirement's live state without writing."""

    states: dict[tuple[str, str], str] = {}
    for requirement in requirements:
        state, _patch = field_requirement_state(
            project=project, database=database, requirement=requirement, request=request
        )
        states[(requirement.collection_group, requirement.field_path)] = state
    return states


def wait_field_operation(
    operation_name: str,
    *,
    project: str,
    database: str,
    request: Callable[..., Mapping[str, Any]],
    timeout_seconds: float,
    poll_interval_seconds: float,
    sleep: Callable[[float], None],
    monotonic: Callable[[], float],
) -> None:
    _operation_resource_parts(operation_name, project=project, database=database)
    deadline = monotonic() + max(0.0, timeout_seconds)
    url = f'{FIRESTORE_ADMIN_API}/{operation_name.lstrip("/")}'
    while True:
        operation = request('GET', url, None)
        if not isinstance(operation, Mapping):
            raise FieldIndexError('Firestore field index operation returned a non-object')
        if operation.get('done') is True:
            if operation.get('error'):
                raise FieldIndexError('Firestore field index operation failed')
            return
        if monotonic() >= deadline:
            raise FieldIndexError('Firestore field index operation timed out')
        sleep(min(max(0.1, poll_interval_seconds), max(0.1, deadline - monotonic())))


def _terminal_field_state(
    *,
    project: str,
    database: str,
    requirement: FieldIndexRequirement,
    request: Callable[..., Mapping[str, Any]],
    timeout_seconds: float,
    poll_interval_seconds: float,
    sleep: Callable[[float], None],
    monotonic: Callable[[], float],
) -> str:
    """Poll until the field leaves CREATING and return the settled state."""

    deadline = monotonic() + max(0.0, timeout_seconds)
    while True:
        state, _patch = field_requirement_state(
            project=project, database=database, requirement=requirement, request=request
        )
        if state != 'CREATING':
            return state
        if monotonic() >= deadline:
            raise FieldIndexError(f'Firestore field index timed out: {requirement.identifier}')
        sleep(min(max(0.1, poll_interval_seconds), max(0.1, deadline - monotonic())))


def wait_field_requirement(
    *,
    project: str,
    database: str,
    requirement: FieldIndexRequirement,
    request: Callable[..., Mapping[str, Any]],
    timeout_seconds: float,
    poll_interval_seconds: float,
    sleep: Callable[[float], None],
    monotonic: Callable[[], float],
) -> None:
    state = _terminal_field_state(
        project=project,
        database=database,
        requirement=requirement,
        request=request,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
        sleep=sleep,
        monotonic=monotonic,
    )
    if state != 'READY':
        raise FieldIndexError(f'Firestore field index did not become ready: {requirement.identifier}')


def _launch_field_patch(
    *,
    project: str,
    database: str,
    requirement: FieldIndexRequirement,
    patch: Mapping[str, Any],
    request: Callable[..., Mapping[str, Any]],
) -> str:
    url = field_resource_url(
        project=project,
        database=database,
        collection_group=requirement.collection_group,
        field_path=requirement.field_path,
    )
    operation = request('PATCH', f'{url}?updateMask=indexConfig', patch)
    if not isinstance(operation, Mapping):
        raise FieldIndexError('Firestore field index update returned a non-object')
    operation_name = operation.get('name')
    return _operation_resource_name(operation_name, project=project, database=database)


def _operation_resource_name(name: Any, *, project: str, database: str) -> str:
    _operation_resource_parts(name, project=project, database=database)
    return name


def apply_field_requirement(
    *,
    project: str,
    database: str,
    requirement: FieldIndexRequirement,
    request: Callable[..., Mapping[str, Any]],
    timeout_seconds: float,
    poll_interval_seconds: float,
    sleep: Callable[[float], None],
    monotonic: Callable[[], float],
) -> bool:
    """Union the live effective config with declared modes; no-op when READY."""

    return (requirement.collection_group, requirement.field_path) in provision_field_requirements(
        requirements=(requirement,),
        project=project,
        database=database,
        request=request,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
        sleep=sleep,
        monotonic=monotonic,
    )


def provision_field_requirements(
    *,
    requirements: tuple[FieldIndexRequirement, ...],
    project: str,
    database: str,
    request: Callable[..., Mapping[str, Any]],
    timeout_seconds: float,
    poll_interval_seconds: float,
    sleep: Callable[[float], None],
    monotonic: Callable[[], float],
) -> set[tuple[str, str]]:
    """Launch every missing field update, then wait once for the whole batch.

    ``timeout_seconds`` bounds the batch from the first non-READY field onward:
    no PATCH is issued after the deadline and every LRO/field wait consumes the
    same remaining budget. The pre-PATCH re-read narrows the stale-inventory
    window but is not a compare-and-swap — cooperating writers are serialized
    by the reconcile schema/workflow lock, not by this client.
    """

    if timeout_seconds <= 0:
        raise FieldIndexError('timeout_seconds must be positive')
    if poll_interval_seconds <= 0:
        raise FieldIndexError('poll_interval_seconds must be positive')
    patched: set[tuple[str, str]] = set()
    unsettled = list(requirements)
    deadline: float | None = None

    def _remaining_timeout() -> float:
        if deadline is None:
            return timeout_seconds
        return max(0.0, deadline - monotonic())

    while unsettled:
        operations: list[tuple[str, FieldIndexRequirement]] = []
        creating: list[FieldIndexRequirement] = []
        survivors: list[FieldIndexRequirement] = []
        for requirement in unsettled:
            state, patch = field_requirement_state(
                project=project, database=database, requirement=requirement, request=request
            )
            key = (requirement.collection_group, requirement.field_path)
            if state == 'READY':
                continue
            if deadline is None:
                deadline = monotonic() + timeout_seconds
            if state == 'CREATING':
                creating.append(requirement)
                survivors.append(requirement)
                continue
            if state != 'MISSING' or patch is None:
                raise FieldIndexError(f'Firestore field index is not provisionable: {requirement.identifier}')
            if key in patched:
                raise FieldIndexError(
                    f'Firestore field index remained missing after its update: {requirement.identifier}'
                )
            if monotonic() >= deadline:
                raise FieldIndexError('Firestore field provisioning timed out')
            operations.append(
                (
                    _launch_field_patch(
                        project=project,
                        database=database,
                        requirement=requirement,
                        patch=patch,
                        request=request,
                    ),
                    requirement,
                )
            )
            patched.add(key)
            survivors.append(requirement)
        for operation_name, _requirement in operations:
            wait_field_operation(
                operation_name,
                project=project,
                database=database,
                request=request,
                timeout_seconds=_remaining_timeout(),
                poll_interval_seconds=poll_interval_seconds,
                sleep=sleep,
                monotonic=monotonic,
            )
        for requirement in creating:
            state = _terminal_field_state(
                project=project,
                database=database,
                requirement=requirement,
                request=request,
                timeout_seconds=_remaining_timeout(),
                poll_interval_seconds=poll_interval_seconds,
                sleep=sleep,
                monotonic=monotonic,
            )
            if state == 'READY':
                survivors.remove(requirement)
        unsettled = survivors
        if unsettled and monotonic() >= deadline:
            raise FieldIndexError('Firestore field provisioning timed out')
    return patched

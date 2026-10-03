"""Read-only real-Firestore oracle for exported runtime query shapes."""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import datetime
import hashlib
import json
import os
import re
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import unquote

from google.api_core.exceptions import FailedPrecondition
from google.api_core.retry import Retry
from google.cloud import firestore_admin_v1
from google.cloud.firestore_v1 import Client
from google.cloud.firestore_v1.base_query import And, FieldFilter, Or
from google.cloud.firestore_v1.document import DocumentSnapshot
from google.protobuf.json_format import MessageToDict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.support.firestore_index_rules import is_served, required_index, resolved_candidate_index
from tests.support.firestore_shape_recorder import (
    Aggregation,
    QueryFilter,
    QueryShape,
    document_path_template,
)

SCHEMA_VERSION = 1
RESOURCE = re.compile(r'^projects/([^/]+)/databases/([^/]+)/collectionGroups/([^/]+)/(indexes|fields)/(.+)$')
COMPOSITE = re.compile(r'create_composite=([A-Za-z0-9_%=-]+)')
EXEMPTION = re.compile(r'create_exemption=([A-Za-z0-9_%=-]+)')
MODES = {'ASCENDING', 'DESCENDING', 'CONTAINS'}
NO_RETRY = Retry(predicate=lambda exc: False)


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def resource_parts(name: str, project: str | None = None, database: str | None = None) -> tuple[str, str]:
    match = RESOURCE.fullmatch(name)
    if not match or (project is not None and match[1] != project) or (database is not None and match[2] != database):
        raise ValueError('index/field resource has an unexpected database identity')
    return match[3], match[5]


def decode_suggested_index(message: str) -> dict[str, Any]:
    match = COMPOSITE.search(message)
    kind = 'indexes'
    if not match:
        match = EXEMPTION.search(message)
        kind = 'fields'
    if not match:
        raise ValueError('FailedPrecondition has no create_composite or create_exemption suggestion')
    token = unquote(match[1])
    raw = base64.b64decode(token + '=' * (-len(token) % 4), altchars=b'-_', validate=True)
    index = firestore_admin_v1.Index.deserialize(raw)
    resource = RESOURCE.fullmatch(index.name)
    if not resource:
        raise ValueError('index/field resource has an unexpected database identity')
    if resource[4] != kind:
        raise ValueError('suggestion kind does not match its resource path')
    collection, leaf = resource[3], resource[5]
    payload = MessageToDict(firestore_admin_v1.Index.pb(index))
    fields = payload.get('fields', [])
    if kind == 'fields' and (len(fields) != 1 or fields[0].get('fieldPath') != leaf):
        raise ValueError('exemption must carry exactly its resource field')
    if not fields or any(
        not field.get('fieldPath')
        or (field.get('order') or field.get('arrayConfig')) not in MODES
        or 'vectorConfig' in field
        for field in fields
    ):
        raise ValueError('suggestion has unsupported or missing field modes')
    if payload.get('queryScope') not in {'COLLECTION', 'COLLECTION_GROUP'}:
        raise ValueError('suggestion has unsupported query scope')
    if len({field['fieldPath'] for field in fields}) != len(fields):
        raise ValueError('suggestion contains duplicate fields')
    return {'collectionGroup': collection, 'queryScope': payload['queryScope'], 'fields': fields}


def error_result(exc: Exception) -> dict[str, Any]:
    return {'status': 'error', 'error_type': type(exc).__name__, 'error': str(exc)[:2000]}


def execute_query(query: Any, timeout: float) -> dict[str, Any]:
    try:
        rows = query.get(retry=NO_RETRY, timeout=timeout)
        return {'status': 'served', 'result_rows': len(rows)}
    except FailedPrecondition as exc:
        if not COMPOSITE.search(str(exc)) and not EXEMPTION.search(str(exc)):
            return error_result(exc)
        try:
            return {'status': 'unserved', 'suggested_index': decode_suggested_index(str(exc))}
        except Exception as decode_error:
            return {**error_result(decode_error), 'error_type': 'SuggestionDecodeError'}
    except Exception as exc:
        return error_result(exc)


def synthetic_path(collection: str, namespace: str) -> str:
    if not collection or '/' in collection:
        raise ValueError('invalid collection id')
    return f'users/{namespace}/{collection}'


def oracle_collection_path(encoded: Mapping[str, Any], namespace: str) -> str:
    """Resolve the probe collection path, preserving root-collection identity.

    A COLLECTION-scope shape recorded against a one-segment path is a real
    collection-group root (e.g. ``feedback_reports``). Deeper recorded paths
    still probe the synthetic ``users/<namespace>/`` tree so no live user
    document is ever read.
    """
    if encoded['scope'] != 'COLLECTION':
        return synthetic_path(encoded['collection_group'], namespace)
    recorded = encoded.get('collection_path')
    if not isinstance(recorded, str) or not recorded:
        raise ValueError('recorded COLLECTION shape omitted collection_path')
    segments = recorded.split('/')
    if not all(segments):
        raise ValueError(f'recorded collection_path is malformed: {recorded!r}')
    if len(segments) % 2 == 0:
        raise ValueError(f'recorded collection_path ends in a document segment: {recorded!r}')
    if segments[-1] != encoded['collection_group']:
        raise ValueError(f'recorded collection_path ends in the wrong collection: {recorded!r}')
    if len(segments) == 1:
        return recorded
    return synthetic_path(encoded['collection_group'], namespace)


def decode_value(value: Mapping[str, Any], client: Any, path: str) -> Any:
    kind, data = value['type'], value.get('value')
    if kind in {'null', 'bool', 'int', 'str'}:
        return data
    if kind == 'float':
        return float(data)
    if kind == 'timestamp':
        return datetime.datetime.fromisoformat(data)
    if kind == 'date':
        return datetime.date.fromisoformat(data)
    if kind == 'bytes':
        return base64.b64decode(data, validate=True)
    if kind == 'array':
        return [decode_value(member, client, path) for member in data]
    if kind == 'map':
        return {key: decode_value(member, client, path) for key, member in data.items()}
    if kind in {'reference', 'snapshot'}:
        original = value.get('reference') if kind == 'snapshot' else data
        identifier = hashlib.sha256(original.encode()).hexdigest()[:24]
        reference = client.document(f'{path}/oracle-{identifier}')
        if kind == 'reference':
            return reference
        payload = {key: decode_value(member, client, path) for key, member in data.items()}
        return DocumentSnapshot(reference, payload, True, None, None, None)
    raise ValueError(f'unsupported representative value type: {kind}')


def decode_tree(tree: Any, client: Any, path: str) -> Any:
    if tree is None:
        return None
    if 'filters' in tree:
        if tree['op'] not in {'AND', 'OR'}:
            raise ValueError('unsupported boolean filter operator')
        return {'op': tree['op'], 'filters': [decode_tree(child, client, path) for child in tree['filters']]}
    value = decode_value(tree['value'], client, path)
    if tree['field'] == '__name__':
        values = value if isinstance(value, list) else [value]
        values = [
            (
                client.document(f'{path}/oracle-{hashlib.sha256(member.encode()).hexdigest()[:24]}')
                if isinstance(member, str)
                else member
            )
            for member in values
        ]
        value = values if isinstance(value, list) else values[0]
    return {'field': tree['field'], 'operator': tree['operator'], 'value': value}


def flatten_tree(tree: Any) -> list[QueryFilter]:
    if tree is None:
        return []
    if 'filters' in tree:
        return [leaf for child in tree['filters'] for leaf in flatten_tree(child)]
    return [QueryFilter(tree['field'], tree['operator'], tree['value'])]


def hydrate_shape(encoded: Mapping[str, Any], client: Any, namespace: str) -> QueryShape:
    path = oracle_collection_path(encoded, namespace)
    tree = encoded.get('filter_tree')
    if tree is None and encoded.get('filters'):
        tree = {'op': 'AND', 'filters': encoded['filters']}
    decoded_tree = decode_tree(tree, client, path)
    return QueryShape(
        collection_group=encoded['collection_group'],
        scope=encoded['scope'],
        collection_path=path,
        filters=tuple(flatten_tree(decoded_tree)),
        orders=tuple((order['field'], order['direction']) for order in encoded['orders']),
        aggregations=tuple(Aggregation(**item) for item in encoded['aggregations']),
        cursors=tuple((item['kind'], decode_value(item['value'], client, path)) for item in encoded.get('cursors', ())),
        limit=1,
        limit_to_last=encoded.get('limit_to_last', False),
        projection=tuple(encoded['projection']) if encoded.get('projection') is not None else None,
        filter_tree=decoded_tree,
    )


def sdk_filter(tree: Mapping[str, Any]) -> Any:
    if 'filters' in tree:
        constructor = And if tree['op'] == 'AND' else Or
        return constructor([sdk_filter(child) for child in tree['filters']])
    operator = 'not-in' if tree['operator'] == 'not_in' else tree['operator']
    return FieldFilter(tree['field'], operator, tree['value'])


def build_query(shape: QueryShape, client: Any) -> Any:
    if shape.scope == 'COLLECTION_GROUP':
        query = client.collection_group(shape.collection_group)
    elif shape.scope == 'COLLECTION':
        query = client.collection(shape.collection_path)
    else:
        raise ValueError('unsupported query scope')
    if shape.filter_tree is not None:
        nodes = shape.filter_tree['filters'] if shape.filter_tree.get('op') == 'AND' else [shape.filter_tree]
        for node in nodes:
            query = query.where(filter=sdk_filter(node))
    for field, direction in shape.orders:
        if direction not in {'ASCENDING', 'DESCENDING'}:
            raise ValueError('unsupported order direction')
        if shape.limit_to_last:
            direction = 'DESCENDING' if direction == 'ASCENDING' else 'ASCENDING'
        query = query.order_by(field, direction=direction)
    if shape.projection is not None:
        query = query.select(shape.projection)
    for kind, value in shape.cursors:
        if kind not in {'start_at', 'start_after', 'end_at', 'end_before'}:
            raise ValueError('unsupported cursor kind')
        query = getattr(query, kind)(value)
    query = query.limit(1)
    for aggregation in shape.aggregations:
        if aggregation.kind == 'count':
            query = query.count(alias=aggregation.alias)
        elif aggregation.kind in {'sum', 'avg'}:
            query = getattr(query, aggregation.kind)(aggregation.field, alias=aggregation.alias)
        else:
            raise ValueError('unsupported aggregation kind')
    return query


def filter_structure(tree: Any, preserve_order: bool = False) -> Any:
    if tree is None:
        return None
    if 'filters' in tree:
        children = [filter_structure(child, preserve_order) for child in tree['filters']]
        return {'op': tree['op'], 'filters': children if preserve_order else sorted(children, key=canonical)}
    result = {'field': tree['field'], 'operator': tree['operator']}
    operand = tree['value']
    if operand['type'] == 'null' or (operand['type'] == 'float' and operand['value'] == 'NaN'):
        result['unary'] = operand['type']
    if tree['operator'] in {'in', 'not_in', 'array_contains_any'}:
        result['disjunction_size'] = len(operand['value'])
    return result


def _recorded_path_template(encoded: Mapping[str, Any]) -> str:
    """Derive the uid-normalized path identity from collection_path itself.

    A supplied ``document_path_template`` is only accepted when it agrees with
    the recorded path — a stale template must never let a root probe and a
    subcollection probe collapse into one signature.
    """
    recorded = encoded.get('collection_path')
    if not isinstance(recorded, str) or not recorded:
        return encoded['collection_group']
    derived = document_path_template(recorded)
    supplied = encoded.get('document_path_template')
    if supplied is not None and supplied != derived:
        raise ValueError('recorded document_path_template disagrees with collection_path')
    return derived


def query_signature(encoded: Mapping[str, Any]) -> str:
    tree = encoded.get('filter_tree')
    if tree is None and encoded.get('filters'):
        tree = {'op': 'AND', 'filters': encoded['filters']}
    return canonical(
        {
            'collection': encoded['collection_group'],
            'scope': encoded['scope'],
            'path_template': _recorded_path_template(encoded),
            'filters': filter_structure(
                tree, any(item['value']['type'] == 'snapshot' for item in encoded.get('cursors', ()))
            ),
            'orders': encoded['orders'],
            'aggregations': [{'kind': item['kind'], 'field': item['field']} for item in encoded['aggregations']],
            'limit_to_last': encoded.get('limit_to_last', False),
            'cursors': [{'kind': item['kind'], 'type': item['value']['type']} for item in encoded.get('cursors', ())],
        }
    )


def deduplicate(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for entry in sorted(entries, key=canonical):
        signature = query_signature(entry['shape'])
        group = groups.setdefault(
            signature,
            {
                'signature': json.loads(signature),
                'id': hashlib.sha256(signature.encode()).hexdigest()[:16],
                'serving': False,
                'entries': {},
            },
        )
        if entry['shape'].get('serving', True):
            group['serving'] = True
        group['entries'].setdefault(entry['id'], entry)
    return [groups[key] for key in sorted(groups)]


def read_live_manifest(
    admin: Any, project: str, database: str, collections: set[str], timeout: float
) -> dict[str, Any]:
    parent = f'projects/{project}/databases/{database}/collectionGroups/-'
    raw_indexes = [
        MessageToDict(firestore_admin_v1.Index.pb(index))
        for index in admin.list_indexes(request={'parent': parent}, retry=None, timeout=timeout)
    ]
    raw_fields = [
        MessageToDict(firestore_admin_v1.Field.pb(field))
        for field in admin.list_fields(
            request={'parent': parent, 'filter': 'indexConfig.usesAncestorConfig:false'}, retry=None, timeout=timeout
        )
    ]
    default_name = f'projects/{project}/databases/{database}/collectionGroups/__default__/fields/*'
    default = MessageToDict(
        firestore_admin_v1.Field.pb(admin.get_field(name=default_name, retry=None, timeout=timeout))
    )
    cache = {field['name']: field for field in [default, *raw_fields]}

    def effective_config(field: dict[str, Any], visited: frozenset[str] = frozenset()) -> dict[str, Any]:
        name = field['name']
        resource_parts(name, project, database)
        if name in visited:
            raise ValueError('cyclic single-field index inheritance')
        config = field.get('indexConfig')
        if config is None or config.get('reverting'):
            raise ValueError('missing or transitioning single-field index configuration')
        if config.get('usesAncestorConfig'):
            ancestor = config['ancestorField']
            resource_parts(ancestor, project, database)
            if ancestor not in cache:
                cache[ancestor] = MessageToDict(
                    firestore_admin_v1.Field.pb(admin.get_field(name=ancestor, retry=None, timeout=timeout))
                )
            return effective_config(cache[ancestor], visited | {name})
        return config

    def field_modes(config: Mapping[str, Any]) -> list[dict[str, Any]]:
        modes = []
        for index in config.get('indexes', []):
            if index.get('state') != 'READY' or index.get('apiScope', 'ANY_API') != 'ANY_API':
                continue
            if index.get('queryScope') not in {'COLLECTION', 'COLLECTION_GROUP'}:
                raise ValueError('unsupported single-field query scope')
            for field in index.get('fields', []):
                if field['fieldPath'] == '__name__':
                    continue
                mode = field.get('order') or field.get('arrayConfig')
                if mode not in MODES:
                    raise ValueError('unsupported single-field mode')
                modes.append(
                    {'queryScope': index['queryScope'], 'arrayConfig' if mode == 'CONTAINS' else 'order': mode}
                )
        return sorted(modes, key=canonical)

    indexes = []
    for index in raw_indexes:
        collection, _ = resource_parts(index['name'], project, database)
        if index.get('state') != 'READY' or index.get('apiScope', 'ANY_API') != 'ANY_API':
            continue
        if any('vectorConfig' in field for field in index.get('fields', [])):
            continue
        if index.get('queryScope') not in {'COLLECTION', 'COLLECTION_GROUP'} or not index.get('fields'):
            raise ValueError('malformed live composite index')
        if any((field.get('order') or field.get('arrayConfig')) not in MODES for field in index['fields']):
            raise ValueError('unsupported live composite mode')
        indexes.append({'collectionGroup': collection, 'queryScope': index['queryScope'], 'fields': index['fields']})
    defaults = field_modes(effective_config(default))
    overrides = {
        (collection, '*'): {'collectionGroup': collection, 'fieldPath': '*', 'indexes': defaults}
        for collection in collections
    }
    for field in raw_fields:
        collection, field_path = resource_parts(field['name'], project, database)
        if collection == '__default__':
            continue
        overrides[collection, field_path] = {
            'collectionGroup': collection,
            'fieldPath': field_path,
            'indexes': field_modes(effective_config(field)),
        }
    manifest = {'indexes': sorted(indexes, key=canonical), 'fieldOverrides': sorted(overrides.values(), key=canonical)}
    return {
        'manifest': manifest,
        'raw_indexes': sorted(raw_indexes, key=canonical),
        'raw_fields': sorted(cache.values(), key=canonical),
    }


def equivalent_suggestion(required: Any, suggested: Mapping[str, Any]) -> bool:
    if (
        required is None
        or required.collection_group != suggested['collectionGroup']
        or required.scope != suggested['queryScope']
    ):
        return False
    fields = tuple(
        (field['fieldPath'], field.get('order') or field.get('arrayConfig')) for field in suggested['fields']
    )
    if fields and not any(field == '__name__' for field, _ in fields):
        direction = next((mode for _, mode in reversed(fields) if mode != 'CONTAINS'), 'ASCENDING')
        fields += (('__name__', direction),)
    prefix_size = len(required.equality_fields)
    prefix = dict(fields[:prefix_size])
    expected = dict(required.fields[:prefix_size])
    return (
        len(fields) == len(required.fields)
        and len(dict(fields)) == len(fields)
        and prefix.keys() == expected.keys()
        and all(
            prefix[field] == 'CONTAINS' if mode == 'CONTAINS' else prefix[field] in {'ASCENDING', 'DESCENDING'}
            for field, mode in expected.items()
        )
        and fields[prefix_size:] == required.fields[prefix_size:]
    )


def compare_prediction(shape: QueryShape, manifest: Mapping[str, Any], observed: Mapping[str, Any]) -> dict[str, Any]:
    candidate = resolved_candidate_index(shape, manifest)
    required = required_index(shape)
    predicted = is_served(shape, manifest)
    failures, reports = [], []
    if observed['status'] == 'unserved':
        if predicted:
            failures.append('predicted_served_but_unserved')
        if not equivalent_suggestion(required, observed['suggested_index']):
            failures.append('suggested_index_mismatch')
    elif observed['status'] == 'served' and not predicted:
        reports.append('predicted_unserved_but_served')
    return {
        'predicted_served': predicted,
        'required_index': required.to_dict() if required else None,
        'candidate_index': candidate.to_dict(),
        'uncertain': candidate.uncertain,
        'rule_bugs': failures,
        'review_findings': reports,
        'resolution': (
            (
                'confirmed_required_index'
                if observed['status'] == 'unserved' and not failures
                else (
                    'observed_served_without_full_candidate'
                    if observed['status'] == 'served' and not predicted
                    else None
                )
            )
            if candidate.uncertain
            else None
        ),
    }


class RateLimiter:
    def __init__(self, queries_per_second: float):
        self.interval = 1 / queries_per_second
        self.lock = threading.Lock()
        self.next_start = 0.0

    def wait(self, deadline: float) -> bool:
        with self.lock:
            start = max(time.monotonic(), self.next_start)
            if start >= deadline:
                return False
            self.next_start = start + self.interval
        time.sleep(max(0, start - time.monotonic()))
        return time.monotonic() < deadline


def empty_group_probe(
    client: Any, namespace: str, timeout: float, limiter: RateLimiter, deadline: float
) -> dict[str, Any]:
    collection = f'oracle_probe_{namespace}'
    baseline = client.collection_group(collection).limit(1)
    if not limiter.wait(deadline):
        return {'verified': False, 'error': 'runtime budget exhausted before empty-group probe'}
    empty = execute_query(baseline, min(timeout, max(0.01, deadline - time.monotonic())))
    if empty['status'] != 'served' or empty['result_rows'] != 0:
        return {'verified': False, 'collection': collection, 'empty_scan': empty}
    query = (
        client.collection_group(collection)
        .where(filter=And([FieldFilter('oracle_equality', '==', namespace), FieldFilter('oracle_range', '>=', 0)]))
        .order_by('oracle_range')
        .limit(1)
    )
    if not limiter.wait(deadline):
        return {'verified': False, 'empty_scan': empty, 'error': 'runtime budget exhausted before indexed probe'}
    checked = execute_query(query, min(timeout, max(0.01, deadline - time.monotonic())))
    suggested = checked.get('suggested_index', {})
    return {
        'verified': checked['status'] == 'unserved'
        and suggested.get('collectionGroup') == collection
        and suggested.get('queryScope') == 'COLLECTION_GROUP',
        'collection': collection,
        'empty_scan': empty,
        'indexed_query': checked,
    }


def run_groups(
    groups: list[dict[str, Any]],
    client: Any,
    manifest: Mapping[str, Any],
    namespace: str,
    concurrency: int,
    timeout: float,
    limiter: RateLimiter,
    deadline: float,
) -> list[dict[str, Any]]:
    def run(group: dict[str, Any]) -> dict[str, Any]:
        entries = list(group['entries'].values())
        try:
            shapes = [hydrate_shape(entry['shape'], client, namespace) for entry in entries]
            query = build_query(shapes[0], client)
            if not limiter.wait(deadline):
                raise TimeoutError('oracle total runtime budget exhausted; query not executed')
            observed = execute_query(query, min(timeout, max(0.01, deadline - time.monotonic())))
            predictions = [
                dict(id=entry['id'], **compare_prediction(shape, manifest, observed))
                for entry, shape in zip(entries, shapes)
            ]
        except Exception as exc:
            observed, predictions = error_result(exc), []
        return {
            'id': group['id'],
            'signature': group['signature'],
            'serving': group['serving'],
            'shape_ids': [entry['id'] for entry in entries],
            'calling_functions': sorted({entry['calling_function'] for entry in entries}),
            'observed': observed,
            'predictions': predictions,
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        return list(pool.map(run, groups))


def build_report(
    project: str,
    database: str,
    namespace: str,
    export: Mapping[str, Any],
    inventory: Mapping[str, Any],
    probe: Mapping[str, Any],
    results: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    predictions = [prediction for result in results for prediction in result['predictions']]

    def outcome_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
        row_predictions = [prediction for row in rows for prediction in row['predictions']]
        return {
            **{
                status: sum(row['observed']['status'] == status for row in rows)
                for status in ('served', 'unserved', 'error')
            },
            'rule_bugs': sum(bool(prediction['rule_bugs']) for prediction in row_predictions),
        }

    counts = {
        'exported_shapes': len(export['shapes']),
        'unique_queries': len(deduplicate(export['shapes'])),
        'evaluated_signatures': len(results),
        **{
            status: sum(result['observed']['status'] == status for result in results)
            for status in ('served', 'unserved', 'error')
        },
        'rule_bugs': sum(bool(prediction['rule_bugs']) for prediction in predictions),
        'review_findings': sum(bool(prediction['review_findings']) for prediction in predictions),
        'resolved_uncertain': sum(prediction['resolution'] is not None for prediction in predictions),
        'serving_shapes': sum(1 for entry in export['shapes'] if entry['shape'].get('serving', True)),
        'nonserving_shapes': sum(1 for entry in export['shapes'] if not entry['shape'].get('serving', True)),
        'serving_counts': outcome_counts([result for result in results if result['serving']]),
        'nonserving_counts': outcome_counts([result for result in results if not result['serving']]),
    }
    resolved = [
        {
            'shape_id': prediction['id'],
            'query_id': result['id'],
            'resolution': prediction['resolution'],
            'observed': result['observed'],
            'prediction': prediction,
        }
        for result in results
        for prediction in result['predictions']
        if prediction['resolution'] is not None
    ]
    comparisons_valid = bool(probe.get('verified')) and not errors
    if not comparisons_valid:
        resolved = []
    counts['resolved_uncertain'] = len(resolved)
    return {
        'schema_version': SCHEMA_VERSION,
        'project': project,
        'database': database,
        'namespace': namespace,
        'read_only': True,
        'comparisons_valid': comparisons_valid,
        'export_sha256': hashlib.sha256(canonical(export).encode()).hexdigest(),
        'manifest_sha256': hashlib.sha256(canonical(inventory.get('manifest', {})).encode()).hexdigest(),
        'normalization': 'Collection paths are synthetic except recorded one-segment collection-group roots, which probe the real root collection on dev/QA targets only (production roots are refused before any client is created); limit=1 and offset=0; limit_to_last reverses wire orders. '
        'Collection groups retain their real ID and may read at most one existing document. Values are never reported.',
        'empty_group_probe': probe,
        'inventory': inventory,
        'counts': counts,
        'errors': errors,
        'results': results,
        'resolved_uncertain': resolved,
        'exit_code': 2 if errors or counts['error'] or not probe.get('verified') else 1 if counts['rule_bugs'] else 0,
    }


def markdown_report(report: Mapping[str, Any]) -> str:
    lines = [
        '# Firestore index-rule oracle',
        '',
        f"Target: `{report['project']}` / `{report['database']}` (read-only)",
        '',
        f"Exit code: {report['exit_code']}; empty collection-group index check: {report['empty_group_probe'].get('verified', False)}",
        '',
        '| Measure | Count |',
        '| --- | ---: |',
    ]
    lines += [f"| {key} | {value} |" for key, value in report['counts'].items() if not isinstance(value, dict)]
    for outcome_key in ('serving_counts', 'nonserving_counts'):
        if outcome_key in report['counts']:
            lines += ['', f'| {outcome_key} | Count |', '| --- | ---: |']
            lines += [f'| {status} | {value} |' for status, value in report['counts'][outcome_key].items()]
    if not report['comparisons_valid']:
        lines += [
            '',
            'Comparisons are INCONCLUSIVE; the findings below are diagnostic only and no uncertainty is resolved.',
        ]
    lines += [
        '',
        'Success proves service only against the captured live manifest, not that a composite is unnecessary.',
        'Unserved-to-served findings require review for rule bugs/index merging. No flags or ledgers are changed automatically.',
        '',
        '## Findings',
        '',
        '| Query | Shape | Finding |',
        '| --- | --- | --- |',
    ]
    for result in report['results']:
        if result['observed']['status'] == 'error':
            lines.append(f"| {result['id']} | — | error: {result['observed']['error_type']} |")
        for prediction in result['predictions']:
            for finding in prediction['rule_bugs'] + prediction['review_findings']:
                lines.append(f"| {result['id']} | {prediction['id']} | {finding} |")
    if report['errors']:
        lines += ['', '## Run errors', *[f"- {item['error_type']}: {item['error']}" for item in report['errors']]]
    return '\n'.join(lines) + '\n'


def has_root_probe(export: Mapping[str, Any]) -> bool:
    """True when the export probes a real collection-group root (one-segment path)."""

    return any(
        entry['shape'].get('scope') == 'COLLECTION'
        and isinstance(entry['shape'].get('collection_path'), str)
        and len(entry['shape']['collection_path'].split('/')) == 1
        for entry in export.get('shapes', ())
    )


def write_reports(report: Mapping[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / 'report.json').write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + '\n')
    (output_dir / 'report.md').write_text(markdown_report(report))
    (output_dir / 'resolved-uncertain.json').write_text(
        json.dumps(
            {
                'schema_version': SCHEMA_VERSION,
                'project': report['project'],
                'database': report['database'],
                'export_sha256': report['export_sha256'],
                'manifest_sha256': report['manifest_sha256'],
                'comparisons_valid': report['comparisons_valid'],
                'resolutions': report['resolved_uncertain'],
            },
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + '\n'
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export', type=Path, required=True)
    parser.add_argument('--project', default='based-hardware-dev')
    parser.add_argument('--database', default='jit-qa')
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--allow-prod-read-only', action='store_true')
    parser.add_argument('--concurrency', type=int, default=8)
    parser.add_argument('--queries-per-second', type=float, default=8)
    parser.add_argument('--query-timeout', type=float, default=10)
    parser.add_argument('--max-runtime', type=float, default=540)
    args = parser.parse_args(argv)
    if args.project == 'based-hardware' and not args.allow_prod_read_only:
        parser.error('production is refused without --allow-prod-read-only')
    if os.environ.get('FIRESTORE_EMULATOR_HOST'):
        parser.error('the emulator is not an index-planner oracle; unset FIRESTORE_EMULATOR_HOST')
    if not re.fullmatch(r'[a-z][a-z0-9-]{4,61}[a-z0-9]', args.project) or not re.fullmatch(
        r'[A-Za-z0-9()-]+', args.database
    ):
        parser.error('project must be a project ID (not a numeric alias), and database must be a resource ID')
    if not (
        1 <= args.concurrency <= 32
        and 0 < args.queries_per_second <= 50
        and 0 < args.query_timeout <= 60
        and 0 < args.max_runtime <= 600
    ):
        parser.error('invalid concurrency, rate, timeout, or runtime bound')
    export = json.loads(args.export.read_text())
    if export.get('schema_version') != SCHEMA_VERSION or not export.get('shapes'):
        parser.error('expected a non-empty v1 recorder export')
    if any(driver.get('errors') for driver in export.get('drivers', [])):
        parser.error('recorder export has driver errors')
    if has_root_probe(export) and (args.project, args.database) != ('based-hardware-dev', 'jit-qa'):
        parser.error(
            'root collection-group probes only run on based-hardware-dev/jit-qa; '
            'real production roots are never read'
        )
    namespace = f'index-oracle-{uuid.uuid4().hex}'
    started = time.monotonic()
    deadline = started + args.max_runtime
    limiter = RateLimiter(args.queries_per_second)
    inventory, probe, results, errors = {}, {}, [], []
    try:
        client = Client(project=args.project, database=args.database)
        admin = firestore_admin_v1.FirestoreAdminClient()
        collections = {entry['shape']['collection_group'] for entry in export['shapes']}
        inventory = read_live_manifest(admin, args.project, args.database, collections, args.query_timeout)
        probe = empty_group_probe(client, namespace, args.query_timeout, limiter, deadline)
        if probe['verified']:
            results = run_groups(
                deduplicate(export['shapes']),
                client,
                inventory['manifest'],
                namespace,
                args.concurrency,
                args.query_timeout,
                limiter,
                deadline,
            )
            after = read_live_manifest(admin, args.project, args.database, collections, args.query_timeout)
            if canonical(inventory) != canonical(after):
                errors.append(
                    error_result(
                        RuntimeError('live index inventory changed during the run; comparisons are inconclusive')
                    )
                )
        else:
            errors.append(
                error_result(
                    RuntimeError('empty collection-group index checking was not demonstrated; no shapes executed')
                )
            )
    except Exception as exc:
        errors.append(error_result(exc))
    report = build_report(args.project, args.database, namespace, export, inventory, probe, results, errors)
    report['elapsed_seconds'] = round(time.monotonic() - started, 3)
    write_reports(report, args.output_dir)
    print(f"oracle: {canonical(report['counts'])}; reports: {args.output_dir}")
    return report['exit_code']


if __name__ == '__main__':
    raise SystemExit(main())

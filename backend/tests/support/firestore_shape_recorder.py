"""Test-time Firestore fake that records the index-relevant shape of every query.

Install ``RecordingFirestore`` in place of the real client via
``install_recorder``. Query builders are immutable: each modifier returns a new
object, so a partially built query can be forked without affecting siblings.
Terminal calls (``.stream()`` / ``.get()`` on a query or aggregation query)
append a frozen ``QueryShape`` to ``client.shapes``; document ``.get()`` reads
return seeded payloads (or a missing snapshot) and are not recorded as queries.
"""

from __future__ import annotations

import base64
import dataclasses
import datetime
import enum
import json
import math
import importlib
import sys
import unittest.mock
from collections.abc import Mapping
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Iterator

ASCENDING = 'ASCENDING'
DESCENDING = 'DESCENDING'

_SCOPE_COLLECTION = 'COLLECTION'
_SCOPE_COLLECTION_GROUP = 'COLLECTION_GROUP'


@dataclass(frozen=True)
class QueryFilter:
    field: str
    operator: str
    value: Any


@dataclass(frozen=True)
class Aggregation:
    kind: str
    field: str | None = None
    alias: str | None = None


def document_path_template(collection_path: str) -> str:
    """Render a document path template from a collection path.

    Segments in document positions (odd indexes) become ``{uid}`` when the
    parent collection is ``users`` and ``{document_id}`` otherwise, so the
    template is stable across concrete document ids.
    """
    segments = [s for s in collection_path.split('/') if s]
    rendered = []
    for index, segment in enumerate(segments):
        if index % 2 == 0:
            rendered.append(segment)
        else:
            rendered.append('{uid}' if segments[index - 1] == 'users' else '{document_id}')
    rendered.append('{document_id}')
    return '/'.join(rendered)


def _encode_value(value: Any) -> dict[str, Any]:
    """Encode a representative value as a deterministic, JSON-serializable tagged dict.

    Raises ``TypeError`` for value kinds that have no faithful encoding: an oracle
    rebuilding this query later must never receive a silently dropped value.
    """
    if value is None:
        return {'type': 'null', 'value': None}
    if isinstance(value, bool):
        return {'type': 'bool', 'value': value}
    if isinstance(value, enum.Enum):
        encoded = _encode_value(value.value)
        encoded['enum'] = type(value).__qualname__
        return encoded
    if isinstance(value, int):
        return {'type': 'int', 'value': value}
    if isinstance(value, float):
        if math.isnan(value):
            return {'type': 'float', 'value': 'NaN'}
        if math.isinf(value):
            return {'type': 'float', 'value': 'Infinity' if value > 0 else '-Infinity'}
        return {'type': 'float', 'value': value}
    if isinstance(value, str):
        return {'type': 'str', 'value': value}
    if isinstance(value, datetime.datetime):
        return {'type': 'timestamp', 'value': value.isoformat()}
    if isinstance(value, datetime.date):
        return {'type': 'date', 'value': value.isoformat()}
    if isinstance(value, (bytes, bytearray)):
        return {'type': 'bytes', 'value': base64.b64encode(bytes(value)).decode('ascii')}
    to_dict = getattr(value, 'to_dict', None)
    reference = getattr(value, 'reference', None)
    if callable(to_dict) and reference is not None:
        payload = to_dict()
        return {
            'type': 'snapshot',
            'reference': getattr(reference, 'path', str(reference)),
            'value': _encode_value(payload if isinstance(payload, Mapping) else {})['value'],
        }
    path = getattr(value, 'path', None)
    if isinstance(path, str) and '/' in path:
        return {'type': 'reference', 'value': path}
    if isinstance(value, (list, tuple)):
        return {'type': 'array', 'value': [_encode_value(v) for v in value]}
    if isinstance(value, (set, frozenset)):
        members = [_encode_value(item) for item in value]
        members.sort(key=lambda item: json.dumps(item, sort_keys=True))
        return {'type': 'array', 'value': members}
    if isinstance(value, Mapping):
        return {
            'type': 'map',
            'value': {str(key): _encode_value(value[key]) for key in sorted(value, key=str)},
        }
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _encode_value(dataclasses.asdict(value))
    model_dump = getattr(value, 'model_dump', None)
    if callable(model_dump):
        return _encode_value(model_dump())
    raise TypeError(f'unsupported query representative value type: {type(value).__qualname__}')


def _encode_filter_tree(tree: Any) -> Any:
    if tree is None:
        return None
    if 'filters' in tree:
        return {'op': tree['op'], 'filters': [_encode_filter_tree(child) for child in tree['filters']]}
    return {
        'field': tree['field'],
        'operator': tree['operator'],
        'value': _encode_value(tree['value']),
    }


def _filter_tree_skeleton(tree: Any) -> Any:
    """The boolean structure of a filter tree with values stripped."""
    if tree is None:
        return None
    if 'filters' in tree:
        return {'op': tree['op'], 'filters': [_filter_tree_skeleton(child) for child in tree['filters']]}
    return {'field': tree['field'], 'operator': tree['operator']}


@dataclass(frozen=True)
class QueryShape:
    collection_group: str
    scope: str = _SCOPE_COLLECTION
    collection_path: str = ''
    filters: tuple[QueryFilter, ...] = ()
    orders: tuple[tuple[str, str], ...] = ()
    aggregations: tuple[Aggregation, ...] = ()
    cursors: tuple[tuple[str, Any], ...] = ()
    limit: int | None = None
    limit_to_last: bool = False
    offset: int = 0
    projection: tuple[str, ...] | None = None
    filter_tree: Any = None
    calling_function: str = ''
    driver_function: str = ''
    parameter_combo: dict = field(default_factory=dict)
    serving: bool = True

    @property
    def uses_cursors(self) -> bool:
        return bool(self.cursors)

    @property
    def document_path_template(self) -> str:
        return document_path_template(self.collection_path)

    def to_dict(self) -> dict[str, Any]:
        """Serialize deterministically with tagged representative values."""
        return {
            'collection_group': self.collection_group,
            'scope': self.scope,
            'collection_path': self.collection_path,
            'document_path_template': self.document_path_template,
            'filters': [
                {'field': f.field, 'operator': f.operator, 'value': _encode_value(f.value)} for f in self.filters
            ],
            'filter_tree': _encode_filter_tree(self.filter_tree),
            'orders': [{'field': f, 'direction': d} for f, d in self.orders],
            'aggregations': [dataclasses.asdict(a) for a in self.aggregations],
            'cursors': [{'kind': kind, 'value': _encode_value(value)} for kind, value in self.cursors],
            'limit': self.limit,
            'limit_to_last': self.limit_to_last,
            'offset': self.offset,
            'projection': list(self.projection) if self.projection is not None else None,
            'uses_cursors': self.uses_cursors,
            'calling_function': self.calling_function,
            'driver_function': self.driver_function,
            'parameter_combo': _encode_value(self.parameter_combo)['value'],
            'serving': self.serving,
        }

    def signature(self) -> str:
        """JSON identity of the index-relevant shape.

        Excludes parameter combos, concrete filter values, limits/offsets,
        collection-path document ids, and projections; includes collection
        group, scope, flattened filters, orders, aggregation kinds/fields,
        filter boolean structure, calling function, and cursor usage.
        """
        identity = {
            'collection_group': self.collection_group,
            'scope': self.scope,
            'path_template': self.document_path_template,
            'filters': [{'field': f.field, 'operator': f.operator} for f in self.filters],
            'filter_tree': _filter_tree_skeleton(self.filter_tree),
            'orders': [list(o) for o in self.orders],
            'aggregations': [{'kind': a.kind, 'field': a.field} for a in self.aggregations],
            'cursors': sorted(kind for kind, _ in self.cursors),
            'limit_to_last': self.limit_to_last,
            'calling_function': self.calling_function,
            'driver_function': self.driver_function,
        }
        return json.dumps(identity, sort_keys=True)


_UNARY_OPERATOR_NAMES = {'IS_NULL': '==', 'IS_NAN': '==', 'IS_NOT_NULL': '!=', 'IS_NOT_NAN': '!='}


def _normalize_operator(op_string: Any) -> str:
    """Normalize an SDK operator string/enum to the canonical wire operator.

    The SDK turns ``== None``/``!= None`` and ``== NaN``/``!= NaN`` into unary
    filters whose ``op_string`` is an enum (``IS_NULL``, ``IS_NOT_NULL``,
    ``IS_NAN``, ``IS_NOT_NAN``); these map back to the canonical comparison the
    author wrote. Anything else is a plain operator string like ``<='' or
    ``array-contains`` and only gets hyphen-to-underscore normalization.
    """
    name = getattr(op_string, 'name', None)
    if name in _UNARY_OPERATOR_NAMES:
        return _UNARY_OPERATOR_NAMES[name]
    return str(op_string).replace('-', '_')


def _normalize_direction(direction: Any) -> str:
    """Normalize an SDK direction enum/string; reject anything unrecognized."""
    name = getattr(direction, 'name', None) or str(direction)
    normalized = name.strip().upper()
    if normalized in {ASCENDING, 'ASC'}:
        return ASCENDING
    if normalized in {DESCENDING, 'DESC'}:
        return DESCENDING
    raise ValueError(f'unrecognized order_by direction: {direction!r}')


def _normalize_filter(filter_obj: Any) -> dict[str, Any]:
    children = getattr(filter_obj, 'filters', None)
    operator = getattr(filter_obj, 'operator', None)
    if children is not None and operator is not None:
        op_name = getattr(operator, 'name', str(operator)).upper()
        return {'op': op_name, 'filters': [_normalize_filter(child) for child in children]}
    return {
        'field': filter_obj.field_path,
        'operator': _normalize_operator(filter_obj.op_string),
        'value': getattr(filter_obj, 'value', None),
    }


def _flatten_leaves(tree: Any) -> Iterator[dict[str, Any]]:
    if tree is None:
        return
    if 'filters' in tree:
        for child in tree['filters']:
            yield from _flatten_leaves(child)
    else:
        yield tree


def _calling_function() -> str:
    """The nearest ``database.*`` frame as ``module.qualname``, excluding this module."""
    this_module = __name__
    frame = sys._getframe(1)
    fallback = ''
    while frame is not None:
        module = frame.f_globals.get('__name__', '')
        if module == this_module:
            frame = frame.f_back
            continue
        if module == 'database' or module.startswith('database.'):
            return f'{module}.{frame.f_code.co_qualname}'
        if not fallback and module and not module.startswith('tests.support'):
            fallback = f'{module}.{frame.f_code.co_qualname}'
        frame = frame.f_back
    return fallback


@dataclass(frozen=True)
class _QueryState:
    collection_group: str
    scope: str
    collection_path: str
    filter_nodes: tuple[dict[str, Any], ...] = ()
    orders: tuple[tuple[str, str], ...] = ()
    cursors: tuple[tuple[str, Any], ...] = ()
    limit: int | None = None
    limit_to_last: bool = False
    offset: int = 0
    projection: tuple[str, ...] | None = None
    aggregations: tuple[Aggregation, ...] = ()

    @property
    def filter_tree(self) -> dict[str, Any] | None:
        if not self.filter_nodes:
            return None
        if len(self.filter_nodes) == 1:
            return self.filter_nodes[0]
        return {'op': 'AND', 'filters': list(self.filter_nodes)}


class RecordingDocumentSnapshot:
    """Stand-in for ``DocumentSnapshot``; ``exists`` mirrors seeded data presence."""

    def __init__(self, reference: 'RecordingDocumentReference', data: dict[str, Any] | None):
        self._reference = reference
        self._data = data
        self.exists = data is not None
        self.id = reference.id
        self.reference = reference

    def to_dict(self) -> dict[str, Any] | None:
        return dict(self._data) if self._data is not None else None

    def get(self, field_path: str) -> Any:
        if self._data is None:
            raise KeyError(field_path)
        return self._data[field_path]


class RecordingDocumentReference:
    """Stand-in for ``DocumentReference`` with neutral writes and seeded reads."""

    def __init__(self, client: 'RecordingFirestore', path: str):
        self._client = client
        self.path = path
        self.id = path.split('/')[-1]

    @property
    def parent(self) -> 'RecordingQuery' | None:
        parent_path = self.path.rsplit('/', 1)[0]
        return RecordingQuery._collection(self._client, parent_path)

    def collection(self, *segments: str) -> 'RecordingQuery':
        return RecordingQuery._collection(self._client, '/'.join((self.path, *segments)))

    def collections(self) -> list:
        return []

    def get(self, field_paths: Any = None, transaction: Any = None, **kwargs: Any) -> RecordingDocumentSnapshot:
        return RecordingDocumentSnapshot(self, self._client.documents.get(self.path))

    def set(self, data: Any, merge: Any = False) -> Any:
        return _neutral_write_result()

    def create(self, data: Any) -> Any:
        return _neutral_write_result()

    def update(self, data: Any) -> Any:
        return _neutral_write_result()

    def delete(self, *args: Any, **kwargs: Any) -> Any:
        return _neutral_write_result()

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, RecordingDocumentReference) and other.path == self.path

    def __hash__(self) -> int:
        return hash(self.path)

    def __repr__(self) -> str:
        return f'RecordingDocumentReference({self.path!r})'


def _neutral_write_result() -> Any:
    return SimpleNamespace(update_time=None)


class RecordingQuery:
    """Immutable query builder doubling as a collection reference."""

    def __init__(self, client: 'RecordingFirestore', state: _QueryState):
        self._client = client
        self._state = state

    @classmethod
    def _collection(cls, client: 'RecordingFirestore', path: str) -> 'RecordingQuery':
        return cls(
            client,
            _QueryState(
                collection_group=path.split('/')[-1],
                scope=_SCOPE_COLLECTION,
                collection_path=path,
            ),
        )

    @classmethod
    def _collection_group(cls, client: 'RecordingFirestore', group_id: str) -> 'RecordingQuery':
        return cls(
            client,
            _QueryState(
                collection_group=group_id,
                scope=_SCOPE_COLLECTION_GROUP,
                collection_path=group_id,
            ),
        )

    @property
    def id(self) -> str:
        return self._state.collection_group

    @property
    def path(self) -> str:
        return self._state.collection_path

    @property
    def parent(self) -> RecordingDocumentReference | None:
        segments = self._state.collection_path.split('/')
        if len(segments) < 2:
            return None
        return RecordingDocumentReference(self._client, '/'.join(segments[:-1]))

    def _replace(self, **changes: Any) -> 'RecordingQuery':
        return type(self)(self._client, dataclasses.replace(self._state, **changes))

    def document(self, *segments: str) -> RecordingDocumentReference:
        return RecordingDocumentReference(self._client, '/'.join((self._state.collection_path, *segments)))

    def add(self, document_data: Any, *args: Any, **kwargs: Any) -> tuple:
        """SDK ``CollectionReference.add`` equivalent: create under a generated id."""
        reference = self.document(self._client._next_auto_id())
        reference.set(document_data)
        return (_neutral_write_result(), reference)

    def where(self, *args: Any, filter: Any = None, **kwargs: Any) -> 'RecordingQuery':
        if filter is None:
            field_path, op_string, value = args
            node = {'field': field_path, 'operator': _normalize_operator(op_string), 'value': value}
        else:
            node = _normalize_filter(filter)
        return self._replace(filter_nodes=self._state.filter_nodes + (node,))

    def order_by(self, field_path: str, direction: Any = ASCENDING) -> 'RecordingQuery':
        return self._replace(orders=self._state.orders + ((field_path, _normalize_direction(direction)),))

    def limit(self, count: int) -> 'RecordingQuery':
        return self._replace(limit=count, limit_to_last=False)

    def limit_to_last(self, count: int) -> 'RecordingQuery':
        return self._replace(limit=count, limit_to_last=True)

    def offset(self, num_to_skip: int) -> 'RecordingQuery':
        return self._replace(offset=num_to_skip)

    def select(self, field_paths: Any) -> 'RecordingQuery':
        return self._replace(projection=tuple(field_paths))

    def start_at(self, document_fields_or_snapshot: Any) -> 'RecordingQuery':
        return self._replace(cursors=self._state.cursors + (('start_at', document_fields_or_snapshot),))

    def start_after(self, document_fields_or_snapshot: Any) -> 'RecordingQuery':
        return self._replace(cursors=self._state.cursors + (('start_after', document_fields_or_snapshot),))

    def end_before(self, document_fields_or_snapshot: Any) -> 'RecordingQuery':
        return self._replace(cursors=self._state.cursors + (('end_before', document_fields_or_snapshot),))

    def end_at(self, document_fields_or_snapshot: Any) -> 'RecordingQuery':
        return self._replace(cursors=self._state.cursors + (('end_at', document_fields_or_snapshot),))

    def count(self, alias: str | None = None) -> 'RecordingAggregationQuery':
        return self._aggregation('count', None, alias)

    def sum(self, field_path: str, alias: str | None = None) -> 'RecordingAggregationQuery':
        return self._aggregation('sum', field_path, alias)

    def avg(self, field_path: str, alias: str | None = None) -> 'RecordingAggregationQuery':
        return self._aggregation('avg', field_path, alias)

    def _aggregation(self, kind: str, field_path: str | None, alias: str | None) -> 'RecordingAggregationQuery':
        return RecordingAggregationQuery(
            self._client,
            dataclasses.replace(
                self._state,
                aggregations=self._state.aggregations + (Aggregation(kind, field_path, alias),),
            ),
        )

    def _record(self) -> QueryShape:
        shape = self._shape()
        self._client.shapes.append(shape)
        return shape

    def _shape(self) -> QueryShape:
        state = self._state
        tree = state.filter_tree
        flat = tuple(
            QueryFilter(field=leaf['field'], operator=leaf['operator'], value=leaf['value'])
            for leaf in _flatten_leaves(tree)
        )
        return QueryShape(
            collection_group=state.collection_group,
            scope=state.scope,
            collection_path=state.collection_path,
            filters=flat,
            orders=state.orders,
            aggregations=state.aggregations,
            cursors=state.cursors,
            limit=state.limit,
            limit_to_last=state.limit_to_last,
            offset=state.offset,
            projection=state.projection,
            filter_tree=tree,
            calling_function=_calling_function(),
            driver_function=self._client.driver_function,
            parameter_combo=dict(self._client.parameter_combo),
        )

    def stream(self, transaction: Any = None, retry: Any = None, timeout: Any = None) -> Iterator:
        self._record()
        return iter(self._client._pop_results())

    def get(self, transaction: Any = None, retry: Any = None, timeout: Any = None) -> list:
        self._record()
        return self._client._pop_results()

    def list_documents(self, page_size: int | None = None, retry: Any = None, timeout: Any = None) -> Iterator:
        return iter(())


class RecordingAggregationQuery:
    """Immutable aggregation builder; ``count``/``sum``/``avg`` chain onto it."""

    def __init__(self, client: 'RecordingFirestore', state: _QueryState):
        self._query = RecordingQuery(client, state)

    def _aggregation(self, kind: str, field_path: str | None, alias: str | None) -> 'RecordingAggregationQuery':
        return RecordingAggregationQuery(
            self._query._client,
            dataclasses.replace(
                self._query._state,
                aggregations=self._query._state.aggregations + (Aggregation(kind, field_path, alias),),
            ),
        )

    def count(self, alias: str | None = None) -> 'RecordingAggregationQuery':
        return self._aggregation('count', None, alias)

    def sum(self, field_path: str, alias: str | None = None) -> 'RecordingAggregationQuery':
        return self._aggregation('sum', field_path, alias)

    def avg(self, field_path: str, alias: str | None = None) -> 'RecordingAggregationQuery':
        return self._aggregation('avg', field_path, alias)

    def _neutral_results(self) -> list[list[Any]]:
        return [
            [
                SimpleNamespace(value=0, alias=agg.alias or agg.field or f'{agg.kind}_1')
                for agg in self._query._state.aggregations
            ]
        ]

    def get(self, transaction: Any = None, retry: Any = None, timeout: Any = None) -> list:
        self._query._record()
        return self._neutral_results()

    def stream(self, transaction: Any = None, retry: Any = None, timeout: Any = None) -> Iterator:
        self._query._record()
        return iter(self._neutral_results())


class RecordingBatch:
    """Neutral ``WriteBatch`` stand-in."""

    def __init__(self, client: 'RecordingFirestore'):
        self._client = client
        self.operations: list[tuple[str, Any, Any]] = []

    def set(self, reference: Any, data: Any, merge: Any = False) -> 'RecordingBatch':
        self.operations.append(('set', reference, data))
        return self

    def create(self, reference: Any, data: Any) -> 'RecordingBatch':
        self.operations.append(('create', reference, data))
        return self

    def update(self, reference: Any, data: Any) -> 'RecordingBatch':
        self.operations.append(('update', reference, data))
        return self

    def delete(self, reference: Any, *args: Any, **kwargs: Any) -> 'RecordingBatch':
        self.operations.append(('delete', reference, None))
        return self

    def commit(self, *args: Any, **kwargs: Any) -> list:
        results = [_neutral_write_result() for _ in self.operations]
        self.operations.clear()
        return results


class RecordingTransaction:
    """Satisfies the private surface the SDK's ``@firestore.transactional`` drives."""

    def __init__(self, client: 'RecordingFirestore', max_attempts: int = 5, read_only: bool = False):
        self._client = client
        self._max_attempts = max_attempts
        self._read_only = read_only
        self._id: bytes | None = None
        self._write_ops: list[tuple[str, Any, Any]] = []

    @property
    def in_progress(self) -> bool:
        return self._id is not None

    @property
    def id(self) -> bytes | None:
        return self._id

    def _clean_up(self) -> None:
        self._id = None
        self._write_ops.clear()

    def _begin(self, retry_id: bytes | None = None) -> None:
        self._id = retry_id or b'recording-transaction-0'

    def _commit(self, *args: Any, **kwargs: Any) -> list:
        results = [_neutral_write_result() for _ in self._write_ops]
        self._clean_up()
        return results

    def _rollback(self) -> None:
        self._clean_up()

    def get(self, ref_or_query: Any, *args: Any, **kwargs: Any) -> Any:
        if isinstance(ref_or_query, RecordingDocumentReference):
            return ref_or_query.get()
        if isinstance(ref_or_query, RecordingAggregationQuery):
            return ref_or_query.stream(transaction=self)
        if isinstance(ref_or_query, RecordingQuery):
            return ref_or_query.stream(transaction=self)
        return iter(())

    def get_all(self, references: Any, *args: Any, **kwargs: Any) -> list:
        return [ref.get() for ref in references]

    def set(self, reference: Any, data: Any, merge: Any = False) -> None:
        self._write_ops.append(('set', reference, data))

    def create(self, reference: Any, data: Any) -> None:
        self._write_ops.append(('create', reference, data))

    def update(self, reference: Any, data: Any) -> None:
        self._write_ops.append(('update', reference, data))

    def delete(self, reference: Any, *args: Any, **kwargs: Any) -> None:
        self._write_ops.append(('delete', reference, None))


class RecordingFirestore:
    """In-memory client replacement; queries record shapes, results are neutral.

    Attributes:
        shapes: ``QueryShape`` instances, one per terminal query call.
        documents: seeded ``path -> payload`` mapping served by document reads.
        driver_function: originating driver name stamped onto each shape; the
            ``calling_function`` field always carries the stack-derived caller.
        parameter_combo: current driver parameter combo copied onto each shape.
    """

    def __init__(self, documents: dict[str, dict] | None = None):
        self.shapes: list[QueryShape] = []
        self.documents: dict[str, dict] = dict(documents or {})
        self.driver_function: str = ''
        self.parameter_combo: dict = {}
        self._queued_results: list[list] = []
        self._auto_id_counter = 0

    def _next_auto_id(self) -> str:
        self._auto_id_counter += 1
        return f'auto-{self._auto_id_counter}'

    def queue_results(self, rows: list) -> None:
        """Queue consume-once terminal results; a queued row is never repeated."""
        self._queued_results.append(list(rows))

    def reset_queues(self) -> None:
        """Clear queued consume-once rows and the auto-id counter between trials."""
        self._queued_results.clear()
        self._auto_id_counter = 0

    def queued_leftovers(self) -> list[list]:
        """Rows still queued — a driver trial should leave none behind."""
        return list(self._queued_results)

    def _pop_results(self) -> list:
        return self._queued_results.pop(0) if self._queued_results else []

    def snapshot(self, path: str, data: dict | None = None) -> 'RecordingDocumentSnapshot':
        """Build a snapshot bound to this client for ``queue_results`` fixtures."""
        return RecordingDocumentSnapshot(RecordingDocumentReference(self, path), data or {})

    @contextmanager
    def recording_context(self, driver_function: str = '', combo: dict | None = None):
        """Set ``driver_function``/``parameter_combo`` for the duration of a driver call."""
        previous_driver, previous_combo = self.driver_function, self.parameter_combo
        self.driver_function = driver_function
        self.parameter_combo = dict(combo or {})
        try:
            yield self
        finally:
            self.driver_function, self.parameter_combo = previous_driver, previous_combo

    def collection(self, *segments: str) -> RecordingQuery:
        return RecordingQuery._collection(self, '/'.join(segments))

    def document(self, *segments: str) -> RecordingDocumentReference:
        return RecordingDocumentReference(self, '/'.join(segments))

    def collection_group(self, group_id: str) -> RecordingQuery:
        return RecordingQuery._collection_group(self, group_id)

    def get_all(self, references: Any, *args: Any, **kwargs: Any) -> list:
        return [ref.get() for ref in references]

    def batch(self) -> RecordingBatch:
        return RecordingBatch(self)

    def transaction(self, **kwargs: Any) -> RecordingTransaction:
        return RecordingTransaction(
            self,
            max_attempts=kwargs.get('max_attempts', 5),
            read_only=kwargs.get('read_only', False),
        )


@contextmanager
def install_recorder(client: RecordingFirestore):
    """Patch every client acquisition path in ``database._client`` to ``client``.

    Scoped ``unittest.mock`` patches cover the three cached client singletons
    (so previously imported getter functions and the ``db`` / ``data_plane_db``
    lazy proxies resolve to the fake) plus the ``google.cloud.firestore.Client``
    and ``firebase_admin.firestore.client`` constructors. A module that kept
    its own direct reference to a real client instance cannot be intercepted
    here; such module-local aliases are out of scope.
    """
    _client_module = importlib.import_module('database._client')

    patches = [
        unittest.mock.patch.object(_client_module, '_firestore_client', client),
        unittest.mock.patch.object(_client_module, '_customer_firestore_client', client),
        unittest.mock.patch.object(_client_module, '_data_plane_firestore_client', client),
    ]
    for module_name, attribute in (
        ('google.cloud.firestore', 'Client'),
        ('firebase_admin.firestore', 'client'),
    ):
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        patches.append(unittest.mock.patch.object(module, attribute, return_value=client))

    with ExitStack() as exit_stack:
        for patch in patches:
            exit_stack.enter_context(patch)
        yield client

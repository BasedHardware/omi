"""In-process numeric vector index behind ``database.vector_db`` (DESIGN L7).

It speaks the subset of the Pinecone ``Index`` API that ``database/vector_db.py`` and
``database/pinecone_partition_index.OwnerIndex`` use: ``upsert``, ``update``,
``delete`` (ids or filter), ``fetch``, ``list``, ``query``, ``_query`` and
``describe_index_stats``. Mutations honour ``_return_http_data_only=False`` with a
``(body, 200, {'x-pinecone-request-lsn': n})`` tuple, as OwnerIndex requires.

Unlike ``testing/e2e/fakes/vector_search.py`` (lexical scoring for wiring tests),
scores here are real numeric similarity over the stored values (cosine by default,
the production index metric), so product thresholds (e.g. task dedup at 0.6) keep
their meaning when the vectors come from the production embedding model.

The index can be saved to and loaded from a private JSON file so the stack stays
persistent across processes.
"""

from __future__ import annotations

from collections import defaultdict
import math
import os
from pathlib import Path
import threading
from typing import Any, Iterator, Mapping
from testing.pipeline_lab.store import private_subdir

_OPERATORS = {'$eq', '$ne', '$in', '$nin', '$exists', '$gte', '$lte', '$gt', '$lt'}


class UnsupportedFilter(ValueError):
    pass


def matches_filter(metadata: Mapping[str, Any], expression: Mapping[str, Any] | None) -> bool:
    """Pinecone metadata filter semantics for the operators the product uses."""
    if not expression:
        return True
    for key, expected in expression.items():
        if key == '$and':
            if not all(matches_filter(metadata, clause) for clause in expected):
                return False
            continue
        if key == '$or':
            if not any(matches_filter(metadata, clause) for clause in expected):
                return False
            continue
        if key.startswith('$'):
            raise UnsupportedFilter(f'unsupported top-level operator {key}')
        present = key in metadata
        actual = metadata.get(key)
        conditions = expected if isinstance(expected, dict) else {'$eq': expected}
        for op, value in conditions.items():
            if op not in _OPERATORS:
                raise UnsupportedFilter(f'unsupported operator {op}')
            values = actual if isinstance(actual, list) else [actual]
            if op == '$eq' and not (present and (actual == value or (isinstance(actual, list) and value in actual))):
                return False
            if op == '$ne' and present and (actual == value or (isinstance(actual, list) and value in actual)):
                return False
            if op == '$exists' and present != bool(value):
                return False
            if op == '$in' and not (present and any(item in value for item in values)):
                return False
            if op == '$nin' and present and any(item in value for item in values):
                return False
            if op in ('$gte', '$lte', '$gt', '$lt'):
                if not present or not isinstance(actual, (int, float)) or isinstance(actual, bool):
                    return False
                if op == '$gte' and not actual >= value:
                    return False
                if op == '$lte' and not actual <= value:
                    return False
                if op == '$gt' and not actual > value:
                    return False
                if op == '$lt' and not actual < value:
                    return False
    return True


def _norm(values: list[float]) -> float:
    return math.sqrt(sum(v * v for v in values))


class NumericVectorIndex:
    def __init__(self, dimension: int, *, metric: str = 'cosine', path: Path | None = None):
        if metric not in ('cosine', 'dotproduct', 'euclidean'):
            raise ValueError('metric must be cosine, dotproduct or euclidean')
        self.dimension = dimension
        self.metric = metric
        self.path = Path(path) if path is not None else None
        self._namespaces: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        self._lsn: dict[str, int] = defaultdict(int)
        self._lock = threading.RLock()
        self.query_log: list[dict[str, Any]] = []

    # -- persistence -------------------------------------------------------
    def save(self, path: Path | None = None) -> Path:
        from testing.pipeline_lab.stack.io import write_json

        target = Path(path or self.path or '')
        if not str(target):
            raise ValueError('no index path')
        with self._lock:
            payload = {
                'dimension': self.dimension,
                'metric': self.metric,
                'lsn': dict(self._lsn),
                'namespaces': {ns: list(records.values()) for ns, records in self._namespaces.items()},
            }
        return write_json(target, payload)

    @classmethod
    def load(cls, path: Path) -> 'NumericVectorIndex':
        from testing.pipeline_lab.stack.io import read_json

        payload = read_json(path)
        index = cls(int(payload['dimension']), metric=payload.get('metric', 'cosine'), path=path)
        for namespace, records in payload.get('namespaces', {}).items():
            for record in records:
                index._namespaces[namespace][record['id']] = record
        index._lsn.update({k: int(v) for k, v in payload.get('lsn', {}).items()})
        return index

    @classmethod
    def open(cls, path: Path, *, dimension: int, metric: str = 'cosine') -> 'NumericVectorIndex':
        if Path(path).exists():
            index = cls.load(path)
            if index.dimension != dimension:
                raise ValueError(f'stored index has dimension {index.dimension}, expected {dimension}')
            return index
        private_subdir(Path(path).parent)
        return cls(dimension, metric=metric, path=path)

    # -- Pinecone surface ---------------------------------------------------
    def _ack(self, body: dict, namespace: str, data_only: bool) -> Any:
        self._lsn[namespace] += 1
        if data_only:
            return body
        return body, 200, {'x-pinecone-request-lsn': str(self._lsn[namespace])}

    def _check_values(self, values: Any) -> list[float]:
        vector = [float(v) for v in values]
        if len(vector) != self.dimension:
            raise ValueError(f'vector dimension {len(vector)} does not match index dimension {self.dimension}')
        return vector

    def upsert(
        self, vectors: list[Mapping[str, Any]], namespace: str = '', _return_http_data_only: bool = True, **_: Any
    ):
        with self._lock:
            for item in vectors:
                if isinstance(item, (tuple, list)):
                    vector_id, values, *rest = item
                    metadata = rest[0] if rest else {}
                else:
                    vector_id, values, metadata = item['id'], item.get('values', []), item.get('metadata') or {}
                self._namespaces[namespace][vector_id] = {
                    'id': vector_id,
                    'values': self._check_values(values),
                    'metadata': dict(metadata),
                }
            return self._ack({'upserted_count': len(vectors)}, namespace, _return_http_data_only)

    def update(
        self,
        id: str,
        values: list[float] | None = None,
        set_metadata: Mapping[str, Any] | None = None,
        namespace: str = '',
        _return_http_data_only: bool = True,
        **_: Any,
    ):
        with self._lock:
            record = self._namespaces[namespace].get(id)
            if record is not None:
                if values is not None:
                    record['values'] = self._check_values(values)
                if set_metadata:
                    record['metadata'].update(set_metadata)
            return self._ack({}, namespace, _return_http_data_only)

    def delete(
        self,
        ids: list[str] | None = None,
        delete_all: bool = False,
        namespace: str = '',
        filter: Mapping[str, Any] | None = None,
        _return_http_data_only: bool = True,
        **_: Any,
    ):
        with self._lock:
            records = self._namespaces[namespace]
            if delete_all:
                doomed = list(records)
            elif filter is not None:
                doomed = [vid for vid, rec in records.items() if matches_filter(rec['metadata'], filter)]
            else:
                doomed = [vid for vid in ids or [] if vid in records]
            for vector_id in doomed:
                records.pop(vector_id, None)
            return self._ack({}, namespace, _return_http_data_only)

    def fetch(self, ids: list[str], namespace: str = '', **_: Any) -> dict[str, Any]:
        with self._lock:
            records = self._namespaces[namespace]
            return {
                'vectors': {vid: _copy(records[vid]) for vid in ids if vid in records},
                'namespace': namespace,
            }

    def list(self, prefix: str = '', namespace: str = '', limit: int = 100, **_: Any) -> Iterator[list[str]]:
        with self._lock:
            ids = sorted(vid for vid in self._namespaces[namespace] if vid.startswith(prefix))
        for start in range(0, len(ids), max(1, limit)):
            yield ids[start : start + limit]

    def describe_index_stats(self, **_: Any) -> dict[str, Any]:
        with self._lock:
            return {
                'dimension': self.dimension,
                'namespaces': {ns: {'vector_count': len(records)} for ns, records in self._namespaces.items()},
                'total_vector_count': sum(len(records) for records in self._namespaces.values()),
            }

    def _score(self, query: list[float], values: list[float]) -> float:
        if self.metric == 'dotproduct':
            return sum(a * b for a, b in zip(query, values))
        if self.metric == 'euclidean':
            return -math.sqrt(sum((a - b) ** 2 for a, b in zip(query, values)))
        denominator = _norm(query) * _norm(values)
        return sum(a * b for a, b in zip(query, values)) / denominator if denominator else 0.0

    def query(
        self,
        vector: list[float] | None = None,
        top_k: int = 10,
        namespace: str = '',
        filter: Mapping[str, Any] | None = None,
        include_values: bool = False,
        include_metadata: bool = False,
        id: str | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        with self._lock:
            records = self._namespaces[namespace]
            if vector is None and id is not None and id in records:
                vector = records[id]['values']
            if vector is None:
                raise ValueError('query needs a vector or a stored id')
            query = self._check_values(vector)
            scored = []
            for vector_id, record in records.items():
                if not matches_filter(record['metadata'], filter):
                    continue
                scored.append((self._score(query, record['values']), vector_id, record))
            scored.sort(key=lambda row: (-row[0], row[1]))
            matches = []
            for score, vector_id, record in scored[: max(0, int(top_k))]:
                match: dict[str, Any] = {'id': vector_id, 'score': score}
                if include_metadata:
                    match['metadata'] = dict(record['metadata'])
                if include_values:
                    match['values'] = list(record['values'])
                matches.append(match)
            self.query_log.append({'namespace': namespace, 'top_k': top_k, 'hits': len(matches)})
            return {'matches': matches, 'namespace': namespace}

    def _query(self, *, namespace: str = '', _return_http_data_only: bool = True, **kwargs: Any):
        body = self.query(namespace=namespace, **kwargs)
        if _return_http_data_only:
            return body
        return body, 200, {'x-pinecone-max-indexed-lsn': str(self._lsn[namespace])}

    # -- lab helpers --------------------------------------------------------
    def count(self, namespace: str = '') -> int:
        with self._lock:
            return len(self._namespaces.get(namespace, {}))

    def namespaces(self) -> dict[str, int]:
        with self._lock:
            return {ns: len(records) for ns, records in self._namespaces.items() if records}


def _copy(record: Mapping[str, Any]) -> dict[str, Any]:
    return {'id': record['id'], 'values': list(record['values']), 'metadata': dict(record['metadata'])}


def default_index_path(lab_root: Path) -> Path:
    return Path(os.path.join(lab_root, 'stack', 'vector_index.json'))

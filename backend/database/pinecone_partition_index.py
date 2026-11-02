"""Owner-scoped Pinecone calls with durable admission before provider mutations.

Each request uses one primary. A failed or ambiguous mutation keeps its pending
marker, preventing migration; searches never fall back to a stale old copy.
"""

from __future__ import annotations

from hashlib import sha256
import json
import logging
import os
import time
from typing import Any, Mapping, Sequence, cast

from database import pinecone_partition_state as state
from database.legal_holds import external_write_fence
from database.pinecone_provider_errors import barrier_record, is_missing_namespace

logger = logging.getLogger(__name__)


def _field(value: Any, name: str) -> Any:
    return value[name] if isinstance(value, dict) else getattr(value, name)


def _owner_filter(value: Any, uid: str) -> bool:
    if not isinstance(value, dict):
        return False
    if value.get('uid') == uid or value.get('uid') == {'$eq': uid}:
        return True
    return any(_owner_filter(part, uid) for part in value.get('$and', []))


def _body_and_lsn(response: Any) -> tuple[Any, int | None]:
    if isinstance(response, tuple) and len(response) == 3:
        body, status, headers = response
        if not 200 <= status < 300:
            raise RuntimeError('Pinecone mutation was not acknowledged')
        headers = {str(k).lower(): v for k, v in headers.items()}
        raw = headers.get('x-pinecone-request-lsn')
        return body, int(raw) if raw is not None else None
    return response, None


def _provider_mutation(index: Any, method: str, args: tuple, namespace: str, kwargs: dict) -> tuple[Any, int | None]:
    try:
        return _body_and_lsn(getattr(index, method)(*args, namespace=namespace, _return_http_data_only=False, **kwargs))
    except Exception as error:
        if method == 'delete' and is_missing_namespace(error):
            # Zero denotes proven namespace absence, not an acknowledged LSN.
            return {}, 0
        raise


class OwnerIndex:
    def __init__(self, index: Any, uid: str, *, index_name: str | None = None, firestore_client: Any = None):
        if not isinstance(cast(object, uid), str) or not uid.strip():
            raise ValueError('Pinecone owner is required')
        self.index = index
        self.uid = uid
        self.index_name = index_name or os.getenv('PINECONE_INDEX_NAME', '')
        if not self.index_name:
            raise ValueError('Pinecone index identity is required for owner routing')
        self.firestore_client = firestore_client
        self._deletion_lsns: dict[str, dict[str, int]] = {}
        self._deletion_revisions: dict[str, int] = {}

    def _key(self, family: str) -> state.PartitionKey:
        return state.PartitionKey(self.index_name, family, self.uid)

    def _route(self, family: str) -> str:
        return state.get_route(self._key(family), firestore_client=self.firestore_client).primary_namespace

    def _check_filter(self, value: Any) -> None:
        if not _owner_filter(value, self.uid):
            raise ValueError('Pinecone filter must constrain the authenticated owner')

    def query(self, *, namespace: str, **kwargs: Any) -> Any:
        self._check_filter(kwargs.get('filter'))
        return self.index.query(namespace=self._route(namespace), **kwargs)

    def fetch(self, *, ids: list[str], namespace: str, **kwargs: Any) -> Any:
        result = self.index.fetch(ids=ids, namespace=self._route(namespace), **kwargs)
        self._check_records(_field(result, 'vectors').values())
        return result

    def list(self, *, prefix: str, namespace: str, **kwargs: Any) -> Any:
        if not prefix.startswith(self.uid + '-'):
            raise ValueError('Pinecone listing requires an owner-scoped prefix')
        return self.index.list(prefix=prefix, namespace=self._route(namespace), **kwargs)

    def _check_records(self, records: Any) -> None:
        for record in records:
            if _field(record, 'metadata').get('uid') != self.uid:
                raise ValueError('Pinecone record owner does not match routing owner')

    def _mutate(self, method: str, args: tuple, family: str, kwargs: dict, ids: list[str]) -> Any:
        if any(
            name in kwargs
            for name in ('async_req', 'async_threadpool_executor', 'batch_size', '_return_http_data_only')
        ):
            raise ValueError('Partition writes require a single synchronous provider acknowledgement')
        key = self._key(family)
        filter_digest = (
            sha256(json.dumps(kwargs['filter'], sort_keys=True).encode()).hexdigest() if 'filter' in kwargs else None
        )
        ticket = state.begin_mutation(
            key,
            affected_ids=ids,
            full_owner=not ids,
            operation_kind=method,
            attempted_namespaces=[key.family, key.partition_namespace] if method == 'delete' else None,
            filter_digest=filter_digest,
            firestore_client=self.firestore_client,
        )
        other = key.partition_namespace if ticket.primary_namespace == key.family else key.family
        try:
            if method in {'upsert', 'update'}:
                # Admission makes an in-flight write visible to purge verification;
                # the fresh fence rejects writers that resumed after the purge.
                with external_write_fence(self.uid, firestore_client=self.firestore_client):
                    pass
            if ids and method in {'update', 'delete'}:
                targets = (ticket.primary_namespace, other) if method == 'delete' else (ticket.primary_namespace,)
                for target in targets:
                    existing = self.index.fetch(ids=ids, namespace=target)
                    self._check_records(_field(existing, 'vectors').values())
        except Exception:
            # Only reads/validation have occurred, so this is a known no-op.
            state.finish_mutation(key, ticket, firestore_client=self.firestore_client)
            raise
        try:
            body, lsn = _provider_mutation(self.index, method, args, ticket.primary_namespace, kwargs)
            if method == 'delete':
                # Privacy deletion also covers the unserved rollback copy.
                _provider_mutation(self.index, method, args, other, kwargs)
        except Exception:
            self._uncertain(key, ticket)
            raise
        state.finish_mutation(key, ticket, write_lsn=lsn, firestore_client=self.firestore_client)
        return body

    def _uncertain(self, key: state.PartitionKey, ticket: state.MutationTicket) -> None:
        try:
            state.mark_mutation_uncertain(key, ticket, firestore_client=self.firestore_client)
        except Exception:
            # A failed state write leaves the original durable pending marker.
            logger.error('Could not persist uncertain Pinecone operation key=%s', key.document_id)

    def upsert(self, *, vectors: Sequence[Mapping[str, Any]], namespace: str, **kwargs: Any) -> Any:
        self._check_records(vectors)
        return self._mutate('upsert', (), namespace, {'vectors': vectors, **kwargs}, [v['id'] for v in vectors])

    def update(self, id: str, *, namespace: str, **kwargs: Any) -> Any:
        metadata = kwargs.get('set_metadata', {})
        if 'uid' in metadata and metadata['uid'] != self.uid:
            raise ValueError('Pinecone updates cannot change record ownership')
        return self._mutate('update', (id,), namespace, kwargs, [id])

    def delete(self, *, namespace: str, **kwargs: Any) -> Any:
        if kwargs.get('delete_all'):
            raise ValueError('A bucket may contain other owners; delete_all is forbidden')
        if 'filter' in kwargs:
            self._check_filter(kwargs['filter'])
        elif not kwargs.get('ids'):
            raise ValueError('Pinecone delete requires scoped IDs or filter')
        return self._mutate('delete', (), namespace, kwargs, list(kwargs.get('ids', [])))

    def delete_all_copies(self, *, namespace: str, filter: dict) -> None:
        self._deletion_lsns.pop(namespace, None)
        self._deletion_revisions.pop(namespace, None)
        self._check_filter(filter)
        key = self._key(namespace)
        route = state.get_route(key, firestore_client=self.firestore_client)
        if route.mode == 'copying':
            if route.migration_token is None:
                raise state.PartitionStateError('Copying route lacks its migration token')
            if not route.pending_count:
                state.cancel_migration(key, route.migration_token, firestore_client=self.firestore_client)
        # Erase known copies even if earlier provider work is unresolved. Final
        # verification still refuses completion until those operations settle.
        dimension = _field(self.index.describe_index_stats(), 'dimension')
        ticket = state.begin_mutation(
            key,
            full_owner=True,
            operation_kind='delete',
            attempted_namespaces=[key.family, key.partition_namespace],
            filter_digest=sha256(json.dumps(filter, sort_keys=True).encode()).hexdigest(),
            firestore_client=self.firestore_client,
        )
        primary_lsn = None
        lsns = {}
        try:
            for target in (key.family, key.partition_namespace):
                _, lsn = _provider_mutation(self.index, 'delete', (), target, {'filter': filter})
                if lsn is None:
                    raise state.PartitionStateError('Pinecone delete did not provide a freshness receipt')
                if target == ticket.primary_namespace:
                    primary_lsn = lsn
        except Exception:
            self._uncertain(key, ticket)
            raise
        finished = state.finish_mutation(key, ticket, write_lsn=primary_lsn, firestore_client=self.firestore_client)
        # These records have no UID and cannot resurrect customer data. If a
        # barrier request fails, retry verification without poisoning the
        # already-acknowledged customer deletion with unrelated uncertainty.
        for target in (key.family, key.partition_namespace):
            _, lsn = _provider_mutation(self.index, 'upsert', (), target, {'vectors': [barrier_record(dimension)]})
            if lsn is None:
                raise state.PartitionStateError('Pinecone barrier did not provide a freshness receipt')
            lsns[target] = lsn
        self._deletion_lsns[namespace] = lsns
        self._deletion_revisions[namespace] = finished.revision

    def verify_empty_all_copies(self, *, namespace: str, filter: dict) -> None:
        self._check_filter(filter)
        key = self._key(namespace)
        route = state.get_route(key, firestore_client=self.firestore_client)
        if route.pending_count or route.uncertain_count or route.mode == 'copying':
            raise state.PartitionBusy('Account purge must wait for outstanding vector work')
        lsns = self._deletion_lsns.get(namespace)
        if lsns is None or self._deletion_revisions.get(namespace) != route.revision:
            raise state.PartitionStateError('Account purge lacks deletion freshness receipts')
        dimension = _field(self.index.describe_index_stats(), 'dimension')
        for target in (key.family, key.partition_namespace):
            for attempt in range(6):
                result, _, headers = self.index._query(
                    namespace=target,
                    vector=[1.0] + [0.0] * (dimension - 1),
                    filter=filter,
                    top_k=1,
                    _return_http_data_only=False,
                )
                indexed = int(headers.get('x-pinecone-max-indexed-lsn', 0 if lsns[target] == 0 else -1))
                if indexed >= lsns[target] and not _field(result, 'matches'):
                    break
                if attempt == 5:
                    raise state.PartitionBusy('Pinecone account purge is not yet visible')
                time.sleep(1)
        after = state.get_route(key, firestore_client=self.firestore_client)
        if after.revision != route.revision or after.pending_count or after.uncertain_count:
            raise state.PartitionBusy('Vector activity changed during purge verification')


def owner_index(index: Any, uid: str, *, index_name: str | None = None, firestore_client: Any = None) -> OwnerIndex:
    return OwnerIndex(index, uid, index_name=index_name, firestore_client=firestore_client)

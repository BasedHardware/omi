"""Transactional document store for batch scheduling; lazy, explicitly namespaced.

Writes are buffered until the body returns so all Firestore reads precede writes.
The transaction callback must be pure; it may be retried by Firestore.
"""

from copy import deepcopy
import os
import re
from typing import Any, Callable, Protocol, TypeVar

from google.cloud import firestore

from database._client import get_data_plane_firestore_client
from database.batch_pipeline_privacy import assert_batch_write_allowed
from database.batch_pipeline_recovery import quarantine_fenced
from utils.sync.stage import collection_name

T = TypeVar('T')


class Transaction(Protocol):
    def get(self, table: str, key: str) -> dict: ...
    def put(self, table: str, key: str, value: dict) -> None: ...
    def patch(self, table: str, key: str, fields: dict) -> None: ...
    def first_pending(self, owner_key: str) -> dict | None: ...
    def service_frontier(self, priority: int) -> float: ...
    def check_privacy(self, uid: str, conversation_ids=(), expected_generation: int | None = None) -> int: ...


class Store(Protocol):
    def run(self, body: Callable[[Transaction], T]) -> T: ...
    def due(self, state: str, now: float, limit: int) -> list[str]: ...
    def oldest(self, priority: int, *, ready_only: bool) -> float | None: ...
    def oldest_retry(self, priority: int) -> float | None: ...
    def control_candidate(self, priority: int, pool: str, now: float) -> str | None: ...
    def quarantine_fenced(self, segment_id: str, now: float) -> bool: ...


class FirestoreTransaction:
    def __init__(self, client: Any, namespace: str, transaction: Any):
        self.client = client
        self.namespace = namespace
        self.transaction = transaction
        self.cache: dict[tuple[str, str], dict] = {}
        self.writes: dict[tuple[str, str], dict] = {}
        self.patches: dict[tuple[str, str], dict] = {}

    def _ref(self, table: str, key: str):
        if table == 'conversations':
            uid, conversation_id = key.split('/', 1)
            return self.client.collection('users').document(uid).collection('conversations').document(conversation_id)
        if table == 'content':
            uid, content_id = key.split('/', 1)
            return (
                self.client.collection('users')
                .document(uid)
                .collection(collection_name('sync_content_ledger'))
                .document(content_id)
            )
        return self.client.collection(f'{self.namespace}_{table}').document(key)

    def get(self, table: str, key: str) -> dict:
        address = (table, key)
        if address not in self.cache:
            snapshot = self._ref(table, key).get(transaction=self.transaction)
            self.cache[address] = (snapshot.to_dict() or {}) if snapshot.exists else {}
        return deepcopy({**self.writes.get(address, self.cache[address]), **self.patches.get(address, {})})

    def put(self, table: str, key: str, value: dict) -> None:
        if table == 'conversations':
            raise ValueError('conversation admission requires a field patch, never a document set')
        self.writes[(table, key)] = deepcopy(value)

    def patch(self, table: str, key: str, fields: dict) -> None:
        if table != 'conversations' or set(fields) != {'record_lane_owner'}:
            raise ValueError('only the conversation route owner may be patched by admission')
        self.patches.setdefault((table, key), {}).update(deepcopy(fields))

    def first_pending(self, owner_key: str) -> dict | None:
        return first_pending(self.client, self.namespace, owner_key, transaction=self.transaction)

    def service_frontier(self, priority: int) -> float:
        return service_frontier(self.client, self.namespace, priority, transaction=self.transaction)

    def check_privacy(self, uid: str, conversation_ids=(), expected_generation: int | None = None) -> int:
        return assert_batch_write_allowed(
            self.client,
            self.transaction,
            uid,
            conversation_ids=conversation_ids,
            expected_generation=expected_generation,
        )

    def flush(self):
        if len(self.writes) + len(self.patches) > 450:
            raise RuntimeError('batch transaction write budget exceeded')
        guarded = set()
        for (table, key), value in self.writes.items():
            if table not in {'jobs', 'results'}:
                continue
            job = value if table == 'jobs' else self.get('jobs', key)
            identity = (job['owner_id'], job.get('conversation_id'), job.get('privacy_generation'))
            if identity in guarded:
                continue
            guarded.add(identity)
            generation = assert_batch_write_allowed(
                self.client,
                self.transaction,
                job['owner_id'],
                conversation_ids=(job['conversation_id'],) if job.get('conversation_id') else (),
                expected_generation=job.get('privacy_generation'),
            )
            if table == 'jobs' and value.get('privacy_generation') is None:
                value['privacy_generation'] = generation
        for (table, key), value in self.writes.items():
            self.transaction.set(self._ref(table, key), value)
        for (table, key), fields in self.patches.items():
            self.transaction.update(self._ref(table, key), fields)


class FirestoreStore:
    def __init__(self, namespace: str, *, firestore_client: Any = None):
        # Require a stage-qualified name; never infer dev from the customer project.
        if namespace not in {'batch_pipeline_prod', 'batch_pipeline_dev'} and not re.fullmatch(
            r'batch_pipeline_test_[a-z0-9_]{1,40}', namespace
        ):
            raise ValueError('explicit batch_pipeline_{prod,dev,test_<id>} namespace required')
        self.namespace = namespace
        self._client = firestore_client
        self._require_stage()

    def _require_stage(self):
        if self.namespace.startswith('batch_pipeline_test_'):
            host = os.getenv('FIRESTORE_EMULATOR_HOST', '')
            if not host.startswith(('127.0.0.1:', 'localhost:')):
                raise RuntimeError('test namespace requires a loopback emulator; no cloud fallback')
            if self._client is not None and getattr(self._client, '_emulator_host', None) != host:
                raise RuntimeError('injected test client must be bound to the loopback emulator')
        else:
            stage = os.getenv('OMI_ENV_STAGE', '').strip().lower()
            if stage not in {'prod', 'dev'} or self.namespace != f'batch_pipeline_{stage}':
                raise RuntimeError('batch namespace must match explicit runtime stage')

    @property
    def client(self):
        self._require_stage()
        return self._client if self._client is not None else get_data_plane_firestore_client()

    def run(self, body):
        @firestore.transactional
        def commit(transaction):
            view = FirestoreTransaction(self.client, self.namespace, transaction)
            result = body(view)
            view.flush()
            return result

        return commit(self.client.transaction())

    def due(self, state: str, now: float, limit: int = 100) -> list[str]:
        return due(self.client, self.namespace, state, now, limit)

    def oldest(self, priority: int, *, ready_only: bool = False) -> float | None:
        return oldest(self.client, self.namespace, priority, ready_only=ready_only)

    def control_candidate(self, priority: int, pool: str, now: float) -> str | None:
        return control_candidate(self.client, self.namespace, priority, pool, now)

    def oldest_retry(self, priority: int) -> float | None:
        return oldest_retry(self.client, self.namespace, priority)

    def quarantine_fenced(self, segment_id: str, now: float) -> bool:
        return quarantine_fenced(self.client, self.namespace, segment_id, now)

    def projection_pending(self, limit: int = 100) -> list[str]:
        return projection_pending(self.client, self.namespace, limit)


def projection_pending(client: Any, namespace: str, limit: int = 100) -> list[str]:
    docs = (
        client.collection(f'{namespace}_results')
        .where('projection_state', 'in', ['pending', 'persisted', 'ready'])
        .order_by('committed_at')
        .limit(max(1, min(limit, 100)))
        .stream()
    )
    return [doc.id for doc in docs]


def first_pending(client: Any, namespace: str, owner_key: str, *, transaction: Any = None) -> dict | None:
    docs = list(
        client.collection(f'{namespace}_jobs')
        .where('owner_key', '==', owner_key)
        .where('merge_pending', '==', True)
        .order_by('capture_at')
        .order_by('segment_id')
        .limit(1)
        .stream(transaction=transaction)
    )
    return docs[0].to_dict() if docs else None


def due(client: Any, namespace: str, state: str, now: float, limit: int = 100) -> list[str]:
    if state not in {'leased', 'retry', 'result_ready', 'record_pending'}:
        raise ValueError('only recoverable states may be scanned')
    field = {
        'leased': 'lease_until',
        'retry': 'available_at',
        'result_ready': 'enqueued_at',
        'record_pending': 'available_at',
    }[state]
    docs = (
        client.collection(f'{namespace}_jobs')
        .where('state', '==', state)
        .where(field, '<=', now)
        .order_by(field)
        .limit(max(1, min(limit, 100)))
        .stream()
    )
    return [doc.id for doc in docs]


def oldest(client: Any, namespace: str, priority: int, *, ready_only: bool = False) -> float | None:
    query = client.collection(f'{namespace}_jobs').where('priority', '==', priority)
    query = query.where('state', '==', 'ready') if ready_only else query.where('merge_pending', '==', True)
    docs = list(query.order_by('enqueued_at').limit(1).stream())
    return docs[0].to_dict()['enqueued_at'] if docs else None


def control_candidate(client: Any, namespace: str, priority: int, pool: str, now: float) -> str | None:
    if priority not in (0, 1, 2) or pool not in {'batch', 'live'}:
        raise ValueError('bounded priority and pool required')
    prefix = f'p{priority}_'
    service, available = prefix + 'service', prefix + pool + '_available_at'
    docs = list(
        client.collection(f'{namespace}_control')
        .where(prefix + 'active', '==', True)
        .where(service, '>=', 0)
        .where(available, '<=', now)
        .order_by(service)
        .order_by(available)
        .limit(1)
        .stream()
    )
    return docs[0].id if docs else None


def oldest_retry(client: Any, namespace: str, priority: int) -> float | None:
    docs = list(
        client.collection(f'{namespace}_jobs')
        .where('priority', '==', priority)
        .where('retry_started_at', '>=', 0)
        .order_by('retry_started_at')
        .limit(1)
        .stream()
    )
    return docs[0].to_dict()['retry_started_at'] if docs else None


def service_frontier(client: Any, namespace: str, priority: int, *, transaction: Any = None) -> float:
    if priority not in (0, 1, 2):
        raise ValueError('bounded priority required')
    name = f'p{priority}_service'
    docs = list(
        client.collection(f'{namespace}_control')
        .order_by(name, direction=firestore.Query.DESCENDING)
        .limit(1)
        .stream(transaction=transaction)
    )
    return docs[0].to_dict()[name] if docs else 0.0

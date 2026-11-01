"""Uncached owner routing and mutation fences for Pinecone partition migrations.

Provider IO happens outside these transactions. An unfinished mutation never
expires: an unknown provider outcome must block migration until reconciled.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from functools import wraps
import json
from typing import Any, Mapping, Sequence, cast
from uuid import uuid4

from database import _client as firestore_clients
from database.account_deletion_policy import account_deletion_marker_blocks_access

COLLECTION = 'pinecone_partition_routes'
FAMILIES = frozenset({'ns1', 'ns2', 'ns3', 'ns4', 'ns_x', 'ns_tchunks', 'workstream-association-v1'})
BUCKET_COUNT = 256
MAX_PENDING = 128
MAX_AFFECTED_IDS = 1000
OPERATION_KINDS = frozenset({'unknown', 'upsert', 'update', 'delete', 'copy_upsert', 'copy_delete'})


class PartitionStateError(RuntimeError):
    """Routing authority is malformed or unavailable; never guess a namespace."""


class PartitionBusy(PartitionStateError):
    """An outstanding mutation or migration prevents the transition."""


class PartitionConflict(PartitionStateError):
    """The evidence no longer describes the current generation."""


@dataclass(frozen=True)
class PartitionKey:
    index_name: str
    family: str
    uid: str

    def __post_init__(self) -> None:
        if self.family not in FAMILIES:
            raise ValueError('unknown Pinecone family')
        for value in (self.index_name, self.uid):
            if not isinstance(cast(object, value), str) or not value.strip() or len(value) > 512:
                raise ValueError('index name and owner must be nonempty bounded strings')

    @property
    def document_id(self) -> str:
        return sha256(json.dumps([self.index_name, self.family, self.uid]).encode()).hexdigest()

    @property
    def partition_namespace(self) -> str:
        bucket = int.from_bytes(sha256(self.uid.encode()).digest()[:4], 'big') % BUCKET_COUNT
        return f'{self.family}-p1-{bucket:02x}'


@dataclass(frozen=True)
class Route:
    mode: str
    primary_namespace: str
    source_namespace: str
    target_namespace: str | None
    revision: int
    pending_count: int
    migration_token: str | None
    latest_write_lsn: int
    unknown_freshness: bool
    uncertain_count: int


@dataclass(frozen=True)
class MutationTicket:
    key_id: str
    token: str
    revision: int
    primary_namespace: str
    migration_token: str | None


def _client(firestore_client: Any | None) -> Any:
    if firestore_client is not None:
        return firestore_client
    return firestore_clients.get_data_plane_firestore_client()


def _transactional(function: Any) -> Any:
    # Disabled adapters and import-isolated worker tests must not initialize
    # provider SDKs. Resolve this SDK boundary only when a transaction runs.
    @wraps(function)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        from google.cloud.firestore_v1 import transactional

        return transactional(function)(*args, **kwargs)

    setattr(wrapped, 'to_wrap', function)
    return wrapped


def _document(client: Any, key: PartitionKey) -> Any:
    return client.collection(COLLECTION).document(key.document_id)


def _read(ref: Any, key: PartitionKey, transaction: Any | None = None) -> dict[str, Any]:
    snapshot = ref.get(transaction=transaction) if transaction is not None else ref.get()
    return _snapshot_row(snapshot, key)


def _snapshot_row(snapshot: Any, key: PartitionKey) -> dict[str, Any]:
    if not snapshot.exists:
        return {
            'schema_version': 1,
            'index_name': key.index_name,
            'family': key.family,
            'uid': key.uid,
            'mode': 'legacy',
            'primary_namespace': key.family,
            'revision': 0,
            'pending': {},
            'latest_write_lsn': 0,
            'unknown_freshness': True,
            'uncertain_count': 0,
        }
    row = snapshot.to_dict()
    if not isinstance(row, dict):
        raise PartitionStateError('partition route is not an object')
    if (
        type(row.get('schema_version')) is not int
        or row['schema_version'] != 1
        or (row.get('index_name'), row.get('family'), row.get('uid')) != (key.index_name, key.family, key.uid)
        or row.get('mode') not in {'legacy', 'copying', 'partitioned'}
        or type(row.get('revision')) is not int
        or row['revision'] < 0
        or not isinstance(row.get('pending'), dict)
        or len(row['pending']) > MAX_PENDING
        or type(row.get('latest_write_lsn')) is not int
        or row['latest_write_lsn'] < 0
        or type(row.get('unknown_freshness')) is not bool
        or type(row.get('uncertain_count')) is not int
        or row['uncertain_count'] < 0
    ):
        raise PartitionStateError('partition route identity or revision is invalid')
    namespaces = {key.family, key.partition_namespace}
    if row.get('primary_namespace') not in namespaces:
        raise PartitionStateError('partition primary namespace is invalid')
    mode = row['mode']
    if mode == 'copying':
        if (
            not _valid_token(row.get('migration_token'))
            or row.get('target_namespace') not in namespaces - {row['primary_namespace']}
            or row.get('target_mode') not in {'legacy', 'partitioned'}
            or row['target_namespace'] != (key.family if row['target_mode'] == 'legacy' else key.partition_namespace)
        ):
            raise PartitionStateError('partition migration is invalid')
    elif row['primary_namespace'] != (key.family if mode == 'legacy' else key.partition_namespace):
        raise PartitionStateError('partition mode contradicts its primary')
    for token, pending in row['pending'].items():
        if (
            not _valid_token(token)
            or not isinstance(pending, dict)
            or type(pending.get('revision')) is not int
            or not 0 < pending['revision'] <= row['revision']
            or pending.get('primary_namespace') != row['primary_namespace']
            or pending.get('migration_token') != row.get('migration_token')
        ):
            raise PartitionStateError('partition pending mutation is invalid')
    return row


def _route(row: Mapping[str, Any]) -> Route:
    return Route(
        mode=row['mode'],
        primary_namespace=row['primary_namespace'],
        source_namespace=row['primary_namespace'],
        target_namespace=row.get('target_namespace'),
        revision=row['revision'],
        pending_count=len(row['pending']),
        migration_token=row.get('migration_token'),
        latest_write_lsn=row['latest_write_lsn'],
        unknown_freshness=row['unknown_freshness'],
        uncertain_count=row['uncertain_count'],
    )


def _valid_token(token: Any) -> bool:
    return isinstance(token, str) and 0 < len(token) <= 64 and all(c.isalnum() or c in '-_' for c in token)


def get_route(key: PartitionKey, *, firestore_client: Any | None = None) -> Route:
    """Read fresh authority, registering a first-seen owner for future sweeps.

    Existing rows require one read and no write. A missing row is checked again
    transactionally so registration cannot overwrite concurrent activity.
    """
    client = _client(firestore_client)
    ref = _document(client, key)
    snapshot = ref.get()
    if snapshot.exists:
        return _route(_snapshot_row(snapshot, key))
    return _register_missing_route(client.transaction(), ref, key)


@_transactional
def _register_missing_route(transaction: Any, ref: Any, key: PartitionKey) -> Route:
    snapshot = ref.get(transaction=transaction)
    row = _snapshot_row(snapshot, key)
    if not snapshot.exists:
        transaction.set(ref, row)
    return _route(row)


def begin_mutation(
    key: PartitionKey,
    *,
    affected_ids: Sequence[str] = (),
    full_owner: bool = False,
    operation_id: str | None = None,
    operation_kind: str = 'unknown',
    attempted_namespaces: Sequence[str] | None = None,
    filter_digest: str | None = None,
    firestore_client: Any | None = None,
) -> MutationTicket:
    """Admit one provider mutation and return its sole primary namespace.

    ``full_owner`` is required for filtered deletes or any mutation whose exact
    affected provider IDs are unknown. The migration runner must reconcile the
    full owner's copied inventory for such an operation.
    """
    if isinstance(affected_ids, (str, bytes)) or type(full_owner) is not bool:
        raise ValueError('invalid affected vector scope')
    ids = list(dict.fromkeys(affected_ids))
    if (
        len(ids) > MAX_AFFECTED_IDS
        or any(not isinstance(cast(object, item), str) or not item or len(item) > 4096 for item in ids)
        or len(json.dumps(ids).encode()) > 256_000
        or (not ids and not full_owner)
    ):
        raise ValueError('bounded affected IDs or full_owner scope is required')
    token = operation_id or uuid4().hex
    if not _valid_token(token):
        raise ValueError('invalid operation id')
    if operation_kind not in OPERATION_KINDS:
        raise ValueError('unknown mutation operation kind')
    namespaces = list(dict.fromkeys(attempted_namespaces)) if attempted_namespaces is not None else None
    if namespaces is not None and (
        isinstance(attempted_namespaces, (str, bytes))
        or not namespaces
        or any(namespace not in {key.family, key.partition_namespace} for namespace in namespaces)
    ):
        raise ValueError('attempted namespaces must be this owner family\'s known copies')
    if filter_digest is not None and not _is_digest(filter_digest):
        raise ValueError('filter_digest must be a SHA256 digest')
    client = _client(firestore_client)
    return _begin_mutation(
        client.transaction(),
        _document(client, key),
        key,
        token,
        ids,
        full_owner,
        operation_kind,
        namespaces,
        filter_digest,
    )


@_transactional
def _begin_mutation(
    transaction: Any,
    ref: Any,
    key: PartitionKey,
    token: str,
    ids: list[str],
    full_owner: bool,
    operation_kind: str,
    namespaces: list[str] | None,
    filter_digest: str | None,
) -> MutationTicket:
    row = _read(ref, key, transaction)
    if token in row['pending']:
        raise PartitionBusy('mutation token is already pending; do not repeat uncertain provider IO')
    if len(row['pending']) >= MAX_PENDING:
        raise PartitionBusy('too many unresolved Pinecone mutations')
    operation_ref = ref.collection('operations').document(token)
    if operation_ref.get(transaction=transaction).exists:
        raise PartitionConflict('operation id already exists in the mutation journal')
    row['revision'] += 1
    entry = {
        'revision': row['revision'],
        'primary_namespace': row['primary_namespace'],
        'migration_token': row.get('migration_token'),
    }
    scope = {'affected_ids': sorted(ids), 'full_owner': full_owner, 'filter_digest': filter_digest}
    admission = {
        **entry,
        **scope,
        'status': 'pending',
        'operation_kind': operation_kind,
        'attempted_namespaces': namespaces or [row['primary_namespace']],
        'scope_digest': sha256(json.dumps(scope, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
    }
    row['pending'][token] = entry
    transaction.set(ref, row)
    transaction.set(operation_ref, admission)
    return MutationTicket(key.document_id, token, row['revision'], row['primary_namespace'], row.get('migration_token'))


def finish_mutation(
    key: PartitionKey,
    ticket: MutationTicket,
    *,
    write_lsn: int | None = None,
    firestore_client: Any | None = None,
) -> Route:
    """Call ONLY after the primary acknowledged success, never from ``finally``.

    A failed or timed-out provider operation intentionally retains its pending
    marker. Retrying a completed finish is harmless and never repeats IO.
    """
    if ticket.key_id != key.document_id:
        raise PartitionConflict('mutation ticket belongs to a different owner/family/index')
    if write_lsn is not None and (type(write_lsn) is not int or write_lsn < 0):
        raise ValueError('write_lsn must be a nonnegative integer')
    client = _client(firestore_client)
    return _finish_mutation(client.transaction(), _document(client, key), key, ticket, write_lsn)


@_transactional
def _finish_mutation(
    transaction: Any, ref: Any, key: PartitionKey, ticket: MutationTicket, write_lsn: int | None
) -> Route:
    row = _read(ref, key, transaction)
    pending = row['pending'].get(ticket.token)
    if pending is None:
        return _route(row)
    expected = {
        'revision': ticket.revision,
        'primary_namespace': ticket.primary_namespace,
        'migration_token': ticket.migration_token,
    }
    if pending != expected:
        raise PartitionConflict('mutation ticket does not match admission')
    del row['pending'][ticket.token]
    row['revision'] += 1
    if write_lsn is None:
        row['unknown_freshness'] = True
    else:
        row['latest_write_lsn'] = max(row['latest_write_lsn'], write_lsn)
    transaction.set(ref, row)
    operation_ref = ref.collection('operations').document(ticket.token)
    if ticket.migration_token is None:
        transaction.delete(operation_ref)
    else:
        transaction.update(operation_ref, {'status': 'completed'})
    return _route(row)


def mark_mutation_uncertain(key: PartitionKey, ticket: MutationTicket, *, firestore_client: Any | None = None) -> Route:
    """Preserve an unknown outcome without exhausting normal mutation slots.

    The caller has stopped awaiting the provider, but this does NOT assert the
    provider stopped executing. Migration remains blocked indefinitely until an
    operator proves final state and reconciles the durable operation record.
    """
    if ticket.key_id != key.document_id:
        raise PartitionConflict('mutation ticket belongs to a different owner/family/index')
    client = _client(firestore_client)
    return _mark_mutation_uncertain(client.transaction(), _document(client, key), key, ticket)


@_transactional
def _mark_mutation_uncertain(transaction: Any, ref: Any, key: PartitionKey, ticket: MutationTicket) -> Route:
    row = _read(ref, key, transaction)
    pending = row['pending'].get(ticket.token)
    if pending is None:
        return _route(row)
    if pending != {
        'revision': ticket.revision,
        'primary_namespace': ticket.primary_namespace,
        'migration_token': ticket.migration_token,
    }:
        raise PartitionConflict('mutation ticket does not match admission')
    del row['pending'][ticket.token]
    row['revision'] += 1
    row['uncertain_count'] += 1
    row['unknown_freshness'] = True
    transaction.set(ref, row)
    operation_ref = ref.collection('operations').document(ticket.token)
    transaction.update(operation_ref, {'status': 'uncertain'})
    return _route(row)


def _is_digest(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in '0123456789abcdef' for char in value)


def _artifact_evidence(value: Mapping[str, Any]) -> bool:
    reference = value.get('artifact_ref')
    return (
        isinstance(reference, str) and 0 < len(reference.strip()) <= 1024 and _is_digest(value.get('artifact_sha256'))
    )


def reconcile_mutation(
    key: PartitionKey,
    operation_id: str,
    expected_revision: int,
    receipt: Mapping[str, Any],
    *,
    firestore_client: Any | None = None,
) -> Route:
    """Operator-only recovery of a definitively settled provider operation.

    This is not an HTTP API or a timeout escape. The operator must inspect and
    preserve the referenced provider trace artifacts and authoritative scope
    reconciliation; this module validates their binding, not their truth.
    Every admitted namespace needs a final rejection or an acknowledged write
    indexed through its LSN. A timeout, age, boolean-only claim or probe of an
    unrelated request cannot settle an unknown original request.
    """
    if (
        not _valid_token(operation_id)
        or type(expected_revision) is not int
        or expected_revision < 0
        or not isinstance(cast(object, receipt), Mapping)
        or len(json.dumps(dict(receipt)).encode()) > 32_000
    ):
        raise ValueError('bounded recovery receipt and exact revision are required')
    client = _client(firestore_client)
    return _reconcile_mutation(
        client.transaction(), _document(client, key), key, operation_id, expected_revision, dict(receipt)
    )


def _validate_recovery_receipt(key: PartitionKey, operation_id: str, operation: dict, receipt: dict) -> dict[str, int]:
    ids, full_owner = operation.get('affected_ids'), operation.get('full_owner')
    if (
        not isinstance(ids, list)
        or any(not isinstance(vector_id, str) or not vector_id for vector_id in ids)
        or type(full_owner) is not bool
        or (not ids and not full_owner)
        or not _is_digest(operation.get('scope_digest'))
    ):
        raise PartitionStateError('admitted operation scope is malformed')
    scope = {'affected_ids': ids, 'full_owner': full_owner, 'filter_digest': operation.get('filter_digest')}
    digest = sha256(json.dumps(scope, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if digest != operation['scope_digest']:
        raise PartitionStateError('admitted operation scope digest does not match its inventory')
    if (
        operation.get('operation_kind') not in OPERATION_KINDS - {'unknown'}
        or receipt.get('key_id') != key.document_id
        or receipt.get('operation_id') != operation_id
        or receipt.get('operation_kind') != operation.get('operation_kind')
        or receipt.get('admission_revision') != operation.get('revision')
        or receipt.get('scope_digest') != operation.get('scope_digest')
        or not _valid_token(receipt.get('receipt_id'))
    ):
        raise PartitionConflict('recovery receipt does not identify the admitted mutation')
    reconciliation = receipt.get('reconciliation')
    if (
        not isinstance(reconciliation, dict)
        or reconciliation.get('authoritative_reconciled') is not True
        or reconciliation.get('scope_digest') != operation.get('scope_digest')
        or not _artifact_evidence(reconciliation)
    ):
        raise PartitionConflict('authoritative affected-scope reconciliation evidence is required')
    outcomes = receipt.get('provider_outcomes')
    namespaces = operation.get('attempted_namespaces')
    if (
        not isinstance(namespaces, list)
        or not namespaces
        or any(namespace not in {key.family, key.partition_namespace} for namespace in namespaces)
        or not isinstance(outcomes, list)
        or len(outcomes) != len(namespaces)
    ):
        raise PartitionConflict('every attempted namespace requires provider evidence')
    observed: set[str] = set()
    lsns: dict[str, int] = {}
    for outcome in outcomes:
        if not isinstance(outcome, dict):
            raise PartitionConflict('provider outcome is malformed')
        namespace = outcome.get('namespace')
        request_id = outcome.get('request_id')
        if (
            not isinstance(namespace, str)
            or namespace not in namespaces
            or namespace in observed
            or not isinstance(request_id, str)
            or not 0 < len(request_id.strip()) <= 256
            or outcome.get('original_request_settled') is not True
            or not _artifact_evidence(outcome)
        ):
            raise PartitionConflict('provider evidence is missing its original request identity')
        observed.add(namespace)
        if outcome.get('disposition') == 'rejected':
            if (
                type(outcome.get('http_status')) is not int
                or outcome['http_status'] not in {400, 401, 403, 404, 413, 422}
                or outcome.get('no_mutation') is not True
            ):
                raise PartitionConflict('provider rejection does not prove absence of mutation')
        elif outcome.get('disposition') == 'applied':
            write_lsn, indexed_lsn = outcome.get('write_lsn'), outcome.get('indexed_lsn')
            if type(write_lsn) is not int or type(indexed_lsn) is not int or not 0 < write_lsn <= indexed_lsn:
                raise PartitionConflict('provider completion lacks an indexed acknowledged write')
            lsns[namespace] = write_lsn
        else:
            raise PartitionConflict('unknown provider outcome cannot be reconciled')
    return lsns


@_transactional
def _reconcile_mutation(
    transaction: Any, ref: Any, key: PartitionKey, operation_id: str, expected_revision: int, receipt: dict
) -> Route:
    row = _read(ref, key, transaction)
    operation_ref = ref.collection('operations').document(operation_id)
    snapshot = operation_ref.get(transaction=transaction)
    operation = snapshot.to_dict() if snapshot.exists else None
    if row['revision'] != expected_revision:
        raise PartitionConflict('routing revision changed; reverify recovery evidence')
    if receipt.get('revision') != expected_revision:
        raise PartitionConflict('recovery evidence belongs to another routing revision')
    if not isinstance(operation, dict) or operation.get('status') not in {'pending', 'uncertain'}:
        raise PartitionConflict('operation is absent or already settled')
    if set(row['pending']) - {operation_id}:
        raise PartitionBusy('other active mutations must drain before recovery')
    is_pending = operation_id in row['pending']
    if (operation['status'] == 'pending') != is_pending:
        raise PartitionStateError('operation status contradicts active admission')
    if not is_pending and row['uncertain_count'] <= 0:
        raise PartitionStateError('uncertain operation has no routing counter')
    lsns = _validate_recovery_receipt(key, operation_id, operation, receipt)
    if is_pending:
        admission = row['pending'][operation_id]
        if any(
            admission.get(field) != operation.get(field)
            for field in ('revision', 'primary_namespace', 'migration_token')
        ):
            raise PartitionStateError('pending operation identity changed')
        del row['pending'][operation_id]
    else:
        row['uncertain_count'] -= 1
    row['revision'] += 1
    row['latest_write_lsn'] = max(row['latest_write_lsn'], lsns.get(row['primary_namespace'], 0))
    # Recovery of one operation cannot establish freshness for other historic
    # writes. The migration runner must still establish its normal barrier.
    row['unknown_freshness'] = True
    transaction.set(ref, row)
    transaction.update(operation_ref, {'status': 'reconciled', 'recovery_receipt': receipt})
    return _route(row)


def begin_migration(
    key: PartitionKey, token: str, *, rollback: bool = False, firestore_client: Any | None = None
) -> Route:
    """Reserve a non-expiring migration; any pending old operation blocks it."""
    if not _valid_token(token):
        raise ValueError('invalid migration token')
    client = _client(firestore_client)
    deletion_ref = client.collection('account_deletions').document(key.uid)
    return _begin_migration(client.transaction(), _document(client, key), key, token, rollback, deletion_ref)


def begin_rollback(key: PartitionKey, token: str, *, firestore_client: Any | None = None) -> Route:
    """Rollback is a fresh verified migration, never a direct route toggle."""
    return begin_migration(key, token, rollback=True, firestore_client=firestore_client)


def cancel_migration(key: PartitionKey, token: str, *, firestore_client: Any | None = None) -> Route:
    """Invalidate a quiet migration without changing the served primary.

    This does not purge the unserved target. Deletion callers must separately
    purge both namespaces and verify absence after all admitted work drains.
    """
    if not _valid_token(token):
        raise ValueError('invalid migration token')
    client = _client(firestore_client)
    return _cancel_migration(client.transaction(), _document(client, key), key, token)


@_transactional
def _cancel_migration(transaction: Any, ref: Any, key: PartitionKey, token: str) -> Route:
    row = _read(ref, key, transaction)
    if row['mode'] != 'copying' or row['migration_token'] != token:
        raise PartitionConflict('migration token does not own the route')
    if row['pending']:
        raise PartitionBusy('unfinished provider mutations block cancellation')
    row['mode'] = 'legacy' if row['primary_namespace'] == key.family else 'partitioned'
    row['revision'] += 1
    for field in ('target_mode', 'target_namespace', 'migration_token'):
        row.pop(field, None)
    transaction.set(ref, row)
    return _route(row)


@_transactional
def _begin_migration(
    transaction: Any, ref: Any, key: PartitionKey, token: str, rollback: bool, deletion_ref: Any
) -> Route:
    row = _read(ref, key, transaction)
    deletion_snapshot = deletion_ref.get(transaction=transaction)
    deletion = deletion_snapshot.to_dict() if deletion_snapshot.exists else {}
    if not isinstance(deletion, dict):
        raise PartitionStateError('account deletion authority is malformed')
    if account_deletion_marker_blocks_access(
        marker_exists=deletion_snapshot.exists, raw_status=deletion.get('wipe_status')
    ):
        raise PartitionBusy('account deletion blocks partition migration')
    if row['mode'] == 'copying':
        if row['migration_token'] == token and row['target_mode'] == ('legacy' if rollback else 'partitioned'):
            return _route(row)
        raise PartitionBusy('another migration owns this route')
    if row['pending'] or row['uncertain_count']:
        raise PartitionBusy('unfinished provider mutations block migration')
    if row['mode'] != ('partitioned' if rollback else 'legacy'):
        raise PartitionConflict('migration direction does not match the primary')
    row.update(
        mode='copying',
        target_namespace=key.family if rollback else key.partition_namespace,
        target_mode='legacy' if rollback else 'partitioned',
        migration_token=token,
        revision=row['revision'] + 1,
    )
    transaction.set(ref, row)
    return _route(row)


def cutover(
    key: PartitionKey,
    token: str,
    expected_revision: int,
    receipt: Mapping[str, Any],
    *,
    firestore_client: Any | None = None,
) -> Route:
    """Switch only with fresh external parity evidence for this exact revision.

    The caller must prove provider freshness, complete owner inventory parity
    and correct metadata/values/absence before supplying this receipt. Counts
    alone are not parity. This module cannot itself prove provider visibility.
    """
    if not isinstance(cast(object, receipt), Mapping):
        raise ValueError('a verification receipt is required')
    if type(expected_revision) is not int or expected_revision < 0 or not _valid_token(token):
        raise ValueError('invalid cutover generation')
    client = _client(firestore_client)
    return _cutover(client.transaction(), _document(client, key), key, token, expected_revision, dict(receipt))


@_transactional
def _cutover(
    transaction: Any, ref: Any, key: PartitionKey, token: str, revision: int, receipt: dict[str, Any]
) -> Route:
    row = _read(ref, key, transaction)
    if row['mode'] != 'copying' or row['migration_token'] != token or row['revision'] != revision:
        raise PartitionConflict('migration generation changed; reverify before cutover')
    if row['pending'] or row['uncertain_count']:
        raise PartitionBusy('unfinished provider mutations block cutover')
    if (
        receipt.get('passed') is not True
        or receipt.get('freshness_verified') is not True
        or receipt.get('key_id') != key.document_id
        or receipt.get('migration_token') != token
        or receipt.get('revision') != revision
        or receipt.get('source_namespace') != row['primary_namespace']
        or receipt.get('target_namespace') != row['target_namespace']
        or not _valid_token(receipt.get('receipt_id'))
    ):
        raise PartitionConflict('verification receipt does not authorize this cutover')
    source_indexed_lsn = receipt.get('source_indexed_lsn')
    target_write_lsn = receipt.get('target_write_lsn')
    target_indexed_lsn = receipt.get('target_indexed_lsn')
    if (
        type(source_indexed_lsn) is not int
        or type(target_write_lsn) is not int
        or type(target_indexed_lsn) is not int
        or min(source_indexed_lsn, target_write_lsn, target_indexed_lsn) < 0
        or source_indexed_lsn < row['latest_write_lsn']
        or target_indexed_lsn < target_write_lsn
    ):
        raise PartitionConflict('provider indexing has not reached the acknowledged writes')
    if row['unknown_freshness']:
        barrier = receipt.get('source_barrier_lsn')
        if type(barrier) is not int or barrier <= 0 or not row['latest_write_lsn'] <= barrier <= source_indexed_lsn:
            raise PartitionConflict('source requires an acknowledged freshness barrier after the quiet window')
    row.update(
        mode=row['target_mode'],
        primary_namespace=row['target_namespace'],
        revision=row['revision'] + 1,
        last_receipt_id=receipt['receipt_id'],
        latest_write_lsn=target_write_lsn,
        unknown_freshness=False,
    )
    for field in ('target_mode', 'target_namespace', 'migration_token'):
        row.pop(field, None)
    transaction.set(ref, row)
    return _route(row)

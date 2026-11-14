"""Bounded, retryable erasure of top-level batch state and referenced objects."""

from collections.abc import Callable, Iterable
from datetime import datetime, timedelta, timezone
from config.batch_pipeline import scheduler_control_key
from typing import Any

from google.cloud import firestore

from database._client import get_data_plane_firestore_client
from database import batch_pipeline_privacy_queries as queries
from database.batch_pipeline_privacy import advance_privacy_generation, finish_privacy_purge, privacy_owner_key
from database.batch_pipeline_shadow_hook import mirror_refresh, purge_owner as purge_jobstore_owner
from database.batch_pipeline_allowance_hold import STATE as ALLOWANCE_HELD, OWNERS as ALLOWANCE_OWNERS

NAMESPACES = ('batch_pipeline_prod', 'batch_pipeline_dev')
PAGE_SIZE = 100


def _belongs(data: dict, conversation_id: str | None) -> bool:
    if conversation_id is None:
        return True
    binding = data.get('projection_binding') or {}
    identities = {
        data.get('conversation_id'),
        (data.get('item') or {}).get('conversation_id'),
        data.get('source_conversation_id'),
        (data.get('projection_binding') or {}).get('target_conversation_id'),
        *(data.get('conversation_ids') or []),
        *(data.get('source_conversation_ids') or []),
    }
    if binding and 'capture_at' in data:
        from utils.sync.capture import chunk_identity

        identities.add(
            chunk_identity(
                binding['owner_id'],
                binding.get('source', 'omi'),
                binding.get('client_device_id'),
                binding.get('is_locked', False),
                data['capture_at'],
            )
        )
    identities.add((data.get('projection') or {}).get('conversation_id'))
    return conversation_id in identities


def _references(data: dict) -> set[str]:
    result = data.get('result') or {}
    return {uri for uri in (data.get('audio_uri'), result.get('result_uri'), data.get('uri')) if uri}


def _delete_job(
    client: Any,
    namespace: str,
    snapshot: Any,
    *,
    retain_ordering: bool,
    fence: Callable[[Any], None] | None = None,
) -> None:
    """Unlink one job while contending on scheduler control/queue fences.

    ``fence`` re-proves the caller's deletion authority inside this same
    transaction, so the erase cannot commit after that authority is lost.
    """
    touched: list[tuple[str, str]] = []  # A2 shadow: documents to re-copy after commit

    @firestore.transactional
    def remove(transaction):
        touched.clear()
        if fence is not None:
            fence(transaction)
        job = snapshot.reference.get(transaction=transaction).to_dict() or {}
        if not job:
            return
        key = job['owner_key']
        result_ref = client.collection(f'{namespace}_results').document(snapshot.id)
        result = result_ref.get(transaction=transaction).to_dict() or {}
        owner_ref = client.collection(f'{namespace}_owners').document(key)
        owner = owner_ref.get(transaction=transaction).to_dict() or {}
        control_ref = client.collection(f'{namespace}_control').document(scheduler_control_key(key))
        control = control_ref.get(transaction=transaction).to_dict() or {'rings': {}}
        queue_key = f"{job['priority']}_{key}"
        queue_ref = client.collection(f'{namespace}_queues').document(queue_key)
        queue = queue_ref.get(transaction=transaction).to_dict() or {}
        # Segment IDs are globally unique; this needs only a single-field index.
        predecessors = queries.predecessor_documents(client, namespace, snapshot.id, transaction)
        hold_ref = client.collection(f'{namespace}_{ALLOWANCE_OWNERS}').document(key)
        hold = hold_ref.get(transaction=transaction).to_dict() if job.get('state') == ALLOWANCE_HELD else None
        if predecessors and (predecessors[0].to_dict() or {}).get('owner_key') != key:
            raise RuntimeError('batch queue ownership mismatch')
        touched.extend([('jobs', snapshot.id), ('results', snapshot.id), ('owners', key), ('queues', queue_key)])
        touched.extend([('control', scheduler_control_key(key)), *(('jobs', p.id) for p in predecessors)])
        if hold:
            hold['held_count'] = max(0, hold.get('held_count', 0) - 1)
            hold['active'] = hold['held_count'] > 0
            transaction.set(hold_ref, hold)
            touched.append((ALLOWANCE_OWNERS, key))
        if queue.get('head') == snapshot.id:
            queue['head'] = job.get('next', '')
        if queue.get('tail') == snapshot.id:
            queue['tail'] = predecessors[0].id if predecessors else ''
        if queue and not queue.get('head'):
            for ring in control.get('rings', {}).values():
                while queue_key in ring:
                    ring.remove(queue_key)
            transaction.delete(queue_ref)
        elif queue:
            transaction.set(queue_ref, queue)
        for predecessor in predecessors:
            transaction.update(predecessor.reference, {'next': job.get('next', '')})
        transaction.set(control_ref, control)
        transaction.delete(snapshot.reference)
        if retain_ordering and result:
            _write_erased_result(transaction, result_ref, result, owner_ref, owner)
        else:
            transaction.delete(result_ref)

    remove(client.transaction())
    mirror_refresh(namespace, touched)


def _erase_artifact(
    uid: str,
    namespace: str,
    snapshot: Any,
    data: dict[str, Any],
    delete_uri: Callable[[str, str], None],
    fence: Callable[[Any], None] | None = None,
    client: Any = None,
) -> None:
    # The default deleter enforces the requested owner's configured storage
    # prefix before any metadata repair. A foreign URI raises, so the purge
    # cannot acknowledge erasure or transfer deletion authority to that row.
    for uri in _references(data):
        delete_uri(uid, uri)
    pending_until = data.get('write_pending_until', datetime.min.replace(tzinfo=timezone.utc))
    pending = pending_until > datetime.now(timezone.utc)
    # Privacy intent is authoritative, even if routine cleanup parked this
    # row. Keep late-upload erasure reachable and clear any racing TTL.
    repair = {
        'owner_id': uid,
        'owner_key': privacy_owner_key(uid),
        'erasure_requested': True,
        'cleanup_after': pending_until,
        'expires_at': firestore.DELETE_FIELD,
    }
    if fence is None:
        if pending:
            snapshot.reference.update(repair)
        else:
            snapshot.reference.delete()
    else:

        @firestore.transactional
        def fenced(transaction):
            fence(transaction)  # authority re-proven in the erasing transaction
            if pending:
                transaction.update(snapshot.reference, repair)
            else:
                transaction.delete(snapshot.reference)

        if client is None:
            raise ValueError('a fenced artifact erase needs the client that owns the row')
        fenced(client.transaction())
    mirror_refresh(namespace, [('artifacts', snapshot.id)])


def purge_batch_owner(
    uid: str,
    *,
    firestore_client: Any = None,
    conversation_id: str | None = None,
    reason: str = 'deleted',
    namespaces: Iterable[str] = NAMESPACES,
    delete_uri: Callable[[str, str], None] | None = None,
) -> int:
    """Fence first; erase objects before metadata so partial failures can retry.

    Conversation callers persist intent first. Account/protection changes
    advance generation before scanning. Never clear physical GPU reservations:
    lease loss does not prove inference idle. Purge both stage namespaces on
    the customer data plane even when admission is off. Synthetic namespaces
    require a loopback emulator client.
    """
    client = firestore_client if firestore_client is not None else get_data_plane_firestore_client()
    namespaces = tuple(namespaces)
    for namespace in namespaces:
        if namespace not in NAMESPACES:
            from database.batch_pipeline_store import FirestoreStore

            FirestoreStore(namespace, firestore_client=client)
    key = privacy_owner_key(uid)
    generation = 0
    if reason not in {'deleted', 'data_protection'}:
        raise ValueError('bounded privacy reason required')
    if conversation_id is None:
        generation = advance_privacy_generation(client, uid, blocked=reason == 'deleted')
    else:
        tombstone = (
            client.collection('users').document(uid).collection('deleted_conversations').document(conversation_id)
        )
        if not tombstone.get().exists:
            raise RuntimeError('conversation deletion intent required before batch purge')
    default_storage_cleanup = delete_uri is None
    if delete_uri is None:
        from utils.batch_pipeline.retention import delete_batch_object

        delete_uri = delete_batch_object
    deleted = 0
    for namespace in namespaces:
        segments = set()
        for table in (
            'jobs',
            'results',
            'artifacts',
            'projections',
            'intakes',
            'shadow_jobs',
            'coalesce_groups',
            'coalesce_sources',
            'coalesce_heads',
            'allowance_holds',
        ):
            after = None
            while True:
                rows = queries.owner_documents(client, namespace, table, key, after=after)
                if not rows:
                    break
                after = rows[-1]
                for snapshot in rows:
                    data = snapshot.to_dict() or {}
                    result = {}
                    if table == 'jobs':
                        result_ref = client.collection(f'{namespace}_results').document(snapshot.id)
                        result = result_ref.get().to_dict() or {}
                    matched = _belongs(
                        {**data, 'projection': result.get('projection') or data.get('projection')}, conversation_id
                    )
                    if not matched and not (
                        (table == 'artifacts' and data.get('segment_id') in segments)
                        or (table == 'intakes' and segments.intersection(data.get('segment_ids') or []))
                    ):
                        continue
                    if table in {'jobs', 'results'}:
                        segments.add(snapshot.id)
                    if table == 'artifacts':
                        _erase_artifact(uid, namespace, snapshot, data, delete_uri)
                        deleted += 1
                        continue
                    for uri in _references(data):
                        delete_uri(uid, uri)
                    if table == 'jobs':
                        for uri in _references(result):
                            delete_uri(uid, uri)
                        _delete_job(client, namespace, snapshot, retain_ordering=conversation_id is not None)
                    elif table == 'results' and conversation_id is not None:
                        _erase_result(client, namespace, snapshot)
                    elif table == 'coalesce_groups':
                        from database.batch_pipeline_coalescing import purge_group

                        purge_group(client, namespace, snapshot.id, uid)
                    else:
                        snapshot.reference.delete()
                    if table != 'jobs':
                        mirror_refresh(namespace, [(table, snapshot.id)])
                    deleted += 1
        # A routine owner-mismatch flag must never hide accepted audio from
        # privacy erasure. This bounded, single-field fallback reaches parked
        # rows without scanning other owners or trusting a foreign URI.
        after = None
        while True:
            rows = queries.artifacts_by_owner_id(client, namespace, uid, after=after)
            if not rows:
                break
            after = rows[-1]
            for snapshot in rows:
                data = snapshot.to_dict() or {}
                if data.get('owner_key') == key:
                    continue  # Already handled above, including pending writes.
                if not _belongs(data, conversation_id) and data.get('segment_id') not in segments:
                    continue
                _erase_artifact(uid, namespace, snapshot, data, delete_uri)
                deleted += 1
        if conversation_id is None:
            _purge_owner_fairness(client, namespace, key)
            if default_storage_cleanup:
                from utils.batch_pipeline.retention import purge_batch_storage_owner

                purge_batch_storage_owner(uid, namespace)
        # A5: the Postgres copy (A2 shadow) is erased in the same retryable flow, before the purge is
        # recorded as finished; a failure raises and the caller retries. No-op outside shadow mode.
        purge_jobstore_owner(namespace, uid)
    if conversation_id is None:
        finish_privacy_purge(client, uid, generation)
    return deleted


def _purge_owner_fairness(client: Any, namespace: str, key: str) -> None:
    @firestore.transactional
    def remove(transaction):
        control_ref = client.collection(f'{namespace}_control').document(scheduler_control_key(key))
        snapshot = control_ref.get(transaction=transaction)
        control = snapshot.to_dict() or {'rings': {}}
        queue_keys = {f'{priority}_{key}' for priority in range(3)}
        for priority, ring in control.get('rings', {}).items():
            control['rings'][priority] = [value for value in ring if value not in queue_keys]
        if snapshot.exists:
            transaction.set(control_ref, control)
        for queue_key in queue_keys:
            transaction.delete(client.collection(f'{namespace}_queues').document(queue_key))
        transaction.delete(client.collection(f'{namespace}_owners').document(key))
        transaction.delete(client.collection(f'{namespace}_merge_holds').document(key))

    remove(client.transaction())
    queues = [('queues', f'{priority}_{key}') for priority in range(3)]
    mirror_refresh(namespace, [('control', scheduler_control_key(key)), ('owners', key), *queues])


def _write_erased_result(transaction: Any, result_ref: Any, result: dict, owner_ref: Any, owner: dict) -> None:
    """Retain only the ordering edge; no body, source identity, or reference.

    ``log_sequence`` (a log position) keeps an erased projection watermark
    usable for the merge's catch-up depth.
    """
    erased = {
        field: result[field]
        for field in ('segment_id', 'owner_key', 'capture_at', 'protocol_version', 'log_sequence')
        if field in result
    }
    erased.update(projection_state='erased', previous_segment_id=result.get('previous_segment_id'))
    if owner.get('projection_watermark') == result.get('previous_segment_id'):
        transaction.update(owner_ref, {'projection_watermark': result['segment_id']})
        erased['expires_at'] = datetime.now(timezone.utc) + timedelta(days=45)
    elif owner.get('projection_watermark') == result['segment_id']:
        erased['expires_at'] = datetime.now(timezone.utc) + timedelta(days=45)
    transaction.set(result_ref, erased)


def _erase_result(client: Any, namespace: str, snapshot: Any, fence: Callable[[Any], None] | None = None) -> None:
    @firestore.transactional
    def erase(transaction):
        if fence is not None:
            fence(transaction)
        result = snapshot.reference.get(transaction=transaction).to_dict() or {}
        if not result:
            return
        owner_ref = client.collection(f'{namespace}_owners').document(result['owner_key'])
        owner = owner_ref.get(transaction=transaction).to_dict() or {}
        _write_erased_result(transaction, snapshot.reference, result, owner_ref, owner)

    erase(client.transaction())
    owner_key = (snapshot.to_dict() or {}).get('owner_key')
    mirror_refresh(namespace, [('results', snapshot.id), *([('owners', owner_key)] if owner_key else [])])


# Shared with the resumable conversation purge (database.batch_pipeline_conversation_purge),
# which must match and erase rows exactly as this pass does.
row_belongs = _belongs
row_references = _references
delete_job = _delete_job
erase_artifact = _erase_artifact
erase_result = _erase_result

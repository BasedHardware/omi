"""Durable, idempotent conversation mutations for offline-capable clients."""

import copy
import hashlib
import json
import logging
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

from google.cloud import firestore

from ._client import get_firestore_client, run_transactional
from .conversation_revisions import ensure_timezone_aware, firestore_revision_datetime
from .conversations import conversations_collection

_RECEIPTS_COLLECTION = 'mutation_receipts'
DEFAULT_RECEIPT_TTL_DAYS = 14
DEFAULT_RECEIPT_TTL = timedelta(days=DEFAULT_RECEIPT_TTL_DAYS)
_RECEIPT_SCHEMA_VERSION = 1


class ConversationMutationNotFoundError(LookupError):
    """The target conversation disappeared before its mutation committed."""


class ConversationMutationLockedError(PermissionError):
    """A new mutation cannot change a plan-locked conversation."""


class ConversationMutationConflictError(RuntimeError):
    """A durable typed conflict for a mutation that cannot be applied."""

    def __init__(self, response: Dict[str, Any]):
        super().__init__(str(response.get('code', 'conversation mutation conflict')))
        self.response = response


class ConversationMutationReceiptUnavailableError(RuntimeError):
    """A committed receipt could not be read back into a canonical response."""


def _normalized_revision(value: Any) -> Optional[datetime]:
    revision = firestore_revision_datetime(value)
    return revision.astimezone(timezone.utc) if revision is not None else None


def _sync_state(data: Dict[str, Any], revision: Any) -> Dict[str, Any]:
    """Build the bounded user-owned projection stored in mutation receipts."""
    structured = data.get('structured')
    generated_title = structured.get('title') if isinstance(structured, Mapping) else None
    user_title = data.get('user_title')
    title = user_title if isinstance(user_title, str) else generated_title if isinstance(generated_title, str) else None
    return {
        'revision': revision,
        'title': title,
        'starred': bool(data.get('starred', False)),
        'folder_id': data.get('folder_id'),
        'visibility': data.get('visibility') or 'private',
    }


def _fingerprint(base_revision: datetime, operation: Dict[str, Any]) -> str:
    revision = ensure_timezone_aware(base_revision).astimezone(timezone.utc).isoformat()
    intent = json.dumps(
        {'base_revision': revision, 'operation': operation},
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=True,
    )
    return hashlib.sha256(intent.encode('utf-8')).hexdigest()


def _receipt_id(client_mutation_id: str) -> str:
    """Keep arbitrary released-client identifiers out of Firestore paths."""
    return hashlib.sha256(client_mutation_id.encode('utf-8')).hexdigest()


def _apply_operation(current: Dict[str, Any], operation: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Project one validated user-owned operation into state and Firestore patch."""
    operation_type = operation.get('type')
    next_state = copy.deepcopy(current)
    if operation_type == 'set_title':
        title = operation.get('title')
        if not isinstance(title, str):
            raise ValueError('set_title requires title')
        structured = next_state.get('structured')
        current_structured_title = structured.get('title') if isinstance(structured, Mapping) else None
        patch = (
            {'structured.title': title, 'user_title': title}
            if current.get('user_title') != title or current_structured_title != title
            else {}
        )
        next_state['user_title'] = title
        if not isinstance(structured, dict):
            structured = {}
            next_state['structured'] = structured
        structured['title'] = title
        return next_state, patch

    if operation_type == 'set_starred':
        starred = operation.get('starred')
        if not isinstance(starred, bool):
            raise ValueError('set_starred requires starred')
        patch = {'starred': starred} if bool(current.get('starred', False)) != starred else {}
        next_state['starred'] = starred
        return next_state, patch

    raise ValueError(f'unsupported conversation mutation: {operation_type}')


def apply_conversation_sync_mutation(
    uid: str,
    conversation_id: str,
    *,
    client_mutation_id: str,
    base_revision: datetime,
    operation: Dict[str, Any],
    ttl: timedelta = DEFAULT_RECEIPT_TTL,
    firestore_client: Any = None,
) -> tuple[Dict[str, Any], bool]:
    """Apply one user mutation exactly once against a canonical revision.

    The conversation write and its compact receipt share one Firestore commit.
    Receipts are stamped with `expire_at` corresponding to the outbox retry horizon
    (defaulting to DEFAULT_RECEIPT_TTL) to bound Firestore document growth.
    For a real state change, the receipt document's own ``update_time`` is the
    commit revision returned on both the first response and every retry. A no-op
    stores the conversation's existing revision because Firestore may preserve
    a document's old ``update_time`` when an update changes no values.
    """
    if ttl <= timedelta(0):
        raise ValueError(f'mutation receipt ttl must be positive, got {ttl}')

    client = firestore_client if firestore_client is not None else get_firestore_client()
    conversation_ref = (
        client.collection('users').document(uid).collection(conversations_collection).document(conversation_id)
    )
    receipt_ref = conversation_ref.collection(_RECEIPTS_COLLECTION).document(_receipt_id(client_mutation_id))
    fingerprint = _fingerprint(base_revision, operation)
    replayed = False

    @firestore.transactional
    def _apply(transaction) -> None:
        nonlocal replayed
        # Firestore requires every read to finish before the first write.
        receipt_snapshot = receipt_ref.get(transaction=transaction)
        conversation_snapshot = conversation_ref.get(transaction=transaction)
        now_utc = datetime.now(timezone.utc)
        expire_at = now_utc + ttl

        if getattr(receipt_snapshot, 'exists', False):
            receipt = receipt_snapshot.to_dict() or {}
            receipt_expire_at = receipt.get('expire_at')
            is_expired = False
            if receipt_expire_at is not None and isinstance(receipt_expire_at, datetime):
                aware_expire = ensure_timezone_aware(receipt_expire_at).astimezone(timezone.utc)
                if aware_expire <= now_utc:
                    is_expired = True

            if not is_expired:
                if receipt.get('client_mutation_id') != client_mutation_id or receipt.get('fingerprint') != fingerprint:
                    raise ConversationMutationConflictError(
                        {
                            'status': 'conflict',
                            'code': 'mutation_id_reused',
                            'client_mutation_id': client_mutation_id,
                            'conversation_id': conversation_id,
                            'conversation': None,
                        }
                    )
                replayed = True
                return

            # Semantic Note: Once a receipt expires beyond its TTL (the client outbox retry horizon),
            # it is treated as expired and eligible for re-application. This allows legitimate retries
            # that outlived the cache window to re-apply rather than fail permanently, but converts
            # the hard 'mutation_id_reused' conflict guard into a time-bounded guarantee.
            # Same-id retries with differing fingerprints after expiration will re-apply cleanly
            # against current state rather than throwing a permanent conflict.

        def _write_receipt(resp: Dict[str, Any], rev_source: Optional[str] = None) -> None:
            receipt_payload: Dict[str, Any] = {
                'schema_version': _RECEIPT_SCHEMA_VERSION,
                'client_mutation_id': client_mutation_id,
                'fingerprint': fingerprint,
                'created_at': firestore.SERVER_TIMESTAMP,
                'expire_at': expire_at,
                'response': resp,
            }
            if rev_source:
                receipt_payload['revision_source'] = rev_source

            if hasattr(transaction, 'set'):
                transaction.set(receipt_ref, receipt_payload)
            elif getattr(receipt_snapshot, 'exists', False):
                transaction.update(receipt_ref, receipt_payload)
            else:
                transaction.create(receipt_ref, receipt_payload)

        if not getattr(conversation_snapshot, 'exists', False):
            raise ConversationMutationNotFoundError(conversation_id)

        current = conversation_snapshot.to_dict() or {}
        if current.get('is_locked', False):
            raise ConversationMutationLockedError(conversation_id)
        current_revision = _normalized_revision(getattr(conversation_snapshot, 'update_time', None))
        requested_revision = ensure_timezone_aware(base_revision).astimezone(timezone.utc)

        if current_revision is None:
            response = {
                'status': 'conflict',
                'code': 'revision_unavailable',
                'client_mutation_id': client_mutation_id,
                'conversation_id': conversation_id,
                'conversation': None,
            }
            _write_receipt(response)
            return

        if requested_revision != current_revision:
            response = {
                'status': 'conflict',
                'code': 'base_revision_mismatch',
                'client_mutation_id': client_mutation_id,
                'conversation_id': conversation_id,
                'conversation': _sync_state(current, current_revision),
            }
            _write_receipt(response)
            return

        next_state, patch = _apply_operation(current, operation)
        response_state = _sync_state(next_state, current_revision)
        revision_source = 'stored'
        if patch:
            # Both writes use one atomic commit, so the receipt metadata carries
            # the exact post-write conversation revision without timestamp loss.
            response_state.pop('revision')
            revision_source = 'receipt_update_time'
        response = {
            'status': 'ok',
            'client_mutation_id': client_mutation_id,
            'conversation_id': conversation_id,
            'conversation': response_state,
        }
        if patch:
            transaction.update(conversation_ref, patch)
        _write_receipt(response, revision_source)

    run_transactional(client, _apply)

    receipt_snapshot = receipt_ref.get()
    if not getattr(receipt_snapshot, 'exists', False):
        raise ConversationMutationReceiptUnavailableError('conversation mutation receipt was not readable after commit')
    receipt = receipt_snapshot.to_dict() or {}
    if receipt.get('client_mutation_id') != client_mutation_id or receipt.get('fingerprint') != fingerprint:
        raise ConversationMutationConflictError(
            {
                'status': 'conflict',
                'code': 'mutation_id_reused',
                'client_mutation_id': client_mutation_id,
                'conversation_id': conversation_id,
                'conversation': None,
            }
        )
    response = receipt.get('response')
    if not isinstance(response, dict):
        raise ConversationMutationReceiptUnavailableError('conversation mutation receipt has no response')
    if response.get('status') == 'conflict':
        raise ConversationMutationConflictError(response)
    result = copy.deepcopy(response)
    conversation = result.get('conversation')
    if receipt.get('revision_source') == 'receipt_update_time' and isinstance(conversation, dict):
        revision = _normalized_revision(getattr(receipt_snapshot, 'update_time', None))
        if revision is None:
            raise ConversationMutationReceiptUnavailableError('conversation mutation receipt has no revision')
        conversation['revision'] = revision
    return result, replayed


def get_conversation_mutation_receipt(
    uid: str,
    conversation_id: str,
    client_mutation_id: str,
    firestore_client: Any = None,
) -> Optional[Dict[str, Any]]:
    """Retrieve raw mutation receipt data by client_mutation_id, or None if expired or non-existent."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    receipt_ref = (
        client.collection('users')
        .document(uid)
        .collection(conversations_collection)
        .document(conversation_id)
        .collection(_RECEIPTS_COLLECTION)
        .document(_receipt_id(client_mutation_id))
    )
    snapshot = receipt_ref.get()
    if not getattr(snapshot, 'exists', False):
        return None
    data = snapshot.to_dict() or {}
    expire_at = data.get('expire_at')
    if expire_at is not None and isinstance(expire_at, datetime):
        if ensure_timezone_aware(expire_at).astimezone(timezone.utc) <= datetime.now(timezone.utc):
            return None
    return data


def prune_expired_mutation_receipts(
    uid: str,
    conversation_id: str,
    *,
    now: Optional[datetime] = None,
    batch_size: int = 100,
    firestore_client: Any = None,
) -> int:
    """Explicit garbage collector for expired mutation receipts.

    While Firestore automatically purges documents via collection TTL policies,
    this helper provides on-demand deterministic cleanup for maintenance sweeps,
    test tear-downs, and client migration runs.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    now_utc = ensure_timezone_aware(now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    receipts_ref = (
        client.collection('users')
        .document(uid)
        .collection(conversations_collection)
        .document(conversation_id)
        .collection(_RECEIPTS_COLLECTION)
    )

    deleted_count = 0
    try:
        query = receipts_ref.where('expire_at', '<=', now_utc).limit(batch_size)
        docs = list(query.stream() if hasattr(query, 'stream') else query.get())
        if not docs:
            return 0

        if hasattr(client, 'batch'):
            batch = client.batch()
            for doc in docs:
                ref = getattr(doc, 'reference', None)
                if ref is not None:
                    batch.delete(ref)
                elif hasattr(doc, 'delete'):
                    doc.delete()
                deleted_count += 1
            if hasattr(batch, 'commit'):
                batch.commit()
        else:
            for doc in docs:
                ref = getattr(doc, 'reference', None)
                if ref is not None and hasattr(ref, 'delete'):
                    ref.delete()
                elif hasattr(doc, 'delete'):
                    doc.delete()
                deleted_count += 1
    except Exception as e:
        logger.exception(
            'Failed during mutation receipt pruning for user %s, conversation %s: %s',
            uid,
            conversation_id,
            e,
        )
        raise
    return deleted_count

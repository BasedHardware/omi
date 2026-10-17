"""Transactional privacy authority for batch intake, compute and projection.

All reads precede caller writes and use the customer-data transaction. The
hashed generation survives recursive account wipes and contains no content.
"""

from collections.abc import Iterable
import hashlib
from typing import Any

from database.account_deletion_policy import account_deletion_blocks_access, normalize_account_deletion_status

PRIVACY_COLLECTION = 'batch_pipeline_privacy'


class BatchPrivacyBlocked(RuntimeError):
    """A deleted, migrating or E2EE owner/source cannot accept server results."""


def privacy_owner_key(uid: str) -> str:
    if not uid or '/' in uid or len(uid.encode()) > 256:
        raise ValueError('bounded owner document ID required')
    return hashlib.sha256(uid.encode()).hexdigest()


def assert_batch_write_allowed(
    client: Any,
    transaction: Any,
    uid: str,
    *,
    conversation_ids: Iterable[str] = (),
    expected_generation: int | None = None,
    snapshots: dict | None = None,
) -> int:
    """Fence a mutation. Admission records the returned generation for replay.

    Check all source IDs and assigned targets inside the mutation transaction:
    choosing another target must never revive a deleted source. Unknown accounts
    are denied even if their deletion marker has disappeared.
    """
    key = privacy_owner_key(uid)
    marker = client.collection('account_deletions').document(uid).get(transaction=transaction)
    status = normalize_account_deletion_status(
        marker_exists=marker.exists, raw_status=(marker.to_dict() or {}).get('wipe_status')
    )
    if account_deletion_blocks_access(status):
        raise BatchPrivacyBlocked('account_deleted')
    user = client.collection('users').document(uid)
    snapshot = user.get(transaction=transaction)
    data = snapshot.to_dict() or {}
    if snapshots is not None:
        snapshots['user'] = data
    if not snapshot.exists:
        raise BatchPrivacyBlocked('account_missing')
    if (
        data.get('data_protection_level', 'enhanced') not in {'standard', 'enhanced'}
        or data.get('migration_status') is not None
    ):
        raise BatchPrivacyBlocked('data_protection_changed')
    privacy = client.collection(PRIVACY_COLLECTION).document(key).get(transaction=transaction).to_dict() or {}
    generation = int(privacy.get('generation', 0))
    if (
        privacy.get('blocked')
        or privacy.get('purging')
        or (expected_generation is not None and expected_generation != generation)
    ):
        raise BatchPrivacyBlocked('privacy_generation_changed')
    budget = 0
    for source_id in set(conversation_ids):
        conversation_id = source_id
        chain = set()
        redirected = False
        while True:
            if conversation_id in chain:
                raise BatchPrivacyBlocked('conversation_redirect_cycle')
            chain.add(conversation_id)
            budget += 1
            if budget > 256:
                raise BatchPrivacyBlocked('conversation_fence_budget')
            if not conversation_id or '/' in conversation_id or len(conversation_id.encode()) > 256:
                raise ValueError('bounded conversation document ID required')
            if user.collection('deleted_conversations').document(conversation_id).get(transaction=transaction).exists:
                raise BatchPrivacyBlocked('conversation_deleted')
            conversation = user.collection('conversations').document(conversation_id).get(transaction=transaction)
            row = conversation.to_dict() or {}
            if snapshots is not None:
                snapshots.setdefault('conversations', {})[conversation_id] = row
            if row.get('record_lane_owner') == 'batch_live_v1' and (
                row.get('uses_custom_stt')
                or not row.get('private_cloud_sync_enabled')
                or not data.get('private_cloud_sync_enabled', False)
            ):
                raise BatchPrivacyBlocked('recording_privacy_changed')
            if redirected and not conversation.exists:
                raise BatchPrivacyBlocked('conversation_redirect_missing')
            if not row.get('deleted'):
                break
            target = row.get('sync_merged_into')
            if not isinstance(target, str) or not target:
                raise BatchPrivacyBlocked('conversation_deleted')
            # Server-owned redirects are expected. Follow the target in this
            # transaction; user intent above always dominates a redirect.
            conversation_id, redirected = target, True
    return generation


def advance_privacy_generation(client: Any, uid: str, *, blocked: bool) -> int:
    """Invalidate in-flight references before account/protection cleanup."""
    from google.cloud import firestore

    reference = client.collection(PRIVACY_COLLECTION).document(privacy_owner_key(uid))

    @firestore.transactional
    def advance(transaction):
        previous = reference.get(transaction=transaction).to_dict() or {}
        generation = int(previous.get('generation', 0)) + 1
        transaction.set(
            reference, {'generation': generation, 'blocked': blocked or bool(previous.get('blocked')), 'purging': True}
        )
        return generation

    return advance(client.transaction())


def finish_privacy_purge(client: Any, uid: str, generation: int) -> None:
    """Reopen admission only after this exact protection purge converges."""
    from google.cloud import firestore

    reference = client.collection(PRIVACY_COLLECTION).document(privacy_owner_key(uid))

    @firestore.transactional
    def finish(transaction):
        previous = reference.get(transaction=transaction).to_dict() or {}
        if previous.get('generation') == generation:
            transaction.update(reference, {'purging': False})

    finish(client.transaction())


def erased_predecessors(
    client: Any,
    transaction: Any,
    namespace: str,
    owner_key: str,
    predecessor: str | None,
    watermark: str | None,
) -> list[Any] | None:
    """Read an erased ordering chain without skipping unfinished projections.

    Caller TTLs returned receipts only after its cursor advance commits. A
    bounded read budget fails closed; maintenance may advance in smaller steps.
    """
    references = []
    seen = set()
    for _ in range(128):
        if predecessor == watermark:
            return references
        if predecessor is None or predecessor in seen:
            return None
        seen.add(predecessor)
        reference = client.collection(f'{namespace}_results').document(predecessor)
        data = reference.get(transaction=transaction).to_dict() or {}
        if data.get('owner_key') != owner_key or data.get('projection_state') != 'erased':
            return None
        references.append(reference)
        predecessor = data.get('previous_segment_id')
    return references if predecessor == watermark else None

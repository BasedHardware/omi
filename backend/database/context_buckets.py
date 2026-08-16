"""Context bucket persistence for facts published by capture devices.

Writes are ordered by the publishing device's clock rather than arrival order, so a
retried or reordered sync cannot regress state. Reads are fenced by account generation
and filter expired facts, so a lagging collector never serves stale context.
"""

from datetime import datetime, timezone
from typing import Any, Optional, cast

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from database._client import get_firestore_client
from database.read_boundary import parse_snapshots
from models.context_bucket import (
    ContextBucket,
    ContextBucketPurgeReport,
    ContextBucketSync,
    ContextBucketSyncReport,
    ContextBucketSyncRequest,
    ContextFact,
    ContextFactSync,
)

BUCKETS_COLLECTION = 'context_buckets'
FACTS_COLLECTION = 'context_bucket_facts'


def _get_db(firestore_client: Any = None) -> Any:
    return firestore_client or get_firestore_client()


def _user_ref(uid: str, *, firestore_client: Any = None):
    return _get_db(firestore_client).collection('users').document(uid)


def _bucket_ref(uid: str, bucket_id: str, *, firestore_client: Any = None):
    return _user_ref(uid, firestore_client=firestore_client).collection(BUCKETS_COLLECTION).document(bucket_id)


def _facts_collection(uid: str, *, firestore_client: Any = None):
    """Facts live beside buckets rather than beneath them.

    A flat per-user collection keeps every fact read a single owner-scoped query,
    where a subcollection would force either a fan-out over buckets or a
    collection-group query that spans every user in the database.
    """

    return _user_ref(uid, firestore_client=firestore_client).collection(FACTS_COLLECTION)


def _snapshot_dict(snapshot: Any) -> dict[str, Any]:
    payload = snapshot.to_dict()
    return cast(dict[str, Any], payload) if isinstance(payload, dict) else {}


def _readable_payload(snapshot: Any) -> dict[str, Any]:
    """Drop the storage-only generation fence before contract validation."""

    payload = _snapshot_dict(snapshot)
    payload.pop('account_generation', None)
    return payload


def _as_aware(value: Any) -> Optional[datetime]:
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _is_stale(stored: dict[str, Any], incoming_device_updated_at: datetime) -> bool:
    """Report whether a stored row already reflects a device write at least this new."""

    stored_at = _as_aware(stored.get('device_updated_at'))
    if stored_at is None:
        return False
    incoming = _as_aware(incoming_device_updated_at)
    return incoming is not None and incoming <= stored_at


def _bucket_storage(
    bucket: ContextBucketSync,
    *,
    device_id: str,
    account_generation: int,
    now: datetime,
    created_at: datetime,
) -> dict[str, Any]:
    return {
        'bucket_id': bucket.bucket_id,
        'subject_kind': bucket.subject_kind.value,
        'subject_id': bucket.subject_id,
        'workstream_id': bucket.workstream_id,
        'display_label': bucket.display_label,
        'notify_worthiness': bucket.notify_worthiness,
        'visit_count': bucket.visit_count,
        'last_visited_at': bucket.last_visited_at,
        'device_id': device_id,
        'device_updated_at': bucket.device_updated_at,
        'account_generation': account_generation,
        'created_at': created_at,
        'updated_at': now,
    }


def _fact_storage(
    fact: ContextFactSync,
    *,
    bucket_id: str,
    device_id: str,
    account_generation: int,
    now: datetime,
    created_at: datetime,
) -> dict[str, Any]:
    return {
        'fact_id': fact.fact_id,
        'bucket_id': bucket_id,
        'statement': fact.statement,
        'identifiers': list(fact.identifiers),
        'confidence': fact.confidence,
        'notify_worthiness': fact.notify_worthiness,
        'disposition_state': fact.disposition_state.value,
        'workstream_tag': fact.workstream_tag,
        'evidence_refs': [ref.model_dump(mode='python') for ref in fact.evidence_refs],
        'expires_at': fact.expires_at,
        'device_id': device_id,
        'device_updated_at': fact.device_updated_at,
        'account_generation': account_generation,
        'created_at': created_at,
        'updated_at': now,
    }


def sync_context_buckets(
    uid: str,
    request: ContextBucketSyncRequest,
    *,
    account_generation: int,
    firestore_client: Any = None,
) -> ContextBucketSyncReport:
    """Upsert device-published buckets and facts, skipping writes the store already leads."""

    client = _get_db(firestore_client)
    now = datetime.now(timezone.utc)
    buckets_written = 0
    buckets_skipped = 0
    facts_written = 0
    facts_skipped = 0

    for bucket in request.buckets:
        bucket_ref = _bucket_ref(uid, bucket.bucket_id, firestore_client=client)
        batch = client.batch()
        stored_bucket = _snapshot_dict(bucket_ref.get())
        if stored_bucket and _is_stale(stored_bucket, bucket.device_updated_at):
            buckets_skipped += 1
        else:
            batch.set(
                bucket_ref,
                _bucket_storage(
                    bucket,
                    device_id=request.device_id,
                    account_generation=account_generation,
                    now=now,
                    created_at=_as_aware(stored_bucket.get('created_at')) or now,
                ),
            )
            buckets_written += 1

        facts_ref = _facts_collection(uid, firestore_client=client)
        for fact in bucket.facts:
            fact_ref = facts_ref.document(fact.fact_id)
            stored_fact = _snapshot_dict(fact_ref.get())
            if stored_fact and _is_stale(stored_fact, fact.device_updated_at):
                facts_skipped += 1
                continue
            batch.set(
                fact_ref,
                _fact_storage(
                    fact,
                    bucket_id=bucket.bucket_id,
                    device_id=request.device_id,
                    account_generation=account_generation,
                    now=now,
                    created_at=_as_aware(stored_fact.get('created_at')) or now,
                ),
            )
            facts_written += 1
        batch.commit()

    return ContextBucketSyncReport(
        buckets_written=buckets_written,
        buckets_skipped_stale=buckets_skipped,
        facts_written=facts_written,
        facts_skipped_stale=facts_skipped,
    )


def list_context_buckets(
    uid: str,
    *,
    account_generation: int,
    workstream_id: Optional[str] = None,
    limit: int = 100,
    firestore_client: Any = None,
) -> list[ContextBucket]:
    query = (
        _user_ref(uid, firestore_client=firestore_client)
        .collection(BUCKETS_COLLECTION)
        .where(filter=FieldFilter('account_generation', '==', account_generation))
    )
    if workstream_id is not None:
        query = query.where(filter=FieldFilter('workstream_id', '==', workstream_id))
    query = query.order_by('updated_at', direction=firestore.Query.DESCENDING).limit(limit)
    return parse_snapshots(ContextBucket, query.stream(), payload_from_snapshot=_readable_payload)


def list_context_facts(
    uid: str,
    *,
    account_generation: int,
    workstream_id: Optional[str] = None,
    minimum_confidence: float = 0,
    limit: int = 200,
    now: Optional[datetime] = None,
    firestore_client: Any = None,
) -> list[ContextFact]:
    """Read live facts across every bucket, newest first.

    Expiry is applied here rather than left to collection so a lagging collector
    cannot serve a fact the device already considers dead.
    """

    moment = now or datetime.now(timezone.utc)
    query = _facts_collection(uid, firestore_client=firestore_client).where(
        filter=FieldFilter('account_generation', '==', account_generation)
    )
    if workstream_id is not None:
        query = query.where(filter=FieldFilter('workstream_tag', '==', workstream_id))
    snapshots = query.order_by('updated_at', direction=firestore.Query.DESCENDING).limit(limit).stream()
    facts = parse_snapshots(ContextFact, snapshots, payload_from_snapshot=_readable_payload)
    live = [
        fact
        for fact in facts
        if fact.confidence >= minimum_confidence
        and (fact.expires_at is None or cast(datetime, _as_aware(fact.expires_at)) > moment)
    ]
    return live


def purge_context_buckets(
    uid: str,
    bucket_ids: list[str],
    *,
    firestore_client: Any = None,
) -> ContextBucketPurgeReport:
    """Delete synced copies of buckets a device has stopped retaining locally."""

    client = _get_db(firestore_client)
    buckets_deleted = 0
    facts_deleted = 0

    facts_ref = _facts_collection(uid, firestore_client=client)
    for bucket_id in bucket_ids:
        bucket_ref = _bucket_ref(uid, bucket_id, firestore_client=client)
        batch = client.batch()
        owned_facts = facts_ref.where(filter=FieldFilter('bucket_id', '==', bucket_id)).stream()
        for fact_snapshot in owned_facts:
            batch.delete(fact_snapshot.reference)
            facts_deleted += 1
        if bucket_ref.get().exists:
            batch.delete(bucket_ref)
            buckets_deleted += 1
        batch.commit()

    return ContextBucketPurgeReport(buckets_deleted=buckets_deleted, facts_deleted=facts_deleted)


__all__ = [
    'BUCKETS_COLLECTION',
    'FACTS_COLLECTION',
    'list_context_buckets',
    'list_context_facts',
    'purge_context_buckets',
    'sync_context_buckets',
]

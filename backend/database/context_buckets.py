"""Context bucket persistence for facts published by capture devices.

Writes are ordered by the publishing device's clock rather than arrival order, so a
retried or reordered sync cannot regress state. Reads are fenced by account generation
and filter expired facts, so a lagging collector never serves stale context.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional, cast

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from database._client import get_firestore_client
from database.firestore_index_registry import CONTEXT_BUCKET_FACTS_BY_GENERATION_QUERY
from database.read_boundary import parse_snapshots
from models.context_bucket import (
    ContextBucketPurgeReport,
    ContextBucketSync,
    ContextBucketSyncReport,
    ContextBucketSyncRequest,
    ContextFact,
    ContextFactSync,
)

BUCKETS_COLLECTION = 'context_buckets'
FACTS_COLLECTION = 'context_bucket_facts'

# Expiry and the confidence floor are applied after the query, so it over-fetches
# to keep post-filter starvation off the caller. The ceiling bounds the read when
# a caller asks for a large page.
FACT_OVERFETCH_FACTOR = 4
FACT_OVERFETCH_CEILING = 1000

# Ordering trusts the publishing device's clock, so a device running fast could
# stamp a far-future time and lock every other device out of that row until wall
# clock caught up. Clamping rather than rejecting keeps a mildly skewed clock
# syncing normally while bounding how far ahead any device can place itself.
MAX_DEVICE_CLOCK_SKEW = timedelta(hours=1)


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


def _clamped_device_time(value: datetime, *, now: datetime) -> datetime:
    """Bound how far ahead of the server a device may place itself."""

    aware = _as_aware(value)
    if aware is None:
        return now
    ceiling = now + MAX_DEVICE_CLOCK_SKEW
    return ceiling if aware > ceiling else aware


def _is_stale(
    stored: dict[str, Any],
    incoming_device_updated_at: datetime,
    *,
    account_generation: int,
) -> bool:
    """Report whether a stored row already reflects a device write at least this new.

    A row from a different account generation is never stale. Generation fences
    every read, so a row left behind at the old generation is invisible; skipping
    its rewrite as "already current" would strand it permanently, because the
    device has no reason to bump a device clock that did not change.
    """

    if int(stored.get('account_generation', 0)) != account_generation:
        return False
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
        'device_updated_at': _clamped_device_time(bucket.device_updated_at, now=now),
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
        'device_updated_at': _clamped_device_time(fact.device_updated_at, now=now),
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
    facts_ref = _facts_collection(uid, firestore_client=client)

    for bucket in request.buckets:
        bucket_ref = _bucket_ref(uid, bucket.bucket_id, firestore_client=client)
        fact_refs = [(fact, facts_ref.document(fact.fact_id)) for fact in bucket.facts]
        transaction = client.transaction()

        @firestore.transactional
        def apply(write_transaction, bucket=bucket, bucket_ref=bucket_ref, fact_refs=fact_refs):
            """Re-read every row inside the transaction so the staleness test commits atomically.

            Reading outside the transaction and writing after would let two
            concurrent syncs both observe an old row and both write, so the
            loser's older device clock could overwrite the newer state.

            Firestore forbids a read after a write inside a transaction, so
            every row is read up front and the writes are decided afterwards.
            """

            stored_bucket = _snapshot_dict(bucket_ref.get(transaction=write_transaction))
            stored_facts = [
                (fact, fact_ref, _snapshot_dict(fact_ref.get(transaction=write_transaction)))
                for fact, fact_ref in fact_refs
            ]

            written = skipped = fact_written = fact_skipped = 0
            if stored_bucket and _is_stale(
                stored_bucket,
                _clamped_device_time(bucket.device_updated_at, now=now),
                account_generation=account_generation,
            ):
                skipped += 1
            else:
                write_transaction.set(
                    bucket_ref,
                    _bucket_storage(
                        bucket,
                        device_id=request.device_id,
                        account_generation=account_generation,
                        now=now,
                        created_at=_as_aware(stored_bucket.get('created_at')) or now,
                    ),
                )
                written += 1

            for fact, fact_ref, stored_fact in stored_facts:
                if stored_fact and _is_stale(
                    stored_fact,
                    _clamped_device_time(fact.device_updated_at, now=now),
                    account_generation=account_generation,
                ):
                    fact_skipped += 1
                    continue
                write_transaction.set(
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
                fact_written += 1
            return written, skipped, fact_written, fact_skipped

        written, skipped, fact_written, fact_skipped = apply(transaction)
        buckets_written += written
        buckets_skipped += skipped
        facts_written += fact_written
        facts_skipped += fact_skipped

    return ContextBucketSyncReport(
        buckets_written=buckets_written,
        buckets_skipped_stale=buckets_skipped,
        facts_written=facts_written,
        facts_skipped_stale=facts_skipped,
    )


def list_context_facts(
    uid: str,
    *,
    account_generation: int,
    minimum_confidence: float = 0,
    limit: int = 200,
    now: Optional[datetime] = None,
    firestore_client: Any = None,
) -> list[ContextFact]:
    """Read live facts across every bucket, newest first.

    Expiry and the confidence floor are applied here rather than in the query.
    Expiry cannot be a range filter alongside the ordering without another
    composite index, and the caller's floor is a runtime value.

    Because those filters run after the query, the query must over-fetch: with
    the caller's limit applied in Firestore, expired or low-confidence rows at
    the top of the ordering would consume the budget and silently starve live
    facts that sort behind them.
    """

    moment = now or datetime.now(timezone.utc)
    query = CONTEXT_BUCKET_FACTS_BY_GENERATION_QUERY.build(
        _facts_collection(uid, firestore_client=firestore_client),
        {'account_generation': account_generation},
        field_filter_factory=FieldFilter,
    )
    fetch_limit = min(limit * FACT_OVERFETCH_FACTOR, FACT_OVERFETCH_CEILING)
    snapshots = query.order_by('updated_at', direction=firestore.Query.DESCENDING).limit(fetch_limit).stream()
    facts = parse_snapshots(ContextFact, snapshots, payload_from_snapshot=_readable_payload)
    live = [
        fact
        for fact in facts
        if fact.confidence >= minimum_confidence
        and (fact.expires_at is None or cast(datetime, _as_aware(fact.expires_at)) > moment)
    ]
    return live[:limit]


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
    'list_context_facts',
    'purge_context_buckets',
    'sync_context_buckets',
]

"""Durable dead-letter ledger for terminal backfill sync failures.

One document per job in ``sync_dead_letters/{job_id}`` carrying only bounded
operational fields — uid, job_id, an optional assigned conversation_id,
``lane='backfill'``, ``status='pending'|'dead_letter'``, a closed
``failure_code`` vocabulary, ``attempt_count``, ``created_at``, and
``dead_lettered_at`` once confirmed. No raw error strings, file paths,
transcript, or audio bytes may ever land here.

The Redis sync job is the client-visible truth and keeps its existing
``failed``/``partial_failure`` contract; this ledger is the durable diagnosis
that survives the 24h Redis TTL. A terminal publisher must write the pending
record *before* the Redis terminal transition and confirm it afterwards, so a
crash anywhere in the sequence leaves at most a pending doc — durable enough
for the terminal-delivery path to confirm before ACK/cleanup, and never a
double client-visible status.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any, Optional

from google.cloud import firestore

from database._client import get_firestore_client

DEAD_LETTERS_COLLECTION = 'sync_dead_letters'
DEAD_LETTER_LANE = 'backfill'
STATUS_PENDING = 'pending'
STATUS_DEAD_LETTER = 'dead_letter'

FAILURE_CODES = frozenset(
    {
        'speaker_embedding_unconfigured',
        'speaker_embedding_failed',
        'typesense_projection_failed',
        'stt_failed',
        'llm_failed',
        'empty_structured_guard',
        'unknown',
    }
)


def dead_letter_failure_code(reason: Any) -> str:
    """Map any reason/error code into the closed ledger vocabulary."""
    if isinstance(reason, str) and reason in FAILURE_CODES:
        return reason
    return 'unknown'


def _client(firestore_client: Any = None) -> Any:
    return firestore_client if firestore_client is not None else get_firestore_client()


def _doc_ref(client: Any, job_id: str) -> Any:
    return client.collection(DEAD_LETTERS_COLLECTION).document(job_id)


def _emit_confirmed(doc: dict[str, Any]) -> None:
    sys.stdout.write(
        json.dumps(
            {
                'event': 'sync_backfill_dead_letter',
                'job_id': doc.get('job_id'),
                'uid': doc.get('uid'),
                'failure_code': doc.get('failure_code'),
                'outcome': 'confirmed',
            },
            default=str,
        )
        + '\n'
    )
    sys.stdout.flush()


def record_dead_letter_pending(
    *,
    job_id: str,
    uid: Any,
    conversation_id: Any = None,
    failure_code: str = 'unknown',
    firestore_client: Any = None,
) -> dict[str, Any]:
    """Write the pending ledger record a backfill terminal publish requires.

    Idempotent on the ``job_id`` document id: repeat terminal attempts only
    increment ``attempt_count`` and keep the original ``created_at``. A doc
    already confirmed stays ``dead_letter`` — confirmation never regresses.
    Raises on Firestore failure; callers must let that fail the publish closed
    rather than terminalizing Redis without the durable record.
    """
    client = _client(firestore_client)
    doc_ref = _doc_ref(client, job_id)
    now = datetime.now(timezone.utc)

    def _txn(transaction: Any) -> dict[str, Any]:
        snapshot = doc_ref.get(transaction=transaction)
        existing = snapshot.to_dict() or {} if getattr(snapshot, 'exists', False) else {}
        record: dict[str, Any] = {
            'uid': uid,
            'job_id': job_id,
            'lane': DEAD_LETTER_LANE,
            'status': existing.get('status') if existing.get('status') == STATUS_DEAD_LETTER else STATUS_PENDING,
            'failure_code': failure_code if failure_code in FAILURE_CODES else 'unknown',
            'attempt_count': int(existing.get('attempt_count') or 0) + 1,
            'created_at': existing.get('created_at') or now,
        }
        if conversation_id or existing.get('conversation_id'):
            record['conversation_id'] = conversation_id or existing.get('conversation_id')
        transaction.set(doc_ref, record, merge=True)
        return record

    return firestore.transactional(_txn)(client.transaction())


def get_dead_letter(job_id: str, *, firestore_client: Any = None) -> Optional[dict[str, Any]]:
    """Return the ledger doc for ``job_id`` or ``None`` when it does not exist."""
    client = _client(firestore_client)
    snapshot = _doc_ref(client, job_id).get()
    if not getattr(snapshot, 'exists', False):
        return None
    return snapshot.to_dict()


def confirm_dead_letter(job_id: str, *, firestore_client: Any = None) -> Optional[dict[str, Any]]:
    """Flip a pending record to ``dead_letter``; ``None`` when the doc is missing.

    The ``sync_backfill_dead_letter`` event is emitted only when the
    transaction's winning attempt performed the ``pending -> dead_letter``
    write itself — a retried attempt that observes an already-confirmed doc
    returns ``did_transition=False``, so redeliveries and transaction retries
    cannot double-count the confirmed cohort.
    """
    client = _client(firestore_client)
    doc_ref = _doc_ref(client, job_id)
    now = datetime.now(timezone.utc)

    def _txn(transaction: Any) -> tuple[Optional[dict[str, Any]], bool]:
        snapshot = doc_ref.get(transaction=transaction)
        if not getattr(snapshot, 'exists', False):
            return None, False
        doc = snapshot.to_dict() or {}
        if doc.get('status') == STATUS_DEAD_LETTER:
            return doc, False
        transaction.set(doc_ref, {'status': STATUS_DEAD_LETTER, 'dead_lettered_at': now}, merge=True)
        return {**doc, 'status': STATUS_DEAD_LETTER, 'dead_lettered_at': now}, True

    confirmed, did_transition = firestore.transactional(_txn)(client.transaction())
    if confirmed is not None and did_transition:
        _emit_confirmed(confirmed)
    return confirmed


def _validate_dead_letter_identity(doc: dict[str, Any], job_id: str, uid: Any) -> None:
    """Fail closed when a ledger doc does not belong to this job/uid pair."""
    if doc.get('job_id') != job_id or (isinstance(uid, str) and uid and doc.get('uid') != uid):
        raise RuntimeError(f'sync dead-letter identity mismatch for job {job_id}')


def ensure_dead_letter_confirmed(
    job_id: str,
    *,
    uid: Any = None,
    conversation_id: Any = None,
    failure_code: str = 'unknown',
    firestore_client: Any = None,
) -> dict[str, Any]:
    """Confirm the ledger doc, writing the pending record first when absent.

    The terminal-delivery path uses this before ACK/cleanup: a worker that won
    the Redis terminal CAS but crashed before confirming leaves a pending doc
    this call closes out, and a doc that never landed (older code, wedge) is
    created and confirmed in the same pass — but only when the caller supplies
    a uid, so a fabricated replacement can never pass for the real record. Any
    identity mismatch fails closed instead of confirming someone else's doc.
    """
    existing = get_dead_letter(job_id, firestore_client=firestore_client)
    if existing is None:
        if not isinstance(uid, str) or not uid:
            raise RuntimeError(f'sync dead-letter missing and uid unavailable for job {job_id}')
        record_dead_letter_pending(
            job_id=job_id,
            uid=uid,
            conversation_id=conversation_id,
            failure_code=failure_code,
            firestore_client=firestore_client,
        )
    else:
        _validate_dead_letter_identity(existing, job_id, uid)
    confirmed = confirm_dead_letter(job_id, firestore_client=firestore_client)
    if confirmed is None:
        raise RuntimeError(f'sync dead-letter write did not land for job {job_id}')
    _validate_dead_letter_identity(confirmed, job_id, uid)
    return confirmed

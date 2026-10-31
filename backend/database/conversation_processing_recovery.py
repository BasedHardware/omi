"""Age-bounded processing orphan recovery, fenced against every active job owner."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from google.cloud import firestore

from database import conversation_finalization_jobs as jobs
from database._client import get_firestore_client
from database.conversation_finalization_values import parse_timestamp, uid_from_conversation_path
from database.conversation_terminal_title import kept_row_terminal_update, user_time_zone
from database.quiet_check_retirement import stop_quiet_check_for_conversation


def _has_active_processing_job(transaction: Any, data: dict, job_ref_for_id: Callable | None) -> bool:
    job_id = data.get('finalization_job_id')
    if not job_id:
        return False
    if job_ref_for_id is None:
        return True
    job = job_ref_for_id(job_id).get(transaction=transaction).to_dict() or {}
    return job.get('status') not in jobs.TERMINAL_JOB_STATUSES


def _stamp_processing_admission_if_absent_txn(
    transaction: Any, conversation_ref: Any, now: datetime, job_ref_for_id: Callable | None = None
) -> bool:
    """Server-owned migration: stamp the admission fence on a legacy processing row.

    Returns ``True`` only when a bare ``processing`` row lacking a valid
    ``processing_admitted_at`` was stamped with ``now``. A row already stamped, in
    any other lifecycle state, or absent is left untouched. The stamp is the sole
    authority the orphan sweep trusts; it never terminalizes a row here.
    """
    snapshot = conversation_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return False
    data = snapshot.to_dict() or {}
    if data.get('status') != 'processing':
        return False
    if data.get('deleted') or data.get('discarded') or data.get('deferred'):
        return False
    if isinstance(data.get('processing_admitted_at'), datetime):
        return False
    if _has_active_processing_job(transaction, data, job_ref_for_id):
        return False
    transaction.update(conversation_ref, {'processing_admitted_at': now})
    return True


def stamp_processing_admission_if_absent(uid: str, conversation_id: str, *, firestore_client: Any = None) -> bool:
    """Stamp the authoritative admission fence on a legacy processing conversation."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    transaction = client.transaction()
    transactional = firestore.transactional(_stamp_processing_admission_if_absent_txn)
    return transactional(
        transaction,
        client.collection('users').document(uid).collection(jobs.CONVERSATIONS_COLLECTION).document(conversation_id),
        datetime.now(timezone.utc),
        lambda job_id: client.collection(jobs.FINALIZATION_JOBS_COLLECTION).document(job_id),
    )


def _complete_unstampable_orphan_conversation_txn(
    transaction: Any, conversation_ref: Any, stale_before: datetime, job_ref_for_id: Callable | None = None
) -> bool:
    """Terminalize a legacy orphan whose admission fence can never be stamped.

    A conversation sitting at Firestore's 1 MiB document ceiling rejects every
    growing write, so ``stamp_processing_admission_if_absent`` can never migrate
    it: the row would stay ``processing`` for good while the sweep retries it
    forever. The snapshot's server-owned ``update_time`` stands in for the fence
    the document cannot carry — only a row no writer (including a live processor,
    which is equally unable to write to it) has touched since ``stale_before`` is
    terminalized. Every other ownership fence still applies, and the terminal
    write only shrinks the document, so it fits where the stamp did not.
    """
    snapshot = conversation_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return False
    data = snapshot.to_dict() or {}
    if data.get('status') != 'processing':
        return False
    if data.get('deleted') or data.get('discarded') or data.get('deferred'):
        return False
    if _has_active_processing_job(transaction, data, job_ref_for_id):
        return False
    if parse_timestamp(data.get('processing_admitted_at')) is not None:
        return False  # no longer a legacy row: the admission-fenced path owns it
    last_written = parse_timestamp(getattr(snapshot, 'update_time', None))
    if last_written is None or last_written > stale_before:
        return False
    transaction.update(conversation_ref, {'status': 'completed'})
    return True


def complete_unstampable_orphan_conversation(
    uid: str, conversation_id: str, *, stale_after: timedelta, firestore_client: Any = None
) -> bool:
    """Terminalize a legacy orphan that is too large to accept the admission fence."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    transaction = client.transaction()
    transactional = firestore.transactional(_complete_unstampable_orphan_conversation_txn)
    completed = transactional(
        transaction,
        client.collection('users').document(uid).collection(jobs.CONVERSATIONS_COLLECTION).document(conversation_id),
        datetime.now(timezone.utc) - stale_after,
        lambda job_id: client.collection(jobs.FINALIZATION_JOBS_COLLECTION).document(job_id),
    )
    if completed:
        stop_quiet_check_for_conversation(uid, conversation_id, firestore_client=client)
    return completed


def _complete_orphan_conversation_txn(
    transaction: Any,
    conversation_ref: Any,
    expected_admitted_at: datetime | None,
    now: datetime,
    uid: str | None = None,
    time_zone_for_uid: Callable[[str], str | None] | None = None,
    job_ref_for_id: Callable | None = None,
) -> bool:
    """Terminalize exactly the scanned orphan generation, fencing every live owner.

    Verified immediately before the write, inside the transaction:
    * still ``processing`` (not already completed/discarded/merging),
    * not ``deferred`` (a desktop lazy row that intentionally stays on processing),
    * no active durable job (a terminal job cannot own processing), and
    * ``processing_admitted_at`` still equals the scanned generation (the processor
      has not renewed its lease or been re-admitted).

    Only when every assumption still holds is the row moved to ``completed``. Any
    divergence is an expected CAS fencing (``False``), never a terminalization of
    live or durable-owned work. An untitled row also gets its deterministic title
    (``kept_row_terminal_update``) so it never lands in the list untitled.
    """
    del now  # the terminal write carries no timestamp; the fence is the generation
    snapshot = conversation_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return False
    data = snapshot.to_dict() or {}
    if data.get('status') != 'processing':
        return False
    if data.get('deleted') or data.get('discarded') or data.get('deferred'):
        return False
    if _has_active_processing_job(transaction, data, job_ref_for_id):
        return False
    admitted_at = parse_timestamp(data.get('processing_admitted_at'))
    expected_admitted = parse_timestamp(expected_admitted_at)
    if admitted_at is None or admitted_at != expected_admitted:
        return False
    uid = uid or uid_from_conversation_path(str(getattr(conversation_ref, 'path', '') or ''))
    terminal: dict[str, Any] = {'status': 'completed'}
    if uid:
        terminal = kept_row_terminal_update(uid, data, conversation_ref, terminal, time_zone_for_uid)
    transaction.update(conversation_ref, terminal)
    return True


def complete_orphan_conversation(
    uid: str, conversation_id: str, *, expected_admitted_at: datetime | None, firestore_client: Any = None
) -> bool:
    """Close one crash orphan through the generation/ownership fence."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    transaction = client.transaction()
    transactional = firestore.transactional(_complete_orphan_conversation_txn)
    completed = transactional(
        transaction,
        client.collection('users').document(uid).collection(jobs.CONVERSATIONS_COLLECTION).document(conversation_id),
        expected_admitted_at,
        datetime.now(timezone.utc),
        uid,
        lambda zone_uid: user_time_zone(client, zone_uid),
        lambda job_id: client.collection(jobs.FINALIZATION_JOBS_COLLECTION).document(job_id),
    )
    if completed:
        stop_quiet_check_for_conversation(uid, conversation_id, firestore_client=client)
    return completed

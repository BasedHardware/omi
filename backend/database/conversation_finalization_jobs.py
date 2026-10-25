"""Firestore outbox and lease state for durable conversation finalization.

Cloud Tasks is deliberately only a wake-up mechanism.  The durable source of
truth is one Firestore job per ``(uid, conversation_id, finalization_revision)``.
No transcript, credential, request header, or raw exception is stored here.
"""

from __future__ import annotations

import logging
import math
import os
from hashlib import sha256
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Literal, Mapping, TypedDict

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from config.listen_quiet_finalization import enabled as quiet_finalization_enabled
from database import conversations as conversations_db
from database import recording_sessions as recording_sessions_db
from database.account_deletion_policy import account_deletion_blocks_access, normalize_account_deletion_status
from database.quiet_check_retirement import stop_quiet_check_for_conversation, stop_quiet_checks_for_job
from database._client import document_id_from_seed, get_firestore_client
from database.conversation_terminal_title import (
    dead_letter_conversation_updates,
    kept_row_terminal_update,
    user_time_zone,
)
from database.firestore_transaction_retry import run_with_transaction_contention_retry
from database.firestore_index_registry import (
    FINALIZATION_OLDEST_NONTERMINAL_QUERY,
    MEETING_RECEIPTS_DUE_QUERY,
)
from database.people_stats_cache import invalidate_people_stats_cache
from models.client_processing import PROJECTION_FAMILY_FIELDS
from models.conversation_continuity import continuation_timeout
from utils.conversations.backfill_stats import same_timestamp_revision
from utils.conversations.processing_trigger import PROCESSING_MODES, ProcessingTrigger, is_recovery_trigger
from utils.conversations.recovery import (
    TERMINAL_NO_DERIVED_EFFECTS_FIELD,
    raw_transcript_bytes,
    recovery_audio_file_ids,
    structured_has_protected_content,
)

CONVERSATIONS_COLLECTION = 'conversations'
FINALIZATION_JOBS_COLLECTION = 'conversation_finalization_jobs'
# This projection starts at the first release that writes terminal outcomes.
# It intentionally does not backfill historical jobs: terminal writes for rows
# without this generation remain durable on the job itself but cannot move the
# new denominator.  Reading this fixed shard set is safe on every replica.
FINALIZATION_PROJECTION_COLLECTION = 'conversation_finalization_projection_shards'
FINALIZATION_PROJECTION_GENERATION = 'terminal-outcomes-v1'
FINALIZATION_PROJECTION_SHARD_COUNT = 16

FinalizationJobStatus = Literal['queued', 'leased', 'completed', 'dead_letter', 'blocked_byok']
TERMINAL_JOB_STATUSES = frozenset({'completed', 'dead_letter'})
NONTERMINAL_JOB_STATUSES = frozenset({'queued', 'leased', 'blocked_byok'})
DEFAULT_LEASE_SECONDS = 1500
DEFAULT_RECONCILE_STALE_SECONDS = 300
# Conservative: the synchronous legacy route admits processing with no durable
# job, and its request thread is not killed by the HTTP timeout, so the orphan
# window must exceed any plausible live synchronous process_conversation run.
DEFAULT_ORPHAN_RECONCILE_STALE_SECONDS = 900
# Prompt reclaim restores reconnect waiting; abandonment bounds that waiting
# by the last live activity, never by recovery bookkeeping activity.
DEFAULT_BYOK_ABANDONED_AFTER_SECONDS = 14 * 86_400
BYOK_ABANDONED_FAILURE_CODE = 'byok_session_abandoned'
MEETING_RECEIPT_SCHEMA_VERSION = 1
MEETING_RECEIPT_RECONCILE_AFTER = timedelta(minutes=10)


class FinalizationIntent(TypedDict):
    job_id: str | None
    status: str
    dispatch_generation: int | None
    requires_byok: bool
    fanout_key: str | None
    created: bool


class FinalizationAdmission(TypedDict):
    """Pure lifecycle-service decision evaluated inside the outbox transaction."""

    accepted: bool
    terminal: bool
    reason: str
    fanout_key: str | None


class FinalizationFanoutClaim(TypedDict):
    """Ownership result for the durable external-integration fanout."""

    status: str
    fanout_key: str | None


class ByokAbandonment(TypedDict):
    """Terminal disposition of one stranded BYOK finalization job.

    ``status`` is ``abandoned`` only when this call committed the terminal;
    ``fenced`` means an expected ownership CAS loss and ``missing`` an absent
    row.  ``conversation_outcome`` separates the two very different real shapes:
    ``closed`` (the bound conversation was still ``processing`` and this call
    ended its lifecycle) from ``already_terminal`` / ``unbound`` / ``missing``
    (the conversation was finalized by the inline pusher lane, or moved on, and
    the job row was pure orphaned bookkeeping).
    """

    status: str
    conversation_outcome: str


class FinalizationClaim(TypedDict):
    """Result of a claim, including the per-claim ownership fence."""

    status: str
    lease_epoch: int | None
    attempt_count: int
    created_at: datetime | None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: Any) -> datetime | None:
    """Parse aware/naive datetimes, ISO-8601 strings, and numeric epoch timestamps to UTC."""
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        clean = value.strip()
        if not clean:
            return None
        try:
            dt = datetime.fromisoformat(clean.replace('Z', '+00:00'))
            return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            pass
        try:
            sec = float(clean)
            if not math.isnan(sec) and not math.isinf(sec) and 0 <= sec <= 253402300799:
                return datetime.fromtimestamp(sec, timezone.utc)
        except (ValueError, TypeError, OverflowError):
            pass
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            sec = float(value)
            if not math.isnan(sec) and not math.isinf(sec) and 0 <= sec <= 253402300799:
                return datetime.fromtimestamp(sec, timezone.utc)
        except (ValueError, TypeError, OverflowError):
            pass
        return None
    return None


def get_finalization_reconcile_stale_after() -> timedelta:
    """Return the bounded delay before a missed handoff becomes replayable."""
    try:
        seconds = int(os.getenv('LISTEN_FINALIZATION_RECONCILE_STALE_SECONDS', str(DEFAULT_RECONCILE_STALE_SECONDS)))
    except ValueError:
        seconds = DEFAULT_RECONCILE_STALE_SECONDS
    return timedelta(seconds=max(30, seconds))


def get_stale_processing_orphan_after() -> timedelta:
    """Return the bounded delay before a bare-`processing` row is a crash orphan.

    Bounds the authoritative, server-owned admission fence
    (``processing_admitted_at``), never caller-controlled ``created_at``. Distinct
    from the durable-job replay window (which a lease already bounds); this path
    owns no lease, so the value is clamped to a conservative floor (300s, longer
    than any plausible live synchronous ``process_conversation`` run) and a
    one-day ceiling so an operator misconfiguration cannot defer recovery for an
    unbounded period. Classified as a reliability recovery knob; deploy default
    is unset so the floor applies.
    """
    try:
        seconds = int(
            os.getenv('LISTEN_FINALIZATION_ORPHAN_STALE_SECONDS', str(DEFAULT_ORPHAN_RECONCILE_STALE_SECONDS))
        )
    except ValueError:
        seconds = DEFAULT_ORPHAN_RECONCILE_STALE_SECONDS
    return timedelta(seconds=min(86_400, max(300, seconds)))


def get_byok_abandoned_after() -> timedelta:
    """Return the bounded age after which a stranded BYOK job is abandoned.

    Bounds the server-owned last-activity instant on the job. Clamped to a
    one-day floor, so a live session that legitimately reconnects always wins,
    and a 90-day ceiling, so an operator misconfiguration cannot defer the
    disposition of an unownable row for an unbounded period. Classified as a
    reliability recovery knob; the deploy default is unset, so the built-in
    14-day default applies.
    """
    try:
        seconds = int(
            os.getenv('LISTEN_FINALIZATION_BYOK_ABANDONED_SECONDS', str(DEFAULT_BYOK_ABANDONED_AFTER_SECONDS))
        )
    except ValueError:
        seconds = DEFAULT_BYOK_ABANDONED_AFTER_SECONDS
    return timedelta(seconds=min(90 * 86_400, max(86_400, seconds)))


def _claim_result(
    status: str,
    lease_epoch: int | None = None,
    attempt_count: int = 0,
    created_at: datetime | None = None,
) -> FinalizationClaim:
    return {
        'status': status,
        'lease_epoch': lease_epoch,
        'attempt_count': attempt_count,
        'created_at': created_at,
    }


def _is_current_lease(job: dict[str, Any], dispatch_generation: int, lease_epoch: int) -> bool:
    return (
        job.get('status') == 'leased'
        and int(job.get('dispatch_generation') or 1) == dispatch_generation
        and int(job.get('lease_epoch') or 0) == lease_epoch
    )


def _client(firestore_client: Any = None) -> Any:
    return firestore_client if firestore_client is not None else get_firestore_client()


def _conversation_ref(client: Any, uid: str, conversation_id: str) -> Any:
    return client.collection('users').document(uid).collection(CONVERSATIONS_COLLECTION).document(conversation_id)


def _uid_from_conversation_path(path: str) -> str | None:
    """Return the uid from a ``users/{uid}/conversations/{conversation_id}`` path."""
    parts = path.split('/')
    if len(parts) == 4 and parts[0] == 'users' and parts[2] == CONVERSATIONS_COLLECTION:
        return parts[1]
    return None


def _job_ref(client: Any, job_id: str) -> Any:
    return client.collection(FINALIZATION_JOBS_COLLECTION).document(job_id)


def _projection_shard(job_id: str) -> int:
    """Choose a stable aggregate shard without exposing job identity in metrics."""
    return int.from_bytes(sha256(job_id.encode('utf-8')).digest()[:4], 'big') % FINALIZATION_PROJECTION_SHARD_COUNT


def _projection_shard_id(generation: str, shard: int) -> str:
    return f'{generation}-{shard:02d}'


def _projection_ref_for_job(projection_collection: Any, job: Mapping[str, Any]) -> Any | None:
    generation = job.get('projection_generation')
    shard = job.get('projection_shard')
    if not isinstance(generation, str) or not isinstance(shard, int):
        return None
    if generation != FINALIZATION_PROJECTION_GENERATION or not 0 <= shard < FINALIZATION_PROJECTION_SHARD_COUNT:
        return None
    return projection_collection.document(_projection_shard_id(generation, shard))


def _record_projection_delta(
    transaction: Any, projection_collection: Any | None, job: Mapping[str, Any], **deltas: int
) -> None:
    """Atomically add state deltas for an admitted projection generation.

    A terminal replay returns before this helper, and Firestore retries rerun
    the transaction against a fresh snapshot. Therefore each committed state
    transition contributes exactly once without a per-job metrics side record.
    """
    if projection_collection is None:
        return
    shard_ref = _projection_ref_for_job(projection_collection, job)
    if shard_ref is None:
        return
    fields: dict[str, Any] = {
        'generation': FINALIZATION_PROJECTION_GENERATION,
        'shard': int(job['projection_shard']),
    }
    fields.update({name: firestore.Increment(delta) for name, delta in deltas.items() if delta})
    if len(fields) == 2:
        return
    transaction.set(shard_ref, fields, merge=True)


def _job_id(uid: str, conversation_id: str, revision: int) -> str:
    return document_id_from_seed(f'listen-finalization:{uid}:{conversation_id}:{revision}')


def _intent_from_job(job_id: str, data: dict[str, Any], *, created: bool = False) -> FinalizationIntent:
    return {
        'job_id': job_id,
        'status': str(data.get('status') or 'queued'),
        'dispatch_generation': int(data.get('dispatch_generation') or 1),
        'requires_byok': bool(data.get('requires_byok')),
        'fanout_key': data.get('fanout_key') if isinstance(data.get('fanout_key'), str) else None,
        'created': created,
    }


def _no_finalization_intent(status: str) -> FinalizationIntent:
    return {
        'job_id': None,
        'status': status,
        'dispatch_generation': None,
        'requires_byok': False,
        'fanout_key': None,
        'created': False,
    }


def _conversation_has_finalization_content(
    uid: str, conversation: Mapping[str, Any], conversation_ref: Any, transaction: Any
) -> bool:
    """Read current and pre-marker photo content within the admission transaction."""
    if conversations_db.raw_conversation_has_content(uid, dict(conversation)):
        return True
    # Pre-marker photo-only recordings keep their durable children admissible until legacy
    # rows have naturally finalized, without moving the read outside this
    # transaction's authoritative snapshot.
    return next(iter(conversation_ref.collection('photos').limit(1).stream(transaction=transaction)), None) is not None


def recovery_admission_refusal(
    uid: str,
    conversation: Mapping[str, Any],
    recovery_cutoff: datetime | None,
) -> str | None:
    """Bounded refusal reason for one SERVER_RECOVERY admission, or ``None``.

    Checked against the outbox transaction's authoritative snapshot before writes,
    and by the sweep for bounded, content-free action logs.

    The one-attempt policy is structural: a row carrying any
    ``finalization_job_id`` (including a dead-lettered one) is refused rather
    than minting a second finalization revision, because the deterministic
    ``(uid, conversation_id, revision)`` identity cannot safely re-admit a
    terminal generation. Those rows page for manual review instead.
    """
    if recovery_cutoff is None:
        return 'no_cutoff'
    status = getattr(conversation.get('status'), 'value', conversation.get('status'))
    if status != 'in_progress':
        return 'status'
    if conversation.get('deleted') or conversation.get('discarded'):
        return 'tombstoned'
    if conversation.get('deferred'):
        return 'deferred'
    if conversation.get('is_locked'):
        return 'locked'
    processing_state = getattr(conversation.get('processing_state'), 'value', conversation.get('processing_state'))
    if processing_state == 'local_pending':
        return 'local_pending'
    if conversation.get(TERMINAL_NO_DERIVED_EFFECTS_FIELD):
        return 'terminal_no_derived'
    source = getattr(conversation.get('source'), 'value', conversation.get('source'))
    if source != 'omi' and not (source == 'phone' and quiet_finalization_enabled()):
        return 'source'
    if structured_has_protected_content(conversation.get('structured'), conversation.get('user_title')):
        return 'protected_content'
    if conversation.get('finalization_job_id'):
        return 'has_job'
    from utils.conversations.lifecycle_clocks import speech_clock

    finished_at = speech_clock(uid, conversation)
    if not isinstance(finished_at, datetime):
        return 'no_finished_at'
    cut = recovery_cutoff if recovery_cutoff.tzinfo else recovery_cutoff.replace(tzinfo=timezone.utc)
    if (finished_at if finished_at.tzinfo else finished_at.replace(tzinfo=timezone.utc)) > cut:
        return 'not_stale'
    if not (conversation.get('audio_files') or conversations_db.raw_conversation_has_content(uid, dict(conversation))):
        return 'no_content'
    if recovery_audio_file_ids(conversation) is None:
        return 'oversized_audio_files'
    return None


def recording_session_lease_expiry(
    transaction: Any,
    recording_sessions_collection: Any | None,
    uid: str,
    conversation_id: str,
    conversation: Mapping[str, Any],
    now: datetime,
) -> datetime | None:
    """Read the live-session fence in the same transaction as recovery admission."""
    external_data = conversation.get('external_data') or {}
    if not isinstance(external_data, Mapping):
        return None
    recording_session_id = external_data.get('recording_session_id')
    if not isinstance(recording_session_id, str) or not recording_session_id or recording_sessions_collection is None:
        return None
    snapshot = recording_sessions_collection.document(recording_session_id).get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return None
    session = snapshot.to_dict() or {}
    if (
        session.get('uid') != uid
        or session.get('recording_session_id') != recording_session_id
        or session.get('conversation_id') != conversation_id
        or str(session.get('lifecycle_phase') or '') != 'in_progress'
    ):
        return None
    lease_expires_at = session.get('lease_expires_at')
    if not isinstance(lease_expires_at, datetime):
        return None
    if lease_expires_at.tzinfo is None and now.tzinfo is not None:
        lease_expires_at = lease_expires_at.replace(tzinfo=timezone.utc)
    return lease_expires_at


class BackfillAdmissionFence(TypedDict, total=False):
    expected_update_time: datetime | None
    backfill_run_id: str | None
    expected_session_revision: str | None


def has_finalization_job_for_revision(
    transaction: Any, jobs_collection: Any, uid: str, conversation_id: str, revision: int
) -> bool:
    """Read the deterministic generation even when its row bind is absent."""
    return bool(jobs_collection.document(_job_id(uid, conversation_id, revision)).get(transaction=transaction).exists)


def backfill_owner_available(transaction: Any, user_ref: Any, jobs_collection: Any) -> bool:
    """One outstanding historical generation per owner, across operator restarts."""
    snapshot = user_ref.collection('backfill_state').document('inflight').get(transaction=transaction)
    state = snapshot.to_dict() or {}
    previous = state.get('job_id')
    if not previous:
        return True
    job_snapshot = jobs_collection.document(previous).get(transaction=transaction)
    # Missing ownership is uncertain, never a reason to create more work.
    return bool(job_snapshot.exists and (job_snapshot.to_dict() or {}).get('status') == 'completed')


def _snapshot_bound_projection_updates(
    uid: str,
    conversation: Mapping[str, Any],
    extra_updates: Mapping[str, Any] | None,
    *,
    transcript_corrections: list[dict] | None = None,
) -> dict[str, Any]:
    """Bind ``extra_updates`` to this snapshot, then keep projection fields only.

    A later projection that binds here overwrites the display field (1.7c);
    one that does not is dropped. Binding is the same helper every exit uses
    — not a second write path per branch.
    """
    bound = conversations_db.extra_updates_with_bound_client_processing(
        uid, conversation, extra_updates, transcript_corrections=transcript_corrections
    )
    return {field: bound[field] for field in PROJECTION_FAMILY_FIELDS if field in bound}


# The only caller metadata this transaction may persist alongside its own
# lifecycle keys. An allowlist, not a denylist: Firestore reads a dotted key as
# a nested field path, so ``client_processing.title`` is a write *into* the
# projection that no exact-name denylist of ``PROJECTION_FAMILY_FIELDS`` would
# catch. Projection fields are owned by ``_apply_snapshot_bound_projection``,
# and the bind report is an out-parameter, never a document field.
_CALLER_LIFECYCLE_METADATA: frozenset[str] = frozenset({'external_data'})


def _non_projection_extra_updates(extra_updates: Mapping[str, Any] | None) -> dict[str, Any]:
    """Allowlisted caller metadata the create path may persist (calendar context)."""
    return {key: value for key, value in (extra_updates or {}).items() if key in _CALLER_LIFECYCLE_METADATA}


def _apply_snapshot_bound_projection(
    transaction: Any,
    conversation_ref: Any,
    uid: str,
    conversation: Mapping[str, Any] | None,
    extra_updates: Mapping[str, Any] | None,
    lifecycle_updates: Mapping[str, Any],
) -> None:
    """Write snapshot-bound projection fields, then any exit-owned lifecycle.

    The durable intent transaction's only conversation write. Projection
    fields come from this helper alone: lifecycle keys in ``lifecycle_updates``
    (job identity, generation, status, deferred, calendar context) are merged
    after, and a projection key in that mapping cannot bypass the bind.
    """
    if conversation is None:
        return
    corrections = None
    if conversation.get('has_transcript_corrections') and any(
        field in (extra_updates or {}) for field in PROJECTION_FAMILY_FIELDS
    ):
        from database import review_store

        overlay_ref = conversation_ref.parent.parent.collection('transcript_corrections').document(conversation_ref.id)
        overlay = overlay_ref.get(transaction=transaction).to_dict()
        corrections = review_store.require_doc(uid, overlay).get('source')
        if not isinstance(corrections, list):
            raise ValueError('Transcript correction overlay invalid')
    conversation_updates = _snapshot_bound_projection_updates(
        uid, conversation, extra_updates, transcript_corrections=corrections
    )
    for key, value in lifecycle_updates.items():
        # A dotted key is a Firestore field path: ``client_processing.title``
        # writes inside the projection without going through the bind.
        if key.split('.', 1)[0] in PROJECTION_FAMILY_FIELDS:
            continue
        conversation_updates[key] = value
    if conversation_updates:
        transaction.update(conversation_ref, conversation_updates)


def _create_or_get_finalization_intent_txn(
    transaction: Any,
    conversation_ref: Any,
    jobs_collection: Any,
    uid: str,
    conversation_id: str,
    requires_byok: bool,
    finalization_admission: Callable[[Mapping[str, Any]], FinalizationAdmission],
    now: datetime,
    *,
    projection_collection: Any | None = None,
    trigger: ProcessingTrigger = ProcessingTrigger.CAPTURE_END,
    extra_updates: Mapping[str, Any] | None = None,
    recovery_cutoff: datetime | None = None,
    recording_sessions_collection: Any | None = None,
    expected_update_time: datetime | None = None,
    backfill_run_id: str | None = None,
    expected_session_revision: str | None = None,
    account_deletion_ref: Any | None = None,
    require_expired_recording_lease: bool = False,
) -> FinalizationIntent:
    """Persist finalization ownership before any pusher or task handoff.

    Every return runs ``_apply_snapshot_bound_projection`` in ``finally``.
    A new exit inside the ``try`` is therefore bound automatically; do not
    add a conversation write, or a return, outside that ``try``.
    """
    intent: FinalizationIntent = _no_finalization_intent('missing')
    lifecycle_updates: dict[str, Any] = {}
    conversation: dict[str, Any] | None = None
    raised = False
    try:
        conversation_snapshot = conversation_ref.get(transaction=transaction)
        if not getattr(conversation_snapshot, 'exists', False):
            return intent

        loaded: dict[str, Any] = conversation_snapshot.to_dict() or {}
        conversation = loaded
        if trigger is ProcessingTrigger.SILENT_BACKFILL:
            if extra_updates:
                raise ValueError('historical admission cannot update projections')
            if loaded.get('record_lane_owner'):
                return _no_finalization_intent('refused_record_owner')
            if expected_update_time is None or not backfill_run_id:
                return _no_finalization_intent('refused_unbound_backfill')
            if not same_timestamp_revision(conversation_snapshot.update_time, expected_update_time):
                return _no_finalization_intent('refused_revision_changed')
            # A changed/renewed lease refuses even if it expired by execution.
            external = loaded.get('external_data') or {}
            sid = external.get('recording_session_id') if isinstance(external, Mapping) else None
            observed_session_revision = None
            if sid is not None and (not isinstance(sid, str) or not sid or '/' in sid):
                return _no_finalization_intent('refused_invalid_session')
            if sid and recording_sessions_collection is not None:
                session_snapshot = recording_sessions_collection.document(sid).get(transaction=transaction)
                stamp = getattr(session_snapshot, 'update_time', None)
                if stamp is not None:
                    observed_session_revision = stamp.rfc3339() if hasattr(stamp, 'rfc3339') else stamp.isoformat()
            if observed_session_revision != expected_session_revision:
                return _no_finalization_intent('refused_session_changed')
            user_ref = conversation_ref.parent.parent
            if not backfill_owner_available(transaction, user_ref, jobs_collection):
                return _no_finalization_intent('refused_owner_inflight')
            privacy = user_ref.get(transaction=transaction).to_dict() or {}
            if privacy.get('data_protection_level', 'enhanced') not in {'standard', 'enhanced'}:
                return _no_finalization_intent('refused_privacy')
            if (privacy.get('byok') or {}).get('active'):
                return _no_finalization_intent('refused_byok')
        if is_recovery_trigger(trigger):
            if trigger is ProcessingTrigger.SERVER_RECOVERY and account_deletion_ref is not None:
                marker = account_deletion_ref.get(transaction=transaction)
                deletion_status = normalize_account_deletion_status(
                    marker_exists=bool(marker.exists),
                    raw_status=(marker.to_dict() or {}).get('wipe_status'),
                )
                if account_deletion_blocks_access(deletion_status):
                    intent = _no_finalization_intent('refused_account_deleting')
                    return intent
            refusal = recovery_admission_refusal(uid, loaded, recovery_cutoff)
            if refusal is not None:
                intent = _no_finalization_intent(f'refused_{refusal}')
                return intent
            if quiet_finalization_enabled():
                timeout = loaded.get('listen_quiet_timeout_seconds', 120)
                if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not math.isfinite(timeout):
                    timeout = 120
                timeout = max(1, min(timeout, 14400))
                finished_at = loaded['finished_at']
                finished_at = finished_at if finished_at.tzinfo else finished_at.replace(tzinfo=timezone.utc)
                if finished_at + timedelta(seconds=continuation_timeout(loaded, timeout)) > now:
                    intent = _no_finalization_intent('refused_not_quiet')
                    return intent
            lease_expiry = recording_session_lease_expiry(
                transaction,
                recording_sessions_collection,
                uid,
                conversation_id,
                loaded,
                now,
            )
            if require_expired_recording_lease and lease_expiry is None:
                intent = _no_finalization_intent('refused_recording_lease_unknown')
                return intent
            if lease_expiry is not None and lease_expiry > now:
                intent = _no_finalization_intent('refused_active_recording_session')
                return intent
        if loaded.get('deferred'):
            intent = _no_finalization_intent('deferred')
            return intent
        if not is_recovery_trigger(trigger) and not _conversation_has_finalization_content(
            uid, loaded, conversation_ref, transaction
        ):
            intent = _no_finalization_intent('no_content')
            return intent

        # The lifecycle service owns this pure decision, but it is evaluated while
        # Firestore holds the conversation transaction snapshot. A late disconnect
        # therefore cannot reopen a failed/discarded terminal row after a stale
        # pre-transaction read.
        admission = finalization_admission(loaded)
        if admission['terminal']:
            intent = _no_finalization_intent(admission['reason'])
            return intent

        existing_job_id = loaded.get('finalization_job_id')
        if isinstance(existing_job_id, str) and existing_job_id:
            existing_ref = jobs_collection.document(existing_job_id)
            existing_snapshot = existing_ref.get(transaction=transaction)
            if getattr(existing_snapshot, 'exists', False):
                intent = _intent_from_job(existing_job_id, existing_snapshot.to_dict() or {})
                return intent

        if not admission['accepted'] or not admission['fanout_key']:
            intent = _no_finalization_intent(admission['reason'])
            return intent

        revision = int(loaded.get('finalization_revision') or 0) + 1
        job_id = _job_id(uid, conversation_id, revision)
        job_ref = jobs_collection.document(job_id)
        job_snapshot = job_ref.get(transaction=transaction)
        if getattr(job_snapshot, 'exists', False):
            job = job_snapshot.to_dict() or {}
            # Lifecycle fields stay owned by this attach; extra_updates may only
            # contribute a snapshot-bound projection, never identity or status.
            lifecycle_updates.update(
                {
                    'status': 'processing',
                    'finalization_job_id': job_id,
                    'finalization_revision': revision,
                    'finalization_status': job.get('status', 'queued'),
                }
            )
            intent = _intent_from_job(job_id, job)
            return intent

        if trigger is ProcessingTrigger.SERVER_RECOVERY:
            requires_byok = bool(requires_byok or loaded.get('listen_finalization_requires_byok'))
        status: FinalizationJobStatus = 'blocked_byok' if requires_byok else 'queued'
        job = {
            'schema_version': 1,
            'uid': uid,
            'conversation_id': conversation_id,
            'finalization_revision': revision,
            'status': status,
            'requires_byok': requires_byok,
            'client_platform': loaded.get('client_platform'),
            # Persist why this generation is processed with the immutable
            # finalization generation so a replay cannot change it.
            'processing_trigger': trigger.value,
            # Legacy mirror so a worker from before processing_trigger (a
            # rollback) still runs the same mode; drop after one release.
            'force_process': PROCESSING_MODES[trigger].run_now,
            'fanout_key': admission['fanout_key'],
            'fanout_status': 'pending',
            'dispatch_generation': 1,
            'attempt_count': 0,
            'task_retry_count': 0,
            'projection_generation': FINALIZATION_PROJECTION_GENERATION,
            'projection_shard': _projection_shard(job_id),
            'created_at': now,
            'updated_at': now,
            'dispatch_requested_at': now,
        }
        if trigger is ProcessingTrigger.SILENT_BACKFILL:
            job['delivery_policy'] = 'silent_backfill_v1'
            job['backfill_run_id'] = backfill_run_id
            lifecycle_updates['silent_backfill'] = {'version': 1, 'run_id': backfill_run_id}
        if is_recovery_trigger(trigger):
            job['selfheal_attempt'] = 1
            job['selfheal_enqueued_at'] = now
            job['selfheal_transcript_bytes'] = raw_transcript_bytes(loaded)
            job['selfheal_audio_file_ids'] = recovery_audio_file_ids(loaded) or []
        if not requires_byok:
            job['reconcile_after_at'] = now + get_finalization_reconcile_stale_after()
        if trigger is ProcessingTrigger.SILENT_BACKFILL:
            transaction.set(
                conversation_ref.parent.parent.collection('backfill_state').document('inflight'),
                {'job_id': job_id, 'run_id': backfill_run_id, 'created_at': now},
            )
        transaction.set(job_ref, job)
        _record_projection_delta(
            transaction,
            projection_collection,
            job,
            accepted=1,
            # Written out rather than **-unpacked: an unpacked argument list is
            # opaque to every scanner in the trust-boundary guardrail at once,
            # so this function may not use one. A zero delta is skipped by
            # _record_projection_delta exactly as an absent key is.
            blocked_byok=1 if requires_byok else 0,
            queued=0 if requires_byok else 1,
        )
        # Lifecycle fields are authoritative to this outbox transaction. Callers
        # may atomically persist request metadata (for example calendar context),
        # but cannot override the accepted generation's identity or status.
        # A T1-validated projection in extra_updates is re-checked against this
        # snapshot in ``finally`` so a concurrent transcript mutation cannot
        # resurrect it on T2.
        lifecycle_updates.update(_non_projection_extra_updates(extra_updates))
        lifecycle_updates.update(
            {
                'status': 'processing',
                'finalization_job_id': job_id,
                'finalization_revision': revision,
                'finalization_status': status,
            }
        )
        intent = _intent_from_job(job_id, job, created=True)
        return intent
    except BaseException:
        # This frame's own failure. ``sys.exc_info()`` is wrong here: it also
        # reports an exception being handled by a *caller* frame, so a
        # finalization invoked from inside an ``except`` block would commit its
        # job and silently skip the conversation bind.
        raised = True
        raise
    finally:
        # Only on a normal exit. An exception aborts the transaction, so the
        # write would never commit; attempting it can only replace the real
        # traceback with a binding error raised inside ``finally``.
        if not raised:
            _apply_snapshot_bound_projection(
                transaction,
                conversation_ref,
                uid,
                conversation,
                extra_updates,
                lifecycle_updates,
            )


def create_or_get_finalization_intent(
    uid: str,
    conversation_id: str,
    *,
    requires_byok: bool,
    finalization_admission: Callable[[Mapping[str, Any]], FinalizationAdmission],
    trigger: ProcessingTrigger = ProcessingTrigger.CAPTURE_END,
    extra_updates: Mapping[str, Any] | None = None,
    recovery_cutoff: datetime | None = None,
    require_expired_recording_lease: bool = False,
    firestore_client: Any = None,
    expected_update_time: datetime | None = None,
    backfill_run_id: str | None = None,
    expected_session_revision: str | None = None,
) -> FinalizationIntent:
    client = _client(firestore_client)
    conversation_ref = _conversation_ref(client, uid, conversation_id)
    jobs_collection = client.collection(FINALIZATION_JOBS_COLLECTION)
    projection_collection = client.collection(FINALIZATION_PROJECTION_COLLECTION)
    user_ref = client.collection('users').document(uid)
    recording_sessions_collection = user_ref.collection(recording_sessions_db.RECORDING_SESSIONS_COLLECTION)

    def create_intent_in_transaction(transaction: Any) -> FinalizationIntent:
        # The Firestore SDK's transactional wrapper retains retry state. Build
        # it for this outer attempt so concurrent REST finalizers always get a
        # fresh transaction and wrapper after read-time contention.
        transactional = firestore.transactional(_create_or_get_finalization_intent_txn)
        return transactional(
            transaction,
            conversation_ref,
            jobs_collection,
            uid,
            conversation_id,
            requires_byok,
            finalization_admission,
            _now(),
            projection_collection=projection_collection,
            trigger=trigger,
            extra_updates=extra_updates,
            recovery_cutoff=recovery_cutoff,
            recording_sessions_collection=recording_sessions_collection,
            expected_update_time=expected_update_time,
            backfill_run_id=backfill_run_id,
            expected_session_revision=expected_session_revision,
            account_deletion_ref=(
                client.collection('account_deletions').document(uid)
                if trigger is ProcessingTrigger.SERVER_RECOVERY
                else None
            ),
            require_expired_recording_lease=require_expired_recording_lease,
        )

    intent = run_with_transaction_contention_retry(
        client.transaction,
        create_intent_in_transaction,
        operation_name='conversation_finalization_intent',
    )
    stop_quiet_check_for_conversation(uid, conversation_id, firestore_client=client)
    if intent['created']:
        invalidate_people_stats_cache(uid)
    return intent


def _resume_blocked_byok_job_txn(
    transaction: Any, job_ref: Any, now: datetime, projection_collection: Any | None = None
) -> FinalizationIntent:
    snapshot = job_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return {
            'job_id': None,
            'status': 'missing',
            'dispatch_generation': None,
            'requires_byok': False,
            'fanout_key': None,
            'created': False,
        }
    job = snapshot.to_dict() or {}
    if job.get('status') == 'blocked_byok' and job.get('requires_byok'):
        transaction.update(
            job_ref,
            {
                'status': 'queued',
                'updated_at': now,
                'last_byok_resume_at': now,
                'byok_last_activity_at': firestore.DELETE_FIELD,
                # Due reconciliation revokes ownership, never processes BYOK.
                'reconcile_after_at': now + get_finalization_reconcile_stale_after(),
            },
        )
        _record_projection_delta(transaction, projection_collection, job, blocked_byok=-1, queued=1)
        job['status'] = 'queued'
    return _intent_from_job(snapshot.id, job)


def resume_blocked_byok_job_for_live_session(job_id: str, *, firestore_client: Any = None) -> FinalizationIntent:
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_resume_blocked_byok_job_txn)
    return transactional(
        transaction,
        _job_ref(client, job_id),
        _now(),
        client.collection(FINALIZATION_PROJECTION_COLLECTION),
    )


def _claim_finalization_job_txn(
    transaction: Any,
    job_ref: Any,
    dispatch_generation: int,
    allow_byok: bool,
    lease_seconds: int,
    now: datetime,
    expected_uid: str | None = None,
    expected_conversation_id: str | None = None,
    projection_collection: Any | None = None,
    count_worker_claim: bool = False,
) -> FinalizationClaim:
    snapshot = job_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return _claim_result('missing')
    job = snapshot.to_dict() or {}
    status = str(job.get('status') or '')
    if expected_uid is not None and job.get('uid') != expected_uid:
        return _claim_result('identity_mismatch')
    if expected_conversation_id is not None and job.get('conversation_id') != expected_conversation_id:
        return _claim_result('identity_mismatch')
    if status == 'completed' and job.get('finalization_outcome') == 'fenced':
        return _claim_result('fenced')
    if status in TERMINAL_JOB_STATUSES:
        return _claim_result(status)
    if bool(job.get('requires_byok')) and not allow_byok:
        return _claim_result('blocked_byok')
    if status == 'blocked_byok':
        return _claim_result('blocked_byok')
    if int(job.get('dispatch_generation') or 1) != dispatch_generation:
        return _claim_result('stale_generation')
    if status == 'leased':
        lease_expires_at = job.get('lease_expires_at')
        if isinstance(lease_expires_at, datetime) and lease_expires_at > now:
            return _claim_result('leased')
    if status not in ('queued', 'leased'):
        return _claim_result('not_actionable')

    lease_epoch = int(job.get('lease_epoch') or 0) + 1
    lease_expires_at = now + timedelta(seconds=lease_seconds)
    # Keep the failed-processing count separate from worker claims: a live
    # pusher session handoff is not a failed attempt. Each accepted Cloud Tasks claim
    # consumes one durable worker slot, including a worker killed before it can
    # write a failure. The transaction and lease fence make duplicates free.
    attempt_count = int(job.get('attempt_count') or 0)
    worker_claim_count = int(job.get('worker_claim_count') or 0) + (1 if count_worker_claim else 0)
    if count_worker_claim:
        attempt_count = max(attempt_count, worker_claim_count - 1)

    transaction.update(
        job_ref,
        {
            'status': 'leased',
            'leased_at': now,
            'lease_expires_at': lease_expires_at,
            # A lease epoch fences a worker that resumes after another worker
            # has reclaimed its expired lease. Terminal writes must present it.
            'lease_epoch': lease_epoch,
            'lease_counts_worker_attempt': count_worker_claim,
            **({'worker_claim_count': worker_claim_count} if count_worker_claim else {}),
            'reconcile_after_at': lease_expires_at,
            'updated_at': now,
        },
    )
    if status == 'queued':
        _record_projection_delta(transaction, projection_collection, job, queued=-1, leased=1)
    created_at = job.get('created_at')
    return _claim_result(
        'claimed',
        lease_epoch,
        attempt_count,
        created_at if isinstance(created_at, datetime) else None,
    )


def claim_finalization_job(
    job_id: str,
    dispatch_generation: int,
    *,
    allow_byok: bool = False,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    expected_uid: str | None = None,
    expected_conversation_id: str | None = None,
    count_worker_claim: bool = False,
    firestore_client: Any = None,
) -> FinalizationClaim:
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_claim_finalization_job_txn)
    return transactional(
        transaction,
        _job_ref(client, job_id),
        dispatch_generation,
        allow_byok,
        lease_seconds,
        _now(),
        expected_uid,
        expected_conversation_id,
        client.collection(FINALIZATION_PROJECTION_COLLECTION),
        count_worker_claim,
    )


def _mark_finalization_completed_txn(
    transaction: Any,
    job_ref: Any,
    dispatch_generation: int,
    lease_epoch: int,
    now: datetime,
    projection_collection: Any | None = None,
) -> bool:
    snapshot = job_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return False
    job = snapshot.to_dict() or {}
    if job.get('status') == 'completed':
        return int(job.get('lease_epoch') or 0) == lease_epoch
    if not _is_current_lease(job, dispatch_generation, lease_epoch):
        return False
    if job.get('fanout_status') != 'completed':
        return False
    transaction.update(
        job_ref,
        {
            'status': 'completed',
            'completed_at': now,
            'terminal_outcome': 'success',
            'updated_at': now,
            'lease_expires_at': now,
            'reconcile_after_at': firestore.DELETE_FIELD,
            'last_failure_code': None,
        },
    )
    _record_projection_delta(transaction, projection_collection, job, leased=-1, completed=1, success=1)
    return True


def mark_finalization_completed(
    job_id: str, dispatch_generation: int, lease_epoch: int, *, firestore_client: Any = None
) -> bool:
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_mark_finalization_completed_txn)
    return transactional(
        transaction,
        _job_ref(client, job_id),
        dispatch_generation,
        lease_epoch,
        _now(),
        client.collection(FINALIZATION_PROJECTION_COLLECTION),
    )


def _mark_finalization_fenced_txn(
    transaction: Any,
    job_ref: Any,
    dispatch_generation: int,
    lease_epoch: int,
    now: datetime,
    projection_collection: Any | None = None,
) -> bool:
    """Terminally complete a current lease that was fenced before fanout.

    A discard or newer lifecycle generation can win after the job lease was
    acquired. That is a successful no-fanout terminal outcome, not a retryable
    processing failure. It must remain distinct from normal completion so a
    replay cannot mistake it for a delivered external integration.
    """
    snapshot = job_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return False
    job = snapshot.to_dict() or {}
    if job.get('status') == 'completed':
        return job.get('finalization_outcome') == 'fenced' and int(job.get('lease_epoch') or 0) == lease_epoch
    if not _is_current_lease(job, dispatch_generation, lease_epoch):
        return False
    if job.get('fanout_status') not in (None, 'pending'):
        return False
    transaction.update(job_ref, _fenced_finalization_update(now))
    _record_projection_delta(transaction, projection_collection, job, leased=-1, completed=1, stale=1)
    return True


def mark_finalization_fenced(
    job_id: str, dispatch_generation: int, lease_epoch: int, *, firestore_client: Any = None
) -> bool:
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_mark_finalization_fenced_txn)
    return transactional(
        transaction,
        _job_ref(client, job_id),
        dispatch_generation,
        lease_epoch,
        _now(),
        client.collection(FINALIZATION_PROJECTION_COLLECTION),
    )


def _fanout_key(job: dict[str, Any]) -> str:
    key = job.get('fanout_key')
    if isinstance(key, str) and key:
        return key
    # Backfill jobs created before the durable fanout boundary on their first
    # retry. The key is deterministic per immutable finalization revision.
    return f"conversation:{job.get('conversation_id', '')}:finalization:{int(job.get('finalization_revision') or 1)}"


def _fenced_finalization_update(now: datetime) -> dict[str, Any]:
    """Return the terminal no-fanout state shared by every fencing boundary."""
    return {
        'status': 'completed',
        'completed_at': now,
        'updated_at': now,
        'lease_expires_at': now,
        'reconcile_after_at': firestore.DELETE_FIELD,
        'last_failure_code': None,
        'finalization_outcome': 'fenced',
        'terminal_outcome': 'stale',
        'fanout_status': 'fenced',
        'fanout_fenced_at': now,
    }


def _fanout_claim(status: str, fanout_key: str | None) -> FinalizationFanoutClaim:
    return {'status': status, 'fanout_key': fanout_key}


def _conversation_admits_fanout(conversation: Mapping[str, Any], job: Mapping[str, Any], job_id: str) -> bool:
    """Require the immutable job binding to still name a completed conversation."""
    if conversation.get('discarded') or conversation.get('status') != 'completed':
        return False
    if conversation.get('finalization_job_id') != job_id:
        return False
    try:
        return int(conversation.get('finalization_revision') or 0) == int(job.get('finalization_revision') or 0)
    except (TypeError, ValueError):
        return False


def _claim_finalization_fanout_txn(
    transaction: Any,
    job_ref: Any,
    dispatch_generation: int,
    lease_epoch: int,
    now: datetime,
    conversation_ref_for_job: Callable[[str, str], Any],
    projection_collection: Any | None = None,
) -> FinalizationFanoutClaim:
    """Claim fanout only if this job still owns the completed conversation.

    Reading the conversation in this Firestore transaction makes a concurrent
    discard or newer finalization revision retry the transaction before the
    fanout lease can commit.  The losing state is terminally fenced here,
    rather than leaving a retryable leased job for either worker to replay.
    """
    snapshot = job_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return _fanout_claim('missing', None)
    job = snapshot.to_dict() or {}
    fanout_key = _fanout_key(job)
    if job.get('fanout_status') == 'completed':
        return _fanout_claim('completed', fanout_key)
    if not _is_current_lease(job, dispatch_generation, lease_epoch):
        return _fanout_claim('lease_conflict', fanout_key)

    uid = job.get('uid')
    conversation_id = job.get('conversation_id')
    if not isinstance(uid, str) or not uid or not isinstance(conversation_id, str) or not conversation_id:
        transaction.update(job_ref, _fenced_finalization_update(now))
        _record_projection_delta(transaction, projection_collection, job, leased=-1, completed=1, stale=1)
        return _fanout_claim('fenced', fanout_key)

    conversation_ref = conversation_ref_for_job(uid, conversation_id)
    conversation_snapshot = conversation_ref.get(transaction=transaction)
    conversation = conversation_snapshot.to_dict() if getattr(conversation_snapshot, 'exists', False) else None
    if not isinstance(conversation, Mapping) or not _conversation_admits_fanout(conversation, job, job_ref.id):
        transaction.update(job_ref, _fenced_finalization_update(now))
        _record_projection_delta(transaction, projection_collection, job, leased=-1, completed=1, stale=1)
        return _fanout_claim('fenced', fanout_key)

    transaction.update(
        job_ref,
        {
            'fanout_key': fanout_key,
            'fanout_status': 'leased',
            'fanout_lease_epoch': lease_epoch,
            'fanout_started_at': now,
            'updated_at': now,
        },
    )
    return _fanout_claim('claimed', fanout_key)


def claim_finalization_fanout(
    job_id: str,
    dispatch_generation: int,
    lease_epoch: int,
    *,
    firestore_client: Any = None,
) -> FinalizationFanoutClaim:
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_claim_finalization_fanout_txn)
    return transactional(
        transaction,
        _job_ref(client, job_id),
        dispatch_generation,
        lease_epoch,
        _now(),
        lambda uid, conversation_id: _conversation_ref(client, uid, conversation_id),
        client.collection(FINALIZATION_PROJECTION_COLLECTION),
    )


def _mark_finalization_fanout_completed_txn(
    transaction: Any,
    job_ref: Any,
    dispatch_generation: int,
    lease_epoch: int,
    now: datetime,
) -> bool:
    snapshot = job_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return False
    job = snapshot.to_dict() or {}
    if job.get('fanout_status') == 'completed':
        return int(job.get('fanout_lease_epoch') or 0) == lease_epoch
    if not _is_current_lease(job, dispatch_generation, lease_epoch):
        return False
    transaction.update(
        job_ref,
        {
            'fanout_status': 'completed',
            'fanout_completed_at': now,
            'updated_at': now,
        },
    )
    return True


def mark_finalization_fanout_completed(
    job_id: str,
    dispatch_generation: int,
    lease_epoch: int,
    *,
    firestore_client: Any = None,
) -> bool:
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_mark_finalization_fanout_completed_txn)
    return transactional(
        transaction,
        _job_ref(client, job_id),
        dispatch_generation,
        lease_epoch,
        _now(),
    )


def _mark_finalization_retryable_txn(
    transaction: Any,
    job_ref: Any,
    dispatch_generation: int,
    lease_epoch: int,
    failure_code: str,
    now: datetime,
    projection_collection: Any | None = None,
    count_attempt: bool = True,
) -> bool:
    if not count_attempt and failure_code != 'record_owner_contention':
        raise ValueError('only route contention may defer without a processing attempt')
    snapshot = job_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return False
    job = snapshot.to_dict() or {}
    if not _is_current_lease(job, dispatch_generation, lease_epoch):
        return False
    attempt_count = int(job.get('attempt_count') or 0) + int(count_attempt)
    transaction.update(
        job_ref,
        {
            'status': 'queued',
            'updated_at': now,
            'lease_expires_at': now,
            'attempt_count': attempt_count,
            'reconcile_after_at': now + get_finalization_reconcile_stale_after(),
            'last_failure_code': failure_code,
            # A contention-only delivery did no processing. Refund its durable
            # worker slot too, or the next claim would count it as a killed worker.
            **(
                {'worker_claim_count': max(0, int(job.get('worker_claim_count') or 0) - 1)}
                if not count_attempt and job.get('lease_counts_worker_attempt')
                else {}
            ),
        },
    )
    _record_projection_delta(transaction, projection_collection, job, leased=-1, queued=1)
    return True


def mark_finalization_retryable(
    job_id: str,
    dispatch_generation: int,
    lease_epoch: int,
    failure_code: str = 'processing_failed',
    *,
    firestore_client: Any = None,
    count_attempt: bool = True,
) -> bool:
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_mark_finalization_retryable_txn)
    return transactional(
        transaction,
        _job_ref(client, job_id),
        dispatch_generation,
        lease_epoch,
        failure_code,
        _now(),
        client.collection(FINALIZATION_PROJECTION_COLLECTION),
        count_attempt,
    )


def _mark_finalization_dead_letter_txn(
    transaction: Any,
    job_ref: Any,
    dispatch_generation: int,
    lease_epoch: int,
    retry_count: int,
    now: datetime,
    conversation_ref_for_job: Callable[[str, str], Any] | None = None,
    projection_collection: Any | None = None,
    failure_code: str = 'final_attempt_failed',
    time_zone_for_uid: Callable[[str], str | None] | None = None,
) -> bool:
    snapshot = job_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return False
    job = snapshot.to_dict() or {}
    if not _is_current_lease(job, dispatch_generation, lease_epoch):
        return False
    if job.get('fanout_status') == 'completed':
        # A committed fanout is successful work even if its worker died before
        # closing the job. The caller must finish it with the same lease fence.
        return False
    conversation_ref = None
    conversation = None
    uid = job.get('uid')
    conversation_id = job.get('conversation_id')
    if (
        conversation_ref_for_job is not None
        and isinstance(uid, str)
        and uid
        and isinstance(conversation_id, str)
        and conversation_id
    ):
        # Read the bound conversation before the first transaction write. A
        # final worker failure must close its still-current processing
        # generation atomically with dead-lettering the job; otherwise a crash
        # between independent writes strands the customer on processing.
        conversation_ref = conversation_ref_for_job(uid, conversation_id)
        conversation_snapshot = conversation_ref.get(transaction=transaction)
        conversation = conversation_snapshot.to_dict() if getattr(conversation_snapshot, 'exists', False) else None
    conversation_updates: dict[str, Any] | None = None
    if (
        conversation_ref is not None
        and isinstance(uid, str)
        and isinstance(conversation, Mapping)
        and conversation.get('status') == 'processing'
        and not conversation.get('discarded')
        and conversation.get('finalization_job_id') == job_ref.id
        and conversation.get('finalization_revision') == job.get('finalization_revision')
    ):
        # Computed before the first write: it may read the photos child
        # collection inside this transaction.
        conversation_updates = dead_letter_conversation_updates(
            uid, conversation, conversation_ref, transaction, failure_code, time_zone_for_uid
        )
    if conversation_updates is not None and isinstance(uid, str) and isinstance(conversation, Mapping):
        from database.processing_attention import create_in_transaction

        create_in_transaction(
            transaction, uid, conversation_ref, dict(conversation), conversation_updates, failure_code, now
        )
    transaction.update(
        job_ref,
        {
            'status': 'dead_letter',
            'updated_at': now,
            'terminal_at': now,
            'terminal_outcome': 'failure',
            'lease_expires_at': now,
            'reconcile_after_at': firestore.DELETE_FIELD,
            'task_retry_count': retry_count,
            # Callers pass the inclusive terminal attempt. An exhausted crash
            # claim did no processing, so do not invent another failure here.
            'attempt_count': max(int(job.get('attempt_count') or 0), retry_count),
            'last_failure_code': failure_code,
        },
    )
    _record_projection_delta(transaction, projection_collection, job, leased=-1, dead_letter=1, failure=1)
    if conversation_updates is not None:
        transaction.update(conversation_ref, conversation_updates)
    return True


def mark_finalization_dead_letter(
    job_id: str,
    dispatch_generation: int,
    lease_epoch: int,
    retry_count: int,
    *,
    failure_code: str = 'final_attempt_failed',
    firestore_client: Any = None,
) -> bool:
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_mark_finalization_dead_letter_txn)
    closed = transactional(
        transaction,
        _job_ref(client, job_id),
        dispatch_generation,
        lease_epoch,
        retry_count,
        _now(),
        lambda uid, conversation_id: _conversation_ref(client, uid, conversation_id),
        client.collection(FINALIZATION_PROJECTION_COLLECTION),
        failure_code,
        lambda uid: user_time_zone(client, uid),
    )
    if closed:
        stop_quiet_checks_for_job(job_id, firestore_client=client)
    return closed


def get_finalization_job(job_id: str, *, firestore_client: Any = None) -> dict[str, Any] | None:
    snapshot = _job_ref(_client(firestore_client), job_id).get()
    if not getattr(snapshot, 'exists', False):
        return None
    return snapshot.to_dict() or {}


def _record_meeting_receipt_txn(
    transaction: Any,
    conversation_ref: Any,
    jobs_collection: Any,
    uid: str,
    conversation_id: str,
    finalization_job_id: str | None,
    eligible: bool,
    reason: str,
    duration_s: float,
    dedup_speech_s: float,
    now: datetime,
) -> dict[str, Any]:
    """Create the finalization-job receipt once and project its verdict to the conversation."""
    conversation_snapshot = conversation_ref.get(transaction=transaction)
    if not getattr(conversation_snapshot, 'exists', False):
        return {'status': 'missing'}
    conversation = conversation_snapshot.to_dict() or {}
    existing_job_id = conversation.get('finalization_job_id')
    job_id = (
        finalization_job_id
        if isinstance(finalization_job_id, str) and finalization_job_id
        else (
            existing_job_id
            if isinstance(existing_job_id, str) and existing_job_id
            else _job_id(uid, conversation_id, int(conversation.get('finalization_revision') or 0) + 1)
        )
    )
    job_ref = jobs_collection.document(job_id)
    job_snapshot = job_ref.get(transaction=transaction)
    job = (job_snapshot.to_dict() or {}) if getattr(job_snapshot, 'exists', False) else {}
    if job and (job.get('uid') != uid or job.get('conversation_id') != conversation_id):
        return {'status': 'identity_mismatch'}

    receipt = {
        'meeting_receipt_schema_version': MEETING_RECEIPT_SCHEMA_VERSION,
        'meeting_treatment_eligible': eligible,
        'meeting_treatment_reason': reason,
        'meeting_duration_s': duration_s,
        'meeting_dedup_speech_s': dedup_speech_s,
        'meeting_receipt_created_at': now,
        'meeting_receipt_updated_at': now,
        'meeting_receipt_reconcile_after_at': now + MEETING_RECEIPT_RECONCILE_AFTER,
        'meeting_receipt_intent_id': None,
        'meeting_receipt_intent_persisted_at': None,
        'meeting_receipt_materialized_at': None,
    }
    if job.get('meeting_receipt_schema_version') == MEETING_RECEIPT_SCHEMA_VERSION:
        receipt = {
            key: job.get(key)
            for key in (
                'meeting_receipt_schema_version',
                'meeting_treatment_eligible',
                'meeting_treatment_reason',
                'meeting_duration_s',
                'meeting_dedup_speech_s',
                'meeting_receipt_created_at',
                'meeting_receipt_updated_at',
                'meeting_receipt_reconcile_after_at',
                'meeting_receipt_intent_id',
                'meeting_receipt_intent_persisted_at',
                'meeting_receipt_materialized_at',
            )
            if key in job
        }
    elif job:
        transaction.update(job_ref, receipt)
    else:
        revision = int(conversation.get('finalization_revision') or 0) + 1
        transaction.set(
            job_ref,
            {
                'schema_version': 1,
                'uid': uid,
                'conversation_id': conversation_id,
                'finalization_revision': revision,
                'status': 'completed',
                'requires_byok': False,
                'processing_trigger': ProcessingTrigger.CAPTURE_END.value,
                'force_process': False,
                'fanout_key': f'conversation:{conversation_id}:finalization',
                'fanout_status': 'completed',
                'fanout_completed_at': now,
                'finalization_outcome': 'success',
                'terminal_outcome': 'success',
                'terminal_at': now,
                'dispatch_generation': 1,
                'attempt_count': 1,
                'task_retry_count': 0,
                'created_at': now,
                'updated_at': now,
                **receipt,
            },
        )

    conversation_updates = {
        'finalization_job_id': job_id,
        'meeting_treatment_eligible': bool(receipt['meeting_treatment_eligible']),
        'meeting_treatment_reason': receipt['meeting_treatment_reason'],
        'meeting_duration_s': receipt['meeting_duration_s'],
        'meeting_dedup_speech_s': receipt['meeting_dedup_speech_s'],
    }
    if not existing_job_id:
        conversation_updates['finalization_revision'] = int(conversation.get('finalization_revision') or 0) + 1
        conversation_updates['finalization_status'] = 'completed'
    transaction.update(conversation_ref, conversation_updates)
    return {'status': 'recorded', 'job_id': job_id, **receipt}


def record_meeting_receipt(
    uid: str,
    conversation_id: str,
    *,
    finalization_job_id: str | None,
    eligible: bool,
    reason: str,
    duration_s: float,
    dedup_speech_s: float,
    firestore_client: Any = None,
) -> dict[str, Any]:
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_record_meeting_receipt_txn)
    result = transactional(
        transaction,
        _conversation_ref(client, uid, conversation_id),
        client.collection(FINALIZATION_JOBS_COLLECTION),
        uid,
        conversation_id,
        finalization_job_id,
        eligible,
        reason,
        duration_s,
        dedup_speech_s,
        _now(),
    )
    if result['status'] == 'recorded':
        stop_quiet_check_for_conversation(uid, conversation_id, firestore_client=client)
    return result


def mark_meeting_receipt_intent_persisted(job_id: str, intent_id: str, *, firestore_client: Any = None) -> bool:
    client = _client(firestore_client)
    job_ref = _job_ref(client, job_id)
    transaction = client.transaction()

    @firestore.transactional
    def apply(write_transaction: Any) -> bool:
        snapshot = job_ref.get(transaction=write_transaction)
        if not getattr(snapshot, 'exists', False):
            return False
        job = snapshot.to_dict() or {}
        existing = job.get('meeting_receipt_intent_id')
        if isinstance(existing, str):
            return existing == intent_id
        now = _now()
        write_transaction.update(
            job_ref,
            {
                'meeting_receipt_intent_id': intent_id,
                'meeting_receipt_intent_persisted_at': now,
                'meeting_receipt_updated_at': now,
            },
        )
        return True

    return apply(transaction)


def mark_meeting_receipt_materialized(
    uid: str,
    conversation_id: str,
    intent_id: str,
    *,
    materialized_at: datetime,
    firestore_client: Any = None,
) -> bool:
    client = _client(firestore_client)
    conversation_ref = _conversation_ref(client, uid, conversation_id)
    transaction = client.transaction()

    @firestore.transactional
    def apply(write_transaction: Any) -> bool:
        conversation_snapshot = conversation_ref.get(transaction=write_transaction)
        if not getattr(conversation_snapshot, 'exists', False):
            return False
        job_id = (conversation_snapshot.to_dict() or {}).get('finalization_job_id')
        if not isinstance(job_id, str) or not job_id:
            return False
        job_ref = _job_ref(client, job_id)
        job_snapshot = job_ref.get(transaction=write_transaction)
        if not getattr(job_snapshot, 'exists', False):
            return False
        job = job_snapshot.to_dict() or {}
        if job.get('meeting_receipt_intent_id') != intent_id:
            return False
        if job.get('meeting_receipt_materialized_at') is None:
            write_transaction.update(
                job_ref,
                {
                    'meeting_receipt_materialized_at': materialized_at,
                    'meeting_receipt_updated_at': materialized_at,
                },
            )
        return True

    return apply(transaction)


def get_meeting_receipt_reconcile_candidates(
    *, limit: int = 100, now: datetime | None = None, firestore_client: Any = None
) -> list[dict[str, Any]]:
    """Return eligible receipts old enough to repair and still missing an intent id."""
    client = _client(firestore_client)
    cutoff = now or _now()
    query = MEETING_RECEIPTS_DUE_QUERY.build(
        client.collection(FINALIZATION_JOBS_COLLECTION),
        {
            'meeting_treatment_eligible': True,
            'meeting_receipt_intent_id': None,
            'meeting_receipt_reconcile_after_at': cutoff,
        },
        field_filter_factory=FieldFilter,
    )
    query = query.limit(max(1, min(limit, 100)))
    candidates: list[dict[str, Any]] = []
    for snapshot in query.stream():
        job = snapshot.to_dict() or {}
        candidates.append(job | {'job_id': snapshot.id})
    return candidates


def get_meeting_receipt_backfill_candidates(
    *,
    limit: int = 100,
    max_scan: int = 2000,
    resume_after_path: str | None = None,
    firestore_client: Any = None,
) -> dict[str, Any]:
    """Scan completed conversations fairly for legacy desktop meetings without receipts."""
    client = _client(firestore_client)
    page_size = max(1, min(limit, 100))
    collected: list[dict[str, Any]] = []
    scanned = 0
    last_path: str | None = None
    exhausted = False
    cursor_snapshot: Any = None
    if resume_after_path:
        fetched = client.document(resume_after_path).get()
        if getattr(fetched, 'exists', False):
            cursor_snapshot = fetched

    while len(collected) < limit and scanned < max_scan:
        query = client.collection_group(CONVERSATIONS_COLLECTION).where(
            filter=firestore.FieldFilter('status', '==', 'completed')
        )
        query = query.limit(page_size)
        if cursor_snapshot is not None:
            query = query.start_after(cursor_snapshot)
        page = list(query.stream())
        if not page:
            exhausted = True
            break
        for snapshot in page:
            scanned += 1
            if scanned > max_scan:
                break
            last_path = snapshot.reference.path
            uid = _uid_from_conversation_path(snapshot.reference.path)
            if uid is None:
                continue
            data = snapshot.to_dict() or {}
            external_data = data.get('external_data') or {}
            source = data.get('source')
            source = getattr(source, 'value', source)
            if (
                source != 'desktop'
                or not isinstance(external_data, Mapping)
                or external_data.get('conversation_role') != 'meeting'
                or data.get('meeting_treatment_reason')
            ):
                continue
            collected.append({'uid': uid, 'conversation_id': snapshot.id, 'conversation': data | {'id': snapshot.id}})
            if len(collected) >= limit:
                break
        if scanned > max_scan:
            break
        if len(page) < page_size:
            exhausted = True
            break
        cursor_snapshot = page[-1]

    return {
        'candidates': collected,
        'resume_after_path': None if exhausted else last_path,
        'exhausted': exhausted,
    }


def _claim_finalization_replay_txn(
    transaction: Any,
    job_ref: Any,
    stale_after: timedelta,
    now: datetime,
    projection_collection: Any | None = None,
    byok_only: bool = False,
) -> FinalizationIntent:
    snapshot = job_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return {
            'job_id': None,
            'status': 'missing',
            'dispatch_generation': None,
            'requires_byok': False,
            'fanout_key': None,
            'created': False,
        }
    job = snapshot.to_dict() or {}
    status = str(job.get('status') or '')
    if byok_only and not job.get('requires_byok'):
        return _intent_from_job(snapshot.id, job)
    if status == 'blocked_byok' or status in TERMINAL_JOB_STATUSES:
        if 'reconcile_after_at' in job:
            transaction.update(job_ref, {'reconcile_after_at': firestore.DELETE_FIELD, 'updated_at': now})
        return _intent_from_job(snapshot.id, job)
    if status == 'leased':
        lease_expires_at = job.get('lease_expires_at')
        if bool(job.get('requires_byok')) and not isinstance(lease_expires_at, datetime):
            return _intent_from_job(snapshot.id, job)
        if isinstance(lease_expires_at, datetime) and lease_expires_at > now:
            return _intent_from_job(snapshot.id, job)
    if status == 'queued':
        dispatch_requested_at = job.get('dispatch_requested_at')
        if job.get('requires_byok'):
            activity = [
                job.get(field) for field in ('updated_at', 'last_byok_resume_at', 'dispatch_requested_at', 'created_at')
            ]
            activity = [value for value in activity if isinstance(value, datetime)]
            if not activity:
                return _intent_from_job(snapshot.id, job)
            dispatch_requested_at = max(activity)
        if isinstance(dispatch_requested_at, datetime) and dispatch_requested_at > now - stale_after:
            return _intent_from_job(snapshot.id, job)
    if status not in ('queued', 'leased'):
        return _intent_from_job(snapshot.id, job)

    if job.get('requires_byok'):
        transaction.update(
            job_ref,
            {
                'status': 'blocked_byok',
                'byok_last_activity_at': _job_last_activity_at(job),
                'updated_at': now,
                'lease_epoch': int(job.get('lease_epoch') or 0) + 1,
                'lease_expires_at': firestore.DELETE_FIELD,
                'reconcile_after_at': firestore.DELETE_FIELD,
            },
        )
        _record_projection_delta(transaction, projection_collection, job, **{status: -1, 'blocked_byok': 1})
        job['status'] = 'blocked_byok'
        return _intent_from_job(snapshot.id, job)

    generation = int(job.get('dispatch_generation') or 1) + 1
    transaction.update(
        job_ref,
        {
            'status': 'queued',
            'dispatch_generation': generation,
            'dispatch_requested_at': now,
            'updated_at': now,
            'lease_expires_at': now,
            'reconcile_after_at': now + stale_after,
        },
    )
    if status == 'leased':
        _record_projection_delta(transaction, projection_collection, job, leased=-1, queued=1)
    job['status'] = 'queued'
    job['dispatch_generation'] = generation
    # Only the transaction that minted this generation should enqueue it.
    # A concurrent reconciler that observes its fresh queued row must not
    # report another dispatch of the same named Cloud Task.
    return _intent_from_job(snapshot.id, job, created=True)


def claim_finalization_replay(
    job_id: str, *, stale_after: timedelta, firestore_client: Any = None, byok_only: bool = False
) -> FinalizationIntent:
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_claim_finalization_replay_txn)
    return transactional(
        transaction,
        _job_ref(client, job_id),
        stale_after,
        _now(),
        client.collection(FINALIZATION_PROJECTION_COLLECTION),
        byok_only,
    )


def recover_stranded_byok_jobs(*, limit: int = 50, firestore_client: Any = None) -> dict[str, int]:
    """Rotate through at most 50 rows per active status using the existing age index.

    Persisted CAS cursors prevent a stable non-BYOK prefix from starving legacy
    rows. Candidate reads are advisory; each reclaim rereads ownership inside a
    transaction. Failed rows are revisited on the next rotation.
    """
    client = _client(firestore_client)
    collection = client.collection(FINALIZATION_JOBS_COLLECTION)
    page_size = max(1, min(limit, 50))
    result = {'scanned': 0, 'blocked': 0, 'errors': 0}
    for status in ('queued', 'leased'):
        state_ref = client.collection(STALE_PROCESSING_SWEEP_STATE_COLLECTION).document(f'byok_reclaim_{status}')
        state = state_ref.get().to_dict() or {}
        query = FINALIZATION_OLDEST_NONTERMINAL_QUERY.build(
            collection, {'status': status}, field_filter_factory=FieldFilter
        ).order_by('created_at')
        path = state.get('resume_after_path')
        if isinstance(path, str) and path.startswith(FINALIZATION_JOBS_COLLECTION + '/'):
            cursor = client.document(path).get()
            if cursor.exists and isinstance((cursor.to_dict() or {}).get('created_at'), datetime):
                query = query.start_after(cursor)
        snapshots = list(query.limit(page_size).stream())
        for snapshot in snapshots:
            result['scanned'] += 1
            if not (snapshot.to_dict() or {}).get('requires_byok'):
                continue
            try:
                intent = claim_finalization_replay(
                    snapshot.id,
                    stale_after=get_finalization_reconcile_stale_after(),
                    firestore_client=client,
                    byok_only=True,
                )
                if intent['status'] == 'blocked_byok':
                    result['blocked'] += 1
            except Exception:
                result['errors'] += 1
        next_path = snapshots[-1].reference.path if len(snapshots) == page_size else None
        firestore.transactional(_advance_stale_processing_sweep_cursor_txn)(
            client.transaction(), state_ref, int(state.get('generation', 0)), next_path, _now()
        )
    return result


def _advance_finalization_replay_cursor_txn(
    transaction: Any, ref: Any, generation: int, cursor: dict[str, Any] | None
) -> bool:
    state = ref.get(transaction=transaction).to_dict() or {}
    if int(state.get('generation', 0)) != generation:
        return False
    transaction.set(ref, {'generation': generation + 1, 'cursor': cursor, 'updated_at': _now()})
    return True


def get_finalization_replay_candidates(*, limit: int = 100, firestore_client: Any = None) -> list[dict[str, Any]]:
    """Rotate a bounded due page even when every selected worker fails to advance.

    Persist the original ordered values, not a document snapshot re-read after
    mutation. A repaired/deleted last row must not rewind or skip the next page.
    Freeze each sweep cutoff so recurring successors cannot keep the window
    full forever. CAS fences competing scans. A crash after reservation delays
    these rows until bounded wrap; it never removes the durable obligation.
    """
    client = _client(firestore_client)
    try:
        safe_limit = max(1, min(int(limit), 2000))
    except (ValueError, TypeError):
        safe_limit = 100
    state_ref = client.collection('conversation_recovery_state').document('finalization_replay')
    state = state_ref.get().to_dict() or {}
    cursor = state.get('cursor')
    cutoff = cursor.get('cutoff') if isinstance(cursor, dict) else None
    if not isinstance(cutoff, datetime):
        cutoff = _now()
    query = (
        client.collection(FINALIZATION_JOBS_COLLECTION)
        .where('reconcile_after_at', '<=', cutoff)
        .order_by('reconcile_after_at')
        .order_by('__name__')
    )
    # The SDK only adds implicit name ordering for snapshot cursors. With a
    # value dict it silently drops name unless that order is explicit.
    if (
        isinstance(cursor, dict)
        and isinstance(cursor.get('reconcile_after_at'), datetime)
        and isinstance(cursor.get('job_id'), str)
    ):
        query = query.start_after(
            {
                'reconcile_after_at': cursor['reconcile_after_at'],
                '__name__': client.collection(FINALIZATION_JOBS_COLLECTION).document(cursor['job_id']),
            }
        )
    snapshots = list(query.limit(safe_limit).stream())
    next_cursor = None
    if len(snapshots) == safe_limit:
        last = snapshots[-1]
        next_cursor = {
            'reconcile_after_at': (last.to_dict() or {})['reconcile_after_at'],
            'job_id': last.id,
            'cutoff': cutoff,
        }
    firestore.transactional(_advance_finalization_replay_cursor_txn)(
        client.transaction(), state_ref, int(state.get('generation', 0)), next_cursor
    )
    logging.getLogger(__name__).info(
        'event=finalization_replay_page project=%s database=%s selected=%s quiet=%s resumed=%s',
        getattr(client, 'project', 'injected'),
        getattr(client, '_database', '(default)'),
        len(snapshots),
        sum((snapshot.to_dict() or {}).get('kind') == 'listen_quiet_check' for snapshot in snapshots),
        bool(cursor),
    )
    return [(snapshot.to_dict() or {}) | {'job_id': snapshot.id} for snapshot in snapshots]


def get_finalization_replay_oldest_overdue_age_seconds(*, firestore_client: Any = None) -> float:
    """Measure the true head independently of the rotating replay window."""
    now = _now()
    query = (
        _client(firestore_client)
        .collection(FINALIZATION_JOBS_COLLECTION)
        .where('reconcile_after_at', '<=', now)
        .order_by('reconcile_after_at')
        .limit(1)
    )
    for snapshot in query.stream():
        return max(0.0, (now - (snapshot.to_dict() or {})['reconcile_after_at']).total_seconds())
    return 0.0


def defer_finalization_replay(candidate: dict[str, Any], *, firestore_client: Any = None) -> bool:
    """Back off only the exact overdue snapshot that failed to make progress."""
    client = _client(firestore_client)
    ref = client.collection(FINALIZATION_JOBS_COLLECTION).document(candidate['job_id'])

    @firestore.transactional
    def defer(transaction: Any) -> bool:
        current = ref.get(transaction=transaction).to_dict() or {}
        now = _now()
        due = current.get('reconcile_after_at')
        if not isinstance(due, datetime) or due > now:
            return False
        if any(
            current.get(key) != candidate.get(key) for key in ('status', 'dispatch_generation', 'reconcile_after_at')
        ):
            return False
        updates: dict[str, Any] = {'reconcile_after_at': now + timedelta(seconds=60), 'updated_at': now}
        if current.get('kind') != 'listen_quiet_check' and (
            current.get('status') in TERMINAL_JOB_STATUSES or current.get('status') == 'blocked_byok'
        ):
            updates['reconcile_after_at'] = firestore.DELETE_FIELD
        transaction.update(ref, updates)
        return True

    return defer(client.transaction())


def get_stale_processing_orphan_candidates(
    *,
    stale_after: timedelta,
    limit: int = 100,
    max_scan: int = 2000,
    resume_after_path: str | None = None,
    firestore_client: Any = None,
) -> dict[str, Any]:
    """Return a bounded window of actionable bare-`processing` conversations.

    Eligibility is bounded by the authoritative, server-owned admission fence
    ``processing_admitted_at`` — never caller-controlled ``created_at``. A bare
    ``processing`` row (no ``finalization_job_id``) that is not ``deferred`` is:

    * returned with ``legacy=False`` when its admission age exceeds
      ``stale_after`` (a genuine crash orphan ready for exactly one terminal), and
    * returned with ``legacy=True`` when it predates the admission stamp (a
      stranded legacy row the caller must migrate by stamping the fence, never
      terminalized on first sight).

    Fresh admissions under ``stale_after`` are filtered out and never returned.

    The cross-user sweep is a single-equality ``collection_group`` query on
    ``status == 'processing'``. A single-field equality query is served by
    Firestore's automatic single-field index, so no composite index is registered
    or deployed and the query is deliberately not collection-scoped. Because
    client-side exclusion (deferred / durable-job-owned / fresh / legacy) happens
    after the page cap, the sweep pages with a ``start_after`` cursor so a stable
    first page of excluded rows cannot starve a later eligible orphan.

    Eventual discovery is guaranteed by a **persisted, rotated sweep cursor**.
    Each invocation resumes from ``resume_after_path`` (the last-examined row) and
    examines at most ``max_scan`` rows; when the collection is exhausted the
    cursor wraps (``exhausted=True``), so a stable excluded prefix larger than any
    per-invocation bound cannot permanently hide a later orphan — repeated bounded
    sweeps cover the whole collection. The caller persists ``resume_after_path``
    (or ``None`` once ``exhausted``) between invocations.

    Returns ``{'candidates', 'resume_after_path', 'exhausted'}``.
    """
    client = _client(firestore_client)
    cutoff = _now() - stale_after
    try:
        safe_limit = max(1, min(int(limit), 500))
    except (ValueError, TypeError):
        safe_limit = 100
    try:
        safe_max_scan = max(1, min(int(max_scan), 10000))
    except (ValueError, TypeError):
        safe_max_scan = 2000
    page_size = max(1, min(safe_limit, 100))
    collected: list[dict[str, Any]] = []
    scanned = 0
    last_path: str | None = None
    exhausted = False

    cursor_snapshot: Any = None
    if resume_after_path:
        fetched = client.document(resume_after_path).get()
        if getattr(fetched, 'exists', False):
            cursor_snapshot = fetched  # resume the collection-group scan
        # A vanished cursor document wraps the sweep back to the top (safe re-scan).

    while len(collected) < safe_limit and scanned < safe_max_scan:
        query = client.collection_group(CONVERSATIONS_COLLECTION).where(
            filter=firestore.FieldFilter('status', '==', 'processing')
        )
        query = query.limit(page_size)
        if cursor_snapshot is not None:
            query = query.start_after(cursor_snapshot)
        page = list(query.stream())
        if not page:
            exhausted = True  # reached the tail of the collection from the cursor
            break
        for snapshot in page:
            scanned += 1
            if scanned > safe_max_scan:
                break
            last_path = snapshot.reference.path
            uid = _uid_from_conversation_path(snapshot.reference.path)
            if uid is None:
                continue
            data = snapshot.to_dict() or {}
            if data.get('deferred') or data.get('finalization_job_id'):
                continue
            admitted_at = _parse_timestamp(data.get('processing_admitted_at'))
            if admitted_at is not None:
                if admitted_at > cutoff:
                    continue  # fresh admission still under the conservative threshold
                collected.append(
                    {'uid': uid, 'conversation_id': snapshot.id, 'processing_admitted_at': admitted_at, 'legacy': False}
                )
            else:
                collected.append(
                    {'uid': uid, 'conversation_id': snapshot.id, 'processing_admitted_at': None, 'legacy': True}
                )
            if len(collected) >= safe_limit:
                break
        if scanned > safe_max_scan:
            break  # bounded work for this invocation; the cursor persists progress
        if len(page) < page_size:
            exhausted = True  # partial page => reached the tail
            break
        cursor_snapshot = page[-1]

    return {
        'candidates': collected,
        'resume_after_path': None if exhausted else last_path,
        'exhausted': exhausted,
    }


STALE_PROCESSING_SWEEP_STATE_COLLECTION = 'conversation_recovery_state'
STALE_PROCESSING_SWEEP_STATE_DOC = 'stale_processing_sweep'
MEETING_RECEIPT_SWEEP_STATE_DOC = 'meeting_receipt_backfill_sweep'
BYOK_ABANDONMENT_SWEEP_STATE_DOC = 'byok_abandonment_sweep'
IN_PROGRESS_CONTENT_SWEEP_STATE_DOC = 'in_progress_content_sweep'
IN_PROGRESS_QUIET_SWEEP_STATE_DOC = 'in_progress_quiet_sweep'
SELFHEAL_MAX_PENDING_VERIFICATIONS = 100


def scan_in_progress_conversations(
    *,
    page_size: int = 100,
    max_scan: int = 2000,
    resume_after_path: str | None = None,
    firestore_client: Any = None,
    content_due_before: datetime | None = None,
) -> dict[str, Any]:
    """Return a bounded window of ``status == 'in_progress'`` conversation rows.

    The legacy query shape is fixed: a single-equality ``collection_group`` on
    ``conversations.status == 'in_progress'``, limited per page, optionally
    resuming after the persisted cursor snapshot. Every recovery predicate is
    evaluated Python-side by the caller; no extra Firestore predicate may be
    added to that legacy shape. The always-on fast recovery caller explicitly
    selects the content-bearing, due-by-finished_at collection-group index.
    This avoids rotating through historical empty stubs before finding a
    recently expired recording. Lease and admission guards remain transactional.

    Returns ``{'rows', 'scanned', 'resume_after_path', 'exhausted'}`` where each
    row is ``{'uid', 'conversation_id', 'path', 'data'}``.
    """
    client = _client(firestore_client)
    page_size = max(1, min(page_size, 100))
    rows: list[dict[str, Any]] = []
    scanned = 0
    last_path: str | None = None
    exhausted = False

    cursor_snapshot: Any = None
    if resume_after_path:
        fetched = client.document(resume_after_path).get()
        if getattr(fetched, 'exists', False):
            cursor_snapshot = fetched

    while scanned < max_scan:
        query = (
            client.collection_group(CONVERSATIONS_COLLECTION)
            .where(filter=firestore.FieldFilter('status', '==', 'in_progress'))
            .limit(page_size)
        )
        if content_due_before is not None:
            query = (
                query.where(filter=firestore.FieldFilter('has_content', '==', True))
                .where(filter=firestore.FieldFilter('finished_at', '<=', content_due_before))
                .order_by('finished_at')
            )
        if cursor_snapshot is not None:
            query = query.start_after(cursor_snapshot)
        page = list(query.stream())
        if not page:
            exhausted = True
            break
        for snapshot in page:
            scanned += 1
            if scanned > max_scan:
                break
            last_path = snapshot.reference.path
            uid = _uid_from_conversation_path(snapshot.reference.path)
            if uid is None:
                continue
            rows.append(
                {
                    'uid': uid,
                    'conversation_id': snapshot.id,
                    'path': snapshot.reference.path,
                    'data': snapshot.to_dict() or {},
                }
            )
        if scanned > max_scan:
            break
        if len(page) < page_size:
            exhausted = True
            break
        cursor_snapshot = page[-1]

    return {
        'rows': rows,
        'scanned': scanned,
        'resume_after_path': None if exhausted else last_path,
        'exhausted': exhausted,
    }


def get_in_progress_content_sweep_cursor(*, quiet: bool = False, firestore_client: Any = None) -> dict[str, Any]:
    """Read the CAS cursor and bounded job identities with optional ``admitted_at`` deadlines."""
    client = _client(firestore_client)
    snapshot = (
        client.collection(STALE_PROCESSING_SWEEP_STATE_COLLECTION)
        .document(IN_PROGRESS_QUIET_SWEEP_STATE_DOC if quiet else IN_PROGRESS_CONTENT_SWEEP_STATE_DOC)
        .get()
    )
    if not getattr(snapshot, 'exists', False):
        return {'resume_after_path': None, 'generation': 0, 'pending_verifications': []}
    data = snapshot.to_dict() or {}
    path = data.get('resume_after_path')
    pending = data.get('pending_verifications')
    if not isinstance(pending, list):
        pending = []
    entries: list[dict[str, Any]] = []
    for entry in pending[:SELFHEAL_MAX_PENDING_VERIFICATIONS]:
        if not isinstance(entry, Mapping):
            continue
        uid = entry.get('uid')
        conversation_id = entry.get('conversation_id')
        job_id = entry.get('job_id')
        if isinstance(uid, str) and isinstance(conversation_id, str) and isinstance(job_id, str):
            clean_entry: dict[str, Any] = {'uid': uid, 'conversation_id': conversation_id, 'job_id': job_id}
            admitted_at = entry.get('admitted_at')
            if isinstance(admitted_at, datetime):
                clean_entry['admitted_at'] = admitted_at
            entries.append(clean_entry)
    return {
        'resume_after_path': path if isinstance(path, str) else None,
        'generation': int(data.get('generation', 0)),
        'pending_verifications': entries,
        'updated_at': data.get('updated_at'),
    }


def _advance_in_progress_content_sweep_cursor_txn(
    transaction: Any,
    doc_ref: Any,
    expected_generation: int,
    new_resume_after_path: str | None,
    pending_verifications: list[dict[str, Any]],
    now: datetime,
) -> bool:
    """CAS-update the self-heal sweep cursor and pending-verification list atomically.

    Same generation fence as ``_advance_stale_processing_sweep_cursor_txn``; a
    losing writer returns ``False`` and its pending list is not persisted, so
    the next tick re-admits nothing the winner already claimed (the admission
    transaction itself is the real fence — this list is verification state).
    """
    snapshot = doc_ref.get(transaction=transaction)
    current_generation = 0
    if getattr(snapshot, 'exists', False):
        current_generation = int((snapshot.to_dict() or {}).get('generation', 0))
    if current_generation != expected_generation:
        return False
    transaction.set(
        doc_ref,
        {
            'resume_after_path': new_resume_after_path,
            'generation': current_generation + 1,
            'updated_at': now,
            'pending_verifications': pending_verifications[:SELFHEAL_MAX_PENDING_VERIFICATIONS],
        },
    )
    return True


def advance_in_progress_content_sweep_cursor(
    expected_generation: int,
    new_resume_after_path: str | None,
    *,
    pending_verifications: list[dict[str, Any]] | None = None,
    quiet: bool = False,
    firestore_client: Any = None,
) -> bool:
    """Atomically advance the self-heal sweep cursor; ``False`` on a CAS loss."""
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_advance_in_progress_content_sweep_cursor_txn)
    return transactional(
        transaction,
        client.collection(STALE_PROCESSING_SWEEP_STATE_COLLECTION).document(
            IN_PROGRESS_QUIET_SWEEP_STATE_DOC if quiet else IN_PROGRESS_CONTENT_SWEEP_STATE_DOC
        ),
        expected_generation,
        new_resume_after_path,
        pending_verifications or [],
        _now(),
    )


def get_stale_processing_sweep_cursor(*, firestore_client: Any = None) -> dict[str, Any]:
    """Return the persisted sweep cursor and its CAS generation.

    Returns ``{'resume_after_path': str | None, 'generation': int}``. The
    generation is the compare-and-swap token a caller must hold to advance the
    cursor; ``0`` when the document has never been written. Multiple backend-listen
    pods share this single cursor, so the generation prevents a delayed scan from
    rewinding another pod's advance.
    """
    client = _client(firestore_client)
    state_ref = client.collection(STALE_PROCESSING_SWEEP_STATE_COLLECTION).document(STALE_PROCESSING_SWEEP_STATE_DOC)
    snapshot = state_ref.get()
    if not getattr(snapshot, 'exists', False):
        return {'resume_after_path': None, 'generation': 0}
    data = snapshot.to_dict() or {}
    path = data.get('resume_after_path')
    return {
        'resume_after_path': path if isinstance(path, str) else None,
        'generation': int(data.get('generation', 0)),
    }


def _advance_stale_processing_sweep_cursor_txn(
    transaction: Any, doc_ref: Any, expected_generation: int, new_resume_after_path: str | None, now: datetime
) -> bool:
    """CAS-update the sweep cursor inside a Firestore transaction.

    Returns ``True`` only when the persisted generation still equals
    ``expected_generation`` — proving no other pod advanced the cursor between
    this pod's read and write. On success the cursor advances and the generation
    bumps, so a delayed competing writer holding the old generation is fenced out
    (``False``) and cannot rewind progress.
    """
    snapshot = doc_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        current_generation = 0
    else:
        current_generation = int((snapshot.to_dict() or {}).get('generation', 0))
    if current_generation != expected_generation:
        return False
    transaction.set(
        doc_ref,
        {'resume_after_path': new_resume_after_path, 'generation': current_generation + 1, 'updated_at': now},
    )
    return True


def advance_stale_processing_sweep_cursor(
    expected_generation: int, new_resume_after_path: str | None, *, firestore_client: Any = None
) -> bool:
    """Atomically advance the sweep cursor; ``None`` rotates the next sweep to the top.

    Returns ``False`` when another pod already advanced the cursor (the CAS
    generation changed). The caller's sweep work is still valid — the exact-
    generation fence in ``complete_orphan_conversation`` prevents double-terminalization
    — but the cursor does not advance from this pod's perspective, so the next sweep
    safely re-scans the same window.
    """
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_advance_stale_processing_sweep_cursor_txn)
    return transactional(
        transaction,
        client.collection(STALE_PROCESSING_SWEEP_STATE_COLLECTION).document(STALE_PROCESSING_SWEEP_STATE_DOC),
        expected_generation,
        new_resume_after_path,
        _now(),
    )


def get_meeting_receipt_backfill_cursor(*, firestore_client: Any = None) -> dict[str, Any]:
    client = _client(firestore_client)
    snapshot = (
        client.collection(STALE_PROCESSING_SWEEP_STATE_COLLECTION).document(MEETING_RECEIPT_SWEEP_STATE_DOC).get()
    )
    if not getattr(snapshot, 'exists', False):
        return {'resume_after_path': None, 'generation': 0}
    data = snapshot.to_dict() or {}
    path = data.get('resume_after_path')
    return {
        'resume_after_path': path if isinstance(path, str) else None,
        'generation': int(data.get('generation', 0)),
    }


def advance_meeting_receipt_backfill_cursor(
    expected_generation: int, new_resume_after_path: str | None, *, firestore_client: Any = None
) -> bool:
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_advance_stale_processing_sweep_cursor_txn)
    return transactional(
        transaction,
        client.collection(STALE_PROCESSING_SWEEP_STATE_COLLECTION).document(MEETING_RECEIPT_SWEEP_STATE_DOC),
        expected_generation,
        new_resume_after_path,
        _now(),
    )


def _stamp_processing_admission_if_absent_txn(transaction: Any, conversation_ref: Any, now: datetime) -> bool:
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
    if isinstance(data.get('processing_admitted_at'), datetime):
        return False
    transaction.update(conversation_ref, {'processing_admitted_at': now})
    return True


def stamp_processing_admission_if_absent(uid: str, conversation_id: str, *, firestore_client: Any = None) -> bool:
    """Stamp the authoritative admission fence on a legacy processing conversation."""
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_stamp_processing_admission_if_absent_txn)
    return transactional(transaction, _conversation_ref(client, uid, conversation_id), _now())


def _complete_unstampable_orphan_conversation_txn(
    transaction: Any, conversation_ref: Any, stale_before: datetime
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
    if data.get('discarded') or data.get('deferred') or data.get('finalization_job_id'):
        return False
    if _parse_timestamp(data.get('processing_admitted_at')) is not None:
        return False  # no longer a legacy row: the admission-fenced path owns it
    last_written = _parse_timestamp(getattr(snapshot, 'update_time', None))
    if last_written is None or last_written > stale_before:
        return False
    transaction.update(conversation_ref, {'status': 'completed'})
    return True


def complete_unstampable_orphan_conversation(
    uid: str, conversation_id: str, *, stale_after: timedelta, firestore_client: Any = None
) -> bool:
    """Terminalize a legacy orphan that is too large to accept the admission fence."""
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_complete_unstampable_orphan_conversation_txn)
    completed = transactional(transaction, _conversation_ref(client, uid, conversation_id), _now() - stale_after)
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
) -> bool:
    """Terminalize exactly the scanned orphan generation, fencing every live owner.

    Verified immediately before the write, inside the transaction:
    * still ``processing`` (not already completed/discarded/merging),
    * not ``deferred`` (a desktop lazy row that intentionally stays on processing),
    * no ``finalization_job_id`` (a finalizer attached durable ownership after
      discovery), and
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
    if data.get('discarded') or data.get('deferred') or data.get('finalization_job_id'):
        return False
    admitted_at = _parse_timestamp(data.get('processing_admitted_at'))
    expected_admitted = _parse_timestamp(expected_admitted_at)
    if admitted_at is None or admitted_at != expected_admitted:
        return False
    uid = uid or _uid_from_conversation_path(str(getattr(conversation_ref, 'path', '') or ''))
    terminal: dict[str, Any] = {'status': 'completed'}
    if uid:
        terminal = kept_row_terminal_update(uid, data, conversation_ref, terminal, time_zone_for_uid)
    transaction.update(conversation_ref, terminal)
    return True


def complete_orphan_conversation(
    uid: str, conversation_id: str, *, expected_admitted_at: datetime | None, firestore_client: Any = None
) -> bool:
    """Close one crash orphan through the generation/ownership fence."""
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_complete_orphan_conversation_txn)
    completed = transactional(
        transaction,
        _conversation_ref(client, uid, conversation_id),
        expected_admitted_at,
        _now(),
        uid,
        lambda zone_uid: user_time_zone(client, zone_uid),
    )
    if completed:
        stop_quiet_check_for_conversation(uid, conversation_id, firestore_client=client)
    return completed


def _renew_processing_lease_txn(transaction: Any, conversation_ref: Any, now: datetime) -> bool:
    """Refresh the admission lease on a still-processing row owned by a live processor."""
    snapshot = conversation_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return False
    data = snapshot.to_dict() or {}
    if data.get('status') != 'processing' or data.get('discarded'):
        return False
    transaction.update(conversation_ref, {'processing_admitted_at': now})
    return True


def renew_processing_lease(uid: str, conversation_id: str, *, firestore_client: Any = None) -> bool:
    """Renew the server-owned admission lease so recovery cannot mistake a live processor for a crash."""
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_renew_processing_lease_txn)
    return transactional(transaction, _conversation_ref(client, uid, conversation_id), _now())


def _reacquire_deferred_processing_txn(transaction: Any, conversation_ref: Any, now: datetime) -> bool:
    """Atomically claim a deferred row and renew its admission lease.

    ``deferred=True`` is the compare-and-swap ownership token: concurrent
    first opens may both observe it before this transaction, but only one can
    clear it and launch enrichment. A completed deferred row represents an
    earlier enrichment failure and is reopened for an explicit retry.
    """
    snapshot = conversation_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return False
    data = snapshot.to_dict() or {}
    if (
        data.get('status') not in {'processing', 'completed'}
        or data.get('discarded')
        or data.get('deferred') is not True
    ):
        return False
    transaction.update(
        conversation_ref,
        {'status': 'processing', 'deferred': False, 'processing_admitted_at': now},
    )
    return True


def reacquire_deferred_processing(uid: str, conversation_id: str, *, firestore_client: Any = None) -> bool:
    """Atomically claim deferred ownership and renew the lease in one transaction."""
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_reacquire_deferred_processing_txn)
    return transactional(transaction, _conversation_ref(client, uid, conversation_id), _now())


def _recover_deferred_processing_failure_txn(transaction: Any, conversation_ref: Any) -> bool:
    """Atomically publish a retryable terminal after deferred enrichment fails."""
    snapshot = conversation_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return False
    data = snapshot.to_dict() or {}
    if (
        data.get('status') not in {'processing', 'completed'}
        or data.get('discarded')
        or data.get('deferred') is not False
    ):
        return False
    transaction.update(conversation_ref, {'status': 'completed', 'deferred': True})
    return True


def recover_deferred_processing_failure(uid: str, conversation_id: str, *, firestore_client: Any = None) -> bool:
    """Atomically re-arm deferred enrichment without exposing a stuck processing row."""
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_recover_deferred_processing_failure_txn)
    completed = transactional(transaction, _conversation_ref(client, uid, conversation_id))
    if completed:
        stop_quiet_check_for_conversation(uid, conversation_id, firestore_client=client)
    return completed


def _job_last_activity_at(job: Mapping[str, Any]) -> datetime | None:
    """Return the most recent server-owned activity instant on a job."""
    for field in ('byok_last_activity_at', 'updated_at', 'created_at'):
        parsed = _parse_timestamp(job.get(field))
        if parsed is not None:
            return parsed
    return None


def get_abandoned_byok_job_candidates(
    *,
    abandoned_after: timedelta,
    limit: int = 100,
    max_scan: int = 2000,
    resume_after_path: str | None = None,
    firestore_client: Any = None,
) -> dict[str, Any]:
    """Return a bounded window of BYOK jobs that no consumer can ever claim again.

    The sweep never executes finalization or reads credentials. Its bounded
    single-field query selects all BYOK rows, including blocked_byok; eligibility
    is checked after pagination and again in the terminal transaction:

    * ``status`` in ``queued`` / ``leased`` / ``blocked_byok``.
    * no live lease, if ``leased``.
    * last live activity older than ``abandoned_after``. Prompt reclaim preserves
      that instant in ``byok_last_activity_at`` before updating bookkeeping;
      reconnect clears it and refreshes activity. Unknown age fails closed.

    The cross-collection sweep is a single-equality query on
    ``requires_byok == True``, served by Firestore's automatic single-field index
    (no composite index is registered or deployed). Because exclusion happens
    after the page cap, the sweep pages with a ``start_after`` cursor and stops
    after ``max_scan`` rows; the caller persists ``resume_after_path`` (or
    ``None`` once ``exhausted``) so repeated bounded sweeps cover the whole
    collection and a stable terminal prefix cannot starve a later stranded row.

    Returns ``{'candidates', 'resume_after_path', 'exhausted'}``.
    """
    client = _client(firestore_client)
    now = _now()
    cutoff = now - abandoned_after
    try:
        safe_limit = max(1, min(int(limit), 500))
    except (ValueError, TypeError):
        safe_limit = 100
    try:
        safe_max_scan = max(1, min(int(max_scan), 10000))
    except (ValueError, TypeError):
        safe_max_scan = 2000
    page_size = max(1, min(safe_limit, 100))
    collection = client.collection(FINALIZATION_JOBS_COLLECTION)
    collected: list[dict[str, Any]] = []
    scanned = 0
    last_path: str | None = None
    exhausted = False

    cursor_snapshot: Any = None
    if resume_after_path:
        fetched = client.document(resume_after_path).get()
        if getattr(fetched, 'exists', False):
            cursor_snapshot = fetched
        # A vanished cursor document wraps the sweep back to the top (safe re-scan).

    while len(collected) < safe_limit and scanned < safe_max_scan:
        query = collection.where(filter=firestore.FieldFilter('requires_byok', '==', True)).limit(page_size)
        if cursor_snapshot is not None:
            query = query.start_after(cursor_snapshot)
        page = list(query.stream())
        if not page:
            exhausted = True  # reached the tail of the collection from the cursor
            break
        for snapshot in page:
            scanned += 1
            if scanned > safe_max_scan:
                break
            reference = getattr(snapshot, 'reference', None)
            last_path = getattr(reference, 'path', None) or f'{FINALIZATION_JOBS_COLLECTION}/{snapshot.id}'
            job = snapshot.to_dict() or {}
            status = str(job.get('status') or '')
            if status not in ('queued', 'leased', 'blocked_byok'):
                continue
            if status == 'leased':
                lease_expires_at = _parse_timestamp(job.get('lease_expires_at'))
                if lease_expires_at is not None and lease_expires_at > now:
                    continue  # a live worker still owns this lease
            last_activity = _job_last_activity_at(job)
            if last_activity is None or last_activity > cutoff:
                continue  # unknown age, or still inside the reconnect window
            collected.append(job | {'job_id': snapshot.id, 'last_activity_at': last_activity})
            if len(collected) >= safe_limit:
                break
        if scanned > safe_max_scan:
            break  # bounded work for this invocation; the cursor persists progress
        if len(page) < page_size:
            exhausted = True  # partial page => reached the tail
            break
        cursor_snapshot = page[-1]

    return {
        'candidates': collected,
        'resume_after_path': None if exhausted else last_path,
        'exhausted': exhausted,
    }


def _byok_abandonment(status: str, conversation_outcome: str = 'none') -> ByokAbandonment:
    return {'status': status, 'conversation_outcome': conversation_outcome}


def _abandon_byok_finalization_job_txn(
    transaction: Any,
    job_ref: Any,
    expected_status: str,
    expected_dispatch_generation: int,
    expected_lease_epoch: int,
    cutoff: datetime,
    now: datetime,
    conversation_ref_for_job: Callable[[str, str], Any] | None = None,
    projection_collection: Any | None = None,
    time_zone_for_uid: Callable[[str], str | None] | None = None,
) -> ByokAbandonment:
    """Terminalize exactly the scanned unownable BYOK generation, fencing every live owner.

    Verified inside the transaction, immediately before the write: the job still
    requires BYOK, is still queued, leased, or blocked_byok, still carries
    the scanned status / dispatch generation / lease epoch (so a live session
    that resumed or claimed it in the meantime wins), holds no unexpired lease,
    and is still older than the abandonment cutoff. Any divergence is an expected
    CAS fencing, never a terminalization of live work.

    The terminal is honest: ``dead_letter`` with ``last_failure_code``
    ``byok_session_abandoned``, distinct from ``final_attempt_failed``. No
    finalization is attempted and no fanout is delivered.

    The bound conversation is read before the first write, so its terminal (when
    it is still ``processing``) commits atomically with the job's. It is moved to
    ``completed`` rather than ``failed``/``discarded``: exactly the choice
    ``complete_orphan_conversation`` makes, so the user's recording stays
    retrievable and reprocessable with their own keys instead of being hidden.
    """
    snapshot = job_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return _byok_abandonment('missing')
    job = snapshot.to_dict() or {}
    status = str(job.get('status') or '')
    if not bool(job.get('requires_byok')):
        return _byok_abandonment('fenced')
    if status not in ('queued', 'leased', 'blocked_byok') or status != expected_status:
        return _byok_abandonment('fenced')
    if int(job.get('dispatch_generation') or 1) != expected_dispatch_generation:
        return _byok_abandonment('fenced')
    if int(job.get('lease_epoch') or 0) != expected_lease_epoch:
        return _byok_abandonment('fenced')
    if status == 'leased':
        lease_expires_at = _parse_timestamp(job.get('lease_expires_at'))
        if lease_expires_at is not None and lease_expires_at > now:
            return _byok_abandonment('fenced')
    last_activity = _job_last_activity_at(job)
    if last_activity is None or last_activity > cutoff:
        return _byok_abandonment('fenced')

    uid = job.get('uid')
    conversation_id = job.get('conversation_id')
    conversation_ref = None
    conversation: Any = None
    if (
        conversation_ref_for_job is not None
        and isinstance(uid, str)
        and uid
        and isinstance(conversation_id, str)
        and conversation_id
    ):
        # Read the bound conversation before the first transaction write: the
        # customer must never be left on `processing` by a crash between two
        # independent writes.
        conversation_ref = conversation_ref_for_job(uid, conversation_id)
        conversation_snapshot = conversation_ref.get(transaction=transaction)
        conversation = conversation_snapshot.to_dict() if getattr(conversation_snapshot, 'exists', False) else None

    closes_conversation = (
        conversation_ref is not None
        and isinstance(uid, str)
        and isinstance(conversation, Mapping)
        and conversation.get('finalization_job_id') == job_ref.id
        and conversation.get('finalization_revision') == job.get('finalization_revision')
        and conversation.get('status') == 'processing'
        and not conversation.get('discarded')
        and not conversation.get('deferred')
    )
    # Pure decode of the snapshot already held; no transactional read after a write.
    terminal: dict[str, Any] = {'status': 'completed', 'finalization_status': 'dead_letter'}
    if closes_conversation and isinstance(uid, str) and isinstance(conversation, Mapping):
        terminal = kept_row_terminal_update(uid, conversation, conversation_ref, terminal, time_zone_for_uid)

    transaction.update(
        job_ref,
        {
            'status': 'dead_letter',
            'updated_at': now,
            'terminal_at': now,
            'terminal_outcome': 'failure',
            'finalization_outcome': BYOK_ABANDONED_FAILURE_CODE,
            'lease_expires_at': now,
            'reconcile_after_at': firestore.DELETE_FIELD,
            # Nothing was ever delivered to an external integration.
            'fanout_status': 'fenced',
            'fanout_fenced_at': now,
            'last_failure_code': BYOK_ABANDONED_FAILURE_CODE,
        },
    )
    _record_projection_delta(
        transaction,
        projection_collection,
        job,
        queued=-1 if status == 'queued' else 0,
        leased=-1 if status == 'leased' else 0,
        blocked_byok=-1 if status == 'blocked_byok' else 0,
        dead_letter=1,
        failure=1,
    )

    if conversation_ref is None or not isinstance(conversation, Mapping):
        return _byok_abandonment('abandoned', 'missing')
    if conversation.get('finalization_job_id') != job_ref.id or conversation.get('finalization_revision') != job.get(
        'finalization_revision'
    ):
        return _byok_abandonment('abandoned', 'unbound')
    if conversation.get('status') != 'processing' or conversation.get('discarded'):
        # The inline pusher lane already finalized this conversation; the job row
        # was orphaned bookkeeping, so only the job needed a terminal.
        return _byok_abandonment('abandoned', 'already_terminal')
    if conversation.get('deferred'):
        # A desktop lazy row intentionally stays on `processing` and is owned by
        # its own lane, exactly as the bare-`processing` sweep treats it.
        return _byok_abandonment('abandoned', 'deferred')
    transaction.update(conversation_ref, terminal)
    return _byok_abandonment('abandoned', 'closed')


def abandon_byok_finalization_job(
    job_id: str,
    *,
    expected_status: str,
    expected_dispatch_generation: int,
    expected_lease_epoch: int,
    abandoned_after: timedelta,
    firestore_client: Any = None,
) -> ByokAbandonment:
    """Close one unownable BYOK job through its generation/ownership fence."""
    client = _client(firestore_client)
    now = _now()
    transaction = client.transaction()
    transactional = firestore.transactional(_abandon_byok_finalization_job_txn)
    result = transactional(
        transaction,
        _job_ref(client, job_id),
        expected_status,
        expected_dispatch_generation,
        expected_lease_epoch,
        now - abandoned_after,
        now,
        lambda uid, conversation_id: _conversation_ref(client, uid, conversation_id),
        client.collection(FINALIZATION_PROJECTION_COLLECTION),
        lambda uid: user_time_zone(client, uid),
    )
    if result['status'] == 'abandoned':
        stop_quiet_checks_for_job(job_id, firestore_client=client)
    return result


def get_byok_abandonment_sweep_cursor(*, firestore_client: Any = None) -> dict[str, Any]:
    """Return the persisted BYOK sweep cursor and its CAS generation."""
    client = _client(firestore_client)
    state_ref = client.collection(STALE_PROCESSING_SWEEP_STATE_COLLECTION).document(BYOK_ABANDONMENT_SWEEP_STATE_DOC)
    snapshot = state_ref.get()
    if not getattr(snapshot, 'exists', False):
        return {'resume_after_path': None, 'generation': 0}
    data = snapshot.to_dict() or {}
    path = data.get('resume_after_path')
    return {
        'resume_after_path': path if isinstance(path, str) else None,
        'generation': int(data.get('generation', 0)),
    }


def advance_byok_abandonment_sweep_cursor(
    expected_generation: int, new_resume_after_path: str | None, *, firestore_client: Any = None
) -> bool:
    """Atomically advance the BYOK sweep cursor; ``None`` rotates the next sweep to the top."""
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_advance_stale_processing_sweep_cursor_txn)
    return transactional(
        transaction,
        client.collection(STALE_PROCESSING_SWEEP_STATE_COLLECTION).document(BYOK_ABANDONMENT_SWEEP_STATE_DOC),
        expected_generation,
        new_resume_after_path,
        _now(),
    )


def get_finalization_job_summary(*, firestore_client: Any = None) -> dict[str, float | int]:
    """Read one generation's fixed shard fan-in plus the oldest unfinished job.

    This deliberately never aggregates ``conversation_finalization_jobs``. A
    backend-listen replica performs exactly ``FINALIZATION_PROJECTION_SHARD_COUNT``
    projection-document reads, regardless of terminal history size. Pre-release
    jobs carry no generation and remain absent from this new denominator; their
    terminal field is still preserved on the authoritative job document.
    """
    client = _client(firestore_client)
    now = _now()
    jobs_collection = client.collection(FINALIZATION_JOBS_COLLECTION)
    projection_collection = client.collection(FINALIZATION_PROJECTION_COLLECTION)
    totals = {
        name: 0
        for name in (
            'accepted',
            'queued',
            'leased',
            'blocked_byok',
            'completed',
            'dead_letter',
            'success',
            'failure',
            'stale',
        )
    }
    for shard in range(FINALIZATION_PROJECTION_SHARD_COUNT):
        snapshot = projection_collection.document(_projection_shard_id(FINALIZATION_PROJECTION_GENERATION, shard)).get()
        if not getattr(snapshot, 'exists', False):
            continue
        data = snapshot.to_dict() or {}
        # A malformed or stale document cannot contaminate this generation's
        # denominator. The writer is the sole producer of matching documents.
        if data.get('generation') != FINALIZATION_PROJECTION_GENERATION or data.get('shard') != shard:
            continue
        for name in totals:
            value = data.get(name, 0)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                try:
                    f_val = float(value)
                    if not math.isnan(f_val) and not math.isinf(f_val):
                        totals[name] += int(f_val)
                except (ValueError, TypeError, OverflowError):
                    pass

    # One indexed oldest-row read per status, independent of terminal history.
    oldest_age_seconds = 0.0
    oldest_blocked_byok_age_seconds = 0.0
    for status in sorted(NONTERMINAL_JOB_STATUSES):
        oldest_query = (
            FINALIZATION_OLDEST_NONTERMINAL_QUERY.build(
                jobs_collection, {'status': status}, field_filter_factory=FieldFilter
            )
            .order_by('created_at')
            .limit(1)
        )
        for snapshot in oldest_query.stream():
            created_at = _parse_timestamp((snapshot.to_dict() or {}).get('created_at'))
            if created_at is not None:
                age = max(0.0, (now - created_at).total_seconds())
                if status == 'blocked_byok':
                    oldest_blocked_byok_age_seconds = max(oldest_blocked_byok_age_seconds, age)
                else:
                    oldest_age_seconds = max(oldest_age_seconds, age)
    return {
        'accepted': totals['accepted'],
        'success': totals['success'],
        'failure': totals['failure'],
        'stale': totals['stale'],
        'nonterminal': totals['queued'] + totals['leased'],
        'queued': totals['queued'],
        'leased': totals['leased'],
        'blocked_byok': totals['blocked_byok'],
        'completed': totals['completed'],
        'dead_letter': totals['dead_letter'],
        # Every admitted generation terminal transition writes an outcome.
        # Historical terminals are intentionally out of this bounded generation.
        'terminal_unknown': 0,
        'oldest_nonterminal_age_seconds': oldest_age_seconds,
        'oldest_blocked_byok_age_seconds': oldest_blocked_byok_age_seconds,
    }

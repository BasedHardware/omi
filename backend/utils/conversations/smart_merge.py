"""Fold a finished pendant conversation into the preceding one when Jev says same occasion.

Live capture splits on two minutes of silence, so one evening can become seven
rows. The durable finalizer calls ``smart_merge_step`` after it owns the
fanout claim and before any derived effect of the new conversation (N) runs.
Modes (``CONVERSATION_SMART_MERGE_MODE``; unset or blank means ``merge``, an
unrecognized value means ``off``):

- ``off``: no reads, no model call, no writes.
- ``shadow``: pick the candidate predecessor (P), ask Jev, store the decision
  record on N and emit metrics; never merge.
- ``merge``: as shadow, and at ``p_same >= MERGE_THRESHOLD`` absorb N into P:
  P keeps its id and gains N's transcript; N becomes a redirect tombstone
  (``database/smart_merge.py``); N's derived effects never run; P is refreshed
  once per absorb (``ProcessingTrigger.SMART_MERGE``).

Fail-open: before the absorb commits, any error, timeout or missing answer
keeps N separate and its finalization continues unchanged. After the absorb
commits, N is a donor: cleanup and refresh failures raise
``SmartMergeIncomplete`` so the finalization job retries, and the donor branch
resumes them on every later attempt, regardless of mode, and never runs N's
own derived effects. The finalizer runs that resume before its fanout claim,
which fences the discarded donor; a failed refresh releases its own lease.

Races are settled by the survivor revision (``smart_merge.revision`` and
``refreshed_revision``): an absorb needs no refresh owed, so a refresh never
persists a transcript older than the latest absorb.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo
from uuid import uuid4

from config.conversation_smart_merge import (
    JEV_MAX_ATTEMPTS,
    JEV_TIMEOUT_SECONDS,
    MERGE_THRESHOLD,
    PRECEDING_QUERY_LIMIT,
    QUESTION_VERSION,
    REFRESH_LEASE_SECONDS,
    SmartMergeMode,
    smart_merge_mode,
    smart_merge_uid_allowed,
)
from config.jev_decisions import JEV_MODEL
from database import conversations as conversations_db
from database import notifications as notification_db
from database import smart_merge as smart_merge_db
from database.firestore_read_metrics import FirestoreReadSite
from database.legal_holds import DestructiveOperationInProgress, LegalHoldActive, LegalHoldAuthorityUnavailable
from database.sync_bridges import mark_sync_bridge_cleaned
from utils.cloud_tasks import is_audio_merge_dispatch_enabled
from utils.conversations.factory import deserialize_conversation
from utils.conversations.merge_conversations import copy_sync_bridge_audio, retract_sync_bridge_source
from utils.conversations.process_conversation import process_conversation, save_structured_vector
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.smart_merge_policy import (
    DECISION_FIELD,
    PairCheck,
    SkipReason,
    absorb_payloads,
    check_pair,
    fragment_of,
    fragment_segments,
    is_donor,
    ledger_fragments,
    new_conversation_skip,
    partition,
    predecessor_status_skip,
    refresh_owed,
    revision,
    smart_merge_state,
    stretch_before,
)
from utils.conversations.smart_merge_state import QUESTION_NAME, QUESTIONS, build_state, state_sha256
from utils.executors import postprocess_executor, run_blocking
from utils.llm.jev_client import ask_jev
from utils.metrics import record_conversation_smart_merge, record_conversation_smart_merge_refresh
from utils.observability.fallback import record_fallback
from utils.other.storage import compute_audio_files_fingerprint, enqueue_conversation_artifact_build

logger = logging.getLogger(__name__)

JEV_LANE = 'conversation_smart_merge'
RECORD_VERSION = 1

# Decision values stored on N and used as metric reasons.
MERGED, KEPT = 'merged', 'kept'
SHADOW_WOULD_MERGE, SHADOW_KEEP = 'shadow_would_merge', 'shadow_keep'


class SmartMergeIncomplete(RuntimeError):
    """An absorb committed but its cleanup or survivor refresh did not finish; retry the job."""


# --------------------------------------------------------------------------- entry


async def smart_merge_step(
    uid: str,
    conversation_id: str,
    initial_row: Mapping[str, Any],
    *,
    trigger: ProcessingTrigger,
    owner: str,
) -> bool:
    """Returns True when N is (now) a donor: the caller must skip N's own derived effects.

    ``initial_row`` is the finalizer's pre-processing read, used only for the
    free donor check, so ``off`` stays I/O-free.
    """
    if is_donor(initial_row):
        await run_blocking(postprocess_executor, finish_absorb, uid, conversation_id, owner=owner, resumed=True)
        return True
    mode = smart_merge_mode()
    if mode is SmartMergeMode.OFF:
        return False
    return await run_blocking(
        postprocess_executor, decide_and_apply, uid, conversation_id, mode=mode, trigger=trigger, owner=owner
    )


def decide_and_apply(
    uid: str, conversation_id: str, *, mode: SmartMergeMode, trigger: ProcessingTrigger, owner: str
) -> bool:
    try:
        plan = _decide(uid, conversation_id, mode=mode, trigger=trigger, owner=owner)
    except Exception as error:
        # Never let the optional step change the finalization outcome.
        logger.warning(
            'event=smart_merge outcome=error stage=decide exception_type=%s uid=%s conversation=%s',
            type(error).__name__,
            uid,
            conversation_id,
        )
        record_conversation_smart_merge(mode=mode.value, decision='skip', reason='error')
        return False
    if plan is None:
        return False
    return _absorb(uid, conversation_id, plan, mode=mode, owner=owner)


# --------------------------------------------------------------------------- decision


class _MergePlan:
    def __init__(self, survivor_id: str, expected_revision: int, record: dict[str, Any], gap: Optional[float]):
        self.survivor_id = survivor_id
        self.expected_revision = expected_revision
        self.record = record
        self.gap = gap


def _segments(row: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    value = row.get('transcript_segments')
    return [s for s in value if isinstance(s, Mapping)] if isinstance(value, list) else []


def _skip(mode: SmartMergeMode, reason: str, uid: str, conversation_id: str, gap: Optional[float] = None) -> None:
    record_conversation_smart_merge(mode=mode.value, decision='skip', reason=reason, gap_seconds=gap)
    logger.info('event=smart_merge decision=skip reason=%s uid=%s conversation=%s', reason, uid, conversation_id)


def _user_tz(uid: str) -> ZoneInfo:
    name = notification_db.get_user_time_zone(uid)
    try:
        return ZoneInfo(name) if name else ZoneInfo('UTC')
    except Exception:
        return ZoneInfo('UTC')


def _decision_record(
    *,
    mode: SmartMergeMode,
    decision: str,
    reason: str,
    p_same: Optional[float],
    candidate_id: str,
    check: PairCheck,
    stretch_count: int,
    state_hash: Optional[str],
) -> dict[str, Any]:
    """Server-only audit record: numbers and ids, never text."""
    return {
        'version': RECORD_VERSION,
        'mode': mode.value,
        'decision': decision,
        'reason': reason,
        'decided_by': 'jev',
        'p_same': None if p_same is None else round(p_same, 4),
        'threshold': MERGE_THRESHOLD,
        'model': JEV_MODEL,
        'question_version': QUESTION_VERSION,
        'candidate_id': candidate_id,
        'gap_seconds': None if check.gap_seconds is None else round(check.gap_seconds, 1),
        'speech_gap_seconds': None if check.speech_gap_seconds is None else round(check.speech_gap_seconds, 1),
        'stretch_count': stretch_count,
        'state_sha256': state_hash,
        'decided_at': datetime.now(timezone.utc),
    }


def _ask(state: str) -> Optional[float]:
    answers = ask_jev(
        state, QUESTIONS, lane=JEV_LANE, timeout_seconds=JEV_TIMEOUT_SECONDS, max_attempts=JEV_MAX_ATTEMPTS
    )
    return None if answers is None else answers.noul(QUESTION_NAME)


def _decide(
    uid: str, conversation_id: str, *, mode: SmartMergeMode, trigger: ProcessingTrigger, owner: str
) -> Optional[_MergePlan]:
    """Ask (or reuse) the decision; a plan only in merge mode at or above the threshold."""
    if not smart_merge_uid_allowed(uid):
        _skip(mode, SkipReason.UID_NOT_ALLOWED, uid, conversation_id)
        return None
    new_row = conversations_db.get_conversation(uid, conversation_id, read_site=FirestoreReadSite.SMART_MERGE)
    if not new_row:
        return None
    new_row = dict(new_row, id=conversation_id)
    new_segments = _segments(new_row)
    reason = new_conversation_skip(new_row, new_segments, capture_end=trigger is ProcessingTrigger.CAPTURE_END)
    if reason is None and not isinstance(new_row.get('created_at'), datetime):
        reason = SkipReason.CONVERSATION_NOT_ELIGIBLE
    if reason is not None:
        _skip(mode, reason, uid, conversation_id)
        return None

    rows = smart_merge_db.find_preceding_conversations(
        uid, source=new_row['source'], created_before=new_row['created_at'], limit=PRECEDING_QUERY_LIMIT
    )
    survivor_meta = next((row for row in rows if partition(row) == partition(new_row)), None)
    if survivor_meta is None:
        _skip(mode, SkipReason.NO_PREDECESSOR, uid, conversation_id)
        return None
    reason = predecessor_status_skip(survivor_meta)
    if reason is not None:
        _skip(mode, reason, uid, conversation_id)
        return None
    survivor_id = str(survivor_meta['id'])
    if refresh_owed(survivor_meta) and mode is SmartMergeMode.MERGE:
        # A refresh a crashed or dead-lettered job still owes: pay it before deciding.
        try:
            refresh_survivor(uid, survivor_id, owner=owner)
        except Exception as error:
            logger.warning(
                'event=smart_merge outcome=owed_refresh_failed exception_type=%s uid=%s survivor=%s',
                type(error).__name__,
                uid,
                survivor_id,
            )

    survivor = conversations_db.get_conversation(uid, survivor_id, read_site=FirestoreReadSite.SMART_MERGE)
    if not survivor:
        _skip(mode, SkipReason.NO_PREDECESSOR, uid, conversation_id)
        return None
    survivor = dict(survivor, id=survivor_id)
    survivor_segments = _segments(survivor)
    check = check_pair(survivor, survivor_segments, new_row, new_segments)
    if check.reason is not None:
        _skip(mode, check.reason, uid, conversation_id, check.gap_seconds)
        return None

    stored = new_row.get(DECISION_FIELD)
    prior: Mapping[str, Any] = stored if isinstance(stored, Mapping) else {}
    reuse = prior.get('candidate_id') == survivor_id and prior.get('question_version') == QUESTION_VERSION
    if reuse:
        # Sticky: a replay never re-asks, so a run-to-run flip cannot change a retried job.
        p_same = prior.get('p_same')
        stretch_count, state_hash = int(prior.get('stretch_count') or 0), prior.get('state_sha256')
    else:
        fragments = ledger_fragments(survivor)
        b = fragment_of(new_row)
        if b is None or not fragments:
            _skip(mode, SkipReason.CONVERSATION_NOT_ELIGIBLE, uid, conversation_id)
            return None
        a = fragments[-1]
        candidates = list(fragments[:-1])
        for row in rows:
            if str(row.get('id')) != survivor_id:
                candidates.extend(ledger_fragments(row))
        stretch = stretch_before(a, candidates)
        state = build_state(
            source=str(new_row['source']),
            a=a,
            a_segments=fragment_segments(survivor, survivor_segments, a),
            b=b,
            b_segments=new_segments,
            stretch=stretch,
            tz=_user_tz(uid),
        )
        p_same = _ask(state)
        stretch_count, state_hash = len(stretch), state_sha256(state)

    if (
        isinstance(p_same, bool)
        or not isinstance(p_same, (int, float))
        or not math.isfinite(p_same)
        or not 0.0 <= p_same <= 1.0
    ):
        p_same = None
    same = p_same is not None and p_same >= MERGE_THRESHOLD
    reason = 'jev_unavailable' if p_same is None else ('jev_same' if same else 'jev_different')

    def record(decision: str, why: str) -> dict[str, Any]:
        return _decision_record(
            mode=mode,
            decision=decision,
            reason=why,
            p_same=p_same,
            candidate_id=survivor_id,
            check=check,
            stretch_count=stretch_count,
            state_hash=state_hash,
        )

    if mode is SmartMergeMode.SHADOW or not same:
        decision = (SHADOW_WOULD_MERGE if same else SHADOW_KEEP) if mode is SmartMergeMode.SHADOW else KEPT
        if not reuse or prior.get('decision') != decision:
            smart_merge_db.record_decision(uid, conversation_id, record(decision, reason))
        record_conversation_smart_merge(
            mode=mode.value,
            decision='merge' if same else 'keep',
            reason=reason,
            gap_seconds=check.gap_seconds,
            p_same=None if reuse else p_same,
        )
        logger.info(
            'event=smart_merge mode=%s decision=%s reason=%s p_same=%s gap_s=%s uid=%s conversation=%s candidate=%s',
            mode.value,
            decision,
            reason,
            p_same,
            check.gap_seconds,
            uid,
            conversation_id,
            survivor_id,
        )
        return None
    merge_record = record(MERGED, reason)
    if not reuse and not smart_merge_db.record_decision(uid, conversation_id, merge_record):
        return None
    return _MergePlan(survivor_id, revision(survivor), merge_record, check.gap_seconds)


# --------------------------------------------------------------------------- absorb


def _absorb(uid: str, conversation_id: str, plan: _MergePlan, *, mode: SmartMergeMode, owner: str) -> bool:
    merged_at = datetime.now(timezone.utc)

    def payloads(
        survivor: Mapping[str, Any],
        survivor_segments: Sequence[Mapping[str, Any]],
        donor: Mapping[str, Any],
        donor_segments: Sequence[Mapping[str, Any]],
    ) -> tuple[Optional[str], Optional[dict], Optional[dict]]:
        reason = new_conversation_skip(donor, donor_segments, capture_end=True)
        if reason is None:
            reason = check_pair(survivor, survivor_segments, donor, donor_segments).reason
        if reason is not None:
            return reason, None, None
        survivor_update, donor_update = absorb_payloads(
            survivor, survivor_segments, donor, donor_segments, merged_at=merged_at, decision=plan.record
        )
        return None, survivor_update, donor_update

    try:
        result = smart_merge_db.absorb_conversation(
            uid, plan.survivor_id, conversation_id, expected_revision=plan.expected_revision, plan=payloads
        )
        outcome, reason = result.outcome, result.reason
    except Exception as error:
        # A transaction error normally commits nothing; an ambiguous commit is
        # settled by reading the donor marker back.
        logger.warning(
            'event=smart_merge outcome=error stage=absorb exception_type=%s uid=%s conversation=%s',
            type(error).__name__,
            uid,
            conversation_id,
        )
        row = conversations_db.get_conversation(uid, conversation_id, read_site=FirestoreReadSite.SMART_MERGE)
        outcome, reason = ('absorbed', 'absorbed') if row and is_donor(row) else ('rejected', 'error')

    if outcome == 'rejected':
        kept = dict(plan.record, decision=KEPT, reason=reason)
        try:
            smart_merge_db.record_decision(uid, conversation_id, kept)
        except Exception:
            logger.warning('event=smart_merge outcome=record_failed uid=%s conversation=%s', uid, conversation_id)
        record_conversation_smart_merge(mode=mode.value, decision='keep', reason=reason, gap_seconds=plan.gap)
        logger.info(
            'event=smart_merge mode=%s decision=kept reason=%s uid=%s conversation=%s candidate=%s',
            mode.value,
            reason,
            uid,
            conversation_id,
            plan.survivor_id,
        )
        return False

    record_conversation_smart_merge(
        mode=mode.value, decision='merge', reason='absorbed', gap_seconds=plan.gap, p_same=plan.record.get('p_same')
    )
    logger.info(
        'event=smart_merge mode=%s decision=merged p_same=%s uid=%s conversation=%s survivor=%s',
        mode.value,
        plan.record.get('p_same'),
        uid,
        conversation_id,
        plan.survivor_id,
    )
    finish_absorb(uid, conversation_id, owner=owner)
    return True


# This module's own SmartMergeIncomplete codes: a bounded log vocabulary.
_INCOMPLETE_CODES = frozenset(
    {
        'donor_receipt_revision_changed',
        'refresh_lease_busy',
        'survivor_changed_before_refresh',
        'refresh_not_persisted',
        'survivor_vector_failed',
        'refresh_completion_fenced',
        'processing_checkpoint_fenced',
        'donor_cleanup_deferred',
    }
)


def _incomplete_cause(error: Exception) -> str:
    """An exception class name or one of this module's fence codes; never message text."""
    code = error.args[0] if isinstance(error, SmartMergeIncomplete) and error.args else None
    return code if code in _INCOMPLETE_CODES else type(error).__name__


def finish_absorb(uid: str, donor_id: str, *, owner: str, resumed: bool = False) -> None:
    """Replayable completion of a committed absorb: donor cleanup, then survivor refresh.

    Idempotent: the cleanup receipt and the survivor's ``refreshed_revision``
    make a repeat after a completed run a read-only no-op. ``resumed`` marks a
    finalization retry of the donor; its success is logged as ``resumed_ok``.
    """
    step = 'cleanup'
    try:
        donor = conversations_db.get_conversation(uid, donor_id, read_site=FirestoreReadSite.SMART_MERGE)
        if not donor or not is_donor(donor):
            return  # purged with a user-deleted survivor, or never absorbed
        survivor_id = str(smart_merge_state(donor).get('survivor_id') or '')
        if not survivor_id:
            return
        _cleanup_donor(uid, donor_id, donor, survivor_id)
        step = 'refresh'
        refresh_survivor(uid, survivor_id, owner=owner)
    except Exception as error:
        # Bounded: no ids, no message text (provider errors can quote transcript).
        logger.warning('event=smart_merge outcome=incomplete step=%s cause=%s', step, _incomplete_cause(error))
        if isinstance(error, SmartMergeIncomplete):
            raise
        raise SmartMergeIncomplete(type(error).__name__) from error
    if resumed:
        logger.info('event=smart_merge outcome=resumed_ok')


_DEFERRED_RETRACTION = (DestructiveOperationInProgress, LegalHoldActive, LegalHoldAuthorityUnavailable)


def _cleanup_donor(uid: str, donor_id: str, donor: Mapping[str, Any], survivor_id: str) -> None:
    """The sync bridge's receipt protocol, for one donor."""
    donor_revision = donor.get('sync_content_revision')
    survivor = conversations_db.get_conversation(uid, survivor_id, read_site=FirestoreReadSite.SMART_MERGE) or {}
    live_survivor = bool(survivor) and not survivor.get('deleted')
    audio_target = survivor_id if live_survivor and survivor.get('private_cloud_sync_enabled') else None
    needs_cleanup = donor.get('sync_bridge_cleaned_revision') != donor_revision
    needs_copy = bool(audio_target) and (needs_cleanup or donor.get('sync_bridge_audio_target') != audio_target)
    deferred = False
    if needs_cleanup:
        try:
            retract_sync_bridge_source(uid, donor_id)
        except _DEFERRED_RETRACTION:
            # Same policy as the sync bridge: the exclusive destructive gate or a
            # hold wins; the receipt stays pending for a later replay.
            deferred = True
            record_fallback(
                component='conversation_smart_merge',
                from_mode='retract',
                to_mode='deferred',
                reason='other',
                outcome='degraded',
                log=logger,
            )
    if needs_copy:
        copy_sync_bridge_audio(uid, donor_id, survivor_id)
        audio_files = conversations_db.create_audio_files_from_chunks(uid, survivor_id)
        if audio_files:
            files_payload = [audio_file.dict() for audio_file in audio_files]
            conversations_db.update_conversation(uid, survivor_id, {'audio_files': files_payload})
            if is_audio_merge_dispatch_enabled():
                enqueue_conversation_artifact_build(
                    uid, survivor_id, compute_audio_files_fingerprint(files_payload), caller='smart_merge'
                )
    if not deferred and (needs_cleanup or needs_copy):
        if not mark_sync_bridge_cleaned(uid, donor_id, donor_revision, audio_target):
            raise SmartMergeIncomplete('donor_receipt_revision_changed')
    if deferred:
        # A held source still owes retraction. Do not close its only durable retry.
        raise SmartMergeIncomplete('donor_cleanup_deferred')


def refresh_survivor(uid: str, survivor_id: str, *, owner: str) -> None:
    """Regenerate the survivor once for its current revision, under a short lease."""
    # Job ids survive lease expiry and redelivery. Each invocation needs its own
    # token so a late failure cannot release a newer delivery of the same job.
    owner = f'{owner}:{uuid4().hex}'
    claimed = smart_merge_db.claim_survivor_refresh(
        uid, survivor_id, owner=owner, now=datetime.now(timezone.utc), lease_seconds=REFRESH_LEASE_SECONDS
    )
    if claimed is None:
        row = conversations_db.get_conversation(uid, survivor_id, read_site=FirestoreReadSite.SMART_MERGE)
        if row and not row.get('deleted') and refresh_owed(row):
            record_conversation_smart_merge_refresh('lease_busy')
            raise SmartMergeIncomplete('refresh_lease_busy')
        return
    try:
        _refresh_claimed(uid, survivor_id, claimed, owner=owner)
    except Exception:
        # A failed refresh must not park the owed refresh behind its own lease for
        # REFRESH_LEASE_SECONDS; compare-and-release so another owner's lease survives.
        try:
            smart_merge_db.release_survivor_refresh(uid, survivor_id, owner=owner)
        except Exception as release_error:
            logger.warning(
                'event=smart_merge outcome=lease_release_failed exception_type=%s', type(release_error).__name__
            )
        raise


def _refresh_claimed(uid: str, survivor_id: str, claimed: int, *, owner: str) -> None:
    row = conversations_db.get_conversation(uid, survivor_id, read_site=FirestoreReadSite.SMART_MERGE)
    if not row or row.get('deleted') or revision(row) != claimed:
        if row and not row.get('deleted'):
            raise SmartMergeIncomplete('survivor_changed_before_refresh')
        return
    processed = deserialize_conversation(row)
    state = smart_merge_state(row)
    if int(state.get('processed_revision') or 0) < claimed or state.get('processed_sync_revision') != row.get(
        'sync_content_revision'
    ):
        persistence = {'owned': True}
        try:
            processed = process_conversation(
                uid,
                processed.language or 'en',
                processed,
                trigger=ProcessingTrigger.SMART_MERGE,
                persistence_observer=lambda owned: persistence.__setitem__('owned', owned),
                smart_merge_refresh=(claimed, owner),
            )
        except Exception:
            record_conversation_smart_merge_refresh('failed')
            raise
        if not persistence['owned']:
            # Deleted, or a sync append moved the transcript on; the next decision
            # against this survivor pays the refresh it still owes.
            record_conversation_smart_merge_refresh('fenced')
            raise SmartMergeIncomplete('refresh_not_persisted')
        if not smart_merge_db.checkpoint_survivor_processing(
            uid, survivor_id, owner=owner, revision=claimed, sync_revision=row.get('sync_content_revision')
        ):
            raise SmartMergeIncomplete('processing_checkpoint_fenced')
    try:
        # Reprocess never re-embeds; the merged occasion must be findable as a whole.
        save_structured_vector(uid, processed)
    except Exception as error:
        logger.warning(
            'event=smart_merge outcome=vector_failed exception_type=%s uid=%s survivor=%s',
            type(error).__name__,
            uid,
            survivor_id,
        )
        record_conversation_smart_merge_refresh('failed')
        raise SmartMergeIncomplete('survivor_vector_failed') from error
    if smart_merge_db.complete_survivor_refresh(uid, survivor_id, owner=owner, revision=claimed):
        record_conversation_smart_merge_refresh('refreshed')
    else:
        raise SmartMergeIncomplete('refresh_completion_fenced')

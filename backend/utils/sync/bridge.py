"""Replayable external bridge effects, always outside assignment transactions.

Ancestry is persisted with the transcript. Donor retraction that collides with
the exclusive destructive-operation gate is deferred onto the revision-fenced
receipt and retried on a later append; original audio and redirect tombstones
are never removed. Copy and checkpoint failures still propagate to the job
retry path.
"""

from __future__ import annotations

import logging
from _thread import LockType
from typing import Callable, NotRequired, TypedDict

from config.conversation_smart_merge import smart_merge_flatten_chain_repair_enabled, smart_merge_flatten_enabled
from config import merge_ancestry
from config import sync_operation_snapshot
from config.firestore_read_levers import lever_enabled
from config.sync_finalize import sync_finalize_target_recovery_enabled
from utils.conversations.smart_merge_policy import user_managed as _policy_user_managed
from database.action_item_refresh import RefreshConversationUnavailable
from database import conversations as conversations_db
from database.firestore_read_origin import read_origin
from database.legal_holds import (
    DestructiveOperationInProgress,
    LegalHoldActive,
    LegalHoldAuthorityUnavailable,
)
from database.sync_bridges import mark_sync_bridge_cleaned
from utils.conversations.action_item_refresh import transfer_donor
from utils.conversations.merge_conversations import copy_sync_bridge_audio, retract_sync_bridge_source
from utils.metrics import OMI_SYNC_BRIDGE_RETRACTION_TOTAL
from utils.observability.fallback import record_fallback
from utils.sync.assignment_errors import (
    SyncAssignmentConflict,
    SyncAssignmentConflictReason,
    SyncAssignmentSuperseded,
)
from utils.sync.telemetry import bounded_exception_reason, bounded_exception_type
from utils.sync.fsr_metadata import read_metadata

logger = logging.getLogger(__name__)

_DEFERRED_RETRACTION_REASONS: dict[type[BaseException], str] = {
    DestructiveOperationInProgress: 'gate_busy',
    LegalHoldActive: 'hold_active',
    LegalHoldAuthorityUnavailable: 'authority_unavailable',
}


class SyncBridgeAssignment(TypedDict):
    id: str
    sync_relevance: str
    sync_merged_from: NotRequired[list[str]]
    private_cloud_sync_enabled: NotRequired[bool]


class SyncSegmentResponse(TypedDict):
    new_memories: set[str]
    updated_memories: set[str]
    _merged: NotRequired[dict[str, str | None]]


def _record_bridge_retraction(outcome: str, reason: str = 'none') -> None:
    try:
        OMI_SYNC_BRIDGE_RETRACTION_TOTAL.labels(outcome=outcome, reason=reason).inc()
    except Exception:
        pass


def _deferred_retraction_reason(error: BaseException) -> str | None:
    for error_type, reason in _DEFERRED_RETRACTION_REASONS.items():
        if isinstance(error, error_type):
            return reason
    return None


def _record_refresh_deferred(reason: str, error: BaseException | None = None) -> None:
    _record_bridge_retraction('deferred', reason)
    logger.warning(
        'event=sync_bridge_refresh outcome=deferred reason=%s exception_type=%s',
        reason,
        bounded_exception_type(error) if error is not None else 'none',
    )
    record_fallback(
        component='sync_dispatch',
        from_mode='retract',
        to_mode='deferred',
        reason='other',
        outcome='degraded',
        log=logger,
    )


def _bridge_source_defect(
    source: dict | None, survivor_id: str, lineage: list[str], load: Callable[[str], dict | None]
) -> str | None:
    """Bounded reason a smart survivor's bridge source does not redirect at it, else ``None``.

    Ordinary sync absorbs leave ancestors redirecting at an intermediate hop of
    the same lineage. With chain repair on, a chain of tombstones that stays in
    the survivor's ``sync_merged_from`` and ends at the survivor is accepted:
    every hop's content already belongs to the survivor, and the next flatten
    re-points the hops. Anything leaving the lineage still conflicts.
    """
    if not source or not source.get('deleted') or not source.get('sync_merged_into'):
        return None
    target = source['sync_merged_into']
    if target == survivor_id:
        return None
    if target not in lineage:
        return 'redirect_elsewhere'
    if not smart_merge_flatten_chain_repair_enabled():
        return 'chain'
    # Same hop shape the flatten planner accepts: a plain sync tombstone that is
    # not user-managed. A hop that is not discarded, has no revision, carries
    # smart-merge state, or is starred or otherwise user-managed stays a
    # conflict, so finalize never cleans up a row the planner would refuse.
    if not merge_ancestry.plain_chain_hop(source) or _policy_user_managed(source):
        return 'chain_broken'
    members = set(lineage)
    for _ in range(len(members)):
        hop = load(target)
        if not hop or not merge_ancestry.plain_chain_hop(hop) or _policy_user_managed(hop):
            return 'chain_broken'
        target = hop['sync_merged_into']
        if target == survivor_id:
            return None
        if target not in members:
            return 'chain_broken'
    return 'chain_broken'


@read_origin('job:sync_operation_snapshot')
def finish_sync_bridges(
    uid: str, conversation_id: str, *, audio_source_id: str | None = None, silent: bool = False
) -> str:
    recovery = sync_finalize_target_recovery_enabled()
    # The legacy hydrated reader can do photo/correction IO after its document
    # snapshot, so only the existing metadata-only path permits this fast path.
    reuse = sync_operation_snapshot.enabled() and lever_enabled('backfill_task_reads', uid)
    visited: set[str] = set()
    while True:
        if conversation_id in visited or len(visited) >= 16:
            raise SyncAssignmentConflict('sync redirect cycle', subtype=SyncAssignmentConflictReason.REDIRECT_CYCLE)
        visited.add(conversation_id)
        row = read_metadata(conversations_db, uid, conversation_id, operation='bridge')
        if not row or (row.get('deleted') and not row.get('sync_merged_into')):
            raise SyncAssignmentSuperseded('sync conversation deleted during bridge')
        if row.get('sync_merged_into'):
            conversation_id = row['sync_merged_into']
            continue
        flatten = smart_merge_flatten_enabled() and (row.get('smart_merge') or {}).get('role') == 'survivor'
        lineage = row.get('sync_merged_from', [])
        sources: dict[str, dict | None] = {}

        def load(source_id: str) -> dict | None:
            if source_id not in sources:
                sources[source_id] = read_metadata(conversations_db, uid, source_id, operation='bridge')
            return sources[source_id]

        redirected = False
        effects_started = False
        for source_id in lineage:
            source = load(source_id)
            kind = _bridge_source_defect(source, conversation_id, lineage, load) if flatten else None
            if not source or not source.get('deleted') or not source.get('sync_merged_into') or kind:
                logger.warning(
                    'event=sync_bridge outcome=source_rejected kind=%s',
                    kind or ('missing' if not source else 'not_tombstone'),
                )
                raise SyncAssignmentConflict(
                    'sync bridge source missing or not a tombstone',
                    subtype=SyncAssignmentConflictReason.BRIDGE_SOURCE_NOT_TOMBSTONE,
                )
            revision = source['sync_content_revision']
            needs_cleanup = source.get('sync_bridge_cleaned_revision') != revision
            audio_target = conversation_id if row.get('private_cloud_sync_enabled') else None
            needs_copy = audio_target and (
                needs_cleanup or source.get('sync_bridge_audio_target') != audio_target or source_id == audio_source_id
            )
            # Donor task retraction can cancel client reminders. A silent repair
            # preserves that durable cleanup debt for a later normal append.
            cleanup_deferred = bool(silent and needs_cleanup)
            if needs_cleanup and not silent:
                effects_started = True
                _record_bridge_retraction('attempted')
                logger.info('event=sync_bridge outcome=attempted uid=%s source_id=%s', uid, source_id)
                try:
                    try:
                        transfer_donor(uid, source_id, conversation_id)
                    except RefreshConversationUnavailable as error:
                        if not recovery:
                            raise
                        if not error.successor_id:
                            raise SyncAssignmentSuperseded('sync refresh target deleted') from error
                        _record_refresh_deferred('target_redirected', error)
                        conversation_id = error.successor_id
                        redirected = True
                        break
                    except Exception as error:
                        if not recovery:
                            raise
                        # Never retract donor tasks or stamp cleanup after a failed
                        # transfer. Persisted intake can complete; the receipt stays
                        # pending for a later append/reconciliation.
                        _record_refresh_deferred('refresh_failed', error)
                        cleanup_deferred = True
                    if not cleanup_deferred:
                        retract_sync_bridge_source(uid, source_id)
                except SyncAssignmentSuperseded:
                    raise
                except Exception as error:
                    reason = _deferred_retraction_reason(error)
                    if reason is None:
                        _record_bridge_retraction('failed', 'other')
                        logger.error(
                            'event=sync_bridge outcome=failed exception_type=%s reason=%s uid=%s source_id=%s',
                            bounded_exception_type(error),
                            bounded_exception_reason(error),
                            uid,
                            source_id,
                        )
                        raise
                    cleanup_deferred = True
                    _record_bridge_retraction('deferred', reason)
                    logger.info(
                        'event=sync_bridge outcome=deferred reason=%s exception_type=%s uid=%s source_id=%s',
                        reason,
                        bounded_exception_type(error),
                        uid,
                        source_id,
                    )
                    record_fallback(
                        component='sync_dispatch',
                        from_mode='retract',
                        to_mode='deferred',
                        reason='other',
                        outcome='degraded',
                        log=logger,
                    )
            if needs_copy:
                effects_started = True
                # Invalidate an older copy receipt before late audio copying:
                # if copying fails, a retry without this worker's source hint
                # must still see pending audio work.
                if source_id == audio_source_id and source.get('sync_bridge_audio_target') == audio_target:
                    if not mark_sync_bridge_cleaned(uid, source_id, revision, None):
                        raise RuntimeError('sync bridge completion revision changed')
                copy_sync_bridge_audio(uid, source_id, conversation_id)
            if cleanup_deferred:
                continue
            if needs_cleanup or needs_copy:
                effects_started = True
                if not mark_sync_bridge_cleaned(uid, source_id, revision, audio_target):
                    raise RuntimeError('sync bridge completion revision changed')
                if needs_cleanup:
                    _record_bridge_retraction('converged')
                    logger.info('event=sync_bridge outcome=converged uid=%s source_id=%s', uid, source_id)
        if redirected:
            continue
        # Only the no-lineage fast path has no intervening donor reads or
        # effects. Recheck after a lineage traversal, even if cleanup was done,
        # so a redirect during donor reads still updates the returned target.
        if reuse and not effects_started and not lineage:
            current = row
            sync_operation_snapshot.avoided('bridge_no_effect')
        else:
            current = read_metadata(conversations_db, uid, conversation_id, operation='bridge')
        if current and current.get('sync_merged_into'):
            conversation_id = current['sync_merged_into']
            continue
        if not current or current.get('deleted'):
            raise SyncAssignmentSuperseded('sync conversation deleted during bridge')
        return conversation_id


def finish_sync_segment(
    uid: str,
    assigned: SyncBridgeAssignment,
    response: SyncSegmentResponse,
    lock: LockType,
    language: str | None,
    *,
    audio_source_id: str | None = None,
) -> None:
    """One completion point, after audio persistence; follow a concurrent bridge."""
    if not assigned.get('sync_merged_from') and not assigned.get('private_cloud_sync_enabled'):
        return
    conversation_id = assigned['id']
    try:
        canonical_id = finish_sync_bridges(uid, conversation_id, audio_source_id=audio_source_id)
    except SyncAssignmentSuperseded as error:
        if not sync_finalize_target_recovery_enabled():
            raise
        # This callback alone runs after intake audio/transcript persistence.
        # Shared batch callers retain the helper's existing supersession signal
        # and their own privacy/receipt settlement contract.
        _record_refresh_deferred('target_unavailable', error)
        canonical_id = None
    if canonical_id != conversation_id:
        with lock:
            response['new_memories'].discard(conversation_id)
            response['updated_memories'].discard(conversation_id)
            if canonical_id is not None:
                response['updated_memories'].add(canonical_id)
            merged = response.setdefault('_merged', {})
            merged.pop(conversation_id, None)
            if canonical_id is not None and assigned['sync_relevance'] == 'keep':
                merged[canonical_id] = language

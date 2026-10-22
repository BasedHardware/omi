"""Bounded held-audio recovery from the existing locked-content request path.

The async coordinator borrows leaf workers. Audio stays held until transcription,
content persistence and idempotent usage settlement succeed, including silence.
"""

from functools import partial
import logging
import threading
import time

from typing import Any, Awaitable, Callable

from config.rate_card import recording_units_per_hour
from config.stt_cap_dispatch import recovery_admission_enabled as enabled, any_recovery_admission_enabled, hold_lane
from database import users as users_db
from database import sync_cap_holds, sync_cap_recovery, cap_recovery_pacing
from utils.analytics import record_usage
from utils.executors import run_blocking, db_executor, sync_executor, storage_executor
from utils.stt_cap_dispatch import sync_allowed
from utils.fair_use import get_hard_restriction_status, is_daily_audio_ceiling_exceeded
from utils.stt.pre_recorded import get_prerecorded_service
from utils import funded_processing
from utils.sync import cap_hold, cap_hold_reservations, cap_recovery_plan, cap_work_budget
from utils.sync.cap_hold_erasure import erase as _erase
from utils.observability.held_content import record_recovery, record_pacing
from utils.observability.stt_cap_dispatch import record_reconciliation
from utils.sync.cap_recovery_audio import prepare as prepare_audio
from utils.sync.held_coverage import piece_state, covered_receipt
from utils.sync.held_piece_split import delegate, attempt_floor
from utils.sync.cap_recovery_receipts import settled_empty as _settled_empty
from models.geolocation import Geolocation
from utils.sync.pipeline import (
    process_segment,
    build_person_embeddings_cache,
    finalize_recovered_sync_segment,
)
from models.conversation import ConversationSource

logger = logging.getLogger(__name__)
RECONCILIATION_COOLDOWN_SECONDS = 1800
_backlog_runner: Callable[[str], Awaitable[bool | None]] | None = None


def register_backlog_runner(runner: Callable[[str], Awaitable[bool | None]]) -> None:
    global _backlog_runner
    _backlog_runner = runner


def _stored(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _stored(item) for key, item in value.items()}
    if isinstance(value, (set, tuple, list)):
        return [_stored(item) for item in value]
    return value


def _response(receipts: dict) -> dict:
    response: dict[str, Any] = {'new_memories': set(), 'updated_memories': set()}
    for receipt in receipts.values():
        for key, value in receipt.get('response', {}).items():
            if key in {'new_memories', 'updated_memories', '_fenced_conversation_ids'}:
                response.setdefault(key, set()).update(value)
            elif isinstance(value, dict):
                response.setdefault(key, {}).update(value)
    return response


async def _save(uid: str, snapshot: Any, row: dict, updates: dict) -> bool:
    saved = await run_blocking(db_executor, cap_hold.checkpoint, uid, snapshot.reference, row['lease_token'], updates)
    if saved:
        row.update(updates)
    return saved


def _new_dispatch_allowed(uid: str, lane: str) -> bool:
    if not enabled(uid, lane) or not sync_allowed(uid, lane=lane):
        return False
    restricted, _ = get_hard_restriction_status(uid)
    return not restricted and not is_daily_audio_ceiling_exceeded(uid)


async def _recover_row(uid: str, snapshot: Any, row: dict[str, Any]) -> bool:
    if not any_recovery_admission_enabled(uid):
        return False
    if row.get('finalized'):
        return True
    meta = await run_blocking(storage_executor, cap_hold.metadata, uid, row)
    lane = hold_lane(meta)
    if lane is None or not enabled(uid, lane):
        return False
    if meta.get('content_id'):
        status = await run_blocking(db_executor, sync_cap_holds.recovery_status, uid, meta['content_id'], snapshot.id)
        if status in {'completed', 'settled'}:
            return await _save(uid, snapshot, row, {'finalized': True, 'ledger_already_settled': True})
        if status != 'ready':
            return False
    if not row.get('piece_receipts') and not await run_blocking(db_executor, _new_dispatch_allowed, uid, lane):
        return False
    prefs = await run_blocking(db_executor, users_db.get_user_transcription_preferences, uid) or {}
    private = await run_blocking(db_executor, users_db.get_user_private_cloud_sync_enabled, uid)
    protection = await run_blocking(db_executor, users_db.get_data_protection_level, uid) if private else None
    try:
        embeddings = await run_blocking(db_executor, build_person_embeddings_cache, uid)
    except Exception as error:
        logger.warning(
            'event=stt_cap_recovery outcome=speaker_context_unavailable exception_type=%s', type(error).__name__
        )
        embeddings = {}
    geolocation = Geolocation.model_validate(meta['geolocation']) if meta.get('geolocation') else None
    directory = await run_blocking(storage_executor, cap_hold.recovery_directory, uid)
    receipts: dict[str, dict[str, Any]] = dict(row.get('piece_receipts') or {})

    async def save_receipt(name: str, receipt: dict[str, Any] | None) -> bool:
        updated = dict(receipts)
        if receipt is None:
            updated.pop(name, None)
        else:
            updated[name] = receipt
        if not await _save(uid, snapshot, row, {'piece_receipts': updated}):
            return False
        receipts.clear()
        receipts.update(updated)
        return True

    record_recovery('attempt')
    try:
        try:
            plan, local_paths, contexts = await cap_recovery_plan.ensure_plan(
                uid, snapshot, row, meta, directory, prepare_audio, _save
            )
        except cap_recovery_plan.PlanFenced:
            return False
        processed = set(row.get('processed_paths') or [])
        pending = False
        for name in sorted(set(plan) | set(receipts)):
            if cap_work_budget.exhausted():
                pending = True
                break
            if not await run_blocking(
                db_executor, cap_hold.renew, uid, snapshot.reference, row['lease_token'], time.time()
            ):
                return False
            if name in processed:
                continue
            receipt: dict[str, Any] | None = receipts.get(name)
            if receipt and receipt.get('state') == 'failed_reconciliation':
                continue
            attempt = max(
                attempt_floor(plan.get(name, {})),
                (receipt or {}).get('attempt', 1) if (receipt or {}).get('provider_result') else 1,
            )
            settled = _settled_empty(receipt)
            if settled is not None:
                # Crash between the result checkpoint and the receipt save.
                if not await save_receipt(name, settled):
                    return False
                record_reconciliation('settled_empty', snapshot.id, name)
                receipt = settled
            elif receipt and receipt.get('state') == 'dispatched' and not receipt.get('provider_result'):
                if 'dispatched_at' not in receipt:
                    receipt = {
                        **receipt,
                        'attempt': receipt.get('attempt', 1),
                        'dispatched_at': row.get('created_at', time.time()),
                    }
                    if not await save_receipt(name, receipt):
                        return False
                if time.time() - receipt['dispatched_at'] < RECONCILIATION_COOLDOWN_SECONDS:
                    pending = True
                    continue
                proof = await run_blocking(db_executor, sync_cap_recovery.ingested_piece, uid, snapshot.id, name)
                if proof:
                    receipt = {**proof, 'reconciled_ingested': True}
                    if not await save_receipt(name, receipt):
                        return False
                    record_reconciliation('reconciled_ingested', snapshot.id, name)
                elif receipt.get('attempt', 1) >= 2 or name not in plan:
                    if not await save_receipt(
                        name, {**receipt, 'state': 'failed_reconciliation', 'has_content': False}
                    ):
                        return False
                    record_reconciliation('failed', snapshot.id, name)
                    continue
                else:
                    attempt = 2
            if receipt is None or receipt.get('state') == 'dispatched':
                cached_result = (receipt or {}).get('provider_result')
                if not cached_result and not await run_blocking(db_executor, _new_dispatch_allowed, uid, lane):
                    pending = True
                    continue
                previous = receipt
                try:
                    segment_path, context = await cap_recovery_plan.stage_piece(
                        uid, name, plan[name], directory, local_paths, contexts
                    )
                    coverage_state = (
                        await run_blocking(db_executor, piece_state, uid, segment_path, meta, context)
                        if not cached_result
                        else None
                    )
                    if coverage_state is not None and coverage_state.state == 'partial':
                        piece = (name, segment_path, context, coverage_state, attempt)
                        if not await delegate(uid, snapshot, row, piece, plan, receipts, processed, save=_save):
                            return False
                        pending = True
                        continue
                    if coverage_state is not None:
                        if not await save_receipt(name, covered_receipt(previous)):
                            return False
                        processed.add(name)
                        if not await _save(uid, snapshot, row, {'processed_paths': sorted(processed)}):
                            return False
                        continue
                    language = prefs.get('language') or ''
                    service = (
                        ((receipt or {})['provider'], None, (receipt or {})['model'])
                        if cached_result
                        else get_prerecorded_service(
                            language if prefs.get('single_language_mode') and language else 'multi'
                        )
                    )
                except Exception as error:
                    logger.warning(
                        'event=stt_cap_recovery outcome=prepare_deferred hold_id=%s piece=%r exception_type=%s',
                        snapshot.id,
                        name,
                        type(error).__name__,
                    )
                    pending = True
                    continue
                if not cached_result:
                    pacing = await run_blocking(db_executor, cap_recovery_pacing.reserve, plan[name]['seconds'])
                    now = time.time()
                    if pacing.outcome != 'granted':
                        since = row.get('pacing_deferred_since') or now
                        if not await _save(
                            uid,
                            snapshot,
                            row,
                            {
                                'next_attempt_at': now + pacing.retry_after,
                                'pacing_deferred_since': since,
                                'pacing_reason': pacing.reason,
                            },
                        ):
                            return False
                        record_pacing(pacing.outcome, plan[name]['seconds'], now - since)
                        pending = True
                        break
                    record_pacing('granted', plan[name]['seconds'])
                    if row.get('pacing_deferred_since') and not await _save(
                        uid, snapshot, row, {'pacing_deferred_since': 0, 'pacing_reason': '', 'next_attempt_at': 0}
                    ):
                        return False
                intent: dict[str, Any] = {
                    **({'provider_result': cached_result} if cached_result else {}),
                    'state': 'dispatched',
                    'provider': service[0],
                    'model': service[2],
                    'funding': 'omi',
                    'attempt': attempt,
                    'dispatched_at': time.time(),
                    'seconds': plan[name]['seconds'],
                    'usage_metadata': {'funding': 'omi', 'provider': service[0], 'source': 'sync_v2'},
                }
                if not await save_receipt(name, intent):
                    return False
                response = {'new_memories': set(), 'updated_memories': set()}
                errors, outcome = [], {'provider_called': False}
                try:
                    ok = await run_blocking(
                        sync_executor,
                        process_segment,
                        segment_path,
                        uid,
                        response,
                        threading.Lock(),
                        errors,
                        ConversationSource(meta['source']),
                        False,
                        prefs,
                        embeddings,
                        private_cloud_sync_enabled=bool(private),
                        data_protection_level=protection,
                        client_device_id=meta.get('client_device_id'),
                        client_platform=meta.get('client_platform'),
                        target_conversation_id=context.get('target_conversation_id'),
                        geolocation=geolocation,
                        source_position_map=context.get('source_position_map'),
                        **(
                            {'recording_session_id': context['recording_session_id']}
                            if context.get('recording_session_id')
                            else {}
                        ),
                        lineage_binding=context.get('lineage_binding'),
                        sync_lane=meta.get('sync_lane', 'fresh'),
                        cap_recovery=True,
                        cap_dispatch_lane=lane,
                        deferred_outcome=outcome,
                        cap_recovery_service=service,
                        cap_recovery_checkpoint={
                            'hold_id': snapshot.id,
                            'piece': name,
                            'lease_token': row['lease_token'],
                            'attempt': attempt,
                            'receipt': intent,
                            **(
                                {'capture_partition': f"live:{snapshot.id}:channel:{meta.get('channel', 0)}"}
                                if meta.get('origin') == 'live'
                                else {}
                            ),
                        },
                    )
                except Exception as error:
                    ok = False
                    errors.append(type(error).__name__)
                    logger.warning(
                        'event=stt_cap_recovery outcome=processing_deferred hold_id=%s piece=%r exception_type=%s',
                        snapshot.id,
                        name,
                        type(error).__name__,
                    )
                if not outcome['provider_called']:
                    if not await save_receipt(name, previous):
                        return False
                    record_reconciliation('cleared_noncall', snapshot.id, name)
                    pending = True
                    continue
                if attempt == 2:
                    record_reconciliation('redispatched', snapshot.id, name)
                if errors or outcome.get('cap_held') or outcome.get('recovery_ambiguous'):
                    refreshed = await run_blocking(db_executor, snapshot.reference.get)
                    persisted = (refreshed.to_dict() or {}).get('piece_receipts') or {}
                    receipts.update(persisted)
                    row['piece_receipts'] = dict(receipts)
                    receipt = _settled_empty(receipts.get(name))
                    if receipt is None:
                        pending = True
                        continue
                    if not await save_receipt(name, receipt):
                        return False
                    record_reconciliation('settled_empty', snapshot.id, name)
                else:
                    receipt = {
                        **{k: v for k, v in intent.items() if k != 'provider_result'},
                        'state': 'transcribed',
                        'response': _stored(response),
                        'seconds': intent['seconds'] if ok else 0,
                        'has_content': bool(ok),
                    }
                    if not await save_receipt(name, receipt):
                        return False
            if receipt['has_content']:
                seconds = int(receipt['seconds'])
                await run_blocking(
                    db_executor,
                    record_usage,
                    uid,
                    transcription_seconds=seconds,
                    speech_seconds=seconds,
                    idempotency_key=f'cap-hold-{snapshot.id}-{name}',
                    usage_metadata=receipt.get(
                        'usage_metadata', {'funding': 'omi', 'provider': 'unknown', 'source': 'sync_v2'}
                    ),
                )
            processed.add(name)
            if not await _save(uid, snapshot, row, {'processed_paths': sorted(processed)}):
                return False
        # Finalize completed siblings even while another piece is cooling down.
        finalized = set(row.get('finalized_paths') or [])
        ready = {name: receipts[name] for name in processed - finalized if name in receipts}
        if ready:
            await run_blocking(sync_executor, finalize_recovered_sync_segment, uid, _response(ready), bool(private))
            finalized.update(ready)
            if not await _save(uid, snapshot, row, {'finalized_paths': sorted(finalized)}):
                return False
        if pending:
            return False
        failed = any(r.get('state') == 'failed_reconciliation' for r in receipts.values())
        retained = failed or any(r.get('reconciled_ingested') for r in receipts.values())
        saved = await _save(
            uid,
            snapshot,
            row,
            {
                'finalized': True,
                'recovery_response': _stored(_response(receipts)),
                'failed_reconciliation': failed,
                'retain_audio': retained,
            },
        )
        if saved:
            record_recovery('completed')
        return saved
    finally:
        await run_blocking(storage_executor, directory.cleanup)


def _settle_and_erase(uid: str, snapshot: Any, row: dict) -> None:
    if row.get('failed_reconciliation'):
        snapshot.reference.update({'state': 'retained', 'next_attempt_at': cap_hold.RETAINED_NEXT_ATTEMPT_AT})
        return  # Siblings finalized, but the held ledger must not claim failed audio was transcribed.
    if not row.get('settled'):
        meta = cap_hold.metadata(uid, row)
        if meta.get('content_id') and not row.get('ledger_already_settled'):
            if not sync_cap_holds.settle_hold(
                uid,
                meta['content_id'],
                snapshot.id,
                row.get('recovery_response') or {},
                len(row.get('piece_receipts') or {}),
            ):
                raise RuntimeError('hold content ledger ownership changed')
        snapshot.reference.update({'settled': True})
    if row.get('retain_audio'):
        snapshot.reference.update({'state': 'retained', 'next_attempt_at': cap_hold.RETAINED_NEXT_ATTEMPT_AT})
    else:
        _erase(uid, snapshot, row)


async def _selected_lane(uid: str, row: dict) -> str | None:
    """The hold's original dispatch lane when this owner and lane are in recovery scope, else None.

    Recovery scope = execution admission plus main's optional recovery cohort (#22991)."""
    if not any_recovery_admission_enabled(uid):
        return None
    meta = await run_blocking(storage_executor, cap_hold.metadata, uid, row)
    lane = hold_lane(meta)
    return lane if lane is not None and enabled(uid, lane) else None


async def selected_for_recovery(uid: str, row: dict) -> bool:
    return await _selected_lane(uid, row) is not None


async def recover_selected(uid: str, snapshot: Any) -> bool:
    """One explicitly selected manifest, retaining existing claim/receipt fences."""
    row = snapshot.to_dict() or {}
    lane = await _selected_lane(uid, row)
    if lane is None:
        return False
    if row.get('state') == 'completed':
        await run_blocking(storage_executor, _settle_and_erase, uid, snapshot, row)
        return True
    if row.get('state') == 'batch_admitted':
        # Terminal hand-off (lane 8): batch owns this audio. Only finish an interrupted erase; never
        # claim, re-admit, or settle it (settlement would bill the batch-processed audio twice).
        await run_blocking(storage_executor, _erase, uid, snapshot, row)
        return True
    row = await run_blocking(db_executor, cap_hold.claim, uid, snapshot.reference, time.time())
    if row is None:
        return False
    try:
        from utils.batch_pipeline import cap_hold_admission

        if await run_blocking(db_executor, cap_hold_admission.enabled_for, row):
            if not await run_blocking(db_executor, _new_dispatch_allowed, uid, lane):
                return False
            admitted = await cap_hold_admission.admit_held(uid, snapshot, row)
            if admitted.outcome == 'covered':
                if not await _save(
                    uid, snapshot, row, {'state': 'completed', 'finalized': True, 'recovery_response': {}}
                ):
                    return False
                await run_blocking(storage_executor, _settle_and_erase, uid, snapshot, row)
                return True
            if admitted.outcome not in ('admitted', 'already_admitted'):
                return False
            await run_blocking(
                db_executor,
                partial(
                    cap_hold_reservations.reserve,
                    uid,
                    snapshot.id,
                    units=cap_hold.remaining_seconds(row) * float(recording_units_per_hour('batch')) / 3600,
                    period=funded_processing.period_id(),
                    batch_job_id=admitted.batch_job_id or '',
                ),
            )
            if not await _save(uid, snapshot, row, {'state': 'batch_admitted', 'batch_job_id': admitted.batch_job_id}):
                return False
            await run_blocking(storage_executor, _erase, uid, snapshot, row)
            return True
        if not await _recover_row(uid, snapshot, row):
            return False
        if not await _save(uid, snapshot, row, {'state': 'completed'}):
            return False
        await run_blocking(storage_executor, _settle_and_erase, uid, snapshot, row)
        return True
    finally:
        await run_blocking(db_executor, cap_hold.release, uid, snapshot.reference, row['lease_token'])


async def recover(uid: str) -> None:
    # Legacy request/reset/resume hooks may wake an approved run, but never
    # create consent. Worker is imported lazily to avoid pipeline import cycles.
    if any_recovery_admission_enabled(uid) and _backlog_runner is not None:
        await _backlog_runner(uid)

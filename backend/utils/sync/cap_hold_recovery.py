"""Bounded held-audio recovery from the existing locked-content request path.

The async coordinator borrows leaf workers. Audio stays held until transcription,
content persistence and idempotent usage settlement succeed, including silence.
"""

import asyncio
import logging
from pathlib import Path
import threading
import time

from anyio import from_thread
from typing import Any
from google.api_core.exceptions import NotFound

from config.stt_cap_dispatch import enabled
from database import users as users_db
from database import sync_cap_holds
from utils.analytics import record_usage
from utils.executors import run_blocking, db_executor, sync_executor, storage_executor, start_background_task
from utils.stt_cap_dispatch import sync_allowed
from utils.fair_use import get_hard_restriction_status, is_daily_audio_ceiling_exceeded
from utils.sync import cap_hold
from utils.sync.files import get_wav_duration
from utils.sync.cap_recovery_audio import prepare as prepare_audio
from models.geolocation import Geolocation
from utils.sync.pipeline import (
    process_segment,
    build_person_embeddings_cache,
    finalize_recovered_sync_segment,
)
from models.conversation import ConversationSource

logger = logging.getLogger(__name__)


def _erase(uid: str, snapshot: Any, row: dict[str, Any]) -> None:
    # Account deletion already purges this existing owner-scoped chunk prefix.
    for path in filter(None, (row['audio_path'], row.get('metadata_path'))):
        if not path.startswith(f'chunks/{uid}/cap-held/'):
            raise ValueError('hold audio owner mismatch')
        try:
            cap_hold.get_private_cloud_sync_bucket().blob(path).delete()
        except NotFound:
            pass
    snapshot.reference.delete()


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


def _new_dispatch_allowed(uid: str) -> bool:
    if not sync_allowed(uid):
        return False
    restricted, _ = get_hard_restriction_status(uid)
    return not restricted and not is_daily_audio_ceiling_exceeded(uid)


async def _recover_row(uid: str, snapshot: Any, row: dict[str, Any]) -> bool:
    if row.get('finalized'):
        return True
    meta = await run_blocking(db_executor, cap_hold.metadata, uid, row)
    if meta.get('content_id'):
        status = await run_blocking(db_executor, sync_cap_holds.recovery_status, uid, meta['content_id'], snapshot.id)
        if status in {'completed', 'settled'}:
            return await _save(uid, snapshot, row, {'finalized': True, 'ledger_already_settled': True})
        if status != 'ready':
            return False
    if not row.get('piece_receipts') and not await run_blocking(db_executor, _new_dispatch_allowed, uid):
        return False
    prefs = await run_blocking(db_executor, users_db.get_user_transcription_preferences, uid)
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
    try:
        name = Path(meta.get('file_name') or f"{meta['timestamp']}.wav").name
        path = str(Path(directory.name) / name)
        await run_blocking(storage_executor, cap_hold.read_audio, uid, row, path)
        paths, source_maps, targets, bindings = await prepare_audio(uid, path, meta)
        processed = set(row.get('processed_paths') or [])
        receipts: dict[str, dict[str, Any]] = dict(row.get('piece_receipts') or {})
        for segment_path in sorted(paths):
            if not await run_blocking(
                db_executor, cap_hold.renew, uid, snapshot.reference, row['lease_token'], time.time()
            ):
                return False
            name = Path(segment_path).name
            if name in processed:
                continue
            receipt: dict[str, Any] | None = receipts.get(name)
            if receipt is None:
                if not await run_blocking(db_executor, _new_dispatch_allowed, uid):
                    return False
                response = {'new_memories': set(), 'updated_memories': set()}
                errors, outcome = [], {}
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
                    target_conversation_id=targets.get(segment_path, meta.get('target_conversation_id')),
                    geolocation=geolocation,
                    source_position_map=source_maps.get(segment_path),
                    lineage_binding=bindings.get(segment_path, meta.get('lineage_binding')),
                    sync_lane=meta.get('sync_lane', 'fresh'),
                    cap_recovery=True,
                    deferred_outcome=outcome,
                )
                if errors or outcome.get('cap_held'):
                    return False
                seconds = await run_blocking(sync_executor, get_wav_duration, segment_path) if ok else 0
                receipt = {
                    'response': _stored(response),
                    'seconds': seconds,
                    'has_content': bool(ok),
                    'usage_metadata': {
                        'funding': 'omi',
                        'provider': outcome.get('provider') or 'unknown',
                        'source': 'sync_v2',
                    },
                }
                receipts[name] = receipt
                # Paid STT/content is now durable BEFORE usage or enrichment.
                # A settlement retry reuses this receipt without dispatching STT.
                if not await _save(uid, snapshot, row, {'piece_receipts': dict(receipts)}):
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
        response = _response(receipts)
        if receipts:
            # Ordinary sync finalizes the joined batch, not each VAD piece.
            await run_blocking(sync_executor, finalize_recovered_sync_segment, uid, response, bool(private))
        return await _save(uid, snapshot, row, {'finalized': True, 'recovery_response': _stored(response)})
    finally:
        await run_blocking(storage_executor, directory.cleanup)


def _settle_and_erase(uid: str, snapshot: Any, row: dict) -> None:
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
    _erase(uid, snapshot, row)


async def recover(uid: str) -> None:
    # One cheap distributed cooldown before querying usage or manifests. Failed
    # Redis means deferred recovery, never duplicate provider dispatch.
    acquired = await run_blocking(db_executor, cap_hold.recovery_cooldown, uid)
    if not acquired:
        return
    rows = await run_blocking(db_executor, cap_hold.pending_holds, uid)
    for snapshot in rows:
        row = snapshot.to_dict() or {}
        try:
            if row.get('state') == 'completed':
                await run_blocking(storage_executor, _settle_and_erase, uid, snapshot, row)
                continue
            row = await run_blocking(db_executor, cap_hold.claim, uid, snapshot.reference, time.time())
            if row is None:
                continue
            try:
                if await _recover_row(uid, snapshot, row):
                    if not await _save(uid, snapshot, row, {'state': 'completed'}):
                        continue
                    await run_blocking(storage_executor, _settle_and_erase, uid, snapshot, row)
            finally:
                await run_blocking(db_executor, cap_hold.release, uid, snapshot.reference, row['lease_token'])
        except Exception as error:
            logger.warning('event=stt_cap_recovery outcome=deferred exception_type=%s', type(error).__name__)


async def _schedule(uid: str) -> None:
    start_background_task(recover(uid), name='stt_cap_hold_recovery')


def kick(uid: str) -> None:
    if not enabled():
        return
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        from_thread.run(_schedule, uid)
    else:
        start_background_task(recover(uid), name='stt_cap_hold_recovery')

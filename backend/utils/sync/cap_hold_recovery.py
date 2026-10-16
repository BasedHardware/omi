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
from google.cloud import firestore
from google.api_core.exceptions import NotFound

from config.stt_cap_dispatch import enabled
from database import users as users_db
from utils.analytics import record_usage
from utils.executors import run_blocking, db_executor, sync_executor, storage_executor, start_background_task
from utils.stt_cap_dispatch import sync_allowed
from utils.sync import cap_hold
from utils.sync.files import get_wav_duration
from utils.sync.pipeline import (
    process_segment,
    retrieve_vad_segments,
    finalize_recovered_sync_segment,
)
from models.conversation import ConversationSource

logger = logging.getLogger(__name__)


def _erase(uid: str, snapshot: Any, row: dict[str, Any]) -> None:
    # Account deletion already purges this existing owner-scoped chunk prefix.
    path = row['audio_path']
    if not path.startswith(f'chunks/{uid}/cap-held/'):
        raise ValueError('hold audio owner mismatch')
    try:
        cap_hold.get_private_cloud_sync_bucket().blob(path).delete()
    except NotFound:
        pass
    snapshot.reference.delete()


async def _recover_row(uid: str, snapshot: Any, row: dict[str, Any]) -> bool:
    meta = await run_blocking(db_executor, cap_hold.metadata, uid, row)
    prefs = await run_blocking(db_executor, users_db.get_user_transcription_preferences, uid)
    private = await run_blocking(db_executor, users_db.get_user_private_cloud_sync_enabled, uid)
    protection = await run_blocking(db_executor, users_db.get_data_protection_level, uid) if private else None
    directory = await run_blocking(storage_executor, cap_hold.recovery_directory, uid)
    try:
        path = str(Path(directory.name) / f"{meta['timestamp']}.wav")
        await run_blocking(storage_executor, cap_hold.read_audio, uid, row, path)
        paths, errors = {path}, []
        if meta.get('full_capture'):
            paths = set()
            await run_blocking(sync_executor, retrieve_vad_segments, path, paths, errors)
            if errors:
                return False
        processed = set(row.get('processed_paths') or [])
        for segment_path in sorted(paths):
            if not await run_blocking(
                db_executor, cap_hold.renew, uid, snapshot.reference, row['lease_token'], time.time()
            ):
                return False
            name = Path(segment_path).name
            if name in processed:
                continue
            if not await run_blocking(db_executor, sync_allowed, uid):
                return False
            response = {'new_memories': set(), 'updated_memories': set()}
            outcome = {}
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
                private_cloud_sync_enabled=bool(private),
                data_protection_level=protection,
                client_device_id=meta.get('client_device_id'),
                client_platform=meta.get('client_platform'),
                target_conversation_id=meta.get('target_conversation_id'),
                cap_recovery=True,
                deferred_outcome=outcome,
            )
            if errors or outcome.get('cap_held'):
                return False
            if ok:
                await run_blocking(sync_executor, finalize_recovered_sync_segment, uid, response, bool(private))
                seconds = await run_blocking(sync_executor, get_wav_duration, segment_path)
                await run_blocking(
                    db_executor,
                    record_usage,
                    uid,
                    transcription_seconds=int(seconds),
                    speech_seconds=int(seconds),
                    idempotency_key=f'cap-hold-{snapshot.id}-{name}',
                    usage_metadata={'funding': 'omi', 'provider': 'unknown', 'source': 'sync_v2'},
                )
            await run_blocking(
                db_executor, snapshot.reference.update, {'processed_paths': firestore.ArrayUnion([name])}
            )
    finally:
        await run_blocking(storage_executor, directory.cleanup)
    return True


async def recover(uid: str) -> None:
    # One cheap distributed cooldown before querying usage or manifests. Failed
    # Redis means deferred recovery, never duplicate provider dispatch.
    acquired = await run_blocking(db_executor, cap_hold.recovery_cooldown, uid)
    if not acquired or not await run_blocking(db_executor, sync_allowed, uid):
        return
    rows = await run_blocking(db_executor, cap_hold.pending_holds, uid)
    for snapshot in rows:
        row = snapshot.to_dict() or {}
        try:
            if row.get('state') == 'completed':
                await run_blocking(storage_executor, _erase, uid, snapshot, row)
                continue
            row = await run_blocking(db_executor, cap_hold.claim, uid, snapshot.reference, time.time())
            if row is None:
                continue
            try:
                if await _recover_row(uid, snapshot, row):
                    await run_blocking(db_executor, snapshot.reference.update, {'state': 'completed'})
                    await run_blocking(storage_executor, _erase, uid, snapshot, row)
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

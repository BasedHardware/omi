"""Keep the live playback projection fresh without rediscovering its prefix per write."""

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List

from google.api_core.exceptions import InvalidArgument
from prometheus_client import Counter

from config import audio_archive
from database import conversations as conversations_db, conversation_tombstones
from database._client import get_firestore_client
from database.audio_chunk_metadata import audio_chunk_entry
from utils.other import storage
from utils.observability.fallback import record_fallback
from utils.executors import run_blocking, storage_executor
from utils.other.audio_outbox_metrics import record_failure
from utils.speaker_learning_jobs import schedule_person_voice_learning_retry

PROJECTIONS = Counter('omi_pusher_audio_file_projection_total', 'Pusher playback projection refreshes', ['mode'])
logger = logging.getLogger(__name__)
CLOSE_RETRY_BUDGET = 2
REFRESH_SECONDS = 300
MAX_CONVERSATIONS = 128
MAX_CHUNKS = 2048


def enabled() -> bool:
    return os.getenv('PUSHER_AUDIO_FILE_INCREMENTAL_ENABLED', '1').strip().lower() not in {'0', 'false', 'off'}


@dataclass
class Inventory:
    chunks: list[dict[str, Any]]
    files: list[dict[str, Any]]
    listed_at: float


def projection_owner_gone(uid: str, conversation_id: str) -> bool:
    """Deletion-intent read for a projection NotFound: owner gone, or live?

    Same tombstone read as the custody write gate (utils/other/storage.py);
    a missing conversation doc covers hard-deleted rows without a tombstone.
    Runs only on the NotFound arm, so live conversations pay no extra reads.
    """
    if conversation_tombstones.is_deleted(uid, conversation_id):
        return True
    doc = (
        get_firestore_client()
        .collection('users')
        .document(uid)
        .collection('conversations')
        .document(conversation_id)
        .get()
    )
    return not doc.exists


def get_uploaded_audio_chunks(uid: str, conversation_id: str, paths: List[str]) -> List[Dict[str, Any]]:
    """Read exact encoded objects; never discover siblings or raw archive packs.

    Regional objects win at duplicate paths, matching list_audio_chunks.
    A missing/unknown object refuses the incremental projection.
    """
    prefix = f'chunks/{uid}/{conversation_id}/'
    names = storage._chunk_bucket_names(storage.private_cloud_sync_bucket)
    chunks = []
    for path in dict.fromkeys(paths):
        if not path.startswith(prefix) or '/' in path[len(prefix) :]:
            raise ValueError('projection requires an encoded conversation chunk')
        entry = None
        for name in reversed(names):
            blob = storage._get_storage_client().bucket(name).get_blob(path)
            if blob is not None:
                entry = audio_chunk_entry(blob, source_identity=True, primary_bucket=storage.private_cloud_sync_bucket)
                break
        if entry is None or not entry.get('generation'):
            raise ValueError('projection chunk metadata unavailable')
        span = entry.get('span')
        if span and span['start'] != entry['timestamp']:
            entry['legacy_timestamp'] = entry['timestamp']
            entry['timestamp'] = span['start']
        chunks.append(entry)
    return chunks


class PusherAudioProjection:
    """Socket-owned metadata only. Loss, eviction and ambiguity mean full rebuild.

    Archive overlays can subtract/split encoded coverage and are not append-only.
    Keep their existing listing path until the manifest-first reader owns them.
    """

    def __init__(self, uid: str):
        self.uid = uid
        self.has_uploaded_paths = False
        self.close_debt: set[str] = set()
        self.finished: set[str] = set()
        self.close_retries: dict[str, int] = {}
        self.inventory: dict[str, Inventory | None] = {}

    def refresh(self, conversation_id: str, paths: list[str] | None = None, *, force: bool = False) -> bool | None:
        state = self.inventory.get(conversation_id)
        if not force:
            self.finished.discard(conversation_id)
        # A failed refresh keeps a close-time full rebuild due, but cannot
        # lend an old inventory to the next flush.
        self.has_uploaded_paths = self.has_uploaded_paths or bool(paths)
        if enabled() and len(self.close_debt) < MAX_CONVERSATIONS:
            self.close_debt.add(conversation_id)
        incremental = enabled() and (bool(paths) or force) and not audio_archive.admitted(self.uid, 'READ')
        if incremental and paths and (conversation_id in self.inventory or len(self.inventory) < MAX_CONVERSATIONS):
            self.inventory[conversation_id] = None
        now = time.monotonic()
        chunks = None
        expected = None
        if incremental and state is not None and paths and not force and now - state.listed_at < REFRESH_SECONDS:
            try:
                new_chunks = get_uploaded_audio_chunks(self.uid, conversation_id, paths)
                # A replay, overwrite or equal-clock sibling needs the full
                # listing order, including cross-bucket tie precedence.
                if all(chunk['timestamp'] > state.chunks[-1]['timestamp'] for chunk in new_chunks):
                    chunks = [*state.chunks, *sorted(new_chunks, key=lambda chunk: chunk['timestamp'])]
                    expected = state.files
            except Exception:
                # Point-read failures must rebuild, never silently reuse stale files.
                record_fallback(
                    component='pusher',
                    from_mode='incremental_audio_files',
                    to_mode='audio_file_listing',
                    reason='other',
                    outcome='recovered',
                )
        # One optimistic attempt, then a full rebuild if another writer changed
        # the document. No cache TTL is advanced by an incremental append.
        for _ in range(2):
            if chunks is None:
                if enabled():
                    # Snapshot before discovery: a full rebuild must not
                    # overwrite a projection another pod publishes during LIST.
                    owner = conversations_db.get_conversation_raw_snapshot(
                        self.uid, conversation_id, field_paths=['audio_files', 'deleted']
                    )
                    if owner is None or owner.get('deleted'):
                        self.inventory.pop(conversation_id, None)
                        return False
                    expected = owner.get('audio_files') or []
                else:
                    expected = None
                if incremental and paths:
                    chunks = storage.list_audio_chunks(self.uid, conversation_id, source_identity=True)
                    files = conversations_db.create_audio_files_from_chunks(
                        self.uid, conversation_id, listed_chunks=chunks
                    )
                else:
                    files = conversations_db.create_audio_files_from_chunks(self.uid, conversation_id)
                listed_at = time.monotonic()
                mode = 'full'
            else:
                files = conversations_db.create_audio_files_from_chunks(self.uid, conversation_id, listed_chunks=chunks)
                listed_at = state.listed_at
                mode = 'incremental'
            PROJECTIONS.labels(mode=mode).inc()
            if not files:
                if not enabled():
                    owner = conversations_db.get_conversation_raw_snapshot(
                        self.uid, conversation_id, field_paths=['deleted']
                    )
                    if owner is None or owner.get('deleted'):
                        return False
                return None
            payload = [af.model_dump() for af in files]
            try:
                if expected is None:
                    applied = conversations_db.update_conversation(self.uid, conversation_id, {'audio_files': payload})
                else:
                    applied = conversations_db.update_conversation(
                        self.uid, conversation_id, {'audio_files': payload}, expected_audio_files=expected
                    )
            except conversations_db.AudioFilesChanged:
                chunks = None
                continue
            if (
                applied
                and incremental
                and chunks
                and len(chunks) + sum(len(item.chunks) for item in self.inventory.values() if item is not None)
                <= MAX_CHUNKS
                and all(af.get('source_fingerprint') for af in payload)
                and all(chunk.get('span') and chunk.get('is_batch') and chunk.get('generation') for chunk in chunks)
                and (conversation_id in self.inventory or len(self.inventory) < MAX_CONVERSATIONS)
            ):
                self.inventory[conversation_id] = Inventory(chunks, payload, listed_at)
            else:
                self.inventory.pop(conversation_id, None)
            return applied
        raise RuntimeError('audio projection refresh exhausted')

    def finish(self, conversation_id: str) -> bool | None:
        if not enabled() or not self.has_uploaded_paths or conversation_id in self.finished:
            return None  # Rollback/unknown writer retains per-flush-only behavior.
        result = self.refresh(conversation_id, force=True)
        self.inventory.pop(conversation_id, None)
        self.close_debt.discard(conversation_id)
        if len(self.finished) < MAX_CONVERSATIONS:
            self.finished.add(conversation_id)
        return result

    async def finish_pending(self, conv_id: str, deleted_conversations: set[str], identity_refreshed: set[str]) -> bool:
        if conv_id in deleted_conversations:
            self.inventory.pop(conv_id, None)
            self.close_debt.discard(conv_id)
            return True
        try:
            applied = await run_blocking(storage_executor, self.finish, conv_id)
        except Exception as exc:
            # A close-time discovery failure must not escape into websocket
            # supervision (or expose SDK messages containing private paths).
            # Retry optional projection work, never the already committed PCM.
            attempts = self.close_retries.get(conv_id, 0)
            if not isinstance(exc, InvalidArgument) and attempts < CLOSE_RETRY_BUDGET:
                self.close_retries[conv_id] = attempts + 1
                logger.warning('Close audio projection rebuild deferred exception_type=%s', type(exc).__name__)
                return False
            self.close_retries.pop(conv_id, None)
            self.inventory.pop(conv_id, None)
            self.close_debt.discard(conv_id)
            if len(self.finished) < MAX_CONVERSATIONS:
                self.finished.add(conv_id)
            record_failure('projection', reason='invalid_argument' if isinstance(exc, InvalidArgument) else 'transient')
            record_fallback(
                component='pusher',
                from_mode='private_cloud_sync',
                to_mode='raw_audio',
                reason='other',
                outcome='degraded',
                log=logger,
            )
            # The per-flush projection and raw receipt remain authoritative;
            # optional rediscovery failure cannot turn a clean drain into loss.
            return True
        self.close_retries.pop(conv_id, None)
        if applied:
            schedule_person_voice_learning_retry(self.uid, conv_id)
            if len(identity_refreshed) < 128:
                identity_refreshed.add(conv_id)
        elif applied is False:
            deleted_conversations.add(conv_id)
        return True

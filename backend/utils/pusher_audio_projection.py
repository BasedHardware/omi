"""Keep the live playback projection fresh without rediscovering its prefix per write."""

import os
import time
from dataclasses import dataclass
from typing import Any

from prometheus_client import Counter

from config import audio_archive
from database import conversations as conversations_db
from utils.other import storage
from utils.observability.fallback import record_fallback

PROJECTIONS = Counter('omi_pusher_audio_file_projection_total', 'Pusher playback projection refreshes', ['mode'])
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


class PusherAudioProjection:
    """Socket-owned metadata only. Loss, eviction and ambiguity mean full rebuild.

    Archive overlays can subtract/split encoded coverage and are not append-only.
    Keep their existing listing path until the manifest-first reader owns them.
    """

    def __init__(self, uid: str):
        self.uid = uid
        self.inventory: dict[str, Inventory | None] = {}

    def refresh(self, conversation_id: str, paths: list[str] | None = None, *, force: bool = False) -> bool | None:
        state = self.inventory.get(conversation_id)
        # A failed refresh keeps a close-time full rebuild due, but cannot
        # lend an old inventory to the next flush.
        if conversation_id in self.inventory or len(self.inventory) < MAX_CONVERSATIONS:
            self.inventory[conversation_id] = None
        incremental = enabled() and not audio_archive.admitted(self.uid, 'READ')
        now = time.monotonic()
        chunks = None
        expected = None
        if incremental and state is not None and paths and not force and now - state.listed_at < REFRESH_SECONDS:
            try:
                new_chunks = storage.get_uploaded_audio_chunks(self.uid, conversation_id, paths)
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
                if incremental and paths:
                    chunks = storage.list_audio_chunks(self.uid, conversation_id, source_identity=True)
                    files = conversations_db.create_audio_files_from_chunks(
                        self.uid, conversation_id, listed_chunks=chunks
                    )
                else:
                    files = conversations_db.create_audio_files_from_chunks(self.uid, conversation_id)
                expected = None
                listed_at = time.monotonic()
                mode = 'full'
            else:
                files = conversations_db.create_audio_files_from_chunks(self.uid, conversation_id, listed_chunks=chunks)
                listed_at = state.listed_at
                mode = 'incremental'
            PROJECTIONS.labels(mode=mode).inc()
            if not files:
                if incremental and paths:
                    # Even an empty projection must not hide a deleted owner.
                    owner = conversations_db.get_conversation_raw_snapshot(
                        self.uid, conversation_id, field_paths=['deleted']
                    )
                    if owner is None or owner.get('deleted'):
                        self.inventory.pop(conversation_id, None)
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
                and (conversation_id in self.inventory or len(self.inventory) < MAX_CONVERSATIONS)
            ):
                self.inventory[conversation_id] = Inventory(chunks, payload, listed_at)
            else:
                self.inventory.pop(conversation_id, None)
            return applied
        raise RuntimeError('audio projection refresh exhausted')

    def finish(self, conversation_id: str) -> bool | None:
        if conversation_id not in self.inventory:
            return None  # Every non-cached flush already did a full rebuild.
        result = self.refresh(conversation_id, force=True)
        self.inventory.pop(conversation_id, None)
        return result

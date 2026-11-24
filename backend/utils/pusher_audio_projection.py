"""Keep the live playback projection fresh without rediscovering its prefix per write."""

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List

from google.api_core.exceptions import InvalidArgument
from prometheus_client import Counter

from config import audio_archive
from config.pusher_record import close_fast_path_enabled
from config.batch_pipeline_projection_rebuild import enabled as durable_debt_enabled
from database import conversations as conversations_db, record_projection_rebuild
from database.audio_chunk_metadata import audio_chunk_entry
from utils.other.private_sync_get_metrics import Reader, object_get_reader
from utils.other import storage
from utils.batch_pipeline.record_projection_rebuild import (
    projected_chunks,
    discover,
)
from utils.observability.fallback import record_fallback
from utils.executors import run_blocking, storage_executor, playback_debt_executor, db_executor, start_background_task
from utils.other.audio_outbox_metrics import record_failure
from utils.speaker_learning_jobs import schedule_person_voice_learning_retry

PROJECTIONS = Counter('omi_pusher_audio_file_projection_total', 'Pusher playback projection refreshes', ['mode'])
# Why a refresh paid for a full prefix discovery. Closed values; one increment
# per full discovery, so the sum equals the mode="full" count above.
FULL_CAUSES = (
    'disabled',
    'forced',
    'no_paths',
    'no_inventory',
    'listing_expired',
    'point_read_failed',
    'order_fallback',
    'projection_error',
    'cas_conflict',
)
FULL_DISCOVERIES = Counter(
    'omi_pusher_audio_file_full_discovery_total', 'Pusher playback full discoveries by cause', ['cause']
)
for _cause in FULL_CAUSES:
    FULL_DISCOVERIES.labels(cause=_cause)
logger = logging.getLogger(__name__)
CLOSE_RETRY_BUDGET = 2
REFRESH_SECONDS = 300
MAX_CONVERSATIONS = 128
MAX_CHUNKS = 2048
MAX_MARKER_RETRIES = record_projection_rebuild.MAX_MARKERS_PER_BATCH
MARKER_CLOSE_SECONDS = 3.0
MARKER_ATTEMPT_SECONDS = 1.25
MARKER_WRITES = Counter('omi_pusher_projection_debt_total', 'Best-effort projection marker handoffs', ['outcome'])


def enabled() -> bool:
    return os.getenv('PUSHER_AUDIO_FILE_INCREMENTAL_ENABLED', '1').strip().lower() not in {'0', 'false', 'off'}


@dataclass
class Inventory:
    chunks: list[dict[str, Any]]
    files: list[dict[str, Any]]
    listed_at: float


@object_get_reader(Reader.PLAYBACK_INVENTORY)
def get_uploaded_audio_chunks(uid: str, conversation_id: str, paths: List[str]) -> List[Dict[str, Any]]:
    """Read exact encoded objects; never discover siblings or raw archive packs.

    Regional objects win at duplicate paths, matching list_audio_chunks.
    A missing/unknown object refuses the incremental projection.
    """
    prefix = f'chunks/{uid}/{conversation_id}/'
    names = list(
        dict.fromkeys(
            name for name in (storage.private_cloud_sync_bucket, os.getenv('BUCKET_AUDIO_DERIVED', '').strip()) if name
        )
    )
    chunks = []
    for path in dict.fromkeys(paths):
        if path.startswith(f'raw-live/{uid}/{conversation_id}/') and audio_archive.admitted(uid, 'READ'):
            continue  # The existing pack index supplies authoritative raw spans.
        if not path.startswith(prefix) or '/' in path[len(prefix) :]:
            raise ValueError('projection requires an encoded conversation chunk')
        entry = None
        for name in reversed(names):
            blob = storage.chunk_source_bucket(name).get_blob(path)
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

    Cache encoded inventory only. Recompute raw coverage overlays from the
    existing pack index every flush; those fragments are not append-only.
    """

    def __init__(self, uid: str, *, on_refresh=None):
        self.uid = uid
        self.on_refresh = on_refresh
        self.has_uploaded_paths = False
        self.close_debt: set[str] = set()
        # Separate metadata-only overflow inventory; never retain PCM receipts
        # or gate recording completion on optional marker persistence.
        self.marker_retry: dict[str, int] = {}
        self.marker_sequence = 0
        self.marker_task: asyncio.Task | None = None
        self.finished: set[str] = set()
        self.close_retries: dict[str, int] = {}
        self.inventory: dict[str, Inventory | None] = {}
        self.defer_metadata = False
        self.durable_debt: set[str] = set()
        self.debt_versions: dict[str, Any] = {}

    def refresh(self, conversation_id: str, paths: list[str] | None = None, *, force: bool = False) -> bool | None:
        state = self.inventory.pop(conversation_id, None)
        self.finished.discard(conversation_id)
        # A failed refresh keeps a close-time full rebuild due, but cannot
        # lend an old inventory to the next flush.
        self.has_uploaded_paths = self.has_uploaded_paths or bool(paths)
        if enabled() and len(self.close_debt) < MAX_CONVERSATIONS:
            self.close_debt.add(conversation_id)
        incremental = enabled() and (bool(paths) or force)
        if incremental and paths and (conversation_id in self.inventory or len(self.inventory) < MAX_CONVERSATIONS):
            self.inventory[conversation_id] = None
        now = time.monotonic()
        chunks = None
        expected = None
        listed_at = now
        if not enabled():
            cause = 'disabled'
        elif force:
            cause = 'forced'
        elif not paths:
            cause = 'no_paths'
        elif state is None:
            cause = 'no_inventory'
        elif now - state.listed_at >= REFRESH_SECONDS:
            cause = 'listing_expired'
        else:
            cause = 'order_fallback'
        if incremental and state is not None and paths and not force and now - state.listed_at < REFRESH_SECONDS:
            try:
                new_chunks = get_uploaded_audio_chunks(self.uid, conversation_id, paths)
                # A replay, overwrite or equal-clock sibling needs the full
                # listing order, including cross-bucket tie precedence.
                if all(not state.chunks or chunk['timestamp'] > state.chunks[-1]['timestamp'] for chunk in new_chunks):
                    chunks = [*state.chunks, *sorted(new_chunks, key=lambda chunk: chunk['timestamp'])]
                    expected = state.files
                    listed_at = state.listed_at
            except Exception:
                # Point-read failures must rebuild, never silently reuse stale files.
                cause = 'point_read_failed'
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
            raw_complete = True
            if chunks is None:
                if enabled():
                    discovery = discover(
                        self.uid,
                        conversation_id,
                        strict_raw=force and durable_debt_enabled(),
                        fallback=record_fallback,
                        reuse_manifest_bodies=not force,
                    )
                    if discovery is None:
                        self.inventory.pop(conversation_id, None)
                        return False
                    expected, chunks, files, raw_complete = discovery
                else:
                    expected = None
                    files = conversations_db.create_audio_files_from_chunks(self.uid, conversation_id)
                listed_at = time.monotonic()
                mode = 'full'
                FULL_DISCOVERIES.labels(cause=cause).inc()
            else:
                # Raw fragments can shrink or split as encoded coverage grows;
                # re-derive them, never append yesterday's projected fragments.
                try:
                    listed = projected_chunks(self.uid, conversation_id, chunks, reuse_manifest_bodies=True)
                except Exception:
                    # An incremental encoded view is not a full fallback.
                    # Rediscover encoded siblings before matching main's
                    # raw-index failure behavior.
                    chunks = None
                    cause = 'projection_error'
                    continue
                files = conversations_db.create_audio_files_from_chunks(self.uid, conversation_id, listed_chunks=listed)
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
                cause = 'cas_conflict'
                continue
            if (
                applied
                and raw_complete
                and incremental
                and chunks is not None
                and sum(len(af.get('chunk_timestamps') or []) for af in payload)
                + sum(
                    sum(len(af.get('chunk_timestamps') or []) for af in item.files)
                    for item in self.inventory.values()
                    if item is not None
                )
                <= MAX_CHUNKS
                and all(af.get('source_fingerprint') for af in payload)
                and all(chunk.get('span') and chunk.get('is_batch') and chunk.get('generation') for chunk in chunks)
                and (conversation_id in self.inventory or len(self.inventory) < MAX_CONVERSATIONS)
            ):
                self.inventory[conversation_id] = Inventory(chunks, payload, listed_at)
            else:
                self.inventory.pop(conversation_id, None)
            if applied and force and enabled():
                # A closing batch already rebuilt the prefix: its close scan
                # must not immediately repeat that same full discovery.
                self.close_debt.discard(conversation_id)
                self.inventory.pop(conversation_id, None)
                if len(self.finished) < MAX_CONVERSATIONS:
                    self.finished.add(conversation_id)
            return applied
        raise RuntimeError('audio projection refresh exhausted')

    def finish(self, conversation_id: str) -> bool | None:
        if not enabled() or not self.has_uploaded_paths or conversation_id in self.finished:
            return None  # Rollback/unknown writer retains per-flush-only behavior.
        result = self.refresh(conversation_id, force=True)
        self.inventory.pop(conversation_id, None)
        if result is None and durable_debt_enabled():
            return None  # Empty discovery cannot discharge the close obligation.
        self.close_debt.discard(conversation_id)
        if len(self.finished) < MAX_CONVERSATIONS:
            self.finished.add(conversation_id)
        return result

    async def finish_pending(self, conv_id: str, deleted_conversations: set[str], identity_refreshed: set[str]) -> bool:
        if conv_id in deleted_conversations:
            self.inventory.pop(conv_id, None)
            self.close_debt.discard(conv_id)
            return True
        if self.defer_metadata:
            return await self.defer_rebuild(conv_id)
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
            queued = await self.defer_rebuild(conv_id)
            self.close_retries.pop(conv_id, None)
            self.inventory.pop(conv_id, None)
            if queued:
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
        if applied is None and self.has_uploaded_paths and conv_id in self.close_debt and durable_debt_enabled():
            if await self.defer_rebuild(conv_id):
                self.close_debt.discard(conv_id)
            if len(self.finished) < MAX_CONVERSATIONS:
                self.finished.add(conv_id)
        self.close_retries.pop(conv_id, None)
        if applied:
            schedule_person_voice_learning_retry(self.uid, conv_id)
            if len(identity_refreshed) < 128:
                identity_refreshed.add(conv_id)
        elif applied is False:
            deleted_conversations.add(conv_id)
        return True

    async def defer_close_refresh(self, conv_id: str, paths=None, *, closing: bool = True) -> bool:
        """Write debt before optional discovery; capacity overflow stays cold debt."""
        from utils.pusher_playback_coordinator import coordinator

        # Completion deduplicates pathless scans, never a newly uploaded batch.
        # A prior refresh may already have retired that batch's durable marker.
        if paths or not closing:
            self.finished.discard(conv_id)
        if closing and not paths and conv_id in self.finished and conv_id in self.durable_debt:
            return True
        if not durable_debt_enabled():
            return False
        self.defer_metadata = True
        if paths:
            self.durable_debt.discard(conv_id)  # A new upload needs a new durable request.
            self.debt_versions.pop(conv_id, None)
        if not await self.defer_rebuild(conv_id):
            return False
        admitted = coordinator().submit(
            self.uid,
            conv_id,
            paths,
            closing,
            self.on_refresh,
            observed_update_time=self.debt_versions.get(conv_id),
        )
        if not admitted:
            record_fallback(
                component='pusher',
                from_mode='playback_metadata',
                to_mode='durable_repair',
                reason='capacity_full',
                outcome='degraded',
                log=logger,
            )
        self.inventory.pop(conv_id, None)
        self.has_uploaded_paths = True
        if closing and len(self.finished) < MAX_CONVERSATIONS:
            self.finished.add(conv_id)
        return True

    async def defer_rebuild(self, conv_id: str) -> bool:
        """Success means a committed write, never only a scheduled task."""
        if not durable_debt_enabled():
            return True
        if not close_fast_path_enabled():
            return self._defer_rebuild_legacy(conv_id)
        if conv_id in self.durable_debt:
            return True
        if conv_id not in self.marker_retry and len(self.marker_retry) >= MAX_MARKER_RETRIES - MAX_CONVERSATIONS:
            MARKER_WRITES.labels(outcome='marker_retry_overflow').inc()
            return False
        self.marker_sequence += 1
        self.marker_retry[conv_id] = self.marker_sequence
        try:
            async with asyncio.timeout(MARKER_ATTEMPT_SECONDS):
                versions = await run_blocking(
                    playback_debt_executor, record_projection_rebuild.mark_many, self.uid, {conv_id}
                )
        except Exception as exc:
            MARKER_WRITES.labels(outcome='marker_write_failed').inc()
            logger.warning('Projection marker_write_failed exception_type=%s', type(exc).__name__)
            return False
        self.marker_retry.pop(conv_id, None)
        self._remember_durable_debt(conv_id, versions)
        self.close_debt.discard(conv_id)
        MARKER_WRITES.labels(outcome='persisted').inc()
        return True

    def _remember_durable_debt(self, cid: str, versions) -> None:
        # Metadata ACKs are a cache, not custody authority. Reclaim an old ACK
        # rather than refusing every new recording after an all-day stream.
        if MAX_CONVERSATIONS <= 0:
            return
        if cid not in self.durable_debt and len(self.durable_debt) >= MAX_CONVERSATIONS:
            old = next(iter(self.durable_debt))
            self.durable_debt.discard(old)
            self.debt_versions.pop(old, None)
        self.durable_debt.add(cid)
        if type(versions) is dict and (version := versions.get(cid)) is not None:
            self.debt_versions[cid] = version

    def _defer_rebuild_legacy(self, conv_id: str) -> bool:
        """Original optional-debt handoff, unchanged with fast closure disabled."""
        if not durable_debt_enabled():
            return True
        if conv_id not in self.marker_retry and len(self.marker_retry) >= MAX_MARKER_RETRIES - MAX_CONVERSATIONS:
            MARKER_WRITES.labels(outcome='marker_retry_overflow').inc()
            logger.error('Projection debt retry inventory full; optional marker handoff refused')
            return False
        self.marker_sequence += 1
        self.marker_retry[conv_id] = self.marker_sequence
        self._start_marker_task()
        return True

    def _start_marker_task(self) -> None:
        if self.marker_retry and (self.marker_task is None or self.marker_task.done()):
            self.marker_task = start_background_task(self._persist_markers(), name='projection-debt-handoff')

    async def _persist_markers(self) -> None:
        # At most two batched RPCs, including executor queue time. A late SDK
        # commit is metadata-only, idempotent and has its own one-second timeout.
        for _ in range(2):
            pending = dict(self.marker_retry)
            if not pending:
                return
            try:
                async with asyncio.timeout(MARKER_ATTEMPT_SECONDS):
                    versions = await run_blocking(
                        playback_debt_executor if close_fast_path_enabled() else db_executor,
                        record_projection_rebuild.mark_many,
                        self.uid,
                        set(pending),
                    )
            except Exception as exc:
                MARKER_WRITES.labels(outcome='marker_write_failed').inc()
                logger.warning('Projection marker_write_failed exception_type=%s', type(exc).__name__)
                continue
            for cid, sequence in pending.items():
                if self.marker_retry.get(cid) == sequence:
                    self.marker_retry.pop(cid, None)
                    self.close_debt.discard(cid)
                    if close_fast_path_enabled():
                        self._remember_durable_debt(cid, versions)
            MARKER_WRITES.labels(outcome='persisted').inc(len(pending))

    async def persist_pending(self) -> None:
        """Total socket-cleanup budget, independent of the number of debts."""
        if not durable_debt_enabled():
            self.close_debt.clear()
            self.marker_retry.clear()
            return
        for cid in self.close_debt:
            if cid not in self.marker_retry:
                self.marker_sequence += 1
                self.marker_retry[cid] = self.marker_sequence
        self._start_marker_task()
        if self.marker_task is None and not self.defer_metadata:
            return
        try:
            async with asyncio.timeout(MARKER_CLOSE_SECONDS):
                if self.defer_metadata:
                    from utils.pusher_playback_coordinator import coordinator

                    await coordinator().wait_owner(self.uid)
                for attempt in range(2):
                    self._start_marker_task()
                    if self.marker_task is not None:
                        await asyncio.shield(self.marker_task)
                    if not self.marker_retry or attempt == 1:
                        break
                    self._start_marker_task()
        except TimeoutError:
            MARKER_WRITES.labels(outcome='marker_write_failed').inc()
            logger.warning('Projection marker_write_failed cleanup_budget_exhausted')
            if self.defer_metadata:
                record_fallback(
                    component='pusher',
                    from_mode='playback_metadata',
                    to_mode='durable_repair',
                    reason='timeout',
                    outcome='degraded',
                    log=logger,
                )
        # Background work is bounded independently; socket close never waits
        # for a second round after the total cleanup budget expires.

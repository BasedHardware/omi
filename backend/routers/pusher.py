import hashlib
import struct
import asyncio
import time
import uuid
from collections import deque
from typing import Any, Awaitable, Deque, Dict, List, Optional, Tuple, cast
from config.batch_pipeline import live_record_admission_enabled
from config.audio_outbox import enabled as audio_outbox_enabled

from fastapi import APIRouter
from fastapi.websockets import WebSocketDisconnect, WebSocket
from starlette.websockets import WebSocketState

import database.conversations as conversations_db
from database import users as users_db
from database.legal_holds import DestructiveOperationInProgress
from utils.conversations.speaker_identity_retry import schedule_completed_identity_retries
from utils.pusher_finalization import FINALIZATION_RESULT_PROTOCOL_LEGACY, process_conversation_task
from utils.pusher_protocol import (
    BUFFERED_AUDIO_MAX_BYTES,
    MAX_SAMPLE_RATE,
    MIN_SAMPLE_RATE,
    PRIVATE_CLOUD_QUEUE_MAX_SIZE,
    AUDIO_TIMELINE_PROTOCOL,
    AudioBytesQueueItem,
    ByteBudget,
    PrivateCloudChunk,
    PrivateCloudSpan,
    SpeakerSampleRequest,
    TranscriptQueueItem,
    append_bounded,
    audio_timeline_ack_frame,
    audio_custody_ack_frame,
    bound_private_pending,
    extend_bounded,
    frame_header,
    json_object,
    pusher_session_outcome,
)
from utils.apps import is_audio_bytes_app_enabled
from utils.app_integrations import (
    trigger_realtime_integrations,
    trigger_realtime_audio_bytes,
)
from utils.executors import db_executor, storage_executor, run_blocking, start_background_task
from utils.episodes.live import on_session_end as flush_episode_moment
from utils.async_tasks import (
    supervise_tasks,
    drain_tasks,
    create_named_task,
    wait_for_event,
)
from utils.webhooks import (
    send_audio_bytes_developer_webhook,
    realtime_transcript_webhook,
    get_audio_bytes_webhook_seconds,
)
from utils.other.storage import upload_audio_chunks_batch
from utils.other.audio_outbox import AudioReceipt, AudioProjection, commit_pcm, read_pcm
from utils.other.audio_outbox_metrics import BACKPRESSURE, record_failure, record_would_drop
from utils.journey_metrics_contract import ClientKind, bounded_client_kind
from utils.metrics import (
    OMI_AUDIO_TIMELINE_CHUNKS_WRITTEN_TOTAL,
    OMI_AUDIO_TIMELINE_REPLAY_CONFLICTS_TOTAL,
    PUSHER_ACTIVE_WS_CONNECTIONS,
    PUSHER_PRIVATE_CLOUD_UPLOAD_DROPS,
    PUSHER_RECONCILE_LISTS_SKIPPED_TOTAL,
    PUSHER_SILENT_RUN_FLUSHES_SKIPPED_TOTAL,
)
from utils.readiness import ReadinessGate
from utils.observability.fallback import record_fallback
from utils.observability.journeys import JourneyAttempt
from utils.speaker_learning_jobs import run_authorized_person_learning, schedule_person_voice_learning_retry
import logging

from config.rollout_cohorts import warm_rollout_cohorts

logger = logging.getLogger(__name__)

router = APIRouter()


def _parse_finalization_result_protocol(value: Any) -> int:
    """Return the result capability, defaulting callers to the legacy wire contract."""
    if value is None:
        return FINALIZATION_RESULT_PROTOCOL_LEGACY
    if isinstance(value, bool) or not isinstance(value, int) or value < FINALIZATION_RESULT_PROTOCOL_LEGACY:
        raise ValueError('finalization_result_protocol must be a positive integer')
    return value


# Constants for speaker sample extraction
SPEAKER_SAMPLE_PROCESS_INTERVAL = 15.0
SPEAKER_SAMPLE_MIN_AGE = 120.0

# Constants for private cloud sync
PRIVATE_CLOUD_SYNC_PROCESS_INTERVAL = 1.0
PRIVATE_CLOUD_CHUNK_DURATION = 60.0
PRIVATE_CLOUD_BATCH_MAX_AGE = 60.0  # seconds — flush batch if oldest chunk exceeds this age
PRIVATE_CLOUD_SYNC_MAX_RETRIES = 3
# Audio-timeline v2 continuity: 1 ms filename-rounding tolerance. A positive
# discontinuity beyond it flushes the partial chunk and pending batch; an
# overlap is trimmed (or an exact replay ignored); conflicting bytes for the
# same range fail closed and are never overwritten.
AUDIO_TIMELINE_CONTINUITY_TOLERANCE = 0.001

# Queue size limits
SPEAKER_SAMPLE_QUEUE_WARN_SIZE = 100

# Bounded ledger of recently flushed v2 runs: (start_wall, end_wall, sha256 of
# the flushed bytes). An overlapping replay whose conflict window reaches past
# the live buffer can only be reconciled against these digests; anything the
# ledger no longer covers fails closed. 64 runs bounds the memory (~200 B)
# while covering over an hour of 60 s chunks.
V2_FLUSHED_RUN_LEDGER_SIZE = 64

# Constants for transcript queue batching
TRANSCRIPT_QUEUE_FLUSH_INTERVAL = 1.0  # seconds
TRANSCRIPT_QUEUE_WARN_SIZE = 50

# Constants for audio bytes queue
AUDIO_BYTES_QUEUE_WARN_SIZE = 20

# Receive timeout: if no data arrives for this long, the connection is considered dead.
# Backend-listen sends heartbeats every ~30s, so 5 minutes without ANY data means the
# upstream connection is gone.  Without this, half-open TCP connections hang forever,
# leaking the gauge + ~15 MB per ghost connection.
WS_RECEIVE_TIMEOUT = 300.0  # seconds

# After receive_task exits, background tasks get this long to drain their queues
# before being force-cancelled.  Prevents hung GCS uploads or webhook calls from
# blocking cleanup indefinitely.
BG_DRAIN_TIMEOUT = 30.0  # seconds


async def _dispatch_transcript_item(
    uid: str, segments: List[Dict[str, Any]], memory_id: Optional[str], client_kind: ClientKind = 'unknown'
) -> None:
    async def run(sink: str, call: Awaitable[Any]) -> None:
        try:
            await call
        except Exception as e:
            logger.error('Error processing transcript %s type=%s uid=%s', sink, type(e).__name__, uid)

    await asyncio.gather(
        run('integrations', trigger_realtime_integrations(uid, segments, memory_id, client_kind=client_kind)),
        run('webhook', realtime_transcript_webhook(uid, segments, client_kind=client_kind)),
    )


async def _websocket_util_trigger(
    websocket: WebSocket,
    uid: str,
    sample_rate: int = 8000,
    client_kind: str = 'unknown',
    audio_timeline: Optional[int] = None,
    audio_custody: Optional[int] = None,
) -> None:
    logger.info(f'_websocket_util_trigger {uid}')
    resolved_client_kind = bounded_client_kind(client_kind)

    try:
        await websocket.accept()
    except RuntimeError as e:
        logger.error(e)
        await websocket.close(code=1011, reason="Dirty state")
        return

    if not MIN_SAMPLE_RATE <= sample_rate <= MAX_SAMPLE_RATE:
        await websocket.close(code=1008, reason='Invalid sample rate')
        return
    if audio_custody not in (None, 1):
        await websocket.close(code=1008, reason='Unsupported audio custody version')
        return

    # Audio-timeline v2 opt-in: only acknowledged connections get v2
    # continuity handling. The acknowledgment is sent before any other frame
    # so the listen side consumes it in its connect path; an old listen that
    # never sent the query parameter sees nothing change.
    audio_timeline_v2 = False
    if audio_timeline is not None:
        if isinstance(audio_timeline, bool) or audio_timeline != AUDIO_TIMELINE_PROTOCOL:
            await websocket.close(code=1008, reason='Unsupported audio timeline version')
            return
        audio_timeline_v2 = True
        try:
            await websocket.send_bytes(audio_timeline_ack_frame())
        except Exception as e:
            logger.error(f'Failed to send audio timeline ack: {e} {uid}')
            return

    # Defense-in-depth: during drain the LB should already have removed us from
    # the NEG, but reject straggler NEW connections.  We accept the handshake
    # FIRST so the client sees a clean WS close frame (1001 Going Away) rather
    # than a failed HTTP upgrade — a pre-accept close is surfaced as an
    # exception by the websockets client and recorded as a circuit-breaker
    # failure in backend-listen (backend/utils/pusher.py), which can trip the
    # pod's pusher circuit during a normal rollout.
    if not ReadinessGate.is_serving():
        logger.info(f'Rejecting new WS for {uid}: pusher is draining')
        await websocket.close(code=1001)
        return

    await warm_rollout_cohorts(uid)
    journey_attempt = JourneyAttempt('pusher_session')
    websocket_active = True
    shutdown_event = asyncio.Event()
    websocket_close_code = 1000
    application_failed = False

    try:
        # audio bytes
        audio_bytes_webhook_delay_seconds = await run_blocking(db_executor, get_audio_bytes_webhook_seconds, uid)
        audio_bytes_trigger_delay_seconds = 4
        has_audio_apps_enabled = await run_blocking(db_executor, is_audio_bytes_app_enabled, uid)
        private_cloud_sync_enabled = await run_blocking(db_executor, users_db.get_user_private_cloud_sync_enabled, uid)
        cached_protection_level = (
            (await run_blocking(db_executor, users_db.get_data_protection_level, uid))
            if private_cloud_sync_enabled
            else None
        )
    except asyncio.CancelledError:
        journey_attempt.finish('cancelled')
        raise
    except Exception:
        journey_attempt.finish('failure')
        raise

    # Bounded queues — prevent unbounded memory growth during backpressure
    speaker_sample_queue: deque[SpeakerSampleRequest] = deque(maxlen=SPEAKER_SAMPLE_QUEUE_WARN_SIZE)
    transcript_queue: deque[TranscriptQueueItem] = deque(maxlen=TRANSCRIPT_QUEUE_WARN_SIZE)
    audio_bytes_queue: deque[AudioBytesQueueItem] = deque(maxlen=AUDIO_BYTES_QUEUE_WARN_SIZE)

    # private_cloud_queue caps at PRIVATE_CLOUD_QUEUE_MAX_SIZE to prevent OOM kills.
    # An OOM kill loses ALL queued data for ALL users on the pod — dropping the oldest
    # chunk for one user is strictly better than killing the pod.
    private_cloud_queue: deque[PrivateCloudChunk] = deque(maxlen=PRIVATE_CLOUD_QUEUE_MAX_SIZE)
    audio_bytes_event = asyncio.Event()  # Signals when items are added for instant wake
    audio_budget = ByteBudget(BUFFERED_AUDIO_MAX_BYTES)
    durable_audio = audio_outbox_enabled()
    # The bounded lane holds generation-pinned references, never the only PCM.
    # A crash after commit but before queue.put is recoverable via raw-live's
    # existing per-conversation playback index, independent of this process.
    durable_queue: asyncio.Queue[AudioProjection] = asyncio.Queue(maxsize=PRIVATE_CLOUD_QUEUE_MAX_SIZE)
    custody_root = uuid.uuid4().hex
    custody_sequence = 0

    async def archive_private_audio(
        audio_data: bytes, timestamp: float, conversation_id: Optional[str]
    ) -> Optional[AudioReceipt]:
        nonlocal custody_sequence
        if not (durable_audio and private_cloud_sync_enabled and audio_data):
            return None
        # Before overlap trimming or lossy derivatives. An audio ACK requires
        # both remote objects; a failed commit leaves the producer unacknowledged.
        receipt = await run_blocking(
            storage_executor,
            commit_pcm,
            uid,
            bytes(audio_data),
            conversation_id,
            timestamp,
            sample_rate,
            custody_root,
            custody_sequence,
            data_protection_level=cached_protection_level,
            clock_source='server_projected' if audio_timeline_v2 else 'arrival_estimate',
        )
        custody_sequence += 1
        if audio_custody == 1:
            await websocket.send_bytes(audio_custody_ack_frame(receipt.to_dict()))
        return receipt

    async def queue_private_projection(receipt: Optional[AudioReceipt], start: float, samples: int) -> None:
        if receipt is not None and receipt.conversation_id and samples:
            if durable_queue.full():
                BACKPRESSURE.labels(stage='pusher_queue').inc()
                record_would_drop('pusher_queue')
            await durable_queue.put(AudioProjection(receipt, start, receipt.samples - samples, samples))

    async def process_durable_private_cloud_queue() -> None:
        # Pending conversations hold only receipts. Hydrate at most one bounded
        # contiguous batch for the legacy playback projection, preserving the
        # old 60-second write cadence without retaining 60 seconds of PCM.
        pending_refs: dict[str, list[AudioProjection]] = {}
        queued_at: dict[str, float] = {}
        identity_refreshed: set[str] = set()

        async def flush_refs(conv_id: str) -> None:
            refs = pending_refs.pop(conv_id, [])
            queued_at.pop(conv_id, None)
            if not refs:
                return
            try:
                chunks: List[Dict[str, Any]] = []
                for ref in refs:
                    pcm = await run_blocking(storage_executor, read_pcm, uid, ref.receipt)
                    pcm = pcm[ref.offset_samples * 2 : (ref.offset_samples + ref.samples) * 2]
                    if len(pcm) != ref.samples * 2:
                        raise ValueError('durable projection sample range is incomplete')
                    chunk: Dict[str, Any] = {'data': pcm, 'timestamp': ref.start}
                    if audio_timeline_v2:
                        chunk['span'] = {
                            'start': ref.start,
                            'samples': ref.samples,
                            'sample_rate': ref.sample_rate,
                        }
                    chunks.append(chunk)
                if not audio_timeline_v2:
                    # Legacy headers are last-arrival-minus-duration estimates,
                    # not capture positions. Preserve the old continuous batch
                    # and its first timestamp; jitter cannot create v2 spans.
                    chunks = [{'data': b''.join(chunk['data'] for chunk in chunks), 'timestamp': refs[0].start}]
                await run_blocking(
                    storage_executor,
                    upload_audio_chunks_batch,
                    chunks,
                    uid,
                    conv_id,
                    cached_protection_level,
                    sample_rate=sample_rate,
                )
                OMI_AUDIO_TIMELINE_CHUNKS_WRITTEN_TOTAL.labels(
                    reason='with_spans' if audio_timeline_v2 else 'without_spans'
                ).inc()
                audio_files = await run_blocking(
                    storage_executor, conversations_db.create_audio_files_from_chunks, uid, conv_id
                )
                if audio_files:
                    applied = await run_blocking(
                        storage_executor,
                        conversations_db.update_conversation,
                        uid,
                        conv_id,
                        {'audio_files': [af.model_dump() for af in audio_files]},
                        record_owner_out=record_owners if len(record_owners) < 128 else None,
                    )
                    if applied:
                        schedule_person_voice_learning_retry(uid, conv_id)
                        if len(identity_refreshed) < 128:
                            identity_refreshed.add(conv_id)
            except Exception:
                # Projection is optional for custody: media AND its exact
                # manifest survive in remote storage and are discoverable
                # by raw-live playback after restart/reconnect.
                fail_recording(conv_id)
                record_failure('projection')
                record_fallback(
                    component='pusher',
                    from_mode='private_cloud_sync',
                    to_mode='raw_audio',
                    reason='other',
                    outcome='degraded',
                    log=logger,
                )
                logger.warning('Durable audio projection deferred; archive receipt retained')

        while websocket_active or not durable_queue.empty() or pending_refs or record_close_requests:
            await wait_for_event(shutdown_event, PRIVATE_CLOUD_SYNC_PROCESS_INTERVAL)
            while not durable_queue.empty():
                ref = durable_queue.get_nowait()
                conv_id = ref.conversation_id
                if conv_id is not None:
                    refs = pending_refs.get(conv_id, [])
                    if refs:
                        end = refs[-1].start + refs[-1].samples / refs[-1].sample_rate
                        total_bytes = (sum(r.samples for r in refs) + ref.samples) * 2
                        if (
                            (audio_timeline_v2 and abs(ref.start - end) > AUDIO_TIMELINE_CONTINUITY_TOLERANCE)
                            or len(refs) >= 60
                            or total_bytes > BUFFERED_AUDIO_MAX_BYTES
                        ):
                            await flush_refs(conv_id)
                    elif len(pending_refs) >= PRIVATE_CLOUD_QUEUE_MAX_SIZE:
                        BACKPRESSURE.labels(stage='pending_refs').inc()
                        record_would_drop('pending_refs')
                        await flush_refs(next(iter(pending_refs)))
                    pending_refs.setdefault(conv_id, []).append(ref)
                    queued_at.setdefault(conv_id, time.monotonic())
                durable_queue.task_done()
            for conv_id, refs in list(pending_refs.items()):
                if (
                    not websocket_active
                    or conv_id in record_close_requests
                    or time.monotonic() - queued_at[conv_id] >= PRIVATE_CLOUD_BATCH_MAX_AGE
                    or sum(r.samples / r.sample_rate for r in refs) >= PRIVATE_CLOUD_CHUNK_DURATION
                ):
                    await flush_refs(conv_id)
            for conv_id in list(record_close_requests):
                if (
                    conv_id not in failed_recordings
                    and not record_upload_failed
                    and (live_record_admission_enabled() or conv_id in record_owners)
                ):
                    await run_blocking(db_executor, conversations_db.seal_record_audio, uid, conv_id)
                record_owners.pop(conv_id, None)
                record_close_requests.discard(conv_id)
        if identity_refreshed:
            schedule_completed_identity_retries(uid, identity_refreshed)

    # (start_wall, end_wall, sha256) of v2 runs whose GCS upload SUCCEEDED, for
    # reconciling replays that reach past the live buffer. Entries are appended
    # by the upload task after `upload_audio_chunks_batch` returns, so a chunk
    # evicted by the bounded queue or a batch dropped after exhausting its
    # retries never lends its digest to a later replay: that range stays
    # unverifiable (a counted conflict) instead of trusted.
    v2_flushed_runs: Deque[Tuple[float, float, str]] = deque(maxlen=V2_FLUSHED_RUN_LEDGER_SIZE)
    # Conversations that may skip the per-flush replay-reconcile listing: one
    # span upload already committed this session and no replay signal has been
    # seen since (duplicate frame, trimmed overlap, conflict, or a create-only
    # collision). A replay signal re-enables reconciliation for the rest of
    # the session. The exemption is only a cost skip: the create-only write
    # plus identical-content no-op keeps a missed signal correct.
    # The exemption is windowed by conversation_generation: the continuity
    # window that proved a clean span upload dies at every conversation-id
    # frame (audio_timeline_last_end resets there), so a batch created in a
    # later window must reconcile again instead of trusting a proof earned
    # under a window it can no longer see.
    v2_reconcile_exempt: Dict[str, int] = {}
    conversation_generation = 0
    # Conversations with a chunk already enqueued this session. A skipped
    # all-zero run is only audio-identical when objects exist on BOTH sides:
    # readers zero-fill the gap between two objects, so a leading silent run
    # (no earlier object) must be stored to anchor the recording's start.
    conversations_with_chunks: set[str] = set()
    v2_replay_seen: set[str] = set()
    record_close_requests: set[str] = set()
    record_owners: dict[str, str] = {}
    record_upload_failed = False
    failed_recordings: set[str] = set()

    def fail_recording(conversation_id: str) -> None:
        nonlocal record_upload_failed
        if len(failed_recordings) < 128:
            failed_recordings.add(conversation_id)
        else:
            record_upload_failed = True  # bounded fail-closed overflow, never forget a failed source

    async def process_private_cloud_queue() -> None:
        """Background task that batches private cloud sync uploads by conversation_id.

        Chunks are accumulated per conversation and flushed when:
        - The batch reaches 60s of audio data, or
        - The oldest chunk in the batch exceeds PRIVATE_CLOUD_BATCH_MAX_AGE, or
        - The websocket disconnects (shutdown flush).
        """
        nonlocal websocket_active
        nonlocal application_failed, record_upload_failed

        if durable_audio:
            await process_durable_private_cloud_queue()
            return

        # Pending batches keyed by conversation_id
        pending: Dict[str, Dict[str, Any]] = {}

        # Batches closed early by a v2 discontinuity (or a failed upload
        # retrying): uploaded before any pending batch for the same
        # conversation, so noncontiguous PCM is never concatenated.
        ready_batches: List[Dict[str, Any]] = []

        # Conversations deleted underneath us (e.g. discarded as empty at rollover).
        # Their chunks can never be referenced, played or cleaned up again, so we
        # stop uploading rather than leaving more orphans in the bucket (#11742).
        deleted_conversations: set[str] = set()
        identity_refreshed: set[str] = set()
        # Set when the storage authority refuses this account's writes because a
        # destructive operation owns the gate (account deletion in progress): the
        # refusal is permanent for the session, so later batches drop fast instead
        # of replaying the same fenced write every flush.
        upload_fenced: bool = False

        def _add_to_batch(chunk_info: PrivateCloudChunk) -> None:
            nonlocal record_upload_failed
            conv_id = chunk_info['conversation_id']
            if conv_id in deleted_conversations or upload_fenced:
                audio_budget.release(len(chunk_info['data']))
                return
            span = chunk_info.get('span')
            chunk_end: Optional[float] = None
            if span:
                # v2 chunks know their exact end; legacy chunks end where the
                # next chunk's start lands (the old contiguous assumption).
                chunk_end = chunk_info['timestamp'] + span['samples'] / span['sample_rate']
            batch: Optional[Dict[str, Any]] = pending.get(conv_id)
            if batch is not None and chunk_end is not None and batch.get('end') is not None:
                # Never batch noncontiguous PCM: a gap (or overlap) between
                # the batch's current end and this chunk's start closes the
                # pending batch for upload before the new run accumulates.
                if abs(chunk_info['timestamp'] - cast(float, batch['end'])) > AUDIO_TIMELINE_CONTINUITY_TOLERANCE:
                    if pending.pop(conv_id, None) is not None:
                        ready_batches.append(batch)
                    batch = None
            if batch is None:
                before = set(pending)
                bound_private_pending(pending, audio_budget)
                for dropped_id in before - set(pending):
                    fail_recording(dropped_id)
                batch = {
                    'data': bytearray(),
                    'conversation_id': conv_id,
                    'timestamp': chunk_info['timestamp'],  # oldest chunk timestamp
                    'queued_at': time.monotonic(),
                    'retries': 0,
                }
                pending[conv_id] = batch
            batch['data'].extend(chunk_info['data'])
            # Latest chunk's window wins; a generation change always splits
            # noncontiguous v2 runs into their own batch first (above), so a
            # batch never silently mixes windows when the split matters.
            batch['timeline_generation'] = chunk_info.get('timeline_generation')
            if chunk_end is not None and span:
                batch['end'] = chunk_end
                batch['span'] = {
                    'samples': len(batch['data']) // 2,
                    'sample_rate': span['sample_rate'],
                }

        async def _flush_batch(conv_id: str):
            """Upload a conversation's pending batched chunk."""
            await _upload_batch(pending.pop(conv_id, None))

        async def _upload_batch(batch: Optional[Dict[str, Any]]):
            """Upload a batched chunk and update audio files."""
            nonlocal application_failed, upload_fenced, record_upload_failed
            if not batch or len(batch['data']) == 0:
                return
            if upload_fenced:
                # The fence latched earlier this session: this batch was already
                # queued before the refusal — drop it instead of replaying a
                # write the authority has refused for the rest of the session.
                audio_budget.release(len(batch['data']))
                batch['data'] = bytearray()
                return
            conv_id = batch['conversation_id']
            chunk_data = bytes(batch['data'])
            del batch['data']  # free bytearray immediately — chunk_data holds the bytes copy
            timestamp = batch['timestamp']
            retries = batch.get('retries', 0)
            try:
                upload_chunk: Dict[str, Any] = {'data': chunk_data, 'timestamp': timestamp}
                if batch.get('span'):
                    upload_chunk['span'] = {**batch['span'], 'start': timestamp}
                chunks_to_upload: List[Dict[str, Any]] = [upload_chunk]
                # Skip the replay-reconcile listing once this session has
                # committed a span upload for the conversation with no replay
                # signal since — and only while the batch was buffered under
                # the same continuity window that earned the exemption: a
                # conversation-id frame resets that window, so a batch from a
                # later window reconciles again. The first upload of a
                # session (or any upload after a replay signal, a window
                # change, or a failed attempt) reconciles.
                batch_generation = batch.get('timeline_generation')
                reconcile_prefix = conv_id in v2_replay_seen or v2_reconcile_exempt.get(conv_id) != batch_generation
                if not reconcile_prefix:
                    PUSHER_RECONCILE_LISTS_SKIPPED_TOTAL.inc()
                await run_blocking(
                    storage_executor,
                    cast(Any, upload_audio_chunks_batch),
                    chunks_to_upload,
                    uid,
                    conv_id,
                    cast(str, cached_protection_level),
                    sample_rate=sample_rate,
                    reconcile_prefix=reconcile_prefix,
                )
                OMI_AUDIO_TIMELINE_CHUNKS_WRITTEN_TOTAL.labels(
                    reason='with_spans' if batch.get('span') is not None else 'without_spans'
                ).inc()
                if batch.get('span') is not None and batch.get('end') is not None:
                    if conv_id not in v2_replay_seen and isinstance(batch_generation, int):
                        if len(v2_reconcile_exempt) < 1024:
                            v2_reconcile_exempt[conv_id] = batch_generation
                    # The digest ledger records only runs whose object exists.
                    # Batches are contiguous by construction (discontinuities
                    # close them in `_add_to_batch`), so one entry covers the
                    # whole uploaded run; a batch that never gets here —
                    # evicted before upload, or dropped after exhausting its
                    # retries — leaves no entry and stays unverifiable.
                    v2_flushed_runs.append((timestamp, batch['end'], hashlib.sha256(chunk_data).hexdigest()))
                del chunks_to_upload
                try:
                    audio_files = await run_blocking(
                        storage_executor, conversations_db.create_audio_files_from_chunks, uid, conv_id
                    )
                    if audio_files:
                        files_payload = [af.model_dump() for af in audio_files]
                        applied = await run_blocking(
                            storage_executor,
                            conversations_db.update_conversation,
                            uid,
                            conv_id,
                            {'audio_files': files_payload},
                            record_owner_out=record_owners if len(record_owners) < 128 else None,
                        )
                        if applied:
                            schedule_person_voice_learning_retry(uid, conv_id)
                            if len(identity_refreshed) < 128:
                                identity_refreshed.add(conv_id)
                        else:
                            deleted_conversations.add(conv_id)
                            logger.info(f"Conversation gone, stopped private cloud sync {uid} {conv_id}")
                            record_fallback(
                                component='pusher',
                                from_mode='private_cloud_sync',
                                to_mode='drop',
                                reason='policy',
                                outcome='exhausted',
                                log=logger,
                            )
                except Exception as e:
                    logger.error(f"Error updating audio files: {e} {uid} {conv_id}")
                audio_budget.release(len(chunk_data))
            except Exception as e:
                if isinstance(e, DestructiveOperationInProgress):
                    # The storage authority fenced this account: a destructive
                    # operation (account deletion) owns the gate for hours. The
                    # refusal is permanent — no retry of this batch can pass the
                    # fence, and every later flush would burn the same three
                    # doomed attempts against the same authority reads. Latch
                    # the session: drop what is queued and stop accepting more,
                    # like the deleted-conversation path, and keep the session
                    # itself healthy (the closure is by design, not a fault).
                    upload_fenced = True
                    audio_budget.release(len(chunk_data))
                    PUSHER_PRIVATE_CLOUD_UPLOAD_DROPS.inc()
                    record_fallback(
                        component='pusher',
                        from_mode='private_cloud_sync',
                        to_mode='drop',
                        reason='policy',
                        outcome='exhausted',
                        log=logger,
                    )
                    logger.warning(
                        f'Private cloud sync stopped: account writes are fenced by a destructive operation '
                        f'(no retry) {uid} {conv_id}'
                    )
                elif retries < PRIVATE_CLOUD_SYNC_MAX_RETRIES:
                    batch['retries'] = retries + 1
                    batch['data'] = bytearray(chunk_data)
                    # A failed attempt (including a create-only collision,
                    # which is replay evidence) re-enables the reconcile
                    # listing for this conversation for the rest of the
                    # session; the upload loop also forces reconciliation on
                    # its own retry attempt.
                    v2_replay_seen.add(conv_id)
                    # Retry in the ordered ready lane on a later process tick,
                    # keeping the batch's queue time: an in-turn immediate
                    # retry burns the whole budget on one fast permanent error
                    # (or blocks this uploader for four back-to-back slow
                    # timeouts). The ready lane skips the retry gate during
                    # shutdown so the drain stays bounded.
                    batch['retry_at'] = time.monotonic() + PRIVATE_CLOUD_SYNC_PROCESS_INTERVAL
                    ready_batches.append(batch)
                    logger.error(f"Private cloud batch upload failed (retry {retries + 1}): {e} {uid} {conv_id}")
                else:
                    audio_budget.release(len(chunk_data))
                    PUSHER_PRIVATE_CLOUD_UPLOAD_DROPS.inc()
                    application_failed = True
                    fail_recording(conv_id)
                    logger.info(
                        f"Private cloud batch upload failed after {PRIVATE_CLOUD_SYNC_MAX_RETRIES} retries, dropping: {e} {uid} {conv_id}"
                    )
            del chunk_data

        while (
            websocket_active
            or len(private_cloud_queue) > 0
            or len(pending) > 0
            or ready_batches
            or record_close_requests
        ):
            await wait_for_event(shutdown_event, PRIVATE_CLOUD_SYNC_PROCESS_INTERVAL)

            if record_upload_failed or upload_fenced:
                record_close_requests.clear()
            record_close_requests.difference_update(failed_recordings)

            # Drain queue into pending batches
            if private_cloud_queue:
                chunks_to_process = private_cloud_queue.copy()
                private_cloud_queue.clear()
                for chunk_info in chunks_to_process:
                    _add_to_batch(chunk_info)

            if upload_fenced:
                # The fence latched mid-session: anything still held is dropped
                # fast (budget released, no upload, no retries) so the loop's
                # drain contract still completes and shutdown stays bounded.
                while ready_batches:
                    dropped = ready_batches.pop(0)
                    payload = dropped.get('data')
                    audio_budget.release(len(payload) if payload else 0)
                for dropped in list(pending.values()):
                    audio_budget.release(len(dropped.get('data', b'')))
                pending.clear()
                continue

            if not pending and not ready_batches and not record_close_requests:
                # `pending` alone must not gate the iteration: a failed
                # upload's retry batch lives in `ready_batches`, and skipping
                # the ready lane below with `continue` would leave the loop
                # condition truthy forever (a busy spin once shutdown is set).
                continue

            now = time.monotonic()
            batch_size_threshold = sample_rate * 2 * PRIVATE_CLOUD_CHUNK_DURATION

            # Discontinuity-closed batches upload first, in order. A failed
            # upload's retry waits one process interval before it is due
            # (`retry_at`); the gate is skipped during shutdown so the drain
            # never stalls on it.
            while ready_batches:
                head = ready_batches[0]
                retry_at = head.get('retry_at')
                if retry_at is not None and websocket_active and now < retry_at:
                    break
                await _upload_batch(ready_batches.pop(0))

            # Determine which conversations to flush
            conv_ids_to_flush: List[str] = []
            for conv_id, batch in pending.items():
                batch_age = now - batch['queued_at']
                is_shutdown = not websocket_active
                is_size_ready = len(batch['data']) >= batch_size_threshold
                is_age_ready = batch_age >= PRIVATE_CLOUD_BATCH_MAX_AGE
                owned_close = conv_id in record_close_requests and (
                    live_record_admission_enabled() or conv_id in record_owners
                )
                # Leave one uploader tick for the boundary frame/close message
                # to join a size-ready batch. Otherwise a scheduler tick between
                # the full run and its final frame creates a second tiny object.
                # Real discontinuities still close into ready_batches, and age,
                # recording close and disconnect always flush immediately.
                if is_size_ready and 'size_ready_at' not in batch:
                    batch['size_ready_at'] = now
                size_grace_elapsed = (
                    is_size_ready and now - batch['size_ready_at'] >= PRIVATE_CLOUD_SYNC_PROCESS_INTERVAL
                )
                if is_shutdown or size_grace_elapsed or is_age_ready or owned_close:
                    conv_ids_to_flush.append(conv_id)

            for conv_id in conv_ids_to_flush:
                await _flush_batch(conv_id)
            for conv_id in list(record_close_requests):
                if (
                    not record_upload_failed
                    and conv_id not in failed_recordings
                    and not upload_fenced
                    and conv_id not in pending
                    and not any(b['conversation_id'] == conv_id for b in ready_batches)
                    and not any(b['conversation_id'] == conv_id for b in private_cloud_queue)
                ):
                    if live_record_admission_enabled() or conv_id in record_owners:
                        await run_blocking(db_executor, conversations_db.seal_record_audio, uid, conv_id)
                    record_owners.pop(conv_id, None)
                    record_close_requests.discard(conv_id)

        # Only authoritative uploaded manifests qualify. Admission is process-wide
        # and eligibility precedes the eight-pass selection limit.
        if identity_refreshed:
            schedule_completed_identity_retries(uid, identity_refreshed)

    async def process_speaker_sample_queue() -> None:
        """Background task that processes speaker sample extraction requests."""
        nonlocal websocket_active

        while websocket_active or len(speaker_sample_queue) > 0:
            await wait_for_event(shutdown_event, SPEAKER_SAMPLE_PROCESS_INTERVAL)

            if not speaker_sample_queue:
                continue

            current_time = time.time()
            is_shutdown = not websocket_active

            # Separate ready and pending requests.
            # On shutdown, skip the age check — process everything so pending
            # samples aren't silently dropped when the drain timeout fires.
            ready_requests: List[SpeakerSampleRequest] = []
            pending_requests: List[SpeakerSampleRequest] = []

            for request in list(speaker_sample_queue):
                if is_shutdown or current_time - request['queued_at'] >= SPEAKER_SAMPLE_MIN_AGE:
                    ready_requests.append(request)
                else:
                    pending_requests.append(request)

            # Keep pending requests in queue (rebuild deque with pending only)
            speaker_sample_queue.clear()
            speaker_sample_queue.extend(pending_requests)

            # Process ready requests (fire and forget)
            for request in ready_requests:
                person_id = request['person_id']
                conv_id = request['conversation_id']
                segment_ids = request['segment_ids']

                try:
                    await run_authorized_person_learning(
                        uid=uid,
                        person_id=person_id,
                        conversation_id=conv_id,
                        segment_ids=segment_ids,
                        sample_rate=sample_rate,
                    )
                except Exception as e:
                    logger.error(f"Error extracting speaker samples: {e} {uid} {conv_id}")

    async def process_transcript_queue() -> None:
        """Batched consumer for transcript events (realtime integrations + webhooks)."""
        nonlocal websocket_active

        while websocket_active or len(transcript_queue) > 0:
            await wait_for_event(shutdown_event, TRANSCRIPT_QUEUE_FLUSH_INTERVAL)

            if not transcript_queue:
                continue

            # Process batch
            batch: List[TranscriptQueueItem] = list(transcript_queue)
            transcript_queue.clear()

            for item in batch:
                await _dispatch_transcript_item(uid, item['segments'], item['memory_id'], resolved_client_kind)

    async def process_audio_bytes_queue() -> None:
        """Event-driven consumer for audio bytes triggers (app integrations + webhooks)."""
        nonlocal websocket_active

        while websocket_active or len(audio_bytes_queue) > 0:
            # Wait for signal or check periodically for shutdown
            try:
                await asyncio.wait_for(audio_bytes_event.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                if shutdown_event.is_set() and not audio_bytes_queue:
                    break
                continue

            audio_bytes_event.clear()

            if not audio_bytes_queue:
                continue

            # Process all queued items
            batch: List[AudioBytesQueueItem] = list(audio_bytes_queue)
            audio_bytes_queue.clear()

            for item in batch:
                try:
                    if item['type'] == 'app':
                        await trigger_realtime_audio_bytes(uid, item['sample_rate'], item['data'])
                    elif item['type'] == 'webhook':
                        await send_audio_bytes_developer_webhook(uid, item['sample_rate'], item['data'])
                except Exception as e:
                    logger.error(f"Error processing audio bytes: {e} {uid}")
                finally:
                    audio_budget.release(len(item['data']))

    # The conversation this session last streamed, for the episode moment flush at teardown.
    episode_session: Dict[str, Optional[str]] = {'conversation_id': None}

    async def receive_tasks() -> None:
        nonlocal websocket_active
        nonlocal websocket_close_code
        nonlocal application_failed, record_upload_failed
        nonlocal speaker_sample_queue
        nonlocal transcript_queue
        nonlocal audio_bytes_queue
        nonlocal conversation_generation

        audiobuffer = bytearray()
        trigger_audiobuffer = bytearray()
        private_cloud_sync_buffer = bytearray()
        private_cloud_chunk_start_time: Optional[float] = None
        current_conversation_id: Optional[str] = None
        # Audio-timeline v2 continuity for this socket: the projected end of
        # the last accepted run and its conversation. None until first audio
        # or after a conversation switch (which flushes the run).
        audio_timeline_last_end: Optional[float] = None

        def _queue_private_cloud_chunk(*, skip_if_silent: bool = False) -> None:
            nonlocal record_upload_failed
            if durable_audio:
                return
            if not (private_cloud_sync_enabled and current_conversation_id and len(private_cloud_sync_buffer) > 0):
                return
            if not any(private_cloud_sync_buffer):
                # An all-zero run carries no audio information: every reader
                # zero-fills gaps between objects with these same bytes, so
                # skipping the run is audio-identical to storing it, without
                # one sub-1 KB object per silence boundary. Two conditions
                # must hold, or the zero-fill gap has no boundary to fill
                # against: the flush must be a discontinuity (audio for this
                # conversation has arrived beyond the gap, so a later object
                # is guaranteed — worst case at the next terminal flush), and
                # the conversation must already have an earlier chunk (a
                # leading silent run would otherwise shift the recording's
                # start to the first stored object). Shutdown, conversation
                # switch, process handoff and size triggers never skip: with
                # no guaranteed later object the zeros must be stored.
                if skip_if_silent and current_conversation_id in conversations_with_chunks:
                    PUSHER_SILENT_RUN_FLUSHES_SKIPPED_TOTAL.inc()
                    audio_budget.release(len(private_cloud_sync_buffer))
                    _reset_private_cloud_buffer()
                    return
            if len(private_cloud_queue) >= PRIVATE_CLOUD_QUEUE_MAX_SIZE:
                fail_recording(private_cloud_queue[0]['conversation_id'])
                logger.warning(
                    f"private_cloud_queue full ({len(private_cloud_queue)}/{PRIVATE_CLOUD_QUEUE_MAX_SIZE}), "
                    f"dropping oldest chunk to prevent OOM {uid}"
                )
            chunk_payload: PrivateCloudChunk = {
                'data': bytes(private_cloud_sync_buffer),
                'conversation_id': current_conversation_id,
                'timestamp': private_cloud_chunk_start_time or time.time(),
            }
            if audio_timeline_v2:
                # v2 runs carry their authoritative PCM sample count so
                # coverage never has to be inferred from encoded blob size.
                # The flushed-run digest is recorded by the upload task only
                # after this chunk's batch lands in GCS (see _upload_batch).
                span: PrivateCloudSpan = {
                    'samples': len(private_cloud_sync_buffer) // 2,
                    'sample_rate': int(sample_rate),
                }
                chunk_payload['span'] = span
            # The continuity window this chunk was buffered under; the upload
            # path compares it against the conversation's clean-upload window.
            chunk_payload['timeline_generation'] = conversation_generation
            # This chunk anchors every later gap for the conversation,
            # including the zero-fill left by any skipped silent run.
            conversations_with_chunks.add(current_conversation_id)
            append_bounded(
                private_cloud_queue,
                chunk_payload,
                'private_cloud',
                byte_budget=audio_budget,
                size_of=lambda chunk: len(chunk['data']),
            )

        def _reset_private_cloud_buffer() -> None:
            nonlocal private_cloud_sync_buffer
            nonlocal private_cloud_chunk_start_time
            private_cloud_sync_buffer = bytearray()
            private_cloud_chunk_start_time = None

        def _v2_overlap_conflict(run_start: float, overlap_bytes: int, audio: bytes) -> bool:
            """True when the overlapping range's bytes cannot be proven identical.

            The overlap region [run_start, run_start + overlap_bytes) is
            verified against the live buffer (byte compare) and, for the part
            predating it, against the flushed-run digest ledger. Any region
            that can be neither compared nor digest-matched is a conflict: the
            already-stored bytes stay, the unverified overlap is dropped, and
            only the frame's new tail past the accepted end is kept.
            """
            tol = AUDIO_TIMELINE_CONTINUITY_TOLERANCE
            bps = sample_rate * 2
            overlap_hi = run_start + overlap_bytes / bps
            buffer_lo = private_cloud_chunk_start_time if private_cloud_sync_buffer else None

            def flushed_runs_cover(need_lo: float, need_hi: float) -> bool:
                if need_hi <= need_lo + tol:
                    return True
                covered_hi = need_hi
                for fs, fe, digest in reversed(v2_flushed_runs):
                    if fe <= need_lo + tol:
                        break
                    if fs >= covered_hi - tol:
                        continue
                    if fs < need_lo - tol:
                        # Partial run overlap: only whole-run digests exist.
                        return False
                    off = round((fs - run_start) * bps)
                    n = round((fe - fs) * bps)
                    if off < 0 or off + n > len(audio) or hashlib.sha256(audio[off : off + n]).hexdigest() != digest:
                        return False
                    covered_hi = fs
                    if covered_hi <= need_lo + tol:
                        return True
                return covered_hi <= need_lo + tol

            if buffer_lo is None or buffer_lo > run_start + tol:
                pre_hi = overlap_hi if buffer_lo is None else min(overlap_hi, buffer_lo)
                if not flushed_runs_cover(run_start, pre_hi):
                    return True
            if buffer_lo is not None:
                b_lo = max(run_start, buffer_lo)
                if b_lo < overlap_hi - tol:
                    in_audio = round((b_lo - run_start) * bps)
                    in_audio -= in_audio % 2
                    in_buffer = round((b_lo - buffer_lo) * bps)
                    in_buffer -= in_buffer % 2
                    comparable = min(
                        overlap_bytes - in_audio, len(audio) - in_audio, len(private_cloud_sync_buffer) - in_buffer
                    )
                    if (
                        comparable > 0
                        and bytes(private_cloud_sync_buffer[in_buffer : in_buffer + comparable])
                        != audio[in_audio : in_audio + comparable]
                    ):
                        return True
            return False

        try:
            while websocket_active:
                try:
                    data = await asyncio.wait_for(websocket.receive_bytes(), timeout=WS_RECEIVE_TIMEOUT)
                except asyncio.TimeoutError:
                    logger.warning(f"WebSocket receive timeout ({WS_RECEIVE_TIMEOUT}s), closing connection {uid}")
                    # This is a dead upstream, not a normal remote close. Keep its
                    # terminal outcome distinct from protocol close codes 1000/1001.
                    websocket_close_code = 1011
                    application_failed = True
                    break
                header_type = frame_header(data)

                # Heartbeat (data-frame keepalive from backend to reset GKE ILB idle timer)
                if header_type == 100:
                    continue

                # Conversation ID
                if header_type == 103:
                    new_conversation_id = bytes(data[4:]).decode("utf-8")
                    # Flush private cloud buffer for the old conversation before switching
                    if current_conversation_id and current_conversation_id != new_conversation_id:
                        if len(private_cloud_sync_buffer) > 0:
                            logger.info(
                                f"Flushed private cloud buffer on conversation switch: "
                                f"{len(private_cloud_sync_buffer)} bytes {uid}"
                            )
                        _queue_private_cloud_chunk()
                        _reset_private_cloud_buffer()
                        if private_cloud_sync_enabled and len(record_close_requests) < 128:
                            record_close_requests.add(current_conversation_id)
                    current_conversation_id = new_conversation_id
                    episode_session['conversation_id'] = new_conversation_id
                    # A conversation boundary ends the current v2 run: the
                    # next audio starts a fresh continuity window. Every
                    # clean-span exemption was proven under the old window;
                    # the generation bump retires them all, so a rebound
                    # conversation's next upload reconciles again.
                    conversation_generation += 1
                    audio_timeline_last_end = None
                    logger.info(f"Pusher received conversation_id: {current_conversation_id} {uid}")
                    continue

                # Transcript - queue for batched processing
                if header_type == 102:
                    res = json_object(data)
                    segments = res.get('segments')
                    memory_id = res.get('memory_id')
                    if not isinstance(segments, list) or not all(isinstance(segment, dict) for segment in segments):
                        raise ValueError('segments must be a list of objects')
                    if memory_id is not None and not isinstance(memory_id, str):
                        raise ValueError('memory_id must be a string')
                    # A transcript's memory_id must NOT overwrite the session's authoritative
                    # current_conversation_id (which is set only by header 103). Doing so let a stale
                    # lifecycle event carrying an older conversation's memory_id rebind a newer recording
                    # session, mis-associating subsequent private-cloud audio (see issue #6952).
                    if len(transcript_queue) >= TRANSCRIPT_QUEUE_WARN_SIZE:
                        logger.warning(f"Warning: transcript_queue size {len(transcript_queue)} {uid}")
                    # Route this transcript by its own memory_id when present, falling back to the
                    # session's conversation id. This does not mutate session-scoped state.
                    conversation_or_memory_id = memory_id or current_conversation_id
                    append_bounded(
                        transcript_queue,
                        {'segments': segments, 'memory_id': conversation_or_memory_id},
                        'transcript',
                    )
                    continue

                # Process conversation request
                if header_type == 104:
                    res = json_object(data)
                    conversation_id = res.get('conversation_id')
                    language = res.get('language', 'en')
                    byok_keys = res.get('byok_keys') or None
                    finalization_job_id = res.get('finalization_job_id')
                    dispatch_generation = res.get('dispatch_generation')
                    finalization_result_protocol = _parse_finalization_result_protocol(
                        res.get('finalization_result_protocol')
                    )
                    if conversation_id is not None and not isinstance(conversation_id, str):
                        raise ValueError('conversation_id must be a string')
                    if not isinstance(language, str):
                        raise ValueError('language must be a string')
                    if byok_keys is not None and (
                        not isinstance(byok_keys, dict)
                        or not all(isinstance(key, str) and isinstance(value, str) for key, value in byok_keys.items())
                    ):
                        raise ValueError('byok_keys must be an object')
                    if finalization_job_id is not None and not isinstance(finalization_job_id, str):
                        raise ValueError('finalization_job_id must be a string')
                    if dispatch_generation is not None and (
                        isinstance(dispatch_generation, bool) or not isinstance(dispatch_generation, int)
                    ):
                        raise ValueError('dispatch_generation must be an integer')
                    if conversation_id:
                        if private_cloud_sync_enabled and (
                            live_record_admission_enabled() or conversation_id in record_owners
                        ):
                            _queue_private_cloud_chunk()
                            _reset_private_cloud_buffer()
                            if len(record_close_requests) < 128:
                                record_close_requests.add(conversation_id)
                        logger.info(f"Pusher received process_conversation request: {conversation_id} {uid}")
                        # Durable finalization already has a Firestore owner. It
                        # must survive an originating listen socket close after
                        # this handoff, so pusher owns it at process scope. Its
                        # lifespan drains tracked tasks on process shutdown.
                        start_background_task(
                            process_conversation_task(
                                uid,
                                conversation_id,
                                language,
                                websocket,
                                byok_keys=byok_keys,
                                finalization_job_id=(
                                    finalization_job_id if isinstance(finalization_job_id, str) else None
                                ),
                                dispatch_generation=(
                                    dispatch_generation if isinstance(dispatch_generation, int) else None
                                ),
                                client_kind=resolved_client_kind,
                                finalization_result_protocol=finalization_result_protocol,
                            ),
                            name=f'pusher_finalization:{uid}:{conversation_id}',
                        )
                    continue

                # Speaker sample extraction request - queue for background processing
                if header_type == 105:
                    res = json_object(data)
                    person_id = res.get('person_id')
                    conv_id = res.get('conversation_id')
                    segment_ids = res.get('segment_ids', [])
                    if person_id is not None and not isinstance(person_id, str):
                        raise ValueError('person_id must be a string')
                    if conv_id is not None and not isinstance(conv_id, str):
                        raise ValueError('conversation_id must be a string')
                    if not isinstance(segment_ids, list) or not all(
                        isinstance(segment_id, str) for segment_id in segment_ids
                    ):
                        raise ValueError('segment_ids must be a list of strings')
                    if person_id and conv_id and segment_ids:
                        if len(speaker_sample_queue) >= SPEAKER_SAMPLE_QUEUE_WARN_SIZE:
                            logger.warning(f"Warning: speaker_sample_queue size {len(speaker_sample_queue)} {uid}")
                        logger.info(
                            f"Queued speaker sample request: person={person_id}, {len(segment_ids)} segments {uid}"
                        )
                        append_bounded(
                            speaker_sample_queue,
                            {
                                'person_id': person_id,
                                'conversation_id': conv_id,
                                'segment_ids': segment_ids,
                                'queued_at': time.time(),
                            },
                            'speaker_sample',
                        )
                    continue

                # Audio bytes
                if header_type == 101:
                    # Parse: header(4) | timestamp(8 bytes double) | audio_data
                    buffer_start_timestamp = struct.unpack("d", data[4:12])[0]
                    audio_data = data[12:]

                    receipt = await archive_private_audio(audio_data, buffer_start_timestamp, current_conversation_id)

                    if audio_timeline_v2:
                        # v2: the timestamp is the projected start of this
                        # run's first sample. Compare against the last accepted
                        # run's end with 1 ms tolerance: a positive
                        # discontinuity flushes the partial chunk (and the
                        # pending batch downstream) instead of concatenating
                        # across a gap; an overlap is reconciled exactly.
                        run_seconds = len(audio_data) / (sample_rate * 2)
                        run_start = buffer_start_timestamp
                        run_end = run_start + run_seconds
                        if audio_timeline_last_end is not None:
                            delta = run_start - audio_timeline_last_end
                            if delta > AUDIO_TIMELINE_CONTINUITY_TOLERANCE:
                                # skip_if_silent: audio for this conversation
                                # has arrived beyond the gap, so a later
                                # object is guaranteed to follow whatever this
                                # flush stores (or drops) — the only flush
                                # where a skipped all-zero run is provably
                                # interior, never the recording's last.
                                _queue_private_cloud_chunk(skip_if_silent=True)
                                _reset_private_cloud_buffer()
                            elif delta < -AUDIO_TIMELINE_CONTINUITY_TOLERANCE:
                                # Any overlap of already-accepted audio is
                                # replay evidence for this conversation: the
                                # upload path must keep reconciling against
                                # committed objects this session.
                                if current_conversation_id:
                                    v2_replay_seen.add(current_conversation_id)
                                if run_end <= audio_timeline_last_end + AUDIO_TIMELINE_CONTINUITY_TOLERANCE:
                                    # Exact replay of an already accepted
                                    # range: never re-store or re-emit it.
                                    logger.info(
                                        f'Ignored duplicate v2 audio replay '
                                        f'start={run_start:.3f}s {len(audio_data)}B {uid}'
                                    )
                                    continue
                                overlap_bytes = int((audio_timeline_last_end - run_start) * sample_rate * 2)
                                overlap_bytes -= overlap_bytes % 2
                                if overlap_bytes >= len(audio_data):
                                    continue
                                # Verify the overlapping prefix against every
                                # retained copy of that range — the live buffer
                                # by bytes, anything older by flushed-run
                                # digest. Differing or unverifiable bytes for
                                # an accepted range are never re-stored; the
                                # frame's genuinely new tail past the accepted
                                # end still continues the run from there.
                                if _v2_overlap_conflict(run_start, overlap_bytes, audio_data):
                                    OMI_AUDIO_TIMELINE_REPLAY_CONFLICTS_TOTAL.inc()
                                    logger.warning(
                                        f'Conflicting v2 audio for an accepted range '
                                        f'start={run_start:.3f}s overlap={overlap_bytes}B; '
                                        f'dropping the unverified overlap, keeping the new tail {uid}'
                                    )
                                audio_data = audio_data[overlap_bytes:]
                                run_start = audio_timeline_last_end
                                run_end = run_start + len(audio_data) / (sample_rate * 2)
                        audio_timeline_last_end = run_end
                        buffer_start_timestamp = run_start

                    # Custody retains the original; only the accepted v2 tail
                    # enters the derivative projection after replay trimming.
                    await queue_private_projection(receipt, buffer_start_timestamp, len(audio_data) // 2)

                    # Only accumulate audio buffers if there's a consumer (app trigger or webhook)
                    # Without this guard, buffers grow ~16KB/s indefinitely for users with no audio apps
                    if has_audio_apps_enabled:
                        extend_bounded(trigger_audiobuffer, audio_data, 'audio_app_buffer', audio_budget)
                    if audio_bytes_webhook_delay_seconds is not None:
                        extend_bounded(audiobuffer, audio_data, 'audio_webhook_buffer', audio_budget)

                    # Private cloud sync - queue chunks for background processing
                    if private_cloud_sync_enabled and current_conversation_id and not durable_audio:
                        if private_cloud_chunk_start_time is None:
                            # Use timestamp from first buffer of this 5-second chunk
                            private_cloud_chunk_start_time = buffer_start_timestamp

                        stored_capture = extend_bounded(
                            private_cloud_sync_buffer,
                            audio_data,
                            'private_cloud_buffer',
                            audio_budget,
                        )
                        if not stored_capture:
                            fail_recording(current_conversation_id)
                        # Queue chunk every PRIVATE_CLOUD_CHUNK_DURATION seconds
                        if len(private_cloud_sync_buffer) >= sample_rate * 2 * PRIVATE_CLOUD_CHUNK_DURATION:
                            _queue_private_cloud_chunk()
                            _reset_private_cloud_buffer()

                    # Queue audio bytes triggers for batched processing
                    if (
                        has_audio_apps_enabled
                        and len(trigger_audiobuffer) > sample_rate * audio_bytes_trigger_delay_seconds * 2
                    ):
                        if len(audio_bytes_queue) >= AUDIO_BYTES_QUEUE_WARN_SIZE:
                            logger.warning(f"Warning: audio_bytes_queue size {len(audio_bytes_queue)} {uid}")
                        append_bounded(
                            audio_bytes_queue,
                            {
                                'type': 'app',
                                'sample_rate': sample_rate,
                                'data': trigger_audiobuffer.copy(),
                            },
                            'audio_bytes',
                            byte_budget=audio_budget,
                            size_of=lambda item: len(item['data']),
                        )
                        audio_bytes_event.set()  # Wake consumer immediately
                        trigger_audiobuffer = bytearray()
                    if (
                        audio_bytes_webhook_delay_seconds is not None
                        and len(audiobuffer) > sample_rate * audio_bytes_webhook_delay_seconds * 2
                    ):
                        if len(audio_bytes_queue) >= AUDIO_BYTES_QUEUE_WARN_SIZE:
                            logger.warning(f"Warning: audio_bytes_queue size {len(audio_bytes_queue)} {uid}")
                        append_bounded(
                            audio_bytes_queue,
                            {
                                'type': 'webhook',
                                'sample_rate': sample_rate,
                                'data': audiobuffer.copy(),
                            },
                            'audio_bytes',
                            byte_budget=audio_budget,
                            size_of=lambda item: len(item['data']),
                        )
                        audio_bytes_event.set()  # Wake consumer immediately
                        audiobuffer = bytearray()
                    continue

        except (ValueError, struct.error, UnicodeDecodeError) as exc:
            websocket_close_code = 1003
            logger.warning(f'Invalid pusher frame: {type(exc).__name__} {uid}')
        except WebSocketDisconnect as exc:
            websocket_close_code = exc.code or 1006
            logger.info("WebSocket disconnected")
        except Exception as e:
            logger.error(f'Could not process audio: error {e}')
            websocket_close_code = 1011
            application_failed = True
        finally:
            # Flush any remaining private cloud sync buffer before shutdown
            if len(private_cloud_sync_buffer) > 0:
                logger.info(f"Flushed final private cloud buffer: {len(private_cloud_sync_buffer)} bytes {uid}")
            _queue_private_cloud_chunk()
            if private_cloud_sync_enabled and current_conversation_id and len(record_close_requests) < 128:
                record_close_requests.add(current_conversation_id)
            websocket_active = False
            audio_bytes_event.set()

    bg_main_tasks: List[asyncio.Task[Any]] = []
    try:
        PUSHER_ACTIVE_WS_CONNECTIONS.inc()
        receive_task = create_named_task(receive_tasks(), name=f"ws:{uid}:receive")
        bg_main_tasks = [
            create_named_task(process_speaker_sample_queue(), name=f"ws:{uid}:speaker_samples"),
            create_named_task(process_private_cloud_queue(), name=f"ws:{uid}:private_cloud"),
            create_named_task(process_transcript_queue(), name=f"ws:{uid}:transcripts"),
            create_named_task(process_audio_bytes_queue(), name=f"ws:{uid}:audio_bytes"),
        ]

        exit_result = await supervise_tasks(
            receive_task=receive_task,
            bg_tasks=bg_main_tasks,
            finite_tasks=None,
            label="pusher",
        )
        logger.info(f"Supervisor exited: reason={exit_result.reason} task={exit_result.task_name} {uid}")
        if exit_result.reason in {'crash', 'lifetime_done'}:
            # A background worker dying or unexpectedly returning ends an accepted
            # session abnormally even though the socket itself has no close frame.
            websocket_close_code = 1011
            application_failed = True

        if receive_task.done() and not receive_task.cancelled():
            exc = receive_task.exception()
            if exc is not None:
                raise exc

        if not receive_task.done():
            websocket_active = False
            receive_task.cancel()
            try:
                await receive_task
            except asyncio.CancelledError:
                pass

        shutdown_event.set()
        await drain_tasks(bg_main_tasks, timeout=BG_DRAIN_TIMEOUT, label="pusher_bg", cancel=False)

    except asyncio.CancelledError:
        websocket_close_code = 1006
        raise
    except Exception as e:
        logger.error(f"Error during WebSocket operation: {e}")
        websocket_close_code = 1011
        application_failed = True
    finally:
        shutdown_event.set()
        websocket_active = False

        all_to_cancel = [t for t in bg_main_tasks if not t.done()]
        await drain_tasks(all_to_cancel, timeout=5.0, label="pusher_cleanup", cancel=True)

        PUSHER_ACTIVE_WS_CONNECTIONS.dec()
        # Live episode moments buffer in this process; a pod move or reconnect must not strand them.
        await flush_episode_moment(uid, episode_session['conversation_id'])

        journey_attempt.finish(pusher_session_outcome(websocket_close_code, application_failed=application_failed))

        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close(code=websocket_close_code)
            except Exception as e:
                logger.error(f"Error closing WebSocket: {e}")


@router.websocket("/v1/trigger/listen")
async def websocket_endpoint_trigger(
    websocket: WebSocket,
    uid: str,
    sample_rate: int = 8000,
    client_kind: str = 'unknown',
    audio_timeline: Optional[int] = None,
    audio_custody: Optional[int] = None,
) -> None:
    await _websocket_util_trigger(websocket, uid, sample_rate, client_kind, audio_timeline, audio_custody)

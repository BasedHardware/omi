import struct
import asyncio
import json
import time
from collections import deque
from typing import Any, Coroutine, Dict, List, Optional, Set, TypedDict, cast

from fastapi import APIRouter
from fastapi.websockets import WebSocketDisconnect, WebSocket
from starlette.websockets import WebSocketState

import database.conversations as conversations_db
from database import conversation_finalization_jobs as finalization_jobs_db
from database import users as users_db
from services.conversation_finalization import final_attempt_failed
from utils.apps import is_audio_bytes_app_enabled
from utils.app_integrations import (
    trigger_realtime_integrations,
    trigger_realtime_audio_bytes,
)
from utils.byok import set_byok_keys, set_byok_uid
from utils.conversations import lifecycle as lifecycle_service
from utils.conversations.finalizer import (
    ConversationFinalizationDisposition,
    ConversationFinalizationError,
    finalize_persisted_conversation,
)
from utils.executors import db_executor, storage_executor, run_blocking
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
from utils.cloud_tasks import get_listen_finalization_tasks_max_attempts, is_audio_merge_dispatch_enabled
from utils.other.storage import maybe_invalidate_conversation_playback, upload_audio_chunks_batch
from utils.metrics import PUSHER_ACTIVE_WS_CONNECTIONS
from utils.observability.journeys import JourneyAttempt, JourneyOutcome, record_capture_finalization_terminal
from utils.speaker_identification import extract_speaker_samples
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Constants for speaker sample extraction
SPEAKER_SAMPLE_PROCESS_INTERVAL = 15.0
SPEAKER_SAMPLE_MIN_AGE = 120.0

# Constants for private cloud sync
PRIVATE_CLOUD_SYNC_PROCESS_INTERVAL = 1.0
PRIVATE_CLOUD_CHUNK_DURATION = 60.0
PRIVATE_CLOUD_BATCH_MAX_AGE = 60.0  # seconds — flush batch if oldest chunk exceeds this age
PRIVATE_CLOUD_SYNC_MAX_RETRIES = 3

# Queue size limits
PRIVATE_CLOUD_QUEUE_MAX_SIZE = 20  # ~18MB/connection max (30 conns × 18MB = 540MB) — prevents OOM with headroom
SPEAKER_SAMPLE_QUEUE_WARN_SIZE = 100

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


def pusher_session_outcome(close_code: int, *, application_failed: bool = False) -> JourneyOutcome:
    """Classify accepted sessions without counting normal disconnects as failures."""
    if application_failed or close_code == 1011:
        return 'failure'
    if close_code in {1000, 1001}:
        return 'success'
    return 'cancelled'


class _SpeakerSampleRequest(TypedDict):
    person_id: str
    conversation_id: str
    segment_ids: List[str]
    queued_at: float


class _TranscriptQueueItem(TypedDict):
    segments: List[Dict[str, Any]]
    memory_id: Optional[str]


class _AudioBytesQueueItem(TypedDict):
    type: str
    sample_rate: int
    data: bytearray


class _PrivateCloudChunk(TypedDict):
    data: bytes
    conversation_id: str
    timestamp: float
    retries: int


async def _process_conversation_task(
    uid: str,
    conversation_id: str,
    language: str,
    websocket: WebSocket,
    byok_keys: Optional[Dict[str, str]] = None,
    finalization_job_id: Optional[str] = None,
    dispatch_generation: Optional[int] = None,
) -> None:
    """Process a leased conversation job and send a minimal result to listen.

    `byok_keys` is forwarded from the listen service. When present, LLM and
    STT calls made inside process_conversation route through the user's own
    provider keys instead of Omi's env keys.
    """
    if byok_keys:
        set_byok_keys(byok_keys)
        set_byok_uid(uid)

    async def send_result(result: Dict[str, Any]) -> None:
        data = bytearray()
        data.extend(struct.pack("I", 201))
        data.extend(bytes(json.dumps(result), "utf-8"))
        await websocket.send_bytes(bytes(data))

    job_id: Optional[str] = None
    generation: Optional[int] = None
    lease_epoch: Optional[int] = None
    attempt_count: int = 0

    async def record_failure(failure_code: str) -> bool:
        """Release the lease. Returns whether this was the terminal attempt.

        Inline dispatch has no Cloud Tasks worker to exhaust the attempt budget,
        so the claimed attempt count is the only bound on a deterministically
        failing job. Without a terminal state the conversation would stay
        `processing` forever and be re-finalized by every later session.
        """
        if job_id is None or generation is None or lease_epoch is None:
            return False
        terminal = attempt_count >= get_listen_finalization_tasks_max_attempts()
        try:
            if terminal:
                marked_dead_letter = await run_blocking(
                    db_executor,
                    final_attempt_failed,
                    job_id,
                    generation,
                    lease_epoch,
                    attempt_count,
                )
                if not marked_dead_letter:
                    return False
                return await run_blocking(
                    db_executor, lifecycle_service.fail_and_discard_processing, uid, conversation_id
                )
            await run_blocking(
                db_executor,
                finalization_jobs_db.mark_finalization_retryable,
                job_id,
                generation,
                lease_epoch,
                failure_code,
            )
        except Exception:
            logger.error(
                'pusher finalization recovery update failed uid=%s conversation=%s failure=%s terminal=%s',
                uid,
                conversation_id,
                failure_code,
                terminal,
            )
            return False
        return False

    try:
        if not finalization_job_id or dispatch_generation is None:
            # Every finalization request must be mediated by the Firestore
            # owner.  Accepting the legacy frame would allow a pending pusher
            # session to bypass the durable claim and double-process work.
            await send_result({'conversation_id': conversation_id, 'error': 'durable_job_required'})
            return

        job_id = finalization_job_id
        generation = dispatch_generation

        claim = await run_blocking(
            db_executor,
            finalization_jobs_db.claim_finalization_job,
            job_id,
            generation,
            allow_byok=bool(byok_keys),
            expected_uid=uid,
            expected_conversation_id=conversation_id,
        )
        claim_status = claim['status']
        if claim_status == 'fenced':
            await send_result({'conversation_id': conversation_id, 'fenced': True})
            return
        if claim_status == 'completed':
            await send_result({'conversation_id': conversation_id, 'success': True})
            return
        if claim_status != 'claimed':
            await send_result(
                {
                    'conversation_id': conversation_id,
                    'error': f'job_{claim_status}',
                    # A dead-lettered job is never actionable again; telling the
                    # live session it is terminal stops it from re-requesting.
                    'terminal': claim_status in finalization_jobs_db.TERMINAL_JOB_STATUSES,
                }
            )
            return
        attempt_count = claim['attempt_count']
        lease_epoch = claim['lease_epoch']
        if lease_epoch is None:
            logger.error(
                'pusher finalization claim returned no lease epoch uid=%s conversation=%s', uid, conversation_id
            )
            await send_result({'conversation_id': conversation_id, 'error': 'processing_failed'})
            return

        disposition = await finalize_persisted_conversation(
            uid,
            conversation_id,
            language,
            finalization_job_id=job_id,
            dispatch_generation=generation,
            lease_epoch=lease_epoch,
        )

        if disposition == ConversationFinalizationDisposition.fenced:
            completed = await run_blocking(
                db_executor,
                lifecycle_service.complete_fenced_finalization,
                job_id,
                generation,
                lease_epoch,
            )
        else:
            completed = await run_blocking(
                db_executor,
                finalization_jobs_db.mark_finalization_completed,
                job_id,
                generation,
                lease_epoch,
            )
        if not completed:
            await send_result({'conversation_id': conversation_id, 'error': 'job_completion_conflict'})
            return
        if disposition == ConversationFinalizationDisposition.fenced:
            record_capture_finalization_terminal('stale', claim.get('created_at'))
            await send_result({'conversation_id': conversation_id, 'fenced': True})
            return
        record_capture_finalization_terminal('success', claim.get('created_at'))
        await send_result({'conversation_id': conversation_id, 'success': True})
    except ConversationFinalizationError:
        terminal = await record_failure('processing_failed')
        logger.error(
            'pusher finalization failed uid=%s conversation=%s failure=processing_failed terminal=%s',
            uid,
            conversation_id,
            terminal,
        )
        try:
            await send_result({'conversation_id': conversation_id, 'error': 'processing_failed', 'terminal': terminal})
        except Exception:
            pass
    except Exception:
        terminal = await record_failure('worker_failed')
        logger.error(
            'pusher finalization task failed uid=%s conversation=%s failure=worker_failed terminal=%s',
            uid,
            conversation_id,
            terminal,
        )
        try:
            await send_result({'conversation_id': conversation_id, 'error': 'processing_failed', 'terminal': terminal})
        except Exception:
            pass


async def _websocket_util_trigger(
    websocket: WebSocket,
    uid: str,
    sample_rate: int = 8000,
) -> None:
    logger.info(f'_websocket_util_trigger {uid}')

    try:
        await websocket.accept()
    except RuntimeError as e:
        logger.error(e)
        await websocket.close(code=1011, reason="Dirty state")
        return

    journey_attempt = JourneyAttempt('pusher_session')
    websocket_active = True
    shutdown_event = asyncio.Event()
    websocket_close_code = 1000
    application_failed = False

    try:
        # audio bytes
        audio_bytes_webhook_delay_seconds = get_audio_bytes_webhook_seconds(uid)
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

    # Track background tasks to cancel on cleanup (prevents memory leaks from fire-and-forget tasks)
    bg_tasks: Set[asyncio.Task[Any]] = set()

    def spawn(coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
        """Create a tracked background task that will be cancelled on cleanup."""
        task = asyncio.create_task(coro)
        bg_tasks.add(task)

        def on_done(t: asyncio.Task[Any]) -> None:
            bg_tasks.discard(t)
            if t.cancelled():
                return
            exc = t.exception()
            if exc:
                logger.error(f"Unhandled exception in background task: {exc} {uid}")

        task.add_done_callback(on_done)
        return task

    # Bounded queues — prevent unbounded memory growth during backpressure
    speaker_sample_queue: deque[_SpeakerSampleRequest] = deque(maxlen=SPEAKER_SAMPLE_QUEUE_WARN_SIZE)
    transcript_queue: deque[_TranscriptQueueItem] = deque(maxlen=TRANSCRIPT_QUEUE_WARN_SIZE)
    audio_bytes_queue: deque[_AudioBytesQueueItem] = deque(maxlen=AUDIO_BYTES_QUEUE_WARN_SIZE)

    # private_cloud_queue caps at PRIVATE_CLOUD_QUEUE_MAX_SIZE to prevent OOM kills.
    # An OOM kill loses ALL queued data for ALL users on the pod — dropping the oldest
    # chunk for one user is strictly better than killing the pod.
    private_cloud_queue: deque[_PrivateCloudChunk] = deque(maxlen=PRIVATE_CLOUD_QUEUE_MAX_SIZE)
    audio_bytes_event = asyncio.Event()  # Signals when items are added for instant wake

    async def process_private_cloud_queue() -> None:
        """Background task that batches private cloud sync uploads by conversation_id.

        Chunks are accumulated per conversation and flushed when:
        - The batch reaches 60s of audio data, or
        - The oldest chunk in the batch exceeds PRIVATE_CLOUD_BATCH_MAX_AGE, or
        - The websocket disconnects (shutdown flush).
        """
        nonlocal websocket_active

        # Pending batches keyed by conversation_id
        pending: Dict[str, Dict[str, Any]] = {}

        def _add_to_batch(chunk_info: _PrivateCloudChunk) -> None:
            conv_id = chunk_info['conversation_id']
            if conv_id not in pending:
                pending[conv_id] = {
                    'data': bytearray(),
                    'conversation_id': conv_id,
                    'timestamp': chunk_info['timestamp'],  # oldest chunk timestamp
                    'queued_at': time.monotonic(),
                    'retries': 0,
                }
            batch = pending[conv_id]
            batch['data'].extend(chunk_info['data'])

        async def _flush_batch(conv_id: str):
            """Upload a batched chunk and update audio files."""
            batch = pending.pop(conv_id, None)
            if not batch or len(batch['data']) == 0:
                return
            chunk_data = bytes(batch['data'])
            del batch['data']  # free bytearray immediately — chunk_data holds the bytes copy
            timestamp = batch['timestamp']
            retries = batch.get('retries', 0)
            try:
                chunks_to_upload: List[Dict[str, Any]] = [{'data': chunk_data, 'timestamp': timestamp}]
                await run_blocking(
                    storage_executor,
                    cast(Any, upload_audio_chunks_batch),
                    chunks_to_upload,
                    uid,
                    conv_id,
                    cast(str, cached_protection_level),
                )
                del chunks_to_upload
                try:
                    audio_files = await run_blocking(
                        storage_executor, conversations_db.create_audio_files_from_chunks, uid, conv_id
                    )
                    if audio_files:
                        files_payload = [af.model_dump() for af in audio_files]
                        await run_blocking(
                            storage_executor,
                            conversations_db.update_conversation,
                            uid,
                            conv_id,
                            {'audio_files': files_payload},
                        )
                        # Rebuild the conversation playback artifact if a stamped one
                        # went stale. No stamp (the live-conversation common case) → no-op.
                        if is_audio_merge_dispatch_enabled():
                            stamp = await run_blocking(
                                storage_executor, conversations_db.get_conversation_audio_stamp, uid, conv_id
                            )
                            if stamp:
                                await run_blocking(
                                    storage_executor,
                                    maybe_invalidate_conversation_playback,
                                    uid,
                                    conv_id,
                                    {'conversation_audio': stamp},
                                    files_payload,
                                    'pusher_flush',
                                )
                except Exception as e:
                    logger.error(f"Error updating audio files: {e} {uid} {conv_id}")
            except Exception as e:
                if retries < PRIVATE_CLOUD_SYNC_MAX_RETRIES:
                    batch['retries'] = retries + 1
                    batch['data'] = bytearray(chunk_data)
                    batch['queued_at'] = time.monotonic()  # reset age so next retry waits ~60s
                    pending[conv_id] = batch
                    logger.error(f"Private cloud batch upload failed (retry {retries + 1}): {e} {uid} {conv_id}")
                else:
                    logger.info(
                        f"Private cloud batch upload failed after {PRIVATE_CLOUD_SYNC_MAX_RETRIES} retries, dropping: {e} {uid} {conv_id}"
                    )
            del chunk_data

        while websocket_active or len(private_cloud_queue) > 0 or len(pending) > 0:
            await wait_for_event(shutdown_event, PRIVATE_CLOUD_SYNC_PROCESS_INTERVAL)

            # Drain queue into pending batches
            if private_cloud_queue:
                chunks_to_process = private_cloud_queue.copy()
                private_cloud_queue.clear()
                for chunk_info in chunks_to_process:
                    _add_to_batch(chunk_info)

            if not pending:
                continue

            now = time.monotonic()
            batch_size_threshold = sample_rate * 2 * PRIVATE_CLOUD_CHUNK_DURATION

            # Determine which conversations to flush
            conv_ids_to_flush: List[str] = []
            for conv_id, batch in pending.items():
                batch_age = now - batch['queued_at']
                is_shutdown = not websocket_active
                is_size_ready = len(batch['data']) >= batch_size_threshold
                is_age_ready = batch_age >= PRIVATE_CLOUD_BATCH_MAX_AGE
                if is_shutdown or is_size_ready or is_age_ready:
                    conv_ids_to_flush.append(conv_id)

            for conv_id in conv_ids_to_flush:
                await _flush_batch(conv_id)

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
            ready_requests: List[_SpeakerSampleRequest] = []
            pending_requests: List[_SpeakerSampleRequest] = []

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
                    await extract_speaker_samples(
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
            batch: List[_TranscriptQueueItem] = list(transcript_queue)
            transcript_queue.clear()

            for item in batch:
                segments = item['segments']
                memory_id = item['memory_id']
                try:
                    await trigger_realtime_integrations(uid, segments, memory_id)
                    await realtime_transcript_webhook(uid, segments)
                except Exception as e:
                    logger.error(f"Error processing transcript batch: {e} {uid}")

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
            batch: List[_AudioBytesQueueItem] = list(audio_bytes_queue)
            audio_bytes_queue.clear()

            for item in batch:
                try:
                    if item['type'] == 'app':
                        await trigger_realtime_audio_bytes(uid, item['sample_rate'], item['data'])
                    elif item['type'] == 'webhook':
                        await send_audio_bytes_developer_webhook(uid, item['sample_rate'], item['data'])
                except Exception as e:
                    logger.error(f"Error processing audio bytes: {e} {uid}")

    async def receive_tasks() -> None:
        nonlocal websocket_active
        nonlocal websocket_close_code
        nonlocal application_failed
        nonlocal speaker_sample_queue
        nonlocal transcript_queue
        nonlocal audio_bytes_queue

        audiobuffer = bytearray()
        trigger_audiobuffer = bytearray()
        private_cloud_sync_buffer = bytearray()
        private_cloud_chunk_start_time: Optional[float] = None
        current_conversation_id: Optional[str] = None

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
                header_type = struct.unpack('<I', data[:4])[0]

                # Heartbeat (data-frame keepalive from backend to reset GKE ILB idle timer)
                if header_type == 100:
                    continue

                # Conversation ID
                if header_type == 103:
                    new_conversation_id = bytes(data[4:]).decode("utf-8")
                    # Flush private cloud buffer for the old conversation before switching
                    if (
                        private_cloud_sync_enabled
                        and current_conversation_id
                        and current_conversation_id != new_conversation_id
                        and len(private_cloud_sync_buffer) > 0
                    ):
                        if len(private_cloud_queue) >= PRIVATE_CLOUD_QUEUE_MAX_SIZE:
                            logger.warning(
                                f"private_cloud_queue full ({len(private_cloud_queue)}/{PRIVATE_CLOUD_QUEUE_MAX_SIZE}), "
                                f"dropping oldest chunk to prevent OOM {uid}"
                            )
                        private_cloud_queue.append(
                            {
                                'data': bytes(private_cloud_sync_buffer),
                                'conversation_id': current_conversation_id,
                                'timestamp': private_cloud_chunk_start_time or time.time(),
                                'retries': 0,
                            }
                        )
                        logger.info(
                            f"Flushed private cloud buffer on conversation switch: {len(private_cloud_sync_buffer)} bytes {uid}"
                        )
                        private_cloud_sync_buffer = bytearray()
                        private_cloud_chunk_start_time = None
                    current_conversation_id = new_conversation_id
                    logger.info(f"Pusher received conversation_id: {current_conversation_id} {uid}")
                    continue

                # Transcript - queue for batched processing
                if header_type == 102:
                    res = json.loads(bytes(data[4:]).decode("utf-8"))
                    segments = res.get('segments')
                    memory_id = res.get('memory_id')
                    # A transcript's memory_id must NOT overwrite the session's authoritative
                    # current_conversation_id (which is set only by header 103). Doing so let a stale
                    # lifecycle event carrying an older conversation's memory_id rebind a newer recording
                    # session, mis-associating subsequent private-cloud audio (see issue #6952).
                    if len(transcript_queue) >= TRANSCRIPT_QUEUE_WARN_SIZE:
                        logger.warning(f"Warning: transcript_queue size {len(transcript_queue)} {uid}")
                    # Route this transcript by its own memory_id when present, falling back to the
                    # session's conversation id. This does not mutate session-scoped state.
                    conversation_or_memory_id = memory_id or current_conversation_id
                    transcript_queue.append({'segments': segments, 'memory_id': conversation_or_memory_id})
                    continue

                # Process conversation request
                if header_type == 104:
                    res = json.loads(bytes(data[4:]).decode("utf-8"))
                    conversation_id = res.get('conversation_id')
                    language = res.get('language', 'en')
                    byok_keys = res.get('byok_keys') or None
                    finalization_job_id = res.get('finalization_job_id')
                    dispatch_generation = res.get('dispatch_generation')
                    if conversation_id:
                        logger.info(f"Pusher received process_conversation request: {conversation_id} {uid}")
                        spawn(
                            _process_conversation_task(
                                uid,
                                conversation_id,
                                language,
                                websocket,
                                byok_keys,
                                finalization_job_id if isinstance(finalization_job_id, str) else None,
                                dispatch_generation if isinstance(dispatch_generation, int) else None,
                            )
                        )
                    continue

                # Speaker sample extraction request - queue for background processing
                if header_type == 105:
                    res = json.loads(bytes(data[4:]).decode("utf-8"))
                    person_id = res.get('person_id')
                    conv_id = res.get('conversation_id')
                    segment_ids = res.get('segment_ids', [])
                    if person_id and conv_id and segment_ids:
                        if len(speaker_sample_queue) >= SPEAKER_SAMPLE_QUEUE_WARN_SIZE:
                            logger.warning(f"Warning: speaker_sample_queue size {len(speaker_sample_queue)} {uid}")
                        logger.info(
                            f"Queued speaker sample request: person={person_id}, {len(segment_ids)} segments {uid}"
                        )
                        speaker_sample_queue.append(
                            {
                                'person_id': person_id,
                                'conversation_id': conv_id,
                                'segment_ids': segment_ids,
                                'queued_at': time.time(),
                            }
                        )
                    continue

                # Audio bytes
                if header_type == 101:
                    # Parse: header(4) | timestamp(8 bytes double) | audio_data
                    buffer_start_timestamp = struct.unpack("d", data[4:12])[0]
                    audio_data = data[12:]

                    # Only accumulate audio buffers if there's a consumer (app trigger or webhook)
                    # Without this guard, buffers grow ~16KB/s indefinitely for users with no audio apps
                    if has_audio_apps_enabled:
                        trigger_audiobuffer.extend(audio_data)
                    if audio_bytes_webhook_delay_seconds is not None:
                        audiobuffer.extend(audio_data)

                    # Private cloud sync - queue chunks for background processing
                    if private_cloud_sync_enabled and current_conversation_id:
                        if private_cloud_chunk_start_time is None:
                            # Use timestamp from first buffer of this 5-second chunk
                            private_cloud_chunk_start_time = buffer_start_timestamp

                        private_cloud_sync_buffer.extend(audio_data)
                        # Queue chunk every PRIVATE_CLOUD_CHUNK_DURATION seconds
                        if len(private_cloud_sync_buffer) >= sample_rate * 2 * PRIVATE_CLOUD_CHUNK_DURATION:
                            if len(private_cloud_queue) >= PRIVATE_CLOUD_QUEUE_MAX_SIZE:
                                logger.warning(
                                    f"private_cloud_queue full ({len(private_cloud_queue)}/{PRIVATE_CLOUD_QUEUE_MAX_SIZE}), "
                                    f"dropping oldest chunk to prevent OOM {uid}"
                                )
                            private_cloud_queue.append(
                                {
                                    'data': bytes(private_cloud_sync_buffer),
                                    'conversation_id': current_conversation_id,
                                    'timestamp': cast(float, private_cloud_chunk_start_time),
                                    'retries': 0,
                                }
                            )
                            private_cloud_sync_buffer = bytearray()
                            private_cloud_chunk_start_time = None

                    # Queue audio bytes triggers for batched processing
                    if (
                        has_audio_apps_enabled
                        and len(trigger_audiobuffer) > sample_rate * audio_bytes_trigger_delay_seconds * 2
                    ):
                        if len(audio_bytes_queue) >= AUDIO_BYTES_QUEUE_WARN_SIZE:
                            logger.warning(f"Warning: audio_bytes_queue size {len(audio_bytes_queue)} {uid}")
                        audio_bytes_queue.append(
                            {
                                'type': 'app',
                                'sample_rate': sample_rate,
                                'data': trigger_audiobuffer.copy(),
                            }
                        )
                        audio_bytes_event.set()  # Wake consumer immediately
                        trigger_audiobuffer = bytearray()
                    if (
                        audio_bytes_webhook_delay_seconds is not None
                        and len(audiobuffer) > sample_rate * audio_bytes_webhook_delay_seconds * 2
                    ):
                        if len(audio_bytes_queue) >= AUDIO_BYTES_QUEUE_WARN_SIZE:
                            logger.warning(f"Warning: audio_bytes_queue size {len(audio_bytes_queue)} {uid}")
                        audio_bytes_queue.append(
                            {
                                'type': 'webhook',
                                'sample_rate': sample_rate,
                                'data': audiobuffer.copy(),
                            }
                        )
                        audio_bytes_event.set()  # Wake consumer immediately
                        audiobuffer = bytearray()
                    continue

        except WebSocketDisconnect as exc:
            websocket_close_code = exc.code or 1006
            logger.info("WebSocket disconnected")
        except Exception as e:
            logger.error(f'Could not process audio: error {e}')
            websocket_close_code = 1011
            application_failed = True
        finally:
            # Flush any remaining private cloud sync buffer before shutdown
            if private_cloud_sync_enabled and current_conversation_id and len(private_cloud_sync_buffer) > 0:
                if len(private_cloud_queue) >= PRIVATE_CLOUD_QUEUE_MAX_SIZE:
                    logger.warning(
                        f"private_cloud_queue full ({len(private_cloud_queue)}/{PRIVATE_CLOUD_QUEUE_MAX_SIZE}), "
                        f"dropping oldest chunk to prevent OOM {uid}"
                    )
                private_cloud_queue.append(
                    {
                        'data': bytes(private_cloud_sync_buffer),
                        'conversation_id': current_conversation_id,
                        'timestamp': private_cloud_chunk_start_time or time.time(),
                        'retries': 0,
                    }
                )
                logger.info(f"Flushed final private cloud buffer: {len(private_cloud_sync_buffer)} bytes {uid}")
            websocket_active = False

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

        all_to_cancel = list(bg_tasks) + [t for t in bg_main_tasks if not t.done()]
        await drain_tasks(all_to_cancel, timeout=5.0, label="pusher_cleanup", cancel=True)
        bg_tasks.clear()

        PUSHER_ACTIVE_WS_CONNECTIONS.dec()

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
) -> None:
    await _websocket_util_trigger(websocket, uid, sample_rate)

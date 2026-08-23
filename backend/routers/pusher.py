import struct
import asyncio
import time
from collections import deque
from typing import Any, Awaitable, Dict, List, Optional, cast

from fastapi import APIRouter
from fastapi.websockets import WebSocketDisconnect, WebSocket
from starlette.websockets import WebSocketState

import database.conversations as conversations_db
from database import users as users_db
from utils.pusher_finalization import process_conversation_task
from utils.pusher_protocol import (
    BUFFERED_AUDIO_MAX_BYTES,
    MAX_SAMPLE_RATE,
    MIN_SAMPLE_RATE,
    PRIVATE_CLOUD_QUEUE_MAX_SIZE,
    AudioBytesQueueItem,
    ByteBudget,
    PrivateCloudChunk,
    SpeakerSampleRequest,
    TranscriptQueueItem,
    append_bounded,
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
from utils.cloud_tasks import is_audio_merge_dispatch_enabled
from utils.other.storage import maybe_invalidate_conversation_playback, upload_audio_chunks_batch
from utils.journey_metrics_contract import ClientKind, bounded_client_kind
from utils.metrics import (
    PUSHER_ACTIVE_WS_CONNECTIONS,
    PUSHER_PRIVATE_CLOUD_UPLOAD_DROPS,
)
from utils.readiness import ReadinessGate
from utils.observability.fallback import record_fallback
from utils.observability.journeys import JourneyAttempt
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

    async def process_private_cloud_queue() -> None:
        """Background task that batches private cloud sync uploads by conversation_id.

        Chunks are accumulated per conversation and flushed when:
        - The batch reaches 60s of audio data, or
        - The oldest chunk in the batch exceeds PRIVATE_CLOUD_BATCH_MAX_AGE, or
        - The websocket disconnects (shutdown flush).
        """
        nonlocal websocket_active
        nonlocal application_failed

        # Pending batches keyed by conversation_id
        pending: Dict[str, Dict[str, Any]] = {}

        # Conversations deleted underneath us (e.g. discarded as empty at rollover).
        # Their chunks can never be referenced, played or cleaned up again, so we
        # stop uploading rather than leaving more orphans in the bucket (#11742).
        deleted_conversations: set[str] = set()

        def _add_to_batch(chunk_info: PrivateCloudChunk) -> None:
            conv_id = chunk_info['conversation_id']
            if conv_id in deleted_conversations:
                audio_budget.release(len(chunk_info['data']))
                return
            if conv_id not in pending:
                bound_private_pending(pending, audio_budget)
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
            nonlocal application_failed
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
                        applied = await run_blocking(
                            storage_executor,
                            conversations_db.update_conversation,
                            uid,
                            conv_id,
                            {'audio_files': files_payload},
                        )
                        if applied:
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
                if retries < PRIVATE_CLOUD_SYNC_MAX_RETRIES:
                    batch['retries'] = retries + 1
                    batch['data'] = bytearray(chunk_data)
                    batch['queued_at'] = 0.0 if not websocket_active else time.monotonic()
                    pending[conv_id] = batch
                    logger.error(f"Private cloud batch upload failed (retry {retries + 1}): {e} {uid} {conv_id}")
                else:
                    audio_budget.release(len(chunk_data))
                    PUSHER_PRIVATE_CLOUD_UPLOAD_DROPS.inc()
                    application_failed = True
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
                header_type = frame_header(data)

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
                        append_bounded(
                            private_cloud_queue,
                            {
                                'data': bytes(private_cloud_sync_buffer),
                                'conversation_id': current_conversation_id,
                                'timestamp': private_cloud_chunk_start_time or time.time(),
                            },
                            'private_cloud',
                            byte_budget=audio_budget,
                            size_of=lambda chunk: len(chunk['data']),
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
                                byok_keys,
                                finalization_job_id if isinstance(finalization_job_id, str) else None,
                                dispatch_generation if isinstance(dispatch_generation, int) else None,
                                resolved_client_kind,
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

                    # Only accumulate audio buffers if there's a consumer (app trigger or webhook)
                    # Without this guard, buffers grow ~16KB/s indefinitely for users with no audio apps
                    if has_audio_apps_enabled:
                        extend_bounded(trigger_audiobuffer, audio_data, 'audio_app_buffer', audio_budget)
                    if audio_bytes_webhook_delay_seconds is not None:
                        extend_bounded(audiobuffer, audio_data, 'audio_webhook_buffer', audio_budget)

                    # Private cloud sync - queue chunks for background processing
                    if private_cloud_sync_enabled and current_conversation_id:
                        if private_cloud_chunk_start_time is None:
                            # Use timestamp from first buffer of this 5-second chunk
                            private_cloud_chunk_start_time = buffer_start_timestamp

                        extend_bounded(
                            private_cloud_sync_buffer,
                            audio_data,
                            'private_cloud_buffer',
                            audio_budget,
                        )
                        # Queue chunk every PRIVATE_CLOUD_CHUNK_DURATION seconds
                        if len(private_cloud_sync_buffer) >= sample_rate * 2 * PRIVATE_CLOUD_CHUNK_DURATION:
                            if len(private_cloud_queue) >= PRIVATE_CLOUD_QUEUE_MAX_SIZE:
                                logger.warning(
                                    f"private_cloud_queue full ({len(private_cloud_queue)}/{PRIVATE_CLOUD_QUEUE_MAX_SIZE}), "
                                    f"dropping oldest chunk to prevent OOM {uid}"
                                )
                            append_bounded(
                                private_cloud_queue,
                                {
                                    'data': bytes(private_cloud_sync_buffer),
                                    'conversation_id': current_conversation_id,
                                    'timestamp': cast(float, private_cloud_chunk_start_time),
                                },
                                'private_cloud',
                                byte_budget=audio_budget,
                                size_of=lambda chunk: len(chunk['data']),
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
            if private_cloud_sync_enabled and current_conversation_id and len(private_cloud_sync_buffer) > 0:
                if len(private_cloud_queue) >= PRIVATE_CLOUD_QUEUE_MAX_SIZE:
                    logger.warning(
                        f"private_cloud_queue full ({len(private_cloud_queue)}/{PRIVATE_CLOUD_QUEUE_MAX_SIZE}), "
                        f"dropping oldest chunk to prevent OOM {uid}"
                    )
                append_bounded(
                    private_cloud_queue,
                    {
                        'data': bytes(private_cloud_sync_buffer),
                        'conversation_id': current_conversation_id,
                        'timestamp': private_cloud_chunk_start_time or time.time(),
                    },
                    'private_cloud',
                    byte_budget=audio_budget,
                    size_of=lambda chunk: len(chunk['data']),
                )
                logger.info(f"Flushed final private cloud buffer: {len(private_cloud_sync_buffer)} bytes {uid}")
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
) -> None:
    await _websocket_util_trigger(websocket, uid, sample_rate, client_kind)

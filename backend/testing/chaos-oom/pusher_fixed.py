"""
Fixed pusher.py — from PR #4784 branch fix/pusher-memory-leak-bg-tasks.

Two fixes:
1. spawn() function with bg_tasks: Set[asyncio.Task] + cleanup in finally
2. deque(maxlen=N) for 3 non-critical queues — private_cloud_queue stays unbounded (data safety)

Improvements:
#2: bg_task_metrics in spawn() — tracks created/done/cancelled/in_flight/max_in_flight
#3: _bounded_append() with queue drop counters
#4: debug_metrics with queue_max_len tracking
"""

import struct
import asyncio
import json
import sys
import time
from collections import deque
from datetime import datetime, timezone
from typing import List, Set

from fastapi import APIRouter
from fastapi.websockets import WebSocketDisconnect, WebSocket
from starlette.websockets import WebSocketState

import database.conversations as conversations_db
from database import users as users_db
from database.redis_db import get_cached_user_geolocation
from models.conversation import Conversation, ConversationStatus, Geolocation
from utils.apps import is_audio_bytes_app_enabled
from utils.app_integrations import (
    trigger_realtime_integrations,
    trigger_realtime_audio_bytes,
    trigger_external_integrations,
)
from utils.conversations.location import get_google_maps_location
from utils.conversations.process_conversation import process_conversation
from utils.webhooks import (
    send_audio_bytes_developer_webhook,
    realtime_transcript_webhook,
    get_audio_bytes_webhook_seconds,
)
from utils.other.storage import upload_audio_chunk
from utils.speaker_identification import extract_speaker_samples

router = APIRouter()

# Constants for speaker sample extraction
SPEAKER_SAMPLE_PROCESS_INTERVAL = 15.0
SPEAKER_SAMPLE_MIN_AGE = 120.0

# Constants for private cloud sync
PRIVATE_CLOUD_SYNC_PROCESS_INTERVAL = 1.0
PRIVATE_CLOUD_CHUNK_DURATION = 5.0
PRIVATE_CLOUD_SYNC_MAX_RETRIES = 3

# Queue warning thresholds
PRIVATE_CLOUD_QUEUE_WARN_SIZE = 50
SPEAKER_SAMPLE_QUEUE_WARN_SIZE = 100

# Constants for transcript queue batching
TRANSCRIPT_QUEUE_FLUSH_INTERVAL = 1.0  # seconds
TRANSCRIPT_QUEUE_WARN_SIZE = 50

# Constants for audio bytes queue
AUDIO_BYTES_QUEUE_WARN_SIZE = 20

# Improvement #3 + #4: Global debug metrics — exposed via /debug/memory as pusher_debug
debug_metrics = {
    'queue_drops': {
        'speaker_sample': 0,
        'transcript': 0,
        'audio_bytes': 0,
    },
    'queue_max_len': {
        'speaker_sample': 0,
        'transcript': 0,
        'audio_bytes': 0,
        'private_cloud': 0,
    },
    'bg_task_metrics': {
        'created': 0,
        'done': 0,
        'cancelled': 0,
        'in_flight': 0,
        'max_in_flight': 0,
    },
}


def _bounded_append(q, name, item):
    """Append to a bounded deque, tracking drops and max length."""
    was_full = len(q) == q.maxlen
    q.append(item)  # deque silently drops oldest if full
    if was_full:
        debug_metrics['queue_drops'][name] += 1
    current = len(q)
    if current > debug_metrics['queue_max_len'][name]:
        debug_metrics['queue_max_len'][name] = current


def _track_queue_len(queue, name):
    """Track max length for unbounded queues (private_cloud)."""
    current = len(queue)
    if current > debug_metrics['queue_max_len'][name]:
        debug_metrics['queue_max_len'][name] = current


async def _process_conversation_task(uid: str, conversation_id: str, language: str, websocket: WebSocket):
    """Process a conversation and send result back to _listen via websocket."""
    try:
        conversation_data = conversations_db.get_conversation(uid, conversation_id)
        if not conversation_data:
            response = {"conversation_id": conversation_id, "error": "conversation_not_found"}
            data = bytearray()
            data.extend(struct.pack("I", 201))
            data.extend(bytes(json.dumps(response), "utf-8"))
            await websocket.send_bytes(data)
            return

        conversation = Conversation(**conversation_data)

        if conversation.status != ConversationStatus.processing:
            conversations_db.update_conversation_status(uid, conversation.id, ConversationStatus.processing)
            conversation.status = ConversationStatus.processing

        try:
            geolocation = get_cached_user_geolocation(uid)
            if geolocation:
                geolocation = Geolocation(**geolocation)
                conversation.geolocation = get_google_maps_location(geolocation.latitude, geolocation.longitude)

            conversation = await asyncio.to_thread(process_conversation, uid, language, conversation)
            messages = await asyncio.to_thread(trigger_external_integrations, uid, conversation)
        except Exception as e:
            print(f"Error processing conversation: {e}", uid, conversation_id)
            conversations_db.set_conversation_as_discarded(uid, conversation.id)
            conversation.discarded = True
            messages = []

        response = {"conversation_id": conversation_id, "success": True}
        data = bytearray()
        data.extend(struct.pack("I", 201))
        data.extend(bytes(json.dumps(response), "utf-8"))
        await websocket.send_bytes(data)

    except Exception as e:
        print(f"Error in _process_conversation_task: {e}", uid, conversation_id)
        response = {"conversation_id": conversation_id, "error": str(e)}
        data = bytearray()
        data.extend(struct.pack("I", 201))
        data.extend(bytes(json.dumps(response), "utf-8"))
        try:
            await websocket.send_bytes(data)
        except Exception:
            pass


async def _websocket_util_trigger(
    websocket: WebSocket,
    uid: str,
    sample_rate: int = 8000,
):
    print('_websocket_util_trigger', uid)

    try:
        await websocket.accept()
    except RuntimeError as e:
        print(e)
        await websocket.close(code=1011, reason="Dirty state")
        return

    websocket_active = True
    websocket_close_code = 1000

    audio_bytes_webhook_delay_seconds = get_audio_bytes_webhook_seconds(uid)
    audio_bytes_trigger_delay_seconds = 4
    has_audio_apps_enabled = is_audio_bytes_app_enabled(uid)
    private_cloud_sync_enabled = users_db.get_user_private_cloud_sync_enabled(uid)

    # FIX 1: Track background tasks to cancel on cleanup
    bg_tasks: Set[asyncio.Task] = set()
    btm = debug_metrics['bg_task_metrics']  # shorthand

    def spawn(coro) -> asyncio.Task:
        """Create a tracked background task that will be cancelled on cleanup."""
        # Improvement #2: bg_task_metrics in spawn
        btm['created'] += 1
        btm['in_flight'] += 1
        if btm['in_flight'] > btm['max_in_flight']:
            btm['max_in_flight'] = btm['in_flight']

        task = asyncio.create_task(coro)
        bg_tasks.add(task)

        def on_done(t):
            bg_tasks.discard(t)
            btm['in_flight'] -= 1
            if t.cancelled():
                btm['cancelled'] += 1
                return
            btm['done'] += 1
            exc = t.exception()
            if exc:
                print(f"Unhandled exception in background task: {exc}", uid)

        task.add_done_callback(on_done)
        return task

    # FIX 2: Bounded queues — deque(maxlen=N) prevents unbounded memory growth
    speaker_sample_queue: deque = deque(maxlen=SPEAKER_SAMPLE_QUEUE_WARN_SIZE)
    transcript_queue: deque = deque(maxlen=TRANSCRIPT_QUEUE_WARN_SIZE)
    audio_bytes_queue: deque = deque(maxlen=AUDIO_BYTES_QUEUE_WARN_SIZE)

    # private_cloud_queue stays unbounded — it carries irreplaceable user audio.
    # Silent drops (via deque maxlen) would cause permanent data loss.
    private_cloud_queue: List[dict] = []
    audio_bytes_event = asyncio.Event()

    async def process_private_cloud_queue():
        nonlocal websocket_active

        while websocket_active or len(private_cloud_queue) > 0:
            await asyncio.sleep(PRIVATE_CLOUD_SYNC_PROCESS_INTERVAL)

            if not private_cloud_queue:
                continue

            chunks_to_process = private_cloud_queue.copy()
            private_cloud_queue.clear()

            successful_conversation_ids = set()

            for chunk_info in chunks_to_process:
                chunk_data = chunk_info['data']
                conv_id = chunk_info['conversation_id']
                timestamp = chunk_info['timestamp']
                retries = chunk_info.get('retries', 0)

                try:
                    await asyncio.to_thread(upload_audio_chunk, chunk_data, uid, conv_id, timestamp)
                    successful_conversation_ids.add(conv_id)
                except Exception as e:
                    if retries < PRIVATE_CLOUD_SYNC_MAX_RETRIES:
                        chunk_info['retries'] = retries + 1
                        private_cloud_queue.append(chunk_info)
                        print(f"Private cloud upload failed (retry {retries + 1}): {e}", uid, conv_id)
                    else:
                        print(
                            f"Private cloud upload failed after {PRIVATE_CLOUD_SYNC_MAX_RETRIES} retries, dropping chunk: {e}",
                            uid,
                            conv_id,
                        )

            for conv_id in successful_conversation_ids:
                try:
                    audio_files = await asyncio.to_thread(conversations_db.create_audio_files_from_chunks, uid, conv_id)
                    if audio_files:
                        await asyncio.to_thread(
                            conversations_db.update_conversation,
                            uid,
                            conv_id,
                            {'audio_files': [af.dict() for af in audio_files]},
                        )
                except Exception as e:
                    print(f"Error updating audio files: {e}", uid, conv_id)

    async def process_speaker_sample_queue():
        nonlocal websocket_active

        while websocket_active or len(speaker_sample_queue) > 0:
            await asyncio.sleep(SPEAKER_SAMPLE_PROCESS_INTERVAL)

            if not speaker_sample_queue:
                continue

            current_time = time.time()

            ready_requests = []
            pending_requests = []

            for request in list(speaker_sample_queue):
                if current_time - request['queued_at'] >= SPEAKER_SAMPLE_MIN_AGE:
                    ready_requests.append(request)
                else:
                    pending_requests.append(request)

            speaker_sample_queue.clear()
            speaker_sample_queue.extend(pending_requests)

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
                    print(f"Error extracting speaker samples: {e}", uid, conv_id)

    async def process_transcript_queue():
        nonlocal websocket_active

        while websocket_active or len(transcript_queue) > 0:
            await asyncio.sleep(TRANSCRIPT_QUEUE_FLUSH_INTERVAL)

            if not transcript_queue:
                continue

            batch = list(transcript_queue)
            transcript_queue.clear()

            for item in batch:
                segments = item['segments']
                memory_id = item['memory_id']
                try:
                    await trigger_realtime_integrations(uid, segments, memory_id)
                    await realtime_transcript_webhook(uid, segments)
                except Exception as e:
                    print(f"Error processing transcript batch: {e}", uid)

    async def process_audio_bytes_queue():
        nonlocal websocket_active

        while websocket_active or len(audio_bytes_queue) > 0:
            try:
                await asyncio.wait_for(audio_bytes_event.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            audio_bytes_event.clear()

            if not audio_bytes_queue:
                continue

            batch = list(audio_bytes_queue)
            audio_bytes_queue.clear()

            for item in batch:
                try:
                    if item['type'] == 'app':
                        await trigger_realtime_audio_bytes(uid, item['sample_rate'], item['data'])
                    elif item['type'] == 'webhook':
                        await send_audio_bytes_developer_webhook(uid, item['sample_rate'], item['data'])
                except Exception as e:
                    print(f"Error processing audio bytes: {e}", uid)

    async def receive_tasks():
        nonlocal websocket_active
        nonlocal websocket_close_code
        nonlocal speaker_sample_queue
        nonlocal transcript_queue
        nonlocal audio_bytes_queue

        audiobuffer = bytearray()
        trigger_audiobuffer = bytearray()
        private_cloud_sync_buffer = bytearray()
        private_cloud_chunk_start_time = None
        current_conversation_id = None

        try:
            while websocket_active:
                data = await websocket.receive_bytes()
                header_type = struct.unpack('<I', data[:4])[0]

                if header_type == 103:
                    current_conversation_id = bytes(data[4:]).decode("utf-8")
                    continue

                if header_type == 102:
                    res = json.loads(bytes(data[4:]).decode("utf-8"))
                    segments = res.get('segments')
                    memory_id = res.get('memory_id')
                    if memory_id:
                        current_conversation_id = memory_id
                    conversation_or_memory_id = memory_id or current_conversation_id
                    _bounded_append(
                        transcript_queue, 'transcript', {'segments': segments, 'memory_id': conversation_or_memory_id}
                    )
                    continue

                # FIX 1: spawn() instead of safe_create_task() — tracked and cancelled on cleanup
                if header_type == 104:
                    res = json.loads(bytes(data[4:]).decode("utf-8"))
                    conversation_id = res.get('conversation_id')
                    language = res.get('language', 'en')
                    if conversation_id:
                        spawn(_process_conversation_task(uid, conversation_id, language, websocket))
                    continue

                if header_type == 105:
                    res = json.loads(bytes(data[4:]).decode("utf-8"))
                    person_id = res.get('person_id')
                    conv_id = res.get('conversation_id')
                    segment_ids = res.get('segment_ids', [])
                    if person_id and conv_id and segment_ids:
                        _bounded_append(
                            speaker_sample_queue,
                            'speaker_sample',
                            {
                                'person_id': person_id,
                                'conversation_id': conv_id,
                                'segment_ids': segment_ids,
                                'queued_at': time.time(),
                            },
                        )
                    continue

                if header_type == 101:
                    buffer_start_timestamp = struct.unpack("d", data[4:12])[0]
                    audio_data = data[12:]

                    audiobuffer.extend(audio_data)
                    trigger_audiobuffer.extend(audio_data)

                    if private_cloud_sync_enabled and current_conversation_id:
                        if private_cloud_chunk_start_time is None:
                            private_cloud_chunk_start_time = buffer_start_timestamp

                        private_cloud_sync_buffer.extend(audio_data)
                        if len(private_cloud_sync_buffer) >= sample_rate * 2 * PRIVATE_CLOUD_CHUNK_DURATION:
                            private_cloud_queue.append(
                                {
                                    'data': bytes(private_cloud_sync_buffer),
                                    'conversation_id': current_conversation_id,
                                    'timestamp': private_cloud_chunk_start_time,
                                    'retries': 0,
                                }
                            )
                            _track_queue_len(private_cloud_queue, 'private_cloud')
                            private_cloud_sync_buffer = bytearray()
                            private_cloud_chunk_start_time = None

                    if (
                        has_audio_apps_enabled
                        and len(trigger_audiobuffer) > sample_rate * audio_bytes_trigger_delay_seconds * 2
                    ):
                        _bounded_append(
                            audio_bytes_queue,
                            'audio_bytes',
                            {
                                'type': 'app',
                                'sample_rate': sample_rate,
                                'data': trigger_audiobuffer.copy(),
                            },
                        )
                        audio_bytes_event.set()
                        trigger_audiobuffer = bytearray()
                    if (
                        audio_bytes_webhook_delay_seconds
                        and len(audiobuffer) > sample_rate * audio_bytes_webhook_delay_seconds * 2
                    ):
                        _bounded_append(
                            audio_bytes_queue,
                            'audio_bytes',
                            {
                                'type': 'webhook',
                                'sample_rate': sample_rate,
                                'data': audiobuffer.copy(),
                            },
                        )
                        audio_bytes_event.set()
                        audiobuffer = bytearray()
                    continue

        except WebSocketDisconnect:
            print("WebSocket disconnected")
        except Exception as e:
            print(f'Could not process audio: error {e}')
            websocket_close_code = 1011
        finally:
            if private_cloud_sync_enabled and current_conversation_id and len(private_cloud_sync_buffer) > 0:
                private_cloud_queue.append(
                    {
                        'data': bytes(private_cloud_sync_buffer),
                        'conversation_id': current_conversation_id,
                        'timestamp': private_cloud_chunk_start_time or time.time(),
                        'retries': 0,
                    }
                )
            websocket_active = False

    try:
        receive_task = asyncio.create_task(receive_tasks())
        speaker_sample_task = asyncio.create_task(process_speaker_sample_queue())
        private_cloud_task = asyncio.create_task(process_private_cloud_queue())
        transcript_task = asyncio.create_task(process_transcript_queue())
        audio_bytes_task = asyncio.create_task(process_audio_bytes_queue())
        await asyncio.gather(
            receive_task,
            speaker_sample_task,
            private_cloud_task,
            transcript_task,
            audio_bytes_task,
        )

    except Exception as e:
        print(f"Error during WebSocket operation: {e}")
    finally:
        websocket_active = False

        # FIX 1: Cancel all tracked background tasks to prevent memory leaks
        tasks_to_cancel = list(bg_tasks)
        for task in tasks_to_cancel:
            task.cancel()
        if tasks_to_cancel:
            await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
        bg_tasks.clear()

        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close(code=websocket_close_code)
            except Exception as e:
                print(f"Error closing WebSocket: {e}")


@router.websocket("/v1/trigger/listen")
async def websocket_endpoint_trigger(
    websocket: WebSocket,
    uid: str,
    sample_rate: int = 8000,
):
    await _websocket_util_trigger(websocket, uid, sample_rate)

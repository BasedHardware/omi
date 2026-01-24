import struct
import asyncio
import json
import time
from datetime import datetime, timezone
from typing import List

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
from utils.other.task import safe_create_task
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


async def _process_conversation_task(uid: str, conversation_id: str, language: str, websocket: WebSocket):
    """Process a conversation and send result back to _listen via websocket."""
    try:
        conversation_data = conversations_db.get_conversation(uid, conversation_id)
        if not conversation_data:
            # Send error response
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
            # Geolocation
            geolocation = get_cached_user_geolocation(uid)
            if geolocation:
                geolocation = Geolocation(**geolocation)
                conversation.geolocation = get_google_maps_location(geolocation.latitude, geolocation.longitude)

            # Run blocking operations in thread pool to avoid blocking event loop
            conversation = await asyncio.to_thread(process_conversation, uid, language, conversation)
            messages = await asyncio.to_thread(trigger_external_integrations, uid, conversation)
        except Exception as e:
            print(f"Error processing conversation: {e}", uid, conversation_id)
            conversations_db.set_conversation_as_discarded(uid, conversation.id)
            conversation.discarded = True
            messages = []

        # Send success response back (minimal - transcribe will fetch from DB)
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

    # audio bytes
    audio_bytes_webhook_delay_seconds = get_audio_bytes_webhook_seconds(uid)
    audio_bytes_trigger_delay_seconds = 4
    has_audio_apps_enabled = is_audio_bytes_app_enabled(uid)
    private_cloud_sync_enabled = users_db.get_user_private_cloud_sync_enabled(uid)

    # Queue for pending speaker sample extraction requests
    speaker_sample_queue: List[dict] = []

    # Queue for pending private cloud sync chunks
    private_cloud_queue: List[dict] = []

    # Queue for pending transcript events (batched for realtime integrations + webhooks)
    transcript_queue: List[dict] = []

    # Queue for pending audio bytes triggers (batched for app integrations + webhooks)
    audio_bytes_queue: List[dict] = []
    audio_bytes_event = asyncio.Event()  # Signals when items are added for instant wake

    async def process_private_cloud_queue():
        """Background task that processes private cloud sync uploads with retry logic."""
        nonlocal websocket_active, private_cloud_queue

        while websocket_active or len(private_cloud_queue) > 0:
            await asyncio.sleep(PRIVATE_CLOUD_SYNC_PROCESS_INTERVAL)

            if not private_cloud_queue:
                continue

            # Process all pending chunks
            chunks_to_process = private_cloud_queue.copy()
            private_cloud_queue = []

            successful_conversation_ids = set()  # Track conversations with successful uploads

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
                        # Re-queue with incremented retry count
                        chunk_info['retries'] = retries + 1
                        private_cloud_queue.append(chunk_info)
                        print(f"Private cloud upload failed (retry {retries + 1}): {e}", uid, conv_id)
                    else:
                        print(
                            f"Private cloud upload failed after {PRIVATE_CLOUD_SYNC_MAX_RETRIES} retries, dropping chunk: {e}",
                            uid,
                            conv_id,
                        )

            # Update audio_files for conversations with successful uploads
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
        """Background task that processes speaker sample extraction requests."""
        nonlocal websocket_active, speaker_sample_queue

        while websocket_active or len(speaker_sample_queue) > 0:
            await asyncio.sleep(SPEAKER_SAMPLE_PROCESS_INTERVAL)

            if not speaker_sample_queue:
                continue

            current_time = time.time()

            # Separate ready and pending requests
            ready_requests = []
            pending_requests = []

            for request in speaker_sample_queue:
                if current_time - request['queued_at'] >= SPEAKER_SAMPLE_MIN_AGE:
                    ready_requests.append(request)
                else:
                    pending_requests.append(request)

            # Keep pending requests in queue
            speaker_sample_queue = pending_requests

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
                    print(f"Error extracting speaker samples: {e}", uid, conv_id)

    async def process_transcript_queue():
        """Batched consumer for transcript events (realtime integrations + webhooks)."""
        nonlocal websocket_active, transcript_queue

        while websocket_active or len(transcript_queue) > 0:
            await asyncio.sleep(TRANSCRIPT_QUEUE_FLUSH_INTERVAL)

            if not transcript_queue:
                continue

            # Process batch
            batch = transcript_queue.copy()
            transcript_queue = []

            for item in batch:
                segments = item['segments']
                memory_id = item['memory_id']
                try:
                    await trigger_realtime_integrations(uid, segments, memory_id)
                    await realtime_transcript_webhook(uid, segments)
                except Exception as e:
                    print(f"Error processing transcript batch: {e}", uid)

    async def process_audio_bytes_queue():
        """Event-driven consumer for audio bytes triggers (app integrations + webhooks)."""
        nonlocal websocket_active, audio_bytes_queue

        while websocket_active or len(audio_bytes_queue) > 0:
            # Wait for signal or check periodically for shutdown
            try:
                await asyncio.wait_for(audio_bytes_event.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                continue  # Check websocket_active and queue on timeout

            audio_bytes_event.clear()

            if not audio_bytes_queue:
                continue

            # Process all queued items
            batch = audio_bytes_queue.copy()
            audio_bytes_queue = []

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

                # Conversation ID
                if header_type == 103:
                    current_conversation_id = bytes(data[4:]).decode("utf-8")
                    print(f"Pusher received conversation_id: {current_conversation_id}", uid)
                    continue

                # Transcript - queue for batched processing
                if header_type == 102:
                    res = json.loads(bytes(data[4:]).decode("utf-8"))
                    segments = res.get('segments')
                    memory_id = res.get('memory_id')
                    # Update conversation_id from transcript if provided
                    if memory_id:
                        current_conversation_id = memory_id
                    if len(transcript_queue) >= TRANSCRIPT_QUEUE_WARN_SIZE:
                        print(f"Warning: transcript_queue size {len(transcript_queue)}", uid)
                    transcript_queue.append({'segments': segments, 'memory_id': memory_id})
                    continue

                # Process conversation request
                if header_type == 104:
                    res = json.loads(bytes(data[4:]).decode("utf-8"))
                    conversation_id = res.get('conversation_id')
                    language = res.get('language', 'en')
                    if conversation_id:
                        print(f"Pusher received process_conversation request: {conversation_id}", uid)
                        safe_create_task(_process_conversation_task(uid, conversation_id, language, websocket))
                    continue

                # Speaker sample extraction request - queue for background processing
                if header_type == 105:
                    res = json.loads(bytes(data[4:]).decode("utf-8"))
                    person_id = res.get('person_id')
                    conv_id = res.get('conversation_id')
                    segment_ids = res.get('segment_ids', [])
                    if person_id and conv_id and segment_ids:
                        if len(speaker_sample_queue) >= SPEAKER_SAMPLE_QUEUE_WARN_SIZE:
                            print(f"Warning: speaker_sample_queue size {len(speaker_sample_queue)}", uid)
                        print(f"Queued speaker sample request: person={person_id}, {len(segment_ids)} segments", uid)
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

                    audiobuffer.extend(audio_data)
                    trigger_audiobuffer.extend(audio_data)

                    # Private cloud sync - queue chunks for background processing
                    if private_cloud_sync_enabled and current_conversation_id:
                        if private_cloud_chunk_start_time is None:
                            # Use timestamp from first buffer of this 5-second chunk
                            private_cloud_chunk_start_time = buffer_start_timestamp

                        private_cloud_sync_buffer.extend(audio_data)
                        # Queue chunk every 5 seconds (sample_rate * 2 bytes per sample * 5 seconds)
                        if len(private_cloud_sync_buffer) >= sample_rate * 2 * PRIVATE_CLOUD_CHUNK_DURATION:
                            if len(private_cloud_queue) >= PRIVATE_CLOUD_QUEUE_WARN_SIZE:
                                print(f"Warning: private_cloud_queue size {len(private_cloud_queue)}", uid)
                            private_cloud_queue.append(
                                {
                                    'data': bytes(private_cloud_sync_buffer),
                                    'conversation_id': current_conversation_id,
                                    'timestamp': private_cloud_chunk_start_time,
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
                            print(f"Warning: audio_bytes_queue size {len(audio_bytes_queue)}", uid)
                        audio_bytes_queue.append({
                            'type': 'app',
                            'sample_rate': sample_rate,
                            'data': trigger_audiobuffer.copy(),
                        })
                        audio_bytes_event.set()  # Wake consumer immediately
                        trigger_audiobuffer = bytearray()
                    if (
                        audio_bytes_webhook_delay_seconds
                        and len(audiobuffer) > sample_rate * audio_bytes_webhook_delay_seconds * 2
                    ):
                        if len(audio_bytes_queue) >= AUDIO_BYTES_QUEUE_WARN_SIZE:
                            print(f"Warning: audio_bytes_queue size {len(audio_bytes_queue)}", uid)
                        audio_bytes_queue.append({
                            'type': 'webhook',
                            'sample_rate': sample_rate,
                            'data': audiobuffer.copy(),
                        })
                        audio_bytes_event.set()  # Wake consumer immediately
                        audiobuffer = bytearray()
                    continue

        except WebSocketDisconnect:
            print("WebSocket disconnected")
        except Exception as e:
            print(f'Could not process audio: error {e}')
            websocket_close_code = 1011
        finally:
            # Flush any remaining private cloud sync buffer before shutdown
            if private_cloud_sync_enabled and current_conversation_id and len(private_cloud_sync_buffer) > 0:
                private_cloud_queue.append(
                    {
                        'data': bytes(private_cloud_sync_buffer),
                        'conversation_id': current_conversation_id,
                        'timestamp': private_cloud_chunk_start_time or time.time(),
                        'retries': 0,
                    }
                )
                print(f"Flushed final private cloud buffer: {len(private_cloud_sync_buffer)} bytes", uid)
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

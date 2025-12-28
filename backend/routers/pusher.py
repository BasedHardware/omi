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
from utils.app_integrations import trigger_realtime_integrations, trigger_realtime_audio_bytes, trigger_external_integrations
from utils.conversations.location import get_google_maps_location
from utils.conversations.process_conversation import process_conversation
from utils.webhooks import (
    send_audio_bytes_developer_webhook,
    realtime_transcript_webhook,
    get_audio_bytes_webhook_seconds,
)
from utils.other.storage import (
    upload_audio_chunk,
    list_audio_chunks,
    download_audio_chunks_and_merge,
    upload_person_speech_sample_from_bytes,
)

router = APIRouter()

# Constants for speaker sample extraction
SPEAKER_SAMPLE_MIN_SEGMENT_DURATION = 2.0  # Minimum segment duration in seconds
SPEAKER_SAMPLE_PROCESS_INTERVAL = 5.0  # seconds between queue checks
SPEAKER_SAMPLE_MIN_AGE = 10.0  # seconds to wait before processing a request
PRIVATE_CLOUD_CHUNK_DURATION = 5.0  # Duration of each audio chunk in seconds


async def _extract_speaker_samples(
    uid: str,
    person_id: str,
    conversation_id: str,
    started_at_ts: float,
    segments: List[dict],
    chunks: List[dict],
    sample_rate: int = 16000,
):
    """
    Extract speech samples from segments and store as speaker profiles.
    Processes each segment one by one, stops when sample limit reached.
    Chunks are passed in from the caller (already verified to exist).
    """
    try:
        # Check current sample count once
        sample_count = await asyncio.to_thread(
            users_db.get_person_speech_samples_count, uid, person_id
        )
        if sample_count >= 5:
            print(f"Person {person_id} already has {sample_count} samples, skipping", uid, conversation_id)
            return

        samples_added = 0
        max_samples_to_add = 5 - sample_count

        for seg in segments:
            if samples_added >= max_samples_to_add:
                break

            segment_start = seg.get('start')
            segment_end = seg.get('end')
            if segment_start is None or segment_end is None:
                continue

            seg_duration = segment_end - segment_start
            if seg_duration < SPEAKER_SAMPLE_MIN_SEGMENT_DURATION:
                print(f"Segment too short ({seg_duration:.1f}s), skipping", uid, conversation_id)
                continue

            # Calculate absolute timestamps
            abs_start = started_at_ts + segment_start
            abs_end = started_at_ts + segment_end

            # Find overlapping chunks
            relevant_timestamps = [
                c['timestamp'] for c in chunks
                if (c['timestamp'] + PRIVATE_CLOUD_CHUNK_DURATION) >= abs_start
                and c['timestamp'] <= abs_end
            ]

            if not relevant_timestamps:
                print(f"No relevant chunks for segment {segment_start:.1f}-{segment_end:.1f}s", uid, conversation_id)
                continue

            # Download, merge, and extract
            merged = await asyncio.to_thread(
                download_audio_chunks_and_merge, uid, conversation_id, relevant_timestamps
            )
            buffer_start = min(relevant_timestamps)
            bytes_per_second = sample_rate * 2  # 16-bit mono

            start_byte = max(0, int((abs_start - buffer_start) * bytes_per_second))
            end_byte = min(len(merged), int((abs_end - buffer_start) * bytes_per_second))
            sample_audio = merged[start_byte:end_byte]

            # Ensure minimum sample length (0.5 seconds)
            min_sample_bytes = int(sample_rate * 0.5 * 2)
            if len(sample_audio) < min_sample_bytes:
                print(f"Sample too short ({len(sample_audio)} bytes), skipping", uid, conversation_id)
                continue

            # Upload and store
            path = await asyncio.to_thread(
                upload_person_speech_sample_from_bytes, sample_audio, uid, person_id, sample_rate
            )

            success = await asyncio.to_thread(
                users_db.add_person_speech_sample, uid, person_id, path
            )
            if success:
                samples_added += 1
                print(f"Stored speech sample {samples_added} for person {person_id}: {path}", uid, conversation_id)
            else:
                print(f"Failed to add speech sample for person {person_id}", uid, conversation_id)
                break  # Likely hit limit

    except Exception as e:
        print(f"Error extracting speaker samples: {e}", uid, conversation_id)


async def _process_conversation_task(uid: str, conversation_id: str, language: str, websocket: WebSocket):
    """Process a conversation and send result back to _listen via websocket."""
    try:
        conversation_data = conversations_db.get_conversation(uid, conversation_id)
        if not conversation_data:
            # Send error response
            response = {
                "conversation_id": conversation_id,
                "error": "conversation_not_found"
            }
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
            conversation = await asyncio.to_thread(
                process_conversation, uid, language, conversation
            )
            messages = await asyncio.to_thread(
                trigger_external_integrations, uid, conversation
            )
        except Exception as e:
            print(f"Error processing conversation: {e}", uid, conversation_id)
            conversations_db.set_conversation_as_discarded(uid, conversation.id)
            conversation.discarded = True
            messages = []

        # Send success response back (minimal - transcribe will fetch from DB)
        response = {
            "conversation_id": conversation_id,
            "success": True
        }
        data = bytearray()
        data.extend(struct.pack("I", 201))
        data.extend(bytes(json.dumps(response), "utf-8"))
        await websocket.send_bytes(data)
        
    except Exception as e:
        print(f"Error in _process_conversation_task: {e}", uid, conversation_id)
        response = {
            "conversation_id": conversation_id,
            "error": str(e)
        }
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

    loop = asyncio.get_event_loop()

    # audio bytes
    audio_bytes_webhook_delay_seconds = get_audio_bytes_webhook_seconds(uid)
    audio_bytes_trigger_delay_seconds = 4
    has_audio_apps_enabled = is_audio_bytes_app_enabled(uid)
    private_cloud_sync_enabled = users_db.get_user_private_cloud_sync_enabled(uid)
    private_cloud_sync_delay_seconds = 5

    async def save_audio_chunk(chunk_data: bytes, uid: str, conversation_id: str, timestamp: float):
        upload_audio_chunk(chunk_data, uid, conversation_id, timestamp)

    # task
    # Queue for pending speaker sample extraction requests
    speaker_sample_queue: List[dict] = []

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
                started_at_ts = request['started_at']
                segments = request['segments']

                try:
                    chunks = await asyncio.to_thread(list_audio_chunks, uid, conv_id)
                    if not chunks:
                        print(f"No chunks found for {conv_id}, skipping speaker sample extraction", uid)
                        continue

                    await _extract_speaker_samples(
                        uid=uid,
                        person_id=person_id,
                        conversation_id=conv_id,
                        started_at_ts=started_at_ts,
                        segments=segments,
                        chunks=chunks,
                        sample_rate=sample_rate,
                    )
                except Exception as e:
                    print(f"Error extracting speaker samples: {e}", uid, conv_id)

    async def receive_tasks():
        nonlocal websocket_active
        nonlocal websocket_close_code
        nonlocal speaker_sample_queue

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

                # Transcript
                if header_type == 102:
                    res = json.loads(bytes(data[4:]).decode("utf-8"))
                    segments = res.get('segments')
                    memory_id = res.get('memory_id')
                    # Update conversation_id from transcript if provided
                    if memory_id:
                        current_conversation_id = memory_id
                    asyncio.create_task(trigger_realtime_integrations(uid, segments, memory_id))
                    asyncio.create_task(realtime_transcript_webhook(uid, segments))
                    continue

                # Process conversation request
                if header_type == 104:
                    res = json.loads(bytes(data[4:]).decode("utf-8"))
                    conversation_id = res.get('conversation_id')
                    language = res.get('language', 'en')
                    if conversation_id:
                        print(f"Pusher received process_conversation request: {conversation_id}", uid)
                        asyncio.run_coroutine_threadsafe(
                            _process_conversation_task(uid, conversation_id, language, websocket), loop
                        )
                    continue

                # Speaker sample extraction request - queue for background processing
                if header_type == 105:
                    res = json.loads(bytes(data[4:]).decode("utf-8"))
                    person_id = res.get('person_id')
                    conv_id = res.get('conversation_id')
                    started_at_ts = res.get('started_at')
                    segments = res.get('segments', [])
                    if person_id and conv_id and started_at_ts is not None and segments:
                        print(f"Queued speaker sample request: person={person_id}, {len(segments)} segments", uid)
                        speaker_sample_queue.append({
                            'person_id': person_id,
                            'conversation_id': conv_id,
                            'started_at': started_at_ts,
                            'segments': segments,
                            'queued_at': time.time(),
                        })
                    continue

                # Audio bytes
                if header_type == 101:
                    # Parse: header(4) | timestamp(8 bytes double) | audio_data
                    buffer_start_timestamp = struct.unpack("d", data[4:12])[0]
                    audio_data = data[12:]
                    
                    audiobuffer.extend(audio_data)
                    trigger_audiobuffer.extend(audio_data)

                    # Private cloud sync
                    if private_cloud_sync_enabled and current_conversation_id:
                        if private_cloud_chunk_start_time is None:
                            # Use timestamp from first buffer of this 5-second chunk
                            private_cloud_chunk_start_time = buffer_start_timestamp

                        private_cloud_sync_buffer.extend(audio_data)
                        # Save chunk every 5 seconds (sample_rate * 2 bytes per sample * 5 seconds)
                        if len(private_cloud_sync_buffer) >= sample_rate * 2 * private_cloud_sync_delay_seconds:
                            chunk_data = bytes(private_cloud_sync_buffer)
                            timestamp = private_cloud_chunk_start_time
                            conv_id = current_conversation_id
                            asyncio.run_coroutine_threadsafe(
                                save_audio_chunk(chunk_data, uid, conv_id, timestamp), loop
                            )
                            private_cloud_sync_buffer = bytearray()
                            private_cloud_chunk_start_time = None

                    if (
                        has_audio_apps_enabled
                        and len(trigger_audiobuffer) > sample_rate * audio_bytes_trigger_delay_seconds * 2
                    ):
                        asyncio.run_coroutine_threadsafe(
                            trigger_realtime_audio_bytes(uid, sample_rate, trigger_audiobuffer.copy()), loop
                        )
                        trigger_audiobuffer = bytearray()
                    if (
                        audio_bytes_webhook_delay_seconds
                        and len(audiobuffer) > sample_rate * audio_bytes_webhook_delay_seconds * 2
                    ):
                        asyncio.run_coroutine_threadsafe(
                            send_audio_bytes_developer_webhook(uid, sample_rate, audiobuffer.copy()), loop
                        )
                        audiobuffer = bytearray()
                    continue

        except WebSocketDisconnect:
            print("WebSocket disconnected")
        except Exception as e:
            print(f'Could not process audio: error {e}')
            websocket_close_code = 1011
        finally:
            websocket_active = False

    try:
        receive_task = asyncio.create_task(receive_tasks())
        speaker_sample_task = asyncio.create_task(process_speaker_sample_queue())
        await asyncio.gather(receive_task, speaker_sample_task)

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

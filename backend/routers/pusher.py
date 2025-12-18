import struct
import asyncio
import json
import time
from datetime import datetime, timezone

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
from utils.other.storage import upload_audio_chunk

router = APIRouter()


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
    async def receive_tasks():
        nonlocal websocket_active
        nonlocal websocket_close_code

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

                # Audio bytes
                if header_type == 101:
                    audiobuffer.extend(data[4:])
                    trigger_audiobuffer.extend(data[4:])

                    # Private cloud sync
                    if private_cloud_sync_enabled and current_conversation_id:
                        if private_cloud_chunk_start_time is None:
                            private_cloud_chunk_start_time = time.time()

                        private_cloud_sync_buffer.extend(data[4:])
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
        await asyncio.gather(receive_task)

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

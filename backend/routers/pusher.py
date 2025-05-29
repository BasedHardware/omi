import struct
import asyncio
import json
import hashlib
import time

from fastapi import APIRouter
from fastapi.websockets import WebSocketDisconnect, WebSocket
from starlette.websockets import WebSocketState

from utils.apps import is_audio_bytes_app_enabled
from utils.app_integrations import trigger_realtime_integrations, trigger_realtime_audio_bytes
from utils.webhooks import send_audio_bytes_developer_webhook, realtime_transcript_webhook, \
    get_audio_bytes_webhook_seconds
import database.redis_db as redis_db

router = APIRouter()


async def _websocket_util_trigger(
        websocket: WebSocket, uid: str, sample_rate: int = 8000,
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
    audio_bytes_trigger_delay_seconds = 5
    has_audio_apps_enabled = is_audio_bytes_app_enabled(uid)

    # task
    async def receive_tasks():
        nonlocal websocket_active
        nonlocal websocket_close_code

        audiobuffer = bytearray()
        trigger_audiobuffer = bytearray()

        try:
            while websocket_active:
                data = await websocket.receive_bytes()
                header_type = struct.unpack('<I', data[:4])[0]

                # Transcript
                if header_type == 102:
                    res = json.loads(bytes(data[4:]).decode("utf-8"))
                    segments = res.get('segments')
                    memory_id = res.get('memory_id')
                    
                    # **DEDUPLICATION: Prevent multiple calls for the same transcript data**
                    # Generate a unique hash for this transcript event
                    event_data = f"{uid}:{memory_id}:{len(segments)}"
                    for segment in segments:
                        event_data += f":{segment.get('id', '')}:{segment.get('start', 0)}"
                    
                    event_hash = hashlib.md5(event_data.encode()).hexdigest()
                    dedup_key = f"transcript_event:{event_hash}"
                    
                    # Check if this event was already processed recently (within 5 seconds)
                    try:
                        if redis_db.r.get(dedup_key):
                            print(f"🛑 Skipping duplicate transcript webhook call for user {uid} (hash: {event_hash[:8]})")
                            continue
                        
                        # Mark this event as processed for 5 seconds
                        redis_db.r.setex(dedup_key, 5, "processed")
                        print(f"✅ Processing unique transcript webhook call for user {uid} (hash: {event_hash[:8]})")
                        
                    except Exception as e:
                        print(f"Error with deduplication cache: {e}")
                        # Continue processing if Redis fails
                    
                    # Process the transcript webhooks
                    asyncio.run_coroutine_threadsafe(trigger_realtime_integrations(uid, segments, memory_id), loop)
                    asyncio.run_coroutine_threadsafe(realtime_transcript_webhook(uid, segments), loop)
                    continue

                # Audio bytes
                if header_type == 101:
                    audiobuffer.extend(data[4:])
                    trigger_audiobuffer.extend(data[4:])
                    if has_audio_apps_enabled and len(
                            trigger_audiobuffer) > sample_rate * audio_bytes_trigger_delay_seconds * 2:
                        asyncio.run_coroutine_threadsafe(
                            trigger_realtime_audio_bytes(uid, sample_rate, trigger_audiobuffer.copy()), loop)
                        trigger_audiobuffer = bytearray()
                    if audio_bytes_webhook_delay_seconds and len(
                            audiobuffer) > sample_rate * audio_bytes_webhook_delay_seconds * 2:
                        asyncio.run_coroutine_threadsafe(
                            send_audio_bytes_developer_webhook(uid, sample_rate, audiobuffer.copy()), loop)
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
        websocket: WebSocket, uid: str, sample_rate: int = 8000,
):
    await _websocket_util_trigger(websocket, uid, sample_rate)

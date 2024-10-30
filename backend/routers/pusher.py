import uuid
import struct
from datetime import datetime, timezone, timedelta
from enum import Enum

import opuslib
import webrtcvad
from fastapi import APIRouter
from fastapi.websockets import WebSocketDisconnect, WebSocket
from pydub import AudioSegment
from starlette.websockets import WebSocketState

import database.memories as memories_db
from database import redis_db
from database.redis_db import get_cached_user_geolocation
from models.memory import Memory, TranscriptSegment, MemoryStatus, Structured, Geolocation
from models.message_event import MemoryEvent, MessageEvent
from utils.memories.location import get_google_maps_location
from utils.memories.process_memory import process_memory
from utils.plugins import trigger_external_integrations, trigger_realtime_integrations
from utils.stt.streaming import *
from utils.webhooks import send_audio_bytes_developer_webhook, realtime_transcript_webhook, \
    get_audio_bytes_webhook_seconds

router = APIRouter()

async def _websocket_util_transcript(
        websocket: WebSocket, uid: str,
):
    print('_websocket_util_transcript', uid)

    try:
        await websocket.accept()
    except RuntimeError as e:
        print(e)
        await websocket.close(code=1011, reason="Dirty state")
        return

    websocket_active = True
    websocket_close_code = 1000

    loop = asyncio.get_event_loop()

    # task
    async def receive_segments():
        nonlocal websocket_active
        nonlocal websocket_close_code

        try:
            while websocket_active:
                segments = await websocket.receive_json()
                # print(f"pusher received segments {len(segments)}")
                asyncio.run_coroutine_threadsafe(trigger_realtime_integrations(uid, segments), loop)
                asyncio.run_coroutine_threadsafe(realtime_transcript_webhook(uid, segments), loop)

        except WebSocketDisconnect:
            print("WebSocket disconnected")
        except Exception as e:
            print(f'Could not process segments: error {e}')
            websocket_close_code = 1011
        finally:
            websocket_active = False

    # heart beat
    async def send_heartbeat():
        nonlocal websocket_active
        nonlocal websocket_close_code
        try:
            while websocket_active:
                await asyncio.sleep(20)
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_json({"type": "ping"})
                else:
                    break
        except WebSocketDisconnect:
            print("WebSocket disconnected")
        except Exception as e:
            print(f'Heartbeat error: {e}')
            websocket_close_code = 1011
        finally:
            websocket_active = False

    try:
        receive_task = asyncio.create_task(
            receive_segments()
        )
        heartbeat_task = asyncio.create_task(send_heartbeat())
        await asyncio.gather(receive_task, heartbeat_task)

    except Exception as e:
        print(f"Error during WebSocket operation: {e}")
    finally:
        websocket_active = False
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close(code=websocket_close_code)
            except Exception as e:
                print(f"Error closing WebSocket: {e}")


@router.websocket("/v1/trigger/transcript/listen")
async def websocket_endpoint_transcript(
        websocket: WebSocket, uid: str,
):
    await _websocket_util_transcript(websocket, uid)


async def _websocket_util_audio_bytes(
        websocket: WebSocket, uid: str, sample_rate: int = 8000,
):
    print('_websocket_util_audio_bytes', uid)

    try:
        await websocket.accept()
    except RuntimeError as e:
        print(e)
        await websocket.close(code=1011, reason="Dirty state")
        return

    websocket_active = True
    websocket_close_code = 1000

    loop = asyncio.get_event_loop()

    audio_bytes_webhook_delay_seconds = get_audio_bytes_webhook_seconds(uid)

    # task
    async def receive_audio_bytes():
        nonlocal websocket_active
        nonlocal websocket_close_code

        audiobuffer = bytearray()

        try:
            while websocket_active:
                data = await websocket.receive_bytes()
                # print(f"pusher received audio bytes {len(data)}")
                audiobuffer.extend(data)
                if audio_bytes_webhook_delay_seconds and len(
                        audiobuffer) > sample_rate * audio_bytes_webhook_delay_seconds * 2:
                    asyncio.create_task(send_audio_bytes_developer_webhook(uid, sample_rate, audiobuffer.copy()))
                    audiobuffer = bytearray()

        except WebSocketDisconnect:
            print("WebSocket disconnected")
        except Exception as e:
            print(f'Could not process audio: error {e}')
            websocket_close_code = 1011
        finally:
            websocket_active = False

    # heart beat
    async def send_heartbeat():
        nonlocal websocket_active
        nonlocal websocket_close_code
        try:
            while websocket_active:
                await asyncio.sleep(20)
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_json({"type": "ping"})
                else:
                    break
        except WebSocketDisconnect:
            print("WebSocket disconnected")
        except Exception as e:
            print(f'Heartbeat error: {e}')
            websocket_close_code = 1011
        finally:
            websocket_active = False

    try:
        receive_task = asyncio.create_task(
            receive_audio_bytes()
        )
        heartbeat_task = asyncio.create_task(send_heartbeat())
        await asyncio.gather(receive_task, heartbeat_task)

    except Exception as e:
        print(f"Error during WebSocket operation: {e}")
    finally:
        websocket_active = False
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close(code=websocket_close_code)
            except Exception as e:
                print(f"Error closing WebSocket: {e}")


@router.websocket("/v1/trigger/audio-bytes/listen")
async def websocket_endpoint_audio_bytes(
        websocket: WebSocket, uid: str, sample_rate: int = 8000,
):
    await _websocket_util_audio_bytes(websocket, uid, sample_rate)


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

    # task
    async def receive_audio_bytes():
        nonlocal websocket_active
        nonlocal websocket_close_code

        audiobuffer = bytearray()

        try:
            while websocket_active:
                data = await websocket.receive_bytes()
                header_type = struct.unpack('<I', data[:4])[0]

                # Transcript
                if header_type == 100:
                    segments = json.loads(bytes(data[4:]).decode("utf-8"))
                    asyncio.run_coroutine_threadsafe(trigger_realtime_integrations(uid, segments), loop)
                    asyncio.run_coroutine_threadsafe(realtime_transcript_webhook(uid, segments), loop)
                    continue

                # Audio bytes
                if header_type == 101:
                    audiobuffer.extend(data[4:])
                    if audio_bytes_webhook_delay_seconds and len(
                            audiobuffer) > sample_rate * audio_bytes_webhook_delay_seconds * 2:
                        asyncio.create_task(send_audio_bytes_developer_webhook(uid, sample_rate, audiobuffer.copy()))
                        audiobuffer = bytearray()
                    continue

        except WebSocketDisconnect:
            print("WebSocket disconnected")
        except Exception as e:
            print(f'Could not process audio: error {e}')
            websocket_close_code = 1011
        finally:
            websocket_active = False

    # heart beat
    async def send_heartbeat():
        nonlocal websocket_active
        nonlocal websocket_close_code
        try:
            while websocket_active:
                await asyncio.sleep(20)
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_json({"type": "ping"})
                else:
                    break
        except WebSocketDisconnect:
            print("WebSocket disconnected")
        except Exception as e:
            print(f'Heartbeat error: {e}')
            websocket_close_code = 1011
        finally:
            websocket_active = False

    try:
        receive_task = asyncio.create_task(
            receive_audio_bytes()
        )
        heartbeat_task = asyncio.create_task(send_heartbeat())
        await asyncio.gather(receive_task, heartbeat_task)

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

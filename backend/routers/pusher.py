import struct
import asyncio
import json
import time
from collections import deque

from fastapi import APIRouter
from fastapi.websockets import WebSocketDisconnect, WebSocket
from starlette.websockets import WebSocketState

from utils.apps import is_audio_bytes_app_enabled
from utils.app_integrations import trigger_realtime_integrations, trigger_realtime_audio_bytes
from utils.webhooks import send_audio_bytes_developer_webhook, realtime_transcript_webhook, \
    get_audio_bytes_webhook_seconds

router = APIRouter()

# Audio buffer management class
class AudioBufferManager:
    def __init__(self, max_buffer_size: int = 1024 * 1024):  # 1MB default
        self.max_buffer_size = max_buffer_size
        self.buffer = bytearray()
        self.timestamps = deque()  # Track when data was added
        self.overflow_count = 0
        self.last_cleanup_time = time.time()
    
    def add_data(self, data: bytes) -> bool:
        """Add data to buffer, return True if successful, False if overflow"""
        current_time = time.time()
        
        # Check if adding this data would cause overflow
        if len(self.buffer) + len(data) > self.max_buffer_size:
            self.overflow_count += 1
            # Remove oldest data to make space
            self._cleanup_old_data()
            
            # If still too full, drop the new data
            if len(self.buffer) + len(data) > self.max_buffer_size:
                return False
        
        self.buffer.extend(data)
        self.timestamps.append(current_time)
        return True
    
    def get_data(self, max_bytes: int) -> bytes:
        """Get up to max_bytes from buffer"""
        if len(self.buffer) == 0:
            return b''
        
        data_to_return = self.buffer[:max_bytes]
        self.buffer = self.buffer[max_bytes:]
        
        # Remove corresponding timestamps
        for _ in range(len(data_to_return)):
            if self.timestamps:
                self.timestamps.popleft()
        
        return data_to_return
    
    def clear(self):
        """Clear all data from buffer"""
        self.buffer.clear()
        self.timestamps.clear()
    
    def _cleanup_old_data(self):
        """Remove data older than 5 seconds to prevent time slippage"""
        current_time = time.time()
        cutoff_time = current_time - 5.0  # 5 seconds
        
        # Remove old timestamps and corresponding data
        while self.timestamps and self.timestamps[0] < cutoff_time:
            self.timestamps.popleft()
            if self.buffer:
                self.buffer = self.buffer[1:]  # Remove one byte per timestamp
    
    def get_stats(self) -> dict:
        """Get buffer statistics for debugging"""
        return {
            'buffer_size': len(self.buffer),
            'max_buffer_size': self.max_buffer_size,
            'overflow_count': self.overflow_count,
            'oldest_timestamp': self.timestamps[0] if self.timestamps else None,
            'newest_timestamp': self.timestamps[-1] if self.timestamps else None
        }

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

    # Initialize audio buffer managers
    audio_buffer_manager = AudioBufferManager(max_buffer_size=sample_rate * 10)  # 10 seconds of audio
    trigger_buffer_manager = AudioBufferManager(max_buffer_size=sample_rate * 10)

    # task
    async def receive_tasks():
        nonlocal websocket_active
        nonlocal websocket_close_code

        try:
            while websocket_active:
                data = await websocket.receive_bytes()
                header_type = struct.unpack('<I', data[:4])[0]

                # Transcript
                if header_type == 102:
                    res = json.loads(bytes(data[4:]).decode("utf-8"))
                    segments = res.get('segments')
                    memory_id = res.get('memory_id')
                    asyncio.run_coroutine_threadsafe(trigger_realtime_integrations(uid, segments, memory_id), loop)
                    asyncio.run_coroutine_threadsafe(realtime_transcript_webhook(uid, segments), loop)
                    continue

                # Audio bytes
                if header_type == 101:
                    audio_data = data[4:]
                    
                    # Add to buffers with overflow protection
                    audio_success = audio_buffer_manager.add_data(audio_data)
                    trigger_success = trigger_buffer_manager.add_data(audio_data)
                    
                    if not audio_success or not trigger_success:
                        print(f"Audio buffer overflow detected for uid {uid}. Audio: {audio_success}, Trigger: {trigger_success}")
                    
                    # Process trigger buffer
                    if has_audio_apps_enabled:
                        trigger_data = trigger_buffer_manager.get_data(sample_rate * audio_bytes_trigger_delay_seconds * 2)
                        if trigger_data:
                            asyncio.run_coroutine_threadsafe(
                                trigger_realtime_audio_bytes(uid, sample_rate, trigger_data), loop)
                    
                    # Process webhook buffer
                    if audio_bytes_webhook_delay_seconds:
                        webhook_data = audio_buffer_manager.get_data(sample_rate * audio_bytes_webhook_delay_seconds * 2)
                        if webhook_data:
                            asyncio.run_coroutine_threadsafe(
                                send_audio_bytes_developer_webhook(uid, sample_rate, webhook_data), loop)
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

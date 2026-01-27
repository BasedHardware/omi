import asyncio
import json
import struct
import time
from typing import Callable, List, Optional, Set

from websockets.exceptions import ConnectionClosed

from utils.pusher import connect_to_trigger_pusher


class PusherHandler:
    """Manages the WebSocket connection to the trigger-pusher service for a streaming session."""

    def __init__(
        self,
        uid: str,
        session_id: str,
        language: str,
        sample_rate: int,
        is_active: Callable[[], bool],
        get_current_conversation_id: Callable[[], Optional[str]],
        on_conversation_processed: Optional[Callable[[str], None]] = None,
        private_cloud_sync_enabled: bool = False,
        audio_bytes_webhook_seconds: Optional[int] = None,
        audio_bytes_app_enabled: bool = False,
    ):
        self._uid = uid
        self._session_id = session_id
        self._language = language
        self._sample_rate = sample_rate
        self._is_active = is_active
        self._get_current_conversation_id = get_current_conversation_id
        self._on_conversation_processed = on_conversation_processed

        # Connection state
        self._pusher_ws = None
        self._pusher_connected = False
        self._connect_lock = asyncio.Lock()

        # Transcript buffers
        self._segment_buffers: list = []

        # Audio bytes buffers
        self._audio_buffers = bytearray()
        self._audio_buffer_last_received: Optional[float] = None
        self._audio_bytes_enabled: bool = (
            bool(audio_bytes_webhook_seconds) or audio_bytes_app_enabled or private_cloud_sync_enabled
        )

        # Conversation sync
        self._last_synced_conversation_id: Optional[str] = None

        # Conversation processing
        self._pending_conversation_requests: Set[str] = set()
        self._pending_request_event = asyncio.Event()

    # ---- Connection Management ----

    async def connect(self) -> None:
        """Connect to trigger-pusher WebSocket with retry logic."""
        async with self._connect_lock:
            if self._pusher_connected:
                return
            if self._pusher_ws:
                try:
                    await self._pusher_ws.close()
                    self._pusher_ws = None
                except Exception as e:
                    print(f"PusherHandler: draining failed: {e}", self._uid, self._session_id)
            await self._do_connect()

    async def _do_connect(self) -> None:
        try:
            self._pusher_ws = await connect_to_trigger_pusher(
                self._uid, self._sample_rate, retries=5, is_active=self._is_active
            )
            if self._pusher_ws is None:
                return
            self._pusher_connected = True
        except Exception as e:
            print(f"PusherHandler: connect error: {e}", self._uid, self._session_id)

    async def close(self, code: int = 1000) -> None:
        """Flush buffers and close pusher WebSocket."""
        await self._flush_all(auto_reconnect=False)
        if self._pusher_ws:
            try:
                await self._pusher_ws.close(code)
            except Exception:
                pass

    def is_connected(self) -> bool:
        return self._pusher_connected

    @property
    def has_audio_bytes(self) -> bool:
        return self._audio_bytes_enabled

    # ---- Transcript Sending ----

    def transcript_send(self, segments: list) -> None:
        """Buffer transcript segments for sending to pusher (non-async)."""
        self._segment_buffers.extend(segments)

    async def transcript_consume(self) -> None:
        """Background task: flushes transcript buffer to pusher every 1s."""
        while self._is_active():
            await asyncio.sleep(1)
            if len(self._segment_buffers) > 0:
                await self._transcript_flush(auto_reconnect=True)

    async def _transcript_flush(self, auto_reconnect: bool = True) -> None:
        if self._pusher_connected and self._pusher_ws and len(self._segment_buffers) > 0:
            try:
                conversation_id = self._get_current_conversation_id()
                data = bytearray()
                data.extend(struct.pack("I", 102))
                data.extend(
                    bytes(
                        json.dumps({"segments": self._segment_buffers, "memory_id": conversation_id}),
                        "utf-8",
                    )
                )
                self._segment_buffers = []
                await self._pusher_ws.send(data)
            except ConnectionClosed as e:
                print(f"PusherHandler: transcript connection closed: {e}", self._uid, self._session_id)
                self._pusher_connected = False
            except Exception as e:
                print(f"PusherHandler: transcript flush failed: {e}", self._uid, self._session_id)
        if auto_reconnect and not self._pusher_connected and self._is_active():
            await self.connect()

    # ---- Audio Bytes Sending ----

    def audio_bytes_send(self, audio_bytes: bytes, received_at: float) -> None:
        """Buffer audio bytes for sending to pusher (non-async)."""
        if not self._audio_bytes_enabled:
            return
        self._audio_buffers.extend(audio_bytes)
        self._audio_buffer_last_received = received_at

    async def audio_bytes_consume(self) -> None:
        """Background task: flushes audio buffer to pusher every 1s."""
        while self._is_active():
            await asyncio.sleep(1)
            if len(self._audio_buffers) > 0:
                await self._audio_bytes_flush(auto_reconnect=True)

    async def _audio_bytes_flush(self, auto_reconnect: bool = True) -> None:
        conversation_id = self._get_current_conversation_id()

        # Sync conversation ID first
        if (
            self._pusher_ws
            and conversation_id
            and (self._last_synced_conversation_id is None or conversation_id != self._last_synced_conversation_id)
        ):
            try:
                data = bytearray()
                data.extend(struct.pack("I", 103))
                data.extend(bytes(conversation_id, "utf-8"))
                await self._pusher_ws.send(data)
                self._last_synced_conversation_id = conversation_id
            except ConnectionClosed as e:
                print(f"PusherHandler: audio_bytes conv sync connection closed: {e}", self._uid, self._session_id)
                self._pusher_connected = False
            except Exception as e:
                print(f"PusherHandler: audio_bytes conv sync failed: {e}", self._uid, self._session_id)

        # Send audio bytes
        if self._pusher_connected and self._pusher_ws and len(self._audio_buffers) > 0:
            try:
                buffer_duration_seconds = len(self._audio_buffers) / (self._sample_rate * 2)
                buffer_start_time = (self._audio_buffer_last_received or time.time()) - buffer_duration_seconds

                data = bytearray()
                data.extend(struct.pack("I", 101))
                data.extend(struct.pack("d", buffer_start_time))
                data.extend(self._audio_buffers.copy())
                self._audio_buffers = bytearray()
                await self._pusher_ws.send(data)
            except ConnectionClosed as e:
                print(f"PusherHandler: audio_bytes connection closed: {e}", self._uid, self._session_id)
                self._pusher_connected = False
            except Exception as e:
                print(f"PusherHandler: audio_bytes flush failed: {e}", self._uid, self._session_id)

        if auto_reconnect and not self._pusher_connected and self._is_active():
            await self.connect()

    # ---- Conversation Processing ----

    async def request_conversation_processing(self, conversation_id: str) -> bool:
        """Send opcode 104 to request conversation processing by pusher."""
        if not self._pusher_connected or not self._pusher_ws:
            print(
                f"PusherHandler: not connected, cannot request processing for {conversation_id}",
                self._uid,
                self._session_id,
            )
            return False
        try:
            self._pending_conversation_requests.add(conversation_id)
            self._pending_request_event.set()
            data = bytearray()
            data.extend(struct.pack("I", 104))
            data.extend(bytes(json.dumps({"conversation_id": conversation_id, "language": self._language}), "utf-8"))
            await self._pusher_ws.send(data)
            print(f"PusherHandler: sent process request for {conversation_id}", self._uid, self._session_id)
            return True
        except Exception as e:
            print(f"PusherHandler: process request failed: {e}", self._uid, self._session_id)
            self._pending_conversation_requests.discard(conversation_id)
            return False

    async def pusher_receive(self) -> None:
        """Background task: receives messages from pusher (opcode 201 = conversation processed)."""
        while self._is_active():
            if not self._pending_conversation_requests:
                self._pending_request_event.clear()
                try:
                    await asyncio.wait_for(self._pending_request_event.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    continue

            if not self._pusher_connected or not self._pusher_ws:
                await asyncio.sleep(0.5)
                continue

            try:
                msg = await asyncio.wait_for(self._pusher_ws.recv(), timeout=5.0)
                if not msg or len(msg) < 4:
                    continue
                header_type = struct.unpack('<I', msg[:4])[0]

                if header_type == 201:
                    result = json.loads(msg[4:].decode("utf-8"))
                    conv_id = result.get("conversation_id")
                    self._pending_conversation_requests.discard(conv_id)

                    if "error" in result:
                        print(
                            f"PusherHandler: conversation processing failed: {result['error']}",
                            self._uid,
                            self._session_id,
                        )
                        continue

                    if result.get("success") and self._on_conversation_processed:
                        print(f"PusherHandler: conversation processed: {conv_id}", self._uid, self._session_id)
                        self._on_conversation_processed(conv_id)

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except ConnectionClosed as e:
                print(f"PusherHandler: receive connection closed: {e}", self._uid, self._session_id)
                self._pusher_connected = False
            except Exception as e:
                print(f"PusherHandler: receive error: {e}", self._uid, self._session_id)
                await asyncio.sleep(0.5)

            if not self._pusher_connected and self._is_active():
                await self.connect()

    # ---- Speaker Sample ----

    async def send_speaker_sample_request(self, person_id: str, conv_id: str, segment_ids: List[str]) -> None:
        """Send opcode 105 for speaker sample extraction."""
        if not self._pusher_connected or not self._pusher_ws:
            return
        try:
            data = bytearray()
            data.extend(struct.pack("I", 105))
            data.extend(
                bytes(
                    json.dumps(
                        {
                            "person_id": person_id,
                            "conversation_id": conv_id,
                            "segment_ids": segment_ids,
                        }
                    ),
                    "utf-8",
                )
            )
            await self._pusher_ws.send(data)
            print(
                f"PusherHandler: sent speaker sample request: person={person_id}, {len(segment_ids)} segments",
                self._uid,
                self._session_id,
            )
        except Exception as e:
            print(f"PusherHandler: speaker sample request failed: {e}", self._uid, self._session_id)

    # ---- Helpers ----

    async def _flush_all(self, auto_reconnect: bool = True) -> None:
        await self._audio_bytes_flush(auto_reconnect=auto_reconnect)
        await self._transcript_flush(auto_reconnect=auto_reconnect)

    def get_background_tasks(self) -> list:
        """Returns list of coroutines to run as background tasks via asyncio.gather."""
        tasks = [self.transcript_consume(), self.pusher_receive()]
        if self._audio_bytes_enabled:
            tasks.append(self.audio_bytes_consume())
        return tasks

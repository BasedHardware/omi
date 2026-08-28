"""Soniox real-time streaming client.

Kept out of ``streaming.py`` so the shared module does not grow past the product
line-count ratchet, and so this provider's token-delta protocol stays readable on
its own. Imports flow one way: this module never imports from ``streaming.py``.
"""

import asyncio
import json
import logging
import os
import threading
from typing import Any, Callable, Dict, Final, List, Optional

import websockets

from config.stt_provider_policy import normalized_stt_language
from utils.metrics import OMI_LIVE_STT_MISALIGNED_FRAMES_TOTAL
from utils.stt.socket import STTSocket

logger = logging.getLogger(__name__)

SONIOX_SERVICE_NAME: Final = 'soniox'
SONIOX_WS_URL: Final = os.getenv('SONIOX_WS_URL', 'wss://stt-rt.soniox.com/transcribe-websocket')
SONIOX_MODEL: Final = os.getenv('SONIOX_MODEL', 'stt-rt-v5')
# Soniox closes any socket that receives neither audio nor a keepalive for 20s.
# VAD gating routinely holds audio back for longer than that, so idle sockets die
# as 408 request_timeout unless we fill the gap ourselves.
SONIOX_KEEPALIVE_SECONDS: Final = 10.0


class SafeSonioxSocket(STTSocket):
    """Streaming socket for Soniox real-time.

    Soniox streams token deltas rather than utterances: every message carries a
    ``tokens`` list whose entries flip ``is_final`` once the model commits them.
    Non-final tokens are revised in place, so only final ones are forwarded, and
    consecutive finals from the same speaker are coalesced into one segment to match
    what the listen pipeline expects from the other providers.
    """

    def __init__(
        self,
        ws: Any,
        stream_transcript: Callable[[List[Dict[str, Any]]], None],
        loop: asyncio.AbstractEventLoop,
        preseconds: int = 0,
    ) -> None:
        self._ws: Any = ws
        self._stream_transcript = stream_transcript
        self._loop = loop
        self._preseconds = preseconds
        self._dead = False
        self._closed = False
        self._death_reason: Optional[str] = None
        self._lock = threading.Lock()
        self._send_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=2000)
        self._done_event = asyncio.Event()
        # Odd-length s16le frames would split a sample across messages; carry the
        # trailing byte rather than emit a half sample.
        self._pending_odd_byte: bytes = b''
        self._recv_task: asyncio.Task[None] = asyncio.ensure_future(self._recv_loop(), loop=loop)
        self._send_task: asyncio.Task[None] = asyncio.ensure_future(self._send_loop(), loop=loop)

    @property
    def is_connection_dead(self) -> bool:
        return self._dead

    @property
    def death_reason(self) -> Optional[str]:
        return self._death_reason

    def _mark_dead(self, reason: str) -> None:
        with self._lock:
            if not self._dead:
                self._dead = True
                self._death_reason = reason

    def send(self, data: bytes) -> bool:
        with self._lock:
            if self._dead or self._closed:
                return False
            if not data:
                return True
            aligned = self._pending_odd_byte + data
            self._pending_odd_byte = aligned[-1:] if len(aligned) % 2 else b''
            if self._pending_odd_byte:
                aligned = aligned[:-1]
                OMI_LIVE_STT_MISALIGNED_FRAMES_TOTAL.labels(provider=SONIOX_SERVICE_NAME, stage='provider_send').inc()
            if not aligned:
                return True

        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
        if current_loop is not self._loop and (current_loop is not None or self._loop.is_running()):
            self._mark_dead('send called outside provider event loop')
            return False

        try:
            self._send_queue.put_nowait(aligned)
        except asyncio.QueueFull:
            self._mark_dead('send queue full')
            return False
        return True

    def finalize(self) -> None:
        pass

    def finish(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        try:
            self._loop.call_soon_threadsafe(lambda: self._send_queue.put_nowait(b''))
        except (RuntimeError, Exception):
            pass

    async def drain_and_close(self) -> None:
        try:
            await asyncio.sleep(0)
            try:
                self._send_queue.put_nowait(b'')
            except asyncio.QueueFull:
                pass
            try:
                await asyncio.wait_for(self._done_event.wait(), timeout=60)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                logger.warning('Soniox drain timed out waiting for finished message')
        except Exception:
            pass
        self._recv_task.cancel()
        try:
            await self._ws.close()
        except Exception:
            pass

    async def _send_loop(self) -> None:
        try:
            while not self._closed and not self._dead:
                try:
                    data = await asyncio.wait_for(self._send_queue.get(), timeout=SONIOX_KEEPALIVE_SECONDS)
                except asyncio.TimeoutError:
                    await self._ws.send(json.dumps({'type': 'keepalive'}))
                    continue
                if data == b'':
                    # Documented end-of-audio signal: an empty text frame.
                    await self._ws.send('')
                    break
                await self._ws.send(data)
        except websockets.exceptions.ConnectionClosed as e:
            self._mark_dead(f'ws send closed: {e}')
        except Exception as e:
            self._mark_dead(f'ws send error: {e}')

    async def _recv_loop(self) -> None:
        try:
            async for raw_msg in self._ws:
                if self._closed:
                    break
                try:
                    msg = json.loads(raw_msg)
                except (json.JSONDecodeError, TypeError):
                    continue
                if msg.get('error_code'):
                    err = f"{msg.get('error_code')} {msg.get('error_type', '')} {msg.get('error_message', '')}".strip()
                    logger.error(f'Soniox streaming error: {err}')
                    self._done_event.set()
                    self._mark_dead(f'soniox error: {err}')
                    break

                tokens: List[Any] = msg.get('tokens') or []
                if tokens:
                    self._handle_tokens(tokens)

                if msg.get('finished'):
                    self._done_event.set()
                    break
        except websockets.exceptions.ConnectionClosed as e:
            self._mark_dead(f'ws recv closed: {e}')
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self._mark_dead(f'ws recv error: {e}')
        finally:
            self._done_event.set()

    def _handle_tokens(self, tokens: List[Any]) -> None:
        segments: List[Dict[str, Any]] = []
        for token in tokens:
            if not isinstance(token, dict) or not token.get('is_final'):
                continue
            text = str(token.get('text') or '')
            if not text.strip():
                continue
            start_ms = int(token.get('start_ms') or 0)
            start = start_ms / 1000.0
            if self._preseconds and start < self._preseconds:
                continue
            raw_speaker = token.get('speaker')
            try:
                speaker_idx = max(int(raw_speaker) - 1, 0) if raw_speaker is not None else 0
            except (TypeError, ValueError):
                speaker_idx = 0
            speaker = f'SPEAKER_{speaker_idx:02d}'
            # Live tokens arrive with duration_ms null, so a segment's end has to come
            # from the next token's start; the last one falls back to its own start.
            duration_ms = token.get('duration_ms')
            end = (start_ms + int(duration_ms)) / 1000.0 if duration_ms else start
            if segments:
                segments[-1]['end'] = max(segments[-1]['end'], start - self._preseconds)
            if segments and segments[-1]['speaker'] == speaker:
                segments[-1]['text'] += text
                segments[-1]['end'] = end
                continue
            segments.append(
                {
                    'speaker': speaker,
                    'start': start - self._preseconds,
                    'end': end - self._preseconds,
                    'text': text,
                    'is_user': False,
                    'person_id': None,
                }
            )
        if not segments:
            return
        for segment in segments:
            segment['text'] = segment['text'].strip()
        self._stream_transcript([segment for segment in segments if segment['text']])


async def process_audio_soniox(
    stream_transcript: Callable[[List[Dict[str, Any]]], None],
    sample_rate: int,
    language: str,
    preseconds: int = 0,
) -> SafeSonioxSocket:
    api_key = os.getenv('SONIOX_API_KEY')
    if not api_key:
        raise ValueError('SONIOX_API_KEY environment variable is not set')

    config: Dict[str, Any] = {
        'api_key': api_key,
        'model': SONIOX_MODEL,
        'audio_format': 'pcm_s16le',
        'sample_rate': sample_rate,
        'num_channels': 1,
        'enable_speaker_diarization': True,
        'enable_language_identification': True,
    }
    # 'multi' is auto-detect: send no hint and let identification do the work.
    normalized = normalized_stt_language(language)
    if normalized and language != 'multi':
        config['language_hints'] = [normalized]

    logger.info(f'Connecting to Soniox streaming sample_rate={sample_rate} language={language}')
    ws = await websockets.connect(SONIOX_WS_URL, ping_timeout=15, ping_interval=15)
    await ws.send(json.dumps(config))
    loop = asyncio.get_running_loop()
    sock = SafeSonioxSocket(ws, stream_transcript, loop, preseconds=preseconds)
    logger.info('Soniox streaming connection established')
    return sock

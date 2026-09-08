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

from config.stt_provider_policy import normalized_stt_language, soniox_accepts_language_hint
from utils.metrics import OMI_LIVE_STT_MISALIGNED_FRAMES_TOTAL
from utils.observability.fallback import record_fallback
from utils.stt.socket import STTSocket

logger = logging.getLogger(__name__)

SONIOX_SERVICE_NAME: Final = 'soniox'
SONIOX_WS_URL: Final = os.getenv('SONIOX_WS_URL', 'wss://stt-rt.soniox.com/transcribe-websocket')
SONIOX_MODEL: Final = os.getenv('SONIOX_MODEL', 'stt-rt-v5')
# Soniox closes any socket that receives neither audio nor keepalive for 20s.
# VAD gating routinely holds audio back for longer than that, so idle sockets die
# as 408 request_timeout unless we fill the gap ourselves.
SONIOX_KEEPALIVE_SECONDS: Final = 10.0

# Typed in-stream rejection reasons, mapped off the provider's own error frame
# (``error_code`` + ``error_type``). Prod 2026-08-30/31 (backend-listen):
# 400 invalid_request "No audio received" (~42/30m), 402
# organization_balance_exhausted (~7/30m), 413 max_duration_reached (~3/30m)
# all surfaced as one free-text ERROR signature, indistinguishable in metrics
# and in the terminal-failure reason vocabulary.
SONIOX_DEATH_IDLE_TIMEOUT: Final = 'soniox_idle_timeout'
SONIOX_DEATH_ACCOUNT_STATE: Final = 'soniox_account_state'
SONIOX_DEATH_ROTATION: Final = 'soniox_rotation'
SONIOX_DEATH_INVALID_HINT: Final = 'soniox_invalid_hint'


def soniox_death_reason(error_code: Any, error_type: Any, error_message: Any = None) -> str:
    """Bound a Soniox in-stream error frame to a typed death reason.

    The raw provider text stays on the death latch for logs; this mapping is
    what the bounded terminal-failure vocabulary consumes, so a new provider
    error shape degrades to ``connection_lost`` rather than growing a new
    metric cardinality per message.
    """
    error = str(error_type or '').strip().lower()
    if error == 'organization_balance_exhausted':
        return SONIOX_DEATH_ACCOUNT_STATE
    try:
        code = int(error_code)
    except (TypeError, ValueError):
        return 'connection_lost'
    if code == 400:
        message = str(error_message or '').strip().lower()
        if 'invalid language hint' in message:
            # The provider rejected a ``language_hints`` entry outside its
            # documented vocabulary. Config-shaped, not usage-shaped: this is
            # not the idle watchdog, and reporting it as one hid a recurring
            # connect-time death behind a WARNING (prod 2026-09-02/03).
            return SONIOX_DEATH_INVALID_HINT
        # "No audio received": the idle watchdog fired. The socket's keepalive
        # covers the no-client-audio case; this shape arrives when VAD gating
        # withheld real audio for the whole window.
        return SONIOX_DEATH_IDLE_TIMEOUT
    if code == 413:
        # Documented rotation: open a new WebSocket. The failover path does.
        return SONIOX_DEATH_ROTATION
    return 'connection_lost'


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
        # Typed, bounded death reason (e.g. SONIOX_DEATH_ACCOUNT_STATE) for the
        # terminal-failure vocabulary; None until the socket dies.
        self._typed_death_reason: Optional[str] = None
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

    @property
    def typed_death_reason(self) -> Optional[str]:
        """Bounded reason for the terminal-failure vocabulary (None = untyped)."""
        return self._typed_death_reason

    def _mark_dead(self, reason: str, typed_reason: Optional[str] = None) -> None:
        with self._lock:
            if not self._dead:
                self._dead = True
                self._death_reason = reason
                self._typed_death_reason = typed_reason

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
                    typed = soniox_death_reason(msg.get('error_code'), msg.get('error_type'), msg.get('error_message'))
                    if typed in (SONIOX_DEATH_ACCOUNT_STATE, SONIOX_DEATH_INVALID_HINT):
                        # The provider evaluated the account (402) or the session
                        # config (400 invalid language hint) and refused to
                        # serve: our side of the fence owns the fix, so these
                        # stay at ERROR for the on-call instead of hiding behind
                        # the idle/rotation WARNING that hid this signature.
                        logger.error(f'Soniox streaming error: {err}')
                    else:
                        # Idle-timeout and documented rotation are the
                        # protocol answering how the session was used, not a
                        # provider fault; failing to discriminate kept this the
                        # top backend-listen error signature with no signal.
                        logger.warning('Soniox stream closed: %s', err)
                    self._done_event.set()
                    self._mark_dead(f'soniox error: {err}', typed_reason=typed)
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
    # Hints bias recognition; identification still detects every supported
    # language without one. The provider validates ``language_hints`` against
    # its documented vocabulary and answers ``400 invalid_request Invalid
    # language hint`` — after the WebSocket upgrade already succeeded — for any
    # entry outside it, killing the session at the config frame (prod
    # backend-listen 2026-09-02/03). 'multi' is our auto-detect sentinel, not an
    # ISO code, so it must send no hint; compare on the normalized base code so
    # a capitalized sentinel or a region-tagged locale ('Multi', 'ja-JP') cannot
    # smuggle a rejected entry past the raw-string guard.
    normalized = normalized_stt_language(language)
    if normalized and normalized != 'multi':
        if soniox_accepts_language_hint(normalized):
            config['language_hints'] = [normalized]
        else:
            # Auto-detect serves every language the model supports, so the
            # session stays live; this is a mode change (hinted -> identified)
            # and must be visible to ops, not silently healed.
            record_fallback(
                component='stt_selection',
                from_mode='soniox_language_hint',
                to_mode='soniox_language_identification',
                reason='capability_mismatch',
                outcome='degraded',
            )
            logger.warning(
                'Soniox language hint dropped: language=%s is outside the documented hint vocabulary; '
                'falling back to language identification',
                language,
            )

    logger.info(f'Connecting to Soniox streaming sample_rate={sample_rate} language={language}')
    ws = await websockets.connect(SONIOX_WS_URL, ping_timeout=15, ping_interval=15)
    await ws.send(json.dumps(config))
    loop = asyncio.get_running_loop()
    sock = SafeSonioxSocket(ws, stream_transcript, loop, preseconds=preseconds)
    logger.info('Soniox streaming connection established')
    return sock

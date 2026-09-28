"""Soniox real-time streaming client.

Kept out of ``streaming.py`` so the shared module does not grow past the product
line-count ratchet, and so this provider's token-delta protocol stays readable on
its own. Imports flow one way: this module never imports from ``streaming.py``.
"""

import asyncio
import json
import logging
import os
import random
import threading
import time
from typing import Any, Callable, Dict, Final, List, Optional

import websockets

from config.stt_provider_policy import normalized_stt_language, soniox_accepts_language_hint
from utils.metrics import OMI_LIVE_STT_MISALIGNED_FRAMES_TOTAL
from utils.observability.fallback import record_fallback
from utils.stt.socket import STTSocket
from utils.stt.language_policy import LiveLanguageProfile, soniox_hints
from utils.stt.stream_close import (
    PROVIDER_AUTH_REJECTED,
    PROVIDER_BUDGET_EXHAUSTED,
    PROVIDER_RATE_LIMITED,
    record_stt_stream_close,
)

logger = logging.getLogger(__name__)

SONIOX_SERVICE_NAME: Final = 'soniox'
SONIOX_WS_URL: Final = os.getenv('SONIOX_WS_URL', 'wss://stt-rt.soniox.com/transcribe-websocket')
SONIOX_MODEL: Final = os.getenv('SONIOX_MODEL', 'stt-rt-v5')
# Soniox closes any socket that receives neither audio nor keepalive for 20s.
# VAD gating routinely holds audio back for longer than that, so idle sockets die
# as 408 request_timeout unless we fill the gap ourselves.
SONIOX_KEEPALIVE_SECONDS: Final = 10.0
SONIOX_CONNECT_RETRY_DEADLINE_SECONDS: Final = 5.0
SONIOX_CONNECT_RETRY_DELAYS: Final = (0.35, 0.8, 1.6)
SONIOX_RATE_LIMIT_ERROR_LOG_SECONDS: Final = 300.0
_last_rate_limit_error_log = 0.0
_rate_limit_events: list[float] = []
_rate_limit_log_lock = threading.Lock()

# Typed in-stream rejection reasons, mapped off the provider's own error frame
# (``error_code`` + ``error_type``). Prod 2026-08-30/31 (backend-listen):
# 400 invalid_request "No audio received" (~42/30m), 402
# organization_balance_exhausted (~7/30m), 413 max_duration_reached (~3/30m)
# all surfaced as one free-text ERROR signature, indistinguishable in metrics
# and in the terminal-failure reason vocabulary.
SONIOX_DEATH_IDLE_TIMEOUT: Final = 'soniox_idle_timeout'
SONIOX_DEATH_ROTATION: Final = 'soniox_rotation'
SONIOX_DEATH_INVALID_HINT: Final = 'soniox_invalid_hint'
_SONIOX_BUDGET_ERROR_TYPES: Final = frozenset(
    {
        'organization_balance_exhausted',
        'organization_monthly_budget_exhausted',
        'project_monthly_budget_exhausted',
    }
)


def soniox_death_reason(error_code: Any, error_type: Any, error_message: Any = None) -> str:
    """Bound a Soniox in-stream error frame to a typed death reason.

    The raw provider text stays on the death latch for logs; this mapping is
    what the bounded terminal-failure vocabulary consumes, so a new provider
    error shape degrades to ``connection_lost`` rather than growing a new
    metric cardinality per message.
    """
    from utils.stt.live_rollout import configured_chain_enabled

    error = str(error_type or '').strip().lower()
    try:
        code = int(error_code)
    except (TypeError, ValueError):
        code = None
    if code == 429 or error in {'limit_exceeded', 'rate_limit_exceeded'}:
        return PROVIDER_RATE_LIMITED
    if error in _SONIOX_BUDGET_ERROR_TYPES:
        return PROVIDER_BUDGET_EXHAUSTED
    if code == 402:
        # HTTP 402 is payment/quota regardless of error_type wording. Monthly
        # budget used to fall through here as connection_lost (WARNING), so a
        # 27.5h organization_monthly_budget_exhausted outage never paged.
        return PROVIDER_BUDGET_EXHAUSTED
    if configured_chain_enabled():
        if error == 'organization_quota_exhausted':
            return PROVIDER_BUDGET_EXHAUSTED
        if error == 'invalid_api_key' or code in {401, 403}:
            return PROVIDER_AUTH_REJECTED
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


class SonioxRateLimitError(RuntimeError):
    """Connect-time 429 after the bounded retry window has been spent."""

    reason = PROVIDER_RATE_LIMITED


def _rate_limit_persistent_error(message: str, *, force: bool = False) -> None:
    """Escalate a continuing organization-wide limit once per pod per window."""
    global _last_rate_limit_error_log
    now = time.monotonic()
    with _rate_limit_log_lock:
        _rate_limit_events[:] = [
            event for event in _rate_limit_events if now - event <= SONIOX_RATE_LIMIT_ERROR_LOG_SECONDS
        ]
        _rate_limit_events.append(now)
        if len(_rate_limit_events) > 3:
            del _rate_limit_events[:-3]
        if not force and len(_rate_limit_events) < 3:
            return
        if now - _last_rate_limit_error_log < SONIOX_RATE_LIMIT_ERROR_LOG_SECONDS:
            return
        _last_rate_limit_error_log = now
    logger.error('Soniox real-time rate limiting persists: %s', message)


def _websocket_status(error: BaseException) -> Optional[int]:
    status = getattr(error, 'status_code', None)
    response = getattr(error, 'response', None)
    status = status or getattr(response, 'status_code', None) or getattr(response, 'status', None)
    if status is None:
        return None
    try:
        return int(status)
    except (TypeError, ValueError):
        return None


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
        # Typed, bounded death reason (e.g. PROVIDER_BUDGET_EXHAUSTED) for the
        # terminal-failure vocabulary; None until the socket dies.
        self._typed_death_reason: Optional[str] = None
        self._lock = threading.Lock()
        self._send_queue: asyncio.Queue[bytes | str] = asyncio.Queue(maxsize=2000)
        # A response can end in the middle of a word. Downstream joins distinct
        # segments with spaces, so retain the last word until its boundary is known.
        self._pending_segment: Optional[Dict[str, Any]] = None
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
        def enqueue() -> None:
            if self._dead or self._closed:
                return
            try:
                self._send_queue.put_nowait(json.dumps({'type': 'finalize'}))
            except asyncio.QueueFull:
                self._mark_dead('send queue full')

        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
        if current_loop is self._loop:
            enqueue()
        else:
            try:
                self._loop.call_soon_threadsafe(enqueue)
            except RuntimeError:
                self._mark_dead('finalize called after provider event loop closed')

    def finish(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True

        def finish_on_loop() -> None:
            try:
                self._flush_pending()
            finally:
                try:
                    self._send_queue.put_nowait(b'')
                except asyncio.QueueFull:
                    self._mark_dead('send queue full')

        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
        if current_loop is self._loop:
            finish_on_loop()
        else:
            try:
                self._loop.call_soon_threadsafe(finish_on_loop)
            except RuntimeError:
                self._mark_dead('finish called after provider event loop closed')

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
        self._send_task.cancel()
        # Receive cleanup flushes the last committed word. Complete that callback
        # before the owner tears down its transcript consumer, including timeout.
        await asyncio.gather(self._recv_task, self._send_task, return_exceptions=True)
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
                    record_stt_stream_close(provider=SONIOX_SERVICE_NAME, reason=typed)
                    if typed in (PROVIDER_BUDGET_EXHAUSTED, PROVIDER_AUTH_REJECTED, SONIOX_DEATH_INVALID_HINT):
                        # The provider evaluated the account (402 / monthly budget)
                        # or the session config (400 invalid language hint) and
                        # refused to serve: our side of the fence owns the fix,
                        # so these stay at ERROR for the on-call instead of
                        # hiding behind the idle/rotation WARNING that hid this
                        # signature. Monthly budget used to miss the typed set
                        # and log at WARNING for 27.5h.
                        logger.error(f'Soniox streaming error: {err}')
                    else:
                        # Idle-timeout and documented rotation are the
                        # protocol answering how the session was used, not a
                        # provider fault; failing to discriminate kept this the
                        # top backend-listen error signature with no signal.
                        logger.warning('Soniox stream closed: %s', err)
                        if typed == PROVIDER_RATE_LIMITED:
                            _rate_limit_persistent_error(err)
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
            try:
                self._flush_pending()
            finally:
                self._done_event.set()

    def _flush_pending(self, ready: Optional[List[Dict[str, Any]]] = None) -> None:
        segment = self._pending_segment
        self._pending_segment = None
        if segment is not None and segment['text'].strip():
            segment['text'] = segment['text'].strip()
            segment.pop('_language_mixed', None)
            if ready is not None:
                ready.append(segment)
            else:
                self._stream_transcript([segment])

    def _handle_tokens(self, tokens: List[Any]) -> None:
        ready: List[Dict[str, Any]] = []
        for token in tokens:
            if not isinstance(token, dict) or not token.get('is_final'):
                continue
            text = str(token.get('text') or '')
            if text in {'<end>', '<fin>'}:
                self._flush_pending(ready)
                continue
            # Translation is a separate stream, not spoken transcript content.
            if token.get('translation_status') == 'translation':
                continue
            if text and text[0].isspace():
                self._flush_pending(ready)
            if not text.strip():
                continue
            if token.get('start_ms') is None or token.get('end_ms') is None:
                continue
            start_ms = int(token['start_ms'])
            start = start_ms / 1000.0
            if self._preseconds and start < self._preseconds:
                continue
            raw_speaker = token.get('speaker')
            try:
                speaker_idx = max(int(raw_speaker) - 1, 0) if raw_speaker is not None else 0
            except (TypeError, ValueError):
                speaker_idx = 0
            speaker = f'SPEAKER_{speaker_idx:02d}'
            end = max(start, int(token['end_ms']) / 1000.0)
            pending = self._pending_segment
            if pending is not None and (
                pending['speaker'] != speaker
                or start - self._preseconds - pending['end'] >= 3.0
                or len(pending['text']) + len(text) > 4096
            ):
                self._flush_pending(ready)
            if self._pending_segment is None:
                self._pending_segment = {
                    'speaker': speaker,
                    'start': start - self._preseconds,
                    'end': end - self._preseconds,
                    'text': text,
                    'is_user': False,
                    'person_id': None,
                }
                if token.get('language'):
                    self._pending_segment['_provider_language'] = token['language']
            else:
                self._pending_segment['text'] += text
                self._pending_segment['end'] = max(self._pending_segment['end'], end - self._preseconds)
                token_language = token.get('language')
                if not self._pending_segment.get('_language_mixed') and token_language != self._pending_segment.get(
                    '_provider_language'
                ):
                    self._pending_segment.pop('_provider_language', None)
                    self._pending_segment['_language_mixed'] = True
            if text[-1].isspace():
                self._flush_pending(ready)
        if ready:
            self._stream_transcript(ready)


async def process_audio_soniox(
    stream_transcript: Callable[[List[Dict[str, Any]]], None],
    sample_rate: int,
    language: str,
    preseconds: int = 0,
    *,
    profile: LiveLanguageProfile | None = None,
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
    hints = soniox_hints(language, profile)
    if hints:
        config['language_hints'] = hints
    rejected = (
        profile.primary
        if profile
        and profile.in_scope
        and profile.multi
        and profile.primary_group == 'non_en'
        and os.getenv('STT_MULTI_LANGUAGE_HINTS', 'true').lower() == 'true'
        else normalized_stt_language(language)
    )
    if rejected and rejected != 'multi' and not soniox_accepts_language_hint(rejected):
        # Invalid hints are dropped while identification remains enabled.
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
            rejected,
        )

    logger.info(f'Connecting to Soniox streaming sample_rate={sample_rate} language={language}')
    deadline = time.monotonic() + SONIOX_CONNECT_RETRY_DEADLINE_SECONDS
    ws = None
    last_rate_limit: BaseException | None = None
    for attempt in range(len(SONIOX_CONNECT_RETRY_DELAYS) + 1):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            ws = await asyncio.wait_for(
                websockets.connect(SONIOX_WS_URL, ping_timeout=15, ping_interval=15, open_timeout=remaining),
                timeout=remaining,
            )
            break
        except Exception as error:
            if _websocket_status(error) != 429:
                raise
            last_rate_limit = error
            record_stt_stream_close(provider=SONIOX_SERVICE_NAME, reason=PROVIDER_RATE_LIMITED)
            logger.warning(
                'Soniox real-time connect rate limited (attempt %d/%d)',
                attempt + 1,
                len(SONIOX_CONNECT_RETRY_DELAYS) + 1,
            )
            if attempt >= len(SONIOX_CONNECT_RETRY_DELAYS):
                break
            delay = SONIOX_CONNECT_RETRY_DELAYS[attempt] * random.uniform(0.75, 1.25)
            await asyncio.sleep(min(delay, max(0.0, deadline - time.monotonic())))
    if ws is None:
        _rate_limit_persistent_error('429 responses continued through the bounded connect retry window', force=True)
        raise SonioxRateLimitError('Soniox real-time connect rate limited after bounded retries') from last_rate_limit
    try:
        await ws.send(json.dumps(config))
    except BaseException:
        try:
            await ws.close()
        except Exception:
            logger.warning('Failed to close Soniox socket after config send failure')
        raise
    loop = asyncio.get_running_loop()
    sock = SafeSonioxSocket(ws, stream_transcript, loop, preseconds=preseconds)
    logger.info('Soniox streaming connection established')
    return sock

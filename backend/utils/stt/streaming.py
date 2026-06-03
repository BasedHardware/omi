import asyncio
import io
import os
import random
import threading
import wave
from enum import Enum
from typing import Callable, List, Optional

import websockets
from deepgram import DeepgramClient, DeepgramClientOptions, LiveTranscriptionEvents
from deepgram.clients.live.v1 import LiveOptions

from utils.async_tasks import create_named_task
from utils.byok import get_byok_key
from utils.executors import sync_executor, run_blocking
from utils.http_client import get_stt_client, get_stt_semaphore
from utils.stt.safe_socket import KeepaliveConfig, SafeDeepgramSocket  # noqa: F401 — re-exported for backward compat
from utils.stt.vad_gate import GatedDeepgramSocket
import logging

logger = logging.getLogger(__name__)


headers = {"Authorization": f"Token {os.getenv('DEEPGRAM_API_KEY')}", "Content-Type": "audio/*"}


class STTService(str, Enum):
    deepgram = "deepgram"

    @staticmethod
    def get_model_name(value):
        if value == STTService.deepgram:
            return 'deepgram_streaming'


deepgram_nova3_multi_languages = {
    "multi",
    "en",
    "en-US",
    "en-AU",
    "en-GB",
    "en-IN",
    "en-NZ",
    "es",
    "es-419",
    "fr",
    "fr-CA",
    "de",
    "hi",
    "ru",
    "pt",
    "pt-BR",
    "pt-PT",
    "ja",
    "it",
    "nl",
}
deepgram_nova3_languages = {
    "ar",
    "ar-AE",
    "ar-SA",
    "ar-QA",
    "ar-KW",
    "ar-SY",
    "ar-LB",
    "ar-PS",
    "ar-JO",
    "ar-EG",
    "ar-SD",
    "ar-TD",
    "ar-MA",
    "ar-DZ",
    "ar-TN",
    "ar-IQ",
    "ar-IR",
    "be",
    "bg",
    "bn",
    "bs",
    "ca",
    "cs",
    "da",
    "da-DK",
    "de",
    "de-CH",
    "el",
    "en",
    "en-US",
    "en-AU",
    "en-GB",
    "en-IN",
    "en-NZ",
    "es",
    "es-419",
    "et",
    "fa",
    "fi",
    "fr",
    "fr-CA",
    "he",
    "hi",
    "hr",
    "hu",
    "id",
    "it",
    "ja",
    "kn",
    "ko",
    "ko-KR",
    "lt",
    "lv",
    "mk",
    "mr",
    "ms",
    "nl",
    "nl-BE",
    "no",
    "pl",
    "pt",
    "pt-BR",
    "pt-PT",
    "ro",
    "ru",
    "sk",
    "sl",
    "sr",
    "sv",
    "sv-SE",
    "ta",
    "te",
    "th",
    "th-TH",
    "tl",
    "tr",
    "uk",
    "ur",
    "vi",
    "zh",
    "zh-CN",
    "zh-Hans",
    "zh-HK",
    "zh-Hant",
    "zh-TW",
}


def get_stt_service_for_language(language: str, multi_lang_enabled: bool = True):
    if multi_lang_enabled and language in deepgram_nova3_multi_languages:
        return STTService.deepgram, 'multi', 'nova-3'
    if language in deepgram_nova3_languages:
        return STTService.deepgram, language, 'nova-3'

    # Fallback to deepgram nova-3 with English
    return STTService.deepgram, 'en', 'nova-3'


def should_preserve_filler_words(language: str) -> bool:
    """Return True if filler words should be preserved for the given Deepgram language.

    English filler sounds ("um", "uh") are safe to strip. But in other languages
    those sounds are real words — e.g. Portuguese "um" means "a/one" (#6575).
    """
    return not language.startswith('en')


# Initialize Deepgram client based on environment configuration
is_dg_self_hosted = os.getenv('DEEPGRAM_SELF_HOSTED_ENABLED', '').lower() == 'true'
deepgram_options = DeepgramClientOptions(options={"termination_exception_connect": "true"})

deepgram_cloud_options = DeepgramClientOptions(options={"termination_exception_connect": "true"})
deepgram_cloud_options.url = "https://api.deepgram.com"

if is_dg_self_hosted:
    dg_self_hosted_url = os.getenv('DEEPGRAM_SELF_HOSTED_URL')
    if not dg_self_hosted_url:
        raise ValueError("DEEPGRAM_SELF_HOSTED_URL must be set when DEEPGRAM_SELF_HOSTED_ENABLED is true")
    # Override only the URL while keeping all other options
    deepgram_options.url = dg_self_hosted_url
    deepgram_cloud_options.url = dg_self_hosted_url
    logger.info(f"Using Deepgram self-hosted at: {dg_self_hosted_url}")

deepgram = DeepgramClient(os.getenv('DEEPGRAM_API_KEY'), deepgram_options)

# unused fn
deepgram_beta = DeepgramClient(os.getenv('DEEPGRAM_API_KEY'), deepgram_cloud_options)


async def process_audio_dg(
    stream_transcript,
    language: str,
    sample_rate: int,
    channels: int,
    model: str = 'nova-3',
    keywords: List[str] = [],
    vad_gate=None,
    is_active: Optional[Callable[[], bool]] = None,
):
    """Create a Deepgram streaming connection.

    Args:
        vad_gate: Optional VADStreamingGate. If provided, returns a
            GatedDeepgramSocket that handles VAD gating internally and
            remaps timestamps in the stream_transcript callback.
    """
    logger.info(f'process_audio_dg {language} {sample_rate} {channels}')

    # If gate provided, wrap stream_transcript to remap DG timestamps
    if vad_gate is not None:
        _original_stream_transcript = stream_transcript

        def stream_transcript(segments):
            vad_gate.remap_segments(segments)
            _original_stream_transcript(segments)

    def on_message(self, result, **kwargs):
        sentence = result.channel.alternatives[0].transcript
        if len(sentence) == 0:
            return
        segments = []
        for word in result.channel.alternatives[0].words:
            if not segments:
                segments.append(
                    {
                        'speaker': f"SPEAKER_{word.speaker}",
                        'start': word.start,
                        'end': word.end,
                        'text': word.punctuated_word,
                        'is_user': False,
                        'person_id': None,
                    }
                )
            else:
                last_segment = segments[-1]
                if last_segment['speaker'] == f"SPEAKER_{word.speaker}":
                    last_segment['text'] += f" {word.punctuated_word}"
                    last_segment['end'] = word.end
                else:
                    segments.append(
                        {
                            'speaker': f"SPEAKER_{word.speaker}",
                            'start': word.start,
                            'end': word.end,
                            'text': word.punctuated_word,
                            'is_user': False,
                            'person_id': None,
                        }
                    )

        stream_transcript(segments)

    def on_error(self, error, **kwargs):
        logger.error(f"Deepgram error: {error}")

    logger.info("Connecting to Deepgram")  # Log before connection attempt
    dg_connection = await connect_to_deepgram_with_backoff(
        on_message, on_error, language, sample_rate, channels, model, keywords, is_active=is_active
    )

    if dg_connection is None:
        return None

    # Always wrap with SafeDeepgramSocket for dead-connection detection (#5870)
    safe_conn = SafeDeepgramSocket(dg_connection)

    # Register close-reason handlers that feed into SafeDeepgramSocket
    def on_dg_close(self, close, **kwargs):
        reason = f'DG close event: {close}'
        logger.info('Deepgram connection closed: %s', close)
        safe_conn.set_close_reason(reason)

    def on_dg_error(self, error, **kwargs):
        reason = f'DG error event: {error}'
        logger.warning('Deepgram error (close-reason capture): %s', error)
        safe_conn.set_close_reason(reason)

    dg_connection.on(LiveTranscriptionEvents.Close, on_dg_close)
    dg_connection.on(LiveTranscriptionEvents.Error, on_dg_error)

    # Wrap with VAD gate if provided
    if vad_gate is not None:
        return GatedDeepgramSocket(safe_conn, gate=vad_gate)
    return safe_conn


# Calculate backoff with jitter
def calculate_backoff_with_jitter(attempt, base_delay=1000, max_delay=32000):
    jitter = random.random() * base_delay
    backoff = min(((2**attempt) * base_delay) + jitter, max_delay)
    return backoff


async def connect_to_deepgram_with_backoff(
    on_message,
    on_error,
    language: str,
    sample_rate: int,
    channels: int,
    model: str,
    keywords: List[str] = [],
    retries=3,
    is_active: Optional[Callable[[], bool]] = None,
):
    logger.info("connect_to_deepgram_with_backoff")
    for attempt in range(retries):
        if is_active is not None and not is_active():
            logger.warning("Session ended, aborting Deepgram retry")
            return None
        try:
            result = await run_blocking(
                sync_executor,
                connect_to_deepgram,
                on_message,
                on_error,
                language,
                sample_rate,
                channels,
                model,
                keywords,
            )
            if result is not None:
                return result
            # start() returned False — retry unless this is the last attempt
            if attempt == retries - 1:
                logger.error('Deepgram start() returned False on all %d attempts — giving up', retries)
                return None
            logger.warning('Deepgram start() returned False (attempt %d/%d), retrying...', attempt + 1, retries)
        except Exception as error:
            logger.error(f'An error occurred: {error}')
            if attempt == retries - 1:  # Last attempt
                raise
        backoff_delay = calculate_backoff_with_jitter(attempt)
        logger.warning(f"Waiting {backoff_delay:.0f}ms before next retry...")
        await asyncio.sleep(backoff_delay / 1000)  # Convert ms to seconds for sleep

    raise Exception(f'Could not open socket: All retry attempts failed.')


def _dg_keywords_set(options: LiveOptions, keywords: List[str]):
    if options.model in ['nova-3']:
        options.keyterm = keywords
        return options

    options.keywords = keywords
    return options


def _deepgram_client_for_request() -> DeepgramClient:
    """Return a Deepgram client keyed to the current request's BYOK Deepgram key.

    BYOK users pay Deepgram directly — we don't want to rack up minutes on the
    Omi Deepgram account for them. Self-hosted Deepgram ignores BYOK since
    there's no per-user billing concept there.
    """
    if is_dg_self_hosted:
        return deepgram
    byok = get_byok_key('deepgram')
    if byok:
        return DeepgramClient(byok, deepgram_cloud_options)
    return deepgram


def connect_to_deepgram(
    on_message, on_error, language: str, sample_rate: int, channels: int, model: str, keywords: List[str] = []
):
    try:
        dg_connection = _deepgram_client_for_request().listen.websocket.v("1")
        dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)
        dg_connection.on(LiveTranscriptionEvents.Error, on_error)

        def on_open(self, open, **kwargs):
            logger.info("Connection Open")

        def on_metadata(self, metadata, **kwargs):
            logger.info(f"Metadata: {metadata}")

        def on_speech_started(self, speech_started, **kwargs):
            logger.info("Speech Started")

        def on_utterance_end(self, utterance_end, **kwargs):
            pass

        def on_close(self, close, **kwargs):
            logger.info("Connection Closed")

        def on_unhandled(self, unhandled, **kwargs):
            logger.error(f"Unhandled Websocket Message: {unhandled}")

        dg_connection.on(LiveTranscriptionEvents.Open, on_open)
        dg_connection.on(LiveTranscriptionEvents.Metadata, on_metadata)
        dg_connection.on(LiveTranscriptionEvents.SpeechStarted, on_speech_started)
        dg_connection.on(LiveTranscriptionEvents.UtteranceEnd, on_utterance_end)
        dg_connection.on(LiveTranscriptionEvents.Close, on_close)
        dg_connection.on(LiveTranscriptionEvents.Unhandled, on_unhandled)
        options = LiveOptions(
            punctuate=True,
            no_delay=True,
            endpointing=300,
            language=language,
            interim_results=False,
            smart_format=True,
            profanity_filter=False,
            diarize=True,
            filler_words=should_preserve_filler_words(language),
            channels=channels,
            multichannel=channels > 1,
            model=model,
            sample_rate=sample_rate,
            encoding='linear16',
        )
        if len(keywords) > 0:
            options = _dg_keywords_set(options, keywords)

        result = dg_connection.start(options)
        logger.info(f'Deepgram connection started: {result}')
        if not result:
            logger.error('Deepgram connection start() returned False — connection not established')
            return None
        return dg_connection
    except websockets.exceptions.WebSocketException as e:
        raise Exception(f'Could not open socket: WebSocketException {e}')
    except Exception as e:
        raise Exception(f'Could not open socket: {e}')


# ---------------------------------------------------------------------------
# Parakeet (self-hosted) streaming-shaped STT
#
# The Parakeet service is a *batch* endpoint (POST /v1/transcribe, whole file ->
# {text, segments}). The listen pipeline drives a *streaming* socket (sync .send(pcm)
# + .finish(), async stream_transcript callbacks). This wrapper bridges the two: it
# buffers PCM16 mono into fixed windows, POSTs each window to the service, and feeds
# the resulting segments to stream_transcript — same interface as process_audio_dg.
#
# Gated by HOSTED_PARAKEET_API_URL (unset in prod -> never used; prod stays on Deepgram).
# Diarization is not done here (Parakeet doesn't diarize) — segments come through as a
# single speaker, matching how the backend treats single-channel audio.
# ---------------------------------------------------------------------------

PARAKEET_WINDOW_SECONDS = float(os.getenv('PARAKEET_WINDOW_SECONDS', '6.0'))


def _pcm16_to_wav_bytes(pcm: bytes, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)  # int16
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


class ParakeetStreamingSocket:
    """Streaming-shaped wrapper over the batch Parakeet /v1/transcribe service.

    Mirrors the SafeDeepgramSocket interface the listen pipeline uses (sync send/finish).
    """

    def __init__(
        self, stream_transcript, api_url: str, sample_rate: int, window_seconds: float = PARAKEET_WINDOW_SECONDS
    ):
        self._stream_transcript = stream_transcript
        self._url = api_url.rstrip('/') + '/v1/transcribe'
        self._sample_rate = sample_rate
        self._window_bytes = int(sample_rate * 2 * window_seconds)  # int16 mono
        self._buf = bytearray()
        self._lock = threading.Lock()
        self._emitted_seconds = 0.0
        self._closed = False
        self._pump_task: Optional[asyncio.Task] = None
        # Surfaced to the listen loop via is_connection_dead so a crashed pump is detected
        # and drained like a dead Deepgram socket (the receive loop polls is_connection_dead).
        self._dead = False
        self._dead_reason: Optional[str] = None

    def start(self):
        # Named + tracked so it's supervised/drained like the other WS-scoped tasks.
        self._pump_task = create_named_task(self._pump(), name="parakeet_stt_pump")

    # --- interface the listen pipeline calls ---
    def send(self, data: bytes):
        if self._closed or not data:
            return
        with self._lock:
            self._buf.extend(data)

    async def finish(self):
        """Drain the final (sub-window) chunk INLINE before returning.

        The listen teardown calls this and then closes the client socket / cancels the
        transcript-processing task, so the tail must be transcribed and delivered to
        stream_transcript() *here*, not on the next pump tick (which would be dropped).
        """
        self._closed = True
        pump, self._pump_task = self._pump_task, None
        if pump is not None:
            try:
                # The pump observes _closed, force-flushes whatever remains, then exits.
                await pump
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Parakeet pump await error during finish")
        # Backstop: if the pump died early (and left audio buffered), drain it here so the
        # tail is never silently lost. No-op when the pump already emptied the buffer.
        await self._flush(force=True)

    # --- SafeDeepgramSocket-compatible health interface (the listen loop polls these) ---
    @property
    def is_connection_dead(self) -> bool:
        # Transient POST errors are retried on the next window (stay alive). Only a crashed
        # pump (no consumer for buffered audio) reports dead so the listen loop tears down.
        return self._dead

    @property
    def death_reason(self) -> Optional[str]:
        return self._dead_reason

    @property
    def keepalive_count(self) -> int:
        return 0

    def set_close_reason(self, reason: str) -> None:
        pass

    def finalize(self) -> None:
        # No persistent connection to finalize; the tail is drained by finish().
        pass

    # --- internals ---
    async def _pump(self):
        try:
            while True:
                await asyncio.sleep(0.5)
                closing = self._closed
                await self._flush(force=closing)
                if closing:
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception("Parakeet pump loop error")
            self._dead = True
            self._dead_reason = f'parakeet pump crashed: {e}'

    async def _flush(self, force: bool):
        with self._lock:
            avail = len(self._buf)
            if not (avail >= self._window_bytes or (force and avail > 0)):
                return
            take = avail if force else self._window_bytes
            chunk = bytes(self._buf[:take])
            del self._buf[:take]
            start = self._emitted_seconds
            dur = (take // 2) / self._sample_rate
            self._emitted_seconds += dur

        segments = await self._transcribe_chunk(chunk, start, dur)
        if segments:
            self._stream_transcript(segments)

    async def _transcribe_chunk(self, pcm: bytes, start: float, dur: float) -> List[dict]:
        wav = _pcm16_to_wav_bytes(pcm, self._sample_rate)
        try:
            client = get_stt_client()
            async with get_stt_semaphore():
                resp = await client.post(self._url, files={'file': ('audio.wav', wav, 'audio/wav')})
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"Parakeet transcribe failed: {e}")
            return []

        out: List[dict] = []
        for s in data.get('segments', []) or []:
            text = (s.get('text') or '').strip()
            if not text:
                continue
            out.append(
                {
                    'speaker': 'SPEAKER_0',
                    'start': start + float(s.get('start', 0.0)),
                    'end': start + float(s.get('end', 0.0)),
                    'text': text,
                    'is_user': False,
                    'person_id': None,
                }
            )
        if not out and (data.get('text') or '').strip():
            out.append(
                {
                    'speaker': 'SPEAKER_0',
                    'start': start,
                    'end': start + dur,
                    'text': data['text'].strip(),
                    'is_user': False,
                    'person_id': None,
                }
            )
        return out


async def process_audio_parakeet(
    stream_transcript,
    language: str,
    sample_rate: int,
    channels: int,
    model: str = 'parakeet',
    keywords: List[str] = [],
    vad_gate=None,
    is_active: Optional[Callable[[], bool]] = None,
):
    """Drop-in replacement for process_audio_dg backed by the self-hosted Parakeet service.

    Returns a ParakeetStreamingSocket (sync send/finish) or None if not configured.
    """
    api_url = os.getenv('HOSTED_PARAKEET_API_URL')
    if not api_url:
        logger.error('process_audio_parakeet: HOSTED_PARAKEET_API_URL not set')
        return None
    logger.info(f'process_audio_parakeet {language} {sample_rate} {channels} -> {api_url}')
    socket = ParakeetStreamingSocket(stream_transcript, api_url, sample_rate)
    socket.start()
    return socket

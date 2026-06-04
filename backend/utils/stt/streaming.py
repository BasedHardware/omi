import asyncio
import io
import json
import os
import random
import threading
import urllib.parse
import wave as _wave
from enum import Enum
from typing import Callable, List, Optional

import websockets
from deepgram import DeepgramClient, DeepgramClientOptions, LiveTranscriptionEvents
from deepgram.clients.live.v1 import LiveOptions

from utils.byok import get_byok_key
from utils.executors import sync_executor, run_blocking
from utils.stt.safe_socket import KeepaliveConfig, SafeDeepgramSocket  # noqa: F401 — re-exported for backward compat
from utils.stt.socket import STTSocket
import logging

logger = logging.getLogger(__name__)


headers = {"Authorization": f"Token {os.getenv('DEEPGRAM_API_KEY')}", "Content-Type": "audio/*"}


class STTService(str, Enum):
    deepgram = "deepgram"
    modulate = "modulate"

    @staticmethod
    def get_model_name(value):
        if value == STTService.deepgram:
            return 'deepgram_streaming'
        if value == STTService.modulate:
            return 'modulate_streaming'


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


modulate_languages = {
    'multi',
    'en',
    'af',
    'sq',
    'ar',
    'az',
    'eu',
    'be',
    'bn',
    'bs',
    'bg',
    'ca',
    'zh',
    'hr',
    'cs',
    'da',
    'nl',
    'et',
    'fi',
    'fr',
    'gl',
    'de',
    'el',
    'gu',
    'he',
    'hi',
    'hu',
    'id',
    'it',
    'ja',
    'kn',
    'kk',
    'ko',
    'lv',
    'lt',
    'mk',
    'ms',
    'ml',
    'mr',
    'no',
    'fa',
    'pl',
    'pt',
    'pa',
    'ro',
    'ru',
    'sr',
    'sk',
    'sl',
    'es',
    'sw',
    'sv',
    'tl',
    'ta',
    'te',
    'th',
    'tr',
    'uk',
    'ur',
    'vi',
    'cy',
}

stt_service_models = os.getenv('STT_SERVICE_MODELS', 'dg-nova-3').split(',')


def _normalize_language(language: str) -> str:
    if not language:
        return ''
    return language.split('-')[0].split('_')[0].lower()


def get_stt_service_for_language(language: str, multi_lang_enabled: bool = True):
    base_lang = _normalize_language(language)
    for m in stt_service_models:
        m = m.strip()
        if m.startswith('dg-'):
            dg_model = m.replace('dg-', '', 1)
            if multi_lang_enabled and language in deepgram_nova3_multi_languages:
                return STTService.deepgram, 'multi', dg_model
            if language in deepgram_nova3_languages:
                return STTService.deepgram, language, dg_model
            continue
        if m == 'modulate-velma-2':
            if base_lang in modulate_languages:
                return STTService.modulate, base_lang, 'velma-2'

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
    is_active: Optional[Callable[[], bool]] = None,
):
    logger.info(f'process_audio_dg {language} {sample_rate} {channels}')

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
# Modulate (Velma-2) streaming
# ---------------------------------------------------------------------------


def _build_wav_header(sample_rate: int, bits_per_sample: int = 16, channels: int = 1) -> bytes:
    buf = io.BytesIO()
    with _wave.open(buf, 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(bits_per_sample // 8)
        wf.setframerate(sample_rate)
        wf.writeframes(b'')
    return buf.getvalue()


class SafeModulateSocket(STTSocket):

    def __init__(self, ws, stream_transcript, loop, preseconds: int = 0):
        self._ws = ws
        self._stream_transcript = stream_transcript
        self._loop = loop
        self._preseconds = preseconds
        self._dead = False
        self._closed = False
        self._death_reason: Optional[str] = None
        self._lock = threading.Lock()
        self._header_sent = False
        self._wav_header: Optional[bytes] = None
        self._send_queue: asyncio.Queue = asyncio.Queue(maxsize=2000)
        self._done_event = asyncio.Event()
        self._prev_partial_text: str = ''
        self._prev_partial_start_ms: int = 0
        self._prev_partial_word_count: int = 0
        self._recv_task = asyncio.ensure_future(self._recv_loop(), loop=loop)
        self._send_task = asyncio.ensure_future(self._send_loop(), loop=loop)

    def set_wav_header(self, header: bytes):
        self._wav_header = header

    @property
    def is_connection_dead(self) -> bool:
        return self._dead

    @property
    def death_reason(self) -> Optional[str]:
        return self._death_reason

    def _mark_dead(self, reason: str):
        with self._lock:
            if not self._dead:
                self._dead = True
                self._death_reason = reason

    def send(self, data: bytes) -> None:
        with self._lock:
            if self._dead or self._closed:
                return
            if not self._header_sent and self._wav_header:
                data = self._wav_header + data
                self._header_sent = True

        def _enqueue():
            try:
                self._send_queue.put_nowait(data)
            except asyncio.QueueFull:
                self._mark_dead('send queue full')

        try:
            self._loop.call_soon_threadsafe(_enqueue)
        except RuntimeError:
            self._mark_dead('event loop closed')

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

    async def drain_and_close(self):
        try:
            await asyncio.sleep(0)
            _EOS_SENTINEL = b'__EOS__'
            try:
                self._send_queue.put_nowait(_EOS_SENTINEL)
            except asyncio.QueueFull:
                pass
            try:
                await asyncio.wait_for(self._send_task, timeout=10)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            try:
                await asyncio.wait_for(self._done_event.wait(), timeout=60)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                logger.warning('Modulate drain timed out waiting for done message')
                if self._prev_partial_text:
                    self._flush_partial()
        except Exception:
            pass
        if self._prev_partial_text:
            self._flush_partial()
        self._recv_task.cancel()
        try:
            await self._ws.close()
        except Exception:
            pass

    async def _send_loop(self):
        _EOS_SENTINEL = b'__EOS__'
        try:
            while not self._closed and not self._dead:
                data = await self._send_queue.get()
                if data == b'':
                    break
                if data == _EOS_SENTINEL:
                    # Docs: send empty text frame ("") to signal end of audio stream
                    await self._ws.send('')
                    break
                await self._ws.send(data)
        except websockets.exceptions.ConnectionClosed as e:
            self._mark_dead(f'ws send closed: {e}')
        except Exception as e:
            self._mark_dead(f'ws send error: {e}')

    async def _recv_loop(self):
        try:
            async for raw_msg in self._ws:
                if self._closed:
                    break
                try:
                    msg = json.loads(raw_msg)
                except (json.JSONDecodeError, TypeError):
                    continue

                msg_type = msg.get('type', '')
                if msg_type == 'error':
                    err = msg.get('error', msg.get('message', 'unknown error'))
                    logger.error(f'Modulate streaming error: {err}')
                    if self._prev_partial_text:
                        self._flush_partial()
                    self._done_event.set()
                    self._mark_dead(f'modulate error: {err}')
                    break
                elif msg_type == 'done':
                    logger.info('Modulate streaming done: duration_ms=%s', msg.get('duration_ms'))
                    if self._prev_partial_text:
                        self._flush_partial()
                    self._done_event.set()
                    break
                elif msg_type == 'partial_utterance':
                    pu = msg.get('partial_utterance', msg)
                    self._handle_partial_utterance(pu)
                elif msg_type == 'utterance':
                    utt = msg.get('utterance', msg)
                    self._handle_utterance(utt)
        except websockets.exceptions.ConnectionClosed as e:
            self._mark_dead(f'ws recv closed: {e}')
        except Exception as e:
            self._mark_dead(f'ws recv error: {e}')

    def _handle_partial_utterance(self, msg: dict):
        text = msg.get('text', '').strip()
        if not text:
            return
        start_ms = msg.get('start_ms', 0)
        self._prev_partial_text = text
        self._prev_partial_start_ms = start_ms
        self._prev_partial_word_count = len(text.split())

    def _flush_partial(self):
        text = self._prev_partial_text
        start_ms = self._prev_partial_start_ms
        self._prev_partial_text = ''
        self._prev_partial_word_count = 0
        if not text:
            return
        start = start_ms / 1000.0
        if self._preseconds and start < self._preseconds:
            return
        segments = [
            {
                'speaker': 'SPEAKER_00',
                'start': start,
                'end': start,
                'text': text,
                'is_user': False,
                'person_id': None,
            }
        ]
        self._stream_transcript(segments)

    def _handle_utterance(self, msg: dict):
        text = msg.get('text', '').strip()
        if not text:
            return

        self._prev_partial_text = ''
        self._prev_partial_word_count = 0

        start_ms = msg.get('start_ms', 0)
        duration_ms = msg.get('duration_ms', 0)
        start = start_ms / 1000.0
        end = (start_ms + duration_ms) / 1000.0

        if self._preseconds and start < self._preseconds:
            return

        raw_speaker = msg.get('speaker')
        if isinstance(raw_speaker, int) and raw_speaker >= 1:
            speaker_idx = raw_speaker - 1
        else:
            speaker_idx = 0
        speaker = f'SPEAKER_{speaker_idx:02d}'

        segments = [
            {
                'speaker': speaker,
                'start': start,
                'end': end,
                'text': text,
                'is_user': False,
                'person_id': None,
            }
        ]
        self._stream_transcript(segments)


async def process_audio_modulate(
    stream_transcript,
    sample_rate: int,
    language: str,
    preseconds: int = 0,
):
    api_key = os.getenv('MODULATE_API_KEY')
    if not api_key:
        raise ValueError('MODULATE_API_KEY environment variable is not set')

    params = {
        'api_key': api_key,
        'speaker_diarization': 'true',
        'partial_results': 'true',
        'sample_rate': str(sample_rate),
        'audio_format': 's16le',
        'num_channels': '1',
    }
    if language and language != 'multi':
        params['language'] = language
    uri = f'wss://modulate-developer-apis.com/api/velma-2-stt-streaming?{urllib.parse.urlencode(params)}'

    logger.info(f'Connecting to Modulate Velma-2 streaming sample_rate={sample_rate} language={language}')
    ws = await websockets.connect(uri, ping_timeout=10, ping_interval=10)
    loop = asyncio.get_running_loop()
    sock = SafeModulateSocket(ws, stream_transcript, loop, preseconds=preseconds)
    logger.info('Modulate Velma-2 streaming connection established')
    return sock


def sort_segments_by_start(segments: list) -> list:
    return sorted(segments, key=lambda s: s.get('start', 0))


def make_stream_callback(callback, vad_gate, passthrough: bool):
    if vad_gate is not None and not passthrough:

        def wrapped(segments):
            vad_gate.remap_segments(segments)
            callback(segments)

        return wrapped
    return callback


def sort_transcript_segments_in_place(segments: list) -> None:
    segments.sort(key=lambda s: s.start)

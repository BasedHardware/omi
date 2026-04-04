import asyncio
import os
import random
from enum import Enum
from typing import Callable, List, Optional

import websockets
from deepgram import DeepgramClient, DeepgramClientOptions, LiveTranscriptionEvents
from deepgram.clients.live.v1 import LiveOptions

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


# Language codes supported in nova-2 but NOT in nova-3
deepgram_nova2_languages = {
    "zh",
    "zh-CN",
    "zh-Hans",
    "zh-TW",
    "zh-Hant",
    "zh-HK",
    "th",
    "th-TH",
}
deepgram_nova2_multi_languages = {
    'multi',
    "en",
    "en-US",
    "en-AU",
    "en-GB",
    "en-IN",
    "en-NZ",
    "es",
    "es-419",
}
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
    "bg",
    "ca",
    "cs",
    "da",
    "da-DK",
    "nl",
    "en",
    "en-US",
    "en-AU",
    "en-GB",
    "en-IN",
    "en-NZ",
    "et",
    "fi",
    "nl-BE",
    "fr",
    "fr-CA",
    "de",
    "de-CH",
    "el",
    "hi",
    "hu",
    "id",
    "it",
    "ja",
    "ko",
    "ko-KR",
    "lv",
    "lt",
    "ms",
    "no",
    "pl",
    "pt",
    "pt-BR",
    "pt-PT",
    "ro",
    "ru",
    "sk",
    "es",
    "es-419",
    "sv",
    "sv-SE",
    "tr",
    "uk",
    "vi",
}

# Supported values: dg-nova-3,dg-nova-2
stt_service_models = os.getenv('STT_SERVICE_MODELS', 'dg-nova-3').split(',')


def get_stt_service_for_language(language: str, multi_lang_enabled: bool = True, fair_use_stage: str = 'none'):
    # Fair-use enforcement: throttle/restrict stages force nova-2 to reduce cost (#6314)
    # Pass requested language through — Deepgram handles unsupported langs gracefully.
    if fair_use_stage in ('throttle', 'restrict'):
        if multi_lang_enabled:
            return STTService.deepgram, 'multi', 'nova-2-general'
        return STTService.deepgram, language, 'nova-2-general'

    for m in stt_service_models:
        # DeepGram Nova-3
        if m == 'dg-nova-3':
            if multi_lang_enabled and language in deepgram_nova3_multi_languages:
                return STTService.deepgram, 'multi', 'nova-3'
            if language in deepgram_nova3_languages:
                return STTService.deepgram, language, 'nova-3'
        # DeepGram Nova-2
        elif m == 'dg-nova-2':
            if multi_lang_enabled and language in deepgram_nova2_multi_languages:
                return STTService.deepgram, 'multi', 'nova-2-general'
            if language in deepgram_nova2_languages:
                return STTService.deepgram, language, 'nova-2-general'

    # Fallback to deepgram nova-3
    return STTService.deepgram, 'en', 'nova-3'


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
    model: str = 'nova-2-general',
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
            return await asyncio.to_thread(
                connect_to_deepgram, on_message, on_error, language, sample_rate, channels, model, keywords
            )
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


def connect_to_deepgram(
    on_message, on_error, language: str, sample_rate: int, channels: int, model: str, keywords: List[str] = []
):
    try:
        dg_connection = deepgram.listen.websocket.v("1")
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
            filler_words=False,
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
        return dg_connection
    except websockets.exceptions.WebSocketException as e:
        raise Exception(f'Could not open socket: WebSocketException {e}')
    except Exception as e:
        raise Exception(f'Could not open socket: {e}')

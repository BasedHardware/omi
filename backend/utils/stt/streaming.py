import asyncio
import inspect
import io
import json
import os
import threading
import urllib.parse
import wave as _wave
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, Final, List, Optional, Tuple, cast

import numpy as np
import websockets
from deepgram import DeepgramClient, DeepgramClientOptions, LiveTranscriptionEvents
from deepgram.clients.live.v1 import LiveOptions

from config.stt_provider_policy import (
    MODULATE_PROVIDER,
    PARAKEET_PROVIDER,
    SONIOX_PROVIDER,
    STTServingSurface,
    deepgram_provider_for_runtime,
    default_models_for_surface,
    modulate_supports_language,
    normalized_stt_language,
    parakeet_supports_language,
    provider_for_model_token,
    provider_is_enabled,
    supports_live_multilingual_mode,
)
from utils.async_tasks import create_named_task
from utils.byok import get_byok_key
from utils.executors import sync_executor, run_blocking
from utils.metrics import OMI_LIVE_STT_MISALIGNED_FRAMES_TOTAL
from utils.http_client import get_stt_client, get_stt_semaphore
from utils.stt.safe_socket import SafeDeepgramSocket  # noqa: F401 — re-exported for backward compat
from utils.stt.socket import STTSocket
from utils.stt.soniox import SafeSonioxSocket, process_audio_soniox  # fmt: skip  # pyright: ignore[reportUnusedImport]  # noqa: F401 — re-exported for backward compat
from utils.stt.provider_resilience import (
    EXPECTED_REJECTIONS,
    ProviderCircuitBreaker,
    close_rejected_socket,
    fallback_socket_is_serving,
)
from utils.stt.speaker_embedding import (
    async_extract_embedding_from_bytes,
    compare_embeddings,
)
from utils.stt.speaker_clustering import select_speaker_cluster
from utils.observability.fallback import record_fallback
from utils.other.backoff import calculate_backoff_with_jitter
import logging

logger = logging.getLogger(__name__)


class STTService(str, Enum):
    deepgram = "deepgram"
    modulate = "modulate"
    parakeet = "parakeet"
    soniox = "soniox"

    @staticmethod
    def get_model_name(value: 'STTService') -> Optional[str]:
        if value == STTService.deepgram:
            return 'deepgram_streaming'
        if value == STTService.modulate:
            return 'modulate_streaming'
        if value == STTService.parakeet:
            return 'parakeet_streaming'
        if value == STTService.soniox:
            return 'soniox_streaming'


class ParakeetConnectionError(RuntimeError):
    def __init__(self, reason: str, detail: str = '') -> None:
        self.reason = reason
        super().__init__(detail or reason)


_parakeet_circuit = ProviderCircuitBreaker(
    failure_threshold=int(os.getenv('PARAKEET_CIRCUIT_FAILURE_THRESHOLD', '3')),
    cooldown_seconds=float(os.getenv('PARAKEET_CIRCUIT_COOLDOWN_SECONDS', '30')),
)

_deepgram_circuit = ProviderCircuitBreaker(
    failure_threshold=int(os.getenv('DEEPGRAM_CIRCUIT_FAILURE_THRESHOLD', '3')),
    cooldown_seconds=float(os.getenv('DEEPGRAM_CIRCUIT_COOLDOWN_SECONDS', '30')),
)


_modulate_circuit = ProviderCircuitBreaker(
    failure_threshold=int(os.getenv('MODULATE_CIRCUIT_FAILURE_THRESHOLD', '3')),
    cooldown_seconds=float(os.getenv('MODULATE_CIRCUIT_COOLDOWN_SECONDS', '30')),
)
_soniox_circuit = ProviderCircuitBreaker(
    failure_threshold=int(os.getenv('MODULATE_CIRCUIT_FAILURE_THRESHOLD', '3')),
    cooldown_seconds=float(os.getenv('MODULATE_CIRCUIT_COOLDOWN_SECONDS', '30')),
)


def _circuit_for_primary(primary_service: STTService) -> ProviderCircuitBreaker:
    if primary_service == STTService.parakeet:
        return _parakeet_circuit
    if primary_service == STTService.deepgram:
        return _deepgram_circuit
    if primary_service == STTService.modulate:
        return _modulate_circuit
    if primary_service == STTService.soniox:
        return _soniox_circuit
    raise ValueError(f'connection fallback is not defined for a {primary_service.value} primary')


def open_provider_selection_circuit(provider: str | None, *, reason: str) -> bool:
    """Open a provider's process-local selection circuit after a serve-time death.

    Selection normally learns from connect-time outcomes alone, so a provider
    that accepts the upgrade and dies while serving audio is invisible to it:
    the next reconnect's successful connect resets the failure counter. The
    live-session terminal path calls this so reconnecting clients skip the
    provider that just died for one cooldown window. Returns whether a known
    provider's circuit was opened; unknown provider names are tolerated
    (same shapes metrics accept) and simply report ``False``.
    """
    if not provider:
        return False
    try:
        service = STTService(provider)
    except ValueError:
        return False
    circuit = _circuit_for_primary(service)
    logger.warning('Opening %s selection circuit after serve-time death reason=%s', provider, reason)
    circuit.record_serve_failure()
    return True


def _fallback_failure_reason(error: BaseException) -> str:
    """Classify why a fallback provider could not serve, for the next leg's telemetry."""
    if isinstance(error, (asyncio.TimeoutError, TimeoutError)):
        return 'timeout'
    detail = str(error).lower()
    if 'limit' in detail or 'quota' in detail or 'exhausted' in detail or 'balance' in detail:
        return 'quota'  # incl. Soniox 402 'organization_balance_exhausted'
    return 'provider_5xx'


# Deepgram and Parakeet refuse at connect time, so a returned socket is proof
# enough. Velma-2 accepts the upgrade and only then answers "Monthly usage limit
# reached.", so a Modulate socket is not evidence that the session is served.
_POST_CONNECT_REJECTING_PRIMARIES: Final = frozenset({STTService.modulate})


async def _primary_is_serving(primary_service: STTService, socket: STTSocket) -> bool:
    """Return whether a connected primary is actually serving the session.

    Only providers that reject after the upgrade pay the liveness grace, so live
    session setup keeps its hot path for the providers that fail at connect.
    """
    if primary_service not in _POST_CONNECT_REJECTING_PRIMARIES:
        return True
    return await fallback_socket_is_serving(socket)


async def _connect_serving_fallback(
    connect: Callable[[], Awaitable[Optional[STTSocket]]], service: STTService
) -> STTSocket:
    """Connect a fallback provider and prove it is actually serving before adopting it."""
    socket = await connect()
    if socket is None:
        raise RuntimeError(f'{service.value} returned no socket')
    if not await fallback_socket_is_serving(socket):
        detail = getattr(socket, 'death_reason', None) or 'stream rejected'
        close_rejected_socket(socket)
        raise RuntimeError(f'{service.value} rejected the stream: {detail}')
    return socket


async def connect_stt_socket_with_fallback(
    *,
    primary_service: STTService,
    connect_primary: Callable[[], Awaitable[Optional[STTSocket]]],
    connect_modulate: Optional[Callable[[], Awaitable[Optional[STTSocket]]]] = None,
    connect_deepgram: Optional[Callable[[], Awaitable[Optional[STTSocket]]]] = None,
    connect_parakeet: Optional[Callable[[], Awaitable[Optional[STTSocket]]]] = None,
) -> Tuple[STTSocket, STTService]:
    """Connect the selected primary before audio starts, walking the configured fallbacks.

    ``STT_SERVICE_MODELS`` states an ordered preference, so a primary that
    cannot open a socket must advance to the next configured provider instead
    of failing the session — a Deepgram account rejecting every connect with
    HTTP 402 otherwise takes the whole deployment's live transcription down
    (#11695). The chain must not stop at Modulate either: with Deepgram at HTTP
    402 and Modulate answering 500/over quota, an English session died while a
    healthy Parakeet deployment sat idle behind them in the same list (#11752).
    Modulate is a primary as well as a fallback: a deployment listing
    ``modulate-velma-2,dg-nova-3,parakeet`` lost 100% of its sessions for ~50
    minutes because a Modulate primary bypassed this helper entirely (#11752).

    The circuit is deliberately process-local and never owns capacity. The
    Parakeet service rejects excess streams at its GPU boundary; this helper
    only avoids repeated connection latency while a provider is unhealthy.
    """
    circuit = _circuit_for_primary(primary_service)

    reason = 'circuit_open'
    if circuit.allow_request():
        try:
            socket = await connect_primary()
            if socket is None:
                reason = 'config_incomplete'
                circuit.record_failure()
            elif await _primary_is_serving(primary_service, socket):
                circuit.record_success()
                return socket, primary_service
            else:
                # The primary took the session and then refused it. Release the
                # socket and walk the chain instead of serving a dead stream.
                detail = getattr(socket, 'death_reason', None) or 'stream rejected'
                close_rejected_socket(socket)
                reason = _fallback_failure_reason(RuntimeError(detail))
                circuit.record_failure()
        except ParakeetConnectionError as error:
            reason = error.reason
            if reason in EXPECTED_REJECTIONS:
                circuit.record_rejection(reason)
            else:
                circuit.record_failure()
        except (asyncio.TimeoutError, TimeoutError):
            reason = 'timeout'
            circuit.record_failure()
        except Exception:
            reason = 'provider_5xx'
            circuit.record_failure()

    # A provider is never offered its own failure as a fallback, so the chain
    # excludes the primary: a Modulate primary walks Deepgram then Parakeet
    # (#11752). The relative order of the fallback legs is fixed here and is not
    # parsed out of STT_SERVICE_MODELS; it matches the declared deployment
    # config, and callers already gate each leg on whether the deployment can
    # serve it. Reading the true order off the policy list is a separate change.
    ordered: List[Tuple[STTService, Optional[Callable[[], Awaitable[Optional[STTSocket]]]]]] = [
        (STTService.modulate, connect_modulate),
        (STTService.deepgram, connect_deepgram),
        (STTService.parakeet, connect_parakeet),
    ]
    candidates: List[Tuple[STTService, Callable[[], Awaitable[Optional[STTSocket]]]]] = [
        (service, connect) for service, connect in ordered if connect is not None and service != primary_service
    ]

    from_mode = primary_service.value
    for service, connect in candidates:
        try:
            fallback_socket = await _connect_serving_fallback(connect, service)
        except Exception as error:
            record_fallback(
                component='stt_selection',
                from_mode=from_mode,
                to_mode=service.value,
                reason=reason,
                outcome='exhausted',
            )
            if service == candidates[-1][0]:
                raise
            from_mode = service.value
            reason = _fallback_failure_reason(error)
            continue

        record_fallback(
            component='stt_selection',
            from_mode=from_mode,
            to_mode=service.value,
            reason=reason,
            outcome='recovered',
        )
        return fallback_socket, service

    raise RuntimeError('No STT fallback provider was configured')


async def drain_stt_socket(socket: STTSocket) -> None:
    """Await a serving socket's tail drain, with a synchronous close fallback."""
    drain_and_close = getattr(socket, 'drain_and_close', None)
    if not callable(drain_and_close):
        socket.finish()
        return
    drain_result = drain_and_close()
    if inspect.isawaitable(drain_result):
        await drain_result
        return
    logger.warning('STT provider lacks async tail drain')
    socket.finish()


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


# Compatibility export for callers. Its value is owned by stt_provider_policy.
DEFAULT_STT_SERVICE_MODELS = default_models_for_surface(STTServingSurface.STREAMING)
stt_service_models = os.getenv('STT_SERVICE_MODELS', ','.join(DEFAULT_STT_SERVICE_MODELS)).split(',')


def modulate_is_configured_fallback(language: Optional[str]) -> bool:
    """Return whether Modulate may take over a session whose primary failed.

    ``STT_SERVICE_MODELS`` is an ordered preference list, so Modulate serves a
    failed primary only where the deployment actually lists it and Velma-2
    accepts the session language.
    """
    return (
        'modulate-velma-2' in (model.strip() for model in stt_service_models)
        and provider_is_enabled(MODULATE_PROVIDER, STTServingSurface.STREAMING)
        and modulate_supports_language(language)
    )


def deepgram_fallback_model(language: Optional[str]) -> Optional[str]:
    """Return the Deepgram model that may take over a session whose primary failed.

    Same contract as ``modulate_is_configured_fallback``, but it resolves a model
    rather than answering yes/no: a Modulate primary resolved ``stt_model`` and
    ``stt_language`` for Velma-2, so the caller has no Deepgram model to reuse and
    cannot know which ``dg-*`` deployment the runtime actually lists. ``None``
    means Deepgram must not be offered the session at all.
    """
    if not provider_is_enabled(deepgram_provider_for_runtime(is_dg_self_hosted), STTServingSurface.STREAMING):
        return None
    if not _deepgram_is_available():
        return None
    if language not in deepgram_nova3_multi_languages and language not in deepgram_nova3_languages:
        return None
    for model in (model.strip() for model in stt_service_models):
        if model.startswith('dg-'):
            return model.replace('dg-', '', 1)
    return None


def parakeet_is_configured_fallback(language: Optional[str]) -> bool:
    """Return whether Parakeet may take over a session whose earlier providers failed.

    Same contract as ``modulate_is_configured_fallback``, one provider further
    down the ordered ``STT_SERVICE_MODELS`` preference: the deployment must list
    Parakeet, the policy must serve it, its endpoint must be configured, and it
    must support the session's resolved provider language.
    """
    return (
        STTService.parakeet.value in (model.strip() for model in stt_service_models)
        and provider_is_enabled(PARAKEET_PROVIDER, STTServingSurface.STREAMING)
        and bool(os.getenv('HOSTED_PARAKEET_API_URL'))
        and parakeet_supports_language(STTServingSurface.STREAMING, language or 'en')
    )


def _stt_selection_from_mode(_language: str, base_lang: str) -> str:
    if base_lang and base_lang != 'en':
        return 'requested_non_en'
    if any(m.strip() for m in stt_service_models):
        return 'configured'
    return 'none'


def _requested_stt_language(
    language: Optional[str], base_lang: str, *, multi_lang_enabled: bool, surface: STTServingSurface
) -> str:
    """Resolve the provider language while retaining PTT's explicit input language.

    Live sessions with multi-language enabled must select a provider's auto-detect
    mode. PTT does not load the user's transcription preference, so it keeps its
    explicit language unless the client itself sends the ``multi`` sentinel.
    """
    if base_lang == 'multi' or (
        surface == STTServingSurface.STREAMING
        and multi_lang_enabled
        and language
        and supports_live_multilingual_mode(language)
    ):
        return 'multi'
    return base_lang


def _models_with_preferred_service(
    models: List[str] | Tuple[str, ...], *, preferred_service: Optional[str]
) -> Tuple[str, ...]:
    """Honor a recognized client engine preference within the serving policy."""
    normalized_preference = (preferred_service or '').strip().lower()
    if normalized_preference != STTService.parakeet.value:
        return tuple(models)
    return tuple(model for model in models if model.strip() == STTService.parakeet.value) + tuple(
        model for model in models if model.strip() != STTService.parakeet.value
    )


def get_stt_service_for_language(
    language: Optional[str],
    multi_lang_enabled: bool = True,
    *,
    surface: STTServingSurface = STTServingSurface.STREAMING,
    preferred_service: Optional[str] = None,
    exclude: frozenset[str] = frozenset(),
) -> Tuple[Optional[STTService], Optional[str], Optional[str]]:
    """Select a serving STT provider allowed for the requested product surface.

    ``exclude`` holds provider tokens that already died for this session, so a
    mid-session failover asks for the next provider down the chain rather than
    reselecting the one that just failed.

    A ``dg-*`` configuration serves from whichever Deepgram deployment the
    runtime is configured for — self-hosted when its endpoint is set, otherwise
    the hosted API. Without credentials it falls through to the policy-owned
    alternatives rather than failing the session.
    """
    # Missing language metadata historically meant English. Preserve that
    # behavior without opening a retired-provider fallback for unknown values.
    base_lang = normalized_stt_language(language) or 'en'
    requested_language = _requested_stt_language(
        language,
        base_lang,
        multi_lang_enabled=multi_lang_enabled,
        surface=surface,
    )

    def select(
        models: List[str] | Tuple[str, ...],
    ) -> Tuple[Optional[Tuple[STTService, str, str]], Optional[str]]:
        parakeet_fallback_reason: Optional[str] = None
        for model in _models_with_preferred_service(models, preferred_service=preferred_service):
            model = model.strip()
            if provider_for_model_token(model) in exclude:
                continue
            if (
                model.startswith('dg-')
                and provider_is_enabled(deepgram_provider_for_runtime(is_dg_self_hosted), surface)
                and _deepgram_is_available()
            ):
                dg_model = model.replace('dg-', '', 1)
                if multi_lang_enabled and language in deepgram_nova3_multi_languages:
                    return (STTService.deepgram, 'multi', dg_model), parakeet_fallback_reason
                if language in deepgram_nova3_languages:
                    return (STTService.deepgram, language, dg_model), parakeet_fallback_reason
                continue
            if model == 'parakeet':
                if provider_is_enabled(PARAKEET_PROVIDER, surface) and os.getenv('HOSTED_PARAKEET_API_URL'):
                    if parakeet_supports_language(surface, requested_language):
                        return (STTService.parakeet, requested_language, 'parakeet'), parakeet_fallback_reason
                    else:
                        parakeet_fallback_reason = 'capability_mismatch'
                else:
                    parakeet_fallback_reason = 'config_incomplete'
            if (
                model == 'modulate-velma-2'
                and provider_is_enabled(MODULATE_PROVIDER, surface)
                and modulate_supports_language(requested_language)
            ):
                return (STTService.modulate, requested_language, 'velma-2'), parakeet_fallback_reason
            if model == 'soniox' and provider_is_enabled(SONIOX_PROVIDER, surface) and os.getenv('SONIOX_API_KEY'):
                # Soniox identifies the language itself, so every requested language
                # including 'multi' is serviceable.
                return (STTService.soniox, requested_language, 'soniox'), parakeet_fallback_reason
        return None, parakeet_fallback_reason

    prefers_parakeet = (preferred_service or '').strip().lower() == STTService.parakeet.value

    def record_selected_fallback(
        selected: Tuple[STTService, str, str], *, used_default: bool, parakeet_fallback_reason: Optional[str]
    ) -> None:
        if selected[0] != STTService.parakeet and (prefers_parakeet or parakeet_fallback_reason):
            record_fallback(
                component='stt_selection',
                from_mode=STTService.parakeet.value,
                to_mode=selected[0].value,
                reason=parakeet_fallback_reason
                or (
                    'capability_mismatch'
                    if not parakeet_supports_language(surface, requested_language)
                    else 'config_incomplete'
                ),
                outcome='degraded',
            )
        elif used_default:
            record_fallback(
                component='stt_selection',
                from_mode=_stt_selection_from_mode(language or '', base_lang),
                to_mode=selected[0].value,
                reason='config_incomplete',
                outcome='degraded',
            )

    selected, parakeet_fallback_reason = select(stt_service_models)
    if selected is not None:
        record_selected_fallback(selected, used_default=False, parakeet_fallback_reason=parakeet_fallback_reason)
        return selected

    selected, parakeet_fallback_reason = select(default_models_for_surface(surface))
    if selected is not None:
        record_selected_fallback(selected, used_default=True, parakeet_fallback_reason=parakeet_fallback_reason)
        return selected

    record_fallback(
        component='stt_selection',
        from_mode=_stt_selection_from_mode(language or '', base_lang),
        to_mode='unavailable',
        reason='capability_mismatch',
        outcome='exhausted',
    )
    return None, None, None


def should_preserve_filler_words(language: str) -> bool:
    """Return True if filler words should be preserved for the given Deepgram language.

    English filler sounds ("um", "uh") are safe to strip. But in other languages
    those sounds are real words — e.g. Portuguese "um" means "a/one" (#6575).
    """
    return not language.startswith('en')


# The endpoint is always set explicitly, never the SDK default.
DEEPGRAM_CLOUD_ENDPOINT: Final = 'https://api.deepgram.com'

is_dg_self_hosted = os.getenv('DEEPGRAM_SELF_HOSTED_ENABLED', '').lower() == 'true'
deepgram: Optional[DeepgramClient] = None


def _deepgram_options(endpoint: str) -> DeepgramClientOptions:
    """Build options per client, pinned to an endpoint, never the SDK default.

    DeepgramClient.__init__ writes its key into what it is handed, so a shared
    object strands the managed client on whichever BYOK key came last."""
    options = DeepgramClientOptions(options={"termination_exception_connect": "true"})
    options.url = endpoint
    return options


def _require_self_hosted_deepgram_endpoint(endpoint: str) -> str:
    """Reject the hosted endpoint where a self-hosted one was promised.

    Falling back to the hosted API would bill the wrong account and hide a
    broken self-hosted deployment behind working transcription.
    """
    if not endpoint:
        raise ValueError("DEEPGRAM_SELF_HOSTED_URL must be set when DEEPGRAM_SELF_HOSTED_ENABLED is true")
    if urllib.parse.urlparse(endpoint).hostname == 'api.deepgram.com':
        raise ValueError('DEEPGRAM_SELF_HOSTED_URL must not point to api.deepgram.com')
    return endpoint


_managed_deepgram_lock = threading.RLock()
_managed_deepgram_ready = False


def _build_managed_deepgram_client() -> Optional[DeepgramClient]:
    """Build the account-owned client, or None when no credential is configured."""
    if is_dg_self_hosted:
        endpoint = _require_self_hosted_deepgram_endpoint(os.getenv('DEEPGRAM_SELF_HOSTED_URL') or '')
        logger.info(f'Using Deepgram self-hosted at: {endpoint}')
        return DeepgramClient(os.getenv('DEEPGRAM_API_KEY') or '', _deepgram_options(endpoint))
    api_key = os.getenv('DEEPGRAM_API_KEY')
    if not api_key:
        return None
    logger.info('Using Deepgram hosted API')
    return DeepgramClient(api_key, _deepgram_options(DEEPGRAM_CLOUD_ENDPOINT))


def _managed_deepgram_client() -> Optional[DeepgramClient]:
    """Return the account client, constructing it on first use.

    Deferred so importing this module never depends on Deepgram configuration:
    schema export, test collection and other non-serving entry points import it
    without credentials. Mirrors the lazy client in ``utils/stt/pre_recorded.py``.
    """
    global deepgram, _managed_deepgram_ready
    if _managed_deepgram_ready:
        return deepgram
    with _managed_deepgram_lock:
        if not _managed_deepgram_ready:
            deepgram = _build_managed_deepgram_client()
            _managed_deepgram_ready = True
    return deepgram


def _deepgram_is_available() -> bool:
    """Return whether this request could reach Deepgram at all.

    A BYOK user brings their own credential, so Deepgram stays selectable on a
    runtime that has no account key of its own.
    """
    return _managed_deepgram_client() is not None or bool(get_byok_key('deepgram'))


async def process_audio_dg(
    stream_transcript: Callable[[List[Dict[str, Any]]], None],
    language: str,
    sample_rate: int,
    channels: int,
    model: str = 'nova-3',
    keywords: Optional[List[str]] = None,
    is_active: Optional[Callable[[], bool]] = None,
) -> Optional[SafeDeepgramSocket]:
    logger.info(f'process_audio_dg {language} {sample_rate} {channels}')

    def on_message(self: Any, result: Any, **kwargs: Any) -> None:
        sentence = result.channel.alternatives[0].transcript
        if len(sentence) == 0:
            return
        segments: List[Dict[str, Any]] = []
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

    def on_error(self: Any, error: Any, **kwargs: Any) -> None:
        logger.error(f"Deepgram error: {error}")

    logger.info("Connecting to Deepgram")  # Log before connection attempt
    dg_connection = await connect_to_deepgram_with_backoff(
        on_message, on_error, language, sample_rate, channels, model, keywords or [], is_active=is_active
    )

    if dg_connection is None:
        return None

    # Always wrap with SafeDeepgramSocket for dead-connection detection (#5870)
    safe_conn = SafeDeepgramSocket(dg_connection)

    # Register close-reason handlers that feed into SafeDeepgramSocket
    def on_dg_close(self: Any, close: Any, **kwargs: Any) -> None:
        reason = f'DG close event: {close}'
        logger.info('Deepgram connection closed: %s', close)
        safe_conn.set_close_reason(reason)

    def on_dg_error(self: Any, error: Any, **kwargs: Any) -> None:
        reason = f'DG error event: {error}'
        logger.warning('Deepgram error (close-reason capture): %s', error)
        safe_conn.set_close_reason(reason)

    dg_connection.on(LiveTranscriptionEvents.Close, on_dg_close)
    dg_connection.on(LiveTranscriptionEvents.Error, on_dg_error)

    return safe_conn


async def connect_to_deepgram_with_backoff(
    on_message: Callable[..., Any],
    on_error: Callable[..., Any],
    language: str,
    sample_rate: int,
    channels: int,
    model: str,
    keywords: List[str] = [],
    retries: int = 3,
    is_active: Optional[Callable[[], bool]] = None,
) -> Optional[Any]:
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
    """Return the Deepgram client for the current request.

    BYOK users pay Deepgram directly, so their key serves their requests.
    Self-hosted has no per-user billing and ignores BYOK.
    """
    managed = _managed_deepgram_client()
    if is_dg_self_hosted:
        if managed is None:
            raise RuntimeError('Self-hosted Deepgram is not configured')
        return managed
    byok = get_byok_key('deepgram')
    if byok:
        return DeepgramClient(byok, _deepgram_options(DEEPGRAM_CLOUD_ENDPOINT))
    if managed is None:
        raise RuntimeError('Deepgram is not configured; set DEEPGRAM_API_KEY or provide a BYOK key')
    return managed


def connect_to_deepgram(
    on_message: Callable[..., Any],
    on_error: Callable[..., Any],
    language: str,
    sample_rate: int,
    channels: int,
    model: str,
    keywords: List[str] = [],
) -> Optional[Any]:
    try:
        dg_connection: Any = _deepgram_client_for_request().listen.websocket.v("1")
        dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)
        dg_connection.on(LiveTranscriptionEvents.Error, on_error)

        def on_open(self: Any, open: Any, **kwargs: Any) -> None:
            logger.info("Connection Open")

        def on_metadata(self: Any, metadata: Any, **kwargs: Any) -> None:
            logger.info(f"Metadata: {metadata}")

        def on_speech_started(self: Any, speech_started: Any, **kwargs: Any) -> None:
            logger.info("Speech Started")

        def on_utterance_end(self: Any, utterance_end: Any, **kwargs: Any) -> None:
            pass

        def on_close(self: Any, close: Any, **kwargs: Any) -> None:
            logger.info("Connection Closed")

        def on_unhandled(self: Any, unhandled: Any, **kwargs: Any) -> None:
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
        # `keywords` can be None (e.g. the multi-channel / phone-call path opens the
        # socket without passing a vocabulary list). Guard against `len(None)`, which
        # previously raised "object of type 'NoneType' has no len()" and aborted the
        # socket open, leaving the client stuck in a reconnect loop.
        if keywords:
            options = _dg_keywords_set(options, keywords)

        result: Any = dg_connection.start(options)
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


def _build_wav_header(sample_rate: int, bits_per_sample: int = 16, channels: int = 1) -> bytes:  # type: ignore[reportUnusedFunction]  # exported, exercised by tests/unit/test_modulate_stt.py
    buf = io.BytesIO()
    with _wave.open(buf, 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(bits_per_sample // 8)
        wf.setframerate(sample_rate)
        wf.writeframes(b'')
    return buf.getvalue()


MODULATE_DEATH_SERVE_ERROR: Final = 'modulate_serve_error'

# Velma's in-stream error frames are free text, so the fault boundary is
# matched on normalized text. Server-fault shapes say the provider could not
# serve the stream it accepted (5xx wording, or an explicit account-state
# refusal); everything else — invalid audio we sent, rate limits — is either
# our fault or this session's, and must not bench the provider fleet-wide.
_MODULATE_SERVER_FAULT_MARKERS: Final = (
    'internal server error',
    'internal error',
    'unable to complete the request',
    'server error',
    'monthly usage limit',  # account-state refusal: no stream can be served
    'usage limit reached',
    'quota exceeded',
)


def modulate_death_reason(err: Any) -> Optional[str]:
    """Bound a Velma in-stream error frame to a typed death reason.

    Returns ``MODULATE_DEATH_SERVE_ERROR`` when the text says the provider
    failed to serve the stream it accepted, else ``None`` (untyped — the raw
    text stays on the death latch for logs). New provider wordings degrade to
    untyped rather than growing a new bounded token per message.
    """
    normalized = str(err or '').strip().lower().rstrip('.')
    if not normalized:
        return None
    if any(marker in normalized for marker in _MODULATE_SERVER_FAULT_MARKERS):
        return MODULATE_DEATH_SERVE_ERROR
    return None


class SafeModulateSocket(STTSocket):
    def __init__(
        self,
        ws: Any,
        stream_transcript: Callable[[List[Dict[str, Any]]], None],
        loop: asyncio.AbstractEventLoop,
        preseconds: int = 0,
    ) -> None:
        self._ws: Any = ws
        self._stream_transcript: Callable[[List[Dict[str, Any]]], None] = stream_transcript
        self._loop: asyncio.AbstractEventLoop = loop
        self._preseconds: int = preseconds
        self._dead = False
        self._closed = False
        self._death_reason: Optional[str] = None
        # Typed, bounded death reason (MODULATE_DEATH_SERVE_ERROR) for the
        # terminal-failure vocabulary; None until the socket dies.
        self._typed_death_reason: Optional[str] = None
        self._lock = threading.Lock()
        self._header_sent = False
        self._wav_header: Optional[bytes] = None
        self._send_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=2000)
        self._done_event = asyncio.Event()
        self._prev_partial_text: str = ''
        self._prev_partial_start_ms: int = 0
        self._prev_partial_word_count: int = 0
        # Velma rejects any s16le frame that is not a whole number of samples with
        # {"type":"error","error":"Invalid input audio"} and then closes the socket, so a
        # single odd-length frame ends the session even after valid audio. Nothing upstream
        # guarantees even-length buffers, so carry a trailing odd byte to the next frame.
        self._pending_odd_byte: bytes = b''
        self._recv_task: asyncio.Task[None] = asyncio.ensure_future(self._recv_loop(), loop=loop)
        self._send_task: asyncio.Task[None] = asyncio.ensure_future(self._send_loop(), loop=loop)

    def set_wav_header(self, header: bytes) -> None:
        self._wav_header = header

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
        """Synchronously accept audio only when it reaches the provider queue.

        The listen handler runs on ``self._loop``.  A producer on a different
        event loop cannot safely wait for a queue callback without blocking that
        loop, so it is treated as a terminal ownership error rather than
        optimistically dropping audio.
        """
        with self._lock:
            if self._dead or self._closed:
                return False
            if not data:
                # b'' is this socket's shutdown sentinel: _send_loop breaks on it and finish()
                # uses it to stop the loop. Enqueuing an empty audio frame would therefore end
                # the send loop mid-session while the socket still reports itself alive, so every
                # later frame would be queued and never sent. The Parakeet sockets guard the same
                # way. The header stays pending because _header_sent is only set once it is queued.
                return True
            aligned = self._pending_odd_byte + data
            self._pending_odd_byte = aligned[-1:] if len(aligned) % 2 else b''
            if self._pending_odd_byte:
                aligned = aligned[:-1]
                misaligned = True
            else:
                misaligned = False
            if misaligned:
                OMI_LIVE_STT_MISALIGNED_FRAMES_TOTAL.labels(
                    provider=STTService.modulate.value, stage='provider_send'
                ).inc()
            if not aligned:
                # One carried byte and nothing else yet: it is buffered, not dropped.
                return True
            prepend_header = not self._header_sent and self._wav_header is not None
            queued_data = (self._wav_header or b'') + aligned if prepend_header else aligned

        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if current_loop is not self._loop:
            # This only occurs in synchronous tests / shutdown code where the
            # provider loop is stopped, so no concurrent queue consumer exists.
            # It remains a truthful immediate enqueue rather than a deferred
            # cross-loop callback. A live foreign loop is a terminal misuse.
            if current_loop is not None or self._loop.is_running():
                self._mark_dead('send called outside provider event loop')
                return False

        try:
            self._send_queue.put_nowait(queued_data)
        except asyncio.QueueFull:
            self._mark_dead('send queue full')
            return False

        if prepend_header:
            with self._lock:
                self._header_sent = True
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

    async def _send_loop(self) -> None:
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

    async def _recv_loop(self) -> None:
        try:
            async for raw_msg in self._ws:
                if self._closed:
                    break
                try:
                    loaded: object = json.loads(raw_msg)
                except (json.JSONDecodeError, TypeError):
                    continue
                if not isinstance(loaded, dict):
                    continue
                msg: Dict[str, Any] = cast(Dict[str, Any], loaded)

                msg_type = msg.get('type', '')
                if msg_type == 'error':
                    err = msg.get('error', msg.get('message', 'unknown error'))
                    typed = modulate_death_reason(err)
                    if typed is not None:
                        # The provider accepted the stream and then failed to
                        # serve it: a provider fault, and the outage signal an
                        # on-call needs (backend-listen #3 signature,
                        # 2026-08-31: ×11/30m "Internal server error", ×5/30m
                        # "Unable to complete the request").
                        logger.error(f'Modulate streaming error: {err}')
                    else:
                        # Client/session-caused frames (e.g. invalid audio we
                        # sent) are the protocol answering, not an outage.
                        logger.warning(f'Modulate stream closed: {err}')
                    if self._prev_partial_text:
                        self._flush_partial()
                    self._done_event.set()
                    self._mark_dead(f'modulate error: {err}', typed_reason=typed)
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
            # A clean async-for exhaustion means the provider closed the upstream
            # WebSocket without raising. A local drain (self._closed) or an
            # explicit provider 'done' (self._done_event) is expected
            # finalization; any other clean close is unexpected provider death and
            # must latch terminal so the listen loop propagates it without waiting
            # for another client audio frame (#10028).
            if not self._closed and not self._done_event.is_set():
                self._mark_dead('modulate ws closed cleanly without terminal frame')
        except websockets.exceptions.ConnectionClosed as e:
            self._mark_dead(f'ws recv closed: {e}')
        except Exception as e:
            self._mark_dead(f'ws recv error: {e}')

    def _handle_partial_utterance(self, msg: Dict[str, Any]) -> None:
        # Modulate sends cumulative partial_utterance messages during streaming
        # (e.g., "He", "He could", "He could hardly"...) but these are preview-only.
        # We buffer them here and only forward the final `utterance` via _handle_utterance.
        #
        # Limitation: the user sees no live text until the utterance finalizes
        # (after the speech segment completes). For continuous speech, this can be
        # the entire clip duration. Modulate has no endpointing config to control this.
        # Deepgram uses endpointing=300ms to deliver finalized chunks mid-stream.
        #
        # To add live preview from partials, implement delta extraction (Option C-lite):
        # track committed words, emit only new stable words as incremental segments.
        # This would require careful handling of Modulate's occasional mid-partial
        # text revisions and start_ms shifts.
        text = msg.get('text', '').strip()
        if not text:
            return
        start_ms = msg.get('start_ms', 0)
        self._prev_partial_text = text
        self._prev_partial_start_ms = start_ms
        self._prev_partial_word_count = len(text.split())

    def _flush_partial(self) -> None:
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

    def _handle_utterance(self, msg: Dict[str, Any]) -> None:
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
    stream_transcript: Callable[[List[Dict[str, Any]]], None],
    sample_rate: int,
    language: str,
    preseconds: int = 0,
) -> SafeModulateSocket:
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


# --- Parakeet (self-hosted, opt-in) ---------------------------------------------------------------
PARAKEET_WINDOW_SECONDS = float(os.getenv('PARAKEET_WINDOW_SECONDS', '6.0'))
PARAKEET_WS_CONNECT_TIMEOUT = float(os.getenv('PARAKEET_WS_CONNECT_TIMEOUT', '10.0'))


def _pcm16_to_wav_bytes(pcm: bytes, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with _wave.open(buf, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)  # int16
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


class ParakeetStreamingSocket(STTSocket):
    """Streaming-shaped wrapper over the batch Parakeet /v1/transcribe service.

    Implements the STTSocket interface the listen pipeline (and the VAD gate) expect: sync
    send/finish/finalize plus the is_connection_dead/death_reason properties. The real tail
    drain is async drain_and_close(), which the listen teardown awaits.
    """

    def __init__(
        self,
        stream_transcript: Callable[[List[Dict[str, Any]]], None],
        api_url: str,
        sample_rate: int,
        window_seconds: float = PARAKEET_WINDOW_SECONDS,
    ) -> None:
        self._stream_transcript: Callable[[List[Dict[str, Any]]], None] = stream_transcript
        self._url = api_url.rstrip('/') + '/v1/transcribe'
        self._sample_rate = sample_rate
        self._window_bytes = int(sample_rate * 2 * window_seconds)  # int16 mono
        self._buf = bytearray()
        self._lock = threading.Lock()
        self._emitted_seconds = 0.0
        self._closed = False
        self._pump_task: Optional[asyncio.Task[None]] = None
        # Surfaced to the listen loop via is_connection_dead so a crashed pump is detected
        # and drained like a dead Deepgram socket (the receive loop polls is_connection_dead).
        self._dead = False
        self._dead_reason: Optional[str] = None

        # Basic online diarization: Parakeet returns no speaker info, so we embed each segment's
        # voice (via the same hosted embedding service the listen pipeline uses downstream) and
        # cluster into session-stable SPEAKER_N labels. Opt-in: only when that service is wired up.
        self._diarize = bool(os.getenv('HOSTED_SPEAKER_EMBEDDING_API_URL')) and (
            os.getenv('PARAKEET_DIARIZATION', '1') == '1'
        )
        self._spk_centroids: List[np.ndarray[Any, Any]] = []  # running-mean embedding per discovered speaker
        self._spk_counts: List[int] = []
        self._last_speaker = 0  # reused for clips too short to embed / on transient embed failures

    def start(self) -> None:
        # Named + tracked so it's supervised/drained like the other WS-scoped tasks.
        self._pump_task = create_named_task(self._pump(), name="parakeet_stt_pump")

    # --- STTSocket interface the listen pipeline / VAD gate call (all sync) ---
    def send(self, data: bytes) -> bool:
        if self._closed or self._dead or getattr(self, '_finalized', False):
            return False
        if not data:
            return True
        with self._lock:
            self._buf.extend(data)
        return True

    def finish(self) -> None:
        # Sync close signal (ABC requirement; the VAD gate calls this). The pump observes
        # _closed, force-flushes, and exits; the awaited tail drain happens in drain_and_close().
        self._closed = True

    def finalize(self) -> None:
        # No persistent connection to finalize; the tail is drained by drain_and_close().
        pass

    @property
    def is_connection_dead(self) -> bool:
        # Transient POST errors are retried on the next window (stay alive). Only a crashed
        # pump (no consumer for buffered audio) reports dead so the listen loop tears down.
        return self._dead

    @property
    def death_reason(self) -> Optional[str]:
        return self._dead_reason

    # --- async tail drain awaited by the listen teardown ---
    async def drain_and_close(self) -> None:
        """Drain the final (sub-window) chunk INLINE before returning.

        The listen teardown awaits this and then closes the client socket / cancels the
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
                logger.exception("Parakeet pump await error during drain")
        # Backstop: if the pump died early (and left audio buffered), drain it here so the
        # tail is never silently lost. No-op when the pump already emptied the buffer.
        await self._flush(force=True)

    # --- internals ---
    async def _pump(self) -> None:
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

    async def _flush(self, force: bool) -> None:
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

    async def _assign_speaker(self, seg_pcm: bytes) -> int:
        """Cluster a segment's voice embedding into a session-stable speaker index.

        Online greedy clustering uses the short-clip threshold and cluster cap from
        speaker_clustering. Once the cap is full, the nearest centroid absorbs misses.
        Falls back to the previous speaker when diarization is off, the clip is too short
        to embed, or the embedding service errs, so a transient failure never drops text.
        """
        if not self._diarize:
            return 0
        # async_extract_embedding_from_bytes needs >= MIN_EMBEDDING_AUDIO_DURATION (0.5s); give a
        # little margin. Shorter clips (back-channels, one-word turns) inherit the running speaker.
        if len(seg_pcm) < int(self._sample_rate * 2 * 0.6):
            return self._last_speaker
        try:
            wav = _pcm16_to_wav_bytes(seg_pcm, self._sample_rate)
            emb = await async_extract_embedding_from_bytes(wav)
        except Exception as e:
            logger.warning(f"Parakeet diarization embed failed; reusing speaker {self._last_speaker}: {e}")
            return self._last_speaker

        best_i, create_new, _, capped = select_speaker_cluster(emb, self._spk_centroids, compare_embeddings)
        if not create_new:
            if capped:
                # The cap forced this merge; the embedding missed every centroid,
                # so folding it into a running mean would drag that centroid
                # toward a different speaker. Report the degraded outcome.
                record_fallback(
                    component='other',
                    from_mode='new_speaker_centroid',
                    to_mode='nearest_centroid',
                    reason='capacity_full',
                    outcome='degraded',
                    log=logger,
                )
                self._last_speaker = best_i
                return best_i
            # Running-mean keeps the centroid stable as the speaker keeps talking.
            n = self._spk_counts[best_i]
            self._spk_centroids[best_i] = (self._spk_centroids[best_i] * n + emb) / (n + 1)
            self._spk_counts[best_i] = n + 1
            self._last_speaker = best_i
            return best_i

        self._spk_centroids.append(emb)
        self._spk_counts.append(1)
        self._last_speaker = best_i
        return self._last_speaker

    def _slice_pcm(self, pcm: bytes, rel_start: float, rel_end: float) -> bytes:
        """Window-relative [rel_start, rel_end] seconds → PCM16 byte slice (clamped)."""
        b0 = max(0, int(rel_start * self._sample_rate) * 2)
        b1 = min(len(pcm), int(rel_end * self._sample_rate) * 2)
        return pcm[b0:b1] if b1 > b0 else b''

    async def _transcribe_chunk(self, pcm: bytes, start: float, dur: float) -> List[Dict[str, Any]]:
        wav = _pcm16_to_wav_bytes(pcm, self._sample_rate)
        try:
            client = get_stt_client()
            async with get_stt_semaphore():
                resp = await client.post(self._url, files={'file': ('audio.wav', wav, 'audio/wav')})
            resp.raise_for_status()
            loaded: object = resp.json()
        except Exception as e:
            logger.error(f"Parakeet transcribe failed: {e}")
            return []

        if not isinstance(loaded, dict):
            return []
        data: Dict[str, Any] = cast(Dict[str, Any], loaded)

        out: List[Dict[str, Any]] = []
        segments_raw: object = data.get('segments', [])
        segments: List[object] = cast(List[object], segments_raw) if isinstance(segments_raw, list) else []
        for s in segments:
            if not isinstance(s, dict):
                continue
            seg: Dict[str, Any] = cast(Dict[str, Any], s)
            text = (seg.get('text') or '').strip()
            if not text:
                continue
            rel_start = float(seg.get('start', 0.0))
            rel_end = float(seg.get('end', rel_start))
            speaker = await self._assign_speaker(self._slice_pcm(pcm, rel_start, rel_end))
            out.append(
                {
                    'speaker': f'SPEAKER_{speaker}',
                    'start': start + rel_start,
                    'end': start + rel_end,
                    'text': text,
                    'is_user': False,
                    'person_id': None,
                }
            )
        if not out and (data.get('text') or '').strip():
            speaker = await self._assign_speaker(pcm)
            out.append(
                {
                    'speaker': f'SPEAKER_{speaker}',
                    'start': start,
                    'end': start + dur,
                    'text': str(data.get('text', '')).strip(),
                    'is_user': False,
                    'person_id': None,
                }
            )
        return out


class ParakeetWebSocketSocket(STTSocket):
    """True streaming via Parakeet /v3/stream WebSocket with server-side VAD + diarization."""

    def __init__(
        self,
        stream_transcript: Callable[[List[Dict[str, Any]]], None],
        ws_url: str,
        sample_rate: int,
    ) -> None:
        self._stream_transcript: Callable[[List[Dict[str, Any]]], None] = stream_transcript
        self._ws_url = ws_url
        self._sample_rate = sample_rate
        self._send_queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue(maxsize=1000)
        self._closed = False
        self._dead = False
        self._dead_reason: Optional[str] = None
        self._ws: Any = None
        self._sender_task: Optional[asyncio.Task[None]] = None
        self._receiver_task: Optional[asyncio.Task[None]] = None
        self._connected_event = asyncio.Event()
        self._startup_event = asyncio.Event()
        self._startup_failure_reason = 'provider_5xx'

    async def start(self) -> None:
        self._sender_task = create_named_task(self._run(), name="parakeet_ws_stream")
        try:
            await asyncio.wait_for(self._startup_event.wait(), timeout=PARAKEET_WS_CONNECT_TIMEOUT)
        except asyncio.TimeoutError:
            logger.error(f'Parakeet WS connect timeout after {PARAKEET_WS_CONNECT_TIMEOUT}s')
            self._mark_dead(f'parakeet ws connect timeout after {PARAKEET_WS_CONNECT_TIMEOUT}s')
            self._startup_failure_reason = 'timeout'
            self._closed = True
            self._cancel_task(self._sender_task)
            raise ParakeetConnectionError('timeout', self._dead_reason or 'Parakeet connect timeout')
        if not self._connected_event.is_set():
            logger.error(f'Parakeet WS failed before connection: {self._dead_reason}')
            raise ParakeetConnectionError(
                self._startup_failure_reason,
                self._dead_reason or 'parakeet ws failed before connection',
            )
        logger.info('Parakeet WS connected successfully')

    def send(self, data: bytes) -> bool:
        if self._closed or self._dead:
            return False
        if not data:
            return True
        try:
            self._send_queue.put_nowait(data)
        except asyncio.QueueFull:
            self._mark_dead('parakeet ws send queue full')
            return False
        return True

    def finish(self) -> None:
        self._finalized = True
        self._queue_finalize_nowait()

    def finalize(self) -> None:
        self._finalized = True
        self._queue_finalize_nowait()

    @property
    def is_connection_dead(self) -> bool:
        return self._dead

    @property
    def death_reason(self) -> Optional[str]:
        return self._dead_reason

    async def drain_and_close(self) -> None:
        if self._connected_event.is_set():
            await self._send_queue.put(None)
        self._closed = True
        if self._sender_task and not self._sender_task.done():
            try:
                await asyncio.wait_for(self._sender_task, timeout=10)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._cancel_task(self._sender_task)
        if self._receiver_task and not self._receiver_task.done():
            try:
                await asyncio.wait_for(self._receiver_task, timeout=10)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._cancel_task(self._receiver_task)

    def _mark_dead(self, reason: str) -> None:
        self._dead = True
        self._dead_reason = reason

    def _cancel_task(self, task: Optional[asyncio.Task[None]]) -> None:
        if task and not task.done():
            task.cancel()

    def _queue_finalize_nowait(self) -> None:
        if self._closed:
            return
        try:
            self._send_queue.put_nowait(None)
        except asyncio.QueueFull:
            self._mark_dead('parakeet ws send queue full while finalizing')

    async def _run(self) -> None:
        url = f"{self._ws_url}?sample_rate={self._sample_rate}"

        try:
            async with websockets.connect(url, max_size=10 * 1024 * 1024) as ws:
                self._ws = ws
                ready_raw = await asyncio.wait_for(ws.recv(), timeout=PARAKEET_WS_CONNECT_TIMEOUT)
                try:
                    ready = json.loads(ready_raw) if isinstance(ready_raw, str) else None
                except json.JSONDecodeError as error:
                    raise RuntimeError('Parakeet returned an invalid readiness frame') from error
                if not isinstance(ready, dict) or ready.get('type') != 'ready':
                    raise RuntimeError('Parakeet did not confirm stream admission')
                self._receiver_task = create_named_task(self._receive_loop(ws), name="parakeet_ws_recv")
                self._connected_event.set()
                self._startup_event.set()

                while True:
                    try:
                        data = await asyncio.wait_for(self._send_queue.get(), timeout=0.1)
                        if data is None:
                            await ws.send("finalize")
                            await asyncio.sleep(5)
                            break
                        await ws.send(data)
                    except asyncio.TimeoutError:
                        if self._closed:
                            break
                        continue
                    except Exception as e:
                        logger.error(f"Parakeet WS send error: {e}")
                        self._mark_dead(f"parakeet ws send: {e}")
                        break
                if self._closed and self._receiver_task and not self._receiver_task.done():
                    try:
                        await asyncio.wait_for(self._receiver_task, timeout=10)
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        self._cancel_task(self._receiver_task)

        except Exception as e:
            logger.error(f"Parakeet WS connection error: {e}")
            close_reason = str(getattr(e, 'reason', '') or '')
            if close_reason in EXPECTED_REJECTIONS:
                self._startup_failure_reason = close_reason
            elif isinstance(e, (asyncio.TimeoutError, TimeoutError)):
                self._startup_failure_reason = 'timeout'
            self._mark_dead(f"parakeet ws failed: {e}")
        finally:
            self._startup_event.set()
            self._closed = True
            if self._ws:
                try:
                    await self._ws.close()
                except Exception:
                    pass

    async def _receive_loop(self, ws: Any) -> None:
        try:
            async for msg in ws:
                if isinstance(msg, str):
                    try:
                        loaded: object = json.loads(msg)
                        if isinstance(loaded, dict):
                            seg: Dict[str, Any] = cast(Dict[str, Any], loaded)
                            if seg.get("text"):
                                self._stream_transcript([seg])
                    except json.JSONDecodeError:
                        pass
            # A clean async-for exhaustion means the provider closed the upstream
            # WebSocket without raising. Unless this is a local drain/finalization
            # (self._closed, set by drain_and_close and the _run finally), it is an
            # unexpected clean provider close and must latch terminal so the listen
            # loop propagates it without waiting for another client audio frame (#10028).
            if not self._closed:
                self._mark_dead('parakeet ws closed cleanly by provider')
        except Exception as e:
            if not self._closed:
                logger.error(f"Parakeet WS recv error: {e}")
                self._mark_dead(f"parakeet ws recv: {e}")


async def process_audio_parakeet(
    stream_transcript: Callable[[List[Dict[str, Any]]], None],
    language: str,
    sample_rate: int,
    channels: int,
    model: str = 'parakeet',
    keywords: Optional[List[str]] = None,
    is_active: Optional[Callable[[], bool]] = None,
) -> Optional[ParakeetWebSocketSocket]:
    """STT path backed by the self-hosted Parakeet /v3/stream WebSocket.

    Server-side VAD + diarization — the backend just relays PCM chunks
    and receives speaker-labeled segments.
    """
    api_url = os.getenv('HOSTED_PARAKEET_API_URL')
    if not api_url:
        logger.error('process_audio_parakeet: HOSTED_PARAKEET_API_URL not set')
        return None

    ws_url = api_url.replace('http://', 'ws://').replace('https://', 'wss://').rstrip('/') + '/v3/stream'
    logger.info(f'process_audio_parakeet {language} {sample_rate} -> {ws_url}')
    socket = ParakeetWebSocketSocket(stream_transcript, ws_url, sample_rate)
    await socket.start()
    return socket


def sort_segments_by_start(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(segments, key=lambda s: s.get('start', 0))


def make_stream_callback(
    callback: Callable[[List[Dict[str, Any]]], None],
    vad_gate: Any,
    passthrough: bool,
) -> Callable[[List[Dict[str, Any]]], None]:
    if vad_gate is not None and not passthrough:

        def wrapped(segments: List[Dict[str, Any]]) -> None:
            vad_gate.remap_segments(segments)
            callback(segments)

        return wrapped
    return callback


def sort_transcript_segments_in_place(segments: List[Any]) -> None:
    segments.sort(key=lambda s: s.start)

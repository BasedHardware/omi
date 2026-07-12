import asyncio
import io
import json
import logging
import os
import audioop
import struct
import time
import uuid
from collections import deque, OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Coroutine, Dict, List, Optional, Sequence, Set, Tuple, cast

import av
import numpy as np

_OPUS_IMPORT_ERROR: Optional[BaseException] = None
try:
    import opuslib  # type: ignore[reportMissingImports]
except Exception as e:
    opuslib = None
    _OPUS_IMPORT_ERROR = e
else:
    _OPUS_IMPORT_ERROR = None

_LC3_IMPORT_ERROR: Optional[BaseException] = None
try:
    import lc3  # lc3py  # type: ignore[reportMissingImports]
except Exception as e:
    lc3 = None
    _LC3_IMPORT_ERROR = e
else:
    _LC3_IMPORT_ERROR = None

from fastapi import APIRouter, Depends
from fastapi.websockets import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
from firebase_admin.auth import InvalidIdTokenError

from utils.speaker_assignment import (
    process_speaker_assigned_segments,
    update_speaker_assignment_maps,
    should_update_speaker_to_person_map,
)
from utils.byok import get_byok_keys, extract_byok_from_websocket, set_byok_keys
from utils.transcribe_store import (
    calendar_db,
    check_credits_invalidation,
    conversations_db,
    get_user_transcription_preferences,
    redis_db,
    user_db,
)
from models.conversation import Conversation
from models.conversation_enums import ConversationSource, ConversationStatus
from utils.conversations.factory import deserialize_conversation
from models.conversation_photo import ConversationPhoto
from models.structured import Structured
from models.transcript_segment import TranscriptSegment
from models.message_event import (
    ConversationEvent,
    ConversationSessionEvent,
    FREEMIUM_ACTION_SETUP_ON_DEVICE_STT,
    FreemiumThresholdReachedEvent,
    LastConversationEvent,
    MessageEvent,
    MessageServiceStatusEvent,
    PhotoDescribedEvent,
    PhotoProcessingEvent,
    SegmentsDeletedEvent,
    SpeakerLabelSuggestionEvent,
    TranslationEvent,
)
from models.transcript_segment import Translation
from models.users import PlanType
from utils.analytics import billable_transcription_seconds, record_usage
from utils.app_integrations import trigger_realtime_integrations
from utils.apps import is_audio_bytes_app_enabled
from utils.conversations.process_conversation import retrieve_in_progress_conversation
from utils.notifications import send_credit_limit_notification, send_silent_user_notification
from utils.other import endpoints as auth
from utils.other.storage import get_profile_audio_if_exists, get_user_has_speech_profile
from utils.client_device import (
    ClientDeviceContext,
    resolve_client_device_from_headers,
    resolve_client_device_from_websocket_auth_message,
)
from utils.pusher import PusherCircuitBreakerOpen
from utils.request_validation import ImageChunkEnvelope
from utils.speaker_identification import detect_speaker_from_text
from utils.stt.streaming import (
    STTService,
    get_stt_service_for_language,
    make_stream_callback,
    process_audio_dg,
    process_audio_modulate,
    process_audio_parakeet,
    sort_segments_by_start,
    sort_transcript_segments_in_place,
)
from utils.stt.vad_gate import GatedSTTSocket, VADStreamingGate, VAD_GATE_MODE, is_gate_enabled
from utils.fair_use import (
    FAIR_USE_ENABLED,
    FAIR_USE_CHECK_INTERVAL_SECONDS,
    FAIR_USE_RESTRICT_DAILY_DG_MS,
    record_speech_ms,
    get_rolling_speech_ms,
    check_soft_caps,
    trigger_classifier_if_needed,
    get_enforcement_stage,
    is_dg_budget_exhausted,
    record_dg_usage_ms,
)
from utils.subscription import (
    has_transcription_credits,
    get_remaining_transcription_seconds,
    is_trial_paywalled,
)
from utils.translation import TranslationService
from utils.translation_cache import (
    TranscriptSegmentLanguageCache,
    ConversationLanguageState,
    should_persist_translation,
)
from utils.listen_session_bootstrap import finalize_listen_connect_context, load_listen_connect_base
from utils.translation_coordinator import TranslationCoordinator
from utils.transcribe_decisions import (  # async-blockers: no-import-scope; async-blockers: no-changed-range-scope
    ConversationLifecycleAction,
    USER_SELF_PERSON_ID,
    decide_existing_conversation_action,
    decide_lifecycle_action,
    decide_multi_channel_mix,
    decide_multi_channel_stt_send,
    decide_stt_buffer_flush,
    decide_text_speaker_assignment,
    effective_conversation_timeout,
    is_user_self_match,
    normalize_codec_frame,
    normalize_language,
    person_id_for_client,
    resolve_photo_conversation_source,
    select_translation_language,
    should_enable_speaker_identification,
    should_flush_final_multi_channel_mix,
    should_force_single_language,
    should_include_speech_profile,
    should_initialize_vad_gate,
    should_load_speech_profile,
    should_queue_speaker_embedding,
    should_process_on_disconnect,
    should_remove_in_progress_pointer,
    should_skip_speaker_detection,
    should_spawn_speaker_match,
    stt_buffer_flush_size as calculate_stt_buffer_flush_size,
    vad_gate_mode,
)
from utils.webhooks import get_audio_bytes_webhook_seconds
from utils.onboarding import OnboardingHandler

from utils.aac import AACDecoder
from utils.audio import AudioRingBuffer
from utils.metrics import (
    BACKEND_LISTEN_ACTIVE_WS_CONNECTIONS,
)
from utils.listen_pusher_session import ListenPusherSession, ListenPusherSessionConfig, ListenPusherSessionDeps
from utils.stt.speaker_embedding import (
    extract_embedding_from_bytes,
    compare_embeddings,
    SPEAKER_MATCH_THRESHOLD,
)
from utils.speaker_sample_migration import maybe_migrate_person_samples
from utils.executors import db_executor, storage_executor, sync_executor, run_blocking, start_background_task
from utils.log_sanitizer import sanitize, sanitize_pii
from utils.async_tasks import WebSocketTaskSupervisor, drain_tasks, wait_for_event

logger = logging.getLogger(__name__)


@dataclass
class ListenSessionState:
    active: bool = True
    close_code: int = 1001  # Going Away, don't close with good from backend
    shutdown_event: asyncio.Event = field(default_factory=asyncio.Event)
    audio_ring_buffer: Optional[AudioRingBuffer] = None
    speaker_id_enabled: bool = False
    speaker_id_done: asyncio.Event = field(default_factory=asyncio.Event)
    speaker_map_dirty: bool = False
    first_audio_byte_timestamp: Optional[float] = None
    last_usage_record_timestamp: Optional[float] = None
    words_transcribed_since_last_record: int = 0
    last_transcript_time: Optional[float] = None
    current_conversation_id: Optional[str] = None
    freemium_threshold_sent: bool = False
    remaining_seconds_cache: Optional[int] = None
    remaining_seconds_cache_ts: float = 0.0
    remaining_seconds_cache_initialized: bool = False
    fair_use_last_check_ts: float = 0.0
    fair_use_dg_budget_exhausted: bool = False
    fair_use_track_dg_usage: bool = False
    dg_usage_ms_pending: int = 0
    last_audio_received_time: Optional[float] = None
    last_activity_time: Optional[float] = None


def _get_opuslib() -> Any:
    if opuslib is None:
        raise RuntimeError(
            'Opus streaming requires opuslib and the native libopus library. '
            'Install the OS-level Opus package before using the opus codec.'
        ) from _OPUS_IMPORT_ERROR
    return opuslib


def _get_lc3() -> Any:
    if lc3 is None:
        message = 'LC3 streaming requires lc3py and its native codec library. Install lc3py before using the lc3 codec.'
        raise RuntimeError(message) from _LC3_IMPORT_ERROR
    return lc3


router = APIRouter()


PUSHER_ENABLED = bool(os.getenv('HOSTED_PUSHER_API_URL'))

# Freemium: Send notification when credits threshold is reached
FREEMIUM_THRESHOLD_SECONDS = 180  # 3 minutes remaining - notify user

TARGET_SAMPLE_RATE = 16000


WS_RECEIVE_TIMEOUT = 300.0  # seconds — no-data timeout on client WebSocket receive
BG_DRAIN_TIMEOUT = 30.0  # seconds — grace period for bg tasks to drain after disconnect


def _normalize_client_conversation_id(client_conversation_id: Optional[str]) -> Optional[str]:
    if not client_conversation_id:
        return None
    value = client_conversation_id.strip()
    if not value:
        return None
    try:
        return str(uuid.UUID(value))
    except ValueError:
        return None


# ---- Multi-channel support ----


@dataclass
class ChannelConfig:
    channel_id: int  # Wire protocol ID (1-indexed: 0x01, 0x02, ...)
    label: str  # Human-readable label
    is_user: bool  # Whether this channel represents the user's voice
    speaker_label: str  # STT speaker label


def build_channel_config(source: str) -> List[ChannelConfig]:
    """Build channel configuration based on source type."""
    if source == 'phone_call':
        return [
            ChannelConfig(channel_id=0x01, label='mic', is_user=True, speaker_label='SPEAKER_00'),
            ChannelConfig(channel_id=0x02, label='remote', is_user=False, speaker_label='SPEAKER_01'),
        ]
    elif source == 'desktop':
        return [
            ChannelConfig(channel_id=0x01, label='mic', is_user=True, speaker_label='SPEAKER_00'),
            ChannelConfig(channel_id=0x02, label='system_audio', is_user=False, speaker_label='SPEAKER_01'),
        ]
    return [
        ChannelConfig(channel_id=0x01, label='mic', is_user=True, speaker_label='SPEAKER_00'),
        ChannelConfig(channel_id=0x02, label='remote', is_user=False, speaker_label='SPEAKER_01'),
    ]


def mix_n_channel_buffers(buffers: List[bytearray]) -> bytes:
    """Mix N 16-bit PCM mono buffers sample-by-sample into one mono stream, clamping to int16 range."""
    min_len = min((len(b) for b in buffers), default=0)
    if min_len < 2:
        return b''
    # Align to sample boundary (2 bytes per sample)
    min_len = min_len - (min_len % 2)
    num_samples = min_len // 2
    channel_samples = [struct.unpack(f'<{num_samples}h', b[:min_len]) for b in buffers]
    mixed: List[int] = []
    for i in range(num_samples):
        s = sum(ch[i] for ch in channel_samples)
        mixed.append(max(-32768, min(32767, s)))
    return struct.pack(f'<{num_samples}h', *mixed)


def resample_pcm(pcm_data: bytes, source_rate: int, target_rate: int) -> bytes:
    """Simple resampling by sample duplication/decimation."""
    if source_rate == target_rate:
        return pcm_data
    if source_rate <= 0 or target_rate <= 0:
        return pcm_data
    num_samples = len(pcm_data) // 2
    if num_samples == 0:
        return pcm_data
    samples = struct.unpack(f'<{num_samples}h', pcm_data)
    ratio = target_rate / source_rate
    new_length = int(num_samples * ratio)
    resampled: List[int] = []
    for i in range(new_length):
        src_idx = min(int(i / ratio), num_samples - 1)
        resampled.append(samples[src_idx])
    return struct.pack(f'<{len(resampled)}h', *resampled)


class CustomSttMode(str, Enum):
    disabled = "disabled"
    enabled = "enabled"


async def _stream_handler(
    websocket: WebSocket,
    uid: str,
    language: str = 'en',
    sample_rate: int = 8000,
    codec: str = 'pcm8',
    channels: int = 1,
    include_speech_profile: bool = True,
    stt_service: Optional[str] = None,
    conversation_timeout: int = 120,
    source: Optional[str] = None,
    custom_stt_mode: CustomSttMode = CustomSttMode.disabled,
    onboarding_mode: bool = False,
    speaker_auto_assign_enabled: bool = False,
    create_speakers: bool = True,
    vad_gate_override: Optional[str] = None,
    call_id: Optional[str] = None,
    client_conversation_id: Optional[str] = None,
    client_device_context: Optional[ClientDeviceContext] = None,
):
    """
    Core WebSocket streaming handler. Assumes websocket is already accepted and uid is validated.
    This function is called by both _listen (for app clients) and web_listen_handler (for web clients).
    """
    session_id = str(uuid.uuid4())
    client_conversation_id = _normalize_client_conversation_id(client_conversation_id)
    client_device_context = client_device_context or resolve_client_device_from_headers(websocket.headers)

    if not uid or len(uid) <= 0:
        await websocket.close(code=1008, reason="Bad uid")
        return

    set_byok_keys(extract_byok_from_websocket(websocket))

    if await run_blocking(db_executor, is_trial_paywalled, uid, source):
        logger.info("trial paywall: closing desktop WS uid=%s session=%s reason=trial_expired", uid, session_id)
        try:
            await websocket.send_json(
                FreemiumThresholdReachedEvent(
                    remaining_seconds=0,
                    action=FREEMIUM_ACTION_SETUP_ON_DEVICE_STT,
                ).to_json()
            )
            await asyncio.sleep(0.5)
            await websocket.close(code=1008, reason="trial_expired")
        except Exception as e:
            logger.error(f"Error closing paywalled WS: {e} {uid} {session_id}")
        return

    logger.info(
        f'_stream_handler {uid} {session_id} {language} {sample_rate} {codec} {include_speech_profile} {stt_service} {conversation_timeout} custom_stt={custom_stt_mode} onboarding={onboarding_mode} client_conversation_id={bool(client_conversation_id)}'
    )

    use_custom_stt = custom_stt_mode == CustomSttMode.enabled
    is_multi_channel = channels >= 2

    # Multi-channel state (only allocated when channels >= 2)
    channel_configs: List[ChannelConfig] = []
    channel_id_to_index: Dict[int, int] = {}
    stt_sockets_multi: List[Any] = []
    multi_opus_decoders: List[Any] = []
    channel_mix_buffers: List[bytearray] = []
    if is_multi_channel:
        channel_configs = build_channel_config(source or 'phone_call')
        channel_id_to_index = {ch.channel_id: i for i, ch in enumerate(channel_configs)}
        stt_sockets_multi = [None] * len(channel_configs)
        if codec == 'opus':
            multi_opus_decoders = [_get_opuslib().Decoder(sample_rate, 1) for _ in channel_configs]
        else:
            multi_opus_decoders = [None] * len(channel_configs)
        channel_mix_buffers = [bytearray() for _ in channel_configs]
        # Multi-channel doesn't use speech profiles or onboarding
        include_speech_profile = should_include_speech_profile(
            include_speech_profile, is_multi_channel, onboarding_mode
        )

    # Helper to gate person_id based on client capability (backward compatibility)
    # OLD apps don't send speaker_auto_assign param -> receive empty person_id
    # NEW apps send speaker_auto_assign=enabled -> receive populated person_id
    def _person_id_for_client(person_id: str) -> str:
        return person_id_for_client(person_id, speaker_auto_assign_enabled)

    # Onboarding mode overrides: no speech profile (creating new one), single language
    include_speech_profile = should_include_speech_profile(include_speech_profile, is_multi_channel, onboarding_mode)

    # Frame size, codec
    frame_size: int = 160
    lc3_chunk_size: Optional[int] = None
    lc3_frame_duration_us: Optional[int] = None

    codec_decision = normalize_codec_frame(codec)
    codec = codec_decision.codec
    frame_size = codec_decision.frame_size
    lc3_chunk_size = codec_decision.lc3_chunk_size
    lc3_frame_duration_us = codec_decision.lc3_frame_duration_us

    connect_base = await load_listen_connect_base(uid, source=source, use_custom_stt=use_custom_stt)
    if not connect_base.user_exists:
        await websocket.close(code=1008, reason="Bad user")
        return

    user_has_credits = connect_base.user_has_credits
    if not user_has_credits:
        try:
            await send_credit_limit_notification(uid)
        except Exception as e:
            logger.error(f"Error sending credit limit notification: {e} {uid} {session_id}")

    transcription_prefs = connect_base.transcription_prefs
    single_language_mode = should_force_single_language(
        onboarding_mode, transcription_prefs.get('single_language_mode', False)
    )

    # Convert 'auto' to 'multi' for consistency
    language = normalize_language(language)

    # The client's explicitly-requested engine (query param), captured before the
    # language-based selection below overwrites stt_service.
    requested_stt_service = stt_service

    # Determine the best STT service
    stt_service, stt_language, stt_model = get_stt_service_for_language(
        language, multi_lang_enabled=not single_language_mode
    )
    if not stt_service or not stt_language:
        await websocket.close(code=1008, reason=f"The language is not supported, {language}")
        return

    # Opt-in: honor an explicit Parakeet request only when the self-hosted service is configured.
    if requested_stt_service == 'parakeet' and os.getenv('HOSTED_PARAKEET_API_URL'):
        stt_service = STTService.parakeet

    connect_ctx = finalize_listen_connect_context(
        connect_base,
        language=language,
        onboarding_mode=onboarding_mode,
        stt_language=stt_language,
    )
    single_language_mode = connect_ctx.single_language_mode
    vocabulary = connect_ctx.vocabulary
    language = connect_ctx.language
    user_language_preference = connect_ctx.user_language_preference
    translation_language = connect_ctx.translation_language
    transcription_prefs = connect_ctx.transcription_prefs

    # Stamp mobile custom-STT usage onto the user doc so these users are queryable
    # and meterable (#7690) — the app otherwise only signals it per-session via the
    # custom_stt WS param. Write only on change to keep this off the hot path.
    # Best-effort telemetry only: never let a tracking write failure (e.g. a
    # transient Firestore error) tear down the session — catch, log, and proceed.
    if use_custom_stt != transcription_prefs.get('uses_custom_stt', False):
        try:
            await run_blocking(db_executor, user_db.set_user_custom_stt_usage, uid, use_custom_stt)
        except Exception as e:
            logger.warning(f"Failed to persist custom_stt usage {uid} {session_id}: {e}")

    session = ListenSessionState()
    task_supervisor = WebSocketTaskSupervisor(
        uid=uid,
        label="listen",
        gauge=BACKEND_LISTEN_ACTIVE_WS_CONNECTIONS,
    )
    session.shutdown_event = task_supervisor.shutdown_event

    # Buffer size limits to prevent memory leaks during outages/lag
    MAX_SEGMENT_BUFFER_SIZE = 1000  # Max segments to buffer
    MAX_PHOTO_BUFFER_SIZE = 100  # Max photos to buffer
    MAX_AUDIO_BUFFER_SIZE = 1024 * 1024 * 10  # 10MB max audio buffer
    MAX_PENDING_REQUESTS = 100  # Max pending conversation requests
    MAX_PENDING_SPEAKER_SAMPLE_REQUESTS = 50  # Max speaker-sample requests buffered while pusher is down
    MAX_IMAGE_CHUNKS = 50  # Max concurrent image uploads
    IMAGE_CHUNK_TTL = 60.0  # Seconds before incomplete image chunks expire
    IMAGE_CHUNK_CLEANUP_INTERVAL = 2.0  # Seconds between cleanup scans
    IMAGE_CHUNK_CLEANUP_MIN_SIZE = 5  # Skip scans for tiny caches unless oldest can expire

    # Initialize segment buffers early (before onboarding handler needs them)
    realtime_segment_buffers: "deque[Dict[str, Any]]" = deque(maxlen=MAX_SEGMENT_BUFFER_SIZE)
    realtime_photo_buffers: deque[ConversationPhoto] = deque(maxlen=MAX_PHOTO_BUFFER_SIZE)

    # === Speaker Identification State ===
    RING_BUFFER_DURATION = 60.0  # seconds
    SPEAKER_ID_MIN_AUDIO = 2.0
    _SPEAKER_ID_TARGET_AUDIO = 4.0

    speaker_id_segment_queue: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue(maxsize=100)
    person_embeddings_cache: Dict[str, Dict[str, Any]] = {}  # person_id -> {embedding, name}
    # Speaker ID fields on session are set once private_cloud_sync_enabled is known.
    # Dedicated set for speaker match tasks so the final pass can drain them independently
    speaker_match_tasks: Set[asyncio.Task[Any]] = set()

    def spawn(coro: Awaitable[Any], *, name: str) -> asyncio.Task[Any]:
        return task_supervisor.create_task(cast(Coroutine[Any, Any, Any], coro), name=name)

    # Onboarding handler
    onboarding_handler: Optional[OnboardingHandler] = None
    if onboarding_mode:

        async def send_onboarding_event(event: Dict[str, Any]):
            if session.active and websocket.client_state == WebSocketState.CONNECTED:
                try:
                    await websocket.send_json(event)
                except Exception as e:
                    logger.error(f"Error sending onboarding event: {e} {uid} {session_id}")

        def onboarding_stream_transcript(segments: List[Dict[str, Any]]):
            """Inject onboarding question segments into the transcript stream."""
            nonlocal realtime_segment_buffers
            realtime_segment_buffers.extend(segments)

        onboarding_handler = OnboardingHandler(uid, send_onboarding_event, onboarding_stream_transcript)
        spawn(onboarding_handler.send_current_question(), name="onboarding_question")

    locked_conversation_ids: Set[str] = set()
    speaker_to_person_map: Dict[int, Tuple[str, str]] = {}
    segment_person_assignment_map: Dict[str, str] = {}
    current_session_segments: Dict[str, bool] = {}  # Store only speech_profile_processed status
    suggested_segments: Set[str] = set()

    # Push the freemium threshold event upfront for already-exhausted users so
    # the desktop popup appears immediately on connect, instead of waiting for
    # the periodic loop's first 60s tick (typical desktop session is shorter).
    if not user_has_credits:
        try:
            await websocket.send_json(
                FreemiumThresholdReachedEvent(
                    remaining_seconds=0,
                    action=FREEMIUM_ACTION_SETUP_ON_DEVICE_STT,
                ).to_json()
            )
            session.freemium_threshold_sent = True
        except Exception as e:
            logger.error(f"Error sending freemium threshold event on connect: {e} {uid} {session_id}")

    # Credit cache: avoid querying ~720 Firestore docs every 60s per stream (#5439 sub-task 1)
    CREDITS_REFRESH_SECONDS = 900  # 15 min

    # Fair-use state (#5746)
    # DG budget gate — checked at session start + per cap-check interval
    # Covers restrict-stage users (#5746) and free-exhausted users (#6083)
    # Track DG usage only for restrict-stage users (not all users)
    # DG usage accumulator: batch Redis writes every 60s instead of per-chunk (#5854)

    # Session-start: check DG budget for restrict-stage users (#6083)
    if FAIR_USE_ENABLED:
        try:
            _init_stage = connect_ctx.fair_use_init_stage
            logger.info(f'fair_use: session start uid={uid} session={session_id} stage={_init_stage}')
            if connect_ctx.fair_use_track_dg_usage:
                session.fair_use_track_dg_usage = True
                session.fair_use_dg_budget_exhausted = connect_ctx.fair_use_dg_budget_exhausted
                if session.fair_use_dg_budget_exhausted:
                    logger.info(f'fair_use: DG budget already exhausted at session start for {uid}')
        except Exception as e:
            logger.error(f'fair_use: session-start budget check error for {uid}: {e}')

    async def _record_usage_periodically():
        nonlocal user_has_credits

        while session.active:
            if await wait_for_event(session.shutdown_event, 60):
                break

            # Flush batched DG usage to Redis (#5854 — was per-chunk, now every 60s)
            # Placed before use_custom_stt guard so all STT paths get flushed
            if session.fair_use_track_dg_usage and session.dg_usage_ms_pending > 0:
                record_dg_usage_ms(uid, session.dg_usage_ms_pending)
                session.dg_usage_ms_pending = 0

            if use_custom_stt:
                continue

            transcription_seconds = 0
            speech_seconds_delta = 0

            # Consume speech_ms delta from VAD gate (#5746)
            if vad_gate is not None:
                speech_ms = vad_gate.consume_speech_ms_delta()
                speech_seconds_delta = speech_ms // 1000
                # Record to Redis for rolling window tracking
                if FAIR_USE_ENABLED and speech_ms > 0:
                    record_speech_ms(uid, speech_ms)
                    logger.debug(f'fair_use: recorded {speech_ms}ms speech uid={uid} session={session_id}')

            if session.last_usage_record_timestamp:
                current_time = time.time()
                # Clamped to the last audio actually received (#4700): keepalive
                # pings keep the socket alive after the device stops streaming.
                transcription_seconds = billable_transcription_seconds(
                    session.last_usage_record_timestamp, session.last_audio_received_time, current_time
                )

                words_to_record = session.words_transcribed_since_last_record
                session.words_transcribed_since_last_record = 0  # reset

                if transcription_seconds > 0 or words_to_record > 0 or speech_seconds_delta > 0:
                    record_usage(
                        uid,
                        transcription_seconds=transcription_seconds,
                        words_transcribed=words_to_record,
                        speech_seconds=speech_seconds_delta,
                    )
                session.last_usage_record_timestamp = current_time

            # Fair-use soft cap check (every FAIR_USE_CHECK_INTERVAL_SECONDS) (#5746)
            # Track + detect + classify + set stage + notify. No service degradation.
            now_ts = time.time()
            if FAIR_USE_ENABLED and now_ts - session.fair_use_last_check_ts >= FAIR_USE_CHECK_INTERVAL_SECONDS:
                session.fair_use_last_check_ts = now_ts
                try:
                    speech_totals = get_rolling_speech_ms(uid)
                    triggered_caps = cast(List[Any], check_soft_caps(uid, speech_totals=speech_totals))
                    if triggered_caps:
                        logger.info(
                            f'fair_use: soft cap triggered for {uid} session={session_id} caps={triggered_caps}'
                        )
                        start_background_task(
                            trigger_classifier_if_needed(uid, triggered_caps, session_id),
                            name=f"fair_use_classifier:{uid}:{session_id}",
                        )
                        # Start DG tracking proactively — classifier may escalate to restrict
                        # before next poll. Harmless if user isn't actually escalated.
                        if FAIR_USE_RESTRICT_DAILY_DG_MS > 0:
                            session.fair_use_track_dg_usage = True
                    else:
                        logger.info(
                            f'fair_use: cap check ok uid={uid} session={session_id}'
                            f' daily={speech_totals["daily_ms"]}ms'
                            f' 3day={speech_totals["three_day_ms"]}ms'
                            f' weekly={speech_totals["weekly_ms"]}ms'
                        )
                except Exception as e:
                    logger.error(f'fair_use: cap check error for {uid}: {e}')

                # DG budget gate: check restrict-stage budget (#6083)
                # Re-check stage after classifier may have escalated (fire-and-forget task above)
                try:
                    stage = get_enforcement_stage(uid)
                    if stage == 'restrict' and FAIR_USE_RESTRICT_DAILY_DG_MS > 0:
                        session.fair_use_track_dg_usage = True
                        was_exhausted = session.fair_use_dg_budget_exhausted
                        session.fair_use_dg_budget_exhausted = is_dg_budget_exhausted(uid)
                        if session.fair_use_dg_budget_exhausted and not was_exhausted:
                            logger.info(f'fair_use: DG budget exhausted for {uid} session={session_id}')
                    else:
                        session.fair_use_track_dg_usage = False
                        session.fair_use_dg_budget_exhausted = False
                except Exception as e:
                    logger.error(f'fair_use: DG budget check error for {uid}: {e}')

            # Freemium: Check remaining credits with local cache (#5439)
            # Refresh from Firestore only every CREDITS_REFRESH_SECONDS; decrement locally between refreshes
            # Active invalidation: subscription changes set a Redis signal (#5446)
            now = time.time()
            credits_invalidated = check_credits_invalidation(uid)
            needs_refresh = (
                not session.remaining_seconds_cache_initialized
                or credits_invalidated
                or now - session.remaining_seconds_cache_ts >= CREDITS_REFRESH_SECONDS
                # Fast-refresh when credits exhausted (user may upgrade or month may roll over)
                or (
                    session.remaining_seconds_cache is not None
                    and session.remaining_seconds_cache <= 0
                    and now - session.remaining_seconds_cache_ts >= 60
                )
            )
            if needs_refresh:
                session.remaining_seconds_cache = get_remaining_transcription_seconds(uid, source=source)
                session.remaining_seconds_cache_ts = now
                session.remaining_seconds_cache_initialized = True
            elif session.remaining_seconds_cache is not None and transcription_seconds > 0:
                # Decrement locally between refreshes (None = unlimited, don't decrement)
                session.remaining_seconds_cache = max(0, session.remaining_seconds_cache - transcription_seconds)

            remaining_seconds = session.remaining_seconds_cache

            # Notify user when approaching limit (3 minutes remaining)
            if (
                remaining_seconds is not None
                and remaining_seconds <= FREEMIUM_THRESHOLD_SECONDS
                and not session.freemium_threshold_sent
            ):
                # Determine required action
                # Currently: user must setup on-device STT
                # Future: backend may auto-fallback to lower-tier cloud STT (action = ACTION_NONE)
                await _asend_message_event(
                    FreemiumThresholdReachedEvent(
                        remaining_seconds=remaining_seconds,
                        action=FREEMIUM_ACTION_SETUP_ON_DEVICE_STT,
                    )
                )
                session.freemium_threshold_sent = True

                # Also send push notification
                try:
                    await send_credit_limit_notification(uid)
                except Exception as e:
                    logger.error(f"Error sending credit limit notification: {e} {uid} {session_id}")

            # Update credits state
            if remaining_seconds is not None and remaining_seconds <= 0:
                user_has_credits = False
            elif remaining_seconds is None or remaining_seconds > 0:
                user_has_credits = True
                # Reset threshold flag if credits were restored (new month, upgrade, etc.)
                if remaining_seconds is None or remaining_seconds > FREEMIUM_THRESHOLD_SECONDS:
                    session.freemium_threshold_sent = False

            # Silence notification logic for basic plan users
            user_subscription = user_db.get_user_valid_subscription(uid)
            if not user_subscription or user_subscription.plan == PlanType.basic:
                time_of_last_words = session.last_transcript_time or session.first_audio_byte_timestamp
                if (
                    session.last_audio_received_time
                    and time_of_last_words
                    and (session.last_audio_received_time - time_of_last_words) > 15 * 60
                ):
                    logger.info(f"User {uid} has been silent for over 15 minutes. Sending notification. {session_id}")
                    try:
                        await send_silent_user_notification(uid)
                    except Exception as e:
                        logger.error(f"Error sending silent user notification: {e} {uid} {session_id}")

    async def _asend_message_event(msg: MessageEvent):
        if not session.active:
            return False
        try:
            await websocket.send_json(msg.to_json())
            return True
        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected {uid} {session_id}")
            session.active = False
        except Exception as e:
            logger.error(f"Can not send message event, error: {e} {uid} {session_id}")

        return False

    def _send_message_event(msg: MessageEvent):
        if not session.active:
            return
        return spawn(_asend_message_event(msg), name="message_event")

    # Heart beat
    _started_at = time.time()
    inactivity_timeout_seconds = 90
    session.last_audio_received_time = None
    session.last_activity_time = None

    # Send pong every 10s then handle it in the app \
    # since Starlette is not support pong automatically
    async def send_heartbeat():
        logger.debug(f"send_heartbeat {uid} {session_id}")

        try:
            while session.active:
                # ping fast
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_text("ping")
                else:
                    break

                # Inactivity timeout
                if session.last_activity_time and time.time() - session.last_activity_time > inactivity_timeout_seconds:
                    logger.warning(
                        f"Session timeout due to inactivity ({inactivity_timeout_seconds}s) {uid} {session_id}"
                    )
                    session.close_code = 1001
                    session.active = False
                    break

                # next
                if await wait_for_event(session.shutdown_event, 10):
                    break
        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected {uid} {session_id}")
        except Exception as e:
            logger.error(f'Heartbeat error: {e} {uid} {session_id}')
            session.close_code = 1011
        finally:
            session.active = False

    heartbeat_task = None

    _send_message_event(
        MessageServiceStatusEvent(event_type="service_status", status="initiating", status_text="Service Starting")
    )

    # Create or get conversation ID early for audio chunk storage
    private_cloud_sync_enabled = user_db.get_user_private_cloud_sync_enabled(uid)

    # Enable speaker identification when user has speech profile or private cloud sync
    has_speech_profile = False
    if should_load_speech_profile(
        use_custom_stt=use_custom_stt,
        is_multi_channel=is_multi_channel,
        include_speech_profile=include_speech_profile,
    ):
        has_speech_profile = get_user_has_speech_profile(uid)
    session.speaker_id_enabled = should_enable_speaker_identification(
        use_custom_stt=use_custom_stt,
        private_cloud_sync_enabled=private_cloud_sync_enabled,
        has_speech_profile=has_speech_profile,
    )
    if session.speaker_id_enabled:
        session.audio_ring_buffer = AudioRingBuffer(RING_BUFFER_DURATION, sample_rate)

    # Conversation timeout (to process the conversation after x seconds of silence)
    # Max: 4h, min 2m
    conversation_creation_timeout = effective_conversation_timeout(conversation_timeout, is_multi_channel)

    # Stream transcript
    # Callback for when pusher finishes processing a conversation
    def on_conversation_processed(conversation_id: str):
        if conversation_id != session.current_conversation_id:
            logger.warning(
                "Suppressing lifecycle event for non-current conversation %s on listen session %s %s",
                conversation_id,
                session_id,
                uid,
            )
            return
        conversation_data = conversations_db.get_conversation(uid, conversation_id)
        if conversation_data:
            conversation = deserialize_conversation(conversation_data)
            _send_message_event(
                ConversationEvent(
                    event_type="memory_created",
                    memory=conversation,
                    messages=[],
                    recording_session_id=client_conversation_id,
                )
            )

    def on_conversation_processing_started(conversation_id: str):
        if conversation_id != session.current_conversation_id:
            logger.warning(
                "Suppressing lifecycle event for non-current conversation %s on listen session %s %s",
                conversation_id,
                session_id,
                uid,
            )
            return
        conversation_data = conversations_db.get_conversation(uid, conversation_id)
        if conversation_data:
            conversation = deserialize_conversation(conversation_data)
            _send_message_event(
                ConversationEvent(
                    event_type="memory_processing_started",
                    memory=conversation,
                    recording_session_id=client_conversation_id,
                )
            )

    async def cleanup_processing_conversations():
        processing = conversations_db.get_processing_conversations(uid)
        if not processing:
            logger.info(f'finalize_processing_conversations len(processing): 0 {uid} {session_id}')
            return
        logger.info(f'finalize_processing_conversations len(processing): {len(processing)} {uid} {session_id}')
        if len(processing) == 0:
            return
        if not request_conversation_processing:
            logger.warning(f"Pusher not enabled, cannot reprocess {len(processing)} conversations {uid} {session_id}")
            return

        for conversation in processing:
            # Route to pusher — buffer if disconnected, send when connected (#6061)
            await request_conversation_processing(conversation['id'])

    async def process_pending_conversations(timed_out_id: Optional[str]):
        await asyncio.sleep(7.0)
        if timed_out_id:
            await _process_conversation(timed_out_id)
        await cleanup_processing_conversations()

    # Send last completed conversation to client
    def send_last_conversation():
        last_conversation = conversations_db.get_last_completed_conversation(uid)
        if last_conversation:
            _send_message_event(LastConversationEvent(memory_id=last_conversation['id']))

    send_last_conversation()

    # Create new stub conversation for next batch
    async def _create_new_in_progress_conversation():

        conversation_source = ConversationSource.omi
        if source:
            try:
                conversation_source = ConversationSource(source)
            except ValueError:
                logger.error(f"Invalid conversation source '{source}', defaulting to 'omi' {uid} {session_id}")
                conversation_source = ConversationSource.omi

        new_conversation_id = client_conversation_id or str(uuid.uuid4())
        if client_conversation_id:
            existing_conversation = conversations_db.get_conversation(uid, client_conversation_id)
            if existing_conversation:
                if existing_conversation.get('status') == ConversationStatus.in_progress:
                    session.current_conversation_id = client_conversation_id
                    redis_db.set_in_progress_conversation_id(uid, session.current_conversation_id)
                    _send_message_event(
                        ConversationSessionEvent(
                            conversation_id=session.current_conversation_id,
                            recording_session_id=client_conversation_id,
                        )
                    )
                    logger.info(
                        f"Resuming client-scoped conversation {session.current_conversation_id} {uid} {session_id}"
                    )
                    return
                logger.warning(
                    f"Client conversation id already exists with status {existing_conversation.get('status')}; generating server id instead {uid} {session_id}"
                )
                new_conversation_id = str(uuid.uuid4())
        stub_conversation = Conversation(
            id=new_conversation_id,
            created_at=datetime.now(timezone.utc),
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            structured=Structured(),
            language=language,
            transcript_segments=[],
            photos=[],
            status=ConversationStatus.in_progress,
            source=conversation_source,
            private_cloud_sync_enabled=private_cloud_sync_enabled,
            call_id=call_id if is_multi_channel else None,
            client_device_id=client_device_context.client_device_id,
            client_platform=client_device_context.platform,
        )
        if client_conversation_id and new_conversation_id == client_conversation_id:
            conversations_db.create_conversation_if_absent(uid, stub_conversation.model_dump())
        else:
            conversations_db.upsert_conversation(uid, conversation_data=stub_conversation.model_dump())
        redis_db.set_in_progress_conversation_id(uid, new_conversation_id)

        detected_meeting_id = None

        # Only check for meetings if source is desktop
        if conversation_source == ConversationSource.desktop:
            now = datetime.now(timezone.utc)
            # Check ±2 minute window
            time_window = timedelta(minutes=2)
            start_range = now - time_window
            end_range = now + time_window

            meetings = calendar_db.get_meetings_in_time_range(uid, start_range, end_range)

            if len(meetings) == 1:
                # Exactly one meeting found
                detected_meeting_id = meetings[0]['id']
            elif len(meetings) > 1:
                closest_meeting = None
                smallest_diff = None

                for meeting in meetings:
                    # Calculate absolute time difference between meeting start and now
                    time_diff = abs((meeting['start_time'] - now).total_seconds())

                    if smallest_diff is None or time_diff < smallest_diff:
                        smallest_diff = time_diff
                        closest_meeting = meeting

                if closest_meeting:
                    detected_meeting_id = closest_meeting['id']
                    logger.info(
                        f"Selected closest meeting: {closest_meeting['title']} (diff: {smallest_diff}s) {uid} {session_id}"
                    )

        # Store meeting association if auto-detected
        if detected_meeting_id:
            redis_db.set_conversation_meeting_id(new_conversation_id, detected_meeting_id)

        session.current_conversation_id = new_conversation_id
        _send_message_event(
            ConversationSessionEvent(
                conversation_id=new_conversation_id,
                recording_session_id=client_conversation_id,
            )
        )

        logger.info(f"Created new stub conversation: {new_conversation_id} {uid} {session_id}")

    async def _process_conversation(conversation_id: str):
        logger.info(f"_process_conversation {uid} {session_id}")
        conversation = conversations_db.get_conversation(uid, conversation_id)
        if conversation:
            has_content = conversation.get('transcript_segments') or conversation.get('photos')
            if has_content:
                if not request_conversation_processing:
                    logger.warning(
                        f"Pusher not enabled, skipping conversation {conversation_id} (stays in_progress) {uid} {session_id}"
                    )
                    return False
                # Mark processing + buffer for pusher — never process locally (#6061)
                conversations_db.update_conversation_status(uid, conversation_id, ConversationStatus.processing)
                on_conversation_processing_started(conversation_id)
                await request_conversation_processing(conversation_id)
                return True
            else:
                logger.info(f'Clean up the conversation {conversation_id}, reason: no content {uid} {session_id}')
                conversations_db.delete_conversation(uid, conversation_id)
                return True
        return False

    # Process existing conversations
    async def _prepare_in_progess_conversations() -> Optional[str]:
        # A client-provided UUID is the durable identity of this recording.  It
        # must win over the legacy, user-global in-progress pointer; otherwise a
        # stale Redis/Firestore row can rebind a fresh desktop recording.
        if client_conversation_id:
            await _create_new_in_progress_conversation()
            return None

        if existing_conversation := retrieve_in_progress_conversation(uid):
            finished_at = datetime.fromisoformat(existing_conversation['finished_at'].isoformat())
            seconds_since_last_segment = (datetime.now(timezone.utc) - finished_at).total_seconds()
            action = decide_existing_conversation_action(
                seconds_since_last_segment=seconds_since_last_segment,
                conversation_creation_timeout=conversation_creation_timeout,
            )
            if action == ConversationLifecycleAction.process_and_create_new:
                logger.info(
                    f'Processing existing conversation {existing_conversation["id"]} (timed out: {seconds_since_last_segment:.1f}s) {uid} {session_id}'
                )
                await _create_new_in_progress_conversation()
                return existing_conversation["id"]

            # Continue with the existing conversation
            resuming_conversation_id: str = existing_conversation['id']
            session.current_conversation_id = resuming_conversation_id
            _send_message_event(ConversationSessionEvent(conversation_id=resuming_conversation_id))
            logger.info(
                f"Resuming conversation {session.current_conversation_id}. Will timeout in {conversation_creation_timeout - seconds_since_last_segment:.1f}s {uid} {session_id}"
            )
            return None

        # else
        await _create_new_in_progress_conversation()
        return None

    _send_message_event(
        MessageServiceStatusEvent(status="in_progress_conversations_processing", status_text="Processing Conversations")
    )
    if is_multi_channel:
        # Multi-channel: one conversation per session, no resuming
        await _create_new_in_progress_conversation()
        timed_out_conversation_id = None
    else:
        timed_out_conversation_id = await _prepare_in_progess_conversations()

    def _update_in_progress_conversation(
        conversation: Conversation,
        segments: List[TranscriptSegment],
        photos: List[ConversationPhoto],
        finished_at: datetime,
    ):
        updated_segments: List[TranscriptSegment] = []
        removed_ids: List[str] = []

        if segments:
            conversation.transcript_segments, updated_segments, removed_ids = TranscriptSegment.combine_segments(
                conversation.transcript_segments, segments
            )
            sort_transcript_segments_in_place(conversation.transcript_segments)
            if session.speaker_map_dirty:
                # A new speaker match was found — retroactively fix all earlier segments once
                process_speaker_assigned_segments(
                    conversation.transcript_segments,
                    segment_person_assignment_map,
                    speaker_to_person_map,
                )
                session.speaker_map_dirty = False
            else:
                process_speaker_assigned_segments(
                    updated_segments,
                    segment_person_assignment_map,
                    speaker_to_person_map,
                )
            segments_dicts = [segment.model_dump() for segment in conversation.transcript_segments]
            conversations_db.update_conversation_segments(
                uid, conversation.id, segments_dicts, data_protection_level=_cached_protection_level
            )
            _update_cached_segments(segments_dicts)

        if photos:
            conversations_db.store_conversation_photos(uid, conversation.id, photos)
            # Photo-bearing conversations default to the openglass label unless the
            # source already identifies a photo-capable device (e.g. rayban_meta).
            new_source_value = resolve_photo_conversation_source(
                conversation.source.value if conversation.source else None
            )
            if new_source_value is not None and conversation.source != ConversationSource(new_source_value):
                new_source = ConversationSource(new_source_value)
                conversations_db.update_conversation(uid, conversation.id, {'source': new_source})
                conversation.source = new_source

        conversations_db.update_conversation_finished_at(uid, conversation.id, finished_at)
        return conversation, updated_segments, removed_ids

    # STT
    # Validate session.active before initiating STT
    if not session.active or websocket.client_state != WebSocketState.CONNECTED:
        logger.info(f"websocket was closed {uid} {session_id}")
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close(code=session.close_code)
            except Exception as e:
                logger.error(f"Error closing WebSocket: {e} {uid} {session_id}")
        return

    # Process STT
    stt_socket = None

    vad_gate = None

    def stream_transcript(segments: List[Dict[str, Any]]) -> None:
        nonlocal realtime_segment_buffers
        realtime_segment_buffers.extend(segments)

    async def _create_stt_socket(
        callback: Callable[[List[Dict[str, Any]]], None],
        lang: str,
        sr: int,
        model: str,
        kw: Optional[List[str]] = None,
        active_check: Optional[Callable[[], bool]] = None,
    ):
        keywords: List[str] = kw if kw is not None else []
        if stt_service == STTService.parakeet:
            return await process_audio_parakeet(
                callback, lang, sr, 1, model=model, keywords=keywords, is_active=active_check
            )
        if stt_service == STTService.modulate:
            return await process_audio_modulate(callback, sr, lang)
        return await process_audio_dg(callback, lang, sr, 1, model=model, keywords=keywords, is_active=active_check)

    async def _process_stt():
        nonlocal stt_socket
        try:
            if use_custom_stt:
                logger.info(f"Custom STT mode enabled - using suggested transcripts from app {uid} {session_id}")
                return None

            if is_multi_channel:
                for i, ch_config in enumerate(channel_configs):

                    def make_multi_channel_callback(cfg: ChannelConfig) -> Callable[[List[Dict[str, Any]]], None]:
                        def cb(segments: List[Dict[str, Any]]) -> None:
                            for seg in segments:
                                seg['is_user'] = cfg.is_user
                                seg['speaker'] = cfg.speaker_label
                            realtime_segment_buffers.extend(segments)

                        return cb

                    callback = make_multi_channel_callback(ch_config)
                    # Pass the user's vocabulary (always includes "Omi") so phone-call /
                    # multi-channel transcripts get the same keyterm hinting as single-channel.
                    stt_sockets_multi[i] = await _create_stt_socket(
                        callback,
                        stt_language,
                        TARGET_SAMPLE_RATE,
                        stt_model,
                        kw=vocabulary[:100] if vocabulary else None,
                    )
                logger.info(
                    f"Multi-channel STT connections established ({len(channel_configs)} channels) {uid} {session_id}"
                )
                return None

            nonlocal vad_gate
            if should_initialize_vad_gate(override=vad_gate_override, global_gate_enabled=is_gate_enabled()):
                gate_mode = vad_gate_mode(override=vad_gate_override, default_mode=VAD_GATE_MODE)
                try:
                    vad_gate = VADStreamingGate(
                        sample_rate=sample_rate,
                        channels=1,
                        mode=gate_mode,
                        uid=uid,
                        session_id=session_id,
                    )
                    logger.info(
                        'VAD gate initialized mode=%s codec=%s sample_rate=%s uid=%s session=%s',
                        gate_mode,
                        codec,
                        sample_rate,
                        uid,
                        session_id,
                    )
                except Exception:
                    logger.exception('VAD gate init failed, continuing without gate uid=%s session=%s', uid, session_id)
                    vad_gate = None
            passthrough = stt_service == STTService.modulate

            raw_socket = await _create_stt_socket(
                make_stream_callback(stream_transcript, vad_gate, passthrough),
                stt_language,
                sample_rate,
                stt_model,
                kw=vocabulary[:100] if vocabulary else None,
                active_check=lambda: session.active,
            )
            if vad_gate is not None and raw_socket is not None:
                stt_socket = GatedSTTSocket(raw_socket, gate=vad_gate, passthrough_audio=passthrough)
            else:
                stt_socket = raw_socket
            return None

        except Exception as e:
            logger.error(f"Initial processing error: {e} {uid} {session_id}")
            session.close_code = 1011
            await websocket.close(code=session.close_code)
            return None

    # Pusher
    #
    transcript_send: Optional[Callable[..., Any]] = None
    transcript_consume: Optional[Callable[..., Any]] = None
    audio_bytes_send: Optional[Callable[..., Any]] = None
    audio_bytes_consume: Optional[Callable[..., Any]] = None
    pusher_close: Optional[Callable[..., Any]] = None
    pusher_connect: Optional[Callable[..., Any]] = None
    request_conversation_processing: Optional[Callable[..., Any]] = None
    pusher_receive: Optional[Callable[..., Any]] = None
    pusher_is_connected: Optional[Callable[..., Any]] = None
    _pusher_is_degraded: Optional[Callable[..., Any]] = None
    pusher_start_degraded: Optional[Callable[..., Any]] = None
    send_speaker_sample_request: Optional[Callable[..., Any]] = None
    pusher_heartbeat: Optional[Callable[..., Any]] = None

    # Transcripts
    #
    translation_enabled = translation_language is not None
    language_cache = TranscriptSegmentLanguageCache()
    translation_service = TranslationService()

    # Normalize locale-tagged language (e.g. "en-US" -> "en") for langdetect compatibility
    _translation_language_base = translation_language.split('-')[0] if translation_language else None

    # Translation coordinator (issue #6155) — replaces debounce/per-segment state
    translation_persist_lock = asyncio.Lock()
    conversation_language_state = (
        ConversationLanguageState(translation_language or 'en') if translation_enabled else None
    )

    async def _on_translation_ready(segment_id: str, translated_text: str, detected_lang: str, conversation_id: str):
        """Callback from TranslationCoordinator when a translation is ready to persist."""
        if not translation_language:
            return
        if not session.active and not (translation_coordinator and translation_coordinator._flushing):  # type: ignore[reportPrivateUsage]  # access translation coordinator flush flag
            return

        try:
            trans = Translation(lang=translation_language, text=translated_text)

            # Persist with lock to prevent concurrent read-modify-write clobbering
            async with translation_persist_lock:
                if conversation_id == session.current_conversation_id:
                    conversation = _get_cached_conversation()
                    protection_level = _cached_protection_level
                else:
                    conversation = conversations_db.get_conversation(uid, conversation_id)
                    protection_level = None
                if conversation:
                    for i, existing_segment in enumerate(conversation.get('transcript_segments', [])):
                        if existing_segment['id'] == segment_id:
                            # Update or add translation
                            translations = existing_segment.get('translations', [])
                            existing_idx = next(
                                (j for j, t in enumerate(translations) if t.get('lang') == translation_language), None
                            )
                            if existing_idx is not None:
                                translations[existing_idx] = trans.model_dump()
                            else:
                                translations.append(trans.model_dump())
                            conversation['transcript_segments'][i]['translations'] = translations
                            conversations_db.update_conversation_segments(
                                uid,
                                conversation_id,
                                conversation['transcript_segments'],
                                data_protection_level=protection_level,
                            )
                            if conversation_id == session.current_conversation_id:
                                _update_cached_segments(conversation['transcript_segments'])
                            break

            if session.active:
                # Build segment dict for the event
                seg_dict = None
                if conversation_id == session.current_conversation_id:
                    conv = _get_cached_conversation()
                    if conv:
                        for s in conv.get('transcript_segments', []):
                            if s['id'] == segment_id:
                                seg_dict = s
                                break
                if seg_dict:
                    _send_message_event(TranslationEvent(segments=[seg_dict]))

        except Exception as e:
            logger.error(f"Translation persist error: {e} {uid} {session_id}")

    translation_coordinator: Optional[TranslationCoordinator] = (
        TranslationCoordinator(
            target_language=translation_language or 'en',
            translation_service=translation_service,
            on_translation_ready=_on_translation_ready,
            language_state=conversation_language_state,
        )
        if translation_enabled
        else None
    )

    # Keep legacy state for backward compatibility during transition
    _pending_translations = {}
    _translation_flushing = False

    async def translate(
        segments: List[TranscriptSegment], conversation_id: str, removed_ids: Optional[List[str]] = None
    ):
        """Route updated segments to the TranslationCoordinator."""
        if not translation_coordinator:
            return
        await translation_coordinator.observe(segments, removed_ids or [], conversation_id)

    async def flush_pending_translations():
        """Flush all pending translations before cleanup."""
        if translation_coordinator:
            await translation_coordinator.flush()
            m = translation_coordinator.metrics
            logger.info(
                f"translate_summary {uid} session={session_id} "
                f"mono_skips={m['mono_gate_skips']} classify_skips={m['classify_skips']} "
                f"defers={m['classify_defers']} translates={m['classify_translates']} "
                f"batches={m['batch_api_calls']} neg_cache={m['negative_cache_sets']} "
                f"prefix_resets={m['prefix_resets']}"
            )

    async def conversation_lifecycle_manager():
        """Background task that checks conversation timeout and triggers processing every 5 seconds."""
        nonlocal conversation_creation_timeout

        logger.info(
            f"Starting conversation lifecycle manager (timeout: {conversation_creation_timeout}s) {uid} {session_id}"
        )

        while session.active:
            await asyncio.sleep(5)

            if not session.current_conversation_id:
                logger.warning(f"WARN: the current conversation is not valid {uid} {session_id}")
                continue

            conversation = conversations_db.get_conversation(uid, session.current_conversation_id)
            if not conversation:
                logger.warning(
                    f"WARN: the current conversation is not found (id: {session.current_conversation_id}) {uid} {session_id}"
                )
                await _create_new_in_progress_conversation()
                continue

            # Check if conversation status is not in_progress
            action = decide_lifecycle_action(
                conversation_exists=True,
                status=conversation.get('status'),
                in_progress_status=ConversationStatus.in_progress,
                seconds_since_last_update=None,
                conversation_creation_timeout=conversation_creation_timeout,
            )
            if action == ConversationLifecycleAction.create_new:
                logger.warning(
                    f"WARN: conversation {session.current_conversation_id} status is {conversation.get('status')}, not in_progress. Creating new conversation. {uid} {session_id}"
                )
                await _create_new_in_progress_conversation()
                continue

            # Check if conversation should be processed
            finished_at = datetime.fromisoformat(conversation['finished_at'].isoformat())
            seconds_since_last_update = (datetime.now(timezone.utc) - finished_at).total_seconds()
            action = decide_lifecycle_action(
                conversation_exists=True,
                status=conversation.get('status'),
                in_progress_status=ConversationStatus.in_progress,
                seconds_since_last_update=seconds_since_last_update,
                conversation_creation_timeout=conversation_creation_timeout,
            )
            if action == ConversationLifecycleAction.process_and_create_new:
                logger.info(
                    f"Conversation {session.current_conversation_id} timeout reached ({seconds_since_last_update:.1f}s). Processing... {uid} {session_id}"
                )
                # Drain any in-flight embedding match tasks before flushing
                if speaker_match_tasks:
                    await drain_tasks(
                        list(speaker_match_tasks), timeout=5.0, label="listen_speaker_rollover", cancel=False
                    )
                _flush_speaker_assignments(session.current_conversation_id)
                await _process_conversation(session.current_conversation_id)
                await _create_new_in_progress_conversation()

    async def speaker_identification_task():
        """Consume segment queue, accumulate per speaker, trigger match when ready."""
        nonlocal speaker_to_person_map
        nonlocal person_embeddings_cache

        if not session.speaker_id_enabled:
            session.speaker_id_done.set()
            return

        # Load user's own embedding from Firestore (extracted at profile creation time)
        # Fallback: if user has a speech profile but no stored embedding (pre-deployment profiles),
        # extract from the WAV file and store it in Firestore for future sessions.
        if has_speech_profile:
            try:
                embedding_list = await run_blocking(db_executor, user_db.get_user_speaker_embedding, uid)
                if embedding_list:
                    user_embedding = np.array(embedding_list, dtype=np.float32).reshape(1, -1)
                    person_embeddings_cache[USER_SELF_PERSON_ID] = {
                        'embedding': user_embedding,
                        'name': 'User',
                    }
                    logger.info(f"Speaker ID: loaded user speaker embedding from Firestore {uid} {session_id}")
                else:
                    logger.info(f"Speaker ID: no stored embedding, extracting from speech profile {uid} {session_id}")
                    file_path = await run_blocking(storage_executor, get_profile_audio_if_exists, uid)
                    if file_path:

                        def _read_file(p: Any) -> bytes:
                            with open(p, 'rb') as f:
                                return f.read()

                        profile_bytes = await run_blocking(storage_executor, _read_file, file_path)
                        user_embedding = cast(
                            "np.ndarray[Any, Any]",
                            await run_blocking(
                                sync_executor,
                                cast(Any, extract_embedding_from_bytes),
                                profile_bytes,
                                "speech_profile.wav",
                            ),
                        )
                        del profile_bytes
                        person_embeddings_cache[USER_SELF_PERSON_ID] = {
                            'embedding': user_embedding,
                            'name': 'User',
                        }
                        # Store in Firestore so future sessions load directly
                        await run_blocking(
                            db_executor,
                            user_db.set_user_speaker_embedding,
                            uid,
                            user_embedding.flatten().tolist(),
                        )
                        logger.info(f"Speaker ID: extracted and stored user embedding {uid} {session_id}")
            except Exception as e:
                logger.error(f"Speaker ID: failed to load user embedding: {e} {uid} {session_id}")

        # Load person embeddings (migrate if needed for v2 API compatibility)
        try:
            people: List[Dict[str, Any]] = user_db.get_people(uid)
            for person in people:
                # Migrate if needed for v2 API compatibility
                if person.get('speech_samples'):
                    person = await maybe_migrate_person_samples(uid, person)

                # Skip cache if migration failed (version still <3) to avoid mixing embedding spaces
                if person.get('speech_samples_version', 1) < 3:
                    continue

                emb = person.get('speaker_embedding')
                # Only load embedding if person has speech samples — contacts without
                # samples may have stale embeddings from a pre-v3 model (#6238)
                if emb and person.get('speech_samples'):
                    person_embeddings_cache[person['id']] = {
                        'embedding': np.array(emb, dtype=np.float32).reshape(1, -1),
                        'name': person['name'],
                    }
            logger.info(f"Speaker ID: loaded {len(person_embeddings_cache)} person embeddings {uid} {session_id}")
        except Exception as e:
            logger.error(f"Speaker ID: failed to load embeddings: {e} {uid} {session_id}")
            session.speaker_id_done.set()
            return

        if not person_embeddings_cache:
            logger.info(f"Speaker ID: no stored embeddings, task disabled {uid} {session_id}")
            session.speaker_id_done.set()
            return

        # Consume loop — keep running until websocket closes AND queue is drained.
        # stream_transcript_process can enqueue segments after session.active=False,
        # so we must not exit on the flag alone.
        while True:
            try:
                seg = await asyncio.wait_for(speaker_id_segment_queue.get(), timeout=2.0)
            except asyncio.TimeoutError:
                if not session.active:
                    break  # WebSocket closed and no data for 2s — queue is drained
                continue

            speaker_id: Any = seg['speaker_id']

            # Skip if already resolved
            if should_spawn_speaker_match(
                speaker_already_mapped=speaker_id in speaker_to_person_map,
                duration=seg['duration'],
                min_audio_seconds=SPEAKER_ID_MIN_AUDIO,
            ):
                task = spawn(_match_speaker_embedding(speaker_id, seg), name="speaker_match")
                speaker_match_tasks.add(task)
                task.add_done_callback(speaker_match_tasks.discard)

        logger.info(f"Speaker ID task ended {uid} {session_id}")
        session.speaker_id_done.set()

    async def _match_speaker_embedding(speaker_id: int, segment: Dict[str, Any]) -> None:
        """Extract audio from ring buffer and match against stored embeddings."""
        nonlocal speaker_to_person_map, segment_person_assignment_map

        try:
            seg_start = segment['abs_start']
            seg_end = segment['abs_end']
            duration = segment['duration']

            if duration < SPEAKER_ID_MIN_AUDIO:
                logger.info(f"Speaker ID: segment too short ({duration:.1f}s) {uid} {session_id}")
                return

            # Get buffer time range
            ring_buffer = session.audio_ring_buffer
            if ring_buffer is None:
                logger.info(f"Speaker ID: buffer not initialized {uid} {session_id}")
                return
            time_range = ring_buffer.get_time_range()
            if time_range is None:
                logger.info(f"Speaker ID: buffer empty {uid} {session_id}")
                return

            buffer_start_ts, buffer_end_ts = time_range

            # Calculate extraction range - stay within segment bounds, max 10 seconds from center
            MAX_EXTRACT_DURATION = 10.0

            if duration <= MAX_EXTRACT_DURATION:
                # Segment fits within max duration, use full segment
                extract_start = seg_start
                extract_end = seg_end
            else:
                # Segment is longer than max, extract 10s from center
                center = (seg_start + seg_end) / 2
                half_duration = MAX_EXTRACT_DURATION / 2
                extract_start = center - half_duration
                extract_end = center + half_duration

            # Clamp to buffer availability
            extract_start = max(buffer_start_ts, extract_start)
            extract_end = min(buffer_end_ts, extract_end)

            if extract_end <= extract_start:
                logger.info(f"Speaker ID: no audio to extract {uid} {session_id}")
                return

            # Reject clips too short for speaker embedding (issue #4572)
            extracted_duration = extract_end - extract_start
            if extracted_duration < SPEAKER_ID_MIN_AUDIO:
                logger.info(
                    f"Speaker ID: extracted audio too short ({extracted_duration:.2f}s < {SPEAKER_ID_MIN_AUDIO}s) after buffer clamping {uid} {session_id}"
                )
                return

            # Extract only the needed bytes directly from ring buffer
            pcm_data = ring_buffer.extract(extract_start, extract_end)
            if not pcm_data:
                logger.error(f"Speaker ID: failed to extract audio {uid} {session_id}")
                return

            # Convert PCM to numpy for WAV encoding
            samples = np.frombuffer(pcm_data, dtype=np.int16)

            # Convert PCM to WAV using av
            output_buffer = io.BytesIO()
            output_container = av.open(output_buffer, mode='w', format='wav')
            output_stream: Any = output_container.add_stream('pcm_s16le', rate=sample_rate)
            output_stream.layout = 'mono'

            frame = av.AudioFrame.from_ndarray(samples.reshape(1, -1), format='s16', layout='mono')
            frame.rate = sample_rate

            for packet in output_stream.encode(frame):
                output_container.mux(packet)
            for packet in output_stream.encode():
                output_container.mux(packet)

            output_container.close()
            wav_bytes = output_buffer.getvalue()

            # Extract embedding (API call)
            query_embedding = cast(
                "np.ndarray[Any, Any]",
                await run_blocking(sync_executor, cast(Any, extract_embedding_from_bytes), wav_bytes, "query.wav"),
            )
            # Find best match
            best_match = None
            best_distance = float('inf')

            logger.debug(
                f"Speaker ID: comparing speaker {speaker_id} against {len(person_embeddings_cache)} people: {uid} {session_id}"
            )
            for person_id, data in person_embeddings_cache.items():
                distance = compare_embeddings(query_embedding, data['embedding'])
                logger.debug(f"  - {sanitize_pii(data['name'])}: {distance:.4f} {uid} {session_id}")
                if distance < best_distance:
                    best_distance = distance
                    best_match = (person_id, data['name'])

            if best_match and best_distance < SPEAKER_MATCH_THRESHOLD:
                person_id, person_name = best_match

                if is_user_self_match(person_id):
                    # User's own voice matched — mark speaker as user for session consistency
                    logger.info(
                        f"Speaker ID: speaker {speaker_id} -> USER (distance={best_distance:.3f}) {uid} {session_id}"
                    )
                    speaker_to_person_map[speaker_id] = (USER_SELF_PERSON_ID, 'User')

                    # Auto-assign the triggering segment so it gets corrected on next batch
                    segment_person_assignment_map[segment['id']] = USER_SELF_PERSON_ID

                    # Notify client so it can retroactively update all segments with this speaker_id
                    # to is_user=true (segments sent before the embedding match had is_user=false).
                    # Always send 'user' directly — is_user is fundamental, not gated by auto_assign.
                    _send_message_event(
                        SpeakerLabelSuggestionEvent(
                            speaker_id=speaker_id,
                            person_id='user',
                            person_name='User',
                            segment_id=segment['id'],
                        )
                    )
                    session.speaker_map_dirty = True
                else:
                    logger.info(
                        f"Speaker ID: speaker {speaker_id} -> {sanitize_pii(person_name)} (distance={best_distance:.3f}) {uid} {session_id}"
                    )

                    # Store for session consistency
                    speaker_to_person_map[speaker_id] = (person_id, person_name)

                    # Auto-assign processed segment
                    segment_person_assignment_map[segment['id']] = person_id

                    # Notify client (gated for backward compatibility)
                    _send_message_event(
                        SpeakerLabelSuggestionEvent(
                            speaker_id=speaker_id,
                            person_id=_person_id_for_client(person_id),
                            person_name=person_name,
                            segment_id=segment['id'],
                        )
                    )
                    session.speaker_map_dirty = True
            else:
                logger.info(f"Speaker ID: speaker {speaker_id} no match (best={best_distance:.3f}) {uid} {session_id}")

        except Exception as e:
            logger.error(f"Speaker ID: match error for speaker {speaker_id}: {e} {uid} {session_id}")

    # In-memory conversation cache to avoid Firestore re-reads every 0.6s
    _cached_conversation_data = None
    _cached_conversation_id = None
    _cached_conversation_time = 0.0  # monotonic
    _cached_protection_level = 'standard'
    CONVERSATION_CACHE_REFRESH_SECONDS = 30

    def _get_cached_conversation(force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        nonlocal _cached_conversation_data, _cached_conversation_id, _cached_conversation_time, _cached_protection_level
        now = time.monotonic()
        id_changed = session.current_conversation_id != _cached_conversation_id
        stale = (now - _cached_conversation_time) >= CONVERSATION_CACHE_REFRESH_SECONDS
        if _cached_conversation_data is None or id_changed or stale or force_refresh:
            current_id = cast(str, session.current_conversation_id)
            data = conversations_db.get_conversation(uid, current_id)
            if data:
                _cached_conversation_data = data
                _cached_conversation_id = session.current_conversation_id
                _cached_conversation_time = now
                _cached_protection_level = data.get('data_protection_level', 'standard')
            return data
        return _cached_conversation_data

    def _update_cached_segments(segments_dicts: List[Dict[str, Any]]) -> None:
        """Update the cached conversation's transcript_segments in-place after a write."""
        if _cached_conversation_data is not None:
            _cached_conversation_data['transcript_segments'] = segments_dicts

    def _flush_speaker_assignments(conversation_id: Optional[str]) -> None:
        """Apply any pending speaker assignments to conversation segments in Firestore.

        Called before conversation rollover/processing to ensure labels are persisted
        even if the embedding match landed after the last transcript batch.
        """
        if not (speaker_to_person_map or segment_person_assignment_map) or not conversation_id:
            return
        try:
            conversation_data = _get_cached_conversation(force_refresh=True)
            if not conversation_data:
                return
            conversation = deserialize_conversation(conversation_data)
            if not conversation.transcript_segments:
                return
            process_speaker_assigned_segments(
                conversation.transcript_segments,
                segment_person_assignment_map,
                speaker_to_person_map,
            )
            segments_dicts = [seg.model_dump() for seg in conversation.transcript_segments]
            conversations_db.update_conversation_segments(
                uid, conversation.id, segments_dicts, data_protection_level=_cached_protection_level
            )
            _update_cached_segments(segments_dicts)
            session.speaker_map_dirty = False
        except Exception as e:
            logger.error(f"Error flushing speaker assignments for {conversation_id}: {e} {uid} {session_id}")

    async def stream_transcript_process():
        nonlocal realtime_segment_buffers, realtime_photo_buffers, websocket
        nonlocal translation_enabled, speaker_to_person_map, suggested_segments

        while session.active or len(realtime_segment_buffers) > 0 or len(realtime_photo_buffers) > 0:
            await asyncio.sleep(0.6)

            # Periodic cleanup of expired image chunks (enforces TTL even when uploads stop)
            _cleanup_expired_image_chunks()

            if not realtime_segment_buffers and not realtime_photo_buffers:
                continue

            segments_to_process = sort_segments_by_start(list(realtime_segment_buffers))
            realtime_segment_buffers.clear()

            photos_to_process = list(realtime_photo_buffers)
            realtime_photo_buffers.clear()

            finished_at = datetime.now(timezone.utc)

            # Get conversation (cached — refreshes on ID change or every 30s)
            conversation_data = _get_cached_conversation()
            if not conversation_data:
                logger.warning(
                    f"Warning: conversation {session.current_conversation_id} not found during segment processing {uid} {session_id}"
                )
                continue

            # Guard session.first_audio_byte_timestamp must be set
            if not session.first_audio_byte_timestamp:
                logger.warning(
                    f"Warning: session.first_audio_byte_timestamp not set, skipping segment processing {uid} {session_id}"
                )
                continue

            transcript_segments = []
            time_offset: float = 0.0
            if segments_to_process:
                session.last_transcript_time = time.time()

                # If conversation has no segments yet, set started_at based on when first speech occurred
                if not conversation_data.get('transcript_segments'):
                    first_speech_timestamp = session.first_audio_byte_timestamp + segments_to_process[0]["start"]
                    new_started_at = datetime.fromtimestamp(first_speech_timestamp, tz=timezone.utc)
                    conversations_db.update_conversation(
                        uid, cast(str, session.current_conversation_id), {'started_at': new_started_at}
                    )
                    conversation_data['started_at'] = new_started_at

                # Calculate unified time offset: audio stream start relative to conversation start
                conversation_started_at = conversation_data['started_at']
                if isinstance(conversation_started_at, str):
                    conversation_started_at = datetime.fromisoformat(conversation_started_at)
                time_offset = session.first_audio_byte_timestamp - conversation_started_at.timestamp()

                # Apply offset to all segments
                for i, segment in enumerate(segments_to_process):
                    segment["start"] += time_offset
                    segment["end"] += time_offset
                    segments_to_process[i] = segment

                newly_processed_segments: List[TranscriptSegment] = []
                for s in segments_to_process:
                    segment = TranscriptSegment(**s, speech_profile_processed=True)
                    # In onboarding mode, force is_user=True for non-Omi segments (user's answers)
                    if onboarding_mode and s.get('speaker_id') != OnboardingHandler.OMI_SPEAKER_ID:
                        segment.is_user = True
                    newly_processed_segments.append(segment)
                words_transcribed = len(" ".join([seg.text for seg in newly_processed_segments]).split())
                if words_transcribed > 0:
                    session.words_transcribed_since_last_record += words_transcribed

                for seg in newly_processed_segments:
                    current_session_segments[cast(str, seg.id)] = seg.speech_profile_processed
                transcript_segments, _, _ = TranscriptSegment.combine_segments([], newly_processed_segments)

            # Update transcript segments
            conversation = deserialize_conversation(conversation_data)
            result = _update_in_progress_conversation(conversation, transcript_segments, photos_to_process, finished_at)
            if not result or not result[0]:
                continue
            conversation, updated_segments, removed_ids = result

            if removed_ids:
                _send_message_event(SegmentsDeletedEvent(segment_ids=removed_ids))

            if transcript_segments:
                await websocket.send_json([segment.model_dump() for segment in updated_segments])

                if transcript_send is not None and user_has_credits:
                    transcript_send([segment.model_dump() for segment in transcript_segments])
                elif not PUSHER_ENABLED and user_has_credits:
                    # Fallback: trigger realtime integrations directly when pusher is disabled
                    try:
                        await trigger_realtime_integrations(
                            uid,
                            [s.model_dump() for s in transcript_segments],
                            session.current_conversation_id,
                            source=source,
                        )
                    except Exception as e:
                        logger.error(f"Error triggering realtime integrations: {e} {uid} {session_id}")

                # Onboarding: pass segments to handler for answer detection
                if onboarding_handler and not onboarding_handler.completed:
                    onboarding_handler.on_segments_received([s.model_dump() for s in transcript_segments])

                if translation_enabled:
                    await translate(updated_segments, conversation.id, removed_ids=removed_ids)

                # Speaker detection
                for segment in updated_segments:
                    if should_skip_speaker_detection(
                        person_id=segment.person_id,
                        is_user=segment.is_user,
                        segment_id=cast(str, segment.id),
                        suggested_segments=cast(Sequence[str], suggested_segments),
                    ):
                        continue

                    # Session consistency speaker identification
                    if segment.speaker_id in speaker_to_person_map:
                        person_id, person_name = speaker_to_person_map[segment.speaker_id]
                        if is_user_self_match(person_id):
                            # User's own voice — set is_user flag
                            segment.is_user = True
                            suggested_segments.add(cast(str, segment.id))
                            continue
                        _send_message_event(
                            SpeakerLabelSuggestionEvent(
                                speaker_id=segment.speaker_id,
                                person_id=_person_id_for_client(person_id),
                                person_name=person_name,
                                segment_id=cast(str, segment.id),
                            )
                        )
                        suggested_segments.add(cast(str, segment.id))
                        continue

                    # Embeding id speaker indentification
                    if should_queue_speaker_embedding(
                        speaker_id=segment.speaker_id,
                        person_id=segment.person_id,
                        is_user=segment.is_user,
                        speaker_id_enabled=session.speaker_id_enabled,
                        has_person_embeddings=bool(person_embeddings_cache),
                        speaker_already_mapped=segment.speaker_id in speaker_to_person_map,
                    ):
                        try:
                            speaker_id_segment_queue.put_nowait(
                                {
                                    'id': segment.id,
                                    'speaker_id': segment.speaker_id,
                                    'abs_start': session.first_audio_byte_timestamp
                                    + segment.start
                                    - time_offset,  # raw start/end
                                    'abs_end': session.first_audio_byte_timestamp + segment.end - time_offset,
                                    'duration': segment.end - segment.start,
                                }
                            )
                        except asyncio.QueueFull:
                            pass  # Drop if queue is full

                    # Text-based detection
                    detected_name = detect_speaker_from_text(segment.text)
                    if detected_name:
                        person = user_db.get_person_by_name(uid, detected_name)
                        generated_person_id = str(uuid.uuid4()) if not person and create_speakers else ''
                        text_assignment = decide_text_speaker_assignment(
                            existing_person_id=person['id'] if person else None,
                            create_speakers=create_speakers,
                            generated_person_id=generated_person_id,
                            speaker_auto_assign_enabled=speaker_auto_assign_enabled,
                        )
                        if text_assignment.should_create_person:
                            # Backend creates person if missing
                            user_db.create_person(
                                uid,
                                {
                                    'id': text_assignment.person_id,
                                    'name': detected_name,
                                    'created_at': datetime.now(timezone.utc),
                                    'updated_at': datetime.now(timezone.utc),
                                },
                            )
                        _send_message_event(
                            SpeakerLabelSuggestionEvent(
                                speaker_id=cast(int, segment.speaker_id),
                                person_id=text_assignment.event_person_id,
                                person_name=detected_name,
                                segment_id=cast(str, segment.id),
                            )
                        )
                        # Set maps for future segments, but only if diarization is active
                        # (speaker_id > 0 means diarization assigned a real speaker)
                        # Set maps for future segments using helper function
                        if text_assignment.update_maps:
                            if should_update_speaker_to_person_map(segment.speaker_id):
                                speaker_to_person_map[cast(int, segment.speaker_id)] = (
                                    cast(str, text_assignment.person_id),
                                    detected_name,
                                )
                            segment_person_assignment_map[cast(str, segment.id)] = cast(str, text_assignment.person_id)
                        suggested_segments.add(cast(str, segment.id))

        # Wait for speaker_identification_task to finish consuming its queue and spawning
        # all _match_speaker_embedding tasks, then drain those tasks so speaker maps are
        # fully populated before the final Firestore flush.
        try:
            await asyncio.wait_for(session.speaker_id_done.wait(), timeout=15.0)
        except asyncio.TimeoutError:
            logger.warning(f"Timeout waiting for speaker ID task to finish {uid} {session_id}")
        if speaker_match_tasks:
            await drain_tasks(list(speaker_match_tasks), timeout=10.0, label="listen_speaker_final", cancel=False)

        # Final pass: apply any pending speaker assignments so Firestore is correct
        # even if the embedding match completed on the last segment (no subsequent batch).
        _flush_speaker_assignments(session.current_conversation_id)

    # Image chunks cache with TTL tracking: {temp_id: {'chunks': [...], 'created_at': float}}
    # Using OrderedDict for O(1) oldest removal (insertion order preserved)
    image_chunks: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
    last_image_chunk_cleanup = 0.0

    def _cleanup_expired_image_chunks():
        """Remove image chunks that have exceeded TTL."""
        nonlocal last_image_chunk_cleanup
        now = time.time()
        if now - last_image_chunk_cleanup < IMAGE_CHUNK_CLEANUP_INTERVAL:
            return
        if image_chunks and len(image_chunks) < IMAGE_CHUNK_CLEANUP_MIN_SIZE:
            oldest_created_at = next(iter(image_chunks.values()))['created_at']
            if now - oldest_created_at <= IMAGE_CHUNK_TTL:
                last_image_chunk_cleanup = now
                return
        last_image_chunk_cleanup = now
        expired = [tid for tid, data in image_chunks.items() if now - data['created_at'] > IMAGE_CHUNK_TTL]
        for tid in expired:
            del image_chunks[tid]
            logger.warning(f"Expired incomplete image upload: {tid} {uid} {session_id}")

    async def process_photo(
        uid: str,
        image_b64: str,
        temp_id: str,
        send_event_func: Callable[[MessageEvent], Awaitable[Any]],
        photo_buffer: "deque[ConversationPhoto]",
    ):
        from utils.llm.openglass import describe_image

        photo_id = str(uuid.uuid4())
        await send_event_func(PhotoProcessingEvent(temp_id=temp_id, photo_id=photo_id))

        try:
            description = await describe_image(uid, image_b64)
            discarded = not description or not description.strip()
        except Exception as e:
            logger.error(f"Error describing image: {e} {uid} {session_id}")
            description = "Could not generate description."
            discarded = True

        final_photo = ConversationPhoto(id=photo_id, base64=image_b64, description=description, discarded=discarded)
        photo_buffer.append(final_photo)
        await send_event_func(PhotoDescribedEvent(photo_id=photo_id, description=description, discarded=discarded))

    async def handle_image_chunk(
        uid: str,
        chunk_data: Dict[str, Any],
        image_chunks_cache: "OrderedDict[str, Dict[str, Any]]",
        send_event_func: Callable[[MessageEvent], Awaitable[Any]],
        photo_buffer: "deque[ConversationPhoto]",
    ):
        try:
            chunk = ImageChunkEnvelope.model_validate(chunk_data)
        except ValueError as e:
            logger.error(f"Invalid image chunk received: {sanitize(chunk_data)} {uid} {session_id}: {e}")
            raise ValueError('invalid image chunk') from e

        temp_id = chunk.id
        index = chunk.index
        total = chunk.total
        data = chunk.data

        # Cleanup expired chunks periodically
        _cleanup_expired_image_chunks()

        if temp_id not in image_chunks_cache:
            # Enforce max concurrent uploads - O(1) with OrderedDict
            if len(image_chunks_cache) >= MAX_IMAGE_CHUNKS:
                # Remove oldest entry (first inserted)
                oldest_id, _ = image_chunks_cache.popitem(last=False)
                logger.info(f"Dropped oldest image upload to make room: {oldest_id} {uid} {session_id}")
            image_chunks_cache[temp_id] = {'chunks': [None] * total, 'created_at': time.time()}

        chunks_data = image_chunks_cache[temp_id]['chunks']
        try:
            chunk.validate_against_cached_total(len(chunks_data))
        except ValueError as e:
            logger.error(f"Invalid image chunk sequence received: {sanitize(chunk_data)} {uid} {session_id}: {e}")
            raise ValueError('invalid image chunk sequence') from e

        if chunks_data[index] is None:
            chunks_data[index] = data

        if all(chunk is not None for chunk in chunks_data):
            b64_image_data = "".join(chunks_data)
            del image_chunks_cache[temp_id]
            spawn(process_photo(uid, b64_image_data, temp_id, send_event_func, photo_buffer), name="photo_process")

    # Initialize decoders based on codec
    opus_decoder: Any = None
    aac_decoder: Any = None
    lc3_decoder: Any = None

    if codec == 'opus':
        opus_decoder = _get_opuslib().Decoder(sample_rate, 1)
    elif codec == 'aac':
        aac_decoder = AACDecoder(uid=uid, session_id=session_id, sample_rate=sample_rate, channels=channels)
    elif codec == 'lc3':
        if lc3 is None:
            session.close_code = 1011
            logger.error(f"LC3 codec requested but lc3py is not installed {uid} {session_id}")
            await websocket.close(code=session.close_code, reason="LC3 codec is not available")
            return
        lc3_decoder = _get_lc3().Decoder(lc3_frame_duration_us, sample_rate)

    async def receive_data(stt_socket: Any) -> None:
        nonlocal realtime_photo_buffers, speaker_to_person_map
        timer_start = time.time()
        session.last_audio_received_time = timer_start
        session.last_activity_time = timer_start

        # STT audio buffer - accumulate 30ms before sending for better transcription quality
        stt_audio_buffer = bytearray()
        stt_buffer_flush_size = calculate_stt_buffer_flush_size(
            sample_rate
        )  # 30ms at 16-bit mono (e.g., 6400 bytes at 16kHz)

        async def flush_stt_buffer(force: bool = False):
            nonlocal stt_audio_buffer, stt_socket

            socket_dead = stt_socket is not None and stt_socket.is_connection_dead
            decision = decide_stt_buffer_flush(
                buffer_len=len(stt_audio_buffer),
                flush_size=stt_buffer_flush_size,
                force=force,
                socket_dead=socket_dead,
                socket_available=stt_socket is not None,
                fair_use_dg_budget_exhausted=session.fair_use_dg_budget_exhausted,
                fair_use_track_dg_usage=session.fair_use_track_dg_usage,
                sample_rate=sample_rate,
            )
            if not decision.should_flush:
                return

            chunk = bytes(stt_audio_buffer)
            stt_audio_buffer.clear()

            if decision.socket_dead:
                close_reason = stt_socket.death_reason or 'unknown'
                logger.error(
                    'STT connection died mid-session uid=%s session=%s reason=%s',
                    uid,
                    session_id,
                    close_reason,
                )
                stt_socket = None

            if decision.send_to_stt:
                stt_socket.send(chunk)
                session.dg_usage_ms_pending += decision.dg_usage_ms

        try:
            while session.active:
                try:
                    message = await asyncio.wait_for(websocket.receive(), timeout=WS_RECEIVE_TIMEOUT)
                except asyncio.TimeoutError:
                    logger.warning(f"WS receive timeout ({WS_RECEIVE_TIMEOUT}s), closing connection {uid} {session_id}")
                    break
                session.last_activity_time = time.time()

                # Handle client disconnect
                if message.get("type") == "websocket.disconnect":
                    close_code = message.get("code", 1000)
                    session.close_code = close_code
                    close_reason = {
                        1000: "normal_closure",
                        1001: "going_away_os_or_background",
                        1006: "abnormal_closure",
                        1011: "server_error",
                    }.get(close_code, "unknown")
                    logger.info(f"Client disconnected: code={close_code} reason={close_reason} {uid} {session_id}")
                    break

                data: Any = message.get("bytes")
                if data is not None:
                    if len(data) <= 2:  # Ping/keepalive, 0x8a 0x00
                        continue

                    session.last_audio_received_time = time.time()

                    if session.first_audio_byte_timestamp is None:
                        session.first_audio_byte_timestamp = session.last_audio_received_time
                        session.last_usage_record_timestamp = session.first_audio_byte_timestamp

                    if is_multi_channel:
                        # Multi-channel: demux [channel_id][audio_bytes]
                        channel_id = data[0]
                        audio_data = data[1:]
                        ch_idx = channel_id_to_index.get(channel_id)
                        if ch_idx is None:
                            continue

                        # Decode per-channel
                        if codec == 'opus' and multi_opus_decoders[ch_idx]:
                            try:
                                mc_frame_size = sample_rate // 50  # 20ms frames
                                audio_data = multi_opus_decoders[ch_idx].decode(bytes(audio_data), mc_frame_size)
                                if not audio_data:
                                    continue
                            except Exception as e:
                                logger.error(f"[OPUS-MC] ch={ch_idx} decoding error: {e} {uid} {session_id}")
                                continue

                        # Resample to TARGET_SAMPLE_RATE for STT
                        pcm_16k = resample_pcm(bytes(audio_data), sample_rate, TARGET_SAMPLE_RATE)

                        # Send to per-channel STT (budget-gated for restricted/exhausted users)
                        should_send_mc_stt, mc_dg_usage_ms = decide_multi_channel_stt_send(
                            socket_available=bool(stt_sockets_multi[ch_idx]),
                            fair_use_dg_budget_exhausted=session.fair_use_dg_budget_exhausted,
                            pcm_len=len(pcm_16k),
                            fair_use_track_dg_usage=session.fair_use_track_dg_usage,
                        )
                        if should_send_mc_stt:
                            try:
                                stt_sockets_multi[ch_idx].send(pcm_16k)
                                # Accumulate DG usage locally, flushed every 60s (#5854)
                                session.dg_usage_ms_pending += mc_dg_usage_ms
                            except Exception as e:
                                logger.error(f"[MC-STT] ch={ch_idx} send error: {e} {uid} {session_id}")

                        # Accumulate per-channel audio for mixing before sending to pusher
                        channel_mix_buffers[ch_idx].extend(pcm_16k)

                        # Mix when all channels have data, send mixed mono to pusher
                        mix_decision = decide_multi_channel_mix(
                            channel_mix_buffers, audio_bytes_enabled=audio_bytes_send is not None
                        )
                        if mix_decision.should_mix:
                            trim_bufs = [bytearray(b[: mix_decision.min_len]) for b in channel_mix_buffers]
                            mixed = mix_n_channel_buffers(trim_bufs)
                            if mixed and audio_bytes_send is not None:
                                audio_bytes_send(mixed, session.last_audio_received_time)
                            # Remove consumed bytes from each buffer
                            for buf in channel_mix_buffers:
                                del buf[: mix_decision.min_len]

                    else:
                        # Single-channel: existing logic
                        # Decode based on codec
                        if codec == 'opus' and sample_rate == 16000:
                            try:
                                data = opus_decoder.decode(bytes(data), frame_size=frame_size)
                                if not data:
                                    continue
                            except Exception as e:
                                logger.error(f"[OPUS] Decoding error: {e} {uid} {session_id}")
                                continue
                        elif codec == 'aac':
                            try:
                                data = aac_decoder.decode(bytes(data))
                                if not data:
                                    continue
                            except Exception as e:
                                logger.error(f"[AAC] Decoding error: {e} {uid} {session_id}")
                                continue
                        elif codec == 'lc3':
                            try:
                                # Decode LC3 frame to PCM
                                # lc3.decode returns PCM bytes directly with bit_depth=16
                                pcm_bytes = lc3_decoder.decode(bytes(data), bit_depth=16)
                                if not pcm_bytes:
                                    continue
                                data = pcm_bytes
                            except Exception as e:
                                logger.error(
                                    f"[LC3] Decoding error: {e} | "
                                    f"Data size: {len(data)} bytes (expected: {lc3_chunk_size}) | "
                                    f"Frame duration: {lc3_frame_duration_us}μs | "
                                    f"Sample rate: {sample_rate}Hz {uid} {session_id}"
                                )
                                continue

                        if codec == 'pcm8':
                            data = audioop.bias(data, 1, -128)
                            data = audioop.lin2lin(data, 1, 2)

                        # Feed ring buffer for speaker identification (always, with wall-clock time)
                        if session.audio_ring_buffer is not None:
                            session.audio_ring_buffer.write(data, session.last_audio_received_time)

                        if not use_custom_stt:
                            # VAD gating is handled inside GatedSTTSocket.send()
                            stt_audio_buffer.extend(data)
                            await flush_stt_buffer()

                        if audio_bytes_send is not None:
                            audio_bytes_send(data, session.last_audio_received_time)

                elif (message_text := message.get("text")) is not None:
                    try:
                        loaded: object = json.loads(message_text)
                        json_data: Dict[str, Any] = cast(Dict[str, Any], loaded) if isinstance(loaded, dict) else {}
                        if json_data.get('type') == 'image_chunk':
                            try:
                                await handle_image_chunk(
                                    uid, json_data, image_chunks, _asend_message_event, realtime_photo_buffers
                                )
                            except ValueError:
                                session.close_code = 1008
                                session.active = False
                                break
                        elif json_data.get('type') == 'skip_question':
                            if onboarding_handler and not onboarding_handler.completed:
                                await onboarding_handler.skip_current_question()
                        elif json_data.get('type') == 'suggested_transcript':
                            if use_custom_stt:
                                suggested_segments = json_data.get('segments', [])
                                stt_provider = json_data.get('stt_provider')
                                if suggested_segments:
                                    # Attach stt_provider to each segment
                                    if stt_provider:
                                        for seg in suggested_segments:
                                            seg['stt_provider'] = stt_provider
                                    stream_transcript(suggested_segments)
                        elif json_data.get('type') == 'speaker_assigned':
                            segment_ids = json_data.get('segment_ids', [])
                            can_assign = False
                            if segment_ids:
                                for sid in segment_ids:
                                    if sid in current_session_segments and current_session_segments[sid]:
                                        can_assign = True
                                        break

                            # Always set maps regardless of can_assign (fixes latest segments missed)
                            speaker_id = json_data.get('speaker_id')
                            person_id = json_data.get('person_id')
                            person_name = json_data.get('person_name')
                            maps_updated = update_speaker_assignment_maps(
                                cast(int, speaker_id),
                                cast(str, person_id),
                                cast(str, person_name),
                                segment_ids,
                                speaker_to_person_map,
                                segment_person_assignment_map,
                            )
                            if maps_updated:
                                logger.info(
                                    f"Speaker {speaker_id} assigned to {person_name} ({person_id}) {uid} {session_id}"
                                )

                                # Forward to pusher for speech sample extraction (non-blocking)
                                # Only for real people (not 'user') and when private cloud sync is enabled
                                # Only when can_assign is true (has speech_profile_processed segment)
                                if (
                                    can_assign
                                    and person_id
                                    and person_id != 'user'
                                    and private_cloud_sync_enabled
                                    and send_speaker_sample_request is not None
                                    and session.current_conversation_id
                                ):
                                    spawn(
                                        send_speaker_sample_request(
                                            person_id=person_id,
                                            conv_id=session.current_conversation_id,
                                            segment_ids=segment_ids,
                                        ),
                                        name="speaker_sample_request",
                                    )
                            else:
                                logger.info(
                                    f"Speaker assignment ignored: missing speaker_id/person_id/person_name. {uid} {session_id}"
                                )
                    except json.JSONDecodeError:
                        logger.info(
                            f"Received non-json text message: {sanitize(message.get('text'))} {uid} {session_id}"
                        )

        except WebSocketDisconnect:
            logger.error(f"WebSocket disconnected (exception) {uid} {session_id}")
        except Exception as e:
            logger.error(f'Could not process data: error {e} {uid} {session_id}')
            session.close_code = 1011
        finally:
            # Log VAD gate metrics before cleanup
            if vad_gate is not None:
                logger.info(json.dumps(vad_gate.to_json_log()))
            # Flush any remaining audio in buffer to STT
            if not use_custom_stt:
                await flush_stt_buffer(force=True)
            # EOS drain: send EOS and wait for final transcripts while
            # stream_transcript_process is still running (before session.active=False)
            try:
                if is_multi_channel:
                    for mc_stt_socket in stt_sockets_multi:
                        if mc_stt_socket and hasattr(mc_stt_socket, 'drain_and_close'):
                            await mc_stt_socket.drain_and_close()
                else:
                    drain_target: Any = stt_socket
                    if isinstance(stt_socket, GatedSTTSocket):
                        drain_target = stt_socket._conn  # type: ignore[reportPrivateUsage]  # access underlying STT socket for EOS drain
                    if drain_target and hasattr(drain_target, 'drain_and_close'):
                        await drain_target.drain_and_close()
            except Exception as e:
                logger.error(f"Error draining STT EOS: {e} {uid} {session_id}")
            session.active = False

    # Start
    #
    bg_main_tasks = []
    try:
        task_supervisor.start_session()
        # Init STT
        _send_message_event(MessageServiceStatusEvent(status="stt_initiating", status_text="STT Service Starting"))
        await _process_stt()

        # Init pusher
        pusher_tasks: List[asyncio.Task[Any]] = []
        if PUSHER_ENABLED:
            pusher_session = ListenPusherSession(
                ListenPusherSessionConfig(
                    uid=uid,
                    session_id=session_id,
                    sample_rate=sample_rate,
                    is_multi_channel=is_multi_channel,
                    language=language,
                    audio_bytes_enabled=(
                        bool(get_audio_bytes_webhook_seconds(uid))
                        or is_audio_bytes_app_enabled(uid)
                        or private_cloud_sync_enabled
                    ),
                    max_segment_buffer_size=MAX_SEGMENT_BUFFER_SIZE,
                    max_audio_buffer_size=MAX_AUDIO_BUFFER_SIZE,
                    max_pending_requests=MAX_PENDING_REQUESTS,
                    max_pending_speaker_sample_requests=MAX_PENDING_SPEAKER_SAMPLE_REQUESTS,
                ),
                ListenPusherSessionDeps(
                    get_current_conversation_id=lambda: session.current_conversation_id,
                    is_active=lambda: session.active,
                    shutdown_event=session.shutdown_event,
                    get_byok_keys=get_byok_keys,
                    on_conversation_processed=on_conversation_processed,
                    wait_for_event=wait_for_event,
                ),
            )

            pusher_connect = pusher_session.connect
            pusher_close = pusher_session.close
            transcript_send = pusher_session.transcript_send
            transcript_consume = pusher_session.transcript_consume
            audio_bytes_send = pusher_session.audio_bytes_send if pusher_session.config.audio_bytes_enabled else None
            audio_bytes_consume = (
                pusher_session.audio_bytes_consume if pusher_session.config.audio_bytes_enabled else None
            )
            request_conversation_processing = pusher_session.request_conversation_processing
            pusher_receive = pusher_session.pusher_receive
            pusher_is_connected = pusher_session.is_connected
            _pusher_is_degraded = pusher_session.is_degraded
            pusher_start_degraded = pusher_session.start_degraded
            send_speaker_sample_request = pusher_session.send_speaker_sample_request
            pusher_heartbeat = pusher_session.pusher_heartbeat

            # Pusher connection — graceful degradation instead of 1011 hard close
            try:
                await pusher_connect()
            except PusherCircuitBreakerOpen:
                logger.warning(f"Circuit breaker open on initial connect, starting in degraded mode {uid} {session_id}")
            except Exception as e:
                logger.error(f"Pusher initial connect failed: {e}, starting in degraded mode {uid} {session_id}")

            if not pusher_is_connected():
                logger.warning(
                    f"Pusher not connected, session starts in degraded mode (DG streaming continues) {uid} {session_id}"
                )
                # Enter degraded mode and start reconnect loop
                pusher_start_degraded()

            # Pusher tasks (always started — they handle disconnected state gracefully)
            if transcript_consume is not None:
                pusher_tasks.append(
                    task_supervisor.create_lifetime_task(transcript_consume(), name="pusher_transcript")
                )
            if audio_bytes_consume is not None:
                pusher_tasks.append(task_supervisor.create_lifetime_task(audio_bytes_consume(), name="pusher_audio"))
            if pusher_receive is not None:
                pusher_tasks.append(task_supervisor.create_lifetime_task(pusher_receive(), name="pusher_receive"))
            pusher_tasks.append(task_supervisor.create_lifetime_task(pusher_heartbeat(), name="pusher_heartbeat"))

        # Tasks
        data_process_task = task_supervisor.create_task(receive_data(stt_socket), name="receive")
        heartbeat_task = task_supervisor.create_lifetime_task(send_heartbeat(), name="heartbeat")
        stream_transcript_task = task_supervisor.create_lifetime_task(
            stream_transcript_process(), name="stream_transcript"
        )
        record_usage_task = task_supervisor.create_lifetime_task(_record_usage_periodically(), name="record_usage")

        _send_message_event(MessageServiceStatusEvent(status="ready"))

        bg_main_tasks = [
            stream_transcript_task,
            heartbeat_task,
            record_usage_task,
        ] + pusher_tasks

        if is_multi_channel:
            # Multi-channel doesn't run speaker_identification_task
            session.speaker_id_done.set()

        if not is_multi_channel:
            # Single-channel: conversation lifecycle (timeout splitting), pending processing, speaker ID
            lifecycle_manager_task = task_supervisor.create_lifetime_task(
                conversation_lifecycle_manager(), name="lifecycle"
            )
            pending_conversations_task = task_supervisor.create_finite_task(
                process_pending_conversations(timed_out_conversation_id), name="pending_convos"
            )
            speaker_id_task = task_supervisor.create_finite_task(speaker_identification_task(), name="speaker_id")
            bg_main_tasks.extend([lifecycle_manager_task, pending_conversations_task, speaker_id_task])

        exit_result = await task_supervisor.supervise(receive_task=data_process_task)
        logger.info(f"Supervisor exited: reason={exit_result.reason} task={exit_result.task_name} {uid} {session_id}")

        if data_process_task.done() and not data_process_task.cancelled():
            exc = data_process_task.exception()
            if exc is not None:
                raise exc

        if not data_process_task.done():
            session.active = False
            data_process_task.cancel()
            try:
                await data_process_task
            except asyncio.CancelledError:
                pass

        session.shutdown_event.set()
        await task_supervisor.drain_monitored(timeout=BG_DRAIN_TIMEOUT, cancel=False)

    except Exception as e:
        logger.error(f"Error during WebSocket operation: {e} {uid} {session_id}")
    finally:
        session.shutdown_event.set()
        task_supervisor.end_session()
        if not use_custom_stt and session.last_usage_record_timestamp:
            transcription_seconds = billable_transcription_seconds(
                session.last_usage_record_timestamp, session.last_audio_received_time, time.time()
            )
            words_to_record = session.words_transcribed_since_last_record

            # Flush any pending speech_ms delta to Redis (#5746 reviewer fix)
            # Prevents short-session bypass: users reconnecting every <60s
            # would never trigger the periodic flush in the usage loop.
            speech_seconds_delta = 0
            if vad_gate is not None:
                speech_ms = vad_gate.consume_speech_ms_delta()
                speech_seconds_delta = speech_ms // 1000
                if FAIR_USE_ENABLED and speech_ms > 0:
                    record_speech_ms(uid, speech_ms)
                    logger.debug(f'fair_use: session end flush {speech_ms}ms speech uid={uid} session={session_id}')

            # Flush pending DG usage accumulator (#5854)
            if session.fair_use_track_dg_usage and session.dg_usage_ms_pending > 0:
                record_dg_usage_ms(uid, session.dg_usage_ms_pending)
                session.dg_usage_ms_pending = 0

            if transcription_seconds > 0 or words_to_record > 0 or speech_seconds_delta > 0:
                record_usage(
                    uid,
                    transcription_seconds=transcription_seconds,
                    words_transcribed=words_to_record,
                    speech_seconds=speech_seconds_delta,
                )

        # Flush pending debounced translations BEFORE setting session.active=False
        try:
            await flush_pending_translations()
        except Exception as e:
            logger.error(f"Error flushing pending translations: {e} {uid} {session_id}")

        session.active = False

        # STT sockets
        try:
            if is_multi_channel:
                for mc_stt_socket in stt_sockets_multi:
                    if mc_stt_socket:
                        mc_stt_socket.finish()
            else:
                if stt_socket:
                    stt_socket.finish()
        except Exception as e:
            logger.error(f"Error closing STT sockets: {e} {uid} {session_id}")

        # Client sockets
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close(code=session.close_code)
            except Exception as e:
                logger.error(f"Error closing Client WebSocket: {e} {uid} {session_id}")

        # Single-channel sessions normally stay open for reconnects/timeouts. If the client closes
        # cleanly after writing content, submit that exact conversation so desktop can reconcile it.
        if not is_multi_channel and session.current_conversation_id:
            try:
                conversation = conversations_db.get_conversation(uid, session.current_conversation_id)
                if conversation is not None and should_process_on_disconnect(
                    is_multi_channel=is_multi_channel,
                    close_code=session.close_code,
                    conversation_id=session.current_conversation_id,
                    conversation=conversation,
                    in_progress_status=ConversationStatus.in_progress,
                ):
                    _flush_speaker_assignments(session.current_conversation_id)
                    processed = await _process_conversation(session.current_conversation_id)
                    if processed:
                        current_in_progress_id = redis_db.get_in_progress_conversation_id(uid)
                        if should_remove_in_progress_pointer(
                            current_in_progress_id=current_in_progress_id,
                            conversation_id=session.current_conversation_id,
                        ):
                            redis_db.remove_in_progress_conversation_id(uid)
                        logger.info(
                            f"Single-channel conversation {session.current_conversation_id} submitted for processing on disconnect {uid} {session_id}"
                        )
            except Exception as e:
                logger.error(f"Error processing single-channel conversation on disconnect: {e} {uid} {session_id}")

        # Multi-channel: process the single conversation at session end
        if is_multi_channel and session.current_conversation_id:
            try:
                redis_db.remove_in_progress_conversation_id(uid)
                _flush_speaker_assignments(session.current_conversation_id)
                await _process_conversation(session.current_conversation_id)
                logger.info(
                    f"Multi-channel conversation {session.current_conversation_id} submitted for processing {uid} {session_id}"
                )
            except Exception as e:
                logger.error(f"Error processing multi-channel conversation: {e} {uid} {session_id}")

        # Flush any remaining mixed audio to pusher before closing the socket
        if should_flush_final_multi_channel_mix(
            is_multi_channel=is_multi_channel,
            audio_bytes_enabled=audio_bytes_send is not None,
            buffers=channel_mix_buffers,
        ):
            try:
                mixed = mix_n_channel_buffers(channel_mix_buffers)
                if mixed:
                    if audio_bytes_send is not None:
                        audio_bytes_send(mixed, time.time())
            except Exception as e:
                logger.error(f"Error flushing final multi-channel mix to pusher: {e} {uid} {session_id}")
            for buf in channel_mix_buffers:
                buf.clear()

        # Pusher sockets
        if pusher_close is not None:
            try:
                await pusher_close()
            except Exception as e:
                logger.error(f"Error closing Pusher: {e} {uid} {session_id}")

        # Clean up onboarding handler
        if onboarding_handler:
            onboarding_handler.cleanup()

        await task_supervisor.drain_all(timeout=5.0, cancel=True)

        # Clean up collections and heavy objects to aid garbage collection
        try:
            locked_conversation_ids.clear()
            speaker_to_person_map.clear()
            segment_person_assignment_map.clear()
            current_session_segments.clear()
            suggested_segments.clear()
            realtime_segment_buffers.clear()
            realtime_photo_buffers.clear()
            image_chunks.clear()
            person_embeddings_cache.clear()
            # Release conversation cache
            _cached_conversation_data = None
        except NameError as e:
            # Variables might not be defined if an error occurred early
            logger.error(f"Cleanup error (safe to ignore): {e} {uid} {session_id}")

        # Release heavy objects that hold model state / native resources
        try:
            if vad_gate is not None:
                del vad_gate
            language_cache.cache.clear()
            translation_service.translation_cache.clear()
        except NameError:
            pass

    logger.info(f"_stream_handler ended {uid} {session_id}")


async def _listen(
    websocket: WebSocket,
    uid: str,
    language: str = 'en',
    sample_rate: int = 8000,
    codec: str = 'pcm8',
    channels: int = 1,
    include_speech_profile: bool = True,
    stt_service: Optional[str] = None,
    conversation_timeout: int = 120,
    source: Optional[str] = None,
    custom_stt_mode: CustomSttMode = CustomSttMode.disabled,
    onboarding_mode: bool = False,
    speaker_auto_assign_enabled: bool = False,
    create_speakers: bool = True,
    vad_gate_override: Optional[str] = None,
    call_id: Optional[str] = None,
    client_conversation_id: Optional[str] = None,
):
    """
    WebSocket handler for app clients. Accepts the websocket connection and delegates to _stream_handler.
    """
    logger.info(f"_listen {uid}")
    try:
        await websocket.accept()
    except RuntimeError as e:
        logger.error(f"_listen: accept error {e} {uid}")
        return

    await _stream_handler(
        websocket,
        uid,
        language,
        sample_rate,
        codec,
        channels,
        include_speech_profile,
        stt_service,
        conversation_timeout=conversation_timeout,
        source=source,
        custom_stt_mode=custom_stt_mode,
        onboarding_mode=onboarding_mode,
        speaker_auto_assign_enabled=speaker_auto_assign_enabled,
        create_speakers=create_speakers,
        vad_gate_override=vad_gate_override,
        call_id=call_id,
        client_conversation_id=client_conversation_id,
    )
    logger.info(f"_listen ended {uid}")


@router.websocket("/v4/listen")
async def listen_handler(
    websocket: WebSocket,
    uid: str = Depends(auth.get_current_user_uid_ws_listen),
    language: str = 'en',
    sample_rate: int = 8000,
    codec: str = 'pcm8',
    channels: int = 1,
    include_speech_profile: bool = True,
    stt_service: Optional[str] = None,
    conversation_timeout: int = 120,
    source: Optional[str] = None,
    custom_stt: str = 'disabled',
    onboarding: str = 'disabled',
    speaker_auto_assign: str = 'disabled',
    create_speakers: bool = True,
    vad_gate: str = '',
    call_id: Optional[str] = None,
    client_conversation_id: Optional[str] = None,
):
    custom_stt_mode = CustomSttMode.enabled if custom_stt == 'enabled' else CustomSttMode.disabled
    onboarding_mode = onboarding == 'enabled'
    speaker_auto_assign_enabled = speaker_auto_assign == 'enabled'
    vad_gate_override = vad_gate if vad_gate in ('enabled', 'disabled') else None
    await _listen(
        websocket,
        uid,
        language,
        sample_rate,
        codec,
        channels,
        include_speech_profile,
        stt_service,  # pass the client's requested engine through (e.g. 'parakeet')
        conversation_timeout=conversation_timeout,
        source=source,
        custom_stt_mode=custom_stt_mode,
        onboarding_mode=onboarding_mode,
        speaker_auto_assign_enabled=speaker_auto_assign_enabled,
        create_speakers=create_speakers,
        vad_gate_override=vad_gate_override,
        call_id=call_id,
        client_conversation_id=client_conversation_id,
    )


@router.websocket("/v4/web/listen")
async def web_listen_handler(
    websocket: WebSocket,
    language: str = 'en',
    sample_rate: int = 8000,
    codec: str = 'pcm8',
    channels: int = 1,
    include_speech_profile: bool = True,
    conversation_timeout: int = 120,
    source: Optional[str] = None,
    custom_stt: str = 'disabled',
    onboarding: str = 'disabled',
    call_id: Optional[str] = None,
    client_conversation_id: Optional[str] = None,
):
    """
    WebSocket endpoint for web browser clients using first-message authentication.

    First message must be: {"type": "auth", "token": "<firebase_token>"}
    Response: {"type": "auth_response", "success": true/false}
    """
    logger.info("web_listen_handler")
    try:
        await websocket.accept()
    except RuntimeError as e:
        logger.error(f"web_listen_handler: accept error {e}")
        return

    # Wait for auth message with timeout
    try:
        first_message = await asyncio.wait_for(websocket.receive(), timeout=5.0)
    except asyncio.TimeoutError:
        await websocket.close(code=1008, reason="Auth timeout")
        return
    except WebSocketDisconnect:
        return

    # Authenticate via first message
    try:
        uid = auth.get_current_user_uid_from_ws_message(cast(Dict[str, Any], first_message))
    except ValueError as e:
        await websocket.close(code=1008, reason=str(e))
        return
    except InvalidIdTokenError:
        await websocket.send_json({"type": "auth_response", "success": False})
        await websocket.close(code=1008, reason="Invalid token")
        return
    except Exception as e:
        logger.error(f"web_listen_handler: auth error {e}")
        await websocket.send_json({"type": "auth_response", "success": False})
        await websocket.close(code=1008, reason="Auth error")
        return

    client_device_context = resolve_client_device_from_websocket_auth_message(first_message)

    # Send success response
    await websocket.send_json({"type": "auth_response", "success": True})
    logger.info(f"web_listen_handler authenticated {uid}")

    # Proceed with streaming (websocket already accepted, uid already validated)
    custom_stt_mode = CustomSttMode.enabled if custom_stt == 'enabled' else CustomSttMode.disabled
    onboarding_mode = onboarding == 'enabled'

    await _stream_handler(
        websocket,
        uid,
        language,
        sample_rate,
        codec,
        channels,
        include_speech_profile,
        None,
        conversation_timeout=conversation_timeout,
        source=source,
        custom_stt_mode=custom_stt_mode,
        onboarding_mode=onboarding_mode,
        call_id=call_id,
        client_conversation_id=client_conversation_id,
        client_device_context=client_device_context,
    )
    logger.info(f"web_listen_handler ended {uid}")

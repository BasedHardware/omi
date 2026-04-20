import asyncio
import hashlib
import io
import json
import logging
import os
import random
import struct
import time
import uuid
import wave
from collections import deque, OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

import av
import numpy as np
import opuslib  # type: ignore

import lc3  # lc3py

from fastapi import APIRouter, Depends
from fastapi.websockets import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
from websockets.exceptions import ConnectionClosed

from firebase_admin.auth import InvalidIdTokenError

from utils.speaker_assignment import (
    process_speaker_assigned_segments,
    update_speaker_assignment_maps,
    should_update_speaker_to_person_map,
)
import database.conversations as conversations_db
import database.calendar_meetings as calendar_db
import database.users as user_db
from utils.byok import get_byok_keys, extract_byok_from_websocket, set_byok_keys, validate_byok_websocket
from database.users import get_user_transcription_preferences
from database import redis_db
from database.redis_db import check_credits_invalidation
from models.conversation import Conversation
from models.conversation_enums import ConversationSource, ConversationStatus
from utils.conversations.factory import deserialize_conversation
from models.conversation_photo import ConversationPhoto
from models.structured import Structured
from models.transcript_segment import TranscriptSegment
from models.message_event import (
    ConversationEvent,
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
from utils.analytics import record_usage
from utils.app_integrations import trigger_realtime_integrations
from utils.apps import is_audio_bytes_app_enabled
from utils.conversations.process_conversation import retrieve_in_progress_conversation
from utils.notifications import send_credit_limit_notification, send_silent_user_notification
from utils.other import endpoints as auth
from utils.other.storage import get_profile_audio_if_exists, get_user_has_speech_profile
from utils.pusher import connect_to_trigger_pusher, PusherCircuitBreakerOpen, get_circuit_breaker, CircuitState
from utils.speaker_identification import detect_speaker_from_text
from utils.stt.streaming import (
    STTService,
    get_stt_service_for_language,
    process_audio_dg,
)
from utils.stt.vad_gate import VADStreamingGate, VAD_GATE_MODE, is_gate_enabled
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
from utils.subscription import has_transcription_credits, get_remaining_transcription_seconds
from utils.translation import TranslationService
from utils.translation_cache import (
    TranscriptSegmentLanguageCache,
    ConversationLanguageState,
    should_persist_translation,
)
from utils.translation_coordinator import TranslationCoordinator
from utils.webhooks import get_audio_bytes_webhook_seconds
from utils.onboarding import OnboardingHandler

from utils.aac import AACDecoder
from utils.audio import AudioRingBuffer
from utils.metrics import (
    BACKEND_LISTEN_ACTIVE_WS_CONNECTIONS,
    PUSHER_CIRCUIT_BREAKER_REJECTIONS,
    PUSHER_CIRCUIT_BREAKER_STATE,
    PUSHER_SESSION_DEGRADED,
)
from utils.stt.speaker_embedding import (
    extract_embedding_from_bytes,
    compare_embeddings,
    SPEAKER_MATCH_THRESHOLD,
)
from utils.speaker_sample_migration import maybe_migrate_person_samples
from utils.log_sanitizer import sanitize, sanitize_pii

logger = logging.getLogger(__name__)

router = APIRouter()


PUSHER_ENABLED = bool(os.getenv('HOSTED_PUSHER_API_URL'))

# Freemium: Send notification when credits threshold is reached
FREEMIUM_THRESHOLD_SECONDS = 180  # 3 minutes remaining - notify user

TARGET_SAMPLE_RATE = 16000


# Per-session pusher reconnect state machine
class PusherReconnectState(str, Enum):
    CONNECTED = 'connected'
    RECONNECT_BACKOFF = 'reconnect_backoff'
    DEGRADED = 'degraded'
    HALF_OPEN_PROBE = 'half_open_probe'


PUSHER_MAX_RECONNECT_ATTEMPTS = 6
PUSHER_DEGRADED_COOLDOWN = 60.0  # seconds before probing from DEGRADED
PUSHER_RECONNECT_BASE_DELAY = 1.0  # seconds
PUSHER_RECONNECT_MAX_DELAY = 60.0  # seconds


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
    mixed = []
    for i in range(num_samples):
        s = sum(ch[i] for ch in channel_samples)
        mixed.append(max(-32768, min(32767, s)))
    return struct.pack(f'<{num_samples}h', *mixed)


def resample_pcm(pcm_data: bytes, source_rate: int, target_rate: int) -> bytes:
    """Simple resampling by sample duplication/decimation."""
    if source_rate == target_rate:
        return pcm_data
    num_samples = len(pcm_data) // 2
    if num_samples == 0:
        return pcm_data
    samples = struct.unpack(f'<{num_samples}h', pcm_data)
    ratio = target_rate / source_rate
    new_length = int(num_samples * ratio)
    resampled = []
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
    vad_gate_override: Optional[str] = None,
    call_id: Optional[str] = None,
):
    """
    Core WebSocket streaming handler. Assumes websocket is already accepted and uid is validated.
    This function is called by both _listen (for app clients) and web_listen_handler (for web clients).
    """
    session_id = str(uuid.uuid4())
    BACKEND_LISTEN_ACTIVE_WS_CONNECTIONS.inc()
    logger.info(
        f'_stream_handler {uid} {session_id} {language} {sample_rate} {codec} {include_speech_profile} {stt_service} {conversation_timeout} custom_stt={custom_stt_mode} onboarding={onboarding_mode}'
    )

    # BaseHTTPMiddleware skips WebSocket scope, so extract BYOK headers manually.
    # This ensures Deepgram streaming and pusher-forwarded LLM calls use the
    # user's own keys when set.
    byok_ws_keys = extract_byok_from_websocket(websocket)
    if byok_ws_keys:
        set_byok_keys(byok_ws_keys)

    # Validate BYOK keys against Firestore enrollment.
    # BYOK-active users MUST send keys matching their enrolled fingerprints.
    # Non-BYOK users' headers are silently cleared.
    byok_error = validate_byok_websocket(uid)
    if byok_error:
        logger.warning(f'_stream_handler BYOK validation failed {uid}: {byok_error}')
        await websocket.send_json({'error': byok_error})
        await websocket.close(code=4003)
        BACKEND_LISTEN_ACTIVE_WS_CONNECTIONS.dec()
        return

    use_custom_stt = custom_stt_mode == CustomSttMode.enabled
    is_multi_channel = channels >= 2

    # Multi-channel state (only allocated when channels >= 2)
    channel_configs: List[ChannelConfig] = []
    channel_id_to_index: Dict[int, int] = {}
    stt_sockets_multi: list = []
    multi_opus_decoders: list = []
    channel_mix_buffers: List[bytearray] = []
    if is_multi_channel:
        channel_configs = build_channel_config(source or 'phone_call')
        channel_id_to_index = {ch.channel_id: i for i, ch in enumerate(channel_configs)}
        stt_sockets_multi = [None] * len(channel_configs)
        if codec == 'opus':
            multi_opus_decoders = [opuslib.Decoder(sample_rate, 1) for _ in channel_configs]
        else:
            multi_opus_decoders = [None] * len(channel_configs)
        channel_mix_buffers = [bytearray() for _ in channel_configs]
        # Multi-channel doesn't use speech profiles or onboarding
        include_speech_profile = False

    # Helper to gate person_id based on client capability (backward compatibility)
    # OLD apps don't send speaker_auto_assign param -> receive empty person_id
    # NEW apps send speaker_auto_assign=enabled -> receive populated person_id
    def _person_id_for_client(person_id: str) -> str:
        if speaker_auto_assign_enabled:
            return person_id
        return ""

    # Onboarding mode overrides: no speech profile (creating new one), single language
    if onboarding_mode:
        include_speech_profile = False

    if not uid or len(uid) <= 0:
        await websocket.close(code=1008, reason="Bad uid")
        return

    user_has_credits = True if use_custom_stt else has_transcription_credits(uid)
    if not user_has_credits:
        try:
            await send_credit_limit_notification(uid)
        except Exception as e:
            logger.error(f"Error sending credit limit notification: {e} {uid} {session_id}")

    # Frame size, codec
    frame_size: int = 160
    lc3_chunk_size: Optional[int] = None
    lc3_frame_duration_us: Optional[int] = None

    if codec == "opus_fs320":
        codec = "opus"
        frame_size = 320
    elif codec == "lc3_fs1030":
        codec = "lc3"
        lc3_chunk_size = 30  # 30 bytes per frame
        lc3_frame_duration_us = 10000  # 10ms = 10000 microseconds

    # Fetch user transcription preferences
    transcription_prefs = get_user_transcription_preferences(uid)
    single_language_mode = transcription_prefs.get('single_language_mode', False)
    vocabulary = transcription_prefs.get('vocabulary', [])

    # Onboarding mode: force single language for better accuracy
    if onboarding_mode:
        single_language_mode = True

    # Always include "Omi" as predefined vocabulary
    vocabulary = list({"Omi"} | set(vocabulary))

    # Convert 'auto' to 'multi' for consistency
    language = 'multi' if language == 'auto' else language

    # Determine the best STT service
    stt_service, stt_language, stt_model = get_stt_service_for_language(
        language, multi_lang_enabled=not single_language_mode
    )
    if not stt_service or not stt_language:
        await websocket.close(code=1008, reason=f"The language is not supported, {language}")
        return

    # Translation language (disabled in single language mode)
    translation_language = None
    if single_language_mode:
        translation_language = None
    elif stt_language == 'multi':
        if language == "multi":
            user_language_preference = user_db.get_user_language_preference(uid)
            if user_language_preference:
                translation_language = user_language_preference
        else:
            translation_language = language

    websocket_active = True
    websocket_close_code = 1001  # Going Away, don't close with good from backend

    # Buffer size limits to prevent memory leaks during outages/lag
    MAX_SEGMENT_BUFFER_SIZE = 1000  # Max segments to buffer
    MAX_PHOTO_BUFFER_SIZE = 100  # Max photos to buffer
    MAX_AUDIO_BUFFER_SIZE = 1024 * 1024 * 10  # 10MB max audio buffer
    MAX_PENDING_REQUESTS = 100  # Max pending conversation requests
    MAX_IMAGE_CHUNKS = 50  # Max concurrent image uploads
    IMAGE_CHUNK_TTL = 60.0  # Seconds before incomplete image chunks expire
    IMAGE_CHUNK_CLEANUP_INTERVAL = 2.0  # Seconds between cleanup scans
    IMAGE_CHUNK_CLEANUP_MIN_SIZE = 5  # Skip scans for tiny caches unless oldest can expire

    # Initialize segment buffers early (before onboarding handler needs them)
    realtime_segment_buffers: deque = deque(maxlen=MAX_SEGMENT_BUFFER_SIZE)
    realtime_photo_buffers: deque[ConversationPhoto] = deque(maxlen=MAX_PHOTO_BUFFER_SIZE)

    # === Speaker Identification State ===
    RING_BUFFER_DURATION = 60.0  # seconds
    SPEAKER_ID_MIN_AUDIO = 2.0
    SPEAKER_ID_TARGET_AUDIO = 4.0

    audio_ring_buffer: Optional[AudioRingBuffer] = None
    speaker_id_segment_queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=100)
    person_embeddings_cache: Dict[str, dict] = {}  # person_id -> {embedding, name}
    speaker_id_enabled = False  # Will be set after private_cloud_sync_enabled is known
    speaker_id_done = asyncio.Event()  # Set when speaker_identification_task finishes
    speaker_map_dirty = False  # Set when a new match is added; triggers one-time full-segment pass

    # Track background tasks to cancel on cleanup (prevents memory leaks from fire-and-forget tasks)
    bg_tasks: Set[asyncio.Task] = set()
    # Dedicated set for speaker match tasks so the final pass can drain them independently
    speaker_match_tasks: Set[asyncio.Task] = set()

    def spawn(coro) -> asyncio.Task:
        """Create a tracked background task that will be cancelled on cleanup."""
        task = asyncio.create_task(coro)
        bg_tasks.add(task)

        def on_done(t):
            bg_tasks.discard(t)
            if t.cancelled():
                return
            exc = t.exception()
            if exc:
                logger.error(f"Unhandled exception in background task: {exc} {uid} {session_id}")

        task.add_done_callback(on_done)
        return task

    # Onboarding handler
    onboarding_handler: Optional[OnboardingHandler] = None
    if onboarding_mode:

        async def send_onboarding_event(event: dict):
            if websocket_active and websocket.client_state == WebSocketState.CONNECTED:
                try:
                    await websocket.send_json(event)
                except Exception as e:
                    logger.error(f"Error sending onboarding event: {e} {uid} {session_id}")

        def onboarding_stream_transcript(segments: List[dict]):
            """Inject onboarding question segments into the transcript stream."""
            nonlocal realtime_segment_buffers
            realtime_segment_buffers.extend(segments)

        onboarding_handler = OnboardingHandler(uid, send_onboarding_event, onboarding_stream_transcript)
        spawn(onboarding_handler.send_current_question())

    locked_conversation_ids: Set[str] = set()
    speaker_to_person_map: Dict[int, Tuple[str, str]] = {}
    segment_person_assignment_map: Dict[str, str] = {}
    current_session_segments: Dict[str, bool] = {}  # Store only speech_profile_processed status
    suggested_segments: Set[str] = set()
    first_audio_byte_timestamp: Optional[float] = None
    last_usage_record_timestamp: Optional[float] = None
    words_transcribed_since_last_record: int = 0
    last_transcript_time: Optional[float] = None
    current_conversation_id = None

    freemium_threshold_sent = False  # Track if we've sent the freemium threshold notification

    # Credit cache: avoid querying ~720 Firestore docs every 60s per stream (#5439 sub-task 1)
    CREDITS_REFRESH_SECONDS = 900  # 15 min
    remaining_seconds_cache: Optional[int] = None  # None = not yet fetched (distinct from unlimited)
    remaining_seconds_cache_ts: float = 0.0
    remaining_seconds_cache_initialized = False

    # Fair-use state (#5746)
    fair_use_last_check_ts: float = 0.0
    # DG budget gate — checked at session start + per cap-check interval
    # Covers restrict-stage users (#5746) and free-exhausted users (#6083)
    fair_use_dg_budget_exhausted: bool = False
    # Track DG usage only for restrict-stage users (not all users)
    fair_use_track_dg_usage: bool = False
    # DG usage accumulator: batch Redis writes every 60s instead of per-chunk (#5854)
    dg_usage_ms_pending: int = 0

    # Session-start: check DG budget for restrict-stage users (#6083)
    if FAIR_USE_ENABLED:
        try:
            _init_stage = get_enforcement_stage(uid)
            logger.info(f'fair_use: session start uid={uid} session={session_id} stage={_init_stage}')
            if _init_stage == 'restrict' and FAIR_USE_RESTRICT_DAILY_DG_MS > 0:
                fair_use_track_dg_usage = True
                fair_use_dg_budget_exhausted = is_dg_budget_exhausted(uid)
                if fair_use_dg_budget_exhausted:
                    logger.info(f'fair_use: DG budget already exhausted at session start for {uid}')
        except Exception as e:
            logger.error(f'fair_use: session-start budget check error for {uid}: {e}')

    async def _record_usage_periodically():
        nonlocal websocket_active, last_usage_record_timestamp, words_transcribed_since_last_record
        nonlocal last_audio_received_time, last_transcript_time, user_has_credits
        nonlocal freemium_threshold_sent
        nonlocal remaining_seconds_cache, remaining_seconds_cache_ts, remaining_seconds_cache_initialized
        nonlocal fair_use_last_check_ts, fair_use_dg_budget_exhausted, fair_use_track_dg_usage
        nonlocal dg_usage_ms_pending

        while websocket_active:
            await asyncio.sleep(60)
            if not websocket_active:
                break

            # Flush batched DG usage to Redis (#5854 — was per-chunk, now every 60s)
            # Placed before use_custom_stt guard so all STT paths get flushed
            if fair_use_track_dg_usage and dg_usage_ms_pending > 0:
                record_dg_usage_ms(uid, dg_usage_ms_pending)
                dg_usage_ms_pending = 0

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

            if last_usage_record_timestamp:
                current_time = time.time()
                transcription_seconds = int(current_time - last_usage_record_timestamp)

                words_to_record = words_transcribed_since_last_record
                words_transcribed_since_last_record = 0  # reset

                if transcription_seconds > 0 or words_to_record > 0 or speech_seconds_delta > 0:
                    record_usage(
                        uid,
                        transcription_seconds=transcription_seconds,
                        words_transcribed=words_to_record,
                        speech_seconds=speech_seconds_delta,
                    )
                last_usage_record_timestamp = current_time

            # Fair-use soft cap check (every FAIR_USE_CHECK_INTERVAL_SECONDS) (#5746)
            # Track + detect + classify + set stage + notify. No service degradation.
            now_ts = time.time()
            if FAIR_USE_ENABLED and now_ts - fair_use_last_check_ts >= FAIR_USE_CHECK_INTERVAL_SECONDS:
                fair_use_last_check_ts = now_ts
                try:
                    speech_totals = get_rolling_speech_ms(uid)
                    triggered_caps = check_soft_caps(uid, speech_totals=speech_totals)
                    if triggered_caps:
                        logger.info(
                            f'fair_use: soft cap triggered for {uid} session={session_id} caps={triggered_caps}'
                        )
                        asyncio.create_task(trigger_classifier_if_needed(uid, triggered_caps, session_id))
                        # Start DG tracking proactively — classifier may escalate to restrict
                        # before next poll. Harmless if user isn't actually escalated.
                        if FAIR_USE_RESTRICT_DAILY_DG_MS > 0:
                            fair_use_track_dg_usage = True
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
                        fair_use_track_dg_usage = True
                        was_exhausted = fair_use_dg_budget_exhausted
                        fair_use_dg_budget_exhausted = is_dg_budget_exhausted(uid)
                        if fair_use_dg_budget_exhausted and not was_exhausted:
                            logger.info(f'fair_use: DG budget exhausted for {uid} session={session_id}')
                    else:
                        fair_use_track_dg_usage = False
                        fair_use_dg_budget_exhausted = False
                except Exception as e:
                    logger.error(f'fair_use: DG budget check error for {uid}: {e}')

            # Freemium: Check remaining credits with local cache (#5439)
            # Refresh from Firestore only every CREDITS_REFRESH_SECONDS; decrement locally between refreshes
            # Active invalidation: subscription changes set a Redis signal (#5446)
            now = time.time()
            credits_invalidated = check_credits_invalidation(uid)
            needs_refresh = (
                not remaining_seconds_cache_initialized
                or credits_invalidated
                or now - remaining_seconds_cache_ts >= CREDITS_REFRESH_SECONDS
                # Fast-refresh when credits exhausted (user may upgrade or month may roll over)
                or (
                    remaining_seconds_cache is not None
                    and remaining_seconds_cache <= 0
                    and now - remaining_seconds_cache_ts >= 60
                )
            )
            if needs_refresh:
                remaining_seconds_cache = get_remaining_transcription_seconds(uid)
                remaining_seconds_cache_ts = now
                remaining_seconds_cache_initialized = True
            elif remaining_seconds_cache is not None and transcription_seconds > 0:
                # Decrement locally between refreshes (None = unlimited, don't decrement)
                remaining_seconds_cache = max(0, remaining_seconds_cache - transcription_seconds)

            remaining_seconds = remaining_seconds_cache

            # Notify user when approaching limit (3 minutes remaining)
            if (
                remaining_seconds is not None
                and remaining_seconds <= FREEMIUM_THRESHOLD_SECONDS
                and not freemium_threshold_sent
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
                freemium_threshold_sent = True

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
                    freemium_threshold_sent = False

            # Silence notification logic for basic plan users
            user_subscription = user_db.get_user_valid_subscription(uid)
            if not user_subscription or user_subscription.plan == PlanType.basic:
                time_of_last_words = last_transcript_time or first_audio_byte_timestamp
                if (
                    last_audio_received_time
                    and time_of_last_words
                    and (last_audio_received_time - time_of_last_words) > 15 * 60
                ):
                    logger.info(f"User {uid} has been silent for over 15 minutes. Sending notification. {session_id}")
                    try:
                        await send_silent_user_notification(uid)
                    except Exception as e:
                        logger.error(f"Error sending silent user notification: {e} {uid} {session_id}")

    async def _asend_message_event(msg: MessageEvent):
        nonlocal websocket_active
        if not websocket_active:
            return False
        try:
            await websocket.send_json(msg.to_json())
            return True
        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected {uid} {session_id}")
            websocket_active = False
        except Exception as e:
            logger.error(f"Can not send message event, error: {e} {uid} {session_id}")

        return False

    def _send_message_event(msg: MessageEvent):
        nonlocal websocket_active
        if not websocket_active:
            return
        return spawn(_asend_message_event(msg))

    # Heart beat
    started_at = time.time()
    inactivity_timeout_seconds = 90
    last_audio_received_time = None
    last_activity_time = None

    # Send pong every 10s then handle it in the app \
    # since Starlette is not support pong automatically
    async def send_heartbeat():
        logger.debug(f"send_heartbeat {uid} {session_id}")
        nonlocal websocket_active
        nonlocal websocket_close_code
        nonlocal started_at
        nonlocal last_audio_received_time

        try:
            while websocket_active:
                # ping fast
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_text("ping")
                else:
                    break

                # Inactivity timeout
                if last_activity_time and time.time() - last_activity_time > inactivity_timeout_seconds:
                    logger.warning(
                        f"Session timeout due to inactivity ({inactivity_timeout_seconds}s) {uid} {session_id}"
                    )
                    websocket_close_code = 1001
                    websocket_active = False
                    break

                # next
                await asyncio.sleep(10)
        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected {uid} {session_id}")
        except Exception as e:
            logger.error(f'Heartbeat error: {e} {uid} {session_id}')
            websocket_close_code = 1011
        finally:
            websocket_active = False

    # Start heart beat
    heartbeat_task = asyncio.create_task(send_heartbeat())

    _send_message_event(
        MessageServiceStatusEvent(event_type="service_status", status="initiating", status_text="Service Starting")
    )

    # Validate user
    if not user_db.is_exists_user(uid):
        websocket_active = False
        await websocket.close(code=1008, reason="Bad user")
        return

    # Create or get conversation ID early for audio chunk storage
    private_cloud_sync_enabled = user_db.get_user_private_cloud_sync_enabled(uid)

    # Enable speaker identification when user has speech profile or private cloud sync
    has_speech_profile = False
    if not use_custom_stt and not is_multi_channel and include_speech_profile:
        has_speech_profile = get_user_has_speech_profile(uid)
    speaker_id_enabled = not use_custom_stt and (private_cloud_sync_enabled or has_speech_profile)
    if speaker_id_enabled:
        audio_ring_buffer = AudioRingBuffer(RING_BUFFER_DURATION, sample_rate)

    # Conversation timeout (to process the conversation after x seconds of silence)
    # Max: 4h, min 2m
    conversation_creation_timeout = conversation_timeout
    if conversation_creation_timeout == -1 or is_multi_channel:
        conversation_creation_timeout = 4 * 60 * 60  # Max timeout for multi-channel / phone calls
    if conversation_creation_timeout < 120:
        conversation_creation_timeout = 120

    # Stream transcript
    # Callback for when pusher finishes processing a conversation
    def on_conversation_processed(conversation_id: str):
        conversation_data = conversations_db.get_conversation(uid, conversation_id)
        if conversation_data:
            conversation = deserialize_conversation(conversation_data)
            _send_message_event(ConversationEvent(event_type="memory_created", memory=conversation, messages=[]))

    def on_conversation_processing_started(conversation_id: str):
        conversation_data = conversations_db.get_conversation(uid, conversation_id)
        if conversation_data:
            conversation = deserialize_conversation(conversation_data)
            _send_message_event(ConversationEvent(event_type="memory_processing_started", memory=conversation))

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
        nonlocal current_conversation_id

        conversation_source = ConversationSource.omi
        if source:
            try:
                conversation_source = ConversationSource(source)
            except ValueError:
                logger.error(f"Invalid conversation source '{source}', defaulting to 'omi' {uid} {session_id}")
                conversation_source = ConversationSource.omi

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
        )
        conversations_db.upsert_conversation(uid, conversation_data=stub_conversation.dict())
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

        current_conversation_id = new_conversation_id

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
                    return
                # Mark processing + buffer for pusher — never process locally (#6061)
                conversations_db.update_conversation_status(uid, conversation_id, ConversationStatus.processing)
                on_conversation_processing_started(conversation_id)
                await request_conversation_processing(conversation_id)
            else:
                logger.info(f'Clean up the conversation {conversation_id}, reason: no content {uid} {session_id}')
                conversations_db.delete_conversation(uid, conversation_id)

    # Process existing conversations
    async def _prepare_in_progess_conversations():
        nonlocal current_conversation_id

        if existing_conversation := retrieve_in_progress_conversation(uid):
            finished_at = datetime.fromisoformat(existing_conversation['finished_at'].isoformat())
            seconds_since_last_segment = (datetime.now(timezone.utc) - finished_at).total_seconds()
            if seconds_since_last_segment >= conversation_creation_timeout:
                logger.info(
                    f'Processing existing conversation {existing_conversation["id"]} (timed out: {seconds_since_last_segment:.1f}s) {uid} {session_id}'
                )
                await _create_new_in_progress_conversation()
                return existing_conversation["id"]

            # Continue with the existing conversation
            current_conversation_id = existing_conversation['id']
            logger.info(
                f"Resuming conversation {current_conversation_id}. Will timeout in {conversation_creation_timeout - seconds_since_last_segment:.1f}s {uid} {session_id}"
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
        nonlocal speaker_map_dirty
        updated_segments: List[TranscriptSegment] = []
        removed_ids: List[str] = []

        if segments:
            conversation.transcript_segments, updated_segments, removed_ids = TranscriptSegment.combine_segments(
                conversation.transcript_segments, segments
            )
            if speaker_map_dirty:
                # A new speaker match was found — retroactively fix all earlier segments once
                process_speaker_assigned_segments(
                    conversation.transcript_segments,
                    segment_person_assignment_map,
                    speaker_to_person_map,
                )
                speaker_map_dirty = False
            else:
                process_speaker_assigned_segments(
                    updated_segments,
                    segment_person_assignment_map,
                    speaker_to_person_map,
                )
            segments_dicts = [segment.dict() for segment in conversation.transcript_segments]
            conversations_db.update_conversation_segments(
                uid, conversation.id, segments_dicts, data_protection_level=_cached_protection_level
            )
            _update_cached_segments(segments_dicts)

        if photos:
            conversations_db.store_conversation_photos(uid, conversation.id, photos)
            # Update source if we now have photos
            if conversation.source != ConversationSource.openglass:
                conversations_db.update_conversation(uid, conversation.id, {'source': ConversationSource.openglass})
                conversation.source = ConversationSource.openglass

        conversations_db.update_conversation_finished_at(uid, conversation.id, finished_at)
        return conversation, updated_segments, removed_ids

    # STT
    # Validate websocket_active before initiating STT
    if not websocket_active or websocket.client_state != WebSocketState.CONNECTED:
        logger.info(f"websocket was closed {uid} {session_id}")
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close(code=websocket_close_code)
            except Exception as e:
                logger.error(f"Error closing WebSocket: {e} {uid} {session_id}")
        return

    # Process STT
    deepgram_socket = None

    vad_gate = None

    def stream_transcript(segments):
        nonlocal realtime_segment_buffers
        # Note: DG timestamp remapping is handled inside GatedDeepgramSocket wrapper
        realtime_segment_buffers.extend(segments)

    async def _process_stt():
        nonlocal websocket_close_code
        nonlocal deepgram_socket
        try:
            if use_custom_stt:
                logger.info(f"Custom STT mode enabled - using suggested transcripts from app {uid} {session_id}")
                return None

            if is_multi_channel:
                # Create one STT connection per channel
                for i, ch_config in enumerate(channel_configs):

                    def make_multi_channel_callback(cfg):
                        def cb(segments):
                            for seg in segments:
                                seg['is_user'] = cfg.is_user
                                seg['speaker'] = cfg.speaker_label
                            realtime_segment_buffers.extend(segments)

                        return cb

                    callback = make_multi_channel_callback(ch_config)
                    stt_sockets_multi[i] = await process_audio_dg(
                        callback,
                        stt_language,
                        TARGET_SAMPLE_RATE,
                        1,
                        model=stt_model,
                    )
                logger.info(
                    f"Multi-channel STT connections established ({len(channel_configs)} channels) {uid} {session_id}"
                )
                return None

            # Initialize VAD gate for all eligible DG sessions.
            # Gate requires PCM16 LE (linear16). All codecs (opus, aac, lc3)
            # decode to int16 before buffering. pcm8/pcm16 are linear16 from hardware
            # (the "8"/"16" refers to sample rate kHz, not bit depth).
            # DG always receives mono (channels=1), so clamp gate channels to 1.
            nonlocal vad_gate
            gate_enabled_by_override = vad_gate_override == 'enabled'
            gate_disabled_by_override = vad_gate_override == 'disabled'
            if not gate_disabled_by_override and (is_gate_enabled() or gate_enabled_by_override):
                gate_mode = 'active' if gate_enabled_by_override else VAD_GATE_MODE
                try:
                    vad_gate = VADStreamingGate(
                        sample_rate=sample_rate,
                        channels=1,  # DG always receives mono (encoding=linear16, channels=1)
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

            deepgram_socket = await process_audio_dg(
                stream_transcript,
                stt_language,
                sample_rate,
                1,
                model=stt_model,
                keywords=vocabulary[:100] if vocabulary else None,
                vad_gate=vad_gate,
                is_active=lambda: websocket_active,
            )
            return None

        except Exception as e:
            logger.error(f"Initial processing error: {e} {uid} {session_id}")
            websocket_close_code = 1011
            await websocket.close(code=websocket_close_code)
            return None

    # Pusher
    #
    def create_pusher_task_handler():
        nonlocal websocket_active
        nonlocal current_conversation_id

        pusher_ws = None
        pusher_connect_lock = asyncio.Lock()
        pusher_connected = False

        # Per-session reconnect state machine
        reconnect_state = PusherReconnectState.CONNECTED
        reconnect_attempts = 0
        reconnect_task = None  # single task per session
        degraded_since: float = 0.0

        # Transcript (bounded to prevent memory growth when pusher is down)
        segment_buffers: deque = deque(maxlen=MAX_SEGMENT_BUFFER_SIZE)

        last_synced_conversation_id = None

        # Conversation processing — maps conversation_id to {sent_at, retries}
        PENDING_REQUEST_TIMEOUT = 120  # seconds before retrying a pending request
        MAX_RETRIES_PER_REQUEST = 3
        pending_conversation_requests: Dict[str, dict] = {}
        pending_request_event = asyncio.Event()

        def transcript_send(segments):
            nonlocal segment_buffers
            segment_buffers.extend(segments)

        async def request_conversation_processing(conversation_id: str):
            """Request pusher to process a conversation."""
            nonlocal pusher_ws, pusher_connected, pending_conversation_requests, pending_request_event
            if not pusher_connected or not pusher_ws:
                logger.info(f"Pusher not connected for {conversation_id}, will retry on reconnect {uid} {session_id}")
                # Track as pending so it gets retried on reconnect
                if conversation_id not in pending_conversation_requests:
                    pending_conversation_requests[conversation_id] = {'sent_at': time.time(), 'retries': 0}
                    pending_request_event.set()
                return False
            # Prevent unbounded growth of pending requests
            if len(pending_conversation_requests) >= MAX_PENDING_REQUESTS:
                oldest_id = min(
                    pending_conversation_requests, key=lambda k: pending_conversation_requests[k]['sent_at']
                )
                logger.info(
                    f"Too many pending requests, dropping {oldest_id} to add {conversation_id} {uid} {session_id}"
                )
                del pending_conversation_requests[oldest_id]
            try:
                pending_conversation_requests[conversation_id] = {
                    'sent_at': time.time(),
                    'retries': pending_conversation_requests.get(conversation_id, {}).get('retries', 0),
                }
                pending_request_event.set()  # Signal the receiver
                data = bytearray()
                data.extend(struct.pack("I", 104))
                # Forward BYOK keys to pusher so process_conversation routes LLM
                # calls through the user's keys. Empty dict when user isn't BYOK
                # — pusher then uses its env keys (unchanged behavior).
                payload = {
                    "conversation_id": conversation_id,
                    "language": language,
                    "byok_keys": get_byok_keys(),
                }
                data.extend(bytes(json.dumps(payload), "utf-8"))
                await pusher_ws.send(data)
                logger.info(f"Sent process_conversation request to pusher: {conversation_id} {uid} {session_id}")
                return True
            except Exception as e:
                logger.error(f"Failed to send process_conversation request: {e} {uid} {session_id}")
                return False

        async def _transcript_flush(auto_reconnect: bool = True):
            nonlocal pusher_ws
            nonlocal pusher_connected
            if pusher_connected and pusher_ws and len(segment_buffers) > 0:
                try:
                    # 102|data
                    data = bytearray()
                    data.extend(struct.pack("I", 102))
                    data.extend(
                        bytes(
                            json.dumps({"segments": list(segment_buffers), "memory_id": current_conversation_id}),
                            "utf-8",
                        )
                    )
                    segment_buffers.clear()  # reset
                    await pusher_ws.send(data)
                except ConnectionClosed as e:
                    logger.error(f"Pusher transcripts Connection closed: {e} {uid} {session_id}")
                    _mark_disconnected()
                except Exception as e:
                    logger.error(f"Pusher transcripts failed: {e} {uid} {session_id}")

        async def transcript_consume():
            nonlocal websocket_active
            while websocket_active:
                await asyncio.sleep(1)
                if len(segment_buffers) > 0:
                    await _transcript_flush(auto_reconnect=True)

        # Audio bytes (bounded to prevent memory growth when pusher is down)
        # Using deque of chunks for O(1) trimming instead of O(n) bytearray slice
        audio_chunks: deque = deque()  # deque of bytes objects
        audio_total_size = 0  # Track total size for O(1) limit check
        audio_buffer_last_received: float = None  # Track when last audio was received
        audio_bytes_enabled = (
            bool(get_audio_bytes_webhook_seconds(uid)) or is_audio_bytes_app_enabled(uid) or private_cloud_sync_enabled
        )

        def audio_bytes_send(audio_bytes: bytes, received_at: float):
            nonlocal audio_chunks, audio_total_size, audio_buffer_last_received
            chunk = audio_bytes
            # Trim oversized incoming chunk
            if len(chunk) > MAX_AUDIO_BUFFER_SIZE:
                chunk = chunk[-MAX_AUDIO_BUFFER_SIZE:]
            # Drop oldest chunks to make room - O(1) per chunk
            while audio_total_size + len(chunk) > MAX_AUDIO_BUFFER_SIZE and audio_chunks:
                old = audio_chunks.popleft()
                audio_total_size -= len(old)
            audio_chunks.append(chunk)
            audio_total_size += len(chunk)
            audio_buffer_last_received = received_at

        async def _audio_bytes_flush(auto_reconnect: bool = True):
            nonlocal audio_chunks, audio_total_size
            nonlocal audio_buffer_last_received
            nonlocal pusher_ws
            nonlocal pusher_connected
            nonlocal last_synced_conversation_id

            # Send conversation ID
            if (
                pusher_ws
                and current_conversation_id
                and (last_synced_conversation_id is None or current_conversation_id != last_synced_conversation_id)
            ):
                try:
                    # 103|conversation_id
                    data = bytearray()
                    data.extend(struct.pack("I", 103))
                    data.extend(bytes(current_conversation_id, "utf-8"))
                    await pusher_ws.send(data)
                    last_synced_conversation_id = current_conversation_id
                except ConnectionClosed as e:
                    logger.error(f"Pusher audio_bytes Connection closed: {e} {uid} {session_id}")
                    _mark_disconnected()
                except Exception as e:
                    logger.error(f"Failed to send conversation_id to pusher: {e} {uid} {session_id}")

            # Send audio bytes
            if pusher_connected and pusher_ws and audio_total_size > 0:
                try:
                    # Calculate buffer start time:
                    # buffer_start = last_received_time - buffer_duration
                    # buffer_duration = buffer_length_bytes / (rate * 2 bytes per sample)
                    # Multi-channel audio is resampled to TARGET_SAMPLE_RATE before reaching the pusher
                    effective_rate = TARGET_SAMPLE_RATE if is_multi_channel else sample_rate
                    buffer_duration_seconds = audio_total_size / (effective_rate * 2)
                    buffer_start_time = (audio_buffer_last_received or time.time()) - buffer_duration_seconds

                    # Join chunks into contiguous bytes for sending
                    audio_data = b''.join(audio_chunks)

                    # 101|timestamp(8 bytes double)|audio_data
                    data = bytearray()
                    data.extend(struct.pack("I", 101))
                    data.extend(struct.pack("d", buffer_start_time))
                    data.extend(audio_data)
                    # Reset buffer
                    audio_chunks.clear()
                    audio_total_size = 0
                    del audio_data  # Free immediately
                    await pusher_ws.send(data)
                except ConnectionClosed as e:
                    logger.error(f"Pusher audio_bytes Connection closed: {e} {uid} {session_id}")
                    _mark_disconnected()
                except Exception as e:
                    logger.error(f"Pusher audio_bytes failed: {e} {uid} {session_id}")

        async def audio_bytes_consume():
            nonlocal websocket_active
            nonlocal audio_chunks, audio_total_size
            nonlocal pusher_ws
            nonlocal pusher_connected
            while websocket_active:
                await asyncio.sleep(1)
                if audio_total_size > 0:
                    await _audio_bytes_flush(auto_reconnect=True)

        async def pusher_receive():
            """Receive and handle messages from pusher, with timeout-based retry for pending requests."""
            nonlocal websocket_active, pusher_ws, pusher_connected, pending_conversation_requests, pending_request_event
            while websocket_active:
                # Wait efficiently until there's work to do
                if not pending_conversation_requests:
                    pending_request_event.clear()
                    try:
                        await asyncio.wait_for(pending_request_event.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        continue  # Check websocket_active

                if not pusher_connected or not pusher_ws:
                    await asyncio.sleep(0.5)
                    continue

                try:
                    msg = await asyncio.wait_for(pusher_ws.recv(), timeout=5.0)
                    if not msg or len(msg) < 4:
                        continue
                    header_type = struct.unpack('<I', msg[:4])[0]

                    # Conversation processed response
                    if header_type == 201:
                        result = json.loads(msg[4:].decode("utf-8"))
                        conversation_id = result.get("conversation_id")
                        pending_conversation_requests.pop(conversation_id, None)

                        if "error" in result:
                            logger.error(f"Conversation processing failed: {result['error']} {uid} {session_id}")
                            continue

                        if result.get("success"):
                            logger.info(f"Conversation processed by pusher: {conversation_id} {uid} {session_id}")
                            on_conversation_processed(conversation_id)

                except asyncio.TimeoutError:
                    pass  # Fall through to retry check below
                except asyncio.CancelledError:
                    break
                except ConnectionClosed as e:
                    logger.error(f"Pusher receive connection closed: {e} {uid} {session_id}")
                    _mark_disconnected()
                except Exception as e:
                    logger.error(f"Pusher receive error: {e} {uid} {session_id}")
                    await asyncio.sleep(0.5)

                # Retry timed-out pending requests (handles silent WS death)
                now = time.time()
                timed_out = [
                    cid
                    for cid, info in list(pending_conversation_requests.items())
                    if now - info['sent_at'] > PENDING_REQUEST_TIMEOUT
                ]
                for cid in timed_out:
                    info = pending_conversation_requests.get(cid)
                    if not info:
                        continue
                    if info['retries'] >= MAX_RETRIES_PER_REQUEST:
                        logger.warning(
                            f"Conversation {cid} retry limit reached, keeping buffered for pusher recovery {uid} {session_id}"
                        )
                        # Don't drop — conversation is marked processing in Firestore,
                        # cleanup_processing_conversations() will pick it up on next session (#6061)
                        info['sent_at'] = now  # Reset timeout to avoid tight retry loop
                        continue
                    info['retries'] += 1
                    logger.warning(
                        f"Retrying process_conversation for {cid} (attempt {info['retries']}/{MAX_RETRIES_PER_REQUEST}) {uid} {session_id}"
                    )
                    await request_conversation_processing(cid)

        async def _flush():
            await _audio_bytes_flush(auto_reconnect=False)
            await _transcript_flush(auto_reconnect=False)

        def _mark_disconnected():
            """Signal pusher disconnection — sets state and ensures reconnect loop is running."""
            nonlocal pusher_connected, reconnect_state, reconnect_task
            if not pusher_connected:
                return  # already marked
            pusher_connected = False
            if reconnect_state == PusherReconnectState.CONNECTED:
                reconnect_state = PusherReconnectState.RECONNECT_BACKOFF
                logger.info(f"Pusher disconnected, entering RECONNECT_BACKOFF {uid} {session_id}")
            # Ensure reconnect loop is running (single task per session)
            if reconnect_task is None or reconnect_task.done():
                reconnect_task = asyncio.create_task(_pusher_reconnect_loop())

        async def _pusher_reconnect_loop():
            """Single reconnect loop per session — replaces 3 scattered auto-reconnect calls.

            State machine:
            RECONNECT_BACKOFF → (6 failures) → DEGRADED → (60s) → HALF_OPEN_PROBE → success → CONNECTED
                                                                                   → failure → DEGRADED
            """
            nonlocal reconnect_state, reconnect_attempts, degraded_since, pusher_connected
            logger.info(f"Pusher reconnect loop started {uid} {session_id}")
            PUSHER_SESSION_DEGRADED.inc()
            try:
                while websocket_active and not pusher_connected:
                    if reconnect_state == PusherReconnectState.RECONNECT_BACKOFF:
                        if reconnect_attempts >= PUSHER_MAX_RECONNECT_ATTEMPTS:
                            reconnect_state = PusherReconnectState.DEGRADED
                            degraded_since = time.monotonic()
                            reconnect_attempts = 0
                            logger.warning(
                                f"Pusher reconnect exhausted ({PUSHER_MAX_RECONNECT_ATTEMPTS} attempts), "
                                f"entering DEGRADED mode {uid} {session_id}"
                            )
                            # Keep pending conversations buffered — will resend when pusher recovers (#6061)
                            if pending_conversation_requests:
                                logger.info(
                                    f"Keeping {len(pending_conversation_requests)} conversations buffered for pusher recovery {uid} {session_id}"
                                )
                            continue

                        # Exponential backoff: 1s, 2s, 4s, 8s, 16s, 32s (capped at 60s)
                        delay = min(
                            PUSHER_RECONNECT_BASE_DELAY * (2**reconnect_attempts),
                            PUSHER_RECONNECT_MAX_DELAY,
                        )
                        # Add jitter (±25%)
                        delay *= 0.75 + random.random() * 0.5
                        logger.info(
                            f"Pusher reconnect attempt {reconnect_attempts + 1}/{PUSHER_MAX_RECONNECT_ATTEMPTS}, "
                            f"waiting {delay:.1f}s {uid} {session_id}"
                        )
                        await asyncio.sleep(delay)
                        if not websocket_active:
                            break

                        try:
                            await connect()
                            if pusher_connected:
                                reconnect_state = PusherReconnectState.CONNECTED
                                reconnect_attempts = 0
                                logger.info(f"Pusher reconnected successfully {uid} {session_id}")
                                break
                        except PusherCircuitBreakerOpen:
                            PUSHER_CIRCUIT_BREAKER_REJECTIONS.inc()
                            # Circuit breaker is open — skip to degraded immediately
                            reconnect_state = PusherReconnectState.DEGRADED
                            degraded_since = time.monotonic()
                            reconnect_attempts = 0
                            logger.warning(f"Circuit breaker open, skipping to DEGRADED {uid} {session_id}")
                            # Keep pending conversations buffered — will resend when pusher recovers (#6061)
                            continue
                        except Exception:
                            pass  # _connect already logged the error

                        reconnect_attempts += 1

                    elif reconnect_state == PusherReconnectState.DEGRADED:
                        # Wait for cooldown before probing
                        elapsed = time.monotonic() - degraded_since
                        remaining = PUSHER_DEGRADED_COOLDOWN - elapsed
                        if remaining > 0:
                            await asyncio.sleep(min(remaining, 5.0))
                            continue
                        # Cooldown elapsed — try a single probe
                        reconnect_state = PusherReconnectState.HALF_OPEN_PROBE
                        logger.info(f"Pusher DEGRADED cooldown elapsed, probing {uid} {session_id}")

                    elif reconnect_state == PusherReconnectState.HALF_OPEN_PROBE:
                        try:
                            await connect()
                            if pusher_connected:
                                reconnect_state = PusherReconnectState.CONNECTED
                                reconnect_attempts = 0
                                logger.info(f"Pusher probe succeeded, back to CONNECTED {uid} {session_id}")
                                break
                        except PusherCircuitBreakerOpen:
                            PUSHER_CIRCUIT_BREAKER_REJECTIONS.inc()
                            pass
                        except Exception:
                            pass
                        # Probe failed — back to DEGRADED
                        reconnect_state = PusherReconnectState.DEGRADED
                        degraded_since = time.monotonic()
                        logger.warning(f"Pusher probe failed, back to DEGRADED {uid} {session_id}")

                    else:
                        # Shouldn't happen, but guard against
                        break
            finally:
                PUSHER_SESSION_DEGRADED.dec()
                logger.info(f"Pusher reconnect loop ended (state={reconnect_state.value}) {uid} {session_id}")

        async def connect():
            nonlocal pusher_connected
            nonlocal pusher_connect_lock
            nonlocal pusher_ws
            async with pusher_connect_lock:
                if pusher_connected:
                    return
                # drain
                if pusher_ws:
                    try:
                        await pusher_ws.close()
                        pusher_ws = None
                    except Exception as e:
                        logger.error(f"Pusher draining failed: {e} {uid} {session_id}")
                # connect (PusherCircuitBreakerOpen propagates to caller)
                await _connect()

        async def _connect():
            nonlocal pusher_ws
            nonlocal pusher_connected
            nonlocal current_conversation_id
            nonlocal reconnect_state, reconnect_attempts

            try:
                pusher_sample_rate = TARGET_SAMPLE_RATE if is_multi_channel else sample_rate
                pusher_ws = await connect_to_trigger_pusher(
                    uid, pusher_sample_rate, retries=5, is_active=lambda: websocket_active
                )
                if pusher_ws is None:
                    # Session ended during connection attempt
                    return
                pusher_connected = True
                reconnect_state = PusherReconnectState.CONNECTED
                reconnect_attempts = 0
                # Re-send any pending conversation requests after reconnect
                if pending_conversation_requests:
                    logger.info(
                        f"Reconnected to pusher, re-sending {len(pending_conversation_requests)} pending requests {uid} {session_id}"
                    )
                    for cid in list(pending_conversation_requests.keys()):
                        pending_conversation_requests[cid]['sent_at'] = time.time()
                        await request_conversation_processing(cid)
            except PusherCircuitBreakerOpen:
                raise  # Let caller handle circuit breaker
            except Exception as e:
                logger.error(f"Exception in connect: {e} {uid} {session_id}")

        async def close(code: int = 1000):
            nonlocal reconnect_task
            # Cancel reconnect loop if running
            if reconnect_task and not reconnect_task.done():
                reconnect_task.cancel()
                try:
                    await reconnect_task
                except asyncio.CancelledError:
                    pass
                reconnect_task = None
            await _flush()
            if pusher_ws:
                await pusher_ws.close(code)

        def is_degraded():
            return reconnect_state in (PusherReconnectState.DEGRADED, PusherReconnectState.HALF_OPEN_PROBE)

        async def send_speaker_sample_request(
            person_id: str,
            conv_id: str,
            segment_ids: List[str],
        ):
            """Send speaker sample extraction request to pusher with segment IDs."""
            nonlocal pusher_ws, pusher_connected
            if not pusher_connected or not pusher_ws:
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
                await pusher_ws.send(data)
                logger.info(
                    f"Sent speaker sample request to pusher: person={person_id}, {len(segment_ids)} segments {uid} {session_id}"
                )
            except Exception as e:
                logger.error(f"Failed to send speaker sample request: {e} {uid} {session_id}")

        def is_connected():
            return pusher_connected

        async def pusher_heartbeat():
            """Send periodic data-frame heartbeats to reset the GKE ILB idle timer.

            The GKE Internal Load Balancer counts only data frames for its idle
            timeout (default 30 s). WebSocket control frames (ping/pong) are
            ignored. During user silence most connections carry zero data frames,
            causing the ILB to kill the connection. This task sends a minimal
            4-byte data frame (header type 100) every 20 s to keep the link alive.
            """
            nonlocal pusher_ws, pusher_connected, websocket_active
            while websocket_active:
                await asyncio.sleep(20)
                if pusher_connected and pusher_ws:
                    try:
                        await pusher_ws.send(struct.pack("I", 100))
                    except ConnectionClosed:
                        _mark_disconnected()
                    except Exception as e:
                        logger.error(f"Pusher heartbeat send failed: {e} {uid} {session_id}")

        def start_degraded():
            """Enter degraded mode and start reconnect loop after initial connect failure."""
            nonlocal reconnect_state, reconnect_task, degraded_since
            reconnect_state = PusherReconnectState.DEGRADED
            degraded_since = time.monotonic()
            if reconnect_task is None or reconnect_task.done():
                reconnect_task = asyncio.create_task(_pusher_reconnect_loop())

        return (
            connect,
            close,
            transcript_send,
            transcript_consume,
            audio_bytes_send if audio_bytes_enabled else None,
            audio_bytes_consume if audio_bytes_enabled else None,
            request_conversation_processing,
            pusher_receive,
            is_connected,
            is_degraded,
            start_degraded,
            send_speaker_sample_request,
            pusher_heartbeat,
        )

    transcript_send = None
    transcript_consume = None
    audio_bytes_send = None
    audio_bytes_consume = None
    pusher_close = None
    pusher_connect = None
    request_conversation_processing = None
    pusher_receive = None
    pusher_is_connected = None
    pusher_is_degraded = None
    pusher_start_degraded = None
    send_speaker_sample_request = None
    pusher_heartbeat = None

    # Transcripts
    #
    translation_enabled = translation_language is not None
    language_cache = TranscriptSegmentLanguageCache()
    translation_service = TranslationService()

    # Normalize locale-tagged language (e.g. "en-US" -> "en") for langdetect compatibility
    translation_language_base = translation_language.split('-')[0] if translation_language else None

    # Translation coordinator (issue #6155) — replaces debounce/per-segment state
    translation_persist_lock = asyncio.Lock()
    conversation_language_state = (
        ConversationLanguageState(translation_language or 'en') if translation_enabled else None
    )

    async def _on_translation_ready(segment_id: str, translated_text: str, detected_lang: str, conversation_id: str):
        """Callback from TranslationCoordinator when a translation is ready to persist."""
        if not translation_language:
            return
        if not websocket_active and not (translation_coordinator and translation_coordinator._flushing):
            return

        try:
            trans = Translation(lang=translation_language, text=translated_text)

            # Persist with lock to prevent concurrent read-modify-write clobbering
            async with translation_persist_lock:
                if conversation_id == current_conversation_id:
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
                                translations[existing_idx] = trans.dict()
                            else:
                                translations.append(trans.dict())
                            conversation['transcript_segments'][i]['translations'] = translations
                            conversations_db.update_conversation_segments(
                                uid,
                                conversation_id,
                                conversation['transcript_segments'],
                                data_protection_level=protection_level,
                            )
                            if conversation_id == current_conversation_id:
                                _update_cached_segments(conversation['transcript_segments'])
                            break

            if websocket_active:
                # Build segment dict for the event
                seg_dict = None
                if conversation_id == current_conversation_id:
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

    translation_coordinator = (
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
    pending_translations = {}
    translation_flushing = False

    async def translate(segments: List[TranscriptSegment], conversation_id: str, removed_ids: List[str] = None):
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
        nonlocal websocket_active, current_conversation_id, conversation_creation_timeout

        logger.info(
            f"Starting conversation lifecycle manager (timeout: {conversation_creation_timeout}s) {uid} {session_id}"
        )

        while websocket_active:
            await asyncio.sleep(5)

            if not current_conversation_id:
                logger.warning(f"WARN: the current conversation is not valid {uid} {session_id}")
                continue

            conversation = conversations_db.get_conversation(uid, current_conversation_id)
            if not conversation:
                logger.warning(
                    f"WARN: the current conversation is not found (id: {current_conversation_id}) {uid} {session_id}"
                )
                await _create_new_in_progress_conversation()
                continue

            # Check if conversation status is not in_progress
            if conversation.get('status') != ConversationStatus.in_progress:
                logger.warning(
                    f"WARN: conversation {current_conversation_id} status is {conversation.get('status')}, not in_progress. Creating new conversation. {uid} {session_id}"
                )
                await _create_new_in_progress_conversation()
                continue

            # Check if conversation should be processed
            finished_at = datetime.fromisoformat(conversation['finished_at'].isoformat())
            seconds_since_last_update = (datetime.now(timezone.utc) - finished_at).total_seconds()
            if seconds_since_last_update >= conversation_creation_timeout:
                logger.info(
                    f"Conversation {current_conversation_id} timeout reached ({seconds_since_last_update:.1f}s). Processing... {uid} {session_id}"
                )
                # Drain any in-flight embedding match tasks before flushing
                if speaker_match_tasks:
                    pending = list(speaker_match_tasks)
                    try:
                        await asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True), timeout=5.0)
                    except asyncio.TimeoutError:
                        logger.warning(f"Timeout draining speaker match tasks before rollover {uid} {session_id}")
                _flush_speaker_assignments(current_conversation_id)
                await _process_conversation(current_conversation_id)
                await _create_new_in_progress_conversation()

    # Sentinel person_id for user's own voice — must match speaker_assignment.py's 'user' sentinel
    USER_SELF_PERSON_ID = 'user'

    async def speaker_identification_task():
        """Consume segment queue, accumulate per speaker, trigger match when ready."""
        nonlocal websocket_active, speaker_to_person_map
        nonlocal person_embeddings_cache, audio_ring_buffer

        if not speaker_id_enabled:
            speaker_id_done.set()
            return

        # Load user's own embedding from Firestore (extracted at profile creation time)
        # Fallback: if user has a speech profile but no stored embedding (pre-deployment profiles),
        # extract from the WAV file and store it in Firestore for future sessions.
        if has_speech_profile:
            try:
                embedding_list = await asyncio.to_thread(user_db.get_user_speaker_embedding, uid)
                if embedding_list:
                    user_embedding = np.array(embedding_list, dtype=np.float32).reshape(1, -1)
                    person_embeddings_cache[USER_SELF_PERSON_ID] = {
                        'embedding': user_embedding,
                        'name': 'User',
                    }
                    logger.info(f"Speaker ID: loaded user speaker embedding from Firestore {uid} {session_id}")
                else:
                    logger.info(f"Speaker ID: no stored embedding, extracting from speech profile {uid} {session_id}")
                    file_path = await asyncio.to_thread(get_profile_audio_if_exists, uid)
                    if file_path:
                        with open(file_path, 'rb') as f:
                            profile_bytes = f.read()
                        user_embedding = await asyncio.to_thread(
                            extract_embedding_from_bytes, profile_bytes, "speech_profile.wav"
                        )
                        del profile_bytes
                        person_embeddings_cache[USER_SELF_PERSON_ID] = {
                            'embedding': user_embedding,
                            'name': 'User',
                        }
                        # Store in Firestore so future sessions load directly
                        await asyncio.to_thread(
                            user_db.set_user_speaker_embedding, uid, user_embedding.flatten().tolist()
                        )
                        logger.info(f"Speaker ID: extracted and stored user embedding {uid} {session_id}")
            except Exception as e:
                logger.error(f"Speaker ID: failed to load user embedding: {e} {uid} {session_id}")

        # Load person embeddings (migrate if needed for v2 API compatibility)
        try:
            people = user_db.get_people(uid)
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
            speaker_id_done.set()
            return

        if not person_embeddings_cache:
            logger.info(f"Speaker ID: no stored embeddings, task disabled {uid} {session_id}")
            speaker_id_done.set()
            return

        # Consume loop — keep running until websocket closes AND queue is drained.
        # stream_transcript_process can enqueue segments after websocket_active=False,
        # so we must not exit on the flag alone.
        while True:
            try:
                seg = await asyncio.wait_for(speaker_id_segment_queue.get(), timeout=2.0)
            except asyncio.TimeoutError:
                if not websocket_active:
                    break  # WebSocket closed and no data for 2s — queue is drained
                continue

            speaker_id = seg['speaker_id']

            # Skip if already resolved
            if speaker_id in speaker_to_person_map:
                continue

            duration = seg['duration']
            if duration >= SPEAKER_ID_MIN_AUDIO:
                task = spawn(_match_speaker_embedding(speaker_id, seg))
                speaker_match_tasks.add(task)
                task.add_done_callback(speaker_match_tasks.discard)

        logger.info(f"Speaker ID task ended {uid} {session_id}")
        speaker_id_done.set()

    async def _match_speaker_embedding(speaker_id: int, segment: dict):
        """Extract audio from ring buffer and match against stored embeddings."""
        nonlocal speaker_to_person_map, segment_person_assignment_map, audio_ring_buffer, speaker_map_dirty

        try:
            seg_start = segment['abs_start']
            seg_end = segment['abs_end']
            duration = segment['duration']

            if duration < SPEAKER_ID_MIN_AUDIO:
                logger.info(f"Speaker ID: segment too short ({duration:.1f}s) {uid} {session_id}")
                return

            # Get buffer time range
            time_range = audio_ring_buffer.get_time_range()
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
            pcm_data = audio_ring_buffer.extract(extract_start, extract_end)
            if not pcm_data:
                logger.error(f"Speaker ID: failed to extract audio {uid} {session_id}")
                return

            # Convert PCM to numpy for WAV encoding
            samples = np.frombuffer(pcm_data, dtype=np.int16)

            # Convert PCM to WAV using av
            output_buffer = io.BytesIO()
            output_container = av.open(output_buffer, mode='w', format='wav')
            output_stream = output_container.add_stream('pcm_s16le', rate=sample_rate)
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
            query_embedding = await asyncio.to_thread(extract_embedding_from_bytes, wav_bytes, "query.wav")

            # Find best match
            best_match = None
            best_distance = float('inf')

            # Print all candidates with scores for tuning
            logger.info(
                f"Speaker ID: comparing speaker {speaker_id} against {len(person_embeddings_cache)} people: {uid} {session_id}"
            )
            for person_id, data in person_embeddings_cache.items():
                distance = compare_embeddings(query_embedding, data['embedding'])
                logger.info(f"  - {sanitize_pii(data['name'])}: {distance:.4f} {uid} {session_id}")
                if distance < best_distance:
                    best_distance = distance
                    best_match = (person_id, data['name'])

            if best_match and best_distance < SPEAKER_MATCH_THRESHOLD:
                person_id, person_name = best_match

                if person_id == USER_SELF_PERSON_ID:
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
                    speaker_map_dirty = True
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
                    speaker_map_dirty = True
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

    def _get_cached_conversation(force_refresh=False):
        nonlocal _cached_conversation_data, _cached_conversation_id, _cached_conversation_time, _cached_protection_level
        now = time.monotonic()
        id_changed = current_conversation_id != _cached_conversation_id
        stale = (now - _cached_conversation_time) >= CONVERSATION_CACHE_REFRESH_SECONDS
        if _cached_conversation_data is None or id_changed or stale or force_refresh:
            data = conversations_db.get_conversation(uid, current_conversation_id)
            if data:
                _cached_conversation_data = data
                _cached_conversation_id = current_conversation_id
                _cached_conversation_time = now
                _cached_protection_level = data.get('data_protection_level', 'standard')
            return data
        return _cached_conversation_data

    def _update_cached_segments(segments_dicts):
        """Update the cached conversation's transcript_segments in-place after a write."""
        if _cached_conversation_data is not None:
            _cached_conversation_data['transcript_segments'] = segments_dicts

    def _flush_speaker_assignments(conversation_id: str):
        """Apply any pending speaker assignments to conversation segments in Firestore.

        Called before conversation rollover/processing to ensure labels are persisted
        even if the embedding match landed after the last transcript batch.
        """
        nonlocal speaker_map_dirty
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
            segments_dicts = [seg.dict() for seg in conversation.transcript_segments]
            conversations_db.update_conversation_segments(
                uid, conversation.id, segments_dicts, data_protection_level=_cached_protection_level
            )
            _update_cached_segments(segments_dicts)
            speaker_map_dirty = False
        except Exception as e:
            logger.error(f"Error flushing speaker assignments for {conversation_id}: {e} {uid} {session_id}")

    async def stream_transcript_process():
        nonlocal websocket_active, realtime_segment_buffers, realtime_photo_buffers, websocket
        nonlocal current_conversation_id, translation_enabled, speaker_to_person_map, suggested_segments, words_transcribed_since_last_record, last_transcript_time

        while websocket_active or len(realtime_segment_buffers) > 0 or len(realtime_photo_buffers) > 0:
            await asyncio.sleep(0.6)

            # Periodic cleanup of expired image chunks (enforces TTL even when uploads stop)
            _cleanup_expired_image_chunks()

            if not realtime_segment_buffers and not realtime_photo_buffers:
                continue

            segments_to_process = list(realtime_segment_buffers)
            realtime_segment_buffers.clear()

            photos_to_process = list(realtime_photo_buffers)
            realtime_photo_buffers.clear()

            finished_at = datetime.now(timezone.utc)

            # Get conversation (cached — refreshes on ID change or every 30s)
            conversation_data = _get_cached_conversation()
            if not conversation_data:
                logger.warning(
                    f"Warning: conversation {current_conversation_id} not found during segment processing {uid} {session_id}"
                )
                continue

            # Guard first_audio_byte_timestamp must be set
            if not first_audio_byte_timestamp:
                logger.warning(
                    f"Warning: first_audio_byte_timestamp not set, skipping segment processing {uid} {session_id}"
                )
                continue

            transcript_segments = []
            if segments_to_process:
                last_transcript_time = time.time()

                # If conversation has no segments yet, set started_at based on when first speech occurred
                if not conversation_data.get('transcript_segments'):
                    first_speech_timestamp = first_audio_byte_timestamp + segments_to_process[0]["start"]
                    new_started_at = datetime.fromtimestamp(first_speech_timestamp, tz=timezone.utc)
                    conversations_db.update_conversation(uid, current_conversation_id, {'started_at': new_started_at})
                    conversation_data['started_at'] = new_started_at

                # Calculate unified time offset: audio stream start relative to conversation start
                conversation_started_at = conversation_data['started_at']
                if isinstance(conversation_started_at, str):
                    conversation_started_at = datetime.fromisoformat(conversation_started_at)
                time_offset = first_audio_byte_timestamp - conversation_started_at.timestamp()

                # Apply offset to all segments
                for i, segment in enumerate(segments_to_process):
                    segment["start"] += time_offset
                    segment["end"] += time_offset
                    segments_to_process[i] = segment

                newly_processed_segments = []
                for s in segments_to_process:
                    segment = TranscriptSegment(**s, speech_profile_processed=True)
                    # In onboarding mode, force is_user=True for non-Omi segments (user's answers)
                    if onboarding_mode and s.get('speaker_id') != OnboardingHandler.OMI_SPEAKER_ID:
                        segment.is_user = True
                    newly_processed_segments.append(segment)
                words_transcribed = len(" ".join([seg.text for seg in newly_processed_segments]).split())
                if words_transcribed > 0:
                    words_transcribed_since_last_record += words_transcribed

                for seg in newly_processed_segments:
                    current_session_segments[seg.id] = seg.speech_profile_processed
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
                await websocket.send_json([segment.dict() for segment in updated_segments])

                if transcript_send is not None and user_has_credits:
                    transcript_send([segment.dict() for segment in transcript_segments])
                elif not PUSHER_ENABLED and user_has_credits:
                    # Fallback: trigger realtime integrations directly when pusher is disabled
                    try:
                        await trigger_realtime_integrations(
                            uid, [s.dict() for s in transcript_segments], current_conversation_id
                        )
                    except Exception as e:
                        logger.error(f"Error triggering realtime integrations: {e} {uid} {session_id}")

                # Onboarding: pass segments to handler for answer detection
                if onboarding_handler and not onboarding_handler.completed:
                    onboarding_handler.on_segments_received([s.dict() for s in transcript_segments])

                if translation_enabled:
                    await translate(updated_segments, conversation.id, removed_ids=removed_ids)

                # Speaker detection
                for segment in updated_segments:
                    if segment.person_id or segment.is_user or segment.id in suggested_segments:
                        continue

                    # Session consistency speaker identification
                    if segment.speaker_id in speaker_to_person_map:
                        person_id, person_name = speaker_to_person_map[segment.speaker_id]
                        if person_id == USER_SELF_PERSON_ID:
                            # User's own voice — set is_user flag
                            segment.is_user = True
                            suggested_segments.add(segment.id)
                            continue
                        _send_message_event(
                            SpeakerLabelSuggestionEvent(
                                speaker_id=segment.speaker_id,
                                person_id=_person_id_for_client(person_id),
                                person_name=person_name,
                                segment_id=segment.id,
                            )
                        )
                        suggested_segments.add(segment.id)
                        continue

                    # Embeding id speaker indentification
                    if speaker_id_enabled and person_embeddings_cache:
                        started_at_ts = conversation.started_at.timestamp()
                        if (
                            segment.speaker_id is not None
                            and not segment.person_id
                            and not segment.is_user
                            and segment.speaker_id not in speaker_to_person_map
                        ):
                            try:
                                speaker_id_segment_queue.put_nowait(
                                    {
                                        'id': segment.id,
                                        'speaker_id': segment.speaker_id,
                                        'abs_start': first_audio_byte_timestamp
                                        + segment.start
                                        - time_offset,  # raw start/end
                                        'abs_end': first_audio_byte_timestamp + segment.end - time_offset,
                                        'duration': segment.end - segment.start,
                                        'text': segment.text,  # TODO: remove
                                    }
                                )
                            except asyncio.QueueFull:
                                pass  # Drop if queue is full

                    # Text-based detection
                    detected_name = detect_speaker_from_text(segment.text)
                    if detected_name:
                        person = user_db.get_person_by_name(uid, detected_name)
                        if person:
                            person_id = person['id']
                        else:
                            # Backend creates person if missing
                            person_id = str(uuid.uuid4())
                            user_db.create_person(
                                uid,
                                {
                                    'id': person_id,
                                    'name': detected_name,
                                    'created_at': datetime.now(timezone.utc),
                                    'updated_at': datetime.now(timezone.utc),
                                },
                            )
                        _send_message_event(
                            SpeakerLabelSuggestionEvent(
                                speaker_id=segment.speaker_id,
                                person_id=_person_id_for_client(person_id),
                                person_name=detected_name,
                                segment_id=segment.id,
                            )
                        )
                        # Set maps for future segments, but only if diarization is active
                        # (speaker_id > 0 means diarization assigned a real speaker)
                        # Set maps for future segments using helper function
                        if should_update_speaker_to_person_map(segment.speaker_id):
                            speaker_to_person_map[segment.speaker_id] = (person_id, detected_name)
                        segment_person_assignment_map[segment.id] = person_id
                        suggested_segments.add(segment.id)

        # Wait for speaker_identification_task to finish consuming its queue and spawning
        # all _match_speaker_embedding tasks, then drain those tasks so speaker maps are
        # fully populated before the final Firestore flush.
        try:
            await asyncio.wait_for(speaker_id_done.wait(), timeout=15.0)
        except asyncio.TimeoutError:
            logger.warning(f"Timeout waiting for speaker ID task to finish {uid} {session_id}")
        if speaker_match_tasks:
            pending = list(speaker_match_tasks)
            try:
                await asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True), timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning(f"Timeout waiting for embedding tasks before final pass {uid} {session_id}")

        # Final pass: apply any pending speaker assignments so Firestore is correct
        # even if the embedding match completed on the last segment (no subsequent batch).
        _flush_speaker_assignments(current_conversation_id)

    # Image chunks cache with TTL tracking: {temp_id: {'chunks': [...], 'created_at': float}}
    # Using OrderedDict for O(1) oldest removal (insertion order preserved)
    image_chunks: OrderedDict[str, dict] = OrderedDict()
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

    async def process_photo(uid: str, image_b64: str, temp_id: str, send_event_func, photo_buffer):
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

    async def handle_image_chunk(uid: str, chunk_data: dict, image_chunks_cache: dict, send_event_func, photo_buffer):
        temp_id = chunk_data.get('id')
        index = chunk_data.get('index')
        total = chunk_data.get('total')
        data = chunk_data.get('data')

        if not temp_id or not isinstance(index, int) or not isinstance(total, int) or not data:
            logger.error(f"Invalid image chunk received: {sanitize(chunk_data)} {uid} {session_id}")
            return

        # Cleanup expired chunks periodically
        _cleanup_expired_image_chunks()

        if temp_id not in image_chunks_cache:
            if total <= 0:
                return
            # Enforce max concurrent uploads - O(1) with OrderedDict
            if len(image_chunks_cache) >= MAX_IMAGE_CHUNKS:
                # Remove oldest entry (first inserted)
                oldest_id, _ = image_chunks_cache.popitem(last=False)
                logger.info(f"Dropped oldest image upload to make room: {oldest_id} {uid} {session_id}")
            image_chunks_cache[temp_id] = {'chunks': [None] * total, 'created_at': time.time()}

        chunks_data = image_chunks_cache[temp_id]['chunks']
        if index < total and chunks_data[index] is None:
            chunks_data[index] = data

        if all(chunk is not None for chunk in chunks_data):
            b64_image_data = "".join(chunks_data)
            del image_chunks_cache[temp_id]
            spawn(process_photo(uid, b64_image_data, temp_id, send_event_func, photo_buffer))

    # Initialize decoders based on codec
    opus_decoder = None
    aac_decoder = None
    lc3_decoder = None

    if codec == 'opus':
        opus_decoder = opuslib.Decoder(sample_rate, 1)
    elif codec == 'aac':
        aac_decoder = AACDecoder(uid=uid, session_id=session_id, sample_rate=sample_rate, channels=channels)
    elif codec == 'lc3':
        lc3_decoder = lc3.Decoder(lc3_frame_duration_us, sample_rate)

    async def receive_data(dg_socket):
        nonlocal websocket_active, websocket_close_code, last_audio_received_time, last_activity_time, current_conversation_id
        nonlocal realtime_photo_buffers, speaker_to_person_map, first_audio_byte_timestamp, last_usage_record_timestamp
        nonlocal audio_ring_buffer, dg_usage_ms_pending
        timer_start = time.time()
        last_audio_received_time = timer_start
        last_activity_time = timer_start

        # STT audio buffer - accumulate 30ms before sending for better transcription quality
        stt_audio_buffer = bytearray()
        stt_buffer_flush_size = int(sample_rate * 2 * 0.03)  # 30ms at 16-bit mono (e.g., 6400 bytes at 16kHz)

        async def flush_stt_buffer(force: bool = False):
            nonlocal stt_audio_buffer, dg_usage_ms_pending, dg_socket

            if not stt_audio_buffer:
                return
            if not force and len(stt_audio_buffer) < stt_buffer_flush_size:
                return

            chunk = bytes(stt_audio_buffer)
            stt_audio_buffer.clear()

            # Check if DG connection died (keepalive or send failure) (#5870)
            if dg_socket is not None and dg_socket.is_connection_dead:
                close_reason = dg_socket.death_reason or 'unknown'
                logger.error(
                    'DG connection died mid-session uid=%s session=%s reason=%s',
                    uid,
                    session_id,
                    close_reason,
                )
                dg_socket = None  # Stop sending to dead connection

            if dg_socket is not None:
                # DG budget gate: skip sending if daily budget is exhausted (#5746, #6083)
                if fair_use_dg_budget_exhausted:
                    pass  # Audio not forwarded to DG — budget/credits exhausted
                else:
                    dg_socket.send(chunk)
                    # Accumulate DG usage locally, flushed every 60s (#5854)
                    if fair_use_track_dg_usage:
                        chunk_ms = len(chunk) * 1000 // (sample_rate * 2)  # 16-bit mono
                        dg_usage_ms_pending += chunk_ms

        try:
            while websocket_active:
                message = await websocket.receive()
                last_activity_time = time.time()

                # Handle client disconnect
                if message.get("type") == "websocket.disconnect":
                    close_code = message.get("code", 1000)
                    close_reason = {
                        1000: "normal_closure",
                        1001: "going_away_os_or_background",
                        1006: "abnormal_closure",
                        1011: "server_error",
                    }.get(close_code, "unknown")
                    logger.info(f"Client disconnected: code={close_code} reason={close_reason} {uid} {session_id}")
                    break

                if message.get("bytes") is not None:
                    data = message.get("bytes")
                    if len(data) <= 2:  # Ping/keepalive, 0x8a 0x00
                        continue

                    last_audio_received_time = time.time()

                    if first_audio_byte_timestamp is None:
                        first_audio_byte_timestamp = last_audio_received_time
                        last_usage_record_timestamp = first_audio_byte_timestamp

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
                        if stt_sockets_multi[ch_idx] and not fair_use_dg_budget_exhausted:
                            try:
                                stt_sockets_multi[ch_idx].send(pcm_16k)
                                # Accumulate DG usage locally, flushed every 60s (#5854)
                                if fair_use_track_dg_usage:
                                    mc_chunk_ms = len(pcm_16k) * 1000 // (TARGET_SAMPLE_RATE * 2)
                                    dg_usage_ms_pending += mc_chunk_ms
                            except Exception as e:
                                logger.error(f"[MC-STT] ch={ch_idx} send error: {e} {uid} {session_id}")

                        # Accumulate per-channel audio for mixing before sending to pusher
                        channel_mix_buffers[ch_idx].extend(pcm_16k)

                        # Mix when all channels have data, send mixed mono to pusher
                        if audio_bytes_send is not None and all(len(b) > 0 for b in channel_mix_buffers):
                            min_len = min(len(b) for b in channel_mix_buffers)
                            min_len = min_len - (min_len % 2)  # align to sample boundary
                            if min_len > 0:
                                trim_bufs = [bytearray(b[:min_len]) for b in channel_mix_buffers]
                                mixed = mix_n_channel_buffers(trim_bufs)
                                if mixed:
                                    audio_bytes_send(mixed, last_audio_received_time)
                                # Remove consumed bytes from each buffer
                                for buf in channel_mix_buffers:
                                    del buf[:min_len]

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

                        # Feed ring buffer for speaker identification (always, with wall-clock time)
                        if audio_ring_buffer is not None:
                            audio_ring_buffer.write(data, last_audio_received_time)

                        if not use_custom_stt:
                            # VAD gating is handled inside GatedDeepgramSocket.send()
                            stt_audio_buffer.extend(data)
                            await flush_stt_buffer()

                        if audio_bytes_send is not None:
                            audio_bytes_send(data, last_audio_received_time)

                elif message.get("text") is not None:
                    try:
                        json_data = json.loads(message.get("text"))
                        if json_data.get('type') == 'image_chunk':
                            await handle_image_chunk(
                                uid, json_data, image_chunks, _asend_message_event, realtime_photo_buffers
                            )
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
                                speaker_id,
                                person_id,
                                person_name,
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
                                    and current_conversation_id
                                ):
                                    spawn(
                                        send_speaker_sample_request(
                                            person_id=person_id,
                                            conv_id=current_conversation_id,
                                            segment_ids=segment_ids,
                                        )
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
            websocket_close_code = 1011
        finally:
            # Log VAD gate metrics before cleanup
            if vad_gate is not None:
                logger.info(json.dumps(vad_gate.to_json_log()))
            # Flush any remaining audio in buffer to STT
            if not use_custom_stt:
                await flush_stt_buffer(force=True)
            websocket_active = False

    # Start
    #
    try:
        # Init STT
        _send_message_event(MessageServiceStatusEvent(status="stt_initiating", status_text="STT Service Starting"))
        await _process_stt()

        # Init pusher
        pusher_tasks = []
        if PUSHER_ENABLED:
            (
                pusher_connect,
                pusher_close,
                transcript_send,
                transcript_consume,
                audio_bytes_send,
                audio_bytes_consume,
                request_conversation_processing,
                pusher_receive,
                pusher_is_connected,
                pusher_is_degraded,
                pusher_start_degraded,
                send_speaker_sample_request,
                pusher_heartbeat,
            ) = create_pusher_task_handler()

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
                pusher_tasks.append(asyncio.create_task(transcript_consume()))
            if audio_bytes_consume is not None:
                pusher_tasks.append(asyncio.create_task(audio_bytes_consume()))
            if pusher_receive is not None:
                pusher_tasks.append(asyncio.create_task(pusher_receive()))
            pusher_tasks.append(asyncio.create_task(pusher_heartbeat()))

        # Tasks
        data_process_task = asyncio.create_task(receive_data(deepgram_socket))
        stream_transcript_task = asyncio.create_task(stream_transcript_process())
        record_usage_task = asyncio.create_task(_record_usage_periodically())

        _send_message_event(MessageServiceStatusEvent(status="ready"))

        tasks = [
            data_process_task,
            stream_transcript_task,
            heartbeat_task,
            record_usage_task,
        ] + pusher_tasks

        if is_multi_channel:
            # Multi-channel doesn't run speaker_identification_task
            speaker_id_done.set()

        if not is_multi_channel:
            # Single-channel: conversation lifecycle (timeout splitting), pending processing, speaker ID
            lifecycle_manager_task = asyncio.create_task(conversation_lifecycle_manager())
            pending_conversations_task = asyncio.create_task(process_pending_conversations(timed_out_conversation_id))
            speaker_id_task = asyncio.create_task(speaker_identification_task())
            tasks.extend([lifecycle_manager_task, pending_conversations_task, speaker_id_task])

        await asyncio.gather(*tasks)

    except Exception as e:
        logger.error(f"Error during WebSocket operation: {e} {uid} {session_id}")
    finally:
        BACKEND_LISTEN_ACTIVE_WS_CONNECTIONS.dec()
        if not use_custom_stt and last_usage_record_timestamp:
            transcription_seconds = int(time.time() - last_usage_record_timestamp)
            words_to_record = words_transcribed_since_last_record

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
            if fair_use_track_dg_usage and dg_usage_ms_pending > 0:
                record_dg_usage_ms(uid, dg_usage_ms_pending)
                dg_usage_ms_pending = 0

            if transcription_seconds > 0 or words_to_record > 0 or speech_seconds_delta > 0:
                record_usage(
                    uid,
                    transcription_seconds=transcription_seconds,
                    words_transcribed=words_to_record,
                    speech_seconds=speech_seconds_delta,
                )

        # Flush pending debounced translations BEFORE setting websocket_active=False
        try:
            await flush_pending_translations()
        except Exception as e:
            logger.error(f"Error flushing pending translations: {e} {uid} {session_id}")

        websocket_active = False

        # STT sockets
        try:
            if is_multi_channel:
                for mc_stt_socket in stt_sockets_multi:
                    if mc_stt_socket:
                        mc_stt_socket.finish()
            else:
                if deepgram_socket:
                    # GatedDeepgramSocket.finish() handles finalize automatically
                    deepgram_socket.finish()
        except Exception as e:
            logger.error(f"Error closing STT sockets: {e} {uid} {session_id}")

        # Client sockets
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close(code=websocket_close_code)
            except Exception as e:
                logger.error(f"Error closing Client WebSocket: {e} {uid} {session_id}")

        # Multi-channel: process the single conversation at session end
        if is_multi_channel and current_conversation_id:
            try:
                redis_db.remove_in_progress_conversation_id(uid)
                _flush_speaker_assignments(current_conversation_id)
                await _process_conversation(current_conversation_id)
                logger.info(
                    f"Multi-channel conversation {current_conversation_id} submitted for processing {uid} {session_id}"
                )
            except Exception as e:
                logger.error(f"Error processing multi-channel conversation: {e} {uid} {session_id}")

        # Pusher sockets
        if pusher_close is not None:
            try:
                await pusher_close()
            except Exception as e:
                logger.error(f"Error closing Pusher: {e} {uid} {session_id}")

        # Clean up onboarding handler
        if onboarding_handler:
            onboarding_handler.cleanup()

        # Cancel all tracked background tasks to prevent memory leaks
        # Snapshot to avoid mutation during iteration
        tasks_to_cancel = list(bg_tasks)
        for task in tasks_to_cancel:
            task.cancel()
        if tasks_to_cancel:
            await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
        bg_tasks.clear()

        # Flush any remaining mixed audio to pusher
        if is_multi_channel and audio_bytes_send is not None and any(len(b) > 0 for b in channel_mix_buffers):
            try:
                mixed = mix_n_channel_buffers(channel_mix_buffers)
                if mixed:
                    audio_bytes_send(mixed, time.time())
            except Exception:
                pass
            for buf in channel_mix_buffers:
                buf.clear()

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
            if language_cache is not None:
                language_cache.cache.clear()
            if translation_service is not None:
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
    vad_gate_override: Optional[str] = None,
    call_id: Optional[str] = None,
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
        vad_gate_override=vad_gate_override,
        call_id=call_id,
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
    vad_gate: str = '',
    call_id: Optional[str] = None,
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
        None,
        conversation_timeout=conversation_timeout,
        source=source,
        custom_stt_mode=custom_stt_mode,
        onboarding_mode=onboarding_mode,
        speaker_auto_assign_enabled=speaker_auto_assign_enabled,
        vad_gate_override=vad_gate_override,
        call_id=call_id,
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
        uid = auth.get_current_user_uid_from_ws_message(first_message)
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
    )
    logger.info(f"web_listen_handler ended {uid}")

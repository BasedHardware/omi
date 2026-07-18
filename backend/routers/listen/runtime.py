"""Runtime coordinator for an accepted /v4/listen WebSocket."""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from dataclasses import replace
from typing import Any, Awaitable, Callable, Dict, List, Optional, cast

from fastapi.websockets import WebSocketDisconnect
from starlette.websockets import WebSocketState

from models.message_event import (
    FREEMIUM_ACTION_SETUP_ON_DEVICE_STT,
    FreemiumThresholdReachedEvent,
    MessageEvent,
    MessageServiceStatusEvent,
    SpeakerLabelSuggestionEvent,
)
from models.users import PlanType
from utils.analytics import billable_transcription_seconds, record_usage
from utils.apps import is_audio_bytes_app_enabled
from utils.async_tasks import WebSocketTaskSupervisor, drain_tasks, wait_for_event
from utils.byok import extract_byok_from_websocket, get_byok_keys, set_byok_keys
from utils.client_device import resolve_client_device_from_headers
from utils.executors import db_executor, run_blocking, start_background_task
from utils.fair_use import (
    FAIR_USE_CHECK_INTERVAL_SECONDS,
    FAIR_USE_ENABLED,
    FAIR_USE_RESTRICT_DAILY_DG_MS,
    check_soft_caps,
    get_enforcement_stage,
    get_rolling_speech_ms,
    is_daily_audio_ceiling_exceeded,
    is_dg_budget_exhausted,
    record_dg_usage_ms,
    record_speech_ms,
    trigger_classifier_if_needed,
)
from utils.listen_pusher_session import ListenPusherSession, ListenPusherSessionConfig, ListenPusherSessionDeps
from utils.listen_session_bootstrap import finalize_listen_connect_context, load_listen_connect_base
from utils.metrics import BACKEND_LISTEN_ACTIVE_WS_CONNECTIONS
from utils.notifications import send_credit_limit_notification, send_silent_user_notification
from utils.onboarding import OnboardingHandler
from utils.pusher import PusherCircuitBreakerOpen
from utils.stt.streaming import STTService, get_stt_service_for_language
from config.stt_provider_policy import PARAKEET_PROVIDER, STTServingSurface, provider_is_enabled
from utils.subscription import get_remaining_transcription_seconds, is_trial_paywalled
from utils.transcribe_decisions import (
    effective_conversation_timeout,
    normalize_codec_frame,
    normalize_language,
    should_enable_speaker_identification,
    should_force_single_language,
    should_include_speech_profile,
    should_load_speech_profile,
    validate_audio_format,
)
from utils.transcribe_store import check_credits_invalidation, conversations_db, redis_db, user_db
from utils.webhooks import get_audio_bytes_webhook_seconds
from utils.audio import AudioRingBuffer
from utils.other.storage import get_user_has_speech_profile
from utils.transcribe_decisions import USER_SELF_PERSON_ID, person_id_for_client

from .contracts import ListenLimits, ListenRequest, ListenSessionState
from .conversations import LiveConversationController
from .persistence import ListenPersistence
from .receiver import ListenReceiver
from .speakers import SpeakerMatcher
from .transcripts import TranscriptProcessor
from utils.listen_audio import build_channel_config

logger = logging.getLogger(__name__)

PUSHER_ENABLED = bool(os.getenv('HOSTED_PUSHER_API_URL'))
FREEMIUM_THRESHOLD_SECONDS = 180


def _normalize_client_conversation_id(value: Optional[str]) -> Optional[str]:
    if not value or not value.strip():
        return None
    try:
        return str(uuid.UUID(value.strip()))
    except ValueError:
        return None


class ListenSessionRuntime:
    """Stateful session coordinator; subcomponents only communicate through this surface."""

    def __init__(self, request: ListenRequest):
        self.request = request
        self.limits = ListenLimits()
        self.persistence = ListenPersistence()
        self.state = ListenSessionState()
        self.session_id = str(uuid.uuid4())
        self.client_conversation_id = _normalize_client_conversation_id(request.client_conversation_id)
        self.recording_session_id = self.client_conversation_id or str(uuid.uuid4())
        self.recording_session_ids_by_conversation: Dict[str, str] = {}
        self.client_device_context = request.client_device_context or resolve_client_device_from_headers(
            request.websocket.headers
        )
        self.use_custom_stt = request.custom_stt_mode.value == 'enabled'
        self.pusher_enabled = PUSHER_ENABLED
        self.is_multi_channel = request.channels >= 2
        self.language = request.language
        self.stt_service: Any = None
        self.stt_language = ''
        self.stt_model = ''
        self.vocabulary: List[str] = []
        self.translation_language: Optional[str] = None
        self.user_has_credits = True
        self.private_cloud_sync_enabled = False
        self.has_speech_profile = False
        self.conversation_creation_timeout = request.conversation_timeout
        self.frame_size = 160
        self.lc3_frame_duration_us: Optional[int] = None
        self.task_supervisor = WebSocketTaskSupervisor(
            uid=request.uid, label='listen', gauge=BACKEND_LISTEN_ACTIVE_WS_CONNECTIONS
        )
        self.state.shutdown_event = self.task_supervisor.shutdown_event
        self.request_conversation_processing: Optional[Callable[..., Awaitable[Any]]] = None
        self.transcript_send: Optional[Callable[..., Any]] = None
        self.audio_bytes_send: Optional[Callable[..., Any]] = None
        self.send_speaker_sample_request: Optional[Callable[..., Awaitable[Any]]] = None
        self.pusher_close: Optional[Callable[..., Awaitable[Any]]] = None
        self.pusher_tasks: List[asyncio.Task[Any]] = []
        self.onboarding_handler: Optional[OnboardingHandler] = None
        self.onboarding_omi_speaker_id = OnboardingHandler.OMI_SPEAKER_ID
        self.receiver: Any = None
        self.speakers: Any = None
        self.transcripts: Any = None
        self.conversations: Any = None

    def _build_components(self) -> None:
        channels = build_channel_config(self.request.source or 'phone_call') if self.is_multi_channel else []
        self.receiver = ListenReceiver(
            self, channels, {channel.channel_id: index for index, channel in enumerate(channels)}
        )
        self.speakers = SpeakerMatcher(self)
        self.transcripts = TranscriptProcessor(self)
        self.conversations = LiveConversationController(self)

    def spawn(self, coro: Awaitable[Any], *, name: str) -> asyncio.Task[Any]:
        return self.task_supervisor.create_task(cast(Any, coro), name=name)

    async def wait(self, seconds: float) -> bool:
        return await wait_for_event(self.state.shutdown_event, seconds)

    async def drain(self, tasks: List[asyncio.Task[Any]], *, timeout: float, label: str) -> None:
        await drain_tasks(tasks, timeout=timeout, label=label, cancel=False)

    async def asend_event(self, event: MessageEvent) -> bool:
        if not self.state.active:
            return False
        try:
            await self.request.websocket.send_json(event.to_json())
            return True
        except WebSocketDisconnect:
            self.state.active = False
        except Exception as error:
            logger.error('Listen event delivery failed type=%s', type(error).__name__)
        return False

    def send_event(self, event: MessageEvent) -> None:
        if self.state.active:
            self.spawn(self.asend_event(event), name='message_event')

    def emit_speaker_suggestion(self, speaker_id: int, person_id: str, person_name: str, segment_id: str) -> None:
        self.send_event(
            SpeakerLabelSuggestionEvent(
                speaker_id=speaker_id,
                person_id=(
                    'user'
                    if person_id == USER_SELF_PERSON_ID
                    else person_id_for_client(person_id, self.request.speaker_auto_assign_enabled)
                ),
                person_name=person_name,
                segment_id=segment_id,
            )
        )

    async def _admit(self) -> bool:
        if not self.request.uid:
            await self.request.websocket.close(code=1008, reason='Bad uid')
            return False
        set_byok_keys(extract_byok_from_websocket(self.request.websocket))
        if await run_blocking(db_executor, is_trial_paywalled, self.request.uid, self.request.source):
            await self.request.websocket.send_json(
                FreemiumThresholdReachedEvent(remaining_seconds=0, action=FREEMIUM_ACTION_SETUP_ON_DEVICE_STT).to_json()
            )
            await self.wait(0.5)
            await self.request.websocket.close(code=1008, reason='trial_expired')
            return False
        error = validate_audio_format(self.request.codec, self.request.sample_rate)
        if error:
            await self.request.websocket.close(code=1003, reason=error)
            return False
        return True

    async def _bootstrap(self) -> bool:
        request = self.request
        base = await load_listen_connect_base(request.uid, source=request.source, use_custom_stt=self.use_custom_stt)
        if not base.user_exists:
            await request.websocket.close(code=1008, reason='Bad user')
            return False
        self.user_has_credits = base.user_has_credits
        self.language = normalize_language(request.language)
        requested_service = request.stt_service
        single_language_mode = should_force_single_language(
            request.onboarding_mode,
            base.transcription_prefs.get('single_language_mode', False),
        )
        self.stt_service, self.stt_language, self.stt_model = get_stt_service_for_language(
            self.language,
            multi_lang_enabled=not single_language_mode,
        )
        if not self.stt_service or not self.stt_language:
            await request.websocket.close(code=1008, reason=f'The language is not supported, {self.language}')
            return False
        if (
            requested_service == 'parakeet'
            and provider_is_enabled(PARAKEET_PROVIDER, STTServingSurface.STREAMING)
            and os.getenv('HOSTED_PARAKEET_API_URL')
        ):
            self.stt_service = STTService.parakeet
        context = finalize_listen_connect_context(
            base, language=self.language, onboarding_mode=request.onboarding_mode, stt_language=self.stt_language
        )
        self.language = context.language
        self.vocabulary = context.vocabulary
        self.translation_language = context.translation_language
        if self.use_custom_stt != context.transcription_prefs.get('uses_custom_stt', False):
            try:
                await self.persistence.call(user_db.set_user_custom_stt_usage, request.uid, self.use_custom_stt)
            except Exception as error:
                logger.warning('Custom STT usage stamp failed type=%s', type(error).__name__)
        self.private_cloud_sync_enabled = await self.persistence.call(
            user_db.get_user_private_cloud_sync_enabled, request.uid
        )
        include_profile = should_include_speech_profile(
            request.include_speech_profile, self.is_multi_channel, request.onboarding_mode
        )
        if should_load_speech_profile(
            use_custom_stt=self.use_custom_stt,
            is_multi_channel=self.is_multi_channel,
            include_speech_profile=include_profile,
        ):
            self.has_speech_profile = await self.persistence.call(get_user_has_speech_profile, request.uid)
        self.state.speaker_id_enabled = should_enable_speaker_identification(
            use_custom_stt=self.use_custom_stt,
            private_cloud_sync_enabled=self.private_cloud_sync_enabled,
            has_speech_profile=self.has_speech_profile,
        )
        if self.state.speaker_id_enabled:
            self.state.audio_ring_buffer = AudioRingBuffer(self.limits.ring_buffer_duration, request.sample_rate)
        self.conversation_creation_timeout = effective_conversation_timeout(
            request.conversation_timeout, self.is_multi_channel
        )
        decision = normalize_codec_frame(request.codec)
        self.request = replace(request, codec=decision.codec)
        self.frame_size = decision.frame_size
        self.lc3_frame_duration_us = decision.lc3_frame_duration_us
        self._build_components()
        if not self.user_has_credits:
            try:
                await send_credit_limit_notification(request.uid)
                await request.websocket.send_json(
                    FreemiumThresholdReachedEvent(
                        remaining_seconds=0, action=FREEMIUM_ACTION_SETUP_ON_DEVICE_STT
                    ).to_json()
                )
                self.state.freemium_threshold_sent = True
            except Exception as error:
                logger.error('Credit-limit notification failed type=%s', type(error).__name__)
        if FAIR_USE_ENABLED:
            self.state.fair_use_track_dg_usage = context.fair_use_track_dg_usage
            self.state.fair_use_dg_budget_exhausted = context.fair_use_dg_budget_exhausted
        if request.onboarding_mode:

            async def send_onboarding(event: Dict[str, Any]) -> None:
                if self.state.active and request.websocket.client_state == WebSocketState.CONNECTED:
                    await request.websocket.send_json(event)

            self.onboarding_handler = OnboardingHandler(request.uid, send_onboarding, self.transcripts.enqueue)
        return True

    async def _heartbeat(self) -> None:
        while self.state.active:
            if self.request.websocket.client_state != WebSocketState.CONNECTED:
                self.state.active = False
                break
            await self.request.websocket.send_text('ping')
            if self.state.last_activity_time and time.time() - self.state.last_activity_time > 90:
                self.state.close_code = 1001
                self.state.active = False
                break
            if await self.wait(10):
                break

    async def _record_usage_periodically(self) -> None:
        while self.state.active:
            if await self.wait(60):
                break
            transcription_seconds = await self._flush_usage(final=False)
            if self.use_custom_stt:
                continue
            now = time.time()
            if FAIR_USE_ENABLED and now - self.state.fair_use_last_check_ts >= FAIR_USE_CHECK_INTERVAL_SECONDS:
                self.state.fair_use_last_check_ts = now
                try:
                    if self.state.fair_use_plan is None:
                        sub = await self.persistence.call(user_db.get_user_valid_subscription, self.request.uid)
                        self.state.fair_use_plan = sub.plan if sub else None
                    totals = await self.persistence.call(get_rolling_speech_ms, self.request.uid)
                    caps = await self.persistence.call(
                        check_soft_caps, self.request.uid, speech_totals=totals, plan=self.state.fair_use_plan
                    )
                    if caps:
                        start_background_task(
                            trigger_classifier_if_needed(self.request.uid, caps, self.session_id),
                            name=f'fair_use_classifier:{self.request.uid}:{self.session_id}',
                        )
                        if FAIR_USE_RESTRICT_DAILY_DG_MS > 0:
                            self.state.fair_use_track_dg_usage = True
                    stage = await self.persistence.call(get_enforcement_stage, self.request.uid)
                    if stage == 'restrict' and FAIR_USE_RESTRICT_DAILY_DG_MS > 0:
                        self.state.fair_use_track_dg_usage = True
                        was_exhausted = self.state.fair_use_dg_budget_exhausted
                        self.state.fair_use_dg_budget_exhausted = await self.persistence.call(
                            is_dg_budget_exhausted, self.request.uid
                        )
                        if self.state.fair_use_dg_budget_exhausted and not was_exhausted:
                            logger.info('Fair-use DG budget exhausted')
                    elif caps and FAIR_USE_RESTRICT_DAILY_DG_MS > 0:
                        # Meter while the classifier decides whether this cap hit should escalate.
                        self.state.fair_use_dg_budget_exhausted = False
                    else:
                        self.state.fair_use_track_dg_usage = False
                        self.state.fair_use_dg_budget_exhausted = False
                    # Hard anti-abuse daily audio ceiling (all plans): once over the ceiling,
                    # stop forwarding audio to STT for the rest of the day. Reuses the same
                    # gate the restrict stage uses, so no socket close / reconnect loop.
                    if is_daily_audio_ceiling_exceeded(self.request.uid, speech_totals=totals):
                        if not self.state.fair_use_dg_budget_exhausted:
                            logger.info('Fair-use daily audio ceiling reached uid=%s', self.request.uid)
                        self.state.fair_use_dg_budget_exhausted = True
                except Exception as error:
                    logger.error('Fair-use listen check failed type=%s', type(error).__name__)
            await self._refresh_credits(transcription_seconds=transcription_seconds)

    async def _refresh_credits(self, *, transcription_seconds: int = 0) -> None:
        now = time.time()
        invalidated = await self.persistence.call(check_credits_invalidation, self.request.uid)
        needs_refresh = (
            not self.state.remaining_seconds_cache_initialized
            or invalidated
            or now - self.state.remaining_seconds_cache_ts >= self.limits.credits_refresh_seconds
            or (
                self.state.remaining_seconds_cache is not None
                and self.state.remaining_seconds_cache <= 0
                and now - self.state.remaining_seconds_cache_ts >= 60
            )
        )
        if needs_refresh:
            self.state.remaining_seconds_cache = await self.persistence.call(
                get_remaining_transcription_seconds, self.request.uid, source=self.request.source
            )
            self.state.remaining_seconds_cache_ts = now
            self.state.remaining_seconds_cache_initialized = True
        elif self.state.remaining_seconds_cache is not None and transcription_seconds > 0:
            self.state.remaining_seconds_cache = max(0, self.state.remaining_seconds_cache - transcription_seconds)
        remaining = self.state.remaining_seconds_cache
        if remaining is not None and remaining <= FREEMIUM_THRESHOLD_SECONDS and not self.state.freemium_threshold_sent:
            await self.asend_event(
                FreemiumThresholdReachedEvent(remaining_seconds=remaining, action=FREEMIUM_ACTION_SETUP_ON_DEVICE_STT)
            )
            self.state.freemium_threshold_sent = True
            try:
                await send_credit_limit_notification(self.request.uid)
            except Exception as error:
                logger.error('Credit-limit notification refresh failed type=%s', type(error).__name__)
        self.user_has_credits = remaining is None or remaining > 0
        if self.user_has_credits and (remaining is None or remaining > FREEMIUM_THRESHOLD_SECONDS):
            self.state.freemium_threshold_sent = False
        subscription = await self.persistence.call(user_db.get_user_valid_subscription, self.request.uid)
        if not subscription or subscription.plan == PlanType.basic:
            last_words = self.state.last_transcript_time or self.state.first_audio_byte_timestamp
            if (
                self.state.last_audio_received_time
                and last_words
                and self.state.last_audio_received_time - last_words > 15 * 60
            ):
                try:
                    await send_silent_user_notification(self.request.uid)
                except Exception as error:
                    logger.error('Silent-user notification refresh failed type=%s', type(error).__name__)

    async def _flush_usage(self, *, final: bool) -> int:
        if self.state.fair_use_track_dg_usage and self.state.dg_usage_ms_pending:
            await self.persistence.call(record_dg_usage_ms, self.request.uid, self.state.dg_usage_ms_pending)
            self.state.dg_usage_ms_pending = 0
        if self.use_custom_stt or not self.state.last_usage_record_timestamp:
            return 0
        speech_seconds = 0
        if self.receiver.vad_gate is not None:
            speech_ms = self.receiver.vad_gate.consume_speech_ms_delta()
            speech_seconds = speech_ms // 1000
            if FAIR_USE_ENABLED and speech_ms:
                await self.persistence.call(record_speech_ms, self.request.uid, speech_ms)
        now = time.time()
        seconds = billable_transcription_seconds(
            self.state.last_usage_record_timestamp, self.state.last_audio_received_time, now
        )
        words = self.state.words_transcribed_since_last_record
        self.state.words_transcribed_since_last_record = 0
        if seconds or words or speech_seconds:
            await self.persistence.call(
                record_usage,
                self.request.uid,
                transcription_seconds=seconds,
                words_transcribed=words,
                speech_seconds=speech_seconds,
            )
        if not final:
            self.state.last_usage_record_timestamp = now
        return seconds

    async def _start_pusher(self) -> None:
        if not PUSHER_ENABLED:
            return
        audio_bytes_enabled = (
            bool(await self.persistence.call(get_audio_bytes_webhook_seconds, self.request.uid))
            or await self.persistence.call(is_audio_bytes_app_enabled, self.request.uid)
            or self.private_cloud_sync_enabled
        )
        session = ListenPusherSession(
            ListenPusherSessionConfig(
                uid=self.request.uid,
                session_id=self.session_id,
                sample_rate=self.request.sample_rate,
                is_multi_channel=self.is_multi_channel,
                language=self.language,
                audio_bytes_enabled=audio_bytes_enabled,
                max_segment_buffer_size=self.limits.max_segment_buffer_size,
                max_audio_buffer_size=self.limits.max_audio_buffer_size,
                max_pending_requests=self.limits.max_pending_requests,
                max_pending_speaker_sample_requests=self.limits.max_pending_speaker_sample_requests,
            ),
            ListenPusherSessionDeps(
                get_current_conversation_id=lambda: self.state.current_conversation_id,
                is_active=lambda: self.state.active,
                shutdown_event=self.state.shutdown_event,
                get_byok_keys=get_byok_keys,
                on_conversation_processed=self.conversations.on_conversation_processed,
                wait_for_event=wait_for_event,
            ),
        )
        self.pusher_close = session.close
        self.transcript_send = session.transcript_send
        self.audio_bytes_send = session.audio_bytes_send if session.config.audio_bytes_enabled else None
        self.request_conversation_processing = session.request_conversation_processing
        self.send_speaker_sample_request = session.send_speaker_sample_request
        try:
            await session.connect()
        except PusherCircuitBreakerOpen:
            pass
        except Exception as error:
            logger.error('Pusher initial connection failed type=%s', type(error).__name__)
        if not session.is_connected():
            session.start_degraded()
        self.pusher_tasks = [
            self.task_supervisor.create_lifetime_task(session.transcript_consume(), name='pusher_transcript'),
            self.task_supervisor.create_lifetime_task(session.pusher_receive(), name='pusher_receive'),
            self.task_supervisor.create_lifetime_task(session.pusher_heartbeat(), name='pusher_heartbeat'),
        ]
        if session.config.audio_bytes_enabled:
            self.pusher_tasks.append(
                self.task_supervisor.create_lifetime_task(session.audio_bytes_consume(), name='pusher_audio')
            )

    async def run(self) -> None:
        if not await self._admit() or not await self._bootstrap():
            return
        try:
            self.receiver.initialize_decoders()
        except Exception as error:
            logger.error('Codec decoder initialization failed type=%s', type(error).__name__)
            reason = 'LC3 codec is not available' if self.request.codec == 'lc3' else 'unsupported_audio_format'
            await self.request.websocket.close(code=self.state.close_code, reason=reason)
            return
        self.send_event(
            MessageServiceStatusEvent(event_type='service_status', status='initiating', status_text='Service Starting')
        )
        await self.conversations.send_last_conversation()
        self.send_event(
            MessageServiceStatusEvent(
                status='in_progress_conversations_processing', status_text='Processing Conversations'
            )
        )
        timed_out = await self.conversations.prepare()
        background: List[asyncio.Task[Any]] = []
        try:
            self.task_supervisor.start_session()
            await self.asend_event(
                MessageServiceStatusEvent(status='stt_initiating', status_text='STT Service Starting')
            )
            if not await self.receiver.initialize_stt():
                return
            await self._start_pusher()
            receive_task = self.task_supervisor.create_task(self.receiver.receive_data(), name='receive')
            background.extend(
                [
                    self.task_supervisor.create_lifetime_task(self._heartbeat(), name='heartbeat'),
                    self.task_supervisor.create_lifetime_task(
                        self.transcripts.process_loop(), name='stream_transcript'
                    ),
                    self.task_supervisor.create_lifetime_task(self._record_usage_periodically(), name='record_usage'),
                    *self.pusher_tasks,
                ]
            )
            if self.is_multi_channel:
                self.state.speaker_id_done.set()
            else:
                background.extend(
                    [
                        self.task_supervisor.create_lifetime_task(
                            self.conversations.lifecycle_loop(), name='lifecycle'
                        ),
                        self.task_supervisor.create_finite_task(
                            self.conversations.process_pending(timed_out), name='pending_convos'
                        ),
                        self.task_supervisor.create_finite_task(self.speakers.load_and_run(), name='speaker_id'),
                    ]
                )
            self.send_event(MessageServiceStatusEvent(status='ready'))
            result = await self.task_supervisor.supervise(receive_task=receive_task)
            logger.info('Listen supervisor exited reason=%s task=%s', result.reason, result.task_name)
            if receive_task.done() and not receive_task.cancelled():
                receive_error = receive_task.exception()
                if receive_error is not None:
                    raise receive_error
            if not receive_task.done():
                self.state.active = False
                receive_task.cancel()
                try:
                    await receive_task
                except asyncio.CancelledError:
                    pass
            self.state.shutdown_event.set()
            await self.task_supervisor.drain_monitored(timeout=self.limits.bg_drain_timeout, cancel=False)
        except Exception as error:
            logger.error('Listen WebSocket operation failed type=%s', type(error).__name__)
        finally:
            await self._teardown()

    async def _teardown(self) -> None:
        self.state.shutdown_event.set()
        self.task_supervisor.end_session()
        try:
            await self.transcripts.flush_translations()
        except Exception as error:
            logger.error('Translation flush failed type=%s', type(error).__name__)
        self.state.active = False
        try:
            self.receiver.finish()
        except Exception as error:
            logger.error('STT finish failed type=%s', type(error).__name__)
        await self._flush_usage(final=True)
        if self.request.websocket.client_state == WebSocketState.CONNECTED and not self.state.stt_terminal_failure:
            try:
                await self.request.websocket.close(code=self.state.close_code)
            except Exception:
                pass
        conversation_id = self.state.current_conversation_id
        if conversation_id:
            try:
                if self.is_multi_channel:
                    await self.persistence.call(redis_db.remove_in_progress_conversation_id, self.request.uid)
                    await self.transcripts.flush_speaker_assignments(conversation_id)
                    await self.conversations.process_conversation(conversation_id)
                else:
                    conversation = await self.persistence.call(
                        conversations_db.get_conversation, self.request.uid, conversation_id
                    )
                    if (
                        conversation
                        and self.state.close_code == 1000
                        and getattr(conversation.get('source'), 'value', conversation.get('source')) == 'desktop'
                        and (conversation.get('transcript_segments') or conversation.get('photos'))
                    ):
                        await self.transcripts.flush_speaker_assignments(conversation_id)
                        if await self.conversations.process_conversation(conversation_id):
                            current = await self.persistence.call(
                                redis_db.get_in_progress_conversation_id, self.request.uid
                            )
                            if current == conversation_id:
                                await self.persistence.call(
                                    redis_db.remove_in_progress_conversation_id, self.request.uid
                                )
            except Exception as error:
                logger.error('Conversation disconnect finalization failed type=%s', type(error).__name__)
        try:
            await self.receiver.flush_multi_channel_tail()
        finally:
            if self.pusher_close:
                try:
                    await self.pusher_close()
                except Exception as error:
                    logger.error('Pusher close failed type=%s', type(error).__name__)
        if self.onboarding_handler:
            self.onboarding_handler.cleanup()
        await self.task_supervisor.drain_all(timeout=5.0, cancel=True)
        self.receiver.clear()
        self.transcripts.clear()
        self.speakers.clear()


async def run_listen_session(request: ListenRequest) -> None:
    await ListenSessionRuntime(request).run()

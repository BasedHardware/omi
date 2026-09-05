"""Inbound listen WebSocket frames, audio decoding, and image assembly."""

from __future__ import annotations

import asyncio
import audioop
import json
import logging
import time
import uuid
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple, cast

lc3: Any = None
lc3_import_error: Optional[BaseException] = None
try:
    import lc3 as lc3_module  # type: ignore[reportMissingImports]
except Exception as error:
    lc3_import_error = error
else:
    lc3 = lc3_module

opuslib: Any = None
opuslib_import_error: Optional[BaseException] = None
try:
    import opuslib as opuslib_module  # type: ignore[reportMissingImports]
except Exception as error:
    opuslib_import_error = error
else:
    opuslib = opuslib_module

from fastapi.websockets import WebSocketDisconnect

from models.conversation_photo import ConversationPhoto
from models.message_event import PhotoDescribedEvent, PhotoProcessingEvent
from models.transcript_segment import SpeakerIdentityStatus
from utils.aac import AACDecoder
from utils.llm.openglass import describe_image
from utils.request_validation import ImageChunkEnvelope
from utils.speaker_assignment import update_speaker_assignment_maps
from utils.stt.live_failure import (
    MAX_STT_FAILOVERS,
    flush_live_stt_buffer,
    live_stt_initialization_failure,
    live_stt_socket_is_dead,
    live_stt_terminal_reason,
    live_stt_upstream_failure,
    note_typed_provider_death,
    send_live_stt_audio,
    terminate_live_stt_session,
)
from config.stt_provider_policy import provider_for_service
from utils.stt.provider_resilience import close_rejected_socket, fallback_socket_is_serving
from utils.stt.streaming import (
    STTService,
    connect_stt_socket_with_fallback,
    deepgram_fallback_model,
    get_stt_service_for_language,
    make_stream_callback,
    modulate_is_configured_fallback,
    parakeet_is_configured_fallback,
    process_audio_dg,
    process_audio_modulate,
    process_audio_soniox,
    process_audio_parakeet,
)
from utils.stt.speaker_identity import SpeakerProviderEpoch
from utils.stt.vad_gate import GatedSTTSocket, VADStreamingGate, VAD_GATE_MODE, is_gate_enabled
from utils.transcribe_decisions import (
    TARGET_SAMPLE_RATE,
    decide_multi_channel_mix,
    decide_multi_channel_stt_send,
    decide_stt_buffer_flush,
    should_flush_final_multi_channel_mix,
    should_initialize_vad_gate,
    stt_buffer_flush_size,
    vad_gate_mode,
)
from utils.log_sanitizer import sanitize
from utils.listen_audio import ChannelConfig, mix_n_channel_buffers, resample_pcm
from utils.observability.fallback import record_fallback
from utils.observability.transcription import (
    record_listen_audio_outcome,
    record_listen_unknown_channel_prefix,
)
from utils.product_telemetry import emit_product_event

logger = logging.getLogger(__name__)

# Cadence for the frame-independent provider-death monitor (#10028). Short enough
# to terminate a zombie "Listening" session promptly, far below ws_receive_timeout.
STT_DEATH_POLL_INTERVAL_SECONDS = 1.0

# Longest frame the Opus format can carry, in milliseconds.
OPUS_MAX_FRAME_MS = 120

# Consecutive undecodable frames that mean the session's whole stream is unusable rather
# than one corrupt packet: 1 s of audio at the 20 ms cadence omi clients encode with.
DECODE_FAILURE_STREAK_ALERT = 50


def opus_decode_capacity(sample_rate: int) -> int:
    """Samples to hand `Decoder.decode` as its output-buffer size.

    Opus packets are self-describing: `frame_size` is only the capacity of the buffer the
    decoder writes into, and it never emits more samples than the packet actually holds, so
    a 10 ms frame still decodes to 10 ms under a larger buffer. Sizing it to the negotiated
    frame duration instead made libopus answer `buffer too small` for every longer frame a
    client sent, and the receiver dropped the whole session's audio one frame at a time.
    """
    return sample_rate // 1000 * OPUS_MAX_FRAME_MS


def _get_opuslib() -> Any:
    if opuslib is None:
        raise RuntimeError('Opus streaming requires opuslib and the native libopus library.') from opuslib_import_error
    return opuslib


def _get_lc3() -> Any:
    if lc3 is None:
        raise RuntimeError('LC3 streaming requires lc3py and its native codec library.') from lc3_import_error
    return lc3


class ListenReceiver:
    def __init__(self, host: Any, channel_configs: List[ChannelConfig], channel_id_to_index: Dict[int, int]):
        self.host = host
        self.channel_configs = channel_configs
        self.channel_id_to_index = channel_id_to_index
        self.stt_socket: Any = None
        # Providers whose socket already died this session; a failover must not
        # reselect one, or a dead primary would be chosen again immediately.
        self._stt_failed_providers: set[str] = set()
        self._stt_rebuild: Optional[Tuple[Any, Any, int]] = None
        self._stt_failover_lock = asyncio.Lock()
        self.stt_sockets_multi: List[Any] = [None] * len(channel_configs)
        self.multi_opus_decoders: List[Any] = [None] * len(channel_configs)
        self.channel_mix_buffers: List[bytearray] = [bytearray() for _ in channel_configs]
        self.opus_decoder: Any = None
        self.aac_decoder: Any = None
        self.lc3_decoder: Any = None
        self.vad_gate: Any = None
        self.image_chunks: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self.last_image_chunk_cleanup = 0.0
        self.decode_failure_streak = 0
        self.decode_stream_reported = False
        self._unknown_prefix_streak = 0
        self.speaker_provider_epoch = SpeakerProviderEpoch()

    def _capture(self, method: str, *args: Any) -> None:
        """Keep optional dev capture out of the production audio failure domain."""
        capture = getattr(self.host, method, None)
        if not callable(capture):
            return
        try:
            capture(*args)
        except Exception as error:
            logger.warning('Listen parity capture failed method=%s type=%s', method, type(error).__name__)

    def _record_decode_failure(
        self, codec: str, error: BaseException, payload_len: int, channel: Optional[int] = None
    ) -> None:
        """Report an undecodable audio frame with enough detail to act on it.

        Dropping the frame keeps the socket alive, so an undecodable stream is a fail-open
        branch: the user records a whole session and gets no transcript, no ring buffer, and
        no mixed audio, while the only trace is one `type=OpusError` line per frame. That name
        cannot tell a corrupt client stream from a decoder the receiver sized wrong (#10701),
        so carry the codec's own message and the payload size, and once the streak proves the
        entire stream is failing, report it as the silent mic it is.
        """
        self.decode_failure_streak += 1
        logger.warning(
            'Listen audio frame decode failed codec=%s channel=%s type=%s bytes=%s streak=%s detail=%s',
            codec,
            channel,
            type(error).__name__,
            payload_len,
            self.decode_failure_streak,
            sanitize(error)[:120],
        )
        if self.decode_stream_reported or self.decode_failure_streak < DECODE_FAILURE_STREAK_ALERT:
            return
        self.decode_stream_reported = True
        record_fallback(
            component='silent_mic',
            from_mode=codec,
            to_mode='none',
            reason='capability_mismatch',
            outcome='exhausted',
        )

    def _serving_provider(self) -> str:
        """Resolve the provider actually serving this session, read at use time.

        ``_create_stt_socket`` can fall back from Parakeet to Modulate, so a
        value snapshotted before the socket exists attributes a Modulate
        failure to Parakeet (#11306).
        """
        return getattr(self.host.stt_service, 'value', self.host.stt_service)

    def _enqueue_stt_segments(self, segments: List[Dict[str, Any]], provider: Optional[str] = None) -> None:
        """Persist the provider epoch before local speaker numbers enter the conversation."""
        self._capture('capture_inbound_stt', segments)
        self.speaker_provider_epoch.stamp(segments, provider or self._serving_provider())
        self.host.transcripts.enqueue(segments)

    def _telemetry_platform(self) -> Any:
        """Platform label for listen funnel counters; never part of the audio failure domain."""

        return getattr(getattr(self.host, 'client_device_context', None), 'platform', None)

    def _mark_first_audio(self, now: float) -> None:
        """Record the funnel's first-audio transition once a frame was accepted.

        Called only after a frame passed channel-prefix validation and decoding,
        so a session of purely unknown-prefix or undecodable frames stays at zero
        audio and can still surface as a no-audio teardown. Reads defensively:
        funnel telemetry never belongs to the audio failure domain.
        """

        if getattr(self.host.state, 'first_audio_byte_timestamp', None) is not None:
            return

        self.host.state.first_audio_byte_timestamp = now
        self.host.state.last_usage_record_timestamp = now
        record_listen_audio_outcome(
            source=getattr(self.host.request, 'source', None),
            outcome='first_audio',
            platform=self._telemetry_platform(),
        )
        start_transcription = getattr(self.host, 'start_live_transcription', None)
        if callable(start_transcription):
            start_transcription()

    def initialize_decoders(self) -> None:
        request = self.host.request
        if self.host.is_multi_channel:
            if request.codec == 'opus':
                self.multi_opus_decoders = [
                    _get_opuslib().Decoder(request.sample_rate, 1) for _ in self.channel_configs
                ]
            return
        if request.codec == 'opus':
            self.opus_decoder = _get_opuslib().Decoder(request.sample_rate, 1)
        elif request.codec == 'aac':
            self.aac_decoder = AACDecoder(
                uid=request.uid,
                session_id=self.host.session_id,
                sample_rate=request.sample_rate,
                channels=request.channels,
            )
        elif request.codec == 'lc3':
            self.lc3_decoder = _get_lc3().Decoder(self.host.lc3_frame_duration_us, request.sample_rate)

    async def _create_stt_socket(self, callback: Any, sample_rate: int, modulate_callback: Any = None) -> Any:
        keywords = self.host.vocabulary[:100] if self.host.vocabulary else []
        if self.host.stt_service == STTService.parakeet:
            socket, actual_service = await connect_stt_socket_with_fallback(
                primary_service=STTService.parakeet,
                connect_primary=lambda: process_audio_parakeet(
                    callback,
                    self.host.stt_language,
                    sample_rate,
                    1,
                    model=self.host.stt_model,
                    keywords=keywords,
                    is_active=lambda: self.host.state.active,
                ),
                connect_modulate=lambda: process_audio_modulate(
                    modulate_callback or callback,
                    sample_rate,
                    self.host.stt_language,
                ),
            )
            self.host.stt_service = actual_service
            if actual_service == STTService.modulate:
                self.host.stt_model = 'velma-2'
            return socket
        if self.host.stt_service == STTService.soniox:
            # Soniox identifies language itself, so no language gate on the fallbacks;
            # they inherit the same chain a Modulate primary uses.
            dg_fallback_model = deepgram_fallback_model(self.host.stt_language)

            def connect_deepgram_from_soniox() -> Any:
                return process_audio_dg(
                    callback,
                    self.host.stt_language,
                    sample_rate,
                    1,
                    model=cast(str, dg_fallback_model),
                    keywords=keywords,
                    is_active=lambda: self.host.state.active,
                )

            socket, actual_service = await connect_stt_socket_with_fallback(
                primary_service=STTService.soniox,
                connect_primary=lambda: process_audio_soniox(
                    modulate_callback or callback,
                    sample_rate,
                    self.host.stt_language,
                ),
                connect_modulate=(
                    (
                        lambda: process_audio_modulate(
                            modulate_callback or callback,
                            sample_rate,
                            self.host.stt_language,
                        )
                    )
                    if modulate_is_configured_fallback(self.host.stt_language)
                    else None
                ),
                connect_deepgram=connect_deepgram_from_soniox if dg_fallback_model else None,
            )
            self.host.stt_service = actual_service
            if actual_service == STTService.modulate:
                self.host.stt_model = 'velma-2'
            elif actual_service == STTService.deepgram:
                self.host.stt_model = cast(str, dg_fallback_model)
            return socket
        if self.host.stt_service == STTService.modulate:
            # Velma-2 accepts the upgrade and only then reports being over quota,
            # so a Modulate primary needs the same chain its siblings use (#11752).
            dg_fallback_model = deepgram_fallback_model(self.host.stt_language)

            def connect_deepgram_fallback() -> Any:
                return process_audio_dg(
                    callback,
                    self.host.stt_language,
                    sample_rate,
                    1,
                    model=cast(str, dg_fallback_model),
                    keywords=keywords,
                    is_active=lambda: self.host.state.active,
                )

            def connect_parakeet_fallback() -> Any:
                return process_audio_parakeet(
                    callback,
                    self.host.stt_language,
                    sample_rate,
                    1,
                    model='parakeet',
                    keywords=keywords,
                    is_active=lambda: self.host.state.active,
                )

            socket, actual_service = await connect_stt_socket_with_fallback(
                primary_service=STTService.modulate,
                connect_primary=lambda: process_audio_modulate(
                    modulate_callback or callback,
                    sample_rate,
                    self.host.stt_language,
                ),
                connect_deepgram=connect_deepgram_fallback if dg_fallback_model else None,
                connect_parakeet=(
                    connect_parakeet_fallback if parakeet_is_configured_fallback(self.host.stt_language) else None
                ),
            )
            self.host.stt_service = actual_service
            if actual_service == STTService.deepgram:
                self.host.stt_model = cast(str, dg_fallback_model)
            elif actual_service == STTService.parakeet:
                self.host.stt_model = 'parakeet'
            return socket
        if self.host.stt_service == STTService.deepgram:

            def connect_deepgram() -> Any:
                return process_audio_dg(
                    callback,
                    self.host.stt_language,
                    sample_rate,
                    1,
                    model=self.host.stt_model,
                    keywords=keywords,
                    is_active=lambda: self.host.state.active,
                )

            if not modulate_is_configured_fallback(self.host.stt_language):
                return await connect_deepgram()

            def connect_parakeet() -> Any:
                return process_audio_parakeet(
                    callback,
                    self.host.stt_language,
                    sample_rate,
                    1,
                    model='parakeet',
                    keywords=keywords,
                    is_active=lambda: self.host.state.active,
                )

            socket, actual_service = await connect_stt_socket_with_fallback(
                primary_service=STTService.deepgram,
                connect_primary=connect_deepgram,
                connect_modulate=lambda: process_audio_modulate(
                    modulate_callback or callback,
                    sample_rate,
                    self.host.stt_language,
                ),
                connect_parakeet=(
                    connect_parakeet if parakeet_is_configured_fallback(self.host.stt_language) else None
                ),
            )
            self.host.stt_service = actual_service
            if actual_service == STTService.modulate:
                self.host.stt_model = 'velma-2'
            elif actual_service == STTService.parakeet:
                self.host.stt_model = 'parakeet'
            return socket
        raise RuntimeError(f'Unsupported serving STT provider {self.host.stt_service!r}')

    async def _drain_stt_sockets(self) -> None:
        sockets = self.stt_sockets_multi if self.host.is_multi_channel else [self.stt_socket]
        for socket in sockets:
            target = socket._conn if isinstance(socket, GatedSTTSocket) else socket  # type: ignore[reportPrivateUsage]
            if target is None:
                continue
            try:
                drain = getattr(target, 'drain_and_close', None)
                if callable(drain):
                    await cast(Any, drain)()
                else:
                    target.finish()
            except Exception as error:
                logger.error('Listen STT drain failure type=%s', type(error).__name__)
                try:
                    target.finish()
                except Exception:
                    pass
        self.stt_socket = None
        self.stt_sockets_multi = [None] * len(self.channel_configs)

    async def initialize_stt(self) -> bool:
        request = self.host.request
        if self.host.use_custom_stt:
            return True
        try:
            if self.host.is_multi_channel:
                for index, config in enumerate(self.channel_configs):

                    def callback(segments: List[Dict[str, Any]], channel: ChannelConfig = config) -> None:
                        for segment in segments:
                            segment['is_user'] = channel.is_user
                            segment['speaker_identity_status'] = (
                                SpeakerIdentityStatus.user.value
                                if channel.is_user
                                else SpeakerIdentityStatus.not_user.value
                            )
                            segment['speaker'] = channel.speaker_label
                        self._enqueue_stt_segments(segments)

                    socket = await self._create_stt_socket(callback, TARGET_SAMPLE_RATE)
                    if socket is None:
                        await self._drain_stt_sockets()
                        await terminate_live_stt_session(
                            request.websocket,
                            self.host.state,
                            failure=live_stt_upstream_failure(self._serving_provider()),
                            reason='initialization_failed',
                            platform=self.host.client_device_context.platform,
                        )
                        return False
                    self.stt_sockets_multi[index] = socket
                return True
            if should_initialize_vad_gate(override=request.vad_gate_override, global_gate_enabled=is_gate_enabled()):
                try:
                    self.vad_gate = VADStreamingGate(
                        sample_rate=request.sample_rate,
                        channels=1,
                        mode=vad_gate_mode(override=request.vad_gate_override, default_mode=VAD_GATE_MODE),
                        uid=request.uid,
                        session_id=self.host.session_id,
                    )
                except Exception:
                    logger.exception('VAD gate initialization failed; continuing without it')

            def capture_and_enqueue(segments: List[Dict[str, Any]]) -> None:
                self._enqueue_stt_segments(segments)

            parakeet_callback = make_stream_callback(capture_and_enqueue, self.vad_gate, False)
            modulate_callback = make_stream_callback(capture_and_enqueue, self.vad_gate, True)
            raw = await self._create_stt_socket(
                parakeet_callback,
                request.sample_rate,
                modulate_callback=modulate_callback,
            )
            if raw is None:
                await self._drain_stt_sockets()
                await terminate_live_stt_session(
                    request.websocket,
                    self.host.state,
                    failure=live_stt_upstream_failure(self._serving_provider()),
                    reason='initialization_failed',
                    platform=self.host.client_device_context.platform,
                )
                return False
            passthrough = self.host.stt_service == STTService.modulate
            self.stt_socket = (
                GatedSTTSocket(raw, gate=self.vad_gate, passthrough_audio=passthrough) if self.vad_gate else raw
            )
            # Retained so a mid-session failover can rebuild the socket against the
            # next provider without re-deriving the callbacks or the gate.
            self._stt_rebuild = (parakeet_callback, modulate_callback, request.sample_rate)
            self.host.spawn(self._monitor_stt_death(), name='stt_death_monitor')
            return True
        except Exception as error:
            await self._drain_stt_sockets()
            await terminate_live_stt_session(
                request.websocket,
                self.host.state,
                failure=live_stt_initialization_failure(error, self._serving_provider()),
                reason='initialization_failed',
                platform=self.host.client_device_context.platform,
            )
            return False

    async def _failover_stt_socket(self) -> bool:
        """Move a live session onto the next provider after its socket died.

        Modulate accepts the WebSocket and only then sends an error frame, so its
        outages land mid-session where ``connect_stt_socket_with_fallback`` — which
        only runs at connect time — cannot help. Without this the chain is inert
        against the failure it exists for: during the 2026-08-30 outage Velma failed
        82% of sessions while Soniox and Deepgram served zero.

        Single-channel only. Multi-channel holds several sockets whose segments are
        stitched by channel, so swapping one mid-stream needs its own design.

        Serialized: the death monitor and the audio send path can observe the same
        death within milliseconds of each other, and the loser of the lock must
        adopt the winner's replacement instead of burning another chain slot on a
        second rebuild.
        """
        async with self._stt_failover_lock:
            if self.stt_socket is not None and not live_stt_socket_is_dead(self.stt_socket):
                return True
            return await self._rebuild_stt_socket_locked()

    async def _rebuild_stt_socket_locked(self) -> bool:
        rebuild = getattr(self, '_stt_rebuild', None)
        if rebuild is None or self.host.is_multi_channel or self.host.use_custom_stt:
            return False
        if not self.host.state.active or self.host.state.stt_terminal_failure:
            return False

        dead_provider = provider_for_service(self.host.stt_service)
        if dead_provider:
            self._stt_failed_providers.add(dead_provider)
        if len(self._stt_failed_providers) > MAX_STT_FAILOVERS:
            return False
        # A provider-level typed rejection (Soniox 402 balance-exhausted) is
        # fleet-level evidence the failover would otherwise swallow: the session
        # survives on the next provider, so the terminal path that normally
        # feeds the selection circuit never runs for it, and the NEXT session is
        # handed straight back to the provider that refuses every stream.
        note_typed_provider_death(self.stt_socket, dead_provider)

        service, language, model = get_stt_service_for_language(
            self.host.language,
            multi_lang_enabled=self.host.multi_lang_enabled,
            exclude=frozenset(self._stt_failed_providers),
        )
        if service is None:
            return False

        parakeet_callback, modulate_callback, sample_rate = rebuild
        previous = self.stt_socket
        self.host.stt_service, self.host.stt_language, self.host.stt_model = service, language, model
        try:
            raw = await self._create_stt_socket(
                parakeet_callback,
                sample_rate,
                modulate_callback=modulate_callback,
            )
        except Exception:
            logger.exception('STT failover connect raised')
            return False
        if raw is None:
            return False
        # A provider can accept the upgrade and reject the stream ~150ms later;
        # treating that as a heal would report recovery for a session that is
        # already dead again.
        if not await fallback_socket_is_serving(raw):
            close_rejected_socket(raw)
            return False

        passthrough = self.host.stt_service == STTService.modulate
        self.stt_socket = (
            GatedSTTSocket(raw, gate=self.vad_gate, passthrough_audio=passthrough) if self.vad_gate else raw
        )
        record_fallback(
            component='stt_live_session',
            from_mode=dead_provider or 'unknown',
            to_mode=service.value,
            reason='connection_lost',
            outcome='recovered',
        )
        logger.info(f'STT failover mid-session: {dead_provider} -> {service.value}')
        if previous is not None:
            try:
                previous.finish()
            except Exception:
                logger.warning('Failed to close the STT socket that died before failover')
        return True

    async def _monitor_stt_death(self) -> None:
        """Terminate the client session promptly when the provider STT socket dies.

        The receive loop only observes provider death while flushing a client
        audio buffer (``_flush_stt_buffer`` → ``live_stt_socket_is_dead``), so a
        clean upstream close with no further client audio could hold the mobile
        socket in the "Listening" state until the 300s ``ws_receive_timeout``.
        This frame-independent poll drives the same idempotent terminal path
        (``stt_failed`` + WebSocket 1011) as soon as the death latch flips (#10028).
        """
        while self.host.state.active and not self.host.state.stt_terminal_failure:
            socket = self.stt_socket
            if socket is not None and live_stt_socket_is_dead(socket):
                if await self._failover_stt_socket():
                    continue
                await terminate_live_stt_session(
                    self.host.request.websocket,
                    self.host.state,
                    failure=live_stt_upstream_failure(self._serving_provider()),
                    reason=live_stt_terminal_reason(socket, 'connection_lost'),
                    platform=self.host.client_device_context.platform,
                )
                return
            # Shutdown-aware sleep: wakes immediately on session shutdown, in
            # which case normal teardown owns termination and we simply exit.
            if await self.host.wait(STT_DEATH_POLL_INTERVAL_SECONDS):
                return

    def _cleanup_expired_image_chunks(self) -> None:
        now = time.time()
        if now - self.last_image_chunk_cleanup < self.host.limits.image_chunk_cleanup_interval:
            return
        self.last_image_chunk_cleanup = now
        expired = [
            temporary_id
            for temporary_id, data in self.image_chunks.items()
            if now - data['created_at'] > self.host.limits.image_chunk_ttl
        ]
        for temporary_id in expired:
            del self.image_chunks[temporary_id]

    async def _process_photo(self, image_b64: str, temporary_id: str) -> None:
        photo_id = str(uuid.uuid4())
        await self.host.asend_event(PhotoProcessingEvent(temp_id=temporary_id, photo_id=photo_id))
        try:
            description = await describe_image(self.host.request.uid, image_b64)
            discarded = not description or not description.strip()
        except Exception as error:
            logger.error('Image description failed type=%s', type(error).__name__)
            description, discarded = 'Could not generate description.', True
        self.host.transcripts.photo_buffer.append(
            ConversationPhoto(id=photo_id, base64=image_b64, description=description, discarded=discarded)
        )
        await self.host.asend_event(
            PhotoDescribedEvent(photo_id=photo_id, description=description, discarded=discarded)
        )

    async def _handle_image_chunk(self, payload: Dict[str, Any]) -> None:
        chunk = ImageChunkEnvelope.model_validate(payload)
        self._cleanup_expired_image_chunks()
        if chunk.id not in self.image_chunks:
            if len(self.image_chunks) >= self.host.limits.max_image_chunks:
                self.image_chunks.popitem(last=False)
            self.image_chunks[chunk.id] = {'chunks': [None] * chunk.total, 'created_at': time.time()}
        chunks = self.image_chunks[chunk.id]['chunks']
        chunk.validate_against_cached_total(len(chunks))
        if chunks[chunk.index] is None:
            chunks[chunk.index] = chunk.data
        if all(value is not None for value in chunks):
            image = ''.join(chunks)
            del self.image_chunks[chunk.id]
            self.host.spawn(self._process_photo(image, chunk.id), name='photo_process')

    async def _flush_stt_buffer(self, buffer: bytearray, *, force: bool = False) -> None:
        request = self.host.request
        # Bounded retry, not a single attempt: when the send path fails over to
        # the next provider the chunk is reported unsent with the buffer intact,
        # and it must reach the replacement socket now — the next client chunk
        # may be a VAD-gated silence away. `_failover_stt_socket` enforces
        # MAX_STT_FAILOVERS, so the bound here is a backstop, not the limit.
        for _ in range(MAX_STT_FAILOVERS + 2):
            socket_dead = self.stt_socket is not None and live_stt_socket_is_dead(self.stt_socket)
            decision = decide_stt_buffer_flush(
                buffer_len=len(buffer),
                flush_size=stt_buffer_flush_size(request.sample_rate),
                force=force,
                socket_dead=socket_dead,
                socket_available=self.stt_socket is not None,
                fair_use_dg_budget_exhausted=self.host.state.fair_use_dg_budget_exhausted,
                fair_use_track_dg_usage=self.host.state.fair_use_track_dg_usage,
                sample_rate=request.sample_rate,
            )
            if not decision.should_flush:
                return
            if self.host.state.fair_use_dg_budget_exhausted:
                buffer.clear()
                return
            outbound_audio = bytes(buffer)
            sent = await flush_live_stt_buffer(
                request.websocket,
                self.host.state,
                stt_socket=self.stt_socket,
                buffer=buffer,
                provider=self._serving_provider(),
                platform=self.host.client_device_context.platform,
                attempt_failover=self._failover_stt_socket,
            )
            if sent:
                self._capture('capture_outbound_stt', outbound_audio)
                self.host.state.dg_usage_ms_pending += decision.dg_usage_ms
                return
            if self.host.state.stt_terminal_failure:
                return

    async def _handle_multi_channel_audio(self, data: bytes, now: float | None = None) -> int:
        if now is None:
            now = time.time()
        request = self.host.request
        channel_index = self.channel_id_to_index.get(data[0])
        if channel_index is None:
            # A whole call's worth of frames can land here if a client prefixes
            # its channels differently than build_channel_config expects; that
            # used to be indistinguishable from silence, so count and log it.
            record_listen_unknown_channel_prefix(
                source=getattr(request, 'source', None),
                platform=self._telemetry_platform(),
            )
            self._unknown_prefix_streak += 1
            if self._unknown_prefix_streak <= 3 or self._unknown_prefix_streak % 100 == 0:
                logger.warning(
                    'Listen multi-channel frame dropped unknown prefix byte=%d frames=%s',
                    data[0],
                    self._unknown_prefix_streak,
                )
            return 0
        self._unknown_prefix_streak = 0
        audio = data[1:]
        if request.codec == 'opus' and self.multi_opus_decoders[channel_index]:
            try:
                audio = self.multi_opus_decoders[channel_index].decode(
                    bytes(audio), opus_decode_capacity(request.sample_rate)
                )
            except Exception as error:
                self._record_decode_failure('opus', error, len(audio), channel=channel_index)
                return 0
            self.decode_failure_streak = 0
            if not audio:
                return 0
        # First audio only counts once the channel prefix resolved and an opus
        # frame decoded; rejected frames above leave the no-audio funnel intact.
        self._mark_first_audio(now)
        pcm = resample_pcm(bytes(audio), request.sample_rate, TARGET_SAMPLE_RATE)
        self._capture('capture_client_audio', pcm)
        # Custom-STT clients own transcript production.  Their channel sockets are intentionally
        # absent, but captured audio still proceeds to the pusher mix path.
        if not self.host.use_custom_stt:
            should_send, dg_usage_ms = decide_multi_channel_stt_send(
                socket_available=bool(self.stt_sockets_multi[channel_index]),
                fair_use_dg_budget_exhausted=self.host.state.fair_use_dg_budget_exhausted,
                pcm_len=len(pcm),
                fair_use_track_dg_usage=self.host.state.fair_use_track_dg_usage,
            )
            if should_send:
                sent = await send_live_stt_audio(
                    request.websocket,
                    self.host.state,
                    stt_socket=self.stt_sockets_multi[channel_index],
                    audio=pcm,
                    provider=self._serving_provider(),
                    platform=self.host.client_device_context.platform,
                )
                if sent:
                    self._capture('capture_outbound_stt', pcm)
                    self.host.state.dg_usage_ms_pending += dg_usage_ms
        # Only accumulate channel audio for the pusher mix when an audio-bytes consumer is attached.
        # decide_multi_channel_mix and the teardown flush both gate on this same condition, so
        # without a consumer nothing ever drains these per-channel buffers. Appending regardless (the
        # old behavior) left them growing for the whole session (~64 KB/s for stereo) until the
        # worker ran out of memory, taking every co-located live session down with it.
        if self.host.audio_bytes_send is not None:
            self.channel_mix_buffers[channel_index].extend(pcm)
            decision = decide_multi_channel_mix(
                self.channel_mix_buffers, audio_bytes_enabled=self.host.audio_bytes_send is not None
            )
            if decision.should_mix:
                mixed = mix_n_channel_buffers(
                    [bytearray(buffer[: decision.min_len]) for buffer in self.channel_mix_buffers]
                )
                if mixed and self.host.audio_bytes_send is not None:
                    self.host.audio_bytes_send(mixed, self.host.state.last_audio_received_time or time.time())
                for buffer in self.channel_mix_buffers:
                    del buffer[: decision.min_len]

        return len(audio)

    async def _handle_text(self, message: str) -> None:
        try:
            loaded = json.loads(message)
        except json.JSONDecodeError:
            logger.info('Invalid listen text message: %s', sanitize(message))
            return

        payload = cast(Dict[str, Any], loaded) if isinstance(loaded, dict) else {}
        kind = payload.get('type')
        if kind == 'image_chunk':
            try:
                await self._handle_image_chunk(payload)
            except ValueError:
                self.host.state.close_code = 1008
                self.host.state.active = False
        elif kind == 'start_onboarding' and self.host.onboarding_handler:
            await self.host.onboarding_handler.start()
        elif kind == 'skip_question' and self.host.onboarding_handler and not self.host.onboarding_handler.completed:
            await self.host.onboarding_handler.skip_current_question()
        elif kind == 'suggested_transcript' and self.host.use_custom_stt:
            segments = payload.get('segments', [])
            provider = payload.get('stt_provider')
            self._enqueue_stt_segments(segments, provider=provider or 'custom')
        elif kind == 'speaker_assigned':
            await self._handle_speaker_assigned(payload)
        elif kind == 'finalization_reason':
            reason = payload.get('reason')
            if reason in {
                'user_stop',
                'finish_and_continue',
                'meeting_started',
                'meeting_ended',
                'max_duration_rotation',
                'crash_recovery',
                'retry',
            }:
                self.host.state.finalization_reason = reason

    async def _handle_speaker_assigned(self, payload: Dict[str, Any]) -> None:
        segment_ids = payload.get('segment_ids', [])
        speaker = self.host.speakers
        updated = update_speaker_assignment_maps(
            cast(int, payload.get('speaker_id')),
            cast(str, payload.get('person_id')),
            cast(str, payload.get('person_name')),
            segment_ids,
            speaker.speaker_to_person,
            speaker.segment_assignments,
        )
        if not updated:
            return
        if (
            payload.get('person_id')
            and payload.get('person_id') != 'user'
            and self.host.private_cloud_sync_enabled
            and self.host.send_speaker_sample_request
            and self.host.state.current_conversation_id
            and any(self.host.transcripts.current_session_segments.get(segment_id) for segment_id in segment_ids)
        ):
            self.host.spawn(
                self.host.send_speaker_sample_request(
                    person_id=payload['person_id'],
                    conv_id=self.host.state.current_conversation_id,
                    segment_ids=segment_ids,
                ),
                name='speaker_sample_request',
            )

    async def receive_data(self) -> None:
        request = self.host.request
        buffer = bytearray()
        decoded_audio_bytes = 0
        self.host.state.last_audio_received_time = time.time()
        self.host.state.last_activity_time = self.host.state.last_audio_received_time
        try:
            while self.host.state.active:
                try:
                    message = await asyncio.wait_for(
                        request.websocket.receive(), timeout=self.host.limits.ws_receive_timeout
                    )
                except asyncio.TimeoutError:
                    break
                self.host.state.last_activity_time = time.time()
                if message.get('type') == 'websocket.disconnect':
                    self.host.state.close_code = message.get('code', 1000)
                    break
                data = message.get('bytes')
                if data is not None:
                    if len(data) <= 2:
                        continue
                    now = time.time()
                    self.host.state.last_audio_received_time = now
                    if self.host.is_multi_channel:
                        # `_handle_multi_channel_audio` marks first audio only
                        # after the channel prefix is known-good (and an opus
                        # frame decoded), so unknown-prefix frames leave the
                        # session eligible for a no_audio teardown.
                        decoded_audio_bytes += await self._handle_multi_channel_audio(data, now)
                        continue
                    try:
                        decoded: bytes = data
                        if request.codec == 'opus':
                            decoded = self.opus_decoder.decode(
                                bytes(data), frame_size=opus_decode_capacity(request.sample_rate)
                            )
                        elif request.codec == 'aac':
                            decoded = self.aac_decoder.decode(bytes(data))
                        elif request.codec == 'lc3':
                            decoded = self.lc3_decoder.decode(bytes(data), bit_depth=16)
                        elif request.codec == 'pcm8':
                            decoded = audioop.lin2lin(audioop.bias(data, 1, -128), 1, 2)
                    except Exception as error:
                        self._record_decode_failure(request.codec, error, len(data))
                        continue
                    self.decode_failure_streak = 0
                    if not decoded:
                        continue
                    self._mark_first_audio(now)
                    decoded_audio_bytes += len(decoded)
                    self._capture('capture_client_audio', decoded)
                    if self.host.state.audio_ring_buffer is not None:
                        self.host.state.audio_ring_buffer.write(decoded, now)
                    if not self.host.use_custom_stt:
                        buffer.extend(decoded)
                        await self._flush_stt_buffer(buffer)
                    if self.host.audio_bytes_send is not None:
                        self.host.audio_bytes_send(decoded, now)
                elif message.get('text') is not None:
                    await self._handle_text(message['text'])
        except WebSocketDisconnect:
            pass
        except Exception as error:
            logger.error('Listen receive failure type=%s', type(error).__name__)
            self.host.state.close_code = 1011
        finally:
            if decoded_audio_bytes:
                sample_rate = max(1, int(getattr(request, 'sample_rate', 16000)))
                emit_product_event(
                    uid=str(getattr(request, 'uid', '') or ''),
                    event='Encoded Audio Duration Measured',
                    properties={
                        'recording_id': getattr(self.host, 'recording_session_id', None),
                        'conversation_id': getattr(self.host.state, 'current_conversation_id', None),
                        'codec': request.codec,
                        'decoded_audio_bytes': decoded_audio_bytes,
                        'duration_seconds': decoded_audio_bytes / (sample_rate * 2),
                    },
                )
            if self.vad_gate is not None:
                vad_metrics = self.vad_gate.get_metrics()
                logger.info(json.dumps(self.vad_gate.to_json_log()))
                speech_ms = max(0, int(vad_metrics.get('speech_ms_total') or 0))
                if speech_ms:
                    emit_product_event(
                        uid=str(getattr(request, 'uid', '') or ''),
                        event='Speech Positive Duration Measured',
                        properties={
                            'recording_id': getattr(self.host, 'recording_session_id', None),
                            'conversation_id': getattr(self.host.state, 'current_conversation_id', None),
                            'duration_seconds': speech_ms / 1000,
                            'measurement': 'server_vad',
                            'vad_mode': vad_metrics.get('mode') or 'unknown',
                        },
                    )
            if not self.host.use_custom_stt:
                await self._flush_stt_buffer(buffer, force=True)
            await self._drain_stt_sockets()
            self.host.state.active = False

    async def flush_multi_channel_tail(self) -> None:
        if not should_flush_final_multi_channel_mix(
            is_multi_channel=self.host.is_multi_channel,
            audio_bytes_enabled=self.host.audio_bytes_send is not None,
            buffers=self.channel_mix_buffers,
        ):
            return
        mixed = mix_n_channel_buffers(self.channel_mix_buffers)
        if mixed and self.host.audio_bytes_send is not None:
            self.host.audio_bytes_send(mixed, time.time())
        for buffer in self.channel_mix_buffers:
            buffer.clear()

    def finish(self) -> None:
        for socket in self.stt_sockets_multi if self.host.is_multi_channel else [self.stt_socket]:
            if socket:
                socket.finish()

    def clear(self) -> None:
        self.image_chunks.clear()

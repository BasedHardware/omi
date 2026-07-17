"""Inbound listen WebSocket frames, audio decoding, and image assembly."""

from __future__ import annotations

import asyncio
import audioop
import json
import logging
import time
import uuid
from collections import OrderedDict
from typing import Any, Dict, List, Optional, cast

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
from utils.aac import AACDecoder
from utils.llm.openglass import describe_image
from utils.request_validation import ImageChunkEnvelope
from utils.speaker_assignment import update_speaker_assignment_maps
from utils.stt.live_failure import (
    flush_live_stt_buffer,
    live_stt_initialization_failure,
    live_stt_socket_is_dead,
    live_stt_upstream_failure,
    send_live_stt_audio,
    terminate_live_stt_session,
)
from utils.stt.streaming import (
    STTService,
    make_stream_callback,
    process_audio_modulate,
    process_audio_parakeet,
)
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

logger = logging.getLogger(__name__)


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
        self.stt_sockets_multi: List[Any] = [None] * len(channel_configs)
        self.multi_opus_decoders: List[Any] = [None] * len(channel_configs)
        self.channel_mix_buffers: List[bytearray] = [bytearray() for _ in channel_configs]
        self.opus_decoder: Any = None
        self.aac_decoder: Any = None
        self.lc3_decoder: Any = None
        self.vad_gate: Any = None
        self.image_chunks: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self.last_image_chunk_cleanup = 0.0

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

    async def _create_stt_socket(self, callback: Any, sample_rate: int) -> Any:
        keywords = self.host.vocabulary[:100] if self.host.vocabulary else []
        if self.host.stt_service == STTService.parakeet:
            return await process_audio_parakeet(
                callback,
                self.host.stt_language,
                sample_rate,
                1,
                model=self.host.stt_model,
                keywords=keywords,
                is_active=lambda: self.host.state.active,
            )
        if self.host.stt_service == STTService.modulate:
            return await process_audio_modulate(callback, sample_rate, self.host.stt_language)
        raise RuntimeError(f'Unsupported serving STT provider {self.host.stt_service!r}')

    async def initialize_stt(self) -> bool:
        request = self.host.request
        provider = getattr(self.host.stt_service, 'value', self.host.stt_service)
        if self.host.use_custom_stt:
            return True
        try:
            if self.host.is_multi_channel:
                for index, config in enumerate(self.channel_configs):

                    def callback(segments: List[Dict[str, Any]], channel: ChannelConfig = config) -> None:
                        for segment in segments:
                            segment['is_user'] = channel.is_user
                            segment['speaker'] = channel.speaker_label
                        self.host.transcripts.enqueue(segments)

                    socket = await self._create_stt_socket(callback, TARGET_SAMPLE_RATE)
                    if socket is None:
                        await terminate_live_stt_session(
                            request.websocket,
                            self.host.state,
                            failure=live_stt_upstream_failure(provider),
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
            passthrough = self.host.stt_service == STTService.modulate
            raw = await self._create_stt_socket(
                make_stream_callback(self.host.transcripts.enqueue, self.vad_gate, passthrough), request.sample_rate
            )
            if raw is None:
                await terminate_live_stt_session(
                    request.websocket,
                    self.host.state,
                    failure=live_stt_upstream_failure(provider),
                    reason='initialization_failed',
                    platform=self.host.client_device_context.platform,
                )
                return False
            self.stt_socket = (
                GatedSTTSocket(raw, gate=self.vad_gate, passthrough_audio=passthrough) if self.vad_gate else raw
            )
            return True
        except Exception as error:
            await terminate_live_stt_session(
                request.websocket,
                self.host.state,
                failure=live_stt_initialization_failure(error, provider),
                reason='initialization_failed',
                platform=self.host.client_device_context.platform,
            )
            return False

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
        sent = await flush_live_stt_buffer(
            request.websocket,
            self.host.state,
            stt_socket=self.stt_socket,
            buffer=buffer,
            provider=getattr(self.host.stt_service, 'value', self.host.stt_service),
            platform=self.host.client_device_context.platform,
        )
        if sent:
            self.host.state.dg_usage_ms_pending += decision.dg_usage_ms

    async def _handle_multi_channel_audio(self, data: bytes) -> None:
        request = self.host.request
        channel_index = self.channel_id_to_index.get(data[0])
        if channel_index is None:
            return
        audio = data[1:]
        if request.codec == 'opus' and self.multi_opus_decoders[channel_index]:
            try:
                audio = self.multi_opus_decoders[channel_index].decode(bytes(audio), request.sample_rate // 50)
            except Exception as error:
                logger.warning(
                    'Listen audio frame decode failed codec=opus channel=%s type=%s',
                    channel_index,
                    type(error).__name__,
                )
                return
            if not audio:
                return
        pcm = resample_pcm(bytes(audio), request.sample_rate, TARGET_SAMPLE_RATE)
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
                    provider=getattr(self.host.stt_service, 'value', self.host.stt_service),
                    platform=self.host.client_device_context.platform,
                )
                if sent:
                    self.host.state.dg_usage_ms_pending += dg_usage_ms
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
        elif kind == 'skip_question' and self.host.onboarding_handler and not self.host.onboarding_handler.completed:
            await self.host.onboarding_handler.skip_current_question()
        elif kind == 'suggested_transcript' and self.host.use_custom_stt:
            segments = payload.get('segments', [])
            provider = payload.get('stt_provider')
            if provider:
                for segment in segments:
                    segment['stt_provider'] = provider
            self.host.transcripts.enqueue(segments)
        elif kind == 'speaker_assigned':
            await self._handle_speaker_assigned(payload)

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
                    if self.host.state.first_audio_byte_timestamp is None:
                        self.host.state.first_audio_byte_timestamp = now
                        self.host.state.last_usage_record_timestamp = now
                    if self.host.is_multi_channel:
                        await self._handle_multi_channel_audio(data)
                        continue
                    try:
                        decoded: bytes = data
                        if request.codec == 'opus':
                            decoded = self.opus_decoder.decode(bytes(data), frame_size=self.host.frame_size)
                        elif request.codec == 'aac':
                            decoded = self.aac_decoder.decode(bytes(data))
                        elif request.codec == 'lc3':
                            decoded = self.lc3_decoder.decode(bytes(data), bit_depth=16)
                        elif request.codec == 'pcm8':
                            decoded = audioop.lin2lin(audioop.bias(data, 1, -128), 1, 2)
                    except Exception as error:
                        logger.warning(
                            'Listen audio frame decode failed codec=%s type=%s', request.codec, type(error).__name__
                        )
                        continue
                    if not decoded:
                        continue
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
            if self.vad_gate is not None:
                logger.info(json.dumps(self.vad_gate.to_json_log()))
            if not self.host.use_custom_stt:
                await self._flush_stt_buffer(buffer, force=True)
            try:
                sockets = self.stt_sockets_multi if self.host.is_multi_channel else [self.stt_socket]
                for socket in sockets:
                    target = socket._conn if isinstance(socket, GatedSTTSocket) else socket  # type: ignore[reportPrivateUsage]
                    if target and hasattr(target, 'drain_and_close'):
                        await cast(Any, target).drain_and_close()
            except Exception as error:
                logger.error('Listen STT drain failure type=%s', type(error).__name__)
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

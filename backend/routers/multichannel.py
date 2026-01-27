import asyncio
import os
import struct as struct_mod
import time
import uuid as uuid_mod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

import opuslib

from fastapi import APIRouter, Depends, Query
from fastapi.websockets import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

import database.conversations as conversations_db
import database.users as users_db
from database import redis_db
from database.users import get_user_transcription_preferences
from models.conversation import (
    Conversation,
    ConversationSource,
    ConversationStatus,
    Structured,
    TranscriptSegment,
)
from models.message_event import MessageEvent
from utils.apps import is_audio_bytes_app_enabled
from utils.other import endpoints as auth
from utils.other.storage import upload_audio_chunk
from utils.stt.streaming import process_audio_dg, get_stt_service_for_language, STTService
from utils.streaming.conversation_manager import create_in_progress_conversation, process_completed_conversation
from utils.streaming.pusher_handler import PusherHandler
from utils.streaming.translator import translate_segments
from utils.streaming.usage_tracker import UsageTracker
from utils.translation import TranslationService
from utils.translation_cache import TranscriptSegmentLanguageCache
from utils.webhooks import get_audio_bytes_webhook_seconds

router = APIRouter()

# ---- Constants ----

PUSHER_ENABLED = bool(os.getenv('HOSTED_PUSHER_API_URL'))
TARGET_SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2
CHUNK_DURATION_SECONDS = 5
CHUNK_UPLOAD_MAX_RETRIES = 3


# ---- Channel Configuration ----


@dataclass
class ChannelConfig:
    channel_id: int  # Wire protocol ID (1-indexed: 0x01, 0x02, ...)
    label: str  # Human-readable label
    is_user: bool  # Whether this channel represents the user's voice
    speaker_label: str  # STT speaker label


def build_channel_config(source: str, num_channels: int) -> List[ChannelConfig]:
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
    # Generic N-channel
    configs = []
    for i in range(num_channels):
        configs.append(
            ChannelConfig(
                channel_id=i + 1,
                label=f'channel_{i}',
                is_user=(i == 0),
                speaker_label=f'SPEAKER_{i:02d}',
            )
        )
    return configs


# ---- Audio Helpers ----


def mix_n_channel_buffers(buffers: List[bytearray]) -> bytes:
    """Mix N 16-bit PCM mono buffers sample-by-sample, clamping to int16 range."""
    max_len = max((len(b) for b in buffers), default=0)
    if max_len == 0:
        return b''
    # Make even
    max_len = max_len - (max_len % 2)
    padded = [b + bytearray(max_len - len(b)) for b in buffers]
    num_samples = max_len // 2
    channel_samples = [struct_mod.unpack(f'<{num_samples}h', p[:max_len]) for p in padded]
    mixed = []
    for i in range(num_samples):
        s = sum(ch[i] for ch in channel_samples)
        mixed.append(max(-32768, min(32767, s)))
    return struct_mod.pack(f'<{num_samples}h', *mixed)


# ---- WebSocket Endpoint ----


@router.websocket("/v1/listen/multi")
async def multi_channel_listen(
    websocket: WebSocket,
    uid: str = Depends(auth.get_current_user_uid),
    source: str = Query(...),
    language: str = Query(default='en'),
    sample_rate: int = Query(default=48000),
    codec: str = Query(default='pcm'),
    channels: int = Query(default=2),
    call_id: Optional[str] = Query(default=None),
):
    """
    Multi-channel audio transcription WebSocket.

    Protocol:
    - Client sends: [1 byte channel_id] + [audio bytes]
    - Channel IDs are 1-indexed (0x01, 0x02, ...)
    - Server sends: JSON transcript events with is_user flag
    """
    print(
        f"multi_channel_listen: uid={uid}, source={source}, language={language}, "
        f"sample_rate={sample_rate}, codec={codec}, channels={channels}, call_id={call_id}"
    )

    try:
        await websocket.accept()
    except RuntimeError as e:
        print(f"multi_channel_listen: accept error: {e}")
        return

    await _multi_channel_stream_handler(websocket, uid, source, language, sample_rate, codec, channels, call_id)
    print(f"multi_channel_listen ended: uid={uid}, source={source}")


async def _multi_channel_stream_handler(
    websocket: WebSocket,
    uid: str,
    source: str,
    language: str,
    sample_rate: int,
    codec: str,
    num_channels: int,
    call_id: Optional[str],
):
    session_id = str(uuid_mod.uuid4())
    websocket_active = True
    call_start_time = time.time()
    main_event_loop = asyncio.get_running_loop()

    # ---- Channel config ----
    channel_configs = build_channel_config(source, num_channels)
    channel_id_to_index = {ch.channel_id: i for i, ch in enumerate(channel_configs)}

    # ---- Conversation source ----
    try:
        conversation_source = ConversationSource(source)
    except ValueError:
        print(f"multi_channel: invalid source '{source}', defaulting to 'omi'", uid, session_id)
        conversation_source = ConversationSource.omi

    # ---- Private cloud sync ----
    private_cloud_sync_enabled = users_db.get_user_private_cloud_sync_enabled(uid)

    # ---- Message event helper ----
    def send_message_event(event: MessageEvent):
        if websocket_active and websocket.client_state == WebSocketState.CONNECTED:
            try:
                asyncio.run_coroutine_threadsafe(
                    websocket.send_json(event.to_json() if hasattr(event, 'to_json') else event.dict()),
                    main_event_loop,
                )
            except Exception as e:
                print(f"multi_channel: send_message_event error: {e}", uid, session_id)

    # ---- Usage tracking ----
    usage_tracker = UsageTracker(
        uid=uid,
        session_id=session_id,
        send_message_event=send_message_event,
        is_active=lambda: websocket_active,
    )
    usage_tracker.check_initial_credits()

    # ---- Transcription preferences ----
    transcription_prefs = get_user_transcription_preferences(uid)
    single_language_mode = transcription_prefs.get('single_language_mode', False)

    # Convert 'auto' to 'multi' for consistency
    lang = 'multi' if language == 'auto' else language

    stt_service, stt_language, stt_model = get_stt_service_for_language(
        lang, multi_lang_enabled=not single_language_mode
    )
    if not stt_service or not stt_language:
        await websocket.close(code=1008, reason=f"Language not supported: {language}")
        return

    # ---- Translation setup ----
    translation_language = None
    if not single_language_mode:
        if stt_language == 'multi':
            if lang == 'multi':
                user_language_preference = users_db.get_user_language_preference(uid)
                if user_language_preference:
                    translation_language = user_language_preference
            else:
                translation_language = lang

    translation_service = TranslationService()
    language_cache = TranscriptSegmentLanguageCache()
    translation_enabled = translation_language is not None

    # ---- Audio state ----
    # Per-channel chunk buffers for mixing before upload
    channel_chunk_buffers = [bytearray() for _ in channel_configs]
    chunk_upload_queue: List[dict] = []
    chunk_timestamps: List[float] = []
    last_chunk_time = time.time()

    # Per-channel opus decoders
    opus_decoders: List[Optional[opuslib.Decoder]] = []
    for _ in channel_configs:
        if codec == 'opus':
            opus_decoders.append(opuslib.Decoder(sample_rate, 1))
        else:
            opus_decoders.append(None)

    # ---- Transcript state ----
    transcript_segments: List[dict] = []
    realtime_segment_buffers: List[dict] = []

    # ---- STT connections (one per channel) ----
    stt_sockets: list = [None] * len(channel_configs)

    def make_transcript_callback(ch_index: int, ch_config: ChannelConfig):
        def callback(segments: list):
            nonlocal transcript_segments
            for seg in segments:
                seg['is_user'] = ch_config.is_user
                seg['speaker'] = ch_config.speaker_label
                transcript_segments.append(seg)
            realtime_segment_buffers.extend(segments)
            usage_tracker.on_transcript_received()

        return callback

    try:
        for i, ch_config in enumerate(channel_configs):
            callback = make_transcript_callback(i, ch_config)
            if stt_service == STTService.deepgram:
                stt_sockets[i] = await process_audio_dg(
                    callback, stt_language, TARGET_SAMPLE_RATE, 1, preseconds=0, model=stt_model
                )
            else:
                # Fallback to Deepgram
                stt_sockets[i] = await process_audio_dg(
                    callback, 'en', TARGET_SAMPLE_RATE, 1, preseconds=0, model='nova-3'
                )
    except Exception as e:
        print(f"multi_channel: failed to connect STT: {e}", uid, session_id)
        await websocket.close(code=1011, reason="Failed to connect to transcription service")
        return

    print(f"multi_channel: STT connections established ({len(channel_configs)} channels)", uid, session_id)

    # ---- Create conversation ----
    conversation_id = await create_in_progress_conversation(
        uid=uid,
        language=language,
        source=conversation_source,
        private_cloud_sync_enabled=private_cloud_sync_enabled,
        session_id=session_id,
        check_calendar=(source == 'desktop'),
        conversation_id=call_id,
    )

    # ---- Pusher ----
    pusher_handler = None
    if PUSHER_ENABLED:
        audio_webhook_seconds = get_audio_bytes_webhook_seconds(uid)
        audio_app_enabled = is_audio_bytes_app_enabled(uid)

        pusher_handler = PusherHandler(
            uid=uid,
            session_id=session_id,
            language=language,
            sample_rate=TARGET_SAMPLE_RATE,
            is_active=lambda: websocket_active,
            get_current_conversation_id=lambda: conversation_id,
            on_conversation_processed=lambda cid: print(
                f"multi_channel: conversation processed: {cid}", uid, session_id
            ),
            private_cloud_sync_enabled=private_cloud_sync_enabled,
            audio_bytes_webhook_seconds=audio_webhook_seconds,
            audio_bytes_app_enabled=audio_app_enabled,
        )
        await pusher_handler.connect()
        if not pusher_handler.is_connected():
            print(f"multi_channel: pusher connection failed", uid, session_id)
            # Continue without pusher — will fallback to local processing

    # ---- Audio processing helpers ----

    def decode_audio(data: bytes, opus_decoder) -> bytes:
        """Decode audio from codec to PCM16."""
        if codec == 'opus' and opus_decoder:
            try:
                frame_size = sample_rate // 50  # 20ms frames
                pcm = opus_decoder.decode(data, frame_size)
                return pcm
            except Exception:
                return data
        return data

    def resample_if_needed(pcm_data: bytes, source_rate: int, target_rate: int) -> bytes:
        """Simple resampling by sample duplication/decimation."""
        if source_rate == target_rate:
            return pcm_data
        num_samples = len(pcm_data) // 2
        if num_samples == 0:
            return pcm_data
        samples = struct_mod.unpack(f'<{num_samples}h', pcm_data)
        ratio = target_rate / source_rate
        new_length = int(num_samples * ratio)
        resampled = []
        for i in range(new_length):
            src_idx = min(int(i / ratio), num_samples - 1)
            resampled.append(samples[src_idx])
        return struct_mod.pack(f'<{len(resampled)}h', *resampled)

    # ---- Background tasks ----

    async def process_chunk_uploads():
        """Upload mixed audio chunks to storage."""
        nonlocal websocket_active, chunk_upload_queue
        while websocket_active or len(chunk_upload_queue) > 0:
            if len(chunk_upload_queue) == 0:
                await asyncio.sleep(1)
                continue

            chunks_to_process = chunk_upload_queue.copy()
            chunk_upload_queue = []

            for chunk_info in chunks_to_process:
                try:
                    await asyncio.to_thread(
                        upload_audio_chunk,
                        chunk_info['data'],
                        uid,
                        conversation_id,
                        chunk_info['timestamp'],
                    )
                    chunk_timestamps.append(chunk_info['timestamp'])
                except Exception as e:
                    print(f"multi_channel: chunk upload failed: {e}", uid, session_id)
                    retries = chunk_info.get('retries', 0)
                    if retries < CHUNK_UPLOAD_MAX_RETRIES:
                        chunk_info['retries'] = retries + 1
                        chunk_upload_queue.append(chunk_info)

            await asyncio.sleep(0.5)

    async def heartbeat():
        """Send periodic pings to keep WebSocket alive."""
        nonlocal websocket_active
        while websocket_active:
            await asyncio.sleep(10)
            if not websocket_active:
                break
            try:
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_json({'type': 'ping'})
            except (WebSocketDisconnect, RuntimeError):
                websocket_active = False
                break

    async def stream_transcript_process():
        """Process buffered transcript segments: update DB, send to client, translate, pusher."""
        nonlocal websocket_active, realtime_segment_buffers

        while websocket_active or len(realtime_segment_buffers) > 0:
            await asyncio.sleep(0.6)

            if not realtime_segment_buffers:
                continue

            segments_to_process = realtime_segment_buffers.copy()
            realtime_segment_buffers = []

            finished_at = datetime.now(timezone.utc)

            # Get conversation
            conversation_data = conversations_db.get_conversation(uid, conversation_id)
            if not conversation_data:
                print(f"multi_channel: conversation {conversation_id} not found", uid, session_id)
                continue

            # Build TranscriptSegment objects
            newly_processed_segments = []
            for s in segments_to_process:
                seg = TranscriptSegment(
                    text=s.get('text', ''),
                    speaker=s.get('speaker', 'SPEAKER_00'),
                    is_user=s.get('is_user', False),
                    start=s.get('start', 0.0),
                    end=s.get('end', 0.0),
                )
                newly_processed_segments.append(seg)

            # Count words for usage tracking
            words_transcribed = len(" ".join([seg.text for seg in newly_processed_segments]).split())
            if words_transcribed > 0:
                usage_tracker.on_words_transcribed(words_transcribed)

            # Combine with existing segments
            combined_segments, _, _ = TranscriptSegment.combine_segments([], newly_processed_segments)

            # Update conversation in DB
            conversation = Conversation(**conversation_data)
            existing_segments = conversation.transcript_segments or []
            all_segments = existing_segments + combined_segments
            # Sort by start time
            all_segments.sort(key=lambda s: s.start)

            update_data = {
                'transcript_segments': [seg.dict() for seg in all_segments],
                'finished_at': finished_at,
            }
            conversations_db.update_conversation(uid, conversation_id, update_data)

            # Send to client
            if websocket_active:
                try:
                    for seg in combined_segments:
                        await websocket.send_json(
                            {
                                'type': 'phone_transcript',
                                'segment': {
                                    'id': seg.id,
                                    'text': seg.text,
                                    'is_user': seg.is_user,
                                    'speaker': seg.speaker,
                                    'start': seg.start,
                                    'end': seg.end,
                                    'is_final': True,
                                },
                            }
                        )
                except (WebSocketDisconnect, RuntimeError):
                    websocket_active = False

            # Send to pusher
            if pusher_handler and pusher_handler.is_connected() and usage_tracker.user_has_credits:
                pusher_handler.transcript_send([seg.dict() for seg in combined_segments])

            # Translation
            if translation_enabled and combined_segments:
                await translate_segments(
                    segments=combined_segments,
                    conversation_id=conversation_id,
                    uid=uid,
                    translation_language=translation_language,
                    source_language=stt_language,
                    translation_service=translation_service,
                    language_cache=language_cache,
                    send_message_event=send_message_event,
                    session_id=session_id,
                )

    async def receive_audio():
        """Main WebSocket receive loop — demultiplexes channels."""
        nonlocal websocket_active, last_chunk_time

        channel_packets = [0] * len(channel_configs)
        channel_bytes = [0] * len(channel_configs)
        last_stats_time = time.time()

        while websocket_active:
            try:
                message = await websocket.receive()
            except WebSocketDisconnect:
                websocket_active = False
                break

            if message.get('type') == 'websocket.disconnect':
                websocket_active = False
                break

            data = message.get('bytes')
            if not data or len(data) < 2:
                continue

            channel_id = data[0]
            audio_data = data[1:]

            # Map channel ID to index
            ch_idx = channel_id_to_index.get(channel_id)
            if ch_idx is None:
                continue

            # Decode audio
            pcm = decode_audio(audio_data, opus_decoders[ch_idx])
            pcm_16k = resample_if_needed(pcm, sample_rate, TARGET_SAMPLE_RATE)

            # Stats
            channel_packets[ch_idx] += 1
            channel_bytes[ch_idx] += len(pcm_16k)

            # Usage tracking
            now = time.time()
            if usage_tracker.first_audio_byte_timestamp is None:
                usage_tracker.on_first_audio(now)
            usage_tracker.on_audio_received(now)

            # Send to STT
            if stt_sockets[ch_idx]:
                try:
                    stt_sockets[ch_idx].send(pcm_16k)
                except Exception as e:
                    if channel_packets[ch_idx] <= 5 or channel_packets[ch_idx] % 500 == 0:
                        print(
                            f"multi_channel: STT send error ch={ch_idx} pkt={channel_packets[ch_idx]}: {e}",
                            uid,
                            session_id,
                        )

            # Buffer for mixed audio storage
            channel_chunk_buffers[ch_idx].extend(pcm_16k)

            # Send mixed audio to pusher
            if pusher_handler and pusher_handler.has_audio_bytes:
                pusher_handler.audio_bytes_send(pcm_16k, now)

            # Log stats every 10 seconds
            if now - last_stats_time >= 10:
                stats_parts = []
                for i, ch in enumerate(channel_configs):
                    stats_parts.append(f"{ch.label}: {channel_packets[i]} pkts ({channel_bytes[i]} bytes)")
                print(f"multi_channel: audio stats - {', '.join(stats_parts)}", uid, session_id)
                last_stats_time = now

            # Flush chunks periodically
            if now - last_chunk_time >= CHUNK_DURATION_SECONDS:
                has_data = any(len(buf) > 0 for buf in channel_chunk_buffers)
                if has_data:
                    if private_cloud_sync_enabled:
                        chunk_data = mix_n_channel_buffers(channel_chunk_buffers)
                        chunk_upload_queue.append(
                            {
                                'data': chunk_data,
                                'timestamp': last_chunk_time,
                                'retries': 0,
                            }
                        )
                    for buf in channel_chunk_buffers:
                        buf.clear()
                    last_chunk_time = now

    # ---- Run all tasks ----

    tasks = [
        asyncio.create_task(receive_audio()),
        asyncio.create_task(heartbeat()),
        asyncio.create_task(stream_transcript_process()),
        asyncio.create_task(usage_tracker.run()),
    ]
    if private_cloud_sync_enabled:
        tasks.append(asyncio.create_task(process_chunk_uploads()))
    if pusher_handler:
        for coro in pusher_handler.get_background_tasks():
            tasks.append(asyncio.create_task(coro))

    try:
        await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e:
        print(f"multi_channel: error in tasks: {e}", uid, session_id)
    finally:
        websocket_active = False

    # ---- Cleanup ----

    # Close STT sockets
    for i, stt_socket in enumerate(stt_sockets):
        if stt_socket:
            try:
                stt_socket.finish()
            except Exception:
                pass

    # Close pusher
    if pusher_handler:
        try:
            await pusher_handler.close()
        except Exception:
            pass

    # Upload remaining audio chunks
    has_remaining = any(len(buf) > 0 for buf in channel_chunk_buffers)
    if private_cloud_sync_enabled and has_remaining:
        try:
            final_chunk = mix_n_channel_buffers(channel_chunk_buffers)
            await asyncio.to_thread(upload_audio_chunk, final_chunk, uid, conversation_id, time.time())
            del final_chunk
        except Exception as e:
            print(f"multi_channel: final chunk upload failed: {e}", uid, session_id)

    # Free audio buffers
    for buf in channel_chunk_buffers:
        buf.clear()
    del channel_chunk_buffers

    # Record final usage
    usage_tracker.record_final_usage()

    # Build final transcript segments
    final_segments = []
    for seg in sorted(transcript_segments, key=lambda s: s.get('start', 0)):
        final_segments.append(
            TranscriptSegment(
                text=seg.get('text', ''),
                speaker=seg.get('speaker', 'SPEAKER_00'),
                is_user=seg.get('is_user', False),
                person_id=seg.get('person_id'),
                start=seg.get('start', 0.0),
                end=seg.get('end', 0.0),
            )
        )

    # Update conversation
    update_data = {
        'finished_at': datetime.now(timezone.utc),
        'transcript_segments': [seg.dict() for seg in final_segments],
        'status': ConversationStatus.processing.value,
    }
    conversations_db.update_conversation(uid, conversation_id, update_data)
    redis_db.remove_in_progress_conversation_id(uid)

    # Process conversation
    await process_completed_conversation(
        uid=uid,
        conversation_id=conversation_id,
        language=language,
        send_message_event=send_message_event,
        pusher_handler=pusher_handler,
        session_id=session_id,
    )

    call_duration = time.time() - call_start_time
    print(
        f"multi_channel: session {session_id} completed, duration={call_duration:.1f}s, "
        f"segments={len(final_segments)}",
        uid,
        session_id,
    )

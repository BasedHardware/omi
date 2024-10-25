import uuid
from datetime import datetime, timezone, timedelta
from enum import Enum

import opuslib
import webrtcvad
from fastapi import APIRouter
from fastapi.websockets import WebSocketDisconnect, WebSocket
from pydub import AudioSegment
from starlette.websockets import WebSocketState

import database.memories as memories_db
from database import redis_db
from database.redis_db import get_cached_user_geolocation
from models.memory import Memory, TranscriptSegment, MemoryStatus, Structured, Geolocation
from models.message_event import MemoryEvent, MessageEvent
from utils.memories.location import get_google_maps_location
from utils.memories.process_memory import process_memory
from utils.plugins import trigger_external_integrations, trigger_realtime_integrations
from utils.stt.streaming import *
from utils.webhooks import send_audio_bytes_developer_webhook, realtime_transcript_webhook, \
    get_audio_bytes_webhook_seconds

router = APIRouter()


class STTService(str, Enum):
    deepgram = "deepgram"
    soniox = "soniox"
    speechmatics = "speechmatics"

    # auto = "auto"

    @staticmethod
    def get_model_name(value):
        if value == STTService.deepgram:
            return 'deepgram_streaming'
        elif value == STTService.soniox:
            return 'soniox_streaming'
        elif value == STTService.speechmatics:
            return 'speechmatics_streaming'


def retrieve_in_progress_memory(uid):
    memory_id = redis_db.get_in_progress_memory_id(uid)
    existing = None

    if memory_id:
        existing = memories_db.get_memory(uid, memory_id)
        if existing and existing['status'] != 'in_progress':
            existing = None

    if not existing:
        existing = memories_db.get_in_progress_memory(uid)
    return existing


async def _websocket_util(
        websocket: WebSocket, uid: str, language: str = 'en', sample_rate: int = 8000, codec: str = 'pcm8',
        channels: int = 1, include_speech_profile: bool = True, stt_service: STTService = STTService.soniox
):
    print('_websocket_util', uid, language, sample_rate, codec, include_speech_profile)

    # Not when comes from the phone, and only Friend's with 1.0.4
    if stt_service == STTService.soniox and language not in soniox_valid_languages:
        stt_service = STTService.deepgram

    try:
        await websocket.accept()
    except RuntimeError as e:
        print(e)
        await websocket.close(code=1011, reason="Dirty state")
        return

    # Initiate a separate vad for each websocket
    w_vad = webrtcvad.Vad()
    w_vad.set_mode(1)

    # A  frame must be either 10, 20, or 30 ms in duration
    def _has_speech(data, sample_rate):
        sample_size = 320 if sample_rate == 16000 else 160
        offset = 0
        while offset < len(data):
            sample = data[offset:offset + sample_size]
            if len(sample) < sample_size:
                sample = sample + bytes([0x00] * (sample_size - len(sample) % sample_size))
            has_speech = w_vad.is_speech(sample, sample_rate)
            if has_speech:
                return True
            offset += sample_size
        return False

    # Stream transcript
    loop = asyncio.get_event_loop()
    memory_creation_timeout = 120

    async def _send_message_event(msg: MessageEvent):
        print(f"Message: type ${msg.event_type}")
        try:
            await websocket.send_json(msg.to_json())
            return True
        except WebSocketDisconnect:
            print("WebSocket disconnected")
        except RuntimeError as e:
            print(f"Can not send message event, error: {e}")

        return False

    async def _trigger_create_memory_with_delay(delay_seconds: int, finished_at: datetime):
        # print('memory_creation_timer', delay_seconds)
        try:
            await asyncio.sleep(delay_seconds)

            # recheck session
            memory = retrieve_in_progress_memory(uid)
            if not memory or memory['finished_at'] > finished_at:
                print(f"_trigger_create_memory_with_delay not memory or not last session")
                return
            await _create_current_memory()
        except asyncio.CancelledError:
            pass

    async def _create_memory(memory: dict):
        memory = Memory(**memory)
        if memory.status != MemoryStatus.processing:
            asyncio.create_task(_send_message_event(MemoryEvent(event_type="memory_processing_started", memory=memory)))
            memories_db.update_memory_status(uid, memory.id, MemoryStatus.processing)
            memory.status = MemoryStatus.processing

        try:
            # Geolocation
            geolocation = get_cached_user_geolocation(uid)
            if geolocation:
                geolocation = Geolocation(**geolocation)
                memory.geolocation = get_google_maps_location(geolocation.latitude, geolocation.longitude)

            memory = process_memory(uid, language, memory)
            messages = trigger_external_integrations(uid, memory)
        except Exception as e:
            print(f"Error processing memory: {e}")
            memories_db.set_memory_as_discarded(uid, memory.id)
            memory.discarded = True
            messages = []

        asyncio.create_task(
            _send_message_event(MemoryEvent(event_type="memory_created", memory=memory, messages=messages))
        )

    async def finalize_processing_memories(processing: List[dict]):
        # handle edge case of memory was actually processing? maybe later, doesn't hurt really anyway.
        # also fix from getMemories endpoint?
        print('finalize_processing_memories len(processing):', len(processing))
        for memory in processing:
            await _create_memory(memory)

    processing = memories_db.get_processing_memories(uid)
    asyncio.create_task(finalize_processing_memories(processing))

    async def _create_current_memory():
        print("_create_current_memory")

        # Reset state variablesr
        nonlocal seconds_to_trim
        nonlocal seconds_to_add
        seconds_to_trim = None
        seconds_to_add = None

        memory = retrieve_in_progress_memory(uid)
        if not memory or not memory['transcript_segments']:
            return
        await _create_memory(memory)

    # memory_creation_task_lock = False
    memory_creation_task_lock = asyncio.Lock()
    memory_creation_task = None
    seconds_to_trim = None
    seconds_to_add = None

    # Determine previous disconnected socket seconds to add + start processing timer if a memory in progress
    if existing_memory := retrieve_in_progress_memory(uid):
        # segments seconds alignment
        started_at = datetime.fromisoformat(existing_memory['started_at'].isoformat())
        seconds_to_add = (datetime.now(timezone.utc) - started_at).total_seconds()

        # processing if needed logic
        finished_at = datetime.fromisoformat(existing_memory['finished_at'].isoformat())
        seconds_since_last_segment = (datetime.now(timezone.utc) - finished_at).total_seconds()
        if seconds_since_last_segment >= memory_creation_timeout:
            print('_websocket_util processing existing_memory', existing_memory['id'], seconds_since_last_segment)
            asyncio.create_task(_create_current_memory())
        else:
            print('_websocket_util will process', existing_memory['id'], 'in',
                  memory_creation_timeout - seconds_since_last_segment, 'seconds')
            memory_creation_task = asyncio.create_task(
                _trigger_create_memory_with_delay(memory_creation_timeout - seconds_since_last_segment, finished_at)
            )

    def _get_or_create_in_progress_memory(segments: List[dict]):
        if existing := retrieve_in_progress_memory(uid):
            # print('_get_or_create_in_progress_memory existing', existing['id'])
            memory = Memory(**existing)
            memory.transcript_segments = TranscriptSegment.combine_segments(
                memory.transcript_segments, [TranscriptSegment(**segment) for segment in segments]
            )
            redis_db.set_in_progress_memory_id(uid, memory.id)
            return memory

        started_at = datetime.now(timezone.utc) - timedelta(seconds=segments[0]['end'] - segments[0]['start'])
        memory = Memory(
            id=str(uuid.uuid4()),
            uid=uid,
            structured=Structured(),
            language=language,
            created_at=started_at,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            transcript_segments=[TranscriptSegment(**segment) for segment in segments],
            status=MemoryStatus.in_progress,
        )
        print('_get_in_progress_memory new', memory)
        memories_db.upsert_memory(uid, memory_data=memory.dict())
        redis_db.set_in_progress_memory_id(uid, memory.id)
        return memory

    async def create_memory_on_segment_received_task(finished_at: datetime):
        nonlocal memory_creation_task
        async with memory_creation_task_lock:
            if memory_creation_task is not None:
                memory_creation_task.cancel()
                try:
                    await memory_creation_task
                except asyncio.CancelledError:
                    print("memory_creation_task is cancelled now")
            memory_creation_task = asyncio.create_task(
                _trigger_create_memory_with_delay(memory_creation_timeout, finished_at))

    def stream_transcript(segments):
        nonlocal websocket
        nonlocal seconds_to_trim

        if not segments or len(segments) == 0:
            return

        # Align the start, end segment
        if seconds_to_trim is None:
            seconds_to_trim = segments[0]["start"]

        finished_at = datetime.now(timezone.utc)
        asyncio.run_coroutine_threadsafe(create_memory_on_segment_received_task(finished_at), loop)

        # Segments aligning duration seconds.
        if seconds_to_add:
            for i, segment in enumerate(segments):
                segment["start"] += seconds_to_add
                segment["end"] += seconds_to_add
                segments[i] = segment
        elif seconds_to_trim:
            for i, segment in enumerate(segments):
                segment["start"] -= seconds_to_trim
                segment["end"] -= seconds_to_trim
                segments[i] = segment

        asyncio.run_coroutine_threadsafe(websocket.send_json(segments), loop)

        # realtime plugins + realtime webhook
        asyncio.run_coroutine_threadsafe(trigger_realtime_integrations(uid, segments), loop)
        asyncio.run_coroutine_threadsafe(realtime_transcript_webhook(uid, segments), loop)

        memory = _get_or_create_in_progress_memory(segments)  # can trigger race condition? increase soniox utterance?
        memories_db.update_memory_segments(uid, memory.id, [s.dict() for s in memory.transcript_segments])
        memories_db.update_memory_finished_at(uid, memory.id, finished_at)

        # threading.Thread(target=process_segments, args=(uid, segments)).start() # restore when plugins work

    soniox_socket = None
    speechmatics_socket = None
    deepgram_socket = None
    deepgram_socket2 = None

    speech_profile_duration = 0
    try:
        file_path, speech_profile_duration = None, 0
        # TODO: how bee does for recognizing other languages speech profile
        if language == 'en' and (codec == 'opus' or codec == 'pcm16') and include_speech_profile:
            file_path = get_profile_audio_if_exists(uid)
            speech_profile_duration = AudioSegment.from_wav(file_path).duration_seconds + 5 if file_path else 0

        # DEEPGRAM
        if stt_service == STTService.deepgram:
            deepgram_socket = await process_audio_dg(
                stream_transcript, language, sample_rate, 1, preseconds=speech_profile_duration
            )
            if speech_profile_duration:
                deepgram_socket2 = await process_audio_dg(stream_transcript, language, sample_rate, 1)

                async def deepgram_socket_send(data):
                    return deepgram_socket.send(data)

                await send_initial_file_path(file_path, deepgram_socket_send)
        # SONIOX
        elif stt_service == STTService.soniox:
            soniox_socket = await process_audio_soniox(
                stream_transcript, sample_rate, language,
                uid if include_speech_profile else None
            )
        # SPEECHMATICS
        elif stt_service == STTService.speechmatics:
            speechmatics_socket = await process_audio_speechmatics(
                stream_transcript, sample_rate, language, preseconds=speech_profile_duration
            )
            if speech_profile_duration:
                await send_initial_file_path(file_path, speechmatics_socket.send)
                print('speech_profile speechmatics duration', speech_profile_duration)

    except Exception as e:
        print(f"Initial processing error: {e}")
        websocket_close_code = 1011
        await websocket.close(code=websocket_close_code)
        return

    decoder = opuslib.Decoder(sample_rate, 1)
    websocket_active = True
    websocket_close_code = 1001  # Going Away, don't close with good from backend
    audio_bytes_webhook_delay_seconds = get_audio_bytes_webhook_seconds(uid)

    async def receive_audio(dg_socket1, dg_socket2, soniox_socket, speechmatics_socket1):
        nonlocal websocket_active
        nonlocal websocket_close_code

        timer_start = time.time()
        audiobuffer = bytearray()
        # f = open("audio.bin", "ab")
        try:
            while websocket_active:
                data = await websocket.receive_bytes()
                # save the data to a file
                # data_length = len(data)
                # f.write(struct.pack('I', data_length))  # Write length as 4 bytes
                # f.write(data)

                if codec == 'opus' and sample_rate == 16000:
                    data = decoder.decode(bytes(data), frame_size=160)

                audiobuffer.extend(data)

                if include_speech_profile and codec != 'opus':  # don't do for opus 1.0.4 for now
                    has_speech = _has_speech(data, sample_rate)
                    if not has_speech:
                        continue

                if soniox_socket is not None:
                    await soniox_socket.send(data)

                if speechmatics_socket1 is not None:
                    await speechmatics_socket1.send(data)

                if dg_socket1 is not None:
                    elapsed_seconds = time.time() - timer_start
                    if elapsed_seconds > speech_profile_duration or not dg_socket2:
                        dg_socket1.send(data)
                        if dg_socket2:
                            print('Killing socket2')
                            dg_socket2.finish()
                            dg_socket2 = None
                    else:
                        dg_socket2.send(data)

                if audio_bytes_webhook_delay_seconds and len(
                        audiobuffer) > sample_rate * audio_bytes_webhook_delay_seconds * 2:
                    asyncio.create_task(send_audio_bytes_developer_webhook(uid, sample_rate, audiobuffer.copy()))
                    audiobuffer = bytearray()

        except WebSocketDisconnect:
            print("WebSocket disconnected")
        except Exception as e:
            print(f'Could not process audio: error {e}')
            websocket_close_code = 1011
        finally:
            websocket_active = False
            if dg_socket1:
                dg_socket1.finish()
            if dg_socket2:
                dg_socket2.finish()
            if soniox_socket:
                await soniox_socket.close()
            if speechmatics_socket:
                await speechmatics_socket.close()

    # heart beat
    started_at = time.time()
    timeout_seconds = 420  # 7m # Soft timeout, should < MODAL_TIME_OUT - 3m
    has_timeout = os.getenv('NO_SOCKET_TIMEOUT') is None

    async def send_heartbeat():
        nonlocal websocket_active
        nonlocal websocket_close_code
        nonlocal started_at
        try:
            while websocket_active:
                await asyncio.sleep(30)
                # print('send_heartbeat')
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_json({"type": "ping"})
                else:
                    break

                # timeout
                if not has_timeout:
                    continue

                if time.time() - started_at >= timeout_seconds:
                    print(f"Session timeout is hit by soft timeout {timeout_seconds}")
                    websocket_close_code = 1001
                    websocket_active = False
        except WebSocketDisconnect:
            print("WebSocket disconnected")
        except Exception as e:
            print(f'Heartbeat error: {e}')
            websocket_close_code = 1011
        finally:
            websocket_active = False

    try:
        receive_task = asyncio.create_task(
            receive_audio(deepgram_socket, deepgram_socket2, soniox_socket, speechmatics_socket)
        )
        heartbeat_task = asyncio.create_task(send_heartbeat())
        await asyncio.gather(receive_task, heartbeat_task)

    except Exception as e:
        print(f"Error during WebSocket operation: {e}")
    finally:
        websocket_active = False
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close(code=websocket_close_code)
            except Exception as e:
                print(f"Error closing WebSocket: {e}")


@router.websocket("/v2/listen")
async def websocket_endpoint(
        websocket: WebSocket, uid: str, language: str = 'en', sample_rate: int = 8000, codec: str = 'pcm8',
        channels: int = 1, include_speech_profile: bool = True, stt_service: STTService = STTService.soniox
):
    await _websocket_util(websocket, uid, language, sample_rate, codec, channels, include_speech_profile, stt_service)

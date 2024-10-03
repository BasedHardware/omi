import threading
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
from models.memory import Memory, TranscriptSegment, MemoryStatus, Structured
from models.message_event import NewMemoryCreated, MessageEvent
from utils.memories.process_memory import process_memory
from utils.plugins import trigger_external_integrations
from utils.stt.streaming import *

router = APIRouter()


# Minor script generate wav from raw audio bytes
# import wave
# import os
#
# # Parameters for the WAV file
# sample_rate = 16000  # Assuming a sample rate of 16000 Hz
# channels = 1  # Mono audio
# sample_width = 2  # Assuming 16-bit audio (2 bytes per sample)
#
# # Read the raw audio data from the file
# with open("audio.raw", "rb") as raw_file:
#     raw_audio_data = raw_file.read()
#
# if __name__ == '__main__':
#     with wave.open("output.wav", "wb") as wav_file:
#         wav_file.setnchannels(channels)  # Set mono/stereo
#         wav_file.setsampwidth(sample_width)  # Set sample width to 16 bits (2 bytes)
#         wav_file.setframerate(sample_rate)  # Set sample rate to 16000 Hz
#         wav_file.writeframes(raw_audio_data)  # Write raw audio data to WAV

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


async def _websocket_util(
        websocket: WebSocket, uid: str, language: str = 'en', sample_rate: int = 8000, codec: str = 'pcm8',
        channels: int = 1, include_speech_profile: bool = True, new_memory_watch: bool = False,
        # stt_service: STTService = STTService.deepgram,
):
    print('websocket_endpoint', uid, language, sample_rate, codec, channels, include_speech_profile, new_memory_watch)

    # Not when comes from the phone, and only Friend's with 1.0.4
    if language == 'en' and sample_rate == 16000 and codec == 'opus':
        stt_service = STTService.soniox
    else:
        stt_service = STTService.deepgram

    try:
        await websocket.accept()
    except RuntimeError as e:
        print(e)
        return

    session_id = str(uuid.uuid4())

    # Initiate a separate vad for each websocket
    w_vad = webrtcvad.Vad()
    w_vad.set_mode(1)
    flush_new_memory_lock = threading.Lock()

    # Stream transcript
    loop = asyncio.get_event_loop()

    # Soft timeout, should < MODAL_TIME_OUT - 3m
    timeout_seconds = 420  # 7m
    started_at = time.time()

    def _get_in_progress_memory(segments: List[dict] = []):
        existing = memories_db.get_in_progress_memory(uid)
        if existing:
            print('_get_in_progress_memory existing', existing)
            memory = Memory(**existing)
            memory.transcript_segments = TranscriptSegment.combine_segments(
                memory.transcript_segments, [TranscriptSegment(**segment) for segment in segments]
            )
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
        return memory

    async def memory_creation_timer():
        try:
            await asyncio.sleep(120)
            await _create_memory()
        except asyncio.CancelledError:
            pass

    memory_creation_task = None
    segment_start = None

    def stream_transcript(segments, _):
        nonlocal websocket
        nonlocal segment_start
        nonlocal memory_creation_task

        if not segments or len(segments) == 0:
            return

        # Align the start, end segment
        if not segment_start:
            segment_start = segments[0]["start"]

        if memory_creation_task is not None:
            memory_creation_task.cancel()
        memory_creation_task = asyncio.create_task(memory_creation_timer())

        for i, segment in enumerate(segments):
            segment["start"] -= segment_start
            segment["end"] -= segment_start
            segments[i] = segment
        # TODO: what when transcript is large!
        memory = _get_in_progress_memory(segments)  # can trigger race condition? increase soniox utterance?
        memories_db.update_memory_segments(uid, memory.id, [s.dict() for s in memory.transcript_segments])
        memories_db.update_memory_finished_at(uid, memory.id, datetime.now(timezone.utc))

        asyncio.run_coroutine_threadsafe(websocket.send_json(segments), loop)
        threading.Thread(target=process_segments, args=(uid, segments)).start()

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
                stream_transcript, 1, language, sample_rate, channels, preseconds=speech_profile_duration
            )
            if speech_profile_duration:
                deepgram_socket2 = await process_audio_dg(
                    stream_transcript, 2, language, sample_rate, channels
                )

                async def deepgram_socket_send(data):
                    return deepgram_socket.send(data)

                await send_initial_file_path(file_path, deepgram_socket_send)
        # SONIOX
        elif stt_service == STTService.soniox:
            soniox_socket = await process_audio_soniox(
                stream_transcript, 1, sample_rate, language,
                uid if include_speech_profile else None
            )
        # SPEECHMATICS
        elif stt_service == STTService.speechmatics:
            speechmatics_socket = await process_audio_speechmatics(
                stream_transcript, 1, sample_rate, language, preseconds=speech_profile_duration
            )
            if speech_profile_duration:
                await send_initial_file_path(file_path, speechmatics_socket.send)
                print('speech_profile speechmatics duration', speech_profile_duration)

    except Exception as e:
        print(f"Initial processing error: {e}")
        websocket_close_code = 1011
        await websocket.close(code=websocket_close_code)
        return

    decoder = opuslib.Decoder(sample_rate, channels)
    websocket_active = True
    websocket_close_code = 1001  # Going Away, don't close with good from backend

    async def receive_audio(dg_socket1, dg_socket2, soniox_socket, speechmatics_socket1):
        nonlocal websocket_active
        nonlocal websocket_close_code

        timer_start = time.time()
        # f = open("audio.raw", "ab")
        try:
            while websocket_active:
                data = await websocket.receive_bytes()

                if codec == 'opus' and sample_rate == 16000:
                    data = decoder.decode(bytes(data), frame_size=160)

                if include_speech_profile:
                    # pick 320 bytes as a vad sample, cause frame_width 2?
                    vad_sample_size = 320
                    vad_sample = data[:vad_sample_size]
                    if len(vad_sample) < vad_sample_size:
                        vad_sample = vad_sample + bytes([0x00] * (vad_sample_size - len(vad_sample)))
                    has_speech = w_vad.is_speech(vad_sample, sample_rate)
                    if not has_speech:
                        continue

                # TODO: is the VAD slowing down the STT service? specially soniox?
                # - but from write data, it feels faster, but the processing is having issues
                # - and soniox after missingn a couple filtered bytes get's slower
                # - specially after waiting for like a couple seconds.
                # f.write(data)

                if soniox_socket is not None:
                    await soniox_socket.send(data)

                if speechmatics_socket1 is not None:
                    await speechmatics_socket1.send(data)

                if deepgram_socket is not None:
                    elapsed_seconds = time.time() - timer_start
                    if elapsed_seconds > speech_profile_duration or not dg_socket2:
                        dg_socket1.send(data)
                        if dg_socket2:
                            print('Killing socket2')
                            dg_socket2.finish()
                            dg_socket2 = None
                    else:
                        dg_socket2.send(data)

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
                if time.time() - started_at >= timeout_seconds:
                    print(f"Session timeout is hit by soft timeout {timeout_seconds}, session {session_id}")
                    websocket_close_code = 1001
                    websocket_active = False
        except WebSocketDisconnect:
            print("WebSocket disconnected")
        except Exception as e:
            print(f'Heartbeat error: {e}')
            websocket_close_code = 1011
        finally:
            websocket_active = False

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

    # Create proccesing memory

    # Create memory
    async def _create_memory():
        print("_create_memory")

        memory = _get_in_progress_memory()
        if not memory or not memory.transcript_segments:
            raise Exception('FAILED')

        await _send_message_event(MessageEvent(event_type="memory_processing_started"))

        memories_db.update_memory_status(uid, memory.id, MemoryStatus.processing)
        memory = process_memory(uid, language, memory)
        memories_db.update_memory_status(uid, memory.id, MemoryStatus.completed)
        messages = trigger_external_integrations(uid, memory)

        await _send_message_event(MessageEvent(event_type="memory_processing_completed"))
        ok = await _send_message_event(
            NewMemoryCreated(
                event_type="memory_created",
                memory_id=memory.id,
                memory=memory,
                messages=messages,
            )
        )
        if not ok:
            print("Failed to send memory created message")

    try:
        receive_task = asyncio.create_task(
            receive_audio(deepgram_socket, deepgram_socket2, soniox_socket, speechmatics_socket))
        heartbeat_task = asyncio.create_task(send_heartbeat())

        # Run task
        # if new_memory_watch:
        #     # new_memory_task = asyncio.create_task(memory_transcript_segements_watch())
        #     await asyncio.gather(receive_task, new_memory_task, heartbeat_task)
        # else:
        await asyncio.gather(receive_task, heartbeat_task)

    except Exception as e:
        print(f"Error during WebSocket operation: {e}")
    finally:
        websocket_active = False
        memory_watching = False

        # Flush new memory watch
        # if new_memory_watch:
        #     await _flush_new_memory_with_lock(time_validate=False)

        # Close socket
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close(code=websocket_close_code)
            except Exception as e:
                print(f"Error closing WebSocket: {e}")


@router.websocket("/listen")
async def websocket_endpoint(
        websocket: WebSocket, uid: str, language: str = 'en', sample_rate: int = 8000, codec: str = 'pcm8',
        channels: int = 1, include_speech_profile: bool = True, new_memory_watch: bool = False,
        # stt_service: STTService = STTService.deepgram
):
    await _websocket_util(
        websocket, uid, language, sample_rate, codec, channels, include_speech_profile, new_memory_watch,  # stt_service
    )

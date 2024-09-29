import threading
import uuid
from datetime import datetime, timezone
from enum import Enum

import opuslib
import webrtcvad
from fastapi import APIRouter
from fastapi.websockets import WebSocketDisconnect, WebSocket
from pydub import AudioSegment
from starlette.websockets import WebSocketState

import database.memories as memories_db
import database.processing_memories as processing_memories_db
from models.memory import Memory, TranscriptSegment
from models.message_event import NewMemoryCreated, MessageEvent, NewProcessingMemoryCreated, \
    ProcessingMemoryStatusChanged
from models.processing_memory import ProcessingMemory, ProcessingMemoryStatus
from utils.memories.process_memory import process_memory
from utils.processing_memories import create_memory_by_processing_memory
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

    min_seconds_limit = 120
    min_words_limit = 1

    # Processing memory
    memory_watching = new_memory_watch
    processing_memory: ProcessingMemory = None
    processing_memory_synced: int = 0

    # Stream transcript
    memory_stream_id = 1
    memory_transcript_segements: List[TranscriptSegment] = []
    speech_profile_stream_id = 2
    loop = asyncio.get_event_loop()

    # Soft timeout, should < MODAL_TIME_OUT - 3m
    timeout_seconds = 420  # 7m
    started_at = time.time()

    def stream_transcript(segments, stream_id):
        nonlocal websocket
        nonlocal processing_memory
        nonlocal processing_memory_synced
        nonlocal memory_transcript_segements
        nonlocal segment_start
        nonlocal segment_end

        if not segments or len(segments) == 0:
            return

        # Align the start, end segment
        if not segment_start:
            start = segments[0]["start"]
            segment_start = start

        # end
        end = segments[-1]["end"]
        if not segment_end or segment_end < end:
            segment_end = end

        for i, segment in enumerate(segments):
            segment["start"] -= segment_start
            segment["end"] -= segment_start
            segments[i] = segment

        asyncio.run_coroutine_threadsafe(websocket.send_json(segments), loop)
        threading.Thread(target=process_segments, args=(uid, segments)).start()

        # memory segments
        # Warn: need double check should we still seperate the memory and speech profile stream or not?
        if (stream_id == memory_stream_id or stream_id == speech_profile_stream_id) and new_memory_watch:
            delta_seconds = 0
            if processing_memory and processing_memory.timer_start > 0:
                delta_seconds = timer_start - processing_memory.timer_start
            memory_transcript_segements = TranscriptSegment.combine_segments(
                memory_transcript_segements, list(map(lambda m: TranscriptSegment(**m), segments)), delta_seconds
            )

            # Sync processing transcript, periodly
            if processing_memory and int(time.time()) % 3 == 0:
                processing_memory_synced = len(memory_transcript_segements)
                processing_memory.transcript_segments = memory_transcript_segements

                now_ts = time.time()
                capturing_to = datetime.fromtimestamp(now_ts + min_seconds_limit, timezone.utc)

                processing_memories_db.update_processing_memory_segments(
                    uid, processing_memory.id,
                    list(map(lambda m: m.dict(), processing_memory.transcript_segments)),
                    capturing_to,
                )

    soniox_socket = None
    speechmatics_socket = None
    deepgram_socket = None
    deepgram_socket2 = None

    websocket_active = True
    websocket_close_code = 1001  # Going Away, don't close with good from backend
    timer_start = None
    segment_start = None
    segment_end = None
    # audio_buffer = None
    duration = 0
    try:
        file_path, duration = None, 0
        # TODO: how bee does for recognizing other languages speech profile
        if language == 'en' and (codec == 'opus' or codec == 'pcm16') and include_speech_profile:
            file_path = get_profile_audio_if_exists(uid)
            duration = AudioSegment.from_wav(file_path).duration_seconds + 5 if file_path else 0

        # DEEPGRAM
        if stt_service == STTService.deepgram:
            deepgram_socket = await process_audio_dg(
                stream_transcript, memory_stream_id, language, sample_rate, channels, preseconds=duration
            )
            if duration:
                deepgram_socket2 = await process_audio_dg(
                    stream_transcript, speech_profile_stream_id, language, sample_rate, channels
                )

                async def deepgram_socket_send(data):
                    return deepgram_socket.send(data)

                await send_initial_file_path(file_path, deepgram_socket_send)
        # SONIOX
        elif stt_service == STTService.soniox:
            soniox_socket = await process_audio_soniox(
                stream_transcript, speech_profile_stream_id, sample_rate, language,
                uid if include_speech_profile else None
            )
        # SPEECHMATICS
        elif stt_service == STTService.speechmatics:
            speechmatics_socket = await process_audio_speechmatics(
                stream_transcript, speech_profile_stream_id, sample_rate, language, preseconds=duration
            )
            if duration:
                await send_initial_file_path(file_path, speechmatics_socket.send)
                print('speech_profile speechmatics duration', duration)

    except Exception as e:
        print(f"Initial processing error: {e}")
        websocket_close_code = 1011
        await websocket.close(code=websocket_close_code)
        return

    window_size_samples = 256 if sample_rate == 8000 else 512

    decoder = opuslib.Decoder(sample_rate, channels)

    async def receive_audio(dg_socket1, dg_socket2, soniox_socket, speechmatics_socket1):
        nonlocal websocket_active
        nonlocal websocket_close_code
        nonlocal timer_start
        timer_start = time.time()

        # f = open("audio.raw", "ab")
        try:
            while websocket_active:
                raw_data = await websocket.receive_bytes()
                data = raw_data[:]

                if codec == 'opus' and sample_rate == 16000:
                    data = decoder.decode(bytes(data), frame_size=160)

                has_speech = w_vad.is_speech(data, sample_rate)
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
                    if elapsed_seconds > duration or not dg_socket2:
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
    async def _create_processing_memory():
        nonlocal processing_memory
        nonlocal memory_transcript_segements
        nonlocal processing_memory_synced

        # Check the last processing memory
        last_processing_memory_data = processing_memories_db.get_last(uid)
        now_ts = time.time()
        if last_processing_memory_data:
            last_processing_memory = ProcessingMemory(**last_processing_memory_data)
            if last_processing_memory.capturing_to and last_processing_memory.capturing_to.timestamp() > now_ts:
                processing_memory = last_processing_memory

        # Or create new
        if not processing_memory:
            processing_memory = ProcessingMemory(
                id=str(uuid.uuid4()),
                created_at=datetime.now(timezone.utc),
                timer_start=timer_start,
                timer_segment_start=timer_start + segment_start,
                language=language,
            )

        # Status, capturing to
        processing_memory.status = ProcessingMemoryStatus.Capturing
        processing_memory.capturing_to = datetime.fromtimestamp(now_ts + min_seconds_limit, timezone.utc)

        # Track session changes
        processing_memory.session_id = session_id
        processing_memory.session_ids.append(session_id)

        # Track timer start
        processing_memory.timer_starts.append(timer_start)

        # Transcript with delta
        memory_transcript_segements = TranscriptSegment.combine_segments(
            processing_memory.transcript_segments, memory_transcript_segements,
            timer_start - processing_memory.timer_start
        )

        processing_memory_synced = len(memory_transcript_segements)
        processing_memory.transcript_segments = memory_transcript_segements[:processing_memory_synced]
        processing_memories_db.upsert_processing_memory(uid, processing_memory.dict())

        # Message: New processing memory created
        ok = await _send_message_event(NewProcessingMemoryCreated(
            event_type="new_processing_memory_created",
            processing_memory_id=processing_memory.id,
            memory_id=processing_memory.memory_id,
        ),
        )
        if not ok:
            print("Can not send message event new_processing_memory_created")

    # Create memory
    async def _create_memory():
        print("create memory")
        nonlocal processing_memory
        nonlocal processing_memory_synced
        nonlocal memory_transcript_segements

        if not processing_memory:
            # Force create one
            await _create_processing_memory()
        else:
            # or ensure synced processing transcript
            processing_memory_data = processing_memories_db.get_processing_memory_by_id(uid, processing_memory.id)
            if not processing_memory_data:
                print("processing memory is not found")
                return
            processing_memory = ProcessingMemory(**processing_memory_data)

            processing_memory_synced = len(memory_transcript_segements)
            processing_memory.transcript_segments = memory_transcript_segements[:processing_memory_synced]

            now_ts = time.time()
            capturing_to = datetime.fromtimestamp(now_ts + min_seconds_limit, timezone.utc)

            processing_memories_db.update_processing_memory_segments(
                uid, processing_memory.id,
                list(map(lambda m: m.dict(), processing_memory.transcript_segments)),
                capturing_to,
            )

        # Update processing memory status
        processing_memory.status = ProcessingMemoryStatus.Processing
        processing_memories_db.update_processing_memory_status(
            uid, processing_memory.id,
            processing_memory.status,
        )
        # Message: processing memory status changed
        ok = await _send_message_event(ProcessingMemoryStatusChanged(
            event_type="processing_memory_status_changed",
            processing_memory_id=processing_memory.id,
            processing_memory_status=processing_memory.status),
        )
        if not ok:
            print("Can not send message event processing_memory_status_changed")

        # Message: creating
        ok = await _send_message_event(MessageEvent(event_type="new_memory_creating"))
        if not ok:
            print("Can not send message event new_memory_creating")

        # Not existed memory then create new one
        messages = []
        if not processing_memory.memory_id:
            new_memory, new_messages, updated_processing_memory = await create_memory_by_processing_memory(
                uid, processing_memory.id
            )
            if not new_memory:
                print("Can not create new memory")

                # Message: failed
                ok = await _send_message_event(MessageEvent(event_type="new_memory_create_failed"))
                if not ok:
                    print("Can not send message event new_memory_create_failed")
                return

            memory = new_memory
            messages = new_messages
            processing_memory = updated_processing_memory
        else:
            # Or process the existed with new transcript
            memory_data = memories_db.get_memory(uid, processing_memory.memory_id)
            if memory_data is None:
                print(f"Memory is not found. Uid: {uid}. Memory: {processing_memory.memory_id}")
                return
            memory = Memory(**memory_data)

            # Update transcripts
            memory.transcript_segments = processing_memory.transcript_segments
            memories_db.update_memory_segments(
                uid, memory.id, [segment.dict() for segment in memory.transcript_segments]
            )

            # Update finished at
            memory.finished_at = datetime.fromtimestamp(
                memory.started_at.timestamp() + processing_memory.transcript_segments[-1].end, timezone.utc
            )
            memories_db.update_memory_finished_at(uid, memory.id, memory.finished_at)

            # Process
            memory = process_memory(uid, memory.language, memory, force_process=True)

        # Update processing memory status
        processing_memory.status = ProcessingMemoryStatus.Done
        processing_memories_db.update_processing_memory_status(
            uid, processing_memory.id,
            processing_memory.status,
        )
        # Message: processing memory status changed
        ok = await _send_message_event(ProcessingMemoryStatusChanged(
            event_type="processing_memory_status_changed",
            processing_memory_id=processing_memory.id,
            memory_id=processing_memory.memory_id,
            processing_memory_status=processing_memory.status),
        )
        if not ok:
            print("Can not send message event processing_memory_status_changed")

        # Message: completed
        msg = NewMemoryCreated(
            event_type="new_memory_created", processing_memory_id=processing_memory.id, memory_id=memory.id,
            memory=memory, messages=messages,
        )
        ok = await _send_message_event(msg)
        if not ok:
            print("Can not send message event new_memory_created")

        return memory

    # New memory watch
    async def memory_transcript_segements_watch():
        nonlocal memory_watching
        nonlocal websocket_active
        while memory_watching and websocket_active:
            await asyncio.sleep(5)
            await _try_flush_new_memory_with_lock()

    async def _try_flush_new_memory_with_lock(time_validate: bool = True):
        with flush_new_memory_lock:
            return await _try_flush_new_memory(time_validate=time_validate)

    async def _try_flush_new_memory(time_validate: bool = True):
        nonlocal memory_transcript_segements
        nonlocal timer_start
        nonlocal segment_start
        nonlocal segment_end
        nonlocal processing_memory
        nonlocal processing_memory_synced

        if not timer_start:
            print("not timer start")
            return

        # Validate last segment
        if not segment_end:
            return

        # First chunk, create processing memory
        should_create_processing_memory = not processing_memory and len(memory_transcript_segements) > 0
        if should_create_processing_memory:
            await _create_processing_memory()

        # Validate transcript
        # Longer 120s
        now = time.time()
        should_create_memory_time = True
        if time_validate:
            should_create_memory_time = timer_start + segment_end + min_seconds_limit < now

        # 1 words at least
        should_create_memory_time_words = min_words_limit == 0
        if min_words_limit > 0 and should_create_memory_time:
            wc = 0
            for segment in memory_transcript_segements:
                wc = wc + len(segment.text.split(" "))
                if wc >= min_words_limit:
                    should_create_memory_time_words = True
                    break

        should_create_memory = should_create_memory_time and should_create_memory_time_words
        print(
            f"Should create memory {should_create_memory} - {timer_start} {segment_end} {min_seconds_limit} {now} - {time_validate}, session {session_id}")
        if should_create_memory:
            memory = await _create_memory()
            if not memory:
                print(
                    f"Can not create new memory uid: ${uid}, processing memory: {processing_memory.id if processing_memory else 0}")
                return

            # Clean
            memory_transcript_segements = memory_transcript_segements[processing_memory_synced:]
            processing_memory_synced = 0
            processing_memory = None

    try:
        receive_task = asyncio.create_task(
            receive_audio(deepgram_socket, deepgram_socket2, soniox_socket, speechmatics_socket))
        heartbeat_task = asyncio.create_task(send_heartbeat())

        # Run task
        if new_memory_watch:
            new_memory_task = asyncio.create_task(memory_transcript_segements_watch())
            await asyncio.gather(receive_task, new_memory_task, heartbeat_task)
        else:
            await asyncio.gather(receive_task, heartbeat_task)

    except Exception as e:
        print(f"Error during WebSocket operation: {e}")
    finally:
        websocket_active = False
        memory_watching = False

        # Flush new memory watch
        if new_memory_watch:
            await _try_flush_new_memory_with_lock(time_validate=False)

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

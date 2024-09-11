import asyncio
import os
import threading
import time
import uuid
from typing import List
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.websockets import (WebSocketDisconnect, WebSocket)
from starlette.websockets import WebSocketState

from utils.other.storage import upload_postprocessing_audio, download_postprocessing_audio
import database.processing_memories as processing_memories_db
import database.memories as memories_db
from database.redis_db import get_user_speech_profile, get_user_speech_profile_duration
from models.memory import Memory, TranscriptSegment
from models.message_event import NewMemoryCreated, MessageEvent, NewProcessingMemoryCreated
from models.processing_memory import ProcessingMemory
from routers.postprocessing import postprocess_memory_util
from utils.audio import create_wav_from_bytes, merge_wav_files
from utils.memories.process_memory import process_memory
from utils.processing_memories import create_memory_by_processing_memory
from utils.stt.streaming import process_audio_dg, send_initial_file
from utils.stt.streaming import process_segments
from utils.stt.vad import VADIterator, model

router = APIRouter()


# @router.post("/v1/transcribe", tags=['v1'])
# will be used again in Friend V2
# def transcribe_auth(file: UploadFile, uid: str, language: str = 'en'):
#     upload_id = str(uuid.uuid4())
#     file_path = f"_temp/{upload_id}_{file.filename}"
#     with open(file_path, 'wb') as f:
#         f.write(file.file.read())
#
#     aseg = AudioSegment.from_wav(file_path)
#     print(f'Transcribing audio {aseg.duration_seconds} secs and {aseg.frame_rate / 1000} khz')
#
#     if vad_is_empty(file_path):  # TODO: get vad segments
#         os.remove(file_path)
#         return []
#     transcript = transcribe_file_deepgram(file_path, language=language)
#     os.remove(file_path)
#     return transcript


# templates = Jinja2Templates(directory="templates")

# @router.get("/", response_class=HTMLResponse) // FIXME
# def get(request: Request):
#     return templates.TemplateResponse("index.html", {"request": request})

#
# Q: Why do we need try-catch around websocket.accept?
# A: When a modal (modal app) timeout occurs, it allows a new request to be made, and a new WebSocket is initiated. Everything seems fine, right?
#    But what if the receive[1], which belongs to the old request, is still lingering somewhere in the application?
#    Yes, you know that if the app doesn’t manage the receive well, the new socket may receive messages from the existing receive. That’s why when a modal timeout happens, you might see various RuntimeErrors like:
#    - Expected ASGI message "websocket.connect" but got "websocket.receive"
#    - Expected ASGI message "websocket.connect" but got "websocket.disconnect"
#    These messages are from the old receive. I called it Dirty Receive.
#
#    Because modal don't open their proto source code yet. So to deal with that kind of modal app error, lets support the grateful accept.
#
#    [1] receive in the WebSocket init function
#    class WebSocket(HTTPConnection):
#       def __init__(self, scope: Scope, receive: Receive, send: Send) -> None:
#

def _combine_segments(segments: [], new_segments: []):
    if not new_segments or len(new_segments) == 0:
        return segments

    joined_similar_segments = []
    for new_segment in new_segments:
        if (joined_similar_segments and
                (joined_similar_segments[-1].speaker == new_segment.speaker or
                 (joined_similar_segments[-1].is_user and new_segment.is_user))):
            joined_similar_segments[-1].text += f' {new_segment.text}'
            joined_similar_segments[-1].end = new_segment.end
        else:
            joined_similar_segments.append(new_segment)

    if (segments and
            (segments[-1].speaker == joined_similar_segments[0].speaker or
             (segments[-1].is_user and joined_similar_segments[0].is_user)) and
            (joined_similar_segments[0].start - segments[-1].end < 30)):
        segments[-1].text += f' {joined_similar_segments[0].text}'
        segments[-1].end = joined_similar_segments[0].end
        joined_similar_segments.pop(0)

    segments.extend(joined_similar_segments)

    return segments


async def _websocket_util(
        websocket: WebSocket, uid: str, language: str = 'en', sample_rate: int = 8000, codec: str = 'pcm8',
        channels: int = 1, include_speech_profile: bool = True, new_memory_watch: bool = False,
):
    print('websocket_endpoint', uid, language, sample_rate, codec, channels, include_speech_profile, new_memory_watch)

    # Check: Why do we need try-catch around websocket.accept?
    try:
        await websocket.accept()
    except RuntimeError as e:
        print(e)
        return

    session_id = str(uuid.uuid4())

    flush_new_memory_lock = threading.Lock()

    min_seconds_limit = 120
    min_words_limit = 1

    # Processing memory
    memory_watching = new_memory_watch
    processing_memory: ProcessingMemory = None
    processing_memory_synced: int = 0
    processing_audio_frames = []
    processing_audio_frame_synced: int = 0

    # Stream transcript
    memory_stream_id = 1
    memory_transcript_segements: List[TranscriptSegment] = []
    speech_profile_stream_id = 2
    loop = asyncio.get_event_loop()

    # Soft timeout
    timeout_seconds = 420  # 7m ~ MODAL_TIME_OUT - 3m
    started_at = time.time()

    def stream_transcript(segments, stream_id):
        nonlocal websocket
        nonlocal processing_memory
        nonlocal processing_memory_synced
        nonlocal memory_transcript_segements

        if not segments or len(segments) == 0:
            return

        asyncio.run_coroutine_threadsafe(websocket.send_json(segments), loop)
        threading.Thread(target=process_segments, args=(uid, segments)).start()

        # memory segments
        # Warn: need double check should we still seperate the memory and speech profile stream or not?
        if (stream_id == memory_stream_id or stream_id == speech_profile_stream_id) and new_memory_watch:
            memory_transcript_segements = _combine_segments(memory_transcript_segements, list(map(lambda m: TranscriptSegment(**m), segments)))
            print("hey")
            print(len(list(map(lambda m: TranscriptSegment(**m), segments))))
            print(len(memory_transcript_segements))

            # Sync processing transcript, periodly
            if processing_memory and len(memory_transcript_segements) % 3 == 0:
                processing_memory_synced = len(memory_transcript_segements)
                processing_memory.transcript_segments = memory_transcript_segements
                processing_memories_db.update_processing_memory(uid, processing_memory.id, processing_memory.dict())

    def stream_audio(audio_buffer):
        if not new_memory_watch:
            return

        processing_audio_frames.append(audio_buffer)

    # Process
    transcript_socket2 = None
    websocket_active = True
    websocket_close_code = 1001  # Going Away, don't close with good from backend
    timer_start = None
    audio_buffer = None
    duration = 0
    try:
        if language == 'en' and codec == 'opus' and include_speech_profile:
            speech_profile = get_user_speech_profile(uid)
            duration = get_user_speech_profile_duration(uid)
            print('speech_profile', len(speech_profile), duration)
            if duration:
                duration *= 2
        else:
            speech_profile, duration = [], 0

        transcript_socket = await process_audio_dg(stream_transcript, memory_stream_id,
                                                   language, sample_rate, codec, channels,
                                                   preseconds=duration)

        if duration:
            transcript_socket2 = await process_audio_dg(stream_transcript, speech_profile_stream_id,
                                                        language, sample_rate, codec, channels)

            await send_initial_file(speech_profile, transcript_socket)

    except Exception as e:
        print(f"Initial processing error: {e}")
        websocket_close_code = 1011
        await websocket.close(code=websocket_close_code)
        return

    vad_iterator = VADIterator(model, sampling_rate=sample_rate)  # threshold=0.9
    window_size_samples = 256 if sample_rate == 8000 else 512

    async def receive_audio(socket1, socket2):
        nonlocal websocket_active
        nonlocal websocket_close_code
        nonlocal timer_start
        nonlocal audio_buffer
        audio_buffer = bytearray()
        timer_start = time.time()
        # speech_state = SpeechState.no_speech
        voice_found, not_voice = 0, 0
        # path = 'scripts/vad/audio_bytes.txt'
        # if os.path.exists(path):
        #     os.remove(path)
        # audio_file = open(path, "a")
        try:
            while websocket_active:
                data = await websocket.receive_bytes()
                audio_buffer.extend(data)

                elapsed_seconds = time.time() - timer_start
                if elapsed_seconds > duration or not socket2:
                    socket1.send(audio_buffer)
                    if socket2:
                        print('Killing socket2')
                        socket2.finish()
                        socket2 = None
                else:
                    socket2.send(audio_buffer)

                # stream
                stream_audio(data)

                audio_buffer = bytearray()

        except WebSocketDisconnect:
            print("WebSocket disconnected")
        except Exception as e:
            print(f'Could not process audio: error {e}')
            websocket_close_code = 1011
        finally:
            websocket_active = False
            socket1.finish()
            if socket2:
                socket2.finish()

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
        print(f"Message: ${msg.to_json()}")
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
        if not last_processing_memory_data:
            last_processing_memory = ProcessingMemory(**last_processing_memory_data)
            segment_end = 0
            for segment in last_processing_memory.transcript_segments:
                segment_end = max(segment_end, segment.end)
            if last_processing_memory.timer_start + segment_end + min_seconds_limit > time.time():
                processing_memory = last_processing_memory
                memory_transcript_segements = last_processing_memory.transcript_segments + memory_transcript_segements

        # Or create new
        if not processing_memory:
            processing_memory = ProcessingMemory(
                id=str(uuid.uuid4()),
                created_at=datetime.now(timezone.utc),
                timer_start=timer_start,
                language=language,
            )

        # Track session changes
        if processing_memory.session_id and processing_memory.session_id != session_id:
            print(f"Processing memory {processing_memory.id} session id changes, old: {processing_memory.session_id}, new: {session_id}")
        processing_memory.session_id = session_id

        processing_memory_synced = len(memory_transcript_segements)
        processing_memory.transcript_segments = memory_transcript_segements[:processing_memory_synced]
        processing_memories_db.upsert_processing_memory(uid, processing_memory.dict())

        # Message: New processing memory created
        ok = await _send_message_event(NewProcessingMemoryCreated(
            event_type="new_processing_memory_created",
            processing_memory_id=processing_memory.id),
        )
        if not ok:
            print("Can not send message event new_processing_memory_created")

    async def _post_process_memory(memory: Memory):
        nonlocal processing_memory
        nonlocal processing_audio_frames
        nonlocal processing_audio_frame_synced

        # Create wav
        processing_audio_frame_synced = len(processing_audio_frames)
        file_path = f"_temp/{memory.id}_{uuid.uuid4()}_be"
        create_wav_from_bytes(file_path=file_path, frames=processing_audio_frames[:processing_audio_frame_synced],
                              frame_rate=sample_rate, channels=channels, codec=codec, )

        # Merge new audio with the previous
        if processing_memory.audio_url:
            previous_file_path = f"_temp/{memory.id}_{uuid.uuid4()}_be"
            download_postprocessing_audio(processing_memory.audio_url, previous_file_path)

            # merge
            merge_file_path = f"_temp/{memory.id}_{uuid.uuid4()}_be"
            merge_wav_files(merge_file_path, [previous_file_path, file_path])

            # clean
            os.remove(previous_file_path)
            os.remove(file_path)

            # new
            file_path = merge_file_path

        # Process
        emotional_feedback = processing_memory.emotional_feedback
        (status, new_memory) = postprocess_memory_util(memory.id, file_path, uid, emotional_feedback, )
        if status == 200:
            memory = new_memory
        else:
            print(f"Post processing failed {memory.id}")

        # Store postprocessing audio file
        signed_url = upload_postprocessing_audio(file_path)
        processing_memory.audio_url = signed_url
        processing_memories_db.update_processing_memory(uid, processing_memory.id, processing_memory.dict())

        os.remove(file_path)

        return memory

    # Create memory
    async def _create_memory():
        print("create memory")
        nonlocal processing_memory
        nonlocal processing_memory_synced
        nonlocal processing_audio_frames
        nonlocal processing_audio_frame_synced
        nonlocal memory_transcript_segements

        if not processing_memory:
            # Force create one
            await _create_processing_memory()
        else:
            # or ensure synced processing transcript
            processing_memories = processing_memories_db.get_processing_memories_by_id(uid, [processing_memory.id])
            if len(processing_memories) == 0:
                print("processing memory is not found")
                return
            processing_memory = ProcessingMemory(**processing_memories[0])

            processing_memory_synced = len(memory_transcript_segements)
            processing_memory.transcript_segments = memory_transcript_segements[:processing_memory_synced]
            processing_memories_db.update_processing_memory(uid, processing_memory.id, processing_memory.dict())

        # Message: creating
        ok = await _send_message_event(MessageEvent(event_type="new_memory_creating"))
        if not ok:
            print("Can not send message event new_memory_creating")

        # Not existed memory then create new one
        memory = None
        messages = []
        if not processing_memory.memory_id:
            (new_memory, new_messages, updated_processing_memory) = await create_memory_by_processing_memory(uid, processing_memory.id)
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
            memories_db.update_memory_segments(uid, memory.id, [segment.dict() for segment in memory.transcript_segments])
            
            # Process
            memory = process_memory(uid, memory.language, memory, force_process=True)

        # Post processing
        new_memory = await _post_process_memory(memory)
        if new_memory:
            memory = new_memory

        # Message: completed
        msg = NewMemoryCreated(event_type="new_memory_created",
                               processing_memory_id=processing_memory.id,
                               memory_id=memory.id,
                               memory=memory,
                               messages=messages, )
        ok = await _send_message_event(msg)
        if not ok:
            print("Can not send message event new_memory_created")

        return memory

    # New memory watch
    async def memory_transcript_segements_watch():
        nonlocal memory_watching
        nonlocal websocket_active
        while memory_watching and websocket_active:
            print(f"new memory watch, uid: {uid}, session: {session_id}")
            await asyncio.sleep(5)
            await _try_flush_new_memory_with_lock()

    async def _try_flush_new_memory_with_lock(time_validate: bool = True):
        with flush_new_memory_lock:
            return await _try_flush_new_memory(time_validate=time_validate)

    async def _try_flush_new_memory(time_validate: bool = True):
        nonlocal memory_transcript_segements
        nonlocal timer_start
        nonlocal processing_memory
        nonlocal processing_memory_synced
        nonlocal processing_audio_frames
        nonlocal processing_audio_frame_synced

        if not timer_start:
            print("not timer start")
            return

        # Validate last segment
        last_segment = None
        if len(memory_transcript_segements) > 0:
            last_segment = memory_transcript_segements[-1]
        if not last_segment:
            print("Not last segment or last segment invalid")
            if last_segment:
                print(f"{last_segment.dict()}")
            return

        # First chunk, create processing memory
        should_create_processing_memory = not processing_memory and len(memory_transcript_segements) > 0
        print(f"Should create processing {should_create_processing_memory}")
        if should_create_processing_memory:
            await _create_processing_memory()

        # Validate transcript
        # Longer 120s
        segment_end = last_segment.end
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
            processing_audio_frames = processing_audio_frames[processing_audio_frame_synced:]
            processing_audio_frame_synced = 0
            processing_memory = None

    try:
        receive_task = asyncio.create_task(receive_audio(transcript_socket, transcript_socket2))
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
        channels: int = 1, include_speech_profile: bool = True, new_memory_watch: bool = False
):
    await _websocket_util(websocket, uid, language, sample_rate, codec, channels, include_speech_profile,
                          new_memory_watch)

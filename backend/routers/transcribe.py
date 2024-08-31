import asyncio
import time
import asyncio
import os
import threading
import uuid
from datetime import datetime

from models.message_event import NewMemoryCreated, MessageEvent
from models.processing_memory import ProcessingMemory
from models.memory import Memory, PostProcessingModel, PostProcessingStatus, MemoryPostProcessing, TranscriptSegment
from utils.memories.process_memory import process_memory
from utils.memories.location import get_google_maps_location
from utils.plugins import trigger_external_integrations
from utils.processing_memories import create_memory_by_processing_memory
import database.processing_memories as processing_memories_db
import database.memories as memories_db

from fastapi import APIRouter
from fastapi.websockets import (WebSocketDisconnect, WebSocket)
from starlette.websockets import WebSocketState
from utils.stt.streaming import process_segments

from database.redis_db import get_user_speech_profile, get_user_speech_profile_duration
from utils.stt.streaming import process_audio_dg, send_initial_file
from utils.stt.vad import VADIterator, model

# import opuslib

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
        # Should not close here, maybe used by deepgram
        # await websocket.close()
        return

    # Processing memory
    processing_memory = None

    # Stream transcript
    memory_stream_id = 1
    memory_transcript_segements = []
    speech_profile_stream_id = 2
    loop = asyncio.get_event_loop()

    def stream_transcript(segments, stream_id):
        nonlocal websocket

        print("Received transcript segments")
        print(segments)

        asyncio.run_coroutine_threadsafe(websocket.send_json(segments), loop)
        threading.Thread(target=process_segments, args=(uid, segments)).start()

        # memory segments
        if stream_id == memory_stream_id and new_memory_watch:
            memory_transcript_segements.extend(segments)

            # Sync processing transcript, periodly
            if processing_memory and len(memory_transcript_segements) % 3 == 0:
                new_segments = memory_transcript_segements[len(processing_memory.transcript_segments):]
                processing_memory.transcript_segments.extend(list(map(lambda m: TranscriptSegment(**m), new_segments)))
                processing_memories_db.update_processing_memory(uid, processing_memory.id, processing_memory.dict())

    # Process
    transcript_socket2 = None
    websocket_active = True
    timer_start = None
    duration = 0
    try:
        if language == 'en' and codec == 'opus' and include_speech_profile:
            speech_profile = get_user_speech_profile(uid)
            duration = get_user_speech_profile_duration(uid)
            print('speech_profile', len(speech_profile), duration)
            if duration:
                duration += 20
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
        await websocket.close()
        return

    vad_iterator = VADIterator(model, sampling_rate=sample_rate)  # threshold=0.9
    window_size_samples = 256 if sample_rate == 8000 else 512

    async def receive_audio(socket1, socket2):
        nonlocal websocket_active
        nonlocal timer_start
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

                audio_buffer = bytearray()

        except WebSocketDisconnect:
            print("WebSocket disconnected")
        except Exception as e:
            print(f'Could not process audio: error {e}')
        finally:
            websocket_active = False
            socket1.finish()
            if socket2:
                socket2.finish()

    # heart beat
    async def send_heartbeat():
        nonlocal websocket_active
        try:
            while websocket_active:
                await asyncio.sleep(30)
                # print('send_heartbeat')
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_json({"type": "ping"})
                else:
                    break
        except WebSocketDisconnect:
            print("WebSocket disconnected")
        except Exception as e:
            print(f'Heartbeat error: {e}')
        finally:
            websocket_active = False

    # new proccesing memory
    async def _create_processing_memory():
        nonlocal processing_memory
        nonlocal memory_transcript_segements
        try:
            processing_memory = ProcessingMemory(
                id=str(uuid.uuid4()),
                created_at=datetime.utcnow(),
                timer_start=timer_start,
                language=language,
            )
            processing_memory.transcript_segments = list(map(lambda m: TranscriptSegment(**m), memory_transcript_segements))
            processing_memories_db.upsert_processing_memory(uid, processing_memory.dict())

            # send processing memory created
            await websocket.send_json({"type": "new_processing_memory_created", "processing_memory_id": processing_memory.id})

        except WebSocketDisconnect:
            print("WebSocket disconnected")
        except Exception as e:
            print(f'Can not create processing memory error: {e}')
        finally:
            pass

    async def _create_memory():
        print(f"create memory")
        nonlocal processing_memory
        try:
            if not processing_memory:
                await _create_processing_memory()  # force create one
                return

            # Message: creating
            await websocket.send_json({"type": "new_memory_creating", })

            # Create memory
            (memory, messages) = await create_memory_by_processing_memory(uid, processing_memory.id)
            if not memory:
                print("Can not create new memory")
                # Message: failed
                await websocket.send_json({"type": "new_memory_create_failed", })
                return

            # Message: completed
            event_type = "new_memory_created"
            msg = NewMemoryCreated(event_type=event_type,
                                   processing_memory_id=processing_memory.id,
                                   memory_id=memory.id,
                                   memory=memory,
                                   messages=messages,).model_dump(mode="json")
            msg["type"] = event_type
            print(msg)
            await websocket.send_json(msg)

        except WebSocketDisconnect:
            print("WebSocket disconnected")
        except Exception as e:
            print(f'Can not create memory: {e}')
        finally:
            pass

    # New memory watch
    async def memory_transcript_segements_watch():
        nonlocal memory_transcript_segements
        nonlocal timer_start
        while True:
            print("new memory watch")
            await asyncio.sleep(5)

            if not timer_start:
                print("not timer start")
                continue

            # last segment
            last_segment = None
            if len(memory_transcript_segements) > 0:
                last_segment = memory_transcript_segements[-1]
            if not last_segment or "end" not in last_segment:
                print(f"not last segment or invalid")
                if last_segment:
                    print(f"{last_segment.dict()}")
                continue

            # first chunk, create processing memory
            should_create_processing_memory = len(memory_transcript_segements) > 0 \
                and not processing_memory
            print(f"should create processing {should_create_processing_memory}")
            if should_create_processing_memory:
                await _create_processing_memory()

            # debounce 15s, 15 words at least
            segment_end = int(last_segment["end"])
            now = time.time()
            should_create_memory = (timer_start + segment_end + 15 < now)
            if should_create_memory:
                should_create_memory = False
                wc = 0
                for segment in memory_transcript_segements:
                    wc = wc + len(segment["text"].split(" "))
                    if wc >= 15:
                        should_create_memory = True
                        break
            print(f"should create memory {timer_start} {segment_end} {now} {should_create_memory}")
            if should_create_memory:
                # Ensure synced processing transcript
                if processing_memory:
                    processing_memory.transcript_segments = list(map(lambda m: TranscriptSegment(**m), memory_transcript_segements))
                    processing_memories_db.update_processing_memory(uid, processing_memory.id, processing_memory.dict())

                # Create memory
                await _create_memory()
                break

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
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close()
            except Exception as e:
                print(f"Error closing WebSocket: {e}")


@ router.websocket("/listen")
async def websocket_endpoint(
        websocket: WebSocket, uid: str, language: str = 'en', sample_rate: int = 8000, codec: str = 'pcm8',
        channels: int = 1, include_speech_profile: bool = True, new_memory_watch: bool = False
):
    print("here")
    await _websocket_util(websocket, uid, language, sample_rate, codec, channels, include_speech_profile, new_memory_watch)

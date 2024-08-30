import asyncio
import time
import asyncio
import os
import threading
import uuid
from datetime import datetime

from models.processing_memory import ProcessingMemory
from models.memory import Memory, PostProcessingModel, PostProcessingStatus, MemoryPostProcessing, TranscriptSegment
from utils.memories.process_memory import process_memory
from utils.memories.location import get_google_maps_location
from utils.plugins import trigger_external_integrations
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
        channels: int = 1, include_speech_profile: bool = True,
):
    print('websocket_endpoint', uid, language, sample_rate, codec, channels, include_speech_profile)

    # Check: Why do we need try-catch around websocket.accept?
    try:
        await websocket.accept()
    except RuntimeError as e:
        print(e)
        # Should not close here, maybe used by deepgram
        # await websocket.close()
        return

    # processing memory
    processing_memory_id = None

    # Stream transcript
    memory_stream_id = 1
    memory_transcript_segements = []
    speech_profile_stream_id = 2
    loop = asyncio.get_event_loop()

    async def stream_transcript(segments, stream_id):
        asyncio.run_coroutine_threadsafe(websocket.send_json(segments), loop)
        threading.Thread(target=process_segments, args=(uid, segments)).start()

        # memory segments
        if stream_id == memory_stream_id:
            memory_transcript_segements.extend(segments)

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

    async def _create_processing_memory():
        try:
            processing_memory = ProcessingMemory(
                id=str(uuid.uuid4()),
                created_at=datetime.utcnow(),
            )
            processing_memories_db.upsert_processing_memory(uid, processing_memory.dict())

            # send processing memory created
            await websocket.send_json({"type": "new_processing_memory_created", "processing_memory_id": processing_memory.id})

        except WebSocketDisconnect:
            print("WebSocket disconnected")
        except Exception as e:
            print(f'Can not create processing memory error: {e}')
            # TODO: send create new memory failed
        finally:
            pass

    async def _create_memory():
        nonlocal processing_memory_id
        nonlocal memory_transcript_segements
        try:
            if not processing_memory_id:
                print("processing memory is not initiated")
                return

            # Fetch new
            processing_memories = processing_memories_db.get_processing_memories_by_id(uid, [processing_memory_id])
            if len(processing_memories) == 0:
                print("processing memory is not found")
                return
            processing_memory = ProcessingMemory(**processing_memories[0])

            # Send message
            await websocket.send_json({"type": "new_memory_creating", })

            # Create memory
            segment_end = memory_transcript_segements[len(memory_transcript_segements)-1]["end"]
            create_memory = Memory(
                id=str(uuid.uuid4()),
                uid=uid,
                started_at=datetime.fromtimestamp(timer_start),
                finished_at=datetime.fromtimestamp(timer_start + segment_end),
                language=processing_memory.language,
            )
            transcript_segments = memory_transcript_segements
            if not transcript_segments or len(transcript_segments) == 0:
                print("Transcript segments is invalid")
                await websocket.send_json({"type": "new_memory_create_failed", })
                return
            create_memory.transcript_segments = map(lambda m: TranscriptSegment(**m), transcript_segments)

            geolocation = processing_memory.geolocation
            if geolocation and not geolocation.google_place_id:
                create_memory.geolocation = get_google_maps_location(geolocation.latitude, geolocation.longitude)

            language_code = create_memory.language
            memory = process_memory(uid, language_code, create_memory)
            if not processing_memory.trigger_integrations:
                await websocket.send_json({"type": "new_memory_created", "processing_memory_id": processing_memory.id, "memory_id": memory.id})

                # update
                processing_memory.memory_id = memory.id
                processing_memories_db.update_processing_memory(uid, processing_memory.id, processing_memory.dict())
                return

            if not memory.discarded:
                memories_db.set_postprocessing_status(uid, memory.id, PostProcessingStatus.not_started)
                memory.postprocessing = MemoryPostProcessing(status=PostProcessingStatus.not_started,
                                                             model=PostProcessingModel.fal_whisperx)

            messages = trigger_external_integrations(uid, memory)

            # update
            processing_memory.message_ids = map(lambda m: m.id, messages)
            processing_memories_db.update_processing_memory(uid, processing_memory.id, processing_memory.dict())

            # Comleted message
            await websocket.send_json({"type": "new_memory_created", "processing_memory_id": processing_memory.id, "memory_id": memory.id})

        except WebSocketDisconnect:
            print("WebSocket disconnected")
        except Exception as e:
            print(f'Can not create memory: {e}')
            # TODO: throw new memory created failed
        finally:
            pass

    # new memory watch
    async def memory_transcript_segements_watch():
        nonlocal memory_transcript_segements
        nonlocal timer_start
        while True:
            await asyncio.sleep(5)

            if not timer_start:
                continue

            # last segment
            last_segment = None
            if len(memory_transcript_segements) > 0:
                last_segment = memory_transcript_segements[len(memory_transcript_segements)-1]
            if not last_segment or "end" not in last_segment:
                continue

            # first chunk, create processing memory
            should_create_processing_memory = len(memory_transcript_segements) > 0
            if should_create_processing_memory:
                _create_processing_memory()

            # Should count words
            should_create_memory = (int(last_segment["end"]) + timer_start + 15 < time.time()) and (len(memory_transcript_segements) >= 3)
            if should_create_memory:
                _create_memory()
                break

    try:
        receive_task = asyncio.create_task(receive_audio(transcript_socket, transcript_socket2))
        heartbeat_task = asyncio.create_task(send_heartbeat())
        new_memory_task = asyncio.create_task(memory_transcript_segements_watch())
        await asyncio.gather(receive_task, new_memory_task, heartbeat_task)
    except Exception as e:
        print(f"Error during WebSocket operation: {e}")
    finally:
        websocket_active = False
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close()
            except Exception as e:
                print(f"Error closing WebSocket: {e}")


@router.websocket("/listen")
async def websocket_endpoint(
        websocket: WebSocket, uid: str, language: str = 'en', sample_rate: int = 8000, codec: str = 'pcm8',
        channels: int = 1, include_speech_profile: bool = True
):
    await _websocket_util(websocket, uid, language, sample_rate, codec, channels, include_speech_profile)

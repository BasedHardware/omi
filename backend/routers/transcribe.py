import asyncio
import os
import time
import uuid

from fastapi import APIRouter, UploadFile
from fastapi.websockets import (WebSocketDisconnect, WebSocket)
from pydub import AudioSegment
from starlette.websockets import WebSocketState
import torch
import numpy as np
from collections import deque

from utils.redis_utils import get_user_speech_profile, get_user_speech_profile_duration
from utils.stt.deepgram_util import process_audio_dg, send_initial_file2, transcribe_file_deepgram
from utils.stt.vad import VADIterator, model, get_speech_state, SpeechState, vad_is_empty, is_speech_present

router = APIRouter()


# @router.post("/v1/transcribe", tags=['v1'])
# will be used again in Friend V2
def transcribe_auth(file: UploadFile, uid: str, language: str = 'en'):
    upload_id = str(uuid.uuid4())
    file_path = f"_temp/{upload_id}_{file.filename}"
    with open(file_path, 'wb') as f:
        f.write(file.file.read())

    aseg = AudioSegment.from_wav(file_path)
    print(f'Transcribing audio {aseg.duration_seconds} secs and {aseg.frame_rate / 1000} khz')

    if vad_is_empty(file_path):  # TODO: get vad segments
        os.remove(file_path)
        return []
    transcript = transcribe_file_deepgram(file_path, language=language)
    os.remove(file_path)
    return transcript


# templates = Jinja2Templates(directory="templates")

# @router.get("/", response_class=HTMLResponse) // FIXME
# def get(request: Request):
#     return templates.TemplateResponse("index.html", {"request": request})


async def _websocket_util(
        websocket: WebSocket, uid: str, language: str = 'en', sample_rate: int = 8000, codec: str = 'pcm8',
        channels: int = 1, include_speech_profile: bool = True,
):
    print('websocket_endpoint', uid, language, sample_rate, codec, channels, include_speech_profile)
    await websocket.accept()
    transcript_socket2 = None
    websocket_active = True
    duration = 0
    is_speech_active = False
    speech_timeout = 1.0  # Configurable even better if we can decade from user needs/behaviour
    last_speech_time = 0
    try:
        if language == 'en' and codec == 'opus' and include_speech_profile:
            speech_profile = get_user_speech_profile(uid)
            duration = get_user_speech_profile_duration(uid)
            print('speech_profile', len(speech_profile), duration)
            if duration:
                duration += 10
        else:
            speech_profile, duration = [], 0

        transcript_socket = await process_audio_dg(uid, websocket, language, sample_rate, codec, channels,
                                                   preseconds=duration)
        if duration:
            transcript_socket2 = await process_audio_dg(uid, websocket, language, sample_rate, codec, channels)
            await send_initial_file2(speech_profile, transcript_socket)

    except Exception as e:
        print(f"Initial processing error: {e}")
        await websocket.close()
        return

    vad_iterator = VADIterator(model, sampling_rate=sample_rate)  # threshold=0.9
    window_size_samples = 256 if sample_rate == 8000 else 512

    async def receive_audio(socket1, socket2):
        audio_buffer = deque(maxlen=sample_rate * 3)  # 3 secs
        nonlocal is_speech_active, last_speech_time, websocket_active
        timer_start = time.time()
        speech_state = SpeechState.no_speech
        voice_found, not_voice = 0, 0
        # path = 'scripts/vad/audio_bytes.txt'
        # if os.path.exists(path):
        #     os.remove(path)
        # audio_file = open(path, "a")
        try:
            while websocket_active:
                data = await websocket.receive_bytes()
                # print(len(data))
                if codec == 'opus':
                    audio = AudioSegment(data=data, sample_width=2, frame_rate=sample_rate, channels=channels)
                    samples = torch.tensor(audio.get_array_of_samples()).float() / 32768.0
                elif codec in ['pcm8', 'pcm16']:
                    dtype = torch.int8 if codec == 'pcm8' else torch.int16
                    samples = torch.frombuffer(data, dtype=dtype).float()
                    samples = samples / (128.0 if codec == 'pcm8' else 32768.0)
                else:
                    raise ValueError(f"Unsupported codec: {codec}")
                
                audio_buffer.extend(samples)
                # print(len(audio_buffer), window_size_samples * 2) # * 2 because 16bit
                # TODO: vad not working propperly.
                # - PCM still has to collect samples, and while it collects them, still sends them to the socket, so it's like nothing
                # - Opus always says there's no speech (but collection doesn't matter much, as it triggers like 1 per 0.2 seconds)

                # len(data) = 160, 8khz 16bit -> 2 bytes per sample, 80 samples, needs 256 samples, which is 256*2 bytes
                if len(audio_buffer) >= window_size_samples * 2:
                    tensor_audio = torch.tensor(list(audio_buffer))
                    if is_speech_present(tensor_audio, vad_iterator, window_size_samples):
                        print('+Detected speech')
                        is_speech_active = True
                        last_speech_time = time.time()
                    elif is_speech_active:
                        if time.time() - last_speech_time > speech_timeout:
                            is_speech_active = False
                            print('-NO Detected speech')
                            continue
                        print('+Detected speech')
                    else:
                        print('-NO Detected speech')
                        continue
            
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

    try:
        receive_task = asyncio.create_task(receive_audio(transcript_socket, transcript_socket2))
        heartbeat_task = asyncio.create_task(send_heartbeat())
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


@router.websocket("/listen")
async def websocket_endpoint(
        websocket: WebSocket, uid: str, language: str = 'en', sample_rate: int = 8000, codec: str = 'pcm8',
        channels: int = 1, include_speech_profile: bool = True
):
    await _websocket_util(websocket, uid, language, sample_rate, codec, channels, include_speech_profile)

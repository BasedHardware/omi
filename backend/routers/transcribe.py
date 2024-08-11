import asyncio
import os
import time
import uuid

from fastapi import APIRouter, UploadFile
from fastapi.websockets import (WebSocketDisconnect, WebSocket)
from pydub import AudioSegment
from starlette.websockets import WebSocketState
import torch
from collections import deque
import opuslib

from utils.redis_utils import get_user_speech_profile, get_user_speech_profile_duration
from utils.stt.deepgram_util import process_audio_dg, send_initial_file2, transcribe_file_deepgram, convert_pcm8_to_pcm16
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
    speech_timeout = 0.7  # Configurable even better if we can decade from user needs/behaviour
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

    threshold = 0.6 # Currently most fitting threshold
    vad_iterator = VADIterator(model, sampling_rate=sample_rate, threshold=threshold) 
    window_size_samples = 256 if sample_rate == 8000 else 512
    if codec == 'opus':
        decoder = opuslib.Decoder(sample_rate, channels)

    async def receive_audio(socket1, socket2):
        nonlocal is_speech_active, last_speech_time, decoder, websocket_active
        audio_buffer = deque(maxlen=sample_rate * 1)  # 1 secs
        databuffer = bytearray(b"")
        
        REALTIME_RESOLUTION = 0.01
        if codec == 'pcm8':
            sample_width = 1
        else:
            sample_width = 2
        if sample_width:
            byte_rate = sample_width * sample_rate * channels
            chunk_size = int(byte_rate * REALTIME_RESOLUTION)
        else:
            chunk_size = 4096 # Arbitrary value
            
        timer_start = time.time()
        speech_state = SpeechState.no_speech
        voice_found, not_voice = 0, 0
        # path = 'scripts/vad/audio_bytes.txt'
        # if os.path.exists(path):
        #     os.remove(path)
        # audio_file = open(path, "a")
        try:
            sample_width = 1 if codec == "pcm8" else 2
            while websocket_active:
                data = await websocket.receive_bytes()
                if codec == 'opus':
                    data = decoder.decode(data, frame_size=320) # 160 if want lower latency
                    # audio = AudioSegment(data=data, sample_width=sample_width, frame_rate=sample_rate, channels=channels, format='opus')
                    # samples = torch.tensor(audio.get_array_of_samples()).float() / 32768.0
                    samples = torch.frombuffer(data, dtype=torch.int16).float() / 32768.0
                elif codec in ['pcm8', 'pcm16']:
                    dtype = torch.int8 if codec == 'pcm8' else torch.int16
                    writeable_data = bytearray(data)
                    samples = torch.frombuffer(writeable_data, dtype=dtype).float()
                    samples = samples / (128.0 if codec == 'pcm8' else 32768.0)
                else:
                    raise ValueError(f"Unsupported codec: {codec}")
                
                audio_buffer.extend(samples)
                # print(len(audio_buffer), window_size_samples * 2) # * 2 because 16bit
                # len(data) = 160, 8khz 16bit -> 2 bytes per sample, 80 samples, needs 256 samples, which is 256*2 bytes
                if len(audio_buffer) >= window_size_samples * 2:
                    tensor_audio = torch.tensor(list(audio_buffer))
                    if is_speech_present(tensor_audio[len(tensor_audio) - window_size_samples * 2 :], vad_iterator, window_size_samples):
                        # print('+Detected speech')
                        is_speech_active = True
                        last_speech_time = time.time()
                    elif is_speech_active:
                        if time.time() - last_speech_time > speech_timeout:
                            is_speech_active = False
                            # Clear only happens after the speech timeout
                            audio_buffer.clear()
                            # print('-NO Detected speech')
                            continue
                    else:
                        continue
            
                elapsed_seconds = time.time() - timer_start
                if elapsed_seconds > duration or not socket2:
                    if codec == 'pcm8': # DG does not support pcm8 directly
                        data = convert_pcm8_to_pcm16(data)
                    databuffer.extend(data)
                    if len(databuffer) >= chunk_size:
                        socket1.send(databuffer[:len(databuffer) - len(databuffer) % chunk_size])
                        databuffer = databuffer[len(databuffer) - len(databuffer) % chunk_size:]
                        await asyncio.sleep(REALTIME_RESOLUTION)
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

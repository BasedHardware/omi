import asyncio
import time

from fastapi import APIRouter
from fastapi.websockets import (WebSocketDisconnect, WebSocket)
from starlette.websockets import WebSocketState
import torch
from collections import deque
import opuslib

from database.redis_db import get_user_speech_profile, get_user_speech_profile_duration
from utils.stt.streaming import process_audio_dg, send_initial_file
from utils.stt.vad import VADIterator, model, is_speech_present

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
    speech_timeout = 2.0 # Good for now (who doesnt like integer) but better dynamically adjust it by user behaviour, just idea: Increase as active time passes but until certain threshold, but not needed yet.
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
            await send_initial_file(speech_profile, transcript_socket)

    except Exception as e:
        print(f"Initial processing error: {e}")
        await websocket.close()
        return

    threshold = 0.7
    vad_iterator = VADIterator(model, sampling_rate=sample_rate, threshold=threshold) 
    window_size_samples = 256 if sample_rate == 8000 else 512
    if codec == 'opus':
        decoder = opuslib.Decoder(sample_rate, channels)

    async def receive_audio(socket1, socket2):
        nonlocal is_speech_active, last_speech_time, websocket_active, decoder
        
        REALTIME_RESOLUTION = 0.025
        sample_width = 2  # pcm8/16 here is 16 bit
        byte_rate = sample_width * sample_rate * channels
        # chunk_size = int(byte_rate * REALTIME_RESOLUTION)
        audio_buffer = deque(maxlen=window_size_samples)
        databuffer = bytearray(b"")
        prespeech_audio = deque(maxlen=int(byte_rate * 0.5))
            
        timer_start = time.time()
        audio_cursor = 0 # For sleep realtime logic
        last_vad_check_time = 0
        opus_vad_check_interval = speech_timeout/40  # interval for Opus VAD checks

        try:
            while websocket_active:
                data = await websocket.receive_bytes()
                recv_time = time.time()
                if codec == 'opus':
                    copy_opus_byte = bytes(data)
                    decoded_opus = decoder.decode(copy_opus_byte, frame_size=160) # Version Firmware v1.0
                    writable_opus_data = bytearray(decoded_opus)
                    samples = torch.frombuffer(writable_opus_data, dtype=torch.int16).float() / 32768.0
                elif codec in ['pcm8', 'pcm16']:  # Both are 16 bit
                    writable_data = bytearray(data)
                    samples = torch.frombuffer(writable_data, dtype=torch.int16).float() / 32768.0
                else:
                    raise ValueError(f"Unsupported codec: {codec}")
                audio_buffer.extend(samples)
                if codec in ['pcm8', 'pcm16']:
                    if len(audio_buffer) >= window_size_samples:
                        tensor_audio = torch.tensor(list(audio_buffer))
                        if is_speech_present(tensor_audio[-window_size_samples:], vad_iterator, window_size_samples):
                            if not is_speech_active:
                                for audio in prespeech_audio:
                                    databuffer.extend(audio.int().numpy().tobytes())
                                prespeech_audio.clear()
                                print('+Detected speech')
                            is_speech_active = True
                            last_speech_time = recv_time
                        elif is_speech_active:
                            if recv_time - last_speech_time > speech_timeout:
                                is_speech_active = False
                                vad_iterator.reset_states()
                                prespeech_audio.extend(samples)
                                print('-NO Detected speech')
                                continue
                        else:
                            prespeech_audio.extend(samples)
                            continue
                elif codec == 'opus':
                    # CHeck VAD for Opus every vad_check_interval
                    if recv_time - last_vad_check_time >= opus_vad_check_interval and not is_speech_active:
                        last_vad_check_time = recv_time
                        if len(audio_buffer) >= window_size_samples:
                            tensor_audio = torch.tensor(list(audio_buffer))
                            if is_speech_present(tensor_audio[-window_size_samples:], vad_iterator, window_size_samples):
                                print('!+ Start Detected speech\n')
                                is_speech_active = True
                                last_speech_time = recv_time
                    elif is_speech_active and recv_time - last_vad_check_time >= speech_timeout/2 :
                        last_vad_check_time += speech_timeout/30
                        if len(audio_buffer) >= window_size_samples:
                            tensor_audio = torch.tensor(list(audio_buffer))
                            if is_speech_present(tensor_audio[-window_size_samples:], vad_iterator, window_size_samples):
                                print("+ Still active but detected speech\n")
                                last_vad_check_time += speech_timeout/2
                                last_speech_time = recv_time
                            elif recv_time - last_speech_time > speech_timeout:
                                print("- No detected while active, reverting to no active speech\n")
                                is_speech_active = False
                                vad_iterator.reset_states()
                                continue
                    
                    if not is_speech_active:
                        continue
                
                elapsed_seconds = recv_time - timer_start
                databuffer.extend(data)
                # Sleep logic, because naive sleep is not accurate
                current_time = time.time()
                elapsed_time = current_time - timer_start
                if elapsed_time < audio_cursor + REALTIME_RESOLUTION:
                    sleep_time = (audio_cursor + REALTIME_RESOLUTION) - elapsed_time
                    await asyncio.sleep(sleep_time)
                    
                if elapsed_seconds > duration or not socket2:
                    # Just send them all, no difference
                    socket1.send(databuffer)
                    if socket2:
                        print('Killing socket2')
                        socket2.finish()
                        socket2 = None
                else:
                    # Socket2 send all too
                    socket2.send(databuffer)
                    
                databuffer = bytearray(b"")
                audio_cursor += REALTIME_RESOLUTION

        except WebSocketDisconnect as e:
            print(f"WebSocket disconnected: {e}")
        except Exception as e:
            print(f'Could not process websocket audio: error {e}')
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
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_json({"type": "ping"})
                else:
                    break
        except WebSocketDisconnect as e:
            print(f"WebSocket disconnected: {e}")
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

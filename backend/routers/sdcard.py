import asyncio
import uuid
import datetime

from fastapi import APIRouter
from fastapi.websockets import WebSocketDisconnect, WebSocket
from pydub import AudioSegment

from models.memory import *
from utils.audio import create_wav_from_bytes
from utils.memories.process_memory import process_memory
from utils.other.storage import upload_sdcard_audio
from utils.stt.pre_recorded import fal_whisperx, fal_postprocessing
from utils.stt.vad import vad_is_empty

router = APIRouter()


# TODO: version -> /v1/sdcard_stream
@router.websocket("/sdcard_stream")
async def sdcard_streaming_endpoint(websocket: WebSocket, uid: str):
    try:
        await websocket.accept()
    except RuntimeError as e:
        print(e)
        return

    # activate the websocket
    websocket_active = True
    session_id = str(uuid.uuid4())
    big_file_path = f"_temp/_temp{session_id}.wav"
    first_packet_flag = False
    data_packet_length = 83
    # data_packet_length = 440
    seconds_until_timeout = 10.0
    audio_frames = []

    try:
        while websocket_active:
            if first_packet_flag:
                data = await asyncio.wait_for(websocket.receive_bytes(), timeout=seconds_until_timeout)

            else:
                data = await websocket.receive_bytes()

            if len(data) == data_packet_length:  # valid packet size
                if not first_packet_flag:
                    first_packet_flag = True
                    print('first valid packet received')
            elif len(data) == 440:
                if not first_packet_flag:
                    first_packet_flag = True
                    print('first valid packet received')
            if data == 100:  # valid code
                print('done.')
                websocket_active = False
                break
            amount = int(data[3])
            frame_to_decode = bytes(list(data[4:4 + amount]))
            audio_frames.append(frame_to_decode)

    except WebSocketDisconnect:
        print("websocket gone")
    except asyncio.TimeoutError:
        print('timeout condition, exitting')
    except Exception as e:
        print('something went wrong')
    finally:
        websocket_active = False
    frames_per_second = 100.0
    file_seconds = len(audio_frames) / frames_per_second
    if file_seconds < 5.0:  
        print('audio file too small')
        return

    create_wav_from_bytes(big_file_path, audio_frames, "opus", 16000, 1, 2)

    try:
        vad_segments = vad_is_empty(big_file_path, return_segments=True)
        print(vad_segments)
        if vad_segments:
            temp_file_list = []
            vad_segments_combined = combine_vad_segments(vad_segments)
            aseg = AudioSegment.from_wav(big_file_path)

            for i, segments in enumerate(vad_segments_combined):
                start, end = segments['start'], segments['end']

                segment_aseg = aseg[max(0, (start - 1) * 1000):min((end + 1) * 1000, aseg.duration_seconds * 1000)]
                temp_file_name = f"_temp/{session_id}_{i}.wav"
                segment_aseg.export(temp_file_name, format="wav")

                temp_file_list.append(temp_file_name)

        else:
            print('nothing worth using memory for')
            return

        for file, segments in zip(temp_file_list, vad_segments_combined):
            signed_url = upload_sdcard_audio(file)
            words = fal_whisperx(signed_url, 4, 2)
            fal_segments = fal_postprocessing(words, 0)
            print(fal_segments)
            # TODO: need to detect language here for each, whisperx should be able to return that in the response.
            if not fal_segments:
                print('failed to get fal segments')
                continue
            temp_memory = CreateMemory(
                started_at=datetime.datetime.now(datetime.UTC),
                finished_at=datetime.datetime.now(datetime.UTC),
                transcript_segments=fal_segments,
                source=MemorySource.sdcard,
                language='en'
            )
            result: Memory = process_memory(uid, temp_memory.language, temp_memory, force_process=False)
            # TODO: should use the websocket to send each memory as created to the client, check transcribe_v2.py
            # websocket.send_json(result.to_json()) 
        await websocket.send_json({"type": "done"})

    except Exception as e:
        print('error bruf')
        print(e)
        return

    print('finished')
    return


def combine_vad_segments(vad_segments):
    seconds_between_conversations = 120.0
    if len(vad_segments) == 1:
        return vad_segments
    segments_result = []
    temp_segment = None
    for i in range(len(vad_segments)):
        if not temp_segment:
            temp_segment = vad_segments[i]
            continue
        else:
            if (vad_segments[i]['start'] - vad_segments[i - 1]['end']) > seconds_between_conversations:
                segments_result.append(temp_segment)
                temp_segment = vad_segments[i]
            else:
                temp_segment['end'] = vad_segments[i]['end']
    if temp_segment is not None:
        segments_result.append(temp_segment)
    return segments_result
'''

packets are as follows:

[a ...... b..... c...... d.....]

'''
#data_packet_size
def split_segments(socket_segments):
    result = []
    max_packet_size_idx = 440 - 1

    current_packet_size = 0
    
    if not socket_segments:
        return []
    offset = 0
    while True:
        current_packet_size = socket_segments[offset]
        if (current_packet_size + offset   > max_packet_size_idx):
            break
        elif (current_packet_size + offset == max_packet_size_idx):
            result.append(socket_segments[offset+1:offset+current_packet_size])
            break
        elif (current_packet_size + offset  < max_packet_size_idx):
            result.append(socket_segments[offset+1:offset+current_packet_size])
            offset+=current_packet_size+1
            continue
        
    return result
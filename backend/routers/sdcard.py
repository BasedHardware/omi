import os
from typing import Optional
import os
from models.memory import *
import requests
from fastapi import APIRouter, FastAPI,Depends, HTTPException, UploadFile
from utils.memories.process_memory import process_memory, process_user_emotion
from utils.other.storage import upload_sdcard_audio,create_signed_postprocessing_audio_url
from utils.other import endpoints as auth
import datetime
import uuid
from utils.stt.pre_recorded import fal_whisperx, fal_postprocessing
from utils.audio import create_wav_from_bytes
from utils.stt.vad import vad_is_empty
from fastapi.websockets import WebSocketDisconnect, WebSocket
from starlette.websockets import WebSocketState
from utils.stt.vad import VADIterator, model
import asyncio
import opuslib
from pydub import AudioSegment
import time
router = APIRouter()

@router.websocket("/sdcard_stream")
async def sdcard_streaming_endpoint(
        websocket: WebSocket, uid: str,bt_connected_time: str
):

    bt_connected_time_dt = datetime.datetime.strptime(bt_connected_time, '%Y-%m-%d %H:%M:%S.%fZ').replace(tzinfo=datetime.timezone.utc)
    
    try:
        await websocket.accept()
    except RuntimeError as e:
        print(e)
        return
    
    #activate the websocket
    websocket_active = True
    session_id = str(uuid.uuid4())
    big_file_path = f"_temp/_temp{session_id}.wav"
    first_packet_flag=False
    data_packet_length=83
    packet_count = 0
    seconds_until_timeout = 10.0
    audio_frames = []

    try:
        while websocket_active:
            if first_packet_flag:
                data = await asyncio.wait_for(websocket.receive_bytes(), timeout=seconds_until_timeout)

            else:
                data = await websocket.receive_bytes()

            if (len(data) == data_packet_length): #valid packet size
                if not first_packet_flag:
                    first_packet_flag = True
                    print('first valid packet received')
            if data == 100: #valid code
                print('done.')
                websocket_active = False
                break
            amount = int(data[3])
            frame_to_decode = bytes(list(data[4:4+amount]))
            audio_frames.append(frame_to_decode)

    except WebSocketDisconnect:
        print("websocket gone")
    except asyncio.TimeoutError:
        print('timeout condition, exitting')
        websocket_active = False
    except Exception as e:
        print('somethign went wrong')
    finally:
        websocket_active = False
    duration_of_file = len(audio_frames) / 100.0
    if duration_of_file < 5.0:#seconds
        print('audio file too small')
        return 
    
    create_wav_from_bytes(big_file_path, audio_frames, "opus", 16000, 1, 2)

    try:
        temp_file_path = f"_temp/{session_id}"#+file_num .wav
        current_file_num = 1
        temp_file_name = 'temp' + str(current_file_num)

        
        vad_segments = vad_is_empty(big_file_path, return_segments=True)
        print(vad_segments)
        temp_file_list = []
        vad_segments_combined = []
        if vad_segments:
            vad_segments_combined = combine_val_segments(vad_segments)
            for segments in vad_segments_combined:
                
                start = segments['start']
                end = segments['end']
                aseg = AudioSegment.from_wav(big_file_path)
                aseg = aseg[max(0, (start - 1) * 1000):min((end + 1) * 1000, aseg.duration_seconds * 1000)]
                temp_file_name = temp_file_path + str(current_file_num) + '.wav'
                temp_file_list.append(temp_file_name)
                aseg.export(temp_file_name, format="wav")
                current_file_num+=1
                
        else:
            print('nothing worth using memory for')
            return 
            
        for file, segments in zip(temp_file_list,vad_segments_combined):
            signed_url = upload_sdcard_audio(file)
            aseg = AudioSegment.from_wav(file)
            words = fal_whisperx(signed_url, 1, 2)
            duration_entire_process = datetime.datetime.now(datetime.timezone.utc)
            time_to_subtract = (duration_entire_process - bt_connected_time_dt).total_seconds()
            zero_base = duration_of_file
            fal_segments = fal_postprocessing(words, aseg.duration_seconds)
            print(fal_segments)
            if not fal_segments:
                print('failed to get fal segments')
                continue
            temp_memory = CreateMemory(
            started_at= datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(seconds=time_to_subtract+zero_base-segments['start']),
            finished_at= datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(seconds=time_to_subtract+zero_base-segments['end']),
    
            transcript_segments = fal_segments,
            source= MemorySource.sdcard,
            language = 'en'
            )
            result: Memory = process_memory(uid , temp_memory.language, temp_memory, force_process=True)
        await websocket.send_json({"type": "done"})

    except Exception as e:
        print('error bruf')
        print(e)
        return

    print('finished')
    return

def combine_val_segments(val_segments):
    if len(val_segments) == 1:
        return val_segments
    segments_result = []
    temp_segment = None
    for i in range(len(val_segments)):
        if not temp_segment:
            temp_segment = val_segments[i]
            continue
        else:
            if (val_segments[i]['start'] - val_segments[i-1]['end']) > 120.0:
                segments_result.append(temp_segment)
                temp_segment = None
            else:
                temp_segment['end'] = val_segments[i]['end']
    if temp_segment is not None:
        segments_result.append(temp_segment)
    return segments_result

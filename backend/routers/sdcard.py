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

url = "https://api.deepgram.com/v1/listen"
headers = { 
#    "Authorization": "Token {os.getenv('DEEPGRAM_API_KEY')}" ,
    "Authorization": "Token 19e6bff945ec7b8346da429548a80b40973704e4", 
    "Content-Type": "audio/*",
            }

params = {
    "model": "whisper"
        }
@router.post("/sdcard_memory", response_model=List[Memory], tags=['memories'])
async def download_wav(
        file: UploadFile, #, uid: str = Depends(auth.get_current_user_uid)
        date_time: str,
        uid: str = Depends(auth.get_current_user_uid)
):      
        #save file here?
        # print(uid)
      
        print('s')
        file_path = f"_temp/_{file.filename}"
        with open(file_path, 'wb') as f:
            f.write(file.file.read())
        f.close()
        temp_url = upload_sdcard_audio(file_path)
        # print(date_time)
        datetime_now = datetime.datetime.now(datetime.timezone.utc) #save the current time. will be used to determine elapsed time
        #start of audio to transcription stage
        try:   
            f_ = open(file_path,'rb')
            response = requests.post(url, headers=headers, params = params,data=f_.read())
            f_.close()
        except:
            print("eror parsing")
            return 
        response2 = response.json()
        #end of audio to transcriptoin stage
        print(response2)
        if response2['metadata']['duration'] == 0.0:
            return 400
        if not response2['results']['channels']:
            return 400
        #this part is for more accurate time measurement
        # date_string = "2024-09-14T14:43:46.560643" #the true start of transcription is the time of download + file duration
        # format_string = "%Y-%m-%dT%H:%M:%S.%f"
        # datetime_object = datetime.datetime.strptime( date_string, format_string) 
        file_duration = response2['metadata']['duration']
        approximate_file_delay = file_duration * 2.2 #based on empirical observations of ble download speed. 2.2 is tunable
        #partitioning stage
        partitioned_transcripts = partition_transcripts(response2)
        memory_list = []
        print('length of list:',len(partitioned_transcripts))
        for partitions in partitioned_transcripts:
            #weed out the transcripts here
            if not partitions: #empty list
                 continue
            if len(partitions[0].text.split()) < 8: #too small
                 continue
            temp_start_time = partitions[0].start
            temp_end_time = partitions[0].end
            partitions[0].start = 0.0
            partitions[0].end = temp_end_time-temp_start_time
            temp_memory = CreateMemory(
            started_at= datetime_now - datetime.timedelta(seconds=(file_duration - temp_start_time)) - datetime.timedelta(seconds=approximate_file_delay),
            finished_at= datetime_now  - datetime.timedelta(seconds=(file_duration - temp_end_time)) - datetime.timedelta(seconds=approximate_file_delay),
            transcript_segments = partitions,
            language = 'en'
            )
            result: Memory = process_memory(uid , temp_memory.language, temp_memory, force_process=True)
            print(temp_memory.transcript_segments)

            memory_list.append(result)
        if not memory_list:
            return 400
        
        return memory_list

def partition_transcripts(json_file):
    #may be transcription dervice dependant
    transcript_list =json_file['results']['channels'][0]['alternatives'][0]['words']
    list_of_conversations = []
    previous_end_time = 0.0
    tr_threshold = 30.0
    current_transcript_string = ''
    current_start_num = 0.0
    for words in transcript_list:
        word_ = words['word']
        end = words['end']
        start = words['start']
        if (start - previous_end_time > tr_threshold):
            test1 = TranscriptSegment(text=current_transcript_string,is_user = True,start = current_start_num,end = previous_end_time)
            current_start_num = words['start']
            list_of_conversations.append([test1])
            current_transcript_string= ''
        #TODO:partition within segment for different speakers
        #if different speaker: do this....
        current_transcript_string = current_transcript_string + word_ + ' '
        previous_end_time = end
    final_conv = TranscriptSegment(text=current_transcript_string,is_user=True ,start = current_start_num,end = previous_end_time)
    list_of_conversations.append([final_conv])
    return list_of_conversations


@router.websocket("/sdcard_stream")
async def sdcard_streaming_endpoint(
        websocket: WebSocket, uid: str,bt_connected_time: str
):
    print(uid)
    print(bt_connected_time)
    bt_connected_time_dt = datetime.datetime.strptime(bt_connected_time, '%Y-%m-%d %H:%M:%S.%fZ').replace(tzinfo=datetime.timezone.utc)
    print('datetime')
    print(bt_connected_time_dt)

    try:
        await websocket.accept()
    except RuntimeError as e:
        print(e)
        return
    
    #stream all data into a audio file
    websocket_active = True
    session_id = str(uuid.uuid4())
    big_file_path = f"_temp/_temp{session_id}.wav"
    first_packet_flag=False
    data_packet_length=83
    packet_count = 0
    audio_frames = []

    try:
        while websocket_active:
            if first_packet_flag:
                data = await asyncio.wait_for(websocket.receive_bytes(), timeout=10.0)

            else:
                data = await websocket.receive_bytes()


            if (len(data) == data_packet_length):
                if not first_packet_flag:
                    first_packet_flag = True
                    print('first valid packet received')
            if data == 100:
                print('done.')
                websocket_active = False
                break
            amount = int(data[3])
            # print(session_id)
            frame_to_decode = bytes(list(data[4:4+amount]))
            audio_frames.append(frame_to_decode)
            # if websocket.client_state == WebSocketState.CONNECTED:
            #     pass
            # else:
            #     websocket_active = False
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
    if duration_of_file < 5.0:
        print('audio file too small')
        return 
    
    create_wav_from_bytes(big_file_path, audio_frames, "opus", 16000, 1, 2)

    try:
        temp_file_path = f"_temp/{session_id}"#+file_num .wav
        current_file_num = 1
        temp_file_name = 'temp' + str(current_file_num)
        temp_file_list = []
        vad_segments = vad_is_empty(big_file_path, return_segments=True)
        print(vad_segments)
        vad_segments_combined = []
        if vad_segments:
            vad_segments_combined = combine_val_segments(vad_segments)
            for segments in vad_segments_combined:
                print(segments)
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
            
        for file,segments in zip(temp_file_list,vad_segments_combined):
            signed_url = upload_sdcard_audio(file)
            aseg = AudioSegment.from_wav(file)
            words = fal_whisperx(signed_url, 1,2)
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

    #return good signal
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

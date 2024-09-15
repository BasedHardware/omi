import os
from typing import Optional
import os
from models.memory import *
import requests
from fastapi import APIRouter, FastAPI,Depends, HTTPException, UploadFile
from utils.memories.process_memory import process_memory, process_user_emotion
from utils.other.storage import upload_sdcard_audio
from utils.other import endpoints as auth
import datetime

router = APIRouter()


url = "https://api.deepgram.com/v1/listen"
headers = {
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
        file_path = f"_temp/_{file.filename}"
        with open(file_path, 'wb') as f:
            f.write(file.file.read())

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

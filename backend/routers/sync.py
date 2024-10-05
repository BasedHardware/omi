import os
import threading
from typing import List

from fastapi import APIRouter, UploadFile, File, Depends

from utils.other import endpoints as auth
from utils.stt.vad import vad_is_empty

router = APIRouter()

import shutil


@router.post("/v1/sync-local-files")
async def upload_files(files: List[UploadFile] = File(...), uid: str = Depends(auth.get_current_user_uid)):
    directory = f'syncing/{uid}/'
    os.makedirs(directory, exist_ok=True)
    paths = []
    for file in files:
        filename = file.filename
        path = f"{directory}{filename}"
        paths.append(path)
        with open(path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

    # generate a couple .txt files with websocket
    wav_files = []
    for i, path in enumerate(paths):
        # decode the file to wav, if duration is less than 1s, discard
        # paths[i] = decoded wav file path
        pass

    all_segments = {}

    def single(path):
        start_timestamp = int(path.split('/')[-1].split('_')[-1].split('.')[0])
        segments = vad_is_empty(path, return_segments=True)
        # combine them when appropiate, if distance < 1s (similar to speech profile) | skip < 1s isolated parts
        # export each segment to a file

        # for each final segment
        # subpath = path + f'_{i}.wav'
        # timestamp = start_timestamp + segment['start']
        # all_segments[subpath] = timestamp

    threads = []
    for path in paths:
        threads.append(threading.Thread(target=single, args=(path,)))

    chunk_size = 5
    for i in range(0, len(threads), chunk_size):
        [t.start() for t in threads[i:i + chunk_size]]
        [t.join() for t in threads[i:i + chunk_size]]

    response = {'updated_memories': [], 'new_memories': []}
    for path, start_timestamp in all_segments.items():
        # call deepgram prerecorded or whisper-x, get List[TranscriptSegment]
        # find nearest memory to start_timestamp (< 120 seconds) either after, before, or between
        #   if found -> insert to the memory (if between, caution with the order)
        #   if not found -> create a new memory with the segments received.
        pass

    # notify through FCM too ?
    return response

import os
import struct
import threading
from datetime import datetime
from typing import List

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from opuslib import Decoder
from pydub import AudioSegment

from utils.other import endpoints as auth
from utils.stt.vad import vad_is_empty

router = APIRouter()

import shutil
import wave


def decode_opus_file_to_wav(opus_file_path, wav_file_path, sample_rate=16000, channels=1):
    decoder = Decoder(sample_rate, channels)
    with open(opus_file_path, 'rb') as f:
        pcm_data = []
        frame_count = 0
        while True:
            length_bytes = f.read(4)
            if not length_bytes:
                print("End of file reached.")
                break
            if len(length_bytes) < 4:
                print("Incomplete length prefix at the end of the file.")
                break

            frame_length = struct.unpack('<I', length_bytes)[0]
            print(f"Reading frame {frame_count}: length {frame_length}")
            opus_data = f.read(frame_length)
            print(len(opus_data), frame_length)
            if len(opus_data) < frame_length:
                print(f"Unexpected end of file at frame {frame_count}.")
                break
            try:
                pcm_frame = decoder.decode(opus_data, frame_size=160)
                pcm_data.append(pcm_frame)
                frame_count += 1
            except Exception as e:
                print(f"Error decoding frame {frame_count}: {e}")
                break
        if pcm_data:
            pcm_bytes = b''.join(pcm_data)
            with wave.open(wav_file_path, 'wb') as wav_file:
                wav_file.setnchannels(channels)
                wav_file.setsampwidth(2)  # 16-bit audio
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(pcm_bytes)
            print(f"Decoded audio saved to {wav_file_path}")
        else:
            print("No PCM data was decoded.")


# decode_opus_file_to_wav('audio.bin', 'audio.wav')

def retrieve_file_paths(files: List[UploadFile], uid: str):
    directory = f'syncing/{uid}/'
    os.makedirs(directory, exist_ok=True)
    paths = []
    for file in files:
        filename = file.filename
        # VAlidate the file is .bin and contains a _$timestamp.bin, if not, 400 bad request
        if not filename.endswith('.bin'):
            raise HTTPException(status_code=400, detail=f"Invalid file format {filename}")
        if '_' not in filename:
            raise HTTPException(status_code=400, detail=f"Invalid file format {filename}, missing timestamp")
        try:
            timestamp = int(filename.split('_')[-1].split('.')[0])
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid file format {filename}, invalid timestamp")

        time = datetime.fromtimestamp(timestamp)
        if time > datetime.now() or time < datetime(2024, 1, 1):
            raise HTTPException(status_code=400, detail=f"Invalid file format {filename}, invalid timestamp")

        path = f"{directory}{filename}"
        paths.append(path)
        with open(path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    return paths



def decode_files_to_wav(files_path: List[str]):
    wav_files = []
    for path in files_path:
        wav_path = path.replace('.bin', '.wav')
        decode_opus_file_to_wav(path, wav_path)
        aseg = AudioSegment.from_wav(wav_path)
        if aseg.duration_seconds < 1:
            os.remove(wav_path)
            continue
        wav_files.append(wav_path)
        os.remove(path)
    return wav_files


@router.post("/v1/sync-local-files")
async def upload_files(files: List[UploadFile] = File(...), uid: str = Depends(auth.get_current_user_uid)):
    paths = retrieve_file_paths(files, uid)
    paths = decode_files_to_wav(paths)

    all_segments = {}

    def single(path):
        start_timestamp = int(path.split('/')[-1].split('_')[-1].split('.')[0])
        segments = vad_is_empty(path, return_segments=True)
        print(path, segments)
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

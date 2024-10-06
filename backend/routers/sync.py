import os
import struct
import threading
import time
from datetime import datetime
from typing import List

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from opuslib import Decoder
from pydub import AudioSegment

from database.memories import get_closest_memory_to_timestamps
from models.memory import CreateMemory
from models.transcript_segment import TranscriptSegment
from utils.memories.process_memory import process_memory
from utils.other import endpoints as auth
from utils.other.storage import get_syncing_file_temporal_url, delete_syncing_temporal_file
from utils.stt.pre_recorded import fal_whisperx, fal_postprocessing
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
            # print(f"Reading frame {frame_count}: length {frame_length}")
            opus_data = f.read(frame_length)
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


def get_timestamp_from_path(path: str):
    timestamp = int(path.split('/')[-1].split('_')[-1].split('.')[0])
    if timestamp > 1e10:
        return int(timestamp / 1000)
    return timestamp


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
            timestamp = get_timestamp_from_path(filename)
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


def retrieve_vad_segments(path: str, segmented_paths: set):
    start_timestamp = get_timestamp_from_path(path)
    voice_segments = vad_is_empty(path, return_segments=True, cache=True)
    segments = []
    # should we merge more aggressively, to avoid too many small segments? ~ not for now
    # Pros -> lesser segments, faster, less concurrency
    # Cons -> less accuracy.
    for i, segment in enumerate(voice_segments):
        if segments and (segment['start'] - segments[-1]['end']) < 1:
            segments[-1]['end'] = segment['end']
        else:
            segments.append(segment)

    print(path, segments)

    aseg = AudioSegment.from_wav(path)
    os.remove(path)
    for i, segment in enumerate(segments):
        if (segment['end'] - segment['start']) < 1:
            continue
        segment_timestamp = start_timestamp + segment['start']
        segment_path = f'{segment_timestamp}.wav'
        segment_aseg = aseg[segment['start'] * 1000:segment['end'] * 1000]
        segment_aseg.export(segment_path, format='wav')
        segmented_paths.add(segment_path)


def process_segment(path: str, uid: str, response: dict):
    url = get_syncing_file_temporal_url(path)

    def delete_file():
        time.sleep(480)
        delete_syncing_temporal_file(path)

    threading.Thread(target=delete_file).start()

    words, language = fal_whisperx(url, 3, 2, True)
    transcript_segments: List[TranscriptSegment] = fal_postprocessing(words, 0)
    if not transcript_segments:
        print('failed to get fal segments')
        return
    timestamp = get_timestamp_from_path(path)
    closest_memory = get_closest_memory_to_timestamps(uid, timestamp, timestamp + transcript_segments[-1].end)
    # if not closest_memory:
    create_memory = CreateMemory(
        started_at=datetime.fromtimestamp(timestamp),
        finished_at=datetime.fromtimestamp(timestamp + transcript_segments[-1].end),
        transcript_segments=transcript_segments
    )
    created = process_memory(uid, language, create_memory)
    response['new_memories'].add(created.id)
    # else:
    # TODO: take transcript segments from closest memory, and set timestamp to each segment
    #  - take this ones and set timestamp
    #  - sort by timestamp
    #  - update the memory transcript segments
    # pass
    print(timestamp, transcript_segments)


@router.post("/v1/sync-local-files")
async def sync_local_files(files: List[UploadFile] = File(...), uid: str = Depends(auth.get_current_user_uid)):
    paths = retrieve_file_paths(files, uid)
    wav_paths = decode_files_to_wav(paths)

    def chunk_threads(threads):
        chunk_size = 5
        for i in range(0, len(threads), chunk_size):
            [t.start() for t in threads[i:i + chunk_size]]
            [t.join() for t in threads[i:i + chunk_size]]

    segmented_paths = set()
    threads = [threading.Thread(target=retrieve_vad_segments, args=(path, segmented_paths)) for path in wav_paths]
    chunk_threads(threads)

    response = {'updated_memories': set(), 'new_memories': set()}
    threads = [threading.Thread(target=process_segment, args=(path, uid, response,)) for path in segmented_paths]
    chunk_threads(threads)

    # notify through FCM too ?
    return response

# STEPS
# - Download all files.
# - get each of those memories
# - read local json with each memory audio file
# - call whisper groq (whisper-largev3)
# - Create a table df, well printed, with each transcript result side by side
# - prompt for computing WER using groq whisper as baseline (if better, but most likely)
# - Run for deepgram vs soniox, and generate comparison result
import asyncio
# - P3
# - Include speechmatics to the game
import json
import os
from typing import Dict, List

import firebase_admin
from dotenv import load_dotenv
from pydub import AudioSegment

load_dotenv('../../.dev.env')
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '../../' + os.getenv('GOOGLE_APPLICATION_CREDENTIALS')

firebase_admin.initialize_app()

from models.transcript_segment import TranscriptSegment
from utils.stt.streaming import process_audio_dg, process_audio_soniox, process_audio_speechmatics


def store_model_result(memory_id: str, model: str, result: List[Dict]):
    file_path = 'results.json'
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            results = json.load(f)
    else:
        results = {}

    if memory_id not in results:
        results[memory_id] = {}

    results[memory_id][model] = result
    # save it
    with open(file_path, 'w') as f:
        json.dump(results, f)


def add_model_result_segments(memory_id: str, model: str, result: List[Dict]):
    file_path = 'results.json'
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            results = json.load(f)
    else:
        results = {}

    if memory_id not in results:
        results[memory_id] = {}

    if model not in results[memory_id]:
        results[memory_id][model] = []

    segments = [TranscriptSegment(**s) for s in results[memory_id][model]]
    new_segments = [TranscriptSegment(**s) for s in result]

    segments = TranscriptSegment.combine_segments(segments, new_segments)
    store_model_result(memory_id, model, [s.dict() for s in segments])


async def process_memories_audio_files():
    uids = os.listdir('_temp2')
    for uid in uids:
        memories = os.listdir(f'_temp2/{uid}')
        memories = [f'_temp2/{uid}/{memory}' for memory in memories]
        # memories_id = []
        # for file_path in memories:
        #     if AudioSegment.from_wav(file_path).frame_rate != 16000:
        #         continue
        #     memory_id = file_path.split('.')[0]
        #     memories_id.append(memory_id)

        # memories_data = get_memories_by_id(uid, memories_id)
        for file_path in memories:
            memory_id = file_path.split('/')[-1].split('.')[0]
            print(memory_id)

            def stream_transcript_deepgram(new_segments, _):
                print(new_segments)
                add_model_result_segments(memory_id, 'deepgram', new_segments)

            def stream_transcript_soniox(new_segments, _):
                print(new_segments)
                add_model_result_segments(memory_id, 'soniox', new_segments)

            def stream_transcript_speechmatics(new_segments, _):
                print(new_segments)
                add_model_result_segments(memory_id, 'speechmatics', new_segments)

            socket = await process_audio_dg(stream_transcript_deepgram, '1', 'en', 16000, 'pcm16', 1, 0)
            socket_soniox = await process_audio_soniox(stream_transcript_soniox, '1', 'en', None)
            socket_speechmatics = await process_audio_speechmatics(stream_transcript_speechmatics, '1', 'en', 0)
            duration = AudioSegment.from_wav(file_path).duration_seconds
            print('duration', duration)
            with open(file_path, "rb") as file:

                while True:
                    chunk = file.read(320)
                    if not chunk:
                        break
                    # print('Uploading', len(chunk))
                    # TODO: Race conditions here?
                    socket.send(bytes(chunk))
                    await socket_soniox.send(bytes(chunk))
                    await socket_speechmatics.send(bytes(chunk))
                    await asyncio.sleep(0.0001)
            print('File sent')
            # - call for whisper-x
            # - store in a json file and cache
            await asyncio.sleep(duration)  # TODO: await duration
            break
        break


if __name__ == '__main__':
    asyncio.run(process_memories_audio_files())

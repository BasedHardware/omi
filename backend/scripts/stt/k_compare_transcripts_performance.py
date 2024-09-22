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
from groq import Groq

from utils.other.storage import upload_postprocessing_audio
from utils.stt.pre_recorded import fal_whisperx, fal_postprocessing


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


def add_model_result_segments(model: str, new_segments: List[Dict], result: Dict):
    segments = [TranscriptSegment(**s) for s in result[model]]
    new_segments = [TranscriptSegment(**s) for s in new_segments]
    segments = TranscriptSegment.combine_segments(segments, new_segments)
    result[model] = [s.dict() for s in segments]


def execute_groq(file_path: str):
    client = Groq(api_key=os.getenv('GROQ_API_KEY'))
    with open(file_path, "rb") as file:
        transcription = client.audio.transcriptions.create(
            file=(file_path, file.read()),
            model="whisper-large-v3",
            response_format="text",
            language="en",
            temperature=0.0
        )
        return str(transcription)


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
            aseg = AudioSegment.from_wav(file_path)
            memory_id = file_path.split('/')[-1].split('.')[0]

            if os.path.exists(f'results/{memory_id}.json'):
                print('Already processed', memory_id)
                continue
            print('Started processing', memory_id, 'duration', aseg.duration_seconds)
            result = {
                'deepgram': [],
                'soniox': [],
                'speechmatics': []
            }

            def stream_transcript_deepgram(new_segments, _):
                print('stream_transcript_deepgram', new_segments)
                add_model_result_segments('deepgram', new_segments, result)

            def stream_transcript_soniox(new_segments, _):
                print('stream_transcript_soniox', new_segments)
                add_model_result_segments('soniox', new_segments, result)

            def stream_transcript_speechmatics(new_segments, _):
                print('stream_transcript_speechmatics', new_segments)
                add_model_result_segments('speechmatics', new_segments, result)

            groq_result: str = execute_groq(file_path)  # source of truth
            result['whisper-large-v3'] = groq_result

            # whisperx
            signed_url = upload_postprocessing_audio(file_path)
            words = fal_whisperx(signed_url)
            fal_segments = fal_postprocessing(words, aseg.duration_seconds)
            result['fal_whisperx'] = [s.dict() for s in fal_segments]

            # streaming models
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
                    socket.send(bytes(chunk))
                    await socket_soniox.send(bytes(chunk))
                    await socket_speechmatics.send(bytes(chunk))
                    await asyncio.sleep(0.001)
            await asyncio.sleep(duration)

            os.makedirs('results', exist_ok=True)
            with open(f'results/{memory_id}.json', 'w') as f:
                json.dump(result, f, indent=2)
        break


from jiwer import wer


def compute_wer():
    dir = 'results/'
    for file in os.listdir(dir):
        if not file.endswith('.json'):
            continue
        with open(f'{dir}{file}', 'r') as f:
            result = json.load(f)
        source = str(result['whisper-large-v3']).strip().lower().replace('  ', ' ')
        print(file)
        for model, segments in result.items():
            if model == 'whisper-large-v3': # TODO: words vs each other
                continue
            segments_str = ' '.join([s['text'] for s in segments]).strip().lower().replace('  ', ' ')
            value = wer(source, segments_str)
            print(f'{model} WER: {value}')
        print('-----------------------------------------')


if __name__ == '__main__':
    # asyncio.run(process_memories_audio_files())
    compute_wer()

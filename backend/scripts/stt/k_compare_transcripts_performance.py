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
import re
from collections import defaultdict
from itertools import islice
from typing import Dict, List

import firebase_admin
from dotenv import load_dotenv
from pydub import AudioSegment
from tabulate import tabulate

load_dotenv('../../.dev.env')
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '../../' + os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
firebase_admin.initialize_app()

from models.transcript_segment import TranscriptSegment
from utils.stt.streaming import process_audio_dg, process_audio_soniox, process_audio_speechmatics
from groq import Groq

from utils.other.storage import upload_postprocessing_audio
from utils.stt.pre_recorded import fal_whisperx, fal_postprocessing


def add_model_result_segments(model: str, new_segments: List[Dict], result: Dict):
    segments = [TranscriptSegment(**s) for s in result[model]]
    new_segments = [TranscriptSegment(**s) for s in new_segments]
    segments = TranscriptSegment.combine_segments(segments, new_segments)
    result[model] = [s.dict() for s in segments]


def execute_groq(file_path: str):
    file_size = os.path.getsize(file_path)
    print('execute_groq file_size', file_size / 1024 / 1024, 'MB')
    split_files = []
    if file_size / 1024 / 1024 > 25:
        # split file
        aseg = AudioSegment.from_wav(file_path)
        # split every 10 minutes
        split_duration = 10 * 60 * 1000
        for i in range(0, len(aseg), split_duration):
            split_file_path = f'{file_path}_{i}.wav'
            split_files.append(split_file_path)
            aseg[i:i + split_duration].export(split_file_path, format="wav")
    else:
        split_files.append(file_path)

    client = Groq(api_key=os.getenv('GROQ_API_KEY'))
    result = ''
    for file_path in split_files:
        with open(file_path, "rb") as file:
            transcription = client.audio.transcriptions.create(
                file=(file_path, file.read()),
                model="whisper-large-v3",
                response_format="verbose_json",
                language="en",
                temperature=0.0
            )
            result += ' ' + str(transcription)
    return result.strip().lower().replace('  ', ' ')


async def _execute_single(file_path: str):
    aseg = AudioSegment.from_wav(file_path)
    duration = aseg.duration_seconds
    memory_id = file_path.split('/')[-1].split('.')[0]

    if os.path.exists(f'results/{memory_id}.json'):
        print('Already processed', memory_id)
        return
    if aseg.duration_seconds < 5:
        print('Skipping', memory_id, 'duration', aseg.duration_seconds)
        return

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

    # streaming models
    socket = await process_audio_dg(stream_transcript_deepgram, '1', 'en', 16000, 'pcm16', 1, 0)
    socket_soniox = await process_audio_soniox(stream_transcript_soniox, '1', 'en', None)
    socket_speechmatics = await process_audio_speechmatics(stream_transcript_speechmatics, '1', 'en', 0)
    print('duration', duration)
    with open(file_path, "rb") as file:
        while True:
            chunk = file.read(320)
            if not chunk:
                break
            socket.send(bytes(chunk))
            await socket_soniox.send(bytes(chunk))
            await socket_speechmatics.send(bytes(chunk))
            await asyncio.sleep(0.005)

    print('Finished sending audio')
    groq_result: str = execute_groq(file_path)  # source of truth
    result['whisper-large-v3'] = groq_result

    # whisperx
    try:
        signed_url = upload_postprocessing_audio(file_path)
        words = fal_whisperx(signed_url)
        fal_segments = fal_postprocessing(words, duration)
        result['fal_whisperx'] = [s.dict() for s in fal_segments]
    except Exception as e:
        print('fal_whisperx', e)
        result['fal_whisperx'] = []

    print('Waiting for sockets to finish', min(60, duration), 'seconds')
    await asyncio.sleep(min(30, duration))

    os.makedirs('results', exist_ok=True)
    with open(f'results/{memory_id}.json', 'w') as f:
        json.dump(result, f, indent=2)

    socket.finish()
    await socket_soniox.close()
    await socket_speechmatics.close()


def batched(iterable, n):
    """
    Generator that yields lists of size 'n' from 'iterable'.
    """
    it = iter(iterable)
    while True:
        batch = list(islice(it, n))
        if not batch:
            break
        yield batch


async def process_memories_audio_files():
    uids = os.listdir('_temp2')
    for uid in uids:
        memories = os.listdir(f'_temp2/{uid}')
        memories = [f'_temp2/{uid}/{memory}' for memory in memories]
        # batch_size = 5
        for memory in memories:
            await _execute_single(memory)
        # for batch_num, batch in enumerate(batched(memories, batch_size), start=1):
        #     tasks = [asyncio.create_task(_execute_single(file_path)) for file_path in batch]
        #     await asyncio.gather(*tasks)
        #     print(f'Batch {batch_num} processed')


from jiwer import wer


def compute_wer():
    """
    Computes the Word Error Rate (WER) for each transcription model against a reference model
    across all JSON files in the specified directory. Outputs detailed results and overall rankings.
    """
    dir_path = 'results/'  # Directory containing JSON files
    reference_model = 'whisper-large-v3'  # Reference model key
    table_data = []  # List to hold detailed table rows
    wer_accumulator = defaultdict(list)  # To accumulate WERs per model
    points_counter = defaultdict(int)  # To count points per model based on WER rankings

    # Define detailed table headers
    detailed_headers = [
        "File",
        "Model",
        "WER",
        "Source Words",
        "Model Words",
        "Source Characters",
        "Model Characters",
        "Transcript"
    ]

    # Check if the directory exists
    if not os.path.isdir(dir_path):
        print(f"Directory '{dir_path}' does not exist.")
        return

    # Iterate through all files in the specified directory
    for file in os.listdir(dir_path):
        if not file.endswith('.json'):
            continue  # Skip non-JSON files

        file_path = os.path.join(dir_path, file)
        with open(file_path, 'r', encoding='utf-8') as f:
            try:
                result = json.load(f)
            except json.JSONDecodeError:
                print(f"Error decoding JSON in file: {file}")
                continue  # Skip files with invalid JSON

        # Check if the reference model exists in the JSON
        if reference_model not in result:
            print(f"Reference model '{reference_model}' not found in file: {file}")
            continue  # Skip files without the reference model

        # Assemble the reference transcript
        reference_text = regex_fix(result.get(reference_model, ''))
        if isinstance(reference_text, list):
            # If reference_text is a list of segments
            reference_text = ' '.join([segment.get('text', '') for segment in reference_text]).strip().lower()
        else:
            # If reference_text is a single string
            reference_text = str(reference_text).strip().lower()
        reference_text = ' '.join(reference_text.split())  # Normalize whitespace

        # Calculate source words and characters
        source_words = len(reference_text.split())
        source_characters = len(reference_text)

        print(f"Processing file: {file}")

        # Temporary storage for current file's model WERs to determine ranking points
        current_file_wer = {}

        # Iterate through each model in the JSON
        for model, segments in result.items():
            if model == reference_model:
                model_text = reference_text  # Reference model's transcript
            else:
                if isinstance(segments, list):
                    # Assemble the model's transcript from segments
                    model_text = ' '.join([segment.get('text', '') for segment in segments]).strip().lower()
                else:
                    # If segments is a single string
                    model_text = str(segments).strip().lower()
                model_text = ' '.join(model_text.split())  # Normalize whitespace

            # Calculate model words and characters
            model_words = len(model_text.split())
            model_characters = len(model_text)

            # Compute WER
            current_wer = wer(reference_text, model_text)

            # Accumulate WER for overall statistics (exclude reference model)
            if model != reference_model:
                wer_accumulator[model].append(current_wer)

            # Store WER for current file's ranking
            if model != reference_model:
                current_file_wer[model] = current_wer

            # Append the data to the detailed table
            table_data.append([
                file,
                model,
                f"{current_wer:.2%}",
                source_words,
                model_words,
                source_characters,
                model_characters,
                model_text
            ])

        # Determine which model(s) had the lowest WER in the current file
        if current_file_wer:
            min_wer = min(current_file_wer.values())
            best_models = [model for model, w in current_file_wer.items() if w == min_wer]
            for model in best_models:
                points_counter[model] += 1  # Assign 1 point to each best model

        print('-----------------------------------------')

    # Generate the detailed WER table using tabulate
    if table_data:
        print("\nDetailed WER Results:")
        detailed_table = tabulate(table_data, headers=detailed_headers, tablefmt="grid", stralign="left")
        with open('results/detailed_wer.txt', 'w') as f:
            f.write(detailed_table)
    else:
        print("No data to display.")

    # Compute overall WER per model (average)
    overall_wer = {}
    for model, wer_list in wer_accumulator.items():
        if wer_list:
            overall_wer[model] = sum(wer_list) / len(wer_list)

    # Create a list for overall WER table
    overall_wer_table = []
    for model, avg_wer in overall_wer.items():
        overall_wer_table.append([
            model,
            f"{avg_wer:.2%}"
        ])

    # Sort the overall WER table by average WER ascending (lower is better)
    overall_wer_table_sorted = sorted(overall_wer_table, key=lambda x: x[1])

    # Define overall WER table headers
    overall_wer_headers = ["Model", "Average WER"]

    # Generate the overall WER table
    if overall_wer_table_sorted:
        print("\nOverall WER per Model:")
        overall_wer_formatted = tabulate(overall_wer_table_sorted, headers=overall_wer_headers, tablefmt="grid",
                                         stralign="left")
        print(overall_wer_formatted)
        with open('results/wer.txt', 'w') as f:
            f.write(overall_wer_formatted)
    else:
        print("No overall WER data to display.")

    # Create a ranking table based on points
    ranking_table = []
    for model, points in points_counter.items():
        ranking_table.append([
            model,
            points
        ])

    # Sort the ranking table by points descending (more points are better)
    ranking_table_sorted = sorted(ranking_table, key=lambda x: x[1], reverse=True)

    # Assign rankings
    ranking_table_with_rank = []
    current_rank = 1
    previous_points = None
    for idx, (model, points) in enumerate(ranking_table_sorted):
        if points != previous_points:
            rank = current_rank
        else:
            rank = current_rank - 1  # Same rank as previous
        ranking_table_with_rank.append([
            rank,
            model,
            points
        ])
        previous_points = points
        current_rank += 1

    # Define ranking table headers
    ranking_headers = ["Rank", "Model", "Points"]

    # Generate the ranking table
    if ranking_table_with_rank:
        print("\nModel Rankings Based on WER Performance:")
        ranking_table_formatted = tabulate(ranking_table_with_rank, headers=ranking_headers, tablefmt="grid",
                                           stralign="left")
        print(ranking_table_formatted)
        with open('results/ranking.txt', 'w') as f:
            f.write(ranking_table_formatted)
    else:
        print("No ranking data to display.")


def regex_fix(text: str):
    # Define the regular expression
    pattern = r'(?<=transcription\(text=["\'])(.*?)(?=["\'],\s*task=)'

    # Search for the pattern in the data
    match = re.search(pattern, text)

    # If a match is found, extract and print the text
    if match:
        extracted_text = match.group(0)
        return extracted_text
    else:
        print("No match found.")
        return text


if __name__ == '__main__':
    # asyncio.run(process_memories_audio_files())
    compute_wer()
    # client = Groq(api_key=os.getenv('GROQ_API_KEY'))
    # file_path = '_temp2/DX8n89KAmUaG9O7Qvj8xTi81Zu12/0bce5547-675b-4dea-b9fe-cfb69740100b.wav'

    # with open(file_path, "rb") as file:
    #     transcription = client.audio.transcriptions.create(
    #         file=(file_path, file.read()),
    #         model="whisper-large-v3",
    #         response_format="verbose_json",
    #         language="en",
    #         temperature=0.0
    #     )
    #     print(transcription)
    #     for segment in transcription.segments:
    #         print(segment['start'], segment['end'], segment['text'])

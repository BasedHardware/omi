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
import requests
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
                response_format="text",
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
    socket_soniox = await process_audio_soniox(stream_transcript_soniox, '1', 16000, 'en', None)
    socket_speechmatics = await process_audio_speechmatics(stream_transcript_speechmatics, '1', 16000, 'en', 0)
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
    """Fix some of the stored JSON in results/$id.json from the Groq API."""
    pattern = r'(?<=transcription\(text=["\'])(.*?)(?=["\'],\s*task=)'
    match = re.search(pattern, text)
    if match:
        extracted_text = match.group(0)
        return extracted_text
    else:
        print("No match found.")
        return text


def pyannote_diarize(file_path: str):
    memory_id = file_path.split('/')[-1].split('.')[0]
    with open('diarization.json', 'r') as f:
        results = json.loads(f.read())

    if memory_id in results:
        print('Already diarized', memory_id)
        return

    url = "https://api.pyannote.ai/v1/diarize"
    headers = {"Authorization": f"Bearer {os.getenv('PYANNOTE_API_KEY')}"}
    webhook = 'https://camel-lucky-reliably.ngrok-free.app/webhook'
    signed_url = upload_postprocessing_audio(file_path)
    data = {'webhook': webhook, 'url': signed_url}
    response = requests.post(url, headers=headers, json=data)
    print(memory_id, response.json()['jobId'])
    # update diarization.json, and set jobId=memoryId
    with open('diarization.json', 'r') as f:
        diarization = json.loads(f.read())

    diarization[response.json()['jobId']] = memory_id
    with open('diarization.json', 'w') as f:
        json.dump(diarization, f, indent=2)


def generate_diarizations():
    uids = os.listdir('_temp2')
    for uid in uids:
        memories = os.listdir(f'_temp2/{uid}')
        memories = [f'_temp2/{uid}/{memory}' for memory in memories]
        for memory in memories:
            memory_id = memory.split('/')[-1].split('.')[0]
            if os.path.exists(f'results/{memory_id}.json'):
                pyannote_diarize(memory)
            else:
                print('Skipping', memory_id)


from pyannote.metrics.diarization import DiarizationErrorRate
from pyannote.core import Annotation, Segment

der_metric = DiarizationErrorRate()


def compute_der():
    """
    Computes the Diarization Error Rate (DER) for each model across all JSON files in the 'results/' directory.
    Outputs a summary table and rankings to 'der_report.txt'.
    """
    dir_path = 'results/'  # Directory containing result JSON files and 'diarization.json'
    output_file = os.path.join(dir_path, 'der_report.txt')  # Output report file
    excluded_model = 'whisper-large-v3'  # Model to exclude from analysis

    # Initialize DER metric
    der_metric = DiarizationErrorRate()

    # Check if the directory exists
    if not os.path.isdir(dir_path):
        print(f"Directory '{dir_path}' does not exist.")
        return

    # Path to 'diarization.json'
    diarization_path = 'diarization.json'

    # Load reference diarization data
    with open(diarization_path, 'r', encoding='utf-8') as f:
        try:
            diarization = json.load(f)
        except json.JSONDecodeError:
            print(f"Error decoding JSON in 'diarization.json'.")
            return

    # Prepare to collect DER results
    der_results = []  # List to store [Memory ID, Model, DER]
    model_der_accumulator = defaultdict(list)  # To calculate average DER per model

    # Iterate through all JSON files in 'results/' directory
    for file in os.listdir(dir_path):
        if not file.endswith('.json') or file == 'diarization.json':
            continue  # Skip non-JSON files and 'diarization.json' itself

        memory_id = file.split('.')[0]  # Extract memory ID from filename

        # Check if memory_id exists in 'diarization.json'
        if memory_id not in diarization:
            print(f"Memory ID '{memory_id}' not found in 'diarization.json'. Skipping file: {file}")
            continue

        # Load reference segments for the current memory_id
        ref_segments = diarization[memory_id]
        ref_annotation = Annotation()
        for seg in ref_segments:
            speaker, start, end = seg['speaker'], seg['start'], seg['end']
            ref_annotation[Segment(start, end)] = speaker

        # Load hypothesis segments from the result JSON file
        file_path = os.path.join(dir_path, file)
        with open(file_path, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                print(f"Error decoding JSON in file: {file}. Skipping.")
                continue

        # Iterate through each model's segments in the result
        for model, segments in data.items():
            if model == excluded_model:
                continue  # Skip the excluded model

            hyp_annotation = Annotation()
            for seg in segments:
                speaker, start, end = seg['speaker'], seg['start'], seg['end']
                # Optional: Normalize speaker labels if necessary
                if speaker == 'SPEAKER_0':
                    speaker = 'SPEAKER_00'
                elif speaker == 'SPEAKER_1':
                    speaker = 'SPEAKER_01'
                elif speaker == 'SPEAKER_2':
                    speaker = 'SPEAKER_02'
                elif speaker == 'SPEAKER_3':
                    speaker = 'SPEAKER_03'
                hyp_annotation[Segment(start, end)] = speaker

            # Compute DER between reference and hypothesis
            der = der_metric(ref_annotation, hyp_annotation)

            # Store the result
            der_results.append([memory_id, model, f"{der:.2%}"])
            model_der_accumulator[model].append(der)

    # Generate the detailed DER table
    der_table = tabulate(der_results, headers=["Memory ID", "Model", "DER"], tablefmt="grid", stralign="left")

    # Calculate average DER per model
    average_der = []
    for model, ders in model_der_accumulator.items():
        avg = sum(ders) / len(ders)
        average_der.append([model, f"{avg:.2%}"])

    # Sort models by average DER ascending (lower is better)
    average_der_sorted = sorted(average_der, key=lambda x: float(x[1].strip('%')))

    # Determine the winner (model with the lowest average DER)
    winner = average_der_sorted[0][0] if average_der_sorted else "N/A"

    # Prepare rankings (1st, 2nd, etc.)
    rankings = []
    rank = 1
    previous_der = None
    for model, avg in average_der_sorted:
        current_der = float(avg.strip('%'))
        if previous_der is None or current_der < previous_der:
            current_rank = rank
        else:
            current_rank = rank - 1  # Same rank as previous if DER is equal
        rankings.append([current_rank, model, avg])
        previous_der = current_der
        rank += 1

    # Generate the rankings table
    ranking_table = tabulate(rankings, headers=["Rank", "Model", "Average DER"], tablefmt="grid", stralign="left")

    # Write all results to the output file
    with open(output_file, 'w', encoding='utf-8') as out_f:
        out_f.write("Diarization Error Rate (DER) Analysis Report\n")
        out_f.write("=" * 50 + "\n\n")
        out_f.write("Detailed DER Results:\n")
        out_f.write(der_table + "\n\n")
        out_f.write("Average DER per Model:\n")
        out_f.write(
            tabulate(average_der_sorted, headers=["Model", "Average DER"], tablefmt="grid", stralign="left") + "\n\n")
        out_f.write("Model Rankings Based on Average DER:\n")
        out_f.write(ranking_table + "\n\n")
        out_f.write(f"Winner: {winner}\n")

    # Print a confirmation message
    print(f"Diarization Error Rate (DER) analysis completed. Report saved to '{output_file}'.")

    # Optionally, print the tables to the console as well
    if der_results:
        print("\nDetailed DER Results:")
        print(der_table)
    if average_der_sorted:
        print("\nAverage DER per Model:")
        print(tabulate(average_der_sorted, headers=["Model", "Average DER"], tablefmt="grid", stralign="left"))
    if rankings:
        print("\nModel Rankings Based on Average DER:")
        print(ranking_table)
        print(f"\nWinner: {winner}")


if __name__ == '__main__':
    # asyncio.run(process_memories_audio_files())
    # generate_diarizations()

    # compute_wer()
    compute_der()

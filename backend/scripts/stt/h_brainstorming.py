import base64
import json
import mimetypes
import os

import fal_client
from groq import Groq
from openai import OpenAI

from utils.other.endpoints import timeit

os.environ['GROQ_API_KEY'] = ''
os.environ['FAL_KEY'] = ''

# filename = '../audioSamples/empty.wav'


# filename = '../audioSamples/1719787052529-temp.wav'
filename = 'data/more/18-42-24-841626.wav'


# filename = 'data/more/18-45-32-069108.wav'


def execute():
    client = OpenAI()
    with open(filename, "rb") as file:
        transcription = client.audio.transcriptions.create(
            file=(filename, file.read()),
            model="whisper-1",
            timestamp_granularities=["segment"],
            response_format="verbose_json",
            language="en",
            temperature=0.0
        )
        segments = transcription.json()
        print(segments)
        data = json.loads(segments).get('segments', [])
        for segment in data:
            print(segment['start'], segment['end'], segment['text'])


@timeit
def execute_groq():
    client = Groq()
    with open(filename, "rb") as file:
        transcription = client.audio.transcriptions.create(
            file=(filename, file.read()),
            model="whisper-large-v3",
            response_format="text",
            language="en",
            temperature=0.0
        )
        # print(transcription)
        return transcription


@timeit
def diarization(content: str):
    # client = OpenAI()
    client = Groq()
    system_prompt = '''You are a helpful assistant for correcting transcriptions of conversations.\
    Correct any spelling discrepancies in the transcribed text, add necessary punctuation such as periods, commas, \
    and capitalization, and most important differentiate contextually within the multiple speakers in the conversation.
    
    The output should be formatted as a JSON instance that conforms to the JSON schema below.
    
    As an example, for the schema {"properties": {"foo": {"title": "Foo", "description": "a list of strings", "type": "array", "items": {"type": "string"}}}, "required": ["foo"]}
    the object {"foo": ["bar", "baz"]} is a well-formatted instance of the schema. The object {"properties": {"foo": ["bar", "baz"]}} is not well-formatted.
    
    Here is the output schema:
    ```
    {"properties": {"segments": {"title": "Segments", "description": "The segments of the conversation", "default": [], "type": "array", "items": {"$ref": "#/definitions/Segment"}}}, "definitions": {"Segment": {"title": "Segment", "type": "object", "properties": {"speaker": {"title": "Speaker", "description": "The speaker id for this segment", "default": "SPEAKER_00", "type": "string"}, "text": {"title": "Text", "description": "The text of the segment", "default": "", "type": "string"}}}}}
    ```'''.replace('  ', '').strip()

    response = client.chat.completions.create(
        # model="gpt-4o",
        model="llama3-70b-8192",
        temperature=0,
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": content}]
    )
    return response.choices[0].message.content


def file_to_base64_url(file_path):
    # Determine the MIME type of the file
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        mime_type = 'application/octet-stream'

    # Read the file and encode it in base64
    with open(file_path, 'rb') as file:
        file_content = file.read()
        encoded_string = base64.b64encode(file_content).decode('utf-8')

    # Format as data URL
    base64_url = f"data:{mime_type};base64,{encoded_string}"
    return base64_url


@timeit
def fal():
    handler = fal_client.submit("fal-ai/wizper", arguments={"audio_url": file_to_base64_url(filename)})
    result = handler.get()
    print(result.get('text', ''))
    return result.get('text', '')


@timeit
def fal_whisperx():
    if not has_audio():
        return []
    handler = fal_client.submit(
        "fal-ai/whisper",
        arguments={
            "audio_url": file_to_base64_url(filename),
            'task': 'transcribe',
            'diarize': True,
            'language': 'en',
            'chunk_level': 'segment',
            "num_speakers": None,
            'version': '3'
        },
    )

    result = handler.get()
    chunks = result.get('chunks', [])
    for chunk in chunks:
        chunk['start'] = chunk['timestamp'][0]
        chunk['end'] = chunk['timestamp'][1]
        del chunk['timestamp']
        print(chunk)
    return chunks


import torch

torch.set_num_threads(1)

model, utils = torch.hub.load(repo_or_dir='snakers4/silero-vad', model='silero_vad')
(get_speech_timestamps, _, read_audio, _, _) = utils


@timeit
def has_audio():
    wav = read_audio(filename)
    speech_timestamps = get_speech_timestamps(wav, model, sampling_rate=8000)
    return len(speech_timestamps) > 0


def retrieve_proper_segment_points(file_path):
    wav = read_audio(file_path)
    speech_timestamps = get_speech_timestamps(wav, model, sampling_rate=8000)
    if not speech_timestamps:
        return [None, None]
    return [speech_timestamps[0]['start'] / 1000, speech_timestamps[-1]['end'] / 1000]


if __name__ == '__main__':
    # execute()
    files = sorted(os.listdir('../audioSamples'), key=lambda x: x)
    print('Files:', files)
    for path in os.listdir('../audioSamples'):
        filename = f'../audioSamples/{path}'
        transcription = execute_groq()
        # transcription = fal()
        print(diarization(transcription))
    # fal_whisperx()
    # has_audio()
    # print(retrieve_proper_segment_points(filename))

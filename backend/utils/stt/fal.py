import base64
import mimetypes
from typing import List

import fal_client

from models.transcript_segment import TranscriptSegment
from utils.endpoints import timeit


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


def base64_to_file(base64_url, file_path):
    # Extract the base64 content
    _, base64_content = base64_url.split(',')
    file_content = base64.b64decode(base64_content)

    # Write the content to the file
    with open(file_path, 'wb') as file:
        file.write(file_content)
    return file.read()


def upload_fal_file(mid: str, audio_base64_url: str):
    print(audio_base64_url)
    file_bytes = base64_to_file(audio_base64_url, f"_temp/{mid}.wav")
    url = fal_client.upload(file_bytes, "audio/wav")
    print('url', url)
    return url


def delete_fal_file(url: str):
    # url = fal_client.de(file_bytes, "audio/wav")
    # return url
    return False


@timeit
def fal_whisperx(audio_url: str) -> List[TranscriptSegment]:
    handler = fal_client.submit(
        "fal-ai/whisper",
        arguments={
            "audio_url": audio_url,
            'task': 'transcribe',
            'diarize': True,
            'language': 'en',
            'chunk_level': 'segment',
            "num_speakers": None,
            'version': '3',
            'batch_size': 64,
            # 'prompt': 'Low quality audio recording',
        },
    )

    result = handler.get()
    chunks = result.get('chunks', [])
    for chunk in chunks:
        chunk['start'] = chunk['timestamp'][0]
        chunk['end'] = chunk['timestamp'][1]
        chunk['text'] = chunk['text'].strip()
        chunk['is_user'] = False
        del chunk['timestamp']

    cleaned = []
    # join segments with same speaker, and less than 30 seconds apart
    for chunk in chunks:
        if cleaned and chunk['speaker'] == cleaned[-1]['speaker'] and chunk['start'] - cleaned[-1]['end'] < 30:
            cleaned[-1]['end'] = chunk['end']
            cleaned[-1]['text'] += ' ' + chunk['text']
        else:
            cleaned.append(chunk)

    segments = []
    for segment in cleaned:
        segments.append(TranscriptSegment(
            text=segment['text'],
            speaker=segment['speaker'] or 'SPEAKER_00',
            is_user=segment['is_user'],
            start=segment['start'],
            end=segment['end'],
        ))

    return segments

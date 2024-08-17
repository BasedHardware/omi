import base64
import mimetypes
from typing import List

import fal_client

from models.transcript_segment import TranscriptSegment


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


def fal_whisperx(audio_base64_url: str) -> List[TranscriptSegment]:
    handler = fal_client.submit(
        "fal-ai/whisper",
        arguments={
            "audio_url": audio_base64_url,
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

    # TODO: Include pipeline post processing, so that is_user get's matched with the correct speaker
    # TODO: Do punctuation correction with LLM

    # TODO: test other languages
    # TODO: eventually do speaker embedding matching
    return cleaned

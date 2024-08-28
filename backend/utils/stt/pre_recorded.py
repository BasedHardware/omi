import base64
import mimetypes
from collections import defaultdict
from typing import List

import fal_client

from models.transcript_segment import TranscriptSegment
from utils.other.endpoints import timeit


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


@timeit
def fal_whisperx(audio_url: str, speakers_count: int = None, attempts: int = 0) -> List[dict]:
    print('fal_whisperx', audio_url, speakers_count, attempts)

    try:
        # TODO: this appear to be terrible at speech profile, without passing num_speakers
        handler = fal_client.submit(
            "fal-ai/whisper",
            arguments={
                "audio_url": audio_url,
                'task': 'transcribe',
                'diarize': True,
                'language': 'en',
                'chunk_level': 'word',
                # "num_speakers": None,
                'version': '3',
                'batch_size': 64,
                'num_speakers': speakers_count,
                # 'prompt': 'Let\'s listen to this conversation recording'
            },
        )
        result = handler.get()
        words = result.get('chunks', [])
        if not words:
            raise Exception('No chunks found')
        return words
    except Exception as e:
        print(e)
        return fal_whisperx(audio_url, speakers_count, attempts + 1) if attempts < 2 else []


def _words_cleaning(words: List[dict]):
    words_cleaned: List[dict] = []
    for i, w in enumerate(words):
        # if w['timestamp'][0] == w['timestamp'][1]:
        #     continue
        words_cleaned.append({
            'start': round(w['timestamp'][0], 2),
            'end': round(w['timestamp'][1] or w['timestamp'][0] + 1, 2),
            'speaker': w['speaker'],
            'text': str(w['text']).strip(),
            'is_user': False,
            'person_id': None,
        })

    for i, word in enumerate(words_cleaned):
        speaker = word['speaker']
        if not speaker:
            prev_chunk = words_cleaned[i - 1] if i > 0 else None
            next_chunk = words_cleaned[i + 1] if i < len(words_cleaned) - 1 else None
            prev_speaker = prev_chunk['speaker'] if prev_chunk else None
            next_speaker = next_chunk['speaker'] if next_chunk else None

            if prev_speaker and next_speaker:
                if prev_speaker == next_speaker:
                    speaker = prev_chunk['speaker']
                else:
                    secs_from_prev = word['start'] - prev_chunk['end'] if prev_chunk else 0
                    secs_to_next = next_chunk['start'] - word['end'] if next_chunk else 0
                    speaker = prev_speaker if secs_from_prev < secs_to_next else next_speaker
            elif prev_speaker:
                speaker = prev_speaker
            elif next_speaker:
                speaker = next_speaker
            else:
                speaker = 'SPEAKER_00'

            words_cleaned[i]['speaker'] = speaker

    # for chunk in words_cleaned:
    #     print(chunk)
    return words_cleaned


def _retrieve_user_speaker_id(words: list, skip_n_seconds: int):
    if not skip_n_seconds:
        return None

    user_speaker_id = defaultdict(int)
    for word in words:
        if word['start'] >= skip_n_seconds:
            break
        if not word['speaker']:
            continue
        user_speaker_id[word['speaker']] += 1

    user_speaker_id = max(user_speaker_id, key=user_speaker_id.get) if user_speaker_id else None
    return user_speaker_id


def _merge_segments(words: List[dict], skip_n_seconds: int, user_speaker_id: str):
    segments = []
    for word in words:
        if word['start'] < skip_n_seconds:
            continue
        word['is_user'] = word['speaker'] == user_speaker_id if word['speaker'] else False

        same_prev_speaker = word['speaker'] == segments[-1]['speaker'] if segments else False
        seconds_from_prev = word['start'] - segments[-1]['end'] if segments else 0

        # TODO: consider having a max segment size too
        if segments and same_prev_speaker and seconds_from_prev < 30:
            segments[-1]['end'] = word['end']
            segments[-1]['text'] += ' ' + word['text']
        else:
            segments.append(word)
    return segments


def _segments_as_objects(segments: List[dict]) -> List[TranscriptSegment]:
    if not segments:
        return []
    starts_at = segments[0]['start']
    return [TranscriptSegment(
        text=str(segment['text']).strip().capitalize(),
        speaker=segment['speaker'],
        is_user=segment['is_user'],
        person_id=None,
        start=round(segment['start'] - starts_at, 2),
        end=round(segment['end'] - starts_at, 2),
    ) for segment in segments]


def fal_postprocessing(
        words: List[dict], duration: int, skip_n_seconds: int = 0  # , merge_segments: bool = True
) -> List[TranscriptSegment]:
    words: List[dict] = _words_cleaning(words)
    user_speaker_id = _retrieve_user_speaker_id(words, skip_n_seconds)
    segments = _merge_segments(words, skip_n_seconds, user_speaker_id)
    segments = _segments_as_objects(segments)
    return segments

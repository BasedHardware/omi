import json
import os
from collections import defaultdict
from typing import Any, Dict, List, cast

import torch  # type: ignore[reportMissingImports]  # torch not installed in dev venv
from fastapi import File, UploadFile, Form
from pydantic import BaseModel
from pydub import AudioSegment
from speechbrain.inference.speaker import SpeakerRecognition  # type: ignore[reportMissingImports]  # speechbrain not installed in dev venv

from utils.stt.speech_profile import get_speech_profile_expanded
import logging

logger = logging.getLogger(__name__)


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str


class ResponseItem(BaseModel):
    is_user: bool
    person_id: str | None = None


# SpeechBrain 1.x expects run_opts["device"] to be a string, not torch.device.
device: str = 'cuda:0' if cast(Any, torch.cuda.is_available()) else 'cpu'  # type: ignore[reportUnknownMemberType]  # torch untyped
model: Any = SpeakerRecognition.from_hparams(  # type: ignore[reportUnknownMemberType]  # speechbrain untyped
    source="speechbrain/spkrec-ecapa-voxceleb",
    savedir="pretrained_models/spkrec-ecapa-voxceleb",
    run_opts={"device": device},
)


def sample_same_speaker_as_segment(sample_audio: str, segment: str) -> float:
    try:
        score, prediction = cast(Any, model.verify_files(sample_audio, segment))  # type: ignore[reportUnknownMemberType]  # speechbrain untyped
        if bool(prediction[0]):
            return float(score[0])
        return 0
    except Exception as e:
        logger.error(e)
        return 0


def classify_segments(
    audio_file_path: str,
    profile_path: str,
    people: List[Dict[str, Any]],
    segments: List[TranscriptSegment],
) -> List[Dict[str, Any]]:
    matches: List[Dict[str, Any]] = [{'is_user': False, 'person_id': None}] * len(segments)
    if not profile_path:
        return matches

    # TODO: do per segment cleaning later. 1 by 1, maybe running pyannote VAD here (gpu), or using silero
    # cleaning start, end doesn't do anything, cause segments are already pointing that

    audio = cast(Any, AudioSegment.from_wav(audio_file_path))  # type: ignore[reportUnknownMemberType]  # pydub partially typed
    logger.info(f'Duration: {audio.duration_seconds}')

    file_name = os.path.basename(audio_file_path)
    for i, segment in enumerate(segments):

        duration = segment.end - segment.start
        by_chunk_matches: defaultdict[str, float] = defaultdict(float)

        for j in range(0, int(duration), 30):
            start = segment.start + j
            end = min(segment.end, start + 30)

            temporal_file = f"_temp/{file_name}_{start}_{end}.wav"
            chunk = cast(Any, AudioSegment.from_wav(audio_file_path)[start * 1000 : end * 1000])  # type: ignore[reportUnknownMemberType]  # pydub partially typed
            chunk.export(temporal_file, format="wav")

            by_chunk_matches['user'] += sample_same_speaker_as_segment(temporal_file, profile_path)
            for person in people:
                by_chunk_matches[cast(str, person['id'])] += sample_same_speaker_as_segment(
                    temporal_file, cast(str, person['path'])
                )

            os.remove(temporal_file)

        if not by_chunk_matches:
            continue
        logger.info(by_chunk_matches)
        max_match = max(by_chunk_matches, key=lambda k: by_chunk_matches[k])
        matches[i] = {'is_user': max_match == 'user', 'person_id': None if max_match == 'user' else max_match}

    return matches


os.makedirs('_temp', exist_ok=True)


def endpoint(uid: str, audio_file: UploadFile = File(...), segments: str = Form(...)) -> List[Dict[str, Any]]:
    """
    This endpoint obtains the user (speech profile + samples) + all user people speech samples
    and every segment from the transcript from the stt model, and classifies each segment to a person or to the user.

    :return: List of ResponseItem with is_user and person_id.
    """
    profile_path = get_speech_profile_expanded(uid)
    default: List[Dict[str, Any]] = [{'is_user': False}] * len(json.loads(segments))

    if not profile_path:
        return default

    audio_filename = cast(str, audio_file.filename)
    with open(audio_filename, 'wb') as f:
        f.write(audio_file.file.read())

    segments_data = json.loads(segments)
    transcript_segments = [TranscriptSegment(**segment) for segment in segments_data]

    # people = get_people_with_speech_samples(uid)
    people: List[Dict[str, Any]] = []
    try:
        result = classify_segments(audio_filename, profile_path, people, transcript_segments)
        # print(result)
        return result
    except:
        return default
    finally:
        os.remove(profile_path)
        os.remove(audio_filename)

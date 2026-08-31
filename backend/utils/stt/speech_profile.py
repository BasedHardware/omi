import json
import logging
import os
from typing import Any, Dict, List, Optional

import httpx
from pydub import AudioSegment  # pydub is untyped

from utils.executors import storage_executor, run_blocking
from utils.http_client import get_stt_client
from utils.log_sanitizer import sanitize
from utils.observability.fallback import record_fallback
from utils.other.storage import (
    get_profile_audio_if_exists,
    get_additional_profile_recordings,
    get_user_people_ids,
    get_user_person_speech_samples,
)

logger = logging.getLogger(__name__)


def _get_speech_profile_api_url() -> str:
    """Get the speech profile API URL from environment."""
    url = os.getenv('HOSTED_SPEECH_PROFILE_API_URL')
    if not url:
        raise ValueError('HOSTED_SPEECH_PROFILE_API_URL environment variable not set')
    return url


def _unattributed(segments: List[Dict[str, Any]], reason: str) -> List[Dict[str, Any]]:
    """Give up on speaker identity for this conversation, and say so on the counter.

    Returning "not the user, no person" for every segment keeps post-processing alive, which is the right
    trade: a conversation without attribution beats a conversation that fails to save. But it used to be an
    `info` line and nothing else, so a matcher that had been down for a week looked exactly like a week of
    conversations that genuinely had no known speaker in them.

    Both twins route their fail-open through here so the two copies cannot drift apart on what they report.
    """
    record_fallback(
        component='speaker',
        from_mode='speech_profile_match',
        to_mode='unattributed',
        reason=reason,
        outcome='degraded',
        log=logger,
    )
    return [{'is_user': False, 'person_id': None}] * len(segments)


def _reason_for_status(status_code: int) -> str:
    if status_code == 429:
        return 'provider_429'
    if status_code >= 500:
        return 'provider_5xx'
    return 'other'


def _validate_segment_matches(result: object, segments: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
    """Validate an external speech-profile JSON response before returning it.

    Returns a normalized list (one entry per segment) on success, or None if the
    response shape is malformed. Callers index the result by segment position, so
    we must guarantee len(matches) == len(segments) and that every item is a dict
    with the 'is_user' key that the consumer reads.
    """
    if not isinstance(result, list):
        return None

    # Boolean-list response: normalize to the dict shape the caller expects.
    if result and isinstance(result[0], bool):
        if len(result) != len(segments):
            return None
        return [{'is_user': bool(r), 'person_id': None} for r in result]  # type: ignore[reportUnknownVariableType,reportUnknownArgumentType]  # untyped JSON list elements

    # Already-dict response: validate length and per-item schema.
    if len(result) != len(segments):
        return None
    for item in result:
        if not isinstance(item, dict) or 'is_user' not in item:
            return None
    return result  # type: ignore[reportUnknownVariableType]  # validated external JSON response


def get_speech_profile_matching_predictions(
    uid: str, audio_file_path: str, segments: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    logger.info('get_speech_profile_matching_predictions')
    with open(audio_file_path, 'rb') as audio_f:
        files = [
            ('audio_file', (os.path.basename(audio_file_path), audio_f, 'audio/wav')),
        ]
        response = httpx.post(
            _get_speech_profile_api_url() + f'?uid={uid}',
            data={'segments': json.dumps(segments)},
            files=files,
            timeout=120.0,
        )

    if response.status_code != 200:
        logger.info(f'get_speech_profile_matching_predictions {sanitize(response.text)}')
        return _unattributed(segments, _reason_for_status(response.status_code))
    try:
        result = response.json()
        logger.info(f'get_speech_profile_matching_predictions {sanitize(result)}')
        validated = _validate_segment_matches(result, segments)
        if validated is not None:
            return validated

        # Malformed/empty response shape: fall back to per-segment default so
        # callers that index matches[i] do not crash conversation post-processing.
        logger.info('get_speech_profile_matching_predictions malformed response shape, using default')
        return _unattributed(segments, 'malformed_doc')
    except Exception as e:
        logger.info(f'get_speech_profile_matching_predictions {str(e)}')
        return _unattributed(segments, 'malformed_doc')


def _read_file(path: str) -> bytes:
    with open(path, 'rb') as f:
        return f.read()


async def async_get_speech_profile_matching_predictions(
    uid: str, audio_file_path: str, segments: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Async version of get_speech_profile_matching_predictions using httpx.AsyncClient."""
    logger.info('async_get_speech_profile_matching_predictions')
    file_data = await run_blocking(storage_executor, _read_file, audio_file_path)

    files = {'audio_file': (os.path.basename(audio_file_path), file_data, 'audio/wav')}

    try:
        client = get_stt_client()
        response = await client.post(
            _get_speech_profile_api_url() + f'?uid={uid}',
            data={'segments': json.dumps(segments)},
            files=files,
        )
    except Exception as e:
        logger.error(f'async_get_speech_profile_matching_predictions HTTP error: {e}')
        return _unattributed(segments, 'timeout' if isinstance(e, httpx.TimeoutException) else 'other')

    if response.status_code != 200:
        logger.info(f'async_get_speech_profile_matching_predictions {sanitize(response.text)}')
        return _unattributed(segments, _reason_for_status(response.status_code))
    try:
        result = response.json()
        logger.info(f'async_get_speech_profile_matching_predictions {sanitize(result)}')
        validated = _validate_segment_matches(result, segments)
        if validated is not None:
            return validated

        # Malformed/empty response shape: fall back to per-segment default so
        # callers that index matches[i] do not crash conversation post-processing.
        logger.info('async_get_speech_profile_matching_predictions malformed response shape, using default')
        return _unattributed(segments, 'malformed_doc')
    except Exception as e:
        logger.info(f'async_get_speech_profile_matching_predictions {str(e)}')
        return _unattributed(segments, 'malformed_doc')


def get_speech_profile_expanded(uid: str) -> Optional[str]:
    main = get_profile_audio_if_exists(uid, download=True)
    if not main:
        return None
    parts = get_additional_profile_recordings(uid, download=True)
    aseg: Any = AudioSegment.from_wav(main)  # type: ignore[reportUnknownMemberType]  # pydub untyped
    for part in parts:
        aseg += AudioSegment.from_wav(part)  # type: ignore[reportUnknownMemberType]  # pydub untyped
    path = f'_temp/{uid}_complete_speech_profile.wav'
    aseg.export(path, format='wav')  # type: ignore[reportUnknownMemberType]  # pydub untyped
    return path


def get_people_with_speech_samples(uid: str) -> List[Dict[str, str]]:
    people_ids = get_user_people_ids(uid)
    people: List[Dict[str, str]] = []
    for pid in people_ids:
        file_paths = get_user_person_speech_samples(uid, pid, download=True)
        aseg: Any = AudioSegment.empty()
        for path in file_paths:
            aseg += AudioSegment.from_wav(path)  # type: ignore[reportUnknownMemberType]  # pydub untyped
        path = f'_temp/{uid}_{pid}_complete_speech_profile.wav'
        aseg.export(path, format='wav')  # type: ignore[reportUnknownMemberType]  # pydub untyped
        people.append({'id': pid, 'path': path})
    return people

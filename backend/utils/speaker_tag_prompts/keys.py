"""Ignored-voice identity shared by storage, prompt selection and voice matching."""

import hashlib


def ignored_voice_key(conversation_id: str, speaker_id: int) -> str:
    key = f'{conversation_id}:{speaker_id}'
    # The colon requires a quoted field path; backslashes/backticks are escaped.
    escaped = key.replace('\\', '\\\\').replace('`', '\\`')
    path = f'ignored_voices.`{escaped}`.assignment_generation'
    if len(path.encode('utf-8')) <= 1500:
        return key
    # This suffix cannot collide with an existing decimal speaker suffix.
    return f'sha256:{hashlib.sha256(key.encode("utf-8")).hexdigest()}:'

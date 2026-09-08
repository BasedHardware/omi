"""Sanitized, interprocess-safe JSONL evidence for the Sync stack gauntlet.

The worker handles local test audio and transcript data.  Evidence accepts only
sanitized metadata, so retained failures are useful without preserving either.
"""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
from typing import Any

_FORBIDDEN_KEYS = frozenset(
    {
        'audio',
        'audio_bytes',
        'body',
        'file_path',
        'payload',
        'raw_blob_paths',
        'text',
        'transcript',
        'uid',
    }
)


def evidence_dir() -> Path:
    state_dir = os.getenv('OMI_SYNC_STACK_STATE_DIR', '').strip()
    if not state_dir:
        raise RuntimeError('OMI_SYNC_STACK_STATE_DIR is required for Sync stack evidence')
    path = Path(state_dir) / 'evidence'
    path.mkdir(parents=True, exist_ok=True)
    return path


def _assert_safe(value: Any, *, key: str | None = None) -> None:
    if key in _FORBIDDEN_KEYS:
        raise ValueError(f'unsafe evidence key: {key}')
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            if not isinstance(child_key, str):
                raise ValueError('evidence keys must be strings')
            _assert_safe(child_value, key=child_key)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _assert_safe(item)
        return
    if isinstance(value, str):
        for sentinel_name in ('OMI_SYNC_STACK_SENSITIVE_UID', 'OMI_SYNC_STACK_TRANSCRIPT_TOKEN'):
            sentinel = os.getenv(sentinel_name, '')
            if sentinel and sentinel in value:
                raise ValueError(f'unsafe evidence contains {sentinel_name}')


def write_event(stream: str, event: dict[str, Any]) -> None:
    """Append one metadata-only event while serializing independent ASGI roles."""
    if not stream.replace('_', '').isalnum():
        raise ValueError(f'invalid evidence stream: {stream!r}')
    _assert_safe(event)
    line = json.dumps(event, sort_keys=True, separators=(',', ':'))
    path = evidence_dir() / f'{stream}.jsonl'
    with path.open('a', encoding='utf-8') as output:
        fcntl.flock(output.fileno(), fcntl.LOCK_EX)
        try:
            output.write(line + '\n')
            output.flush()
        finally:
            fcntl.flock(output.fileno(), fcntl.LOCK_UN)

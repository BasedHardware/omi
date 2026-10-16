"""Playback identity from an ordered immutable source manifest, never encoded size alone."""

import hashlib
import json
from typing import Any


def source_fingerprint(chunks: list[dict[str, Any]]) -> str | None:
    # GCS list supplies generation + checksums without another object read.
    # Legacy/packed entries without immutable evidence keep their random IDs.
    if not chunks or any(not c.get('path') or not c.get('generation') for c in chunks):
        return None
    manifest = [
        {key: c.get(key) for key in ('bucket', 'path', 'generation', 'md5_hash', 'crc32c', 'timestamp', 'size', 'span')}
        for c in chunks
    ]
    payload = {'format': 'mp3-48k-16khz-gapfill-v1', 'chunks': manifest}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()


def validate_sources(audio_files: list[dict[str, Any]], chunks: list[dict[str, Any]]) -> None:
    """Refuse changed sources under a stamped identity, including mid-build overwrite."""
    for af in audio_files:
        expected = af.get('source_fingerprint')
        if not expected:
            continue
        timestamps = set(af['chunk_timestamps'])
        selected = [chunk for chunk in chunks if chunk['timestamp'] in timestamps]
        if source_fingerprint(selected) != expected:
            raise RuntimeError('playback source manifest changed')


def retain_aliases(audio_files: list[dict[str, Any]], previous: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep recent client handles while rebuilding groups, without trusting old artifacts.

    Aliases resolve to the *current* group/identity, never the old cached bytes.
    A bounded history avoids growing the conversation document on every append.
    Splits only retain an alias when one new group covers its entire old source.
    """
    result = [dict(af) for af in audio_files]
    for old in previous:
        timestamps = set(old.get('chunk_timestamps') or [])
        matches = [af for af in result if timestamps and timestamps <= set(af.get('chunk_timestamps') or [])]
        if len(matches) != 1:
            continue
        target = matches[0]
        aliases = [*(target.get('legacy_ids') or []), *(old.get('legacy_ids') or []), old.get('id')]
        target['legacy_ids'] = list(dict.fromkeys(a for a in aliases if isinstance(a, str) and a != target.get('id')))[
            -128:
        ]
    return result

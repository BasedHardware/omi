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

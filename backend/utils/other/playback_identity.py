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
        {
            **{
                key: c.get(key)
                for key in ('bucket', 'path', 'generation', 'md5_hash', 'crc32c', 'timestamp', 'size', 'span')
            },
            **({'raw_source_start': c['raw_source_start']} if 'raw_source_start' in c else {}),
        }
        for c in chunks
    ]
    payload = {'format': 'mp3-48k-16khz-gapfill-v1', 'chunks': manifest}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()


def resolve_sources(audio_file: dict[str, Any], chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Resolve current entries only when the complete immutable manifest matches."""
    expected = audio_file.get('source_fingerprint')
    timestamps = set(audio_file['chunk_timestamps'])
    selected = [chunk for chunk in chunks if chunk['timestamp'] in timestamps]
    if not expected or source_fingerprint(selected) == expected:
        return selected
    aliases = {
        chunk['legacy_timestamp']
        for chunk in chunks
        if chunk.get('legacy_timestamp') in timestamps and chunk['timestamp'] not in timestamps
    }
    compatible = []
    for chunk in chunks:
        if chunk.get('legacy_timestamp') in aliases:
            compatible.append(({**chunk, 'timestamp': chunk['legacy_timestamp']}, chunk))
        elif chunk['timestamp'] in timestamps and chunk['timestamp'] not in aliases:
            compatible.append((chunk, chunk))
    compatible.sort(key=lambda pair: (pair[0]['timestamp'], pair[0]['path']))
    # Only the lookup clock changes in this compatibility view. Generations,
    # checksums, paths, spans and raw selectors must still match the old hash.
    if source_fingerprint([view for view, _ in compatible]) == expected:
        return [current for _, current in compatible]
    raise RuntimeError('playback source manifest changed')


def validate_sources(audio_files: list[dict[str, Any]], chunks: list[dict[str, Any]]) -> None:
    """Refuse changed sources under a stamped identity, including mid-build overwrite."""
    for af in audio_files:
        if af.get('source_fingerprint'):
            resolve_sources(af, chunks)


def retain_aliases(audio_files: list[dict[str, Any]], previous: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep recent client handles while rebuilding groups, without trusting old artifacts.

    Aliases resolve to the *current* group/identity, never the old cached bytes.
    A bounded history avoids growing the conversation document on every append.
    Splits only retain an alias when one new group covers its entire old source.
    """
    result = [dict(af) for af in audio_files]
    for old in previous:
        timestamps = set(old.get('chunk_timestamps') or [])

        def covers(af: dict[str, Any]) -> bool:
            current = set(af.get('chunk_timestamps') or [])
            if not timestamps or not current:
                return False
            if timestamps <= current:
                return True
            if not timestamps <= current | {round(stamp, 3) for stamp in current}:
                return False
            # A rounded handle must cover the entire old part, not merely a
            # nearby tiny raw fragment. Ambiguous/split groups retain no alias.
            if old.get('duration') is None or af.get('duration') is None:
                return False
            return min(current) <= min(timestamps) + 0.001 and (
                min(current) + af['duration'] >= min(timestamps) + old['duration'] - 0.001
            )

        matches = [af for af in result if covers(af)]
        if len(matches) != 1:
            continue
        target = matches[0]
        aliases = [*(target.get('legacy_ids') or []), *(old.get('legacy_ids') or []), old.get('id')]
        target['legacy_ids'] = list(dict.fromkeys(a for a in aliases if isinstance(a, str) and a != target.get('id')))[
            -128:
        ]
    return result

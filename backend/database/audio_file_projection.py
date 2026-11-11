"""Pure AudioFile grouping projection, independent of storage discovery."""

import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from models.audio_file import AudioFile, ChunkSpan
from utils.other.playback_identity import source_fingerprint


def finalize_audio_file_group(
    uid: str, conversation_id: str, chunk_group: List[dict], existing_files: List[AudioFile]
) -> Optional[AudioFile]:
    """
    Create an AudioFile record that references chunks (no merging).

    Args:
        uid: User ID
        conversation_id: Conversation ID
        chunk_group: List of chunk dicts to reference
        existing_files: List of existing audio files

    Returns:
        AudioFile object or None if failed
    """
    if not chunk_group:
        return None

    # Generate file ID
    source_hash = source_fingerprint(chunk_group)
    file_id = (
        str(uuid.uuid5(uuid.NAMESPACE_OID, f'{uid}/{conversation_id}/{source_hash}'))
        if source_hash
        else str(uuid.uuid4())
    )

    # Extract timestamps
    timestamps = [chunk['timestamp'] for chunk in chunk_group]

    # v2 groups carry validated contiguous coverage spans from blob metadata;
    # duration is the authoritative span extent, never an encoded-size guess.
    spans: List[Tuple[float, float]] = []
    playback_starts: List[float] = []
    for chunk in chunk_group:
        span = chunk.get('span')
        if not isinstance(span, dict):
            spans = []
            break
        try:
            start = float(span['start'])
            samples = float(span['samples'])
            rate = float(span['sample_rate'])
        except (KeyError, TypeError, ValueError):
            spans = []
            break
        if samples <= 0 or rate <= 0:
            spans = []
            break
        spans.append((start, start + samples / rate))
        playback_start = span.get('playback_start')
        if isinstance(playback_start, (int, float)):
            playback_starts.append(float(playback_start))

    if spans:
        started_at = datetime.fromtimestamp(spans[0][0], tz=timezone.utc)
        duration = spans[-1][1] - spans[0][0]
        return AudioFile(
            id=file_id,
            source_fingerprint=source_hash,
            uid=uid,
            conversation_id=conversation_id,
            chunk_timestamps=timestamps,
            provider='gcp',
            started_at=started_at,
            duration=duration,
            chunk_spans=[ChunkSpan(start=round(start, 3), end=round(end, 3)) for start, end in spans],
            # The normalized wall basis holds only when every chunk in the
            # group carries its persisted playback start; one legacy chunk
            # leaves the part on the raw capture clock.
            playback_start=(min(playback_starts) if len(playback_starts) == len(spans) else None),
        )

    # Calculate started_at and duration from timestamps and blob sizes
    started_at = datetime.fromtimestamp(chunk_group[0]['timestamp'], tz=timezone.utc)
    last_chunk_start = datetime.fromtimestamp(chunk_group[-1]['timestamp'], tz=timezone.utc)
    # Estimate last chunk duration from blob size (PCM16 mono at 16kHz = 32000 bytes/sec).
    # Approximate for opus-encoded blobs; conversation_audio.captured_duration (from
    # decoded PCM) is the display source of truth.
    last_chunk_size = chunk_group[-1].get('size') or 0
    last_chunk_duration = last_chunk_size / 32000.0 if last_chunk_size > 0 else 5.0
    duration = (last_chunk_start - started_at).total_seconds() + last_chunk_duration

    return AudioFile(
        id=file_id,
        source_fingerprint=source_hash,
        uid=uid,
        conversation_id=conversation_id,
        chunk_timestamps=timestamps,
        provider='gcp',
        started_at=started_at,
        duration=duration,
    )

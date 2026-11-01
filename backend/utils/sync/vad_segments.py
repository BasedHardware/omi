"""Shared legacy sync VAD grouping and duration cap; no model imports."""

import os

MAX_VAD_SEGMENT_SECONDS = int(os.getenv('SYNC_MAX_VAD_SEGMENT_SECONDS', '300'))


def merge_and_cap_vad_segments(voice_segments: list, max_seconds: int = MAX_VAD_SEGMENT_SECONDS) -> list:
    merged = []
    for segment in voice_segments:
        if (
            merged
            and (segment['start'] - merged[-1]['end']) < 120
            and (segment['end'] - merged[-1]['start']) <= max_seconds
        ):
            merged[-1]['end'] = segment['end']
        else:
            merged.append(dict(segment))

    segments = []
    for segment in merged:
        if segment['end'] - segment['start'] <= max_seconds:
            segments.append(segment)
        else:
            chunk_start = segment['start']
            while chunk_start < segment['end']:
                chunk_end = min(chunk_start + max_seconds, segment['end'])
                segments.append({'start': chunk_start, 'end': chunk_end})
                chunk_start = chunk_end
    return segments

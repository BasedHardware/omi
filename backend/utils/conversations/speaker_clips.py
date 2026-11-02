"""Assemble one speaker clip from a session's verified decoded cache."""

import math
from typing import List, Optional, Tuple

from database.audio_timeline import COVERAGE_TOLERANCE_SECONDS
from utils.conversations.speaker_sync_store import in_sync_store
from utils.other.audio_chunks import AudioChunkReadSession
from utils.stt.conversation_speakers import MIN_EMBED_SECONDS

SAMPLE_RATE = 16000
# Long segments often hold more than one voice; the middle is the most representative.
MAX_CLIP_SECONDS = 15.0


def _inward_sample(bound: float, origin: float, *, exclusive_end: bool) -> int:
    """Cut inward on this chunk's grid, snapping only arithmetic roundoff.

    Subtracting epoch-sized floats loses low bits. Bound that uncertainty by
    the operands' ULPs rather than treating a fractional sample as an integer.
    An end index includes only complete samples before the exclusive end.
    """
    offset = (bound - origin) * SAMPLE_RATE
    uncertainty = (math.ulp(bound) + math.ulp(origin)) * SAMPLE_RATE + math.ulp(offset)
    nearest = round(offset)
    if abs(offset - nearest) <= uncertainty:
        offset = float(nearest)
    return math.floor(offset) if exclusive_end else math.ceil(offset)


def verified_clip(
    session: AudioChunkReadSession,
    start: float,
    end: float,
    *,
    windows: Optional[List[Tuple[float, float]]] = None,
    sync_store_only: bool = False,
) -> Tuple[Optional[bytes], str]:
    """Assemble at most 15s from the invocation's generation-pinned decoded cache.

    No downloads, padding, or interpolation. Only a tolerance-sized leading or
    trailing edge may be trimmed; an internal missing extent refuses the clip.
    Used only when the exact base midpoint clip cannot embed. Inventory/decoded
    coverage validation has already admitted this session. Cuts are inward and
    the sum of pieces has an integer 240,000-sample budget, even on mixed grids.
    """
    if end - start > MAX_CLIP_SECONDS:
        middle = (start + end) / 2.0
        start, end = middle - MAX_CLIP_SECONDS / 2, middle + MAX_CLIP_SECONDS / 2
    if end - start < MIN_EMBED_SECONDS:
        return None, 'clip_too_short'
    position = start
    pieces = []
    remaining_samples = int(MAX_CLIP_SECONDS * SAMPLE_RATE)
    for chunk in sorted(session.chunks, key=lambda c: c.get('span', {}).get('start', c['timestamp'])):
        chunk_start = chunk.get('span', {}).get('start', chunk['timestamp'])
        pcm, _ = session.cache.get(chunk['path'], (None, 'missing_blob'))
        if pcm is None or (sync_store_only and not in_sync_store(chunk)):
            continue
        chunk_end = chunk_start + len(pcm) / (SAMPLE_RATE * 2)
        if chunk_end <= position or chunk_start >= end:
            continue
        # Between pieces, allow only wall-axis roundoff (well below one sample).
        if chunk_start > position + 1e-6:
            if pieces or chunk_start - position > COVERAGE_TOLERANCE_SECONDS:
                return None, 'chunk_boundary' if pieces else 'no_clip'
            position = chunk_start
        stop = min(end, chunk_end)
        first_sample = max(0, _inward_sample(position, chunk_start, exclusive_end=False))
        last_sample = min(len(pcm) // 2, _inward_sample(stop, chunk_start, exclusive_end=True))
        last_sample = min(last_sample, first_sample + remaining_samples)
        piece = pcm[first_sample * 2 : last_sample * 2]
        if piece and windows is not None:
            windows.append((chunk_start + first_sample / SAMPLE_RATE, chunk_start + last_sample / SAMPLE_RATE))
        pieces.append(piece)
        remaining_samples -= len(piece) // 2
        position = stop
        if position >= end - 1e-6:
            clip = b''.join(pieces)
            return (clip, 'none') if len(clip) >= MIN_EMBED_SECONDS * SAMPLE_RATE * 2 else (None, 'clip_too_short')
    if pieces and end - position <= COVERAGE_TOLERANCE_SECONDS:
        clip = b''.join(pieces)
        return (clip, 'none') if len(clip) >= MIN_EMBED_SECONDS * SAMPLE_RATE * 2 else (None, 'clip_too_short')
    return None, 'chunk_boundary' if pieces else 'no_clip'

"""Complete short speaker clips positioned by each legacy blob's own timestamp.

This repairs merge-induced drift, not legacy capture-clock drift. Callers must
still verify the clip against the labeled transcript before learning a voice.
"""

import math
from typing import Optional

from utils.metrics import OMI_SPEAKER_CLIP_COVERAGE_TOTAL
from utils.other.storage import iter_audio_chunk_pcm

MAX_SPEAKER_CLIP_SECONDS = 12.0
MAX_SPEAKER_CLIP_BLOBS = 32


def legacy_speaker_clip_pcm(
    uid: str, conversation_id: str, start: float, end: float, sample_rate: int = 16000
) -> Optional[bytes]:
    """Return PCM16 for an absolute wall-time window, or None for missing evidence.

    Search individual blobs newest first, at most 32 downloads including missing
    blobs. Earlier overlapping blobs may fill gaps left by a shorter newer blob.
    Batch interiors have no trustworthy legacy clock and are never admitted.
    Only a completely filled integer sample window may leave this function.
    """
    if (
        not math.isfinite(start)
        or not math.isfinite(end)
        or end <= start
        or end - start > MAX_SPEAKER_CLIP_SECONDS
        or sample_rate <= 0
    ):
        OMI_SPEAKER_CLIP_COVERAGE_TOTAL.labels(outcome='invalid_window').inc()
        return None
    needed = round((end - start) * sample_rate)
    if needed <= 0:
        OMI_SPEAKER_CLIP_COVERAGE_TOTAL.labels(outcome='invalid_window').inc()
        return None

    def wanted(blob_start: float, next_start: Optional[float]) -> bool:
        return blob_start < end

    uncovered = [(0, needed)]
    result = bytearray(needed * 2)
    for blob_start, pcm in iter_audio_chunk_pcm(
        uid,
        conversation_id,
        wanted,
        sample_rate=sample_rate,
        single_chunks_only=True,
        newest_first=True,
        max_downloads=MAX_SPEAKER_CLIP_BLOBS,
    ):
        first = round((blob_start - start) * sample_rate)
        last = first + len(pcm) // 2
        remaining = []
        for left, right in uncovered:
            begin, finish = max(left, first), min(right, last)
            if finish <= begin:
                remaining.append((left, right))
                continue
            result[begin * 2 : finish * 2] = pcm[(begin - first) * 2 : (finish - first) * 2]
            if left < begin:
                remaining.append((left, begin))
            if finish < right:
                remaining.append((finish, right))
        uncovered = remaining
        if not uncovered:
            OMI_SPEAKER_CLIP_COVERAGE_TOTAL.labels(outcome='covered').inc()
            return bytes(result)
    outcome = 'gap' if uncovered[0][0] > 0 and uncovered[-1][1] < needed else 'missing'
    OMI_SPEAKER_CLIP_COVERAGE_TOTAL.labels(outcome=outcome).inc()
    return None

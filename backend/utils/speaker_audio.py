"""Complete short speaker clips positioned by each legacy blob's own timestamp.

This repairs merge-induced drift, not legacy capture-clock drift. Callers must
still verify the clip against the labeled transcript before learning a voice.
"""

import math
from typing import Optional

from utils.metrics import OMI_SPEAKER_CLIP_COVERAGE_TOTAL
from utils.other.storage import iter_audio_chunk_pcm

MAX_SPEAKER_CLIP_SECONDS = 12.0


def legacy_speaker_clip_pcm(
    uid: str, conversation_id: str, start: float, end: float, sample_rate: int = 16000
) -> Optional[bytes]:
    """Return PCM16 for an absolute wall-time window, or None for any missing samples.

    Download only the predecessor blob and blobs starting inside the window.
    The iterator resolves batch blobs by their actual start, even when the
    requested window begins at an interior batch timestamp. Overlap is consumed
    once; gaps are never padded with silence or counted as teaching evidence.
    Integer sample offsets avoid accumulating floating-point merge drift.
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
        return blob_start < end and (next_start is None or next_start > start)

    cursor = 0
    pieces = []
    for blob_start, pcm in iter_audio_chunk_pcm(uid, conversation_id, wanted, sample_rate=sample_rate):
        first = round((blob_start - start) * sample_rate)
        last = first + len(pcm) // 2
        if last <= cursor:
            continue
        if first > cursor:
            OMI_SPEAKER_CLIP_COVERAGE_TOTAL.labels(outcome='gap').inc()
            return None
        take = min(last, needed) - cursor
        offset = cursor - first
        pieces.append(pcm[offset * 2 : (offset + take) * 2])
        cursor += take
        if cursor == needed:
            OMI_SPEAKER_CLIP_COVERAGE_TOTAL.labels(outcome='covered').inc()
            return b''.join(pieces)
    OMI_SPEAKER_CLIP_COVERAGE_TOTAL.labels(outcome='missing').inc()
    return None

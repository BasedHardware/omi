"""Speaker clips: proven sample placement with legacy batch compatibility.

An unverified batch keeps main's timing behavior and is never reported as proven
coverage. Teaching still applies its text-containment and dominant-speaker gates.
"""

import math
from typing import Optional

from utils.metrics import OMI_SPEAKER_CLIP_COVERAGE_TOTAL
from utils.other import storage
from utils.other.audio_chunks import (
    AudioChunkReadSession,
    MAX_SPEAKER_DOWNLOADS,
    iter_audio_chunk_pcm,
    chunk_start,
)

MAX_SPEAKER_CLIP_SECONDS = 12.0
MAX_SPEAKER_CLIP_BLOBS = MAX_SPEAKER_DOWNLOADS
CLIP_CALLERS = ('teaching', 'owner_confirmation', 'preview', 'unknown')


def legacy_speaker_clip_pcm(
    uid: str,
    conversation_id: str,
    start: float,
    end: float,
    sample_rate: int = 16000,
    *,
    session: Optional[AudioChunkReadSession] = None,
    timestamps: Optional[list[float]] = None,
    caller: str = 'unknown',
) -> Optional[bytes]:
    """Strict spans prove coverage; uncertain timestamps retain main's exact merger.

    Both policies share one bounded session. Exhaustion never changes policy.
    """
    caller = caller if caller in CLIP_CALLERS else 'unknown'

    def record(outcome, reason):
        OMI_SPEAKER_CLIP_COVERAGE_TOTAL.labels(outcome=outcome, reason=reason, caller=caller).inc()

    if (
        not math.isfinite(start)
        or not math.isfinite(end)
        or end <= start
        or end - start > MAX_SPEAKER_CLIP_SECONDS
        or sample_rate <= 0
    ):
        record('invalid_window', 'invalid_window')
        return None
    start_sample = round(start * sample_rate)
    end_sample = round(end * sample_rate)
    needed = end_sample - start_sample
    if needed <= 0:
        record('invalid_window', 'invalid_window')
        return None
    session = session or AudioChunkReadSession(uid, conversation_id, sample_rate)
    listed_chunks = session.chunks
    if session.limit_hit:
        record('missing', 'download_limit')
        return None
    session.reason = 'missing_blob'

    # Use the manifest's original timestamps, exactly as main did. Batch ranges
    # describe chunk starts, not continuity or the last chunk's end.
    ordered = sorted(set(timestamps)) if timestamps is not None else [c['timestamp'] for c in listed_chunks]
    first = max((i for i, ts in enumerate(ordered) if ts <= start), default=0)
    relevant = [ts for ts in ordered[first:] if ts <= end]

    def main_clip(loader):
        if not relevant:
            return None
        try:
            merged = storage.download_audio_chunks_and_merge(
                uid,
                conversation_id,
                relevant,
                sample_rate=sample_rate,
                listed_chunks=listed_chunks,
                chunk_loader=loader,
            )
        except FileNotFoundError:
            return None
        offset = start_sample - round(min(relevant) * sample_rate)
        return merged[max(0, offset) * 2 : max(0, offset + needed) * 2] or None

    # Any selected uncertain object requires main's policy for this window.
    # Include batches by their requested timestamp range, as the merger does.
    selected = []
    relevant_set = {round(ts, 3) for ts in relevant}
    for chunk in listed_chunks:
        if chunk.get('is_batch'):
            key = chunk['path'].split('/')[-1].split('.batch.', 1)[0]
            bounds = [float(value) for value in key.split('-', 1)]
            matches = any(bounds[0] <= round(ts, 3) <= bounds[-1] for ts in relevant)
        else:
            matches = round(chunk['timestamp'], 3) in relevant_set
        if matches:
            selected.append(chunk)
    if any(not chunk.get('span') for chunk in selected):
        pcm = main_clip(session.fetch)
        if session.limit_hit or not session.in_budget():
            record('missing', 'download_limit')
            return None
        record('compatibility' if pcm else 'missing', 'uncertain_timing' if pcm else session.reason)
        return pcm

    # Main must have selected audio before strict placement can improve it.
    # In particular, do not recover an outlasting predecessor main skipped.
    if not relevant:
        record('missing', 'missing_blob')
        return None

    def wanted(blob_start: float, next_start: Optional[float]) -> bool:
        return blob_start < end and any(chunk_start(c) == blob_start for c in selected)

    uncovered = [(0, needed)]
    result = bytearray(needed * 2)
    for blob_start, pcm in iter_audio_chunk_pcm(
        uid,
        conversation_id,
        wanted,
        sample_rate=sample_rate,
        single_chunks_only=True,
        newest_first=True,
        session=session,
        window_start=start,
    ):
        chunk = session.last_chunk
        if chunk is None:
            chunk = next((c for c in selected if chunk_start(c) == blob_start), None)
        span = chunk.get('span') if chunk is not None else None
        if span is None:
            # No metadata means no authoritative coverage, even in mixed stores.
            continue
        if span['sample_rate'] != sample_rate:
            session.reason = 'decode_failed'
            continue
        pcm = pcm[: span['samples'] * 2]
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
            if not session.in_budget():
                record('missing', 'download_limit')
                return None
            baseline = main_clip(session.fetch)
            if baseline is None or len(baseline) < needed * 2 or not session.in_budget():
                record('missing', session.reason)
                return None
            record('covered', 'complete')
            return bytes(result)
    outcome = 'gap' if uncovered[0][0] > 0 and uncovered[-1][1] < needed else 'missing'
    reason = session.reason if session.reason != 'missing_blob' else ('gap' if outcome == 'gap' else 'missing_blob')
    record(outcome, reason)
    return None

"""Speaker clips: proven sample placement with legacy batch compatibility.

An unverified batch keeps main's timing behavior and is never reported as proven
coverage. Teaching still applies its text-containment and dominant-speaker gates.
"""

import math
from typing import Optional

from utils.metrics import OMI_SPEAKER_CLIP_COVERAGE_TOTAL
from utils.other import storage
from utils.other.audio_chunks import AudioChunkReadSession, MAX_SPEAKER_DOWNLOADS, iter_audio_chunk_pcm

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
    """Return real PCM for a short absolute window, without inventing samples.

    Filename-only starts have +/-0.5ms uncertainty; uncovered boundary samples
    within that tolerance are trimmed, never padded. Span metadata is exact.
    Unverified batches use the existing merger, not a claim of strict coverage.
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
    needed = round((end - start) * sample_rate)
    if needed <= 0:
        record('invalid_window', 'invalid_window')
        return None
    session = session or AudioChunkReadSession(uid, conversation_id, sample_rate)
    session.reason = 'missing_blob'

    # Use the manifest's original timestamps, exactly as main did. Batch ranges
    # describe chunk starts, not continuity or the last chunk's end.
    ordered = sorted(set(timestamps)) if timestamps is not None else [c['timestamp'] for c in session.chunks]
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
                listed_chunks=session.chunks,
                chunk_loader=loader,
            )
        except FileNotFoundError:
            return None
        offset = round((start - min(relevant)) * sample_rate)
        return merged[max(0, offset) * 2 : max(0, offset + needed) * 2] or None

    if ordered:
        unverified = False
        for chunk in session.chunks:
            if not chunk.get('is_batch') or chunk.get('span'):
                continue
            key = chunk['path'].split('/')[-1].split('.batch.', 1)[0]
            bounds = [float(value) for value in key.split('-', 1)]
            if any(bounds[0] <= round(ts, 3) <= bounds[-1] for ts in relevant):
                unverified = True
                break
        if unverified:
            pcm = main_clip(session.fetch)
            if session.limit_hit:
                pcm = main_clip(session.compatibility_fetch)
            reason = 'download_limit' if session.compatibility_escape else 'unverified_batch' if pcm else session.reason
            record('compatibility' if pcm else 'missing', reason)
            return pcm or None

    def wanted(blob_start: float, next_start: Optional[float]) -> bool:
        return blob_start < end + 0.000501

    uncovered = [(0, needed)]
    result = bytearray(needed * 2)
    tolerance = round(0.0005 * sample_rate)
    uncertain = []
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
        span = chunk.get('span') if chunk is not None else None
        authoritative = bool(span)
        if span is not None:
            if span['sample_rate'] != sample_rate:
                session.reason = 'decode_failed'
                continue
            pcm = pcm[: span['samples'] * 2]
        first = round((blob_start - start) * sample_rate)
        if not authoritative and abs(first) <= tolerance and len(pcm) // 2 == needed:
            # A complete boundary-aligned filename-only chunk can have either
            # sign of rounding error. Move its uncertain origin within the
            # known +/-0.5ms interval; keep every real sample and the 10s floor.
            first = 0
        last = first + len(pcm) // 2
        if not authoritative:
            uncertain.append((first, last))
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
            record('covered', 'complete')
            return bytes(result)
    if session.limit_hit and ordered and relevant:
        # A resource cap does not prove main's clip was wrong. Preserve its
        # selected-window behavior, and expose the cost exception explicitly.
        pcm = main_clip(session.compatibility_fetch)
        record('compatibility' if pcm else 'missing', 'download_limit')
        return pcm
    # Only timestamp-rounding boundary uncertainty may shorten a window.
    # Only joins bounded by two uncertain starts may shed rounding samples;
    # authoritative truncation and larger gaps remain unavailable.
    left, right = 0, needed
    rounded_holes = []
    for begin, finish in uncovered:
        if begin == 0 and finish <= tolerance and any(abs(first - finish) <= 1 for first, _ in uncertain):
            left = finish
        elif finish == needed and needed - begin <= tolerance and any(abs(last - begin) <= 1 for _, last in uncertain):
            right = begin
        elif (
            finish - begin <= tolerance * 2
            and any(last == begin for _, last in uncertain)
            and any(first == finish for first, _ in uncertain)
        ):
            rounded_holes.append((begin, finish))
        else:
            outcome = 'gap' if uncovered[0][0] > 0 and uncovered[-1][1] < needed else 'missing'
            record(
                outcome,
                session.reason if session.reason != 'missing_blob' else ('gap' if outcome == 'gap' else 'missing_blob'),
            )
            return None
    if right > left:
        record('covered', 'timestamp_rounding')
        pieces = []
        for begin, finish in rounded_holes:
            pieces.append(result[left * 2 : begin * 2])
            left = finish
        pieces.append(result[left * 2 : right * 2])
        return b''.join(pieces)
    record('missing', session.reason)
    return None

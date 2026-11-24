"""Pure window framing and overlap proof for the pusher capture buffer."""

import hashlib
from typing import Deque, Optional, Tuple

from utils.pusher_protocol import ByteBudget, extend_bounded

AUDIO_TIMELINE_CONTINUITY_TOLERANCE = 0.001


def append_window_run(
    *,
    durable: bool,
    sequence: int,
    buffer: bytearray,
    audio_data: bytes,
    start: float,
    budget: ByteBudget,
    gap_before: bool = False,
) -> tuple[Optional[dict], bool]:
    """Buffer one accepted private-cloud run; returns (frame checkpoint, stored).

    The checkpoint pins the run into the durable window manifest when the
    session runs the outbox; legacy sessions buffer the same bytes for the
    batched .batch.enc projection without a checkpoint.
    """
    checkpoint = None
    if durable:
        # The per-message commit rejected non-sample-aligned PCM as a protocol
        # error; keep that contract at the buffer edge so odd payloads cannot
        # merge into a silently zero-sample window.
        if len(audio_data) % 2:
            raise ValueError('audio payload is not sample-aligned')
        checkpoint = {
            'sequence': sequence,
            'byte_offset': len(buffer),
            'bytes': len(audio_data),
            'start': start,
            'samples': len(audio_data) // 2,
            'gap_before': gap_before,
            'sha256': hashlib.sha256(audio_data).hexdigest(),
        }
    stored = extend_bounded(buffer, audio_data, 'private_cloud_buffer', budget)
    return checkpoint, stored


def v2_overlap_conflict(
    run_start: float,
    overlap_bytes: int,
    audio: bytes,
    *,
    sample_rate: int,
    private_cloud_chunk_start_time: float | None,
    private_cloud_sync_buffer: bytearray,
    v2_flushed_runs: Deque[Tuple[float, float, str]],
    frames: list[dict] | None = None,
) -> bool:
    """True when the overlapping range's bytes cannot be proven identical.

    The overlap region [run_start, run_start + overlap_bytes) is
    verified against the live buffer (byte compare) and, for the part
    predating it, against the flushed-run digest ledger. Any region
    that can be neither compared nor digest-matched is a conflict: the
    already-stored bytes stay, the unverified overlap is dropped, and
    only the frame's new tail past the accepted end is kept.
    """
    tol = AUDIO_TIMELINE_CONTINUITY_TOLERANCE
    bps = sample_rate * 2
    overlap_hi = run_start + overlap_bytes / bps
    if frames:
        # In a gapped window, wall offsets are not byte offsets. Compare each
        # retained frame and require complete captured coverage of the overlap.
        cursor = run_start
        for frame in frames:
            end = frame['start'] + frame['samples'] / sample_rate
            lo, hi = max(cursor, frame['start']), min(end, overlap_hi)
            if hi <= lo:
                continue
            if lo > cursor + tol:
                return True
            source_offset = round((lo - run_start) * bps)
            buffer_offset = frame['byte_offset'] + round((lo - frame['start']) * bps)
            count = round((hi - lo) * bps)
            if audio[source_offset : source_offset + count] != bytes(
                private_cloud_sync_buffer[buffer_offset : buffer_offset + count]
            ):
                return True
            cursor = hi
            if cursor >= overlap_hi - tol:
                return False
        return True
    buffer_lo = private_cloud_chunk_start_time if private_cloud_sync_buffer else None

    def flushed_runs_cover(need_lo: float, need_hi: float) -> bool:
        if need_hi <= need_lo + tol:
            return True
        covered_hi = need_hi
        for fs, fe, digest in reversed(v2_flushed_runs):
            if fe <= need_lo + tol:
                break
            if fs >= covered_hi - tol:
                continue
            if fs < need_lo - tol:
                # Partial run overlap: only whole-run digests exist.
                return False
            off = round((fs - run_start) * bps)
            n = round((fe - fs) * bps)
            if off < 0 or off + n > len(audio) or hashlib.sha256(audio[off : off + n]).hexdigest() != digest:
                return False
            covered_hi = fs
            if covered_hi <= need_lo + tol:
                return True
        return covered_hi <= need_lo + tol

    if buffer_lo is None or buffer_lo > run_start + tol:
        pre_hi = overlap_hi if buffer_lo is None else min(overlap_hi, buffer_lo)
        if not flushed_runs_cover(run_start, pre_hi):
            return True
    if buffer_lo is not None:
        b_lo = max(run_start, buffer_lo)
        if b_lo < overlap_hi - tol:
            in_audio = round((b_lo - run_start) * bps)
            in_audio -= in_audio % 2
            in_buffer = round((b_lo - buffer_lo) * bps)
            in_buffer -= in_buffer % 2
            comparable = min(
                overlap_bytes - in_audio, len(audio) - in_audio, len(private_cloud_sync_buffer) - in_buffer
            )
            if (
                comparable > 0
                and bytes(private_cloud_sync_buffer[in_buffer : in_buffer + comparable])
                != audio[in_audio : in_audio + comparable]
            ):
                return True
    return False

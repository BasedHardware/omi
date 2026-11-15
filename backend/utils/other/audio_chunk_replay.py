"""Bounded verification of an audio payload's already-committed storage prefix.

Pure helpers only: all storage I/O arrives through the keyword-only ``bucket``
and ``list_chunks`` seams so this module never imports ``storage`` itself.
"""

import math
from functools import partial
import time
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from database.audio_timeline import get_extension_for_path
from utils import encryption
from utils.other.raw_audio_read import read_pack, select_raw_pcm
from utils.other.raw_audio import decode_capture
from utils.other.audio_frame_table import resampled_samples

RECONCILE_MAX_OBJECTS = 64
RECONCILE_MAX_BYTES = 64 * 1024 * 1024
RECONCILE_MAX_SECONDS = 10.0
RECONCILE_MAX_ATTEMPTS = 3


class AudioChunkContentConflict(ValueError):
    """Different bytes already occupy an immutable audio projection name."""


def _listed_generation(chunk: Mapping[str, Any]) -> Optional[int]:
    generation = chunk.get('generation')
    if not isinstance(generation, int) or isinstance(generation, bool) or generation <= 0:
        return None
    return generation


def _raw_chunk_object_pcm(
    bucket: Any, chunk: Mapping[str, Any], uid: str, deadline: float, max_bytes: int, sample_rate: int = 16000
) -> Tuple[Optional[bytes], int]:
    """Decode one listed object to raw PCM under the reconciliation budget.

    ``max_bytes`` is the remaining reconciliation byte budget: a listed object
    whose declared size exceeds it is rejected before any download so the
    bounded budget can never be overshot. Returns ``(pcm, charged_bytes)``;
    ``pcm`` is None whenever the evidence is missing, unreadable, unpinned,
    oversized, or not provably raw PCM.
    """
    path = chunk.get('path')
    if not isinstance(path, str):
        return None, 0
    ext = get_extension_for_path(path)
    raw_capture = path.startswith(f'raw-live/{uid}/')
    if not raw_capture and ext not in ('batch.bin', 'batch.enc', 'bin', 'enc'):
        return None, 0
    size = chunk.get('size')
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0 or size > max_bytes:
        return None, 0
    generation = _listed_generation(chunk)
    if generation is None:
        return None, 0
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return None, 0
    try:
        if raw_capture:
            pcm = read_pack(
                bucket,
                path,
                uid,
                {'timeout': remaining, 'retry': None, 'if_generation_match': generation},
                sample_rate=sample_rate,
            )
            return pcm, size
        blob_bytes = bucket.blob(path).download_as_bytes(
            timeout=max(0.001, remaining),
            retry=None,
            end=size - 1,
            if_generation_match=generation,
        )
    except Exception:
        return None, size
    if len(blob_bytes) != size:
        return None, size
    try:
        pcm = encryption.decrypt_audio_file(blob_bytes, uid) if ext in ('batch.enc', 'enc') else blob_bytes
    except Exception:
        return None, size
    if len(pcm) % 2:
        return None, size
    if 'raw_capture_rate' in chunk and chunk['raw_capture_rate'] != sample_rate:
        # Framed projections store native PCM. Compare a whole-object rendition
        # using the same decoder as raw custody, then select each frame's bounds.
        # Never skip a committed projection just because its rate differs.
        try:
            pcm = decode_capture(
                pcm,
                {'format': 'pcm16le', 'sample_rate': str(chunk['raw_capture_rate']), 'channels': '1'},
                sample_rate,
            )
        except Exception:
            return None, size
    return pcm, size


def _chunk_samples(chunk, sample_rate):
    if 'raw_capture_rate' not in chunk or sample_rate == 16000:
        return chunk['span']['samples']
    offset = chunk['raw_capture_offset_samples']
    rate = chunk['raw_capture_rate']
    return resampled_samples(offset + chunk['raw_capture_samples'], rate, sample_rate) - resampled_samples(
        offset, rate, sample_rate
    )


def _chunk_pcm(pcm, chunk, sample_rate):
    """Select a span only after caching and charging its entire immutable object."""
    if 'raw_capture_rate' in chunk:
        return select_raw_pcm(pcm, chunk, sample_rate)
    else:
        if 'raw_offset_samples' not in chunk:
            return pcm
        offset, count = chunk.get('raw_offset_samples', 0), chunk['span']['samples']
    return pcm[offset * 2 : (offset + count) * 2]


def _span_candidate_offset(chunk: Mapping[str, Any], position: float, sample_rate: int) -> Optional[int]:
    span = chunk.get('span')
    if not isinstance(span, Mapping):
        return None
    rate = span.get('sample_rate')
    start = span.get('start')
    samples = span.get('samples')
    if not (isinstance(rate, int) and not isinstance(rate, bool) and rate > 0 and rate == sample_rate):
        return None
    if not (isinstance(start, (int, float)) and not isinstance(start, bool) and math.isfinite(start)):
        return None
    if not (isinstance(samples, int) and not isinstance(samples, bool) and samples > 0):
        return None
    offset = round((position - float(start)) * sample_rate)
    if offset < 0 or offset >= samples:
        return None
    if abs((float(start) + offset / sample_rate) - position) > 0.5 / sample_rate:
        return None
    return offset


def verify_frame_overlaps(
    uid, conversation_id, pcm, frames, sample_rate, *, bucket, list_chunks, bucket_for, receipt=None
):
    """Fresh bounded proof listing: a rebatched frame cannot replace conflicting committed spans."""
    deadline = time.monotonic() + RECONCILE_MAX_SECONDS
    chunks = list_chunks(uid, conversation_id, timeout=5, deadline=deadline, max_count=10000, include_raw=True)
    decoded = {}
    charged = 0
    offset = 0
    for frame in frames:
        start, end = frame['start'], frame['start'] + frame['samples'] / sample_rate
        for chunk in chunks:
            if receipt and chunk['path'] == receipt['path']:
                continue  # The new receipt is not independent evidence of earlier custody.
            span = chunk.get('span')
            if not span:
                continue  # Spanless sources provide no replay inference, as on the legacy path.
            old_start = span['start']
            capture_rate = chunk.get('raw_capture_rate', span['sample_rate'])
            samples = _chunk_samples(chunk, sample_rate)
            old_end = old_start + samples / (sample_rate if 'raw_capture_rate' in chunk else capture_rate)
            lo, hi = max(start, old_start), min(end, old_end)
            if hi <= lo:
                continue
            if capture_rate != sample_rate and 'raw_capture_rate' not in chunk:
                raise ValueError('framed replay rate cannot be verified')
            key = (chunk.get('bucket'), chunk['path'], chunk.get('generation'))
            if key not in decoded:
                if (
                    len(decoded) >= RECONCILE_MAX_OBJECTS
                    or charged >= RECONCILE_MAX_BYTES
                    or time.monotonic() >= deadline
                ):
                    raise TimeoutError('framed replay proof budget exhausted')
                source = bucket_for(chunk.get('bucket')) if chunk.get('bucket') else bucket
                data, size = _raw_chunk_object_pcm(
                    source, chunk, uid, deadline, RECONCILE_MAX_BYTES - charged, sample_rate
                )
                charged += size
                if data is None:
                    raise ValueError('framed replay source cannot be verified')
                decoded[key] = data
            data = _chunk_pcm(decoded[key], chunk, sample_rate)
            if len(data) != samples * 2:
                raise ValueError('framed replay source cannot be verified')
            left = round((lo - old_start) * sample_rate) * 2
            right = offset + round((lo - start) * sample_rate) * 2
            count = round((hi - lo) * sample_rate) * 2
            if time.monotonic() >= deadline:
                raise TimeoutError('framed replay proof budget exhausted')
            if data[left : left + count] != pcm[right : right + count]:
                raise AudioChunkContentConflict('framed replay conflicts with committed PCM')
        offset += frame['samples'] * 2


def frame_overlap_verifier(uid, conversation_id, sample_rate, bucket, list_chunks, bucket_for):
    return partial(
        verify_frame_overlaps,
        uid,
        conversation_id,
        sample_rate=sample_rate,
        bucket=bucket,
        list_chunks=list_chunks,
        bucket_for=bucket_for,
    )


def reconcile_committed_prefix(
    uid: str,
    conversation_id: str,
    timestamp: float,
    data: bytes,
    sample_rate: int,
    *,
    require_spans: bool = False,
    bucket: Any,
    list_chunks: Callable[..., List[Dict[str, Any]]],
    bucket_for: Optional[Callable[[Optional[str]], Any]] = None,
) -> Tuple[int, List[str]]:
    """Count how many leading bytes of ``data`` are provably committed already.

    ``bucket_for`` resolves a listed entry's ``bucket`` key (absent = ``bucket``),
    so a generation listed from the regional chunk bucket is read there.

    ``timestamp`` is the sender's original wire timestamp for ``data[0]``.
    Returns ``(verified_prefix_bytes, committed_paths)``. A verified prefix is
    bounded identity — the same anchor plus a byte-equal payload — not a
    global producer id: zero proof is never permission to discard, and it
    says nothing about bytes beyond what was compared.

    With ``require_spans`` the proof chain uses each object's authoritative
    span (start + samples + rate) on the half-open sample grid: adjacent
    committed spans are reconciled across rebatching while every overlapping
    PCM byte is compared. Legacy spanless storage carries zero replay
    inference: ``require_spans=False`` returns ``(0, [])`` before any
    listing or download, and the caller streams the payload verbatim exactly
    like the literal main uploader.

    Bounds: the listing is a single bounded full inventory (SDK timeout plus
    caller deadline, at most 10,000 entries — a larger inventory raises and
    proves nothing). At most 64 objects totaling 64 MiB of declared object
    bytes are downloaded within 10 seconds; any oversize candidate rejects
    before download so the byte cap is never exceeded. Transient listing or
    download failure also proves nothing — zero proof keeps the retained
    envelope for a verbatim resend. Reconciliation is not a commit ACK: on
    the negotiated span path, unavailable proof can still cause a collision
    or a duplicate store; spanless callers never reach this branch.
    """
    if not require_spans:
        return 0, []
    if not data or sample_rate <= 0:
        return 0, []
    try:
        position = float(timestamp)
    except (TypeError, ValueError):
        return 0, []
    if not math.isfinite(position):
        return 0, []
    deadline = time.monotonic() + RECONCILE_MAX_SECONDS
    try:
        remaining = deadline - time.monotonic()
        chunks = list_chunks(
            uid,
            conversation_id,
            timeout=min(5.0, max(0.001, remaining)),
            deadline=deadline,
            max_count=10000,
        )
    except Exception:
        return 0, []

    verified = 0
    paths: List[str] = []
    downloads = 0
    bytes_seen = 0
    while verified < len(data):
        if time.monotonic() >= deadline or downloads >= RECONCILE_MAX_OBJECTS or bytes_seen >= RECONCILE_MAX_BYTES:
            break
        candidates = []
        for c in chunks:
            offset = _span_candidate_offset(c, position, sample_rate)
            if offset is not None:
                candidates.append((c, offset))
        if len(candidates) != 1:
            break
        chunk, offset_samples = candidates[0]
        source = bucket_for(chunk.get('bucket')) if bucket_for is not None and chunk.get('bucket') else bucket
        pcm, charged = _raw_chunk_object_pcm(
            source, chunk, uid, deadline, RECONCILE_MAX_BYTES - bytes_seen, sample_rate
        )
        downloads += 1
        bytes_seen += charged
        if pcm is None or bytes_seen > RECONCILE_MAX_BYTES:
            break
        pcm = _chunk_pcm(pcm, chunk, sample_rate)
        if len(pcm) != chunk['span']['samples'] * 2:
            break
        comparable = pcm[offset_samples * 2 :]
        available = min(len(comparable), len(data) - verified)
        if available <= 0 or comparable[:available] != data[verified : verified + available]:
            break
        verified += available
        paths.append(chunk['path'])
        position += available / (sample_rate * 2)
    return verified, paths

"""Bounded verification of an audio payload's already-committed storage prefix.

Pure helpers only: all storage I/O arrives through the keyword-only ``bucket``
and ``list_chunks`` seams so this module never imports ``storage`` itself.
"""

import math
import time
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from database.audio_timeline import get_extension_for_path
from utils import encryption

RECONCILE_MAX_OBJECTS = 64
RECONCILE_MAX_BYTES = 64 * 1024 * 1024
RECONCILE_MAX_SECONDS = 10.0
RECONCILE_MAX_ATTEMPTS = 3


def _listed_generation(chunk: Mapping[str, Any]) -> Optional[int]:
    generation = chunk.get('generation')
    if not isinstance(generation, int) or isinstance(generation, bool) or generation <= 0:
        return None
    return generation


def _raw_chunk_object_pcm(
    bucket: Any, chunk: Mapping[str, Any], uid: str, deadline: float, max_bytes: int
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
    if ext not in ('batch.bin', 'batch.enc', 'bin', 'enc'):
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
    return pcm, size


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
) -> Tuple[int, List[str]]:
    """Count how many leading bytes of ``data`` are provably committed already.

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
        pcm, charged = _raw_chunk_object_pcm(bucket, chunk, uid, deadline, RECONCILE_MAX_BYTES - bytes_seen)
        downloads += 1
        bytes_seen += charged
        if pcm is None or bytes_seen > RECONCILE_MAX_BYTES:
            break
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

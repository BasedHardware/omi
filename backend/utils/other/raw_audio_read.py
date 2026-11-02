"""Require complete, verified raw coverage before retiring any PCM write."""

import hashlib
import threading
import time
from bisect import bisect_right
from database.audio_timeline import chunk_span, span_valid

from utils import encryption
from utils.other.raw_audio import decode_capture

_index_lock = threading.Lock()
_indexes: dict[tuple, tuple[float, list]] = {}
# Pack writes invalidate their conversation's entry proactively
# (invalidate_pack_index), so the TTL only bounds cross-instance staleness,
# and staleness always fails safe: a missing pack keeps the PCM write (proof
# path) or falls back to PCM (read path). 120 s amortizes the per-read-session
# list over the ~6-60 s flush cadence instead of listing once per flush.
_INDEX_TTL = 120
_MAX_INDEXES = 128


def invalidate_pack_index(bucket, uid: str, conversation_id: str):
    with _index_lock:
        _indexes.pop((getattr(bucket, 'name', ''), uid, conversation_id), None)


def list_packs(bucket, uid: str, conversation_id: str):
    key = (getattr(bucket, 'name', ''), uid, conversation_id)
    with _index_lock:
        cached = _indexes.get(key)
        if cached and cached[0] > time.monotonic():
            return cached[1]
    packs = []
    for index, blob in enumerate(
        bucket.list_blobs(prefix=f'raw-live/{uid}/{conversation_id}/', timeout=10, retry=None)
    ):
        if index >= 10000:
            raise TimeoutError('raw capture index budget exhausted')
        metadata = blob.metadata or {}
        if metadata.get('clock_source') == 'arrival_estimate':
            # Legacy pusher clocks cannot position independent raw packs on a
            # capture timeline. Keep them recoverable by immutable receipt;
            # ordinary playback uses the legacy continuous PCM projection.
            continue
        try:
            start, end = float(metadata['capture_start']), float(metadata['capture_end'])
            if int(metadata['gap_count']) != 0 or end <= start or int(metadata['channels']) != 1:
                continue
            if metadata['codec'] not in {'opus', 'flac', 'pcm16', 'pcm8'}:
                continue
            if metadata.get('source_layout', 'mono') != 'mono':
                continue
            packs.append(
                {
                    'timestamp': start,
                    'path': blob.name,
                    'size': blob.size,
                    'is_batch': False,
                    'span': {'start': start, 'samples': round((end - start) * 16000), 'sample_rate': 16000},
                    'raw_end': end,
                    'generation': getattr(blob, 'generation', None),
                    'pcm_sha256': metadata.get('pcm_sha256'),
                }
            )
        except (KeyError, ValueError, TypeError):
            continue
    result = sorted(packs, key=lambda item: item['timestamp'])
    with _index_lock:
        if len(_indexes) >= _MAX_INDEXES:
            _indexes.pop(next(iter(_indexes)))
        _indexes[key] = (time.monotonic() + _INDEX_TTL, result)
    return result


def read_pack(bucket, path: str, uid: str, download_kwargs=None, sample_rate: int = 16000) -> bytes:
    download_kwargs = {'timeout': 10, 'retry': None, **(download_kwargs or {})}
    blob = bucket.blob(path)
    blob.reload(**(download_kwargs or {}))
    metadata = blob.metadata or {}
    raw = blob.download_as_bytes(**(download_kwargs or {}))
    if metadata.get('encrypted') == 'true':
        raw = encryption.decrypt_audio_file(raw, uid)
    if hashlib.sha256(raw).hexdigest() != metadata.get('sha256'):
        raise ValueError('capture checksum mismatch')
    pcm = decode_capture(raw, metadata, sample_rate)
    expected = round((float(metadata['capture_end']) - float(metadata['capture_start'])) * sample_rate) * 2
    if abs(len(pcm) - expected) > 2:
        raise ValueError('capture sample coverage mismatch')
    return pcm


def verified_pcm_paths(bucket, uid: str, conversation_id: str, chunks, sample_rate):
    """Only skip a write with full committed coverage and a capture-PCM identity proof."""
    if sample_rate != 16000:
        return None
    packs = list_packs(bucket, uid, conversation_id)
    verified = []
    decoded = {}
    for chunk in chunks:
        span = chunk.get('span') or {}
        if span.get('sample_rate') != 16000:
            return None
        start = float(chunk['timestamp'])
        payload = chunk['data']
        end = start + len(payload) / 32000
        pack = next(
            (item for item in packs if item['timestamp'] <= start + 0.0001 and item['raw_end'] >= end - 0.0001), None
        )
        if pack is None:
            return None
        path = pack['path']
        if path not in decoded:
            decoded[path] = read_pack(bucket, path, uid)
        offset = round((start - pack['timestamp']) * 16000) * 2
        whole_pack_proof = (
            offset == 0
            and len(payload) == len(decoded[path])
            and pack.get('pcm_sha256') == hashlib.sha256(payload).hexdigest()
        )
        if not whole_pack_proof and decoded[path][offset : offset + len(payload)] != payload:
            return None
        if path not in verified:
            verified.append(path)
    return verified


def pcm_for_span(bucket, uid: str, conversation_id: str, span, *, expected_sha256: str | None = None):
    if not span or span['sample_rate'] != 16000 or not expected_sha256:
        return None
    start = float(span['start'])
    count = int(span['samples']) * 2
    for pack in list_packs(bucket, uid, conversation_id):
        if pack['timestamp'] <= start + 0.0001 and pack['raw_end'] >= start + count / 32000 - 0.0001:
            pcm = read_pack(bucket, pack['path'], uid)
            offset = round((start - pack['timestamp']) * 16000) * 2
            selected = pcm[offset : offset + count]
            if len(selected) == count and hashlib.sha256(selected).hexdigest() == expected_sha256:
                return selected
    return None


def uncovered_raw_packs(packs: list[dict], chunks: list[dict]) -> list[dict]:
    """Project only uncovered raw intervals; never infer coverage from blob size."""
    covered: list[tuple[int, int]] = []
    unknown = []
    for item in chunks:
        span = chunk_span(item)
        if span and span_valid(span['start'], span['start'] + span['samples'] / span['sample_rate']):
            covered.append(
                (round(span['start'] * 16000), round((span['start'] + span['samples'] / span['sample_rate']) * 16000))
            )
        else:
            unknown.append(item['timestamp'])
    union: list[tuple[int, int]] = []
    for start, end in sorted(covered):
        if union and start <= union[-1][1]:
            union[-1] = (union[-1][0], max(union[-1][1], end))
        else:
            union.append((start, end))
    ends = [end for _, end in union]
    result = []
    raw_cursor = None
    for pack in packs:
        # Keep historical selection for spanless legacy entries: their encoded
        # size is not proof of sample coverage.
        if any(pack['timestamp'] <= stamp < pack['raw_end'] for stamp in unknown):
            continue
        original_start = round(pack['timestamp'] * 16000)
        original_end = original_start + pack['span']['samples']
        cursor = max(original_start, raw_cursor) if raw_cursor is not None else original_start
        remaining = []
        index = bisect_right(ends, cursor)
        while index < len(union) and union[index][0] < original_end and cursor < original_end:
            lo, hi = union[index]
            if lo > cursor:
                remaining.append((cursor, min(lo, original_end)))
            cursor = max(cursor, hi)
            index += 1
        if cursor < original_end:
            remaining.append((cursor, original_end))
        raw_cursor = max(raw_cursor or original_end, original_end)
        for start, end in remaining:
            item = dict(pack)
            if start != original_start or end != original_end:
                item.update(
                    timestamp=start / 16000,
                    raw_end=end / 16000,
                    raw_source_start=pack['timestamp'],
                    span={'start': start / 16000, 'samples': end - start, 'sample_rate': 16000},
                )
            result.append(item)
    return result


def select_raw_pcm(pcm: bytes, chunk: dict, sample_rate: int) -> bytes:
    """A listing fragment selects exact samples from the unchanged source pack."""
    if 'raw_source_start' not in chunk:
        return pcm
    span = chunk['span']
    offset = round((chunk['timestamp'] - chunk['raw_source_start']) * sample_rate) * 2
    count = round(span['samples'] * sample_rate / span['sample_rate']) * 2
    selected = pcm[offset : offset + count]
    if len(selected) != count:
        raise ValueError('raw playback fragment has incomplete sample coverage')
    return selected

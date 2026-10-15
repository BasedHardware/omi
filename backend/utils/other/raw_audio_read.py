"""Require complete, verified raw coverage before retiring any PCM write."""

import hashlib
import threading
import time

from utils import encryption
from utils.other.raw_audio import decode_capture

_index_lock = threading.Lock()
_indexes: dict[tuple, tuple[float, list]] = {}
_INDEX_TTL = 5
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
        try:
            start, end = float(metadata['capture_start']), float(metadata['capture_end'])
            if int(metadata['gap_count']) != 0 or end <= start or int(metadata['channels']) != 1:
                continue
            if metadata['codec'] not in {'opus', 'flac'}:
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


def pcm_for_span(bucket, uid: str, conversation_id: str, span):
    if not span or span['sample_rate'] != 16000:
        return None
    start = float(span['start'])
    count = int(span['samples']) * 2
    for pack in list_packs(bucket, uid, conversation_id):
        if pack['timestamp'] <= start + 0.0001 and pack['raw_end'] >= start + count / 32000 - 0.0001:
            pcm = read_pack(bucket, pack['path'], uid)
            offset = round((start - pack['timestamp']) * 16000) * 2
            selected = pcm[offset : offset + count]
            if len(selected) == count:
                return selected
    return None

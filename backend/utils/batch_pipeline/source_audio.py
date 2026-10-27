"""Authenticated reference manifests over retained audio; never copies canonical audio.

Pure decoding shared by the CPU admission coordinator and the GPU artifact reader.
Every source is owner/conversation scoped and pinned to a GCS generation. The
batch retention outbox owns only the small manifest, never the retained source.
"""

import audioop
import hashlib
import json
import struct
from typing import Callable

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from utils.batch_pipeline.audio import audio_unit, with_context
from utils.batch_pipeline import leaf_timings
from utils.other.raw_audio import decode_capture

MAGIC = b'OMIRECORD1\n'
MAX_SOURCE_BYTES = 256 * 1024 * 1024
MAX_REFERENCES = 4096


def decode_source(raw: bytes, ref: dict, owner_key: bytes) -> bytes:
    if not raw or len(raw) > MAX_SOURCE_BYTES:
        raise ValueError('invalid retained audio size')
    metadata = ref.get('metadata') or {}
    path = ref['path']
    encrypted = path.endswith('.enc') or metadata.get('encrypted') == 'true'
    if encrypted:
        decoded, offset = bytearray(), 0
        aes = AESGCM(owner_key)
        with leaf_timings.measure('decrypt'):
            while offset < len(raw):
                if offset + 4 > len(raw):
                    raise ValueError('truncated encrypted audio length')
                size = struct.unpack_from('>I', raw, offset)[0]
                offset += 4
                if not 28 <= size <= MAX_SOURCE_BYTES or offset + size > len(raw):
                    raise ValueError('invalid encrypted audio frame')
                decoded.extend(aes.decrypt(raw[offset : offset + 12], raw[offset + 12 : offset + size], None))
                offset += size
        raw = bytes(decoded)
    if path.startswith('raw-live/'):
        if hashlib.sha256(raw).hexdigest() != metadata.get('sha256'):
            raise ValueError('retained capture checksum mismatch')
        return leaf_timings.call('decode', decode_capture, raw, metadata, 16000)
    if '.opus' in path:
        # Existing legacy chunk codec, shared with playback. Import is lazy in
        # the codec binding; no storage/database/provider SDK is constructed.
        from utils.other.audio_opus import decode_opus_to_pcm

        return leaf_timings.call('decode', decode_opus_to_pcm, raw, sample_rate=16000)
    rate = int(ref.get('sample_rate', 16000))
    if len(raw) % 2 or not 8000 <= rate <= 48000:
        raise ValueError('invalid retained PCM')
    return leaf_timings.call('decode', audioop.ratecv, raw, 2, 1, rate, 16000, None)[0] if rate != 16000 else raw


def validate_reference(ref: dict, uid: str, conversation_id: str, allowed_buckets: set[str]) -> None:
    path = ref.get('path', '')
    if (
        ref.get('bucket') not in allowed_buckets
        or not path.startswith((f'chunks/{uid}/{conversation_id}/', f'raw-live/{uid}/{conversation_id}/'))
        or any(part in {'.', '..'} for part in path.split('/'))
        or not str(ref.get('generation', '')).isdigit()
        or int(ref['generation']) <= 0
    ):
        raise ValueError('retained audio reference is outside admitted source')


def read_reference(client, ref: dict, uid: str, conversation_id: str, allowed_buckets: set[str], key: bytes) -> bytes:
    validate_reference(ref, uid, conversation_id, allowed_buckets)
    generation = int(ref['generation'])
    blob = client.bucket(ref['bucket']).blob(ref['path'], generation=generation)
    leaf_timings.call('download_metadata', blob.reload, if_generation_match=generation, timeout=30, retry=None)
    if not blob.size or not 0 < blob.size <= MAX_SOURCE_BYTES:
        raise ValueError('retained audio source exceeds size budget')
    raw = leaf_timings.call('download', blob.download_as_bytes, if_generation_match=generation, timeout=60, retry=None)
    return decode_source(raw, ref, key)


def materialize(body: bytes, item, fetch: Callable[[dict], bytes]) -> bytes:
    manifest = json.loads(body[len(MAGIC) :])
    if (
        manifest.get('owner_id') != item.owner_id
        or manifest.get('conversation_id') != item.conversation_id
        or manifest.get('capture_at') != item.capture_at
        or not 1 <= len(manifest.get('references', [])) <= MAX_REFERENCES
    ):
        raise ValueError('retained audio manifest binding mismatch')
    pcm = bytearray(round(item.duration_seconds * 16000) * 2)
    previous = 0
    for ref in manifest['references']:
        source = fetch(ref)
        if hashlib.sha256(source).hexdigest() != ref['pcm_sha256']:
            raise ValueError('retained PCM digest changed')
        start, offset, frames = ref['start_frame'], ref['offset_frame'], ref['frames']
        if any(type(v) is not int for v in (start, offset, frames)) or start < previous or offset < 0 or frames <= 0:
            raise ValueError('invalid retained audio slice')
        if (offset + frames) * 2 > len(source) or (start + frames) * 2 > len(pcm):
            raise ValueError('retained audio slice exceeds capture')
        pcm[start * 2 : (start + frames) * 2] = source[offset * 2 : (offset + frames) * 2]
        previous = start + frames
    return with_context(audio_unit(item.capture_at, bytes(pcm)).wav, manifest['context'])

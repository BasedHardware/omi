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
from utils.batch_pipeline import leaf_timings, record_seal_profile
from utils.other.audio_frame_table import FRAME_SCHEMA, gapped_frames
from utils.other.raw_audio import WAL_FORMAT, decode_capture, decode_capture_frames

MAGIC = b'OMIRECORD1\n'
MAX_SOURCE_BYTES = 256 * 1024 * 1024
MAX_REFERENCES = 4096


def batch_timing_store(references: list[dict]) -> str | None:
    """Only homogeneous live PCM custody references prove the batch clock."""
    if references and all(str(ref.get('path') or '').endswith(('.batch.enc', '.batch.bin')) for ref in references):
        return 'batch'
    return None


class InvalidRetainedManifest(ValueError):
    """The stored manifest itself can never materialize; a retry reads the same bytes."""


def decode_source(raw: bytes, ref: dict, owner_key: bytes, *, frames: list[dict] | None = None) -> bytes:
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
        if frames is not None and metadata.get('format') == WAL_FORMAT:
            # A gapped pack's retained zero-sample frames are not decodable
            # packets; walking the writer's own frame table keeps every sample
            # at its capture position instead of failing on the diagnostic row.
            return leaf_timings.call('decode', decode_capture_frames, raw, metadata, frames, 16000)
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
    if ref.get('bucket') not in allowed_buckets:
        # The allowed set is deploy configuration, not the manifest: stay retryable.
        raise ValueError('retained audio reference is outside admitted source')
    path = ref.get('path', '')
    if (
        not isinstance(path, str)
        or not path.startswith((f'chunks/{uid}/{conversation_id}/', f'raw-live/{uid}/{conversation_id}/'))
        or any(part in {'.', '..'} for part in path.split('/'))
        or not str(ref.get('generation', '')).isdigit()
        or int(ref['generation']) <= 0
    ):
        raise InvalidRetainedManifest('retained audio reference is outside admitted source')


def read_reference(
    client,
    ref: dict,
    uid: str,
    conversation_id: str,
    allowed_buckets: set[str],
    key: bytes,
    *,
    source_metadata=False,
    read_budget=None,
    listed_source=None,
    frames=None,
) -> bytes:
    validate_reference(ref, uid, conversation_id, allowed_buckets)
    generation = int(ref['generation'])
    blob = client.bucket(ref['bucket']).blob(ref['path'], generation=generation)
    if read_budget is not None:
        read_budget.begin()
    # Data generation alone does not fence metadata-only updates (sample rate,
    # encryption/checksum metadata). Only a versioned listing can replace the GET.
    listed = listed_source or {}
    size = listed.get('size')
    metageneration = listed.get('metageneration')
    use_listing = (
        size is not None
        and (not source_metadata or 'metadata' in listed)
        and type(metageneration) is int
        and metageneration > 0
    )
    if not use_listing:
        record_seal_profile.metadata_reload()
        leaf_timings.call(
            'download_metadata',
            blob.reload,
            if_generation_match=generation,
            timeout=read_budget.timeout(30) if read_budget is not None else 30,
            retry=None,
        )
        size = blob.size
        metadata = (blob.metadata or {}) if source_metadata else {}
    else:
        metadata = listed.get('metadata') or {}
    if source_metadata:
        ref['metadata'] = metadata
        if 'sample_rate' not in ref:
            ref['sample_rate'] = int(metadata.get('record_sample_rate', 16000))
    if not size or not 0 < size <= MAX_SOURCE_BYTES:
        raise ValueError('retained audio source exceeds size budget')
    if read_budget is not None:
        read_budget.reserve(size)
    raw = leaf_timings.call(
        'download',
        blob.download_as_bytes,
        if_generation_match=generation,
        **({'if_metageneration_match': metageneration} if use_listing else {}),
        timeout=read_budget.timeout(60) if read_budget is not None else 60,
        retry=None,
    )
    record_seal_profile.received(len(raw))
    if read_budget is not None:
        read_budget.received_bytes += len(raw)
        read_budget.timeout(60)
    if frames is None and ref['path'].startswith('raw-live/') and metadata:
        # A gapped, unframed omi-wal pack has no declared frame schema, so the
        # ordinary decoder would try to decode its retained zero-sample
        # diagnostic rows. Resolve the writer's own frame table and decode
        # through it. A gapped flac/pcm16 pack encodes the captured PCM
        # contiguously, so the ordinary decoder already returns its samples.
        if (
            metadata.get('format') == WAL_FORMAT
            and metadata.get('frame_schema') != FRAME_SCHEMA
            and int(metadata.get('gap_count') or 0) != 0
        ):
            frames, _ = gapped_frames(client.bucket(ref['bucket']), blob, uid, metadata=metadata)
    return decode_source(raw, ref, key, frames=frames)


def _well_formed(ref: dict) -> bool:
    return isinstance(ref.get('pcm_sha256'), str) and isinstance(ref.get('path', ''), str)


def materialize(body: bytes, item, fetch: Callable[[dict], bytes]) -> bytes:
    try:
        manifest = json.loads(body[len(MAGIC) :])
    except ValueError:
        raise InvalidRetainedManifest('retained audio manifest is not JSON') from None
    references = manifest.get('references') if isinstance(manifest, dict) else None
    if (
        not isinstance(references, list)
        or not isinstance(manifest.get('context'), dict)
        or not all(isinstance(ref, dict) and _well_formed(ref) for ref in references)
    ):
        raise InvalidRetainedManifest('malformed retained audio manifest')
    if (
        manifest.get('owner_id') != item.owner_id
        or manifest.get('conversation_id') != item.conversation_id
        or manifest.get('capture_at') != item.capture_at
        or not 1 <= len(references) <= MAX_REFERENCES
    ):
        raise InvalidRetainedManifest('retained audio manifest binding mismatch')
    pcm = bytearray(round(item.duration_seconds * 16000) * 2)
    previous = 0
    previous_key, previous_source = None, b''
    for ref in references:
        source_key = tuple(ref.get(name) for name in ('bucket', 'path', 'generation', 'pcm_sha256'))
        pinned = all(value is not None for value in source_key)
        if pinned and source_key == previous_key:
            source = previous_source
        else:
            source = fetch(ref)
            if hashlib.sha256(source).hexdigest() != ref['pcm_sha256']:
                raise ValueError('retained PCM digest changed')
            previous_key, previous_source = source_key if pinned else None, source
        start, offset, frames = ref.get('start_frame'), ref.get('offset_frame'), ref.get('frames')
        if any(type(v) is not int for v in (start, offset, frames)) or start < previous or offset < 0 or frames <= 0:
            raise InvalidRetainedManifest('invalid retained audio slice')
        if (offset + frames) * 2 > len(source) or (start + frames) * 2 > len(pcm):
            raise InvalidRetainedManifest('retained audio slice exceeds capture')
        pcm[start * 2 : (start + frames) * 2] = source[offset * 2 : (offset + frames) * 2]
        previous = start + frames
    return with_context(audio_unit(item.capture_at, bytes(pcm)).wav, manifest['context'])

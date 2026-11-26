"""Frame positions for immutable custody media and its PCM projections.

One object may contain disjoint capture spans. Sample offsets refer to captured
PCM concatenation, never elapsed wall time. A media upload alone is not proof.
"""

import hashlib
import json
import math
import os
import threading
import time
from types import SimpleNamespace
from typing import Any

from cachetools import TTLCache
from google.api_core.exceptions import NotFound, PreconditionFailed

from config.record_wal_storage import private_archive_bucket
from utils import encryption
from config.refactor_modes import default_on
from utils.other.gcs_read_reuse import REPLACEMENT_CALLS, avoided
from utils.pusher_audio_window import AUDIO_TIMELINE_CONTINUITY_TOLERANCE

FRAME_SCHEMA = 'audio_frames_v1'
MAX_FRAMES = 4096
MAX_MANIFEST_BYTES = 4 * 1024 * 1024


def _inventory_body_size(body: bytes) -> int:
    return len(body) + 256  # Charge an entry as well as its encoded body.


_inventory_bodies = TTLCache(maxsize=8 * 1024 * 1024, ttl=120, getsizeof=_inventory_body_size)
_inventory_lock = threading.Lock()


def validate_frames(frames: list[dict], sample_rate: int, *, allow_empty: bool = False) -> int:
    """Validate a frame table; ``allow_empty`` admits retained zero-sample frames.

    A pack whose writer did not declare ``frame_schema`` may still carry a
    custody manifest. Its frames can include zero-sample rows: the producer
    retained an undecodable packet as a diagnostic, and the writer counted it
    as a gap. Those rows carry no audio and contribute no samples.
    """
    if not frames or len(frames) > MAX_FRAMES or sample_rate <= 0:
        raise ValueError('invalid capture frame table')
    total = 0
    previous_sequence = None
    previous_end = None
    for frame in frames:
        start, samples = frame['start'], frame['samples']
        sequence = frame['sequence']
        if (
            not isinstance(start, (int, float))
            or isinstance(start, bool)
            or not math.isfinite(start)
            or not isinstance(samples, int)
            or isinstance(samples, bool)
            or samples < 0
            or (samples == 0 and not allow_empty)
            or not isinstance(sequence, int)
            or isinstance(sequence, bool)
            or (previous_sequence is not None and sequence <= previous_sequence)
            or not isinstance(frame['gap_before'], bool)
        ):
            raise ValueError('invalid capture frame')
        if previous_end is not None and start - previous_end < -AUDIO_TIMELINE_CONTINUITY_TOLERANCE:
            raise ValueError('capture frames overlap')
        if previous_end is not None and frame['gap_before'] != (abs(start - previous_end) > 0.002):
            raise ValueError('capture gap marker differs from frame positions')
        previous_sequence = sequence
        previous_end = start + samples / sample_rate
        total += samples
    return total


def io_timeout(deadline=None, maximum=10):
    remaining = maximum if deadline is None else min(maximum, deadline - time.monotonic())
    if remaining <= 0:
        raise TimeoutError('capture proof deadline exhausted')
    return remaining


def resampled_samples(samples: int, rate: int, output_rate: int = 16000) -> int:
    """Length of audioop's whole-stream rendition, including its first sample."""
    return ((samples - 1) * output_rate // rate + 1) if samples else 0


def _listed_manifest_bytes(
    blob, listed, deadline, *, partition: tuple[str, str], reuse_inventory_body=False, memo=None
):
    """Use listing metadata only when the current object still matches both versions."""
    if (
        listed is None
        or listed.name != blob.name
        or os.getenv('PRIVATE_SYNC_LISTED_MANIFEST_READ_ENABLED', 'true').strip().lower() == 'false'
    ):
        return None
    generation = listed.generation
    metageneration = getattr(listed, 'metageneration', None)
    size = listed.size
    metadata = listed.metadata or {}
    checksum = metadata.get('sha256')
    encrypted = metadata.get('encrypted')
    if (
        type(generation) is not int
        or generation <= 0
        or type(metageneration) is not int
        or metageneration <= 0
        or type(size) is not int
        or not 0 <= size <= MAX_MANIFEST_BYTES
        or not isinstance(checksum, str)
        or not checksum
        or encrypted not in ('true', 'false')
    ):
        return None
    cache_key = None
    cached_body = None
    if reuse_inventory_body:
        cache_key = (*partition, blob.name, generation, metageneration, checksum, encrypted)
        with _inventory_lock:
            cached_body = _inventory_bodies.get(cache_key)
    memo_key = None
    memo_hit = False
    if memo is not None and default_on('PRIVATE_SYNC_REQUEST_READ_MEMO_ENABLED') and not reuse_inventory_body:
        memo_key = ('manifest', *partition, blob.name, generation, metageneration, checksum)
        cached_body = memo.get(memo_key)
        memo_hit = cached_body is not None
    try:
        if cached_body is not None:
            # Read the live object's metadata without selecting an older generation.
            blob.reload(
                if_generation_match=generation,
                if_metageneration_match=metageneration,
                timeout=io_timeout(deadline),
                retry=None,
            )
            if memo_hit:
                avoided('manifest_memo', 'payload', payload_bytes=len(cached_body))
                REPLACEMENT_CALLS.labels('manifest_memo', 'metadata').inc()
            return cached_body, metadata, None, memo_key
        raw = blob.download_as_bytes(
            if_generation_match=generation,
            if_metageneration_match=metageneration,
            timeout=io_timeout(deadline),
            retry=None,
        )
    except PreconditionFailed:
        # The listing lost a race. Re-read current metadata through the ordinary path.
        return None
    return raw, metadata, cache_key, memo_key


def _manifest(
    bucket,
    uid: str,
    path: str,
    generation=None,
    digest=None,
    *,
    deadline=None,
    require_frame_schema=True,
    listed=None,
    reuse_inventory_body=False,
    memo=None,
    require_listed=False,
) -> dict:
    if not path.startswith(f'audio-outbox/{uid}/'):
        raise ValueError('frame manifest owner mismatch')
    blob = bucket.blob(path, generation=int(generation)) if generation else bucket.blob(path)
    # Avoid a generation in the URL for this path. Preconditions apply to the
    # current object, so an overwritten older version cannot satisfy the listing proof.
    observed = (
        _listed_manifest_bytes(
            blob,
            listed,
            deadline,
            partition=(bucket.name, uid),
            reuse_inventory_body=reuse_inventory_body,
            memo=memo,
        )
        if not generation and bucket.name == private_archive_bucket()
        else None
    )
    cache_key = None
    memo_key = None
    if observed is None:
        if require_listed:
            raise PreconditionFailed('known manifest no longer matches the listing')
        blob.reload(timeout=io_timeout(deadline), retry=None)
        pinned = int(generation or blob.generation)
        if pinned <= 0:
            raise ValueError('frame manifest requires generation')
        if blob.size is None or blob.size > MAX_MANIFEST_BYTES:
            raise ValueError('frame manifest exceeds read bound')
        manifest_metadata = blob.metadata or {}
        metageneration = getattr(blob, 'metageneration', None)
        checksum = digest or manifest_metadata.get('sha256')
        download_kwargs = {'if_generation_match': pinned, 'timeout': io_timeout(deadline), 'retry': None}
        encoded = None
        if (
            listed is None
            and memo is not None
            and default_on('PRIVATE_SYNC_REQUEST_READ_MEMO_ENABLED')
            and (type(metageneration) is int and metageneration > 0 and isinstance(checksum, str) and checksum)
        ):
            memo_key = ('manifest', bucket.name, uid, path, pinned, metageneration, checksum)
            download_kwargs['if_metageneration_match'] = metageneration
            encoded = memo.get(memo_key)
            if encoded is not None:
                avoided('manifest_memo', 'payload', payload_bytes=len(encoded))
        if encoded is None:
            try:
                encoded = blob.download_as_bytes(**download_kwargs)
            except PreconditionFailed:
                if memo_key is None:
                    raise
                REPLACEMENT_CALLS.labels('manifest_memo', 'payload').inc()
                # Restart from live metadata using the ordinary verified read.
                return _manifest(
                    bucket, uid, path, generation, digest, deadline=deadline, require_frame_schema=require_frame_schema
                )
    else:
        encoded, manifest_metadata, cache_key, memo_key = observed
    raw = encoded
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError('frame manifest exceeds read bound')
    if manifest_metadata.get('encrypted') == 'true':
        raw = encryption.decrypt_audio_file(raw, uid)
    if hashlib.sha256(raw).hexdigest() != (digest or manifest_metadata.get('sha256')):
        raise ValueError('frame manifest checksum mismatch')
    manifest = json.loads(raw)
    if manifest['schema'] != 'audio_custody_v1':
        raise ValueError('unknown capture frame schema')
    if require_frame_schema:
        if manifest['capture'].get('frame_schema') != FRAME_SCHEMA:
            raise ValueError('unknown capture frame schema')
        validate_frames(manifest['frames'], int(manifest['capture']['sample_rate']))
    else:
        validate_frames(manifest['frames'], int(manifest['capture']['sample_rate']), allow_empty=True)
    if memo is not None and memo_key is not None:
        memo.put(memo_key, encoded, len(encoded))
    if cache_key is not None:
        with _inventory_lock:
            _inventory_bodies[cache_key] = encoded
    return manifest


def committed_frames(bucket, blob, uid: str, *, deadline=None, memo=None) -> tuple[list[dict], int]:
    metadata = blob.metadata or {}
    manifest = _manifest(bucket, uid, metadata['custody_manifest_path'], deadline=deadline, memo=memo)
    if manifest['media'] != {
        'bucket': bucket.name,
        'path': blob.name,
        'generation': str(blob.generation),
        'sha256': metadata['sha256'],
    }:
        raise ValueError('capture frame media mismatch')
    rate = int(manifest['capture']['sample_rate'])
    return manifest['frames'], rate


def unframed_frames(
    bucket,
    blob,
    uid: str,
    manifest_path: str,
    *,
    deadline=None,
    metadata=None,
    listed_manifest=None,
    reuse_inventory_body=False,
    require_listed=False,
    memo=None,
) -> tuple[list[dict], int]:
    """Frame positions for a pack whose writer did not declare a frame schema.

    ``commit_capture`` always writes the custody manifest beside the media, but
    only a framed pack records ``custody_manifest_path`` in the media metadata.
    The manifest is still the writer's own record of where each captured frame
    sits on the capture clock, so it is the only truthful source for a gapped
    pack's internal gap positions.
    """
    metadata = metadata if metadata is not None else (blob.metadata or {})
    manifest = _manifest(
        bucket,
        uid,
        manifest_path,
        deadline=deadline,
        require_frame_schema=False,
        listed=listed_manifest,
        reuse_inventory_body=reuse_inventory_body,
        require_listed=require_listed,
        memo=memo,
    )
    if manifest['media'] != {
        'bucket': bucket.name,
        'path': blob.name,
        'generation': str(blob.generation),
        'sha256': metadata['sha256'],
    }:
        raise ValueError('capture frame media mismatch')
    rate = int(manifest['capture']['sample_rate'])
    return manifest['frames'], rate


def media_name(blob_name: str, uid: str) -> str:
    """The writer's shared name for a raw-live pack and its custody manifest."""
    prefix = f'raw-live/{uid}/'
    if not blob_name.startswith(prefix):
        raise ValueError('capture pack owner mismatch')
    return blob_name[len(prefix) :].rsplit('/', 1)[0]


def _known_manifest_key(memo, bucket, blob, uid):
    if (
        memo is None
        or not default_on('PRIVATE_SYNC_KNOWN_KEY_LIST_REUSE_ENABLED')
        or not default_on('PRIVATE_SYNC_LISTED_MANIFEST_READ_ENABLED')
        or bucket.name != private_archive_bucket()
    ):
        return None
    generation = getattr(blob, 'generation', None)
    metageneration = getattr(blob, 'metageneration', None)
    if type(generation) is int and generation > 0 and type(metageneration) is int and metageneration > 0:
        return ('gapped_manifest', bucket.name, uid, blob.name, generation, metageneration)
    return None


def remember_gapped_manifest(memo, bucket, blob, uid, manifest):
    key = _known_manifest_key(memo, bucket, blob, uid)
    generation = getattr(manifest, 'generation', None)
    metageneration = getattr(manifest, 'metageneration', None)
    if (
        key is not None
        and type(generation) is int
        and generation > 0
        and type(metageneration) is int
        and metageneration > 0
    ):
        # Keep a snapshot of the listing. The live key read must still satisfy
        # both versions and the manifest's digest and media binding.
        candidate = SimpleNamespace(
            name=manifest.name,
            generation=generation,
            metageneration=metageneration,
            size=manifest.size,
            metadata=dict(manifest.metadata or {}),
        )
        memo.put(key, candidate, 10 * 1024)


def gapped_frames(bucket, blob, uid: str, *, deadline=None, metadata=None, memo=None) -> tuple[list[dict], int]:
    """The writer's own frame positions for one gapped, unframed pack.

    ``commit_capture`` names the manifest directory exactly like the media
    directory, so a prefix listing maps a pack to its own manifest. The pack's
    internal gaps require one unambiguous manifest.
    """
    prefix = f'audio-outbox/{uid}/{media_name(blob.name, uid)}/'
    # Uniqueness is established once by this operation's scoped inventory.
    # A key hit checks both live versions and media binding again.
    key = _known_manifest_key(memo, bucket, blob, uid)
    known = memo.get(key) if memo is not None and key is not None else None
    if known is not None:
        try:
            frames = unframed_frames(
                bucket,
                blob,
                uid,
                known.name,
                deadline=deadline,
                metadata=metadata,
                listed_manifest=known,
                require_listed=True,
                memo=memo,
            )
        except (NotFound, PreconditionFailed, ValueError, KeyError):
            REPLACEMENT_CALLS.labels('known_key', 'object_get').inc()
        else:
            avoided('known_key', 'list')
            return frames

    candidates = []
    for index, candidate in enumerate(bucket.list_blobs(prefix=prefix, timeout=io_timeout(deadline), retry=None)):
        io_timeout(deadline)
        if index >= MAX_FRAMES:
            raise TimeoutError('capture manifest listing budget exhausted')
        if (candidate.metadata or {}).get('format') == 'audio-custody-manifest-v1':
            candidates.append(candidate)
            if len(candidates) > 1:
                break
    if len(candidates) != 1:
        raise ValueError('gapped capture has no unique custody manifest')
    manifest = candidates[0]
    frames = unframed_frames(
        bucket, blob, uid, manifest.name, deadline=deadline, metadata=metadata, listed_manifest=manifest, memo=memo
    )
    remember_gapped_manifest(memo, bucket, blob, uid, manifest)
    return frames


def receipt_frames(bucket, uid: str, receipt: dict, *, deadline=None, memo=None) -> tuple[list[dict], int]:
    if receipt['bucket'] != bucket.name or not receipt['path'].startswith(f'raw-live/{uid}/'):
        raise ValueError('frame receipt owner mismatch')
    manifest = _manifest(
        bucket,
        uid,
        receipt['manifest_path'],
        receipt['manifest_generation'],
        receipt['manifest_sha256'],
        deadline=deadline,
        memo=memo,
    )
    if manifest['media'] != {key: receipt[key] for key in ('bucket', 'path', 'generation', 'sha256')}:
        raise ValueError('frame receipt media mismatch')
    rate = int(receipt['sample_rate'])
    if validate_frames(manifest['frames'], rate) != receipt['samples']:
        raise ValueError('frame receipt sample mismatch')
    return manifest['frames'], rate


def entries(frames: list[dict], rate: int, source: dict[str, Any], *, allow_empty: bool = False) -> list[dict]:
    """Walk original frames; coalesce only sample-contiguous rows, retaining every real gap."""
    validate_frames(frames, rate, allow_empty=allow_empty)
    result = []
    offset = 0
    for frame in frames:
        mapped_offset = resampled_samples(offset, rate)
        count = resampled_samples(offset + frame['samples'], rate) - mapped_offset
        if frame['samples'] == 0:
            # A retained zero-sample frame is a diagnostic, not audio. It still
            # advances the capture clock, so the next frame keeps its position.
            continue
        entry = {
            **source,
            'timestamp': frame['start'],
            'raw_end': frame['start'] + frame['samples'] / rate,
            'span': {'start': frame['start'], 'samples': count, 'sample_rate': 16000},
            'raw_offset_samples': mapped_offset,
            'raw_capture_offset_samples': offset,
            'raw_capture_samples': frame['samples'],
            'raw_capture_rate': rate,
            'gap_before': frame['gap_before'],
            'is_batch': False,
        }
        previous = result[-1] if result else None
        expected = previous['raw_end'] if previous else 0.0
        if (
            previous
            and not frame['gap_before']
            and previous['raw_offset_samples'] + previous['span']['samples'] == entry['raw_offset_samples']
            and math.isclose(
                frame['start'], expected, rel_tol=0, abs_tol=2 * max(math.ulp(frame['start']), math.ulp(expected))
            )
        ):
            previous['span']['samples'] += count
            previous['raw_capture_samples'] += frame['samples']
            previous['raw_end'] = entry['raw_end']
        else:
            result.append(entry)
        offset += frame['samples']
    return result


def has_frame_receipt(blob) -> bool:
    """Only actual metadata mappings can declare a framed projection."""
    metadata = getattr(blob, 'metadata', None)
    return isinstance(metadata, dict) and 'framed_receipt' in metadata


def projection_entries(bucket, blob, uid: str, source: dict, *, deadline=None, memo=None) -> list[dict]:
    receipt = json.loads(blob.metadata['framed_receipt'])
    frames, rate = receipt_frames(bucket, uid, receipt, deadline=deadline, memo=memo)
    if (blob.metadata or {}).get('pcm_sha256') != receipt['pcm_sha256']:
        raise ValueError('projection frame identity mismatch')
    return entries(frames, rate, source)


def append_projection_entries(chunks, bucket, blob, uid, entry, deadline, max_count, strict, *, memo=None):
    try:
        chunks.extend(
            projection_entries(bucket, blob, uid, entry, deadline=deadline, memo=memo)
            if has_frame_receipt(blob)
            else [entry]
        )
    except ValueError:
        if strict:
            raise
        return
    if max_count is not None and len(chunks) > max_count:
        raise TimeoutError('speaker audio listing budget exhausted')

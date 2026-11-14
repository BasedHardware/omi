"""Frame positions for immutable custody media and its PCM projections.

One object may contain disjoint capture spans. Sample offsets refer to captured
PCM concatenation, never elapsed wall time. A media upload alone is not proof.
"""

import hashlib
import json
import math
import time
from typing import Any

from utils import encryption
from utils.pusher_audio_window import AUDIO_TIMELINE_CONTINUITY_TOLERANCE

FRAME_SCHEMA = 'audio_frames_v1'
MAX_FRAMES = 4096
MAX_MANIFEST_BYTES = 4 * 1024 * 1024


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


def _manifest(
    bucket, uid: str, path: str, generation=None, digest=None, *, deadline=None, require_frame_schema=True
) -> dict:
    if not path.startswith(f'audio-outbox/{uid}/'):
        raise ValueError('frame manifest owner mismatch')
    blob = bucket.blob(path, generation=int(generation)) if generation else bucket.blob(path)
    blob.reload(timeout=io_timeout(deadline), retry=None)
    pinned = int(generation or blob.generation)
    if pinned <= 0:
        raise ValueError('frame manifest requires generation')
    raw = blob.download_as_bytes(if_generation_match=pinned, timeout=io_timeout(deadline), retry=None)
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError('frame manifest exceeds read bound')
    if (blob.metadata or {}).get('encrypted') == 'true':
        raw = encryption.decrypt_audio_file(raw, uid)
    if hashlib.sha256(raw).hexdigest() != (digest or (blob.metadata or {}).get('sha256')):
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
    return manifest


def committed_frames(bucket, blob, uid: str, *, deadline=None) -> tuple[list[dict], int]:
    metadata = blob.metadata or {}
    manifest = _manifest(bucket, uid, metadata['custody_manifest_path'], deadline=deadline)
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
    bucket, blob, uid: str, manifest_path: str, *, deadline=None, metadata=None
) -> tuple[list[dict], int]:
    """Frame positions for a pack whose writer did not declare a frame schema.

    ``commit_capture`` always writes the custody manifest beside the media, but
    only a framed pack records ``custody_manifest_path`` in the media metadata.
    The manifest is still the writer's own record of where each captured frame
    sits on the capture clock, so it is the only truthful source for a gapped
    pack's internal gap positions.
    """
    metadata = metadata if metadata is not None else (blob.metadata or {})
    manifest = _manifest(bucket, uid, manifest_path, deadline=deadline, require_frame_schema=False)
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


def gapped_frames(bucket, blob, uid: str, *, deadline=None, metadata=None) -> tuple[list[dict], int]:
    """The writer's own frame positions for one gapped, unframed pack.

    ``commit_capture`` names the manifest directory exactly like the media
    directory, so one prefix listing maps a pack to its own manifest without a
    per-pack list. A missing or ambiguous manifest is an error: the pack's
    internal gaps are unknowable without it.
    """
    prefix = f'audio-outbox/{uid}/{media_name(blob.name, uid)}/'
    candidates = [
        candidate
        for candidate in bucket.list_blobs(prefix=prefix, timeout=io_timeout(deadline), retry=None)
        if (candidate.metadata or {}).get('format') == 'audio-custody-manifest-v1'
    ]
    if len(candidates) != 1:
        raise ValueError('gapped capture has no unique custody manifest')
    return unframed_frames(bucket, blob, uid, candidates[0].name, deadline=deadline, metadata=metadata)


def receipt_frames(bucket, uid: str, receipt: dict, *, deadline=None) -> tuple[list[dict], int]:
    if receipt['bucket'] != bucket.name or not receipt['path'].startswith(f'raw-live/{uid}/'):
        raise ValueError('frame receipt owner mismatch')
    manifest = _manifest(
        bucket,
        uid,
        receipt['manifest_path'],
        receipt['manifest_generation'],
        receipt['manifest_sha256'],
        deadline=deadline,
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


def projection_entries(bucket, blob, uid: str, source: dict, *, deadline=None) -> list[dict]:
    receipt = json.loads(blob.metadata['framed_receipt'])
    frames, rate = receipt_frames(bucket, uid, receipt, deadline=deadline)
    if (blob.metadata or {}).get('pcm_sha256') != receipt['pcm_sha256']:
        raise ValueError('projection frame identity mismatch')
    return entries(frames, rate, source)


def append_projection_entries(chunks, bucket, blob, uid, entry, deadline, max_count, strict):
    try:
        chunks.extend(
            projection_entries(bucket, blob, uid, entry, deadline=deadline) if has_frame_receipt(blob) else [entry]
        )
    except ValueError:
        if strict:
            raise
        return
    if max_count is not None and len(chunks) > max_count:
        raise TimeoutError('speaker audio listing budget exhausted')

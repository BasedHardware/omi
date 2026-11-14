"""Require complete, verified raw coverage before retiring any PCM write."""

import hashlib
import json
import threading
import time
from bisect import bisect_right
from datetime import datetime
from google.cloud.exceptions import NotFound
from database.audio_timeline import chunk_span, span_valid

from utils import encryption
from utils.other.raw_audio import WAL_FORMAT, decode_capture, decode_capture_frames
from utils.other.audio_frame_table import (
    FRAME_SCHEMA,
    committed_frames,
    entries,
    gapped_frames,
    media_name,
    unframed_frames,
    validate_frames,
    receipt_frames,
    resampled_samples,
    io_timeout,
)
from utils.other.audio_raw_read_metrics import (
    ChecksumMismatch,
    CoverageMismatch,
    DecodeError,
    DecryptError,
    error_result,
    record,
    log_failure,
)
from config.refactor_modes import raw_live_gapped_packs_enabled

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


def _gapped_unframed(metadata: dict) -> bool:
    """A pack the writer recorded with gaps but without a declared frame schema."""
    if metadata.get('frame_schema') == FRAME_SCHEMA:
        return False
    try:
        return int(metadata['gap_count']) != 0
    except (KeyError, TypeError, ValueError):
        return False


def _custody_manifests(bucket, uid: str, conversation_id: str, *, deadline=None, timeout=10, max_count=10000):
    """Custody manifests written beside this conversation's unframed packs.

    ``commit_capture`` names the manifest directory exactly like the media
    directory, so one prefix listing maps every pack to its own manifest
    without a per-pack list.
    """
    prefix = f'audio-outbox/{uid}/{conversation_id}/'
    owner_prefix = f'audio-outbox/{uid}/'
    manifests = {}
    for index, blob in enumerate(bucket.list_blobs(prefix=prefix, timeout=io_timeout(deadline, timeout), retry=None)):
        if index >= max_count or (deadline is not None and time.monotonic() >= deadline):
            raise TimeoutError('raw capture manifest index budget exhausted')
        if (blob.metadata or {}).get('format') != 'audio-custody-manifest-v1':
            continue
        # Key by the writer's shared name, exactly as media_name derives it from
        # the media path, so a single-segment pack name matches too.
        manifests[blob.name[len(owner_prefix) :].rsplit('/', 1)[0]] = blob
    return manifests


def _gap_count_matches(frames: list[dict], gap_count: int) -> bool:
    """The writer counts a discontinuity and a retained zero-sample frame alike."""
    return (
        sum(frame['gap_before'] for frame in frames) + sum(1 for frame in frames if frame['samples'] == 0) == gap_count
    )


def list_packs(bucket, uid: str, conversation_id: str, *, fresh=False, deadline=None, timeout=10, max_count=10000):
    key = (getattr(bucket, 'name', ''), uid, conversation_id)
    with _index_lock:
        cached = _indexes.get(key)
        if not fresh and cached and cached[0] > time.monotonic():
            return cached[1]
    packs = []
    gapped_enabled = raw_live_gapped_packs_enabled()
    manifests = None
    for index, blob in enumerate(
        bucket.list_blobs(
            prefix=f'raw-live/{uid}/{conversation_id}/', timeout=io_timeout(deadline, timeout), retry=None
        )
    ):
        if index >= max_count or (deadline is not None and time.monotonic() >= deadline):
            raise TimeoutError('raw capture index budget exhausted')
        metadata = blob.metadata or {}
        if metadata.get('clock_source') == 'arrival_estimate':
            # Legacy pusher clocks cannot position independent raw packs on a
            # capture timeline. Keep them recoverable by immutable receipt;
            # ordinary playback uses the legacy continuous PCM projection.
            continue
        try:
            start, end = float(metadata['capture_start']), float(metadata['capture_end'])
            framed = metadata.get('frame_schema') == FRAME_SCHEMA
            gapped = not framed and int(metadata['gap_count']) != 0
            if (gapped and not gapped_enabled) or end <= start or int(metadata['channels']) != 1:
                continue
            if metadata['codec'] not in {'opus', 'flac', 'pcm16', 'pcm8'}:
                continue
            if metadata.get('source_layout', 'mono') != 'mono':
                continue
            source = {
                'timestamp': start,
                'path': blob.name,
                'size': blob.size,
                'is_batch': False,
                'span': {'start': start, 'samples': round((end - start) * 16000), 'sample_rate': 16000},
                'raw_end': end,
                'generation': getattr(blob, 'generation', None),
                'pcm_sha256': metadata.get('pcm_sha256'),
            }
            created = getattr(blob, 'time_created', None)
            if isinstance(created, datetime):
                source['raw_created_at'] = created.timestamp()
            if framed:
                frames, rate = committed_frames(bucket, blob, uid, deadline=deadline)
                if sum(frame['gap_before'] for frame in frames) != int(metadata['gap_count']):
                    raise CoverageMismatch('capture gap count differs from frame table')
                packs.extend(entries(frames, rate, source))
                if len(packs) > max_count:
                    raise TimeoutError('raw capture index budget exhausted')
            elif gapped:
                # The writer kept the exact frame positions in the custody
                # manifest even though the media metadata omits the frame
                # schema. Without it the pack's internal gaps are unknowable,
                # so an unresolvable manifest stays excluded rather than being
                # decoded as one continuous stream.
                if manifests is None:
                    manifests = _custody_manifests(
                        bucket, uid, conversation_id, deadline=deadline, timeout=timeout, max_count=max_count
                    )
                manifest = manifests.get(media_name(blob.name, uid))
                if manifest is None:
                    continue
                frames, rate = unframed_frames(bucket, blob, uid, manifest.name, deadline=deadline)
                if not _gap_count_matches(frames, int(metadata['gap_count'])):
                    raise CoverageMismatch('capture gap count differs from frame table')
                packs.extend(entries(frames, rate, source, allow_empty=True))
                if len(packs) > max_count:
                    raise TimeoutError('raw capture index budget exhausted')
            else:
                packs.append(source)
        except (KeyError, ValueError, TypeError, NotFound):
            continue
    result = sorted(packs, key=lambda item: item['timestamp'])
    with _index_lock:
        if len(_indexes) >= _MAX_INDEXES:
            _indexes.pop(next(iter(_indexes)))
        _indexes[key] = (time.monotonic() + _INDEX_TTL, result)
    return result


def raw_chunks_for_listing(
    bucket,
    uid,
    conversation_id,
    chunks,
    *,
    enabled,
    include_raw=False,
    timeout=None,
    deadline=None,
    max_count=None,
    require_archive=False,
    list_raw=list_packs,
):
    """Playback may fall back; independent replay proof requires a fresh complete inventory."""
    if not enabled:
        return []
    try:
        packs = (
            list_raw(
                bucket,
                uid,
                conversation_id,
                fresh=True,
                deadline=deadline,
                timeout=timeout or 10,
                max_count=max_count or 10000,
            )
            if include_raw
            else list_raw(bucket, uid, conversation_id)
        )
        raw_chunks = packs if include_raw else uncovered_raw_packs(packs, chunks)
        if max_count is not None and len(chunks) + len(raw_chunks) > max_count:
            raise TimeoutError('speaker audio listing budget exhausted')
        return raw_chunks
    except Exception:
        if require_archive or include_raw:
            raise
        log_failure('other')
        return []


def finish_audio_listing(chunks, raw_chunks, source_identity):
    chunks.extend(raw_chunks)
    if source_identity or raw_chunks:
        for chunk in chunks:
            span = chunk.get('span')
            if span and span['start'] != chunk['timestamp']:
                # Preserve the sample clock after encoded coverage replaces raw
                # fragments and across archive kill-switch changes.
                chunk['legacy_timestamp'] = chunk['timestamp']
                chunk['timestamp'] = span['start']
    return sorted(chunks, key=lambda item: item['timestamp'])


def _read_pack(bucket, path: str, uid: str, download_kwargs=None, sample_rate: int = 16000) -> bytes:
    download_kwargs = {'timeout': 10, 'retry': None, **(download_kwargs or {})}
    blob = bucket.blob(path)
    try:
        return _decode_pack(bucket, blob, uid, download_kwargs, sample_rate)
    except Exception as error:
        record(error_result(error), (blob.metadata or {}).get('codec'))
        raise


def _decode_pack(bucket, blob, uid: str, download_kwargs, sample_rate: int) -> bytes:
    deadline = time.monotonic() + download_kwargs.get('timeout', 10)
    blob.reload(**(download_kwargs or {}))
    metadata = blob.metadata or {}
    frames = None
    if metadata.get('frame_schema') == FRAME_SCHEMA:
        frames, rate = committed_frames(bucket, blob, uid, deadline=deadline)
        expected = resampled_samples(validate_frames(frames, rate), rate, sample_rate) * 2
    elif _gapped_unframed(metadata) and raw_live_gapped_packs_enabled():
        # A gapped pack's decoded length is the sum of its recorded frames, not
        # its wall span. The manifest is the only truthful source for both.
        frames, rate = gapped_frames(bucket, blob, uid, deadline=deadline)
        expected = resampled_samples(sum(int(frame['samples']) for frame in frames), rate, sample_rate) * 2
    else:
        expected = round((float(metadata['capture_end']) - float(metadata['capture_start'])) * sample_rate) * 2
    raw = blob.download_as_bytes(**{**download_kwargs, 'timeout': io_timeout(deadline)})
    if metadata.get('encrypted') == 'true':
        try:
            raw = encryption.decrypt_audio_file(raw, uid)
        except Exception as error:
            raise DecryptError('capture decrypt failed') from error
    if hashlib.sha256(raw).hexdigest() != metadata.get('sha256'):
        raise ChecksumMismatch('capture checksum mismatch')
    try:
        if frames is not None and metadata.get('frame_schema') != FRAME_SCHEMA and metadata.get('format') == WAL_FORMAT:
            # Only the omi-wal container carries per-packet byte ranges. A
            # gapped flac/pcm16 pack encodes the captured PCM contiguously, so
            # the ordinary decoder already returns exactly the recorded samples.
            pcm = decode_capture_frames(raw, metadata, frames, sample_rate)
        else:
            pcm = decode_capture(raw, metadata, sample_rate)
    except Exception as error:
        raise DecodeError('capture decode failed') from error
    if abs(len(pcm) - expected) > 2:
        raise CoverageMismatch('capture sample coverage mismatch')
    return pcm


def read_pack(bucket, path: str, uid: str, download_kwargs=None, sample_rate: int = 16000) -> bytes:
    pcm = _read_pack(bucket, path, uid, download_kwargs, sample_rate)
    record('ok')
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
        offset = (pack.get('raw_offset_samples', 0) + round((start - pack['timestamp']) * 16000)) * 2
        whole_pack_proof = (
            'raw_offset_samples' not in pack
            and offset == 0
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
        # Historical PCM often has no raw identity. This optional lookup is
        # not a raw read attempt until a covering raw candidate is found.
        return None
    start = float(span['start'])
    count = int(span['samples']) * 2
    matched = False
    try:
        packs = list_packs(bucket, uid, conversation_id)
    except Exception as error:
        record(error_result(error))
        raise
    for pack in packs:
        if pack['timestamp'] <= start + 0.0001 and pack['raw_end'] >= start + count / 32000 - 0.0001:
            matched = True
            pcm = _read_pack(bucket, pack['path'], uid)
            offset = (pack.get('raw_offset_samples', 0) + round((start - pack['timestamp']) * 16000)) * 2
            selected = pcm[offset : offset + count]
            if len(selected) == count and hashlib.sha256(selected).hexdigest() == expected_sha256:
                record('ok')
                return selected
    if matched:
        record('identity_mismatch')
    return None


def pcm_for_projection(bucket, uid: str, metadata: dict, sample_rate: int):
    """A framed projection points to disjoint spans, never a synthetic wall interval."""
    try:
        receipt = json.loads(metadata['framed_receipt'])
        if sample_rate != receipt['sample_rate']:
            return None
        receipt_frames(bucket, uid, receipt)
    except Exception as error:
        record(error_result(error))
        raise
    # The shared raw read boundary records decode failures with its loaded codec.
    pcm = _read_pack(bucket, receipt['path'], uid, {'if_generation_match': int(receipt['generation'])}, sample_rate)
    if hashlib.sha256(pcm).hexdigest() != receipt['pcm_sha256'] or receipt['pcm_sha256'] != metadata.get('pcm_sha256'):
        record('identity_mismatch')
        return None
    record('ok')
    return pcm


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
    # A reconnect can commit a second raw receipt before projection detects a
    # conflict. Prefer the earlier immutable media creation time, regardless of
    # prefix-list order or the new window's start/end; retain only its new tail.
    for pack in sorted(packs, key=lambda item: (item.get('raw_created_at') is None, item.get('raw_created_at', 0))):
        # Keep historical selection for spanless legacy entries: their encoded
        # size is not proof of sample coverage.
        if any(pack['timestamp'] <= stamp < pack['raw_end'] for stamp in unknown):
            continue
        original_start = round(pack['timestamp'] * 16000)
        original_end = original_start + pack['span']['samples']
        cursor = original_start
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
        for start, end in remaining:
            item = dict(pack)
            if start != original_start or end != original_end:
                item.update(
                    timestamp=start / 16000,
                    raw_end=end / 16000,
                    raw_source_start=pack['timestamp'],
                    span={'start': start / 16000, 'samples': end - start, 'sample_rate': 16000},
                )
                if 'raw_offset_samples' in pack:
                    item['raw_offset_samples'] = pack['raw_offset_samples'] + start - original_start
                    if 'raw_capture_rate' in pack:
                        rate = pack['raw_capture_rate']
                        capture_start = pack['raw_capture_offset_samples']
                        capture_end = capture_start + pack['raw_capture_samples']
                        # Only quantize cut edges. A rounded rendition length
                        # cannot reconstruct the original capture endpoints.
                        if start != original_start:
                            capture_start = min(
                                capture_end, max(capture_start, round(item['raw_offset_samples'] * rate / 16000))
                            )
                        if end != original_end:
                            capture_end = max(
                                capture_start,
                                min(
                                    capture_end,
                                    round((pack['raw_offset_samples'] + end - original_start) * rate / 16000),
                                ),
                            )
                        item.update(
                            raw_capture_offset_samples=capture_start,
                            raw_capture_samples=capture_end - capture_start,
                        )
                    item.pop('raw_source_start', None)
            result.append(item)
        # Claim this pack's interval for subsequent raw packs, just as encoded
        # spans already claim theirs. No stored bytes or frame times change.
        merged = []
        for lo, hi in sorted([*union, (original_start, original_end)]):
            if merged and lo <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
            else:
                merged.append((lo, hi))
        union = merged
        ends = [hi for _, hi in union]
    return sorted(result, key=lambda item: item['timestamp'])


def select_raw_pcm(pcm: bytes, chunk: dict, sample_rate: int) -> bytes:
    """A listing fragment selects exact samples from the unchanged source pack."""
    if 'raw_source_start' not in chunk and 'raw_offset_samples' not in chunk:
        return pcm
    span = chunk['span']
    # Upsampling can put a 16 kHz cut between two source sample boundaries.
    # Keep that rendition's exact bounds as well as the native capture bounds.
    if 'raw_capture_rate' in chunk and sample_rate != 16000:
        rate = chunk['raw_capture_rate']
        start = resampled_samples(chunk['raw_capture_offset_samples'], rate, sample_rate)
        end = resampled_samples(chunk['raw_capture_offset_samples'] + chunk['raw_capture_samples'], rate, sample_rate)
        selected = pcm[start * 2 : end * 2]
        if len(selected) != (end - start) * 2:
            raise ValueError('raw playback fragment has incomplete sample coverage')
        return selected
    offset = (
        round(chunk['raw_offset_samples'] * sample_rate / 16000)
        if 'raw_offset_samples' in chunk
        else round((chunk['timestamp'] - chunk['raw_source_start']) * sample_rate)
    ) * 2
    count = round(span['samples'] * sample_rate / span['sample_rate']) * 2
    selected = pcm[offset : offset + count]
    if len(selected) != count:
        raise ValueError('raw playback fragment has incomplete sample coverage')
    return selected

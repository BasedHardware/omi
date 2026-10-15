"""Apply source-frame coverage plans to decoded WAL WAV files.

Splits kept source-frame intervals into per-interval WAV derivatives inside a
unique subdirectory of the original file, never concatenating covered gaps.
Every derivative filename keeps the original phone-clock start plus its sample
offset so downstream VAD/STT naming and timestamps stay anchored, and every
derivative carries a rebased source_frame_map claim. Also owns the bounded
lineage-envelope lookup and per-batch orchestration for the consumer.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import uuid
import wave
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional, TypeGuard

from config.capture_evidence import capture_evidence_dark_write_enabled
from config.sync_audio_coverage import sync_wal_audio_coverage_active_for
from utils.capture_evidence import decoded_frame_map
from utils.executors import submit_with_context
from utils.observability.fallback import record_fallback
from utils.request_validation import parse_sync_filename_timestamp
from utils.sync import recording_lineage
from utils.sync.audio_coverage import (
    MAX_DECODED_FRAMES,
    MAX_ENVELOPES,
    MAX_OUTPUT_INTERVALS,
    plan_unreceived_frames,
    validated_live_ranges,
)
from utils.sync.files import get_timestamp_from_path, get_wav_duration
from utils.sync.lineage_diagnostics import classify_generation_row
from utils.sync.recording_session_target import clean_text, source_value

logger = logging.getLogger(__name__)

COVERAGE_DISCOVERY_SECONDS = 3600


def _is_int(value: object) -> bool:
    return type(value) is int


def _valid_capture_root(root: object) -> bool:
    if not isinstance(root, str):
        return False
    try:
        uuid.UUID(root)
    except (ValueError, AttributeError):
        return False
    return True


def _remove_generated(paths: set) -> None:
    for path in paths:
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            logger.warning('wal audio coverage: failed to remove generated path after error')


def _claim_valid(claim: Any) -> TypeGuard[dict]:
    raw: Any = claim
    if not isinstance(raw, Mapping):
        return False
    if not _valid_capture_root(raw.get('capture_root')):
        return False
    epoch: Any = raw.get('clock_epoch')
    start: Any = raw.get('source_frame_start')
    count: Any = raw.get('frame_count')
    rate: Any = raw.get('rate_hz')
    if not all(_is_int(v) for v in (epoch, start, count, rate)):
        return False
    if epoch < 0 or start < 0 or count <= 0 or rate <= 0:
        return False
    return raw.get('codec') in ('pcm16', 'opus') and raw.get('channel') == 'mono'


def frame_sample_offsets(frame_samples: Sequence[int]) -> Optional[list[int]]:
    """Cumulative decoded-sample offsets for each source frame, [0, ..., total]."""
    try:
        frame_count = len(frame_samples)
    except TypeError:
        return None
    if not frame_count or frame_count > MAX_DECODED_FRAMES:
        return None
    samples = list(frame_samples)
    if any(not _is_int(n) or n <= 0 for n in samples):
        return None
    offsets = [0]
    for count in samples:
        offsets.append(offsets[-1] + count)
    return offsets


def _format_timestamp(value: Decimal) -> str:
    if value == value.to_integral_value():
        return str(int(value))
    return format(value.normalize(), 'f')


def _result(status: str, wav_paths: list[str], frame_maps: dict, generated: set) -> dict:
    return {
        'status': status,
        'wav_paths': wav_paths,
        'frame_maps': frame_maps,
        'generated_paths': generated,
    }


def apply_wal_audio_coverage(
    wav_path: str,
    claim: Mapping,
    frame_samples: Sequence[int],
    keep_intervals: Sequence[tuple[int, int]] | None,
    *,
    frame_map: Optional[Mapping] = None,
) -> Optional[dict]:
    """Materialize kept source-frame intervals of one decoded WAL file.

    keep_intervals is the exact output of plan_unreceived_frames: absolute
    source-frame half-open intervals over [claim.source_frame_start,
    source_frame_start + len(frame_samples)). Returns None on any malformed
    input or write failure so the caller keeps the original bytes, path, and
    map untouched. All paths written are reported in generated_paths; on
    failure they are removed before returning None.
    """
    if keep_intervals is None or not _claim_valid(claim):
        return None
    try:
        interval_count = len(keep_intervals)
    except TypeError:
        return None
    if interval_count > MAX_OUTPUT_INTERVALS:
        return None
    offsets = frame_sample_offsets(frame_samples)
    if offsets is None:
        return None
    if frame_map is not None and frame_map.get('offsets') != offsets:
        return None
    domain_start = claim['source_frame_start']
    domain_count = len(offsets) - 1
    domain_end = domain_start + domain_count
    if domain_count > claim['frame_count']:
        return None

    spans: list[tuple[int, int]] = []
    for interval in keep_intervals:
        try:
            start, end = interval
        except (TypeError, ValueError):
            return None
        if not _is_int(start) or not _is_int(end):
            return None
        if start < domain_start or end > domain_end or end <= start:
            return None
        spans.append((start, end))
    if spans != sorted(spans) or any(spans[i][1] > spans[i + 1][0] for i in range(len(spans) - 1)):
        return None

    try:
        with wave.open(wav_path, 'rb') as source:
            channels = source.getnchannels()
            sample_width = source.getsampwidth()
            frame_rate = source.getframerate()
            total_frames = source.getnframes()
            params = (channels, sample_width, frame_rate)
    except Exception:
        return None
    if params != (1, 2, claim['rate_hz']) or total_frames != offsets[-1]:
        return None

    try:
        base_timestamp = Decimal(str(parse_sync_filename_timestamp(wav_path)))
    except ValueError:
        return None

    if not spans:
        return _result('suppressed', [], {}, set())
    if len(spans) == 1 and spans[0] == (domain_start, domain_end):
        frame_maps = {wav_path: frame_map} if frame_map is not None else {}
        return _result('unchanged', [wav_path], frame_maps, set())

    directory = os.path.dirname(wav_path)
    stem = os.path.basename(wav_path).rsplit('.', 1)[0]
    coverage_dir = os.path.join(directory, f'{stem}.coverage', uuid.uuid4().hex)
    source_incomplete = bool(frame_map.get('incomplete')) if isinstance(frame_map, Mapping) else False
    generated: set = set()
    try:
        os.makedirs(coverage_dir, exist_ok=True)
        with wave.open(wav_path, 'rb') as source:
            wav_paths: list[str] = []
            frame_maps: dict = {}
            for start, end in spans:
                first = start - domain_start
                last = end - domain_start
                sample_start = offsets[first]
                sample_end = offsets[last]
                derivative_timestamp = _format_timestamp(base_timestamp + Decimal(sample_start) / frame_rate)
                derivative_path = os.path.join(coverage_dir, f'{stem}_{derivative_timestamp}.wav')
                generated.add(derivative_path)
                source.setpos(sample_start)
                payload = source.readframes(sample_end - sample_start)
                if len(payload) != (sample_end - sample_start) * 2:
                    raise ValueError('short wav read')
                with wave.open(derivative_path, 'wb') as out:
                    out.setnchannels(1)
                    out.setsampwidth(2)
                    out.setframerate(frame_rate)
                    out.writeframes(payload)
                rebased = [0]
                running = 0
                for index in range(first, last):
                    running += offsets[index + 1] - offsets[index]
                    rebased.append(running)
                derivative_claim = dict(claim)
                derivative_claim['source_frame_start'] = start
                derivative_claim['frame_count'] = end - start
                frame_maps[derivative_path] = {
                    'claim': derivative_claim,
                    'offsets': rebased,
                    'incomplete': source_incomplete,
                    'coverage_trimmed': True,
                }
                wav_paths.append(derivative_path)
    except Exception as e:
        _remove_generated(generated)
        try:
            os.removedirs(coverage_dir)
        except OSError:
            pass
        logger.warning('wal audio coverage: split failed exception_type=%s', type(e).__name__)
        return None
    return _result('split', wav_paths, frame_maps, generated)


def _live_coverage_envelopes(
    uid: str,
    origin_id: str,
    *,
    started_before: datetime,
    finished_after: datetime,
    source: Any,
    client_device_id: Optional[str],
    is_locked: bool,
    firestore_client: Any = None,
) -> tuple[Optional[list[dict]], str]:
    """Validated live envelopes for one capture origin, or an abstention token.

    Same bounded indexed lineage lookup as segment binding; only provenance-
    compatible rows can donate their stored live capture_evidence snapshot.
    """
    rows, truncated_before, degraded = recording_lineage.load_lineage(
        uid,
        clean_text(origin_id),
        started_before,
        firestore_client,
        finished_after,
        include_capture_evidence=True,
    )
    if degraded:
        return None, 'degraded'
    if truncated_before is not None:
        return None, 'truncated'
    wanted_source = source_value(source)
    device_id = clean_text(client_device_id)
    envelopes: list[dict] = []
    for row in rows:
        if (
            classify_generation_row(
                row,
                origin_id=clean_text(origin_id),
                source=wanted_source,
                client_device_id=device_id,
                is_locked=is_locked,
            )
            is not None
        ):
            continue
        evidence = row.get('capture_evidence')
        if isinstance(evidence, Mapping) and evidence:
            envelopes.append(dict(evidence))
    if len(envelopes) > MAX_ENVELOPES:
        return None, 'overflow'
    return envelopes, 'eligible'


def apply_batch_wal_audio_coverage(
    uid: str,
    origin_id: str,
    *,
    source: Any,
    client_device_id: Optional[str],
    is_locked: bool,
    wav_paths: Sequence[str],
    source_frame_maps: Mapping,
    decoded_frames: Mapping,
    firestore_client: Any = None,
) -> dict:
    """Trim positively live-received frames from every mapped WAV in the batch.

    Blocking: performs the bounded lineage read and filesystem work; call via an
    executor. Returns a dict whose 'status' is 'applied' or 'abstained'; on
    'applied' the caller replaces wav_paths/source_frame_maps with the returned
    ones and cleans up 'retired_paths'. Any evidence failure abstains the whole
    batch and returns the originals untouched.
    """
    stats = {
        'kept_seconds': 0.0,
        'dropped_seconds': 0.0,
        'context_seconds': 0.0,
        'file_count': 0,
        'suppressed_count': 0,
    }
    started_values = []
    end_values = []
    for path in wav_paths:
        try:
            began = float(get_timestamp_from_path(path))
        except (ValueError, TypeError):
            return {'status': 'abstained', 'reason': 'unparseable', 'stats': stats}
        started_values.append(began)
        end_values.append(began + get_wav_duration(path))
    envelopes, eligibility = _live_coverage_envelopes(
        uid,
        origin_id,
        started_before=datetime.fromtimestamp(max(end_values) + COVERAGE_DISCOVERY_SECONDS, tz=timezone.utc),
        finished_after=datetime.fromtimestamp(min(started_values) - COVERAGE_DISCOVERY_SECONDS, tz=timezone.utc),
        source=source,
        client_device_id=client_device_id,
        is_locked=is_locked,
        firestore_client=firestore_client,
    )
    if envelopes is None:
        return {'status': 'abstained', 'reason': eligibility, 'stats': stats}

    planned: list[tuple[str, Any, Any, Any]] = []
    for path in wav_paths:
        mapping = source_frame_maps.get(path)
        if not isinstance(mapping, Mapping):
            planned.append((path, None, None, None))
            continue
        claim = mapping['claim']
        frame_samples = decoded_frames.get(path, [])
        try:
            wal_start_seconds: Any = float(get_timestamp_from_path(path))
        except (ValueError, TypeError):
            wal_start_seconds = None
        ranges = validated_live_ranges(
            claim, envelopes, wal_start_seconds=wal_start_seconds, frame_samples=frame_samples
        )
        if ranges is None:
            return {'status': 'abstained', 'reason': 'evidence', 'stats': stats}
        keep = plan_unreceived_frames(
            frame_samples,
            ranges,
            frame_start=claim['source_frame_start'],
            sample_rate=claim['rate_hz'],
        )
        if keep is None:
            planned.append((path, mapping, None, None))
            continue
        keep_uncovered = plan_unreceived_frames(
            frame_samples,
            ranges,
            frame_start=claim['source_frame_start'],
            sample_rate=claim['rate_hz'],
            context_seconds=0,
        )
        planned.append((path, mapping, frame_samples, (keep, keep_uncovered)))

    new_wav_paths: list[str] = []
    new_frame_maps: dict = {}
    retired_paths: list[str] = []
    generated_paths: set = set()
    for path, mapping, frame_samples, plan in planned:
        if plan is None:
            new_wav_paths.append(path)
            if isinstance(mapping, Mapping):
                new_frame_maps[path] = mapping
            continue
        keep, keep_uncovered = plan
        claim = mapping['claim']
        result = apply_wal_audio_coverage(path, claim, frame_samples, keep, frame_map=mapping)
        if result is None:
            _remove_generated(generated_paths)
            return {'status': 'abstained', 'reason': 'geometry', 'stats': stats}
        stats['file_count'] += 1
        offsets = frame_sample_offsets(frame_samples)
        if offsets is None:
            _remove_generated(generated_paths)
            return {'status': 'abstained', 'reason': 'geometry', 'stats': stats}
        domain_start = claim['source_frame_start']
        total_seconds = offsets[-1] / claim['rate_hz']
        kept_samples = sum(offsets[end - domain_start] - offsets[start - domain_start] for start, end in keep)
        uncovered_samples = (
            sum(offsets[end - domain_start] - offsets[start - domain_start] for start, end in keep_uncovered)
            if keep_uncovered is not None
            else kept_samples
        )
        stats['kept_seconds'] += kept_samples / claim['rate_hz']
        stats['dropped_seconds'] += total_seconds - kept_samples / claim['rate_hz']
        stats['context_seconds'] += (kept_samples - uncovered_samples) / claim['rate_hz']
        if result['status'] == 'suppressed':
            retired_paths.append(path)
            stats['suppressed_count'] += 1
            continue
        if result['status'] == 'unchanged':
            new_wav_paths.append(path)
            new_frame_maps[path] = mapping
            continue
        retired_paths.append(path)
        generated_paths |= result['generated_paths']
        new_wav_paths.extend(result['wav_paths'])
        new_frame_maps.update(result['frame_maps'])
    return {
        'status': 'applied',
        'reason': 'none',
        'stats': stats,
        'wav_paths': new_wav_paths,
        'source_frame_maps': new_frame_maps,
        'retired_paths': retired_paths,
        'generated_paths': generated_paths,
        'suppressed_all': stats['suppressed_count'] > 0 and not new_wav_paths,
    }


def build_sync_source_frame_maps(
    capture_evidence_claims: Optional[Mapping[str, dict]],
    wav_paths: Sequence[str],
    decoded_frames: Mapping[str, list[int]],
) -> dict:
    """Anchor each decoded WAL WAV to original frame ordinals when S1 claims exist."""
    source_frame_maps: dict = {}
    if not (
        capture_evidence_dark_write_enabled()
        and isinstance(capture_evidence_claims, Mapping)
        and capture_evidence_claims
    ):
        return source_frame_maps
    for wav_path in wav_paths:
        claim = capture_evidence_claims.get(os.path.basename(wav_path).replace('.wav', '.bin'))
        if (
            not _claim_valid(claim)
            or (claim['codec'] == 'pcm16' and '_pcm16_' not in wav_path)
            or (claim['codec'] == 'opus' and '_opus_' not in wav_path)
        ):
            continue
        with wave.open(wav_path, 'rb') as decoded_wav:
            mapping = decoded_frame_map(
                claim,
                decoded_frames.get(wav_path, []),
                wav_rate_hz=decoded_wav.getframerate(),
                wav_channels=decoded_wav.getnchannels(),
            )
        if mapping is not None:
            source_frame_maps[wav_path] = mapping
    return source_frame_maps


def _submit_orphan_cleanup(storage_executor: Any, cleanup_files: Any, coverage: Any) -> None:
    if not isinstance(coverage, Mapping):
        return
    generated = coverage.get('generated_paths')
    if not generated:
        return
    try:
        submit_with_context(storage_executor, cleanup_files, list(generated))
    except Exception:
        logger.warning('wal audio coverage: orphan cleanup submit failed')


async def apply_sync_wal_audio_coverage(
    uid: str,
    source: Any,
    should_lock: bool,
    client_device_id: Optional[str],
    recording_session_id: Optional[str],
    capture_evidence_claims: Optional[Mapping[str, dict]],
    wav_paths: list,
    decoded_frames: Mapping,
    *,
    run_blocking: Any,
    db_executor: Any,
    storage_executor: Any,
    cleanup_files: Any,
) -> tuple[list, dict, bool]:
    """Trim positively live-received WAL frames before VAD/STT.

    Returns ``(wav_paths, source_frame_maps, suppressed_all)``. Without upload
    signal or either gate the inputs come back untouched with no lookup and no
    coverage log; a missing stored snapshot still costs the bounded lineage
    lookup before retaining everything. Any coverage failure retains the
    original audio and reports the shared fallback once.
    """
    source_frame_maps = build_sync_source_frame_maps(capture_evidence_claims, wav_paths, decoded_frames)
    if not (
        source_frame_maps
        and sync_wal_audio_coverage_active_for(uid)
        and capture_evidence_dark_write_enabled()
        and capture_evidence_claims
        and recording_session_id
    ):
        return wav_paths, source_frame_maps, False

    cancelled = threading.Event()
    finished: dict = {}

    def worker() -> dict:
        result = apply_batch_wal_audio_coverage(
            uid,
            recording_session_id,
            source=source,
            client_device_id=client_device_id,
            is_locked=bool(should_lock),
            wav_paths=wav_paths,
            source_frame_maps=source_frame_maps,
            decoded_frames=decoded_frames,
        )
        finished['coverage'] = result
        if cancelled.is_set():
            _submit_orphan_cleanup(storage_executor, cleanup_files, result)
        return result

    try:
        coverage = await run_blocking(db_executor, worker)
    except asyncio.CancelledError:
        cancelled.set()
        _submit_orphan_cleanup(storage_executor, cleanup_files, finished.get('coverage'))
        raise
    except Exception:
        record_fallback(
            component='other',
            from_mode='sync_lineage',
            to_mode='temporal',
            reason='other',
            outcome='degraded',
            log=logger,
        )
        return wav_paths, source_frame_maps, False
    try:
        stats = coverage['stats']
        logger.info(
            'event=sync_wal_audio_coverage outcome=%s method=source_frame kept_seconds=%.3f dropped_seconds=%.3f context_seconds=%.3f file_count=%d suppressed=%d',
            coverage['status'],
            stats['kept_seconds'],
            stats['dropped_seconds'],
            stats['context_seconds'],
            stats['file_count'],
            stats['suppressed_count'],
        )
    except Exception:
        pass
    if coverage['status'] != 'applied':
        return wav_paths, source_frame_maps, False
    return coverage['wav_paths'], coverage['source_frame_maps'], coverage['suppressed_all']

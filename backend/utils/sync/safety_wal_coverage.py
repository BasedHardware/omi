"""Server-only live coverage, without client S1 claims.

Time overlap alone never authorizes a drop. A bounded energy-envelope probe must
establish a unique WAL-to-stored-audio clock offset. Otherwise preserve the WAL
and let transcript overlap dedupe run. All storage and WAV I/O runs in a worker.
"""

from __future__ import annotations

import logging
import math
import os
import time
import uuid
import wave
from collections.abc import Awaitable, Callable, Collection
from concurrent.futures import Executor
from typing import Any

import numpy as np

from config.sync_safety_wal import sync_safety_wal_enabled
from utils.observability.fallback import record_fallback
from utils.sync.files import get_timestamp_from_path, get_wav_duration
from utils.sync.safety_wal_metrics import AUDIO_BYTES_NOT_STORED, WAL_SECONDS_SKIPPED

logger = logging.getLogger(__name__)
RATE = 16000
HOP = 1600  # 100 ms envelope; the cut retains a one-second boundary margin.
MAX_SKEW = 90
MARGIN = 1.0
MAX_PCM_BYTES = 64 * 1024 * 1024


def energy_envelope(pcm: bytes) -> np.ndarray:
    samples = np.frombuffer(pcm, dtype='<i2').astype(np.float32)
    count = len(samples) // HOP
    if not count:
        return np.array([], dtype=np.float32)
    return np.sqrt(np.mean(samples[: count * HOP].reshape(count, HOP) ** 2, axis=1))


def estimate_offset(wal: np.ndarray, wal_start: float, probes: list[tuple[float, np.ndarray]]) -> float | None:
    """Unique non-silent >=6-second fingerprint, searching at most +/-90 seconds.

    Positive offset maps device WAL timestamps onto stored live timestamps.
    Reject flat/silent, ambiguous/repeated and weak matches rather than assuming
    receive-time and device clocks agree. Probe at most the first 20 WAL seconds.
    """
    wal = wal[:200]
    scores = []
    for start, live in probes:
        # Search sample-grid lags directly, including sub-second chunk origins.
        center = round((wal_start - start) * 10)
        for lag in range(max(-len(wal) + 60, center - MAX_SKEW * 10), min(len(live) - 60, center + MAX_SKEW * 10) + 1):
            first = max(0, -lag)
            last = min(len(wal), len(live) - lag)
            if last - first < 60:
                continue
            a, b = wal[first:last], live[first + lag : last + lag]
            a, b = a - a.mean(), b - b.mean()
            denom = float(np.linalg.norm(a) * np.linalg.norm(b))
            if denom <= 1 or float(np.std(a)) < 10 or float(np.std(b)) < 10:
                continue
            score = float(np.dot(a, b) / denom)
            scores.append((score, start + lag / 10 - wal_start))
    if not scores:
        return None
    best, offset = max(scores)
    # Competing offsets outside half the retained margin make the cut unsafe.
    rivals = [score for score, other in scores if abs(other - offset) > MARGIN / 2]
    if best < 0.92 or (rivals and best - max(rivals) < 0.10):
        return None
    return offset


def uncovered_intervals(
    start: float, duration: float, coverage: list[tuple[float, float]], offset: float | None
) -> list[tuple[float, float]]:
    """WAL-relative uncovered intervals, eroding coverage to keep boundary speech."""
    if offset is None or not math.isfinite(offset):
        return [(0.0, duration)]
    merged = []
    for left, right in sorted(coverage):
        if merged and left <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(right, merged[-1][1]))
        else:
            merged.append((left, right))
    kept = []
    cursor = 0.0
    for left, right in merged:
        left = max(0.0, left - start - offset + MARGIN)
        right = min(duration, right - start - offset - MARGIN)
        if right <= left or right <= cursor:
            continue
        if left > cursor:
            kept.append((cursor, left))
        cursor = max(cursor, right)
    if cursor < duration:
        kept.append((cursor, duration))
    return kept


def _materialize(path: str, intervals: list[tuple[float, float]], offset: float) -> list[str]:
    outputs = []
    directory = os.path.join(os.path.dirname(path), 'safety-coverage', uuid.uuid4().hex)
    try:
        os.makedirs(directory)
        with wave.open(path, 'rb') as source:
            rate = source.getframerate()
            params = source.getparams()
            timestamp = get_timestamp_from_path(path)
            for first, last in intervals:
                # Rounding outward preserves every uncovered sample.
                begin, end = math.floor(first * rate), math.ceil(last * rate)
                source.setpos(begin)
                payload = source.readframes(end - begin)
                if len(payload) != (end - begin) * params.nchannels * params.sampwidth:
                    raise ValueError('short coverage read')
                output = os.path.join(directory, f'wal_{timestamp + offset + begin / rate:.6f}.wav')
                outputs.append(output)
                with wave.open(output, 'wb') as destination:
                    destination.setparams(params)
                    destination.writeframes(payload)
        return outputs
    except Exception:
        for output in outputs:
            if os.path.exists(output):
                os.remove(output)
        raise


def cut_live_coverage(uid: str, row: dict, path: str) -> tuple[list[str], str, float, int]:
    from utils.other import storage

    start, duration = get_timestamp_from_path(path), get_wav_duration(path)
    chunks = storage.list_audio_chunks(uid, row['id'], timeout=5, max_count=10000)
    coverage, probes = [], []
    budget = 0
    attempts = 0
    deadline = time.monotonic() + 15
    for chunk in sorted(chunks, key=lambda c: abs(float(c['timestamp']) - start)):
        span = chunk.get('span')
        # Legacy batches concatenate payloads without preserving internal gaps.
        # Their aggregate decoded duration cannot prove continuous wall coverage.
        if chunk.get('is_batch') and not span:
            continue
        left = float(span['start'] if span else chunk['timestamp'])
        # Legacy chunks may extend across the WAL start; don't infer duration
        # from encoded size. Decode relevant chunks, bounded by bytes/count.
        if left > start + duration + MAX_SKEW:
            continue
        if span:
            seconds = float(span['samples']) / float(span['sample_rate'])
            if left + seconds < start - MAX_SKEW:
                continue
            coverage.append((left, left + seconds))
        elif left < start - MAX_SKEW - 3600:
            continue
        needs_probe = abs(left - start) <= MAX_SKEW + 60
        if not span or needs_probe:
            if (
                int(chunk.get('size') or 0) > 8 * 1024 * 1024
                or budget >= MAX_PCM_BYTES
                or attempts >= 32
                or time.monotonic() >= deadline
            ):
                continue
            attempts += 1
            pcm = storage.download_audio_chunk_pcm(uid, chunk['path'], RATE)
            if not pcm:
                continue
            budget += len(pcm)
            seconds = len(pcm) / (RATE * 2)
            if not span:
                coverage.append((left, left + seconds))
            if needs_probe and len(probes) < 12:
                probes.append((left, energy_envelope(pcm[: RATE * 2 * 180])))
    with wave.open(path, 'rb') as source:
        if source.getnchannels() != 1 or source.getsampwidth() != 2 or source.getframerate() != RATE:
            return [path], 'unsupported_wav', 0.0, 0
        envelope = energy_envelope(source.readframes(RATE * 20))
    offset = estimate_offset(envelope, start, probes)
    if offset is None:
        return [path], 'unreliable_clock', 0.0, 0
    intervals = uncovered_intervals(start, duration, coverage, offset)
    if len(intervals) > 128:
        return [path], 'fragmented_coverage', 0.0, 0
    skipped = duration - sum(last - first for first, last in intervals)
    if skipped <= 0:
        return [path], 'no_coverage', 0.0, 0
    outputs = _materialize(path, intervals, offset)
    return outputs, 'energy_match', skipped, int(skipped * RATE * 2)


async def apply_safety_wal_coverage(
    uid: str,
    wav_paths: list[str],
    target_id: str | None,
    *,
    run_blocking: Callable[..., Awaitable[Any]],
    db_executor: Executor | None,
    storage_executor: Executor | None,
    job_ref: str,
    protected_paths: Collection[str] = (),
    capture_partition: dict[str, Any] | None = None,
) -> tuple[list[str], set[str]]:
    from database import conversations

    results, generated = [], set()
    reasons, skipped, saved = set(), 0.0, 0
    enabled = sync_safety_wal_enabled()
    for path in wav_paths:
        reason, seconds, size, outputs = 'disabled', 0.0, 0, [path]
        if path in protected_paths:
            reason = 's1_mapped'
        elif enabled:
            try:
                start = get_timestamp_from_path(path)
                duration = await run_blocking(storage_executor, get_wav_duration, path)
                row = (
                    await run_blocking(db_executor, conversations.get_conversation, uid, target_id)
                    if target_id
                    else await run_blocking(
                        db_executor, conversations.get_closest_conversation_to_timestamps, uid, start, start + duration
                    )
                )
                # A sync-only row cannot prove coverage from the live socket.
                from utils.sync.assignment import compatible_capture

                live = (
                    row
                    and not row.get('deleted')
                    and (row.get('sync_live_target') or not row.get('sync_content_revision'))
                    and (capture_partition is None or compatible_capture(row, capture_partition))
                )
                if live:
                    outputs, reason, seconds, size = await run_blocking(
                        storage_executor, cut_live_coverage, uid, row, path
                    )
                else:
                    reason = 'no_live_target'
            except Exception as exc:
                reason = 'lookup_or_cut_failed'
                logger.warning('event=sync_safety_wal_coverage_error exception_type=%s', type(exc).__name__)
                record_fallback(
                    component='sync_dispatch', from_mode='none', to_mode='none', reason='other', outcome='degraded'
                )
            if reason in ('unreliable_clock', 'unsupported_wav', 'fragmented_coverage'):
                record_fallback(
                    component='sync_dispatch', from_mode='none', to_mode='none', reason='other', outcome='degraded'
                )
        results.extend(outputs)
        generated.update(output for output in outputs if output != path)
        reasons.add(reason)
        skipped += seconds
        saved += size
        WAL_SECONDS_SKIPPED.labels(reason=reason).inc(seconds)
        AUDIO_BYTES_NOT_STORED.labels(reason=reason).inc(size)
    logger.info(
        'event=sync_safety_wal_coverage job_ref=%s enabled=%s reasons=%s skipped_seconds=%.3f audio_bytes_not_stored=%s inputs=%s outputs=%s',
        job_ref,
        enabled,
        ','.join(sorted(reasons)),
        skipped,
        saved,
        len(wav_paths),
        len(results),
    )
    return results, generated

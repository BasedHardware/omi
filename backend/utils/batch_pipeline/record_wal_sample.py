"""One time-boxed, counts-only alignment probe for native record uploads."""

import asyncio
from collections.abc import Mapping, Sequence
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
from struct import error as StructError
import threading
import time
from typing import Any

from cryptography.exceptions import InvalidTag
from google.api_core.exceptions import GoogleAPICallError
from prometheus_client import Counter as Metric

from config.audio_archive import derived_audio_bucket
from config.record_wal_sample import ATTEMPT_SECONDS, slot_at
from database import record_wal_sample as state
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.record_wal_handoff import HandoffConflict
from database.batch_pipeline_store import FirestoreStore
from utils import encryption
from utils.batch_pipeline.artifact_reads import ArtifactReadBudget, ArtifactReadLimit
from utils.batch_pipeline.record_wal_alignment import CLOCK_RATE, Packet, index_live, overlap, tick
from utils.executors import db_executor, run_blocking, storage_executor, sync_executor
from utils.other.audio_frame_table import MAX_MANIFEST_BYTES, media_name, validate_frames
from utils.other.audio_opus import opus_packet_samples
from utils.other.raw_audio import WAL_FORMAT, filename_provenance, wal_packets
from utils.other.storage import get_private_cloud_sync_bucket

MAX_WAL_BYTES = 8 * 1024 * 1024
MAX_MANIFEST_TOTAL = 16 * 1024 * 1024
MAX_PACKS = 6
MAX_FILES = 20
MAX_PACKETS = 50_000
_SHA256 = re.compile(r"[0-9a-f]{64}")

attempts = Metric('omi_record_wal_handoff_sample_attempts_total', 'One-time sampling attempts', ['outcome'])
totals = Metric(
    'omi_record_wal_handoff_sample_totals_total',
    'Aggregate classified WAL payload plus framing bytes, or Opus ticks at 48 kHz',
    ['dispatch', 'classification', 'unit'],
)
offsets = Metric('omi_record_wal_handoff_sample_clock_offsets_total', 'Files with proved offsets', ['bucket'])
io_work = Metric('omi_record_wal_handoff_sample_io_total', 'Issued bounded sampler work', ['unit'])

_slot_lock = threading.Lock()
_latest_attempted = -1


@dataclass
class SampleReads:
    deadline: ArtifactReadBudget
    issued: int = 0

    def timeout(self, ceiling: float) -> float:
        if self.issued >= 10:
            raise ArtifactReadLimit('WAL sample point-read limit')
        result = self.deadline.timeout(ceiling)
        self.issued += 1
        return result


def _try_process_slot(slot: int) -> bool:
    global _latest_attempted
    with _slot_lock:
        if slot <= _latest_attempted:
            return False
        # Never immediately retry even an indeterminate create response.
        _latest_attempted = slot
        return True


def read_staged_packets(
    paths: Sequence[str], budget: ArtifactReadBudget, *, descriptors=None
) -> list[tuple[str, int, list[Packet]]]:
    if not 0 < len(paths) <= MAX_FILES:
        raise ArtifactReadLimit('WAL sample file count')
    remaining = MAX_WAL_BYTES
    packet_count = 0
    files = []
    for path in map(Path, paths):
        budget.timeout(2)
        size = path.stat().st_size
        if not 0 < size <= remaining:
            raise ArtifactReadLimit('WAL sample staged bytes')
        remaining -= size
        info = filename_provenance(str(path))
        packets = []
        if info.get('format') == WAL_FORMAT and info.get('channels') == 1:
            try:
                with path.open('rb') as stream:
                    raw = stream.read(size)
                    observed_size = os.fstat(stream.fileno()).st_size
                if len(raw) != size or observed_size != size:
                    raise ValueError('WAL size changed during sampling')
                rate = info['sample_rate']
                if rate not in {8000, 12000, 16000, 24000, 48000}:
                    raise ValueError('unsupported sample geometry')
                cursor = tick(info['capture_start'])
                for packet in wal_packets(raw):
                    packet_count += 1
                    if packet_count > MAX_PACKETS:
                        raise ArtifactReadLimit('WAL sample packet count')
                    budget.timeout(2)
                    samples = opus_packet_samples(packet, rate)
                    if not 0 < samples <= rate * 120 // 1000:
                        raise ValueError('inconsistent WAL packet duration')
                    span = samples * CLOCK_RATE // rate
                    packets.append(Packet(hashlib.sha256(packet).hexdigest(), span, cursor, len(packet)))
                    cursor += span
                if descriptors is not None and packets:
                    frame_size = info.get('frame_size')
                    if (
                        info.get('codec') == 'opus'
                        and frame_size in {80, 160, 320, 480, 640, 960}
                        and all(packet.ticks * rate == frame_size * CLOCK_RATE for packet in packets)
                    ):
                        descriptors[path.name] = {
                            'name': path.name,
                            'sha256': hashlib.sha256(raw).hexdigest(),
                            'size': size,
                            'codec': 'opus',
                            'sample_rate': rate,
                            'channels': 1,
                            'frame_size': frame_size,
                            'capture_start': info['capture_start'],
                            'frame_count': len(packets),
                            'sample_count': frame_size * len(packets),
                        }
            except (OSError, ValueError):
                # A known-size unreadable file has ambiguous bytes but no
                # measured duration. Its valid siblings still contribute.
                packets.clear()
        files.append((path.name, size, packets))
    return files


def _first_page(bucket, prefix, page_size, budget):
    budget.begin()
    iterator = bucket.list_blobs(
        prefix=prefix,
        page_size=page_size,
        timeout=budget.timeout(2),
        retry=None,
    )
    return list(next(iterator.pages, ())), bool(iterator.next_page_token)


def _page(bucket, prefix, max_entries, budget):
    items, more = _first_page(bucket, prefix, max_entries + 1, budget)
    if more:
        raise ArtifactReadLimit('partial WAL sample inventory')
    if len(items) > max_entries:
        raise ArtifactReadLimit('WAL sample inventory object count')
    return items


def _has_chunks(bucket, prefix, budget):
    # This probe only certifies the empty set. Any object or continuation page
    # prevents a gap claim while preserving positive packet matches.
    try:
        items, more = _first_page(bucket, prefix, 1, budget)
    except GoogleAPICallError:
        return True
    return bool(items) or more


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _manifest(bucket, uid, cid, media, listed, budget):
    before = listed.metadata or {}
    live = media.metadata or {}
    if (
        not listed.name.startswith(f'audio-outbox/{uid}/{cid}/')
        or before.get('format') != 'audio-custody-manifest-v1'
        or before.get('conversation_id') != cid
        or before.get('encrypted') not in {'true', 'false'}
        or type(listed.size) is not int
        or not 0 < listed.size <= MAX_MANIFEST_BYTES
        or type(listed.generation) is not int
        or listed.generation <= 0
        or type(listed.metageneration) is not int
        or listed.metageneration <= 0
        or type(media.generation) is not int
        or media.generation <= 0
        or live.get('format') != WAL_FORMAT
        or not _is_sha256(live.get('sha256'))
        or live.get('codec') != 'opus'
        or live.get('source_layout') != 'mono'
        or live.get('encrypted') not in {'true', 'false'}
        or live.get('conversation_id') != cid
        or live.get('clock_source') != 'server_projected'
        or live.get('consent_state') != 'private_cloud_sync_enabled'
        or live.get('custody_schema') != 'audio_custody_v1'
    ):
        raise ValueError('missing canonical WAL sample evidence')
    budget.begin()
    budget.reserve(listed.size)
    blob = bucket.blob(listed.name)
    raw = blob.download_as_bytes(
        raw_download=True,
        if_generation_match=listed.generation,
        if_metageneration_match=listed.metageneration,
        timeout=budget.timeout(2),
        retry=None,
    )
    if len(raw) != listed.size:
        raise ValueError('manifest length changed')
    budget.received_bytes += len(raw)
    if before['encrypted'] == 'true':
        raw = encryption.decrypt_audio_file(raw, uid)
    if hashlib.sha256(raw).hexdigest() != before.get('sha256'):
        raise ValueError('manifest digest changed')
    manifest = json.loads(raw)
    if not isinstance(manifest, dict):
        raise ValueError('manifest must be a JSON object')
    if manifest.get('schema') != 'audio_custody_v1' or manifest['media'] != {
        'bucket': bucket.name,
        'path': media.name,
        'generation': str(media.generation),
        'sha256': live.get('sha256'),
    }:
        raise ValueError('manifest does not bind live generation')
    capture = manifest['capture']
    rate = int(capture['sample_rate'])
    if rate not in {8000, 12000, 16000, 24000, 48000} or rate != int(live['sample_rate']):
        raise ValueError('manifest does not bind capture geometry')
    if capture['format'] != WAL_FORMAT or int(capture['channels']) != 1 or int(live['channels']) != 1:
        raise ValueError('unsupported live capture geometry')
    frames = manifest['frames']
    validate_frames(frames, rate)
    result = []
    cursor = 0
    for frame in frames:
        budget.timeout(2)
        length = frame['bytes']
        digest = frame['sha256']
        if type(length) is not int or not 4 < length <= 65540 or not _is_sha256(digest):
            raise ValueError('invalid packet proof')
        if frame['byte_offset'] != cursor:
            raise ValueError('invalid packet offset')
        cursor += length
        if not 0 < frame['samples'] <= rate * 120 // 1000:
            raise ValueError('invalid frame duration')
        position = frame.get('source')
        source = (
            (position['capture_root'], position['clock_epoch'], position['source_frame'])
            if isinstance(position, dict)
            else None
        )
        result.append(Packet(digest, frame['samples'] * CLOCK_RATE // rate, tick(frame['start']), length - 4, source))
    if cursor + (32 if live['encrypted'] == 'true' else 0) != media.size:
        raise ValueError('manifest does not cover live object length')
    return result


def read_manifest_inventory(uid, cid, check_alternate_sources, budget, *, versions=None):
    bucket = get_private_cloud_sync_bucket()
    media = _page(bucket, f'raw-live/{uid}/{cid}/', MAX_PACKS, budget)
    if not media:
        return [], False
    manifests = _page(bucket, f'audio-outbox/{uid}/{cid}/', MAX_PACKS, budget)
    by_name = {}
    for manifest in manifests:
        name = manifest.name[len(f'audio-outbox/{uid}/') :].rsplit('/', 1)[0]
        if name in by_name:
            raise ValueError('conflicting live manifests')
        by_name[name] = manifest
    runs = []
    for item in media:
        manifest = by_name[media_name(item.name, uid)]
        run = _manifest(bucket, uid, cid, item, manifest, budget)
        runs.append(run)
        if versions is not None:
            versions.append((item, manifest, run))
    alternate = True
    if check_alternate_sources:
        prefix = f'chunks/{uid}/{cid}/'
        alternate = _has_chunks(bucket, prefix, budget)
        regional = derived_audio_bucket()
        if not alternate and regional and regional != bucket.name:
            alternate = _has_chunks(bucket.client.bucket(regional), prefix, budget)
    return sorted(runs, key=lambda run: run[0].start), not alternate


def _same_sealed_capture(row: Mapping[str, Any], current: Mapping[str, Any]) -> bool:
    fields = (
        'status',
        'record_audio_closed',
        'record_audio_partial',
        'record_upload_failed',
        'record_upload_revision',
        'record_upload_sessions',
        'finished_at',
        'record_wal_handoff_present',
    )
    return (
        row.get('status') == 'completed'
        and row.get('record_audio_closed') is True
        and not row.get('record_audio_partial')
        and not row.get('record_upload_failed')
        and not row.get('record_upload_sessions')
        and not row.get('record_wal_handoff_present')
        and bool(row.get('finished_at'))
        and all(row.get(key) == current.get(key) for key in fields)
    )


def _bracketed_candidates(
    claim: Mapping[str, Any] | None,
    wal: list[Packet],
    runs: list[list[Packet]],
    matches: dict[int, tuple[int, int]],
) -> set[int]:
    if not claim or claim['frame_count'] != len(wal) or claim.get('codec') != 'opus' or not matches:
        return set()
    track = (claim['capture_root'], claim['clock_epoch'])
    first = claim['source_frame_start']
    observed = set()
    for run in runs:
        for packet in run:
            if packet.source is None or packet.source[:2] != track:
                return set()
            ordinal = packet.source[2]
            if ordinal in observed:
                return set()
            observed.add(ordinal)
    for index, (run, position) in matches.items():
        if runs[run][position].source != (*track, first + index):
            return set()
    # Bracket within this exact stream. Exclude any live source at a nominally
    # absent position, including a different packet with that same ordinal.
    return {index for index in range(min(matches) + 1, max(matches)) if first + index not in observed}


def _offset_bucket(value: int) -> str:
    if value < -5 * CLOCK_RATE:
        return 'lt_minus_5s'
    if value < -CLOCK_RATE // 4:
        return 'minus_5s_to_minus_250ms'
    if value <= CLOCK_RATE // 4:
        return 'within_250ms'
    if value <= 5 * CLOCK_RATE:
        return '250ms_to_5s'
    return 'gt_5s'


def _count(
    files: list[tuple[str, int, list[Packet]]],
    runs: list[list[Packet]],
    claims: Mapping[str, dict[str, Any]],
    check_bracketed_candidates: bool,
    budget: ArtifactReadBudget,
) -> tuple[Counter[tuple[str, str]], Counter[str]]:
    result: Counter[tuple[str, str]] = Counter()
    clock: Counter[str] = Counter()
    placements = index_live(runs, budget.timeout)
    for name, size, wal in files:
        budget.timeout(2)
        if not wal:
            result['ambiguous', 'bytes'] += size
            result['ambiguous', 'unknown_duration_files'] += 1
            continue
        matches = overlap(wal, runs, placements, budget.timeout)
        bracketed = _bracketed_candidates(claims.get(name), wal, runs, matches) if check_bracketed_candidates else set()
        if matches:
            index = min(matches)
            run, position = matches[index]
            clock[_offset_bucket(runs[run][position].start - wal[index].start)] += 1
        for index, packet in enumerate(wal):
            if index in matches:
                classification = 'duplicate'
            elif index in bracketed:
                # Client ordinal claims bind only the matching anchors. There
                # is no authenticated source position for the intervening WAL
                # packets, so they remain ambiguous even in a sealed record.
                classification = 'ambiguous_bracketed'
            else:
                classification = 'ambiguous'
            result[classification, 'bytes'] += packet.size + 4
            result[classification, 'ticks'] += packet.ticks
    return result, clock


async def observe(
    *,
    store: FirestoreStore,
    uid: str,
    cid: str,
    source: str,
    device: str | None,
    paths: Sequence[str],
    content_id: str,
    claims: Mapping[str, dict[str, Any]],
    status_code: int,
    has_jobs: bool,
) -> None:
    slot = slot_at(time.time())
    if slot is None or not content_id or not device:
        return
    if int(hashlib.sha256(content_id.encode()).hexdigest()[:12], 16) % 1000:
        return
    if not _try_process_slot(slot):
        attempts.labels('local_slot_miss').inc()
        return
    dispatch = 'refused' if status_code == 503 else 'accepted' if status_code in {200, 202} else 'other'
    budget = ArtifactReadBudget(time.monotonic() + ATTEMPT_SECONDS, MAX_MANIFEST_TOTAL, 14)
    reads = SampleReads(budget)
    try:
        async with asyncio.timeout(ATTEMPT_SECONDS):
            if not await run_blocking(db_executor, state.claim_slot, store, slot, budget):
                attempts.labels('contested_slot').inc()
                return
            attempts.labels('claimed_slot').inc()
            generation, row = await run_blocking(
                db_executor, state.authority, store, uid, cid, source, device, budget, reads
            )
            try:
                layout = await run_blocking(sync_executor, read_staged_packets, paths, budget)
            except OSError:
                attempts.labels('unreadable_staged').inc()
                return
            candidate = not has_jobs and _same_sealed_capture(row, row)
            try:
                runs, no_alternate = await run_blocking(
                    storage_executor, read_manifest_inventory, uid, cid, candidate, budget
                )
            except (InvalidTag, StructError):
                attempts.labels('unreadable_manifest').inc()
                runs, no_alternate = [], False
            except (ValueError, KeyError, TypeError, GoogleAPICallError, ArtifactReadLimit):
                attempts.labels('unproven_inventory').inc()
                runs, no_alternate = [], False
            _, current = await run_blocking(
                db_executor,
                state.authority,
                store,
                uid,
                cid,
                source,
                device,
                budget,
                reads,
                expected_generation=generation,
            )
            result, clock = await run_blocking(
                sync_executor,
                _count,
                layout,
                runs,
                claims,
                no_alternate and _same_sealed_capture(row, current),
                budget,
            )
            for (classification, unit), value in result.items():
                totals.labels(dispatch, classification, unit).inc(value)
            for label, count in clock.items():
                offsets.labels(label).inc(count)
            attempts.labels('counted').inc()
    except (BatchPrivacyBlocked, HandoffConflict):
        attempts.labels('authority_refused').inc()
    except (ArtifactReadLimit, TimeoutError):
        attempts.labels('limit').inc()
    except Exception:
        # No content, IDs or SDK messages enter sampling telemetry.
        attempts.labels('unavailable').inc()
    finally:
        io_work.labels('point_reads').inc(reads.issued)
        io_work.labels('gcs_requests').inc(budget.objects)
        io_work.labels('remote_bytes').inc(budget.received_bytes)

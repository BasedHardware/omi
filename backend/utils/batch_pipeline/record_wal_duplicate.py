"""Prove whole native WAL files against immutable, admitted live slices."""

import asyncio
from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import struct
import threading
import time

from cryptography.exceptions import InvalidTag
from google.api_core.exceptions import GoogleAPICallError
from prometheus_client import Counter as Metric

from config.record_wal_duplicate import ARCHIVE_BUCKET, mode
from config.record_wal_sample import ATTEMPT_SECONDS
from database import record_wal_duplicate as ledger
from database.record_wal_handoff import identity
from database.record_wal_sample import claim_slot
from utils.batch_pipeline import record_wal_sample as sample
from utils.batch_pipeline.artifact_reads import ArtifactReadBudget, ArtifactReadLimit
from utils.batch_pipeline.record_wal_alignment import Packet, index_live, overlap
from utils.executors import db_executor, run_blocking, storage_executor, sync_executor
from utils.other.storage import get_private_cloud_sync_bucket

decisions = Metric(
    'omi_record_wal_handoff_duplicate_decisions_total', 'Whole-bundle proof decisions', ['mode', 'outcome']
)
files_seen = Metric(
    'omi_record_wal_handoff_duplicate_files_total', 'Whole files evaluated by duplicate proof', ['mode', 'outcome']
)
proof_io = Metric('omi_record_wal_handoff_duplicate_io_total', 'Duplicate settlement request work', ['mode', 'unit'])
shadow_checks = Metric(
    'omi_record_wal_handoff_duplicate_shadow_checks_total', 'Independent proof comparison', ['outcome']
)
_slot_lock = threading.Lock()
_last_slot = -1


@dataclass
class Inventory:
    runs: list[list[Packet]]
    covered: set[tuple[int, int]]
    versions: list
    capture_sessions: tuple[str | None, ...]
    fingerprints: tuple[str, ...] = ()


def _inventory(request, attestation, budget):
    bucket = get_private_cloud_sync_bucket()
    if attestation['bucket'] != ARCHIVE_BUCKET or bucket.name != ARCHIVE_BUCKET:
        raise ValueError('duplicate WAL bucket differs from attestation')
    versions: list = []
    runs, _ = sample.read_manifest_inventory(request.uid, request.cid, False, budget, versions=versions)
    ordered = sorted(versions, key=lambda item: item[2][0].start)
    slices = defaultdict(list)
    for entry in attestation['slices']:
        first = entry['first']
        slices[entry['path'], entry['generation']].append((first, first + entry['count']))
    covered = set()
    for index, (obj, _, run) in enumerate(ordered):
        if (obj.metadata or {}).get('sample_rate') != '16000':
            continue
        # At 16 kHz the admitted PCM offsets count the same samples as the
        # packet frame table. Other rate/trim conventions stay ineligible.
        offset = 0
        for pos, packet in enumerate(run):
            budget.timeout(2)
            if packet.ticks % 3:
                raise ValueError('nonintegral live source coordinate')
            end = offset + packet.ticks // 3
            if any(lo <= offset and end <= hi for lo, hi in slices[obj.name, obj.generation]):
                covered.add((index, pos))
            offset = end
    fingerprints = tuple(
        identity(
            [obj.name, obj.generation, obj.metageneration, manifest.name, manifest.generation, manifest.metageneration]
        )
        for obj, manifest, _ in ordered
    )
    capture_sessions = tuple((obj.metadata or {}).get('capture_session_id') for obj, _, _ in ordered)
    return Inventory(runs, covered, ordered, capture_sessions, fingerprints)


def _recheck(inventory, budget):
    bucket = get_private_cloud_sync_bucket()
    for media, manifest, _ in inventory.versions:
        for obj in (media, manifest):
            if type(obj.metageneration) is not int or obj.metageneration <= 0:
                raise ValueError('duplicate WAL metadata generation missing')
            budget.begin()
            bucket.blob(obj.name).reload(
                if_generation_match=obj.generation,
                if_metageneration_match=obj.metageneration,
                timeout=budget.timeout(2),
                retry=None,
            )


def _qualify(matches, wal, claim, data, source_counts):
    if len(matches) != len(wal) or not wal:
        return None
    positions = [matches[i] for i in range(len(wal))]
    root, epoch, first = (claim[key] for key in ('capture_root', 'clock_epoch', 'source_frame_start'))
    previous = None
    for offset, (run, pos) in enumerate(positions):
        packet = data.runs[run][pos]
        source = (root, epoch, first + offset)
        if (
            (run, pos) not in data.covered
            or packet.source != source
            or source_counts[source] != 1
            or packet.identity != wal[offset].identity
            or previous
            and abs(packet.start - (previous.start + previous.ticks)) > 96
        ):
            return None
        previous = packet
    packs = sorted({run for run, _ in positions})
    sessions = {data.capture_sessions[run] for run in packs}
    if len(sessions) != 1 or not next(iter(sessions)):
        return None
    versions = [data.fingerprints[run] for run in packs] if data.fingerprints else []
    return identity([root, epoch, first, len(wal), versions])


def _oracle(wal, claim, data, full_positions, source_counts, budget):
    # Independent of anchored indexing: enumerate exact contiguous packet
    # sequences from every possible occurrence of the first packet.
    sequence = [packet.identity for packet in wal]
    start_positions = full_positions.get(sequence[0], ())
    selected = None
    for start in start_positions:
        budget.timeout(2)
        if start + len(sequence) > len(full_positions.positions):
            continue
        candidate = {}
        for offset, packet_id in enumerate(sequence):
            if offset % 128 == 0:
                budget.timeout(2)
            run, pos = full_positions.positions[start + offset]
            if data.runs[run][pos].identity != packet_id:
                break
            candidate[offset] = (run, pos)
        else:
            if selected is not None:
                return None
            selected = candidate
    if selected is None:
        return None
    return _qualify(selected, wal, claim, data, source_counts)


class Positions(dict):
    def __init__(self, data):
        super().__init__()
        self.positions = []
        for run, packets in enumerate(data.runs):
            for pos, packet in enumerate(packets):
                self.setdefault(packet.identity, []).append(len(self.positions))
                self.positions.append((run, pos))


def _placements(layout, descriptors, claims, inventory, budget, shadow):
    runs = inventory.runs
    index = index_live(runs, budget.timeout)
    source_counts = Counter(packet.source for run in runs for packet in run if packet.source is not None)
    positions = Positions(inventory) if shadow else None
    results = []
    disagreements = False
    for name, _, wal in sorted(layout):
        entry, claim = descriptors[name], claims[name]
        if (
            entry['sample_rate'] != 16000
            or claim['rate_hz'] != entry['sample_rate']
            or claim['codec'] != 'opus'
            or claim['channel'] != 'mono'
            or claim['frame_count'] != len(wal)
        ):
            results.append(None)
            continue
        matches = overlap(wal, runs, index, budget.timeout)
        proved = _qualify(matches, wal, claim, inventory, source_counts)
        # An anchored refusal can conservatively hold real duplicates. The
        # Shadow checks each anchored positive with the independent oracle.
        # Active settlement uses the qualified anchored decision.
        if proved and positions is not None:
            disagreements |= proved != _oracle(wal, claim, inventory, positions, source_counts, budget)
        results.append(proved)
    return results, disagreements


def _request(uid, cid, source, device, content_id, session, claims):
    return ledger.Request(uid, cid, source, device, content_id, session, identity(claims) if claims else None)


def _budget():
    return ArtifactReadBudget(time.monotonic() + ATTEMPT_SECONDS, sample.MAX_MANIFEST_TOTAL, 20)


def _views(budget, current):
    limit = ledger.MAX_VIEW_READS + ledger.MAX_REDIRECT_READS if current == 'replay' else ledger.MAX_VIEW_READS
    finish_limit = ledger.MAX_SETTLEMENT_VIEW_READS if current == 'settle' else ledger.MAX_VIEW_READS
    return ledger.PointReads(budget, limit=limit, mode=current), ledger.PointReads(
        budget, limit=finish_limit, mode=current
    )


async def replay(store, uid, cid, source, device, content_id, session, claims):
    reads, _ = await run_blocking(sync_executor, _views, _budget(), 'replay')
    try:
        async with asyncio.timeout(ATTEMPT_SECONDS):
            request = await run_blocking(sync_executor, _request, uid, cid, source, device, content_id, session, claims)
            state = await run_blocking(db_executor, ledger.reconcile, store, reads, request)
        return state.reply if state and state.prior else None
    finally:
        proof_io.labels('replay', 'point_reads').inc(reads.issued)


def select(uid, content_id):
    current, slot = mode(uid, time.time())
    if current == 'shadow' and int(hashlib.sha256(content_id.encode()).hexdigest()[:12], 16) % 1000:
        return 'off', None
    return current, slot


def _claim_process(slot):
    global _last_slot
    with _slot_lock:
        if slot <= _last_slot:
            return False
        _last_slot = slot
        return True


async def evaluate(store, uid, cid, source, device, content_id, session, paths, claims, current, slot=None):
    """The shadow observes a refused reply. Only active mode can write an alias."""
    budget = _budget()
    prepare, finish = None, None
    outcome = 'hold'
    counted = False
    proof_started = False
    commit_fence = CommitFence() if current == 'settle' else None
    try:
        async with asyncio.timeout(ATTEMPT_SECONDS):
            prepare, finish = await run_blocking(sync_executor, _views, budget, current)
            if current == 'shadow':
                if slot is None or not _claim_process(slot):
                    return None
                proof_io.labels('shadow', 'slot_attempts').inc()
                if not await run_blocking(db_executor, claim_slot, store, slot, budget, duplicate_shadow=True):
                    return None
            proof_started = True
            counted = True
            files_seen.labels(current, 'evaluated').inc(len(paths))
            if not claims or len(claims) != len(paths):
                return None
            descriptors: dict = {}
            layout = await run_blocking(
                sync_executor, sample.read_staged_packets, paths, budget, descriptors=descriptors
            )
            if len(descriptors) != len(paths) or set(descriptors) != claims.keys() or len(layout) != len(paths):
                return None
            request = await run_blocking(sync_executor, _request, uid, cid, source, device, content_id, session, claims)
            entries = [descriptors[name] for name in sorted(descriptors)]
            before = await run_blocking(db_executor, ledger.reconcile, store, prepare, request, files=entries)
            if before is None:
                return None
            if before.prior:
                outcome = 'replay'
                return before.reply if current == 'settle' else None
            data = await run_blocking(storage_executor, _inventory, request, before.scope.source, budget)
            placements, disagree = await run_blocking(
                sync_executor, _placements, layout, descriptors, claims, data, budget, current == 'shadow'
            )
            files_seen.labels(current, 'covered').inc(sum(value is not None for value in placements))
            if current == 'shadow' and any(placements):
                shadow_checks.labels('disagree' if disagree else 'agree').inc()
            if disagree or any(value is None for value in placements):
                return None
            await run_blocking(storage_executor, _recheck, data, budget)
            if select(uid, content_id)[0] != current:
                return None
            settled = await run_blocking(
                db_executor,
                ledger.reconcile,
                store,
                finish,
                request,
                files=entries,
                expected=before.scope,
                placements=placements,
                commit=commit_fence is not None,
                before_commit=commit_fence.begin if commit_fence is not None else None,
            )
            if settled is None:
                return None
            if settled.prior:
                outcome = 'replay'
            else:
                outcome = 'settled' if current == 'settle' else 'would_settle'
                files_seen.labels(current, outcome).inc(len(paths))
                proof_io.labels(current, 'bundle_bytes').inc(sum(entry['size'] for entry in entries))
                if current == 'settle':
                    proof_io.labels(current, 'receipt_writes').inc(settled.receipt_writes)
                    proof_io.labels(current, 'donor_writes').inc(int(not settled.marked))
            return settled.reply if current == 'settle' else None
    except (ArtifactReadLimit, GoogleAPICallError, OSError, ValueError, KeyError, TypeError, InvalidTag, struct.error):
        outcome = 'unavailable'
        # Proof reads are optional to legacy coverage. An in-flight CAS may
        # already own the result, so only an exact retry can resolve its reply.
        if commit_fence is not None and not commit_fence.cancel():
            raise
        return None
    except Exception:
        outcome = 'unavailable'
        if current == 'settle':
            raise
        return None
    finally:
        if commit_fence is not None:
            commit_fence.cancel()
        if proof_started and prepare is not None and finish is not None:
            proof_io.labels(current, 'point_reads').inc(prepare.issued + finish.issued)
            proof_io.labels(current, 'gcs_requests').inc(budget.objects)
            proof_io.labels(current, 'manifest_bytes').inc(budget.received_bytes)
        if counted:
            decisions.labels(current, outcome).inc()


class CommitFence:
    """Serialize the RPC boundary with fallback after an executor wait ends."""

    def __init__(self):
        self._lock = threading.Lock()
        self._started = False
        self._cancelled = False

    def begin(self):
        with self._lock:
            if self._cancelled:
                raise ArtifactReadLimit('duplicate WAL commit cancelled before dispatch')
            self._started = True

    def cancel(self):
        with self._lock:
            if self._started:
                return False
            self._cancelled = True
            return True

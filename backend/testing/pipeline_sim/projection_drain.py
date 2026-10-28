"""Owner-chain projection throughput on virtual time (``projection-drain``).

Runs the **real** ``Projector`` walk, sweep and ``OwnerDrains`` scheduler over a
modelled result log for heavy catch-up owners, and reports projection rows per
minute per owner. Only the projection stage is modelled: persisted->ready
follow-ups, GPU and merge are out of scope.

Time model. Every store, GCS, Typesense and transaction call charges a fixed
latency (``LATENCY``, p50s from the 2026-10-20 run-14 diagnosis) to the lane that
made it. The walk's blocking step is one lane; a read-ahead or parallel lookup
submitted from it is its own lane, starting at submit time, and waiting on its
result moves the walk lane to that lane's end. So overlap is modelled, but not
Firestore hot-document contention or retries. Between steps, asyncio's virtual
loop interleaves owners at step granularity.

Modes:
- ``sweep_walk``: today. The sweep-shared 30 s walk, one serving tick per 20 s,
  every input read and both pre-check transactions on the chain, index inline.
- ``drain_only``: the owner drain with the cuts switched off (scheduling only).
- ``drain``: Phase 1. The owner drain, read-ahead, deferred index, no pre-checks.

Every mode must persist the same rows in the same chain order and make the same
assignment calls, candidate hints included; ``run`` reports both.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import Future
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import logging
import os
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from config.policy import ProjectionPolicy
from database import conversations as conversations_db
from database.batch_pipeline_projection import ProjectionBlocked, ProjectionReplay
from testing.pipeline_sim.clock import SIM_EPOCH, VirtualClock, run_virtual
from utils.batch_pipeline import audio, context, projection, projection_drain, projection_parts, projection_prefetch
from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem
from utils.batch_pipeline.scheduler import owner_key

# Seconds per call (p50, run 14 §1). Inline index grows with the canonical's
# cumulative donors, as run 14's index_ms did.
LATENCY = {
    'doc_read': 0.03,
    'successor_query': 0.05,
    'page_query': 0.1,
    'claim': 0.002,
    'check_transaction': 0.1,
    'load_result': 0.22,
    'fetch_audio': 0.25,
    'context': 0.05,
    'build': 0.05,
    'candidate': 0.1,
    'assignment_transaction': 0.305,
    'index_base': 0.085,
    'index_per_donor': 0.15,
}
SERVING_INTERVAL_SECONDS = 20.0
CAPTURE_SECONDS = 20.0
SESSION_ROWS = 10
SESSION_GAP_SECONDS = 150.0
CONTENT_ROWS = 10

MODES = {
    'sweep_walk': {
        'BATCH_PIPELINE_OWNER_DRAIN_ENABLED': 'false',
        'BATCH_PIPELINE_PROJECTION_PREFETCH': '0',
        'BATCH_PIPELINE_PROJECTION_INDEX_DEFERRED_ENABLED': 'false',
    },
    'drain_only': {
        'BATCH_PIPELINE_OWNER_DRAIN_ENABLED': 'true',
        'BATCH_PIPELINE_PROJECTION_PREFETCH': '0',
        'BATCH_PIPELINE_PROJECTION_INDEX_DEFERRED_ENABLED': 'false',
    },
    'drain': {
        'BATCH_PIPELINE_OWNER_DRAIN_ENABLED': 'true',
        'BATCH_PIPELINE_PROJECTION_PREFETCH': '4',
        'BATCH_PIPELINE_PROJECTION_INDEX_DEFERRED_ENABLED': 'true',
    },
}
FIXED_SWITCHES = {
    'BATCH_PIPELINE_SWEEP_OWNER_CHAIN_ENABLED': 'true',
    'BATCH_PIPELINE_PROJECTION_PENDING_PAGE_ENABLED': 'true',
    'BATCH_PIPELINE_PROJECTION_TIMING_ENABLED': 'false',
}


class Lanes:
    """Virtual time for the walk lane and the read-ahead lanes it submits."""

    def __init__(self, clock: VirtualClock):
        self.clock = clock
        self.stack: list[float] = []
        self.charges: dict[str, int] = {}

    def monotonic(self) -> float:
        return self.stack[-1] if self.stack else self.clock.now

    def spend(self, op: str, seconds: float | None = None) -> None:
        self.charges[op] = self.charges.get(op, 0) + 1
        if self.stack:
            self.stack[-1] += LATENCY[op] if seconds is None else seconds

    def lane(self, fn, *args, **kwargs) -> tuple[Any, BaseException | None, float]:
        """Run ``fn`` on a lane starting now; returns (result, error, end time)."""
        self.stack.append(self.monotonic())
        try:
            return fn(*args, **kwargs), None, self.stack[-1]
        except Exception as error:
            return None, error, self.stack[-1]
        finally:
            self.stack.pop()

    def wait_until(self, when: float) -> None:
        if self.stack:
            self.stack[-1] = max(self.stack[-1], when)

    def module(self) -> SimpleNamespace:
        return SimpleNamespace(time=self.monotonic, monotonic=self.monotonic, perf_counter=self.monotonic)


class LaneExecutor:
    """``Executor.submit`` that runs the task now on its own overlapping lane."""

    def __init__(self, lanes: Lanes):
        self.lanes = lanes

    def submit(self, fn, *args, **kwargs) -> Future:
        result, error, ready_at = self.lanes.lane(fn, *args, **kwargs)
        return LaneFuture(self.lanes, result, error, ready_at)


class LaneFuture(Future):
    def __init__(self, lanes, result, error, ready_at):
        super().__init__()
        self.lanes, self.ready_at = lanes, ready_at
        if error is not None:
            self.set_exception(error)
        else:
            self.set_result(result)

    def result(self, timeout=None):
        self.lanes.wait_until(self.ready_at)
        return super().result(timeout=0)


class Doc(SimpleNamespace):
    def get(self, **_):
        self.lanes.spend('doc_read')
        row = self.row()
        return SimpleNamespace(to_dict=lambda: dict(row) if row is not None else None)


class ChainLog:
    """Result log, owner watermarks and receipts, with ``ProjectionStore`` facades."""

    namespace = 'batch_pipeline_sim_projection'

    def __init__(self, lanes: Lanes):
        self.lanes = lanes
        self.results: dict[str, dict] = {}
        self.jobs: dict[str, dict] = {}
        self.bindings: dict[str, ProjectionBinding] = {}
        self.owners: dict[str, dict] = {}
        self.tails: dict[str, str | None] = {}
        self.committed = 0.0
        self.persist_order: list[str] = []
        self.client = None
        self.store = self
        self.policy_parts = {'projection': ProjectionPolicy(async_projection=True).to_dict()}

    def commit(self, owner: str, content: str, segment: str, siblings: list[str], capture_at: float) -> None:
        key = owner_key(owner)
        self.committed += 1
        self.results[segment] = {
            'owner_key': key,
            'segment_id': segment,
            'previous_segment_id': self.tails.get(key),
            'committed_at': self.committed,
            'projection_state': 'pending',
            'result': {'outcome': 'success', 'result_uri': f'gs://sim/{segment}.json'},
        }
        self.tails[key] = segment
        self.bindings[segment] = ProjectionBinding(owner, f'job-{content}', content, tuple(siblings))
        item = WorkItem(segment, owner, capture_at, f'gs://sim/{segment}.wav', CAPTURE_SECONDS, Priority.DEEP)
        self.jobs[segment] = {**asdict(item), 'requires_compute_admission': True, 'policy_parts': self.policy_parts}

    # --- FirestoreStore facade ------------------------------------------------
    def projection_page(self, limit=100, *, after=None, states=('pending', 'persisted', 'ready')):
        self.lanes.spend('page_query')
        rows = sorted(
            (row['committed_at'], sid) for sid, row in self.results.items() if row['projection_state'] in states
        )
        if after is not None:
            rows = [row for row in rows if row > after]
        page = rows[:limit]
        return [sid for _, sid in page], (page[-1] if len(page) == limit else None)

    def projection_successor(self, key, previous):
        self.lanes.spend('successor_query')
        matches = [
            sid
            for sid, row in self.results.items()
            if row['owner_key'] == key and row['previous_segment_id'] == previous
        ]
        return matches[0] if len(matches) == 1 else None

    # --- ProjectionStore facade -----------------------------------------------
    def ref(self, table, sid):
        return Doc(lanes=self.lanes, row=lambda: self.results.get(sid))

    def read(self, sid):
        self.lanes.spend('doc_read')
        self.lanes.spend('doc_read')
        return dict(self.jobs[sid]), dict(self.results[sid]), self.bindings[sid]

    def projection_watermark(self, key):
        self.lanes.spend('doc_read')
        return self.owners.get(key, {}).get('projection_watermark')

    def session(self, sid, binding, now, **_):
        return Session(self, sid, binding)

    def check(self, session):
        self.lanes.spend('check_transaction')
        session.prepare(None)


class Session:
    def __init__(self, log: ChainLog, sid: str, binding: ProjectionBinding):
        self.log, self.segment_id, self.binding = log, sid, binding
        self.policy = ProjectionPolicy(async_projection=True)

    def prepare(self, transaction):
        row = self.log.results[self.segment_id]
        if row.get('projection'):
            raise ProjectionReplay(row['projection'])
        if row['previous_segment_id'] != self.log.owners.get(row['owner_key'], {}).get('projection_watermark'):
            raise ProjectionBlocked('earlier committed projection must persist first')

    def validate_plan(self, transaction, planned):
        pass

    def persist(self, transaction, planned=None, **_):
        assigned = planned[0] if planned else {}
        receipt = {'state': 'persisted', 'conversation_id': assigned.get('id')}
        row = self.log.results[self.segment_id]
        row.update(projection=receipt, projection_state='persisted')
        self.log.owners.setdefault(row['owner_key'], {})['projection_watermark'] = self.segment_id
        self.log.persist_order.append(self.segment_id)
        return receipt

    def persist_empty(self, **_):
        self.log.lanes.spend('assignment_transaction')
        self.prepare(None)
        return self.persist(None)


class Conversations:
    """Modelled sync assignment: sessions of contiguous rows; bridges absorb a donor."""

    def __init__(self, lanes: Lanes, bridges: set[str]):
        self.lanes, self.bridges = lanes, bridges
        self.rows: dict[str, dict] = {}
        self.calls: list[tuple] = []
        self.index: dict[str, str] = {}
        self.index_ops = 0

    def live(self, uid):
        return [row for row in self.rows.values() if row['uid'] == uid and not row.get('deleted')]

    def closest(self, uid, start, end):
        self.lanes.spend('candidate')
        rows = [row for row in self.live(uid) if row['start'] - 120 <= end and start <= row['end'] + 120]
        return {'id': max(rows, key=lambda row: (row['end'], row['id']))['id']} if rows else None

    def assign(self, uid, incoming, *, candidate_id=None, before_assign, after_assign, defer_index=None, **_):
        self.lanes.spend('assignment_transaction')
        before_assign(None)
        start, end = incoming['started_at'].timestamp(), incoming['finished_at'].timestamp()
        near = [row for row in self.live(uid) if start <= row['end'] + 120 and row['start'] - 120 <= end]
        canonical = max(near, key=lambda row: (row['end'], row['id'])) if near else None
        absorbed = []
        if canonical is None:
            canonical = self.rows[incoming['id']] = {
                'id': incoming['id'],
                'uid': uid,
                'start': start,
                'end': end,
                'merged_from': [],
            }
        canonical['end'] = max(canonical['end'], end)
        if incoming['id'] in self.bridges:
            older = [row for row in self.live(uid) if row is not canonical]
            if older:
                donor = max(older, key=lambda row: (row['end'], row['id']))
                donor['deleted'] = True
                canonical['start'] = min(canonical['start'], donor['start'])
                canonical['merged_from'] = sorted({*canonical['merged_from'], *donor['merged_from'], donor['id']})
                absorbed = [donor['id']]
        planned = ({'id': canonical['id'], 'sync_merged_from': list(canonical['merged_from'])}, False, [])
        after_assign(None, planned)
        self.calls.append((incoming['id'], candidate_id, canonical['id'], tuple(absorbed)))
        if defer_index is not None:
            defer_index(uid, canonical['id'], sorted({*canonical['merged_from'], *absorbed}))
        else:
            self.lanes.spend(
                'index_base', LATENCY['index_base'] + LATENCY['index_per_donor'] * len(canonical['merged_from'])
            )
            self.converge(uid, [canonical['id']], canonical['merged_from'])
        return planned

    def converge(self, uid, conversation_ids, donor_ids):
        for donor in donor_ids:
            self.index.pop(donor, None)
            self.index_ops += 1
        for cid in conversation_ids:
            if cid not in donor_ids:
                row = self.rows[cid]
                if row.get('deleted'):
                    self.index.pop(cid, None)
                else:
                    self.index[cid] = f"{row['start']:.0f}-{row['end']:.0f}"
                self.index_ops += 1


@contextmanager
def _environment(values: dict[str, str]):
    saved = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def workload(log: ChainLog, owners: int, rows: int, bridge_every: int) -> tuple[dict[str, list[str]], set[str]]:
    chains: dict[str, list[str]] = {}
    bridges: set[str] = set()
    for o in range(owners):
        owner = f'sim-owner-{o + 1}'
        chains[owner] = []
    # Owners' backlogs interleave in the log the way a burst commits them.
    for n in range(rows):
        session, position = divmod(n, SESSION_ROWS)
        capture_at = SIM_EPOCH - 86400 + session * (SESSION_ROWS * CAPTURE_SECONDS + SESSION_GAP_SECONDS)
        capture_at += position * CAPTURE_SECONDS
        content = n // CONTENT_ROWS
        for owner in chains:
            sid = f'{owner}-s{n:05d}'
            siblings = [f'{owner}-s{m:05d}' for m in range(content * CONTENT_ROWS, (content + 1) * CONTENT_ROWS)]
            log.commit(
                owner,
                f'{owner}-c{content}',
                sid,
                siblings[: min(len(siblings), rows - content * CONTENT_ROWS)],
                capture_at,
            )
            chains[owner].append(sid)
            if position == 0 and session and bridge_every and session % bridge_every == 0:
                bridges.add(sid)
    return chains, bridges


def run(
    mode: str = 'drain', *, rows: int = 1200, owners: int = 1, bridge_every: int = 2, horizon_hours: float = 12
) -> dict:
    """One deterministic run (no randomness); rows/min per owner and order checks."""
    if mode not in MODES:
        raise ValueError(f'unknown mode {mode}')
    clock = VirtualClock()
    lanes = Lanes(clock)
    log = ChainLog(lanes)
    chains, bridges = workload(log, owners, rows, bridge_every)
    model = Conversations(lanes, bridges)
    lane_executor = LaneExecutor(lanes)
    payload = {
        'words': [{'word': 'sim', 'timestamp': [0.5, CAPTURE_SECONDS - 1.0]}],
        'audio_seconds': CAPTURE_SECONDS,
        'speech_seconds': CAPTURE_SECONDS - 2.0,
        'diarization': {'turns': []},
    }

    def load_result(item, uri):
        lanes.spend('load_result')
        return dict(payload)

    def fetch_audio(item):
        lanes.spend('fetch_audio')
        return b''

    def resolve(item, binding, manifest, client, *, projection_item=None, require_lineage_fence=False):
        lanes.spend('context')
        return context.ResolvedContext(binding.target_conversation_id)

    def build_incoming(item, binding, payload, **_):
        lanes.spend('build')
        return {
            'id': item.segment_id,
            'started_at': datetime.fromtimestamp(item.capture_at, timezone.utc),
            'finished_at': datetime.fromtimestamp(item.capture_at + payload['words'][-1]['timestamp'][1], timezone.utc),
            'transcript_segments': [{'speaker_id_scope': f'sync:{item.segment_id}'}],
        }

    held: set[str] = set()

    @contextmanager
    def claim(namespace, key):
        lanes.spend('claim')
        if key in held:
            yield False
            return
        held.add(key)
        try:
            yield True
        finally:
            held.discard(key)

    async def inline_blocking(executor, fn, *args, **kwargs):
        result, error, ended = lanes.lane(fn, *args, **kwargs)
        await asyncio.sleep(max(0.0, ended - clock.now))
        if error is not None:
            raise error
        return result

    projector = projection.Projector(log, load_result, fetch_audio=fetch_audio, clock=clock.time)
    projector.store = log
    projector.schedule_index_flush = lambda: lanes.lane(projector.index.flush)
    finished: dict[str, float] = {}
    started_at = clock.now

    def done(owner):
        return all(log.results[sid].get('projection') for sid in chains[owner])

    async def serve():
        loop = asyncio.get_running_loop()
        with patch.object(projection_drain, 'start_background_task', lambda coro, name: loop.create_task(coro)):
            while len(finished) < len(chains) and clock.now - started_at < horizon_hours * 3600:
                _, error, ended = lanes.lane(projector.sweep)
                if error is not None:
                    raise error
                await asyncio.sleep(max(0.0, ended - clock.now))
                if projector.owes_drains:
                    projector.start_drains()
                if projector.owes_index:
                    projector.schedule_index_flush()
                for owner in chains:
                    if owner not in finished and done(owner):
                        finished[owner] = clock.now
                # Drains keep running between ticks; poll owners each second.
                for _ in range(int(SERVING_INTERVAL_SECONDS)):
                    await asyncio.sleep(1.0)
                    for owner in chains:
                        if owner not in finished and done(owner):
                            finished[owner] = clock.now
                    if len(finished) == len(chains):
                        break

    patches = [
        patch.object(projection, 'time', lanes.module()),
        patch.object(projection_drain, 'time', lanes.module()),
        patch.object(projection_drain, 'run_blocking', inline_blocking),
        patch.object(projection, 'projection_claim', claim),
        patch.object(projection, 'build_incoming', build_incoming),
        patch.object(projection_parts, 'split_result', lambda item, payload: [(item, payload)]),
        patch.object(context, 'resolve_context', resolve),
        patch.object(audio, 'read_context', lambda body: {}),
        patch.object(projection_prefetch, 'storage_executor', lane_executor),
        patch('utils.executors.db_executor', lane_executor),
        patch.object(conversations_db, 'assign_sync_conversation', model.assign),
        patch.object(conversations_db, 'get_closest_conversation_to_timestamps', model.closest),
        patch.object(conversations_db, 'index_sync_assignment', model.converge),
    ]
    logging.disable(logging.CRITICAL)
    try:
        with _environment({**FIXED_SWITCHES, **MODES[mode]}):
            for active in patches:
                active.start()
            try:
                run_virtual(clock, serve)
                # The run stops when the last row persists; converge what the
                # cancelled drain's post-step flush still owed.
                projector.index.flush()
            finally:
                for active in reversed(patches):
                    active.stop()
    finally:
        logging.disable(logging.NOTSET)
    per_owner = {
        owner: {
            'rows': len(chain),
            'drain_seconds': round(finished[owner] - started_at, 1) if owner in finished else None,
            'rows_per_min': round(len(chain) * 60 / (finished[owner] - started_at), 1) if owner in finished else 0.0,
        }
        for owner, chain in chains.items()
    }
    order_ok = True
    for chain in chains.values():
        members = set(chain)
        persisted = [sid for sid in log.persist_order if sid in members]
        order_ok = order_ok and persisted == chain[: len(persisted)]
    return {
        'mode': mode,
        'rows_per_owner': rows,
        'owners': owners,
        'all_persisted': len(finished) == len(chains),
        'chain_order': order_ok and len(set(log.persist_order)) == len(log.persist_order),
        'rows_per_min_min': min(entry['rows_per_min'] for entry in per_owner.values()),
        'rows_per_min_max': max(entry['rows_per_min'] for entry in per_owner.values()),
        'per_owner': per_owner,
        'assignments': model.calls,
        'index': dict(model.index),
        'check_transactions': lanes.charges.get('check_transaction', 0),
        'result_loads': lanes.charges.get('load_result', 0),
    }

"""Ordered conversation driver (DESIGN L1 M1, L3, stage list notes -> notifications).

For each conversation of the day, in production finalization order:

1. set the lab clock to its production finalization instant;
2. seed the pre-finalization row (stored transcript, derived fields removed);
3. run the **real** durable finalization path, un-stubbed: create the finalization
   intent, claim the lease, ``finalize_persisted_conversation`` (which runs
   ``process_conversation``: discard, notes, folder, apps, vectors, memories, action
   items + pushes, goals, webhooks) and mark the job completed - the same sequence
   ``testing/lifecycle_sim`` drives;
4. wait for fire-and-forget work to drain (executor barrier + event-loop tasks).

Steps 1-4 are serial: memories, tasks, goals and dedup read what earlier
conversations wrote. After the whole day, each conversation is exported to the
store contract JSON with K-way fan-out (order-independent reads only).

The store and finalizer are small protocols so the driver is unit-testable with
fakes; :class:`ProductChainStore` and :class:`ProductFinalizer` are the real ones.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
import time
from typing import Any, Iterable, Mapping, Protocol, Sequence

from testing.pipeline_lab.chain.barrier import ExecutorBarrier, drain_event_loop
from testing.pipeline_lab.chain.export import normalize_conversation
from testing.pipeline_lab.chain.order import ChainItem, pre_finalization_row
from testing.pipeline_lab.sinks.capture import CaptureSinks, capture_scope
from testing.pipeline_lab.stack.clock import LabClock, real_now
from testing.pipeline_lab.stack.io import iso, parse_time, read_jsonl, write_json


class ChainStore(Protocol):
    def seed_conversation(self, uid: str, row: Mapping[str, Any]) -> None: ...

    def read_conversation(self, uid: str, conversation_id: str) -> dict[str, Any] | None: ...

    def action_items_for(self, uid: str, conversation_id: str) -> list[dict[str, Any]]: ...

    def memories_for(self, uid: str, conversation_id: str) -> list[dict[str, Any]]: ...

    def people_names(self, uid: str) -> dict[str, str]: ...


class Finalizer(Protocol):
    async def finalize(self, uid: str, conversation_id: str, language: str | None) -> str: ...


@dataclass
class ConversationRun:
    conversation_id: str
    instant: str
    instant_source: str
    lane: str
    status: str = 'pending'
    disposition: str | None = None
    error: str | None = None
    seconds: float = 0.0
    barrier_seconds: float = 0.0
    background_tasks: int = 0
    background_failures: int = 0
    loop_tasks_left: int = 0
    window: tuple[str, str] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class ChainReport:
    conversations: list[ConversationRun] = field(default_factory=list)
    exported: int = 0
    seconds: float = 0.0
    export_seconds: float = 0.0
    warnings: list[str] = field(default_factory=list)

    def stage_summary(self) -> dict[str, Any]:
        failed = sum(1 for c in self.conversations if c.status == 'failed')
        return {
            'status': 'failed' if failed and failed == len(self.conversations) else ('partial' if failed else 'ok'),
            'conversations': len(self.conversations),
            'failed': failed,
            'exported': self.exported,
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            'summary': self.stage_summary(),
            'seconds': self.seconds,
            'export_seconds': self.export_seconds,
            'warnings': self.warnings,
            'conversations': [c.as_dict() for c in self.conversations],
        }


def llm_call_ids_by_conversation(
    llm_calls_path: Path | None, windows: Mapping[str, tuple[str, str]] | None = None
) -> dict[str, list[str]]:
    """Attribute proxy calls to conversations: by the tagged conversation id, else by time window.

    The window fallback is exact only because the ordered path is serial.
    """
    out: dict[str, list[str]] = {}
    if llm_calls_path is None or not Path(llm_calls_path).exists():
        return out
    parsed_windows = {cid: (parse_time(start), parse_time(end)) for cid, (start, end) in (windows or {}).items()}
    for row in read_jsonl(llm_calls_path):
        call_id = row.get('id')
        if not call_id:
            continue
        cid = row.get('conversation_id')
        if not cid:
            at = parse_time(row.get('at'))
            if at is None:
                continue
            cid = next((c for c, (start, end) in parsed_windows.items() if start and end and start <= at <= end), None)
        if cid:
            out.setdefault(cid, []).append(str(call_id))
    return out


class ChainDriver:
    def __init__(
        self,
        *,
        uid: str,
        store: ChainStore,
        finalizer: Finalizer,
        clock: LabClock | None,
        barrier: ExecutorBarrier,
        sinks: CaptureSinks,
        run_dir: Path | None = None,
        llm_calls_path: Path | None = None,
        export_workers: int = 4,
        barrier_timeout: float = 300.0,
        loop_drain_timeout: float = 60.0,
        stop_on_error: bool = False,
    ):
        self.uid = uid
        self.store = store
        self.finalizer = finalizer
        self.clock = clock
        self.barrier = barrier
        self.sinks = sinks
        self.run_dir = Path(run_dir) if run_dir is not None else None
        self.llm_calls_path = llm_calls_path or (self.run_dir / 'llm_calls.jsonl' if self.run_dir else None)
        self.export_workers = max(1, export_workers)
        self.barrier_timeout = barrier_timeout
        self.loop_drain_timeout = loop_drain_timeout
        self.stop_on_error = stop_on_error

    async def _one(self, item: ChainItem) -> ConversationRun:
        run = ConversationRun(item.conversation_id, iso(item.instant), item.instant_source, item.lane)
        started = time.monotonic()
        window_start = real_now()
        if self.clock is not None:
            self.clock.set(item.instant)
        submitted_before = self.barrier.submitted
        failed_before = self.barrier.failed
        try:
            with capture_scope(item.conversation_id, 'finalize'):
                row = pre_finalization_row(item.row)
                await asyncio.to_thread(self.store.seed_conversation, self.uid, row)
                disposition = await self.finalizer.finalize(self.uid, item.conversation_id, row.get('language'))
                run.disposition = str(getattr(disposition, 'value', disposition))
                drained, left = await drain_event_loop(self.loop_drain_timeout)
                barrier_started = time.monotonic()
                await asyncio.to_thread(self.barrier.wait, self.barrier_timeout)
                drained2, left = await drain_event_loop(self.loop_drain_timeout)
                run.barrier_seconds = time.monotonic() - barrier_started
                run.loop_tasks_left = left
            run.status = 'ok'
        except Exception as error:  # noqa: BLE001 - one bad conversation must not hide the rest
            run.status = 'failed'
            run.error = type(error).__name__
        run.background_tasks = self.barrier.submitted - submitted_before
        run.background_failures = self.barrier.failed - failed_before
        run.seconds = time.monotonic() - started
        run.window = (iso(window_start), iso(real_now()))
        return run

    def _export_one(self, run: ConversationRun, people: Mapping[str, str], call_ids: Mapping[str, list[str]]) -> bool:
        row = self.store.read_conversation(self.uid, run.conversation_id)
        if row is None:
            return False
        payload = normalize_conversation(
            row,
            action_items=self.store.action_items_for(self.uid, run.conversation_id),
            memories=self.store.memories_for(self.uid, run.conversation_id),
            notifications=self.sinks.notifications_for(run.conversation_id),
            llm_call_ids=call_ids.get(run.conversation_id, []),
            lane=run.lane,
            # M1 replays production's own capture ids, so the baseline id is the id.
            baseline_id=run.conversation_id,
            people=people,
        )
        payload['replay'] = {
            'status': run.status,
            'disposition': run.disposition,
            'error': run.error,
            'instant': run.instant,
            'instant_source': run.instant_source,
        }
        if self.run_dir is not None:
            write_json(self.run_dir / 'conversations' / f'{run.conversation_id}.json', payload)
        return True

    def export(self, report: ChainReport) -> int:
        started = time.monotonic()
        people = self.store.people_names(self.uid)
        windows = {c.conversation_id: c.window for c in report.conversations if c.window}
        call_ids = llm_call_ids_by_conversation(self.llm_calls_path, windows)
        with ThreadPoolExecutor(max_workers=self.export_workers, thread_name_prefix='lab-export') as pool:
            results = list(pool.map(lambda run: self._export_one(run, people, call_ids), report.conversations))
        report.exported = sum(1 for ok in results if ok)
        report.export_seconds = time.monotonic() - started
        return report.exported

    async def run(self, items: Sequence[ChainItem]) -> ChainReport:
        report = ChainReport()
        started = time.monotonic()
        for item in items:
            run = await self._one(item)
            report.conversations.append(run)
            if run.loop_tasks_left:
                report.warnings.append(f'{item.conversation_id}: {run.loop_tasks_left} event-loop tasks still running')
            if run.status == 'failed':
                report.warnings.append(f'{item.conversation_id}: finalization failed ({run.error})')
                if self.stop_on_error:
                    break
        report.seconds = time.monotonic() - started
        await asyncio.to_thread(self.export, report)
        if self.run_dir is not None:
            write_json(self.run_dir / 'chain.json', report.as_dict())
        return report


class ProductChainStore:
    """Reads and writes through ``database.*`` helpers (needs the lab environment)."""

    def seed_conversation(self, uid: str, row: Mapping[str, Any]) -> None:
        from database import conversations as conversations_db
        from testing.pipeline_lab.seed.writer import assert_lab_target, restore_times

        assert_lab_target(uid)
        conversations_db.upsert_conversation_with_lifecycle(uid, restore_times(dict(row)))

    def read_conversation(self, uid: str, conversation_id: str) -> dict[str, Any] | None:
        from database import conversations as conversations_db
        from testing.pipeline_lab.stack.io import plain

        row = conversations_db.get_conversation(uid, conversation_id)
        return plain(row) if row else None

    def action_items_for(self, uid: str, conversation_id: str) -> list[dict[str, Any]]:
        from database import action_items as action_items_db
        from testing.pipeline_lab.stack.io import plain

        return plain(action_items_db.get_action_items_by_conversation(uid, conversation_id))

    def memories_for(self, uid: str, conversation_id: str) -> list[dict[str, Any]]:
        from google.cloud.firestore_v1 import FieldFilter

        from database import memories as memories_db
        from database._client import get_firestore_client
        from testing.pipeline_lab.stack.io import plain

        ids = set(memories_db.get_memory_ids_for_conversation(uid, conversation_id))
        collection = get_firestore_client().collection('users').document(uid).collection('memories')
        ids.update(
            doc.id for doc in collection.where(filter=FieldFilter('conversation_id', '==', conversation_id)).stream()
        )
        if not ids:
            return []
        return plain(memories_db.get_memories_by_ids(uid, sorted(ids)))

    def people_names(self, uid: str) -> dict[str, str]:
        from database import users as users_db

        return {str(p.get('id')): str(p.get('name') or '') for p in users_db.get_people(uid) or [] if p.get('id')}


class ProductFinalizer:
    """The durable finalization sequence, as ``testing/lifecycle_sim/harness.py`` drives it."""

    def __init__(self, firestore_client: Any = None):
        self.firestore_client = firestore_client

    async def finalize(self, uid: str, conversation_id: str, language: str | None) -> str:
        from database import conversation_finalization_jobs as jobs
        from utils.conversations import finalizer, lifecycle

        intent = await asyncio.to_thread(
            jobs.create_or_get_finalization_intent,
            uid,
            conversation_id,
            requires_byok=False,
            finalization_admission=lambda row: lifecycle._finalization_admission(row, conversation_id),
            firestore_client=self.firestore_client,
        )
        if not intent.get('job_id'):
            return f'not_admitted:{intent.get("status")}'
        generation = intent['dispatch_generation']
        claim = await asyncio.to_thread(
            jobs.claim_finalization_job, intent['job_id'], generation, firestore_client=self.firestore_client
        )
        if claim.get('status') != 'claimed':
            return f'not_claimed:{claim.get("status")}'
        epoch = claim['lease_epoch']
        disposition = await finalizer.finalize_persisted_conversation(
            uid,
            conversation_id,
            language,
            finalization_job_id=intent['job_id'],
            dispatch_generation=generation,
            lease_epoch=epoch,
        )
        if disposition is finalizer.ConversationFinalizationDisposition.completed:
            await asyncio.to_thread(
                jobs.mark_finalization_completed,
                intent['job_id'],
                generation,
                epoch,
                firestore_client=self.firestore_client,
            )
        return disposition.value


def chain_items_from(rows: Iterable[Mapping[str, Any]]) -> list[ChainItem]:
    from testing.pipeline_lab.chain.order import plan_chain

    return plan_chain(rows)

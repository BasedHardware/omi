"""Pipeline lab, lane chain: ordering, frozen instants, executor barrier, export contract."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
import json
import time

import pytest

from testing.pipeline_lab.chain.barrier import BarrierTimeout, ExecutorBarrier
from testing.pipeline_lab.chain.driver import ChainDriver, llm_call_ids_by_conversation
from testing.pipeline_lab.chain.export import normalize_conversation
from testing.pipeline_lab.chain.order import finalization_instant, plan_chain, pre_finalization_row
from testing.pipeline_lab.seed.synthetic import make_conversation
from testing.pipeline_lab.sinks.capture import CaptureSinks
from testing.pipeline_lab.stack.clock import LabClock
from testing.pipeline_lab.stack.io import append_jsonl

UID = 'local-dev-user'
DAY = datetime(2026, 3, 14, tzinfo=timezone.utc)

CONVERSATION_KEYS = {
    'id',
    'baseline_id',
    'lane',
    'started_at',
    'finished_at',
    'discarded',
    'discard_reason',
    'language',
    'segments',
    'structured',
    'action_items',
    'memories',
    'notifications',
    'llm_call_ids',
    'evaluable',
}


def test_finalization_instant_prefers_production_notes_time():
    row = {'notes_written_at': '2026-03-14T09:13:00Z', 'finished_at': '2026-03-14T09:12:00Z'}
    assert finalization_instant(row) == (datetime(2026, 3, 14, 9, 13, tzinfo=timezone.utc), 'notes_written_at')
    instant, source = finalization_instant({'finished_at': '2026-03-14T09:12:00Z'})
    assert source == 'finished_at+lag' and instant == datetime(2026, 3, 14, 9, 13, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        finalization_instant({})


def test_plan_orders_by_instant_not_input_order():
    rows = [make_conversation(UID, i, DAY + timedelta(hours=h)) for i, h in ((0, 15), (1, 9), (2, 12))]
    rows[2]['notes_written_at'] = (DAY + timedelta(hours=8)).isoformat()  # finalized before the others
    assert [item.conversation_id for item in plan_chain(rows)] == ['conv-002', 'conv-001', 'conv-000']


def test_pre_finalization_row_keeps_capture_facts_only():
    row = make_conversation(UID, 0, DAY)
    row.update({'apps_results': [{'x': 1}], 'finalization_revision': 3, 'folder_id': 'f'})
    fresh = pre_finalization_row(row)
    assert fresh['status'] == 'in_progress' and fresh['discarded'] is False and fresh['structured'] == {}
    assert fresh['transcript_segments'] == row['transcript_segments']
    for derived in ('apps_results', 'finalization_revision', 'folder_id', 'notes_llm_input_hash', 'record_lane_owner'):
        assert derived not in fresh


def test_barrier_waits_for_nested_background_work():
    pool = ThreadPoolExecutor(max_workers=2)
    barrier = ExecutorBarrier()
    done = []
    with ExitStack() as stack:
        barrier.instrument(stack, pool)

        def child():
            time.sleep(0.05)
            done.append('child')

        def parent():
            time.sleep(0.05)
            pool.submit(child)
            done.append('parent')

        pool.submit(parent)
        barrier.wait(timeout=5)
        assert done == ['parent', 'child'] and barrier.submitted == 2
        pool.submit(lambda: time.sleep(1))
        with pytest.raises(BarrierTimeout):
            barrier.wait(timeout=0.1)
    assert 'submit' not in vars(pool)  # instance wrapper removed
    pool.shutdown(wait=True)


class FakeStore:
    def __init__(self):
        self.rows = {}
        self.tasks = {}
        self.memories = {}

    def seed_conversation(self, uid, row):
        self.rows[row['id']] = dict(row)

    def read_conversation(self, uid, cid):
        return self.rows.get(cid)

    def action_items_for(self, uid, cid):
        return self.tasks.get(cid, [])

    def memories_for(self, uid, cid):
        return self.memories.get(cid, [])

    def people_names(self, uid):
        return {}


class FakeFinalizer:
    """Stands in for the product path: reads the clock, writes later, pushes, fails on demand."""

    def __init__(self, store, clock, pool, sinks, fail=()):
        self.store, self.clock, self.pool, self.sinks, self.fail = store, clock, pool, sinks, set(fail)
        self.seen = []

    async def finalize(self, uid, cid, language):
        self.seen.append((cid, self.clock.now(), sorted(self.store.tasks)))
        if cid in self.fail:
            raise RuntimeError('synthetic failure')
        row = self.store.rows[cid]

        def background():
            time.sleep(0.05)  # the driver must wait for this before the next conversation
            self.store.tasks[cid] = [{'description': f'task for {cid}', 'completed': False}]
            self.sinks.record_messages([{'token': 'pipeline-lab-x', 'data': {'title': f'push {cid}'}}], api='test')

        self.pool.submit(background)
        row.update(status='completed', structured={'title': f'title {cid}', 'overview': 'o'})
        return 'completed'


def _driver(tmp_path, fail=()):
    clock = LabClock(DAY, tick=False)
    store = FakeStore()
    sinks = CaptureSinks(run_dir=tmp_path, clock=clock.now)
    pool = ThreadPoolExecutor(max_workers=2)
    barrier = ExecutorBarrier()
    stack = ExitStack()
    barrier.instrument(stack, pool)
    finalizer = FakeFinalizer(store, clock, pool, sinks, fail)
    driver = ChainDriver(
        uid=UID, store=store, finalizer=finalizer, clock=clock, barrier=barrier, sinks=sinks, run_dir=tmp_path
    )
    return driver, finalizer, store, stack, pool


def test_driver_runs_in_order_at_production_instants_and_exports_contract(tmp_path):
    driver, finalizer, store, stack, pool = _driver(tmp_path)
    rows = [make_conversation(UID, i, DAY + timedelta(hours=9 + i)) for i in range(3)]
    append_jsonl(tmp_path / 'llm_calls.jsonl', {'id': 'call-1', 'conversation_id': 'conv-001', 'at': 'x'})
    with stack:
        report = asyncio.run(driver.run(plan_chain(rows)))
    pool.shutdown()
    assert [c for c, _, _ in finalizer.seen] == ['conv-000', 'conv-001', 'conv-002']
    for (cid, at, tasks_before), row in zip(finalizer.seen, rows):
        assert at == datetime.fromisoformat(row['notes_written_at'])
    # Each conversation saw every earlier conversation's drained background writes.
    assert [tasks for _, _, tasks in finalizer.seen] == [[], ['conv-000'], ['conv-000', 'conv-001']]
    assert report.stage_summary() == {'status': 'ok', 'conversations': 3, 'failed': 0, 'exported': 3}
    exported = json.loads((tmp_path / 'conversations' / 'conv-001.json').read_text())
    assert CONVERSATION_KEYS <= set(exported)
    assert exported['structured']['title'] == 'title conv-001'
    assert exported['action_items'][0]['description'] == 'task for conv-001'
    assert [n['title'] for n in exported['notifications']] == ['push conv-001']
    assert exported['llm_call_ids'] == ['call-1']
    assert exported['evaluable'] == {'boundaries': False, 'reason': 'stored_transcript_boundaries'}
    assert exported['replay']['instant_source'] == 'notes_written_at'
    assert json.loads((tmp_path / 'chain.json').read_text())['summary']['exported'] == 3


def test_one_failing_conversation_does_not_stop_the_day(tmp_path):
    driver, finalizer, store, stack, pool = _driver(tmp_path, fail={'conv-001'})
    rows = [make_conversation(UID, i, DAY + timedelta(hours=9 + i)) for i in range(3)]
    with stack:
        report = asyncio.run(driver.run(plan_chain(rows)))
    pool.shutdown()
    assert [c.status for c in report.conversations] == ['ok', 'failed', 'ok']
    assert report.conversations[1].error == 'RuntimeError'
    assert report.stage_summary()['status'] == 'partial'
    assert any('conv-001' in warning for warning in report.warnings)


def test_llm_calls_fall_back_to_the_serial_time_window(tmp_path):
    path = tmp_path / 'llm_calls.jsonl'
    append_jsonl(path, {'id': 'a', 'at': '2026-03-14T10:00:05Z'})
    append_jsonl(path, {'id': 'b', 'at': '2026-03-14T10:00:15Z', 'conversation_id': 'tagged'})
    append_jsonl(path, {'id': 'c', 'at': '2026-03-14T11:00:00Z'})
    windows = {'c1': ('2026-03-14T10:00:00Z', '2026-03-14T10:00:10Z')}
    assert llm_call_ids_by_conversation(path, windows) == {'c1': ['a'], 'tagged': ['b']}


def test_normalize_conversation_shape_and_stable_keys():
    row = make_conversation(UID, 0, DAY, discarded=True)
    row['relevance_decision'] = {'reason': 'too_short'}
    first = normalize_conversation(row, memories=[{'content': 'Likes  tomatoes', 'category': 'x'}])
    second = normalize_conversation(row, memories=[{'content': 'likes tomatoes', 'category': 'x'}])
    assert set(first) == CONVERSATION_KEYS
    assert first['discarded'] is True and first['discard_reason'] == 'too_short'
    assert first['memories'][0]['key'] == second['memories'][0]['key']
    assert first['action_items'][0]['description'] == 'Order heirloom tomato seeds'
    assert {'start', 'end', 'speaker', 'speaker_name', 'is_user', 'text'} == set(first['segments'][0])
    assert first['segments'][0]['speaker_name'] == 'You'

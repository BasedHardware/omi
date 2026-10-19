"""Two GPU replicas over one serializable store: scheduling, not compute, limits.

``MemoryStore`` runs every transaction under one global lock, which is stricter
than Firestore. If two pumps still drain independent owners about twice as
fast as one, no pull, merge or recovery step assumes a single worker.
Correctness under real Firestore transactions is covered by
``tests/integration/test_batch_pipeline_two_workers_firestore.py``.
"""

from collections import Counter

from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401

import pytest

from tests.support.batch_two_workers import FakeGpu, Recorder, build_pump, item, run_pumps
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from utils.batch_pipeline.scheduler import Scheduler, owner_key


@pytest.fixture(autouse=True)
def prod_worker_flags(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_HEAD_PRIORITY_ENABLED', 'true')
    monkeypatch.delenv('STT_CAP_DISPATCH_ENABLED', raising=False)
    monkeypatch.delenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', raising=False)


def drain(workers, *, owners=8, per_owner=2, batch_size=2, gpu_seconds=0.5):
    store = MemoryStore()
    admit = Scheduler(store)
    expected = set()
    for n in range(owners):
        for k in range(per_owner):
            segment = f'owner-{n}-{k}'
            expected.add(segment)
            assert admit.enqueue(item(segment, f'owner-{n}', k + 1), 0)
    recorder = Recorder()
    pumps = [
        build_pump(
            f'worker-{n}', store, recorder, FakeGpu(f'worker-{n}', recorder.gpu, seconds=gpu_seconds), batch_size
        )
        for n in range(workers)
    ]

    def drained():
        with recorder.lock:
            return {seg for _, seg in recorder.committed} >= expected

    elapsed = run_pumps(pumps, drained, timeout=60)
    assert recorder.accepted == Counter({seg: 1 for seg in expected})
    assert Counter(seg for _, seg in recorder.committed) == Counter({seg: 1 for seg in expected})
    assert Counter(seg for _, seg in recorder.gpu) == Counter({seg: 1 for seg in expected})
    return elapsed, store, recorder


def test_two_workers_roughly_double_independent_owner_throughput():
    one, _, _ = drain(1)
    two, store, recorder = drain(2)
    speedup = one / two
    print(f'two-worker drain: one={one:.2f}s two={two:.2f}s speedup={speedup:.2f}x')
    assert {name for name, _ in recorder.gpu} == {'worker-0', 'worker-1'}
    assert speedup >= 1.6, f'two workers drained only {speedup:.2f}x faster ({one:.2f}s vs {two:.2f}s)'
    for n in range(8):
        owner = owner_key(f'owner-{n}')
        chain = sorted(
            (v for (table, _), v in store.rows.items() if table == 'results' and v['owner_key'] == owner),
            key=lambda v: v['log_sequence'],
        )
        assert [v['segment_id'] for v in chain] == [f'owner-{n}-0', f'owner-{n}-1']
        assert [v['previous_segment_id'] for v in chain] == [None, f'owner-{n}-0']

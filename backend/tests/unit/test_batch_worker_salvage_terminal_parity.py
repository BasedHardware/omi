"""Terminal parity for salvaged evidence across the ladder and the scheduler.

A salvaged unit rides the pump as an ordinary ``FailedWork`` whose evidence is
the unit's cursor stage with the closed ``unknown`` reason. These pins drive
the real pump publication and the real lease-fenced ladder on a memory store
and fail when the eventual terminal quarantine does not name the cursor stage
(``stage=<cursor> worker_reason=unknown``, never the anonymous
``stage=unknown worker_reason=unclassified``), when the escape evidence
demotes onto a designed-handoff channel, or when the evidence does not survive
evidence-less attempts to the ceiling.

Failure-Class: FC-worker-flight-escape-voids-settled-and-held-units-into-anonymous-quarantine
"""

import logging
import time
from unittest.mock import Mock

import pytest

from utils.batch_pipeline.contracts import FailedWork, HeldWork, WorkResult
from utils.batch_pipeline.pump import Pump
from utils.batch_pipeline.scheduler import Scheduler
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from tests.unit.test_batch_pipeline_worker import item, setup_worker

FC = 'FC-worker-flight-escape-voids-settled-and-held-units-into-anonymous-quarantine'

CLOSED_STAGES = ('fetch_decode', 'vad_windows', 'word_clocks', 'assemble_words', 'asr_recovery')


@pytest.fixture(autouse=True)
def _salvage_terminal_pipeline(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')


def _worker():
    worker, *_ = setup_worker()
    return worker


def _salvaged_failed(stage):
    return FailedWork('a', None, None, {'stage': stage, 'reason': 'unknown'})


# ------------------------------------------------- pump evidence forwarding


@pytest.mark.asyncio
@pytest.mark.parametrize('stage', CLOSED_STAGES)
async def test_pump_forwards_salvaged_evidence_per_cursor_stage(monkeypatch, stage):
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), time.time())
    lease = queue.pull(time.time())[0]
    fail = Mock(wraps=queue.fail)
    monkeypatch.setattr(queue, 'fail', fail)
    await Pump(queue, _worker())._publish(lease, {'a': _salvaged_failed(stage)}, set())
    assert fail.call_args.kwargs['worker_failure_evidence'] == {'stage': stage, 'reason': 'unknown'}


@pytest.mark.asyncio
async def test_pump_salvaged_failure_carries_no_measured_vad(monkeypatch):
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), time.time())
    lease = queue.pull(time.time())[0]
    fail = Mock(wraps=queue.fail)
    monkeypatch.setattr(queue, 'fail', fail)
    await Pump(queue, _worker())._publish(lease, {'a': _salvaged_failed('vad_windows')}, set())
    assert fail.call_args.kwargs['measured_held_vad_speech_seconds'] is None
    assert fail.call_args.kwargs['worker_vad_receipt'] is None


@pytest.mark.asyncio
async def test_pump_forwards_salvaged_holds_as_defers(monkeypatch):
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), time.time())
    lease = queue.pull(time.time())[0]
    defer = Mock(wraps=queue.defer)
    monkeypatch.setattr(queue, 'defer', defer)
    await Pump(queue, _worker())._publish(lease, {'a': HeldWork('a', reason='')}, set())
    # The pump folds the empty recorded hold reason to None across the boundary;
    # a salvaged hold still lands as an admission-refused defer, never a retry.
    assert defer.call_args.kwargs.get('held_reason') is None
    assert defer.call_args.kwargs.get('admission_refused') is True


@pytest.mark.asyncio
async def test_pump_settled_results_still_complete(monkeypatch):
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), time.time())
    lease = queue.pull(time.time())[0]
    result = WorkResult('a', 'encrypted-result://a')
    assert await Pump(queue, _worker())._publish(lease, {'a': result}, set()) is True
    assert store.rows['jobs', 'a']['state'] == 'result_ready'


# ------------------------------------------------- ladder: evidence to ceiling


async def _ladder(monkeypatch, work_factory, *, attempts, caplog=None):
    store = MemoryStore()
    queue = Scheduler(store)
    start = time.time()
    queue.enqueue(item('a'), start)
    for attempt in range(1, attempts + 1):
        if attempt > 1:
            due = store.rows['jobs', 'a']['available_at']
            queue.recover(due)
        now = start if attempt == 1 else store.rows['jobs', 'a']['available_at']
        lease = queue.pull(now)[0]
        level = caplog.at_level(logging.INFO, logger='utils.batch_pipeline.scheduler') if caplog else _nulllevel()
        with level:
            await Pump(queue, _worker())._publish(lease, {'a': work_factory(attempt)}, set())
    return queue, store


class _nulllevel:
    def __enter__(self):
        return None

    def __exit__(self, *args):
        return None


@pytest.mark.asyncio
@pytest.mark.parametrize('stage', CLOSED_STAGES)
async def test_salvaged_evidence_ladder_defers_then_quarantines(monkeypatch, stage):
    _, store = await _ladder(monkeypatch, lambda a: _salvaged_failed(stage), attempts=5)
    job = store.rows['jobs', 'a']
    assert job['state'] == 'quarantined'
    assert job['attempt'] == 5
    assert job['worker_failure_evidence'] == {'stage': stage, 'reason': 'unknown'}


@pytest.mark.asyncio
@pytest.mark.parametrize('stage', CLOSED_STAGES)
async def test_salvaged_evidence_terminal_names_the_cursor_stage(monkeypatch, caplog, stage):
    with caplog.at_level(logging.ERROR, logger='utils.batch_pipeline.scheduler'):
        _, store = await _ladder(monkeypatch, lambda a: _salvaged_failed(stage), attempts=5)
    quarantined = [r for r in caplog.records if 'event=batch_quarantined' in r.getMessage()]
    assert len(quarantined) == 1
    assert quarantined[-1].getMessage() == (
        f'event=batch_quarantined reason=worker_failed attempt=5 recovery=held stage={stage} worker_reason=unknown'
    )


@pytest.mark.asyncio
@pytest.mark.parametrize('stage', CLOSED_STAGES)
async def test_salvaged_evidence_terminal_stays_off_designed_channels(monkeypatch, caplog, stage):
    with caplog.at_level(logging.INFO, logger='utils.batch_pipeline.scheduler'):
        _, store = await _ladder(monkeypatch, lambda a: _salvaged_failed(stage), attempts=5)
    assert not [r for r in caplog.records if 'event=batch_language_guard' in r.getMessage()]
    assert not [r for r in caplog.records if 'event=batch_empty_ladder' in r.getMessage()]
    assert not [r for r in caplog.records if 'event=batch_validation_disposition' in r.getMessage()]
    assert store.rows['jobs', 'a']['state'] == 'quarantined'


@pytest.mark.asyncio
async def test_salvaged_terminal_keeps_the_awaiting_recovery_warning(monkeypatch, caplog):
    with caplog.at_level(logging.INFO, logger='utils.batch_pipeline.scheduler'):
        _, store = await _ladder(monkeypatch, lambda a: _salvaged_failed('vad_windows'), attempts=5)
    warnings = [
        r
        for r in caplog.records
        if 'event=batch_recovery outcome=held reason=awaiting_fenced_recovery' in r.getMessage()
    ]
    assert len(warnings) >= 1
    assert store.rows['jobs', 'a']['state'] == 'quarantined'


@pytest.mark.asyncio
@pytest.mark.parametrize('stage', ('vad_windows', 'assemble_words'))
async def test_salvaged_evidence_defers_at_mid_ladder(monkeypatch, stage):
    _, store = await _ladder(monkeypatch, lambda a: _salvaged_failed(stage), attempts=1)
    job = store.rows['jobs', 'a']
    assert job['state'] == 'retry'
    assert job['worker_failure_evidence'] == {'stage': stage, 'reason': 'unknown'}


@pytest.mark.asyncio
async def test_later_evidenceless_attempts_preserve_salvaged_diagnosis(monkeypatch):
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), time.time())
    lease = queue.pull(time.time())[0]
    await Pump(queue, _worker())._publish(lease, {'a': _salvaged_failed('vad_windows')}, set())
    for _ in range(4):
        due = store.rows['jobs', 'a']['available_at']
        queue.recover(due)
        lease = queue.pull(due)[0]
        await Pump(queue, _worker())._publish(lease, {}, set())
    job = store.rows['jobs', 'a']
    assert job['state'] == 'quarantined'
    assert job['worker_failure_evidence'] == {'stage': 'vad_windows', 'reason': 'unknown'}


@pytest.mark.asyncio
async def test_latest_typed_diagnosis_supersedes_salvaged_evidence(monkeypatch):
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('a'), time.time())
    lease = queue.pull(time.time())[0]
    await Pump(queue, _worker())._publish(lease, {'a': _salvaged_failed('vad_windows')}, set())
    for _ in range(4):
        due = store.rows['jobs', 'a']['available_at']
        queue.recover(due)
        lease = queue.pull(due)[0]
        await Pump(queue, _worker())._publish(
            lease,
            {'a': FailedWork('a', None, None, {'stage': 'word_clocks', 'reason': 'word_clock'})},
            set(),
        )
    job = store.rows['jobs', 'a']
    assert job['state'] == 'quarantined'
    assert job['worker_failure_evidence'] == {'stage': 'word_clocks', 'reason': 'word_clock'}

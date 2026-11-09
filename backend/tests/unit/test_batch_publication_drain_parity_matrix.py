"""Publication-drain parity matrix: every result kind x every flight path.

Each cell drives the real publication path (``Pump._publish_flight``) with one
work kind across a scripted scheduler and a scripted ordered merge, then
asserts the exact observable contract: the scheduler call log, the drained
owner set, and the armed deferred-drain ledger. The expected tuples were
derived from the convergence contract in
``docs/batch-merge-deferred-drain-convergence.md`` — not from the code — so a
drift on either side fails this matrix.

Failure-Class: FC-publication-drain-contention-exhaustion-left-without-a-convergence-owner
"""

import asyncio
import types

import pytest

from database.firestore_transaction_retry import FirestoreContentionExhausted
from utils.batch_pipeline.contracts import (
    FailedWork,
    HeldWork,
    LeasedWork,
    Priority,
    RecoveryWork,
    ValidationFailureWork,
    WorkItem,
    WorkResult,
)
import utils.batch_pipeline.pump as pump_module
from utils.batch_pipeline.pump import Pump


@pytest.fixture(autouse=True)
def inline_blocking(monkeypatch):
    async def passthrough(executor, function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(pump_module, 'run_blocking', passthrough)


HOT = FirestoreContentionExhausted('hot')


class ScriptScheduler:
    def __init__(self):
        self.store = self
        self.calls = []
        # Segments whose transition loses to contention: the attempt is
        # observable in the call log, then marks the segment lost.
        self.loss_segments = frozenset()

    def complete(self, result, token, now):
        self.calls.append(('complete', result.segment_id))
        if result.segment_id in self.loss_segments:
            raise HOT
        return True

    def fail(self, segment_id, token, now, **kwargs):
        self.calls.append(('fail', segment_id, _sortable(kwargs)))
        if segment_id in self.loss_segments:
            raise HOT
        return True

    def defer(self, segment_id, token, now, retry_after=30, held_reason=None, admission_refused=False):
        self.calls.append(('defer', segment_id, retry_after, held_reason, admission_refused))
        if segment_id in self.loss_segments:
            raise HOT
        return True

    def heartbeat(self, segment_id, token, now):
        return True


def _sortable(kwargs):
    return tuple(sorted(kwargs.items()))


class ScriptMerge:
    """commit_next script modes: 'empty' converges, 'first' loses once per
    owner, 'always' always loses."""

    def __init__(self, mode):
        self.held_owners = set()
        self.mode = mode
        self.drained = []
        self.commits = 0
        self.first_loss_done = set()

    def commit_next(self, owner_id, now):
        self.drained.append(owner_id)
        self.commits += 1
        if self.mode == 'empty':
            return None
        if self.mode == 'first':
            if owner_id not in self.first_loss_done:
                self.first_loss_done.add(owner_id)
                raise FirestoreContentionExhausted('hot')
            return None
        raise FirestoreContentionExhausted('hot')


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def work(segment, owner):
    item = WorkItem(
        segment_id=segment,
        owner_id=owner,
        capture_at=1000.0,
        audio_uri='gs://bucket/audio/' + segment,
        duration_seconds=12.0,
        priority=Priority.RECENT,
    )
    return LeasedWork(item=item, token='tok', attempt=1, lease_until=1999.0)


def result_of(kind, segment):
    if kind == 'success':
        return WorkResult(segment, 'gs://r/' + segment)
    if kind == 'held':
        return HeldWork(segment, retry_after=45, reason='cap_hold')
    if kind == 'validation':
        return ValidationFailureWork(segment, 'fetch_decode', 'staged_audio_invalid', 1.5, {'receipt': True})
    if kind == 'recovery':
        return RecoveryWork(
            segment,
            padded_retry_empty=True,
            padded_retry='empty',
            reason='empty_asr',
            measured_held_vad_speech_seconds=1.5,
            worker_vad_receipt={'receipt': True},
        )
    if kind == 'failed':
        return FailedWork(segment, 2.5, {'receipt': True}, {'stage': 'vad_windows', 'reason': 'unsupported_language'})
    return None


def make_pump(merge, concurrency):
    pump = Pump(types.SimpleNamespace(), types.SimpleNamespace(), merge=merge, publish_concurrency=concurrency)
    clock = Clock()
    pump._monotonic = clock

    async def instant_publication_sleep(delay, *args, **kwargs):
        pass  # the re-strike lane steps its schedule instantly in this matrix

    pump._publication_sleep = instant_publication_sleep
    return pump, clock


async def test_matrix_success_c1_empty_single():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {
        'seg-1': result_of('success', 'seg-1'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [('complete', 'seg-1')]
    assert merge.drained == ['owner-1']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_success_c1_empty_two_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-a', 'owner-a'), work('seg-b', 'owner-b')]
    result_map = {
        'seg-a': result_of('success', 'seg-a'),
        'seg-b': result_of('success', 'seg-b'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [('complete', 'seg-a'), ('complete', 'seg-b')]
    assert merge.drained == ['owner-a', 'owner-b']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_success_c1_empty_two_seg_same_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1'), work('seg-2', 'owner-1')]
    result_map = {
        'seg-1': result_of('success', 'seg-1'),
        'seg-2': result_of('success', 'seg-2'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [('complete', 'seg-1'), ('complete', 'seg-2')]
    assert merge.drained == ['owner-1', 'owner-1']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_success_c1_empty_mixed_accept():
    scheduler = ScriptScheduler()
    scheduler.loss_segments = {'seg-b'}
    scheduler.complete_ok = False
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-a', 'owner-a'), work('seg-b', 'owner-b')]
    result_map = {
        'seg-a': result_of('success', 'seg-a'),
        'seg-b': result_of('success', 'seg-b'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [('complete', 'seg-a'), ('complete', 'seg-b')] + [('complete', 'seg-b')] * 3
    assert merge.drained == ['owner-a']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_success_c1_empty_pre_lost():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {
        'seg-1': result_of('success', 'seg-1'),
    }
    lost = {'seg-1'}
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [('complete', 'seg-1')]
    assert merge.drained == ['owner-1']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_success_c4_empty_single():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {
        'seg-1': result_of('success', 'seg-1'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [('complete', 'seg-1')]
    assert merge.drained == ['owner-1']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_success_c4_empty_two_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-a', 'owner-a'), work('seg-b', 'owner-b')]
    result_map = {
        'seg-a': result_of('success', 'seg-a'),
        'seg-b': result_of('success', 'seg-b'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [('complete', 'seg-a'), ('complete', 'seg-b')]
    assert merge.drained == ['owner-a', 'owner-b']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_success_c4_empty_two_seg_same_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1'), work('seg-2', 'owner-1')]
    result_map = {
        'seg-1': result_of('success', 'seg-1'),
        'seg-2': result_of('success', 'seg-2'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [('complete', 'seg-1'), ('complete', 'seg-2')]
    assert merge.drained == ['owner-1']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_success_c4_empty_mixed_accept():
    scheduler = ScriptScheduler()
    scheduler.loss_segments = {'seg-b'}
    scheduler.complete_ok = False
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-a', 'owner-a'), work('seg-b', 'owner-b')]
    result_map = {
        'seg-a': result_of('success', 'seg-a'),
        'seg-b': result_of('success', 'seg-b'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [('complete', 'seg-a'), ('complete', 'seg-b')] + [('complete', 'seg-b')] * 3
    assert merge.drained == ['owner-a']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_success_c4_empty_pre_lost():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {
        'seg-1': result_of('success', 'seg-1'),
    }
    lost = {'seg-1'}
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [('complete', 'seg-1')]
    assert merge.drained == ['owner-1']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_held_c1_empty_single():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {
        'seg-1': result_of('held', 'seg-1'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [('defer', 'seg-1', 45, 'cap_hold', True)]
    assert merge.drained == []
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_held_c1_empty_two_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-a', 'owner-a'), work('seg-b', 'owner-b')]
    result_map = {
        'seg-a': result_of('held', 'seg-a'),
        'seg-b': result_of('held', 'seg-b'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [('defer', 'seg-a', 45, 'cap_hold', True), ('defer', 'seg-b', 45, 'cap_hold', True)]
    assert merge.drained == []
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_held_c1_empty_two_seg_same_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1'), work('seg-2', 'owner-1')]
    result_map = {
        'seg-1': result_of('held', 'seg-1'),
        'seg-2': result_of('held', 'seg-2'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [('defer', 'seg-1', 45, 'cap_hold', True), ('defer', 'seg-2', 45, 'cap_hold', True)]
    assert merge.drained == []
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_held_c1_empty_mixed_accept():
    scheduler = ScriptScheduler()
    scheduler.loss_segments = {'seg-b'}
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = False
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-a', 'owner-a'), work('seg-b', 'owner-b')]
    result_map = {
        'seg-a': result_of('held', 'seg-a'),
        'seg-b': result_of('held', 'seg-b'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert (
        scheduler.calls
        == [('defer', 'seg-a', 45, 'cap_hold', True), ('defer', 'seg-b', 45, 'cap_hold', True)]
        + [('defer', 'seg-b', 45, 'cap_hold', True)] * 3
    )
    assert merge.drained == []
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_held_c1_empty_pre_lost():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {
        'seg-1': result_of('held', 'seg-1'),
    }
    lost = {'seg-1'}
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [('defer', 'seg-1', 45, 'cap_hold', True)]
    assert merge.drained == []
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_held_c4_empty_single():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {
        'seg-1': result_of('held', 'seg-1'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [('defer', 'seg-1', 45, 'cap_hold', True)]
    assert merge.drained == []
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_held_c4_empty_two_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-a', 'owner-a'), work('seg-b', 'owner-b')]
    result_map = {
        'seg-a': result_of('held', 'seg-a'),
        'seg-b': result_of('held', 'seg-b'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [('defer', 'seg-a', 45, 'cap_hold', True), ('defer', 'seg-b', 45, 'cap_hold', True)]
    assert merge.drained == []
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_held_c4_empty_two_seg_same_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1'), work('seg-2', 'owner-1')]
    result_map = {
        'seg-1': result_of('held', 'seg-1'),
        'seg-2': result_of('held', 'seg-2'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [('defer', 'seg-1', 45, 'cap_hold', True), ('defer', 'seg-2', 45, 'cap_hold', True)]
    assert merge.drained == []
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_held_c4_empty_mixed_accept():
    scheduler = ScriptScheduler()
    scheduler.loss_segments = {'seg-b'}
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = False
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-a', 'owner-a'), work('seg-b', 'owner-b')]
    result_map = {
        'seg-a': result_of('held', 'seg-a'),
        'seg-b': result_of('held', 'seg-b'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert (
        scheduler.calls
        == [('defer', 'seg-a', 45, 'cap_hold', True), ('defer', 'seg-b', 45, 'cap_hold', True)]
        + [('defer', 'seg-b', 45, 'cap_hold', True)] * 3
    )
    assert merge.drained == []
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_held_c4_empty_pre_lost():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {
        'seg-1': result_of('held', 'seg-1'),
    }
    lost = {'seg-1'}
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [('defer', 'seg-1', 45, 'cap_hold', True)]
    assert merge.drained == []
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_validation_c1_empty_single():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {
        'seg-1': result_of('validation', 'seg-1'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('worker_failure', {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        )
    ]
    assert merge.drained == ['owner-1']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_validation_c1_empty_two_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-a', 'owner-a'), work('seg-b', 'owner-b')]
    result_map = {
        'seg-a': result_of('validation', 'seg-a'),
        'seg-b': result_of('validation', 'seg-b'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-a',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('worker_failure', {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('worker_failure', {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-a', 'owner-b']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_validation_c1_empty_two_seg_same_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1'), work('seg-2', 'owner-1')]
    result_map = {
        'seg-1': result_of('validation', 'seg-1'),
        'seg-2': result_of('validation', 'seg-2'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('worker_failure', {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-2',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('worker_failure', {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-1', 'owner-1']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_validation_c1_empty_mixed_accept():
    scheduler = ScriptScheduler()
    scheduler.loss_segments = {'seg-b'}
    scheduler.complete_ok = True
    scheduler.fail_ok = False
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-a', 'owner-a'), work('seg-b', 'owner-b')]
    result_map = {
        'seg-a': result_of('validation', 'seg-a'),
        'seg-b': result_of('validation', 'seg-b'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-a',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('worker_failure', {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('worker_failure', {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('worker_failure', {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('worker_failure', {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('worker_failure', {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-a']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_validation_c1_empty_pre_lost():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {
        'seg-1': result_of('validation', 'seg-1'),
    }
    lost = {'seg-1'}
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('worker_failure', {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        )
    ]
    assert merge.drained == ['owner-1']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_validation_c4_empty_single():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {
        'seg-1': result_of('validation', 'seg-1'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('worker_failure', {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        )
    ]
    assert merge.drained == ['owner-1']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_validation_c4_empty_two_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-a', 'owner-a'), work('seg-b', 'owner-b')]
    result_map = {
        'seg-a': result_of('validation', 'seg-a'),
        'seg-b': result_of('validation', 'seg-b'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-a',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('worker_failure', {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('worker_failure', {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-a', 'owner-b']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_validation_c4_empty_two_seg_same_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1'), work('seg-2', 'owner-1')]
    result_map = {
        'seg-1': result_of('validation', 'seg-1'),
        'seg-2': result_of('validation', 'seg-2'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('worker_failure', {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-2',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('worker_failure', {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-1']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_validation_c4_empty_mixed_accept():
    scheduler = ScriptScheduler()
    scheduler.loss_segments = {'seg-b'}
    scheduler.complete_ok = True
    scheduler.fail_ok = False
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-a', 'owner-a'), work('seg-b', 'owner-b')]
    result_map = {
        'seg-a': result_of('validation', 'seg-a'),
        'seg-b': result_of('validation', 'seg-b'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-a',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('worker_failure', {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('worker_failure', {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('worker_failure', {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('worker_failure', {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('worker_failure', {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-a']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_validation_c4_empty_pre_lost():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {
        'seg-1': result_of('validation', 'seg-1'),
    }
    lost = {'seg-1'}
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('worker_failure', {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        )
    ]
    assert merge.drained == ['owner-1']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_recovery_c1_empty_single():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {
        'seg-1': result_of('recovery', 'seg-1'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('padded_retry', 'empty'),
                    ('padded_retry_empty', True),
                    ('quarantine', True),
                    ('worker_failure', {'stage': 'assemble_words', 'reason': 'empty_asr'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        )
    ]
    assert merge.drained == ['owner-1']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_recovery_c1_empty_two_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-a', 'owner-a'), work('seg-b', 'owner-b')]
    result_map = {
        'seg-a': result_of('recovery', 'seg-a'),
        'seg-b': result_of('recovery', 'seg-b'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-a',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('padded_retry', 'empty'),
                    ('padded_retry_empty', True),
                    ('quarantine', True),
                    ('worker_failure', {'stage': 'assemble_words', 'reason': 'empty_asr'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('padded_retry', 'empty'),
                    ('padded_retry_empty', True),
                    ('quarantine', True),
                    ('worker_failure', {'stage': 'assemble_words', 'reason': 'empty_asr'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-a', 'owner-b']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_recovery_c1_empty_two_seg_same_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1'), work('seg-2', 'owner-1')]
    result_map = {
        'seg-1': result_of('recovery', 'seg-1'),
        'seg-2': result_of('recovery', 'seg-2'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('padded_retry', 'empty'),
                    ('padded_retry_empty', True),
                    ('quarantine', True),
                    ('worker_failure', {'stage': 'assemble_words', 'reason': 'empty_asr'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-2',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('padded_retry', 'empty'),
                    ('padded_retry_empty', True),
                    ('quarantine', True),
                    ('worker_failure', {'stage': 'assemble_words', 'reason': 'empty_asr'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-1', 'owner-1']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_recovery_c1_empty_mixed_accept():
    scheduler = ScriptScheduler()
    scheduler.loss_segments = {'seg-b'}
    scheduler.complete_ok = True
    scheduler.fail_ok = False
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-a', 'owner-a'), work('seg-b', 'owner-b')]
    result_map = {
        'seg-a': result_of('recovery', 'seg-a'),
        'seg-b': result_of('recovery', 'seg-b'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-a',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('padded_retry', 'empty'),
                    ('padded_retry_empty', True),
                    ('quarantine', True),
                    ('worker_failure', {'stage': 'assemble_words', 'reason': 'empty_asr'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('padded_retry', 'empty'),
                    ('padded_retry_empty', True),
                    ('quarantine', True),
                    ('worker_failure', {'stage': 'assemble_words', 'reason': 'empty_asr'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('padded_retry', 'empty'),
                    ('padded_retry_empty', True),
                    ('quarantine', True),
                    ('worker_failure', {'stage': 'assemble_words', 'reason': 'empty_asr'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('padded_retry', 'empty'),
                    ('padded_retry_empty', True),
                    ('quarantine', True),
                    ('worker_failure', {'stage': 'assemble_words', 'reason': 'empty_asr'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('padded_retry', 'empty'),
                    ('padded_retry_empty', True),
                    ('quarantine', True),
                    ('worker_failure', {'stage': 'assemble_words', 'reason': 'empty_asr'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-a']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_recovery_c1_empty_pre_lost():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {
        'seg-1': result_of('recovery', 'seg-1'),
    }
    lost = {'seg-1'}
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('padded_retry', 'empty'),
                    ('padded_retry_empty', True),
                    ('quarantine', True),
                    ('worker_failure', {'stage': 'assemble_words', 'reason': 'empty_asr'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        )
    ]
    assert merge.drained == ['owner-1']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_recovery_c4_empty_single():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {
        'seg-1': result_of('recovery', 'seg-1'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('padded_retry', 'empty'),
                    ('padded_retry_empty', True),
                    ('quarantine', True),
                    ('worker_failure', {'stage': 'assemble_words', 'reason': 'empty_asr'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        )
    ]
    assert merge.drained == ['owner-1']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_recovery_c4_empty_two_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-a', 'owner-a'), work('seg-b', 'owner-b')]
    result_map = {
        'seg-a': result_of('recovery', 'seg-a'),
        'seg-b': result_of('recovery', 'seg-b'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-a',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('padded_retry', 'empty'),
                    ('padded_retry_empty', True),
                    ('quarantine', True),
                    ('worker_failure', {'stage': 'assemble_words', 'reason': 'empty_asr'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('padded_retry', 'empty'),
                    ('padded_retry_empty', True),
                    ('quarantine', True),
                    ('worker_failure', {'stage': 'assemble_words', 'reason': 'empty_asr'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-a', 'owner-b']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_recovery_c4_empty_two_seg_same_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1'), work('seg-2', 'owner-1')]
    result_map = {
        'seg-1': result_of('recovery', 'seg-1'),
        'seg-2': result_of('recovery', 'seg-2'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('padded_retry', 'empty'),
                    ('padded_retry_empty', True),
                    ('quarantine', True),
                    ('worker_failure', {'stage': 'assemble_words', 'reason': 'empty_asr'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-2',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('padded_retry', 'empty'),
                    ('padded_retry_empty', True),
                    ('quarantine', True),
                    ('worker_failure', {'stage': 'assemble_words', 'reason': 'empty_asr'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-1']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_recovery_c4_empty_mixed_accept():
    scheduler = ScriptScheduler()
    scheduler.loss_segments = {'seg-b'}
    scheduler.complete_ok = True
    scheduler.fail_ok = False
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-a', 'owner-a'), work('seg-b', 'owner-b')]
    result_map = {
        'seg-a': result_of('recovery', 'seg-a'),
        'seg-b': result_of('recovery', 'seg-b'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-a',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('padded_retry', 'empty'),
                    ('padded_retry_empty', True),
                    ('quarantine', True),
                    ('worker_failure', {'stage': 'assemble_words', 'reason': 'empty_asr'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('padded_retry', 'empty'),
                    ('padded_retry_empty', True),
                    ('quarantine', True),
                    ('worker_failure', {'stage': 'assemble_words', 'reason': 'empty_asr'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('padded_retry', 'empty'),
                    ('padded_retry_empty', True),
                    ('quarantine', True),
                    ('worker_failure', {'stage': 'assemble_words', 'reason': 'empty_asr'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('padded_retry', 'empty'),
                    ('padded_retry_empty', True),
                    ('quarantine', True),
                    ('worker_failure', {'stage': 'assemble_words', 'reason': 'empty_asr'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('padded_retry', 'empty'),
                    ('padded_retry_empty', True),
                    ('quarantine', True),
                    ('worker_failure', {'stage': 'assemble_words', 'reason': 'empty_asr'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-a']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_recovery_c4_empty_pre_lost():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {
        'seg-1': result_of('recovery', 'seg-1'),
    }
    lost = {'seg-1'}
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('padded_retry', 'empty'),
                    ('padded_retry_empty', True),
                    ('quarantine', True),
                    ('worker_failure', {'stage': 'assemble_words', 'reason': 'empty_asr'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        )
    ]
    assert merge.drained == ['owner-1']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_failed_c1_empty_single():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {
        'seg-1': result_of('failed', 'seg-1'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 2.5),
                    ('worker_failure_evidence', {'stage': 'vad_windows', 'reason': 'unsupported_language'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        )
    ]
    assert merge.drained == ['owner-1']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_failed_c1_empty_two_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-a', 'owner-a'), work('seg-b', 'owner-b')]
    result_map = {
        'seg-a': result_of('failed', 'seg-a'),
        'seg-b': result_of('failed', 'seg-b'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-a',
            (
                (
                    ('measured_held_vad_speech_seconds', 2.5),
                    ('worker_failure_evidence', {'stage': 'vad_windows', 'reason': 'unsupported_language'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', 2.5),
                    ('worker_failure_evidence', {'stage': 'vad_windows', 'reason': 'unsupported_language'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-a', 'owner-b']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_failed_c1_empty_two_seg_same_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1'), work('seg-2', 'owner-1')]
    result_map = {
        'seg-1': result_of('failed', 'seg-1'),
        'seg-2': result_of('failed', 'seg-2'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 2.5),
                    ('worker_failure_evidence', {'stage': 'vad_windows', 'reason': 'unsupported_language'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-2',
            (
                (
                    ('measured_held_vad_speech_seconds', 2.5),
                    ('worker_failure_evidence', {'stage': 'vad_windows', 'reason': 'unsupported_language'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-1', 'owner-1']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_failed_c1_empty_mixed_accept():
    scheduler = ScriptScheduler()
    scheduler.loss_segments = {'seg-b'}
    scheduler.complete_ok = True
    scheduler.fail_ok = False
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-a', 'owner-a'), work('seg-b', 'owner-b')]
    result_map = {
        'seg-a': result_of('failed', 'seg-a'),
        'seg-b': result_of('failed', 'seg-b'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-a',
            (
                (
                    ('measured_held_vad_speech_seconds', 2.5),
                    ('worker_failure_evidence', {'stage': 'vad_windows', 'reason': 'unsupported_language'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', 2.5),
                    ('worker_failure_evidence', {'stage': 'vad_windows', 'reason': 'unsupported_language'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', 2.5),
                    ('worker_failure_evidence', {'stage': 'vad_windows', 'reason': 'unsupported_language'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', 2.5),
                    ('worker_failure_evidence', {'stage': 'vad_windows', 'reason': 'unsupported_language'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', 2.5),
                    ('worker_failure_evidence', {'stage': 'vad_windows', 'reason': 'unsupported_language'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-a']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_failed_c1_empty_pre_lost():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {
        'seg-1': result_of('failed', 'seg-1'),
    }
    lost = {'seg-1'}
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 2.5),
                    ('worker_failure_evidence', {'stage': 'vad_windows', 'reason': 'unsupported_language'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        )
    ]
    assert merge.drained == ['owner-1']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_failed_c4_empty_single():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {
        'seg-1': result_of('failed', 'seg-1'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 2.5),
                    ('worker_failure_evidence', {'stage': 'vad_windows', 'reason': 'unsupported_language'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        )
    ]
    assert merge.drained == ['owner-1']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_failed_c4_empty_two_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-a', 'owner-a'), work('seg-b', 'owner-b')]
    result_map = {
        'seg-a': result_of('failed', 'seg-a'),
        'seg-b': result_of('failed', 'seg-b'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-a',
            (
                (
                    ('measured_held_vad_speech_seconds', 2.5),
                    ('worker_failure_evidence', {'stage': 'vad_windows', 'reason': 'unsupported_language'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', 2.5),
                    ('worker_failure_evidence', {'stage': 'vad_windows', 'reason': 'unsupported_language'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-a', 'owner-b']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_failed_c4_empty_two_seg_same_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1'), work('seg-2', 'owner-1')]
    result_map = {
        'seg-1': result_of('failed', 'seg-1'),
        'seg-2': result_of('failed', 'seg-2'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 2.5),
                    ('worker_failure_evidence', {'stage': 'vad_windows', 'reason': 'unsupported_language'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-2',
            (
                (
                    ('measured_held_vad_speech_seconds', 2.5),
                    ('worker_failure_evidence', {'stage': 'vad_windows', 'reason': 'unsupported_language'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-1']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_failed_c4_empty_mixed_accept():
    scheduler = ScriptScheduler()
    scheduler.loss_segments = {'seg-b'}
    scheduler.complete_ok = True
    scheduler.fail_ok = False
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-a', 'owner-a'), work('seg-b', 'owner-b')]
    result_map = {
        'seg-a': result_of('failed', 'seg-a'),
        'seg-b': result_of('failed', 'seg-b'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-a',
            (
                (
                    ('measured_held_vad_speech_seconds', 2.5),
                    ('worker_failure_evidence', {'stage': 'vad_windows', 'reason': 'unsupported_language'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', 2.5),
                    ('worker_failure_evidence', {'stage': 'vad_windows', 'reason': 'unsupported_language'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', 2.5),
                    ('worker_failure_evidence', {'stage': 'vad_windows', 'reason': 'unsupported_language'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', 2.5),
                    ('worker_failure_evidence', {'stage': 'vad_windows', 'reason': 'unsupported_language'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', 2.5),
                    ('worker_failure_evidence', {'stage': 'vad_windows', 'reason': 'unsupported_language'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-a']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_failed_c4_empty_pre_lost():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {
        'seg-1': result_of('failed', 'seg-1'),
    }
    lost = {'seg-1'}
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 2.5),
                    ('worker_failure_evidence', {'stage': 'vad_windows', 'reason': 'unsupported_language'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        )
    ]
    assert merge.drained == ['owner-1']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_missing_c1_empty_single():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', None),
                    ('worker_failure_evidence', None),
                    ('worker_vad_receipt', None),
                )
            ),
        )
    ]
    assert merge.drained == ['owner-1']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_missing_c1_empty_two_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-a', 'owner-a'), work('seg-b', 'owner-b')]
    result_map = {}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-a',
            (
                (
                    ('measured_held_vad_speech_seconds', None),
                    ('worker_failure_evidence', None),
                    ('worker_vad_receipt', None),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', None),
                    ('worker_failure_evidence', None),
                    ('worker_vad_receipt', None),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-a', 'owner-b']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_missing_c1_empty_two_seg_same_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1'), work('seg-2', 'owner-1')]
    result_map = {}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', None),
                    ('worker_failure_evidence', None),
                    ('worker_vad_receipt', None),
                )
            ),
        ),
        (
            'fail',
            'seg-2',
            (
                (
                    ('measured_held_vad_speech_seconds', None),
                    ('worker_failure_evidence', None),
                    ('worker_vad_receipt', None),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-1', 'owner-1']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_missing_c1_empty_mixed_accept():
    scheduler = ScriptScheduler()
    scheduler.loss_segments = {'seg-b'}
    scheduler.complete_ok = True
    scheduler.fail_ok = False
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-a', 'owner-a'), work('seg-b', 'owner-b')]
    result_map = {}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-a',
            (
                (
                    ('measured_held_vad_speech_seconds', None),
                    ('worker_failure_evidence', None),
                    ('worker_vad_receipt', None),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', None),
                    ('worker_failure_evidence', None),
                    ('worker_vad_receipt', None),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', None),
                    ('worker_failure_evidence', None),
                    ('worker_vad_receipt', None),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', None),
                    ('worker_failure_evidence', None),
                    ('worker_vad_receipt', None),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', None),
                    ('worker_failure_evidence', None),
                    ('worker_vad_receipt', None),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-a']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_missing_c1_empty_pre_lost():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {}
    lost = {'seg-1'}
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', None),
                    ('worker_failure_evidence', None),
                    ('worker_vad_receipt', None),
                )
            ),
        )
    ]
    assert merge.drained == ['owner-1']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_missing_c4_empty_single():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', None),
                    ('worker_failure_evidence', None),
                    ('worker_vad_receipt', None),
                )
            ),
        )
    ]
    assert merge.drained == ['owner-1']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_missing_c4_empty_two_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-a', 'owner-a'), work('seg-b', 'owner-b')]
    result_map = {}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-a',
            (
                (
                    ('measured_held_vad_speech_seconds', None),
                    ('worker_failure_evidence', None),
                    ('worker_vad_receipt', None),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', None),
                    ('worker_failure_evidence', None),
                    ('worker_vad_receipt', None),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-a', 'owner-b']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_missing_c4_empty_two_seg_same_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1'), work('seg-2', 'owner-1')]
    result_map = {}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', None),
                    ('worker_failure_evidence', None),
                    ('worker_vad_receipt', None),
                )
            ),
        ),
        (
            'fail',
            'seg-2',
            (
                (
                    ('measured_held_vad_speech_seconds', None),
                    ('worker_failure_evidence', None),
                    ('worker_vad_receipt', None),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-1']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_missing_c4_empty_mixed_accept():
    scheduler = ScriptScheduler()
    scheduler.loss_segments = {'seg-b'}
    scheduler.complete_ok = True
    scheduler.fail_ok = False
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-a', 'owner-a'), work('seg-b', 'owner-b')]
    result_map = {}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-a',
            (
                (
                    ('measured_held_vad_speech_seconds', None),
                    ('worker_failure_evidence', None),
                    ('worker_vad_receipt', None),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', None),
                    ('worker_failure_evidence', None),
                    ('worker_vad_receipt', None),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', None),
                    ('worker_failure_evidence', None),
                    ('worker_vad_receipt', None),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', None),
                    ('worker_failure_evidence', None),
                    ('worker_vad_receipt', None),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', None),
                    ('worker_failure_evidence', None),
                    ('worker_vad_receipt', None),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-a']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_missing_c4_empty_pre_lost():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('empty')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {}
    lost = {'seg-1'}
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', None),
                    ('worker_failure_evidence', None),
                    ('worker_vad_receipt', None),
                )
            ),
        )
    ]
    assert merge.drained == ['owner-1']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_success_c1_first_single():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('first')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {
        'seg-1': result_of('success', 'seg-1'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [('complete', 'seg-1')]
    assert merge.drained == ['owner-1']
    assert {'owner-1': 1} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_success_c1_first_two_seg_same_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('first')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1'), work('seg-2', 'owner-1')]
    result_map = {
        'seg-1': result_of('success', 'seg-1'),
        'seg-2': result_of('success', 'seg-2'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [('complete', 'seg-1'), ('complete', 'seg-2')]
    assert merge.drained == ['owner-1', 'owner-1']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_success_c1_always_single():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('always')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {
        'seg-1': result_of('success', 'seg-1'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [('complete', 'seg-1')]
    assert merge.drained == ['owner-1']
    assert {'owner-1': 1} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_success_c1_always_two_seg_same_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('always')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1'), work('seg-2', 'owner-1')]
    result_map = {
        'seg-1': result_of('success', 'seg-1'),
        'seg-2': result_of('success', 'seg-2'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [('complete', 'seg-1'), ('complete', 'seg-2')]
    assert merge.drained == ['owner-1', 'owner-1']
    assert {'owner-1': 2} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_success_c1_first_two_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('first')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-a', 'owner-a'), work('seg-b', 'owner-b')]
    result_map = {
        'seg-a': result_of('success', 'seg-a'),
        'seg-b': result_of('success', 'seg-b'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [('complete', 'seg-a'), ('complete', 'seg-b')]
    assert merge.drained == ['owner-a', 'owner-b']
    assert {'owner-a': 1, 'owner-b': 1} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_success_c4_first_single():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('first')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {
        'seg-1': result_of('success', 'seg-1'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [('complete', 'seg-1')]
    assert merge.drained == ['owner-1']
    assert {'owner-1': 1} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_success_c4_first_two_seg_same_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('first')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1'), work('seg-2', 'owner-1')]
    result_map = {
        'seg-1': result_of('success', 'seg-1'),
        'seg-2': result_of('success', 'seg-2'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [('complete', 'seg-1'), ('complete', 'seg-2')]
    assert merge.drained == ['owner-1']
    assert {'owner-1': 1} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_success_c4_always_single():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('always')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {
        'seg-1': result_of('success', 'seg-1'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [('complete', 'seg-1')]
    assert merge.drained == ['owner-1']
    assert {'owner-1': 1} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_success_c4_always_two_seg_same_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('always')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1'), work('seg-2', 'owner-1')]
    result_map = {
        'seg-1': result_of('success', 'seg-1'),
        'seg-2': result_of('success', 'seg-2'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [('complete', 'seg-1'), ('complete', 'seg-2')]
    assert merge.drained == ['owner-1']
    assert {'owner-1': 1} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_success_c4_first_two_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('first')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-a', 'owner-a'), work('seg-b', 'owner-b')]
    result_map = {
        'seg-a': result_of('success', 'seg-a'),
        'seg-b': result_of('success', 'seg-b'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [('complete', 'seg-a'), ('complete', 'seg-b')]
    assert merge.drained == ['owner-a', 'owner-b']
    assert {'owner-a': 1, 'owner-b': 1} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_held_c1_first_single():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('first')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {
        'seg-1': result_of('held', 'seg-1'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [('defer', 'seg-1', 45, 'cap_hold', True)]
    assert merge.drained == []
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_held_c1_first_two_seg_same_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('first')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1'), work('seg-2', 'owner-1')]
    result_map = {
        'seg-1': result_of('held', 'seg-1'),
        'seg-2': result_of('held', 'seg-2'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [('defer', 'seg-1', 45, 'cap_hold', True), ('defer', 'seg-2', 45, 'cap_hold', True)]
    assert merge.drained == []
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_held_c1_always_single():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('always')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {
        'seg-1': result_of('held', 'seg-1'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [('defer', 'seg-1', 45, 'cap_hold', True)]
    assert merge.drained == []
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_held_c1_always_two_seg_same_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('always')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1'), work('seg-2', 'owner-1')]
    result_map = {
        'seg-1': result_of('held', 'seg-1'),
        'seg-2': result_of('held', 'seg-2'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [('defer', 'seg-1', 45, 'cap_hold', True), ('defer', 'seg-2', 45, 'cap_hold', True)]
    assert merge.drained == []
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_held_c1_first_two_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('first')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-a', 'owner-a'), work('seg-b', 'owner-b')]
    result_map = {
        'seg-a': result_of('held', 'seg-a'),
        'seg-b': result_of('held', 'seg-b'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [('defer', 'seg-a', 45, 'cap_hold', True), ('defer', 'seg-b', 45, 'cap_hold', True)]
    assert merge.drained == []
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_held_c4_first_single():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('first')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {
        'seg-1': result_of('held', 'seg-1'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [('defer', 'seg-1', 45, 'cap_hold', True)]
    assert merge.drained == []
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_held_c4_first_two_seg_same_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('first')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1'), work('seg-2', 'owner-1')]
    result_map = {
        'seg-1': result_of('held', 'seg-1'),
        'seg-2': result_of('held', 'seg-2'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [('defer', 'seg-1', 45, 'cap_hold', True), ('defer', 'seg-2', 45, 'cap_hold', True)]
    assert merge.drained == []
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_held_c4_always_single():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('always')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {
        'seg-1': result_of('held', 'seg-1'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [('defer', 'seg-1', 45, 'cap_hold', True)]
    assert merge.drained == []
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_held_c4_always_two_seg_same_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('always')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1'), work('seg-2', 'owner-1')]
    result_map = {
        'seg-1': result_of('held', 'seg-1'),
        'seg-2': result_of('held', 'seg-2'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [('defer', 'seg-1', 45, 'cap_hold', True), ('defer', 'seg-2', 45, 'cap_hold', True)]
    assert merge.drained == []
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_held_c4_first_two_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('first')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-a', 'owner-a'), work('seg-b', 'owner-b')]
    result_map = {
        'seg-a': result_of('held', 'seg-a'),
        'seg-b': result_of('held', 'seg-b'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [('defer', 'seg-a', 45, 'cap_hold', True), ('defer', 'seg-b', 45, 'cap_hold', True)]
    assert merge.drained == []
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_validation_c1_first_single():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('first')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {
        'seg-1': result_of('validation', 'seg-1'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('worker_failure', {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        )
    ]
    assert merge.drained == ['owner-1']
    assert {'owner-1': 1} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_validation_c1_first_two_seg_same_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('first')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1'), work('seg-2', 'owner-1')]
    result_map = {
        'seg-1': result_of('validation', 'seg-1'),
        'seg-2': result_of('validation', 'seg-2'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('worker_failure', {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-2',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('worker_failure', {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-1', 'owner-1']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_validation_c1_always_single():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('always')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {
        'seg-1': result_of('validation', 'seg-1'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('worker_failure', {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        )
    ]
    assert merge.drained == ['owner-1']
    assert {'owner-1': 1} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_validation_c1_always_two_seg_same_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('always')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1'), work('seg-2', 'owner-1')]
    result_map = {
        'seg-1': result_of('validation', 'seg-1'),
        'seg-2': result_of('validation', 'seg-2'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('worker_failure', {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-2',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('worker_failure', {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-1', 'owner-1']
    assert {'owner-1': 2} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_validation_c1_first_two_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('first')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-a', 'owner-a'), work('seg-b', 'owner-b')]
    result_map = {
        'seg-a': result_of('validation', 'seg-a'),
        'seg-b': result_of('validation', 'seg-b'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-a',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('worker_failure', {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('worker_failure', {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-a', 'owner-b']
    assert {'owner-a': 1, 'owner-b': 1} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_validation_c4_first_single():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('first')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {
        'seg-1': result_of('validation', 'seg-1'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('worker_failure', {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        )
    ]
    assert merge.drained == ['owner-1']
    assert {'owner-1': 1} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_validation_c4_first_two_seg_same_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('first')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1'), work('seg-2', 'owner-1')]
    result_map = {
        'seg-1': result_of('validation', 'seg-1'),
        'seg-2': result_of('validation', 'seg-2'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('worker_failure', {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-2',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('worker_failure', {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-1']
    assert {'owner-1': 1} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_validation_c4_always_single():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('always')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {
        'seg-1': result_of('validation', 'seg-1'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('worker_failure', {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        )
    ]
    assert merge.drained == ['owner-1']
    assert {'owner-1': 1} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_validation_c4_always_two_seg_same_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('always')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1'), work('seg-2', 'owner-1')]
    result_map = {
        'seg-1': result_of('validation', 'seg-1'),
        'seg-2': result_of('validation', 'seg-2'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('worker_failure', {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-2',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('worker_failure', {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-1']
    assert {'owner-1': 1} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_validation_c4_first_two_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('first')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-a', 'owner-a'), work('seg-b', 'owner-b')]
    result_map = {
        'seg-a': result_of('validation', 'seg-a'),
        'seg-b': result_of('validation', 'seg-b'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-a',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('worker_failure', {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('worker_failure', {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-a', 'owner-b']
    assert {'owner-a': 1, 'owner-b': 1} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_recovery_c1_first_single():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('first')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {
        'seg-1': result_of('recovery', 'seg-1'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('padded_retry', 'empty'),
                    ('padded_retry_empty', True),
                    ('quarantine', True),
                    ('worker_failure', {'stage': 'assemble_words', 'reason': 'empty_asr'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        )
    ]
    assert merge.drained == ['owner-1']
    assert {'owner-1': 1} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_recovery_c1_first_two_seg_same_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('first')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1'), work('seg-2', 'owner-1')]
    result_map = {
        'seg-1': result_of('recovery', 'seg-1'),
        'seg-2': result_of('recovery', 'seg-2'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('padded_retry', 'empty'),
                    ('padded_retry_empty', True),
                    ('quarantine', True),
                    ('worker_failure', {'stage': 'assemble_words', 'reason': 'empty_asr'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-2',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('padded_retry', 'empty'),
                    ('padded_retry_empty', True),
                    ('quarantine', True),
                    ('worker_failure', {'stage': 'assemble_words', 'reason': 'empty_asr'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-1', 'owner-1']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_recovery_c1_always_single():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('always')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {
        'seg-1': result_of('recovery', 'seg-1'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('padded_retry', 'empty'),
                    ('padded_retry_empty', True),
                    ('quarantine', True),
                    ('worker_failure', {'stage': 'assemble_words', 'reason': 'empty_asr'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        )
    ]
    assert merge.drained == ['owner-1']
    assert {'owner-1': 1} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_recovery_c1_always_two_seg_same_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('always')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1'), work('seg-2', 'owner-1')]
    result_map = {
        'seg-1': result_of('recovery', 'seg-1'),
        'seg-2': result_of('recovery', 'seg-2'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('padded_retry', 'empty'),
                    ('padded_retry_empty', True),
                    ('quarantine', True),
                    ('worker_failure', {'stage': 'assemble_words', 'reason': 'empty_asr'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-2',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('padded_retry', 'empty'),
                    ('padded_retry_empty', True),
                    ('quarantine', True),
                    ('worker_failure', {'stage': 'assemble_words', 'reason': 'empty_asr'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-1', 'owner-1']
    assert {'owner-1': 2} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_recovery_c1_first_two_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('first')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-a', 'owner-a'), work('seg-b', 'owner-b')]
    result_map = {
        'seg-a': result_of('recovery', 'seg-a'),
        'seg-b': result_of('recovery', 'seg-b'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-a',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('padded_retry', 'empty'),
                    ('padded_retry_empty', True),
                    ('quarantine', True),
                    ('worker_failure', {'stage': 'assemble_words', 'reason': 'empty_asr'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('padded_retry', 'empty'),
                    ('padded_retry_empty', True),
                    ('quarantine', True),
                    ('worker_failure', {'stage': 'assemble_words', 'reason': 'empty_asr'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-a', 'owner-b']
    assert {'owner-a': 1, 'owner-b': 1} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_recovery_c4_first_single():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('first')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {
        'seg-1': result_of('recovery', 'seg-1'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('padded_retry', 'empty'),
                    ('padded_retry_empty', True),
                    ('quarantine', True),
                    ('worker_failure', {'stage': 'assemble_words', 'reason': 'empty_asr'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        )
    ]
    assert merge.drained == ['owner-1']
    assert {'owner-1': 1} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_recovery_c4_first_two_seg_same_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('first')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1'), work('seg-2', 'owner-1')]
    result_map = {
        'seg-1': result_of('recovery', 'seg-1'),
        'seg-2': result_of('recovery', 'seg-2'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('padded_retry', 'empty'),
                    ('padded_retry_empty', True),
                    ('quarantine', True),
                    ('worker_failure', {'stage': 'assemble_words', 'reason': 'empty_asr'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-2',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('padded_retry', 'empty'),
                    ('padded_retry_empty', True),
                    ('quarantine', True),
                    ('worker_failure', {'stage': 'assemble_words', 'reason': 'empty_asr'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-1']
    assert {'owner-1': 1} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_recovery_c4_always_single():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('always')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {
        'seg-1': result_of('recovery', 'seg-1'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('padded_retry', 'empty'),
                    ('padded_retry_empty', True),
                    ('quarantine', True),
                    ('worker_failure', {'stage': 'assemble_words', 'reason': 'empty_asr'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        )
    ]
    assert merge.drained == ['owner-1']
    assert {'owner-1': 1} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_recovery_c4_always_two_seg_same_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('always')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1'), work('seg-2', 'owner-1')]
    result_map = {
        'seg-1': result_of('recovery', 'seg-1'),
        'seg-2': result_of('recovery', 'seg-2'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('padded_retry', 'empty'),
                    ('padded_retry_empty', True),
                    ('quarantine', True),
                    ('worker_failure', {'stage': 'assemble_words', 'reason': 'empty_asr'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-2',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('padded_retry', 'empty'),
                    ('padded_retry_empty', True),
                    ('quarantine', True),
                    ('worker_failure', {'stage': 'assemble_words', 'reason': 'empty_asr'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-1']
    assert {'owner-1': 1} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_recovery_c4_first_two_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('first')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-a', 'owner-a'), work('seg-b', 'owner-b')]
    result_map = {
        'seg-a': result_of('recovery', 'seg-a'),
        'seg-b': result_of('recovery', 'seg-b'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-a',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('padded_retry', 'empty'),
                    ('padded_retry_empty', True),
                    ('quarantine', True),
                    ('worker_failure', {'stage': 'assemble_words', 'reason': 'empty_asr'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', 1.5),
                    ('padded_retry', 'empty'),
                    ('padded_retry_empty', True),
                    ('quarantine', True),
                    ('worker_failure', {'stage': 'assemble_words', 'reason': 'empty_asr'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-a', 'owner-b']
    assert {'owner-a': 1, 'owner-b': 1} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_failed_c1_first_single():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('first')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {
        'seg-1': result_of('failed', 'seg-1'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 2.5),
                    ('worker_failure_evidence', {'stage': 'vad_windows', 'reason': 'unsupported_language'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        )
    ]
    assert merge.drained == ['owner-1']
    assert {'owner-1': 1} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_failed_c1_first_two_seg_same_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('first')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1'), work('seg-2', 'owner-1')]
    result_map = {
        'seg-1': result_of('failed', 'seg-1'),
        'seg-2': result_of('failed', 'seg-2'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 2.5),
                    ('worker_failure_evidence', {'stage': 'vad_windows', 'reason': 'unsupported_language'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-2',
            (
                (
                    ('measured_held_vad_speech_seconds', 2.5),
                    ('worker_failure_evidence', {'stage': 'vad_windows', 'reason': 'unsupported_language'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-1', 'owner-1']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_failed_c1_always_single():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('always')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {
        'seg-1': result_of('failed', 'seg-1'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 2.5),
                    ('worker_failure_evidence', {'stage': 'vad_windows', 'reason': 'unsupported_language'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        )
    ]
    assert merge.drained == ['owner-1']
    assert {'owner-1': 1} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_failed_c1_always_two_seg_same_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('always')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1'), work('seg-2', 'owner-1')]
    result_map = {
        'seg-1': result_of('failed', 'seg-1'),
        'seg-2': result_of('failed', 'seg-2'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 2.5),
                    ('worker_failure_evidence', {'stage': 'vad_windows', 'reason': 'unsupported_language'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-2',
            (
                (
                    ('measured_held_vad_speech_seconds', 2.5),
                    ('worker_failure_evidence', {'stage': 'vad_windows', 'reason': 'unsupported_language'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-1', 'owner-1']
    assert {'owner-1': 2} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_failed_c1_first_two_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('first')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-a', 'owner-a'), work('seg-b', 'owner-b')]
    result_map = {
        'seg-a': result_of('failed', 'seg-a'),
        'seg-b': result_of('failed', 'seg-b'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-a',
            (
                (
                    ('measured_held_vad_speech_seconds', 2.5),
                    ('worker_failure_evidence', {'stage': 'vad_windows', 'reason': 'unsupported_language'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', 2.5),
                    ('worker_failure_evidence', {'stage': 'vad_windows', 'reason': 'unsupported_language'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-a', 'owner-b']
    assert {'owner-a': 1, 'owner-b': 1} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_failed_c4_first_single():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('first')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {
        'seg-1': result_of('failed', 'seg-1'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 2.5),
                    ('worker_failure_evidence', {'stage': 'vad_windows', 'reason': 'unsupported_language'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        )
    ]
    assert merge.drained == ['owner-1']
    assert {'owner-1': 1} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_failed_c4_first_two_seg_same_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('first')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1'), work('seg-2', 'owner-1')]
    result_map = {
        'seg-1': result_of('failed', 'seg-1'),
        'seg-2': result_of('failed', 'seg-2'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 2.5),
                    ('worker_failure_evidence', {'stage': 'vad_windows', 'reason': 'unsupported_language'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-2',
            (
                (
                    ('measured_held_vad_speech_seconds', 2.5),
                    ('worker_failure_evidence', {'stage': 'vad_windows', 'reason': 'unsupported_language'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-1']
    assert {'owner-1': 1} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_failed_c4_always_single():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('always')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {
        'seg-1': result_of('failed', 'seg-1'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 2.5),
                    ('worker_failure_evidence', {'stage': 'vad_windows', 'reason': 'unsupported_language'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        )
    ]
    assert merge.drained == ['owner-1']
    assert {'owner-1': 1} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_failed_c4_always_two_seg_same_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('always')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1'), work('seg-2', 'owner-1')]
    result_map = {
        'seg-1': result_of('failed', 'seg-1'),
        'seg-2': result_of('failed', 'seg-2'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', 2.5),
                    ('worker_failure_evidence', {'stage': 'vad_windows', 'reason': 'unsupported_language'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-2',
            (
                (
                    ('measured_held_vad_speech_seconds', 2.5),
                    ('worker_failure_evidence', {'stage': 'vad_windows', 'reason': 'unsupported_language'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-1']
    assert {'owner-1': 1} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_failed_c4_first_two_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('first')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-a', 'owner-a'), work('seg-b', 'owner-b')]
    result_map = {
        'seg-a': result_of('failed', 'seg-a'),
        'seg-b': result_of('failed', 'seg-b'),
    }
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-a',
            (
                (
                    ('measured_held_vad_speech_seconds', 2.5),
                    ('worker_failure_evidence', {'stage': 'vad_windows', 'reason': 'unsupported_language'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', 2.5),
                    ('worker_failure_evidence', {'stage': 'vad_windows', 'reason': 'unsupported_language'}),
                    ('worker_vad_receipt', {'receipt': True}),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-a', 'owner-b']
    assert {'owner-a': 1, 'owner-b': 1} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_missing_c1_first_single():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('first')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', None),
                    ('worker_failure_evidence', None),
                    ('worker_vad_receipt', None),
                )
            ),
        )
    ]
    assert merge.drained == ['owner-1']
    assert {'owner-1': 1} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_missing_c1_first_two_seg_same_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('first')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1'), work('seg-2', 'owner-1')]
    result_map = {}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', None),
                    ('worker_failure_evidence', None),
                    ('worker_vad_receipt', None),
                )
            ),
        ),
        (
            'fail',
            'seg-2',
            (
                (
                    ('measured_held_vad_speech_seconds', None),
                    ('worker_failure_evidence', None),
                    ('worker_vad_receipt', None),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-1', 'owner-1']
    assert {} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    await pump.flush_deferred_drains()


async def test_matrix_missing_c1_always_single():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('always')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', None),
                    ('worker_failure_evidence', None),
                    ('worker_vad_receipt', None),
                )
            ),
        )
    ]
    assert merge.drained == ['owner-1']
    assert {'owner-1': 1} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_missing_c1_always_two_seg_same_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('always')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1'), work('seg-2', 'owner-1')]
    result_map = {}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', None),
                    ('worker_failure_evidence', None),
                    ('worker_vad_receipt', None),
                )
            ),
        ),
        (
            'fail',
            'seg-2',
            (
                (
                    ('measured_held_vad_speech_seconds', None),
                    ('worker_failure_evidence', None),
                    ('worker_vad_receipt', None),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-1', 'owner-1']
    assert {'owner-1': 2} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_missing_c1_first_two_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('first')
    pump, clock = make_pump(merge, 1)
    pump.scheduler = scheduler
    leases = [work('seg-a', 'owner-a'), work('seg-b', 'owner-b')]
    result_map = {}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-a',
            (
                (
                    ('measured_held_vad_speech_seconds', None),
                    ('worker_failure_evidence', None),
                    ('worker_vad_receipt', None),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', None),
                    ('worker_failure_evidence', None),
                    ('worker_vad_receipt', None),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-a', 'owner-b']
    assert {'owner-a': 1, 'owner-b': 1} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_missing_c4_first_single():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('first')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', None),
                    ('worker_failure_evidence', None),
                    ('worker_vad_receipt', None),
                )
            ),
        )
    ]
    assert merge.drained == ['owner-1']
    assert {'owner-1': 1} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_missing_c4_first_two_seg_same_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('first')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1'), work('seg-2', 'owner-1')]
    result_map = {}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', None),
                    ('worker_failure_evidence', None),
                    ('worker_vad_receipt', None),
                )
            ),
        ),
        (
            'fail',
            'seg-2',
            (
                (
                    ('measured_held_vad_speech_seconds', None),
                    ('worker_failure_evidence', None),
                    ('worker_vad_receipt', None),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-1']
    assert {'owner-1': 1} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_missing_c4_always_single():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('always')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1')]
    result_map = {}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', None),
                    ('worker_failure_evidence', None),
                    ('worker_vad_receipt', None),
                )
            ),
        )
    ]
    assert merge.drained == ['owner-1']
    assert {'owner-1': 1} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_missing_c4_always_two_seg_same_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('always')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-1', 'owner-1'), work('seg-2', 'owner-1')]
    result_map = {}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-1',
            (
                (
                    ('measured_held_vad_speech_seconds', None),
                    ('worker_failure_evidence', None),
                    ('worker_vad_receipt', None),
                )
            ),
        ),
        (
            'fail',
            'seg-2',
            (
                (
                    ('measured_held_vad_speech_seconds', None),
                    ('worker_failure_evidence', None),
                    ('worker_vad_receipt', None),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-1']
    assert {'owner-1': 1} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()


async def test_matrix_missing_c4_first_two_owner():
    scheduler = ScriptScheduler()
    scheduler.complete_ok = True
    scheduler.fail_ok = True
    scheduler.defer_ok = True
    merge = ScriptMerge('first')
    pump, clock = make_pump(merge, 4)
    pump.scheduler = scheduler
    leases = [work('seg-a', 'owner-a'), work('seg-b', 'owner-b')]
    result_map = {}
    lost = set()
    await pump._publish_flight(leases, result_map, lost)
    assert scheduler.calls == [
        (
            'fail',
            'seg-a',
            (
                (
                    ('measured_held_vad_speech_seconds', None),
                    ('worker_failure_evidence', None),
                    ('worker_vad_receipt', None),
                )
            ),
        ),
        (
            'fail',
            'seg-b',
            (
                (
                    ('measured_held_vad_speech_seconds', None),
                    ('worker_failure_evidence', None),
                    ('worker_vad_receipt', None),
                )
            ),
        ),
    ]
    assert merge.drained == ['owner-a', 'owner-b']
    assert {'owner-a': 1, 'owner-b': 1} == {o: v["attempts"] for o, v in pump._deferred_drains.items()}
    assert pump._deferred_lane is not None
    await pump.flush_deferred_drains()

"""New native recordings jump bulk repair without changing custody or provider policy."""

from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from config.record_drain import record_intake_priority
from config.policy import resolve_batch_policy
from utils.batch_pipeline import record_provider
from utils.batch_pipeline.contracts import Priority, WorkItem, ProjectionBinding
from utils.batch_pipeline.scheduler import Scheduler
from tests.unit.test_batch_pipeline_scheduler import MemoryStore

NOW = 2000000


@pytest.mark.parametrize(
    'age,expected',
    [
        (0, Priority.FRESH),
        (120, Priority.FRESH),
        (600, Priority.FRESH),
        (601, Priority.RECENT),
        (86400, Priority.RECENT),
        (604800, Priority.RECENT),
        (604801, Priority.DEEP),
    ],
)
def test_priority_uses_finished_time(age, expected):
    assert record_intake_priority(datetime.fromtimestamp(NOW - age, timezone.utc), NOW) == expected


@pytest.mark.parametrize(
    'clock', [None, True, 'unknown', datetime(2026, 1, 1), datetime.fromtimestamp(NOW + 100, timezone.utc)]
)
def test_unknown_or_future_finish_cannot_claim_fresh_priority(clock):
    assert record_intake_priority(clock, NOW) == Priority.RECENT


def test_priority_kill_switch_restores_previous_fresh_class(monkeypatch):
    monkeypatch.setenv('RECORD_INTAKE_AGE_PRIORITY_ENABLED', 'false')
    assert record_intake_priority(datetime.fromtimestamp(0, timezone.utc), NOW) == Priority.FRESH


def native(segment, finished, *, owner='synthetic', partial=False):
    item = WorkItem(
        segment, owner, finished - 3600, 'gs://synthetic/audio', 3600, Priority.FRESH, conversation_id='capture'
    )
    binding = ProjectionBinding(
        owner,
        f'job-{segment}',
        f'content-{segment}',
        (segment,),
        language='en',
        target_conversation_id='capture',
        record_origin=True,
        native_record=True,
        partial_record=partial,
    )
    return item, binding


@pytest.mark.parametrize('partial', [False, True])
def test_both_native_paths_are_classified_before_admission(monkeypatch, partial):
    item, binding = native('old', NOW - 86400, partial=partial)
    admit = Mock(return_value={'outcome': 'batch'})
    monkeypatch.setattr(record_provider, 'admit', admit)
    barrier = {'finished_at': datetime.fromtimestamp(NOW - 86400, timezone.utc)}
    policy = resolve_batch_policy('synthetic')
    record_provider.admit_record_units(
        object(), [item], binding, NOW, policy=policy, record_barrier=barrier, require_artifacts=True
    )
    assert admit.call_args.args[1][0].priority == Priority.RECENT
    assert admit.call_args.kwargs['policy'] is policy
    assert admit.call_args.kwargs['record_barrier'] is barrier
    assert admit.call_args.kwargs['require_artifacts'] is True


def test_new_recording_pulls_ahead_of_bulk_repair_even_for_the_same_owner(monkeypatch):
    store = MemoryStore()
    queue = Scheduler(store)

    def enqueue(store, items, binding, now, **kwargs):
        for item in items:
            queue.enqueue(item, now)
        return {'outcome': 'batch'}

    monkeypatch.setattr(record_provider, 'admit', enqueue)
    policy = resolve_batch_policy('synthetic')
    for i in range(40):
        item, binding = native(f'old-{i}', NOW - 86400)
        record_provider.admit_record_units(
            store,
            [item],
            binding,
            NOW,
            policy=policy,
            record_barrier={'finished_at': datetime.fromtimestamp(NOW - 86400, timezone.utc)},
        )
    fresh, binding = native('just-ended', NOW - 120)  # one-hour recording ended two minutes ago
    record_provider.admit_record_units(
        store,
        [fresh],
        binding,
        NOW,
        policy=policy,
        record_barrier={'finished_at': datetime.fromtimestamp(NOW - 120, timezone.utc)},
    )
    assert queue.pull(NOW, 1)[0].item.segment_id == 'just-ended'
    assert store.rows['jobs', 'old-0']['priority'] == int(Priority.RECENT)
    # The independent merge/guard cohort keeps its existing capture-age
    # semantics; changing scheduling class must not relabel old results fresh.
    assert store.rows['jobs', 'old-0']['fresh_capture'] is False
    assert store.rows['jobs', 'just-ended']['fresh_capture'] is True


def test_classification_never_promotes_already_lower_priority(monkeypatch):
    item, binding = native('lower', NOW - 120)
    admit = Mock()
    monkeypatch.setattr(record_provider, 'admit', admit)
    record_provider.admit_record_units(
        object(),
        [replace(item, priority=Priority.DEEP)],
        binding,
        NOW,
        policy=resolve_batch_policy('synthetic'),
        record_barrier={'finished_at': datetime.fromtimestamp(NOW - 120, timezone.utc)},
    )
    assert admit.call_args.args[1][0].priority == Priority.DEEP

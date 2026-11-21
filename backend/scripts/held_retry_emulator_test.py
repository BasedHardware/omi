"""PL-532/533: durable retry grants and commit-owned spent signals on every Store.

The production scheduler and recovery fence run unchanged on old Firestore,
replacement Postgres and the reference simulator. CI requires sim/emulator;
complete local qualification requires OMI_REQUIRE_STORE_BACKENDS=all. Customer
authority on Postgres uses the existing harness seam, not the serving A4 bridge.
No provider, audio storage or production data is accessed.
"""

from copy import deepcopy
from dataclasses import asdict

import pytest

from config import backlog_state_machine as switches
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_projection_protocol import ProjectionBlocked
from database.batch_pipeline_quarantine_recovery import RecoveryStore
from testing.store_fixtures import store_backend  # noqa: F401
from utils import backlog_metrics
from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem
from utils.batch_pipeline.scheduler import Scheduler

pytestmark = pytest.mark.integration
T0 = 1_800_000_000.0


@pytest.fixture
def h(store_backend, monkeypatch):  # noqa: F811
    monkeypatch.setenv('OMI_ENV_STAGE', 'offline')
    monkeypatch.setenv(switches.RETRY_CAP_SWITCH, 'true')
    monkeypatch.setenv(switches.HELD_REDRIVE_BUDGET_SWITCH, 'true')
    monkeypatch.setenv(switches.HELD_REDRIVE_COUNTER_SWITCH, 'true')
    monkeypatch.setenv('BATCH_PIPELINE_MAX_ATTEMPTS', '2')
    monkeypatch.delenv('CAPTURE_COVERAGE_MODE', raising=False)
    monkeypatch.delenv('CAPTURE_COVERAGE_UID_ALLOWLIST', raising=False)
    return store_backend


def read(h, table='jobs', key='speech'):
    return h.store.run(lambda tx: tx.get(table, key))


def patch(h, fields, table='jobs', key='speech'):
    def commit(tx):
        row = tx.get(table, key)
        tx.put(table, key, {**row, **fields})

    h.store.run(commit)


def seed(h, *, redrives=0, dead=False):
    owner = h.seed_user('held-retry')
    item = WorkItem('speech', owner, T0, 'gs://synthetic/retained-input#17', 4, Priority.FRESH)
    queue = Scheduler(h.store)
    assert queue.enqueue(item, T0)
    (lease,) = queue.pull(T0)
    assert queue.fail(item.segment_id, lease.token, T0 + 1, quarantine=True)
    binding = ProjectionBinding(owner, 'upload', 'synthetic-content', (item.segment_id,))

    def bind(tx):
        row = tx.get('jobs', item.segment_id)
        row.update(
            projection_binding=asdict(binding),
            attempt=2,
            held_redrives=redrives,
            recovery={'token': 'spent-provider-intent', 'settled_at': T0 + 1, 'privacy_generation': 0},
        )
        if dead:
            row.update(state='dead', merge_pending=True, dead_letter_reason='held_expired', held_expired_at=T0 + 2)
        tx.put('jobs', item.segment_id, row)
        tx.put(
            'content',
            f'{owner}/{binding.content_id}',
            {
                'dispatch_protocol': 'batch_v1',
                'status': 'processing',
                'job_id': binding.job_id,
                'batch_pipeline': {'protocol_version': 1, 'namespace': h.namespace, 'segment_ids': ['speech']},
            },
        )

    h.store.run(bind)
    return binding


def retained(row):
    return {
        key: deepcopy(row[key])
        for key in ('audio_uri', 'capture_at', 'duration_seconds', 'projection_binding', 'recovery')
    }


def requeue(h, entry, now, **kwargs):
    if entry == 'recovery':
        return RecoveryStore(h.store).requeue_quarantined('speech', now, **kwargs)
    assert not kwargs
    return Scheduler(h.store).redrive_dead('speech', now)


def hold_again(h, now, *, dead=False):
    queue = Scheduler(h.store)
    (lease,) = queue.pull(now)
    assert queue.fail('speech', lease.token, now + 1, quarantine=True)
    fields = {'attempt': 2}
    if dead:
        fields.update(state='dead', merge_pending=True, dead_letter_reason='held_expired')
    patch(h, fields)


@pytest.mark.parametrize('rollback', ['grant', 'cap'])
def test_pl532_rollback_keeps_issued_grants_and_preserves_attempts_across_restart(h, monkeypatch, rollback):
    seed(h)
    before = retained(read(h))
    assert requeue(h, 'recovery', T0 + 10)
    granted = read(h)
    assert (granted['attempt'], granted['held_redrive_last_attempt'], granted['held_redrives']) == (0, 2, 1)
    switch = switches.HELD_REDRIVE_BUDGET_SWITCH if rollback == 'grant' else switches.RETRY_CAP_SWITCH
    monkeypatch.setenv(switch, 'false')
    assert read(h) == granted  # Changing policy must not claw back an issued grant.

    attempts = []
    for n in range(4):
        # Reconstruct the real coordinator each turn; no process-local retry budget.
        queue = Scheduler(h.store)
        now = T0 + 1000 + n * 1000
        queue.recover(now)
        leases = queue.pull(now)
        if not leases:
            break
        assert len(leases) == 1 and leases[0].item.segment_id == 'speech'
        attempts.append(leases[0].attempt)
        assert queue.recover(now + 121) == 1
        assert retained(read(h)) == before
    assert attempts == ([1, 2] if rollback == 'grant' else [1, 2, 3, 4])
    settled = read(h)
    assert settled['attempt'] == attempts[-1]
    assert settled['held_redrives'] == 1 and settled['held_redrive_last_attempt'] == 2
    if rollback == 'grant':
        assert settled['state'] == 'quarantined'
        assert requeue(h, 'recovery', T0 + 10000)
        later = read(h)
        assert (later['attempt'], later['held_redrives'], later['held_redrive_last_attempt']) == (2, 2, 2)
    else:
        assert settled['state'] != 'quarantined'


def test_pl532_only_three_held_redrives_can_grant_a_fresh_attempt_budget(h):
    seed(h)
    original = retained(read(h))
    for number in range(1, 6):
        assert requeue(h, 'recovery', T0 + number * 10)
        row = read(h)
        assert row['held_redrives'] == number
        assert row['attempt'] == (0 if number <= 3 else 2)
        assert row['held_redrive_last_attempt'] == 2
        assert retained(row) == original
        hold_again(h, T0 + number * 10 + 1)


@pytest.mark.parametrize('entry', ['recovery', 'scheduler'])
@pytest.mark.parametrize('counter', ['true', 'false'])
def test_pl533_spent_marker_commits_with_the_winner_and_never_repages(h, monkeypatch, entry, counter):
    seed(h, redrives=3, dead=True)
    original = retained(read(h))
    monkeypatch.setenv(switches.HELD_REDRIVE_COUNTER_SWITCH, counter)
    events = []

    def observe(event):
        # A callback reading the actual backend must see the committed transition.
        row = read(h)
        assert row['state'] == 'ready' and row['held_redrives'] == 4
        assert row['held_redrive_budget_spent_at'] == T0 + 10
        events.append(event)

    monkeypatch.setattr(backlog_metrics, 'record_transition', observe)
    assert requeue(h, entry, T0 + 10)
    row = read(h)
    assert row['held_redrives'] == 4 and row['held_redrive_budget_spent_at'] == T0 + 10
    assert retained(row) == original
    assert not requeue(h, entry, T0 + 11)  # Duplicate delivery loses the state CAS.
    assert events == (['held_redrive_budget_spent'] if counter == 'true' else [])

    monkeypatch.setenv(switches.HELD_REDRIVE_COUNTER_SWITCH, 'true')
    hold_again(h, T0 + 12, dead=True)
    assert requeue(h, entry, T0 + 20)
    assert read(h)['held_redrives'] == 5
    assert read(h)['held_redrive_budget_spent_at'] == T0 + 10
    assert events == (['held_redrive_budget_spent'] if counter == 'true' else [])


@pytest.mark.parametrize('entry', ['recovery', 'scheduler'])
@pytest.mark.parametrize('fence', ['privacy', 'content', 'active'])
def test_pl533_refused_redrives_change_no_accounting_or_signal(h, monkeypatch, entry, fence):
    binding = seed(h, redrives=3, dead=True)
    if fence == 'privacy':
        h.customer.block_privacy(binding.owner_id)
    elif fence == 'content':
        patch(h, {'job_id': 'replacement-owner'}, 'content', f'{binding.owner_id}/{binding.content_id}')
    else:
        patch(h, {'token': 'active-worker'})
    before = read(h)
    events = []
    monkeypatch.setattr(backlog_metrics, 'record_transition', events.append)
    if fence == 'active':
        assert not requeue(h, entry, T0 + 10)
    else:
        with pytest.raises(BatchPrivacyBlocked if fence == 'privacy' else ProjectionBlocked):
            requeue(h, entry, T0 + 10)
    assert read(h) == before and events == []


class AbortedProbe(RuntimeError):
    pass


@pytest.mark.parametrize('entry', ['recovery', 'scheduler'])
@pytest.mark.parametrize('retry', [False, True])
def test_pl533_aborted_transaction_cannot_spend_or_emit_and_body_retry_emits_once(h, monkeypatch, entry, retry):
    seed(h, redrives=3, dead=True)
    before = read(h)
    original_run = h.store.run
    events = []
    monkeypatch.setattr(backlog_metrics, 'record_transition', events.append)

    def run(body):
        def abort(tx):
            body(tx)
            raise AbortedProbe('synthetic abort before Store flush')

        if not retry:
            return original_run(abort)
        with pytest.raises(AbortedProbe):
            original_run(abort)
        assert original_run(lambda tx: tx.get('jobs', 'speech')) == before
        assert events == []
        return original_run(body)

    # Both attempts use real Store transactions; no fake commit or query is used.
    with monkeypatch.context() as scoped:
        scoped.setattr(h.store, 'run', run)
        if retry:
            assert requeue(h, entry, T0 + 10)
        else:
            with pytest.raises(AbortedProbe):
                requeue(h, entry, T0 + 10)
    after = read(h)
    if retry:
        assert after['held_redrives'] == 4 and after['held_redrive_budget_spent_at'] == T0 + 10
        assert events == ['held_redrive_budget_spent']
    else:
        assert after == before and events == []


@pytest.mark.parametrize('repair', ['snapshot', 'input_expiring', 'stale_snapshot'])
def test_pl533_staging_repairs_never_consume_held_grants_or_page(h, monkeypatch, repair):
    seed(h, redrives=3, dead=True)
    if repair == 'input_expiring':
        patch(h, {'dead_letter_reason': 'input_expiring'})
    before = read(h)
    expected = deepcopy(before)
    if repair == 'stale_snapshot':
        expected['attempt'] = 1
    events = []
    monkeypatch.setattr(backlog_metrics, 'record_transition', events.append)
    kwargs = {} if repair == 'input_expiring' else {'expected_job': expected}
    assert requeue(h, 'recovery', T0 + 10, **kwargs) is (repair != 'stale_snapshot')
    after = read(h)
    assert after['attempt'] == before['attempt'] and after['held_redrives'] == 3
    assert 'held_redrive_budget_spent_at' not in after
    assert retained(after) == retained(before) and events == []
    if repair == 'stale_snapshot':
        assert after == before

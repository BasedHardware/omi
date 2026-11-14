"""Synthetic ghost hints: release/expiry gaps and the repair's active follow-up.

Loopback Firestore only, using the existing projection lane's anonymous client.
The former strict xfails are regressions for the flagged automatic exit.
All storage here is synthetic and emulator-only.
"""

import asyncio
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from config.batch_pipeline import HELD_DEAD_LETTER_SECONDS
from database import batch_pipeline_projection_release as release_module
from database.batch_pipeline_projection_release import (
    RELEASE_PAGE,
    RELEASE_TICK_SECONDS,
    ProjectionReleaseStore,
    expired_page_ids,
    release_scan_pass,
)
from database.batch_pipeline_store import projection_page
from scripts import reconcile_batch_projection_ghost_holds as repair_module
from scripts.reconcile_batch_projection_ghost_holds import reconcile
from tests.integration.test_batch_pipeline_projection_firestore import lane
from utils.batch_pipeline.contracts import ProjectionBinding
from utils.batch_pipeline.held_dead_letter import ProjectionHeldDeadLetter
from utils.batch_pipeline.scheduler import owner_key

pytestmark = pytest.mark.integration
NOW = 40 * 86400.0
GHOSTS = ('a-ghost-none', 'b-ghost-recovered')
RESTORABLE, MISSING, PRIVACY = 'c-real-restorable', 'd-real-missing', 'e-privacy'


@pytest.fixture
def holds(lane, monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_HOLD_RECOVERY_ENABLED', 'true')
    monkeypatch.delenv('BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_COHORT', raising=False)
    monkeypatch.setenv('BATCH_HELD_DEAD_LETTER_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_FOLLOWUP_PAGE_ENABLED', 'true')
    projection = lane.projector.store
    for segment in (*GHOSTS, RESTORABLE, MISSING, PRIVACY):
        binding = ProjectionBinding(
            lane.uid,
            f'job-{segment}',
            f'content-{segment}',
            (segment,),
            target_conversation_id=f'target-{segment}',
            record_origin=True,
            data_protection_level='standard',
        )
        if segment != MISSING:
            lane.user.collection('conversations').document(binding.target_conversation_id).set(
                {'status': 'completed', 'record_lane_owner': 'batch_sync_v1'}
            )
        ghost = segment in GHOSTS
        projection.ref('jobs', segment).set(
            {
                'owner_id': lane.uid,
                'state': 'committed',
                'projection_binding': asdict(binding),
                'recovery_state': (None if segment == GHOSTS[0] else 'recovered') if ghost else 'held',
                'audio_uri': 'gs://synthetic/retained-audio#1',
            }
        )
        projection.ref('results', segment).set(
            {
                'segment_id': segment,
                'owner_key': owner_key(lane.uid),
                'committed_at': 1.0,
                'projection_state': 'quarantine_held',
                'protocol_version': 2,
                'payload': {'words': ['synthetic retained output']},
                'projection': (
                    {'state': 'ready'}
                    if ghost
                    else {
                        'state': 'quarantined',
                        'disposition': 'ambiguous_generation',
                        'quarantine_reason': 'conversation_missing' if segment == MISSING else 'record_conflict',
                        'held_speech_seconds': 3.0,
                    }
                ),
                **(
                    {
                        'projection_privacy_refusal': {
                            'version': 1,
                            'reason': 'recording_privacy_changed',
                            'held_at': 1.0,
                        }
                    }
                    if segment == PRIVACY
                    else {}
                ),
            }
        )
    return lane


def snapshot(lane, kind):
    return {doc.id: doc.to_dict() for doc in lane.client.collection(f'{lane.store.namespace}_{kind}').stream()}


def scan(lane, now, caplog):
    caplog.clear()
    counts, _ = release_scan_pass(lane.projector.store, limit=RELEASE_PAGE, after_id=None, now=now)
    # release_page's fetch failure returns zero counts; it does not increment
    # error. Neither a swallowed fetch failure nor a transaction failure is the
    # selector gap. RuntimeError deliberately falls outside raises=AssertionError.
    if counts['error'] or any(
        record.name == release_module.__name__ and 'outcome=retry' in record.getMessage() for record in caplog.records
    ):
        raise RuntimeError('release scan retry/error is not the expected selector gap')
    if not counts['examined']:
        raise RuntimeError('release scan examined no rows; this is not the expected selector gap')
    return counts


def test_real_hold_releases_missing_target_waits_then_expires_privacy_is_fenced(holds, caplog):
    projection = holds.projector.store
    before = snapshot(holds, 'results')
    before_jobs = snapshot(holds, 'jobs')
    privacy_job = projection.ref('jobs', PRIVACY).get().to_dict()
    # Passing mixed-page control: all five result classes are actually examined.
    # Ghost exit expectations are covered by the flag-on regressions below.
    assert scan(holds, NOW, caplog)['examined'] >= 5
    release = ProjectionReleaseStore(projection)
    released = projection.ref('results', RESTORABLE).get().to_dict()
    assert released['projection_state'] == 'pending' and released['projection'] == {}
    assert projection.ref('jobs', RESTORABLE).get().to_dict() == {
        **before_jobs[RESTORABLE],
        'recovery_state': None,
    }
    assert released['payload'] == before[RESTORABLE]['payload']
    assert not release.release(MISSING, NOW) and not release.expired
    waiting = projection.ref('results', MISSING).get().to_dict()
    deadline = NOW + HELD_DEAD_LETTER_SECONDS
    assert waiting == {**before[MISSING], 'held_deadline_at': deadline}
    assert not release.release(MISSING, deadline - 1) and not release.expired
    assert projection.ref('results', MISSING).get().to_dict() == waiting
    assert not release.release(MISSING, deadline) and release.expired
    assert projection.ref('results', MISSING).get().to_dict() == {
        **waiting,
        'held_expired_at': deadline,
        'held_expired_reason': 'held_expired',
    }
    assert not release.release(MISSING, deadline + 1) and not release.expired
    assert MISSING in expired_page_ids(holds.client, holds.store.namespace, RELEASE_PAGE, None)
    assert not release.release(PRIVACY, NOW)
    assert not release.release(PRIVACY, deadline)
    assert projection.ref('results', PRIVACY).get().to_dict() == before[PRIVACY]
    assert projection.ref('jobs', PRIVACY).get().to_dict() == privacy_job


@pytest.mark.parametrize('segment', GHOSTS, ids=['recovery-none', 'recovery-recovered'])
def test_ghost_hold_release_normalizes_ready_hint(holds, segment, caplog, monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_ENABLED', 'true')
    scan(holds, NOW, caplog)
    # Automatic repair uses the normal ready discovery state.
    row = holds.projector.store.ref('results', segment).get().to_dict()
    assert row['projection_state'] == 'ready'
    assert row['ghost_settled_cohort'] == 'g1'


@pytest.mark.parametrize('segment', GHOSTS, ids=['recovery-none', 'recovery-recovered'])
def test_aged_ghost_exits_via_ready_without_expiry(holds, segment, caplog, monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_ENABLED', 'true')
    scan(holds, NOW, caplog)
    scan(holds, NOW + HELD_DEAD_LETTER_SECONDS, caplog)
    ProjectionHeldDeadLetter(holds.store).tick(NOW + HELD_DEAD_LETTER_SECONDS + 86400)
    entry = holds.projector.store.ref('results', segment).get().to_dict()
    assert entry['projection_state'] == 'ready'
    assert 'held_expired_reason' not in entry
    assert 'held_deadline_at' not in entry


@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('recovery_state', [None, 'held'])
@pytest.mark.parametrize('deadline', [None, NOW - 1])
def test_completed_assignment_receipt_cannot_expire(holds, monkeypatch, enabled, recovery_state, deadline):
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_ENABLED', str(enabled).lower())
    projection = holds.projector.store
    segment = GHOSTS[0]
    projection.ref('jobs', segment).update({'recovery_state': recovery_state})
    if deadline is not None:
        projection.ref('results', segment).update({'held_deadline_at': deadline})
    before = {kind: projection.ref(kind, segment).get().to_dict() for kind in ('jobs', 'results')}
    release = ProjectionReleaseStore(projection)
    assert not release.release(segment, NOW)
    assert not release.expired
    settled = enabled and recovery_state != 'held'
    assert release.ghost_settled is settled
    assert projection.ref('jobs', segment).get().to_dict() == before['jobs']
    assert projection.ref('results', segment).get().to_dict() == {
        **before['results'],
        **(
            {
                'projection_state': 'ready',
                'ghost_settled_cohort': 'g1',
                'projection_finish_due_at': NOW,
                'projection_finish_backoff_step': 0,
            }
            if settled
            else {}
        ),
    }


@pytest.mark.parametrize('failure', ['fetch', 'transaction'])
def test_expected_gap_cannot_hide_scan_failures(holds, monkeypatch, caplog, failure):
    def fail(*args, **kwargs):
        raise RuntimeError('synthetic scan failure')

    if failure == 'fetch':
        monkeypatch.setattr(release_module, 'held_page_ids', fail)
    else:
        monkeypatch.setattr(ProjectionReleaseStore, 'release', fail)
    with pytest.raises(RuntimeError, match='scan retry/error'):
        scan(holds, NOW, caplog)


def test_reconcile_only_repairs_ghost_hints_and_is_idempotent(holds, monkeypatch):
    script_clock = Mock(wraps=repair_module.time)
    script_clock.time.return_value = NOW
    monkeypatch.setattr(repair_module, 'time', script_clock)
    before_results, before_jobs = snapshot(holds, 'results'), snapshot(holds, 'jobs')
    dry = reconcile(holds.client, holds.store.namespace, batch_size=1)
    assert dry == dict(scanned=5, matched=2, updated=0, conflicts=0, errors=0, deadline_reached=0)
    assert snapshot(holds, 'results') == before_results
    applied = reconcile(holds.client, holds.store.namespace, apply=True, batch_size=1)
    assert applied == {**dry, 'updated': 2}
    assert snapshot(holds, 'results') == {
        segment: {
            **row,
            **(
                {'projection_state': 'ready', 'projection_finish_due_at': NOW, 'projection_finish_backoff_step': 0}
                if segment in GHOSTS
                else {}
            ),
        }
        for segment, row in before_results.items()
    }
    assert snapshot(holds, 'jobs') == before_jobs
    assert set(projection_page(holds.client, holds.store.namespace, states=('ready',))[0]) == set(GHOSTS)
    assert reconcile(holds.client, holds.store.namespace, apply=True, batch_size=1) == {
        **dry,
        'scanned': 3,
        'matched': 0,
    }


def seed_targeted_batch(lane):
    """Persist a completed target before projecting a bound batch's ready receipt."""
    batch = lane.seed()
    target = batch.items[0].conversation_id
    batch.binding = replace(batch.binding, target_conversation_id=target)
    lane.projector.store.ref('jobs', batch.ids[0]).update({'projection_binding': asdict(batch.binding)})
    lane.user.collection('conversations').document(target).set(
        {
            'id': target,
            'source': 'omi',
            'started_at': datetime.fromtimestamp(1000, timezone.utc),
            'finished_at': datetime.fromtimestamp(1030, timezone.utc),
            'created_at': datetime.fromtimestamp(1000, timezone.utc),
            'transcript_segments': [],
            'is_locked': False,
            'status': 'completed',
            'record_lane_owner': 'batch_sync_v1',
            'structured': {},
            'data_protection_level': 'standard',
        }
    )
    return batch


@pytest.mark.parametrize('recovery_state', [None, 'recovered'], ids=['recovery-none', 'recovery-recovered'])
def test_repaired_ready_hint_completes_ledger_and_publishes_without_reassignment(lane, monkeypatch, recovery_state):
    monkeypatch.delenv('BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_COHORT', raising=False)
    batch = seed_targeted_batch(lane)
    lane.finish(batch)
    segment = batch.ids[0]

    def crash_before_completion(*args, **kwargs):
        raise RuntimeError('synthetic stop after ready receipt')

    with monkeypatch.context() as patch:
        patch.setattr(lane.projector, 'complete_content', crash_before_completion)
        with pytest.raises(RuntimeError, match='synthetic stop after ready receipt'):
            lane.projector.project(segment)
    ref = lane.projector.store.ref('results', segment)
    ready = deepcopy(ref.get().to_dict())
    assert ready['projection']['state'] == 'ready'
    ref.update({'projection_state': 'quarantine_held'})
    lane.projector.store.ref('jobs', segment).update({'recovery_state': recovery_state})
    assert batch.ledger.get().to_dict()['status'] == 'processing'
    assert not lane.published
    assert projection_page(lane.client, lane.store.namespace, states=('ready',))[0] == []
    loads, tasks = list(lane.loads), list(lane.tasks)
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_ENABLED', 'true')
    committed_at = ready['committed_at']
    counts, _ = release_scan_pass(lane.projector.store, limit=RELEASE_PAGE, after_id=None, now=committed_at + 86400)
    assert counts['ghost_settled'] == 1
    assert ref.get().to_dict() == {
        **ready,
        'ghost_settled_cohort': 'g1',
        'projection_finish_due_at': committed_at + 86400,
        'projection_finish_backoff_step': 0,
    }
    assert projection_page(lane.client, lane.store.namespace, states=('ready',))[0] == [segment]
    # Drive the ordinary ready-receipt replay path, including the real ledger,
    # accounting and acknowledgement transactions. Only external publication
    # and enqueue are captured by the established emulator lane fixture.
    result = lane.projector.project(segment)
    assert result is not None and result['updated_memories'] == [ready['projection']['conversation_id']]
    assert batch.ledger.get().to_dict()['status'] == 'completed'
    assert lane.projector.status(lane.uid, batch.binding.content_id)['status'] == 'completed'
    assert lane.published == [result]
    assert ref.get().to_dict()['projection_state'] == 'completed'
    assert ref.get().to_dict()['ghost_settled_cohort'] == 'g1'
    assert lane.loads == loads and lane.tasks == tasks
    accounting = lane.projector.store.prepare_accounting(batch.binding, NOW)
    assert accounting['completed'] and not accounting['updates']
    completed_ledger = batch.ledger.get().to_dict()
    assert lane.projector.project(segment) == result
    assert batch.ledger.get().to_dict() == completed_ledger
    assert lane.loads == loads and lane.tasks == tasks
    # Publication is intentionally replayed to repair a lost client reply;
    # the real publisher owns its idempotency fence, not this captured callback.
    assert lane.published == [result, result]


@pytest.mark.skip(
    reason='Rows examined in a 5s tick depend on emulator RPC latency and host load; page 128 is a cap, not throughput'
)
def test_release_scan_throughput_5s_page128():
    assert RELEASE_TICK_SECONDS == 5.0 and RELEASE_PAGE == 128


def test_flag_off_classifies_ghosts_without_mutating_them(holds, monkeypatch, caplog):
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_ENABLED', 'false')
    before_results, before_jobs = snapshot(holds, 'results'), snapshot(holds, 'jobs')
    counts = scan(holds, NOW, caplog)
    assert counts['ghost_settled'] == 0 and counts['ghost_skipped_count_only'] == 2
    for segment in GHOSTS:
        assert holds.projector.store.ref('results', segment).get().to_dict() == before_results[segment]
        assert holds.projector.store.ref('jobs', segment).get().to_dict() == before_jobs[segment]


@pytest.mark.parametrize(
    'kind,changes,skip',
    [
        ('results', {'projection_state': 'pending'}, 'hint_changed'),
        ('results', {'projection': {'state': 'persisted'}}, 'receipt_not_ready'),
        ('results', {'projection_parts': {'0': {'state': 'quarantined'}}}, 'part_quarantined'),
        ('target', None, 'target_not_restorable'),
        ('target', {'deleted': True}, 'target_not_restorable'),
        ('target', {'discarded': True}, 'target_not_restorable'),
        ('target', {'status': 'in_progress'}, 'target_not_restorable'),
        ('results', {'projection_privacy_refusal': {'version': 1}}, 'privacy'),
        ('results', {'owner_key': 'foreign'}, 'binding'),
        ('jobs', {'recovery_state': 'held'}, 'job_held'),
        ('jobs', {'state': 'quarantined'}, 'job_not_committed'),
        ('results', {'committed_at': NOW - 86399}, 'young'),
    ],
)
def test_page_selection_cannot_authorize_changed_ghost(holds, monkeypatch, kind, changes, skip):
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_ENABLED', 'true')
    projection = holds.projector.store
    segment = GHOSTS[0]
    before = {}

    def selected_page(*args):
        # A writer changes authority after the page was selected. release()
        # must use its transaction-fresh documents, never page-time predicates.
        if kind == 'target':
            target = holds.user.collection('conversations').document(f'target-{segment}')
            target.delete() if changes is None else target.update(changes)
        else:
            projection.ref(kind, segment).update(changes)
        before.update({name: projection.ref(name, segment).get().to_dict() for name in ('jobs', 'results')})
        return [segment]

    monkeypatch.setattr(release_module, 'held_page_ids', selected_page)
    counts, _ = release_module.release_page(projection, limit=1, after_id=None, now=NOW)
    assert counts['error'] == 0 and counts['ghost_settled'] == 0
    assert counts[f'ghost_skipped_{skip}'] == 1
    assert {name: projection.ref(name, segment).get().to_dict() for name in before} == before


def test_transaction_retry_counts_only_one_committed_ghost(holds, monkeypatch, caplog):
    from google.api_core.exceptions import Aborted
    from google.cloud.firestore_v1.transaction import Transaction

    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_COHORT', 'invalid/label')
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_ENABLED', 'true')
    segment = GHOSTS[0]
    monkeypatch.setattr(release_module, 'held_page_ids', lambda *a: [segment])
    original = Transaction._commit
    attempts = []

    def commit(transaction):
        if transaction._write_pbs:
            attempts.append(True)
            if len(attempts) == 1:
                # Model a server abort, including release of its read locks.
                # Raising locally without rollback leaves a live emulator tx.
                transaction._rollback()
                raise Aborted('synthetic commit contention')
        return original(transaction)

    monkeypatch.setattr(Transaction, '_commit', commit)
    counts, _ = release_module.release_page(holds.projector.store, limit=1, after_id=None, now=NOW)
    assert len(attempts) == 2
    assert counts['error'] == 0 and counts['ghost_settled'] == counts['ghost_classified'] == 1
    assert counts['ghost_age_30d_plus'] == 1
    assert sum('event=batch_projection_ghost_cohort' in r.getMessage() for r in caplog.records) == 1
    row = holds.projector.store.ref('results', segment).get().to_dict()
    assert row['projection_state'] == 'ready'
    assert row['ghost_settled_cohort'] == 'g1'


def test_cohort_equality_only_counts_and_inert_non_ghost_rows(holds, monkeypatch, caplog):
    from google.cloud.firestore_v1.base_query import FieldFilter, And

    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_COHORT', 'G_2-drain')
    scan(holds, NOW, caplog)
    results = holds.client.collection(f'{holds.store.namespace}_results')
    for segment in (RESTORABLE, MISSING, PRIVACY):
        assert 'ghost_settled_cohort' not in results.document(segment).get().to_dict()
    # Same six aggregate shapes as the canary: only equality conjunctions,
    # with a separate count per blocked state. No OR/IN or composite index.
    # Emulator execution cannot prove prod index availability; HTTP 400 stays UNKNOWN.
    cohort = FieldFilter('ghost_settled_cohort', '==', 'G_2-drain')
    blocked = ('pending', 'persisted', 'quarantine_held')
    for index, state in enumerate(('completed', *blocked, 'erased', 'quarantined')):
        results.document(f'cohort-count-{index}').set({'ghost_settled_cohort': 'G_2-drain', 'projection_state': state})
    results.document('other-cohort').set({'ghost_settled_cohort': 'g2', 'projection_state': 'ready'})
    queries = [
        results.where(filter=cohort),
        results.where(filter=And([cohort, FieldFilter('projection_state', '==', 'ready')])),
        results.where(filter=And([cohort, FieldFilter('projection_state', '==', 'completed')])),
        *[results.where(filter=And([cohort, FieldFilter('projection_state', '==', state)])) for state in blocked],
    ]
    total, ready, completed, *blocked_counts = [q.count(alias='total').get()[0][0].value for q in queries]
    assert (total, ready, completed) == (8, 2, 1)
    assert dict(zip(blocked, blocked_counts)) == {'pending': 1, 'persisted': 1, 'quarantine_held': 1}
    blocked_total = sum(blocked_counts)
    assert blocked_total == 3
    assert total - ready - completed - blocked_total == 2


def test_invalid_cohort_fallback_survives_real_transaction(holds, monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_COHORT', 'bad/label')
    release = ProjectionReleaseStore(holds.projector.store)
    assert not release.release(GHOSTS[0], NOW) and release.ghost_settled
    assert holds.projector.store.ref('results', GHOSTS[0]).get().to_dict()['ghost_settled_cohort'] == 'g1'


@pytest.mark.asyncio
@pytest.mark.parametrize('refusal', [None, 'conversation_deleted', 'account_deleted'])
async def test_settle_wake_tail_uses_real_completion_and_rechecks_privacy(lane, monkeypatch, refusal):
    from database.batch_pipeline_privacy import BatchPrivacyBlocked
    from utils.batch_pipeline.projection_followup import ProjectionFollowups

    monkeypatch.setenv('BATCH_PIPELINE_ASYNC_PROJECTION_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_ENABLED', 'true')
    monkeypatch.delenv('BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_WAKE_ENABLED', raising=False)
    batch = seed_targeted_batch(lane)
    lane.finish(batch)
    segment = batch.ids[0]
    complete = lane.projector.complete_content
    with monkeypatch.context() as patch:
        patch.setattr(lane.projector, 'complete_content', Mock(side_effect=RuntimeError('stop before completion')))
        with pytest.raises(RuntimeError, match='stop before completion'):
            lane.projector.project(segment)
    ref = lane.projector.store.ref('results', segment)
    ready = ref.get().to_dict()
    assert ready['projection']['state'] == 'ready'
    ref.update({'projection_state': 'quarantine_held'})
    monkeypatch.setattr(lane.projector, 'clock', lambda: ready['committed_at'] + 86400)
    assert lane.projector.release_held_scan()['ghost_settled'] == 1
    assert lane.projector.chain_followups == [segment]
    assert ref.get().to_dict()['committed_at'] == ready['committed_at']
    assert not lane.published
    loads, tasks = list(lane.loads), list(lane.tasks)

    if refusal == 'conversation_deleted':
        lane.user.collection('deleted_conversations').document(batch.items[0].conversation_id).set({'deleted': True})
        lane.user.collection('conversations').document(ready['projection']['conversation_id']).delete()
    elif refusal == 'account_deleted':
        lane.client.collection('account_deletions').document(lane.uid).set({'wipe_status': 'queued'})
    if refusal:
        # Exercise the completion transaction itself as well as the follow-up's
        # earlier check: neither entry point may publish a now-fenced source.
        with pytest.raises(BatchPrivacyBlocked) as error:
            complete(segment, batch.binding)
        assert error.value.reason == refusal
        assert not lane.published

    completion = Mock(wraps=complete)
    monkeypatch.setattr(lane.projector, 'complete_content', completion)
    runner = ProjectionFollowups(lane.projector)
    lane.projector.followups = runner
    # Keep discovery beyond the row: only the new tail handoff can offer it.
    monkeypatch.setattr(runner, 'candidates', lambda: [])
    await lane.projector.start_followups()
    while runner.tasks:
        await asyncio.wait_for(asyncio.gather(*list(runner.tasks.values())), 30)
    assert not lane.projector.chain_followups and not runner.owed
    if refusal:
        assert not lane.published
        assert batch.ledger.get().to_dict()['status'] == 'processing'
        assert ref.get().to_dict()['projection_state'] != 'completed'
    else:
        completion.assert_called_once_with(segment, batch.binding)
        assert ref.get().to_dict()['projection_state'] == 'completed'
        assert batch.ledger.get().to_dict()['status'] == 'completed'
        assert len(lane.published) == 1
    assert lane.loads == loads and lane.tasks == tasks

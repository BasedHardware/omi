"""Pre-PR main and new workers against real loopback Firestore transactions.

No cloud fallback. These tests inherit the isolated synthetic project fixture.
"""

from contextlib import contextmanager
from copy import deepcopy

import pytest

from database import batch_pipeline_conversation_purge as purge
from database import batch_pipeline_conversation_purge_scans as scans
from database import conversation_batch_purge_jobs as jobs
from tests.integration.test_conversation_purge_coalescing_emulator import (
    _assert_erased,
    _dispatch,
    _expire,
    _run,
    _seed,
    world,  # noqa: F401
)
from tests.integration.test_conversation_batch_purge_emulator import plane  # noqa: F401
from tests.support.pre_coalescing_worker import load_worker

pytestmark = pytest.mark.integration


@pytest.fixture
def old(monkeypatch, world):
    old = load_worker()
    # Only external side effects differ from production. Runner, traversal,
    # leases, journals, row deletion and transaction retries are the old source.
    monkeypatch.setattr(old.purge, 'conversation_objects', lambda *a, **k: [])
    monkeypatch.setattr(old.purge, 'purge_jobstore_owner', lambda *a: 0)
    monkeypatch.setattr(old.purge, 'mirror_refresh', lambda *a: None)
    monkeypatch.setattr(old.jobs, 'UNIT_YIELD_SECONDS', 0)
    return old


def _old_run(old, world, job, generation, **kwargs):
    return old.jobs.run_job(job, generation, firestore_client=world.client, sleep=lambda _: None, **kwargs)


def _row(world, job):
    return world.client.collection(jobs.COLLECTION).document(job).get().to_dict()


def _redrive(monkeypatch, old, world):
    # This reconciler is unchanged from pre-PR main. Use its old jobs API and
    # replace only Cloud Tasks transport/probing; the SDK due query and claim
    # transaction actually run. Acknowledged tasks are no longer queued.
    from utils.conversations import deletion_batch_purge as reconcile

    queued = []
    with monkeypatch.context() as scoped:
        scoped.setattr(reconcile, 'purge_jobs', old.jobs)
        scoped.setattr(reconcile, 'is_conversation_batch_purge_dispatch_configured', lambda: True)
        scoped.setattr(reconcile, 'conversation_batch_purge_consumer_ready', lambda: True)
        scoped.setattr(reconcile, 'conversation_batch_purge_task_pending', lambda *a, **k: False)
        scoped.setattr(reconcile, 'enqueue_conversation_batch_purge', lambda job, gen, **k: queued.append((job, gen)))
        counts = reconcile.reconcile_conversation_batch_purges()
    assert counts.get('dispatched', 0) == len(queued)
    return queued


def test_disabled_coalescing_allows_both_binaries_to_finish_redriven_tasks(monkeypatch, world, old):
    monkeypatch.setenv(scans.SWITCH, 'off')
    cids = ['one', 'two', 'three', 'four']
    ids = [world.arm(cid) for cid in cids]
    _seed(world, cids)
    for n, job in enumerate(ids):
        generation = _dispatch(world, job)
        runner = _run if n % 2 else lambda *a, **k: _old_run(old, *a, **k)
        # Interrupt each real legacy traversal at its first checkpoint.
        assert runner(world, job, generation, budget_seconds=0) == 'checkpointed'
        row = _row(world, job)
        assert not row.get('owner_scan') and not row.get('scan_epoch')
        assert row.get('progress')
    queued = _redrive(monkeypatch, old, world)
    assert {job for job, _ in queued} == set(ids)
    for n, (job, generation) in enumerate(queued):
        # Swap versions on redrive: old -> new and new -> old.
        if ids.index(job) % 2:
            assert _old_run(old, world, job, generation) == 'purged'
        else:
            assert _run(world, job, generation) == 'purged'
    _assert_erased(world, cids)


@pytest.mark.parametrize('role', ['leader', 'follower'])
def test_actual_old_delivery_into_leased_group_is_acknowledged_then_redriven(monkeypatch, world, old, role):
    cids = ['one', 'two']
    leader, follower = [world.arm(cid) for cid in cids]
    original = {job: _dispatch(world, job) for job in (leader, follower)}
    _seed(world, cids)
    _, scan = scans._claim(world.client, leader, original[leader])
    # A leaked old binary during rollback must not consume the shared cursor.
    progress = scans.ScanProgress(world.client, leader, scan, sleep=lambda _: None)
    progress.checkpoint({'ns': 1, 'phase': 'segments'})
    job = leader if role == 'leader' else follower
    assert _old_run(old, world, job, scan['members'][job]['generation']) == 'in_progress'
    if role == 'follower':
        assert _old_run(old, world, job, original[job]) == 'superseded'
    assert _row(world, job) and _row(world, leader)['owner_scan']['position']['ns'] == 1
    # Simulate the pre-floor binary receiving tasks after leases expire.
    _expire(world, scan)
    queued = _redrive(monkeypatch, old, world)
    assert {key for key, _ in queued} == {leader, follower}
    for key, generation in queued:
        assert _old_run(old, world, key, generation) == 'purged'
    _assert_erased(world, cids)


@pytest.mark.parametrize('role', ['leader', 'follower'])
@pytest.mark.parametrize('switch', ['on', 'off'])
def test_old_takeover_mid_group_then_new_worker_never_rejoins_stale_cursor(monkeypatch, world, old, role, switch):
    cids = ['one', 'two']
    leader, follower = [world.arm(cid) for cid in cids]
    generation = _dispatch(world, leader)
    _seed(world, cids)
    _, scan = scans._claim(world.client, leader, generation)
    progress = scans.ScanProgress(world.client, leader, scan, sleep=lambda _: None)
    progress.add_segments(follower, purge.NAMESPACES[0], ['mine-1'])
    progress.checkpoint({'ns': 2})  # Must never be used by the old binary or successor.
    _expire(world, scan)
    job = leader if role == 'leader' else follower
    pages = []
    query = old.purge.queries.owner_documents

    def observe(client, ns, table, key, **kwargs):
        pages.append((ns, table, kwargs.get('after')))
        return query(client, ns, table, key, **kwargs)

    with monkeypatch.context() as scoped:
        scoped.setattr(old.purge.queries, 'owner_documents', observe)
        assert _old_run(old, world, job, scan['members'][job]['generation'], budget_seconds=0) == 'checkpointed'
    assert pages[0] == (purge.NAMESPACES[0], 'jobs', None)
    original_progress = deepcopy(_row(world, job)['progress'])
    with pytest.raises(jobs.RunSuperseded):
        progress.finish('completed')
    # Kill-switch handback must keep a replacement old worker's progress AND
    # each member's canonical journal, including the segment-only fallback.
    journals = {
        key: jobs.segment_records(key, purge.NAMESPACES[0], firestore_client=world.client) for key in (leader, follower)
    }
    monkeypatch.setenv(scans.SWITCH, switch)
    assert scans._claim(world.client, leader, generation) == ('legacy', None)
    assert _row(world, job)['progress'] == original_progress
    for key in (leader, follower):
        assert jobs.segment_records(key, purge.NAMESPACES[0], firestore_client=world.client) == journals[key]
        row = _row(world, key)
        assert not row.get('scan_epoch')
        assert _run(world, key, row['generation']) == 'purged'
    _assert_erased(world, cids)


def test_readiness_metadata_is_never_a_job_for_either_version(monkeypatch, world, old):
    marker = world.client.collection(jobs.COLLECTION).document('_owner_scan_v1_readiness')
    marker.set({'all_consumers_new': True})
    assert marker.id != jobs.job_id(world.uid, marker.id)
    assert old.jobs.claim_dispatch(marker.id, firestore_client=world.client) is None
    assert jobs.claim_dispatch(marker.id, firestore_client=world.client) is None
    assert old.jobs.due_jobs(firestore_client=world.client) == []
    assert jobs.due_jobs(firestore_client=world.client) == []
    assert scans.owner_candidates(world.uid, firestore_client=world.client) == []
    assert _redrive(monkeypatch, old, world) == []
    assert marker.get().exists


@pytest.mark.parametrize('when', ['during_seal', 'after_seal', 'after_checkpoint'])
@pytest.mark.parametrize('producer', ['old', 'new'])
def test_rearm_during_and_after_sealing_is_not_completed_by_old_group(monkeypatch, world, old, when, producer):
    cids = ['one', 'two']
    leader, follower = [world.arm(cid) for cid in cids]
    generation = _dispatch(world, leader)
    _seed(world, cids)

    def rearm():
        fields = (old.jobs if producer == 'old' else jobs).arm_fields(world.uid, 'two')
        world.client.collection(jobs.COLLECTION).document(follower).set(fields, merge=True)
        return fields

    armed = []
    candidates = scans.owner_candidates

    def during_seal(*args, **kwargs):
        snapshots = candidates(*args, **kwargs)
        armed.append(rearm())  # stale enumeration, fresh transactional seal reads
        return snapshots

    with monkeypatch.context() as scoped:
        if when == 'during_seal':
            scoped.setattr(scans, 'owner_candidates', during_seal)
        _, scan = scans._claim(world.client, leader, generation)
    progress = scans.ScanProgress(world.client, leader, scan, sleep=lambda _: None)
    if when == 'during_seal':
        assert scan['members'][follower]['armed_at'] == armed[0]['armed_at']
        progress.check_authority()
    else:
        if when == 'after_checkpoint':
            progress.checkpoint({'ns': 1, 'phase': 'discover'})
        rearm()
        with pytest.raises(jobs.RunSuperseded):
            progress.finish('completed')
        assert scans.handback(world.client, leader, scan['epoch'], scan['token'])
        assert _row(world, follower)
    # New rows behind a shared cursor and a newly armed post-seal conversation
    # must be visited by a fresh successor, never added to the old membership.
    late = world.arm('late')
    assert late not in scan['members']
    if when == 'during_seal':
        scans.handback(world.client, leader, scan['epoch'], scan['token'])
    _seed(world, [*cids, 'late'])
    assert _run(world, leader, generation) == 'purged'
    _assert_erased(world, [*cids, 'late'])


def test_switch_off_mid_group_hands_journals_back_before_legacy(monkeypatch, world, old):
    cids = ['one', 'two']
    leader, follower = [world.arm(cid) for cid in cids]
    generation = _dispatch(world, leader)
    _seed(world, cids)
    query = purge.queries.owner_documents
    before = {}

    def interrupt(client, ns, table, key, **kwargs):
        rows = query(client, ns, table, key, **kwargs)
        if table == 'artifacts' and not before:
            for job in (leader, follower):
                before[job] = (
                    deepcopy(_row(world, job).get('progress')),
                    jobs.segment_records(job, ns, firestore_client=client),
                )
                assert before[job][1]
            monkeypatch.setenv(scans.SWITCH, 'false')
        return rows

    with monkeypatch.context() as scoped:
        scoped.setattr(purge.queries, 'owner_documents', interrupt)
        assert _run(world, leader, generation) == 'superseded'
    for job, (position, segments) in before.items():
        row = _row(world, job)
        assert row.get('progress') == position and not row.get('scan_epoch')
        assert jobs.segment_records(job, purge.NAMESPACES[0], firestore_client=world.client) == segments
    queued = _redrive(monkeypatch, old, world)
    assert {job for job, _ in queued} == {leader, follower}
    for job, gen in queued:
        assert _old_run(old, world, job, gen) == 'purged'
    _assert_erased(world, cids)


def test_frozen_old_rearm_gap_demonstrates_why_the_floor_is_required(monkeypatch, world, old):
    """Reproduce the old binary's limitation on synthetic data, then recover it.

    The release floor excludes old binaries that cannot compare arm revisions.
    """
    cids = ['one', 'two']
    leader, follower = [world.arm(cid) for cid in cids]
    generation = _dispatch(world, leader)
    _seed(world, cids)
    _, scan = scans._claim(world.client, leader, generation)
    _expire(world, scan)
    rearmed = []

    def rearm_after_first_namespace(ns, uid):
        if not rearmed:
            world.arm('one')
            world.client.collection(f'{ns}_results').document('rearmed-behind-cursor').set(
                {'owner_key': world.key, 'owner_id': uid, 'conversation_id': 'one', 'segment_id': 'rearmed'}
            )
            rearmed.append(True)
        return 0

    monkeypatch.setattr(old.purge, 'purge_jobstore_owner', rearm_after_first_namespace)
    assert _old_run(old, world, leader, generation) == 'purged'
    assert rearmed and not _row(world, leader)
    remaining = world.client.collection(f'{purge.NAMESPACES[0]}_results').document('rearmed-behind-cursor')
    assert remaining.get().to_dict().get('projection_state') != 'erased'
    # Old completion ignored the re-arm. The follower's stale delegation keeps
    # it out of a new group. Per-conversation recovery can still erase the row.
    world.arm('one')
    generation = _dispatch(world, leader)
    assert scans._claim(world.client, leader, generation) == ('legacy', None)
    assert _run(world, leader, generation) == 'purged'
    row = _row(world, follower)
    assert _run(world, follower, row['generation']) == 'purged'
    assert remaining.get().to_dict()['projection_state'] == 'erased'
    _assert_erased(world, cids)


@pytest.mark.parametrize('boundary', ['checkpoint', 'unit', 'completion'])
def test_new_legacy_rearm_behind_cursor_is_redriven_without_early_completion(monkeypatch, world, boundary):
    """A real fallback traversal passes the new row before its obligation is re-armed."""
    monkeypatch.setenv(scans.SWITCH, 'off')
    leader = world.arm('one')
    _seed(world, ['one'])
    generation = _dispatch(world, leader)
    rearmed = []
    original_finish = jobs.finish_run

    def rearm():
        world.arm('one')
        remaining = world.client.collection(f'{purge.NAMESPACES[0]}_results').document('behind-cursor')
        remaining.set({'owner_key': world.key, 'conversation_id': 'one', 'segment_id': 'behind-cursor'})
        rearmed.append(remaining)

    def shadow(namespace, uid):
        if namespace == purge.NAMESPACES[0] and not rearmed and boundary == 'checkpoint':
            rearm()
        return 0

    def finish(*args, **kwargs):
        if args[3] == 'completed' and not rearmed and boundary == 'completion':
            rearm()  # after every traversal checkpoint, immediately before completion's transaction
        return original_finish(*args, **kwargs)

    original_unit = jobs.RunProgress.unit

    @contextmanager
    def unit(self):
        changed = boundary == 'unit' and not rearmed and self.position.get('ns', 0) >= 1
        if changed:
            rearm()  # outside the previous unit, just before the next unit transaction
        with original_unit(self) as authority:
            assert not changed, 're-armed run entered destructive work'
            yield authority

    monkeypatch.setattr(jobs.RunProgress, 'unit', unit)
    monkeypatch.setattr(purge, 'purge_jobstore_owner', shadow)
    monkeypatch.setattr(jobs, 'finish_run', finish)
    assert _run(world, leader, generation) == 'superseded'
    row = _row(world, leader)
    assert row['last_outcome'] == 'rearmed' and row['progress'] == {}
    assert row['lease_until'] is None and row['run_token'] is None
    assert rearmed[0].get().to_dict()['conversation_id'] == 'one'
    next_generation = _dispatch(world, leader)
    assert next_generation == generation + 1
    assert _run(world, leader, next_generation) == 'purged'
    assert not _row(world, leader)
    assert rearmed[0].get().to_dict()['projection_state'] == 'erased'
    _assert_erased(world, ['one'])

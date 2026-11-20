"""Hermetic old-binary admission proofs; actual takeover/erasure runs in emulator."""

from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from database import batch_pipeline_conversation_purge_scans as scans
from database import conversation_batch_purge_jobs as jobs
from tests.support.pre_coalescing_worker import load_worker
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore


@pytest.fixture
def versions(monkeypatch):
    old = load_worker()
    client = StrictFirestore()
    monkeypatch.delenv(scans.SWITCH, raising=False)
    for module in (jobs, scans, old.jobs):
        monkeypatch.setattr(module, '_in_transaction', lambda client, body: body(client.transaction()))
    monkeypatch.setattr(old.jobs.rpc_deadline, 'bind_firestore_client', lambda client: client)
    leader, follower = jobs.job_id('owner', 'one'), jobs.job_id('owner', 'two')
    members = {}
    for job, cid in ((leader, 'one'), (follower, 'two')):
        arm = jobs.arm_fields('owner', cid)
        members[job] = {**arm, 'generation': 2}
        client.collection(jobs.COLLECTION).document(job).create(
            {
                **arm,
                'generation': 2,
                'lease_generation': 2,
                'run_token': 'shared',
                'lease_until': jobs._now() + timedelta(seconds=300),
                'scan_epoch': 'epoch',
                'scan_leader': leader,
            }
        )
        client.document(f'users/owner/deleted_conversations/{cid}').create({'id': cid})
    scan = {'uid': 'owner', 'epoch': 'epoch', 'token': 'shared', 'members': members, 'position': {'ns': 2}}
    client.rows[(jobs.COLLECTION, leader)]['owner_scan'] = deepcopy(scan)
    return SimpleNamespace(old=old, client=client, leader=leader, follower=follower, scan=scan)


@pytest.mark.parametrize('role', ['leader', 'follower'])
@pytest.mark.parametrize('generation,outcome', [(1, 'superseded'), (2, 'in_progress')])
def test_actual_old_delivery_cannot_enter_live_group(monkeypatch, versions, role, generation, outcome):
    v = versions
    traversal = Mock(side_effect=AssertionError('old worker entered a live coalesced scan'))
    monkeypatch.setattr(v.old.purge, 'purge_conversation', traversal)
    before = deepcopy(v.client.rows)
    assert v.old.jobs.run_job(getattr(v, role), generation, firestore_client=v.client) == outcome
    assert v.client.rows == before
    traversal.assert_not_called()


@pytest.mark.parametrize('role', ['leader', 'follower'])
def test_old_takeover_ignores_shared_cursor_and_handback_retains_legacy_progress(monkeypatch, versions, role):
    v = versions
    job = getattr(v, role)
    row = v.client.rows[(jobs.COLLECTION, job)]
    row['lease_until'] = jobs._now() - timedelta(seconds=1)
    legacy_position = {'ns': 0, 'phase': 'discover', 'table': 1, 'after': 'old-page'}

    def checkpoint(uid, cid, progress, **kwargs):
        assert progress.position == {}  # never owner_scan.position == {ns: 2}
        progress.checkpoint(legacy_position)
        raise v.old.purge.PurgeCheckpointed()

    monkeypatch.setattr(v.old.purge, 'purge_conversation', checkpoint)
    monkeypatch.setattr(v.old.jobs, 'assert_account_deletion_permitted', lambda uid: None)
    assert v.old.jobs.run_job(job, 2, firestore_client=v.client) == 'checkpointed'
    assert scans.handback(v.client, v.leader, 'epoch', 'shared')
    row = v.client.rows[(jobs.COLLECTION, job)]
    assert row['progress'] == legacy_position
    assert not row.get('scan_epoch') and row.get('run_token') is None


def test_legacy_completion_succeeds_after_rearm_with_same_dispatch_generation(versions):
    v = versions
    row = v.client.rows[(jobs.COLLECTION, v.leader)]
    row['lease_until'] = jobs._now() - timedelta(seconds=1)
    claim, _, token = v.old.jobs.begin_run(v.leader, 2, firestore_client=v.client)
    assert claim == 'run'
    # An unchanged old producer or a new producer can re-arm without changing
    # dispatch generation. The old binary cannot compare that arm at completion.
    row.update(jobs.arm_fields('owner', 'one'))
    assert v.old.jobs.finish_run(v.leader, 2, token, 'completed', firestore_client=v.client)


@pytest.mark.parametrize('mode', ['seal', 'resume'])
def test_switch_rechecked_inside_seal_and_resume_transaction(monkeypatch, versions, mode):
    v = versions
    if mode == 'seal':
        for job in (v.leader, v.follower):
            row = v.client.rows[(jobs.COLLECTION, job)]
            for key in ('owner_scan', 'scan_leader', 'scan_epoch', 'lease_until', 'run_token', 'lease_generation'):
                row.pop(key, None)
    else:
        v.client.rows[(jobs.COLLECTION, v.leader)]['lease_until'] = None
    monkeypatch.setattr(
        scans,
        'owner_candidates',
        lambda *a, **k: [
            SimpleNamespace(id=job, reference=v.client.collection(jobs.COLLECTION).document(job))
            for job in (v.leader, v.follower)
        ],
    )
    monkeypatch.setattr(scans, 'enabled', Mock(side_effect=[True, False]))
    assert scans._claim(v.client, v.leader, 2) == ('legacy', None)
    assert all(not v.client.rows[(jobs.COLLECTION, job)].get('scan_epoch') for job in (v.leader, v.follower))


def test_dangling_leader_with_null_epoch_falls_back_without_inheriting_a_cursor(versions):
    v = versions
    v.client.rows[(jobs.COLLECTION, v.follower)]['scan_epoch'] = None
    v.client.rows[(jobs.COLLECTION, v.leader)]['owner_scan'] = None
    before = deepcopy(v.client.rows)
    assert scans._claim(v.client, v.follower, 2) == ('legacy', None)
    assert v.client.rows == before


@pytest.mark.parametrize('outcome', ['failed', 'busy'])
@pytest.mark.parametrize('superseded', [False, True])
def test_failed_settlement_preserves_original_task_error(monkeypatch, versions, outcome, superseded):
    v = versions
    original = RuntimeError('original destructive-unit failure')
    replacement = jobs.RunSuperseded() if superseded else RuntimeError('settlement failed')
    progress = SimpleNamespace(check_authority=Mock(), finish=Mock(side_effect=replacement))
    monkeypatch.setattr(scans, '_claim', lambda *a: ('run', v.scan))
    monkeypatch.setattr(scans, 'ScanProgress', lambda *a, **k: progress)
    monkeypatch.setattr(scans.legal_holds, 'assert_account_deletion_permitted', lambda uid: None)
    monkeypatch.setattr(scans, 'purge_conversations', Mock(side_effect=original))
    monkeypatch.setattr(scans.jobs, 'lost_gate_to_peer', lambda *a: outcome == 'busy')
    handback = Mock(side_effect=RuntimeError('handback also failed'))
    monkeypatch.setattr(scans, 'handback', handback)
    with pytest.raises(RuntimeError) as caught:
        scans.run_job(v.leader, 2, firestore_client=v.client)
    assert caught.value is original
    progress.finish.assert_called_once_with(outcome)
    assert handback.call_count == int(superseded)


@pytest.mark.parametrize('boundary', ['checkpoint', 'unit', 'segments_done', 'completion'])
@pytest.mark.parametrize('producer', ['new', 'old'])
def test_new_legacy_run_fences_rearms_at_every_write_boundary(monkeypatch, versions, boundary, producer):
    from contextlib import nullcontext

    v = versions
    ref = jobs.job_ref(v.client, 'owner', 'one')
    v.client.rows[(jobs.COLLECTION, v.leader)] = jobs.arm_fields('owner', 'one') | {'generation': 2}
    claim, row, token = jobs.begin_run(v.leader, 2, firestore_client=v.client)
    assert claim == 'run'
    progress = jobs.RunProgress(v.client, v.leader, 2, token, 'owner', row.get('progress'))
    progress.checkpoint({'ns': 1}, add_segments=('namespace', ['durable-segment']))
    saved = deepcopy(v.client.rows)
    arm = (
        jobs.arm_fields('owner', 'one')
        if producer == 'new'
        else {'armed_at': row['armed_at'] + timedelta(seconds=1), 'due_at': jobs._now()}
    )
    v.client.rows[ref.path].update(arm)
    monkeypatch.setattr(jobs.legal_holds, 'bounded_destructive_unit', lambda *a, **k: nullcontext(None))
    if boundary == 'completion':
        assert not jobs.finish_run(v.leader, 2, token, 'completed', firestore_client=v.client)
    else:
        with pytest.raises(jobs.RunSuperseded):
            if boundary == 'checkpoint':
                progress.checkpoint({'ns': 2}, add_segments=('namespace', ['not-authorized']))
            elif boundary == 'segments_done':
                progress.segments_done('namespace', ['durable-segment'])
            else:
                with progress.unit():
                    pytest.fail('stale arm entered destructive work')
        assert v.client.rows[ref.path]['progress'] == {'ns': 1}
        assert not jobs.finish_run(v.leader, 2, token, 'checkpointed', firestore_client=v.client)
    current = ref.get().to_dict()
    assert current['last_outcome'] == 'rearmed' and current['progress'] == {}
    assert current['lease_until'] is None and current['run_token'] is None
    assert {k: r for k, r in v.client.rows.items() if len(k) > 2} == {k: r for k, r in saved.items() if len(k) > 2}
    assert jobs.claim_dispatch(v.leader, firestore_client=v.client)[0] == 3
    claim, next_row, _ = jobs.begin_run(v.leader, 3, firestore_client=v.client)
    assert claim == 'run' and next_row['progress'] == {}


@pytest.mark.parametrize('stamp', ['matching', 'older', 'absent'])
def test_legacy_claim_resumes_only_progress_bound_to_its_current_arm(versions, stamp):
    v = versions
    arm = jobs.arm_fields('owner', 'one')
    cursor = {'ns': 1, 'phase': 'discover', 'table': 1, 'after': 'passed'}
    row = {**arm, 'generation': 2, 'progress': cursor}
    if stamp != 'absent':
        row['progress_arm'] = {key: arm[key] for key in ('armed_at', 'arm_revision')}
        if stamp == 'older':
            row['progress_arm']['arm_revision'] = 'earlier-arm'
    v.client.rows[(jobs.COLLECTION, v.leader)] = row
    journal = jobs.segment_ref(v.client, v.leader, 'namespace', 'durable')
    journal.create({'namespace': 'namespace', 'segment_id': 'durable'})
    claim, claimed, _ = jobs.begin_run(v.leader, 2, firestore_client=v.client)
    assert claim == 'run'
    assert claimed['progress'] == (cursor if stamp == 'matching' else {})
    assert journal.get().exists

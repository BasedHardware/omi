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


def test_old_completion_has_no_rearm_fence_so_readiness_is_required(versions):
    v = versions
    row = v.client.rows[(jobs.COLLECTION, v.leader)]
    row['lease_until'] = jobs._now() - timedelta(seconds=1)
    claim, _, token = v.old.jobs.begin_run(v.leader, 2, firestore_client=v.client)
    assert claim == 'run'
    # An unchanged old producer or a new producer can re-arm without changing
    # dispatch generation. The old binary cannot compare that arm at completion.
    row.update(jobs.arm_fields('owner', 'one'))
    assert v.old.jobs.finish_run(v.leader, 2, token, 'completed', firestore_client=v.client)
    # This is the frozen binary's limitation, not a supported mixed-group mode.
    # New enrollment must refuse absent readiness even though its switch is on.
    v.client.rows[(jobs.COLLECTION, v.leader)] = jobs.arm_fields('owner', 'one') | {'generation': 2}
    assert scans.enabled()
    assert scans._claim(v.client, v.leader, 2) == ('legacy', None)


@pytest.mark.parametrize(
    'marker', [None, {}, {'all_consumers_new': 'true'}, {'all_consumers_new': False}, 'expired', 'naive', 'unbounded']
)
def test_missing_stale_or_malformed_readiness_never_coalesces(monkeypatch, versions, marker):
    v = versions
    now = jobs._now()
    if isinstance(marker, dict) and 'all_consumers_new' in marker:
        marker = {**marker, 'valid_until': now + timedelta(hours=1)}
    if isinstance(marker, str):
        until = {
            'expired': now - timedelta(seconds=1),
            'naive': now.replace(tzinfo=None) + timedelta(hours=1),
            'unbounded': now + timedelta(days=2),
        }[marker]
        marker = {'all_consumers_new': True, 'valid_until': until}
    if marker is not None:
        v.client.collection(scans.READINESS_COLLECTION).document(scans.READINESS_DOCUMENT).create(marker)
    candidates = Mock(side_effect=AssertionError('mixed roll attempted enrollment'))
    monkeypatch.setattr(scans, 'owner_candidates', candidates)
    before = deepcopy(v.client.rows)
    assert scans._claim(v.client, v.leader, 2) == ('legacy', None)
    assert all(v.client.rows[key].get('progress') == value.get('progress') for key, value in before.items())
    assert all(v.client.rows[key].get('generation') == value.get('generation') for key, value in before.items())
    candidates.assert_not_called()


@pytest.mark.parametrize('mode', ['seal', 'resume'])
def test_readiness_rechecked_inside_seal_and_resume_transaction(monkeypatch, versions, mode):
    v = versions
    if mode == 'seal':
        for job in (v.leader, v.follower):
            row = v.client.rows[(jobs.COLLECTION, job)]
            for key in ('owner_scan', 'scan_leader', 'scan_epoch', 'lease_until', 'run_token', 'lease_generation'):
                row.pop(key, None)
    else:
        v.client.rows[(jobs.COLLECTION, v.leader)]['lease_until'] = None
    marker = (scans.READINESS_COLLECTION, scans.READINESS_DOCUMENT)
    v.client.rows[marker] = {'all_consumers_new': True, 'valid_until': jobs._now() + timedelta(hours=1)}
    monkeypatch.setattr(
        scans,
        'owner_candidates',
        lambda *a, **k: [
            SimpleNamespace(id=job, reference=v.client.collection(jobs.COLLECTION).document(job))
            for job in (v.leader, v.follower)
        ],
    )
    ready = scans.consumers_ready

    def revoke(client, transaction=None):
        if transaction is not None:
            client.rows[marker]['all_consumers_new'] = False
        return ready(client, transaction)

    monkeypatch.setattr(scans, 'consumers_ready', revoke)
    assert scans._claim(v.client, v.leader, 2) == ('legacy', None)
    assert all(not v.client.rows[(jobs.COLLECTION, job)].get('scan_epoch') for job in (v.leader, v.follower))


def test_unreadable_readiness_retries_instead_of_asserting_consumer_compatibility(monkeypatch, versions):
    v = versions
    before = deepcopy(v.client.rows)
    monkeypatch.setattr(scans, 'consumers_ready', Mock(side_effect=RuntimeError('synthetic control read failed')))
    with pytest.raises(RuntimeError, match='synthetic control read failed'):
        scans._claim(v.client, v.leader, 2)
    assert v.client.rows == before


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

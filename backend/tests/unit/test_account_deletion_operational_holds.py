"""Privacy erasure may release proven operational holds, never legal holds."""

from copy import deepcopy
import sqlite3
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import PreconditionFailed

from utils.other import account_deletion_holds as holds
from scripts import account_deletion_operational_holds as operator
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

UID = 'synthetic-owner'


class Blob:
    def __init__(self):
        self.name = f'syncing/{UID}/job/source.bin'
        self.bucket = SimpleNamespace(name='syncing-local')
        self.generation = 123
        self.metageneration = 2
        self.temporary_hold = True
        self.event_based_hold = False
        self.retention = SimpleNamespace(mode=None, retain_until_time=None)
        self.retention_expiration_time = None
        self.metadata = {}
        self.reload = MagicMock()
        self.patch = MagicMock(side_effect=self._patch)

    def _patch(self, **kwargs):
        assert kwargs == {'if_generation_match': 123, 'if_metageneration_match': 2}
        self.metageneration = 3


def approval(blob):
    plan = {
        'schema_version': 1,
        'campaign': 'expiry-20261017',
        'owner_sha256': holds.object_digest(UID),
        'objects': [
            {
                'bucket': 'syncing-local',
                'object_sha256': holds.object_digest(blob.name),
                'generation': '123',
                'metageneration': '2',
            }
        ],
    }
    return {
        'issuer': 'reviewed_operator',
        'approval_ref': 'operator-review:test',
        'plan': plan,
        'plan_sha256': holds.plan_digest(plan),
    }


@pytest.fixture
def setup(monkeypatch):
    blob = Blob()
    marker = {'wipe_status': 'running', 'operational_hold_release_approval': approval(blob)}
    receipt = {}
    marker_ref = MagicMock()
    marker_ref.get.side_effect = lambda: SimpleNamespace(exists=True, to_dict=lambda: deepcopy(marker))
    receipt_ref = marker_ref.collection.return_value.document.return_value
    receipt_ref.get.side_effect = lambda: SimpleNamespace(exists=bool(receipt), to_dict=lambda: deepcopy(receipt))
    receipt_ref.set.side_effect = lambda value: (receipt.clear(), receipt.update(deepcopy(value)))
    gate = MagicMock()
    legal = MagicMock()
    monkeypatch.setattr(holds, 'assert_destructive_gate_still_ours', gate)
    monkeypatch.setattr(holds, 'assert_account_deletion_permitted', legal)
    monkeypatch.setattr(holds, 'account_deletion_document', lambda *args, **kwargs: marker_ref)
    client = object()
    return SimpleNamespace(
        blob=blob, marker=marker, receipt=receipt, receipt_ref=receipt_ref, client=client, gate=gate, legal=legal
    )


def release(s):
    holds.release_operational_hold_for_account_deletion(UID, s.blob, firestore_client=s.client)


def test_approved_hold_released_with_cas_and_durable_intent(setup):
    s = setup
    writes = []
    original_set = s.receipt_ref.set.side_effect
    s.receipt_ref.set.side_effect = lambda value: (writes.append(value['state']), original_set(value))
    original_patch = s.blob.patch.side_effect
    s.blob.patch.side_effect = lambda **kwargs: (writes.append('patch'), original_patch(**kwargs))
    release(s)
    assert writes == ['release_pending', 'patch', 'released']
    assert s.blob.temporary_hold is False
    assert s.receipt['released_metageneration'] == '3'
    assert UID not in str(s.receipt)
    assert s.blob.name not in str(s.receipt)
    s.gate.assert_called_with(UID, 'account_deletion', token=f'account-deletion:{UID}', firestore_client=s.client)


@pytest.mark.parametrize(
    'field,value',
    [
        ('event_based_hold', True),
        ('retention_expiration_time', 'future'),
        ('metadata', {'legal_hold': 'true'}),
        ('metadata', {'unknown': 'preserve'}),
    ],
)
def test_equivalent_legal_or_unknown_hold_never_released(setup, field, value):
    s = setup
    setattr(s.blob, field, value)
    with pytest.raises(holds.OperationalStorageHoldBlocked, match='protected'):
        release(s)
    s.blob.patch.assert_not_called()
    s.receipt_ref.set.assert_not_called()


def test_object_retention_never_released(setup):
    s = setup
    s.blob.retention.mode = 'Unlocked'
    with pytest.raises(holds.OperationalStorageHoldBlocked, match='protected'):
        release(s)
    s.blob.patch.assert_not_called()


@pytest.mark.parametrize('gate_kind', ['gate', 'legal'])
def test_live_authority_failure_prevents_patch(setup, gate_kind):
    s = setup
    getattr(s, gate_kind).side_effect = RuntimeError('authority blocked')
    with pytest.raises(RuntimeError, match='authority blocked'):
        release(s)
    s.blob.patch.assert_not_called()


@pytest.mark.parametrize(
    'mutation', ['no_approval', 'other_owner', 'digest', 'generation', 'metageneration', 'not_running']
)
def test_unapproved_or_changed_identity_fails_closed(setup, mutation):
    s = setup
    if mutation == 'no_approval':
        s.marker.pop('operational_hold_release_approval')
    elif mutation == 'other_owner':
        s.marker['operational_hold_release_approval']['plan']['owner_sha256'] = '0' * 64
    elif mutation == 'digest':
        s.marker['operational_hold_release_approval']['plan_sha256'] = '0' * 64
    elif mutation == 'not_running':
        s.marker['wipe_status'] = 'failed'
    else:
        setattr(s.blob, mutation, 999)
    with pytest.raises(holds.OperationalStorageHoldBlocked):
        release(s)
    s.blob.patch.assert_not_called()


def test_cas_failure_is_not_retried_without_review(setup):
    s = setup
    s.blob.patch.side_effect = PreconditionFailed('metadata changed')
    with pytest.raises(PreconditionFailed):
        release(s)
    assert s.receipt['state'] == 'release_pending'
    assert s.blob.patch.call_count == 1


def test_patch_success_receipt_failure_reconciles_on_retry(setup):
    s = setup
    original_set = s.receipt_ref.set.side_effect

    def write(value):
        if value['state'] == 'released':
            raise RuntimeError('receipt unavailable')
        original_set(value)

    s.receipt_ref.set.side_effect = write
    with pytest.raises(RuntimeError, match='receipt unavailable'):
        release(s)
    assert s.receipt['state'] == 'release_pending'
    assert s.blob.metageneration == 3
    s.receipt_ref.set.side_effect = original_set
    release(s)
    assert s.receipt['state'] == 'released'
    assert s.blob.patch.call_count == 1


def test_ambiguous_success_does_not_accept_extra_metadata_changes(setup):
    s = setup
    release(s)
    s.blob.metageneration = 4
    with pytest.raises(holds.OperationalStorageHoldBlocked):
        release(s)
    assert s.blob.patch.call_count == 1


def test_unheld_without_approval_needs_no_release(setup):
    s = setup
    s.blob.temporary_hold = False
    s.marker.pop('operational_hold_release_approval')
    release(s)
    s.blob.patch.assert_not_called()
    s.receipt_ref.set.assert_not_called()


def test_plan_requires_exact_preservation_generation():
    blob = Blob()
    proof = {(holds.object_digest(blob.name), str(blob.generation))}
    assert operator.build_plan(UID, [blob], proof)['objects'] == approval(blob)['plan']['objects']
    with pytest.raises(ValueError, match='no operational preservation proof'):
        operator.build_plan(UID, [blob], {(holds.object_digest(blob.name), 'old-generation')})


def test_owner_with_sql_wildcards_does_not_broaden_receipt_selection(tmp_path):
    with sqlite3.connect(tmp_path / 'source-index.sqlite') as db:
        db.execute('CREATE TABLE sources(c INTEGER,s INTEGER,n TEXT)')
        db.executemany(
            'INSERT INTO sources VALUES(?,?,?)',
            [
                (1, 1, 'syncing/owner_with%wildcards/job/a'),
                (2, 1, 'syncing/ownerXwithXwildcards/job/b'),
            ],
        )
    with sqlite3.connect(tmp_path / 'final-audit.sqlite') as db:
        db.execute('CREATE TABLE proof(c INTEGER,s INTEGER,restored TEXT,state TEXT,hold INTEGER)')
        db.executemany('INSERT INTO proof VALUES(?,?,?,?,?)', [(1, 1, '123', 'held', 1), (2, 1, '456', 'held', 1)])
    proofs = operator.preservation_proofs(tmp_path, 'owner_with%wildcards')
    assert proofs == {(holds.object_digest('syncing/owner_with%wildcards/job/a'), '123')}


def test_registration_uses_transaction_authority_before_writing():
    client = StrictFirestore()
    client.rows[('account_deletions', UID)] = {'wipe_status': 'failed', 'wipe_job_id': 'opaque-job'}
    client.rows[('legal_hold_deletion_gates', UID)] = {
        'schema_version': 'legal_hold_deletion_gate.v1',
        'uid': UID,
        'kind': 'account_deletion',
        'token': 'operator-token',
        'state': 'running',
        'started_at': holds.datetime.now(holds.timezone.utc),
    }
    plan_approval = approval(Blob())
    operator.register_plan(client.transaction(), client, UID, 'opaque-job', 'operator-token', plan_approval)
    assert client.rows[('account_deletions', UID)]['operational_hold_release_approval'] == plan_approval


def test_registration_refuses_legal_hold_and_preserves_marker():
    client = StrictFirestore()
    client.rows[('account_deletions', UID)] = {'wipe_status': 'failed', 'wipe_job_id': 'opaque-job'}
    client.rows[('legal_holds', UID)] = {'schema_version': 'legal_hold.v1', 'issuer': 'admin', 'active': True}
    with pytest.raises(RuntimeError, match='legal hold'):
        operator.register_plan(client.transaction(), client, UID, 'opaque-job', 'token', approval(Blob()))
    assert 'operational_hold_release_approval' not in client.rows[('account_deletions', UID)]

"""Privacy erasure may release proven operational holds, never legal holds."""

from copy import deepcopy
import hashlib
import json
import os
import sqlite3
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from google.api_core.exceptions import InvalidArgument, PreconditionFailed
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from google.cloud.firestore_v1._helpers import encode_dict
from google.cloud.firestore_v1.types import Document

from database import account_deletion_operational_holds as holds
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
        'campaign_ledger_sha256': holds.plan_digest(holds.PRESERVATION_LEDGER_SHA256),
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


@pytest.fixture(params=['inline', 'sharded'])
def setup(monkeypatch, request):
    blob = Blob()
    approved = approval(blob)
    shards = {}
    if request.param == 'sharded':
        approved, shards = holds.shard_release_approval(UID, approved)
    marker = {'wipe_status': 'running', 'operational_hold_release_approval': approved}
    receipt = {}
    marker_ref = MagicMock()
    marker_ref.get.side_effect = lambda: SimpleNamespace(exists=True, to_dict=lambda: deepcopy(marker))
    receipt_ref = marker_ref.collection.return_value.document.return_value
    receipt_ref.get.side_effect = lambda: SimpleNamespace(exists=bool(receipt), to_dict=lambda: deepcopy(receipt))
    receipt_ref.set.side_effect = lambda value: (receipt.clear(), receipt.update(deepcopy(value)))
    shard_collection = MagicMock()
    shard_collection.document.side_effect = lambda prefix: SimpleNamespace(
        get=lambda: SimpleNamespace(exists=prefix in shards, to_dict=lambda: deepcopy(shards[prefix]))
    )
    marker_ref.collection.side_effect = lambda name: (
        shard_collection
        if name == holds.OPERATIONAL_HOLD_RELEASE_PLAN_SHARDS
        else SimpleNamespace(document=lambda _: receipt_ref)
    )
    gate = MagicMock()
    legal = MagicMock()
    monkeypatch.setattr(holds, 'assert_destructive_gate_still_ours', gate)
    monkeypatch.setattr(holds, 'assert_account_deletion_permitted', legal)
    monkeypatch.setattr(holds, 'account_deletion_document', lambda *args, **kwargs: marker_ref)
    client = object()
    return SimpleNamespace(
        blob=blob,
        marker=marker,
        receipt=receipt,
        receipt_ref=receipt_ref,
        client=client,
        gate=gate,
        legal=legal,
        shards=shards,
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
    assert s.receipt['plan_sha256'] == approval(s.blob)['plan_sha256']
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
    s.receipt_ref.set.assert_not_called()


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


@pytest.mark.parametrize('approval_state', ['absent', 'unmatched', 'approved'])
@pytest.mark.parametrize('metadata', [{'legal_hold': 'true'}, {'Legal-Hold': 'case'}, {'unknown_hold': 'true'}])
def test_unheld_legal_marker_never_bypasses_approval_checks(setup, approval_state, metadata):
    s = setup
    s.blob.temporary_hold = False
    s.blob.metadata = metadata
    if approval_state == 'absent':
        s.marker.pop('operational_hold_release_approval')
    elif approval_state == 'unmatched':
        s.blob.generation = 456
    with pytest.raises(holds.OperationalStorageHoldBlocked, match='protected'):
        release(s)
    s.blob.patch.assert_not_called()
    s.receipt_ref.set.assert_not_called()


def test_account_purge_protects_unheld_legal_marker_outside_sync_bucket():
    blob = SimpleNamespace(temporary_hold=False, metadata={'legal_hold': 'case'}, delete=MagicMock())
    bucket = SimpleNamespace(name='other-configured-owner-bucket', list_blobs=MagicMock(return_value=[blob]))
    with pytest.raises(holds.OperationalStorageHoldBlocked, match='protected'):
        holds.delete_owner_bucket_prefix(bucket, f'{UID}/', real_gcs=False, account_deletion_uid=UID)
    blob.delete.assert_not_called()


def test_plan_requires_exact_preservation_generation():
    blob = Blob()
    proof = {(holds.object_digest(blob.name), str(blob.generation))}
    assert operator.build_plan(UID, [blob], proof)['objects'] == approval(blob)['plan']['objects']
    with pytest.raises(ValueError, match='no operational preservation proof'):
        operator.build_plan(UID, [blob], {(holds.object_digest(blob.name), 'old-generation')})


def test_owner_with_sql_wildcards_does_not_broaden_receipt_selection(tmp_path, monkeypatch):
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
    monkeypatch.setattr(
        operator,
        'PRESERVATION_LEDGER_SHA256',
        {
            name: hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
            for name in ('source-index.sqlite', 'final-audit.sqlite')
        },
    )
    proofs = operator.preservation_proofs(tmp_path, 'owner_with%wildcards')
    assert proofs == {(holds.object_digest('syncing/owner_with%wildcards/job/a'), '123')}


def test_matching_generation_from_other_campaign_ledger_is_refused(tmp_path, monkeypatch):
    for name in ('source-index.sqlite', 'final-audit.sqlite'):
        with sqlite3.connect(tmp_path / name) as db:
            db.execute('CREATE TABLE campaign(name TEXT)')
            db.execute('INSERT INTO campaign VALUES(?)', ('trusted-campaign',))
    name = f'syncing/{UID}/job/a'
    with sqlite3.connect(tmp_path / 'source-index.sqlite') as db:
        db.execute('CREATE TABLE sources(c INTEGER,s INTEGER,n TEXT)')
        db.execute('INSERT INTO sources VALUES(?,?,?)', (1, 1, name))
    with sqlite3.connect(tmp_path / 'final-audit.sqlite') as db:
        db.execute('CREATE TABLE proof(c INTEGER,s INTEGER,restored TEXT,state TEXT,hold INTEGER)')
        db.execute('INSERT INTO proof VALUES(?,?,?,?,?)', (1, 1, '123', 'held', 1))
    trusted = {
        name: hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
        for name in ('source-index.sqlite', 'final-audit.sqlite')
    }
    monkeypatch.setattr(operator, 'PRESERVATION_LEDGER_SHA256', trusted)
    operator.verify_preservation_ledger(tmp_path)
    assert operator.preservation_proofs(tmp_path, UID) == {(holds.object_digest(name), '123')}
    with sqlite3.connect(tmp_path / 'final-audit.sqlite') as db:
        db.execute('UPDATE campaign SET name=?', ('different-campaign',))
    with pytest.raises(ValueError, match='identity or integrity mismatch'):
        operator.preservation_proofs(tmp_path, UID)


def test_unpinned_wal_overlay_is_refused(tmp_path):
    (tmp_path / 'source-index.sqlite-wal').write_bytes(b'unapproved-overlay')
    with pytest.raises(ValueError, match='uncheckpointed'):
        operator.verify_preservation_ledger(tmp_path)


def test_release_approval_requires_the_trusted_campaign_binding(setup):
    s = setup
    approved = s.marker['operational_hold_release_approval']
    approved['plan']['campaign_ledger_sha256'] = '0' * 64
    approved['plan_sha256'] = holds.plan_digest(approved['plan'])
    with pytest.raises(holds.OperationalStorageHoldBlocked, match='malformed or changed'):
        release(s)
    s.blob.patch.assert_not_called()


@pytest.mark.parametrize('requested', [None, 'https://actual-production.run.app/v1/users/account-deletion-wipes/run'])
def test_handler_is_bound_to_exact_production_service_uri(requested):
    session = MagicMock()
    session.get.return_value.json.return_value = {'uri': 'https://actual-production.run.app'}
    assert (
        operator.verified_handler_url(session, requested)
        == 'https://actual-production.run.app/v1/users/account-deletion-wipes/run'
    )
    session.get.assert_called_once_with(operator.SERVICE_METADATA_URL, params={'fields': 'uri'}, timeout=30)


def test_other_backend_sync_named_service_is_not_a_queue_target():
    session = MagicMock()
    session.get.return_value.json.return_value = {'uri': 'https://actual-production.run.app'}
    with pytest.raises(ValueError, match='differs from the live production'):
        operator.verified_handler_url(
            session, 'https://backend-sync-attacker.run.app/v1/users/account-deletion-wipes/run'
        )


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
    transaction = client.transaction()
    operator.register_plan(transaction, client, UID, 'opaque-job', 'operator-token', plan_approval)
    marker = client.rows[('account_deletions', UID)]['operational_hold_release_approval']
    assert marker['plan_sha256'] == plan_approval['plan_sha256']
    assert 'objects' not in marker['plan']
    assert len(transaction.creates) == 1
    prefix = plan_approval['plan']['objects'][0]['object_sha256'][:2]
    assert client.rows[('account_deletions', UID, holds.OPERATIONAL_HOLD_RELEASE_PLAN_SHARDS, prefix)] == {
        'objects': plan_approval['plan']['objects']
    }
    replay = client.transaction()
    operator.register_plan(replay, client, UID, 'opaque-job', 'operator-token', plan_approval)
    assert not replay.has_written
    with pytest.raises(ValueError, match='must not be overwritten'):
        operator.register_plan(
            client.transaction(),
            client,
            UID,
            'opaque-job',
            'operator-token',
            {**plan_approval, 'approval_ref': 'other'},
        )


def test_registration_refuses_legal_hold_and_preserves_marker():
    client = StrictFirestore()
    client.rows[('account_deletions', UID)] = {'wipe_status': 'failed', 'wipe_job_id': 'opaque-job'}
    client.rows[('legal_holds', UID)] = {'schema_version': 'legal_hold.v1', 'issuer': 'admin', 'active': True}
    with pytest.raises(RuntimeError, match='legal hold'):
        operator.register_plan(client.transaction(), client, UID, 'opaque-job', 'token', approval(Blob()))
    assert 'operational_hold_release_approval' not in client.rows[('account_deletions', UID)]
    assert not client.transactions[-1].has_written


@pytest.mark.parametrize('missing', [True, False])
@pytest.mark.parametrize('setup', ['sharded'], indirect=True)
def test_missing_or_changed_shard_blocks_release(setup, missing):
    s = setup
    prefix = holds.object_digest(s.blob.name)[:2]
    if missing:
        del s.shards[prefix]
    else:
        s.shards[prefix]['objects'][0]['metageneration'] = '999'
    with pytest.raises(holds.OperationalStorageHoldBlocked, match='shard is missing or changed'):
        release(s)
    s.blob.patch.assert_not_called()
    s.receipt_ref.set.assert_not_called()


@pytest.mark.skipif(
    not os.getenv('FIRESTORE_EMULATOR_HOST', '').startswith(('127.0.0.1:', 'localhost:')),
    reason='isolated loopback Firestore emulator required',
)
def test_registration_above_firestore_document_limit():
    client = firestore.Client(project='demo-deletion-shards', credentials=AnonymousCredentials())
    uid = 'synthetic-' + uuid4().hex
    marker = client.collection('account_deletions').document(uid)
    gate = client.collection('legal_hold_deletion_gates').document(uid)
    blob = Blob()
    blob.name = f'syncing/{uid}/synthetic.bin'
    plan_approval = approval(blob)
    plan = plan_approval['plan']
    plan['owner_sha256'] = holds.object_digest(uid)
    plan['objects'].extend(
        {
            'bucket': 'syncing-local',
            'object_sha256': holds.object_digest(f'synthetic-object/{index}'),
            'generation': str(1_792_000_000_000_000 + index),
            'metageneration': '2',
        }
        for index in range(13_463)
    )
    plan['objects'].sort(key=lambda item: item['object_sha256'])
    plan_approval['plan_sha256'] = holds.plan_digest(plan)
    inline_bytes = len(json.dumps(plan_approval, separators=(',', ':')).encode())
    assert inline_bytes > 1_048_576
    marker.set({'wipe_status': 'failed', 'wipe_job_id': 'opaque-job'})
    gate.set(
        {
            'schema_version': 'legal_hold_deletion_gate.v1',
            'uid': uid,
            'kind': 'account_deletion',
            'token': 'operator-token',
            'state': 'running',
            'started_at': holds.datetime.now(holds.timezone.utc),
        }
    )
    try:
        with pytest.raises(InvalidArgument, match='(?i)size|large'):
            marker.update({'operational_hold_release_approval': plan_approval})

        operator.register_plan(client.transaction(), client, uid, 'opaque-job', 'operator-token', plan_approval)
        marker_data = marker.get().to_dict()
        manifest = marker_data['operational_hold_release_approval']
        assert manifest['plan_sha256'] == plan_approval['plan_sha256']
        assert 'objects' not in manifest['plan']
        shards = {
            doc.id: doc.to_dict() for doc in marker.collection(holds.OPERATIONAL_HOLD_RELEASE_PLAN_SHARDS).stream()
        }
        assert len(shards) == 256
        assert set(shards) == set(manifest['shard_sha256'])
        assert [item for prefix in sorted(shards) for item in shards[prefix]['objects']] == plan['objects']
        for prefix, shard in shards.items():
            assert all(item['object_sha256'].startswith(prefix) for item in shard['objects'])
            assert holds.plan_digest(shard) == manifest['shard_sha256'][prefix]

        marker_bytes = Document.pb(Document(fields=encode_dict(marker_data))).ByteSize()
        max_shard_bytes = max(Document.pb(Document(fields=encode_dict(shard))).ByteSize() for shard in shards.values())
        print(
            f'objects={len(plan["objects"])} inline_json_bytes={inline_bytes} shards={len(shards)} '
            f'marker_proto_field_bytes={marker_bytes} max_shard_proto_field_bytes={max_shard_bytes}'
        )

        marker.update({'wipe_status': 'running'})
        gate.update({'token': f'account-deletion:{uid}'})
        holds.release_operational_hold_for_account_deletion(uid, blob, firestore_client=client)
        blob.patch.assert_called_once_with(if_generation_match=123, if_metageneration_match=2)
        (receipt,) = list(marker.collection('operational_hold_releases').stream())
        assert receipt.to_dict()['state'] == 'released'
        assert receipt.to_dict()['plan_sha256'] == plan_approval['plan_sha256']
    finally:
        client.recursive_delete(marker)
        gate.delete()
        client.close()

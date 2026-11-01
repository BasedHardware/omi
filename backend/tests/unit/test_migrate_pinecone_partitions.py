"""Operator guards: no inventory writes, no unreviewed rollout, owned resumes only."""

from dataclasses import asdict, replace
from datetime import datetime, timezone
from hashlib import sha256
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from database import pinecone_partition_state as state
from scripts import migrate_pinecone_partitions as cli
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore


@pytest.fixture
def args(tmp_path, monkeypatch):
    monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    return cli.parse_args(['--index', cli.DEV_INDEX, '--uid', 'owner', '--output-dir', str(tmp_path)])


@pytest.fixture
def key():
    return state.PartitionKey(cli.DEV_INDEX, 'ns1', 'owner')


def route(key, mode='copying', **changes):
    return replace(
        state.Route(mode, key.family, key.family, key.partition_namespace, 0, 0, 'owned-token', 0, False, 0),
        **changes,
    )


def test_inventory_does_not_register_missing_owner(args, key, monkeypatch):
    db = StrictFirestore()
    monkeypatch.setattr(state, 'get_route', Mock(side_effect=AssertionError('serving registration invoked')))
    result = cli.process_key(args, key, db, None)
    assert result['status'] == 'inventory'
    assert result['registered'] is False
    assert db.rows == {}


@pytest.fixture
def receipts(args, tmp_path):
    def artifact(name, content):
        path = tmp_path / name
        cli.atomic_json(path, content)
        return {'path': name, 'sha256': sha256(path.read_bytes()).hexdigest()}

    evidence = artifact('evidence.json', {'unit_test_fixture': True})
    inventory = artifact('inventory.json', {'writer_names': sorted(cli.CORE_WRITERS)})
    commit = 'a' * 40
    fleet = {
        'schema_version': 1,
        'index_name': 'memories-backend',
        'implementation_commit': commit,
        'reviewed_by': 'unit-test-reviewer',
        'reviewed_at': datetime.now(timezone.utc).isoformat(),
        'writer_inventory_complete': True,
        'writer_inventory_artifact': inventory,
        'writers': [
            {
                'name': name,
                'source_sha': commit,
                'image': 'unit-test@sha256:' + 'b' * 64,
                'implementation_present': True,
                'runtime_verified': True,
                'evidence': evidence,
            }
            for name in cli.CORE_WRITERS
        ],
    }
    proof = {
        'schema_version': 1,
        'status': 'GO',
        'implementation_commit': commit,
        'families_verified': sorted(state.FAMILIES),
        'real_user_path_verified': True,
        'cleanup_verified': True,
        'repeats': 3,
        'artifacts': [evidence],
        'allowed_production_test_uids': ['owner'],
        'stage': 'production_pilot',
        'index_name': 'memories-backend',
    }
    args.apply = True
    args.index = 'memories-backend'
    args.fleet_receipt = tmp_path / 'fleet.json'
    args.test_user_proof = tmp_path / 'proof.json'

    def persist():
        cli.atomic_json(args.fleet_receipt, fleet)
        cli.atomic_json(args.test_user_proof, proof)

    persist()
    return fleet, proof, persist


def test_production_apply_requires_receipts(args):
    args.apply, args.index = True, 'memories-backend'
    with pytest.raises(cli.OperatorGateError, match='requires reviewed'):
        cli.production_gate(args, ['owner'])


def test_production_receipt_passes_exact_reviewed_scope(args, receipts):
    result = cli.production_gate(args, ['owner'])
    assert result['implementation_commit'] == 'a' * 40
    assert result['fleet_receipt_sha256'] == sha256(args.fleet_receipt.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    'change',
    ['mutable_image', 'missing_writer', 'wrong_commit', 'missing_family', 'not_production_pilot', 'stale_review'],
)
def test_production_evidence_failures_refuse_apply(args, receipts, change):
    fleet, proof, persist = receipts
    if change == 'mutable_image':
        fleet['writers'][0]['image'] = 'mutable:main'
    elif change == 'missing_writer':
        fleet['writers'].pop()
    elif change == 'wrong_commit':
        proof['implementation_commit'] = 'c' * 40
    elif change == 'missing_family':
        proof['families_verified'].pop()
    elif change == 'not_production_pilot':
        proof['stage'] = 'development'
    elif change == 'stale_review':
        fleet['reviewed_at'] = '2020-01-01T00:00:00Z'
    persist()
    with pytest.raises(cli.OperatorGateError):
        cli.production_gate(args, ['owner'])


def test_tampered_evidence_refuses_apply(args, receipts):
    (args.output_dir / 'evidence.json').write_text('{"changed":true}')
    with pytest.raises(cli.OperatorGateError, match='hash'):
        cli.production_gate(args, ['owner'])


def test_pilot_cannot_include_unapproved_owner(args, receipts):
    args.pilot = True
    with pytest.raises(cli.OperatorGateError, match='explicitly identified'):
        cli.production_gate(args, ['different-owner'])


@pytest.mark.parametrize('pending,uncertain', [(1, 0), (0, 1), (1, 1)])
def test_unsettled_provider_operations_never_retry(args, key, monkeypatch, pending, uncertain):
    args.apply = True
    monkeypatch.setattr(
        state, 'get_route', lambda *a, **kw: route(key, pending_count=pending, uncertain_count=uncertain)
    )
    factory = Mock(side_effect=AssertionError('migration must not start'))
    monkeypatch.setattr(cli, 'BoundedMigration', factory)
    assert cli.process_key(args, key, None, None)['status'] == 'blocked_unsettled_operations'
    factory.assert_not_called()


@pytest.mark.parametrize('resume,journal_token', [(False, 'owned-token'), (True, None), (True, 'foreign-token')])
def test_copying_requires_explicit_resume_and_matching_journal(args, key, monkeypatch, resume, journal_token):
    args.apply, args.resume = True, resume
    monkeypatch.setattr(state, 'get_route', lambda *a, **kw: route(key))
    if journal_token:
        cli.atomic_json(
            args.output_dir / 'owners' / f'{key.document_id}.json',
            {'key': asdict(key), 'rollback': False, 'migration_token': journal_token},
        )
    assert cli.process_key(args, key, None, None)['status'] == 'blocked_foreign_or_unowned_migration'


class SweepDB:
    """Only models the operator's bounded single-field discovery calls."""

    def __init__(self, keys_by_mode):
        self.keys_by_mode = keys_by_mode
        self.filters = []

    def collection(self, name):
        assert name == state.COLLECTION
        return self

    def where(self, *, filter):
        assert filter.field_path == 'mode'
        self.mode = filter.value
        self.filters.append(self.mode)
        return self

    def limit(self, value):
        self.bound = value
        return self

    def stream(self):
        return iter(
            [
                SimpleNamespace(id=key.document_id, to_dict=lambda key=key: asdict(key))
                for key in self.keys_by_mode.get(self.mode, [])[: self.bound]
            ]
        )


def test_sweep_resume_discovers_owned_copy_and_completes_cas(args, key, monkeypatch):
    args.uid, args.sweep, args.resume, args.apply = None, True, True, True
    db = SweepDB({'copying': [key]})
    keys, inventory = cli.select_keys(args, db)
    assert keys == [key]
    assert db.filters == ['copying', 'legacy']
    assert inventory['scan_complete']
    cli.atomic_json(
        args.output_dir / 'owners' / f'{key.document_id}.json',
        {'key': asdict(key), 'rollback': False, 'migration_token': 'owned-token'},
    )
    monkeypatch.setattr(state, 'get_route', lambda *a, **kw: route(key))
    args.dimension = 3072
    receipt = {'revision': 11, 'records': 3}
    qualify = Mock(return_value=receipt)
    monkeypatch.setattr(cli, 'BoundedMigration', lambda *a, **kw: SimpleNamespace(qualify=qualify))
    cutover = Mock(return_value=route(key, mode='partitioned'))
    monkeypatch.setattr(state, 'cutover', cutover)
    result = cli.process_key(args, key, db, None)
    assert result['status'] == 'complete'
    qualify.assert_called_once_with('owned-token', dimension=3072, rollback=False)
    cutover.assert_called_once_with(key, 'owned-token', 11, receipt, firestore_client=db)
    journal = json.loads((args.output_dir / 'owners' / f'{key.document_id}.json').read_text())
    assert journal['status'] == 'complete'


def test_sweep_owner_limit_and_document_limit_are_reported(args, key):
    args.uid, args.sweep, args.resume = None, True, True
    args.max_owners = 1
    other = state.PartitionKey(cli.DEV_INDEX, 'ns1', 'other')
    db = SweepDB({'copying': [key], 'legacy': [other]})
    keys, inventory = cli.select_keys(args, db)
    assert keys == [key]
    assert inventory['deferred_owners_in_scan'] == 1
    assert not inventory['scan_complete']
    args.max_route_docs = 1
    db = SweepDB({'copying': [key], 'legacy': [other]})
    _, inventory = cli.select_keys(args, db)
    assert db.filters == ['copying']
    assert not inventory['scan_complete']


def test_budget_refuses_before_durable_write_admission(args, key, monkeypatch):
    transport = cli.BudgetTransport('unit-test.pinecone.io', 'unit-test-key', args)
    try:
        transport.requests = args.max_provider_requests
        parent_write = Mock(side_effect=AssertionError('durable admission invoked'))
        monkeypatch.setattr(cli.OwnerMigration, '_write', parent_write)
        migration = cli.BoundedMigration(key, transport, firestore_client=None)
        with pytest.raises(cli.BudgetExceeded):
            migration._write('owned-token', 'vectors/upsert', key.family, ['id'], vectors=[])
        parent_write.assert_not_called()
    finally:
        transport.client.close()

"""Real Firestore client/decorator with mocked RPCs; no credentials or network.

Exercises SDK rollback, write-buffer cleanup and commit retries rather than
claiming the strict fixture models server contention or lock scheduling.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import Aborted, DeadlineExceeded, InvalidArgument, ServiceUnavailable
from google.cloud.firestore_v1 import _helpers
from google.cloud.firestore_v1.transaction import Transaction
from google.cloud.firestore_v1.types import BatchGetDocumentsResponse, CommitResponse, Document

from config import conversation_smart_merge as config
from database import smart_merge as smart_merge_db
from database import smart_merge_audit as audit_db
from tests.unit.test_conversation_smart_merge import UID, World
from tests.unit.test_conversation_smart_merge_audit import GATE, MARKER, _audit_path, _gate, _merge
from tests.unit.fixtures.offline_firestore_sdk import OfflineFirestoreClient
from utils.conversations import smart_merge


@pytest.fixture
def sdk_world(monkeypatch):
    monkeypatch.delenv(config.SMART_MERGE_UID_ALLOWLIST_ENV, raising=False)
    monkeypatch.setenv(config.SMART_MERGE_AUDIT_ENV, 'on')
    world = World(monkeypatch)
    client = OfflineFirestoreClient(project='synthetic-audit-test')
    api = MagicMock()
    client._firestore_api_internal = api
    monkeypatch.setattr(smart_merge_db, 'get_firestore_client', lambda: client)
    committed, reads, failed_reads, rollbacks = [], [], set(), []
    failure = SimpleNamespace(read_path=None, read_error=None, abort_commit=False, gate_on_abort=False)

    def begin(**kwargs):
        return SimpleNamespace(transaction=f'txn-{api.begin_transaction.call_count}'.encode())

    def batch_get(*, request, **kwargs):
        name = request['documents'][0]
        path = tuple(name.split('/documents/', 1)[1].split('/'))
        transaction_id = request.get('transaction')
        reads.append((transaction_id, path))
        if path == failure.read_path:
            failed_reads.add(transaction_id)
            raise failure.read_error
        row = world.store.rows.get(path)
        if row is None:
            return iter([BatchGetDocumentsResponse(missing=name)])
        return iter([BatchGetDocumentsResponse(found=Document(name=name, fields=_helpers.encode_dict(row)))])

    def commit(*, request, **kwargs):
        assert request['transaction'] not in failed_reads, 'committed a poisoned transaction'
        writes = request['writes']
        if failure.abort_commit and any('/smart_merge_audit/' in write.update.name for write in writes):
            failure.abort_commit = False
            if failure.gate_on_abort:
                world.store.rows[GATE] = _gate()
            raise Aborted('synthetic conflict before commit')
        committed.append(request)
        for write in writes:
            path = tuple(write.update.name.split('/documents/', 1)[1].split('/'))
            data = _helpers.decode_dict(write.update.fields, client)
            if write.update_mask.field_paths:
                world.store.rows[path].update(data)
            else:
                world.store.rows[path] = data
        return CommitResponse(commit_time=datetime.now(timezone.utc))

    api.begin_transaction.side_effect = begin
    api.batch_get_documents.side_effect = batch_get
    api.commit.side_effect = commit
    api.rollback.side_effect = lambda *, request, **kw: rollbacks.append(request['transaction'])
    outcomes = []
    monkeypatch.setattr(smart_merge, 'record_conversation_smart_merge_audit', outcomes.append)
    return SimpleNamespace(
        world=world,
        api=api,
        failure=failure,
        reads=reads,
        committed=committed,
        failed_reads=failed_reads,
        rollbacks=rollbacks,
        outcomes=outcomes,
    )


@pytest.mark.parametrize('path', [GATE, MARKER])
@pytest.mark.parametrize('error', [Aborted, DeadlineExceeded, ServiceUnavailable, InvalidArgument])
@pytest.mark.parametrize('rollback_fails', [False, True])
def test_failed_fence_rpc_rolls_back_and_uses_fresh_transaction(sdk_world, path, error, rollback_fails):
    test = sdk_world
    test.failure.read_path = path
    test.failure.read_error = error('synthetic failed read')
    if rollback_fails:

        def rollback(*, request, **kwargs):
            test.rollbacks.append(request['transaction'])
            raise ServiceUnavailable('synthetic rollback failure masks callback exception')

        test.api.rollback.side_effect = rollback
    assert _merge(test.world) is True
    assert test.failed_reads <= set(test.rollbacks)
    assert all(request['transaction'] not in test.failed_reads for request in test.committed)
    assert test.world.raw('n')['deleted'] is True
    assert _audit_path('n') not in test.world.store.rows
    assert test.outcomes == ['skipped_error'] and len(test.world.jev_calls) == 1


def test_partial_audit_staging_failure_rolls_back_all_writes(sdk_world, monkeypatch):
    real = Transaction.set

    def failed_set(self, ref, data, *args, **kwargs):
        real(self, ref, data, *args, **kwargs)
        if '/smart_merge_audit/' in ref.path:
            raise ValueError('synthetic failure after buffering audit')

    monkeypatch.setattr(Transaction, 'set', failed_set)
    assert _merge(sdk_world.world) is True
    assert sdk_world.rollbacks
    assert _audit_path('n') not in sdk_world.world.store.rows
    assert not any('/smart_merge_audit/' in w.update.name for r in sdk_world.committed for w in r['writes'])
    assert sdk_world.outcomes == ['skipped_error']


@pytest.mark.parametrize('gate_on_abort', [False, True])
def test_sdk_commit_retry_rechecks_fence_and_commits_once(sdk_world, gate_on_abort):
    test = sdk_world
    test.failure.abort_commit = True
    test.failure.gate_on_abort = gate_on_abort
    assert _merge(test.world) is True
    absorbs = [r for r in test.committed if any('deleted' in w.update.fields for w in r['writes'])]
    assert len(absorbs) == 1
    assert (_audit_path('n') in test.world.store.rows) is not gate_on_abort
    assert len(test.world.raw('p')['smart_merge']['fragments']) == 2
    assert test.outcomes == ['skipped_gate' if gate_on_abort else 'written']
    assert len(test.world.jev_calls) == 1
    assert sum(path == GATE for _, path in test.reads) == 2
    assert sum(path == MARKER for _, path in test.reads) == 2
    # A finalization replay never backfills a skipped audit or writes a second one.
    result = smart_merge_db.absorb_conversation(
        UID,
        'p',
        'n',
        expected_revision=0,
        plan=lambda *a: pytest.fail('replanned a donor'),
    )
    assert result.outcome == 'already_absorbed'


@pytest.mark.parametrize(
    'field,value',
    [
        ('source', 'synthetic-secret'),
        ('source', 'omi\n'),
        ('model', 'synthetic/secret'),
        ('mode', 'synthetic'),
        ('question_version', 'synthetic'),
        ('donor_id', 'synthetic/secret'),
        ('survivor_id', 'p\n'),
    ],
)
def test_projection_rejects_untrusted_enums_and_document_paths(sdk_world, field, value):
    assert _merge(sdk_world.world) is True
    donor = sdk_world.world.raw('n')
    kwargs = dict(
        donor_id='n',
        survivor_id='p',
        survivor_state=sdk_world.world.raw('p')['smart_merge'],
        donor_update=donor,
        source='omi',
    )
    if field in ('source', 'donor_id', 'survivor_id'):
        kwargs[field] = value
    else:
        donor['smart_merge_decision'][field] = value
    with pytest.raises(ValueError):
        audit_db.audit_record(**kwargs)

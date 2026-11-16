"""Restore retries must preserve current-generation and terminal stale fences."""

from datetime import datetime, timezone

import pytest

from database import conversation_finalization_jobs as jobs
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore


@pytest.mark.parametrize(
    'change,expected',
    [
        ({}, 'lease_conflict'),
        ({'discarded': True}, 'fenced'),
        ({'finalization_job_id': 'newer-job'}, 'fenced'),
        ({'finalization_revision': 2}, 'fenced'),
        ({'status': 'processing'}, 'fenced'),
        (None, 'fenced'),
    ],
)
def test_expected_discard_only_retries_an_otherwise_current_restored_generation(change, expected):
    client = StrictFirestore()
    job_ref = client.collection('jobs').document('job')
    conversation_ref = client.document('users/synthetic/conversations/capture')
    job = {
        'uid': 'synthetic',
        'conversation_id': 'capture',
        'status': 'leased',
        'dispatch_generation': 1,
        'lease_epoch': 1,
        'finalization_revision': 1,
        'fanout_status': 'pending',
    }
    client.rows[job_ref.path] = dict(job)
    if change is not None:
        client.rows[conversation_ref.path] = {
            'status': 'completed',
            'discarded': False,
            'finalization_job_id': 'job',
            'finalization_revision': 1,
            **change,
        }
    transaction = client.transaction()
    claim = jobs._claim_finalization_fanout_txn(
        transaction,
        job_ref,
        1,
        1,
        datetime.now(timezone.utc),
        lambda *_: conversation_ref,
        expected_discarded=True,
    )
    assert claim['status'] == expected
    durable = client.rows[job_ref.path]
    if expected == 'lease_conflict':
        assert durable == job
        assert not transaction.has_written
    else:
        assert durable['status'] == 'completed'
        assert durable['fanout_status'] == 'fenced'
        assert durable['finalization_outcome'] == 'fenced'
        assert durable['terminal_outcome'] == 'stale'
        assert len(transaction.updates) == 1
        replay = client.transaction()
        assert (
            jobs._claim_finalization_fanout_txn(
                replay, job_ref, 1, 1, datetime.now(timezone.utc), lambda *_: conversation_ref, expected_discarded=True
            )['status']
            == 'lease_conflict'
        )
        assert not replay.has_written

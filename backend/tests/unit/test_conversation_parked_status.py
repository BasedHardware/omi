"""Only durably settled parked records can receive a status-only migration write."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from google.protobuf.timestamp_pb2 import Timestamp
from proto.datetime_helpers import DatetimeWithNanoseconds

from database import conversation_parked_status as parked, conversations
from utils.conversations import capture_group_notes_refresh, summary_delivery

CUTOFF = datetime(2026, 11, 21, tzinfo=timezone.utc)
DISCARD = {'verdict': 'discard', 'decided_by': 'rule', 'reason': 'filler_only', 'trigger': 'capture_end'}


@pytest.mark.parametrize(
    ('fields', 'expected'),
    [
        ({'deferred': True, 'source': 'desktop'}, 'deferred'),
        ({'deferred': True, 'source': 'omi'}, 'unclassified'),
        ({'deferred': True, 'source': 'desktop', 'record_lane_owner': 'batch_live_v1'}, 'other_owner'),
        ({'deferred': True, 'source': 'desktop', 'processing_state': 'local_pending'}, 'other_owner'),
        (
            {'deferred': True, 'source': 'desktop', 'processing_admitted_at': CUTOFF + timedelta(minutes=1)},
            'recent_or_unknown_admission',
        ),
        ({'discarded': True}, 'discard_unproven'),
        ({'discarded': True, 'finalization_job_id': 'job'}, 'discard_unproven'),
        ({'discarded': True, 'relevance_decision': {'verdict': 'discard'}}, 'discard_unproven'),
        ({'discarded': True, 'sync_relevance_user_kept': True}, 'other_owner'),
        ({'discarded': True, 'relevance_decision': DISCARD}, 'discarded'),
        ({'deleted': True}, 'deleted'),
        ({'deleted': True, 'v3_derived': True}, 'other_owner'),
        ({'status': 'completed', 'deleted': True}, 'changed'),
        ({}, 'unclassified'),
    ],
)
def test_candidate_uses_durable_disposition(fields, expected):
    assert parked.classify({'status': 'processing', **fields}, cutoff=CUTOFF) == expected


class _Ref:
    def __init__(self, path):
        self.path = path
        self.id = path.rsplit('/', 1)[-1]

    @property
    def parent(self):
        return _Ref(self.path.rsplit('/', 1)[0])

    def collection(self, name):
        return _Ref(f'{self.path}/{name}')

    document = collection


def _snapshot(ref, data, revision, *, scan=False):
    clock = None
    if revision is not None:
        wire = Timestamp(seconds=1_700_000_000, nanos=revision)
        clock = wire if scan else DatetimeWithNanoseconds.from_timestamp_pb(wire)
    return SimpleNamespace(reference=ref, update_time=clock, exists=data is not None, to_dict=lambda: data)


@pytest.mark.parametrize('apply', [True, False])
def test_status_only_after_ownership_validation(apply):
    ref_active, ref_changed, ref_settled = (_Ref(f'users/owner/conversations/{cid}') for cid in ('one', 'two', 'three'))
    parked_row = {'status': 'processing', 'source': 'desktop', 'deferred': True}
    active_row = {**parked_row, 'finalization_job_id': 'job', 'finalization_revision': 1}
    job_ref = _Ref(f'{parked.FINALIZATION_JOBS_COLLECTION}/job')
    current = {
        ref_active.path: _snapshot(ref_active, active_row, 1),
        ref_changed.path: _snapshot(ref_changed, active_row, 2),
        ref_settled.path: _snapshot(ref_settled, parked_row, 1),
        job_ref.path: _snapshot(
            job_ref, {'uid': 'owner', 'conversation_id': 'one', 'finalization_revision': 1, 'status': 'leased'}, 1
        ),
    }
    active, changed, settled = (
        _snapshot(ref_active, active_row, 1, scan=True),
        _snapshot(ref_changed, active_row, 1, scan=True),
        _snapshot(ref_settled, parked_row, 1, scan=True),
    )
    transaction = Mock()
    client = SimpleNamespace(
        collection=_Ref,
        get_all=lambda refs, **kwargs: [current.get(item.path, _snapshot(item, None, None)) for item in reversed(refs)],
    )

    assert parked.settle_in_transaction(
        transaction, client, [active, changed, settled], cutoff=CUTOFF, apply=apply
    ) == [
        'finalization_fenced',
        'changed',
        'deferred',
    ]
    if apply:
        transaction.update.assert_called_once_with(ref_settled, {'status': 'completed'})
    else:
        transaction.update.assert_not_called()


@pytest.mark.parametrize(
    ('fields', 'metadata_path', 'expected'),
    [
        ({'deferred': True}, f'{parked.ACCOUNT_DELETION_COLLECTION}/owner', 'custody_fenced'),
        ({'deleted': True}, None, 'deletion_fenced'),
        ({'deferred': True}, f'users/owner/{parked.TOMBSTONES}/c1', 'deletion_fenced'),
    ],
)
def test_status_write_refuses_conflicting_custody(fields, metadata_path, expected):
    ref = _Ref('users/owner/conversations/c1')
    row = {'status': 'processing', 'source': 'desktop', **fields}
    snapshots = {ref.path: _snapshot(ref, row, 1)}
    if metadata_path:
        metadata_ref = _Ref(metadata_path)
        snapshots[metadata_path] = _snapshot(metadata_ref, {}, 1)
    client = SimpleNamespace(
        collection=_Ref,
        get_all=lambda refs, **kwargs: [snapshots.get(item.path, _snapshot(item, None, None)) for item in refs],
    )
    transaction = Mock()
    assert parked.settle_in_transaction(
        transaction, client, [_snapshot(ref, row, 1, scan=True)], cutoff=CUTOFF, apply=True
    ) == [expected]
    transaction.update.assert_not_called()


@pytest.mark.parametrize('disposition', ['deleted', 'discarded'])
@pytest.mark.parametrize('deferred', [True, None, 'false', 0])
def test_discard_deletion_scope_refuses_deferred_markers_before_custody_reads(disposition, deferred):
    row = {
        'status': 'processing',
        disposition: True,
        'deferred': deferred,
        'relevance_decision': DISCARD,
    }
    assert parked.classify(row, cutoff=CUTOFF, discard_deletion_only=True) == 'deferred_excluded'


@pytest.mark.parametrize(('revision', 'expected'), [(1, 'deferred_excluded'), (2, 'changed')])
def test_discard_deletion_transaction_refuses_deferred_added_after_scan(revision, expected):
    ref = _Ref('users/owner/conversations/c1')
    row = {'status': 'processing', 'discarded': True, 'relevance_decision': DISCARD}
    scanned = _snapshot(ref, row, 1, scan=True)
    latest = _snapshot(ref, {**row, 'deferred': True}, revision)
    client = SimpleNamespace(collection=_Ref, get_all=Mock(return_value=[latest]))
    transaction = Mock()

    assert parked.settle_in_transaction(
        transaction, client, [scanned], cutoff=CUTOFF, apply=True, discard_deletion_only=True
    ) == [expected]
    assert client.get_all.call_count == 1
    assert not transaction.mock_calls


@pytest.mark.parametrize('disposition', ['deleted', 'discarded'])
def test_discard_deletion_scope_preserves_visibility_and_notes_refusals(disposition):
    ref = _Ref('users/owner/conversations/c1')
    row = {
        'status': 'processing',
        disposition: True,
        'deferred': False,
        'relevance_decision': DISCARD,
    }
    current = {ref.path: _snapshot(ref, row, 1)}
    if disposition == 'deleted':
        tombstone = _Ref(f'users/owner/{parked.TOMBSTONES}/c1')
        current[tombstone.path] = _snapshot(tombstone, {}, 1)
    client = SimpleNamespace(
        collection=_Ref,
        get_all=lambda refs, **kwargs: [current.get(item.path, _snapshot(item, None, None)) for item in refs],
    )
    transaction = Mock()

    assert parked.settle_in_transaction(
        transaction, client, [_snapshot(ref, row, 1, scan=True)], cutoff=CUTOFF, apply=True, discard_deletion_only=True
    ) == [disposition]
    transaction.update.assert_called_once_with(ref, {'status': 'completed'})
    assert len(transaction.mock_calls) == 1
    settled = {**row, **transaction.update.call_args.args[1]}
    assert not conversations.is_visible_conversation(settled)
    assert conversations.is_visible_conversation(settled, include_discarded=True) == (disposition == 'discarded')
    assert summary_delivery.refusal(settled) == 'lifecycle'
    assert not capture_group_notes_refresh._eligible_primary_row(settled)

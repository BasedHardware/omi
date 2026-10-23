"""Gate 3 observes committed creates without changing assignment reads/writes."""

from copy import deepcopy
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from config import rollout_cohorts, sync_lineage
from database import conversations as db
from database import sync_live_overlap
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreDocument
from tests.unit.test_sync_cross_job_assignment import chunk
from utils.sync.assignment_telemetry import created_sync_row_observation


@pytest.fixture(autouse=True)
def flags(monkeypatch):
    monkeypatch.setenv('SYNC_LINEAGE_RESOLVE_ENABLED', 'true')
    monkeypatch.setenv('SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST', 'u')
    monkeypatch.setenv('SYNC_LIVE_OVERLAP_ENABLED', 'true')
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'off')
    monkeypatch.setattr(db, 'index_sync_assignment', lambda *a: None)


@pytest.fixture
def encoded_plans(monkeypatch):
    plans = []
    encode = db.encode_sync_assignment_plan

    def capture(uid, client, transaction, payload, current):
        plans.append(deepcopy(payload))
        return encode(uid, client, transaction, payload, current)

    monkeypatch.setattr(db, 'encode_sync_assignment_plan', capture)
    return plans


def persist(monkeypatch, *, live=None, complete=True, eligible=True, client=None):
    client = client or StrictFirestore()
    if live is not None:
        client.rows[('users', 'u', 'conversations', 'live')] = deepcopy(live)

    def discover(user, incoming, *, diagnostics=None):
        if diagnostics is not None:
            diagnostics['lookup_complete'] = complete
        return ('live',) if live is not None else ()

    monkeypatch.setattr(db, 'find_sync_live_overlap_candidates', discover)
    incoming = dict(chunk('wal', 1000), data_protection_level='standard')
    # Mirror the trusted producer's admission snapshot, not a fresh policy
    # evaluation inside assignment (the real cohort resolver can perform IO).
    if eligible and sync_lineage.sync_lineage_resolve_active_for('u'):
        incoming['_sync_lineage_eligible'] = True
    return client, db.assign_sync_conversation('u', incoming, firestore_client=client)


def observations(caplog):
    return [r.message for r in caplog.records if 'stage=assignment' in r.message]


def test_clear_emits_once_after_commit_and_retry_append_is_silent(monkeypatch, caplog):
    client = StrictFirestore()
    transaction = client.transaction()
    commit = transaction._commit

    def checked_commit():
        assert not observations(caplog)
        commit()

    monkeypatch.setattr(transaction, '_commit', checked_commit)
    monkeypatch.setattr(client, 'transaction', lambda: transaction)
    with caplog.at_level(logging.INFO):
        client, (row, created, _) = persist(monkeypatch, client=client)
    assert created
    assert observations(caplog) == [
        'event=sync_lineage_resolve outcome=created_clear stage=assignment '
        'checked_live_candidates_bucket=0 lookup_complete=true'
    ]
    assert '_sync_lineage_created' not in row
    assert not any(k.startswith('_sync_lineage_') for k in client.rows[('users', 'u', 'conversations', 'wal')])
    # Use a fresh transaction: StrictFirestore deliberately has no retry model.
    monkeypatch.setattr(client, 'transaction', lambda: StrictFirestore.transaction(client))
    with caplog.at_level(logging.INFO):
        _, (_, created, _) = persist(monkeypatch, client=client)
    assert not created and len(observations(caplog)) == 1


def test_overlap_with_empty_live_stub_is_observed_without_adopting_it(monkeypatch, caplog):
    live = dict(chunk('live', 1002), has_content=False, capture_evidence={'origin': 'live'}, transcript_segments=[])
    with caplog.at_level(logging.INFO):
        _, (row, created, _) = persist(monkeypatch, live=live)
    assert created and row['id'] == 'wal'
    assert observations(caplog) == [
        'event=sync_lineage_resolve outcome=created_overlap stage=assignment '
        'checked_live_candidates_bucket=1 lookup_complete=true'
    ]
    assert 'chapter' not in observations(caplog)[0]


def test_incomplete_lookup_is_unknown_not_clear(monkeypatch, caplog):
    with caplog.at_level(logging.INFO):
        _, (_, created, _) = persist(monkeypatch, complete=False)
    assert created
    assert observations(caplog) == [
        'event=sync_lineage_resolve outcome=created_unknown stage=assignment '
        'checked_live_candidates_bucket=0 lookup_complete=false'
    ]


def test_live_recording_stamp_survives_sync_revision_and_replaced_capture_evidence():
    incoming = chunk('wal', 1000)
    row = dict(
        chunk('live', 1002),
        sync_content_revision=7,
        capture_evidence={'origin': 'sync_vad'},
        external_data={'recording_origin_id': 'synthetic-origin'},
    )
    assert created_sync_row_observation([row], incoming, incoming, lookup_complete=True) == {
        'outcome': 'created_overlap',
        'checked_live_candidates_bucket': '1',
        'lookup_complete': True,
    }


@pytest.mark.parametrize('admitted,s1,enabled', [(False, True, True), (True, False, True), (True, True, False)])
def test_non_admitted_or_unvalidated_intake_is_silent_and_has_identical_reads_writes(
    monkeypatch, caplog, admitted, s1, enabled, encoded_plans
):
    if not admitted:
        monkeypatch.setenv('SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST', 'another-owner')
    if not enabled:
        monkeypatch.setenv('SYNC_LINEAGE_RESOLVE_ENABLED', 'false')
    reads = []
    get = StrictFirestoreDocument.get

    def counted(ref, *a, **kw):
        reads.append((ref.path, kw.get('transaction') is not None))
        return get(ref, *a, **kw)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', counted)
    with caplog.at_level(logging.INFO):
        baseline, result = persist(monkeypatch, eligible=False)
        baseline_reads = list(reads)
        reads.clear()
        current, observed = persist(monkeypatch, eligible=s1)
    # Compare plaintext codec inputs; encrypted sidecar nonces intentionally vary.
    assert result == observed and baseline.rows.keys() == current.rows.keys()
    assert encoded_plans[0] == encoded_plans[1]
    assert reads == baseline_reads
    assert not observations(caplog)


def test_validated_admission_never_refreshes_cohort_storage_inside_assignment(monkeypatch, caplog):
    incoming = dict(chunk('wal', 1000), data_protection_level='standard', _sync_lineage_eligible=True)

    def forbidden(*args, **kwargs):
        raise AssertionError('telemetry must not refresh cohort membership')

    monkeypatch.setattr(rollout_cohorts, '_membership_resolver', forbidden)
    monkeypatch.setenv('SYNC_LINEAGE_LIVE_DEDUPE_ENABLED', 'false')
    monkeypatch.setattr(db, 'find_sync_live_overlap_candidates', lambda *args, **kwargs: ())
    with caplog.at_level(logging.INFO):
        _, created, _ = db.assign_sync_conversation('u', incoming, firestore_client=StrictFirestore())
    assert created
    assert len(observations(caplog)) == 1


@pytest.mark.parametrize('stub', [False, True])
def test_eligible_observation_adds_no_reads_or_persisted_fields(monkeypatch, stub, encoded_plans):
    reads = []
    get = StrictFirestoreDocument.get

    def counted(ref, *a, **kw):
        reads.append(ref.path)
        return get(ref, *a, **kw)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', counted)
    live = dict(chunk('live', 1002), has_content=False, transcript_segments=[]) if stub else None
    baseline, result = persist(monkeypatch, eligible=False, live=live)
    baseline_reads = list(reads)
    reads.clear()
    current, observed = persist(monkeypatch, live=live)
    # Compare plaintext codec inputs; encrypted sidecar nonces intentionally vary.
    assert result == observed and baseline.rows.keys() == current.rows.keys()
    assert encoded_plans[0] == encoded_plans[1]
    assert reads == baseline_reads


@pytest.mark.parametrize('size,complete', [(0, True), (127, True), (128, False)])
def test_existing_discovery_query_preserves_limit_and_reports_completeness(size, complete):
    user = MagicMock()
    query = user.collection.return_value
    for name in ('where', 'order_by', 'select', 'limit'):
        getattr(query, name).return_value = query
    query.stream.return_value = [SimpleNamespace(id=str(i), to_dict=lambda: chunk('live', 1002)) for i in range(size)]
    status = {}
    sync_live_overlap.find_sync_live_overlap_candidates(user, chunk('wal', 1000), diagnostics=status)
    assert status == {'lookup_complete': complete}
    query.stream.assert_called_once_with(timeout=10)
    query.limit.assert_called_once_with(128)
    assert 'transcript_segments' not in query.select.call_args.args[0]


@pytest.mark.parametrize(
    'field,value',
    [('source', 'phone'), ('client_device_id', 'other'), ('is_locked', True), ('sync_clock_run', 'other')],
)
def test_other_partitions_do_not_count_as_live_candidates(field, value):
    incoming = chunk('wal', 1000)
    row = dict(chunk('live', 1001), **{field: value})
    assert created_sync_row_observation([row], incoming, incoming, lookup_complete=True) == {
        'outcome': 'created_clear',
        'checked_live_candidates_bucket': '0',
        'lookup_complete': True,
    }


@pytest.mark.parametrize('abort', [False, True])
def test_commit_retries_emit_once_and_failed_commits_emit_nothing(monkeypatch, caplog, abort):
    from google.api_core.exceptions import Aborted, ServiceUnavailable
    from tests.unit.test_conversation_persistence_transaction_expiry import _FakeFirestoreClient
    from utils.sync import assignment

    client = _FakeFirestoreClient(None, [Aborted('retry commit') if abort else ServiceUnavailable('failed commit')])

    def body(transaction, user_ref, incoming, **kwargs):
        payload = {k: v for k, v in incoming.items() if not k.startswith('_sync_lineage_')}
        transaction.set(client.doc_ref, payload)
        result = dict(
            payload, _sync_lineage_created=created_sync_row_observation([], payload, payload, lookup_complete=True)
        )
        return result, True, payload['transcript_segments']

    monkeypatch.setattr(assignment, 'assign_in_transaction', body)
    monkeypatch.setenv('SYNC_LIVE_OVERLAP_ENABLED', 'false')
    incoming = dict(chunk('wal', 1000), data_protection_level='standard', _sync_lineage_eligible=True)
    with caplog.at_level(logging.INFO):
        if abort:
            db.assign_sync_conversation('u', incoming, firestore_client=client)
            assert len(client.commits) == len(observations(caplog)) == 1
        else:
            with pytest.raises(ServiceUnavailable):
                db.assign_sync_conversation('u', incoming, firestore_client=client)
            assert not observations(caplog) and not client.commits

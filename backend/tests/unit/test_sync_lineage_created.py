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
from utils.sync.intake_completion import log_sync_lineage_created


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


def persist(
    monkeypatch,
    *,
    live=None,
    complete=True,
    reason=None,
    eligible=True,
    client=None,
    incoming=None,
    discovery_calls=None,
    **assignment_kwargs,
):
    client = client or StrictFirestore()
    if live is not None:
        client.rows[('users', 'u', 'conversations', 'live')] = deepcopy(live)

    def discover(user, incoming, *, diagnostics=None):
        if discovery_calls is not None:
            discovery_calls.append(True)
        if diagnostics is not None:
            diagnostics['lookup_complete'] = complete
            if reason is not None:
                diagnostics['incomplete_reason'] = reason
        return ('live',) if live is not None else ()

    monkeypatch.setattr(db, 'find_sync_live_overlap_candidates', discover)
    incoming = dict(incoming or chunk('wal', 1000), data_protection_level='standard')
    # Mirror the trusted producer's admission snapshot, not a fresh policy
    # evaluation inside assignment (the real cohort resolver can perform IO).
    if eligible and sync_lineage.sync_lineage_resolve_active_for('u'):
        incoming['_sync_lineage_eligible'] = True
    return client, db.assign_sync_conversation('u', incoming, firestore_client=client, **assignment_kwargs)


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
        'checked_live_candidates_bucket=0 lookup_complete=false incomplete_reason=not_recorded'
    ]


@pytest.mark.parametrize('overlap', [False, True])
def test_stamp_gap_reroute_discovers_and_rechecks_live_candidates(monkeypatch, caplog, overlap):
    client = StrictFirestore()
    stamp = dict(chunk('stamp', 0), data_protection_level='standard')
    client.rows[('users', 'u', 'conversations', 'stamp')] = deepcopy(stamp)
    # An empty overlapping stub cannot be adopted, but must prove overlap.
    live = dict(chunk('live', 1002 if overlap else 2000), has_content=False, transcript_segments=[])
    incoming = dict(chunk('wal', 1000), _sync_lineage_binding='stamp_fallback')
    calls, fences = [], []
    with caplog.at_level(logging.INFO):
        _, (row, created, _) = persist(
            monkeypatch,
            client=client,
            live=live,
            incoming=incoming,
            target_id='stamp',
            discovery_calls=calls,
            before_assign=lambda transaction: fences.append(transaction),
        )
    assert created and row['_sync_lineage_stamp_gap_refused'] is True
    assert client.rows[('users', 'u', 'conversations', 'stamp')] == stamp
    assert len(calls) == 1 and len(fences) == 2 and fences[0] is not fences[1]
    outcome = 'created_overlap' if overlap else 'created_clear'
    assert observations(caplog) == [
        f'event=sync_lineage_resolve outcome={outcome} stage=assignment '
        'checked_live_candidates_bucket=2_5 lookup_complete=true'
    ]
    assert all('_sync_lineage_created' not in value for value in client.rows.values())


@pytest.mark.parametrize('overlap', [False, True])
@pytest.mark.parametrize('duration', [9.5, 330])
@pytest.mark.parametrize('dedupe_enabled', [False, True])
def test_stamp_gap_reroute_never_adopts_live_content(monkeypatch, caplog, overlap, duration, dedupe_enabled):
    from datetime import timedelta

    from utils.sync.live_overlap import choose_live_overlap

    monkeypatch.setenv('SYNC_LINEAGE_LIVE_DEDUPE_ENABLED', str(dedupe_enabled).lower())
    client = StrictFirestore()
    stamp = dict(chunk('stamp', 0), data_protection_level='standard')
    client.rows[('users', 'u', 'conversations', 'stamp')] = deepcopy(stamp)
    live = dict(chunk('live', 1002 if overlap else 2000), has_content=True, capture_evidence={'origin': 'live'})
    incoming = dict(chunk('wal', 1000), _sync_lineage_binding='stamp_fallback')
    incoming['finished_at'] = incoming['started_at'] + timedelta(seconds=duration)
    incoming['transcript_segments'][0]['end'] = duration
    # This is adoptable content on ordinary untargeted intake. The long case
    # would stretch it by more than 300 s if reroute selection regressed.
    assert choose_live_overlap([live], incoming) == ('live' if overlap else None)
    if overlap and duration > 300:
        assert (incoming['finished_at'] - live['finished_at']).total_seconds() > 300
    calls = []
    with caplog.at_level(logging.INFO):
        _, (row, created, _) = persist(
            monkeypatch,
            client=client,
            live=live,
            target_id='stamp',
            incoming=incoming,
            discovery_calls=calls,
        )
    assert created and row['id'] == 'wal'
    assert row['_sync_lineage_stamp_gap_refused'] is True
    assert client.rows[('users', 'u', 'conversations', 'stamp')] == stamp
    assert client.rows[('users', 'u', 'conversations', 'live')] == live
    assert ('users', 'u', 'conversations', 'wal') in client.rows
    assert calls == [True]
    outcome = 'created_overlap' if overlap else 'created_clear'
    assert observations(caplog) == [
        f'event=sync_lineage_resolve outcome={outcome} stage=assignment '
        'checked_live_candidates_bucket=2_5 lookup_complete=true'
    ]


@pytest.mark.parametrize('reason', ['lookup_failed', 'page_cap'])
def test_stamp_gap_incomplete_discovery_stays_unknown(monkeypatch, caplog, reason):
    with caplog.at_level(logging.INFO):
        _, (_, created, _) = persist(
            monkeypatch,
            live=chunk('live', 0),
            target_id='live',
            complete=False,
            reason=reason,
            incoming=dict(chunk('wal', 1000), _sync_lineage_binding='stamp_fallback'),
        )
    assert created
    assert len(observations(caplog)) == 1
    assert observations(caplog)[0].endswith(f'lookup_complete=false incomplete_reason={reason}')


@pytest.mark.parametrize('stamp_binding', [False, True])
def test_retained_target_does_not_discover(monkeypatch, stamp_binding):
    calls = []
    incoming = dict(chunk('wal', 1010), _sync_lineage_binding='stamp_fallback' if stamp_binding else 'bound')
    _, (row, created, _) = persist(
        monkeypatch,
        live=chunk('live', 1000),
        target_id='live',
        incoming=incoming,
        discovery_calls=calls,
    )
    assert not created and row['id'] == 'live' and not calls


def test_reroute_rechecks_fence_before_any_write(monkeypatch, caplog):
    from utils.sync.assignment_errors import SyncAssignmentSuperseded

    calls, fences = [], []
    client = StrictFirestore()
    live = chunk('live', 0)

    def fence(transaction):
        fences.append(transaction)
        if len(fences) == 2:
            raise SyncAssignmentSuperseded('synthetic fence changed during discovery')

    with caplog.at_level(logging.INFO), pytest.raises(SyncAssignmentSuperseded):
        persist(
            monkeypatch,
            client=client,
            live=live,
            target_id='live',
            discovery_calls=calls,
            incoming=dict(chunk('wal', 1000), _sync_lineage_binding='stamp_fallback'),
            before_assign=fence,
        )
    assert len(calls) == 1 and len(fences) == 2 and not observations(caplog)
    assert client.rows == {('users', 'u', 'conversations', 'live'): live}


def test_create_without_discovery_is_labelled_skipped(monkeypatch, caplog):
    calls = []
    with caplog.at_level(logging.INFO):
        _, (_, created, _) = persist(monkeypatch, target_id='missing', discovery_calls=calls)
    assert created and not calls
    assert observations(caplog)[0].endswith('lookup_complete=false incomplete_reason=discovery_skipped')


@pytest.mark.parametrize('reason', ['lookup_failed', 'page_cap'])
def test_discovery_reason_reaches_committed_unknown_log(monkeypatch, caplog, reason):
    with caplog.at_level(logging.INFO):
        _, (_, created, _) = persist(monkeypatch, complete=False, reason=reason)
    assert created
    assert observations(caplog) == [
        'event=sync_lineage_resolve outcome=created_unknown stage=assignment '
        f'checked_live_candidates_bucket=0 lookup_complete=false incomplete_reason={reason}'
    ]


def test_missing_device_is_attributed_even_when_discovery_is_skipped(monkeypatch, caplog):
    incoming = chunk('wal', 1000)
    incoming.pop('client_device_id', None)
    with caplog.at_level(logging.INFO):
        _, (_, created, _) = persist(monkeypatch, incoming=incoming)
    assert created
    assert observations(caplog)[0].endswith('lookup_complete=false incomplete_reason=no_device')


def test_discovered_candidate_missing_from_transaction_cache_is_attributed(monkeypatch, caplog):
    # Coverage discovery runs, while disabled temporal adoption leaves its
    # candidate unread. Observation must describe that gap without filling it.
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'shadow')
    monkeypatch.setenv('SYNC_LIVE_OVERLAP_ENABLED', 'false')
    live = dict(chunk('live', 1002), has_content=False, transcript_segments=[])
    with caplog.at_level(logging.INFO):
        _, (_, created, _) = persist(monkeypatch, live=live)
    assert created
    assert observations(caplog)[0].endswith('lookup_complete=false incomplete_reason=candidate_unread')


def test_committed_extent_outside_incoming_is_attributed():
    incoming = chunk('wal', 1000)
    result = dict(incoming, finished_at=incoming['finished_at'].timestamp() + 1)
    observation = created_sync_row_observation([], result, incoming, lookup_complete=True)
    assert observation['outcome'] == 'created_unknown'
    assert observation['incomplete_reason'] == 'extent_outside_incoming'


@pytest.mark.parametrize('candidate', [False, True])
@pytest.mark.parametrize('end', [float('nan'), float('inf'), 1000, 999])
def test_nonfinite_or_empty_new_or_checked_candidate_extent_is_attributed(candidate, end):
    incoming = chunk('wal', 1000)
    invalid = dict(incoming, finished_at=end)
    observation = created_sync_row_observation(
        [invalid] if candidate else [], incoming if candidate else invalid, incoming, lookup_complete=True
    )
    assert observation['outcome'] == 'created_unknown'
    assert observation['incomplete_reason'] == 'invalid_extent'


def test_observation_error_is_attributed_and_never_raises():
    incoming = chunk('wal', 1000)
    observation = created_sync_row_observation([], {}, incoming, lookup_complete=True)
    assert observation['outcome'] == 'created_unknown'
    assert observation['incomplete_reason'] == 'observation_error'


@pytest.mark.parametrize(
    'discovery,device,outside,unread,expected',
    [
        ('lookup_failed', False, True, True, 'lookup_failed'),
        ('page_cap', False, True, True, 'page_cap'),
        (None, False, True, True, 'no_device'),
        (None, True, True, True, 'extent_outside_incoming'),
        (None, True, False, True, 'candidate_unread'),
        (None, True, False, False, 'invalid_extent'),
        ('discovery_skipped', True, False, False, 'invalid_extent'),
    ],
)
def test_unknown_reasons_use_first_matching_priority(discovery, device, outside, unread, expected):
    incoming = chunk('wal', 1000)
    if not device:
        incoming.pop('client_device_id', None)
    result = dict(incoming, finished_at=incoming['finished_at'].timestamp() + 1) if outside else incoming
    invalid_candidate = dict(result, finished_at=float('nan'))
    observation = created_sync_row_observation(
        [invalid_candidate],
        result,
        incoming,
        lookup_complete=False,
        lookup_incomplete_reason=discovery,
        candidates_read=not unread,
    )
    assert observation['incomplete_reason'] == expected


@pytest.mark.parametrize('reason', [None, 'private-unbounded-value'])
def test_missing_or_unrecognized_reason_logs_only_closed_fallback(caplog, reason):
    incoming = chunk('wal', 1000)
    observation = created_sync_row_observation(
        [], incoming, incoming, lookup_complete=False, lookup_incomplete_reason=reason
    )
    assert observation['incomplete_reason'] == 'not_recorded'
    # Also exercise old intake payloads, which may not contain the new field.
    observation['incomplete_reason'] = reason
    if reason is None:
        observation.pop('incomplete_reason')
    with caplog.at_level(logging.INFO):
        log_sync_lineage_created(observation)
    assert observations(caplog)[0].endswith('incomplete_reason=not_recorded')
    assert 'private-unbounded-value' not in observations(caplog)[0]


def test_overlap_on_incomplete_lookup_omits_reason(caplog):
    incoming = chunk('wal', 1000)
    observation = created_sync_row_observation(
        [chunk('live', 1002)], incoming, incoming, lookup_complete=False, lookup_incomplete_reason='page_cap'
    )
    assert observation['outcome'] == 'created_overlap'
    assert 'incomplete_reason' not in observation
    with caplog.at_level(logging.INFO):
        log_sync_lineage_created(observation)
    assert 'incomplete_reason' not in observations(caplog)[0]


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


def test_non_admitted_incomplete_intake_has_no_reason_and_identical_reads(monkeypatch, caplog, encoded_plans):
    from utils.sync import assignment

    reads, calls = [], []
    get, assign = StrictFirestoreDocument.get, assignment.assign_in_transaction

    def counted(ref, *args, **kwargs):
        reads.append(ref.path)
        return get(ref, *args, **kwargs)

    def capture(*args, **kwargs):
        calls.append(kwargs)
        return assign(*args, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', counted)
    monkeypatch.setattr(assignment, 'assign_in_transaction', capture)
    with caplog.at_level(logging.INFO):
        baseline, result = persist(monkeypatch, complete=False, reason='page_cap')
        baseline_reads = list(reads)
        reads.clear()
        current, observed = persist(monkeypatch, complete=False, reason='page_cap', eligible=False)
    assert result == observed and baseline.rows.keys() == current.rows.keys()
    assert reads == baseline_reads and encoded_plans[0] == encoded_plans[1]
    assert len(observations(caplog)) == 1
    assert observations(caplog)[0].endswith('incomplete_reason=page_cap')
    assert 'live_lookup_incomplete_reason' not in calls[1] and 'live_lookup_complete' not in calls[1]
    assert 'incomplete_reason' not in observed[0]
    assert all('incomplete_reason' not in row for row in current.rows.values())


@pytest.mark.parametrize('size', [0, 127, 128])
@pytest.mark.parametrize('device', [False, True])
def test_existing_discovery_query_preserves_limit_and_reports_completeness(size, device):
    user = MagicMock()
    query = user.collection.return_value
    for name in ('where', 'order_by', 'select', 'limit'):
        getattr(query, name).return_value = query
    query.stream.return_value = [SimpleNamespace(id=str(i), to_dict=lambda: chunk('live', 1002)) for i in range(size)]
    status = {}
    incoming = chunk('wal', 1000)
    if not device:
        incoming.pop('client_device_id', None)
    sync_live_overlap.find_sync_live_overlap_candidates(user, incoming, diagnostics=status)
    expected = {'lookup_complete': size < 128 and device}
    if size == 128:
        expected['incomplete_reason'] = 'page_cap'
    elif not device:
        expected['incomplete_reason'] = 'no_device'
    assert status == expected
    query.stream.assert_called_once_with(timeout=10)
    query.limit.assert_called_once_with(128)
    assert 'transcript_segments' not in query.select.call_args.args[0]


def test_discovery_exception_records_lookup_failed_before_other_reasons():
    user = MagicMock()
    user.collection.side_effect = RuntimeError('synthetic failure')
    status = {'incomplete_reason': 'page_cap'}
    incoming = chunk('wal', 1000)
    incoming.pop('client_device_id', None)
    assert sync_live_overlap.find_sync_live_overlap_candidates(user, incoming, diagnostics=status) == ()
    assert status == {'lookup_complete': False, 'incomplete_reason': 'lookup_failed'}


def test_observation_logger_never_raises(monkeypatch):
    from utils.sync import intake_completion

    def fail(*args, **kwargs):
        raise RuntimeError('synthetic log failure')

    monkeypatch.setattr(intake_completion.logger, 'info', fail)
    log_sync_lineage_created(
        {'outcome': 'created_unknown', 'checked_live_candidates_bucket': '0', 'lookup_complete': False}
    )


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

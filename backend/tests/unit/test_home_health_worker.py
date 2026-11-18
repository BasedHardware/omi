"""Home health observes the customer-facing contract without exporting customer data."""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from scripts import home_health_worker as worker
from services import home_health_repair as repair, home_health_review as review
from utils.conversations.summary_delivery import deadline_seconds


def row(now, **overrides):
    return {
        'status': 'completed',
        'record_lane_owner': 'batch_live_v1',
        'private_cloud_sync_enabled': True,
        'data_protection_level': 'enhanced',
        'created_at': now - timedelta(hours=3),
        'started_at': now - timedelta(hours=3),
        'finished_at': now - timedelta(hours=2, minutes=59),
        'has_content': True,
        'content_word_units': 45,
        'record_projection_revision': 3,
        'sync_content_revision': 4,
        'summary_output_present': False,
        'structured': {'title': 'Discussion notes', 'emoji': '💬'},
        **overrides,
    }


@pytest.fixture
def now():
    return datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def flags(monkeypatch):
    for name in ('HOME_STEP_PROJECTION', 'SUMMARY_PROJECTION_DEBT_ENABLED', 'HOME_TRANSCRIPTION_PRESENTATION_GATE'):
        monkeypatch.delenv(name, raising=False)


def test_landed_speech_without_debt_and_the_same_blank_card_are_two_signals(now):
    metrics, findings = review.inspect_row(
        row(now, summary_title_provenance='server_minimum', structured={'emoji': '💬'}), now=now
    )
    assert {'transcript_expected', 'notes_expected', 'ready_cards'} <= metrics
    assert {'notes_not_scheduled', 'ready_card_blank', 'ready_title_missing'} <= findings
    assert 'transcript_wait_expired' not in findings
    assert 'ready_emoji_default' not in findings  # quality denominator is summarized cards


@pytest.mark.parametrize(
    'status,updates,expected',
    [
        ('in_progress', {}, 'capture_not_completed'),
        (
            'completed',
            {'record_projection_revision': 0, 'structured': {}, 'home_transcription_deadline_at': timedelta(hours=-30)},
            'transcript_wait_expired',
        ),
        ('completed', {'summary_due_at': -1}, 'notes_overdue'),
        (
            'completed',
            {'summary_output_present': True, 'structured': {'title': 'Discussion notes', 'emoji': '💬'}},
            'summary_without_preview',
        ),
    ],
)
def test_distinct_customer_symptoms(now, status, updates, expected):
    updated = {key: now + value if isinstance(value, timedelta) else value for key, value in updates.items()}
    assert expected in review.inspect_row(row(now, status=status, **updated), now=now)[1]


def test_manual_title_notes_and_quiet_capture_do_not_get_flagged_as_missing(now):
    assert 'ready_title_generic' not in review.inspect_row(row(now, user_title='Discussion notes'), now=now)[1]
    notes = row(
        now, summary_output_present=True, structured={'title': 'Test title', 'overview': 'Test notes', 'emoji': '🙂'}
    )
    assert not review.inspect_row(notes, now=now)[1]
    blocked = row(now, summary_blocked_reason='content_below_floor')
    assert review.inspect_row(blocked, now=now) == ({'rows', 'hidden_by_design'}, set())
    assert review.inspect_row(row(now, data_protection_level='private'), now=now)[0] == {'rows', 'protected_or_unknown'}
    assert review.inspect_row(row(now, terminal_no_derived_effects=True), now=now)[0] == {
        'rows',
        'terminal_without_derivatives',
    }
    assert 'summary_receipt_unknown' in review.inspect_row(row(now, summary_output_present=None), now=now)[0]


def test_receipt_suppresses_small_cells_and_never_exports_content(now):
    observations = review.Review()
    private_title = 'private-title-unique'
    private_overview = 'private-overview-unique'
    for index in range(review.MIN_REPORT_OWNERS):
        for _ in range(review.REPEATED_CARDS):
            observations.observe(
                f'private-owner-unique-{index}',
                row(
                    now,
                    summary_output_present=True,
                    structured={'title': private_title, 'overview': private_overview, 'emoji': '💬'},
                ),
                now=now,
            )
    observations.observe(
        'private-owner-extra',
        row(now, summary_title_provenance='server_minimum', structured={'emoji': '💬'}),
        now=now,
    )
    receipt = observations.receipt()
    encoded = json.dumps(receipt)
    assert not any(value in encoded for value in (private_title, private_overview, 'private-owner'))
    assert 'ready_card_blank' not in {item['issue_key'] for item in receipt['feedback']}
    recurring = next(item for item in receipt['feedback'] if item['issue_key'] == 'ready_emoji_default')
    assert recurring['owners_with_repeated_symptom'] == review.MIN_REPORT_OWNERS
    assert recurring['affected_rows'] == recurring['observable_rows'] == 15


@pytest.mark.parametrize(
    'updates',
    [
        {'data_protection_level': 'private'},
        {'deleted': True},
        {'discarded': True},
        {'user_title': 'Personal title'},
        {'user_overview': ''},
        {'content_word_units': 0},
        {'summary_due_at': 4},
        {'summary_output_present': True},
        {'summary_output_present': None},
        {'summary_blocked_reason': 'empty_output_exhausted'},
        {'sync_content_revision': True},
        {'record_projection_revision': 0},
        {'finalization_status': 'leased'},
        {'structured': {'title': 'Existing title'}},
        {'record_lane_owner': 'batch_sync_v1'},
        {'structured': {'title': 'Discussion notes', 'sections': [{'body_markdown': 'Existing notes'}]}},
    ],
)
def test_candidate_does_not_rearm_protected_existing_or_terminal_rows(now, updates):
    assert not repair.candidate(row(now, **updates), now=now.timestamp())


@pytest.mark.parametrize(
    'derived',
    [{'action_items': [{'description': 'Test task'}]}, {'events': [{'title': 'Test event'}]}],
)
def test_derived_items_are_not_a_summary(now, derived):
    prior = row(now, structured={'title': 'Discussion notes', **derived})
    assert repair.candidate(prior, now=now.timestamp())


@pytest.mark.parametrize('lane,expected_lane', [('fresh', 'fresh'), (None, 'batch')])
def test_repair_rechecks_revision_and_arms_only_the_original_clock(now, lane, expected_lane):
    prior = row(now, summary_first_pending_at=now.timestamp() - 600, summary_lane=lane)
    ref = Mock(id='test_capture')
    transaction, client = Mock(), Mock()
    ref.get.side_effect = lambda *, transaction, field_paths: SimpleNamespace(
        exists=True,
        to_dict=lambda: {key: value for key, value in prior.items() if key in field_paths},
    )
    ref.parent.parent.get.return_value = SimpleNamespace(exists=True, to_dict=lambda: {})
    client.collection.return_value.document.return_value.get.return_value.exists = False
    with patch.object(repair, 'assert_batch_write_allowed') as privacy:
        assert (
            repair.commit(client, transaction, ref, 'test_owner', (1, 1, None, None), now=now.timestamp())
            == 'superseded'
        )
        privacy.assert_not_called()
        transaction.update.assert_not_called()
        assert (
            repair.commit(client, transaction, ref, 'test_owner', repair.generation(prior), now=now.timestamp())
            == 'armed'
        )
        privacy.assert_called_once_with(
            client, transaction, 'test_owner', conversation_ids=('test_capture',), allow_token_mint=False
        )
    transaction.update.assert_called_once_with(
        ref,
        {
            'summary_first_pending_at': prior['summary_first_pending_at'],
            'summary_due_at': prior['summary_first_pending_at'] + deadline_seconds(),
            'summary_title_provenance': 'server_minimum',
            'summary_lane': expected_lane,
        },
    )


@pytest.mark.parametrize(
    'kind,expected', [('byok', 'provider_refused'), ('job', 'finalization_refused'), ('outbox', 'outbox_owned')]
)
def test_repair_respects_other_writers_and_provider_policy(now, kind, expected):
    prior = row(now, finalization_job_id='job' if kind == 'job' else None, finalization_revision=1)
    ref, transaction, client = Mock(id='test_capture'), Mock(), Mock()
    ref.get.return_value = SimpleNamespace(exists=True, to_dict=lambda: prior.copy())
    ref.parent.parent.get.return_value = SimpleNamespace(
        exists=True, to_dict=lambda: {'byok': {'active': kind == 'byok'}}
    )
    snapshot = SimpleNamespace(exists=kind == 'outbox', to_dict=lambda: {})
    client.collection.return_value.document.return_value.get.return_value = snapshot
    with patch.object(repair, 'assert_batch_write_allowed'):
        assert (
            repair.commit(client, transaction, ref, 'test_owner', repair.generation(prior), now=now.timestamp())
            == expected
        )
    transaction.update.assert_not_called()


def test_repair_never_reads_card_fields_when_protection_is_unknown(now):
    prior = row(now)
    del prior['private_cloud_sync_enabled']
    ref, transaction, client = Mock(), Mock(), Mock()
    ref.get.return_value = SimpleNamespace(exists=True, to_dict=lambda: prior)
    assert (
        repair.commit(client, transaction, ref, 'test_owner', repair.generation(prior), now=now.timestamp())
        == 'superseded'
    )
    ref.get.assert_called_once_with(transaction=transaction, field_paths=repair.APPLY_METADATA_FIELDS)
    transaction.update.assert_not_called()


def _page(now, count, limit=5):
    return count, [
        (
            f'private-test-{index}',
            SimpleNamespace(path=f'users/private-test-{index}/conversations/private-test-row'),
            row(now),
        )
        for index in range(min(count, limit))
    ]


def _args(now, **updates):
    return SimpleNamespace(
        **{
            'lane': 'batch_live_v1',
            'start': now - timedelta(hours=4),
            'end': now - timedelta(hours=1),
            'per_status': 5,
            'apply': False,
            'max_writes': 2,
            'execute_before': now + timedelta(minutes=5),
            **updates,
        }
    )


def test_review_and_apply_use_fixed_read_and_write_caps(now):
    with (
        patch.object(
            worker, 'scan', side_effect=lambda *a, **kw: _page(now, 6) if kw['status'] == 'completed' else (0, [])
        ),
        patch.object(repair, 'arm', return_value='armed') as arm,
    ):
        receipt, failed = worker.run(None, _args(now), now=now)
        assert not failed and receipt['survey_documents'] == 6
        assert receipt['status_coverage']['completed'] == 'capped'
        assert receipt['repair']['candidate_owners'] == 5
        arm.assert_not_called()
        receipt, failed = worker.run(None, _args(now, apply=True), now=now)
        assert not failed and arm.call_count == 2 and receipt['repair']['outcomes'] == {'armed': 2}
        assert 'private-test' not in json.dumps(receipt)


def test_query_error_cannot_trigger_partial_apply_or_leak_exception(now):
    with (
        patch.object(worker, 'scan', side_effect=[_page(now, 5), RuntimeError('private-test-path')]),
        patch.object(repair, 'arm') as arm,
    ):
        receipt, failed = worker.run(None, _args(now, apply=True), now=now)
    assert failed and receipt['status_coverage']['in_progress'] == 'query_failed'
    assert receipt['status_coverage']['processing'] == 'not_scanned'
    assert receipt['status_coverage']['merging'] == 'not_scanned'
    assert receipt['status_coverage']['failed'] == 'not_scanned'
    arm.assert_not_called()
    assert 'private-test-path' not in json.dumps(receipt)


def test_small_status_cell_suppresses_read_count_even_when_other_rows_are_reportable(now):
    def scan(*args, **kwargs):
        if kwargs['status'] == 'completed':
            return _page(now, 5)
        if kwargs['status'] == 'processing':
            return _page(now, 1)
        return 0, []

    with patch.object(worker, 'scan', side_effect=scan):
        receipt, failed = worker.run(None, _args(now), now=now)
    assert not failed and not receipt['suppressed']
    assert receipt['survey_documents'] is None
    assert receipt['status_coverage']['processing'] == 'suppressed'


def test_existing_notes_attempt_is_not_reported_as_missing_admission(now):
    prior = row(now, notes_written_at=now - timedelta(hours=1))
    metrics, findings = review.inspect_row(prior, now=now)
    assert 'notes_attempt_without_delivery_receipt' in metrics
    assert 'notes_not_scheduled' not in findings
    assert not repair.candidate(prior, now=now.timestamp())


def test_expired_apply_cannot_enter_the_transaction(now):
    client = Mock()
    result = repair.arm(client, Mock(), 'test_owner', (), deadline=0, execute_before=now.timestamp() - 1)
    assert result == 'deadline_reached'
    client.transaction.assert_not_called()


def test_apply_deadline_prevents_a_late_commit_rpc(monkeypatch):
    monotonic = 10.0
    monkeypatch.setattr(repair.rpc_deadline, 'now', lambda: monotonic)
    monkeypatch.setattr(repair.time, 'time', lambda: 1000.0)
    monkeypatch.setattr(repair.firestore, 'transactional', lambda function: function)
    underlying_commit = Mock()
    client = SimpleNamespace(_firestore_api=SimpleNamespace(commit=underlying_commit), transaction=Mock())

    def after_reads(*args, **kwargs):
        nonlocal monotonic
        monotonic = 12.0
        return client._firestore_api.commit()

    monkeypatch.setattr(repair, 'commit', after_reads)
    assert repair.arm(client, Mock(), 'test_owner', (), deadline=11, execute_before=1005) == 'deadline_reached'
    underlying_commit.assert_not_called()


def test_scan_uses_the_registered_masked_finish_time_query(now, monkeypatch):
    monkeypatch.setattr(worker.firestore, 'transactional', lambda fn: fn)
    client, query = Mock(), Mock()
    client.collection_group.return_value = query
    query.get.return_value = []
    for method in ('where', 'order_by', 'select', 'limit'):
        getattr(query, method).return_value = query
    start = now - timedelta(hours=1)
    scanned = worker.scan(
        client, lane='batch_live_v1', status='completed', start=start, end=now, limit=11, deadline=float('inf')
    )
    client.collection_group.assert_called_once_with('conversations')
    filters = [record.kwargs['filter'] for record in query.where.call_args_list]
    assert [(item.field_path, item.op_string, item.value) for item in filters] == [
        ('record_lane_owner', '==', 'batch_live_v1'),
        ('status', '==', 'completed'),
        ('finished_at', '>=', start),
        ('finished_at', '<', now),
    ]
    assert [(record.args, record.kwargs) for record in query.order_by.call_args_list] == [
        (('finished_at',), {'direction': worker.firestore.Query.DESCENDING}),
        (('__name__',), {'direction': worker.firestore.Query.DESCENDING}),
    ]
    query.select.assert_called_once_with(repair.DISCOVERY_FIELDS)
    assert not set(repair.DISCOVERY_FIELDS) & set(review.CARD_FIELDS)
    query.limit.assert_called_once_with(12)
    client.transaction.assert_called_once_with(read_only=True, max_attempts=1)
    query.get.assert_called_once_with(transaction=client.transaction.return_value)
    client.get_all.assert_not_called()
    assert scanned == (0, [])


def test_scan_fetches_card_fields_only_for_rows_with_known_permission(now, monkeypatch):
    monkeypatch.setattr(worker.firestore, 'transactional', lambda fn: fn)
    client, query = Mock(), Mock()
    client.collection_group.return_value = query
    for method in ('where', 'order_by', 'select', 'limit'):
        getattr(query, method).return_value = query
    metadata = [
        row(now),
        row(now, is_locked=True),
        row(now, data_protection_level='private'),
        row(now, private_cloud_sync_enabled=False),
        row(now),
        row(now),
    ]
    metadata[4].pop('private_cloud_sync_enabled')
    refs = [entry[1] for entry in _page(now, 6, limit=6)[1]]
    query.get.return_value = [
        SimpleNamespace(
            reference=ref,
            to_dict=lambda meta=meta: {key: value for key, value in meta.items() if key in repair.DISCOVERY_FIELDS},
        )
        for ref, meta in zip(refs, metadata)
    ]
    client.get_all.return_value = [
        SimpleNamespace(exists=True, reference=refs[0], to_dict=lambda: {'structured': {'title': 'Test title'}})
    ]
    scanned, rows = worker.scan(
        client, lane='batch_live_v1', status='completed', start=now, end=now, limit=5, deadline=float('inf')
    )
    client.get_all.assert_called_once_with(
        [refs[0]], field_paths=review.CARD_FIELDS, transaction=client.transaction.return_value
    )
    assert scanned == 6
    assert rows[0][2]['structured']['title'] == 'Test title'
    assert all('structured' not in entry[2] for entry in rows[1:])


def test_review_mask_preserves_partial_audio_visibility(now, monkeypatch):
    monkeypatch.setenv('HOME_HIDE_BELOW_FLOOR_ROWS', 'on')
    recent = row(
        now,
        record_projection_revision=0,
        record_audio_partial=True,
        started_at=now - timedelta(seconds=40),
        finished_at=now - timedelta(seconds=20),
    )
    masked = {key: value for key, value in recent.items() if key in review.METADATA_FIELDS}
    assert not review.hidden_for_review(masked)
    assert review.hidden_for_review({**masked, 'record_audio_partial': False})


def test_review_uses_the_current_legacy_list_recording_label(now):
    metrics, findings = review.inspect_row(row(now), now=now)
    assert 'ready_cards' in metrics and 'notes_not_scheduled' in findings
    assert 'ready_card_blank' not in findings and 'ready_title_missing' not in findings


def _serving(revision='first', percent=100):
    return {'status': {'traffic': [{'revisionName': f'backend-integration-{revision}', 'percent': percent}]}}


def _sweep_revision(name, flags=None):
    flags = {
        'OMI_BACKEND_RELEASE_SHA': 'a' * 40,
        'SUMMARY_DEBT_REPAIR_ENABLED': 'true',
        **(flags or {}),
    }
    return {
        'metadata': {'name': name},
        'spec': {'containers': [{'env': [{'name': key, 'value': value} for key, value in flags.items()]}]},
    }


@pytest.mark.parametrize(
    'flags,allowed',
    [
        ({}, True),
        ({'SUMMARY_PROJECTION_DEBT_ENABLED': 'off'}, False),
        ({'SUMMARY_PROJECTION_DEBT_ENABLED': 'false'}, False),
        ({'SUMMARY_DEBT_REPAIR_ENABLED': 'false'}, False),
        ({'SUMMARY_DEBT_REPAIR_ENABLED': 'on', 'CAPTURE_COVERAGE_MODE': 'serve'}, True),
        ({'SUMMARY_DEBT_REPAIR_ENABLED': 'on', 'CAPTURE_COVERAGE_MODE': 'off'}, False),
        ({'SUMMARY_PROJECTION_DEBT_ENABLED': None}, False),
    ],
)
def test_production_admission_uses_receiving_revision_settings(monkeypatch, flags, allowed):
    def describe(kind, name, deadline):
        assert deadline == 400
        return _serving() if kind == 'services' else _sweep_revision(name, flags)

    monkeypatch.setattr(worker.runtime, '_describe', describe)
    assert worker.runtime.serving_allows_repair(deadline=400) is allowed


def test_production_admission_refuses_changed_traffic_or_an_unreadable_revision(monkeypatch):
    describe = Mock(side_effect=[_serving(), _sweep_revision('backend-integration-first'), _serving('second')])
    monkeypatch.setattr(worker.runtime, '_describe', describe)
    assert not worker.runtime.serving_allows_repair(deadline=400)
    describe.side_effect = OSError('private log value')
    assert not worker.runtime.serving_allows_repair(deadline=400)


def test_production_admission_refuses_when_any_receiving_revision_has_admission_off(monkeypatch):
    mixed = _serving(percent=75)
    mixed['status']['traffic'].extend(_serving('second', percent=25)['status']['traffic'])
    second = _sweep_revision('backend-integration-second', {'SUMMARY_PROJECTION_DEBT_ENABLED': 'off'})
    describe = Mock(side_effect=[mixed, _sweep_revision('backend-integration-first'), second])
    monkeypatch.setattr(worker.runtime, '_describe', describe)
    assert not worker.runtime.serving_allows_repair(deadline=400)


def test_production_apply_refuses_before_any_write_when_live_policy_is_disabled(now):
    client = SimpleNamespace(project=worker.runtime.PRODUCTION_PROJECT)
    with (
        patch.object(
            worker, 'scan', side_effect=lambda *a, **kw: _page(now, 5) if kw['status'] == 'completed' else (0, [])
        ),
        patch.object(worker.runtime, 'serving_allows_repair', return_value=False) as verify,
        patch.object(repair, 'arm') as arm,
    ):
        receipt, failed = worker.run(client, _args(now, apply=True), now=now)
    assert failed and receipt['repair']['serving_policy'] == 'unavailable_or_disabled'
    verify.assert_called_once()
    arm.assert_not_called()

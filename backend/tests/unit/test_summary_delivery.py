"""Summary success is a fenced durable outcome, never upload/model success."""

import importlib
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from config import summary_guarantee as flags
from utils.conversations import summary_delivery as delivery
from utils.conversations.deterministic_minimum import build_deterministic_minimum_structured


@pytest.fixture(scope='module', autouse=True)
def summary_database_dependency():
    # The banked-summary branch lazily imports effective_user_title. Load the
    # real dependency in setup so the call CPU guard measures merge logic,
    # while import failures still fail this suite and all assertions stay real.
    importlib.import_module('database.conversations')


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.delenv('FIRST_SUMMARY_UID_ALLOWLIST', raising=False)


def minimum():
    return dict(
        status='completed',
        summary_output_present=False,
        structured={'title': 'Server title', 'title_provenance': 'server_minimum', 'overview': '', 'sections': []},
    )


def debt():
    row = minimum()
    delivery.prepare(row, 'u', now=100)
    return row


def test_first_summary_provenance_covers_known_owners_when_merge_is_disabled(monkeypatch):
    monkeypatch.setenv('CONVERSATION_MERGE_BEFORE_PROCESSING', 'false')
    row = SimpleNamespace(transcript_segments=[])
    assert 'title_provenance' not in build_deterministic_minimum_structured(row, uid=None).model_dump()
    assert 'title_provenance' not in build_deterministic_minimum_structured(row).model_dump()
    assert build_deterministic_minimum_structured(row, uid='outside-owner').model_dump()['title_provenance'] == (
        'server_minimum'
    )


def test_server_title_provenance_is_not_a_model_or_manual_title(enabled):
    result = build_deterministic_minimum_structured(SimpleNamespace(transcript_segments=[]), uid='u')
    assert result.model_dump()['title_provenance'] == 'server_minimum'
    assert 'title_provenance' not in result.model_json_schema()['properties']
    assert delivery.refusal(debt()) is None
    for field, value in [
        ('user_title', 'Edited'),
        ('user_overview', ''),
        ('discarded', True),
        ('deleted', True),
        ('is_locked', True),
        ('deferred', True),
        ('processing_state', 'local_pending'),
        ('data_protection_level', 'e2ee'),
        ('finalization_job_id', 'owned'),
        ('finalization_status', 'blocked_byok'),
    ]:
        assert delivery.refusal({**debt(), field: value}) is not None
    assert delivery.refusal({**debt(), 'summary_title_provenance': 'unknown'}) == 'unknown_provenance'


def test_deadline_metadata_survives_appends(enabled):
    row = debt()
    delivery.prepare(row, 'u', now=10000)
    assert row['summary_first_pending_at'] == 100
    assert row['summary_due_at'] == 220


def test_current_finalizer_finishes_completed_minimum_but_background_repair_cannot(enabled, monkeypatch):
    row = {**debt(), 'finalization_job_id': 'current-job', 'finalization_status': 'queued'}
    assert delivery.refusal(row) == 'generation_owned'
    assert delivery.finalization_pending(row, 'u', 'current-job')
    for changes in (
        {'structured': {'overview': 'Already delivered'}},
        {'user_title': 'Manual title'},
        {'deleted': True},
        {'discarded': True},
        {'terminal_no_derived_effects': True},
        {'data_protection_level': 'e2ee'},
        {'summary_title_provenance': None},
        {'summary_blocked_reason': 'empty_output_exhausted'},
        {'finalization_status': 'blocked_byok'},
        {'finalization_job_id': 'replacement-job'},
        {'finalization_job_id': None},
    ):
        assert not delivery.finalization_pending({**row, **changes}, 'u', 'current-job')


@pytest.mark.parametrize('finish,expected', [(50, 1900), (1800, 200), (2100, None), (None, None)])
def test_post_speech_latency_excludes_time_before_acceptance_and_open_speech(enabled, finish, expected):
    row = debt()
    if finish is not None:
        row['finished_at'] = datetime.fromtimestamp(finish, timezone.utc)
    receipt = delivery.merge_result(row, {'status': 'completed', 'summary_output_present': True}, 'u', now=2000)
    assert receipt['latency'] == 1900
    assert receipt['closed_latency'] == expected


def test_intake_discard_never_indexes_debt_and_keep_gets_a_new_deadline(enabled):
    row = {**minimum(), 'discarded': True}
    delivery.prepare(row, 'u', now=100)
    assert row['summary_due_at'] is None
    assert row['summary_discard_receipted']
    assert 'summary_first_pending_at' not in row
    delivery.prepare(row, 'u', now=200)
    assert row['summary_due_at'] is None
    row['discarded'] = False
    delivery.prepare(row, 'u', now=300)
    assert row['summary_due_at'] == 420 and row['summary_first_pending_at'] == 300


def test_existing_due_discard_and_exhausted_empty_output_leave_the_index(enabled):
    row = {**debt(), 'discarded': True}
    delivery.prepare(row, 'u', now=1000)
    assert row['summary_due_at'] is None
    blocked = {**debt(), 'summary_blocked_reason': 'empty_output_exhausted'}
    delivery.prepare(blocked, 'u', now=1000)
    assert blocked['summary_due_at'] is None
    assert delivery.refusal(blocked) == 'empty_output_exhausted'


def test_only_owner_replacement_fences_a_live_result_after_expiry():
    token = delivery.PROCESS_CONTEXT.set({'owner': 'same', 'claimed': True, 'lease_until': 1})
    try:
        assert not delivery.processing_fenced({'summary_processing_owner': 'same', 'summary_processing_lease_until': 1})
        assert delivery.processing_fenced({'summary_processing_owner': 'replacement'})
    finally:
        delivery.PROCESS_CONTEXT.reset(token)


def test_actions_events_title_and_empty_sections_do_not_satisfy_summary():
    for structured in (
        {'title': 't'},
        {'overview': '  ', 'action_items': [1]},
        {'events': [1]},
        {'sections': [{'title': 'Heading', 'body_markdown': ' '}]},
    ):
        assert not delivery.present(structured)
    assert delivery.present({'sections': [{'body_markdown': 'A supported note.'}]})
    assert delivery.present({'overview': 'A supported overview.'})


def test_empty_model_output_retains_debt_and_prior_good_output(enabled):
    row = debt()
    with pytest.raises(delivery.SummaryOutputUnavailable):
        delivery.merge_result(row, minimum(), 'u', now=300)
    assert row['summary_due_at'] == 220
    # A failed model attempt never gets to overwrite a prior usable summary:
    # the enriched row now commits (no lane stranding without an outbox), but
    # the banked content and receipts are re-applied onto the write instead
    # of letting the empty structured payload clobber them.
    old = {
        **row,
        'structured': {'title': 'Kept', 'overview': 'Banked summary'},
        'summary_completed_at': 150,
        'summary_due_at': 220,  # Legacy residue must not survive this return.
        'summary_output_present': True,
    }
    empty_write = minimum()
    assert delivery.merge_result(old, empty_write, 'u', now=300) is None
    banked_structured = empty_write['structured']
    assert isinstance(banked_structured, dict)
    assert banked_structured['overview'] == 'Banked summary'
    assert empty_write['summary_output_present'] is True
    assert empty_write['summary_completed_at'] == 150
    assert empty_write['summary_due_at'] is None


def test_lost_ack_does_not_emit_second_terminal_receipt(enabled):
    row = debt()
    write = {'status': 'completed', 'summary_output_present': True}
    receipt = delivery.merge_result(row, write, 'u', now=150)
    assert receipt['present'] and receipt['latency'] == 50
    assert write['summary_due_at'] is None and write['summary_completed_at'] == 150
    assert delivery.merge_result({**row, **write}, dict(write), 'u', now=200) is None


def test_generation_fence_and_manual_edit_after_admission(enabled):
    row = {**debt(), 'sync_content_revision': 2}
    token = delivery.REPAIR_CONTEXT.set({'summary_expected_revision': 2})
    try:
        assert not delivery.repair_fenced(row)
        assert delivery.repair_fenced({**row, 'sync_content_revision': 3})
        assert delivery.repair_fenced({**row, 'user_title': 'Manual'})
        assert delivery.repair_fenced({**row, 'finalization_job_id': 'new-generation'})
    finally:
        delivery.REPAIR_CONTEXT.reset(token)


def test_invalid_deadlines_remain_bounded(enabled, monkeypatch):
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_SECONDS', 'invalid')
    assert flags.deadline_seconds() == 120
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_SECONDS', '999')
    assert flags.deadline_seconds() == 120


def test_local_only_minimum_is_explicitly_blocked_not_retried_as_empty(enabled):
    write = {**minimum(), 'terminal_no_derived_effects': True}
    context = {'owner': 'worker', 'lease_until': 999}
    token = delivery.PROCESS_CONTEXT.set(context)
    try:
        receipt = delivery.merge_result(debt(), write, 'u', now=150)
        assert receipt['reason'] == 'local_only' and not receipt['present']
        assert write['summary_due_at'] is None and context['blocked_reason'] == 'local_only'
    finally:
        delivery.PROCESS_CONTEXT.reset(token)


def test_discard_receipt_does_not_hide_a_later_first_summary(enabled):
    row = debt()
    write = {'status': 'completed', 'discarded': True, 'summary_output_present': False}
    receipt = delivery.merge_result(row, write, 'u', now=150)
    assert not receipt['present'] and 'summary_completed_at' not in write
    assert write['summary_discard_receipted']
    assert delivery.merge_result({**row, **write}, dict(write), 'u', now=151) is None
    restored = {**row, **write, 'discarded': False}
    delivery.prepare(restored, 'u', now=200)
    assert restored['summary_due_at'] == 320 and restored['summary_first_pending_at'] == 200
    output = {'status': 'completed', 'summary_output_present': True}
    receipt = delivery.merge_result(restored, output, 'u', now=250)
    assert receipt['present'] and receipt['latency'] == 50


@pytest.mark.parametrize('gauge', [delivery.EXPIRED_SEEN, delivery.NEAR_EXPIRY_ADMITTED])
def test_repair_gauge_is_declared_for_production_scraping(gauge):
    import json
    from pathlib import Path

    metric = next(iter(gauge.collect()))
    assert metric.type == 'gauge'
    assert metric.samples[0].labels == {}
    inventory = json.loads(
        (Path(__file__).resolve().parents[3] / 'backend/charts/monitoring/metric-inventory.prod.json').read_text()
    )
    assert metric.name in inventory['declared_metrics']


def test_repair_counter_is_declared_for_production_scraping():
    import json
    from pathlib import Path

    metric = next(iter(delivery.REPAIR.collect()))
    assert metric.type == 'counter'
    assert delivery.REPAIR._labelnames == ('outcome',)
    inventory = json.loads(
        (Path(__file__).resolve().parents[3] / 'backend/charts/monitoring/metric-inventory.prod.json').read_text()
    )
    assert metric.name + '_total' in inventory['declared_metrics']


@pytest.mark.parametrize('hours', ['72', '1'])
@pytest.mark.parametrize('phase', ['near_expiry', 'newest'])
@pytest.mark.parametrize('cursor_kind', ['legacy', 'expired', 'current', 'wrong_phase', 'wrong_window'])
def test_repair_query_uses_gate_window_and_safe_cursor(monkeypatch, hours, phase, cursor_kind):
    from database.summary_debt_queries import due_conversations
    from tests.support.firestore_shape_recorder import RecordingFirestore, install_recorder
    from utils.enrichment.age_gate import max_age_seconds

    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', hours)
    now = 1_800_000_000.0
    window = max_age_seconds()
    pending = now - window + 1 if phase == 'near_expiry' else now - 1
    after = {'due': now - 1, 'path': 'users/synthetic/conversations/c', 'pending': pending}
    if cursor_kind != 'legacy':
        after.update(phase=phase, window=window)
    if cursor_kind == 'expired':
        after['pending'] = now - 73 * 3600
    if cursor_kind == 'wrong_phase':
        after['phase'] = 'newest' if phase == 'near_expiry' else 'near_expiry'
    if cursor_kind == 'wrong_window':
        after['window'] = -1
    client = RecordingFirestore()
    with install_recorder(client), client.recording_context('database.summary_debt_queries.due_conversations', {}):
        due_conversations(now=now, phase=phase, limit=1000, after=after, firestore_client=client)
    shape = client.shapes[0]
    assert shape.limit == 500
    filters = {(f.field, f.operator, f.value) for f in shape.filters}
    assert ('summary_due_at', '<=', now) in filters
    assert shape.orders == (
        ('summary_first_pending_at', 'ASCENDING' if phase == 'near_expiry' else 'DESCENDING'),
        ('summary_due_at', 'ASCENDING'),
        ('__name__', 'ASCENDING'),
    )
    assert ('summary_first_pending_at', '>=', now - window) in filters
    assert (
        'summary_first_pending_at',
        '<=' if phase == 'near_expiry' else '>',
        now - window + flags.REPAIR_NEAR_EXPIRY_SECONDS,
    ) in filters
    assert shape.uses_cursors is (cursor_kind == 'current')


@pytest.mark.parametrize('cursor_kind', ['legacy', 'gated', 'old_disabled_phase'])
@pytest.mark.parametrize('pending_kind', ['missing', 'null'])
def test_disabled_gate_scans_and_admits_missing_pending_with_legacy_query(monkeypatch, cursor_kind, pending_kind):
    from services import summary_debt_repair as repair
    from tests.support.firestore_shape_recorder import RecordingFirestore, install_recorder

    monkeypatch.setenv('SUMMARY_DEBT_REPAIR_ENABLED', 'true')
    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', '0')
    cursor = {'due': 219, 'path': 'users/synthetic/conversations/previous'}
    if cursor_kind != 'legacy':
        cursor.update(version=2, pending=100, phase='newest', window=72 * 3600 if cursor_kind == 'gated' else 0)
    client = RecordingFirestore({repair.CURSOR: cursor})
    row = {**debt(), 'summary_due_at': 220}
    if pending_kind == 'missing':
        del row['summary_first_pending_at']
    else:
        row['summary_first_pending_at'] = None
    snapshot = client.snapshot('users/synthetic/conversations/c', row)
    client.queue_results([snapshot])
    monkeypatch.setattr(repair, 'account_deletion_blocks_user_work', lambda _: False)
    admitted = []
    monkeypatch.setattr(repair, 'redrive', lambda *args, **kwargs: admitted.append(args[2]) or True)
    with install_recorder(client):
        counts = repair.tick(now=220, client=client)
    assert counts == {'scanned': 1, 'admitted': 1, 'near_expiry_admitted': 0, 'errors': 0, 'expired_seen': 0}
    assert admitted == ['c']
    assert len(client.shapes) == 1  # No expiry-phase query when the gate is off.
    shape = client.shapes[0]
    assert [(f.field, f.operator, f.value) for f in shape.filters] == [('summary_due_at', '<=', 220)]
    assert shape.orders == (('summary_due_at', 'ASCENDING'), ('__name__', 'ASCENDING'))
    assert shape.uses_cursors is (cursor_kind == 'legacy')


@pytest.mark.parametrize(
    'due', [0, -10, datetime(2026, 1, 1, tzinfo=timezone.utc), float('inf'), float('-inf'), float('nan')]
)
def test_gated_cursor_preserves_finite_nonpositive_due_and_datetime(monkeypatch, due):
    from database.summary_debt_queries import due_conversations
    from tests.support.firestore_shape_recorder import RecordingFirestore, install_recorder

    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', '72')
    now = 1_800_000_000.0
    client = RecordingFirestore()
    cursor = {
        'phase': 'newest',
        'window': 72 * 3600,
        'pending': now - 1,
        'due': due,
        'path': 'users/synthetic/conversations/a',
    }
    with install_recorder(client):
        due_conversations(now=now, after=cursor, limit=1, firestore_client=client)
    shape = client.shapes[0]
    if isinstance(due, datetime) or due in (0, -10):
        assert dict(shape.cursors)['start_after']['summary_due_at'] == (
            due.timestamp() if isinstance(due, datetime) else due
        )
    else:
        assert not shape.uses_cursors


@pytest.mark.parametrize('urgent_count', [0, 2], ids=['empty-near-expiry', 'owner-deferral'])
def test_newest_index_failure_finishes_near_expiry_progress_and_counts(monkeypatch, caplog, urgent_count):
    from google.api_core.exceptions import FailedPrecondition
    from services import summary_debt_repair as repair
    from tests.support.firestore_shape_recorder import (
        RecordingFirestore,
        RecordingQuery,
        RecordingTransaction,
        install_recorder,
    )

    monkeypatch.setenv('SUMMARY_DEBT_REPAIR_ENABLED', 'true')
    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', '72')
    monkeypatch.setattr(repair, 'REPAIR_QUERY_PAGE_LIMIT', 2)
    monkeypatch.setattr(repair, 'REPAIR_PER_OWNER_TICK_LIMIT', 1)
    monkeypatch.setattr(repair, 'account_deletion_blocks_user_work', lambda _: False)
    monkeypatch.setattr(repair, 'redrive', lambda *_args, **_kwargs: True)
    now = 1_800_000_000.0
    prior = {
        'phase': 'newest',
        'window': 72 * 3600,
        'pending': now - 1,
        'due': now - 1,
        'path': 'users/synthetic/conversations/z',
    }
    client = RecordingFirestore({repair.CURSOR: {'version': 2, 'phases': {'newest': prior}}})
    rows = [
        client.snapshot(
            f'users/synthetic/conversations/{name}',
            {**debt(), 'summary_first_pending_at': now - 72 * 3600 + 100 + i, 'summary_due_at': now - 1},
        )
        for i, name in enumerate(('a', 'b')[:urgent_count])
    ]
    client.queue_results(rows)
    client.queue_results([])
    original_stream = RecordingQuery.stream
    original_commit = RecordingTransaction._commit

    def stream(query, *args, **kwargs):
        if ('summary_first_pending_at', 'DESCENDING') in query._state.orders:
            raise FailedPrecondition('synthetic index unavailable')
        return original_stream(query, *args, **kwargs)

    def commit(transaction, *args, **kwargs):
        for operation, ref, payload in transaction._write_ops:
            assert operation in ('set', 'update')
            existing = client.documents.get(ref.path, {}) if operation == 'update' else {}
            client.documents[ref.path] = {**existing, **payload}
        return original_commit(transaction, *args, **kwargs)

    monkeypatch.setattr(RecordingQuery, 'stream', stream)
    monkeypatch.setattr(RecordingTransaction, '_commit', commit)

    def totals():
        return {
            sample.labels['outcome']: sample.value
            for metric in delivery.REPAIR.collect()
            for sample in metric.samples
            if sample.name.endswith('_total')
        }

    before = totals()
    with install_recorder(client):
        counts = repair.tick(now=now, client=client)
    expected_admitted = int(bool(urgent_count))
    assert counts == {
        'scanned': urgent_count,
        'admitted': expected_admitted,
        'near_expiry_admitted': expected_admitted,
        'errors': 1,
        'expired_seen': 0,
    }
    progress = client.documents[repair.CURSOR]
    assert progress['lease_until'] == 0
    assert progress['next_at'] == now + repair.REPAIR_INTERVAL_SECONDS
    assert progress['phases']['near_expiry'] is None  # Owner deferral does not pin discovery before exhaustion.
    assert progress['phases']['newest'] == prior
    assert (
        len(
            [
                r
                for r in caplog.records
                if r.message == 'event=summary_debt_repair_newest_index_unavailable outcome=error'
            ]
        )
        == 1
    )
    after = totals()
    assert {key: after[key] - before.get(key, 0) for key in after} == {
        'scanned': urgent_count,
        'admitted': expected_admitted,
        'near_expiry_admitted': expected_admitted,
        'error': 1,
        'expired_seen': 0,
    }


@pytest.mark.parametrize('phase,error_type', [('near_expiry', 'precondition'), ('newest', 'other')])
def test_query_errors_other_than_newest_precondition_propagate(monkeypatch, phase, error_type):
    from google.api_core.exceptions import FailedPrecondition
    from services import summary_debt_repair as repair
    from tests.support.firestore_shape_recorder import RecordingFirestore, install_recorder

    monkeypatch.setenv('SUMMARY_DEBT_REPAIR_ENABLED', 'true')
    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', '72')
    error = FailedPrecondition if error_type == 'precondition' else RuntimeError

    def query(**kwargs):
        if kwargs['phase'] == phase:
            raise error('synthetic query error')
        return []

    monkeypatch.setattr(repair, 'due_conversations', query)
    client = RecordingFirestore()
    with install_recorder(client), pytest.raises(error):
        repair.tick(now=1_800_000_000.0, client=client)


@pytest.fixture
def rotating_repair(monkeypatch):
    from services import summary_debt_repair as repair
    from tests.support.firestore_shape_recorder import RecordingFirestore, RecordingTransaction, install_recorder

    client = RecordingFirestore()
    phases = {'near_expiry': [], 'newest': []}
    original_commit = RecordingTransaction._commit

    def commit(transaction, *args, **kwargs):
        for operation, ref, payload in transaction._write_ops:
            assert operation in ('set', 'update')
            existing = client.documents.get(ref.path, {}) if operation == 'update' else {}
            client.documents[ref.path] = {**existing, **payload}
        return original_commit(transaction, *args, **kwargs)

    def query(*, phase, limit, after, **kwargs):
        rows = phases[phase]
        start = next((i + 1 for i, row in enumerate(rows) if after and row.reference.path == after['path']), 0)
        return [row for row in rows[start:] if row.to_dict().get('summary_due_at') is not None][:limit]

    monkeypatch.setenv('SUMMARY_DEBT_REPAIR_ENABLED', 'true')
    monkeypatch.setattr(repair, 'account_deletion_blocks_user_work', lambda _: False)
    monkeypatch.setattr(repair, 'due_conversations', query)
    monkeypatch.setattr(RecordingTransaction, '_commit', commit)
    with install_recorder(client):
        yield repair, client, phases


@pytest.mark.parametrize('hours', [72, 0])
@pytest.mark.parametrize('scan_limit', [8, 100])
def test_owner_deferrals_continue_across_ticks_and_all_debt_returns_after_wrap(
    rotating_repair, monkeypatch, hours, scan_limit
):
    from math import ceil

    repair, client, phases = rotating_repair
    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', str(hours))
    monkeypatch.setattr(repair, 'REPAIR_SCAN_LIMIT', scan_limit)
    monkeypatch.setattr(repair, 'REPAIR_PER_OWNER_TICK_LIMIT', 3)
    monkeypatch.setattr(repair, 'REPAIR_ADMISSION_LIMIT', 8)
    now = 1_800_000_000.0
    urgent = 3 if hours else 0
    for i in range(urgent):
        path = f'users/a/conversations/urgent-{i}'
        client.documents[path] = {**debt(), 'summary_first_pending_at': now - hours * 3600 + 480 + i}
        phases['near_expiry'].append(client.snapshot(path, client.documents[path]))
    for i in range(2 * scan_limit + 1):
        path = f'users/a/conversations/newest-{i:03}'
        client.documents[path] = {**debt(), 'summary_first_pending_at': now - i - 1}
        phases['newest'].append(client.snapshot(path, client.documents[path]))
    other = 'users/b/conversations/other'
    client.documents[other] = {**debt(), 'summary_first_pending_at': now - 1000}
    phases['newest'].append(client.snapshot(other, client.documents[other]))
    admitted = []
    failing = True

    def redrive(_, owner, cid, **kwargs):
        path = f'users/{owner}/conversations/{cid}'
        if failing and owner == 'a':
            raise RuntimeError('synthetic persistent admission failure')
        admitted.append(path)
        client.documents[path]['summary_due_at'] = None
        return True

    monkeypatch.setattr(repair, 'redrive', redrive)
    bound = ceil(len(phases['newest']) / (scan_limit - urgent))
    for tick in range(bound):
        counts = repair.tick(now=now + tick * repair.REPAIR_INTERVAL_SECONDS, client=client)
        assert counts['scanned'] <= scan_limit
        assert counts['admitted'] + counts['errors'] <= 8
        if tick == 0:
            cursor = client.documents[repair.CURSOR]
            progress = cursor['phases']['newest'] if hours else cursor
            assert progress['path'] == phases['newest'][scan_limit - urgent - 1].reference.path
    assert admitted == [other]  # B is discovered despite A consuming its quota every tick.
    deferred = phases['newest'][scan_limit - urgent - 1].reference.path
    assert client.documents[deferred]['summary_due_at'] == 220
    # Remove the urgent obstruction; every deferred newest row must come back
    # from the separate conversation debt store, including rows before wrap.
    for snapshot in phases['near_expiry']:
        client.documents[snapshot.reference.path]['summary_due_at'] = None
    failing = False
    for tick in range(bound, bound + ceil(len(phases['newest']) / 3) + 2):
        repair.tick(now=now + tick * repair.REPAIR_INTERVAL_SECONDS, client=client)
        if all(client.documents[row.reference.path]['summary_due_at'] is None for row in phases['newest']):
            break
    assert len(admitted) == len(set(admitted)) == len(phases['newest'])
    assert set(admitted) == {row.reference.path for row in phases['newest']}


@pytest.mark.parametrize('hours', [72, 0])
def test_emitted_continuation_cursor_keeps_rollback_shapes(rotating_repair, monkeypatch, hours):
    from database.summary_debt_queries import due_conversations

    repair, client, phases = rotating_repair
    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', str(hours))
    monkeypatch.setattr(repair, 'REPAIR_SCAN_LIMIT', 1)
    monkeypatch.setattr(repair, 'redrive', lambda *_args, **_kwargs: False)
    now = 1_800_000_000.0
    path = 'users/a/conversations/c'
    phases['newest'].append(client.snapshot(path, {**debt(), 'summary_first_pending_at': now - 1}))
    repair.tick(now=now, client=client)
    cursor = client.documents[repair.CURSOR]
    assert cursor['version'] == 2
    if hours:
        assert cursor['path'] is cursor['due'] is cursor['pending'] is None
        after = cursor['phases']['newest']
        assert set(after) == {'phase', 'window', 'path', 'due', 'pending'}
        # Current v2 readers continue; the older flat-cursor reader rewinds.
        due_conversations(now=now, after=after, firestore_client=client)
        assert client.shapes[-1].uses_cursors
        due_conversations(now=now, after=cursor, firestore_client=client)
        assert not client.shapes[-1].uses_cursors
    else:
        assert cursor['phases'] == {} and cursor['pending'] is None
        assert cursor['path'] == path and cursor['due'] == 220
        due_conversations(now=now, after=cursor, firestore_client=client)
        assert client.shapes[-1].uses_cursors

"""Pending exits use real proof/transaction paths, with synthetic local rows."""

from copy import deepcopy
from datetime import datetime, timezone
import io
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config import record_partial, record_seal_repair as config
from config.record_audio import record_identity
from database.record_pending_repair import cancel_missing
from tests.unit.test_record_seal_cluster_repair import FakeProcess, proof, settle
from tests.unit.test_record_seal_nojob import source, PATH, JOB_PATH, SERVER, SCOPE
from tests.unit.test_record_partial import source as partial_source, finish, pending, ROW, FLAGS, NOW
from utils.batch_pipeline import record_seal_cluster_repair as cluster, record_producer_proof
from utils.batch_pipeline.record_seal_budget import SweepBudget, BudgetExhausted


@pytest.fixture(autouse=True)
def legacy_jobs_order(monkeypatch):
    """Keep the original name-scan regressions; age ordering is covered in the cluster suite."""
    monkeypatch.setenv('RECORD_SEAL_REPAIR_AGE_ORDER', 'off')


@pytest.mark.parametrize(
    'setting,enabled', [(None, True), ('off', False), ('OFF', False), ('false', True), ('on', True)]
)
def test_discovery_kill_switch_is_default_on(monkeypatch, setting, enabled):
    if setting is None:
        monkeypatch.delenv('RECORD_SEAL_REPAIR_JOBS', raising=False)
    else:
        monkeypatch.setenv('RECORD_SEAL_REPAIR_JOBS', setting)
    assert config.jobs_enabled() is enabled


@pytest.mark.parametrize('blocker', ['producer_pending_tokens', 'upload_failed', 'already_closed_job_pending'])
@pytest.mark.parametrize('durable', [False, True])
def test_pending_seal_never_bypasses_full_tail_proof(source, proof, blocker, durable):
    assert settle(source, proof) == 'sealed_registered'
    row = source[1].rows[PATH]
    row.update(record_audio_closed=blocker == 'already_closed_job_pending')
    if blocker == 'producer_pending_tokens':
        row['record_upload_sessions'] = {'stopped': {'pod': 'gone', 'process_started_at': 100}}
    elif blocker == 'upload_failed':
        row['record_upload_failed'] = True
    if not durable:
        row['finished_at'] = datetime.fromtimestamp(150, timezone.utc)
    before = deepcopy(source[1].rows)
    result = settle(source, proof)
    expected = ('upload_failed_cleared' if blocker == 'upload_failed' else 'sealed') if durable else 'proof_refused'
    assert result == expected
    if durable:
        assert row['record_audio_closed']
        assert not row.get('record_upload_failed') and not row.get('record_upload_sessions')
        assert source[1].rows[JOB_PATH]['state'] == 'record_pending'  # Admission owns advancement.
    else:
        assert source[1].rows == before


@pytest.mark.parametrize('token', [True, {'pod': 'live', 'process_started_at': 100}])
def test_aged_pending_tokens_do_not_expire(source, proof, token):
    assert settle(source, proof) == 'sealed_registered'
    row = source[1].rows[PATH]
    row.update(record_audio_closed=False, record_upload_sessions={'unknown': token})
    value = proof()
    value['pods'] = {'live': 100}
    assert settle(source, lambda: value) == 'upload_pending'
    assert row['record_upload_sessions'] == {'unknown': token}


def test_noncompleted_capture_remains_with_finalization_owner(source, proof):
    assert settle(source, proof) == 'sealed_registered'
    source[1].rows[PATH].update(status='processing', record_audio_closed=False)
    before = deepcopy(source[1].rows)
    assert settle(source, proof) == 'not_completed'
    assert source[1].rows == before


def age_partial(partial_source):
    assert finish(partial_source) == 'partial_finished'
    row = partial_source[1].rows[ROW]
    row['record_audio_partial']['finished_partial_at'] = datetime.fromtimestamp(
        NOW - record_partial.INVENTORY_POLL_SECONDS, timezone.utc
    )
    return row


def repair_partial(source, proof=None, mode='apply'):
    return cluster.repair_one(
        source[0],
        object(),
        object(),
        '/'.join(ROW),
        flags=FLAGS,
        inventory=lambda: source[2] if proof is None else proof,
        budget=SweepBudget(240),
        mode=mode,
    )


@pytest.mark.parametrize('proof_ok', [False, True])
@pytest.mark.parametrize('state', ['record_pending', 'partial_retired'])
def test_aged_partial_retries_with_fresh_proof_and_keeps_barrier(partial_source, proof_ok, state):
    row = age_partial(partial_source)
    segment = record_identity('synthetic', 'record')[1]
    job = partial_source[1].rows[('batch_pipeline_dev_jobs', segment)]
    job['state'] = state
    job['partial_run'] = {'retired_at': NOW, 'coverage': [{'start': 100, 'end': 110}]}
    before_rows = deepcopy(partial_source[1].rows)
    before = deepcopy(row['record_audio_partial'])
    assert not cluster.settled(row)
    if proof_ok:
        assert repair_partial(partial_source) == 'partial_finished'
        assert cluster.settled(row)
        assert row['record_audio_partial']['generation'] == before['generation']
        assert row['record_audio_partial']['finished_at'] == before['finished_at']
        assert not row['record_audio_closed']
        assert pending(partial_source)['state'] == 'record_pending'
        assert 'retired_at' not in pending(partial_source)['partial_run']
        assert (
            pending(partial_source)['partial_run']['coverage']
            == before_rows[('batch_pipeline_dev_jobs', segment)]['partial_run']['coverage']
        )
    else:
        with pytest.raises(ValueError):
            repair_partial(partial_source, proof={})
        assert partial_source[1].rows == before_rows
        assert row['record_audio_partial'] == before
        assert not row['record_audio_closed']


@pytest.mark.parametrize(
    'change,expected',
    [
        ({'record_upload_sessions': {'live': True}}, 'upload_pending'),
        ({'private_cloud_sync_enabled': False}, 'privacy_refused'),
        ({'discarded': True}, 'privacy_refused'),
    ],
)
def test_aged_partial_refusal_never_clears_barrier(partial_source, change, expected):
    row = age_partial(partial_source)
    row.update(change)
    before = deepcopy(partial_source[1].rows)
    assert repair_partial(partial_source) == expected
    assert partial_source[1].rows == before


def test_aged_partial_plan_does_not_rearm(partial_source):
    age_partial(partial_source)
    before = deepcopy(partial_source[1].rows)
    assert repair_partial(partial_source, mode='plan') == 'partial_eligible'
    assert partial_source[1].rows == before


def test_partial_retired_after_inventory_retries_through_transaction(partial_source):
    row = age_partial(partial_source)
    job_id = record_identity('synthetic', 'record')[1]

    def inventory():
        partial_source[1].rows[('batch_pipeline_dev_jobs', job_id)]['state'] = 'partial_retired'
        return partial_source[2]

    assert (
        cluster.repair_one(
            partial_source[0],
            object(),
            object(),
            '/'.join(ROW),
            flags=FLAGS,
            inventory=inventory,
            budget=SweepBudget(240),
        )
        == 'partial_finished'
    )
    assert pending(partial_source)['state'] == 'record_pending'
    assert row['record_audio_partial'] and not row['record_audio_closed']


def missing(source, proof):
    assert settle(source, proof) == 'sealed_registered'
    source[1].rows.pop(PATH)
    source[1].rows[JOB_PATH]['enqueued_at'] = 0


@pytest.mark.parametrize('fenced', [False, True])
@pytest.mark.parametrize('preview', [False, True])
def test_missing_cancel_is_revocation_only_and_privacy_fenced(source, proof, fenced, preview):
    missing(source, proof)
    if fenced:
        source[1].rows[('users', 'synthetic', 'deleted_conversations', 'capture')] = {'deleted': True}
    before = deepcopy(source[1].rows)
    result = cancel_missing(source[0], 'synthetic', 'capture', now=config.MISSING_CONVERSATION_SECONDS, preview=preview)
    if preview:
        assert result == 'missing_cancel_eligible' and source[1].rows == before
    else:
        assert result == ('missing_cancelled_fenced' if fenced else 'missing_cancelled')
        assert source[1].rows[JOB_PATH]['state'] == 'cancelled'
        assert source[1].transactions[-1].updates == [(JOB_PATH, {'state': 'cancelled', 'merge_pending': False})]
        assert PATH not in source[1].rows
        assert 'expires_at' not in source[1].rows[JOB_PATH]
        assert source[1].rows[JOB_PATH]['record_snapshot'] == before[JOB_PATH]['record_snapshot']


@pytest.mark.parametrize('age', [0, config.MISSING_CONVERSATION_SECONDS - 1])
def test_missing_cancel_waits_seven_days(source, proof, age):
    missing(source, proof)
    before = deepcopy(source[1].rows)
    assert cancel_missing(source[0], 'synthetic', 'capture', now=age) == 'not_aged'
    assert source[1].rows == before


@pytest.mark.parametrize('change', ['conversation_returns', 'job_advances', 'identity_changes'])
def test_missing_cancel_rechecks_state(source, proof, change):
    missing(source, proof)
    if change == 'conversation_returns':
        source[1].rows[PATH] = {'status': 'completed'}
    elif change == 'job_advances':
        source[1].rows[JOB_PATH]['state'] = 'ready'
    else:
        source[1].rows[JOB_PATH]['owner_id'] = 'other'
    before = deepcopy(source[1].rows)
    assert cancel_missing(source[0], 'synthetic', 'capture', now=config.MISSING_CONVERSATION_SECONDS) == 'state_changed'
    assert source[1].rows == before


class JobsClient:
    def __init__(self, documents):
        self.documents, self.offset, self.cap, self.filters = documents, 0, None, []

    def collection(self, name):
        assert name == 'batch_pipeline_prod_jobs'
        self.offset = 0
        return self

    def where(self, *, filter):
        self.filters.append((filter.field_path, filter.op_string, filter.value))
        return self

    def order_by(self, field):
        assert field == '__name__'
        return self

    def select(self, fields):
        assert fields == ('owner_id', 'conversation_id', 'enqueued_at', 'record_content_id')
        return self

    def limit(self, cap):
        assert 0 < cap <= 128
        self.cap = cap
        return self

    def start_after(self, cursor):
        self.offset = next(i + 1 for i, doc in enumerate(self.documents) if doc.reference.path == cursor['__name__'])
        return self

    def document(self, path):
        return path

    def stream(self, **kwargs):
        assert 0 < kwargs['timeout'] <= 10 and kwargs['retry'] is None
        return self.documents[self.offset : self.offset + self.cap]


def job_doc(i, enqueued=0):
    cid = f'capture-{i}'
    content, segment = record_identity('synthetic', cid)
    return SimpleNamespace(
        id=segment,
        reference=SimpleNamespace(path=f'batch_pipeline_prod_jobs/{segment}'),
        to_dict=lambda: {
            'owner_id': 'synthetic',
            'conversation_id': cid,
            'record_content_id': content,
            'enqueued_at': enqueued,
        },
    )


def test_jobs_discovery_bounds_age_cursor_and_wrap():
    docs = [job_doc(i) for i in range(5)]
    client = JobsClient(docs)
    selected = {}
    rows, saturated, cursor = cluster.discover_jobs(
        client, budget=SweepBudget(60), max_rows=2, selected_cursors=selected
    )
    assert len(rows) == 2 and saturated and cursor == selected[rows[-1][0]]
    assert client.filters == [('state', '==', 'record_pending')]
    more, saturated, cursor = cluster.discover_jobs(client, budget=SweepBudget(60), after=cursor, max_rows=8)
    assert len(more) == 3 and not saturated and cursor is None
    assert len({path for path, _ in rows + more}) == 5
    assert cluster.discover_jobs(client, budget=SweepBudget(60), max_scan=1)[1]


@pytest.mark.parametrize('enqueued', [float('nan'), float('inf'), True, None, 'old', 10**12])
def test_jobs_discovery_refuses_unknown_or_young_age(enqueued):
    client = JobsClient([job_doc(1, enqueued)])
    assert cluster.discover_jobs(client, budget=SweepBudget(60))[0] == []


def test_jobs_discovery_deadline_checks_before_read():
    clock = [0]
    budget = SweepBudget(1, clock=lambda: clock[0])
    clock[0] = 1
    with pytest.raises(BudgetExhausted):
        cluster.discover_jobs(Mock(), budget=budget)


@pytest.mark.parametrize('blocker', [*sorted(cluster.BLOCKERS), 'private@example.invalid'])
def test_blocker_outcome_counters_are_allowlisted(blocker):
    process = FakeProcess([0], 0, result='proof_refused')
    process.stdout = io.BytesIO(json.dumps({'disposition': 'proof_refused', 'blocker': blocker}).encode())
    progress = []
    report = cluster.coordinate(
        [('private-path', 100)],
        workers=1,
        row_seconds=1,
        run_seconds=1,
        mode='apply',
        launch=lambda *_: process,
        progress=progress.append,
    )
    if blocker in cluster.BLOCKERS:
        assert report['blocker_outcomes'] == {f'{blocker}:proof_refused': 1}
        assert progress[0]['blocker'] == blocker
    else:
        assert report['blocker_outcomes'] == {} and blocker not in json.dumps(progress)


def test_aged_partial_without_coordinator_enters_real_finish_partial(partial_source):
    row = age_partial(partial_source)
    segment = record_identity('synthetic', 'record')[1]
    partial_source[1].rows[('batch_pipeline_dev_jobs', segment)].pop('partial_coordinator')
    assert repair_partial(partial_source) == 'partial_finished'
    assert pending(partial_source)['partial_coordinator']
    assert row['record_audio_partial'] and not row['record_audio_closed']


def test_missing_job_routes_to_cancellation_without_speech_proof(source, proof, monkeypatch):
    missing(source, proof)
    monkeypatch.setattr(cluster.time, 'time', lambda: config.MISSING_CONVERSATION_SECONDS)
    assert settle(source, Mock(side_effect=AssertionError('cancellation cannot claim speech'))) == 'missing_cancelled'
    assert source[1].rows[JOB_PATH]['state'] == 'cancelled'


def test_missing_cancel_kill_switch_rechecked_in_transaction(source, proof, monkeypatch):
    missing(source, proof)
    monkeypatch.setenv('RECORD_SEAL_REPAIR_JOBS', 'off')
    before = deepcopy(source[1].rows)
    assert cancel_missing(source[0], 'synthetic', 'capture', now=config.MISSING_CONVERSATION_SECONDS) == 'disabled'
    assert source[1].rows == before


def test_jobs_scan_advances_past_young_prefix_without_reading_unbounded_rows():
    client = JobsClient([job_doc(i, 10**12) for i in range(128)] + [job_doc(129)])
    rows, saturated, cursor = cluster.discover_jobs(client, budget=SweepBudget(60))
    assert rows == [] and saturated
    rows, saturated, cursor = cluster.discover_jobs(client, budget=SweepBudget(60), after=cursor)
    assert [path for path, _ in rows] == ['users/synthetic/conversations/capture-129']
    assert not saturated and cursor is None


def test_jobs_cursor_is_encrypted_independent_and_round_trips():
    from tests.unit.test_record_seal_cluster_repair import CursorClient
    from utils.batch_pipeline.record_seal_repair_cursor import RepairCursor

    class Frontiers:
        def __init__(self):
            self.states = {}

        def collection(self, name):
            assert name == 'batch_pipeline_prod_maintenance'
            return SimpleNamespace(document=lambda name: self.states.setdefault(name, CursorClient()))

    client = Frontiers()
    stamp = datetime(2026, 11, 1, tzinfo=timezone.utc)
    budget = SweepBudget(60)
    jobs = RepairCursor(client, b'synthetic-key' * 4, jobs=True)
    conversations = RepairCursor(client, b'synthetic-key' * 4)
    cursor = {'path': 'batch_pipeline_prod_jobs/private-segment', 'finished_at': stamp}
    jobs.write(cursor, budget)
    assert jobs.read(budget) == cursor
    assert conversations.read(budget) is None
    assert b'private-segment' not in jobs.ref.state['cursor']
    # A conversation cursor cannot be replayed into the jobs frontier.
    conversations.write({'path': 'users/synthetic/conversations/capture', 'finished_at': stamp}, budget)
    jobs.ref.state = conversations.ref.state
    with pytest.raises(ValueError):
        jobs.read(budget)


@pytest.mark.parametrize('mode', ['plan', 'apply'])
def test_both_discovery_legs_share_worker_budget_and_checkpoint_only_attempts(source, proof, monkeypatch, mode):
    from database import _client
    from utils.batch_pipeline import record_seal_sweeper
    from tests.unit.test_record_seal_cluster_repair import CursorClient

    class Client:
        def __init__(self):
            self.frontiers = {}
            self.jobs = JobsClient([job_doc(i) for i in range(6)])
            stamp = datetime.fromtimestamp(100, timezone.utc)
            self.conversations = CursorClient(
                [
                    SimpleNamespace(
                        reference=SimpleNamespace(path=f'users/synthetic/conversations/legacy-{i}'),
                        to_dict=lambda: {'finished_at': stamp},
                    )
                    for i in range(6)
                ]
            )

        def collection(self, name):
            if name == 'batch_pipeline_prod_jobs':
                return self.jobs.collection(name)
            assert name == 'batch_pipeline_prod_maintenance'
            return SimpleNamespace(document=lambda key: self.frontiers.setdefault(key, CursorClient()))

        def document(self, path):
            return SimpleNamespace(path=path) if path.startswith('users/') else path

        def collection_group(self, name):
            return self.conversations.collection_group(name)

    client = Client()
    original_discover = cluster.discover

    def bounded_discover(*args, **kwargs):
        assert kwargs['max_scan'] + 128 == cluster.MAX_SCAN
        return original_discover(*args, **kwargs)

    monkeypatch.setattr(cluster, 'discover', bounded_discover)
    monkeypatch.setattr(_client, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(record_seal_sweeper, 'read_pusher_pod_proof', proof)
    monkeypatch.setattr(config, 'require_runtime', lambda: None)
    monkeypatch.setattr(config, 'server_flags', lambda: SERVER)
    monkeypatch.setattr(config, 'settings', lambda: (4, 240, 1500, mode))
    attempts = []

    def work(rows, **kwargs):
        assert len(rows) <= cluster.MAX_ROWS
        attempted = [path for path, _ in rows[:4]]
        attempts.extend(attempted)
        for path in attempted:
            kwargs['attempted'](path)
        return {'rows': len(rows), 'dispositions': {'deferred': len(rows) - 4, 'proof_refused': 4}}

    monkeypatch.setattr(cluster, 'coordinate', work)
    for _ in range(3):
        assert cluster.run()['outcome'] == 'ok'
    job_attempts = [path for path in attempts if '/capture-' in path]
    conversation_attempts = [path for path in attempts if '/legacy-' in path]
    if mode == 'apply':
        assert len(set(job_attempts)) == len(set(conversation_attempts)) == 6
    else:
        assert len(set(job_attempts)) == len(set(conversation_attempts)) == 2
        assert all(frontier.writes == 0 for frontier in client.frontiers.values())


def test_blocker_log_metric_has_closed_labels_and_cloud_run_keep_coverage():
    from pathlib import Path
    import re
    import yaml

    backend = Path(__file__).resolve().parents[2]
    metrics = json.loads((backend / 'deploy/record-seal-repair/log-metrics.json').read_text())
    counter = next(metric for metric in metrics if metric['name'] == 'omi_record_seal_repair_blocker_outcomes')
    assert counter['metricDescriptor']['metricKind'] == 'DELTA'
    expression = counter['labelExtractors']['blocker']
    pattern = json.loads(expression.split(', ', 1)[1][:-1])
    for blocker in cluster.BLOCKERS:
        assert re.search(pattern, json.dumps({'blocker': blocker})).group(1) == blocker
    for private in ['private@example.invalid', 'users/private/conversations/private', 'A' * 28]:
        assert re.search(pattern, json.dumps({'blocker': private})) is None
    gmp = yaml.safe_load((backend / 'deploy/cloud_run_gmp_sidecar.yaml').read_text())
    keep = gmp['spec']['endpoints'][0]['metricRelabeling'][0]['regex']
    assert re.fullmatch(keep, counter['name'])


def test_no_initial_conversation_slots_preserve_unattempted_frontier():
    from tests.unit.test_record_seal_cluster_repair import CursorClient

    stamp = datetime.fromtimestamp(100, timezone.utc)
    docs = [
        SimpleNamespace(
            reference=SimpleNamespace(path=f'users/synthetic/conversations/{i}'), to_dict=lambda: {'finished_at': stamp}
        )
        for i in range(4)
    ]
    client = CursorClient(docs)
    after = {'path': docs[0].reference.path, 'finished_at': stamp}
    rows, _, cursor = cluster.discover(client, budget=SweepBudget(60), after=after, advance_rows=0)
    assert len(rows) == 3 and cursor == after


@pytest.mark.parametrize('state', ['record_pending', 'partial_retired'])
def test_jobs_switch_off_skips_aged_partial_and_transactional_retry(partial_source, monkeypatch, state):
    from database.record_partial import finish_partial

    row = age_partial(partial_source)
    segment = record_identity('synthetic', 'record')[1]
    partial_source[1].rows[('batch_pipeline_dev_jobs', segment)]['state'] = state
    monkeypatch.setenv('RECORD_SEAL_REPAIR_JOBS', 'off')
    before = deepcopy(partial_source[1].rows)
    assert cluster.settled(row)
    from tests.unit.test_record_seal_cluster_repair import CursorClient

    client = CursorClient([SimpleNamespace(reference=SimpleNamespace(path='/'.join(ROW)), to_dict=lambda: row)])
    assert cluster.discover(client, budget=SweepBudget(60))[0] == []
    inventory = Mock(side_effect=AssertionError('rollback must skip aged proof/retry'))
    assert (
        cluster.repair_one(
            partial_source[0],
            object(),
            object(),
            '/'.join(ROW),
            flags=FLAGS,
            inventory=inventory,
            budget=SweepBudget(240),
        )
        == 'already_partial'
    )
    inventory.assert_not_called()
    assert (
        finish_partial(
            partial_source[0],
            '/'.join(ROW),
            reason='tail_lagging',
            proof=partial_source[2],
            now=NOW,
            retry_aged=True,
        )
        == 'already_partial'
    )
    assert partial_source[1].rows == before


def test_jobs_switch_off_never_queries_jobs_leg(source, proof, monkeypatch):
    from database import _client
    from utils.batch_pipeline import record_seal_sweeper
    from tests.unit.test_record_seal_cluster_repair import CursorClient

    monkeypatch.setenv('RECORD_SEAL_REPAIR_JOBS', 'off')
    monkeypatch.setattr(_client, 'get_firestore_client', lambda: CursorClient())
    monkeypatch.setattr(record_seal_sweeper, 'read_pusher_pod_proof', proof)
    monkeypatch.setattr(config, 'require_runtime', lambda: None)
    monkeypatch.setattr(config, 'server_flags', lambda: SERVER)
    monkeypatch.setattr(config, 'settings', lambda: (4, 240, 1500, 'apply'))
    discover_jobs = Mock(side_effect=AssertionError('rollback must not query jobs leg'))
    monkeypatch.setattr(cluster, 'discover_jobs', discover_jobs)
    assert cluster.run()['outcome'] == 'ok'
    discover_jobs.assert_not_called()


def test_jobs_switch_off_during_proof_prevents_aged_partial_rearm(partial_source, monkeypatch):
    row = age_partial(partial_source)
    before = deepcopy(partial_source[1].rows)

    def inventory():
        monkeypatch.setenv('RECORD_SEAL_REPAIR_JOBS', 'off')
        return partial_source[2]

    assert (
        cluster.repair_one(
            partial_source[0],
            object(),
            object(),
            '/'.join(ROW),
            flags=FLAGS,
            inventory=inventory,
            budget=SweepBudget(240),
        )
        == 'already_partial'
    )
    assert partial_source[1].rows == before
    assert row['record_audio_partial'] and not row['record_audio_closed']


@pytest.mark.parametrize(
    'mode,expected', [('off', 'upload_pending'), ('shadow', 'upload_pending'), ('serve', 'sealed')]
)
def test_lease_expired_pending_runs_existing_full_proof_exit(source, proof, monkeypatch, mode, expected):
    assert settle(source, proof) == 'sealed_registered'
    row = source[1].rows[PATH]

    now = 10000
    monkeypatch.setattr(record_producer_proof.time, 'time', lambda: now)
    row.update(
        record_audio_closed=False,
        record_upload_sessions={
            's': {
                'pod': 'live',
                'process_started_at': 100,
                'last_signal_at': now - 7200,
                'lease_expires_at': now - 3600,
                'signal_source': 'frames',
            }
        },
    )
    value = {'namespace': 'prod-omi-backend', 'captured_at': now, 'resource_version': '1', 'pods': {'live': 1}}
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', mode)
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    assert settle(source, lambda: value) == expected
    assert bool(row['record_upload_sessions']) is (mode != 'serve')

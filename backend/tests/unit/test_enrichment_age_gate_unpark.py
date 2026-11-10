"""Synthetic operator unpark: dry-run purity, privacy CAS and durable enqueue debt."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from database.batch_pipeline_privacy import BatchPrivacyBlocked
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.enrichment import age_gate, outbox
from utils.enrichment import unpark

NOW = 10_000_000.0
UID = 'synthetic-owner'
CID = 'synthetic-conversation'
KEY = outbox.key(UID, CID)
ROW_PATH = (outbox.COLLECTION, KEY)
BINDING = {
    'queue': 'enrichment',
    'handler': 'https://worker.invalid/v2/enrichment/run',
    'audience': 'https://worker.invalid/v2/enrichment/run',
    'invoker_sa': 'synthetic@example.invalid',
}


def row():
    return {
        'document_id': KEY,
        'uid': UID,
        'conversation_id': CID,
        'language': 'en',
        'version': 7,
        'first_pending_at': NOW - 3600,
        'latest_pending_at': NOW - 3000,
        'first_summary_policy': {'policy_id': 'preserved'},
        'sync_hold': True,
        'age_gate_parked': True,
        'deferred_reason': age_gate.REASON,
        'deferred_since': NOW - 60,
        'dormant': True,
        'due_at': None,
        'task_due_at': None,
        'task_token': 'a' * 32,
        'lease_until': 0,
        'owner': None,
        'dispatch': dict(BINDING),
    }


@pytest.fixture
def source(monkeypatch):
    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', '72')
    monkeypatch.delenv('ENRICHMENT_AGE_GATE_UNPARK_ENABLED', raising=False)
    monkeypatch.setattr(unpark, 'assert_batch_write_allowed', lambda *args, **kwargs: 1)
    monkeypatch.setattr(unpark.time, 'time', lambda: NOW)
    client = StrictFirestore(
        {
            ('users', UID): {'private_cloud_sync_enabled': True},
            ('users', UID, 'conversations', CID): {'created_at': NOW - 3600, 'content': 'untouched'},
            ROW_PATH: row(),
        }
    )
    return client


def plan(client, document_ids=None):
    return unpark.plan_unpark(client, document_ids or [KEY], now=NOW, max_age_seconds=age_gate.max_age_seconds())


def apply(client, plan, wake=None):
    return unpark.apply_unpark(client, plan, plan['plan_sha256'], pace_seconds=0, wake=wake or Mock())


def no_writes(client):
    return all(not tx.updates and not tx.sets for tx in client.transactions)


def test_dry_run_counts_only_and_apply_preserves_debt_and_binding(source):
    result = plan(source)
    report = unpark.summary(result)
    assert report['dispositions'] == {'eligible': 1}
    assert no_writes(source)
    assert all(value not in json.dumps(report) for value in (UID, CID, KEY, 'a' * 32))
    wake = Mock()
    assert apply(source, result, wake) == {'unparked': 1}
    persisted = source.rows[ROW_PATH]
    assert persisted['age_gate_parked'] is False
    assert persisted['deferred_reason'] is None and 'deferred_since' not in persisted
    assert persisted['dormant'] is False
    assert persisted['due_at'] == persisted['task_due_at'] == NOW
    assert persisted['task_token'] != 'a' * 32
    assert persisted['first_pending_at'] == NOW - 3600
    assert persisted['version'] == 7 and persisted['sync_hold'] is True
    assert persisted['first_summary_policy'] == {'policy_id': 'preserved'}
    assert persisted['dispatch'] == BINDING
    assert source.rows[('users', UID, 'conversations', CID)]['content'] == 'untouched'
    assert wake.call_count == 1 and wake.call_args.args[0] == persisted
    writes = len([tx for tx in source.transactions if tx.sets])
    assert apply(source, result, wake) == {'state_changed': 1}
    assert wake.call_count == 1
    assert len([tx for tx in source.transactions if tx.sets]) == writes


@pytest.mark.parametrize(
    'change,reason',
    [
        ({'age_gate_parked': False}, 'not_parked'),
        ({'deferred_reason': 'other'}, 'not_parked'),
        ({'dormant': False}, 'not_parked'),
        ({'task_token': None}, 'not_parked'),
        ({'lease_until': NOW + 1}, 'leased'),
        ({'held_reason': 'document_size_limit'}, 'blocked'),
        ({'summary_blocked_reason': 'empty_output_exhausted'}, 'blocked'),
        ({'summary_seen': True}, 'blocked'),
        ({'dispatch': None}, 'unbound'),
        ({'first_pending_at': NOW - 73 * 3600}, 'outside_age_window'),
    ],
)
def test_unsafe_rows_have_no_write_or_wake_authority(source, change, reason):
    source.rows[ROW_PATH].update(change)
    result = plan(source)
    assert result['entries'][0]['disposition'] == reason
    assert 'task_token' not in result['entries'][0]
    assert apply(source, result) == {reason: 1}
    assert no_writes(source)


def test_old_conversation_is_refused_even_with_fresh_obligation(source):
    source.rows[('users', UID, 'conversations', CID)]['created_at'] = NOW - 73 * 3600
    result = plan(source)
    assert result['entries'][0]['disposition'] == 'outside_age_window'
    assert apply(source, result) == {'outside_age_window': 1}
    assert no_writes(source)


def test_zero_window_admits_otherwise_old_but_parked_debt(source, monkeypatch):
    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', '0')
    source.rows[ROW_PATH]['first_pending_at'] = NOW - 1000 * 3600
    result = plan(source)
    assert result['entries'][0]['disposition'] == 'eligible'
    assert apply(source, result) == {'unparked': 1}


def test_stale_token_and_changed_window_refuse_before_writes(source, monkeypatch):
    result = plan(source)
    source.rows[ROW_PATH]['task_token'] = 'b' * 32
    assert apply(source, result) == {'state_changed': 1}
    assert no_writes(source)
    fresh = plan(source)
    monkeypatch.setattr(age_gate, 'max_age_seconds', lambda: 1.0)
    with pytest.raises(ValueError, match='age window'):
        apply(source, fresh)
    assert no_writes(source)


def test_privacy_change_before_apply_prevents_unpark(source, monkeypatch):
    result = plan(source)
    monkeypatch.setattr(unpark, 'assert_batch_write_allowed', Mock(side_effect=BatchPrivacyBlocked('account_deleted')))
    assert apply(source, result) == {'privacy_refused': 1}
    assert no_writes(source)


def test_enqueue_failure_leaves_due_debt_and_is_not_retried_by_stale_plan(source):
    result = plan(source)
    wake = Mock(side_effect=RuntimeError('lost acknowledgement'))
    assert apply(source, result, wake) == {'enqueue_error': 1}
    persisted = source.rows[ROW_PATH]
    assert persisted['dormant'] is False and persisted['due_at'] == NOW
    assert apply(source, result, Mock()) == {'state_changed': 1}
    assert wake.call_count == 1


def test_pacing_sleeps_once_between_two_eligible_rows(source, monkeypatch):
    second_uid, second_cid = 'synthetic-owner-2', 'synthetic-conversation-2'
    second_key = outbox.key(second_uid, second_cid)
    second = row()
    second.update(document_id=second_key, uid=second_uid, conversation_id=second_cid, task_token='b' * 32)
    source.rows[(outbox.COLLECTION, second_key)] = second
    source.rows[('users', second_uid)] = {'private_cloud_sync_enabled': True}
    source.rows[('users', second_uid, 'conversations', second_cid)] = {'created_at': NOW - 3600}
    sleeps = []
    monkeypatch.setattr(unpark.time, 'sleep', lambda seconds: sleeps.append(seconds))
    result = unpark.plan_unpark(source, [KEY, second_key], now=NOW, max_age_seconds=age_gate.max_age_seconds())
    assert unpark.apply_unpark(source, result, result['plan_sha256'], pace_seconds=2.5, wake=Mock()) == {'unparked': 2}
    assert sleeps == [2.5]


def test_bad_approval_and_kill_switch_refuse_before_writes(source, monkeypatch):
    result = plan(source)
    with pytest.raises(ValueError, match='approval'):
        unpark.apply_unpark(source, result, '0' * 64, pace_seconds=0)
    assert no_writes(source)
    monkeypatch.setenv('ENRICHMENT_AGE_GATE_UNPARK_ENABLED', 'false')
    with pytest.raises(ValueError, match='disabled'):
        apply(source, result)
    assert no_writes(source)


def test_discovery_newest_first_shape_and_private_cursor_contract():
    client, query = Mock(), Mock()
    client.collection.return_value = query
    for method in ('where', 'order_by', 'select', 'limit', 'start_after'):
        getattr(query, method).return_value = query
    snapshot = SimpleNamespace(
        id=KEY,
        reference=SimpleNamespace(path=f'{outbox.COLLECTION}/{KEY}'),
        to_dict=lambda: {'deferred_since': NOW},
    )
    query.stream.return_value = [snapshot]
    cursor = {'deferred_since': NOW + 1, 'path': f'{outbox.COLLECTION}/{KEY}'}
    assert unpark.discover(client, after=cursor) == (
        [KEY],
        {'deferred_since': NOW, 'path': f'{outbox.COLLECTION}/{KEY}'},
    )
    query.order_by.assert_any_call('deferred_since', direction='DESCENDING')
    query.order_by.assert_any_call('__name__', direction='DESCENDING')
    query.select.assert_called_once_with(['deferred_since'])
    query.start_after.assert_called_once_with({'deferred_since': NOW + 1, '__name__': client.document.return_value})
    query.stream.return_value = []
    assert unpark.discover(client, after=cursor) == ([], None)
    for limit in (0, 129, True):
        with pytest.raises(ValueError):
            unpark.discover(client, limit=limit)
    for invalid in ({'path': f'users/{UID}'}, {'deferred_since': True, 'path': cursor['path']}, []):
        with pytest.raises(ValueError):
            unpark.discover(client, after=invalid)


def cli():
    path = Path(__file__).resolve().parents[2] / 'scripts' / 'unpark_enrichment_age_gate.py'
    spec = importlib.util.spec_from_file_location('unpark_age_gate_cli', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    'tier,apply_mode,allowed',
    [
        ('ro-prod', False, True),
        ('prod-operator', False, True),
        ('ro-prod', True, False),
        ('prod-operator', True, True),
        ('ro-dev', False, False),
    ],
)
def test_cli_tiers_before_client_access(monkeypatch, tier, apply_mode, allowed):
    monkeypatch.setenv('GCP_AGENT_TIER', tier)
    monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    monkeypatch.delenv('SERVICE_ACCOUNT_JSON', raising=False)
    monkeypatch.delenv('ENRICHMENT_AGE_GATE_UNPARK_ENABLED', raising=False)
    reached = Mock(side_effect=RuntimeError('stop before network'))
    module = cli()
    monkeypatch.setattr(module, 'get_firestore_client', reached)
    args = ['--next-file', '/unused'] + (['--apply', '--approve-plan-sha256', 'digest'] if apply_mode else [])
    with pytest.raises(RuntimeError if allowed else SystemExit):
        module.main(args)
    assert reached.called is allowed


def test_cli_disabled_apply_never_reads_cursor_or_client(monkeypatch):
    monkeypatch.setenv('GCP_AGENT_TIER', 'prod-operator')
    monkeypatch.setenv('ENRICHMENT_AGE_GATE_UNPARK_ENABLED', 'false')
    monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    monkeypatch.delenv('SERVICE_ACCOUNT_JSON', raising=False)
    reached = Mock()
    module = cli()
    monkeypatch.setattr(module, 'get_firestore_client', reached)
    with pytest.raises(SystemExit):
        module.main(
            ['--next-file', '/unused', '--after-file', '/private/input', '--apply', '--approve-plan-sha256', 'x']
        )
    reached.assert_not_called()


def test_cli_dry_run_outputs_only_counts_digest_and_checkpoint(source, monkeypatch, capsys):
    module = cli()
    monkeypatch.setenv('GCP_AGENT_TIER', 'ro-prod')
    monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    monkeypatch.delenv('SERVICE_ACCOUNT_JSON', raising=False)
    monkeypatch.setattr(module, 'get_firestore_client', lambda: source)
    cursor = {'deferred_since': NOW, 'path': f'{outbox.COLLECTION}/{KEY}'}
    monkeypatch.setattr(module, 'discover', lambda *args, **kwargs: ([KEY], cursor))
    write = Mock()
    monkeypatch.setattr(module, 'write_cursor', write)
    module.main(['--next-file', '/private/cursor'])
    output = capsys.readouterr()
    report = json.loads(output.out)
    assert report['dispositions'] == {'eligible': 1} and report['apply'] is False
    assert set(report) == {'operation', 'plan_sha256', 'count', 'dispositions', 'apply'}
    assert all(value not in output.out + output.err for value in (UID, CID, KEY, '/private', 'a' * 32))
    write.assert_called_once_with('/private/cursor', cursor)
    assert no_writes(source)


def test_cli_invalid_arguments_do_not_echo_sensitive_values(capsys):
    with pytest.raises(SystemExit):
        cli().main(['--limit', 'synthetic-private-path'])
    output = capsys.readouterr()
    assert json.loads(output.out)['outcome'] == 'invalid_arguments'
    assert 'synthetic-private-path' not in output.out + output.err


def test_private_cursor_permissions_and_rejects_public_directory(tmp_path, monkeypatch):
    module = cli()
    real_resolve = Path.resolve

    def resolve(path, *args, **kwargs):
        return tmp_path if str(path) == '/Volumes/Ephemeral/scratch' else real_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'resolve', resolve)
    directory = tmp_path / 'private'
    directory.mkdir(mode=0o700)
    path = directory / 'cursor.json'
    module.write_cursor(path, None)
    assert path.stat().st_mode & 0o777 == 0o600
    assert json.loads(path.read_text()) == {'after': None}
    directory.chmod(0o755)
    with pytest.raises(ValueError):
        module.write_cursor(path, None)

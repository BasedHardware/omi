"""Synthetic operator unpark: dry-run purity, privacy CAS and durable enqueue debt."""

import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from google.api_core.exceptions import FailedPrecondition
import pytest

from database import batch_pipeline_privacy
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.enrichment import age_gate, outbox
from utils.enrichment import unpark

NOW = 10_000_000.0
UID = 'synthetic-owner'
CID = 'synthetic-conversation'
KEY = outbox.key(UID, CID)
ROW_PATH = (outbox.COLLECTION, KEY)
CONVERSATION_PATH = ('users', UID, 'conversations', CID)
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
    monkeypatch.setattr(unpark, 'time', SimpleNamespace(time=lambda: NOW, sleep=unpark.time.sleep))
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


def test_dry_run_does_not_schedule_privacy_token_mint(source, monkeypatch):
    authorize = batch_pipeline_privacy.assert_batch_write_allowed
    monkeypatch.setattr(unpark, 'assert_batch_write_allowed', authorize)
    memo_levers = {'bpp_generation_memo', 'bpp_decision_cache', 'bpp_token_mint'}
    monkeypatch.setattr(batch_pipeline_privacy, 'lever_enabled', lambda name, _uid: name in memo_levers)
    monkeypatch.setattr(batch_pipeline_privacy, 'ttl_enabled', lambda name, _uid: name == 'bpp_decision_cache')
    mint = Mock()
    monkeypatch.setattr(batch_pipeline_privacy, 'schedule_token_mint', mint)
    assert plan(source)['entries'][0]['disposition'] == 'eligible'
    mint.assert_not_called()
    assert no_writes(source)

    @unpark.firestore.transactional
    def default_privacy_check(transaction):
        return authorize(source, transaction, UID, conversation_ids=[CID])

    default_privacy_check(source.transaction())
    mint.assert_called_once()


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
        ({'uid': 'synthetic-other'}, 'identity_changed'),
        (None, 'identity_changed'),
        ({'first_pending_at': NOW - 73 * 3600}, 'outside_age_window'),
    ],
)
def test_unsafe_rows_have_no_write_or_wake_authority(source, change, reason):
    if change is None:
        del source.rows[ROW_PATH]
    else:
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


def test_conversation_only_summary_block_refuses_dry_run_and_approved_apply(source):
    approved = plan(source)
    assert unpark.summary(approved)['dispositions'] == {'eligible': 1}
    source.rows[CONVERSATION_PATH]['summary_blocked_reason'] = 'local_only'
    assert unpark.summary(plan(source))['dispositions'] == {'blocked': 1}
    wake = Mock()
    assert apply(source, approved, wake) == {'blocked': 1}
    wake.assert_not_called()
    assert no_writes(source)


def test_unknown_age_is_refused_with_a_bounded_window(source, monkeypatch):
    approved = plan(source)
    del source.rows[ROW_PATH]['first_pending_at']
    del source.rows[CONVERSATION_PATH]['created_at']
    assert unpark.summary(plan(source))['dispositions'] == {'outside_age_window': 1}
    wake = Mock()
    assert apply(source, approved, wake) == {'outside_age_window': 1}
    wake.assert_not_called()
    assert no_writes(source)
    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', '0')
    assert unpark.summary(plan(source))['dispositions'] == {'eligible': 1}


def test_per_row_read_and_write_errors_are_counted_without_waking(source, monkeypatch):
    approved = plan(source)
    missing_key = outbox.key(UID, 'missing')
    monkeypatch.setattr(unpark, 'assert_batch_write_allowed', Mock(side_effect=RuntimeError('synthetic failure')))
    result = plan(source, [KEY, missing_key])
    assert unpark.summary(result)['dispositions'] == {'read_error': 1, 'identity_changed': 1}
    wake = Mock()
    assert apply(source, approved, wake) == {'write_error': 1}
    wake.assert_not_called()
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


@pytest.fixture
def operator_cli(monkeypatch, tmp_path):
    # Register environment changes that main() makes directly.
    for key in ('OMI_ENV_STAGE', 'ENRICHMENT_MAX_AGE_HOURS'):
        monkeypatch.setenv(key, os.environ.get(key, ''))
    module = cli()
    monkeypatch.setattr(module, 'SCRATCH', tmp_path)
    monkeypatch.setattr(module, 'time', SimpleNamespace(time=lambda: unpark.time.time()))
    tmp_path.chmod(0o700)
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
def test_cli_tiers_before_client_access(monkeypatch, tier, apply_mode, allowed, operator_cli):
    monkeypatch.setenv('GCP_AGENT_TIER', tier)
    monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    monkeypatch.delenv('SERVICE_ACCOUNT_JSON', raising=False)
    monkeypatch.delenv('ENRICHMENT_AGE_GATE_UNPARK_ENABLED', raising=False)
    reached = Mock(side_effect=RuntimeError('stop before network'))
    module = operator_cli
    monkeypatch.setattr(module.firestore, 'Client', reached)
    args = ['--next-file', str(module.SCRATCH / 'cursor.json'), '--serving-max-age-hours', '72']
    if apply_mode:
        args += ['--apply', '--approve-plan-sha256', 'a' * 64]
    with pytest.raises(RuntimeError if allowed else SystemExit):
        module.main(args)
    assert reached.called is allowed


def test_cli_disabled_apply_never_reads_cursor_or_client(monkeypatch, capsys):
    monkeypatch.setenv('GCP_AGENT_TIER', 'prod-operator')
    monkeypatch.setenv('ENRICHMENT_AGE_GATE_UNPARK_ENABLED', 'false')
    monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    monkeypatch.delenv('SERVICE_ACCOUNT_JSON', raising=False)
    reached = Mock()
    module = cli()
    monkeypatch.setattr(module.firestore, 'Client', reached)
    with pytest.raises(SystemExit):
        module.main(
            [
                '--next-file',
                '/unused',
                '--after-file',
                '/private/input',
                '--serving-max-age-hours',
                '72',
                '--apply',
                '--approve-plan-sha256',
                'a' * 64,
            ]
        )
    reached.assert_not_called()
    assert json.loads(capsys.readouterr().out)['reason'] == 'apply_disabled'


def test_cli_dry_run_outputs_only_counts_digest_and_checkpoint(source, monkeypatch, capsys, operator_cli):
    module = operator_cli
    monkeypatch.setenv('GCP_AGENT_TIER', 'ro-prod')
    monkeypatch.setenv('ENRICHMENT_AGE_GATE_UNPARK_ENABLED', 'false')
    monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    monkeypatch.delenv('SERVICE_ACCOUNT_JSON', raising=False)
    client = Mock(return_value=source)
    monkeypatch.setattr(module.firestore, 'Client', client)
    cursor = {'deferred_since': NOW, 'path': f'{outbox.COLLECTION}/{KEY}'}
    monkeypatch.setattr(module, 'discover', lambda *args, **kwargs: ([KEY], cursor))
    write = Mock()
    monkeypatch.setattr(module, 'write_cursor', write)
    next_file = str(module.SCRATCH / 'cursor.json')
    module.main(['--next-file', next_file, '--serving-max-age-hours', '84'])
    output = capsys.readouterr()
    report = json.loads(output.out)
    assert report['dispositions'] == {'eligible': 1} and report['apply'] is False
    assert report['rows_scanned'] == report['count'] == 1
    assert report['project'] == 'based-hardware' and report['serving_max_age_hours'] == 84
    assert set(report) == {
        'operation',
        'plan_sha256',
        'count',
        'rows_scanned',
        'dispositions',
        'apply',
        'project',
        'serving_max_age_hours',
    }
    assert all(value not in output.out + output.err for value in (UID, CID, KEY, next_file, 'a' * 32))
    client.assert_called_once_with(project='based-hardware')
    write.assert_called_once_with(next_file, cursor, scratch_root=None)
    assert no_writes(source)


@pytest.mark.parametrize('effects_only', [False, True])
def test_cli_apply_uses_approved_plan_and_persisted_binding(source, monkeypatch, capsys, effects_only, operator_cli):
    from utils import cloud_tasks

    module = operator_cli
    monkeypatch.setenv('GCP_AGENT_TIER', 'prod-operator')
    monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    monkeypatch.delenv('SERVICE_ACCOUNT_JSON', raising=False)
    monkeypatch.delenv('ENRICHMENT_AGE_GATE_UNPARK_ENABLED', raising=False)
    monkeypatch.setenv('SYNC_TASKS_PROJECT', 'based-hardware-dev')
    monkeypatch.delenv('SYNC_TASKS_LOCATION', raising=False)
    monkeypatch.setenv('DEMAND_PROCESSING_ENABLED', 'true')
    document_id = KEY
    dispatch = BINDING
    if effects_only:
        document_id = outbox.key(UID, CID + '\0effects')
        handler = 'https://worker.invalid/v1/conversation-finalization-jobs/run'
        dispatch = {**BINDING, 'handler': handler, 'audience': 'https://worker.invalid'}
        source.rows[(outbox.COLLECTION, document_id)] = {
            **source.rows.pop(ROW_PATH),
            'document_id': document_id,
            'effects_only': True,
            'dispatch': dispatch,
        }
    row_path = (outbox.COLLECTION, document_id)
    monkeypatch.setattr(module.firestore, 'Client', Mock(return_value=source))

    def discover_parked(*args, **kwargs):
        return ([document_id] if source.rows[row_path]['age_gate_parked'] else []), None

    monkeypatch.setattr(module, 'discover', discover_parked)
    checkpoint = Mock()
    monkeypatch.setattr(module, 'write_cursor', checkpoint)

    def check_task_target(*args, **kwargs):
        assert os.environ['SYNC_TASKS_PROJECT'] == 'based-hardware'
        assert os.environ['SYNC_TASKS_LOCATION'] == 'us-central1'

    enqueue = Mock(side_effect=check_task_target)
    monkeypatch.setattr(cloud_tasks, 'enqueue_named_task', enqueue)
    args = ['--next-file', str(module.SCRATCH / 'cursor.json'), '--serving-max-age-hours', '72']
    module.main(args)
    digest = json.loads(capsys.readouterr().out)['plan_sha256']
    assert no_writes(source)
    # The approved digest also pins the confirmed serving window.
    checkpoint.reset_mock()
    approve = ['--apply', '--approve-plan-sha256', digest]
    module.main(args[:-1] + ['73'] + approve)
    assert json.loads(capsys.readouterr().out)['outcome'] == 'plan_changed'
    assert no_writes(source)
    checkpoint.assert_not_called()
    enqueue.assert_not_called()

    # The apply runs on a later clock than the dry-run; the approved digest must survive it.
    monkeypatch.setattr(unpark.time, 'time', lambda: NOW + 600)
    apply_args = args + approve
    module.main(apply_args)
    report = json.loads(capsys.readouterr().out)
    assert report['apply'] is True and report['outcomes'] == {'unparked': 1}
    persisted = source.rows[row_path]
    assert persisted['age_gate_parked'] is False
    assert persisted['due_at'] == NOW + 600
    enqueue.assert_called_once()
    queue, handler, _, payload = enqueue.call_args.args
    assert (queue, handler) == (dispatch['queue'], dispatch['handler'])
    assert enqueue.call_args.kwargs['audience'] == dispatch['audience']
    assert payload == {'kind': 'sync_reprocess', 'key': document_id, 'task_token': persisted['task_token']}

    checkpoint.reset_mock()
    module.main(apply_args)
    report = json.loads(capsys.readouterr().out)
    assert report['outcome'] == 'plan_changed'
    assert report['count'] == 0 and 'plan_sha256' not in report
    checkpoint.assert_not_called()
    enqueue.assert_called_once()
    assert sum(bool(tx.sets) for tx in source.transactions) == 1


def test_cli_invalid_arguments_do_not_echo_sensitive_values(capsys):
    with pytest.raises(SystemExit):
        cli().main(['--limit', 'synthetic-private-path'])
    output = capsys.readouterr()
    assert json.loads(output.out)['outcome'] == 'invalid_arguments'
    assert 'synthetic-private-path' not in output.out + output.err


def test_cli_rejects_public_checkpoint_before_client_access(monkeypatch, capsys, operator_cli):
    monkeypatch.setenv('GCP_AGENT_TIER', 'ro-prod')
    monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    monkeypatch.delenv('SERVICE_ACCOUNT_JSON', raising=False)
    public = operator_cli.SCRATCH / 'public'
    public.mkdir()
    public.chmod(0o755)
    client = Mock()
    monkeypatch.setattr(operator_cli.firestore, 'Client', client)
    with pytest.raises(SystemExit) as error:
        operator_cli.main(['--next-file', str(public / 'cursor.json'), '--serving-max-age-hours', '72'])
    assert error.value.code == 2
    assert json.loads(capsys.readouterr().out)['reason'] == 'cursor_path'
    client.assert_not_called()


@pytest.mark.parametrize('custom_root', [False, True])
def test_cli_passes_private_checkpoint_back_to_discovery(monkeypatch, capsys, operator_cli, tmp_path, custom_root):
    monkeypatch.setenv('GCP_AGENT_TIER', 'ro-prod')
    monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    monkeypatch.delenv('SERVICE_ACCOUNT_JSON', raising=False)
    client, query = Mock(), Mock()
    client.collection.return_value = query
    for method in ('where', 'order_by', 'select', 'limit', 'start_after'):
        getattr(query, method).return_value = query
    path = f'{outbox.COLLECTION}/{KEY}'
    page = Mock(id=KEY, reference=SimpleNamespace(path=path))
    page.to_dict.return_value = {'deferred_since': NOW}
    query.stream.side_effect = [[page], []]
    monkeypatch.setattr(operator_cli.firestore, 'Client', Mock(return_value=client))
    monkeypatch.setattr(unpark, 'prepare', Mock(return_value=('blocked', None)))
    args = ['--serving-max-age-hours', '72', '--limit', '1']
    scratch = operator_cli.SCRATCH
    if custom_root:
        operator_cli.SCRATCH = tmp_path / 'absent-default'
        scratch = tmp_path / 'alternate'
        scratch.mkdir(mode=0o700)
        args += ['--scratch-root', str(scratch)]
    first = scratch / 'first.json'
    second = scratch / 'second.json'

    operator_cli.main(args + ['--next-file', str(first)])
    report = json.loads(capsys.readouterr().out)
    assert report['count'] == report['rows_scanned'] == 1
    assert json.loads(first.read_text()) == {'after': {'deferred_since': NOW, 'path': path}}
    assert first.stat().st_mode & 0o777 == 0o600
    query.start_after.assert_not_called()

    operator_cli.main(args + ['--after-file', str(first), '--next-file', str(second)])
    report = json.loads(capsys.readouterr().out)
    assert report['count'] == report['rows_scanned'] == 0
    client.document.assert_called_once_with(path)
    query.start_after.assert_called_once_with({'deferred_since': NOW, '__name__': client.document.return_value})
    assert json.loads(second.read_text()) == {'after': None}


@pytest.mark.parametrize('unsafe_path', ['public_root', 'different_owner', 'symlink_escape'])
def test_cli_rejects_unsafe_custom_scratch_before_client_access(
    monkeypatch, capsys, operator_cli, tmp_path, unsafe_path
):
    monkeypatch.setenv('GCP_AGENT_TIER', 'ro-prod')
    monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    monkeypatch.delenv('SERVICE_ACCOUNT_JSON', raising=False)
    root = tmp_path / 'alternate'
    root.mkdir(mode=0o700)
    child = root / 'checkpoint'
    if unsafe_path == 'symlink_escape':
        outside = tmp_path / 'outside'
        outside.mkdir(mode=0o700)
        child.symlink_to(outside, target_is_directory=True)
    else:
        child.mkdir(mode=0o700)
        if unsafe_path == 'public_root':
            root.chmod(0o755)
        else:
            other_owner = root.stat().st_uid + 1
            monkeypatch.setattr(operator_cli.os, 'geteuid', lambda: other_owner)
    client = Mock()
    monkeypatch.setattr(operator_cli.firestore, 'Client', client)
    with pytest.raises(SystemExit) as error:
        operator_cli.main(
            ['--scratch-root', str(root), '--next-file', str(child / 'next.json'), '--serving-max-age-hours', '72']
        )
    assert error.value.code == 2
    assert json.loads(capsys.readouterr().out)['reason'] == 'cursor_path'
    client.assert_not_called()


def test_cli_error_reports_type_without_exception_message(monkeypatch, capsys, operator_cli):
    monkeypatch.setattr(operator_cli, 'main', Mock(side_effect=FailedPrecondition('sensitive details')))
    assert operator_cli.run_cli() == 1
    output = capsys.readouterr()
    assert json.loads(output.out) == {'operation': unpark.OPERATION, 'outcome': 'error', 'error': 'FailedPrecondition'}
    assert 'sensitive details' not in output.out + output.err


def test_private_cursor_permissions_and_rejects_public_directory(tmp_path, monkeypatch):
    module = cli()
    monkeypatch.setattr(module, 'SCRATCH', tmp_path)
    directory = tmp_path / 'private'
    directory.mkdir(mode=0o700)
    path = directory / 'cursor.json'
    module.write_cursor(path, None)
    assert path.stat().st_mode & 0o777 == 0o600
    assert json.loads(path.read_text()) == {'after': None}
    directory.chmod(0o755)
    with pytest.raises(ValueError):
        module.write_cursor(path, None)

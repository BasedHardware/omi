import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scripts import settle_parked_conversations as runner


@pytest.mark.parametrize('scope_args', [[], ['--scope', 'discard-deletion']])
def test_cli_defaults_to_discard_deletion(tmp_path, monkeypatch, scope_args):
    checkpoint = tmp_path / 'operator' / 'dry-run.json'
    monkeypatch.setenv('GCP_AGENT_TIER', 'ro-prod')
    monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    monkeypatch.setattr(
        runner.sys,
        'argv',
        ['runner', 'dry-run', '--cutoff', '2020-01-01T00:00:00Z', '--checkpoint', str(checkpoint), *scope_args],
    )
    monkeypatch.setattr(runner.firestore, 'Client', Mock())
    monkeypatch.setattr(runner, 'run_pass', Mock(return_value='exhausted'))
    approval = Mock()
    monkeypatch.setattr(runner.subprocess, 'run', approval)

    assert runner.main() == 0
    assert json.loads(checkpoint.read_text())['scope'] == 'discard-deletion'
    approval.assert_not_called()


@pytest.mark.parametrize('scope_args', [['--scope', 'all'], ['--scope', 'all', '--approval-ref', 'not-a-comment']])
def test_all_without_verified_release_approval_refuses_before_checkpoint(tmp_path, monkeypatch, capsys, scope_args):
    checkpoint = tmp_path / 'operator' / 'canary.json'
    monkeypatch.setenv('GCP_AGENT_TIER', 'prod-operator')
    monkeypatch.setenv('CONVERSATION_PARKED_TERMINAL_STATUS_ENABLED', 'on')
    monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    monkeypatch.setattr(
        runner.sys,
        'argv',
        ['runner', 'canary', '--cutoff', '2020-01-01T00:00:00Z', '--checkpoint', str(checkpoint), *scope_args],
    )
    firestore = Mock()
    monkeypatch.setattr(runner.firestore, 'Client', firestore)

    with pytest.raises(SystemExit, match='2'):
        runner.main()
    assert 'requires a verified Release --approval-ref' in capsys.readouterr().err
    assert not checkpoint.parent.exists()
    firestore.assert_not_called()


def test_all_approval_binds_release_author_phase_cutoff_and_day(monkeypatch):
    reference = '00000000-0000-4000-8000-000000000001'
    now = datetime(2026, 11, 24, 7, tzinfo=timezone.utc)
    cutoff = now - timedelta(hours=7)
    approval = {
        'id': reference,
        'issue_id': runner.RELEASE_ISSUE,
        'author_id': runner.RELEASE_OWNER,
        'author_type': 'agent',
        'content': 'PARKED-ALL-APPROVED: canary 2026-11-24T00:00:00+00:00 2026-11-24',
    }
    read = Mock(side_effect=lambda *args, **kwargs: SimpleNamespace(stdout=json.dumps([approval])))
    monkeypatch.setattr(runner.subprocess, 'run', read)

    assert runner._check_all_approval(reference, 'canary', cutoff, now)
    assert runner.RELEASE_ISSUE in read.call_args.args[0]
    assert not runner._check_all_approval(reference, 'apply', cutoff, now)
    assert not runner._check_all_approval(reference, 'canary', cutoff - timedelta(hours=1), now)
    assert not runner._check_all_approval(reference, 'canary', cutoff, now + timedelta(days=1))
    approval['issue_id'] = 'another-issue'
    assert not runner._check_all_approval(reference, 'canary', cutoff, now)
    approval['issue_id'] = runner.RELEASE_ISSUE
    approval['author_id'] = 'untrusted'
    assert not runner._check_all_approval(reference, 'canary', cutoff, now)
    read.side_effect = OSError('tracker unavailable')
    assert not runner._check_all_approval(reference, 'canary', cutoff, now)


def test_canary_resumes_from_scan_cap_with_one_cumulative_write_cap(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=6)
    state = runner._initial_state(SimpleNamespace(phase='canary', cutoff=cutoff, scope='all'), now)
    checkpoint = tmp_path / 'canary.json'
    candidate = Mock()
    candidate.reference.path = 'users/test/conversations/test'
    candidate.get.return_value = cutoff
    transaction = Mock()
    client = Mock()
    client.transaction.return_value = transaction
    settle = Mock(side_effect=[['deferred', 'other_owner'], ['other_owner'], ['deferred']])
    page = Mock(side_effect=[[candidate, candidate], [candidate], [candidate]])

    monkeypatch.setattr(runner, 'CANARY_SIZE', 2)
    monkeypatch.setattr(runner, 'MAX_BATCH_WRITES', 2)
    monkeypatch.setattr(runner, '_page', page)
    monkeypatch.setattr(runner, '_validate_canary', Mock())
    monkeypatch.setattr(runner.parked, 'classify', Mock(return_value='deferred'))
    monkeypatch.setattr(runner.firestore, 'transactional', lambda _: settle)

    assert runner.run_pass(client, checkpoint, state, 'canary') == 'canary_scan_cap'
    state = json.loads(checkpoint.read_text())
    assert state['counts']['written'] == 1
    assert runner._can_resume(state, 'canary', cutoff, 'all')
    assert not runner._can_resume(state, 'apply', cutoff, 'all')

    assert runner.run_pass(client, checkpoint, state, 'canary') == 'canary_paused'
    assert [call.args[2] for call in page.call_args_list] == [2, 1, 1]
    assert state['counts']['written'] == 2
    assert state['scanned'] == 4


def test_resume_refuses_a_canary_with_unreconciled_writes():
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=6)
    state = runner._initial_state(SimpleNamespace(phase='canary', cutoff=cutoff, scope='all'), now)
    state['unfinished_transaction'] = True

    assert not runner._can_resume(state, 'canary', cutoff, 'all')
    assert not runner._can_resume(state, 'apply', cutoff, 'all')


def test_verified_discard_deletion_checkpoint_cannot_authorize_all_scope():
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=6)
    scope = runner.DISCARD_DELETION_SCOPE
    state = runner._initial_state(SimpleNamespace(phase='canary', cutoff=cutoff, scope=scope), now)
    state['canary_verified'] = True

    assert runner._can_resume(state, 'apply', cutoff, scope)
    assert not runner._can_resume(state, 'apply', cutoff, 'all')
    del state['scope']
    assert not runner._can_resume(state, 'apply', cutoff, scope)
    assert not runner._can_resume(state, 'apply', cutoff, 'all')


def test_narrow_scan_does_not_join_custody_for_a_deferred_row(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=6)
    args = SimpleNamespace(phase='canary', cutoff=cutoff, scope=runner.DISCARD_DELETION_SCOPE)
    state = runner._initial_state(args, now)
    snapshot = Mock()
    snapshot.reference.path = 'users/test/conversations/test'
    snapshot.to_dict.return_value = {'status': 'processing', 'deleted': True, 'deferred': True}
    snapshot.get.return_value = cutoff
    monkeypatch.setattr(runner, '_page', Mock(return_value=[snapshot]))
    client = Mock()

    assert runner.run_pass(client, tmp_path / 'canary.json', state, 'canary') == 'exhausted'
    assert state['counts'] == {'deferred_excluded': 1}
    client.transaction.assert_not_called()

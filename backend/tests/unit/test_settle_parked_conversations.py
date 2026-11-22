import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from scripts import settle_parked_conversations as runner


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

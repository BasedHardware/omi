"""The replay must execute new result writes without weakening transaction rules."""

from copy import deepcopy

import pytest

from testing.batch_replay.gate import adapter_digest
from testing.batch_replay.runner import ResultTransactionLog, fixed_transaction_fixture


class BaseLog:
    def ref(self, table, sid):
        return ('nontransactional', table, sid)


class Log(ResultTransactionLog, BaseLog):
    def __init__(self):
        self.results = {'synthetic-head': {'projection_state': 'pending', 'retained': True}}


def test_first_failure_stamp_persists_and_later_attempt_keeps_it():
    log = Log()

    def stamp(transaction):
        ref = log.ref('results', 'synthetic-head')
        row = ref.get(transaction=transaction).to_dict()
        if row.get('projection_blocked_since') is not None:
            return False
        transaction.update(ref, {'projection_blocked_since': 17.0, 'projection_block_type': 'TimeoutError'})
        return True

    assert log.run(stamp) is True
    assert log.run(stamp) is False
    assert log.results['synthetic-head'] == {
        'projection_state': 'pending',
        'retained': True,
        'projection_blocked_since': 17.0,
        'projection_block_type': 'TimeoutError',
    }
    assert log.ref('results', 'synthetic-head') == ('nontransactional', 'results', 'synthetic-head')


@pytest.mark.parametrize('failure', ['callback', 'read_after_write', 'outside_results'])
def test_failed_callback_never_publishes_partial_result_mutations(failure):
    log = Log()
    before = deepcopy(log.results)

    def operation(transaction):
        ref = log.ref('results', 'synthetic-head')
        ref.get(transaction=transaction)
        transaction.update(ref, {'projection_blocked_since': 17.0})
        if failure == 'callback':
            raise ValueError('synthetic callback failure')
        if failure == 'read_after_write':
            ref.get(transaction=transaction)
        log.ref('jobs', 'synthetic-head')

    expected = {
        'callback': ValueError,
        'read_after_write': fixed_transaction_fixture().ReadAfterWriteError,
        'outside_results': NotImplementedError,
    }
    with pytest.raises(expected[failure]):
        log.run(operation)
    assert log.results == before
    assert log.ref('results', 'synthetic-head') == ('nontransactional', 'results', 'synthetic-head')


def test_selected_snapshot_fixture_is_not_transaction_authority(monkeypatch):
    from tests.unit.fixtures import strict_firestore_transaction as selected_fixture

    def refuse_selected_fixture(*args, **kwargs):
        raise AssertionError('selected snapshot must not supply fixed replay transaction rules')

    monkeypatch.setattr(selected_fixture, 'StrictFirestore', refuse_selected_fixture)
    log = Log()
    assert log.run(lambda transaction: transaction.update(log.ref('results', 'synthetic-head'), {'stamp': 17})) is None
    assert log.results['synthetic-head']['stamp'] == 17


def test_fixed_transaction_fixture_changes_adapter_identity(tmp_path):
    files = [tmp_path / name for name in ('gate', 'runner', 'incidents', 'transaction_fixture')]
    for path in files:
        path.write_bytes(path.name.encode())
    before = adapter_digest(*files)
    files[-1].write_bytes(b'changed transaction semantics')
    assert adapter_digest(*files) != before

"""The replay must execute new result writes without weakening transaction rules."""

from copy import deepcopy

import pytest

from testing.batch_replay.runner import ResultTransactionLog
from tests.unit.fixtures.strict_firestore_transaction import ReadAfterWriteError


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

    expected = {'callback': ValueError, 'read_after_write': ReadAfterWriteError, 'outside_results': NotImplementedError}
    with pytest.raises(expected[failure]):
        log.run(operation)
    assert log.results == before
    assert log.ref('results', 'synthetic-head') == ('nontransactional', 'results', 'synthetic-head')

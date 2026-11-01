"""Read-time aborts must not discard a pass before its first model turn."""

from copy import deepcopy
from datetime import datetime, timezone

import pytest
from google.api_core.exceptions import Aborted, DeadlineExceeded
from google.cloud.firestore_v1.transaction import _Transactional

from config.dream_agent import Caps
from database import dream_turns, firestore_transaction_retry
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreDocument
from utils.llm.shaped_agent import Turn

NOW = datetime(2026, 10, 21, 13, 1, tzinfo=timezone.utc)
OWNER = 'synthetic-dream-contention'
STATE = ('dream_users', OWNER)


@pytest.fixture
def database(monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_ENABLED', 'true')
    return StrictFirestore(
        {
            STATE: {
                'lease': {
                    'run_id': 'synthetic-run',
                    'day': NOW.date().isoformat(),
                    'turn_receipts': [],
                    'budget_charge_usd': 0.0,
                }
            }
        }
    )


def operate(database, operation):
    if operation == 'reserve':
        dream_turns.reserve(OWNER, 'synthetic-run', 100, Caps(), now=NOW, firestore_client=database)
    else:
        turn = Turn(tokens=50, prompt_tokens=40, completion_tokens=10, cached_tokens=0)
        turn.cost_status, turn.cost_micro_usd = 'priced', 100
        dream_turns.settle(OWNER, 'synthetic-run', turn, firestore_client=database)


@pytest.mark.parametrize('kind', ['known_zero', 'unknown_usage', 'billed_tokens', 'billed_cost', 'unpriced'])
def test_only_known_zero_settlement_bypasses_full_receipt_cap(database, kind):
    lease = database.rows[STATE]['lease']
    lease['turn_receipts'] = [
        {'tokens': 1, 'accounted_tokens': 1, 'cached_tokens': 0, 'cost_status': 'priced', 'cost_micro_usd': 1}
        for _ in range(128)
    ]
    operate(database, 'reserve')
    turn = Turn(tokens=int(kind == 'billed_tokens'), accounted_tokens=int(kind in {'unknown_usage', 'billed_tokens'}))
    turn.cost_status = 'unpriced' if kind == 'unpriced' else 'priced'
    turn.cost_micro_usd = int(kind == 'billed_cost')
    if kind != 'known_zero':
        with pytest.raises(ValueError, match='dream_turn_cap'):
            dream_turns.settle(OWNER, 'synthetic-run', turn, firestore_client=database)
        return
    dream_turns.settle(OWNER, 'synthetic-run', turn, firestore_client=database)
    lease = database.rows[STATE]['lease']
    assert len(lease['turn_receipts']) == 128 and lease['minute_hold'] is None
    assert lease['budget_charge_usd'] == pytest.approx(0.000128)
    assert sum(row.get('tokens', 0) for key, row in database.rows.items() if key[0] == 'dream_scheduler') == 0


def commit_exhausted():
    """Produce the SDK's real ValueError-from-Aborted, without any fake writes."""

    class Transaction:
        _max_attempts, _read_only, _id = 5, False, None

        def _clean_up(self):
            self._id = None

        def _begin(self, retry_id=None):
            self._id = b'synthetic'

        def _commit(self):
            raise Aborted('synthetic commit contention')

        def _rollback(self):
            self._id = None

    with pytest.raises(ValueError) as error:
        _Transactional(lambda tx: None)(Transaction())
    assert isinstance(error.value.__cause__, Aborted)
    return error.value


@pytest.mark.parametrize('operation', ['reserve', 'settle'])
@pytest.mark.parametrize('failure', ['read_abort', 'commit_exhausted', 'persistent_abort', 'ambiguous_commit'])
def test_turn_transactions_retry_only_atomic_contention(database, monkeypatch, operation, failure):
    if operation == 'settle':
        operate(database, 'reserve')
    before = deepcopy(database.rows)
    initial_transactions = len(database.transactions)
    reads, sleeps = [], []
    error = (
        commit_exhausted()
        if failure == 'commit_exhausted'
        else (
            DeadlineExceeded('synthetic ambiguous commit')
            if failure == 'ambiguous_commit'
            else Aborted('synthetic read contention')
        )
    )
    original_get = StrictFirestoreDocument.get

    def get(ref, transaction=None, **kwargs):
        if ref.path[0] == 'dream_scheduler':
            reads.append(transaction)
            if len(reads) == 1 or failure in {'persistent_abort', 'ambiguous_commit'}:
                raise error
        return original_get(ref, transaction=transaction, **kwargs)

    retry = firestore_transaction_retry.run_with_transaction_contention_retry

    def fast_retry(*args, **kwargs):
        return retry(*args, **kwargs, sleep=sleeps.append, random_value=lambda: 0)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    monkeypatch.setattr(firestore_transaction_retry, 'run_with_transaction_contention_retry', fast_retry)
    if failure in {'persistent_abort', 'ambiguous_commit'}:
        expected = (
            firestore_transaction_retry.FirestoreContentionExhausted
            if failure == 'persistent_abort'
            else DeadlineExceeded
        )
        with pytest.raises(expected):
            operate(database, operation)
        assert database.rows == before
        assert len(reads) == (5 if failure == 'persistent_abort' else 1)
    else:
        operate(database, operation)
        assert len(reads) == 2 and len(sleeps) == 1
        lease = database.rows[STATE]['lease']
        if operation == 'reserve':
            assert lease['minute_hold']['tokens'] == 100
            assert sum(row.get('tokens', 0) for key, row in database.rows.items() if key[0] == 'dream_scheduler') == 100
        else:
            assert len(lease['turn_receipts']) == 1
            assert lease['budget_charge_usd'] == pytest.approx(0.0001)
    assert len(database.transactions) - initial_transactions == len(reads)
    assert len({id(tx) for tx in reads}) == len(reads)

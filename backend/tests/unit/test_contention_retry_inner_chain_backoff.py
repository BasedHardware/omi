"""The inner transaction chain shares the wave-bridge backoff without changing its short-chain shape.

``database._client.run_transactional`` restarts expired transaction ids (and,
opt-in ``transient=True``, contention-classified provider errors) with the
same ``equal_jitter_delay`` ladder the outer budget uses. Its default and
nested callers run at most three attempts, whose rungs (0.2s / 0.4s / 0.8s
high bounds) are unchanged by the wave-bridge cap; only callers that opt into
five or more attempts feel the tail rungs. These tests pin that boundary: the
restart predicates, the fresh-transaction-per-restart contract, the outcome
envelope, and the exact backoff each attempt depth receives.

Failure-Class: FC-contention-chain-spends-its-budget-inside-one-abort-wave
"""

import pytest
from google.api_core.exceptions import Aborted, DeadlineExceeded, InvalidArgument, ResourceExhausted, ServiceUnavailable

from database._client import run_transactional

EXPIRED = 'The referenced transaction has expired or is no longer valid.'


class FakeClock:
    def __init__(self, now: float = 1000.0):
        self.now = now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def expired_error() -> InvalidArgument:
    return InvalidArgument(EXPIRED)


class FakeTransaction:
    """Fresh transaction stand-in; identity proves each restart gets a new one."""

    def __init__(self, marker):
        self.marker = marker


class FakeClient:
    """Stand-in for the Firestore client: mints a distinct transaction per call."""

    def __init__(self):
        self.minted = []

    def transaction(self, *args, **kwargs):
        transaction = FakeTransaction(len(self.minted))
        self.minted.append(transaction)
        return transaction


def fake_client():
    return FakeClient()


def ok_body(transactions):
    def body(transaction, *args, **kwargs):
        transactions.append(transaction)
        return 'committed'

    return body


def failing_body(times, error_factory, transactions):
    def body(transaction, *args, **kwargs):
        transactions.append(transaction)
        if len(transactions) <= times:
            raise error_factory()
        return 'committed'

    return body


def test_default_path_restarts_only_expired_transaction_ids():
    transactions, clock = [], FakeClock()

    def body(transaction, *args, **kwargs):
        transactions.append(transaction)
        raise Aborted('509 some other abort without the expiry marker')

    # A plain Aborted without the expiry marker is NOT an expired id on the
    # default path: it escapes immediately — one attempt, no restart, no backoff.
    with pytest.raises(Aborted):
        run_transactional(fake_client(), body, sleep=clock.sleep, random_value=lambda: 1.0)
    assert len(transactions) == 1
    assert clock.now == 1000.0


def test_expired_id_gets_a_fresh_transaction_and_the_first_rung():
    transactions, clock = [], FakeClock()

    def body(transaction, *args, **kwargs):
        transactions.append(transaction)
        if len(transactions) == 1:
            raise expired_error()
        return 'committed'

    assert run_transactional(fake_client(), body, sleep=clock.sleep, random_value=lambda: 1.0) == 'committed'
    assert len(transactions) == 2
    assert transactions[0] is not transactions[1]
    assert clock.now - 1000.0 == pytest.approx(0.2)


def test_default_three_attempt_chain_sleeps_the_unchanged_early_rungs():
    transactions, clock = [], FakeClock()
    sleeps = []

    def record(seconds):
        sleeps.append(seconds)
        clock.sleep(seconds)

    def body(transaction, *args, **kwargs):
        transactions.append(transaction)
        if len(transactions) < 3:
            raise expired_error()
        return 'committed'

    assert run_transactional(fake_client(), body, sleep=record, random_value=lambda: 1.0) == 'committed'
    # attempts=3 by default: the 0.2s and 0.4s rungs only — the wave-bridge
    # cap cannot lengthen the default inner chain.
    assert sleeps == [0.2, 0.4]


def test_default_chain_exhausts_after_three_expired_ids():
    transactions, clock = [], FakeClock()

    def body(transaction, *args, **kwargs):
        transactions.append(transaction)
        raise expired_error()

    try:
        run_transactional(fake_client(), body, sleep=clock.sleep, random_value=lambda: 1.0)
        raise AssertionError('expected the last expired error to escape')
    except InvalidArgument as error:
        assert EXPIRED in str(error)
    assert len(transactions) == 3
    # attempts=3 sleeps only after the first two failures: 0.2 + 0.4.
    assert clock.now - 1000.0 == pytest.approx(0.6)


def test_transient_mode_restarts_contention_and_provider_errors():
    transactions, clock = [], FakeClock()
    attempts = {'n': 0}
    queued = [Aborted('a'), DeadlineExceeded('d'), ServiceUnavailable('s'), ResourceExhausted('r')]

    def body(transaction, *args, **kwargs):
        attempts['n'] += 1
        transactions.append(transaction)
        if attempts['n'] <= 4:
            raise queued[attempts['n'] - 1]
        return 'committed'

    assert run_transactional(
        fake_client(), body, transient=True, attempts=5, sleep=clock.sleep, random_value=lambda: 1.0
    )
    assert len(transactions) == 5
    # Four restarts at maximum jitter: 0.2 + 0.4 + 0.8 + 1.6 — the fifth
    # attempt is where the transient chain lands after the wave-bridge rung.
    assert clock.now - 1000.0 == 3.0


def test_transient_mode_exhausts_at_the_attempt_cap():
    clock = FakeClock()
    attempts = []

    def body(transaction, *args, **kwargs):
        attempts.append(1)
        raise Aborted('contention')

    try:
        run_transactional(fake_client(), body, transient=True, attempts=5, sleep=clock.sleep, random_value=lambda: 1.0)
        raise AssertionError('expected exhaustion')
    except Aborted:
        pass
    assert len(attempts) == 5
    assert clock.now - 1000.0 == 3.0  # 0.2 + 0.4 + 0.8 + 1.6 of backoff


def test_transient_mode_ignores_unrelated_errors():
    clock = FakeClock()
    attempts = []

    def body(transaction, *args, **kwargs):
        attempts.append(1)
        raise ValueError('bug')

    try:
        run_transactional(fake_client(), body, transient=True, attempts=5, sleep=clock.sleep, random_value=lambda: 1.0)
    except ValueError:
        pass
    assert len(attempts) == 1
    assert clock.now == 1000.0


def test_nested_attempts_one_runs_exactly_once():
    transactions, clock = [], FakeClock()
    run_transactional(
        fake_client(),
        ok_body(transactions),
        attempts=1,
        initial_transaction=FakeTransaction('outer'),
        sleep=clock.sleep,
    )
    assert len(transactions) == 1
    assert transactions[0].marker == 'outer'
    assert clock.now == 1000.0


def test_nested_attempts_one_lets_the_expired_initial_escape_to_the_outer_budget():
    """``attempts=1`` means the outer contention budget owns every retry: an
    expired initial transaction is not replaced here — it propagates so the
    outer chain's fresh attempt owns the restart."""
    transactions, clock = [], FakeClock()

    def body(transaction, *args, **kwargs):
        transactions.append(transaction)
        raise expired_error()

    with pytest.raises(InvalidArgument):
        run_transactional(
            fake_client(),
            body,
            attempts=1,
            initial_transaction=FakeTransaction('outer'),
            sleep=clock.sleep,
            random_value=lambda: 1.0,
        )
    assert len(transactions) == 1
    assert transactions[0].marker == 'outer'
    assert clock.now == 1000.0


def test_inner_chain_replaces_an_expired_initial_within_its_own_budget():
    transactions, clock = [], FakeClock()

    def body(transaction, *args, **kwargs):
        transactions.append(transaction)
        if len(transactions) == 1:
            raise expired_error()
        return 'committed'

    assert (
        run_transactional(
            fake_client(),
            body,
            attempts=2,
            initial_transaction=FakeTransaction('outer'),
            sleep=clock.sleep,
            random_value=lambda: 1.0,
        )
        == 'committed'
    )
    # The expired outer id is replaced by a fresh transaction from the client,
    # never replayed under the retired id.
    assert len(transactions) == 2
    assert transactions[0].marker == 'outer'
    assert transactions[1].marker != 'outer'
    assert clock.now - 1000.0 == pytest.approx(0.2)


def test_outcome_records_retried_ok_after_a_restart():
    transactions, clock, outcome = [], FakeClock(), {}

    def body(transaction, *args, **kwargs):
        transactions.append(transaction)
        if len(transactions) == 1:
            raise expired_error()
        return 'committed'

    run_transactional(fake_client(), body, sleep=clock.sleep, random_value=lambda: 1.0, outcome=outcome)
    assert outcome == {'status': 'retried_ok'}


def test_outcome_records_exhausted_when_the_budget_runs_out():
    clock, outcome = FakeClock(), {}

    def body(transaction, *args, **kwargs):
        raise expired_error()

    try:
        run_transactional(fake_client(), body, attempts=2, sleep=clock.sleep, random_value=lambda: 1.0, outcome=outcome)
    except InvalidArgument:
        pass
    assert outcome == {'status': 'exhausted'}


def test_outcome_untouched_on_first_attempt_success():
    transactions, clock, outcome = [], FakeClock(), {}
    run_transactional(fake_client(), ok_body(transactions), sleep=clock.sleep, outcome=outcome)
    assert outcome == {}


def test_backoff_runs_after_the_callable_returns():
    """A lock held inside the callable is released before the sleep: the
    restart's backoff must never hold a caller's critical section."""
    clock = FakeClock()
    events = []

    def body(transaction, *args, **kwargs):
        events.append('body')
        raise expired_error()

    def record_sleep(seconds):
        events.append(f'sleep:{seconds}')
        clock.sleep(seconds)

    try:
        run_transactional(fake_client(), body, attempts=2, sleep=record_sleep, random_value=lambda: 1.0)
    except InvalidArgument:
        pass
    # Two attempts, one restart: the sleep runs between the callable returns,
    # never inside one, and the final failure raises without another sleep.
    assert events == ['body', 'sleep:0.2', 'body']


def test_kwargs_are_forwarded_to_the_callable():
    transactions, clock = [], FakeClock()
    seen = {}

    def body(transaction, *args, **kwargs):
        seen.update(kwargs)
        transactions.append(transaction)
        return 'committed'

    run_transactional(fake_client(), body, sleep=clock.sleep, namespace='x', fence='y')
    assert seen == {'namespace': 'x', 'fence': 'y'}


def test_attempts_below_one_still_run_once():
    transactions, clock = [], FakeClock()
    assert run_transactional(fake_client(), ok_body(transactions), attempts=0, sleep=clock.sleep) == 'committed'
    assert len(transactions) == 1


def test_wave_bridge_cap_does_not_lengthen_the_default_inner_chain():
    """The store's nested budgets pass attempts=1 and the standalone default
    is three attempts: both stay inside the unchanged early rungs. Only an
    explicit attempts>=4 caller (transient opt-in) reaches the grown rungs."""
    transactions, clock = [], FakeClock()

    def body(transaction, *args, **kwargs):
        transactions.append(transaction)
        raise expired_error()

    try:
        run_transactional(fake_client(), body, attempts=4, sleep=clock.sleep, random_value=lambda: 1.0)
    except InvalidArgument:
        pass
    # Four attempts sleep after failures 1-3 only: 0.2 + 0.4 + 0.8 — the
    # fourth rung (1.6) belongs to the fifth attempt's restart, outside the
    # default and nested chains' reach.
    assert len(transactions) == 4
    assert clock.now - 1000.0 == pytest.approx(1.4)

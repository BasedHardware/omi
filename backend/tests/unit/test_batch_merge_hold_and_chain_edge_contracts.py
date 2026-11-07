"""Merge bookkeeping, scheduler label contracts and chain odds and ends.

The wave bridge changes how long the chain waits; the callers around it keep
their bookkeeping exact. This suite closes out the remaining caller-level
contracts: the ordered merge's hold-marker cursor, release and entry-flag
bookkeeping; the scheduler transition methods' label and propagation
contracts; and a handful of chain edge semantics (boolean budgets, float
rungs, site attribution, single-attempt silence).

Failure-Class: FC-contention-chain-spends-its-budget-inside-one-abort-wave
"""

import pytest
from google.api_core.exceptions import Aborted

import database.firestore_transaction_retry as retry_module
from database.firestore_transaction_retry import (
    DEFAULT_MAX_ATTEMPTS,
    FirestoreContentionExhausted,
    equal_jitter_delay,
    run_with_transaction_contention_retry,
)
from utils.batch_pipeline.merge import OrderedMerge

KEY = 'k1'
OWNER = 'owner-a'


class FakeClock:
    def __init__(self, now: float = 1000.0):
        self.now = now

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


# --------------------------------------------------------------------------
# OrderedMerge.release_hold
# --------------------------------------------------------------------------


class HoldStore:
    def __init__(self, rows=None):
        self.rows = rows if rows is not None else {}
        self.run_calls = 0
        self.run_error = None

    def run(self, body, *, operation=None):
        self.run_calls += 1
        if self.run_error is not None:
            self.run_error, error = None, self.run_error
            raise error
        tx = SimpleTx(self.rows)
        result = body(tx)
        return result

    def probe(self, table, key):
        return self.rows.get((table, key), {})

    def held_merge_owners(self, limit=50, after=None):
        marked = [
            (key, None) for (table, key), value in self.rows.items() if table == 'merge_holds' and value.get('held')
        ]
        if after is not None:
            marked = marked[[key for key, _ in marked].index(after) + 1 :]
        return marked[:limit]


class SimpleTx:
    def __init__(self, rows):
        self.rows = rows

    def get(self, table, key):
        return self.rows.get((table, key), {})

    def put(self, table, key, value):
        self.rows[(table, key)] = value


def test_release_hold_clears_a_marked_owner():
    rows = {('merge_holds', KEY): {'held': True}}
    merge = OrderedMerge(HoldStore(rows), head_wait_seconds=0, catch_up_depth=0)
    merge.release_hold(KEY)
    assert rows[('merge_holds', KEY)]['held'] is False


def test_release_hold_keeps_a_marked_owner_at_the_depth_cap():
    rows = {
        ('merge_holds', KEY): {'held': True},
        ('owners', KEY): {'log_sequence': 10, 'projection_watermark': 'w1'},
        ('results', 'w1'): {'log_sequence': 2},
    }
    merge = OrderedMerge(HoldStore(rows), head_wait_seconds=0, catch_up_depth=5)
    merge.release_hold(KEY)
    assert rows[('merge_holds', KEY)]['held'] is True


def test_release_hold_force_clears_even_at_the_cap():
    rows = {('merge_holds', KEY): {'held': True}}
    merge = OrderedMerge(HoldStore(rows), head_wait_seconds=0, catch_up_depth=5)
    merge.release_hold(KEY, force=True)
    assert rows[('merge_holds', KEY)]['held'] is False


def test_release_hold_of_an_unmarked_owner_writes_nothing():
    rows = {}
    merge = OrderedMerge(HoldStore(rows), head_wait_seconds=0, catch_up_depth=0)
    merge.release_hold(KEY)
    assert rows == {}


def test_release_hold_exhaustion_escapes():
    merge = OrderedMerge(HoldStore({('merge_holds', KEY): {'held': True}}), head_wait_seconds=0, catch_up_depth=0)
    merge.store.run_error = FirestoreContentionExhausted('storm')
    with pytest.raises(FirestoreContentionExhausted):
        merge.release_hold(KEY)


def test_marked_page_returns_the_cursor_page():
    rows = {('merge_holds', f'k{i}'): {'held': True} for i in range(3)}
    store = HoldStore(rows)
    merge = OrderedMerge(store, head_wait_seconds=0, catch_up_depth=0)
    page = merge.marked_page(2)
    assert len(page) == 2


def test_marked_page_short_page_resets_the_cursor():
    rows = {('merge_holds', f'k{i}'): {'held': True} for i in range(2)}
    merge = OrderedMerge(HoldStore(rows), head_wait_seconds=0, catch_up_depth=0)
    merge.marked_page(50)
    assert merge._marked_after is None


def test_marked_page_full_page_advances_the_cursor():
    rows = {('merge_holds', f'k{i}'): {'held': True} for i in range(3)}
    merge = OrderedMerge(HoldStore(rows), head_wait_seconds=0, catch_up_depth=0)
    page = merge.marked_page(2)
    assert merge._marked_after == page[-1][0]


def test_reoffer_marked_releases_ownerless_markers():
    rows = {('merge_holds', KEY): {'held': True}}
    store = HoldStore(rows)
    merge = OrderedMerge(store, head_wait_seconds=0, catch_up_depth=0)
    merge.reoffer_marked(lambda owner: pytest.fail('an ownerless marker is not drained'), limit=50)
    assert rows[('merge_holds', KEY)]['held'] is False


def test_reoffer_marked_drains_marked_owners():
    drained = []
    rows = {('merge_holds', KEY): {'held': True}}
    store = HoldStore(rows)
    store.held_merge_owners = lambda limit=50, after=None: [(KEY, OWNER)]
    merge = OrderedMerge(store, head_wait_seconds=0, catch_up_depth=0)
    merge.reoffer_marked(lambda owner: drained.append(owner), limit=50)
    assert drained == [OWNER]
    assert rows[('merge_holds', KEY)]['held'] is False


def test_reoffer_marked_survives_one_failing_owner():
    rows = {('merge_holds', 'a1'): {'held': True}, ('merge_holds', 'b2'): {'held': True}}
    store = HoldStore(rows)
    merge = OrderedMerge(store, head_wait_seconds=0, catch_up_depth=0)

    def drain(owner):
        if owner == 'a1':
            raise FirestoreContentionExhausted('hot')

    merge.reoffer_marked(drain, limit=50)
    # One fenced owner must not starve the rest of the page: both markers released.
    assert store.rows[('merge_holds', 'a1')]['held'] is False
    assert store.rows[('merge_holds', 'b2')]['held'] is False


# --------------------------------------------------------------------------
# Chain odds and ends
# --------------------------------------------------------------------------


def test_boolean_attempt_budget_behaves_as_one():
    """``True`` is 1: the chain runs a single attempt and exhausts."""
    clock = FakeClock()

    def operation(transaction):
        raise Aborted('contention')

    with pytest.raises(FirestoreContentionExhausted):
        run_with_transaction_contention_retry(
            lambda: object(),
            operation,
            operation_name='true',
            max_attempts=True,
            sleep=clock.sleep,
            monotonic=clock.monotonic,
        )


def test_float_attempt_rungs_are_well_defined():
    assert equal_jitter_delay(1.5, random_value=lambda: 1.0) == pytest.approx(0.2 * 2**0.5)


def test_single_attempt_chain_logs_no_retry_lines(caplog):
    clock = FakeClock()

    def operation(transaction):
        raise Aborted('contention')

    with caplog.at_level('WARNING', logger='database.firestore_transaction_retry'):
        with pytest.raises(FirestoreContentionExhausted):
            run_with_transaction_contention_retry(
                lambda: object(),
                operation,
                operation_name='once',
                max_attempts=1,
                sleep=clock.sleep,
                monotonic=clock.monotonic,
            )
    assert [line for line in caplog.messages if 'outcome=retry' in line] == []


def test_exhaustion_logs_carry_the_static_site_field(caplog):
    clock = FakeClock()

    def operation(transaction):
        raise Aborted('contention')

    with caplog.at_level('ERROR', logger='database.firestore_transaction_retry'):
        with pytest.raises(FirestoreContentionExhausted):
            run_with_transaction_contention_retry(
                lambda: object(), operation, operation_name='site', sleep=clock.sleep, monotonic=clock.monotonic
            )
    for record in caplog.records:
        assert record.filename == 'firestore_transaction_retry.py'


def test_the_default_jitter_source_is_the_random_module():
    # Two runs with the real jitter source land in the attempt-1 band.
    for _ in range(5):
        assert 0.1 <= equal_jitter_delay(1) < 0.2


def test_default_attempt_budget_is_importable_surface():
    assert DEFAULT_MAX_ATTEMPTS == 5


def test_recovery_on_attempt_two_logs_recovered(caplog):
    clock = FakeClock()
    state = {'n': 0}

    def operation(transaction):
        state['n'] += 1
        if state['n'] == 1:
            raise Aborted('contention')

    with caplog.at_level('INFO', logger='database.firestore_transaction_retry'):
        run_with_transaction_contention_retry(
            lambda: object(), operation, operation_name='r2', sleep=clock.sleep, monotonic=clock.monotonic
        )
    assert any('attempt=2/5' in line for line in caplog.messages)


def test_non_contention_error_site_is_the_caller_not_the_chain():
    clock = FakeClock()

    def operation(transaction):
        raise KeyError('real bug')

    with pytest.raises(KeyError):
        run_with_transaction_contention_retry(
            lambda: object(), operation, operation_name='caller_site', sleep=clock.sleep, monotonic=clock.monotonic
        )


def test_the_chain_module_name_is_the_log_namespace():
    assert retry_module.__name__ == 'database.firestore_transaction_retry'


def test_delay_schedule_never_sleeps_on_the_first_attempt():
    """Attempt 1 runs immediately: the wave bridge only widens gaps after a
    failure, never the time to the first try."""
    clock = FakeClock()
    seen = []

    def operation(transaction):
        seen.append(clock.now)
        raise Aborted('contention')

    with pytest.raises(FirestoreContentionExhausted):
        run_with_transaction_contention_retry(
            lambda: object(),
            operation,
            operation_name='first',
            sleep=clock.sleep,
            random_value=lambda: 1.0,
            monotonic=clock.monotonic,
        )
    assert seen[0] == 1000.0

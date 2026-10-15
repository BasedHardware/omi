"""Hermetic unit suite for database/firestore_transaction_retry.py (#20101).

Covers the contention detector's full causal-graph walk (explicit __cause__,
implicit __context__, PEP 654 groups, cycle safety), status-code matching
including non-contention negatives, jitter hardening, parameter validation,
and on_retry fault isolation. The module ships a stub fallback for
FirestoreAborted, so the suite needs no google.api_core install.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import pytest

from database import firestore_transaction_retry as retry_mod

Aborted = retry_mod.FirestoreAborted
run = retry_mod.run_with_transaction_contention_retry


class HttpStyleError(Exception):
    def __init__(self, code):
        super().__init__('http')
        self.code = code


class GrpcStyleError(Exception):
    def __init__(self, code):
        super().__init__('grpc')
        self.grpc_status_code = code


def _drive(op, *, attempts=5):
    sleeps = []
    retries = []
    result = run(
        lambda: object(),
        op,
        operation_name='test',
        max_attempts=attempts,
        sleep=sleeps.append,
        random_value=lambda: 0.0,
        on_retry=lambda a, d, e: retries.append((a, d)),
    )
    return result, sleeps, retries


def _fail_then_succeed(error_factory, succeed_after):
    state = {'n': 0}

    def op(_txn):
        state['n'] += 1
        if state['n'] <= succeed_after:
            raise error_factory()
        return 'ok'

    return op, state


# ---------------------------------------------------------------------------
# Causal-graph traversal
# ---------------------------------------------------------------------------
def test_direct_aborted_retries_then_succeeds():
    op, state = _fail_then_succeed(lambda: Aborted('aborted'), 2)
    result, sleeps, _ = _drive(op)
    assert result == 'ok' and state['n'] == 3 and len(sleeps) == 2


def test_implicit_context_chain_retries():
    """raise inside except without `from` puts the cause on __context__."""

    def make():
        try:
            raise Aborted('inner')
        except Aborted:
            raise RuntimeError('wrapper')

    op, state = _fail_then_succeed(make, 1)
    result, _, _ = _drive(op)
    assert result == 'ok' and state['n'] == 2


def test_explicit_cause_retries():
    def make():
        e = RuntimeError('wrapper')
        e.__cause__ = Aborted('inner')
        return e

    op, state = _fail_then_succeed(make, 1)
    result, _, _ = _drive(op)
    assert result == 'ok' and state['n'] == 2


def test_exception_group_member_retries():
    def make():
        return ExceptionGroup('g', [ValueError('noise'), Aborted('aborted')])

    op, state = _fail_then_succeed(make, 1)
    result, _, _ = _drive(op)
    assert result == 'ok' and state['n'] == 2


def test_causal_cycle_does_not_hang():
    a, b = RuntimeError('a'), RuntimeError('b')
    a.__cause__ = b
    b.__cause__ = a
    op, _ = _fail_then_succeed(lambda: a, 5)
    with pytest.raises(RuntimeError):
        run(lambda: None, op, operation_name='t', max_attempts=1, sleep=lambda s: None)


# ---------------------------------------------------------------------------
# Status-code matching
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('err', [HttpStyleError(409), GrpcStyleError(10)])
def test_wrapped_contention_status_retries(err):
    op, state = _fail_then_succeed(lambda: err, 1)
    result, _, _ = _drive(op)
    assert result == 'ok' and state['n'] == 2


@pytest.mark.parametrize('err', [HttpStyleError(400), HttpStyleError(404), GrpcStyleError(9), ValueError('x')])
def test_non_contention_raises_without_retry(err):
    op, state = _fail_then_succeed(lambda: err, 99)
    with pytest.raises(type(err)) as exc_info:
        _drive(op)
    assert exc_info.value is err
    assert state['n'] == 1


def test_bool_status_code_is_not_contention():
    class BoolCode(Exception):
        code = True  # bool is a subclass of int — must not match 409 families

    with pytest.raises(BoolCode):
        run(lambda: None, lambda t: (_ for _ in ()).throw(BoolCode()), operation_name='t', sleep=lambda s: None)


# ---------------------------------------------------------------------------
# Bounds, exhaustion, hooks
# ---------------------------------------------------------------------------
def test_exhaustion_raises_contention_exhausted():
    sleeps = []
    with pytest.raises(retry_mod.FirestoreContentionExhausted):
        run(
            lambda: object(),
            lambda t: (_ for _ in ()).throw(Aborted('always')),
            operation_name='t',
            max_attempts=3,
            sleep=sleeps.append,
            random_value=lambda: 0.0,
        )
    assert len(sleeps) == 2


@pytest.mark.parametrize('bad', [True, False, 0, -1, 2.5, 'x'])
def test_max_attempts_validation(bad):
    with pytest.raises((ValueError, TypeError)):
        run(lambda: None, lambda t: None, operation_name='t', max_attempts=bad)


@pytest.mark.parametrize('rng', [lambda: float('nan'), lambda: float('inf'), lambda: 1.5, lambda: -0.5, lambda: 'x'])
def test_jitter_degrades_safely(rng):
    sleeps = []
    op, _ = _fail_then_succeed(lambda: Aborted('x'), 1)
    run(lambda: object(), op, operation_name='t', sleep=sleeps.append, random_value=rng)
    assert len(sleeps) == 1 and 0.05 <= sleeps[0] <= 0.2


def test_on_retry_hook_is_fault_isolated():
    op, state = _fail_then_succeed(lambda: Aborted('x'), 1)

    def bad_hook(a, d, e):
        raise RuntimeError('hook exploded')

    result = run(
        lambda: object(), op, operation_name='t', sleep=lambda s: None, random_value=lambda: 0.0, on_retry=bad_hook
    )
    assert result == 'ok' and state['n'] == 2


def test_on_retry_receives_attempt_delay_error():
    seen = []
    raised = Aborted('x')
    op, _ = _fail_then_succeed(lambda: raised, 1)
    run(
        lambda: object(),
        op,
        operation_name='t',
        sleep=lambda s: None,
        random_value=lambda: 0.25,
        on_retry=lambda a, d, e: seen.append((a, d, e)),
    )
    # attempt 1: low=0.1, high=0.2, jitter=0.25 -> delay = 0.1 + 0.1*0.25
    assert seen == [(1, 0.125, raised)]


def test_success_on_first_attempt_never_sleeps():
    sleeps = []
    result = run(lambda: object(), lambda t: 'ok', operation_name='t', sleep=sleeps.append)
    assert result == 'ok' and sleeps == []


def test_backoff_grows_and_caps():
    sleeps = []
    run(
        lambda: object(),
        _fail_then_succeed(lambda: Aborted('x'), 4)[0],
        operation_name='t',
        max_attempts=5,
        sleep=sleeps.append,
        random_value=lambda: 1.0,
    )
    assert sleeps == sorted(sleeps) and sleeps[-1] <= 1.0

"""Ladder alignment grid for the mid-ladder storm gate.

Every cell drives one deterministic retry chain through
``run_with_transaction_contention_retry`` with an inter-attempt gate and
asserts the full sleep vector, the gate-call vector and the boundary
outcome against the documented rung arithmetic: rung ``i`` waits
``min(0.2 * 2**(i - 1), 4.0)`` seconds of equal jitter plus whatever the
gate returned for that rung. The expectations are computed at generation
time from that formula and written as literals - no shared helper decides
a cell's expectation.

Failure-Class: FC-mid-ladder-retry-collides-inside-the-concurrently-armed-storm-window
"""

import logging
import re

import pytest
from google.api_core.exceptions import Aborted

from database.firestore_transaction_retry import (
    FirestoreContentionExhausted,
    run_with_transaction_contention_retry,
)


class _Clock:
    """Deterministic monotonic clock, sleep recorder and jitter source."""

    def __init__(self, now=100.0, jitter=1.0):
        self.now = now
        self.jitter = jitter
        self.sleeps = []
        self.gate_calls = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        assert seconds >= 0
        self.sleeps.append(round(seconds, 9))
        self.now += seconds

    def random_value(self):
        return self.jitter

    def advance(self, seconds):
        self.now += seconds


def _chain(clock, *, aborts, gate=None, max_attempts=5, deadline=None, fail_non_contention_at=None):
    """Run one chain: ``aborts`` Aborted bodies, then success.

    ``fail_non_contention_at`` raises ``ValueError`` on that 1-based attempt
    instead of an Aborted, modelling a real failure riding mid-chain.
    """
    state = {'n': 0}

    def operation(tx):
        state['n'] += 1
        if fail_non_contention_at is not None and state['n'] == fail_non_contention_at:
            raise ValueError('not contention')
        if state['n'] <= aborts:
            raise Aborted('synthetic contention')
        return 'ok'

    kwargs = {
        'operation_name': 'grid',
        'sleep': clock.sleep,
        'random_value': clock.random_value,
        'monotonic': clock.monotonic,
        'max_attempts': max_attempts,
    }
    if gate is not None:
        kwargs['inter_attempt_gate'] = gate
    if deadline is not None:
        kwargs['deadline'] = deadline
    return run_with_transaction_contention_retry(lambda: object(), operation, **kwargs)


def _gate_recorder(clock, value):
    """A gate returning ``value`` that records every attempt it sees."""

    def gate(attempt):
        clock.gate_calls.append(attempt)
        return value

    return gate


def _fmt(values):
    return '[' + ', '.join(repr(round(v, 9)) for v in values) + ']'


def test_align_recover_after_1_jitter_000_gate_0000():
    """Chain recovers on attempt 1 (jitter 0.0, gate 0.0): 0 gated rung(s) []."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.0))
    assert result == 'ok'
    assert clock.gate_calls == []
    assert clock.sleeps == []  # no retries


def test_align_recover_after_1_jitter_000_gate_0125():
    """Chain recovers on attempt 1 (jitter 0.0, gate 0.125): 0 gated rung(s) []."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.gate_calls == []
    assert clock.sleeps == []  # no retries


def test_align_recover_after_1_jitter_000_gate_0250():
    """Chain recovers on attempt 1 (jitter 0.0, gate 0.25): 0 gated rung(s) []."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.25))
    assert result == 'ok'
    assert clock.gate_calls == []
    assert clock.sleeps == []  # no retries


def test_align_recover_after_1_jitter_000_gate_0500():
    """Chain recovers on attempt 1 (jitter 0.0, gate 0.5): 0 gated rung(s) []."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.5))
    assert result == 'ok'
    assert clock.gate_calls == []
    assert clock.sleeps == []  # no retries


def test_align_recover_after_1_jitter_000_gate_1000():
    """Chain recovers on attempt 1 (jitter 0.0, gate 1.0): 0 gated rung(s) []."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 1.0))
    assert result == 'ok'
    assert clock.gate_calls == []
    assert clock.sleeps == []  # no retries


def test_align_recover_after_1_jitter_000_gate_2000():
    """Chain recovers on attempt 1 (jitter 0.0, gate 2.0): 0 gated rung(s) []."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 2.0))
    assert result == 'ok'
    assert clock.gate_calls == []
    assert clock.sleeps == []  # no retries


def test_align_recover_after_1_jitter_000_gate_4000():
    """Chain recovers on attempt 1 (jitter 0.0, gate 4.0): 0 gated rung(s) []."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 4.0))
    assert result == 'ok'
    assert clock.gate_calls == []
    assert clock.sleeps == []  # no retries


def test_align_recover_after_1_jitter_025_gate_0000():
    """Chain recovers on attempt 1 (jitter 0.25, gate 0.0): 0 gated rung(s) []."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.0))
    assert result == 'ok'
    assert clock.gate_calls == []
    assert clock.sleeps == []  # no retries


def test_align_recover_after_1_jitter_025_gate_0125():
    """Chain recovers on attempt 1 (jitter 0.25, gate 0.125): 0 gated rung(s) []."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.gate_calls == []
    assert clock.sleeps == []  # no retries


def test_align_recover_after_1_jitter_025_gate_0250():
    """Chain recovers on attempt 1 (jitter 0.25, gate 0.25): 0 gated rung(s) []."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.25))
    assert result == 'ok'
    assert clock.gate_calls == []
    assert clock.sleeps == []  # no retries


def test_align_recover_after_1_jitter_025_gate_0500():
    """Chain recovers on attempt 1 (jitter 0.25, gate 0.5): 0 gated rung(s) []."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.5))
    assert result == 'ok'
    assert clock.gate_calls == []
    assert clock.sleeps == []  # no retries


def test_align_recover_after_1_jitter_025_gate_1000():
    """Chain recovers on attempt 1 (jitter 0.25, gate 1.0): 0 gated rung(s) []."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 1.0))
    assert result == 'ok'
    assert clock.gate_calls == []
    assert clock.sleeps == []  # no retries


def test_align_recover_after_1_jitter_025_gate_2000():
    """Chain recovers on attempt 1 (jitter 0.25, gate 2.0): 0 gated rung(s) []."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 2.0))
    assert result == 'ok'
    assert clock.gate_calls == []
    assert clock.sleeps == []  # no retries


def test_align_recover_after_1_jitter_025_gate_4000():
    """Chain recovers on attempt 1 (jitter 0.25, gate 4.0): 0 gated rung(s) []."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 4.0))
    assert result == 'ok'
    assert clock.gate_calls == []
    assert clock.sleeps == []  # no retries


def test_align_recover_after_1_jitter_050_gate_0000():
    """Chain recovers on attempt 1 (jitter 0.5, gate 0.0): 0 gated rung(s) []."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.0))
    assert result == 'ok'
    assert clock.gate_calls == []
    assert clock.sleeps == []  # no retries


def test_align_recover_after_1_jitter_050_gate_0125():
    """Chain recovers on attempt 1 (jitter 0.5, gate 0.125): 0 gated rung(s) []."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.gate_calls == []
    assert clock.sleeps == []  # no retries


def test_align_recover_after_1_jitter_050_gate_0250():
    """Chain recovers on attempt 1 (jitter 0.5, gate 0.25): 0 gated rung(s) []."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.25))
    assert result == 'ok'
    assert clock.gate_calls == []
    assert clock.sleeps == []  # no retries


def test_align_recover_after_1_jitter_050_gate_0500():
    """Chain recovers on attempt 1 (jitter 0.5, gate 0.5): 0 gated rung(s) []."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.5))
    assert result == 'ok'
    assert clock.gate_calls == []
    assert clock.sleeps == []  # no retries


def test_align_recover_after_1_jitter_050_gate_1000():
    """Chain recovers on attempt 1 (jitter 0.5, gate 1.0): 0 gated rung(s) []."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 1.0))
    assert result == 'ok'
    assert clock.gate_calls == []
    assert clock.sleeps == []  # no retries


def test_align_recover_after_1_jitter_050_gate_2000():
    """Chain recovers on attempt 1 (jitter 0.5, gate 2.0): 0 gated rung(s) []."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 2.0))
    assert result == 'ok'
    assert clock.gate_calls == []
    assert clock.sleeps == []  # no retries


def test_align_recover_after_1_jitter_050_gate_4000():
    """Chain recovers on attempt 1 (jitter 0.5, gate 4.0): 0 gated rung(s) []."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 4.0))
    assert result == 'ok'
    assert clock.gate_calls == []
    assert clock.sleeps == []  # no retries


def test_align_recover_after_1_jitter_075_gate_0000():
    """Chain recovers on attempt 1 (jitter 0.75, gate 0.0): 0 gated rung(s) []."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.0))
    assert result == 'ok'
    assert clock.gate_calls == []
    assert clock.sleeps == []  # no retries


def test_align_recover_after_1_jitter_075_gate_0125():
    """Chain recovers on attempt 1 (jitter 0.75, gate 0.125): 0 gated rung(s) []."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.gate_calls == []
    assert clock.sleeps == []  # no retries


def test_align_recover_after_1_jitter_075_gate_0250():
    """Chain recovers on attempt 1 (jitter 0.75, gate 0.25): 0 gated rung(s) []."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.25))
    assert result == 'ok'
    assert clock.gate_calls == []
    assert clock.sleeps == []  # no retries


def test_align_recover_after_1_jitter_075_gate_0500():
    """Chain recovers on attempt 1 (jitter 0.75, gate 0.5): 0 gated rung(s) []."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.5))
    assert result == 'ok'
    assert clock.gate_calls == []
    assert clock.sleeps == []  # no retries


def test_align_recover_after_1_jitter_075_gate_1000():
    """Chain recovers on attempt 1 (jitter 0.75, gate 1.0): 0 gated rung(s) []."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 1.0))
    assert result == 'ok'
    assert clock.gate_calls == []
    assert clock.sleeps == []  # no retries


def test_align_recover_after_1_jitter_075_gate_2000():
    """Chain recovers on attempt 1 (jitter 0.75, gate 2.0): 0 gated rung(s) []."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 2.0))
    assert result == 'ok'
    assert clock.gate_calls == []
    assert clock.sleeps == []  # no retries


def test_align_recover_after_1_jitter_075_gate_4000():
    """Chain recovers on attempt 1 (jitter 0.75, gate 4.0): 0 gated rung(s) []."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 4.0))
    assert result == 'ok'
    assert clock.gate_calls == []
    assert clock.sleeps == []  # no retries


def test_align_recover_after_1_jitter_100_gate_0000():
    """Chain recovers on attempt 1 (jitter 1.0, gate 0.0): 0 gated rung(s) []."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.0))
    assert result == 'ok'
    assert clock.gate_calls == []
    assert clock.sleeps == []  # no retries


def test_align_recover_after_1_jitter_100_gate_0125():
    """Chain recovers on attempt 1 (jitter 1.0, gate 0.125): 0 gated rung(s) []."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.gate_calls == []
    assert clock.sleeps == []  # no retries


def test_align_recover_after_1_jitter_100_gate_0250():
    """Chain recovers on attempt 1 (jitter 1.0, gate 0.25): 0 gated rung(s) []."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.25))
    assert result == 'ok'
    assert clock.gate_calls == []
    assert clock.sleeps == []  # no retries


def test_align_recover_after_1_jitter_100_gate_0500():
    """Chain recovers on attempt 1 (jitter 1.0, gate 0.5): 0 gated rung(s) []."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.5))
    assert result == 'ok'
    assert clock.gate_calls == []
    assert clock.sleeps == []  # no retries


def test_align_recover_after_1_jitter_100_gate_1000():
    """Chain recovers on attempt 1 (jitter 1.0, gate 1.0): 0 gated rung(s) []."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 1.0))
    assert result == 'ok'
    assert clock.gate_calls == []
    assert clock.sleeps == []  # no retries


def test_align_recover_after_1_jitter_100_gate_2000():
    """Chain recovers on attempt 1 (jitter 1.0, gate 2.0): 0 gated rung(s) []."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 2.0))
    assert result == 'ok'
    assert clock.gate_calls == []
    assert clock.sleeps == []  # no retries


def test_align_recover_after_1_jitter_100_gate_4000():
    """Chain recovers on attempt 1 (jitter 1.0, gate 4.0): 0 gated rung(s) []."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 4.0))
    assert result == 'ok'
    assert clock.gate_calls == []
    assert clock.sleeps == []  # no retries


def test_align_recover_after_2_jitter_000_gate_0000():
    """Chain recovers on attempt 2 (jitter 0.0, gate 0.0): 1 gated rung(s) [0.1]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.0))
    assert result == 'ok'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [0.1]  # rung1


def test_align_recover_after_2_jitter_000_gate_0125():
    """Chain recovers on attempt 2 (jitter 0.0, gate 0.125): 1 gated rung(s) [0.225]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [0.225]  # rung1


def test_align_recover_after_2_jitter_000_gate_0250():
    """Chain recovers on attempt 2 (jitter 0.0, gate 0.25): 1 gated rung(s) [0.35]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.25))
    assert result == 'ok'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [0.35]  # rung1


def test_align_recover_after_2_jitter_000_gate_0500():
    """Chain recovers on attempt 2 (jitter 0.0, gate 0.5): 1 gated rung(s) [0.6]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.5))
    assert result == 'ok'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [0.6]  # rung1


def test_align_recover_after_2_jitter_000_gate_1000():
    """Chain recovers on attempt 2 (jitter 0.0, gate 1.0): 1 gated rung(s) [1.1]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 1.0))
    assert result == 'ok'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [1.1]  # rung1


def test_align_recover_after_2_jitter_000_gate_2000():
    """Chain recovers on attempt 2 (jitter 0.0, gate 2.0): 1 gated rung(s) [2.1]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 2.0))
    assert result == 'ok'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [2.1]  # rung1


def test_align_recover_after_2_jitter_000_gate_4000():
    """Chain recovers on attempt 2 (jitter 0.0, gate 4.0): 1 gated rung(s) [4.1]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 4.0))
    assert result == 'ok'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [4.1]  # rung1


def test_align_recover_after_2_jitter_025_gate_0000():
    """Chain recovers on attempt 2 (jitter 0.25, gate 0.0): 1 gated rung(s) [0.125]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.0))
    assert result == 'ok'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [0.125]  # rung1


def test_align_recover_after_2_jitter_025_gate_0125():
    """Chain recovers on attempt 2 (jitter 0.25, gate 0.125): 1 gated rung(s) [0.25]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [0.25]  # rung1


def test_align_recover_after_2_jitter_025_gate_0250():
    """Chain recovers on attempt 2 (jitter 0.25, gate 0.25): 1 gated rung(s) [0.375]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.25))
    assert result == 'ok'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [0.375]  # rung1


def test_align_recover_after_2_jitter_025_gate_0500():
    """Chain recovers on attempt 2 (jitter 0.25, gate 0.5): 1 gated rung(s) [0.625]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.5))
    assert result == 'ok'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [0.625]  # rung1


def test_align_recover_after_2_jitter_025_gate_1000():
    """Chain recovers on attempt 2 (jitter 0.25, gate 1.0): 1 gated rung(s) [1.125]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 1.0))
    assert result == 'ok'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [1.125]  # rung1


def test_align_recover_after_2_jitter_025_gate_2000():
    """Chain recovers on attempt 2 (jitter 0.25, gate 2.0): 1 gated rung(s) [2.125]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 2.0))
    assert result == 'ok'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [2.125]  # rung1


def test_align_recover_after_2_jitter_025_gate_4000():
    """Chain recovers on attempt 2 (jitter 0.25, gate 4.0): 1 gated rung(s) [4.125]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 4.0))
    assert result == 'ok'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [4.125]  # rung1


def test_align_recover_after_2_jitter_050_gate_0000():
    """Chain recovers on attempt 2 (jitter 0.5, gate 0.0): 1 gated rung(s) [0.15]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.0))
    assert result == 'ok'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [0.15]  # rung1


def test_align_recover_after_2_jitter_050_gate_0125():
    """Chain recovers on attempt 2 (jitter 0.5, gate 0.125): 1 gated rung(s) [0.275]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [0.275]  # rung1


def test_align_recover_after_2_jitter_050_gate_0250():
    """Chain recovers on attempt 2 (jitter 0.5, gate 0.25): 1 gated rung(s) [0.4]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.25))
    assert result == 'ok'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [0.4]  # rung1


def test_align_recover_after_2_jitter_050_gate_0500():
    """Chain recovers on attempt 2 (jitter 0.5, gate 0.5): 1 gated rung(s) [0.65]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.5))
    assert result == 'ok'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [0.65]  # rung1


def test_align_recover_after_2_jitter_050_gate_1000():
    """Chain recovers on attempt 2 (jitter 0.5, gate 1.0): 1 gated rung(s) [1.15]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 1.0))
    assert result == 'ok'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [1.15]  # rung1


def test_align_recover_after_2_jitter_050_gate_2000():
    """Chain recovers on attempt 2 (jitter 0.5, gate 2.0): 1 gated rung(s) [2.15]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 2.0))
    assert result == 'ok'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [2.15]  # rung1


def test_align_recover_after_2_jitter_050_gate_4000():
    """Chain recovers on attempt 2 (jitter 0.5, gate 4.0): 1 gated rung(s) [4.15]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 4.0))
    assert result == 'ok'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [4.15]  # rung1


def test_align_recover_after_2_jitter_075_gate_0000():
    """Chain recovers on attempt 2 (jitter 0.75, gate 0.0): 1 gated rung(s) [0.175]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.0))
    assert result == 'ok'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [0.175]  # rung1


def test_align_recover_after_2_jitter_075_gate_0125():
    """Chain recovers on attempt 2 (jitter 0.75, gate 0.125): 1 gated rung(s) [0.3]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [0.3]  # rung1


def test_align_recover_after_2_jitter_075_gate_0250():
    """Chain recovers on attempt 2 (jitter 0.75, gate 0.25): 1 gated rung(s) [0.425]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.25))
    assert result == 'ok'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [0.425]  # rung1


def test_align_recover_after_2_jitter_075_gate_0500():
    """Chain recovers on attempt 2 (jitter 0.75, gate 0.5): 1 gated rung(s) [0.675]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.5))
    assert result == 'ok'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [0.675]  # rung1


def test_align_recover_after_2_jitter_075_gate_1000():
    """Chain recovers on attempt 2 (jitter 0.75, gate 1.0): 1 gated rung(s) [1.175]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 1.0))
    assert result == 'ok'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [1.175]  # rung1


def test_align_recover_after_2_jitter_075_gate_2000():
    """Chain recovers on attempt 2 (jitter 0.75, gate 2.0): 1 gated rung(s) [2.175]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 2.0))
    assert result == 'ok'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [2.175]  # rung1


def test_align_recover_after_2_jitter_075_gate_4000():
    """Chain recovers on attempt 2 (jitter 0.75, gate 4.0): 1 gated rung(s) [4.175]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 4.0))
    assert result == 'ok'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [4.175]  # rung1


def test_align_recover_after_2_jitter_100_gate_0000():
    """Chain recovers on attempt 2 (jitter 1.0, gate 0.0): 1 gated rung(s) [0.2]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.0))
    assert result == 'ok'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [0.2]  # rung1


def test_align_recover_after_2_jitter_100_gate_0125():
    """Chain recovers on attempt 2 (jitter 1.0, gate 0.125): 1 gated rung(s) [0.325]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [0.325]  # rung1


def test_align_recover_after_2_jitter_100_gate_0250():
    """Chain recovers on attempt 2 (jitter 1.0, gate 0.25): 1 gated rung(s) [0.45]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.25))
    assert result == 'ok'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [0.45]  # rung1


def test_align_recover_after_2_jitter_100_gate_0500():
    """Chain recovers on attempt 2 (jitter 1.0, gate 0.5): 1 gated rung(s) [0.7]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.5))
    assert result == 'ok'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [0.7]  # rung1


def test_align_recover_after_2_jitter_100_gate_1000():
    """Chain recovers on attempt 2 (jitter 1.0, gate 1.0): 1 gated rung(s) [1.2]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 1.0))
    assert result == 'ok'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [1.2]  # rung1


def test_align_recover_after_2_jitter_100_gate_2000():
    """Chain recovers on attempt 2 (jitter 1.0, gate 2.0): 1 gated rung(s) [2.2]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 2.0))
    assert result == 'ok'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [2.2]  # rung1


def test_align_recover_after_2_jitter_100_gate_4000():
    """Chain recovers on attempt 2 (jitter 1.0, gate 4.0): 1 gated rung(s) [4.2]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 4.0))
    assert result == 'ok'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [4.2]  # rung1


def test_align_recover_after_3_jitter_000_gate_0000():
    """Chain recovers on attempt 3 (jitter 0.0, gate 0.0): 2 gated rung(s) [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [0.1, 0.2]  # rung1 + rung2


def test_align_recover_after_3_jitter_000_gate_0125():
    """Chain recovers on attempt 3 (jitter 0.0, gate 0.125): 2 gated rung(s) [0.225, 0.325]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [0.225, 0.325]  # rung1 + rung2


def test_align_recover_after_3_jitter_000_gate_0250():
    """Chain recovers on attempt 3 (jitter 0.0, gate 0.25): 2 gated rung(s) [0.35, 0.45]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.25))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [0.35, 0.45]  # rung1 + rung2


def test_align_recover_after_3_jitter_000_gate_0500():
    """Chain recovers on attempt 3 (jitter 0.0, gate 0.5): 2 gated rung(s) [0.6, 0.7]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.5))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [0.6, 0.7]  # rung1 + rung2


def test_align_recover_after_3_jitter_000_gate_1000():
    """Chain recovers on attempt 3 (jitter 0.0, gate 1.0): 2 gated rung(s) [1.1, 1.2]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 1.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [1.1, 1.2]  # rung1 + rung2


def test_align_recover_after_3_jitter_000_gate_2000():
    """Chain recovers on attempt 3 (jitter 0.0, gate 2.0): 2 gated rung(s) [2.1, 2.2]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 2.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [2.1, 2.2]  # rung1 + rung2


def test_align_recover_after_3_jitter_000_gate_4000():
    """Chain recovers on attempt 3 (jitter 0.0, gate 4.0): 2 gated rung(s) [4.1, 4.2]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 4.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [4.1, 4.2]  # rung1 + rung2


def test_align_recover_after_3_jitter_025_gate_0000():
    """Chain recovers on attempt 3 (jitter 0.25, gate 0.0): 2 gated rung(s) [0.125, 0.25]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [0.125, 0.25]  # rung1 + rung2


def test_align_recover_after_3_jitter_025_gate_0125():
    """Chain recovers on attempt 3 (jitter 0.25, gate 0.125): 2 gated rung(s) [0.25, 0.375]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [0.25, 0.375]  # rung1 + rung2


def test_align_recover_after_3_jitter_025_gate_0250():
    """Chain recovers on attempt 3 (jitter 0.25, gate 0.25): 2 gated rung(s) [0.375, 0.5]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.25))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [0.375, 0.5]  # rung1 + rung2


def test_align_recover_after_3_jitter_025_gate_0500():
    """Chain recovers on attempt 3 (jitter 0.25, gate 0.5): 2 gated rung(s) [0.625, 0.75]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.5))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [0.625, 0.75]  # rung1 + rung2


def test_align_recover_after_3_jitter_025_gate_1000():
    """Chain recovers on attempt 3 (jitter 0.25, gate 1.0): 2 gated rung(s) [1.125, 1.25]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 1.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [1.125, 1.25]  # rung1 + rung2


def test_align_recover_after_3_jitter_025_gate_2000():
    """Chain recovers on attempt 3 (jitter 0.25, gate 2.0): 2 gated rung(s) [2.125, 2.25]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 2.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [2.125, 2.25]  # rung1 + rung2


def test_align_recover_after_3_jitter_025_gate_4000():
    """Chain recovers on attempt 3 (jitter 0.25, gate 4.0): 2 gated rung(s) [4.125, 4.25]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 4.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [4.125, 4.25]  # rung1 + rung2


def test_align_recover_after_3_jitter_050_gate_0000():
    """Chain recovers on attempt 3 (jitter 0.5, gate 0.0): 2 gated rung(s) [0.15, 0.3]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [0.15, 0.3]  # rung1 + rung2


def test_align_recover_after_3_jitter_050_gate_0125():
    """Chain recovers on attempt 3 (jitter 0.5, gate 0.125): 2 gated rung(s) [0.275, 0.425]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [0.275, 0.425]  # rung1 + rung2


def test_align_recover_after_3_jitter_050_gate_0250():
    """Chain recovers on attempt 3 (jitter 0.5, gate 0.25): 2 gated rung(s) [0.4, 0.55]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.25))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [0.4, 0.55]  # rung1 + rung2


def test_align_recover_after_3_jitter_050_gate_0500():
    """Chain recovers on attempt 3 (jitter 0.5, gate 0.5): 2 gated rung(s) [0.65, 0.8]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.5))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [0.65, 0.8]  # rung1 + rung2


def test_align_recover_after_3_jitter_050_gate_1000():
    """Chain recovers on attempt 3 (jitter 0.5, gate 1.0): 2 gated rung(s) [1.15, 1.3]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 1.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [1.15, 1.3]  # rung1 + rung2


def test_align_recover_after_3_jitter_050_gate_2000():
    """Chain recovers on attempt 3 (jitter 0.5, gate 2.0): 2 gated rung(s) [2.15, 2.3]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 2.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [2.15, 2.3]  # rung1 + rung2


def test_align_recover_after_3_jitter_050_gate_4000():
    """Chain recovers on attempt 3 (jitter 0.5, gate 4.0): 2 gated rung(s) [4.15, 4.3]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 4.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [4.15, 4.3]  # rung1 + rung2


def test_align_recover_after_3_jitter_075_gate_0000():
    """Chain recovers on attempt 3 (jitter 0.75, gate 0.0): 2 gated rung(s) [0.175, 0.35]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [0.175, 0.35]  # rung1 + rung2


def test_align_recover_after_3_jitter_075_gate_0125():
    """Chain recovers on attempt 3 (jitter 0.75, gate 0.125): 2 gated rung(s) [0.3, 0.475]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [0.3, 0.475]  # rung1 + rung2


def test_align_recover_after_3_jitter_075_gate_0250():
    """Chain recovers on attempt 3 (jitter 0.75, gate 0.25): 2 gated rung(s) [0.425, 0.6]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.25))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [0.425, 0.6]  # rung1 + rung2


def test_align_recover_after_3_jitter_075_gate_0500():
    """Chain recovers on attempt 3 (jitter 0.75, gate 0.5): 2 gated rung(s) [0.675, 0.85]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.5))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [0.675, 0.85]  # rung1 + rung2


def test_align_recover_after_3_jitter_075_gate_1000():
    """Chain recovers on attempt 3 (jitter 0.75, gate 1.0): 2 gated rung(s) [1.175, 1.35]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 1.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [1.175, 1.35]  # rung1 + rung2


def test_align_recover_after_3_jitter_075_gate_2000():
    """Chain recovers on attempt 3 (jitter 0.75, gate 2.0): 2 gated rung(s) [2.175, 2.35]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 2.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [2.175, 2.35]  # rung1 + rung2


def test_align_recover_after_3_jitter_075_gate_4000():
    """Chain recovers on attempt 3 (jitter 0.75, gate 4.0): 2 gated rung(s) [4.175, 4.35]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 4.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [4.175, 4.35]  # rung1 + rung2


def test_align_recover_after_3_jitter_100_gate_0000():
    """Chain recovers on attempt 3 (jitter 1.0, gate 0.0): 2 gated rung(s) [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [0.2, 0.4]  # rung1 + rung2


def test_align_recover_after_3_jitter_100_gate_0125():
    """Chain recovers on attempt 3 (jitter 1.0, gate 0.125): 2 gated rung(s) [0.325, 0.525]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [0.325, 0.525]  # rung1 + rung2


def test_align_recover_after_3_jitter_100_gate_0250():
    """Chain recovers on attempt 3 (jitter 1.0, gate 0.25): 2 gated rung(s) [0.45, 0.65]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.25))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [0.45, 0.65]  # rung1 + rung2


def test_align_recover_after_3_jitter_100_gate_0500():
    """Chain recovers on attempt 3 (jitter 1.0, gate 0.5): 2 gated rung(s) [0.7, 0.9]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.5))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [0.7, 0.9]  # rung1 + rung2


def test_align_recover_after_3_jitter_100_gate_1000():
    """Chain recovers on attempt 3 (jitter 1.0, gate 1.0): 2 gated rung(s) [1.2, 1.4]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 1.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [1.2, 1.4]  # rung1 + rung2


def test_align_recover_after_3_jitter_100_gate_2000():
    """Chain recovers on attempt 3 (jitter 1.0, gate 2.0): 2 gated rung(s) [2.2, 2.4]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 2.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [2.2, 2.4]  # rung1 + rung2


def test_align_recover_after_3_jitter_100_gate_4000():
    """Chain recovers on attempt 3 (jitter 1.0, gate 4.0): 2 gated rung(s) [4.2, 4.4]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 4.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [4.2, 4.4]  # rung1 + rung2


def test_align_recover_after_4_jitter_000_gate_0000():
    """Chain recovers on attempt 4 (jitter 0.0, gate 0.0): 3 gated rung(s) [0.1, 0.2, 0.4]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [0.1, 0.2, 0.4]  # rung1 + rung2 + rung3


def test_align_recover_after_4_jitter_000_gate_0125():
    """Chain recovers on attempt 4 (jitter 0.0, gate 0.125): 3 gated rung(s) [0.225, 0.325, 0.525]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [0.225, 0.325, 0.525]  # rung1 + rung2 + rung3


def test_align_recover_after_4_jitter_000_gate_0250():
    """Chain recovers on attempt 4 (jitter 0.0, gate 0.25): 3 gated rung(s) [0.35, 0.45, 0.65]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.25))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [0.35, 0.45, 0.65]  # rung1 + rung2 + rung3


def test_align_recover_after_4_jitter_000_gate_0500():
    """Chain recovers on attempt 4 (jitter 0.0, gate 0.5): 3 gated rung(s) [0.6, 0.7, 0.9]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.5))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [0.6, 0.7, 0.9]  # rung1 + rung2 + rung3


def test_align_recover_after_4_jitter_000_gate_1000():
    """Chain recovers on attempt 4 (jitter 0.0, gate 1.0): 3 gated rung(s) [1.1, 1.2, 1.4]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 1.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [1.1, 1.2, 1.4]  # rung1 + rung2 + rung3


def test_align_recover_after_4_jitter_000_gate_2000():
    """Chain recovers on attempt 4 (jitter 0.0, gate 2.0): 3 gated rung(s) [2.1, 2.2, 2.4]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 2.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [2.1, 2.2, 2.4]  # rung1 + rung2 + rung3


def test_align_recover_after_4_jitter_000_gate_4000():
    """Chain recovers on attempt 4 (jitter 0.0, gate 4.0): 3 gated rung(s) [4.1, 4.2, 4.4]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 4.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [4.1, 4.2, 4.4]  # rung1 + rung2 + rung3


def test_align_recover_after_4_jitter_025_gate_0000():
    """Chain recovers on attempt 4 (jitter 0.25, gate 0.0): 3 gated rung(s) [0.125, 0.25, 0.5]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [0.125, 0.25, 0.5]  # rung1 + rung2 + rung3


def test_align_recover_after_4_jitter_025_gate_0125():
    """Chain recovers on attempt 4 (jitter 0.25, gate 0.125): 3 gated rung(s) [0.25, 0.375, 0.625]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [0.25, 0.375, 0.625]  # rung1 + rung2 + rung3


def test_align_recover_after_4_jitter_025_gate_0250():
    """Chain recovers on attempt 4 (jitter 0.25, gate 0.25): 3 gated rung(s) [0.375, 0.5, 0.75]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.25))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [0.375, 0.5, 0.75]  # rung1 + rung2 + rung3


def test_align_recover_after_4_jitter_025_gate_0500():
    """Chain recovers on attempt 4 (jitter 0.25, gate 0.5): 3 gated rung(s) [0.625, 0.75, 1.0]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.5))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [0.625, 0.75, 1.0]  # rung1 + rung2 + rung3


def test_align_recover_after_4_jitter_025_gate_1000():
    """Chain recovers on attempt 4 (jitter 0.25, gate 1.0): 3 gated rung(s) [1.125, 1.25, 1.5]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 1.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [1.125, 1.25, 1.5]  # rung1 + rung2 + rung3


def test_align_recover_after_4_jitter_025_gate_2000():
    """Chain recovers on attempt 4 (jitter 0.25, gate 2.0): 3 gated rung(s) [2.125, 2.25, 2.5]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 2.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [2.125, 2.25, 2.5]  # rung1 + rung2 + rung3


def test_align_recover_after_4_jitter_025_gate_4000():
    """Chain recovers on attempt 4 (jitter 0.25, gate 4.0): 3 gated rung(s) [4.125, 4.25, 4.5]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 4.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [4.125, 4.25, 4.5]  # rung1 + rung2 + rung3


def test_align_recover_after_4_jitter_050_gate_0000():
    """Chain recovers on attempt 4 (jitter 0.5, gate 0.0): 3 gated rung(s) [0.15, 0.3, 0.6]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [0.15, 0.3, 0.6]  # rung1 + rung2 + rung3


def test_align_recover_after_4_jitter_050_gate_0125():
    """Chain recovers on attempt 4 (jitter 0.5, gate 0.125): 3 gated rung(s) [0.275, 0.425, 0.725]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [0.275, 0.425, 0.725]  # rung1 + rung2 + rung3


def test_align_recover_after_4_jitter_050_gate_0250():
    """Chain recovers on attempt 4 (jitter 0.5, gate 0.25): 3 gated rung(s) [0.4, 0.55, 0.85]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.25))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [0.4, 0.55, 0.85]  # rung1 + rung2 + rung3


def test_align_recover_after_4_jitter_050_gate_0500():
    """Chain recovers on attempt 4 (jitter 0.5, gate 0.5): 3 gated rung(s) [0.65, 0.8, 1.1]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.5))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [0.65, 0.8, 1.1]  # rung1 + rung2 + rung3


def test_align_recover_after_4_jitter_050_gate_1000():
    """Chain recovers on attempt 4 (jitter 0.5, gate 1.0): 3 gated rung(s) [1.15, 1.3, 1.6]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 1.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [1.15, 1.3, 1.6]  # rung1 + rung2 + rung3


def test_align_recover_after_4_jitter_050_gate_2000():
    """Chain recovers on attempt 4 (jitter 0.5, gate 2.0): 3 gated rung(s) [2.15, 2.3, 2.6]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 2.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [2.15, 2.3, 2.6]  # rung1 + rung2 + rung3


def test_align_recover_after_4_jitter_050_gate_4000():
    """Chain recovers on attempt 4 (jitter 0.5, gate 4.0): 3 gated rung(s) [4.15, 4.3, 4.6]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 4.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [4.15, 4.3, 4.6]  # rung1 + rung2 + rung3


def test_align_recover_after_4_jitter_075_gate_0000():
    """Chain recovers on attempt 4 (jitter 0.75, gate 0.0): 3 gated rung(s) [0.175, 0.35, 0.7]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [0.175, 0.35, 0.7]  # rung1 + rung2 + rung3


def test_align_recover_after_4_jitter_075_gate_0125():
    """Chain recovers on attempt 4 (jitter 0.75, gate 0.125): 3 gated rung(s) [0.3, 0.475, 0.825]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [0.3, 0.475, 0.825]  # rung1 + rung2 + rung3


def test_align_recover_after_4_jitter_075_gate_0250():
    """Chain recovers on attempt 4 (jitter 0.75, gate 0.25): 3 gated rung(s) [0.425, 0.6, 0.95]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.25))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [0.425, 0.6, 0.95]  # rung1 + rung2 + rung3


def test_align_recover_after_4_jitter_075_gate_0500():
    """Chain recovers on attempt 4 (jitter 0.75, gate 0.5): 3 gated rung(s) [0.675, 0.85, 1.2]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.5))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [0.675, 0.85, 1.2]  # rung1 + rung2 + rung3


def test_align_recover_after_4_jitter_075_gate_1000():
    """Chain recovers on attempt 4 (jitter 0.75, gate 1.0): 3 gated rung(s) [1.175, 1.35, 1.7]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 1.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [1.175, 1.35, 1.7]  # rung1 + rung2 + rung3


def test_align_recover_after_4_jitter_075_gate_2000():
    """Chain recovers on attempt 4 (jitter 0.75, gate 2.0): 3 gated rung(s) [2.175, 2.35, 2.7]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 2.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [2.175, 2.35, 2.7]  # rung1 + rung2 + rung3


def test_align_recover_after_4_jitter_075_gate_4000():
    """Chain recovers on attempt 4 (jitter 0.75, gate 4.0): 3 gated rung(s) [4.175, 4.35, 4.7]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 4.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [4.175, 4.35, 4.7]  # rung1 + rung2 + rung3


def test_align_recover_after_4_jitter_100_gate_0000():
    """Chain recovers on attempt 4 (jitter 1.0, gate 0.0): 3 gated rung(s) [0.2, 0.4, 0.8]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [0.2, 0.4, 0.8]  # rung1 + rung2 + rung3


def test_align_recover_after_4_jitter_100_gate_0125():
    """Chain recovers on attempt 4 (jitter 1.0, gate 0.125): 3 gated rung(s) [0.325, 0.525, 0.925]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [0.325, 0.525, 0.925]  # rung1 + rung2 + rung3


def test_align_recover_after_4_jitter_100_gate_0250():
    """Chain recovers on attempt 4 (jitter 1.0, gate 0.25): 3 gated rung(s) [0.45, 0.65, 1.05]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.25))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [0.45, 0.65, 1.05]  # rung1 + rung2 + rung3


def test_align_recover_after_4_jitter_100_gate_0500():
    """Chain recovers on attempt 4 (jitter 1.0, gate 0.5): 3 gated rung(s) [0.7, 0.9, 1.3]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.5))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [0.7, 0.9, 1.3]  # rung1 + rung2 + rung3


def test_align_recover_after_4_jitter_100_gate_1000():
    """Chain recovers on attempt 4 (jitter 1.0, gate 1.0): 3 gated rung(s) [1.2, 1.4, 1.8]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 1.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [1.2, 1.4, 1.8]  # rung1 + rung2 + rung3


def test_align_recover_after_4_jitter_100_gate_2000():
    """Chain recovers on attempt 4 (jitter 1.0, gate 2.0): 3 gated rung(s) [2.2, 2.4, 2.8]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 2.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [2.2, 2.4, 2.8]  # rung1 + rung2 + rung3


def test_align_recover_after_4_jitter_100_gate_4000():
    """Chain recovers on attempt 4 (jitter 1.0, gate 4.0): 3 gated rung(s) [4.2, 4.4, 4.8]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 4.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [4.2, 4.4, 4.8]  # rung1 + rung2 + rung3


def test_align_recover_after_5_jitter_000_gate_0000():
    """Chain recovers on attempt 5 (jitter 0.0, gate 0.0): 4 gated rung(s) [0.1, 0.2, 0.4, 0.8]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [0.1, 0.2, 0.4, 0.8]  # rung1 + rung2 + rung3 + rung4


def test_align_recover_after_5_jitter_000_gate_0125():
    """Chain recovers on attempt 5 (jitter 0.0, gate 0.125): 4 gated rung(s) [0.225, 0.325, 0.525, 0.925]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [0.225, 0.325, 0.525, 0.925]  # rung1 + rung2 + rung3 + rung4


def test_align_recover_after_5_jitter_000_gate_0250():
    """Chain recovers on attempt 5 (jitter 0.0, gate 0.25): 4 gated rung(s) [0.35, 0.45, 0.65, 1.05]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.25))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [0.35, 0.45, 0.65, 1.05]  # rung1 + rung2 + rung3 + rung4


def test_align_recover_after_5_jitter_000_gate_0500():
    """Chain recovers on attempt 5 (jitter 0.0, gate 0.5): 4 gated rung(s) [0.6, 0.7, 0.9, 1.3]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.5))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [0.6, 0.7, 0.9, 1.3]  # rung1 + rung2 + rung3 + rung4


def test_align_recover_after_5_jitter_000_gate_1000():
    """Chain recovers on attempt 5 (jitter 0.0, gate 1.0): 4 gated rung(s) [1.1, 1.2, 1.4, 1.8]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 1.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [1.1, 1.2, 1.4, 1.8]  # rung1 + rung2 + rung3 + rung4


def test_align_recover_after_5_jitter_000_gate_2000():
    """Chain recovers on attempt 5 (jitter 0.0, gate 2.0): 4 gated rung(s) [2.1, 2.2, 2.4, 2.8]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 2.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [2.1, 2.2, 2.4, 2.8]  # rung1 + rung2 + rung3 + rung4


def test_align_recover_after_5_jitter_000_gate_4000():
    """Chain recovers on attempt 5 (jitter 0.0, gate 4.0): 4 gated rung(s) [4.1, 4.2, 4.4, 4.8]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 4.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [4.1, 4.2, 4.4, 4.8]  # rung1 + rung2 + rung3 + rung4


def test_align_recover_after_5_jitter_025_gate_0000():
    """Chain recovers on attempt 5 (jitter 0.25, gate 0.0): 4 gated rung(s) [0.125, 0.25, 0.5, 1.0]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0]  # rung1 + rung2 + rung3 + rung4


def test_align_recover_after_5_jitter_025_gate_0125():
    """Chain recovers on attempt 5 (jitter 0.25, gate 0.125): 4 gated rung(s) [0.25, 0.375, 0.625, 1.125]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [0.25, 0.375, 0.625, 1.125]  # rung1 + rung2 + rung3 + rung4


def test_align_recover_after_5_jitter_025_gate_0250():
    """Chain recovers on attempt 5 (jitter 0.25, gate 0.25): 4 gated rung(s) [0.375, 0.5, 0.75, 1.25]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.25))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [0.375, 0.5, 0.75, 1.25]  # rung1 + rung2 + rung3 + rung4


def test_align_recover_after_5_jitter_025_gate_0500():
    """Chain recovers on attempt 5 (jitter 0.25, gate 0.5): 4 gated rung(s) [0.625, 0.75, 1.0, 1.5]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.5))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [0.625, 0.75, 1.0, 1.5]  # rung1 + rung2 + rung3 + rung4


def test_align_recover_after_5_jitter_025_gate_1000():
    """Chain recovers on attempt 5 (jitter 0.25, gate 1.0): 4 gated rung(s) [1.125, 1.25, 1.5, 2.0]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 1.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [1.125, 1.25, 1.5, 2.0]  # rung1 + rung2 + rung3 + rung4


def test_align_recover_after_5_jitter_025_gate_2000():
    """Chain recovers on attempt 5 (jitter 0.25, gate 2.0): 4 gated rung(s) [2.125, 2.25, 2.5, 3.0]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 2.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [2.125, 2.25, 2.5, 3.0]  # rung1 + rung2 + rung3 + rung4


def test_align_recover_after_5_jitter_025_gate_4000():
    """Chain recovers on attempt 5 (jitter 0.25, gate 4.0): 4 gated rung(s) [4.125, 4.25, 4.5, 5.0]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 4.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [4.125, 4.25, 4.5, 5.0]  # rung1 + rung2 + rung3 + rung4


def test_align_recover_after_5_jitter_050_gate_0000():
    """Chain recovers on attempt 5 (jitter 0.5, gate 0.0): 4 gated rung(s) [0.15, 0.3, 0.6, 1.2]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [0.15, 0.3, 0.6, 1.2]  # rung1 + rung2 + rung3 + rung4


def test_align_recover_after_5_jitter_050_gate_0125():
    """Chain recovers on attempt 5 (jitter 0.5, gate 0.125): 4 gated rung(s) [0.275, 0.425, 0.725, 1.325]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [0.275, 0.425, 0.725, 1.325]  # rung1 + rung2 + rung3 + rung4


def test_align_recover_after_5_jitter_050_gate_0250():
    """Chain recovers on attempt 5 (jitter 0.5, gate 0.25): 4 gated rung(s) [0.4, 0.55, 0.85, 1.45]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.25))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [0.4, 0.55, 0.85, 1.45]  # rung1 + rung2 + rung3 + rung4


def test_align_recover_after_5_jitter_050_gate_0500():
    """Chain recovers on attempt 5 (jitter 0.5, gate 0.5): 4 gated rung(s) [0.65, 0.8, 1.1, 1.7]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.5))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [0.65, 0.8, 1.1, 1.7]  # rung1 + rung2 + rung3 + rung4


def test_align_recover_after_5_jitter_050_gate_1000():
    """Chain recovers on attempt 5 (jitter 0.5, gate 1.0): 4 gated rung(s) [1.15, 1.3, 1.6, 2.2]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 1.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [1.15, 1.3, 1.6, 2.2]  # rung1 + rung2 + rung3 + rung4


def test_align_recover_after_5_jitter_050_gate_2000():
    """Chain recovers on attempt 5 (jitter 0.5, gate 2.0): 4 gated rung(s) [2.15, 2.3, 2.6, 3.2]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 2.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [2.15, 2.3, 2.6, 3.2]  # rung1 + rung2 + rung3 + rung4


def test_align_recover_after_5_jitter_050_gate_4000():
    """Chain recovers on attempt 5 (jitter 0.5, gate 4.0): 4 gated rung(s) [4.15, 4.3, 4.6, 5.2]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 4.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [4.15, 4.3, 4.6, 5.2]  # rung1 + rung2 + rung3 + rung4


def test_align_recover_after_5_jitter_075_gate_0000():
    """Chain recovers on attempt 5 (jitter 0.75, gate 0.0): 4 gated rung(s) [0.175, 0.35, 0.7, 1.4]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [0.175, 0.35, 0.7, 1.4]  # rung1 + rung2 + rung3 + rung4


def test_align_recover_after_5_jitter_075_gate_0125():
    """Chain recovers on attempt 5 (jitter 0.75, gate 0.125): 4 gated rung(s) [0.3, 0.475, 0.825, 1.525]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [0.3, 0.475, 0.825, 1.525]  # rung1 + rung2 + rung3 + rung4


def test_align_recover_after_5_jitter_075_gate_0250():
    """Chain recovers on attempt 5 (jitter 0.75, gate 0.25): 4 gated rung(s) [0.425, 0.6, 0.95, 1.65]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.25))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [0.425, 0.6, 0.95, 1.65]  # rung1 + rung2 + rung3 + rung4


def test_align_recover_after_5_jitter_075_gate_0500():
    """Chain recovers on attempt 5 (jitter 0.75, gate 0.5): 4 gated rung(s) [0.675, 0.85, 1.2, 1.9]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.5))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [0.675, 0.85, 1.2, 1.9]  # rung1 + rung2 + rung3 + rung4


def test_align_recover_after_5_jitter_075_gate_1000():
    """Chain recovers on attempt 5 (jitter 0.75, gate 1.0): 4 gated rung(s) [1.175, 1.35, 1.7, 2.4]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 1.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [1.175, 1.35, 1.7, 2.4]  # rung1 + rung2 + rung3 + rung4


def test_align_recover_after_5_jitter_075_gate_2000():
    """Chain recovers on attempt 5 (jitter 0.75, gate 2.0): 4 gated rung(s) [2.175, 2.35, 2.7, 3.4]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 2.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [2.175, 2.35, 2.7, 3.4]  # rung1 + rung2 + rung3 + rung4


def test_align_recover_after_5_jitter_075_gate_4000():
    """Chain recovers on attempt 5 (jitter 0.75, gate 4.0): 4 gated rung(s) [4.175, 4.35, 4.7, 5.4]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 4.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [4.175, 4.35, 4.7, 5.4]  # rung1 + rung2 + rung3 + rung4


def test_align_recover_after_5_jitter_100_gate_0000():
    """Chain recovers on attempt 5 (jitter 1.0, gate 0.0): 4 gated rung(s) [0.2, 0.4, 0.8, 1.6]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [0.2, 0.4, 0.8, 1.6]  # rung1 + rung2 + rung3 + rung4


def test_align_recover_after_5_jitter_100_gate_0125():
    """Chain recovers on attempt 5 (jitter 1.0, gate 0.125): 4 gated rung(s) [0.325, 0.525, 0.925, 1.725]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [0.325, 0.525, 0.925, 1.725]  # rung1 + rung2 + rung3 + rung4


def test_align_recover_after_5_jitter_100_gate_0250():
    """Chain recovers on attempt 5 (jitter 1.0, gate 0.25): 4 gated rung(s) [0.45, 0.65, 1.05, 1.85]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.25))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [0.45, 0.65, 1.05, 1.85]  # rung1 + rung2 + rung3 + rung4


def test_align_recover_after_5_jitter_100_gate_0500():
    """Chain recovers on attempt 5 (jitter 1.0, gate 0.5): 4 gated rung(s) [0.7, 0.9, 1.3, 2.1]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.5))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [0.7, 0.9, 1.3, 2.1]  # rung1 + rung2 + rung3 + rung4


def test_align_recover_after_5_jitter_100_gate_1000():
    """Chain recovers on attempt 5 (jitter 1.0, gate 1.0): 4 gated rung(s) [1.2, 1.4, 1.8, 2.6]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 1.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [1.2, 1.4, 1.8, 2.6]  # rung1 + rung2 + rung3 + rung4


def test_align_recover_after_5_jitter_100_gate_2000():
    """Chain recovers on attempt 5 (jitter 1.0, gate 2.0): 4 gated rung(s) [2.2, 2.4, 2.8, 3.6]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 2.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [2.2, 2.4, 2.8, 3.6]  # rung1 + rung2 + rung3 + rung4


def test_align_recover_after_5_jitter_100_gate_4000():
    """Chain recovers on attempt 5 (jitter 1.0, gate 4.0): 4 gated rung(s) [4.2, 4.4, 4.8, 5.6]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 4.0))
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [4.2, 4.4, 4.8, 5.6]  # rung1 + rung2 + rung3 + rung4


def test_align_recover_after_6_jitter_000_gate_0000():
    """Chain recovers on attempt 6 (jitter 0.0, gate 0.0): 5 gated rung(s) [0.1, 0.2, 0.4, 0.8, 1.6]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.0), max_attempts=6)
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [0.1, 0.2, 0.4, 0.8, 1.6]  # rung1 + rung2 + rung3 + rung4 + rung5


def test_align_recover_after_6_jitter_000_gate_0125():
    """Chain recovers on attempt 6 (jitter 0.0, gate 0.125): 5 gated rung(s) [0.225, 0.325, 0.525, 0.925, 1.725]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.125), max_attempts=6)
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [0.225, 0.325, 0.525, 0.925, 1.725]  # rung1 + rung2 + rung3 + rung4 + rung5


def test_align_recover_after_6_jitter_000_gate_0250():
    """Chain recovers on attempt 6 (jitter 0.0, gate 0.25): 5 gated rung(s) [0.35, 0.45, 0.65, 1.05, 1.85]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.25), max_attempts=6)
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [0.35, 0.45, 0.65, 1.05, 1.85]  # rung1 + rung2 + rung3 + rung4 + rung5


def test_align_recover_after_6_jitter_000_gate_0500():
    """Chain recovers on attempt 6 (jitter 0.0, gate 0.5): 5 gated rung(s) [0.6, 0.7, 0.9, 1.3, 2.1]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.5), max_attempts=6)
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [0.6, 0.7, 0.9, 1.3, 2.1]  # rung1 + rung2 + rung3 + rung4 + rung5


def test_align_recover_after_6_jitter_000_gate_1000():
    """Chain recovers on attempt 6 (jitter 0.0, gate 1.0): 5 gated rung(s) [1.1, 1.2, 1.4, 1.8, 2.6]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 1.0), max_attempts=6)
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [1.1, 1.2, 1.4, 1.8, 2.6]  # rung1 + rung2 + rung3 + rung4 + rung5


def test_align_recover_after_6_jitter_000_gate_2000():
    """Chain recovers on attempt 6 (jitter 0.0, gate 2.0): 5 gated rung(s) [2.1, 2.2, 2.4, 2.8, 3.6]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 2.0), max_attempts=6)
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [2.1, 2.2, 2.4, 2.8, 3.6]  # rung1 + rung2 + rung3 + rung4 + rung5


def test_align_recover_after_6_jitter_000_gate_4000():
    """Chain recovers on attempt 6 (jitter 0.0, gate 4.0): 5 gated rung(s) [4.1, 4.2, 4.4, 4.8, 5.6]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 4.0), max_attempts=6)
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [4.1, 4.2, 4.4, 4.8, 5.6]  # rung1 + rung2 + rung3 + rung4 + rung5


def test_align_recover_after_6_jitter_025_gate_0000():
    """Chain recovers on attempt 6 (jitter 0.25, gate 0.0): 5 gated rung(s) [0.125, 0.25, 0.5, 1.0, 2.0]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.0), max_attempts=6)
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [0.125, 0.25, 0.5, 1.0, 2.0]  # rung1 + rung2 + rung3 + rung4 + rung5


def test_align_recover_after_6_jitter_025_gate_0125():
    """Chain recovers on attempt 6 (jitter 0.25, gate 0.125): 5 gated rung(s) [0.25, 0.375, 0.625, 1.125, 2.125]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.125), max_attempts=6)
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [0.25, 0.375, 0.625, 1.125, 2.125]  # rung1 + rung2 + rung3 + rung4 + rung5


def test_align_recover_after_6_jitter_025_gate_0250():
    """Chain recovers on attempt 6 (jitter 0.25, gate 0.25): 5 gated rung(s) [0.375, 0.5, 0.75, 1.25, 2.25]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.25), max_attempts=6)
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [0.375, 0.5, 0.75, 1.25, 2.25]  # rung1 + rung2 + rung3 + rung4 + rung5


def test_align_recover_after_6_jitter_025_gate_0500():
    """Chain recovers on attempt 6 (jitter 0.25, gate 0.5): 5 gated rung(s) [0.625, 0.75, 1.0, 1.5, 2.5]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.5), max_attempts=6)
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [0.625, 0.75, 1.0, 1.5, 2.5]  # rung1 + rung2 + rung3 + rung4 + rung5


def test_align_recover_after_6_jitter_025_gate_1000():
    """Chain recovers on attempt 6 (jitter 0.25, gate 1.0): 5 gated rung(s) [1.125, 1.25, 1.5, 2.0, 3.0]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 1.0), max_attempts=6)
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [1.125, 1.25, 1.5, 2.0, 3.0]  # rung1 + rung2 + rung3 + rung4 + rung5


def test_align_recover_after_6_jitter_025_gate_2000():
    """Chain recovers on attempt 6 (jitter 0.25, gate 2.0): 5 gated rung(s) [2.125, 2.25, 2.5, 3.0, 4.0]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 2.0), max_attempts=6)
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [2.125, 2.25, 2.5, 3.0, 4.0]  # rung1 + rung2 + rung3 + rung4 + rung5


def test_align_recover_after_6_jitter_025_gate_4000():
    """Chain recovers on attempt 6 (jitter 0.25, gate 4.0): 5 gated rung(s) [4.125, 4.25, 4.5, 5.0, 6.0]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 4.0), max_attempts=6)
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [4.125, 4.25, 4.5, 5.0, 6.0]  # rung1 + rung2 + rung3 + rung4 + rung5


def test_align_recover_after_6_jitter_050_gate_0000():
    """Chain recovers on attempt 6 (jitter 0.5, gate 0.0): 5 gated rung(s) [0.15, 0.3, 0.6, 1.2, 2.4]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.0), max_attempts=6)
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [0.15, 0.3, 0.6, 1.2, 2.4]  # rung1 + rung2 + rung3 + rung4 + rung5


def test_align_recover_after_6_jitter_050_gate_0125():
    """Chain recovers on attempt 6 (jitter 0.5, gate 0.125): 5 gated rung(s) [0.275, 0.425, 0.725, 1.325, 2.525]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.125), max_attempts=6)
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [0.275, 0.425, 0.725, 1.325, 2.525]  # rung1 + rung2 + rung3 + rung4 + rung5


def test_align_recover_after_6_jitter_050_gate_0250():
    """Chain recovers on attempt 6 (jitter 0.5, gate 0.25): 5 gated rung(s) [0.4, 0.55, 0.85, 1.45, 2.65]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.25), max_attempts=6)
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [0.4, 0.55, 0.85, 1.45, 2.65]  # rung1 + rung2 + rung3 + rung4 + rung5


def test_align_recover_after_6_jitter_050_gate_0500():
    """Chain recovers on attempt 6 (jitter 0.5, gate 0.5): 5 gated rung(s) [0.65, 0.8, 1.1, 1.7, 2.9]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.5), max_attempts=6)
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [0.65, 0.8, 1.1, 1.7, 2.9]  # rung1 + rung2 + rung3 + rung4 + rung5


def test_align_recover_after_6_jitter_050_gate_1000():
    """Chain recovers on attempt 6 (jitter 0.5, gate 1.0): 5 gated rung(s) [1.15, 1.3, 1.6, 2.2, 3.4]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 1.0), max_attempts=6)
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [1.15, 1.3, 1.6, 2.2, 3.4]  # rung1 + rung2 + rung3 + rung4 + rung5


def test_align_recover_after_6_jitter_050_gate_2000():
    """Chain recovers on attempt 6 (jitter 0.5, gate 2.0): 5 gated rung(s) [2.15, 2.3, 2.6, 3.2, 4.4]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 2.0), max_attempts=6)
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [2.15, 2.3, 2.6, 3.2, 4.4]  # rung1 + rung2 + rung3 + rung4 + rung5


def test_align_recover_after_6_jitter_050_gate_4000():
    """Chain recovers on attempt 6 (jitter 0.5, gate 4.0): 5 gated rung(s) [4.15, 4.3, 4.6, 5.2, 6.4]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 4.0), max_attempts=6)
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [4.15, 4.3, 4.6, 5.2, 6.4]  # rung1 + rung2 + rung3 + rung4 + rung5


def test_align_recover_after_6_jitter_075_gate_0000():
    """Chain recovers on attempt 6 (jitter 0.75, gate 0.0): 5 gated rung(s) [0.175, 0.35, 0.7, 1.4, 2.8]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.0), max_attempts=6)
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [0.175, 0.35, 0.7, 1.4, 2.8]  # rung1 + rung2 + rung3 + rung4 + rung5


def test_align_recover_after_6_jitter_075_gate_0125():
    """Chain recovers on attempt 6 (jitter 0.75, gate 0.125): 5 gated rung(s) [0.3, 0.475, 0.825, 1.525, 2.925]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.125), max_attempts=6)
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [0.3, 0.475, 0.825, 1.525, 2.925]  # rung1 + rung2 + rung3 + rung4 + rung5


def test_align_recover_after_6_jitter_075_gate_0250():
    """Chain recovers on attempt 6 (jitter 0.75, gate 0.25): 5 gated rung(s) [0.425, 0.6, 0.95, 1.65, 3.05]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.25), max_attempts=6)
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [0.425, 0.6, 0.95, 1.65, 3.05]  # rung1 + rung2 + rung3 + rung4 + rung5


def test_align_recover_after_6_jitter_075_gate_0500():
    """Chain recovers on attempt 6 (jitter 0.75, gate 0.5): 5 gated rung(s) [0.675, 0.85, 1.2, 1.9, 3.3]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.5), max_attempts=6)
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [0.675, 0.85, 1.2, 1.9, 3.3]  # rung1 + rung2 + rung3 + rung4 + rung5


def test_align_recover_after_6_jitter_075_gate_1000():
    """Chain recovers on attempt 6 (jitter 0.75, gate 1.0): 5 gated rung(s) [1.175, 1.35, 1.7, 2.4, 3.8]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 1.0), max_attempts=6)
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [1.175, 1.35, 1.7, 2.4, 3.8]  # rung1 + rung2 + rung3 + rung4 + rung5


def test_align_recover_after_6_jitter_075_gate_2000():
    """Chain recovers on attempt 6 (jitter 0.75, gate 2.0): 5 gated rung(s) [2.175, 2.35, 2.7, 3.4, 4.8]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 2.0), max_attempts=6)
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [2.175, 2.35, 2.7, 3.4, 4.8]  # rung1 + rung2 + rung3 + rung4 + rung5


def test_align_recover_after_6_jitter_075_gate_4000():
    """Chain recovers on attempt 6 (jitter 0.75, gate 4.0): 5 gated rung(s) [4.175, 4.35, 4.7, 5.4, 6.8]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 4.0), max_attempts=6)
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [4.175, 4.35, 4.7, 5.4, 6.8]  # rung1 + rung2 + rung3 + rung4 + rung5


def test_align_recover_after_6_jitter_100_gate_0000():
    """Chain recovers on attempt 6 (jitter 1.0, gate 0.0): 5 gated rung(s) [0.2, 0.4, 0.8, 1.6, 3.2]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.0), max_attempts=6)
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [0.2, 0.4, 0.8, 1.6, 3.2]  # rung1 + rung2 + rung3 + rung4 + rung5


def test_align_recover_after_6_jitter_100_gate_0125():
    """Chain recovers on attempt 6 (jitter 1.0, gate 0.125): 5 gated rung(s) [0.325, 0.525, 0.925, 1.725, 3.325]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.125), max_attempts=6)
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [0.325, 0.525, 0.925, 1.725, 3.325]  # rung1 + rung2 + rung3 + rung4 + rung5


def test_align_recover_after_6_jitter_100_gate_0250():
    """Chain recovers on attempt 6 (jitter 1.0, gate 0.25): 5 gated rung(s) [0.45, 0.65, 1.05, 1.85, 3.45]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.25), max_attempts=6)
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [0.45, 0.65, 1.05, 1.85, 3.45]  # rung1 + rung2 + rung3 + rung4 + rung5


def test_align_recover_after_6_jitter_100_gate_0500():
    """Chain recovers on attempt 6 (jitter 1.0, gate 0.5): 5 gated rung(s) [0.7, 0.9, 1.3, 2.1, 3.7]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.5), max_attempts=6)
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [0.7, 0.9, 1.3, 2.1, 3.7]  # rung1 + rung2 + rung3 + rung4 + rung5


def test_align_recover_after_6_jitter_100_gate_1000():
    """Chain recovers on attempt 6 (jitter 1.0, gate 1.0): 5 gated rung(s) [1.2, 1.4, 1.8, 2.6, 4.2]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 1.0), max_attempts=6)
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [1.2, 1.4, 1.8, 2.6, 4.2]  # rung1 + rung2 + rung3 + rung4 + rung5


def test_align_recover_after_6_jitter_100_gate_2000():
    """Chain recovers on attempt 6 (jitter 1.0, gate 2.0): 5 gated rung(s) [2.2, 2.4, 2.8, 3.6, 5.2]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 2.0), max_attempts=6)
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [2.2, 2.4, 2.8, 3.6, 5.2]  # rung1 + rung2 + rung3 + rung4 + rung5


def test_align_recover_after_6_jitter_100_gate_4000():
    """Chain recovers on attempt 6 (jitter 1.0, gate 4.0): 5 gated rung(s) [4.2, 4.4, 4.8, 5.6, 7.2]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 4.0), max_attempts=6)
    assert result == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [4.2, 4.4, 4.8, 5.6, 7.2]  # rung1 + rung2 + rung3 + rung4 + rung5


def test_align_exhaust_budget_1_jitter_000_gate_0000():
    """Exhaustion at 1 attempts (jitter 0.0, gate 0.0): 0 gated rung(s) [], gate skipped on the dying attempt."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.0), max_attempts=1)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == []
    assert clock.sleeps == []


def test_align_exhaust_budget_1_jitter_000_gate_0250():
    """Exhaustion at 1 attempts (jitter 0.0, gate 0.25): 0 gated rung(s) [], gate skipped on the dying attempt."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.25), max_attempts=1)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == []
    assert clock.sleeps == []


def test_align_exhaust_budget_1_jitter_000_gate_4000():
    """Exhaustion at 1 attempts (jitter 0.0, gate 4.0): 0 gated rung(s) [], gate skipped on the dying attempt."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 4.0), max_attempts=1)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == []
    assert clock.sleeps == []


def test_align_exhaust_budget_1_jitter_100_gate_0000():
    """Exhaustion at 1 attempts (jitter 1.0, gate 0.0): 0 gated rung(s) [], gate skipped on the dying attempt."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.0), max_attempts=1)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == []
    assert clock.sleeps == []


def test_align_exhaust_budget_1_jitter_100_gate_0250():
    """Exhaustion at 1 attempts (jitter 1.0, gate 0.25): 0 gated rung(s) [], gate skipped on the dying attempt."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.25), max_attempts=1)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == []
    assert clock.sleeps == []


def test_align_exhaust_budget_1_jitter_100_gate_4000():
    """Exhaustion at 1 attempts (jitter 1.0, gate 4.0): 0 gated rung(s) [], gate skipped on the dying attempt."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 4.0), max_attempts=1)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == []
    assert clock.sleeps == []


def test_align_exhaust_budget_2_jitter_000_gate_0000():
    """Exhaustion at 2 attempts (jitter 0.0, gate 0.0): 1 gated rung(s) [0.1], gate skipped on the dying attempt."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.0), max_attempts=2)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [0.1]


def test_align_exhaust_budget_2_jitter_000_gate_0250():
    """Exhaustion at 2 attempts (jitter 0.0, gate 0.25): 1 gated rung(s) [0.35], gate skipped on the dying attempt."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.25), max_attempts=2)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [0.35]


def test_align_exhaust_budget_2_jitter_000_gate_4000():
    """Exhaustion at 2 attempts (jitter 0.0, gate 4.0): 1 gated rung(s) [4.1], gate skipped on the dying attempt."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 4.0), max_attempts=2)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [4.1]


def test_align_exhaust_budget_2_jitter_100_gate_0000():
    """Exhaustion at 2 attempts (jitter 1.0, gate 0.0): 1 gated rung(s) [0.2], gate skipped on the dying attempt."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.0), max_attempts=2)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [0.2]


def test_align_exhaust_budget_2_jitter_100_gate_0250():
    """Exhaustion at 2 attempts (jitter 1.0, gate 0.25): 1 gated rung(s) [0.45], gate skipped on the dying attempt."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.25), max_attempts=2)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [0.45]


def test_align_exhaust_budget_2_jitter_100_gate_4000():
    """Exhaustion at 2 attempts (jitter 1.0, gate 4.0): 1 gated rung(s) [4.2], gate skipped on the dying attempt."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 4.0), max_attempts=2)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == [1]
    assert clock.sleeps == [4.2]


def test_align_exhaust_budget_3_jitter_000_gate_0000():
    """Exhaustion at 3 attempts (jitter 0.0, gate 0.0): 2 gated rung(s) [0.1, 0.2], gate skipped on the dying attempt."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.0), max_attempts=3)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [0.1, 0.2]


def test_align_exhaust_budget_3_jitter_000_gate_0250():
    """Exhaustion at 3 attempts (jitter 0.0, gate 0.25): 2 gated rung(s) [0.35, 0.45], gate skipped on the dying attempt."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.25), max_attempts=3)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [0.35, 0.45]


def test_align_exhaust_budget_3_jitter_000_gate_4000():
    """Exhaustion at 3 attempts (jitter 0.0, gate 4.0): 2 gated rung(s) [4.1, 4.2], gate skipped on the dying attempt."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 4.0), max_attempts=3)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [4.1, 4.2]


def test_align_exhaust_budget_3_jitter_100_gate_0000():
    """Exhaustion at 3 attempts (jitter 1.0, gate 0.0): 2 gated rung(s) [0.2, 0.4], gate skipped on the dying attempt."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.0), max_attempts=3)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [0.2, 0.4]


def test_align_exhaust_budget_3_jitter_100_gate_0250():
    """Exhaustion at 3 attempts (jitter 1.0, gate 0.25): 2 gated rung(s) [0.45, 0.65], gate skipped on the dying attempt."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.25), max_attempts=3)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [0.45, 0.65]


def test_align_exhaust_budget_3_jitter_100_gate_4000():
    """Exhaustion at 3 attempts (jitter 1.0, gate 4.0): 2 gated rung(s) [4.2, 4.4], gate skipped on the dying attempt."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 4.0), max_attempts=3)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [4.2, 4.4]


def test_align_exhaust_budget_4_jitter_000_gate_0000():
    """Exhaustion at 4 attempts (jitter 0.0, gate 0.0): 3 gated rung(s) [0.1, 0.2, 0.4], gate skipped on the dying attempt."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.0), max_attempts=4)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [0.1, 0.2, 0.4]


def test_align_exhaust_budget_4_jitter_000_gate_0250():
    """Exhaustion at 4 attempts (jitter 0.0, gate 0.25): 3 gated rung(s) [0.35, 0.45, 0.65], gate skipped on the dying attempt."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.25), max_attempts=4)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [0.35, 0.45, 0.65]


def test_align_exhaust_budget_4_jitter_000_gate_4000():
    """Exhaustion at 4 attempts (jitter 0.0, gate 4.0): 3 gated rung(s) [4.1, 4.2, 4.4], gate skipped on the dying attempt."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 4.0), max_attempts=4)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [4.1, 4.2, 4.4]


def test_align_exhaust_budget_4_jitter_100_gate_0000():
    """Exhaustion at 4 attempts (jitter 1.0, gate 0.0): 3 gated rung(s) [0.2, 0.4, 0.8], gate skipped on the dying attempt."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.0), max_attempts=4)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [0.2, 0.4, 0.8]


def test_align_exhaust_budget_4_jitter_100_gate_0250():
    """Exhaustion at 4 attempts (jitter 1.0, gate 0.25): 3 gated rung(s) [0.45, 0.65, 1.05], gate skipped on the dying attempt."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.25), max_attempts=4)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [0.45, 0.65, 1.05]


def test_align_exhaust_budget_4_jitter_100_gate_4000():
    """Exhaustion at 4 attempts (jitter 1.0, gate 4.0): 3 gated rung(s) [4.2, 4.4, 4.8], gate skipped on the dying attempt."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 4.0), max_attempts=4)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [4.2, 4.4, 4.8]


def test_align_exhaust_budget_5_jitter_000_gate_0000():
    """Exhaustion at 5 attempts (jitter 0.0, gate 0.0): 4 gated rung(s) [0.1, 0.2, 0.4, 0.8], gate skipped on the dying attempt."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.0), max_attempts=5)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [0.1, 0.2, 0.4, 0.8]


def test_align_exhaust_budget_5_jitter_000_gate_0250():
    """Exhaustion at 5 attempts (jitter 0.0, gate 0.25): 4 gated rung(s) [0.35, 0.45, 0.65, 1.05], gate skipped on the dying attempt."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.25), max_attempts=5)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [0.35, 0.45, 0.65, 1.05]


def test_align_exhaust_budget_5_jitter_000_gate_4000():
    """Exhaustion at 5 attempts (jitter 0.0, gate 4.0): 4 gated rung(s) [4.1, 4.2, 4.4, 4.8], gate skipped on the dying attempt."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 4.0), max_attempts=5)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [4.1, 4.2, 4.4, 4.8]


def test_align_exhaust_budget_5_jitter_100_gate_0000():
    """Exhaustion at 5 attempts (jitter 1.0, gate 0.0): 4 gated rung(s) [0.2, 0.4, 0.8, 1.6], gate skipped on the dying attempt."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.0), max_attempts=5)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [0.2, 0.4, 0.8, 1.6]


def test_align_exhaust_budget_5_jitter_100_gate_0250():
    """Exhaustion at 5 attempts (jitter 1.0, gate 0.25): 4 gated rung(s) [0.45, 0.65, 1.05, 1.85], gate skipped on the dying attempt."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.25), max_attempts=5)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [0.45, 0.65, 1.05, 1.85]


def test_align_exhaust_budget_5_jitter_100_gate_4000():
    """Exhaustion at 5 attempts (jitter 1.0, gate 4.0): 4 gated rung(s) [4.2, 4.4, 4.8, 5.6], gate skipped on the dying attempt."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 4.0), max_attempts=5)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [4.2, 4.4, 4.8, 5.6]


def test_align_exhaust_budget_6_jitter_000_gate_0000():
    """Exhaustion at 6 attempts (jitter 0.0, gate 0.0): 5 gated rung(s) [0.1, 0.2, 0.4, 0.8, 1.6], gate skipped on the dying attempt."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.0), max_attempts=6)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [0.1, 0.2, 0.4, 0.8, 1.6]


def test_align_exhaust_budget_6_jitter_000_gate_0250():
    """Exhaustion at 6 attempts (jitter 0.0, gate 0.25): 5 gated rung(s) [0.35, 0.45, 0.65, 1.05, 1.85], gate skipped on the dying attempt."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.25), max_attempts=6)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [0.35, 0.45, 0.65, 1.05, 1.85]


def test_align_exhaust_budget_6_jitter_000_gate_4000():
    """Exhaustion at 6 attempts (jitter 0.0, gate 4.0): 5 gated rung(s) [4.1, 4.2, 4.4, 4.8, 5.6], gate skipped on the dying attempt."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 4.0), max_attempts=6)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [4.1, 4.2, 4.4, 4.8, 5.6]


def test_align_exhaust_budget_6_jitter_100_gate_0000():
    """Exhaustion at 6 attempts (jitter 1.0, gate 0.0): 5 gated rung(s) [0.2, 0.4, 0.8, 1.6, 3.2], gate skipped on the dying attempt."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.0), max_attempts=6)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [0.2, 0.4, 0.8, 1.6, 3.2]


def test_align_exhaust_budget_6_jitter_100_gate_0250():
    """Exhaustion at 6 attempts (jitter 1.0, gate 0.25): 5 gated rung(s) [0.45, 0.65, 1.05, 1.85, 3.45], gate skipped on the dying attempt."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.25), max_attempts=6)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [0.45, 0.65, 1.05, 1.85, 3.45]


def test_align_exhaust_budget_6_jitter_100_gate_4000():
    """Exhaustion at 6 attempts (jitter 1.0, gate 4.0): 5 gated rung(s) [4.2, 4.4, 4.8, 5.6, 7.2], gate skipped on the dying attempt."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 4.0), max_attempts=6)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == [1, 2, 3, 4, 5]
    assert clock.sleeps == [4.2, 4.4, 4.8, 5.6, 7.2]


def test_align_exhaust_budget_7_jitter_000_gate_0000():
    """Exhaustion at 7 attempts (jitter 0.0, gate 0.0): 6 gated rung(s) [0.1, 0.2, 0.4, 0.8, 1.6, 2.0], gate skipped on the dying attempt."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.0), max_attempts=7)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == [1, 2, 3, 4, 5, 6]
    assert clock.sleeps == [0.1, 0.2, 0.4, 0.8, 1.6, 2.0]


def test_align_exhaust_budget_7_jitter_000_gate_0250():
    """Exhaustion at 7 attempts (jitter 0.0, gate 0.25): 6 gated rung(s) [0.35, 0.45, 0.65, 1.05, 1.85, 2.25], gate skipped on the dying attempt."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.25), max_attempts=7)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == [1, 2, 3, 4, 5, 6]
    assert clock.sleeps == [0.35, 0.45, 0.65, 1.05, 1.85, 2.25]


def test_align_exhaust_budget_7_jitter_000_gate_4000():
    """Exhaustion at 7 attempts (jitter 0.0, gate 4.0): 6 gated rung(s) [4.1, 4.2, 4.4, 4.8, 5.6, 6.0], gate skipped on the dying attempt."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 4.0), max_attempts=7)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == [1, 2, 3, 4, 5, 6]
    assert clock.sleeps == [4.1, 4.2, 4.4, 4.8, 5.6, 6.0]


def test_align_exhaust_budget_7_jitter_100_gate_0000():
    """Exhaustion at 7 attempts (jitter 1.0, gate 0.0): 6 gated rung(s) [0.2, 0.4, 0.8, 1.6, 3.2, 4.0], gate skipped on the dying attempt."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.0), max_attempts=7)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == [1, 2, 3, 4, 5, 6]
    assert clock.sleeps == [0.2, 0.4, 0.8, 1.6, 3.2, 4.0]


def test_align_exhaust_budget_7_jitter_100_gate_0250():
    """Exhaustion at 7 attempts (jitter 1.0, gate 0.25): 6 gated rung(s) [0.45, 0.65, 1.05, 1.85, 3.45, 4.25], gate skipped on the dying attempt."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.25), max_attempts=7)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == [1, 2, 3, 4, 5, 6]
    assert clock.sleeps == [0.45, 0.65, 1.05, 1.85, 3.45, 4.25]


def test_align_exhaust_budget_7_jitter_100_gate_4000():
    """Exhaustion at 7 attempts (jitter 1.0, gate 4.0): 6 gated rung(s) [4.2, 4.4, 4.8, 5.6, 7.2, 8.0], gate skipped on the dying attempt."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 4.0), max_attempts=7)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.gate_calls == [1, 2, 3, 4, 5, 6]
    assert clock.sleeps == [4.2, 4.4, 4.8, 5.6, 7.2, 8.0]


def test_align_deadline_ample_jitter_000_gate_0000():
    """Far deadline (jitter 0.0, gate 0.0): both retries gated, sleeps [0.1, 0.2]."""
    clock = _Clock(jitter=0.0)
    assert _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.0), deadline=10**6) == 'ok'
    assert clock.sleeps == [0.1, 0.2]


def test_align_deadline_tight_jitter_000_gate_0000():
    """Tight deadline (jitter 0.0, gate 0.0): rung 1 priced at 0.1s sleeps then the reserve refuses."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.0), deadline=100.5)
    assert caught.value.reason == 'deadline_exhausted'
    assert clock.gate_calls == [1]  # rung 1 was priced before the budget refused attempt 2
    assert clock.sleeps == [0.1]  # the priced rung sleeps, then the 30s reserve refuses


def test_align_deadline_ample_jitter_000_gate_1000():
    """Far deadline (jitter 0.0, gate 1.0): both retries gated, sleeps [1.1, 1.2]."""
    clock = _Clock(jitter=0.0)
    assert _chain(clock, aborts=2, gate=_gate_recorder(clock, 1.0), deadline=10**6) == 'ok'
    assert clock.sleeps == [1.1, 1.2]


def test_align_deadline_tight_jitter_000_gate_1000():
    """Tight deadline (jitter 0.0, gate 1.0): rung 1 priced at 1.1s exceeds the 0.5s remaining: refused at pricing."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=2, gate=_gate_recorder(clock, 1.0), deadline=100.5)
    assert caught.value.reason == 'deadline_exhausted'
    assert clock.gate_calls == [1]  # rung 1 was priced before the budget refused attempt 2
    assert clock.sleeps == []  # the priced rung exceeds the remaining budget: no sleep


def test_align_deadline_ample_jitter_000_gate_30000():
    """Far deadline (jitter 0.0, gate 30.0): both retries gated, sleeps [30.1, 30.2]."""
    clock = _Clock(jitter=0.0)
    assert _chain(clock, aborts=2, gate=_gate_recorder(clock, 30.0), deadline=10**6) == 'ok'
    assert clock.sleeps == [30.1, 30.2]


def test_align_deadline_tight_jitter_000_gate_30000():
    """Tight deadline (jitter 0.0, gate 30.0): rung 1 priced at 30.1s exceeds the 0.5s remaining: refused at pricing."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=2, gate=_gate_recorder(clock, 30.0), deadline=100.5)
    assert caught.value.reason == 'deadline_exhausted'
    assert clock.gate_calls == [1]  # rung 1 was priced before the budget refused attempt 2
    assert clock.sleeps == []  # the priced rung exceeds the remaining budget: no sleep


def test_align_deadline_ample_jitter_050_gate_0000():
    """Far deadline (jitter 0.5, gate 0.0): both retries gated, sleeps [0.15, 0.3]."""
    clock = _Clock(jitter=0.5)
    assert _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.0), deadline=10**6) == 'ok'
    assert clock.sleeps == [0.15, 0.3]


def test_align_deadline_tight_jitter_050_gate_0000():
    """Tight deadline (jitter 0.5, gate 0.0): rung 1 priced at 0.15s sleeps then the reserve refuses."""
    clock = _Clock(jitter=0.5)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.0), deadline=100.5)
    assert caught.value.reason == 'deadline_exhausted'
    assert clock.gate_calls == [1]  # rung 1 was priced before the budget refused attempt 2
    assert clock.sleeps == [0.15]  # the priced rung sleeps, then the 30s reserve refuses


def test_align_deadline_ample_jitter_050_gate_1000():
    """Far deadline (jitter 0.5, gate 1.0): both retries gated, sleeps [1.15, 1.3]."""
    clock = _Clock(jitter=0.5)
    assert _chain(clock, aborts=2, gate=_gate_recorder(clock, 1.0), deadline=10**6) == 'ok'
    assert clock.sleeps == [1.15, 1.3]


def test_align_deadline_tight_jitter_050_gate_1000():
    """Tight deadline (jitter 0.5, gate 1.0): rung 1 priced at 1.15s exceeds the 0.5s remaining: refused at pricing."""
    clock = _Clock(jitter=0.5)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=2, gate=_gate_recorder(clock, 1.0), deadline=100.5)
    assert caught.value.reason == 'deadline_exhausted'
    assert clock.gate_calls == [1]  # rung 1 was priced before the budget refused attempt 2
    assert clock.sleeps == []  # the priced rung exceeds the remaining budget: no sleep


def test_align_deadline_ample_jitter_050_gate_30000():
    """Far deadline (jitter 0.5, gate 30.0): both retries gated, sleeps [30.15, 30.3]."""
    clock = _Clock(jitter=0.5)
    assert _chain(clock, aborts=2, gate=_gate_recorder(clock, 30.0), deadline=10**6) == 'ok'
    assert clock.sleeps == [30.15, 30.3]


def test_align_deadline_tight_jitter_050_gate_30000():
    """Tight deadline (jitter 0.5, gate 30.0): rung 1 priced at 30.15s exceeds the 0.5s remaining: refused at pricing."""
    clock = _Clock(jitter=0.5)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=2, gate=_gate_recorder(clock, 30.0), deadline=100.5)
    assert caught.value.reason == 'deadline_exhausted'
    assert clock.gate_calls == [1]  # rung 1 was priced before the budget refused attempt 2
    assert clock.sleeps == []  # the priced rung exceeds the remaining budget: no sleep


def test_align_deadline_ample_jitter_100_gate_0000():
    """Far deadline (jitter 1.0, gate 0.0): both retries gated, sleeps [0.2, 0.4]."""
    clock = _Clock(jitter=1.0)
    assert _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.0), deadline=10**6) == 'ok'
    assert clock.sleeps == [0.2, 0.4]


def test_align_deadline_tight_jitter_100_gate_0000():
    """Tight deadline (jitter 1.0, gate 0.0): rung 1 priced at 0.2s sleeps then the reserve refuses."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.0), deadline=100.5)
    assert caught.value.reason == 'deadline_exhausted'
    assert clock.gate_calls == [1]  # rung 1 was priced before the budget refused attempt 2
    assert clock.sleeps == [0.2]  # the priced rung sleeps, then the 30s reserve refuses


def test_align_deadline_ample_jitter_100_gate_1000():
    """Far deadline (jitter 1.0, gate 1.0): both retries gated, sleeps [1.2, 1.4]."""
    clock = _Clock(jitter=1.0)
    assert _chain(clock, aborts=2, gate=_gate_recorder(clock, 1.0), deadline=10**6) == 'ok'
    assert clock.sleeps == [1.2, 1.4]


def test_align_deadline_tight_jitter_100_gate_1000():
    """Tight deadline (jitter 1.0, gate 1.0): rung 1 priced at 1.2s exceeds the 0.5s remaining: refused at pricing."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=2, gate=_gate_recorder(clock, 1.0), deadline=100.5)
    assert caught.value.reason == 'deadline_exhausted'
    assert clock.gate_calls == [1]  # rung 1 was priced before the budget refused attempt 2
    assert clock.sleeps == []  # the priced rung exceeds the remaining budget: no sleep


def test_align_deadline_ample_jitter_100_gate_30000():
    """Far deadline (jitter 1.0, gate 30.0): both retries gated, sleeps [30.2, 30.4]."""
    clock = _Clock(jitter=1.0)
    assert _chain(clock, aborts=2, gate=_gate_recorder(clock, 30.0), deadline=10**6) == 'ok'
    assert clock.sleeps == [30.2, 30.4]


def test_align_deadline_tight_jitter_100_gate_30000():
    """Tight deadline (jitter 1.0, gate 30.0): rung 1 priced at 30.2s exceeds the 0.5s remaining: refused at pricing."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=2, gate=_gate_recorder(clock, 30.0), deadline=100.5)
    assert caught.value.reason == 'deadline_exhausted'
    assert clock.gate_calls == [1]  # rung 1 was priced before the budget refused attempt 2
    assert clock.sleeps == []  # the priced rung exceeds the remaining budget: no sleep


def test_align_gatepriced_allowed_jitter_000_gate_0000():
    """Deadline covers rung1+gate and the reserve (jitter 0.0, gate 0.0): the gated retry runs."""
    clock = _Clock(jitter=0.0)
    assert _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.0), deadline=140.1) == 'ok'
    assert clock.sleeps == [0.1]


def test_align_gatepriced_refused_jitter_000_gate_0000():
    """Deadline below rung1+gate (jitter 0.0, gate 0.0): gate consulted, retry refused."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.0), deadline=100.09, max_attempts=3)
    assert caught.value.reason == 'deadline_exhausted'
    assert clock.gate_calls == [1]  # consulted, then refused on the combined price
    assert clock.sleeps == []


def test_align_gatepriced_allowed_jitter_000_gate_0500():
    """Deadline covers rung1+gate and the reserve (jitter 0.0, gate 0.5): the gated retry runs."""
    clock = _Clock(jitter=0.0)
    assert _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.5), deadline=140.6) == 'ok'
    assert clock.sleeps == [0.6]


def test_align_gatepriced_refused_jitter_000_gate_0500():
    """Deadline below rung1+gate (jitter 0.0, gate 0.5): gate consulted, retry refused."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.5), deadline=100.59, max_attempts=3)
    assert caught.value.reason == 'deadline_exhausted'
    assert clock.gate_calls == [1]  # consulted, then refused on the combined price
    assert clock.sleeps == []


def test_align_gatepriced_allowed_jitter_100_gate_0000():
    """Deadline covers rung1+gate and the reserve (jitter 1.0, gate 0.0): the gated retry runs."""
    clock = _Clock(jitter=1.0)
    assert _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.0), deadline=140.2) == 'ok'
    assert clock.sleeps == [0.2]


def test_align_gatepriced_refused_jitter_100_gate_0000():
    """Deadline below rung1+gate (jitter 1.0, gate 0.0): gate consulted, retry refused."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.0), deadline=100.19, max_attempts=3)
    assert caught.value.reason == 'deadline_exhausted'
    assert clock.gate_calls == [1]  # consulted, then refused on the combined price
    assert clock.sleeps == []


def test_align_gatepriced_allowed_jitter_100_gate_0500():
    """Deadline covers rung1+gate and the reserve (jitter 1.0, gate 0.5): the gated retry runs."""
    clock = _Clock(jitter=1.0)
    assert _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.5), deadline=140.7) == 'ok'
    assert clock.sleeps == [0.7]


def test_align_gatepriced_refused_jitter_100_gate_0500():
    """Deadline below rung1+gate (jitter 1.0, gate 0.5): gate consulted, retry refused."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.5), deadline=100.69, max_attempts=3)
    assert caught.value.reason == 'deadline_exhausted'
    assert clock.gate_calls == [1]  # consulted, then refused on the combined price
    assert clock.sleeps == []


def test_align_hostile_bool_true_aborts_1_jitter_000():
    """Hostile gate answer bool_true (aborts 1, jitter 0.0): rungs stay bare [0.1]."""
    clock = _Clock(jitter=0.0)
    assert _chain(clock, aborts=1, gate=_gate_recorder(clock, True)) == 'ok'
    assert clock.sleeps == [0.1]  # bare equal-jitter schedule


def test_align_hostile_bool_true_aborts_1_jitter_100():
    """Hostile gate answer bool_true (aborts 1, jitter 1.0): rungs stay bare [0.2]."""
    clock = _Clock(jitter=1.0)
    assert _chain(clock, aborts=1, gate=_gate_recorder(clock, True)) == 'ok'
    assert clock.sleeps == [0.2]  # bare equal-jitter schedule


def test_align_hostile_bool_true_aborts_3_jitter_000():
    """Hostile gate answer bool_true (aborts 3, jitter 0.0): rungs stay bare [0.1, 0.2, 0.4]."""
    clock = _Clock(jitter=0.0)
    assert _chain(clock, aborts=3, gate=_gate_recorder(clock, True)) == 'ok'
    assert clock.sleeps == [0.1, 0.2, 0.4]  # bare equal-jitter schedule


def test_align_hostile_bool_true_aborts_3_jitter_100():
    """Hostile gate answer bool_true (aborts 3, jitter 1.0): rungs stay bare [0.2, 0.4, 0.8]."""
    clock = _Clock(jitter=1.0)
    assert _chain(clock, aborts=3, gate=_gate_recorder(clock, True)) == 'ok'
    assert clock.sleeps == [0.2, 0.4, 0.8]  # bare equal-jitter schedule


def test_align_hostile_string_aborts_1_jitter_000():
    """Hostile gate answer string (aborts 1, jitter 0.0): rungs stay bare [0.1]."""
    clock = _Clock(jitter=0.0)
    assert _chain(clock, aborts=1, gate=_gate_recorder(clock, '0.5')) == 'ok'
    assert clock.sleeps == [0.1]  # bare equal-jitter schedule


def test_align_hostile_string_aborts_1_jitter_100():
    """Hostile gate answer string (aborts 1, jitter 1.0): rungs stay bare [0.2]."""
    clock = _Clock(jitter=1.0)
    assert _chain(clock, aborts=1, gate=_gate_recorder(clock, '0.5')) == 'ok'
    assert clock.sleeps == [0.2]  # bare equal-jitter schedule


def test_align_hostile_string_aborts_3_jitter_000():
    """Hostile gate answer string (aborts 3, jitter 0.0): rungs stay bare [0.1, 0.2, 0.4]."""
    clock = _Clock(jitter=0.0)
    assert _chain(clock, aborts=3, gate=_gate_recorder(clock, '0.5')) == 'ok'
    assert clock.sleeps == [0.1, 0.2, 0.4]  # bare equal-jitter schedule


def test_align_hostile_string_aborts_3_jitter_100():
    """Hostile gate answer string (aborts 3, jitter 1.0): rungs stay bare [0.2, 0.4, 0.8]."""
    clock = _Clock(jitter=1.0)
    assert _chain(clock, aborts=3, gate=_gate_recorder(clock, '0.5')) == 'ok'
    assert clock.sleeps == [0.2, 0.4, 0.8]  # bare equal-jitter schedule


def test_align_hostile_none_aborts_1_jitter_000():
    """Hostile gate answer none (aborts 1, jitter 0.0): rungs stay bare [0.1]."""
    clock = _Clock(jitter=0.0)
    assert _chain(clock, aborts=1, gate=_gate_recorder(clock, None)) == 'ok'
    assert clock.sleeps == [0.1]  # bare equal-jitter schedule


def test_align_hostile_none_aborts_1_jitter_100():
    """Hostile gate answer none (aborts 1, jitter 1.0): rungs stay bare [0.2]."""
    clock = _Clock(jitter=1.0)
    assert _chain(clock, aborts=1, gate=_gate_recorder(clock, None)) == 'ok'
    assert clock.sleeps == [0.2]  # bare equal-jitter schedule


def test_align_hostile_none_aborts_3_jitter_000():
    """Hostile gate answer none (aborts 3, jitter 0.0): rungs stay bare [0.1, 0.2, 0.4]."""
    clock = _Clock(jitter=0.0)
    assert _chain(clock, aborts=3, gate=_gate_recorder(clock, None)) == 'ok'
    assert clock.sleeps == [0.1, 0.2, 0.4]  # bare equal-jitter schedule


def test_align_hostile_none_aborts_3_jitter_100():
    """Hostile gate answer none (aborts 3, jitter 1.0): rungs stay bare [0.2, 0.4, 0.8]."""
    clock = _Clock(jitter=1.0)
    assert _chain(clock, aborts=3, gate=_gate_recorder(clock, None)) == 'ok'
    assert clock.sleeps == [0.2, 0.4, 0.8]  # bare equal-jitter schedule


def test_align_hostile_nan_aborts_1_jitter_000():
    """Hostile gate answer nan (aborts 1, jitter 0.0): rungs stay bare [0.1]."""
    clock = _Clock(jitter=0.0)
    assert _chain(clock, aborts=1, gate=_gate_recorder(clock, float('nan'))) == 'ok'
    assert clock.sleeps == [0.1]  # bare equal-jitter schedule


def test_align_hostile_nan_aborts_1_jitter_100():
    """Hostile gate answer nan (aborts 1, jitter 1.0): rungs stay bare [0.2]."""
    clock = _Clock(jitter=1.0)
    assert _chain(clock, aborts=1, gate=_gate_recorder(clock, float('nan'))) == 'ok'
    assert clock.sleeps == [0.2]  # bare equal-jitter schedule


def test_align_hostile_nan_aborts_3_jitter_000():
    """Hostile gate answer nan (aborts 3, jitter 0.0): rungs stay bare [0.1, 0.2, 0.4]."""
    clock = _Clock(jitter=0.0)
    assert _chain(clock, aborts=3, gate=_gate_recorder(clock, float('nan'))) == 'ok'
    assert clock.sleeps == [0.1, 0.2, 0.4]  # bare equal-jitter schedule


def test_align_hostile_nan_aborts_3_jitter_100():
    """Hostile gate answer nan (aborts 3, jitter 1.0): rungs stay bare [0.2, 0.4, 0.8]."""
    clock = _Clock(jitter=1.0)
    assert _chain(clock, aborts=3, gate=_gate_recorder(clock, float('nan'))) == 'ok'
    assert clock.sleeps == [0.2, 0.4, 0.8]  # bare equal-jitter schedule


def test_align_hostile_inf_aborts_1_jitter_000():
    """Hostile gate answer inf (aborts 1, jitter 0.0): rungs stay bare [0.1]."""
    clock = _Clock(jitter=0.0)
    assert _chain(clock, aborts=1, gate=_gate_recorder(clock, float('inf'))) == 'ok'
    assert clock.sleeps == [0.1]  # bare equal-jitter schedule


def test_align_hostile_inf_aborts_1_jitter_100():
    """Hostile gate answer inf (aborts 1, jitter 1.0): rungs stay bare [0.2]."""
    clock = _Clock(jitter=1.0)
    assert _chain(clock, aborts=1, gate=_gate_recorder(clock, float('inf'))) == 'ok'
    assert clock.sleeps == [0.2]  # bare equal-jitter schedule


def test_align_hostile_inf_aborts_3_jitter_000():
    """Hostile gate answer inf (aborts 3, jitter 0.0): rungs stay bare [0.1, 0.2, 0.4]."""
    clock = _Clock(jitter=0.0)
    assert _chain(clock, aborts=3, gate=_gate_recorder(clock, float('inf'))) == 'ok'
    assert clock.sleeps == [0.1, 0.2, 0.4]  # bare equal-jitter schedule


def test_align_hostile_inf_aborts_3_jitter_100():
    """Hostile gate answer inf (aborts 3, jitter 1.0): rungs stay bare [0.2, 0.4, 0.8]."""
    clock = _Clock(jitter=1.0)
    assert _chain(clock, aborts=3, gate=_gate_recorder(clock, float('inf'))) == 'ok'
    assert clock.sleeps == [0.2, 0.4, 0.8]  # bare equal-jitter schedule


def test_align_hostile_negative_aborts_1_jitter_000():
    """Hostile gate answer negative (aborts 1, jitter 0.0): rungs stay bare [0.1]."""
    clock = _Clock(jitter=0.0)
    assert _chain(clock, aborts=1, gate=_gate_recorder(clock, -1.0)) == 'ok'
    assert clock.sleeps == [0.1]  # bare equal-jitter schedule


def test_align_hostile_negative_aborts_1_jitter_100():
    """Hostile gate answer negative (aborts 1, jitter 1.0): rungs stay bare [0.2]."""
    clock = _Clock(jitter=1.0)
    assert _chain(clock, aborts=1, gate=_gate_recorder(clock, -1.0)) == 'ok'
    assert clock.sleeps == [0.2]  # bare equal-jitter schedule


def test_align_hostile_negative_aborts_3_jitter_000():
    """Hostile gate answer negative (aborts 3, jitter 0.0): rungs stay bare [0.1, 0.2, 0.4]."""
    clock = _Clock(jitter=0.0)
    assert _chain(clock, aborts=3, gate=_gate_recorder(clock, -1.0)) == 'ok'
    assert clock.sleeps == [0.1, 0.2, 0.4]  # bare equal-jitter schedule


def test_align_hostile_negative_aborts_3_jitter_100():
    """Hostile gate answer negative (aborts 3, jitter 1.0): rungs stay bare [0.2, 0.4, 0.8]."""
    clock = _Clock(jitter=1.0)
    assert _chain(clock, aborts=3, gate=_gate_recorder(clock, -1.0)) == 'ok'
    assert clock.sleeps == [0.2, 0.4, 0.8]  # bare equal-jitter schedule


def test_align_hostile_zero_aborts_1_jitter_000():
    """Hostile gate answer zero (aborts 1, jitter 0.0): rungs stay bare [0.1]."""
    clock = _Clock(jitter=0.0)
    assert _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.0)) == 'ok'
    assert clock.sleeps == [0.1]  # bare equal-jitter schedule


def test_align_hostile_zero_aborts_1_jitter_100():
    """Hostile gate answer zero (aborts 1, jitter 1.0): rungs stay bare [0.2]."""
    clock = _Clock(jitter=1.0)
    assert _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.0)) == 'ok'
    assert clock.sleeps == [0.2]  # bare equal-jitter schedule


def test_align_hostile_zero_aborts_3_jitter_000():
    """Hostile gate answer zero (aborts 3, jitter 0.0): rungs stay bare [0.1, 0.2, 0.4]."""
    clock = _Clock(jitter=0.0)
    assert _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.0)) == 'ok'
    assert clock.sleeps == [0.1, 0.2, 0.4]  # bare equal-jitter schedule


def test_align_hostile_zero_aborts_3_jitter_100():
    """Hostile gate answer zero (aborts 3, jitter 1.0): rungs stay bare [0.2, 0.4, 0.8]."""
    clock = _Clock(jitter=1.0)
    assert _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.0)) == 'ok'
    assert clock.sleeps == [0.2, 0.4, 0.8]  # bare equal-jitter schedule


def test_align_scripted_step_ladder_jitter_000():
    """Scripted residuals [0.0, 0.25, 0.0, 0.5] (jitter 0.0): each rung carries its own gate wait [0.1, 0.45, 0.4, 1.3]."""
    clock = _Clock(jitter=0.0)
    script = [0.0, 0.25, 0.0, 0.5]
    gate = lambda attempt: (clock.gate_calls.append(attempt), script[attempt - 1])[1]
    assert _chain(clock, aborts=4, gate=gate) == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [0.1, 0.45, 0.4, 1.3]


def test_align_scripted_step_ladder_jitter_100():
    """Scripted residuals [0.0, 0.25, 0.0, 0.5] (jitter 1.0): each rung carries its own gate wait [0.2, 0.65, 0.8, 2.1]."""
    clock = _Clock(jitter=1.0)
    script = [0.0, 0.25, 0.0, 0.5]
    gate = lambda attempt: (clock.gate_calls.append(attempt), script[attempt - 1])[1]
    assert _chain(clock, aborts=4, gate=gate) == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [0.2, 0.65, 0.8, 2.1]


def test_align_scripted_front_loaded_jitter_000():
    """Scripted residuals [1.0, 0.0, 0.0, 0.0] (jitter 0.0): each rung carries its own gate wait [1.1, 0.2, 0.4, 0.8]."""
    clock = _Clock(jitter=0.0)
    script = [1.0, 0.0, 0.0, 0.0]
    gate = lambda attempt: (clock.gate_calls.append(attempt), script[attempt - 1])[1]
    assert _chain(clock, aborts=4, gate=gate) == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [1.1, 0.2, 0.4, 0.8]


def test_align_scripted_front_loaded_jitter_100():
    """Scripted residuals [1.0, 0.0, 0.0, 0.0] (jitter 1.0): each rung carries its own gate wait [1.2, 0.4, 0.8, 1.6]."""
    clock = _Clock(jitter=1.0)
    script = [1.0, 0.0, 0.0, 0.0]
    gate = lambda attempt: (clock.gate_calls.append(attempt), script[attempt - 1])[1]
    assert _chain(clock, aborts=4, gate=gate) == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [1.2, 0.4, 0.8, 1.6]


def test_align_scripted_back_loaded_jitter_000():
    """Scripted residuals [0.0, 0.0, 0.0, 2.0] (jitter 0.0): each rung carries its own gate wait [0.1, 0.2, 0.4, 2.8]."""
    clock = _Clock(jitter=0.0)
    script = [0.0, 0.0, 0.0, 2.0]
    gate = lambda attempt: (clock.gate_calls.append(attempt), script[attempt - 1])[1]
    assert _chain(clock, aborts=4, gate=gate) == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [0.1, 0.2, 0.4, 2.8]


def test_align_scripted_back_loaded_jitter_100():
    """Scripted residuals [0.0, 0.0, 0.0, 2.0] (jitter 1.0): each rung carries its own gate wait [0.2, 0.4, 0.8, 3.6]."""
    clock = _Clock(jitter=1.0)
    script = [0.0, 0.0, 0.0, 2.0]
    gate = lambda attempt: (clock.gate_calls.append(attempt), script[attempt - 1])[1]
    assert _chain(clock, aborts=4, gate=gate) == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [0.2, 0.4, 0.8, 3.6]


def test_align_scripted_constant_cap_jitter_000():
    """Scripted residuals [4.0, 4.0, 4.0, 4.0] (jitter 0.0): each rung carries its own gate wait [4.1, 4.2, 4.4, 4.8]."""
    clock = _Clock(jitter=0.0)
    script = [4.0, 4.0, 4.0, 4.0]
    gate = lambda attempt: (clock.gate_calls.append(attempt), script[attempt - 1])[1]
    assert _chain(clock, aborts=4, gate=gate) == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [4.1, 4.2, 4.4, 4.8]


def test_align_scripted_constant_cap_jitter_100():
    """Scripted residuals [4.0, 4.0, 4.0, 4.0] (jitter 1.0): each rung carries its own gate wait [4.2, 4.4, 4.8, 5.6]."""
    clock = _Clock(jitter=1.0)
    script = [4.0, 4.0, 4.0, 4.0]
    gate = lambda attempt: (clock.gate_calls.append(attempt), script[attempt - 1])[1]
    assert _chain(clock, aborts=4, gate=gate) == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [4.2, 4.4, 4.8, 5.6]


def test_align_scripted_alternating_jitter_000():
    """Scripted residuals [0.125, 0.0, 0.375, 0.0] (jitter 0.0): each rung carries its own gate wait [0.225, 0.2, 0.775, 0.8]."""
    clock = _Clock(jitter=0.0)
    script = [0.125, 0.0, 0.375, 0.0]
    gate = lambda attempt: (clock.gate_calls.append(attempt), script[attempt - 1])[1]
    assert _chain(clock, aborts=4, gate=gate) == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [0.225, 0.2, 0.775, 0.8]


def test_align_scripted_alternating_jitter_100():
    """Scripted residuals [0.125, 0.0, 0.375, 0.0] (jitter 1.0): each rung carries its own gate wait [0.325, 0.4, 1.175, 1.6]."""
    clock = _Clock(jitter=1.0)
    script = [0.125, 0.0, 0.375, 0.0]
    gate = lambda attempt: (clock.gate_calls.append(attempt), script[attempt - 1])[1]
    assert _chain(clock, aborts=4, gate=gate) == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [0.325, 0.4, 1.175, 1.6]


def test_align_scripted_decay_jitter_000():
    """Scripted residuals [2.0, 1.0, 0.5, 0.25] (jitter 0.0): each rung carries its own gate wait [2.1, 1.2, 0.9, 1.05]."""
    clock = _Clock(jitter=0.0)
    script = [2.0, 1.0, 0.5, 0.25]
    gate = lambda attempt: (clock.gate_calls.append(attempt), script[attempt - 1])[1]
    assert _chain(clock, aborts=4, gate=gate) == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [2.1, 1.2, 0.9, 1.05]


def test_align_scripted_decay_jitter_100():
    """Scripted residuals [2.0, 1.0, 0.5, 0.25] (jitter 1.0): each rung carries its own gate wait [2.2, 1.4, 1.3, 1.85]."""
    clock = _Clock(jitter=1.0)
    script = [2.0, 1.0, 0.5, 0.25]
    gate = lambda attempt: (clock.gate_calls.append(attempt), script[attempt - 1])[1]
    assert _chain(clock, aborts=4, gate=gate) == 'ok'
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [2.2, 1.4, 1.3, 1.85]


def test_align_optin_budget_8_jitter_000_gate_0000():
    """Opt-in chain of 8 (jitter 0.0, gate 0.0): 7 gated rungs, capped tail."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.0), max_attempts=8)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.sleeps == [0.1, 0.2, 0.4, 0.8, 1.6, 2.0, 2.0]
    assert all(s <= 8.0 + 1e-9 for s in clock.sleeps)  # capped 4.0s rung + capped 4.0s gate


def test_align_optin_budget_8_jitter_000_gate_4000():
    """Opt-in chain of 8 (jitter 0.0, gate 4.0): 7 gated rungs, capped tail."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 4.0), max_attempts=8)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.sleeps == [4.1, 4.2, 4.4, 4.8, 5.6, 6.0, 6.0]
    assert all(s <= 8.0 + 1e-9 for s in clock.sleeps)  # capped 4.0s rung + capped 4.0s gate


def test_align_optin_budget_8_jitter_100_gate_0000():
    """Opt-in chain of 8 (jitter 1.0, gate 0.0): 7 gated rungs, capped tail."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.0), max_attempts=8)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.sleeps == [0.2, 0.4, 0.8, 1.6, 3.2, 4.0, 4.0]
    assert all(s <= 8.0 + 1e-9 for s in clock.sleeps)  # capped 4.0s rung + capped 4.0s gate


def test_align_optin_budget_8_jitter_100_gate_4000():
    """Opt-in chain of 8 (jitter 1.0, gate 4.0): 7 gated rungs, capped tail."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 4.0), max_attempts=8)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.sleeps == [4.2, 4.4, 4.8, 5.6, 7.2, 8.0, 8.0]
    assert all(s <= 8.0 + 1e-9 for s in clock.sleeps)  # capped 4.0s rung + capped 4.0s gate


def test_align_optin_budget_9_jitter_000_gate_0000():
    """Opt-in chain of 9 (jitter 0.0, gate 0.0): 8 gated rungs, capped tail."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.0), max_attempts=9)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.sleeps == [0.1, 0.2, 0.4, 0.8, 1.6, 2.0, 2.0, 2.0]
    assert all(s <= 8.0 + 1e-9 for s in clock.sleeps)  # capped 4.0s rung + capped 4.0s gate


def test_align_optin_budget_9_jitter_000_gate_4000():
    """Opt-in chain of 9 (jitter 0.0, gate 4.0): 8 gated rungs, capped tail."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 4.0), max_attempts=9)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.sleeps == [4.1, 4.2, 4.4, 4.8, 5.6, 6.0, 6.0, 6.0]
    assert all(s <= 8.0 + 1e-9 for s in clock.sleeps)  # capped 4.0s rung + capped 4.0s gate


def test_align_optin_budget_9_jitter_100_gate_0000():
    """Opt-in chain of 9 (jitter 1.0, gate 0.0): 8 gated rungs, capped tail."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.0), max_attempts=9)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.sleeps == [0.2, 0.4, 0.8, 1.6, 3.2, 4.0, 4.0, 4.0]
    assert all(s <= 8.0 + 1e-9 for s in clock.sleeps)  # capped 4.0s rung + capped 4.0s gate


def test_align_optin_budget_9_jitter_100_gate_4000():
    """Opt-in chain of 9 (jitter 1.0, gate 4.0): 8 gated rungs, capped tail."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 4.0), max_attempts=9)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.sleeps == [4.2, 4.4, 4.8, 5.6, 7.2, 8.0, 8.0, 8.0]
    assert all(s <= 8.0 + 1e-9 for s in clock.sleeps)  # capped 4.0s rung + capped 4.0s gate


def test_align_optin_budget_10_jitter_000_gate_0000():
    """Opt-in chain of 10 (jitter 0.0, gate 0.0): 9 gated rungs, capped tail."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.0), max_attempts=10)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.sleeps == [0.1, 0.2, 0.4, 0.8, 1.6, 2.0, 2.0, 2.0, 2.0]
    assert all(s <= 8.0 + 1e-9 for s in clock.sleeps)  # capped 4.0s rung + capped 4.0s gate


def test_align_optin_budget_10_jitter_000_gate_4000():
    """Opt-in chain of 10 (jitter 0.0, gate 4.0): 9 gated rungs, capped tail."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 4.0), max_attempts=10)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.sleeps == [4.1, 4.2, 4.4, 4.8, 5.6, 6.0, 6.0, 6.0, 6.0]
    assert all(s <= 8.0 + 1e-9 for s in clock.sleeps)  # capped 4.0s rung + capped 4.0s gate


def test_align_optin_budget_10_jitter_100_gate_0000():
    """Opt-in chain of 10 (jitter 1.0, gate 0.0): 9 gated rungs, capped tail."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.0), max_attempts=10)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.sleeps == [0.2, 0.4, 0.8, 1.6, 3.2, 4.0, 4.0, 4.0, 4.0]
    assert all(s <= 8.0 + 1e-9 for s in clock.sleeps)  # capped 4.0s rung + capped 4.0s gate


def test_align_optin_budget_10_jitter_100_gate_4000():
    """Opt-in chain of 10 (jitter 1.0, gate 4.0): 9 gated rungs, capped tail."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 4.0), max_attempts=10)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.sleeps == [4.2, 4.4, 4.8, 5.6, 7.2, 8.0, 8.0, 8.0, 8.0]
    assert all(s <= 8.0 + 1e-9 for s in clock.sleeps)  # capped 4.0s rung + capped 4.0s gate


def test_align_optin_budget_11_jitter_000_gate_0000():
    """Opt-in chain of 11 (jitter 0.0, gate 0.0): 10 gated rungs, capped tail."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.0), max_attempts=11)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.sleeps == [0.1, 0.2, 0.4, 0.8, 1.6, 2.0, 2.0, 2.0, 2.0, 2.0]
    assert all(s <= 8.0 + 1e-9 for s in clock.sleeps)  # capped 4.0s rung + capped 4.0s gate


def test_align_optin_budget_11_jitter_000_gate_4000():
    """Opt-in chain of 11 (jitter 0.0, gate 4.0): 10 gated rungs, capped tail."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 4.0), max_attempts=11)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.sleeps == [4.1, 4.2, 4.4, 4.8, 5.6, 6.0, 6.0, 6.0, 6.0, 6.0]
    assert all(s <= 8.0 + 1e-9 for s in clock.sleeps)  # capped 4.0s rung + capped 4.0s gate


def test_align_optin_budget_11_jitter_100_gate_0000():
    """Opt-in chain of 11 (jitter 1.0, gate 0.0): 10 gated rungs, capped tail."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.0), max_attempts=11)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.sleeps == [0.2, 0.4, 0.8, 1.6, 3.2, 4.0, 4.0, 4.0, 4.0, 4.0]
    assert all(s <= 8.0 + 1e-9 for s in clock.sleeps)  # capped 4.0s rung + capped 4.0s gate


def test_align_optin_budget_11_jitter_100_gate_4000():
    """Opt-in chain of 11 (jitter 1.0, gate 4.0): 10 gated rungs, capped tail."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 4.0), max_attempts=11)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.sleeps == [4.2, 4.4, 4.8, 5.6, 7.2, 8.0, 8.0, 8.0, 8.0, 8.0]
    assert all(s <= 8.0 + 1e-9 for s in clock.sleeps)  # capped 4.0s rung + capped 4.0s gate


def test_align_optin_budget_12_jitter_000_gate_0000():
    """Opt-in chain of 12 (jitter 0.0, gate 0.0): 11 gated rungs, capped tail."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.0), max_attempts=12)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.sleeps == [0.1, 0.2, 0.4, 0.8, 1.6, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0]
    assert all(s <= 8.0 + 1e-9 for s in clock.sleeps)  # capped 4.0s rung + capped 4.0s gate


def test_align_optin_budget_12_jitter_000_gate_4000():
    """Opt-in chain of 12 (jitter 0.0, gate 4.0): 11 gated rungs, capped tail."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 4.0), max_attempts=12)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.sleeps == [4.1, 4.2, 4.4, 4.8, 5.6, 6.0, 6.0, 6.0, 6.0, 6.0, 6.0]
    assert all(s <= 8.0 + 1e-9 for s in clock.sleeps)  # capped 4.0s rung + capped 4.0s gate


def test_align_optin_budget_12_jitter_100_gate_0000():
    """Opt-in chain of 12 (jitter 1.0, gate 0.0): 11 gated rungs, capped tail."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.0), max_attempts=12)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.sleeps == [0.2, 0.4, 0.8, 1.6, 3.2, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0]
    assert all(s <= 8.0 + 1e-9 for s in clock.sleeps)  # capped 4.0s rung + capped 4.0s gate


def test_align_optin_budget_12_jitter_100_gate_4000():
    """Opt-in chain of 12 (jitter 1.0, gate 4.0): 11 gated rungs, capped tail."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(FirestoreContentionExhausted) as caught:
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 4.0), max_attempts=12)
    assert caught.value.reason == 'attempts_exhausted'
    assert clock.sleeps == [4.2, 4.4, 4.8, 5.6, 7.2, 8.0, 8.0, 8.0, 8.0, 8.0, 8.0]
    assert all(s <= 8.0 + 1e-9 for s in clock.sleeps)  # capped 4.0s rung + capped 4.0s gate


def test_align_fine_recover_1_jitter_000_gate_0125():
    """Fine lattice (recover 1, jitter 0.0, gate 0.125): sleeps []."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == []


def test_align_fine_recover_1_jitter_000_gate_0375():
    """Fine lattice (recover 1, jitter 0.0, gate 0.375): sleeps []."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == []


def test_align_fine_recover_1_jitter_000_gate_0625():
    """Fine lattice (recover 1, jitter 0.0, gate 0.625): sleeps []."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == []


def test_align_fine_recover_1_jitter_000_gate_0875():
    """Fine lattice (recover 1, jitter 0.0, gate 0.875): sleeps []."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == []


def test_align_fine_recover_1_jitter_010_gate_0125():
    """Fine lattice (recover 1, jitter 0.1, gate 0.125): sleeps []."""
    clock = _Clock(jitter=0.1)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == []


def test_align_fine_recover_1_jitter_010_gate_0375():
    """Fine lattice (recover 1, jitter 0.1, gate 0.375): sleeps []."""
    clock = _Clock(jitter=0.1)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == []


def test_align_fine_recover_1_jitter_010_gate_0625():
    """Fine lattice (recover 1, jitter 0.1, gate 0.625): sleeps []."""
    clock = _Clock(jitter=0.1)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == []


def test_align_fine_recover_1_jitter_010_gate_0875():
    """Fine lattice (recover 1, jitter 0.1, gate 0.875): sleeps []."""
    clock = _Clock(jitter=0.1)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == []


def test_align_fine_recover_1_jitter_025_gate_0125():
    """Fine lattice (recover 1, jitter 0.25, gate 0.125): sleeps []."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == []


def test_align_fine_recover_1_jitter_025_gate_0375():
    """Fine lattice (recover 1, jitter 0.25, gate 0.375): sleeps []."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == []


def test_align_fine_recover_1_jitter_025_gate_0625():
    """Fine lattice (recover 1, jitter 0.25, gate 0.625): sleeps []."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == []


def test_align_fine_recover_1_jitter_025_gate_0875():
    """Fine lattice (recover 1, jitter 0.25, gate 0.875): sleeps []."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == []


def test_align_fine_recover_1_jitter_030_gate_0125():
    """Fine lattice (recover 1, jitter 0.3, gate 0.125): sleeps []."""
    clock = _Clock(jitter=0.3)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == []


def test_align_fine_recover_1_jitter_030_gate_0375():
    """Fine lattice (recover 1, jitter 0.3, gate 0.375): sleeps []."""
    clock = _Clock(jitter=0.3)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == []


def test_align_fine_recover_1_jitter_030_gate_0625():
    """Fine lattice (recover 1, jitter 0.3, gate 0.625): sleeps []."""
    clock = _Clock(jitter=0.3)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == []


def test_align_fine_recover_1_jitter_030_gate_0875():
    """Fine lattice (recover 1, jitter 0.3, gate 0.875): sleeps []."""
    clock = _Clock(jitter=0.3)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == []


def test_align_fine_recover_1_jitter_050_gate_0125():
    """Fine lattice (recover 1, jitter 0.5, gate 0.125): sleeps []."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == []


def test_align_fine_recover_1_jitter_050_gate_0375():
    """Fine lattice (recover 1, jitter 0.5, gate 0.375): sleeps []."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == []


def test_align_fine_recover_1_jitter_050_gate_0625():
    """Fine lattice (recover 1, jitter 0.5, gate 0.625): sleeps []."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == []


def test_align_fine_recover_1_jitter_050_gate_0875():
    """Fine lattice (recover 1, jitter 0.5, gate 0.875): sleeps []."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == []


def test_align_fine_recover_1_jitter_070_gate_0125():
    """Fine lattice (recover 1, jitter 0.7, gate 0.125): sleeps []."""
    clock = _Clock(jitter=0.7)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == []


def test_align_fine_recover_1_jitter_070_gate_0375():
    """Fine lattice (recover 1, jitter 0.7, gate 0.375): sleeps []."""
    clock = _Clock(jitter=0.7)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == []


def test_align_fine_recover_1_jitter_070_gate_0625():
    """Fine lattice (recover 1, jitter 0.7, gate 0.625): sleeps []."""
    clock = _Clock(jitter=0.7)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == []


def test_align_fine_recover_1_jitter_070_gate_0875():
    """Fine lattice (recover 1, jitter 0.7, gate 0.875): sleeps []."""
    clock = _Clock(jitter=0.7)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == []


def test_align_fine_recover_1_jitter_075_gate_0125():
    """Fine lattice (recover 1, jitter 0.75, gate 0.125): sleeps []."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == []


def test_align_fine_recover_1_jitter_075_gate_0375():
    """Fine lattice (recover 1, jitter 0.75, gate 0.375): sleeps []."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == []


def test_align_fine_recover_1_jitter_075_gate_0625():
    """Fine lattice (recover 1, jitter 0.75, gate 0.625): sleeps []."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == []


def test_align_fine_recover_1_jitter_075_gate_0875():
    """Fine lattice (recover 1, jitter 0.75, gate 0.875): sleeps []."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == []


def test_align_fine_recover_1_jitter_090_gate_0125():
    """Fine lattice (recover 1, jitter 0.9, gate 0.125): sleeps []."""
    clock = _Clock(jitter=0.9)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == []


def test_align_fine_recover_1_jitter_090_gate_0375():
    """Fine lattice (recover 1, jitter 0.9, gate 0.375): sleeps []."""
    clock = _Clock(jitter=0.9)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == []


def test_align_fine_recover_1_jitter_090_gate_0625():
    """Fine lattice (recover 1, jitter 0.9, gate 0.625): sleeps []."""
    clock = _Clock(jitter=0.9)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == []


def test_align_fine_recover_1_jitter_090_gate_0875():
    """Fine lattice (recover 1, jitter 0.9, gate 0.875): sleeps []."""
    clock = _Clock(jitter=0.9)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == []


def test_align_fine_recover_1_jitter_100_gate_0125():
    """Fine lattice (recover 1, jitter 1.0, gate 0.125): sleeps []."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == []


def test_align_fine_recover_1_jitter_100_gate_0375():
    """Fine lattice (recover 1, jitter 1.0, gate 0.375): sleeps []."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == []


def test_align_fine_recover_1_jitter_100_gate_0625():
    """Fine lattice (recover 1, jitter 1.0, gate 0.625): sleeps []."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == []


def test_align_fine_recover_1_jitter_100_gate_0875():
    """Fine lattice (recover 1, jitter 1.0, gate 0.875): sleeps []."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=0, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == []


def test_align_fine_recover_2_jitter_000_gate_0125():
    """Fine lattice (recover 2, jitter 0.0, gate 0.125): sleeps [0.225]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == [0.225]


def test_align_fine_recover_2_jitter_000_gate_0375():
    """Fine lattice (recover 2, jitter 0.0, gate 0.375): sleeps [0.475]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == [0.475]


def test_align_fine_recover_2_jitter_000_gate_0625():
    """Fine lattice (recover 2, jitter 0.0, gate 0.625): sleeps [0.725]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == [0.725]


def test_align_fine_recover_2_jitter_000_gate_0875():
    """Fine lattice (recover 2, jitter 0.0, gate 0.875): sleeps [0.975]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == [0.975]


def test_align_fine_recover_2_jitter_010_gate_0125():
    """Fine lattice (recover 2, jitter 0.1, gate 0.125): sleeps [0.235]."""
    clock = _Clock(jitter=0.1)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == [0.235]


def test_align_fine_recover_2_jitter_010_gate_0375():
    """Fine lattice (recover 2, jitter 0.1, gate 0.375): sleeps [0.485]."""
    clock = _Clock(jitter=0.1)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == [0.485]


def test_align_fine_recover_2_jitter_010_gate_0625():
    """Fine lattice (recover 2, jitter 0.1, gate 0.625): sleeps [0.735]."""
    clock = _Clock(jitter=0.1)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == [0.735]


def test_align_fine_recover_2_jitter_010_gate_0875():
    """Fine lattice (recover 2, jitter 0.1, gate 0.875): sleeps [0.985]."""
    clock = _Clock(jitter=0.1)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == [0.985]


def test_align_fine_recover_2_jitter_025_gate_0125():
    """Fine lattice (recover 2, jitter 0.25, gate 0.125): sleeps [0.25]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == [0.25]


def test_align_fine_recover_2_jitter_025_gate_0375():
    """Fine lattice (recover 2, jitter 0.25, gate 0.375): sleeps [0.5]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == [0.5]


def test_align_fine_recover_2_jitter_025_gate_0625():
    """Fine lattice (recover 2, jitter 0.25, gate 0.625): sleeps [0.75]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == [0.75]


def test_align_fine_recover_2_jitter_025_gate_0875():
    """Fine lattice (recover 2, jitter 0.25, gate 0.875): sleeps [1.0]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == [1.0]


def test_align_fine_recover_2_jitter_030_gate_0125():
    """Fine lattice (recover 2, jitter 0.3, gate 0.125): sleeps [0.255]."""
    clock = _Clock(jitter=0.3)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == [0.255]


def test_align_fine_recover_2_jitter_030_gate_0375():
    """Fine lattice (recover 2, jitter 0.3, gate 0.375): sleeps [0.505]."""
    clock = _Clock(jitter=0.3)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == [0.505]


def test_align_fine_recover_2_jitter_030_gate_0625():
    """Fine lattice (recover 2, jitter 0.3, gate 0.625): sleeps [0.755]."""
    clock = _Clock(jitter=0.3)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == [0.755]


def test_align_fine_recover_2_jitter_030_gate_0875():
    """Fine lattice (recover 2, jitter 0.3, gate 0.875): sleeps [1.005]."""
    clock = _Clock(jitter=0.3)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == [1.005]


def test_align_fine_recover_2_jitter_050_gate_0125():
    """Fine lattice (recover 2, jitter 0.5, gate 0.125): sleeps [0.275]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == [0.275]


def test_align_fine_recover_2_jitter_050_gate_0375():
    """Fine lattice (recover 2, jitter 0.5, gate 0.375): sleeps [0.525]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == [0.525]


def test_align_fine_recover_2_jitter_050_gate_0625():
    """Fine lattice (recover 2, jitter 0.5, gate 0.625): sleeps [0.775]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == [0.775]


def test_align_fine_recover_2_jitter_050_gate_0875():
    """Fine lattice (recover 2, jitter 0.5, gate 0.875): sleeps [1.025]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == [1.025]


def test_align_fine_recover_2_jitter_070_gate_0125():
    """Fine lattice (recover 2, jitter 0.7, gate 0.125): sleeps [0.295]."""
    clock = _Clock(jitter=0.7)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == [0.295]


def test_align_fine_recover_2_jitter_070_gate_0375():
    """Fine lattice (recover 2, jitter 0.7, gate 0.375): sleeps [0.545]."""
    clock = _Clock(jitter=0.7)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == [0.545]


def test_align_fine_recover_2_jitter_070_gate_0625():
    """Fine lattice (recover 2, jitter 0.7, gate 0.625): sleeps [0.795]."""
    clock = _Clock(jitter=0.7)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == [0.795]


def test_align_fine_recover_2_jitter_070_gate_0875():
    """Fine lattice (recover 2, jitter 0.7, gate 0.875): sleeps [1.045]."""
    clock = _Clock(jitter=0.7)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == [1.045]


def test_align_fine_recover_2_jitter_075_gate_0125():
    """Fine lattice (recover 2, jitter 0.75, gate 0.125): sleeps [0.3]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == [0.3]


def test_align_fine_recover_2_jitter_075_gate_0375():
    """Fine lattice (recover 2, jitter 0.75, gate 0.375): sleeps [0.55]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == [0.55]


def test_align_fine_recover_2_jitter_075_gate_0625():
    """Fine lattice (recover 2, jitter 0.75, gate 0.625): sleeps [0.8]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == [0.8]


def test_align_fine_recover_2_jitter_075_gate_0875():
    """Fine lattice (recover 2, jitter 0.75, gate 0.875): sleeps [1.05]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == [1.05]


def test_align_fine_recover_2_jitter_090_gate_0125():
    """Fine lattice (recover 2, jitter 0.9, gate 0.125): sleeps [0.315]."""
    clock = _Clock(jitter=0.9)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == [0.315]


def test_align_fine_recover_2_jitter_090_gate_0375():
    """Fine lattice (recover 2, jitter 0.9, gate 0.375): sleeps [0.565]."""
    clock = _Clock(jitter=0.9)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == [0.565]


def test_align_fine_recover_2_jitter_090_gate_0625():
    """Fine lattice (recover 2, jitter 0.9, gate 0.625): sleeps [0.815]."""
    clock = _Clock(jitter=0.9)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == [0.815]


def test_align_fine_recover_2_jitter_090_gate_0875():
    """Fine lattice (recover 2, jitter 0.9, gate 0.875): sleeps [1.065]."""
    clock = _Clock(jitter=0.9)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == [1.065]


def test_align_fine_recover_2_jitter_100_gate_0125():
    """Fine lattice (recover 2, jitter 1.0, gate 0.125): sleeps [0.325]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == [0.325]


def test_align_fine_recover_2_jitter_100_gate_0375():
    """Fine lattice (recover 2, jitter 1.0, gate 0.375): sleeps [0.575]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == [0.575]


def test_align_fine_recover_2_jitter_100_gate_0625():
    """Fine lattice (recover 2, jitter 1.0, gate 0.625): sleeps [0.825]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == [0.825]


def test_align_fine_recover_2_jitter_100_gate_0875():
    """Fine lattice (recover 2, jitter 1.0, gate 0.875): sleeps [1.075]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == [1.075]


def test_align_fine_recover_3_jitter_000_gate_0125():
    """Fine lattice (recover 3, jitter 0.0, gate 0.125): sleeps [0.225, 0.325]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == [0.225, 0.325]


def test_align_fine_recover_3_jitter_000_gate_0375():
    """Fine lattice (recover 3, jitter 0.0, gate 0.375): sleeps [0.475, 0.575]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == [0.475, 0.575]


def test_align_fine_recover_3_jitter_000_gate_0625():
    """Fine lattice (recover 3, jitter 0.0, gate 0.625): sleeps [0.725, 0.825]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == [0.725, 0.825]


def test_align_fine_recover_3_jitter_000_gate_0875():
    """Fine lattice (recover 3, jitter 0.0, gate 0.875): sleeps [0.975, 1.075]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == [0.975, 1.075]


def test_align_fine_recover_3_jitter_010_gate_0125():
    """Fine lattice (recover 3, jitter 0.1, gate 0.125): sleeps [0.235, 0.345]."""
    clock = _Clock(jitter=0.1)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == [0.235, 0.345]


def test_align_fine_recover_3_jitter_010_gate_0375():
    """Fine lattice (recover 3, jitter 0.1, gate 0.375): sleeps [0.485, 0.595]."""
    clock = _Clock(jitter=0.1)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == [0.485, 0.595]


def test_align_fine_recover_3_jitter_010_gate_0625():
    """Fine lattice (recover 3, jitter 0.1, gate 0.625): sleeps [0.735, 0.845]."""
    clock = _Clock(jitter=0.1)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == [0.735, 0.845]


def test_align_fine_recover_3_jitter_010_gate_0875():
    """Fine lattice (recover 3, jitter 0.1, gate 0.875): sleeps [0.985, 1.095]."""
    clock = _Clock(jitter=0.1)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == [0.985, 1.095]


def test_align_fine_recover_3_jitter_025_gate_0125():
    """Fine lattice (recover 3, jitter 0.25, gate 0.125): sleeps [0.25, 0.375]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == [0.25, 0.375]


def test_align_fine_recover_3_jitter_025_gate_0375():
    """Fine lattice (recover 3, jitter 0.25, gate 0.375): sleeps [0.5, 0.625]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == [0.5, 0.625]


def test_align_fine_recover_3_jitter_025_gate_0625():
    """Fine lattice (recover 3, jitter 0.25, gate 0.625): sleeps [0.75, 0.875]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == [0.75, 0.875]


def test_align_fine_recover_3_jitter_025_gate_0875():
    """Fine lattice (recover 3, jitter 0.25, gate 0.875): sleeps [1.0, 1.125]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == [1.0, 1.125]


def test_align_fine_recover_3_jitter_030_gate_0125():
    """Fine lattice (recover 3, jitter 0.3, gate 0.125): sleeps [0.255, 0.385]."""
    clock = _Clock(jitter=0.3)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == [0.255, 0.385]


def test_align_fine_recover_3_jitter_030_gate_0375():
    """Fine lattice (recover 3, jitter 0.3, gate 0.375): sleeps [0.505, 0.635]."""
    clock = _Clock(jitter=0.3)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == [0.505, 0.635]


def test_align_fine_recover_3_jitter_030_gate_0625():
    """Fine lattice (recover 3, jitter 0.3, gate 0.625): sleeps [0.755, 0.885]."""
    clock = _Clock(jitter=0.3)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == [0.755, 0.885]


def test_align_fine_recover_3_jitter_030_gate_0875():
    """Fine lattice (recover 3, jitter 0.3, gate 0.875): sleeps [1.005, 1.135]."""
    clock = _Clock(jitter=0.3)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == [1.005, 1.135]


def test_align_fine_recover_3_jitter_050_gate_0125():
    """Fine lattice (recover 3, jitter 0.5, gate 0.125): sleeps [0.275, 0.425]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == [0.275, 0.425]


def test_align_fine_recover_3_jitter_050_gate_0375():
    """Fine lattice (recover 3, jitter 0.5, gate 0.375): sleeps [0.525, 0.675]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == [0.525, 0.675]


def test_align_fine_recover_3_jitter_050_gate_0625():
    """Fine lattice (recover 3, jitter 0.5, gate 0.625): sleeps [0.775, 0.925]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == [0.775, 0.925]


def test_align_fine_recover_3_jitter_050_gate_0875():
    """Fine lattice (recover 3, jitter 0.5, gate 0.875): sleeps [1.025, 1.175]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == [1.025, 1.175]


def test_align_fine_recover_3_jitter_070_gate_0125():
    """Fine lattice (recover 3, jitter 0.7, gate 0.125): sleeps [0.295, 0.465]."""
    clock = _Clock(jitter=0.7)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == [0.295, 0.465]


def test_align_fine_recover_3_jitter_070_gate_0375():
    """Fine lattice (recover 3, jitter 0.7, gate 0.375): sleeps [0.545, 0.715]."""
    clock = _Clock(jitter=0.7)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == [0.545, 0.715]


def test_align_fine_recover_3_jitter_070_gate_0625():
    """Fine lattice (recover 3, jitter 0.7, gate 0.625): sleeps [0.795, 0.965]."""
    clock = _Clock(jitter=0.7)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == [0.795, 0.965]


def test_align_fine_recover_3_jitter_070_gate_0875():
    """Fine lattice (recover 3, jitter 0.7, gate 0.875): sleeps [1.045, 1.215]."""
    clock = _Clock(jitter=0.7)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == [1.045, 1.215]


def test_align_fine_recover_3_jitter_075_gate_0125():
    """Fine lattice (recover 3, jitter 0.75, gate 0.125): sleeps [0.3, 0.475]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == [0.3, 0.475]


def test_align_fine_recover_3_jitter_075_gate_0375():
    """Fine lattice (recover 3, jitter 0.75, gate 0.375): sleeps [0.55, 0.725]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == [0.55, 0.725]


def test_align_fine_recover_3_jitter_075_gate_0625():
    """Fine lattice (recover 3, jitter 0.75, gate 0.625): sleeps [0.8, 0.975]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == [0.8, 0.975]


def test_align_fine_recover_3_jitter_075_gate_0875():
    """Fine lattice (recover 3, jitter 0.75, gate 0.875): sleeps [1.05, 1.225]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == [1.05, 1.225]


def test_align_fine_recover_3_jitter_090_gate_0125():
    """Fine lattice (recover 3, jitter 0.9, gate 0.125): sleeps [0.315, 0.505]."""
    clock = _Clock(jitter=0.9)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == [0.315, 0.505]


def test_align_fine_recover_3_jitter_090_gate_0375():
    """Fine lattice (recover 3, jitter 0.9, gate 0.375): sleeps [0.565, 0.755]."""
    clock = _Clock(jitter=0.9)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == [0.565, 0.755]


def test_align_fine_recover_3_jitter_090_gate_0625():
    """Fine lattice (recover 3, jitter 0.9, gate 0.625): sleeps [0.815, 1.005]."""
    clock = _Clock(jitter=0.9)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == [0.815, 1.005]


def test_align_fine_recover_3_jitter_090_gate_0875():
    """Fine lattice (recover 3, jitter 0.9, gate 0.875): sleeps [1.065, 1.255]."""
    clock = _Clock(jitter=0.9)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == [1.065, 1.255]


def test_align_fine_recover_3_jitter_100_gate_0125():
    """Fine lattice (recover 3, jitter 1.0, gate 0.125): sleeps [0.325, 0.525]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == [0.325, 0.525]


def test_align_fine_recover_3_jitter_100_gate_0375():
    """Fine lattice (recover 3, jitter 1.0, gate 0.375): sleeps [0.575, 0.775]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == [0.575, 0.775]


def test_align_fine_recover_3_jitter_100_gate_0625():
    """Fine lattice (recover 3, jitter 1.0, gate 0.625): sleeps [0.825, 1.025]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == [0.825, 1.025]


def test_align_fine_recover_3_jitter_100_gate_0875():
    """Fine lattice (recover 3, jitter 1.0, gate 0.875): sleeps [1.075, 1.275]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == [1.075, 1.275]


def test_align_fine_recover_4_jitter_000_gate_0125():
    """Fine lattice (recover 4, jitter 0.0, gate 0.125): sleeps [0.225, 0.325, 0.525]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == [0.225, 0.325, 0.525]


def test_align_fine_recover_4_jitter_000_gate_0375():
    """Fine lattice (recover 4, jitter 0.0, gate 0.375): sleeps [0.475, 0.575, 0.775]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == [0.475, 0.575, 0.775]


def test_align_fine_recover_4_jitter_000_gate_0625():
    """Fine lattice (recover 4, jitter 0.0, gate 0.625): sleeps [0.725, 0.825, 1.025]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == [0.725, 0.825, 1.025]


def test_align_fine_recover_4_jitter_000_gate_0875():
    """Fine lattice (recover 4, jitter 0.0, gate 0.875): sleeps [0.975, 1.075, 1.275]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == [0.975, 1.075, 1.275]


def test_align_fine_recover_4_jitter_010_gate_0125():
    """Fine lattice (recover 4, jitter 0.1, gate 0.125): sleeps [0.235, 0.345, 0.565]."""
    clock = _Clock(jitter=0.1)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == [0.235, 0.345, 0.565]


def test_align_fine_recover_4_jitter_010_gate_0375():
    """Fine lattice (recover 4, jitter 0.1, gate 0.375): sleeps [0.485, 0.595, 0.815]."""
    clock = _Clock(jitter=0.1)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == [0.485, 0.595, 0.815]


def test_align_fine_recover_4_jitter_010_gate_0625():
    """Fine lattice (recover 4, jitter 0.1, gate 0.625): sleeps [0.735, 0.845, 1.065]."""
    clock = _Clock(jitter=0.1)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == [0.735, 0.845, 1.065]


def test_align_fine_recover_4_jitter_010_gate_0875():
    """Fine lattice (recover 4, jitter 0.1, gate 0.875): sleeps [0.985, 1.095, 1.315]."""
    clock = _Clock(jitter=0.1)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == [0.985, 1.095, 1.315]


def test_align_fine_recover_4_jitter_025_gate_0125():
    """Fine lattice (recover 4, jitter 0.25, gate 0.125): sleeps [0.25, 0.375, 0.625]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == [0.25, 0.375, 0.625]


def test_align_fine_recover_4_jitter_025_gate_0375():
    """Fine lattice (recover 4, jitter 0.25, gate 0.375): sleeps [0.5, 0.625, 0.875]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == [0.5, 0.625, 0.875]


def test_align_fine_recover_4_jitter_025_gate_0625():
    """Fine lattice (recover 4, jitter 0.25, gate 0.625): sleeps [0.75, 0.875, 1.125]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == [0.75, 0.875, 1.125]


def test_align_fine_recover_4_jitter_025_gate_0875():
    """Fine lattice (recover 4, jitter 0.25, gate 0.875): sleeps [1.0, 1.125, 1.375]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == [1.0, 1.125, 1.375]


def test_align_fine_recover_4_jitter_030_gate_0125():
    """Fine lattice (recover 4, jitter 0.3, gate 0.125): sleeps [0.255, 0.385, 0.645]."""
    clock = _Clock(jitter=0.3)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == [0.255, 0.385, 0.645]


def test_align_fine_recover_4_jitter_030_gate_0375():
    """Fine lattice (recover 4, jitter 0.3, gate 0.375): sleeps [0.505, 0.635, 0.895]."""
    clock = _Clock(jitter=0.3)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == [0.505, 0.635, 0.895]


def test_align_fine_recover_4_jitter_030_gate_0625():
    """Fine lattice (recover 4, jitter 0.3, gate 0.625): sleeps [0.755, 0.885, 1.145]."""
    clock = _Clock(jitter=0.3)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == [0.755, 0.885, 1.145]


def test_align_fine_recover_4_jitter_030_gate_0875():
    """Fine lattice (recover 4, jitter 0.3, gate 0.875): sleeps [1.005, 1.135, 1.395]."""
    clock = _Clock(jitter=0.3)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == [1.005, 1.135, 1.395]


def test_align_fine_recover_4_jitter_050_gate_0125():
    """Fine lattice (recover 4, jitter 0.5, gate 0.125): sleeps [0.275, 0.425, 0.725]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == [0.275, 0.425, 0.725]


def test_align_fine_recover_4_jitter_050_gate_0375():
    """Fine lattice (recover 4, jitter 0.5, gate 0.375): sleeps [0.525, 0.675, 0.975]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == [0.525, 0.675, 0.975]


def test_align_fine_recover_4_jitter_050_gate_0625():
    """Fine lattice (recover 4, jitter 0.5, gate 0.625): sleeps [0.775, 0.925, 1.225]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == [0.775, 0.925, 1.225]


def test_align_fine_recover_4_jitter_050_gate_0875():
    """Fine lattice (recover 4, jitter 0.5, gate 0.875): sleeps [1.025, 1.175, 1.475]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == [1.025, 1.175, 1.475]


def test_align_fine_recover_4_jitter_070_gate_0125():
    """Fine lattice (recover 4, jitter 0.7, gate 0.125): sleeps [0.295, 0.465, 0.805]."""
    clock = _Clock(jitter=0.7)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == [0.295, 0.465, 0.805]


def test_align_fine_recover_4_jitter_070_gate_0375():
    """Fine lattice (recover 4, jitter 0.7, gate 0.375): sleeps [0.545, 0.715, 1.055]."""
    clock = _Clock(jitter=0.7)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == [0.545, 0.715, 1.055]


def test_align_fine_recover_4_jitter_070_gate_0625():
    """Fine lattice (recover 4, jitter 0.7, gate 0.625): sleeps [0.795, 0.965, 1.305]."""
    clock = _Clock(jitter=0.7)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == [0.795, 0.965, 1.305]


def test_align_fine_recover_4_jitter_070_gate_0875():
    """Fine lattice (recover 4, jitter 0.7, gate 0.875): sleeps [1.045, 1.215, 1.555]."""
    clock = _Clock(jitter=0.7)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == [1.045, 1.215, 1.555]


def test_align_fine_recover_4_jitter_075_gate_0125():
    """Fine lattice (recover 4, jitter 0.75, gate 0.125): sleeps [0.3, 0.475, 0.825]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == [0.3, 0.475, 0.825]


def test_align_fine_recover_4_jitter_075_gate_0375():
    """Fine lattice (recover 4, jitter 0.75, gate 0.375): sleeps [0.55, 0.725, 1.075]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == [0.55, 0.725, 1.075]


def test_align_fine_recover_4_jitter_075_gate_0625():
    """Fine lattice (recover 4, jitter 0.75, gate 0.625): sleeps [0.8, 0.975, 1.325]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == [0.8, 0.975, 1.325]


def test_align_fine_recover_4_jitter_075_gate_0875():
    """Fine lattice (recover 4, jitter 0.75, gate 0.875): sleeps [1.05, 1.225, 1.575]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == [1.05, 1.225, 1.575]


def test_align_fine_recover_4_jitter_090_gate_0125():
    """Fine lattice (recover 4, jitter 0.9, gate 0.125): sleeps [0.315, 0.505, 0.885]."""
    clock = _Clock(jitter=0.9)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == [0.315, 0.505, 0.885]


def test_align_fine_recover_4_jitter_090_gate_0375():
    """Fine lattice (recover 4, jitter 0.9, gate 0.375): sleeps [0.565, 0.755, 1.135]."""
    clock = _Clock(jitter=0.9)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == [0.565, 0.755, 1.135]


def test_align_fine_recover_4_jitter_090_gate_0625():
    """Fine lattice (recover 4, jitter 0.9, gate 0.625): sleeps [0.815, 1.005, 1.385]."""
    clock = _Clock(jitter=0.9)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == [0.815, 1.005, 1.385]


def test_align_fine_recover_4_jitter_090_gate_0875():
    """Fine lattice (recover 4, jitter 0.9, gate 0.875): sleeps [1.065, 1.255, 1.635]."""
    clock = _Clock(jitter=0.9)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == [1.065, 1.255, 1.635]


def test_align_fine_recover_4_jitter_100_gate_0125():
    """Fine lattice (recover 4, jitter 1.0, gate 0.125): sleeps [0.325, 0.525, 0.925]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == [0.325, 0.525, 0.925]


def test_align_fine_recover_4_jitter_100_gate_0375():
    """Fine lattice (recover 4, jitter 1.0, gate 0.375): sleeps [0.575, 0.775, 1.175]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == [0.575, 0.775, 1.175]


def test_align_fine_recover_4_jitter_100_gate_0625():
    """Fine lattice (recover 4, jitter 1.0, gate 0.625): sleeps [0.825, 1.025, 1.425]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == [0.825, 1.025, 1.425]


def test_align_fine_recover_4_jitter_100_gate_0875():
    """Fine lattice (recover 4, jitter 1.0, gate 0.875): sleeps [1.075, 1.275, 1.675]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == [1.075, 1.275, 1.675]


def test_align_fine_recover_5_jitter_000_gate_0125():
    """Fine lattice (recover 5, jitter 0.0, gate 0.125): sleeps [0.225, 0.325, 0.525, 0.925]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == [0.225, 0.325, 0.525, 0.925]


def test_align_fine_recover_5_jitter_000_gate_0375():
    """Fine lattice (recover 5, jitter 0.0, gate 0.375): sleeps [0.475, 0.575, 0.775, 1.175]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == [0.475, 0.575, 0.775, 1.175]


def test_align_fine_recover_5_jitter_000_gate_0625():
    """Fine lattice (recover 5, jitter 0.0, gate 0.625): sleeps [0.725, 0.825, 1.025, 1.425]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == [0.725, 0.825, 1.025, 1.425]


def test_align_fine_recover_5_jitter_000_gate_0875():
    """Fine lattice (recover 5, jitter 0.0, gate 0.875): sleeps [0.975, 1.075, 1.275, 1.675]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == [0.975, 1.075, 1.275, 1.675]


def test_align_fine_recover_5_jitter_010_gate_0125():
    """Fine lattice (recover 5, jitter 0.1, gate 0.125): sleeps [0.235, 0.345, 0.565, 1.005]."""
    clock = _Clock(jitter=0.1)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == [0.235, 0.345, 0.565, 1.005]


def test_align_fine_recover_5_jitter_010_gate_0375():
    """Fine lattice (recover 5, jitter 0.1, gate 0.375): sleeps [0.485, 0.595, 0.815, 1.255]."""
    clock = _Clock(jitter=0.1)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == [0.485, 0.595, 0.815, 1.255]


def test_align_fine_recover_5_jitter_010_gate_0625():
    """Fine lattice (recover 5, jitter 0.1, gate 0.625): sleeps [0.735, 0.845, 1.065, 1.505]."""
    clock = _Clock(jitter=0.1)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == [0.735, 0.845, 1.065, 1.505]


def test_align_fine_recover_5_jitter_010_gate_0875():
    """Fine lattice (recover 5, jitter 0.1, gate 0.875): sleeps [0.985, 1.095, 1.315, 1.755]."""
    clock = _Clock(jitter=0.1)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == [0.985, 1.095, 1.315, 1.755]


def test_align_fine_recover_5_jitter_025_gate_0125():
    """Fine lattice (recover 5, jitter 0.25, gate 0.125): sleeps [0.25, 0.375, 0.625, 1.125]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == [0.25, 0.375, 0.625, 1.125]


def test_align_fine_recover_5_jitter_025_gate_0375():
    """Fine lattice (recover 5, jitter 0.25, gate 0.375): sleeps [0.5, 0.625, 0.875, 1.375]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == [0.5, 0.625, 0.875, 1.375]


def test_align_fine_recover_5_jitter_025_gate_0625():
    """Fine lattice (recover 5, jitter 0.25, gate 0.625): sleeps [0.75, 0.875, 1.125, 1.625]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == [0.75, 0.875, 1.125, 1.625]


def test_align_fine_recover_5_jitter_025_gate_0875():
    """Fine lattice (recover 5, jitter 0.25, gate 0.875): sleeps [1.0, 1.125, 1.375, 1.875]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == [1.0, 1.125, 1.375, 1.875]


def test_align_fine_recover_5_jitter_030_gate_0125():
    """Fine lattice (recover 5, jitter 0.3, gate 0.125): sleeps [0.255, 0.385, 0.645, 1.165]."""
    clock = _Clock(jitter=0.3)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == [0.255, 0.385, 0.645, 1.165]


def test_align_fine_recover_5_jitter_030_gate_0375():
    """Fine lattice (recover 5, jitter 0.3, gate 0.375): sleeps [0.505, 0.635, 0.895, 1.415]."""
    clock = _Clock(jitter=0.3)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == [0.505, 0.635, 0.895, 1.415]


def test_align_fine_recover_5_jitter_030_gate_0625():
    """Fine lattice (recover 5, jitter 0.3, gate 0.625): sleeps [0.755, 0.885, 1.145, 1.665]."""
    clock = _Clock(jitter=0.3)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == [0.755, 0.885, 1.145, 1.665]


def test_align_fine_recover_5_jitter_030_gate_0875():
    """Fine lattice (recover 5, jitter 0.3, gate 0.875): sleeps [1.005, 1.135, 1.395, 1.915]."""
    clock = _Clock(jitter=0.3)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == [1.005, 1.135, 1.395, 1.915]


def test_align_fine_recover_5_jitter_050_gate_0125():
    """Fine lattice (recover 5, jitter 0.5, gate 0.125): sleeps [0.275, 0.425, 0.725, 1.325]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == [0.275, 0.425, 0.725, 1.325]


def test_align_fine_recover_5_jitter_050_gate_0375():
    """Fine lattice (recover 5, jitter 0.5, gate 0.375): sleeps [0.525, 0.675, 0.975, 1.575]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == [0.525, 0.675, 0.975, 1.575]


def test_align_fine_recover_5_jitter_050_gate_0625():
    """Fine lattice (recover 5, jitter 0.5, gate 0.625): sleeps [0.775, 0.925, 1.225, 1.825]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == [0.775, 0.925, 1.225, 1.825]


def test_align_fine_recover_5_jitter_050_gate_0875():
    """Fine lattice (recover 5, jitter 0.5, gate 0.875): sleeps [1.025, 1.175, 1.475, 2.075]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == [1.025, 1.175, 1.475, 2.075]


def test_align_fine_recover_5_jitter_070_gate_0125():
    """Fine lattice (recover 5, jitter 0.7, gate 0.125): sleeps [0.295, 0.465, 0.805, 1.485]."""
    clock = _Clock(jitter=0.7)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == [0.295, 0.465, 0.805, 1.485]


def test_align_fine_recover_5_jitter_070_gate_0375():
    """Fine lattice (recover 5, jitter 0.7, gate 0.375): sleeps [0.545, 0.715, 1.055, 1.735]."""
    clock = _Clock(jitter=0.7)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == [0.545, 0.715, 1.055, 1.735]


def test_align_fine_recover_5_jitter_070_gate_0625():
    """Fine lattice (recover 5, jitter 0.7, gate 0.625): sleeps [0.795, 0.965, 1.305, 1.985]."""
    clock = _Clock(jitter=0.7)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == [0.795, 0.965, 1.305, 1.985]


def test_align_fine_recover_5_jitter_070_gate_0875():
    """Fine lattice (recover 5, jitter 0.7, gate 0.875): sleeps [1.045, 1.215, 1.555, 2.235]."""
    clock = _Clock(jitter=0.7)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == [1.045, 1.215, 1.555, 2.235]


def test_align_fine_recover_5_jitter_075_gate_0125():
    """Fine lattice (recover 5, jitter 0.75, gate 0.125): sleeps [0.3, 0.475, 0.825, 1.525]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == [0.3, 0.475, 0.825, 1.525]


def test_align_fine_recover_5_jitter_075_gate_0375():
    """Fine lattice (recover 5, jitter 0.75, gate 0.375): sleeps [0.55, 0.725, 1.075, 1.775]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == [0.55, 0.725, 1.075, 1.775]


def test_align_fine_recover_5_jitter_075_gate_0625():
    """Fine lattice (recover 5, jitter 0.75, gate 0.625): sleeps [0.8, 0.975, 1.325, 2.025]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == [0.8, 0.975, 1.325, 2.025]


def test_align_fine_recover_5_jitter_075_gate_0875():
    """Fine lattice (recover 5, jitter 0.75, gate 0.875): sleeps [1.05, 1.225, 1.575, 2.275]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == [1.05, 1.225, 1.575, 2.275]


def test_align_fine_recover_5_jitter_090_gate_0125():
    """Fine lattice (recover 5, jitter 0.9, gate 0.125): sleeps [0.315, 0.505, 0.885, 1.645]."""
    clock = _Clock(jitter=0.9)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == [0.315, 0.505, 0.885, 1.645]


def test_align_fine_recover_5_jitter_090_gate_0375():
    """Fine lattice (recover 5, jitter 0.9, gate 0.375): sleeps [0.565, 0.755, 1.135, 1.895]."""
    clock = _Clock(jitter=0.9)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == [0.565, 0.755, 1.135, 1.895]


def test_align_fine_recover_5_jitter_090_gate_0625():
    """Fine lattice (recover 5, jitter 0.9, gate 0.625): sleeps [0.815, 1.005, 1.385, 2.145]."""
    clock = _Clock(jitter=0.9)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == [0.815, 1.005, 1.385, 2.145]


def test_align_fine_recover_5_jitter_090_gate_0875():
    """Fine lattice (recover 5, jitter 0.9, gate 0.875): sleeps [1.065, 1.255, 1.635, 2.395]."""
    clock = _Clock(jitter=0.9)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == [1.065, 1.255, 1.635, 2.395]


def test_align_fine_recover_5_jitter_100_gate_0125():
    """Fine lattice (recover 5, jitter 1.0, gate 0.125): sleeps [0.325, 0.525, 0.925, 1.725]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.125))
    assert result == 'ok'
    assert clock.sleeps == [0.325, 0.525, 0.925, 1.725]


def test_align_fine_recover_5_jitter_100_gate_0375():
    """Fine lattice (recover 5, jitter 1.0, gate 0.375): sleeps [0.575, 0.775, 1.175, 1.975]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.375))
    assert result == 'ok'
    assert clock.sleeps == [0.575, 0.775, 1.175, 1.975]


def test_align_fine_recover_5_jitter_100_gate_0625():
    """Fine lattice (recover 5, jitter 1.0, gate 0.625): sleeps [0.825, 1.025, 1.425, 2.225]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.625))
    assert result == 'ok'
    assert clock.sleeps == [0.825, 1.025, 1.425, 2.225]


def test_align_fine_recover_5_jitter_100_gate_0875():
    """Fine lattice (recover 5, jitter 1.0, gate 0.875): sleeps [1.075, 1.275, 1.675, 2.475]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.875))
    assert result == 'ok'
    assert clock.sleeps == [1.075, 1.275, 1.675, 2.475]


def test_align_fine_recover_6_jitter_000_gate_0125():
    """Fine lattice (recover 6, jitter 0.0, gate 0.125): sleeps [0.225, 0.325, 0.525, 0.925, 1.725]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.125), max_attempts=6)
    assert result == 'ok'
    assert clock.sleeps == [0.225, 0.325, 0.525, 0.925, 1.725]


def test_align_fine_recover_6_jitter_000_gate_0375():
    """Fine lattice (recover 6, jitter 0.0, gate 0.375): sleeps [0.475, 0.575, 0.775, 1.175, 1.975]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.375), max_attempts=6)
    assert result == 'ok'
    assert clock.sleeps == [0.475, 0.575, 0.775, 1.175, 1.975]


def test_align_fine_recover_6_jitter_000_gate_0625():
    """Fine lattice (recover 6, jitter 0.0, gate 0.625): sleeps [0.725, 0.825, 1.025, 1.425, 2.225]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.625), max_attempts=6)
    assert result == 'ok'
    assert clock.sleeps == [0.725, 0.825, 1.025, 1.425, 2.225]


def test_align_fine_recover_6_jitter_000_gate_0875():
    """Fine lattice (recover 6, jitter 0.0, gate 0.875): sleeps [0.975, 1.075, 1.275, 1.675, 2.475]."""
    clock = _Clock(jitter=0.0)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.875), max_attempts=6)
    assert result == 'ok'
    assert clock.sleeps == [0.975, 1.075, 1.275, 1.675, 2.475]


def test_align_fine_recover_6_jitter_010_gate_0125():
    """Fine lattice (recover 6, jitter 0.1, gate 0.125): sleeps [0.235, 0.345, 0.565, 1.005, 1.885]."""
    clock = _Clock(jitter=0.1)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.125), max_attempts=6)
    assert result == 'ok'
    assert clock.sleeps == [0.235, 0.345, 0.565, 1.005, 1.885]


def test_align_fine_recover_6_jitter_010_gate_0375():
    """Fine lattice (recover 6, jitter 0.1, gate 0.375): sleeps [0.485, 0.595, 0.815, 1.255, 2.135]."""
    clock = _Clock(jitter=0.1)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.375), max_attempts=6)
    assert result == 'ok'
    assert clock.sleeps == [0.485, 0.595, 0.815, 1.255, 2.135]


def test_align_fine_recover_6_jitter_010_gate_0625():
    """Fine lattice (recover 6, jitter 0.1, gate 0.625): sleeps [0.735, 0.845, 1.065, 1.505, 2.385]."""
    clock = _Clock(jitter=0.1)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.625), max_attempts=6)
    assert result == 'ok'
    assert clock.sleeps == [0.735, 0.845, 1.065, 1.505, 2.385]


def test_align_fine_recover_6_jitter_010_gate_0875():
    """Fine lattice (recover 6, jitter 0.1, gate 0.875): sleeps [0.985, 1.095, 1.315, 1.755, 2.635]."""
    clock = _Clock(jitter=0.1)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.875), max_attempts=6)
    assert result == 'ok'
    assert clock.sleeps == [0.985, 1.095, 1.315, 1.755, 2.635]


def test_align_fine_recover_6_jitter_025_gate_0125():
    """Fine lattice (recover 6, jitter 0.25, gate 0.125): sleeps [0.25, 0.375, 0.625, 1.125, 2.125]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.125), max_attempts=6)
    assert result == 'ok'
    assert clock.sleeps == [0.25, 0.375, 0.625, 1.125, 2.125]


def test_align_fine_recover_6_jitter_025_gate_0375():
    """Fine lattice (recover 6, jitter 0.25, gate 0.375): sleeps [0.5, 0.625, 0.875, 1.375, 2.375]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.375), max_attempts=6)
    assert result == 'ok'
    assert clock.sleeps == [0.5, 0.625, 0.875, 1.375, 2.375]


def test_align_fine_recover_6_jitter_025_gate_0625():
    """Fine lattice (recover 6, jitter 0.25, gate 0.625): sleeps [0.75, 0.875, 1.125, 1.625, 2.625]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.625), max_attempts=6)
    assert result == 'ok'
    assert clock.sleeps == [0.75, 0.875, 1.125, 1.625, 2.625]


def test_align_fine_recover_6_jitter_025_gate_0875():
    """Fine lattice (recover 6, jitter 0.25, gate 0.875): sleeps [1.0, 1.125, 1.375, 1.875, 2.875]."""
    clock = _Clock(jitter=0.25)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.875), max_attempts=6)
    assert result == 'ok'
    assert clock.sleeps == [1.0, 1.125, 1.375, 1.875, 2.875]


def test_align_fine_recover_6_jitter_030_gate_0125():
    """Fine lattice (recover 6, jitter 0.3, gate 0.125): sleeps [0.255, 0.385, 0.645, 1.165, 2.205]."""
    clock = _Clock(jitter=0.3)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.125), max_attempts=6)
    assert result == 'ok'
    assert clock.sleeps == [0.255, 0.385, 0.645, 1.165, 2.205]


def test_align_fine_recover_6_jitter_030_gate_0375():
    """Fine lattice (recover 6, jitter 0.3, gate 0.375): sleeps [0.505, 0.635, 0.895, 1.415, 2.455]."""
    clock = _Clock(jitter=0.3)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.375), max_attempts=6)
    assert result == 'ok'
    assert clock.sleeps == [0.505, 0.635, 0.895, 1.415, 2.455]


def test_align_fine_recover_6_jitter_030_gate_0625():
    """Fine lattice (recover 6, jitter 0.3, gate 0.625): sleeps [0.755, 0.885, 1.145, 1.665, 2.705]."""
    clock = _Clock(jitter=0.3)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.625), max_attempts=6)
    assert result == 'ok'
    assert clock.sleeps == [0.755, 0.885, 1.145, 1.665, 2.705]


def test_align_fine_recover_6_jitter_030_gate_0875():
    """Fine lattice (recover 6, jitter 0.3, gate 0.875): sleeps [1.005, 1.135, 1.395, 1.915, 2.955]."""
    clock = _Clock(jitter=0.3)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.875), max_attempts=6)
    assert result == 'ok'
    assert clock.sleeps == [1.005, 1.135, 1.395, 1.915, 2.955]


def test_align_fine_recover_6_jitter_050_gate_0125():
    """Fine lattice (recover 6, jitter 0.5, gate 0.125): sleeps [0.275, 0.425, 0.725, 1.325, 2.525]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.125), max_attempts=6)
    assert result == 'ok'
    assert clock.sleeps == [0.275, 0.425, 0.725, 1.325, 2.525]


def test_align_fine_recover_6_jitter_050_gate_0375():
    """Fine lattice (recover 6, jitter 0.5, gate 0.375): sleeps [0.525, 0.675, 0.975, 1.575, 2.775]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.375), max_attempts=6)
    assert result == 'ok'
    assert clock.sleeps == [0.525, 0.675, 0.975, 1.575, 2.775]


def test_align_fine_recover_6_jitter_050_gate_0625():
    """Fine lattice (recover 6, jitter 0.5, gate 0.625): sleeps [0.775, 0.925, 1.225, 1.825, 3.025]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.625), max_attempts=6)
    assert result == 'ok'
    assert clock.sleeps == [0.775, 0.925, 1.225, 1.825, 3.025]


def test_align_fine_recover_6_jitter_050_gate_0875():
    """Fine lattice (recover 6, jitter 0.5, gate 0.875): sleeps [1.025, 1.175, 1.475, 2.075, 3.275]."""
    clock = _Clock(jitter=0.5)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.875), max_attempts=6)
    assert result == 'ok'
    assert clock.sleeps == [1.025, 1.175, 1.475, 2.075, 3.275]


def test_align_fine_recover_6_jitter_070_gate_0125():
    """Fine lattice (recover 6, jitter 0.7, gate 0.125): sleeps [0.295, 0.465, 0.805, 1.485, 2.845]."""
    clock = _Clock(jitter=0.7)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.125), max_attempts=6)
    assert result == 'ok'
    assert clock.sleeps == [0.295, 0.465, 0.805, 1.485, 2.845]


def test_align_fine_recover_6_jitter_070_gate_0375():
    """Fine lattice (recover 6, jitter 0.7, gate 0.375): sleeps [0.545, 0.715, 1.055, 1.735, 3.095]."""
    clock = _Clock(jitter=0.7)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.375), max_attempts=6)
    assert result == 'ok'
    assert clock.sleeps == [0.545, 0.715, 1.055, 1.735, 3.095]


def test_align_fine_recover_6_jitter_070_gate_0625():
    """Fine lattice (recover 6, jitter 0.7, gate 0.625): sleeps [0.795, 0.965, 1.305, 1.985, 3.345]."""
    clock = _Clock(jitter=0.7)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.625), max_attempts=6)
    assert result == 'ok'
    assert clock.sleeps == [0.795, 0.965, 1.305, 1.985, 3.345]


def test_align_fine_recover_6_jitter_070_gate_0875():
    """Fine lattice (recover 6, jitter 0.7, gate 0.875): sleeps [1.045, 1.215, 1.555, 2.235, 3.595]."""
    clock = _Clock(jitter=0.7)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.875), max_attempts=6)
    assert result == 'ok'
    assert clock.sleeps == [1.045, 1.215, 1.555, 2.235, 3.595]


def test_align_fine_recover_6_jitter_075_gate_0125():
    """Fine lattice (recover 6, jitter 0.75, gate 0.125): sleeps [0.3, 0.475, 0.825, 1.525, 2.925]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.125), max_attempts=6)
    assert result == 'ok'
    assert clock.sleeps == [0.3, 0.475, 0.825, 1.525, 2.925]


def test_align_fine_recover_6_jitter_075_gate_0375():
    """Fine lattice (recover 6, jitter 0.75, gate 0.375): sleeps [0.55, 0.725, 1.075, 1.775, 3.175]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.375), max_attempts=6)
    assert result == 'ok'
    assert clock.sleeps == [0.55, 0.725, 1.075, 1.775, 3.175]


def test_align_fine_recover_6_jitter_075_gate_0625():
    """Fine lattice (recover 6, jitter 0.75, gate 0.625): sleeps [0.8, 0.975, 1.325, 2.025, 3.425]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.625), max_attempts=6)
    assert result == 'ok'
    assert clock.sleeps == [0.8, 0.975, 1.325, 2.025, 3.425]


def test_align_fine_recover_6_jitter_075_gate_0875():
    """Fine lattice (recover 6, jitter 0.75, gate 0.875): sleeps [1.05, 1.225, 1.575, 2.275, 3.675]."""
    clock = _Clock(jitter=0.75)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.875), max_attempts=6)
    assert result == 'ok'
    assert clock.sleeps == [1.05, 1.225, 1.575, 2.275, 3.675]


def test_align_fine_recover_6_jitter_090_gate_0125():
    """Fine lattice (recover 6, jitter 0.9, gate 0.125): sleeps [0.315, 0.505, 0.885, 1.645, 3.165]."""
    clock = _Clock(jitter=0.9)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.125), max_attempts=6)
    assert result == 'ok'
    assert clock.sleeps == [0.315, 0.505, 0.885, 1.645, 3.165]


def test_align_fine_recover_6_jitter_090_gate_0375():
    """Fine lattice (recover 6, jitter 0.9, gate 0.375): sleeps [0.565, 0.755, 1.135, 1.895, 3.415]."""
    clock = _Clock(jitter=0.9)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.375), max_attempts=6)
    assert result == 'ok'
    assert clock.sleeps == [0.565, 0.755, 1.135, 1.895, 3.415]


def test_align_fine_recover_6_jitter_090_gate_0625():
    """Fine lattice (recover 6, jitter 0.9, gate 0.625): sleeps [0.815, 1.005, 1.385, 2.145, 3.665]."""
    clock = _Clock(jitter=0.9)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.625), max_attempts=6)
    assert result == 'ok'
    assert clock.sleeps == [0.815, 1.005, 1.385, 2.145, 3.665]


def test_align_fine_recover_6_jitter_090_gate_0875():
    """Fine lattice (recover 6, jitter 0.9, gate 0.875): sleeps [1.065, 1.255, 1.635, 2.395, 3.915]."""
    clock = _Clock(jitter=0.9)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.875), max_attempts=6)
    assert result == 'ok'
    assert clock.sleeps == [1.065, 1.255, 1.635, 2.395, 3.915]


def test_align_fine_recover_6_jitter_100_gate_0125():
    """Fine lattice (recover 6, jitter 1.0, gate 0.125): sleeps [0.325, 0.525, 0.925, 1.725, 3.325]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.125), max_attempts=6)
    assert result == 'ok'
    assert clock.sleeps == [0.325, 0.525, 0.925, 1.725, 3.325]


def test_align_fine_recover_6_jitter_100_gate_0375():
    """Fine lattice (recover 6, jitter 1.0, gate 0.375): sleeps [0.575, 0.775, 1.175, 1.975, 3.575]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.375), max_attempts=6)
    assert result == 'ok'
    assert clock.sleeps == [0.575, 0.775, 1.175, 1.975, 3.575]


def test_align_fine_recover_6_jitter_100_gate_0625():
    """Fine lattice (recover 6, jitter 1.0, gate 0.625): sleeps [0.825, 1.025, 1.425, 2.225, 3.825]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.625), max_attempts=6)
    assert result == 'ok'
    assert clock.sleeps == [0.825, 1.025, 1.425, 2.225, 3.825]


def test_align_fine_recover_6_jitter_100_gate_0875():
    """Fine lattice (recover 6, jitter 1.0, gate 0.875): sleeps [1.075, 1.275, 1.675, 2.475, 4.075]."""
    clock = _Clock(jitter=1.0)
    result = _chain(clock, aborts=5, gate=_gate_recorder(clock, 0.875), max_attempts=6)
    assert result == 'ok'
    assert clock.sleeps == [1.075, 1.275, 1.675, 2.475, 4.075]


def test_align_noncontention_at_2_jitter_000_gate_0000():
    """Non-contention failure at attempt 2 (jitter 0.0, gate 0.0): 1 gated rungs then the raise, no gate on the dying attempt."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(ValueError):
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.0), fail_non_contention_at=2)
    assert clock.gate_calls == [1]
    assert clock.sleeps == [0.1]


def test_align_noncontention_at_2_jitter_000_gate_0500():
    """Non-contention failure at attempt 2 (jitter 0.0, gate 0.5): 1 gated rungs then the raise, no gate on the dying attempt."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(ValueError):
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.5), fail_non_contention_at=2)
    assert clock.gate_calls == [1]
    assert clock.sleeps == [0.6]


def test_align_noncontention_at_2_jitter_100_gate_0000():
    """Non-contention failure at attempt 2 (jitter 1.0, gate 0.0): 1 gated rungs then the raise, no gate on the dying attempt."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(ValueError):
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.0), fail_non_contention_at=2)
    assert clock.gate_calls == [1]
    assert clock.sleeps == [0.2]


def test_align_noncontention_at_2_jitter_100_gate_0500():
    """Non-contention failure at attempt 2 (jitter 1.0, gate 0.5): 1 gated rungs then the raise, no gate on the dying attempt."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(ValueError):
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.5), fail_non_contention_at=2)
    assert clock.gate_calls == [1]
    assert clock.sleeps == [0.7]


def test_align_noncontention_at_3_jitter_000_gate_0000():
    """Non-contention failure at attempt 3 (jitter 0.0, gate 0.0): 2 gated rungs then the raise, no gate on the dying attempt."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(ValueError):
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.0), fail_non_contention_at=3)
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [0.1, 0.2]


def test_align_noncontention_at_3_jitter_000_gate_0500():
    """Non-contention failure at attempt 3 (jitter 0.0, gate 0.5): 2 gated rungs then the raise, no gate on the dying attempt."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(ValueError):
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.5), fail_non_contention_at=3)
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [0.6, 0.7]


def test_align_noncontention_at_3_jitter_100_gate_0000():
    """Non-contention failure at attempt 3 (jitter 1.0, gate 0.0): 2 gated rungs then the raise, no gate on the dying attempt."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(ValueError):
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.0), fail_non_contention_at=3)
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [0.2, 0.4]


def test_align_noncontention_at_3_jitter_100_gate_0500():
    """Non-contention failure at attempt 3 (jitter 1.0, gate 0.5): 2 gated rungs then the raise, no gate on the dying attempt."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(ValueError):
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.5), fail_non_contention_at=3)
    assert clock.gate_calls == [1, 2]
    assert clock.sleeps == [0.7, 0.9]


def test_align_noncontention_at_4_jitter_000_gate_0000():
    """Non-contention failure at attempt 4 (jitter 0.0, gate 0.0): 3 gated rungs then the raise, no gate on the dying attempt."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(ValueError):
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.0), fail_non_contention_at=4)
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [0.1, 0.2, 0.4]


def test_align_noncontention_at_4_jitter_000_gate_0500():
    """Non-contention failure at attempt 4 (jitter 0.0, gate 0.5): 3 gated rungs then the raise, no gate on the dying attempt."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(ValueError):
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.5), fail_non_contention_at=4)
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [0.6, 0.7, 0.9]


def test_align_noncontention_at_4_jitter_100_gate_0000():
    """Non-contention failure at attempt 4 (jitter 1.0, gate 0.0): 3 gated rungs then the raise, no gate on the dying attempt."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(ValueError):
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.0), fail_non_contention_at=4)
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [0.2, 0.4, 0.8]


def test_align_noncontention_at_4_jitter_100_gate_0500():
    """Non-contention failure at attempt 4 (jitter 1.0, gate 0.5): 3 gated rungs then the raise, no gate on the dying attempt."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(ValueError):
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.5), fail_non_contention_at=4)
    assert clock.gate_calls == [1, 2, 3]
    assert clock.sleeps == [0.7, 0.9, 1.3]


def test_align_noncontention_at_5_jitter_000_gate_0000():
    """Non-contention failure at attempt 5 (jitter 0.0, gate 0.0): 4 gated rungs then the raise, no gate on the dying attempt."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(ValueError):
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.0), fail_non_contention_at=5)
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [0.1, 0.2, 0.4, 0.8]


def test_align_noncontention_at_5_jitter_000_gate_0500():
    """Non-contention failure at attempt 5 (jitter 0.0, gate 0.5): 4 gated rungs then the raise, no gate on the dying attempt."""
    clock = _Clock(jitter=0.0)
    with pytest.raises(ValueError):
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.5), fail_non_contention_at=5)
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [0.6, 0.7, 0.9, 1.3]


def test_align_noncontention_at_5_jitter_100_gate_0000():
    """Non-contention failure at attempt 5 (jitter 1.0, gate 0.0): 4 gated rungs then the raise, no gate on the dying attempt."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(ValueError):
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.0), fail_non_contention_at=5)
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [0.2, 0.4, 0.8, 1.6]


def test_align_noncontention_at_5_jitter_100_gate_0500():
    """Non-contention failure at attempt 5 (jitter 1.0, gate 0.5): 4 gated rungs then the raise, no gate on the dying attempt."""
    clock = _Clock(jitter=1.0)
    with pytest.raises(ValueError):
        _chain(clock, aborts=10**6, gate=_gate_recorder(clock, 0.5), fail_non_contention_at=5)
    assert clock.gate_calls == [1, 2, 3, 4]
    assert clock.sleeps == [0.7, 0.9, 1.3, 2.1]


def test_align_raising_gate_at_2_jitter_000():
    """Gate raises on rung 2 (jitter 0.0): that rung stays bare [0.6, 0.2, 0.9]."""
    clock = _Clock(jitter=0.0)

    def broken_gate(attempt):
        if attempt == 2:
            raise RuntimeError('gate down')
        return 0.5

    assert _chain(clock, aborts=3, gate=broken_gate) == 'ok'
    assert clock.sleeps == [0.6, 0.2, 0.9]  # rung 2 failed open to the bare rung


def test_align_raising_gate_at_3_jitter_000():
    """Gate raises on rung 3 (jitter 0.0): that rung stays bare [0.6, 0.7, 0.4]."""
    clock = _Clock(jitter=0.0)

    def broken_gate(attempt):
        if attempt == 3:
            raise RuntimeError('gate down')
        return 0.5

    assert _chain(clock, aborts=3, gate=broken_gate) == 'ok'
    assert clock.sleeps == [0.6, 0.7, 0.4]  # rung 3 failed open to the bare rung


def test_align_raising_gate_at_4_jitter_000():
    """Gate raises on rung 4 (jitter 0.0): that rung stays bare [0.6, 0.7, 0.9]."""
    clock = _Clock(jitter=0.0)

    def broken_gate(attempt):
        if attempt == 4:
            raise RuntimeError('gate down')
        return 0.5

    assert _chain(clock, aborts=3, gate=broken_gate) == 'ok'
    assert clock.sleeps == [0.6, 0.7, 0.9]  # rung 4 failed open to the bare rung


def test_align_raising_gate_at_2_jitter_100():
    """Gate raises on rung 2 (jitter 1.0): that rung stays bare [0.7, 0.4, 1.3]."""
    clock = _Clock(jitter=1.0)

    def broken_gate(attempt):
        if attempt == 2:
            raise RuntimeError('gate down')
        return 0.5

    assert _chain(clock, aborts=3, gate=broken_gate) == 'ok'
    assert clock.sleeps == [0.7, 0.4, 1.3]  # rung 2 failed open to the bare rung


def test_align_raising_gate_at_3_jitter_100():
    """Gate raises on rung 3 (jitter 1.0): that rung stays bare [0.7, 0.9, 0.8]."""
    clock = _Clock(jitter=1.0)

    def broken_gate(attempt):
        if attempt == 3:
            raise RuntimeError('gate down')
        return 0.5

    assert _chain(clock, aborts=3, gate=broken_gate) == 'ok'
    assert clock.sleeps == [0.7, 0.9, 0.8]  # rung 3 failed open to the bare rung


def test_align_raising_gate_at_4_jitter_100():
    """Gate raises on rung 4 (jitter 1.0): that rung stays bare [0.7, 0.9, 1.3]."""
    clock = _Clock(jitter=1.0)

    def broken_gate(attempt):
        if attempt == 4:
            raise RuntimeError('gate down')
        return 0.5

    assert _chain(clock, aborts=3, gate=broken_gate) == 'ok'
    assert clock.sleeps == [0.7, 0.9, 1.3]  # rung 4 failed open to the bare rung


def test_align_retry_log_rows_aborts_1_jitter_000(caplog):
    """Retry log rows for 1 gated rung(s) (jitter 0.0): every row carries delay_ms and gate_ms=250."""
    clock = _Clock(jitter=0.0)
    import logging

    with caplog.at_level(logging.INFO, logger='database.firestore_transaction_retry'):
        assert _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.25)) == 'ok'
    lines = [record.getMessage() for record in caplog.records if 'outcome=retry' in record.getMessage()]
    assert len(lines) == 1
    for index, line in enumerate(lines, start=1):
        assert re.fullmatch(
            r'firestore_transaction_contention operation=grid attempt=%d/5 outcome=retry delay_ms=\d+ gate_ms=250'
            % index,
            line,
        )


def test_align_retry_log_rows_aborts_1_jitter_100(caplog):
    """Retry log rows for 1 gated rung(s) (jitter 1.0): every row carries delay_ms and gate_ms=250."""
    clock = _Clock(jitter=1.0)
    import logging

    with caplog.at_level(logging.INFO, logger='database.firestore_transaction_retry'):
        assert _chain(clock, aborts=1, gate=_gate_recorder(clock, 0.25)) == 'ok'
    lines = [record.getMessage() for record in caplog.records if 'outcome=retry' in record.getMessage()]
    assert len(lines) == 1
    for index, line in enumerate(lines, start=1):
        assert re.fullmatch(
            r'firestore_transaction_contention operation=grid attempt=%d/5 outcome=retry delay_ms=\d+ gate_ms=250'
            % index,
            line,
        )


def test_align_retry_log_rows_aborts_2_jitter_000(caplog):
    """Retry log rows for 2 gated rung(s) (jitter 0.0): every row carries delay_ms and gate_ms=250."""
    clock = _Clock(jitter=0.0)
    import logging

    with caplog.at_level(logging.INFO, logger='database.firestore_transaction_retry'):
        assert _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.25)) == 'ok'
    lines = [record.getMessage() for record in caplog.records if 'outcome=retry' in record.getMessage()]
    assert len(lines) == 2
    for index, line in enumerate(lines, start=1):
        assert re.fullmatch(
            r'firestore_transaction_contention operation=grid attempt=%d/5 outcome=retry delay_ms=\d+ gate_ms=250'
            % index,
            line,
        )


def test_align_retry_log_rows_aborts_2_jitter_100(caplog):
    """Retry log rows for 2 gated rung(s) (jitter 1.0): every row carries delay_ms and gate_ms=250."""
    clock = _Clock(jitter=1.0)
    import logging

    with caplog.at_level(logging.INFO, logger='database.firestore_transaction_retry'):
        assert _chain(clock, aborts=2, gate=_gate_recorder(clock, 0.25)) == 'ok'
    lines = [record.getMessage() for record in caplog.records if 'outcome=retry' in record.getMessage()]
    assert len(lines) == 2
    for index, line in enumerate(lines, start=1):
        assert re.fullmatch(
            r'firestore_transaction_contention operation=grid attempt=%d/5 outcome=retry delay_ms=\d+ gate_ms=250'
            % index,
            line,
        )


def test_align_retry_log_rows_aborts_3_jitter_000(caplog):
    """Retry log rows for 3 gated rung(s) (jitter 0.0): every row carries delay_ms and gate_ms=250."""
    clock = _Clock(jitter=0.0)
    import logging

    with caplog.at_level(logging.INFO, logger='database.firestore_transaction_retry'):
        assert _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.25)) == 'ok'
    lines = [record.getMessage() for record in caplog.records if 'outcome=retry' in record.getMessage()]
    assert len(lines) == 3
    for index, line in enumerate(lines, start=1):
        assert re.fullmatch(
            r'firestore_transaction_contention operation=grid attempt=%d/5 outcome=retry delay_ms=\d+ gate_ms=250'
            % index,
            line,
        )


def test_align_retry_log_rows_aborts_3_jitter_100(caplog):
    """Retry log rows for 3 gated rung(s) (jitter 1.0): every row carries delay_ms and gate_ms=250."""
    clock = _Clock(jitter=1.0)
    import logging

    with caplog.at_level(logging.INFO, logger='database.firestore_transaction_retry'):
        assert _chain(clock, aborts=3, gate=_gate_recorder(clock, 0.25)) == 'ok'
    lines = [record.getMessage() for record in caplog.records if 'outcome=retry' in record.getMessage()]
    assert len(lines) == 3
    for index, line in enumerate(lines, start=1):
        assert re.fullmatch(
            r'firestore_transaction_contention operation=grid attempt=%d/5 outcome=retry delay_ms=\d+ gate_ms=250'
            % index,
            line,
        )


def test_align_retry_log_rows_aborts_4_jitter_000(caplog):
    """Retry log rows for 4 gated rung(s) (jitter 0.0): every row carries delay_ms and gate_ms=250."""
    clock = _Clock(jitter=0.0)
    import logging

    with caplog.at_level(logging.INFO, logger='database.firestore_transaction_retry'):
        assert _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.25)) == 'ok'
    lines = [record.getMessage() for record in caplog.records if 'outcome=retry' in record.getMessage()]
    assert len(lines) == 4
    for index, line in enumerate(lines, start=1):
        assert re.fullmatch(
            r'firestore_transaction_contention operation=grid attempt=%d/5 outcome=retry delay_ms=\d+ gate_ms=250'
            % index,
            line,
        )


def test_align_retry_log_rows_aborts_4_jitter_100(caplog):
    """Retry log rows for 4 gated rung(s) (jitter 1.0): every row carries delay_ms and gate_ms=250."""
    clock = _Clock(jitter=1.0)
    import logging

    with caplog.at_level(logging.INFO, logger='database.firestore_transaction_retry'):
        assert _chain(clock, aborts=4, gate=_gate_recorder(clock, 0.25)) == 'ok'
    lines = [record.getMessage() for record in caplog.records if 'outcome=retry' in record.getMessage()]
    assert len(lines) == 4
    for index, line in enumerate(lines, start=1):
        assert re.fullmatch(
            r'firestore_transaction_contention operation=grid attempt=%d/5 outcome=retry delay_ms=\d+ gate_ms=250'
            % index,
            line,
        )

"""Shared cell harness for the Chat-first/candidate-outbox bounded-lane grids.

Each grid cell drives one real lane boundary — ``run_bounded_lane_transaction``
(a fresh ``max_attempts=1`` transaction per outer attempt, the engine's
equal-jitter ladder, the expiry-restarting inner helper at ``attempts=1``)
behind a scripted fault plan — and freezes the observables the grid tests
compare as literals. The engine under test is the production one —
``run_with_transaction_contention_retry`` — with only the wall-clock edges
pinned: sleep is recorded and never slept, the equal-jitter draw is pinned to
the band midpoint, and the fake clock charges each body attempt the
scenario's cost. The runner imports the engine at call time, so one pinning
covers every joined lane, and the inner expiry helper
(``database._client.run_transactional``) runs real at ``attempts=1``.

``model_cell`` — the independent hand-transcribed expectation walk the
emitter compares against — lives outside the tree. It predicts every
observable from the source predicates and the engine's documented accounting:
one fresh transaction per outer attempt; equal-jitter rungs at the pinned
draw; Aborted faults (bare or wrapped in a domain carrier carrying them as
``__cause__``) replay until the attempt cap; expired-transaction retirements
replay too and keep the three-fresh-chain ceiling only while no deadline is
in scope; foreign domain refusals pass through single-shot unwrapped; an
ambient deadline scope (the only way a lane inherits one — the runner passes
no ``deadline`` of its own) gates every retry behind the reserve rule before
the attempt and never lets the jitter sleep run past the deadline; an
exhaustion carries the typed reason, the zero retry-after and the final
fault as its cause; every engine line lands on the engine's logger and the
lane's exhaustion marker on the driving module's logger.

Failure-Class: FC-bare-chat-first-and-candidate-outbox-transactions-fail-on-first-contention
"""

import logging

from google.api_core.exceptions import Aborted as FirestoreAborted
from google.api_core.exceptions import InvalidArgument as FirestoreInvalidArgument

from database import bounded_lane_transaction as lane_module
from database import firestore_transaction_retry as engine
from database.firestore_transaction_retry import transaction_retry_deadline_scope

PINNED_JITTER_DRAW = 0.5
CLOCK_START_SECONDS = 100.0
EXPIRED_TRANSACTION_MESSAGE = '400 The referenced transaction has expired or is no longer valid'
ABORT_MESSAGE = '409 transaction contention preflight collision'
DOMAIN_REFUSAL_MESSAGE = 'domain refusal single-shot'


class LaneDomainRefusal(Exception):
    """A foreign domain error: never contention, never replayed."""


class LaneFaultWrapper(Exception):
    """A domain-shaped carrier whose ``__cause__`` is the real fault."""


# deadline_mode -> (ambient scope delta from CLOCK_START, per-attempt body
# clock cost). ``None`` scopes nothing and charges nothing: the chain keeps
# the attempt-only bound and the expired-chain ceiling. The wide-body
# variants charge real seconds per attempt so the reserve rule, not the
# jitter, is what ends the chain.
DEADLINE_MODES = {
    'none': (None, 0.0),
    'nonbinding_600': (600.0, 0.01),
    'boundary_30': (30.0, 0.0),
    'floor_block_35': (35.0, 20.0),
    'reserve_block_100': (100.0, 30.0),
    'overspend_25': (25.0, 30.0),
}


class _CellTransaction:
    def __init__(self, identifier):
        self.identifier = identifier


class _CellClient:
    """Mints a fresh transaction per call and records every mint."""

    def __init__(self):
        self.minted = []
        self.max_attempts_kwargs = []

    def transaction(self, max_attempts=None):
        self.max_attempts_kwargs.append(max_attempts)
        transaction = _CellTransaction(f'txn-{len(self.minted) + 1}')
        self.minted.append(transaction.identifier)
        return transaction


class _PinnedClock:
    def __init__(self):
        self.now = CLOCK_START_SECONDS

    def advance(self, cost):
        self.now += cost

    def __call__(self):
        return self.now


class _SleepRecorder:
    def __init__(self):
        self.sleeps = []

    def __call__(self, seconds):
        # Recorded, never slept: the fake clock does not advance either, so a
        # rung wait consumes no deadline budget in this harness.
        self.sleeps.append(round(float(seconds), 9))


def pin_bounded_chain(monkeypatch, sleep_recorder, clock):
    """Drive the real engine with the wall-clock edges pinned.

    The runner imports the engine from the module at call time, so one
    binding covers every joined lane.
    """
    actual = engine.run_with_transaction_contention_retry

    def factory(*args, **kwargs):
        kwargs.setdefault('sleep', sleep_recorder)
        kwargs.setdefault('random_value', lambda: PINNED_JITTER_DRAW)
        kwargs.setdefault('monotonic', clock)
        return actual(*args, **kwargs)

    monkeypatch.setattr(engine, 'run_with_transaction_contention_retry', factory)


def _fault(event, abort_form):
    if event == 'abort':
        inner = FirestoreAborted(ABORT_MESSAGE)
        if abort_form == 'chained_cause':
            wrapper = LaneFaultWrapper(DOMAIN_REFUSAL_MESSAGE)
            wrapper.__cause__ = inner
            return wrapper
        return inner
    if event == 'expired':
        return FirestoreInvalidArgument(EXPIRED_TRANSACTION_MESSAGE)
    raise AssertionError(f'unscripted event {event!r}')


def _body_plan(aborts, expiries, terminal):
    events = ['abort'] * aborts + ['expired'] * expiries
    if terminal in {'ok', 'foreign'}:
        events.append(terminal)
    return events


def build_body(recorder, plan, clock, cost, terminal, abort_form):
    def body(transaction):
        index = recorder['calls']
        recorder['calls'] += 1
        recorder['txn_ids'].append(transaction.identifier)
        clock.advance(cost)
        if index < len(plan):
            event = plan[index]
            if event == 'ok':
                return 'lane_ok'
            if event == 'foreign':
                raise LaneDomainRefusal(DOMAIN_REFUSAL_MESSAGE)
            raise _fault(event, abort_form)
        if terminal == 'forever':
            raise _fault('abort', abort_form)
        raise AssertionError('plan exhausted without a terminal event')

    return body


def drive_cell(
    monkeypatch,
    caplog,
    *,
    label,
    lane_logger_name,
    aborts=0,
    expiries=0,
    max_attempts=5,
    deadline_mode='none',
    terminal='ok',
    abort_form='bare',
):
    """Drive one cell through the real lane runner and freeze the observables."""

    assert deadline_mode in DEADLINE_MODES
    assert terminal in {'ok', 'foreign', 'forever'}
    assert abort_form in {'bare', 'chained_cause'}
    scope_delta, cost = DEADLINE_MODES[deadline_mode]
    plan = _body_plan(aborts, expiries, terminal)
    client = _CellClient()
    clock = _PinnedClock()
    sleep_recorder = _SleepRecorder()
    recorder = {'calls': 0, 'txn_ids': []}
    caplog.set_level(logging.DEBUG)

    pin_bounded_chain(monkeypatch, sleep_recorder, clock)
    freeze = {}
    try:
        with transaction_retry_deadline_scope(None if scope_delta is None else CLOCK_START_SECONDS + scope_delta):
            freeze['result'] = lane_module.run_bounded_lane_transaction(
                client,
                build_body(recorder, plan, clock, cost, terminal, abort_form),
                operation_name=label,
                logger=logging.getLogger(lane_logger_name),
                max_attempts=max_attempts,
            )
            freeze['raised'] = None
    except LaneDomainRefusal:
        freeze['result'] = None
        freeze['raised'] = 'foreign'
        freeze['reason'] = None
        freeze['retry_after'] = None
        freeze['cause'] = None
    except Exception as error:  # the freeze names every remaining raised shape
        freeze['result'] = None
        freeze['raised'] = (
            'deadline_exhausted'
            if getattr(error, 'reason', '') == 'deadline_exhausted'
            else (
                'contention_exhausted'
                if type(error).__name__ == 'FirestoreContentionExhausted'
                else f'unexpected:{type(error).__name__}'
            )
        )
        freeze['reason'] = getattr(error, 'reason', None)
        freeze['retry_after'] = round(getattr(error, 'retry_after', 0.0), 9)
        freeze['cause'] = type(error.__cause__).__name__ if error.__cause__ is not None else None
    if freeze['raised'] is None:
        freeze['reason'] = None
        freeze['retry_after'] = None
        freeze['cause'] = None
    freeze['body_calls'] = list(range(1, recorder['calls'] + 1))
    freeze['transactions'] = list(client.minted)
    freeze['max_attempts_kwargs'] = list(client.max_attempts_kwargs)
    freeze['sleeps'] = list(sleep_recorder.sleeps)
    records = [(record.levelname, record.getMessage()) for record in caplog.records]
    freeze['engine_records'] = [item for item in records if item[1].startswith('firestore_transaction_contention')]
    freeze['lane_records'] = [item for item in records if item[1].startswith(f'event={label}_contention_exhausted')]
    return freeze

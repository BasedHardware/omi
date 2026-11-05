"""Bounded transaction labels shared by serving pulls and shadow metadata."""

from contextlib import contextmanager
from contextvars import ContextVar
import re

from config.batch_pipeline import SCHEDULER_SHARDS

_pull_operation = ContextVar('batch_pull_operation', default='batch_pipeline_store')
SHADOW_STORE_OPERATIONS = frozenset(
    {
        'finish',
        'offer',
        'reserve',
        'ready',
        'projection_input',
        'take',
        'paid',
        'handoff',
        'start_recovery',
        'recovery_transport_failed',
        'reap',
    }
)


_PULL_OPERATION_PATTERN = re.compile(r'^[a-z][a-z0-9_]{0,63}$')


def current_operation() -> str:
    return _pull_operation.get()


@contextmanager
def store_operation(operation: str):
    """Attribute one batch store transaction with a static caller label.

    Every worker-hot mutation that runs through ``FirestoreStore.run`` without
    the pull/shadow contexts used to log contention as the unlabeled default
    ``batch_pipeline_store``, so an ``outcome=exhausted`` storm could not be
    attributed to the caller that burned the budget. Call sites pass literal
    labels only; the pattern rejects anything a caller could interpolate.
    """
    if not _PULL_OPERATION_PATTERN.fullmatch(operation):
        raise ValueError('static store operation label required')
    token = _pull_operation.set(operation)
    try:
        yield
    finally:
        _pull_operation.reset(token)


@contextmanager
def shadow_operation(operation: str):
    if operation not in SHADOW_STORE_OPERATIONS:
        raise ValueError('static shadow store operation required')
    token = _pull_operation.set(f'batch_shadow_{operation}')
    try:
        yield
    finally:
        _pull_operation.reset(token)


@contextmanager
def pull_operation(operation: str, shard: str):
    if operation not in {'claim', 'pull'} or shard not in {f'scheduler_{n:02d}' for n in range(SCHEDULER_SHARDS)}:
        raise ValueError('static pull operation and scheduler shard required')
    token = _pull_operation.set(f'batch_{operation} shard={shard}')
    try:
        yield
    finally:
        _pull_operation.reset(token)

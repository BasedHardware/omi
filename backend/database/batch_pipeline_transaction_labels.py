"""Bounded transaction labels shared by serving pulls and shadow metadata.

Every ``FirestoreStore.run`` resolves to a static caller label before a
transaction opens. The anonymous ``batch_pipeline_store`` default used to
absorb every unlabeled worker-hot mutation, so an ``outcome=exhausted``
storm could not be attributed to the caller that burned the budget. The
default is now ``None`` and an unlabeled run is refused instead of logging
under a label shared by dozens of unrelated call sites.
"""

from contextlib import contextmanager
from contextvars import ContextVar
import re

from config.batch_pipeline import SCHEDULER_SHARDS

_pull_operation: ContextVar[str | None] = ContextVar('batch_pull_operation', default=None)
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
# The serving pull composes its two validated components into one label; the
# shard is admitted only through pull_operation's own bounded checks.
_PULL_COMPOSITE_PATTERN = re.compile(r'^batch_(?:pull|claim) shard=scheduler_[0-9]{2}$')
_SHARD_SUFFIXES = frozenset(f'{n:02d}' for n in range(SCHEDULER_SHARDS))


def current_operation() -> str | None:
    return _pull_operation.get()


def require_operation_label(operation: str | None) -> str:
    """Validate and return a static store operation label.

    ``None`` — no ambient ``store_operation`` context and no explicit
    ``operation=`` — raises: an anonymous transaction is exactly the
    unattributable contention storm this module exists to prevent. Literal
    labels and the composed serving-pull label only, and the composed
    shard must be one of the configured scheduler shards; the patterns
    reject anything a caller could interpolate.
    """
    if isinstance(operation, str):
        if _PULL_OPERATION_PATTERN.fullmatch(operation):
            return operation
        if _PULL_COMPOSITE_PATTERN.fullmatch(operation) and operation.rsplit('scheduler_', 1)[1] in _SHARD_SUFFIXES:
            return operation
    raise ValueError('static store operation label required')


@contextmanager
def store_operation(operation: str):
    """Attribute one batch store transaction with a static caller label.

    Call sites pass literal labels only; the pattern rejects anything a
    caller could interpolate.
    """
    require_operation_label(operation)
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

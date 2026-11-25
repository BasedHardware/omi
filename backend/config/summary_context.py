"""Bounded failure metadata for optional summary reads; never provider messages."""

from contextlib import contextmanager
from typing import Iterator

STAGES = frozenset({'budget', 'embedding', 'vector', 'hydrate'})


def mark_failure(error: Exception, stage: str) -> None:
    if stage not in STAGES:
        raise ValueError('unknown summary context stage')
    try:
        if not getattr(error, '_summary_context_stage', None):
            setattr(error, '_summary_context_stage', stage)
    except (AttributeError, TypeError):
        # Telemetry is best-effort: an exception that rejects attributes keeps
        # propagating unchanged and is reported without a stage.
        pass


@contextmanager
def context_stage(stage: str) -> Iterator[None]:
    try:
        yield
    except Exception as error:
        mark_failure(error, stage)
        raise


def failure_details(error: Exception) -> tuple[str, str]:
    stage = 'budget' if isinstance(error, TimeoutError) else 'hydrate'
    current: BaseException | None = error
    exception_type = type(error).__name__
    # Service adapters wrap provider exceptions. Follow only explicit causes,
    # with a hard bound even if a provider constructs a cyclic exception chain.
    for _ in range(8):
        if current is None:
            break
        candidate = getattr(current, '_summary_context_stage', None)
        if candidate in STAGES:
            stage = candidate
        exception_type = type(current).__name__
        current = current.__cause__
    return stage, exception_type

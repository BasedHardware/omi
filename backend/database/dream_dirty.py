"""Cheap post-write signals; flag off performs no I/O. Payloads contain ids only."""

import functools
import inspect
import logging
from typing import Any, cast
from contextvars import ContextVar
from prometheus_client import Counter

from config.dream_agent import mode
from database.dream_store import mark_dirty
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)
dream_writing = ContextVar('dream_writing', default=False)
canary_writing = ContextVar('dream_canary_writing', default=False)


def _dirty_counter() -> Counter:
    try:
        return Counter('omi_dream_dirty_enqueue_total', 'Dream dirty enqueue outcomes', ['outcome'])
    except ValueError:
        # Prometheus has no public collector lookup; match the existing reload convention.
        from prometheus_client import REGISTRY

        return cast(Counter, getattr(REGISTRY, '_names_to_collectors')['omi_dream_dirty_enqueue_total'])


DIRTY = _dirty_counter()


def after_write(collection: str):
    def decorate(fn):
        signature = inspect.signature(fn)
        parameters = tuple(signature.parameters)

        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            result: Any = fn(*args, **kwargs)
            if mode() != 'off' and not dream_writing.get() and result is not False:
                bound = signature.bind(*args, **kwargs).arguments
                uid = bound[parameters[0]]
                data = bound[parameters[1]]
                rows = data if isinstance(data, list) else [data]
                ids = [str(row['id']) for row in rows if isinstance(row, dict) and row.get('id')]
                if isinstance(data, str):
                    ids = [data]
                if collection == 'action_items' and not isinstance(data, str):
                    ids = [result] if isinstance(result, str) else result if isinstance(result, list) else ids
                if collection == 'memory_items' and isinstance(result, str):
                    ids = [result]
                if collection == 'candidates':
                    from models.candidate import CandidateRecord

                    if isinstance(result, CandidateRecord):
                        ids = [result.candidate_id]
                notify(uid, [(collection, value) for value in ids])
            return result

        return wrapped

    return decorate


def notify(uid: str, refs: list[tuple[str, str]]) -> None:
    if mode() == 'off' or dream_writing.get() or not refs:
        return
    try:
        if mark_dirty(uid, refs, canary=True) if canary_writing.get() else mark_dirty(uid, refs):
            DIRTY.labels('ok').inc()
    except Exception as exc:
        DIRTY.labels('failed').inc()
        record_fallback(
            component='agent_tools',
            from_mode='dream_dirty_signal',
            to_mode='none',
            reason='enqueue_failed',
            outcome='degraded',
            log=logger,
        )
        logger.warning('Dream dirty signal failed error_type=%s', type(exc).__name__)

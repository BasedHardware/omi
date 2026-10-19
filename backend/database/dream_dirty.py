"""Cheap post-write signals; flag off performs no I/O. Payloads contain ids only."""

import functools
import inspect
import logging
from typing import Any, List, Optional, Tuple, cast
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


def _clean_token(value: object) -> str:
    if not isinstance(value, str):
        return ''
    cleaned = value.strip()
    if (
        not cleaned
        or len(cleaned) > 128
        or any(ch in cleaned for ch in ('/', '\\', '\x00', '\r', '\n'))
        or '..' in cleaned
    ):
        return ''
    return cleaned


def _clean_ids(values: object) -> List[str]:
    if not isinstance(values, (list, tuple)):
        return []
    cleaned: List[str] = []
    for item in values:
        if item is None or isinstance(item, bool):
            continue
        token = _clean_token(str(item) if isinstance(item, (str, int)) else item)
        if token:
            cleaned.append(token)
    return cleaned


def after_write(collection: str):
    clean_collection = _clean_token(collection)

    def decorate(fn):
        signature = inspect.signature(fn)
        parameters = tuple(signature.parameters)

        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            result: Any = fn(*args, **kwargs)
            if clean_collection and mode() != 'off' and not dream_writing.get() and result is not False:
                try:
                    bound_args = signature.bind(*args, **kwargs)
                    bound_args.apply_defaults()
                    bound = bound_args.arguments
                except TypeError:
                    return result
                uid: Optional[Any] = bound.get(parameters[0]) if len(parameters) >= 1 else None
                data: Optional[Any] = bound.get(parameters[1]) if len(parameters) >= 2 else None
                clean_uid = _clean_token(uid)
                if not clean_uid:
                    return result
                rows = data if isinstance(data, list) else [data]
                ids = _clean_ids([row.get('id') for row in rows if isinstance(row, dict) and row.get('id')])
                if isinstance(data, str):
                    ids = _clean_ids([data])
                if clean_collection == 'action_items' and not isinstance(data, str):
                    if isinstance(result, str):
                        ids = _clean_ids([result])
                    elif isinstance(result, list):
                        ids = _clean_ids(result)
                if clean_collection == 'memory_items' and isinstance(result, str):
                    ids = _clean_ids([result])
                if clean_collection == 'candidates':
                    from models.candidate import CandidateRecord

                    if isinstance(result, CandidateRecord):
                        ids = _clean_ids([result.candidate_id])
                if ids:
                    notify(clean_uid, [(clean_collection, value) for value in ids])
            return result

        return wrapped

    return decorate


def notify(uid: str, refs: list[tuple[str, str]]) -> None:
    if mode() == 'off' or dream_writing.get() or not refs or not isinstance(refs, (list, tuple)):
        return
    clean_uid = _clean_token(uid)
    if not clean_uid:
        return
    clean_refs: List[Tuple[str, str]] = []
    for item in refs:
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            continue
        col_token = _clean_token(item[0])
        id_token = _clean_token(item[1])
        if col_token and id_token:
            clean_refs.append((col_token, id_token))
    if not clean_refs:
        return
    try:
        if (
            mark_dirty(clean_uid, clean_refs, canary=True)
            if canary_writing.get()
            else mark_dirty(clean_uid, clean_refs)
        ):
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

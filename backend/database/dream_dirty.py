"""Cheap post-write signals; flag off performs no I/O. Payloads contain ids only."""

import functools
import inspect
import logging
import re
from typing import Any, cast
from contextvars import ContextVar
from prometheus_client import Counter

from config.dream_agent import mode
from database.dream_store import mark_dirty
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)
dream_writing = ContextVar('dream_writing', default=False)
canary_writing = ContextVar('dream_canary_writing', default=False)

_MAX_UID_LENGTH = 128
_MAX_DOCUMENT_ID_BYTES = 1500
_MAX_REFS = 100
_CONTROL_CHARS = re.compile(r'[\x00-\x1f\x7f]')


def _dirty_counter() -> Counter:
    try:
        return Counter('omi_dream_dirty_enqueue_total', 'Dream dirty enqueue outcomes', ['outcome'])
    except ValueError:
        # Prometheus has no public collector lookup; match the existing reload convention.
        from prometheus_client import REGISTRY

        return cast(Counter, getattr(REGISTRY, '_names_to_collectors')['omi_dream_dirty_enqueue_total'])


DIRTY = _dirty_counter()


def _clean_token(value: Any, *, max_chars: int = _MAX_UID_LENGTH, max_bytes: int = 0) -> str | None:
    """Return a Firestore-safe identifier, or None when the value cannot be used as one.

    Rejects non-strings, booleans, blank/whitespace-only values, path separators,
    the ``.``/``..`` traversal names, ``__reserved__`` names, control characters and
    over-long identifiers so a malformed post-write value can never be turned into a
    document path or a queue key.
    """
    if value is None or isinstance(value, bool) or not isinstance(value, str):
        return None
    token = value.strip()
    if not token:
        return None
    if token in {'.', '..'} or '..' in token or '/' in token or '\\' in token:
        return None
    if _CONTROL_CHARS.search(token):
        return None
    if token.startswith('__') and token.endswith('__'):
        return None
    if max_chars and len(token) > max_chars:
        return None
    if max_bytes and len(token.encode('utf-8')) > max_bytes:
        return None
    return token


def _coerce_document_id(value: Any) -> Any:
    """Mirror the historical ``str(row['id'])`` coercion for numeric row ids.

    ``_clean_token`` only accepts ``str``, so without this a writer passing a
    numeric primary key (``{'id': 123}``) would silently stop marking the
    document dirty - a regression against the pre-hardening behaviour.
    Booleans are left untouched on purpose so they stay rejected.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return str(value)
    return value


def _clean_ids(values: Any) -> list[str]:
    """Drop unusable ids, keep first-seen order, and cap the fan-out at ``_MAX_REFS``."""
    if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple, set)):
        values = [values] if values is not None else []
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        token = _clean_token(value, max_chars=0, max_bytes=_MAX_DOCUMENT_ID_BYTES)
        if token is None or token in seen:
            continue
        seen.add(token)
        cleaned.append(token)
        if len(cleaned) >= _MAX_REFS:
            break
    return cleaned


def _clean_refs(refs: Any) -> list[tuple[str, str]]:
    """Keep only well-formed ``(collection, document_id)`` pairs built from safe tokens."""
    if not isinstance(refs, (list, tuple)):
        return []
    cleaned: list[tuple[str, str]] = []
    for ref in refs:
        if not isinstance(ref, (list, tuple)) or len(ref) != 2:
            continue
        collection = _clean_token(ref[0], max_chars=0, max_bytes=_MAX_DOCUMENT_ID_BYTES)
        document_id = _clean_token(ref[1], max_chars=0, max_bytes=_MAX_DOCUMENT_ID_BYTES)
        if collection is None or document_id is None:
            continue
        cleaned.append((collection, document_id))
        if len(cleaned) >= _MAX_REFS:
            break
    return cleaned


def after_write(collection: str):
    def decorate(fn):
        signature = inspect.signature(fn)
        parameters = tuple(signature.parameters)

        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            result: Any = fn(*args, **kwargs)
            if mode() != 'off' and not dream_writing.get() and result is not False:
                bound = None
                try:
                    bound = signature.bind(*args, **kwargs)
                    bound.apply_defaults()
                except TypeError:
                    bound = None
                uid = bound.arguments.get(parameters[0]) if bound is not None and parameters else None
                data = bound.arguments.get(parameters[1]) if bound is not None and len(parameters) > 1 else None
                ids = _ids_for(collection, data, result)
                notify(uid, [(collection, value) for value in ids])
            return result

        return wrapped

    return decorate


def _ids_for(collection: str, data: Any, result: Any) -> list[str]:
    """Collect the ids a write should mark dirty, mirroring the historical rules."""
    ids: Any = []
    if isinstance(data, str):
        ids = [data]
    else:
        rows = data if isinstance(data, list) else [data]
        ids = [
            _coerce_document_id(row['id']) for row in rows if isinstance(row, dict) and row.get('id')
        ]
    if collection == 'action_items' and not isinstance(data, str):
        ids = [result] if isinstance(result, str) else result if isinstance(result, list) else ids
    if collection == 'memory_items' and isinstance(result, str):
        ids = [result]
    if collection == 'candidates':
        from models.candidate import CandidateRecord

        if isinstance(result, CandidateRecord):
            ids = [result.candidate_id]
    if isinstance(ids, (list, tuple, set)) and len(ids) > _MAX_REFS:
        logger.warning(
            'Dream dirty fan-out truncated collection=%s requested=%s cap=%s',
            collection,
            len(ids),
            _MAX_REFS,
        )
    return _clean_ids(ids)


def notify(uid: str, refs: list[tuple[str, str]]) -> None:
    if mode() == 'off' or dream_writing.get() or not refs:
        return
    clean_uid = _clean_token(uid)
    if clean_uid is None:
        return
    clean_refs = _clean_refs(refs)
    if not clean_refs:
        return
    try:
        if canary_writing.get():
            marked = mark_dirty(clean_uid, clean_refs, canary=True)
        else:
            marked = mark_dirty(clean_uid, clean_refs)
        if marked:
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

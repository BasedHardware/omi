"""Shared Firestore snapshot-to-model read boundary.

Malformed or legacy Firestore documents are untrusted input. Presentation
readers can use the fail-open entry points below to preserve the rest of a
response, while idempotency and canonical-state readers use the strict entry
point so corruption cannot create a duplicate side effect.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Iterator, Mapping
from typing import Any, TypeVar, cast

from pydantic import ValidationError

logger = logging.getLogger(__name__)

T = TypeVar('T', covariant=True)


# Pydantic's classmethod accepts ``obj`` plus optional keyword controls, which
# cannot be expressed by a narrow protocol without rejecting normal BaseModels.
ModelParser = type[Any] | Callable[[Mapping[str, Any]], T]
SnapshotPayload = Callable[[Any], Mapping[str, Any]]


_fallback_recorder: Callable[..., None] | None
try:
    # Bind eagerly in real backend processes so the first malformed document
    # stays within fast-reader latency budgets. Some strict-only router import
    # tests intentionally stub FastAPI incompletely; they defer this safely.
    from utils.observability.fallback import record_fallback as _shared_record_fallback
except ImportError:
    _fallback_recorder = None
else:
    _fallback_recorder = _shared_record_fallback


def record_fallback(**kwargs: Any) -> None:
    """Import telemetry only when a fail-open reader actually drops a document.

    Strict-only stores are imported by lightweight router tests that intentionally
    stub FastAPI. Their deferred first use preserves that import isolation.
    """
    global _fallback_recorder
    if _fallback_recorder is None:
        from utils.observability.fallback import record_fallback as shared_record_fallback

        _fallback_recorder = shared_record_fallback
    _fallback_recorder(**kwargs)


class MalformedDocError(RuntimeError):
    """A strict Firestore reader encountered a structurally invalid document."""

    def __init__(self, *, document_path: str, error_types: tuple[str, ...], error_fields: tuple[str, ...]):
        self.document_path = document_path
        self.error_types = error_types
        self.error_fields = error_fields
        super().__init__(
            f'malformed Firestore document path={document_path} '
            f'validation_fields={list(error_fields)} validation_types={list(error_types)}'
        )


def _snapshot_path(snapshot: Any) -> str:
    reference = getattr(snapshot, 'reference', None)
    reference_path = getattr(reference, 'path', None)
    if isinstance(reference_path, str) and reference_path:
        return reference_path
    path = getattr(snapshot, 'path', None)
    if isinstance(path, str) and path:
        return path
    document_id = getattr(snapshot, 'id', None)
    if isinstance(document_id, str) and document_id:
        return f'<unknown>/{document_id}'
    return '<unknown>'


def _error_types(error: ValidationError | TypeError) -> tuple[str, ...]:
    if not isinstance(error, ValidationError):
        return (type(error).__name__,)
    return tuple(str(item.get('type', 'unknown')) for item in error.errors(include_input=False, include_url=False)[:5])


def _error_fields(error: ValidationError | TypeError) -> tuple[str, ...]:
    """Return only structural field paths, never rejected input values."""
    if not isinstance(error, ValidationError):
        return ('<payload>',)
    fields: list[str] = []
    for item in error.errors(include_input=False, include_url=False)[:5]:
        location = item.get('loc', ())
        fields.append('.'.join(str(part) for part in location) or '<payload>')
    return tuple(fields)


def _default_payload(snapshot: Any) -> Mapping[str, Any]:
    payload = snapshot.to_dict()
    if not isinstance(payload, Mapping):
        raise TypeError('Firestore snapshot payload must be a mapping')
    return cast(Mapping[str, Any], payload)


def _payload_for(
    snapshot: Any,
    *,
    payload_from_snapshot: SnapshotPayload | None,
    document_id_field: str | None,
) -> Mapping[str, Any]:
    payload = dict((payload_from_snapshot or _default_payload)(snapshot))
    if document_id_field is not None:
        document_id = getattr(snapshot, 'id', None)
        if isinstance(document_id, str) and document_id:
            payload.setdefault(document_id_field, document_id)
    return payload


def _parse(model: ModelParser[T], payload: Mapping[str, Any]) -> T:
    validator = getattr(model, 'model_validate', None)
    if callable(validator):
        return cast(T, validator(payload))
    return cast(Callable[[Mapping[str, Any]], T], model)(payload)


def _parse_strict(
    model: ModelParser[T],
    snapshot: Any,
    *,
    payload_from_snapshot: SnapshotPayload | None,
    document_id_field: str | None,
) -> T:
    try:
        return _parse(
            model,
            _payload_for(
                snapshot,
                payload_from_snapshot=payload_from_snapshot,
                document_id_field=document_id_field,
            ),
        )
    except (ValidationError, TypeError) as error:
        document_path = _snapshot_path(snapshot)
        error_types = _error_types(error)
        error_fields = _error_fields(error)
        # Never render ValidationError: its input_value can contain Firestore PII.
        logger.warning(
            'Malformed Firestore document path=%s validation_fields=%s validation_types=%s',
            document_path,
            error_fields,
            error_types,
        )
        raise MalformedDocError(
            document_path=document_path,
            error_types=error_types,
            error_fields=error_fields,
        ) from error


def _record_drop() -> None:
    record_fallback(
        component='firestore_read',
        from_mode='firestore_document',
        to_mode='skip_malformed_document',
        reason='malformed_doc',
        outcome='degraded',
        log=logger,
    )


def parse_snapshot_or_none(
    model: ModelParser[T],
    snapshot: Any,
    *,
    payload_from_snapshot: SnapshotPayload | None = None,
    document_id_field: str | None = None,
) -> T | None:
    """Parse one presentation snapshot, returning ``None`` for malformed data."""
    if not getattr(snapshot, 'exists', True):
        return None
    try:
        return _parse_strict(
            model,
            snapshot,
            payload_from_snapshot=payload_from_snapshot,
            document_id_field=document_id_field,
        )
    except MalformedDocError:
        _record_drop()
        return None


def parse_snapshots(
    model: ModelParser[T],
    snapshots: Iterable[Any],
    *,
    payload_from_snapshot: SnapshotPayload | None = None,
    document_id_field: str | None = None,
) -> list[T]:
    """Parse materialized presentation snapshots, dropping malformed entries."""
    return [
        parsed
        for snapshot in snapshots
        if (
            parsed := parse_snapshot_or_none(
                model,
                snapshot,
                payload_from_snapshot=payload_from_snapshot,
                document_id_field=document_id_field,
            )
        )
        is not None
    ]


def iter_parsed_snapshots(
    model: ModelParser[T],
    snapshot_iter: Iterable[Any],
    *,
    payload_from_snapshot: SnapshotPayload | None = None,
    document_id_field: str | None = None,
) -> Iterator[T]:
    """Lazily parse presentation snapshots, dropping malformed entries."""
    for snapshot in snapshot_iter:
        parsed = parse_snapshot_or_none(
            model,
            snapshot,
            payload_from_snapshot=payload_from_snapshot,
            document_id_field=document_id_field,
        )
        if parsed is not None:
            yield parsed


def parse_snapshot_strict(
    model: ModelParser[T],
    snapshot: Any,
    *,
    payload_from_snapshot: SnapshotPayload | None = None,
    document_id_field: str | None = None,
) -> T:
    """Parse a correctness-critical snapshot or raise a typed corruption error."""
    return _parse_strict(
        model,
        snapshot,
        payload_from_snapshot=payload_from_snapshot,
        document_id_field=document_id_field,
    )

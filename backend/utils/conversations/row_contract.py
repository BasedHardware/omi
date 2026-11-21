"""One contract for stored conversation rows: producers are checked at the write, readers isolate bad rows.

Readers validate a stored row with ``Conversation`` (``Conversation(**row)`` and the list endpoints'
``response_model``). A producer that commits raw dicts is otherwise first validated by every reader: on
2026-11-17 one v3 row without ``structured.participants[].source`` turned every ``GET /v1/conversations``
page for its owner into a 500 (#25588).

- ``check_write(row, producer=...)``: validate a full row against the reader model before it is committed.
  An invalid row raises ``InvalidConversationRow`` naming the producer; the caller keeps its own retry or
  park convention, so the source stays owed and nothing is silently dropped.
  ``CONVERSATION_ROW_WRITE_VALIDATION_ENABLED=false`` is the kill switch: count and log, then write.
- ``readable_rows`` / ``readable_models``: list reads skip a row the response model rejects, count it through
  ``record_fallback`` and log its id and the failing field paths, and return the rest of the page.

Logs carry ids, field paths and error types only, never field values.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from typing import Any, TypeVar, cast

from prometheus_client import Counter
from pydantic import BaseModel, ValidationError

from config.refactor_modes import default_on
from models.conversation import Conversation
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)

WRITE_VALIDATION_ENV = 'CONVERSATION_ROW_WRITE_VALIDATION_ENABLED'

WRITE_REJECTIONS = Counter(
    'omi_conversation_row_write_invalid_total',
    'Producer-built conversation rows the reader model rejects at the write seam',
    ['producer', 'outcome'],
)

_MAX_PATHS = 8

ModelT = TypeVar('ModelT', bound=BaseModel)


class InvalidConversationRow(ValueError):
    """A producer built a conversation row its readers cannot validate."""

    def __init__(self, producer: str, conversation_id: str, paths: list[str]):
        self.producer = producer
        self.conversation_id = conversation_id
        self.paths = paths
        super().__init__(f'invalid conversation row producer={producer} id={conversation_id} paths={paths}')


def error_paths(error: ValidationError) -> list[str]:
    """Field paths and error types, without input values: safe to log."""
    paths: list[str] = []
    for item in error.errors(include_input=False, include_url=False):
        location = '.'.join(str(part) for part in item.get('loc') or ()) or '<root>'
        paths.append(f"{location}:{item.get('type', 'invalid')}")
    return paths[:_MAX_PATHS]


def check_write(row: Mapping[str, Any], *, producer: str) -> None:
    """Validate a full producer-built row against the reader model before it is committed."""
    try:
        Conversation.model_validate(row)
    except ValidationError as error:
        paths = error_paths(error)
        conversation_id = str(row.get('id') or 'unknown')
        enforced = default_on(WRITE_VALIDATION_ENV)
        WRITE_REJECTIONS.labels(producer=producer, outcome='rejected' if enforced else 'logged').inc()
        logger.error(
            'conversation row invalid at write producer=%s conversation_id=%s enforced=%s paths=%s',
            producer,
            conversation_id,
            enforced,
            paths,
        )
        if enforced:
            raise InvalidConversationRow(producer, conversation_id, paths) from None


def _screen(rows: Iterable[Any], surface: str, model: type[BaseModel]) -> list[tuple[Any, BaseModel]]:
    kept: list[tuple[Any, BaseModel]] = []
    for row in rows:
        try:
            if not isinstance(row, Mapping):
                raise TypeError('not_a_mapping')
            kept.append((row, model.model_validate(row)))
        except (ValidationError, TypeError) as error:
            record_fallback(
                component='conversation_row_contract',
                from_mode='strict',
                to_mode='row_skipped',
                reason='malformed_doc',
                outcome='degraded',
            )
            logger.warning(
                'conversation row skipped on read surface=%s conversation_id=%s paths=%s',
                surface,
                str(row.get('id', 'unknown')) if isinstance(row, Mapping) else 'unknown',
                error_paths(error) if isinstance(error, ValidationError) else ['<root>:not_a_mapping'],
            )
    return kept


def readable_rows(rows: Iterable[Any], *, surface: str, model: type[BaseModel] = Conversation) -> list[Any]:
    """The input rows ``model`` accepts, unchanged, for endpoints whose response model re-validates them."""
    return [row for row, _ in _screen(rows, surface, model)]


def readable_models(rows: Iterable[Any], *, surface: str, model: type[ModelT]) -> list[ModelT]:
    """The validated ``model`` instance for each row it accepts."""
    return [cast(ModelT, validated) for _, validated in _screen(rows, surface, model)]

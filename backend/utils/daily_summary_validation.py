"""Recap read/candidate validation without mutating stored data or source conversations."""

import json
import logging
from typing import Any

from pydantic_core import PydanticSerializationError

import database.daily_summaries as summaries_db
from database.read_boundary import MalformedDocError, parse_payload_strict
from models.daily_summary import DailySummaryResponse
from utils.observability.fallback import record_fallback
from utils.other.list_budget import ListReadBudget, ListReadBudgetExhausted

logger = logging.getLogger(__name__)


class DailySummaryUnavailable(Exception):
    """Stored or generated recap data cannot be represented by the released response schema."""


def _parse(record: Any, uid: str) -> DailySummaryResponse:
    try:
        parsed = parse_payload_strict(
            DailySummaryResponse, record, document_path=f'users/{uid}/daily_summaries/<response>'
        )
        # The legacy model permits extra fields. A Firestore-valid bytes/reference/NaN
        # value can validate but still fail FastAPI's JSON serialization afterwards.
        json.dumps(parsed.model_dump(mode='json'), allow_nan=False)
        return parsed
    except (MalformedDocError, PydanticSerializationError, ValueError, TypeError):
        raise DailySummaryUnavailable('Daily recap data is temporarily unavailable') from None


def _invalid_read(uid: str, operation: str, count: int, *, partial: bool) -> None:
    # Pydantic exception text contains input_value, including private memories/recap content.
    # Emit metadata only, never the exception or document payload.
    logger.warning('Invalid daily summary response uid=%s operation=%s count=%d', uid, operation, count)
    if partial:
        record_fallback(
            component='other',
            from_mode='daily_summary_records',
            to_mode='validated_daily_summaries',
            reason='other',
            outcome='degraded',
            log=logger,
        )


def require_daily_summary(record: Any, *, uid: str, operation: str) -> DailySummaryResponse:
    try:
        return _parse(record, uid)
    except DailySummaryUnavailable:
        _invalid_read(uid, operation, 1, partial=False)
        raise DailySummaryUnavailable('Daily recap data is temporarily unavailable') from None


def validate_daily_summaries(records: list[Any], *, uid: str, operation: str) -> list[DailySummaryResponse]:
    valid = []
    invalid = 0
    for record in records:
        try:
            valid.append(_parse(record, uid))
        except DailySummaryUnavailable:
            invalid += 1
    if invalid:
        _invalid_read(uid, operation, invalid, partial=bool(valid))
        if not valid:
            raise DailySummaryUnavailable('Daily recap data is temporarily unavailable')
    return valid


def read_daily_summary_page(
    uid: str,
    *,
    limit: int,
    offset: int,
    start_date: str | None = None,
    end_date: str | None = None,
    request: Any = None,
) -> list[DailySummaryResponse]:
    invalid = 0

    def readable(record: dict) -> bool:
        nonlocal invalid
        try:
            _parse(record, uid)
            return True
        except DailySummaryUnavailable:
            invalid += 1
            return False

    # Filter before offset/limit. Released clients page by returned item count; filtering an
    # already-limited raw page would hide older recaps or duplicate its last row on the next page.
    budget = ListReadBudget.for_request(request, route='daily_summaries', owner_uid=uid)
    try:
        rows = summaries_db.get_daily_summaries(
            uid,
            limit=limit,
            offset=offset,
            start_date=start_date,
            end_date=end_date,
            record_filter=readable,
            read_budget=budget,
        )
    except ListReadBudgetExhausted:
        budget.observe('unavailable')
        # A partial page would make released clients stop loading, hiding valid older recaps.
        raise DailySummaryUnavailable('Daily recap read budget exhausted') from None
    budget.observe('complete')
    valid = validate_daily_summaries(rows, uid=uid, operation='list')
    if invalid:
        _invalid_read(uid, 'list', invalid, partial=bool(valid) or offset > 0)
        if not valid and offset == 0:
            raise DailySummaryUnavailable('Daily recap data is temporarily unavailable')
    return valid

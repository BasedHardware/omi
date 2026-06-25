from datetime import date, datetime, timezone
from typing import Annotated, Any, TypeVar

from fastapi import HTTPException, Query
from pydantic import BaseModel, Field, TypeAdapter, ValidationError, model_validator

PositiveLimit = Annotated[int, Query(ge=1, le=1000)]
CalendarMeetingsLimit = Annotated[int, Query(ge=1, le=100)]
NonNegativeOffset = Annotated[int, Query(ge=0)]
HistoryDays = Annotated[int, Query(ge=1, le=365)]

ModelT = TypeVar('ModelT', bound=BaseModel)


def parse_form_json(model_type: type[ModelT] | type[dict], raw_value: str, field_name: str) -> ModelT | dict[str, Any]:
    """Validate a JSON string submitted in a multipart/form-data field.

    FastAPI cannot apply normal JSON body validation to string form fields. Keep
    this helper as the single boundary for those endpoints so malformed JSON and
    non-object payloads consistently fail with 422 before any I/O work.
    """
    try:
        if isinstance(model_type, type) and issubclass(model_type, BaseModel):
            return model_type.model_validate_json(raw_value)
        return TypeAdapter(dict[str, Any]).validate_json(raw_value)
    except (ValidationError, ValueError) as e:
        raise HTTPException(status_code=422, detail=f'Invalid {field_name}: {e}')


def validate_calendar_date(value: str | None, field_name: str = 'date') -> str | None:
    """Validate YYYY-MM-DD strings as real calendar dates and return the original string."""
    if value is None:
        return None
    try:
        date.fromisoformat(value)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f'Invalid {field_name}: expected a real YYYY-MM-DD date') from e
    return value


def parse_timezone_aware_datetime(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as e:
        raise ValueError(f'{field_name} must be a valid ISO 8601 datetime') from e
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f'{field_name} must include a timezone offset')
    return parsed


def parse_sync_filename_timestamp(path: str) -> int:
    """Parse and validate the unix timestamp suffix in a sync .bin filename.

    Filenames are expected to end with _<unix-seconds-or-millis>.bin. The
    returned timestamp is UTC seconds and is safe to pass to fromtimestamp(...,
    tz=timezone.utc).
    """
    filename = path.split('/')[-1]
    try:
        raw_timestamp = int(filename.rsplit('_', 1)[1].rsplit('.', 1)[0])
    except (IndexError, ValueError) as e:
        raise ValueError('invalid timestamp') from e

    timestamp = raw_timestamp // 1000 if raw_timestamp > 10_000_000_000 else raw_timestamp
    try:
        timestamp_dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    except (OSError, OverflowError, ValueError) as e:
        raise ValueError('invalid timestamp') from e

    now = datetime.now(timezone.utc)
    if timestamp_dt > now or timestamp_dt < datetime(2024, 1, 1, tzinfo=timezone.utc):
        raise ValueError('invalid timestamp')
    return timestamp


class ImageChunkEnvelope(BaseModel):
    id: str = Field(min_length=1)
    index: int = Field(ge=0)
    total: int = Field(ge=1, le=256)
    data: str = Field(min_length=1)

    @model_validator(mode='after')
    def validate_index_within_total(self):
        if self.index >= self.total:
            raise ValueError('index must be smaller than total')
        return self

    def validate_against_cached_total(self, cached_total: int | None) -> None:
        if cached_total is not None and cached_total != self.total:
            raise ValueError('total must be consistent for all chunks in an image upload')
        if cached_total is not None and self.index >= cached_total:
            raise ValueError('index is outside the cached upload buffer')

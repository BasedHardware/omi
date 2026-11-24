"""Shared date and disjunction validation for conversation list/count requests."""

from datetime import datetime, timezone
from typing import List

from fastapi import HTTPException

# Firestore 'in' filters accept at most 30 values (see database/apps.py, database/chat.py). Reject
# an oversized status/source filter before it reaches the query so a caller cannot turn a
# comma-separated filter into an unhandled 500. ConversationStatus and the source set are both
# tiny, so a cap of 20 can never reject a request a real client would send.
MAX_IN_FILTER_VALUES = 20


def aware_datetime(value: datetime) -> datetime:
    # FastAPI parses a query datetime as naive or timezone-aware depending on whether the client
    # included a UTC offset. Normalize to timezone-aware (UTC) so comparing the two ends of a date
    # range never raises TypeError on mixed awareness (which would surface as a 500).
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def reject_oversized_filter(values: List[str], field_name: str) -> None:
    if len(values) > MAX_IN_FILTER_VALUES:
        raise HTTPException(status_code=400, detail=f"{field_name} accepts at most {MAX_IN_FILTER_VALUES} values")

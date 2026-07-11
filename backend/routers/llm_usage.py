from pydantic import BaseModel

"""Per-day LLM usage drill-down, a companion to /v1/users/me/llm-usage.

Wires the tested-but-unwired database.llm_usage day getter to a read endpoint. This
lives in its own module because the natural host, routers/users.py (where the other
/v1/users/me/llm-usage routes are), is a very large file; a small new router keeps
the change contained. The per-feature aggregation itself lives in the database layer
(get_daily_usage_summary), shared with get_usage_summary via _sum_model_tokens.
"""

from datetime import date as date_type, datetime, timezone
from typing import Dict, Optional

from fastapi import APIRouter, Depends, Query

import database.llm_usage as llm_usage_db
from utils.other import endpoints as auth

router = APIRouter()


class LlmUsageCounters(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    call_count: int = 0


class DailyLlmUsageResponse(BaseModel):
    date: str
    features: Dict[str, LlmUsageCounters] = {}
    total: LlmUsageCounters
    has_data: bool = False


@router.get('/v1/users/me/llm-usage/daily', response_model=DailyLlmUsageResponse, tags=['users'])
def get_daily_llm_usage(
    date: Optional[date_type] = Query(default=None, description='UTC day (YYYY-MM-DD); defaults to today'),
    uid: str = Depends(auth.get_current_user_uid),
):
    """The current user's LLM token usage for a single UTC day, by feature and totals.

    The existing GET /v1/users/me/llm-usage returns only a 30-day aggregate; this exposes a
    single day. The date query param is a typed date, so Pydantic validates it at the API
    boundary (a malformed value yields 422). Returns zeros with has_data=false when the day
    has no recorded usage.
    """
    day = datetime(date.year, date.month, date.day, tzinfo=timezone.utc) if date else None
    return llm_usage_db.get_daily_usage_summary(uid, day)

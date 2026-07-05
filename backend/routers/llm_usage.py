"""Per-day LLM usage drill-down, a companion to /v1/users/me/llm-usage.

Wires the tested-but-unwired database.llm_usage.get_daily_usage helper to a read
endpoint. This lives in its own module because the natural host, routers/users.py
(where the other /v1/users/me/llm-usage routes are), is a very large file; a small
new router keeps the change contained.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

import database.llm_usage as llm_usage_db
from utils.other import endpoints as auth

router = APIRouter()

# Scalar fields stored alongside the per-feature maps on a daily usage doc.
_META_KEYS = {'date', 'last_updated'}


@router.get('/v1/users/me/llm-usage/daily', tags=['users'])
def get_daily_llm_usage(
    date: Optional[str] = Query(default=None, description='UTC day as YYYY-MM-DD; defaults to today'),
    uid: str = Depends(auth.get_current_user_uid),
):
    """The current user's LLM token usage for a single UTC day, by feature and totals.

    The existing GET /v1/users/me/llm-usage returns only a 30-day aggregate; this exposes
    a single day. Reads only users/{uid}/llm_usage/{YYYY-MM-DD}; returns zeros with
    has_data=false when nothing was recorded for that day.
    """
    if date is None:
        day = datetime.now(timezone.utc)
    else:
        try:
            day = datetime.strptime(date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(status_code=400, detail='date must be in YYYY-MM-DD format')

    raw = llm_usage_db.get_daily_usage(uid, day)  # {} when no data for the day

    features = {}
    total_in = total_out = total_calls = 0
    for feature, models in raw.items():
        if feature in _META_KEYS or not isinstance(models, dict):
            continue
        f_in = f_out = f_calls = 0
        for _model, tokens in models.items():
            # Only nested {feature}.{model} token dicts count; skip cost-only scalar buckets,
            # mirroring get_usage_summary.
            if isinstance(tokens, dict):
                f_in += tokens.get('input_tokens', 0)
                f_out += tokens.get('output_tokens', 0)
                f_calls += tokens.get('call_count', 0)
        if f_in or f_out or f_calls:
            features[feature] = {
                'input_tokens': f_in,
                'output_tokens': f_out,
                'total_tokens': f_in + f_out,
                'call_count': f_calls,
            }
            total_in += f_in
            total_out += f_out
            total_calls += f_calls

    return {
        'date': day.strftime('%Y-%m-%d'),
        'features': features,
        'total': {
            'input_tokens': total_in,
            'output_tokens': total_out,
            'total_tokens': total_in + total_out,
            'call_count': total_calls,
        },
        'has_data': bool(features),
    }

"""Weekly and monthly recaps rolled up from the stored daily recaps (#4468)."""

import logging
from datetime import date as Date
from datetime import datetime
from itertools import islice
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

import database.daily_summaries as daily_summaries_db
import database.notifications as notification_db
import database.users as users_db
from database.conversation_scan import RECAP_PEOPLE_SCAN_CAP, conversation_scan_budget, recap_people_scan
from models.period_recap import PeriodRecapResponse
from utils.observability.fallback import record_fallback
from utils.other import endpoints as auth
from utils.people_stats import aggregate_people_stats
from utils.period_recaps import (
    RECAP_PERIODS,
    build_period_recap,
    local_today,
    period_bounds,
    period_utc_bounds,
    previous_period_bounds,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# Two full months of daily recaps: the period plus the one before it.
RECAP_SUMMARY_READ_LIMIT = 62


@router.get('/v1/users/recaps/{period}', tags=['v1'], response_model=PeriodRecapResponse)
def get_period_recap(
    request: Request,
    period: str,
    date: Optional[str] = Query(None, description='Any local date in the period (YYYY-MM-DD); defaults to today'),
    uid: str = Depends(auth.get_current_user_uid),
):
    """
    Get the weekly (Monday-Sunday) or monthly recap that contains ``date``.

    Rolled up from the user's daily recaps: totals, busiest day, highlights,
    decisions, open questions, open action items, the people talked to most,
    and the previous period's totals. No AI call is made.
    """
    if period not in RECAP_PERIODS:
        raise HTTPException(status_code=422, detail="period must be 'week' or 'month'")
    time_zone = notification_db.get_user_time_zone(uid)
    today = local_today(time_zone)
    if date is None:
        anchor = today
    else:
        try:
            anchor = datetime.strptime(date, '%Y-%m-%d').date()
        except ValueError:
            raise HTTPException(status_code=422, detail='Invalid date format. Use YYYY-MM-DD')
        if anchor > today:
            raise HTTPException(status_code=422, detail='Date cannot be in the future')

    start, end = period_bounds(period, anchor)
    previous_start, _ = previous_period_bounds(period, start)
    summaries = daily_summaries_db.get_daily_summaries(
        uid,
        limit=RECAP_SUMMARY_READ_LIMIT,
        offset=0,
        start_date=previous_start.isoformat(),
        end_date=end.isoformat(),
    )
    people_stats, people_names = _period_people(request, uid, start, end, time_zone)
    return PeriodRecapResponse(
        **build_period_recap(
            period,
            start,
            end,
            summaries,
            previous_summaries=summaries,
            people_stats=people_stats,
            people_names=people_names,
        )
    )


def _period_people(request: Request, uid: str, start: Date, end: Date, time_zone: Optional[str]):
    """People stats for the period; a failed scan degrades to a recap without people."""
    try:
        start_utc, end_utc = period_utc_bounds(start, end, time_zone)
        budget = conversation_scan_budget(request, route='period_recap')
        conversations = recap_people_scan(uid, start_date=start_utc, end_date=end_utc, budget=budget)
        stats = aggregate_people_stats(islice(conversations, RECAP_PEOPLE_SCAN_CAP))
        names = {
            person.get('id'): person.get('name')
            for person in users_db.get_people(uid)
            if isinstance(person, dict) and person.get('id') in stats
        }
        return stats, names
    except Exception as exc:
        record_fallback(
            component='period_recap',
            from_mode='with_people',
            to_mode='without_people',
            reason='other',
            outcome='degraded',
            log=logger,
        )
        logger.warning('period recap people scan failed error_class=%s', type(exc).__name__)
        return {}, {}

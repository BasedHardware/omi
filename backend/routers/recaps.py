"""Weekly and monthly recaps rolled up from the stored daily recaps (#4468)."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

import database.action_items as action_items_db
import database.daily_summaries as daily_summaries_db
import database.notifications as notification_db
import database.users as users_db
from database.conversation_scan import RECAP_PEOPLE_SCAN_CAP, conversation_scan_budget, recap_people_scan
from models.period_recap import PeriodRecapResponse
from utils.observability.fallback import record_fallback
from utils.other import endpoints as auth
from utils.other.list_budget import ListReadBudget, finish_list_budget
from utils.people_stats import collect_people_stats
from utils.period_recaps import (
    MAX_TOP_PEOPLE,
    MIN_RECAP_DATE,
    RECAP_PERIODS,
    build_period_recap,
    local_today,
    period_bounds,
    period_utc_bounds,
    previous_period_bounds,
    rank_people,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# Two full months of daily recaps (the period plus the one before it), with room
# for a regenerated copy of every date. A read that fills it may be cut off, so
# the comparison with the previous period is then left out.
RECAP_SUMMARY_READ_LIMIT = 124
# Open tasks read for the recap. Locked (paywalled) tasks are dropped after the
# read and the rest capped at MAX_RECAP_ITEMS, so the read takes more than it
# shows: newer locked tasks cannot crowd out the open ones. The query cannot
# filter on is_locked, as older tasks have no such field.
RECAP_TASK_READ_LIMIT = 50


@router.get('/v1/users/recaps/{period}', tags=['v1'], response_model=PeriodRecapResponse)
def get_period_recap(
    request: Request,
    response: Response,
    period: str,
    date: Optional[str] = Query(None, description='Any local date in the period (YYYY-MM-DD); defaults to today'),
    uid: str = Depends(auth.get_current_user_uid),
):
    """
    Get the weekly (Monday-Sunday) or monthly recap that contains ``date``.

    Rolled up from the user's daily recaps: totals, busiest day, highlights,
    decisions, open questions, the live open tasks created in the period, the
    people talked to most, and the previous period's totals over the same
    stretch. No AI call is made. A read cut short by the request budget, or a
    failed task or people read, sets ``X-Omi-List-Truncated``.
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
        if anchor < MIN_RECAP_DATE:
            raise HTTPException(status_code=422, detail=f'Date must be on or after {MIN_RECAP_DATE.isoformat()}')
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
    start_utc, end_utc = period_utc_bounds(start, end, time_zone)
    budget = conversation_scan_budget(request, route='period-recap')
    open_tasks, tasks_failed = _period_open_tasks(uid, start_utc, end_utc, budget)
    people_stats, people_names = _period_people(uid, start_utc, end_utc, budget)
    if tasks_failed:
        # Marked only now: an exhausted budget would end the people scan before it read anything.
        _mark_partial(budget)
    recap = PeriodRecapResponse(
        **build_period_recap(
            period,
            start,
            end,
            summaries,
            previous_summaries=summaries if len(summaries) < RECAP_SUMMARY_READ_LIMIT else None,
            today=today,
            action_items=open_tasks,
            time_zone=time_zone,
            people_stats=people_stats,
            people_names=people_names,
        )
    )
    finish_list_budget(response, budget)
    return recap


def _mark_partial(budget: ListReadBudget) -> None:
    """A failed side read leaves the recap partial: report it as truncated.

    The budget names only 'deadline' and 'documents'. A failed read is closer to
    'deadline': it is transient and Try Again can clear it, whereas 'documents'
    describes a fixed allowance that a retry would hit again.
    """
    budget.mark_exhausted('deadline')


def _period_open_tasks(
    uid: str, start_utc: datetime, end_utc: datetime, budget: ListReadBudget
) -> Tuple[List[Dict[str, Any]], bool]:
    """The live open tasks created in the period, and whether the read failed.

    A failed read degrades to no tasks. The caller marks the response partial
    once the other reads are done, so the failure cannot cut them short.
    """
    try:
        tasks = action_items_db.get_action_items(
            uid, completed=False, start_date=start_utc, end_date=end_utc, limit=RECAP_TASK_READ_LIMIT, budget=budget
        )
        return tasks, False
    except Exception:
        # The fallback warning carries no cause; keep it at debug so an
        # unexpected error (not just a failed read) is still traceable.
        logger.debug('period recap open-task read failed', exc_info=True)
        record_fallback(
            component='daily_summary',
            from_mode='with_tasks',
            to_mode='without_tasks',
            reason='other',
            outcome='degraded',
            log=logger,
        )
        return [], True


def _period_people(
    uid: str, start_utc: datetime, end_utc: datetime, budget: ListReadBudget
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
    """People stats for the period; a failed scan degrades to a recap without people, marked partial.

    The ranking samples the period's newest RECAP_PEOPLE_SCAN_CAP conversations.
    Filling that cap is the documented sample, not a truncation: only a budget
    cut (marked by the scan itself) or a failure makes the response partial.
    A dismissed person keeps their history but is left out, as the People list
    leaves them out.
    """
    try:
        conversations = recap_people_scan(uid, start_date=start_utc, end_date=end_utc, budget=budget)
        # No uid: the shared People-stats cache is not scoped to a date range.
        stats = collect_people_stats(conversations, scan_cap=RECAP_PEOPLE_SCAN_CAP, budget=budget)
        names: Dict[str, str] = {}
        for person in users_db.get_people_by_ids(uid, rank_people(stats)[: MAX_TOP_PEOPLE * 3]):
            person_id = person.get('id') if isinstance(person, dict) else None
            name = person.get('name') if isinstance(person, dict) else None
            dismissed = isinstance(person, dict) and person.get('is_dismissed') is True
            if isinstance(person_id, str) and person_id in stats and isinstance(name, str) and not dismissed:
                names[person_id] = name
        return stats, names
    except Exception:
        logger.debug('period recap people scan failed', exc_info=True)
        record_fallback(
            component='daily_summary',
            from_mode='with_people',
            to_mode='without_people',
            reason='other',
            outcome='degraded',
            log=logger,
        )
        _mark_partial(budget)
        return {}, {}

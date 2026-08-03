"""Assemble one edition.

The rule that shapes this file: omit, never pad. Every block is optional and a thin day
produces a thin paper. Length is a hard constraint rather than a target, so the caps here
are not tuning knobs — raising them changes what the product is.
"""

import logging
from datetime import date, timedelta

import database.daily_summaries as daily_summaries_db
from database.users import get_people
from models.other import Person
from models.paper import Edition, EditionTier, MarginNote

from .desk import find_dropped_people
from .editorial import write_editorial
from .loops import find_open_loops
from .stances import find_one_sided_stance

logger = logging.getLogger(__name__)

# How far back the longitudinal blocks look. Two weeks is long enough for a loop to feel
# genuinely dropped and short enough that a closed thread does not resurface.
WINDOW_DAYS = 14

MAX_OPEN_LOOPS = 3
MAX_DESK_ITEMS = 1


def _window(uid: str, target: date) -> list[dict]:
    """Stored daily summaries for the window ending on ``target``, inclusive."""
    start = (target - timedelta(days=WINDOW_DAYS)).isoformat()
    return daily_summaries_db.get_daily_summaries(
        uid,
        limit=WINDOW_DAYS + 1,
        start_date=start,
        end_date=target.isoformat(),
    )


def _people_names(uid: str) -> list[str]:
    try:
        return [p.name for p in Person.deserialize_many_safe(get_people(uid)) if p.name]
    except Exception as e:  # noqa: BLE001 — the desk block is optional.
        logger.warning('paper: could not load people, skipping desk block: %s', e)
        return []


def _margin_from(summaries: list[dict]) -> MarginNote | None:
    """One thing learned, most recent first."""
    for summary in sorted(summaries, key=lambda s: str(s.get('date') or ''), reverse=True):
        for nugget in summary.get('knowledge_nuggets') or []:
            insight = ((nugget or {}).get('insight') or '').strip()
            if insight:
                return MarginNote(insight=insight, source_date=str(summary.get('date') or ''))
    return None


def build_edition(
    uid: str,
    target_date: date,
    tier: EditionTier = EditionTier.EDITION,
    issue_number: int = 1,
) -> Edition:
    """Build the edition for ``target_date``.

    The free tier stops after the lede. That is the paywall: not fewer words, but no
    longitudinal reading of the record.
    """
    summaries = _window(uid, target_date)
    edition = Edition(date=target_date.isoformat(), issue_number=issue_number, tier=tier)
    if not summaries:
        return edition

    today_key = target_date.isoformat()
    today_summary = next((s for s in summaries if str(s.get('date') or '') == today_key), None)
    if today_summary is None:
        today_summary = max(summaries, key=lambda s: str(s.get('date') or ''))

    stance = find_one_sided_stance(summaries) if tier is EditionTier.EDITION else None
    lede, counterpoint = write_editorial(uid, today_summary, stance)
    edition.lede = lede

    if tier is not EditionTier.EDITION:
        return edition

    edition.counterpoint = counterpoint
    edition.open_loops = find_open_loops(summaries, target_date, limit=MAX_OPEN_LOOPS)
    edition.desk = find_dropped_people(summaries, _people_names(uid), target_date, limit=MAX_DESK_ITEMS)
    edition.margin = _margin_from(summaries)
    return edition

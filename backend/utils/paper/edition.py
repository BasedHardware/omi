"""Assemble one edition.

Two rules shape this file.

**Omit, never pad.** Every section is optional and a thin day produces a thin
paper. The caps are not tuning knobs; raising them changes what the product is.

**A dead source costs one section, never the edition.** Each source is gathered
independently and reports its own health. What failed is printed on the page,
because a paper that has quietly had no Gmail for two weeks looks exactly like
a paper about a quiet fortnight.
"""

import asyncio
import logging
from datetime import date, timedelta

from models.paper import Commitment, Edition, EditionTier, SourceHealth
from utils.executors import db_executor, llm_executor, run_blocking
from utils.log_sanitizer import sanitize
from utils.retrieval.tools.integration_base import (
    get_access_token_checked,
    get_integration_checked,
)

from . import context as context_mod
from . import interests as interests_mod
from . import photo as photo_mod
from .editorial import build_today, cluster_newsletters, pick_buzz, rank_for_you, write_cover, write_yesterday
from .sources.calendar_source import fetch_today
from .sources.discovery import paper_candidates, web_candidates
from .sources.gmail_source import GOOGLE_INTEGRATION_KEY, fetch_newsletters
from .sources.hackernews import fetch_buzz

logger = logging.getLogger(__name__)

MAX_COMMITMENTS = 5
MAX_NEWSLETTER_STORIES = 12
MAX_PAPERS = 3


def _google_access(uid: str) -> tuple[dict | None, str | None]:
    """The Google grant Gmail and Calendar both ride on."""
    integration, err = get_integration_checked(
        uid,
        GOOGLE_INTEGRATION_KEY,
        'Google',
        'Google account not connected',
        'Error checking Google connection',
    )
    if err:
        return None, None
    token, token_err = get_access_token_checked(integration, 'Google access token missing')
    if token_err:
        return integration, None
    return integration, token


# An item this far past due is not a task any more, it is a note to self that
# never got closed. Printing a dozen of them turns Today into a graveyard.
STALE_AFTER_DAYS = 21

# Due inside this window is the actual reason to read a section called Today.
IMMINENT_DAYS = 7


def _commitment_rank(item: dict, today: date, yesterday: date) -> tuple[int, str] | None:
    """Sort key for one open action item, or None when it should not print.

    Ranked by what makes it worth reading this morning, not by whichever due
    date is oldest. Sorting ascending by due date surfaced eight items a month
    overdue and buried everything created yesterday, which is exactly backwards
    for a daily paper.
    """
    due = str(item.get('due_at') or item.get('due_date') or '')[:10]
    created = str(item.get('created_at') or '')[:10]

    if created and created >= yesterday.isoformat():
        return (0, due or created)  # came out of yesterday, still warm
    if due and today.isoformat() <= due <= (today + timedelta(days=IMMINENT_DAYS)).isoformat():
        return (1, due)  # due today or this week
    if due and (today - timedelta(days=STALE_AFTER_DAYS)).isoformat() <= due < today.isoformat():
        return (2, due)  # overdue, but recently enough to still be real
    if due:
        return None  # older than three weeks: a graveyard entry
    if created and created >= (today - timedelta(days=STALE_AFTER_DAYS)).isoformat():
        return (3, created)  # no due date, but recent
    return None


def _commitments_from(context: context_mod.DayContext, today: date) -> list[Commitment]:
    """Open action items worth putting in front of the reader this morning."""
    yesterday = today - timedelta(days=1)
    ranked: list[tuple[tuple[int, str], Commitment]] = []
    for item in context.commitments:
        text = str(item.get('description') or item.get('title') or '').strip()
        if not text:
            continue
        rank = _commitment_rank(item, today, yesterday)
        if rank is None:
            continue
        due = str(item.get('due_at') or item.get('due_date') or '')[:10]
        ranked.append((rank, Commitment(text=text, due=due, source='action_item')))

    ranked.sort(key=lambda pair: pair[0])
    return [commitment for _, commitment in ranked[:MAX_COMMITMENTS]]


def _unpack(result: object, arity: int, failure: SourceHealth) -> tuple:
    """A gathered source result, or empty values plus a failed health record.

    Sources return `(items, health)` or `(items, held_back, health)`. When one
    raises, the section is emptied and the failure is reported rather than
    disappearing into a quiet-looking page.
    """
    if isinstance(result, BaseException):
        logger.warning('paper: a source raised: %s', sanitize(str(result)))
        return tuple([[]] * (arity - 1)) + (failure,)
    return tuple(result)  # type: ignore[arg-type]


async def build_edition(
    uid: str,
    target_date: date,
    tier: EditionTier = EditionTier.EDITION,
    issue_number: int = 1,
) -> Edition:
    """Build the edition published on ``target_date``.

    The paper is a morning object: it reports on the day before and looks ahead
    to the day it is read. ``yesterday`` is therefore built from
    ``target_date - 1`` and ``today`` from ``target_date`` itself.

    The free tier stops after yesterday. That is the paywall: not fewer words,
    but no reading of the outside world through the reader's context.
    """
    edition = Edition(date=target_date.isoformat(), issue_number=issue_number, tier=tier)
    yesterday_date = target_date - timedelta(days=1)

    day_context = await run_blocking(db_executor, context_mod.gather, uid, yesterday_date)
    edition.source_health.extend(day_context.health)

    edition.yesterday = await run_blocking(llm_executor, write_yesterday, uid, day_context)

    if tier is not EditionTier.EDITION:
        return edition

    integration, access_token = await run_blocking(db_executor, _google_access, uid)

    profile = await run_blocking(llm_executor, interests_mod.get_profile, uid, target_date)
    edition.source_health.append(
        SourceHealth(
            source='interest profile',
            ok=profile.is_usable,
            fetched=profile.covers_days,
            kept=len(profile.interests),
            note='' if profile.is_usable else 'not enough record to learn interests yet',
        )
    )

    # Independent reads, run together. gather() is exception-safe per source and
    # each of these returns its own health, so one failure never cancels the rest.
    newsletters_task = fetch_newsletters(uid, integration, access_token, yesterday_date)
    calendar_task = fetch_today(integration, access_token, target_date)
    web_task = web_candidates(profile)

    # return_exceptions keeps the promise in this module's docstring: one source
    # raising costs its section, not the edition. Without it the first exception
    # propagates and the whole request 500s.
    results = await asyncio.gather(newsletters_task, calendar_task, web_task, return_exceptions=True)

    newsletter_messages, held_back, gmail_health = _unpack(
        results[0], 3, SourceHealth(source='gmail', ok=False, note='gmail read raised')
    )
    events, calendar_health = _unpack(
        results[1], 2, SourceHealth(source='calendar', ok=False, note='calendar read raised')
    )
    news, web_health = _unpack(results[2], 2, SourceHealth(source='web', ok=False, note='web search raised'))
    edition.source_health.extend([gmail_health, calendar_health, web_health])
    edition.held_back.extend(held_back)

    candidates, arxiv_health = await run_blocking(llm_executor, paper_candidates, profile, target_date)
    edition.source_health.append(arxiv_health)

    buzz_lines, buzz_health = await run_blocking(llm_executor, fetch_buzz, profile, target_date)
    edition.source_health.append(buzz_health)
    news = list(news) + await run_blocking(llm_executor, pick_buzz, uid, buzz_lines, profile)

    edition.today = await run_blocking(
        llm_executor, build_today, uid, events, _commitments_from(day_context, target_date), calendar_health.ok
    )
    edition.newsletters = await run_blocking(
        llm_executor,
        cluster_newsletters,
        uid,
        newsletter_messages,
        profile,
        MAX_NEWSLETTER_STORIES,
    )
    edition.for_you = await run_blocking(llm_executor, rank_for_you, uid, candidates, news, profile, MAX_PAPERS)

    try:
        edition.photo = await run_blocking(llm_executor, photo_mod.make_photo, uid, day_context)
        edition.source_health.append(
            SourceHealth(
                source='photo',
                ok=True,
                kept=1 if edition.photo else 0,
                note='' if edition.photo else 'no groundable moment in the day',
            )
        )
    except Exception as e:  # noqa: BLE001 — the photo never blocks the edition.
        logger.warning('paper: photo step failed: %s', sanitize(str(e)))
        edition.source_health.append(SourceHealth(source='photo', ok=False, note=sanitize(str(e))[:200]))

    edition.cover = await run_blocking(llm_executor, write_cover, uid, _cover_contents(edition))
    return edition


def _cover_contents(edition: Edition) -> list[str]:
    """What today's edition actually contains, for the cover line."""
    lines: list[str] = []
    if edition.yesterday and edition.yesterday.headline:
        lines.append(f'Yesterday: {edition.yesterday.headline}')
    if edition.today and edition.today.events:
        lines.append(f'{len(edition.today.events)} events today')
    for story in edition.newsletters[:6]:
        lines.append(f'News: {story.summary}')
    for item in edition.for_you.papers:
        lines.append(f'Paper: {item.title}')
    return lines

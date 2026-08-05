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
from utils.executors import db_executor, run_blocking
from utils.log_sanitizer import sanitize
from utils.retrieval.tools.integration_base import (
    get_access_token_checked,
    get_integration_checked,
)

from . import context as context_mod
from . import interests as interests_mod
from . import photo as photo_mod
from .editorial import build_today, cluster_newsletters, rank_for_you, write_cover, write_yesterday
from .sources.calendar_source import fetch_today
from .sources.discovery import paper_candidates, web_candidates
from .sources.gmail_source import GOOGLE_INTEGRATION_KEY, fetch_newsletters

logger = logging.getLogger(__name__)

MAX_COMMITMENTS = 8
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


def _commitments_from(context: context_mod.DayContext) -> list[Commitment]:
    """Open action items, most urgent first."""
    out: list[Commitment] = []
    for item in context.commitments:
        text = str(item.get('description') or item.get('title') or '').strip()
        if not text:
            continue
        due = item.get('due_at') or item.get('due_date') or ''
        out.append(Commitment(text=text, due=str(due or '')[:10], source='action_item'))
    out.sort(key=lambda c: (not c.due, c.due))
    return out[:MAX_COMMITMENTS]


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

    edition.yesterday = await run_blocking(db_executor, write_yesterday, uid, day_context)

    if tier is not EditionTier.EDITION:
        return edition

    integration, access_token = await run_blocking(db_executor, _google_access, uid)

    profile = await run_blocking(db_executor, interests_mod.get_profile, uid, target_date)
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

    (newsletter_messages, held_back, gmail_health), (events, calendar_health), (news, web_health) = (
        await asyncio.gather(
            newsletters_task,
            calendar_task,
            web_task,
        )
    )
    edition.source_health.extend([gmail_health, calendar_health, web_health])
    edition.held_back.extend(held_back)

    candidates, arxiv_health = await run_blocking(db_executor, paper_candidates, profile, target_date)
    edition.source_health.append(arxiv_health)

    edition.today = await run_blocking(db_executor, build_today, uid, events, _commitments_from(day_context))
    edition.newsletters = await run_blocking(
        db_executor,
        cluster_newsletters,
        uid,
        newsletter_messages,
        profile,
        MAX_NEWSLETTER_STORIES,
    )
    edition.for_you = await run_blocking(db_executor, rank_for_you, uid, candidates, news, profile, MAX_PAPERS)

    try:
        edition.photo = await run_blocking(db_executor, photo_mod.make_photo, uid, day_context)
    except Exception as e:  # noqa: BLE001 — the photo never blocks the edition.
        logger.warning('paper: photo step failed: %s', sanitize(str(e)))

    edition.cover = await run_blocking(db_executor, write_cover, uid, _cover_contents(edition))
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

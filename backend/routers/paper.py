"""PAPER — the daily personal newspaper."""

import logging
from datetime import date as date_cls

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse

import database.auth as auth_db
import database.daily_summaries as daily_summaries_db
from models.paper import Edition, EditionTier
from utils.executors import db_executor, run_blocking
from utils.log_sanitizer import sanitize
from utils.other import endpoints as auth
from utils.paper.edition import build_edition
from utils.paper.render import render_html

router = APIRouter()

logger = logging.getLogger(__name__)

# Building an edition runs several model calls, an image generation and a set of
# web searches, so both routes are rate limited per UID. The render route calls
# the same builder and is limited identically — limiting only the JSON route
# would leave the expensive path wide open.
PAPER_RATE_POLICY = 'paper:edition'


# ============================================================================
# HELPERS
# ============================================================================


def _issue_number(uid: str, through: date_cls) -> int:
    """Editions published through ``through`` — the masthead number.

    Counted through the requested date rather than from today's total, so a
    historic edition keeps the number it was published under instead of drifting
    upward every time a new summary lands.
    """
    try:
        summaries = daily_summaries_db.get_daily_summaries(uid, limit=1000, end_date=through.isoformat())
        return max(1, len(summaries or []))
    except Exception as e:  # noqa: BLE001 — a missing count must not block the edition.
        logger.warning('paper: could not read issue number, defaulting to 1: %s', sanitize(str(e)))
        return 1


def _reader_name(uid: str) -> str:
    """The name printed on the masthead. Absent is fine; wrong is not."""
    try:
        return str(auth_db.get_user_name(uid, use_default=False) or '').strip()
    except Exception as e:  # noqa: BLE001 — the masthead name is decoration.
        logger.warning('paper: could not read reader name: %s', sanitize(str(e)))
        return ''


# ============================================================================
# ENDPOINTS
# ============================================================================


@router.get('/v1/paper/{date}', tags=['paper'], response_model=Edition)
async def get_paper(
    date: date_cls,
    tier: EditionTier = Query(EditionTier.EDITION),
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, PAPER_RATE_POLICY)),
):
    issue_number = await run_blocking(db_executor, _issue_number, uid, date)
    return await build_edition(uid, date, tier=tier, issue_number=issue_number)


@router.get('/v1/paper/{date}/render', tags=['paper'], response_class=HTMLResponse)
async def render_paper(
    date: date_cls,
    tier: EditionTier = Query(EditionTier.EDITION),
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, PAPER_RATE_POLICY)),
):
    issue_number = await run_blocking(db_executor, _issue_number, uid, date)
    edition = await build_edition(uid, date, tier=tier, issue_number=issue_number)
    name = await run_blocking(db_executor, _reader_name, uid)
    return HTMLResponse(render_html(edition, name))

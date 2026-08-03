"""PAPER — the daily personal newspaper."""

import logging
from datetime import date as date_cls

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse

import database.daily_summaries as daily_summaries_db
from models.paper import Edition, EditionTier
from utils.llms.memory import get_prompt_memories
from utils.log_sanitizer import sanitize
from utils.other import endpoints as auth
from utils.paper.edition import build_edition
from utils.paper.render import render_html

router = APIRouter()

logger = logging.getLogger(__name__)


# ============================================================================
# HELPERS
# ============================================================================


def _parse_date(value: str) -> date_cls:
    try:
        return date_cls.fromisoformat(value)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail='Date must be yyyy-mm-dd')


def _issue_number(uid: str) -> int:
    """Editions published to date — the masthead number and the streak counter."""
    try:
        return max(1, daily_summaries_db.get_summaries_count(uid))
    except Exception as e:  # noqa: BLE001 — a missing count must not block the edition.
        logger.warning('paper: could not read issue number, defaulting to 1: %s', sanitize(str(e)))
        return 1


def _reader_name(uid: str) -> str:
    """The name printed on the masthead. Absent is fine; wrong is not."""
    try:
        user_name, _ = get_prompt_memories(uid)
        return str(user_name or '').strip()
    except Exception as e:  # noqa: BLE001 — the masthead name is decoration.
        logger.warning('paper: could not read reader name: %s', sanitize(str(e)))
        return ''


# ============================================================================
# ENDPOINTS
# ============================================================================


@router.get('/v1/paper/{date}', tags=['paper'], response_model=Edition)
def get_paper(
    date: str,
    tier: EditionTier = Query(EditionTier.EDITION),
    uid: str = Depends(auth.get_current_user_uid),
):
    return build_edition(uid, _parse_date(date), tier=tier, issue_number=_issue_number(uid))


@router.get('/v1/paper/{date}/render', tags=['paper'], response_class=HTMLResponse)
def render_paper(
    date: str,
    tier: EditionTier = Query(EditionTier.EDITION),
    uid: str = Depends(auth.get_current_user_uid),
):
    edition = build_edition(uid, _parse_date(date), tier=tier, issue_number=_issue_number(uid))
    return HTMLResponse(render_html(edition, _reader_name(uid)))

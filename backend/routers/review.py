"""Default-off Review and entity pages. All storage is scoped to the auth uid."""

import os
import re
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response

from config.open_loops import open_loops_enabled
from database import candidates, notifications as notification_db, review_changes, review_store
from database.open_loops import get_cards as get_open_loop_cards
from models.entity_pages import EntitiesResponse, EntityCorrection, EntityPage
from models.open_loops import (
    OPEN_LOOP_ANSWER_STATE,
    OpenLoopAnswerRequest,
    OpenLoopAnswerResponse,
    OpenLoopCard,
    OpenLoopCardsResponse,
)
from models.review import (
    ReviewAnswer,
    ReviewAnswerReceipt,
    ReviewChange,
    ReviewChangesResponse,
    ReviewItemsResponse,
    ReviewItemsResponseV2,
    ReviewAnswerV2,
)
from utils import entity_pages, review
from utils.open_loops import service as open_loops_service
from utils.other import endpoints as auth
from utils.speaker_tag_prompts.service import TagPromptInvalid
from utils.task_intelligence.task_links import TaskLinkValidationError


def require_review_surface():
    if os.environ.get('REVIEW_SURFACE_MODE', 'off').strip().lower() != 'on':
        raise HTTPException(status_code=404, detail='review_surface_disabled')


router = APIRouter(dependencies=[Depends(require_review_surface)])
ReadUser = Depends(auth.with_rate_limit(auth.get_current_user_uid, 'review:read'))
WriteUser = Depends(auth.with_rate_limit(auth.get_current_user_uid, 'review:write'))


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except (review_store.ReviewNotFound, candidates.CandidateNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (
        review_store.ReviewConflict,
        candidates.CandidateStoreError,
        TagPromptInvalid,
        TaskLinkValidationError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get('/v1/review/items', response_model=ReviewItemsResponse, tags=['review'])
def get_review_items(uid: str = ReadUser):
    return _call(review.get_items, uid)


@router.post('/v1/review/items/{item_id}/answer', response_model=ReviewAnswerReceipt, tags=['review'])
def answer_review_item(item_id: str, answer: ReviewAnswer, background_tasks: BackgroundTasks, uid: str = WriteUser):
    if item_id.startswith('agent_proposal:'):
        raise HTTPException(status_code=409, detail='Agent proposals require Review v2')
    return _call(review.answer_item, uid, item_id, answer, schedule=background_tasks.add_task)


@router.get('/v2/review/items', response_model=ReviewItemsResponseV2, tags=['review'])
def get_review_items_v2(uid: str = ReadUser):
    return _call(review.get_items, uid, include_agent_proposals=True)


@router.post('/v2/review/items/{item_id}/answer', response_model=ReviewAnswerReceipt, tags=['review'])
def answer_review_item_v2(
    item_id: str, answer: ReviewAnswerV2, background_tasks: BackgroundTasks, uid: str = WriteUser
):
    return _call(review.answer_item, uid, item_id, answer, schedule=background_tasks.add_task)


def _valid_zone(value: str | None) -> str | None:
    if not value:
        return None
    try:
        ZoneInfo(value)
    except Exception:
        return None
    return value


# The cards documents are keyed by the pass's ISO local day, and card ids are
# loop ids: 'ol-<16 hex>' (store.stable_key) or 'task-<task id>' (a task-born
# loop). Malformed values are rejected here, before any Firestore read, instead
# of surfacing as a store error.
_OPEN_LOOP_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
_OPEN_LOOP_CARD_ID = re.compile(r'^(ol-[0-9a-f]{16}|task-[A-Za-z0-9_-]{1,64})$')


def _valid_open_loop_date(value: str) -> bool:
    if not _OPEN_LOOP_DATE.fullmatch(value):
        return False
    try:
        datetime.strptime(value, '%Y-%m-%d')
    except ValueError:
        return False
    return True


@router.get('/v1/review/open-loops', response_model=OpenLoopCardsResponse, tags=['review'])
def get_review_open_loops(uid: str = ReadUser, time_zone: str | None = Query(default=None, max_length=64)):
    """The day's pending open-loop cards, at most the three the daily pass wrote.

    The day is resolved exactly as the pass dated it for this uid (see
    ``open_loops_service.cards_display_day``), with a bounded fallback to the
    previous day; the zone resolution follows the user usage endpoint: a valid
    request zone, else the stored profile zone, else UTC.
    """
    if not open_loops_enabled():
        return OpenLoopCardsResponse()
    tz = _valid_zone(time_zone) or _valid_zone(notification_db.get_user_time_zone(uid))
    day, pending = open_loops_service.list_owner_pending_cards(uid, tz=tz)
    cards = []
    for card in pending:
        card_id = str(card.get('id') or '')
        question = str(card.get('question') or '')
        if not card_id or not question:
            continue
        cards.append(
            OpenLoopCard(
                card_id=card_id,
                date=day,
                question=question,
                context_line=str(card.get('context_line') or ''),
            )
        )
    return OpenLoopCardsResponse(cards=cards)


@router.post('/v1/review/open-loops/{date}/{card_id}/answer', response_model=OpenLoopAnswerResponse, tags=['review'])
def answer_review_open_loop(date: str, card_id: str, request: OpenLoopAnswerRequest, uid: str = WriteUser):
    if not open_loops_enabled():
        raise HTTPException(status_code=404, detail='open_loops_disabled')
    if not _valid_open_loop_date(date):
        raise HTTPException(status_code=422, detail='invalid_open_loop_date')
    if not _OPEN_LOOP_CARD_ID.fullmatch(card_id):
        raise HTTPException(status_code=422, detail='invalid_open_loop_card_id')
    card = open_loops_service.answer_card(uid, card_id, request.action, date_str=date)
    if card is None:
        day_cards = get_open_loop_cards(uid, date) or []
        existing = next((c for c in day_cards if str(c.get('id')) == str(card_id)), None)
        if existing is not None and existing.get('state') != open_loops_service.PENDING_STATE:
            raise HTTPException(status_code=409, detail='open_loop_card_already_answered')
        raise HTTPException(status_code=404, detail='open_loop_card_not_found')
    return OpenLoopAnswerResponse(card_id=str(card.get('id')), date=date, state=OPEN_LOOP_ANSWER_STATE[request.action])


@router.get('/v1/review/changes', response_model=ReviewChangesResponse, tags=['review'])
def get_review_changes(cursor: str | None = Query(default=None, max_length=256), uid: str = ReadUser):
    return _call(review_changes.list_changes, uid, cursor)


@router.post('/v1/review/changes/{change_id}/undo', response_model=ReviewChange, tags=['review'])
def undo_review_change(change_id: str, uid: str = WriteUser):
    return _call(review_changes.set_undone, uid, change_id, True)


@router.post('/v1/review/changes/{change_id}/redo', response_model=ReviewChange, tags=['review'])
def redo_review_change(change_id: str, uid: str = WriteUser):
    return _call(review_changes.set_undone, uid, change_id, False)


@router.get('/v1/entities', response_model=EntitiesResponse, tags=['entity_pages'])
def get_entities(type: Literal['project'] = Query(...), uid: str = ReadUser):
    return EntitiesResponse(entities=_call(entity_pages.project_refs, uid))


@router.get('/v1/entities/{entity_id}/page', response_model=EntityPage, tags=['entity_pages'])
def get_entity_page(entity_id: str, uid: str = ReadUser):
    return _call(entity_pages.get_entity_page, uid, entity_id)


@router.post('/v1/entities/{entity_id}/corrections', status_code=204, tags=['entity_pages'])
def correct_entity(entity_id: str, correction: EntityCorrection, uid: str = WriteUser):
    _call(entity_pages.correct_entity, uid, entity_id, correction.text)
    return Response(status_code=204)


@router.get('/v1/conversations/{conversation_id}/entities', response_model=EntitiesResponse, tags=['entity_pages'])
def get_conversation_entities(conversation_id: str, uid: str = ReadUser):
    return EntitiesResponse(entities=_call(entity_pages.conversation_entities, uid, conversation_id))

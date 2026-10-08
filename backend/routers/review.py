"""Default-off Review and entity pages. All storage is scoped to the auth uid."""

import os
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response

from database import candidates, review_changes, review_store
from models.entity_pages import EntitiesResponse, EntityCorrection, EntityPage
from models.review import ReviewAnswer, ReviewAnswerReceipt, ReviewChange, ReviewChangesResponse, ReviewItemsResponse
from utils import entity_pages, review
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
    return _call(review.answer_item, uid, item_id, answer, schedule=background_tasks.add_task)


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

"""Filter-independent processing projection and owner-only recovery endpoints."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from fastapi.responses import JSONResponse, Response
from google.cloud import firestore

from database import processing_attention as store
from database._client import db, run_transactional
from models.pending_work import (
    AttentionItemsPage,
    AttentionRetryAllResponse,
    AttentionRetryResponse,
    PendingWorkSnapshot,
    RetryAllRequest,
    SeenRequest,
)
from utils.other import endpoints as auth

router = APIRouter(tags=['processing'])


@router.get('/v1/pending-work', response_model=PendingWorkSnapshot)
def pending_work(uid: str = Depends(auth.get_current_user_uid)):
    from database.sync_jobs import pending_sync_jobs

    attention = store.list_items(uid, limit=store.LIMIT)
    return {
        'enabled': True,
        'items': store.pending_conversations(uid) + pending_sync_jobs(uid),
        'attention_unseen_count': sum(not item['seen'] for item in attention),
    }


@router.get('/v1/attention-items', response_model=AttentionItemsPage)
def attention_items(uid: str = Depends(auth.get_current_user_uid)):
    items = store.list_items(uid)
    return {'enabled': True, 'items': items, 'unseen_count': sum(not item['seen'] for item in items)}


def _operation_response(operation: dict[str, Any]) -> dict[str, Any]:
    return {'operation_id': operation['operation_id'], 'state': operation['state']}


def _run(uid: str, item_id: str, operation: dict[str, Any], background_tasks: BackgroundTasks) -> None:
    # Existing reprocess is synchronous. Share its implementation, preserving speaker learning.
    from routers.conversations import execute_reprocess
    from database import conversations as conversations_db
    from utils.conversations.factory import deserialize_conversation

    try:
        raw = conversations_db.get_conversation(uid, operation['conversation_id'])
        if not raw or conversations_db.is_soft_deleted(raw) or store.generation(raw) != operation['generation']:
            store.finish(uid, operation, 'failed', item_id)
            operation['state'] = 'failed'
            return
        if not store.unresolved(raw):
            store.finish(uid, operation, 'succeeded', item_id)
            operation['state'] = 'succeeded'
            return
        conversation = deserialize_conversation(raw)
        if not store.owns_live_claim(uid, operation):
            store.finish(uid, operation, 'failed', item_id)
            operation['state'] = 'failed'
            return
        result = execute_reprocess(
            uid,
            conversation.id,
            conversation,
            conversation.language or 'en',
            None,
            None,
            bool(raw.get('discarded')),
            background_tasks,
            None,
        )
        state = 'failed' if not result.structured.overview else 'succeeded'
    except Exception:
        store.finish(uid, operation, 'failed', item_id)
        raise
    store.finish(uid, operation, state, item_id)
    operation['state'] = state


def _claim_item(uid: str, item_id: str, idempotency_key: str | None = None) -> tuple[dict[str, Any], bool]:
    snapshot = store.items_ref(uid).document(item_id).get()
    if not snapshot.exists:
        raise HTTPException(status_code=404, detail='Attention item not found')
    try:
        return store.claim(uid, (snapshot.to_dict() or {})['conversation_id'], item_id, idempotency_key=idempotency_key)
    except store.ClaimRejected as error:
        if str(error) == 'not_found':
            raise HTTPException(status_code=404, detail='Attention item not found') from error
        raise HTTPException(status_code=409, detail='not_retryable') from error


@router.post('/v1/attention-items/retry-all', response_model=AttentionRetryAllResponse)
def retry_all(
    request: RetryAllRequest, background_tasks: BackgroundTasks, uid: str = Depends(auth.get_current_user_uid)
):
    items = [item for item in store.list_items(uid) if item['retryable']]
    request_ref = (
        db.collection('users')
        .document(uid)
        .collection('processing_retry_batches')
        .document(hashlib.sha256(request.idempotency_key.encode()).hexdigest())
    )

    @firestore.transactional
    def reserve(transaction):
        snapshot = request_ref.get(transaction=transaction)
        if snapshot.exists:
            return snapshot.to_dict()['response'], []
        # Stage writes until every claim read has completed (Firestore ordering rule).
        writes = []

        claims = []
        for item in items:
            conv_ref = (
                db.collection('users').document(uid).collection('conversations').document(item['conversation_id'])
            )
            claims.append((item, conv_ref))
        # Snapshot all documents first, then execute the shared decision using cached reads.
        owned = []
        operations = []
        for item, conv_ref in claims:
            try:
                operation, is_owner = store.claim_in_transaction(
                    transaction,
                    conv_ref,
                    uid,
                    store.items_ref(uid).document(item['id']),
                    staged_writes=writes,
                    idempotency_key='batch:' + request.idempotency_key,
                )
            except store.ClaimRejected:
                continue
            operations.append({'id': item['id'], **_operation_response(operation)})
            if is_owner:
                owned.append((item['id'], operation))
        for method, args, kwargs in writes:
            getattr(transaction, method)(*args, **kwargs)
        response = {'operations': operations}
        transaction.set(request_ref, {'response': response})
        return response, owned

    response, owned = run_transactional(db, reserve)
    for item_id, operation in owned:
        try:
            _run(uid, item_id, operation, background_tasks)
        except Exception:
            logging.getLogger(__name__).error('Attention retry failed operation_id=%s', operation['operation_id'])
    return response


@router.post('/v1/attention-items/seen', status_code=204, response_class=Response, response_model=None)
def seen(request: SeenRequest, uid: str = Depends(auth.get_current_user_uid)):
    ids = [item['id'] for item in store.list_items(uid)] if request.all else request.ids
    for item_id in ids:
        ref = store.items_ref(uid).document(item_id)
        if ref.get().exists:
            ref.update({'seen': True})
    return Response(status_code=204)


@router.post('/v1/attention-items/{item_id}/retry', response_model=AttentionRetryResponse)
def retry(
    item_id: str,
    background_tasks: BackgroundTasks,
    uid: str = Depends(auth.get_current_user_uid),
    idempotency_key: str | None = Header(default=None, alias='Idempotency-Key'),
):
    try:
        operation, owned = _claim_item(uid, item_id, idempotency_key)
    except HTTPException as error:
        if error.status_code == 409:
            return JSONResponse(status_code=409, content={'state': 'not_retryable'})
        raise
    if owned:
        _run(uid, item_id, operation, background_tasks)
    return _operation_response(operation)


@router.post('/v1/attention-items/{item_id}/dismiss', status_code=204, response_class=Response, response_model=None)
def dismiss(item_id: str, uid: str = Depends(auth.get_current_user_uid)):
    ref = store.items_ref(uid).document(item_id)
    if not ref.get().exists:
        raise HTTPException(status_code=404, detail='Attention item not found')
    ref.update({'active': False, 'dismissed': True})
    return Response(status_code=204)

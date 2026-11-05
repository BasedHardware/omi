"""Read-only task presence and cursor-paged task-bearing conversations."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from google.api_core.exceptions import GoogleAPICallError

from database import conversation_task_links
from models.conversation import SearchRequest
from models.conversation_tasks import (
    ConversationTaskPresenceRequest,
    ConversationTaskPresenceResponse,
    TaskConversationPageRequest,
    TaskConversationPageResponse,
)
from routers.conversations import search_conversations_endpoint
from utils.conversations import paid_lock_recovery
from utils.conversations.render import redact_conversations_for_list
from utils.conversations.task_filter import TaskFilterCursorError, TaskFilterUnavailable, task_conversation_page
from utils.executors import db_executor, run_blocking
from utils.other import endpoints as auth
from utils.other.list_budget import ListReadBudgetExhausted, list_read_budget_for_request

router = APIRouter()


@router.post('/v1/conversations/task-presence', response_model=ConversationTaskPresenceResponse, tags=['conversations'])
async def task_presence(
    data: ConversationTaskPresenceRequest,
    request: Request,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, 'conversations:task-presence')),
):
    budget = list_read_budget_for_request(request, route='conversation-task-presence')
    try:
        presence = await run_blocking(
            db_executor,
            lambda: conversation_task_links.visible_task_presence(uid, data.conversation_ids, budget=budget),
        )
    except (ListReadBudgetExhausted, GoogleAPICallError) as error:
        raise HTTPException(
            status_code=503, detail='Task presence is temporarily unavailable. Please retry.'
        ) from error
    budget.observe('complete')
    return {'presence': presence}


@router.post('/v1/conversations/with-tasks/page', response_model=TaskConversationPageResponse, tags=['conversations'])
async def conversations_with_tasks(
    data: TaskConversationPageRequest,
    request: Request,
    response: Response,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, 'conversations:search')),
):
    budget = list_read_budget_for_request(request, route='conversations-with-tasks')

    async def browse(after, scope):
        rows, more = await run_blocking(
            db_executor,
            lambda: conversation_task_links.browse_candidate_page(uid, data, after=after, scope=scope, budget=budget),
        )
        await run_blocking(db_executor, paid_lock_recovery.heal_conversations, uid, [row for _, row in rows if row])
        return rows, more

    async def search(page):
        # Reuse the actual search owner, including exact references, spoken-word
        # hits, lock recovery, authoritative hydration and privacy redaction.
        return await search_conversations_endpoint(
            SearchRequest(
                query=data.query,
                page=page,
                per_page=50,
                include_discarded=data.include_discarded,
                start_date=data.start_date.isoformat() if data.start_date else None,
                end_date=data.end_date.isoformat() if data.end_date else None,
            ),
            uid=uid,
            request=request,
            response=response,
        )

    async def presence(ids):
        return await run_blocking(
            db_executor, lambda: conversation_task_links.linked_task_presence(uid, ids, budget=budget)
        )

    try:
        result = await task_conversation_page(
            uid, data, budget=budget, browse_page=browse, search_page=search, presence=presence
        )
    except TaskFilterCursorError as error:
        raise HTTPException(status_code=400, detail='Invalid task-filter cursor. Refresh this list.') from error
    except (
        TaskFilterUnavailable,
        ListReadBudgetExhausted,
        GoogleAPICallError,
        paid_lock_recovery.RecoveryUnavailable,
    ) as error:
        raise HTTPException(
            status_code=503, detail='Conversations with tasks are temporarily unavailable. Please retry.'
        ) from error
    redact_conversations_for_list(result['items'])
    budget.observe('truncated' if result['partial'] else 'complete')
    return result

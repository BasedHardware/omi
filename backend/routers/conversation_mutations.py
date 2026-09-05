"""Authenticated HTTP contract for durable conversation mutations."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

import database.conversation_mutations as mutations_db
from models.conversation import (
    ConversationSyncConflictResponse,
    ConversationSyncMutationRequest,
    ConversationSyncMutationResponse,
)
from utils.other import endpoints as auth

router = APIRouter()


@router.post(
    '/v1/conversations/{conversation_id}/mutations',
    tags=['conversations'],
    response_model=ConversationSyncMutationResponse,
    responses={409: {'model': ConversationSyncConflictResponse}},
)
def apply_conversation_sync_mutation(
    conversation_id: str,
    request: ConversationSyncMutationRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    """Apply or exactly replay one durable optimistic conversation mutation."""
    try:
        response = mutations_db.apply_conversation_sync_mutation(
            uid,
            conversation_id,
            client_mutation_id=request.client_mutation_id,
            base_revision=request.base_revision,
            operation=request.operation.model_dump(mode='python'),
        )
    except mutations_db.ConversationMutationNotFoundError as error:
        raise HTTPException(status_code=404, detail='Conversation not found') from error
    except mutations_db.ConversationMutationLockedError as error:
        raise HTTPException(status_code=402, detail='A paid plan is required to access this conversation.') from error
    except mutations_db.ConversationMutationConflictError as error:
        conflict = ConversationSyncConflictResponse.model_validate(error.response)
        return JSONResponse(status_code=409, content=conflict.model_dump(mode='json'))
    except mutations_db.ConversationMutationReceiptUnavailableError as error:
        raise HTTPException(status_code=503, detail='Conversation mutation acknowledgement unavailable') from error
    return ConversationSyncMutationResponse.model_validate(response)

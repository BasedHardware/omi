"""Authenticated owner undo for shared chat edit receipts."""

import re
from fastapi import APIRouter, Depends, HTTPException
from models.chat import UndoChatReceiptResponse
from utils.messaging.undo import UndoStore
from utils.executors import postprocess_executor, run_blocking
from utils.other import endpoints as auth

router = APIRouter()


@router.post('/v1/chat/receipts/{receipt_id}/undo', response_model=UndoChatReceiptResponse)
async def undo_chat_receipt(receipt_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """Undo an owner-scoped chat write once and return its updated content block."""
    if not re.fullmatch(r'[a-f0-9]{32}', receipt_id):
        raise HTTPException(status_code=404, detail='Receipt not found')
    try:
        return await run_blocking(postprocess_executor, UndoStore().undo_for_owner, uid, receipt_id)
    except LookupError:
        raise HTTPException(status_code=404, detail='Receipt not found')
    except PermissionError:
        raise HTTPException(status_code=409, detail='Receipt can no longer be undone')

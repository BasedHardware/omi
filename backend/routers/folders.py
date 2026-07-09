import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from pydantic import BaseModel, ValidationError

import database.folders as folders_db
import database.conversations as conversations_db
from models.folder import (
    Folder,
    CreateFolderRequest,
    UpdateFolderRequest,
    MoveConversationRequest,
    BulkMoveConversationsRequest,
    ReorderFoldersRequest,
    FolderMutationResponse,
    BulkMoveConversationsResponse,
)
from models.conversation import Conversation, conversation_mutation_data
from utils.conversations.render import redact_conversations_for_list
from utils.other import endpoints as auth

logger = logging.getLogger(__name__)

router = APIRouter()


class ConversationFolderMutationResponse(BaseModel):
    status: str
    id: str
    updated_at: Optional[datetime] = None
    revision: Optional[str] = None


@router.get('/v1/folders', response_model=List[Folder], tags=['folders'])
def get_folders(uid: str = Depends(auth.get_current_user_uid)):
    """
    Get all folders for the current user.
    Initializes system folders if this is the first access.
    """
    folders = folders_db.get_folders(uid)
    if not folders:
        folders = folders_db.initialize_system_folders(uid)
    return folders


@router.post('/v1/folders', response_model=Folder, tags=['folders'])
def create_folder(request: CreateFolderRequest, uid: str = Depends(auth.get_current_user_uid)):
    """Create a new custom folder."""
    # Check folder limit (50 custom folders)
    existing = folders_db.get_folders(uid)
    custom_count = len([f for f in existing if not f.get('is_system')])
    if custom_count >= 50:
        raise HTTPException(status_code=400, detail="Maximum folder limit reached (50 custom folders)")

    folder = folders_db.create_folder(
        uid,
        name=request.name,
        description=request.description,
        color=request.color,
        icon=request.icon,
    )
    return folder


@router.get('/v1/folders/{folder_id}', response_model=Folder, tags=['folders'])
def get_folder(folder_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """Get a specific folder by ID."""
    folder = folders_db.get_folder(uid, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    return folder


@router.patch('/v1/folders/{folder_id}', response_model=Folder, tags=['folders'])
def update_folder(folder_id: str, request: UpdateFolderRequest, uid: str = Depends(auth.get_current_user_uid)):
    """Update folder metadata (name, description, color, icon, order)."""
    folder = folders_db.get_folder(uid, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    update_data = request.model_dump(exclude_unset=True)
    if update_data:
        folders_db.update_folder(uid, folder_id, update_data)

    return folders_db.get_folder(uid, folder_id)


@router.delete('/v1/folders/{folder_id}', status_code=204, tags=['folders'])
def delete_folder(
    folder_id: str,
    move_to_folder_id: Optional[str] = Query(None, description="Target folder for conversations (defaults to 'Other')"),
    uid: str = Depends(auth.get_current_user_uid),
):
    """Delete a folder and move its conversations to another folder."""
    folder = folders_db.get_folder(uid, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    if folder.get('is_system'):
        raise HTTPException(status_code=400, detail="Cannot delete system folder")

    if move_to_folder_id:
        if move_to_folder_id == folder_id:
            raise HTTPException(status_code=400, detail="Cannot move conversations to the folder being deleted")
        if not folders_db.get_folder(uid, move_to_folder_id):
            raise HTTPException(status_code=404, detail="Target folder not found")

    folders_db.delete_folder(uid, folder_id, move_to_folder_id)


@router.post('/v1/folders/reorder', response_model=FolderMutationResponse, tags=['folders'])
def reorder_folders(request: ReorderFoldersRequest, uid: str = Depends(auth.get_current_user_uid)):
    """Reorder folders by providing an ordered list of folder IDs."""
    existing_ids = {folder['id'] for folder in folders_db.get_folders(uid)}
    unknown_ids = [folder_id for folder_id in request.folder_ids if folder_id not in existing_ids]
    if unknown_ids:
        raise HTTPException(status_code=422, detail={"message": "Unknown folder IDs", "folder_ids": unknown_ids})

    folders_db.reorder_folders(uid, request.folder_ids)
    return {"status": "ok"}


@router.get('/v1/folders/{folder_id}/conversations', response_model=List[Conversation], tags=['folders'])
def get_folder_conversations(
    folder_id: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    include_discarded: bool = Query(False),
    uid: str = Depends(auth.get_current_user_uid),
) -> List[Conversation]:
    """Get all conversations in a folder with pagination."""
    folder = folders_db.get_folder(uid, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    conversations = folders_db.get_conversations_in_folder(
        uid, folder_id, limit=limit, offset=offset, include_discarded=include_discarded
    )
    redact_conversations_for_list(conversations)
    # Validate each record individually so one malformed/legacy conversation doesn't fail the whole list
    # with a 500.
    valid_conversations: List[Conversation] = []
    for conv in conversations:
        try:
            valid_conversations.append(Conversation.model_validate(conv))
        except ValidationError as e:
            invalid_fields = [err['loc'][0] for err in e.errors() if err.get('loc')]
            logger.warning(f"Skipping invalid conversation in folder {folder_id} for uid {uid}: {invalid_fields}")
            continue
    return valid_conversations


@router.patch(
    '/v1/conversations/{conversation_id}/folder',
    response_model=ConversationFolderMutationResponse,
    tags=['folders'],
)
def move_conversation_to_folder(
    conversation_id: str, request: MoveConversationRequest, uid: str = Depends(auth.get_current_user_uid)
):
    """Move a conversation to a different folder."""
    conversation = conversations_db.get_conversation_access_state(uid, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conversation.get('is_locked', False):
        raise HTTPException(status_code=402, detail="A paid plan is required to access this conversation.")

    if request.folder_id:
        folder = folders_db.get_folder(uid, request.folder_id)
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found")

    write_result = folders_db.move_conversation_to_folder(uid, conversation_id, request.folder_id)
    if write_result is False or write_result is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "ok", **conversation_mutation_data(conversation_id, write_result)}


@router.post(
    '/v1/folders/{folder_id}/conversations/bulk-move',
    response_model=BulkMoveConversationsResponse,
    tags=['folders'],
)
def bulk_move_conversations(
    folder_id: str, request: BulkMoveConversationsRequest, uid: str = Depends(auth.get_current_user_uid)
):
    """Move multiple conversations to a folder."""
    folder = folders_db.get_folder(uid, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    # Validate none of the conversations are locked
    for conv_id in request.conversation_ids:
        conv = conversations_db.get_conversation(uid, conv_id)
        if not conv:
            raise HTTPException(status_code=404, detail=f"Conversation {conv_id} not found")
        if conv.get('is_locked', False):
            raise HTTPException(status_code=402, detail="A paid plan is required to access this conversation.")

    moved = folders_db.bulk_move_conversations_to_folder(uid, request.conversation_ids, folder_id)
    return {"status": "ok", "moved_count": moved}

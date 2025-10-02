from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional

import database.folders as folders_db
import database.conversations as conversations_db
from models.folder import (
    Folder,
    CreateFolderRequest,
    UpdateFolderRequest,
    MoveConversationRequest,
    BulkMoveConversationsRequest,
    DeleteFolderRequest,
)
from models.conversation import Conversation
from utils.other import endpoints as auth

router = APIRouter()


@router.get('/v1/folders', response_model=List[Folder], tags=['folders'])
def get_folders(uid: str = Depends(auth.get_current_user_uid)):
    """Get all folders for the current user"""
    folders = folders_db.get_folders(uid)
    return folders


@router.post('/v1/folders', response_model=Folder, tags=['folders'])
def create_folder(request: CreateFolderRequest, uid: str = Depends(auth.get_current_user_uid)):
    """Create a new folder"""
    folder = folders_db.create_folder(uid, name=request.name, color=request.color, icon=request.icon)
    return folder


@router.get('/v1/folders/{folder_id}', response_model=Folder, tags=['folders'])
def get_folder(folder_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """Get a specific folder"""
    folder = folders_db.get_folder(uid, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    return folder


@router.patch('/v1/folders/{folder_id}', response_model=Folder, tags=['folders'])
def update_folder(folder_id: str, request: UpdateFolderRequest, uid: str = Depends(auth.get_current_user_uid)):
    """Update folder metadata"""
    folder = folders_db.get_folder(uid, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    update_data = {}
    if request.name is not None:
        update_data['name'] = request.name
    if request.color is not None:
        update_data['color'] = request.color
    if request.icon is not None:
        update_data['icon'] = request.icon
    if request.order is not None:
        update_data['order'] = request.order

    if update_data:
        folders_db.update_folder(uid, folder_id, update_data)

    # Return updated folder
    return folders_db.get_folder(uid, folder_id)


@router.delete('/v1/folders/{folder_id}', status_code=204, tags=['folders'])
def delete_folder(
    folder_id: str,
    move_to_folder_id: Optional[str] = Query(None, description="Target folder for conversations"),
    uid: str = Depends(auth.get_current_user_uid),
):
    """Delete a folder and move its conversations"""
    folder = folders_db.get_folder(uid, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    if folder.get('is_default'):
        raise HTTPException(status_code=400, detail="Cannot delete default folder")

    try:
        folders_db.delete_folder(uid, folder_id, move_to_folder_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"status": "Ok"}


@router.get('/v1/folders/{folder_id}/conversations', response_model=List[Conversation], tags=['folders'])
def get_folder_conversations(
    folder_id: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    include_discarded: bool = Query(False),
    uid: str = Depends(auth.get_current_user_uid),
):
    """Get all conversations in a folder"""
    folder = folders_db.get_folder(uid, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    # Get conversation IDs in folder
    conversation_ids = folders_db.get_conversations_in_folder(
        uid, folder_id, limit=limit, offset=offset, include_discarded=include_discarded
    )

    # Fetch full conversations with proper decryption
    if not conversation_ids:
        return []

    conversations = conversations_db.get_conversations_by_id(uid, conversation_ids, include_discarded=include_discarded)
    return conversations


@router.patch('/v1/conversations/{conversation_id}/folder', tags=['folders', 'conversations'])
def move_conversation_to_folder(
    conversation_id: str, request: MoveConversationRequest, uid: str = Depends(auth.get_current_user_uid)
):
    """Move a conversation to a folder"""
    conversation = conversations_db.get_conversation(uid, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Verify folder exists (if not moving to default)
    if request.folder_id is not None:
        folder = folders_db.get_folder(uid, request.folder_id)
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found")

    folders_db.move_conversation_to_folder(uid, conversation_id, request.folder_id)

    return {"status": "Ok"}


@router.post('/v1/folders/{folder_id}/conversations/bulk-move', tags=['folders'])
def bulk_move_conversations(
    folder_id: str, request: BulkMoveConversationsRequest, uid: str = Depends(auth.get_current_user_uid)
):
    """Move multiple conversations to a folder"""
    folder = folders_db.get_folder(uid, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    success = folders_db.bulk_move_conversations_to_folder(uid, request.conversation_ids, folder_id)

    if not success:
        raise HTTPException(status_code=400, detail="Failed to move conversations")

    return {"status": "Ok", "moved_count": len(request.conversation_ids)}

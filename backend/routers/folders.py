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
    ReorderFoldersRequest,
)
from models.conversation import Conversation
from utils.other import endpoints as auth

router = APIRouter()


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

    folders_db.delete_folder(uid, folder_id, move_to_folder_id)


@router.post('/v1/folders/reorder', tags=['folders'])
def reorder_folders(request: ReorderFoldersRequest, uid: str = Depends(auth.get_current_user_uid)):
    """Reorder folders by providing an ordered list of folder IDs."""
    folders_db.reorder_folders(uid, request.folder_ids)
    return {"status": "ok"}


@router.get('/v1/folders/{folder_id}/conversations', response_model=List[Conversation], tags=['folders'])
def get_folder_conversations(
    folder_id: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    include_discarded: bool = Query(False),
    uid: str = Depends(auth.get_current_user_uid),
):
    """Get all conversations in a folder with pagination."""
    folder = folders_db.get_folder(uid, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    conversations = folders_db.get_conversations_in_folder(
        uid, folder_id, limit=limit, offset=offset, include_discarded=include_discarded
    )
    return conversations


@router.patch('/v1/conversations/{conversation_id}/folder', tags=['folders'])
def move_conversation_to_folder(
    conversation_id: str, request: MoveConversationRequest, uid: str = Depends(auth.get_current_user_uid)
):
    """Move a conversation to a different folder."""
    conversation = conversations_db.get_conversation(uid, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if request.folder_id:
        folder = folders_db.get_folder(uid, request.folder_id)
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found")

    folders_db.move_conversation_to_folder(uid, conversation_id, request.folder_id)
    return {"status": "ok"}


@router.post('/v1/folders/{folder_id}/conversations/bulk-move', tags=['folders'])
def bulk_move_conversations(
    folder_id: str, request: BulkMoveConversationsRequest, uid: str = Depends(auth.get_current_user_uid)
):
    """Move multiple conversations to a folder."""
    folder = folders_db.get_folder(uid, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    moved = folders_db.bulk_move_conversations_to_folder(uid, request.conversation_ids, folder_id)
    return {"status": "ok", "moved_count": moved}

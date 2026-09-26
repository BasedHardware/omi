import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from pydantic import ValidationError

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
from models.conversation import Conversation, ConversationMutationResponse
from utils.conversations.render import redact_conversations_for_list
from utils.other import endpoints as auth

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get('/v1/folders', response_model=List[Folder], tags=['folders'])
def get_folders(uid: str = Depends(auth.get_current_user_uid)):
    """
    Get all folders for the current user.
    Initializes system folders if this is the first access.
    """
    try:
        folders = folders_db.get_folders(uid)
        if not folders:
            folders = folders_db.initialize_system_folders(uid)
        return folders
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch folders for user {uid}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch folders")


@router.post('/v1/folders', response_model=Folder, tags=['folders'])
def create_folder(request: CreateFolderRequest, uid: str = Depends(auth.get_current_user_uid)):
    """Create a new custom folder."""
    clean_name = request.name.strip() if request.name else ""
    if not clean_name:
        raise HTTPException(status_code=400, detail="Folder name cannot be empty or whitespace")

    try:
        # Check folder limit (50 custom folders)
        existing = folders_db.get_folders(uid)
        custom_count = len([f for f in existing if not f.get('is_system')])
        if custom_count >= 50:
            raise HTTPException(status_code=400, detail="Maximum folder limit reached (50 custom folders)")

        folder = folders_db.create_folder(
            uid,
            name=clean_name,
            description=request.description,
            color=request.color,
            icon=request.icon,
        )
        return folder
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create folder for user {uid}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create folder")


@router.get('/v1/folders/{folder_id}', response_model=Folder, tags=['folders'])
def get_folder(folder_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """Get a specific folder by ID."""
    clean_folder_id = folder_id.strip() if folder_id else ""
    if not clean_folder_id:
        raise HTTPException(status_code=400, detail="folder_id cannot be empty or whitespace")

    try:
        folder = folders_db.get_folder(uid, clean_folder_id)
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found")
        return folder
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get folder {clean_folder_id} for user {uid}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve folder")


@router.patch('/v1/folders/{folder_id}', response_model=Folder, tags=['folders'])
def update_folder(folder_id: str, request: UpdateFolderRequest, uid: str = Depends(auth.get_current_user_uid)):
    """Update folder metadata (name, description, color, icon, order)."""
    clean_folder_id = folder_id.strip() if folder_id else ""
    if not clean_folder_id:
        raise HTTPException(status_code=400, detail="folder_id cannot be empty or whitespace")

    update_data = request.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="At least one field must be provided for update")

    if 'name' in update_data and update_data['name'] is not None:
        clean_name = update_data['name'].strip()
        if not clean_name:
            raise HTTPException(status_code=400, detail="Folder name cannot be empty or whitespace")
        update_data['name'] = clean_name

    try:
        folder = folders_db.get_folder(uid, clean_folder_id)
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found")

        folders_db.update_folder(uid, clean_folder_id, update_data)
        updated = folders_db.get_folder(uid, clean_folder_id)
        if not updated:
            raise HTTPException(status_code=404, detail="Folder not found after update")
        return updated
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update folder {clean_folder_id} for user {uid}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update folder")


@router.delete('/v1/folders/{folder_id}', status_code=204, tags=['folders'])
def delete_folder(
    folder_id: str,
    move_to_folder_id: Optional[str] = Query(None, description="Target folder for conversations (defaults to 'Other')"),
    uid: str = Depends(auth.get_current_user_uid),
):
    """Delete a folder and move its conversations to another folder."""
    clean_folder_id = folder_id.strip() if folder_id else ""
    if not clean_folder_id:
        raise HTTPException(status_code=400, detail="folder_id cannot be empty or whitespace")

    clean_move_to_folder_id = None
    if move_to_folder_id is not None:
        clean_move_to_folder_id = move_to_folder_id.strip()
        if not clean_move_to_folder_id:
            raise HTTPException(status_code=400, detail="move_to_folder_id cannot be empty or whitespace")

    try:
        folder = folders_db.get_folder(uid, clean_folder_id)
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found")

        if folder.get('is_system'):
            raise HTTPException(status_code=400, detail="Cannot delete system folder")

        if clean_move_to_folder_id:
            if clean_move_to_folder_id == clean_folder_id:
                raise HTTPException(status_code=400, detail="Cannot move conversations to the folder being deleted")
            if not folders_db.get_folder(uid, clean_move_to_folder_id):
                raise HTTPException(status_code=404, detail="Target folder not found")

        folders_db.delete_folder(uid, clean_folder_id, clean_move_to_folder_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete folder {clean_folder_id} for user {uid}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete folder")


@router.post('/v1/folders/reorder', response_model=FolderMutationResponse, tags=['folders'])
def reorder_folders(request: ReorderFoldersRequest, uid: str = Depends(auth.get_current_user_uid)):
    """Reorder folders by providing an ordered list of folder IDs."""
    if not request.folder_ids:
        raise HTTPException(status_code=400, detail="folder_ids list cannot be empty")

    clean_folder_ids = []
    for fid in request.folder_ids:
        clean_fid = fid.strip() if fid else ""
        if not clean_fid:
            raise HTTPException(status_code=400, detail="folder_ids contains empty or whitespace ID")
        clean_folder_ids.append(clean_fid)

    try:
        existing_folders = folders_db.get_folders(uid)
        existing_ids = {folder['id'] for folder in existing_folders}
        unknown_ids = [folder_id for folder_id in clean_folder_ids if folder_id not in existing_ids]
        if unknown_ids:
            raise HTTPException(status_code=422, detail={"message": "Unknown folder IDs", "folder_ids": unknown_ids})

        folders_db.reorder_folders(uid, clean_folder_ids)
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reorder folders for user {uid}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to reorder folders")


@router.get('/v1/folders/{folder_id}/conversations', response_model=List[Conversation], tags=['folders'])
def get_folder_conversations(
    folder_id: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    include_discarded: bool = Query(False),
    uid: str = Depends(auth.get_current_user_uid),
) -> List[Conversation]:
    """Get all conversations in a folder with pagination."""
    clean_folder_id = folder_id.strip() if folder_id else ""
    if not clean_folder_id:
        raise HTTPException(status_code=400, detail="folder_id cannot be empty or whitespace")

    try:
        folder = folders_db.get_folder(uid, clean_folder_id)
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found")

        conversations = folders_db.get_conversations_in_folder(
            uid, clean_folder_id, limit=limit, offset=offset, include_discarded=include_discarded
        )
        redact_conversations_for_list(conversations)

        # Validate each record individually so one malformed/legacy conversation doesn't fail the whole list
        valid_conversations: List[Conversation] = []
        for conv in conversations:
            try:
                valid_conversations.append(Conversation.model_validate(conv))
            except ValidationError as e:
                invalid_fields = [err['loc'][0] for err in e.errors() if err.get('loc')]
                logger.warning(f"Skipping invalid conversation in folder {clean_folder_id} for uid {uid}: {invalid_fields}")
                continue
        return valid_conversations
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get conversations in folder {clean_folder_id} for user {uid}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve conversations in folder")


@router.patch(
    '/v1/conversations/{conversation_id}/folder', response_model=ConversationMutationResponse, tags=['folders']
)
def move_conversation_to_folder(
    conversation_id: str, request: MoveConversationRequest, uid: str = Depends(auth.get_current_user_uid)
):
    """Move a conversation to a different folder."""
    clean_conv_id = conversation_id.strip() if conversation_id else ""
    if not clean_conv_id:
        raise HTTPException(status_code=400, detail="conversation_id cannot be empty or whitespace")

    clean_target_folder_id = request.folder_id.strip() if request.folder_id else None

    try:
        conversation = conversations_db.get_conversation(uid, clean_conv_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if conversation.get('is_locked', False):
            raise HTTPException(status_code=402, detail="A paid plan is required to access this conversation.")

        if clean_target_folder_id:
            folder = folders_db.get_folder(uid, clean_target_folder_id)
            if not folder:
                raise HTTPException(status_code=404, detail="Folder not found")

        folders_db.move_conversation_to_folder(uid, clean_conv_id, clean_target_folder_id)
        updated_conv = conversations_db.get_conversation(uid, clean_conv_id)
        return {"status": "ok", "conversation": updated_conv}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to move conversation {clean_conv_id} to folder for user {uid}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to move conversation to folder")


@router.post(
    '/v1/folders/{folder_id}/conversations/bulk-move',
    response_model=BulkMoveConversationsResponse,
    tags=['folders'],
)
def bulk_move_conversations(
    folder_id: str, request: BulkMoveConversationsRequest, uid: str = Depends(auth.get_current_user_uid)
):
    """Move multiple conversations to a folder."""
    clean_folder_id = folder_id.strip() if folder_id else ""
    if not clean_folder_id:
        raise HTTPException(status_code=400, detail="folder_id cannot be empty or whitespace")

    if not request.conversation_ids:
        raise HTTPException(status_code=400, detail="conversation_ids list cannot be empty")

    clean_conv_ids = []
    for cid in request.conversation_ids:
        clean_cid = cid.strip() if cid else ""
        if not clean_cid:
            raise HTTPException(status_code=400, detail="conversation_ids contains empty or whitespace ID")
        clean_conv_ids.append(clean_cid)

    try:
        folder = folders_db.get_folder(uid, clean_folder_id)
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found")

        # Validate none of the conversations are locked
        for conv_id in clean_conv_ids:
            conv = conversations_db.get_conversation(uid, conv_id)
            if not conv:
                raise HTTPException(status_code=404, detail=f"Conversation {conv_id} not found")
            if conv.get('is_locked', False):
                raise HTTPException(status_code=402, detail="A paid plan is required to access this conversation.")

        moved = folders_db.bulk_move_conversations_to_folder(uid, clean_conv_ids, clean_folder_id)
        return {"status": "ok", "moved_count": moved}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to bulk move conversations to folder {clean_folder_id} for user {uid}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to bulk move conversations")

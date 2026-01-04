from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from datetime import datetime, timezone

import database.action_items as action_items_db
from utils.other import endpoints as auth
from utils.notifications import (
    send_action_item_data_message,
    send_action_item_update_message,
    send_action_item_deletion_message,
)
from pydantic import BaseModel, Field

router = APIRouter()


# Request models specific to action items
class CreateActionItemRequest(BaseModel):
    description: str = Field(description="The action item description")
    completed: bool = Field(default=False, description="Whether the action item is completed")
    due_at: Optional[datetime] = Field(default=None, description="When the action item is due")
    conversation_id: Optional[str] = Field(
        default=None, description="ID of the conversation this action item came from"
    )


class UpdateActionItemRequest(BaseModel):
    description: Optional[str] = Field(default=None, description="Updated description")
    completed: Optional[bool] = Field(default=None, description="Updated completion status")
    due_at: Optional[datetime] = Field(default=None, description="Updated due date")
    exported: Optional[bool] = Field(default=None, description="Whether the item has been exported")
    export_date: Optional[datetime] = Field(default=None, description="When the item was exported")
    export_platform: Optional[str] = Field(default=None, description="Platform the item was exported to")


class ActionItemResponse(BaseModel):
    id: str
    description: str
    completed: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    due_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    conversation_id: Optional[str] = None
    is_locked: bool = False
    exported: bool = False
    export_date: Optional[datetime] = None
    export_platform: Optional[str] = None


def _get_valid_action_item(uid: str, action_item_id: str) -> dict:
    action_item = action_items_db.get_action_item(uid, action_item_id)
    if not action_item:
        raise HTTPException(status_code=404, detail="Action item not found")

    if action_item.get('is_locked', False):
        raise HTTPException(status_code=402, detail="Unlimited Plan Required to access this action item.")

    return action_item


# *****************************
# ******** CRUD ROUTES ********
# *****************************


@router.post("/v1/action-items", response_model=ActionItemResponse, tags=['action-items'])
def create_action_item(request: CreateActionItemRequest, uid: str = Depends(auth.get_current_user_uid)):
    """Create a new action item."""
    action_item_data = {
        'description': request.description,
        'completed': request.completed,
        'due_at': request.due_at,
        'conversation_id': request.conversation_id,
    }

    action_item_id = action_items_db.create_action_item(uid, action_item_data)
    action_item = action_items_db.get_action_item(uid, action_item_id)

    if not action_item:
        raise HTTPException(status_code=500, detail="Failed to create action item")

    # Send FCM data message if action item has a due date
    if request.due_at:
        send_action_item_data_message(
            user_id=uid,
            action_item_id=action_item_id,
            description=request.description,
            due_at=request.due_at.isoformat(),
        )

    return ActionItemResponse(**action_item)


@router.get("/v1/action-items", tags=['action-items'])
def get_action_items(
    limit: int = Query(50, ge=1, le=500, description="Maximum number of action items to return"),
    offset: int = Query(0, ge=0, description="Number of action items to skip"),
    completed: Optional[bool] = Query(None, description="Filter by completion status"),
    conversation_id: Optional[str] = Query(None, description="Filter by conversation ID"),
    start_date: Optional[datetime] = Query(None, description="Filter by creation start date (inclusive)"),
    end_date: Optional[datetime] = Query(None, description="Filter by creation end date (inclusive)"),
    due_start_date: Optional[datetime] = Query(None, description="Filter by due start date (inclusive)"),
    due_end_date: Optional[datetime] = Query(None, description="Filter by due end date (inclusive)"),
    uid: str = Depends(auth.get_current_user_uid),
):
    """Get action items for the current user."""
    action_items = action_items_db.get_action_items(
        uid=uid,
        conversation_id=conversation_id,
        completed=completed,
        start_date=start_date,
        end_date=end_date,
        due_start_date=due_start_date,
        due_end_date=due_end_date,
        limit=limit,
        offset=offset,
    )

    for item in action_items:
        if item.get('is_locked', False):
            description = item.get('description', '')
            item['description'] = (description[:70] + '...') if len(description) > 70 else description

    response_items = [ActionItemResponse(**item) for item in action_items]

    has_more = len(action_items) == limit
    if has_more:
        next_batch = action_items_db.get_action_items(
            uid=uid,
            conversation_id=conversation_id,
            completed=completed,
            start_date=start_date,
            end_date=end_date,
            due_start_date=due_start_date,
            due_end_date=due_end_date,
            limit=1,
            offset=offset + limit,
        )
        has_more = len(next_batch) > 0

    return {"action_items": response_items, "has_more": has_more}


@router.get("/v1/action-items/{action_item_id}", response_model=ActionItemResponse, tags=['action-items'])
def get_action_item(action_item_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """Get a specific action item by ID."""
    action_item = _get_valid_action_item(uid, action_item_id)

    if not action_item:
        raise HTTPException(status_code=404, detail="Action item not found")

    return ActionItemResponse(**action_item)


@router.patch("/v1/action-items/{action_item_id}", response_model=ActionItemResponse, tags=['action-items'])
def update_action_item(
    action_item_id: str, request: UpdateActionItemRequest, uid: str = Depends(auth.get_current_user_uid)
):
    """Update an action item."""
    # Check if action item exists
    existing_item = _get_valid_action_item(uid, action_item_id)
    if not existing_item:
        raise HTTPException(status_code=404, detail="Action item not found")

    # Prepare update data
    update_data = {}
    if request.description is not None:
        update_data['description'] = request.description
    if request.completed is not None:
        update_data['completed'] = request.completed
        if request.completed:
            update_data['completed_at'] = datetime.now(timezone.utc)
        else:
            update_data['completed_at'] = None
    # Check if due_at was explicitly provided (even if None) to allow clearing
    # In Pydantic v2, we check model_fields_set to see if field was explicitly set
    if 'due_at' in request.model_fields_set:
        # Field was explicitly provided (even if None) - update it
        update_data['due_at'] = request.due_at
    elif request.due_at is not None:
        # Fallback: only update if not None (for backwards compatibility)
        update_data['due_at'] = request.due_at
    if request.exported is not None:
        update_data['exported'] = request.exported
    if request.export_date is not None:
        update_data['export_date'] = request.export_date
    if request.export_platform is not None:
        update_data['export_platform'] = request.export_platform

    # Update the action item
    success = action_items_db.update_action_item(uid, action_item_id, update_data)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update action item")

    # Return updated action item
    updated_item = action_items_db.get_action_item(uid, action_item_id)

    # Send FCM update message if due_at changed
    if 'due_at' in update_data and update_data['due_at']:
        send_action_item_update_message(
            user_id=uid,
            action_item_id=action_item_id,
            description=updated_item.get('description', ''),
            due_at=update_data['due_at'].isoformat(),
        )

    return ActionItemResponse(**updated_item)


@router.patch("/v1/action-items/{action_item_id}/completed", response_model=ActionItemResponse, tags=['action-items'])
def toggle_action_item_completion(
    action_item_id: str,
    completed: bool = Query(description="Whether to mark as completed or not"),
    uid: str = Depends(auth.get_current_user_uid),
):
    """Mark an action item as completed or uncompleted."""
    # Check if action item exists
    existing_item = _get_valid_action_item(uid, action_item_id)
    if not existing_item:
        raise HTTPException(status_code=404, detail="Action item not found")

    # Update completion status
    success = action_items_db.mark_action_item_completed(uid, action_item_id, completed)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update action item")

    # Return updated action item
    updated_item = action_items_db.get_action_item(uid, action_item_id)
    return ActionItemResponse(**updated_item)


@router.delete("/v1/action-items/{action_item_id}", status_code=204, tags=['action-items'])
def delete_action_item(action_item_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """Delete an action item."""
    _get_valid_action_item(uid, action_item_id)
    success = action_items_db.delete_action_item(uid, action_item_id)
    if not success:
        raise HTTPException(status_code=404, detail="Action item not found")

    # Send FCM deletion message to cancel scheduled notification
    send_action_item_deletion_message(user_id=uid, action_item_id=action_item_id)

    return {"status": "Ok"}


# *****************************
# *** CONVERSATION-SPECIFIC ***
# *****************************


@router.get("/v1/conversations/{conversation_id}/action-items", tags=['action-items'])
def get_conversation_action_items(conversation_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """Get all action items for a specific conversation."""
    action_items = action_items_db.get_action_items_by_conversation(uid, conversation_id)
    response_items = [ActionItemResponse(**item) for item in action_items]

    return {"action_items": response_items, "conversation_id": conversation_id}


@router.delete("/v1/conversations/{conversation_id}/action-items", status_code=204, tags=['action-items'])
def delete_conversation_action_items(conversation_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """Delete all action items for a specific conversation."""
    deleted_count = action_items_db.delete_action_items_for_conversation(uid, conversation_id)

    return {"status": "Ok", "deleted_count": deleted_count}


# *****************************
# ******* BATCH OPERATIONS ****
# *****************************


@router.post("/v1/action-items/batch", tags=['action-items'])
def create_action_items_batch(
    action_items: List[CreateActionItemRequest], uid: str = Depends(auth.get_current_user_uid)
):
    """Create multiple action items in a batch."""
    if not action_items:
        return {"action_items": [], "created_count": 0}

    # Prepare action items data
    action_items_data = []
    for item in action_items:
        action_item_data = {
            'description': item.description,
            'completed': False,
            'due_at': item.due_at,
            'conversation_id': item.conversation_id,
        }
        action_items_data.append(action_item_data)

    # Create batch
    created_ids = action_items_db.create_action_items_batch(uid, action_items_data)

    # Fetch created items and send FCM messages
    created_items = []
    for idx, item_id in enumerate(created_ids):
        item = action_items_db.get_action_item(uid, item_id)
        if item:
            created_items.append(ActionItemResponse(**item))

            # Send FCM data message if action item has a due date
            if idx < len(action_items) and action_items[idx].due_at:
                send_action_item_data_message(
                    user_id=uid,
                    action_item_id=item_id,
                    description=action_items[idx].description,
                    due_at=action_items[idx].due_at.isoformat(),
                )

    return {"action_items": created_items, "created_count": len(created_items)}

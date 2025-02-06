from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from models.action_item import ActionItem, ActionItemStatus
import database.action_items as action_items_db
from utils.other import endpoints as auth

router = APIRouter(
    prefix="/v1/action-items",
    tags=["action-items"]
)

class CreateActionItemRequest(BaseModel):
    description: str
    memory_id: Optional[str] = None
    due_date: Optional[datetime] = None

class UpdateActionItemRequest(BaseModel):
    description: Optional[str] = None
    status: Optional[ActionItemStatus] = None
    due_date: Optional[datetime] = None

@router.post("", response_model=ActionItem)
def create_action_item(
    request: CreateActionItemRequest,
    uid: str = Depends(auth.get_current_user_uid)
):
    return action_items_db.create_action_item(
        uid=uid,
        description=request.description,
        memory_id=request.memory_id,
        due_date=request.due_date
    )

@router.get("", response_model=List[ActionItem])
def get_action_items(
    status: Optional[ActionItemStatus] = None,
    memory_id: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0,
    uid: str = Depends(auth.get_current_user_uid)
):
    return action_items_db.get_action_items(
        uid=uid,
        status=status,
        memory_id=memory_id,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset
    )

@router.patch("/{action_item_id}", response_model=ActionItem)
def update_action_item(
    action_item_id: str,
    request: UpdateActionItemRequest,
    uid: str = Depends(auth.get_current_user_uid)
):
    updates = request.dict(exclude_unset=True)
    updated_item = action_items_db.update_action_item(uid, action_item_id, updates)
    if not updated_item:
        raise HTTPException(status_code=404, detail="Action item not found")
    return updated_item

@router.delete("/{action_item_id}")
def delete_action_item(
    action_item_id: str,
    uid: str = Depends(auth.get_current_user_uid)
):
    success = action_items_db.delete_action_item(uid, action_item_id)
    if not success:
        raise HTTPException(status_code=404, detail="Action item not found")
    return {"message": "Action item deleted successfully"}
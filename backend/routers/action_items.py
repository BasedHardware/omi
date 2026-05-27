import asyncio
import uuid

from utils.executors import db_executor

from fastapi import Request, APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from datetime import datetime, timezone

import database.action_items as action_items_db
import database.conversations as conversations_db
import database.redis_db as redis_db
from database.vector_db import (
    upsert_action_item_vector,
    upsert_action_item_vectors_batch,
    delete_action_item_vector,
    delete_action_item_vectors_batch,
    search_action_items_by_vector,
)
from utils.users import get_user_display_name
from utils.notifications import (
    send_notification,
    send_action_item_data_message,
    send_action_item_update_message,
    send_action_item_deletion_message,
    send_action_items_batch_deletion_message,
)
from utils.task_sync import auto_sync_action_item
from pydantic import BaseModel, Field
from utils.auth_middleware import require_firebase

_public_router = APIRouter()
_firebase_router = APIRouter(dependencies=[Depends(require_firebase)])


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
    apple_reminder_id: Optional[str] = Field(default=None, description="EventKit calendarItemIdentifier")
    sort_order: Optional[int] = Field(default=None, description="Manual sort order within category")
    indent_level: Optional[int] = Field(default=None, ge=0, le=3, description="Indentation level (0-3)")


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
    apple_reminder_id: Optional[str] = None
    sort_order: int = 0
    indent_level: int = 0


def _get_valid_action_item(uid: str, action_item_id: str) -> dict:
    action_item = action_items_db.get_action_item(uid, action_item_id)
    if not action_item:
        raise HTTPException(status_code=404, detail="Action item not found")

    if action_item.get('is_locked', False):
        raise HTTPException(status_code=402, detail="A paid plan is required to access this action item.")

    return action_item


# *****************************
# ******* BATCH OPERATIONS ****
# *****************************


class BatchUpdateActionItemEntry(BaseModel):
    id: str
    sort_order: Optional[int] = None
    indent_level: Optional[int] = Field(default=None, ge=0, le=3)


class BatchUpdateActionItemsRequest(BaseModel):
    items: List[BatchUpdateActionItemEntry] = Field(..., max_length=500)


@_firebase_router.patch("/v1/action-items/batch", tags=['action-items'])
def batch_update_action_items(request: Request, data: BatchUpdateActionItemsRequest):
    uid = request.state.uid
    """Batch update sort_order and indent_level for multiple action items."""
    action_items_db.batch_update_action_items(uid, data.items)
    return {"status": "ok", "updated_count": len(data.items)}


# *****************************
# ****** REMINDERS SYNC *******
# *****************************


class SyncBatchItem(BaseModel):
    id: str
    description: Optional[str] = None
    completed: Optional[bool] = None
    due_at: Optional[datetime] = None
    exported: Optional[bool] = None
    export_platform: Optional[str] = None
    apple_reminder_id: Optional[str] = None


class SyncBatchRequest(BaseModel):
    items: List[SyncBatchItem] = Field(..., max_length=100)


@_firebase_router.get("/v1/action-items/pending-sync", tags=['action-items'])
def get_pending_sync_items(request: Request, platform: str = Query('apple_reminders', description="Sync platform")):
    uid = request.state.uid
    """Get action items that need sync: pending export + already synced items for bidirectional sync."""
    result = action_items_db.get_pending_apple_reminders_sync(uid)
    pending_export = [item for item in result["pending_export"] if not item.get('is_locked', False)]
    synced_items = [item for item in result["synced_items"] if not item.get('is_locked', False)]
    return {
        "pending_export": [ActionItemResponse(**item) for item in pending_export],
        "synced_items": [ActionItemResponse(**item) for item in synced_items],
    }


@_firebase_router.patch("/v1/action-items/sync-batch", tags=['action-items'])
def sync_batch_update(request: Request, data: SyncBatchRequest):
    uid = request.state.uid
    """Batch update action items during reminders sync. Single Firestore batch commit."""
    if not data.items:
        return {"status": "ok", "updated_count": 0}

    # Pre-fetch items to skip locked ones
    locked_ids = set()
    for item in data.items:
        existing = action_items_db.get_action_item(uid, item.id)
        if existing and existing.get('is_locked', False):
            locked_ids.add(item.id)

    updates = []
    for item in data.items:
        if item.id in locked_ids:
            continue
        update_data = {}
        if item.description is not None:
            update_data['description'] = item.description
        if item.completed is not None:
            update_data['completed'] = item.completed
            if item.completed:
                update_data['completed_at'] = datetime.now(timezone.utc)
            else:
                update_data['completed_at'] = None
        if item.due_at is not None:
            update_data['due_at'] = item.due_at
        if item.exported is not None:
            update_data['exported'] = item.exported
        if item.export_platform is not None:
            update_data['export_platform'] = item.export_platform
        if item.apple_reminder_id is not None:
            update_data['apple_reminder_id'] = item.apple_reminder_id
        if update_data:
            updates.append({'id': item.id, 'data': update_data})

    action_items_db.batch_sync_update_action_items(uid, updates)

    desc_updates = [u for u in updates if 'description' in u['data']]
    if desc_updates:
        upsert_action_item_vectors_batch(
            uid, [{'action_item_id': u['id'], 'description': u['data']['description']} for u in desc_updates]
        )

    return {"status": "ok", "updated_count": len(updates)}


# *****************************
# ******** CRUD ROUTES ********
# *****************************


@_firebase_router.post("/v1/action-items", response_model=ActionItemResponse, tags=['action-items'])
def create_action_item(request: Request, data: CreateActionItemRequest):
    uid = request.state.uid
    """Create a new action item."""
    action_item_data = {
        'description': data.description,
        'completed': data.completed,
        'due_at': data.due_at,
        'conversation_id': data.conversation_id,
    }

    action_item_id = action_items_db.create_action_item(uid, action_item_data)
    action_item = action_items_db.get_action_item(uid, action_item_id)

    if not action_item:
        raise HTTPException(status_code=500, detail="Failed to create action item")

    # Send FCM data message if action item has a due date
    if data.due_at:
        send_action_item_data_message(
            user_id=uid,
            action_item_id=action_item_id,
            description=data.description,
            due_at=data.due_at.isoformat(),
        )

    upsert_action_item_vector(uid, action_item_id, data.description)

    def _run_auto_sync():
        asyncio.run(auto_sync_action_item(uid, {"id": action_item_id, **action_item_data}, skip_apple_reminders=True))

    db_executor.submit(_run_auto_sync)

    return ActionItemResponse(**action_item)


@_firebase_router.get("/v1/action-items", tags=['action-items'])
def get_action_items(
    request: Request,
    limit: int = Query(50, ge=1, le=500, description="Maximum number of action items to return"),
    offset: int = Query(0, ge=0, description="Number of action items to skip"),
    completed: Optional[bool] = Query(None, description="Filter by completion status"),
    conversation_id: Optional[str] = Query(None, description="Filter by conversation ID"),
    start_date: Optional[datetime] = Query(None, description="Filter by creation start date (inclusive)"),
    end_date: Optional[datetime] = Query(None, description="Filter by creation end date (inclusive)"),
    due_start_date: Optional[datetime] = Query(None, description="Filter by due start date (inclusive)"),
    due_end_date: Optional[datetime] = Query(None, description="Filter by due end date (inclusive)"),
):
    uid = request.state.uid
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


@_firebase_router.get("/v1/action-items/search", tags=['action-items'])
def search_action_items(
    request: Request,
    query: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(10, ge=1, le=50, description="Maximum results"),
):
    uid = request.state.uid
    """Semantic search across action items using vector similarity."""
    action_item_ids = search_action_items_by_vector(uid, query, limit=limit)
    if not action_item_ids:
        return {"action_items": []}

    action_items = action_items_db.get_action_items_by_ids(uid, action_item_ids)
    action_items = [item for item in action_items if not item.get('is_locked', False)]
    return {"action_items": [ActionItemResponse(**item) for item in action_items]}


@_firebase_router.get("/v1/action-items/{action_item_id}", response_model=ActionItemResponse, tags=['action-items'])
def get_action_item(request: Request, action_item_id: str):
    uid = request.state.uid
    """Get a specific action item by ID."""
    action_item = _get_valid_action_item(uid, action_item_id)

    if not action_item:
        raise HTTPException(status_code=404, detail="Action item not found")

    return ActionItemResponse(**action_item)


@_firebase_router.patch("/v1/action-items/{action_item_id}", response_model=ActionItemResponse, tags=['action-items'])
def update_action_item(request: Request, action_item_id: str, data: UpdateActionItemRequest):
    uid = request.state.uid
    """Update an action item."""
    # Check if action item exists
    existing_item = _get_valid_action_item(uid, action_item_id)
    if not existing_item:
        raise HTTPException(status_code=404, detail="Action item not found")

    # Prepare update data
    update_data = {}
    if data.description is not None:
        update_data['description'] = data.description
    if data.completed is not None:
        update_data['completed'] = data.completed
        if data.completed:
            update_data['completed_at'] = datetime.now(timezone.utc)
        else:
            update_data['completed_at'] = None
    # Check if due_at was explicitly provided (even if None) to allow clearing
    # In Pydantic v2, we check model_fields_set to see if field was explicitly set
    if 'due_at' in data.model_fields_set:
        # Field was explicitly provided (even if None) - update it
        update_data['due_at'] = data.due_at
    elif data.due_at is not None:
        # Fallback: only update if not None (for backwards compatibility)
        update_data['due_at'] = data.due_at
    if data.exported is not None:
        update_data['exported'] = data.exported
    if data.export_date is not None:
        update_data['export_date'] = data.export_date
    if data.export_platform is not None:
        update_data['export_platform'] = data.export_platform
    if data.apple_reminder_id is not None:
        update_data['apple_reminder_id'] = data.apple_reminder_id
    if data.sort_order is not None:
        update_data['sort_order'] = data.sort_order
    if data.indent_level is not None:
        update_data['indent_level'] = data.indent_level

    # Update the action item
    success = action_items_db.update_action_item(uid, action_item_id, update_data)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update action item")

    if data.description is not None:
        upsert_action_item_vector(uid, action_item_id, data.description)

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


@_firebase_router.patch(
    "/v1/action-items/{action_item_id}/completed", response_model=ActionItemResponse, tags=['action-items']
)
def toggle_action_item_completion(
    request: Request, action_item_id: str, completed: bool = Query(description="Whether to mark as completed or not")
):
    uid = request.state.uid
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

    # Notify sender if this was a shared task that just got completed
    if completed and existing_item.get('shared_from'):
        shared_from = existing_item['shared_from']
        sender_uid = shared_from.get('sender_uid')
        if sender_uid:
            recipient_name = get_user_display_name(uid)
            desc = existing_item.get('description', '')
            description = (desc[:57] + '...') if len(desc) > 60 else desc
            send_notification(sender_uid, "Task completed", f"{recipient_name} completed: {description}")

    return ActionItemResponse(**updated_item)


@_firebase_router.delete("/v1/action-items/{action_item_id}", status_code=204, tags=['action-items'])
def delete_action_item(request: Request, action_item_id: str):
    uid = request.state.uid
    """Delete an action item."""
    _get_valid_action_item(uid, action_item_id)
    success = action_items_db.delete_action_item(uid, action_item_id)
    if not success:
        raise HTTPException(status_code=404, detail="Action item not found")

    delete_action_item_vector(uid, action_item_id)

    # Send FCM deletion message to cancel scheduled notification
    send_action_item_deletion_message(user_id=uid, action_item_id=action_item_id)

    return {"status": "Ok"}


class BatchDeleteActionItemsRequest(BaseModel):
    ids: List[str] = Field(description="IDs of action items to delete", min_length=1, max_length=500)


@_firebase_router.post("/v1/action-items/batch-delete", tags=['action-items'])
def batch_delete_action_items(request: Request, data: BatchDeleteActionItemsRequest):
    """Delete multiple action items in one request.

    Firestore deletes go through chunked batched commits in the DB layer; the
    vector store delete and the FCM cancellation message both use their batch
    helpers — no per-id loop on this hot path.
    """
    uid = request.state.uid
    deleted_ids = action_items_db.delete_action_items_batch(uid, data.ids)

    if deleted_ids:
        delete_action_item_vectors_batch(uid, deleted_ids)
        send_action_items_batch_deletion_message(user_id=uid, action_item_ids=deleted_ids)

    return {"status": "Ok", "deleted_count": len(deleted_ids), "deleted_ids": deleted_ids}


# *****************************
# *** CONVERSATION-SPECIFIC ***
# *****************************


@_firebase_router.get("/v1/conversations/{conversation_id}/action-items", tags=['action-items'])
def get_conversation_action_items(request: Request, conversation_id: str):
    uid = request.state.uid
    """Get all action items for a specific conversation."""
    conversation = conversations_db.get_conversation(uid, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conversation.get('is_locked', False):
        raise HTTPException(status_code=402, detail="A paid plan is required to access this conversation.")
    action_items = action_items_db.get_action_items_by_conversation(uid, conversation_id)
    response_items = [ActionItemResponse(**item) for item in action_items]

    return {"action_items": response_items, "conversation_id": conversation_id}


@_firebase_router.delete("/v1/conversations/{conversation_id}/action-items", status_code=204, tags=['action-items'])
def delete_conversation_action_items(request: Request, conversation_id: str):
    uid = request.state.uid
    """Delete all action items for a specific conversation."""
    existing = action_items_db.get_action_items_by_conversation(uid, conversation_id)
    existing_ids = [item['id'] for item in existing]

    deleted_count = action_items_db.delete_action_items_for_conversation(uid, conversation_id)

    if existing_ids:
        delete_action_item_vectors_batch(uid, existing_ids)

    return {"status": "Ok", "deleted_count": deleted_count}


@_firebase_router.post("/v1/action-items/batch", tags=['action-items'])
def create_action_items_batch(request: Request, action_items: List[CreateActionItemRequest]):
    uid = request.state.uid
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

    upsert_action_item_vectors_batch(
        uid,
        [
            {'action_item_id': aid, 'description': data['description']}
            for aid, data in zip(created_ids, action_items_data)
        ],
    )

    return {"action_items": created_items, "created_count": len(created_items)}


# *****************************
# ******* TASK SHARING ********
# *****************************


class ShareTasksRequest(BaseModel):
    task_ids: List[str] = Field(description="IDs of action items to share", min_length=1, max_length=20)


class AcceptSharedTasksRequest(BaseModel):
    token: str = Field(description="Share token from the shared URL")


@_firebase_router.post("/v1/action-items/share", tags=['action-items'])
def share_action_items(request: Request, data: ShareTasksRequest):
    uid = request.state.uid
    """Create a shareable link for selected action items."""
    # Validate all task_ids belong to user and are not locked
    for task_id in data.task_ids:
        item = action_items_db.get_action_item(uid, task_id)
        if not item:
            raise HTTPException(status_code=404, detail=f"Action item {task_id} not found")
        if item.get('is_locked', False):
            raise HTTPException(status_code=402, detail="Cannot share locked action items.")

    # Get sender display name
    display_name = get_user_display_name(uid)

    # Generate token and store in Redis
    token = uuid.uuid4().hex
    result = redis_db.store_task_share(token, uid, display_name, data.task_ids)
    if result is None:
        raise HTTPException(status_code=500, detail="Failed to create share link")

    return {"url": f"https://h.omi.me/tasks/{token}", "token": token}


@_public_router.get("/v1/action-items/shared/{token}", tags=['action-items'])
def get_shared_action_items(token: str):
    """Public endpoint — get shared task preview (no auth required)."""
    share_data = redis_db.get_task_share(token)
    if not share_data:
        raise HTTPException(status_code=404, detail="Share link expired or not found")

    sender_uid = share_data['uid']
    task_ids = share_data['task_ids']

    # Fetch tasks — only expose description + due_at, skip locked items
    tasks = []
    for task_id in task_ids:
        item = action_items_db.get_action_item(sender_uid, task_id)
        if item and not item.get('is_locked', False):
            tasks.append(
                {
                    "description": item.get('description', ''),
                    "due_at": item.get('due_at'),
                }
            )

    return {
        "sender_name": share_data['display_name'],
        "tasks": tasks,
        "count": len(tasks),
    }


@_firebase_router.post("/v1/action-items/accept", tags=['action-items'])
def accept_shared_action_items(request: Request, data: AcceptSharedTasksRequest):
    uid = request.state.uid
    """Save shared tasks to the recipient's task list."""
    share_data = redis_db.get_task_share(data.token)
    if not share_data:
        raise HTTPException(status_code=404, detail="Share link expired or not found")

    # Prevent self-accept
    if share_data['uid'] == uid:
        raise HTTPException(status_code=400, detail="Cannot accept your own shared tasks")

    sender_uid = share_data['uid']
    task_ids = share_data['task_ids']

    # Pre-validate: check which items are eligible (exist and not locked)
    eligible_ids = []
    for task_id in task_ids:
        item = action_items_db.get_action_item(sender_uid, task_id)
        if item and not item.get('is_locked', False):
            eligible_ids.append(task_id)

    if not eligible_ids:
        raise HTTPException(status_code=402, detail="All shared tasks are locked. A paid plan is required.")

    # Atomically check and mark acceptance to prevent duplicates
    accepted = redis_db.try_accept_task_share(data.token, uid)
    if accepted is None:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    if not accepted:
        raise HTTPException(status_code=409, detail="You have already accepted this share")

    # Copy each eligible task to recipient's list
    created_ids = []
    for task_id in eligible_ids:
        original = action_items_db.get_action_item(sender_uid, task_id)
        if not original or original.get('is_locked', False):
            continue

        new_item = {
            'description': original.get('description', ''),
            'completed': False,
            'due_at': original.get('due_at'),
            'shared_from': {
                'token': data.token,
                'sender_uid': sender_uid,
                'sender_name': share_data['display_name'],
                'original_task_id': task_id,
            },
        }
        new_id = action_items_db.create_action_item(uid, new_item)
        created_ids.append(new_id)
        upsert_action_item_vector(uid, new_id, new_item['description'])

    # If race condition caused all items to become locked after pre-check, rollback token
    if not created_ids:
        redis_db.undo_accept_task_share(data.token, uid)
        raise HTTPException(status_code=402, detail="Shared tasks are no longer available.")

    return {"created": created_ids, "count": len(created_ids)}


router = APIRouter()
router.include_router(_public_router)
router.include_router(_firebase_router)

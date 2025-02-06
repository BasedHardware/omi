from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from models.action_item import ActionItem, ActionItemStatus
from ._client import db

def create_action_item(uid: str, description: str, memory_id: Optional[str] = None, due_date: Optional[datetime] = None) -> ActionItem:
    now = datetime.now(timezone.utc)
    action_item = ActionItem(
        id=str(uuid4()),
        memory_id=memory_id,
        uid=uid,
        description=description,
        created_at=now,
        updated_at=now,
        due_date=due_date
    )
    
    db.collection('users').document(uid).collection('action_items').document(action_item.id).set(action_item.dict())
    return action_item

def get_action_items(
    uid: str,
    status: Optional[ActionItemStatus] = None,
    memory_id: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0
) -> List[ActionItem]:
    query = db.collection('users').document(uid).collection('action_items')
    
    filters = []
    if status:
        filters.append(FieldFilter('status', '==', status))
    if memory_id:
        filters.append(FieldFilter('memory_id', '==', memory_id))
    if start_date:
        filters.append(FieldFilter('created_at', '>=', start_date))
    if end_date:
        filters.append(FieldFilter('created_at', '<=', end_date))
    
    if filters:
        for f in filters:
            query = query.where(filter=f)
    
    query = query.order_by('created_at', direction=firestore.Query.DESCENDING).limit(limit).offset(offset)
    
    return [ActionItem(**doc.to_dict()) for doc in query.stream()]

def update_action_item(uid: str, action_item_id: str, updates: dict) -> Optional[ActionItem]:
    doc_ref = db.collection('users').document(uid).collection('action_items').document(action_item_id)
    doc = doc_ref.get()
    
    if not doc.exists:
        return None
        
    updates['updated_at'] = datetime.now(timezone.utc)
    if updates.get('status') == ActionItemStatus.COMPLETED:
        updates['completed_at'] = datetime.now(timezone.utc)
    doc_ref.update(updates)
    
    updated_doc = doc_ref.get()
    return ActionItem(**updated_doc.to_dict())

def delete_action_item(uid: str, action_item_id: str) -> bool:
    doc_ref = db.collection('users').document(uid).collection('action_items').document(action_item_id)
    doc = doc_ref.get()
    
    if not doc.exists:
        return False
        
    updates = {
        'status': ActionItemStatus.DELETED,
        'deleted_at': datetime.now(timezone.utc),
        'updated_at': datetime.now(timezone.utc)
    }
    doc_ref.update(updates)
    return True
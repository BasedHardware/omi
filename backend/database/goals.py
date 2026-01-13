"""
Goal tracking database operations for user goals.
Stores user goals in Firestore under users/{uid}/goals collection.
"""
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from ._client import db

goals_collection = 'goals'
goal_history_collection = 'goal_history'
users_collection = 'users'


def get_user_goal(uid: str) -> Optional[Dict[str, Any]]:
    """Get the current active goal for a user (backward compatibility - returns first active goal)."""
    user_ref = db.collection(users_collection).document(uid)
    goals_ref = user_ref.collection(goals_collection)
    
    # Get the first active goal (for backward compatibility)
    query = goals_ref.where(filter=FieldFilter('is_active', '==', True)).limit(1)
    docs = list(query.stream())
    
    if docs:
        return docs[0].to_dict()
    return None


def get_user_goals(uid: str, limit: int = 3) -> List[Dict[str, Any]]:
    """Get all active goals for a user (up to limit)."""
    user_ref = db.collection(users_collection).document(uid)
    goals_ref = user_ref.collection(goals_collection)
    
    # Get all active goals
    query = goals_ref.where(filter=FieldFilter('is_active', '==', True)).limit(limit)
    docs = list(query.stream())
    
    # Sort in Python instead of Firestore (avoids composite index requirement)
    goals = [doc.to_dict() for doc in docs]
    goals.sort(key=lambda x: x.get('created_at') or '', reverse=False)
    
    return goals


def create_goal(uid: str, goal_data: Dict[str, Any], max_goals: int = 3) -> Dict[str, Any]:
    """Create a new goal for a user. Supports up to max_goals active goals."""
    user_ref = db.collection(users_collection).document(uid)
    goals_ref = user_ref.collection(goals_collection)
    
    # Check current active goal count
    active_goals = list(goals_ref.where(filter=FieldFilter('is_active', '==', True)).stream())
    
    # If at max, deactivate the oldest one
    if len(active_goals) >= max_goals:
        # Sort by created_at and deactivate oldest
        active_goals_data = [(doc, doc.to_dict().get('created_at')) for doc in active_goals]
        active_goals_data.sort(key=lambda x: x[1] if x[1] else datetime.min.replace(tzinfo=timezone.utc))
        oldest_doc = active_goals_data[0][0]
        oldest_doc.reference.update({'is_active': False, 'ended_at': datetime.now(timezone.utc)})
    
    # Create new goal
    goal_id = goal_data.get('id') or f"goal_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    goal_data['id'] = goal_id
    goal_data['is_active'] = True
    goal_data['created_at'] = datetime.now(timezone.utc)
    goal_data['updated_at'] = datetime.now(timezone.utc)
    
    goal_ref = goals_ref.document(goal_id)
    goal_ref.set(goal_data)
    
    return goal_data


def update_goal(uid: str, goal_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Update an existing goal."""
    user_ref = db.collection(users_collection).document(uid)
    goals_ref = user_ref.collection(goals_collection)
    goal_ref = goals_ref.document(goal_id)
    
    doc = goal_ref.get()
    if not doc.exists:
        return None
    
    updates['updated_at'] = datetime.now(timezone.utc)
    goal_ref.update(updates)
    
    return goal_ref.get().to_dict()


def update_goal_progress(uid: str, goal_id: str, current_value: float) -> Optional[Dict[str, Any]]:
    """Update the current progress value of a goal."""
    user_ref = db.collection(users_collection).document(uid)
    goals_ref = user_ref.collection(goals_collection)
    goal_ref = goals_ref.document(goal_id)
    
    doc = goal_ref.get()
    if not doc.exists:
        return None
    
    goal_ref.update({
        'current_value': current_value,
        'updated_at': datetime.now(timezone.utc)
    })
    
    # Also save to history
    save_goal_progress_history(uid, goal_id, current_value)
    
    return goal_ref.get().to_dict()


def save_goal_progress_history(uid: str, goal_id: str, value: float):
    """Save a progress data point to history."""
    user_ref = db.collection(users_collection).document(uid)
    goals_ref = user_ref.collection(goals_collection)
    goal_ref = goals_ref.document(goal_id)
    history_ref = goal_ref.collection(goal_history_collection)
    
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    history_doc = history_ref.document(today)
    
    history_doc.set({
        'date': today,
        'value': value,
        'recorded_at': datetime.now(timezone.utc)
    }, merge=True)


def get_goal_history(uid: str, goal_id: str, days: int = 30) -> List[Dict[str, Any]]:
    """Get progress history for a goal."""
    user_ref = db.collection(users_collection).document(uid)
    goals_ref = user_ref.collection(goals_collection)
    goal_ref = goals_ref.document(goal_id)
    history_ref = goal_ref.collection(goal_history_collection)
    
    query = history_ref.order_by('date', direction=firestore.Query.DESCENDING).limit(days)
    history = [doc.to_dict() for doc in query.stream()]
    
    return history


def get_all_goals(uid: str, include_inactive: bool = False) -> List[Dict[str, Any]]:
    """Get all goals for a user."""
    user_ref = db.collection(users_collection).document(uid)
    goals_ref = user_ref.collection(goals_collection)
    
    if include_inactive:
        query = goals_ref.order_by('created_at', direction=firestore.Query.DESCENDING)
    else:
        query = goals_ref.where(filter=FieldFilter('is_active', '==', True))
    
    return [doc.to_dict() for doc in query.stream()]


def delete_goal(uid: str, goal_id: str) -> bool:
    """Delete a goal."""
    user_ref = db.collection(users_collection).document(uid)
    goals_ref = user_ref.collection(goals_collection)
    goal_ref = goals_ref.document(goal_id)
    
    doc = goal_ref.get()
    if not doc.exists:
        return False
    
    goal_ref.delete()
    return True


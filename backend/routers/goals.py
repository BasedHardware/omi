"""
Goal tracking API endpoints.
Handles user goals with AI-powered suggestions and advice.
"""
import uuid
from datetime import datetime
from typing import Optional, List
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from database import goals as goals_db
from utils.other import endpoints as auth
from utils.llm.goals import suggest_goal as suggest_goal_llm, get_goal_advice as get_goal_advice_llm, extract_and_update_goal_progress

router = APIRouter()


class GoalType(str, Enum):
    """Types of goals supported."""
    boolean = "boolean"      # 0/1, true/false
    scale = "scale"          # e.g., 0-10
    numeric = "numeric"      # e.g., 0-1,000,000


class GoalCreate(BaseModel):
    """Model for creating a new goal."""
    title: str = Field(..., description="The goal title/description")
    goal_type: GoalType = Field(default=GoalType.scale, description="Type of goal metric")
    target_value: float = Field(..., description="Target value to achieve")
    current_value: float = Field(default=0, description="Current progress value")
    min_value: float = Field(default=0, description="Minimum value of the scale")
    max_value: float = Field(default=10, description="Maximum value of the scale")
    unit: Optional[str] = Field(default=None, description="Unit label (e.g., 'users', 'points')")


class GoalUpdate(BaseModel):
    """Model for updating a goal."""
    title: Optional[str] = None
    target_value: Optional[float] = None
    current_value: Optional[float] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    unit: Optional[str] = None


class GoalResponse(BaseModel):
    """Response model for a goal."""
    id: str
    title: str
    goal_type: str
    target_value: float
    current_value: float
    min_value: float
    max_value: float
    unit: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    advice: Optional[str] = None


class GoalSuggestionResponse(BaseModel):
    """Response model for AI-generated goal suggestion."""
    suggested_title: str
    suggested_type: str
    suggested_target: float
    reasoning: str


class AdviceResponse(BaseModel):
    """Response model for AI-generated advice."""
    advice: str


@router.get('/v1/goals', tags=['goals'])
async def get_current_goal(uid: str = Depends(auth.get_current_user_uid)) -> Optional[dict]:
    """Get the current active goal for the user (backward compatibility)."""
    goal = goals_db.get_user_goal(uid)
    if goal:
        # Convert datetime objects to strings for JSON serialization
        if 'created_at' in goal and hasattr(goal['created_at'], 'isoformat'):
            goal['created_at'] = goal['created_at'].isoformat()
        if 'updated_at' in goal and hasattr(goal['updated_at'], 'isoformat'):
            goal['updated_at'] = goal['updated_at'].isoformat()
    return goal


@router.get('/v1/goals/all', tags=['goals'])
async def get_all_goals(uid: str = Depends(auth.get_current_user_uid)) -> List[dict]:
    """Get all active goals for the user (up to 3)."""
    goals = goals_db.get_user_goals(uid, limit=3)
    
    # Convert datetime objects to strings for JSON serialization
    for goal in goals:
        if 'created_at' in goal and hasattr(goal['created_at'], 'isoformat'):
            goal['created_at'] = goal['created_at'].isoformat()
        if 'updated_at' in goal and hasattr(goal['updated_at'], 'isoformat'):
            goal['updated_at'] = goal['updated_at'].isoformat()
    
    return goals


@router.post('/v1/goals', tags=['goals'])
async def create_goal(
    goal: GoalCreate,
    uid: str = Depends(auth.get_current_user_uid)
) -> dict:
    """Create a new goal. This will deactivate any existing active goal."""
    goal_data = {
        'id': f"goal_{uuid.uuid4().hex[:12]}",
        'title': goal.title,
        'goal_type': goal.goal_type.value,
        'target_value': goal.target_value,
        'current_value': goal.current_value,
        'min_value': goal.min_value,
        'max_value': goal.max_value,
        'unit': goal.unit,
    }
    
    created_goal = goals_db.create_goal(uid, goal_data)
    
    # Convert datetime for JSON
    if 'created_at' in created_goal and hasattr(created_goal['created_at'], 'isoformat'):
        created_goal['created_at'] = created_goal['created_at'].isoformat()
    if 'updated_at' in created_goal and hasattr(created_goal['updated_at'], 'isoformat'):
        created_goal['updated_at'] = created_goal['updated_at'].isoformat()
    
    return created_goal


@router.patch('/v1/goals/{goal_id}', tags=['goals'])
async def update_goal(
    goal_id: str,
    updates: GoalUpdate,
    uid: str = Depends(auth.get_current_user_uid)
) -> dict:
    """Update an existing goal."""
    update_data = updates.model_dump(exclude_unset=True)
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No updates provided")
    
    updated_goal = goals_db.update_goal(uid, goal_id, update_data)
    
    if not updated_goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    
    # Convert datetime for JSON
    if 'created_at' in updated_goal and hasattr(updated_goal['created_at'], 'isoformat'):
        updated_goal['created_at'] = updated_goal['created_at'].isoformat()
    if 'updated_at' in updated_goal and hasattr(updated_goal['updated_at'], 'isoformat'):
        updated_goal['updated_at'] = updated_goal['updated_at'].isoformat()
    
    return updated_goal


@router.patch('/v1/goals/{goal_id}/progress', tags=['goals'])
async def update_goal_progress(
    goal_id: str,
    current_value: float = Query(..., description="New progress value"),
    uid: str = Depends(auth.get_current_user_uid)
) -> dict:
    """Update the progress value of a goal."""
    updated_goal = goals_db.update_goal_progress(uid, goal_id, current_value)
    
    if not updated_goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    
    # Convert datetime for JSON
    if 'created_at' in updated_goal and hasattr(updated_goal['created_at'], 'isoformat'):
        updated_goal['created_at'] = updated_goal['created_at'].isoformat()
    if 'updated_at' in updated_goal and hasattr(updated_goal['updated_at'], 'isoformat'):
        updated_goal['updated_at'] = updated_goal['updated_at'].isoformat()
    
    return updated_goal


@router.get('/v1/goals/{goal_id}/history', tags=['goals'])
async def get_goal_history(
    goal_id: str,
    days: int = Query(default=30, le=365),
    uid: str = Depends(auth.get_current_user_uid)
) -> List[dict]:
    """Get progress history for a goal."""
    history = goals_db.get_goal_history(uid, goal_id, days)
    
    # Convert datetime objects
    for entry in history:
        if 'recorded_at' in entry and hasattr(entry['recorded_at'], 'isoformat'):
            entry['recorded_at'] = entry['recorded_at'].isoformat()
    
    return history


@router.delete('/v1/goals/{goal_id}', tags=['goals'])
async def delete_goal(
    goal_id: str,
    uid: str = Depends(auth.get_current_user_uid)
) -> dict:
    """Delete a goal."""
    success = goals_db.delete_goal(uid, goal_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Goal not found")
    
    return {"success": True, "deleted_id": goal_id}


@router.get('/v1/goals/suggest', tags=['goals'])
async def suggest_goal(uid: str = Depends(auth.get_current_user_uid)) -> dict:
    """Generate an AI-suggested goal based on user's memories and conversations."""
    return suggest_goal_llm(uid)


@router.get('/v1/goals/{goal_id}/advice', tags=['goals'])
async def get_goal_advice(
    goal_id: str,
    uid: str = Depends(auth.get_current_user_uid)
) -> dict:
    """Get AI-generated actionable advice for achieving a goal."""
    try:
        advice = get_goal_advice_llm(uid, goal_id)
        return {'advice': advice}
    except ValueError:
        raise HTTPException(status_code=404, detail="Goal not found")


@router.get('/v1/goals/advice', tags=['goals'])
async def get_current_goal_advice(uid: str = Depends(auth.get_current_user_uid)) -> dict:
    """Get AI-generated advice for the current active goal."""
    goal = goals_db.get_user_goal(uid)
    if not goal:
        return {'advice': 'Set a goal to get personalized advice!'}
    
    return await get_goal_advice(goal['id'], uid)


class ProgressExtractRequest(BaseModel):
    """Request to extract progress from text."""
    text: str


@router.post('/v1/goals/extract-progress', tags=['goals'])
async def extract_and_update_progress(
    request: ProgressExtractRequest,
    uid: str = Depends(auth.get_current_user_uid)
) -> dict:
    """
    Extract goal progress from conversation/chat text and update if found.
    Uses LLM to understand context and extract numeric progress.
    """
    result = extract_and_update_goal_progress(uid, request.text)
    if result is None:
        return {'updated': False, 'reason': 'No active goal'}
    
    if result.get('status') == 'updated':
        return {
            'updated': True,
            'previous_value': result.get('old_value'),
            'new_value': result.get('new_value'),
            'reasoning': result.get('reasoning', '')
        }
    
    return {'updated': False, 'reason': result.get('message', 'No progress found in text')}


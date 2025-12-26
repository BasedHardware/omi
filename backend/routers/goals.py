"""
Goal tracking API endpoints.
Handles user goals with AI-powered suggestions and advice.
"""
import os
import uuid
from datetime import datetime, timezone
from typing import Optional, List
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from database import goals as goals_db
from database import memories as memories_db
from utils.other import endpoints as auth
from utils.llm.clients import llm_mini

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
    """Get the current active goal for the user."""
    goal = goals_db.get_user_goal(uid)
    if goal:
        # Convert datetime objects to strings for JSON serialization
        if 'created_at' in goal and hasattr(goal['created_at'], 'isoformat'):
            goal['created_at'] = goal['created_at'].isoformat()
        if 'updated_at' in goal and hasattr(goal['updated_at'], 'isoformat'):
            goal['updated_at'] = goal['updated_at'].isoformat()
    return goal


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
    try:
        # Get user's memories for context
        memories = memories_db.get_memories(uid, limit=100, offset=0)
        
        if not memories:
            # Default suggestion when no memories
            return {
                'suggested_title': 'Learn something new every day',
                'suggested_type': 'scale',
                'suggested_target': 10,
                'suggested_min': 0,
                'suggested_max': 10,
                'reasoning': 'Start tracking your daily learning progress!'
            }
        
        # Prepare memory context for AI
        memory_texts = [m.get('content', '') for m in memories[:50] if m.get('content')]
        memory_context = '\n'.join(memory_texts[:20])  # Limit context size
        
        prompt = f"""Based on the user's memories and interests, suggest ONE meaningful personal goal they could track.

User's recent memories/learnings:
{memory_context}

Generate a goal suggestion in this exact JSON format:
{{
    "suggested_title": "Brief, actionable goal title (e.g., 'Exercise 5 times a week', 'Read 20 books this year', 'Save $10,000')",
    "suggested_type": "scale" or "numeric" or "boolean",
    "suggested_target": <number>,
    "suggested_min": <minimum value>,
    "suggested_max": <maximum value or target>,
    "reasoning": "One sentence explaining why this goal fits the user"
}}

Choose a goal type:
- "boolean" for yes/no goals (0 or 1)
- "scale" for rating goals (e.g., 0-10 satisfaction)
- "numeric" for countable goals (e.g., books read, money saved, users acquired)

Make the goal specific, measurable, and relevant to their interests."""

        response = llm_mini.invoke(prompt).content
        
        # Parse JSON from response
        import json
        import re
        
        # Find JSON in response
        json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
        if json_match:
            suggestion = json.loads(json_match.group())
            return suggestion
        
        # Fallback if parsing fails
        return {
            'suggested_title': 'Track your daily progress',
            'suggested_type': 'scale',
            'suggested_target': 10,
            'suggested_min': 0,
            'suggested_max': 10,
            'reasoning': 'A simple goal to get you started!'
        }
        
    except Exception as e:
        print(f"Error generating goal suggestion: {e}")
        return {
            'suggested_title': 'Make progress every day',
            'suggested_type': 'scale', 
            'suggested_target': 10,
            'suggested_min': 0,
            'suggested_max': 10,
            'reasoning': 'Start with a simple daily progress goal!'
        }


@router.get('/v1/goals/{goal_id}/advice', tags=['goals'])
async def get_goal_advice(
    goal_id: str,
    uid: str = Depends(auth.get_current_user_uid)
) -> dict:
    """Get AI-generated actionable advice for achieving a goal."""
    try:
        # Get the goal
        goal = goals_db.get_user_goal(uid)
        if not goal or goal.get('id') != goal_id:
            raise HTTPException(status_code=404, detail="Goal not found")
        
        # Get user context
        memories = memories_db.get_memories(uid, limit=50, offset=0)
        memory_context = '\n'.join([m.get('content', '')[:200] for m in memories[:10] if m.get('content')])
        
        # Get progress history
        history = goals_db.get_goal_history(uid, goal_id, days=7)
        
        progress_pct = 0
        if goal.get('max_value', 0) > goal.get('min_value', 0):
            range_val = goal['max_value'] - goal['min_value']
            progress_pct = ((goal.get('current_value', 0) - goal.get('min_value', 0)) / range_val) * 100
        
        prompt = f"""Give ONE short, actionable piece of advice (max 15 words) for this goal:

Goal: {goal.get('title', 'Unknown')}
Current progress: {goal.get('current_value', 0)} / {goal.get('target_value', 10)} ({progress_pct:.0f}%)
Goal type: {goal.get('goal_type', 'scale')}

Recent user context:
{memory_context[:500]}

Recent progress history (last 7 days): {len(history)} entries

Provide a brief, specific, actionable tip. Be encouraging but practical. No fluff.
Just return the advice text, nothing else."""

        advice = llm_mini.invoke(prompt).content
        
        # Clean up the response
        advice = advice.strip().strip('"').strip("'")
        if len(advice) > 100:
            advice = advice[:97] + "..."
        
        return {'advice': advice}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error generating advice: {e}")
        return {'advice': 'Keep pushing forward, one step at a time!'}


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
    goal = goals_db.get_user_goal(uid)
    if not goal:
        return {'updated': False, 'reason': 'No active goal'}
    
    try:
        prompt = f"""Analyze this text and determine if it mentions progress toward the user's goal.

Goal: "{goal.get('title', '')}"
Current progress: {goal.get('current_value', 0)} / {goal.get('target_value', 10)}

Text to analyze:
"{request.text}"

If the text mentions a new progress value for this goal, extract it.
Examples:
- "We hit 500 in revenue" -> 500
- "Now at 1000 users" -> 1000  
- "Completed 3 more tasks" -> current + 3
- "We're at 50%" -> calculate 50% of target

Respond in JSON format:
{{"found": true/false, "new_value": number or null, "reasoning": "brief explanation"}}

Only return true if you're confident the text relates to this specific goal."""

        response = llm_mini.invoke(prompt).content
        
        import json
        import re
        
        # Parse response
        json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            
            if result.get('found') and result.get('new_value') is not None:
                new_value = float(result['new_value'])
                
                # Update the goal
                updated = goals_db.update_goal_progress(uid, goal['id'], new_value)
                
                if updated:
                    return {
                        'updated': True,
                        'previous_value': goal.get('current_value', 0),
                        'new_value': new_value,
                        'reasoning': result.get('reasoning', '')
                    }
        
        return {'updated': False, 'reason': 'No progress found in text'}
        
    except Exception as e:
        print(f"Error extracting progress: {e}")
        return {'updated': False, 'reason': str(e)}


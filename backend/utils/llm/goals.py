"""
LLM utilities for goal tracking.
Handles AI-powered goal suggestions, advice generation, and progress extraction.
"""
import json
import re
from typing import Optional, Dict

import database.goals as goals_db
import database.memories as memories_db
from utils.llm.clients import llm_mini


def suggest_goal(uid: str) -> Dict:
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
        
        # Find JSON in response
        json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
        if json_match:
            suggestion = json.loads(json_match.group())
            # Ensure min/max are present, default if not
            suggestion['suggested_min'] = suggestion.get('suggested_min', 0)
            suggestion['suggested_max'] = suggestion.get('suggested_max', suggestion.get('suggested_target', 10))
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


def get_goal_advice(uid: str, goal_id: str) -> str:
    """Get AI-generated actionable advice for achieving a goal."""
    try:
        # Get the goal
        goal = goals_db.get_user_goal(uid)
        if not goal or goal.get('id') != goal_id:
            raise ValueError("Goal not found")
        
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
        
        return advice
        
    except Exception as e:
        print(f"Error generating advice: {e}")
        return 'Keep pushing forward, one step at a time!'


def extract_and_update_goal_progress(uid: str, text: str) -> Optional[Dict]:
    """
    Extract goal progress from text and update if found.
    Returns dict with update info if successful, None otherwise.
    """
    try:
        goal = goals_db.get_user_goal(uid)
        if not goal or not text or len(text) < 5:
            return None
        
        goal_title = goal.get('title', '')
        current_value = goal.get('current_value', 0)
        target_value = goal.get('target_value', 10)
        goal_type = goal.get('goal_type', 'numeric')
        
        prompt = f"""Analyze this message to see if it mentions progress toward this goal:

Goal: "{goal_title}"
Goal Type: {goal_type}
Current Progress: {current_value} / {target_value}

User Message: "{text[:500]}"

If the message mentions a NEW progress value for this goal, extract it. 
Handle formats like:
- "1k users" → 1000
- "500k" → 500000
- "1.5 million" → 1500000
- "1000" → 1000
- Percentages relative to goal

Return JSON only: {{"found": true/false, "value": number_or_null, "reasoning": "brief explanation"}}
Only return found=true if you're confident this is about the SPECIFIC goal mentioned above."""

        response = llm_mini.invoke(prompt).content
        
        # Extract JSON from response
        match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response, re.DOTALL)
        if match:
            result = json.loads(match.group())
            if result.get('found') and result.get('value') is not None:
                new_value = float(result['value'])
                old_value = current_value
                if new_value != old_value:
                    goals_db.update_goal_progress(uid, goal['id'], new_value)
                    print(f"[GOAL-AUTO] Updated '{goal_title}': {old_value} -> {new_value} (reasoning: {result.get('reasoning', 'N/A')})")
                    return {
                        "status": "updated",
                        "old_value": old_value,
                        "new_value": new_value,
                        "reasoning": result.get('reasoning')
                    }
        return {"status": "no_update", "message": "No relevant progress mentioned or extracted."}
    except Exception as e:
        print(f"Error in extract_and_update_goal_progress: {e}")
        return {"status": "error", "message": str(e)}


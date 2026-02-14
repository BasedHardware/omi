"""
LLM utilities for goal tracking.
Handles AI-powered goal suggestions, advice generation, and progress extraction.
"""

import json
import re
import traceback
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List

import database.goals as goals_db
import database.memories as memories_db
import database.conversations as conversations_db
import database.chat as chat_db
from database.vector_db import query_vectors as vector_search
from utils.llm.clients import llm_mini, llm_medium
from utils.llm.usage_tracker import track_usage, Features


def _get_goal_context(uid: str, goal_title: str) -> Dict[str, str]:
    """
    Get rich context for goal advice using hybrid retrieval:
    1. Vector search for goal-relevant conversations
    2. Recent conversations (last 7 days)
    3. Recent chat messages
    4. User memories/facts

    Returns dict with conversation_context, chat_context, memory_context
    """
    conv_summaries = []
    seen_ids = set()

    # 1. Vector search: Find conversations semantically related to the goal
    try:
        relevant_ids = vector_search(query=goal_title, uid=uid, k=10)
        if relevant_ids:
            relevant_convs = conversations_db.get_conversations_by_id(uid, relevant_ids)
            for conv in relevant_convs[:5]:  # Top 5 most relevant
                conv_id = conv.get('id')
                if conv_id and conv_id not in seen_ids:
                    seen_ids.add(conv_id)
                    overview = conv.get('structured', {}).get('overview', '')
                    if overview:
                        conv_summaries.append(f"[Relevant] {overview[:300]}")
    except Exception as e:
        print(f"[GOAL-ADVICE] Vector search error: {e}")

    # 2. Recent conversations (last 7 days) - for current context
    try:
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        recent_convs = conversations_db.get_conversations(
            uid=uid, limit=20, statuses=['completed'], include_discarded=False
        )
        for conv in recent_convs:
            conv_id = conv.get('id')
            created = conv.get('created_at')
            if conv_id and conv_id not in seen_ids:
                # Check if within last 7 days
                if created and isinstance(created, datetime) and created > week_ago:
                    seen_ids.add(conv_id)
                    overview = conv.get('structured', {}).get('overview', '')
                    if overview:
                        conv_summaries.append(f"[Recent] {overview[:250]}")
                        if len(conv_summaries) >= 10:
                            break
    except Exception as e:
        print(f"[GOAL-ADVICE] Recent conversations error: {e}")

    # 3. Recent chat messages
    chat_context = ""
    try:
        recent_messages = chat_db.get_messages(uid, limit=15, app_id=None)
        if recent_messages:
            chat_lines = []
            for msg in reversed(recent_messages):  # Chronological order
                sender = "User" if msg.get('sender') == 'human' else "Omi"
                text = msg.get('text', '')[:200]
                if text:
                    chat_lines.append(f"{sender}: {text}")
            chat_context = '\n'.join(chat_lines[-10:])  # Last 10 messages
    except Exception as e:
        print(f"[GOAL-ADVICE] Chat messages error: {e}")

    # 4. User memories/facts
    memory_context = ""
    try:
        memories = memories_db.get_memories(uid, limit=30, offset=0)
        memory_texts = [m.get('content', '')[:150] for m in memories[:15] if m.get('content')]
        memory_context = '\n'.join(memory_texts)
    except Exception as e:
        print(f"[GOAL-ADVICE] Memories error: {e}")

    return {
        'conversation_context': '\n'.join(conv_summaries),
        'chat_context': chat_context,
        'memory_context': memory_context,
    }


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
                'reasoning': 'Start tracking your daily learning progress!',
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

        with track_usage(uid, Features.GOALS):
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
            'reasoning': 'A simple goal to get you started!',
        }

    except Exception as e:
        print(f"Error generating goal suggestion: {e}")
        return {
            'suggested_title': 'Make progress every day',
            'suggested_type': 'scale',
            'suggested_target': 10,
            'suggested_min': 0,
            'suggested_max': 10,
            'reasoning': 'Start with a simple daily progress goal!',
        }


def get_goal_advice(uid: str, goal_id: str) -> str:
    """
    Get AI-generated actionable advice for achieving a goal.
    Uses hybrid retrieval: vector search + recent context + chat history.
    """
    try:
        # Get the goal
        goals = goals_db.get_user_goals(uid)
        goal = next((g for g in goals if g.get('id') == goal_id), None)
        if not goal:
            raise ValueError("Goal not found")

        goal_title = goal.get('title', 'Unknown')
        current_value = goal.get('current_value', 0)
        target_value = goal.get('target_value', 10)

        # Calculate progress
        progress_pct = 0
        if target_value > 0:
            progress_pct = (current_value / target_value) * 100

        # Get rich context using hybrid retrieval
        context = _get_goal_context(uid, goal_title)

        # Build the prompt with full context
        prompt = f"""You are a strategic advisor. Based on the user's goal and their context, give ONE specific actionable step they should take THIS WEEK.

GOAL: "{goal_title}"
PROGRESS: {current_value:,.0f} / {target_value:,.0f} ({progress_pct:.1f}%)

RECENT CONVERSATIONS (what they've been discussing/working on):
{context['conversation_context'][:1500] if context['conversation_context'] else 'No recent conversations'}

RECENT CHAT (what they're currently thinking about):
{context['chat_context'][:800] if context['chat_context'] else 'No recent chat'}

USER FACTS:
{context['memory_context'][:600] if context['memory_context'] else 'No facts available'}

Give ONE specific action in 1-2 sentences. Be concise but complete. No generic advice."""

        print(
            f"[GOAL-ADVICE] Generating advice for '{goal_title}' with {len(context['conversation_context'])} chars conv, {len(context['chat_context'])} chars chat"
        )

        # Use the better model for high-quality advice
        with track_usage(uid, Features.GOALS):
            advice = llm_medium.invoke(prompt).content

        # Clean up quotes but keep full text
        advice = advice.strip().strip('"').strip("'")

        return advice

    except Exception as e:
        print(f"[GOAL-ADVICE] Error: {e}")
        traceback.print_exc()
        return 'Focus on the next small step toward your goal.'


def extract_and_update_goal_progress(uid: str, text: str) -> Optional[Dict]:
    """
    Extract goal progress from text and update if found.
    Checks all active goals in a SINGLE LLM call. Returns dict with update info if successful, None otherwise.
    """
    try:
        goals = goals_db.get_user_goals(uid)
        if not goals or not text or len(text) < 5:
            return None

        # Build a single prompt that evaluates all goals at once
        goals_list = []
        goals_by_id = {}
        for goal in goals:
            goal_id = goal.get('id', '')
            if not goal_id:
                continue
            goal_title = goal.get('title', '')
            current_value = goal.get('current_value', 0)
            target_value = goal.get('target_value', 10)
            goal_type = goal.get('goal_type', 'numeric')
            goals_list.append(
                f'- id: "{goal_id}", title: "{goal_title}", type: {goal_type}, progress: {current_value}/{target_value}'
            )
            goals_by_id[goal_id] = goal

        if not goals_list:
            return None

        goals_text = '\n'.join(goals_list)

        prompt = f"""Analyze this message to see if it mentions progress toward ANY of these goals:

Goals:
{goals_text}

User Message: "{text[:500]}"

For each goal where the message mentions a NEW absolute progress value, extract it.
Convert shorthand to numbers: "1k" → 1000, "500k" → 500000, "1.5 million" → 1500000.
The "value" MUST be the absolute current total, NOT a relative change or percentage.

Return ONLY a JSON array, no other text. Include ONLY goals where progress was found.
If no goals match, return an empty array: []

Example output: [{{"goal_id": "goal_abc123", "found": true, "value": 2500, "reasoning": "user said total is $2,500"}}]

Only include a goal if you're confident the message is about that SPECIFIC goal."""

        with track_usage(uid, Features.GOALS):
            response = llm_mini.invoke(prompt).content

        # Parse JSON array from response using non-greedy extraction
        results = _parse_json_array(response)
        if results is None:
            return {"status": "no_update", "message": "No relevant progress mentioned or extracted."}

        updates = []
        seen_goal_ids = set()
        for result in results:
            try:
                if not isinstance(result, dict) or not result.get('found') or result.get('value') is None:
                    continue
                goal_id = result.get('goal_id', '')
                if not goal_id or goal_id in seen_goal_ids:
                    continue
                seen_goal_ids.add(goal_id)
                goal = goals_by_id.get(goal_id)
                if not goal:
                    continue
                new_value = float(result['value'])
                # Validate: reject NaN, inf, and negative values
                if new_value != new_value or new_value == float('inf') or new_value == float('-inf') or new_value < 0:
                    continue
                old_value = goal.get('current_value', 0)
                if new_value != old_value:
                    goals_db.update_goal_progress(uid, goal_id, new_value)
                    goal_title = goal.get('title', '')
                    print(
                        f"[GOAL-AUTO] Updated '{goal_title}': {old_value} -> {new_value} (reasoning: {result.get('reasoning', 'N/A')})"
                    )
                    updates.append(
                        {
                            "goal_id": goal_id,
                            "goal_title": goal_title,
                            "old_value": old_value,
                            "new_value": new_value,
                            "reasoning": result.get('reasoning'),
                        }
                    )
            except (ValueError, TypeError, KeyError):
                continue

        if updates:
            return {"status": "updated", "updates": updates}
        return {"status": "no_update", "message": "No relevant progress mentioned or extracted."}
    except Exception as e:
        print(f"Error in extract_and_update_goal_progress: {e}")
        return {"status": "error", "message": str(e)}


def _parse_json_array(text: str) -> Optional[List]:
    """Extract and parse the first JSON array from LLM response text."""
    # Find the first '[' and try to parse from there
    start = text.find('[')
    if start == -1:
        return None
    try:
        decoder = json.JSONDecoder()
        result, _ = decoder.raw_decode(text, start)
        if isinstance(result, list):
            return result
        return [result]
    except (json.JSONDecodeError, ValueError):
        return None

"""
LLM utilities for goal tracking.
Handles AI-powered goal suggestions, advice generation, and progress extraction.
"""

from utils.generated_compute import generated_compute_allowed

import json
import math
import re
import traceback
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Set, cast

import database.goals as goals_db
import database.conversations as conversations_db
import database.chat as chat_db
from database._client import db as firestore_db
from database.vector_db import query_vectors as vector_search
from models.goal import sanitize_suggestion_dict
from utils.llm.clients import get_llm
from utils.llm.usage_tracker import track_usage, Features
from utils.memory.memory_service import MemoryService
import logging

logger = logging.getLogger(__name__)


def _get_goal_context(uid: str, goal_title: str) -> Dict[str, str]:
    """
    Get rich context for goal advice using hybrid retrieval:
    1. Vector search for goal-relevant conversations
    2. Recent conversations (last 7 days)
    3. Recent chat messages
    4. User memories/facts

    Returns dict with conversation_context, chat_context, memory_context
    """
    conv_summaries: List[str] = []
    seen_ids: Set[str] = set()

    # 1. Vector search: Find conversations semantically related to the goal
    try:
        relevant_ids = vector_search(query=goal_title, uid=uid, k=10)
        if relevant_ids:
            relevant_convs = conversations_db.get_conversations_by_id(uid, relevant_ids)
            for conv in [c for c in relevant_convs if not c.get('is_locked')][:5]:
                conv_id = conv.get('id')
                if conv_id and conv_id not in seen_ids:
                    seen_ids.add(conv_id)
                    overview = cast(Dict[str, Any], conv.get('structured', {})).get('overview', '')
                    if overview:
                        conv_summaries.append(f"[Relevant] {overview[:300]}")
    except Exception as e:
        logger.error(f"[GOAL-ADVICE] Vector search error: {e}")

    # 2. Recent conversations (last 7 days) - for current context
    try:
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        recent_convs = conversations_db.get_conversations(
            uid=uid, limit=20, statuses=['completed'], include_discarded=False
        )
        for conv in [c for c in recent_convs if not c.get('is_locked')]:
            conv_id = conv.get('id')
            created = conv.get('created_at')
            if conv_id and conv_id not in seen_ids:
                # Check if within last 7 days
                if created and isinstance(created, datetime) and created > week_ago:
                    seen_ids.add(conv_id)
                    overview = cast(Dict[str, Any], conv.get('structured', {})).get('overview', '')
                    if overview:
                        conv_summaries.append(f"[Recent] {overview[:250]}")
                        if len(conv_summaries) >= 10:
                            break
    except Exception as e:
        logger.error(f"[GOAL-ADVICE] Recent conversations error: {e}")

    # 3. Recent chat messages
    chat_context = ""
    try:
        recent_messages = chat_db.get_messages(uid, limit=15, app_id=None)
        if recent_messages:
            chat_lines: List[str] = []
            for msg in reversed(recent_messages):  # Chronological order
                sender = "User" if msg.get('sender') == 'human' else "Omi"
                # get('text', '') only defaults an ABSENT key; a stored message with text=None would
                # make None[:200] raise, and the broad except below then drops the entire chat block
                # from the goal-advice prompt. The memory block below already guards with if m.get(...).
                text = (msg.get('text') or '')[:200]
                if text:
                    chat_lines.append(f"{sender}: {text}")
            chat_context = '\n'.join(chat_lines[-10:])  # Last 10 messages
    except Exception as e:
        logger.error(f"[GOAL-ADVICE] Chat messages error: {e}")

    # 4. User memories/facts
    memory_context = ""
    try:
        memories = [m.dict() for m in MemoryService(db_client=firestore_db).read(uid, limit=30, offset=0)]
        memory_texts = [
            m.get('content', '')[:150] for m in memories[:15] if m.get('content') and not m.get('is_locked')
        ]
        memory_context = '\n'.join(memory_texts)
    except Exception as e:
        logger.error(f"[GOAL-ADVICE] Memories error: {e}")

    return {
        'conversation_context': '\n'.join(conv_summaries),
        'chat_context': chat_context,
        'memory_context': memory_context,
    }


def _safe_float(val: Any, default: float) -> float:
    if val is None or isinstance(val, bool) or val == "":
        return default
    try:
        f = float(val)
        return f if math.isfinite(f) else default
    except (TypeError, ValueError):
        return default


def _safe_optional_float(val: Any) -> Optional[float]:
    if val is None or isinstance(val, bool) or val == "":
        return None
    try:
        f = float(val)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _safe_float_field(value: Any, default: float) -> float:
    """Coerce an individual suggestion numeric field to float, falling back per-field."""
    if value is None or isinstance(value, bool):
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


safe_float = _safe_float
safe_optional_float = _safe_optional_float

sanitize_goal_suggestion = sanitize_suggestion_dict


def suggest_goal(uid: str) -> Dict[str, Any]:
    """Generate an AI-suggested goal based on user's memories and conversations."""
    try:
        # Get user's memories for context
        memories = [m.dict() for m in MemoryService(db_client=firestore_db).read(uid, limit=100, offset=0)]

        # Prepare memory context for AI — exclude locked memories
        memory_texts = [
            cast(str, m.get('content', '')) for m in memories[:50] if m.get('content') and not m.get('is_locked')
        ]

        if not memories or not memory_texts:
            # Default suggestion when no unlocked memories are available
            return sanitize_goal_suggestion({
                'suggested_title': 'Learn something new every day',
                'suggested_type': 'scale',
                'suggested_target': 10.0,
                'suggested_min': 0.0,
                'suggested_max': 10.0,
                'reasoning': 'Start tracking your daily learning progress!',
            })

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
            response = cast(str, cast(Any, get_llm('goals').invoke(prompt)).content)

        # Find JSON in response
        json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
        if json_match:
            try:
                suggestion = json.loads(json_match.group())
                suggestion['suggested_target'] = _safe_float_field(suggestion.get('suggested_target'), 10.0)
                suggestion['suggested_min'] = _safe_float_field(suggestion.get('suggested_min'), 0.0)
                suggestion['suggested_max'] = _safe_float_field(
                    suggestion.get('suggested_max'), suggestion['suggested_target']
                )
                if not suggestion.get('suggested_title'):
                    suggestion['suggested_title'] = 'Track your daily progress'
                if suggestion.get('suggested_type') not in ('boolean', 'scale', 'numeric'):
                    suggestion['suggested_type'] = 'scale'
                if not suggestion.get('reasoning'):
                    suggestion['reasoning'] = 'A simple goal to get you started!'
                return sanitize_goal_suggestion(suggestion)
            except Exception:
                pass

        # Fallback if parsing fails
        return sanitize_goal_suggestion({
            'suggested_title': 'Track your daily progress',
            'suggested_type': 'scale',
            'suggested_target': 10.0,
            'suggested_min': 0.0,
            'suggested_max': 10.0,
            'reasoning': 'A simple goal to get you started!',
        })

    except Exception as e:
        logger.error(f"Error generating goal suggestion: {e}")
        return sanitize_goal_suggestion({
            'suggested_title': 'Make progress every day',
            'suggested_type': 'scale',
            'suggested_target': 10.0,
            'suggested_min': 0.0,
            'suggested_max': 10.0,
            'reasoning': 'Start tracking your daily progress!',
        })


def get_goal_advice(uid: str, goal_id: str) -> str:
    """
    Get AI-generated actionable advice for achieving a goal.
    Uses hybrid retrieval: vector search + recent context + chat history.
    """
    # Get the goal - raise ValueError for missing/inactive goals to let the router return 404
    goal = goals_db.get_goal_by_id(uid, goal_id)
    if not goal or not goal.get('is_active'):
        raise ValueError("Goal not found")

    try:
        goal_title = str(goal.get('title') or 'Unknown')

        # Safely parse numeric current and target values if present
        current_val = _safe_optional_float(goal.get('current_value'))
        target_val = _safe_optional_float(goal.get('target_value'))

        # Build progress description safely supporting numeric and qualitative goals
        if current_val is not None and target_val is not None and target_val > 0:
            progress_pct = (current_val / target_val) * 100
            progress_line = f"PROGRESS: {current_val:,.0f} / {target_val:,.0f} ({progress_pct:.1f}%)"
        elif current_val is not None and target_val is not None:
            progress_line = f"PROGRESS: {current_val:,.0f} / {target_val:,.0f}"
        elif current_val is not None:
            progress_line = f"PROGRESS: {current_val:,.0f} (no numeric target set)"
        elif target_val is not None:
            progress_line = f"PROGRESS: Target {target_val:,.0f} (current progress not tracked numerically)"
        else:
            progress_line = "PROGRESS: Qualitative goal (no numeric metric set)"

        # Get rich context using hybrid retrieval
        context = _get_goal_context(uid, goal_title)

        # Build the prompt with full context
        prompt = f"""You are a strategic advisor. Based on the user's goal and their context, give ONE specific actionable step they should take THIS WEEK.

GOAL: "{goal_title}"
{progress_line}

RECENT CONVERSATIONS (what they've been discussing/working on):
{context['conversation_context'][:1500] if context['conversation_context'] else 'No recent conversations'}

RECENT CHAT (what they're currently thinking about):
{context['chat_context'][:800] if context['chat_context'] else 'No recent chat'}

USER FACTS:
{context['memory_context'][:600] if context['memory_context'] else 'No facts available'}

Give ONE specific action in 1-2 sentences. Be concise but complete. No generic advice."""

        logger.info(
            f"[GOAL-ADVICE] Generating advice for '{goal_title}' with {len(context['conversation_context'])} chars conv, {len(context['chat_context'])} chars chat"
        )

        # Use the better model for high-quality advice
        with track_usage(uid, Features.GOALS):
            advice = cast(str, cast(Any, get_llm('goals_advice').invoke(prompt)).content)

        # Clean up quotes but keep full text
        advice = advice.strip().strip('"').strip("'")

        return advice

    except Exception as e:
        logger.error(f"[GOAL-ADVICE] Error: {e}")
        traceback.print_exc()
        return 'Focus on the next small step toward your goal.'


def extract_and_update_goal_progress(
    uid: str,
    text: str,
    *,
    idempotency_key_prefix: Optional[str] = None,
    account_generation: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """
    Extract goal progress from text and update if found.
    Checks all active goals in a SINGLE LLM call. Returns dict with update info if successful, None otherwise.
    """
    if not generated_compute_allowed(uid, 'goals'):
        return None
    try:
        goals = goals_db.get_user_goals(uid, limit=100)
        if not goals or not text or len(text) < 5:
            return None

        # Build a single prompt that evaluates all goals at once
        goals_list: List[str] = []
        goals_by_id: Dict[str, Any] = {}
        for goal in goals:
            goal_id = goal.get('id', '')
            if not goal_id:
                continue
            # Purely qualitative goals (no target and no metric) cannot receive numeric progress.
            # Skip them from the prompt to avoid burning LLM tokens and prevent LLM hallucination
            # from corrupting qualitative goals into a half-numeric state.
            if goal.get('target_value') is None and goal.get('metric') is None and goal.get('current_value') is None:
                continue

            goal_title = goal.get('title', '')
            current_value = goal.get('current_value')
            target_value = goal.get('target_value')
            goal_type = goal.get('goal_type', 'numeric')
            curr_str = f"{current_value}" if current_value is not None else "not set"
            target_str = f"{target_value}" if target_value is not None else "not set"
            goals_list.append(
                f'- id: "{goal_id}", title: "{goal_title}", type: {goal_type}, progress: {curr_str}/{target_str}'
            )
            goals_by_id[cast(str, goal_id)] = goal

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
            response = cast(str, cast(Any, get_llm('goals').invoke(prompt)).content)

        # Parse JSON array from response using non-greedy extraction
        results = _parse_json_array(response)
        if results is None:
            return {"status": "no_update", "message": "No relevant progress mentioned or extracted."}

        updates: List[Dict[str, Any]] = []
        seen_goal_ids: Set[str] = set()
        for result in results:
            result_dict = cast(Dict[str, Any], result)
            try:
                if not isinstance(result, dict) or not result_dict.get('found') or result_dict.get('value') is None:
                    continue
                goal_id = cast(str, result_dict.get('goal_id', ''))
                if not goal_id or goal_id in seen_goal_ids:
                    continue
                seen_goal_ids.add(goal_id)
                goal = goals_by_id.get(goal_id)
                if not goal:
                    continue
                # Double-guard: never write numeric progress to a purely qualitative goal
                if goal.get('target_value') is None and goal.get('metric') is None and goal.get('current_value') is None:
                    continue
                parsed_val = _safe_optional_float(result_dict.get('value'))
                if parsed_val is None or parsed_val < 0:
                    continue
                new_value = parsed_val
                old_value = _safe_optional_float(goal.get('current_value'))
                if old_value is None or new_value != old_value:
                    if idempotency_key_prefix is None:
                        goals_db.update_goal_progress(uid, goal_id, new_value)
                    else:
                        goals_db.update_goal_progress(
                            uid,
                            goal_id,
                            new_value,
                            idempotency_key=f'{idempotency_key_prefix}:{goal_id}',
                            account_generation=account_generation,
                        )
                    goal_title = goal.get('title', '')
                    logger.info(
                        f"[GOAL-AUTO] Updated '{goal_title}': {old_value} -> {new_value} (reasoning: {result_dict.get('reasoning', 'N/A')})"
                    )
                    updates.append(
                        {
                            "goal_id": goal_id,
                            "goal_title": goal_title,
                            "old_value": old_value,
                            "new_value": new_value,
                            "reasoning": str(result_dict.get('reasoning') or ''),
                        }
                    )
            except (ValueError, TypeError, KeyError):
                continue

        if updates:
            return {"status": "updated", "updates": updates}
        return {"status": "no_update", "message": "No relevant progress mentioned or extracted."}
    except Exception as e:
        logger.error(f"Error in extract_and_update_goal_progress: {e}")
        return {"status": "error", "message": str(e)}


def _parse_json_array(text: str) -> Optional[List[Any]]:
    """Extract and parse the first JSON array from LLM response text."""
    # Find the first '[' and try to parse from there
    start = text.find('[')
    if start == -1:
        return None
    try:
        decoder = json.JSONDecoder()
        result, _ = decoder.raw_decode(text, start)
        if isinstance(result, list):
            return cast(List[Any], result)
        return [result]
    except (json.JSONDecodeError, ValueError):
        return None

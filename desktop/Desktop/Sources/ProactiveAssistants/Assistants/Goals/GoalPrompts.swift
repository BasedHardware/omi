import Foundation

/// Prompts for AI-powered goal features
/// Adapted from backend: /Users/matthewdi/omi/backend/utils/llm/goals.py
enum GoalPrompts {

    /// Prompt for getting actionable advice on achieving a goal
    static let goalAdvice = """
You are a strategic advisor. Based on the user's goal and their context, give ONE specific actionable step they should take THIS WEEK.

GOAL: "{goal_title}"
PROGRESS: {current_value} / {target_value} ({progress_pct}%)

RECENT CONVERSATIONS (what they've been discussing/working on):
{conversation_context}

USER FACTS:
{memory_context}

Give ONE specific action in 1-2 sentences. Be concise but complete. No generic advice.
"""

    /// Prompt for automatically generating a goal based on rich user context
    static let generateGoal = """
You are generating a personal goal for a user. Your job is to reason deeply about WHO this person is and what they're trying to ACHIEVE — not just what they talk about day-to-day.

STEP 1: Understand the user at a high level. What is their role? What are their ambitions? What life direction are they heading in?

USER'S PERSONA:
{persona_context}

USER'S MEMORIES (facts about them):
{memory_context}

STEP 2: Look at what they're actively working on and talking about. What unmet needs or gaps do you see?

RECENT CONVERSATIONS (what they've been discussing/working on):
{conversation_context}

CURRENT TASKS (each prefixed with [task_id]):
{action_items_context}

STEP 3: Review their goal history. Do NOT re-suggest goals they already completed or abandoned. Learn from what they chose to stop doing.

ACTIVE GOALS (do NOT duplicate):
{existing_goals}

COMPLETED GOALS (already achieved — do not repeat):
{completed_goals}

ABANDONED GOALS (user chose to stop — avoid similar goals unless context strongly suggests they want to retry):
{abandoned_goals}

STEP 4: Synthesize. Based on the above, identify ONE specific, measurable goal that:
1. Reflects what the user is STRIVING for at a deeper level, not just surface-level patterns in their conversations
2. Addresses an unmet need or gap — something they care about but haven't made structured progress on
3. Is NOT a duplicate of any active, completed, or abandoned goal
4. Has a clear numeric target and timeframe implied by the title (e.g., "Ship 3 features this month", "Read 2 books", "Close 5 deals")
5. Would genuinely excite or motivate this specific person

STEP 5: Link relevant tasks. Look at the CURRENT TASKS list above. Pick any tasks (by their [task_id]) that are directly related to achieving this goal. Only link tasks that genuinely contribute to the goal — don't force connections.

Return JSON only:
{
    "suggested_title": "Brief, actionable goal title",
    "suggested_description": "1-2 sentences explaining WHY this goal matters for the user and what achieving it looks like",
    "suggested_type": "scale" or "numeric" or "boolean",
    "suggested_target": <number>,
    "suggested_min": <minimum value>,
    "suggested_max": <maximum value or target>,
    "reasoning": "One sentence explaining why this goal fits the user right now",
    "linked_task_ids": ["task_id_1", "task_id_2"]
}

Choose a goal type:
- "boolean" for yes/no goals (0 or 1)
- "scale" for rating goals (e.g., 0-10 satisfaction)
- "numeric" for countable goals (e.g., books read, money saved, users acquired)
"""

    /// Prompt for extracting goal progress from text
    static let extractProgress = """
Analyze this message to see if it mentions progress toward this goal:

Goal: "{goal_title}"
Goal Type: {goal_type}
Current Progress: {current_value} / {target_value}

User Message: "{text}"

If the message mentions a NEW progress value for this goal, extract it.
Handle formats like:
- "1k users" -> 1000
- "500k" -> 500000
- "1.5 million" -> 1500000
- "1000" -> 1000
- Percentages relative to goal

Return JSON only: {"found": true/false, "value": number_or_null, "reasoning": "brief explanation"}
Only return found=true if you're confident this is about the SPECIFIC goal mentioned above.
"""
}

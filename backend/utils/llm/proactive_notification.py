from typing import List, Optional

from pydantic import BaseModel, Field

from utils.llm.clients import llm_mini


class ProactiveAdvice(BaseModel):
    notification_text: str = Field(
        description="The advice. Max 100 chars. Start with the actionable part. No filler words."
    )
    reasoning: str = Field(
        description=(
            "Why this is worth interrupting. MUST cite a specific date, quote, or detail "
            "from the user's facts, goals, or past conversations. "
            "If you can only say 'user mentioned X' without a concrete reference, set has_advice=false."
        )
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "0.90+: preventing a concrete mistake or critical non-obvious connection. "
            "0.75-0.89: specific dot-connecting across conversations the user would miss. "
            "0.60-0.74: useful but user might figure it out. "
            "Below 0.60: do not send."
        ),
    )
    category: str = Field(description="One of: productivity, mistake_prevention, goal_connection, dot_connecting")


class ProactiveNotificationResult(BaseModel):
    has_advice: bool = Field(
        description=(
            "True ONLY when advice is SPECIFIC to the conversation AND the user likely "
            "would NOT figure it out themselves. False in all other cases."
        )
    )
    advice: Optional[ProactiveAdvice] = Field(
        default=None, description="The notification to send. Required when has_advice is true."
    )
    context_summary: str = Field(description="Brief summary of what user is discussing (1 sentence). Always provided.")
    current_activity: str = Field(default="", description="What the user is doing or deciding right now.")


FREQUENCY_TO_BASE_THRESHOLD = {
    0: None,
    1: 0.92,
    2: 0.85,
    3: 0.78,
    4: 0.70,
    5: 0.60,
}

FREQUENCY_GUIDANCE = {
    1: "Ultra selective. Only prevent clear mistakes or truly critical insights. 1-3 per day max.",
    2: "Very selective. Only non-obvious insights tied to specific goals or history. 3-5 per day.",
    3: "Balanced. Only when you have a specific, actionable insight the user would miss. 5-8 per day.",
    4: "Proactive. Share specific insights connecting this conversation to goals/history. 8-12 per day.",
    5: "Very proactive. Share insights when you spot non-obvious connections. Up to 12 per day.",
}

MAX_DAILY_NOTIFICATIONS = 12

PROACTIVE_PROMPT_TEMPLATE = """You analyze {user_name}'s live conversations to find ONE specific, high-value insight they would NOT figure out on their own.

CORE QUESTION: Is {user_name} about to make a mistake, missing a non-obvious connection to their goals/history, or forgetting a commitment?

SET has_advice=true ONLY when you can answer YES to BOTH:
1. The advice is SPECIFIC to what's being discussed (not generic wisdom)
2. {user_name} likely does NOT already know this (non-obvious)

SET has_advice=false when:
- You'd be stating something obvious ({user_name} can figure it out themselves)
- The advice is generic and not tied to the specific conversation content
- The advice is similar to something in RECENT NOTIFICATIONS (check below)
- You sent a notification on the same topic in the last 24 hours (check RECENT NOTIFICATIONS timestamps)
- You're reaching — if you have to stretch to find advice, there isn't any

WHAT QUALIFIES (high bar):
- {user_name} is about to make a decision that contradicts a specific goal they set
- {user_name} mentioned person X two weeks ago in context Y, and that's directly relevant now
- {user_name} committed to doing X but is now doing the opposite
- A specific fact from {user_name}'s history directly applies to the current conversation
- {user_name} is repeating a pattern you've seen before that led to a bad outcome

WHAT DOES NOT QUALIFY (instant has_advice=false):
- "Take a break" / "Stay hydrated" / "Practice mindfulness" / "Pause and reflect" (wellness)
- "Stay focused" / "You've got this" / "Believe in yourself" (motivational platitudes)
- "It sounds like you're frustrated" / "Let's take a moment" (therapist-speak)
- "You should think about..." / "Consider..." / "You might want to..." (vague suggestions)
- "Confirm [thing]" / "Ensure [thing]" / "Clarify [thing]" — restating awareness is NOT advice. {user_name} already knows what they're working on. Only qualify if you're adding a SPECIFIC fact they don't have.
- Restating what {user_name} just said in different words
- Generic productivity advice that applies to anyone
- Anything about emotions, stress, frustration, or feelings
- Advice that could be given without knowing {user_name}'s specific history/goals

== {user_name}'S FACTS ==
{user_facts}

== {user_name}'S GOALS ==
{goals_text}

== RELEVANT PAST CONVERSATIONS ==
{past_conversations}

== CURRENT CONVERSATION ==
{current_conversation}

== RECENT NOTIFICATIONS (do not repeat or send semantically similar) ==
{recent_notifications}

== FREQUENCY ==
{frequency_guidance}

FORMAT: Keep notification_text under 100 characters. Start with the actionable part. No filler.
- GOOD: "Call Mike about the deal — he mentioned a deadline Friday"
- GOOD: "You said you'd stop taking on extra projects. This is that."
- BAD: "Nikita, it sounds like frustration is high right now. When you feel overwhelmed..."
- BAD: "Your messages show frustration and maybe anger. Let's take a moment."

REASONING must cite a SPECIFIC date, quote, or detail from {user_name}'s facts, goals, or past conversations. Example: "On Feb 12, {user_name} told Mike he'd finish by Friday — that's tomorrow and he hasn't started." If your reasoning only says "{user_name} mentioned X" without a concrete reference, set has_advice=false."""


def _format_goals(goals: list) -> str:
    if not goals:
        return "No active goals set."
    lines = []
    for g in goals:
        title = g.get('title', g.get('description', 'Unnamed goal'))
        description = g.get('description', '')
        if description and description != title:
            lines.append(f"- {title}: {description}")
        else:
            lines.append(f"- {title}")
    return "\n".join(lines)


def _format_current_conversation(messages: list, user_name: str) -> str:
    if not messages:
        return "No conversation in progress."
    lines = []
    for msg in messages:
        speaker = user_name if msg.get('is_user') else "Other"
        lines.append(f"[{speaker}]: {msg.get('text', '')}")
    return "\n".join(lines)


def _format_recent_notifications(notifications: list) -> str:
    if not notifications:
        return "No recent notifications sent."
    lines = []
    for n in notifications:
        created = n.get('created_at', 'unknown time')
        text = n.get('text', '')
        lines.append(f"[{created}]: {text}")
    return "\n".join(lines)


def evaluate_proactive_notification(
    user_name: str,
    user_facts: str,
    goals: list,
    past_conversations_str: str,
    current_messages: list,
    recent_notifications: list,
    frequency: int,
) -> ProactiveNotificationResult:
    goals_text = _format_goals(goals)
    current_conversation = _format_current_conversation(current_messages, user_name)
    notifications_text = _format_recent_notifications(recent_notifications)
    guidance = FREQUENCY_GUIDANCE.get(frequency, FREQUENCY_GUIDANCE[3])

    prompt = PROACTIVE_PROMPT_TEMPLATE.format(
        user_name=user_name,
        user_facts=user_facts,
        goals_text=goals_text,
        past_conversations=(
            past_conversations_str if past_conversations_str else "No relevant past conversations found."
        ),
        current_conversation=current_conversation,
        recent_notifications=notifications_text,
        frequency_guidance=guidance,
    )

    with_parser = llm_mini.with_structured_output(ProactiveNotificationResult)
    result: ProactiveNotificationResult = with_parser.invoke(prompt)
    return result

from typing import List, Optional

from pydantic import BaseModel, Field

from utils.llm.clients import llm_mini


class ProactiveAdvice(BaseModel):
    notification_text: str = Field(description="The push notification message (<300 chars, direct, personal)")
    reasoning: str = Field(
        description=(
            "Why this notification is worth sending. MUST cite a specific fact, goal, "
            "or past conversation from the user's history. If you cannot cite a concrete "
            "connection, do not send the notification."
        )
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "0.90+ = preventing a mistake or critical connection to goals. "
            "0.75-0.89 = non-obvious dot-connecting across conversations/history. "
            "0.50-0.74 = useful but user might figure out themselves. "
            "Below 0.50 = generic, don't send."
        ),
    )
    category: str = Field(
        description="One of: goal_connection, pattern_insight, mistake_prevention, commitment_reminder, dot_connecting"
    )


class ProactiveNotificationResult(BaseModel):
    has_advice: bool = Field(
        description=(
            "True ONLY when the notification scores high on at least 3 of the 4 axes: "
            "actionability, timeliness, non-obviousness, connection to history/goals."
        )
    )
    advice: Optional[ProactiveAdvice] = Field(
        default=None, description="The notification to send. Required when has_advice is true."
    )
    context_summary: str = Field(
        description="Brief summary of the current conversation context (1-2 sentences). Always provided."
    )


FREQUENCY_TO_BASE_THRESHOLD = {
    0: None,
    1: 0.90,
    2: 0.75,
    3: 0.60,
    4: 0.40,
    5: 0.25,
}

FREQUENCY_GUIDANCE = {
    1: "Ultra selective. Only for preventing clear mistakes or truly critical insights. 1-3 per day max.",
    2: "Very selective. Only non-obvious insights that connect to their goals or history. 3-5 per day.",
    3: "Balanced. Interrupt when you have specific, actionable value tied to their goals/patterns. 5-10 per day.",
    4: "Proactive. Share relevant insights connecting current conversation to goals/history. 8-12 per day.",
    5: "Very proactive. Look for any opportunity to connect dots and add value. Up to 12 per day.",
}

MAX_DAILY_NOTIFICATIONS = 12

PROACTIVE_PROMPT_TEMPLATE = """You are {user_name}'s sharp, observant friend who has been listening to their conversations and knows their history deeply. You are NOT a life coach, therapist, or wellness advisor. You are the friend who connects dots others miss.

Your job: Decide if the current conversation warrants a push notification. Most of the time, it does NOT.

== {user_name}'S FACTS & PERSONALITY ==
{user_facts}

== {user_name}'S ACTIVE GOALS ==
{goals_text}

== RELEVANT PAST CONVERSATIONS ==
{past_conversations}

== CURRENT LIVE CONVERSATION ==
{current_conversation}

== YOUR RECENT NOTIFICATIONS (last 20) ==
{recent_notifications}

== NOTIFICATION FREQUENCY SETTING ==
{frequency_guidance}

== EVALUATION FRAMEWORK ==
Before deciding to send a notification, evaluate on ALL FOUR axes:

1. ACTIONABILITY: Can {user_name} DO something concrete right now based on this? ("You should think about..." = NOT actionable. "Call Mike back about the deal before 5pm" = actionable.)

2. TIMELINESS: Does this matter RIGHT NOW vs later? Is there a window closing? A decision being made? If it can wait until tomorrow, don't send it now.

3. NON-OBVIOUSNESS: Would {user_name} have figured this out themselves? This is the "holy shit" axis. Connecting their goal X with something they said 2 weeks ago with what they're about to do RIGHT NOW = non-obvious. Telling them to "stay focused" = painfully obvious.

4. CONNECTION TO HISTORY/GOALS: Does this link the current conversation to their stated goals, past patterns, or previous commitments? The more specific the connection, the higher the value.

has_advice should be true ONLY when the notification scores high on at least 3 of these 4 axes.

== CONFIDENCE CALIBRATION ==
- 0.90+ : Preventing a concrete mistake OR critical connection to a specific goal with time pressure
- 0.75-0.89 : Non-obvious dot-connecting across different conversations or time periods
- 0.50-0.74 : Useful insight but user might figure it out themselves
- Below 0.50 : Generic observation — DO NOT SEND

== ANTI-PATTERNS (instant has_advice=false) ==
- Generic wellness advice ("take a break", "stay hydrated", "practice mindfulness")
- Vague suggestions without specific references ("you might want to consider...")
- Restating what the user just said back to them
- Motivational platitudes ("you've got this!", "believe in yourself!")
- Advice that doesn't reference a specific fact, goal, or past conversation
- Hedging with "however" or "on the other hand" — take a clear stance or don't send

== REASONING REQUIREMENT ==
The reasoning field MUST cite a specific fact, goal, or past conversation. Example:
- GOOD: "User's goal is 'save $50k for house' and they're about to spend $3k on a vacation they mentioned regretting last month"
- BAD: "User seems stressed and could use some encouragement"
If you cannot write a reasoning that cites a concrete connection, set has_advice=false.

== OUTPUT ==
Always provide context_summary (brief summary of current conversation).
Set has_advice=true only when you have a genuinely valuable, non-obvious notification.
When has_advice=true, provide the full advice object with notification_text (<300 chars), reasoning, confidence, and category."""


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

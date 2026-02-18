from typing import List, Optional

from pydantic import BaseModel, Field

from models.chat import Message
from utils.llm.clients import llm_mini
from utils.llms.memory import get_prompt_memories


class ProactiveAdvice(BaseModel):
    notification_text: str = Field(
        description="Push notification message (<300 chars, direct, like texting a sharp friend)"
    )
    reasoning: str = Field(
        description="Must cite specific facts, goals, or past conversations that make this advice non-obvious. "
        "If you cannot cite a concrete connection, do not send the notification."
    )
    confidence: float = Field(ge=0, le=1, description="Confidence score 0-1 based on calibration guide")
    category: str = Field(
        description="One of: goal_connection, pattern_insight, mistake_prevention, dot_connecting, timely_nudge"
    )


class ProactiveNotificationResult(BaseModel):
    has_advice: bool = Field(description="True only when the notification scores high on at least 3 of the 4 axes")
    advice: Optional[ProactiveAdvice] = Field(default=None, description="The notification to send, if any")
    context_summary: str = Field(default="", description="Brief summary of what's happening in the conversation")


FREQUENCY_TO_BASE_THRESHOLD = {
    0: None,  # disabled
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

PROACTIVE_NOTIFICATION_PROMPT = '''You are {user_name}'s sharp, observant friend who knows their history, goals, and patterns.
Your job: connect dots across time and conversations that {user_name} wouldn't connect themselves.

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
Before sending ANY notification, evaluate on these four axes:

1. ACTIONABILITY: Can {user_name} DO something concrete right now based on this?
2. TIMELINESS: Does this matter NOW vs later? Is there a window closing?
3. NON-OBVIOUSNESS: Would {user_name} have figured this out themselves? (This is the "holy shit" axis — connecting their goal X with something they said 2 weeks ago with what they're about to do right now.)
4. CONNECTION TO HISTORY/GOALS: Does this link the current conversation to their stated goals, past patterns, or previous commitments?

Set has_advice=true ONLY when the notification scores high on at least 3 of these 4 axes.

== CONFIDENCE CALIBRATION ==
- 0.90+: Preventing a specific mistake OR a critical connection to their goals that they clearly don't see
- 0.75-0.89: Non-obvious dot-connecting across conversations/history. "You said X two weeks ago, and now you're about to Y"
- 0.50-0.74: Useful insight but the user might figure it out themselves
- Below 0.50: Generic advice. Do NOT send.

== ANTI-PATTERNS (never do these) ==
- Generic wellness advice ("take a break", "stay hydrated", "practice gratitude")
- Vague suggestions without specific reference to their history ("you might want to consider...")
- Restating what the user just said back to them
- Hedging or presenting both sides ("on one hand... on the other hand...")
- Advice that doesn't reference a specific fact, goal, or past conversation

== REASONING REQUIREMENT ==
The reasoning field MUST cite a specific fact, goal, or past conversation. Example:
- GOOD: "User's goal is to save $50k for a house. They mentioned spending $600 on a gaming console. Two weeks ago they said they were behind on savings."
- BAD: "User seems to be spending money they shouldn't."
If you cannot write reasoning that cites specifics, set has_advice=false.

== OUTPUT FORMAT ==
- notification_text: <300 chars, direct, like a sharp friend texting. No markdown, no emojis. End with a specific question.
- category: goal_connection | pattern_insight | mistake_prevention | dot_connecting | timely_nudge
'''


def evaluate_proactive_notification(
    user_name: str,
    user_facts: str,
    goals: List[dict],
    past_conversations: str,
    current_conversation: str,
    recent_notifications: str,
    frequency: int,
) -> ProactiveNotificationResult:
    goals_text = "No active goals set."
    if goals:
        parts = []
        for g in goals:
            title = g.get('title', g.get('description', 'Unnamed goal'))
            desc = g.get('description', '')
            if desc and desc != title:
                parts.append(f"- {title}: {desc}")
            else:
                parts.append(f"- {title}")
        goals_text = "\n".join(parts)

    guidance = FREQUENCY_GUIDANCE.get(frequency, FREQUENCY_GUIDANCE[3])

    prompt = PROACTIVE_NOTIFICATION_PROMPT.format(
        user_name=user_name or "User",
        user_facts=user_facts or "No facts available.",
        goals_text=goals_text,
        past_conversations=past_conversations or "No relevant past conversations found.",
        current_conversation=current_conversation or "No conversation content.",
        recent_notifications=recent_notifications or "No recent notifications sent.",
        frequency_guidance=guidance,
    )

    with_parser = llm_mini.with_structured_output(ProactiveNotificationResult)
    result: ProactiveNotificationResult = with_parser.invoke(prompt)
    return result


def get_proactive_message(
    uid: str,
    plugin_prompt: str,
    params: [str],
    context: str,
    chat_messages: List[Message],
    user_name: str = None,
    user_facts: str = None,
) -> str:
    """Legacy function for external/third-party app proactive notifications."""
    if user_name is None or user_facts is None:
        user_name, user_facts = get_prompt_memories(uid)

    prompt = plugin_prompt
    memories_str = user_facts
    for param in params:
        if param == "user_name":
            prompt = prompt.replace("{{user_name}}", user_name)
            continue
        if param == "user_facts":
            prompt = prompt.replace("{{user_facts}}", memories_str)
            continue
        if param == "user_context":
            prompt = prompt.replace("{{user_context}}", context if context else "")
            continue
        if param == "user_chat":
            prompt = prompt.replace(
                "{{user_chat}}", Message.get_messages_as_string(chat_messages) if chat_messages else ""
            )
            continue
    prompt = prompt.replace('    ', '').strip()

    return llm_mini.invoke(prompt).content

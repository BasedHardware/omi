from typing import List, Optional

from pydantic import BaseModel, Field

from utils.llm.clients import llm_mini
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Step 1: Relevance Gate — is this conversation worth evaluating?
# ---------------------------------------------------------------------------


class RelevanceResult(BaseModel):
    is_relevant: bool = Field(
        description=(
            "True ONLY if there is a specific, concrete insight the user would genuinely "
            "benefit from hearing right now. Most conversations are NOT relevant — default to false."
        )
    )
    relevance_score: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "0.90+: preventing a concrete mistake or time-sensitive opportunity right now. "
            "0.75-0.89: non-obvious connection the user would genuinely miss. "
            "0.60-0.74: somewhat useful but user might figure it out. "
            "Below 0.60: not worth interrupting."
        ),
    )
    reasoning: str = Field(
        description="What specific thing in the conversation warrants a notification. Must cite a concrete detail."
    )
    context_summary: str = Field(description="Brief summary of what user is discussing (1 sentence).")


GATE_PROMPT = """You decide whether {user_name}'s current conversation contains something worth interrupting them about.

IMPORTANT: Most conversations do NOT warrant a notification. Your default answer is is_relevant=false.

{user_name} should be interrupted ONLY when you can point to a SPECIFIC thing:
- {user_name} is about to make a concrete mistake (wrong numbers, contradicting a commitment, agreeing to something bad)
- Someone said something that directly conflicts with {user_name}'s stated plans, commitments, or history
- There is a time-sensitive action {user_name} should take RIGHT NOW that they will miss otherwise
- A specific, non-obvious connection between what's being said and {user_name}'s history that changes their next move

{user_name} should NOT be interrupted for:
- General conversations that loosely relate to their work or goals
- Topics where {user_name} is already handling things correctly
- Conversations where {user_name} is not speaking — unless someone said something critical that demands immediate action
- Anything where you need to stretch to justify relevance
- Opportunities to remind {user_name} about their goals (they already know their goals)
- Topics similar to RECENT NOTIFICATIONS below

== {user_name}'S FACTS ==
{user_facts}

== {user_name}'S GOALS ==
{goals_text}

== CURRENT CONVERSATION ==
{current_conversation}

== RECENT NOTIFICATIONS (do not flag similar topics) ==
{recent_notifications}"""


# ---------------------------------------------------------------------------
# Step 2: Generate — produce the actual notification text
# ---------------------------------------------------------------------------


class NotificationDraft(BaseModel):
    notification_text: str = Field(
        description="The notification. Max 100 chars. Specific and actionable. Like a text from a sharp friend."
    )
    reasoning: str = Field(
        description=(
            "Why this is worth sending. MUST cite specific names, numbers, dates, or quotes "
            "from the conversation or user history."
        )
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "0.90+: preventing a clear mistake or critical time-sensitive action. "
            "0.75-0.89: genuinely non-obvious connection the user would miss. "
            "0.60-0.74: useful but user might figure it out. "
            "Below 0.60: do not send."
        ),
    )
    category: str = Field(description="One of: productivity, mistake_prevention, goal_connection, dot_connecting")


GENERATE_PROMPT = """{user_name}'s conversation was flagged as containing something worth a notification.

The reason it was flagged: {gate_reasoning}

Generate ONE specific, actionable notification.

Rules:
- State WHAT happened and WHAT {user_name} should do — be concrete
- Reference specific names, numbers, or things actually said in the conversation
- Write it like a sharp friend texting, not a corporate advisor
- NEVER start with: Confirm, Ensure, Clarify, Consider, Prioritize, Remember, Review, Align, Make sure, Don't forget
- Under 100 characters
- The notification must contain information {user_name} does NOT already have, or a connection they can't see

== {user_name}'S FACTS ==
{user_facts}

== {user_name}'S GOALS ==
{goals_text}

== RELEVANT PAST CONVERSATIONS ==
{past_conversations}

== CURRENT CONVERSATION ==
{current_conversation}

== RECENT NOTIFICATIONS (do not repeat) ==
{recent_notifications}

== FREQUENCY ==
{frequency_guidance}"""


# ---------------------------------------------------------------------------
# Step 3: Critic — would a human actually want this notification?
# ---------------------------------------------------------------------------


class ValidationResult(BaseModel):
    approved: bool = Field(
        description="True ONLY if you would genuinely want to receive this notification yourself. Most should be rejected."
    )
    reasoning: str = Field(description="Why this should or should not be sent to the user's phone.")


CRITIC_PROMPT = """You are the last gate before this notification hits {user_name}'s phone. Your job is to BLOCK bad notifications. Most notifications should be REJECTED.

NOTIFICATION: "{notification_text}"
REASONING: "{draft_reasoning}"

THE CONVERSATION IT'S BASED ON:
{current_conversation}

{user_name}'S GOALS:
{goals_text}

Imagine you are {user_name}. You're in the middle of a conversation. Your phone buzzes. You look down and see this notification. Do you think:
A) "Oh shit, glad I saw this — this changes what I do next" → APPROVE
B) "I already know this / this is obvious / this is annoying / so what?" → REJECT

REJECT if ANY of these are true:
- The notification tells {user_name} something they clearly already know from the conversation
- The notification is a reminder about goals without providing new information
- The advice could apply to literally anyone in any conversation
- The notification uses vague corporate language (align, prioritize, leverage, ensure, optimize, reassess)
- The notification starts with a goal name (e.g. "30-video goal:", "Meet 12 people goal:")
- Removing this notification from {user_name}'s day would change absolutely nothing
- The "specific reference" in the reasoning is actually a stretch or very generic

APPROVE only if ALL of these are true:
- The notification contains specific information {user_name} genuinely does not have right now
- A smart friend would say this exact thing in person and {user_name} would thank them
- NOT seeing this notification could lead to a missed opportunity or avoidable mistake"""


# ---------------------------------------------------------------------------
# Legacy models (kept for eval tests backward compatibility)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Thresholds & frequency config
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Step 1: Gate
# ---------------------------------------------------------------------------


def evaluate_relevance(
    user_name: str,
    user_facts: str,
    goals: list,
    current_messages: list,
    recent_notifications: list,
) -> RelevanceResult:
    """Cheap first pass: is this conversation worth generating a notification for?"""
    goals_text = _format_goals(goals)
    current_conversation = _format_current_conversation(current_messages, user_name)
    notifications_text = _format_recent_notifications(recent_notifications)

    prompt = GATE_PROMPT.format(
        user_name=user_name,
        user_facts=user_facts,
        goals_text=goals_text,
        current_conversation=current_conversation,
        recent_notifications=notifications_text,
    )

    with_parser = llm_mini.with_structured_output(RelevanceResult)
    result: RelevanceResult = with_parser.invoke(prompt)
    return result


# ---------------------------------------------------------------------------
# Step 2: Generate
# ---------------------------------------------------------------------------


def generate_notification(
    user_name: str,
    user_facts: str,
    goals: list,
    past_conversations_str: str,
    current_messages: list,
    recent_notifications: list,
    frequency: int,
    gate_reasoning: str,
) -> NotificationDraft:
    """Generate the actual notification text, only called when gate passes."""
    goals_text = _format_goals(goals)
    current_conversation = _format_current_conversation(current_messages, user_name)
    notifications_text = _format_recent_notifications(recent_notifications)
    guidance = FREQUENCY_GUIDANCE.get(frequency, FREQUENCY_GUIDANCE[3])

    prompt = GENERATE_PROMPT.format(
        user_name=user_name,
        user_facts=user_facts,
        goals_text=goals_text,
        past_conversations=(
            past_conversations_str if past_conversations_str else "No relevant past conversations found."
        ),
        current_conversation=current_conversation,
        recent_notifications=notifications_text,
        frequency_guidance=guidance,
        gate_reasoning=gate_reasoning,
    )

    with_parser = llm_mini.with_structured_output(NotificationDraft)
    result: NotificationDraft = with_parser.invoke(prompt)
    return result


# ---------------------------------------------------------------------------
# Step 3: Critic
# ---------------------------------------------------------------------------


def validate_notification(
    user_name: str,
    notification_text: str,
    draft_reasoning: str,
    current_messages: list,
    goals: list,
) -> ValidationResult:
    """Final human-perspective check: would you actually want this on your phone?"""
    current_conversation = _format_current_conversation(current_messages, user_name)
    goals_text = _format_goals(goals)

    prompt = CRITIC_PROMPT.format(
        user_name=user_name,
        notification_text=notification_text,
        draft_reasoning=draft_reasoning,
        current_conversation=current_conversation,
        goals_text=goals_text,
    )

    with_parser = llm_mini.with_structured_output(ValidationResult)
    result: ValidationResult = with_parser.invoke(prompt)
    return result


# ---------------------------------------------------------------------------
# Legacy single-call (kept for eval tests)
# ---------------------------------------------------------------------------

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


def evaluate_proactive_notification(
    user_name: str,
    user_facts: str,
    goals: list,
    past_conversations_str: str,
    current_messages: list,
    recent_notifications: list,
    frequency: int,
) -> ProactiveNotificationResult:
    """Legacy single-call evaluation. Kept for eval tests."""
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

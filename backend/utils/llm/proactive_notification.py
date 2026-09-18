import hashlib
import os
import re
from typing import Any, Mapping, Optional, cast

from langchain_core.messages import BaseMessage, HumanMessage
from pydantic import BaseModel, Field

from utils.byok import has_byok_keys
from utils.llm.clients import get_llm
from utils.llm.gateway_client import should_route_features_through_gateway
from utils.llm.model_config import get_model_config
from utils.llm.prompt_cache import EXPLICIT_CACHE_BREAKPOINT, EXPLICIT_CACHE_OPTIONS, has_cacheable_prefix
from utils.llm.temporal import current_date_in_tz
import logging

logger = logging.getLogger(__name__)

Record = Mapping[str, object]

# Kill switch for the gate's explicit prompt cache. Default on: the gate is the
# single largest paid-tier OpenAI line and the whole point of the split prompt
# below is that its prefix becomes readable. Set to a falsey value to fall back
# to an unmarked (uncached, plain-input-rate) request without a deploy.
MENTOR_GATE_PROMPT_CACHE_ENABLED_ENV = 'MENTOR_GATE_PROMPT_CACHE_ENABLED'


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


GATE_PROMPT_STABLE = """You decide whether {user_name}'s current conversation contains something worth interrupting them about.

Today is {current_date}. Treat this as the present when judging whether anything is upcoming, time-sensitive, or in the future. Dates in {current_date}'s year or later are normal and current; never decide a correctly stated date is wrong or in the future based on your own assumptions about the year.

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

"""

# Everything after the goals block changes on every single gate call, so it must
# live after the cache breakpoint. Splitting here is what makes the prefix above
# readable at all: see utils/llm/prompt_cache.
GATE_PROMPT_VOLATILE = """== CURRENT CONVERSATION ==
{current_conversation}

== RECENT NOTIFICATIONS (do not flag similar topics) ==
{recent_notifications}"""

# GATE_PROMPT is the concatenation of the two blocks above and is kept as the
# single-string form the eval suites render. Production sends the two blocks as
# separate content parts so the stable one can end on a cache breakpoint; the
# bytes the model reads are identical either way.
GATE_PROMPT = GATE_PROMPT_STABLE + GATE_PROMPT_VOLATILE


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

Today is {current_date}. Treat this as the present; a correctly stated date in {current_date}'s year or later is normal, not an error or something to warn the user about.

The reason it was flagged: {gate_reasoning}

Generate ONE specific, actionable notification.

Rules:
- State WHAT happened and WHAT {user_name} should do — be concrete
- Reference specific names, numbers, or things actually said in the conversation
- Write it like a sharp friend texting, not a corporate advisor
- NEVER start with: Confirm, Ensure, Clarify, Consider, Prioritize, Remember, Review, Align, Make sure, Don't forget
- Under 100 characters
- The notification must contain information {user_name} does NOT already have, or a connection they can't see{language_instruction}

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

Today is {current_date}. REJECT any notification that claims a correctly stated date is in the future, or that the user's clock, calendar, or system date is wrong, when that is based only on an assumption about what year it is. Dates in {current_date}'s year or later are normal.

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
- The "specific reference" in the reasoning is actually a stretch or very generic{language_instruction}

APPROVE only if ALL of these are true:
- The notification contains specific information {user_name} genuinely does not have right now
- A smart friend would say this exact thing in person and {user_name} would thank them
- NOT seeing this notification could lead to a missed opportunity or avoidable mistake"""


# Accept only clean BCP-47-style language/locale tokens (e.g. ja, pt-BR, zh-TW). The language comes
# from a user-controlled preference and is interpolated into the prompts, so reject anything else
# (newlines, punctuation, extra text) to prevent prompt injection.
_BCP47_LANGUAGE_RE = re.compile(r'[A-Za-z]{2,8}(-[A-Za-z0-9]{2,8})*')


def _language_instruction(output_language: str, *, for_critic: bool = False) -> str:
    """Instruction telling the model to write (or, for the critic, reject if not written in) the
    user's language (#5214).

    Returns "" for English, an unset language, or any value that is not a clean BCP-47 token, so the
    model defaults to English and a user-controlled preference cannot inject prompt text. English
    family codes (en, en-US, ...) intentionally produce no instruction.
    """
    lang = (output_language or 'en').strip()
    if not lang or lang.lower().startswith('en') or not _BCP47_LANGUAGE_RE.fullmatch(lang):
        return ""
    if for_critic:
        return f"\n- The notification is written in a language other than the user's (expected code: {lang})"
    return f"\n- Write the notification entirely in the user's language (language/locale code: {lang})"


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
    4: "Proactive. Share specific insights connecting this conversation to goals/history. 6-9 per day.",
    5: "Very proactive. Share insights when you spot non-obvious connections. Up to 9 per day.",
}


def _resolve_daily_cap(default: int = 9, minimum: int = 1, maximum: int = 1000) -> int:
    """Read the daily-cap override, clamped to a sane range.

    A non-integer or unset value falls back to the default, and the result is
    bounded so a typo cannot silently disable proactive notifications (0/negative)
    or remove throttling entirely (an accidental huge value)."""
    raw = os.getenv('MAX_DAILY_NOTIFICATIONS')
    if raw is None:
        return default
    try:
        return max(minimum, min(int(raw), maximum))
    except (TypeError, ValueError):
        return default


# Hard ceiling on proactive notifications per user per day, across every source
# (mentor + third-party proactive apps). Defaults to 9 to keep the user under the
# "less than 10 daily notifs" target in #4859; override with the env var to tune
# without a code change.
MAX_DAILY_NOTIFICATIONS = _resolve_daily_cap()


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _str_value(value: object, default: str = "") -> str:
    if isinstance(value, str):
        return value
    return default


def _format_goals(goals: list[Record]) -> str:
    if not goals:
        return "No active goals set."
    lines: list[str] = []
    for g in goals:
        title = _str_value(g.get('title'), _str_value(g.get('description'), 'Unnamed goal'))
        description = _str_value(g.get('description'))
        if description and description != title:
            lines.append(f"- {title}: {description}")
        else:
            lines.append(f"- {title}")
    return "\n".join(lines)


def _format_current_conversation(messages: list[Record], user_name: str) -> str:
    if not messages:
        return "No conversation in progress."
    lines: list[str] = []
    for msg in messages:
        speaker = user_name if msg.get('is_user') else "Other"
        lines.append(f"[{speaker}]: {_str_value(msg.get('text'))}")
    return "\n".join(lines)


def _format_recent_notifications(notifications: list[Record]) -> str:
    if not notifications:
        return "No recent notifications sent."
    lines: list[str] = []
    for n in notifications:
        created = _str_value(n.get('created_at'), 'unknown time')
        text = _str_value(n.get('text'))
        lines.append(f"[{created}]: {text}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Step 1: Gate
# ---------------------------------------------------------------------------


def _env_flag_enabled(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {'1', 'true', 'yes', 'on'}


def gate_cache_supported() -> bool:
    """True only when the gate request actually reaches an OpenAI GPT-5.6 model.

    The explicit-cache contract (``prompt_cache_options`` plus a
    ``prompt_cache_breakpoint`` content part) is a GPT-5.6 request shape. A BYOK
    user's key can reroute this feature to another provider entirely, and a
    non-gateway deployment resolves the route from the QoS profile, so both are
    checked before a provider-specific field is put on the wire.
    """
    if has_byok_keys():
        return False
    if should_route_features_through_gateway():
        # generated_route_overrides.yaml pins the proactive_notification lane to
        # openai/gpt-5.6-luna.
        return True
    model, provider = get_model_config('proactive_notification')
    return provider == 'openai' and model.startswith('gpt-5.6')


def gate_cache_enabled() -> bool:
    return gate_cache_supported() and _env_flag_enabled(MENTOR_GATE_PROMPT_CACHE_ENABLED_ENV, default=True)


def gate_cache_key(uid: str) -> str:
    """Per-user routing key for the gate prefix.

    Hashed rather than raw: the key is sent to the provider and only has to be
    stable per user, not identifying. Versioned so a future prompt edit cannot
    collide with prefixes written by the previous wording.
    """
    return f'omi-mentor-gate-v1-{hashlib.sha256(uid.encode("utf-8")).hexdigest()[:32]}'


def build_gate_messages(stable: str, volatile: str, *, cache_enabled: bool) -> list[BaseMessage]:
    """One user message whose stable half ends on an explicit cache breakpoint.

    Two content parts of one message rather than two messages: the model reads
    exactly the concatenated text it read before this change, while the provider
    gains the boundary it needs to serve a read. Without the breakpoint the whole
    prompt is one unbroken block, which is why this feature reports zero cached
    tokens today (see utils/llm/prompt_cache).
    """
    stable_part: dict[str, Any] = {'type': 'text', 'text': stable}
    if cache_enabled:
        stable_part['prompt_cache_breakpoint'] = dict(EXPLICIT_CACHE_BREAKPOINT)
    return [HumanMessage(content=[stable_part, {'type': 'text', 'text': volatile}])]


def evaluate_relevance(
    user_name: str,
    user_facts: str,
    goals: list[Record],
    current_messages: list[Record],
    recent_notifications: list[Record],
    current_date: Optional[str] = None,
    uid: Optional[str] = None,
) -> RelevanceResult:
    """Cheap first pass: is this conversation worth generating a notification for?"""
    goals_text = _format_goals(goals)
    current_conversation = _format_current_conversation(current_messages, user_name)
    notifications_text = _format_recent_notifications(recent_notifications)
    resolved_date = current_date or current_date_in_tz(None)

    stable = GATE_PROMPT_STABLE.format(
        user_name=user_name,
        user_facts=user_facts,
        goals_text=goals_text,
        current_date=resolved_date,
    )
    volatile = GATE_PROMPT_VOLATILE.format(
        current_conversation=current_conversation,
        recent_notifications=notifications_text,
    )

    # A prefix under the provider's floor is never served back, so marking it
    # would buy a cache write nobody can read — strictly worse than plain input.
    cache_enabled = bool(uid) and has_cacheable_prefix(stable) and gate_cache_enabled()
    messages = build_gate_messages(stable, volatile, cache_enabled=cache_enabled)

    llm = get_llm(
        'proactive_notification',
        cache_key=gate_cache_key(uid) if cache_enabled and uid else None,
        prompt_cache_options=dict(EXPLICIT_CACHE_OPTIONS) if cache_enabled else None,
    )
    with_parser = llm.with_structured_output(RelevanceResult)
    result = cast(RelevanceResult, with_parser.invoke(messages))
    return result


# ---------------------------------------------------------------------------
# Step 2: Generate
# ---------------------------------------------------------------------------


def generate_notification(
    user_name: str,
    user_facts: str,
    goals: list[Record],
    past_conversations_str: str,
    current_messages: list[Record],
    recent_notifications: list[Record],
    frequency: int,
    gate_reasoning: str,
    output_language: str = 'en',
    current_date: Optional[str] = None,
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
        language_instruction=_language_instruction(output_language),
        current_date=current_date or current_date_in_tz(None),
    )

    with_parser = get_llm('proactive_notification').with_structured_output(NotificationDraft)
    result = cast(NotificationDraft, with_parser.invoke(prompt))
    return result


# ---------------------------------------------------------------------------
# Step 3: Critic
# ---------------------------------------------------------------------------


def validate_notification(
    user_name: str,
    notification_text: str,
    draft_reasoning: str,
    current_messages: list[Record],
    goals: list[Record],
    output_language: str = 'en',
    current_date: Optional[str] = None,
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
        language_instruction=_language_instruction(output_language, for_critic=True),
        current_date=current_date or current_date_in_tz(None),
    )

    with_parser = get_llm('proactive_notification').with_structured_output(ValidationResult)
    result = cast(ValidationResult, with_parser.invoke(prompt))
    return result


# ---------------------------------------------------------------------------
# Legacy single-call (kept for eval tests)
# ---------------------------------------------------------------------------

PROACTIVE_PROMPT_TEMPLATE = """You analyze {user_name}'s live conversations to find ONE specific, high-value insight they would NOT figure out on their own.

Today is {current_date}. Treat this as the present when reasoning about deadlines, "tomorrow", or whether something is upcoming. Never flag a correctly stated date as wrong or in the future based on an assumption about the year.

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

FORMAT: Keep notification_text under 100 characters.
- NEVER start with a goal name ("30-video goal:", "12-people goal:")
- NEVER say "your X goal" in the notification
- NEVER start with: Confirm, Ensure, Clarify, Consider, Prioritize, Remember, Review, Align, Reassess
- Lead with the action or the conflict, not the goal
- Write like you're texting a friend, not writing a corporate memo
- GOOD: "You just paused videos but your deadline means you'll fall behind by 6"
- GOOD: "Ask [Name] to grab coffee — strong fit and you're only at 4/12"
- GOOD: "Call Mike about the deal — he mentioned a deadline Friday"
- BAD: "30-video goal: line up a backup editor today"
- BAD: "Consider aligning your NYC plans with your growth strategy"
- BAD: "Your messages show frustration and maybe anger. Let's take a moment."

REASONING must cite a SPECIFIC date, quote, or detail from {user_name}'s facts, goals, or past conversations. Example: "On Feb 12, {user_name} told Mike he'd finish by Friday — that's tomorrow and he hasn't started." If your reasoning only says "{user_name} mentioned X" without a concrete reference, set has_advice=false."""


def evaluate_proactive_notification(
    user_name: str,
    user_facts: str,
    goals: list[Record],
    past_conversations_str: str,
    current_messages: list[Record],
    recent_notifications: list[Record],
    frequency: int,
    current_date: Optional[str] = None,
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
        current_date=current_date or current_date_in_tz(None),
    )

    with_parser = get_llm('proactive_notification').with_structured_output(ProactiveNotificationResult)
    result = cast(ProactiveNotificationResult, with_parser.invoke(prompt))
    return result

import hashlib
import os
import unicodedata
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional, Tuple, cast

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from models.app import App
from models.calendar_context import CalendarMeetingContext
from models.conversation import Conversation
from models.conversation_photo import ConversationPhoto
from models.structured import ActionItem, Event, Structured
from models.structured_extraction import ActionItemsExtraction, StructuredExtraction
from .clients import get_llm, get_llm_gateway_chat_structured, parser
from utils.byok import has_byok_keys
from utils.llm.gateway_client import record_chat_extraction_gateway_result
from utils.llm.gateway_observability import record_gateway_shadow_comparison
import logging

logger = logging.getLogger(__name__)
CONVERSATION_STRUCTURE_SHADOW_FEATURE = 'conversation_structure.extract.shadow'
CONVERSATION_STRUCTURE_SHADOW_ENABLED_ENV = 'OMI_LLM_GATEWAY_CONVERSATION_STRUCTURE_SHADOW_ENABLED'
CONVERSATION_STRUCTURE_SHADOW_SAMPLE_RATE_ENV = 'OMI_LLM_GATEWAY_CONVERSATION_STRUCTURE_SHADOW_SAMPLE_RATE'
CONVERSATION_ACTION_ITEMS_SHADOW_FEATURE = 'conversation_action_items.extract.shadow'
CONVERSATION_ACTION_ITEMS_SHADOW_ENABLED_ENV = 'OMI_LLM_GATEWAY_CONVERSATION_ACTION_ITEMS_SHADOW_ENABLED'
CONVERSATION_ACTION_ITEMS_SHADOW_SAMPLE_RATE_ENV = 'OMI_LLM_GATEWAY_CONVERSATION_ACTION_ITEMS_SHADOW_SAMPLE_RATE'

# =============================================
#            FOLDER ASSIGNMENT
# =============================================
# The implementation moved to conversation_folder.py; that route still uses
# get_llm('conv_folder') as the production model/provider plug-in seam.


class DiscardConversation(BaseModel):
    discard: bool = Field(description="If the conversation should be discarded or not")


class SpeakerIdMatch(BaseModel):
    speaker_id: int = Field(description="The speaker id assigned to the segment")


def _invoke_gateway_shadow_chain(chain: Any, values: dict[str, Any], *, feature: str) -> BaseModel | None:
    if has_byok_keys():
        record_chat_extraction_gateway_result(feature=feature, outcome='skipped', reason='byok')
        return None
    try:
        response = chain.invoke(values)
    except Exception:
        record_chat_extraction_gateway_result(feature=feature, outcome='fallback', reason='unexpected_error')
        return None
    record_chat_extraction_gateway_result(feature=feature, outcome='success', reason='ok')
    return response


def _word_count(text: str) -> int:
    if not text:
        return 0
    cjk_chars = sum(1 for c in text if unicodedata.east_asian_width(c) in ('W', 'F', 'H'))
    if cjk_chars > len(text) * 0.3:
        return cjk_chars // 2
    return len(text.split())


def _coerce_action_items(response: ActionItemsExtraction) -> List[ActionItem]:
    return response.to_action_items()


def _content_str(response: Any) -> str:
    content = response.content
    return content if isinstance(content, str) else str(content)


def _coerce_structured(response: Structured | StructuredExtraction) -> Structured:
    if isinstance(response, StructuredExtraction):
        return response.to_structured()
    return response


def _normalize_action_item_due_dates(
    action_items: List[ActionItem],
    *,
    user_tz: Any,
    now: datetime,
    log_past_due_clears: bool,
) -> List[ActionItem]:
    for action_item in action_items:
        if action_item.due_at is None:
            continue
        if action_item.due_at.tzinfo is None:
            action_item.due_at = action_item.due_at.replace(tzinfo=user_tz).astimezone(timezone.utc)
        else:
            action_item.due_at = action_item.due_at.astimezone(timezone.utc)
        if action_item.due_at < now - timedelta(days=1):
            if log_past_due_clears:
                logger.warning(
                    f'Clearing past due_at {action_item.due_at.isoformat()} for action item: {action_item.description}'
                )
            action_item.due_at = None
    return action_items


def _record_chat_extraction_comparison(*, feature: str, field: str, outcome: str) -> None:
    record_gateway_shadow_comparison(feature=feature, field=field, outcome=outcome)


def _env_flag_enabled(name: str, *, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {'1', 'true', 'yes', 'on'}


def _env_sample_rate(name: str, *, default: float = 0.0) -> float:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return max(0.0, min(1.0, float(value)))
    except ValueError:
        return default


def _should_run_gateway_shadow(
    *,
    feature: str,
    enabled_env: str,
    sample_rate_env: str,
    sample_id: str,
    started_at: datetime,
    conversation_context: str,
) -> bool:
    if has_byok_keys():
        record_chat_extraction_gateway_result(
            feature=feature,
            outcome='skipped',
            reason='byok',
        )
        return False

    if not _env_flag_enabled(enabled_env):
        record_chat_extraction_gateway_result(
            feature=feature,
            outcome='skipped',
            reason='disabled',
        )
        return False

    sample_rate = _env_sample_rate(sample_rate_env, default=1.0)
    if sample_rate <= 0:
        record_chat_extraction_gateway_result(
            feature=feature,
            outcome='skipped',
            reason='sample_rate_zero',
        )
        return False
    if sample_rate >= 1:
        return True

    sample_key = f'{sample_id}:{started_at.isoformat()}:{len(conversation_context)}'
    sample_value = int(hashlib.sha256(sample_key.encode('utf-8')).hexdigest()[:8], 16) / 0xFFFFFFFF
    if sample_value < sample_rate:
        return True

    record_chat_extraction_gateway_result(
        feature=feature,
        outcome='skipped',
        reason='sampled_out',
    )
    return False


def _should_run_conversation_structure_shadow(uid: str, started_at: datetime, conversation_context: str) -> bool:
    return _should_run_gateway_shadow(
        feature=CONVERSATION_STRUCTURE_SHADOW_FEATURE,
        enabled_env=CONVERSATION_STRUCTURE_SHADOW_ENABLED_ENV,
        sample_rate_env=CONVERSATION_STRUCTURE_SHADOW_SAMPLE_RATE_ENV,
        sample_id=uid,
        started_at=started_at,
        conversation_context=conversation_context,
    )


def _should_run_conversation_action_items_shadow(
    sample_id: str, started_at: datetime, conversation_context: str
) -> bool:
    return _should_run_gateway_shadow(
        feature=CONVERSATION_ACTION_ITEMS_SHADOW_FEATURE,
        enabled_env=CONVERSATION_ACTION_ITEMS_SHADOW_ENABLED_ENV,
        sample_rate_env=CONVERSATION_ACTION_ITEMS_SHADOW_SAMPLE_RATE_ENV,
        sample_id=sample_id,
        started_at=started_at,
        conversation_context=conversation_context,
    )


def _normalized_text(value: object) -> str:
    if value is None:
        return ''
    return ' '.join(str(value).casefold().split())


def _text_similarity_bucket(left: object, right: object) -> str:
    normalized_left = _normalized_text(left)
    normalized_right = _normalized_text(right)
    if not normalized_left and not normalized_right:
        return 'both_empty'
    if not normalized_left:
        return 'legacy_empty_gateway_present'
    if not normalized_right:
        return 'legacy_present_gateway_empty'
    if normalized_left == normalized_right:
        return 'exact_match'
    ratio = SequenceMatcher(None, normalized_left, normalized_right).ratio()
    if ratio >= 0.85:
        return 'high_similarity'
    if ratio >= 0.60:
        return 'medium_similarity'
    return 'low_similarity'


def _length_ratio_bucket(left: object, right: object) -> str:
    normalized_left = _normalized_text(left)
    normalized_right = _normalized_text(right)
    left_len = len(normalized_left)
    right_len = len(normalized_right)
    if left_len == 0 and right_len == 0:
        return 'both_empty'
    if left_len == 0:
        return 'legacy_empty_gateway_present'
    if right_len == 0:
        return 'legacy_present_gateway_empty'
    ratio = right_len / left_len
    if ratio < 0.5:
        return 'gateway_much_shorter'
    if ratio < 0.8:
        return 'gateway_shorter'
    if ratio <= 1.25:
        return 'similar_length'
    if ratio <= 2.0:
        return 'gateway_longer'
    return 'gateway_much_longer'


def _record_conversation_structure_shadow_comparison(
    gateway_response: Structured | None,
    legacy_response: Structured,
) -> None:
    if gateway_response is None:
        return

    legacy_category = getattr(legacy_response.category, 'value', legacy_response.category)
    gateway_category = getattr(gateway_response.category, 'value', gateway_response.category)

    _record_chat_extraction_comparison(
        feature=CONVERSATION_STRUCTURE_SHADOW_FEATURE,
        field='category',
        outcome='exact_match' if legacy_category == gateway_category else 'mismatch',
    )
    _record_chat_extraction_comparison(
        feature=CONVERSATION_STRUCTURE_SHADOW_FEATURE,
        field='emoji',
        outcome='exact_match' if legacy_response.emoji == gateway_response.emoji else 'mismatch',
    )
    _record_chat_extraction_comparison(
        feature=CONVERSATION_STRUCTURE_SHADOW_FEATURE,
        field='title_similarity',
        outcome=_text_similarity_bucket(legacy_response.title, gateway_response.title),
    )
    _record_chat_extraction_comparison(
        feature=CONVERSATION_STRUCTURE_SHADOW_FEATURE,
        field='overview_similarity',
        outcome=_text_similarity_bucket(legacy_response.overview, gateway_response.overview),
    )
    _record_chat_extraction_comparison(
        feature=CONVERSATION_STRUCTURE_SHADOW_FEATURE,
        field='overview_length_ratio',
        outcome=_length_ratio_bucket(legacy_response.overview, gateway_response.overview),
    )


def _count_comparison_bucket(legacy_count: int, gateway_count: int) -> str:
    if legacy_count == gateway_count:
        return 'exact_match'
    if gateway_count < legacy_count:
        return 'gateway_fewer'
    return 'gateway_more'


def _ordered_description_similarity_bucket(legacy_items: List[ActionItem], gateway_items: List[ActionItem]) -> str:
    if not legacy_items and not gateway_items:
        return 'both_empty'
    if not legacy_items:
        return 'legacy_empty_gateway_present'
    if not gateway_items:
        return 'legacy_present_gateway_empty'
    if len(legacy_items) != len(gateway_items):
        return 'count_mismatch'

    buckets = [
        _text_similarity_bucket(left.description, right.description) for left, right in zip(legacy_items, gateway_items)
    ]
    if all(bucket == 'exact_match' for bucket in buckets):
        return 'all_exact_match'
    if all(bucket in {'exact_match', 'high_similarity'} for bucket in buckets):
        return 'all_high_similarity'
    if all(bucket in {'exact_match', 'high_similarity', 'medium_similarity'} for bucket in buckets):
        return 'all_medium_similarity'
    return 'low_similarity'


def _due_at_presence_bucket(legacy_items: List[ActionItem], gateway_items: List[ActionItem]) -> str:
    if not legacy_items and not gateway_items:
        return 'both_empty'
    if len(legacy_items) != len(gateway_items):
        return 'count_mismatch'
    legacy_presence = [item.due_at is not None for item in legacy_items]
    gateway_presence = [item.due_at is not None for item in gateway_items]
    return 'exact_match' if legacy_presence == gateway_presence else 'mismatch'


def _due_at_value_bucket(legacy_items: List[ActionItem], gateway_items: List[ActionItem]) -> str:
    if not legacy_items and not gateway_items:
        return 'both_empty'
    if len(legacy_items) != len(gateway_items):
        return 'count_mismatch'

    legacy_due_at = [item.due_at for item in legacy_items]
    gateway_due_at = [item.due_at for item in gateway_items]
    if not any(legacy_due_at) and not any(gateway_due_at):
        return 'no_due_dates'
    if legacy_due_at == gateway_due_at:
        return 'exact_match'
    return 'mismatch'


def _record_conversation_action_items_shadow_comparison(
    gateway_response: ActionItemsExtraction | None,
    legacy_response: List[ActionItem],
    *,
    user_tz: Any,
    now: datetime,
) -> None:
    if gateway_response is None:
        return

    gateway_items = _coerce_action_items(gateway_response)
    _normalize_action_item_due_dates(gateway_items, user_tz=user_tz, now=now, log_past_due_clears=False)
    _record_chat_extraction_comparison(
        feature=CONVERSATION_ACTION_ITEMS_SHADOW_FEATURE,
        field='count',
        outcome=_count_comparison_bucket(len(legacy_response), len(gateway_items)),
    )
    _record_chat_extraction_comparison(
        feature=CONVERSATION_ACTION_ITEMS_SHADOW_FEATURE,
        field='description_similarity',
        outcome=_ordered_description_similarity_bucket(legacy_response, gateway_items),
    )
    _record_chat_extraction_comparison(
        feature=CONVERSATION_ACTION_ITEMS_SHADOW_FEATURE,
        field='due_at_presence',
        outcome=_due_at_presence_bucket(legacy_response, gateway_items),
    )
    _record_chat_extraction_comparison(
        feature=CONVERSATION_ACTION_ITEMS_SHADOW_FEATURE,
        field='due_at_value',
        outcome=_due_at_value_bucket(legacy_response, gateway_items),
    )


def _run_conversation_structure_shadow(
    prompt: ChatPromptTemplate, prompt_values: dict[str, Any], legacy_response: Structured
) -> None:
    gateway_chain = cast(
        Any,
        prompt | get_llm_gateway_chat_structured(cache_key='omi-transcript-structure') | parser,
    )
    gateway_response = _invoke_gateway_shadow_chain(
        gateway_chain,
        prompt_values,
        feature=CONVERSATION_STRUCTURE_SHADOW_FEATURE,
    )
    if gateway_response is not None:
        _record_conversation_structure_shadow_comparison(
            _coerce_structured(cast(Structured | StructuredExtraction, gateway_response)), legacy_response
        )


def _run_conversation_action_items_shadow(
    prompt: ChatPromptTemplate,
    prompt_values: dict[str, Any],
    legacy_response: List[ActionItem],
    user_tz: Any,
    now: datetime,
) -> None:
    gateway_chain = cast(
        Any,
        prompt
        | get_llm_gateway_chat_structured(cache_key='omi-extract-actions')
        | PydanticOutputParser(pydantic_object=ActionItemsExtraction),
    )
    gateway_response = _invoke_gateway_shadow_chain(
        gateway_chain,
        prompt_values,
        feature=CONVERSATION_ACTION_ITEMS_SHADOW_FEATURE,
    )
    _record_conversation_action_items_shadow_comparison(
        cast(Optional[ActionItemsExtraction], gateway_response),
        legacy_response,
        user_tz=user_tz,
        now=now,
    )


def _submit_llm_background(fn: Any, *args: Any) -> Any:
    from utils.executors import llm_executor, submit_with_context

    return submit_with_context(llm_executor, fn, *args)


def _submit_gateway_shadow(
    worker_fn: Any,
    feature: str,
    log_label: str,
    *args: Any,
) -> None:
    try:
        future = _submit_llm_background(worker_fn, *args)
    except Exception:
        record_chat_extraction_gateway_result(
            feature=feature,
            outcome='skipped',
            reason='submit_error',
        )
        return

    def _log_shadow_failure(completed_future: Any) -> None:
        try:
            completed_future.result()
        except Exception:
            logger.exception('%s shadow task failed', log_label)

    future.add_done_callback(_log_shadow_failure)


def _submit_conversation_structure_shadow(
    prompt: ChatPromptTemplate, prompt_values: dict[str, Any], legacy_response: Structured
) -> None:
    _submit_gateway_shadow(
        _run_conversation_structure_shadow,
        CONVERSATION_STRUCTURE_SHADOW_FEATURE,
        'conversation_structure',
        prompt,
        prompt_values,
        legacy_response,
    )


def _submit_conversation_action_items_shadow(
    prompt: ChatPromptTemplate,
    prompt_values: dict[str, Any],
    legacy_response: List[ActionItem],
    user_tz: Any,
    now: datetime,
) -> None:
    _submit_gateway_shadow(
        _run_conversation_action_items_shadow,
        CONVERSATION_ACTION_ITEMS_SHADOW_FEATURE,
        'conversation_action_items',
        prompt,
        prompt_values,
        legacy_response,
        user_tz,
        now,
    )


def should_discard_conversation(
    transcript: str, photos: Optional[List[ConversationPhoto]] = None, duration_seconds: Optional[float] = None
) -> bool:
    # If there's a long transcript, it's very unlikely we want to discard it.
    # This is a performance optimization to avoid unnecessary LLM calls.
    word_count = _word_count(transcript) if transcript and transcript.strip() else 0
    if word_count > 100:
        return False
    has_photos = photos and ConversationPhoto.photos_as_string(photos) != 'None'

    context_parts: List[str] = []
    if transcript and transcript.strip():
        context_parts.append(f"Transcript: ```{transcript.strip()}```")

    if has_photos:
        photo_descriptions = ConversationPhoto.photos_as_string(photos) if photos else 'None'
        context_parts.append(f"Photo Descriptions from a wearable camera:\n{photo_descriptions}")

    # If there is no content to process (e.g., empty transcript and no photo descriptions), discard.
    if not context_parts:
        return True

    full_context = "\n\n".join(context_parts)

    # Add duration metadata so the LLM can make duration-aware decisions
    duration_context = ""
    if duration_seconds is not None:
        duration_context = f"\nConversation duration: {int(duration_seconds)} seconds. Word count: {word_count} words."
        if duration_seconds < 120:
            duration_context += (
                "\nNote: This is a very short conversation (under 2 minutes). "
                "Apply a higher bar for keeping — only KEEP if the content is clearly actionable "
                "(a specific task, reminder, name/person, appointment, or meaningful request like 'call mom' or 'buy milk'). "
                "Generic filler words, acknowledgments, or incomplete thoughts in short conversations should be discarded."
            )

    prompt_template = '''You will receive a transcript, a series of photo descriptions from a wearable camera, or both. Your task is to decide if this content is meaningful enough to be saved as a memory.

Task: Decide if the content should be saved as conversation summary.
{duration_context}

KEEP (output: discard = False) if the content contains any of the following:
• A task, request, or action item (e.g., "call John before 5", "buy groceries", "remind me to email Sarah").
• A decision, commitment, or plan.
• A question that requires follow-up.
• Personal facts, preferences, or details likely useful later (e.g., remembering a person, place, or object).
• An important event, social interaction, or significant moment with meaningful context or consequences.
• An insight, summary, or key takeaway that provides value.
• A visually significant scene (e.g., a whiteboard with notes, a document, a memorable view, a person's face).

DISCARD (output: discard = True) if the content is:
• Trivial conversation snippets (e.g., brief apologies, casual remarks, single-sentence comments without context).
• Very brief interactions (5-10 seconds) that lack actionable content or meaningful context.
• Casual acknowledgments, greetings, or passing comments that don't contain useful information (e.g., "okay", "hmm", "yeah sure", "sorry", "hello", "alright").
• Incomplete or fragmented speech that doesn't convey a clear meaning.
• Blurry photos, uninteresting scenery with no context, or content that doesn't meet the KEEP criteria above.
• Feels like asking Siri or other AI assistant something in 1-2 sentences or using voice to type something in a chat for 5-10 seconds.

Return exactly one line:
discard = <True|False>

Content:
{full_context}

{format_instructions}'''.replace(
        '    ', ''
    ).strip()
    custom_parser = PydanticOutputParser(pydantic_object=DiscardConversation)
    prompt_values = {
        'full_context': full_context,
        'duration_context': duration_context,
        'format_instructions': custom_parser.get_format_instructions(),
    }

    prompt = cast(Any, ChatPromptTemplate).from_messages([prompt_template])
    chain = prompt | get_llm('conv_discard') | custom_parser
    try:
        response: DiscardConversation = chain.invoke(prompt_values)
        return response.discard

    except Exception as e:
        logger.error(f'Error determining memory discard: {e}')
        return False


# =============================================
#       SHARED CONVERSATION CONTEXT BUILDER
# =============================================


def _build_conversation_context(
    transcript: str,
    photos: Optional[List[ConversationPhoto]] = None,
    calendar_meeting_context: Optional['CalendarMeetingContext'] = None,
) -> str:
    """Build the conversation context string shared across LLM prompts.

    Produces a deterministic string from transcript, photos, and calendar context.
    Used as the second system message (after static instructions) so that the static
    instruction prefix enables cross-conversation OpenAI prompt caching.

    Returns:
        Formatted context string, or empty string if no content provided.
    """
    context_parts: List[str] = []

    if calendar_meeting_context:
        participants_str = ", ".join(
            [
                f"{p.name} <{p.email}>" if p.name and p.email else p.name or p.email or "Unknown"
                for p in calendar_meeting_context.participants
            ]
        )
        calendar_context_str = f"""
CALENDAR MEETING CONTEXT:
- Meeting Title: {calendar_meeting_context.title}
- Scheduled Time: {calendar_meeting_context.start_time.strftime('%Y-%m-%d %H:%M UTC')}
- Duration: {calendar_meeting_context.duration_minutes} minutes
- Platform: {calendar_meeting_context.platform or 'Not specified'}
- Participants: {participants_str or 'None listed'}
{f'- Meeting Notes: {calendar_meeting_context.notes}' if calendar_meeting_context.notes else ''}
{f'- Meeting Link: {calendar_meeting_context.meeting_link}' if calendar_meeting_context.meeting_link else ''}
""".strip()
        context_parts.append(calendar_context_str)

    if transcript and transcript.strip():
        context_parts.append(f"Transcript: ```{transcript.strip()}```")

    if photos:
        photo_descriptions = ConversationPhoto.photos_as_string(photos)
        if photo_descriptions != 'None':
            context_parts.append(f"Photo Descriptions from a wearable camera:\n{photo_descriptions}")

    return "\n\n".join(context_parts)


def extract_action_items(
    transcript: str,
    started_at: datetime,
    language_code: str,
    tz: str,
    photos: Optional[List[ConversationPhoto]] = None,
    existing_action_items: Optional[List[Dict[str, Any]]] = None,
    calendar_meeting_context: Optional['CalendarMeetingContext'] = None,
    output_language_code: Optional[str] = None,
    user_name: Optional[str] = 'User',
) -> List[ActionItem]:
    """
    Dedicated function to extract action items from conversation content.

    Args:
        transcript: Conversation transcript
        started_at: When the conversation started
        language_code: Language code for the conversation
        tz: User's timezone
        photos: Optional conversation photos
        existing_action_items: Open action items semantically related to this
            conversation (top vector matches, recently active). Caller is
            expected to pre-filter to open items only; this function defends
            in depth by skipping any item that arrives marked completed.

    Returns:
        List of extracted ActionItem objects
    """
    conversation_context = _build_conversation_context(transcript, photos, calendar_meeting_context)
    if not conversation_context:
        return []

    existing_items_context = ""
    if existing_action_items:
        items_list: List[str] = []
        for item in existing_action_items:
            # Defensive: the rendered section is "OPEN TASKS"; a completed item
            # leaking through (e.g. a future caller that doesn't pre-filter)
            # would mislead the LLM into suppressing valid new tasks.
            if item.get('completed', False):
                continue
            desc = item.get('description', '')
            due = item.get('due_at')
            due_str = due.strftime('%Y-%m-%d %H:%M UTC') if due else 'No due date'
            items_list.append(f"  • {desc} (Due: {due_str})")

        if items_list:
            existing_items_context = (
                f"\n\nPOTENTIALLY RELATED OPEN TASKS — recently active, semantically similar ({len(items_list)} items):\n"
                + "\n".join(items_list)
            )

    # First system message: task-specific instructions (static prefix enables cross-conversation caching)
    # NOTE: {language_code} is in the context message, not here, to keep this prefix fully static across all languages.
    instructions_text = '''You are an expert action item extractor. Your sole purpose is to identify and extract high-quality, actionable tasks from the provided content.

    CRITICAL: If CALENDAR MEETING CONTEXT is provided with participant names, you MUST use those names:
    - The conversation DEFINITELY happened between the named participants
    - NEVER use "Speaker 0", "Speaker 1", "Speaker 2", etc. when participant names are available
    - Match transcript speakers to participant names by analyzing the conversation context
    - Use participant names in ALL action items (e.g., "Follow up with Sarah" NOT "Follow up with Speaker 0")
    - Reference the meeting title/context when relevant to the action item
    - Consider the scheduled meeting time and duration when extracting due dates
    - If you cannot confidently match a speaker to a name, use the action description without speaker references

    DEDUPLICATION RULES — be conservative about suppressing:
    • The "POTENTIALLY RELATED OPEN TASKS" section lists open items recently active in the user's task list, semantically similar to this conversation. They may or may not be true duplicates.
    • Only suppress a candidate if you are 100% confident the existing task captures this EXACT intent and the user is just re-mentioning it (not re-doing it).
    • EXTRACT (do not suppress) when the user signals re-occurrence or distinct scope:
      - Re-occurrence cues: "again", "another", "still need to", "I forgot to", "more", "one more"
      - Different person, scope, or deadline ("Submit report by March 1" vs "Submit report by April 15" — different deadlines, both valid)
      - Existing item describes a one-off task that's already in progress; user is starting a new instance
    • If user says "I did X" / "I just X'd" / "X is done" / "X is taken care of": DO NOT extract a new item AND do not modify the existing one — just leave it (auto-completion of existing tasks is out of scope here).
    • Examples of true DUPLICATES (suppress):
      - "Call John" said today, existing open "Call John" from this morning, no new context → DUPLICATE
      - "Email Sarah about meeting" said today, existing "Email Sarah about meeting" still open → DUPLICATE (same intent re-mentioned)
    • Examples of NOT duplicates (extract anyway):
      - Existing: "Buy milk" (open). User says "I need to buy more milk" → EXTRACT (re-occurrence cue)
      - Existing: "Submit report by March 1" (open). User says "Submit report by April 15" → EXTRACT (different deadline)
      - Existing: "Call dentist" (open). User says "Call plumber" → EXTRACT (different scope)
    • When unsure → EXTRACT. A duplicate the user can delete is recoverable; a silently-suppressed real task is not.
    • SINGLE-TOPIC LIMIT: Within THIS conversation, extract AT MOST 1 action item per topic — not one per variation, option, or detail. (This rule applies within the current transcript, not across conversations.)

    WORKFLOW:
    1. FIRST: Read the ENTIRE conversation carefully to understand the full context
    2. SECOND: Identify all topics, people, places, or things being discussed
    3. THIRD: Default to extracting NOTHING. Filter aggressively:
       - Is the user ALREADY doing this or about to do it? SKIP IT
       - Is this being handled in real-time between the participants? SKIP IT
       - Would a busy person genuinely forget this without a reminder? If not OBVIOUS, SKIP IT
       - NEVER extract multiple items about the same topic from a single conversation
       - When in doubt, extract 0 items. One missed marginal task is far better than multiple garbage tasks.
    4. FOURTH: Extract ONLY action items that passed step 3, using specific names/details
    5. FIFTH: Extract timing information separately and put it in the due_at field
    6. SIXTH: Clean the description - remove ALL time references and vague words
    7. SEVENTH: Final check - description should be timeless and specific (e.g., "Buy groceries" NOT "buy them by tomorrow")

    CRITICAL CONTEXT:
    • These action items are primarily for the PRIMARY USER who is having/recording this conversation
    • The primary user's name is {user_name}
    • The user is the person wearing the device or initiating the conversation
    • Focus on tasks the primary user needs to track and act upon
    • Include tasks for OTHER people ONLY if:
      - The primary user is dependent on that task being completed
      - It's super crucial for the primary user to track it
      - The primary user needs to follow up on it

    QUALITY OVER QUANTITY:
    • Better to have 0 action items than to flood the user with unnecessary ones
    • Only extract action items that are truly important and need tracking
    • When in doubt, DON'T extract - be conservative and selective
    • Think: "Would a busy person want to be reminded of this?"

    STRICT FILTERING RULES - Include ONLY tasks that meet ALL these criteria:

    1. **Clear Ownership & Relevance to Primary User**:
       - Identify which speaker is the primary user based on conversational context
       - Look for cues: who is asking questions, who is receiving advice/tasks, who initiates topics
       - For tasks assigned to the primary user: phrase them directly (start with verb)
       - For tasks assigned to others: include them ONLY if primary user is dependent on them or needs to track them
       - **CRITICAL**: When CALENDAR MEETING CONTEXT provides participant names:
         * Analyze the transcript to match speakers to the named participants
         * Use the actual participant names in ALL action items
         * ABSOLUTELY NEVER use "Speaker 0", "Speaker 1", "Speaker 2", etc.
         * Example: "Follow up with Sarah about budget" NOT "Follow up with Speaker 0 about budget"
       - If no calendar context: NEVER use "Speaker 0", "Speaker 1", etc. in the final action item description
       - If unsure about names, use natural phrasing like "Follow up on...", "Ensure...", etc.

    2. **Concrete Action**: The task describes a specific, actionable next step (not vague intentions)

    3. **Timing Signal**: The task includes a timing cue:
       - Explicit dates or times
       - Relative timing ("tomorrow", "next week", "by Friday", "this month")
       - Urgency markers ("urgent", "ASAP", "high priority")

    4. **Real Importance**: The task has genuine consequences if missed:
       - Financial impact (bills, payments, purchases, invoices)
       - Health/safety concerns (appointments, medications, safety checks)
       - Hard deadlines (submissions, filings, registrations)
       - Explicit stress if missed (stated by speakers)
       - Critical dependencies (primary user blocked without it)
       - Commitments to other people (meetings, deliverables, promises)

    5. **NOT Already Being Done or About to Do Immediately**:
       - Skip if user is currently doing it, about to do it, or handling it in this conversation
       - "I'm going to X" → SKIP (about to do it right now)
       - "I'll do X for you" → SKIP (immediate response to a request)
       - "Let me X" → SKIP (taking action now)
       - "Today I will X" → SKIP unless there's a specific time/deadline attached
       - "I want to X" → SKIP unless paired with a concrete deadline
       - Only EXTRACT if there's a real future deadline that could be forgotten:
         * "I need to submit the report by Friday" → EXTRACT (forgettable deadline)
         * "Call the dentist tomorrow" → EXTRACT (future deadline)
         * "Don't forget to pay rent by the 1st" → EXTRACT (financial deadline)

    EXCLUDE these types of items (be aggressive about exclusion):
    • Things user is ALREADY doing or actively working on
    • Casual mentions or updates ("I'm working on X", "currently doing Y")
    • Vague suggestions without commitment ("we should grab coffee sometime", "let's meet up soon")
    • Casual mentions without commitment ("maybe I'll check that out")
    • General goals without specific next steps ("I need to exercise more")
    • Past actions being discussed
    • Hypothetical scenarios ("if we do X, then Y")
    • Trivial tasks with no real consequences
    • Tasks assigned to others that don't impact the primary user
    • Routine daily activities the user already knows about
    • Things that are obvious or don't need a reminder
    • Updates or status reports about ongoing work
    • Conversations where the action is being completed in real-time between the participants
    • Back-and-forth clarification or decision-making about something happening right now
    • Requests and responses between people who are together and handling the matter on the spot
    • If the entire conversation is a brief in-person exchange that will be resolved within minutes, extract 0 items

    FORMAT REQUIREMENTS:
    • Keep each action item SHORT and concise (maximum 15 words, strict limit)
    • Use clear, direct language
    • Start with a verb when possible (e.g., "Call", "Send", "Review", "Pay", "Open", "Submit", "Finish", "Complete")
    • Include only essential details

    • CRITICAL - Resolve ALL vague references:
      - Read the ENTIRE conversation to understand what is being discussed
      - If you see vague references like:
        * "the feature" → identify WHAT feature from conversation
        * "this project" → identify WHICH project from conversation
        * "that task" → identify WHAT task from conversation
        * "it" → identify what "it" refers to from conversation
      - Look for keywords, topics, or subjects mentioned earlier in the conversation
      - Replace ALL vague words with specific names from the conversation context
      - Examples:
        * User says: "planning Sarah's birthday party" then later "buy decorations for it"
          → Extract: "Buy decorations for Sarah's birthday party"
        * User says: "car making weird noise" then later "take it to mechanic"
          → Extract: "Take car to mechanic"
        * User says: "quarterly sales report" then later "send it to the team"
          → Extract: "Send quarterly sales report to team"

    • CRITICAL - Remove time references from description (they go in due_at field):
      - NEVER include timing words in the action item description itself
      - Remove: "by tomorrow", "by evening", "today", "next week", "by Friday", etc.
      - The timing information is captured in the due_at field separately
      - Focus ONLY on the action and what needs to be done
      - Examples:
        * "buy groceries by tomorrow" → "Buy groceries"
        * "call dentist by next Monday" → "Call dentist"
        * "pay electricity bill by Friday" → "Pay electricity bill"
        * "submit insurance claim today" → "Submit insurance claim"
        * "book flight tickets by evening" → "Book flight tickets"

    • Remove filler words and unnecessary context
    • Merge duplicates
    • Order by: due date → urgency → alphabetical

    DUE DATE EXTRACTION:
    Resolve each due date in the user's LOCAL time. NEVER produce a past date.

    REFERENCE_TIME (user's local time): If {started_at_local} is >7 days before {current_time_local}, use {current_time_local} (historical reprocessing). Otherwise use {started_at_local}.

    Date resolution: "today" → REFERENCE_TIME date, "tomorrow" → next day, weekday names → next occurrence, "next week" → +7 days.
    Time resolution: "morning" → 9AM, "afternoon" → 2PM, "evening" → 6PM, "noon" → 12PM, "end of day"/"midnight" → 11:59PM, no time → 11:59PM. "urgent"/"ASAP" → 2h from REFERENCE_TIME.
    Output the resolved value as the user's LOCAL wall-clock time in ISO 8601 with NO timezone suffix or offset (no 'Z', no '+05:30') — the server converts it to UTC. Verify it is in the future relative to REFERENCE_TIME; if past, omit due_at.

    Example: REFERENCE_TIME "2025-10-03T13:25:00", "tomorrow before 10am" → "2025-10-04T10:00:00"
    Format: naive local ISO 8601, no suffix (e.g., "2025-10-04T10:00:00").

    Conversation started at (local): {started_at_local}
    Current time (local): {current_time_local}
    User timezone: {tz}

    {format_instructions}'''.replace(
        '    ', ''
    ).strip()

    response_language = output_language_code or language_code
    action_items_parser = PydanticOutputParser(pydantic_object=ActionItemsExtraction)
    # Second system message: conversation context + existing items (dynamic, per-conversation)
    context_message = 'The content language is {language_code}. You MUST respond entirely in {response_language}.\n\nContent:\n{conversation_context}{existing_items_context}'
    prompt = cast(Any, ChatPromptTemplate).from_messages([('system', instructions_text), ('system', context_message)])
    chain = prompt | get_llm('conv_action_items', cache_key='omi-extract-actions') | action_items_parser

    current_time = datetime.now(timezone.utc)

    # Resolve the user's timezone once; fall back to UTC on an invalid/missing tz (and log it).
    # The LLM emits naive LOCAL wall-clock due dates (see prompt); we convert them to UTC here
    # deterministically instead of trusting the model to do the timezone math (the cause of #7059).
    try:
        user_tz = ZoneInfo(tz) if tz else timezone.utc
    except Exception:
        logger.warning(f'Invalid timezone {tz!r} for action item extraction; falling back to UTC')
        user_tz = timezone.utc

    started_at_local = (started_at if started_at.tzinfo else started_at.replace(tzinfo=timezone.utc)).astimezone(
        user_tz
    )
    current_time_local = current_time.astimezone(user_tz)
    prompt_values = {
        'conversation_context': conversation_context,
        'format_instructions': action_items_parser.get_format_instructions(),
        'language_code': language_code,
        'response_language': response_language,
        'started_at_local': started_at_local.replace(tzinfo=None).isoformat(),
        'current_time_local': current_time_local.replace(tzinfo=None).isoformat(),
        'tz': tz or 'UTC',
        'existing_items_context': existing_items_context,
        'user_name': user_name or 'User',
    }

    try:
        response = chain.invoke(prompt_values)
        action_items = _coerce_action_items(response)

        # Set created_at for action items if not already set
        now = current_time
        for action_item in action_items:
            if action_item.created_at is None:
                action_item.created_at = now
        # The LLM returns naive LOCAL time; convert to UTC deterministically (and normalize any
        # tz-aware value), then clear due dates more than 1 day in the past.
        _normalize_action_item_due_dates(action_items, user_tz=user_tz, now=now, log_past_due_clears=True)

        if _should_run_conversation_action_items_shadow('conversation_action_items', started_at, conversation_context):
            _submit_conversation_action_items_shadow(prompt, prompt_values, action_items, user_tz, now)

        return action_items

    except Exception as e:
        logger.error(f'Error extracting action items: {e}')
        return []


def _local_started_at_iso(started_at: datetime, tz: Optional[str]) -> str:
    """Render the capture time as the user's local wall-clock for prompt date context (#4773).

    The LLM is unreliable at converting UTC to the user's timezone, which mislabels the time of day
    in titles and overviews. Convert deterministically here instead. Naive datetimes are treated as
    UTC; a missing or invalid timezone falls back to UTC.
    """
    try:
        user_tz = ZoneInfo(tz) if tz else timezone.utc
    except Exception:  # noqa: BLE001 - any unknown/invalid tz falls back to UTC
        user_tz = timezone.utc
    aware = started_at if started_at.tzinfo is not None else started_at.replace(tzinfo=timezone.utc)
    return aware.astimezone(user_tz).replace(tzinfo=None).isoformat()


def get_transcript_structure(
    transcript: str,
    started_at: datetime,
    language_code: str,
    tz: str,
    uid: str,
    photos: Optional[List[ConversationPhoto]] = None,
    calendar_meeting_context: Optional['CalendarMeetingContext'] = None,
    output_language_code: Optional[str] = None,
) -> Structured:
    conversation_context = _build_conversation_context(transcript, photos, calendar_meeting_context)
    if not conversation_context:
        return Structured()  # Should be caught by discard logic, but as a safeguard.

    response_language = output_language_code or language_code

    # First system message: task-specific instructions (static prefix enables cross-conversation caching)
    # NOTE: language instructions are in context_message (second message) to keep this prefix fully static.
    instructions_text = '''You are an expert content analyzer. Your task is to analyze the provided content (which could be a transcript, a series of photo descriptions from a wearable camera, or both) and provide structure and clarity.

    CRITICAL: If CALENDAR MEETING CONTEXT is provided with participant names, you MUST use those names:
    - The conversation DEFINITELY happened between the named participants
    - NEVER use "Speaker 0", "Speaker 1", "Speaker 2", etc. when participant names are available
    - Match transcript speakers to participant names by carefully analyzing the conversation context
    - Use participant names throughout the title, overview, and all generated content
    - Use the meeting title as a strong signal for the conversation title (but you can refine it based on the actual discussion)
    - Use the meeting platform and scheduled time to provide better context in the overview
    - Consider the meeting notes/description when analyzing the conversation's purpose
    - If there are 2-3 participants with known names, naturally mention them in the title (e.g., "Sarah and John Discuss Q2 Budget", "Team Meeting with Alex, Maria, and Chris")

    For the title, Write a clear, compelling headline (≤ 10 words) that captures the central topic and outcome. Use Title Case, avoid filler words, and include a key noun + verb where possible (e.g., "Team Finalizes Q2 Budget" or "Family Plans Weekend Road Trip"). If calendar context provides participant names (2-3 people), naturally include them when relevant (e.g., "John and Sarah Plan Marketing Campaign").
    For the overview, condense the content into a summary with the main topics discussed or scenes observed, making sure to capture the key points and important details. When calendar context provides participant names, you MUST use their actual names instead of "Speaker 0" or "Speaker 1" to make the summary readable and personal. Analyze the transcript to understand who said what and match speakers to participant names.
    For the emoji, select a single emoji that vividly reflects the core subject, mood, or outcome of the content. Strive for an emoji that is specific and evocative, rather than generic (e.g., prefer 🎉 for a celebration over 👍 for general agreement, or 💡 for a new idea over 🧠 for general thought).

    For the category, classify the content into one of the available categories.

    For Calendar Events, apply strict filtering to include ONLY events that meet ALL these criteria:
    • **Confirmed commitment**: Not suggestions or "maybe" - actual scheduled events
    • **User involvement**: The user is expected to attend, participate, or take action
    • **Specific timing**: Has concrete date/time, not vague references like "sometime" or "soon"
    • **Important/actionable**: Missing it would have real consequences or impact

    INCLUDE these event types:
    • Meetings & appointments (business meetings, doctor visits, interviews)
    • Hard deadlines (project due dates, payment deadlines, submission dates)
    • Personal commitments (family events, social gatherings user committed to)
    • Travel & transportation (flights, trains, scheduled pickups)
    • Recurring obligations (classes, regular meetings, scheduled calls)

    EXCLUDE these:
    • Casual mentions ("we should meet sometime", "maybe next week")
    • Historical references (past events being discussed)
    • Other people's events (events user isn't involved in)
    • Vague suggestions ("let's grab coffee soon")
    • Hypothetical scenarios ("if we meet Tuesday...")

    For date context, this content was captured at {started_at}, which is already the user's local time ({tz}). Interpret it as-is and describe times of day in the title and overview accordingly; do not re-interpret this timestamp as UTC.

    {format_instructions}'''.replace(
        '    ', ''
    ).strip()

    # Second system message: conversation context (dynamic, per-conversation)
    context_message = 'The content language is {language_code}. You MUST respond entirely in {response_language}.\n\nContent:\n{conversation_context}'
    prompt = cast(Any, ChatPromptTemplate).from_messages([('system', instructions_text), ('system', context_message)])
    chain = prompt | get_llm('conv_structure', cache_key='omi-transcript-structure') | parser
    legacy_prompt_values = {
        'conversation_context': conversation_context,
        'format_instructions': parser.get_format_instructions(),
        'language_code': language_code,
        'response_language': response_language,
        'started_at': _local_started_at_iso(started_at, tz),
        'tz': tz or 'UTC',
    }

    response = _coerce_structured(chain.invoke(legacy_prompt_values))
    if _should_run_conversation_structure_shadow(uid, started_at, conversation_context):
        _submit_conversation_structure_shadow(
            prompt,
            legacy_prompt_values,
            response,
        )

    for event in response.events or []:
        if event.duration > 180:
            event.duration = 180
        event.created = False

    return response


def get_reprocess_transcript_structure(
    transcript: str,
    started_at: datetime,
    language_code: str,
    tz: str,
    title: str,
    photos: Optional[List[ConversationPhoto]] = None,
    output_language_code: Optional[str] = None,
) -> Structured:
    context_parts: List[str] = []
    if transcript and transcript.strip():
        context_parts.append(f"Transcript: ```{transcript.strip()}```")

    if photos:
        photo_descriptions = ConversationPhoto.photos_as_string(photos)
        if photo_descriptions != 'None':
            context_parts.append(f"Photo Descriptions from a wearable camera:\n{photo_descriptions}")

    if not context_parts:
        return Structured()

    full_context = "\n\n".join(context_parts)
    response_language = output_language_code or language_code

    prompt_text = '''You are an expert content analyzer. Your task is to analyze the provided content (which could be a transcript, a series of photo descriptions from a wearable camera, or both) and provide structure and clarity.
    The content language is {language_code}. You MUST respond entirely in {response_language}.

    For the title, use ```{title}```, if it is empty, use the main topic of the content.
    For the overview, condense the content into a summary with the main topics discussed or scenes observed, making sure to capture the key points and important details.
    For the emoji, select a single emoji that vividly reflects the core subject, mood, or outcome of the content. Strive for an emoji that is specific and evocative, rather than generic (e.g., prefer 🎉 for a celebration over 👍 for general agreement, or 💡 for a new idea over 🧠 for general thought).

    For the category, classify the content into one of the available categories.

    For Calendar Events, apply strict filtering to include ONLY events that meet ALL these criteria:
    • **Confirmed commitment**: Not suggestions or "maybe" - actual scheduled events
    • **User involvement**: The user is expected to attend, participate, or take action
    • **Specific timing**: Has concrete date/time, not vague references like "sometime" or "soon"
    • **Important/actionable**: Missing it would have real consequences or impact
    
    INCLUDE these event types:
    • Meetings & appointments (business meetings, doctor visits, interviews)
    • Hard deadlines (project due dates, payment deadlines, submission dates)
    • Personal commitments (family events, social gatherings user committed to)
    • Travel & transportation (flights, trains, scheduled pickups)
    • Recurring obligations (classes, regular meetings, scheduled calls)
    
    EXCLUDE these:
    • Casual mentions ("we should meet sometime", "maybe next week")
    • Historical references (past events being discussed)
    • Other people's events (events user isn't involved in)
    • Vague suggestions ("let's grab coffee soon")
    • Hypothetical scenarios ("if we meet Tuesday...")
    
    For date context, this content was captured at {started_at}, which is already the user's local time ({tz}). Interpret it as-is and describe times of day in the title and overview accordingly; do not re-interpret this timestamp as UTC.

    Content:
    {full_context}

    {format_instructions}'''.replace(
        '    ', ''
    ).strip()

    prompt = cast(Any, ChatPromptTemplate).from_messages([('system', prompt_text)])
    chain = prompt | get_llm('conv_structure', cache_key='omi-transcript-structure') | parser

    response = _coerce_structured(
        chain.invoke(
            {
                'full_context': full_context,
                'title': title,
                'format_instructions': parser.get_format_instructions(),
                'language_code': language_code,
                'response_language': response_language,
                'started_at': _local_started_at_iso(started_at, tz),
                'tz': tz or 'UTC',
            }
        )
    )

    for event in response.events or []:
        if event.duration > 180:
            event.duration = 180
        event.created = False

    return response


def get_app_result(transcript: str, photos: List[ConversationPhoto], app: App, language_code: str = 'en') -> str:
    context_parts: List[str] = []
    if transcript and transcript.strip():
        context_parts.append(f"Transcript: ```{transcript.strip()}```")

    if photos:
        photo_descriptions = ConversationPhoto.photos_as_string(photos)
        if photo_descriptions != 'None':
            context_parts.append(f"Photo Descriptions from a wearable camera:\n{photo_descriptions}")

    if not context_parts:
        return ""

    full_context = "\n\n".join(context_parts)

    prompt = f'''
    You are an AI with the following characteristics:
    Name: {app.name},
    Description: {app.description},
    Task: ${app.memory_prompt}

    Language: The conversation language is {language_code}. Use the same language {language_code} for your response.

    Conversation:
    {full_context}
    '''

    response = get_llm('conv_app_result', cache_key='omi-app-result').invoke(prompt)
    content = _content_str(response).replace('```json', '').replace('```', '')
    return content


class SuggestedAppsSelection(BaseModel):
    suggested_apps: List[str] = Field(
        description='List of up to 3 app IDs that are most suitable for processing this conversation, ordered by relevance. Empty list if none are suitable.'
    )
    reasoning: str = Field(
        description='Brief explanation of why these apps were selected based on the conversation content.'
    )


class BestAppSelection(BaseModel):
    app_id: str = Field(
        description='The ID of the best app for processing this conversation, or an empty string if none are suitable.'
    )


def get_suggested_apps_for_conversation(conversation: Conversation, apps: List[App]) -> Tuple[List[str], str]:
    """
    Get top 3 suggested apps for the given conversation based on its structured content
    and the specific task/outcome each app provides.
    Returns tuple of (suggested_app_ids, reasoning)
    """
    if not apps:
        return [], "No apps available"

    if not conversation.structured:
        return [], "No structured content available"

    structured_data = conversation.structured
    conversation_details = f"""
    Title: {structured_data.title or 'N/A'}
    Category: {structured_data.category.value if structured_data.category else 'N/A'}
    Overview: {structured_data.overview or 'N/A'}
    Action Items: {ActionItem.actions_to_string(structured_data.action_items) if structured_data.action_items else 'None'}
    Events Mentioned: {Event.events_to_string(structured_data.events) if structured_data.events else 'None'}
    """

    apps_xml = "<apps>\n"
    for app in apps:
        apps_xml += f"""  <app>
    <id>{app.id}</id>
    <name>{app.name}</name>
    <description>{app.description}</description>
    <memory_prompt>{app.memory_prompt}</memory_prompt>
  </app>\n"""
    apps_xml += "</apps>"

    prompt = f"""
    You are an expert app recommendation system. Your goal is to suggest the top 3 most suitable apps for processing the given conversation based on the conversation's structured content and each app's specific capabilities.

    <conversation_details>
    {conversation_details.strip()}
    </conversation_details>

    <available_apps>
    {apps_xml.strip()}
    </available_apps>

    Task:
    1. Analyze the conversation's structured content: title, category, overview, action items, and events.
    2. For each app, evaluate how well its description and memory_prompt align with the conversation's content and themes.
    3. Consider the potential value and relevance of each app's output for this specific conversation.
    4. Select up to 3 apps that would provide the most meaningful and valuable analysis, ordered by relevance (most relevant first).

    Selection Criteria:
    - **Content Alignment**: App's purpose should directly relate to the conversation's topics, category, or themes
    - **Value Potential**: App should be able to extract meaningful insights from this specific conversation
    - **Specificity**: Prefer apps with specific, targeted functionality over generic ones
    - **Actionability**: Prioritize apps that can provide actionable insights or useful analysis

    Quality Standards:
    - Only suggest apps that have clear relevance to the conversation content
    - If fewer than 3 apps are truly suitable, suggest only the relevant ones
    - If no apps are genuinely suitable, return an empty list
    - Do not force matches - quality over quantity

    Provide your suggestions with brief reasoning explaining why these apps are most suitable for this conversation.
    """

    try:
        with_parser = get_llm('conv_app_select').with_structured_output(SuggestedAppsSelection)
        response: SuggestedAppsSelection = cast(SuggestedAppsSelection, with_parser.invoke(prompt))

        # Validate that suggested app IDs exist in the available apps
        valid_app_ids = {app.id for app in apps}
        suggested_apps = [app_id for app_id in response.suggested_apps if app_id in valid_app_ids]

        return suggested_apps, response.reasoning

    except Exception as e:
        logger.error(f"Error getting suggested apps: {e}")
        return [], f"Error in app suggestion: {str(e)}"


def select_best_app_for_conversation(conversation: Conversation, apps: List[App]) -> Optional[App]:
    """
    Select the best app for the given conversation based on its structured content
    and the specific task/outcome each app provides.
    """
    if not apps:
        return None

    if not conversation.structured:
        return None

    structured_data = conversation.structured
    conversation_details = f"""
    Title: {structured_data.title or 'N/A'}
    Category: {structured_data.category.value if structured_data.category else 'N/A'}
    Overview: {structured_data.overview or 'N/A'}
    Action Items: {ActionItem.actions_to_string(structured_data.action_items) if structured_data.action_items else 'None'}
    Events Mentioned: {Event.events_to_string(structured_data.events) if structured_data.events else 'None'}
    """

    apps_xml = "<apps>\n"
    for app in apps:
        apps_xml += f"""  <app>
    <id>{app.id}</id>
    <category>{app.category}</category>
    <description>{app.description}</description>
  </app>\n"""
    apps_xml += "</apps>"

    prompt = f"""
    You are an expert app selector. Your goal is to determine the single best app for processing the given conversation based on the conversation's structured content and each app's specific capabilities.

    <conversation_details>
    {conversation_details.strip()}
    </conversation_details>

    <available_apps>
    {apps_xml.strip()}
    </available_apps>

    Task:
    1. Analyze the conversation's structured content: title, category, overview, action items, and events.
    2. For each app, evaluate how well its description and category align with the conversation's content.
    3. Determine which single app would provide the most meaningful, relevant, and valuable analysis for this specific conversation.
    4. Select the app whose capabilities best match the conversation's themes and content.

    Critical Instructions:
    - Only select an app if its specific capabilities are highly relevant to the conversation's content and themes
    - Consider the potential value and actionability of the app's output for this conversation
    - If no app is genuinely suitable for this conversation, return an empty app_id
    - Do not force a match - it's better to return empty than select an inappropriate app
    - Focus on quality and relevance over generic applicability

    Provide ONLY the app_id of the best matching app, or an empty string if no app is suitable.
    """

    try:
        with_parser = get_llm('conv_app_select').with_structured_output(BestAppSelection)
        response: BestAppSelection = cast(BestAppSelection, with_parser.invoke(prompt))
        selected_app_id = response.app_id

        if not selected_app_id or selected_app_id.strip() == "":
            return None

        # Find the app object with the matching ID
        selected_app = next((app for app in apps if app.id == selected_app_id), None)
        if selected_app:
            return selected_app
        else:
            return None

    except Exception as e:
        logger.error(f"Error selecting best app: {e}")
        return None


def generate_summary_with_prompt(conversation_text: str, prompt: str, language_code: str = 'en') -> str:
    # Build prompt matching the app processing format (without forced "be concise" constraint)
    full_prompt = f"""
    Your task is: {prompt}

    Language: The conversation language is {language_code}. Use the same language {language_code} for your response.

    The conversation is:
    {conversation_text}
    """
    response = get_llm('daily_summary', cache_key='omi-daily-summary').invoke(full_prompt)
    return _content_str(response)

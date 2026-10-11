import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from importlib import import_module
from zoneinfo import ZoneInfo
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, TYPE_CHECKING, cast

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from models.app import App
from models.calendar_context import CalendarMeetingContext
from models.conversation import Conversation
from models.conversation_photo import ConversationPhoto
from models.structured import ActionItem, Event, Structured
from models.structured_extraction import (
    RichStructuredExtraction,
    StructuredExtraction,
)
from .clients import get_llm, get_llm_gateway_chat_structured, parser
from .discard_parser import DiscardConversation, LenientDiscardParser
from .gateway_error_contract import is_byok_rate_limit_gateway_error
from utils.byok import has_byok_keys
from utils.conversations.meeting_participants import MeetingRoster

if TYPE_CHECKING:
    from utils.conversations.episode_evidence import EvidenceItem

from utils.llm.conversation_notes_prompts import (
    conversation_notes_volatile_instructions as _conversation_notes_volatile_instructions,
    conversation_notes_static_instructions as _conversation_notes_static_instructions,
    conversation_note_density,
)
from utils.conversations.wake_word import (
    WAKE_WORD_DISCARD_PROMPT_RULES,
    WAKE_WORD_PROMPT_RULES,
    has_structural_wake_word_marker,
)
from utils.conversations.relevance_rules import KEEP_WORD_COUNT, transcript_word_count
from utils.conversations.summary_selection import render_sections_markdown
from utils.llm.action_item_normalization import normalize_action_item_due_dates as _normalize_action_item_due_dates
from utils.llm.meeting_notes_rich_prompts import NotesFrameImage, rich_static_instructions, screen_frames_message
from utils.llm.meeting_notes_rich_prompts import rich_volatile_instructions
from utils.llm.conversation_title_people import general_title_static_instructions, title_people_block
from utils.llm.meeting_notes_presentation import (
    enforce_conversation_note_presentation,
    enforce_static_conversation_note_presentation,
)
from utils.llm.meeting_notes_validation import (
    enforce_structured_presentation_contract,
    sanitize_structured_speaker_placeholders,
    strip_speaker_placeholders,
    validate_rich_meeting_notes,
    validate_structured_source_segment_ids,
)
from utils.llm.notes_observability import current_run, observe_notes
from utils.llm.shaped_agent import Budget, Mount, Turn, route_for_uid, run_loop
from utils.llm.shaped_notes_transport import isolated_notes_model
from utils.llm.model_config import FOREGROUND_REQUEST_TIMEOUT_SECONDS
from utils.llm.prompt_cache import (
    EXPLICIT_CACHE_MINIMUM_TOKENS,
    EXPLICIT_CACHE_OPTIONS,
    has_cacheable_prefix,
    marked_prefix_request,
    prefix_cache_key,
)
from utils.llm.conversation_prompt_context import ConversationPromptPrefix
from utils.llm.conversation_prompt_prefix import shared_conversation_cache_supported

try:
    from utils.llm.gateway_client import should_route_features_through_gateway
except ImportError:  # pragma: no cover - isolated legacy tests provide only the shadow seam

    def should_route_features_through_gateway() -> bool:
        return False


logger = logging.getLogger(__name__)
GPT56_EXPLICIT_CACHE_OPTIONS = EXPLICIT_CACHE_OPTIONS
CONVERSATION_NOTES_CACHE_KEY = 'omi-conversation-notes-v1'
APP_RESULT_CACHE_NAMESPACE = 'omi-app-result-v1'
GPT56_CACHE_MINIMUM_TOKENS = EXPLICIT_CACHE_MINIMUM_TOKENS


def _gpt56_cacheable_system_message(content: str, *, cache_enabled: bool, formatted: bool) -> Any:
    """Build the static-prefix system message.

    Pre-formatted instructions (gateway mode) are always a concrete message:
    ChatPromptTemplate would otherwise parse the literal JSON braces in the
    parser schema as template variables and fail before the LLM call. The
    breakpoint is added only when the explicit-cache path will actually pay
    for a cache write; explicit mode without a breakpoint is the unique-prompt
    opt-out from billable cache writes.
    """
    if not formatted and not cache_enabled:
        return ('system', content)
    block: Dict[str, Any] = {'type': 'text', 'text': content}
    if cache_enabled:
        block['prompt_cache_breakpoint'] = {'mode': 'explicit'}
    return SystemMessage(content=[block])


def _has_gpt56_cacheable_static_prefix(content: str) -> bool:
    """Use the model-family tokenizer as a conservative preflight for a cache write."""
    return has_cacheable_prefix(content)


# =============================================
#            FOLDER ASSIGNMENT
# =============================================
# The implementation moved to conversation_folder.py; that route still uses
# get_llm('conv_folder') as the production model/provider plug-in seam.


class SpeakerIdMatch(BaseModel):
    speaker_id: int = Field(description="The speaker id assigned to the segment")


def _word_count(text: str) -> int:
    return transcript_word_count(text)


def _content_str(response: Any) -> str:
    content = response.content
    return content if isinstance(content, str) else str(content)


def _coerce_structured(response: Structured | StructuredExtraction) -> Structured:
    if isinstance(response, StructuredExtraction):
        return response.to_structured()
    return response


def _gpt56_explicit_cache_enabled() -> bool:
    # The route half stays local so this module's gateway seam remains patchable;
    # the kill-switch half is owned once, in prompt_cache, for every caller.
    return should_route_features_through_gateway()


def should_discard_conversation(
    transcript: str,
    photos: Optional[List[ConversationPhoto]] = None,
    duration_seconds: Optional[float] = None,
    *,
    trusted_wake_word_markers: bool = False,
    on_error: Optional[Callable[[Exception], None]] = None,
    neighbor_gap_seconds: Optional[float] = None,
    neighbor_position: Optional[str] = None,
) -> bool:
    """Model tier of the relevance decision (utils/conversations/relevance.py).

    Fails open to keep; ``on_error`` lets the caller record that it did. A
    neighbor (a kept conversation within the boundary gap) is described by its
    gap and position only; none of its content enters the prompt.
    """
    # If there's a long transcript, it's very unlikely we want to discard it.
    # This is a performance optimization to avoid unnecessary LLM calls.
    word_count = _word_count(transcript) if transcript and transcript.strip() else 0
    if word_count > KEEP_WORD_COUNT:
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
    if neighbor_gap_seconds is not None:
        relation = 'started' if neighbor_position == 'before' else 'ended'
        anchor = 'after another saved conversation ended' if relation == 'started' else 'before another one started'
        duration_context += (
            f"\nThis snippet {relation} {int(neighbor_gap_seconds)} seconds {anchor}. "
            "If it only continues, answers, or closes that conversation and adds no task, fact, plan, "
            "or name of its own, discard it."
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
    if trusted_wake_word_markers and has_structural_wake_word_marker(transcript):
        prompt_template = f'{prompt_template}\n\n{WAKE_WORD_DISCARD_PROMPT_RULES}'
    custom_parser = LenientDiscardParser(pydantic_object=DiscardConversation)
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
        if on_error is not None:
            on_error(e)
        return False


# =============================================
#       SHARED CONVERSATION CONTEXT BUILDER
# =============================================


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


# Notes must use the foreground structure budget, not the gateway's background
# first-byte deadline. The owning feature route declares it in model_config.
CONVERSATION_STRUCTURE_TIMEOUT_SECONDS = FOREGROUND_REQUEST_TIMEOUT_SECONDS
# Screen-OCR rows already parsed from the context are a follow-up; this gate counts frames only.
_NOTES_TIER_MIN_WORDS = 1500
_NOTES_TIER_MIN_SCREEN_FRAMES = 5


def _notes_tier_escalation_enabled() -> bool:
    """Default off. Unset, blank, and unknown values stay off."""
    return os.getenv('NOTES_TIER_ESCALATION_ENABLED', '').strip().lower() in {'1', 'true', 'yes', 'on'}


def _shaped_notes_tier(words: int, screen_count: int) -> tuple[bool, str]:
    if (
        _notes_tier_escalation_enabled()
        and words >= _NOTES_TIER_MIN_WORDS
        and screen_count >= _NOTES_TIER_MIN_SCREEN_FRAMES
    ):
        return True, 'screen_volume'
    return False, 'below_threshold'


def _record_shaped_notes_tier(escalated: bool, reason: str, words: int, screen_count: int) -> None:
    run = current_run()
    if run is None:
        return
    run.escalated = escalated
    run.escalation_reason = reason
    run.words = words
    run.screen_count = screen_count
    if escalated:
        run.requested_effort = 'xhigh'
        run.effort = 'xhigh'


def notes_mount() -> Mount:
    return Mount(
        instructions=_conversation_notes_static_instructions('') + """
Calendar invitees are expected participants only. Screen-shown names are observed
listing data only. Neither establishes attendance or binds an audio cluster to a
person. Attribute speech only from the original speaker map or direct evidence.
Do not infer attendance, absence, or a no-show from either listing.
""",
        schema=StructuredExtraction,
        budget=Budget(turns=1, tool_calls=0, deadline_seconds=CONVERSATION_STRUCTURE_TIMEOUT_SECONDS),
    )


def get_conversation_notes(
    prefix: ConversationPromptPrefix,
    *,
    uid: Optional[str] = None,
    **kwargs: Any,
) -> Structured:
    if route_for_uid(uid) != 'new':
        raise RuntimeError('Shaped notes disabled; restore the previous image for legacy serving')
    return _get_shaped_conversation_notes(prefix, **kwargs)


@observe_notes
def _get_shaped_conversation_notes(prefix: ConversationPromptPrefix, **kwargs: Any) -> Structured:
    frames = kwargs.get('screen_frames') or ()
    # Never reuse the old prefix metadata: it may already have bound a roster.
    context = prefix.shaped_context or ('FULL TRANSCRIPT\n' + prefix.context.split('FULL TRANSCRIPT\n', 1)[-1])
    words = _word_count(context)
    rich_mode = kwargs.get('rich_context_enabled', False)
    screen_count = len(frames)
    escalated, escalation_reason = _shaped_notes_tier(words, screen_count)
    _record_shaped_notes_tier(escalated, escalation_reason, words, screen_count)
    if not prefix.has_usable_content and not frames:
        return Structured()
    mount = notes_mount()
    evidence = [
        {
            'role': 'user',
            'content': json.dumps(
                {
                    'response_language': kwargs.get('output_language_code') or kwargs['language_code'],
                    'timezone': kwargs['tz'],
                    'started_at': kwargs['started_at'].isoformat(),
                    'task_intelligence_capture': kwargs['task_intelligence_capture'],
                    'open_tasks': kwargs.get('existing_action_items') or [],
                    'capture_evidence': context,
                    **({'title_people': title_people_block(prefix)} if not rich_mode else {}),
                },
                ensure_ascii=False,
                default=str,
            ),
        }
    ]
    if frames:
        evidence.append(screen_frames_message(frames))
    # The notes lane can be Anthropic (main default); it rejects both
    # response_format and prompt_cache_breakpoint. The shaped notes mount never
    # carries a cache breakpoint; parser-based extraction needs no provider
    # cache hint to work on any lane.
    model = get_llm('conv_structure', request_timeout=CONVERSATION_STRUCTURE_TIMEOUT_SECONDS)
    extraction_parser = PydanticOutputParser(pydantic_object=StructuredExtraction)
    format_instructions = extraction_parser.get_format_instructions()
    static_instructions = mount.instructions + '\n\n' + format_instructions
    if not rich_mode:
        static_instructions = general_title_static_instructions(mount.instructions, format_instructions)
    mount = Mount(
        instructions=static_instructions,
        budget=mount.budget,
    )

    async def invoke():
        async with isolated_notes_model(model) as isolated_model:
            # After isolation so the cloner still sees the notes model. Unsupported
            # models stay unbound and keep their own options. Lazy import: the
            # episode writer module is heavy and some file-loading test harnesses
            # exec this module with stubbed dependencies.
            if escalated:
                from utils.llm.episode_writer import bind_episode_effort

                call_model = bind_episode_effort(isolated_model, 'xhigh')
            else:
                call_model = isolated_model

            async def model_turn(shape: Mount, messages: list[Any]) -> Turn:
                response = await call_model.ainvoke(messages)
                content = getattr(response, 'content', response)
                if isinstance(content, list):
                    content = ''.join(part.get('text', '') if isinstance(part, dict) else str(part) for part in content)
                return Turn(value=extraction_parser.parse(str(content)))

            return await run_loop(mount, evidence, model_turn)

    result = asyncio.run(invoke())
    structured = StructuredExtraction.model_validate(result.value).to_structured()
    # A one-turn mount cannot buy the legacy presentation revision call.
    enforce_static_conversation_note_presentation(
        structured, prefix.transcript_segment_ids, title_people=() if rich_mode else prefix.title_people
    )
    now = datetime.now(timezone.utc)
    try:
        user_tz = ZoneInfo(kwargs['tz']) if kwargs['tz'] else timezone.utc
    except Exception:
        user_tz = timezone.utc
    for item in structured.action_items:
        if item.created_at is None:
            item.created_at = now
    _normalize_action_item_due_dates(structured.action_items, user_tz=user_tz, now=now, log_past_due_clears=True)
    for event in structured.events:
        event.duration = min(event.duration, 180)
        event.created = False
    structured.overview = render_sections_markdown(structured.sections) or structured.overview
    return structured


def get_app_result(
    transcript: str,
    photos: List[ConversationPhoto],
    app: App,
    language_code: str = 'en',
    prompt_prefix: Optional[ConversationPromptPrefix] = None,
) -> str:
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

    # Split, not rewritten: the framing is stable for an app+language and repeats on
    # every conversation that app summarizes. The two halves concatenate to exactly
    # the string this prompt was (test_app_result_wire_text_is_byte_identical_...).
    app_framing = f'''
    You are an AI with the following characteristics:
    Name: {app.name},
    Description: {app.description},
    Task: ${app.memory_prompt}

    Language: The conversation language is {language_code}. Use the same language {language_code} for your response.

    Conversation:
    '''
    app_conversation_block = f'''{full_context}
    '''
    prompt = f'{app_framing}{app_conversation_block}'

    # Both branches run a user-authored prompt over a whole conversation while the user waits, so
    # they need the foreground deadline get_llm gives the conv_app_result feature (see model_config);
    # on the background one they returned `openai.APITimeoutError` and the reprocess lost its summary.
    if prompt_prefix is not None:
        instructions = f'''Apply this explicitly selected summarization app to the shared conversation.
Name: {app.name}
Description: {app.description}
Task: {app.memory_prompt}'''
        explicit_cache_enabled = shared_conversation_cache_supported()
        cache_enabled = explicit_cache_enabled and has_cacheable_prefix(instructions)
        model = get_llm(
            'conv_app_result',
            cache_key=prefix_cache_key(APP_RESULT_CACHE_NAMESPACE, instructions) if cache_enabled else None,
            prompt_cache_options=GPT56_EXPLICIT_CACHE_OPTIONS if explicit_cache_enabled else None,
        )
        response = model.invoke(
            [
                _gpt56_cacheable_system_message(instructions, cache_enabled=cache_enabled, formatted=True),
                SystemMessage(content=f'Respond in {language_code}.'),
                *prompt_prefix.messages(cache_enabled=False),
            ]
        )
        # apps_results render on the summary card like notes; strip diarization
        # placeholders the same way (SCA-454) — getSummarizedApp shows this verbatim.
        return strip_speaker_placeholders(_content_str(response).replace('```json', '').replace('```', ''))

    gateway_mode_enabled = should_route_features_through_gateway()
    explicit_cache_enabled = _gpt56_explicit_cache_enabled()
    # Above the provider's floor the leading framing is a readable prefix: one write,
    # then a read on every later conversation this app summarizes inside the TTL.
    # Below it, marked_prefix_request declines and the request keeps its previous
    # shape — explicit mode, no breakpoint, no routing key — which is how a unique
    # prompt opts out of billable writes. BYOK is excluded: a BYOK key can route
    # this feature off GPT-5.6, where a typed cache field is not a valid content part.
    marked_key, marked_messages = (
        marked_prefix_request(APP_RESULT_CACHE_NAMESPACE, app_framing, app_conversation_block)
        if explicit_cache_enabled and not has_byok_keys()
        else (None, None)
    )
    # The None/legacy split keys on gateway mode so
    # gateway-on requests never fall back to a legacy implicit routing key.
    cache_key = marked_key or (None if gateway_mode_enabled else 'omi-app-result')
    cache_options = GPT56_EXPLICIT_CACHE_OPTIONS if explicit_cache_enabled and not has_byok_keys() else None
    app_result_llm = get_llm('conv_app_result', cache_key=cache_key, prompt_cache_options=cache_options)
    response = app_result_llm.invoke(marked_messages or prompt)
    content = strip_speaker_placeholders(_content_str(response).replace('```json', '').replace('```', ''))
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


# POST /v1/conversations/{id}/test-prompt runs this inline while the user waits, so it must not
# inherit the shared gateway transport deadline (15s to first response byte), which is sized for
# background feature calls. A whole-transcript summary regularly needs longer than that: in prod on
# 2026-08-19 the same conversation failed three times at 15.2s / 15.3s / 15.4s. The route's own
# budget is the 120s default of TimeoutMiddleware, so a foreground attempt fits with headroom.
SUMMARY_WITH_PROMPT_TIMEOUT_SECONDS = FOREGROUND_REQUEST_TIMEOUT_SECONDS


class SummaryProviderError(Exception):
    """The summary provider failed on its own account, so no summary exists to return.

    Classified here, at the call that owns the provider, so the caller only has to decide how to
    report it. ``timed_out`` separates a deadline from an upstream 5xx.
    """

    def __init__(self, message: str, *, timed_out: bool) -> None:
        super().__init__(message)
        self.timed_out = timed_out


def generate_summary_with_prompt(conversation_text: str, prompt: str, language_code: str = 'en') -> str:
    # Build prompt matching the app processing format (without forced "be concise" constraint)
    full_prompt = f"""
    Your task is: {prompt}

    Language: The conversation language is {language_code}. Use the same language {language_code} for your response.

    The conversation is:
    {conversation_text}
    """
    llm = get_llm('daily_summary', cache_key='omi-daily-summary', request_timeout=SUMMARY_WITH_PROMPT_TIMEOUT_SECONDS)
    try:
        response = llm.invoke(full_prompt)
    except Exception as exc:
        # The shared provider-error classifier lives in the chat-retrieval package; this module is
        # on the import path of most of the backend, so keep that package off it and pay for the
        # import only on the failure branch.
        from utils.retrieval.safety import is_transient_provider_error, provider_fallback_reason

        if not is_transient_provider_error(exc):
            raise
        raise SummaryProviderError(
            f'summary provider failed: {type(exc).__name__}',
            timed_out=provider_fallback_reason(exc) == 'timeout',
        ) from exc
    return _content_str(response)

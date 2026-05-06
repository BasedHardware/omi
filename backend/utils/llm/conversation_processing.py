from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from database.auth import get_user_name
from models.app import App
from models.calendar_context import CalendarMeetingContext
from models.conversation import Conversation
from models.conversation_photo import ConversationPhoto
from models.structured import ActionItem, ActionItemsExtraction, Event, Structured
from .clients import get_llm, parser
import logging

logger = logging.getLogger(__name__)

# =============================================
#            FOLDER ASSIGNMENT
# =============================================


class FolderAssignment(BaseModel):
    """Model for AI folder assignment response."""

    folder_id: str = Field(description="The ID of the best matching folder for this conversation")
    confidence: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Confidence score for folder assignment (0.0 to 1.0)"
    )
    reasoning: str = Field(default="", description="Brief explanation of why this folder was chosen")


def build_folders_context(folders: List[dict]) -> str:
    """
    Build context string for LLM folder assignment using natural language descriptions.

    Each folder's description explains what conversations belong in it,
    allowing the AI to match based on intent rather than keywords.
    """
    if not folders:
        return "No folders available. Use default assignment."

    lines = []
    for folder in folders:
        folder_id = folder.get('id', '')
        name = folder.get('name', '')
        description = folder.get('description', '')
        is_default = folder.get('is_default', False)

        # Format: folder_id | "Folder Name" → Description
        if description:
            line = f'- {folder_id} | "{name}" → {description}'
        else:
            line = f'- {folder_id} | "{name}"'

        if is_default:
            line += " (DEFAULT - use when no other folder matches)"

        lines.append(line)

    return "\n".join(lines)


def assign_conversation_to_folder(
    title: str,
    overview: str,
    category: str,
    user_folders: List[dict],
) -> Tuple[Optional[str], float, str]:
    """
    Use AI to assign a conversation to the most appropriate folder.

    Args:
        title: The conversation title
        overview: The conversation overview/summary
        category: The conversation category
        user_folders: List of user's folders with id, name, description, is_default

    Returns:
        Tuple of (folder_id, confidence, reasoning)
        Returns (None, 0.0, reason) if assignment fails or confidence is too low
    """
    if not user_folders:
        return None, 0.0, "No folders available"

    folders_context = build_folders_context(user_folders)

    # Find default folder for fallback
    default_folder = next((f for f in user_folders if f.get('is_default')), None)
    default_folder_id = default_folder.get('id') if default_folder else None

    # Build conversation context
    conversation_context = f"""
Title: {title}
Category: {category}
Overview: {overview}
""".strip()

    prompt_text = '''You are a folder assignment system. Match the conversation to the folder that best represents its overall theme.

FOLDERS:
{folders_context}

CONVERSATION:
{conversation_context}

INSTRUCTIONS:
- Match based on the dominant theme of the conversation (what it's fundamentally about)
- The folder should feel like a natural home for this conversation
- Only assign to a non-default folder if the theme clearly matches
- When in doubt, use the DEFAULT folder

Provide:
- folder_id: The best matching folder ID from the list above
- confidence: Match strength (0.0-1.0). Use 0.9+ only for clear thematic matches, below 0.7 means use DEFAULT
- reasoning: One sentence explaining the match

{format_instructions}'''

    folder_parser = PydanticOutputParser(pydantic_object=FolderAssignment)
    prompt = ChatPromptTemplate.from_messages([('system', prompt_text)])
    chain = prompt | get_llm('conv_folder') | folder_parser

    try:
        response: FolderAssignment = chain.invoke(
            {
                'folders_context': folders_context,
                'conversation_context': conversation_context,
                'format_instructions': folder_parser.get_format_instructions(),
            }
        )

        # Validate the folder_id exists
        valid_folder_ids = {f.get('id') for f in user_folders}
        if response.folder_id not in valid_folder_ids:
            return default_folder_id, 0.3, f"Invalid folder ID returned, using default"

        # If confidence is too low, use default folder
        if response.confidence < 0.7 and default_folder_id:
            return (
                default_folder_id,
                response.confidence,
                f"Low confidence ({response.confidence:.2f}), using default folder",
            )

        return response.folder_id, response.confidence, response.reasoning

    except Exception as e:
        logger.error(f'Error assigning conversation to folder: {e}')
        return default_folder_id, 0.0, f"Error: {str(e)}"


class DiscardConversation(BaseModel):
    discard: bool = Field(description="If the conversation should be discarded or not")


class SpeakerIdMatch(BaseModel):
    speaker_id: int = Field(description="The speaker id assigned to the segment")


def should_discard_conversation(
    transcript: str, photos: List[ConversationPhoto] = None, duration_seconds: Optional[float] = None
) -> bool:
    # If there's a long transcript, it's very unlikely we want to discard it.
    # This is a performance optimization to avoid unnecessary LLM calls.
    if transcript and len(transcript.split(' ')) > 100:
        return False

    word_count = len(transcript.split()) if transcript and transcript.strip() else 0
    has_photos = photos and ConversationPhoto.photos_as_string(photos) != 'None'

    context_parts = []
    if transcript and transcript.strip():
        context_parts.append(f"Transcript: ```{transcript.strip()}```")

    if has_photos:
        photo_descriptions = ConversationPhoto.photos_as_string(photos)
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

    custom_parser = PydanticOutputParser(pydantic_object=DiscardConversation)
    prompt = ChatPromptTemplate.from_messages(
        [
            '''You will receive a transcript, a series of photo descriptions from a wearable camera, or both. Your task is to decide if this content is meaningful enough to be saved as a memory.

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
        ]
    )
    chain = prompt | get_llm('conv_discard') | custom_parser
    try:
        response: DiscardConversation = chain.invoke(
            {
                'full_context': full_context,
                'duration_context': duration_context,
                'format_instructions': custom_parser.get_format_instructions(),
            }
        )
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
    context_parts = []

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
    photos: List[ConversationPhoto] = None,
    existing_action_items: List[dict] = None,
    calendar_meeting_context: 'CalendarMeetingContext' = None,
    output_language_code: str = None,
) -> List[ActionItem]:
    """
    Dedicated function to extract action items from conversation content.

    Args:
        transcript: Conversation transcript
        started_at: When the conversation started
        language_code: Language code for the conversation
        tz: User's timezone
        photos: Optional conversation photos
        existing_action_items: Recent action items for deduplication (from past 2 days)

    Returns:
        List of extracted ActionItem objects
    """
    conversation_context = _build_conversation_context(transcript, photos, calendar_meeting_context)
    if not conversation_context:
        return []

    existing_items_context = ""
    if existing_action_items:
        items_list = []
        for item in existing_action_items:
            desc = item.get('description', '')
            due = item.get('due_at')
            due_str = due.strftime('%Y-%m-%d %H:%M UTC') if due else 'No due date'
            completed = '✓ Completed' if item.get('completed', False) else 'Pending'
            items_list.append(f"  • {desc} (Due: {due_str}) [{completed}]")

        existing_items_context = f"\n\nEXISTING ACTION ITEMS FROM PAST 2 DAYS ({len(items_list)} items):\n" + "\n".join(
            items_list
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

    CRITICAL DEDUPLICATION RULES (Check BEFORE extracting):
    • DO NOT extract action items that are >95% similar to existing ones in the content
    • Check both the description AND the due date/timeframe
    • Consider semantic similarity, not just exact word matches
    • Examples of what counts as DUPLICATES (DO NOT extract):
      - "Call John" vs "Phone John" → DUPLICATE
      - "Finish report by Friday" (existing) vs "Complete report by end of week" → DUPLICATE
      - "Buy milk" (existing) vs "Get milk from store" → DUPLICATE
      - "Email Sarah about meeting" (existing) vs "Send email to Sarah regarding the meeting" → DUPLICATE
    • Examples of what is NOT duplicate (OK to extract):
      - "Buy groceries" (existing) vs "Buy milk" → NOT duplicate (different scope)
      - "Call dentist" (existing) vs "Call plumber" → NOT duplicate (different person/service)
      - "Submit report by March 1st" (existing) vs "Submit report by March 15th" → NOT duplicate (different deadlines)
    • If you're unsure whether something is a duplicate, err on the side of treating it as a duplicate (DON'T extract)
    • SINGLE-TOPIC LIMIT: If a conversation discusses one topic, extract AT MOST 1 action item for it — not one per variation, option, or detail mentioned in the discussion.

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
    All due_at values MUST be future UTC timestamps with 'Z' suffix. NEVER produce a past date.

    REFERENCE_TIME: If {started_at} is >7 days before {current_time}, use {current_time} (historical reprocessing). Otherwise use {started_at}.

    Date resolution: "today" → REFERENCE_TIME date, "tomorrow" → next day, weekday names → next occurrence, "next week" → +7 days.
    Time resolution: "morning" → 9AM, "afternoon" → 2PM, "evening" → 6PM, "noon" → 12PM, "end of day"/"midnight" → 11:59PM, no time → 11:59PM. "urgent"/"ASAP" → 2h from REFERENCE_TIME.
    Process: resolve date + time in user's timezone ({tz}), convert to UTC with 'Z' suffix, verify it's future relative to {current_time}. If past, omit due_at.

    Example: REFERENCE_TIME "2025-10-03T13:25:00Z", tz "Asia/Kolkata": "tomorrow before 10am" → Oct 4 10:00 IST → "2025-10-04T04:30:00Z"
    Format: UTC with 'Z' suffix only (e.g., "2025-10-04T04:30:00Z"). No timezone offsets like "+05:30".

    Conversation started at: {started_at}
    Current time: {current_time}
    User timezone: {tz}

    {format_instructions}'''.replace(
        '    ', ''
    ).strip()

    response_language = output_language_code or language_code
    action_items_parser = PydanticOutputParser(pydantic_object=ActionItemsExtraction)
    # Second system message: conversation context + existing items (dynamic, per-conversation)
    context_message = 'The content language is {language_code}. You MUST respond entirely in {response_language}.\n\nContent:\n{conversation_context}{existing_items_context}'
    prompt = ChatPromptTemplate.from_messages([('system', instructions_text), ('system', context_message)])
    chain = prompt | get_llm('conv_action_items', cache_key='omi-extract-actions') | action_items_parser

    current_time = datetime.now(timezone.utc)

    try:
        response = chain.invoke(
            {
                'conversation_context': conversation_context,
                'format_instructions': action_items_parser.get_format_instructions(),
                'language_code': language_code,
                'response_language': response_language,
                'started_at': started_at.isoformat(),
                'current_time': current_time.isoformat(),
                'tz': tz,
                'existing_items_context': existing_items_context,
            }
        )

        # Set created_at for action items if not already set
        now = current_time
        for action_item in response.action_items or []:
            if action_item.created_at is None:
                action_item.created_at = now
            # Post-extraction validation: clear due dates more than 1 day in the past
            if action_item.due_at is not None:
                due_utc = (
                    action_item.due_at if action_item.due_at.tzinfo else action_item.due_at.replace(tzinfo=timezone.utc)
                )
                if due_utc < now - timedelta(days=1):
                    logger.warning(
                        f'Clearing past due_at {action_item.due_at.isoformat()} for action item: {action_item.description}'
                    )
                    action_item.due_at = None

        return response.action_items or []

    except Exception as e:
        logger.error(f'Error extracting action items: {e}')
        return []


def get_transcript_structure(
    transcript: str,
    started_at: datetime,
    language_code: str,
    tz: str,
    uid: str,
    photos: List[ConversationPhoto] = None,
    calendar_meeting_context: 'CalendarMeetingContext' = None,
    output_language_code: str = None,
) -> Structured:
    conversation_context = _build_conversation_context(transcript, photos, calendar_meeting_context)
    if not conversation_context:
        return Structured()  # Should be caught by discard logic, but as a safeguard.

    response_language = output_language_code or language_code
    try:
        user_name = get_user_name(uid)
    except Exception as e:
        logger.warning(f'Failed to load user name for transcript structuring (uid={uid}): {e}')
        user_name = 'The User'

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

    For date context, this content was captured on {started_at}. {tz} is the user's timezone; respond in user local timezone.

    {format_instructions}'''.replace(
        '    ', ''
    ).strip()

    # Second system message: conversation context (dynamic, per-conversation)
    context_message = 'The content language is {language_code}. You MUST respond entirely in {response_language}.\n\nContent:\n{conversation_context}'
    prompt = ChatPromptTemplate.from_messages([('system', instructions_text), ('system', context_message)])
    chain = prompt | get_llm('conv_structure', cache_key='omi-transcript-structure') | parser

    response = chain.invoke(
        {
            'conversation_context': conversation_context,
            'format_instructions': parser.get_format_instructions(),
            'language_code': language_code,
            'response_language': response_language,
            'started_at': started_at.isoformat(),
            'tz': tz,
        }
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
    photos: List[ConversationPhoto] = None,
    output_language_code: str = None,
) -> Structured:
    context_parts = []
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
    
    For date context, this content was captured on {started_at}. {tz} is the user's timezone; respond in user local timezone.

    Content:
    {full_context}

    {format_instructions}'''.replace(
        '    ', ''
    ).strip()

    prompt = ChatPromptTemplate.from_messages([('system', prompt_text)])
    chain = prompt | get_llm('conv_structure', cache_key='omi-transcript-structure') | parser

    response = chain.invoke(
        {
            'full_context': full_context,
            'title': title,
            'format_instructions': parser.get_format_instructions(),
            'language_code': language_code,
            'response_language': response_language,
            'started_at': started_at.isoformat(),
            'tz': tz,
        }
    )

    for event in response.events or []:
        if event.duration > 180:
            event.duration = 180
        event.created = False

    return response


def get_app_result(transcript: str, photos: List[ConversationPhoto], app: App, language_code: str = 'en') -> str:
    context_parts = []
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
    content = response.content.replace('```json', '').replace('```', '')
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
        response: SuggestedAppsSelection = with_parser.invoke(prompt)

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
        response: BestAppSelection = with_parser.invoke(prompt)
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
    return response.content

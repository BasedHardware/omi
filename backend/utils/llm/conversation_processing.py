from datetime import datetime, timezone
from typing import List, Optional, Tuple

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from models.app import App
from models.conversation import (
    CalendarMeetingContext,
    Structured,
    Conversation,
    ActionItem,
    Event,
    ConversationPhoto,
    ActionItemsExtraction,
)
from .clients import llm_mini, parser, llm_high, llm_medium_experiment


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
    transcript: str,
    title: str,
    overview: str,
    category: str,
    user_folders: List[dict],
) -> Tuple[Optional[str], float, str]:
    """
    Use AI to assign a conversation to the most appropriate folder.

    Args:
        transcript: The conversation transcript
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

Transcript excerpt (first 500 chars):
{transcript[:500] if transcript else 'No transcript'}
""".strip()

    prompt_text = '''You are an expert at organizing conversations into folders.

The user has organized their folders with descriptions that explain what belongs in each:

{folders_context}

Based on the **primary topic and intent** of the conversation below, choose the folder whose description best matches.

CONVERSATION:
{conversation_context}

DECISION PROCESS:
1. What is the main subject being discussed?
2. Which folder description aligns best with this subject?
3. If multiple folders could apply, choose based on the **primary purpose** of the conversation
4. If no folder clearly matches (confidence < 0.5), use the DEFAULT folder

Example reasoning:
- A conversation about "meeting with trainer to plan an AI fitness app" could match both Health and Technology
- Since the primary purpose is building an app, Technology is the better match

Provide:
- folder_id: The ID of the best matching folder (from the list above)
- confidence: A score from 0.0 to 1.0 indicating match strength
  * 0.8-1.0: Clear match - conversation clearly fits the folder description
  * 0.5-0.8: Reasonable match - conversation relates to the folder description
  * Below 0.5: Weak match - use the DEFAULT folder instead
- reasoning: Brief explanation of your choice

{format_instructions}'''

    folder_parser = PydanticOutputParser(pydantic_object=FolderAssignment)
    prompt = ChatPromptTemplate.from_messages([('system', prompt_text)])
    chain = prompt | llm_mini | folder_parser

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
        if response.confidence < 0.5 and default_folder_id:
            return (
                default_folder_id,
                response.confidence,
                f"Low confidence ({response.confidence:.2f}), using default folder",
            )

        return response.folder_id, response.confidence, response.reasoning

    except Exception as e:
        print(f'Error assigning conversation to folder: {e}')
        return default_folder_id, 0.0, f"Error: {str(e)}"


class DiscardConversation(BaseModel):
    discard: bool = Field(description="If the conversation should be discarded or not")


class SpeakerIdMatch(BaseModel):
    speaker_id: int = Field(description="The speaker id assigned to the segment")


def should_discard_conversation(transcript: str, photos: List[ConversationPhoto] = None) -> bool:
    # If there's a long transcript, it's very unlikely we want to discard it.
    # This is a performance optimization to avoid unnecessary LLM calls.
    if transcript and len(transcript.split(' ')) > 100:
        return False

    context_parts = []
    if transcript and transcript.strip():
        context_parts.append(f"Transcript: ```{transcript.strip()}```")

    if photos:
        photo_descriptions = ConversationPhoto.photos_as_string(photos)
        if photo_descriptions != 'None':
            context_parts.append(f"Photo Descriptions from a wearable camera:\n{photo_descriptions}")

    # If there is no content to process (e.g., empty transcript and no photo descriptions), discard.
    if not context_parts:
        return True

    full_context = "\n\n".join(context_parts)

    custom_parser = PydanticOutputParser(pydantic_object=DiscardConversation)
    prompt = ChatPromptTemplate.from_messages(
        [
            '''You will receive a transcript, a series of photo descriptions from a wearable camera, or both. Your task is to decide if this content is meaningful enough to be saved as a memory. Length is never a reason to discard.

Task: Decide if the content should be saved as a memory.

KEEP (output: discard = False) if the content contains any of the following:
• A task, request, or action item.
• A decision, commitment, or plan.
• A question that requires follow-up.
• Personal facts, preferences, or details likely useful later (e.g., remembering a person, place, or object).
• An important event, social interaction, or significant moment.
• An insight, summary, or key takeaway.
• A visually significant scene (e.g., a whiteboard with notes, a document, a memorable view, a person's face).

If none of these are present, DISCARD (output: discard = True). For example, discard blurry photos, uninteresting scenery with no context, or trivial conversation snippets.

Return exactly one line:
discard = <True|False>

Content:
{full_context}

{format_instructions}'''.replace(
                '    ', ''
            ).strip()
        ]
    )
    chain = prompt | llm_mini | custom_parser
    try:
        response: DiscardConversation = chain.invoke(
            {
                'full_context': full_context,
                'format_instructions': custom_parser.get_format_instructions(),
            }
        )
        return response.discard

    except Exception as e:
        print(f'Error determining memory discard: {e}')
        return False


def extract_action_items(
    transcript: str,
    started_at: datetime,
    language_code: str,
    tz: str,
    photos: List[ConversationPhoto] = None,
    existing_action_items: List[dict] = None,
    calendar_meeting_context: 'CalendarMeetingContext' = None,
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
    context_parts = []
    if transcript and transcript.strip():
        context_parts.append(f"Transcript: ```{transcript.strip()}```")

    if photos:
        photo_descriptions = ConversationPhoto.photos_as_string(photos)
        if photo_descriptions != 'None':
            context_parts.append(f"Photo Descriptions from a wearable camera:\n{photo_descriptions}")

    # Add calendar meeting context if available
    calendar_context_str = ""
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
"""
        context_parts.insert(0, calendar_context_str.strip())

    if not context_parts:
        return []

    full_context = "\n\n".join(context_parts)

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

    prompt_text = '''You are an expert action item extractor. Your sole purpose is to identify and extract high-quality, actionable tasks from the provided content.

    The content language is {language_code}. Use the same language {language_code} for your response.

    CRITICAL: If CALENDAR MEETING CONTEXT is provided with participant names, you MUST use those names:
    - The conversation DEFINITELY happened between the named participants
    - NEVER use "Speaker 0", "Speaker 1", "Speaker 2", etc. when participant names are available
    - Match transcript speakers to participant names by analyzing the conversation context
    - Use participant names in ALL action items (e.g., "Follow up with Sarah" NOT "Follow up with Speaker 0")
    - Reference the meeting title/context when relevant to the action item
    - Consider the scheduled meeting time and duration when extracting due dates
    - If you cannot confidently match a speaker to a name, use the action description without speaker references{existing_items_context}

    CRITICAL DEDUPLICATION RULES (Check BEFORE extracting):
    • DO NOT extract action items that are >95% similar to existing ones listed above
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

    WORKFLOW:
    1. FIRST: Read the ENTIRE conversation carefully to understand the full context
    2. SECOND: Identify all topics, people, places, or things being discussed
    3. THIRD: Filter aggressively - is the user ALREADY doing this? If yes, SKIP IT
    4. FOURTH: Ask - "Is this truly important enough to remind a busy person?" If no, SKIP IT
    5. FIFTH: Extract ONLY action items that passed steps 3 & 4, using specific names/details
    6. SIXTH: Extract timing information separately and put it in the due_at field
    7. SEVENTH: Clean the description - remove ALL time references and vague words
    8. EIGHTH: Final check - description should be timeless and specific (e.g., "Buy groceries" NOT "buy them by tomorrow")

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

    5. **Future Intent or Deadline**: Extract tasks that the user INTENDS to do or has a deadline for:
       - "I want to X" → EXTRACT (user stated intention, needs reminder)
       - "I need to X by [date]" → EXTRACT (deadline that could be forgotten)
       - "Today I will X" → EXTRACT (daily goal, needs tracking)
       - "This week/month I want to X" → EXTRACT (time-bound goal)
       
       Only skip if user is ACTIVELY doing something RIGHT NOW:
       - "I am currently in the middle of X" → Skip (actively doing it this moment)
       - "Right now I'm doing X" → Skip (immediate present action)

       Examples:
       - ✅ "Today, I want to complete the onboarding experience" → EXTRACT (stated goal with deadline)
       - ✅ "I want to finish the report by Friday" → EXTRACT (intention + deadline)
       - ✅ "This month, I want to grow users to 500k" → EXTRACT (monthly goal)
       - ✅ "Need to call the plumber tomorrow" → EXTRACT (future task)
       - ✅ "Have to submit tax documents by March 31st" → EXTRACT (deadline)
       - ❌ "I'm currently on a call with the client" → Skip (happening right now)
       - ❌ "Right now I'm debugging this issue" → Skip (immediate action)

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

    DUE DATE EXTRACTION (CRITICAL):
    IMPORTANT: All due dates must be in the FUTURE and in UTC format with 'Z' suffix.
    IMPORTANT: When parsing dates, FIRST determine the DATE (today/tomorrow/specific date), THEN apply the TIME.

    Step-by-step date parsing process:
    1. IDENTIFY THE DATE:
       - "today" → current date from {started_at}
       - "tomorrow" → next day from {started_at}
       - "Monday", "Tuesday", etc. → next occurrence of that weekday
       - "next week" → same day next week
       - Specific date (e.g., "March 15") → that date

    2. IDENTIFY THE TIME (if mentioned):
       - "before 10am", "by 10am", "at 10am" → 10:00 AM
       - "before 3pm", "by 3pm", "at 3pm" → 3:00 PM
       - "in the morning" → 9:00 AM
       - "in the afternoon" → 2:00 PM
       - "in the evening", "by evening" → 6:00 PM
       - "at noon" → 12:00 PM
       - "by midnight", "by end of day" → 11:59 PM
       - No time mentioned → 11:59 PM (end of day)

    3. COMBINE DATE + TIME in user's timezone ({tz}), then convert to UTC with 'Z' suffix

    Examples of CORRECT date parsing:
    If {started_at} is "2025-10-03T13:25:00Z" (Oct 3, 6:55 PM IST) and {tz} is "Asia/Kolkata":
    - "tomorrow before 10am" → DATE: Oct 4, TIME: 10:00 AM → "2025-10-04 10:00 IST" → Convert to UTC → "2025-10-04T04:30:00Z"
    - "today by evening" → DATE: Oct 3, TIME: 6:00 PM → "2025-10-03 18:00 IST" → Convert to UTC → "2025-10-03T12:30:00Z"
    - "tomorrow" → DATE: Oct 4, TIME: 11:59 PM (default) → "2025-10-04 23:59 IST" → Convert to UTC → "2025-10-04T18:29:00Z"
    - "by Monday at 2pm" → DATE: next Monday (Oct 6), TIME: 2:00 PM → "2025-10-06 14:00 IST" → Convert to UTC → "2025-10-06T08:30:00Z"
    - "urgent" or "ASAP" → 2 hours from {started_at} → "2025-10-03T15:25:00Z"

    CRITICAL FORMAT: All due_at timestamps MUST be in UTC with 'Z' suffix (e.g., "2025-10-04T04:30:00Z")
    DO NOT include timezone offsets like "+05:30". Always convert to UTC and use 'Z' suffix.

    Reference time: {started_at}
    User timezone: {tz}

    Content:
    {full_context}

    {format_instructions}'''.replace(
        '    ', ''
    ).strip()

    action_items_parser = PydanticOutputParser(pydantic_object=ActionItemsExtraction)
    prompt = ChatPromptTemplate.from_messages([('system', prompt_text)])
    chain = prompt | llm_medium_experiment | action_items_parser

    try:
        response = chain.invoke(
            {
                'full_context': full_context,
                'format_instructions': action_items_parser.get_format_instructions(),
                'language_code': language_code,
                'started_at': started_at.isoformat(),
                'tz': tz,
                'existing_items_context': existing_items_context,
            }
        )

        # Set created_at for action items if not already set
        now = datetime.now(timezone.utc)
        for action_item in response.action_items or []:
            if action_item.created_at is None:
                action_item.created_at = now

        return response.action_items or []

    except Exception as e:
        print(f'Error extracting action items: {e}')
        return []


def get_transcript_structure(
    transcript: str,
    started_at: datetime,
    language_code: str,
    tz: str,
    photos: List[ConversationPhoto] = None,
    existing_action_items: List[dict] = None,
    calendar_meeting_context: 'CalendarMeetingContext' = None,
) -> Structured:
    context_parts = []
    if transcript and transcript.strip():
        context_parts.append(f"Transcript: ```{transcript.strip()}```")

    if photos:
        photo_descriptions = ConversationPhoto.photos_as_string(photos)
        if photo_descriptions != 'None':
            context_parts.append(f"Photo Descriptions from a wearable camera:\n{photo_descriptions}")

    # Add calendar meeting context if available
    calendar_context_str = ""
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
"""
        context_parts.insert(0, calendar_context_str.strip())

    if not context_parts:
        return Structured()  # Should be caught by discard logic, but as a safeguard.

    full_context = "\n\n".join(context_parts)

    prompt_text = '''You are an expert content analyzer. Your task is to analyze the provided content (which could be a transcript, a series of photo descriptions from a wearable camera, or both) and provide structure and clarity.
    The content language is {language_code}. Use the same language {language_code} for your response.

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
    
    For date context, this content was captured on {started_at}. {tz} is the user's timezone; convert all event times to UTC and respond in UTC.


    Content:
    {full_context}

    {format_instructions}'''.replace(
        '    ', ''
    ).strip()

    prompt = ChatPromptTemplate.from_messages([('system', prompt_text)])
    chain = prompt | llm_medium_experiment | parser  # parser is imported from .clients

    response = chain.invoke(
        {
            'full_context': full_context,
            'format_instructions': parser.get_format_instructions(),
            'language_code': language_code,
            'started_at': started_at.isoformat(),
            'tz': tz,
        }
    )

    for event in response.events or []:
        if event.duration > 180:
            event.duration = 180
        event.created = False

    # Extract action items separately
    action_items = extract_action_items(
        transcript, started_at, language_code, tz, photos, existing_action_items, calendar_meeting_context
    )
    response.action_items = action_items

    return response


def get_reprocess_transcript_structure(
    transcript: str,
    started_at: datetime,
    language_code: str,
    tz: str,
    title: str,
    photos: List[ConversationPhoto] = None,
    existing_action_items: List[dict] = None,
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

    prompt_text = '''You are an expert content analyzer. Your task is to analyze the provided content (which could be a transcript, a series of photo descriptions from a wearable camera, or both) and provide structure and clarity.
    The content language is {language_code}. Use the same language {language_code} for your response.

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
    
    For date context, this content was captured on {started_at}. {tz} is the user's timezone; convert all event times to UTC and respond in UTC.

    Content:
    {full_context}

    {format_instructions}'''.replace(
        '    ', ''
    ).strip()

    prompt = ChatPromptTemplate.from_messages([('system', prompt_text)])
    chain = prompt | llm_medium_experiment | parser  # parser is imported from .clients

    response = chain.invoke(
        {
            'full_context': full_context,
            'title': title,
            'format_instructions': parser.get_format_instructions(),
            'language_code': language_code,
            'started_at': started_at.isoformat(),
            'tz': tz,
        }
    )

    for event in response.events or []:
        if event.duration > 180:
            event.duration = 180
        event.created = False

    # Extract action items separately
    action_items = extract_action_items(transcript, started_at, language_code, tz, photos, existing_action_items)
    response.action_items = action_items

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

    response = llm_medium_experiment.invoke(prompt)
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
        with_parser = llm_mini.with_structured_output(SuggestedAppsSelection)
        response: SuggestedAppsSelection = with_parser.invoke(prompt)

        # Validate that suggested app IDs exist in the available apps
        valid_app_ids = {app.id for app in apps}
        suggested_apps = [app_id for app_id in response.suggested_apps if app_id in valid_app_ids]

        return suggested_apps, response.reasoning

    except Exception as e:
        print(f"Error getting suggested apps: {e}")
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
        with_parser = llm_mini.with_structured_output(BestAppSelection)
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
        print(f"Error selecting best app: {e}")
        return None


def generate_summary_with_prompt(conversation_text: str, prompt: str, language_code: str = 'en') -> str:
    # Build prompt matching the app processing format (without forced "be concise" constraint)
    full_prompt = f"""
    Your task is: {prompt}

    Language: The conversation language is {language_code}. Use the same language {language_code} for your response.

    The conversation is:
    {conversation_text}
    """
    response = llm_medium_experiment.invoke(full_prompt)
    return response.content

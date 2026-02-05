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
from .clients import llm_mini, llm_medium, parser, llm_high, llm_medium_experiment
from .usage_tracker import track_usage, Features

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
        if response.confidence < 0.7 and default_folder_id:
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

Task: Decide if the content should be saved as conversation summary.

KEEP (output: discard = False) if the content contains any of the following:
• A task, request, or action item.
• A decision, commitment, or plan.
• A question that requires follow-up.
• Personal facts, preferences, or details likely useful later (e.g., remembering a person, place, or object).
• An important event, social interaction, or significant moment with meaningful context or consequences.
• An insight, summary, or key takeaway that provides value.
• A visually significant scene (e.g., a whiteboard with notes, a document, a memorable view, a person's face).

DISCARD (output: discard = True) if the content is:
• Trivial conversation snippets (e.g., brief apologies, casual remarks, single-sentence comments without context).
• Very brief interactions (5-10 seconds) that lack actionable content or meaningful context.
• Casual acknowledgments, greetings, or passing comments that don't contain useful information.
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

    prompt_text = '''You are an expert action item extractor. Extract actionable tasks from the content.

    Language: {language_code}. Respond in the same language.

    EXPLICIT REQUESTS (HIGHEST PRIORITY - always extract, bypass all filters):
    Patterns: "Remind me to X", "Don't forget X", "Add task X", "Note to self: X", "Todo: X", "Set reminder for X", "You need to X" (said TO user) → EXTRACT "X"

    CALENDAR MEETING CONTEXT RULES:
    If participant names are provided, ALWAYS use them instead of "Speaker 0/1/2". Match speakers to names from context. Use meeting title/time for due dates.{existing_items_context}

    DEDUPLICATION (check BEFORE extracting):
    Skip items >95% semantically similar to existing ones above (check description AND due date). When unsure, treat as duplicate.

    WORKFLOW:
    1. Read entire conversation for context
    2. Extract EXPLICIT task requests (always)
    3. For IMPLICIT tasks - aggressively filter: Is user already doing this? Is it truly important? Would missing it have real consequences? Better to extract 0 than flood with noise
    4. Extract timing → due_at field. Clean description of ALL time references
    5. Resolve vague references ("it", "the feature") to specific names from conversation

    CONTEXT: Action items are for the PRIMARY USER (device wearer/conversation initiator). Include others' tasks ONLY if primary user depends on them.

    FILTERING CRITERIA (all must be met for implicit tasks; explicit requests bypass 3 and 4):
    1. Clear ownership relevant to primary user (use participant names, never "Speaker N")
    2. Concrete, specific action (not vague intentions)
    3. Timing signal: dates, relative timing, or urgency markers
    4. Real importance: financial, health, deadlines, commitments, dependencies
    5. Future intent: "I want to X", "I need to X by [date]", "Today I will X"
       Skip only if user is actively doing it RIGHT NOW

    EXCLUDE: things already being done, casual mentions, vague suggestions, past actions, hypotheticals, trivial tasks, others' tasks not impacting user, routine activities, status updates

    FORMAT:
    • Max 15 words per item. Start with verb. Remove time references (they go in due_at)
    • Resolve ALL vague references to specific names from conversation context
    • Order by: due date → urgency → alphabetical

    DUE DATE EXTRACTION:
    All dates in UTC with 'Z' suffix. Process: DATE first, then TIME.
    - "today" → date from {started_at}; "tomorrow" → next day; weekday names → next occurrence
    - Times: "morning" → 9AM, "afternoon" → 2PM, "evening" → 6PM, "noon" → 12PM, no time → 11:59PM
    - Combine in user timezone ({tz}), convert to UTC. "urgent"/"ASAP" → +2 hours from {started_at}

    Reference time: {started_at}
    User timezone: {tz}

    Content:
    {full_context}

    {format_instructions}'''.replace('    ', '').strip()

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
    chain = prompt | llm_medium | parser  # gpt-4.1: schema-constrained, sufficient for structure

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
    chain = prompt | llm_medium | parser  # gpt-4.1: schema-constrained, sufficient for reprocess structure

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

    response = llm_medium.invoke(prompt)  # gpt-4.1: sufficient for app summarization
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
    response = llm_medium.invoke(full_prompt)  # gpt-4.1: sufficient for custom summarization
    return response.content

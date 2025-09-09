import uuid
import threading
from datetime import datetime, timezone
from typing import Optional

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from models.conversation import Structured, Conversation, ConversationStatus, CategoryEnum, ConversationSource
from models.transcript_segment import TranscriptSegment
from models.chat import Message, MessageSender
import database.notifications as notification_db
import database.users as users_db
from utils.conversations.process_conversation import (
    _extract_memories,
    _save_action_items,
    _extract_trends,
    save_structured_vector,
)
from .clients import llm_medium_experiment, parser


def get_chat_message_structure(message_text: str, timestamp: datetime, language_code: str, tz: str) -> Structured:
    """
    Extract structured data (action items, events, memories) from a single chat message.
    Adapted from get_transcript_structure() for chat message processing.

    Args:
        message_text: The chat message content
        timestamp: When the message was created
        language_code: User's language preference
        tz: User's timezone for date conversions

    Returns:
        Structured object with title, overview, action_items, events, etc.
    """
    if not message_text or not message_text.strip():
        return Structured()

    prompt_text = '''You are an expert content analyzer. Your task is to analyze a single chat message and extract structured insights for memory and task management.
    The message language is {language_code}. Use the same language {language_code} for your response.

    For the title, Write a clear, compelling headline (≤ 10 words) that captures the main topic or intent. Use Title Case, avoid filler words (e.g., "Weekend Trip Planning" or "Project Deadline Discussion").
    For the overview, provide a concise summary of what the user discussed, including key details and context.
    For the emoji, select a single emoji that reflects the core subject or mood of the message.

    For the action items, apply a strict filter and use the format below:  
    • Include **only** tasks that have  
      a) a clear owner (the user or someone specific),  
      b) a concrete next step **and** timing cue (date, "tomorrow", "next week", etc.),  
      c) real importance (deadline, commitment, or explicit importance).  
    • Exclude vague remarks ("I should exercise more").  
    • Format each as a single bullet with its own emoji from the whitelist 📞 📝 🏥 🚗 💻 🛠️ 📦 📊 📚 🔧 ⚠️ ⏳ 🎯 🔋 🎓 📢 💡.
    • IMPORTANT: For each action item, extract and provide a due_at datetime based on timing mentioned:
      - Convert relative times ("tomorrow", "next week") to actual UTC datetime based on {timestamp} and {tz}
      - For "today": use end of day in user's timezone converted to UTC
      - For "tomorrow": use end of next day in user's timezone converted to UTC  
      - For "this week": use end of current week (Sunday) in user's timezone converted to UTC
      - For "next week": use end of next week in user's timezone converted to UTC
      - For specific dates: convert to end of that day in user's timezone to UTC
      - For "urgent" or "ASAP": use 2 hours from {timestamp}
      - For "high priority": use end of today
      - For "when convenient" or no specific time: leave due_at as null

    For the category, classify the message into one of the available categories.

    For Calendar Events, apply strict filtering to include ONLY events that meet ALL these criteria:
    • **Confirmed commitment**: Not suggestions or "maybe" - actual scheduled events
    • **User involvement**: The user is expected to attend, participate, or take action
    • **Specific timing**: Has concrete date/time, not vague references like "sometime" or "soon"
    • **Important/actionable**: Missing it would have real consequences
    
    For date context, this message was sent on {timestamp}. {tz} is the user's timezone; convert all times to UTC and respond in UTC.

    Message Content:
    {message_content}

    {format_instructions}'''.replace(
        '    ', ''
    ).strip()

    prompt = ChatPromptTemplate.from_messages([('system', prompt_text)])
    chain = prompt | llm_medium_experiment | parser

    try:
        response = chain.invoke(
            {
                'message_content': message_text,
                'format_instructions': parser.get_format_instructions(),
                'language_code': language_code,
                'timestamp': timestamp.isoformat(),
                'tz': tz,
            }
        )

        # Set created_at for action items if not already set
        for action_item in response.action_items or []:
            if action_item.created_at is None:
                action_item.created_at = datetime.now(timezone.utc)

        return response

    except Exception as e:
        print(f"Error extracting structure from chat message: {e}")
        return Structured()


def _create_pseudo_conversation_from_message(uid: str, message: Message, structured: Structured) -> Conversation:
    """
    Create a pseudo-Conversation object from a chat message to feed into existing pipeline.
    This allows us to reuse 100% of the existing memories/todos/trends extraction logic.
    """
    # Create a pseudo transcript segment from the chat message
    transcript_segment = TranscriptSegment(
        id=str(uuid.uuid4()),
        text=message.text,
        speaker='SPEAKER_01',
        speaker_id=1,
        is_user=True,  # Required field - this is a user message
        person_id=uid,
        start=0.0,
        end=1.0,
        translations=[],
        speech_profile_processed=True,
    )

    # Create pseudo conversation object
    conversation = Conversation(
        id=f"chat_message_{message.id}",
        created_at=message.created_at,
        started_at=message.created_at,
        finished_at=message.created_at,
        structured=structured,
        transcript_segments=[transcript_segment],
        language='en',  # Will be set properly by caller
        status=ConversationStatus.completed,
        source=ConversationSource.omi,  # Indicate this comes from OMI chat
        discarded=False,
        postprocessing=None,
        geolocation=None,
        photos=[],
        plugins_results=[],
        apps_results=[],
        external_data={},
        analysis_results=[],
    )

    return conversation


def process_chat_message_for_insights(uid: str, message: Message, app_id: Optional[str] = None) -> None:
    """
    Process a chat message through the memories/todos/trends pipeline.
    Reuses existing conversation processing infrastructure.

    Args:
        uid: User ID
        message: The chat message to process (should be human message)
        app_id: Optional app ID for context
    """
    # Skip AI messages - only process human messages
    if message.sender != MessageSender.human:
        return

    # Get user context
    tz = notification_db.get_user_time_zone(uid) or 'UTC'
    language_code = users_db.get_user_language_preference(uid) or 'en'

    try:
        # Step 1: Extract structured data from chat message
        structured = get_chat_message_structure(
            message_text=message.text, timestamp=message.created_at, language_code=language_code, tz=tz
        )

        # Skip if no meaningful content extracted
        if not structured or (not structured.action_items and not structured.title.strip()):
            return

        # Step 2: Create pseudo-conversation for pipeline compatibility
        conversation = _create_pseudo_conversation_from_message(uid, message, structured)
        conversation.language = language_code

        # Step 3: Process through existing pipelines (reuse 100% of existing code)
        # Run in parallel threads just like the conversation pipeline
        threading.Thread(target=save_structured_vector, args=(uid, conversation)).start()
        threading.Thread(target=_extract_memories, args=(uid, conversation)).start()
        threading.Thread(target=_save_action_items, args=(uid, conversation)).start()
        threading.Thread(target=_extract_trends, args=(uid, conversation)).start()

        print(f"Chat message insights processing started for message {message.id}")

    except Exception as e:
        print(f"Error processing chat message for insights: {e}")
        # Don't raise - this shouldn't break the chat flow

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from database import conversations as conversations_db
from database import users as users_db
from models.conversation import (
    Conversation,
    Structured,
    CategoryEnum,
    ActionItem,
    ConversationSource,
    ConversationVisibility,
    ConversationStatus,
)


def ensure_welcome_conversation(uid: str) -> dict | None:
    """
    For first time users, creates a welcome conversation.

    Returns the created conversation as a dict if it was created, otherwise None.
    """
    # If we've already created it, skip
    if users_db.get_welcome_conversation_created(uid):
        return None

    existing = conversations_db.get_conversations(
        uid,
        limit=1,
        offset=0,
        include_discarded=True,
        statuses=[],
    )
    if existing:
        return None

    now = datetime.now(timezone.utc)
    conversation_id = str(uuid.uuid4())

    welcome = Conversation(
        id=conversation_id,
        created_at=now,
        started_at=now,
        finished_at=now,
        source=ConversationSource.omi,
        language='en',
        structured=Structured(
            title='Welcome to Omi',
            overview=(
                "Omi captures moments, meetings or thoughts and turns them into clear summaries with action items.\n"
                "1) Start recording 🎙️: Tap the big Record button to begin recording, and Omi will capture your conversation or thoughts.\n"
                "2) Stop or auto-finish ⏹️: Tap the red stop button to stop. If you're silent for ~2 minutes, Omi auto-finishes and summarizes.\n"
                "3) Review your summary 📝: The new conversation appears at the top with a title, overview, and TODOs.\n"
                "4) Share when needed 🔗: Open a conversation, tap Share, then Send web URL.\n"
                "5) Automate workflows ⚙️: Connect apps to trigger actions when conversations finish - like creating reminders, or updating other tools."
            ),
            emoji='👋',
            category=CategoryEnum.education,
            action_items=[
                ActionItem(description='Try a quick 1-2 minute test recording from the Home screen'),
                ActionItem(description='Open the new conversation and read the summary'),
                ActionItem(description='Share the URL with someone'),
            ],
        ),
        transcript_segments=[],
        photos=[],
        status=ConversationStatus.completed,
        visibility=ConversationVisibility.private,
    )

    conversations_db.upsert_conversation(uid, conversation_data=welcome.dict())
    users_db.set_welcome_conversation_created(uid, welcome.id)
    return welcome.dict()

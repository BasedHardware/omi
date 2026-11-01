"""Conversation prompt timestamps use the named turn zone for captures and photos."""

from datetime import datetime, timezone

from models.conversation_photo import ConversationPhoto
from utils.llm.conversation_prompt_context import build_conversation_prompt_prefix


def test_prompt_context_labels_capture_and_photo_time_in_user_zone():
    started_at = datetime(2026, 9, 26, 7, 18, tzinfo=timezone.utc)
    photo = ConversationPhoto(
        base64='pixel-placeholder',
        description='A whiteboard',
        created_at=started_at,
    )

    prefix = build_conversation_prompt_prefix(
        conversation_id='conversation-1',
        transcript='The team reviewed the launch.',
        started_at=started_at,
        timezone_name='Asia/Ho_Chi_Minh',
        language_code='en',
        photos=[photo],
    )

    assert 'Captured at: Sat 26 Sep 2026, 14:18 Asia/Ho_Chi_Minh (UTC+07:00)' in prefix.context
    assert '[Sat 26 Sep 2026, 14:18 Asia/Ho_Chi_Minh (UTC+07:00)] "A whiteboard"' in prefix.context
    assert '07:18 UTC' not in prefix.context

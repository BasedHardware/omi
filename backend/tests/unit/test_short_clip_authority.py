"""Stored manual titles survive the real model boundary without becoming write authority."""

from datetime import datetime, timezone

from models.conversation import Conversation
from models.structured import Structured
from utils.conversations.factory import deserialize_conversation
from utils.llm.notes_short_clip import quiet_minimum


def test_user_title_survives_deserialization_and_exempts_a_short_row(monkeypatch):
    monkeypatch.setenv('NOTES_SHORT_CLIP_FLOOR', 'on')
    monkeypatch.setenv('NOTES_PACKET_V2_MODE', 'off')
    now = datetime(2026, 10, 31, tzinfo=timezone.utc)
    raw = dict(
        id='curated-row',
        created_at=now,
        started_at=now,
        finished_at=now,
        structured=Structured(title='Recording', title_provenance='server_minimum').model_dump(),
        user_title='My recording',
        transcript_segments=[dict(text='A tiny recording', start=0, end=2, speaker='SPEAKER_00', is_user=True)],
    )
    conversation = deserialize_conversation(raw)
    assert conversation.user_title == 'My recording'
    assert quiet_minimum('synthetic-account', conversation) is None
    assert 'user_title' not in conversation.model_dump()
    assert 'user_title' not in Conversation.model_json_schema()['properties']
    raw.pop('user_title')
    assert quiet_minimum('synthetic-account', deserialize_conversation(raw)).title_provenance == 'server_minimum'

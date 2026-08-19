"""Regression tests for conversation language defaulting to 'en' (#11349).

Proves that omitted language values resolve to 'en' on the three changed
conversation models, and that an explicitly provided language is preserved.
"""

from datetime import datetime, timezone

from models.conversation import (
    Conversation,
    CreateConversation,
    ExternalIntegrationCreateConversation,
)
from models.structured import Structured


def _now():
    return datetime.now(timezone.utc)


class TestConversationLanguageDefault:
    """Omitted language defaults to 'en' on all three changed models."""

    def test_conversation_language_defaults_to_en(self):
        conv = Conversation(
            id='c1',
            created_at=_now(),
            started_at=_now(),
            finished_at=_now(),
            structured=Structured(),
        )
        assert conv.language == 'en'

    def test_create_conversation_language_defaults_to_en(self):
        conv = CreateConversation(
            started_at=_now(),
            finished_at=_now(),
            transcript_segments=[],
        )
        assert conv.language == 'en'

    def test_external_integration_create_conversation_language_defaults_to_en(self):
        conv = ExternalIntegrationCreateConversation(text='hello')
        assert conv.language == 'en'

    def test_conversation_language_defaults_to_en_from_json(self):
        conv = Conversation.model_validate(
            {
                'id': 'c1',
                'created_at': _now().isoformat(),
                'started_at': _now().isoformat(),
                'finished_at': _now().isoformat(),
                'structured': {},
            }
        )
        assert conv.language == 'en'

    def test_explicit_language_is_preserved(self):
        conv = CreateConversation(
            started_at=_now(),
            finished_at=_now(),
            transcript_segments=[],
            language='fr',
        )
        assert conv.language == 'fr'

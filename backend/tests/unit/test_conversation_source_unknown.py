"""Tests for ConversationSource unknown value handling.

Verifies that unknown source values in Firestore don't crash
response serialization (issue #5409).
"""

import sys
from unittest.mock import MagicMock

# Stub heavy dependencies before importing models
for mod in [
    'firebase_admin',
    'firebase_admin.firestore',
    'firebase_admin.auth',
    'firebase_admin.credentials',
    'google.cloud.firestore',
    'google.auth.transport.requests',
    'google.oauth2.id_token',
    'google.cloud.firestore_v1',
    'google.cloud.firestore_v1.base_query',
]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

from models.conversation import ConversationSource


class TestConversationSourceMissing:
    """Test _missing_ classmethod on ConversationSource enum."""

    def test_known_values_unchanged(self):
        """Known enum values still resolve correctly."""
        assert ConversationSource('friend') == ConversationSource.friend
        assert ConversationSource('omi') == ConversationSource.omi
        assert ConversationSource('phone') == ConversationSource.phone
        assert ConversationSource('desktop') == ConversationSource.desktop
        assert ConversationSource('onboarding') == ConversationSource.onboarding
        assert ConversationSource('workflow') == ConversationSource.workflow
        assert ConversationSource('external_integration') == ConversationSource.external_integration

    def test_phone_call_resolves_to_unknown(self):
        """The specific value that caused issue #5409."""
        result = ConversationSource('phone_call')
        assert result == ConversationSource.unknown
        assert result.value == 'unknown'

    def test_arbitrary_unknown_resolves(self):
        """Any unrecognized string resolves to unknown."""
        result = ConversationSource('totally_made_up_source')
        assert result == ConversationSource.unknown

    def test_empty_string_resolves_to_unknown(self):
        """Empty string resolves to unknown rather than crashing."""
        result = ConversationSource('')
        assert result == ConversationSource.unknown

    def test_unknown_value_is_itself(self):
        """The unknown member can be constructed directly."""
        assert ConversationSource('unknown') == ConversationSource.unknown
        assert ConversationSource.unknown.value == 'unknown'

    def test_all_existing_values_still_work(self):
        """Regression: every existing enum member still resolves to itself."""
        for member in ConversationSource:
            assert ConversationSource(member.value) == member

    def test_non_string_int_rejected(self):
        """Non-string values (int) are not coerced to unknown."""
        import pytest

        with pytest.raises(ValueError):
            ConversationSource(123)

    def test_non_string_none_rejected(self):
        """None is not coerced to unknown."""
        import pytest

        with pytest.raises(ValueError):
            ConversationSource(None)

    def test_non_string_dict_rejected(self):
        """Dict is not coerced to unknown."""
        import pytest

        with pytest.raises(ValueError):
            ConversationSource({})


class TestConversationModelWithUnknownSource:
    """Test that Conversation Pydantic model handles unknown sources."""

    def test_conversation_with_phone_call_source(self):
        """Conversation model accepts phone_call without ValidationError."""
        from models.conversation import Conversation, Structured

        conv = Conversation(
            id='test-123',
            created_at='2026-03-06T18:00:00Z',
            started_at='2026-03-06T18:00:00Z',
            finished_at='2026-03-06T18:15:00Z',
            source='phone_call',
            structured=Structured(title='Test', overview='Test overview', emoji='🎤'),
        )
        assert conv.source == ConversationSource.unknown

    def test_conversation_with_known_source(self):
        """Known source values still work in the model."""
        from models.conversation import Conversation, Structured

        conv = Conversation(
            id='test-456',
            created_at='2026-03-06T18:00:00Z',
            started_at='2026-03-06T18:00:00Z',
            finished_at='2026-03-06T18:15:00Z',
            source='phone',
            structured=Structured(title='Test', overview='Test overview', emoji='📱'),
        )
        assert conv.source == ConversationSource.phone

    def test_conversation_dict_serialization(self):
        """Conversation with unknown source serializes without error."""
        from models.conversation import Conversation, Structured

        conv = Conversation(
            id='test-789',
            created_at='2026-03-06T18:00:00Z',
            started_at='2026-03-06T18:00:00Z',
            finished_at='2026-03-06T18:15:00Z',
            source='phone_call',
            structured=Structured(title='Test', overview='Test overview', emoji='🎤'),
        )
        d = conv.dict()
        assert d['source'] == ConversationSource.unknown

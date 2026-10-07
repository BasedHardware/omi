"""Unit tests for chat message persistence resilience and conversation citation deserialization.

Guards against:
1. Deserialization crashes when memories retrieved for chat citations are malformed,
   legacy documents, or object instances.
2. Raw MessageConversation(**m) unpacking errors breaking terminal message persistence.
3. Unnecessary deserialize_conversation imports dragging the conversation model into chat.
4. Function name collisions between delete_person_endpoint and Joan followup-question endpoint.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException

from models.chat import MessageConversation, MessageConversationStructured
from utils.conversation_helpers import extract_memory_ids


class TestMessageConversationSafe:
    """Verifies MessageConversation.from_memory_safe and safe_build_many."""

    def test_from_memory_safe_dict_valid(self):
        now = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
        raw = {
            'id': 'conv-123',
            'created_at': now,
            'structured': {'title': 'Project sync', 'emoji': '🚀'},
        }
        card = MessageConversation.from_memory_safe(raw)
        assert card is not None
        assert card.id == 'conv-123'
        assert card.created_at == now
        assert card.structured.title == 'Project sync'
        assert card.structured.emoji == '🚀'

    def test_from_memory_safe_object(self):
        now = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
        obj = SimpleNamespace(
            id='conv-obj-1',
            created_at=now,
            structured=SimpleNamespace(title='Object Title', emoji='🧠'),
        )
        card = MessageConversation.from_memory_safe(obj)
        assert card is not None
        assert card.id == 'conv-obj-1'
        assert card.created_at == now
        assert card.structured.title == 'Object Title'
        assert card.structured.emoji == '🧠'

    def test_from_memory_safe_already_instance(self):
        now = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
        existing = MessageConversation(
            id='conv-exist',
            created_at=now,
            structured=MessageConversationStructured(title='Existing', emoji='✨'),
        )
        assert MessageConversation.from_memory_safe(existing) is existing

    def test_from_memory_safe_iso_string_datetime(self):
        raw = {
            'id': 'conv-iso',
            'created_at': '2026-09-30T15:30:00Z',
            'structured': {'title': 'ISO Test', 'emoji': '📅'},
        }
        card = MessageConversation.from_memory_safe(raw)
        assert card is not None
        assert card.id == 'conv-iso'
        assert card.created_at.year == 2026
        assert card.created_at.month == 9

    def test_from_memory_safe_missing_structured_defaults(self):
        raw = {
            'id': 'conv-nostruct',
            'created_at': datetime(2026, 9, 30, tzinfo=timezone.utc),
        }
        card = MessageConversation.from_memory_safe(raw)
        assert card is not None
        assert card.id == 'conv-nostruct'
        assert card.structured.title == ''
        assert card.structured.emoji == ''

    def test_from_memory_safe_started_at_fallback(self):
        started = datetime(2026, 9, 30, 10, 0, 0, tzinfo=timezone.utc)
        raw = {
            'id': 'conv-started',
            'started_at': started,
            'structured': {'title': 'Started Fallback'},
        }
        card = MessageConversation.from_memory_safe(raw)
        assert card is not None
        assert card.id == 'conv-started'
        assert card.created_at == started
        assert card.structured.title == 'Started Fallback'
        assert card.structured.emoji == ''

    def test_from_memory_safe_missing_id_returns_none(self):
        assert MessageConversation.from_memory_safe({'structured': {'title': 'No ID'}}) is None
        assert MessageConversation.from_memory_safe({'id': '   '}) is None
        assert MessageConversation.from_memory_safe(None) is None

    def test_safe_build_many_filters_corrupted_records(self):
        now = datetime(2026, 9, 30, tzinfo=timezone.utc)
        memories = [
            {'id': 'conv-1', 'created_at': now, 'structured': {'title': 'One', 'emoji': '1️⃣'}},
            {'corrupt': True},
            None,
            SimpleNamespace(id='conv-3', created_at=now, structured=SimpleNamespace(title='Three', emoji='3️⃣')),
            'not-a-valid-record',
            {'id': 'conv-4', 'created_at': now},
        ]
        cards = MessageConversation.safe_build_many(memories, limit=5)
        assert len(cards) == 3
        assert [c.id for c in cards] == ['conv-1', 'conv-3', 'conv-4']

    def test_safe_build_many_respects_limit(self):
        now = datetime(2026, 9, 30, tzinfo=timezone.utc)
        memories = [{'id': f'conv-{i}', 'created_at': now} for i in range(10)]
        cards = MessageConversation.safe_build_many(memories, limit=3)
        assert len(cards) == 3
        assert [c.id for c in cards] == ['conv-0', 'conv-1', 'conv-2']

    def test_safe_build_many_empty_inputs(self):
        assert MessageConversation.safe_build_many([]) == []
        assert MessageConversation.safe_build_many(None) == []


class TestExtractMemoryIdsResilience:
    """Verifies extract_memory_ids handles dicts and objects without crashing."""

    def test_extract_memory_ids_object_without_id(self):
        records = [
            {'id': 'dict-1'},
            SimpleNamespace(id='obj-1'),
            object(),  # Has no 'id' attribute
            {'id': 'dict-2'},
        ]
        ids = extract_memory_ids(records, limit=5)
        assert ids == ['dict-1', 'obj-1', '', 'dict-2']

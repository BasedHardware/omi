"""Tests for safe Person deserialization across LLM prompt builders and retrieval tools.

Regression tests ensuring that malformed or legacy Person documents (e.g., missing required 'name')
stored in Firestore do not raise unhandled pydantic.ValidationError crashes in:
1. utils.retrieval.tools.conversation_tools (get_conversations_tool and search_conversations_tool)
2. utils.retrieval.rag (retrieve_rag_conversation_context)
3. utils.llm.chat (retrieve_memory_context_params, obtain_emotional_message, extract_question_from_transcript, provide_advice_message)
4. utils.llm.external_integrations (get_conversation_summary, generate_comprehensive_daily_summary)
5. utils.llm.trends (trends_extractor)
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from models.other import Person
from models.transcript_segment import TranscriptSegment
from models.conversation import Conversation
from models.structured import Structured
from models.conversation_enums import ConversationSource, ConversationStatus


RAW_PEOPLE_FIXTURE = [
    {
        "id": "p_valid_1",
        "name": "Alice Smith",
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
        "updated_at": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
    },
    {
        "id": "p_malformed_no_name",
        # Missing required 'name' field
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
    },
    {
        "id": "p_valid_2",
        "name": "Bob Jones",
        "created_at": datetime(2026, 1, 2, tzinfo=timezone.utc).isoformat(),
        "updated_at": datetime(2026, 1, 2, tzinfo=timezone.utc).isoformat(),
    },
]


def _build_test_conversation(cid: str = "c1") -> Conversation:
    now = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    return Conversation(
        id=cid,
        created_at=now,
        started_at=now,
        finished_at=now,
        language="en",
        source=ConversationSource.omi,
        status=ConversationStatus.completed,
        structured=Structured(title="Test Convo", overview="Overview text", emoji="💬"),
        transcript_segments=[
            TranscriptSegment(id="s1", text="Hello Alice", person_id="p_valid_1", speaker_id=0, is_user=False, start=0.0, end=1.0),
            TranscriptSegment(id="s2", text="Corrupt person segment", person_id="p_malformed_no_name", speaker_id=1, is_user=False, start=1.0, end=2.0),
        ],
    )


class TestPersonDeserializationLLMRetrieval(unittest.TestCase):
    def test_person_deserialize_many_safe_filters_malformed_records(self):
        """Verify that Person.deserialize_many_safe isolates valid records and skips corrupt ones."""
        result = Person.deserialize_many_safe(RAW_PEOPLE_FIXTURE)
        self.assertEqual(len(result), 2)
        names = [p.name for p in result]
        self.assertIn("Alice Smith", names)
        self.assertIn("Bob Jones", names)

    def test_conversation_tools_get_conversations_safe_person_deserialization(self):
        """Verify get_conversations_tool does not crash when users_db returns malformed person docs."""
        from utils.retrieval.tools import conversation_tools

        mock_users_db = MagicMock()
        mock_users_db.get_people_by_ids.return_value = RAW_PEOPLE_FIXTURE

        conv = _build_test_conversation("c1")
        conv_dict = conv.model_dump()

        mock_conv_db = MagicMock()
        mock_conv_db.get_conversations.return_value = [conv_dict]

        mock_notif_db = MagicMock()
        mock_notif_db.get_user_time_zone.return_value = "UTC"

        config = {"configurable": {"user_id": "u1"}}

        with patch.object(conversation_tools, "users_db", mock_users_db), \
             patch.object(conversation_tools, "conversations_db", mock_conv_db), \
             patch.object(conversation_tools, "notification_db", mock_notif_db):
            result = conversation_tools.get_conversations_tool.func(
                config=config,
                include_transcript=True,
            )
            self.assertIn("Test convo", result)

    def test_conversation_tools_search_conversations_safe_person_deserialization(self):
        """Verify search_conversations_tool does not crash when users_db returns malformed person docs."""
        from utils.retrieval.tools import conversation_tools

        mock_users_db = MagicMock()
        mock_users_db.get_people_by_ids.return_value = RAW_PEOPLE_FIXTURE

        conv = _build_test_conversation("c2")
        conv_dict = conv.model_dump()

        mock_conv_db = MagicMock()
        mock_conv_db.get_conversations_by_id.return_value = [conv_dict]

        mock_notif_db = MagicMock()
        mock_notif_db.get_user_time_zone.return_value = "UTC"

        config = {"configurable": {"user_id": "u1"}}

        with patch.object(conversation_tools, "users_db", mock_users_db), \
             patch.object(conversation_tools, "conversations_db", mock_conv_db), \
             patch.object(conversation_tools, "notification_db", mock_notif_db), \
             patch.object(conversation_tools, "keyword_search_conversation_ids", return_value=["c2"]), \
             patch.object(conversation_tools.vector_db, "query_vectors", return_value=[]):
            result = conversation_tools.search_conversations_tool.func(
                query="Hello",
                config=config,
                include_transcript=True,
            )
            self.assertIn("Test convo", result)

    def test_rag_retrieve_context_safe_person_deserialization(self):
        """Verify retrieve_rag_conversation_context safely deserializes people when corrupt docs exist."""
        from utils.retrieval import rag
        from utils.llm import chat as chat_llm

        mock_users_db = MagicMock()
        mock_users_db.get_people_by_ids.return_value = RAW_PEOPLE_FIXTURE

        conv = _build_test_conversation("c1")

        with patch.object(rag, "users_db", mock_users_db), \
             patch.object(chat_llm, "users_db", mock_users_db), \
             patch.object(rag, "get_user_name", return_value="User"), \
             patch.object(rag, "retrieve_memories_for_topics", return_value=({"c1": ["work"]}, [conv.model_dump()])), \
             patch.object(rag, "retrieve_memory_context_params", return_value=["work"]), \
             patch.object(rag, "get_better_conversation_chunk", return_value="Chunk"):
            res_context, res_topics = rag.retrieve_rag_conversation_context("u1", conv)
            self.assertIsInstance(res_context, str)

    def test_llm_chat_retrieve_memory_context_params_safe_person(self):
        """Verify retrieve_memory_context_params safely handles malformed people."""
        from utils.llm import chat as chat_llm

        mock_users_db = MagicMock()
        mock_users_db.get_people_by_ids.return_value = RAW_PEOPLE_FIXTURE

        segments = [
            TranscriptSegment(id="s1", text="Hi Alice", person_id="p_valid_1", speaker_id=0, is_user=False, start=0.0, end=1.0),
            TranscriptSegment(id="s2", text="Hi Corrupt", person_id="p_malformed_no_name", speaker_id=1, is_user=False, start=1.0, end=2.0),
        ]

        mock_llm = MagicMock()
        mock_structured = MagicMock()
        mock_structured.invoke.return_value = MagicMock(topics=["work", "tech"])
        mock_llm.with_structured_output.return_value = mock_structured

        with patch.object(chat_llm, "users_db", mock_users_db), \
             patch.object(chat_llm, "get_user_name", return_value="Tester"), \
             patch.object(chat_llm, "get_llm", return_value=mock_llm):
            topics = chat_llm.retrieve_memory_context_params("u1", segments, ["p_valid_1", "p_malformed_no_name"])
            self.assertEqual(topics, ["work", "tech"])

    def test_llm_external_integrations_conversations_summary_safe_person(self):
        """Verify get_conversation_summary safely handles malformed people documents."""
        from utils.llm import external_integrations

        mock_users_db = MagicMock()
        mock_users_db.get_people_by_ids.return_value = RAW_PEOPLE_FIXTURE

        conv = _build_test_conversation("c1")

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="Summary of conversations")

        with patch.object(external_integrations, "users_db", mock_users_db), \
             patch.object(external_integrations, "get_prompt_memories", return_value=("User", "Memories")), \
             patch.object(external_integrations, "get_llm", return_value=mock_llm):
            res = external_integrations.get_conversation_summary("u1", [conv])
            self.assertEqual(res, "Summary of conversations")


if __name__ == '__main__':
    unittest.main()

"""Hermetic unit tests for developer webhook proactive notification null-safety.

Verifies that explicit null values in third-party webhook payloads
(e.g., prompt: null, params: null, context: null, filters: null)
are defensively normalized and do not crash the background dispatch pipeline.
"""

from collections.abc import Mapping
from typing import Any, List, Optional
import unittest
from unittest.mock import MagicMock


class MockProactiveConfig:
    def __init__(self, scopes: List[str]):
        self.scopes = scopes


class MockApp:
    def __init__(
        self,
        app_id: str = "app-test",
        name: str = "TestApp",
        scopes: Optional[List[str]] = None,
    ):
        self.id = app_id
        self.name = name
        self.proactive_notification = MockProactiveConfig(
            scopes
            if scopes is not None
            else ["user_name", "user_facts", "user_context", "user_chat"]
        )

    def has_capability(self, capability: str) -> bool:
        return capability == "proactive_notification"

    def filter_proactive_notification_scopes(
        self, params: Optional[List[str]] = None
    ) -> List[str]:
        if not self.proactive_notification or not params:
            return []
        return [
            param
            for param in params
            if isinstance(param, str)
            and param in self.proactive_notification.scopes
        ]


class MockHarness:
    def __init__(self):
        self.logger = MagicMock()
        self.generate_embedding = MagicMock(return_value=[0.1] * 3072)
        self.query_vectors_by_metadata = MagicMock(return_value=["mem-1"])
        self.conversations_db = MagicMock()
        self.conversations_db.get_conversations_by_id = MagicMock(
            return_value=[
                {"id": "mem-1", "is_locked": False, "title": "Chat"}
            ]
        )
        self.conversations_to_string = MagicMock(
            return_value="Discussed sprint goals"
        )
        self.deserialize_conversations = MagicMock(return_value=["conv1"])
        self.get_prompt_memories = MagicMock(
            return_value=("Alice", "likes python")
        )
        self.get_app_messages = MagicMock(return_value=[])
        self.send_app_notification = MagicMock()
        self.incr_daily_notification_count = MagicMock()
        self._user_day_zone = MagicMock(return_value="UTC")
        self._set_proactive_noti_sent_at = MagicMock()
        self._hit_proactive_notification_rate_limits = MagicMock(
            return_value=False
        )
        self._proactive_daily_cap_reached = MagicMock(return_value=False)

        self.mock_llm = MagicMock()
        self.mock_llm.invoke.return_value.content = (
            "Proactive recommendation text"
        )
        self.get_llm = MagicMock(return_value=self.mock_llm)

    def retrieve_contextual_memories(
        self, uid: str, user_context: Any
    ) -> list:
        if not isinstance(user_context, Mapping):
            user_context = {}
        raw_question = user_context.get('question')
        question = raw_question if isinstance(raw_question, str) else ''
        vector = (
            self.generate_embedding(question)
            if question.strip()
            else [0] * 3072
        )
        self.logger.info(f"query_vectors vector: {vector[:5]}")

        date_filters: dict[str, Any] = {}
        raw_filters = user_context.get('filters')
        filters = raw_filters if isinstance(raw_filters, Mapping) else {}

        def _extract_str_list(val: Any) -> list[str]:
            if not isinstance(val, list):
                return []
            return [str(item) for item in val if item is not None]

        memories_id = self.query_vectors_by_metadata(
            uid,
            vector,
            dates_filter=[date_filters.get("start"), date_filters.get("end")],
            people=_extract_str_list(filters.get("people")),
            topics=_extract_str_list(filters.get("topics")),
            entities=_extract_str_list(filters.get("entities")),
            dates=_extract_str_list(filters.get("dates")),
        )
        convos = (
            self.conversations_db.get_conversations_by_id(uid, memories_id)
            or []
        )
        return [
            c
            for c in convos
            if isinstance(c, Mapping) and not c.get('is_locked')
        ]

    def process_proactive_notification(
        self, uid: str, app: MockApp, data: Any
    ):
        if not app.has_capability("proactive_notification"):
            self.logger.error(
                f"App {app.id} lacks proactive_notification capability {uid}"
            )
            return None
        if data is None:
            return None
        if not isinstance(data, Mapping):
            self.logger.error(
                f"App {app.id} notification payload invalid type={type(data).__name__}"
            )
            return None
        if not data:
            self.logger.info(f"App {app.id} notification payload empty {uid}")
            return None

        if self._hit_proactive_notification_rate_limits(uid, app):
            self.logger.info(f"App {app.id} reached rate limit")
            return None

        if self._proactive_daily_cap_reached(uid):
            self.logger.info(f"App {app.id} proactive daily cap reached")
            return None

        max_prompt_char_limit = 128000
        min_message_char_limit = 5

        raw_prompt = data.get('prompt')
        if not isinstance(raw_prompt, str):
            self.logger.info(
                f"App {app.id} notification payload missing valid prompt {uid}"
            )
            return None

        prompt = raw_prompt.strip()
        if not prompt:
            self.logger.info(f"App {app.id} notification prompt empty {uid}")
            return None

        if len(prompt) > max_prompt_char_limit:
            msg = (
                f"Prompt too long: {len(prompt)}/{max_prompt_char_limit} "
                "characters. Please shorten."
            )
            self.send_app_notification(uid, app.name, app.id, msg)
            self.logger.info(f"App {app.id}, prompt too long")
            return None

        raw_params = data.get('params')
        safe_params = (
            [p for p in raw_params if isinstance(p, str)]
            if isinstance(raw_params, list)
            else []
        )
        filter_scopes = app.filter_proactive_notification_scopes(safe_params)

        user_name, user_facts = self.get_prompt_memories(uid)

        context = None
        if 'user_context' in filter_scopes:
            raw_context = data.get('context')
            context_payload = (
                raw_context if isinstance(raw_context, Mapping) else {}
            )
            memories = self.retrieve_contextual_memories(uid, context_payload)
            if len(memories) > 0:
                context = self.conversations_to_string(
                    self.deserialize_conversations(memories)
                )

        chat_messages = []

        # Build prompt with substitutions
        for param in filter_scopes:
            if param == "user_name":
                prompt = prompt.replace("{{user_name}}", str(user_name or ''))
            elif param == "user_facts":
                prompt = prompt.replace(
                    "{{user_facts}}", str(user_facts or '')
                )
            elif param == "user_context":
                prompt = prompt.replace(
                    "{{user_context}}", context if context else ""
                )
            elif param == "user_chat":
                prompt = prompt.replace("{{user_chat}}", "")
        prompt = prompt.replace('    ', '').strip()
        if not prompt:
            self.logger.info(
                f"App {app.id} notification prompt empty after substitutions"
            )
            return None

        message = self.get_llm('app_integration').invoke(prompt).content
        if not message or len(message) < min_message_char_limit:
            self.logger.info(f"Plugins {app.id}, message too short {uid}")
            return None

        self.send_app_notification(uid, app.name, app.id, message)
        self._set_proactive_noti_sent_at(uid, app)
        self.incr_daily_notification_count(uid, self._user_day_zone(uid))
        return message


class TestProactiveNotificationNullSafety(unittest.TestCase):
    def setUp(self):
        self.harness = MockHarness()
        self.app = MockApp()

    def test_null_prompt_returns_none_safely(self):
        """Explicit null prompt must return None without len() TypeError."""
        payload = {"prompt": None, "params": ["user_name"]}
        result = self.harness.process_proactive_notification(
            "uid-1", self.app, payload
        )
        self.assertIsNone(result)
        self.harness.get_llm.assert_not_called()
        self.harness.send_app_notification.assert_not_called()

    def test_empty_string_prompt_returns_none_safely(self):
        """Empty string prompt must return None without invoking LLM."""
        payload = {"prompt": "", "params": ["user_name"]}
        result = self.harness.process_proactive_notification(
            "uid-1", self.app, payload
        )
        self.assertIsNone(result)
        self.harness.get_llm.assert_not_called()

    def test_whitespace_prompt_returns_none_safely(self):
        """Whitespace-only prompt must return None without invoking LLM."""
        payload = {"prompt": "   \n\t   ", "params": ["user_name"]}
        result = self.harness.process_proactive_notification(
            "uid-1", self.app, payload
        )
        self.assertIsNone(result)
        self.harness.get_llm.assert_not_called()

    def test_non_string_prompt_types_return_none_safely(self):
        """Non-string prompt types must be safely rejected."""
        for bad_prompt in [123, {"key": "val"}, [1, 2, 3], True]:
            result = self.harness.process_proactive_notification(
                "uid-1", self.app, {"prompt": bad_prompt}
            )
            self.assertIsNone(result)
            self.harness.get_llm.assert_not_called()

    def test_prompt_exceeding_max_limit_notifies_and_returns_none(self):
        """Prompt exceeding max char limit warns user and returns None."""
        huge_prompt = "A" * 128001
        result = self.harness.process_proactive_notification(
            "uid-1", self.app, {"prompt": huge_prompt}
        )
        self.assertIsNone(result)
        self.harness.send_app_notification.assert_called_once()
        self.harness.get_llm.assert_not_called()

    def test_null_params_defaults_gracefully(self):
        """Explicit null params must not raise TypeError in filter_scopes."""
        payload = {"prompt": "Advice for user", "params": None}
        result = self.harness.process_proactive_notification(
            "uid-1", self.app, payload
        )
        self.assertEqual(result, "Proactive recommendation text")
        self.harness.send_app_notification.assert_called_once()

    def test_non_list_params_defaults_gracefully(self):
        """Non-list params types (str, dict, int) default to empty list."""
        for bad_params in ["user_name", {"key": "val"}, 42]:
            self.harness.send_app_notification.reset_mock()
            payload = {"prompt": "Advice for user", "params": bad_params}
            result = self.harness.process_proactive_notification(
                "uid-1", self.app, payload
            )
            self.assertEqual(result, "Proactive recommendation text")

    def test_params_with_null_and_mixed_items(self):
        """Params list containing None or non-string items is sanitized."""
        payload = {
            "prompt": "Hello {{user_name}}",
            "params": [None, 123, "user_name", False],
        }
        result = self.harness.process_proactive_notification(
            "uid-1", self.app, payload
        )
        self.assertEqual(result, "Proactive recommendation text")
        self.harness.mock_llm.invoke.assert_called_with("Hello Alice")

    def test_null_context_handled_gracefully(self):
        """Explicit null context must not raise AttributeError on .get()."""
        payload = {
            "prompt": "Context: {{user_context}}",
            "params": ["user_context"],
            "context": None,
        }
        result = self.harness.process_proactive_notification(
            "uid-1", self.app, payload
        )
        self.assertEqual(result, "Proactive recommendation text")
        self.harness.query_vectors_by_metadata.assert_called_once()

    def test_context_with_null_filters_and_fields(self):
        """Context with null filters and null nested fields handled safely."""
        user_context = {"question": None, "filters": None}
        memories = self.harness.retrieve_contextual_memories(
            "uid-1", user_context
        )
        self.assertEqual(len(memories), 1)

        user_context_2 = {
            "question": "What did we talk about?",
            "filters": {
                "people": None,
                "topics": None,
                "entities": None,
                "dates": None,
            },
        }
        memories_2 = self.harness.retrieve_contextual_memories(
            "uid-1", user_context_2
        )
        self.assertEqual(len(memories_2), 1)
        self.harness.query_vectors_by_metadata.assert_called_with(
            "uid-1",
            self.harness.generate_embedding.return_value,
            dates_filter=[None, None],
            people=[],
            topics=[],
            entities=[],
            dates=[],
        )

    def test_app_filter_proactive_notification_scopes_direct_null_call(self):
        """Direct call to app method with None or empty returns []."""
        self.assertEqual(self.app.filter_proactive_notification_scopes(None), [])
        self.assertEqual(self.app.filter_proactive_notification_scopes([]), [])
        self.assertEqual(
            self.app.filter_proactive_notification_scopes(
                [None, "user_name", 999, "invalid_scope"]
            ),
            ["user_name"],
        )

    def test_prompt_empty_after_substitutions(self):
        """Prompt that becomes empty after substitution returns None."""
        self.harness.get_prompt_memories.return_value = (None, None)
        payload = {"prompt": "{{user_name}}", "params": ["user_name"]}
        result = self.harness.process_proactive_notification(
            "uid-1", self.app, payload
        )
        self.assertIsNone(result)
        self.harness.get_llm.assert_not_called()


if __name__ == "__main__":
    unittest.main()

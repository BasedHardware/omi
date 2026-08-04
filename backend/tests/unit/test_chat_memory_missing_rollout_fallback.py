"""Chat memory reads recover the un-enrolled legacy cohort (issue #10736).

An account with no `users/{uid}/memory_control/state` doc resolves to
DENY_MEMORY / `missing_rollout_state`, which is the expected state for the legacy
cohort. The Developer API (#10094) and MCP (#10095) already read the legacy
`memories` collection for that signal; the chat retrieval tools used to return
"No memories available for this request." instead, so chat answered as though the
user had no memories while the memories screen showed them normally.

These exercise the tools themselves through the adapter seam, not source text.
"""

import os
from unittest.mock import patch

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-not-real")

# Imported at module scope so the retrieval-tool import graph is paid at collection time
# rather than inside a test's call phase (backend fast-unit duration guard).
import database.memories as memory_db  # noqa: E402
import database.notifications as notification_db  # noqa: E402
import database.vector_db as vector_db  # noqa: E402
import utils.retrieval.tool_services.memories as memory_service_tools  # noqa: E402
import utils.retrieval.tools.memory_tools as memory_tools  # noqa: E402
from utils.memory.chat_memory_adapter import (  # noqa: E402
    ChatMemorySearchResult,
    chat_legacy_read_authorized,
)
from utils.memory.default_read_rollout import MemoryReadDecision  # noqa: E402
from utils.memory.memory_system import MemorySystem  # noqa: E402


def _denied(reason: str) -> ChatMemorySearchResult:
    return ChatMemorySearchResult(
        text="No memories available for this request.",
        read_decision=MemoryReadDecision.DENY_MEMORY,
        fallback_reason=reason,
    )


def _legacy_memory(memory_id: str = 'mem-1', content: str = 'LEGACY_COHORT_MEMORY') -> dict:
    return {
        'id': memory_id,
        'uid': 'u1',
        'content': content,
        'category': 'core',
        'created_at': '2026-07-27T00:00:00+00:00',
        'updated_at': '2026-07-27T00:00:00+00:00',
    }


class TestChatLegacyReadAuthorized:
    def test_missing_rollout_state_is_authorized(self):
        assert chat_legacy_read_authorized(_denied('missing_rollout_state')) is True

    def test_explicit_legacy_safe_is_authorized(self):
        legacy_safe = ChatMemorySearchResult(
            text=None, read_decision=MemoryReadDecision.USE_LEGACY_SAFE, fallback_reason='chat_legacy_safe'
        )
        assert chat_legacy_read_authorized(legacy_safe) is True

    @pytest.mark.parametrize(
        'reason',
        ['missing_chat_default_memory_grant', 'malformed_rollout_state', 'uid_mismatch', 'shadow_only'],
    )
    def test_other_deny_reasons_stay_fail_closed(self, reason):
        assert chat_legacy_read_authorized(_denied(reason)) is False


class TestChatToolsFallBackToLegacy:
    def test_get_memories_tool_serves_legacy_on_missing_rollout_state(self):
        with (
            patch.object(memory_tools, 'pin_memory_system', return_value=MemorySystem.LEGACY),
            patch.object(
                memory_tools,
                'list_default_chat_memories_decision_text',
                return_value=_denied('missing_rollout_state'),
            ),
            patch.object(memory_db, 'get_memories', return_value=[_legacy_memory()]),
        ):
            result = memory_tools.get_memories_tool.invoke(
                {'limit': 10, 'offset': 0}, config={'configurable': {'user_id': 'u1'}}
            )

        assert 'LEGACY_COHORT_MEMORY' in result
        assert 'No memories available for this request.' not in result

    def test_get_memories_tool_still_denies_other_reasons(self):
        with (
            patch.object(memory_tools, 'pin_memory_system', return_value=MemorySystem.LEGACY),
            patch.object(
                memory_tools,
                'list_default_chat_memories_decision_text',
                return_value=_denied('missing_chat_default_memory_grant'),
            ),
            patch.object(memory_db, 'get_memories', return_value=[_legacy_memory()]) as legacy_read,
        ):
            result = memory_tools.get_memories_tool.invoke(
                {'limit': 10, 'offset': 0}, config={'configurable': {'user_id': 'u1'}}
            )

        assert result == 'No memories available for this request.'
        legacy_read.assert_not_called()

    def test_search_memories_tool_serves_legacy_on_missing_rollout_state(self):
        with (
            patch.object(memory_tools, 'pin_memory_system', return_value=MemorySystem.LEGACY),
            patch.object(
                memory_tools,
                'search_memory_default_chat_memories_vector_decision_text',
                return_value=_denied('missing_rollout_state'),
            ),
            patch.object(notification_db, 'get_user_time_zone', return_value='UTC'),
            patch.object(vector_db, 'find_similar_memories', return_value=[{'memory_id': 'mem-1', 'score': 0.9}]),
            patch.object(memory_db, 'get_memories_by_ids', return_value=[_legacy_memory()]),
        ):
            result = memory_tools.search_memories_tool.invoke(
                {'query': 'coffee'}, config={'configurable': {'user_id': 'u1'}}
            )

        assert 'LEGACY_COHORT_MEMORY' in result
        assert 'No memories available for this request.' not in result

    def test_search_memories_tool_still_denies_other_reasons(self):
        with (
            patch.object(memory_tools, 'pin_memory_system', return_value=MemorySystem.LEGACY),
            patch.object(
                memory_tools,
                'search_memory_default_chat_memories_vector_decision_text',
                return_value=_denied('missing_chat_default_memory_grant'),
            ),
            patch.object(notification_db, 'get_user_time_zone', return_value='UTC'),
            patch.object(vector_db, 'find_similar_memories', return_value=[]) as vector_read,
        ):
            result = memory_tools.search_memories_tool.invoke(
                {'query': 'coffee'}, config={'configurable': {'user_id': 'u1'}}
            )

        assert result == 'No memories available for this request.'
        vector_read.assert_not_called()


class TestToolServicesFallBackToLegacy:
    """The REST tool services (desktop/web chat) share the same guard."""

    def test_get_memories_text_serves_legacy_on_missing_rollout_state(self):
        with (
            patch.object(memory_service_tools, 'pin_memory_system', return_value=MemorySystem.LEGACY),
            patch.object(
                memory_service_tools,
                'list_default_chat_memories_decision_text',
                return_value=_denied('missing_rollout_state'),
            ),
            patch.object(memory_db, 'get_memories', return_value=[_legacy_memory()]),
        ):
            result = memory_service_tools.get_memories_text(uid='u1', limit=10, offset=0)

        assert 'LEGACY_COHORT_MEMORY' in result

    def test_get_memories_text_still_denies_other_reasons(self):
        with (
            patch.object(memory_service_tools, 'pin_memory_system', return_value=MemorySystem.LEGACY),
            patch.object(
                memory_service_tools,
                'list_default_chat_memories_decision_text',
                return_value=_denied('missing_chat_default_memory_grant'),
            ),
            patch.object(memory_db, 'get_memories', return_value=[_legacy_memory()]) as legacy_read,
        ):
            result = memory_service_tools.get_memories_text(uid='u1', limit=10, offset=0)

        assert result == 'No memories available for this request.'
        legacy_read.assert_not_called()

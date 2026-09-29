"""Unit tests verifying exception sanitization in entity timeline and knowledge ledger tools.

Failure-Class: none
Ensures internal exception strings are never leaked in tool output strings.
"""

from unittest.mock import patch
from utils.retrieval.tools import entity_timeline_tools, knowledge_ledger_tools

SENTINEL_ERROR = "SENTINEL_INTERNAL_LEAK_PG_CONN_127_0_0_1_PWD_SECRET"


def test_entity_timeline_exception_sanitized():
    with patch(
        "utils.retrieval.tools.entity_timeline_tools.resolve_effective_memory_read_clock",
        side_effect=RuntimeError(SENTINEL_ERROR),
    ):
        res = entity_timeline_tools.get_entity_timeline_tool.func(
            entity_name="Alice",
            config={"configurable": {"user_id": "test-uid-123"}},
        )
    assert SENTINEL_ERROR not in res
    assert res == "Error: unsupported or invalid entity timeline request. Please try again later."


def test_knowledge_ledger_exception_sanitized():
    with patch(
        "utils.retrieval.tools.knowledge_ledger_tools.resolve_config_uid",
        side_effect=RuntimeError(SENTINEL_ERROR),
    ):
        res = knowledge_ledger_tools.read_knowledge_ledger_tool.func(
            config={"configurable": {"user_id": "test-uid-123"}},
        )
    assert SENTINEL_ERROR not in res
    assert res == "Error reading knowledge ledger. Please try again later."

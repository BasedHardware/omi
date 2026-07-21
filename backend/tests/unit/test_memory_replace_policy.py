"""Memory replace policy — legacy re-extract and cascade delete invariants."""

from __future__ import annotations

import ast
import importlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROCESS_CONVERSATION_PATH = BACKEND_DIR / "utils" / "conversations" / "process_conversation.py"
CONVERSATIONS_ROUTER_PATH = BACKEND_DIR / "routers" / "conversations.py"

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from tests.unit.memory_import_isolation import (
    install_database_client_stub,
    install_ws_i_heavy_import_stubs,
    restore_sys_modules,
    snapshot_sys_modules,
)


@pytest.fixture(scope="module", autouse=True)
def _memory_replace_import_isolation():
    saved = snapshot_sys_modules(["database._client"])
    install_database_client_stub()
    touched = install_ws_i_heavy_import_stubs()
    saved.update(snapshot_sys_modules(touched))
    yield
    restore_sys_modules(saved)


def _load_process_conversation():
    for name in list(sys.modules):
        if name == "utils.conversations.process_conversation" or name.startswith(
            "utils.conversations.process_conversation."
        ):
            del sys.modules[name]
    return importlib.import_module("utils.conversations.process_conversation")


def _function_body(source: str, fn_name: str) -> str:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == fn_name:
            start = node.lineno - 1
            end = node.end_lineno
            lines = source.splitlines()
            return "\n".join(lines[start:end])
    raise AssertionError(f"{fn_name} not found")


def test_legacy_extract_deletes_only_after_successful_parse():
    """Legacy re-extract must not delete conversation memories before extraction completes."""
    source = PROCESS_CONVERSATION_PATH.read_text(encoding="utf-8")
    body = _function_body(source, "_extract_memories_legacy")
    delete_idx = body.index("delete_memories_for_conversation")
    extract_idx = body.index("new_memories_extractor")
    save_idx = body.index("save_memories")
    assert (
        extract_idx < delete_idx < save_idx
    ), "legacy path must extract, then delete old conversation memories, then save new ones"


def test_canonical_extract_retracts_only_after_successful_parse():
    """Canonical re-extract must not retract before extraction completes."""
    source = PROCESS_CONVERSATION_PATH.read_text(encoding="utf-8")
    body = _function_body(source, "_extract_memories_canonical")
    retract_idx = body.index("retract_conversation_memories")
    extract_idx = body.index("new_memories_extractor")
    write_idx = body.index("memory_service.write")
    assert extract_idx < retract_idx < write_idx


def test_cascade_delete_cleans_memories_before_conversation_doc():
    """Cascade delete must remove memories/action-items before the conversation document."""
    source = CONVERSATIONS_ROUTER_PATH.read_text(encoding="utf-8")
    fn_start = source.index("def delete_conversation(")
    fn_end = source.index("\n@router.", fn_start)
    body = source[fn_start:fn_end]
    conv_delete_idx = body.index("conversations_db.delete_conversation")
    cascade_idx = body.index("if cascade:")
    memories_idx = body.index("delete_memories_for_conversation")
    action_items_idx = body.index("delete_action_items_for_conversation")
    assert cascade_idx < memories_idx < conv_delete_idx
    assert cascade_idx < action_items_idx < conv_delete_idx


@pytest.mark.parametrize("extractor_side_effect", [Exception("llm down"), []])
def test_legacy_reextract_failure_preserves_existing_memories(extractor_side_effect, monkeypatch):
    """If extraction fails or yields nothing, prior conversation memories must remain."""
    pc = _load_process_conversation()
    from models.conversation import Conversation
    from models.conversation_enums import CategoryEnum, ConversationSource
    from models.structured import Structured

    legacy_delete = sys.modules["database.memories"].delete_memories_for_conversation
    legacy_delete.reset_mock(return_value={"vector_delete_ids": ["old-mem-1"]})
    legacy_save = sys.modules["database.memories"].save_memories
    legacy_save.reset_mock()

    monkeypatch.setattr(
        pc,
        "new_memories_extractor",
        MagicMock(
            side_effect=extractor_side_effect if isinstance(extractor_side_effect, Exception) else lambda *a, **k: []
        ),
    )
    monkeypatch.setattr(
        pc,
        "memory_system_request_scope",
        lambda uid: MagicMock(__enter__=lambda s: pc.MemorySystem.LEGACY, __exit__=lambda *a: None),
    )

    conversation = Conversation(
        id="conv-preserve",
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        started_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        finished_at=datetime(2026, 6, 1, 1, tzinfo=timezone.utc),
        source=ConversationSource.omi,
        structured=Structured(title="Test", overview="Overview", category=CategoryEnum.personal),
        transcript_segments=[],
    )

    if isinstance(extractor_side_effect, Exception):
        with pytest.raises(Exception, match="llm down"):
            pc._extract_memories_inner("uid-preserve", conversation)
    else:
        pc._extract_memories_inner("uid-preserve", conversation)

    legacy_delete.assert_not_called()
    legacy_save.assert_not_called()


@pytest.mark.parametrize("extractor_side_effect", [Exception("llm down"), []])
def test_canonical_reextract_failure_preserves_existing_memories(extractor_side_effect, monkeypatch):
    """Canonical path: extraction failure or empty result must not retract or write."""
    pc = _load_process_conversation()
    from models.conversation import Conversation
    from models.conversation_enums import CategoryEnum, ConversationSource
    from models.structured import Structured

    # Intercept the MemoryService created inside _extract_memories_canonical
    mock_service = MagicMock()
    monkeypatch.setattr(pc, "MemoryService", lambda db_client: mock_service)

    monkeypatch.setattr(
        pc,
        "new_memories_extractor",
        MagicMock(
            side_effect=extractor_side_effect if isinstance(extractor_side_effect, Exception) else lambda *a, **k: []
        ),
    )
    monkeypatch.setattr(
        pc,
        "memory_system_request_scope",
        lambda uid: MagicMock(__enter__=lambda s: pc.MemorySystem.CANONICAL, __exit__=lambda *a: None),
    )
    monkeypatch.setattr(pc.users_db, "get_user_language_preference", lambda uid: "en")

    conversation = Conversation(
        id="conv-canonical-preserve",
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        started_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        finished_at=datetime(2026, 6, 1, 1, tzinfo=timezone.utc),
        source=ConversationSource.omi,
        structured=Structured(title="Test", overview="Overview", category=CategoryEnum.personal),
        transcript_segments=[],
    )

    if isinstance(extractor_side_effect, Exception):
        with pytest.raises(Exception, match="llm down"):
            pc._extract_memories_inner("uid-canonical-preserve", conversation)
    else:
        pc._extract_memories_inner("uid-canonical-preserve", conversation)

    mock_service.retract_conversation_memories.assert_not_called()
    mock_service.write.assert_not_called()

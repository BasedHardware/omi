"""WS-D upstream boundary locks — Conversations are never Memories.

Characterization + structural tests against the live extraction seam. No production
module changes; asserts invariants WS-I must preserve.
"""

import ast
import importlib
import os
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROCESS_CONVERSATION_PATH = BACKEND_DIR / "utils" / "conversations" / "process_conversation.py"


class _AutoMockModule(ModuleType):
    def __getattr__(self, name):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


def _collection_constant(relative_module: str, constant_name: str) -> str:
    """Read a module-level string constant without importing the database module."""
    module_path = BACKEND_DIR / relative_module
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == constant_name:
                value = node.value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    return value.value
    raise AssertionError(f"{constant_name} not found in {relative_module}")


def _ensure_process_conversation_importable():
    """Stub heavy deps so process_conversation can be imported in unit tests."""
    stubs = [
        "anthropic",
        "av",
        "database._client",
        "database.cache",
        "database.redis_db",
        "database.conversations",
        "database.memories",
        "database.short_term_memories",
        "database.action_items",
        "database.folders",
        "database.users",
        "database.user_usage",
        "database.vector_db",
        "database.chat",
        "database.apps",
        "database.goals",
        "database.notifications",
        "database.tasks",
        "database.trends",
        "database.calendar_meetings",
        "database.auth",
        "deepgram",
        "firebase_admin",
        "firebase_admin.messaging",
        "firebase_admin.auth",
        "google.cloud.firestore",
        "google.cloud.firestore_v1",
        "langchain_core",
        "langchain_core.output_parsers",
        "langchain_core.callbacks",
        "langchain_core.language_models",
        "langchain_core.prompts",
        "langchain_core.runnables",
        "langchain_core.tools",
        "langchain_openai",
        "openai",
        "pinecone",
        "pytz",
        "tiktoken",
        "typesense",
        "modal",
        "utils.other.storage",
        "utils.other.hume",
        "utils.webhooks",
        "utils.task_sync",
        "utils.analytics",
        "utils.retrieval.rag",
        "utils.llm.memories",
        "utils.llm.conversation_processing",
        "utils.llm.external_integrations",
        "utils.llm.trends",
        "utils.llm.goals",
        "utils.llm.chat",
        "utils.llm.clients",
        "utils.llm.usage_tracker",
        "utils.conversations.factory",
        "utils.conversations.subjects",
        "utils.conversations.transcript_chunks",
        "utils.conversations.calendar_linking",
        "utils.notifications",
        "utils.apps",
        "utils.executors",
        "utils.subscription",
        "utils.task_intelligence.workstream_association",
    ]
    for mod_name in stubs:
        if mod_name not in sys.modules:
            mod = _AutoMockModule(mod_name)
            if mod_name in ("langchain_core",) or mod_name.startswith("langchain_core."):
                mod.__path__ = []
            sys.modules[mod_name] = mod

    client = sys.modules["database._client"]
    if not getattr(client, "document_id_from_seed", None) or isinstance(
        getattr(client, "document_id_from_seed"), MagicMock
    ):
        import hashlib
        import uuid as uuid_mod

        def _document_id_from_seed(seed: str) -> str:
            seed_hash = hashlib.sha256(seed.encode("utf-8")).digest()
            return str(uuid_mod.UUID(bytes=seed_hash[:16], version=4))

        client.document_id_from_seed = _document_id_from_seed
        client.db = MagicMock()

    executors = sys.modules["utils.executors"]
    executors.postprocess_executor = MagicMock()
    executors.submit_with_context = MagicMock()

    usage = sys.modules["utils.llm.usage_tracker"]
    usage.track_usage = MagicMock(return_value=types.SimpleNamespace(__enter__=lambda s: s, __exit__=lambda *a: None))
    usage.Features = types.SimpleNamespace(
        MEMORIES=MagicMock(),
        CONVERSATION_ACTION_ITEMS=MagicMock(),
        GOALS=MagicMock(),
        CONVERSATION_FOLDER=MagicMock(),
    )
    sys.modules["utils.task_intelligence.workstream_association"].associate_canonical_evidence = MagicMock()

    sys.modules.pop("utils.conversations.process_conversation", None)
    return importlib.import_module("utils.conversations.process_conversation")


class TestStoreSeparation:
    """Firestore collection names must stay disjoint — no silent store aliasing."""

    def test_conversation_and_memory_collections_are_distinct_constants(self):
        conversations_collection = _collection_constant("database/conversations.py", "conversations_collection")
        memories_collection = _collection_constant("database/memories.py", "memories_collection")
        short_term_collection = _collection_constant("database/short_term_memories.py", "short_term_collection")
        action_items_collection = _collection_constant("database/action_items.py", "action_items_collection")
        goals_collection = _collection_constant("database/goals.py", "goals_collection")

        memory_stores = {memories_collection, short_term_collection}
        workflow = {action_items_collection, goals_collection}

        assert conversations_collection not in memory_stores
        assert conversations_collection not in workflow
        assert memory_stores.isdisjoint(workflow)


class TestExtractionSeamFanOut:
    """process_conversation must fan out to separate downstream writers."""

    def test_process_conversation_submits_three_separate_postprocess_tasks(self):
        source = PROCESS_CONVERSATION_PATH.read_text(encoding="utf-8")
        # Characterization of the live seam — WS-I must keep three distinct destinations.
        assert "submit_with_context(postprocess_executor, _extract_memories" in source
        assert "submit_with_context(postprocess_executor, _save_action_items" in source
        assert "submit_with_context(postprocess_executor, _update_goal_progress" in source

    def test_fan_out_invokes_memory_action_item_and_goal_paths_separately(self):
        """Functional: mocked postprocess submits must hit three different callables."""
        pc = _ensure_process_conversation_importable()

        from models.conversation import Conversation
        from models.conversation_enums import CategoryEnum, ConversationSource
        from models.structured import Structured
        from models.transcript_segment import TranscriptSegment

        submitted = []

        def _capture_submit(_executor, fn, *args, **kwargs):
            submitted.append((fn, args))

        conversation = Conversation(
            id="conv-fanout-1",
            created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
            started_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
            finished_at=datetime(2026, 6, 1, 1, tzinfo=timezone.utc),
            source=ConversationSource.omi,
            folder_id="folder-existing",
            structured=Structured(
                title="Boundary test",
                overview="User discussed weekend hiking plans.",
                category=CategoryEnum.personal,
            ),
            transcript_segments=[
                TranscriptSegment(
                    text="I went hiking last weekend.",
                    speaker_id=0,
                    is_user=True,
                    person_id=None,
                    start=0.0,
                    end=2.0,
                )
            ],
        )

        structured = conversation.structured

        with (
            patch.object(pc, "is_trial_paywalled", return_value=False),
            patch.object(pc.redis_db, "get_conversation_meeting_id", return_value=None),
            patch.object(pc, "_get_structured", return_value=(structured, False)),
            patch.object(pc, "_get_conversation_obj", return_value=conversation),
            patch.object(pc, "_trigger_apps"),
            patch.object(pc.conversations_db, "upsert_conversation"),
            patch.object(pc, "submit_with_context", side_effect=_capture_submit),
            patch.object(pc, "TRANSCRIPT_CHUNK_INDEXING_ENABLED", False),
        ):
            pc.process_conversation("uid-boundary", "en", conversation, is_reprocess=True)

        submitted_fns = {fn.__name__ for fn, _ in submitted if callable(fn) and hasattr(fn, "__name__")}
        assert "_extract_memories" in submitted_fns
        assert "_save_action_items" in submitted_fns
        assert "_update_goal_progress" in submitted_fns
        assert (
            len(submitted_fns.intersection({"_extract_memories", "_save_action_items", "_update_goal_progress"})) == 3
        )


class TestNoConversationAsMemory:
    """Memory creation must persist extracted facts, not the Conversation record."""

    def test_extract_memories_inner_calls_extractor_with_segments_not_conversation_dict(self):
        pc = _ensure_process_conversation_importable()

        from models.conversation import Conversation
        from models.conversation_enums import CategoryEnum, ConversationSource
        from models.memories import Memory, MemoryCategory
        from models.structured import Structured
        from models.transcript_segment import TranscriptSegment

        conversation = Conversation(
            id="conv-extract-1",
            created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
            started_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
            finished_at=datetime(2026, 6, 1, 1, tzinfo=timezone.utc),
            source=ConversationSource.omi,
            structured=Structured(
                title="Hike",
                overview="Weekend hike in the mountains.",
                category=CategoryEnum.personal,
            ),
            transcript_segments=[
                TranscriptSegment(
                    text="I love hiking on weekends.",
                    speaker_id=0,
                    is_user=True,
                    person_id=None,
                    start=0.0,
                    end=2.0,
                )
            ],
        )
        extracted = Memory(content="User loves hiking on weekends.", category=MemoryCategory.interesting)

        saved_payloads = []

        with (
            patch.object(pc.memories_db, "delete_memories_for_conversation") as mock_delete,
            patch.object(pc, "delete_memory_vector"),
            patch.object(pc.users_db, "get_user_language_preference", return_value="en"),
            patch.object(pc, "new_memories_extractor", return_value=[extracted]) as mock_extractor,
            patch.object(pc, "find_similar_memories", return_value=[]),
            patch.object(pc, "infer_subject_from_segments", return_value=(None, "unknown")),
            patch.object(
                pc.memories_db,
                "save_memories",
                side_effect=lambda _uid, rows: saved_payloads.extend(rows),
            ),
            patch.object(pc, "record_usage"),
        ):
            mock_delete.return_value = {"vector_delete_ids": []}
            pc._extract_memories_inner("uid-extract", conversation)

        mock_extractor.assert_called_once()
        extractor_args = mock_extractor.call_args[0]
        assert extractor_args[0] == "uid-extract"
        assert extractor_args[1] is conversation.transcript_segments
        assert extractor_args[1] is not conversation
        assert not isinstance(extractor_args[1], dict)

        assert len(saved_payloads) == 1
        row = saved_payloads[0]
        assert row["content"] == extracted.content
        assert row["conversation_id"] == conversation.id
        assert row["evidence"][0]["source_id"] == conversation.id
        # Must not be a verbatim Conversation document.
        assert "transcript_segments" not in row
        assert "structured" not in row
        assert row.get("id") != conversation.id

    def test_extract_memories_inner_external_integration_uses_text_not_conversation(self):
        pc = _ensure_process_conversation_importable()

        from models.conversation import Conversation
        from models.conversation_enums import CategoryEnum, ConversationSource
        from models.memories import Memory, MemoryCategory
        from models.structured import Structured

        integration_text = "Imported email: user prefers morning meetings on Tuesdays."
        conversation = Conversation(
            id="conv-ext-1",
            created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
            started_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
            finished_at=datetime(2026, 6, 1, 1, tzinfo=timezone.utc),
            source=ConversationSource.external_integration,
            external_data={"text": integration_text, "text_source": "email"},
            structured=Structured(
                title="Imported email",
                overview="External integration import.",
                category=CategoryEnum.personal,
            ),
        )
        extracted = Memory(content="User prefers morning meetings on Tuesdays.", category=MemoryCategory.interesting)

        saved_payloads = []

        with (
            patch.object(pc.memories_db, "delete_memories_for_conversation") as mock_delete,
            patch.object(pc, "delete_memory_vector"),
            patch.object(pc.users_db, "get_user_language_preference", return_value="en"),
            patch.object(pc, "extract_memories_from_text", return_value=[extracted]) as mock_text_extractor,
            patch.object(pc, "new_memories_extractor") as mock_segment_extractor,
            patch.object(pc, "find_similar_memories", return_value=[]),
            patch.object(pc, "infer_subject_from_segments", return_value=(None, "unknown")),
            patch.object(
                pc.memories_db,
                "save_memories",
                side_effect=lambda _uid, rows: saved_payloads.extend(rows),
            ),
            patch.object(pc, "record_usage"),
        ):
            mock_delete.return_value = {"vector_delete_ids": []}
            pc._extract_memories_inner("uid-ext", conversation)

        mock_text_extractor.assert_called_once_with("uid-ext", integration_text, "email", language="en")
        mock_segment_extractor.assert_not_called()

        text_arg = mock_text_extractor.call_args[0][1]
        assert text_arg == integration_text
        assert text_arg is not conversation
        assert not isinstance(text_arg, dict)

        assert len(saved_payloads) == 1
        row = saved_payloads[0]
        assert row["content"] == extracted.content
        assert row["conversation_id"] == conversation.id
        assert "transcript_segments" not in row
        assert "structured" not in row

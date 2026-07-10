"""
Tests for issue #4626: AttributeError in knowledge graph extraction.

get_user_store_recording_permission() returns a bool, but the KG extraction
code treated it as a user dict and called .get('name', 'User') on it.

Fix: use get_user_name() from database/auth.py which reads display_name
from Firebase Auth — the canonical way to get user names in this codebase.

utils.conversations.process_conversation pulls in a large chain of heavy
database.* / utils.* modules (pinecone, typesense, langchain, …) that are not
import-pure yet, so the module is exec'd fresh inside a module-scoped
stub_modules block (the sanctioned Tier-2 reserve seam — see
backend/docs/test_isolation.md and testing/import_isolation.load_module_fresh).
models.memories is pre-imported outside the block so that
@patch("models.memories.MemoryDB.from_memory") patches the same class object
that the freshly-loaded process_conversation binds.
"""

import importlib
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules

_BACKEND = Path(__file__).resolve().parents[2]

# Populated by the ``_load_process_conversation`` module-scoped fixture so the
# test bodies can reference the freshly-loaded module and its stubbed
# dependencies by their original names.
process_conversation = None
auth_mod = None
llm_kg = None
memories_mod = None
vector_db_mod = None
llm_memories = None
utils_analytics = None


def _build_fakes() -> dict[str, ModuleType]:
    """Build the sys.modules fakes consumed by ``stub_modules``."""
    fakes: dict[str, ModuleType] = {}

    def add(name: str) -> AutoMockModule:
        mod = AutoMockModule(name)
        fakes[name] = mod
        return mod

    # database._client — real attrs the code under test binds by name.
    client_mod = ModuleType("database._client")
    client_mod.db = MagicMock()
    client_mod.document_id_from_seed = MagicMock(return_value="doc-id")
    fakes["database._client"] = client_mod

    # database.auth — stub with the canonical user-name function under test.
    auth = add("database.auth")
    auth.get_user_name = MagicMock(return_value="The User")
    auth.get_user_from_uid = MagicMock()

    users = add("database.users")
    users.get_user_language_preference = MagicMock(return_value='en')
    users.get_people_by_ids = MagicMock(return_value=[])

    vector_db = add("database.vector_db")
    for attr in [
        "find_similar_memories",
        "upsert_memory_vector",
        "delete_memory_vector",
        "upsert_action_item_vectors_batch",
        "delete_action_item_vectors_batch",
        "find_similar_action_items",
        "upsert_vector2",
        "update_vector_metadata",
        "upsert_transcript_chunk_vectors",
    ]:
        setattr(vector_db, attr, MagicMock())

    apps = add("database.apps")
    for attr in ["record_app_usage", "get_omi_personas_by_uid_db", "get_app_by_id_db"]:
        setattr(apps, attr, MagicMock())

    llm_usage = add("database.llm_usage")
    llm_usage.record_llm_usage = MagicMock()

    # Redis stubs needed transitively by database.auth.
    redis_mod = add("database.redis_db")
    redis_mod.cache_user_name = MagicMock()
    redis_mod.get_cached_user_name = MagicMock(return_value=None)

    memories = add("database.memories")
    memories.set_memory_kg_extracted = MagicMock()
    memories.get_memory_ids_for_conversation = MagicMock(return_value=[])
    memories.delete_memories_for_conversation = MagicMock()
    memories.get_memory = MagicMock(return_value=None)
    memories.save_memories = MagicMock()
    memories.delete_memory = MagicMock()

    entities = add("database.entities")
    entities.USER_ENTITY_ID = "entity:user"
    entities.person_entity_id = MagicMock(side_effect=lambda person_id: f"entity:person:{person_id}")

    # database.* modules imported by process_conversation but not overridden above.
    for name in [
        "database.conversations",
        "database.notifications",
        "database.tasks",
        "database.action_items",
        "database.folders",
        "database.calendar_meetings",
    ]:
        add(name)

    # utils.apps
    utils_apps = add("utils.apps")
    for attr in ["get_available_apps", "update_personas_async", "update_persona_prompt", "sync_update_persona_prompt"]:
        setattr(utils_apps, attr, MagicMock())

    utils_analytics = add("utils.analytics")
    utils_analytics.record_usage = MagicMock()

    llm_memories = add("utils.llm.memories")
    for attr in ["resolve_memory_conflict", "extract_memories_from_text", "new_memories_extractor"]:
        setattr(llm_memories, attr, MagicMock())

    llm_conv = add("utils.llm.conversation_processing")
    llm_conv_folder = add("utils.llm.conversation_folder")
    llm_conv_folder.assign_conversation_to_folder = MagicMock()
    for attr in [
        "get_transcript_structure",
        "get_app_result",
        "should_discard_conversation",
        "select_best_app_for_conversation",
        "get_suggested_apps_for_conversation",
        "get_reprocess_transcript_structure",
        "assign_conversation_to_folder",
        "extract_action_items",
    ]:
        setattr(llm_conv, attr, MagicMock())

    llm_external = add("utils.llm.external_integrations")
    for attr in ["summarize_experience_text", "get_message_structure"]:
        setattr(llm_external, attr, MagicMock())

    llm_trends = add("utils.llm.trends")
    llm_trends.trends_extractor = MagicMock()

    llm_goals = add("utils.llm.goals")
    llm_goals.extract_and_update_goal_progress = MagicMock()

    llm_chat = add("utils.llm.chat")
    for attr in [
        "retrieve_metadata_from_text",
        "retrieve_metadata_from_message",
        "retrieve_metadata_fields_from_transcript",
        "obtain_emotional_message",
    ]:
        setattr(llm_chat, attr, MagicMock())

    llm_clients = add("utils.llm.clients")
    llm_clients.generate_embedding = MagicMock()

    llm_kg = add("utils.llm.knowledge_graph")
    llm_kg.extract_knowledge_from_memory = MagicMock()

    @contextmanager
    def _track_usage_stub(*_args, **_kwargs):
        yield

    llm_usage_tracker = add("utils.llm.usage_tracker")
    llm_usage_tracker.track_usage = _track_usage_stub
    llm_usage_tracker.Features = SimpleNamespace(
        CONVERSATION_STRUCTURE="conversation_structure",
        CONVERSATION_ACTION_ITEMS="conversation_action_items",
        CONVERSATION_DISCARD="conversation_discard",
        CONVERSATION_APPS="conversation_apps",
        CONVERSATION_FOLDER="conversation_folder",
        GOALS="goals",
        MEMORIES="memories",
        TRENDS="trends",
    )

    utils_notifications = add("utils.notifications")
    for attr in ["send_notification", "send_important_conversation_message", "send_action_item_data_message"]:
        setattr(utils_notifications, attr, MagicMock())

    utils_subscription = add("utils.subscription")
    utils_subscription.is_trial_paywalled = MagicMock(return_value=False)
    utils_subscription.should_defer_desktop_processing = MagicMock(return_value=False)

    utils_hume = add("utils.other.hume")
    for attr in ["get_hume", "HumeJobCallbackModel", "HumeJobModelPredictionResponseModel"]:
        setattr(utils_hume, attr, MagicMock())

    utils_rag = add("utils.retrieval.rag")
    utils_rag.retrieve_rag_conversation_context = MagicMock()

    utils_webhooks = add("utils.webhooks")
    utils_webhooks.conversation_created_webhook = MagicMock()

    utils_task_sync = add("utils.task_sync")
    utils_task_sync.auto_sync_action_items_batch = MagicMock()

    task_intelligence = ModuleType("utils.task_intelligence")
    task_intelligence.__path__ = []  # type: ignore[attr-defined]
    fakes["utils.task_intelligence"] = task_intelligence
    conversation_capture = add("utils.task_intelligence.conversation_capture")
    conversation_capture.capture_enabled = MagicMock(return_value=False)
    conversation_capture.process_before_legacy = MagicMock(return_value=False)
    conversation_capture.canonical_fields = MagicMock(return_value={})
    conversation_capture.legacy_document_ids = MagicMock(return_value=None)
    conversation_capture.reconcile_after_legacy = MagicMock()
    task_intelligence.conversation_capture = conversation_capture

    utils_storage = add("utils.other.storage")
    utils_storage.precache_conversation_audio = MagicMock()

    utils_calendar_linking = add("utils.conversations.calendar_linking")
    utils_calendar_linking.get_overlapping_calendar_event = MagicMock(return_value=None)
    utils_calendar_linking.write_conversation_link_to_calendar_event = MagicMock()

    # utils.conversations.* and utils.memory.* leaves imported by process_conversation.
    subjects = add("utils.conversations.subjects")
    subjects.infer_subject_from_segments = lambda segments: (None, None)
    for name in [
        "utils.conversations.factory",
        "utils.conversations.transcript_chunks",
        "utils.memory.canonical_activation",
        "utils.memory.memory_service",
        "utils.memory.memory_system",
        "utils.memory.memory_system_pin",
        "utils.memory.canonical_memory_adapter",
        "utils.memory.memory_api_contract",
        "utils.executors",
    ]:
        add(name)

    # Parent packages — empty __path__ so no disk fallback pulls heavy chains.
    for pkg in [
        "database",
        "utils",
        "utils.llm",
        "utils.conversations",
        "utils.memory",
        "utils.retrieval",
        "utils.other",
    ]:
        if pkg not in fakes:
            m = ModuleType(pkg)
            m.__path__ = []  # type: ignore[attr-defined]
            fakes[pkg] = m

    return fakes


@pytest.fixture(scope="module", autouse=True)
def _load_process_conversation():
    """Load a fresh utils.conversations.process_conversation against stubbed deps."""
    # Pre-import models.memories OUTSIDE the stub block so it is in the
    # stub_modules saved_keys set (not evicted on teardown). This keeps the
    # MemoryDB class object identical for @patch("models.memories.MemoryDB.from_memory")
    # and the reference process_conversation binds at fresh-load time.
    importlib.import_module("models.memories")
    # Ensure the models package attribute points at the pre-imported module.
    setattr(sys.modules["models"], "memories", sys.modules["models.memories"])

    fakes = _build_fakes()
    with stub_modules(fakes):
        pc = load_module_fresh(
            "utils.conversations.process_conversation",
            os.path.join(str(_BACKEND), "utils", "conversations", "process_conversation.py"),
        )
        global process_conversation, auth_mod, llm_kg, memories_mod, vector_db_mod, llm_memories, utils_analytics
        process_conversation = pc
        auth_mod = fakes["database.auth"]
        llm_kg = fakes["utils.llm.knowledge_graph"]
        memories_mod = fakes["database.memories"]
        vector_db_mod = fakes["database.vector_db"]
        llm_memories = fakes["utils.llm.memories"]
        utils_analytics = fakes["utils.analytics"]
        yield


@pytest.fixture(autouse=True)
def _restore_module_bindings():
    """Re-bind get_user_name onto process_conversation before each test."""
    if "models.memories" not in sys.modules:
        importlib.import_module("models.memories")
    setattr(sys.modules["models"], "memories", sys.modules["models.memories"])
    auth_mod.get_user_name = MagicMock(return_value="The User")
    process_conversation.get_user_name = auth_mod.get_user_name


def _make_conversation_mock():
    """Create a mock Conversation that passes through _extract_memories_inner."""
    conv = MagicMock()
    conv.id = "conv-test"
    conv.source = "audio"  # not external_integration
    conv.transcript_segments = []
    conv.is_locked = False
    return conv


def _make_memory_mock(memory_id="mem-1", content="Test memory", kg_extracted=False):
    """Create a mock that behaves like a MemoryDB for the KG extraction block."""
    m = MagicMock()
    m.id = memory_id
    m.content = content
    m.category.value = "core"
    m.kg_extracted = kg_extracted
    m.is_locked = False
    m.dict.return_value = {"id": memory_id, "content": content, "category": "core"}
    return m


def _make_raw_memory(content="Test memory"):
    """Create a raw extracted memory mock with content for duplicate filtering."""
    memory = MagicMock()
    memory.content = content
    return memory


def _setup_extract_memories(memory_mock):
    """Configure stubs so _extract_memories_inner reaches the KG block with one memory."""
    llm_memories.new_memories_extractor.return_value = [_make_raw_memory(memory_mock.content)]
    vector_db_mod.find_similar_memories.return_value = []
    memories_mod.get_memory_ids_for_conversation.return_value = []
    memories_mod.save_memories.reset_mock()
    utils_analytics.record_usage.reset_mock()


class TestKnowledgeGraphUserLookup:
    """Tests for #4626: KG extraction must use get_user_name from database.auth."""

    def test_kg_extraction_calls_get_user_name_not_permission(self):
        """The KG extraction path must call get_user_name(), not get_user_store_recording_permission."""
        import inspect

        source = inspect.getsource(process_conversation._extract_memories_legacy)
        # Must NOT call the bool-returning function
        assert (
            "get_user_store_recording_permission" not in source
        ), "KG extraction still calls get_user_store_recording_permission (returns bool)"
        # Must NOT call get_user_profile (Firestore has no 'name' field)
        assert (
            "get_user_profile" not in source
        ), "KG extraction calls get_user_profile but Firestore users have no 'name' field"
        # Must call get_user_name from database.auth
        assert "get_user_name" in source

    def test_kg_router_uses_get_user_name(self):
        """Verify knowledge_graph router also uses get_user_name, not get_user_profile."""
        from pathlib import Path

        router_path = Path(__file__).resolve().parent.parent.parent / "routers" / "knowledge_graph.py"
        source = router_path.read_text(encoding="utf-8")
        assert "get_user_name" in source, "Router should use get_user_name from database.auth"
        assert (
            "get_user_profile" not in source
        ), "Router should NOT use get_user_profile (Firestore has no 'name' field)"

    @patch("models.memories.MemoryDB.from_memory")
    def test_kg_extraction_no_attribute_error_when_permission_true(self, mock_from_memory):
        """Regression: calling .get('name') on True raised AttributeError."""
        uid = "test-user-123"
        conv = _make_conversation_mock()
        mem_db = _make_memory_mock("mem-1", "Test memory content")
        mock_from_memory.return_value = mem_db

        _setup_extract_memories(mem_db)
        auth_mod.get_user_name.reset_mock()
        auth_mod.get_user_name.return_value = "Alice"
        llm_kg.extract_knowledge_from_memory.reset_mock()
        memories_mod.set_memory_kg_extracted.reset_mock()

        # This would raise AttributeError before the fix (True.get('name'))
        process_conversation._extract_memories_inner(uid, conv)

        # Verify get_user_name was called
        auth_mod.get_user_name.assert_called_once_with(uid)
        # Verify KG extraction was called with the user's name
        llm_kg.extract_knowledge_from_memory.assert_called_once_with(uid, "Test memory content", "mem-1", "Alice")

    @patch("models.memories.MemoryDB.from_memory")
    def test_kg_extraction_default_name_when_user_not_found(self, mock_from_memory):
        """When get_user_name returns default 'The User', KG extraction uses it."""
        uid = "uid-2"
        conv = _make_conversation_mock()
        mem_db = _make_memory_mock("mem-2", "Another memory")
        mock_from_memory.return_value = mem_db

        _setup_extract_memories(mem_db)
        auth_mod.get_user_name.reset_mock()
        auth_mod.get_user_name.return_value = "The User"
        llm_kg.extract_knowledge_from_memory.reset_mock()

        process_conversation._extract_memories_inner(uid, conv)

        llm_kg.extract_knowledge_from_memory.assert_called_once_with(uid, "Another memory", "mem-2", "The User")

    @patch("models.memories.MemoryDB.from_memory")
    def test_kg_extraction_handles_none_name(self, mock_from_memory):
        """When get_user_name returns None, KG extraction still works."""
        uid = "uid-none"
        conv = _make_conversation_mock()
        mem_db = _make_memory_mock("mem-4", "Memory four")
        mock_from_memory.return_value = mem_db

        _setup_extract_memories(mem_db)
        auth_mod.get_user_name.reset_mock()
        auth_mod.get_user_name.return_value = None
        llm_kg.extract_knowledge_from_memory.reset_mock()

        process_conversation._extract_memories_inner(uid, conv)

        llm_kg.extract_knowledge_from_memory.assert_called_once_with(uid, "Memory four", "mem-4", None)

    @patch("models.memories.MemoryDB.from_memory")
    def test_kg_extraction_multiple_memories(self, mock_from_memory):
        """KG extraction runs for each non-extracted memory in a batch."""
        uid = "uid-multi"
        conv = _make_conversation_mock()
        mem1 = _make_memory_mock("mem-a", "First memory", kg_extracted=False)
        mem2 = _make_memory_mock("mem-b", "Second memory", kg_extracted=False)
        mem3 = _make_memory_mock("mem-c", "Third memory", kg_extracted=True)  # already extracted

        mock_from_memory.side_effect = [mem1, mem2, mem3]
        llm_memories.new_memories_extractor.return_value = [
            _make_raw_memory(mem1.content),
            _make_raw_memory(mem2.content),
            _make_raw_memory(mem3.content),
        ]
        vector_db_mod.find_similar_memories.return_value = []
        memories_mod.get_memory_ids_for_conversation.return_value = []
        memories_mod.save_memories.reset_mock()
        utils_analytics.record_usage.reset_mock()

        auth_mod.get_user_name.reset_mock()
        auth_mod.get_user_name.return_value = "Bob"
        llm_kg.extract_knowledge_from_memory.reset_mock()
        memories_mod.set_memory_kg_extracted.reset_mock()

        process_conversation._extract_memories_inner(uid, conv)

        # Should extract KG for mem-a and mem-b (not mem-c which is already extracted)
        assert llm_kg.extract_knowledge_from_memory.call_count == 2
        calls = llm_kg.extract_knowledge_from_memory.call_args_list
        assert calls[0].args == (uid, "First memory", "mem-a", "Bob")
        assert calls[1].args == (uid, "Second memory", "mem-b", "Bob")
        # set_memory_kg_extracted called for the 2 extracted ones
        assert memories_mod.set_memory_kg_extracted.call_count == 2


class TestKnowledgeGraphFailureHandling:
    """Tests for #4929: kg_extracted must not be set when extraction fails."""

    @patch("models.memories.MemoryDB.from_memory")
    def test_kg_extracted_not_set_when_extractor_returns_none(self, mock_from_memory):
        """When extract_knowledge_from_memory returns None (failure), kg_extracted must NOT be set."""
        uid = "uid-fail"
        conv = _make_conversation_mock()
        mem_db = _make_memory_mock("mem-fail", "Failing memory")
        mock_from_memory.return_value = mem_db

        _setup_extract_memories(mem_db)
        auth_mod.get_user_name.reset_mock()
        auth_mod.get_user_name.return_value = "User"
        llm_kg.extract_knowledge_from_memory.reset_mock()
        llm_kg.extract_knowledge_from_memory.return_value = None
        memories_mod.set_memory_kg_extracted.reset_mock()

        process_conversation._extract_memories_inner(uid, conv)

        llm_kg.extract_knowledge_from_memory.assert_called_once()
        memories_mod.set_memory_kg_extracted.assert_not_called()

    @patch("models.memories.MemoryDB.from_memory")
    def test_kg_extracted_set_only_for_successful_memories_in_batch(self, mock_from_memory):
        """In a batch, kg_extracted is set only for memories where extraction succeeds."""
        uid = "uid-mixed"
        conv = _make_conversation_mock()
        mem1 = _make_memory_mock("mem-ok", "Good memory", kg_extracted=False)
        mem2 = _make_memory_mock("mem-bad", "Bad memory", kg_extracted=False)
        mem3 = _make_memory_mock("mem-ok2", "Another good", kg_extracted=False)

        mock_from_memory.side_effect = [mem1, mem2, mem3]
        llm_memories.new_memories_extractor.return_value = [
            _make_raw_memory(mem1.content),
            _make_raw_memory(mem2.content),
            _make_raw_memory(mem3.content),
        ]
        vector_db_mod.find_similar_memories.return_value = []
        memories_mod.get_memory_ids_for_conversation.return_value = []
        memories_mod.save_memories.reset_mock()
        utils_analytics.record_usage.reset_mock()

        auth_mod.get_user_name.reset_mock()
        auth_mod.get_user_name.return_value = "User"
        llm_kg.extract_knowledge_from_memory.reset_mock()
        # First succeeds, second fails (None), third succeeds
        llm_kg.extract_knowledge_from_memory.side_effect = [
            {'nodes': [], 'edges': []},
            None,
            {'nodes': [{'id': 'n1'}], 'edges': []},
        ]
        memories_mod.set_memory_kg_extracted.reset_mock()

        process_conversation._extract_memories_inner(uid, conv)

        assert llm_kg.extract_knowledge_from_memory.call_count == 3
        # Only 2 should be marked as extracted (mem-ok and mem-ok2), not mem-bad
        assert memories_mod.set_memory_kg_extracted.call_count == 2
        calls = memories_mod.set_memory_kg_extracted.call_args_list
        assert calls[0].args == (uid, "mem-ok")
        assert calls[1].args == (uid, "mem-ok2")

    @patch("models.memories.MemoryDB.from_memory")
    def test_kg_extracted_set_on_empty_success(self, mock_from_memory):
        """When extraction returns empty nodes/edges (success), kg_extracted should still be set."""
        uid = "uid-empty"
        conv = _make_conversation_mock()
        mem_db = _make_memory_mock("mem-empty", "No entities here")
        mock_from_memory.return_value = mem_db

        _setup_extract_memories(mem_db)
        auth_mod.get_user_name.reset_mock()
        auth_mod.get_user_name.return_value = "User"
        llm_kg.extract_knowledge_from_memory.reset_mock()
        llm_kg.extract_knowledge_from_memory.side_effect = None
        llm_kg.extract_knowledge_from_memory.return_value = {'nodes': [], 'edges': []}
        memories_mod.set_memory_kg_extracted.reset_mock()

        process_conversation._extract_memories_inner(uid, conv)

        llm_kg.extract_knowledge_from_memory.assert_called_once()
        memories_mod.set_memory_kg_extracted.assert_called_once_with(uid, "mem-empty")


class TestKnowledgeGraphLockedMemorySkip:
    """Tests for #6146: KG extraction must skip is_locked memories.

    Note: is_locked is set on memories via `memory_db_obj.is_locked = conversation.is_locked`
    at line 450 of process_conversation.py. So we control locking via conv.is_locked.
    """

    @patch("models.memories.MemoryDB.from_memory")
    def test_kg_extraction_skips_locked_conversation_memories(self, mock_from_memory):
        """Memories from a locked conversation must not be sent to extract_knowledge_from_memory."""
        uid = "uid-locked"
        conv = _make_conversation_mock()
        conv.is_locked = True  # This propagates to all memories at line 450

        mem1 = _make_memory_mock("mem-1", "Secret content", kg_extracted=False)
        mem2 = _make_memory_mock("mem-2", "More secret", kg_extracted=False)

        mock_from_memory.side_effect = [mem1, mem2]
        llm_memories.new_memories_extractor.return_value = [
            _make_raw_memory(mem1.content),
            _make_raw_memory(mem2.content),
        ]
        vector_db_mod.find_similar_memories.return_value = []
        memories_mod.get_memory_ids_for_conversation.return_value = []
        memories_mod.save_memories.reset_mock()
        utils_analytics.record_usage.reset_mock()

        auth_mod.get_user_name.reset_mock()
        auth_mod.get_user_name.return_value = "User"
        llm_kg.extract_knowledge_from_memory.reset_mock()
        memories_mod.set_memory_kg_extracted.reset_mock()

        process_conversation._extract_memories_inner(uid, conv)

        # No KG extraction for locked conversation's memories
        llm_kg.extract_knowledge_from_memory.assert_not_called()
        memories_mod.set_memory_kg_extracted.assert_not_called()

    @patch("models.memories.MemoryDB.from_memory")
    def test_kg_extraction_proceeds_for_unlocked_conversation(self, mock_from_memory):
        """Memories from an unlocked conversation should be extracted normally."""
        uid = "uid-unlocked"
        conv = _make_conversation_mock()
        conv.is_locked = False

        mem = _make_memory_mock("mem-ok", "Public content", kg_extracted=False)
        mock_from_memory.return_value = mem

        _setup_extract_memories(mem)
        auth_mod.get_user_name.reset_mock()
        auth_mod.get_user_name.return_value = "User"
        llm_kg.extract_knowledge_from_memory.reset_mock()
        llm_kg.extract_knowledge_from_memory.return_value = {'nodes': [], 'edges': []}
        memories_mod.set_memory_kg_extracted.reset_mock()

        process_conversation._extract_memories_inner(uid, conv)

        llm_kg.extract_knowledge_from_memory.assert_called_once_with(uid, "Public content", "mem-ok", "User")
        memories_mod.set_memory_kg_extracted.assert_called_once_with(uid, "mem-ok")

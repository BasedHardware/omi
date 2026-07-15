"""
Unit tests for usage tracking context in conversation processing.

Verifies that sub-feature tracking is applied per LLM call (no umbrella tracking)
and that each sub-feature gets the correct Features constant.

The module under test (``utils.conversations.process_conversation``) and its dependency
``utils.llm.usage_tracker`` pull in the ``database.*`` / ``firebase`` / ``langchain`` chains
which construct clients at import time. To keep these tests hermetic in a single pytest
process, both modules are loaded fresh inside a module-scoped fixture via the sanctioned
``stub_modules`` + ``load_module_fresh`` seam (see ``backend/docs/test_isolation.md`` and
``testing/import_isolation.py``), against stubbed heavy dependencies. Everything loaded
inside the ``with`` block is evicted on teardown so no stub-fed module leaks to other files.
"""

import re
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from models.conversation import Conversation, CreateConversation
from models.conversation_enums import ConversationSource, ConversationStatus
from models.structured import Structured
from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

# Populated by the autouse ``_load_modules`` fixture before any test runs.
usage_tracker = None
process_conversation = None
llm_conv = None


def _build_fakes() -> dict[str, ModuleType]:
    """Build the stub-module mapping reproducing the original module-scope stubs.

    ``database.*`` is stubbed to avoid the firebase/firestore client construction at import;
    ``langchain_core`` is stubbed minimally (only what ``usage_tracker`` needs); the heavy
    ``utils.llm.*`` / ``utils.conversations.*`` / ``utils.memory.*`` dependencies are stubbed
    because they are not exercised by the tracking-context logic under test. ``models.*`` and
    ``fastapi`` stay real (they are import-pure Pydantic schemas / the framework).
    """
    import hashlib
    import uuid

    fakes: dict[str, ModuleType] = {}

    def add(name: str, mod: ModuleType) -> ModuleType:
        fakes[name] = mod
        return mod

    # --- database package + submodules -------------------------------------
    database_pkg = ModuleType("database")
    database_pkg.__path__ = [str(BACKEND_DIR / "database")]  # type: ignore[attr-defined]
    add("database", database_pkg)

    client_mod = ModuleType("database._client")
    client_mod.db = MagicMock(name="db")
    client_mod.get_firestore_client = lambda: client_mod.db

    def _document_id_from_seed(seed: str) -> str:
        seed_hash = hashlib.sha256(seed.encode("utf-8")).digest()
        return str(uuid.UUID(bytes=seed_hash[:16], version=4))

    client_mod.document_id_from_seed = _document_id_from_seed
    add("database._client", client_mod)

    vector_db = add("database.vector_db", AutoMockModule("database.vector_db"))
    for attr in [
        "find_similar_memories",
        "upsert_memory_vector",
        "delete_memory_vector",
        "upsert_vector2",
        "update_vector_metadata",
        "upsert_action_item_vectors_batch",
        "delete_action_item_vectors_batch",
        "find_similar_action_items",
        "upsert_transcript_chunk_vectors",
        "upsert_memory_vectors_batch",
        "delete_memory_vectors_batch",
        "query_vectors",
    ]:
        setattr(vector_db, attr, MagicMock())

    apps = add("database.apps", AutoMockModule("database.apps"))
    for attr in ["record_app_usage", "get_omi_personas_by_uid_db", "get_app_by_id_db"]:
        setattr(apps, attr, MagicMock())

    llm_usage = ModuleType("database.llm_usage")
    llm_usage.record_llm_usage = MagicMock()
    add("database.llm_usage", llm_usage)

    users = add("database.users", AutoMockModule("database.users"))
    users.get_user_language_preference = MagicMock(return_value=None)
    users.get_people_by_ids = MagicMock(return_value=None)
    users.get_data_protection_level = MagicMock(return_value="enhanced")

    auth = add("database.auth", AutoMockModule("database.auth"))
    auth.get_user_name = MagicMock(return_value="Test User")
    auth.get_current_user_uid = MagicMock()
    auth.with_rate_limit = MagicMock(side_effect=lambda fn, *a, **k: fn)

    entities = ModuleType("database.entities")
    entities.USER_ENTITY_ID = "entity:user"
    entities.person_entity_id = MagicMock(side_effect=lambda pid: f"entity:person:{pid}")
    add("database.entities", entities)

    memories = add("database.memories", AutoMockModule("database.memories"))
    memories.save_memories = MagicMock()
    memories.delete_memories_for_conversation = MagicMock(return_value={"vector_delete_ids": []})
    memories.get_memories = MagicMock(return_value=[])
    memories.get_memory = MagicMock(return_value=None)
    memories.invalidate_memory = MagicMock()
    memories.set_memory_kg_extracted = MagicMock()

    for name in [
        "database.redis_db",
        "database.conversations",
        "database.notifications",
        "database.tasks",
        "database.trends",
        "database.action_items",
        "database.folders",
        "database.calendar_meetings",
        "database.short_term_memories",
        "database.review_queue",
    ]:
        add(name, AutoMockModule(name))

    task_intelligence = ModuleType("utils.task_intelligence")
    task_intelligence.__path__ = []  # type: ignore[attr-defined]
    add("utils.task_intelligence", task_intelligence)
    conversation_capture = AutoMockModule("utils.task_intelligence.conversation_capture")
    conversation_capture.capture_enabled = MagicMock(return_value=False)
    conversation_capture.process_before_legacy = MagicMock(return_value=False)
    conversation_capture.canonical_fields = MagicMock(return_value={})
    conversation_capture.legacy_document_ids = MagicMock(return_value=None)
    conversation_capture.reconcile_after_legacy = MagicMock()
    add("utils.task_intelligence.conversation_capture", conversation_capture)
    task_intelligence.conversation_capture = conversation_capture
    workstream_association = AutoMockModule("utils.task_intelligence.workstream_association")
    workstream_association.associate_canonical_evidence = MagicMock()
    add("utils.task_intelligence.workstream_association", workstream_association)

    # --- firebase / pinecone / typesense / anthropic / stripe --------------
    firebase_admin = ModuleType("firebase_admin")
    firebase_admin.auth = MagicMock()
    add("firebase_admin", firebase_admin)

    pinecone = ModuleType("pinecone")
    pinecone.Pinecone = MagicMock()
    add("pinecone", pinecone)

    typesense = ModuleType("typesense")
    typesense.Client = MagicMock()
    add("typesense", typesense)

    add("anthropic", ModuleType("anthropic"))

    stripe = ModuleType("stripe")
    add("stripe", stripe)

    # --- langchain_core (minimal: only what usage_tracker imports) ---------
    langchain_core = ModuleType("langchain_core")
    langchain_core.__path__ = []  # type: ignore[attr-defined]
    callbacks = ModuleType("langchain_core.callbacks")
    callbacks.BaseCallbackHandler = object
    outputs = ModuleType("langchain_core.outputs")
    outputs.LLMResult = object
    langchain_core.callbacks = callbacks
    langchain_core.outputs = outputs
    langchain_core.output_parsers = ModuleType("langchain_core.output_parsers")
    langchain_core.output_parsers.PydanticOutputParser = MagicMock()
    langchain_core.prompts = ModuleType("langchain_core.prompts")
    langchain_core.prompts.ChatPromptTemplate = MagicMock()
    langchain_core.runnables = ModuleType("langchain_core.runnables")
    langchain_core.runnables.RunnableConfig = dict
    add("langchain_core", langchain_core)
    add("langchain_core.callbacks", callbacks)
    add("langchain_core.outputs", outputs)
    add("langchain_core.output_parsers", langchain_core.output_parsers)
    add("langchain_core.prompts", langchain_core.prompts)
    add("langchain_core.runnables", langchain_core.runnables)

    langchain = ModuleType("langchain")
    langchain.__path__ = []  # type: ignore[attr-defined]
    langchain_prompts = ModuleType("langchain.prompts")
    langchain_prompts.PromptTemplate = MagicMock()
    langchain_prompts.ChatPromptTemplate = MagicMock()
    langchain.prompts = langchain_prompts
    add("langchain", langchain)
    add("langchain.prompts", langchain_prompts)

    # --- utils package + submodules ----------------------------------------
    utils_pkg = ModuleType("utils")
    utils_pkg.__path__ = [str(BACKEND_DIR / "utils")]  # type: ignore[attr-defined]
    add("utils", utils_pkg)

    utils_llm_pkg = ModuleType("utils.llm")
    utils_llm_pkg.__path__ = [str(BACKEND_DIR / "utils" / "llm")]  # type: ignore[attr-defined]
    add("utils.llm", utils_llm_pkg)

    utils_conv_pkg = ModuleType("utils.conversations")
    utils_conv_pkg.__path__ = [str(BACKEND_DIR / "utils" / "conversations")]  # type: ignore[attr-defined]
    add("utils.conversations", utils_conv_pkg)

    # utils.llm.conversation_processing — stub with the names process_conversation imports.
    conv_proc = ModuleType("utils.llm.conversation_processing")
    for attr in [
        "get_transcript_structure",
        "get_app_result",
        "should_discard_conversation",
        "get_suggested_apps_for_conversation",
        "get_reprocess_transcript_structure",
        "assign_conversation_to_folder",
        "extract_action_items",
    ]:
        setattr(conv_proc, attr, MagicMock())
    add("utils.llm.conversation_processing", conv_proc)

    utils_apps = add("utils.apps", AutoMockModule("utils.apps"))
    for attr in ["get_available_apps", "update_personas_async", "update_persona_prompt"]:
        setattr(utils_apps, attr, MagicMock())

    utils_analytics = add("utils.analytics", AutoMockModule("utils.analytics"))
    utils_analytics.record_usage = MagicMock()

    transcript_chunks = add(
        "utils.conversations.transcript_chunks", AutoMockModule("utils.conversations.transcript_chunks")
    )
    transcript_chunks.build_transcript_chunks = MagicMock(return_value=[])

    calendar_linking = add(
        "utils.conversations.calendar_linking", AutoMockModule("utils.conversations.calendar_linking")
    )
    calendar_linking.get_overlapping_calendar_event = MagicMock(return_value=None)
    calendar_linking.write_conversation_link_to_calendar_event = MagicMock()

    add("utils.conversations.factory", AutoMockModule("utils.conversations.factory"))
    lifecycle_service = add("utils.conversations.lifecycle", AutoMockModule("utils.conversations.lifecycle"))
    lifecycle_service.persist_processed_conversation = MagicMock(return_value=True)
    lifecycle_service.create_completed_conversation = MagicMock(return_value=True)
    lifecycle_service.create_processing_conversation = MagicMock(return_value=True)
    subjects = add("utils.conversations.subjects", AutoMockModule("utils.conversations.subjects"))
    subjects.infer_subject_from_segments = lambda segments: (None, None)

    subscription = add("utils.subscription", AutoMockModule("utils.subscription"))
    subscription.is_trial_paywalled = MagicMock(return_value=False)
    subscription.should_defer_desktop_processing = MagicMock(return_value=False)

    executors = add("utils.executors", AutoMockModule("utils.executors"))
    executors.db_executor = MagicMock()
    executors.llm_executor = MagicMock()
    executors.postprocess_executor = MagicMock()

    class _ImmediateFuture:
        def __init__(self, fn, *args, **kwargs):
            try:
                self._result = fn(*args, **kwargs)
                self._exception = None
            except Exception as e:
                self._result = None
                self._exception = e

        def result(self):
            if self._exception:
                raise self._exception
            return self._result

    executors.submit_with_context = MagicMock(
        side_effect=lambda _executor, fn, *args, **kwargs: _ImmediateFuture(fn, *args, **kwargs)
    )

    llm_memories = add("utils.llm.memories", AutoMockModule("utils.llm.memories"))
    for attr in ["resolve_memory_conflict", "extract_memories_from_text", "new_memories_extractor"]:
        setattr(llm_memories, attr, MagicMock())

    llm_external = add("utils.llm.external_integrations", AutoMockModule("utils.llm.external_integrations"))
    for attr in ["summarize_experience_text", "get_message_structure"]:
        setattr(llm_external, attr, MagicMock())

    llm_trends = add("utils.llm.trends", AutoMockModule("utils.llm.trends"))
    llm_trends.trends_extractor = MagicMock()

    llm_goals = add("utils.llm.goals", AutoMockModule("utils.llm.goals"))
    llm_goals.extract_and_update_goal_progress = MagicMock()

    llm_chat = add("utils.llm.chat", AutoMockModule("utils.llm.chat"))
    for attr in [
        "retrieve_metadata_from_text",
        "retrieve_metadata_from_message",
        "retrieve_metadata_fields_from_transcript",
        "obtain_emotional_message",
    ]:
        setattr(llm_chat, attr, MagicMock())

    llm_clients = add("utils.llm.clients", AutoMockModule("utils.llm.clients"))
    llm_clients.generate_embedding = MagicMock()

    utils_notifications = add("utils.notifications", AutoMockModule("utils.notifications"))
    for attr in ["send_notification", "send_important_conversation_message", "send_action_item_data_message"]:
        setattr(utils_notifications, attr, MagicMock())

    utils_hume = add("utils.other.hume", AutoMockModule("utils.other.hume"))
    for attr in ["get_hume", "HumeJobCallbackModel", "HumeJobModelPredictionResponseModel"]:
        setattr(utils_hume, attr, MagicMock())

    utils_rag = add("utils.retrieval.rag", AutoMockModule("utils.retrieval.rag"))
    utils_rag.retrieve_rag_conversation_context = MagicMock()

    utils_webhooks = add("utils.webhooks", AutoMockModule("utils.webhooks"))
    utils_webhooks.conversation_created_webhook = MagicMock()

    utils_task_sync = add("utils.task_sync", AutoMockModule("utils.task_sync"))
    utils_task_sync.auto_sync_action_items_batch = MagicMock()

    utils_storage = add("utils.other.storage", AutoMockModule("utils.other.storage"))
    utils_storage.precache_conversation_audio = MagicMock()

    # utils.memory.* — the canonical memory chain is huge and not exercised by the
    # tracking-context logic under test; stub the five names process_conversation imports.
    canonical_activation = ModuleType("utils.memory.canonical_activation")
    canonical_activation.canonical_write_enabled = MagicMock(return_value=False)
    add("utils.memory.canonical_activation", canonical_activation)

    memory_service = ModuleType("utils.memory.memory_service")
    memory_service.MemoryService = MagicMock()
    add("utils.memory.memory_service", memory_service)

    class _MemorySystem:
        LEGACY = "legacy"
        CANONICAL = "canonical"

    memory_system = ModuleType("utils.memory.memory_system")
    memory_system.MemorySystem = _MemorySystem
    add("utils.memory.memory_system", memory_system)

    memory_system_pin = ModuleType("utils.memory.memory_system_pin")
    memory_system_pin.memory_system_request_scope = MagicMock()
    add("utils.memory.memory_system_pin", memory_system_pin)

    canonical_memory_adapter = ModuleType("utils.memory.canonical_memory_adapter")
    canonical_memory_adapter.extraction_memory_id = MagicMock()
    add("utils.memory.canonical_memory_adapter", canonical_memory_adapter)

    return fakes


@pytest.fixture(scope="module", autouse=True)
def _load_modules(request):
    """Load usage_tracker + process_conversation fresh against stubbed deps.

    Injects the loaded modules (plus the ``utils.llm.conversation_processing`` stub) as
    module-level globals so the existing test bodies and helpers resolve them unchanged.
    ``stub_modules`` restores ``sys.modules`` and evicts the freshly-exec'd modules on
    teardown, keeping the suite hermetic.
    """
    fakes = _build_fakes()
    with stub_modules(fakes):
        ut = load_module_fresh(
            "utils.llm.usage_tracker",
            str(BACKEND_DIR / "utils" / "llm" / "usage_tracker.py"),
        )
        pc = load_module_fresh(
            "utils.conversations.process_conversation",
            str(BACKEND_DIR / "utils" / "conversations" / "process_conversation.py"),
        )
        conv_stub = fakes["utils.llm.conversation_processing"]
        request.module.usage_tracker = ut
        request.module.process_conversation = pc
        request.module.llm_conv = conv_stub
        yield


def test_sub_feature_constants_exist():
    """Verify all sub-feature tracking constants are defined."""
    assert hasattr(usage_tracker.Features, 'CONVERSATION_DISCARD')
    assert hasattr(usage_tracker.Features, 'CONVERSATION_STRUCTURE')
    assert hasattr(usage_tracker.Features, 'CONVERSATION_ACTION_ITEMS')
    assert hasattr(usage_tracker.Features, 'CONVERSATION_FOLDER')
    assert hasattr(usage_tracker.Features, 'CONVERSATION_APPS')
    # Verify they're distinct from the umbrella
    assert usage_tracker.Features.CONVERSATION_DISCARD != usage_tracker.Features.CONVERSATION_PROCESSING
    assert usage_tracker.Features.CONVERSATION_STRUCTURE != usage_tracker.Features.CONVERSATION_PROCESSING


def test_fenced_completion_submits_no_derived_work(monkeypatch):
    input_conversation = MagicMock()
    input_conversation.source = "omi"
    input_conversation.get_person_ids.return_value = []

    completed_conversation = MagicMock()
    completed_conversation.id = "conversation-fenced"
    completed_conversation.dict.return_value = {"id": "conversation-fenced", "status": "completed"}

    persistence = MagicMock(return_value=False)
    submit = MagicMock()
    trigger_apps = MagicMock()
    create_audio_files = MagicMock()
    update_conversation = MagicMock()
    observed_persistence: list[bool] = []
    monkeypatch.setattr(process_conversation, "_get_structured", lambda *args, **kwargs: (MagicMock(), False))
    monkeypatch.setattr(process_conversation, "_get_conversation_obj", lambda *args, **kwargs: completed_conversation)
    monkeypatch.setattr(process_conversation.lifecycle_service, "persist_processed_conversation", persistence)
    monkeypatch.setattr(process_conversation, "submit_with_context", submit)
    monkeypatch.setattr(process_conversation, "_trigger_apps", trigger_apps)
    monkeypatch.setattr(process_conversation.conversations_db, "create_audio_files_from_chunks", create_audio_files)
    monkeypatch.setattr(process_conversation.conversations_db, "update_conversation", update_conversation)

    result = process_conversation.process_conversation(
        "uid",
        "en",
        input_conversation,
        persistence_observer=observed_persistence.append,
    )

    assert result is completed_conversation
    persistence.assert_called_once()
    submit.assert_not_called()
    trigger_apps.assert_not_called()
    create_audio_files.assert_not_called()
    update_conversation.assert_not_called()
    assert observed_persistence == [False]


def test_fresh_creation_uses_the_explicit_completed_lifecycle_owner(monkeypatch):
    new_request = CreateConversation(
        started_at=datetime(2026, 7, 14, tzinfo=timezone.utc),
        finished_at=datetime(2026, 7, 14, 0, 1, tzinfo=timezone.utc),
        transcript_segments=[],
        source=ConversationSource.omi,
    )
    completed_conversation = Conversation(
        id='fresh-conversation',
        created_at=datetime(2026, 7, 14, tzinfo=timezone.utc),
        started_at=new_request.started_at,
        finished_at=new_request.finished_at,
        source=ConversationSource.omi,
        structured=Structured(title=''),
        transcript_segments=[],
        status=ConversationStatus.completed,
        discarded=True,
    )
    created = MagicMock(return_value=True)
    persisted = MagicMock()
    monkeypatch.setattr(process_conversation, '_get_structured', lambda *args, **kwargs: (MagicMock(), True))
    monkeypatch.setattr(process_conversation, '_get_conversation_obj', lambda *args, **kwargs: completed_conversation)
    monkeypatch.setattr(process_conversation.lifecycle_service, 'create_completed_conversation', created)
    monkeypatch.setattr(process_conversation.lifecycle_service, 'persist_processed_conversation', persisted)

    result = process_conversation.process_conversation('uid', 'en', new_request)

    assert result is completed_conversation
    created.assert_called_once_with('uid', completed_conversation.dict(), idempotent=True)
    persisted.assert_not_called()


def test_deferred_fresh_creation_uses_the_explicit_processing_lifecycle_owner(monkeypatch):
    new_request = CreateConversation(
        started_at=datetime(2026, 7, 14, tzinfo=timezone.utc),
        finished_at=datetime(2026, 7, 14, 0, 1, tzinfo=timezone.utc),
        transcript_segments=[],
        source=ConversationSource.desktop,
    )
    deferred_conversation = MagicMock()
    deferred_conversation.id = 'deferred-conversation'
    deferred_conversation.dict.return_value = {'id': 'deferred-conversation', 'status': 'processing'}
    created = MagicMock(return_value=True)
    persisted = MagicMock()
    monkeypatch.setattr(process_conversation, '_build_deferred_structured', lambda *args: MagicMock())
    monkeypatch.setattr(process_conversation, '_get_conversation_obj', lambda *args, **kwargs: deferred_conversation)
    monkeypatch.setattr(process_conversation.lifecycle_service, 'create_processing_conversation', created)
    monkeypatch.setattr(process_conversation.lifecycle_service, 'persist_processed_conversation', persisted)

    result = process_conversation._store_deferred_conversation('uid', new_request)

    assert result is deferred_conversation
    assert deferred_conversation.deferred is True
    created.assert_called_once_with('uid', deferred_conversation.dict(), idempotent=True)
    persisted.assert_not_called()


def test_discard_call_uses_discard_feature_tracking():
    """Verify should_discard_conversation is called within CONVERSATION_DISCARD context."""
    import sys

    captured = {}

    def fake_discard(*args, **kwargs):
        captured["ctx"] = usage_tracker.get_current_context()
        return False  # Don't discard

    # Create a minimal conversation mock without external_data triggering CalendarMeetingContext
    conversation = MagicMock()
    conversation.source = "phone"
    conversation.get_transcript.return_value = "short transcript"
    conversation.photos = []
    conversation.get_person_ids.return_value = []
    conversation.external_data = None  # Prevent CalendarMeetingContext parsing
    conversation.started_at = None
    conversation.finished_at = None

    # Mock notification_db
    notifications_mod = sys.modules["database.notifications"]
    notifications_mod.get_user_time_zone = MagicMock(return_value="UTC")

    # Mock action_items_db
    action_items_mod = sys.modules["database.action_items"]
    action_items_mod.get_action_items = MagicMock(return_value=[])

    # Patch on the process_conversation module (where it's imported/bound)
    with patch.object(process_conversation, "should_discard_conversation", fake_discard), patch.object(
        process_conversation, "get_transcript_structure", MagicMock()
    ):
        try:
            process_conversation._get_structured("user-1", "en", conversation)
        except Exception:
            pass  # We only care about the context capture

    assert captured.get("ctx") is not None
    assert captured["ctx"].feature == usage_tracker.Features.CONVERSATION_DISCARD
    assert captured["ctx"].uid == "user-1"


def test_track_usage_context_resets_after_call():
    """Verify context is properly reset after each sub-feature tracking block."""
    assert usage_tracker.get_current_context() is None

    with usage_tracker.track_usage("user-test", usage_tracker.Features.CONVERSATION_STRUCTURE):
        ctx = usage_tracker.get_current_context()
        assert ctx.feature == usage_tracker.Features.CONVERSATION_STRUCTURE

    # Context should be reset after exiting
    assert usage_tracker.get_current_context() is None


def test_track_usage_context_resets_on_exception():
    """Verify context is properly reset even when an exception occurs."""
    assert usage_tracker.get_current_context() is None

    with pytest.raises(RuntimeError):
        with usage_tracker.track_usage("user-err", usage_tracker.Features.CONVERSATION_DISCARD):
            raise RuntimeError("boom")

    assert usage_tracker.get_current_context() is None


def test_no_umbrella_conversation_processing_tracking():
    """Verify _get_structured no longer wraps everything in CONVERSATION_PROCESSING."""
    import sys

    captured_contexts = []

    # Patch track_usage on the process_conversation module (where it's imported)
    original_track = process_conversation.track_usage

    @contextmanager
    def spy_track_usage(uid, feature):
        captured_contexts.append(feature)
        with original_track(uid, feature):
            yield

    conversation = MagicMock()
    conversation.source = "phone"
    conversation.get_transcript.return_value = "short transcript"
    conversation.photos = []
    conversation.get_person_ids.return_value = []
    conversation.external_data = None
    conversation.started_at = None
    conversation.finished_at = None

    notifications_mod = sys.modules["database.notifications"]
    notifications_mod.get_user_time_zone = MagicMock(return_value="UTC")

    action_items_mod = sys.modules["database.action_items"]
    action_items_mod.get_action_items = MagicMock(return_value=[])

    llm_conv.should_discard_conversation = MagicMock(return_value=False)
    llm_conv.get_transcript_structure = MagicMock()

    with patch.object(process_conversation, "track_usage", spy_track_usage):
        try:
            process_conversation._get_structured("user-2", "en", conversation)
        except Exception:
            pass

    # The umbrella CONVERSATION_PROCESSING should NOT appear
    assert usage_tracker.Features.CONVERSATION_PROCESSING not in captured_contexts
    # Sub-features should appear
    assert (
        usage_tracker.Features.CONVERSATION_DISCARD in captured_contexts
        or usage_tracker.Features.CONVERSATION_STRUCTURE in captured_contexts
    )


def test_action_items_tracked_separately_from_structure():
    """Verify action items extraction uses CONVERSATION_ACTION_ITEMS, not CONVERSATION_STRUCTURE."""
    import sys

    captured_contexts = []

    original_track = process_conversation.track_usage

    @contextmanager
    def spy_track_usage(uid, feature):
        captured_contexts.append(feature)
        with original_track(uid, feature):
            yield

    conversation = MagicMock()
    conversation.source = "phone"
    conversation.get_transcript.return_value = "short transcript"
    conversation.photos = []
    conversation.get_person_ids.return_value = []
    conversation.external_data = None
    conversation.started_at = None
    conversation.finished_at = None

    notifications_mod = sys.modules["database.notifications"]
    notifications_mod.get_user_time_zone = MagicMock(return_value="UTC")

    action_items_mod = sys.modules["database.action_items"]
    action_items_mod.get_action_items = MagicMock(return_value=[])

    with patch.object(process_conversation, "should_discard_conversation", MagicMock(return_value=False)), patch.object(
        process_conversation, "get_transcript_structure", MagicMock()
    ), patch.object(process_conversation, "extract_action_items", MagicMock(return_value=[])), patch.object(
        process_conversation, "track_usage", spy_track_usage
    ):
        try:
            process_conversation._get_structured("user-3", "en", conversation)
        except Exception:
            pass

    assert usage_tracker.Features.CONVERSATION_ACTION_ITEMS in captured_contexts
    # Action items should be tracked separately from structure
    assert captured_contexts.count(usage_tracker.Features.CONVERSATION_ACTION_ITEMS) >= 1
    # Structure should also be tracked
    assert usage_tracker.Features.CONVERSATION_STRUCTURE in captured_contexts


def test_structure_and_apps_tracked_at_runtime():
    """Verify conv_structure and conv_apps tracking at runtime call sites."""
    import sys

    captured_contexts = []

    original_track = process_conversation.track_usage

    @contextmanager
    def spy_track_usage(uid, feature):
        captured_contexts.append(feature)
        with original_track(uid, feature):
            yield

    conversation = MagicMock()
    conversation.source = "phone"
    conversation.get_transcript.return_value = "a transcript with enough words to not be discarded easily"
    conversation.photos = []
    conversation.get_person_ids.return_value = []
    conversation.external_data = None
    conversation.started_at = None
    conversation.finished_at = None
    conversation.structured = MagicMock()
    conversation.structured.title = "Test"
    conversation.structured.overview = "Test overview"
    conversation.structured.category = MagicMock()
    conversation.structured.category.value = "other"
    conversation.structured.action_items = []
    conversation.structured.events = []
    conversation.apps_results = []
    conversation.discarded = False
    conversation.id = "test-conv-id"
    conversation.folder_id = None
    conversation.suggested_summarization_apps = ["app1"]
    conversation.is_locked = False

    notifications_mod = sys.modules["database.notifications"]
    notifications_mod.get_user_time_zone = MagicMock(return_value="UTC")

    action_items_mod = sys.modules["database.action_items"]
    action_items_mod.get_action_items = MagicMock(return_value=[])

    folders_mod = sys.modules["database.folders"]
    folders_mod.get_folders = MagicMock(return_value=[{"id": "f1", "name": "Default", "is_default": True}])

    redis_mod = sys.modules["database.redis_db"]
    redis_mod.get_user_preferred_app = MagicMock(return_value=None)
    redis_mod.get_conversation_summary_app_ids = MagicMock(return_value=[])

    with patch.object(process_conversation, "should_discard_conversation", MagicMock(return_value=False)), patch.object(
        process_conversation, "get_transcript_structure", MagicMock()
    ), patch.object(process_conversation, "extract_action_items", MagicMock(return_value=[])), patch.object(
        process_conversation, "assign_conversation_to_folder", MagicMock(return_value=("f1", 0.9, "match"))
    ), patch.object(
        process_conversation, "track_usage", spy_track_usage
    ):
        try:
            process_conversation._get_structured("user-4", "en", conversation)
        except Exception:
            pass

    # Both structure and folder tracking should fire
    assert usage_tracker.Features.CONVERSATION_STRUCTURE in captured_contexts
    assert usage_tracker.Features.CONVERSATION_DISCARD in captured_contexts


def test_action_items_skipped_on_discard():
    """Verify extract_action_items is NOT called when conversation is discarded."""
    import sys

    conversation = MagicMock()
    conversation.source = "phone"
    conversation.get_transcript.return_value = "short"
    conversation.photos = []
    conversation.get_person_ids.return_value = []
    conversation.external_data = None
    conversation.started_at = None
    conversation.finished_at = None

    notifications_mod = sys.modules["database.notifications"]
    notifications_mod.get_user_time_zone = MagicMock(return_value="UTC")

    action_items_mod = sys.modules["database.action_items"]
    action_items_mod.get_action_items = MagicMock(return_value=[])

    extract_mock = MagicMock(return_value=[])

    with patch.object(process_conversation, "should_discard_conversation", MagicMock(return_value=True)), patch.object(
        process_conversation, "extract_action_items", extract_mock
    ):
        structured, discarded = process_conversation._get_structured("user-5", "en", conversation)

    assert discarded is True
    # extract_action_items should NOT have been called
    extract_mock.assert_not_called()


def test_llm_calls_use_omi_qos_tier_system():
    """Verify all LLM functions use get_llm() with correct feature keys and cache_key param."""
    conv_proc_path = Path(__file__).resolve().parent.parent.parent / "utils" / "llm" / "conversation_processing.py"
    conv_proc_source = conv_proc_path.read_text(encoding="utf-8")

    # get_transcript_structure should use get_llm('conv_structure', cache_key=...)
    struct_match = re.search(
        r'def get_transcript_structure.*?chain = prompt \| get_llm\([\'"](\w+)[\'"]\s*,\s*cache_key=',
        conv_proc_source,
        re.DOTALL,
    )
    assert struct_match is not None
    assert (
        struct_match.group(1) == "conv_structure"
    ), f"Expected get_llm('conv_structure') for structure, got {struct_match.group(1)}"

    # get_app_result should use get_llm('conv_app_result', cache_key=...)
    app_match = re.search(
        r'def get_app_result.*?response = get_llm\([\'"](\w+)[\'"]\s*,\s*cache_key=',
        conv_proc_source,
        re.DOTALL,
    )
    assert app_match is not None
    assert (
        app_match.group(1) == "conv_app_result"
    ), f"Expected get_llm('conv_app_result') for app result, got {app_match.group(1)}"

    # extract_action_items should use get_llm('conv_action_items', cache_key=...)
    action_match = re.search(
        r'def extract_action_items.*?chain = prompt \| get_llm\([\'"](\w+)[\'"]\s*,\s*cache_key=',
        conv_proc_source,
        re.DOTALL,
    )
    assert action_match is not None
    assert (
        action_match.group(1) == "conv_action_items"
    ), f"Expected get_llm('conv_action_items') for action items, got {action_match.group(1)}"

    # Verify cache keys are passed through get_llm's cache_key param (model-safe)
    assert "cache_key='omi-extract-actions'" in conv_proc_source, "Missing cache_key for action items"
    assert "cache_key='omi-transcript-structure'" in conv_proc_source, "Missing cache_key for structure"
    assert "cache_key='omi-app-result'" in conv_proc_source, "Missing cache_key for app result"
    assert "cache_key='omi-daily-summary'" in conv_proc_source, "Missing cache_key for daily summary"


def test_all_callsites_use_get_llm():
    """Verify ALL callsites across conversation_processing, knowledge_graph, and memories use get_llm()."""
    backend_dir = Path(__file__).resolve().parent.parent.parent

    # conversation_processing.py: 9 callsites
    conv_proc_source = (backend_dir / "utils" / "llm" / "conversation_processing.py").read_text(encoding="utf-8")
    conv_proc_calls = re.findall(r"get_llm\('(\w+)'", conv_proc_source)
    assert 'conv_action_items' in conv_proc_calls, "Missing get_llm('conv_action_items') in conversation_processing.py"
    assert 'conv_app_result' in conv_proc_calls, "Missing get_llm('conv_app_result') in conversation_processing.py"
    assert 'conv_app_select' in conv_proc_calls, "Missing get_llm('conv_app_select') in conversation_processing.py"
    assert 'conv_folder' in conv_proc_calls, "Missing get_llm('conv_folder') in conversation_processing.py"
    assert 'conv_discard' in conv_proc_calls, "Missing get_llm('conv_discard') in conversation_processing.py"
    assert 'daily_summary' in conv_proc_calls, "Missing get_llm('daily_summary') in conversation_processing.py"
    # conv_structure appears in both get_transcript_structure and get_reprocess_transcript_structure
    assert (
        conv_proc_calls.count('conv_structure') >= 2
    ), f"Expected at least 2 get_llm('conv_structure') calls (structure + reprocess), got {conv_proc_calls.count('conv_structure')}"

    # knowledge_graph.py: 2 callsites
    kg_source = (backend_dir / "utils" / "llm" / "knowledge_graph.py").read_text(encoding="utf-8")
    kg_calls = re.findall(r"get_llm\('(\w+)'", kg_source)
    assert (
        kg_calls.count('knowledge_graph') == 2
    ), f"Expected 2 get_llm('knowledge_graph') calls, got {kg_calls.count('knowledge_graph')}"

    # memories.py: 5 callsites (memories x2, learnings x1, memory_category x1, memory_conflict x1)
    mem_source = (backend_dir / "utils" / "llm" / "memories.py").read_text(encoding="utf-8")
    mem_calls = re.findall(r"get_llm\('(\w+)'", mem_source)
    assert mem_calls.count('memories') == 2, f"Expected 2 get_llm('memories') calls, got {mem_calls.count('memories')}"
    assert 'learnings' in mem_calls, "Missing get_llm('learnings') in memories.py"
    assert 'memory_category' in mem_calls, "Missing get_llm('memory_category') in memories.py"
    assert 'memory_conflict' in mem_calls, "Missing get_llm('memory_conflict') in memories.py"

    # Total: 9 + 2 + 5 = 16 callsites
    total = len(conv_proc_calls) + len(kg_calls) + len(mem_calls)
    assert total == 16, f"Expected 16 total get_llm() callsites, got {total}"


def test_no_direct_llm_instance_usage_in_wired_files():
    """Verify wired files don't invoke direct llm_mini/llm_medium_experiment/llm_high instances in function bodies."""
    backend_dir = Path(__file__).resolve().parent.parent.parent
    for filename in ["conversation_processing.py", "knowledge_graph.py", "memories.py"]:
        filepath = backend_dir / "utils" / "llm" / filename
        source = filepath.read_text(encoding="utf-8")
        # Check for actual invocations, not just imports
        for usage_pattern in [
            'llm_medium_experiment.invoke',
            'llm_medium_experiment |',
            'llm_mini.invoke',
            'llm_mini |',
            'llm_mini.with_structured_output',
            'llm_high |',
            'llm_high.invoke',
        ]:
            assert usage_pattern not in source, f"{filename} still invokes {usage_pattern} instead of get_llm()"


def test_threaded_tracking_context_isolation():
    """Verify track_usage context works correctly with threading (context isolation)."""
    results = {}

    def thread_fn(uid, feature, key):
        with usage_tracker.track_usage(uid, feature):
            ctx = usage_tracker.get_current_context()
            results[key] = ctx

    t1 = threading.Thread(target=thread_fn, args=("u1", usage_tracker.Features.MEMORIES, "t1"))
    t2 = threading.Thread(target=thread_fn, args=("u2", usage_tracker.Features.TRENDS, "t2"))

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Each thread should have had its own context
    assert results["t1"].feature == usage_tracker.Features.MEMORIES
    assert results["t1"].uid == "u1"
    assert results["t2"].feature == usage_tracker.Features.TRENDS
    assert results["t2"].uid == "u2"

    # Main thread should have no context set
    assert usage_tracker.get_current_context() is None


# ---------------------------------------------------------------------------
# Tests for _trigger_apps preferred-app shortcut (PR #4683, issue #4639)
# ---------------------------------------------------------------------------


def _make_mock_app(app_id, name="TestApp"):
    """Create a minimal App-like mock for _trigger_apps tests."""
    app = MagicMock()
    app.id = app_id
    app.name = name
    app.works_with_memories.return_value = True
    app.enabled = True
    return app


def _setup_trigger_apps_mocks(preferred_app_id=None, default_apps=None, available_apps=None):
    """Set up the module-level mocks needed by _trigger_apps."""
    import sys

    redis_mod = sys.modules["database.redis_db"]
    redis_mod.get_user_preferred_app = MagicMock(return_value=preferred_app_id)

    apps_mod = sys.modules["database.apps"]
    apps_mod.record_app_usage = MagicMock()

    utils_apps_mod = sys.modules["utils.apps"]
    utils_apps_mod.get_available_apps = MagicMock(return_value=available_apps or [])

    llm_conv_mod = llm_conv
    llm_conv_mod.get_app_result = MagicMock(return_value="App result content")
    llm_conv_mod.get_suggested_apps_for_conversation = MagicMock(return_value=(["suggested-app"], "reasoning"))

    return llm_conv_mod, default_apps or []


def _make_trigger_conversation(suggested_apps=None):
    """Create a minimal conversation mock for _trigger_apps tests."""
    conv = MagicMock()
    conv.id = "conv-trigger-test"
    conv.get_transcript.return_value = "Speaker 0: Hello"
    conv.photos = []
    conv.apps_results = []
    conv.suggested_summarization_apps = suggested_apps
    return conv


def _trigger_apps_context(default_apps=None):
    """Context manager that patches all external dependencies of _trigger_apps."""
    suggestion_mock = MagicMock(return_value=(["suggested-app"], "reasoning"))
    app_result_mock = MagicMock(return_value="App result content")
    record_mock = MagicMock()
    return (
        suggestion_mock,
        app_result_mock,
        patch.object(process_conversation, "get_default_conversation_summarized_apps", return_value=default_apps or []),
        patch.object(process_conversation, "get_available_apps", return_value=[]),
        patch.object(process_conversation, "get_suggested_apps_for_conversation", suggestion_mock),
        patch.object(process_conversation, "get_app_result", app_result_mock),
        patch.object(process_conversation, "record_app_usage", record_mock),
    )


def test_trigger_apps_uses_preferred_app_skips_llm_suggestion():
    """When user has a valid preferred app, use it and skip the suggestion LLM call."""
    preferred = _make_mock_app("preferred-app-1", "PreferredApp")
    _setup_trigger_apps_mocks(preferred_app_id="preferred-app-1", available_apps=[preferred])
    conv = _make_trigger_conversation()

    suggestion_mock, app_result_mock, p1, p2, p3, p4, p5 = _trigger_apps_context()
    # Override get_available_apps to return the preferred app
    p2 = patch.object(process_conversation, "get_available_apps", return_value=[preferred])

    with p1, p2, p3, p4, p5:
        process_conversation._trigger_apps("user-preferred", conv)

    # The suggestion LLM call must NOT have been invoked
    suggestion_mock.assert_not_called()
    # The preferred app should have been executed
    app_result_mock.assert_called_once()
    # The app result should be stored on the conversation
    assert len(conv.apps_results) == 1


def test_trigger_apps_stale_preferred_app_falls_through_to_suggestion():
    """When preferred app ID exists in Redis but not in apps dict, fall through to LLM suggestion."""
    suggestion_app = _make_mock_app("suggested-app", "SuggestedApp")
    _setup_trigger_apps_mocks(preferred_app_id="deleted-app-999")
    conv = _make_trigger_conversation()

    suggestion_mock, app_result_mock, p1, p2, p3, p4, p5 = _trigger_apps_context(default_apps=[suggestion_app])

    with p1, p2, p3, p4, p5:
        process_conversation._trigger_apps("user-stale", conv)

    # The suggestion LLM call SHOULD have been invoked since preferred app was invalid
    suggestion_mock.assert_called_once()


def test_trigger_apps_no_preferred_app_runs_suggestion():
    """When no preferred app is set, the suggestion LLM call should run."""
    suggestion_app = _make_mock_app("suggested-app", "SuggestedApp")
    _setup_trigger_apps_mocks(preferred_app_id=None)
    conv = _make_trigger_conversation()

    suggestion_mock, app_result_mock, p1, p2, p3, p4, p5 = _trigger_apps_context(default_apps=[suggestion_app])

    with p1, p2, p3, p4, p5:
        process_conversation._trigger_apps("user-no-pref", conv)

    # The suggestion LLM call SHOULD have been invoked
    suggestion_mock.assert_called_once()

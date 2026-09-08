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
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
import httpx
import openai
import pytest

from llm_gateway.gateway.errors import GatewayCredentialFailureError, GatewayProviderFailureError
from llm_gateway.gateway.schemas import FailureClass
from models.conversation import Conversation, CreateConversation
from models.conversation_enums import ConversationSource, ConversationStatus
from models.structured import Structured
from models.transcript_segment import TranscriptSegment
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
    screen_activity = add("database.screen_activity", AutoMockModule("database.screen_activity"))
    screen_activity.get_screen_activity = MagicMock(return_value=[])

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
    conversation_capture.process_conversation_before_legacy = MagicMock(return_value=False)
    conversation_capture.canonical_conversation_fields = MagicMock(return_value={})
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
        "get_conversation_notes",
    ]:
        setattr(conv_proc, attr, MagicMock())
    add("utils.llm.conversation_processing", conv_proc)
    prompt_prefix = add("utils.llm.conversation_prompt_prefix", AutoMockModule("utils.llm.conversation_prompt_prefix"))
    prompt_prefix.ConversationPromptPrefix = MagicMock
    prompt_prefix.build_conversation_prompt_prefix = MagicMock()

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
    meeting_context = add("utils.conversations.meeting_context", AutoMockModule("utils.conversations.meeting_context"))
    meeting_context.MAX_SCREEN_CONTEXT_ROWS = 80
    meeting_context.context_from_calendar_link = MagicMock()
    meeting_context.context_from_screen_activity = MagicMock()
    meeting_context.merge_meeting_contexts = MagicMock(side_effect=lambda primary, fallback: primary or fallback)

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
    for attr in [
        "resolve_memory_conflict",
        "extract_canonical_l1_memory_candidates",
        "extract_memories_from_text",
        "new_memories_extractor",
    ]:
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
    assert hasattr(usage_tracker.Features, 'WAKE_WORD_ADJUDICATION')
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
    monkeypatch.setattr(process_conversation, "trigger_conversation_apps", trigger_apps)
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


def test_deferred_derived_effects_emit_nothing_until_runner_invoked(monkeypatch):
    """#10468 r5: with defer_derived_effects=True, process_conversation persists
    the result and hands back the entire derived-effect bundle as a deferred
    runner, emitting zero side effects inline.  Only invoking the runner (after
    the durable finalizer has transactionally claimed ownership) emits calendar,
    usage/app, vector, action/goal, audio, webhook, and memory work.  A losing
    claim that never invokes the runner is a no-side-effect outcome."""
    input_conversation = MagicMock()
    input_conversation.source = "omi"
    input_conversation.get_person_ids.return_value = []

    completed_conversation = MagicMock()
    completed_conversation.id = "conversation-deferred"
    completed_conversation.dict.return_value = {"id": "conversation-deferred", "status": "completed"}
    completed_conversation.structured = None  # skip analytics counting
    completed_conversation.apps_results = []
    completed_conversation.suggested_summarization_apps = []
    completed_conversation.private_cloud_sync_enabled = False
    completed_conversation.folder_id = "existing-folder"  # skip folder assignment

    persistence = MagicMock(return_value=True)
    submit = MagicMock()
    trigger_apps = MagicMock()
    create_audio_files = MagicMock()
    update_conversation = MagicMock()
    extract_memories = MagicMock()
    captured: list = []
    monkeypatch.setattr(process_conversation, "_get_structured", lambda *args, **kwargs: (MagicMock(), False))
    monkeypatch.setattr(process_conversation, "_get_conversation_obj", lambda *args, **kwargs: completed_conversation)
    monkeypatch.setattr(process_conversation.lifecycle_service, "persist_processed_conversation", persistence)
    monkeypatch.setattr(process_conversation, "submit_with_context", submit)
    monkeypatch.setattr(process_conversation, "trigger_conversation_apps", trigger_apps)
    monkeypatch.setattr(process_conversation.conversations_db, "create_audio_files_from_chunks", create_audio_files)
    monkeypatch.setattr(process_conversation.conversations_db, "update_conversation", update_conversation)
    monkeypatch.setattr(process_conversation, "_extract_memories", extract_memories)

    result = process_conversation.process_conversation(
        "uid",
        "en",
        input_conversation,
        defer_derived_effects=True,
        derived_effects_observer=captured.append,
    )

    assert result is completed_conversation
    persistence.assert_called_once()
    # ZERO side effects emitted inline — the entire bundle is deferred.
    submit.assert_not_called()
    trigger_apps.assert_not_called()
    create_audio_files.assert_not_called()
    update_conversation.assert_not_called()
    extract_memories.assert_not_called()
    assert len(captured) == 1, "exactly one derived-effects runner must be captured"

    # Invoking the runner (ownership proven) emits every derived effect.
    captured[0]()
    trigger_apps.assert_called_once()
    assert submit.call_count >= 4  # vectors, memory, action items, goals, webhook


def _explicit_selection_flow_conversation():
    completed = MagicMock()
    completed.id = "conversation-explicit-selection"
    completed.dict.return_value = {"id": "conversation-explicit-selection", "status": "completed"}
    completed.structured = None  # skip analytics counting
    completed.apps_results = []
    completed.suggested_summarization_apps = []
    completed.private_cloud_sync_enabled = False
    completed.folder_id = "existing-folder"  # skip folder assignment
    return completed


def _run_explicit_selection_flow(monkeypatch, trigger_apps, update_calls):
    """Drive process_conversation for an explicit app selection; appends each write to update_calls."""
    input_conversation = MagicMock()
    input_conversation.source = "omi"
    input_conversation.get_person_ids.return_value = []
    completed = _explicit_selection_flow_conversation()

    monkeypatch.setattr(process_conversation, "_get_structured", lambda *args, **kwargs: (MagicMock(), False))
    monkeypatch.setattr(process_conversation, "_get_conversation_obj", lambda *args, **kwargs: completed)
    monkeypatch.setattr(
        process_conversation.lifecycle_service, "persist_processed_conversation", MagicMock(return_value=True)
    )
    monkeypatch.setattr(process_conversation, "submit_with_context", MagicMock())
    monkeypatch.setattr(process_conversation, "trigger_conversation_apps", trigger_apps)
    monkeypatch.setattr(process_conversation, "_extract_memories", MagicMock())
    monkeypatch.setattr(
        process_conversation.conversations_db,
        "update_conversation",
        lambda uid, cid, updates: update_calls.append(updates),
    )

    return process_conversation.process_conversation(
        "uid",
        "en",
        input_conversation,
        is_reprocess=True,
        app_id="selected-app",
        explicit_app=SimpleNamespace(id="selected-app"),
    )


def test_explicit_selection_success_persists_that_apps_result(monkeypatch):
    """SCA-359: opt-in + explicit app_id persists the selected app's non-empty result."""
    monkeypatch.setenv('CONVERSATION_NOTES_V2_ENABLED', 'true')

    def _successful_trigger_apps(uid, conversation, **kwargs):
        conversation.apps_results.append(process_conversation.AppResult(app_id='selected-app', content='APP SUMMARY'))

    update_calls: list = []
    result = _run_explicit_selection_flow(monkeypatch, _successful_trigger_apps, update_calls)

    assert result.apps_results == [process_conversation.AppResult(app_id='selected-app', content='APP SUMMARY')]
    assert {
        'apps_results': [{'app_id': 'selected-app', 'content': 'APP SUMMARY'}],
        'suggested_summarization_apps': [],
    } in (update_calls)


def test_explicit_selection_failure_surfaces_a_real_error_and_persists_as_today(monkeypatch):
    """SCA-359 contract: reprocess with app_id returns the app's result or a real error.

    Never a 200 whose payload quietly substitutes first-party notes for the selected
    app's summary. The persist-as-today write-back still runs (the ed2ba41c5b opt-in
    empty persist that clears a stale selection) so the failure contract changes the
    response, not the durable shape."""
    monkeypatch.setenv('CONVERSATION_NOTES_V2_ENABLED', 'true')

    def _failing_trigger_apps(uid, conversation, **kwargs):
        conversation.apps_results = []  # execution failed: nothing appended
        raise process_conversation.ExplicitAppSelectionFailedError('selected-app produced no summary content')

    update_calls: list = []
    with pytest.raises(HTTPException) as exc_info:
        _run_explicit_selection_flow(monkeypatch, _failing_trigger_apps, update_calls)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == 'Error processing conversation, please try again later'
    assert {'apps_results': [], 'suggested_summarization_apps': []} in update_calls


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
    # Imported here, not at module scope: sibling suites stub utils.conversations.
    from utils.conversations.projection_payload import (
        omit_null_processing_state,
        strip_client_processing,
    )

    # The create path strips the untrusted client projection before persisting:
    # a projection is display, so it must not reach a stored conversation payload.
    # A null modeled processing_state is omitted too (flip-review F-1): persist is
    # merge=True, so a dumped None is a real Firestore key.
    created.assert_called_once_with(
        'uid',
        omit_null_processing_state(strip_client_processing(completed_conversation.dict())),
        idempotent=True,
    )
    assert 'client_processing' not in created.call_args.args[1]
    assert 'processing_state' not in created.call_args.args[1]
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


def test_wake_word_marker_reaches_discard_adjudication_without_bypassing_it(monkeypatch):
    conversation = CreateConversation(
        started_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
        finished_at=datetime(2026, 8, 20, 0, 0, 5, tzinfo=timezone.utc),
        transcript_segments=[
            TranscriptSegment(
                id='wake-segment',
                text="Hey Omi, don't forget to send the budget.",
                speaker='SPEAKER_00',
                is_user=True,
                start=0,
                end=5,
            )
        ],
        source=ConversationSource.phone,
    )
    captured: dict[str, object] = {}

    def fake_discard(transcript, photos, duration_seconds, *, trusted_wake_word_markers=False):
        captured.update(
            transcript=transcript,
            photos=photos,
            duration_seconds=duration_seconds,
            trusted_wake_word_markers=trusted_wake_word_markers,
        )
        return True

    monkeypatch.setattr(
        process_conversation,
        'conversation_transcripts_for_llm',
        lambda *_args, **_kwargs: (
            "Test User: Hey Omi, don't forget to send the budget.",
            '[segment:wake-segment 0.000-5.000] '
            "<omi-wake-word-invocation/> Test User: Hey Omi, don't forget to send the budget.",
        ),
    )
    monkeypatch.setattr(process_conversation, 'should_discard_conversation', fake_discard)

    structured, discarded = process_conversation._get_structured('uid', 'multi', conversation)

    assert discarded is True
    assert structured.action_items == []
    assert isinstance(captured['transcript'], str)
    assert '<omi-wake-word-invocation/>' in captured['transcript']
    assert captured['trusted_wake_word_markers'] is True
    assert captured['duration_seconds'] == 5


def test_primary_user_name_reaches_action_item_extraction(monkeypatch):
    conversation = CreateConversation(
        started_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
        finished_at=datetime(2026, 8, 20, 0, 0, 5, tzinfo=timezone.utc),
        transcript_segments=[
            TranscriptSegment(
                id='user-request',
                text='Send the budget.',
                speaker='SPEAKER_00',
                is_user=True,
                start=0,
                end=5,
            )
        ],
        source=ConversationSource.phone,
    )
    structured = Structured(title='Budget', overview='Send the budget')
    extract_mock = MagicMock(return_value=[])

    monkeypatch.setattr(process_conversation, 'get_user_name', lambda *_args, **_kwargs: 'David')
    monkeypatch.setattr(
        process_conversation,
        'conversation_transcripts_for_llm',
        lambda *_args, **_kwargs: (
            'David: Send the budget.',
            '[segment:user-request 0.000-5.000] David: Send the budget.',
        ),
    )
    monkeypatch.setattr(process_conversation, 'should_discard_conversation', lambda *_args, **_kwargs: False)
    monkeypatch.setattr(process_conversation, 'get_transcript_structure', lambda *_args, **_kwargs: structured)
    monkeypatch.setattr(process_conversation, 'extract_action_items', extract_mock)
    monkeypatch.setattr(process_conversation, '_fetch_dedup_candidates', lambda *_args, **_kwargs: [])

    result, discarded = process_conversation._get_structured('uid', 'en', conversation)

    assert discarded is False
    assert result is structured
    assert extract_mock.call_args.kwargs['primary_user_name'] == 'David'


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


def test_byok_rate_limit_reaches_conversation_composition_as_safe_actionable_429(monkeypatch, caplog):
    """The composition boundary must retain the gateway's typed BYOK outcome."""
    sensitive_provider_body = 'provider-body-with-api-key-and-transcript'
    conversation = MagicMock()
    conversation.source = ConversationSource.phone
    conversation.get_transcript.return_value = 'a conversation transcript'
    conversation.photos = []
    conversation.external_data = None
    conversation.started_at = datetime(2026, 8, 4, tzinfo=timezone.utc)
    conversation.finished_at = datetime(2026, 8, 4, 0, 1, tzinfo=timezone.utc)

    monkeypatch.setattr(process_conversation, 'should_discard_conversation', MagicMock(return_value=False))
    monkeypatch.setattr(
        process_conversation,
        'get_transcript_structure',
        MagicMock(
            side_effect=GatewayCredentialFailureError(
                sensitive_provider_body,
                failure_class=FailureClass.BYOK_RATE_LIMIT,
            )
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        process_conversation._get_structured('uid', 'en', conversation)

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail == {
        'code': 'byok_rate_limit',
        'message': 'The configured provider account is rate limited. Please retry later or check its limits.',
    }
    assert sensitive_provider_body not in str(exc_info.value.detail)
    assert sensitive_provider_body not in caplog.text


def test_unwrapped_openai_byok_rate_limit_reaches_conversation_composition(monkeypatch, caplog):
    """The production SDK shape must preserve the actionable BYOK response."""
    sensitive_provider_body = 'provider-body-with-api-key-and-transcript'
    conversation = MagicMock()
    conversation.source = ConversationSource.phone
    conversation.get_transcript.return_value = 'a conversation transcript'
    conversation.photos = []
    conversation.external_data = None
    conversation.started_at = datetime(2026, 8, 4, tzinfo=timezone.utc)
    conversation.finished_at = datetime(2026, 8, 4, 0, 1, tzinfo=timezone.utc)

    sdk_error = openai.RateLimitError(
        sensitive_provider_body,
        response=httpx.Response(429, request=httpx.Request('POST', 'http://gateway.test/v1/chat/completions')),
        body={
            'code': 'credential_failure',
            'failure_class': 'byok_rate_limit',
            'message': sensitive_provider_body,
        },
    )
    monkeypatch.setattr(process_conversation, 'should_discard_conversation', MagicMock(return_value=False))
    monkeypatch.setattr(process_conversation, 'get_transcript_structure', MagicMock(side_effect=sdk_error))

    with pytest.raises(HTTPException) as exc_info:
        process_conversation._get_structured('uid', 'en', conversation)

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail == {
        'code': 'byok_rate_limit',
        'message': 'The configured provider account is rate limited. Please retry later or check its limits.',
    }
    assert sensitive_provider_body not in str(exc_info.value.detail)
    assert sensitive_provider_body not in caplog.text


@pytest.mark.parametrize(
    'error',
    [
        GatewayCredentialFailureError('provider-body-with-api-key', failure_class=FailureClass.BYOK_QUOTA),
        GatewayProviderFailureError('provider-body-with-transcript', failure_class=FailureClass.PROVIDER_429_OMI_PAID),
    ],
)
def test_non_byok_rate_limit_failures_keep_generic_processing_error(monkeypatch, caplog, error):
    conversation = MagicMock()
    conversation.source = ConversationSource.phone
    conversation.get_transcript.return_value = 'a conversation transcript'
    conversation.photos = []
    conversation.external_data = None
    conversation.started_at = datetime(2026, 8, 4, tzinfo=timezone.utc)
    conversation.finished_at = datetime(2026, 8, 4, 0, 1, tzinfo=timezone.utc)

    monkeypatch.setattr(process_conversation, 'should_discard_conversation', MagicMock(return_value=False))
    monkeypatch.setattr(process_conversation, 'get_transcript_structure', MagicMock(side_effect=error))

    with pytest.raises(HTTPException) as exc_info:
        process_conversation._get_structured('uid', 'en', conversation)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == 'Error processing conversation, please try again later'
    assert type(error).__name__ in caplog.text
    assert str(error) not in caplog.text


def test_byok_rate_limit_in_action_item_extraction_reaches_composition_boundary(monkeypatch):
    """A BYOK rate-limit during action-item extraction must not be swallowed by extract_action_items's catch-all.

    extract_action_items catches every exception and returns [] by default. A typed
    BYOK rate-limit must escape so the composition boundary (_get_structured) maps
    it to the actionable 429 contract instead of persisting an incomplete conversation.
    """
    conversation = MagicMock()
    conversation.source = ConversationSource.phone
    conversation.get_transcript.return_value = 'a conversation transcript'
    conversation.photos = []
    conversation.external_data = None
    conversation.started_at = datetime(2026, 8, 4, tzinfo=timezone.utc)
    conversation.finished_at = datetime(2026, 8, 4, 0, 1, tzinfo=timezone.utc)

    monkeypatch.setattr(process_conversation, 'should_discard_conversation', MagicMock(return_value=False))
    monkeypatch.setattr(
        process_conversation,
        'get_transcript_structure',
        MagicMock(return_value=Structured(emoji='🧠', title='Test', overview='Overview', action_items=[])),
    )
    monkeypatch.setattr(
        process_conversation,
        'extract_action_items',
        MagicMock(
            side_effect=GatewayCredentialFailureError(
                'rate limited',
                failure_class=FailureClass.BYOK_RATE_LIMIT,
            )
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        process_conversation._get_structured('uid', 'en', conversation)

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail == {
        'code': 'byok_rate_limit',
        'message': 'The configured provider account is rate limited. Please retry later or check its limits.',
    }


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


def test_conversation_action_items_never_fall_back_to_a_task_writer(monkeypatch):
    """A proposing surface stays proposing when its capture path is unavailable.

    Desktop conversations propose Candidates. Even when the canonical capture
    path reports itself unavailable (``process_conversation_before_legacy`` ->
    False, e.g. rollout control unreadable), `_save_action_items` must NOT fall
    back to writing action items — the previous bugs were all in that fallback.
    """
    action_item = MagicMock()
    action_item.description = 'Send the forecast'
    action_item.completed = False
    action_item.created_at = None
    action_item.updated_at = None
    action_item.due_at = None
    action_item.completed_at = None

    conversation = MagicMock()
    conversation.id = 'conversation-1'
    conversation.is_locked = False
    conversation.source = ConversationSource.desktop
    conversation.transcript_segments = []
    conversation.structured.action_items = [action_item]

    monkeypatch.setattr(
        process_conversation.conversation_capture, 'process_conversation_before_legacy', lambda *args: False
    )
    for writer in ('create_action_item', 'create_action_items_batch'):
        # Bind `writer` per iteration; a late-bound closure would name the wrong
        # function in the failure message for the test that pins the invariant.
        monkeypatch.setattr(
            process_conversation.action_items_db,
            writer,
            lambda *args, _writer=writer, **kwargs: pytest.fail(f'{_writer} must never be called by extraction'),
        )
    emitted = []
    monkeypatch.setattr(process_conversation, 'emit_product_event', lambda **kwargs: emitted.append(kwargs))

    process_conversation._save_action_items('user-1', conversation)

    assert emitted and emitted[0]['properties']['persistence_path'] == 'canonical_candidate'


def test_llm_calls_use_omi_qos_tier_system():
    """Verify all LLM functions use get_llm() with correct feature keys and cache_key param."""
    conv_proc_path = Path(__file__).resolve().parent.parent.parent / "utils" / "llm" / "conversation_processing.py"
    conv_proc_source = conv_proc_path.read_text(encoding="utf-8")

    # get_transcript_structure should use the conv_structure QoS lane.
    struct_match = re.search(
        r'def get_transcript_structure.*?get_llm\(\s*[\'"](\w+)[\'"]\s*,\s*cache_key=',
        conv_proc_source,
        re.DOTALL,
    )
    assert struct_match is not None
    assert (
        struct_match.group(1) == "conv_structure"
    ), f"Expected get_llm('conv_structure') for structure, got {struct_match.group(1)}"

    # get_app_result should use the conv_app_result QoS lane.
    app_match = re.search(
        r'def get_app_result.*?get_llm\(\s*[\'"](\w+)[\'"]\s*,\s*cache_key=',
        conv_proc_source,
        re.DOTALL,
    )
    assert app_match is not None
    assert (
        app_match.group(1) == "conv_app_result"
    ), f"Expected get_llm('conv_app_result') for app result, got {app_match.group(1)}"

    # extract_action_items should use the conv_action_items QoS lane.
    action_match = re.search(
        r'def extract_action_items.*?get_llm\(\s*[\'"](\w+)[\'"]\s*,\s*cache_key=',
        conv_proc_source,
        re.DOTALL,
    )
    assert action_match is not None
    assert (
        action_match.group(1) == "conv_action_items"
    ), f"Expected get_llm('conv_action_items') for action items, got {action_match.group(1)}"

    # Verify cache keys are passed through get_llm's cache_key param (model-safe)
    assert 'ACTION_ITEMS_CACHE_KEY' in conv_proc_source, "Missing stable cache key for action items"
    assert 'TRANSCRIPT_STRUCTURE_CACHE_KEY' in conv_proc_source, "Missing stable cache key for structure"
    assert "else 'omi-app-result'" in conv_proc_source, "Missing cache_key for app result"
    assert "cache_key='omi-daily-summary'" in conv_proc_source, "Missing cache_key for daily summary"


def test_all_callsites_use_get_llm():
    """Verify ALL callsites across conversation_processing, knowledge_graph, and memories use get_llm()."""
    backend_dir = Path(__file__).resolve().parent.parent.parent

    # conversation_processing.py: 9 callsites
    conv_proc_source = (backend_dir / "utils" / "llm" / "conversation_processing.py").read_text(encoding="utf-8")
    conv_proc_calls = re.findall(r"get_llm\(\s*'(\w+)'", conv_proc_source)
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
    kg_calls = re.findall(r"get_llm\(\s*'(\w+)'", kg_source)
    assert (
        kg_calls.count('knowledge_graph') == 2
    ), f"Expected 2 get_llm('knowledge_graph') calls, got {kg_calls.count('knowledge_graph')}"

    # memories.py: 7 callsites (memories x4 incl. the memory-log extract SSOT and the
    # daily-sweep summary agent, learnings x1, memory_category x1, memory_conflict x1)
    mem_source = (backend_dir / "utils" / "llm" / "memories.py").read_text(encoding="utf-8")
    mem_calls = re.findall(r"get_llm\(\s*'(\w+)'", mem_source)
    assert mem_calls.count('memories') == 4, f"Expected 4 get_llm('memories') calls, got {mem_calls.count('memories')}"
    assert 'learnings' in mem_calls, "Missing get_llm('learnings') in memories.py"
    assert 'memory_category' in mem_calls, "Missing get_llm('memory_category') in memories.py"
    assert 'memory_conflict' in mem_calls, "Missing get_llm('memory_conflict') in memories.py"

    # Total: 11 + 2 + 6 = 19 callsites (notes v2 adds the merged note call). This was 18 while the
    # pattern above required the feature key on the same line as `get_llm(`: one already-wrapped
    # conv_app_result callsite was invisible to it, so the count was calibrated against a scan that
    # silently skipped wrapped calls.
    total = len(conv_proc_calls) + len(kg_calls) + len(mem_calls)
    assert total == 20, f"Expected 20 total get_llm() callsites, got {total}"


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
# Tests for trigger_conversation_apps preferred-app shortcut (PR #4683, issue #4639)
# ---------------------------------------------------------------------------


def _make_mock_app(app_id, name="TestApp"):
    """Create a minimal App-like mock for trigger_conversation_apps tests."""
    app = MagicMock()
    app.id = app_id
    app.name = name
    app.works_with_memories.return_value = True
    app.enabled = True
    return app


def _setup_trigger_apps_mocks(preferred_app_id=None, default_apps=None, available_apps=None):
    """Set up the module-level mocks needed by trigger_conversation_apps."""
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
    """Create a minimal conversation mock for trigger_conversation_apps tests."""
    conv = MagicMock()
    conv.id = "conv-trigger-test"
    conv.get_transcript.return_value = "Speaker 0: Hello"
    conv.photos = []
    conv.apps_results = []
    conv.suggested_summarization_apps = suggested_apps
    return conv


def _trigger_apps_context(default_apps=None, availability_app=None):
    """Context manager that patches all external dependencies of trigger_conversation_apps.

    `availability_app` stands in for `get_available_app_model_by_id` — the
    set-preferred route's availability authority (#10074): None models a
    deleted/inaccessible app; an app object models one the setter admitted even
    though it is outside the enabled-installed slice.
    """
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
        patch.object(process_conversation, "get_available_app_model_by_id", return_value=availability_app),
    )


def test_trigger_apps_uses_preferred_app_skips_llm_suggestion():
    """When user has a valid preferred app, use it and skip the suggestion LLM call."""
    preferred = _make_mock_app("preferred-app-1", "PreferredApp")
    _setup_trigger_apps_mocks(preferred_app_id="preferred-app-1", available_apps=[preferred])
    conv = _make_trigger_conversation()

    suggestion_mock, app_result_mock, p1, p2, p3, p4, p5, p6 = _trigger_apps_context()
    # Override get_available_apps to return the preferred app
    p2 = patch.object(process_conversation, "get_available_apps", return_value=[preferred])

    with p1, p2, p3, p4, p5, p6:
        process_conversation.trigger_conversation_apps("user-preferred", conv)

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

    suggestion_mock, app_result_mock, p1, p2, p3, p4, p5, p6 = _trigger_apps_context(default_apps=[suggestion_app])

    with p1, p2, p3, p4, p5, p6:
        process_conversation.trigger_conversation_apps("user-stale", conv)

    # The suggestion LLM call SHOULD have been invoked since preferred app was invalid
    suggestion_mock.assert_called_once()


def test_trigger_apps_no_preferred_app_runs_suggestion():
    """When no preferred app is set, the suggestion LLM call should run."""
    suggestion_app = _make_mock_app("suggested-app", "SuggestedApp")
    _setup_trigger_apps_mocks(preferred_app_id=None)
    conv = _make_trigger_conversation()

    suggestion_mock, app_result_mock, p1, p2, p3, p4, p5, p6 = _trigger_apps_context(default_apps=[suggestion_app])

    with p1, p2, p3, p4, p5, p6:
        process_conversation.trigger_conversation_apps("user-no-pref", conv)

    # The suggestion LLM call SHOULD have been invoked
    suggestion_mock.assert_called_once()


def test_trigger_apps_opt_in_only_skips_default_and_suggestion(monkeypatch):
    """Notes v2 leaves the canonical note as the only default summary path.

    Apps-opt-in is derived from the pipeline mode, not separately configured, so this drives
    the one rollout switch rather than a second boolean."""
    monkeypatch.setenv('CONVERSATION_NOTES_V2_ENABLED', 'true')
    suggestion_app = _make_mock_app('suggested-app', 'SuggestedApp')
    _setup_trigger_apps_mocks(preferred_app_id=None)
    conv = _make_trigger_conversation()

    suggestion_mock, app_result_mock, p1, p2, p3, p4, p5, p6 = _trigger_apps_context(default_apps=[suggestion_app])
    with p1, p2, p3, p4, p5, p6:
        process_conversation.trigger_conversation_apps('user-opt-in-only', conv)

    suggestion_mock.assert_not_called()
    app_result_mock.assert_not_called()
    assert conv.apps_results == []


def test_trigger_apps_counts_a_successful_explicit_reprocess_selection(monkeypatch):
    monkeypatch.setenv('CONVERSATION_NOTES_V2_ENABLED', 'true')
    selected = _make_mock_app('selected-app', 'SelectedApp')
    _setup_trigger_apps_mocks(preferred_app_id=None)
    conv = _make_trigger_conversation()

    suggestion_mock, app_result_mock, p1, p2, p3, p4, p5, p6 = _trigger_apps_context()
    with p1, p2, p3, p4, p5 as record_usage, p6:
        process_conversation.trigger_conversation_apps(
            'user-explicit',
            conv,
            is_reprocess=True,
            app_id=selected.id,
            explicit_app=selected,
            usage_attribution=process_conversation.AppUsageAttribution.EXPLICIT_SELECTION,
        )

    suggestion_mock.assert_not_called()
    app_result_mock.assert_called_once()
    record_usage.assert_called_once_with(
        'user-explicit',
        selected.id,
        process_conversation.UsageHistoryType.memory_created_prompt,
        conversation_id=conv.id,
    )


@pytest.mark.parametrize('is_reprocess', [True, False], ids=['plain-regenerate', 'lazy-enrichment'])
def test_trigger_apps_does_not_count_non_user_reprocessing(is_reprocess):
    preferred = _make_mock_app('preferred-app', 'PreferredApp')
    _setup_trigger_apps_mocks(preferred_app_id=preferred.id, available_apps=[preferred])
    conv = _make_trigger_conversation()

    suggestion_mock, app_result_mock, p1, p2, p3, p4, p5, p6 = _trigger_apps_context()
    p2 = patch.object(process_conversation, 'get_available_apps', return_value=[preferred])
    with p1, p2, p3, p4, p5 as record_usage, p6:
        process_conversation.trigger_conversation_apps(
            'user-non-selection',
            conv,
            is_reprocess=is_reprocess,
            usage_attribution=process_conversation.AppUsageAttribution.NON_USER_REPROCESS,
        )

    suggestion_mock.assert_not_called()
    app_result_mock.assert_called_once()
    record_usage.assert_not_called()


def test_trigger_apps_opt_in_preferred_app_still_auto_runs(monkeypatch):
    """SCA-359: under notes v2 the Redis preferred app remains the one automatic app run."""
    monkeypatch.setenv('CONVERSATION_NOTES_V2_ENABLED', 'true')
    preferred = _make_mock_app('preferred-app', 'PreferredApp')
    _setup_trigger_apps_mocks(preferred_app_id='preferred-app', available_apps=[preferred])
    conv = _make_trigger_conversation()

    suggestion_mock, app_result_mock, p1, p2, p3, p4, p5, p6 = _trigger_apps_context()
    p2 = patch.object(process_conversation, 'get_available_apps', return_value=[preferred])
    with p1, p2, p3, p4, p5, p6:
        process_conversation.trigger_conversation_apps('user-preferred-opt-in', conv)

    suggestion_mock.assert_not_called()
    app_result_mock.assert_called_once()
    assert len(conv.apps_results) == 1


def test_trigger_apps_explicit_selection_execution_failure_is_fail_closed(monkeypatch):
    """SCA-359: an explicitly selected app whose execution fails must not read as success."""
    monkeypatch.setenv('CONVERSATION_NOTES_V2_ENABLED', 'true')
    selected = _make_mock_app('selected-app', 'SelectedApp')
    _setup_trigger_apps_mocks(preferred_app_id=None)
    conv = _make_trigger_conversation()

    suggestion_mock, app_result_mock, p1, p2, p3, p4, p5, p6 = _trigger_apps_context()
    app_result_mock.side_effect = RuntimeError('LLM unavailable')
    with p1, p2, p3, p4, p5, p6:
        with pytest.raises(process_conversation.ExplicitAppSelectionFailedError):
            process_conversation.trigger_conversation_apps(
                'user-explicit',
                conv,
                is_reprocess=True,
                app_id=selected.id,
                explicit_app=selected,
                usage_attribution=process_conversation.AppUsageAttribution.EXPLICIT_SELECTION,
            )

    suggestion_mock.assert_not_called()
    assert conv.apps_results == []


def test_trigger_apps_explicit_selection_empty_content_is_fail_closed(monkeypatch):
    """SCA-359: empty model output is a failed selection, not a silent notes fallback."""
    monkeypatch.setenv('CONVERSATION_NOTES_V2_ENABLED', 'true')
    selected = _make_mock_app('selected-app', 'SelectedApp')
    _setup_trigger_apps_mocks(preferred_app_id=None)
    conv = _make_trigger_conversation()

    suggestion_mock, app_result_mock, p1, p2, p3, p4, p5, p6 = _trigger_apps_context()
    app_result_mock.return_value = '   '
    with p1, p2, p3, p4, p5, p6:
        with pytest.raises(process_conversation.ExplicitAppSelectionFailedError):
            process_conversation.trigger_conversation_apps(
                'user-explicit',
                conv,
                is_reprocess=True,
                app_id=selected.id,
                explicit_app=selected,
                usage_attribution=process_conversation.AppUsageAttribution.EXPLICIT_SELECTION,
            )

    # Persist-as-today shape: the whitespace result is still appended for the
    # write-back; the failure contract is about the response, not the persist.
    assert [(r.app_id, r.content) for r in conv.apps_results] == [('selected-app', '')]


def test_trigger_apps_automatic_app_failure_stays_fail_open(monkeypatch):
    """Only explicit selections fail closed; automatic runs keep log-and-continue."""
    monkeypatch.setenv('CONVERSATION_NOTES_V2_ENABLED', 'true')
    preferred = _make_mock_app('preferred-app', 'PreferredApp')
    _setup_trigger_apps_mocks(preferred_app_id='preferred-app', available_apps=[preferred])
    conv = _make_trigger_conversation()

    suggestion_mock, app_result_mock, p1, p2, p3, p4, p5, p6 = _trigger_apps_context()
    app_result_mock.side_effect = RuntimeError('LLM unavailable')
    p2 = patch.object(process_conversation, 'get_available_apps', return_value=[preferred])
    with p1, p2, p3, p4, p5, p6:
        process_conversation.trigger_conversation_apps('user-automatic', conv)

    app_result_mock.assert_called_once()
    assert conv.apps_results == []


def test_summary_pipeline_mode_cannot_reach_the_regressing_combination(monkeypatch):
    """Legacy notes must never be paired with opt-in apps.

    That pair takes the app summary away and falls back to the short legacy overview — worse
    than either whole configuration. Deriving both from one switch makes it unrepresentable.
    """
    monkeypatch.delenv('CONVERSATION_NOTES_V2_ENABLED', raising=False)
    assert process_conversation.summary_pipeline_mode() is process_conversation.SummaryPipelineMode.LEGACY_APP_PRIMARY
    assert process_conversation.conversation_apps_opt_in_only() is False
    assert process_conversation._conversation_notes_v2_enabled() is False

    monkeypatch.setenv('CONVERSATION_NOTES_V2_ENABLED', 'true')
    assert process_conversation.summary_pipeline_mode() is process_conversation.SummaryPipelineMode.NOTES_V2_APPS_OPT_IN
    assert process_conversation.conversation_apps_opt_in_only() is True
    assert process_conversation._conversation_notes_v2_enabled() is True

    # A stale standalone override must not resurrect the fourth state.
    monkeypatch.delenv('CONVERSATION_NOTES_V2_ENABLED', raising=False)
    monkeypatch.setenv('CONVERSATION_APPS_OPT_IN_ONLY', 'true')
    assert process_conversation.conversation_apps_opt_in_only() is False


def test_trigger_apps_preferred_app_outside_installed_slice_is_still_used():
    """#10074: the set-preferred route admits apps the enabled-installed slice
    does not contain (e.g. a template whose enable call failed). The reader must
    honor the setter's availability authority instead of silently ignoring it."""
    preferred = _make_mock_app("template-app-1", "MyTemplate")
    _setup_trigger_apps_mocks(preferred_app_id="template-app-1")
    conv = _make_trigger_conversation()

    suggestion_mock, app_result_mock, p1, p2, p3, p4, p5, p6 = _trigger_apps_context(availability_app=preferred)

    with p1, p2, p3, p4, p5, p6:
        process_conversation.trigger_conversation_apps("user-template", conv)

    suggestion_mock.assert_not_called()
    app_result_mock.assert_called_once()
    assert len(conv.apps_results) == 1


def test_trigger_apps_preferred_app_without_memories_capability_falls_through():
    """A resolvable preferred app that cannot summarize (no memories capability)
    falls back to suggestions rather than running as a summarizer."""
    persona = _make_mock_app("persona-app-1", "ChatPersona")
    persona.works_with_memories.return_value = False
    suggestion_app = _make_mock_app("suggested-app", "SuggestedApp")
    _setup_trigger_apps_mocks(preferred_app_id="persona-app-1")
    conv = _make_trigger_conversation()

    suggestion_mock, app_result_mock, p1, p2, p3, p4, p5, p6 = _trigger_apps_context(
        default_apps=[suggestion_app], availability_app=persona
    )

    with p1, p2, p3, p4, p5, p6:
        process_conversation.trigger_conversation_apps("user-persona", conv)

    suggestion_mock.assert_called_once()


# Regression: the durable write happens before trigger_conversation_apps runs, so its app summary
# must be written back explicitly (like calendar_event / folder_id / audio_files already are).
# Without that write-back the LLM output is computed and discarded: the detail view falls back to
# structured.overview, a preferred summarization app never takes effect, the suggested-apps
# endpoint stays empty, and PATCH /v1/conversations/{id}/summary has no entry to update.


class _FakeAppResult:
    """Mirrors the AppResult shape the persistence path consumes."""

    def __init__(self, app_id, content):
        self.app_id = app_id
        self.content = content

    def dict(self):
        return {'app_id': self.app_id, 'content': self.content}


def test_app_summary_results_reach_the_database(monkeypatch):
    completed_conversation = Conversation(
        id='conversation-apps',
        created_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
        started_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
        finished_at=datetime(2026, 7, 21, 0, 1, tzinfo=timezone.utc),
        source=ConversationSource.omi,
        structured=Structured(title='Title', overview='Overview'),
        transcript_segments=[],
        status=ConversationStatus.completed,
        discarded=False,
    )

    persisted_payloads = []
    updates = []

    def persisted(_uid, payload, **_kwargs):
        persisted_payloads.append(payload)
        return True

    def update_conversation(_uid, _conversation_id, data):
        updates.append(data)

    def fake_trigger_apps(_uid, conversation, **_kwargs):
        # The real trigger_conversation_apps only mutates the in-memory conversation.
        conversation.suggested_summarization_apps = ['app-1']
        conversation.apps_results = [_FakeAppResult('app-1', 'APP SUMMARY')]

    input_conversation = MagicMock()
    input_conversation.source = 'omi'
    input_conversation.get_person_ids.return_value = []

    monkeypatch.setattr(process_conversation, '_get_structured', lambda *a, **k: (MagicMock(), False))
    monkeypatch.setattr(process_conversation, '_get_conversation_obj', lambda *a, **k: completed_conversation)
    monkeypatch.setattr(process_conversation.lifecycle_service, 'persist_processed_conversation', persisted)
    monkeypatch.setattr(process_conversation.lifecycle_service, 'create_completed_conversation', persisted)
    monkeypatch.setattr(process_conversation, 'trigger_conversation_apps', fake_trigger_apps)
    monkeypatch.setattr(process_conversation, 'submit_with_context', MagicMock())
    monkeypatch.setattr(process_conversation.conversations_db, 'update_conversation', update_conversation)
    monkeypatch.setattr(
        process_conversation.conversations_db, 'create_audio_files_from_chunks', MagicMock(return_value=[])
    )

    process_conversation.process_conversation('uid', 'en', input_conversation)

    # Everything that actually reached the database: the durable payload plus every write-back.
    written = {}
    for payload in persisted_payloads:
        if isinstance(payload, dict):
            written.update(payload)
    for update in updates:
        written.update(update)

    results = written.get('apps_results')
    assert results, 'app summary results never reached the database'
    assert results[0]['app_id'] == 'app-1'
    assert results[0]['content'] == 'APP SUMMARY'
    assert written.get('suggested_summarization_apps') == ['app-1']


def test_force_process_still_defers_folders_and_apps_when_jit_admits(monkeypatch):
    completed_conversation = Conversation(
        id='conversation-jit',
        created_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
        started_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
        finished_at=datetime(2026, 7, 21, 0, 1, tzinfo=timezone.utc),
        source=ConversationSource.omi,
        structured=Structured(title='Title', overview='Overview'),
        transcript_segments=[],
        status=ConversationStatus.completed,
        discarded=False,
    )

    claims: list[str] = []
    input_conversation = MagicMock()
    input_conversation.source = 'omi'
    input_conversation.get_person_ids.return_value = []

    monkeypatch.setattr(process_conversation, '_get_structured', lambda *a, **k: (MagicMock(), False))
    monkeypatch.setattr(process_conversation, '_get_conversation_obj', lambda *a, **k: completed_conversation)
    monkeypatch.setattr(process_conversation.lifecycle_service, 'persist_processed_conversation', lambda *a, **k: True)
    monkeypatch.setattr(process_conversation.lifecycle_service, 'create_completed_conversation', lambda *a, **k: True)
    monkeypatch.setattr(
        process_conversation,
        'resolve_authorized_first_open_plan',
        lambda **_kwargs: SimpleNamespace(defer_derived_work=True),
    )
    monkeypatch.setattr(
        process_conversation.conversations_db,
        'initialize_first_open_work',
        lambda uid, conversation_id, **_kwargs: claims.append(f'{uid}:{conversation_id}') or True,
    )
    monkeypatch.setattr(
        process_conversation.folders_db,
        'get_folders',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError('folders must defer under JIT')),
    )
    monkeypatch.setattr(
        process_conversation,
        'trigger_conversation_apps',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError('apps must defer under JIT')),
    )
    monkeypatch.setattr(process_conversation, 'submit_with_context', MagicMock())
    monkeypatch.setattr(process_conversation.conversations_db, 'update_conversation', MagicMock())
    monkeypatch.setattr(
        process_conversation.conversations_db, 'create_audio_files_from_chunks', MagicMock(return_value=[])
    )

    process_conversation.process_conversation('uid', 'en', input_conversation, force_process=True)

    assert claims == ['uid:conversation-jit']


def test_finalization_survives_an_extraction_run_with_no_grounded_candidates(monkeypatch):
    """Regression: when every L1 candidate failed grounding, canonical extraction
    raised and took the rest of finalization with it — action items, goal
    progress, audio files and the created webhook never ran, and the caller
    (developer conversation intake, sync enrichment) returned 500. Grounding is
    a verdict on the memories only: the replacement is skipped, finalization
    continues."""
    from models.transcript_segment import TranscriptSegment

    completed_conversation = Conversation(
        id='conversation-ungrounded',
        created_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
        started_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
        finished_at=datetime(2026, 7, 21, 0, 1, tzinfo=timezone.utc),
        source=ConversationSource.omi,
        structured=Structured(title='Title', overview='Overview'),
        transcript_segments=[
            TranscriptSegment(
                text='We discussed ordinary weekend plans and a grocery list.',
                speaker='SPEAKER_00',
                is_user=True,
                start=0.0,
                end=4.0,
            )
        ],
        status=ConversationStatus.completed,
        discarded=False,
    )

    memory_service = MagicMock()
    submitted = MagicMock()

    input_conversation = MagicMock()
    input_conversation.source = 'omi'
    input_conversation.get_person_ids.return_value = []

    monkeypatch.setattr(process_conversation, '_get_structured', lambda *a, **k: (MagicMock(), False))
    monkeypatch.setattr(process_conversation, '_get_conversation_obj', lambda *a, **k: completed_conversation)
    monkeypatch.setattr(process_conversation.lifecycle_service, 'persist_processed_conversation', lambda *a, **k: True)
    monkeypatch.setattr(process_conversation.lifecycle_service, 'create_completed_conversation', lambda *a, **k: True)
    monkeypatch.setattr(process_conversation, 'trigger_conversation_apps', lambda *a, **k: None)
    monkeypatch.setattr(process_conversation, 'submit_with_context', submitted)
    monkeypatch.setattr(process_conversation.conversations_db, 'update_conversation', lambda *a, **k: None)
    monkeypatch.setattr(process_conversation, 'MemoryService', lambda db_client: memory_service)
    monkeypatch.setattr(process_conversation.users_db, 'get_user_language_preference', lambda uid: 'en')
    monkeypatch.setattr(
        process_conversation,
        'extract_canonical_l1_memory_candidates',
        MagicMock(
            return_value=[
                SimpleNamespace(
                    content='The user was diagnosed with condition X.',
                    evidence_quotes=['I was diagnosed with condition X'],
                    speaker_label='SPEAKER_00',
                    speaker_scope='session-local',
                    about='the user',
                    risk_flags=[],
                    archive_class='general',
                )
            ]
        ),
    )

    process_conversation.process_conversation('uid', 'en', input_conversation)

    # Nothing is written or retracted for the source ...
    memory_service.replace_conversation_memories.assert_not_called()
    # ... and the effects sequenced after extraction still ran.
    assert '_save_action_items' in {getattr(call.args[1], '__name__', '') for call in submitted.call_args_list}


def test_finalization_survives_an_unavailable_memory_extractor(monkeypatch):
    """Regression: an LLM invoke failure inside canonical extraction (prod:
    openai.APITimeoutError -> WorkingObservationExtractionError) propagated out
    of finalization, so the conversation also lost its action items, goal
    progress, audio files and created webhook and the caller returned 500. A
    provider that did not answer is a verdict on the memories only."""
    from models.transcript_segment import TranscriptSegment
    from models.memory_contracts import WorkingObservationExtractionError

    completed_conversation = Conversation(
        id='conversation-extractor-unavailable',
        created_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
        started_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
        finished_at=datetime(2026, 7, 21, 0, 1, tzinfo=timezone.utc),
        source=ConversationSource.omi,
        structured=Structured(title='Title', overview='Overview'),
        transcript_segments=[
            TranscriptSegment(
                text='We discussed ordinary weekend plans and a grocery list.',
                speaker='SPEAKER_00',
                is_user=True,
                start=0.0,
                end=4.0,
            )
        ],
        status=ConversationStatus.completed,
        discarded=False,
    )

    memory_service = MagicMock()
    submitted = MagicMock()

    input_conversation = MagicMock()
    input_conversation.source = 'omi'
    input_conversation.get_person_ids.return_value = []

    monkeypatch.setattr(process_conversation, '_get_structured', lambda *a, **k: (MagicMock(), False))
    monkeypatch.setattr(process_conversation, '_get_conversation_obj', lambda *a, **k: completed_conversation)
    monkeypatch.setattr(process_conversation.lifecycle_service, 'persist_processed_conversation', lambda *a, **k: True)
    monkeypatch.setattr(process_conversation.lifecycle_service, 'create_completed_conversation', lambda *a, **k: True)
    monkeypatch.setattr(process_conversation, 'trigger_conversation_apps', lambda *a, **k: None)
    monkeypatch.setattr(process_conversation, 'submit_with_context', submitted)
    monkeypatch.setattr(process_conversation.conversations_db, 'update_conversation', lambda *a, **k: None)
    monkeypatch.setattr(process_conversation, 'MemoryService', lambda db_client: memory_service)
    monkeypatch.setattr(process_conversation.users_db, 'get_user_language_preference', lambda uid: 'en')
    monkeypatch.setattr(
        process_conversation,
        'extract_canonical_l1_memory_candidates',
        MagicMock(side_effect=WorkingObservationExtractionError("invoke")),
    )

    process_conversation.process_conversation('uid', 'en', input_conversation)

    # Prior memories are neither replaced nor retracted ...
    memory_service.replace_conversation_memories.assert_not_called()
    # ... and the effects sequenced after extraction still ran.
    assert '_save_action_items' in {getattr(call.args[1], '__name__', '') for call in submitted.call_args_list}


def test_custom_stt_conversation_without_llm_byok_key_runs_llm_work(monkeypatch):
    """Regression for #7690's revert: custom-STT users transcribe on their own
    provider, but their conversations must still get Omi summaries. The gate
    that skipped all LLM post-processing for a custom-STT conversation with no
    LLM BYOK key left those users with no title, overview, or memories."""
    completed_conversation = Conversation(
        id='conversation-custom-stt',
        created_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
        started_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
        finished_at=datetime(2026, 7, 21, 0, 1, tzinfo=timezone.utc),
        source=ConversationSource.omi,
        structured=Structured(title='Title', overview='Overview'),
        transcript_segments=[],
        status=ConversationStatus.completed,
        discarded=False,
        uses_custom_stt=True,
    )

    structured_calls = []
    monkeypatch.setattr(
        process_conversation, '_get_structured', lambda *a, **k: structured_calls.append(1) or (MagicMock(), False)
    )
    monkeypatch.setattr(process_conversation, '_get_conversation_obj', lambda *a, **k: completed_conversation)
    monkeypatch.setattr(process_conversation, 'trigger_conversation_apps', lambda *a, **k: None)
    monkeypatch.setattr(process_conversation, 'submit_with_context', MagicMock())
    # No LLM BYOK key: enrichment must run anyway, on Omi's bill.
    monkeypatch.setattr(process_conversation.users_db, 'is_byok_active', lambda _uid: False)

    process_conversation.process_conversation('uid', 'en', completed_conversation)

    assert structured_calls, 'LLM structuring was skipped for a custom-STT conversation'


def test_custom_stt_conversation_with_llm_byok_key_runs_llm_work(monkeypatch):
    """A custom-STT user who brings their own LLM key keeps full enrichment."""
    completed_conversation = Conversation(
        id='conversation-custom-stt-byok',
        created_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
        started_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
        finished_at=datetime(2026, 7, 21, 0, 1, tzinfo=timezone.utc),
        source=ConversationSource.omi,
        structured=Structured(title='Title', overview='Overview'),
        transcript_segments=[],
        status=ConversationStatus.completed,
        discarded=False,
        uses_custom_stt=True,
    )

    input_conversation = MagicMock()
    input_conversation.source = 'omi'
    input_conversation.get_person_ids.return_value = []
    input_conversation.uses_custom_stt = True

    structured_calls = []
    monkeypatch.setattr(
        process_conversation, '_get_structured', lambda *a, **k: structured_calls.append(1) or (MagicMock(), False)
    )
    monkeypatch.setattr(process_conversation, '_get_conversation_obj', lambda *a, **k: completed_conversation)
    monkeypatch.setattr(process_conversation, 'trigger_conversation_apps', lambda *a, **k: None)
    monkeypatch.setattr(process_conversation, 'submit_with_context', MagicMock())
    monkeypatch.setattr(process_conversation.users_db, 'is_byok_active', lambda _uid: True)

    process_conversation.process_conversation('uid', 'en', input_conversation)

    assert structured_calls, 'LLM structuring was skipped despite an LLM BYOK key'


def test_dedup_candidates_exclude_own_and_merge_source_items():
    """Regression: on reprocess/merge, the conversation's own previous action
    items (and the merge sources') came back as dedup candidates — the LLM
    suppressed re-extracting them and the save step then deleted them, so
    tasks silently vanished. Items from the conversation being processed or
    its merge sources must never be dedup candidates."""
    import sys
    from datetime import datetime, timezone
    from types import SimpleNamespace

    now = datetime.now(timezone.utc)
    items = [
        {'id': 'own', 'conversation_id': 'conv-1', 'completed': False, 'updated_at': now},
        {'id': 'merged', 'conversation_id': 'src-conv', 'completed': False, 'updated_at': now},
        {'id': 'unrelated', 'conversation_id': 'other-conv', 'completed': False, 'updated_at': now},
    ]
    similar = [{'action_item_id': item['id'], 'score': 0.9} for item in items]
    action_items_mod = sys.modules["database.action_items"]
    action_items_mod.get_action_items_by_ids = MagicMock(return_value=items)

    conversation = SimpleNamespace(
        id='conv-1',
        external_data={'merge_metadata': {'source_conversation_ids': ['src-conv']}},
    )
    structured = SimpleNamespace(overview='discussed follow-ups')

    with patch.object(process_conversation, "find_similar_action_items", MagicMock(return_value=similar)):
        eligible = process_conversation._fetch_dedup_candidates('user-1', structured, conversation)

    assert [item['id'] for item in eligible] == ['unrelated']


def test_dedup_candidates_unchanged_without_conversation_context():
    """Without a conversation (new-conversation path has a fresh id), all open
    recent items remain candidates."""
    import sys
    from datetime import datetime, timezone
    from types import SimpleNamespace

    now = datetime.now(timezone.utc)
    items = [{'id': 'open-item', 'conversation_id': 'other-conv', 'completed': False, 'updated_at': now}]
    action_items_mod = sys.modules["database.action_items"]
    action_items_mod.get_action_items_by_ids = MagicMock(return_value=items)

    similar = [{'action_item_id': 'open-item', 'score': 0.9}]
    structured = SimpleNamespace(overview='discussed follow-ups')

    with patch.object(process_conversation, "find_similar_action_items", MagicMock(return_value=similar)):
        eligible = process_conversation._fetch_dedup_candidates('user-1', structured)

    assert [item['id'] for item in eligible] == ['open-item']


def _ledger_gate_conversation(conversation_id: str) -> Conversation:
    return Conversation(
        id=conversation_id,
        created_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
        started_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
        finished_at=datetime(2026, 8, 25, 0, 1, tzinfo=timezone.utc),
        source=ConversationSource.omi,
        language='en',
        structured=Structured(title='t', overview='o'),
        transcript_segments=[
            TranscriptSegment(
                id='seg-1',
                text='hello there, this is a transcript segment',
                speaker='SPEAKER_00',
                speaker_id=0,
                is_user=True,
                start=0.0,
                end=1.0,
            )
        ],
        status=ConversationStatus.processing,
    )


def test_ledger_writer_mode_skips_eager_extraction(monkeypatch):
    """A cut-over (ledger writer mode) user must not pay for per-conversation
    L1 extraction: the compatibility write would be refused by writer admission
    after the model call was already spent, failing finalization. The daily
    sweep owns memory formation for those users, so the public boundary
    returns before parity capture or any model work."""
    import sys

    from models.memory_apply import WriterMode

    memory_system_stub = sys.modules['utils.memory.memory_system']
    monkeypatch.setattr(
        memory_system_stub,
        'ensure_canonical_apply_control_state',
        lambda uid, *, db_client: SimpleNamespace(writer_mode=WriterMode.ledger),
        raising=False,
    )
    inner = MagicMock(side_effect=AssertionError('extraction must not run under ledger writer mode'))
    monkeypatch.setattr(process_conversation, '_extract_memories_inner', inner)
    admitted = []

    class _MemoryService:
        def __init__(self, *, db_client):
            pass

        def ensure_canonical_mutation_ready(self, uid):
            admitted.append(uid)

    monkeypatch.setattr(process_conversation, 'MemoryService', _MemoryService)

    process_conversation.extract_memories('uid-ledger', _ledger_gate_conversation('conv-ledger'))

    assert admitted == ['uid-ledger']
    inner.assert_not_called()


def test_canonical_provider_degradation_emits_bounded_finalization_reason(monkeypatch):
    recorded = []
    monkeypatch.setattr(process_conversation, 'record_finalization_failure', recorded.append)
    monkeypatch.setattr(process_conversation, 'record_fallback', lambda **_fields: None)

    result = process_conversation._canonical_extraction_unavailable(
        SimpleNamespace(id='conversation-1'),
        process_conversation.PATH_CANONICAL,
        RuntimeError('private provider response'),
    )

    assert result.count == 0
    assert recorded == [process_conversation.FinalizationFailureReason.provider]


def test_memory_capability_fence_precedes_sweep_owned_writer_short_circuit(monkeypatch):
    sweep_mode = MagicMock(side_effect=AssertionError('writer mode must not bypass static capability admission'))
    monkeypatch.setattr(process_conversation, '_sweep_owned_writer_mode', sweep_mode)

    class _MemoryService:
        def __init__(self, *, db_client):
            pass

        def ensure_canonical_mutation_ready(self, uid):
            raise RuntimeError('static memory admission failed')

    monkeypatch.setattr(process_conversation, 'MemoryService', _MemoryService)

    with pytest.raises(RuntimeError, match='static memory admission failed'):
        process_conversation.extract_memories('uid-ledger', _ledger_gate_conversation('conv-ledger'))

    sweep_mode.assert_not_called()


def test_compatibility_writer_mode_still_runs_eager_extraction(monkeypatch):
    import sys

    from models.memory_apply import WriterMode

    memory_system_stub = sys.modules['utils.memory.memory_system']
    monkeypatch.setattr(
        memory_system_stub,
        'ensure_canonical_apply_control_state',
        lambda uid, *, db_client: SimpleNamespace(writer_mode=WriterMode.compatibility),
        raising=False,
    )
    inner = MagicMock(
        return_value=process_conversation.ConversationMemoryExtractionResult(
            count=0, source='transcription', path='canonical'
        )
    )
    monkeypatch.setattr(process_conversation, '_extract_memories_inner', inner)

    process_conversation.extract_memories('uid-compat', _ledger_gate_conversation('conv-compat'))

    inner.assert_called_once()


def test_unreadable_writer_mode_preserves_legacy_extraction(monkeypatch):
    import sys

    memory_system_stub = sys.modules['utils.memory.memory_system']

    def unavailable(uid, *, db_client):
        raise RuntimeError('control state unreadable')

    monkeypatch.setattr(memory_system_stub, 'ensure_canonical_apply_control_state', unavailable, raising=False)
    inner = MagicMock(
        return_value=process_conversation.ConversationMemoryExtractionResult(
            count=0, source='transcription', path='canonical'
        )
    )
    monkeypatch.setattr(process_conversation, '_extract_memories_inner', inner)

    process_conversation.extract_memories('uid-err', _ledger_gate_conversation('conv-err'))

    inner.assert_called_once()

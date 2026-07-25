"""Shared sys.modules stub install/teardown helpers for memory unit tests."""

from __future__ import annotations

import hashlib
import os
import sys
import types
import uuid
from types import ModuleType
from typing import Callable, Iterable, Mapping, MutableMapping, Sequence
from unittest.mock import MagicMock

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


class AutoMockModule(ModuleType):
    """Import-complete stub: missing attributes resolve to MagicMock (no cross-test leak)."""

    def __getattr__(self, name: str):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


def snapshot_sys_modules(names: Iterable[str]) -> dict[str, ModuleType | None]:
    return {name: sys.modules.get(name) for name in names}


def restore_sys_modules(saved: Mapping[str, ModuleType | None]) -> None:
    for name, original in saved.items():
        current = sys.modules.get(name)
        if original is None:
            removed = sys.modules.pop(name, None)
            if "." in name:
                parent_name, child_name = name.rsplit(".", 1)
                parent = sys.modules.get(parent_name)
                if (
                    isinstance(parent, ModuleType)
                    and hasattr(parent, child_name)
                    and getattr(parent, child_name, None) is (removed or current)
                ):
                    delattr(parent, child_name)
        else:
            sys.modules[name] = original
            if "." in name:
                parent_name, child_name = name.rsplit(".", 1)
                parent = sys.modules.get(parent_name)
                if isinstance(parent, ModuleType):
                    setattr(parent, child_name, original)


def drop_stale_module(module_name: str, expected_file: str) -> None:
    module = sys.modules.get(module_name)
    if module is None:
        return
    module_file = getattr(module, "__file__", None)
    if isinstance(module_file, str) and os.path.abspath(module_file) == expected_file:
        return
    sys.modules.pop(module_name, None)
    if "." not in module_name:
        return
    parent_name, child_name = module_name.rsplit(".", 1)
    parent = sys.modules.get(parent_name)
    if isinstance(parent, ModuleType) and getattr(parent, child_name, None) is module:
        delattr(parent, child_name)


def make_database_client_stub() -> ModuleType:
    client_mod = types.ModuleType("database._client")
    client_mod.db = MagicMock()
    client_mod.get_firestore_client = lambda: client_mod.db

    def _document_id_from_seed(seed: str) -> str:
        seed_hash = hashlib.sha256(seed.encode("utf-8")).digest()
        return str(uuid.UUID(bytes=seed_hash[:16], version=4))

    client_mod.document_id_from_seed = _document_id_from_seed
    return client_mod


def install_database_client_stub() -> ModuleType:
    stub = make_database_client_stub()
    sys.modules["database._client"] = stub
    database_pkg = sys.modules.get("database")
    if isinstance(database_pkg, ModuleType):
        setattr(database_pkg, "_client", stub)
    return stub


def install_canonical_write_runtime_stubs() -> list[str]:
    """Stubs for write_canonical_extraction_memory → atom_keyword_index import chain."""
    touched: list[str] = []

    firebase_admin = types.ModuleType("firebase_admin")
    firebase_admin.auth = MagicMock()
    sys.modules["firebase_admin"] = firebase_admin
    touched.append("firebase_admin")

    subscription_mod = types.ModuleType("utils.subscription")
    subscription_mod.get_default_basic_subscription = MagicMock()
    subscription_mod.is_trial_paywalled = lambda uid: False
    subscription_mod.should_defer_desktop_processing = lambda uid: False
    sys.modules["utils.subscription"] = subscription_mod
    touched.append("utils.subscription")

    users_mod = AutoMockModule("database.users")
    users_mod.get_data_protection_level = MagicMock(return_value="enhanced")
    sys.modules["database.users"] = users_mod
    touched.append("database.users")

    pinecone_mod = types.ModuleType("pinecone")
    pinecone_mod.Pinecone = MagicMock()
    sys.modules["pinecone"] = pinecone_mod
    touched.append("pinecone")

    typesense_mod = types.ModuleType("typesense")
    typesense_mod.Client = MagicMock()
    sys.modules["typesense"] = typesense_mod
    touched.append("typesense")

    vector_db_mod = AutoMockModule("database.vector_db")
    vector_db_mod.upsert_canonical_memory_vector = MagicMock()
    vector_db_mod.delete_canonical_memory_vector = MagicMock()
    sys.modules["database.vector_db"] = vector_db_mod
    touched.append("database.vector_db")

    return touched


def install_ws_i_heavy_import_stubs() -> list[str]:
    """Install heavy-import stubs used by WS-I process_conversation / memories router tests."""
    touched: list[str] = []

    def _set(name: str, module: ModuleType) -> None:
        sys.modules[name] = module
        touched.append(name)

    firebase_admin = types.ModuleType("firebase_admin")
    firebase_admin.auth = MagicMock()
    _set("firebase_admin", firebase_admin)

    langchain_core = types.ModuleType("langchain_core")
    langchain_core.output_parsers = types.ModuleType("langchain_core.output_parsers")
    langchain_core.output_parsers.PydanticOutputParser = MagicMock()
    langchain_core.prompts = types.ModuleType("langchain_core.prompts")
    langchain_core.prompts.ChatPromptTemplate = MagicMock()
    _set("langchain_core", langchain_core)
    _set("langchain_core.output_parsers", langchain_core.output_parsers)
    _set("langchain_core.prompts", langchain_core.prompts)

    langchain_core.callbacks = types.ModuleType("langchain_core.callbacks")
    langchain_core.callbacks.BaseCallbackHandler = type("BaseCallbackHandler", (), {})
    _set("langchain_core.callbacks", langchain_core.callbacks)

    usage_tracker_mod = types.ModuleType("utils.llm.usage_tracker")
    usage_tracker_mod.track_usage = lambda *args, **kwargs: None

    class _Features:
        pass

    usage_tracker_mod.Features = _Features
    _set("utils.llm.usage_tracker", usage_tracker_mod)

    for name in (
        "anthropic",
        "utils.llm.clients",
        "utils.llm.gateway_client",
        "utils.llm.chat",
        "utils.retrieval.rag",
        "utils.other.hume",
        "utils.other.storage",
        "utils.analytics",
        "utils.conversations.calendar_linking",
    ):
        _set(name, AutoMockModule(name))

    langchain_core.runnables = types.ModuleType("langchain_core.runnables")
    langchain_core.runnables.RunnableConfig = dict
    _set("langchain_core.runnables", langchain_core.runnables)

    langchain = types.ModuleType("langchain")
    langchain.prompts = types.ModuleType("langchain.prompts")
    langchain.prompts.PromptTemplate = MagicMock()
    langchain.prompts.ChatPromptTemplate = MagicMock()
    _set("langchain", langchain)
    _set("langchain.prompts", langchain.prompts)

    _set("stripe", types.ModuleType("stripe"))

    subjects_mod = types.ModuleType("utils.conversations.subjects")
    subjects_mod.infer_subject_from_segments = lambda segments: (None, None)
    _set("utils.conversations.subjects", subjects_mod)

    conversation_processing_mod = AutoMockModule("utils.llm.conversation_processing")
    _set("utils.llm.conversation_processing", conversation_processing_mod)

    pinecone_mod = types.ModuleType("pinecone")
    pinecone_mod.Pinecone = MagicMock()
    _set("pinecone", pinecone_mod)

    auth_mod = AutoMockModule("database.auth")
    auth_mod.get_user_name = lambda uid: "Test User"
    auth_mod.get_current_user_uid = MagicMock()
    auth_mod.with_rate_limit = lambda fn, *args, **kwargs: fn
    _set("database.auth", auth_mod)

    users_mod = AutoMockModule("database.users")
    users_mod.get_user_language_preference = lambda uid: "en"
    users_mod.get_data_protection_level = MagicMock(return_value="enhanced")
    _set("database.users", users_mod)

    subscription_mod = types.ModuleType("utils.subscription")
    subscription_mod.get_default_basic_subscription = MagicMock()
    subscription_mod.is_trial_paywalled = lambda uid: False
    subscription_mod.should_defer_desktop_processing = lambda uid: False
    _set("utils.subscription", subscription_mod)

    vector_db_mod = AutoMockModule("database.vector_db")
    vector_db_mod.find_similar_memories = MagicMock(return_value=[])
    vector_db_mod.delete_memory_vector = MagicMock()
    vector_db_mod.upsert_memory_vector = MagicMock()
    vector_db_mod.delete_memory_vectors_batch = MagicMock()
    vector_db_mod.upsert_memory_vectors_batch = MagicMock()
    vector_db_mod.upsert_action_item_vectors_batch = MagicMock()
    vector_db_mod.delete_action_item_vectors_batch = MagicMock()
    vector_db_mod.find_similar_action_items = MagicMock(return_value=[])
    vector_db_mod.upsert_vector2 = MagicMock()
    vector_db_mod.update_vector_metadata = MagicMock()
    vector_db_mod.upsert_transcript_chunk_vectors = MagicMock()
    vector_db_mod.query_vectors = MagicMock(return_value=[])
    _set("database.vector_db", vector_db_mod)

    memories_mod = AutoMockModule("database.memories")
    memories_mod.save_memories = MagicMock()
    memories_mod.delete_memories_for_conversation = MagicMock(return_value={"vector_delete_ids": []})
    memories_mod.get_memories = MagicMock(return_value=[])
    memories_mod.get_memory = MagicMock(return_value=None)
    memories_mod.invalidate_memory = MagicMock()
    memories_mod.set_memory_kg_extracted = MagicMock()
    _set("database.memories", memories_mod)

    import database

    database.vector_db = vector_db_mod
    database.memories = memories_mod

    for name in (
        "database.redis_db",
        "database.conversations",
        "database.notifications",
        "database.tasks",
        "database.trends",
        "database.action_items",
        "database.folders",
        "database.calendar_meetings",
        "database.apps",
        "database.short_term_memories",
        "database.review_queue",
        "utils.executors",
        "utils.other.endpoints",
        "utils.apps",
        "utils.llm.memories",
        "utils.llm.trends",
        "utils.llm.goals",
        "utils.llm.external_integrations",
        "utils.llm.conversations",
        "utils.llm.processing",
        "utils.llm.speaker_assignment",
        "utils.llm.diarization",
        "utils.llm.speaker_id",
        "utils.llm.speaker_embedding",
        "utils.llm.speech_profile",
        "utils.llm.knowledge_graph",
        "utils.billing",
        "utils.webhooks",
        "utils.notifications",
        "utils.conversations.memories",
        "utils.conversations.factory",
        "utils.conversations.subjects",
        "utils.conversations.transcript_chunks",
        "utils.retrieval.tools.memory_tools",
    ):
        if name not in sys.modules:
            _set(name, AutoMockModule(name))

    return touched


WS_I_HEAVY_STUB_MODULE_NAMES = (
    "firebase_admin",
    "langchain_core",
    "langchain_core.output_parsers",
    "langchain_core.prompts",
    "langchain_core.callbacks",
    "langchain_core.runnables",
    "utils.llm.usage_tracker",
    "anthropic",
    "utils.llm.clients",
    "utils.llm.gateway_client",
    "utils.llm.chat",
    "utils.retrieval.rag",
    "utils.other.hume",
    "utils.other.storage",
    "utils.analytics",
    "utils.conversations.calendar_linking",
    "langchain",
    "langchain.prompts",
    "stripe",
    "utils.conversations.subjects",
    "utils.llm.conversation_processing",
    "pinecone",
    "database.auth",
    "database.users",
    "utils.subscription",
    "database.vector_db",
    "database.memories",
    "database.redis_db",
    "database.conversations",
    "database.notifications",
    "database.tasks",
    "database.trends",
    "database.action_items",
    "database.folders",
    "database.calendar_meetings",
    "database.apps",
    "database.short_term_memories",
    "database.review_queue",
    "utils.executors",
    "utils.other.endpoints",
    "utils.apps",
    "utils.llm.memories",
    "utils.llm.trends",
    "utils.llm.goals",
    "utils.llm.external_integrations",
    "utils.llm.conversations",
    "utils.llm.processing",
    "utils.llm.speaker_assignment",
    "utils.llm.diarization",
    "utils.llm.speaker_id",
    "utils.llm.speaker_embedding",
    "utils.llm.speech_profile",
    "utils.llm.knowledge_graph",
    "utils.billing",
    "utils.webhooks",
    "utils.notifications",
    "utils.conversations.memories",
    "utils.conversations.factory",
    "utils.conversations.transcript_chunks",
    "utils.retrieval.tools.memory_tools",
)


def install_ws_c_backfill_stubs() -> list[str]:
    touched = install_canonical_write_runtime_stubs()

    stripe_mod = types.ModuleType("stripe")
    sys.modules["stripe"] = stripe_mod
    touched.append("stripe")

    pinecone_mod = types.ModuleType("pinecone")
    pinecone_mod.Pinecone = MagicMock()
    sys.modules["pinecone"] = pinecone_mod
    touched.append("pinecone")

    vector_db_mod = AutoMockModule("database.vector_db")
    vector_db_mod.find_similar_memories = MagicMock(return_value=[])
    vector_db_mod.get_memories_by_ids = MagicMock(return_value=[])
    sys.modules["database.vector_db"] = vector_db_mod
    touched.append("database.vector_db")

    memories_mod = AutoMockModule("database.memories")
    sys.modules["database.memories"] = memories_mod
    touched.append("database.memories")

    return touched


def install_ws_j_heavy_import_stubs() -> list[str]:
    touched: list[str] = []

    firebase_admin = types.ModuleType("firebase_admin")
    firebase_admin.auth = MagicMock()
    sys.modules["firebase_admin"] = firebase_admin
    touched.append("firebase_admin")

    pinecone_mod = types.ModuleType("pinecone")
    pinecone_mod.Pinecone = MagicMock()
    sys.modules["pinecone"] = pinecone_mod
    touched.append("pinecone")

    vector_db_mod = AutoMockModule("database.vector_db")
    vector_db_mod.find_similar_memories = MagicMock(return_value=[])
    vector_db_mod.upsert_memory_vector = MagicMock()
    vector_db_mod.delete_memory_vector = MagicMock()
    vector_db_mod.delete_pinecone_memory_vectors_by_id = MagicMock(return_value=0)
    vector_db_mod.delete_memory_vectors_batch = MagicMock()
    sys.modules["database.vector_db"] = vector_db_mod
    touched.append("database.vector_db")

    import database

    database.vector_db = vector_db_mod

    for name in (
        "database.redis_db",
        "database.conversations",
        "database.notifications",
        "database.action_items",
        "database.short_term_memories",
        "database.review_queue",
        "utils.executors",
        "utils.other.endpoints",
        "utils.other.storage",
        "utils.llm.knowledge_graph",
        "utils.conversations.factory",
        "utils.conversations.process_conversation",
        "utils.conversations.search",
        "utils.conversations.calendar_linking",
        "utils.speaker_identification",
        "utils.app_integrations",
        "utils.analytics",
        "utils.subscription",
        "utils.webhooks",
        "utils.billing",
        "utils.llm.conversation_processing",
        "utils.llm.conversations",
        "database.auth",
        "database.users",
        "database.memories",
        "database.chat",
        "database.user_usage",
        "database.daily_summaries",
        "database.llm_usage",
        "database.app_review_config",
        "database.webhook_health",
        "stripe",
        "pytz",
        "twilio",
        "google.cloud",
        "google.api_core",
        "opuslib",
        "pydub",
        "modal",
        "ulid",
        "typesense",
    ):
        if name not in sys.modules:
            sys.modules[name] = AutoMockModule(name)
            touched.append(name)

    return touched


class _EmptyVectorResult:
    def __init__(self, hits=None, rejected_count=0):
        self.hits = hits if hits is not None else []
        self.rejected_count = rejected_count


def install_ws_m_heavy_import_stubs() -> list[str]:
    touched: list[str] = []

    firebase_admin = types.ModuleType("firebase_admin")
    firebase_admin.auth = MagicMock()
    sys.modules["firebase_admin"] = firebase_admin
    touched.append("firebase_admin")

    pinecone_mod = types.ModuleType("pinecone")
    pinecone_mod.Pinecone = MagicMock()
    sys.modules["pinecone"] = pinecone_mod
    touched.append("pinecone")

    vector_db_mod = AutoMockModule("database.vector_db")
    vector_db_mod.find_similar_memories = MagicMock(return_value=[])
    vector_db_mod.query_memory_vector_candidates = MagicMock(return_value=_EmptyVectorResult())
    vector_db_mod.delete_pinecone_memory_vectors_by_id = MagicMock(return_value=0)
    sys.modules["database.vector_db"] = vector_db_mod
    touched.append("database.vector_db")

    import database

    database.vector_db = vector_db_mod

    users_mod = AutoMockModule("database.users")
    users_mod.get_data_protection_level = MagicMock(return_value="enhanced")
    sys.modules["database.users"] = users_mod
    touched.append("database.users")

    for name in (
        "database.redis_db",
        "database.conversations",
        "database.memories",
        "utils.subscription",
        "utils.executors",
        "utils.llm.knowledge_graph",
        "stripe",
        "pytz",
        "google.cloud",
        "google.api_core",
        "modal",
        "ulid",
        "typesense",
    ):
        if name not in sys.modules:
            sys.modules[name] = AutoMockModule(name)
            touched.append(name)

    return touched


def install_ws_n_heavy_import_stubs() -> list[str]:
    touched: list[str] = []

    firebase_admin = types.ModuleType("firebase_admin")
    firebase_admin.auth = MagicMock()
    sys.modules["firebase_admin"] = firebase_admin
    touched.append("firebase_admin")

    kg_mod = types.ModuleType("database.knowledge_graph")
    kg_mod.get_knowledge_graph = MagicMock(return_value={"nodes": [], "edges": []})
    kg_mod.get_knowledge_nodes = MagicMock(return_value=[])
    kg_mod.get_knowledge_edges = MagicMock(return_value=[])
    kg_mod.upsert_knowledge_node = MagicMock()
    kg_mod.upsert_knowledge_edge = MagicMock()
    kg_mod.delete_knowledge_graph = MagicMock()
    sys.modules["database.knowledge_graph"] = kg_mod
    touched.append("database.knowledge_graph")

    for name in (
        "database.redis_db",
        "database.conversations",
        "database.memories",
        "database.vector_db",
        "database.users",
        "utils.subscription",
        "utils.executors",
        "utils.llm.knowledge_graph",
        "stripe",
        "pytz",
        "google.cloud",
        "google.api_core",
        "modal",
        "ulid",
        "typesense",
    ):
        if name not in sys.modules:
            sys.modules[name] = AutoMockModule(name)
            touched.append(name)

    return touched


def install_ws_c_import_stubs() -> list[str]:
    """Install stubs for WS-C backfill tests (database client + backfill chain)."""
    install_database_client_stub()
    touched = ["database._client", *install_ws_c_backfill_stubs()]
    return list(dict.fromkeys(touched))


def install_ws_b_import_stubs() -> list[str]:
    """Install stubs for WS-B short-term lifecycle tests."""
    for name in ("database.vector_db",):
        sys.modules.pop(name, None)
    install_database_client_stub()
    touched = ["database._client", *install_canonical_write_runtime_stubs()]
    return list(dict.fromkeys(touched))


WS_B_STUB_MODULE_NAMES = (
    "database._client",
    "firebase_admin",
    "utils.subscription",
    "database.users",
    "pinecone",
    "typesense",
    "database.vector_db",
)

WS_C_STUB_MODULE_NAMES = (
    "database._client",
    "firebase_admin",
    "utils.subscription",
    "database.users",
    "stripe",
    "pinecone",
    "database.vector_db",
    "database.memories",
)


def install_consolidation_apply_stubs() -> list[str]:
    """Stubs for WS-O consolidation apply tests (real apply path, mocked side effects)."""
    touched: list[str] = []
    install_database_client_stub()
    install_firestore_transactional_stub()
    touched.extend(install_ws_i_heavy_import_stubs())

    review_queue_mod = AutoMockModule("database.review_queue")
    review_queue_mod.create_review_conflict = MagicMock()
    review_queue_mod.purge_stale_review_conflicts_for_memories = MagicMock()
    review_queue_mod.should_escalate_conflict = MagicMock(return_value=True)
    sys.modules["database.review_queue"] = review_queue_mod
    touched.append("database.review_queue")

    jobs_mod = AutoMockModule("jobs.short_term_lifecycle_worker")
    jobs_mod.fetch_short_term_memory_items_firestore = MagicMock(return_value=[])
    sys.modules["jobs.short_term_lifecycle_worker"] = jobs_mod
    touched.append("jobs.short_term_lifecycle_worker")

    return list(dict.fromkeys(touched))


CONSOLIDATION_APPLY_STUB_MODULE_NAMES = (
    "database._client",
    "database.review_queue",
    "jobs.short_term_lifecycle_worker",
    "utils.memory.canonical_consolidation",
)


def module_import_isolation(
    install_fn: Callable[[], Sequence[str]],
    extra_names: Sequence[str] = (),
):
    """Context manager factory for module-scoped autouse fixtures."""

    class _Isolation:
        def __enter__(self):
            names = list(dict.fromkeys(["database._client", *extra_names]))
            self._saved = snapshot_sys_modules(names)
            install_database_client_stub()
            touched = install_fn()
            self._saved.update(snapshot_sys_modules(touched))
            return self

        def __exit__(self, *exc):
            restore_sys_modules(self._saved)
            client_stub = self._saved.get("database._client")
            database_pkg = sys.modules.get("database")
            if (
                isinstance(database_pkg, ModuleType)
                and client_stub is not None
                and getattr(database_pkg, "_client", None) is not client_stub
            ):
                if self._saved.get("database._client") is None:
                    if getattr(database_pkg, "_client", None) is not None:
                        delattr(database_pkg, "_client")
                else:
                    setattr(database_pkg, "_client", self._saved["database._client"])

    return _Isolation()


def ensure_package_path(name: str, path: str) -> ModuleType:
    module = sys.modules.get(name)
    if not isinstance(module, ModuleType):
        module = ModuleType(name)
        sys.modules[name] = module
    module.__path__ = [path]
    if "." in name:
        parent_name, child_name = name.rsplit(".", 1)
        parent = sys.modules.setdefault(parent_name, ModuleType(parent_name))
        setattr(parent, child_name, module)
    return module


def install_mcp_search_memories_stubs(backend_dir: str) -> list[str]:
    touched: list[str] = []

    ensure_package_path("utils", os.path.join(backend_dir, "utils"))
    ensure_package_path("utils.retrieval", os.path.join(backend_dir, "utils", "retrieval"))
    ensure_package_path("models", os.path.join(backend_dir, "models"))

    drop_stale_module("utils.retrieval.hybrid", os.path.join(backend_dir, "utils", "retrieval", "hybrid.py"))
    drop_stale_module("models.memories", os.path.join(backend_dir, "models", "memories.py"))
    drop_stale_module("models.conversation_enums", os.path.join(backend_dir, "models", "conversation_enums.py"))
    drop_stale_module("models.mcp_api_key", os.path.join(backend_dir, "models", "mcp_api_key.py"))

    stub_names = [
        "database._client",
        "database.redis_db",
        "database.conversations",
        "database.memories",
        "database.action_items",
        "database.folders",
        "database.users",
        "database.user_usage",
        "database.vector_db",
        "database.chat",
        "database.apps",
        "database.goals",
        "database.notifications",
        "database.mem_db",
        "database.mcp_api_key",
        "database.daily_summaries",
        "database.fair_use",
        "database.auth",
        "database.dev_api_key",
        "firebase_admin",
        "firebase_admin.messaging",
        "firebase_admin.auth",
        "google.cloud.firestore",
        "google.cloud.firestore_v1",
        "google.cloud.firestore_v1.FieldFilter",
        "google",
        "google.cloud",
        "pinecone",
        "typesense",
        "opuslib",
        "pydub",
        "pusher",
        "modal",
        "utils.other.storage",
        "utils.other.endpoints",
        "utils.stt.pre_recorded",
        "utils.stt.vad",
        "utils.fair_use",
        "utils.subscription",
        "utils.conversations.process_conversation",
        "utils.conversations.render",
        "utils.notifications",
        "utils.apps",
        "utils.llm.memories",
        "utils.llm.chat",
        "utils.log_sanitizer",
        "utils.executors",
        "dependencies",
    ]
    for mod_name in stub_names:
        if mod_name not in sys.modules:
            sys.modules[mod_name] = AutoMockModule(mod_name)
            touched.append(mod_name)

    client = sys.modules["database._client"]
    if not isinstance(getattr(client, "document_id_from_seed", None), types.FunctionType):
        client.document_id_from_seed = lambda seed: "id-" + str(abs(hash(seed)) % (10**12))

    sys.modules["dependencies"].get_uid_from_mcp_api_key = MagicMock(return_value="user-1")
    sys.modules["dependencies"].get_current_user_id = MagicMock(return_value="user-1")
    sys.modules["utils.other.endpoints"].with_rate_limit = MagicMock(side_effect=lambda dependency, _policy: dependency)
    sys.modules["utils.other.endpoints"].check_rate_limit_inline = MagicMock()
    sys.modules["utils.apps"].update_personas_async = MagicMock()
    sys.modules["utils.executors"].db_executor = MagicMock()
    sys.modules["utils.executors"].postprocess_executor = MagicMock()
    sys.modules["utils.llm.memories"].identify_category_for_memory = MagicMock(return_value="other")
    sys.modules["firebase_admin.auth"].InvalidIdTokenError = type("InvalidIdTokenError", (Exception,), {})
    sys.modules["firebase_admin.auth"].ExpiredIdTokenError = type("ExpiredIdTokenError", (Exception,), {})
    sys.modules["firebase_admin.auth"].RevokedIdTokenError = type("RevokedIdTokenError", (Exception,), {})
    sys.modules["firebase_admin.auth"].CertificateFetchError = type("CertificateFetchError", (Exception,), {})
    sys.modules["firebase_admin.auth"].UserNotFoundError = type("UserNotFoundError", (Exception,), {})

    return touched


def ensure_test_import_packages_importable(backend_dir: str | None = None) -> None:
    """Restore real package paths when a prior test module left packages as bare stubs."""
    root = backend_dir or _BACKEND_DIR
    packages = (
        ("utils", "utils", True),
        ("utils.memory", os.path.join("utils", "memory"), True),
        ("models", "models", True),
        ("models.memories", os.path.join("models", "memories.py"), False),
    )
    for name, relative, is_package in packages:
        expected = os.path.join(root, relative)
        drop_stale_module(name, expected) if not is_package else None
        if is_package:
            module = sys.modules.get(name)
            if isinstance(module, ModuleType) and getattr(module, "__path__", None):
                continue
            if module is not None:
                sys.modules.pop(name, None)
                if "." in name:
                    parent_name, child_name = name.rsplit(".", 1)
                    parent = sys.modules.get(parent_name)
                    if isinstance(parent, ModuleType) and getattr(parent, child_name, None) is module:
                        delattr(parent, child_name)
            ensure_package_path(name, expected)


def ensure_utils_memory_packages_importable(backend_dir: str | None = None) -> None:
    """Backward-compatible alias for memory test modules."""
    ensure_test_import_packages_importable(backend_dir)


def install_memory_product_router_stubs(
    fastapi_stub: ModuleType,
    auth_stub: ModuleType,
) -> list[str]:
    sys.modules["fastapi"] = fastapi_stub
    sys.modules["database._client"] = MagicMock()
    vector_db_stub = types.ModuleType("database.vector_db")
    vector_db_stub.query_memory_vector_candidates = MagicMock(return_value=[])
    sys.modules["database.vector_db"] = vector_db_stub
    sys.modules["utils.other.endpoints"] = auth_stub
    database_pkg = sys.modules.get("database")
    if isinstance(database_pkg, ModuleType):
        setattr(database_pkg, "vector_db", vector_db_stub)
    return ["fastapi", "database._client", "database.vector_db", "utils.other.endpoints"]


_NON_ACTIVE_ROUTES_FIRESTORE_STUBBED = False


def install_firestore_transactional_stub():
    """Install a fake-transaction-compatible ``transactional`` on ``firestore_v1``.

    When the real ``google.cloud.firestore_v1`` is already imported, installs a wrapper
    module in ``sys.modules`` instead of mutating the real module attribute.
    Returns a restore callable when a wrapper was installed; otherwise ``None``.
    """
    try:
        import google.cloud.firestore_v1 as real_firestore_v1
    except ImportError:
        real_firestore_v1 = None

    is_real_module = real_firestore_v1 is not None and getattr(real_firestore_v1, "__file__", None) is not None

    def transactional(func):
        def wrapper(transaction, *args, **kwargs):
            if hasattr(transaction, "_begin"):
                transaction._begin()
            try:
                result = func(transaction, *args, **kwargs)
                if hasattr(transaction, "_commit"):
                    transaction._commit()
                return result
            except Exception:
                if hasattr(transaction, "_rollback"):
                    transaction._rollback()
                raise
            finally:
                if hasattr(transaction, "_clean_up"):
                    transaction._clean_up()

        return wrapper

    if is_real_module:
        prior_module = sys.modules.get("google.cloud.firestore_v1")
        wrapper_mod = types.ModuleType("google.cloud.firestore_v1")
        wrapper_mod.__dict__.update(real_firestore_v1.__dict__)
        wrapper_mod.transactional = transactional
        sys.modules["google.cloud.firestore_v1"] = wrapper_mod
        return lambda: sys.modules.__setitem__("google.cloud.firestore_v1", prior_module)

    google_stub = sys.modules.setdefault("google", types.ModuleType("google"))
    cloud_stub = sys.modules.setdefault("google.cloud", types.ModuleType("google.cloud"))
    firestore_v1_stub = sys.modules.setdefault(
        "google.cloud.firestore_v1", types.ModuleType("google.cloud.firestore_v1")
    )

    firestore_v1_stub.transactional = transactional
    google_stub.cloud = cloud_stub
    firestore_mod = sys.modules.setdefault("google.cloud.firestore", types.ModuleType("google.cloud.firestore"))
    cloud_stub.firestore = firestore_mod
    return None


def ensure_non_active_routes_firestore_transactional_stub() -> None:
    """Reload route-store module after binding fake-transaction-compatible decorator.

    L2/memory-tools tests set ``transactional = lambda func: func``, which breaks
    route-store unit fakes unless ``memory_non_active_routes`` is reloaded with a
    wrapper that commits fake transactions.
    """
    global _NON_ACTIVE_ROUTES_FIRESTORE_STUBBED
    if _NON_ACTIVE_ROUTES_FIRESTORE_STUBBED:
        return

    install_firestore_transactional_stub()

    import importlib

    import database.memory_non_active_routes as memory_non_active_routes

    importlib.reload(memory_non_active_routes)
    _NON_ACTIVE_ROUTES_FIRESTORE_STUBBED = True

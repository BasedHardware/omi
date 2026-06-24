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
        if original is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original


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


def install_v17_product_router_stubs(
    fastapi_stub: ModuleType,
    auth_stub: ModuleType,
) -> list[str]:
    sys.modules["fastapi"] = fastapi_stub
    sys.modules["database._client"] = MagicMock()
    sys.modules["utils.other.endpoints"] = auth_stub
    return ["fastapi", "database._client", "utils.other.endpoints"]

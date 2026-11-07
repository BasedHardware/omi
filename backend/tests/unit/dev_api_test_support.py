"""Isolate developer API tests without leaking stub modules or metric registrations."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Iterator
from unittest.mock import MagicMock

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parents[2]

# Import real collector owners once, outside the temporary fake-module context.
import database.firestore_read_metrics  # noqa: F401
import utils.metrics  # noqa: F401
import utils.observability.external_lists  # noqa: F401
import utils.product_metrics  # noqa: F401
import routers.developer_segments as _DEVELOPER_SEGMENTS_COLLECTOR_OWNER  # keep its Prometheus owner registered

_STUB_MODULES = (
    'ulid',
    'pinecone',
    'typesense',
    'opuslib',
    'pydub',
    'pusher',
    'modal',
    'database._client',
    'database.redis_db',
    'database.conversations',
    'database.memories',
    'database.action_items',
    'database.folders',
    'database.users',
    'database.user_usage',
    'database.vector_db',
    'database.chat',
    'database.apps',
    'database.goals',
    'database.notifications',
    'database.mem_db',
    'database.mcp_api_key',
    'database.daily_summaries',
    'database.fair_use',
    'database.auth',
    'database.knowledge_graph',
    'database.dev_api_key',
    'firebase_admin',
    'firebase_admin.messaging',
    'firebase_admin.auth',
    'firebase_admin.credentials',
    'firebase_admin.firestore',
    'google.cloud.firestore',
    'google.cloud.firestore_v1',
    'utils.other.endpoints',
    'utils.other.storage',
    'utils.external_list_reads',
    'utils.external_polling_cache',
    'utils.stt.pre_recorded',
    'utils.stt.vad',
    'utils.fair_use',
    'utils.subscription',
    'utils.conversations.process_conversation',
    'utils.conversations.location',
    'utils.conversations.lifecycle',
    'utils.notifications',
    'utils.apps',
    'utils.llm.memories',
    'utils.llm.chat',
    'utils.llm.knowledge_graph',
    'utils.memory.memory_service',
    'utils.memory.memory_system',
    'utils.executors',
    'services.conversation_frame_evidence',
    'testing.parity_pack_v0.live_capture',
)

class _RedisCacheMiss:
    """Minimal Redis adapter with an empty cache and no network connection."""

    def get(self, *_args, **_kwargs):
        return None

    def set(self, *_args, **_kwargs):
        return True

    def eval(self, *_args, **_kwargs):
        return 10


@contextmanager
def isolated_developer_api(monkeypatch) -> Iterator[SimpleNamespace]:
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-test-not-real')
    monkeypatch.setenv('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')
    stubs: dict[str, ModuleType | None] = {name: AutoMockModule(name) for name in _STUB_MODULES}
    stubs['routers.developer_segments'] = _DEVELOPER_SEGMENTS_COLLECTOR_OWNER
    stubs['utils.external_list_reads'] = None
    stubs['utils.external_polling_cache'] = None
    stubs['database._client'].document_id_from_seed = MagicMock(return_value='memory-id')
    stubs['database.redis_db'].create_bounded_redis_client = lambda *_args, **_kwargs: _RedisCacheMiss()
    stubs['database.vector_db'].upsert_memory_vectors_batch = MagicMock()
    stubs['utils.apps'].update_personas_async = MagicMock()
    auth = stubs['firebase_admin.auth']
    for name in (
        'InvalidIdTokenError',
        'ExpiredIdTokenError',
        'RevokedIdTokenError',
        'CertificateFetchError',
        'UserNotFoundError',
    ):
        setattr(auth, name, type(name, (Exception,), {}))
    stubs['utils.conversations.lifecycle'].ConversationLockedError = type(
        'ConversationLockedError', (Exception,), {}
    )
    endpoints = stubs['utils.other.endpoints']
    endpoints.get_current_user_uid = lambda: 'uid1'
    endpoints.with_rate_limit = lambda dependency, _policy: dependency
    endpoints.with_rate_limit_context = lambda dependency, _policy: dependency
    endpoints.check_api_key_rate_limit = MagicMock()
    endpoints.get_user = MagicMock()

    with stub_modules(stubs):
        import utils

        polling_cache = load_module_fresh(
            'utils.external_polling_cache',
            str(BACKEND_DIR / 'utils' / 'external_polling_cache.py'),
        )
        utils.external_polling_cache = polling_cache
        external_list_reads = load_module_fresh(
            'utils.external_list_reads', str(BACKEND_DIR / 'utils' / 'external_list_reads.py')
        )
        utils.external_list_reads = external_list_reads
        dependencies = load_module_fresh('dependencies', str(BACKEND_DIR / 'dependencies.py'))
        developer = load_module_fresh('routers.developer', str(BACKEND_DIR / 'routers' / 'developer.py'))
        import database.conversations as conversations_db

        yield SimpleNamespace(
            conversations_db=conversations_db,
            dependencies=dependencies,
            developer=developer,
        )

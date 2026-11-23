"""Isolate the conversation entry point for memory and speaker policy tests."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from database import _client as firestore_client
from tests.support.isolated_prometheus import isolated_prometheus
from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules

_PROCESS_CONVERSATION = Path(__file__).resolve().parents[2] / 'utils/conversations/process_conversation.py'

# These adapters either bring in provider wiring or would otherwise perform
# unrelated persistence when the tests exercise memory capture.
_ADAPTERS = (
    'database.auth',
    'database.users',
    'database.notifications',
    'database.redis_db',
    'database.vector_db',
    'utils.analytics',
    'utils.apps',
    'utils.conversations.calendar_linking',
    'utils.conversations.factory',
    'utils.executors',
    'utils.llm.chat',
    'utils.llm.clients',
    'utils.llm.conversation_processing',
    'utils.llm.external_integrations',
    'utils.llm.gateway_client',
    'utils.llm.goals',
    'utils.llm.memories',
    'utils.llm.usage_tracker',
    'utils.notifications',
    'utils.other.hume',
    'utils.other.storage',
    'utils.retrieval.rag',
    'utils.subscription',
    'utils.webhooks',
)


@pytest.fixture(scope="module")
def pc():
    fakes = {name: AutoMockModule(name) for name in _ADAPTERS}
    fakes['database.auth'].get_user_name = lambda uid, use_default=True: 'Test User'
    fakes['database.notifications'].get_user_time_zone = lambda uid: 'UTC'
    fakes['database.users'].get_user_language_preference = lambda uid: 'en'
    fakes['database.users'].get_data_protection_level = MagicMock(return_value='enhanced')
    fakes['database.vector_db'].find_similar_memories = MagicMock(return_value=[])
    fakes['utils.subscription'].should_defer_desktop_processing = lambda uid: False
    fakes['utils.subscription'].should_skip_omi_paid_postprocessing = lambda *args, **kwargs: False
    fakes['utils.subscription'].request_has_llm_byok_key = lambda: False

    with pytest.MonkeyPatch.context() as patch, isolated_prometheus(), stub_modules(fakes):
        client = MagicMock()
        patch.setattr(firestore_client, '_firestore_client', client)
        patch.setattr(firestore_client, '_customer_firestore_client', client)
        patch.setattr(firestore_client, '_data_plane_firestore_client', client)
        yield load_module_fresh('utils.conversations.process_conversation', str(_PROCESS_CONVERSATION))

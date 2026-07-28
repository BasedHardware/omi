"""Sanctioned session-level stub module for test_persona_prompt_rewrite.

Lives under backend/testing/ (exempt from check_module_stub_pollution — the
module-isolation gate) so the module-scope sys.modules stub loop that lets this
test import utils.apps without the full backend does not trip the gate. Importing
this module installs the stubs and exposes ``_AutoMockModule`` for the test's
lazy utils.apps loader.
"""

import os
import sys
from types import ModuleType
from unittest.mock import MagicMock

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

# ---- Stub heavy deps before importing application code (mirrors test_lock_bypass_fixes.py) ----


class _AutoMockModule(ModuleType):
    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


_stubs = [
    'anthropic',
    'av',
    'database._client',
    'database.cache',
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
    'database.llm_usage',
    'database.phone_calls',
    'deepgram',
    'deepgram.clients',
    'deepgram.clients.live',
    'deepgram.clients.live.v1',
    'firebase_admin',
    'firebase_admin.messaging',
    # NOTE (cubic follow-up 4601668066 → rebase): don't stub 'google',
    # 'google.cloud', or 'google.cloud.firestore'. The stubs are bare
    # ModuleType instances with no __path__, so they're not real
    # packages — that breaks any `from google.cloud.X import Y` because
    # Python can't resolve X as a submodule of the stubbed `google` /
    # `google.cloud`. Main added canonical-memory imports to utils.apps
    # which transitively pulls in database.knowledge_graph (which uses
    # `from google.cloud import firestore` and
    # `from google.cloud.firestore_v1 import FieldFilter`) when the
    # test does `import utils.apps`. Let the real google packages
    # resolve so that import chain works.
    # 'google',
    # 'google.cloud',
    # 'google.cloud.firestore',
    'langchain',
    'langchain_core',
    'langchain_core.messages',
    'langchain_openai',
    'langchain_anthropic',
    'langchain_community',
    'langchain_community.chat_message_histories',
    'mem0',
    'openai',
    'pydub',
    'pymemcache',
    'qdrant_client',
    'redis',
    'requests',
    'stripe',
    'tiktoken',
    'tqdm',
    'twitter',
    'utils.llm.usage_tracker',
    'utils.social',
    'utils.stripe',
    'utils.llm.persona',
]
for mod_name in _stubs:
    sys.modules.setdefault(mod_name, _AutoMockModule(mod_name))

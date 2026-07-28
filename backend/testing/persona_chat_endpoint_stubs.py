"""Sanctioned session-level stub module for test_persona_chat_endpoint.

Lives under backend/testing/ (exempt from check_module_stub_pollution — the
module-isolation gate) so the heavy module-scope sys.modules stubbing that lets
this test import utils.apps without the full backend dependency graph does not
trip the gate. Importing this module installs the stubs; do it before
`import utils.apps`.
"""

import os
import sys
import types
from datetime import datetime
from enum import Enum
from typing import Optional
from unittest.mock import MagicMock

from pydantic import BaseModel

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


# ---------------------------------------------------------------------------
# Stub heavy dependencies before importing the module under test.
# utils.apps pulls a long list of names from database.{redis_db,apps,auth,...};
# we give each stub module a MagicMock for every imported attribute so the
# import chain resolves.
# ---------------------------------------------------------------------------
def _full_stub(name, *attrs):
    mod = types.ModuleType(name)
    for a in attrs:
        setattr(mod, a, MagicMock())

    # Catch-all: any attribute lookup not explicitly set returns a MagicMock.
    # Handles long import lists in utils.apps without enumerating each name.
    def _getattr(_attr):
        return MagicMock()

    mod.__getattr__ = _getattr  # type: ignore[attr-defined]
    # Use setdefault so we don't clobber a real module already imported by
    # another test in the same pytest session. This matters when running
    # `pytest backend/tests/unit/` — the persona_chat test would otherwise
    # overwrite database.* stubs into sys.modules and break test collection
    # of unrelated tests (test_prompt_caching, test_users_webhook_url_validation,
    # etc. all fail with module-already-stubbed errors).
    sys.modules.setdefault(name, mod)
    return mod


_redis_attrs = (
    "delete_generic_cache",
    "get_enabled_apps",
    "get_app_reviews",
    "get_generic_cache",
    "set_generic_cache",
    "set_app_usage_history_cache",
    "get_app_usage_history_cache",
    "get_app_money_made_cache",
    "set_app_money_made_cache",
    "get_apps_installs_count",
    "get_apps_reviews",
    "get_app_cache_by_id",
    "set_app_cache_by_id",
    "get_app_money_made",
    "r",
)
_redis = _full_stub("database.redis_db", *_redis_attrs)
_redis.get_enabled_apps = MagicMock(return_value=[])

_apps_db_attrs = (
    "get_private_apps_db",
    "get_public_unapproved_apps_db",
    "get_public_approved_apps_db",
    "get_app_by_id_db",
    "get_app_usage_history_db",
    "set_app_review_in_db",
    "get_app_usage_count_db",
    "get_app_memory_created_integration_usage_count_db",
    "get_app_memory_prompt_usage_count_db",
    "add_tester_db",
    "add_app_access_for_tester_db",
    "remove_app_access_for_tester_db",
    "remove_tester_db",
    "is_tester_db",
    "can_tester_access_app_db",
    "get_apps_for_tester_db",
    "get_app_chat_message_sent_usage_count_db",
    "update_app_in_db",
    "get_audio_apps_count",
    "get_persona_by_uid_db",
    "update_persona_in_db",
    "get_omi_personas_by_uid_db",
    "get_api_key_by_hash_db",
    "get_popular_apps_db",
)
_apps_db = _full_stub("database.apps", *_apps_db_attrs)
_apps_db.get_app_by_id_db = MagicMock(return_value=None)

_full_stub(
    "database.auth",
    "get_user_name",
)
_full_stub("database.conversations", "get_conversations")
_full_stub("database.memories", "get_memories", "get_user_public_memories")
_full_stub("database.notifications")
_full_stub("database.action_items")
_full_stub("database.users")

# NOTE (cubic follow-up 4601668066 → rebase): do NOT stub
# google.cloud.firestore or google.cloud.firestore_v1. The stubs are
# bare ModuleType instances with no __path__, so they're not real
# packages — that breaks `from google.cloud.firestore_v1 import
# FieldFilter` because Python can't resolve firestore_v1 as a
# submodule of the stubbed `google.cloud`. Main added canonical-
# memory imports to utils.apps which transitively pulls in
# database.knowledge_graph (which uses `from google.cloud import
# firestore` and `from google.cloud.firestore_v1 import FieldFilter`)
# when the test does `import utils.apps`. Let the real firestore
# packages resolve so the import chain works.
# _full_stub("google.cloud.firestore")
# _full_stub("google.cloud.firestore_v1")

# NOTE: models.integrations is NOT stubbed — the real module loads so the
# test can exercise the real Pydantic PersonaChatRequest class.
# models.conversation needs real Pydantic models because FastAPI validates
# response_model at route registration time.
_conv_mod = types.ModuleType("models.conversation")


class _ExternalIntegrationCreateConversation(BaseModel):
    """Stub matching the real model's name only — we never hit this route."""

    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class _SearchRequest(BaseModel):
    """Stub matching the real model's name."""

    query: str = ""


class _ConversationSource(str, Enum):
    external_integration = "external_integration"


_conv_mod.ExternalIntegrationCreateConversation = _ExternalIntegrationCreateConversation
_conv_mod.SearchRequest = _SearchRequest
_conv_mod.ConversationSource = _ConversationSource
sys.modules["models.conversation"] = _conv_mod

_full_stub(
    "utils.other.endpoints",
    "check_rate_limit_inline",
    "get_current_user_uid",
)
_full_stub(
    "utils.executors",
    "run_blocking",
    "critical_executor",
    "db_executor",
    "postprocess_executor",
)

# NOTE (cubic follow-up 4601668066 → rebase): do NOT stub 'utils.llm'
# at the package level. The stub is a bare ModuleType with no real
# submodules, so anything that does `from utils.llm.X import Y` will
# get the stub instead of the real module. Main added canonical-
# memory imports to utils.apps which transitively pulls in
# database.knowledge_graph via utils.memory → database.vector_db →
# utils.llm.clients. If 'utils.llm' is stubbed, that chain breaks.
# Stub only the specific submodules we need to mock (the ones
# below) and let the real utils.llm package resolve for the rest.
# _full_stub("utils.llm")
_full_stub(
    "utils.llm.persona",
    "initial_persona_chat_message",
    "condense_conversations",
    "condense_memories",
    "generate_persona_description",
    "condense_tweets",
)
# utils.retrieval.hybrid is needed by utils.memory.canonical_memory_adapter
# (added by main's canonical-memory system). Stub it so the import
# chain from utils.apps → utils.memory → ... doesn't fail (the test
# never exercises the canonical memory path itself; it only needs
# the imports to succeed).
_full_stub("utils.retrieval.hybrid", "rrf_rerank")
_usage_tracker_stub = _full_stub(
    "utils.llm.usage_tracker",
    "track_usage",
    "Features",
)
# Provide a real BaseCallbackHandler for utils.llm.clients' module-level
# `_usage_callback = get_usage_callback()` so ChatOpenAI() can be
# constructed at import time without pydantic 2's strict is_instance_of
# check rejecting a MagicMock (PR #8682 post-rebase issue).
#
# Cubic review follow-up (PR #8682): the previous version used a
# try/except ImportError with a duck-typed fallback class
# (_NullCallback: bare object with __getattr__ returning no-op
# lambdas). pydantic v2's strict is_instance_of check rejects that
# because it doesn't inherit from BaseCallbackHandler. The fallback
# only ever activates when langchain_core is stubbed as a bare
# ModuleType by an earlier-collected test — which ALSO stubs
# langchain_openai, in which case ChatOpenAI is itself a MagicMock
# and pydantic validation is skipped anyway. So the fallback was
# both fragile AND dead code. Removed.
from langchain_core.callbacks import BaseCallbackHandler as _BaseCallbackHandler


class _NullCallback(_BaseCallbackHandler):
    """No-op callback that satisfies pydantic's BaseCallbackHandler check."""

    pass


_usage_tracker_stub.get_usage_callback = lambda: _NullCallback()
_full_stub("utils.app_integrations", "send_app_notification")
_full_stub("utils.conversations")
_full_stub("utils.conversations.process_conversation", "process_conversation", "retrieve_in_progress_conversation")
_full_stub("utils.conversations.location", "get_google_maps_location")
_full_stub("utils.conversations.render", "redact_conversation_for_integration", "conversations_to_string")
_full_stub("utils.conversations.memories", "process_external_integration_memory")
_full_stub("utils.conversations.search", "search_conversations")
_full_stub("utils.conversations.factory", "deserialize_conversations")
_full_stub("utils.social", "get_twitter_timeline")
_full_stub("utils.stripe")
_full_stub("database.cache", "get_memory_cache", "get_pubsub_manager")
# database.users needs get_stripe_connect_account_id
_users_mod = _full_stub("database.users", "get_user_name", "get_stripe_connect_account_id")
# models.app needs App, UsageHistoryItem, UsageHistoryType
# NOTE: models.app is NOT stubbed. The real App class is imported by
# routers.integration at module load (line 23), and the endpoint calls
# `App(**app_dict)` to coerce the Firestore dict to a Pydantic model.
# Stubbing models.app would mask the real class and break the streaming test.
_full_stub(
    "routers.conversations",
    "process_conversation",
    "trigger_external_integrations",
)

# utils.retrieval.graph (imported by integration.py transitively)
_full_stub("utils.retrieval", "graph")
sys.modules["utils.retrieval.graph"] = MagicMock(execute_chat_stream=MagicMock())
# T-022: utils.apps now also imports utils.retrieval.rag (memory RAG
# helper). Stub it so this test can import utils.apps without dragging
# in the full retrieval module.
_rag_stub = _full_stub("utils.retrieval.rag", "retrieve_relevant_memories_for_persona", "format_memories_for_prompt")

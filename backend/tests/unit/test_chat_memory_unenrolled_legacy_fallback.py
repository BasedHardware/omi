"""Omi chat serves legacy memories for un-enrolled accounts instead of hard-denying (#10736).

An account with no ``users/{uid}/memory_control/state`` document resolves to
``DENY_MEMORY`` / ``missing_rollout_state``. That is the expected state for the legacy
cohort, not a failure: ``pin_memory_system`` has already resolved the account to LEGACY,
so the legacy ``memories`` collection is its authoritative surface.

The Developer API (#10094) and hosted MCP (#9892) already treat that signal as
"un-enrolled, read legacy". The four chat retrieval entry points did not, so chat answered
"No memories available for this request." while the memories list screen showed the same
user's memories normally — it read as the assistant forgetting, not as an error.

Both branches are asserted per surface, because the risk in relaxing a fail-closed check is
relaxing it too far: an un-enrolled deny must reach legacy, and every other deny reason must
still refuse to read it.
"""

import os
from datetime import datetime, timezone

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-not-real")

import utils.retrieval.tool_services.memories as memories_svc  # noqa: E402
import utils.retrieval.tools.memory_tools as memory_tools  # noqa: E402
from utils.memory.chat_memory_adapter import ChatMemorySearchResult  # noqa: E402
from utils.memory.default_read_rollout import MemoryReadDecision  # noqa: E402
from utils.memory.memory_system import MemorySystem  # noqa: E402

UID = 'test-uid'
QUERY = 'espresso'
LEGACY_CONTENT = 'User has always been on the legacy memories collection.'
DENY_TEXT = 'No memories available for this request.'

# The un-enrolled signal that must now reach legacy.
UNENROLLED_REASON = 'missing_rollout_state'
# A deny that means "we could not establish this account's state" and must stay fail-closed.
# Chat's grant denial is the chat-consumer reason; there is no app-key gate on this path.
NON_RECOVERABLE_REASON = 'missing_chat_default_memory_grant'

_TOOL_CONFIG = {"configurable": {"user_id": UID}}


def _legacy_row():
    now = datetime(2026, 7, 27, 12, 0, 0, tzinfo=timezone.utc)
    return {
        'id': 'legacy-1',
        'uid': UID,
        'content': LEGACY_CONTENT,
        'created_at': now,
        'updated_at': now,
    }


def _denied(reason):
    """A decision carrying no text, so a hard deny surfaces the generic refusal string."""
    return ChatMemorySearchResult(text=None, read_decision=MemoryReadDecision.DENY_MEMORY, fallback_reason=reason)


def _stub_common(monkeypatch, module, reason, decision_attr):
    """Pin the account to LEGACY and force the given default-read denial."""
    monkeypatch.setattr(module, 'pin_memory_system', lambda *a, **k: MemorySystem.LEGACY)
    monkeypatch.setattr(module, decision_attr, lambda **kwargs: _denied(reason))
    monkeypatch.setattr(module.notification_db, 'get_user_time_zone', lambda uid: None)


def _stub_legacy_list(monkeypatch, module, reads):
    def _get_memories(uid, limit=50, offset=0, start_date=None, end_date=None):
        reads.append(uid)
        return [_legacy_row()]

    monkeypatch.setattr(module.memory_db, 'get_memories', _get_memories)


def _stub_legacy_vector(monkeypatch, module, reads):
    def _find_similar(uid, query, threshold=0.0, limit=5):
        reads.append(uid)
        return [{'memory_id': 'legacy-1', 'score': 0.91}]

    monkeypatch.setattr(module.vector_db, 'find_similar_memories', _find_similar)
    monkeypatch.setattr(module.memory_db, 'get_memories_by_ids', lambda uid, ids: [_legacy_row()])


def _run_service_list(monkeypatch, reason):
    reads = []
    _stub_common(monkeypatch, memories_svc, reason, 'list_default_chat_memories_decision_text')
    _stub_legacy_list(monkeypatch, memories_svc, reads)
    return memories_svc.get_memories_text(uid=UID), reads


def _run_service_search(monkeypatch, reason):
    reads = []
    _stub_common(monkeypatch, memories_svc, reason, 'search_memory_default_chat_memories_vector_decision_text')
    _stub_legacy_vector(monkeypatch, memories_svc, reads)
    return memories_svc.search_memories_text(uid=UID, query=QUERY), reads


def _run_tool_list(monkeypatch, reason):
    reads = []
    _stub_common(monkeypatch, memory_tools, reason, 'list_default_chat_memories_decision_text')
    _stub_legacy_list(monkeypatch, memory_tools, reads)
    return memory_tools.get_memories_tool.func(config=_TOOL_CONFIG), reads


def _run_tool_search(monkeypatch, reason):
    reads = []
    _stub_common(monkeypatch, memory_tools, reason, 'search_memory_default_chat_memories_vector_decision_text')
    _stub_legacy_vector(monkeypatch, memory_tools, reads)
    return memory_tools.search_memories_tool.func(query=QUERY, config=_TOOL_CONFIG), reads


# All four chat entry points that consult the default-read decision: the LangChain tools used
# by mobile chat, and the shared services behind /v1/tools/* for desktop, web, and agents.
CHAT_SURFACES = [
    pytest.param(_run_service_list, id='service_list'),
    pytest.param(_run_service_search, id='service_vector_search'),
    pytest.param(_run_tool_list, id='tool_list'),
    pytest.param(_run_tool_search, id='tool_vector_search'),
]


@pytest.mark.parametrize('run_surface', CHAT_SURFACES)
def test_unenrolled_account_reads_legacy_memories_instead_of_refusing(monkeypatch, run_surface):
    output, legacy_reads = run_surface(monkeypatch, UNENROLLED_REASON)

    assert legacy_reads == [UID], 'un-enrolled deny must reach the legacy memories read'
    assert LEGACY_CONTENT in output
    assert DENY_TEXT not in output


@pytest.mark.parametrize('run_surface', CHAT_SURFACES)
def test_other_deny_reasons_still_refuse_without_reading_legacy(monkeypatch, run_surface):
    output, legacy_reads = run_surface(monkeypatch, NON_RECOVERABLE_REASON)

    assert legacy_reads == [], 'a non-un-enrolled deny must not read legacy memories'
    assert output == DENY_TEXT
    assert LEGACY_CONTENT not in output

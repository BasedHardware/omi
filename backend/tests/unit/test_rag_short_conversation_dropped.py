"""Regression test for rag.get_better_conversation_chunk dropping short conversations.

Bug: for conversations under 250 tokens the function `return`ed the rendered
string, but the caller (retrieve_rag_conversation_context) ignores the futures'
return values and only consumes `context_data.values()`. So short conversations
were silently dropped from the assembled RAG context. The fix writes the rendered
chunk into `context_data[memory.id]` (the path the caller reads) instead of
returning it.

Test strategy: import the real `utils.retrieval.rag` module via the meta-path
stub-finder (so its heavy database/utils imports resolve to stubs), then patch the
module-level helpers it calls so we can drive `get_better_conversation_chunk`
directly with a short conversation and assert the chunk ends up in `context_data`.
"""

import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")
os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

_STUB = (
    "database",
    "utils",
    "firebase_admin",
    "google",
    "pinecone",
    "opuslib",
    "pydub",
    "redis",
    "langchain",
    "langchain_core",
    "stripe",
    "openai",
    "anthropic",
    "modal",
    "ulid",
    "sentry_sdk",
    "requests",
    "typesense",
    "pusher",
    "httpx",
)


# The module under test (and the parent packages the import machinery must
# descend through to reach it) must stay REAL even though they fall under the
# `utils` stub prefix. Everything else under `utils.*` / `database.*` is stubbed.
_REAL = ("utils", "utils.retrieval", "utils.retrieval.rag")


def _is(n):
    if n in _REAL:
        return False
    return any(n == p or n.startswith(p + ".") for p in _STUB)


class _AM(types.ModuleType):
    __path__ = []

    def __getattr__(s, n):
        if n.startswith("__") and n.endswith("__"):
            raise AttributeError(n)
        m = MagicMock()
        setattr(s, n, m)
        return m


class _F(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(s, n, p=None, t=None):
        return importlib.machinery.ModuleSpec(n, s, is_package=True) if _is(n) else None

    def create_module(s, sp):
        return _AM(sp.name)

    def exec_module(s, m):
        pass


_f = _F()
_sav = {n: m for n, m in sys.modules.items() if _is(n)}
for n in list(sys.modules):
    if _is(n):
        sys.modules.pop(n, None)
sys.meta_path.insert(0, _f)
try:
    from utils.retrieval import rag as mod
finally:
    sys.meta_path.remove(_f)
    for n in list(sys.modules):
        if _is(n) and n not in _sav:
            sys.modules.pop(n, None)
    sys.modules.update(_sav)


class _FakeMemory:
    def __init__(self, mem_id):
        self.id = mem_id
        self.transcript_segments = []


def test_short_conversation_written_into_context_data():
    """A short (<250 token) conversation must land in context_data, not be dropped."""
    memory = _FakeMemory("mem-short-1")
    context_data = {}
    rendered = "SHORT CONVERSATION RENDERED TEXT"

    with patch.object(mod.TranscriptSegment, "segments_as_string", return_value="hi there"), patch.object(
        mod, "num_tokens_from_string", return_value=10
    ), patch.object(mod, "conversations_to_string", return_value=rendered), patch.object(
        mod, "chunk_extraction"
    ) as chunk_extraction_mock:
        result = mod.get_better_conversation_chunk(memory, ["topic"], context_data)

    # The short-conversation path must NOT call chunk_extraction.
    chunk_extraction_mock.assert_not_called()
    # The function follows the same contract as the long branch: mutate, return None.
    assert result is None
    # The rendered chunk must be in the dict the caller actually consumes.
    assert context_data.get(memory.id) == rendered
    # And it must be visible via .values() (exactly how the caller assembles context).
    assert rendered in list(context_data.values())


def test_long_conversation_still_written_into_context_data():
    """Sanity: the long-conversation path already writes into context_data (unchanged)."""
    memory = _FakeMemory("mem-long-1")
    context_data = {}

    with patch.object(mod.TranscriptSegment, "segments_as_string", return_value="long convo"), patch.object(
        mod, "num_tokens_from_string", return_value=5000
    ), patch.object(mod, "conversations_to_string", return_value="should-not-be-used"), patch.object(
        mod, "chunk_extraction", return_value="EXTRACTED CHUNK CONTENT"
    ):
        result = mod.get_better_conversation_chunk(memory, ["topic"], context_data)

    assert result is None
    assert context_data.get(memory.id) == "EXTRACTED CHUNK CONTENT"

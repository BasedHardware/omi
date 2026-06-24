"""
Regression test for retrieve_metadata_fields_from_transcript in utils/llm/chat.py.

Bug: the 'entities' list was built from result.topics instead of result.entities,
so the returned entities mirrored the topics and the real entities were dropped.
This drives the function with a fake LLM result whose .topics and .entities are
distinct and asserts the returned 'entities' come from result.entities.

Red (without the fix): metadata['entities'] equals the topics.
Green (with the fix): metadata['entities'] equals the entities.
"""

import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

# Stub heavy packages so importing utils.llm.chat does not require external services.
# pydantic / fastapi are intentionally NOT stubbed (chat.py defines a real pydantic model).
_STUB = (
    'database',
    'firebase_admin',
    'google',
    'pinecone',
    'opuslib',
    'pydub',
    'redis',
    'langchain',
    'langchain_core',
    'langchain_openai',
    'stripe',
    'openai',
    'anthropic',
    'modal',
    'ulid',
    'sentry_sdk',
    'requests',
    'typesense',
    'pusher',
    'httpx',
    'cachetools',
    'tiktoken',
    'utils.llms',
    'utils.llm.clients',
    'utils.llm.usage_tracker',
)


def _is(n):
    return any(n == p or n.startswith(p + '.') for p in _STUB)


class _AM(types.ModuleType):
    __path__ = []

    def __getattr__(s, n):
        if n.startswith('__') and n.endswith('__'):
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
    from utils.llm import chat as mod
finally:
    sys.meta_path.remove(_f)
    for n in list(sys.modules):
        if _is(n) and n not in _sav:
            sys.modules.pop(n, None)
    sys.modules.update(_sav)


class _FakeResult:
    """Stand-in for the ExtractedInformation returned by the structured LLM call."""

    def __init__(self):
        self.people = ['Alice']
        self.topics = ['machinelearning']  # already normalized-friendly, no special chars
        self.entities = ['openai']  # distinct from topics on purpose
        self.dates = []


def _drive():
    fake_result = _FakeResult()

    fake_llm = MagicMock()
    fake_llm.with_structured_output.return_value.invoke.return_value = fake_result

    @contextmanager
    def _noop_ctx(*args, **kwargs):
        yield MagicMock()

    with patch.object(mod, 'get_llm', return_value=fake_llm), patch.object(mod, 'track_usage', _noop_ctx), patch.object(
        mod, 'add_filter_category_item'
    ):
        metadata = mod.retrieve_metadata_fields_from_transcript(
            uid='test_uid',
            created_at=__import__('datetime').datetime(2025, 6, 1, tzinfo=__import__('datetime').timezone.utc),
            transcript_segment=[{'text': 'hello world'}],
            tz='UTC',
        )
    return metadata


def test_entities_come_from_result_entities_not_topics():
    metadata = _drive()
    # With the bug, entities mirror topics -> ['machinelearning'].
    # With the fix, entities come from result.entities -> ['openai'].
    assert metadata['entities'] == ['openai'], f"entities should come from result.entities, got {metadata['entities']}"
    # And entities must NOT equal the topics list (the symptom of the bug).
    assert metadata['entities'] != metadata['topics'], "entities should not mirror topics"
    # Sanity: topics still come from result.topics.
    assert metadata['topics'] == ['machinelearning']

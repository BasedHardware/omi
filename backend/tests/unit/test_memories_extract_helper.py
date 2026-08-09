"""Pure memory-log extract helper is return-only through get_llm('memories')."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from utils.llm import memories as memories_llm


def test_extract_memory_log_from_text_empty_returns_empty():
    assert memories_llm.extract_memory_log_from_text('uid', '   ') == memories_llm.MemoryLogExtraction(
        memories=[], profile=''
    )


def test_extract_memory_log_from_text_parses_llm_json(monkeypatch):
    class FakeLLM:
        def invoke(self, prompt):
            assert 'chatgpt' in prompt
            assert 'Lives in NYC' in prompt
            return SimpleNamespace(content='{"memories": ["Likes coffee", ""], "profile": "Coffee person."}')

    @contextmanager
    def fake_track_usage(*_args, **_kwargs):
        yield

    monkeypatch.setattr(memories_llm, 'get_llm', lambda feature: FakeLLM())
    monkeypatch.setattr(memories_llm, 'track_usage', fake_track_usage)

    result = memories_llm.extract_memory_log_from_text(
        'uid',
        'I like coffee a lot',
        text_source='chatgpt',
        existing_memories=['Lives in NYC'],
    )
    assert result is not None
    assert result.memories == ['Likes coffee']
    assert result.profile == 'Coffee person.'

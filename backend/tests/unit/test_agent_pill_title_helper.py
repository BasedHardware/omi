"""Pure AgentPill title helper is return-only through get_llm('session_titles')."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from utils.llm import agent_pill_title as agent_pill_title_llm


def test_generate_agent_pill_title_ack_empty_returns_empty():
    assert agent_pill_title_llm.generate_agent_pill_title_ack('uid', '   ') == agent_pill_title_llm.AgentPillTitleAck(
        title='', ack=''
    )


def test_generate_agent_pill_title_ack_parses_llm_json(monkeypatch):
    captured: dict[str, object] = {}

    class FakeLLM:
        def invoke(self, prompt):
            assert 'build a mario level' in prompt
            return SimpleNamespace(content='{"title": "Build Mario Level", "ack": "Got it, on it."}')

    @contextmanager
    def fake_track_usage(*_args, **_kwargs):
        yield

    def fake_get_llm(feature, **kwargs):
        captured['feature'] = feature
        captured['kwargs'] = kwargs
        return FakeLLM()

    monkeypatch.setattr(agent_pill_title_llm, 'get_llm', fake_get_llm)
    monkeypatch.setattr(agent_pill_title_llm, 'track_usage', fake_track_usage)

    result = agent_pill_title_llm.generate_agent_pill_title_ack('uid', 'build a mario level')
    assert result is not None
    assert result.title == 'Build Mario Level'
    assert result.ack == 'Got it, on it.'
    assert captured == {
        'feature': 'session_titles',
        'kwargs': {'request_timeout': 8.0, 'max_tokens': 120},
    }


def test_generate_agent_pill_title_ack_normalizes_and_caps_ack_words(monkeypatch):
    class FakeLLM:
        def invoke(self, _prompt):
            return SimpleNamespace(
                content='{"title": "Build Mario Level", "ack": "  Got   it,   I am building this level for you now!  "}'
            )

    @contextmanager
    def fake_track_usage(*_args, **_kwargs):
        yield

    monkeypatch.setattr(agent_pill_title_llm, 'get_llm', lambda *_args, **_kwargs: FakeLLM())
    monkeypatch.setattr(agent_pill_title_llm, 'track_usage', fake_track_usage)

    result = agent_pill_title_llm.generate_agent_pill_title_ack('uid', 'build a mario level')

    assert result is not None
    assert result.ack == 'Got it, I am building this level'

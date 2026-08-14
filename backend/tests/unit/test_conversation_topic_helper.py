"""Conversation topic helper is return-only through get_llm('conv_structure')."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from utils.llm import conversation_topic


@contextmanager
def _fake_track_usage(*_args, **_kwargs):
    yield


def _patch(monkeypatch, content: str, capture: dict | None = None):
    class FakeLLM:
        def invoke(self, prompt):
            if capture is not None:
                capture['prompt'] = prompt
            return SimpleNamespace(content=content)

    features: dict[str, str] = {}

    def fake_get_llm(feature):
        features['feature'] = feature
        return FakeLLM()

    monkeypatch.setattr(conversation_topic, 'get_llm', fake_get_llm)
    monkeypatch.setattr(conversation_topic, 'track_usage', _fake_track_usage)
    return features


def test_empty_transcript_returns_empty_topic():
    assert conversation_topic.generate_conversation_topic('uid', '  ') == conversation_topic.ConversationTopic(
        emoji='', title=''
    )


def test_parses_topic_and_truncates_transcript(monkeypatch):
    capture: dict = {}
    features = _patch(monkeypatch, '{"emoji": " 🎧 ", "title": " Weekly standup "}', capture)

    result = conversation_topic.generate_conversation_topic('uid', 'a' * 10_000)

    assert result is not None
    assert result.emoji == '🎧'
    assert result.title == 'Weekly standup'
    assert features['feature'] == 'conv_structure'
    assert 'a' * conversation_topic.MAX_TRANSCRIPT_CHARS in capture['prompt']
    assert 'a' * (conversation_topic.MAX_TRANSCRIPT_CHARS + 1) not in capture['prompt']


def test_unparseable_response_returns_none(monkeypatch):
    _patch(monkeypatch, 'no json here')
    assert conversation_topic.generate_conversation_topic('uid', 'some transcript') is None

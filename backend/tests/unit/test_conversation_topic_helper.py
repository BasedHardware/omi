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


def test_short_transcript_answers_deterministically_without_a_model(monkeypatch):
    def fail_get_llm(_feature):
        raise AssertionError('a short transcript must not reach the model')

    monkeypatch.setattr(conversation_topic, 'get_llm', fail_get_llm)

    before = _deterministic_short_answers()

    result = conversation_topic.generate_conversation_topic('uid', 'Call mom tomorrow')

    assert result == conversation_topic.ConversationTopic(emoji='', title='Call mom tomorrow')
    assert _deterministic_short_answers() == before + 1


def test_short_transcript_still_calls_model_when_switch_is_off(monkeypatch):
    capture: dict = {}
    _patch(monkeypatch, '{"emoji": "📞", "title": "Mom call"}', capture)
    monkeypatch.setenv('CONVERSATION_TOPIC_DETERMINISTIC_SHORT_ENABLED', 'false')

    result = conversation_topic.generate_conversation_topic('uid', 'Call mom tomorrow')

    assert result is not None
    assert result.emoji == '📞'
    assert 'Call mom tomorrow' in capture['prompt']


def _deterministic_short_answers() -> float:
    from prometheus_client import REGISTRY

    return REGISTRY.get_sample_value('conversation_topic_deterministic_total', {'reason': 'short_transcript'}) or 0.0


def test_parses_topic_and_truncates_transcript(monkeypatch):
    capture: dict = {}
    features = _patch(monkeypatch, '{"emoji": " 🎧 ", "title": " Weekly standup "}', capture)

    # Enough words to clear the deterministic short-transcript floor, ending in
    # one unbroken block that exercises the character truncation below.
    transcript = 'more filler words to clear the deterministic short transcript word floor. ' + 'a' * 10_000
    result = conversation_topic.generate_conversation_topic('uid', transcript)

    assert result is not None
    assert result.emoji == '🎧'
    assert result.title == 'Weekly standup'
    assert features['feature'] == 'conv_structure'
    assert 'a' * 3_000 in capture['prompt']
    assert 'a' * 5_000 not in capture['prompt']


def test_unparseable_response_returns_none(monkeypatch):
    _patch(monkeypatch, 'no json here')
    transcript = 'some transcript that is long enough to clear the deterministic word floor'
    assert conversation_topic.generate_conversation_topic('uid', transcript) is None

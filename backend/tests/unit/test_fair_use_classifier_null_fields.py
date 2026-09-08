"""Regression test: a null field in the classifier response must not disable abuse detection.

utils.llm.fair_use_classifier.classify_user_purpose parses the LLM's JSON, then validated fields
with result.get(k, default). get's default only applies to an ABSENT key, so a present-but-null
field (misuse_score / confidence / evidence: null) slipped through and raised (float(None),
None[:10]). The broad except then swallowed it and returned default_result (misuse_score 0.0 =
"not abuse"), silently disabling abuse detection for that run. Null fields now coerce to defaults.
"""

import asyncio

import utils.llm.fair_use_classifier as fuc


class _FakeResp:
    def __init__(self, content):
        self.content = content


class _FakeLLM:
    def __init__(self, content):
        self._content = content

    async def ainvoke(self, messages):
        return _FakeResp(self._content)


def _run(monkeypatch, content):
    monkeypatch.setattr(fuc, '_prepare_conversation_summaries', lambda uid: [{'duration_minutes': 5}])
    monkeypatch.setattr(fuc, '_classifier_llm', _FakeLLM(content))
    return asyncio.run(fuc.classify_user_purpose('u1'))


def test_null_evidence_does_not_swallow_the_score(monkeypatch):
    result = _run(
        monkeypatch,
        '{"misuse_score": 0.9, "confidence": 0.8, "evidence": null, "usage_type": "commercial"}',
    )
    assert result['misuse_score'] == 0.9  # not swallowed to the 0.0 default
    assert result['evidence'] == []
    assert result['usage_type'] == 'commercial'


def test_null_score_coerces_and_keeps_parsed_result(monkeypatch):
    result = _run(
        monkeypatch,
        '{"misuse_score": null, "confidence": null, "evidence": ["a"], "usage_type": "none"}',
    )
    assert result['misuse_score'] == 0.0  # coerced from null, not crashed to default
    assert result['evidence'] == ["a"]  # proves the parsed result was kept (default evidence is [])

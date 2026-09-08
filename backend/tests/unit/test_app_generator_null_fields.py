"""Regression test: null LLM fields must not 500 app generation.

utils.llm.app_generator.generate_app_from_prompt constructs GeneratedAppData from the LLM's
parsed JSON, OUTSIDE the JSON-parse try/except. It used app_data.get(k, default), whose default
only applies to an ABSENT key. A present-but-null field slipped through and then crashed:
None[:50] (name), "chat" in None (capabilities), or GeneratedAppData validation for the required
str fields description/category. Null fields now coerce to their defaults.
"""

import asyncio

import utils.llm.app_generator as ag


class _FakeResp:
    def __init__(self, content):
        self.content = content


class _FakeLLM:
    def __init__(self, content):
        self._content = content

    async def ainvoke(self, messages):
        return _FakeResp(self._content)


def _patch_llm(monkeypatch, content):
    monkeypatch.setattr(ag, 'get_llm', lambda *a, **k: _FakeLLM(content))


def test_null_llm_fields_fall_back_to_defaults(monkeypatch):
    _patch_llm(monkeypatch, '{"name": null, "description": null, "category": null, "capabilities": null}')

    result = asyncio.run(ag.generate_app_from_prompt("make me an app"))

    assert result.name == "My App"
    assert result.description == "An AI-powered app"
    assert result.category == "other"
    assert result.capabilities == ["chat"]


def test_valid_llm_fields_are_used(monkeypatch):
    content = (
        '{"name": "My Bot", "description": "d", "category": "productivity", '
        '"capabilities": ["chat"], "chat_prompt": "be helpful"}'
    )
    _patch_llm(monkeypatch, content)

    result = asyncio.run(ag.generate_app_from_prompt("x"))

    assert result.name == "My Bot"
    assert result.capabilities == ["chat"]
    assert result.chat_prompt == "be helpful"

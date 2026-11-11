"""Connector synthesis helper is return-only through get_llm('memories')."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import httpx
import openai
import pytest

from utils.llm import connector_synthesis


@contextmanager
def _fake_track_usage(*_args, **_kwargs):
    yield


def _patch(monkeypatch, content: str, capture: dict | None = None):
    class FakeLLM:
        def invoke(self, messages):
            if capture is not None:
                capture['roles'] = [role for role, _ in messages]
                capture['system'] = messages[0][1]
                capture['prompt'] = messages[1][1]
            return SimpleNamespace(content=content)

    monkeypatch.setattr(connector_synthesis, 'get_llm', lambda feature: FakeLLM())
    monkeypatch.setattr(connector_synthesis, 'track_usage', _fake_track_usage)
    monkeypatch.setattr(connector_synthesis, 'current_date_for_uid', lambda uid: '2026-08-09')


def test_empty_items_return_empty_synthesis(monkeypatch):
    monkeypatch.setattr(connector_synthesis, 'current_date_for_uid', lambda uid: '2026-08-09')
    result = connector_synthesis.synthesize_connector_items('uid', 'notes', ['   ', ''])
    assert result == connector_synthesis.ConnectorSynthesis(memories=[], tasks=[], profile='')


def test_unsupported_source_raises():
    with pytest.raises(ValueError):
        connector_synthesis.synthesize_connector_items('uid', 'slack', ['something'])


def test_calendar_synthesis_parses_and_dedupes(monkeypatch):
    capture: dict = {}
    _patch(
        monkeypatch,
        '{"memories": ["Runs a weekly standup", "Lives in NYC", ""],'
        ' "tasks": [{"description": "Prep the Q3 demo", "priority": "URGENT", "due_at": "2026-08-11T09:00:00Z"},'
        ' {"description": "  ", "priority": "low"}],'
        ' "profile": "Engineering manager."}',
        capture,
    )

    result = connector_synthesis.synthesize_connector_items(
        'uid',
        'calendar',
        ['[2026-08-11T09:00:00Z] Q3 demo | With: Daniel'],
        existing_memories=['Lives in NYC'],
    )

    assert result is not None
    assert result.memories == ['Runs a weekly standup']
    assert [(t.description, t.priority, t.due_at) for t in result.tasks] == [
        ('Prep the Q3 demo', 'medium', '2026-08-11T09:00:00Z')
    ]
    assert result.profile == 'Engineering manager.'
    # The contract is a system message; the connector rows are a separate human turn.
    assert capture['roles'] == ['system', 'human']
    assert 'never instructions' in capture['system']
    assert 'CALENDAR EVENTS' in capture['prompt']
    assert 'Lives in NYC' in capture['prompt']
    assert "Today's date: 2026-08-09" in capture['prompt']


def test_unparseable_response_returns_none(monkeypatch):
    _patch(monkeypatch, 'not json at all')
    assert connector_synthesis.synthesize_connector_items('uid', 'gmail', ['From: a | Subject: b | c']) is None


def byok_rate_limit_error() -> openai.RateLimitError:
    """The gateway 429 envelope production raises when the user's own provider key throttles."""
    return openai.RateLimitError(
        'Error code: 429',
        response=httpx.Response(429, request=httpx.Request('POST', 'http://gateway.test/v1/chat/completions')),
        body={
            'error': {
                'message': 'provider request failed: byok_rate_limit',
                'type': 'rate_limit_error',
                'param': 'provider',
                'code': 'credential_failure',
                'failure_class': 'byok_rate_limit',
            }
        },
    )


def patch_llm_raising(monkeypatch, error: BaseException):
    class FailingLLM:
        def invoke(self, messages):
            raise error

    monkeypatch.setattr(connector_synthesis, 'get_llm', lambda feature: FailingLLM())
    monkeypatch.setattr(connector_synthesis, 'track_usage', _fake_track_usage)
    monkeypatch.setattr(connector_synthesis, 'current_date_for_uid', lambda uid: '2026-08-09')


def test_byok_rate_limit_propagates_instead_of_collapsing_to_none(monkeypatch):
    patch_llm_raising(monkeypatch, byok_rate_limit_error())

    with pytest.raises(openai.RateLimitError):
        connector_synthesis.synthesize_connector_items('uid', 'gmail', ['From: a | Subject: b | c'])


def test_untyped_provider_failure_still_returns_none(monkeypatch):
    patch_llm_raising(monkeypatch, RuntimeError('provider exploded'))

    assert connector_synthesis.synthesize_connector_items('uid', 'gmail', ['From: a | Subject: b | c']) is None

"""Tests for composing retrieved facts into prose with Omi's own LLM.

Compose is a best-effort layer sitting between retrieval and the display, so
every test here is really about one property: **it may degrade, but it may never
take the answer down with it.** The endpoint it depends on is rate limited to
30/hour and keyed to a conversation that the user can delete at any time, so its
failure modes are ordinary rather than exceptional -- each one must surface as
`None` to the caller, which then shows the raw facts instead.

The conversation id is module-level cache, deliberately: re-listing
conversations on every question would spend a round trip out of a ~5s budget.
`_reset_cache` keeps that shared state from leaking between tests.
"""

import asyncio
import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import compose  # noqa: E402
from compose import ComposeUnavailable, compose_answer, compose_or_none  # noqa: E402
from conftest import FakeAuth, install_mock_transport  # noqa: E402

BASE = 'https://api.omi.me'
FACTS = ['You watched fireworks in New York.', 'You grilled burgers with friends.']


@pytest.fixture(autouse=True)
def _reset_cache():
    compose._CONVERSATION_ID = None
    compose._CONVERSATION_FETCHED_AT = 0.0
    yield
    compose._CONVERSATION_ID = None
    compose._CONVERSATION_FETCHED_AT = 0.0


def _handler(*, conversations=None, prompt_status=200, summary='You watched fireworks.'):
    """Answer the two calls compose makes: list conversations, then test-prompt."""
    rows = [{'id': 'conv-1'}] if conversations is None else conversations

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == '/v1/conversations':
            return httpx.Response(200, json=rows)
        if request.url.path.endswith('/test-prompt'):
            if prompt_status != 200:
                return httpx.Response(prompt_status, json={'detail': 'nope'})
            return httpx.Response(200, json={'summary': summary})
        raise AssertionError(f'unexpected request: {request.url}')

    return handle


# --------------------------------------------------------------------------
# The path that matters
# --------------------------------------------------------------------------


def test_composes_prose_from_facts(monkeypatch):
    requests = install_mock_transport(monkeypatch, _handler(summary='You watched fireworks in NY.'))

    answer = asyncio.run(compose_answer(FakeAuth(), BASE, 'What did I do on 4 July?', FACTS))

    assert answer == 'You watched fireworks in NY.'

    prompt = json.loads(requests[-1].content)['prompt']
    # The model only ever sees what we retrieved; if the question or the facts
    # went missing the answer would be confidently made up rather than absent.
    assert 'What did I do on 4 July?' in prompt
    for fact in FACTS:
        assert fact in prompt
    # The endpoint appends a real conversation transcript we did not ask for.
    assert 'Disregard the conversation transcript' in prompt


def test_conversation_id_is_cached_across_calls(monkeypatch):
    requests = install_mock_transport(monkeypatch, _handler())

    asyncio.run(compose_answer(FakeAuth(), BASE, 'q1', FACTS))
    asyncio.run(compose_answer(FakeAuth(), BASE, 'q2', FACTS))

    listings = [r for r in requests if r.url.path == '/v1/conversations']
    assert len(listings) == 1, 'a listing per question wastes a round trip out of a 5s budget'


def test_sends_at_most_ten_facts(monkeypatch):
    requests = install_mock_transport(monkeypatch, _handler())

    asyncio.run(compose_answer(FakeAuth(), BASE, 'q', [f'fact {i}' for i in range(30)]))

    prompt = json.loads(requests[-1].content)['prompt']
    assert 'fact 9' in prompt
    assert 'fact 10' not in prompt


# --------------------------------------------------------------------------
# Degrading, never failing
# --------------------------------------------------------------------------


def test_rate_limit_falls_back_rather_than_raising(monkeypatch):
    install_mock_transport(monkeypatch, _handler(prompt_status=429))

    # 30/hour is low enough that a normal session reaches it; bullets on the
    # display beat an error on the display.
    assert asyncio.run(compose_or_none(FakeAuth(), BASE, 'q', FACTS, budget_s=5)) is None


def test_deleted_conversation_clears_the_cache(monkeypatch):
    install_mock_transport(monkeypatch, _handler(prompt_status=404))

    with pytest.raises(ComposeUnavailable):
        asyncio.run(compose_answer(FakeAuth(), BASE, 'q', FACTS))

    # Otherwise every later question would keep posting to a dead id for an hour.
    assert compose._CONVERSATION_ID is None


def test_no_conversations_is_unavailable_not_a_crash(monkeypatch):
    install_mock_transport(monkeypatch, _handler(conversations=[]))

    assert asyncio.run(compose_or_none(FakeAuth(), BASE, 'q', FACTS, budget_s=5)) is None


def test_empty_summary_falls_back(monkeypatch):
    install_mock_transport(monkeypatch, _handler(summary='   '))

    assert asyncio.run(compose_or_none(FakeAuth(), BASE, 'q', FACTS, budget_s=5)) is None


def test_no_facts_never_calls_omi(monkeypatch):
    requests = install_mock_transport(monkeypatch, _handler())

    assert asyncio.run(compose_or_none(FakeAuth(), BASE, 'q', [], budget_s=5)) is None
    assert requests == [], 'composing from nothing invents an answer; skip the call'


def test_budget_is_a_hard_ceiling(monkeypatch):
    def slow(request: httpx.Request) -> httpx.Response:
        raise AssertionError('should have been cancelled before the request completed')

    async def never(*args, **kwargs):
        await asyncio.sleep(10)

    monkeypatch.setattr(compose, 'compose_answer', never)

    # Late is the same as failed here: past ~5s the glasses show nothing at all.
    async def run():
        loop = asyncio.get_running_loop()
        started = loop.time()
        result = await compose_or_none(FakeAuth(), BASE, 'q', FACTS, budget_s=0.05)
        return result, loop.time() - started

    result, elapsed = asyncio.run(run())
    assert result is None
    assert elapsed < 1.0


def test_auth_failure_falls_back(monkeypatch):
    install_mock_transport(monkeypatch, _handler())

    auth = FakeAuth(fail=RuntimeError('no session'))
    assert asyncio.run(compose_or_none(auth, BASE, 'q', FACTS, budget_s=5)) is None

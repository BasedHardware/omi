"""Tests for composing retrieved facts into prose.

Compose is a best-effort layer sitting between retrieval and the display, so
every test here is really about one property: **it may degrade, but it may never
take the answer down with it.** It is a ladder -- the local model on this Mac,
then Omi's rate-limited cloud endpoint, then nothing -- and each rung fails for
ordinary reasons: Ollama is not running, the hourly cap is spent, the cached
conversation was deleted. Every one of those must surface as `None` to the
caller, which then shows the raw retrieved lines instead.

The local rung is off by default here (`_local_off`) so the cloud tests exercise
the cloud; the ladder tests turn it back on explicitly. The conversation id is a
module-level cache, deliberately -- re-listing conversations per question would
spend a round trip out of a ~5s budget -- so it is reset between tests too.
"""

import asyncio
import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import compose  # noqa: E402
import local_llm  # noqa: E402
from compose import ComposeUnavailable, compose_answer, compose_or_none  # noqa: E402
from conftest import FakeAuth, install_mock_transport  # noqa: E402

BASE = 'https://api.omi.me'
FACTS = ['You watched fireworks in New York.', 'You grilled burgers with friends.']


@pytest.fixture(autouse=True)
def _reset_cache():
    compose._CONVERSATION_ID = None
    compose._CONVERSATION_FETCHED_AT = 0.0
    local_llm._available = True
    yield
    compose._CONVERSATION_ID = None
    compose._CONVERSATION_FETCHED_AT = 0.0
    local_llm._available = True


@pytest.fixture(autouse=True)
def _local_off(monkeypatch):
    """Default the local rung off; ladder tests opt back in."""
    monkeypatch.setenv('OMI_EVEN_NO_LOCAL', '1')


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


# --------------------------------------------------------------------------
# The ladder: local first, cloud second, bullets last
# --------------------------------------------------------------------------


def _ladder_handler(*, local_status=200, local_text='You watched fireworks.', cloud_summary='cloud answer'):
    """Answer both rungs: Ollama's /api/generate and Omi's test-prompt."""
    cloud = _handler(summary=cloud_summary)

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == '/api/generate':
            if local_status != 200:
                return httpx.Response(local_status, text='no such model')
            return httpx.Response(200, json={'response': local_text})
        return cloud(request)

    return handle


def test_local_is_preferred_over_the_capped_cloud(monkeypatch):
    monkeypatch.delenv('OMI_EVEN_NO_LOCAL', raising=False)
    requests = install_mock_transport(monkeypatch, _ladder_handler(local_text='You saw fireworks.'))

    answer = asyncio.run(compose_or_none(FakeAuth(), BASE, 'q', FACTS, budget_s=5))

    assert answer == 'You saw fireworks.'
    # Spending the 30/hour cloud budget when a free local model answered would
    # be the whole point of this rung, wasted.
    assert [r.url.path for r in requests] == ['/api/generate']


def test_local_failure_falls_through_to_cloud(monkeypatch):
    monkeypatch.delenv('OMI_EVEN_NO_LOCAL', raising=False)
    requests = install_mock_transport(
        monkeypatch, _ladder_handler(local_status=404, cloud_summary='cloud picked it up')
    )

    answer = asyncio.run(compose_or_none(FakeAuth(), BASE, 'q', FACTS, budget_s=5))

    assert answer == 'cloud picked it up'
    assert '/api/generate' in [r.url.path for r in requests]
    assert any(r.url.path.endswith('/test-prompt') for r in requests)


def test_a_broken_local_model_is_not_retried_every_question(monkeypatch):
    monkeypatch.delenv('OMI_EVEN_NO_LOCAL', raising=False)
    requests = install_mock_transport(monkeypatch, _ladder_handler(local_status=404))

    asyncio.run(compose_or_none(FakeAuth(), BASE, 'q1', FACTS, budget_s=5))
    asyncio.run(compose_or_none(FakeAuth(), BASE, 'q2', FACTS, budget_s=5))

    # A missing model is config, not a blip: paying for that discovery once per
    # question would eat budget that the cloud rung needs.
    assert [r.url.path for r in requests].count('/api/generate') == 1


def test_both_rungs_down_returns_none_rather_than_raising(monkeypatch):
    monkeypatch.delenv('OMI_EVEN_NO_LOCAL', raising=False)
    install_mock_transport(monkeypatch, _ladder_handler(local_status=500, cloud_summary=''))

    assert asyncio.run(compose_or_none(FakeAuth(), BASE, 'q', FACTS, budget_s=5)) is None


def test_local_prompt_carries_the_question_and_facts(monkeypatch):
    monkeypatch.delenv('OMI_EVEN_NO_LOCAL', raising=False)
    requests = install_mock_transport(monkeypatch, _ladder_handler())

    asyncio.run(compose_or_none(FakeAuth(), BASE, 'What did I do?', FACTS, budget_s=5))

    body = json.loads(requests[0].content)
    assert 'What did I do?' in body['prompt']
    assert FACTS[0] in body['prompt']
    # qwen3.6 reasons by default; its thinking tokens cost more than the budget.
    assert body['think'] is False
    # Cold, this model needs 16.5s -- three times the budget -- so residency is
    # not an optimisation here, it is the difference between working and not.
    assert body['keep_alive'] == local_llm.KEEP_ALIVE
    # The cloud-only preamble must not leak into the local prompt.
    assert 'Disregard the conversation transcript' not in body['prompt']

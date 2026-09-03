"""Hop-2 behavior for the Perplexity gateway web-search tool.

sonar-pro stops at the vendor marketing site for product-history questions
(live RCA 2026-09-02). A thin first answer triggers exactly one retry whose
query carries the fixed primary-source retrieval appendix; a substantive first
answer never triggers a second call, and a failing hop-2 keeps the first
answer. httpx is mocked — no live Perplexity in CI.
"""

from typing import Any

import httpx
import pytest

from utils.retrieval.tools import perplexity_tools
from utils.retrieval.tools.perplexity_tools import (
    WEB_SEARCH_RETRIEVAL_APPENDIX,
    _looks_like_thin_miss,
)

_QUERY = 'How long did Whisper Flow take to build the first version of their desktop app?'
_THIN_ANSWER = (
    "I couldn't find public information about how long it took to build the first version. "
    "The company's site focuses on features and pricing."
)
_SUBSTANTIVE_ANSWER = (
    "Wispr Flow founder Tanay Kothari built the first version in about six weeks; hardware was "
    "killed in July 2024 and the launch moved to October 1, 2024."
)


def _sonar_result(text: str, citations: list[str] | None = None) -> dict[str, Any]:
    return {'choices': [{'message': {'content': text}}], 'citations': citations or []}


def _ok(text: str, citations: list[str] | None = None) -> httpx.Response:
    return httpx.Response(200, json=_sonar_result(text, citations))


class _RecordingGateway:
    """Async stand-in for the shared webhook client's POST surface."""

    def __init__(self, outcomes: list[Any]):
        self._outcomes = list(outcomes)
        self.requests: list[dict[str, Any]] = []

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        self.requests.append({'url': url, **kwargs})
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def gateway(monkeypatch):
    def _install(outcomes: list[Any]) -> _RecordingGateway:
        client = _RecordingGateway(outcomes)
        monkeypatch.setattr(perplexity_tools, 'get_webhook_client', lambda: client)
        return client

    return _install


@pytest.mark.asyncio
async def test_thin_first_answer_triggers_one_hop2_with_rewritten_query(gateway):
    client = gateway(
        [
            _ok(_THIN_ANSWER, citations=['https://wisprflow.ai']),
            _ok(_SUBSTANTIVE_ANSWER, citations=['https://www.producthunt.com/stories/go-with-the-flow']),
        ]
    )

    result = await perplexity_tools._perplexity_gateway_search(_QUERY)

    assert len(client.requests) == 2
    assert client.requests[0]['json']['messages'][0]['content'] == _QUERY
    assert client.requests[1]['json']['messages'][0]['content'] == _QUERY + WEB_SEARCH_RETRIEVAL_APPENDIX
    assert _SUBSTANTIVE_ANSWER in result
    assert 'producthunt.com' in result
    assert _THIN_ANSWER not in result
    # The retry stays on the proven lane configuration: same model, same token budget.
    assert all(request['json']['max_tokens'] == 1000 for request in client.requests)
    assert {request['json']['model'] for request in client.requests} == {
        perplexity_tools.feature_auto_lane_id('web_search')
    }


@pytest.mark.asyncio
async def test_substantive_first_answer_makes_exactly_one_call(gateway):
    client = gateway([_ok(_SUBSTANTIVE_ANSWER, citations=['https://example.com/founder-interview'])])

    result = await perplexity_tools._perplexity_gateway_search(_QUERY)

    assert len(client.requests) == 1
    assert client.requests[0]['json']['messages'][0]['content'] == _QUERY
    assert _SUBSTANTIVE_ANSWER in result


@pytest.mark.asyncio
async def test_non_200_first_response_keeps_the_existing_error_path(gateway):
    client = gateway([httpx.Response(503, text='unavailable')])

    result = await perplexity_tools._perplexity_gateway_search(_QUERY)

    assert len(client.requests) == 1
    assert result == 'Error: Perplexity API returned status 503. Please try again later.'


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'hop2_outcome',
    [
        httpx.ConnectError('boom'),
        httpx.Response(500, text='boom'),
        httpx.Response(200, text='not json'),
    ],
    ids=['transport-error', 'non-200', 'malformed-json'],
)
async def test_hop2_failure_returns_the_first_formatted_result(gateway, hop2_outcome):
    client = gateway([_ok(_THIN_ANSWER, citations=['https://wisprflow.ai']), hop2_outcome])

    result = await perplexity_tools._perplexity_gateway_search(_QUERY)

    assert len(client.requests) == 2
    assert _THIN_ANSWER in result
    assert 'wisprflow.ai' in result


@pytest.mark.asyncio
async def test_second_thin_answer_is_returned_without_a_third_call(gateway):
    client = gateway(
        [
            _ok(_THIN_ANSWER, citations=['https://wisprflow.ai']),
            _ok("Still couldn't find a launch timeline.", citations=['https://wisprflow.ai/pricing']),
        ]
    )

    result = await perplexity_tools._perplexity_gateway_search(_QUERY)

    assert len(client.requests) == 2
    assert "Still couldn't find a launch timeline." in result


def test_thin_miss_detector_flags_the_failure_class_not_substance():
    assert _looks_like_thin_miss("I couldn't find public info about the launch timeline.")
    assert _looks_like_thin_miss('There is no public timeline for the first version.')
    assert _looks_like_thin_miss("The company's site focuses on features.")
    assert _looks_like_thin_miss('No detailed information is available about the build period.')
    assert _looks_like_thin_miss('The marketing site does not disclose build dates.')
    assert not _looks_like_thin_miss(_SUBSTANTIVE_ANSWER)
    assert not _looks_like_thin_miss('')

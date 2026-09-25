"""The Jev client (utils/llm/jev_client.py) never raises and returns None on every failure.

HTTP is mocked with httpx.MockTransport; every state and answer here is synthetic.
"""

from __future__ import annotations

import json
from typing import Any, Callable

import httpx
import pytest

from config.jev_decisions import JEV_AUTO_LANE_ID, JEV_MAX_STATE_CHARS
from utils.llm import jev_client
from utils.llm.jev_client import TRUNCATION_MARKER, ask_jev, truncate_state

QUESTIONS = {
    'worth_keeping': {'type': 'noul', 'instructions': 'Keep it?'},
    'owner': {'type': 'choice', 'instructions': 'Whose?', 'criteria': {'user': 'the user', 'third_party': 'other'}},
}


def _ok_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        'model': 'typesafe/jev-1.13-20260917',
        'answers': {
            'worth_keeping': {'type': 'noul', 'noul': 0.12},
            'owner': {
                'type': 'choice',
                'choice': 'user',
                'probabilities': {'user': 0.93, 'third_party': 0.07},
                'confidence': 0.8,
            },
        },
        'usage': {'input_tokens': 40, 'output_tokens': 3},
    }
    body.update(overrides)
    return body


@pytest.fixture
def gateway(monkeypatch):
    """Route the client's httpx.Client through a scripted transport; returns the request log."""
    monkeypatch.setenv('OMI_LLM_GATEWAY_URL', 'http://gateway.test')
    requests: list[httpx.Request] = []
    script: list[Callable[[httpx.Request], httpx.Response]] = []
    recorded: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return script.pop(0)(request)

    real_client = httpx.Client

    def client_factory(*args: Any, **kwargs: Any) -> httpx.Client:
        kwargs['transport'] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(jev_client.httpx, 'Client', client_factory)
    monkeypatch.setattr(jev_client, 'record_jev_decision', lambda **labels: recorded.append(labels))
    return requests, script, recorded


def _respond(status: int, body: Any) -> Callable[[httpx.Request], httpx.Response]:
    return lambda request: httpx.Response(status, json=body)


def _raise(exc: Exception) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc

    return handler


def test_success_posts_to_the_gateway_lane_and_returns_typed_answers(gateway):
    requests, script, recorded = gateway
    script.append(_respond(200, _ok_body()))

    answers = ask_jev('synthetic state', QUESTIONS, lane='conversation_relevance')

    assert answers is not None
    assert answers.noul('worth_keeping') == pytest.approx(0.12)
    assert answers.choice_probability('owner', 'user') == pytest.approx(0.93)
    assert answers.choice_probability('owner', 'general_knowledge') == 0.0
    assert answers.served_model == 'typesafe/jev-1.13-20260917'
    (request,) = requests
    assert str(request.url) == 'http://gateway.test/v1/systemone'
    assert request.headers['x-omi-service-caller'] == 'backend'
    assert request.headers['x-omi-llm-feature'] == 'jev_conversation_relevance'
    assert json.loads(request.content) == {
        'model': JEV_AUTO_LANE_ID,
        'state': 'synthetic state',
        'questions': QUESTIONS,
    }
    assert [entry['outcome'] for entry in recorded] == ['success']


def test_unconfigured_gateway_makes_no_request(gateway, monkeypatch):
    requests, _, recorded = gateway
    monkeypatch.delenv('OMI_LLM_GATEWAY_URL')

    assert ask_jev('state', QUESTIONS, lane='memory_owner') is None
    assert requests == []
    assert [entry['outcome'] for entry in recorded] == ['unconfigured']


def test_a_timeout_is_retried_once_then_answers(gateway):
    requests, script, recorded = gateway
    script.extend([_raise(httpx.ReadTimeout('slow')), _respond(200, _ok_body())])

    assert ask_jev('state', QUESTIONS, lane='memory_owner') is not None
    assert len(requests) == 2
    assert [entry['outcome'] for entry in recorded] == ['success']


def test_two_timeouts_return_none(gateway):
    requests, script, recorded = gateway
    script.extend([_raise(httpx.ReadTimeout('slow')), _raise(httpx.ReadTimeout('slow'))])

    assert ask_jev('state', QUESTIONS, lane='memory_owner') is None
    assert len(requests) == 2
    assert [entry['outcome'] for entry in recorded] == ['timeout']


def test_a_5xx_is_retried_and_a_4xx_is_not(gateway):
    requests, script, recorded = gateway
    script.extend([_respond(503, {}), _respond(502, {})])
    assert ask_jev('state', QUESTIONS, lane='memory_owner') is None
    assert len(requests) == 2

    requests.clear()
    script.append(_respond(404, {'error': 'auto lane not found'}))
    assert ask_jev('state', QUESTIONS, lane='memory_owner') is None
    assert len(requests) == 1
    assert [entry['outcome'] for entry in recorded] == ['http_error', 'http_error']


def test_a_429_fails_open_without_an_instant_retry(gateway):
    requests, script, recorded = gateway
    script.extend([_respond(429, {}), _respond(200, _ok_body())])

    assert ask_jev('state', QUESTIONS, lane='conversation_relevance') is None
    assert len(requests) == 1
    assert len(script) == 1
    assert [entry['outcome'] for entry in recorded] == ['http_error']


@pytest.mark.parametrize(
    'body',
    [
        pytest.param('not json', id='non-json'),
        pytest.param({'answers': {'worth_keeping': {'noul': 0.2}}}, id='missing-question'),
        pytest.param(
            _ok_body(answers={'worth_keeping': {'noul': 1.4}, 'owner': {'probabilities': {'user': 0.5}}}),
            id='probability-out-of-range',
        ),
        pytest.param(
            _ok_body(answers={'worth_keeping': {'noul': True}, 'owner': {'probabilities': {'user': 0.5}}}),
            id='boolean-not-probability',
        ),
        pytest.param(
            _ok_body(answers={'worth_keeping': {'noul': 0.2}, 'owner': {'choice': 'user'}}),
            id='choice-without-probabilities',
        ),
        pytest.param(_ok_body(model='typesafe/jev-1.14'), id='unpinned-model-version'),
        pytest.param(_ok_body(model='typesafe/jev-1.130'), id='prefix-is-not-a-snapshot'),
    ],
)
def test_malformed_answers_return_none_without_retry(gateway, body):
    requests, script, recorded = gateway
    if isinstance(body, str):
        script.append(lambda request: httpx.Response(200, content=body.encode()))
    else:
        script.append(_respond(200, body))

    assert ask_jev('state', QUESTIONS, lane='conversation_relevance') is None
    assert len(requests) == 1
    assert [entry['outcome'] for entry in recorded] == ['malformed']


def test_an_unexpected_error_is_contained(gateway, monkeypatch):
    _, _, recorded = gateway
    monkeypatch.setattr(jev_client, 'llm_gateway_headers', lambda **_: (_ for _ in ()).throw(KeyError('boom')))

    assert ask_jev('state', QUESTIONS, lane='memory_owner') is None
    assert [entry['outcome'] for entry in recorded] == ['transport_error']


def test_state_is_truncated_to_the_context_budget_keeping_head_and_tail(gateway):
    requests, script, _ = gateway
    script.append(_respond(200, _ok_body()))
    state = 'HEAD' + 'x' * (JEV_MAX_STATE_CHARS * 2) + 'TAIL'

    ask_jev(state, QUESTIONS, lane='conversation_relevance')

    sent = json.loads(requests[0].content)['state']
    assert len(sent) == JEV_MAX_STATE_CHARS
    assert sent.startswith('HEAD') and sent.endswith('TAIL') and TRUNCATION_MARKER in sent


def test_short_states_are_not_truncated():
    assert truncate_state('short') == 'short'

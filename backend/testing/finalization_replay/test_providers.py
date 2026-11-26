"""The shared replay HTTP provider measures what it actually serves."""

import json
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from testing.finalization_replay.providers import _IDEMPOTENCY_KEY, _tokens, provider_server


def test_operation_idempotency_key_rejects_crlf():
    assert _IDEMPOTENCY_KEY.fullmatch('invalid\r\nkey') is None


def test_operation_endpoints_reject_invalid_key():
    with provider_server() as server:
        endpoint = f'http://127.0.0.1:{server.server_port}/v1/chat/completions/operations'
        key = 'invalid+key'
        with pytest.raises(HTTPError) as post_error:
            urlopen(Request(endpoint, b'{}', {'Idempotency-Key': key}), timeout=2)
        assert post_error.value.code == 400
        assert key not in server.operations

        server.operations[key] = {}
        with pytest.raises(HTTPError) as get_error:
            urlopen(f'{endpoint}/{key}', timeout=2)
        assert get_error.value.code == 404
        assert 'X-Omi-Idempotency-Key' not in get_error.value.headers


def test_ordinary_completions_reject_idempotency_key():
    calls = []
    with provider_server() as server:
        endpoint = f'http://127.0.0.1:{server.server_port}/v1/chat/completions'
        server.dispatch = lambda *args: calls.append(args)
        request = Request(endpoint, b'{}', {'Idempotency-Key': 'ordinary-key'})
        with pytest.raises(HTTPError) as error:
            urlopen(request, timeout=2)
        assert error.value.code == 400
        assert json.load(error.value)['error']['code'] == 'idempotency_operations_route_required'
        assert not server.operations
    assert not calls


def test_operation_key_rejects_changed_request_and_preserves_original_replay():
    calls = []
    with provider_server() as server:
        endpoint = f'http://127.0.0.1:{server.server_port}/v1/chat/completions/operations'
        server.state = SimpleNamespace(case={})

        def dispatch(_path, body, _headers):
            calls.append(body)
            return {'content': body['prompt']}

        server.dispatch = dispatch
        headers = {'Idempotency-Key': 'operation-key'}
        original = {'prompt': 'synthetic', 'temperature': 0}
        with urlopen(Request(endpoint, json.dumps(original).encode(), headers), timeout=2) as response:
            assert json.load(response) == {'content': 'synthetic'}

        changed = {**original, 'prompt': 'changed'}
        with pytest.raises(HTTPError) as error:
            urlopen(Request(endpoint, json.dumps(changed).encode(), headers), timeout=2)
        assert error.value.code == 409
        assert json.load(error.value)['error']['code'] == 'idempotency_conflict'
        assert 'X-Omi-Idempotency-Key' not in error.value.headers

        equivalent = {'temperature': 0, 'prompt': 'synthetic'}
        with urlopen(Request(endpoint, json.dumps(equivalent).encode(), headers), timeout=2) as response:
            assert json.load(response) == {'content': 'synthetic'}
    assert calls == [original]


@pytest.mark.parametrize('change', ['credential-source', 'forwarded-key', 'schema-property-order'])
def test_keyed_replay_conflicts_when_gateway_fingerprint_changes(change):
    def body(property_names):
        return {
            'response_format': {
                'type': 'json_schema',
                'json_schema': {'schema': {'properties': {name: {'type': 'string'} for name in property_names}}},
            },
        }

    original = body(('first', 'second'))
    retry = body(('second', 'first')) if change == 'schema-property-order' else original
    headers = {'Idempotency-Key': 'operation-key'}
    byok_header = 'X-Omi-Byok-Openai-Key'
    if change == 'forwarded-key':
        headers[byok_header] = 'synthetic-original'
    retry_headers = dict(headers)
    if change != 'schema-property-order':
        retry_headers[byok_header] = 'synthetic-retry'

    calls = []
    with provider_server() as server:
        server.state = SimpleNamespace(case={})
        endpoint = f'http://127.0.0.1:{server.server_port}/v1/chat/completions/operations'

        def dispatch(*_args):
            calls.append(True)
            return {'content': 'synthetic'}

        server.dispatch = dispatch
        with urlopen(Request(endpoint, json.dumps(original).encode(), headers), timeout=2) as response:
            assert response.status == 200
        with pytest.raises(HTTPError) as error:
            urlopen(Request(endpoint, json.dumps(retry).encode(), retry_headers), timeout=2)
        assert error.value.code == 409
        assert json.load(error.value)['error']['code'] == 'idempotency_conflict'
        fingerprint, _ = server.operations['operation-key']
        assert isinstance(fingerprint, bytes) and len(fingerprint) == 32
    assert calls == [True]


def test_wire_usage_uses_content_and_counts_idempotent_completion_once():
    state = SimpleNamespace(
        case={},
        notes='Canned notes.',
        apps=[],
        memories=[],
        notes_prompt_hashes=[],
        record_provider_call=lambda *_args: None,
        record_embedding_request=lambda *_args: None,
    )
    with provider_server() as server:
        server.state = state
        root = f'http://127.0.0.1:{server.server_port}/v1'
        body = {
            'model': 'omi:auto:conv-structure',
            'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': 'The synthetic agenda.'}]}],
        }

        def post(path, payload, headers=None):
            request = Request(root + path, json.dumps(payload).encode(), headers or {})
            with urlopen(request, timeout=2) as response:
                return json.load(response)

        expected = {'prompt_tokens': _tokens('The synthetic agenda.'), 'completion_tokens': _tokens(state.notes)}
        expected['total_tokens'] = sum(expected.values())
        key = 'same.paid_operation:01'
        operations = '/chat/completions/operations'
        headers = {'Idempotency-Key': key}
        assert post('/chat/completions', body)['usage'] == expected
        request = Request(root + operations, json.dumps(body).encode(), headers)
        with urlopen(request, timeout=2) as committed:
            assert committed.headers['X-Omi-Idempotency-Key'] == key
            assert json.load(committed)['usage'] == expected
        assert post(operations, body, headers)['usage'] == expected
        with urlopen(f'{root}{operations}/{key}', timeout=2) as replay:
            assert replay.headers['X-Omi-Idempotency-Key'] == key
            assert json.load(replay)['usage'] == expected
        assert post('/embeddings', {'model': 'openai-embeddings', 'input': [123, 456]})['usage']['total_tokens'] == 2

    assert state.replay_token_calls == [
        {
            'feature': 'conv-structure',
            'input': expected['prompt_tokens'],
            'output': expected['completion_tokens'],
            'embedding': False,
        },
        {
            'feature': 'conv-structure',
            'input': expected['prompt_tokens'],
            'output': expected['completion_tokens'],
            'embedding': False,
        },
        {'feature': 'openai-embeddings', 'input': 2, 'output': 0, 'embedding': True},
    ]

"""The shared replay HTTP provider measures what it actually serves."""

import json
from types import SimpleNamespace
from urllib.request import Request, urlopen

from testing.finalization_replay.providers import _tokens, provider_server


def test_wire_usage_uses_content_and_counts_idempotent_completion_once():
    state = SimpleNamespace(
        case={}, notes='Canned notes.', apps=[], memories=[], provider_calls=[], notes_prompt_hashes=[]
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
        key = {'Idempotency-Key': 'same-paid-operation'}
        assert post('/chat/completions', body)['usage'] == expected
        assert post('/chat/completions/operations', body, key)['usage'] == expected
        assert post('/chat/completions/operations', body, key)['usage'] == expected
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

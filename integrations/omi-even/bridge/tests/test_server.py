"""Tests for the bridge itself: the Even AI agent endpoint and the glasses socket.

Both consumers are unforgiving in the same way -- they have no error UI. The
Even phone app renders `choices[0].message.content` and nothing else, and the
Hub plugin renders whatever text frame arrives. So the contract asserted here is
that *something displayable always comes back*: never a 500, never a body that
overflows the 400-character screen, and never a socket that dies because one
message handler raised.

`server.omi` and `server.auth` are replaced wholesale; no test may reach
api.omi.me (see `conftest._no_network`).
"""

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
from conftest import AUTH_HEADER, EVEN_TOKEN, FakeAuth  # noqa: E402
from capture import CaptureStats  # noqa: E402
from display import DEFAULT_LIMIT  # noqa: E402
from omi_client import ChatEvent, ChatResult  # noqa: E402

AGENT_PATHS = ['/', '/v1/chat/completions', '/chat/completions']


# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------


class FakeOmi:
    """Every Omi call the bridge makes, scripted."""

    def __init__(self) -> None:
        self.chat_result = ChatResult(text='All clear.')
        self.chat_exc: Exception | None = None
        self.stream_events = [ChatEvent('done', 'All clear.')]
        self.stream_exc: Exception | None = None
        self.memories_rows: list[dict] = []
        self.action_rows: list[dict] = []
        self.summary_rows: list[dict] = []
        self.transcript = ''
        self.quota: dict = {'plan': 'unlimited'}
        self.quota_exc: Exception | None = None
        self.calls: list = []

    async def chat(self, text, app_id=None, deadline_s=None):
        self.calls.append(('chat', text, deadline_s))
        if self.chat_exc:
            raise self.chat_exc
        return self.chat_result

    async def chat_stream(self, text, app_id=None):
        self.calls.append(('chat_stream', text))
        if self.stream_exc:
            raise self.stream_exc
        for event in self.stream_events:
            yield event

    async def memories(self, limit=20):
        self.calls.append(('memories', limit))
        if isinstance(self.memories_rows, Exception):
            raise self.memories_rows
        return self.memories_rows[:limit]

    async def action_items(self, limit=20):
        self.calls.append(('action_items', limit))
        if isinstance(self.action_rows, Exception):
            raise self.action_rows
        return self.action_rows[:limit]

    async def daily_summaries(self, limit=3):
        self.calls.append(('daily_summaries', limit))
        return self.summary_rows[:limit]

    async def transcribe_pcm(self, pcm, **kwargs):
        self.calls.append(('transcribe_pcm', pcm))
        return self.transcript

    async def usage_quota(self):
        if self.quota_exc:
            raise self.quota_exc
        return self.quota


class FakeCaptureSession:
    """Stands in for `CaptureSession` so no test opens the listen socket."""

    def __init__(self, auth, base_url, on_segments=None, on_event=None) -> None:
        self.auth = auth
        self.base_url = base_url
        self.on_segments = on_segments
        self.fed: list[bytes] = []
        self.starts = 0
        self.stops: list[bool] = []
        self.start_segments: list[dict] | None = None
        self.stats = CaptureStats(bytes_sent=32000, conversation_id='conv-7')

    async def start(self) -> None:
        self.starts += 1
        if self.start_segments and self.on_segments:
            await self.on_segments(self.start_segments)

    async def stop(self, finalize=True):
        self.stops.append(finalize)
        return self.stats

    def feed(self, pcm: bytes) -> None:
        self.fed.append(pcm)


@pytest.fixture
def bridge(monkeypatch, tmp_path):
    omi = FakeOmi()
    sessions: list[FakeCaptureSession] = []

    class _Session(FakeCaptureSession):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            sessions.append(self)

    monkeypatch.setattr(server, 'omi', omi)
    monkeypatch.setattr(server, 'auth', FakeAuth())
    monkeypatch.setattr(server, 'CaptureSession', _Session)
    monkeypatch.setattr(server, '_CONTRACT_LOG', str(tmp_path / 'add-agent-capture.log'))

    yield SimpleNamespace(
        client=TestClient(server.app),
        omi=omi,
        sessions=sessions,
        contract_log=tmp_path / 'add-agent-capture.log',
    )
    server._clients.clear()


def assert_openai_body(body: dict, *, model: str = 'omi') -> str:
    """The Even app reads exactly one field; the rest must still be well formed."""
    assert body['object'] == 'chat.completion'
    assert body['model'] == model
    assert isinstance(body['created'], int)
    assert isinstance(body['choices'], list) and len(body['choices']) == 1
    choice = body['choices'][0]
    assert choice['index'] == 0
    assert choice['finish_reason'] == 'stop'
    assert choice['message']['role'] == 'assistant'
    content = choice['message']['content']
    assert isinstance(content, str)
    assert set(body['usage']) == {'prompt_tokens', 'completion_tokens', 'total_tokens'}
    return content


def user_body(text) -> dict:
    return {'messages': [{'role': 'user', 'content': text}]}


# --------------------------------------------------------------------------
# _extract_question
# --------------------------------------------------------------------------


def test_plain_string_content():
    assert server._extract_question(user_body('what is on my plate')) == 'what is on my plate'


def test_list_of_parts_content():
    """The newer OpenAI content shape; a string-only parser returns nothing
    here and the bridge answers "No user message found" to every question.
    """
    payload = {'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': 'what is on my plate'}]}]}
    assert server._extract_question(payload) == 'what is on my plate'


def test_list_of_parts_joins_text_and_ignores_other_types():
    payload = {
        'messages': [
            {
                'role': 'user',
                'content': [
                    {'type': 'image_url', 'image_url': {'url': 'https://x/y.png'}},
                    {'type': 'text', 'text': 'what is'},
                    {'type': 'text', 'text': 'on my plate'},
                    {'type': 'text'},
                ],
            }
        ]
    }
    assert server._extract_question(payload) == 'what is on my plate'


def test_the_last_user_message_wins():
    payload = {
        'messages': [
            {'role': 'user', 'content': 'first question'},
            {'role': 'assistant', 'content': 'an answer'},
            {'role': 'user', 'content': 'second question'},
        ]
    }
    assert server._extract_question(payload) == 'second question'


def test_system_prompts_are_not_mistaken_for_the_question():
    payload = {
        'messages': [
            {'role': 'system', 'content': 'You are a helpful assistant.'},
            {'role': 'user', 'content': 'what is on my plate'},
        ]
    }
    assert server._extract_question(payload) == 'what is on my plate'


def test_falls_back_to_the_last_message_when_no_user_role_is_present():
    """The Add Agent contract is undocumented; a firmware that omits `role`
    must still get an answer rather than a 400.
    """
    payload = {'messages': [{'content': 'what is on my plate'}]}
    assert server._extract_question(payload) == 'what is on my plate'


def test_an_empty_last_user_message_falls_back_to_an_earlier_one():
    payload = {
        'messages': [
            {'role': 'user', 'content': 'the real question'},
            {'role': 'user', 'content': '   '},
        ]
    }
    assert server._extract_question(payload) == 'the real question'


def test_content_is_stripped():
    assert server._extract_question(user_body('  spaced out  ')) == 'spaced out'


@pytest.mark.parametrize(
    'payload',
    [
        {},
        {'messages': []},
        {'messages': None},
        {'messages': 'not a list'},
        {'messages': {'role': 'user'}},
        {'messages': [None]},
        {'messages': ['a bare string']},
        {'messages': [42]},
        {'messages': [{'role': 'user'}]},
        {'messages': [{'role': 'user', 'content': None}]},
        {'messages': [{'role': 'user', 'content': 123}]},
        {'messages': [{'role': 'user', 'content': {'text': 'nested wrong'}}]},
        {'messages': [{'role': 'user', 'content': []}]},
        {'messages': [{'role': 'user', 'content': ['a bare string']}]},
        {'messages': [{'role': 'user', 'content': [{'type': 'image_url'}]}]},
        {'messages': [{'role': 'user', 'content': '   '}]},
    ],
)
def test_unusable_bodies_yield_an_empty_question_without_crashing(payload):
    assert server._extract_question(payload) == ''


# --------------------------------------------------------------------------
# _authorized
# --------------------------------------------------------------------------


def make_request(headers: dict):
    scope = {
        'type': 'http',
        'http_version': '1.1',
        'method': 'POST',
        'scheme': 'http',
        'path': '/',
        'raw_path': b'/',
        'query_string': b'',
        'root_path': '',
        'server': ('testserver', 80),
        'client': ('1.2.3.4', 5000),
        'headers': [(k.lower().encode(), v.encode()) for k, v in headers.items()],
    }
    from starlette.requests import Request

    return Request(scope)


@pytest.mark.parametrize(
    'header',
    [
        None,
        '',
        'Bearer',
        'Bearer ',
        EVEN_TOKEN,
        f'Basic {EVEN_TOKEN}',
        f'Token {EVEN_TOKEN}',
        'Bearer wrong-token',
        f'Bearer {EVEN_TOKEN}x',
        f'Bearer {EVEN_TOKEN[:-1]}',
        'Bearer ' + EVEN_TOKEN.upper(),
    ],
)
def test_unauthorized_headers_are_rejected(header):
    headers = {} if header is None else {'authorization': header}
    assert server._authorized(make_request(headers)) is False


@pytest.mark.parametrize(
    'header',
    [
        f'Bearer {EVEN_TOKEN}',
        f'bearer {EVEN_TOKEN}',  # scheme is case-insensitive per RFC 7235
        f'BEARER {EVEN_TOKEN}',
        f'Bearer  {EVEN_TOKEN} ',  # stray whitespace around the value
    ],
)
def test_valid_headers_are_accepted(header):
    assert server._authorized(make_request({'authorization': header})) is True


def test_the_token_is_compared_in_constant_time(monkeypatch):
    """A shared secret over the open internet: `==` short-circuits on the first
    differing byte and leaks the token one character at a time.
    """
    seen = []
    real = server.secrets.compare_digest

    def spy(a, b):
        seen.append((a, b))
        return real(a, b)

    monkeypatch.setattr(server.secrets, 'compare_digest', spy)
    assert server._authorized(make_request({'authorization': f'Bearer {EVEN_TOKEN}'})) is True
    assert seen == [(EVEN_TOKEN, EVEN_TOKEN)]


# --------------------------------------------------------------------------
# Agent endpoint -- auth
# --------------------------------------------------------------------------


@pytest.mark.parametrize('path', AGENT_PATHS)
def test_agent_requires_a_token(bridge, path):
    response = bridge.client.post(path, json=user_body('hi'))
    assert response.status_code == 401
    assert response.json() == {'error': {'message': 'Unauthorized'}}


@pytest.mark.parametrize('path', AGENT_PATHS)
def test_agent_rejects_the_wrong_token(bridge, path):
    response = bridge.client.post(path, json=user_body('hi'), headers={'Authorization': 'Bearer nope'})
    assert response.status_code == 401


def test_an_unauthorized_request_never_reaches_omi(bridge):
    bridge.client.post('/', json=user_body('hi'))
    assert bridge.omi.calls == []


# --------------------------------------------------------------------------
# Agent endpoint -- bad requests
# --------------------------------------------------------------------------


@pytest.mark.parametrize('body', [b'not json', b'', b'{"unterminated', b'\xff\xfe'])
def test_non_json_bodies_are_rejected(bridge, body):
    response = bridge.client.post('/', content=body, headers=AUTH_HEADER)
    assert response.status_code == 400
    assert 'JSON' in response.json()['error']['message']


@pytest.mark.parametrize('body', ['[1, 2, 3]', '"a string"', '42', 'null'])
def test_json_that_is_not_an_object_is_rejected(bridge, body):
    response = bridge.client.post('/', content=body, headers=AUTH_HEADER)
    assert response.status_code == 400


@pytest.mark.parametrize('payload', [{}, {'messages': []}, {'messages': [{'role': 'user', 'content': ''}]}])
def test_a_body_with_no_question_is_rejected(bridge, payload):
    response = bridge.client.post('/', json=payload, headers=AUTH_HEADER)
    assert response.status_code == 400
    assert response.json()['error']['message'] == 'No user message found'


def test_a_bad_request_never_reaches_omi(bridge):
    bridge.client.post('/', content=b'not json', headers=AUTH_HEADER)
    assert bridge.omi.calls == []


# --------------------------------------------------------------------------
# Agent endpoint -- answers
# --------------------------------------------------------------------------


@pytest.mark.parametrize('path', AGENT_PATHS)
def test_a_question_returns_a_valid_chat_completion(bridge, path):
    bridge.omi.chat_result = ChatResult(text='You have three things left today.')
    response = bridge.client.post(path, json=user_body('what is on my plate'), headers=AUTH_HEADER)

    assert response.status_code == 200
    content = assert_openai_body(response.json())
    assert content == 'You have three things left today.'
    assert bridge.omi.calls[0][:2] == ('chat', 'what is on my plate')


def test_the_configured_deadline_is_passed_to_omi(bridge):
    bridge.client.post('/', json=user_body('hi'), headers=AUTH_HEADER)
    assert bridge.omi.calls[0][2] == server.AGENT_DEADLINE_S


def test_the_answer_is_reduced_to_something_the_glasses_can_show(bridge):
    """Omi writes markdown for a phone; the G2 renders ~400 plain characters."""
    bridge.omi.chat_result = ChatResult(
        text='## Today\n\nYou owe **Marcus** the writeup[1] -- see [the doc](https://omi.me/d) 🎉. '
        + 'Also, every other thing on the list is still open and waiting for you. ' * 20
    )
    response = bridge.client.post('/', json=user_body('hi'), headers=AUTH_HEADER)
    content = assert_openai_body(response.json())

    assert len(content) <= DEFAULT_LIMIT
    assert '**' not in content and '](' not in content and '[1]' not in content
    assert 'http' not in content
    for char in content:
        assert char == '\n' or ' ' <= char <= '~', f'unrenderable character {char!r}'


def test_an_omi_error_is_reported_as_an_answer_not_an_http_error(bridge):
    bridge.omi.chat_result = ChatResult(text='', error='quota exhausted')
    response = bridge.client.post('/', json=user_body('hi'), headers=AUTH_HEADER)

    assert response.status_code == 200
    content = assert_openai_body(response.json())
    assert 'could not answer' in content
    assert 'quota exhausted' in content
    assert len(content) <= DEFAULT_LIMIT


def test_an_empty_answer_becomes_a_readable_sentence(bridge):
    bridge.omi.chat_result = ChatResult(text='   ')
    content = assert_openai_body(bridge.client.post('/', json=user_body('hi'), headers=AUTH_HEADER).json())
    assert content == 'Omi had no answer for that.'


def test_a_truncated_answer_is_still_returned(bridge):
    """A partial answer beats a spinner; the deadline exists precisely for this."""
    bridge.omi.chat_result = ChatResult(text='The battery regression is', truncated=True)
    content = assert_openai_body(bridge.client.post('/', json=user_body('hi'), headers=AUTH_HEADER).json())
    assert content == 'The battery regression is'


def test_an_unexpected_exception_never_becomes_a_500(bridge):
    """The glasses have no error path: a 500 shows as nothing at all."""
    bridge.omi.chat_exc = ZeroDivisionError('unexpected')
    response = bridge.client.post('/', json=user_body('hi'), headers=AUTH_HEADER)

    assert response.status_code == 200
    content = assert_openai_body(response.json())
    assert content == 'Bridge error: ZeroDivisionError'
    assert len(content) <= DEFAULT_LIMIT


def test_an_exception_message_is_not_leaked_to_the_glasses(bridge):
    bridge.omi.chat_exc = RuntimeError('postgres://user:hunter2@internal-host/db')
    content = assert_openai_body(bridge.client.post('/', json=user_body('hi'), headers=AUTH_HEADER).json())
    assert 'hunter2' not in content


def test_an_auth_failure_is_a_503_so_the_operator_can_tell_it_apart(bridge):
    bridge.omi.chat_exc = server.AuthError('No signed-in Omi desktop session found')
    response = bridge.client.post('/', json=user_body('hi'), headers=AUTH_HEADER)
    assert response.status_code == 503
    assert 'session' in response.json()['error']['message']


def test_the_model_field_is_echoed_back(bridge):
    body = {'model': 'gpt-4o-mini', **user_body('hi')}
    response = bridge.client.post('/', json=body, headers=AUTH_HEADER)
    assert_openai_body(response.json(), model='gpt-4o-mini')


def test_a_null_model_falls_back_to_omi(bridge):
    body = {'model': None, **user_body('hi')}
    assert_openai_body(bridge.client.post('/', json=body, headers=AUTH_HEADER).json(), model='omi')


def test_the_response_is_plain_json(bridge):
    response = bridge.client.post('/', json=user_body('hi'), headers=AUTH_HEADER)
    assert response.headers['content-type'].startswith('application/json')
    json.loads(response.text)


# --------------------------------------------------------------------------
# Contract capture
# --------------------------------------------------------------------------


def test_the_raw_request_is_captured_for_the_undocumented_contract(bridge):
    bridge.client.post('/', json=user_body('what is on my plate'), headers=AUTH_HEADER)
    entry = json.loads(bridge.contract_log.read_text().split('\n---\n')[0])
    assert entry['method'] == 'POST'
    assert entry['path'] == '/'
    assert 'what is on my plate' in entry['body']


def test_the_bearer_token_is_redacted_from_the_capture(bridge):
    bridge.client.post('/', json=user_body('hi'), headers={'Authorization': 'Bearer super-secret-value'})
    text = bridge.contract_log.read_text()
    assert 'super-secret-value' not in text
    assert '<redacted>' in text


def test_rejected_requests_are_captured_too(bridge):
    """A token mismatch has to stay diagnosable from the capture alone."""
    bridge.client.post('/', json=user_body('hi'), headers={'Authorization': 'Bearer wrong'})
    assert bridge.contract_log.exists()


def test_a_failing_capture_never_breaks_the_request(bridge, monkeypatch):
    monkeypatch.setattr(server, '_CONTRACT_LOG', '/nonexistent-dir/capture.log')
    response = bridge.client.post('/', json=user_body('hi'), headers=AUTH_HEADER)
    assert response.status_code == 200


# --------------------------------------------------------------------------
# /health
# --------------------------------------------------------------------------


def test_health_reports_quota_and_auth_without_credentials(bridge):
    bridge.omi.quota = {'plan': 'unlimited', 'used': 3}
    body = bridge.client.get('/health').json()

    assert body['ok'] is True
    assert body['quota'] == {'plan': 'unlimited', 'used': 3}
    assert body['auth'] == {'loaded': True, 'uid': 'fake-uid', 'expires_in': 3000}
    assert body['omi_api'] == server.OMI_API_BASE
    assert 'token' not in json.dumps(body).lower()


def test_health_never_500s_when_omi_is_down(bridge):
    bridge.omi.quota_exc = RuntimeError('connection refused')
    response = bridge.client.get('/health')

    assert response.status_code == 200
    body = response.json()
    assert body['ok'] is False
    assert 'RuntimeError' in body['quota_error']
    assert body['auth'] == {'loaded': True, 'uid': 'fake-uid', 'expires_in': 3000}


# --------------------------------------------------------------------------
# /app -- handshake and framing
# --------------------------------------------------------------------------


def test_the_socket_greets_with_the_backend_it_is_bound_to(bridge):
    with bridge.client.websocket_connect('/app') as ws:
        assert ws.receive_json() == {'type': 'hello', 'omi_api': server.OMI_API_BASE}


def test_connected_clients_are_tracked_and_released(bridge):
    assert len(server._clients) == 0
    with bridge.client.websocket_connect('/app') as ws:
        ws.receive_json()
        assert len(server._clients) == 1
    assert len(server._clients) == 0


def test_ping_is_answered(bridge):
    with bridge.client.websocket_connect('/app') as ws:
        ws.receive_json()
        ws.send_text(json.dumps({'type': 'ping'}))
        assert ws.receive_json() == {'type': 'pong'}


@pytest.mark.parametrize('raw', ['not json', '', '[1, 2, 3]', '"a string"', 'null', '{"no type": 1}', '{"type": "nope"}'])
def test_junk_and_unknown_messages_are_ignored_without_a_reply(bridge, raw):
    """An unknown type must be a silent no-op, not an error frame and not a
    close -- the plugin and the bridge ship on different schedules.
    """
    with bridge.client.websocket_connect('/app') as ws:
        ws.receive_json()
        ws.send_text(raw)
        ws.send_text(json.dumps({'type': 'ping'}))
        assert ws.receive_json() == {'type': 'pong'}


# --------------------------------------------------------------------------
# /app -- chat
# --------------------------------------------------------------------------


def read_until(ws, kind, limit=50):
    """Collect frames up to and including the first of type `kind`."""
    frames = []
    for _ in range(limit):
        frame = ws.receive_json()
        frames.append(frame)
        if frame.get('type') == kind:
            return frames
    raise AssertionError(f'never received a {kind!r} frame; got {frames}')


def test_chat_streams_deltas_then_a_done_frame(bridge):
    bridge.omi.stream_events = [
        ChatEvent('data', 'x' * 40),
        ChatEvent('data', 'y' * 40),
        ChatEvent('done', 'The battery regression is open.'),
    ]
    with bridge.client.websocket_connect('/app') as ws:
        ws.receive_json()
        ws.send_text(json.dumps({'type': 'chat', 'text': 'what is on my plate'}))
        frames = read_until(ws, 'chat_done')

    assert [f['type'] for f in frames] == ['chat_delta', 'chat_done']
    done = frames[-1]
    assert done['text'] == 'The battery regression is open.'
    assert done['error'] is False
    assert done['pages'] == ['The battery regression is open.']
    assert bridge.omi.calls[0] == ('chat_stream', 'what is on my plate')


def test_deltas_are_coalesced_instead_of_one_frame_per_token(bridge):
    """Every frame is a BLE round trip. 20 tokens must not be 20 writes."""
    bridge.omi.stream_events = [ChatEvent('data', 'token' * 2) for _ in range(20)]
    with bridge.client.websocket_connect('/app') as ws:
        ws.receive_json()
        ws.send_text(json.dumps({'type': 'chat', 'text': 'hi'}))
        frames = read_until(ws, 'chat_done')

    deltas = [f for f in frames if f['type'] == 'chat_delta']
    assert 0 < len(deltas) < 20 / 2, f'{len(deltas)} frames for 20 tokens is not coalescing'
    assert all(len(d['text']) >= 60 for d in deltas)
    assert ''.join(d['text'] for d in deltas) in frames[-1]['text']


def test_thinking_lines_are_forwarded_as_status_and_capped(bridge):
    bridge.omi.stream_events = [ChatEvent('think', 'S' * 500), ChatEvent('done', 'ok')]
    with bridge.client.websocket_connect('/app') as ws:
        ws.receive_json()
        ws.send_text(json.dumps({'type': 'chat', 'text': 'hi'}))
        frames = read_until(ws, 'chat_done')

    status = [f for f in frames if f['type'] == 'chat_status']
    assert len(status) == 1
    assert len(status[0]['text']) <= 60


def test_a_stream_with_no_done_frame_still_answers_from_the_deltas(bridge):
    bridge.omi.stream_events = [ChatEvent('data', 'partial '), ChatEvent('data', 'answer')]
    with bridge.client.websocket_connect('/app') as ws:
        ws.receive_json()
        ws.send_text(json.dumps({'type': 'chat', 'text': 'hi'}))
        done = read_until(ws, 'chat_done')[-1]

    assert done['text'] == 'partial answer'
    assert done['error'] is False


def test_an_empty_done_text_falls_back_to_the_deltas(bridge):
    bridge.omi.stream_events = [ChatEvent('data', 'from the deltas'), ChatEvent('done', '')]
    with bridge.client.websocket_connect('/app') as ws:
        ws.receive_json()
        ws.send_text(json.dumps({'type': 'chat', 'text': 'hi'}))
        assert read_until(ws, 'chat_done')[-1]['text'] == 'from the deltas'


def test_a_stream_error_ends_the_turn_with_an_error_frame(bridge):
    bridge.omi.stream_events = [ChatEvent('data', 'partial'), ChatEvent('error', 'quota exhausted')]
    with bridge.client.websocket_connect('/app') as ws:
        ws.receive_json()
        ws.send_text(json.dumps({'type': 'chat', 'text': 'hi'}))
        done = read_until(ws, 'chat_done')[-1]

    assert done['error'] is True
    assert 'quota exhausted' in done['text']
    assert 'pages' not in done


def test_the_answer_is_fitted_and_paginated_for_the_text_container(bridge):
    """`textContainerUpgrade` caps at 2000 characters."""
    bridge.omi.stream_events = [ChatEvent('done', 'Sentence number one. ' * 400)]
    with bridge.client.websocket_connect('/app') as ws:
        ws.receive_json()
        ws.send_text(json.dumps({'type': 'chat', 'text': 'hi'}))
        done = read_until(ws, 'chat_done')[-1]

    assert len(done['text']) <= 1800
    assert done['pages'] and all(len(page) <= 400 for page in done['pages'])
    assert ' '.join(done['pages']).split() == done['text'].split()


@pytest.mark.parametrize('text', ['', '   ', None])
def test_an_empty_question_is_refused_without_calling_omi(bridge, text):
    with bridge.client.websocket_connect('/app') as ws:
        ws.receive_json()
        ws.send_text(json.dumps({'type': 'chat', 'text': text}))
        frame = ws.receive_json()

    assert frame == {'type': 'chat_done', 'text': 'Nothing to ask.', 'error': True}
    assert bridge.omi.calls == []


# --------------------------------------------------------------------------
# /app -- data views
# --------------------------------------------------------------------------


def test_memories_are_returned_fitted(bridge):
    bridge.omi.memories_rows = [{'content': 'Sarah prefers **async** updates 🎉'}, {'content': 'x' * 900}]
    with bridge.client.websocket_connect('/app') as ws:
        ws.receive_json()
        ws.send_text(json.dumps({'type': 'memories', 'limit': 5}))
        frame = ws.receive_json()

    assert frame['type'] == 'memories'
    assert frame['items'][0] == {'content': 'Sarah prefers async updates'}
    assert len(frame['items'][1]['content']) <= 200
    assert ('memories', 5) in bridge.omi.calls


def test_memories_default_to_twenty(bridge):
    with bridge.client.websocket_connect('/app') as ws:
        ws.receive_json()
        ws.send_text(json.dumps({'type': 'memories'}))
        ws.receive_json()
    assert ('memories', 20) in bridge.omi.calls


def test_action_items_carry_their_completed_flag(bridge):
    bridge.omi.action_rows = [
        {'description': 'Reply to *Marcus*', 'completed': True},
        {'description': 'File the regression'},
        {},
    ]
    with bridge.client.websocket_connect('/app') as ws:
        ws.receive_json()
        ws.send_text(json.dumps({'type': 'action_items'}))
        frame = ws.receive_json()

    assert frame['items'] == [
        {'description': 'Reply to Marcus', 'completed': True},
        {'description': 'File the regression', 'completed': False},
        {'description': '', 'completed': False},
    ]


def test_action_item_descriptions_are_capped(bridge):
    bridge.omi.action_rows = [{'description': 'w ' * 500}]
    with bridge.client.websocket_connect('/app') as ws:
        ws.receive_json()
        ws.send_text(json.dumps({'type': 'action_items'}))
        assert len(ws.receive_json()['items'][0]['description']) <= 120


def test_today_returns_the_summary_paginated(bridge):
    bridge.omi.summary_rows = [{'summary': 'You shipped the OTA. ' * 200}]
    with bridge.client.websocket_connect('/app') as ws:
        ws.receive_json()
        ws.send_text(json.dumps({'type': 'today'}))
        frame = ws.receive_json()

    assert frame['type'] == 'today'
    assert len(frame['text']) <= 1800
    assert all(len(page) <= 400 for page in frame['pages'])
    assert ('daily_summaries', 1) in bridge.omi.calls


def test_today_accepts_the_overview_field_too(bridge):
    bridge.omi.summary_rows = [{'overview': 'A quiet day.'}]
    with bridge.client.websocket_connect('/app') as ws:
        ws.receive_json()
        ws.send_text(json.dumps({'type': 'today'}))
        assert ws.receive_json()['text'] == 'A quiet day.'


def test_today_with_no_summary_says_so(bridge):
    bridge.omi.summary_rows = []
    with bridge.client.websocket_connect('/app') as ws:
        ws.receive_json()
        ws.send_text(json.dumps({'type': 'today'}))
        frame = ws.receive_json()
    assert frame['text'] == 'No summary for today yet.'
    assert frame['pages'] == ['No summary for today yet.']


# --------------------------------------------------------------------------
# /app -- audio
# --------------------------------------------------------------------------


def test_binary_frames_are_fed_to_the_capture_session(bridge):
    with bridge.client.websocket_connect('/app') as ws:
        ws.receive_json()
        ws.send_bytes(b'\x01\x02' * 500)
        ws.send_bytes(b'\x03\x04' * 500)
        ws.send_text(json.dumps({'type': 'ping'}))
        assert ws.receive_json() == {'type': 'pong'}

    assert bridge.sessions[0].fed == [b'\x01\x02' * 500, b'\x03\x04' * 500]


def test_capture_can_be_started_and_stopped(bridge):
    with bridge.client.websocket_connect('/app') as ws:
        ws.receive_json()
        ws.send_text(json.dumps({'type': 'capture', 'enabled': True}))
        assert ws.receive_json() == {'type': 'capture', 'active': True}

        ws.send_text(json.dumps({'type': 'capture', 'enabled': False}))
        stopped = ws.receive_json()

    session = bridge.sessions[0]
    assert session.starts == 1
    assert session.stops[0] is True, 'the conversation must be finalized explicitly'
    assert stopped == {'type': 'capture', 'active': False, 'seconds': 1.0, 'conversation_id': 'conv-7'}


def test_live_transcript_segments_are_pushed_to_the_glasses(bridge):
    with bridge.client.websocket_connect('/app') as ws:
        ws.receive_json()
        bridge.sessions[0].start_segments = [{'text': 'the battery'}, {'text': 'regression'}, {}]
        ws.send_text(json.dumps({'type': 'capture', 'enabled': True}))
        frames = read_until(ws, 'capture')

    transcripts = [f for f in frames if f['type'] == 'transcript']
    assert transcripts == [{'type': 'transcript', 'text': 'the battery regression'}]


def test_the_capture_session_is_stopped_when_the_socket_drops(bridge):
    """Otherwise the conversation lingers `in_progress` until something else
    notices it is stale.
    """
    with bridge.client.websocket_connect('/app') as ws:
        ws.receive_json()
        ws.send_text(json.dumps({'type': 'capture', 'enabled': True}))
        ws.receive_json()
    assert bridge.sessions[0].stops[-1] is True


def test_push_to_talk_transcribes_buffered_pcm(bridge):
    bridge.omi.transcript = 'what is on my plate'
    with bridge.client.websocket_connect('/app') as ws:
        ws.receive_json()
        ws.send_text(json.dumps({'type': 'transcribe', 'pcm_hex': '0102ffee'}))
        assert ws.receive_json() == {'type': 'transcribed', 'text': 'what is on my plate'}

    assert ('transcribe_pcm', b'\x01\x02\xff\xee') in bridge.omi.calls


def test_push_to_talk_with_no_audio_does_not_call_omi(bridge):
    with bridge.client.websocket_connect('/app') as ws:
        ws.receive_json()
        ws.send_text(json.dumps({'type': 'transcribe', 'pcm_hex': ''}))
        assert ws.receive_json() == {'type': 'transcribed', 'text': ''}
    assert bridge.omi.calls == []


# --------------------------------------------------------------------------
# /app -- failure isolation
# --------------------------------------------------------------------------


def test_a_handler_exception_sends_an_error_frame_and_keeps_the_socket_open(bridge):
    """One bad request must not take the session down; the plugin has no
    reconnect UI and the user would just see the app stop responding.
    """
    bridge.omi.memories_rows = RuntimeError('omi is down')
    with bridge.client.websocket_connect('/app') as ws:
        ws.receive_json()
        ws.send_text(json.dumps({'type': 'memories'}))
        error = ws.receive_json()

        assert error['type'] == 'error'
        assert 'RuntimeError' in error['text']

        # Still alive, and still serving.
        ws.send_text(json.dumps({'type': 'ping'}))
        assert ws.receive_json() == {'type': 'pong'}

        bridge.omi.action_rows = [{'description': 'still working'}]
        ws.send_text(json.dumps({'type': 'action_items'}))
        assert ws.receive_json()['items'] == [{'description': 'still working', 'completed': False}]


def test_a_malformed_limit_is_an_error_frame_not_a_dropped_socket(bridge):
    with bridge.client.websocket_connect('/app') as ws:
        ws.receive_json()
        ws.send_text(json.dumps({'type': 'memories', 'limit': 'twenty'}))
        assert ws.receive_json()['type'] == 'error'
        ws.send_text(json.dumps({'type': 'ping'}))
        assert ws.receive_json() == {'type': 'pong'}


def test_a_chat_stream_failure_is_isolated_too(bridge):
    bridge.omi.stream_exc = RuntimeError('stream died')
    with bridge.client.websocket_connect('/app') as ws:
        ws.receive_json()
        ws.send_text(json.dumps({'type': 'chat', 'text': 'hi'}))
        assert ws.receive_json()['type'] == 'error'
        ws.send_text(json.dumps({'type': 'ping'}))
        assert ws.receive_json() == {'type': 'pong'}


# --------------------------------------------------------------------------
# Proactive push
# --------------------------------------------------------------------------


class RecordingSocket:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.got = asyncio.Event()

    async def send_text(self, raw: str) -> None:
        self.sent.append(json.loads(raw))
        self.got.set()


@pytest.mark.asyncio
async def test_broadcast_survives_a_dead_client(monkeypatch):
    class Dead:
        async def send_text(self, raw):
            raise RuntimeError('socket closed')

    alive = RecordingSocket()
    monkeypatch.setattr(server, '_clients', {Dead(), alive})
    await server.broadcast({'type': 'push', 'text': 'hi'})
    assert alive.sent == [{'type': 'push', 'text': 'hi'}]


@pytest.mark.asyncio
async def test_the_push_loop_seeds_on_the_first_pass_and_skips_completed(monkeypatch):
    """Without seeding, connecting the app pushes every existing action item at
    once. Completed items must never surface at all.
    """
    monkeypatch.setenv('OMI_EVEN_PUSH_INTERVAL', '0.01')

    polls = 0

    class Omi:
        async def action_items(self, limit=20):
            nonlocal polls
            polls += 1
            if polls == 1:
                return [{'id': 'existing', 'description': 'was already here'}]
            return [
                {'id': 'existing', 'description': 'was already here'},
                {'id': 'done', 'description': 'already finished', 'completed': True},
                {'id': 'new', 'description': 'File the **regression**'},
            ]

    socket = RecordingSocket()
    monkeypatch.setattr(server, 'omi', Omi())
    monkeypatch.setattr(server, '_clients', {socket})

    task = asyncio.create_task(server._push_loop())
    try:
        await asyncio.wait_for(socket.got.wait(), timeout=5)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert len(socket.sent) == 1, f'expected exactly one push, got {socket.sent}'
    assert socket.sent[0] == {'type': 'push', 'text': 'New task: File the regression'}


@pytest.mark.asyncio
async def test_the_push_loop_survives_a_failing_poll(monkeypatch):
    monkeypatch.setenv('OMI_EVEN_PUSH_INTERVAL', '0.01')
    calls = 0

    class Omi:
        async def action_items(self, limit=20):
            nonlocal calls
            calls += 1
            raise RuntimeError('omi is down')

    monkeypatch.setattr(server, 'omi', Omi())
    monkeypatch.setattr(server, '_clients', {RecordingSocket()})

    task = asyncio.create_task(server._push_loop())
    try:
        while calls < 3:
            await asyncio.sleep(0.01)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert calls >= 3, 'a poll failure must not end the loop'


@pytest.mark.asyncio
async def test_the_push_loop_does_not_poll_without_a_connected_app(monkeypatch):
    monkeypatch.setenv('OMI_EVEN_PUSH_INTERVAL', '0.01')
    calls = 0

    class Omi:
        async def action_items(self, limit=20):
            nonlocal calls
            calls += 1
            return []

    monkeypatch.setattr(server, 'omi', Omi())
    monkeypatch.setattr(server, '_clients', set())

    task = asyncio.create_task(server._push_loop())
    await asyncio.sleep(0.06)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert calls == 0

"""Local HTTP provider responses shared by the Python and Go replay drivers."""

from contextlib import contextmanager
from functools import lru_cache
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import socket
from threading import Lock, Thread
from unittest.mock import patch
from urllib.parse import urlsplit

_IDEMPOTENCY_KEY = re.compile(r'[A-Za-z0-9._:-]{1,128}')


@lru_cache(maxsize=1)
def _encoding():
    import tiktoken

    return tiktoken.get_encoding('cl100k_base')


def _tokens(text):
    return len(_encoding().encode_ordinary(text))


def _message_tokens(message):
    content = message.get('content')
    if isinstance(content, list):
        if any(part.get('type') != 'text' for part in content):
            raise ValueError('unsupported replay message content')
        content = ''.join(part['text'] for part in content)
    count = _tokens(content or '')
    if message.get('tool_calls'):
        count += _tokens(json.dumps(message['tool_calls'], ensure_ascii=False, sort_keys=True))
    return count


def _embeddings(values):
    if isinstance(values, str):
        values = [values]
    if values and all(type(value) is int for value in values):
        values = [values]
    return values, sum(_tokens(value) if isinstance(value, str) else len(value) for value in values)


def _record_tokens(state, feature, prompt, completion, *, embedding=False):
    # Store usage only. Never retain prompt contents in the replay report.
    calls = vars(state).setdefault('replay_token_calls', [])
    calls.append({'feature': feature, 'input': prompt, 'output': completion, 'embedding': embedding})


def response(state, feature):
    defaults = {
        'conv-structure': state.notes,
        'memory-l1': {
            'items': [
                {'text': text, 'archive_class': 'general', 'evidence_quotes': [text], 'confidence': 'high'}
                for text in state.memories
            ]
        },
        'conv-discard': {'discard': False},
        'conv-folder': {'folder_id': 'replay-folder', 'confidence': 0.95, 'reasoning': 'Synthetic planning'},
        'conv-app-result': 'Synthetic app summary.',
        'memory-l2': {'decisions': []},
        'memories': {'memories': []},
        'chat-extraction': {'people': [], 'topics': [], 'entities': [], 'dates': []},
        'goals': [{'goal_id': 'replay-goal', 'found': True, 'value': 2, 'reasoning': 'Two agendas reviewed.'}],
    }
    return state.case.get('responses', {}).get(feature, defaults.get(feature))


@contextmanager
def provider_server():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format, *_args):
            pass

        def _reply(self, status, result, key=None):
            raw = json.dumps(result).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            if key:
                self.send_header('X-Omi-Idempotency-Key', key.replace('\r', '').replace('\n', ''))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            prefix = '/v1/chat/completions/operations/'
            key = self.path.removeprefix(prefix)
            if self.path.startswith(prefix) and _IDEMPOTENCY_KEY.fullmatch(key) and key in self.server.operations:
                _, result = self.server.operations[key]
                self._reply(200, result, key)
                return
            self._reply(404, {'error': {'code': 'idempotency_not_found'}})

        def do_POST(self):
            key = None
            try:
                path = urlsplit(self.path).path
                request_key = self.headers.get('Idempotency-Key')
                if path == '/v1/chat/completions' and request_key is not None:
                    self._reply(400, {'error': {'code': 'idempotency_operations_route_required'}})
                    return
                if request_key is not None and not _IDEMPOTENCY_KEY.fullmatch(request_key):
                    raise ValueError('invalid replay operation identity')
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if path == '/internal/finalization/sync-reference' and self.server.reference is not None:
                    response_status, result = self.server.reference(body, self.headers)
                    self._reply(response_status, result)
                    return
                if path == '/v1/chat/completions/operations':
                    key = request_key
                    if not key:
                        raise ValueError('missing replay operation identity')
                    canonical = json.dumps(body, sort_keys=True, separators=(',', ':'), allow_nan=False)
                    with self.server.operation_lock:
                        if key not in self.server.operations:
                            result = self.server.dispatch('/v1/chat/completions', body, self.headers)
                            self.server.operations[key] = canonical, result
                        committed_request, result = self.server.operations[key]
                    if canonical != committed_request:
                        self._reply(409, {'error': {'code': 'idempotency_conflict'}})
                        return
                else:
                    result = self.server.dispatch(path, body, self.headers)
                status = 503 if path == f"/receive/{self.server.state.case.get('unavailable_app')}" else 200
            except Exception as error:
                self.server.errors.append(type(error).__name__)
                result, status = {'error': {'message': 'unknown replay provider request'}}, 400
            self._reply(status, result, key if status == 200 else None)

    with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
        server.errors = []
        server.operations = {}
        server.operation_lock = Lock()
        server.reference = None

        def dispatch(path, body, headers):
            state = server.state
            if path.startswith('/receive/'):
                key = headers.get('X-Omi-Idempotency-Key') or headers.get('Idempotency-Key')
                state.webhook(path.removeprefix('/receive/'), key, body)
                return {}
            if path == '/v1/embeddings':
                feature = body['model'].removeprefix('omi:auto:')
                values, prompt = _embeddings(body['input'])
                state.record_embedding_request(values)
                _record_tokens(state, feature, prompt, 0, embedding=True)
                return {
                    'object': 'list',
                    'data': [
                        {'object': 'embedding', 'index': i, 'embedding': [0.125, 0.25, 0.5]}
                        for i, _ in enumerate(values)
                    ],
                    'usage': {'prompt_tokens': prompt, 'total_tokens': prompt},
                }
            if path != '/v1/chat/completions':
                raise ValueError('unknown replay gateway endpoint')
            feature = body['model'].removeprefix('omi:auto:')
            fixture = response(state, feature)
            if fixture is None:
                raise ValueError('missing replay response')
            if feature == 'conv-structure' and hasattr(state, 'notes_prompt_hashes'):
                messages = []
                for message in body.get('messages', []):
                    content = message['content']
                    if isinstance(content, list) and all(
                        isinstance(part, dict) and part.keys() == {'type', 'text'} and part['type'] == 'text'
                        for part in content
                    ):
                        # Transport wrappers encode text parts or the same bare string.
                        content = ''.join(part['text'] for part in content)
                    messages.append({'role': message['role'], 'text': content})
                state.notes_prompt_hashes.append(sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest())
            completion = fixture if isinstance(fixture, str) else json.dumps(fixture)
            prompt_tokens = sum(_message_tokens(message) for message in body['messages'])
            if body.get('tools'):
                prompt_tokens += _tokens(json.dumps(body['tools'], ensure_ascii=False, sort_keys=True))
            completion_tokens = _tokens(completion)
            state.record_provider_call(feature, body.get('messages', []), completion)
            _record_tokens(state, feature, prompt_tokens, completion_tokens)
            return {
                'id': 'replay-response',
                'object': 'chat.completion',
                'created': 1,
                'model': body['model'],
                'choices': [
                    {
                        'index': 0,
                        'finish_reason': 'stop',
                        'message': {
                            'role': 'assistant',
                            'content': completion,
                        },
                    }
                ],
                'usage': {
                    'prompt_tokens': prompt_tokens,
                    'completion_tokens': completion_tokens,
                    'total_tokens': prompt_tokens + completion_tokens,
                },
            }

        server.dispatch = dispatch
        thread = Thread(target=server.serve_forever)
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            thread.join()


@contextmanager
def allow_provider_port(port, connect, connect_ex):
    """Extend the existing network guard by exactly the owned server address."""
    guarded_connect, guarded_connect_ex = socket.socket.connect, socket.socket.connect_ex

    def allow(original, guarded):
        def call(sock, address):
            return (original if address == ('127.0.0.1', port) else guarded)(sock, address)

        return call

    with patch.object(socket.socket, 'connect', allow(connect, guarded_connect)), patch.object(
        socket.socket, 'connect_ex', allow(connect_ex, guarded_connect_ex)
    ):
        yield

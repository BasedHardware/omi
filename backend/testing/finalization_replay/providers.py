"""Local HTTP provider responses shared by the Python and Go replay drivers."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
from threading import Thread
from unittest.mock import patch
from urllib.parse import urlsplit


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

        def do_POST(self):
            try:
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                path = urlsplit(self.path).path
                result = self.server.dispatch(path, body, self.headers)
                status = 503 if path == f"/receive/{self.server.state.case.get('unavailable_app')}" else 200
            except Exception as error:
                self.server.errors.append(type(error).__name__)
                result, status = {'error': {'message': 'unknown replay provider request'}}, 400
            raw = json.dumps(result).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
        server.errors = []

        def dispatch(path, body, headers):
            state = server.state
            if path.startswith('/receive/'):
                key = headers.get('X-Omi-Idempotency-Key') or headers.get('Idempotency-Key')
                state.webhook(path.removeprefix('/receive/'), key, body)
                return {}
            if path == '/v1/embeddings':
                state.record_embedding_request(body.get('input', []))
                return {
                    'object': 'list',
                    'data': [
                        {'object': 'embedding', 'index': i, 'embedding': [0.125, 0.25, 0.5]}
                        for i, _ in enumerate(body['input'])
                    ],
                }
            if path != '/v1/chat/completions':
                raise ValueError('unknown replay gateway endpoint')
            feature = body['model'].removeprefix('omi:auto:')
            fixture = response(state, feature)
            if fixture is None:
                raise ValueError('missing replay response')
            completion = fixture if isinstance(fixture, str) else json.dumps(fixture, ensure_ascii=False)
            prompt_tokens, completion_tokens = state.record_provider_call(feature, body.get('messages', []), completion)
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
                            'content': fixture if isinstance(fixture, str) else json.dumps(fixture),
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

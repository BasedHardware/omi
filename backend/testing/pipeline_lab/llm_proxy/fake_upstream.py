"""A scripted, schema-driven fake LLM gateway for hermetic tests and the local-stack smoke.

It stands where the real gateway would sit *behind* the lab proxy, so the proxy's keying,
pricing, cap and call log are the real code. No model runs and nothing leaves the host.

Answers, deterministically from the request body:

- ``POST /v1/chat/completions`` (JSON or SSE when ``stream`` is set). When the request
  asks for structure (``response_format.json_schema``, ``tools``/``functions``, or a
  LangChain "conforms to the JSON schema below" block in the prompt) the reply is the
  smallest instance of that schema, with strings seeded from the last user message so
  different conversations get different titles. Otherwise a short text reply. Random
  UUIDs (version 4) in that message are renamed ``uuid4#1``, ``uuid4#2``, ... in first-seen
  order before seeding, the rule ``determinism.py`` applies to run artifacts: a prompt that
  cites random ids the product minted (transcript segment ids, for one) gets the same answer
  on every repeat.
- ``POST /v1/messages`` (Anthropic shape), the same rules, ``tool_use`` when tools are given.
- ``POST /v1/embeddings``: unit vectors from a hash of each input (``dimensions`` or 3072).
- ``POST /v1/systemone`` with a Jev decision body (``state`` and ``questions``, ``utils/llm/jev_client.py``):
  every ``noul`` question answers 1.0 (true) and every ``choice`` question puts all its probability on its
  first option. The one Jev lane today asks ``worth_keeping``, so the fake keeps, as the chat fake answers
  ``discard: false``. A 2xx answer is what lets the proxy cache the call; before this route the fake
  answered 404, the proxy caches only 2xx, so ``jev_conversation_relevance`` missed on every identical
  re-run. Other ``/v1/systemone`` bodies (gateway prefilter steps) still get 404.

Usage counts are reported so the proxy prices the call. ``FakeUpstream(...).start()`` runs
it on a loopback thread; ``python -m testing.pipeline_lab.llm_proxy.fake_upstream --port N``
runs it in the foreground.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional

DEFAULT_DIMENSIONS = 3072


def _schema_block(text: str) -> str | None:
    """The first fenced ```json {...}``` block's object, found by a linear scan (no regex backtracking)."""
    at = 0
    while (start := text.find('```', at)) >= 0:
        end = text.find('```', start + 3)
        if end < 0:
            return None
        inner = text[start + 3 : end]
        if inner.startswith('json'):
            inner = inner[4:]
        inner = inner.strip()
        if inner.startswith('{') and inner.endswith('}'):
            return inner
        at = end + 3
    return None


_WORD = re.compile(r"[A-Za-z][A-Za-z'-]+")
# The same pattern as ``determinism._UUID4``: the ids the repeat comparison renames.
_UUID4 = re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b')


def _stable_ids(text: str) -> str:
    """``text`` with every random UUID renamed ``uuid4#n`` in first-seen order (the same id, the same name)."""
    names: dict[str, str] = {}
    return _UUID4.sub(lambda match: names.setdefault(match.group(0), f'uuid4#{len(names) + 1}'), text)


def _words(text: str) -> list[str]:
    return _WORD.findall(text or '')


def _seed_text(messages: list[Any]) -> str:
    for message in reversed(messages or []):
        if not isinstance(message, dict) or message.get('role') not in ('user', None):
            continue
        content = message.get('content')
        if isinstance(content, list):
            content = ' '.join(str(part.get('text') or '') for part in content if isinstance(part, dict))
        if content:
            return _stable_ids(str(content))
    return 'synthetic conversation'


def _prompt_text(messages: list[Any]) -> str:
    parts = []
    for message in messages or []:
        content = message.get('content') if isinstance(message, dict) else None
        if isinstance(content, list):
            content = ' '.join(str(part.get('text') or '') for part in content if isinstance(part, dict))
        parts.append(str(content or ''))
    return '\n'.join(parts)


def synthesize(schema: Any, seed: str, name: str = '', defs: Optional[dict] = None, depth: int = 0) -> Any:
    """The smallest value matching ``schema``; strings are short phrases from ``seed``."""
    defs = defs if defs is not None else (schema.get('$defs') or schema.get('definitions') or {})
    if not isinstance(schema, dict) or depth > 8:
        return None
    if '$ref' in schema:
        ref = str(schema['$ref']).split('/')[-1]
        return synthesize(defs.get(ref, {}), seed, name, defs, depth + 1)
    for key in ('anyOf', 'oneOf', 'allOf'):
        if schema.get(key):
            options = [o for o in schema[key] if isinstance(o, dict) and o.get('type') != 'null'] or schema[key]
            return synthesize(options[0], seed, name, defs, depth + 1)
    if 'enum' in schema and schema['enum']:
        return schema['enum'][0]
    if 'const' in schema:
        return schema['const']
    kind = schema.get('type')
    if isinstance(kind, list):
        kind = next((k for k in kind if k != 'null'), 'string')
    if kind == 'object' or 'properties' in schema:
        props = schema.get('properties') or {}
        return {key: synthesize(value, seed, key, defs, depth + 1) for key, value in props.items()}
    if kind == 'array':
        lowered = name.lower()
        # Keep lists that create side effects short; one item exercises the path.
        if any(word in lowered for word in ('memor', 'action', 'task', 'event', 'item', 'fact')):
            count = 1
        else:
            count = 0
        return [
            synthesize(schema.get('items') or {'type': 'string'}, seed, name, defs, depth + 1) for _ in range(count)
        ]
    if kind == 'boolean':
        return False
    if kind == 'integer':
        return int(schema.get('minimum') or 0)
    if kind == 'number':
        return float(schema.get('minimum') or 0.0)
    words = _words(seed) or ['synthetic']
    digest = int(hashlib.sha256(f'{name}\x00{seed}'.encode()).hexdigest(), 16)
    start = digest % max(1, len(words))
    phrase = ' '.join(words[start : start + 6] or words[:6])
    lowered = name.lower()
    if 'emoji' in lowered:
        return '🧪'
    if 'category' in lowered:
        return 'other'
    if 'language' in lowered:
        return 'en'
    if lowered.endswith('_at') or 'date' in lowered or 'time' in lowered:
        return None if schema.get('type') != 'string' else '2026-01-01T00:00:00Z'
    if 'title' in lowered:
        return phrase.title()[:80]
    return f'Synthetic {name or "text"}: {phrase}.'


def _schema_from_request(body: dict[str, Any]) -> tuple[Optional[dict], Optional[str], str]:
    """(schema, tool name, mode) where mode is ``json`` | ``tool`` | ``text``."""
    response_format = body.get('response_format') or {}
    if isinstance(response_format, dict) and response_format.get('type') == 'json_schema':
        spec = response_format.get('json_schema') or {}
        return spec.get('schema') or {}, None, 'json'
    tools = body.get('tools') or []
    if tools:
        first = tools[0]
        function = first.get('function') if isinstance(first, dict) and 'function' in first else first
        schema = function.get('parameters') or function.get('input_schema') or {}
        return schema, function.get('name') or 'tool', 'tool'
    if body.get('functions'):
        function = body['functions'][0]
        return function.get('parameters') or {}, function.get('name') or 'tool', 'function'
    block = _schema_block(_prompt_text(body.get('messages') or []) + str(body.get('system') or ''))
    if block is not None:
        try:
            schema = json.loads(block)
        except json.JSONDecodeError:
            schema = None
        if isinstance(schema, dict) and ('properties' in schema or '$defs' in schema):
            return schema, None, 'json'
    if isinstance(response_format, dict) and response_format.get('type') == 'json_object':
        return {'type': 'object', 'properties': {}}, None, 'json'
    return None, None, 'text'


V3_OUTLINE_MARK = "You outline one stretch of a person's day"
V3_SHORT_TASKS_MARK = 'Return JSON {"action_items": [...]}'
_OUTLINE_LINE = re.compile(r'^\[L(\d+) \d\d:\d\d\] [^:]+: (.*)$', re.MULTILINE)
TOPIC_SWITCH = 'switching topics'


def scripted_reply(prompt: str) -> Optional[str]:
    """Answers for prompts whose reply format is fixed by product code rather than a schema.

    - the conversations-v3 outline (``utils/conversations/v3/outline.SYSTEM_PROMPT``): one
      conversation per stretch, plus a new one at every line containing ``switching topics``
      (so tests can force a split), titled from the line's words;
    - v3 short-clip tasks (``models.short_tasks``): ``{"action_items": []}``.
    """
    if V3_OUTLINE_MARK in prompt:
        lines = [(int(n), text) for n, text in _OUTLINE_LINE.findall(prompt)]
        firsts = [1] + [n for n, text in lines if n > 1 and TOPIC_SWITCH in text.lower()]
        conversations = []
        for first in firsts:
            text = next((t for n, t in lines if n == first), 'synthetic stretch')
            title = ' '.join(_words(text)[:5]).title() or 'Synthetic Stretch'
            conversations.append(
                {
                    'first_line': first,
                    'title': title,
                    'line': f'You talked about {title.lower()}.',
                    'kind': 'conversation',
                    'people': [],
                    'emoji': '🧪',
                    'sections': [{'first_line': first, 'title': title}],
                    'resumes_previous': False,
                }
            )
        return json.dumps({'conversations': conversations})
    if V3_SHORT_TASKS_MARK in prompt:
        return json.dumps({'action_items': []})
    return None


def _tokens(text: str) -> int:
    return max(1, len(text) // 4)


def embedding(text: str, dimensions: int) -> list[float]:
    raw = hashlib.sha256(text.encode('utf-8')).digest()
    values = [((raw[i % len(raw)] + i * 31) % 255) / 127.0 - 1.0 for i in range(dimensions)]
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [round(v / norm, 6) for v in values]


class _Handler(BaseHTTPRequestHandler):
    server_version = 'pipeline-lab-fake-upstream/1'

    def log_message(self, *args: Any) -> None:  # quiet
        return

    def _send(self, status: int, payload: Any) -> None:
        body = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip('/') in ('/health', '/_lab/health'):
            self._send(200, {'ok': True})
            return
        self._send(404, {'error': 'not found'})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get('Content-Length') or 0)
        try:
            body = json.loads(self.rfile.read(length) or b'{}')
        except json.JSONDecodeError:
            self._send(400, {'error': 'bad json'})
            return
        self.server.requests.append({'path': self.path, 'headers': {k.lower(): v for k, v in self.headers.items()}})  # type: ignore[attr-defined]
        path = self.path.split('?')[0].rstrip('/')
        if path.endswith('/embeddings'):
            self._embeddings(body)
        elif path.endswith('/chat/completions'):
            self._chat(body)
        elif path.endswith('/messages'):
            self._anthropic(body)
        elif path.endswith('/systemone') and isinstance(body.get('questions'), dict) and 'state' in body:
            self._jev(body)
        else:
            self._send(404, {'error': 'fake upstream: unsupported path'})

    def _jev(self, body: dict[str, Any]) -> None:
        answers: dict[str, Any] = {}
        for name, question in body['questions'].items():
            kind = question.get('type') if isinstance(question, dict) else None
            if kind == 'choice':
                options = question.get('options') or question.get('choices') or []
                options = list(options.keys() if isinstance(options, dict) else options)
                answers[name] = {'probabilities': {str(o): (1.0 if i == 0 else 0.0) for i, o in enumerate(options)}}
            else:
                answers[name] = {'noul': 1.0}
        prompt_tokens = _tokens(str(body.get('state') or '')) + _tokens(json.dumps(body['questions']))
        self._send(
            200,
            {'answers': answers, 'usage': {'prompt_tokens': prompt_tokens, 'completion_tokens': len(answers)}},
        )

    def _embeddings(self, body: dict[str, Any]) -> None:
        inputs = body.get('input')
        items = inputs if isinstance(inputs, list) else [inputs]
        dims = int(body.get('dimensions') or self.server.dimensions)  # type: ignore[attr-defined]
        data = [
            {'object': 'embedding', 'index': i, 'embedding': embedding(str(text), dims)} for i, text in enumerate(items)
        ]
        tokens = sum(_tokens(str(text)) for text in items)
        self._send(
            200,
            {
                'object': 'list',
                'data': data,
                'model': body.get('model') or 'fake-embedding',
                'usage': {'prompt_tokens': tokens, 'total_tokens': tokens},
            },
        )

    def _reply(self, body: dict[str, Any]) -> tuple[str, Optional[str], str]:
        messages = body.get('messages') or []
        scripted = scripted_reply(_prompt_text(messages) + str(body.get('system') or ''))
        if scripted is not None:
            return scripted, None, 'json'
        schema, tool, mode = _schema_from_request(body)
        seed = _seed_text(messages)
        if mode == 'text':
            return f'Synthetic reply about {" ".join(_words(seed)[:8]) or "the conversation"}.', None, mode
        return json.dumps(synthesize(schema or {}, seed)), tool, mode

    def _chat(self, body: dict[str, Any]) -> None:
        text, tool, mode = self._reply(body)
        prompt_tokens = _tokens(_prompt_text(body.get('messages') or []))
        usage = {
            'prompt_tokens': prompt_tokens,
            'completion_tokens': _tokens(text),
            'total_tokens': prompt_tokens + _tokens(text),
        }
        model = body.get('model') or 'fake-model'
        message: dict[str, Any] = {'role': 'assistant', 'content': text}
        finish = 'stop'
        if mode == 'tool':
            message = {
                'role': 'assistant',
                'content': None,
                'tool_calls': [
                    {'id': 'call_fake_1', 'type': 'function', 'function': {'name': tool, 'arguments': text}}
                ],
            }
            finish = 'tool_calls'
        elif mode == 'function':
            message = {'role': 'assistant', 'content': None, 'function_call': {'name': tool, 'arguments': text}}
            finish = 'function_call'
        if body.get('stream'):
            self._stream(model, message, finish, usage)
            return
        self._send(
            200,
            {
                'id': 'chatcmpl-fake',
                'object': 'chat.completion',
                'created': 0,
                'model': model,
                'choices': [{'index': 0, 'message': message, 'finish_reason': finish}],
                'usage': usage,
            },
        )

    def _stream(self, model: str, message: dict[str, Any], finish: str, usage: dict[str, int]) -> None:
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        delta = {k: v for k, v in message.items() if v is not None}
        if 'tool_calls' in delta:
            delta['tool_calls'] = [{'index': 0, **delta['tool_calls'][0]}]
        chunks = [
            {'choices': [{'index': 0, 'delta': delta, 'finish_reason': None}]},
            {'choices': [{'index': 0, 'delta': {}, 'finish_reason': finish}]},
            {'choices': [], 'usage': usage},
        ]
        for chunk in chunks:
            payload = {'id': 'chatcmpl-fake', 'object': 'chat.completion.chunk', 'created': 0, 'model': model, **chunk}
            self.wfile.write(f'data: {json.dumps(payload)}\n\n'.encode())
        self.wfile.write(b'data: [DONE]\n\n')
        self.wfile.flush()

    def _anthropic(self, body: dict[str, Any]) -> None:
        text, tool, mode = self._reply(body)
        prompt_tokens = _tokens(_prompt_text(body.get('messages') or []) + str(body.get('system') or ''))
        if mode in ('tool', 'function'):
            content = [{'type': 'tool_use', 'id': 'toolu_fake_1', 'name': tool, 'input': json.loads(text)}]
            stop = 'tool_use'
        else:
            content = [{'type': 'text', 'text': text}]
            stop = 'end_turn'
        self._send(
            200,
            {
                'id': 'msg_fake',
                'type': 'message',
                'role': 'assistant',
                'model': body.get('model') or 'fake-model',
                'content': content,
                'stop_reason': stop,
                'usage': {'input_tokens': prompt_tokens, 'output_tokens': _tokens(text)},
            },
        )


class FakeUpstream:
    """Loopback fake gateway. ``start()`` returns self; ``url``; ``stop()``. ``requests`` logs path + headers."""

    def __init__(self, port: int = 0, *, dimensions: int = DEFAULT_DIMENSIONS):
        self._server = ThreadingHTTPServer(('127.0.0.1', port), _Handler)
        self._server.daemon_threads = True
        self._server.requests = []  # type: ignore[attr-defined]
        self._server.dimensions = dimensions  # type: ignore[attr-defined]
        self._thread: Optional[threading.Thread] = None

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f'http://{host}:{port}'

    @property
    def requests(self) -> list[dict[str, Any]]:
        return self._server.requests  # type: ignore[attr-defined]

    def start(self) -> 'FakeUpstream':
        self._thread = threading.Thread(target=self._server.serve_forever, name='lab-fake-upstream', daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m testing.pipeline_lab.llm_proxy.fake_upstream')
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--dimensions', type=int, default=DEFAULT_DIMENSIONS)
    args = parser.parse_args(argv)
    upstream = FakeUpstream(args.port, dimensions=args.dimensions)
    print(json.dumps({'listening': upstream.url}), flush=True)
    try:
        upstream._server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        upstream._server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

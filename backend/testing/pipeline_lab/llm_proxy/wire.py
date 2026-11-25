"""Request keys, usage parsing and pricing for the lab LLM proxy. Stdlib only, no I/O.

What the backend sends through ``OMI_LLM_GATEWAY_URL`` (read at origin/main):

- ``POST /v1/chat/completions``: raw httpx (``utils/llm/gateway_client.py``),
  LangChain/OpenAI SDK (``utils/llm/providers.py``, ``base_url=<gateway>/v1``)
  with ``stream`` true (SSE, ``stream_options.include_usage``) or false;
- ``POST /v1/messages``: the Anthropic SDK pointed at the gateway (``gateway_anthropic.py``), SSE or JSON;
- ``POST /v1/embeddings``, ``/v1/images/generations``, ``/v1/systemone``.

The proxy is path-agnostic: any POST is keyed, cached and priced the same way;
the parsers below only extract usage and a readable output for the call log.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from testing.pipeline_lab.contracts import canonical_json

# Request fields that never change the model's answer but do change per process/run.
DEFAULT_IGNORED_FIELDS = ('user', 'prompt_cache_key', 'safety_identifier', 'metadata')
# Request headers that select behaviour upstream and therefore belong in the key.
KEYED_HEADERS = ('x-omi-llm-feature', 'anthropic-version', 'anthropic-beta')


def request_key(
    method: str,
    path: str,
    body: bytes,
    headers: Mapping[str, str],
    ignored_fields: tuple[str, ...] = DEFAULT_IGNORED_FIELDS,
) -> str:
    """sha256 of the canonical request: method, path, JSON body minus ignored fields, keyed headers."""
    lowered = {k.lower(): v for k, v in headers.items()}
    parsed = parse_json(body)
    if isinstance(parsed, dict):
        body_material: Any = {k: v for k, v in parsed.items() if k not in ignored_fields}
    else:
        body_material = {'raw_sha256': hashlib.sha256(body).hexdigest()}
    material = {
        'method': method.upper(),
        'path': path,
        'body': body_material,
        'headers': {name: lowered[name] for name in KEYED_HEADERS if name in lowered},
    }
    return hashlib.sha256(canonical_json(material).encode('utf-8')).hexdigest()


def parse_json(body: bytes) -> Any:
    try:
        return json.loads(body.decode('utf-8')) if body else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def is_stream_request(body: Any) -> bool:
    return isinstance(body, dict) and body.get('stream') is True


def prompt_view(body: Any) -> Any:
    """What the call log keeps as ``prompt``: messages/system/input, not tool schemas or vectors."""
    if not isinstance(body, dict):
        return None
    view: dict[str, Any] = {}
    for name in ('system', 'messages', 'input', 'prompt'):
        if name in body:
            view[name] = body[name]
    if 'tools' in body:
        view['tools'] = [_tool_name(tool) for tool in body.get('tools') or []]
    if 'response_format' in body:
        view['response_format'] = (body.get('response_format') or {}).get('type')
    return view or None


def _tool_name(tool: Any) -> Any:
    if isinstance(tool, dict):
        return tool.get('name') or (tool.get('function') or {}).get('name') or tool.get('type')
    return None


@dataclass
class Usage:
    model: Optional[str] = None
    tokens_in: int = 0
    tokens_cached: int = 0
    tokens_out: int = 0
    output: Any = None
    known: bool = False  # usage was present in the response
    tool_calls: list[Any] = field(default_factory=list)


def iter_sse_data(body: bytes):
    for raw in body.decode('utf-8', errors='replace').splitlines():
        line = raw.strip()
        if not line.startswith('data:'):
            continue
        data = line[5:].strip()
        if not data or data == '[DONE]':
            continue
        try:
            yield json.loads(data)
        except json.JSONDecodeError:
            continue


def parse_usage(body: bytes, stream: bool) -> Usage:
    usage = Usage()
    if stream:
        text: list[str] = []
        for event in iter_sse_data(body):
            _absorb_stream_event(event, usage, text)
        usage.output = ''.join(text) if text or not usage.tool_calls else None
        if usage.tool_calls and usage.output is None:
            usage.output = {'tool_calls': usage.tool_calls}
        return usage
    parsed = parse_json(body)
    if not isinstance(parsed, dict):
        return usage
    usage.model = parsed.get('model')
    raw = parsed.get('usage') or {}
    if isinstance(raw, dict) and raw:
        _absorb_usage(raw, usage)
    if 'choices' in parsed:  # OpenAI chat completions
        outputs = []
        for choice in parsed.get('choices') or []:
            message = choice.get('message') or {}
            if message.get('tool_calls'):
                outputs.append({'content': message.get('content'), 'tool_calls': message['tool_calls']})
            else:
                outputs.append(message.get('content'))
        usage.output = outputs[0] if len(outputs) == 1 else outputs
    elif parsed.get('type') == 'message' or 'content' in parsed:  # Anthropic messages
        blocks = parsed.get('content') or []
        texts = [b.get('text', '') for b in blocks if isinstance(b, dict) and b.get('type') == 'text']
        tools = [b for b in blocks if isinstance(b, dict) and b.get('type') == 'tool_use']
        usage.output = ''.join(texts) if not tools else {'text': ''.join(texts), 'tool_use': tools}
    elif isinstance(parsed.get('data'), list):  # embeddings / images: never log vectors
        first = parsed['data'][0] if parsed['data'] else {}
        dims = len(first.get('embedding') or []) if isinstance(first, dict) else 0
        usage.output = {'items': len(parsed['data']), 'dims': dims}
    return usage


def _absorb_usage(raw: Mapping[str, Any], usage: Usage) -> None:
    usage.known = True
    if 'prompt_tokens' in raw or 'completion_tokens' in raw:  # OpenAI-shaped
        usage.tokens_in = int(raw.get('prompt_tokens') or 0)
        usage.tokens_out = int(raw.get('completion_tokens') or 0)
        details = raw.get('prompt_tokens_details') or {}
        usage.tokens_cached = min(usage.tokens_in, int(details.get('cached_tokens') or 0))
        return
    # Anthropic-shaped: input_tokens excludes cache reads/writes.
    if 'input_tokens' in raw:
        cache_read = int(raw.get('cache_read_input_tokens') or 0)
        usage.tokens_in = (
            int(raw.get('input_tokens') or 0) + cache_read + int(raw.get('cache_creation_input_tokens') or 0)
        )
        usage.tokens_cached = cache_read
    if 'output_tokens' in raw:
        usage.tokens_out = int(raw.get('output_tokens') or 0)
    if 'total_tokens' in raw and not usage.tokens_in:
        usage.tokens_in = int(raw.get('total_tokens') or 0)


def _absorb_stream_event(event: Any, usage: Usage, text: list[str]) -> None:
    if not isinstance(event, dict):
        return
    kind = event.get('type')
    if kind == 'message_start':  # Anthropic
        message = event.get('message') or {}
        usage.model = message.get('model') or usage.model
        if message.get('usage'):
            _absorb_usage(message['usage'], usage)
        return
    if kind == 'content_block_delta':
        delta = event.get('delta') or {}
        if delta.get('type') == 'text_delta':
            text.append(delta.get('text') or '')
        elif delta.get('type') == 'input_json_delta':
            usage.tool_calls.append(delta.get('partial_json'))
        return
    if kind == 'message_delta':
        raw = event.get('usage') or {}
        if 'output_tokens' in raw:
            usage.known = True
            usage.tokens_out = int(raw['output_tokens'])
        return
    # OpenAI chat.completion.chunk
    usage.model = event.get('model') or usage.model
    for choice in event.get('choices') or []:
        delta = choice.get('delta') or {}
        if delta.get('content'):
            text.append(delta['content'])
        if delta.get('tool_calls'):
            usage.tool_calls.extend(delta['tool_calls'])
    if event.get('usage'):
        _absorb_usage(event['usage'], usage)


@dataclass
class PriceTable:
    """USD per million tokens. Estimates for the cap; the gateway rate card is authoritative.

    ``by_model`` maps a substring of the response model to ``[in, out]``; the
    first match wins, else the default. Cached input is billed at ``cached_factor``.
    """

    default_in: float = 0.10
    default_out: float = 0.60
    cached_factor: float = 0.10
    by_model: dict[str, tuple[float, float]] = field(default_factory=lambda: {'embedding': (0.02, 0.0)})
    default_max_output_tokens: int = 8192
    cushion_usd: float = 0.01

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> 'PriceTable':
        table = cls()
        for name in ('default_in', 'default_out', 'cached_factor', 'cushion_usd'):
            if name in data:
                setattr(table, name, float(data[name]))
        if 'default_max_output_tokens' in data:
            table.default_max_output_tokens = int(data['default_max_output_tokens'])
        if 'by_model' in data:
            table.by_model = {str(k): (float(v[0]), float(v[1])) for k, v in data['by_model'].items()}
        return table

    def rates(self, model: Optional[str]) -> tuple[float, float]:
        for marker, rates in self.by_model.items():
            if model and marker in model:
                return rates
        return self.default_in, self.default_out

    def cost(self, usage: Usage) -> float:
        rate_in, rate_out = self.rates(usage.model)
        fresh = max(0, usage.tokens_in - usage.tokens_cached)
        return (
            fresh * rate_in + usage.tokens_cached * rate_in * self.cached_factor + usage.tokens_out * rate_out
        ) / 1e6

    def reservation(self, path: str, body: Any, body_bytes: int) -> float:
        """Worst case before sending: ~3 bytes per input token, the request's output ceiling."""
        model = body.get('model') if isinstance(body, dict) else None
        rate_in, rate_out = self.rates(
            model if isinstance(model, str) else ('embedding' if 'embedding' in path else None)
        )
        out_tokens = 0
        if 'embeddings' not in path:
            out_tokens = self.default_max_output_tokens
            if isinstance(body, dict):
                for name in ('max_completion_tokens', 'max_tokens', 'max_output_tokens'):
                    if isinstance(body.get(name), int) and body[name] > 0:
                        out_tokens = body[name]
                        break
        return (body_bytes / 3.0) * rate_in / 1e6 + out_tokens * rate_out / 1e6 + self.cushion_usd

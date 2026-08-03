from __future__ import annotations

import base64
import json
import time
from collections.abc import AsyncIterator, Mapping
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.routing import APIRoute

from database import llm_usage as llm_usage_db
from database import redis_db
from utils.byok import get_byok_key
from utils.executors import critical_executor, db_executor, run_blocking
from utils.llm.clients import anthropic_client, get_direct_anthropic_client
from utils.llm.desktop_llm_stub import (
    llm_stub_enabled,
    stub_chat_completions_json,
    stub_chat_completions_stream,
)
from utils.llm.gateway_client import (
    CHAT_AGENT_AUTO_LANE_ID,
    get_llm_gateway_base_url,
    get_llm_gateway_client,
    llm_gateway_headers,
    should_route_features_through_gateway,
)
from utils.llm.usage_tracker import reset_usage_context, set_usage_context
from utils.other import endpoints as auth
from utils.subscription import enforce_chat_quota

_MAX_BODY_BYTES = 16 * 1024 * 1024
_RATE_LIMIT_PER_MINUTE = 120


class _BoundedChatRoute(APIRoute):
    def get_route_handler(self):
        route_handler = super().get_route_handler()

        async def bounded_route_handler(request: Request):
            content_length = request.headers.get('content-length')
            if content_length is not None:
                try:
                    if int(content_length) > _MAX_BODY_BYTES:
                        raise HTTPException(status_code=413, detail='Request body is too large')
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail='Invalid Content-Length') from exc
            received = 0
            receive = request.receive

            async def bounded_receive():
                nonlocal received
                message = await receive()
                if message.get('type') == 'http.request':
                    body = message.get('body', b'')
                    if isinstance(body, bytes):
                        received += len(body)
                        if received > _MAX_BODY_BYTES:
                            raise HTTPException(status_code=413, detail='Request body is too large')
                return message

            return await route_handler(Request(request.scope, receive=bounded_receive))

        return bounded_route_handler


router = APIRouter(route_class=_BoundedChatRoute)

_MODEL_ROUTES = {
    'omi-sonnet': 'claude-sonnet-4-6',
    'omi-opus': 'claude-opus-4-6',
    'claude-opus-4-6': 'claude-opus-4-6',
    'claude-sonnet-4-6': 'claude-sonnet-4-6',
    'claude-opus-4-20250514': 'claude-opus-4-6',
    'claude-sonnet-4-20250514': 'claude-sonnet-4-6',
    'claude-haiku-4-5-20251001': 'claude-haiku-4-5',
    'claude-haiku-4-5': 'claude-haiku-4-5',
}
_MANAGED_CHAT_ALIASES = {
    'omi-sonnet',
    'claude-sonnet-4-6',
    'claude-sonnet-4-20250514',
}
_MAX_TOKENS = 16_384


def _uses_managed_chat_agent(body: Mapping[str, object]) -> bool:
    """Route conversational Sonnet traffic to Luna, but preserve specialist calls.

    Desktop conversational traffic uses the managed Luna chat agent only for
    the supported Sonnet aliases. Extraction jobs use Haiku and some callers
    explicitly request Opus; those legacy Anthropic calls must not inherit the
    chat-agent personality/system prompt or have their requested model rewritten
    to Luna. An omitted model uses the managed chat-agent default; an explicit
    unknown model fails closed in the normal request validation path.
    """
    if 'model' not in body:
        return True
    model = body['model']
    if not isinstance(model, str):
        return False
    normalized = model.lower()
    if normalized in _MODEL_ROUTES:
        return normalized in _MANAGED_CHAT_ALIASES
    return False


def _text(content: object) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ''
    return ''.join(
        block.get('text', '')
        for block in content
        if isinstance(block, Mapping) and block.get('type') == 'text' and isinstance(block.get('text'), str)
    )


def _user_content(content: object) -> object:
    if not isinstance(content, list):
        return content if isinstance(content, str) else ''
    blocks: list[dict[str, object]] = []
    for block in content:
        if not isinstance(block, Mapping):
            continue
        if block.get('type') == 'text' and isinstance(block.get('text'), str):
            blocks.append({'type': 'text', 'text': block['text']})
        elif block.get('type') == 'image_url' and isinstance(block.get('image_url'), Mapping):
            url = block['image_url'].get('url')
            if isinstance(url, str) and url.startswith('data:') and ';base64,' in url:
                media_type, data = url[5:].split(';base64,', 1)
                try:
                    base64.b64decode(data, validate=True)
                except ValueError as exc:
                    raise ValueError('image_url must contain valid base64 data') from exc
                blocks.append({'type': 'image', 'source': {'type': 'base64', 'media_type': media_type, 'data': data}})
    return blocks or ''


def _gateway_user_content(content: object) -> object:
    if not isinstance(content, list):
        return content if isinstance(content, str) else ''
    blocks: list[dict[str, object]] = []
    for block in content:
        if not isinstance(block, Mapping):
            continue
        if block.get('type') == 'text' and isinstance(block.get('text'), str):
            blocks.append({'type': 'text', 'text': block['text']})
        elif block.get('type') == 'image_url' and isinstance(block.get('image_url'), Mapping):
            url = block['image_url'].get('url')
            if isinstance(url, str) and url.startswith('data:') and ';base64,' in url:
                _, data = url[5:].split(';base64,', 1)
                try:
                    base64.b64decode(data, validate=True)
                except ValueError as exc:
                    raise ValueError('image_url must contain valid base64 data') from exc
                blocks.append({'type': 'image_url', 'image_url': {'url': url}})
            elif isinstance(url, str) and url.startswith('https://'):
                blocks.append({'type': 'image_url', 'image_url': {'url': url}})
            else:
                raise ValueError('image_url must be a data URL or an HTTPS URL')
    return blocks or ''


def _gateway_body(body: Mapping[str, object]) -> dict[str, object]:
    messages = body.get('messages')
    if not isinstance(messages, list):
        raise ValueError('messages must be an array')
    translated: list[dict[str, object]] = []
    for message in messages:
        if not isinstance(message, Mapping) or not isinstance(message.get('role'), str):
            raise ValueError('messages must contain role objects')
        updated = dict(message)
        role = message['role']
        if role == 'user':
            updated['content'] = _gateway_user_content(message.get('content', ''))
        elif 'content' not in updated or updated.get('content') is None:
            updated['content'] = ''
        translated.append(updated)
    return {**dict(body), 'model': CHAT_AGENT_AUTO_LANE_ID, 'messages': translated}


def _tool_choice(choice: object) -> dict[str, str] | None:
    if choice in (None, 'none'):
        return None
    if choice == 'auto':
        return {'type': 'auto'}
    if choice == 'required':
        return {'type': 'any'}
    if isinstance(choice, Mapping) and choice.get('type') == 'function' and isinstance(choice.get('function'), Mapping):
        name = choice['function'].get('name')
        if isinstance(name, str):
            return {'type': 'tool', 'name': name}
    raise ValueError('unsupported tool_choice')


def _request(body: object) -> tuple[str, dict[str, object]]:
    if not isinstance(body, Mapping):
        raise ValueError('request body must be an object')
    model = body.get('model')
    messages = body.get('messages')
    if not isinstance(model, str) or model not in _MODEL_ROUTES:
        raise ValueError('unsupported model')
    if not isinstance(messages, list):
        raise ValueError('messages must be an array')
    system: str | None = None
    translated: list[dict[str, object]] = []
    for message in messages:
        if not isinstance(message, Mapping) or not isinstance(message.get('role'), str):
            raise ValueError('messages must contain role objects')
        role = message['role']
        if role in {'system', 'developer'}:
            system = _text(message.get('content'))
        elif role == 'user':
            translated.append({'role': 'user', 'content': _user_content(message.get('content', ''))})
        elif role == 'assistant':
            content: list[dict[str, object]] = []
            text = _text(message.get('content'))
            if text:
                content.append({'type': 'text', 'text': text})
            tool_calls = message.get('tool_calls')
            if isinstance(tool_calls, list):
                for call in tool_calls:
                    if not isinstance(call, Mapping) or not isinstance(call.get('function'), Mapping):
                        raise ValueError('invalid assistant tool call')
                    function = call['function']
                    name, arguments, call_id = function.get('name'), function.get('arguments'), call.get('id')
                    if not all(isinstance(value, str) for value in (name, arguments, call_id)):
                        raise ValueError('invalid assistant tool call')
                    try:
                        input_value = json.loads(arguments)
                    except ValueError:
                        input_value = {}
                    content.append({'type': 'tool_use', 'id': call_id, 'name': name, 'input': input_value})
            translated.append({'role': 'assistant', 'content': content or [{'type': 'text', 'text': ''}]})
        elif role == 'tool':
            tool_call_id = message.get('tool_call_id')
            if not isinstance(tool_call_id, str):
                raise ValueError('tool message missing tool_call_id')
            translated.append(
                {
                    'role': 'user',
                    'content': [
                        {'type': 'tool_result', 'tool_use_id': tool_call_id, 'content': _text(message.get('content'))}
                    ],
                }
            )
        else:
            raise ValueError(f'unsupported message role: {role}')
    maximum = body.get('max_completion_tokens', body.get('max_tokens', 8192))
    if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < 1:
        raise ValueError('max_tokens must be a positive integer')
    result: dict[str, object] = {
        'model': _MODEL_ROUTES[model],
        'max_tokens': min(maximum, _MAX_TOKENS),
        'messages': translated,
    }
    if system and system.strip():
        result['system'] = system
    if isinstance(body.get('temperature'), (int, float)) and not isinstance(body.get('temperature'), bool):
        result['temperature'] = body['temperature']
    tools = body.get('tools')
    choice = _tool_choice(body.get('tool_choice'))
    if isinstance(tools, list) and body.get('tool_choice') != 'none':
        result['tools'] = [
            {
                'name': tool['function']['name'],
                'description': tool['function'].get('description'),
                'input_schema': tool['function'].get('parameters', {'type': 'object', 'properties': {}}),
            }
            for tool in tools
            if isinstance(tool, Mapping)
            and tool.get('type') == 'function'
            and isinstance(tool.get('function'), Mapping)
            and isinstance(tool['function'].get('name'), str)
        ]
    if choice is not None and result.get('tools'):
        result['tool_choice'] = choice
    return model, result


def _usage(usage: object) -> dict[str, object]:
    input_tokens = (
        int(getattr(usage, 'input_tokens', 0))
        + int(getattr(usage, 'cache_creation_input_tokens', 0))
        + int(getattr(usage, 'cache_read_input_tokens', 0))
    )
    output_tokens = int(getattr(usage, 'output_tokens', 0))
    result: dict[str, object] = {
        'prompt_tokens': input_tokens,
        'completion_tokens': output_tokens,
        'total_tokens': input_tokens + output_tokens,
    }
    cached_tokens = int(getattr(usage, 'cache_read_input_tokens', 0))
    if cached_tokens:
        result['prompt_tokens_details'] = {'cached_tokens': cached_tokens}
    return result


def _stop_reason(value: object) -> str:
    return {'end_turn': 'stop', 'max_tokens': 'length', 'tool_use': 'tool_calls', 'stop_sequence': 'stop'}.get(
        value if isinstance(value, str) else '', 'stop'
    )


def _message_response(message: object, public_model: str) -> dict[str, object]:
    content: list[Any] = list(getattr(message, 'content', []))
    tool_calls = [
        {
            'id': block.id,
            'type': 'function',
            'function': {'name': block.name, 'arguments': json.dumps(block.input, separators=(',', ':'))},
        }
        for block in content
        if getattr(block, 'type', None) == 'tool_use'
    ]
    text = ''.join(block.text for block in content if getattr(block, 'type', None) == 'text')
    stop_reason = _stop_reason(getattr(message, 'stop_reason', None))
    response_message: dict[str, object] = {'role': 'assistant', 'content': text or None}
    if tool_calls:
        response_message['tool_calls'] = tool_calls
    return {
        'id': f'chatcmpl-{getattr(message, "id", uuid4())}',
        'object': 'chat.completion',
        'created': int(time.time()),
        'model': public_model,
        'choices': [{'index': 0, 'message': response_message, 'finish_reason': stop_reason}],
        'usage': _usage(getattr(message, 'usage', None)),
    }


def _usage_values(usage: object) -> tuple[int, int, int, int]:
    return (
        int(getattr(usage, 'input_tokens', 0)),
        int(getattr(usage, 'output_tokens', 0)),
        int(getattr(usage, 'cache_read_input_tokens', 0)),
        int(getattr(usage, 'cache_creation_input_tokens', 0)),
    )


def _openai_usage_as_anthropic(usage: object) -> SimpleNamespace:
    if not isinstance(usage, Mapping):
        return SimpleNamespace(
            input_tokens=0,
            output_tokens=0,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        )
    details = usage.get('prompt_tokens_details')
    cached_tokens = (
        int(details.get('cached_tokens', 0))
        if isinstance(details, Mapping) and isinstance(details.get('cached_tokens'), int)
        else 0
    )
    prompt_tokens = int(usage.get('prompt_tokens', 0) or 0)
    cached_tokens = min(max(cached_tokens, 0), max(prompt_tokens, 0))
    return SimpleNamespace(
        input_tokens=max(prompt_tokens - cached_tokens, 0),
        output_tokens=int(usage.get('completion_tokens', 0) or 0),
        cache_read_input_tokens=cached_tokens,
        cache_creation_input_tokens=0,
    )


async def _record_usage(uid: str, usage: object) -> None:
    input_tokens, output_tokens, cache_read_tokens, cache_write_tokens = _usage_values(usage)
    await run_blocking(
        db_executor,
        llm_usage_db.record_llm_usage_bucket,
        uid,
        input_tokens,
        output_tokens,
        cache_read_tokens,
        cache_write_tokens,
        input_tokens + output_tokens + cache_read_tokens + cache_write_tokens,
        0.0,
    )


async def _stream(
    payload: dict[str, object],
    public_model: str,
    uid: str,
    *,
    client: Any | None = None,
) -> AsyncIterator[str]:
    stream_id = f'chatcmpl-{uuid4()}'
    created = int(time.time())
    yield _sse(
        {
            'id': stream_id,
            'object': 'chat.completion.chunk',
            'created': created,
            'model': public_model,
            'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}],
        }
    )
    try:
        stream_client = client or anthropic_client
        async with stream_client.messages.stream(**payload) as stream:
            async for event in stream:
                event_type = getattr(event, 'type', '')
                if event_type == 'content_block_delta':
                    delta = cast(Any, getattr(event, 'delta', None))
                    if getattr(delta, 'type', '') == 'text_delta':
                        yield _sse(
                            {
                                'id': stream_id,
                                'object': 'chat.completion.chunk',
                                'created': created,
                                'model': public_model,
                                'choices': [{'index': 0, 'delta': {'content': delta.text}, 'finish_reason': None}],
                            }
                        )
                    elif getattr(delta, 'type', '') == 'input_json_delta':
                        yield _sse(
                            {
                                'id': stream_id,
                                'object': 'chat.completion.chunk',
                                'created': created,
                                'model': public_model,
                                'choices': [
                                    {
                                        'index': 0,
                                        'delta': {
                                            'tool_calls': [
                                                {
                                                    'index': getattr(event, 'index', 0),
                                                    'function': {'arguments': delta.partial_json},
                                                }
                                            ]
                                        },
                                        'finish_reason': None,
                                    }
                                ],
                            }
                        )
                elif (
                    event_type == 'content_block_start'
                    and getattr(getattr(event, 'content_block', None), 'type', '') == 'tool_use'
                ):
                    block = event.content_block
                    yield _sse(
                        {
                            'id': stream_id,
                            'object': 'chat.completion.chunk',
                            'created': created,
                            'model': public_model,
                            'choices': [
                                {
                                    'index': 0,
                                    'delta': {
                                        'tool_calls': [
                                            {
                                                'index': getattr(event, 'index', 0),
                                                'id': block.id,
                                                'type': 'function',
                                                'function': {'name': block.name, 'arguments': ''},
                                            }
                                        ]
                                    },
                                    'finish_reason': None,
                                }
                            ],
                        }
                    )
                elif event_type == 'message_delta':
                    reason = _stop_reason(getattr(getattr(event, 'delta', None), 'stop_reason', None))
                    yield _sse(
                        {
                            'id': stream_id,
                            'object': 'chat.completion.chunk',
                            'created': created,
                            'model': public_model,
                            'choices': [{'index': 0, 'delta': {}, 'finish_reason': reason}],
                        }
                    )
                    usage = getattr(event, 'usage', None)
                    if usage is not None:
                        await _record_usage(uid, usage)
                        yield _sse(
                            {
                                'id': stream_id,
                                'object': 'chat.completion.chunk',
                                'created': created,
                                'model': public_model,
                                'choices': [],
                                'usage': _usage(usage),
                            }
                        )
    except Exception:
        yield _sse({'error': {'message': 'Upstream provider error', 'type': 'server_error', 'code': 502}})
    yield 'data: [DONE]\n\n'


def _sse_json_payloads(frame_buffer: bytearray, chunk: bytes) -> list[dict[str, object]]:
    frame_buffer.extend(chunk)
    payloads: list[dict[str, object]] = []
    while True:
        separator = frame_buffer.find(b'\n\n')
        if separator < 0:
            break
        raw_frame = bytes(frame_buffer[:separator]).replace(b'\r\n', b'\n').replace(b'\r', b'\n')
        del frame_buffer[: separator + 2]
        data_lines: list[str] = []
        for raw_line in raw_frame.split(b'\n'):
            if raw_line.startswith(b'data:'):
                data_lines.append(raw_line.removeprefix(b'data:').lstrip().decode('utf-8', errors='replace'))
        data = '\n'.join(data_lines).strip()
        if not data or data == '[DONE]':
            continue
        try:
            payload = json.loads(data)
        except ValueError:
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


async def _stream_gateway(gateway_payload: dict[str, object], uid: str) -> AsyncIterator[bytes]:
    usage_token = set_usage_context(uid, 'chat_agent')
    frame_buffer = bytearray()
    usage_recorded = False
    try:
        async with get_llm_gateway_client().stream(
            'POST',
            f'{get_llm_gateway_base_url()}/v1/chat/completions',
            headers=llm_gateway_headers(feature='chat_agent'),
            json=gateway_payload,
        ) as response:
            if response.status_code >= 400:
                yield _sse(
                    {'error': {'message': 'Upstream provider error', 'type': 'server_error', 'code': 502}}
                ).encode()
                yield b'data: [DONE]\n\n'
                return
            async for chunk in response.aiter_bytes():
                if not chunk:
                    continue
                for payload in _sse_json_payloads(frame_buffer, chunk):
                    usage = payload.get('usage')
                    if not usage_recorded and isinstance(usage, Mapping):
                        await _record_usage(uid, _openai_usage_as_anthropic(usage))
                        usage_recorded = True
                yield chunk
    except Exception:
        yield _sse({'error': {'message': 'Upstream provider error', 'type': 'server_error', 'code': 502}}).encode()
        yield b'data: [DONE]\n\n'
    finally:
        reset_usage_context(usage_token)


def _sse(value: dict[str, object]) -> str:
    return f'data: {json.dumps(value, separators=(",", ":"))}\n\n'


async def _meter_server_request(uid: str) -> None:
    if get_byok_key('anthropic'):
        return
    try:
        allowed, _, retry_after = await run_blocking(
            critical_executor, redis_db.check_rate_limit, uid, 'desktop_chat', _RATE_LIMIT_PER_MINUTE, 60
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail='Chat metering is temporarily unavailable') from exc
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={'error': {'message': 'Rate limit exceeded', 'type': 'rate_limit_error', 'code': 429}},
            headers={'Retry-After': str(retry_after)},
        )


@router.post('/v2/chat/completions', response_model=None)
async def chat_completions(
    body: dict[str, object],
    uid: str = Depends(auth.get_current_user_uid),
    x_app_platform: str | None = Header(None, alias='X-App-Platform'),
    x_omi_chat_contract_version: str | None = Header(None, alias='X-Omi-Chat-Contract-Version'),
    x_omi_request_id: str | None = Header(None, alias='X-Omi-Request-Id'),
) -> JSONResponse | StreamingResponse:
    if x_omi_chat_contract_version not in {None, '1'}:
        raise HTTPException(status_code=426, detail='Unsupported chat contract version')
    request_id = x_omi_request_id or str(uuid4())
    stub_headers = {
        'Cache-Control': 'no-cache',
        'X-Omi-Chat-Contract-Version': '1',
        'X-Request-Id': request_id,
    }
    # Hermetic offline profile: short-circuit before quota / Anthropic, matching
    # the retired Rust llm_stub intercept so T2 chat flows stay deterministic.
    if llm_stub_enabled():
        if body.get('stream') is True:
            return StreamingResponse(
                stub_chat_completions_stream(body),
                media_type='text/event-stream',
                headers=stub_headers,
            )
        return JSONResponse(stub_chat_completions_json(body), headers=stub_headers)
    payload: dict[str, object] = {}
    try:
        gateway_mode = should_route_features_through_gateway() and _uses_managed_chat_agent(body)
        if gateway_mode and get_byok_key('anthropic'):
            gateway_mode = False
        enforce_chat_quota(uid, platform=x_app_platform)
        await _meter_server_request(uid)
        if gateway_mode:
            public_model = str(body.get('model') or CHAT_AGENT_AUTO_LANE_ID)
            gateway_payload = _gateway_body(body)
        else:
            public_model, payload = _request(body)
            gateway_payload = {}
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await run_blocking(
        db_executor,
        llm_usage_db.record_chat_quota_question,
        uid,
        f'desktop_chat_completions:{request_id}',
        'desktop_chat_completions',
        platform=x_app_platform,
    )
    if body.get('stream') is True:
        if gateway_mode:
            return StreamingResponse(
                _stream_gateway(gateway_payload, uid),
                media_type='text/event-stream',
                headers={
                    'Cache-Control': 'no-cache',
                    'X-Omi-Chat-Contract-Version': '1',
                    'X-Request-Id': request_id,
                },
            )
        return StreamingResponse(
            _stream(
                payload,
                public_model,
                uid,
                client=get_direct_anthropic_client(byok_api_key=get_byok_key('anthropic')),
            ),
            media_type='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Omi-Chat-Contract-Version': '1',
                'X-Request-Id': request_id,
            },
        )
    if gateway_mode:
        usage_token = set_usage_context(uid, 'chat_agent')
        try:
            response = await get_llm_gateway_client().post(
                f'{get_llm_gateway_base_url()}/v1/chat/completions',
                headers=llm_gateway_headers(feature='chat_agent'),
                json=gateway_payload,
            )
            response.raise_for_status()
            response_body = response.json()
            await _record_usage(uid, _openai_usage_as_anthropic(response_body.get('usage')))
            return JSONResponse(
                response_body,
                headers={
                    'X-Omi-Chat-Contract-Version': '1',
                    'X-Request-Id': request_id,
                },
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail='Upstream provider error') from exc
        finally:
            reset_usage_context(usage_token)
    try:
        # The Anthropic SDK overloads do not accept this compatibility payload
        # typed as dict[str, object]; the request has already been normalized
        # and validated above, so keep the SDK boundary dynamic like _stream.
        direct_client: Any = get_direct_anthropic_client(byok_api_key=get_byok_key('anthropic'))
        message = await direct_client.messages.create(**payload)
    except Exception as exc:
        raise HTTPException(status_code=502, detail='Upstream provider error') from exc
    await _record_usage(uid, getattr(message, 'usage', None))
    return JSONResponse(
        _message_response(message, public_model),
        headers={
            'X-Omi-Chat-Contract-Version': '1',
            'X-Request-Id': request_id,
        },
    )

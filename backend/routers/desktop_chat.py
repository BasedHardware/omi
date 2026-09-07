from __future__ import annotations

import asyncio
import base64
import json
import re
import sys
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from types import SimpleNamespace
from typing import Any, Literal, cast
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.routing import APIRoute

from database._client import get_customer_firestore_client
from database import llm_usage as llm_usage_db
from database import redis_db
from database import users as users_db
from llm_gateway.gateway.request_context import jit_budget_forward_headers
from utils.http_client import get_llm_gateway_semaphore
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
    CHAT_STRUCTURED_AUTO_LANE_ID,
    feature_auto_lane_id,
    get_llm_gateway_base_url,
    get_llm_gateway_client,
    llm_gateway_headers,
    should_route_chat_agent_through_gateway,
)
from utils.llm.gateway_observability import record_gateway_request_result
from utils.llm.gateway_resilience import gateway_circuit, observe_gateway_first_byte
from utils.llm.gateway_serving import is_gateway_transport_failure
from utils.llm.private_context import (
    flatten_text_blocks,
    openai_messages_carry_private_tool_output,
)
from utils.llm.usage_tracker import reset_usage_context, set_usage_context
from utils.journey_metrics_contract import ClientKind, resolve_client_kind_from_headers
from utils.observability.fallback import record_fallback
from utils.observability.journeys import ClientJourneyAttempt
from utils.other import endpoints as auth
from utils.retrieval.tools.perplexity_tools import WEB_SEARCH_RETRIEVAL_APPENDIX
from utils.subscription import enforce_desktop_chat_quota

_MAX_BODY_BYTES = 16 * 1024 * 1024
_RATE_LIMIT_PER_MINUTE = 120
_MAX_PAUSE_TURN_CONTINUATIONS = 3
_WEB_SEARCH_COST_PER_REQUEST = 10.0 / 1_000.0

# Kill-switch / BYOK Anthropic path only. Managed public-web turns use the
# gateway `omi:auto:web-search` lane (Perplexity sonar-pro) instead. The desktop
# OpenAI-compatible client never sees or executes this tool; Anthropic owns the
# lookup and returns the grounded answer in the same completion contract. Keep
# the basic direct tool contract: the newer version defaults to code-execution
# callers.
_WEB_SEARCH_TOOL = {
    'type': 'web_search_20250305',
    'name': 'web_search',
    'max_uses': 5,
    'allowed_callers': ['direct'],
}
_PUBLIC_WEB_ROUTING_INSTRUCTION = (
    '<omi_retrieval_policy>Web search is required and available for this fresh public request. '
    'Use a live public-web or search tool before answering. Base time-sensitive claims only on that lookup and '
    'identify the source. Never say, imply, or hedge that you lack internet, web-search, real-time-data, or tool '
    'access; if the lookup itself fails, state that the lookup failed instead. Do not use private Omi context unless '
    'the user explicitly asks for it.</omi_retrieval_policy>'
)

# Both Anthropic (direct/kill-switch) and Perplexity (managed `omi:auto:web-search`)
# run search on their own servers, so query strings escape the `fetch_url`
# allowlist and SSRF guard entirely. Any client tool result already in the
# request is private context the search query could carry out, so server-side
# search is only offered when every tool result in the transcript comes from this
# allowlist of write/permission tools that return no user data. Unknown tool names
# are treated as private.
_PUBLIC_SAFE_CLIENT_TOOLS = frozenset(
    {
        'cancel_agent_run',
        'check_permission_status',
        'create_action_item',
        'create_calendar_event',
        'point_click',
        'request_permission',
        'set_desktop_attention_override',
        'update_action_item',
        'update_agent_artifact_lifecycle',
    }
)
# Per-user capability record under `assistant_settings`. Absent means allowed:
# principals that predate this gate keep the behavior they shipped with, and a
# denial has to be a stored decision.
_WEB_SEARCH_SETTINGS_SECTION = 'web_search'

_EXPLICIT_WEB_REQUESTS = (
    'search the web',
    'search web',
    'search the internet',
    'search online',
    'look it up online',
    'look this up online',
    'look that up online',
    'find it online',
    'find this online',
    'find that online',
    'google it',
    'google this',
    'google that',
    'browse the web',
    'web search',
    'internet search',
)
_EXPLICIT_WEB_PROHIBITIONS = (
    "don't call web search",
    'do not call web search',
    "don't call the web search",
    'do not call the web search',
    "don't call internet search",
    'do not call internet search',
    "don't call the internet search",
    'do not call the internet search',
    "don't use web search",
    'do not use web search',
    "don't use the web search",
    'do not use the web search',
    "don't use internet search",
    'do not use internet search',
    "don't use the internet search",
    'do not use the internet search',
    "don't search the web",
    'do not search the web',
    "don't search the internet",
    'do not search the internet',
    'no web search',
    'no web searches',
    'no internet search',
    'no internet searches',
    'skip web search',
    'skip the web search',
    'skip searching the web',
    'skip searching online',
    'avoid web search',
    'avoid the web search',
    'avoid searching the web',
    "don't browse the web",
    'do not browse the web',
    "don't browse online",
    'do not browse online',
    "don't search online",
    'do not search online',
    'without searching the web',
    'without searching online',
    'without web search',
)
_EXPLICIT_PRIVATE_CONTEXT = (
    'my conversations',
    'our conversations',
    'my memories',
    'your memory of me',
    'my screen history',
    'my screen activity',
    'my calendar',
    'your calendar',
    'my email',
    'your email',
    'my files',
    'your files',
    'my tasks',
    'your tasks',
    'my action items',
    'my notes',
    'your notes',
    'what did i say',
    'what have i said',
    'what did i do',
    'when did i',
    'what was i doing',
    'what do you remember about me',
)
_CURRENT_USER_MESSAGE_DELIMITER = '\n# User Message\n'
_KERNEL_CONTEXT_PREFIX = '[Kernel Context Snapshot '
_LEGACY_CONTEXT_PREFIX = '# Omi Context Snapshot'
_UNTRUSTED_TOOL_CONTEXT_DELIMITER = '\n\nTool-provided context (untrusted):\n'
_NEGATED_WITHOUT_SEARCH = re.compile(r"\b(?:don't|do not|never)\s+(?:[\w'-]+\s+){0,4}$")
_NO_WEB_SEARCH_RESULTS_REPORT = re.compile(
    r'\b(?:got\s+)?no\s+(?:the\s+)?(?:web|internet)\s+search(?:es)?\s+results?\b'
)


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
    'omi-opus',
    'claude-opus-4-6',
    'claude-opus-4-20250514',
    'omi-luna',
    'omi-auto',
    CHAT_AGENT_AUTO_LANE_ID,
}
# Non-conversational desktop callers (the automation planner and the local-agent
# loop) ask for a single-shot structured completion, not a chat turn. They select
# the structured lane explicitly so they never inherit chat-agent routing.
# Legacy Haiku specialist aliases used the company Anthropic key on this
# router; remap them onto the same structured lane so leftover fielded clients
# stop billing direct Haiku. Kill-switch / BYOK still resolve Haiku via
# _MODEL_ROUTES when gateway_mode is off.
_MANAGED_STRUCTURED_ALIASES = {
    'omi-structured',
    CHAT_STRUCTURED_AUTO_LANE_ID,
    'claude-haiku-4-5-20251001',
    'claude-haiku-4-5',
}
# The realtime voice `think_deeper` escalation: a single-shot, no-tools Luna
# completion with an explicit reasoning effort. OpenAI rejects function tools
# combined with a non-none reasoning_effort on gpt-5.6-luna (/v1/chat/completions),
# so this alias deliberately carries no client tools and the effort travels as a
# per-request parameter instead of the tooled chat-agent lane's pinned `none`.
THINKING_MODEL_ALIAS = 'omi-luna-think'
_THINKING_REASONING_EFFORTS = frozenset({'high', 'xhigh'})
_MANAGED_THINKING_ALIASES = {THINKING_MODEL_ALIAS}
WEB_SEARCH_AUTO_LANE_ID = feature_auto_lane_id('web_search')
_MAX_TOKENS = 16_384
# Top-level automatic prompt caching. Anthropic places this breakpoint on the last
# cacheable block (tools → system → messages). TTL=1h: the default became 5m on
# 2026-03-06, which is shorter than typical gaps between desktop-chat turns.
# The ~14k-token tools+system prefix only hits if those bytes stay identical
# across requests from the same client; volatile content belongs in the user turn.
_PROMPT_CACHE_CONTROL = {'type': 'ephemeral', 'ttl': '1h'}


def _managed_lane_id(body: Mapping[str, object]) -> str:
    """Lane a managed desktop request routes to. Chat is the default."""
    model = body.get('model')
    normalized = model.strip().lower() if isinstance(model, str) else ''
    if normalized in _MANAGED_STRUCTURED_ALIASES:
        return CHAT_STRUCTURED_AUTO_LANE_ID
    return CHAT_AGENT_AUTO_LANE_ID


def _is_thinking_escalation(body: Mapping[str, object]) -> bool:
    """True when this request is a no-tools Luna thinking escalation."""
    model = body.get('model')
    if not isinstance(model, str):
        return False
    return model.strip().lower() in _MANAGED_THINKING_ALIASES


def _uses_managed_chat_agent(body: Mapping[str, object]) -> bool:
    """Route managed desktop traffic onto gateway lanes.

    Desktop conversational traffic uses the managed Luna chat agent for Sonnet
    and leftover Opus aliases plus explicit auto/Luna lane ids. Legacy Haiku
    extraction aliases join the structured lane so they do not inherit the
    chat-agent personality or keep using the company Anthropic key. The voice
    thinking escalation joins the chat-agent lane without tools. An omitted
    model uses the managed chat-agent default; an explicit unknown model fails
    closed in the normal request validation path.
    """
    if 'model' not in body:
        return True
    model = body['model']
    if not isinstance(model, str):
        return False
    normalized = model.strip().lower()
    if not normalized:
        return True
    if (
        normalized in _MANAGED_CHAT_ALIASES
        or normalized in _MANAGED_STRUCTURED_ALIASES
        or normalized in _MANAGED_THINKING_ALIASES
    ):
        return True
    if normalized in _MODEL_ROUTES:
        return normalized in _MANAGED_CHAT_ALIASES
    return False


def _text(content: object) -> str:
    return flatten_text_blocks(content)


def _normalize_policy_text(text: str) -> str:
    return text.strip().strip('.,:;!?').replace('\u2018', "'").replace('\u2019', "'").lower()


def _explicitly_requests_public_web(text: str) -> bool:
    text_without_result_reports = _NO_WEB_SEARCH_RESULTS_REPORT.sub(' ', text)
    return any(phrase in text_without_result_reports for phrase in _EXPLICIT_WEB_REQUESTS)


def _explicitly_prohibits_public_web(text: str, *, allow_result_report: bool = False) -> bool:
    for phrase in _EXPLICIT_WEB_PROHIBITIONS:
        start = text.find(phrase)
        while start >= 0:
            if allow_result_report and _NO_WEB_SEARCH_RESULTS_REPORT.match(text, start):
                start = text.find(phrase, start + 1)
                continue
            if not (phrase.startswith('without ') and _NEGATED_WITHOUT_SEARCH.search(text[:start])):
                return True
            start = text.find(phrase, start + 1)
    for referent in ('web search tool', 'internet search tool'):
        start = text.find(referent)
        while start >= 0:
            tail = text[start + len(referent) : start + len(referent) + 160]
            if any(
                phrase in tail
                for phrase in (
                    "don't call it because",
                    'do not call it because',
                    "don't call it again",
                    'do not call it again',
                )
            ):
                return True
            start = text.find(referent, start + 1)
    return False


def _latest_user_message(messages: object) -> Mapping[str, object] | None:
    if not isinstance(messages, list):
        return None
    return next(
        (message for message in reversed(messages) if isinstance(message, Mapping) and message.get('role') == 'user'),
        None,
    )


def _last_message_is_user(messages: object) -> bool:
    return bool(
        isinstance(messages, list)
        and messages
        and isinstance(messages[-1], Mapping)
        and messages[-1].get('role') == 'user'
    )


def _has_public_web_routing_instruction(messages: object) -> bool:
    latest_user = _latest_user_message(messages)
    return bool(latest_user and _text(latest_user.get('content')).lstrip().startswith(_PUBLIC_WEB_ROUTING_INSTRUCTION))


def _web_search_requested(body: Mapping[str, object]) -> bool:
    messages = body.get('messages')
    client_tools = _anthropic_client_tools(body.get('tools'))
    requested_tool_choice = body.get('tool_choice')
    required_client_tools = bool(client_tools) and (
        requested_tool_choice == 'required'
        or (isinstance(requested_tool_choice, Mapping) and requested_tool_choice.get('type') == 'function')
    )
    return bool(
        requested_tool_choice != 'none'
        and _last_message_is_user(messages)
        and not required_client_tools
        and (body.get('omi_web_search') is True or _has_public_web_routing_instruction(messages))
    )


# Web-search authorization outcome. ``denied`` is a stored per-user decision;
# ``unavailable`` means the lookup failed closed and must not also be reported
# as an explicit denial. Keeps the two fallback reasons mutually exclusive.
WebSearchAuthorization = Literal['authorized', 'denied', 'unavailable']


def _web_search_supported_for_upstream(upstream_model: str) -> bool:
    return not upstream_model.startswith('claude-haiku')


def _web_search_eligible(
    body: Mapping[str, object],
    *,
    authorization: WebSearchAuthorization,
    web_search_supported: bool = True,
) -> bool:
    messages = body.get('messages')
    return bool(
        web_search_supported
        and not _public_web_is_prohibited(messages)
        and _web_search_requested(body)
        and authorization == 'authorized'
        and not _carries_private_tool_output(messages)
    )


def _record_web_search_withheld(
    body: Mapping[str, object],
    *,
    authorization: WebSearchAuthorization,
    web_search_supported: bool,
    from_mode: str,
) -> None:
    messages = body.get('messages')
    if not _web_search_requested(body) or _public_web_is_prohibited(messages):
        return
    if not web_search_supported:
        record_fallback(
            component='other',
            from_mode=from_mode,
            to_mode='model_knowledge',
            reason='capability_mismatch',
            outcome='degraded',
        )
        return
    if _carries_private_tool_output(messages):
        record_fallback(
            component='other',
            from_mode=from_mode,
            to_mode='model_knowledge',
            reason='private_tool_output_in_context',
            outcome='degraded',
        )
    elif authorization == 'denied':
        record_fallback(
            component='other',
            from_mode=from_mode,
            to_mode='model_knowledge',
            reason='not_authorized',
            outcome='degraded',
        )


def _with_public_web_routing_instruction(messages: list[dict[str, object]]) -> list[dict[str, object]]:
    if _has_public_web_routing_instruction(messages):
        return messages
    updated = [dict(message) for message in messages]
    for message in updated:
        if message.get('role') in {'system', 'developer'}:
            existing = _text(message.get('content'))
            message['content'] = (
                f'{existing.rstrip()}\n\n{_PUBLIC_WEB_ROUTING_INSTRUCTION}'
                if existing.strip()
                else _PUBLIC_WEB_ROUTING_INSTRUCTION
            )
            return updated
    return [{'role': 'system', 'content': _PUBLIC_WEB_ROUTING_INSTRUCTION}, *updated]


def _append_web_search_retrieval_appendix(messages: list[dict[str, object]]) -> list[dict[str, object]]:
    """Append the fixed primary-source retrieval hint to the last user message.

    The managed web-search lane sends the raw client question to sonar-pro,
    which retrieves what the query describes — product-history questions stop
    at the vendor marketing site (live RCA 2026-09-02). The same appendix the
    agentic tool's hop-2 uses redirects retrieval at founder interviews,
    Product Hunt launch posts, and postmortems. Idempotent.
    """
    updated = [dict(message) for message in messages]
    for message in reversed(updated):
        if message.get('role') != 'user':
            continue
        content = message.get('content')
        if isinstance(content, str):
            if WEB_SEARCH_RETRIEVAL_APPENDIX not in content:
                message['content'] = f'{content}{WEB_SEARCH_RETRIEVAL_APPENDIX}'
        elif isinstance(content, list) and not any(
            isinstance(block, Mapping) and block.get('text') == WEB_SEARCH_RETRIEVAL_APPENDIX for block in content
        ):
            message['content'] = [*content, {'type': 'text', 'text': WEB_SEARCH_RETRIEVAL_APPENDIX}]
        return updated
    return updated


def _carries_private_tool_output(messages: object) -> bool:
    # The desktop hub also inlines tool output into the user turn behind a
    # literal marker instead of sending an OpenAI `tool` message, so the same
    # private data reaches the request without a tool_call_id to classify.
    return openai_messages_carry_private_tool_output(
        messages,
        public_safe_tools=_PUBLIC_SAFE_CLIENT_TOOLS,
        inline_private_markers=(_UNTRUSTED_TOOL_CONTEXT_DELIMITER,),
    )


def _strip_public_web_routing_instruction(text: str) -> str:
    trimmed = text.lstrip()
    opening = '<omi_retrieval_policy>'
    closing = '</omi_retrieval_policy>'
    if not trimmed.startswith(opening):
        return text
    remainder = trimmed.split(closing, 1)
    return remainder[1].lstrip() if len(remainder) == 2 else text


def _trusted_user_instruction(rendered: str) -> str:
    instruction = _strip_public_web_routing_instruction(rendered)
    if instruction.startswith((_KERNEL_CONTEXT_PREFIX, _LEGACY_CONTEXT_PREFIX)):
        _, delimiter, current_user = instruction.partition(_CURRENT_USER_MESSAGE_DELIMITER)
        if delimiter:
            instruction = current_user
    elif _CURRENT_USER_MESSAGE_DELIMITER in instruction:
        # Only the kernel's canonical wrapper may introduce this boundary. If a
        # raw user string contains it, keep the prefix so the user cannot replace
        # a private or opt-out instruction with a public-web suffix.
        instruction = instruction.partition(_CURRENT_USER_MESSAGE_DELIMITER)[0]
    instruction = instruction.partition(_CURRENT_USER_MESSAGE_DELIMITER)[0]
    return instruction.partition(_UNTRUSTED_TOOL_CONTEXT_DELIMITER)[0]


def _public_web_is_prohibited(messages: object) -> bool:
    latest_user = _latest_user_message(messages)
    if latest_user is None:
        return False
    instruction = _trusted_user_instruction(_text(latest_user.get('content')))
    normalized = _normalize_policy_text(instruction)
    if not normalized:
        return False
    explicitly_mentions_web = _explicitly_requests_public_web(normalized)
    explicitly_prohibits_web = _explicitly_prohibits_public_web(normalized, allow_result_report=explicitly_mentions_web)
    private_context = any(phrase in normalized for phrase in _EXPLICIT_PRIVATE_CONTEXT)
    return explicitly_prohibits_web or (private_context and not explicitly_mentions_web)


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


# Top-level request keys the gateway will accept. The gateway validates the
# forwarded body against a strict allowlist and rejects the whole request with
# HTTP 400 on the first unknown key, so anything the desktop client sends that
# is not listed here must be dropped rather than passed through.
#
# This is not a style preference. Forwarding the client body verbatim took every
# managed desktop chat turn down for ~19 hours: the local pi-mono agent runs the
# OpenAI JS SDK, which sets `store` on every request (and `reasoning_effort`
# whenever a thinking level is set). Neither is in the gateway's allowlist, so
# each turn 400ed before a lane was ever resolved, and `_stream` reported that as
# an in-band `502 Upstream provider error` inside an HTTP 200 — invisible to
# status-code monitoring.
#
# `test_gateway_forwardable_params_stay_within_the_gateway_allowlist` pins this
# set against the gateway's own validator so the two cannot drift apart again.
_GATEWAY_FORWARDABLE_PARAMS = frozenset(
    {
        'frequency_penalty',
        'logit_bias',
        'logprobs',
        'max_completion_tokens',
        'max_tokens',
        'metadata',
        'n',
        'presence_penalty',
        'prompt_cache_key',
        'prompt_cache_options',
        'response_format',
        'seed',
        'service_tier',
        'stop',
        'stream',
        'stream_options',
        'temperature',
        'tool_choice',
        'tools',
        'top_logprobs',
        'top_p',
        'user',
    }
)


def _log_gateway_rejection(response: httpx.Response, *, lane_id: str, request_id: str) -> None:
    """Record why the gateway refused a request.

    A 4xx from the gateway carries a typed body naming the offending field
    (`{"error": {"message": ..., "param": ...}}`), and both call sites used to
    discard it and report a bare `502 Upstream provider error`. That left the
    real reason recorded nowhere: during the 2026-08-20 outage the rejected
    parameter appeared in no log line in either GCP project, so a one-request
    diagnosis took hours of log archaeology instead.

    Client-supplied content is never logged — only the gateway's own error
    message and param, which are gateway-authored and carry no user data.
    """
    status_code = response.status_code
    message = ''
    param = ''
    try:
        payload = response.json()
    except Exception:
        payload = None
    if isinstance(payload, Mapping):
        error = payload.get('error')
        if isinstance(error, Mapping):
            message = str(error.get('message') or '')[:200]
            param = str(error.get('param') or '')[:100]
    event = {
        'event': 'desktop_chat_gateway_refused',
        'message': 'desktop_chat_gateway_refused',
        'lane_id': lane_id,
        'status_code': status_code,
        'param': param or 'unknown',
        'reason': message or 'unavailable',
        'request_id': request_id,
        'severity': 'WARNING',
    }
    sys.stdout.write(json.dumps(event, separators=(',', ':'), sort_keys=True) + '\n')


def _thinking_escalation_effort(body: Mapping[str, object]) -> str:
    """Validated Luna reasoning effort for a thinking escalation.

    The desktop client owns the product-level mapping (`normal` -> high,
    `heavy` -> xhigh); this router only accepts the two wire values the
    escalation surface defines. Anything else fails closed with a 400 rather
    than silently billing an unintended effort tier.
    """
    effort = body.get('reasoning_effort')
    if effort is None or (isinstance(effort, str) and not effort.strip()):
        return 'high'
    if isinstance(effort, str) and effort.strip() in _THINKING_REASONING_EFFORTS:
        return effort.strip()
    raise ValueError('unsupported reasoning_effort for omi-luna-think')


def _gateway_body(body: Mapping[str, object], lane_id: str = CHAT_AGENT_AUTO_LANE_ID) -> dict[str, object]:
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
    gateway_body = {key: value for key, value in body.items() if key in _GATEWAY_FORWARDABLE_PARAMS}
    result = {**gateway_body, 'model': lane_id, 'messages': translated}
    if lane_id == WEB_SEARCH_AUTO_LANE_ID:
        # The Perplexity web-search lane has tools: false. Public-web turns
        # are a live lookup, not a client-tool continuation.
        result.pop('tools', None)
        result.pop('tool_choice', None)
        result['messages'] = _append_web_search_retrieval_appendix(_with_public_web_routing_instruction(translated))
    if _is_thinking_escalation(body):
        # Single-shot Luna reasoning: OpenAI rejects function tools combined
        # with a non-none reasoning_effort on gpt-5.6-luna, so the escalation
        # never carries client tools. The validated effort is server-authored
        # here, not a verbatim client passthrough.
        result.pop('tools', None)
        result.pop('tool_choice', None)
        result.pop('reasoning_effort', None)
        result['reasoning_effort'] = _thinking_escalation_effort(body)
    return result


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


def _anthropic_client_tools(tools: object) -> list[dict[str, object]]:
    if not isinstance(tools, list):
        return []
    return [
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


def _request(
    body: object, *, web_search_authorization: WebSearchAuthorization = 'unavailable'
) -> tuple[str, dict[str, object]]:
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
    client_tools = _anthropic_client_tools(tools)
    upstream_model = cast(str, result['model'])
    web_search_supported = _web_search_supported_for_upstream(upstream_model)
    _record_web_search_withheld(
        body,
        authorization=web_search_authorization,
        web_search_supported=web_search_supported,
        from_mode='anthropic_web_search',
    )
    inject_web_search = _web_search_eligible(
        body,
        authorization=web_search_authorization,
        web_search_supported=web_search_supported,
    )
    if inject_web_search:
        existing_system = result.get('system')
        result['system'] = (
            f'{existing_system.rstrip()}\n\n{_PUBLIC_WEB_ROUTING_INSTRUCTION}'
            if isinstance(existing_system, str) and existing_system.strip()
            else _PUBLIC_WEB_ROUTING_INSTRUCTION
        )
    if body.get('tool_choice') != 'none' and (isinstance(tools, list) or inject_web_search):
        result['tools'] = ([_WEB_SEARCH_TOOL] if inject_web_search else []) + client_tools
    if choice is not None and result.get('tools'):
        result['tool_choice'] = choice
    result['cache_control'] = dict(_PROMPT_CACHE_CONTROL)
    return cast(str, result['model']), result  # response.model = SERVED model, never the alias


def _usage_field(usage: object, field: str) -> int:
    value = usage.get(field, 0) if isinstance(usage, Mapping) else getattr(usage, field, 0)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _web_search_requests(usage: object) -> int:
    direct = _usage_field(usage, 'web_search_requests')
    if direct:
        return direct
    server_tool_use = (
        usage.get('server_tool_use') if isinstance(usage, Mapping) else getattr(usage, 'server_tool_use', None)
    )
    return _usage_field(server_tool_use, 'web_search_requests')


def _usage(usage: object) -> dict[str, object]:
    input_tokens = (
        _usage_field(usage, 'input_tokens')
        + _usage_field(usage, 'cache_creation_input_tokens')
        + _usage_field(usage, 'cache_read_input_tokens')
    )
    output_tokens = _usage_field(usage, 'output_tokens')
    result: dict[str, object] = {
        'prompt_tokens': input_tokens,
        'completion_tokens': output_tokens,
        'total_tokens': input_tokens + output_tokens,
    }
    cached_tokens = _usage_field(usage, 'cache_read_input_tokens')
    if cached_tokens:
        result['prompt_tokens_details'] = {'cached_tokens': cached_tokens}
    search_requests = _web_search_requests(usage)
    if search_requests:
        result['web_search_requests'] = search_requests
    return result


def _stop_reason(value: object) -> str:
    return {'end_turn': 'stop', 'max_tokens': 'length', 'tool_use': 'tool_calls', 'stop_sequence': 'stop'}.get(
        value if isinstance(value, str) else '', 'stop'
    )


def _serialize_content(content: object) -> list[dict[str, object]]:
    if not isinstance(content, list):
        return []
    serialized: list[dict[str, object]] = []
    for block in content:
        if isinstance(block, Mapping):
            serialized.append(dict(block))
            continue
        model_dump = getattr(block, 'model_dump', None)
        if callable(model_dump):
            try:
                dumped = model_dump(mode='json', exclude_none=True)
            except TypeError:
                dumped = model_dump(exclude_none=True)
            if isinstance(dumped, Mapping):
                serialized.append(dict(dumped))
                continue
        block_dict = getattr(block, '__dict__', None)
        if isinstance(block_dict, dict):
            serialized.append(dict(block_dict))
    return serialized


def _block_value(block: object, field: str, default: object = None) -> object:
    if isinstance(block, Mapping):
        return block.get(field, default)
    return getattr(block, field, default)


def _message_content(message: object) -> list[object]:
    content = getattr(message, 'content', [])
    return list(content) if isinstance(content, list) else []


def _message_response(
    message: object,
    public_model: str,
    *,
    content_override: list[object] | None = None,
    usage_override: object | None = None,
) -> dict[str, object]:
    content = content_override if content_override is not None else _message_content(message)
    tool_calls = [
        {
            'id': _block_value(block, 'id'),
            'type': 'function',
            'function': {
                'name': _block_value(block, 'name'),
                'arguments': json.dumps(_block_value(block, 'input', {}), separators=(',', ':')),
            },
        }
        for block in content
        if _block_value(block, 'type') == 'tool_use'
    ]
    text = ''.join(
        value
        for block in content
        if _block_value(block, 'type') == 'text' and isinstance((value := _block_value(block, 'text')), str)
    )
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
        'usage': _usage(usage_override if usage_override is not None else getattr(message, 'usage', None)),
    }


def _usage_values(usage: object) -> tuple[int, int, int, int]:
    return (
        _usage_field(usage, 'input_tokens'),
        _usage_field(usage, 'output_tokens'),
        _usage_field(usage, 'cache_read_input_tokens'),
        _usage_field(usage, 'cache_creation_input_tokens'),
    )


def _merge_usage(total: dict[str, int], usage: object) -> dict[str, int]:
    for field in ('input_tokens', 'output_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens'):
        total[field] = total.get(field, 0) + _usage_field(usage, field)
    search_requests = _web_search_requests(usage)
    if search_requests:
        total['web_search_requests'] = total.get('web_search_requests', 0) + search_requests
    return total


class _PauseTurnContinuationLimitError(RuntimeError):
    def __init__(self, usage: dict[str, int], message: object, content: list[object]):
        super().__init__('Anthropic pause_turn continuation limit reached')
        self.usage = usage
        self.message = message
        self.content = content


async def _continue_pause_turn(
    payload: dict[str, object],
    message: object,
    initial_usage: object | None = None,
    *,
    include_initial_content: bool = True,
    client: Any | None = None,
) -> tuple[object, dict[str, int], list[object]]:
    total_usage = _merge_usage({}, initial_usage if initial_usage is not None else getattr(message, 'usage', None))
    raw_messages = payload.get('messages', [])
    messages = (
        [dict(item) for item in raw_messages if isinstance(item, Mapping)] if isinstance(raw_messages, list) else []
    )
    request = dict(payload)
    request['stream'] = False
    aggregated_content = _message_content(message) if include_initial_content else []
    message_client = client or anthropic_client
    for _ in range(_MAX_PAUSE_TURN_CONTINUATIONS):
        current_content = _message_content(message)
        messages.append({'role': 'assistant', 'content': _serialize_content(current_content)})
        request['messages'] = messages
        message = await message_client.messages.create(**request)
        _merge_usage(total_usage, getattr(message, 'usage', None))
        aggregated_content.extend(_message_content(message))
        if getattr(message, 'stop_reason', None) != 'pause_turn':
            return message, total_usage, aggregated_content
    raise _PauseTurnContinuationLimitError(total_usage, message, aggregated_content)


async def _create_with_pause_turn_continuations(
    payload: dict[str, object],
    *,
    client: Any | None = None,
) -> tuple[object, dict[str, int], list[object] | None]:
    message_client = client or anthropic_client
    message = await message_client.messages.create(**payload)
    total_usage = _merge_usage({}, getattr(message, 'usage', None))
    if getattr(message, 'stop_reason', None) != 'pause_turn':
        return message, total_usage, None
    return await _continue_pause_turn(payload, message, client=message_client)


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
    if get_byok_key('anthropic'):

        def _exclude(record_uid: str) -> None:
            llm_usage_db.record_llm_cost_exclusion(
                record_uid,
                bucket='desktop_chat',
                account='omi',
                cost_exclusion='byok_provider_cost',
                firestore_client=get_customer_firestore_client(),
            )

        await run_blocking(db_executor, _exclude, uid)
        return
    input_tokens, output_tokens, cache_read_tokens, cache_write_tokens = _usage_values(usage)
    total_tokens = input_tokens + output_tokens + cache_read_tokens + cache_write_tokens
    web_search_requests = _web_search_requests(usage)
    cost = web_search_requests * _WEB_SEARCH_COST_PER_REQUEST
    cost_status = 'partial' if web_search_requests else 'missing'
    cost_exclusion = 'provider_token_cost_not_recorded'

    def _write(
        record_uid: str,
        in_tokens: int,
        out_tokens: int,
        cache_read: int,
        cache_write: int,
        combined_tokens: int,
        cost_usd: float,
    ) -> None:
        llm_usage_db.record_llm_usage_bucket(
            record_uid,
            in_tokens,
            out_tokens,
            cache_read,
            cache_write,
            combined_tokens,
            cost_usd if cost_status != 'missing' else None,
            cost_status=cost_status,
            cost_exclusion=cost_exclusion,
            firestore_client=get_customer_firestore_client(),
        )

    await run_blocking(
        db_executor,
        _write,
        uid,
        input_tokens,
        output_tokens,
        cache_read_tokens,
        cache_write_tokens,
        total_tokens,
        cost,
    )


def _consume_task_result(task: asyncio.Task[object]) -> None:
    if not task.cancelled():
        task.exception()


def _schedule_usage_record(uid: str, usage: object) -> None:
    task = asyncio.create_task(_record_usage(uid, usage))
    task.add_done_callback(_consume_task_result)


async def _record_usage_resilient(uid: str, usage: object) -> None:
    task = asyncio.create_task(_record_usage(uid, usage))
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        task.add_done_callback(_consume_task_result)
        raise


async def _stream(
    payload: dict[str, object],
    public_model: str,
    uid: str,
    *,
    client: Any | None = None,
    on_upstream_accepted: Callable[[], Awaitable[None]] | None = None,
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
    stream_usage: dict[str, int] = {}
    message_delta_reason: object = None
    usage_recorded = False
    try:
        stream_client = client or anthropic_client
        async with stream_client.messages.stream(**payload) as stream:
            # Quota is charged once the provider accepts the turn, mirroring the
            # gateway lane: a request the provider rejects costs the user nothing.
            if on_upstream_accepted is not None:
                await on_upstream_accepted()
            message_delta_usage: object = None
            next_tool_index = 0
            client_tool_indexes: dict[int, int] = {}
            async for event in stream:
                event_type = getattr(event, 'type', '')
                if event_type == 'message_start':
                    _merge_usage(stream_usage, getattr(getattr(event, 'message', None), 'usage', None))
                elif event_type == 'content_block_delta':
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
                        event_index = getattr(event, 'index', 0)
                        client_tool_index = client_tool_indexes.get(event_index)
                        if client_tool_index is None:
                            continue
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
                                                    'index': client_tool_index,
                                                    'function': {'arguments': delta.partial_json},
                                                }
                                            ]
                                        },
                                        'finish_reason': None,
                                    }
                                ],
                            }
                        )
                elif event_type == 'content_block_start':
                    block = event.content_block
                    block_type = getattr(block, 'type', '')
                    tool_index = getattr(event, 'index', 0)
                    if block_type in {'server_tool_use', 'web_search_tool_result'}:
                        client_tool_indexes.pop(tool_index, None)
                    elif block_type == 'tool_use':
                        client_tool_index = next_tool_index
                        client_tool_indexes[tool_index] = client_tool_index
                        next_tool_index += 1
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
                                                    'index': client_tool_index,
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
                    message_delta_reason = getattr(getattr(event, 'delta', None), 'stop_reason', None)
                    message_delta_usage = getattr(event, 'usage', None)
                    _merge_usage(stream_usage, message_delta_usage)
            final_message = await stream.get_final_message()
            final_usage = getattr(final_message, 'usage', None) or message_delta_usage
            final_content: list[object] | None = None
            if getattr(final_message, 'stop_reason', None) == 'pause_turn' or message_delta_reason == 'pause_turn':
                final_message, usage, final_content = await _continue_pause_turn(
                    payload, final_message, final_usage, include_initial_content=False, client=stream_client
                )
                for block in final_content:
                    block_type = _block_value(block, 'type')
                    if block_type == 'text' and isinstance(text := _block_value(block, 'text'), str):
                        yield _sse(
                            {
                                'id': stream_id,
                                'object': 'chat.completion.chunk',
                                'created': created,
                                'model': public_model,
                                'choices': [{'index': 0, 'delta': {'content': text}, 'finish_reason': None}],
                            }
                        )
                    elif block_type == 'tool_use':
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
                                                    'index': next_tool_index,
                                                    'id': _block_value(block, 'id'),
                                                    'type': 'function',
                                                    'function': {
                                                        'name': _block_value(block, 'name'),
                                                        'arguments': json.dumps(
                                                            _block_value(block, 'input', {}), separators=(',', ':')
                                                        ),
                                                    },
                                                }
                                            ]
                                        },
                                        'finish_reason': None,
                                    }
                                ],
                            }
                        )
                        next_tool_index += 1
            else:
                usage = final_usage
            if usage is not None:
                await _record_usage_resilient(uid, usage)
                usage_recorded = True
            reason = _stop_reason(getattr(final_message, 'stop_reason', None) or message_delta_reason)
            yield _sse(
                {
                    'id': stream_id,
                    'object': 'chat.completion.chunk',
                    'created': created,
                    'model': public_model,
                    'choices': [{'index': 0, 'delta': {}, 'finish_reason': reason}],
                }
            )
            if usage is not None:
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
    except _PauseTurnContinuationLimitError as exc:
        if not usage_recorded:
            await _record_usage_resilient(uid, exc.usage)
        yield _sse({'error': {'message': 'Upstream provider error', 'type': 'server_error', 'code': 502}})
    except asyncio.CancelledError:
        if stream_usage and not usage_recorded:
            _schedule_usage_record(uid, stream_usage)
        raise
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


def _gateway_feature_for_lane(lane_id: str) -> str:
    """Accounting feature for a managed lane.

    Structured-lane and web-search traffic must not be written to the ledger and
    reliability metrics as chat-agent traffic, or per-feature cost and failure
    signals for those lanes vanish into chat.
    """
    if lane_id == CHAT_STRUCTURED_AUTO_LANE_ID:
        return 'chat_structured'
    if lane_id == WEB_SEARCH_AUTO_LANE_ID:
        return 'web_search'
    return 'chat_agent'


def _gateway_request_headers(
    request_id: str,
    lane_id: str = CHAT_AGENT_AUTO_LANE_ID,
    platform: str | None = None,
    jit_headers: Mapping[str, str] | None = None,
) -> dict[str, str]:
    headers = llm_gateway_headers(feature=_gateway_feature_for_lane(lane_id), platform=platform)
    headers['X-Omi-Request-ID'] = request_id
    if jit_headers:
        headers.update(jit_headers)
    return headers


def _jit_headers_for_forward(
    contract_version: str | None,
    run_id: str | None,
    max_attempts: str | None,
    max_output_tokens: str | None,
    max_input_tokens: str | None,
    max_spend_micro_usd: str | None,
) -> dict[str, str]:
    return jit_budget_forward_headers(
        contract_version,
        run_id,
        max_attempts,
        max_output_tokens,
        max_input_tokens,
        max_spend_micro_usd,
    )


def _record_gateway_result(
    *, outcome: str, reason: str, request_id: str, lane_id: str = CHAT_AGENT_AUTO_LANE_ID
) -> None:
    record_gateway_request_result(
        feature=_gateway_feature_for_lane(lane_id),
        outcome=outcome,
        reason=reason,
        route=lane_id,
        mode='gateway',
        request_id=request_id,
        credential_source='omi_managed',
    )


async def _record_chat_quota_question(uid: str, request_id: str, platform: str | None) -> None:
    def _write() -> None:
        llm_usage_db.record_chat_quota_question(
            uid,
            f'desktop_chat_completions:{request_id}',
            'desktop_chat_completions',
            platform=platform,
            firestore_client=get_customer_firestore_client(),
        )

    await run_blocking(db_executor, _write)


async def _stream_gateway(
    gateway_payload: dict[str, object],
    uid: str,
    request_id: str = 'unknown',
    platform: str | None = None,
    lane_id: str = CHAT_AGENT_AUTO_LANE_ID,
    jit_headers: Mapping[str, str] | None = None,
) -> AsyncIterator[bytes]:
    usage_token = set_usage_context(uid, _gateway_feature_for_lane(lane_id))
    frame_buffer = bytearray()
    usage_recorded = False
    started_at = time.monotonic()
    result_recorded = False
    try:
        if not gateway_circuit.allow_request():
            _record_gateway_result(lane_id=lane_id, outcome='error', reason='circuit_open', request_id=request_id)
            yield _sse({'error': {'message': 'Upstream provider error', 'type': 'server_error', 'code': 502}}).encode()
            yield b'data: [DONE]\n\n'
            return
        async with get_llm_gateway_semaphore():
            async with get_llm_gateway_client().stream(
                'POST',
                f'{get_llm_gateway_base_url()}/v1/chat/completions',
                headers=_gateway_request_headers(request_id, lane_id, platform, jit_headers),
                json=gateway_payload,
            ) as response:
                if response.status_code >= 400:
                    status_error = HTTPException(status_code=response.status_code)
                    transport_failure = is_gateway_transport_failure(status_error)
                    if transport_failure:
                        gateway_circuit.record_transport_failure()
                    _log_gateway_rejection(response, lane_id=lane_id, request_id=request_id)
                    observe_gateway_first_byte(
                        feature=_gateway_feature_for_lane(lane_id),
                        started_at=started_at,
                        outcome='transport_failure' if transport_failure else 'error',
                    )
                    _record_gateway_result(
                        lane_id=lane_id,
                        outcome='fallback' if transport_failure else 'error',
                        reason=f'http_{response.status_code}',
                        request_id=request_id,
                    )
                    result_recorded = True
                    yield _sse(
                        {'error': {'message': 'Upstream provider error', 'type': 'server_error', 'code': 502}}
                    ).encode()
                    yield b'data: [DONE]\n\n'
                    return
                await _record_chat_quota_question(uid, request_id, platform)
                observe_gateway_first_byte(
                    feature=_gateway_feature_for_lane(lane_id), started_at=started_at, outcome='success'
                )
                async for chunk in response.aiter_bytes():
                    if not chunk:
                        continue
                    for payload in _sse_json_payloads(frame_buffer, chunk):
                        usage = payload.get('usage')
                        if not usage_recorded and isinstance(usage, Mapping):
                            await _record_usage(uid, _openai_usage_as_anthropic(usage))
                            usage_recorded = True
                    yield chunk
        gateway_circuit.record_transport_success()
        _record_gateway_result(lane_id=lane_id, outcome='success', reason='ok', request_id=request_id)
        result_recorded = True
    except asyncio.CancelledError:
        if not result_recorded:
            _record_gateway_result(lane_id=lane_id, outcome='cancelled', reason='cancelled', request_id=request_id)
        raise
    except Exception as exc:
        if not result_recorded:
            transport_failure = is_gateway_transport_failure(exc)
            if transport_failure:
                gateway_circuit.record_transport_failure()
            observe_gateway_first_byte(
                feature=_gateway_feature_for_lane(lane_id),
                started_at=started_at,
                outcome='transport_failure' if transport_failure else 'error',
            )
            _record_gateway_result(
                lane_id=lane_id,
                outcome='fallback' if transport_failure else 'error',
                reason='request_error',
                request_id=request_id,
            )
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


async def _web_search_authorized(uid: str, *, from_mode: str = 'anthropic_web_search') -> WebSearchAuthorization:
    try:
        settings = await run_blocking(db_executor, users_db.get_assistant_settings, uid)
    except Exception:
        record_fallback(
            component='other',
            from_mode=from_mode,
            to_mode='model_knowledge',
            reason='authorization_unavailable',
            outcome='degraded',
        )
        return 'unavailable'
    section = cast(Mapping[str, object], settings or {}).get(_WEB_SEARCH_SETTINGS_SECTION)
    if isinstance(section, Mapping) and section.get('enabled') is False:
        return 'denied'
    return 'authorized'


class _DesktopChatStreamOutcome:
    """Incrementally prove an OpenAI-compatible stream delivered an answer."""

    def __init__(self) -> None:
        self._buffer = bytearray()
        self.has_content = False
        self.has_terminal = False
        self.has_error = False

    def observe(self, item: object) -> None:
        if isinstance(item, str):
            chunk = item.encode('utf-8')
        elif isinstance(item, (bytes, bytearray, memoryview)):
            chunk = bytes(item)
        else:
            return
        self._buffer.extend(chunk)
        normalized = bytes(self._buffer).replace(b'\r\n', b'\n').replace(b'\r', b'\n')
        self._buffer = bytearray(normalized)
        while b'\n\n' in self._buffer:
            frame, _, remainder = self._buffer.partition(b'\n\n')
            self._buffer = bytearray(remainder)
            data = b'\n'.join(line[5:].lstrip() for line in frame.splitlines() if line.startswith(b'data:'))
            if not data:
                continue
            if data.strip() == b'[DONE]':
                self.has_terminal = True
                continue
            try:
                payload = json.loads(data)
            except (TypeError, ValueError):
                continue
            if isinstance(payload, Mapping):
                if payload.get('error'):
                    self.has_error = True
                if _desktop_chat_payload_has_content(payload):
                    self.has_content = True

    def failure_when(self, item: object) -> bool:
        self.observe(item)
        return self.has_error

    def success_when(self, _item: object) -> bool:
        return self.has_content and self.has_terminal


def _desktop_chat_payload_has_content(payload: Mapping[str, object]) -> bool:
    choices = payload.get('choices')
    if not isinstance(choices, list):
        return False
    for choice in choices:
        if not isinstance(choice, Mapping):
            continue
        message = choice.get('message')
        delta = choice.get('delta')
        for value in (message, delta):
            if not isinstance(value, Mapping):
                continue
            content = value.get('content')
            if isinstance(content, str) and content.strip():
                return True
            tool_calls = value.get('tool_calls')
            if isinstance(tool_calls, list) and tool_calls:
                return True
    return False


def _desktop_chat_issue_class(exc: BaseException) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return 'upstream_timeout'
    if isinstance(exc, HTTPException):
        if exc.status_code in {408, 504}:
            return 'upstream_timeout'
        if exc.status_code == 503:
            return 'dependency_unavailable'
        if exc.status_code >= 500:
            return 'provider_error'
        return 'upstream_rejected'
    if isinstance(exc, httpx.HTTPStatusError):
        return 'upstream_rejected'
    return 'provider_error'


def _desktop_chat_client_kind(x_app_platform: object, user_agent: object) -> ClientKind:
    headers: dict[str, str] = {}
    if isinstance(x_app_platform, str):
        headers['x-app-platform'] = x_app_platform
    if isinstance(user_agent, str):
        headers['user-agent'] = user_agent
    return resolve_client_kind_from_headers(headers)


async def _chat_completions_unobserved(
    body: dict[str, object],
    uid: str = Depends(auth.get_current_user_uid),
    x_app_platform: str | None = Header(None, alias='X-App-Platform'),
    x_omi_chat_contract_version: str | None = Header(None, alias='X-Omi-Chat-Contract-Version'),
    x_omi_request_id: str | None = Header(None, alias='X-Omi-Request-Id'),
    x_omi_jit_contract_version: str | None = None,
    x_omi_jit_run_id: str | None = None,
    x_omi_jit_max_attempts: str | None = None,
    x_omi_jit_max_output_tokens: str | None = None,
    x_omi_jit_max_input_tokens: str | None = None,
    x_omi_jit_max_spend_micro_usd: str | None = None,
) -> JSONResponse | StreamingResponse:
    if x_omi_chat_contract_version not in {None, '1'}:
        raise HTTPException(status_code=426, detail='Unsupported chat contract version')
    # Direct unit callers invoke the FastAPI endpoint without dependency
    # injection, so omitted Header defaults arrive as Param objects.  Treat
    # those as absent just as the HTTP adapter does; only actual strings may
    # activate the explicit JIT qualification capability.
    jit_header_values = tuple(
        value if isinstance(value, str) else None
        for value in (
            x_omi_jit_contract_version,
            x_omi_jit_run_id,
            x_omi_jit_max_attempts,
            x_omi_jit_max_output_tokens,
            x_omi_jit_max_input_tokens,
            x_omi_jit_max_spend_micro_usd,
        )
    )
    try:
        jit_headers = _jit_headers_for_forward(
            *jit_header_values,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    request_id = x_omi_request_id or str(uuid4())
    stub_headers = {
        'Cache-Control': 'no-cache',
        'X-Omi-Chat-Contract-Version': '1',
        'X-Request-Id': request_id,
    }
    # Hermetic offline profile: short-circuit before quota / Anthropic, matching
    # the retired Rust llm_stub intercept so T2 chat flows stay deterministic.
    if llm_stub_enabled() and not jit_headers:
        if body.get('stream') is True:
            return StreamingResponse(
                stub_chat_completions_stream(body),
                media_type='text/event-stream',
                headers=stub_headers,
            )
        return JSONResponse(stub_chat_completions_json(body), headers=stub_headers)
    payload: dict[str, object] = {}
    try:
        gateway_mode = should_route_chat_agent_through_gateway() and _uses_managed_chat_agent(body)
        if jit_headers and not gateway_mode:
            raise RuntimeError('JIT qualification requires the managed gateway')
        # A BYOK Anthropic key cannot serve the managed Luna thinking lane, so
        # thinking escalations stay on the gateway instead of falling back to
        # direct Anthropic (which would 400 on the Luna alias).
        if gateway_mode and not jit_headers and not _is_thinking_escalation(body) and get_byok_key('anthropic'):
            record_fallback(
                component='llm_gateway',
                from_mode='managed_gateway',
                to_mode='anthropic_byok',
                reason='byok',
                outcome='recovered',
            )
            gateway_mode = False
        if gateway_mode:
            public_model = _managed_lane_id(body)
            # Structured single-shot callers must not inherit the web-search
            # lane even if a leftover client still sets omi_web_search.
            if (
                public_model == CHAT_AGENT_AUTO_LANE_ID
                and not _is_thinking_escalation(body)
                and _web_search_requested(body)
            ):
                web_search_authorization = await _web_search_authorized(uid, from_mode='managed_web_search')
                if _web_search_eligible(body, authorization=web_search_authorization):
                    public_model = WEB_SEARCH_AUTO_LANE_ID
                else:
                    _record_web_search_withheld(
                        body,
                        authorization=web_search_authorization,
                        web_search_supported=True,
                        from_mode='managed_web_search',
                    )
            gateway_payload = _gateway_body(body, public_model)
        else:
            web_search_authorization = 'authorized' if _web_search_requested(body) else 'unavailable'
            if web_search_authorization == 'authorized':
                web_search_authorization = await _web_search_authorized(uid)
            public_model, payload = _request(body, web_search_authorization=web_search_authorization)
            gateway_payload = {}
        enforce_desktop_chat_quota(uid, platform=x_app_platform)
        await _meter_server_request(uid)
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if body.get('stream') is True:
        if gateway_mode:
            return StreamingResponse(
                _stream_gateway(gateway_payload, uid, request_id, x_app_platform, public_model, jit_headers),
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
                on_upstream_accepted=lambda: _record_chat_quota_question(uid, request_id, x_app_platform),
            ),
            media_type='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Omi-Chat-Contract-Version': '1',
                'X-Request-Id': request_id,
            },
        )
    if gateway_mode:
        usage_token = set_usage_context(uid, _gateway_feature_for_lane(public_model))
        started_at = time.monotonic()
        result_recorded = False
        try:
            if not gateway_circuit.allow_request():
                _record_gateway_result(
                    lane_id=public_model, outcome='error', reason='circuit_open', request_id=request_id
                )
                result_recorded = True
                raise HTTPException(status_code=503, detail='Upstream provider unavailable')
            async with get_llm_gateway_semaphore():
                response = await get_llm_gateway_client().post(
                    f'{get_llm_gateway_base_url()}/v1/chat/completions',
                    headers=_gateway_request_headers(request_id, public_model, x_app_platform, jit_headers),
                    json=gateway_payload,
                )
            response.raise_for_status()
            response_body = response.json()
            await _record_chat_quota_question(uid, request_id, x_app_platform)
            gateway_circuit.record_transport_success()
            observe_gateway_first_byte(
                feature=_gateway_feature_for_lane(public_model), started_at=started_at, outcome='success'
            )
            _record_gateway_result(lane_id=public_model, outcome='success', reason='ok', request_id=request_id)
            result_recorded = True
            await _record_usage(uid, _openai_usage_as_anthropic(response_body.get('usage')))
            response_headers = {
                'X-Omi-Chat-Contract-Version': '1',
                'X-Request-Id': request_id,
            }
            if jit_headers and response.headers.get('x-omi-jit-gateway-receipt'):
                response_headers['X-Omi-Jit-Gateway-Receipt'] = response.headers['x-omi-jit-gateway-receipt']
            return JSONResponse(
                response_body,
                headers=response_headers,
            )
        except HTTPException:
            raise
        except Exception as exc:
            if not result_recorded:
                transport_failure = is_gateway_transport_failure(exc)
                if transport_failure:
                    gateway_circuit.record_transport_failure()
                observe_gateway_first_byte(
                    feature=_gateway_feature_for_lane(public_model),
                    started_at=started_at,
                    outcome='transport_failure' if transport_failure else 'error',
                )
                _record_gateway_result(
                    lane_id=public_model,
                    outcome='fallback' if transport_failure else 'error',
                    reason='request_error',
                    request_id=request_id,
                )
            raise HTTPException(status_code=502, detail='Upstream provider error') from exc
        finally:
            reset_usage_context(usage_token)
    try:
        # The Anthropic SDK overloads do not accept this compatibility payload
        # typed as dict[str, object]; the request has already been normalized
        # and validated above, so keep the SDK boundary dynamic like _stream.
        direct_client: Any = get_direct_anthropic_client(byok_api_key=get_byok_key('anthropic'))
        message, usage, content = await _create_with_pause_turn_continuations(payload, client=direct_client)
    except _PauseTurnContinuationLimitError as exc:
        await _record_usage(uid, exc.usage)
        raise HTTPException(status_code=502, detail='Upstream provider error') from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail='Upstream provider error') from exc
    await _record_chat_quota_question(uid, request_id, x_app_platform)
    await _record_usage(uid, usage)
    return JSONResponse(
        _message_response(message, public_model, content_override=content, usage_override=usage),
        headers={
            'X-Omi-Chat-Contract-Version': '1',
            'X-Request-Id': request_id,
        },
    )


@router.post('/v2/chat/completions', response_model=None)
async def chat_completions(
    body: dict[str, object],
    uid: str = Depends(auth.get_current_user_uid),
    x_app_platform: str | None = Header(None, alias='X-App-Platform'),
    x_omi_chat_contract_version: str | None = Header(None, alias='X-Omi-Chat-Contract-Version'),
    x_omi_request_id: str | None = Header(None, alias='X-Omi-Request-Id'),
    x_omi_jit_contract_version: str | None = Header(None, alias='X-Omi-Jit-Contract-Version'),
    x_omi_jit_run_id: str | None = Header(None, alias='X-Omi-Jit-Run-Id'),
    x_omi_jit_max_attempts: str | None = Header(None, alias='X-Omi-Jit-Max-Attempts'),
    x_omi_jit_max_output_tokens: str | None = Header(None, alias='X-Omi-Jit-Max-Output-Tokens'),
    x_omi_jit_max_input_tokens: str | None = Header(None, alias='X-Omi-Jit-Max-Input-Tokens'),
    x_omi_jit_max_spend_micro_usd: str | None = Header(None, alias='X-Omi-Jit-Max-Spend-Micro-Usd'),
    user_agent: str | None = Header(None, alias='User-Agent'),
) -> JSONResponse | StreamingResponse:
    attempt = ClientJourneyAttempt(
        'desktop_chat',
        _desktop_chat_client_kind(x_app_platform, user_agent),
    )
    try:
        response = await _chat_completions_unobserved(
            body,
            uid=uid,
            x_app_platform=x_app_platform,
            x_omi_chat_contract_version=x_omi_chat_contract_version,
            x_omi_request_id=x_omi_request_id,
            x_omi_jit_contract_version=x_omi_jit_contract_version,
            x_omi_jit_run_id=x_omi_jit_run_id,
            x_omi_jit_max_attempts=x_omi_jit_max_attempts,
            x_omi_jit_max_output_tokens=x_omi_jit_max_output_tokens,
            x_omi_jit_max_input_tokens=x_omi_jit_max_input_tokens,
            x_omi_jit_max_spend_micro_usd=x_omi_jit_max_spend_micro_usd,
        )
    except asyncio.CancelledError:
        attempt.cancel()
        raise
    except Exception as exc:
        attempt.fail(_desktop_chat_issue_class(exc))
        raise

    if isinstance(response, StreamingResponse):
        outcome = _DesktopChatStreamOutcome()
        response.body_iterator = attempt.observe_stream(
            response.body_iterator,
            success_when=outcome.success_when,
            failure_when=outcome.failure_when,
            failure_class='provider_error',
            missing_success_class='empty_answer',
        )
        return response

    try:
        payload = json.loads(bytes(response.body))
    except (TypeError, ValueError):
        attempt.fail('invalid_response')
    else:
        if isinstance(payload, Mapping) and payload.get('error'):
            attempt.fail('provider_error')
        elif isinstance(payload, Mapping) and _desktop_chat_payload_has_content(payload):
            attempt.succeed()
        else:
            attempt.fail('empty_answer')
    return response

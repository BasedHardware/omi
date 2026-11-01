"""Gateway-owned cache defaults. Configuration contains no request or owner data."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from utils.llm.prompt_cache import EXPLICIT_CACHE_BREAKPOINT, EXPLICIT_CACHE_OPTIONS

POLICY_FILE = Path(__file__).resolve().parents[1] / 'config' / 'cache_policies.yaml'
INTERNAL_POLICY = '_gateway_cache_policy'


@lru_cache(maxsize=1)
def cache_policies() -> dict[str, Any]:
    with POLICY_FILE.open() as source:
        policies = yaml.safe_load(source)
    values = [policies['default'], *policies['lanes'].values(), *policies['prefixes'].values()]
    for provider_policy in policies.get('providers', {}).values():
        values.extend(provider_policy.get('lanes', {}).values())
        values.extend(provider_policy.get('prefixes', {}).values())
    for value in values:
        if value not in {'explicit', 'implicit', 'off'}:
            raise ValueError('Invalid gateway cache policy')
    return policies


def lane_cache_policy(lane: str, *, provider: str | None = None) -> str:
    policies = cache_policies()
    provider_policy = policies.get('providers', {}).get(provider, {}) if provider else {}
    if lane in provider_policy.get('lanes', {}):
        return provider_policy['lanes'][lane]
    for prefix, policy in provider_policy.get('prefixes', {}).items():
        if lane.startswith(prefix):
            return policy
    if lane in policies['lanes']:
        return policies['lanes'][lane]
    for prefix, policy in policies['prefixes'].items():
        if lane.startswith(prefix):
            return policy
    return policies['default']


def split_prefix(messages: list[Any], *, seed: bool = False) -> tuple[list[Any], list[Any]]:
    """Split at an explicit part boundary; otherwise use system or initial agent seed.

    Never manufacture an empty user message. Never reorder messages or split a
    tool-call/response pair. A marked prefix always wins over inferred policy.
    """
    for index, message in enumerate(messages):
        parts = message.get('content') if isinstance(message, Mapping) else None
        if not isinstance(parts, list):
            continue
        for part_index, part in enumerate(parts):
            if isinstance(part, Mapping) and 'prompt_cache_breakpoint' in part:
                prefix = copy.deepcopy(messages[:index])
                prefix.append({**message, 'content': copy.deepcopy(parts[: part_index + 1])})
                suffix = copy.deepcopy(messages[index + 1 :])
                if parts[part_index + 1 :]:
                    suffix.insert(0, {**message, 'content': copy.deepcopy(parts[part_index + 1 :])})
                return prefix, suffix
    boundary = 0
    for message in messages:
        if not isinstance(message, Mapping) or message.get('role') != 'system':
            break
        boundary += 1
    if seed and boundary < len(messages) and messages[boundary].get('role') == 'user':
        boundary += 1
    return copy.deepcopy(messages[:boundary]), copy.deepcopy(messages[boundary:])


def estimated_prefix_tokens(prefix: object, tools: object = None) -> int:
    # Heuristic only: provider minimum validation remains authoritative. Counting
    # serialized bytes as tokens dramatically overstates eligibility and budget.
    return len(json.dumps([prefix, tools], ensure_ascii=False, separators=(',', ':'))) // 4


def apply_lane_cache_policy(request: dict[str, Any], *, lane: str, provider: str, model: str) -> None:
    from utils.llm.model_config import uses_explicit_cache_and_chat_sanitizer

    policy = lane_cache_policy(lane, provider=provider)
    seed = lane in {'omi:auto:dream-reasoning', 'omi:auto:chat-agent'} or 'session' in lane
    messages = request.get('messages', [])
    prefix, _ = split_prefix(messages, seed=seed)
    estimate = estimated_prefix_tokens(prefix, request.get('tools')) if prefix else 0
    request[INTERNAL_POLICY] = {'lane': lane, 'mode': policy, 'prefix_tokens': estimate, 'seed': seed}
    if provider != 'openai' or not uses_explicit_cache_and_chat_sanitizer(model):
        return
    # Preserve deliberate caller opt-outs and markings; lane defaults fill only
    # absent choices. Off always strips markers and disables premium writes.
    if policy == 'off':
        request['prompt_cache_options'] = dict(EXPLICIT_CACHE_OPTIONS)
        request.pop('prompt_cache_key', None)
        for message in messages:
            if isinstance(message, dict) and isinstance(message.get('content'), list):
                for part in message['content']:
                    if isinstance(part, dict):
                        part.pop('prompt_cache_breakpoint', None)
        return
    if request.get('prompt_cache_options') is not None or request.get('prompt_cache_key') is not None:
        return
    if policy == 'explicit':
        request['prompt_cache_options'] = dict(EXPLICIT_CACHE_OPTIONS)
        if prefix and estimate >= 1024:
            prefix, suffix = split_prefix(messages, seed=seed)
            last = prefix[-1]
            content = last.get('content')
            if isinstance(content, str):
                last['content'] = [
                    {'type': 'text', 'text': content, 'prompt_cache_breakpoint': dict(EXPLICIT_CACHE_BREAKPOINT)}
                ]
            elif isinstance(content, list) and content:
                content[-1]['prompt_cache_breakpoint'] = dict(EXPLICIT_CACHE_BREAKPOINT)
            request['messages'] = prefix + suffix
            request['prompt_cache_key'] = (
                'gateway-'
                + hashlib.sha256(json.dumps([prefix, request.get('tools')], sort_keys=True).encode()).hexdigest()
            )


def provider_cache_request(request: Mapping[str, Any], *, owner: str | None) -> dict[str, Any]:
    """Remove gateway metadata and scope OpenAI routing keys to the authenticated owner."""
    body = dict(request)
    body.pop(INTERNAL_POLICY, None)
    if isinstance(body.get('prompt_cache_key'), str):
        if owner:
            body['prompt_cache_key'] = hashlib.sha256(
                json.dumps([owner, body['prompt_cache_key']]).encode()
            ).hexdigest()
        else:
            # Ownerless requests must never route onto another owner's cache.
            body.pop('prompt_cache_key', None)
            body['prompt_cache_options'] = dict(EXPLICIT_CACHE_OPTIONS)
    return body


def cache_owner_scope(caller: Any) -> str | None:
    """Bind both tenant and authenticated user; tenant collisions cannot share handles."""
    if not caller.user_uid:
        return None
    return json.dumps([caller.tenant_id, caller.user_uid], separators=(',', ':'))

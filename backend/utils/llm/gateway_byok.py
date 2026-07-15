"""BYOK credential envelope helpers for gateway-first routing."""

from __future__ import annotations

import hashlib
from typing import Any, Dict, Optional

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from utils.llm.gateway_client import get_llm_gateway_base_url, get_llm_gateway_service_token
from utils.llm.usage_tracker import get_usage_callback

_BYOK_GATEWAY_HEADER_PREFIX = 'X-Omi-Byok-'
_BYOK_GATEWAY_HEADER_SUFFIX = '-Key'

_usage_callback = get_usage_callback()

# Cache gateway BYOK LLM clients, bounded so a long-lived process serving many distinct BYOK keys
# (the cache key includes a per-key fingerprint) cannot grow this map of clients without limit.
_MAX_BYOK_GATEWAY_CLIENTS = 256
_byok_gateway_llm_cache: Dict[tuple[Any, ...], Any] = {}


def _remember_byok_client(cache_key: tuple[Any, ...], client: Any) -> None:
    # Re-inserting refreshes recency; evict the oldest entry once the cap is reached.
    _byok_gateway_llm_cache.pop(cache_key, None)
    while len(_byok_gateway_llm_cache) >= _MAX_BYOK_GATEWAY_CLIENTS:
        _byok_gateway_llm_cache.pop(next(iter(_byok_gateway_llm_cache)), None)
    _byok_gateway_llm_cache[cache_key] = client


def byok_gateway_header_name(provider: str) -> str:
    return f'{_BYOK_GATEWAY_HEADER_PREFIX}{provider.strip().lower()}{_BYOK_GATEWAY_HEADER_SUFFIX}'


def byok_gateway_default_headers(provider: str, api_key: str) -> dict[str, str]:
    return {byok_gateway_header_name(provider): api_key}


def get_or_create_omi_gateway_llm_for_byok(
    lane_id: str,
    *,
    provider: str,
    api_key: str,
    streaming: bool = False,
    options: Optional[Dict[str, Any]] = None,
):
    """Return a gateway-backed LangChain client that forwards the user's BYOK key."""

    options = options or {}
    base_url = f'{get_llm_gateway_base_url()}/v1'
    service_token = get_llm_gateway_service_token()
    default_headers: dict[str, str] = {
        'X-Omi-Service-Caller': 'backend',
        **byok_gateway_default_headers(provider, api_key),
    }
    if service_token:
        default_headers['Authorization'] = f'Bearer {service_token}'
    key_fingerprint = hashlib.sha256(api_key.encode()).hexdigest()[:16]
    service_token_cache_key = hashlib.sha256(service_token.encode()).hexdigest() if service_token else 'none'

    cache_key = (
        'omi_gateway_byok',
        lane_id,
        streaming,
        base_url,
        service_token_cache_key,
        provider,
        key_fingerprint,
        options.get('request_timeout', 120),
        options.get('max_retries', 1),
    )
    cached = _byok_gateway_llm_cache.get(cache_key)
    if cached is not None:
        return cached
    kwargs: Dict[str, Any] = {
        'api_key': SecretStr('omi-gateway-byok'),
        'base_url': base_url,
        'callbacks': [_usage_callback],
        'default_headers': default_headers,
        'request_timeout': options.get('request_timeout', 120),
        'max_retries': options.get('max_retries', 1),
    }
    if streaming:
        kwargs['streaming'] = True
        kwargs['stream_options'] = {'include_usage': True}
    client = ChatOpenAI(model=lane_id, **kwargs)
    _remember_byok_client(cache_key, client)
    return client

"""Dynamic OpenRouter model metadata catalog.

Product routing stays in ``model_config`` (feature → bare model + provider).
This module loads live OpenRouter model limits (context window, max completion
tokens, supported parameters) so request shaping can stay provider-accurate
without hardcoding numeric ceilings in route YAML.

Inspired by the thin registry shape in undivisible/rs_ai, but fed from
OpenRouter ``GET /api/v1/models`` rather than a static Rust catalog (rs_ai does
not expose context windows or pricing).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Mapping, Optional

import httpx

from utils.llm.openrouter_model_names import openrouter_provider_model_name

logger = logging.getLogger(__name__)

OPENROUTER_MODELS_URL = 'https://openrouter.ai/api/v1/models'
DEFAULT_TTL_SECONDS = 3600


@dataclass(frozen=True)
class OpenRouterModelLimits:
    model_id: str
    context_length: int | None
    max_completion_tokens: int | None
    supported_parameters: tuple[str, ...] = ()


class OpenRouterModelCatalog:
    """Process-local TTL cache of OpenRouter model limits."""

    def __init__(
        self,
        *,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        models_url: str = OPENROUTER_MODELS_URL,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._ttl_seconds = max(1, int(ttl_seconds))
        self._models_url = models_url
        self._transport = transport
        self._lock = threading.Lock()
        self._expires_at = 0.0
        self._models: dict[str, OpenRouterModelLimits] = {}

    def get(self, model_id: str) -> OpenRouterModelLimits | None:
        if not model_id:
            return None
        self._ensure_fresh()
        return self._models.get(model_id)

    def get_for_route(self, provider: str, model: str) -> OpenRouterModelLimits | None:
        return self.get(openrouter_provider_model_name(provider, model))

    def clamp_completion_tokens(self, model_id: str, requested: int | None) -> int | None:
        if requested is None:
            return None
        limits = self.get(model_id)
        if limits is None or limits.max_completion_tokens is None:
            return requested
        return min(requested, limits.max_completion_tokens)

    def _ensure_fresh(self) -> None:
        now = time.monotonic()
        if self._models and now < self._expires_at:
            return
        with self._lock:
            now = time.monotonic()
            if self._models and now < self._expires_at:
                return
            try:
                models = self._fetch_models()
            except Exception:
                logger.warning('OpenRouter model catalog refresh failed; keeping stale entries', exc_info=True)
                self._expires_at = now + min(60, self._ttl_seconds)
                return
            self._models = models
            self._expires_at = now + self._ttl_seconds

    def _fetch_models(self) -> dict[str, OpenRouterModelLimits]:
        headers = {'Accept': 'application/json'}
        api_key = os.getenv('OPENROUTER_API_KEY', '').strip()
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'
        with httpx.Client(timeout=10.0, transport=self._transport) as client:
            response = client.get(self._models_url, headers=headers)
            response.raise_for_status()
            payload = response.json()
        items = payload.get('data') if isinstance(payload, Mapping) else None
        if not isinstance(items, list):
            raise ValueError('OpenRouter models response missing data[]')
        models: dict[str, OpenRouterModelLimits] = {}
        for item in items:
            parsed = _parse_model_item(item)
            if parsed is not None:
                models[parsed.model_id] = parsed
        if not models:
            raise ValueError('OpenRouter models response contained no usable models')
        return models


def _parse_model_item(item: Any) -> OpenRouterModelLimits | None:
    if not isinstance(item, Mapping):
        return None
    model_id = item.get('id')
    if not isinstance(model_id, str) or not model_id:
        return None
    context_length = _positive_int(item.get('context_length'))
    top_provider = item.get('top_provider')
    max_completion_tokens = None
    if isinstance(top_provider, Mapping):
        max_completion_tokens = _positive_int(top_provider.get('max_completion_tokens'))
        if context_length is None:
            context_length = _positive_int(top_provider.get('context_length'))
    supported_raw = item.get('supported_parameters')
    supported: list[str] = []
    if isinstance(supported_raw, list):
        supported = [str(value) for value in supported_raw if isinstance(value, (str, int, float))]
    return OpenRouterModelLimits(
        model_id=model_id,
        context_length=context_length,
        max_completion_tokens=max_completion_tokens,
        supported_parameters=tuple(supported),
    )


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value > 0 else None


_catalog: OpenRouterModelCatalog | None = None
_catalog_lock = threading.Lock()


def get_openrouter_model_catalog() -> OpenRouterModelCatalog:
    global _catalog
    if _catalog is not None:
        return _catalog
    with _catalog_lock:
        if _catalog is None:
            ttl = _env_int('OMI_OPENROUTER_MODEL_CATALOG_TTL_SECONDS', DEFAULT_TTL_SECONDS)
            _catalog = OpenRouterModelCatalog(ttl_seconds=ttl)
        return _catalog


def reset_openrouter_model_catalog_for_tests() -> None:
    global _catalog
    with _catalog_lock:
        _catalog = None


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, '').strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def apply_openrouter_completion_clamp(
    provider_request: Mapping[str, Any],
    *,
    provider: str,
    model: str,
    catalog: Optional[OpenRouterModelCatalog] = None,
) -> dict[str, Any]:
    """Clamp OpenRouter completion caps using live model metadata when available."""
    request = dict(provider_request)
    if provider != 'openrouter':
        return request
    resolved_catalog = catalog or get_openrouter_model_catalog()
    model_id = openrouter_provider_model_name(provider, model)
    for key in ('max_completion_tokens', 'max_tokens'):
        value = request.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            clamped = resolved_catalog.clamp_completion_tokens(model_id, value)
            if clamped is not None:
                request[key] = clamped
    return request

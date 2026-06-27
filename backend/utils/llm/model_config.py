"""Model/profile configuration for backend LLM feature routing.

This module is the source of truth for feature → (model, provider) routing.
Provider-specific client construction lives in ``providers.py``; callers should
continue to use ``clients.get_llm(feature)``.
"""

import logging
import os
import time
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model QoS Profile System
#
# Each profile maps every feature to a (model, provider) tuple.
# The profile is the SINGLE SOURCE OF TRUTH for both model and provider.
# Provider is never inferred from model name — it is declared explicitly.
#
# This means the same model can be hosted by different providers:
#   feature_a: ('gemini-2.5-flash', 'gemini')      → Google direct
#   feature_b: ('gemini-2.5-flash', 'openrouter')   → OpenRouter
#
# Global switch:     MODEL_QOS=premium        (selects entire profile)
#
# Profiles:
#   premium  — maximize cost savings while preserving 80% of max quality
#   max      — 100% quality, best models available, no cost optimization
#   byok     — same models as max (BYOK users pay their own API costs)
# ---------------------------------------------------------------------------

MODEL_QOS_PROFILES: Dict[str, Dict[str, Tuple[str, str]]] = {
    # -----------------------------------------------------------------------
    # premium — maximize cost savings while preserving 80% of max quality.
    # Uses gpt-5.4-mini (not gpt-5.4) for core features, gpt-4.1-mini (not gpt-4.1)
    # for quality-sensitive tasks, gpt-4.1-nano for simple routing/classification,
    # and Gemini flash-lite for low-complexity free-text (titles, followups, onboarding).
    # -----------------------------------------------------------------------
    'premium': {
        # OpenAI — conversation processing
        'conv_action_items': ('gpt-5.4-mini', 'openai'),
        'conv_structure': ('gpt-5.4-mini', 'openai'),
        'conv_app_result': ('gpt-5.4-mini', 'openai'),
        'conv_app_select': ('gpt-4.1-nano', 'openai'),
        'conv_folder': ('gpt-4.1-nano', 'openai'),
        'conv_discard': ('gpt-4.1-nano', 'openai'),
        'daily_summary': ('gpt-5.4-mini', 'openai'),
        'daily_summary_simple': ('gpt-4.1-nano', 'openai'),
        'external_structure': ('gpt-4.1-mini', 'openai'),
        # OpenAI — memories & knowledge
        'memories': ('gpt-4.1-mini', 'openai'),
        'learnings': ('gpt-5.4-mini', 'openai'),
        'memory_conflict': ('gpt-4.1-mini', 'openai'),
        'memory_category': ('gpt-4.1-nano', 'openai'),
        'knowledge_graph': ('gpt-4.1-mini', 'openai'),
        # OpenAI — chat
        'chat_responses': ('gpt-5.4-mini', 'openai'),
        'chat_extraction': ('gpt-4.1-mini', 'openai'),
        'chat_graph': ('gpt-4.1-mini', 'openai'),
        'session_titles': ('gemini-2.5-flash-lite', 'gemini'),
        # Features
        'goals': ('gpt-4.1-mini', 'openai'),
        'goals_advice': ('gpt-5.4-mini', 'openai'),
        'notifications': ('gpt-5.4-mini', 'openai'),
        'proactive_notification': ('gpt-4.1-mini', 'openai'),
        'followup': ('gemini-2.5-flash-lite', 'gemini'),
        'smart_glasses': ('gpt-4.1-nano', 'openai'),
        'openglass': ('gpt-4.1-mini', 'openai'),
        'onboarding': ('gemini-2.5-flash-lite', 'gemini'),
        'app_generator': ('gpt-5.4-mini', 'openai'),
        'app_integration': ('gemini-2.5-flash-lite', 'gemini'),
        'persona_clone': ('gpt-5.4-mini', 'openai'),
        'trends': ('gemini-2.5-flash-lite', 'gemini'),
        # Anthropic (used via get_model() + anthropic_client)
        'chat_agent': ('claude-sonnet-4-6', 'anthropic'),
        # Persona
        'persona_chat': ('gpt-4.1-nano', 'openai'),
        'persona_chat_premium': ('gpt-5.4-mini', 'openai'),
        # OpenRouter
        'wrapped_analysis': ('gemini-3-flash-preview', 'openrouter'),
        # Perplexity
        'web_search': ('sonar-pro', 'perplexity'),
    },
    # -----------------------------------------------------------------------
    # max — 100% quality, best models available, no cost optimization.
    # Uses gpt-5.4 for all core features, o4-mini for reasoning (learnings),
    # gpt-4.1 for chat graph. Pure OpenAI for highest accuracy.
    # -----------------------------------------------------------------------
    'max': {
        # OpenAI — conversation processing
        'conv_action_items': ('gpt-5.4', 'openai'),
        'conv_structure': ('gpt-5.4', 'openai'),
        'conv_app_result': ('gpt-5.4', 'openai'),
        'conv_app_select': ('gpt-4.1-mini', 'openai'),
        'conv_folder': ('gpt-4.1-mini', 'openai'),
        'conv_discard': ('gpt-4.1-mini', 'openai'),
        'daily_summary': ('gpt-5.4', 'openai'),
        'daily_summary_simple': ('gpt-4.1-mini', 'openai'),
        'external_structure': ('gpt-4.1-mini', 'openai'),
        # OpenAI — memories & knowledge
        'memories': ('gpt-4.1-mini', 'openai'),
        'learnings': ('o4-mini', 'openai'),
        'memory_conflict': ('gpt-4.1-mini', 'openai'),
        'memory_category': ('gpt-4.1-mini', 'openai'),
        'knowledge_graph': ('gpt-4.1-mini', 'openai'),
        # OpenAI — chat
        'chat_responses': ('gpt-5.4', 'openai'),
        'chat_extraction': ('gpt-4.1-mini', 'openai'),
        'chat_graph': ('gpt-4.1', 'openai'),
        'session_titles': ('gpt-4.1-mini', 'openai'),
        # Features
        'goals': ('gpt-4.1-mini', 'openai'),
        'goals_advice': ('gpt-5.4', 'openai'),
        'notifications': ('gpt-5.4', 'openai'),
        'proactive_notification': ('gpt-4.1-mini', 'openai'),
        'followup': ('gpt-4.1-mini', 'openai'),
        'smart_glasses': ('gpt-4.1-mini', 'openai'),
        'openglass': ('gpt-4.1-mini', 'openai'),
        'onboarding': ('gpt-4.1-mini', 'openai'),
        'app_generator': ('gpt-5.4', 'openai'),
        'app_integration': ('gpt-4.1-mini', 'openai'),
        'persona_clone': ('gpt-5.4', 'openai'),
        'trends': ('gpt-4.1-mini', 'openai'),
        # Anthropic
        'chat_agent': ('claude-sonnet-4-6', 'anthropic'),
        # Persona
        'persona_chat': ('gpt-4.1-nano', 'openai'),
        'persona_chat_premium': ('gpt-5.4-mini', 'openai'),
        # OpenRouter
        'wrapped_analysis': ('gemini-3-flash-preview', 'openrouter'),
        # Perplexity
        'web_search': ('sonar-pro', 'perplexity'),
    },
    # -----------------------------------------------------------------------
    # byok — same models as max. BYOK users pay their own API costs so they
    # get the same best-quality routing as max subscribers.
    # -----------------------------------------------------------------------
    'byok': {
        # OpenAI — conversation processing
        'conv_action_items': ('gpt-5.4', 'openai'),
        'conv_structure': ('gpt-5.4', 'openai'),
        'conv_app_result': ('gpt-5.4', 'openai'),
        'conv_app_select': ('gpt-4.1-mini', 'openai'),
        'conv_folder': ('gpt-4.1-mini', 'openai'),
        'conv_discard': ('gpt-4.1-mini', 'openai'),
        'daily_summary': ('gpt-5.4', 'openai'),
        'daily_summary_simple': ('gpt-4.1-mini', 'openai'),
        'external_structure': ('gpt-4.1-mini', 'openai'),
        # OpenAI — memories & knowledge
        'memories': ('gpt-4.1-mini', 'openai'),
        'learnings': ('o4-mini', 'openai'),
        'memory_conflict': ('gpt-4.1-mini', 'openai'),
        'memory_category': ('gpt-4.1-mini', 'openai'),
        'knowledge_graph': ('gpt-4.1-mini', 'openai'),
        # OpenAI — chat
        'chat_responses': ('gpt-5.4', 'openai'),
        'chat_extraction': ('gpt-4.1-mini', 'openai'),
        'chat_graph': ('gpt-4.1', 'openai'),
        'session_titles': ('gpt-4.1-mini', 'openai'),
        # Features
        'goals': ('gpt-4.1-mini', 'openai'),
        'goals_advice': ('gpt-5.4', 'openai'),
        'notifications': ('gpt-5.4', 'openai'),
        'proactive_notification': ('gpt-4.1-mini', 'openai'),
        'followup': ('gpt-4.1-mini', 'openai'),
        'smart_glasses': ('gpt-4.1-mini', 'openai'),
        'openglass': ('gpt-4.1-mini', 'openai'),
        'onboarding': ('gpt-4.1-mini', 'openai'),
        'app_generator': ('gpt-5.4', 'openai'),
        'app_integration': ('gpt-4.1-mini', 'openai'),
        'persona_clone': ('gpt-5.4', 'openai'),
        'trends': ('gpt-4.1-mini', 'openai'),
        # Anthropic
        'chat_agent': ('claude-sonnet-4-6', 'anthropic'),
        # Persona
        'persona_chat': ('gpt-4.1-nano', 'openai'),
        'persona_chat_premium': ('gpt-5.4-mini', 'openai'),
        # OpenRouter
        'wrapped_analysis': ('gemini-3-flash-preview', 'openrouter'),
        # Perplexity
        'web_search': ('sonar-pro', 'perplexity'),
    },
}

# Pinned features — (model, provider) fixed regardless of profile or env override.
_PINNED_FEATURES: Dict[str, Tuple[str, str]] = {
    'fair_use': ('gpt-5.1', 'openai'),
}

# Resolve active profile once at startup.
_active_profile_name = os.environ.get('MODEL_QOS', 'premium').strip().lower()
if _active_profile_name not in MODEL_QOS_PROFILES:
    logger.warning('MODEL_QOS=%s is not a valid profile, falling back to premium', _active_profile_name)
    _active_profile_name = 'premium'
_active_profile = MODEL_QOS_PROFILES[_active_profile_name]

# BYOK QoS — all BYOK users get routed to 'byok' profile (top-tier all-OpenAI).
# BYOK users pay their own API costs, so we give them maximum quality models.
_byok_profile_name = 'byok'
_byok_profile = MODEL_QOS_PROFILES[_byok_profile_name]

# Features that can't go through get_llm() (non-ChatOpenAI providers).
_ANTHROPIC_ONLY_FEATURES = {'chat_agent'}
_PERPLEXITY_ONLY_FEATURES = {'web_search'}


# Feature-specific client config (temperature, headers — orthogonal to model choice).
# Only applied when a feature resolves to an OpenRouter model.
_OPENROUTER_TEMPERATURES: Dict[str, float] = {
    'wrapped_analysis': 0.7,
}

# Models that support OpenAI prompt caching (prompt_cache_key routing).
_CACHE_KEY_MODELS = {'gpt-5.4', 'gpt-5.4-mini'}

# Features that call .with_structured_output() — logged when resolving to Gemini for compat monitoring.
_STRUCTURED_OUTPUT_FEATURES = {
    'chat_extraction',
    'proactive_notification',
    'conv_app_select',
    'external_structure',
    'trends',
}

_DEFAULT_CONFIG: Tuple[str, str] = ('gpt-4.1-mini', 'openai')
_SUPPORTED_PROVIDERS = {'openai', 'gemini', 'openrouter', 'anthropic', 'perplexity'}


def _env_flag(name: str, default: str) -> bool:
    return os.environ.get(name, default).strip().lower() not in {'0', 'false', 'no', 'off'}


def _env_int(name: str, default: int, minimum: Optional[int] = None) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logger.warning('%s=%r is not an integer, falling back to %s', name, raw, default)
        return default
    if minimum is not None and value < minimum:
        logger.warning('%s=%s is below minimum %s, falling back to %s', name, value, minimum, default)
        return default
    return value


_DYNAMIC_ROUTE_REFRESH_SECONDS = _env_int('MODEL_AUTO_ROUTER_ROUTE_CACHE_SECONDS', 60, minimum=1)
_auto_router_enabled = _env_flag('MODEL_AUTO_ROUTER_ENABLED', 'true')
_dynamic_routes: Dict[str, Dict[str, Any]] = {}
_dynamic_routes_loaded_at = 0.0
_dynamic_route_loader: Optional[Callable[[str], Optional[Mapping[str, Any]]]] = None
_dynamic_routes_lock = RLock()


def set_dynamic_route_loader(loader: Optional[Callable[[str], Optional[Mapping[str, Any]]]]) -> None:
    """Register a lazy loader for persisted auto-router routes."""

    global _dynamic_route_loader, _dynamic_routes_loaded_at
    with _dynamic_routes_lock:
        _dynamic_route_loader = loader
        _dynamic_routes_loaded_at = 0.0


def set_dynamic_model_routes(route_payload: Optional[Mapping[str, Any]]) -> None:
    """Install an in-memory route table after validating every route."""

    global _dynamic_routes
    with _dynamic_routes_lock:
        _dynamic_routes = _normalize_dynamic_routes(route_payload)
        _reset_dynamic_route_timer()


def clear_dynamic_model_routes() -> None:
    set_dynamic_model_routes(None)


def is_auto_router_enabled() -> bool:
    return _auto_router_enabled


def get_active_dynamic_routes() -> Dict[str, Dict[str, Any]]:
    _maybe_refresh_dynamic_routes()
    with _dynamic_routes_lock:
        _prune_expired_dynamic_routes()
        return {feature: dict(route) for feature, route in _dynamic_routes.items()}


def get_dynamic_route_info(feature: str) -> Optional[Dict[str, Any]]:
    _maybe_refresh_dynamic_routes()
    with _dynamic_routes_lock:
        _prune_expired_dynamic_routes()
        route = _dynamic_routes.get(feature)
        return dict(route) if route else None


def _reset_dynamic_route_timer() -> None:
    global _dynamic_routes_loaded_at
    _dynamic_routes_loaded_at = time.monotonic()


def _maybe_refresh_dynamic_routes() -> None:
    if not _auto_router_enabled or _active_profile_name == _byok_profile_name:
        return
    loader = _dynamic_route_loader
    if loader is None:
        return
    now = time.monotonic()
    if now - _dynamic_routes_loaded_at < _DYNAMIC_ROUTE_REFRESH_SECONDS:
        return

    with _dynamic_routes_lock:
        if now - _dynamic_routes_loaded_at < _DYNAMIC_ROUTE_REFRESH_SECONDS:
            return
        try:
            route_payload = loader(_active_profile_name)
            _dynamic_routes.clear()
            _dynamic_routes.update(_normalize_dynamic_routes(route_payload))
        except Exception as e:
            logger.warning('Model auto-router route load failed: %s', e)
        finally:
            _reset_dynamic_route_timer()


def _normalize_dynamic_routes(route_payload: Optional[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    if not _auto_router_enabled or _active_profile_name == _byok_profile_name or not route_payload:
        return {}

    payload_profile = route_payload.get('profile') if isinstance(route_payload, Mapping) else None
    if payload_profile and payload_profile != _active_profile_name:
        return {}
    if _is_route_payload_expired(route_payload):
        return {}

    payload_expires_at = route_payload.get('expires_at') if isinstance(route_payload, Mapping) else None
    routes_obj = route_payload.get('routes') if isinstance(route_payload, Mapping) else None
    routes = routes_obj if isinstance(routes_obj, Mapping) else route_payload
    normalized: Dict[str, Dict[str, Any]] = {}
    for feature, route in routes.items():
        route_data = _route_to_dict(route)
        if not route_data:
            continue
        if payload_expires_at and 'expires_at' not in route_data:
            route_data['expires_at'] = payload_expires_at
        model = route_data.get('model')
        provider = route_data.get('provider')
        if _is_dynamic_route_allowed(feature, model, provider):
            normalized[feature] = route_data
    return normalized


def _route_to_dict(route: Any) -> Optional[Dict[str, Any]]:
    if isinstance(route, Mapping):
        model = route.get('model')
        provider = route.get('provider')
        if isinstance(model, str) and isinstance(provider, str):
            return dict(route)
        return None
    if isinstance(route, (list, tuple)) and len(route) == 2:
        model, provider = route
        if isinstance(model, str) and isinstance(provider, str):
            return {'model': model, 'provider': provider, 'source': 'auto-router'}
    return None


def _is_route_payload_expired(route_payload: Mapping[str, Any]) -> bool:
    expires_at = route_payload.get('expires_at')
    if not expires_at:
        return False
    parsed = _parse_datetime(expires_at)
    if parsed is None:
        return False
    return parsed < datetime.now(timezone.utc)


def _prune_expired_dynamic_routes() -> None:
    expired = [feature for feature, route in _dynamic_routes.items() if _is_route_payload_expired(route)]
    for feature in expired:
        _dynamic_routes.pop(feature, None)


def _parse_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _is_dynamic_route_allowed(feature: str, model: Any, provider: Any) -> bool:
    if feature in _PINNED_FEATURES:
        return False
    if feature not in _active_profile:
        return False
    if not isinstance(model, str) or not model.strip():
        return False
    if provider not in _SUPPORTED_PROVIDERS:
        return False

    static_provider = _active_profile[feature][1]
    if feature in _ANTHROPIC_ONLY_FEATURES:
        return provider == 'anthropic'
    if feature in _PERPLEXITY_ONLY_FEATURES:
        return provider == 'perplexity'
    if provider in {'anthropic', 'perplexity'}:
        return False
    if static_provider == 'openrouter':
        return provider == 'openrouter'
    if provider == 'openrouter':
        return False
    if feature in _STRUCTURED_OUTPUT_FEATURES and provider not in {'openai', 'gemini'}:
        return False
    return True


def _get_model_config(feature: str) -> Tuple[str, str]:
    """Get the (model, provider) tuple for a feature. Internal — used by get_llm/get_model/get_provider.

    Resolution order: pinned > dynamic auto-route > active profile > fallback.
    """
    if feature in _PINNED_FEATURES:
        return _PINNED_FEATURES[feature]
    route = get_dynamic_route_info(feature)
    if route:
        return route['model'], route['provider']
    return _active_profile.get(feature, _DEFAULT_CONFIG)


def get_model(feature: str) -> str:
    """Get the model name for a feature from the active Model QoS profile.

    Resolution order: pinned > active profile > fallback.

    Args:
        feature: Feature name (e.g. 'conv_action_items', 'chat_agent').

    Returns:
        Model name string (e.g. 'gpt-4.1-mini', 'claude-sonnet-4-6').
    """
    return _get_model_config(feature)[0]


def get_provider(feature: str) -> str:
    """Get the provider for a feature from the active Model QoS profile.

    Returns:
        Provider string: 'openai', 'gemini', 'openrouter', 'anthropic', 'perplexity'.
    """
    return _get_model_config(feature)[1]


def get_route_options(feature: str, model: str, provider: str) -> Dict[str, object]:
    """Return provider/model construction options for a resolved route."""

    options: Dict[str, object] = {}
    if model == 'gpt-5.1':
        options['extra_body'] = {"prompt_cache_retention": "24h"}
    if provider == 'openrouter':
        temperature = _OPENROUTER_TEMPERATURES.get(feature)
        if temperature is not None:
            options['temperature'] = temperature
    if provider == 'gemini':
        # Mechanical Gemini-routed features do not need paid thinking tokens.
        options['thinking_budget'] = 0
    return options


def supports_prompt_cache(model: str) -> bool:
    return model in _CACHE_KEY_MODELS


def is_structured_output_feature(feature: str) -> bool:
    return feature in _STRUCTURED_OUTPUT_FEATURES


def is_anthropic_only_feature(feature: str) -> bool:
    return feature in _ANTHROPIC_ONLY_FEATURES


def is_perplexity_only_feature(feature: str) -> bool:
    return feature in _PERPLEXITY_ONLY_FEATURES


def get_active_profile_name() -> str:
    return _active_profile_name


def get_active_profile() -> Dict[str, Tuple[str, str]]:
    return _active_profile


def get_all_configured_features() -> set[str]:
    return set(_active_profile.keys()) | set(_PINNED_FEATURES.keys())


def get_default_config() -> Tuple[str, str]:
    return _DEFAULT_CONFIG


def get_byok_profile() -> Dict[str, Tuple[str, str]]:
    return _byok_profile


def get_byok_profile_name() -> str:
    return _byok_profile_name

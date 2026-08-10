import os

from fastapi import APIRouter, HTTPException, status
from pydantic import ValidationError

from llm_gateway.gateway.auth import ServiceAuthDependency
from llm_gateway.gateway.config_loader import ConfigValidationError, GatewayConfig
from llm_gateway.gateway.schemas import Surface
from llm_gateway.routers.dependencies import get_gateway_config

router = APIRouter()


@router.get('/health')
def get_health() -> dict[str, str]:
    return {'status': 'healthy'}


@router.get('/ready')
def get_ready(caller: ServiceAuthDependency) -> dict[str, object]:
    try:
        config = get_gateway_config()
    except (ConfigValidationError, ValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='llm gateway config is invalid',
        ) from exc

    if _managed_anthropic_messages_enabled(config) and not os.getenv('ANTHROPIC_API_KEY', '').strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='llm gateway managed messages provider is not configured',
        )

    openrouter_chat = _managed_openrouter_chat_enabled(config)
    openai_chat = _managed_openai_chat_enabled(config)
    if openrouter_chat and not os.getenv('OPENROUTER_API_KEY', '').strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='llm gateway managed chat provider is not configured',
        )
    if openai_chat and not os.getenv('OPENAI_API_KEY', '').strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='llm gateway managed chat provider is not configured',
        )

    if openrouter_chat:
        managed_chat_provider = 'openrouter'
    elif openai_chat:
        managed_chat_provider = 'openai'
    else:
        managed_chat_provider = 'none'

    return {
        'status': 'ready',
        'lanes': sorted(config.lanes.keys()),
        'route_artifact_count': len(config.route_artifacts),
        # Keep the messages field backwards compatible; the desktop chat route
        # now has its own explicit provider readiness signal.
        'managed_messages_provider': 'anthropic' if _managed_anthropic_messages_enabled(config) else 'none',
        'managed_chat_provider': managed_chat_provider,
    }


def _managed_anthropic_messages_enabled(config: GatewayConfig) -> bool:
    for lane in config.lanes.values():
        route = config.route_artifacts.get(lane.active_route)
        if lane.surface == Surface.ANTHROPIC_MESSAGES and route is not None and route.primary.provider == 'anthropic':
            return True
    return False


def _managed_openrouter_chat_enabled(config: GatewayConfig) -> bool:
    for lane in config.lanes.values():
        route = config.route_artifacts.get(lane.active_route)
        if (
            lane.surface == Surface.OPENAI_CHAT_COMPLETIONS
            and route is not None
            and route.primary.provider == 'openrouter'
        ):
            return True
    return False


def _managed_openai_chat_enabled(config: GatewayConfig) -> bool:
    for lane in config.lanes.values():
        route = config.route_artifacts.get(lane.active_route)
        if lane.surface == Surface.OPENAI_CHAT_COMPLETIONS and route is not None and route.primary.provider == 'openai':
            return True
    return False

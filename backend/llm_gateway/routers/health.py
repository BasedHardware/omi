from fastapi import APIRouter, HTTPException, status

from llm_gateway.gateway.auth import ServiceAuthDependency
from llm_gateway.gateway.config_loader import ConfigValidationError
from llm_gateway.routers.dependencies import get_gateway_config

router = APIRouter()


@router.get('/health')
def get_health():
    return {'status': 'healthy'}


@router.get('/ready')
def get_ready(caller: ServiceAuthDependency):
    try:
        config = get_gateway_config()
    except ConfigValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='llm gateway config is invalid',
        ) from exc

    return {
        'status': 'ready',
        'lanes': sorted(config.lanes.keys()),
        'route_artifact_count': len(config.route_artifacts),
    }

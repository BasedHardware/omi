from __future__ import annotations

import hmac
import logging
import os
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from pydantic import Field, ValidationError, field_validator

from llm_gateway.gateway.metrics import observe_auth_rejection, report_observation_failure
from llm_gateway.gateway.request_context import request_id_for
from llm_gateway.gateway.schemas import StrictBaseModel

logger = logging.getLogger(__name__)

PRIMARY_SERVICE_TOKEN_ENV_VAR = 'OMI_LLM_GATEWAY_SERVICE_TOKEN'
LEGACY_SERVICE_TOKEN_ENV_VAR = 'LLM_GATEWAY_SERVICE_TOKEN'
# Kept for backwards compatibility with code/tests that reference the old name.
SERVICE_TOKEN_ENV_VAR = LEGACY_SERVICE_TOKEN_ENV_VAR
SERVICE_TOKEN_ENV_VARS = (PRIMARY_SERVICE_TOKEN_ENV_VAR, LEGACY_SERVICE_TOKEN_ENV_VAR)
ALLOWED_CALLERS_ENV_VAR = 'LLM_GATEWAY_ALLOWED_CALLERS'
DEFAULT_ALLOWED_CALLERS = frozenset({'backend', 'pusher'})

AUTHORIZATION_HEADER = 'authorization'
CALLER_HEADER = 'x-omi-service-caller'
USER_UID_HEADER = 'x-omi-user-uid'
TENANT_ID_HEADER = 'x-omi-tenant-id'


class ServiceCaller(StrictBaseModel):
    name: str = Field(min_length=1, max_length=64, pattern=r'^[a-z][a-z0-9_-]*$')
    user_uid: str | None = Field(default=None, min_length=1, max_length=256)
    tenant_id: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator('name', mode='before')
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator('user_uid', 'tenant_id', mode='before')
    @classmethod
    def normalize_optional_header(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


def require_service_auth(request: Request) -> ServiceCaller:
    expected_token = _configured_service_token()
    if expected_token is None:
        _record_auth_rejection(request, 'auth_not_configured')
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='llm gateway service auth is not configured',
        )

    supplied_token = _extract_bearer_token(request.headers.get(AUTHORIZATION_HEADER))
    if supplied_token is None or not hmac.compare_digest(supplied_token, expected_token):
        _record_auth_rejection(request, 'invalid_token')
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='invalid service authentication',
            headers={'WWW-Authenticate': 'Bearer'},
        )

    caller_name = request.headers.get(CALLER_HEADER)
    if caller_name is None or not caller_name.strip():
        _record_auth_rejection(request, 'missing_caller')
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='missing service caller')

    try:
        caller = ServiceCaller(
            name=caller_name,
            user_uid=request.headers.get(USER_UID_HEADER),
            tenant_id=request.headers.get(TENANT_ID_HEADER),
        )
    except ValidationError as exc:
        _record_auth_rejection(request, 'invalid_caller')
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='invalid service caller') from exc
    if caller.name not in allowed_service_callers():
        _record_auth_rejection(request, 'caller_not_allowed')
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='service caller is not allowed')

    return caller


def _record_auth_rejection(request: Request, reason: str) -> None:
    try:
        observe_auth_rejection(reason)
    except Exception:
        report_observation_failure(api_surface='service_auth', request_id=request_id_for(request))
    logger.warning(
        'llm_gateway_auth_rejected request_id=%s reason=%s',
        request_id_for(request),
        reason,
    )


ServiceAuthDependency = Annotated[ServiceCaller, Depends(require_service_auth)]


def allowed_service_callers() -> frozenset[str]:
    configured = os.getenv(ALLOWED_CALLERS_ENV_VAR)
    if configured is None or not configured.strip():
        return DEFAULT_ALLOWED_CALLERS
    callers = frozenset(item.strip().lower() for item in configured.split(',') if item.strip())
    return callers or DEFAULT_ALLOWED_CALLERS


def _configured_service_token() -> str | None:
    # Match the client precedence (utils.llm.gateway_client): the OMI_ prefixed
    # env var wins; the bare name is kept as a legacy fallback so local dev and
    # token rotation work even when the two disagree.
    for env_var in SERVICE_TOKEN_ENV_VARS:
        token = os.getenv(env_var)
        if token is not None:
            stripped = token.strip()
            if stripped:
                return stripped
    return None


def _extract_bearer_token(authorization: str | None) -> str | None:
    if authorization is None:
        return None
    scheme, separator, token = authorization.strip().partition(' ')
    if separator != ' ' or scheme.lower() != 'bearer':
        return None
    stripped = token.strip()
    return stripped or None

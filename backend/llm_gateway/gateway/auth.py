from __future__ import annotations

import hmac
import os
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from pydantic import Field, field_validator

from llm_gateway.gateway.schemas import StrictBaseModel

SERVICE_TOKEN_ENV_VAR = 'LLM_GATEWAY_SERVICE_TOKEN'
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
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='llm gateway service auth is not configured',
        )

    supplied_token = _extract_bearer_token(request.headers.get(AUTHORIZATION_HEADER))
    if supplied_token is None or not hmac.compare_digest(supplied_token, expected_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='invalid service authentication',
            headers={'WWW-Authenticate': 'Bearer'},
        )

    caller_name = request.headers.get(CALLER_HEADER)
    if caller_name is None or not caller_name.strip():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='missing service caller')

    caller = ServiceCaller(
        name=caller_name,
        user_uid=request.headers.get(USER_UID_HEADER),
        tenant_id=request.headers.get(TENANT_ID_HEADER),
    )
    if caller.name not in allowed_service_callers():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='service caller is not allowed')

    return caller


ServiceAuthDependency = Annotated[ServiceCaller, Depends(require_service_auth)]


def allowed_service_callers() -> frozenset[str]:
    configured = os.getenv(ALLOWED_CALLERS_ENV_VAR)
    if configured is None or not configured.strip():
        return DEFAULT_ALLOWED_CALLERS
    callers = frozenset(item.strip().lower() for item in configured.split(',') if item.strip())
    return callers or DEFAULT_ALLOWED_CALLERS


def _configured_service_token() -> str | None:
    token = os.getenv(SERVICE_TOKEN_ENV_VAR)
    if token is None:
        return None
    stripped = token.strip()
    return stripped or None


def _extract_bearer_token(authorization: str | None) -> str | None:
    if authorization is None:
        return None
    scheme, separator, token = authorization.strip().partition(' ')
    if separator != ' ' or scheme.lower() != 'bearer':
        return None
    stripped = token.strip()
    return stripped or None

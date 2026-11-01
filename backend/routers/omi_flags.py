"""Client feature flags resolved from the Omi flag store (replaces client PostHog `/flags` reads)."""

from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from utils import omi_flags
from utils.other.endpoints import get_current_user_uid

router = APIRouter()


class ClientFlag(BaseModel):
    key: str
    enabled: bool
    variant: str | None = Field(default=None, description='Multivariate value when enabled; null for boolean flags')
    payload_json: str | None = Field(default=None, description='JSON-encoded payload when enabled')


class ClientFlagsResponse(BaseModel):
    version: int | None = Field(description='Store version; null when the store is unconfigured or unreadable')
    flags: list[ClientFlag] = Field(
        description='Only keys the Omi store owns. A key not listed keeps the client\'s previous source.'
    )


@router.get('/v1/flags', response_model=ClientFlagsResponse)
def client_flags(
    surface: Literal['macos', 'mobile', 'web-app', 'windows'] = Query(...),
    uid: str = Depends(get_current_user_uid),
) -> ClientFlagsResponse:
    # In-memory evaluation; the snapshot refresh is bounded by the store read timeout.
    version, resolved = omi_flags.resolve_surface(uid, surface)
    return ClientFlagsResponse(
        version=version,
        flags=[
            ClientFlag(key=key, enabled=r.enabled, variant=r.variant, payload_json=r.payload)
            for key, r in resolved.items()
        ],
    )

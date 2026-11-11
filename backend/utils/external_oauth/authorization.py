"""Two-authority authorization composition for semantic provider operations."""

from __future__ import annotations

from typing import Awaitable, Callable

from utils.external_oauth.contracts import (
    Capability,
    ConnectionState,
    Connector,
    ExternalConnectionRepository,
    SecretLeaseContext,
    SecretPurpose,
)
from utils.external_oauth.scopes import GRANT_FAMILIES

ProductCapabilityCheck = Callable[[str, Capability], Awaitable[bool]]


class RepositoryAuthorizationComposer:
    def __init__(self, *, repository: ExternalConnectionRepository, product_capability_check: ProductCapabilityCheck):
        self._repository = repository
        self._product_capability_check = product_capability_check

    async def authorize(
        self, *, external_owner_id: str, connector: Connector, capability: Capability, operation_id: str
    ) -> SecretLeaseContext:
        if GRANT_FAMILIES[connector].capability != capability:
            raise PermissionError('connector does not implement requested product capability')
        if not await self._product_capability_check(external_owner_id, capability):
            raise PermissionError('product capability is not authorized')
        connection = await self._repository.get(external_owner_id=external_owner_id, connector=connector)
        if connection is None or connection.state != ConnectionState.ACTIVE:
            raise PermissionError('provider grant is not active')
        return SecretLeaseContext(
            connection_id=connection.connection_id,
            generation=connection.generation,
            deletion_epoch=connection.deletion_epoch,
            operation_id=operation_id,
            purpose=SecretPurpose.READ,
        )

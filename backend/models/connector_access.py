"""Wire contract for connector scope requirements and minting defaults."""

from pydantic import BaseModel

from config.mcp_scopes import CONNECTOR_ACCESS_REGISTRY


class ConnectorAccess(BaseModel):
    client_ids: list[str]
    required_scopes: list[str]
    default_scopes: list[str]


def connector_access(connector: str) -> ConnectorAccess:
    return ConnectorAccess.model_validate(CONNECTOR_ACCESS_REGISTRY[connector])

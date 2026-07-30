"""MCP key create stamps product only from X-App-Product."""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from models.mcp_api_key import McpApiKeyCreate, McpApiKeyDB
from routers.api_key_management import create_mcp_key


def _fake_key(product=None):
    return (
        "omi_mcp_raw",
        McpApiKeyDB(
            id="k1",
            name="Context",
            key_prefix="omi_mcp_",
            created_at=datetime.now(timezone.utc),
            user_id="u1",
            hashed_key="hash",
            product=product,
        ),
    )


def test_create_stamps_product_from_header():
    with patch(
        "routers.api_key_management.mcp_api_key_db.create_mcp_key", return_value=_fake_key("context-for-claude")
    ) as create:
        created = create_mcp_key(
            McpApiKeyCreate(name="Context"),
            uid="u1",
            x_app_product="context-for-claude",
        )
    create.assert_called_once_with("u1", "Context", product="context-for-claude")
    assert created.product == "context-for-claude"


def test_create_rejects_body_only_product():
    with pytest.raises(HTTPException) as exc:
        create_mcp_key(
            McpApiKeyCreate(name="Context", product="context-for-claude"),
            uid="u1",
            x_app_product=None,
        )
    assert exc.value.status_code == 422


def test_create_rejects_body_header_mismatch():
    with pytest.raises(HTTPException) as exc:
        create_mcp_key(
            McpApiKeyCreate(name="Context", product="omi-desktop"),
            uid="u1",
            x_app_product="context-for-claude",
        )
    assert exc.value.status_code == 422


def test_create_without_product_stamps_none():
    with patch("routers.api_key_management.mcp_api_key_db.create_mcp_key", return_value=_fake_key(None)) as create:
        create_mcp_key(McpApiKeyCreate(name="Generic"), uid="u1", x_app_product=None)
    create.assert_called_once_with("u1", "Generic", product=None)

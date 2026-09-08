from pathlib import Path
from unittest.mock import MagicMock

from fastapi import HTTPException
import pytest

from database.api_key_metadata import ApiKeyRevocationUnavailableError, ApiKeyValidationError
from routers import api_key_management as routes

BACKEND_DIR = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("router", "expected"),
    [
        (
            routes.mcp_router,
            {
                ("/v1/mcp/keys", "GET"): ("mcp", "get_keys_v1_mcp_keys_get", "Get Keys"),
                ("/v1/mcp/keys", "POST"): ("mcp", "create_key_v1_mcp_keys_post", "Create Key"),
                ("/v1/mcp/keys/{key_id}", "DELETE"): (
                    "mcp",
                    "delete_key_v1_mcp_keys__key_id__delete",
                    "Delete Key",
                ),
            },
        ),
        (
            routes.developer_router,
            {
                ("/v1/dev/keys", "GET"): ("API Keys", "listApiKeys", "Get Keys"),
                ("/v1/dev/keys", "POST"): ("API Keys", "createApiKey", "Create Key"),
                ("/v1/dev/keys/{key_id}", "DELETE"): ("API Keys", "revokeApiKey", "Delete Key"),
            },
        ),
    ],
)
def test_lifecycle_route_metadata_and_auth_dependencies_are_stable(router, expected):
    actual = {}
    for route in router.routes:
        method = next(iter(route.methods))
        actual[(route.path, method)] = (route.tags[0], route.unique_id, route.summary)
        assert [dependency.call for dependency in route.dependant.dependencies] == [routes.get_current_user_id]

    assert actual == expected


def test_lifecycle_routers_are_composed_only_at_main_boundary():
    main_source = (BACKEND_DIR / "main.py").read_text(encoding="utf-8")
    assert "api_key_management," in main_source
    assert "app.include_router(api_key_management.mcp_router)" in main_source
    assert "app.include_router(api_key_management.developer_router)" in main_source

    for leaf_router in ("mcp.py", "developer.py"):
        leaf_source = (BACKEND_DIR / "routers" / leaf_router).read_text(encoding="utf-8")
        assert "api_key_management" not in leaf_source


@pytest.mark.parametrize(
    ("handler", "database_module", "delete_name", "key_kind"),
    [
        (routes.delete_mcp_key, routes.mcp_api_key_db, "delete_mcp_key", "mcp"),
        (routes.delete_developer_key, routes.dev_api_key_db, "delete_dev_key", "dev"),
    ],
)
def test_delete_routes_map_only_typed_revocation_failures_to_one_exhausted_503(
    monkeypatch,
    handler,
    database_module,
    delete_name,
    key_kind,
):
    delete = MagicMock(side_effect=ApiKeyRevocationUnavailableError("internal cache detail"))
    exhausted = MagicMock()
    monkeypatch.setattr(database_module, delete_name, delete)
    monkeypatch.setattr(routes, "record_api_key_revocation_exhausted", exhausted)

    with pytest.raises(HTTPException) as caught:
        handler("key-1", uid="user-1")

    assert caught.value.status_code == 503
    assert caught.value.detail == "API key revocation temporarily unavailable"
    delete.assert_called_once_with("user-1", "key-1")
    exhausted.assert_called_once_with(key_kind=key_kind, log=routes.logger)


@pytest.mark.parametrize(
    ("handler", "database_module", "create_name", "payload"),
    [
        (routes.create_mcp_key, routes.mcp_api_key_db, "create_mcp_key", routes.McpApiKeyCreate(name="safe")),
        (
            routes.create_developer_key,
            routes.dev_api_key_db,
            "create_dev_key",
            routes.DevApiKeyCreate(name="safe"),
        ),
    ],
)
def test_create_routes_map_only_typed_caller_validation_to_422(
    monkeypatch,
    handler,
    database_module,
    create_name,
    payload,
):
    create = MagicMock(side_effect=ApiKeyValidationError("safe caller detail"))
    monkeypatch.setattr(database_module, create_name, create)

    with pytest.raises(HTTPException) as caught:
        handler(payload, uid="user-1")

    assert caught.value.status_code == 422
    assert caught.value.detail == "safe caller detail"


@pytest.mark.parametrize(
    ("handler", "database_module", "create_name", "payload"),
    [
        (routes.create_mcp_key, routes.mcp_api_key_db, "create_mcp_key", routes.McpApiKeyCreate(name="safe")),
        (
            routes.create_developer_key,
            routes.dev_api_key_db,
            "create_dev_key",
            routes.DevApiKeyCreate(name="safe"),
        ),
    ],
)
def test_create_routes_do_not_publish_generic_persistence_value_errors_as_422(
    monkeypatch,
    handler,
    database_module,
    create_name,
    payload,
):
    create = MagicMock(side_effect=ValueError("internal persistence detail"))
    monkeypatch.setattr(database_module, create_name, create)

    with pytest.raises(ValueError, match="internal persistence detail"):
        handler(payload, uid="user-1")

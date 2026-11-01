from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers.retired_app_client_contracts import router
from utils.other.endpoints import get_current_user_uid


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user_uid] = lambda: "test-user"
    return TestClient(app)


def test_retired_jit_operations_return_gone_without_parsing_or_side_effects():
    client = _client()
    retired = [
        ("get", "/v1/jit/knowledge-ledger/prompt-snapshot"),
        ("get", "/v1/jit/knowledge-ledger/mirror-snapshot?cursor=old&page_size=25"),
        ("get", "/v1/jit/rollout-decision"),
        ("get", "/v1/jit/trigger-snapshot"),
        ("post", "/v1/jit/trigger-feedback"),
        ("post", "/v1/jit/proactivity/reservations"),
        ("post", "/v3/memories/old-memory/use"),
        ("get", "/v1/frame-requests/temporary/old-request/image?account_generation=2"),
    ]

    for method, path in retired:
        response = client.request(method, path, content=b"not json")
        assert response.status_code == 410
        assert response.headers["cache-control"] == "no-store"


def test_retired_write_operations_keep_the_released_request_boundary_in_openapi():
    schema = _client().get("/openapi.json").json()
    for path in (
        "/v1/jit/trigger-feedback",
        "/v1/jit/proactivity/reservations",
        "/v3/memories/{memory_id}/use",
    ):
        operation = schema["paths"][path]["post"]
        assert operation["requestBody"]["required"] is True
        assert operation["requestBody"]["content"]["application/json"]["schema"]["additionalProperties"] is True

"""Tests for sanitised error handling in ``backend.routers.memory_product``."""

from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
import pytest

# Router under test
from backend.routers.memory_product import router as memory_router

# Dependency that the router uses to obtain a MemoryService instance.
from backend.services.memory_service import get_memory_service, MemoryService


# --------------------------------------------------------------------------- #
# Mock service that deliberately raises ValueError for each method.
# --------------------------------------------------------------------------- #
class _ErrorRaisingMemoryService(MemoryService):
    async def search_product(self, *_, **__) -> None:
        raise ValueError("memory item uid mismatch: expected 1, got 2")

    async def search_vector(self, *_, **__) -> None:
        raise ValueError("document id mismatch")

    async def search_archive(self, *_, **__) -> None:
        raise ValueError("some internal error")


def _override_memory_service() -> MemoryService:
    """Dependency override returning the mock service."""
    return _ErrorRaisingMemoryService()


# --------------------------------------------------------------------------- #
# Test fixture – FastAPI app with the router and overridden dependency.
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def client() -> TestClient:
    app = FastAPI()
    # Override the service dependency used by the router.
    app.dependency_overrides[get_memory_service] = _override_memory_service
    app.include_router(memory_router)
    return TestClient(app)


# --------------------------------------------------------------------------- #
# Helper assertion – all error responses must be sanitised.
# --------------------------------------------------------------------------- #
def _assert_sanitised_400(response):
    assert response.status_code == 400
    json_body = response.json()
    # FastAPI returns {"detail": "..."} for HTTPException.
    assert json_body.get("detail") == "Invalid request parameters"


# --------------------------------------------------------------------------- #
# Individual endpoint tests.
# --------------------------------------------------------------------------- #
def test_search_product_memory_error_is_sanitised(client: TestClient):
    resp = client.get(
        "/search_product",
        params={"uid": "user-1", "query": "test"},
    )
    _assert_sanitised_400(resp)


def test_search_vector_memory_error_is_sanitised(client: TestClient):
    resp = client.get(
        "/search_vector",
        params={"uid": "user-1", "vector_id": "vec-123"},
    )
    _assert_sanitised_400(resp)


def test_search_archive_memory_error_is_sanitised(client: TestClient):
    resp = client.get(
        "/search_archive",
        params={"uid": "user-1", "archive_id": "arch-456"},
    )
    _assert_sanitised_400(resp)

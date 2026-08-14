"""Universal DELETE /v3/memories/batch contract tests."""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from routers import memories as mem_mod


def _service(monkeypatch, *, error=None):
    service = MagicMock()
    if error is not None:
        service.delete_batch.side_effect = error
    monkeypatch.setattr(mem_mod, "MemoryService", lambda **_kwargs: service)
    return service


def test_batch_delete_deduplicates_ids_and_calls_universal_service_once(monkeypatch):
    service = _service(monkeypatch)
    result = mem_mod.delete_memories_batch(
        data=mem_mod.BatchDeleteMemoriesRequest(memory_ids=["a", "a", "b", "a"]), uid="uid-former-cohort"
    )
    assert result == {"status": "ok"}
    service.delete_batch.assert_called_once_with("uid-former-cohort", ["a", "b"])
    service.delete.assert_not_called()


def test_batch_delete_is_empty_noop_without_service_mutation(monkeypatch):
    service = _service(monkeypatch)
    result = mem_mod.delete_memories_batch(data=mem_mod.BatchDeleteMemoriesRequest(memory_ids=[]), uid="uid-any")
    assert result == {"status": "ok"}
    service.delete_batch.assert_not_called()


@pytest.mark.parametrize("status_code", [402, 404, 413])
def test_batch_delete_preserves_service_error_mapping(monkeypatch, status_code):
    service = _service(monkeypatch, error=HTTPException(status_code=status_code, detail=f"status-{status_code}"))
    with pytest.raises(HTTPException) as error:
        mem_mod.delete_memories_batch(
            data=mem_mod.BatchDeleteMemoriesRequest(memory_ids=["valid", "locked-or-missing"]), uid="uid-arbitrary"
        )
    assert error.value.status_code == status_code
    assert error.value.detail == f"status-{status_code}"
    service.delete_batch.assert_called_once_with("uid-arbitrary", ["valid", "locked-or-missing"])


def test_batch_delete_maps_unexpected_value_error_to_not_found(monkeypatch):
    service = _service(monkeypatch, error=ValueError("memory not found"))
    with pytest.raises(HTTPException) as error:
        mem_mod.delete_memories_batch(
            data=mem_mod.BatchDeleteMemoriesRequest(memory_ids=["missing"]), uid="uid-arbitrary"
        )
    assert error.value.status_code == 404


def test_batch_delete_route_has_no_legacy_or_mirror_mutation():
    source = mem_mod.__file__ and open(mem_mod.__file__, encoding="utf-8").read()
    start = source.index("def delete_memories_batch")
    route = source[start : source.index("def delete_memory(", start + 1)]
    assert "service.delete_batch(uid, memory_ids)" in route
    assert "service.delete(uid, memory_id)" not in route
    assert "memories_db" not in route
    assert "delete_memory_vectors" not in route
    assert "_mirror_delete" not in source


def test_batch_delete_request_model_preserves_released_limit_and_empty_contract():
    assert mem_mod.MEMORIES_BATCH_DELETE_MAX == 100
    assert len(mem_mod.BatchDeleteMemoriesRequest(memory_ids=[f"m{i}" for i in range(100)]).memory_ids) == 100
    assert mem_mod.BatchDeleteMemoriesRequest(memory_ids=[]).memory_ids == []
    with pytest.raises(ValidationError):
        mem_mod.BatchDeleteMemoriesRequest(memory_ids=[f"m{i}" for i in range(101)])


def test_batch_delete_rate_limit_and_route_order_are_preserved():
    from utils.rate_limit_config import RATE_POLICIES

    assert RATE_POLICIES["memories:delete_batch"] == (10, 3600)
    delete_paths = [route.path for route in mem_mod.router.routes if "DELETE" in getattr(route, "methods", set())]
    assert delete_paths.index("/v3/memories/batch") < delete_paths.index("/v3/memories/{memory_id}")

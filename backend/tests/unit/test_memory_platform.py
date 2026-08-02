import pytest
from pydantic import ValidationError

from models.memory_platform import MemoryPlatformCapability
from utils.memory.platform import build_memory_platform_capability


def test_memory_platform_capability_declares_backend_authority_and_canonical_store():
    capability = build_memory_platform_capability()

    assert capability.authority == "omi_backend"
    assert capability.canonical_store.kind == "firestore"
    assert capability.canonical_store.collection == "memory_items"
    assert capability.canonical_store.apply_control == "memory_state/apply_control"


def test_memory_platform_capability_exposes_rest_mcp_and_zkr_contracts():
    capability = build_memory_platform_capability()

    assert capability.surfaces.rest == "GET /v1/memory/platform"
    assert capability.surfaces.mcp == "memory_platform"
    assert capability.surfaces.rest == "GET /v1/memory/platform"
    assert capability.surfaces.mcp == "memory_platform"
    assert capability.zkr.model_dump() == {
        "export_format": 1,
        "replica_role": "mirror",
        "write_mode": "backend_ingest",
        "sync_implemented": False,
    }


def test_memory_platform_contract_rejects_authority_changes():
    with pytest.raises(ValidationError):
        MemoryPlatformCapability(authority="zkr")

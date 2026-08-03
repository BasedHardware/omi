from typing import Literal

from pydantic import BaseModel, ConfigDict

MemoryAuthority = Literal["omi_backend"]
FirestoreStoreKind = Literal["firestore"]
MemoryItemsCollection = Literal["memory_items"]
ApplyControlPath = Literal["memory_state/apply_control"]
RestSurfaceName = Literal["GET /v1/memory/platform"]
McpSurfaceName = Literal["memory_platform"]
ZkrExportFormat = Literal[1]
ZkrReplicaRole = Literal["mirror"]
ZkrWriteMode = Literal["backend_ingest"]


class MemoryCanonicalStore(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: FirestoreStoreKind = "firestore"
    collection: MemoryItemsCollection = "memory_items"
    apply_control: ApplyControlPath = "memory_state/apply_control"


class MemorySurfaceNames(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rest: RestSurfaceName = "GET /v1/memory/platform"
    mcp: McpSurfaceName = "memory_platform"


class ZkrCompatibility(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    export_format: ZkrExportFormat = 1
    replica_role: ZkrReplicaRole = "mirror"
    write_mode: ZkrWriteMode = "backend_ingest"
    sync_implemented: Literal[False] = False


class MemoryPlatformCapability(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    authority: MemoryAuthority = "omi_backend"
    canonical_store: MemoryCanonicalStore = MemoryCanonicalStore()
    surfaces: MemorySurfaceNames = MemorySurfaceNames()
    zkr: ZkrCompatibility = ZkrCompatibility()


class MemoryPlatformIngestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    memory_id: str
    status: Literal["created"] = "created"


MemoryPlatformContract = MemoryPlatformCapability


__all__ = [
    "ApplyControlPath",
    "FirestoreStoreKind",
    "MemoryAuthority",
    "MemoryCanonicalStore",
    "MemoryItemsCollection",
    "MemoryPlatformCapability",
    "MemoryPlatformContract",
    "MemoryPlatformIngestResponse",
    "MemorySurfaceNames",
    "McpSurfaceName",
    "RestSurfaceName",
    "ZkrCompatibility",
    "ZkrExportFormat",
    "ZkrReplicaRole",
    "ZkrWriteMode",
]

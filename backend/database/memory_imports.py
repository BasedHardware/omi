from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from database.document_ids import document_id_from_seed
from database.memory_collections import MemoryCollections
from database.store import get_document_store
from database.store.errors import AlreadyExists
from database.store.sentinels import Increment
from models.memory_imports import (
    MemoryImportArtifact,
    MemoryImportArtifactSourceState,
    MemoryImportBatchItem,
    MemoryImportBatchRequest,
    MemoryImportBatchResponse,
    MemoryImportRunStatus,
    utc_now,
)

MEMORY_IMPORT_BODY_STORAGE_MODE_ENV = "MEMORY_IMPORT_BODY_STORAGE_MODE"


def _store():
    return get_document_store()


@dataclass(frozen=True)
class MemoryImportIngestResult:
    response: MemoryImportBatchResponse


def _normalized_source_type(source_type: str) -> str:
    return "_".join((source_type or "").strip().lower().replace("-", "_").split())


def _stable_content_hash(item: MemoryImportBatchItem) -> str:
    if item.content_hash:
        return item.content_hash
    hasher = hashlib.sha256()
    for value in [item.title, item.snippet, item.content]:
        if value:
            hasher.update(value.encode("utf-8"))
            hasher.update(b"\0")
    return hasher.hexdigest()


def _body_storage_mode() -> str:
    mode = (os.getenv(MEMORY_IMPORT_BODY_STORAGE_MODE_ENV) or "summary").strip().lower()
    return mode if mode in {"summary", "full"} else "summary"


def _safe_client_document_id(uid: str, value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,149}", value):
        return value
    return document_id_from_seed(f"memory-import-client-document-id|{uid}|{value}")


def _artifact_id(uid: str, source_type: str, source_account_hash: Optional[str], item: MemoryImportBatchItem) -> str:
    content_hash = _stable_content_hash(item)
    identity = "|".join(
        [
            source_account_hash or "",
            item.external_id or "",
            content_hash,
        ]
    )
    return document_id_from_seed(f"memory-import-artifact|{uid}|{source_type}|{identity}")


def _run_id(uid: str, request: MemoryImportBatchRequest) -> str:
    if request.import_run_id:
        return _safe_client_document_id(uid, request.import_run_id)
    seed = "|".join(
        [
            "memory-import-run",
            uid,
            _normalized_source_type(request.source_type),
            request.source_account_hash or "",
            request.importer_version,
        ]
    )
    return document_id_from_seed(seed)


def ingest_memory_import_batch(
    uid: str,
    request: MemoryImportBatchRequest,
    *,
    now: Optional[datetime] = None,
) -> MemoryImportIngestResult:
    """Persist import artifacts only; never create product memories or indexes."""
    current_time: datetime = now or utc_now()
    source_type = _normalized_source_type(request.source_type)
    run_id = _run_id(uid, request)
    collections = MemoryCollections(uid=uid)
    store_full_body = _body_storage_mode() == "full"

    created = 0
    deduped = 0
    for item in request.items:
        content_hash = _stable_content_hash(item)
        artifact_id = _artifact_id(uid, source_type, request.source_account_hash, item)
        artifact_path = f"{collections.memory_import_artifacts}/{artifact_id}"
        artifact = MemoryImportArtifact(
            artifact_id=artifact_id,
            uid=uid,
            run_id=run_id,
            source_type=source_type,
            external_id=item.external_id,
            content_hash=content_hash,
            title=item.title,
            snippet=item.snippet,
            redacted_body=item.content if store_full_body else None,
            metadata=dict(item.metadata or {}),
            occurred_at=item.occurred_at,
            captured_at=current_time,
            client_device_id=item.client_device_id,
            redaction_status="importer_full_excerpt" if store_full_body else "title_snippet_only",
            created_at=current_time,
            updated_at=current_time,
        )
        try:
            _store().create(artifact_path, artifact.model_dump(mode="json"))
            created += 1
            continue
        except AlreadyExists:
            deduped += 1
            _store().set(
                artifact_path,
                {
                    "run_id": run_id,
                    "source_state": MemoryImportArtifactSourceState.active.value,
                    "updated_at": current_time.isoformat(),
                },
                merge=True,
            )
            continue

    run_path = f"{collections.memory_import_runs}/{run_id}"
    try:
        _store().create(
            run_path,
            {
                "run_id": run_id,
                "uid": uid,
                "source_type": source_type,
                "source_account_hash": request.source_account_hash,
                "importer_version": request.importer_version,
                "extractor_version": request.extractor_version,
                "status": MemoryImportRunStatus.received.value,
                "artifact_count": 0,
                "deduped_count": 0,
                "candidate_count": 0,
                "accepted_count": 0,
                "promoted_count": 0,
                "started_at": current_time.isoformat(),
                "updated_at": current_time.isoformat(),
                "completed_at": None,
                "last_error": None,
            },
        )
    except AlreadyExists:
        pass
    _store().set(
        run_path,
        {
            "artifact_count": Increment(created),
            "deduped_count": Increment(deduped),
            "updated_at": current_time.isoformat(),
        },
        merge=True,
    )

    return MemoryImportIngestResult(
        response=MemoryImportBatchResponse(
            run_id=run_id,
            artifacts_received=len(request.items),
            artifacts_created=created,
            artifacts_deduped=deduped,
            candidates_created=0,
            status=MemoryImportRunStatus.received,
        )
    )


__all__ = ["ingest_memory_import_batch"]

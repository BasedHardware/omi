#!/usr/bin/env python3
"""Rehydrate and prove the isolated JIT QA keyword projection.

The Typesense instance is deliberately disposable.  This command rebuilds it
from the named ``jit-qa`` Firestore database through the shipped canonical
rebuild helper, then exercises the real ``search_knowledge`` tool.  It emits a
content-free receipt: identifiers and query text are represented by digests,
and no provider document body is written to logs or artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from google.cloud import firestore

# Keep root and backend invocation equally usable.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models.knowledge_ledger_search import validate_ledger_kinds  # noqa: E402
from utils.memory.atom_keyword_index import (  # noqa: E402
    ensure_ledger_keyword_schema,
    ensure_memories_collection,
    keyword_search_ledger_memory_ids,
    rebuild_atom_keyword_index,
)
from utils.retrieval.tools.knowledge_ledger_tools import search_knowledge  # noqa: E402

PROJECT_ID = "based-hardware-dev"
REGION = "us-central1"
DATABASE_ID = "jit-qa"
QA_UID = "vi7SA9ckQCe4ccobWNxlbdcNdC23"
COLLECTION = "jit_qa_canonical_memory_atoms"
SCHEMA_VERSION = "omi.jit.qa.typesense.projection.v1"
TYPESENSE_SERVICE = "typesense-jit-qa"
TYPESENSE_CPU = "1"
TYPESENSE_MEMORY = "1Gi"
TYPESENSE_MIN_INSTANCES = 1
TYPESENSE_MAX_INSTANCES = 1
MAX_QUERY_CHARACTERS = 500
MAX_SEARCH_LIMIT = 20
MAX_PROJECTION_DOCUMENTS = 5_000
DOCUMENT_PAGE_SIZE = 250
_RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_IMAGE_RE = re.compile(r"^gcr\.io/based-hardware-dev/[a-z0-9-]+@sha256:[0-9a-f]{64}$")
_BASE_IMAGE_RE = re.compile(r"^docker\.io/typesense/typesense@sha256:[0-9a-f]{64}$")
_RESULT_ID_RE = re.compile(r"^- \[[^\]]+\] ([A-Za-z0-9][A-Za-z0-9._:-]{0,255})(?: slot=[^:]+)?: ")
_FORBIDDEN_CREDENTIAL_ENV = frozenset({"SERVICE_ACCOUNT_JSON", "FIREBASE_AUTH_CREDENTIALS_PATH"})
_DIGEST_FIELDS = (
    "id",
    "memory_id",
    "userId",
    "layer",
    "status",
    "schema_version",
    "ledger_index_version",
    "ledger_schema_version",
    "ledger_kind",
    "ledger_row_state",
    "ledger_has_slot",
    "ledger_subject_scope",
    "created_at",
)


class ProjectionError(RuntimeError):
    """A fail-closed projection precondition or proof failure."""


def require_sha(value: str, *, label: str) -> None:
    if not _SHA_RE.fullmatch(value):
        raise ProjectionError(f"{label} must be a full lowercase 40-character SHA")


def require_digest_image(value: str, *, label: str) -> None:
    if not _DIGEST_IMAGE_RE.fullmatch(value):
        raise ProjectionError(f"{label} must be a development registry image pinned by digest")


def require_base_image(value: str, *, label: str = "typesense_base_image") -> None:
    if not _BASE_IMAGE_RE.fullmatch(value):
        raise ProjectionError(f"{label} must be docker.io/typesense/typesense pinned by sha256 digest")


def validate_runtime_environment(environment: Mapping[str, str], *, collection: str = COLLECTION) -> None:
    """Reject every data plane and credential selector outside isolated QA."""

    for name in _FORBIDDEN_CREDENTIAL_ENV:
        if environment.get(name, "").strip():
            raise ProjectionError(f"{name} is forbidden for the isolated QA projection")
    if environment.get("FIRESTORE_EMULATOR_HOST", "").strip():
        raise ProjectionError("the QA projection requires named Cloud Firestore, not an emulator")
    expected = {
        "GOOGLE_CLOUD_PROJECT": PROJECT_ID,
        "OMI_FIRESTORE_DATA_PLANE_PROJECT": PROJECT_ID,
        "FIRESTORE_DATABASE_ID": DATABASE_ID,
        "OMI_ENV_STAGE": "dev",
        "OMI_JIT_QA_AUTH_ONLY": "true",
        "OMI_JIT_QA_UID_ALLOWLIST": QA_UID,
        "MEMORY_TYPESENSE_COLLECTION": collection,
        "TYPESENSE_PROTOCOL": "https",
        "TYPESENSE_HOST_PORT": "443",
    }
    for name, value in expected.items():
        if environment.get(name) != value:
            raise ProjectionError(f"{name} must be {value}")
    if not environment.get("TYPESENSE_API_KEY", "").strip():
        raise ProjectionError("TYPESENSE_API_KEY must be supplied through the dedicated QA secret")


def parse_typesense_url(value: str) -> tuple[str, str]:
    """Return ``(base_url, host)`` only for the named QA Cloud Run service."""

    parsed = urlsplit(value.strip())
    host = parsed.hostname or ""
    if (
        parsed.scheme != "https"
        or not host.endswith(".run.app")
        or not host.startswith(f"{TYPESENSE_SERVICE}-")
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or parsed.port not in {None, 443}
    ):
        raise ProjectionError("Typesense URL must be the HTTPS typesense-jit-qa Cloud Run URL")
    return f"https://{host}", host


def configure_runtime(*, typesense_url: str, collection: str = COLLECTION) -> str:
    base_url, host = parse_typesense_url(typesense_url)
    os.environ.update(
        {
            "TYPESENSE_HOST": host,
            "TYPESENSE_HOST_PORT": "443",
            "TYPESENSE_PROTOCOL": "https",
            "MEMORY_TYPESENSE_COLLECTION": collection,
        }
    )
    return base_url


def _json_digest(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _typesense_request(base_url: str, path: str, *, query: Mapping[str, object] | None = None) -> Any:
    api_key = os.environ.get("TYPESENSE_API_KEY", "").strip()
    if not api_key:
        raise ProjectionError("Typesense API key is unavailable")
    url = f"{base_url}{path}"
    if query:
        url = f"{url}?{urlencode({key: str(value) for key, value in query.items()})}"
    request = Request(url, headers={"X-TYPESENSE-API-KEY": api_key, "Accept": "application/json"})
    try:
        with urlopen(request, timeout=10) as response:  # noqa: S310 - URL is validated QA Cloud Run host
            if response.status >= 400:
                raise ProjectionError(f"Typesense request failed with HTTP {response.status}")
            return json.loads(response.read().decode("utf-8"))
    except ProjectionError:
        raise
    except Exception as exc:  # noqa: BLE001 - preserve a content-free failure boundary
        raise ProjectionError(f"Typesense request unavailable ({type(exc).__name__})") from exc


def _health_check(base_url: str) -> None:
    payload = _typesense_request(base_url, "/health")
    if not isinstance(payload, Mapping) or payload.get("ok") is not True:
        raise ProjectionError("Typesense health check did not report ok=true")


def _schema_summary(base_url: str, collection: str) -> tuple[str, list[str]]:
    payload = _typesense_request(base_url, f"/collections/{collection}")
    if not isinstance(payload, Mapping) or payload.get("name") != collection:
        raise ProjectionError("Typesense collection identity does not match the QA collection")
    fields = payload.get("fields")
    if not isinstance(fields, list):
        raise ProjectionError("Typesense collection schema is malformed")
    summary = []
    for field in fields:
        if not isinstance(field, Mapping) or not isinstance(field.get("name"), str):
            raise ProjectionError("Typesense collection schema field is malformed")
        summary.append({key: field[key] for key in ("name", "type", "facet", "optional", "sort") if key in field})
    summary.sort(key=lambda field: str(field["name"]))
    return _json_digest(summary), [str(field["name"]) for field in summary]


def _projection_documents(base_url: str, collection: str) -> list[dict[str, Any]]:
    fields = ",".join(_DIGEST_FIELDS)
    documents: list[dict[str, Any]] = []
    page = 1
    while True:
        payload = _typesense_request(
            base_url,
            f"/collections/{collection}/documents",
            query={"include_fields": fields, "per_page": DOCUMENT_PAGE_SIZE, "page": page},
        )
        if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
            raise ProjectionError("Typesense document inventory is malformed")
        documents.extend(payload)
        if len(documents) > MAX_PROJECTION_DOCUMENTS:
            raise ProjectionError("Typesense projection exceeds the bounded QA document limit")
        if len(payload) < DOCUMENT_PAGE_SIZE:
            break
        page += 1
    seen_ids: set[str] = set()
    for document in documents:
        document_id = document.get("id")
        if not isinstance(document_id, str) or not document_id or document_id in seen_ids:
            raise ProjectionError("Typesense projection contains a missing or duplicate document id")
        if document.get("userId") != QA_UID:
            raise ProjectionError("Typesense projection contains a document outside the fixed QA UID")
        seen_ids.add(document_id)
    return documents


def _projection_digest(documents: Sequence[Mapping[str, Any]]) -> str:
    rows = []
    for document in documents:
        row = {key: document[key] for key in _DIGEST_FIELDS if key in document}
        rows.append(row)
    rows.sort(key=lambda row: (str(row.get("memory_id", "")), str(row.get("id", ""))))
    return _json_digest(rows)


def _id_digest(ids: Sequence[str]) -> str:
    return _json_digest(sorted(set(ids)))


def _parse_search_result_ids(result: str) -> list[str]:
    return [match.group(1) for line in result.splitlines() if (match := _RESULT_ID_RE.match(line))]


def _validate_query(query: str, kinds: str, limit: int) -> frozenset[str]:
    normalized_query = " ".join(query.split())
    if not normalized_query or len(normalized_query) > MAX_QUERY_CHARACTERS:
        raise ProjectionError("query must be non-empty and at most 500 characters")
    if not 1 <= limit <= MAX_SEARCH_LIMIT:
        raise ProjectionError("limit must be between 1 and 20")
    try:
        parsed = validate_ledger_kinds(kinds.split(","))
    except ValueError as exc:
        raise ProjectionError("kinds must contain only valid knowledge ledger kinds") from exc
    return parsed


def build_projection_receipt(
    *,
    source_sha: str,
    run_id: str,
    typesense_url: str,
    typesense_image: str,
    typesense_base_image: str,
    query: str,
    kinds: Sequence[str],
    rebuild_report: Any,
    projection_count: int,
    projection_digest: str,
    schema_digest: str,
    schema_fields: Sequence[str],
    provider_ids: Sequence[str],
    result_ids: Sequence[str],
) -> dict[str, Any]:
    require_sha(source_sha, label="source_sha")
    require_digest_image(typesense_image, label="typesense_image")
    require_base_image(typesense_base_image)
    if not _RUN_ID_RE.fullmatch(run_id):
        raise ProjectionError("run_id must be lowercase and namespaced")
    if not getattr(rebuild_report, "verified", False):
        raise ProjectionError("rebuild report is not verified")
    indexed_count = int(getattr(rebuild_report, "indexed_count", 0))
    expected_count = int(getattr(rebuild_report, "expected_count", 0))
    if indexed_count != expected_count or projection_count != indexed_count:
        raise ProjectionError("receipt counts do not agree with the verified rebuild")
    if projection_count <= 0 or not provider_ids or not result_ids:
        raise ProjectionError("readiness requires a nonempty real ledger keyword result")
    if not set(provider_ids).intersection(result_ids):
        raise ProjectionError("search_knowledge did not consume a keyword candidate")
    base_url, _ = parse_typesense_url(typesense_url)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ready",
        "project": PROJECT_ID,
        "region": REGION,
        "firestore_database_id": DATABASE_ID,
        "uid": QA_UID,
        "typesense_service": TYPESENSE_SERVICE,
        "typesense_url": base_url,
        "typesense_image": typesense_image,
        "typesense_base_image": typesense_base_image,
        "collection": COLLECTION,
        "run_id": run_id,
        "rebuilt_indexed_count": indexed_count,
        "rebuilt_expected_count": expected_count,
        "projection_count": projection_count,
        "projection_digest": projection_digest,
        "schema_digest": schema_digest,
        "schema_fields": list(schema_fields),
        "query_sha256": hashlib.sha256(" ".join(query.split()).encode("utf-8")).hexdigest(),
        "kinds": sorted(set(kinds)),
        "provider_candidate_count": len(provider_ids),
        "provider_candidate_ids_digest": _id_digest(provider_ids),
        "search_result_count": len(result_ids),
        "search_result_ids_digest": _id_digest(result_ids),
        "search_path": "search_knowledge -> search_current_knowledge -> canonical MemoryService",
        "semantic_vector_proof": "unavailable; this receipt qualifies keyword retrieval only",
        "rehydratable_from": "based-hardware-dev/jit-qa/authoritative canonical memory items",
        "resource_bounds": {
            "min_instances": TYPESENSE_MIN_INSTANCES,
            "max_instances": TYPESENSE_MAX_INSTANCES,
            "cpu": TYPESENSE_CPU,
            "memory": TYPESENSE_MEMORY,
            "data_dir": "/tmp/typesense",
        },
        "cost_attribution": {
            "status": "not_measured",
            "basis": "Cloud Run billing is outside the projection proof",
        },
        "restart_rehydration": {
            "current_run": "full_rebuild_completed",
            "post_restart_replay": "not_run; rerun this workflow after any instance restart",
        },
        "captured_at": _utc_now(),
    }


def run_projection(
    *,
    source_sha: str,
    run_id: str,
    typesense_url: str,
    typesense_image: str,
    typesense_base_image: str,
    query: str,
    kinds: str,
    limit: int,
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    env = dict(os.environ if environment is None else environment)
    require_sha(source_sha, label="source_sha")
    require_digest_image(typesense_image, label="typesense_image")
    require_base_image(typesense_base_image)
    if not _RUN_ID_RE.fullmatch(run_id):
        raise ProjectionError("run_id must be lowercase and namespaced")
    parsed_kinds = _validate_query(query, kinds, limit)
    validate_runtime_environment(env)
    base_url = configure_runtime(typesense_url=typesense_url)
    _health_check(base_url)

    # Explicit named-database construction is part of the proof boundary.  A
    # default Firestore client would make the receipt invalid even if the
    # Typesense query happened to return a result.
    db_client = firestore.Client(project=PROJECT_ID, database=DATABASE_ID)
    ensure_memories_collection()
    ensure_ledger_keyword_schema()
    report = rebuild_atom_keyword_index(QA_UID, db_client=db_client)
    if not report.verified:
        raise ProjectionError("canonical Typesense rebuild was not verified")

    schema_digest, schema_fields = _schema_summary(base_url, COLLECTION)
    documents = _projection_documents(base_url, COLLECTION)
    if len(documents) != report.indexed_count:
        raise ProjectionError("Typesense document count does not match the verified rebuild report")
    projection_digest = _projection_digest(documents)

    # The direct candidate call gives producer-side evidence.  The tool call
    # below is the consumer-side evidence and performs authoritative hydration.
    provider_ids = keyword_search_ledger_memory_ids(
        QA_UID,
        " ".join(query.split()),
        kinds=parsed_kinds,
        limit=limit,
        db_client=db_client,
    )
    if not provider_ids:
        raise ProjectionError("real ledger keyword query returned no candidates")
    result = search_knowledge.invoke(
        {"query": query, "kinds": ",".join(sorted(parsed_kinds)), "limit": limit},
        config={"configurable": {"user_id": QA_UID}},
    )
    if (
        not isinstance(result, str)
        or result.startswith("Error:")
        or "No current knowledge ledger entries found." in result
    ):
        raise ProjectionError("search_knowledge returned no current QA result")
    result_ids = _parse_search_result_ids(result)
    return build_projection_receipt(
        source_sha=source_sha,
        run_id=run_id,
        typesense_url=typesense_url,
        typesense_image=typesense_image,
        typesense_base_image=typesense_base_image,
        query=query,
        kinds=sorted(parsed_kinds),
        rebuild_report=report,
        projection_count=len(documents),
        projection_digest=projection_digest,
        schema_digest=schema_digest,
        schema_fields=schema_fields,
        provider_ids=provider_ids,
        result_ids=result_ids,
    )


def write_receipt(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o600)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--typesense-url", required=True)
    parser.add_argument("--typesense-image", required=True)
    parser.add_argument("--typesense-base-image", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--kinds", default="fact,document,trigger")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        receipt = run_projection(
            source_sha=args.source_sha,
            run_id=args.run_id,
            typesense_url=args.typesense_url,
            typesense_image=args.typesense_image,
            typesense_base_image=args.typesense_base_image,
            query=args.query,
            kinds=args.kinds,
            limit=args.limit,
        )
    except (ProjectionError, OSError, ValueError) as exc:
        failure = {
            "schema_version": SCHEMA_VERSION,
            "status": "failed",
            "project": PROJECT_ID,
            "region": REGION,
            "firestore_database_id": DATABASE_ID,
            "uid": QA_UID,
            "run_id": args.run_id,
            "failure_type": type(exc).__name__,
            "captured_at": _utc_now(),
        }
        write_receipt(args.output, failure)
        print(f"JIT QA Typesense projection failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    write_receipt(args.output, receipt)
    print("JIT QA Typesense projection readiness receipt written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

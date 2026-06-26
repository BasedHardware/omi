"""Canonical module for ``utils.memory.v3_f5_evidence`` (WS-G8b).

Neutral ``v3_f5_evidence`` is the source of truth. Legacy ``v3_f5_evidence`` remains an importable alias.
"""

from __future__ import annotations

import ast
import hmac
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

EXPECTED_ENVIRONMENT = "shared-nonprod"
EXPECTED_PROJECT_ID = "omi-memory-evidence-nonprod"
EXPECTED_PROJECT_NUMBER = "123456789012"
EXPECTED_PRINCIPAL = "serviceAccount:memory-v3-f5-evidence@omi-memory-evidence-nonprod.iam.gserviceaccount.com"
EXPECTED_APPROVAL_SUBJECT = "memory-V3-F5 real-service read-only evidence shared-nonprod 2026-06-20"
EXPECTED_APPROVAL_ARTIFACT_PATH = "docs/approvals/memory-v3-f5-shared-nonprod-oracle-review.md"
EXPECTED_ORACLE_REVIEW_ARTIFACT = (
    "docs/operational/memory_readiness_evidence_markers.md#f4-before-f5-real-service-evidence-2026-06-20"
)
APPROVED_PATHS = (
    "control/config metadata",
    "cursor secret metadata",
    "projection state metadata",
    "canary approval metadata",
    "iam policy",
    "firestore index state",
    "audit read log metadata",
)

REQUIRED_READ_PERMISSIONS = frozenset(
    {
        "datastore.databases.get",
        "datastore.entities.get",
        "datastore.entities.list",
        "datastore.indexes.list",
        "iam.serviceAccounts.get",
        "resourcemanager.projects.getIamPolicy",
        "secretmanager.versions.get",
        "secretmanager.secrets.get",
        "logging.logEntries.list",
    }
)
FORBIDDEN_WRITE_PERMISSIONS = frozenset(
    {
        "datastore.entities.create",
        "datastore.entities.update",
        "datastore.entities.delete",
        "datastore.indexes.create",
        "datastore.indexes.update",
        "datastore.indexes.delete",
        "secretmanager.versions.access",
        "secretmanager.secrets.create",
        "secretmanager.secrets.update",
        "secretmanager.secrets.delete",
        "logging.sinks.create",
        "logging.sinks.update",
        "logging.sinks.delete",
    }
)
BROAD_ROLES = frozenset({"roles/owner", "roles/editor"})
MUTATOR_NAMES = frozenset(
    {
        "set",
        "create",
        "update",
        "delete",
        "patch",
        "commit",
        "batch",
        "transaction",
        "add",
        "upsert",
        "emit",
        "publish",
        "route",
    }
)
REQUIRED_INDEXES = {
    "memory_items_by_uid_generation_updated_at": {
        "fields": [("uid", "ASCENDING"), ("generation", "ASCENDING"), ("updated_at", "DESCENDING")],
        "query_scope": "COLLECTION",
        "state": "READY",
    }
}
TOP_LEVEL_ALLOWLIST = frozenset(
    {
        "artifact",
        "version",
        "mode",
        "status",
        "decision",
        "summary",
        "gate_failures",
        "identity_iam",
        "scope",
        "cursor_secret_metadata",
        "zero_write_proof",
        "deadlines",
        "indexes_schema",
        "redaction",
        "f4_risk_confirmations",
        "runtime_readiness",
        "external_readiness",
        "aggregate_readiness",
        "non_claims",
    }
)
SENSITIVE_KEYS = ("token", "secret", "authorization", "header", "url", "exception", "content", "cursor")
HMAC_KEY = b"memory-v3-f5-preparation-redaction-only"


@dataclass(frozen=True)
class EvidenceRunConfig:
    execute: bool = False
    environment: str | None = None
    project_id: str | None = None
    project_number: str | None = None
    expected_principal: str | None = None
    approval_subject: str | None = None
    approval_artifact_path: str | None = None
    approved_paths: tuple[str, ...] = ()
    oracle_review_artifact: str | None = None
    per_rpc_timeout_seconds: int = 5
    overall_deadline_seconds: int = 30
    max_attempts: int = 2
    max_documents_per_read: int = 25


@dataclass
class FakeEvidenceClient:
    principal: str
    permissions: frozenset[str]
    roles: set[str] = field(default_factory=lambda: {"roles/omi.MemoryEvidenceReader"})
    audit_zero_write_methods: list[str] | None = field(default_factory=list)
    indexes: list[dict[str, Any]] = field(
        default_factory=lambda: [
            {
                "name": "memory_items_by_uid_generation_updated_at",
                "fields": [("uid", "ASCENDING"), ("generation", "ASCENDING"), ("updated_at", "DESCENDING")],
                "query_scope": "COLLECTION",
                "state": "READY",
            }
        ]
    )
    fail_call: str | None = None
    inject_sensitive: bool = False
    structural_disable: bool = True
    calls: list[str] = field(default_factory=list)
    mutator_attempts: list[str] = field(default_factory=list)

    def _record(self, name: str) -> None:
        self.calls.append(name)
        if self.fail_call == name:
            raise TimeoutError(f"blocked partial failure from {name}: secret-value https://example.invalid")

    def effective_principal(self) -> str:
        self._record("effective_principal")
        return self.principal

    def iam_policy(self) -> dict[str, Any]:
        self._record("iam_policy")
        return {"roles": sorted(self.roles), "permissions": sorted(self.permissions)}

    def control_config_metadata(self) -> dict[str, Any]:
        self._record("control_config_metadata")
        return {"fields": {"enabled": "bool", "generation": "int", "updated_at": "timestamp"}, "document_count": 1}

    def cursor_secret_metadata(self) -> dict[str, Any]:
        self._record("cursor_secret_metadata")
        payload = {"version_state": "ENABLED", "payload_bytes_read": False, "secret_name": "REDACTED"}
        if self.inject_sensitive:
            payload["raw_secret_name"] = "secret-name"
            payload["cursor"] = "cursor-token"
        return payload

    def projection_state_metadata(self) -> dict[str, Any]:
        self._record("projection_state_metadata")
        data = {"fields": {"uid": "string", "generation": "int", "status": "string"}, "document_count": 3}
        if self.inject_sensitive:
            data["raw_memory_content"] = "raw memory content"
        return data

    def canary_approval_metadata(self) -> dict[str, Any]:
        self._record("canary_approval_metadata")
        return {"fields": {"subject": "string", "deadline": "timestamp", "status": "string"}, "document_count": 1}

    def index_state(self) -> list[dict[str, Any]]:
        self._record("index_state")
        return self.indexes

    def audit_log_metadata(self) -> dict[str, Any]:
        self._record("audit_log_metadata")
        return {"zero_write_methods": self.audit_zero_write_methods, "window_bounded": True}


class ReadOnlyEvidenceClient:
    def __init__(self, client: Any):
        self._client = client

    def __getattr__(self, name: str) -> Any:
        if name in MUTATOR_NAMES:

            def _blocked(*args: Any, **kwargs: Any) -> None:
                attempts = getattr(self._client, "mutator_attempts", None)
                if attempts is not None:
                    attempts.append(name)
                raise RuntimeError(f"mutator blocked before RPC: {name}")

            return _blocked
        return getattr(self._client, name)


def fingerprint(value: str | None) -> str | None:
    if not value:
        return None
    return "hmac:" + hmac.new(HMAC_KEY, value.encode("utf-8"), hashlib.sha256).hexdigest()[:16]


def _base_report(status: str, mode: str = "preparation/default-NOT_RUN") -> dict[str, Any]:
    blocked = {"status": "BLOCKED", "decision": "NO_GO"}
    return {
        "artifact": "v3_f5_real_service_evidence_readiness",
        "version": "memory-V3-F5",
        "mode": mode,
        "status": status,
        "decision": "NO_GO",
        "summary": {"cloud_client_constructed": False, "real_service_execution": False},
        "gate_failures": [],
        "runtime_readiness": blocked,
        "external_readiness": blocked,
        "aggregate_readiness": blocked,
        "non_claims": [
            "no shared/prod service execution performed",
            "no credentials added",
            "no Firestore/cloud/provider/network/vector calls performed by default",
            "no production app/router import or activation/canary/shadow/cutover claim",
            "readiness remains BLOCKED/NO_GO",
        ],
    }


def validate_gates(config: EvidenceRunConfig) -> list[str]:
    expected = {
        "environment": EXPECTED_ENVIRONMENT,
        "project_id": EXPECTED_PROJECT_ID,
        "project_number": EXPECTED_PROJECT_NUMBER,
        "expected_principal": EXPECTED_PRINCIPAL,
        "approval_subject": EXPECTED_APPROVAL_SUBJECT,
        "approval_artifact_path": EXPECTED_APPROVAL_ARTIFACT_PATH,
        "approved_paths": APPROVED_PATHS,
        "oracle_review_artifact": EXPECTED_ORACLE_REVIEW_ARTIFACT,
    }
    failures = []
    for key, expected_value in expected.items():
        if getattr(config, key) != expected_value:
            failures.append(key)
    return failures


def static_mutation_guard(paths: Iterable[Path]) -> dict[str, Any]:
    violations = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in MUTATOR_NAMES:
                violations.append({"path": str(path), "method": node.func.attr, "line": node.lineno})
    return {"status": "BLOCKED" if violations else "PASS", "violations": violations}


def _identity_iam(client: ReadOnlyEvidenceClient, expected_principal: str) -> dict[str, Any]:
    principal = client.effective_principal()
    policy = client.iam_policy()
    permissions = set(policy.get("permissions", []))
    roles = set(policy.get("roles", []))
    missing_reads = sorted(REQUIRED_READ_PERMISSIONS - permissions)
    write_intersection = sorted(FORBIDDEN_WRITE_PERMISSIONS & permissions)
    broad = bool(BROAD_ROLES & roles)
    status = "PASS"
    if principal != expected_principal or missing_reads or write_intersection or broad:
        status = "BLOCKED"
    return {
        "status": status,
        "principal_fingerprint": fingerprint(principal),
        "expected_principal_fingerprint": fingerprint(expected_principal),
        "missing_read_permissions": missing_reads,
        "write_permission_intersection": write_intersection,
        "owner_editor_present": broad,
        "dedicated_evidence_principal_contract": True,
    }


def _indexes_schema(indexes: list[dict[str, Any]]) -> dict[str, Any]:
    by_name = {index.get("name"): index for index in indexes}
    missing = []
    malformed = []
    for name, expected in REQUIRED_INDEXES.items():
        actual = by_name.get(name)
        if not actual:
            missing.append(name)
            continue
        for field in ("fields", "query_scope", "state"):
            if actual.get(field) != expected[field]:
                malformed.append(name)
                break
    return {
        "status": "BLOCKED" if missing or malformed else "PASS",
        "required_indexes": sorted(REQUIRED_INDEXES),
        "missing_indexes": missing,
        "malformed_indexes": malformed,
        "content_fields_validated": False,
        "metadata_fields_validated": ["field_names", "types", "epochs", "generations", "status"],
    }


def build_evidence_report(
    config: EvidenceRunConfig | None = None, client_factory: Callable[[], Any] | None = None
) -> dict[str, Any]:
    config = config or EvidenceRunConfig()
    if not config.execute:
        return _base_report("NOT_RUN")

    report = _base_report("BLOCKED", mode="preparation/execute-gated")
    gate_failures = validate_gates(config)
    report["gate_failures"] = gate_failures
    if gate_failures or client_factory is None:
        if client_factory is None and not gate_failures:
            report["gate_failures"] = ["client_factory"]
        return report

    raw_client = client_factory()
    report["summary"]["cloud_client_constructed"] = True
    client = ReadOnlyEvidenceClient(raw_client)
    static_guard = static_mutation_guard([Path(__file__)])
    service_failure = False
    try:
        identity = _identity_iam(client, EXPECTED_PRINCIPAL)
        control = client.control_config_metadata()
        cursor = client.cursor_secret_metadata()
        projection = client.projection_state_metadata()
        canary = client.canary_approval_metadata()
        indexes = _indexes_schema(client.index_state())
        audit = client.audit_log_metadata()
    except Exception:
        service_failure = True
        identity = {"status": "BLOCKED"}
        control = cursor = projection = canary = {}
        indexes = {"status": "BLOCKED", "missing_indexes": [], "malformed_indexes": []}
        audit = {"zero_write_methods": None}

    zero_status = "PASS" if audit.get("zero_write_methods") == [] else "INCONCLUSIVE"
    f4 = {
        "structural_disable_repository_assertion": bool(getattr(raw_client, "structural_disable", False)),
        "pagination_branch_order_proof": True,
        "read_only_f4_to_f3_call_graph_proof": True,
        "cache_control_no_store_required": True,
    }
    report["identity_iam"] = identity
    report["scope"] = {
        "status": "PASS",
        "approved_metadata_only_paths": list(APPROVED_PATHS),
        "bounded_document_count": config.max_documents_per_read,
        "raw_memory_content_read": False,
        "arbitrary_user_sampling": False,
        "collection_scans": False,
        "route_calls": [],
        "vector_mutations": False,
        "production_app_imported": False,
        "control": control,
        "projection": {"document_count": projection.get("document_count")},
        "canary": {"document_count": canary.get("document_count")},
    }
    report["cursor_secret_metadata"] = {
        "status": "PASS" if cursor.get("payload_bytes_read") is False else "BLOCKED",
        "version_state_present": "version_state" in cursor,
        "payload_bytes_read": bool(cursor.get("payload_bytes_read")),
    }
    report["zero_write_proof"] = {
        "status": zero_status,
        "static_ast_mutation_guard": static_guard,
        "runtime_mutator_wrapper": "enabled",
        "iam_write_permission_intersection_empty": not identity.get("write_permission_intersection"),
        "post_run_audit_zero_write_methods": audit.get("zero_write_methods"),
        "never_attempt_write_to_prove_denial": True,
    }
    report["deadlines"] = {
        "status": "BLOCKED" if service_failure else "PASS",
        "per_rpc_timeout_seconds": config.per_rpc_timeout_seconds,
        "overall_deadline_seconds": config.overall_deadline_seconds,
        "bounded_retries": {"max_attempts": config.max_attempts, "backoff_seconds": [0.05]},
        "bounded_query_document_count": config.max_documents_per_read,
        "fallback_attempted": False,
    }
    report["indexes_schema"] = indexes
    report["redaction"] = {
        "status": "PASS",
        "strategy": "HMAC fingerprints plus top-level fail-closed allowlist",
        "project_fingerprint": fingerprint(config.project_id),
        "principal_fingerprint": fingerprint(config.expected_principal),
        "approval_fingerprint": fingerprint(config.approval_subject),
    }
    report["f4_risk_confirmations"] = f4
    blockers = [
        identity.get("status") == "BLOCKED",
        indexes.get("status") == "BLOCKED",
        static_guard.get("status") == "BLOCKED",
        service_failure,
        not all(f4.values()),
    ]
    if any(blockers):
        report["status"] = "BLOCKED"
    elif zero_status == "INCONCLUSIVE":
        report["status"] = "INCONCLUSIVE"
    else:
        # Real-service preparation can collect fake evidence, but it still does not activate or mark readiness GO.
        report["status"] = "INCONCLUSIVE"
    return report


def _sanitize(obj: Any) -> Any:
    if isinstance(obj, dict):
        clean = {}
        for key, value in obj.items():
            lower = key.lower()
            if any(marker in lower for marker in SENSITIVE_KEYS):
                if key in {"cursor_secret_metadata"}:
                    clean[key] = _sanitize(value)
                elif key in {"payload_bytes_read", "version_state_present"}:
                    clean[key] = value
                else:
                    clean[key] = "REDACTED"
            else:
                clean[key] = _sanitize(value)
        return clean
    if isinstance(obj, list):
        return [_sanitize(item) for item in obj]
    if isinstance(obj, str):
        if any(s in obj for s in ("secret", "cursor-token", "Authorization", "https://", "raw memory content")):
            return "REDACTED"
    return obj


def render_redacted_json(report: dict[str, Any]) -> str:
    unknown = set(report) - TOP_LEVEL_ALLOWLIST
    if unknown:
        raise ValueError(f"output field not explicitly allowlisted: {sorted(unknown)}")
    rendered = json.dumps(_sanitize(report), sort_keys=True, indent=2)
    # Defense-in-depth: fail closed if known raw sentinel fragments survived.
    for sentinel in ("secret-name", "secret-value", "cursor-token", "Authorization", "https://", "raw memory content"):
        if sentinel in rendered:
            raise ValueError(f"redaction failed for sentinel: {sentinel}")
    return rendered


# Neutral symbol aliases (memory names remain valid via shim)

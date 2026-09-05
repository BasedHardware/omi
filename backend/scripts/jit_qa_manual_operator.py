#!/usr/bin/env python3
"""Content-free helpers for the isolated JIT QA manual workflow.

The workflow is the only caller that performs Cloud Run execution.  This
module keeps its safety checks and execution parsing testable without cloud
credentials.  It accepts only the named development job and emits aggregate
counters; log messages and Firestore documents are never copied into a
receipt.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

PROJECT = "based-hardware-dev"
REGION = "us-central1"
DATABASE = "jit-qa"
UID = "vi7SA9ckQCe4ccobWNxlbdcNdC23"
JOB = "knowledge-ledger-drain-qa-job"
RUNTIME_SERVICE_ACCOUNT = "jit-qa-runtime@based-hardware-dev.iam.gserviceaccount.com"
SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
IMAGE_RE = re.compile(r"^gcr\.io/based-hardware-dev/knowledge-ledger-drain-qa-job@sha256:[0-9a-f]{64}$")
EXECUTION_RE = re.compile(r"^knowledge-ledger-drain-qa-job-[a-z0-9-]+$")
SUMMARY_RE = re.compile(
    r"knowledge_ledger_drain:\s+"
    r"scanned=(?P<scanned>\d+)\s+"
    r"inventoried=(?P<inventoried>\d+)\s+"
    r"attempted=(?P<attempted>\d+)\s+"
    r"allowlist_blocked=(?P<allowlist_blocked>\d+)\s+"
    r"blocked=(?P<blocked>\d+)\s+"
    r"revoked=(?P<revoked>\d+)\s+"
    r"remaining=(?P<remaining>\d+)\s+"
    r"cutover=(?P<cutover>\d+)\s+"
    r"migrated_rows=(?P<migrated>\d+)\s+"
    r"errors=(?P<errors>\d+)"
)


class OperatorError(ValueError):
    """Raised when a cloud result crosses the fixed QA boundary."""


def require_source_sha(value: str) -> str:
    if not SOURCE_SHA_RE.fullmatch(value):
        raise OperatorError("source SHA must be a full lowercase 40-character commit")
    return value


def _containers(resource: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Read both Cloud Run v1 and v2 job response shapes."""

    paths = (
        ("spec", "template", "template", "spec", "containers"),
        ("spec", "template", "template", "containers"),
        ("spec", "template", "spec", "template", "spec", "containers"),
        ("spec", "template", "spec", "template", "containers"),
    )
    for path in paths:
        value: object = resource
        for key in path:
            value = value.get(key) if isinstance(value, Mapping) else None
        if value is not None:
            if isinstance(value, list) and len(value) == 1 and isinstance(value[0], Mapping):
                return [value[0]]
            raise OperatorError("QA drain job must have exactly one application container")
    raise OperatorError("QA drain job has no supported container shape")


def _env(container: Mapping[str, Any]) -> tuple[dict[str, str], set[str]]:
    values: dict[str, str] = {}
    secret_names: set[str] = set()
    entries = container.get("env")
    if not isinstance(entries, list):
        raise OperatorError("QA drain job environment is missing")
    for entry in entries:
        if not isinstance(entry, Mapping) or not isinstance(entry.get("name"), str):
            raise OperatorError("QA drain job environment entry is malformed")
        name = str(entry["name"])
        if name in values or name in secret_names:
            raise OperatorError(f"QA drain job environment repeats {name}")
        if "value" in entry:
            if not isinstance(entry["value"], str):
                raise OperatorError(f"QA drain job value for {name} is malformed")
            values[name] = entry["value"]
            continue
        source = entry.get("valueSource", entry.get("valueFrom"))
        if isinstance(source, Mapping):
            reference = source.get("secretKeyRef")
            if isinstance(reference, Mapping):
                secret = reference.get("secret", reference.get("name"))
                version = reference.get("version", reference.get("key"))
                if secret == name and version == "latest":
                    secret_names.add(name)
                    continue
        raise OperatorError(f"QA drain job environment binding for {name} is malformed")
    return values, secret_names


def _service_account(resource: Mapping[str, Any]) -> str | None:
    for path in (
        ("spec", "template", "spec", "template", "spec", "serviceAccount"),
        ("spec", "template", "spec", "template", "spec", "serviceAccountName"),
        ("spec", "template", "template", "serviceAccount"),
        ("spec", "template", "template", "serviceAccountName"),
        ("spec", "template", "spec", "serviceAccount"),
        ("spec", "template", "spec", "serviceAccountName"),
    ):
        value: object = resource
        for key in path:
            value = value.get(key) if isinstance(value, Mapping) else None
        if value is not None:
            return str(value)
    return None


def validate_job_resource(resource: Mapping[str, Any], *, source_sha: str) -> dict[str, str]:
    """Validate the live job's identity, source label, digest, and QA fence."""

    require_source_sha(source_sha)
    metadata = resource.get("metadata")
    if not isinstance(metadata, Mapping) or metadata.get("name") != JOB:
        raise OperatorError("Cloud Run resource is not the isolated QA drain job")
    labels = metadata.get("labels")
    if not isinstance(labels, Mapping) or labels.get("jit-qa") != "true" or labels.get("source-sha") != source_sha:
        raise OperatorError("QA drain job source admission label is missing or stale")
    container = _containers(resource)[0]
    image = container.get("image")
    if not isinstance(image, str) or not IMAGE_RE.fullmatch(image):
        raise OperatorError("QA drain job must serve the immutable development image digest")
    if _service_account(resource) != RUNTIME_SERVICE_ACCOUNT:
        raise OperatorError("QA drain job uses an unexpected runtime service account")
    if container.get("envFrom"):
        raise OperatorError("QA drain job may not inherit an environment bundle")
    values, secrets = _env(container)
    expected = {
        "OMI_ENV_STAGE": "dev",
        "GOOGLE_CLOUD_PROJECT": PROJECT,
        "OMI_FIRESTORE_DATA_PLANE_PROJECT": PROJECT,
        "FIRESTORE_DATABASE_ID": DATABASE,
        "FIREBASE_AUTH_PROJECT_ID": "based-hardware",
        "MEMORY_ENABLED": "on",
        "KNOWLEDGE_LEDGER_DRAIN_ENABLED": "false",
        "KNOWLEDGE_LEDGER_DRAIN_UID_ALLOWLIST": UID,
        "OMI_JIT_QA_AUTH_ONLY": "true",
        "OMI_JIT_QA_UID_ALLOWLIST": UID,
    }
    for name, expected_value in expected.items():
        if values.get(name) != expected_value:
            raise OperatorError(f"QA drain job environment {name} is not the fixed QA value")
    if secrets != {"ENCRYPTION_SECRET", "POSTHOG_PROJECT_API_KEY"}:
        raise OperatorError("QA drain job has an unexpected secret binding")
    forbidden = {"SERVICE_ACCOUNT_JSON", "GOOGLE_APPLICATION_CREDENTIALS", "FIREBASE_AUTH_CREDENTIALS_PATH"}
    if forbidden.intersection(values) or forbidden.intersection(secrets):
        raise OperatorError("QA drain job contains a customer credential selector")
    return {"job": JOB, "image": image, "source_sha": source_sha, "database": DATABASE, "uid": UID}


def execution_name(payload: Mapping[str, Any]) -> str:
    metadata = payload.get("metadata")
    name = metadata.get("name") if isinstance(metadata, Mapping) else None
    if not isinstance(name, str) or not EXECUTION_RE.fullmatch(name):
        raise OperatorError("Cloud Run returned an unexpected QA drain execution name")
    return name


def execution_state(payload: Mapping[str, Any]) -> str:
    status = payload.get("status")
    conditions = status.get("conditions") if isinstance(status, Mapping) else None
    if not isinstance(conditions, list):
        return "running"
    completed = next(
        (item for item in conditions if isinstance(item, Mapping) and item.get("type") == "Completed"), None
    )
    if not isinstance(completed, Mapping) or completed.get("status") not in {"True", "False"}:
        return "running"
    return "succeeded" if completed.get("status") == "True" else "failed"


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        result: list[str] = []
        for child in value.values():
            result.extend(_strings(child))
        return result
    if isinstance(value, list):
        result = []
        for child in value:
            result.extend(_strings(child))
        return result
    return []


def summary_from_logs(payload: object) -> dict[str, Any]:
    """Extract the aggregate line emitted by the real drain job.

    The query is already scoped to one execution by the workflow.  We still
    parse every returned string and require exactly one summary line, so a
    missing or ambiguous log can never be mistaken for a successful page.
    """

    matches = []
    for candidate in _strings(payload):
        matches.extend(SUMMARY_RE.finditer(candidate))
    if len(matches) != 1:
        raise OperatorError(f"expected one content-free drain summary, found {len(matches)}")
    match = matches[0]
    values = {key: int(value) for key, value in match.groupdict().items()}
    return {
        "inventoried_users": values["inventoried"],
        "scanned_documents": values["scanned"],
        "attempted_users": values["attempted"],
        "allowlist_blocked_users": values["allowlist_blocked"],
        "rollout_blocked_users": values["blocked"],
        "authorization_revoked_users": values["revoked"],
        "remaining_users": values["remaining"],
        "cutover_users": values["cutover"],
        "migrated_rows": values["migrated"],
        "errors": ["<redacted>"] * values["errors"],
    }


def _firestore_value(document: Mapping[str, Any], field: str) -> Any:
    fields = document.get("fields")
    entry = fields.get(field) if isinstance(fields, Mapping) else None
    if not isinstance(entry, Mapping):
        return None
    if "stringValue" in entry:
        return entry["stringValue"]
    if "integerValue" in entry:
        try:
            return int(str(entry["integerValue"]))
        except (TypeError, ValueError):
            return None
    if "booleanValue" in entry:
        return entry["booleanValue"]
    return None


def validate_durable_state(
    control: Mapping[str, Any],
    completion: Mapping[str, Any],
    projection: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the named account's content-free post-drain fences."""

    control_mode = _firestore_value(control, "writer_mode")
    if control_mode != "ledger":
        raise OperatorError("durable proof has no stable ledger writer")
    if _firestore_value(completion, "status") != "complete" or _firestore_value(completion, "blocking_row_count") != 0:
        raise OperatorError("durable ledger completion is incomplete")
    if _firestore_value(control, "head_commit_id") != _firestore_value(completion, "source_head_commit_id"):
        raise OperatorError("durable ledger completion head fence mismatches apply-control")
    if _firestore_value(control, "writer_epoch") != _firestore_value(completion, "writer_epoch"):
        raise OperatorError("durable ledger completion epoch fence mismatches apply-control")
    if _firestore_value(projection, "status") != "complete" or _firestore_value(projection, "legacy_row_count") != 0:
        raise OperatorError("durable prompt projection is incomplete")
    scanned = _firestore_value(projection, "scanned_row_count")
    if _firestore_value(projection, "blocking_row_count") != 0 or not isinstance(scanned, int) or scanned <= 0:
        raise OperatorError("durable prompt projection has no completed nonempty scan")
    return {
        "writer_mode": control_mode,
        "completion_status": "complete",
        "projection_status": "complete",
        "scanned_row_count": scanned,
    }


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OperatorError(f"could not read JSON from {path}") from exc


def _load_mapping(path: Path) -> Mapping[str, Any]:
    payload = _load(path)
    if not isinstance(payload, Mapping):
        raise OperatorError(f"{path} must contain a JSON object")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    job = sub.add_parser("validate-job")
    job.add_argument("--source-sha", required=True)
    job.add_argument("--resource-json", type=Path, required=True)
    name = sub.add_parser("execution-name")
    name.add_argument("--execution-json", type=Path, required=True)
    state = sub.add_parser("execution-state")
    state.add_argument("--execution-json", type=Path, required=True)
    logs = sub.add_parser("summary")
    logs.add_argument("--logs-json", type=Path, required=True)
    durable = sub.add_parser("durable")
    durable.add_argument("--control-json", type=Path, required=True)
    durable.add_argument("--completion-json", type=Path, required=True)
    durable.add_argument("--projection-json", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "validate-job":
            print(
                json.dumps(
                    validate_job_resource(_load_mapping(args.resource_json), source_sha=args.source_sha),
                    sort_keys=True,
                )
            )
        elif args.command == "execution-name":
            print(execution_name(_load_mapping(args.execution_json)))
        elif args.command == "execution-state":
            print(execution_state(_load_mapping(args.execution_json)))
        elif args.command == "summary":
            print(json.dumps(summary_from_logs(_load(args.logs_json)), sort_keys=True))
        else:
            print(
                json.dumps(
                    validate_durable_state(
                        _load_mapping(args.control_json),
                        _load_mapping(args.completion_json),
                        _load_mapping(args.projection_json),
                    ),
                    sort_keys=True,
                )
            )
        return 0
    except (OSError, json.JSONDecodeError, OperatorError) as exc:
        print(f"JIT QA operator refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

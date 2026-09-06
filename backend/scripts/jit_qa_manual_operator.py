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

# The deployed-resource contract is owned by the QA deployment workflow.  Keep
# this consumer on that same contract instead of maintaining a second copy of
# its environment and Secret Manager bindings.
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import jit_qa_cloud_run_contract as qa_contract  # noqa: E402

PROJECT = qa_contract.PROJECT_ID
REGION = qa_contract.REGION
DATABASE = qa_contract.FIRESTORE_DATABASE_ID
UID = qa_contract.QA_UID
JOB = qa_contract.LEDGER_DRAIN_JOB
RUNTIME_SERVICE_ACCOUNT = qa_contract.RUNTIME_SERVICE_ACCOUNT
SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
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
SUMMARY_EXPECTATIONS: dict[str, dict[str, int]] = {
    "first": {
        "inventoried_users": 1,
        "scanned_documents": 1,
        "attempted_users": 1,
        "allowlist_blocked_users": 0,
        "rollout_blocked_users": 0,
        "authorization_revoked_users": 0,
        "remaining_users": 1,
        "cutover_users": 0,
        "migrated_rows": 100,
    },
    "second": {
        "inventoried_users": 1,
        "scanned_documents": 1,
        "attempted_users": 1,
        "allowlist_blocked_users": 0,
        "rollout_blocked_users": 0,
        "authorization_revoked_users": 0,
        "remaining_users": 0,
        "cutover_users": 1,
        "migrated_rows": 1,
    },
    "retry": {
        "inventoried_users": 0,
        "scanned_documents": 1,
        "attempted_users": 0,
        "allowlist_blocked_users": 0,
        "rollout_blocked_users": 0,
        "authorization_revoked_users": 0,
        "remaining_users": 0,
        "cutover_users": 0,
        "migrated_rows": 0,
    },
    "rollforward": {
        "inventoried_users": 1,
        "scanned_documents": 1,
        "attempted_users": 1,
        "allowlist_blocked_users": 0,
        "rollout_blocked_users": 0,
        "authorization_revoked_users": 0,
        "remaining_users": 0,
        "cutover_users": 1,
        "migrated_rows": 0,
    },
}


class OperatorError(ValueError):
    """Raised when a cloud result crosses the fixed QA boundary."""


def require_source_sha(value: str) -> str:
    if not SOURCE_SHA_RE.fullmatch(value):
        raise OperatorError("source SHA must be a full lowercase 40-character commit")
    return value


def validate_job_resource(resource: Mapping[str, Any], *, source_sha: str, expected_image: str) -> dict[str, str]:
    """Validate the live job with the deployment workflow's shared contract."""

    require_source_sha(source_sha)
    metadata = resource.get("metadata")
    if not isinstance(metadata, Mapping) or metadata.get("name") != JOB:
        raise OperatorError("Cloud Run resource is not the isolated QA drain job")
    labels = metadata.get("labels")
    if not isinstance(labels, Mapping) or labels.get("jit-qa") != "true" or labels.get("source-sha") != source_sha:
        raise OperatorError("QA drain job source admission label is missing or stale")
    try:
        container = qa_contract._containers(resource, kind="job")[0]
    except qa_contract.JITQAContractError as exc:
        raise OperatorError(str(exc)) from exc
    image = container.get("image")
    if not isinstance(image, str) or not re.fullmatch(
        r"gcr\.io/based-hardware-dev/knowledge-ledger-drain-qa-job@sha256:[0-9a-f]{64}", image
    ):
        raise OperatorError("QA drain job must serve the immutable development image digest")
    if not re.fullmatch(
        r"gcr\.io/based-hardware-dev/knowledge-ledger-drain-qa-job@sha256:[0-9a-f]{64}", expected_image
    ):
        raise OperatorError("resolved QA drain image is not an immutable development image digest")
    if image != expected_image:
        raise OperatorError("live QA drain image does not match the digest resolved from the admitted source tag")
    expected_environment, expected_secret_bindings = qa_contract.resource_environment("drain")
    try:
        qa_contract.validate_cloud_run_resource(
            resource,
            kind="job",
            expected_image=image,
            expected_environment=expected_environment,
            expected_secret_bindings=expected_secret_bindings,
            expected_name=JOB,
            expected_service_account=RUNTIME_SERVICE_ACCOUNT,
        )
    except qa_contract.JITQAContractError as exc:
        raise OperatorError(str(exc)) from exc
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


def validate_summary(summary: Mapping[str, Any], *, phase: str) -> dict[str, Any]:
    """Require the exact content-free counters for one bounded drain phase."""

    expected = SUMMARY_EXPECTATIONS.get(phase)
    if expected is None:
        raise OperatorError(f"unknown drain phase {phase!r}")
    if not isinstance(summary.get("errors"), list) or summary.get("errors"):
        raise OperatorError(f"{phase} drain reported errors")
    for key, value in expected.items():
        if summary.get(key) != value:
            raise OperatorError(f"{phase} drain {key}={summary.get(key)!r}; expected {value!r}")
    return dict(summary)


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


def _required_string(document: Mapping[str, Any], field: str) -> str:
    value = _firestore_value(document, field)
    if not isinstance(value, str) or not value.strip():
        raise OperatorError(f"durable proof is missing non-empty {field}")
    return value


def _required_int(document: Mapping[str, Any], field: str, *, minimum: int) -> int:
    value = _firestore_value(document, field)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise OperatorError(f"durable proof has invalid {field}")
    return value


def validate_durable_state(
    control: Mapping[str, Any],
    completion: Mapping[str, Any],
    projection: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the named account's content-free post-drain fences."""

    if _required_string(control, "uid") != UID:
        raise OperatorError("durable proof belongs to an unexpected QA identity")
    control_mode = _required_string(control, "writer_mode")
    if control_mode != "ledger":
        raise OperatorError("durable proof has no stable ledger writer")
    control_head = _required_string(control, "head_commit_id")
    control_account_generation = _required_int(control, "account_generation", minimum=0)
    control_source_generation = _required_int(control, "source_generation", minimum=0)
    control_writer_epoch = _required_int(control, "writer_epoch", minimum=1)
    if _required_string(completion, "schema_version") != "knowledge_ledger.v1":
        raise OperatorError("durable ledger completion has an unexpected schema")
    if (
        _required_string(completion, "status") != "complete"
        or _required_int(completion, "blocking_row_count", minimum=0) != 0
    ):
        raise OperatorError("durable ledger completion is incomplete")
    completion_head = _required_string(completion, "source_head_commit_id")
    completion_writer_epoch = _required_int(completion, "writer_epoch", minimum=1)
    if control_head != completion_head:
        raise OperatorError("durable ledger completion head fence mismatches apply-control")
    if control_writer_epoch != completion_writer_epoch:
        raise OperatorError("durable ledger completion epoch fence mismatches apply-control")
    if _required_string(projection, "schema_version") != "knowledge_ledger_prompt_projection.v1":
        raise OperatorError("durable prompt projection has an unexpected schema")
    if _required_string(projection, "status") != "complete" or _required_string(projection, "uid") != UID:
        raise OperatorError("durable prompt projection is incomplete or foreign")
    projection_head = _required_string(projection, "source_head_commit_id")
    projection_account_generation = _required_int(projection, "account_generation", minimum=0)
    projection_source_generation = _required_int(projection, "source_generation", minimum=0)
    projection_writer_epoch = _required_int(projection, "writer_epoch", minimum=1)
    if projection_head != control_head or projection_head != completion_head:
        raise OperatorError("durable prompt projection head fence mismatches canonical state")
    if projection_account_generation != control_account_generation:
        raise OperatorError("durable prompt projection account generation mismatches apply-control")
    if projection_source_generation != control_source_generation:
        raise OperatorError("durable prompt projection source generation mismatches apply-control")
    if projection_writer_epoch != control_writer_epoch or projection_writer_epoch != completion_writer_epoch:
        raise OperatorError("durable prompt projection epoch fence mismatches canonical state")
    if _required_int(projection, "legacy_row_count", minimum=0) != 0:
        raise OperatorError("durable prompt projection is incomplete")
    if _required_int(projection, "blocking_row_count", minimum=0) != 0:
        raise OperatorError("durable prompt projection is incomplete")
    scanned = _required_int(projection, "scanned_row_count", minimum=1)
    if scanned <= 0:
        raise OperatorError("durable prompt projection has no completed nonempty scan")
    return {
        "writer_mode": control_mode,
        "completion_status": "complete",
        "projection_status": "complete",
        "head_commit_id": control_head,
        "account_generation": control_account_generation,
        "source_generation": control_source_generation,
        "writer_epoch": control_writer_epoch,
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
    job.add_argument("--expected-image", required=True)
    job.add_argument("--resource-json", type=Path, required=True)
    name = sub.add_parser("execution-name")
    name.add_argument("--execution-json", type=Path, required=True)
    state = sub.add_parser("execution-state")
    state.add_argument("--execution-json", type=Path, required=True)
    logs = sub.add_parser("summary")
    logs.add_argument("--logs-json", type=Path, required=True)
    validated = sub.add_parser("validate-summary")
    validated.add_argument("--summary-json", type=Path, required=True)
    validated.add_argument("--phase", choices=tuple(SUMMARY_EXPECTATIONS), required=True)
    durable = sub.add_parser("durable")
    durable.add_argument("--control-json", type=Path, required=True)
    durable.add_argument("--completion-json", type=Path, required=True)
    durable.add_argument("--projection-json", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "validate-job":
            print(
                json.dumps(
                    validate_job_resource(
                        _load_mapping(args.resource_json),
                        source_sha=args.source_sha,
                        expected_image=args.expected_image,
                    ),
                    sort_keys=True,
                )
            )
        elif args.command == "execution-name":
            print(execution_name(_load_mapping(args.execution_json)))
        elif args.command == "execution-state":
            print(execution_state(_load_mapping(args.execution_json)))
        elif args.command == "summary":
            print(json.dumps(summary_from_logs(_load(args.logs_json)), sort_keys=True))
        elif args.command == "validate-summary":
            print(json.dumps(validate_summary(_load_mapping(args.summary_json), phase=args.phase), sort_keys=True))
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

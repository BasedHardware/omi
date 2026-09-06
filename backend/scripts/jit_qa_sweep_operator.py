#!/usr/bin/env python3
"""Read-only consumer for one server-admitted JIT QA daily-sweep run.

The Cloud Run sweep job is the producer. It tags each durable candidate receipt
with the server-supplied run id and creates one content-free run receipt. This
command reads both sides from the fixed QA database and never treats a
workflow execution counter or log line as product output.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from utils.memory.daily_memory_sweep import (  # noqa: E402
    QA_SWEEP_DATABASE,
    QA_SWEEP_OUTPUT_SCHEMA_VERSION,
    QA_SWEEP_PROJECT,
    QA_SWEEP_RECEIPT_SCHEMA_VERSION,
    QA_SWEEP_RUN_COLLECTION,
    QA_SWEEP_OUTPUT_SUBCOLLECTION,
    QA_SWEEP_UID,
    validate_qa_sweep_environment,
    validate_qa_sweep_run_id,
)
from scripts import jit_qa_cloud_run_contract as qa_contract  # noqa: E402

OUTPUT_COLLECTION = f"users/{QA_SWEEP_UID}/daily_memory_sweep_receipts"
QA_SWEEP_JOB = "daily-memory-sweep-qa-job"
OUTPUT_FIELDS = (
    "uid",
    "qa_run_id",
    "receipt_state",
    "outcome",
    "memory_id",
    "candidate_digest",
    "source_key",
    "source_id",
    "source_type",
    "source_version",
    "source_refs",
)
LIVE_SOURCE_TYPES = frozenset({"daily_summary", "onboarding", "agent_conclusion"})


class JITQASweepOperatorError(RuntimeError):
    """A QA sweep consumer precondition or proof assertion failed."""


def validate_job_resource(resource: Mapping[str, Any], *, source_sha: str, expected_image: str) -> dict[str, str]:
    """Tie the live sweep job's source label and digest to the reviewed SHA."""

    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise JITQASweepOperatorError("QA sweep source SHA must be a full lowercase 40-character commit")
    metadata = resource.get("metadata")
    if not isinstance(metadata, Mapping) or metadata.get("name") != QA_SWEEP_JOB:
        raise JITQASweepOperatorError("Cloud Run resource is not the isolated QA sweep job")
    labels = metadata.get("labels")
    if not isinstance(labels, Mapping) or labels.get("jit-qa") != "true" or labels.get("source-sha") != source_sha:
        raise JITQASweepOperatorError("QA sweep job source admission label is missing or stale")
    try:
        container = qa_contract._containers(resource, kind="job")[0]
    except qa_contract.JITQAContractError as exc:
        raise JITQASweepOperatorError(str(exc)) from exc
    if container.get("image") != expected_image:
        raise JITQASweepOperatorError("live QA sweep image does not match the digest resolved from the source tag")
    try:
        qa_contract.require_digest_image(expected_image, label="resolved QA sweep image")
    except qa_contract.JITQAContractError as exc:
        raise JITQASweepOperatorError(str(exc)) from exc
    return {"job": QA_SWEEP_JOB, "image": expected_image, "source_sha": source_sha}


def build_firestore_client() -> Any:
    run_id = validate_qa_sweep_environment()
    if not run_id:
        raise JITQASweepOperatorError("QA sweep run id is required")
    return firestore.Client(project=QA_SWEEP_PROJECT, database=QA_SWEEP_DATABASE)


def _as_dict(snapshot: Any) -> dict[str, Any]:
    if not getattr(snapshot, "exists", False):
        return {}
    payload = snapshot.to_dict()
    return dict(payload) if isinstance(payload, Mapping) else {}


def _get_document(db_client: Any, path: str, *, label: str) -> dict[str, Any]:
    payload = _as_dict(db_client.document(path).get())
    if not payload:
        raise JITQASweepOperatorError(f"QA sweep {label} is missing")
    return payload


def _read_output_rows(db_client: Any, run_id: str) -> list[dict[str, Any]]:
    collection = db_client.collection(OUTPUT_COLLECTION)
    selector = getattr(collection, "select", None)
    if not callable(selector):
        raise JITQASweepOperatorError("QA sweep consumer requires metadata-only receipt projection")
    query = selector(list(OUTPUT_FIELDS))
    if query is None:
        raise JITQASweepOperatorError("QA sweep consumer requires metadata-only receipt projection")
    try:
        query = query.where(filter=FieldFilter("qa_run_id", "==", run_id))
    except TypeError:
        query = query.where("qa_run_id", "==", run_id)
    limiter = getattr(query, "limit", None)
    streamer = getattr(query, "stream", None)
    if not callable(limiter) or not callable(streamer):
        raise JITQASweepOperatorError("QA sweep consumer cannot bound receipt inventory")
    snapshots = list(limiter(9).stream())
    if len(snapshots) > 8:
        raise JITQASweepOperatorError("QA sweep produced more than eight bounded output rows")
    return [_as_dict(snapshot) for snapshot in snapshots]


def _validate_live_input_evidence(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Require current Chat-backed source metadata in the durable output.

    The seed operator deliberately creates ``legacy_migration`` rows so the
    migration proof can be exercised. Those rows are historical fixtures and
    cannot satisfy this sweep gate. A real sweep candidate must retain the
    server source identity and at least one conversation reference; IDs and
    source types are sufficient evidence here and no private content is read.
    """

    chat_backed = 0
    source_types: set[str] = set()
    for row in rows:
        source_type = row.get("source_type")
        source_id = row.get("source_id")
        source_version = row.get("source_version")
        source_refs = row.get("source_refs")
        if (
            source_type == "legacy_migration"
            or "legacy_migration" in str(source_id).casefold()
            or "legacy" in str(source_id).casefold()
        ):
            raise JITQASweepOperatorError("historical legacy_migration rows cannot prove a live QA sweep input")
        if source_type not in LIVE_SOURCE_TYPES:
            raise JITQASweepOperatorError("QA sweep output has an unsupported or missing source type")
        if not isinstance(source_id, str) or not source_id.strip():
            raise JITQASweepOperatorError("QA sweep output has no source id")
        if not isinstance(source_version, str) or not source_version.strip():
            raise JITQASweepOperatorError("QA sweep output has no source version")
        if (
            not isinstance(source_refs, list)
            or not source_refs
            or any(not isinstance(ref, str) or not ref.strip() for ref in source_refs)
        ):
            raise JITQASweepOperatorError("QA sweep output has no bounded source references")
        source_types.add(source_type)
        if source_type in {"daily_summary", "onboarding"} and any(
            ref.startswith("conversation:") for ref in source_refs
        ):
            chat_backed += 1
    if chat_backed < 1:
        raise JITQASweepOperatorError("QA sweep requires at least one current conversation-backed input")
    return {"chat_backed_rows": chat_backed, "source_types": sorted(source_types)}


def verify_qa_sweep_run(db_client: Any, *, run_id: str, minimum_output_rows: int = 1) -> dict[str, Any]:
    run_id = validate_qa_sweep_run_id(run_id)
    if minimum_output_rows < 1 or minimum_output_rows > 8:
        raise JITQASweepOperatorError("minimum_output_rows must be between 1 and 8")
    run_payload = _get_document(db_client, f"{QA_SWEEP_RUN_COLLECTION}/{run_id}", label="producer receipt")
    output_payload = _get_document(
        db_client,
        f"{QA_SWEEP_RUN_COLLECTION}/{run_id}/outputs/{QA_SWEEP_UID}",
        label="output row",
    )
    expected_identity = {
        "run_id": run_id,
        "uid": QA_SWEEP_UID,
        "project": QA_SWEEP_PROJECT,
        "database": QA_SWEEP_DATABASE,
    }
    for label, payload in (("producer receipt", run_payload), ("output row", output_payload)):
        for key, value in expected_identity.items():
            if payload.get(key) != value:
                raise JITQASweepOperatorError(f"QA sweep {label} has an unexpected {key}")
    if run_payload.get("schema_version") != QA_SWEEP_RECEIPT_SCHEMA_VERSION:
        raise JITQASweepOperatorError("QA sweep producer receipt schema is unsupported")
    if output_payload.get("schema_version") != QA_SWEEP_OUTPUT_SCHEMA_VERSION:
        raise JITQASweepOperatorError("QA sweep output row schema is unsupported")
    if run_payload.get("status") != "completed" or output_payload.get("status") != "completed":
        raise JITQASweepOperatorError("QA sweep producer did not complete")
    policy = run_payload.get("model_policy")
    if not isinstance(policy, Mapping) or policy != {
        "model_name": "gpt-5.6-luna",
        "max_model_candidates": 1,
        "max_model_cost_usd": 0.05,
        "provider_calls_allowed": 1,
    }:
        raise JITQASweepOperatorError("QA sweep model policy is outside the bounded proof contract")
    if output_payload.get("candidate_receipt_collection") != OUTPUT_COLLECTION:
        raise JITQASweepOperatorError("QA sweep output row points at an unexpected receipt collection")
    if output_payload.get("candidate_receipt_join_field") != "qa_run_id":
        raise JITQASweepOperatorError("QA sweep output row has no run-id join field")
    committed_candidates = output_payload.get("committed_candidates")
    if not isinstance(committed_candidates, int) or committed_candidates < minimum_output_rows:
        raise JITQASweepOperatorError("QA sweep produced fewer durable candidates than required")

    rows = _read_output_rows(db_client, run_id)
    if len(rows) != committed_candidates:
        raise JITQASweepOperatorError(
            f"QA sweep durable output rows={len(rows)}; producer receipt says {committed_candidates}"
        )
    for row in rows:
        if (
            row.get("uid") != QA_SWEEP_UID
            or row.get("qa_run_id") != run_id
            or row.get("receipt_state") != "committed"
            or row.get("outcome") != "committed"
            or not isinstance(row.get("memory_id"), str)
            or not row.get("memory_id")
            or not isinstance(row.get("candidate_digest"), str)
        ):
            raise JITQASweepOperatorError("QA sweep output receipt is foreign, incomplete, or not committed")
    input_evidence = _validate_live_input_evidence(rows)
    return {
        "schema_version": "omi.jit.qa.sweep-consumer.v1",
        "status": "PASS",
        "run_id": run_id,
        "project": QA_SWEEP_PROJECT,
        "database": QA_SWEEP_DATABASE,
        "uid": QA_SWEEP_UID,
        "durable_output_rows": len(rows),
        "committed_candidates": committed_candidates,
        "input_evidence": input_evidence,
        "producer_receipt_path": f"{QA_SWEEP_RUN_COLLECTION}/{run_id}",
        "output_collection": OUTPUT_COLLECTION,
        "model_policy": dict(policy),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id")
    parser.add_argument("--minimum-output-rows", type=int, default=1)
    parser.add_argument("command", choices=("verify", "validate-job"))
    parser.add_argument("--source-sha")
    parser.add_argument("--expected-image")
    parser.add_argument("--resource-json", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "validate-job":
        if not args.source_sha or not args.expected_image or args.resource_json is None:
            raise JITQASweepOperatorError("validate-job requires source SHA, expected image, and resource JSON")
        payload = json.loads(args.resource_json.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise JITQASweepOperatorError("QA sweep resource JSON must be an object")
        print(
            json.dumps(validate_job_resource(payload, source_sha=args.source_sha, expected_image=args.expected_image))
        )
        return 0
    if not args.run_id:
        raise JITQASweepOperatorError("verify requires --run-id")
    run_id = validate_qa_sweep_environment()
    if run_id != validate_qa_sweep_run_id(args.run_id):
        raise JITQASweepOperatorError("CLI run id does not match the server-selected QA run id")
    result = verify_qa_sweep_run(build_firestore_client(), run_id=run_id, minimum_output_rows=args.minimum_output_rows)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (JITQASweepOperatorError, ValueError) as exc:
        print(f"JIT QA sweep consumer refused: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

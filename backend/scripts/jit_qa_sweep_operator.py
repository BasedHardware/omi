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

from scripts import jit_qa_cloud_run_contract as qa_contract  # noqa: E402

QA_SWEEP_PROJECT = "based-hardware-dev"
QA_SWEEP_DATABASE = "jit-qa"
QA_SWEEP_UID = "vi7SA9ckQCe4ccobWNxlbdcNdC23"
QA_SWEEP_MODEL_NAME = "gpt-5.6-luna"
QA_SWEEP_MAX_MODEL_CANDIDATES = 1
QA_SWEEP_MAX_MODEL_COST_USD = 0.05
QA_SWEEP_MAX_CATCH_UP_DAYS = 1
QA_SWEEP_MAX_SUMMARY_CONVERSATIONS = 1
QA_SWEEP_MAX_SUMMARY_INPUT_CHARACTERS = 2_000
QA_SWEEP_MAX_TRANSCRIPT_FETCHES = 0
QA_SWEEP_MAX_TRANSCRIPT_FETCH_CHARACTERS = 0
QA_SWEEP_MAX_MEMORY_LOOKUPS = 0
QA_SWEEP_MAX_PROVIDER_CALLS = 1
QA_SWEEP_RECEIPT_SCHEMA_VERSION = "omi.jit.qa.daily-memory-sweep-run.v1"
QA_SWEEP_OUTPUT_SCHEMA_VERSION = "omi.jit.qa.daily-memory-sweep-output.v1"
QA_SWEEP_RUN_COLLECTION = "jit_qa_sweep_runs"
QA_SWEEP_OUTPUT_SUBCOLLECTION = "outputs"
QA_SWEEP_RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")

OUTPUT_COLLECTION = f"users/{QA_SWEEP_UID}/daily_memory_sweep_receipts"
CANONICAL_COLLECTION = f"users/{QA_SWEEP_UID}/memory_items"
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
SOURCE_FIELDS = ("uid", "status", "finished_at", "discarded", "finalization_status")
CANONICAL_FIELDS = (
    "memory_id",
    "uid",
    "status",
    "processing_state",
    "source_state",
    "content",
    "content_hash",
    "evidence",
    "ledger_schema_version",
    "updated_at",
)


class JITQASweepOperatorError(RuntimeError):
    """A QA sweep consumer precondition or proof assertion failed."""


def validate_qa_sweep_run_id(run_id: str) -> str:
    normalized = (run_id or "").strip()
    if not QA_SWEEP_RUN_ID_RE.fullmatch(normalized):
        raise ValueError("QA sweep run id must match [a-z0-9][a-z0-9_-]{0,47}")
    return normalized


def validate_qa_sweep_environment(environ: Mapping[str, str] | None = None) -> str:
    """Lazy bridge to runtime validation so ``validate-job`` stays pure.

    The daily sweep module imports encryption-backed runtime dependencies. Job
    resource validation has no reason to import that path, so this wrapper
    defers it until a real Firestore verification is requested.
    """

    from utils.memory.daily_memory_sweep import validate_qa_sweep_environment as validate

    return validate(environ)


def _projected_document(db_client: Any, path: str, fields: Sequence[str], *, label: str) -> dict[str, Any]:
    """Read one metadata projection; never fall back to a full private doc."""

    try:
        snapshot = db_client.document(path).get(field_paths=list(fields))
    except TypeError as exc:
        raise JITQASweepOperatorError(f"QA sweep {label} requires metadata-only projection") from exc
    except Exception as exc:
        raise JITQASweepOperatorError(f"QA sweep {label} read failed") from exc
    payload = _as_dict(snapshot)
    if not payload:
        raise JITQASweepOperatorError(f"QA sweep {label} is missing")
    return payload


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


def _validate_live_input_evidence(db_client: Any, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Prove source metadata points at an eligible recorded conversation.

    ``conversation:`` references are only identifiers.  The consumer reads a
    metadata projection of each source document to establish existence and
    terminal eligibility.  Omi Chat turns are not this source: the production
    provider reads completed recorded ``users/{uid}/conversations`` rows.
    """

    source_types: set[str] = set()
    verified_source_ids: set[str] = set()
    conversation_source_ids: set[str] = set()
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
        if source_type == "daily_summary" and source_id not in source_refs:
            raise JITQASweepOperatorError("QA sweep source id does not join its conversation reference")
        if source_type == "onboarding":
            onboarding_conversation = source_id.removeprefix("onboarding:")
            if not onboarding_conversation or f"conversation:{onboarding_conversation}" not in source_refs:
                raise JITQASweepOperatorError("QA sweep onboarding source id does not join its conversation reference")
        source_types.add(source_type)
        for source_ref in source_refs:
            if not source_ref.startswith("conversation:"):
                continue
            conversation_id = source_ref.removeprefix("conversation:").strip()
            if not conversation_id or "/" in conversation_id:
                raise JITQASweepOperatorError("QA sweep conversation source reference is malformed")
            path = f"users/{QA_SWEEP_UID}/conversations/{conversation_id}"
            payload = _projected_document(db_client, path, SOURCE_FIELDS, label="recorded conversation source")
            if payload.get("uid") not in (None, QA_SWEEP_UID):
                raise JITQASweepOperatorError("QA sweep source conversation belongs to another owner")
            status = getattr(payload.get("status"), "value", payload.get("status"))
            if bool(payload.get("discarded")) or status != "completed" or payload.get("finished_at") is None:
                raise JITQASweepOperatorError("QA sweep source conversation is not terminal and eligible")
            if source_type == "onboarding":
                finalization = getattr(payload.get("finalization_status"), "value", payload.get("finalization_status"))
                if finalization != "completed":
                    raise JITQASweepOperatorError("QA sweep onboarding source is not finalized")
            conversation_source_ids.add(source_ref)
            verified_source_ids.add(source_ref)
    if not conversation_source_ids:
        raise JITQASweepOperatorError(
            "QA sweep requires a conversation-backed source from a completed recorded conversation; ordinary Chat messages are not sweep input"
        )
    return {
        "source_surface": "recorded_conversation",
        "verified_source_count": len(verified_source_ids),
        "source_types": sorted(source_types),
    }


def _validate_canonical_outputs(db_client: Any, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Hydrate each committed memory id and return content-free proof."""

    memory_ids: list[str] = []
    content_digests: dict[str, str] = {}
    for row in rows:
        memory_id = row.get("memory_id")
        if not isinstance(memory_id, str) or not memory_id.strip() or "/" in memory_id:
            raise JITQASweepOperatorError("QA sweep output has an invalid canonical memory id")
        payload = _projected_document(
            db_client,
            f"{CANONICAL_COLLECTION}/{memory_id}",
            CANONICAL_FIELDS,
            label="canonical memory output",
        )
        if payload.get("uid") != QA_SWEEP_UID or payload.get("memory_id") != memory_id:
            raise JITQASweepOperatorError("QA sweep canonical memory output has unexpected identity")
        if getattr(payload.get("status"), "value", payload.get("status")) != "active":
            raise JITQASweepOperatorError("QA sweep canonical memory output is not active")
        if getattr(payload.get("processing_state"), "value", payload.get("processing_state")) != "processed":
            raise JITQASweepOperatorError("QA sweep canonical memory output is not processed")
        if getattr(payload.get("source_state"), "value", payload.get("source_state")) != "active":
            raise JITQASweepOperatorError("QA sweep canonical memory output source is not active")
        schema = payload.get("ledger_schema_version")
        if not isinstance(schema, str) or not schema.strip():
            raise JITQASweepOperatorError("QA sweep canonical memory output has no ledger schema")
        content = payload.get("content")
        if not isinstance(content, str) or not content.strip():
            raise JITQASweepOperatorError("QA sweep canonical memory output has no content")
        import hashlib

        content_digests[memory_id] = hashlib.sha256(content.encode("utf-8")).hexdigest()
        evidence = payload.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise JITQASweepOperatorError("QA sweep canonical memory output has no provenance evidence")
        source_id = row.get("source_id")
        source_type = row.get("source_type")
        source_version = row.get("source_version")
        matched = False
        for item in evidence:
            if not isinstance(item, Mapping):
                continue
            if (
                item.get("source_id") == source_id
                and item.get("source_type") == source_type
                and item.get("source_version") == source_version
                and getattr(item.get("source_state", "active"), "value", item.get("source_state", "active")) == "active"
            ):
                matched = True
                break
        if not matched:
            raise JITQASweepOperatorError("QA sweep canonical output provenance does not join candidate source")
        memory_ids.append(memory_id)
    return {
        "hydrated_memory_count": len(memory_ids),
        "memory_ids": memory_ids,
        "content_sha256": content_digests,
        "content_disclosed": False,
    }


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
        "model_name": QA_SWEEP_MODEL_NAME,
        "max_model_candidates": QA_SWEEP_MAX_MODEL_CANDIDATES,
        "max_model_cost_usd": QA_SWEEP_MAX_MODEL_COST_USD,
        "max_catch_up_days": QA_SWEEP_MAX_CATCH_UP_DAYS,
        "max_summary_conversations": QA_SWEEP_MAX_SUMMARY_CONVERSATIONS,
        "max_summary_input_characters": QA_SWEEP_MAX_SUMMARY_INPUT_CHARACTERS,
        "max_transcript_fetches": QA_SWEEP_MAX_TRANSCRIPT_FETCHES,
        "max_transcript_fetch_characters": QA_SWEEP_MAX_TRANSCRIPT_FETCH_CHARACTERS,
        "max_memory_lookups": QA_SWEEP_MAX_MEMORY_LOOKUPS,
        "provider_calls_allowed": QA_SWEEP_MAX_PROVIDER_CALLS,
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
    input_evidence = _validate_live_input_evidence(db_client, rows)
    canonical_output = _validate_canonical_outputs(db_client, rows)
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
        "canonical_output": canonical_output,
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

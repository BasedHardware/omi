#!/usr/bin/env python3
"""Read-only consumer for one server-admitted JIT QA daily-sweep run.

The Cloud Run sweep job is the producer. It tags each durable candidate receipt
with the server-supplied run id and creates one content-free run receipt. This
command reads both sides from the fixed QA database and never treats a
workflow execution counter or log line as product output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import uuid
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
QA_SWEEP_MAX_SDK_RETRIES = 0
QA_SWEEP_MAX_GATEWAY_ATTEMPTS = 1
QA_SWEEP_MAX_PROVIDER_CALLS = 1
# Keep these equal to the deployed memories route's QA request contract.  The
# checked-in gpt-5.6-luna card prices 12,288 input + 256 output tokens at under
# the $0.05 cap; the gateway's durable attempt row is the usage/cost authority.
QA_SWEEP_MAX_INPUT_TOKENS = 12_288
QA_SWEEP_MAX_OUTPUT_TOKENS = 256
QA_SWEEP_MAX_SPEND_MICRO_USD = 50_000
QA_SWEEP_ACCOUNTING_READ_RETRIES = 2
QA_SWEEP_ACCOUNTING_RETRY_DELAY_SECONDS = 1.0
QA_SWEEP_JIT_CONTRACT_VERSION = "jit-cloud-qa-v1"
QA_SWEEP_ROUTE_ARTIFACT_ID = "route.memories.model_config.001"
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
GATEWAY_ATTEMPT_COLLECTION = "llm_gateway_attempts"
GATEWAY_ATTEMPT_FIELDS = (
    "request_id",
    "attempt_id",
    "user_uid",
    "feature",
    "provider",
    "configured_model",
    "route_artifact_id",
    "retry_ordinal",
    "outcome",
    "usage_status",
    "cost_status",
    "estimated_cost_micro_usd",
    "prompt_tokens",
    "output_tokens",
    "total_tokens",
    "jit_run_id",
    "jit_contract_version",
)


class JITQASweepOperatorError(RuntimeError):
    """A QA sweep consumer precondition or proof assertion failed."""


def validate_qa_sweep_run_id(run_id: str) -> str:
    normalized = (run_id or "").strip()
    if not QA_SWEEP_RUN_ID_RE.fullmatch(normalized):
        raise ValueError("QA sweep run id must match [a-z0-9][a-z0-9_-]{0,47}")
    return normalized


def validate_qa_sweep_environment(environ: Mapping[str, str] | None = None) -> str:
    """Validate the fixed QA override set without importing runtime secrets."""

    env = environ if environ is not None else os.environ
    run_id = validate_qa_sweep_run_id(env.get("OMI_JIT_QA_SWEEP_RUN_ID", ""))
    required = {
        "OMI_ENV_STAGE": "dev",
        "GOOGLE_CLOUD_PROJECT": QA_SWEEP_PROJECT,
        "GCLOUD_PROJECT": QA_SWEEP_PROJECT,
        "OMI_FIRESTORE_DATA_PLANE_PROJECT": QA_SWEEP_PROJECT,
        "FIRESTORE_DATABASE_ID": QA_SWEEP_DATABASE,
        "FIREBASE_AUTH_PROJECT_ID": "based-hardware",
        "MEMORY_ENABLED": "on",
        "OMI_JIT_QA_AUTH_ONLY": "true",
        "OMI_JIT_QA_UID_ALLOWLIST": QA_SWEEP_UID,
        "OMI_JIT_QA_SWEEP_ADMISSION": "true",
        "MEMORY_DAILY_MEMORY_SWEEP_ENABLED": "true",
        "MEMORY_DAILY_MEMORY_SWEEP_KILL_SWITCH": "false",
        "MEMORY_DAILY_MEMORY_SWEEP_MODEL_ENABLED": "true",
        "MEMORY_DAILY_MEMORY_SWEEP_MODEL_NAME": QA_SWEEP_MODEL_NAME,
        "MEMORY_DAILY_MEMORY_SWEEP_MAX_MODEL_CANDIDATES": str(QA_SWEEP_MAX_MODEL_CANDIDATES),
        "MEMORY_DAILY_MEMORY_SWEEP_MAX_MODEL_COST_USD": f"{QA_SWEEP_MAX_MODEL_COST_USD:g}",
        "MEMORY_DAILY_MEMORY_SWEEP_COHORT_ENABLED": "true",
        "MEMORY_DAILY_MEMORY_SWEEP_COHORT_FLAG": "jit-qa-sweep-v1",
        "MEMORY_DAILY_MEMORY_SWEEP_TIMEZONE_RECONCILIATION_ENABLED": "false",
    }
    for name, expected in required.items():
        if env.get(name, "").strip().casefold() != expected.casefold():
            raise ValueError(f"QA sweep requires {name}={expected!r}")
    if env.get("FIRESTORE_EMULATOR_HOST", "").strip():
        raise ValueError("QA sweep proof must use named Cloud Firestore")
    # Cloud Run uses its named QA workload identity and the resource contract
    # rejects GOOGLE_APPLICATION_CREDENTIALS there. The manual GitHub
    # operator is different: google-github-actions/auth has already validated
    # an ADC file scoped to based-hardware-dev, and needs it to read Firestore.
    # Require an explicit marker for that reviewed operator boundary rather than
    # accepting an arbitrary customer credential in a locally-invoked proof.
    if env.get("SERVICE_ACCOUNT_JSON", "").strip() or env.get("FIREBASE_AUTH_CREDENTIALS_PATH", "").strip():
        raise ValueError("QA sweep proof cannot select customer Firebase credentials")
    if (
        env.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
        and env.get("OMI_JIT_QA_OPERATOR_APPROVED_ADC", "").strip().casefold() != "true"
    ):
        raise ValueError("QA sweep proof requires an explicitly validated development ADC")
    return run_id


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


def _read_gateway_attempt(db_client: Any, *, request_id: str, run_id: str) -> dict[str, Any]:
    """Join the producer request to exactly one durable gateway attempt.

    The sweep process can report how many requests it dispatched, but it cannot
    observe provider retries. The gateway accounting row is the authority for
    the actual attempt, route, usage, and cost; absence of that row is a proof
    failure rather than a zero-attempt claim.
    """

    try:
        uuid.UUID(request_id)
    except (ValueError, AttributeError, TypeError) as exc:
        raise JITQASweepOperatorError("QA sweep dispatch request id is malformed") from exc
    collection = db_client.collection(GATEWAY_ATTEMPT_COLLECTION)
    selector = getattr(collection, "select", None)
    if not callable(selector):
        raise JITQASweepOperatorError("QA sweep consumer requires gateway accounting projection")
    query = selector(list(GATEWAY_ATTEMPT_FIELDS))
    if query is None:
        raise JITQASweepOperatorError("QA sweep consumer requires gateway accounting projection")
    try:
        query = query.where(filter=FieldFilter("request_id", "==", request_id))
    except TypeError:
        query = query.where("request_id", "==", request_id)
    limiter = getattr(query, "limit", None)
    streamer = getattr(query, "stream", None)
    if not callable(limiter) or not callable(streamer):
        raise JITQASweepOperatorError("QA sweep consumer cannot bound gateway accounting inventory")
    snapshots: list[Any] = []
    for retry in range(QA_SWEEP_ACCOUNTING_READ_RETRIES + 1):
        snapshots = list(limiter(2).stream())
        if snapshots or retry == QA_SWEEP_ACCOUNTING_READ_RETRIES:
            break
        # Accounting is written by the gateway's durable completion path and
        # can lag the producer receipt. Retry absence only; a foreign or
        # malformed row is an immediate proof failure.
        time.sleep(QA_SWEEP_ACCOUNTING_RETRY_DELAY_SECONDS)
    if len(snapshots) != 1:
        raise JITQASweepOperatorError(
            "QA sweep gateway accounting must contain exactly one attempt for each dispatched request"
        )
    attempt = _as_dict(snapshots[0])
    if (
        attempt.get("request_id") != request_id
        or attempt.get("user_uid") != QA_SWEEP_UID
        or attempt.get("jit_run_id") != run_id
        or attempt.get("jit_contract_version") != QA_SWEEP_JIT_CONTRACT_VERSION
        or attempt.get("provider") != "openai"
        or attempt.get("feature") != "memories"
        or attempt.get("configured_model") != QA_SWEEP_MODEL_NAME
        or attempt.get("route_artifact_id") != QA_SWEEP_ROUTE_ARTIFACT_ID
        or attempt.get("outcome") != "success"
        or attempt.get("retry_ordinal") != 1
        or attempt.get("usage_status") != "confirmed"
    ):
        raise JITQASweepOperatorError("QA sweep gateway accounting attempt failed the joined success contract")
    for key, maximum in (("prompt_tokens", QA_SWEEP_MAX_INPUT_TOKENS), ("output_tokens", QA_SWEEP_MAX_OUTPUT_TOKENS)):
        value = attempt.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > maximum:
            raise JITQASweepOperatorError(f"QA sweep gateway {key} exceeded the admitted bound")
    cost = attempt.get("estimated_cost_micro_usd")
    if (
        not isinstance(cost, int)
        or isinstance(cost, bool)
        or cost < 0
        or cost > QA_SWEEP_MAX_SPEND_MICRO_USD
        or attempt.get("cost_status") != "estimated"
    ):
        raise JITQASweepOperatorError("QA sweep gateway cost is missing or exceeds the admitted spend bound")
    return {
        key: attempt.get(key)
        for key in (
            "request_id",
            "attempt_id",
            "feature",
            "provider",
            "configured_model",
            "route_artifact_id",
            "retry_ordinal",
            "outcome",
            "usage_status",
            "cost_status",
            "estimated_cost_micro_usd",
            "prompt_tokens",
            "output_tokens",
            "total_tokens",
        )
    }


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
        if schema != "knowledge_ledger.v1":
            raise JITQASweepOperatorError("QA sweep canonical memory output has an unsupported ledger schema")
        content = payload.get("content")
        if not isinstance(content, str) or not content.strip():
            raise JITQASweepOperatorError("QA sweep canonical memory output has no content")
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
        "sdk_max_retries": QA_SWEEP_MAX_SDK_RETRIES,
        "gateway_max_attempts": QA_SWEEP_MAX_GATEWAY_ATTEMPTS,
        "provider_calls_allowed": QA_SWEEP_MAX_PROVIDER_CALLS,
        "max_input_tokens": QA_SWEEP_MAX_INPUT_TOKENS,
        "max_output_tokens": QA_SWEEP_MAX_OUTPUT_TOKENS,
        "max_spend_micro_usd": QA_SWEEP_MAX_SPEND_MICRO_USD,
        "jit_contract_version": QA_SWEEP_JIT_CONTRACT_VERSION,
    }:
        raise JITQASweepOperatorError("QA sweep model policy is outside the bounded proof contract")
    if output_payload.get("candidate_receipt_collection") != OUTPUT_COLLECTION:
        raise JITQASweepOperatorError("QA sweep output row points at an unexpected receipt collection")
    if output_payload.get("candidate_receipt_join_field") != "qa_run_id":
        raise JITQASweepOperatorError("QA sweep output row has no run-id join field")
    dispatch_rows = run_payload.get("model_dispatch_evidence")
    if not isinstance(dispatch_rows, list) or not dispatch_rows:
        raise JITQASweepOperatorError("QA sweep dispatch evidence is missing")
    gateway_attempts: list[dict[str, Any]] = []
    dispatched_requests = 0
    for dispatch in dispatch_rows:
        if not isinstance(dispatch, Mapping):
            raise JITQASweepOperatorError("QA sweep dispatch evidence is malformed")
        if (
            dispatch.get("feature") != "memories"
            or dispatch.get("jit_run_id") != run_id
            or dispatch.get("sdk_max_retries") != QA_SWEEP_MAX_SDK_RETRIES
        ):
            raise JITQASweepOperatorError("QA sweep dispatch route or retry bound is outside the proof contract")
        requests = dispatch.get("requests")
        if not isinstance(requests, list):
            raise JITQASweepOperatorError("QA sweep request evidence is missing")
        dispatched_requests += len(requests)
        if dispatched_requests > QA_SWEEP_MAX_PROVIDER_CALLS:
            raise JITQASweepOperatorError("QA sweep request count exceeds the provider-call bound")
        for request in requests:
            if not isinstance(request, Mapping):
                raise JITQASweepOperatorError("QA sweep request evidence is malformed")
            request_id = request.get("request_id")
            if not isinstance(request_id, str):
                raise JITQASweepOperatorError("QA sweep dispatch request id is malformed")
            try:
                normalized_request_id = str(uuid.UUID(request_id))
            except (ValueError, AttributeError, TypeError) as exc:
                raise JITQASweepOperatorError("QA sweep dispatch request id is malformed") from exc
            if normalized_request_id != request_id.lower():
                raise JITQASweepOperatorError("QA sweep dispatch request id is malformed")
            if (
                request.get("max_input_tokens") != QA_SWEEP_MAX_INPUT_TOKENS
                or request.get("max_output_tokens") != QA_SWEEP_MAX_OUTPUT_TOKENS
                or request.get("max_spend_micro_usd") != QA_SWEEP_MAX_SPEND_MICRO_USD
            ):
                raise JITQASweepOperatorError("QA sweep request budget is outside the proof contract")
            input_bytes = request.get("input_bytes")
            if not isinstance(input_bytes, int) or isinstance(input_bytes, bool) or input_bytes <= 0:
                raise JITQASweepOperatorError("QA sweep request input evidence is malformed")
            if input_bytes > QA_SWEEP_MAX_INPUT_TOKENS:
                raise JITQASweepOperatorError("QA sweep request input exceeded the admitted byte bound")
            if request.get("usage_observed") is not True:
                raise JITQASweepOperatorError("QA sweep request usage was not observed")
            usage = request.get("usage_tokens")
            if (
                not isinstance(usage, Mapping)
                or not usage
                or any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in usage.values())
            ):
                raise JITQASweepOperatorError("QA sweep observed usage evidence is malformed")
            gateway_attempts.append(_read_gateway_attempt(db_client, request_id=request_id, run_id=run_id))
    if dispatched_requests != QA_SWEEP_MAX_PROVIDER_CALLS:
        raise JITQASweepOperatorError("QA sweep did not produce the admitted number of gateway requests")
    committed_candidates = output_payload.get("committed_candidates")
    if (
        not isinstance(committed_candidates, int)
        or isinstance(committed_candidates, bool)
        or committed_candidates < minimum_output_rows
        or committed_candidates > QA_SWEEP_MAX_MODEL_CANDIDATES
    ):
        raise JITQASweepOperatorError("QA sweep durable candidates are outside the admitted bound")

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
        "model_dispatch_evidence": [dict(item) for item in dispatch_rows],
        "gateway_attempts": gateway_attempts,
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

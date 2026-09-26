#!/usr/bin/env python3
"""Build and validate a bounded, matched JIT cost-evidence run.

This driver deliberately has no provider client.  ``--plan`` emits
the exact synthetic inputs and source-derived route/prompt hashes that a later
operator run must use.  ``--join-receipts`` joins content-free endpoint
observations (including the exact ``X-Omi-Request-ID``) to an exported
``llm_gateway_attempts`` ledger, preserving every retry attempt.  The resulting
envelope is consumed by ``--validate-receipts`` together with a harness
sidecar.  The AccountingEvent remains the authority for
provider/model/rate-card/usage/cost; the sidecar joins each ``attempt_id`` to
the synthetic case and records the matched prompt/evidence hashes and all
gateway/tool/cache counters.  Missing usage, model, route, hash, attempt,
tool-round, cache-unit, or cost fields remain unknown and block the
comparison; they are never converted to zero.
The capture modes read only an explicitly named QA agent-state snapshot and,
for ``--export-attempts``/``--export-jit-receipt``, an explicitly fenced
development Firestore ledger;
they never invoke a provider.
The released desktop proactivity response exposes only lane/model and limited
cache usage; it is not a cost receipt.  Legacy and nano therefore require a
durable ``llm_gateway_attempts`` event joined by the exact backend request ID.

The default sample is a three-case synthetic prompt-only proxy.  A real
producer-derived qualification uses exactly two already-completed JIT full
turns, one planned and one ambient, and never launches another full turn just
to populate this evidence.  It stays within the unchanged 3/8/3/1 daily caps.
The fixture is prompt-only evidence until a receipt file is supplied and
validated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

DEFAULT_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "testing"
    / "jit_processing"
    / "fixtures"
    / "jit_architecture_quality_cost_v2.json"
)
DEFAULT_CASE_IDS = ("actionable_deadline", "ambiguous_context", "already_visible")
CAPS = {
    "notifications_per_day": 3,
    "nano_triage_per_day": 8,
    "full_turns_per_day": 3,
    "full_turns_per_candidate": 1,
}
BUDGET_CAP_MICRO_USD = 5_000_000
JIT_FULL_RESERVATION_MICRO_USD = 50_000
# These are the ceilings enforced by the qualification budget and the
# OpenAI-compatible gateway request guard.  The gateway intentionally counts
# serialized UTF-8 bytes as a conservative, tokenizer-independent input-token
# upper bound (see ``_apply_jit_request_budget``), so this driver measures the
# same representation before any network call.
JIT_MAX_INPUT_ENVELOPE_BYTES = 32_768
JIT_MAX_OUTPUT_TOKENS = 2_048
JIT_RUNTIME_GUARD_SOURCE = (
    "backend/llm_gateway/gateway/jit_budget.py:24-25; " "backend/llm_gateway/routers/openai_compatible.py:823-842"
)
MAX_TOOL_MANIFEST_BYTES = 256 * 1024
RECEIPT_SCHEMA_VERSION = "omi.jit.cost_evidence.receipts.v1"
QA_OWNER_UID = "vi7SA9ckQCe4ccobWNxlbdcNdC23"
# AgentRuntimeProcess.defaultStateDirectory() scopes state by the QA bundle
# identifier. Keep this distinct from the QA Firestore database ID (jit-qa).
QA_BUNDLE_IDENTIFIER = "com.omi.omi-jit-qa"
QA_STATE_DIR_NAME = QA_BUNDLE_IDENTIFIER
AGENT_DATABASE_FILENAME = "omi-agentd.sqlite3"
QA_STATE_PATH_SUFFIX = Path("Application Support") / "Omi" / "AgentRuntime" / QA_BUNDLE_IDENTIFIER
MAX_AGENT_TOOL_ROUNDS = 500
MAX_FIRESTORE_REQUEST_IDS = 30
MAX_JIT_GATEWAY_ATTEMPTS = 500
PRODUCER_LANES = ("planned", "ambient")
MAX_PRODUCER_RUNS = len(PRODUCER_LANES)
SOURCE_PROJECTION_SCHEMA_VERSION = "omi.jit.proactivity.source_projection.v1"
# New producer runs persist the source-owned projection as a dedicated run
# input field. The metadata spelling is retained only for explicitly opted-in
# reads of old private QA records during this migration.
SOURCE_PROJECTION_RUN_INPUT_KEY = "jitCostEvidenceProjection"
SOURCE_PROJECTION_LEGACY_METADATA_KEY = "jitCostEvidenceProjection"
SOURCE_PROJECTION_METADATA_KEY = SOURCE_PROJECTION_LEGACY_METADATA_KEY
NANO_BILLING_SCHEMA_VERSION = "omi.jit.proactivity.nano_billing.v1"

# Only these AccountingEvent fields cross the evidence boundary.  In
# particular, a broad Firestore export may contain user identifiers or other
# metadata; the comparison needs attribution and pricing fields, never
# prompts or account content.
ACCOUNTING_RECEIPT_FIELDS = (
    "attempt_id",
    "request_id",
    "api_surface",
    "invocation_id",
    "provider",
    "configured_model",
    "actual_model_version",
    "usage_status",
    "uncached_input_tokens",
    "cached_input_tokens",
    "cache_write_tokens",
    "cache_write_ttl",
    "output_tokens",
    "reasoning_tokens",
    "cache_status",
    "cost_status",
    "estimated_cost_micro_usd",
    "rate_card_id",
    "cost_basis",
    "retry_ordinal",
)
SIDECAR_FIELDS = (
    "run_id",
    "gateway_run_id",
    "agent_run_id",
    "agent_request_id",
    "attempt_ids",
    "request_id",
    "case_id",
    "architecture",
    "stage",
    "gateway_lane",
    "producer_lane",
    "evidence_sha256",
    "prompt_sha256",
    "uncached_prompt_sha256",
    "system_prompt_sha256",
    "tool_rounds",
    "tool_invocations",
    "receipt_origin",
)


class EvidenceError(ValueError):
    """A receipt or fixture cannot support a cost comparison."""


@dataclass(frozen=True)
class Route:
    architecture: str
    stage: str
    gateway_lane: str
    provider: str
    served_model: str
    rate_card_id: str
    prompt_hash_key: str
    system_prompt_hash_key: str | None = None


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load_json(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"cannot read JSON fixture {path}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise EvidenceError(f"JSON root must be an object: {path}")
    return value


def _fixture_routes(fixture: Mapping[str, Any]) -> dict[tuple[str, str], Route]:
    try:
        raw = fixture["billing_receipt_contract"]["runtime_route_contract"]
    except (KeyError, TypeError) as exc:
        raise EvidenceError("fixture has no runtime route contract") from exc
    try:
        return {
            ("legacy", "full"): Route(
                architecture="legacy",
                stage="full",
                gateway_lane=raw["legacy_director"]["gateway_lane"],
                provider=raw["legacy_director"]["provider"],
                served_model=raw["legacy_director"]["model"],
                rate_card_id=raw["legacy_director"]["rate_card_id"],
                prompt_hash_key="prompt_sha256",
            ),
            ("jit", "nano"): Route(
                architecture="jit",
                stage="nano",
                gateway_lane=raw["jit_nano"]["gateway_lane"],
                provider=raw["jit_nano"]["provider"],
                served_model=raw["jit_nano"]["model"],
                rate_card_id=raw["jit_nano"]["rate_card_id"],
                prompt_hash_key="nano_prompt_sha256",
            ),
            ("jit", "full"): Route(
                architecture="jit",
                stage="full",
                gateway_lane=raw["jit_full"]["gateway_lane"],
                provider=raw["jit_full"]["provider"],
                served_model=raw["jit_full"]["model"],
                rate_card_id=raw["jit_full"]["rate_card_id"],
                prompt_hash_key="full_prompt_sha256",
                system_prompt_hash_key="full_system_prompt_sha256",
            ),
        }
    except (KeyError, TypeError) as exc:
        raise EvidenceError(f"fixture route contract is incomplete: {exc}") from exc


def _case_map(fixture: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    cases = fixture.get("cases")
    if not isinstance(cases, list):
        raise EvidenceError("fixture cases must be a list")
    result: dict[str, Mapping[str, Any]] = {}
    for case in cases:
        if not isinstance(case, Mapping) or not isinstance(case.get("case_id"), str):
            raise EvidenceError("fixture contains a malformed case")
        result[case["case_id"]] = case
    return result


def _evidence_hash(case: Mapping[str, Any]) -> str:
    evidence = case.get("shared_evidence")
    if not isinstance(evidence, Mapping):
        raise EvidenceError(f"case {case.get('case_id')} has no shared evidence")
    canonical = json.dumps(evidence, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return _sha256(canonical)


def _matched_inputs(case: Mapping[str, Any]) -> dict[str, str]:
    evidence = case["shared_evidence"]
    legacy = case["prompt_inputs"]["legacy_probe_projection"]
    jit = case["prompt_inputs"]["jit_projection"]
    now = evidence.get("now")
    timezone = evidence.get("timezone")
    captured_at = legacy.get("captured_at")
    context_id = jit.get("context_id")
    if not all(isinstance(value, str) and value for value in (now, timezone, captured_at, context_id)):
        raise EvidenceError(f"case {case['case_id']} lacks evaluation time, timezone, or context ID")
    if now != captured_at:
        raise EvidenceError(f"case {case['case_id']} has mismatched evaluation and captured times")
    if context_id != legacy.get("bucket_id"):
        raise EvidenceError(f"case {case['case_id']} has mismatched legacy/JIT context IDs")
    return {
        "evaluation_time": now,
        "timezone": timezone,
        "context_id": context_id,
        "evidence_sha256": _evidence_hash(case),
    }


def _expected_prompt(case: Mapping[str, Any], route: Route) -> dict[str, str]:
    prompts = case["prompts"]
    if route.architecture == "legacy":
        legacy = prompts["legacy"]
        if not isinstance(legacy.get("prompt_sha256"), str) or not isinstance(
            legacy.get("uncached_prompt_sha256"), str
        ):
            raise EvidenceError(f"case {case['case_id']} lacks the legacy prompt hashes")
        return {
            "prompt_sha256": legacy["prompt_sha256"],
            "uncached_prompt_sha256": legacy["uncached_prompt_sha256"],
        }
    jit = prompts["jit"]
    expected = {"prompt_sha256": jit[route.prompt_hash_key]}
    if route.system_prompt_hash_key:
        expected["system_prompt_sha256"] = jit[route.system_prompt_hash_key]
    return expected


def _materialized_prompts(case: Mapping[str, Any], architecture: str, stage: str) -> dict[str, str]:
    """Return source-materialized prompt strings without exposing them in output."""
    prompts = case.get("prompts")
    if not isinstance(prompts, Mapping):
        raise EvidenceError(f"case {case.get('case_id')} has no prompt materialization")
    if architecture == "legacy":
        source = prompts.get("legacy")
        fields = {
            "prompt": "materialized_prompt",
            "uncached_prompt": "materialized_uncached_prompt",
        }
    elif stage == "nano":
        source = prompts.get("jit")
        fields = {"prompt": "materialized_nano_prompt"}
    elif stage == "full":
        source = prompts.get("jit")
        fields = {
            "prompt": "materialized_full_prompt",
            "system_prompt": "materialized_full_system_prompt",
        }
    else:
        raise EvidenceError(f"unsupported materialized route: {architecture}/{stage}")
    if not isinstance(source, Mapping):
        raise EvidenceError(f"case {case.get('case_id')} has no {architecture}/{stage} prompt materialization")
    result: dict[str, str] = {}
    for output_key, source_key in fields.items():
        value = source.get(source_key)
        if not isinstance(value, str):
            raise EvidenceError(f"case {case.get('case_id')} lacks {source_key}")
        result[output_key] = value
    return result


def _validate_materialized_prompts(
    case: Mapping[str, Any], routes: Mapping[tuple[str, str], Route], architecture: str, stage: str
) -> dict[str, str]:
    """Check the fixture's claimed hashes against its actual UTF-8 prompt bytes."""
    route = routes[(architecture, stage)]
    materialized = _materialized_prompts(case, architecture, stage)
    expected = _expected_prompt(case, route)
    hash_sources = {
        "prompt_sha256": "prompt",
        "uncached_prompt_sha256": "uncached_prompt",
        "system_prompt_sha256": "system_prompt",
    }
    for hash_key, value in expected.items():
        source_key = hash_sources.get(hash_key)
        if source_key is None or source_key not in materialized:
            raise EvidenceError(f"case {case['case_id']} has no materialized value for {hash_key}")
        if _sha256(materialized[source_key]) != value:
            raise EvidenceError(f"case {case['case_id']} {source_key} hash does not match materialized UTF-8 bytes")
    return materialized


def _validate_fixture(fixture: Mapping[str, Any]) -> None:
    if fixture.get("schema_version") != "jit_architecture_quality_cost.v2":
        raise EvidenceError("driver requires the v2 matched-input fixture")
    if fixture.get("prompt_replay_scope", {}).get("status") != "prompt_only_proxy":
        raise EvidenceError("fixture scope must remain explicitly prompt_only_proxy")
    if fixture.get("prompt_replay_scope", {}).get("provider_calls_executed") != 0:
        raise EvidenceError("fixture claims provider calls; refusing to treat it as a zero-call proxy")
    if fixture.get("execution_contract", {}).get("hard_caps") != CAPS:
        raise EvidenceError("fixture caps changed; refresh the operator contract before running")
    if fixture.get("execution_contract", {}).get("operational_cost_cap_usd") != 5.0:
        raise EvidenceError("fixture cost cap changed; refresh the operator contract before running")
    _fixture_routes(fixture)
    _case_map(fixture)


def build_plan(fixture: Mapping[str, Any], case_ids: Sequence[str]) -> dict[str, Any]:
    """Return a no-call execution plan for matched synthetic inputs."""
    _validate_fixture(fixture)
    cases = _case_map(fixture)
    routes = _fixture_routes(fixture)
    if not case_ids:
        raise EvidenceError("at least one case is required")
    if len(set(case_ids)) != len(case_ids):
        raise EvidenceError("case IDs must be unique")
    if len(case_ids) > CAPS["notifications_per_day"]:
        raise EvidenceError("selected sample exceeds the unchanged notification cap")

    planned_cases: list[dict[str, Any]] = []
    for case_id in case_ids:
        case = cases.get(case_id)
        if case is None:
            raise EvidenceError(f"unknown fixture case: {case_id}")
        if case.get("comparability", {}).get("status") == "blocked_context_gap":
            raise EvidenceError(f"case {case_id} has a blocked context projection")
        matched = _matched_inputs(case)
        legacy_route = routes[("legacy", "full")]
        nano_route = routes[("jit", "nano")]
        full_route = routes[("jit", "full")]
        planned_cases.append(
            {
                "case_id": case_id,
                "category": case.get("category"),
                "matched_input": matched,
                "legacy": {
                    "route": legacy_route.__dict__,
                    "prompt_hashes": _expected_prompt(case, legacy_route),
                    "operation_count_exact": 1,
                    "gateway_attempts": "all durable attempt rows; retries are not capped by this operation count",
                },
                "jit": {
                    "nano": {
                        "route": nano_route.__dict__,
                        "prompt_hashes": _expected_prompt(case, nano_route),
                        "operation_count_exact": 1,
                        "gateway_attempts": "all durable attempt rows; retries are not capped by this operation count",
                    },
                    "full": {
                        "route": full_route.__dict__,
                        "prompt_hashes": _expected_prompt(case, full_route),
                        "full_turns_max": 1,
                        "gateway_attempts": "all producer receipt attempt IDs",
                    },
                },
            }
        )

    return {
        "schema_version": "omi.jit.cost_evidence.plan.v1",
        "status": "matched_input_plan",
        "evidence_scope": "prompt_only_proxy; no provider calls",
        "fixture_schema_version": fixture["schema_version"],
        "same_synthetic_context_per_case": True,
        "same_evaluation_time_and_timezone_per_case": True,
        "caps": CAPS,
        "budget_cap_micro_usd": BUDGET_CAP_MICRO_USD,
        "jit_full_reservation_bound_micro_usd": JIT_FULL_RESERVATION_MICRO_USD,
        "minimum_runtime_sample": {
            "matched_cases": len(planned_cases),
            "legacy_operations_exact": len(planned_cases),
            "jit_nano_operations_exact": len(planned_cases),
            "jit_full_turns_max": len(planned_cases),
            "maximum_reserved_jit_full_usd": len(planned_cases) * JIT_FULL_RESERVATION_MICRO_USD / 1_000_000,
            "quality_judgment": "root-owned after trusted receipts and adjudication",
        },
        "cases": planned_cases,
        "receipt_contract": {
            # Legacy and JIT nano proactivity return envelopes whose durable
            # source is the backend AccountingEvent.  JIT full uses the
            # separate, prompt-free durable receipt below.  Do not make the
            # harness pretend that case IDs or prompt hashes are provider
            # fields.
            "legacy_accounting_event_fields": [
                "attempt_id",
                "invocation_id",
                "request_id",
                "api_surface",
                "provider",
                "configured_model",
                "actual_model_version",
                "outcome",
                "usage_status",
                "prompt_tokens",
                "uncached_input_tokens",
                "cached_input_tokens",
                "cache_write_tokens",
                "output_tokens",
                "reasoning_tokens",
                "cache_write_ttl",
                "cache_status",
                "cost_status",
                "estimated_cost_micro_usd",
                "rate_card_id",
                "cost_basis",
            ],
            "legacy_response_observation": {
                "endpoint": "POST /v1/desktop/proactivity/completions",
                "exposes": [
                    "operation",
                    "lane",
                    "provider_model",
                    "usage.cached_tokens",
                    "usage.cache_write_tokens",
                    "cache_write",
                    "fallback_class",
                ],
                "does_not_expose": [
                    "attempt_id",
                    "request_id",
                    "invocation_id",
                    "actual_model_version",
                    "rate_card_id",
                    "cost_status",
                    "estimated_cost_micro_usd",
                ],
                "consequence": (
                    "The endpoint response alone cannot support a trusted cost comparison. "
                    "Join the durable llm_gateway_attempts event by the exact backend request_id; "
                    "if that join is unavailable, leave legacy/nano cost unknown and stop."
                ),
            },
            "legacy_receipt_source": (
                "durable backend llm_gateway_attempts AccountingEvent, joined by exact request_id; "
                "the endpoint response is metadata only"
            ),
            "jit_receipt_source": (
                "jit-gateway-receipt-v1 rebuilt from durable llm_gateway_attempts by exact jit_run_id, "
                "joined to its content-free harness sidecar"
            ),
            "jit_gateway_attempt_fields": [
                "attempt_id",
                "provider",
                "configured_model",
                "actual_model_version",
                "rate_card_id",
                "cost_basis",
                "usage_status",
                "cost_status",
                "normalized_uncached_input_tokens",
                "cached_input_tokens",
                "cache_write_tokens",
                "output_tokens",
                "reasoning_tokens",
                "estimated_cost_micro_usd",
            ],
            "jit_gateway_aggregate_fields": [
                "attempt_count",
                "normalized_uncached_input_tokens",
                "cached_input_tokens",
                "cache_write_tokens",
                "output_tokens",
                "estimated_cost_micro_usd",
                "cost_status",
            ],
            "harness_sidecar_fields": [
                "run_id",
                "gateway_run_id",
                "agent_run_id",
                "agent_request_id",
                "attempt_ids",
                "case_id",
                "architecture",
                "stage",
                "gateway_lane",
                "producer_lane",
                "evidence_sha256",
                "prompt_sha256",
                "tool_rounds",
                "tool_invocations",
            ],
            "unknown_policy": "missing, malformed, aggregate-only, or zero-placeholder cost/counters block; never infer zero",
            "counting": (
                "sum every trusted provider-completion attempt; gateway_attempts is the number of distinct attempt IDs. "
                "The SQLite tool ledger is a provider/tool invocation count, not a model round count; only an explicit "
                "tool_rounds sidecar value may be reported as rounds. Cache units are cached plus cache-write token "
                "units from the receipt."
            ),
            "join": "sidecar.attempt_ids covers provider attempt IDs; run_id is sidecar-owned and stable for all operations in one case; gateway_run_id is the JIT budget execution ID when it differs",
            "legacy_receipts_key": "legacy_provider_receipts",
            "jit_nano_receipts_key": "jit_nano_provider_receipts",
            "actual_jit_nano_receipts_key": "actual_jit_nano_provider_receipts",
            "actual_jit_nano_receipt_origin": (
                "producer nano_billing.request_id joined to durable llm_gateway_attempts; replay nano is excluded from actual architecture cost"
            ),
            "jit_receipts_key": "jit_gateway_receipts",
        },
    }


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _notification_schema(*, allow_lookup: bool = False) -> dict[str, Any]:
    """Mirror ContextProactivityEngine.schema without importing Swift code."""
    properties: dict[str, Any] = {
        "decision": {
            "type": "string",
            "enum": ["suggest", "insight", "task_candidate", "resurface", "silence"],
        },
        "title": {"type": "string", "description": "The specific thing this is about."},
        "message": {"type": "string", "description": "What the user should know or do."},
        "reasoning": {"type": "string"},
        "bucket_entry_refs": {"type": "array", "items": {"type": "string"}},
        "fact_ids": {"type": "array", "items": {"type": "string"}},
        "task_refs": {"type": "array", "items": {"type": "string"}},
    }
    required = ["decision", "title", "message", "reasoning", "bucket_entry_refs", "fact_ids", "task_refs"]
    if allow_lookup:
        properties["lookup_query"] = {"type": "string"}
        required.append("lookup_query")
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _nano_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {"approved": {"type": "boolean"}},
        "required": ["approved"],
        "additionalProperties": False,
    }


def _materialized_descriptor(materialized: Mapping[str, str], key: str) -> dict[str, Any]:
    value = materialized[key]
    encoded = value.encode("utf-8")
    return {"sha256": _sha256_bytes(encoded), "utf8_bytes": len(encoded)}


def _proactive_request_payload(
    *, operation: str, prompt: str, uncached_prompt: str | None, max_completion_tokens: int, cache_key: str | None
) -> dict[str, Any]:
    content: list[dict[str, str]] = [{"type": "text", "text": prompt}]
    if uncached_prompt:
        content.append({"type": "text", "text": uncached_prompt})
    payload: dict[str, Any] = {
        "operation": operation,
        "messages": [{"role": "user", "content": content}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "desktop_proactivity",
                "strict": True,
                "schema": _nano_schema() if operation == "proactive_extraction" else _notification_schema(),
            },
        },
        "max_completion_tokens": max_completion_tokens,
    }
    if cache_key:
        payload["cache_key"] = cache_key
    return payload


def _proactive_gateway_payload(client_payload: Mapping[str, Any], *, gateway_lane: str) -> dict[str, Any]:
    """Apply the current server-side desktop-proactivity payload projection.

    The input endpoint body is not what ``_apply_jit_request_budget`` measures:
    the router adds the lane, metadata, and (for the legacy cache key) an
    explicit breakpoint before forwarding the body to the gateway. Measuring
    this projection avoids a false fit caused by omitting those fields.
    """
    operation = client_payload.get("operation")
    if not isinstance(operation, str):
        raise EvidenceError("proactivity payload has no operation")
    payload = {key: value for key, value in client_payload.items() if key not in {"operation", "cache_key"}}
    payload["model"] = gateway_lane
    payload["metadata"] = {
        "omi_feature": f"desktop_{operation}",
        "prompt_version": f"desktop_{operation}.v1",
        "parser_version": "desktop_proactive_json.v1",
    }
    # The current backend raises the legacy reasoning request to its known
    # recovery floor. This is a small body-size detail, but keeping it here
    # means the no-call measurement matches the forwarded request.
    if operation == "proactive_reasoning":
        payload["max_completion_tokens"] = max(int(payload["max_completion_tokens"]), 2_400)
    cache_key = client_payload.get("cache_key")
    # ``has_cacheable_prefix`` in the backend only emits these cache fields
    # when the first stable text is at least 1,024 tokens (the production
    # heuristic is four characters per token).  Keep the projection exact so
    # the dry-run does not claim cache accounting for a prefix the server
    # would leave unmarked.
    stable_prefix = ""
    messages = payload.get("messages")
    if isinstance(messages, list):
        for message in reversed(messages):
            if not isinstance(message, Mapping):
                continue
            content = message.get("content")
            if isinstance(content, list):
                first = next((part for part in content if isinstance(part, Mapping)), None)
                if isinstance(first, Mapping) and first.get("type") == "text" and isinstance(first.get("text"), str):
                    stable_prefix = first["text"]
                break
            if isinstance(content, str):
                stable_prefix = content
                break
    if isinstance(cache_key, str) and cache_key and len(stable_prefix) >= 4_096:
        payload["prompt_cache_key"] = cache_key
        payload["prompt_cache_options"] = {"mode": "explicit", "ttl": "30m"}
        if isinstance(messages, list) and messages:
            copied_messages = [dict(message) for message in messages if isinstance(message, Mapping)]
            if copied_messages and isinstance(copied_messages[0].get("content"), list):
                parts = list(copied_messages[0]["content"])
                marker = {"type": "text", "text": "", "prompt_cache_breakpoint": {"mode": "explicit"}}
                if not any(isinstance(part, Mapping) and part.get("prompt_cache_breakpoint") for part in parts):
                    parts.insert(1, marker)
                copied_messages[0]["content"] = parts
                payload["messages"] = copied_messages
    return payload


def _openai_tool_payload(tools: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Convert the source MCP definitions to the OpenAI tool wire shape."""
    result: list[dict[str, Any]] = []
    for tool in tools:
        result.append(
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["inputSchema"],
                },
            }
        )
    return result


def _load_tool_manifest(path: Path) -> tuple[list[Mapping[str, Any]], dict[str, Any]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"cannot read tool manifest {path}: {exc}") from exc
    metadata: dict[str, Any] = {}
    if isinstance(raw, Mapping):
        candidate = raw.get("tools")
        for key in ("adapter_id", "manifest_version", "manifest_digest", "context"):
            if key in raw:
                metadata[key] = raw[key]
    else:
        candidate = raw
    if not isinstance(candidate, list) or not candidate:
        raise EvidenceError("tool manifest must be a non-empty JSON list or an object with a tools list")
    if len(_json_bytes(candidate)) > MAX_TOOL_MANIFEST_BYTES:
        raise EvidenceError("tool manifest exceeds the bounded preflight size")
    names: set[str] = set()
    normalized: list[Mapping[str, Any]] = []
    for tool in candidate:
        if not isinstance(tool, Mapping):
            raise EvidenceError("tool manifest contains a malformed entry")
        name = tool.get("name")
        description = tool.get("description")
        input_schema = tool.get("inputSchema")
        if not isinstance(name, str) or not name or name in names:
            raise EvidenceError("tool manifest contains a missing or duplicate name")
        if not isinstance(description, str) or not description:
            raise EvidenceError(f"tool manifest entry {name} lacks a description")
        if not isinstance(input_schema, Mapping):
            raise EvidenceError(f"tool manifest entry {name} lacks inputSchema")
        names.add(name)
        normalized.append({"name": name, "description": description, "inputSchema": input_schema})
    metadata.update(
        {
            "tool_count": len(normalized),
            "manifest_utf8_bytes": len(_json_bytes(normalized)),
            "manifest_sha256": _sha256_bytes(_json_bytes(normalized)),
        }
    )
    return normalized, metadata


def _body_summary(body: Mapping[str, Any]) -> dict[str, Any]:
    encoded = _json_bytes(body)
    size = len(encoded)
    return {
        "request_body_sha256": _sha256_bytes(encoded),
        "request_utf8_bytes": size,
        "input_envelope_limit_bytes": JIT_MAX_INPUT_ENVELOPE_BYTES,
        "fits_input_envelope": size <= JIT_MAX_INPUT_ENVELOPE_BYTES,
    }


def preflight_payloads(
    fixture: Mapping[str, Any],
    case_ids: Sequence[str],
    *,
    tool_manifest: Sequence[Mapping[str, Any]] | None = None,
    tool_manifest_metadata: Mapping[str, Any] | None = None,
    kernel_system_prompt: str | None = None,
) -> dict[str, Any]:
    """Measure source-derived request envelopes without making any provider call.

    Legacy and nano use the exact Swift HTTP body shape. The full path uses the
    actual ``omi-sonnet`` OpenAI-compatible body shape, including the source
    MCP tool definitions. The full summary includes the kernel policy when the
    operator supplies the built runtime's policy artifact; without it the
    smaller result is explicitly labelled minimum-only and remains blocked.
    """
    plan = build_plan(fixture, case_ids)
    routes = _fixture_routes(fixture)
    tool_metadata = dict(tool_manifest_metadata or {})
    if tool_manifest is not None:
        tools = list(tool_manifest)
        if not tools:
            raise EvidenceError("tool manifest must be non-empty")
        # Re-run the same structural checks for callers that already loaded a
        # manifest from a test or an API rather than a file.
        names: set[str] = set()
        for tool in tools:
            if not isinstance(tool, Mapping):
                raise EvidenceError("tool manifest contains a malformed entry")
            if (
                not isinstance(tool.get("name"), str)
                or not tool["name"]
                or tool["name"] in names
                or not isinstance(tool.get("description"), str)
                or not isinstance(tool.get("inputSchema"), Mapping)
            ):
                raise EvidenceError("tool manifest contains an invalid entry")
            names.add(tool["name"])
        openai_tools = _openai_tool_payload(tools)
        tool_metadata.setdefault("tool_count", len(tools))
        tool_metadata.setdefault("manifest_utf8_bytes", len(_json_bytes(tools)))
        tool_metadata.setdefault("manifest_sha256", _sha256_bytes(_json_bytes(tools)))
    else:
        openai_tools = []

    case_results: list[dict[str, Any]] = []
    blocking_reasons: list[str] = []
    for planned in plan["cases"]:
        case_id = planned["case_id"]
        case = _case_map(fixture)[case_id]
        legacy_materialized = _validate_materialized_prompts(case, routes, "legacy", "full")
        nano_materialized = _validate_materialized_prompts(case, routes, "jit", "nano")
        full_materialized = _validate_materialized_prompts(case, routes, "jit", "full")

        legacy_body = _proactive_request_payload(
            operation="proactive_reasoning",
            prompt=legacy_materialized["prompt"],
            uncached_prompt=legacy_materialized["uncached_prompt"],
            max_completion_tokens=800,
            cache_key="director:v1",
        )
        nano_body = _proactive_request_payload(
            operation="proactive_extraction",
            prompt=nano_materialized["prompt"],
            uncached_prompt=None,
            max_completion_tokens=120,
            cache_key=None,
        )
        legacy_summary = {
            "endpoint": "POST /v1/desktop/proactivity/completions",
            "gateway_lane": routes[("legacy", "full")].gateway_lane,
            "provider": routes[("legacy", "full")].provider,
            "served_model": routes[("legacy", "full")].served_model,
            "prompt": _materialized_descriptor(legacy_materialized, "prompt"),
            "uncached_prompt": _materialized_descriptor(legacy_materialized, "uncached_prompt"),
            **_body_summary(
                _proactive_gateway_payload(
                    legacy_body,
                    gateway_lane=routes[("legacy", "full")].gateway_lane,
                )
            ),
        }
        nano_summary = {
            "endpoint": "POST /v1/desktop/proactivity/completions",
            "gateway_lane": routes[("jit", "nano")].gateway_lane,
            "provider": routes[("jit", "nano")].provider,
            "served_model": routes[("jit", "nano")].served_model,
            "prompt": _materialized_descriptor(nano_materialized, "prompt"),
            **_body_summary(
                _proactive_gateway_payload(
                    nano_body,
                    gateway_lane=routes[("jit", "nano")].gateway_lane,
                )
            ),
        }

        system_parts = [full_materialized["system_prompt"]]
        if kernel_system_prompt is not None:
            system_parts.insert(0, kernel_system_prompt)
        full_body = {
            "model": "omi-sonnet",
            "messages": [
                {"role": "system", "content": "\n".join(system_parts)},
                {"role": "user", "content": full_materialized["prompt"]},
            ],
            "tools": openai_tools,
            "max_tokens": JIT_MAX_OUTPUT_TOKENS,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        full_summary: dict[str, Any] = {
            "endpoint": "POST /v2/chat/completions",
            "requested_model": "omi-sonnet",
            "gateway_lane": routes[("jit", "full")].gateway_lane,
            "provider": routes[("jit", "full")].provider,
            "served_model": routes[("jit", "full")].served_model,
            "prompt": _materialized_descriptor(full_materialized, "prompt"),
            "jit_system_prompt": _materialized_descriptor(full_materialized, "system_prompt"),
            "tool_manifest": tool_metadata or None,
            "kernel_system_prompt_supplied": kernel_system_prompt is not None,
            **_body_summary(full_body),
        }
        case_result = {
            "case_id": case_id,
            "legacy": legacy_summary,
            "jit_nano": nano_summary,
            "jit_full": full_summary,
        }
        case_results.append(case_result)
        if not legacy_summary["fits_input_envelope"]:
            blocking_reasons.append(f"{case_id} legacy request exceeds the 32768-byte JIT envelope")
        if not nano_summary["fits_input_envelope"]:
            blocking_reasons.append(f"{case_id} nano request exceeds the 32768-byte JIT envelope")
        if tool_manifest is None:
            blocking_reasons.append("full JIT preflight requires the source-generated MCP tool manifest")
        if kernel_system_prompt is None:
            blocking_reasons.append("full JIT preflight requires the built kernel system-policy artifact")
        if not full_summary["fits_input_envelope"]:
            blocking_reasons.append(f"{case_id} full request exceeds the 32768-byte JIT envelope")

    if not tool_manifest:
        tool_metadata = None
    return {
        "schema_version": "omi.jit.cost_evidence.preflight.v1",
        "status": "blocked" if blocking_reasons else "ready_for_runtime",
        "evidence_scope": (
            "no-call serialized-envelope preflight; proves source/hash/size bounds only, "
            "not provider quality or architecture cost"
        ),
        "fixture_schema_version": fixture["schema_version"],
        "runtime_guard_source": JIT_RUNTIME_GUARD_SOURCE,
        "input_envelope": {
            "encoding": "UTF-8",
            "limit_bytes": JIT_MAX_INPUT_ENVELOPE_BYTES,
            "output_token_cap": JIT_MAX_OUTPUT_TOKENS,
            "modality": "text-only; image/audio calls remain rejected by the runtime guard",
        },
        "tool_manifest": tool_metadata,
        "kernel_system_prompt": {
            "supplied": kernel_system_prompt is not None,
            "utf8_bytes": len(kernel_system_prompt.encode("utf-8")) if kernel_system_prompt is not None else None,
            "sha256": _sha256(kernel_system_prompt) if kernel_system_prompt is not None else None,
        },
        "blocking_reasons": sorted(set(blocking_reasons)),
        "cases": case_results,
        "operator_recipe": [
            "npm --prefix desktop/macos/agent run build --silent",
            "Generate the service/coordinator omi-tools-stdio manifest from the built runtime with jitKnowledgeToolsEnabled=true and jitProactivity=true; assert the exact four read-only JIT tools and write JSON only to a temporary artifact.",
            "Generate kernelSystemPolicy(\"service\", \"coordinator\") from the same built runtime; write UTF-8 text only to a temporary artifact.",
            "Run jit_cost_evidence_driver.py --plan --plan-file <plan.json> and then --preflight --tool-manifest <manifest.json> --kernel-system-prompt <policy.txt> --plan-file <plan.json>.",
            "After parent approval, capture X-Omi-Request-ID for every legacy and nano response, join exact IDs to exported llm_gateway_attempts with --join-receipts, then validate the joined envelope; archive only content-free receipts and sidecars.",
        ],
    }


def _required_int(receipt: Mapping[str, Any], key: str, *, minimum: int = 0) -> int:
    value = receipt.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise EvidenceError(f"receipt {receipt.get('case_id', '?')} has unknown or invalid {key}")
    return value


def _required_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError(f"{label} is missing or empty")
    return value


def _content_free_accounting_receipt(row: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only the prompt-free fields needed by ``summarize_receipts``."""
    return {key: row[key] for key in ACCOUNTING_RECEIPT_FIELDS if key in row}


def _content_free_sidecar(sidecar: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only the opaque IDs and hashes needed to join a receipt."""
    return {key: sidecar[key] for key in SIDECAR_FIELDS if key in sidecar}


def _content_free_jit_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Copy the JIT receipt envelope without accepting arbitrary payload data."""
    allowed = ("schema_version", "run_id", "contract_version", "attempts", "aggregate")
    result = {key: receipt[key] for key in allowed if key in receipt}
    attempts = receipt.get("attempts")
    if isinstance(attempts, list):
        attempt_fields = (
            "attempt_id",
            "provider",
            "configured_model",
            "actual_model_version",
            "rate_card_id",
            "cost_basis",
            "usage_status",
            "cost_status",
            "normalized_uncached_input_tokens",
            "cached_input_tokens",
            "cache_write_tokens",
            "output_tokens",
            "reasoning_tokens",
            "estimated_cost_micro_usd",
        )
        result["attempts"] = [
            {key: item[key] for key in attempt_fields if key in item} for item in attempts if isinstance(item, Mapping)
        ]
    aggregate = receipt.get("aggregate")
    if isinstance(aggregate, Mapping):
        aggregate_fields = (
            "attempt_count",
            "normalized_uncached_input_tokens",
            "cached_input_tokens",
            "cache_write_tokens",
            "output_tokens",
            "reasoning_tokens",
            "estimated_cost_micro_usd",
            "cost_status",
        )
        result["aggregate"] = {key: aggregate[key] for key in aggregate_fields if key in aggregate}
    return result


def _canonical_json_hash(value: Any) -> str:
    """Hash canonical JSON without returning the JSON material."""
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _required_identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise EvidenceError(f"{label} is missing or malformed")
    return value.strip()


def _validate_nano_billing_observation(
    raw: Any,
    *,
    owner_id: str,
    producer_lane: str,
    execution_id: str,
) -> dict[str, Any]:
    """Keep the producer's content-free nano observation for a durable join.

    The desktop can identify the actual nano request, but it cannot price it.
    Accounting rows joined by that exact request ID remain authoritative; this
    projection deliberately carries no cost estimate.
    """
    if not isinstance(raw, Mapping):
        raise EvidenceError("JIT source projection nano_billing is malformed")
    if raw.get("schema_version") != NANO_BILLING_SCHEMA_VERSION:
        raise EvidenceError("JIT source projection nano_billing schema is unsupported")
    dispatch = raw.get("dispatch")
    if dispatch not in {"observed", "not_dispatched"}:
        raise EvidenceError("JIT source projection nano_billing dispatch is invalid")
    if dispatch == "not_dispatched" and producer_lane == "ambient":
        raise EvidenceError("ambient JIT nano billing cannot claim not_dispatched")
    if raw.get("lane") != producer_lane:
        raise EvidenceError("JIT source projection nano_billing lane differs from producer lane")
    if raw.get("owner_id") != owner_id:
        raise EvidenceError("JIT source projection nano_billing owner differs from QA owner")
    nano_context_id = _required_identifier(raw.get("context_id"), "JIT nano billing context_id")

    result: dict[str, Any] = {
        "schema_version": NANO_BILLING_SCHEMA_VERSION,
        "dispatch": dispatch,
        "lane": producer_lane,
        "owner_id": owner_id,
        # This is the nano context identity (for example, a trigger-scoped
        # ID), not the admitted bucket/context identity in matched_input.
        "context_id": nano_context_id,
    }
    required_string_fields = (
        "snapshot_revision",
        "budget_day",
        "candidate_id",
        "outcome",
        "operation",
        "execution_id",
    )
    for field in required_string_fields:
        result[field] = _required_identifier(raw.get(field), f"JIT nano billing {field}")
    optional_string_fields = (
        "request_id",
        "provider",
        "provider_model",
        "provider_response_id",
        "fallback_class",
    )
    for field in optional_string_fields:
        if field in raw and raw[field] is not None:
            result[field] = _required_identifier(raw[field], f"JIT nano billing {field}")
    account_generation = raw.get("account_generation")
    if isinstance(account_generation, bool) or not isinstance(account_generation, int) or account_generation < 0:
        raise EvidenceError("JIT nano billing account_generation is invalid")
    result["account_generation"] = account_generation
    if dispatch == "observed" and "request_id" not in result:
        raise EvidenceError("observed JIT nano billing has no exact request_id")
    if result["execution_id"] != execution_id:
        raise EvidenceError("JIT nano billing execution_id differs from JIT budget")

    integer_fields = (
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "cached_input_tokens",
        "cache_write_tokens",
        "provider_attempts",
    )
    for field in integer_fields:
        if field not in raw or raw[field] is None:
            continue
        value = raw[field]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise EvidenceError(f"JIT nano billing {field} is invalid")
        result[field] = value

    usage_status = raw.get("usage_status")
    if usage_status not in {"reported", "partial", "unknown", "not_applicable"}:
        raise EvidenceError("JIT source projection nano_billing usage_status is invalid")
    cost_status = raw.get("cost_status")
    if cost_status not in {"unknown", "not_applicable"}:
        raise EvidenceError("JIT source projection nano_billing cost_status must remain unknown")
    if dispatch == "observed" and cost_status != "unknown":
        raise EvidenceError("observed JIT nano billing cost_status must remain unknown until durable join")
    if raw.get("estimated_cost_micro_usd") is not None:
        raise EvidenceError("JIT source projection nano_billing cannot contain a cost estimate")
    result["usage_status"] = usage_status
    result["cost_status"] = cost_status

    attempt_ids = raw.get("attempt_ids")
    if not isinstance(attempt_ids, list) or len(attempt_ids) > MAX_JIT_GATEWAY_ATTEMPTS:
        raise EvidenceError("JIT nano billing attempt_ids is required and invalid")
    normalized_attempt_ids = [_required_identifier(value, "JIT nano billing attempt_id") for value in attempt_ids]
    if len(set(normalized_attempt_ids)) != len(normalized_attempt_ids):
        raise EvidenceError("JIT nano billing attempt_ids are duplicated")
    result["attempt_ids"] = normalized_attempt_ids
    if dispatch == "not_dispatched":
        if result.get("provider_attempts") != 0:
            raise EvidenceError("not_dispatched JIT nano billing requires provider_attempts=0")
        if normalized_attempt_ids:
            raise EvidenceError("not_dispatched JIT nano billing requires empty attempt_ids")
        if result["outcome"] != "not_dispatched":
            raise EvidenceError("not_dispatched JIT nano billing outcome must be not_dispatched")
        if usage_status != "not_applicable" or cost_status != "not_applicable":
            raise EvidenceError("not_dispatched JIT nano billing statuses must be not_applicable")
        forbidden_fields = {
            "request_id",
            "provider",
            "provider_model",
            "provider_response_id",
            "fallback_class",
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "cached_input_tokens",
            "cache_write_tokens",
            "cache_write_ttl",
            "cache_status",
            "estimated_cost_micro_usd",
        }
        present_forbidden_fields = sorted(field for field in forbidden_fields if field in raw)
        if present_forbidden_fields:
            raise EvidenceError(
                "not_dispatched JIT nano billing contains provider/usage fields: " + ", ".join(present_forbidden_fields)
            )
    return result


def _optional_opaque(value: Any, label: str) -> str | int | None:
    """Accept only bounded source identities, never arbitrary run metadata."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise EvidenceError(f"{label} has an invalid source identity")
    if isinstance(value, int):
        if value < 0:
            raise EvidenceError(f"{label} has an invalid source identity")
        return value
    return _required_identifier(value, label)


def _validate_source_projection(
    raw: Mapping[str, Any],
    *,
    owner_id: str,
    execution_id: str,
    evidence_sha256: str,
    expected_full_prompt: str,
    producer_lane: str | None = None,
    require_nano_billing: bool = True,
) -> dict[str, Any]:
    """Validate the producer-owned legacy/nano prompt materialization.

    The desktop source writes this private projection into the exact agent run
    input that contains the admitted snapshot.  The harness only returns hashes
    and route metadata; prompt bytes stay in the private run database.  Keeping
    this validator here prevents a hand-written fixture from becoming an
    apparent source projection.
    """
    if raw.get("schema_version") != SOURCE_PROJECTION_SCHEMA_VERSION:
        raise EvidenceError("JIT source projection schema is not the reviewed v1 contract")
    if raw.get("owner_id") != owner_id:
        raise EvidenceError("JIT source projection owner does not match the isolated QA owner")
    if raw.get("execution_id") != execution_id:
        raise EvidenceError("JIT source projection execution_id does not match the JIT budget")
    projection_lane = raw.get("producer_lane")
    if projection_lane not in PRODUCER_LANES:
        raise EvidenceError("JIT source projection producer_lane is missing or malformed")
    if producer_lane is not None and projection_lane != producer_lane:
        raise EvidenceError("JIT source projection lane does not match the producer run")
    projection_evidence = raw.get("evidence_sha256")
    if projection_evidence != evidence_sha256:
        raise EvidenceError("JIT source projection evidence does not match the admitted snapshot")
    matched_input = raw.get("matched_input")
    if not isinstance(matched_input, Mapping):
        raise EvidenceError("JIT source projection has no matched input")
    if matched_input.get("evidence_sha256") != evidence_sha256:
        raise EvidenceError("JIT source projection matched input is not pinned to admitted evidence")
    for key in ("evaluation_time", "timezone", "context_id"):
        _required_identifier(matched_input.get(key), f"JIT source projection {key}")

    def prompt(stage: str, key: str) -> str:
        stage_value = raw.get(stage)
        if not isinstance(stage_value, Mapping):
            raise EvidenceError(f"JIT source projection has no {stage} stage")
        value = stage_value.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > 256_000:
            raise EvidenceError(f"JIT source projection {stage}.{key} is missing or malformed")
        return value

    legacy_stage = raw.get("legacy")
    if not isinstance(legacy_stage, Mapping):
        raise EvidenceError("JIT source projection has no legacy stage")
    projection_mode = legacy_stage.get("projection_mode")
    if projection_mode != "director_baseline_v1":
        raise EvidenceError("JIT source projection legacy mode is not the reviewed director baseline")
    source_builders = legacy_stage.get("source_builders")
    if source_builders != [
        "ContextProactivityPromptBuilder.directorStablePrompt",
        "ContextProactivityPromptBuilder.directorVolatilePrompt",
    ]:
        raise EvidenceError("JIT source projection legacy builders are not the reviewed director builders")
    flags = legacy_stage.get("flags")
    if flags != [
        "allow_lookup=false",
        "include_interject_copy_budgets=false",
        "workstream_pooling=false",
        "proactive_candidates=false",
    ]:
        raise EvidenceError("JIT source projection legacy flags are not the reviewed baseline contract")
    legacy = {
        "prompt": prompt("legacy", "prompt"),
        "uncached_prompt": prompt("legacy", "uncached_prompt"),
        "projection_mode": projection_mode,
        "source_builders": list(source_builders),
        "flags": list(flags),
    }
    nano_stage = raw.get("nano")
    if not isinstance(nano_stage, Mapping) or nano_stage.get("source_builder") != (
        "JITProactivityPromptBuilder.nanoTriagePrompt"
    ):
        raise EvidenceError("JIT source projection nano builder is not the reviewed JIT triage builder")
    nano = {
        "prompt": prompt("nano", "prompt"),
        "source_builder": nano_stage["source_builder"],
    }
    full = raw.get("full")
    if not isinstance(full, Mapping):
        raise EvidenceError("JIT source projection has no full stage")
    if full.get("source_builder") != "JITProactivityPromptBuilder.fullTurnPrompt":
        raise EvidenceError("JIT source projection full builder is not the reviewed JIT full-turn builder")
    full_prompt = prompt("full", "prompt")
    if full_prompt != expected_full_prompt:
        raise EvidenceError("JIT source projection full.prompt does not equal the admitted producer prompt")
    full_materialization = {
        "prompt": full_prompt,
        "source_builder": full["source_builder"],
    }
    nano_billing = None
    if raw.get("nano_billing") is None:
        if require_nano_billing:
            raise EvidenceError("JIT source projection has no required nano_billing observation")
    else:
        nano_billing = _validate_nano_billing_observation(
            raw["nano_billing"],
            owner_id=owner_id,
            producer_lane=projection_lane,
            execution_id=execution_id,
        )
    return {
        "matched_input": {
            "evaluation_time": str(matched_input["evaluation_time"]),
            "timezone": str(matched_input["timezone"]),
            "context_id": str(matched_input["context_id"]),
            "evidence_sha256": evidence_sha256,
        },
        "legacy": legacy,
        "nano": nano,
        "full": full_materialization,
        "producer_lane": projection_lane,
        **({"nano_billing": nano_billing} if nano_billing is not None else {}),
    }


def _require_qa_owner(owner_id: str) -> None:
    if owner_id != QA_OWNER_UID:
        raise EvidenceError("capture owner is not the fixed isolated JIT QA owner")


def _ensure_private_export_directory(path: Path, *, parent: Path | None = None) -> None:
    """Create or validate one owner-only directory in the replay export root."""
    path = path.expanduser()
    if parent is not None and path.parent != parent:
        raise EvidenceError(f"replay directory escaped export root: {path}")
    if path.is_symlink():
        raise EvidenceError(f"refusing symlink replay directory: {path}")
    if not path.exists():
        try:
            # The caller's umask may be permissive.  The mode is checked and
            # fixed through the descriptor below before any prompt bytes are
            # written, so there is no path-level chmod/write window.
            path.mkdir(mode=0o700, parents=parent is None, exist_ok=False)
        except OSError as exc:
            raise EvidenceError(f"cannot create private replay directory: {path}") from exc

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise EvidenceError(f"cannot inspect private replay directory: {path}") from exc
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
            raise EvidenceError(f"replay directory must be an owned directory: {path}")
        os.fchmod(descriptor, 0o700)
    except OSError as exc:
        raise EvidenceError(f"cannot secure replay directory: {path}") from exc
    finally:
        os.close(descriptor)


def _write_private_file(path: Path, data: bytes, *, exclusive: bool = True) -> None:
    """Write one owner-only artifact with safe mode and symlink handling.

    Prompt/evidence files are never created with a process-default mode and
    chmod'd after the write.  New artifacts use O_EXCL|O_NOFOLLOW and 0600 at
    open time.  An existing capture envelope may be updated only when it is
    already an owned regular 0600 file; its descriptor is secured before it is
    truncated or written.
    """
    path = path.expanduser()
    flags = os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    created = False
    try:
        if exclusive:
            descriptor = os.open(path, flags | os.O_CREAT | os.O_EXCL, 0o600)
            created = True
        else:
            try:
                info = path.lstat()
            except FileNotFoundError:
                descriptor = os.open(path, flags | os.O_CREAT | os.O_EXCL, 0o600)
                created = True
            except OSError as exc:
                raise EvidenceError(f"cannot inspect private artifact: {path}") from exc
            else:
                if stat.S_ISLNK(info.st_mode):
                    raise EvidenceError(f"refusing symlink private artifact: {path}")
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                    raise EvidenceError(f"private artifact must be an owned 0600 file: {path}")
                descriptor = os.open(path, flags)
        actual = os.fstat(descriptor)
        if not stat.S_ISREG(actual.st_mode) or actual.st_uid != os.getuid():
            raise EvidenceError(f"private artifact must be an owned regular file: {path}")
        os.fchmod(descriptor, 0o600)
        if not exclusive:
            os.ftruncate(descriptor, 0)
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("private artifact write made no progress")
            view = view[written:]
        os.fsync(descriptor)
    except EvidenceError:
        raise
    except OSError as exc:
        raise EvidenceError(f"failed to write private artifact: {path}") from exc
    finally:
        # ``descriptor`` is only bound after a successful open.  Keeping the
        # close here avoids leaking an fd if fstat/fchmod/write fails.
        if "descriptor" in locals():
            os.close(descriptor)
    if created:
        # The open mode is authoritative; this catches an unusual filesystem
        # that ignored the requested mode without changing it after writing.
        try:
            info = path.lstat()
        except OSError as exc:
            raise EvidenceError(f"cannot verify private artifact: {path}") from exc
        if stat.S_ISLNK(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise EvidenceError(f"private artifact was not created as 0600: {path}")


def _load_private_json(path: Path) -> Mapping[str, Any]:
    """Read a separately exported projection only from an owner-only file."""
    try:
        info = path.lstat()
    except OSError as exc:
        raise EvidenceError(f"cannot inspect private source projection: {path}") from exc
    if stat.S_ISLNK(info.st_mode):
        raise EvidenceError(f"refusing symlink private source projection: {path}")
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise EvidenceError(f"private source projection must be an owned 0600 file: {path}")
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        actual = os.fstat(descriptor)
        if (
            not stat.S_ISREG(actual.st_mode)
            or actual.st_uid != os.getuid()
            or actual.st_mode & 0o077
            or actual.st_ino != info.st_ino
            or actual.st_dev != info.st_dev
        ):
            raise EvidenceError(f"private source projection changed during open: {path}")
        with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
            descriptor = -1
            value = json.load(stream)
    except EvidenceError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"cannot read private source projection {path}: {exc}") from exc
    finally:
        if descriptor is not None and descriptor >= 0:
            os.close(descriptor)
    if not isinstance(value, Mapping):
        raise EvidenceError(f"private source projection must be a JSON object: {path}")
    return value


def _qa_agent_database_path(path: Path) -> Path:
    """Resolve only the explicitly named isolated QA agent database."""
    try:
        resolved = path.expanduser().resolve(strict=True)
    except OSError as exc:
        raise EvidenceError(f"isolated QA agent database is unavailable: {path}") from exc
    if (
        resolved.name != AGENT_DATABASE_FILENAME
        or Path(*resolved.parts[-len(QA_STATE_PATH_SUFFIX.parts) - 1 : -1]) != QA_STATE_PATH_SUFFIX
    ):
        raise EvidenceError(f"agent database must end with /{QA_STATE_PATH_SUFFIX}/{AGENT_DATABASE_FILENAME}")
    return resolved


def _require_private_historical_agent_database(path: Path) -> Path:
    """Allow the legacy metadata projection only from private QA state.

    This compatibility path is for records made before the dedicated run
    input field shipped.  It must not turn a public or shared database's
    metadata into new source evidence.
    """
    resolved = _qa_agent_database_path(path)
    try:
        raw_info = path.expanduser().lstat()
        state_info = resolved.parent.lstat()
        database_info = resolved.lstat()
    except OSError as exc:
        raise EvidenceError(f"historical source projection requires inspectable private QA state: {path}") from exc
    if stat.S_ISLNK(raw_info.st_mode) or stat.S_ISLNK(state_info.st_mode) or stat.S_ISLNK(database_info.st_mode):
        raise EvidenceError("historical source projection refuses symlinked QA state")
    if (
        not stat.S_ISDIR(state_info.st_mode)
        or state_info.st_uid != os.getuid()
        or state_info.st_mode & 0o077
        or not stat.S_ISREG(database_info.st_mode)
        or database_info.st_uid != os.getuid()
        or database_info.st_mode & 0o077
    ):
        raise EvidenceError(
            "historical source projection requires owner-only QA state (0700 directory and 0600 database)"
        )
    return resolved


def _read_agent_run(
    database_path: Path,
    *,
    agent_run_id: str,
    owner_id: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Read one owner-scoped run and its tool ledger rows without writes."""
    resolved = _qa_agent_database_path(database_path)
    connection: sqlite3.Connection | None = None
    try:
        # The app may still have the database open and its newest rows in the
        # WAL.  A normal read-only connection sees the WAL; BEGIN makes both
        # queries one consistent snapshot.  Do not use SQLite's immutable URI
        # mode here because it can ignore a live WAL and miss the producer run.
        connection = sqlite3.connect(f"file:{resolved}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("BEGIN")
        run = connection.execute(
            """
            SELECT r.run_id, r.session_id, r.request_id, r.status, r.input_json,
                   r.result_json, r.system_prompt_hash, s.owner_id
            FROM runs AS r
            JOIN sessions AS s ON s.session_id = r.session_id
            WHERE r.run_id = ?
            """,
            (agent_run_id,),
        ).fetchone()
        if run is None:
            raise EvidenceError(f"agent run is unknown: {agent_run_id}")
        if run["owner_id"] != owner_id:
            raise EvidenceError("agent run owner does not match the fixed isolated QA owner")
        if run["status"] != "succeeded":
            raise EvidenceError(f"agent run status is not succeeded; receipt is unknown ({run['status']})")
        tool_rows = connection.execute(
            """
            SELECT invocation_id, run_id, attempt_id, owner_id, status
            FROM tool_invocation_ledger
            WHERE run_id = ?
            ORDER BY prepared_at_ms ASC, invocation_id ASC
            """,
            (agent_run_id,),
        ).fetchall()
        return dict(run), [dict(row) for row in tool_rows]
    except sqlite3.Error as exc:
        raise EvidenceError(f"cannot read isolated QA agent database: {resolved}") from exc
    finally:
        if connection is not None:
            try:
                connection.rollback()
            finally:
                connection.close()


def _producer_run_materialization(
    database_path: Path,
    *,
    agent_run_id: str,
    owner_id: str,
    projection_dir: Path | None = None,
    allow_legacy_private_metadata_projection: bool = False,
) -> dict[str, Any]:
    """Read and validate the content-free producer fields needed for replay.

    The JIT producer is the source of truth for the full prompt and admitted
    context.  The fixture cannot stand in for those bytes: its prompt hashes
    are intentionally only a no-call proxy.  Keep this helper shared by the
    derived-plan and capture paths so they cannot validate different input.
    """
    run, tool_rows = _read_agent_run(database_path, agent_run_id=agent_run_id, owner_id=owner_id)
    try:
        input_json = json.loads(str(run["input_json"]))
    except (TypeError, json.JSONDecodeError) as exc:
        raise EvidenceError("agent run input_json is not valid JSON") from exc
    if not isinstance(input_json, Mapping):
        raise EvidenceError("agent run input_json is not an object")
    if input_json.get("surfaceKind") != "service":
        raise EvidenceError("agent run surface is not the JIT service surface")
    if input_json.get("mode") != "ask":
        raise EvidenceError("JIT capture requires ask mode")
    metadata = input_json.get("metadata")
    if not isinstance(metadata, Mapping) or metadata.get("jitKnowledgeToolsEnabled") is not True:
        raise EvidenceError("agent run was not admitted with JIT knowledge tools enabled")
    budget = metadata.get("jitBudget")
    if not isinstance(budget, Mapping):
        raise EvidenceError("agent run has no JIT budget authority")
    contract_version = _required_identifier(budget.get("contractVersion"), "JIT budget contractVersion")
    execution_id = _required_identifier(budget.get("executionID"), "JIT budget executionID")
    if contract_version != "jit-cloud-qa-v1":
        raise EvidenceError("agent run JIT budget contract is not the reviewed QA contract")
    snapshot = input_json.get("admittedContextSnapshot")
    if not isinstance(snapshot, Mapping):
        raise EvidenceError("agent run has no admitted context snapshot for evidence hashing")
    if snapshot.get("ownerId") != owner_id:
        raise EvidenceError("admitted context snapshot owner does not match the fixed isolated QA owner")
    prompt = input_json.get("prompt")
    if not isinstance(prompt, str) or not prompt:
        raise EvidenceError("agent run has no producer prompt to hash")
    try:
        result_json = json.loads(str(run["result_json"]))
    except (TypeError, json.JSONDecodeError) as exc:
        raise EvidenceError("agent run result_json is not valid JSON") from exc
    if not isinstance(result_json, Mapping):
        raise EvidenceError("agent run result_json is not an object")
    if result_json.get("jitCostStatus") != "estimated":
        raise EvidenceError("agent run JIT cost status is unknown")
    raw_attempt_ids = result_json.get("jitReceiptAttemptIDs")
    if not isinstance(raw_attempt_ids, list) or not raw_attempt_ids:
        raise EvidenceError("agent run has no JIT receipt attempt IDs")
    attempt_ids = [_required_identifier(value, "agent run receipt attempt_id") for value in raw_attempt_ids]
    if len(set(attempt_ids)) != len(attempt_ids):
        raise EvidenceError("agent run receipt attempt IDs are duplicated")
    provider_attempts = result_json.get("jitProviderAttempts")
    if provider_attempts != len(attempt_ids):
        raise EvidenceError("agent run provider attempt count differs from receipt attempt IDs")
    if any(row.get("owner_id") != owner_id or row.get("run_id") != agent_run_id for row in tool_rows):
        raise EvidenceError("tool ledger contains a row for a different owner or run")
    if len(tool_rows) > MAX_AGENT_TOOL_ROUNDS:
        raise EvidenceError("tool ledger exceeds the bounded JIT tool-round capture limit")
    for row in tool_rows:
        _required_identifier(row.get("invocation_id"), "tool invocation_id")
    actual_prompt_sha256 = _sha256(prompt)
    # This is the Node runtime's canonical JSON hash of the admitted snapshot
    # object. It covers that persisted Node snapshot only; it is not a digest
    # of the Swift context bucket or its complete payload. The Swift source
    # projection carries prompt bytes and the temporal/context tuple separately.
    actual_evidence_sha256 = _canonical_json_hash(snapshot)
    source_identity = {}
    for key, value in {
        "runtime_source": metadata.get("source"),
        "context_snapshot_version": input_json.get("contextSnapshotVersion"),
        "context_snapshot_generation": input_json.get("contextSnapshotGeneration"),
        "context_renderer_fingerprint": input_json.get("contextRendererFingerprint"),
        "context_capability_version": input_json.get("contextCapabilityVersion"),
        "system_prompt_hash": run.get("system_prompt_hash"),
    }.items():
        sanitized = _optional_opaque(value, key)
        if sanitized is not None:
            source_identity[key] = sanitized
    source_projection_origin: str | None = None
    if SOURCE_PROJECTION_RUN_INPUT_KEY in input_json:
        raw_projection = input_json[SOURCE_PROJECTION_RUN_INPUT_KEY]
        if not isinstance(raw_projection, Mapping):
            raise EvidenceError("agent run dedicated JIT source projection is malformed")
        source_projection_origin = "run_input"
    elif projection_dir is not None:
        projection_path = projection_dir / f"{execution_id}.json"
        try:
            candidate = _load_private_json(projection_path)
        except EvidenceError as exc:
            raise EvidenceError(f"JIT source projection is missing for execution {execution_id}") from exc
        raw_projection = candidate
        source_projection_origin = "private_sidecar"
    elif SOURCE_PROJECTION_LEGACY_METADATA_KEY in metadata:
        if not allow_legacy_private_metadata_projection:
            raise EvidenceError(
                "agent run source projection must use the dedicated run-input field; "
                "legacy metadata projection requires explicit historical-private compatibility"
            )
        _require_private_historical_agent_database(database_path)
        raw_projection = metadata[SOURCE_PROJECTION_LEGACY_METADATA_KEY]
        if not isinstance(raw_projection, Mapping):
            raise EvidenceError("historical metadata JIT source projection is malformed")
        source_projection_origin = "legacy_private_metadata"
    else:
        raw_projection = None
    source_projection = None
    if isinstance(raw_projection, Mapping):
        source_projection = _validate_source_projection(
            raw_projection,
            owner_id=owner_id,
            execution_id=execution_id,
            evidence_sha256=actual_evidence_sha256,
            expected_full_prompt=prompt,
            producer_lane=next(
                (metadata[key] for key in ("producerLane", "proactivityLane", "lane") if key in metadata),
                None,
            ),
            require_nano_billing=source_projection_origin != "legacy_private_metadata",
        )
    return {
        "run": run,
        "input": input_json,
        "metadata": metadata,
        "budget": budget,
        "contract_version": contract_version,
        "execution_id": execution_id,
        "snapshot": snapshot,
        "prompt": prompt,
        "result": result_json,
        "attempt_ids": attempt_ids,
        "tool_rows": tool_rows,
        "prompt_sha256": actual_prompt_sha256,
        "evidence_sha256": actual_evidence_sha256,
        "source_identity": source_identity,
        "source_projection": source_projection,
        "source_projection_origin": source_projection_origin,
    }


def _planned_case_route(
    plan: Mapping[str, Any], *, case_id: str, architecture: str, stage: str
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    expected = _index_plan(plan).get((case_id, architecture, stage))
    if expected is None:
        raise EvidenceError(
            f"capture route is not present in the source-derived plan: {case_id}/{architecture}/{stage}"
        )
    case = next((item for item in plan.get("cases", []) if item.get("case_id") == case_id), None)
    if not isinstance(case, Mapping):
        raise EvidenceError(f"capture case is not present in the source-derived plan: {case_id}")
    return case, expected


def _producer_case(
    fixture: Mapping[str, Any],
    *,
    routes: Mapping[tuple[str, str], Route],
    case_id: str,
    lane: str | None,
    materialization: Mapping[str, Any],
) -> dict[str, Any]:
    """Describe one actual JIT turn without copying its prompt or context."""
    full_route = routes[("jit", "full")]
    full_prompt_hashes = {"prompt_sha256": materialization["prompt_sha256"]}
    system_prompt_hash = materialization["source_identity"].get("system_prompt_hash")
    if isinstance(system_prompt_hash, str) and system_prompt_hash:
        full_prompt_hashes["system_prompt_sha256"] = system_prompt_hash
    temporal = materialization["metadata"].get("temporalContext")
    if not isinstance(temporal, Mapping):
        temporal = {}
    evaluation_time = temporal.get("evaluatedAt")
    timezone = temporal.get("timezoneIdentifier")
    matched_input = {
        "evaluation_time": evaluation_time if isinstance(evaluation_time, str) else None,
        "timezone": timezone if isinstance(timezone, str) else None,
        "context_id": _optional_opaque(materialization["snapshot"].get("contextID"), "context_id"),
        "evidence_sha256": materialization["evidence_sha256"],
    }
    source_projection = materialization.get("source_projection")
    if isinstance(source_projection, Mapping):
        # The source projection is evaluated beside the JIT prompt, so it is
        # authoritative for the baseline's clock/context tuple. Its context ID
        # is a Swift source identifier, not a bucket-content digest; the
        # evidence hash above remains the Node snapshot hash. Recheck the
        # evidence hash and identity here as a second fence at the plan seam.
        projected_input = source_projection["matched_input"]
        if projected_input["evidence_sha256"] != materialization["evidence_sha256"]:
            raise EvidenceError("source projection evidence changed after producer materialization")
        if matched_input["context_id"] is not None and projected_input["context_id"] != matched_input["context_id"]:
            raise EvidenceError("source projection context does not match the admitted producer context")
        matched_input = dict(projected_input)
    baseline_unavailable_reason = (
        "the QA agent run persists the actual admitted snapshot and final JIT prompt, "
        "but no source-owned legacy/nano prompt projection; baseline replay is blocked"
    )
    unavailable = {
        "status": "unavailable",
        "blocking_reasons": [baseline_unavailable_reason],
        "prompt_hashes": {},
        "operation_count_exact": 0,
        "gateway_attempts": "unavailable until source-owned replay projection exists",
    }
    if isinstance(source_projection, Mapping):
        legacy_prompt = source_projection["legacy"]
        nano_prompt = source_projection["nano"]
        legacy = {
            "route": routes[("legacy", "full")].__dict__,
            "status": "source_owned",
            "prompt_hashes": {
                "prompt_sha256": _sha256(legacy_prompt["prompt"]),
                "uncached_prompt_sha256": _sha256(legacy_prompt["uncached_prompt"]),
            },
            "operation_count_exact": 1,
            "gateway_attempts": "all durable request attempt rows; retries count",
            "source_owned": True,
            "projection_mode": legacy_prompt["projection_mode"],
            "source_builders": legacy_prompt["source_builders"],
            "flags": legacy_prompt["flags"],
        }
        nano = {
            "route": routes[("jit", "nano")].__dict__,
            "status": "source_owned",
            "prompt_hashes": {"prompt_sha256": _sha256(nano_prompt["prompt"])},
            "operation_count_exact": 1,
            "gateway_attempts": "all durable request attempt rows; retries count",
            "source_owned": True,
            "source_builder": nano_prompt["source_builder"],
        }
        if isinstance(source_projection.get("nano_billing"), Mapping):
            # This is only the content-free producer observation. Its request
            # ID is joined to durable accounting separately from replay nano;
            # the source projection never supplies a cost.
            nano["actual_nano_billing"] = dict(source_projection["nano_billing"])
    else:
        legacy = {"route": routes[("legacy", "full")].__dict__, **unavailable}
        nano = {"route": routes[("jit", "nano")].__dict__, **unavailable}
    full = {
        "route": full_route.__dict__,
        "prompt_hashes": full_prompt_hashes,
        "full_turns_max": 1,
        "provider_attempts_exact": len(materialization["attempt_ids"]),
        "gateway_attempts": "all producer receipt attempt IDs; one full turn may contain retries",
        "producer_derived": True,
    }
    if isinstance(source_projection, Mapping):
        full["source_builder"] = source_projection["full"]["source_builder"]
    case: dict[str, Any] = {
        "case_id": case_id,
        "category": f"producer_observed_{lane}" if lane else "producer_observed",
        "matched_input": matched_input,
        "producer_identity": materialization["source_identity"],
        "producer_attempt_ids": materialization["attempt_ids"],
        "provider_attempts_exact": len(materialization["attempt_ids"]),
        # The SQLite ledger is one row per invocation. It does not persist a
        # model-round boundary, so this is deliberately not called rounds.
        "tool_invocations": len(materialization["tool_rows"]),
        "legacy": legacy,
        "jit": {
            "nano": nano,
            "full": full,
        },
    }
    if lane is not None:
        case["producer_lane"] = lane
    return case


def _producer_plan(
    fixture: Mapping[str, Any],
    *,
    owner_id: str,
    cases: Sequence[Mapping[str, Any]],
    materializations: Sequence[Mapping[str, Any]],
    status: str,
) -> dict[str, Any]:
    routes = _fixture_routes(fixture)
    case_list = [dict(case) for case in cases]
    producer_runs = []
    attempt_ids_by_case: dict[str, list[str]] = {}
    for case, materialization in zip(case_list, materializations, strict=True):
        case_id = _required_identifier(case["case_id"], "producer case_id")
        producer_runs.append(
            {
                "case_id": case_id,
                "producer_lane": case.get("producer_lane"),
                "owner_id": owner_id,
                "agent_run_id": _required_identifier(materialization["run"].get("run_id"), "agent_run_id"),
                "gateway_run_id": materialization["execution_id"],
                "prompt_sha256": materialization["prompt_sha256"],
                "evidence_sha256": materialization["evidence_sha256"],
                "provider_attempts_exact": len(materialization["attempt_ids"]),
                "tool_invocations": len(materialization["tool_rows"]),
                "source_identity": materialization["source_identity"],
            }
        )
        attempt_ids_by_case[case_id] = list(materialization["attempt_ids"])
    return {
        "schema_version": "omi.jit.cost_evidence.plan.v1",
        "status": status,
        "comparison_ready": False,
        "evidence_scope": (
            "actual QA producer snapshots/prompts from the planned and ambient full turns; no provider calls; "
            "legacy and nano source-builder projection unavailable"
        ),
        "fixture_schema_version": fixture["schema_version"],
        "producer_owner_id": owner_id,
        "producer_runs": producer_runs,
        "replay_projection": {
            "status": "blocked_source_builder_projection_required",
            "same_admitted_snapshot_per_case": True,
            "same_evaluation_time_per_case": all(
                case["matched_input"]["evaluation_time"] is not None for case in case_list
            ),
            "same_timezone_per_case": all(case["matched_input"]["timezone"] is not None for case in case_list),
            "legacy": {
                "status": "unavailable",
                "reason": "source-owned legacy/nano prompt projection is not persisted by the producer",
            },
            "nano": {
                "status": "unavailable",
                "reason": "source-owned legacy/nano prompt projection is not persisted by the producer",
            },
            "full": {
                "status": "producer_observed",
                "cases": [case["case_id"] for case in case_list],
            },
        },
        "caps": CAPS,
        "budget_cap_micro_usd": BUDGET_CAP_MICRO_USD,
        "jit_full_reservation_bound_micro_usd": JIT_FULL_RESERVATION_MICRO_USD,
        "minimum_runtime_sample": {
            "matched_cases": len(case_list),
            "actual_jit_full_turns_observed": len(case_list),
            "actual_jit_full_lanes": [case.get("producer_lane") for case in case_list],
            "maximum_reserved_jit_full_usd": len(case_list) * JIT_FULL_RESERVATION_MICRO_USD / 1_000_000,
            "quality_judgment": "root-owned after trusted receipts and adjudication",
        },
        "cases": case_list,
        "receipt_contract": {
            "producer_attempt_ids_by_case": attempt_ids_by_case,
            "producer_receipt_source": "durable llm_gateway_attempts queried by exact jit_run_id",
            "baseline_replay_blocked_until": "source-owned legacy/nano prompt projection is persisted",
            "attempt_counting": "provider_attempts_exact is the number of distinct producer receipt attempt IDs; retries count",
            "tool_counting": "tool_invocations is the number of durable SQLite tool ledger rows; model rounds are not inferred",
        },
    }


def build_producer_derived_pair_plan(
    fixture: Mapping[str, Any],
    *,
    database_path: Path,
    producer_runs: Sequence[tuple[str, str]],
    owner_id: str,
    projection_dir: Path | None = None,
    allow_legacy_private_metadata_projection: bool = False,
) -> dict[str, Any]:
    """Build a two-case plan from the actual planned and ambient JIT turns.

    ``producer_runs`` is an explicit ``(lane, agent_run_id)`` pair for each
    already-completed app turn.  The plan never replays a static fixture prompt
    as if it were observed.  It records the real prompt/evidence hashes and
    durable attempt IDs, while keeping the comparison blocked until the
    source-owned legacy/nano projections exist.
    """
    _validate_fixture(fixture)
    _require_qa_owner(owner_id)
    if len(producer_runs) != MAX_PRODUCER_RUNS:
        raise EvidenceError("producer-derived qualification requires exactly planned and ambient runs")
    by_lane: dict[str, str] = {}
    for raw_lane, raw_run_id in producer_runs:
        lane = _required_identifier(raw_lane, "producer lane")
        if lane not in PRODUCER_LANES:
            raise EvidenceError("producer lane must be planned or ambient")
        if lane in by_lane:
            raise EvidenceError("producer lanes must be unique")
        run_id = _required_identifier(raw_run_id, "producer agent_run_id")
        by_lane[lane] = run_id
    if set(by_lane) != set(PRODUCER_LANES):
        raise EvidenceError("producer-derived qualification requires one planned and one ambient run")
    if len(set(by_lane.values())) != len(by_lane):
        raise EvidenceError("planned and ambient producer runs must be distinct")

    routes = _fixture_routes(fixture)
    cases: list[Mapping[str, Any]] = []
    materializations: list[Mapping[str, Any]] = []
    for lane in PRODUCER_LANES:
        agent_run_id = by_lane[lane]
        materialization = _producer_run_materialization(
            database_path,
            agent_run_id=agent_run_id,
            owner_id=owner_id,
            projection_dir=projection_dir,
            allow_legacy_private_metadata_projection=allow_legacy_private_metadata_projection,
        )
        # The lane is an explicit operator join key because the current
        # SQLite run schema does not persist a first-class proactivity lane.
        # If a future producer persists one, reject disagreement rather than
        # silently relabeling the turn.
        metadata = materialization["metadata"]
        persisted_lane = next(
            (metadata[key] for key in ("producerLane", "proactivityLane", "lane") if key in metadata),
            None,
        )
        if persisted_lane is not None and persisted_lane != lane:
            raise EvidenceError(f"producer run {agent_run_id} lane does not match {lane}")
        cases.append(
            _producer_case(
                fixture,
                routes=routes,
                case_id=lane,
                lane=lane,
                materialization=materialization,
            )
        )
        materializations.append(materialization)
    result = _producer_plan(
        fixture,
        owner_id=owner_id,
        cases=cases,
        materializations=materializations,
        status=(
            "producer_matched_two_case_source_owned_baselines"
            if all(materialization.get("source_projection") for materialization in materializations)
            else "producer_matched_two_case_jit_only"
        ),
    )
    if result["status"] == "producer_matched_two_case_source_owned_baselines":
        result["comparison_ready"] = False
        result["evidence_scope"] = (
            "actual QA producer snapshots/prompts plus source-owned legacy/nano projections from the same "
            "admitted context/time; no provider calls"
        )
        result["replay_projection"] = {
            "status": "source_owned",
            "same_admitted_snapshot_per_case": True,
            "same_evaluation_time_per_case": True,
            "same_timezone_per_case": True,
            "legacy": {"status": "source_owned", "cases": [case["case_id"] for case in cases]},
            "nano": {"status": "source_owned", "cases": [case["case_id"] for case in cases]},
            "full": {"status": "producer_observed", "cases": [case["case_id"] for case in cases]},
        }
        result["receipt_contract"][
            "baseline_replay_blocked_until"
        ] = "trusted endpoint headers and durable accounting joins; source prompt projection is present"
    return result


def build_producer_derived_plan(
    fixture: Mapping[str, Any],
    *,
    database_path: Path,
    agent_run_id: str,
    owner_id: str,
    case_id: str,
    projection_dir: Path | None = None,
    allow_legacy_private_metadata_projection: bool = False,
) -> dict[str, Any]:
    """Backward-compatible one-run producer plan.

    New qualification runs should use ``build_producer_derived_pair_plan`` so
    planned and ambient turns are both explicit.  This narrow form remains for
    capture tooling and old artifacts; it has the same source-owned projection
    limitation and content-free output.
    """
    _validate_fixture(fixture)
    _require_qa_owner(owner_id)
    case_id = _required_identifier(case_id, "producer case_id")
    materialization = _producer_run_materialization(
        database_path,
        agent_run_id=agent_run_id,
        owner_id=owner_id,
        projection_dir=projection_dir,
        allow_legacy_private_metadata_projection=allow_legacy_private_metadata_projection,
    )
    case = _producer_case(
        fixture,
        routes=_fixture_routes(fixture),
        case_id=case_id,
        lane=None,
        materialization=materialization,
    )
    result = _producer_plan(
        fixture,
        owner_id=owner_id,
        cases=[case],
        materializations=[materialization],
        status=(
            "producer_matched_source_owned_baseline"
            if materialization.get("source_projection")
            else "producer_matched_jit_only"
        ),
    )
    if result["status"] == "producer_matched_source_owned_baseline":
        result["evidence_scope"] = (
            "actual QA producer snapshot/prompt plus source-owned legacy/nano projections from the same "
            "admitted context/time; no provider calls"
        )
        result["replay_projection"] = {
            "status": "source_owned",
            "same_admitted_snapshot_per_case": True,
            "same_evaluation_time_per_case": True,
            "same_timezone_per_case": True,
            "legacy": {"status": "source_owned", "cases": [case_id]},
            "nano": {"status": "source_owned", "cases": [case_id]},
            "full": {"status": "producer_observed", "cases": [case_id]},
        }
        result["receipt_contract"][
            "baseline_replay_blocked_until"
        ] = "trusted endpoint headers and durable accounting joins; source prompt projection is present"
    return result


def export_source_projection_inputs(
    *,
    database_path: Path,
    producer_runs: Sequence[tuple[str, str]],
    owner_id: str,
    output_dir: Path,
    projection_dir: Path | None = None,
    allow_legacy_private_metadata_projection: bool = False,
) -> dict[str, Any]:
    """Write private replay inputs emitted by the source-owned producer.

    The output directory is deliberately separate from the content-free plan:
    legacy/nano endpoint calls need the actual prompt bytes, while receipts and
    operator output must remain hash-only.  This command writes only files under
    the caller-selected directory with owner-only permissions and returns file
    names plus hashes, never prompt text.
    """
    _require_qa_owner(owner_id)
    if len(producer_runs) != MAX_PRODUCER_RUNS:
        raise EvidenceError("source projection export requires exactly planned and ambient runs")
    lanes = {lane: run_id for lane, run_id in producer_runs}
    if set(lanes) != set(PRODUCER_LANES) or len(set(lanes.values())) != len(lanes):
        raise EvidenceError("source projection export requires one distinct planned and ambient run")
    output_dir = output_dir.expanduser()
    _ensure_private_export_directory(output_dir)
    exported: list[dict[str, Any]] = []
    for lane in PRODUCER_LANES:
        materialization = _producer_run_materialization(
            database_path,
            agent_run_id=lanes[lane],
            owner_id=owner_id,
            projection_dir=projection_dir,
            allow_legacy_private_metadata_projection=allow_legacy_private_metadata_projection,
        )
        projection = materialization.get("source_projection")
        if not isinstance(projection, Mapping):
            raise EvidenceError(f"source projection is unavailable for {lane}")
        lane_dir = output_dir / lane
        _ensure_private_export_directory(lane_dir, parent=output_dir)
        files: dict[str, Path] = {}

        def write_private(name: str, data: bytes) -> None:
            path = lane_dir / name
            # Do not replace an earlier capture in place: a stale artifact
            # must be explicitly removed by its owner before retry.
            if path.exists() or path.is_symlink():
                raise EvidenceError(f"refusing non-exclusive replay artifact: {path}")
            _write_private_file(path, data)
            files[name] = path

        legacy = projection["legacy"]
        nano = projection["nano"]
        write_private("legacy.prompt", legacy["prompt"].encode("utf-8"))
        write_private("legacy.uncached_prompt", legacy["uncached_prompt"].encode("utf-8"))
        write_private("nano.prompt", nano["prompt"].encode("utf-8"))
        snapshot_bytes = _json_bytes(materialization["snapshot"])
        write_private("evidence.json", snapshot_bytes)
        exported.append(
            {
                "producer_lane": lane,
                "agent_run_id": lanes[lane],
                "execution_id": materialization["execution_id"],
                "evidence_sha256": materialization["evidence_sha256"],
                "legacy_prompt_sha256": _sha256(legacy["prompt"]),
                "legacy_uncached_prompt_sha256": _sha256(legacy["uncached_prompt"]),
                "nano_prompt_sha256": _sha256(nano["prompt"]),
                "files": {name: str(path) for name, path in files.items()},
            }
        )
    return {
        "schema_version": "omi.jit.cost_evidence.projection_export.v1",
        "status": "exported",
        "content_scope": "private owner-only source projection files; stdout contains hashes and paths only",
        "producer_runs": exported,
    }


def _load_gateway_receipt(
    path: Path, *, execution_id: str, contract_version: str, attempt_ids: list[str]
) -> dict[str, Any]:
    receipt = _load_json(path)
    if receipt.get("schema_version") != "jit-gateway-receipt-v1":
        raise EvidenceError("JIT gateway receipt schema is not jit-gateway-receipt-v1")
    if receipt.get("run_id") != execution_id:
        raise EvidenceError("JIT gateway receipt run_id does not match producer budget.executionID")
    if receipt.get("contract_version") != contract_version:
        raise EvidenceError("JIT gateway receipt contract does not match producer budget")
    attempts = receipt.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        raise EvidenceError("JIT gateway receipt has no provider attempts")
    receipt_attempt_ids = [
        _required_identifier(item.get("attempt_id"), "JIT gateway receipt attempt_id")
        for item in attempts
        if isinstance(item, Mapping)
    ]
    if len(receipt_attempt_ids) != len(attempts) or len(set(receipt_attempt_ids)) != len(receipt_attempt_ids):
        raise EvidenceError("JIT gateway receipt attempt identities are malformed")
    if receipt_attempt_ids != attempt_ids:
        raise EvidenceError("JIT gateway receipt attempts do not match the producer result")
    aggregate = receipt.get("aggregate")
    if not isinstance(aggregate, Mapping) or aggregate.get("attempt_count") != len(attempts):
        raise EvidenceError("JIT gateway receipt aggregate does not cover every provider attempt")
    return _content_free_jit_receipt(receipt)


def capture_agent_run(
    plan: Mapping[str, Any],
    *,
    database_path: Path,
    agent_run_id: str,
    comparison_run_id: str,
    owner_id: str,
    case_id: str,
    gateway_receipt_path: Path,
    allow_legacy_private_metadata_projection: bool = False,
) -> dict[str, Any]:
    """Capture one completed JIT producer run into a content-free envelope."""
    _require_qa_owner(owner_id)
    agent_run_id = _required_identifier(agent_run_id, "agent_run_id")
    comparison_run_id = _required_identifier(comparison_run_id, "comparison_run_id")
    case, expected = _planned_case_route(plan, case_id=case_id, architecture="jit", stage="full")
    materialization = _producer_run_materialization(
        database_path,
        agent_run_id=agent_run_id,
        owner_id=owner_id,
        allow_legacy_private_metadata_projection=allow_legacy_private_metadata_projection,
    )
    run = materialization["run"]
    tool_rows = materialization["tool_rows"]
    contract_version = materialization["contract_version"]
    execution_id = materialization["execution_id"]
    actual_prompt_sha256 = materialization["prompt_sha256"]
    actual_evidence_sha256 = materialization["evidence_sha256"]
    matched_input = case["matched_input"]
    if actual_evidence_sha256 != matched_input["evidence_sha256"]:
        raise EvidenceError("producer evidence hash does not match the source-derived matched input")
    expected_prompt_hashes = expected["prompt_hashes"]
    if actual_prompt_sha256 != expected_prompt_hashes["prompt_sha256"]:
        if plan.get("status") == "producer_matched_jit_only":
            raise EvidenceError("producer-derived plan prompt hash changed after plan capture")
        raise EvidenceError("producer prompt hash does not match the source-derived matched input")
    attempt_ids = materialization["attempt_ids"]
    gateway_receipt = _load_gateway_receipt(
        gateway_receipt_path,
        execution_id=execution_id,
        contract_version=contract_version,
        attempt_ids=attempt_ids,
    )
    sidecar = {
        "run_id": comparison_run_id,
        "gateway_run_id": execution_id,
        "agent_run_id": agent_run_id,
        "agent_request_id": _required_identifier(run.get("request_id"), "agent request_id"),
        "attempt_ids": attempt_ids,
        "case_id": case_id,
        "architecture": "jit",
        "stage": "full",
        "gateway_lane": expected["route"]["gateway_lane"],
        **({"producer_lane": case["producer_lane"]} if "producer_lane" in case else {}),
        "evidence_sha256": actual_evidence_sha256,
        "prompt_sha256": actual_prompt_sha256,
        # The local ledger is one row per tool invocation.  It has no durable
        # model-round boundary, so never label this count as rounds.
        "tool_invocations": len(tool_rows),
    }
    if "system_prompt_sha256" in expected_prompt_hashes:
        sidecar["system_prompt_sha256"] = expected_prompt_hashes["system_prompt_sha256"]
    captured: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "status": "captured",
        "sidecars": [_content_free_sidecar(sidecar)],
        "jit_gateway_receipts": [gateway_receipt],
    }
    source_projection = materialization.get("source_projection")
    if isinstance(source_projection, Mapping):
        nano_billing = source_projection.get("nano_billing")
        if isinstance(nano_billing, Mapping) and nano_billing.get("dispatch") == "observed":
            request_id = _required_identifier(nano_billing.get("request_id"), "actual producer nano request_id")
            nano_expected = case["jit"]["nano"]
            nano_observation: dict[str, Any] = {
                "case_id": case_id,
                "architecture": "jit",
                "stage": "nano",
                "request_id": request_id,
                "run_id": comparison_run_id,
                "evidence_sha256": actual_evidence_sha256,
                "prompt_sha256": nano_expected["prompt_hashes"]["prompt_sha256"],
                "gateway_lane": nano_expected["route"]["gateway_lane"],
                "tool_rounds": 0,
                "receipt_origin": "actual",
            }
            captured["request_observations"] = [nano_observation]
    return captured


def _response_request_id(headers_path: Path) -> str:
    try:
        lines = headers_path.read_text(encoding="latin-1").splitlines()
    except OSError as exc:
        raise EvidenceError(f"cannot read endpoint response headers: {headers_path}") from exc
    values: list[str] = []
    for line in lines:
        if ":" not in line:
            continue
        name, value = line.split(":", 1)
        if name.strip().casefold() == "x-omi-request-id":
            values.append(value.strip())
    if len(values) != 1:
        raise EvidenceError("endpoint response must contain exactly one X-Omi-Request-ID header")
    return _required_identifier(values[0], "X-Omi-Request-ID")


def capture_endpoint_observation(
    plan: Mapping[str, Any],
    *,
    headers_path: Path,
    evidence_path: Path,
    prompt_path: Path,
    comparison_run_id: str,
    owner_id: str,
    case_id: str,
    architecture: str,
    stage: str,
    tool_rounds: int = 0,
    receipt_origin: str = "replay",
) -> dict[str, Any]:
    """Capture a legacy/nano response header plus source-owned input hashes.

    A nano observation is a replay by default.  The actual producer nano can
    opt into ``receipt_origin=actual`` only when the producer-derived plan
    carries its content-free ``nano_billing.request_id``; this prevents a
    manually supplied endpoint request from being presented as the original
    producer operation.
    """
    _require_qa_owner(owner_id)
    comparison_run_id = _required_identifier(comparison_run_id, "comparison_run_id")
    if (architecture, stage) not in {("legacy", "full"), ("jit", "nano")}:
        raise EvidenceError("endpoint capture only supports legacy/full or jit/nano")
    if receipt_origin not in {"replay", "actual"}:
        raise EvidenceError("endpoint receipt_origin must be replay or actual")
    if receipt_origin == "actual" and (architecture, stage) != ("jit", "nano"):
        raise EvidenceError("actual receipt_origin is only valid for the JIT nano route")
    if isinstance(tool_rounds, bool) or not isinstance(tool_rounds, int) or tool_rounds < 0:
        raise EvidenceError("endpoint tool_rounds is malformed")
    case, expected = _planned_case_route(plan, case_id=case_id, architecture=architecture, stage=stage)
    evidence = _load_json(evidence_path)
    actual_evidence_sha256 = _canonical_json_hash(evidence)
    try:
        prompt = prompt_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise EvidenceError(f"cannot read endpoint prompt artifact: {prompt_path}") from exc
    actual_prompt_sha256 = _sha256(prompt)
    if actual_evidence_sha256 != case["matched_input"]["evidence_sha256"]:
        raise EvidenceError("endpoint evidence hash does not match the source-derived matched input")
    expected_hashes = expected["prompt_hashes"]
    if actual_prompt_sha256 != expected_hashes["prompt_sha256"]:
        raise EvidenceError("endpoint prompt hash does not match the source-derived matched input")
    request_id = _response_request_id(headers_path)
    if receipt_origin == "actual":
        actual_nano = case["jit"]["nano"].get("actual_nano_billing")
        if not isinstance(actual_nano, Mapping) or actual_nano.get("dispatch") != "observed":
            raise EvidenceError("actual nano capture requires an observed producer nano billing projection")
        if actual_nano.get("request_id") != request_id:
            raise EvidenceError("actual nano response request_id differs from producer nano billing request_id")
    observation: dict[str, Any] = {
        "case_id": case_id,
        "architecture": architecture,
        "stage": stage,
        "request_id": request_id,
        "run_id": comparison_run_id,
        "evidence_sha256": actual_evidence_sha256,
        "prompt_sha256": actual_prompt_sha256,
        "gateway_lane": expected["route"]["gateway_lane"],
        "tool_rounds": tool_rounds,
        "receipt_origin": receipt_origin,
    }
    for field in ("uncached_prompt_sha256", "system_prompt_sha256"):
        if field in expected_hashes:
            observation[field] = expected_hashes[field]
    return {"schema_version": RECEIPT_SCHEMA_VERSION, "status": "captured", "request_observations": [observation]}


def _require_qa_firestore_environment(environment: Mapping[str, str] | None = None) -> None:
    values = environment or os.environ
    expected = {
        "FIRESTORE_DATABASE_ID": "jit-qa",
        "OMI_JIT_QA_AUTH_ONLY": "true",
        "OMI_ENV_STAGE": "dev",
        "GOOGLE_CLOUD_PROJECT": "based-hardware-dev",
        "OMI_FIRESTORE_DATA_PLANE_PROJECT": "based-hardware-dev",
    }
    for key, expected_value in expected.items():
        if values.get(key, "").strip().casefold() != expected_value.casefold():
            raise EvidenceError(f"Firestore export requires isolated QA environment {key}={expected_value}")


def export_durable_attempts(client: Any, *, request_ids: Sequence[str], owner_id: str) -> dict[str, Any]:
    """Read exact QA Firestore attempts and return only accounting fields."""
    _require_qa_owner(owner_id)
    normalized_ids = [_required_identifier(value, "Firestore request_id") for value in request_ids]
    if not normalized_ids or len(normalized_ids) > MAX_FIRESTORE_REQUEST_IDS:
        raise EvidenceError(f"Firestore export accepts 1-{MAX_FIRESTORE_REQUEST_IDS} request IDs")
    from google.cloud.firestore_v1.base_query import FieldFilter

    rows: list[dict[str, Any]] = []
    seen_attempt_ids: set[str] = set()
    for request_id in normalized_ids:
        try:
            documents = (
                client.collection("llm_gateway_attempts")
                .where(filter=FieldFilter("request_id", "==", request_id))
                .limit(MAX_JIT_GATEWAY_ATTEMPTS + 1)
                .stream()
            )
            matched = list(documents)
        except Exception as exc:
            raise EvidenceError("Firestore attempt export failed in the isolated QA database") from exc
        if not matched:
            raise EvidenceError(f"no durable attempt exists for exact request_id {request_id}")
        if len(matched) > MAX_JIT_GATEWAY_ATTEMPTS:
            raise EvidenceError("durable attempt export exceeds its bounded capture limit")
        for document in matched:
            data = document.to_dict()
            if not isinstance(data, Mapping) or data.get("request_id") != request_id:
                raise EvidenceError("Firestore returned an attempt for a different request_id")
            if data.get("user_uid") != owner_id:
                raise EvidenceError("Firestore attempt owner does not match the fixed isolated QA owner")
            attempt_id = _required_identifier(data.get("attempt_id"), "Firestore attempt_id")
            if attempt_id in seen_attempt_ids:
                raise EvidenceError("Firestore export contains a duplicate attempt_id")
            seen_attempt_ids.add(attempt_id)
            rows.append(_content_free_accounting_receipt(data))
    return {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "status": "captured",
        "llm_gateway_attempts": rows,
    }


def _jit_attempt_from_durable_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """Project one immutable AccountingEvent into the JIT receipt shape."""
    fields = {
        "attempt_id": row.get("attempt_id"),
        "provider": row.get("provider"),
        "configured_model": row.get("configured_model"),
        "actual_model_version": row.get("actual_model_version"),
        "rate_card_id": row.get("rate_card_id"),
        "cost_basis": row.get("cost_basis"),
        "usage_status": row.get("usage_status"),
        "cost_status": row.get("cost_status"),
        "normalized_uncached_input_tokens": row.get("uncached_input_tokens"),
        "cached_input_tokens": row.get("cached_input_tokens"),
        "cache_write_tokens": row.get("cache_write_tokens"),
        "output_tokens": row.get("output_tokens"),
        "reasoning_tokens": row.get("reasoning_tokens"),
        "estimated_cost_micro_usd": row.get("estimated_cost_micro_usd"),
    }
    # Keep absent/unknown values absent or null.  The validator then blocks
    # them; replacing them with zero would turn an unpriced attempt into a
    # false cost saving.
    return {key: value for key, value in fields.items() if value is not None}


def _durable_jit_receipt(
    rows: Sequence[Mapping[str, Any]], *, execution_id: str, contract_version: str
) -> dict[str, Any]:
    if not rows:
        raise EvidenceError(f"no durable JIT attempts exist for exact execution ID {execution_id}")
    ordered = sorted(
        rows,
        key=lambda row: (
            row.get("occurred_at") if isinstance(row.get("occurred_at"), str) else "",
            row.get("retry_ordinal") if isinstance(row.get("retry_ordinal"), int) else 2**31,
            str(row.get("invocation_id", "")),
            str(row.get("attempt_id", "")),
        ),
    )
    attempts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in ordered:
        attempt_id = _required_identifier(row.get("attempt_id"), "durable JIT attempt_id")
        if attempt_id in seen:
            raise EvidenceError("durable JIT ledger contains a duplicate attempt_id")
        seen.add(attempt_id)
        attempts.append(_jit_attempt_from_durable_row(row))
    numeric_fields = (
        "normalized_uncached_input_tokens",
        "cached_input_tokens",
        "cache_write_tokens",
        "output_tokens",
    )
    totals: dict[str, int | None] = {}
    for field in numeric_fields:
        values = [attempt.get(field) for attempt in attempts]
        totals[field] = (
            sum(values)
            if all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in values)
            else None
        )
    # Some providers omit reasoning_tokens.  Carry it whenever the durable
    # accounting event supplies it, but retain an explicit unknown instead of
    # turning an absent field into zero.
    reasoning_values = [attempt.get("reasoning_tokens") for attempt in attempts]
    if any(value is not None for value in reasoning_values):
        totals["reasoning_tokens"] = (
            sum(reasoning_values)
            if all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in reasoning_values)
            else None
        )
    cost_values = [attempt.get("estimated_cost_micro_usd") for attempt in attempts]
    costs_known = all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in cost_values)
    all_estimated = all(
        attempt.get("cost_status") == "estimated" and isinstance(attempt.get("estimated_cost_micro_usd"), int)
        for attempt in attempts
    )
    aggregate = {
        "attempt_count": len(attempts),
        **totals,
        "estimated_cost_micro_usd": sum(cost_values) if costs_known and all_estimated else None,
        "cost_status": "estimated" if costs_known and all_estimated else "unknown",
    }
    return {
        "schema_version": "jit-gateway-receipt-v1",
        "run_id": execution_id,
        "contract_version": contract_version,
        "attempts": attempts,
        "aggregate": aggregate,
    }


def export_durable_jit_receipt(
    client: Any, *, execution_id: str, owner_id: str, contract_version: str = "jit-cloud-qa-v1"
) -> dict[str, Any]:
    """Rebuild the prompt-free JIT receipt from its durable attempt ledger.

    Pi's temporary receipt side channel is removed when the adapter turn ends.
    ``llm_gateway_attempts`` is immutable and keyed by provider attempt, so
    the producer's opaque ``jitBudget.executionID`` is the stable join key.
    """
    _require_qa_owner(owner_id)
    execution_id = _required_identifier(execution_id, "JIT gateway execution ID")
    contract_version = _required_identifier(contract_version, "JIT gateway contract version")
    from google.cloud.firestore_v1.base_query import FieldFilter

    try:
        documents = (
            client.collection("llm_gateway_attempts")
            .where(filter=FieldFilter("jit_run_id", "==", execution_id))
            .limit(MAX_JIT_GATEWAY_ATTEMPTS + 1)
            .stream()
        )
        matched = list(documents)
    except Exception as exc:
        raise EvidenceError("Firestore JIT attempt export failed in the isolated QA database") from exc
    if len(matched) > MAX_JIT_GATEWAY_ATTEMPTS:
        raise EvidenceError("durable JIT attempt export exceeds its bounded capture limit")
    rows: list[Mapping[str, Any]] = []
    for document in matched:
        data = document.to_dict()
        if not isinstance(data, Mapping):
            raise EvidenceError("Firestore returned a malformed JIT accounting event")
        if data.get("jit_run_id") != execution_id:
            raise EvidenceError("Firestore returned an attempt for a different JIT execution ID")
        if data.get("jit_contract_version") != contract_version:
            raise EvidenceError("durable JIT attempt contract does not match the producer budget")
        if data.get("user_uid") != owner_id:
            raise EvidenceError("durable JIT attempt owner does not match the fixed isolated QA owner")
        rows.append(data)
    receipt = _durable_jit_receipt(rows, execution_id=execution_id, contract_version=contract_version)
    return {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "status": "captured",
        "jit_gateway_receipt_source": "durable llm_gateway_attempts by exact jit_run_id",
        "jit_gateway_receipts": [receipt],
    }


def _content_free_observation(item: Mapping[str, Any]) -> dict[str, Any]:
    fields = (
        "case_id",
        "architecture",
        "stage",
        "request_id",
        "run_id",
        "evidence_sha256",
        "prompt_sha256",
        "uncached_prompt_sha256",
        "system_prompt_sha256",
        "gateway_lane",
        "tool_rounds",
        "receipt_origin",
    )
    return {key: item[key] for key in fields if key in item}


def merge_capture_fragment(path: Path, fragment: Mapping[str, Any]) -> dict[str, Any]:
    """Append one sanitized capture fragment to a raw receipt envelope."""
    existing: Mapping[str, Any] = {}
    if path.exists():
        existing = _load_json(path)
    merged: dict[str, Any] = {"schema_version": RECEIPT_SCHEMA_VERSION, "status": "captured"}
    for key in (
        "request_observations",
        "llm_gateway_attempts",
        "sidecars",
        "jit_gateway_receipts",
        "actual_jit_nano_provider_receipts",
    ):
        prior = existing.get(key, [])
        added = fragment.get(key, [])
        if not isinstance(prior, list) or not isinstance(added, list):
            raise EvidenceError(f"capture envelope field {key} must be a list")
        if key == "request_observations":
            values = [_content_free_observation(item) for item in prior + added if isinstance(item, Mapping)]
        elif key == "llm_gateway_attempts":
            values = [_content_free_accounting_receipt(item) for item in prior + added if isinstance(item, Mapping)]
        elif key == "sidecars":
            values = [_content_free_sidecar(item) for item in prior + added if isinstance(item, Mapping)]
        elif key == "actual_jit_nano_provider_receipts":
            values = [_content_free_accounting_receipt(item) for item in prior + added if isinstance(item, Mapping)]
        else:
            values = [_content_free_jit_receipt(item) for item in prior + added if isinstance(item, Mapping)]
        merged[key] = values
    return merged


def _validate_jit_gateway_aggregate(
    gateway_receipt: Mapping[str, Any], attempts: Sequence[Mapping[str, Any]], key: object
) -> list[str]:
    """Check that the JIT wrapper aggregate accounts for every attempt."""
    aggregate = gateway_receipt.get("aggregate")
    if not isinstance(aggregate, Mapping):
        return [f"{key} JIT receipt has no aggregate"]
    errors: list[str] = []
    try:
        if _required_int(aggregate, "attempt_count") != len(attempts):
            errors.append(f"{key} JIT aggregate attempt_count differs from attempts")
        field_totals = {
            "normalized_uncached_input_tokens": sum(
                _required_int(attempt, "normalized_uncached_input_tokens") for attempt in attempts
            ),
            "cached_input_tokens": sum(_required_int(attempt, "cached_input_tokens") for attempt in attempts),
            "cache_write_tokens": sum(_required_int(attempt, "cache_write_tokens") for attempt in attempts),
            "output_tokens": sum(_required_int(attempt, "output_tokens") for attempt in attempts),
            "estimated_cost_micro_usd": sum(_required_int(attempt, "estimated_cost_micro_usd") for attempt in attempts),
        }
        reasoning_values = [attempt.get("reasoning_tokens") for attempt in attempts]
        if any(value is not None for value in reasoning_values):
            if not all(
                isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in reasoning_values
            ):
                errors.append(f"{key} JIT reasoning_tokens is unknown or invalid")
            elif aggregate.get("reasoning_tokens") != sum(reasoning_values):
                errors.append(f"{key} JIT aggregate reasoning_tokens differs from attempts")
        for field, expected in field_totals.items():
            if _required_int(aggregate, field) != expected:
                errors.append(f"{key} JIT aggregate {field} differs from attempts")
        if aggregate.get("cost_status") != "estimated":
            errors.append(f"{key} JIT aggregate cost_status is not estimated")
    except EvidenceError as exc:
        errors.append(str(exc))
    return errors


def join_durable_receipts(plan: Mapping[str, Any], envelope: Mapping[str, Any]) -> dict[str, Any]:
    """Join endpoint request observations to exact durable gateway request IDs.

    The endpoint response exposes the backend-generated ``X-Omi-Request-ID``.
    An operator records that value in ``request_observations`` and supplies a
    prompt-free export of ``llm_gateway_attempts``. This function selects only
    rows whose ``request_id`` exactly matches an observed operation, preserves
    every retry attempt, and emits an envelope accepted by
    ``summarize_receipts``. An ``actual`` JIT nano observation must match the
    source projection's exact producer request ID and is kept in a separate
    receipt list from replay nano. Missing or ambiguous joins raise instead of
    treating a route as free or successful.
    """
    observations = envelope.get("request_observations")
    durable_rows = envelope.get("llm_gateway_attempts")
    if not isinstance(observations, list) or not observations:
        raise EvidenceError("request_observations must be a non-empty list")
    if not isinstance(durable_rows, list):
        raise EvidenceError("llm_gateway_attempts must be a list exported from the durable ledger")
    index = _index_plan(plan)
    by_request: dict[str, list[Mapping[str, Any]]] = {}
    seen_attempt_ids: set[str] = set()
    for row in durable_rows:
        if not isinstance(row, Mapping):
            raise EvidenceError("llm_gateway_attempts contains a malformed row")
        request_id = _required_string(row.get("request_id"), "durable event request_id")
        attempt_id = _required_string(row.get("attempt_id"), "durable event attempt_id")
        if attempt_id in seen_attempt_ids:
            raise EvidenceError(f"durable event attempt_id is duplicated: {attempt_id}")
        seen_attempt_ids.add(attempt_id)
        by_request.setdefault(request_id, []).append(row)

    # A case may carry both the separately replayed nano call and the actual
    # producer nano observation.  Their origin is part of the join identity;
    # without it, the second exact request would be mistaken for a duplicate.
    seen_keys: set[tuple[str, str, str, str]] = set()
    legacy_receipts: list[dict[str, Any]] = []
    jit_nano_receipts: list[dict[str, Any]] = []
    actual_jit_nano_receipts: list[dict[str, Any]] = []
    generated_sidecars: list[dict[str, Any]] = []
    joined_attempt_ids: set[str] = set()
    for observation in observations:
        if not isinstance(observation, Mapping):
            raise EvidenceError("request_observations contains a malformed item")
        case_id = _required_string(observation.get("case_id"), "request observation case_id")
        architecture = _required_string(observation.get("architecture"), f"{case_id} architecture")
        stage = _required_string(observation.get("stage"), f"{case_id} stage")
        receipt_origin = observation.get("receipt_origin", "replay")
        if receipt_origin not in {"replay", "actual"}:
            raise EvidenceError(f"request observation has an invalid receipt_origin: {case_id}")
        if receipt_origin == "actual" and (architecture, stage) != ("jit", "nano"):
            raise EvidenceError(f"actual receipt_origin is only valid for JIT nano: {case_id}")
        key = (case_id, architecture, stage, receipt_origin)
        route_key = (case_id, architecture, stage)
        if route_key not in index:
            raise EvidenceError(f"request observation does not match the plan: {route_key}")
        if key in seen_keys:
            raise EvidenceError(f"duplicate request observation for {key}")
        seen_keys.add(key)
        if (architecture, stage) not in {("legacy", "full"), ("jit", "nano")}:
            raise EvidenceError(f"request observation is not a legacy or nano route: {route_key}")
        request_id = _required_string(observation.get("request_id"), f"{key} exact request_id")
        run_id = _required_string(observation.get("run_id"), f"{key} run_id")
        evidence_sha256 = _required_string(observation.get("evidence_sha256"), f"{key} evidence_sha256")
        prompt_sha256 = _required_string(observation.get("prompt_sha256"), f"{key} prompt_sha256")
        tool_rounds = observation.get("tool_rounds")
        if isinstance(tool_rounds, bool) or not isinstance(tool_rounds, int) or tool_rounds < 0:
            raise EvidenceError(f"{key} tool_rounds is missing or invalid")
        case = next(item for item in plan["cases"] if item["case_id"] == case_id)
        actual_nano = case.get("jit", {}).get("nano", {}).get("actual_nano_billing")
        if receipt_origin == "actual":
            if not isinstance(actual_nano, Mapping) or actual_nano.get("dispatch") != "observed":
                raise EvidenceError(f"{key} has no observed producer nano billing projection")
            if actual_nano.get("request_id") != request_id:
                raise EvidenceError(f"{key} request_id differs from producer nano billing observation")
        elif (
            isinstance(actual_nano, Mapping)
            and actual_nano.get("dispatch") == "observed"
            and actual_nano.get("request_id") == request_id
        ):
            raise EvidenceError(f"{key} exact producer nano request must be marked receipt_origin=actual")
        matched_rows = by_request.get(request_id, [])
        if not matched_rows:
            raise EvidenceError(f"{key} has no durable event for exact request_id")
        content_free_rows = [_content_free_accounting_receipt(row) for row in matched_rows]
        attempt_ids = [_required_string(row.get("attempt_id"), f"{key} attempt_id") for row in matched_rows]
        if joined_attempt_ids.intersection(attempt_ids):
            raise EvidenceError(f"{key} shares an attempt_id with another request observation")
        joined_attempt_ids.update(attempt_ids)
        sidecar = {
            "run_id": run_id,
            "attempt_ids": attempt_ids,
            "request_id": request_id,
            "case_id": case_id,
            "architecture": architecture,
            "stage": stage,
            "receipt_origin": receipt_origin,
            "gateway_lane": observation.get("gateway_lane"),
            "evidence_sha256": evidence_sha256,
            "prompt_sha256": prompt_sha256,
            "tool_rounds": tool_rounds,
        }
        for field in ("uncached_prompt_sha256", "system_prompt_sha256"):
            if field in observation:
                sidecar[field] = observation[field]
        generated_sidecars.append(sidecar)
        if architecture == "legacy":
            legacy_receipts.extend(content_free_rows)
        elif receipt_origin == "actual":
            # Actual producer nano spend is kept separate from the optional
            # replay nano so the same request can never be counted twice.
            actual_jit_nano_receipts.extend(content_free_rows)
        else:
            # The nano endpoint uses the same durable AccountingEvent schema
            # as legacy proactivity.  ``summarize_receipts`` accepts this
            # dedicated list and uses its uncached_input_tokens field.
            jit_nano_receipts.extend(content_free_rows)

    existing_sidecars = envelope.get("sidecars")
    if existing_sidecars is None:
        existing_sidecars = []
    if not isinstance(existing_sidecars, list) or not all(isinstance(item, Mapping) for item in existing_sidecars):
        raise EvidenceError("sidecars must be a list of objects")
    jit_gateway_receipts = envelope.get("jit_gateway_receipts")
    if jit_gateway_receipts is None:
        jit_gateway_receipts = []
    if not isinstance(jit_gateway_receipts, list) or not all(
        isinstance(item, Mapping) for item in jit_gateway_receipts
    ):
        raise EvidenceError("jit_gateway_receipts must be a list of objects")
    joined_sidecars = [_content_free_sidecar(item) for item in existing_sidecars] + generated_sidecars
    return {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "status": "joined",
        "legacy_receipt_source": "llm_gateway_attempts",
        "legacy_provider_receipts": legacy_receipts,
        "jit_nano_provider_receipts": jit_nano_receipts,
        "actual_jit_nano_provider_receipts": actual_jit_nano_receipts,
        "jit_gateway_receipts": [_content_free_jit_receipt(item) for item in jit_gateway_receipts],
        "sidecars": joined_sidecars,
        "join_contract": "exact request_id; every durable attempt retained; unknown blocks",
    }


def _index_plan(plan: Mapping[str, Any]) -> dict[tuple[str, str, str], Mapping[str, Any]]:
    result: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    for case in plan.get("cases", []):
        case_id = case["case_id"]
        result[(case_id, "legacy", "full")] = case["legacy"]
        result[(case_id, "jit", "nano")] = case["jit"]["nano"]
        result[(case_id, "jit", "full")] = case["jit"]["full"]
    return result


def summarize_receipts(plan: Mapping[str, Any], envelope: Mapping[str, Any]) -> dict[str, Any]:
    """Validate real legacy events and JIT gateway receipts joined to sidecars."""
    legacy_receipts = envelope.get("legacy_provider_receipts")
    jit_nano_receipts = envelope.get("jit_nano_provider_receipts")
    jit_receipts = envelope.get("jit_gateway_receipts")
    if not isinstance(legacy_receipts, list) or not all(isinstance(item, Mapping) for item in legacy_receipts):
        legacy_receipts = []
    if not isinstance(jit_nano_receipts, list) or not all(isinstance(item, Mapping) for item in jit_nano_receipts):
        jit_nano_receipts = []
    if not isinstance(jit_receipts, list) or not all(isinstance(item, Mapping) for item in jit_receipts):
        jit_receipts = []
    provider_receipts: list[tuple[str, Mapping[str, Any], Mapping[str, Any] | None]] = [
        ("legacy", receipt, None) for receipt in legacy_receipts
    ]
    # The producer's exact nano request is separately joined below. Keep replay
    # rows in the envelope and in total experiment spend, while the actual list
    # is the sole nano source for the actual JIT architecture-cost field.
    actual_jit_nano_receipts = envelope.get("actual_jit_nano_provider_receipts")
    if not isinstance(actual_jit_nano_receipts, list) or not all(
        isinstance(item, Mapping) for item in actual_jit_nano_receipts
    ):
        actual_jit_nano_receipts = []
    provider_receipts.extend(("jit_nano_actual", receipt, None) for receipt in actual_jit_nano_receipts)
    provider_receipts.extend(("jit_nano", receipt, None) for receipt in jit_nano_receipts)
    for gateway_receipt in jit_receipts:
        attempts = gateway_receipt.get("attempts")
        if isinstance(attempts, list):
            provider_receipts.extend(
                ("jit", attempt, gateway_receipt) for attempt in attempts if isinstance(attempt, Mapping)
            )
    sidecars = envelope.get("sidecars")
    if not isinstance(sidecars, list) or not all(isinstance(item, Mapping) for item in sidecars):
        sidecars = []
    legacy_receipt_source = envelope.get("legacy_receipt_source")
    actual_nano_cases = {
        case["case_id"]
        for case in plan.get("cases", [])
        if isinstance(case, Mapping)
        and isinstance(case.get("jit"), Mapping)
        and isinstance(case["jit"].get("nano"), Mapping)
        and isinstance(case["jit"]["nano"].get("actual_nano_billing"), Mapping)
        and case["jit"]["nano"]["actual_nano_billing"].get("dispatch") == "observed"
    }
    not_dispatched_nano_cases = {
        case["case_id"]
        for case in plan.get("cases", [])
        if isinstance(case, Mapping)
        and isinstance(case.get("jit"), Mapping)
        and isinstance(case["jit"].get("nano"), Mapping)
        and isinstance(case["jit"]["nano"].get("actual_nano_billing"), Mapping)
        and case["jit"]["nano"]["actual_nano_billing"].get("dispatch") == "not_dispatched"
    }
    actual_nano_source = (
        "actual_producer"
        if actual_jit_nano_receipts
        else (
            "replay_endpoint"
            if actual_nano_cases
            else "not_dispatched" if not_dispatched_nano_cases else "replay_endpoint"
        )
    )
    actual_nano_seen_cases: set[str] = set()
    if not provider_receipts:
        return {
            "status": "unknown",
            "blocking_reasons": ["no trusted legacy event or JIT gateway receipt"],
            "jit_nano_receipt_source": actual_nano_source,
            "actual_jit_architecture_cost_micro_usd": None,
            "actual_jit_architecture_cost_status": "unknown",
            "gateway_attempts": None,
            "tool_rounds": None,
            "tool_invocations": None,
            "cache_units": None,
            "cost_micro_usd": None,
        }

    index = _index_plan(plan)
    errors: list[str] = []
    if legacy_receipts and legacy_receipt_source != "llm_gateway_attempts":
        errors.append("legacy receipt source must be durable llm_gateway_attempts")
    run_ids: set[str] = set()
    run_ids_by_case: dict[str, set[str]] = {}
    totals = {
        "gateway_attempts": 0,
        "tool_rounds": 0,
        "tool_invocations": 0,
        "cache_units": 0,
        "cost_micro_usd": 0,
        "actual_jit_architecture_cost_micro_usd": 0,
    }
    tool_rounds_complete = True
    tool_invocations_complete = True
    seen: set[tuple[str, str, str]] = set()
    seen_attempt_ids: set[str] = set()
    sidecar_by_attempt: dict[str, Mapping[str, Any]] = {}
    sidecar_tool_counters: dict[int, dict[str, Any]] = {}
    gateway_attempts_by_receipt: dict[int, list[Mapping[str, Any]]] = {}
    for sidecar in sidecars:
        attempt_ids = sidecar.get("attempt_ids")
        if (
            not isinstance(attempt_ids, list)
            or not attempt_ids
            or not all(isinstance(attempt_id, str) and attempt_id for attempt_id in attempt_ids)
        ):
            errors.append("sidecar has missing or malformed attempt_ids")
            continue
        for attempt_id in attempt_ids:
            if attempt_id in sidecar_by_attempt:
                errors.append("sidecar has duplicate attempt_id")
            sidecar_by_attempt[attempt_id] = sidecar
        counter: dict[str, Any] = {"seen": False, "rounds": None, "invocations": None}
        for field, target in (("tool_rounds", "rounds"), ("tool_invocations", "invocations")):
            if field not in sidecar:
                continue
            try:
                counter[target] = _required_int(sidecar, field)
            except EvidenceError as exc:
                errors.append(str(exc))
        if counter["rounds"] is None and counter["invocations"] is None:
            errors.append("sidecar has no trusted tool-round or tool-invocation count")
        if counter["rounds"] is None:
            tool_rounds_complete = False
        if counter["invocations"] is None:
            tool_invocations_complete = False
        sidecar_tool_counters[id(sidecar)] = counter
    for kind, receipt, gateway_receipt in provider_receipts:
        try:
            attempt_id = receipt.get("attempt_id")
            if not isinstance(attempt_id, str) or not attempt_id:
                raise EvidenceError("provider completion has no attempt_id")
            sidecar = sidecar_by_attempt.get(attempt_id)
            if sidecar is None:
                raise EvidenceError(f"provider completion {attempt_id} has no trusted harness sidecar")
            key = (sidecar["case_id"], sidecar["architecture"], sidecar["stage"])
            expected = index.get(key)
            if expected is None:
                raise EvidenceError(f"receipt does not match the plan: {key}")
            optional_replay_nano = (
                kind != "jit_nano_actual"
                and key[1:] == ("jit", "nano")
                and key[0] in (actual_nano_cases | not_dispatched_nano_cases)
            )
            if kind == "jit_nano_actual":
                if sidecar.get("receipt_origin") != "actual":
                    raise EvidenceError(f"{key} actual nano receipt has no actual producer sidecar")
                actual_nano_seen_cases.add(key[0])
            elif kind == "jit_nano" and sidecar.get("receipt_origin") == "actual":
                raise EvidenceError(f"{key} actual producer nano receipt is in the replay receipt list")
            # The route is covered by the actual producer receipt when an
            # observed nano exists. A replay or a no-dispatch diagnostic must
            # still be priced in total experiment spend, but cannot satisfy
            # actual JIT route coverage.
            if not optional_replay_nano:
                seen.add(key)
            route = expected["route"]
            if sidecar.get("gateway_lane") != route["gateway_lane"]:
                raise EvidenceError(f"{key} gateway_lane differs from source-derived route")
            for field in ("provider", "actual_model_version", "rate_card_id"):
                expected_field = "served_model" if field == "actual_model_version" else field
                if receipt.get(field) != route[expected_field]:
                    raise EvidenceError(f"{key} {field} differs from source-derived route")
            if receipt.get("configured_model") != route["served_model"]:
                raise EvidenceError(f"{key} configured_model differs from source-derived route")
            if kind in {"legacy", "jit_nano", "jit_nano_actual"}:
                if not isinstance(receipt.get("request_id"), str) or not receipt["request_id"]:
                    raise EvidenceError(f"{key} durable receipt has no exact request_id join")
                if receipt.get("api_surface") != "openai_chat_completions":
                    raise EvidenceError(f"{key} durable receipt has no trusted gateway api_surface")
                if not isinstance(receipt.get("invocation_id"), str) or not receipt["invocation_id"]:
                    raise EvidenceError(f"{key} durable receipt has no invocation_id")
            planned_case = next(item for item in plan["cases"] if item["case_id"] == sidecar["case_id"])
            matched = planned_case["matched_input"]
            if sidecar.get("evidence_sha256") != matched["evidence_sha256"]:
                raise EvidenceError(f"{key} evidence hash differs from matched input")
            if "producer_lane" in planned_case and sidecar.get("producer_lane") != planned_case["producer_lane"]:
                raise EvidenceError(f"{key} producer lane differs from source-derived producer run")
            prompt_hashes = expected["prompt_hashes"]
            if sidecar.get("prompt_sha256") != prompt_hashes["prompt_sha256"]:
                raise EvidenceError(f"{key} prompt hash differs from source-derived prompt")
            for field, value in prompt_hashes.items():
                if field != "prompt_sha256" and sidecar.get(field) != value:
                    raise EvidenceError(f"{key} {field} differs from source-derived prompt")
            run_id = sidecar.get("run_id")
            if not isinstance(run_id, str) or not run_id:
                raise EvidenceError(f"{key} has no trusted run_id")
            run_ids.add(run_id)
            run_ids_by_case.setdefault(sidecar["case_id"], set()).add(run_id)
            if receipt.get("cost_status") != "estimated":
                raise EvidenceError(f"{key} cost_status is not a trusted estimated receipt")
            if receipt.get("usage_status") != "confirmed":
                raise EvidenceError(f"{key} usage_status is not confirmed")
            if kind in {"jit", "jit_nano", "jit_nano_actual"}:
                normalized_input_key = "normalized_uncached_input_tokens"
                if normalized_input_key not in receipt and kind in {"jit_nano", "jit_nano_actual"}:
                    normalized_input_key = "uncached_input_tokens"
            else:
                normalized_input_key = "uncached_input_tokens"
            if attempt_id in seen_attempt_ids:
                raise EvidenceError(f"duplicate provider attempt_id {attempt_id}")
            seen_attempt_ids.add(attempt_id)
            totals["gateway_attempts"] += 1
            tool_state = sidecar_tool_counters.get(id(sidecar))
            if tool_state is None:
                raise EvidenceError(f"{key} has no trusted tool counter")
            if not tool_state["seen"]:
                if tool_state["rounds"] is not None:
                    totals["tool_rounds"] += tool_state["rounds"]
                if tool_state["invocations"] is not None:
                    totals["tool_invocations"] += tool_state["invocations"]
                tool_state["seen"] = True
            uncached = _required_int(receipt, normalized_input_key)
            cached = _required_int(receipt, "cached_input_tokens")
            cache_write = _required_int(receipt, "cache_write_tokens")
            _required_int(receipt, "output_tokens")
            totals["cache_units"] += cached + cache_write
            cost_micro_usd = _required_int(receipt, "estimated_cost_micro_usd")
            totals["cost_micro_usd"] += cost_micro_usd
            if kind == "jit_nano_actual" or (kind == "jit" and key[1:] == ("jit", "full")):
                totals["actual_jit_architecture_cost_micro_usd"] += cost_micro_usd
            if kind == "jit":
                if (
                    not isinstance(gateway_receipt, Mapping)
                    or gateway_receipt.get("schema_version") != "jit-gateway-receipt-v1"
                ):
                    raise EvidenceError(f"{key} is missing jit-gateway-receipt-v1")
                gateway_attempts_by_receipt.setdefault(id(gateway_receipt), []).append(receipt)
                gateway_run_id = sidecar.get("gateway_run_id") or sidecar.get("run_id")
                if gateway_receipt.get("run_id") != gateway_run_id:
                    raise EvidenceError(f"{key} gateway receipt run_id differs from sidecar")
                gateway_attempts = gateway_receipt.get("attempts")
                matching_gateway_attempt = (
                    next(
                        (
                            item
                            for item in gateway_attempts
                            if isinstance(item, Mapping) and item.get("attempt_id") == attempt_id
                        ),
                        None,
                    )
                    if isinstance(gateway_attempts, list)
                    else None
                )
                if not isinstance(matching_gateway_attempt, Mapping):
                    raise EvidenceError(f"{key} gateway receipt attempt identity is malformed")
                if receipt.get("provider") != matching_gateway_attempt.get("provider"):
                    raise EvidenceError(f"{key} gateway receipt attempt identity is malformed")
            _ = uncached
        except (KeyError, EvidenceError) as exc:
            errors.append(str(exc))

    for case_id, case_run_ids in sorted(run_ids_by_case.items()):
        if len(case_run_ids) > 1:
            errors.append(f"case {case_id} spans multiple run_ids")
    for gateway_receipt_id, attempts in gateway_attempts_by_receipt.items():
        gateway_receipt = next(
            receipt
            for kind, _attempt, receipt in provider_receipts
            if kind == "jit" and id(receipt) == gateway_receipt_id
        )
        errors.extend(_validate_jit_gateway_aggregate(gateway_receipt, attempts, "JIT gateway receipt"))
    expected_keys = set(index) - {(case_id, "jit", "nano") for case_id in not_dispatched_nano_cases}
    missing_keys = expected_keys - seen
    if missing_keys:
        errors.append(
            "receipt coverage is incomplete; missing "
            + ", ".join(f"{case}/{architecture}/{stage}" for case, architecture, stage in sorted(missing_keys))
        )
    for case_id in sorted(actual_nano_cases - actual_nano_seen_cases):
        errors.append(
            f"{case_id}/jit/nano actual producer nano accounting is missing; "
            "replay nano cannot stand in for actual JIT spend"
        )
    for sidecar_state in sidecar_tool_counters.values():
        if not sidecar_state["seen"]:
            errors.append("sidecar has no joined provider completion")
    if totals["cost_micro_usd"] > BUDGET_CAP_MICRO_USD:
        errors.append("trusted receipt cost exceeds the 5 USD cap")
    return {
        "status": "blocked" if errors else "known",
        "blocking_reasons": errors,
        "jit_nano_receipt_source": actual_nano_source,
        "actual_jit_architecture_cost_status": "blocked" if errors else "known",
        **totals,
        # The producer's SQLite ledger has no model-round boundary. Keep the
        # distinction visible and return unknown when any joined sidecar lacks
        # a given counter instead of treating absence as zero.
        "tool_rounds": totals["tool_rounds"] if tool_rounds_complete else None,
        "tool_invocations": totals["tool_invocations"] if tool_invocations_complete else None,
        # One operation/full turn can contain multiple provider attempts;
        # `gateway_attempts` above is the cost count.  Keep this distinct.
        "operations": len(seen),
        "run_id": next(iter(run_ids)) if len(run_ids) == 1 else None,
        "run_ids": {
            case_id: next(iter(case_run_ids))
            for case_id, case_run_ids in sorted(run_ids_by_case.items())
            if len(case_run_ids) == 1
        },
    }


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--case-id", action="append", dest="case_ids")
    parser.add_argument("--plan", action="store_true", help="emit a no-call matched-input plan")
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="measure source-derived request envelopes without making provider calls",
    )
    parser.add_argument(
        "--tool-manifest",
        type=Path,
        help="JSON source MCP manifest (required to complete the full-agent preflight)",
    )
    parser.add_argument(
        "--kernel-system-prompt",
        type=Path,
        help="UTF-8 kernel policy emitted by the same built agent runtime",
    )
    parser.add_argument("--validate-receipts", type=Path, help="validate a JSON receipt envelope against the plan")
    parser.add_argument(
        "--join-receipts",
        type=Path,
        help="join content-free request observations to exact durable llm_gateway_attempts rows",
    )
    parser.add_argument(
        "--capture-agent-run",
        action="store_true",
        help="capture one completed isolated-QA agent SQLite run and its JIT gateway receipt",
    )
    parser.add_argument(
        "--producer-derived-plan",
        action="store_true",
        help="derive a matched JIT plan from completed isolated-QA producer run(s)",
    )
    parser.add_argument(
        "--export-source-projections",
        action="store_true",
        help="export source-owned legacy/nano prompt bytes to a private QA replay directory",
    )
    parser.add_argument(
        "--producer-run",
        action="append",
        dest="producer_runs",
        metavar="LANE=AGENT_RUN_ID",
        help="producer-derived pair member; repeat exactly once for planned and once for ambient",
    )
    parser.add_argument(
        "--capture-endpoint",
        action="store_true",
        help="capture one legacy or nano endpoint response header and source-owned input hashes",
    )
    parser.add_argument(
        "--export-attempts",
        action="store_true",
        help="read exact request IDs from the isolated QA Firestore accounting ledger",
    )
    parser.add_argument(
        "--export-jit-receipt",
        action="store_true",
        help="rebuild jit-gateway-receipt-v1 from durable JIT attempt rows",
    )
    parser.add_argument("--agent-db", type=Path, help="isolated QA omi-agentd.sqlite3 path")
    parser.add_argument(
        "--projection-dir",
        type=Path,
        help="private source projection directory when projections are exported separately from agent metadata",
    )
    parser.add_argument(
        "--allow-legacy-private-metadata-projection",
        action="store_true",
        help="read the pre-migration metadata projection only from owner-only historical QA state",
    )
    parser.add_argument(
        "--projection-output-dir",
        type=Path,
        help="private output directory for --export-source-projections",
    )
    parser.add_argument("--agent-run-id", help="producer agent run ID")
    parser.add_argument("--execution-id", help="opaque JIT gateway budget execution ID")
    parser.add_argument("--comparison-run-id", help="harness comparison run ID")
    parser.add_argument("--gateway-receipt", type=Path, help="content-free jit-gateway-receipt-v1 JSON")
    parser.add_argument("--headers-file", type=Path, help="raw endpoint response headers from curl -D")
    parser.add_argument("--evidence-file", type=Path, help="private canonical JSON evidence artifact")
    parser.add_argument("--prompt-file", type=Path, help="private UTF-8 source prompt artifact")
    parser.add_argument("--owner-id", default=QA_OWNER_UID, help="must be the fixed isolated QA owner")
    parser.add_argument("--architecture", choices=("legacy", "jit"), help="endpoint architecture")
    parser.add_argument("--stage", choices=("full", "nano"), help="endpoint stage")
    parser.add_argument(
        "--receipt-origin",
        choices=("replay", "actual"),
        default="replay",
        help="mark a JIT nano endpoint observation as replay or the source producer operation",
    )
    parser.add_argument("--request-id", action="append", help="exact Firestore request ID (repeatable)")
    parser.add_argument("--output", type=Path, help="append the sanitized fragment to this raw envelope")
    parser.add_argument("--plan-file", type=Path, help="plan JSON to use with --validate-receipts")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    try:
        fixture = _load_json(args.fixture)
        case_ids = tuple(args.case_ids or DEFAULT_CASE_IDS)
        if args.export_source_projections:
            if args.agent_db is None or args.projection_output_dir is None:
                raise EvidenceError("--export-source-projections requires --agent-db and --projection-output-dir")
            if not args.producer_runs:
                raise EvidenceError("--export-source-projections requires two --producer-run values")
            if args.agent_run_id or args.case_ids:
                raise EvidenceError("--export-source-projections cannot be combined with --agent-run-id or --case-id")
            producer_runs: list[tuple[str, str]] = []
            for raw_spec in args.producer_runs:
                if raw_spec.count("=") != 1:
                    raise EvidenceError("--producer-run must use LANE=AGENT_RUN_ID")
                lane, run_id = raw_spec.split("=", 1)
                producer_runs.append((lane, run_id))
            result = export_source_projection_inputs(
                database_path=args.agent_db,
                producer_runs=producer_runs,
                owner_id=args.owner_id,
                output_dir=args.projection_output_dir,
                projection_dir=args.projection_dir,
                allow_legacy_private_metadata_projection=args.allow_legacy_private_metadata_projection,
            )
        elif args.producer_derived_plan:
            if args.producer_runs:
                if args.agent_db is None:
                    raise EvidenceError("--producer-derived-plan with --producer-run requires --agent-db")
                if args.agent_run_id or args.case_ids:
                    raise EvidenceError("--producer-run cannot be combined with --agent-run-id or --case-id")
                producer_runs: list[tuple[str, str]] = []
                for raw_spec in args.producer_runs:
                    if raw_spec.count("=") != 1:
                        raise EvidenceError("--producer-run must use LANE=AGENT_RUN_ID")
                    lane, run_id = raw_spec.split("=", 1)
                    producer_runs.append((lane, run_id))
                result = build_producer_derived_pair_plan(
                    fixture,
                    database_path=args.agent_db,
                    producer_runs=producer_runs,
                    owner_id=args.owner_id,
                    projection_dir=args.projection_dir,
                    allow_legacy_private_metadata_projection=args.allow_legacy_private_metadata_projection,
                )
            else:
                required = {
                    "--agent-db": args.agent_db,
                    "--agent-run-id": args.agent_run_id,
                    "--case-id": args.case_ids[0] if args.case_ids and len(args.case_ids) == 1 else None,
                }
                missing = [key for key, value in required.items() if value is None]
                if missing:
                    raise EvidenceError("--producer-derived-plan requires " + ", ".join(missing))
                result = build_producer_derived_plan(
                    fixture,
                    database_path=args.agent_db,
                    agent_run_id=args.agent_run_id,
                    owner_id=args.owner_id,
                    case_id=args.case_ids[0],
                    projection_dir=args.projection_dir,
                    allow_legacy_private_metadata_projection=args.allow_legacy_private_metadata_projection,
                )
        elif args.preflight:
            tool_manifest = None
            tool_manifest_metadata = None
            if args.tool_manifest:
                tool_manifest, tool_manifest_metadata = _load_tool_manifest(args.tool_manifest)
            kernel_system_prompt = None
            if args.kernel_system_prompt:
                try:
                    kernel_system_prompt = args.kernel_system_prompt.read_text(encoding="utf-8")
                except OSError as exc:
                    raise EvidenceError(f"cannot read kernel system prompt {args.kernel_system_prompt}: {exc}") from exc
            result = preflight_payloads(
                fixture,
                case_ids,
                tool_manifest=tool_manifest,
                tool_manifest_metadata=tool_manifest_metadata,
                kernel_system_prompt=kernel_system_prompt,
            )
        elif args.join_receipts:
            plan = _load_json(args.plan_file) if args.plan_file else build_plan(fixture, case_ids)
            raw_envelope = _load_json(args.join_receipts)
            result = join_durable_receipts(plan, raw_envelope)
        elif args.capture_agent_run:
            required = {
                "--agent-db": args.agent_db,
                "--agent-run-id": args.agent_run_id,
                "--comparison-run-id": args.comparison_run_id,
                "--case-id": case_ids[0] if args.case_ids and len(case_ids) == 1 else None,
                "--gateway-receipt": args.gateway_receipt,
            }
            missing = [key for key, value in required.items() if value is None]
            if missing:
                raise EvidenceError("--capture-agent-run requires " + ", ".join(missing) + " and one --case-id")
            plan = _load_json(args.plan_file) if args.plan_file else build_plan(fixture, case_ids)
            result = capture_agent_run(
                plan,
                database_path=args.agent_db,
                agent_run_id=args.agent_run_id,
                comparison_run_id=args.comparison_run_id,
                owner_id=args.owner_id,
                case_id=case_ids[0],
                gateway_receipt_path=args.gateway_receipt,
                allow_legacy_private_metadata_projection=args.allow_legacy_private_metadata_projection,
            )
        elif args.capture_endpoint:
            required = {
                "--headers-file": args.headers_file,
                "--evidence-file": args.evidence_file,
                "--prompt-file": args.prompt_file,
                "--comparison-run-id": args.comparison_run_id,
                "--case-id": case_ids[0] if args.case_ids and len(case_ids) == 1 else None,
                "--architecture": args.architecture,
                "--stage": args.stage,
            }
            missing = [key for key, value in required.items() if value is None]
            if missing:
                raise EvidenceError("--capture-endpoint requires " + ", ".join(missing) + " and one --case-id")
            plan = _load_json(args.plan_file) if args.plan_file else build_plan(fixture, case_ids)
            result = capture_endpoint_observation(
                plan,
                headers_path=args.headers_file,
                evidence_path=args.evidence_file,
                prompt_path=args.prompt_file,
                comparison_run_id=args.comparison_run_id,
                owner_id=args.owner_id,
                case_id=case_ids[0],
                architecture=args.architecture,
                stage=args.stage,
                receipt_origin=args.receipt_origin,
            )
        elif args.export_attempts:
            _require_qa_firestore_environment()
            if not args.request_id:
                raise EvidenceError("--export-attempts requires at least one --request-id")
            from database._client import get_firestore_client

            result = export_durable_attempts(
                get_firestore_client(), request_ids=args.request_id, owner_id=args.owner_id
            )
        elif args.export_jit_receipt:
            _require_qa_firestore_environment()
            if not args.execution_id:
                raise EvidenceError("--export-jit-receipt requires --execution-id")
            from database._client import get_firestore_client

            result = export_durable_jit_receipt(
                get_firestore_client(), execution_id=args.execution_id, owner_id=args.owner_id
            )
        elif args.validate_receipts:
            plan = _load_json(args.plan_file) if args.plan_file else build_plan(fixture, case_ids)
            envelope = _load_json(args.validate_receipts)
            result = summarize_receipts(plan, envelope)
        else:
            result = build_plan(fixture, case_ids)
        if args.output and result.get("status") == "captured":
            result = merge_capture_fragment(args.output, result)
            _ensure_private_export_directory(args.output.parent)
            _write_private_file(
                args.output,
                (json.dumps(result, indent=2, sort_keys=True) + "\n").encode("utf-8"),
                exclusive=False,
            )
        print(json.dumps(result, indent=2, sort_keys=True))
        return (
            0
            if result.get("status")
            in {
                "matched_input_plan",
                "producer_matched_jit_only",
                "producer_matched_two_case_jit_only",
                "producer_matched_source_owned_baseline",
                "producer_matched_two_case_source_owned_baselines",
                "exported",
                "joined",
                "known",
                "ready_for_runtime",
                "captured",
            }
            else 2
        )
    except EvidenceError as exc:
        print(json.dumps({"status": "blocked", "blocking_reasons": [str(exc)]}, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

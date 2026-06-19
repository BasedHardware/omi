import json
import logging
import re
from enum import Enum
from typing import Any, Dict, List, Optional

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field, ValidationError

from models.v17_memory_contracts import (
    DurableMemoryPatch,
    DurablePatchDecision,
    LifecycleState,
    deterministic_contract_id,
)

try:
    from .clients import get_llm

    _CLIENT_IMPORT_ERROR = None
except Exception as exc:
    # Benchmark/product-module tests may run without Firestore ADC or optional provider deps.
    # Keep the L2 prompt/parser/validation importable so callers can inject an equivalent llm.
    get_llm = None
    _CLIENT_IMPORT_ERROR = exc

logger = logging.getLogger(__name__)

_QUOTE_WRAPPER_RE = re.compile(r"^\s*User\s+(said|mentioned|stated|talked about|noted)\s+['\"]", re.IGNORECASE)


class DurableMemoryPatches(BaseModel):
    patches: List[DurableMemoryPatch] = Field(default_factory=list)


class SynthesisStatus(str, Enum):
    success = "success"
    partial = "partial"
    retryable_failure = "retryable_failure"
    permanent_failure = "permanent_failure"


class CandidateOutcomeStatus(str, Enum):
    proposed = "proposed"
    archive = "archive"
    review = "review"
    reject = "reject"
    skip = "skip"
    invalid = "invalid"


class CandidateOutcome(BaseModel):
    index: int
    status: CandidateOutcomeStatus
    reason_code: str
    patch_id: Optional[str] = None
    evidence_ids: List[str] = Field(default_factory=list)


class DurableMemorySynthesisResult(BaseModel):
    status: SynthesisStatus
    patches: List[DurableMemoryPatch] = Field(default_factory=list)
    outcomes: List[CandidateOutcome] = Field(default_factory=list)
    error_code: Optional[str] = None
    cursor_may_advance: bool = False


durable_memory_patch_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """
You are Omi Layer 2 durable memory synthesis.

Input contains one L2 evidence packet, automatically retrieved existing memories, and bounded replayed custom-search context. Emit durable_memory_patch.v1 objects only.

Choose one of: add, add_evidence, update, merge, keep_both, skip_duplicate, context_only, reject, review.

Rules:
- Use retrieved/custom-search memory context before choosing add vs add_evidence/update/merge/skip_duplicate.
- target_memory_id is mandatory for merge, update, add_evidence, and skip_duplicate.
- Active or review outputs require exact evidence_ids and/or evidence_refs with direct quotes.
- Reject quote-wrapper cards like "User said/mentioned/stated ..."; rewrite into a durable abstraction or reject/review.
- Reject raw fragments, unsupported claims, wrong-subject claims, and secrets.
- Custom search results are context only; they are not primary evidence for new claims unless linked to durable evidence.
- Preserve observed_head_commit_id exactly.
- Preserve attribution fields on every patch: confidence, relationship_to_user, subject_entity_id, subject_label, and aboutness.

PROMOTION RUBRIC:
- Promote to active when a Future agent/user would benefit from remembering this, it is stable or meaningfully recurring, it is about the primary user, user-owned work, a close relationship, or an entity the user cares about, and it has direct source evidence.
- Use review when attribution, durability, or sensitivity is uncertain but the packet may still be useful.
- Use context_only when the source may help future search/reasoning but should not become durable profile memory.
- Use reject for unsupported, transient, generic, wrong-subject, media/story narration, or conversational activity facts.
- Do not rewrite unidentified non-primary speaker facts as user facts; set relationship_to_user=other_speaker or unclear and choose review/context_only/reject unless the user tie is explicit.

DRIFT GUARD: This production prompt and durable_memory_patch.v1 schema are the source of truth for benchmark L2 decisions. Benchmark runners may package evidence and export reports, but must call this product synthesizer for L2 memory decisions.

Return JSON matching:
{format_instructions}
""".strip(),
        ),
        (
            "human",
            """
Observed head commit id: {observed_head_commit_id}

L2 evidence packet:
{packet_json}

Custom search replay artifact:
{custom_search_json}
""".strip(),
        ),
    ]
)


def _content_from_response(response) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, list):
        return "\n".join(str(part) for part in content)
    return str(content)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _is_quote_wrapper(memory_text: Optional[str]) -> bool:
    if not memory_text:
        return False
    return bool(_QUOTE_WRAPPER_RE.match(memory_text))


def _logical_patch_payload(patch: DurableMemoryPatch, packet: Dict[str, Any]) -> Dict[str, Any]:
    """Server-owned logical operation fingerprint.

    The LLM is not trusted to choose control identifiers. The fingerprint is stable across
    observed-head changes and output order, but still includes the semantic operation body.
    """
    return {
        "packet_id": patch.packet_id or packet.get("packet_id"),
        "decision": patch.decision.value,
        "target_memory_id": patch.target_memory_id,
        "memory_text": patch.memory_text,
        "evidence_ids": sorted(patch.evidence_ids or []),
        "predicate": patch.predicate,
        "arguments": patch.arguments,
        "relationship_to_user": patch.relationship_to_user,
        "subject_entity_id": patch.subject_entity_id,
        "aboutness": patch.aboutness,
    }


def _with_server_control_ids(
    patch: DurableMemoryPatch, packet: Dict[str, Any], observed_head_commit_id: Optional[str]
) -> DurableMemoryPatch:
    payload = _logical_patch_payload(patch, packet)
    idempotency_key = deterministic_contract_id("v17-durable-patch-idempotency", payload)
    patch_id = deterministic_contract_id(
        "v17-durable-patch",
        {**payload, "observed_head_commit_id": observed_head_commit_id or "unknown"},
    )
    return patch.model_copy(
        update={
            "patch_id": patch_id,
            "idempotency_key": idempotency_key,
            "observed_head_commit_id": observed_head_commit_id,
            "packet_id": patch.packet_id or packet.get("packet_id"),
            "run_id": patch.run_id or packet.get("run_id") or "v17_l2_patch_synthesizer",
        }
    )


def _with_deterministic_patch_ids(
    patches: List[DurableMemoryPatch], packet: Dict[str, Any], observed_head_commit_id: Optional[str]
) -> List[DurableMemoryPatch]:
    return [_with_server_control_ids(patch, packet, observed_head_commit_id) for patch in patches]


def _valid_non_quote_wrapper_patches(patches: List[DurableMemoryPatch]) -> List[DurableMemoryPatch]:
    return [patch for patch in patches if not _is_quote_wrapper(patch.memory_text)]


def _with_production_safety_guards(patches: List[DurableMemoryPatch]) -> List[DurableMemoryPatch]:
    """Apply deterministic active-memory guardrails after LLM synthesis.

    L1 remains the broad searchable archive. L2 active memory should not promote
    third-party/encountered facts or uncertain subject attribution as stable user
    profile memory just because the model emitted an active patch.
    """
    guarded: List[DurableMemoryPatch] = []
    for patch in patches:
        if patch.result_status not in {LifecycleState.active, LifecycleState.review}:
            guarded.append(patch)
            continue
        if patch.aboutness == "third_party" or patch.relationship_to_user in {"encountered", "other_speaker"}:
            guarded.append(
                patch.model_copy(
                    update={
                        "decision": DurablePatchDecision.context_only,
                        "result_status": LifecycleState.context_only,
                        "memory_text": None,
                        "rationale": (patch.rationale or "")
                        + " Deterministic guard: third-party/encountered facts stay in L1/context, not active durable memory.",
                    }
                )
            )
            continue
        if patch.result_status == LifecycleState.active and (
            patch.aboutness == "unclear" or patch.relationship_to_user == "unclear"
        ):
            guarded.append(
                patch.model_copy(
                    update={
                        "decision": DurablePatchDecision.review,
                        "result_status": LifecycleState.review,
                        "rationale": (patch.rationale or "")
                        + " Deterministic guard: unclear attribution routes to review.",
                    }
                )
            )
            continue
        guarded.append(patch)
    return guarded


def _candidate_outcome_for_patch(index: int, patch: DurableMemoryPatch) -> CandidateOutcome:
    if patch.decision == DurablePatchDecision.reject or patch.result_status == LifecycleState.rejected:
        status = CandidateOutcomeStatus.reject
    elif patch.decision == DurablePatchDecision.context_only or patch.result_status == LifecycleState.context_only:
        status = CandidateOutcomeStatus.archive
    elif patch.decision == DurablePatchDecision.review or patch.result_status == LifecycleState.review:
        status = CandidateOutcomeStatus.review
    elif patch.decision == DurablePatchDecision.skip_duplicate:
        status = CandidateOutcomeStatus.skip
    else:
        status = CandidateOutcomeStatus.proposed
    return CandidateOutcome(
        index=index,
        status=status,
        reason_code=patch.decision.value,
        patch_id=patch.patch_id,
        evidence_ids=patch.evidence_ids,
    )


def _packet_evidence_ids(packet: Dict[str, Any]) -> set[str]:
    ids = set(packet.get("evidence_ids") or [])
    for source_ref in packet.get("source_refs") or []:
        evidence_id = source_ref.get("evidence_id") if isinstance(source_ref, dict) else None
        if evidence_id:
            ids.add(evidence_id)
    for observation in packet.get("observations") or []:
        if not isinstance(observation, dict):
            continue
        ids.update(observation.get("evidence_ids") or [])
        for source_ref in observation.get("source_refs") or []:
            evidence_id = source_ref.get("evidence_id") if isinstance(source_ref, dict) else None
            if evidence_id:
                ids.add(evidence_id)
    return ids


def _raw_payload_from_response_text(text: str) -> Dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE).strip()
        stripped = re.sub(r"\s*```$", "", stripped).strip()
    payload = json.loads(stripped)
    if not isinstance(payload, dict):
        raise ValueError("synthesis payload must be a JSON object")
    return payload


def synthesize_durable_memory_patch_result(
    *,
    packet: Dict[str, Any],
    custom_search_artifact: Dict[str, Any],
    observed_head_commit_id: Optional[str],
    llm=None,
) -> DurableMemorySynthesisResult:
    parser = PydanticOutputParser(pydantic_object=DurableMemoryPatches)
    messages = durable_memory_patch_prompt.format_messages(
        observed_head_commit_id=observed_head_commit_id or "unknown",
        packet_json=_canonical_json(packet),
        custom_search_json=_canonical_json(custom_search_artifact),
        format_instructions=parser.get_format_instructions(),
    )
    if llm is not None:
        model = llm
    elif get_llm is not None:
        model = get_llm("memory_l2")
    else:
        logger.error("Error synthesizing V17 durable patches: missing_llm_client")
        return DurableMemorySynthesisResult(
            status=SynthesisStatus.retryable_failure,
            error_code="missing_llm_client",
            cursor_may_advance=False,
        )

    try:
        response = model.invoke(messages)
    except Exception as exc:
        logger.error("Error invoking V17 durable patch synthesizer: %s", type(exc).__name__)
        return DurableMemorySynthesisResult(
            status=SynthesisStatus.retryable_failure,
            error_code="provider_error",
            cursor_may_advance=False,
        )

    try:
        raw_payload = _raw_payload_from_response_text(_content_from_response(response))
    except Exception as exc:
        logger.error("Error parsing V17 durable patch payload: %s", type(exc).__name__)
        return DurableMemorySynthesisResult(
            status=SynthesisStatus.permanent_failure,
            error_code="parse_error",
            cursor_may_advance=False,
        )

    allowed_evidence = _packet_evidence_ids(packet)
    raw_patches = raw_payload.get("patches", [])
    if not isinstance(raw_patches, list):
        return DurableMemorySynthesisResult(
            status=SynthesisStatus.permanent_failure,
            error_code="patches_not_list",
            cursor_may_advance=False,
        )

    patches: List[DurableMemoryPatch] = []
    outcomes: List[CandidateOutcome] = []
    for index, raw_patch in enumerate(raw_patches):
        if not isinstance(raw_patch, dict):
            outcomes.append(
                CandidateOutcome(index=index, status=CandidateOutcomeStatus.invalid, reason_code="not_object")
            )
            continue
        if raw_patch.get("patch_id") or raw_patch.get("idempotency_key"):
            outcomes.append(
                CandidateOutcome(
                    index=index, status=CandidateOutcomeStatus.invalid, reason_code="untrusted_control_field"
                )
            )
            continue
        candidate_payload = dict(raw_patch)
        candidate_payload["patch_id"] = "server_pending"
        candidate_payload["idempotency_key"] = "server_pending"
        candidate_payload["packet_id"] = candidate_payload.get("packet_id") or packet.get("packet_id")
        candidate_payload["run_id"] = (
            candidate_payload.get("run_id") or packet.get("run_id") or "v17_l2_patch_synthesizer"
        )
        candidate_payload["observed_head_commit_id"] = observed_head_commit_id
        try:
            patch = DurableMemoryPatch(**candidate_payload)
        except ValidationError:
            outcomes.append(
                CandidateOutcome(index=index, status=CandidateOutcomeStatus.invalid, reason_code="validation_error")
            )
            continue
        evidence_ids = set(patch.evidence_ids or [])
        if evidence_ids and allowed_evidence and not evidence_ids.issubset(allowed_evidence):
            outcomes.append(
                CandidateOutcome(
                    index=index,
                    status=CandidateOutcomeStatus.invalid,
                    reason_code="evidence_not_in_packet",
                    evidence_ids=patch.evidence_ids,
                )
            )
            continue
        patch = _with_server_control_ids(patch, packet, observed_head_commit_id)
        patch = _with_production_safety_guards([patch])[0]
        if _is_quote_wrapper(patch.memory_text):
            outcomes.append(
                CandidateOutcome(
                    index=index,
                    status=CandidateOutcomeStatus.reject,
                    reason_code="quote_wrapper_quality_guard",
                    patch_id=patch.patch_id,
                    evidence_ids=patch.evidence_ids,
                )
            )
            continue
        patches.append(patch)
        outcomes.append(_candidate_outcome_for_patch(index, patch))

    invalid_count = sum(1 for outcome in outcomes if outcome.status == CandidateOutcomeStatus.invalid)
    status = SynthesisStatus.partial if patches and invalid_count else SynthesisStatus.success
    return DurableMemorySynthesisResult(status=status, patches=patches, outcomes=outcomes, cursor_may_advance=True)


def synthesize_durable_memory_patches(
    *,
    packet: Dict[str, Any],
    custom_search_artifact: Dict[str, Any],
    observed_head_commit_id: Optional[str],
    llm=None,
) -> List[DurableMemoryPatch]:
    result = synthesize_durable_memory_patch_result(
        packet=packet,
        custom_search_artifact=custom_search_artifact,
        observed_head_commit_id=observed_head_commit_id,
        llm=llm,
    )
    if result.status in {SynthesisStatus.retryable_failure, SynthesisStatus.permanent_failure}:
        logger.error("Error synthesizing V17 durable patches: %s", result.error_code)
    return result.patches

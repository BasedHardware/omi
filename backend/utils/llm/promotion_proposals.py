import json
import logging
import re
from enum import Enum
from typing import Any, Dict, List, Optional, Set, cast

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from models.memory_contracts import (
    DurableMemoryPatch,
    DurablePatchDecision,
    LifecycleState,
    deterministic_contract_id,
)

try:
    from .clients import get_llm

    _client_import_error: Optional[Exception] = None
except Exception as exc:
    # Benchmark/product-module tests may run without Firestore ADC or optional provider deps.
    # Keep the L2 prompt/parser/validation importable so callers can inject an equivalent llm.
    get_llm = None
    _client_import_error = exc
_CLIENT_IMPORT_ERROR = _client_import_error

logger = logging.getLogger(__name__)

_QUOTE_WRAPPER_RE = re.compile(r"^\s*User\s+(said|mentioned|stated|talked about|noted)\s+['\"]", re.IGNORECASE)
_CONTROL_FIELDS = {
    "patch_id",
    "idempotency_key",
    "packet_id",
    "run_id",
    "observed_head_commit_id",
    "new_memory_id",
    "evidence_refs",
}

PROMOTION_RUBRIC = """
- Promote to active when a Future agent/user would benefit from remembering this, it is stable or meaningfully recurring, it is about the primary user, user-owned work, a close relationship, or an entity the user cares about, and it has direct source evidence.
- Use review when attribution, durability, or sensitivity is uncertain but the packet may still be useful.
- Use context_only when the source may help future search/reasoning but should not become durable profile memory.
- Use reject for unsupported, transient, generic, wrong-subject, media/story narration, or conversational activity facts.
- Do not rewrite unidentified non-primary speaker facts as user facts; set relationship_to_user=other_speaker or unclear and choose review/context_only/reject unless the user tie is explicit.
""".strip()


class DurableMemoryPatchProposal(BaseModel):
    """Untrusted LLM proposal schema.

    The model proposes memory semantics only. Server-owned IDs, run metadata,
    provenance records, and evidence refs are resolved after validation.
    """

    model_config = ConfigDict(extra="forbid")

    decision: DurablePatchDecision
    result_status: LifecycleState
    evidence_ids: List[str] = Field(default_factory=list)
    target_memory_id: Optional[str] = None
    memory_text: Optional[str] = None
    predicate: Optional[str] = None
    arguments: Dict[str, Any] = Field(default_factory=dict)
    supersedes: List[str] = Field(default_factory=list)
    rationale: Optional[str] = None
    confidence: str = "medium"
    relationship_to_user: str = "unclear"
    subject_entity_id: Optional[str] = None
    subject_label: Optional[str] = None
    aboutness: str = "unclear"

    @model_validator(mode="after")
    def validate_proposal_contract(self):
        if (
            self.decision
            in {
                DurablePatchDecision.merge,
                DurablePatchDecision.update,
                DurablePatchDecision.add_evidence,
                DurablePatchDecision.skip_duplicate,
            }
            and not self.target_memory_id
        ):
            raise ValueError("target_memory_id is required for merge/update/add_evidence/skip_duplicate decisions")
        if self.decision == DurablePatchDecision.add and not self.memory_text:
            raise ValueError("add proposals require memory_text")
        if self.result_status in {LifecycleState.active, LifecycleState.review} and not self.evidence_ids:
            raise ValueError("active/review proposals require canonical evidence_ids")
        if self.confidence not in {"high", "medium", "low"}:
            raise ValueError("confidence must be high, medium, or low")
        if self.relationship_to_user not in {
            "self",
            "owned_work",
            "adopted",
            "asking_about",
            "encountered",
            "other_speaker",
            "unclear",
        }:
            raise ValueError("invalid relationship_to_user")
        if self.aboutness not in {"primary_user", "user_owned_project", "user_relationship", "third_party", "unclear"}:
            raise ValueError("invalid aboutness")
        return self


class DurableMemoryPatchProposals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patches: List[DurableMemoryPatchProposal] = Field(default_factory=list)  # type: ignore[reportUnknownVariableType]


# Neutral product vocabulary aliases (WS-G11).
PromotionProposal = DurableMemoryPatchProposal
PromotionProposals = DurableMemoryPatchProposals


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
    patches: List[DurableMemoryPatch] = Field(default_factory=list)  # type: ignore[reportUnknownVariableType]
    outcomes: List[CandidateOutcome] = Field(default_factory=list)  # type: ignore[reportUnknownVariableType]
    error_code: Optional[str] = None
    synthesis_terminal: bool = False


PromotionSynthesisResult = DurableMemorySynthesisResult


durable_memory_patch_prompt = cast(Any, ChatPromptTemplate).from_messages(
    [
        (
            "system",
            """
You are Omi Layer 2 durable memory synthesis.

Input contains one L2 evidence packet, automatically retrieved existing memories, and bounded replayed custom-search context. Emit durable_memory_patch_proposal.v1 objects only.

Choose one of: add, add_evidence, update, merge, keep_both, skip_duplicate, context_only, reject, review.

Rules:
- Emit proposal semantics only. NEVER emit patch_id, idempotency_key, packet_id, run_id, observed_head_commit_id, new_memory_id, or evidence_refs.
- Use retrieved/custom-search memory context before choosing add vs add_evidence/update/merge/skip_duplicate.
- target_memory_id is mandatory for merge, update, add_evidence, and skip_duplicate.
- Active or review outputs require exact canonical evidence_ids from the packet.
- Reject quote-wrapper cards like "User said/mentioned/stated ..."; rewrite into a durable abstraction or reject/review.
- Reject raw fragments, unsupported claims, wrong-subject claims, and secrets.
- Custom search results are context only; they are not primary evidence for new claims unless linked to durable evidence.
- Preserve attribution fields on every proposal: confidence, relationship_to_user, subject_entity_id, subject_label, and aboutness.

PROMOTION RUBRIC:
- Promote to active when a Future agent/user would benefit from remembering this, it is stable or meaningfully recurring, it is about the primary user, user-owned work, a close relationship, or an entity the user cares about, and it has direct source evidence.
- Use review when attribution, durability, or sensitivity is uncertain but the packet may still be useful.
- Use context_only when the source may help future search/reasoning but should not become durable profile memory.
- Use reject for unsupported, transient, generic, wrong-subject, media/story narration, or conversational activity facts.
- Do not rewrite unidentified non-primary speaker facts as user facts; set relationship_to_user=other_speaker or unclear and choose review/context_only/reject unless the user tie is explicit.

DRIFT GUARD: This production prompt and durable_memory_patch_proposal.v1 schema are the source of truth for benchmark L2 decisions. Benchmark runners may package evidence and export reports, but must call this product synthesizer for L2 memory decisions.

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

promotion_proposal_prompt = durable_memory_patch_prompt


def _content_from_response(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, list):
        return "\n".join(str(part) for part in cast(List[Any], content))
    return str(content)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _is_quote_wrapper(memory_text: Optional[str]) -> bool:
    if not memory_text:
        return False
    return bool(_QUOTE_WRAPPER_RE.match(memory_text))


def _logical_patch_payload(patch: DurableMemoryPatch, packet: Dict[str, Any]) -> Dict[str, Any]:
    """Server-owned logical operation fingerprint.

    Observed head and output index are execution context, not operation identity.
    The payload includes every field that affects persistent memory state.
    """
    return {
        "packet_id": patch.packet_id or packet.get("packet_id"),
        "decision": patch.decision.value,
        "result_status": patch.result_status.value,
        "target_memory_id": patch.target_memory_id,
        "new_memory_id": patch.new_memory_id,
        "memory_text": patch.memory_text,
        "evidence_ids": sorted(patch.evidence_ids or []),
        "predicate": patch.predicate,
        "arguments": patch.arguments,
        "supersedes": sorted(patch.supersedes or []),
        "confidence": patch.confidence,
        "relationship_to_user": patch.relationship_to_user,
        "subject_entity_id": patch.subject_entity_id,
        "subject_label": patch.subject_label,
        "aboutness": patch.aboutness,
    }


def _with_server_control_ids(
    patch: DurableMemoryPatch, packet: Dict[str, Any], observed_head_commit_id: Optional[str]
) -> DurableMemoryPatch:
    payload = _logical_patch_payload(patch, packet)
    idempotency_key = deterministic_contract_id("memory-durable-patch-idempotency", payload)
    patch_id = deterministic_contract_id("memory-durable-patch", payload)
    new_memory_id = patch.new_memory_id
    if patch.decision in {DurablePatchDecision.add, DurablePatchDecision.keep_both} and not patch.target_memory_id:
        new_memory_id = patch.new_memory_id or "mem_" + patch_id[:32]
        payload = {**payload, "new_memory_id": new_memory_id}
        idempotency_key = deterministic_contract_id("memory-durable-patch-idempotency", payload)
        patch_id = deterministic_contract_id("memory-durable-patch", payload)
    return patch.model_copy(
        update={
            "patch_id": patch_id,
            "idempotency_key": idempotency_key,
            "observed_head_commit_id": observed_head_commit_id,
            "packet_id": patch.packet_id or packet.get("packet_id"),
            "run_id": patch.run_id or packet.get("run_id") or "l2_patch_synthesizer",
            "new_memory_id": new_memory_id,
        }
    )


def _with_deterministic_patch_ids(
    patches: List[DurableMemoryPatch], packet: Dict[str, Any], observed_head_commit_id: Optional[str]
) -> List[DurableMemoryPatch]:
    return [_with_server_control_ids(patch, packet, observed_head_commit_id) for patch in patches]


def _valid_non_quote_wrapper_patches(patches: List[DurableMemoryPatch]) -> List[DurableMemoryPatch]:
    return [patch for patch in patches if not _is_quote_wrapper(patch.memory_text)]


def _with_production_safety_guards(patches: List[DurableMemoryPatch]) -> List[DurableMemoryPatch]:
    """Apply deterministic active-memory guardrails after LLM synthesis."""
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
                        + " Deterministic guard: third-party/encountered facts stay in Short-term/Archive context, not active Long-term memory.",
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
    ids: Set[str] = set(cast(List[Any], packet.get("evidence_ids") or []))
    for source_ref in cast(List[Any], packet.get("source_refs") or []):
        evidence_id = cast(Dict[str, Any], source_ref).get("evidence_id") if isinstance(source_ref, dict) else None
        if evidence_id:
            ids.add(evidence_id)
    for observation in cast(List[Any], packet.get("observations") or []):
        if not isinstance(observation, dict):
            continue
        ids.update(cast(List[Any], cast(Dict[str, Any], observation).get("evidence_ids") or []))
        for source_ref in cast(List[Any], cast(Dict[str, Any], observation).get("source_refs") or []):
            evidence_id = cast(Dict[str, Any], source_ref).get("evidence_id") if isinstance(source_ref, dict) else None
            if evidence_id:
                ids.add(evidence_id)
    return ids


def _retrieved_memory_ids(packet: Dict[str, Any]) -> set[str]:
    ids: Set[str] = set()
    for memory in cast(List[Any], packet.get("retrieved_memory_context") or []):
        if isinstance(memory, dict) and cast(Dict[str, Any], memory).get("memory_id"):
            ids.add(cast(str, memory["memory_id"]))
    return ids


def _raw_payload_from_response_text(text: str) -> Dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE).strip()
        stripped = re.sub(r"\s*```$", "", stripped).strip()
    payload = json.loads(stripped)
    if not isinstance(payload, dict):
        raise ValueError("synthesis payload must be a JSON object")
    return cast(Dict[str, Any], payload)


def _proposal_to_patch(
    proposal: DurableMemoryPatchProposal, packet: Dict[str, Any], observed_head_commit_id: Optional[str]
) -> DurableMemoryPatch:
    return DurableMemoryPatch(
        patch_id="server_pending",
        packet_id=packet.get("packet_id") or "unknown_packet",
        run_id=packet.get("run_id") or "l2_patch_synthesizer",
        observed_head_commit_id=observed_head_commit_id,
        idempotency_key="server_pending",
        decision=proposal.decision,
        result_status=proposal.result_status,
        evidence_ids=proposal.evidence_ids,
        evidence_refs=[],
        target_memory_id=proposal.target_memory_id,
        new_memory_id=None,
        memory_text=proposal.memory_text,
        predicate=proposal.predicate,
        arguments=proposal.arguments,
        supersedes=proposal.supersedes,
        rationale=proposal.rationale,
        confidence=proposal.confidence,  # type: ignore[arg-type]
        relationship_to_user=proposal.relationship_to_user,  # type: ignore[arg-type]
        subject_entity_id=proposal.subject_entity_id,
        subject_label=proposal.subject_label,
        aboutness=proposal.aboutness,  # type: ignore[arg-type]
    )


def synthesize_durable_memory_patch_result(
    *,
    packet: Dict[str, Any],
    custom_search_artifact: Dict[str, Any],
    observed_head_commit_id: Optional[str],
    llm: Any = None,
) -> DurableMemorySynthesisResult:
    parser = PydanticOutputParser(pydantic_object=DurableMemoryPatchProposals)
    messages = durable_memory_patch_prompt.format_messages(
        observed_head_commit_id=observed_head_commit_id or "unknown",
        packet_json=_canonical_json(packet),
        custom_search_json=_canonical_json(custom_search_artifact),
        format_instructions=parser.get_format_instructions(),
    )
    if llm is not None:
        model: Any = llm
    elif get_llm is not None:
        model = get_llm("memory_l2")
    else:
        logger.error("Error synthesizing memory durable patches: missing_llm_client")
        return DurableMemorySynthesisResult(
            status=SynthesisStatus.retryable_failure,
            error_code="missing_llm_client",
            synthesis_terminal=False,
        )

    try:
        response = model.invoke(messages)
    except Exception as exc:
        logger.error("Error invoking memory durable patch synthesizer: %s", type(exc).__name__)
        return DurableMemorySynthesisResult(
            status=SynthesisStatus.retryable_failure,
            error_code="provider_error",
            synthesis_terminal=False,
        )

    try:
        raw_payload = _raw_payload_from_response_text(_content_from_response(response))
    except Exception as exc:
        logger.error("Error parsing memory durable patch payload: %s", type(exc).__name__)
        return DurableMemorySynthesisResult(
            status=SynthesisStatus.retryable_failure,
            error_code="parse_error",
            synthesis_terminal=False,
        )

    raw_patches = raw_payload.get("patches", [])
    if not isinstance(raw_patches, list):
        return DurableMemorySynthesisResult(
            status=SynthesisStatus.retryable_failure,
            error_code="patches_not_list",
            synthesis_terminal=False,
        )
    if not raw_patches:
        return DurableMemorySynthesisResult(
            status=SynthesisStatus.retryable_failure,
            error_code="empty_output_without_explicit_noop",
            synthesis_terminal=False,
        )

    allowed_evidence = _packet_evidence_ids(packet)
    allowed_memory_ids = _retrieved_memory_ids(packet)
    patches: List[DurableMemoryPatch] = []
    outcomes: List[CandidateOutcome] = []

    for index, raw_patch in enumerate(cast(List[Any], raw_patches)):
        if not isinstance(raw_patch, dict):
            outcomes.append(
                CandidateOutcome(index=index, status=CandidateOutcomeStatus.invalid, reason_code="not_object")
            )
            continue
        if _CONTROL_FIELDS.intersection(cast(Dict[str, Any], raw_patch).keys()):
            outcomes.append(
                CandidateOutcome(
                    index=index, status=CandidateOutcomeStatus.invalid, reason_code="untrusted_control_field"
                )
            )
            continue
        try:
            proposal = DurableMemoryPatchProposal(**cast(Dict[str, Any], raw_patch))
        except ValidationError:
            outcomes.append(
                CandidateOutcome(index=index, status=CandidateOutcomeStatus.invalid, reason_code="validation_error")
            )
            continue

        evidence_ids: Set[str] = set(proposal.evidence_ids or [])
        if not evidence_ids.issubset(allowed_evidence):
            outcomes.append(
                CandidateOutcome(
                    index=index,
                    status=CandidateOutcomeStatus.invalid,
                    reason_code="evidence_not_in_packet",
                    evidence_ids=proposal.evidence_ids,
                )
            )
            continue
        memory_refs = {proposal.target_memory_id, *proposal.supersedes} - {None, ""}
        if memory_refs and not memory_refs.issubset(allowed_memory_ids):
            outcomes.append(
                CandidateOutcome(
                    index=index, status=CandidateOutcomeStatus.invalid, reason_code="memory_ref_not_authorized"
                )
            )
            continue

        try:
            patch = _proposal_to_patch(proposal, packet, observed_head_commit_id)
            patch = _with_production_safety_guards([patch])[0]
            if _is_quote_wrapper(patch.memory_text):
                outcomes.append(
                    CandidateOutcome(
                        index=index,
                        status=CandidateOutcomeStatus.reject,
                        reason_code="quote_wrapper_quality_guard",
                        evidence_ids=patch.evidence_ids,
                    )
                )
                continue
            patch = _with_server_control_ids(patch, packet, observed_head_commit_id)
            patch = DurableMemoryPatch(**patch.dict())
        except ValidationError:
            outcomes.append(
                CandidateOutcome(index=index, status=CandidateOutcomeStatus.invalid, reason_code="validation_error")
            )
            continue
        patches.append(patch)
        outcomes.append(_candidate_outcome_for_patch(index, patch))

    invalid_count = sum(1 for outcome in outcomes if outcome.status == CandidateOutcomeStatus.invalid)
    if patches and invalid_count:
        status = SynthesisStatus.partial
    elif patches or any(outcome.status != CandidateOutcomeStatus.invalid for outcome in outcomes):
        status = SynthesisStatus.success
    else:
        status = SynthesisStatus.retryable_failure
    return DurableMemorySynthesisResult(
        status=status,
        patches=patches,
        outcomes=outcomes,
        synthesis_terminal=status != SynthesisStatus.retryable_failure,
    )


def synthesize_durable_memory_patches(
    *,
    packet: Dict[str, Any],
    custom_search_artifact: Dict[str, Any],
    observed_head_commit_id: Optional[str],
    llm: Any = None,
) -> List[DurableMemoryPatch]:
    result = synthesize_durable_memory_patch_result(
        packet=packet,
        custom_search_artifact=custom_search_artifact,
        observed_head_commit_id=observed_head_commit_id,
        llm=llm,
    )
    if result.status != SynthesisStatus.success and result.status != SynthesisStatus.partial:
        raise RuntimeError(
            f"memory durable synthesis did not reach terminal success: {result.error_code or result.status.value}"
        )
    return result.patches


__all__ = [
    "PROMOTION_RUBRIC",
    "CandidateOutcome",
    "CandidateOutcomeStatus",
    "DurableMemoryPatchProposal",
    "DurableMemoryPatchProposals",
    "DurableMemorySynthesisResult",
    "PromotionProposal",
    "PromotionProposals",
    "PromotionSynthesisResult",
    "SynthesisStatus",
    "_CLIENT_IMPORT_ERROR",
    "_CONTROL_FIELDS",
    "_QUOTE_WRAPPER_RE",
    "_candidate_outcome_for_patch",
    "_canonical_json",
    "_content_from_response",
    "_is_quote_wrapper",
    "_logical_patch_payload",
    "_packet_evidence_ids",
    "_proposal_to_patch",
    "_raw_payload_from_response_text",
    "_retrieved_memory_ids",
    "_valid_non_quote_wrapper_patches",
    "_with_deterministic_patch_ids",
    "_with_production_safety_guards",
    "_with_server_control_ids",
    "durable_memory_patch_prompt",
    "get_llm",
    "logger",
    "promotion_proposal_prompt",
    "synthesize_durable_memory_patch_result",
    "synthesize_durable_memory_patches",
]

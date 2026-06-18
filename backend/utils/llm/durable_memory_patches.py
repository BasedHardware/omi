import json
import logging
import re
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


def _with_deterministic_patch_ids(
    patches: List[DurableMemoryPatch], packet: Dict[str, Any], observed_head_commit_id: Optional[str]
) -> List[DurableMemoryPatch]:
    normalized = []
    for index, patch in enumerate(patches):
        payload = {
            "packet_id": patch.packet_id or packet.get("packet_id"),
            "decision": patch.decision.value,
            "target_memory_id": patch.target_memory_id,
            "memory_text": patch.memory_text,
            "evidence_ids": patch.evidence_ids,
            "index": index,
            "observed_head_commit_id": observed_head_commit_id,
        }
        idempotency_key = patch.idempotency_key or deterministic_contract_id("v17-durable-patch-idempotency", payload)
        patch_id = patch.patch_id or deterministic_contract_id("v17-durable-patch", payload)
        normalized.append(
            patch.model_copy(
                update={
                    "patch_id": patch_id,
                    "idempotency_key": idempotency_key,
                    "observed_head_commit_id": patch.observed_head_commit_id or observed_head_commit_id,
                    "packet_id": patch.packet_id or packet.get("packet_id"),
                    "run_id": patch.run_id or packet.get("run_id") or "v17_l2_patch_synthesizer",
                }
            )
        )
    return normalized


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


def synthesize_durable_memory_patches(
    *,
    packet: Dict[str, Any],
    custom_search_artifact: Dict[str, Any],
    observed_head_commit_id: Optional[str],
    llm=None,
) -> List[DurableMemoryPatch]:
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
        return []

    try:
        response = model.invoke(messages)
        parsed = parser.parse(_content_from_response(response))
        patches = _with_deterministic_patch_ids(parsed.patches, packet, observed_head_commit_id)
        patches = _with_production_safety_guards(patches)
        return _valid_non_quote_wrapper_patches(patches)
    except (ValidationError, Exception) as exc:
        logger.error("Error synthesizing V17 durable patches: %s", type(exc).__name__)
        return []

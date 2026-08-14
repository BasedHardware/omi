"""Server-owned canonical promotion and graph-admission contracts.

Long-term memory is a state transition, never a create-time option.  The
promotion planner may propose a compact structured graph plan, but deterministic
code binds that plan to the current short-term item revision, content, and
evidence before the authoritative apply transaction accepts it.
"""

from __future__ import annotations

import json
import math
from datetime import datetime
from typing import Any, Dict, List, Literal, cast

from pydantic import AwareDatetime, BaseModel, Field, field_validator, model_validator

from models.memory_contracts import deterministic_contract_id

PROMOTION_ADMISSION_VERSION = "canonical_memory_promotion_admission.v1"
PROMOTION_GRAPH_PLAN_VERSION = "canonical_memory_graph_plan.v1"
PROMOTION_GRAPH_PLAN_V2_VERSION = "canonical_memory_graph_plan.v2"
PROMOTION_GRAPH_ASSERTION_VERSION = "canonical_memory_graph_assertion.v1"
PROMOTION_GRAPH_ASSERTION_V2_VERSION = "canonical_memory_graph_assertion.v2"
PROMOTION_PLANNER_ID = "canonical_batched_promotion"
PROMOTION_PLANNER_VERSION = "v2"
PROMOTION_GRAPH_SUBJECT_MAX_LENGTH = 200
PROMOTION_GRAPH_PREDICATE_MAX_LENGTH = 64
PROMOTION_GRAPH_ARGUMENT_MAX_COUNT = 16
PROMOTION_GRAPH_ARGUMENT_KEY_MAX_LENGTH = 64
PROMOTION_GRAPH_ARGUMENTS_MAX_JSON_BYTES = 8 * 1024
PROMOTION_GRAPH_ARGUMENTS_MAX_DEPTH = 8
CanonicalGraphNodeType = Literal["person", "place", "organization", "thing", "concept"]


def canonical_graph_entity_id(label: str) -> str:
    """Return the stable graph endpoint id for a readable entity label."""
    normalized = " ".join((label or "").split()).casefold()
    if not normalized:
        raise ValueError("canonical graph entity label must not be blank")
    if normalized == "user":
        return "user"
    if normalized.startswith("ent_"):
        return normalized
    return "ent_" + deterministic_contract_id("canonical-graph-entity", {"label": normalized})[:20]


def _normalized_arguments(arguments: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for key, value in sorted(arguments.items()):
        normalized_key = key.strip()
        if not normalized_key:
            raise ValueError("promotion graph argument keys must not be blank")
        if normalized_key in normalized:
            raise ValueError("promotion graph argument keys must be unique after trimming")
        normalized[normalized_key] = value
    return normalized


def _validate_json_value(value: Any, *, depth: int, ancestors: set[int]) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("promotion graph argument numbers must be finite JSON numbers")
        return
    if not isinstance(value, (list, dict)):
        raise ValueError(
            "promotion graph arguments must contain only JSON values "
            "(null, boolean, number, string, array, or object)"
        )
    if depth > PROMOTION_GRAPH_ARGUMENTS_MAX_DEPTH:
        raise ValueError(
            f"promotion graph arguments exceed maximum JSON nesting depth " f"of {PROMOTION_GRAPH_ARGUMENTS_MAX_DEPTH}"
        )

    container = cast(list[Any] | Dict[Any, Any], value)
    container_id = id(container)
    if container_id in ancestors:
        raise ValueError("promotion graph arguments must not contain cyclic containers")
    ancestors.add(container_id)
    try:
        if isinstance(container, list):
            for item in container:
                _validate_json_value(item, depth=depth + 1, ancestors=ancestors)
            return
        for key, item in container.items():
            if not isinstance(key, str):
                raise ValueError("promotion graph argument object keys must be strings")
            if len(key) > PROMOTION_GRAPH_ARGUMENT_KEY_MAX_LENGTH:
                raise ValueError(
                    f"promotion graph argument keys must be at most "
                    f"{PROMOTION_GRAPH_ARGUMENT_KEY_MAX_LENGTH} characters"
                )
            _validate_json_value(item, depth=depth + 1, ancestors=ancestors)
    finally:
        ancestors.remove(container_id)


def _validate_and_normalize_arguments(value: Any, *, require_nonempty: bool = True) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("promotion graph arguments must be a JSON object")
    arguments = cast(Dict[str, Any], value)
    if len(arguments) > PROMOTION_GRAPH_ARGUMENT_MAX_COUNT:
        raise ValueError(f"promotion graph plan supports at most {PROMOTION_GRAPH_ARGUMENT_MAX_COUNT} arguments")

    _validate_json_value(arguments, depth=0, ancestors=set())
    normalized = _normalized_arguments(arguments)
    if require_nonempty and not normalized:
        raise ValueError("promotion graph plan requires at least one argument")

    try:
        payload_size = len(
            json.dumps(
                normalized,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            ).encode("utf-8")
        )
    except (OverflowError, RecursionError, TypeError, ValueError) as exc:
        raise ValueError("promotion graph arguments must be encodable as canonical JSON") from exc
    if payload_size > PROMOTION_GRAPH_ARGUMENTS_MAX_JSON_BYTES:
        raise ValueError(
            f"promotion graph arguments JSON payload must be at most "
            f"{PROMOTION_GRAPH_ARGUMENTS_MAX_JSON_BYTES} bytes"
        )
    return normalized


class GraphRelationEndpoint(BaseModel):
    """A typed graph endpoint whose identity is derived from its source label."""

    entity_id: str = ""
    label: str
    # This is the stable desktop graph vocabulary.  Rejecting unknown model
    # output here keeps a type change from silently degrading into a concept.
    node_type: CanonicalGraphNodeType

    @field_validator("label", "node_type")
    @classmethod
    def validate_nonblank(cls, value: str) -> str:
        normalized = " ".join((value or "").split())
        if not normalized:
            raise ValueError("graph relation endpoint label and node_type must not be blank")
        if len(normalized) > PROMOTION_GRAPH_SUBJECT_MAX_LENGTH:
            raise ValueError("graph relation endpoint fields exceed the maximum length")
        return normalized

    @model_validator(mode="after")
    def normalize_entity_id(self):
        expected = canonical_graph_entity_id(self.label)
        if self.entity_id and self.entity_id != expected:
            raise ValueError("graph relation endpoint id must be derived from its label")
        self.entity_id = expected
        return self


class PromotionGraphPlan(BaseModel):
    """A non-empty graph assertion generated in the same L2 planning call."""

    schema_version: Literal["canonical_memory_graph_plan.v1", "canonical_memory_graph_plan.v2"] = (
        PROMOTION_GRAPH_PLAN_VERSION
    )
    subject_entity_id: str
    predicate: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    subject: GraphRelationEndpoint | None = None
    object: GraphRelationEndpoint | None = None
    qualifiers: Dict[str, Any] = Field(default_factory=dict)
    plan_hash: str = ""

    @field_validator("subject_entity_id")
    @classmethod
    def validate_subject_entity_id(cls, value: str) -> str:
        stripped = (value or "").strip()
        if not stripped:
            raise ValueError("promotion graph subject and predicate must not be blank")
        if len(stripped) > PROMOTION_GRAPH_SUBJECT_MAX_LENGTH:
            raise ValueError(
                f"promotion graph subject_entity_id must be at most " f"{PROMOTION_GRAPH_SUBJECT_MAX_LENGTH} characters"
            )
        return stripped

    @field_validator("predicate")
    @classmethod
    def validate_predicate(cls, value: str) -> str:
        stripped = (value or "").strip()
        if not stripped:
            raise ValueError("promotion graph subject and predicate must not be blank")
        if len(stripped) > PROMOTION_GRAPH_PREDICATE_MAX_LENGTH:
            raise ValueError(
                f"promotion graph predicate must be at most {PROMOTION_GRAPH_PREDICATE_MAX_LENGTH} characters"
            )
        return stripped

    @field_validator("arguments", mode="before")
    @classmethod
    def validate_arguments(cls, value: Any) -> Dict[str, Any]:
        return _validate_and_normalize_arguments(value, require_nonempty=False)

    @field_validator("qualifiers", mode="before")
    @classmethod
    def validate_qualifiers(cls, value: Any) -> Dict[str, Any]:
        return _validate_and_normalize_arguments(value, require_nonempty=False)

    def hash_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "schema_version": self.schema_version,
            "subject_entity_id": self.subject_entity_id,
            "predicate": self.predicate,
            "arguments": self.arguments,
        }
        if self.schema_version == PROMOTION_GRAPH_PLAN_V2_VERSION:
            payload.update(
                {
                    "subject": self.subject.model_dump(mode="json") if self.subject else None,
                    "object": self.object.model_dump(mode="json") if self.object else None,
                    "qualifiers": self.qualifiers,
                }
            )
        return payload

    @model_validator(mode="after")
    def derive_or_validate_hash(self):
        if self.schema_version == PROMOTION_GRAPH_PLAN_V2_VERSION:
            if self.subject is None or self.object is None:
                raise ValueError("v2 graph relation plans require typed subject and object endpoints")
            if self.subject.entity_id != self.subject_entity_id:
                raise ValueError("v2 graph relation subject must match subject_entity_id")
            if self.subject.entity_id == self.object.entity_id:
                raise ValueError("v2 graph relation plans must not contain self-loops")
            if self.arguments and self.arguments != self.qualifiers:
                raise ValueError("v2 graph relation arguments must match qualifiers")
            self.arguments = self.qualifiers
        elif not self.arguments:
            raise ValueError("promotion graph plan requires at least one argument")
        expected = deterministic_contract_id("canonical-promotion-graph-plan", self.hash_payload())
        if self.plan_hash and self.plan_hash != expected:
            raise ValueError("promotion graph plan hash mismatch")
        self.plan_hash = expected
        return self


class PromotionAdmissionReceipt(BaseModel):
    """Server-authored proof that one exact ST revision passed L2 admission."""

    receipt_version: Literal["canonical_memory_promotion_admission.v1"] = PROMOTION_ADMISSION_VERSION
    receipt_id: str = ""
    planner_id: Literal["canonical_batched_promotion"] = PROMOTION_PLANNER_ID
    planner_version: Literal["v2"] = PROMOTION_PLANNER_VERSION
    decision: Literal["durable"] = "durable"
    memory_id: str
    source_item_revision: int
    output_content_hash: str
    evidence_ids: List[str]
    graph_plan_hash: str
    supersedes: List[str] = Field(default_factory=list)

    @field_validator("memory_id", "output_content_hash", "graph_plan_hash")
    @classmethod
    def validate_nonblank(cls, value: str) -> str:
        stripped = (value or "").strip()
        if not stripped:
            raise ValueError("promotion admission fields must not be blank")
        return stripped

    @field_validator("source_item_revision")
    @classmethod
    def validate_revision(cls, value: int) -> int:
        if value < 1:
            raise ValueError("source_item_revision must be positive")
        return value

    @field_validator("evidence_ids")
    @classmethod
    def validate_evidence(cls, value: List[str]) -> List[str]:
        normalized = sorted({item.strip() for item in value if item and item.strip()})
        if not normalized:
            raise ValueError("promotion admission requires evidence")
        return normalized

    @field_validator("supersedes")
    @classmethod
    def normalize_supersedes(cls, value: List[str]) -> List[str]:
        return sorted({item.strip() for item in value if item and item.strip()})

    def identity_payload(self) -> Dict[str, Any]:
        return {
            "receipt_version": self.receipt_version,
            "planner_id": self.planner_id,
            "planner_version": self.planner_version,
            "decision": self.decision,
            "memory_id": self.memory_id,
            "source_item_revision": self.source_item_revision,
            "output_content_hash": self.output_content_hash,
            "evidence_ids": self.evidence_ids,
            "graph_plan_hash": self.graph_plan_hash,
            "supersedes": self.supersedes,
        }

    @model_validator(mode="after")
    def derive_or_validate_id(self):
        expected = (
            "padm_"
            + deterministic_contract_id(
                "canonical-promotion-admission",
                self.identity_payload(),
            )[:32]
        )
        if self.receipt_id and self.receipt_id != expected:
            raise ValueError("promotion admission receipt id mismatch")
        self.receipt_id = expected
        return self


class MemoryGraphAssertion(BaseModel):
    """Atomic, authoritative per-memory KG assertion.

    Shared entity/edge indexes are projections of this document.  Keeping the
    assertion next to the memory commit means an active Long-term item can never
    exist without a version-fenced graph representation.
    """

    schema_version: Literal["canonical_memory_graph_assertion.v1", "canonical_memory_graph_assertion.v2"] = (
        PROMOTION_GRAPH_ASSERTION_VERSION
    )
    assertion_id: str
    uid: str
    memory_id: str
    item_revision: int
    content_hash: str
    evidence_ids: List[str]
    subject_entity_id: str
    predicate: str
    arguments: Dict[str, Any]
    subject: GraphRelationEndpoint | None = None
    object: GraphRelationEndpoint | None = None
    qualifiers: Dict[str, Any] = Field(default_factory=dict)
    graph_plan_hash: str
    commit_id: str
    commit_sequence: int
    status: Literal["active"] = "active"
    created_at: AwareDatetime

    @field_validator(
        "assertion_id",
        "uid",
        "memory_id",
        "content_hash",
        "subject_entity_id",
        "predicate",
        "graph_plan_hash",
        "commit_id",
    )
    @classmethod
    def validate_nonblank(cls, value: str) -> str:
        stripped = (value or "").strip()
        if not stripped:
            raise ValueError("graph assertion fields must not be blank")
        return stripped

    @field_validator("item_revision", "commit_sequence")
    @classmethod
    def validate_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("graph assertion counters must be positive")
        return value

    @field_validator("evidence_ids")
    @classmethod
    def validate_evidence(cls, value: List[str]) -> List[str]:
        normalized = sorted({item.strip() for item in value if item and item.strip()})
        if not normalized:
            raise ValueError("graph assertion requires evidence")
        return normalized

    @model_validator(mode="after")
    def validate_plan_hash(self):
        plan = PromotionGraphPlan(
            schema_version=(
                PROMOTION_GRAPH_PLAN_V2_VERSION
                if self.schema_version == PROMOTION_GRAPH_ASSERTION_V2_VERSION
                else PROMOTION_GRAPH_PLAN_VERSION
            ),
            subject_entity_id=self.subject_entity_id,
            predicate=self.predicate,
            arguments=self.arguments,
            subject=self.subject,
            object=self.object,
            qualifiers=self.qualifiers,
            plan_hash=self.graph_plan_hash,
        )
        self.arguments = plan.arguments
        self.subject = plan.subject
        self.object = plan.object
        self.qualifiers = plan.qualifiers
        return self

    def graph_records(self) -> Dict[str, List[Dict[str, Any]]]:
        """Derive stable graph nodes/edges without another model call."""
        if self.schema_version == PROMOTION_GRAPH_ASSERTION_V2_VERSION:
            assert self.subject is not None and self.object is not None
            nodes = {
                self.subject.entity_id: {
                    "id": self.subject.entity_id,
                    "label": self.subject.label,
                    "node_type": self.subject.node_type,
                    "aliases": [],
                    "memory_ids": [self.memory_id],
                },
                self.object.entity_id: {
                    "id": self.object.entity_id,
                    "label": self.object.label,
                    "node_type": self.object.node_type,
                    "aliases": [],
                    "memory_ids": [self.memory_id],
                },
            }
            return {
                "nodes": list(nodes.values()),
                "edges": [
                    {
                        "id": "edge_"
                        + deterministic_contract_id(
                            "canonical-graph-edge",
                            {
                                "source_id": self.subject.entity_id,
                                "target_id": self.object.entity_id,
                                "label": self.predicate,
                            },
                        )[:24],
                        "source_id": self.subject.entity_id,
                        "target_id": self.object.entity_id,
                        "label": self.predicate,
                        "memory_ids": [self.memory_id],
                    }
                ],
            }
        nodes: Dict[str, Dict[str, Any]] = {
            self.subject_entity_id: {
                "id": self.subject_entity_id,
                "label": self.subject_entity_id,
                "node_type": "entity",
                "aliases": [],
                "memory_ids": [self.memory_id],
            }
        }
        edges: List[Dict[str, Any]] = []
        for slot, raw_value in self.arguments.items():
            if isinstance(raw_value, dict):
                object_value = cast(Dict[str, Any], raw_value)
                label = str(
                    object_value.get("label") or object_value.get("value") or object_value.get("entity_id") or slot
                )
                target_id = str(object_value.get("entity_id") or canonical_graph_entity_id(label))
            else:
                label = str(raw_value)
                target_id = canonical_graph_entity_id(label)
            nodes.setdefault(
                target_id,
                {
                    "id": target_id,
                    "label": label,
                    "node_type": "entity",
                    "aliases": [],
                    "memory_ids": [self.memory_id],
                },
            )
            edge_label = self.predicate if len(self.arguments) == 1 else f"{self.predicate}:{slot}"
            edges.append(
                {
                    "id": "edge_"
                    + deterministic_contract_id(
                        "canonical-graph-edge",
                        {
                            "source_id": self.subject_entity_id,
                            "target_id": target_id,
                            "label": edge_label,
                        },
                    )[:24],
                    "source_id": self.subject_entity_id,
                    "target_id": target_id,
                    "label": edge_label,
                    "memory_ids": [self.memory_id],
                }
            )
        return {"nodes": list(nodes.values()), "edges": edges}


def build_promotion_admission_receipt(
    *,
    memory_id: str,
    source_item_revision: int,
    output_content_hash: str,
    evidence_ids: List[str],
    graph_plan: PromotionGraphPlan,
    supersedes: List[str],
) -> PromotionAdmissionReceipt:
    return PromotionAdmissionReceipt(
        memory_id=memory_id,
        source_item_revision=source_item_revision,
        output_content_hash=output_content_hash,
        evidence_ids=evidence_ids,
        graph_plan_hash=graph_plan.plan_hash,
        supersedes=supersedes,
    )


def build_memory_graph_assertion(
    *,
    uid: str,
    memory_id: str,
    item_revision: int,
    content_hash: str,
    evidence_ids: List[str],
    graph_plan: PromotionGraphPlan,
    commit_id: str,
    commit_sequence: int,
    created_at: datetime,
) -> MemoryGraphAssertion:
    assertion_id = (
        "mga_"
        + deterministic_contract_id(
            "canonical-memory-graph-assertion",
            {
                "uid": uid,
                "memory_id": memory_id,
                "item_revision": item_revision,
                "content_hash": content_hash,
                "graph_plan_hash": graph_plan.plan_hash,
            },
        )[:32]
    )
    return MemoryGraphAssertion(
        schema_version=(
            PROMOTION_GRAPH_ASSERTION_V2_VERSION
            if graph_plan.schema_version == PROMOTION_GRAPH_PLAN_V2_VERSION
            else PROMOTION_GRAPH_ASSERTION_VERSION
        ),
        assertion_id=assertion_id,
        uid=uid,
        memory_id=memory_id,
        item_revision=item_revision,
        content_hash=content_hash,
        evidence_ids=sorted(set(evidence_ids)),
        subject_entity_id=graph_plan.subject_entity_id,
        predicate=graph_plan.predicate,
        arguments=graph_plan.arguments,
        subject=graph_plan.subject,
        object=graph_plan.object,
        qualifiers=graph_plan.qualifiers,
        graph_plan_hash=graph_plan.plan_hash,
        commit_id=commit_id,
        commit_sequence=commit_sequence,
        created_at=created_at,
    )


def valid_promotion_admission(
    *,
    memory_id: str,
    source_item_revision: int,
    output_content_hash: str,
    evidence_ids: List[str],
    subject_entity_id: str | None,
    predicate: str | None,
    arguments: Dict[str, Any],
    supersedes: List[str],
    promotion: Dict[str, Any],
) -> bool:
    """Validate the complete server-authored promotion proof for an ST item."""
    try:
        graph_plan = PromotionGraphPlan(**promotion["graph_plan"])
        receipt = PromotionAdmissionReceipt(**promotion["admission_receipt"])
        normalized_arguments = _validate_and_normalize_arguments(arguments)
    except (KeyError, TypeError, ValueError):
        return False
    return (
        receipt.memory_id == memory_id
        and receipt.source_item_revision == source_item_revision
        and receipt.output_content_hash == output_content_hash
        and receipt.evidence_ids == sorted(set(evidence_ids))
        and receipt.graph_plan_hash == graph_plan.plan_hash
        and graph_plan.subject_entity_id == (subject_entity_id or "")
        and graph_plan.predicate == (predicate or "")
        and graph_plan.arguments == normalized_arguments
        and receipt.supersedes == sorted(set(supersedes))
        and memory_id not in receipt.supersedes
    )


__all__ = [
    "MemoryGraphAssertion",
    "CanonicalGraphNodeType",
    "PROMOTION_ADMISSION_VERSION",
    "PROMOTION_GRAPH_ASSERTION_VERSION",
    "PROMOTION_GRAPH_ASSERTION_V2_VERSION",
    "PROMOTION_GRAPH_ARGUMENT_KEY_MAX_LENGTH",
    "PROMOTION_GRAPH_ARGUMENT_MAX_COUNT",
    "PROMOTION_GRAPH_ARGUMENTS_MAX_DEPTH",
    "PROMOTION_GRAPH_ARGUMENTS_MAX_JSON_BYTES",
    "PROMOTION_GRAPH_PLAN_VERSION",
    "PROMOTION_GRAPH_PLAN_V2_VERSION",
    "PROMOTION_GRAPH_PREDICATE_MAX_LENGTH",
    "PROMOTION_GRAPH_SUBJECT_MAX_LENGTH",
    "PROMOTION_PLANNER_ID",
    "PROMOTION_PLANNER_VERSION",
    "PromotionAdmissionReceipt",
    "GraphRelationEndpoint",
    "PromotionGraphPlan",
    "build_memory_graph_assertion",
    "build_promotion_admission_receipt",
    "valid_promotion_admission",
]

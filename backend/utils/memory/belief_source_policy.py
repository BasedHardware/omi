"""Deterministic evidence authority; transport and repetition are not truth."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Sequence

from models.memory_evidence import MemoryEvidence, RedactionStatus, SourceState
from models.product_memory import MemoryItem, MemoryItemStatus, ProcessingState, RESTRICTED_SENSITIVITY_LABELS

# Coarse, ratified source order. These are ordering values, not confidence scores.
AUTHORITY = {
    "unknown": 0,
    "assistant": 0,
    "inferred": 1,
    "third_party": 1,
    "screen": 2,
    "user_spoken": 3,
    "user_written": 4,
    "user_direct": 5,
}


def usable_evidence(evidence: MemoryEvidence) -> bool:
    return (
        evidence.source_state == SourceState.active
        and evidence.redaction_status == RedactionStatus.active
        and evidence.encryption_or_redaction_status == RedactionStatus.active
    )


def eligible_record(item: MemoryItem) -> bool:
    promotion = item.promotion or {}
    use = item.arguments.get("memory_use")
    return (
        item.status == MemoryItemStatus.active
        and item.processing_state == ProcessingState.processed
        and item.source_state == SourceState.active
        and not set(item.sensitivity_labels).intersection(RESTRICTED_SENSITIVITY_LABELS)
        and not promotion.get("is_locked", False)
        and promotion.get("user_review") is not False
        and not (isinstance(use, dict) and use.get("suppressed") is True)
        and any(usable_evidence(evidence) for evidence in item.evidence)
    )


def evidence_family(evidence: MemoryEvidence) -> str | None:
    """Original lineage wins. A frame ID alone does not prove independence."""
    if not usable_evidence(evidence):
        return None
    if evidence.lineage_id:
        return evidence.lineage_id
    group = evidence.independence_group
    if group and group not in {"unknown", "legacy", f"{evidence.source_type}:unknown"}:
        return group
    if evidence.source_type == "conversation" and evidence.source_id:
        return f"conversation:{evidence.source_id}"
    return None


def evidence_families(item: MemoryItem) -> frozenset[str]:
    return frozenset(family for evidence in item.evidence if (family := evidence_family(evidence)))


def _field(value: object, name: str, default: object = None) -> object:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _enum_text(value: object) -> str | None:
    raw = getattr(value, "value", value)
    return raw if isinstance(raw, str) else None


def _usable_authority_evidence(evidence: object) -> bool:
    """Read authority metadata from canonical evidence or legacy projections."""
    source_state = _enum_text(_field(evidence, "source_state"))
    if source_state is not None and source_state != SourceState.active.value:
        return False
    for field in ("redaction_status", "encryption_or_redaction_status"):
        status = _enum_text(_field(evidence, field))
        if status is not None and status != RedactionStatus.active.value:
            return False
    return True


def source_authority(item: object) -> int:
    promotion = _field(item, "promotion")
    promotion = promotion if isinstance(promotion, Mapping) else {}
    if (
        bool(_field(item, "user_asserted", False))
        or bool(_field(item, "manually_added", False))
        or (promotion.get("reviewed") is True and promotion.get("user_review") is True)
        or (_field(item, "reviewed") is True and _field(item, "user_review") is True)
    ):
        return AUTHORITY["user_direct"]
    ranks: list[int] = []
    raw_evidence = _field(item, "evidence", ())
    evidence_items = (
        raw_evidence
        if isinstance(raw_evidence, Sequence) and not isinstance(raw_evidence, (str, bytes, bytearray))
        else ()
    )
    for evidence in evidence_items:
        if not _usable_authority_evidence(evidence):
            continue
        attribution = _enum_text(_field(evidence, "attribution")) or "unknown"
        if attribution == "user_direct":
            # Direct authority belongs to the canonical owner assertion, never
            # to capture metadata supplied by an automated producer.
            ranks.append(AUTHORITY["unknown"])
        elif attribution in AUTHORITY and attribution != "unknown":
            ranks.append(AUTHORITY[attribution])
        # A transport or the subject of a claim does not establish its author.
        # Legacy evidence without attribution stays unknown until classified.
    return max(ranks, default=AUTHORITY["unknown"])


def has_verified_owner_authorship(item: object) -> bool:
    """Require owner-authored evidence before a record can drive a proactive bar."""
    return source_authority(item) >= AUTHORITY["user_spoken"]


def same_subject(left: MemoryItem, right: MemoryItem) -> bool:
    if left.subject_scope != right.subject_scope:
        return False
    left_subject, right_subject = left.subject_entity_id, right.subject_entity_id
    if left_subject or right_subject:
        return left_subject == right_subject
    # Primary-user is an account-bound subject; two anonymous third parties are not.
    return getattr(left.subject_scope, "value", left.subject_scope) == "primary_user"


def independent_authoritative_evidence(new: MemoryItem, existing: MemoryItem) -> bool:
    new_families, old_families = evidence_families(new), evidence_families(existing)
    return (
        same_subject(new, existing)
        and bool(new_families)
        and bool(old_families)
        and new_families.isdisjoint(old_families)
        and source_authority(new) > 0
        and source_authority(new) >= source_authority(existing)
        and eligible_record(new)
        and eligible_record(existing)
    )


def judge_record(item: MemoryItem) -> dict[str, Any]:
    """Bounded context from the canonical row, not an untrusted vector payload."""
    return {
        "memory_id": item.memory_id,
        "content": (item.content or "")[:8192],
        "subject_scope": getattr(item.subject_scope, "value", item.subject_scope),
        "subject_entity_id": item.subject_entity_id,
        "authority": source_authority(item),
        "evidence_families": sorted(evidence_families(item)),
        "as_of": original_evidence_time(item).isoformat(),
        "evidence": [
            {
                "source_type": evidence.source_type,
                "source_id": evidence.source_id,
                "source_version": evidence.source_version,
                "attribution": evidence.attribution,
                "source_signal": evidence.source_signal,
                "quote_refs": evidence.quote_refs[:3],
            }
            for evidence in item.evidence[:5]
            if usable_evidence(evidence)
        ],
    }


def original_evidence_time(item: object) -> datetime:
    """Use known capture time without changing item creation or lifecycle TTL."""
    dates: list[datetime] = []
    for evidence in getattr(item, "evidence", []):
        if isinstance(evidence, MemoryEvidence):
            if usable_evidence(evidence) and isinstance(evidence.captured_at, datetime):
                dates.append(evidence.captured_at)
            continue
        # MemoryDB projections carry evidence as JSON dictionaries.  They are
        # already emitted only for usable evidence by the canonical adapter,
        # but preserve their captured_at clock when a projected row reaches a
        # read-side belief calculation.
        if isinstance(evidence, Mapping):
            captured_at = evidence.get("captured_at")
            if isinstance(captured_at, datetime):
                dates.append(captured_at)
            continue
        captured_at = getattr(evidence, "captured_at", None)
        if isinstance(captured_at, datetime):
            dates.append(captured_at)
    if dates:
        base = max(dates)
    else:
        base = getattr(item, "captured_at", None) or getattr(item, "created_at")
    corroborated = getattr(item, "last_corroborated_at", None)
    return max(base, corroborated) if isinstance(corroborated, datetime) else base

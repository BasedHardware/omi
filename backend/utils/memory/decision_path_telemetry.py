"""Stable, text-free telemetry for canonical memory capture and promotion."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from models.memories import SubjectAttribution

MEMORY_DECISION_PATH_EVENT = "canonical_memory_decision_path.v1"


def _normalized_subject_label(value: str | None) -> str:
    return re.sub(r"[\W_]+", " ", (value or "").casefold()).strip()


def classify_model_about(
    about: str | None,
    *,
    user_name: str | None,
    speaker_label: str | None,
) -> str:
    """Reduce model-authored `about` to a non-PII aggregation token."""
    normalized = _normalized_subject_label(about)
    if not normalized:
        return "empty"
    user_aliases = {"user", "the user", "primary user"}
    normalized_user_name = _normalized_subject_label(user_name)
    if normalized_user_name:
        user_aliases.add(normalized_user_name)
        first_name = normalized_user_name.split(" ", 1)[0]
        if len(first_name) >= 2:
            user_aliases.add(first_name)
    if normalized in user_aliases:
        return "primary_user"
    if normalized in {"unknown", "unclear", "uncertain"}:
        return "unclear"
    if "unidentified non primary speaker" in normalized:
        return "unidentified_non_primary_speaker"
    normalized_speaker = _normalized_subject_label(speaker_label)
    if normalized_speaker and (normalized == normalized_speaker or f" {normalized_speaker} " in f" {normalized} "):
        if normalized_speaker.startswith(("speaker ", "ent speaker ")):
            return "source_speaker"
        return "named_person_role_or_entity"
    if normalized.startswith(("speaker ", "ent speaker ")):
        return "source_speaker"
    return "named_person_role_or_entity"


def model_about_disagrees_with_attribution(model_about: str, attribution: SubjectAttribution) -> bool:
    """Compare directional model attribution with the grounded resolver verdict."""
    if model_about == "primary_user":
        return attribution != SubjectAttribution.user
    if model_about in {
        "source_speaker",
        "unidentified_non_primary_speaker",
        "named_person_role_or_entity",
    }:
        return attribution != SubjectAttribution.third_party
    return False


def _emit(logger: logging.Logger, payload: dict[str, Any]) -> None:
    logger.info("%s %s", MEMORY_DECISION_PATH_EVENT, json.dumps(payload, sort_keys=True, separators=(",", ":")))


def count_speaker_ids(segments: Any) -> tuple[int, int]:
    """Return (distinct speakers, speakers flagged as the account owner).

    Both are telemetry concerns, so they live here rather than in conversation
    processing. The owner count is the one that cannot be reconstructed later: 0 means
    diarization never identified the owner, so every memory from the conversation is
    born third_party and dies at the TTL, and >1 is impossible by construction and
    means speaker clustering shattered one person across several ids.
    """
    distinct: set[Any] = set()
    owner: set[Any] = set()
    for segment in segments:
        speaker_id = getattr(segment, "speaker_id", None)
        if speaker_id is None:
            continue
        distinct.add(speaker_id)
        if getattr(segment, "is_user", False):
            owner.add(speaker_id)
    return len(distinct), len(owner)


def emit_memory_capture_decision(
    logger: logging.Logger,
    *,
    uid: str,
    memory_id: str,
    conversation_id: str,
    capture_regime: str,
    subject_attribution: SubjectAttribution,
    model_about: str,
    attribution_disagreed: bool,
    distinct_speaker_ids: int,
    owner_speaker_ids: int,
) -> None:
    _emit(
        logger,
        {
            "stage": "capture",
            "uid": uid,
            "memory_id": memory_id,
            "conversation_id": conversation_id,
            "capture_regime": capture_regime,
            "subject_attribution": subject_attribution.value,
            "model_about": model_about,
            "attribution_disagreed": attribution_disagreed,
            "distinct_speaker_ids": distinct_speaker_ids,
            # How many distinct speakers the diarizer marked as the account owner.
            # An account has exactly one owner, so 0 means the owner was never
            # identified in this conversation and >1 is impossible-by-construction --
            # neither is derivable from distinct_speaker_ids alone, and both are the
            # states that decide whether a memory can ever be promoted.
            "owner_speaker_ids": owner_speaker_ids,
        },
    )


def emit_memory_promotion_decision(
    logger: logging.Logger,
    *,
    uid: str,
    memory_id: str,
    route: str,
    reconciliation: str,
    relationship_to_user: str,
    aboutness: str,
    basis_for_memory: str,
    confidence: str,
    status: str,
) -> None:
    _emit(
        logger,
        {
            "stage": "promotion",
            "uid": uid,
            "memory_id": memory_id,
            "route": route,
            "status": status,
            "reason_code": f"{reconciliation}:{relationship_to_user}:{aboutness}:{basis_for_memory}",
            "reconciliation": reconciliation,
            "relationship_to_user": relationship_to_user,
            "aboutness": aboutness,
            "basis_for_memory": basis_for_memory,
            "confidence": confidence,
        },
    )


def emit_memory_promotion_failure(
    logger: logging.Logger,
    *,
    uid: str,
    memory_id: str,
    status: str,
    reason_code: str,
    route: str = "none",
) -> None:
    """Emit a text-free terminal for a decision stage that did not apply."""
    _emit(
        logger,
        {
            "stage": "promotion",
            "uid": uid,
            "memory_id": memory_id,
            "route": route,
            "status": status,
            "reason_code": reason_code,
        },
    )

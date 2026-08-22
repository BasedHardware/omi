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

"""Compatibility helpers for explicit canonical memory submissions.

Explicit ``create_memory`` calls retain their durable product contract, but the
submitted text must be processed before it becomes eligible for Long-term.  The
legacy function name remains as a narrow compatibility alias while callers are
migrated to the clearer required-processing vocabulary.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, cast

from models.memory_admission import REQUIRED_PROCESSOR_ID, REQUIRED_PROCESSOR_VERSION
from models.product_memory import MemoryLayer

REQUIRED_PROMOTION_REASON_MANUAL = "manual_user_assertion"
REQUIRED_PROMOTION_STATUS_PENDING = "pending"
REQUIRED_PROMOTION_STATUS_PROMOTED = "promoted"
REQUIRED_PROMOTION_STATUS_FAILED_RETRYABLE = "failed_retryable"
REQUIRED_PROCESSING_STATUS_PENDING = "pending_processing"
REQUIRED_PROCESSING_STATUS_PROCESSED = "processed"
REQUIRED_PROCESSING_STATUS_FAILED_RETRYABLE = "processing_failed_retryable"
ADMISSION_CANDIDATE_STATUS_PENDING = "pending_admission"
REQUIRED_PROMOTION_STATUSES = {
    REQUIRED_PROMOTION_STATUS_PENDING,
    REQUIRED_PROMOTION_STATUS_FAILED_RETRYABLE,
}


def _first_evidence(data: Dict[str, Any]) -> Dict[str, Any]:
    raw_evidence = data.get("evidence")
    if not isinstance(raw_evidence, list) or not raw_evidence:
        return {}
    first = cast(List[Any], raw_evidence)[0]
    return cast(Dict[str, Any], first) if isinstance(first, dict) else {}


def _content_hash(data: Dict[str, Any]) -> str:
    content = str(data.get("content") or "").strip()
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def required_processing_payload(data: Dict[str, Any], *, source_surface: str) -> Dict[str, Any]:
    """Create a readable Short-term submission that requires durable processing.

    ``required`` means the processor must eventually produce a durable outcome;
    it no longer means that the raw submitted text is immediately promotable.
    """
    payload = dict(data)
    payload["memory_tier"] = MemoryLayer.short_term.value
    payload["user_asserted"] = bool(payload.get("user_asserted") or payload.get("manually_added"))
    payload["manually_added"] = bool(payload.get("manually_added"))
    evidence = _first_evidence(payload)
    submitted_at = datetime.now(timezone.utc).isoformat()
    promotion = dict(payload.get("promotion") or {})
    promotion.update(
        {
            "required": True,
            "status": REQUIRED_PROMOTION_STATUS_PENDING,
            "reason": promotion.get("reason") or REQUIRED_PROMOTION_REASON_MANUAL,
            "source_surface": source_surface,
            "attempt_count": int(promotion.get("attempt_count") or 0),
            "processing_status": REQUIRED_PROCESSING_STATUS_PENDING,
            "processor_id": REQUIRED_PROCESSOR_ID,
            "processor_version": REQUIRED_PROCESSOR_VERSION,
            "submission": {
                "submission_id": str(payload.get("id") or ""),
                "source_surface": source_surface,
                "source_type": evidence.get("source_type") or "api",
                "source_id": evidence.get("source_id"),
                "client_device_id": evidence.get("client_device_id"),
                "app_id": payload.get("app_id"),
                "content_hash": _content_hash(payload),
                "submitted_at": submitted_at,
            },
        }
    )
    payload["promotion"] = promotion
    return payload


def required_promotion_payload(data: Dict[str, Any], *, source_surface: str) -> Dict[str, Any]:
    """Backward-compatible alias for callers using the old helper name."""
    return required_processing_payload(data, source_surface=source_surface)

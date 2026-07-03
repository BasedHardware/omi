"""Helpers for canonical manual writes that must later promote to long-term."""

from __future__ import annotations

from typing import Any, Dict

from models.product_memory import MemoryLayer

REQUIRED_PROMOTION_REASON_MANUAL = "manual_user_assertion"
REQUIRED_PROMOTION_STATUS_PENDING = "pending"
REQUIRED_PROMOTION_STATUS_PROMOTED = "promoted"
REQUIRED_PROMOTION_STATUS_FAILED_RETRYABLE = "failed_retryable"
REQUIRED_PROMOTION_STATUSES = {
    REQUIRED_PROMOTION_STATUS_PENDING,
    REQUIRED_PROMOTION_STATUS_FAILED_RETRYABLE,
}


def required_promotion_payload(data: Dict[str, Any], *, source_surface: str) -> Dict[str, Any]:
    """Mark a user/API asserted canonical write as short_term with mandatory promotion."""
    payload = dict(data)
    payload["memory_tier"] = MemoryLayer.short_term.value
    payload["user_asserted"] = True
    payload["manually_added"] = True
    promotion = dict(payload.get("promotion") or {})
    promotion.update(
        {
            "required": True,
            "status": promotion.get("status") or REQUIRED_PROMOTION_STATUS_PENDING,
            "reason": promotion.get("reason") or REQUIRED_PROMOTION_REASON_MANUAL,
            "source_surface": source_surface,
            "attempt_count": int(promotion.get("attempt_count") or 0),
        }
    )
    payload["promotion"] = promotion
    return payload

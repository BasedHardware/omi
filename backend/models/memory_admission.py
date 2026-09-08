"""Canonical durable-memory admission receipt contract."""

from __future__ import annotations

import hashlib
from typing import Any, Dict

REQUIRED_PROCESSING_RECEIPT_VERSION = "canonical_memory_processing_receipt.v1"
REQUIRED_PROCESSOR_ID = "canonical_required_memory"
REQUIRED_PROCESSOR_VERSION = "v1"


def valid_required_processing_receipt(
    *,
    content: str,
    item_revision: int,
    promotion: Dict[str, Any],
) -> bool:
    """Return whether admission proof is bound to the current content lineage."""
    receipt = promotion.get("processing_receipt")
    submission = promotion.get("submission")
    if not isinstance(receipt, dict) or not isinstance(submission, dict):
        return False
    if receipt.get("receipt_version") != REQUIRED_PROCESSING_RECEIPT_VERSION:
        return False
    if receipt.get("processor_id") != REQUIRED_PROCESSOR_ID:
        return False
    if receipt.get("processor_version") != REQUIRED_PROCESSOR_VERSION:
        return False
    if promotion.get("processor_id") != REQUIRED_PROCESSOR_ID:
        return False
    if promotion.get("processor_version") != REQUIRED_PROCESSOR_VERSION:
        return False
    if receipt.get("decision") != "durable_required":
        return False
    submission_id = submission.get("submission_id")
    if not submission_id or receipt.get("source_submission_id") != submission_id:
        return False
    if receipt.get("input_hash") != submission.get("content_hash"):
        return False
    if receipt.get("output_hash") != hashlib.sha256(content.encode("utf-8")).hexdigest():
        return False
    input_revision = receipt.get("input_item_revision")
    return (
        isinstance(input_revision, int)
        and isinstance(receipt.get("output_item_revision"), int)
        and input_revision + 1 == receipt["output_item_revision"]
        and receipt["output_item_revision"] <= item_revision
    )


__all__ = [
    "REQUIRED_PROCESSING_RECEIPT_VERSION",
    "REQUIRED_PROCESSOR_ID",
    "REQUIRED_PROCESSOR_VERSION",
    "valid_required_processing_receipt",
]

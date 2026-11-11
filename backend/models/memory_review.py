"""Pure contract for deterministic canonical-memory review queue records."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


def build_memory_review_conflict(
    *,
    fact: Dict[str, Any],
    conflict_with: List[str],
    authority: Optional[str] = None,
    source_commit_id: Optional[str] = None,
    source_item_revision: Optional[int] = None,
    source_content_hash: Optional[str] = None,
    source_short_term_id: Optional[str] = None,
    impact: Optional[float] = None,
    ttl_hours: int = 72,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Build the stable document written by both legacy and canonical review paths."""
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        raise ValueError("review conflict timestamp must be timezone-aware")
    fact_id = str(fact.get("id") or "").strip()
    if not fact_id:
        raise ValueError("review conflict requires fact.id")
    if authority == "canonical_memory" and (
        not source_commit_id or source_item_revision is None or source_item_revision < 1 or not source_content_hash
    ):
        raise ValueError("canonical review requires an exact source commit, revision, and content hash")
    conflicts = sorted({value.strip() for value in conflict_with if value and value.strip()})
    revision_segment = f"r{source_item_revision}:" if authority == "canonical_memory" else ""
    review_id = f"review:{fact_id}:{revision_segment}{','.join(conflicts)}"
    item = {
        "review_id": review_id,
        "fact_id": fact_id,
        "candidate": fact,
        "conflict_with": conflicts,
        "veracity": fact.get("veracity"),
        "impact": impact if impact is not None else fact.get("importance", 0.5),
        "status": "pending",
        "source_commit_id": source_commit_id,
        "source_short_term_id": source_short_term_id,
        "created_at": current_time,
        "updated_at": current_time,
        "expires_at": current_time + timedelta(hours=ttl_hours),
        "permitted_uses": ["answers_with_disclaimer"],
    }
    if authority is not None:
        item["authority"] = authority
    if source_item_revision is not None:
        item["source_item_revision"] = source_item_revision
    if source_content_hash is not None:
        item["source_content_hash"] = source_content_hash
    item["referenced_memory_ids"] = sorted({fact_id, *conflicts})
    return item


__all__ = ["build_memory_review_conflict"]

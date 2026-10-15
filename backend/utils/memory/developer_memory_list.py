"""Developer API memory list reads under the request list-read budget."""

from __future__ import annotations

from typing import Any, List, Optional

from pydantic import ValidationError

from utils.other.list_budget import ListReadBudget, ListReadBudgetExhausted


def _validated_memories(memories: List[Any], response_model: Any, logger: Any) -> list:
    valid_memories = []
    for memory in memories:
        try:
            valid_memories.append(response_model.model_validate(memory.model_dump(mode="json")))
        except (AttributeError, TypeError, ValidationError, ValueError):
            # MemoryService normally returns validated MemoryDB rows, but a
            # malformed historical adapter row must not turn this compatibility
            # endpoint into a 500 for every otherwise healthy memory.
            logger.warning("Skipping malformed memory in Developer API list")
    return valid_memories


def read_developer_memories(
    service: Any,
    uid: str,
    *,
    limit: int,
    offset: int,
    allowed: Optional[set],
    budget: ListReadBudget,
    response_model: Any,
    logger: Any,
) -> list:
    """Fetch the developer memory page, honoring the request's list-read budget."""
    if allowed is None:
        try:
            memories = service.read(uid, limit=limit, offset=offset, include_pending_processing=True, budget=budget)
        except ListReadBudgetExhausted as exc:
            budget.mark_exhausted(exc.reason)
            memories = []
        return _validated_memories(memories, response_model, logger)
    # Category is a sparse filter.  Read ordered universal pages until the
    # requested category page is filled instead of filtering after a raw page
    # (which returned short/empty pages whenever non-matching memories led it).
    target_end = offset + limit
    scan_offset = 0
    matched = []
    max_scan = 5000
    source_exhausted = False
    while scan_offset < max_scan and len(matched) < target_end:
        batch_limit = min(500, max_scan - scan_offset)
        try:
            budget.check()
            batch = service.read(
                uid, limit=batch_limit, offset=scan_offset, include_pending_processing=True, budget=budget
            )
        except ListReadBudgetExhausted as exc:
            budget.mark_exhausted(exc.reason)
            break
        if not batch:
            source_exhausted = True
            break
        scan_offset += len(batch)
        matched.extend(memory for memory in batch if getattr(memory.category, "value", memory.category) in allowed)
        if len(batch) < batch_limit:
            source_exhausted = True
            break
    if not source_exhausted and len(matched) < target_end and not budget.truncated:
        budget.mark_exhausted('documents')
    return _validated_memories(matched[offset:target_end], response_model, logger)

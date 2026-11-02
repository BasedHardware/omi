"""Sparse category windows inside one admitted universal memory read operation."""

from typing import Any, Callable

from fastapi import HTTPException

from utils.other.list_budget import ListReadBudget, ListReadBudgetExhausted


def read_category_window(
    read_window: Callable[..., list[Any]],
    uid: str,
    *,
    limit: int,
    offset: int,
    category_filter: set[str],
    max_window: int,
    budget: ListReadBudget | None = None,
    **kwargs: Any,
) -> list[Any]:
    target = max(0, offset) + max(1, limit)
    if target > max_window:
        raise HTTPException(status_code=413, detail='Memory pagination window exceeded')
    matched: list[Any] = []
    scanned = 0
    size = min(500, max(25, target))
    exhausted = False
    try:
        while scanned < max_window and len(matched) < target:
            take = min(size, max_window - scanned)
            if budget is not None:
                budget.check()
            batch = read_window(uid, limit=take, offset=scanned, budget=budget, **kwargs)
            scanned += len(batch)
            matched.extend(row for row in batch if getattr(row.category, 'value', row.category) in category_filter)
            if len(batch) < take:
                exhausted = True
                break
            size = min(500, size * 2)
    except ListReadBudgetExhausted as exc:
        if budget is not None:
            budget.mark_exhausted(exc.reason)
    if not exhausted and len(matched) < target and budget is not None and not budget.truncated:
        budget.mark_exhausted('documents')
    return matched[max(0, offset) : target]

"""Shared bounded mechanics for upgrade/reset access restoration."""

from typing import Any, Callable


def unlock_query_rows(
    database: Any,
    query: Any,
    update: dict[str, Any],
    *,
    limit: int | None = None,
    on_commit: Callable[[], None] | None = None,
) -> int:
    if limit is not None:
        if not 1 <= limit <= 499:
            raise ValueError('unlock limit must be between 1 and 499')
        query = query.select([]).limit(limit)
    batch = database.batch()
    count = total = 0
    for doc in query.stream():
        batch.update(doc.reference, update)
        count += 1
        total += 1
        if count == 499:
            batch.commit()
            if on_commit:
                on_commit()
            batch = database.batch()
            count = 0
    if count:
        batch.commit()
        if on_commit:
            on_commit()
    if limit is not None and total == 0 and on_commit:
        # A retry repairs invalidation after an ambiguous successful commit.
        on_commit()
    return total

"""Read-only, content-free inventory for bulk legacy-memory planning.

LIFECYCLE: permanent
"""

from __future__ import annotations

from typing import Any

from database._client import db as default_db_client
from database.memories import get_non_filtered_memories
from utils.memory.legacy_backfill import (
    LegacyReader,
    bucket_counts_and_samples,
    fetch_active_legacy_memories,
    is_legacy_backfill_admissible,
    row_content,
)
from utils.memory.legacy_backfill_support import LegacyBackfillInventoryReport


def inventory_legacy_user(
    uid: str,
    *,
    db_client: Any = None,
    get_non_filtered_memories_fn: LegacyReader = get_non_filtered_memories,
) -> LegacyBackfillInventoryReport:
    """Return counts and token proxies without logging or returning memory content."""
    client: Any = db_client if db_client is not None else default_db_client
    legacy_rows = fetch_active_legacy_memories(
        uid,
        db_client=client,
        get_non_filtered_memories_fn=get_non_filtered_memories_fn,
    )
    eligible_rows = [row for row in legacy_rows if row_content(row)]
    bucket_counts, _ = bucket_counts_and_samples(eligible_rows, sample_size=0)
    admitted_rows = [row for row in eligible_rows if is_legacy_backfill_admissible(row)]
    content_character_count = sum(len(row_content(row)) for row in eligible_rows)
    admitted_character_count = sum(len(row_content(row)) for row in admitted_rows)
    return LegacyBackfillInventoryReport(
        uid=uid,
        source_count=len(eligible_rows),
        bucket_counts=bucket_counts,
        admitted_candidate_count=len(admitted_rows),
        content_character_count=content_character_count,
        estimated_tokens=(content_character_count + 3) // 4,
        admitted_candidate_estimated_tokens=(admitted_character_count + 3) // 4,
    )


__all__ = ["inventory_legacy_user"]
